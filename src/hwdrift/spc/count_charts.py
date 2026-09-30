# SPDX-License-Identifier: Apache-2.0
"""Carte per conteggi (WHEA, errori PCIe, TDR): dati di Poisson, non I-MR.

* carta c: LC = c_bar, UCL = c_bar + 3 sqrt(c_bar), LCL = max(0, c_bar - 3 sqrt(c_bar));
* carta u (esposizione variabile n_i, es. ore di accensione):
  UCL_i = u_bar + 3 sqrt(u_bar / n_i).

Regola diretta aggiuntiva (applicata dal chiamante): qualsiasi evento non corretto
(fatale) è sempre un allarme.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike


@dataclass(frozen=True)
class CLimits:
    center: float
    ucl: float
    lcl: float


def c_chart(counts_phase1: ArrayLike) -> CLimits:
    c = np.asarray(counts_phase1, dtype=float)
    if c.size == 0:
        raise ValueError("servono conteggi di Fase I")
    cbar = float(c.mean())
    r = 3 * np.sqrt(cbar)
    return CLimits(cbar, cbar + r, max(0.0, cbar - r))


def c_signals(counts: ArrayLike, lim: CLimits) -> list[int]:
    c = np.asarray(counts, dtype=float)
    return [int(i) for i in np.flatnonzero(c > lim.ucl)]


def u_chart(counts: ArrayLike, exposure: ArrayLike) -> tuple[float, np.ndarray, np.ndarray]:
    c = np.asarray(counts, dtype=float)
    n = np.asarray(exposure, dtype=float)
    if np.any(n <= 0):
        raise ValueError("esposizione deve essere > 0")
    ubar = float(c.sum() / n.sum())
    r = 3 * np.sqrt(ubar / n)
    return ubar, ubar + r, np.maximum(0.0, ubar - r)
