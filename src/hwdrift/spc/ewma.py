# SPDX-License-Identifier: Apache-2.0
"""Carta EWMA (metodo di confronto, più sensibile alle derive piccole e lente).

    z_t = lambda * x_t + (1 - lambda) * z_{t-1},  z_0 = mu
    limiti: mu ± L * sigma * sqrt(lambda / (2 - lambda) * (1 - (1 - lambda)^(2t)))

Con lambda = 0.2, L = 2.86 dà ARL0 ≈ 370 (paragonabile a Shewhart 3 sigma).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike


@dataclass(frozen=True)
class EwmaResult:
    z: np.ndarray
    ucl: np.ndarray
    lcl: np.ndarray
    signals: list[tuple[int, str]]  # (indice, lato) al primo attraversamento


def ewma(x: ArrayLike, mu: float, sigma: float, lam: float = 0.2, L: float = 2.86) -> EwmaResult:
    if not 0 < lam <= 1:
        raise ValueError("lambda in (0, 1]")
    a = np.asarray(x, dtype=float)
    z = np.empty_like(a)
    prev = mu
    for i, v in enumerate(a):
        prev = lam * v + (1 - lam) * prev
        z[i] = prev
    t = np.arange(1, a.size + 1)
    width = L * sigma * np.sqrt(lam / (2 - lam) * (1 - (1 - lam) ** (2 * t)))
    ucl, lcl = mu + width, mu - width
    sig: list[tuple[int, str]] = []
    state = 0
    for i in range(a.size):
        cur = 1 if z[i] > ucl[i] else (-1 if z[i] < lcl[i] else 0)
        if cur != 0 and cur != state:
            sig.append((i, "upper" if cur > 0 else "lower"))
        state = cur
    return EwmaResult(z, ucl, lcl, sig)
