# SPDX-License-Identifier: Apache-2.0
"""Copertura dei regimi (failure mode 6): l'assenza di segnali non è buona salute.

Una carta esiste solo dopo 20-30 osservazioni valide in Fase I, quindi un regime
poco visitato può restare senza carta per settimane. Il tool mostra le
osservazioni valide per regime e per settimana e dichiara "copertura
insufficiente" invece di tacere.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime


def weekly_coverage(conn: sqlite3.Connection, weeks: int = 8) -> list[dict]:
    rows = conn.execute(
        "SELECT component, regime, start_ts, throttled FROM windows WHERE regime IS NOT NULL "
        "ORDER BY start_ts").fetchall()
    agg: dict[tuple[str, str, str], list[int]] = {}
    for comp, regime, ts, thr in rows:
        d = datetime.fromtimestamp(ts / 1000, UTC)
        wk = f"{d.isocalendar().year}-W{d.isocalendar().week:02d}"
        rec = agg.setdefault((comp, regime, wk), [0, 0])
        rec[0 if not thr else 1] += 1
    weeks_sorted = sorted({k[2] for k in agg})[-weeks:]
    out = []
    for (comp, regime, wk), (valid, thr) in sorted(agg.items()):
        if wk in weeks_sorted:
            out.append({"component": comp, "regime": regime, "week": wk, "valid": valid,
                        "throttled": thr})
    return out
