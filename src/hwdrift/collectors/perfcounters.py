# SPDX-License-Identifier: Apache-2.0
"""Contatori di prestazione di Windows: utilizzo e frequenza effettiva della CPU.

Il clock effettivo rispetto al nominale serve a rilevare il throttling.
``\\Processor Information(_Total)\\% Processor Performance`` è la frequenza
effettiva in percentuale della nominale; ``Processor Frequency`` è la nominale.
TODO(M0): confrontare con il clock effettivo di HWiNFO sulle macchine di prova.
"""

from __future__ import annotations

import sys
from typing import Any

from ..model import Sample
from .base import Collector, CollectorUnavailable

PERF = r"\Processor Information(_Total)\% Processor Performance"
FREQ = r"\Processor Information(_Total)\Processor Frequency"
UTIL = r"\Processor Information(_Total)\% Processor Utility"


class PerfCounterCollector(Collector):
    name = "perfcounters"
    pdh: Any = None
    query: Any = None
    c_perf: Any = None
    c_freq: Any = None
    c_util: Any = None

    def start(self) -> None:
        if sys.platform != "win32":
            raise CollectorUnavailable("contatori di prestazione disponibili solo su Windows")
        try:
            import win32pdh  # type: ignore[import-not-found]
        except ImportError as exc:
            raise CollectorUnavailable("pywin32 non installato") from exc
        self.pdh: Any = win32pdh
        self.query = win32pdh.OpenQuery()
        self.c_perf = win32pdh.AddEnglishCounter(self.query, PERF)
        self.c_freq = win32pdh.AddEnglishCounter(self.query, FREQ)
        try:
            self.c_util = win32pdh.AddEnglishCounter(self.query, UTIL)
        except Exception:
            self.c_util = None
        win32pdh.CollectQueryData(self.query)  # i contatori % richiedono due letture

    def _val(self, counter: Any) -> float | None:
        try:
            _, v = self.pdh.GetFormattedCounterValue(counter, self.pdh.PDH_FMT_DOUBLE)
            return float(v)
        except Exception:
            return None

    def poll(self, ts_ms: int, mono_s: float) -> list[Sample]:
        self.pdh.CollectQueryData(self.query)
        perf = self._val(self.c_perf)
        freq = self._val(self.c_freq)
        out = [Sample(ts_ms, self.name, "pdh/frequency", "cpu", "Processor Frequency", freq,
                      "MHz", "cpu.clock_nominal_mhz", mono_s=mono_s)]
        eff = perf * freq / 100.0 if perf is not None and freq is not None else None
        out.append(Sample(ts_ms, self.name, "pdh/effective", "cpu", "% Processor Performance",
                          eff, "MHz", "cpu.clock_eff_mhz", mono_s=mono_s))
        if self.c_util is not None:
            util = self._val(self.c_util)
            out.append(Sample(ts_ms, self.name, "pdh/utility", "cpu", "% Processor Utility",
                              None if util is None else min(util, 100.0), "%",
                              "cpu.load_pct", mono_s=mono_s))
        return out

    def close(self) -> None:
        q = getattr(self, "query", None)
        if q is not None:
            self.pdh.CloseQuery(q)
