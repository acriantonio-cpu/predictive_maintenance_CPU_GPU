# SPDX-License-Identifier: Apache-2.0
"""Scenari di guasto sintetici (Fase 0 e test di integrazione)."""

from __future__ import annotations

from .model import Fault

SCENARIOS: dict[str, list[Fault]] = {
    "healthy": [],
    "dust": [Fault("dust", onset_day=12, rate=0.03)],
    "paste": [Fault("paste_cpu", onset_day=12, rate=0.08)],
    "fan_fail": [Fault("fan_fail_cpu", onset_day=14, severity=0.35, duration_day=0)],
    "gpu_pad": [Fault("gpu_pad", onset_day=12, rate=0.06)],
    "driver_change": [Fault("driver_change", onset_day=14, duration_day=0)],
    "dust_then_clean": [Fault("dust", onset_day=8, rate=0.035), Fault("clean", onset_day=22)],
    "ambient": [Fault("ambient", onset_day=0, severity=5.0, duration_day=0)],
    "power_limit": [Fault("power_limit_gpu", onset_day=14, severity=0.7, duration_day=0)],
    "throttle": [Fault("fan_fail_cpu", onset_day=14, severity=0.05, duration_day=0)],
    "whea": [Fault("whea", onset_day=17, rate=3.0, duration_day=0)],
    "frozen_sensor": [Fault("frozen_cpu_temp", onset_day=14, duration_day=1.0)],
}

DESCRIPTIONS: dict[str, str] = {
    "healthy": "macchina sana (controllo negativo)",
    "dust": "accumulo di polvere: deriva lenta di Rth e sforzo ventola",
    "paste": "pasta termica CPU che si secca: Rth CPU sale, ventola stabile",
    "fan_fail": "ventola CPU degradata (gradino)",
    "gpu_pad": "pasta/pad GPU: sale il delta hotspot-edge",
    "driver_change": "cambio driver GPU (confondente, controllo negativo)",
    "dust_then_clean": "polvere e poi pulizia dichiarata (efficacia della manutenzione)",
    "ambient": "variazione della temperatura ambiente (controllo negativo)",
    "power_limit": "limite di potenza GPU impostato dall'utente (solo info)",
    "throttle": "ventola CPU quasi ferma: throttling grave",
    "whea": "errori WHEA corretti in aumento",
    "frozen_sensor": "sensore di temperatura CPU congelato per un giorno",
}
