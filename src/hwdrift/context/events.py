# SPDX-License-Identifier: Apache-2.0
"""Registro eventi: manutenzioni dichiarate, cambi di configurazione, gap.

Il registro è la fonte delle etichette per la validazione e il riferimento per
il ricalcolo del baseline (sezione 5).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from ..model import EVENT_KINDS, USER_EVENT_KINDS, now_ms

MAX_NOTE = 500


@dataclass(frozen=True)
class Event:
    id: int
    ts: int
    kind: str
    source: str
    detail: dict[str, Any]
    note: str


def add_user_event(conn: sqlite3.Connection, kind: str, ts: int | None = None, note: str = "",
                   detail: dict[str, Any] | None = None) -> int:
    if kind not in USER_EVENT_KINDS and kind != "system.baseline_start":
        valid = ", ".join(USER_EVENT_KINDS)
        raise ValueError(f"tipo di evento non valido: {kind}. Validi: {valid}")
    ts = ts if ts is not None else now_ms()
    with conn:
        cur = conn.execute(
            "INSERT INTO events(ts, kind, source, detail, note) VALUES (?, ?, 'user', ?, ?)",
            (ts, kind, json.dumps(detail or {}), note[:MAX_NOTE]),
        )
    return int(cur.lastrowid or 0)


def list_events(conn: sqlite3.Connection, since: int | None = None, until: int | None = None,
                prefix: str | None = None) -> list[Event]:
    q = "SELECT id, ts, kind, source, detail, note FROM events WHERE 1=1"
    args: list[Any] = []
    if since is not None:
        q += " AND ts >= ?"
        args.append(since)
    if until is not None:
        q += " AND ts <= ?"
        args.append(until)
    if prefix:
        q += " AND kind LIKE ?"
        args.append(prefix.replace("%", "") + "%")
    q += " ORDER BY ts"
    out = []
    for r in conn.execute(q, args):
        try:
            detail = json.loads(r[4])
        except (TypeError, ValueError):
            detail = {}
        out.append(Event(r[0], r[1], r[2], r[3], detail if isinstance(detail, dict) else {}, r[5]))
    return out


def describe(kind: str) -> str:
    return EVENT_KINDS.get(kind, kind)


def confounder_times(conn: sqlite3.Connection) -> list[int]:
    """Istanti che invalidano le finestre: configurazione, gap, riavvii."""
    rows = conn.execute(
        "SELECT ts FROM events WHERE kind LIKE 'config.%' OR kind IN "
        "('system.gap', 'system.reboot', 'system.collector_start')"
    ).fetchall()
    return sorted(int(r[0]) for r in rows)


def config_times(conn: sqlite3.Connection) -> list[int]:
    return sorted(int(r[0]) for r in conn.execute(
        "SELECT ts FROM events WHERE kind LIKE 'config.%'"))


def segment_breaks(conn: sqlite3.Connection) -> list[int]:
    """Istanti che chiudono i segmenti di *tutte* le carte: manutenzioni e nuova Fase I."""
    return sorted(int(r[0]) for r in conn.execute(
        "SELECT ts FROM events WHERE kind LIKE 'maintenance.%' OR kind = 'system.baseline_start'"))


def scoped_breaks(conn: sqlite3.Connection) -> list[tuple[int, str | None]]:
    """Chiusure di segmento con ambito: ``(ts, suffisso componente | None = tutte)``.

    Oltre a manutenzioni e ``baseline start``, anche i cambi di configurazione
    (driver, BIOS, profilo) riaprono la Fase I con limiti provvisori (failure
    mode 4): un gradino dovuto al driver non deve diventare un allarme di
    manutenzione. Un evento con ``detail.component`` (es. ``gpu0``) tocca solo le
    carte di quel componente.
    """
    out: list[tuple[int, str | None]] = []
    for ts, detail in conn.execute(
            "SELECT ts, detail FROM events WHERE kind LIKE 'maintenance.%' "
            "OR kind LIKE 'config.%' OR kind = 'system.baseline_start'"):
        scope = None
        try:
            d = json.loads(detail or "{}")
            comp = d.get("component") if isinstance(d, dict) else None
        except ValueError:
            comp = None
        if isinstance(comp, str) and comp:
            scope = "gpu" if comp == "gpu0" else comp
        out.append((int(ts), scope))
    return sorted(out, key=lambda x: x[0])
