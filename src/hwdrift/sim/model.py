# SPDX-License-Identifier: Apache-2.0
"""Modello termico sintetico di un PC con CPU e GPU (Fase 0 della validazione).

Modello a due resistenze per componente, del primo ordine:

    T_dissipatore = T_amb + R_hs(ventola, polvere) * P
    T_chip        = T_dissipatore + R_pasta * P

La ventola segue la temperatura del *dissipatore* (curva lineare con saturazione):
così la polvere (R_hs sale) fa salire sia Rth sia lo sforzo ventola, mentre la
pasta secca (R_pasta sale) fa salire Rth ma non la ventola. È un'ipotesi di
simulazione coerente con la tabella di diagnosi (sezione 8), non una verità fisica:
va confrontata con i dati reali in Fase 3.

Nessuna dipendenza esterna: il simulatore gira anche nel collector residente.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field


@dataclass
class Fault:
    kind: str  # dust | paste_cpu | fan_fail_cpu | gpu_pad | driver_change | ambient |
    #            power_limit_gpu | whea | frozen_cpu_temp | clean
    onset_day: float = 0.0
    rate: float = 0.0  # crescita relativa per giorno (derive lente)
    severity: float = 0.0  # entità del gradino (guasti improvvisi)
    duration_day: float = 1.0


@dataclass
class MachineParams:
    t_amb: float = 22.0
    cpu_r_hs: float = 0.33
    cpu_r_paste: float = 0.09
    cpu_tjmax: float = 100.0
    cpu_nominal_mhz: float = 3600.0
    cpu_boost_mhz: float = 4300.0
    cpu_p_max: float = 125.0
    gpu_r_hs: float = 0.17
    gpu_r_hot: float = 0.045
    gpu_r_mem: float = 0.07
    gpu_limit: float = 83.0
    gpu_p_max: float = 280.0
    tau_s: float = 90.0
    noise_c: float = 0.25
    noise_p: float = 0.02


@dataclass
class MachineState:
    cpu_hs: float = 26.0
    cpu_t: float = 28.0
    gpu_hs: float = 30.0
    gpu_edge: float = 31.0
    mb: float = 28.0
    ssd: float = 32.0
    cpu_fan: float = 700.0
    gpu_fan: float = 0.0
    throttle_scale_cpu: float = 1.0
    throttle_scale_gpu: float = 1.0
    frozen_value: float | None = None


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclass
class Machine:
    params: MachineParams = field(default_factory=MachineParams)
    faults: list[Fault] = field(default_factory=list)
    seed: int = 1
    state: MachineState = field(default_factory=MachineState)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)

    # ------------------------------------------------------------- degradation
    def _factor(self, kind: str, day: float) -> float:
        """Moltiplicatore di degrado (1 = sano) per derive lente e gradini."""
        f = 1.0
        clean_day = min((x.onset_day for x in self.faults if x.kind == "clean"),
                        default=math.inf)
        for x in self.faults:
            if x.kind != kind or day < x.onset_day:
                continue
            end = clean_day if clean_day > x.onset_day else math.inf
            d = min(day, end) - x.onset_day
            if day >= end:
                continue  # la pulizia riporta allo stato sano
            f *= 1.0 + x.rate * d + x.severity
        return f

    def _active(self, kind: str, day: float) -> Fault | None:
        for x in self.faults:
            if x.kind == kind and x.onset_day <= day < x.onset_day + max(x.duration_day, 0):
                return x
            if x.kind == kind and x.duration_day <= 0 and day >= x.onset_day:
                return x
        return None

    def ambient(self, day: float) -> float:
        a = self._active("ambient", day)
        amp = a.severity if a else 0.0
        # stagionalità + ciclo giornaliero debole
        return (self.params.t_amb + amp * math.sin(2 * math.pi * (day - (a.onset_day if a else 0))
                                                   / 30.0) + 0.8 * math.sin(2 * math.pi * day))

    # -------------------------------------------------------------------- step
    def step(self, dt: float, day: float, p_cpu_target: float, p_gpu_target: float
             ) -> dict[str, float]:
        """Avanza di ``dt`` secondi e restituisce le *letture* dei sensori."""
        p = self.params
        s = self.state
        rng = self.rng
        alpha = 1.0 - math.exp(-dt / p.tau_s)
        t_amb = self.ambient(day)
        dust = self._factor("dust", day)
        paste = self._factor("paste_cpu", day)
        pad = self._factor("gpu_pad", day)
        fan_fail = self._active("fan_fail_cpu", day)
        fan_scale = fan_fail.severity if fan_fail else 1.0

        # --- CPU: throttling se T >= Tjmax (riduce potenza e clock)
        if s.cpu_t >= p.cpu_tjmax - 0.5:
            s.throttle_scale_cpu = max(0.35, s.throttle_scale_cpu - 0.08 * dt / 5)
        else:
            s.throttle_scale_cpu = min(1.0, s.throttle_scale_cpu + 0.05 * dt / 5)
        p_cpu = p_cpu_target * s.throttle_scale_cpu * (1 + rng.gauss(0, p.noise_p))
        fan_cmd = _clamp(650 + (s.cpu_hs - 32.0) * 75.0, 650, 2300)
        s.cpu_fan = fan_cmd * fan_scale
        r_hs = p.cpu_r_hs * dust * math.sqrt(1500.0 / max(s.cpu_fan, 250.0))
        cpu_hs_ss = t_amb + r_hs * p_cpu
        s.cpu_hs += alpha * (cpu_hs_ss - s.cpu_hs)
        s.cpu_t = s.cpu_hs + p.cpu_r_paste * paste * p_cpu

        # --- GPU: limite termico (target) e limite di potenza opzionale
        plim = self._active("power_limit_gpu", day)
        p_cap = p.gpu_p_max * (plim.severity if plim else 1.0)
        power_limited = p_gpu_target > p_cap
        p_gpu_eff = min(p_gpu_target, p_cap)
        if s.gpu_edge >= p.gpu_limit:
            s.throttle_scale_gpu = max(0.5, s.throttle_scale_gpu - 0.05 * dt / 5)
        else:
            s.throttle_scale_gpu = min(1.0, s.throttle_scale_gpu + 0.05 * dt / 5)
        p_gpu = p_gpu_eff * s.throttle_scale_gpu * (1 + rng.gauss(0, p.noise_p))
        s.gpu_fan = 0.0 if s.gpu_hs < 48 else _clamp(1000 + (s.gpu_hs - 48) * 70, 1000, 3200)
        g_r_hs = p.gpu_r_hs * dust * math.sqrt(1800.0 / max(s.gpu_fan, 500.0))
        gpu_hs_ss = t_amb + g_r_hs * p_gpu
        s.gpu_hs += alpha * (gpu_hs_ss - s.gpu_hs)
        s.gpu_edge = s.gpu_hs + 0.02 * p_gpu
        hotspot = s.gpu_edge + p.gpu_r_hot * pad * p_gpu
        mem = s.gpu_edge + p.gpu_r_mem * p_gpu * 0.5

        # --- case: scheda madre e SSD seguono ambiente e calore totale (con polvere)
        s.mb += alpha * (t_amb + 0.035 * (p_cpu + p_gpu) * dust + 4 - s.mb)
        s.ssd += alpha * (t_amb + 0.02 * (p_cpu + p_gpu) * dust + 9 - s.ssd)

        # --- lettura sensori (rumore di misura)
        driver = self._active("driver_change", day)
        gpu_power_scale = 0.9 if driver else 1.0  # il nuovo driver riporta la potenza diversa
        n = p.noise_c
        cpu_temp_read = s.cpu_t + rng.gauss(0, n)
        frozen = self._active("frozen_cpu_temp", day)
        if frozen:
            if s.frozen_value is None:
                s.frozen_value = round(cpu_temp_read, 1)
            cpu_temp_read = s.frozen_value
        else:
            s.frozen_value = None
        clock = (p.cpu_boost_mhz if p_cpu_target > 20 else 2200.0) * s.throttle_scale_cpu
        gpu_reasons = 0
        if s.throttle_scale_gpu < 0.999:
            gpu_reasons |= 0x20  # SW thermal slowdown
        if power_limited:
            gpu_reasons |= 0x4  # SW power cap
        if p_gpu_target < 25:
            gpu_reasons |= 0x1  # idle
        return {
            "cpu.pkg.temp_c": cpu_temp_read,
            "cpu.pkg.power_w": max(p_cpu, 0.5),
            "cpu.load_pct": _clamp(100 * p_cpu_target / p.cpu_p_max + rng.gauss(0, 2), 0, 100),
            "cpu.clock_eff_mhz": clock + rng.gauss(0, 15),
            "cpu.clock_nominal_mhz": p.cpu_nominal_mhz,
            "cpu.throttle_thermal": 1.0 if s.throttle_scale_cpu < 0.999 else 0.0,
            "cpu.fan_rpm": max(0.0, s.cpu_fan + rng.gauss(0, 8)),
            "gpu0.temp_edge_c": s.gpu_edge + rng.gauss(0, n),
            "gpu0.temp_hotspot_c": hotspot + rng.gauss(0, n),
            "gpu0.temp_mem_c": mem + rng.gauss(0, n),
            "gpu0.power_w": max(p_gpu * gpu_power_scale, 1.0),
            "gpu0.util_pct": _clamp(100 * p_gpu_target / p.gpu_p_max + rng.gauss(0, 2), 0, 100),
            "gpu0.fan_rpm": s.gpu_fan if s.gpu_fan == 0 else s.gpu_fan + rng.gauss(0, 10),
            "gpu0.throttle_reasons": float(gpu_reasons),
            "gpu0.throttle_thermal": 1.0 if gpu_reasons & 0x20 else 0.0,
            "gpu0.throttle_power": 1.0 if gpu_reasons & 0x4 else 0.0,
            "mb.temp_c": s.mb + rng.gauss(0, n),
            "ssd0.temp_c": s.ssd + rng.gauss(0, n),
        }


# ------------------------------------------------------------------ workload

# (nome, frazione potenza CPU, frazione potenza GPU, peso, durata min/max in minuti)
BLOCKS = [
    ("office", 0.08, 0.06, 4, (10, 50)),
    ("compile", 0.85, 0.06, 2, (10, 45)),
    ("gaming", 0.40, 0.85, 2, (20, 70)),
    ("video", 0.35, 0.40, 2, (10, 40)),
]


@dataclass
class Workload:
    """Sequenza di blocchi di carico stabili, sessioni diurne, PC spento di notte."""

    seed: int = 1
    on_hours: tuple[float, float] = (8.0, 23.0)
    rng: random.Random = field(init=False)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed * 7919 + 17)
        self._block_end = -1.0
        self._cur = (0.08, 0.06)

    def is_on(self, t_s: float) -> bool:
        hour = (t_s / 3600.0) % 24
        return self.on_hours[0] <= hour < self.on_hours[1]

    def target(self, t_s: float, p: MachineParams) -> tuple[float, float]:
        if t_s >= self._block_end:
            names = [b for b in BLOCKS]
            weights = [b[3] for b in BLOCKS]
            b = self.rng.choices(names, weights)[0]
            lo, hi = b[4]
            self._block_end = t_s + 60 * self.rng.uniform(lo, hi)
            jitter = self.rng.uniform(0.93, 1.07)
            self._cur = (b[1] * p.cpu_p_max * jitter, b[2] * p.gpu_p_max * jitter)
        return self._cur
