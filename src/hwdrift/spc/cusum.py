# SPDX-License-Identifier: Apache-2.0
"""CUSUM tabulare (metodo di confronto), con k = 0.5 sigma e h tra 4 e 5 sigma.

    C+_t = max(0, x_t - (mu + k) + C+_{t-1})
    C-_t = max(0, (mu - k) - x_t + C-_{t-1})

Segnale quando C+ o C- supera h (in unità di sigma).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike


@dataclass(frozen=True)
class CusumResult:
    c_plus: np.ndarray
    c_minus: np.ndarray
    signals: list[tuple[int, str]]  # (indice, lato) al primo attraversamento


def cusum(x: ArrayLike, mu: float, sigma: float, k: float = 0.5, h: float = 5.0) -> CusumResult:
    if sigma <= 0:
        raise ValueError("sigma deve essere > 0")
    a = (np.asarray(x, dtype=float) - mu) / sigma
    cp = np.zeros_like(a)
    cm = np.zeros_like(a)
    p = m = 0.0
    sig: list[tuple[int, str]] = []
    up = dn = False
    for i, v in enumerate(a):
        p = max(0.0, v - k + p)
        m = max(0.0, -k - v + m)
        cp[i], cm[i] = p, m
        if p > h and not up:
            sig.append((i, "upper"))
        if m > h and not dn:
            sig.append((i, "lower"))
        up, dn = p > h, m > h
    return CusumResult(cp, cm, sig)
