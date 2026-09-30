# SPDX-License-Identifier: Apache-2.0
"""Unico scrittore del database durante la raccolta (sezione 5).

* I campioni restano in memoria e si scrivono in batch (default ogni 60 s) in
  un'unica transazione.
* A ogni flush i minuti completi vengono aggregati in ``agg_1min`` (mediana, min,
  max, n, frazione valida): gli aggregati sono permanenti, il grezzo ha ritenzione
  breve (48 h) e viene potato periodicamente.
* Gli errori immediati (``rt_events``) si scrivono subito, senza attendere il batch,
  perché il notificatore deve mostrarli entro pochi secondi.

Non importa numpy/pandas: gira nel collector residente.
"""

from __future__ import annotations

import json
import sqlite3
import statistics
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from ..model import EventRecord, Quality, Sample
from .schema import ensure_channel, set_meta

MINUTE_MS = 60_000


def minute_of(ts_ms: int) -> int:
    return ts_ms - (ts_ms % MINUTE_MS)


def aggregate(values: list[tuple[float | None, int]]) -> tuple[float | None, float | None,
                                                               float | None, int, float]:
    """Aggrega i campioni di un minuto: (mediana, min, max, n, frazione valida).

    Solo i campioni con qualità OK entrano in mediana/min/max; ``n`` conta tutti i
    campioni, così la frazione valida documenta quanti ne sono stati esclusi.
    """
    n = len(values)
    good = [v for v, q in values if q == Quality.OK and v is not None]
    if not good:
        return None, None, None, n, 0.0
    return statistics.median(good), min(good), max(good), n, len(good) / n if n else 0.0


class BatchWriter:
    def __init__(self, conn: sqlite3.Connection, flush_s: float = 60.0,
                 raw_retention_h: float = 48.0) -> None:
        self.conn = conn
        self.flush_ms = int(flush_s * 1000)
        self.retention_ms = int(raw_retention_h * 3600 * 1000)
        self._raw: list[tuple[int, int, float | None, int]] = []
        self._minutes: dict[tuple[int, int], list[tuple[float | None, int]]] = defaultdict(list)
        self._events: list[EventRecord] = []
        self._cache: dict[str, int] = {}
        self._last_flush_ms: int | None = None
        self._last_prune_ms = 0
        self.rows_written = 0

    # ------------------------------------------------------------------ input
    def channel_id(self, name: str, unit: str = "", source: str = "", raw_name: str = "") -> int:
        if name not in self._cache:
            with self.conn:
                ensure_channel(self.conn, name, unit, source, raw_name, self._cache)
        return self._cache[name]

    def add(self, samples: Iterable[Sample]) -> None:
        for s in samples:
            if s.channel is None:
                continue  # sensori non mappati: servono solo a `discover`
            cid = self.channel_id(s.channel, s.unit, s.source, s.raw_name)
            q = int(s.quality)
            self._raw.append((s.ts_ms, cid, s.value, q))
            self._minutes[(cid, minute_of(s.ts_ms))].append((s.value, q))

    def add_event(self, ev: EventRecord) -> None:
        self._events.append(ev)

    # --------------------------------------------------------- immediate path
    def open_rt_event(self, start_ts: int, component: str, reason: str, severity: str,
                      peak: float | None, detail: dict[str, Any]) -> int:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO rt_events(start_ts, component, reason, severity, peak, detail) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (start_ts, component, reason, severity, peak, json.dumps(detail)),
            )
        return int(cur.lastrowid or 0)

    def update_rt_event(self, rt_id: int, severity: str | None = None,
                        peak: float | None = None, end_ts: int | None = None) -> None:
        with self.conn:
            if severity is not None:
                self.conn.execute("UPDATE rt_events SET severity=? WHERE id=?", (severity, rt_id))
            if peak is not None:
                self.conn.execute("UPDATE rt_events SET peak=MAX(COALESCE(peak, ?), ?) WHERE id=?",
                                  (peak, peak, rt_id))
            if end_ts is not None:
                self.conn.execute("UPDATE rt_events SET end_ts=? WHERE id=?", (end_ts, rt_id))

    # ------------------------------------------------------------------ flush
    def due(self, now_ms: int) -> bool:
        if self._last_flush_ms is None:
            self._last_flush_ms = now_ms
            return False
        return now_ms - self._last_flush_ms >= self.flush_ms

    def flush(self, now_ms: int, final: bool = False) -> None:
        """Scrive grezzo, minuti completi ed eventi in un'unica transazione."""
        cur_minute = minute_of(now_ms)
        done = [k for k in self._minutes if final or k[1] < cur_minute]
        aggs = []
        for key in done:
            med, lo, hi, n, frac = aggregate(self._minutes.pop(key))
            aggs.append((key[1], key[0], med, lo, hi, n, frac))
        with self.conn:
            if self._raw:
                self.conn.executemany(
                    "INSERT INTO raw_samples(ts, channel_id, value, quality) VALUES (?, ?, ?, ?)",
                    self._raw,
                )
            if aggs:
                self.conn.executemany(
                    "INSERT OR REPLACE INTO agg_1min(ts, channel_id, median, min, max, n, "
                    "valid_frac) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    aggs,
                )
            for ev in self._events:
                self.conn.execute(
                    "INSERT OR IGNORE INTO events(ts, kind, source, detail, note, ext_id) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (ev.ts_ms, ev.kind, ev.source, json.dumps(ev.detail, default=str),
                     ev.note, ev.ext_id),
                )
            set_meta(self.conn, "heartbeat_ts", str(now_ms))
            if now_ms - self._last_prune_ms > 3_600_000:
                self.conn.execute("DELETE FROM raw_samples WHERE ts < ?",
                                  (now_ms - self.retention_ms,))
                self._last_prune_ms = now_ms
        self.rows_written += len(self._raw)
        self._raw.clear()
        self._events.clear()
        self._last_flush_ms = now_ms


def write_minute_aggregates(conn: sqlite3.Connection, samples: Iterable[Sample],
                            overwrite: bool = False) -> int:
    """Aggrega e scrive direttamente in ``agg_1min`` (import di log storici).

    I log importati possono coprire settimane: si salta ``raw_samples``, che
    avrebbe comunque ritenzione di 48 ore. Per default i minuti già presenti (dati
    del collector) NON vengono sovrascritti.
    """
    cache: dict[str, int] = {}
    buckets: dict[tuple[int, int], list[tuple[float | None, int]]] = defaultdict(list)
    with conn:
        for s in samples:
            if s.channel is None:
                continue
            cid = ensure_channel(conn, s.channel, s.unit, s.source, s.raw_name, cache)
            buckets[(cid, minute_of(s.ts_ms))].append((s.value, int(s.quality)))
        rows = []
        for (cid, minute), vals in buckets.items():
            med, lo, hi, n, frac = aggregate(vals)
            rows.append((minute, cid, med, lo, hi, n, frac))
        verb = "INSERT OR REPLACE" if overwrite else "INSERT OR IGNORE"
        cur = conn.executemany(
            f"{verb} INTO agg_1min(ts, channel_id, median, min, max, n, valid_frac) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
    return cur.rowcount if cur.rowcount >= 0 else len(rows)
