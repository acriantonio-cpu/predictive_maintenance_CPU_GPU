# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path

import jsonschema
import pytest

from hwdrift.alerts.notifier import Notifier
from hwdrift.model import EventRecord, Sample
from hwdrift.storage import export as ex
from hwdrift.storage.schema import set_meta
from hwdrift.storage.writer import BatchWriter

SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"


@pytest.fixture
def filled(conn):
    w = BatchWriter(conn)
    t0 = 1_767_225_600_000
    w.add([Sample(t0 + i * 1000, "t", "x", "cpu", "Intel Core i9 secret", 50.0 + i % 2, "°C",
                  "cpu.pkg.temp_c") for i in range(120)])
    w.add_event(EventRecord(t0, "maintenance.clean", "user", {"component": "cpu",
                                                              "path": "C:/Users/mario"},
                            note="pulito dal tecnico Mario"))
    w.flush(t0 + 200_000, final=True)
    with conn:
        conn.execute("INSERT INTO indicators(ts, indicator, regime, level, value) VALUES "
                     "(?, 'rth_cpu', 'high', 'daily', 0.25)", (t0,))
        conn.execute("INSERT INTO chart_state(chart_id, segment, phase, provisional, start_ts, "
                     "center, sigma, ucl, lcl, updated_ts) VALUES ('rth_cpu|high|daily', 1, "
                     "'II', 0, ?, 0.25, 0.01, 0.28, 0.22, ?)", (t0, t0))
        conn.execute("INSERT INTO signals(chart_id, segment, ts, rule, side, value) VALUES "
                     "('rth_cpu|high|daily', 1, ?, 'R1', 'upper', 0.3)", (t0,))
    return conn


def test_jsonl_valid_against_schemas_and_anonymous(filled, tmp_path):
    paths = ex.export_jsonl(filled, tmp_path / "out")
    for p in paths:
        schema = json.loads((SCHEMAS / p.name.replace("s.jsonl", ".schema.json")).read_text(
            encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        for line in p.read_text(encoding="utf-8").splitlines():
            jsonschema.validate(json.loads(line), schema)
    text = "".join(p.read_text(encoding="utf-8") for p in paths)
    assert "Mario" not in text and "mario" not in text and "Intel" not in text
    assert '"component": "cpu"' in text


def test_non_anonymous_keeps_note(filled, tmp_path):
    ex.export_jsonl(filled, tmp_path / "o", anonymize=False)
    assert "Mario" in (tmp_path / "o" / "events.jsonl").read_text(encoding="utf-8")


def test_csv_prometheus_otlp(filled, tmp_path):
    for p in ex.export_csv(filled, tmp_path / "csv"):
        assert p.exists()
    prom = ex.prometheus_text(filled)
    assert 'hwdrift_indicator{machine="' in prom and prom.endswith("# EOF\n")
    assert 'limit="ucl"' in prom
    otlp = ex.otlp_json(filled)
    dp = otlp["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][0]["gauge"]["dataPoints"]
    assert dp[0]["asDouble"] == 0.25


def _titles(n):
    return [t for t, _ in n.sent]


def test_notifier_dedup_escalation_and_readonly(conn, tmp_path, cfg):
    db = Path(conn.execute("PRAGMA database_list").fetchone()[2])
    n = Notifier(db, tmp_path, cfg)
    now = 1_767_225_600_000
    w = BatchWriter(conn)
    rid = w.open_rt_event(now, "cpu", "thermal", "warning", 90.0, {})
    with conn:
        set_meta(conn, "heartbeat_ts", str(now))
    n.check(now)
    n.check(now + 1000)
    assert len([s for s in _titles(n) if "throttling" in s]) == 1  # una notifica per episodio
    w.update_rt_event(rid, severity="error")
    n.check(now + 2000)
    assert len([s for s in _titles(n) if "throttling" in s]) == 2  # peggiorato: nuova notifica
    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert status["ongoing"][0]["severity"] == "error"
    # lo stato persiste tra riavvii del notificatore
    n2 = Notifier(db, tmp_path, cfg)
    n2.check(now + 3000)
    assert _titles(n2) == []
    # potatura (audit A19): episodi più vecchi di 7 giorni escono dallo stato
    n2.check(now + 8 * 86_400_000)
    assert n2.state["rt"] == {}


def test_notifier_toast_callback(conn, tmp_path, cfg):
    db = Path(conn.execute("PRAGMA database_list").fetchone()[2])
    cfg["alerts"]["toast"] = True
    shown = []
    n = Notifier(db, tmp_path, cfg, show=lambda t, b: shown.append(t) or True)
    BatchWriter(conn).open_rt_event(1, "gpu0", "fan_stopped", "error", 90.0, {})
    n.check(1000)
    assert shown and "ventola ferma" in shown[0]


def test_notifier_stale_collector_and_power_info(conn, tmp_path, cfg, monkeypatch):
    from hwdrift.alerts import notifier as nmod

    monkeypatch.setattr(nmod, "_boot_ms", lambda: None)
    db = Path(conn.execute("PRAGMA database_list").fetchone()[2])
    n = Notifier(db, tmp_path, cfg)
    now = 1_767_225_600_000
    n.started_ms = now - 60 * 60_000
    with conn:
        set_meta(conn, "heartbeat_ts", str(now - 30 * 60_000))
    BatchWriter(conn).open_rt_event(now, "gpu0", "power_limit", "info", 200.0, {})
    st = n.check(now)
    assert "nessun dato" in st["collector"]
    assert any("collector fermo" in s for s in _titles(n))
    assert not any("limite di potenza" in s for s in _titles(n))  # solo info: nessun toast


def test_notifier_budget_suppresses_action(conn, tmp_path, cfg):
    db = Path(conn.execute("PRAGMA database_list").fetchone()[2])
    n = Notifier(db, tmp_path, cfg)
    now = 1_767_225_600_000
    with conn:
        set_meta(conn, "heartbeat_ts", str(now))
        set_meta(conn, "alert_budget_exceeded", "1")
        conn.execute("INSERT INTO alerts(key, first_ts, last_ts, level, title, message) VALUES "
                     "('diag:dust_airflow', 1, 1, 'action', 'Polvere', 'x'), "
                     "('fatal:1', 1, 1, 'action', 'Errore fatale', 'y')")
    n.check(now)
    assert any("Errore fatale" in s for s in _titles(n))
    assert not any("Polvere" in s for s in _titles(n))


def test_stale_grace_after_login(conn, tmp_path, cfg, monkeypatch):
    """Audit: all'accesso l'heartbeat è della sessione precedente, niente falso allarme."""
    from hwdrift.alerts import notifier as nmod

    now = 1_767_225_600_000
    monkeypatch.setattr(nmod, "_boot_ms", lambda: now - 60_000)  # PC acceso da 1 minuto
    db = Path(conn.execute("PRAGMA database_list").fetchone()[2])
    with conn:
        set_meta(conn, "heartbeat_ts", str(now - 12 * 3_600_000))
    n = Notifier(db, tmp_path, cfg)
    n.started_ms = now - 30_000
    n.check(now)
    assert not any("collector fermo" in s for s in _titles(n))
    monkeypatch.setattr(nmod, "_boot_ms", lambda: now - 3_600_000)
    n.started_ms = now - 3_600_000
    n.check(now + 1000)
    assert any("collector fermo" in s for s in _titles(n))


def test_status_does_not_consume_notifications(conn, tmp_path, cfg):
    """Audit: 'hwdrift status' non deve segnare come inviate le notifiche."""
    db = Path(conn.execute("PRAGMA database_list").fetchone()[2])
    BatchWriter(conn).open_rt_event(1, "cpu", "thermal", "error", 99.0, {})
    with conn:
        set_meta(conn, "heartbeat_ts", "1000")
    n = Notifier(db, tmp_path, cfg)
    st = n.check(2000, persist=False)
    assert st["ongoing"] and n.sent == [] and not (tmp_path / "notifier_state.json").exists()
    assert n.sent == []
    n2 = Notifier(db, tmp_path, cfg)
    n2.check(3000)
    assert any("throttling" in s for s in _titles(n2))


def test_csv_non_anonymous_keeps_note_column(filled, tmp_path):
    ex.export_csv(filled, tmp_path / "c", anonymize=False)
    text = (tmp_path / "c" / "events.csv").read_text(encoding="utf-8")
    assert text.splitlines()[0].endswith("note") and "Mario" in text
    ex.export_csv(filled, tmp_path / "a", anonymize=True)
    assert "note" not in (tmp_path / "a" / "events.csv").read_text(encoding="utf-8")
