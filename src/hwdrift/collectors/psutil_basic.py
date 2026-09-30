# SPDX-License-Identifier: Apache-2.0
"""psutil: utilizzo CPU (multipiattaforma). I sensori termici di psutil non esistono
su Windows; su Linux li legge ``linux_hwmon``."""

from __future__ import annotations

import psutil

from ..model import Sample
from .base import Collector


class PsutilCollector(Collector):
    name = "psutil"

    def start(self) -> None:
        psutil.cpu_percent(interval=None)  # la prima lettura è sempre 0

    def poll(self, ts_ms: int, mono_s: float) -> list[Sample]:
        load = psutil.cpu_percent(interval=None)
        # se i contatori di Windows forniscono già cpu.load_pct, questo resta un
        # canale secondario (mappabile a mano nel profilo)
        ch = self.channel_map.mapping.get("psutil/cpu_percent", "cpu.load_pct") or None
        return [Sample(ts_ms, self.name, "psutil/cpu_percent", "cpu", "cpu_percent",
                       float(load), "%", ch, mono_s=mono_s)]
