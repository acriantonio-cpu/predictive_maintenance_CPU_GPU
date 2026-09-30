# SPDX-License-Identifier: Apache-2.0
"""Gestione delle carte di controllo: segmenti, Fase I/II, segnali (sezione 7).

* Una carta è identificata da ``indicatore|regime|livello`` (livello = ``window``
  o ``daily``).
* Segmenti: dopo una manutenzione dichiarata (o ``baseline start``) il segmento
  si chiude e ne parte uno nuovo con una nuova Fase I; il precedente resta
  archiviato.
* Fase I: si chiude al primo istante in cui sono soddisfatti numero minimo di
  osservazioni, di giorni e di sessioni diverse. Anche se l'analisi gira su mesi di
  storico in un colpo solo, la Fase I usa solo il prefisso cronologico minimo:
  così un guasto successivo non entra nei limiti.
* Prima della chiusura i limiti sono *provvisori* (più larghi) e i punti oltre 3σ
  producono solo segnali ``provisional`` (livello info).
* I limiti bloccati non si aggiornano da soli (failure mode 8).
"""

from __future__ import annotations

import bisect
import json
import sqlite3
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..indicators.definitions import SECONDARY_BASES, definition, split
from ..spc import assumptions as assum
from ..spc.count_charts import c_chart, c_signals
from ..spc.cusum import cusum
from ..spc.ewma import ewma
from ..spc.imr import Limits, imr_limits, phase_one
from ..spc.rules import evaluate
from ..spc.trend import mann_kendall

DAY_MS = 86_400_000
# sigma minima per indicatore (nelle unità dell'indicatore)
SIGMA_FLOOR = {"throttle_frac": 0.01, "rth": 1e-4, "idle_temp": 0.05, "hotspot_delta": 0.05,
               "fan_effort": 1.0, "case_delta": 0.05}
SESSION_GAP_MS = 2 * 3_600_000


@dataclass
class Segment:
    chart_id: str
    segment: int
    phase: str
    provisional: bool
    start_ts: int
    locked_ts: int | None
    closed_ts: int | None
    params: dict[str, Any]
    limits: Limits | None


def _load_segments(conn: sqlite3.Connection, chart_id: str) -> list[Segment]:
    out = []
    for r in conn.execute(
        "SELECT segment, phase, provisional, start_ts, locked_ts, closed_ts, center, sigma, "
        "mr_bar, ucl, lcl, ucl_mr, params FROM chart_state WHERE chart_id=? ORDER BY segment",
        (chart_id,),
    ):
        params = json.loads(r[12] or "{}")
        lim = None
        if r[6] is not None and r[7] is not None:
            lim = Limits(r[6], r[7], r[8] or 0.0, r[9], r[10], r[11] or 0.0,
                         params.get("method", "mr"), params.get("widen", 1.0))
        out.append(Segment(chart_id, r[0], r[1], bool(r[2]), r[3], r[4], r[5], params, lim))
    return out


def _save(conn: sqlite3.Connection, s: Segment, now: int) -> None:
    lim = s.limits
    conn.execute(
        "INSERT OR REPLACE INTO chart_state(chart_id, segment, phase, provisional, start_ts, "
        "locked_ts, closed_ts, center, sigma, mr_bar, ucl, lcl, ucl_mr, n_phase1, params, "
        "updated_ts) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (s.chart_id, s.segment, s.phase, int(s.provisional), s.start_ts, s.locked_ts, s.closed_ts,
         lim.center if lim else None, lim.sigma if lim else None, lim.mr_bar if lim else None,
         lim.ucl if lim else None, lim.lcl if lim else None, lim.ucl_mr if lim else None,
         int(s.params.get("n_phase1", 0)), json.dumps(s.params, default=_json_default), now),
    )


def _json_default(o: Any) -> Any:
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.bool_):
        return bool(o)
    raise TypeError(type(o))


def _session_starts(ts: np.ndarray) -> np.ndarray:
    """Inizio di una nuova sessione: pausa > 2 h o cambio di giorno (UTC)."""
    if ts.size == 0:
        return np.zeros(0, dtype=bool)
    days = ts // DAY_MS
    return np.r_[True, (np.diff(ts) > SESSION_GAP_MS) | (np.diff(days) != 0)]


def _sessions(ts: np.ndarray) -> int:
    return int(_session_starts(ts).sum())


def _lock_index(ts: np.ndarray, level: str, spc: dict[str, Any], min_obs: int) -> int | None:
    """Indice (esclusivo) del più corto prefisso che soddisfa i criteri di chiusura."""
    n = ts.size
    if n < min_obs:
        return None
    if level == "daily":
        return min_obs
    days = ts // DAY_MS
    cum_days = np.cumsum(np.r_[True, np.diff(days) != 0])
    cum_sess = np.cumsum(_session_starts(ts))
    ok = ((np.arange(1, n + 1) >= min_obs) & (cum_days >= spc["phase1_min_days"])
          & (cum_sess >= spc["phase1_min_sessions"]))
    idx = np.flatnonzero(ok)
    return int(idx[0]) + 1 if idx.size else None


def _label(ts: int, cfg_times: list[int], window_ms: int) -> str:
    k = bisect.bisect_left(cfg_times, ts - window_ms)
    return "configuration" if k < len(cfg_times) and cfg_times[k] <= ts + window_ms else \
        "maintenance"


class ChartEngine:
    def __init__(self, conn: sqlite3.Connection, cfg: dict[str, Any],
                 breaks: list[tuple[int, str | None]],
                 cfg_times: list[int], now: int, force_lock: set[str] | None = None,
                 chart_breaks: dict[str, list[int]] | None = None) -> None:
        self.conn = conn
        self.cfg = cfg
        self.spc = cfg["spc"]
        self.breaks = breaks
        self.cfg_times = cfg_times
        self.cfg_window_ms = int(cfg["alerts"]["config_window_h"] * 3_600_000)
        self.now = now
        self.force_lock = force_lock or set()
        self.chart_breaks = chart_breaks or {}
        self.new_signals = 0

    # --------------------------------------------------------------- signals
    def _signal(self, seg: Segment, ts: int, rule: str, side: str, value: float,
                points: list[int], label: str | None = None) -> None:
        lab = label or _label(ts, self.cfg_times, self.cfg_window_ms)
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO signals(chart_id, segment, ts, rule, side, value, points, "
            "severity, label) VALUES (?,?,?,?,?,?,?,?,?)",
            (seg.chart_id, seg.segment, int(ts), rule, side, float(value), json.dumps(points),
             "info", lab),
        )
        self.new_signals += cur.rowcount

    # ------------------------------------------------------------------ main
    def update(self, indicator: str, regime: str, level: str) -> Segment | None:
        chart_id = f"{indicator}|{regime}|{level}"
        rows = self.conn.execute(
            "SELECT ts, value FROM indicators WHERE indicator=? AND regime=? AND level=? "
            "ORDER BY ts", (indicator, regime, level)).fetchall()
        if not rows:
            return None
        ts_all = np.array([r[0] for r in rows], dtype=np.int64)
        val_all = np.array([r[1] for r in rows], dtype=float)
        segs = _load_segments(self.conn, chart_id)
        if not segs:
            segs = [Segment(chart_id, 1, "I", True, int(ts_all[0]), None, None, {}, None)]
        cur = segs[-1]
        d = definition(indicator)
        suffix = split(indicator)[1]
        mine = {ts for ts, scope in self.breaks if scope is None or scope == suffix}
        breaks = sorted(mine | set(self.chart_breaks.get(chart_id, [])))
        limit = max(self.now, int(ts_all[-1]))
        for b in breaks:
            if b <= cur.start_ts or b > limit:
                continue
            # il segmento si elabora con i dati fino alla chiusura (anche quando l'analisi
            # recupera settimane in un colpo solo), poi si archivia
            m = (ts_all >= cur.start_ts) & (ts_all < b)
            if m.any():
                self._process(cur, ts_all[m], val_all[m], level, indicator, d)
            self.conn.execute("DELETE FROM signals WHERE chart_id=? AND segment=? AND ts>=?",
                              (chart_id, cur.segment, b))
            cur.closed_ts = b
            _save(self.conn, cur, self.now)
            cur = Segment(chart_id, cur.segment + 1, "I", True, b, None, None, {}, None)
        mask = ts_all >= cur.start_ts
        if mask.any():
            self._process(cur, ts_all[mask], val_all[mask], level, indicator, d)
        _save(self.conn, cur, self.now)
        return cur

    def _process(self, seg: Segment, ts: np.ndarray, vals: np.ndarray, level: str,
                 indicator: str, d: Any) -> None:
        if d is not None and d.kind == "count":
            self._update_count(seg, ts, vals)
        else:
            self._update_imr(seg, ts, vals, level, indicator)

    # ------------------------------------------------------------------- I-MR
    def _update_imr(self, seg: Segment, ts: np.ndarray, vals: np.ndarray, level: str,
                    indicator: str) -> None:
        spc = self.spc
        seg.params["n"] = int(ts.size)
        if seg.locked_ts is None:
            k = _lock_index(ts, level, spc, spc["phase1_min_obs"])
            forced = seg.chart_id in self.force_lock or "*" in self.force_lock
            if k is None and forced and ts.size >= spc["provisional_min_obs"]:
                k = int(ts.size)
            if k is not None:
                self._lock(seg, ts[:k], vals[:k], provisional=(forced and
                                                               _lock_index(ts, level, spc,
                                                                           spc["phase1_min_obs"])
                                                               is None))
            else:
                self._provisional(seg, ts, vals)
                return
        assert seg.locked_ts is not None and seg.limits is not None
        if seg.params.get("degenerate"):
            return
        m2 = ts > seg.locked_ts
        t2, v2 = ts[m2], vals[m2]
        seg.params["n_phase2"] = int(t2.size)
        if t2.size == 0:
            return
        lim = seg.limits
        longterm = level == "window"
        rules = tuple(spc["window_rules"]) if longterm else tuple(spc["rules"])
        for s in evaluate(v2, lim, rules, spc["r2_run"], spc["r3_run"], include_mr=not longterm):
            self._signal(seg, int(t2[s.index]), s.rule, s.side, float(v2[s.index]),
                         [int(t2[p]) for p in s.points])
        if longterm:
            return  # EWMA/CUSUM presuppongono indipendenza: solo sulle carte giornaliere
        sig = lim.sigma * lim.widen
        er = ewma(v2, lim.center, sig, spc["ewma_lambda"], spc["ewma_L"])
        for i, side in er.signals:
            self._signal(seg, int(t2[i]), "EWMA", side, float(v2[i]), [int(t2[i])])
        cr = cusum(v2, lim.center, sig, spc["cusum_k"], spc["cusum_h"])
        for i, side in cr.signals:
            self._signal(seg, int(t2[i]), "CUSUM", side, float(v2[i]), [int(t2[i])])
        if level == "daily" and t2.size >= spc["mk_min_days"]:
            mk = mann_kendall(v2)
            if mk.p < spc["mk_alpha"]:
                self._signal(seg, int(t2[-1]), "MK", "upper" if mk.tau > 0 else "lower",
                             float(v2[-1]), [int(t2[0]), int(t2[-1])])
            seg.params["mk"] = {"tau": mk.tau, "p": mk.p, "sen_slope": mk.sen_slope}

    def _lock(self, seg: Segment, ts: np.ndarray, vals: np.ndarray, provisional: bool) -> None:
        spc = self.spc
        checks = assum.check(vals, spc["acf_threshold"])
        method = spc["sigma"] if spc["sigma"] != "auto" else str(checks["sigma_recommended"])
        level = seg.chart_id.rsplit("|", 1)[-1]
        if level == "window":
            # le osservazioni per finestra sono reattive ma autocorrelate (finestre della
            # stessa sessione si somigliano): sigma di lungo periodo e solo le regole
            # "a punto singolo" (spc.window_rules, default R1). Le regole di sequenza e i
            # metodi a memoria (EWMA, CUSUM, Mann-Kendall) girano sulla carta giornaliera.
            method = "longterm"
        widen = spc["provisional_widen"] if provisional else 1.0
        floor = SIGMA_FLOOR.get(split(seg.chart_id.split("|")[0])[0], 0.0)
        if float(np.std(vals)) == 0.0 and floor == 0.0:
            seg.params.update({"degenerate": True, "n_phase1": int(ts.size)})
            seg.locked_ts = int(ts[-1])
            seg.phase = "II"
            seg.provisional = provisional
            seg.limits = Limits(float(vals.mean()), 0.0, 0.0, float(vals.mean()),
                                float(vals.mean()), 0.0, method, widen)
            return
        res = phase_one(vals, method, spc["phase1_max_iterations"], widen)
        if res.limits.sigma == 0.0 and method != "mr":
            res = phase_one(vals, "mr", spc["phase1_max_iterations"], widen)
        if res.limits.sigma < floor or res.limits.sigma == 0.0:
            # serie quasi sempre costante (es. throttling sempre a zero in Fase I):
            # sigma minima, altrimenti qualsiasi variazione sarebbe fuori limite o
            # la carta non esisterebbe
            sig = max(floor, 1e-9)
            c = res.limits.center
            res = type(res)(Limits(c, sig, sig * 1.128, c + 3 * sig * widen,
                                   c - 3 * sig * widen, 3.267 * sig * 1.128 * widen,
                                   method + "+floor", widen),
                            res.kept, res.excluded, res.iterations)
        seg.limits = res.limits
        seg.locked_ts = int(ts[-1])
        seg.phase = "II"
        seg.provisional = provisional
        seg.params.update({
            "n_phase1": int(ts.size), "method": method, "widen": widen,
            "excluded_ts": [int(ts[i]) for i in res.excluded], "iterations": res.iterations,
            "assumptions": checks, "phase1_days": int(np.unique(ts // DAY_MS).size),
            "phase1_sessions": _sessions(ts),
        })

    def _provisional(self, seg: Segment, ts: np.ndarray, vals: np.ndarray) -> None:
        spc = self.spc
        n0 = spc["provisional_min_obs"]
        seg.phase = "I"
        seg.provisional = True
        if ts.size < n0:
            seg.limits = None
            seg.params["status"] = "insufficient"
            return
        seg.params["status"] = "provisional"
        widen = spc["provisional_widen"]
        if np.std(vals) > 0:
            seg.limits = imr_limits(vals, "mr", widen)
        checked = int(seg.params.get("prov_checked_ts", 0))
        for i in range(n0, ts.size):
            if ts[i] <= checked:
                continue
            prior = vals[:i]
            if np.std(prior) == 0:
                continue
            lim = imr_limits(prior, "mr", widen)
            if vals[i] > lim.ucl or vals[i] < lim.lcl:
                self._signal(seg, int(ts[i]), "R1", "upper" if vals[i] > lim.ucl else "lower",
                             float(vals[i]), [int(ts[i])], label="provisional")
        seg.params["prov_checked_ts"] = int(ts[-1])

    # ----------------------------------------------------------------- counts
    def _update_count(self, seg: Segment, ts: np.ndarray, vals: np.ndarray) -> None:
        min_obs = self.spc["count_phase1_obs"]
        seg.params["n"] = int(ts.size)
        seg.params["chart"] = "c"
        if seg.locked_ts is None:
            if ts.size < min_obs:
                seg.params["status"] = "insufficient"
                return
            lim = c_chart(vals[:min_obs])
            seg.limits = Limits(lim.center, float(np.sqrt(lim.center)), 0.0, lim.ucl, lim.lcl,
                                0.0, "poisson", 1.0)
            seg.locked_ts = int(ts[min_obs - 1])
            seg.phase = "II"
            seg.provisional = False
            seg.params["n_phase1"] = min_obs
        assert seg.limits is not None
        m2 = ts > seg.locked_ts
        t2, v2 = ts[m2], vals[m2]
        from ..spc.count_charts import CLimits

        for i in c_signals(v2, CLimits(seg.limits.center, seg.limits.ucl, seg.limits.lcl)):
            self._signal(seg, int(t2[i]), "C", "upper", float(v2[i]), [int(t2[i])])


def is_primary(indicator: str, primary: list[str]) -> bool:
    return indicator in primary and split(indicator)[0] not in SECONDARY_BASES
