# SPDX-License-Identifier: Apache-2.0
"""Collector Linux sperimentale (hwmon + RAPL): **fuori dal perimetro della v1**.

Esiste per dimostrare che il nucleo è indipendente dal sistema operativo
(requisito 15.2): gli stessi canali canonici arrivano da una sorgente non Windows.
Nessuna garanzia sui nomi dei sensori: la mappatura va confermata con ``discover``.
"""

from __future__ import annotations

from pathlib import Path

from ..model import Sample
from .base import Collector, CollectorUnavailable

HWMON = Path("/sys/class/hwmon")
RAPL = Path("/sys/class/powercap/intel-rapl:0/energy_uj")

_CHIP_HW = {"coretemp": "cpu", "k10temp": "cpu", "zenpower": "cpu", "amdgpu": "gpu",
            "nvme": "storage", "nct6775": "superio", "it87": "superio", "acpitz": "motherboard"}


class LinuxHwmonCollector(Collector):
    name = "linux_hwmon"

    def start(self) -> None:
        if not HWMON.is_dir():
            raise CollectorUnavailable("/sys/class/hwmon assente")
        self._last_energy: tuple[float, float] | None = None

    def poll(self, ts_ms: int, mono_s: float) -> list[Sample]:
        out: list[Sample] = []
        for chip in sorted(HWMON.iterdir()):
            try:
                cname = (chip / "name").read_text().strip()
            except OSError:
                continue
            hw = _CHIP_HW.get(cname, "other")
            for f in sorted(chip.glob("temp*_input")) + sorted(chip.glob("fan*_input")):
                try:
                    raw = float(f.read_text().strip())
                except (OSError, ValueError):
                    continue
                is_temp = f.name.startswith("temp")
                label_f = chip / f.name.replace("_input", "_label")
                try:
                    label = label_f.read_text().strip()
                except OSError:
                    label = f.name.replace("_input", "")
                if hw == "cpu" and label.lower() in ("package id 0", "tctl", "tdie"):
                    label = "CPU Package"
                value = raw / 1000.0 if is_temp else raw
                sid = f"/hwmon/{cname}/{f.name}"
                out.append(self._sample(ts_ms, mono_s, sid, hw, "temp" if is_temp else "fan",
                                        label, value, "°C" if is_temp else "RPM"))
        try:
            e = float(RAPL.read_text().strip())  # spesso leggibile solo da root
            if self._last_energy is not None and mono_s > self._last_energy[1]:
                de = e - self._last_energy[0]
                if de >= 0:
                    out.append(Sample(ts_ms, self.name, "/rapl/package", "cpu", "CPU Package",
                                      de / 1e6 / (mono_s - self._last_energy[1]), "W",
                                      "cpu.pkg.power_w", mono_s=mono_s))
            self._last_energy = (e, mono_s)
        except (OSError, ValueError):
            pass
        return out
