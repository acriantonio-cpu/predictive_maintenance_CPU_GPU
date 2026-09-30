# SPDX-License-Identifier: Apache-2.0
"""Health-check attivo opzionale (``hwdrift healthcheck``, sezione 6).

Applica, solo su richiesta esplicita, un carico CPU breve e ripetibile, così
anche chi non visita mai il regime alto ottiene finestre stazionarie confrontabili
nel tempo. Interruzione di sicurezza: se la temperatura CPU supera la soglia, se
compare throttling o se i dati del collector smettono di arrivare, il carico si
ferma subito.

Il health-check NON legge i sensori direttamente (eviterebbe conflitti di accesso
con il collector): crea il file ``healthcheck.active`` nella cartella dati e il
collector, finché il file esiste, pubblica a ogni ciclo gli ultimi valori in
``live.json``. Il collector deve quindi essere in esecuzione.
TODO(M2): definire carico di riferimento, durata e soglia (questione aperta).
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .model import EventRecord, now_ms


def _burn(stop: mp.synchronize.Event) -> None:  # type: ignore[name-defined]
    x = 0.0
    while not stop.is_set():
        for i in range(20000):
            x += (i * 1.000001) ** 0.5
    _ = x


@dataclass
class HealthcheckResult:
    completed: bool
    reason: str
    duration_s: float
    max_temp: float | None


def read_live(live_path: Path, channel: str, max_age_s: float = 5.0) -> float | None:
    """Ultimo valore di ``channel`` pubblicato dal collector, se abbastanza recente."""
    try:
        data = json.loads(live_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or (now_ms() - int(data.get("ts", 0))) / 1000 > max_age_s:
        return None
    v = data.get("values", {}).get(channel)
    return float(v) if isinstance(v, (int, float)) else None


def run_healthcheck(read_temp: Callable[[], float | None], read_throttle: Callable[[], bool],
                    duration_s: float, abort_temp_c: float, workers: int = 0,
                    poll_s: float = 1.0, stale_limit_s: float = 90.0) -> HealthcheckResult:
    n = workers or max(1, (os.cpu_count() or 2) - 1)
    stop = mp.Event()
    procs = [mp.Process(target=_burn, args=(stop,), daemon=True) for _ in range(n)]
    t0 = time.monotonic()
    tmax: float | None = None
    last_ok = t0
    reason = "completato"
    completed = True
    for p in procs:
        p.start()
    try:
        while time.monotonic() - t0 < duration_s:
            time.sleep(poll_s)
            t = read_temp()
            if t is not None:
                last_ok = time.monotonic()
                tmax = t if tmax is None else max(tmax, t)
                if t >= abort_temp_c:
                    reason, completed = f"interrotto: temperatura {t:.1f} °C >= soglia", False
                    break
            elif time.monotonic() - last_ok > stale_limit_s:
                reason, completed = "interrotto: nessun dato recente dal collector", False
                break
            if read_throttle():
                reason, completed = "interrotto: throttling rilevato", False
                break
    except KeyboardInterrupt:
        reason, completed = "interrotto dall'utente", False
    finally:
        stop.set()
        for p in procs:
            p.join(timeout=5)
            if p.is_alive():
                p.terminate()
    return HealthcheckResult(completed, reason, time.monotonic() - t0, tmax)


def healthcheck_event(res: HealthcheckResult, start_ms: int) -> EventRecord:
    return EventRecord(start_ms, "system.healthcheck",
                       detail={"completed": res.completed, "reason": res.reason,
                               "duration_s": round(res.duration_s, 1), "max_temp": res.max_temp})
