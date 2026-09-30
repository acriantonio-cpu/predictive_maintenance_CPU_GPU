# SPDX-License-Identifier: Apache-2.0
"""Carta degli individuali e dei range mobili (I-MR).

    MR_t = |X_t - X_{t-1}|,  sigma = MR_bar / d2,  d2 = 1.128
    LC = X_bar,  UCL/LCL = X_bar ± 3 * MR_bar / 1.128 = X_bar ± 2.66 * MR_bar
    UCL_MR = 3.267 * MR_bar (D4 per n = 2),  LCL_MR = 0

Variante robusta: sigma = mediana(MR) / 0.954, utile se in Fase I restano outlier.
Variante ``longterm``: deviazione standard campionaria, per serie autocorrelate
(sezione 7, controlli sui presupposti).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from numpy.typing import ArrayLike

D2 = 1.128  # costante d2 per sottogruppi di 2
D4 = 3.267  # costante D4 per sottogruppi di 2
MEDIAN_MR_FACTOR = 0.954  # mediana(MR) / sigma per dati normali


@dataclass(frozen=True)
class Limits:
    center: float
    sigma: float
    mr_bar: float
    ucl: float
    lcl: float
    ucl_mr: float
    method: str = "mr"
    widen: float = 1.0

    def to_dict(self) -> dict[str, float | str]:
        return asdict(self)

    def zone(self, k: float) -> tuple[float, float]:
        """Limiti a k sigma (es. 2 per le linee tratteggiate)."""
        s = self.sigma * self.widen
        return self.center - k * s, self.center + k * s


def moving_ranges(x: ArrayLike) -> np.ndarray:
    a = np.asarray(x, dtype=float)
    if a.size < 2:
        return np.empty(0)
    return np.abs(np.diff(a))


def imr_limits(x: ArrayLike, method: str = "mr", widen: float = 1.0) -> Limits:
    """Limiti I-MR da una serie di Fase I. ``widen`` > 1 per i limiti provvisori."""
    a = np.asarray(x, dtype=float)
    if a.size < 2:
        raise ValueError("servono almeno 2 osservazioni")
    mr = moving_ranges(a)
    mr_bar = float(mr.mean())
    if method == "robust":
        sigma = float(np.median(mr)) / MEDIAN_MR_FACTOR
    elif method == "mr":
        sigma = mr_bar / D2
    elif method == "longterm":
        # deviazione standard campionaria: con dati autocorrelati MR_bar/d2
        # sottostima la variabilità tra sessioni e produce limiti troppo stretti
        sigma = float(a.std(ddof=1))
    else:
        raise ValueError(f"metodo sigma sconosciuto: {method}")
    center = float(a.mean())
    s = sigma * widen
    return Limits(center=center, sigma=sigma, mr_bar=mr_bar, ucl=center + 3 * s,
                  lcl=center - 3 * s, ucl_mr=D4 * (sigma * D2) * widen, method=method,
                  widen=widen)


@dataclass(frozen=True)
class PhaseIResult:
    limits: Limits
    kept: np.ndarray  # maschera booleana dei punti tenuti
    excluded: list[int]  # indici rimossi (causa assegnabile)
    iterations: int


def phase_one(x: ArrayLike, method: str = "mr", max_iter: int = 3,
              widen: float = 1.0) -> PhaseIResult:
    """Fase I: calcola i limiti rimuovendo i punti oltre 3 sigma (massimo ``max_iter``
    iterazioni) e registra quali punti sono stati esclusi.

    I range mobili si ricalcolano sulla serie ridotta (i punti rimossi non entrano
    più nel calcolo di sigma).
    """
    a = np.asarray(x, dtype=float)
    keep = np.ones(a.size, dtype=bool)
    lim = imr_limits(a, method, widen)
    it = 0
    for it in range(1, max_iter + 1):
        out = keep & ((a > lim.ucl) | (a < lim.lcl))
        if not out.any() or (keep & ~out).sum() < max(10, a.size // 2):
            it -= 1
            break
        keep &= ~out
        lim = imr_limits(a[keep], method, widen)
    return PhaseIResult(lim, keep, [int(i) for i in np.flatnonzero(~keep)], max(it, 0))
