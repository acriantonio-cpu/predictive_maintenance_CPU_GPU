# SPDX-License-Identifier: Apache-2.0
"""Interfaccia comune dei collector.

Ogni collector implementa ``start()``, ``poll() -> list[Sample]`` e ``close()``.
I collector non conoscono indicatori né carte: producono solo ``Sample`` (ed
eventualmente ``EventRecord`` tramite ``drain_events``). Un collector che
fallisce non ferma gli altri: il runner registra l'errore come canale di stato.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from ..channels import ChannelMap
from ..model import EventRecord, Sample

log = logging.getLogger(__name__)


class CollectorUnavailable(RuntimeError):
    """La sorgente non è disponibile su questa macchina (libreria o driver assente)."""


class Collector(ABC):
    #: nome breve, usato anche per il canale ``status.<name>``
    name: str = "base"
    #: se True la sorgente accede all'hardware a basso livello (SuperIO, EC, SMBus):
    #: viene sospesa in modalità game-safe
    low_level: bool = False
    #: se True servono privilegi elevati per la maggior parte dei sensori
    needs_admin: bool = False
    #: intervallo minimo tra due poll (0 = a ogni ciclo del runner)
    interval_s: float = 0.0

    def __init__(self, options: dict[str, Any] | None = None,
                 channel_map: ChannelMap | None = None) -> None:
        self.options = options or {}
        self.channel_map = channel_map or ChannelMap({}, auto=True)
        self._events: list[EventRecord] = []

    def start(self) -> None:  # noqa: B027 - hook opzionale
        """Apre la sorgente. Solleva ``CollectorUnavailable`` se non utilizzabile."""

    @abstractmethod
    def poll(self, ts_ms: int, mono_s: float) -> list[Sample]:
        """Legge i sensori una volta."""

    def drain_events(self) -> list[EventRecord]:
        out, self._events = self._events, []
        return out

    def close(self) -> None:  # noqa: B027 - hook opzionale
        pass

    # helper per le sottoclassi
    def _sample(self, ts_ms: int, mono_s: float, sensor_id: str, hw_type: str, kind: str,
                raw_name: str, value: float | None, unit: str,
                hw_index: int | None = None) -> Sample:
        ch = self.channel_map.resolve(sensor_id, hw_type, kind, raw_name, hw_index)
        return Sample(ts_ms=ts_ms, source=self.name, sensor_id=sensor_id, hw_type=hw_type,
                      raw_name=raw_name, value=value, unit=unit, channel=ch, mono_s=mono_s)


def observation(key: str, value: str, config_kind: str) -> EventRecord:
    """Valore di configurazione osservato (driver, BIOS...).

    Non è un evento: il runner lo confronta con l'ultimo valore salvato e registra
    ``config_kind`` solo se è cambiato.
    """
    from ..model import now_ms

    return EventRecord(now_ms(), "observe", detail={"key": key, "value": value,
                                                    "config_kind": config_kind})


def build_collectors(cfg: dict[str, Any]) -> list[Collector]:
    """Istanzia i collector abilitati. Gli import sono pigri: una sorgente assente
    (pythonnet, pynvml, pywin32) non impedisce l'avvio delle altre."""
    from ..channels import ChannelMap

    prof = cfg["profile"]
    cmap = ChannelMap(dict(prof["mapping"]), auto=prof["auto_mapping"])
    src = cfg["sources"]
    out: list[Collector] = []
    if src["simulator"]["enabled"]:
        from .simulator import SimulatorCollector

        out.append(SimulatorCollector(src["simulator"], cmap))
        return out  # il simulatore esclude l'hardware reale
    factories: list[tuple[str, str, str]] = [
        ("lhm", ".lhm", "LhmCollector"),
        ("nvml", ".nvml", "NvmlCollector"),
        ("eventlog", ".eventlog", "EventLogCollector"),
        ("perfcounters", ".perfcounters", "PerfCounterCollector"),
        ("psutil", ".psutil_basic", "PsutilCollector"),
        ("sysinfo", ".wmi_info", "SysInfoCollector"),
        ("smart", ".smart", "SmartCollector"),
        ("linux_hwmon", ".linux_hwmon", "LinuxHwmonCollector"),
    ]
    import importlib

    for key, mod, cls in factories:
        if not src[key]["enabled"]:
            continue
        module = importlib.import_module(mod, __package__)
        out.append(getattr(module, cls)(src[key], cmap))
    return out
