# SPDX-License-Identifier: Apache-2.0
"""Regole di segnale (sezione 7).

* R1: un punto oltre 3 sigma.
* R2: nove punti consecutivi dallo stesso lato della linea centrale.
* R3: sei punti consecutivi in salita (o in discesa).
* R4 (opzionale): due punti su tre oltre 2 sigma dallo stesso lato.
* MR: range mobile oltre UCL_MR (gradino improvviso).

Ogni segnale riporta l'indice del punto in cui la regola scatta, il lato e gli
indici dei punti coinvolti. Le regole si applicano alla serie passata (tipicamente
la Fase II); gli indici sono relativi a quella serie.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike

from .imr import Limits


@dataclass(frozen=True)
class Signal:
    index: int
    rule: str
    side: str  # "upper" | "lower"
    points: tuple[int, ...]


def evaluate(x: ArrayLike, lim: Limits, rules: tuple[str, ...] | list[str] = ("R1", "R2", "R3"),
             r2_run: int = 9, r3_run: int = 6, include_mr: bool = True) -> list[Signal]:
    a = np.asarray(x, dtype=float)
    n = a.size
    out: list[Signal] = []
    if n == 0:
        return out
    s = lim.sigma * lim.widen
    c = lim.center
    if "R1" in rules:
        for i in np.flatnonzero(a > c + 3 * s):
            out.append(Signal(int(i), "R1", "upper", (int(i),)))
        for i in np.flatnonzero(a < c - 3 * s):
            out.append(Signal(int(i), "R1", "lower", (int(i),)))
    if "R2" in rules:
        side = np.sign(a - c)
        run = 0
        for i in range(n):
            if i > 0 and side[i] != 0 and side[i] == side[i - 1]:
                run += 1
            else:
                run = 1 if side[i] != 0 else 0
            if run >= r2_run:
                pts = tuple(range(i - r2_run + 1, i + 1))
                out.append(Signal(i, "R2", "upper" if side[i] > 0 else "lower", pts))
    if "R3" in rules:
        d = np.sign(np.diff(a))
        run = 0
        for i in range(1, n):
            if i > 1 and d[i - 1] != 0 and d[i - 1] == d[i - 2]:
                run += 1
            else:
                run = 1 if d[i - 1] != 0 else 0
            if run >= r3_run - 1:  # r3_run punti = r3_run - 1 incrementi
                pts = tuple(range(i - r3_run + 1, i + 1))
                out.append(Signal(i, "R3", "upper" if d[i - 1] > 0 else "lower", pts))
    if "R4" in rules:
        for i in range(2, n):
            w = a[i - 2:i + 1]
            for sign, name in ((1, "upper"), (-1, "lower")):
                beyond = (sign * (w - c) > 2 * s)
                if beyond.sum() >= 2 and beyond[-1]:
                    pts = tuple(i - 2 + int(j) for j in np.flatnonzero(beyond))
                    out.append(Signal(i, "R4", name, pts))
    if include_mr and n >= 2:
        mr = np.abs(np.diff(a))
        for j in np.flatnonzero(mr > lim.ucl_mr):
            i = int(j) + 1
            out.append(Signal(i, "MR", "upper" if a[i] > a[i - 1] else "lower", (i - 1, i)))
    out.sort(key=lambda z: (z.index, z.rule))
    return out


def false_alarm_arl_r1() -> float:
    """ARL0 teorico della sola R1 su dati normali indipendenti (~370)."""
    from math import erf, sqrt

    p = 1 - erf(3 / sqrt(2))
    return 1 / p
