# SPDX-License-Identifier: Apache-2.0
"""Criterio di M4: dalla CLI, un guasto simulato produce un segnale e un'ipotesi coerente."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from hwdrift.cli import app

pytestmark = pytest.mark.slow


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("HWDRIFT_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("HWDRIFT_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def invoke(*args):
    r = CliRunner().invoke(app, list(args), catch_exceptions=False)
    return r


def test_simulate_analyze_report_export(env):
    db = str(env / "sim.sqlite")
    r = invoke("--db", db, "simulate", "dust", "--days", "24")
    assert r.exit_code == 0, r.output
    r = invoke("--db", db, "analyze")
    assert r.exit_code == 0, r.output
    assert "Analisi completata" in r.output and "report.html" in r.output
    r = invoke("--db", db, "status")
    assert "Polvere" in r.output
    r = invoke("--db", db, "report", "--out", str(env / "r.html"))
    assert (env / "r.html").read_text(encoding="utf-8").startswith("<!doctype html>")
    r = invoke("--db", db, "export", "--format", "jsonl", "--out", str(env / "exp"))
    assert r.exit_code == 0 and (env / "exp" / "indicators.jsonl").exists()
    r = invoke("--db", db, "export", "--format", "prometheus", "--out", str(env / "m.prom"))
    assert "hwdrift_indicator" in (env / "m.prom").read_text(encoding="utf-8")
    r = invoke("--db", db, "export", "--format", "otlp", "--out", str(env / "o.json"))
    assert json.loads((env / "o.json").read_text(encoding="utf-8"))["resourceMetrics"]
    r = invoke("--db", db, "baseline", "status")
    assert "rth_cpu|high|window" in r.output
    # simulate su un database già pieno: rifiuta
    assert invoke("--db", db, "simulate", "healthy").exit_code == 2


def test_event_and_baseline_commands(env):
    db = str(env / "e.sqlite")
    r = invoke("--db", db, "event", "add", "maintenance.clean", "--at", "2026-09-01 10:00",
               "--note", "pulizia")
    assert r.exit_code == 0 and "registrato" in r.output
    assert invoke("--db", db, "event", "add", "banana").exit_code == 2
    r = invoke("--db", db, "event", "list", "--days", "100000")
    assert "maintenance.clean" in r.output
    assert "maintenance.repaste" in invoke("event", "kinds").output
    r = invoke("--db", db, "baseline", "start", "--state", "clean")
    assert r.exit_code == 0 and "appena pulito" in r.output
    r = invoke("--db", db, "baseline", "lock")
    assert r.exit_code == 0


def test_import_hwinfo(env):
    csv_text = ('"Date","Time","CPU Package [°C]","CPU Package Power [W]"\n'
                + "".join(f'"30.9.2026","12:{m:02d}:{s:02d}.000","{50 + s % 3}","{30 + s % 2}"\n'
                          for m in range(3) for s in range(0, 60, 2)))
    f = env / "log.csv"
    f.write_text(csv_text, encoding="utf-8")
    r = invoke("--db", str(env / "i.sqlite"), "import-hwinfo", str(f), "--tz-offset", "0")
    assert r.exit_code == 0, r.output
    assert "cpu.pkg.temp_c" in r.output and "6 aggregati" in r.output


def test_config_errors_and_init(env):
    (env / "bad.yaml").write_text("sampling:\n  foo: 1\n", encoding="utf-8")
    r = CliRunner().invoke(app, ["--config", str(env / "bad.yaml"), "version"])
    assert r.exit_code == 2 and "sconosciuta" in r.output
    assert invoke("init-config", "--path", str(env / "h.yaml")).exit_code == 0
    assert invoke("--config", str(env / "h.yaml"), "version").exit_code == 0
    assert invoke("init-config", "--path", str(env / "h.yaml")).exit_code == 1


def test_run_with_simulator_and_schedule_dry_run(env):
    db = str(env / "run.sqlite")
    r = invoke("--db", db, "run", "--simulate", "healthy", "--interval", "0.2",
               "--max-seconds", "2")
    assert r.exit_code == 0, r.output
    assert "simulator" in r.output
    r = invoke("schedule", "install")
    assert "schtasks" in r.output and "/RL HIGHEST" in r.output
    assert "ONLOGON" in invoke("schedule", "install").output
    r = invoke("healthcheck")
    assert r.exit_code == 1 and "--yes" in r.output
