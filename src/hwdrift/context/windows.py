# SPDX-License-Identifier: Apache-2.0
"""Finestre stazionarie (sezione 6).

Le carte non ricevono mai la temperatura grezza: ricevono indicatori calcolati
solo in condizioni di carico stabile. Una finestra di ``length_min`` minuti è
valida se:

* coefficiente di variazione della potenza < ``power_cv_max``;
* |pendenza della temperatura| < ``temp_slope_max`` °C/min (niente transitori);
* il carico è iniziato da almeno ``warmup_min`` minuti (riscaldamento);
* utilizzo stabile (deviazione standard < ``util_std_max`` punti);
* nessun gap, nessun campione di qualità scarsa, nessun evento di configurazione;
* throttling: la finestra NON si scarta ma viene marcata ``throttled`` e alimenta
  l'indicatore di throttling, mentre è esclusa dal calcolo di Rth (failure mode 5).
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .components import Component
from .minutes import MinuteFrame

MIN_MS = 60_000


@dataclass
class Window:
    component: str
    start_ts: int
    end_ts: int
    power_mean: float
    power_cv: float
    temp_slope: float
    throttled: bool
    summary: dict[str, Any] = field(default_factory=dict)


def _mean(a: np.ndarray) -> float | None:
    a = a[np.isfinite(a)]
    return float(a.mean()) if a.size else None


def find_windows(mf: MinuteFrame, comp: Component, params: dict[str, Any],
                 confounders: list[int], ref: np.ndarray | None,
                 start_from: int | None = None) -> list[Window]:
    """Cerca finestre stazionarie non sovrapposte a partire da ``start_from``."""
    W = int(params["length_min"])
    warm = int(params["warmup_min"])
    cv_max = float(params["power_cv_max"])
    slope_max = float(params["temp_slope_max"])
    util_std_max = float(params["util_std_max"])
    min_valid = float(params["min_valid_frac"])
    min_power = float(params["min_power_w"])

    ts = mf.ts
    n = ts.size
    P = mf.get(comp.power)
    T = mf.get(comp.temp)
    vP = mf.valid.get(comp.power, np.zeros(n))
    vT = mf.valid.get(comp.temp, np.zeros(n))
    U = mf.get(comp.util) if mf.has(comp.util) else None
    thr = np.zeros(n)
    for ch in (comp.throttle_thermal, comp.throttle_power):
        if ch in mf.max:
            thr_ch = np.nan_to_num(mf.max[ch], nan=0.0)
            weight = 2.0 if ch == comp.throttle_thermal else 1.0  # 2 = termico, 1 = potenza
            thr = np.maximum(thr, weight * (thr_ch >= 0.5))
    fan_ch = next((f for f in comp.fans if mf.has(f)), None)
    hot = mf.get(comp.hotspot) if comp.hotspot and mf.has(comp.hotspot) else None
    x = np.arange(W, dtype=float)
    out: list[Window] = []
    i = warm
    if start_from is not None:
        i = max(i, int(np.searchsorted(ts, start_from)))
    while i + W <= n:
        j = i + W
        a = i - warm
        # contiguità: niente minuti mancanti tra riscaldamento e fine finestra
        if ts[j - 1] - ts[a] != (j - 1 - a) * MIN_MS:
            i += 1
            continue
        pw = P[i:j]
        tw = T[i:j]
        if (not np.isfinite(pw).all() or not np.isfinite(tw).all()
                or (vP[a:j] < min_valid).any() or (vT[i:j] < min_valid).any()):
            i += 1
            continue
        pm = float(pw.mean())
        if pm < min_power:
            i += 1
            continue
        cv = float(pw.std(ddof=1) / pm) if W > 1 else 0.0
        if cv >= cv_max:
            i += 1
            continue
        pwarm = P[a:i]
        if not np.isfinite(pwarm).all() or (np.abs(pwarm - pm) / pm > 2 * cv_max).any():
            i += 1
            continue
        slope = float(np.polyfit(x, tw, 1)[0])
        if abs(slope) >= slope_max:
            i += 1
            continue
        if U is not None:
            uw = U[i:j]
            if np.isfinite(uw).all() and uw.std(ddof=1) > util_std_max:
                i += 1
                continue
        start, end = int(ts[i]), int(ts[j - 1]) + MIN_MS
        k = bisect.bisect_left(confounders, int(ts[a]))
        if k < len(confounders) and confounders[k] <= end:
            i += 1
            continue
        tmax = float(thr[i:j].max())
        summary: dict[str, Any] = {
            "t": float(tw.mean()), "p": pm,
            "throttle_thermal": bool(tmax >= 2), "throttle_power": bool(tmax == 1),
        }
        if U is not None:
            summary["util"] = _mean(U[i:j])
        if fan_ch is not None:
            summary["fan"] = _mean(mf.get(fan_ch)[i:j])
            summary["fan_kind"] = "pct" if fan_ch.endswith("_pct") else "rpm"
        if hot is not None:
            summary["hotspot"] = _mean(hot[i:j])
        if ref is not None:
            summary["tref"] = _mean(ref[i:j])
        if mf.has("mb.temp_c"):
            summary["mb"] = _mean(mf.get("mb.temp_c")[i:j])
        out.append(Window(comp.key, start, end, pm, cv, slope, tmax >= 1, summary))
        i = j  # finestre non sovrapposte: riduce l'autocorrelazione
    return out
