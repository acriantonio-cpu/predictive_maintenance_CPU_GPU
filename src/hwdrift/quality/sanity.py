# SPDX-License-Identifier: Apache-2.0
"""Controlli di plausibilità per campione (failure mode 7).

Per ogni canale canonico: range fisico, valori tipici di lettura fallita,
variazione massima plausibile per secondo e rilevamento dei valori congelati.
Il campione non viene scartato: riceve un flag di qualità, così l'esclusione è
registrata e verificabile.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..channels import spec_for
from ..model import Quality, Sample


@dataclass
class _ChannelState:
    last_value: float | None = None
    last_mono: float | None = None
    same_since: float | None = None  # istante monotono da cui il valore è identico


class QualityChecker:
    def __init__(self, frozen_override_s: dict[str, float] | None = None) -> None:
        self._state: dict[str, _ChannelState] = {}
        self._frozen_override = frozen_override_s or {}
        self.counts: dict[Quality, int] = {q: 0 for q in Quality}

    def check(self, s: Sample) -> Sample:
        if s.channel is None:
            s.quality = Quality.UNMAPPED
            return s
        s.quality = self._evaluate(s)
        self.counts[s.quality] += 1
        return s

    def _evaluate(self, s: Sample) -> Quality:
        v = s.value
        st = self._state.setdefault(s.channel or "", _ChannelState())
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return Quality.MISSING
        spec = spec_for(s.channel or "")
        if spec is None:
            return Quality.OK
        q = Quality.OK
        if spec.glitch_values and v in spec.glitch_values:
            q = Quality.GLITCH
        elif not spec.lo <= v <= spec.hi:
            q = Quality.OUT_OF_RANGE
        elif (spec.max_rate is not None and st.last_value is not None
              and st.last_mono is not None and s.mono_s > st.last_mono):
            dt = s.mono_s - st.last_mono
            if abs(v - st.last_value) > spec.max_rate * max(dt, 1.0):
                q = Quality.GLITCH
        # Rilevamento dei valori congelati: valore identico per più di freeze_s.
        freeze_s = self._frozen_override.get(s.channel or "", spec.freeze_s)
        if st.last_value is not None and v == st.last_value:
            if st.same_since is None:
                st.same_since = st.last_mono if st.last_mono is not None else s.mono_s
            if (q == Quality.OK and freeze_s is not None
                    and s.mono_s - st.same_since >= freeze_s):
                q = Quality.FROZEN
        else:
            st.same_since = None
        if q in (Quality.OK, Quality.FROZEN):
            # i glitch non aggiornano il riferimento, altrimenti il salto di ritorno
            # verrebbe a sua volta marcato come glitch
            st.last_value = v
            st.last_mono = s.mono_s
        return q
