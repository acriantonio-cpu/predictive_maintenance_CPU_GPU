# SPDX-License-Identifier: Apache-2.0
"""Rilevatore di errori immediati (sezione 7, failure mode 11).

Il throttling grave non aspetta le carte di controllo: a ogni ciclo di
campionamento il collector valuta regole semplici sui valori istantanei e, dopo un
debounce, apre un *episodio* nella tabella ``rt_events``. Una sola notifica per
episodio; si aggiorna solo se la gravità peggiora.

Gravità (sezione 7):

* throttling termico a carico basso/medio, o entro pochi minuti dall'inizio del
  carico -> ``error``;
* termico dopo carico prolungato in regime alto -> ``warning`` (su un portatile o
  in una stanza calda può essere normale);
* limite di potenza -> ``info`` (spesso voluto);
* ventola ferma con temperatura alta e carico -> ``error``.

Nessuna dipendenza esterna: gira nel collector residente.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2}

# Bit delle "clocks event reasons" NVML (nvml.h: nvmlClocksEventReason*).
# TODO(M0): verificare i valori con la versione di nvidia-ml-py installata
# (``pynvml.nvmlClocksThrottleReasonHwSlowdown`` ecc.).
NVML_GPU_IDLE = 0x1
NVML_APP_CLOCKS = 0x2
NVML_SW_POWER_CAP = 0x4
NVML_HW_SLOWDOWN = 0x8
NVML_SYNC_BOOST = 0x10
NVML_SW_THERMAL = 0x20
NVML_HW_THERMAL = 0x40
NVML_HW_POWER_BRAKE = 0x80
NVML_DISPLAY_CLOCKS = 0x100

NVML_THERMAL_MASK = NVML_SW_THERMAL | NVML_HW_THERMAL | NVML_HW_SLOWDOWN | NVML_HW_POWER_BRAKE
NVML_POWER_MASK = NVML_SW_POWER_CAP


@dataclass
class _Episode:
    key: str
    component: str
    reason: str
    first_true_s: float
    confirmed: bool = False
    rt_id: int | None = None
    severity: str = "info"
    last_true_s: float = 0.0
    peak: float | None = None
    start_ts: int = 0


@dataclass
class RealtimeConfig:
    debounce_s: float = 7.0
    release_s: float = 15.0
    cpu_clock_ratio: float = 0.70
    cpu_load_min_pct: float = 80.0
    cpu_temp_margin_c: float = 10.0
    tjmax_c: float = 100.0
    gpu_thermal_limit_c: float = 83.0
    nominal_clock_mhz: float | None = None
    sustained_high_min: float = 10.0
    fan_stop_temp_c: float = 75.0
    high_power_fraction: float = 0.65

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> RealtimeConfig:
        rt = cfg["realtime"]
        return cls(
            debounce_s=rt["debounce_s"], release_s=rt["release_s"],
            cpu_clock_ratio=rt["cpu_clock_ratio"], cpu_load_min_pct=rt["cpu_load_min_pct"],
            cpu_temp_margin_c=rt["cpu_temp_margin_c"], tjmax_c=cfg["profile"]["cpu"]["tjmax_c"],
            gpu_thermal_limit_c=cfg["profile"]["gpu"]["thermal_limit_c"],
            nominal_clock_mhz=cfg["profile"]["cpu"]["nominal_clock_mhz"],
            sustained_high_min=rt["sustained_high_min"], fan_stop_temp_c=rt["fan_stop_temp_c"],
            high_power_fraction=rt["high_power_fraction"],
        )


# callback: (azione, episodio) con azione in {"open", "escalate", "peak", "close"}
Sink = Callable[[str, _Episode], None]


@dataclass
class RealtimeDetector:
    cfg: RealtimeConfig
    sink: Sink
    _episodes: dict[str, _Episode] = field(default_factory=dict)
    _high_since: dict[str, float | None] = field(default_factory=dict)
    _pmax: dict[str, float] = field(default_factory=dict)

    # ---------------------------------------------------------------- helpers
    def _load_state(self, comp: str, power: float | None, util: float | None,
                    mono: float) -> tuple[bool, float]:
        """Restituisce (carico alto?, minuti da cui il carico è alto)."""
        high = False
        if power is not None and power > 0:
            self._pmax[comp] = max(self._pmax.get(comp, 0.0), power)
            high = power >= self.cfg.high_power_fraction * self._pmax[comp]
        elif util is not None:
            high = util >= self.cfg.cpu_load_min_pct
        if high:
            since = self._high_since.get(comp)
            if since is None:
                self._high_since[comp] = since = mono
            return True, (mono - since) / 60.0
        self._high_since[comp] = None
        return False, 0.0

    def _thermal_severity(self, high: bool, high_min: float) -> str:
        if high and high_min >= self.cfg.sustained_high_min:
            return "warning"
        return "error"

    # ------------------------------------------------------------------- main
    def update(self, values: dict[str, float], mono: float, ts_ms: int) -> None:
        """Valuta le condizioni sui valori istantanei (canale -> valore, qualità OK)."""
        active: dict[str, tuple[str, str, str, float | None]] = {}

        # ---- CPU
        t = values.get("cpu.pkg.temp_c")
        load = values.get("cpu.load_pct")
        clk = values.get("cpu.clock_eff_mhz")
        nominal = values.get("cpu.clock_nominal_mhz") or self.cfg.nominal_clock_mhz
        high, high_min = self._load_state("cpu", values.get("cpu.pkg.power_w"), load, mono)
        thermal_flag = values.get("cpu.throttle_thermal", 0.0) >= 0.5
        near_limit = t is not None and t >= self.cfg.tjmax_c - self.cfg.cpu_temp_margin_c
        clock_low = (clk is not None and nominal and load is not None
                     and load >= self.cfg.cpu_load_min_pct
                     and clk < self.cfg.cpu_clock_ratio * nominal)
        # senza clock effettivo (es. solo LHM) la CPU al limite termico sotto carico è
        # comunque in throttling: le CPU moderne rallentano a Tjmax
        at_limit = (t is not None and t >= self.cfg.tjmax_c - 1.0
                    and (load is None or load >= self.cfg.cpu_load_min_pct / 2))
        if thermal_flag or (clock_low and near_limit) or at_limit:
            active["cpu.thermal"] = ("cpu", "thermal", self._thermal_severity(high, high_min), t)
        elif values.get("cpu.throttle_power", 0.0) >= 0.5:
            active["cpu.power"] = ("cpu", "power_limit", "info", values.get("cpu.pkg.power_w"))
        fan = values.get("cpu.fan_rpm")
        if (fan is not None and fan < 100 and t is not None
                and t >= self.cfg.fan_stop_temp_c):
            active["cpu.fan"] = ("cpu", "fan_stopped", "error", t)

        # ---- GPU (una o più)
        gpus = sorted({k.split(".")[0] for k in values if k.startswith("gpu")})
        for g in gpus:
            gt = values.get(f"{g}.temp_edge_c")
            gh, gh_min = self._load_state(g, values.get(f"{g}.power_w"),
                                          values.get(f"{g}.util_pct"), mono)
            reasons = int(values.get(f"{g}.throttle_reasons", 0.0))
            thermal = (reasons & NVML_THERMAL_MASK) or values.get(f"{g}.throttle_thermal", 0) >= .5
            power = (reasons & NVML_POWER_MASK) or values.get(f"{g}.throttle_power", 0) >= .5
            if thermal:
                active[f"{g}.thermal"] = (g, "thermal", self._thermal_severity(gh, gh_min), gt)
            elif power:
                active[f"{g}.power"] = (g, "power_limit", "info", values.get(f"{g}.power_w"))
            gfan = values.get(f"{g}.fan_rpm")
            gutil = values.get(f"{g}.util_pct", 0.0)
            if (gfan is not None and gfan < 100 and gt is not None
                    and gt >= self.cfg.fan_stop_temp_c and gutil >= 50):
                # molte GPU spengono le ventole a riposo: conta solo sotto carico
                active[f"{g}.fan"] = (g, "fan_stopped", "error", gt)

        self._advance(active, mono, ts_ms)

    def _advance(self, active: dict[str, tuple[str, str, str, float | None]], mono: float,
                 ts_ms: int) -> None:
        for key, (comp, reason, sev, val) in active.items():
            ep = self._episodes.get(key)
            if ep is None:
                ep = _Episode(key, comp, reason, first_true_s=mono, severity=sev,
                              start_ts=ts_ms)
                self._episodes[key] = ep
            ep.last_true_s = mono
            new_peak = val is not None and (ep.peak is None or val > ep.peak)
            if new_peak:
                ep.peak = val
            if not ep.confirmed and mono - ep.first_true_s >= self.cfg.debounce_s:
                ep.confirmed = True
                ep.severity = sev
                self.sink("open", ep)
            elif ep.confirmed:
                if SEVERITY_ORDER[sev] > SEVERITY_ORDER[ep.severity]:
                    ep.severity = sev
                    self.sink("escalate", ep)
                elif new_peak:
                    self.sink("peak", ep)
        for key in list(self._episodes):
            if key in active:
                continue
            ep = self._episodes[key]
            if mono - ep.last_true_s >= self.cfg.release_s:
                if ep.confirmed:
                    self.sink("close", ep)
                del self._episodes[key]

    def close_all(self) -> None:
        for ep in self._episodes.values():
            if ep.confirmed:
                self.sink("close", ep)
        self._episodes.clear()
