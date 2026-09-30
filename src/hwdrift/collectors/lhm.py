# SPDX-License-Identifier: Apache-2.0
"""LibreHardwareMonitor: temperature, potenze, clock, carichi, ventole.

Due modalità (questione aperta della sezione 13, da decidere in M0):

* ``web``: legge ``data.json`` dal server web integrato di LHM. Il collector di
  HWDrift non ha bisogno di privilegi (li ha LHM). Solo indirizzi di loopback:
  nessuna connessione di rete verso altre macchine.
* ``dll``: carica ``LibreHardwareMonitorLib.dll`` con pythonnet. Richiede
  privilegi elevati e il driver kernel di LHM (verificare la compatibilità con
  Memory Integrity).

Il JSON è trattato come input non fidato: limite di dimensione e di profondità.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any

from ..model import Sample
from .base import Collector, CollectorUnavailable

log = logging.getLogger(__name__)

MAX_BYTES = 8 * 1024 * 1024
MAX_DEPTH = 32
_NUM = re.compile(r"^\s*(-?\d+(?:[.,]\d+)?)\s*(.*)$")

_HW_PREFIX = [
    ("/amdcpu", "cpu"), ("/intelcpu", "cpu"), ("/cpu", "cpu"),
    ("/gpu-nvidia", "gpu"), ("/gpu-amd", "gpu"), ("/gpu-intel", "gpu"), ("/gpu", "gpu"),
    ("/lpc", "superio"), ("/mainboard", "motherboard"), ("/motherboard", "motherboard"),
    ("/nvme", "storage"), ("/hdd", "storage"), ("/ssd", "storage"), ("/storage", "storage"),
]


def hw_from_id(sensor_id: str) -> str:
    for prefix, hw in _HW_PREFIX:
        if sensor_id.startswith(prefix):
            return hw
    return "other"


def parse_value(text: str) -> tuple[float | None, str]:
    """``"45,5 °C" -> (45.5, "°C")``. Restituisce ``(None, "")`` se non numerico."""
    m = _NUM.match(text or "")
    if not m:
        return None, ""
    return float(m.group(1).replace(",", ".")), m.group(2).strip()


def iter_sensors(node: dict[str, Any], depth: int = 0):
    """Visita l'albero di ``data.json`` e restituisce i nodi foglia con ``SensorId``."""
    if depth > MAX_DEPTH or not isinstance(node, dict):
        return
    if "SensorId" in node and isinstance(node.get("SensorId"), str):
        yield node
    children = node.get("Children") or []
    if isinstance(children, list):
        for ch in children:
            yield from iter_sensors(ch, depth + 1)


def check_loopback(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "http":
        raise ValueError("sources.lhm.url: solo http su loopback")
    host = parsed.hostname or ""
    if host == "localhost":
        return
    try:
        if ipaddress.ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    raise ValueError(f"sources.lhm.url deve puntare a loopback (127.0.0.1), non a {host!r}")


class LhmCollector(Collector):
    name = "lhm"
    low_level = True
    needs_admin = True

    def start(self) -> None:
        self.mode = self.options.get("mode", "web")
        if self.mode == "web":
            self.url = self.options.get("url", "http://127.0.0.1:8085/data.json")
            check_loopback(self.url)
            self.timeout = float(self.options.get("timeout_s", 2.0))
            # nessun proxy: la richiesta non deve mai lasciare la macchina
            self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            try:
                self._fetch()
            except Exception as exc:
                raise CollectorUnavailable(
                    f"server web di LibreHardwareMonitor non raggiungibile su {self.url}: {exc}. "
                    "Avviare LHM e abilitare Options > Remote Web Server."
                ) from exc
        else:
            self._open_dll()

    # ------------------------------------------------------------------ web
    def _fetch(self) -> dict[str, Any]:
        with self._opener.open(self.url, timeout=self.timeout) as resp:
            data = resp.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("risposta di LHM troppo grande")
        obj = json.loads(data.decode("utf-8", errors="replace"))
        if not isinstance(obj, dict):
            raise ValueError("formato data.json inatteso")
        return obj

    def _poll_web(self, ts_ms: int, mono_s: float) -> list[Sample]:
        out: list[Sample] = []
        for node in iter_sensors(self._fetch()):
            sid = str(node["SensorId"])[:200]
            value, unit = parse_value(str(node.get("Value", "")))
            kind = str(node.get("Type", "")) or _kind_from_id(sid)
            name = str(node.get("Text", ""))[:200]
            out.append(self._sample(ts_ms, mono_s, sid, hw_from_id(sid), kind, name, value, unit))
        return out

    # ------------------------------------------------------------------ dll
    def _open_dll(self) -> None:
        dll = self.options.get("dll_path")
        if not dll:
            raise CollectorUnavailable("sources.lhm.dll_path non impostato")
        try:
            import clr  # type: ignore[import-not-found]  # pythonnet

            clr.AddReference(str(dll))
            from LibreHardwareMonitor.Hardware import (  # type: ignore[import-not-found]
                Computer,
            )
        except Exception as exc:
            raise CollectorUnavailable(f"pythonnet/LibreHardwareMonitorLib non caricabili: {exc}"
                                       ) from exc
        comp = Computer()
        comp.IsCpuEnabled = True
        comp.IsGpuEnabled = True
        comp.IsMotherboardEnabled = True
        comp.IsStorageEnabled = True
        comp.IsControllerEnabled = True
        comp.Open()
        self._computer = comp

    def _poll_dll(self, ts_ms: int, mono_s: float) -> list[Sample]:
        out: list[Sample] = []

        def visit(hw: Any) -> None:
            hw.Update()
            hw_type = str(hw.HardwareType).lower()
            for s in hw.Sensors:
                sid = str(s.Identifier)
                val = s.Value
                kind = str(s.SensorType)
                hw = hw_type or hw_from_id(sid)
                out.append(self._sample(ts_ms, mono_s, sid, hw, kind, str(s.Name),
                                        None if val is None else float(val),
                                        _UNITS.get(kind, "")))
            for sub in hw.SubHardware:
                visit(sub)

        for hw in self._computer.Hardware:
            visit(hw)
        return out

    def poll(self, ts_ms: int, mono_s: float) -> list[Sample]:
        if self.mode == "web":
            return self._poll_web(ts_ms, mono_s)
        return self._poll_dll(ts_ms, mono_s)

    def close(self) -> None:
        comp = getattr(self, "_computer", None)
        if comp is not None:
            comp.Close()


_UNITS = {"Temperature": "°C", "Power": "W", "Clock": "MHz", "Load": "%", "Fan": "RPM",
          "Control": "%", "Voltage": "V"}


def _kind_from_id(sid: str) -> str:
    parts = sid.strip("/").split("/")
    return parts[-2].capitalize() if len(parts) >= 2 else ""
