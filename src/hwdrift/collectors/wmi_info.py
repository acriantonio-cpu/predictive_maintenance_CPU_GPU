# SPDX-License-Identifier: Apache-2.0
"""Informazioni di configurazione (driver GPU, BIOS, modello) come *eventi*.

Non è un sensore: le versioni di driver e BIOS sono confondenti per le carte di
controllo (failure mode 4) e vanno registrate quando cambiano. Su Windows si usa
PowerShell ``Get-CimInstance`` (argomenti fissi, nessun input dell'utente); su
Linux ``/sys/class/dmi/id``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from ..model import Sample
from .base import Collector, observation

_PS = ("Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion | "
       "ConvertTo-Json -Compress; '---'; Get-CimInstance Win32_BIOS | "
       "Select-Object SMBIOSBIOSVersion | ConvertTo-Json -Compress")


def _as_list(obj: object) -> list[dict]:
    if isinstance(obj, list):
        return [o for o in obj if isinstance(o, dict)]
    return [obj] if isinstance(obj, dict) else []


class SysInfoCollector(Collector):
    name = "sysinfo"

    def start(self) -> None:
        self.interval_s = float(self.options.get("interval_s", 900.0))

    def poll(self, ts_ms: int, mono_s: float) -> list[Sample]:
        if sys.platform == "win32":
            self._windows()
        else:
            self._linux()
        return []

    def _windows(self) -> None:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if res.returncode != 0:
            raise RuntimeError(f"powershell: {res.stderr.strip()[:200]}")
        parts = res.stdout.split("---")
        gpus = _as_list(json.loads(parts[0])) if parts[0].strip() else []
        for i, g in enumerate(gpus):
            ver = str(g.get("DriverVersion", ""))[:64]
            if ver:
                self._events.append(observation(f"gpu{i}_driver_wmi", ver, "config.driver"))
        if len(parts) > 1 and parts[1].strip():
            bios = _as_list(json.loads(parts[1]))
            if bios:
                ver = str(bios[0].get("SMBIOSBIOSVersion", ""))[:64]
                if ver:
                    self._events.append(observation("bios", ver, "config.bios"))

    def _linux(self) -> None:
        p = Path("/sys/class/dmi/id/bios_version")
        try:
            ver = p.read_text(encoding="utf-8").strip()[:64]
        except OSError:
            return
        if ver:
            self._events.append(observation("bios", ver, "config.bios"))
