# SPDX-License-Identifier: Apache-2.0
"""Registro eventi di Windows: WHEA, TDR del driver video, Kernel-Power, BugCheck.

Si usa ``wevtutil`` (incluso in Windows) come processo esterno con argomenti fissi,
senza shell: nessuna dipendenza da pywin32 per questa sorgente. L'XML restituito è
trattato come input non fidato (limite di dimensione, parser senza entità esterne).

TODO(M0): compilare il catalogo completo degli ID rilevanti e verificare se la
lettura del canale System richiede elevazione sulle macchine di prova. Gli ID qui
sotto sono quelli documentati più comunemente e vanno confermati.
"""

from __future__ import annotations

import subprocess
import sys
import xml.etree.ElementTree as ET
from typing import Any

from ..model import EventRecord, Sample
from .base import Collector, CollectorUnavailable

MAX_XML = 4 * 1024 * 1024
NS = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}

# (provider, event id) -> tipo di evento HWDrift
EVENT_MAP: dict[tuple[str, int], str] = {
    ("Microsoft-Windows-WHEA-Logger", 17): "hw.whea_corrected",  # PCIe corretto
    ("Microsoft-Windows-WHEA-Logger", 19): "hw.whea_corrected",  # machine check corretto
    ("Microsoft-Windows-WHEA-Logger", 47): "hw.whea_corrected",  # memoria corretto
    ("Microsoft-Windows-WHEA-Logger", 18): "hw.whea_fatal",  # errore fatale
    ("Microsoft-Windows-WHEA-Logger", 1): "hw.whea_fatal",
    ("Display", 4101): "hw.tdr",
    ("Microsoft-Windows-Kernel-Power", 41): "hw.kernel_power",
    ("Microsoft-Windows-WER-SystemErrorReporting", 1001): "hw.bugcheck",
    ("BugCheck", 1001): "hw.bugcheck",
}

_QUERY = ("*[System[(Provider[@Name='Microsoft-Windows-WHEA-Logger'] or "
          "Provider[@Name='Display'] or Provider[@Name='Microsoft-Windows-Kernel-Power'] or "
          "Provider[@Name='BugCheck'] or "
          "Provider[@Name='Microsoft-Windows-WER-SystemErrorReporting'])]]")


def parse_events(xml_text: str) -> list[dict[str, Any]]:
    """Estrae provider, id, record id e timestamp da un output ``wevtutil /f:xml``."""
    if len(xml_text) > MAX_XML:
        xml_text = xml_text[:MAX_XML]
    if "<!DOCTYPE" in xml_text or "<!ENTITY" in xml_text:
        raise ValueError("XML con DTD/entità rifiutato")
    root = ET.fromstring(f"<Events>{xml_text}</Events>")  # noqa: S314
    out = []
    for ev in root.findall("e:Event", NS):
        sysn = ev.find("e:System", NS)
        if sysn is None:
            continue
        prov = sysn.find("e:Provider", NS)
        eid = sysn.find("e:EventID", NS)
        rec = sysn.find("e:EventRecordID", NS)
        tc = sysn.find("e:TimeCreated", NS)
        if prov is None or eid is None or eid.text is None:
            continue
        try:
            event_id = int(eid.text.strip())
        except ValueError:
            continue
        out.append({
            "provider": prov.get("Name", ""),
            "event_id": event_id,
            "record_id": rec.text.strip() if rec is not None and rec.text else None,
            "time": tc.get("SystemTime") if tc is not None else None,
        })
    return out


def _iso_to_ms(s: str | None, fallback: int) -> int:
    if not s:
        return fallback
    from datetime import datetime

    try:
        s2 = s.replace("Z", "+00:00")
        if "." in s2:  # Windows usa 7 cifre decimali: Python ne accetta al massimo 6
            head, tail = s2.split(".", 1)
            frac = "".join(ch for ch in tail if ch.isdigit())[:6]
            tz = tail[len("".join(ch for ch in tail if ch.isdigit())):]
            s2 = f"{head}.{frac}{tz}"
        return int(datetime.fromisoformat(s2).timestamp() * 1000)
    except ValueError:
        return fallback


class EventLogCollector(Collector):
    name = "eventlog"
    max_events: int = 200

    def start(self) -> None:
        if sys.platform != "win32":
            raise CollectorUnavailable("il registro eventi di Windows esiste solo su Windows")
        self.interval_s = float(self.options.get("interval_s", 60.0))
        self.max_events = int(self.options.get("max_events", 200))

    def poll(self, ts_ms: int, mono_s: float) -> list[Sample]:
        res = subprocess.run(
            ["wevtutil", "qe", "System", f"/q:{_QUERY}", "/f:xml", "/rd:true",
             f"/c:{self.max_events}"],
            capture_output=True, text=True, timeout=15, check=False,
        )
        if res.returncode != 0:
            raise RuntimeError(f"wevtutil: {res.stderr.strip()[:200]}")
        for ev in parse_events(res.stdout):
            kind = EVENT_MAP.get((ev["provider"], ev["event_id"]))
            if kind is None:
                continue
            self._events.append(EventRecord(
                _iso_to_ms(ev["time"], ts_ms), kind,
                detail={"provider": ev["provider"], "event_id": ev["event_id"]},
                ext_id=f"{ev['provider']}:{ev['record_id']}",
            ))
        return []
