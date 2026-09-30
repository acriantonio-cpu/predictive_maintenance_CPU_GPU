# SPDX-License-Identifier: Apache-2.0
"""Indicatori per finestra: Rth, delta hotspot-edge, sforzo ventola, deriva idle.

    Rth = (T - T_rif) / P      [°C/W], nei regimi medio e alto

Nel regime idle Rth non è affidabile (dividere per una potenza piccola amplifica il
rumore): si usa la deriva della temperatura a riposo. Le finestre con throttling
sono escluse da Rth: con il clock in calo la potenza scende e Rth sembrerebbe buono
proprio mentre il raffreddamento sta fallendo (failure mode 5).
"""

from __future__ import annotations

from typing import Any


def window_indicators(suffix: str, regime: str, summary: dict[str, Any],
                      throttled: bool, has_ref: bool) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    t = summary.get("t")
    p = summary.get("p")
    tref = summary.get("tref") if has_ref else None
    if t is None or p is None:
        return out
    ref = tref if tref is not None else 0.0
    if throttled:
        return out  # alimentano solo l'indicatore di throttling
    if regime in ("medium", "high") and p > 0:
        out.append((f"rth_{suffix}", (t - ref) / p))
        hot = summary.get("hotspot")
        if hot is not None:
            out.append((f"hotspot_delta_{suffix}", hot - t))
        mb = summary.get("mb")
        if mb is not None and tref is not None and suffix == "cpu":
            out.append(("case_delta_cpu", mb - tref))
    if regime == "idle":
        out.append((f"idle_temp_{suffix}", t - ref))
        if tref is not None and suffix == "cpu":
            # riferimento ambiente misurato a riposo (meno contaminato dal calore interno)
            out.append(("ref_temp", tref))
    fan = summary.get("fan")
    if fan is not None and fan > 0:
        # molte GPU fermano le ventole a riposo: il valore 0 non è uno sforzo
        out.append((f"fan_effort_{suffix}", fan))
    return out
