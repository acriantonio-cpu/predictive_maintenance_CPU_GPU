# SPDX-License-Identifier: Apache-2.0
"""Caricamento degli aggregati a 1 minuto su una griglia temporale comune."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import numpy as np


@dataclass
class MinuteFrame:
    ts: np.ndarray  # int64, ms, minuti ordinati (unione dei canali richiesti)
    median: dict[str, np.ndarray]
    min: dict[str, np.ndarray]
    max: dict[str, np.ndarray]
    valid: dict[str, np.ndarray]

    def get(self, ch: str) -> np.ndarray:
        return self.median.get(ch, np.full(self.ts.size, np.nan))

    def has(self, ch: str) -> bool:
        return ch in self.median and bool(np.isfinite(self.median[ch]).any())


def load_minutes(conn: sqlite3.Connection, channels: list[str], since: int | None = None,
                 until: int | None = None, grid_channel: str | None = None) -> MinuteFrame:
    """Carica i canali richiesti; la griglia è data da ``grid_channel`` se presente."""
    ids = {r[1]: r[0] for r in conn.execute("SELECT id, name FROM channels")}
    wanted = [c for c in channels if c in ids]
    data: dict[str, tuple[np.ndarray, ...]] = {}
    for ch in wanted:
        q = "SELECT ts, median, min, max, valid_frac FROM agg_1min WHERE channel_id=?"
        args: list[int] = [ids[ch]]
        if since is not None:
            q += " AND ts >= ?"
            args.append(since)
        if until is not None:
            q += " AND ts <= ?"
            args.append(until)
        q += " ORDER BY ts"
        rows = conn.execute(q, args).fetchall()
        if not rows:
            continue
        arr = np.array([(r[0], _f(r[1]), _f(r[2]), _f(r[3]), r[4]) for r in rows], dtype=float)
        data[ch] = (arr[:, 0].astype(np.int64), arr[:, 1], arr[:, 2], arr[:, 3], arr[:, 4])
    if grid_channel and grid_channel in data:
        grid = data[grid_channel][0]
    elif data:
        grid = np.unique(np.concatenate([d[0] for d in data.values()]))
    else:
        grid = np.empty(0, dtype=np.int64)
    med, mn, mx, val = {}, {}, {}, {}
    for ch, (ts, m, lo, hi, vf) in data.items():
        idx = np.searchsorted(ts, grid)
        idx_c = np.clip(idx, 0, ts.size - 1)
        hit = (idx < ts.size) & (ts[idx_c] == grid)
        for store, src, fill in ((med, m, np.nan), (mn, lo, np.nan), (mx, hi, np.nan),
                                 (val, vf, 0.0)):
            out = np.full(grid.size, fill)
            out[hit] = src[idx_c[hit]]
            store[ch] = out
    return MinuteFrame(grid, med, mn, mx, val)


def _f(v: float | None) -> float:
    return float("nan") if v is None else float(v)
