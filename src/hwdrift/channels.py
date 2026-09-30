# SPDX-License-Identifier: Apache-2.0
"""Canali canonici e mappatura dei sensori grezzi (sezione 4).

Un livello di mappatura converte i nomi grezzi (diversi per sorgente, lingua e
macchina) in canali stabili come ``cpu.pkg.temp_c``. L'auto-discovery propone una
mappatura con regole euristiche; l'utente la conferma e la salva in un profilo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True, slots=True)
class ChannelSpec:
    unit: str
    lo: float  # limite fisico inferiore plausibile
    hi: float  # limite fisico superiore plausibile
    max_rate: float | None = None  # variazione massima plausibile per secondo
    glitch_values: tuple[float, ...] = ()  # valori tipici di lettura fallita
    freeze_s: float | None = None  # dopo quanti secondi un valore identico è "congelato"
    description: str = ""


# max_rate: il package CPU può salire di 20-30 °C in meno di un secondo all'avvio di un
# carico (Tctl dei Ryzen, spike Intel): 50 °C/s scarta solo salti fisicamente impossibili
_TEMP = {"unit": "°C", "lo": -10.0, "hi": 125.0, "max_rate": 50.0,
         "glitch_values": (0.0, 255.0, -128.0, 127.0), "freeze_s": 900.0}

# Canali canonici fissi. I canali con indice (gpuN, ssdN, chassis.fanN) si
# risolvono con ``spec_for`` tramite pattern.
CANONICAL: dict[str, ChannelSpec] = {
    "cpu.pkg.temp_c": ChannelSpec(**_TEMP, description="temperatura package CPU"),
    "cpu.pkg.power_w": ChannelSpec("W", 0.0, 500.0, None, (), None, "potenza package CPU"),
    "cpu.clock_eff_mhz": ChannelSpec("MHz", 100.0, 7000.0, None, (0.0,), None,
                                     "clock effettivo medio CPU"),
    "cpu.clock_nominal_mhz": ChannelSpec("MHz", 100.0, 7000.0, None, (0.0,), None,
                                         "clock nominale CPU"),
    "cpu.load_pct": ChannelSpec("%", 0.0, 100.0, None, (), None, "utilizzo CPU"),
    "cpu.throttle_thermal": ChannelSpec("flag", 0.0, 1.0, None, (), None,
                                        "throttling termico CPU (se esposto)"),
    "cpu.throttle_power": ChannelSpec("flag", 0.0, 1.0, None, (), None,
                                      "limite di potenza CPU (se esposto)"),
    "cpu.fan_rpm": ChannelSpec("rpm", 0.0, 10000.0, 3000.0, (65535.0,), None, "ventola CPU"),
    "mb.temp_c": ChannelSpec(**_TEMP, description="temperatura scheda madre"),
    "ambient.temp_c": ChannelSpec("°C", -10.0, 60.0, 2.0, (0.0, 255.0), 7200.0,
                                  "temperatura ambiente (sensore esterno o manuale)"),
    "hwdrift.cpu_pct": ChannelSpec("%", 0.0, 100.0 * 256, None, (), None,
                                   "CPU usata dal collector (% di un core)"),
    "hwdrift.rss_mb": ChannelSpec("MB", 0.0, 1e5, None, (), None, "memoria del collector"),
    "hwdrift.interval_s": ChannelSpec("s", 0.1, 60.0, None, (), None,
                                      "intervallo di campionamento effettivo"),
    "hwdrift.game_safe": ChannelSpec("flag", 0.0, 1.0, None, (), None, "modalità game-safe"),
}

_PATTERNS: list[tuple[re.Pattern[str], ChannelSpec]] = [
    (re.compile(r"^gpu\d+\.temp_(edge|hotspot|mem)_c$"),
     ChannelSpec(**_TEMP, description="temperatura GPU")),
    (re.compile(r"^gpu\d+\.power_w$"), ChannelSpec("W", 0.0, 1000.0, None, (), None,
                                                   "potenza scheda GPU")),
    (re.compile(r"^gpu\d+\.fan_rpm$"), ChannelSpec("rpm", 0.0, 10000.0, 3000.0, (65535.0,),
                                                   None, "ventola GPU")),
    (re.compile(r"^gpu\d+\.fan_pct$"), ChannelSpec("%", 0.0, 100.0, None, (), None,
                                                   "ventola GPU (duty)")),
    (re.compile(r"^gpu\d+\.util_pct$"), ChannelSpec("%", 0.0, 100.0, None, (), None,
                                                    "utilizzo GPU")),
    (re.compile(r"^gpu\d+\.clock_mhz$"), ChannelSpec("MHz", 0.0, 5000.0, None, (), None,
                                                     "clock grafico GPU")),
    (re.compile(r"^gpu\d+\.throttle_(thermal|power)$"),
     ChannelSpec("flag", 0.0, 1.0, None, (), None, "throttling GPU")),
    (re.compile(r"^gpu\d+\.throttle_reasons$"),
     ChannelSpec("bitmask", 0.0, 2.0**63, None, (), None, "bitmask throttle reasons NVML")),
    (re.compile(r"^gpu\d+\.pcie_replay$"),
     ChannelSpec("count", 0.0, 2.0**63, None, (), None, "contatore replay PCIe (cumulativo)")),
    (re.compile(r"^ssd\d+\.temp_c$"), ChannelSpec(**_TEMP, description="temperatura SSD")),
    (re.compile(r"^chassis\.fan\d+_rpm$"), ChannelSpec("rpm", 0.0, 10000.0, 3000.0,
                                                       (65535.0,), None, "ventola chassis")),
    (re.compile(r"^status\.[a-z0-9_]+$"), ChannelSpec("flag", 0.0, 1.0, None, (), None,
                                                       "stato del collector (1 = ok)")),
]

_CHANNEL_NAME = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")


def is_valid_channel_name(name: str) -> bool:
    return bool(_CHANNEL_NAME.match(name))


@lru_cache(maxsize=1024)
def spec_for(channel: str) -> ChannelSpec | None:
    """Specifica di un canale canonico, o ``None`` se il nome non è riconosciuto."""
    spec = CANONICAL.get(channel)
    if spec is not None:
        return spec
    for pat, s in _PATTERNS:
        if pat.match(channel):
            return s
    return None


# --------------------------------------------------------------------------- mapping

@dataclass(frozen=True, slots=True)
class _Rule:
    hw: re.Pattern[str]
    kind: re.Pattern[str]
    name: re.Pattern[str]
    target: str  # può contenere {idx} e {n}


def _r(hw: str, kind: str, name: str, target: str) -> _Rule:
    return _Rule(re.compile(hw, re.I), re.compile(kind, re.I), re.compile(name, re.I), target)


# Regole euristiche per LibreHardwareMonitor e HWiNFO. ``kind`` è il tipo di
# sensore LHM (Temperature, Power, Load, Fan, Clock, Control) o l'unità HWiNFO.
# TODO(M0): verificare i nomi reali sulle macchine di prova e aggiornare le regole;
# i nomi cambiano con la versione di LHM, il produttore della CPU e la lingua.
_RULES: list[_Rule] = [
    _r(r"cpu", r"temp|°C", r"^(cpu package|core \(tctl/tdie\)|tctl/tdie|cpu \(tctl/tdie\)|"
       r"package|cpu package temperature)$", "cpu.pkg.temp_c"),
    _r(r"cpu", r"power|^W$", r"^(cpu package|package|cpu package power)$", "cpu.pkg.power_w"),
    _r(r"cpu", r"load|%", r"^(cpu total|total cpu usage)$", "cpu.load_pct"),
    _r(r"gpu", r"temp|°C", r"^(gpu core|gpu temperature|gpu)$", "gpu{idx}.temp_edge_c"),
    _r(r"gpu", r"temp|°C", r"hot ?spot", "gpu{idx}.temp_hotspot_c"),
    _r(r"gpu", r"temp|°C", r"memory junction|gpu memory", "gpu{idx}.temp_mem_c"),
    _r(r"gpu", r"power|^W$", r"^(gpu package|gpu power|gpu board power|board power|"
       r"total board power)$", "gpu{idx}.power_w"),
    _r(r"gpu", r"load|%", r"^(gpu core|gpu core load|gpu utilization)$", "gpu{idx}.util_pct"),
    _r(r"gpu", r"fan|rpm", r"^(gpu fan|gpu fan ?#?1|gpu fan1)$", "gpu{idx}.fan_rpm"),
    _r(r"gpu", r"control|%", r"^(gpu fan|gpu fan ?#?1)$", "gpu{idx}.fan_pct"),
    _r(r"gpu", r"clock|mhz", r"^(gpu core|gpu clock)$", "gpu{idx}.clock_mhz"),
    _r(r"superio|motherboard|lpc|mainboard", r"fan|rpm", r"^(cpu fan|cpu)$", "cpu.fan_rpm"),
    _r(r"superio|motherboard|lpc|mainboard", r"fan|rpm", r"^(fan|chassis fan|system fan) ?#?(\d+)$",
       "chassis.fan{n}_rpm"),
    _r(r"superio|motherboard|lpc|mainboard", r"temp|°C", r"^(system|motherboard|mainboard)$",
       "mb.temp_c"),
    _r(r"storage|drive|nvme|ssd|hdd", r"temp|°C", r"^(temperature|composite temperature|"
       r"drive temperature)$", "ssd{idx}.temp_c"),
]

_IDX = re.compile(r"/(\d+)(?:/|$)")


def propose_channel(hw_type: str, sensor_kind: str, raw_name: str, sensor_id: str = "",
                    hw_index: int | None = None) -> str | None:
    """Propone un canale canonico per un sensore grezzo (auto-discovery).

    Restituisce ``None`` se nessuna regola si applica: il sensore resta non mappato.
    """
    name = raw_name.strip()
    for rule in _RULES:
        if not (rule.hw.search(hw_type) and rule.kind.search(sensor_kind)):
            continue
        m = rule.name.search(name)
        if not m:
            continue
        idx = hw_index
        if idx is None:
            mi = _IDX.search(sensor_id)
            idx = int(mi.group(1)) if mi else 0
        n = next((g for g in reversed(m.groups()) if g and g.isdigit()), "1")
        return rule.target.format(idx=idx, n=n)
    return None


@dataclass
class ChannelMap:
    """Mappatura confermata ``sensor_id -> canale`` (profilo per macchina)."""

    mapping: dict[str, str]
    auto: bool = True  # se True, i sensori non in ``mapping`` usano ``propose_channel``

    def resolve(self, sensor_id: str, hw_type: str, sensor_kind: str, raw_name: str,
                hw_index: int | None = None) -> str | None:
        ch = self.mapping.get(sensor_id)
        if ch is not None:
            return ch or None  # stringa vuota = sensore escluso esplicitamente
        if self.auto:
            return propose_channel(hw_type, sensor_kind, raw_name, sensor_id, hw_index)
        return None
