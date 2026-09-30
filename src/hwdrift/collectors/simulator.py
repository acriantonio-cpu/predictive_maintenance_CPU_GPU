# SPDX-License-Identifier: Apache-2.0
"""Collector simulato in tempo reale (sviluppo senza hardware né privilegi).

Scenari supportati dal collector (i guasti partono dopo ``fault_after_s``):

* ``healthy``: carico variabile, nessun guasto;
* ``throttle``: la ventola CPU si ferma quasi del tutto -> throttling grave;
* ``frozen``: il sensore di temperatura CPU si congela;
* ``crash``: il collector inizia a fallire (test del watchdog);
* ``power_limit``: la GPU va a limite di potenza (solo info).

Per scenari lunghi (settimane) usare ``hwdrift simulate``, che genera i dati offline.
"""

from __future__ import annotations

from ..channels import spec_for
from ..model import Sample
from ..sim.model import Fault, Machine, Workload
from .base import Collector

_ONLINE = {
    "healthy": [],
    "throttle": [Fault("fan_fail_cpu", onset_day=0, severity=0.02, duration_day=0)],
    "frozen": [Fault("frozen_cpu_temp", onset_day=0, duration_day=0)],
    "crash": [],
    "power_limit": [Fault("power_limit_gpu", onset_day=0, severity=0.5, duration_day=0)],
}


class SimulatorCollector(Collector):
    name = "simulator"

    def start(self) -> None:
        scen = self.options.get("scenario", "healthy")
        if scen not in _ONLINE:
            raise ValueError(f"scenario simulatore non valido: {scen} ({sorted(_ONLINE)})")
        self.scenario = scen
        self.fault_after = float(self.options.get("fault_after_s", 600.0))
        seed = int(self.options.get("seed", 1))
        self.machine = Machine(faults=[], seed=seed)
        self.work = Workload(seed=seed, on_hours=(0.0, 24.0))
        self._t0: float | None = None
        self._last: float | None = None

    def poll(self, ts_ms: int, mono_s: float) -> list[Sample]:
        if self._t0 is None:
            self._t0 = mono_s
        t = mono_s - self._t0
        dt = 1.0 if self._last is None else max(mono_s - self._last, 1e-3)
        self._last = mono_s
        faulted = t >= self.fault_after
        if faulted and self.scenario == "crash":
            raise RuntimeError("guasto simulato del collector")
        self.machine.faults = _ONLINE[self.scenario] if faulted else []
        if faulted and self.scenario == "throttle":
            p_cpu, p_gpu = 0.9 * self.machine.params.cpu_p_max, 0.2 * self.machine.params.gpu_p_max
        else:
            p_cpu, p_gpu = self.work.target(t, self.machine.params)
        vals = self.machine.step(dt, t / 86400.0, p_cpu, p_gpu)
        out = []
        for ch, v in vals.items():
            hw = "cpu" if ch.startswith("cpu") else ("gpu" if ch.startswith("gpu") else "board")
            spec = spec_for(ch)
            s = self._sample(ts_ms, mono_s, f"/sim/{ch}", hw, "sim", ch, float(v),
                             spec.unit if spec else "")
            s.channel = ch  # il simulatore produce già canali canonici
            out.append(s)
        return out
