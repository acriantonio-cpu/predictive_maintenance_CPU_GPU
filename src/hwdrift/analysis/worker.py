# SPDX-License-Identifier: Apache-2.0
"""Worker di analisi (``hwdrift analyze``): gira a intervalli, a priorità bassa.

Passi, tutti incrementali e idempotenti:

1. finestre stazionarie per componente;
2. calibrazione dei regimi e assegnazione;
3. indicatori per finestra (Rth, sforzo ventola, hotspot, idle);
4. modelli di baseline e residui, modello continuo;
5. indicatori giornalieri (mediane, throttling, conteggi);
6. carte di controllo e segnali;
7. politica di allarme e ipotesi di diagnosi.

Il worker legge i dati grezzi e scrive solo le tabelle di analisi.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
import time
from collections import defaultdict
from typing import Any

import numpy as np

from ..context.components import Component, components
from ..context.events import config_times, confounder_times, scoped_breaks, segment_breaks
from ..context.minutes import load_minutes
from ..context.regimes import RegimeBounds, calibrate
from ..context.windows import find_windows
from ..indicators import baseline as bl
from ..indicators.definitions import COUNT_EVENT_KINDS
from ..indicators.rth import window_indicators
from ..storage.schema import get_meta, set_meta
from .charts import ChartEngine

log = logging.getLogger(__name__)
DAY_MS = 86_400_000
MIN_MS = 60_000


def conn_has_kind(conn: sqlite3.Connection, kind: str) -> bool:
    return conn.execute("SELECT 1 FROM events WHERE kind=? LIMIT 1", (kind,)).fetchone() is not None


def lower_priority() -> None:
    """Priorità BELOW_NORMAL su Windows, nice 10 altrove."""
    try:
        import psutil

        p = psutil.Process()
        if sys.platform == "win32":
            p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)  # type: ignore[attr-defined]
        else:
            p.nice(10)
    except Exception:
        log.debug("impossibile abbassare la priorità", exc_info=True)


def reference_series(cfg: dict[str, Any], mf_get, mf_has, n: int) -> tuple[np.ndarray | None, str]:
    ref = cfg["profile"]["reference"]
    if ref["mode"] == "user":
        return np.full(n, float(ref["value_c"])), "user"
    if ref["mode"] == "channel" and mf_has(ref["channel"]):
        return mf_get(ref["channel"]), ref["channel"]
    return None, "none"


class Worker:
    def __init__(self, conn: sqlite3.Connection, cfg: dict[str, Any]) -> None:
        self.conn = conn
        self.cfg = cfg
        self.summary: dict[str, Any] = {"warnings": []}

    # -------------------------------------------------------------- helpers
    def _channels(self) -> set[str]:
        return {r[0] for r in self.conn.execute("SELECT name FROM channels")}

    def data_now(self) -> int:
        row = self.conn.execute("SELECT MAX(ts) FROM agg_1min").fetchone()
        real = int(time.time() * 1000)
        return min(int(row[0]) + MIN_MS, real) if row and row[0] is not None else real

    def _bounds(self, comp: str) -> RegimeBounds | None:
        raw = get_meta(self.conn, f"regimes:{comp}")
        return RegimeBounds.from_dict(json.loads(raw)) if raw else None

    # ---------------------------------------------------------- 1. windows
    def step_windows(self, comp: Component) -> int:
        wcfg = self.cfg["windows"]
        row = self.conn.execute("SELECT MAX(end_ts) FROM windows WHERE component=?",
                                (comp.key,)).fetchone()
        scanned = get_meta(self.conn, f"windows_scan:{comp.key}")
        start_from = max(int(row[0]) if row[0] else 0, int(scanned) if scanned else 0) or None
        lookback = (int(wcfg["length_min"]) + int(wcfg["warmup_min"]) + 1) * MIN_MS
        since = start_from - lookback if start_from else None
        ref_cfg = self.cfg["profile"]["reference"]
        chans = [comp.power, comp.temp, comp.util, comp.throttle_thermal, comp.throttle_power,
                 *comp.fans, "mb.temp_c"]
        if comp.hotspot:
            chans.append(comp.hotspot)
        if ref_cfg["mode"] == "channel":
            chans.append(ref_cfg["channel"])
        mf = load_minutes(self.conn, chans, since=since, grid_channel=comp.power)
        if mf.ts.size == 0:
            return 0
        ref, ref_name = reference_series(self.cfg, mf.get, mf.has, mf.ts.size)
        self.summary["reference"] = ref_name
        if ref_name == "none" and ref_cfg["mode"] != "none":
            msg = (f"riferimento T_rif '{ref_cfg.get('channel')}' non disponibile: "
                   "si usa la temperatura assoluta")
            if msg not in self.summary["warnings"]:
                self.summary["warnings"].append(msg)
        wins = find_windows(mf, comp, wcfg, confounder_times(self.conn), ref, start_from)
        bounds = self._bounds(comp.key)
        with self.conn:
            for w in wins:
                regime = bounds.assign(w.power_mean) if bounds else None
                self.conn.execute(
                    "INSERT OR IGNORE INTO windows(component, start_ts, end_ts, regime, "
                    "power_mean, power_cv, temp_slope, throttled, summary) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (w.component, w.start_ts, w.end_ts, regime, w.power_mean, w.power_cv,
                     w.temp_slope, int(w.throttled), json.dumps(w.summary)),
                )
            # le ultime (length+warmup) minuti possono ancora formare una finestra
            last_scan = int(mf.ts[-1]) - lookback
            set_meta(self.conn, f"windows_scan:{comp.key}", str(max(last_scan, 0)))
        return len(wins)

    # ---------------------------------------------------------- 2. regimes
    def step_regimes(self, comp: Component) -> RegimeBounds | None:
        bounds = self._bounds(comp.key)
        rcfg = self.cfg["regimes"]
        if bounds is None:
            rows = self.conn.execute(
                "SELECT power_mean FROM windows WHERE component=? AND throttled=0 "
                "ORDER BY start_ts", (comp.key,)).fetchall()
            if len(rows) < rcfg["calibration_windows"]:
                return None
            cid = self.conn.execute("SELECT id FROM channels WHERE name=?",
                                    (comp.power,)).fetchone()
            mx = np.array([r[0] for r in self.conn.execute(
                "SELECT max FROM agg_1min WHERE channel_id=? AND max IS NOT NULL",
                (cid[0],))], dtype=float) if cid else np.empty(0)
            bounds = calibrate(np.array([r[0] for r in rows]), mx, rcfg["mode"],
                               rcfg["fixed_fractions"])
            with self.conn:
                set_meta(self.conn, f"regimes:{comp.key}", json.dumps(bounds.to_dict()))
        with self.conn:
            for wid, p in self.conn.execute(
                    "SELECT id, power_mean FROM windows WHERE component=? AND regime IS NULL",
                    (comp.key,)).fetchall():
                self.conn.execute("UPDATE windows SET regime=? WHERE id=?",
                                  (bounds.assign(p), wid))
        return bounds

    # ------------------------------------------------------- 3. indicators
    def step_window_indicators(self, comp: Component) -> int:
        n = 0
        with self.conn:
            rows = self.conn.execute(
                "SELECT id, start_ts, regime, throttled, summary FROM windows "
                "WHERE component=? AND ind_done=0 AND regime IS NOT NULL", (comp.key,)).fetchall()
            for wid, ts, regime, thr, summ in rows:
                summary = json.loads(summ)
                for name, value in window_indicators(comp.suffix, regime, summary, bool(thr),
                                                     "tref" in summary):
                    if not np.isfinite(value):
                        continue
                    self.conn.execute(
                        "INSERT OR IGNORE INTO indicators(ts, indicator, regime, level, value, "
                        "window_id) VALUES (?,?,?,?,?,?)", (ts, name, regime, "window", value, wid))
                    n += 1
                self.conn.execute("UPDATE windows SET ind_done=1 WHERE id=?", (wid,))
        return n

    # ----------------------------------------------------- 4. baseline models
    def step_models(self, comp: Component) -> None:
        breaks = segment_breaks(self.conn)
        since = breaks[-1] if breaks else 0
        need = max(self.cfg["spc"]["min_windows_for_model"], self.cfg["spc"]["phase1_min_obs"])
        rows = self.conn.execute(
            "SELECT start_ts, regime, summary FROM windows WHERE component=? AND throttled=0 "
            "AND regime IS NOT NULL AND start_ts >= ? ORDER BY start_ts",
            (comp.key, since)).fetchall()
        if not rows:
            return
        by_regime: dict[str, list[tuple[int, dict]]] = defaultdict(list)
        for ts, regime, summ in rows:
            s = json.loads(summ)
            by_regime[regime].append((ts, s))
            by_regime["all"].append((ts, s))
        for regime, items in by_regime.items():
            variants = {"temp_cont": bl.CONTINUOUS} if regime == "all" else bl.VARIANTS
            for variant, cols in variants.items():
                if not any("tref" in s for _, s in items):
                    cols = tuple(c for c in cols if c != "tref")  # senza riferimento
                use = [(ts, s) for ts, s in items
                       if all(c == "1" or c.replace("^2", "") in s for c in cols)]
                if len(use) < need:
                    continue
                key = f"model:{comp.key}:{regime}:{variant}"
                raw = get_meta(self.conn, key)
                model = None
                if raw:
                    stored = json.loads(raw)
                    if stored.get("since") == since:
                        model = bl.LinearModel.from_dict(stored["model"])
                ts_arr = np.array([u[0] for u in use], dtype=np.int64)
                data = {c: np.array([u[1][c] for u in use], dtype=float)
                        for c in ("p", "tref", "fan") if all(c in u[1] for u in use)}
                y = np.array([u[1]["t"] for u in use], dtype=float)
                if model is None:
                    try:
                        model = bl.fit({k: v[:need] for k, v in data.items()}, cols, y[:need])
                    except (ValueError, np.linalg.LinAlgError):
                        continue
                    with self.conn:
                        set_meta(self.conn, key, json.dumps({"since": since,
                                                             "model": model.to_dict()}))
                res = bl.residuals(model, data, y)
                with self.conn:
                    self.conn.executemany(
                        "INSERT OR IGNORE INTO indicators(ts, indicator, regime, level, value) "
                        "VALUES (?,?,?,?,?)",
                        [(int(t), f"{variant}_{comp.suffix}", regime, "window", float(r))
                         for t, r in zip(ts_arr, res, strict=True) if np.isfinite(r)])

    # --------------------------------------------------------- 5. daily
    def step_daily(self, comps: list[Component]) -> None:
        done = get_meta(self.conn, "daily_done")
        since = (int(done) - DAY_MS) if done else 0
        since -= since % DAY_MS
        min_n = self.cfg["spc"]["min_windows_per_day"]
        groups: dict[tuple[str, str, int], list[float]] = defaultdict(list)
        for ind, regime, ts, v in self.conn.execute(
                "SELECT indicator, regime, ts, value FROM indicators WHERE level='window' "
                "AND ts >= ?", (since,)):
            groups[(ind, regime, ts - ts % DAY_MS)].append(v)
        rows = [(day, ind, regime, "daily", float(np.median(vs)), len(vs))
                for (ind, regime, day), vs in groups.items() if len(vs) >= min_n]
        # giorni con dati (esposizione) per i conteggi e il throttling
        rows += self._daily_minutes(comps, since)
        rows += self._daily_counts(since)
        # solo giorni completi: la mediana di un giorno in corso cambierebbe ancora e
        # un segnale su un valore parziale resterebbe registrato
        today = self.data_now() - self.data_now() % DAY_MS
        rows = [r for r in rows if r[0] < today]
        with self.conn:
            self.conn.execute("DELETE FROM indicators WHERE level='daily' AND ts >= ?", (since,))
            self.conn.executemany(
                "INSERT OR REPLACE INTO indicators(ts, indicator, regime, level, value, n) "
                "VALUES (?,?,?,?,?,?)", rows)
            set_meta(self.conn, "daily_done", str(today))

    def _on_days(self, since: int) -> dict[int, int]:
        """Minuti di attività per giorno (qualsiasi canale di potenza)."""
        out: dict[int, int] = defaultdict(int)
        for day, n in self.conn.execute(
                "SELECT (a.ts / 86400000) * 86400000 AS d, COUNT(DISTINCT a.ts) FROM agg_1min a "
                "JOIN channels c ON c.id=a.channel_id WHERE c.name LIKE '%power_w' AND a.ts >= ? "
                "GROUP BY d", (since,)):
            out[int(day)] = int(n)
        return out

    def _daily_minutes(self, comps: list[Component], since: int) -> list[tuple]:
        rows: list[tuple] = []
        ref_cfg = self.cfg["profile"]["reference"]
        for comp in comps:
            bounds = self._bounds(comp.key)
            chans = [comp.power, comp.throttle_thermal]
            if ref_cfg["mode"] == "channel":
                chans.append(ref_cfg["channel"])
            mf = load_minutes(self.conn, chans, since=since, grid_channel=comp.power)
            if mf.ts.size == 0:
                continue
            days = mf.ts - mf.ts % DAY_MS
            if bounds is not None:
                p = mf.get(comp.power)
                thr = np.nan_to_num(mf.max.get(comp.throttle_thermal, np.zeros(mf.ts.size)),
                                    nan=0.0) >= 0.5
                load = np.isfinite(p) & (p >= bounds.lo)
                for d in np.unique(days):
                    m = (days == d) & load
                    if m.sum() >= 30:
                        rows.append((int(d), f"throttle_frac_{comp.suffix}", "load", "daily",
                                     float(thr[m].mean()), int(m.sum())))
            if comp.key == "cpu" and ref_cfg["mode"] == "channel" and mf.has(ref_cfg["channel"]):
                r = mf.get(ref_cfg["channel"])
                for d in np.unique(days):
                    v = r[(days == d) & np.isfinite(r)]
                    if v.size >= 30:
                        rows.append((int(d), "ref_temp", "day", "daily", float(np.median(v)),
                                     int(v.size)))
        return rows

    def _daily_counts(self, since: int) -> list[tuple]:
        on = {d: n for d, n in self._on_days(since).items() if n >= 60}
        rows: list[tuple] = []
        counts: dict[tuple[str, int], int] = defaultdict(int)
        for kind, ts in self.conn.execute("SELECT kind, ts FROM events WHERE ts >= ? AND kind "
                                          "LIKE 'hw.%'", (since,)):
            for ind, kinds in COUNT_EVENT_KINDS.items():
                if kind in kinds:
                    counts[(ind, ts - ts % DAY_MS)] += 1
        present = {ind for ind, _ in counts}
        for ind, kinds in COUNT_EVENT_KINDS.items():
            for k in kinds:
                if conn_has_kind(self.conn, k):
                    present.add(ind)
        # i conteggi si registrano (anche a zero) solo se la sorgente è attiva
        eventlog_active = self.conn.execute(
            "SELECT 1 FROM channels WHERE name='status.eventlog'").fetchone() is not None
        for ind in COUNT_EVENT_KINDS:
            if ind not in present and not eventlog_active:
                continue
            for d, n in on.items():
                rows.append((d, ind, "day", "daily", float(counts.get((ind, d), 0)), n))
        # replay PCIe: contatore cumulativo -> incremento giornaliero
        for name, in self.conn.execute("SELECT name FROM channels WHERE name LIKE "
                                       "'gpu%.pcie_replay'").fetchall():
            g = name.split(".")[0]
            mf = load_minutes(self.conn, [name], since=since)
            if mf.ts.size == 0:
                continue
            days = mf.ts - mf.ts % DAY_MS
            v = mf.get(name)
            for d in np.unique(days):
                x = v[(days == d) & np.isfinite(v)]
                if x.size and int(d) in on:
                    inc = max(0.0, float(np.max(np.maximum.accumulate(x)) - x[0]))
                    rows.append((int(d), f"pcie_replay_{'gpu' if g == 'gpu0' else g}", "day",
                                 "daily", inc, int(x.size)))
        return rows

    # --------------------------------------------------------- 6. charts
    def step_charts(self, now: int) -> int:
        force_raw = get_meta(self.conn, "force_lock")
        force = set(json.loads(force_raw)) if force_raw else set()
        cb_raw = get_meta(self.conn, "chart_breaks")
        chart_breaks = json.loads(cb_raw) if cb_raw else {}
        eng = ChartEngine(self.conn, self.cfg, scoped_breaks(self.conn), config_times(self.conn),
                          now, force, chart_breaks)
        charts = self.conn.execute(
            "SELECT DISTINCT indicator, regime, level FROM indicators").fetchall()
        with self.conn:
            for ind, regime, level in charts:
                eng.update(ind, regime, level)
            if force:
                set_meta(self.conn, "force_lock", "[]")
        return eng.new_signals

    # --------------------------------------------------------------- run
    def run(self) -> dict[str, Any]:
        t0 = time.perf_counter()
        chans = self._channels()
        comps = components(chans)
        s = self.summary
        s["components"] = [c.key for c in comps]
        s["windows_new"] = sum(self.step_windows(c) for c in comps)
        for c in comps:
            if self.step_regimes(c) is None:
                s["warnings"].append(f"{c.label}: regimi non ancora calibrati "
                                     f"(servono {self.cfg['regimes']['calibration_windows']} "
                                     "finestre stazionarie)")
            self.step_window_indicators(c)
            self.step_models(c)
        self.step_daily(comps)
        now = self.data_now()
        s["signals_new"] = self.step_charts(now)
        from ..alerts.policy import evaluate_alerts

        s["alerts"] = evaluate_alerts(self.conn, self.cfg, now)
        with self.conn:
            set_meta(self.conn, "last_analysis_ts", str(int(time.time() * 1000)))
        s["duration_s"] = round(time.perf_counter() - t0, 3)
        return s


def rebuild(conn: sqlite3.Connection) -> None:
    """Cancella tutte le tabelle di analisi (non i dati): la prossima analisi le
    ricostruisce dagli aggregati a 1 minuto, con nuova calibrazione dei regimi."""
    with conn:
        for t in ("signals", "chart_state", "indicators", "windows", "diagnoses", "alerts"):
            conn.execute(f"DELETE FROM {t}")  # noqa: S608 - nomi fissi
        conn.execute("DELETE FROM meta WHERE key LIKE 'regimes:%' OR key LIKE 'model:%' "
                     "OR key LIKE 'windows_scan:%' OR key IN ('daily_done', 'force_lock', "
                     "'chart_breaks')")


def run_analysis(conn: sqlite3.Connection, cfg: dict[str, Any], low_priority: bool = True
                 ) -> dict[str, Any]:
    if low_priority:
        lower_priority()
    return Worker(conn, cfg).run()
