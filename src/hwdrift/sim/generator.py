# SPDX-License-Identifier: Apache-2.0
"""Generatore offline: scrive settimane di dati sintetici in pochi secondi.

Produce direttamente gli aggregati a 1 minuto (come farebbe il writer) e gli
eventi dello scenario (cambio driver, pulizia, errori WHEA), così la pipeline di
analisi si può provare e testare senza hardware e senza aspettare giorni.
"""

from __future__ import annotations

import random
import sqlite3
from dataclasses import dataclass

from ..channels import spec_for
from ..model import EventRecord, Sample
from ..quality.sanity import QualityChecker
from ..storage.schema import set_meta
from ..storage.writer import write_minute_aggregates
from .model import Machine, MachineParams, Workload
from .scenarios import SCENARIOS

DAY_S = 86_400.0


@dataclass
class GenResult:
    minutes: int
    events: int
    start_ms: int
    end_ms: int


def generate(conn: sqlite3.Connection, scenario: str = "healthy", days: float = 30.0,
             seed: int = 1, start_ms: int = 1_767_225_600_000, dt_s: float = 30.0,
             params: MachineParams | None = None) -> GenResult:
    """Genera ``days`` giorni dello ``scenario`` a partire da ``start_ms`` (UTC).

    Il default di ``start_ms`` è 2026-01-01T00:00Z; i giorni dello scenario
    (``onset_day``) si contano da lì.
    """
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario sconosciuto: {scenario} (disponibili: {sorted(SCENARIOS)})")
    faults = SCENARIOS[scenario]
    params = params or MachineParams()
    machine = Machine(params=params, faults=faults, seed=seed)
    work = Workload(seed=seed)
    qc = QualityChecker()
    rng = random.Random(seed + 101)
    minutes = 0
    events: list[EventRecord] = []
    t = 0.0
    total_s = days * DAY_S
    was_on = False
    chunk: list[Sample] = []
    last_day = -1
    while t < total_s:
        day = t / DAY_S
        on = work.is_on(t)
        ts = start_ms + int(t * 1000)
        if on and not was_on:
            events.append(EventRecord(ts, "system.reboot", detail={"sim": True}))
        was_on = on
        if int(day) != last_day:
            last_day = int(day)
            events.extend(_daily_events(faults, last_day, start_ms, rng))
        if not on:
            t += dt_s
            continue
        p_cpu, p_gpu = work.target(t, params)
        readings = machine.step(dt_s, day, p_cpu, p_gpu)
        for ch, val in readings.items():
            s = Sample(ts_ms=ts, source="simulator", sensor_id=ch, hw_type="sim",
                       raw_name=ch, value=float(val), unit=_unit(ch), channel=ch, mono_s=t)
            chunk.append(qc.check(s))
        if len(chunk) > 200_000:
            minutes += write_minute_aggregates(conn, chunk)
            chunk.clear()
        t += dt_s
    if chunk:
        minutes += write_minute_aggregates(conn, chunk)
    with conn:
        for ev in events:
            conn.execute(
                "INSERT INTO events(ts, kind, source, detail, note, ext_id) VALUES (?,?,?,?,?,?)",
                (ev.ts_ms, ev.kind, ev.source, _json(ev.detail), ev.note, ev.ext_id),
            )
        set_meta(conn, "heartbeat_ts", str(start_ms + int(total_s * 1000)))
        set_meta(conn, "sim_scenario", scenario)
    return GenResult(minutes, len(events), start_ms, start_ms + int(total_s * 1000))


def _unit(ch: str) -> str:
    spec = spec_for(ch)
    return spec.unit if spec else ""


def _daily_events(faults, day: int, start_ms: int, rng: random.Random) -> list[EventRecord]:
    out: list[EventRecord] = []
    base = start_ms + day * int(DAY_S * 1000)
    noon = base + 12 * 3_600_000
    for f in faults:
        if f.kind == "driver_change" and day == int(f.onset_day):
            out.append(EventRecord(base + int((f.onset_day % 1) * DAY_S * 1000) + 1,
                                   "config.driver",
                                   detail={"component": "gpu0", "old": "555.10", "new": "560.20"}))
        if f.kind == "clean" and day == int(f.onset_day):
            out.append(EventRecord(base + 1, "maintenance.clean", source="user",
                                   note="pulizia (simulata)"))
        if f.kind == "power_limit_gpu" and day == int(f.onset_day):
            out.append(EventRecord(base + 1, "config.profile",
                                   detail={"component": "gpu0", "power_limit": f.severity}))
        if f.kind == "whea" and day >= f.onset_day:
            k = _poisson(rng, f.rate)
            for i in range(k):
                out.append(EventRecord(noon + i * 60_000, "hw.whea_corrected",
                                       detail={"event_id": 19, "sim": True},
                                       ext_id=f"sim-{day}-{i}"))
    return out


def _poisson(rng: random.Random, lam: float) -> int:
    # algoritmo di Knuth: lam è piccolo (pochi eventi al giorno)
    import math

    limit = math.exp(-lam)
    k, p = 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def _json(d: dict) -> str:
    import json

    return json.dumps(d)
