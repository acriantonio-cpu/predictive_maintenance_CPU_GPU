# SPDX-License-Identifier: Apache-2.0
"""Tipi di dato condivisi: Sample, qualità ed eventi.

Nessuna dipendenza esterna: questo modulo è importato dal collector residente.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class Quality(IntEnum):
    """Flag di qualità di un campione (sezione 4, "Robustezza richiesta")."""

    OK = 0
    OUT_OF_RANGE = 1  # fuori dal range fisico del canale
    GLITCH = 2  # valore tipico di lettura fallita (0, 255) o salto impossibile
    FROZEN = 3  # valore congelato per troppo tempo
    MISSING = 4  # sensore scomparso / lettura nulla
    UNMAPPED = 5  # sensore grezzo senza canale canonico


def now_ms() -> int:
    """Ora UTC in millisecondi interi (unico formato temporale nel database)."""
    return int(time.time() * 1000)


@dataclass(slots=True)
class Sample:
    """Un campione prodotto da un collector.

    ``channel`` è il nome canonico (es. ``cpu.pkg.temp_c``) oppure ``None`` se il
    sensore grezzo non è mappato: in quel caso il campione serve solo a ``discover``.
    """

    ts_ms: int
    source: str
    sensor_id: str
    hw_type: str
    raw_name: str
    value: float | None
    unit: str
    channel: str | None = None
    quality: Quality = Quality.OK
    mono_s: float = field(default=0.0)


@dataclass(slots=True)
class EventRecord:
    """Evento discreto: manutenzione, configurazione, gap, errori hardware.

    ``ext_id`` serve a de-duplicare eventi letti da sorgenti esterne (es. il
    RecordID del registro eventi di Windows).
    """

    ts_ms: int
    kind: str
    source: str = "auto"
    detail: dict[str, Any] = field(default_factory=dict)
    note: str = ""
    ext_id: str | None = None


# Tipi di evento riconosciuti. I prefissi contano: ``config.*`` è un confondente per
# le carte (sezione 7), ``maintenance.*`` chiude il segmento della carta.
EVENT_KINDS: dict[str, str] = {
    "maintenance.clean": "pulizia (filtri, ventole, dissipatori)",
    "maintenance.repaste": "sostituzione pasta termica / pad",
    "maintenance.fan_replace": "sostituzione ventola o pompa",
    "maintenance.other": "altra manutenzione",
    "config.driver": "cambio versione driver",
    "config.bios": "cambio versione BIOS/firmware",
    "config.profile": "cambio profilo ventole o di potenza",
    "config.hardware": "cambio hardware o posizione del PC",
    "system.reboot": "riavvio",
    "system.gap": "interruzione della raccolta (sospensione, ibernazione, arresto)",
    "system.collector_start": "avvio del collector",
    "system.healthcheck": "health-check attivo",
    "system.baseline_start": "nuova Fase I (baseline) avviata dall'utente",
    "hw.whea_corrected": "errore hardware corretto (WHEA)",
    "hw.whea_fatal": "errore hardware fatale (WHEA)",
    "hw.tdr": "timeout/reset del driver video (TDR)",
    "hw.kernel_power": "spegnimento imprevisto (Kernel-Power 41)",
    "hw.bugcheck": "schermata blu (BugCheck)",
    "user.note": "annotazione",
}

USER_EVENT_KINDS = tuple(
    k for k in EVENT_KINDS if k.startswith(("maintenance.", "config.", "user."))
)


# motivi degli episodi in tempo reale (rt_events.reason)
RT_REASONS: dict[str, str] = {
    "thermal": "throttling termico", "power_limit": "limite di potenza",
    "fan_stopped": "ventola ferma con temperatura alta",
}


def rt_reason(reason: str) -> str:
    """Motivo di un episodio in tempo reale, nella lingua attiva."""
    from .i18n import tr

    return tr(RT_REASONS.get(reason, reason))


def is_config_event(kind: str) -> bool:
    return kind.startswith("config.")


def is_maintenance_event(kind: str) -> bool:
    return kind.startswith("maintenance.")
