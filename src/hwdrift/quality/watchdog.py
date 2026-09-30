# SPDX-License-Identifier: Apache-2.0
"""Watchdog: il collector fermo non deve sembrare "nessun problema" (failure mode 7).

Il collector aggiorna ``meta.heartbeat_ts`` a ogni flush e scrive un canale di
stato ``status.<collector>`` (1 = ok, 0 = errore). Chi legge (notificatore,
report, worker) usa queste funzioni per dichiarare esplicitamente i dati mancanti.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ..model import now_ms
from ..storage.schema import get_meta


@dataclass
class Health:
    heartbeat_ts: int | None
    last_sample_ts: int | None
    stale_min: float | None
    failing_collectors: list[str]

    @property
    def is_stale(self) -> bool:
        return self.stale_min is None or self.stale_min > 0


def check(conn: sqlite3.Connection, stale_after_min: float = 5.0,
          now: int | None = None) -> Health:
    now = now if now is not None else now_ms()
    hb_raw = get_meta(conn, "heartbeat_ts")
    hb = int(hb_raw) if hb_raw else None
    row = conn.execute("SELECT MAX(ts) FROM agg_1min").fetchone()
    last = row[0] if row and row[0] is not None else None
    stale: float | None
    if hb is None:
        stale = None
    else:
        age_min = (now - hb) / 60_000
        stale = age_min if age_min > stale_after_min else 0.0
    failing: list[str] = []
    # stato più recente di ciascun canale status.* negli ultimi 10 minuti
    rows = conn.execute(
        """SELECT c.name, a.median FROM agg_1min a JOIN channels c ON c.id = a.channel_id
           WHERE c.name LIKE 'status.%' AND a.ts = (
               SELECT MAX(ts) FROM agg_1min WHERE channel_id = a.channel_id)
             AND a.ts >= ?""",
        (now - 600_000,),
    ).fetchall()
    for name, med in rows:
        if med is not None and med < 0.5:
            failing.append(name.removeprefix("status."))
    return Health(hb, last, stale, sorted(failing))
