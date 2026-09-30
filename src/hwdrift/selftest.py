# SPDX-License-Identifier: Apache-2.0
"""Selftest (``hwdrift selftest``): stato dei collector e misura dell'overhead.

Esegue il ciclo di raccolta reale per N secondi su un database temporaneo e misura
CPU (% di un core) e memoria residente del processo, confrontandole con il budget
della sezione 2. Verifica anche che il collector non abbia importato librerie
scientifiche. Esce con codice non zero se il budget è superato (test di release).
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import psutil

HEAVY = ("numpy", "pandas", "scipy", "matplotlib", "plotly")


def run_selftest(cfg: dict[str, Any], seconds: float = 30.0) -> dict[str, Any]:
    from .runner import Runner
    from .storage.schema import open_db

    proc = psutil.Process()
    with tempfile.TemporaryDirectory() as td:
        conn = open_db(Path(td) / "selftest.sqlite")
        runner = Runner(cfg, conn)
        runner._startup_events()
        cpu0 = proc.cpu_times()
        t0 = time.monotonic()
        peak_rss = proc.memory_info().rss
        next_t = t0
        while time.monotonic() - t0 < seconds:
            runner.tick()
            peak_rss = max(peak_rss, proc.memory_info().rss)
            next_t += runner.interval
            time.sleep(max(0.0, next_t - time.monotonic()))
        wall = time.monotonic() - t0
        cpu1 = proc.cpu_times()
        runner.shutdown()
        rows = conn.execute("SELECT COUNT(*) FROM raw_samples").fetchone()[0]
        conn.close()
    cpu_pct = 100.0 * ((cpu1.user - cpu0.user) + (cpu1.system - cpu0.system)) / wall
    rss_mb = peak_rss / 1e6
    smp = cfg["sampling"]
    heavy = [m for m in HEAVY if m in sys.modules]
    return {
        "seconds": round(wall, 1), "ticks": runner.ticks, "rows": rows,
        "cpu_pct_one_core": round(cpu_pct, 3), "rss_mb_peak": round(rss_mb, 1),
        "cpu_budget_pct": smp["cpu_budget_pct"], "rss_budget_mb": smp["rss_budget_mb"],
        "within_budget": cpu_pct <= smp["cpu_budget_pct"] and rss_mb <= smp["rss_budget_mb"],
        "heavy_modules_loaded": heavy, "collectors": runner.status(),
        "interval_s": runner.interval,
    }
