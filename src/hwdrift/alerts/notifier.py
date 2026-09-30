# SPDX-License-Identifier: Apache-2.0
"""Notificatore non privilegiato (``hwdrift notify``).

Gira nella sessione dell'utente, senza privilegi elevati, e apre il database in
SOLA LETTURA. Il suo stato (cosa è già stato notificato) sta in un piccolo file
JSON separato, così non scrive mai nel database del collector.

Notifica:

* errori immediati (``rt_events``): all'apertura dell'episodio e se la gravità
  peggiora;
* allarmi di livello attenzione o azione: alla comparsa e se il livello sale;
* collector fermo: se il notificatore gira (quindi il PC è acceso) ma l'heartbeat
  del collector è vecchio, o se una sorgente è in errore.

Scrive inoltre ``status.json``: l'indicatore di stato persistente, perché il toast
può essere soppresso da Focus Assist o da un gioco a schermo intero.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..model import now_ms
from ..quality import watchdog
from ..storage.schema import connect, get_meta
from . import toast

log = logging.getLogger(__name__)

SEV_RANK = {"info": 0, "warning": 1, "error": 2}
LVL_RANK = {"info": 0, "attention": 1, "action": 2}
COMP_LABEL = {"cpu": "CPU", "gpu0": "GPU"}
REASON = {"thermal": "throttling termico", "power_limit": "limite di potenza",
          "fan_stopped": "ventola ferma con temperatura alta"}


def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    tmp.replace(path)


class Notifier:
    def __init__(self, db: Path, state_dir: Path, cfg: dict[str, Any],
                 show: Callable[[str, str], bool] = toast.show) -> None:
        self.db = db
        self.cfg = cfg
        self.state_path = state_dir / "notifier_state.json"
        self.status_path = state_dir / "status.json"
        self.state = _load(self.state_path)
        self.state.setdefault("rt", {})
        self.state.setdefault("alerts", {})
        self.show = show
        self.sent: list[tuple[str, str]] = []

    def _notify(self, title: str, body: str) -> None:
        self.sent.append((title, body))
        if self.cfg["alerts"]["toast"]:
            ok = self.show(title, body)
            if not ok:
                log.info("notifica (non mostrata): %s — %s", title, body)
        log.warning("NOTIFICA: %s — %s", title, body)

    def check(self, now: int | None = None) -> dict[str, Any]:
        now = now if now is not None else now_ms()
        try:
            conn = connect(self.db, readonly=True)
        except sqlite3.OperationalError as exc:
            return {"error": f"database non leggibile: {exc}"}
        try:
            status = self._check(conn, now)
        finally:
            conn.close()
        _save(self.state_path, self.state)
        _save(self.status_path, status)
        return status

    def _check(self, conn: sqlite3.Connection, now: int) -> dict[str, Any]:
        status: dict[str, Any] = {"ts": now, "ongoing": [], "alerts": [], "collector": "ok"}
        # ---- errori immediati
        for rid, start, end, comp, reason, sev, peak in conn.execute(
                "SELECT id, start_ts, end_ts, component, reason, severity, peak FROM rt_events "
                "WHERE start_ts >= ? ORDER BY start_ts", (now - 7 * 86_400_000,)):
            key = str(rid)
            prev = self.state["rt"].get(key)
            label = f"{COMP_LABEL.get(comp, comp.upper())}: {REASON.get(reason, reason)}"
            if end is None:
                status["ongoing"].append({"component": comp, "reason": reason, "severity": sev,
                                          "since": start, "peak": peak})
            if sev == "info":
                continue  # il limite di potenza è spesso voluto: solo nel report
            if prev is None or SEV_RANK[sev] > SEV_RANK.get(prev, -1):
                body = ("Errore immediato: intervenire se si ripete. " if sev == "error"
                        else "Attenzione: normale su un portatile o in una stanza calda. ")
                if peak is not None:
                    body += f"Picco {peak:.0f}."
                self._notify(f"HWDrift — {label}", body)
                self.state["rt"][key] = sev
        # ---- allarmi di analisi
        budget = get_meta(conn, "alert_budget_exceeded") == "1"
        for key, level, title, message in conn.execute(
                "SELECT key, level, title, message FROM alerts WHERE active=1"):
            status["alerts"].append({"key": key, "level": level, "title": title})
            if LVL_RANK[level] < 1:
                continue
            if budget and level == "action" and not key.startswith("fatal:"):
                continue  # budget superato: suggerire di rivedere le soglie, non notificare
            prev = self.state["alerts"].get(key)
            if prev is None or LVL_RANK[level] > LVL_RANK.get(prev, -1):
                self._notify(f"HWDrift — {title}", message)
            self.state["alerts"][key] = level
        # ---- watchdog del collector
        h = watchdog.check(conn, self.cfg["alerts"]["stale_heartbeat_min"], now)
        if h.heartbeat_ts is None:
            status["collector"] = "mai avviato"
        elif h.stale_min:
            status["collector"] = f"nessun dato da {h.stale_min:.0f} minuti"
            last = self.state.get("stale_notified")
            if last is None or last < h.heartbeat_ts:
                self._notify("HWDrift — collector fermo",
                             f"Nessun dato da {h.stale_min:.0f} minuti: lo stato di salute non è "
                             "aggiornato. Controllare l'attività pianificata del collector.")
                self.state["stale_notified"] = h.heartbeat_ts
        if h.failing_collectors:
            status["failing"] = h.failing_collectors
            key = ",".join(h.failing_collectors)
            if self.state.get("failing_notified") != key:
                self._notify("HWDrift — sorgente in errore",
                             f"Sorgenti non funzionanti: {key}. Alcuni indicatori mancano.")
                self.state["failing_notified"] = key
        elif "failing_notified" in self.state:
            del self.state["failing_notified"]
        return status

    def loop(self, interval_s: float = 5.0) -> None:
        while True:
            try:
                self.check()
            except Exception:
                log.exception("errore del notificatore")
            time.sleep(interval_s)
