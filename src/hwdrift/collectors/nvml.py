# SPDX-License-Identifier: Apache-2.0
"""NVML (nvidia-ml-py): temperatura, potenza, clock, ventola, utilizzo, throttle reasons.

Sorgente opzionale: dipende dal driver proprietario NVIDIA. Il tool funziona anche
senza, con meno indicatori. Hotspot e memory junction non sono garantiti su GPU
consumer: si prendono da LHM dove disponibili.
"""

from __future__ import annotations

import logging
from typing import Any

from ..model import Sample
from ..quality.realtime_events import NVML_POWER_MASK, NVML_THERMAL_MASK
from .base import Collector, CollectorUnavailable, observation

log = logging.getLogger(__name__)


class NvmlCollector(Collector):
    name = "nvml"

    def start(self) -> None:
        try:
            import pynvml  # type: ignore[import-not-found]  # pacchetto nvidia-ml-py
        except ImportError as exc:
            raise CollectorUnavailable("nvidia-ml-py non installato") from exc
        try:
            pynvml.nvmlInit()
        except Exception as exc:
            raise CollectorUnavailable(f"NVML non disponibile (driver NVIDIA?): {exc}") from exc
        self.nv: Any = pynvml
        n = pynvml.nvmlDeviceGetCount()
        self.handles = [pynvml.nvmlDeviceGetHandleByIndex(i) for i in range(n)]
        # nomi nuovi (ClocksEvent) e vecchi (ClocksThrottle) a seconda della versione
        self._reasons_fn = (getattr(pynvml, "nvmlDeviceGetCurrentClocksEventReasons", None)
                            or getattr(pynvml, "nvmlDeviceGetCurrentClocksThrottleReasons", None))
        self._driver: str | None = None
        try:
            drv = pynvml.nvmlSystemGetDriverVersion()
            self._driver = drv.decode() if isinstance(drv, bytes) else str(drv)
        except Exception:
            self._driver = None
        if self._driver:
            # osservazione: il runner la confronta con il valore salvato e, se cambia,
            # registra un evento config.driver (confondente per le carte)
            self._events.append(observation("gpu_driver", self._driver, "config.driver"))

    def _try(self, fn: Any, *args: Any) -> Any:
        try:
            return fn(*args)
        except Exception:
            return None

    def poll(self, ts_ms: int, mono_s: float) -> list[Sample]:
        nv = self.nv
        out: list[Sample] = []
        for i, h in enumerate(self.handles):
            g = f"gpu{i}"

            def add(ch: str, value: float | None, unit: str, raw: str, g: str = g,
                    i: int = i) -> None:
                s = Sample(ts_ms, self.name, f"/nvml/{i}/{raw}", "gpu", raw, value, unit,
                           channel=self.channel_map.mapping.get(f"/nvml/{i}/{raw}", ch) or None,
                           mono_s=mono_s)
                out.append(s)

            add(f"{g}.temp_edge_c", self._try(nv.nvmlDeviceGetTemperature, h,
                                               nv.NVML_TEMPERATURE_GPU), "°C", "temperature")
            mw = self._try(nv.nvmlDeviceGetPowerUsage, h)
            add(f"{g}.power_w", None if mw is None else mw / 1000.0, "W", "power")
            add(f"{g}.clock_mhz", self._try(nv.nvmlDeviceGetClockInfo, h, nv.NVML_CLOCK_GRAPHICS),
                "MHz", "clock_graphics")
            fan = self._try(nv.nvmlDeviceGetFanSpeed, h)  # % del massimo (non rpm)
            add(f"{g}.fan_pct", None if fan is None else float(fan), "%", "fan_speed")
            util = self._try(nv.nvmlDeviceGetUtilizationRates, h)
            add(f"{g}.util_pct", None if util is None else float(util.gpu), "%", "utilization")
            if self._reasons_fn is not None:
                r = self._try(self._reasons_fn, h)
                add(f"{g}.throttle_reasons", None if r is None else float(r), "bitmask",
                    "clocks_event_reasons")
                # flag derivati: il massimo per minuto di una bitmask non è significativo,
                # quello di un flag 0/1 sì
                if r is not None:
                    add(f"{g}.throttle_thermal", 1.0 if int(r) & NVML_THERMAL_MASK else 0.0,
                        "flag", "throttle_thermal")
                    add(f"{g}.throttle_power", 1.0 if int(r) & NVML_POWER_MASK else 0.0,
                        "flag", "throttle_power")
            replay = self._try(nv.nvmlDeviceGetPcieReplayCounter, h)
            if replay is not None:
                add(f"{g}.pcie_replay", float(replay), "count", "pcie_replay")
        return out

    def close(self) -> None:
        nv = getattr(self, "nv", None)
        if nv is not None:
            try:
                nv.nvmlShutdown()
            except Exception:
                log.debug("nvmlShutdown fallito", exc_info=True)
