# SPDX-License-Identifier: Apache-2.0
"""Politica di allarme (sezione 7) e generazione delle ipotesi (sezione 8).

* **Info**: una sola regola su un solo indicatore.
* **Attenzione**: segnale che persiste su almeno 2 giorni consecutivi.
* **Azione**: segnale su almeno 2 carte correlate a livello attenzione, combinate
  da una regola di diagnosi.

Inoltre: indicatori primari e secondari (i secondari non superano "info"),
segnali vicini a eventi di configurazione etichettati "configurazione",
budget di allarmi per macchina al mese, errori WHEA fatali sempre allarme,
rilevamento semi-automatico degli eventi di pulizia.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime
from itertools import pairwise
from typing import Any

from ..context.events import describe
from ..diagnosis.engine import LEVELS, Evidence, IndicatorState, diagnose, level_ge, load_rules
from ..i18n import tr
from ..indicators.definitions import CONTEXT_INDICATORS, SECONDARY_BASES, caption, split
from ..storage.schema import set_meta

DAY_MS = 86_400_000
PRIMARY_RULES = {"R1", "R2", "R3", "R4", "MR", "C"}


def _fmt_ts(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, UTC).strftime("%Y-%m-%d %H:%M UTC")


def chart_levels(conn: sqlite3.Connection, cfg: dict[str, Any], now: int
                 ) -> tuple[dict[tuple[str, str], str], dict[str, dict]]:
    """Livello per (carta, lato) nel periodo di osservazione, sul segmento corrente."""
    since = now - int(cfg["alerts"]["lookback_days"] * DAY_MS)
    primary = set(cfg["alerts"]["primary"])
    states: dict[str, dict] = {}
    for cid, seg, phase, params in conn.execute(
            "SELECT chart_id, segment, phase, params FROM chart_state WHERE closed_ts IS NULL"):
        states[cid] = {"segment": seg, "phase": phase, "params": json.loads(params or "{}")}
    days: dict[tuple[str, str], set[int]] = defaultdict(set)
    any_sig: dict[tuple[str, str], bool] = defaultdict(bool)
    for cid, seg, ts, rule, side in conn.execute(
            "SELECT chart_id, segment, ts, rule, side FROM signals WHERE ts >= ? "
            "AND label='maintenance'", (since,)):
        st = states.get(cid)
        if st is None or st["segment"] != seg:
            continue
        any_sig[(cid, side)] = True
        if rule in PRIMARY_RULES:
            days[(cid, side)].add(ts // DAY_MS)
    out: dict[tuple[str, str], str] = {}
    for key in any_sig:
        cid, side = key
        ind = cid.split("|")[0]
        d = sorted(days.get(key, ()))
        persistent = any(b - a == 1 for a, b in pairwise(d))
        lvl = "attention" if persistent else "info"
        secondary = ind not in primary or split(ind)[0] in SECONDARY_BASES
        if secondary and ind not in CONTEXT_INDICATORS:
            lvl = "info"
        out[key] = lvl
    return out, states


def build_evidence(conn: sqlite3.Connection, cfg: dict[str, Any], now: int) -> Evidence:
    levels, states = chart_levels(conn, cfg, now)
    inds: dict[str, IndicatorState] = {}
    for cid, st in states.items():
        ind = cid.split("|")[0]
        s = inds.setdefault(ind, IndicatorState())
        if st["phase"] == "II" and not st["params"].get("degenerate"):
            s.locked = True
    for (cid, side), lvl in levels.items():
        ind = cid.split("|")[0]
        s = inds.setdefault(ind, IndicatorState())
        if level_ge(lvl, getattr(s, side)):
            setattr(s, side, lvl)
        (s.charts_upper if side == "upper" else s.charts_lower)[cid] = lvl
    lookback = now - int(cfg["alerts"]["lookback_days"] * DAY_MS)

    def hours_since(prefix: str) -> float | None:
        row = conn.execute("SELECT MAX(ts) FROM events WHERE kind LIKE ? AND ts >= ? AND ts <= ?",
                           (prefix + "%", lookback, now)).fetchone()
        return (now - row[0]) / 3_600_000 if row and row[0] is not None else None

    return Evidence(inds, hours_since("config."), hours_since("maintenance."),
                    list(cfg["alerts"]["primary"]))


def _upsert(conn: sqlite3.Connection, seen: set[str], key: str, level: str, title: str,
            message: str, now: int) -> None:
    seen.add(key)
    row = conn.execute("SELECT id FROM alerts WHERE key=?", (key,)).fetchone()
    if row:
        conn.execute("UPDATE alerts SET last_ts=?, level=?, title=?, message=?, active=1 "
                     "WHERE id=?", (now, level, title, message, row[0]))
    else:
        conn.execute("INSERT INTO alerts(key, first_ts, last_ts, level, title, message, active) "
                     "VALUES (?,?,?,?,?,?,1)", (key, now, now, level, title, message))


def evaluate_alerts(conn: sqlite3.Connection, cfg: dict[str, Any], now: int) -> dict[str, int]:
    acfg = cfg["alerts"]
    levels, _ = chart_levels(conn, cfg, now)
    ev = build_evidence(conn, cfg, now)
    rules = load_rules()
    diags = diagnose(rules, ev)
    seen: set[str] = set()
    lookback = now - int(acfg["lookback_days"] * DAY_MS)
    with conn:
        # ---- diagnosi (ipotesi)
        current = {d.rule_id for d in diags}
        for (rid,) in conn.execute("SELECT rule_id FROM diagnoses WHERE active=1").fetchall():
            if rid not in current and not rid.startswith("manual."):  # manuali: li chiude l'utente
                conn.execute("UPDATE diagnoses SET active=0 WHERE active=1 AND rule_id=?", (rid,))
        for d in diags:
            vals = (now, d.title, d.confidence, json.dumps(d.supports),
                    json.dumps(d.contradicts), json.dumps(d.actions), json.dumps(d.charts))
            row = conn.execute("SELECT id FROM diagnoses WHERE active=1 AND rule_id=?",
                               (d.rule_id,)).fetchone()
            if row:
                conn.execute("UPDATE diagnoses SET ts=?, title=?, confidence=?, supports=?, "
                             "contradicts=?, actions=?, charts=? WHERE id=?", (*vals, row[0]))
            else:
                conn.execute("INSERT INTO diagnoses(ts, title, confidence, supports, contradicts,"
                             " actions, charts, rule_id, active) VALUES (?,?,?,?,?,?,?,?,1)",
                             (*vals, d.rule_id))
            msg = tr("Ipotesi: {title} (confidenza {conf}). Verifica suggerita: {action}").format(
                title=d.title, conf=tr(d.confidence), action=d.actions[0] if d.actions else "-")
            _upsert(conn, seen, f"diag:{d.rule_id}", d.level, d.title, msg, now)
        # ---- carte singole (info / attenzione)
        for (cid, side), lvl in levels.items():
            ind, regime, _level = cid.split("|")
            base = split(ind)[0]
            # ventola in calo: rilevante solo sotto carico (a riposo sta al minimo)
            relevant = side == "upper" or (base == "fan_effort" and side == "lower"
                                           and regime in ("medium", "high"))
            if not relevant or ind in CONTEXT_INDICATORS:
                continue
            text = tr("{ind} in salita ({regime})" if side == "upper"
                      else "{ind} in calo ({regime})").format(ind=ind, regime=regime)
            _upsert(conn, seen, f"chart:{cid}:{side}", lvl, text, caption(ind, regime), now)
        # ---- rilevamento semi-automatico della pulizia
        if ev.maintenance_event_hours is None:
            for (cid, side), lvl in levels.items():
                base = split(cid.split("|")[0])[0]
                if side == "lower" and lvl == "attention" and base in ("rth", "idle_temp"):
                    _upsert(conn, seen, f"cleaning:{cid.split('|')[0]}", "info",
                            tr("Hai fatto manutenzione?"),
                            tr("{ind} è sceso in modo brusco e persistente senza un evento "
                               "registrato. Se hai pulito o cambiato la pasta, registralo con "
                               "'hwdrift event add maintenance.clean --at <data>'"
                               ).format(ind=cid.split("|")[0]), now)
        # ---- cambi di configurazione: conferma richiesta
        for eid, ts, kind, detail in conn.execute(
                "SELECT id, ts, kind, detail FROM events WHERE kind LIKE 'config.%' AND ts >= ?",
                (lookback,)).fetchall():
            _upsert(conn, seen, f"config:{eid}", "info",
                    tr("Configurazione: {kind}").format(kind=describe(kind)),
                    tr("Evento del {when} {detail}. Le carte coinvolte ripartono con una nuova "
                       "Fase I (limiti provvisori): nessun allarme di manutenzione. Confermare "
                       "che il cambio sia voluto.").format(when=_fmt_ts(ts), detail=detail), now)
        # ---- errori fatali: sempre allarme
        for eid, ts in conn.execute(
                "SELECT id, ts FROM events WHERE kind = 'hw.whea_fatal' AND ts >= ?",
                (lookback,)).fetchall():
            _upsert(conn, seen, f"fatal:{eid}", "action", tr("Errore hardware fatale (WHEA)"),
                    tr("Errore non corretto registrato il {when}: intervenire subito "
                       "(diagnostica di memoria, CPU, PCIe).").format(when=_fmt_ts(ts)), now)
        # ---- budget di allarmi
        month = now - 30 * DAY_MS
        n_action = conn.execute("SELECT COUNT(*) FROM alerts WHERE level='action' AND "
                                "first_ts >= ?", (month,)).fetchone()[0]
        exceeded = n_action > acfg["action_budget_per_month"]
        set_meta(conn, "alert_budget_exceeded", "1" if exceeded else "0")
        if exceeded:
            _upsert(conn, seen, "budget", "info", tr("Troppi allarmi"),
                    tr("{n} allarmi di livello azione negli ultimi 30 giorni (budget {budget}): "
                       "rivedere soglie e regole invece di continuare a notificare.").format(
                        n=n_action, budget=acfg["action_budget_per_month"]), now)
        for (key,) in conn.execute("SELECT key FROM alerts WHERE active=1").fetchall():
            if key not in seen:
                conn.execute("UPDATE alerts SET active=0 WHERE key=?", (key,))
    counts = {lvl: 0 for lvl in LEVELS[1:]}
    for (lvl,) in conn.execute("SELECT level FROM alerts WHERE active=1"):
        counts[lvl] = counts.get(lvl, 0) + 1
    return counts
