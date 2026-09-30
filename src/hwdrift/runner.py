# SPDX-License-Identifier: Apache-2.0
"""Collector residente (``hwdrift run``).

Ciclo principale: a ogni tick interroga i collector, applica i controlli di
qualità, valuta gli errori immediati e accoda i campioni al writer, che scrive in
batch. Robustezza (sezione 4):

* orologio monotono per i tempi, UTC in millisecondi per il database;
* gap esplicito dopo sospensione/ibernazione (salto dell'orologio) e riavvio;
* un collector che fallisce non ferma gli altri: canale ``status.<nome>`` = 0,
  nuovi tentativi con backoff;
* modalità game-safe: sospende le sorgenti a basso livello se gira un processo
  in lista;
* auto-monitoraggio (CPU e RAM del processo) e intervallo adattivo.

Il modulo NON importa numpy/pandas (budget di memoria del collector).
"""

from __future__ import annotations

import contextlib
import json
import logging
import signal
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import psutil

from .collectors.base import Collector, CollectorUnavailable, build_collectors
from .config import data_dir
from .model import EventRecord, Quality, Sample
from .quality.realtime_events import RealtimeConfig, RealtimeDetector
from .quality.sanity import QualityChecker
from .storage.schema import get_meta, open_db, set_meta
from .storage.writer import BatchWriter

log = logging.getLogger(__name__)


@dataclass
class _CState:
    collector: Collector
    ok: bool = False
    started: bool = False
    next_poll: float = 0.0
    failures: int = 0
    last_error: str = ""
    poll_time_s: float = 0.0
    polls: int = 0
    suspended: bool = False


@dataclass
class Clock:
    """Orologio iniettabile: i test avanzano il tempo senza dormire."""

    monotonic: Callable[[], float] = time.monotonic
    wall_ms: Callable[[], int] = field(default=lambda: int(time.time() * 1000))
    sleep: Callable[[float], None] = time.sleep


class Runner:
    def __init__(self, cfg: dict[str, Any], conn: sqlite3.Connection,
                 collectors: list[Collector] | None = None, clock: Clock | None = None) -> None:
        self.cfg = cfg
        self.conn = conn
        self.clock = clock or Clock()
        smp = cfg["sampling"]
        self.base_interval = float(smp["interval_s"])
        self.interval = self.base_interval
        self.writer = BatchWriter(conn, smp["flush_s"], smp["raw_retention_h"])
        self.qc = QualityChecker()
        self.states = [_CState(c) for c in (collectors if collectors is not None
                                            else build_collectors(cfg))]
        self.rt_ids: dict[str, int] = {}
        self.detector = RealtimeDetector(RealtimeConfig.from_config(cfg), self._rt_sink) \
            if cfg["realtime"]["enabled"] else None
        self._stop = False
        self._proc = psutil.Process()
        self._proc.cpu_percent(None)
        self._last_selfmon = -1e9
        self._last_gamecheck = -1e9
        self._cpu_history: list[float] = []
        self.game_safe = False
        self._last_wall: int | None = None
        self._last_mono: float | None = None
        self.ticks = 0
        ddir = data_dir(cfg)
        self.hc_request = ddir / "healthcheck.active"
        self.live_request = ddir / "live.active"  # la GUI lo aggiorna ogni pochi secondi
        self.stop_request = ddir / "stop.request"
        self.live_path = ddir / "live.json"
        self._hc_active = False
        self._last_hc_check = -1e9

    # ------------------------------------------------------------ lifecycle
    def stop(self, *_: Any) -> None:
        self._stop = True

    def _start_collectors(self, now_mono: float) -> None:
        for st in self.states:
            if st.started or st.next_poll > now_mono:
                continue
            try:
                st.collector.start()
                st.started = True
                st.ok = True
                st.failures = 0
                log.info("collector %s avviato", st.collector.name)
            except CollectorUnavailable as exc:
                st.last_error = str(exc)
                st.failures += 1
                st.next_poll = now_mono + min(600.0, 30.0 * st.failures)
                log.warning("collector %s non disponibile: %s", st.collector.name, exc)
            except Exception as exc:
                st.last_error = repr(exc)
                st.failures += 1
                st.next_poll = now_mono + min(600.0, 30.0 * st.failures)
                log.exception("errore all'avvio del collector %s", st.collector.name)

    def _startup_events(self) -> None:
        now = self.clock.wall_ms()
        boot = int(psutil.boot_time() * 1000)
        prev_boot = get_meta(self.conn, "boot_ts")
        hb = get_meta(self.conn, "heartbeat_ts")
        if prev_boot is not None and abs(int(prev_boot) - boot) > 5000:
            self.writer.add_event(EventRecord(boot, "system.reboot"))
        if hb is not None and now - int(hb) > 3 * self.cfg["sampling"]["flush_s"] * 1000:
            self.writer.add_event(EventRecord(int(hb), "system.gap",
                                              detail={"end_ts": now, "reason": "collector fermo"}))
        # episodi lasciati "in corso" da un arresto brusco (spegnimento, crash, kill):
        # si chiudono all'ultimo istante in cui il collector era vivo
        last_alive = int(hb) if hb is not None else now
        with self.conn:
            self.conn.execute("UPDATE rt_events SET end_ts=MAX(start_ts, ?) WHERE end_ts IS NULL",
                              (min(last_alive, now),))
        self.writer.add_event(EventRecord(now, "system.collector_start",
                                          detail={"interval_s": self.interval}))
        with self.conn:
            set_meta(self.conn, "boot_ts", str(boot))

    # ------------------------------------------------------------- helpers
    def _rt_sink(self, action: str, ep: Any) -> None:
        detail = {"reason": ep.reason}
        if action == "open":
            self.rt_ids[ep.key] = self.writer.open_rt_event(
                ep.start_ts, ep.component, ep.reason, ep.severity, ep.peak, detail)
            log.warning("errore immediato: %s %s (%s)", ep.component, ep.reason, ep.severity)
        elif ep.key in self.rt_ids:
            rid = self.rt_ids[ep.key]
            if action == "escalate":
                self.writer.update_rt_event(rid, severity=ep.severity, peak=ep.peak)
            elif action == "peak":
                self.writer.update_rt_event(rid, peak=ep.peak)
            elif action == "close":
                self.writer.update_rt_event(rid, end_ts=self.clock.wall_ms())
                del self.rt_ids[ep.key]

    def _observe(self, ev: EventRecord) -> None:
        """Confronta un valore osservato con quello salvato; se cambia -> evento config."""
        key = f"observed.{ev.detail.get('key')}"
        value = str(ev.detail.get("value"))
        prev = get_meta(self.conn, key)
        if prev is not None and prev != value:
            self.writer.add_event(EventRecord(ev.ts_ms, str(ev.detail["config_kind"]),
                                              detail={"old": prev, "new": value,
                                                      "key": ev.detail.get("key")}))
        if prev != value:
            with self.conn:
                set_meta(self.conn, key, value)

    def _check_game_safe(self, mono: float) -> None:
        gs = self.cfg["game_safe"]
        if not gs["enabled"] or mono - self._last_gamecheck < gs["check_s"]:
            return
        self._last_gamecheck = mono
        names = {n.lower() for n in gs["processes"]}
        active = False
        try:
            for p in psutil.process_iter(["name"]):
                n = (p.info.get("name") or "").lower()
                if n in names:
                    active = True
                    break
        except psutil.Error:
            pass
        if active != self.game_safe:
            log.info("modalità game-safe %s", "attiva" if active else "disattivata")
        self.game_safe = active
        for st in self.states:
            st.suspended = active and st.collector.low_level

    def _selfmon(self, mono: float, ts: int) -> list[Sample]:
        smp = self.cfg["sampling"]
        if mono - self._last_selfmon < smp["selfmon_s"]:
            return []
        self._last_selfmon = mono
        cpu = self._proc.cpu_percent(None)
        rss = self._proc.memory_info().rss / 1e6
        self._cpu_history = ([*self._cpu_history, cpu])[-30:]
        if smp["adaptive"] and len(self._cpu_history) >= 6:
            avg = sum(self._cpu_history[-6:]) / 6
            if avg > smp["cpu_budget_pct"] and self.interval < 5.0:
                self.interval = min(5.0, self.interval * 1.5)
                log.warning("overhead %.2f%% > budget: intervallo portato a %.1f s", avg,
                            self.interval)
                self._cpu_history.clear()
            elif avg < smp["cpu_budget_pct"] / 3 and self.interval > self.base_interval:
                self.interval = max(self.base_interval, self.interval / 1.5)
        mk = lambda ch, v, u: Sample(ts, "hwdrift", ch, "self", ch, v, u, ch,  # noqa: E731
                                     mono_s=mono)
        return [mk("hwdrift.cpu_pct", cpu, "%"), mk("hwdrift.rss_mb", rss, "MB"),
                mk("hwdrift.interval_s", self.interval, "s"),
                mk("hwdrift.game_safe", 1.0 if self.game_safe else 0.0, "flag")]

    def _publish_live(self, latest: dict[str, float], mono: float, ts: int) -> None:
        """Pubblica gli ultimi valori in ``live.json`` solo quando serve: durante un
        health-check (lettura di sicurezza) o finché una GUI li sta guardando (il suo file
        ``live.active`` è stato toccato negli ultimi 10 s). Controlla anche la richiesta di
        arresto pulito (``stop.request``)."""
        if mono - self._last_hc_check >= 2.0:
            self._last_hc_check = mono
            wanted = self.hc_request.exists()
            with contextlib.suppress(OSError):
                wanted = wanted or time.time() - self.live_request.stat().st_mtime < 10.0
            self._hc_active = wanted
            if self.stop_request.exists():
                with contextlib.suppress(OSError):
                    self.stop_request.unlink()
                log.info("arresto richiesto (stop.request)")
                self._stop = True
        if not self._hc_active:
            return
        try:
            tmp = self.live_path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"ts": ts, "values": latest}), encoding="utf-8")
            tmp.replace(self.live_path)
        except OSError:
            log.debug("live.json non scrivibile", exc_info=True)

    # ----------------------------------------------------------------- tick
    def tick(self) -> None:
        mono = self.clock.monotonic()
        ts = self.clock.wall_ms()
        # sospensione/ibernazione: l'orologio di parete salta più del monotono
        if self._last_wall is not None and self._last_mono is not None:
            wall_dt = (ts - self._last_wall) / 1000.0
            mono_dt = mono - self._last_mono
            # su Windows time.monotonic include il tempo di sospensione: serve anche la
            # soglia assoluta, alta abbastanza da non scattare per una lettura lenta
            if wall_dt - mono_dt > 30 or wall_dt > max(90.0, 10 * self.interval):
                self.writer.add_event(EventRecord(self._last_wall, "system.gap",
                                                  detail={"end_ts": ts, "reason": "sospensione"}))
                if self.detector is not None:
                    self.detector.close_all()
        self._last_wall, self._last_mono = ts, mono
        self._start_collectors(mono)
        self._check_game_safe(mono)
        batch: list[Sample] = []
        for st in self.states:
            c = st.collector
            if not st.started or st.suspended or mono < st.next_poll:
                continue
            t0 = time.perf_counter()
            try:
                samples = c.poll(ts, mono)
                ok = True
            except Exception as exc:
                samples = []
                ok = False
                st.failures += 1
                st.last_error = repr(exc)[:300]
                if st.failures in (1, 10) or st.failures % 100 == 0:
                    log.error("collector %s: %s (errori consecutivi: %d)", c.name, exc,
                              st.failures)
            st.poll_time_s += time.perf_counter() - t0
            st.polls += 1
            if ok:
                st.failures = 0
            st.ok = ok
            backoff = min(300.0, 2.0 ** min(st.failures, 8)) if not ok else 0.0
            st.next_poll = mono + max(c.interval_s, backoff)
            batch.extend(samples)
            batch.append(Sample(ts, "hwdrift", f"status/{c.name}", "self", f"status {c.name}",
                                1.0 if ok else 0.0, "flag", f"status.{c.name}", mono_s=mono))
            for ev in c.drain_events():
                if ev.kind == "observe":
                    self._observe(ev)
                else:
                    self.writer.add_event(ev)
        batch.extend(self._selfmon(mono, ts))
        latest: dict[str, float] = {}
        for s in batch:
            self.qc.check(s)
            if s.quality == Quality.OK and s.channel is not None and s.value is not None:
                latest[s.channel] = s.value
        if self.detector is not None:
            self.detector.update(latest, mono, ts)
        self._publish_live(latest, mono, ts)
        self.writer.add(batch)
        if self.writer.due(ts):
            self.writer.flush(ts)
            self._save_status()
        self.ticks += 1

    def run(self, max_ticks: int | None = None, install_signals: bool = True) -> None:
        if install_signals:
            signal.signal(signal.SIGINT, self.stop)
            with contextlib.suppress(ValueError, OSError):
                signal.signal(signal.SIGTERM, self.stop)
        self._startup_events()
        next_t = self.clock.monotonic()
        try:
            while not self._stop and (max_ticks is None or self.ticks < max_ticks):
                self.tick()
                next_t += self.interval
                delay = next_t - self.clock.monotonic()
                if delay > 0:
                    self.clock.sleep(delay)
                else:
                    next_t = self.clock.monotonic()  # in ritardo: non accumulare
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        if self.detector is not None:
            self.detector.close_all()
        try:
            self.writer.flush(self.clock.wall_ms(), final=True)
            self._save_status()
        finally:
            for st in self.states:
                if st.started:
                    try:
                        st.collector.close()
                    except Exception:
                        log.exception("chiusura collector %s", st.collector.name)

    def _save_status(self) -> None:
        """Stato delle sorgenti (anche quelle mai partite, es. LHM non avviato)."""
        try:
            with self.conn:
                set_meta(self.conn, "collectors_status", json.dumps(self.status()))
        except sqlite3.Error:
            log.debug("stato delle sorgenti non salvato", exc_info=True)

    def status(self) -> list[dict[str, Any]]:
        return [{"name": s.collector.name, "started": s.started, "ok": s.ok,
                 "failures": s.failures, "last_error": s.last_error, "polls": s.polls,
                 "avg_poll_ms": 1000 * s.poll_time_s / s.polls if s.polls else None,
                 "suspended": s.suspended} for s in self.states]


def run_collector(cfg: dict[str, Any], db: str, max_ticks: int | None = None) -> Runner:
    conn = open_db(db)
    r = Runner(cfg, conn)
    r.run(max_ticks=max_ticks)
    return r
