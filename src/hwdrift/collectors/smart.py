# SPDX-License-Identifier: Apache-2.0
"""smartmontools: temperatura e usura di SSD/HDD tramite ``smartctl --json``.

Eseguibile esterno (non linkato: vedi le note di licenza, sezione 13). Richiede
privilegi elevati. I dispositivi si elencano esplicitamente in configurazione e
sono validati: nessuna stringa arbitraria passa al processo.
"""

from __future__ import annotations

import json
import re
import subprocess

from ..model import Sample
from .base import Collector, CollectorUnavailable

_DEV = re.compile(r"^(/dev/[A-Za-z0-9/_-]+|[A-Za-z]:|/dev/pd\d+|\\\\\.\\PhysicalDrive\d+)$")


class SmartCollector(Collector):
    name = "smart"
    low_level = True
    needs_admin = True

    def start(self) -> None:
        self.interval_s = float(self.options.get("interval_s", 300.0))
        self.exe = str(self.options.get("smartctl", "smartctl"))
        self.devices = [str(d) for d in self.options.get("devices", [])]
        for d in self.devices:
            if not _DEV.match(d):
                raise ValueError(f"dispositivo SMART non valido: {d!r}")
        if not self.devices:
            raise CollectorUnavailable("sources.smart.devices è vuoto")

    def poll(self, ts_ms: int, mono_s: float) -> list[Sample]:
        out = []
        for i, dev in enumerate(self.devices):
            try:
                res = subprocess.run([self.exe, "--json", "-A", "-H", dev],
                                     capture_output=True, text=True, timeout=30, check=False)
            except FileNotFoundError as exc:
                raise CollectorUnavailable("smartctl non trovato") from exc
            try:
                data = json.loads(res.stdout[:2_000_000] or "{}")
            except json.JSONDecodeError:
                continue
            temp = (data.get("temperature") or {}).get("current")
            out.append(Sample(ts_ms, self.name, f"smart/{i}/temperature", "storage",
                              f"{dev} temperature", None if temp is None else float(temp), "°C",
                              f"ssd{i}.temp_c", mono_s=mono_s))
        return out
