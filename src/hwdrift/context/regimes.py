# SPDX-License-Identifier: Apache-2.0
"""Regimi di carico (idle, medio, alto) definiti sulla potenza (sezione 6).

Due modalità:

* ``adaptive``: terzili della potenza osservata nelle finestre stazionarie di
  calibrazione; si adattano a TDP e uso del PC, ma su un PC quasi sempre inattivo
  i terzili cadono tutti in idle;
* ``fixed``: frazioni della potenza massima osservata (default 30% e 65%), più
  facili da spiegare.

I confini si calcolano una volta (calibrazione) e restano bloccati: se si
muovessero, le carte confronterebbero finestre di regimi diversi.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

REGIMES = ("idle", "medium", "high")


@dataclass(frozen=True)
class RegimeBounds:
    mode: str
    lo: float  # idle < lo
    hi: float  # medium < hi <= high
    pmax: float
    n: int

    def assign(self, power: float) -> str:
        if power < self.lo:
            return "idle"
        if power < self.hi:
            return "medium"
        return "high"

    def to_dict(self) -> dict[str, float | str | int]:
        return {"mode": self.mode, "lo": self.lo, "hi": self.hi, "pmax": self.pmax, "n": self.n}

    @classmethod
    def from_dict(cls, d: dict) -> RegimeBounds:
        return cls(str(d["mode"]), float(d["lo"]), float(d["hi"]), float(d["pmax"]), int(d["n"]))


def calibrate(window_power: np.ndarray, minute_power_max: np.ndarray, mode: str,
              fractions: tuple[float, float] | list[float]) -> RegimeBounds:
    wp = np.asarray(window_power, dtype=float)
    wp = wp[np.isfinite(wp)]
    mp = np.asarray(minute_power_max, dtype=float)
    mp = mp[np.isfinite(mp)]
    if wp.size == 0:
        raise ValueError("nessuna finestra stazionaria per la calibrazione")
    # 99° percentile e non il massimo: un picco spurio non deve spostare i confini
    pmax = float(np.percentile(mp, 99)) if mp.size else float(wp.max())
    if mode == "adaptive":
        lo, hi = (float(v) for v in np.quantile(wp, [1 / 3, 2 / 3]))
        if hi - lo < 1e-6:
            hi = lo + 1e-6
    else:
        lo, hi = fractions[0] * pmax, fractions[1] * pmax
    return RegimeBounds(mode, lo, hi, pmax, int(wp.size))
