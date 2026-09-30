#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Spike M0: campiona LibreHardwareMonitor e NVML a 1 Hz e salva un CSV (sezione 11).

Produce, nella cartella di uscita:

* ``samples.csv``: formato lungo (ts, sorgente, id sensore, tipo hw, nome grezzo, valore,
  unità, canale proposto), TUTTI i sensori, anche non mappati;
* ``catalog.json``: catalogo dei sensori per macchina con il canale proposto;
* ``summary.json``: matrice di disponibilità dei canali canonici e dei flag di
  throttling, distribuzione del tempo per regime di potenza, overhead misurato.

Uso (PowerShell, come amministratore per i sensori LHM a basso livello):

    python scripts/m0_spike.py --hours 24 --out m0-%COMPUTERNAME%

Criterio di completamento di M0: matrice di disponibilità per macchina, prima misura
grezza di overhead e distribuzione del tempo per regime.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

import psutil

from hwdrift.collectors.base import CollectorUnavailable, build_collectors
from hwdrift.config import load_config

KEY_CHANNELS = ["cpu.pkg.temp_c", "cpu.pkg.power_w", "cpu.load_pct", "cpu.clock_eff_mhz",
                "cpu.throttle_thermal", "cpu.fan_rpm", "gpu0.temp_edge_c", "gpu0.temp_hotspot_c",
                "gpu0.temp_mem_c", "gpu0.power_w", "gpu0.fan_rpm", "gpu0.fan_pct",
                "gpu0.util_pct", "gpu0.throttle_reasons", "gpu0.throttle_thermal",
                "chassis.fan1_rpm", "mb.temp_c", "ssd0.temp_c"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--out", type=Path, default=Path("m0-spike"))
    ap.add_argument("--config", type=Path, default=None)
    args = ap.parse_args()
    cfg = load_config(args.config)
    args.out.mkdir(parents=True, exist_ok=True)
    collectors = []
    for c in build_collectors(cfg):
        try:
            c.start()
            collectors.append(c)
            print(f"[ok] {c.name}")
        except CollectorUnavailable as exc:
            print(f"[--] {c.name}: {exc}")
    proc = psutil.Process()
    proc.cpu_percent(None)
    catalog: dict[str, dict] = {}
    seen = Counter()
    power = defaultdict(list)
    events = Counter()
    cpu_samples, rss_peak = [], 0.0
    end = time.monotonic() + args.hours * 3600
    next_t = time.monotonic()
    with (args.out / "samples.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["ts_ms", "source", "sensor_id", "hw_type", "raw_name", "value", "unit",
                    "channel"])
        try:
            while time.monotonic() < end:
                ts, mono = int(time.time() * 1000), time.monotonic()
                for c in collectors:
                    if c.interval_s and getattr(c, "_next", 0) > mono:
                        continue
                    c._next = mono + c.interval_s  # type: ignore[attr-defined]
                    try:
                        samples = c.poll(ts, mono)
                    except Exception as exc:  # noqa: BLE001
                        print(f"errore {c.name}: {exc}")
                        continue
                    for s in samples:
                        w.writerow([s.ts_ms, s.source, s.sensor_id, s.hw_type, s.raw_name,
                                    s.value, s.unit, s.channel or ""])
                        catalog.setdefault(f"{s.source}:{s.sensor_id}", {
                            "source": s.source, "hw_type": s.hw_type, "raw_name": s.raw_name,
                            "unit": s.unit, "proposed_channel": s.channel})
                        if s.channel and s.value is not None:
                            seen[s.channel] += 1
                            if s.channel.endswith("power_w"):
                                power[s.channel].append(s.value)
                    for ev in c.drain_events():
                        events[ev.kind] += 1
                cpu_samples.append(proc.cpu_percent(None))
                rss_peak = max(rss_peak, proc.memory_info().rss / 1e6)
                next_t += args.interval
                time.sleep(max(0.0, next_t - time.monotonic()))
        except KeyboardInterrupt:
            print("interrotto: salvo i risultati parziali")
    regimes = {}
    for ch, vals in power.items():
        vals.sort()
        pmax = vals[int(0.99 * (len(vals) - 1))] if vals else 0
        lo, hi = 0.30 * pmax, 0.65 * pmax
        n = len(vals) or 1
        regimes[ch] = {"pmax_p99": pmax, "idle": sum(v < lo for v in vals) / n,
                       "medium": sum(lo <= v < hi for v in vals) / n,
                       "high": sum(v >= hi for v in vals) / n}
    summary = {
        "machine": psutil.os.environ.get("COMPUTERNAME", ""),
        "hours": args.hours, "collectors": [c.name for c in collectors],
        "availability": {ch: seen.get(ch, 0) > 0 for ch in KEY_CHANNELS},
        "throttle_flags": {ch: seen.get(ch, 0) > 0 for ch in KEY_CHANNELS if "throttle" in ch},
        "regime_time_fraction": regimes, "events": dict(events),
        "overhead": {"cpu_pct_mean": sum(cpu_samples) / max(len(cpu_samples), 1),
                     "cpu_pct_max": max(cpu_samples, default=0), "rss_mb_peak": rss_peak},
    }
    (args.out / "catalog.json").write_text(json.dumps(catalog, indent=1, ensure_ascii=False),
                                           encoding="utf-8")
    (args.out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    for c in collectors:
        c.close()
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
