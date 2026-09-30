# SPDX-License-Identifier: Apache-2.0
"""Controlli sui presupposti dell'I-MR (Fase I): autocorrelazione e normalità.

* ACF a lag 1 e test di Ljung-Box; sopra la soglia (0.3) si preferisce
  l'aggregazione giornaliera o i residui AR(1).
* Normalità: Shapiro-Wilk (n <= 5000); con forte asimmetria si usa sigma robusta.
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import ArrayLike


def acf(x: ArrayLike, lag: int = 1) -> float:
    a = np.asarray(x, dtype=float)
    if a.size <= lag + 1:
        return float("nan")
    d = a - a.mean()
    den = float(np.dot(d, d))
    if den == 0:
        return 0.0
    return float(np.dot(d[:-lag], d[lag:]) / den)


def ljung_box(x: ArrayLike, lags: int = 10) -> tuple[float, float]:
    """Statistica Q di Ljung-Box e p-value (chi quadro con ``lags`` gradi di libertà)."""
    from scipy.stats import chi2

    a = np.asarray(x, dtype=float)
    n = a.size
    lags = min(lags, n - 2)
    if lags < 1:
        return float("nan"), float("nan")
    q = n * (n + 2) * sum(acf(a, k) ** 2 / (n - k) for k in range(1, lags + 1))
    return float(q), float(chi2.sf(q, lags))


def skewness(x: ArrayLike) -> float:
    a = np.asarray(x, dtype=float)
    if a.size < 3 or a.std() == 0:
        return 0.0
    d = a - a.mean()
    return float((d ** 3).mean() / (d ** 2).mean() ** 1.5)


def ar1_residuals(x: ArrayLike) -> np.ndarray:
    """Residui di un modello AR(1) stimato con i momenti (per carte su dati autocorrelati)."""
    a = np.asarray(x, dtype=float)
    phi = acf(a, 1)
    mu = a.mean()
    return (a[1:] - mu) - phi * (a[:-1] - mu)


def check(x: ArrayLike, acf_threshold: float = 0.3) -> dict[str, float | bool | str]:
    from scipy.stats import shapiro

    a = np.asarray(x, dtype=float)
    r1 = acf(a, 1)
    q, p_lb = ljung_box(a)
    if 3 <= a.size <= 5000 and a.std() > 0:
        _, p_sw = shapiro(a)
        p_sw = float(p_sw)
    else:
        p_sw = float("nan")
    sk = skewness(a)
    autocorrelated = bool(not math.isnan(r1) and r1 > acf_threshold)
    non_normal = bool(not math.isnan(p_sw) and p_sw < 0.01)
    rec = "mr"
    if non_normal and abs(sk) > 1.0:
        rec = "robust"
    return {"acf1": r1, "ljung_box_q": q, "ljung_box_p": p_lb, "shapiro_p": p_sw,
            "skewness": sk, "autocorrelated": autocorrelated, "non_normal": non_normal,
            "sigma_recommended": rec, "n": int(a.size)}
