# SPDX-License-Identifier: Apache-2.0
"""Test di trend: Mann-Kendall (non parametrico) e trend lineare (confronto).

Il Mann-Kendall sulla serie giornaliera per regime è il rilevatore complementare a
EWMA e CUSUM per le derive lente (sezione 7). Varianza corretta per i pareggi.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import ArrayLike


@dataclass(frozen=True)
class MKResult:
    s: int
    var_s: float
    z: float
    p: float  # bilaterale
    tau: float
    sen_slope: float


def mann_kendall(x: ArrayLike) -> MKResult:
    a = np.asarray(x, dtype=float)
    n = a.size
    if n < 3:
        return MKResult(0, 0.0, 0.0, 1.0, 0.0, 0.0)
    diff = np.sign(a[None, :] - a[:, None])
    s = int(np.triu(diff, 1).sum())
    _, counts = np.unique(a, return_counts=True)
    ties = counts[counts > 1]
    var_s = (n * (n - 1) * (2 * n + 5) - float((ties * (ties - 1) * (2 * ties + 5)).sum())) / 18
    if s > 0:
        z = (s - 1) / math.sqrt(var_s) if var_s > 0 else 0.0
    elif s < 0:
        z = (s + 1) / math.sqrt(var_s) if var_s > 0 else 0.0
    else:
        z = 0.0
    p = math.erfc(abs(z) / math.sqrt(2))
    tau = s / (n * (n - 1) / 2)
    i, j = np.triu_indices(n, 1)
    slopes = (a[j] - a[i]) / (j - i)
    return MKResult(s, float(var_s), float(z), float(p), float(tau), float(np.median(slopes)))


def linear_trend(x: ArrayLike) -> tuple[float, float]:
    """Pendenza OLS per indice e p-value bilaterale (t di Student)."""
    from scipy.stats import linregress

    a = np.asarray(x, dtype=float)
    if a.size < 3:
        return 0.0, 1.0
    res: Any = linregress(np.arange(a.size), a)
    return float(res.slope), float(res.pvalue)
