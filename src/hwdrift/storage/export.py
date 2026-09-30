# SPDX-License-Identifier: Apache-2.0
"""Export del dataset: CSV, JSON Lines (schema aperto), Parquet, Prometheus, OTLP.

Privacy (sezione 5 e 13): l'export anonimo (default) contiene solo canali
canonici e valori numerici; niente nomi di processo, utente, percorsi, nomi
grezzi dei sensori (che includono il modello di CPU/GPU) né note libere. L'ID
macchina è l'hash casuale locale, non derivato dall'hardware.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ..storage.schema import get_meta

SCHEMA_VERSION = "1.0"
# chiavi di ``events.detail`` ammesse nell'export anonimo
SAFE_DETAIL_KEYS = {"component", "event_id", "provider", "reason", "end_ts", "power_limit"}


def machine_id(conn: sqlite3.Connection) -> str:
    return get_meta(conn, "machine_id") or "unknown"


def iter_records(conn: sqlite3.Connection, kind: str, anonymize: bool = True,
                 since: int | None = None) -> Iterator[dict[str, Any]]:
    """Record conformi agli schemi in ``schemas/`` (uno schema per ``kind``)."""
    mid = machine_id(conn)
    s = since or 0
    if kind == "sample":
        for ts, name, med, lo, hi, n, vf in conn.execute(
                "SELECT a.ts, c.name, a.median, a.min, a.max, a.n, a.valid_frac FROM agg_1min a "
                "JOIN channels c ON c.id=a.channel_id WHERE a.ts >= ? ORDER BY a.ts", (s,)):
            yield {"schema": f"hwdrift.sample/{SCHEMA_VERSION}", "machine_id": mid, "ts": ts,
                   "channel": name, "aggregation": "1min", "median": med, "min": lo, "max": hi,
                   "n": n, "valid_frac": vf}
    elif kind == "indicator":
        for ts, ind, reg, lvl, val, n in conn.execute(
                "SELECT ts, indicator, regime, level, value, n FROM indicators WHERE ts >= ? "
                "ORDER BY ts", (s,)):
            yield {"schema": f"hwdrift.indicator/{SCHEMA_VERSION}", "machine_id": mid, "ts": ts,
                   "indicator": ind, "regime": reg, "level": lvl, "value": val, "n": n}
    elif kind == "event":
        for ts, k, src, detail, note in conn.execute(
                "SELECT ts, kind, source, detail, note FROM events WHERE ts >= ? ORDER BY ts",
                (s,)):
            try:
                d = json.loads(detail or "{}")
            except ValueError:
                d = {}
            if anonymize:
                d = {k2: v for k2, v in d.items() if k2 in SAFE_DETAIL_KEYS}
            rec = {"schema": f"hwdrift.event/{SCHEMA_VERSION}", "machine_id": mid, "ts": ts,
                   "kind": k, "source": src, "detail": d}
            if not anonymize and note:
                rec["note"] = note
            yield rec
    elif kind == "chart_state":
        for r in conn.execute("SELECT chart_id, segment, phase, provisional, start_ts, locked_ts, "
                              "closed_ts, center, sigma, ucl, lcl, n_phase1 FROM chart_state"):
            ind, regime, level = r[0].split("|")
            yield {"schema": f"hwdrift.chart_state/{SCHEMA_VERSION}", "machine_id": mid,
                   "indicator": ind, "regime": regime, "level": level, "segment": r[1],
                   "phase": r[2], "provisional": bool(r[3]), "start_ts": r[4], "locked_ts": r[5],
                   "closed_ts": r[6], "center": r[7], "sigma": r[8], "ucl": r[9], "lcl": r[10],
                   "n_phase1": r[11]}
    elif kind == "signal":
        for r in conn.execute("SELECT chart_id, segment, ts, rule, side, value, label FROM "
                              "signals WHERE ts >= ? ORDER BY ts", (s,)):
            ind, regime, level = r[0].split("|")
            yield {"schema": f"hwdrift.signal/{SCHEMA_VERSION}", "machine_id": mid,
                   "indicator": ind, "regime": regime, "level": level, "segment": r[1],
                   "ts": r[2], "rule": r[3], "side": r[4], "value": r[5], "label": r[6]}
    else:
        raise ValueError(f"tipo di record sconosciuto: {kind}")


KINDS = ("sample", "indicator", "event", "chart_state", "signal")
CSV_FIELDS: dict[str, list[str]] = {
    "sample": ["schema", "machine_id", "ts", "channel", "aggregation", "median", "min", "max",
               "n", "valid_frac"],
    "indicator": ["schema", "machine_id", "ts", "indicator", "regime", "level", "value", "n"],
    "event": ["schema", "machine_id", "ts", "kind", "source", "detail", "note"],
    "chart_state": ["schema", "machine_id", "indicator", "regime", "level", "segment", "phase",
                    "provisional", "start_ts", "locked_ts", "closed_ts", "center", "sigma",
                    "ucl", "lcl", "n_phase1"],
    "signal": ["schema", "machine_id", "indicator", "regime", "level", "segment", "ts", "rule",
               "side", "value", "label"],
}


def export_jsonl(conn: sqlite3.Connection, out_dir: Path, anonymize: bool = True,
                 since: int | None = None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for kind in KINDS:
        p = out_dir / f"{kind}s.jsonl"
        with p.open("w", encoding="utf-8") as fh:
            for rec in iter_records(conn, kind, anonymize, since):
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        paths.append(p)
    return paths


def export_csv(conn: sqlite3.Connection, out_dir: Path, anonymize: bool = True,
               since: int | None = None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for kind in KINDS:
        p = out_dir / f"{kind}s.csv"
        fields = [f for f in CSV_FIELDS[kind] if not (anonymize and f == "note")]
        with p.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for rec in iter_records(conn, kind, anonymize, since):
                writer.writerow({k: (json.dumps(v) if isinstance(v, dict) else v)
                                 for k, v in rec.items()})
        paths.append(p)
    return paths


def export_parquet(conn: sqlite3.Connection, out_dir: Path, anonymize: bool = True,
                   since: int | None = None) -> list[Path]:
    try:
        import pyarrow as pa  # type: ignore[import-not-found]
        import pyarrow.parquet as pq  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("export Parquet: installare l'extra 'parquet' (pyarrow)") from exc
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for kind in KINDS:
        recs = [{k: (json.dumps(v) if isinstance(v, dict) else v) for k, v in r.items()}
                for r in iter_records(conn, kind, anonymize, since)]
        if not recs:
            continue
        p = out_dir / f"{kind}s.parquet"
        pq.write_table(pa.Table.from_pylist(recs), p)
        paths.append(p)
    return paths


def _latest_indicators(conn: sqlite3.Connection) -> list[tuple[str, str, str, int, float]]:
    return conn.execute(
        "SELECT i.indicator, i.regime, i.level, i.ts, i.value FROM indicators i JOIN "
        "(SELECT indicator, regime, level, MAX(ts) AS mts FROM indicators GROUP BY 1,2,3) m "
        "ON i.indicator=m.indicator AND i.regime=m.regime AND i.level=m.level AND i.ts=m.mts"
    ).fetchall()


def _esc(v: str) -> str:
    return v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def prometheus_text(conn: sqlite3.Connection) -> str:
    """Formato di esposizione OpenMetrics (per il textfile collector di node_exporter)."""
    mid = machine_id(conn)
    lines = [
        "# HELP hwdrift_indicator Ultimo valore di un indicatore di salute.",
        "# TYPE hwdrift_indicator gauge",
    ]
    for ind, reg, lvl, ts, val in _latest_indicators(conn):
        lines.append(f'hwdrift_indicator{{machine="{_esc(mid)}",indicator="{_esc(ind)}",'
                     f'regime="{_esc(reg)}",level="{_esc(lvl)}"}} {val!r} {ts / 1000:.3f}')
    lines += ["# HELP hwdrift_chart_limit Limiti bloccati delle carte di controllo.",
              "# TYPE hwdrift_chart_limit gauge"]
    for cid, center, ucl, lcl in conn.execute(
            "SELECT chart_id, center, ucl, lcl FROM chart_state WHERE closed_ts IS NULL AND "
            "phase='II'"):
        ind, reg, lvl = cid.split("|")
        for name, v in (("center", center), ("ucl", ucl), ("lcl", lcl)):
            if v is not None:
                lines.append(f'hwdrift_chart_limit{{machine="{_esc(mid)}",indicator="{_esc(ind)}",'
                             f'regime="{_esc(reg)}",level="{_esc(lvl)}",limit="{name}"}} {v!r}')
    lines += ["# HELP hwdrift_active_alerts Allarmi attivi per livello.",
              "# TYPE hwdrift_active_alerts gauge"]
    for lvl in ("info", "attention", "action"):
        n = conn.execute("SELECT COUNT(*) FROM alerts WHERE active=1 AND level=?", (lvl,)
                         ).fetchone()[0]
        lines.append(f'hwdrift_active_alerts{{machine="{_esc(mid)}",level="{lvl}"}} {n}')
    last = conn.execute("SELECT MAX(ts) FROM agg_1min").fetchone()[0]
    lines += ["# HELP hwdrift_last_sample_timestamp_seconds Ultimo dato ricevuto.",
              "# TYPE hwdrift_last_sample_timestamp_seconds gauge",
              f'hwdrift_last_sample_timestamp_seconds{{machine="{_esc(mid)}"}} '
              f"{(last or 0) / 1000:.3f}", "# EOF"]
    return "\n".join(lines) + "\n"


def otlp_json(conn: sqlite3.Connection) -> dict[str, Any]:
    """Metriche in formato OTLP/JSON (file locale; nessun invio di rete)."""
    from .. import __version__

    points = []
    for ind, reg, lvl, ts, val in _latest_indicators(conn):
        points.append({
            "timeUnixNano": str(int(ts) * 1_000_000), "asDouble": float(val),
            "attributes": [{"key": "indicator", "value": {"stringValue": ind}},
                           {"key": "regime", "value": {"stringValue": reg}},
                           {"key": "level", "value": {"stringValue": lvl}}],
        })
    return {"resourceMetrics": [{
        "resource": {"attributes": [
            {"key": "service.name", "value": {"stringValue": "hwdrift"}},
            {"key": "host.id", "value": {"stringValue": machine_id(conn)}}]},
        "scopeMetrics": [{"scope": {"name": "hwdrift", "version": __version__},
                          "metrics": [{"name": "hwdrift.indicator",
                                       "description": "Indicatori di salute termica",
                                       "gauge": {"dataPoints": points}}]}],
    }]}
