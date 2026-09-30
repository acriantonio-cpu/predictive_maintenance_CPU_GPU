# SPDX-License-Identifier: Apache-2.0
"""Il prodotto in inglese (lingua predefinita): allarmi, ipotesi, report, notifiche e CLI."""

from __future__ import annotations

import copy
import re

import pytest

from hwdrift.analysis.worker import run_analysis
from hwdrift.config import DEFAULTS
from hwdrift.reporting.html_report import ReportBuilder
from hwdrift.sim.generator import generate
from hwdrift.storage.schema import open_db

pytestmark = pytest.mark.slow
ITALIAN_MARKERS = re.compile(
    r"\b(Stato generale|Allarmi|Ipotesi|Carte di controllo|Polvere|salita|Nessun|nessun|"
    r"Copertura|Verifiche suggerite|Confidenza|Collector fermo|Segnali|Eventi|Sorgent)\w*")


@pytest.fixture(autouse=True)
def english_language(monkeypatch, italian_by_default):
    """Dopo la fixture globale (italiano) riporta la lingua a inglese per questi test."""
    from hwdrift import i18n

    monkeypatch.setenv("HWDRIFT_LANGUAGE", "en")
    i18n.set_language("en")


@pytest.fixture(scope="module")
def english(tmp_path_factory, request):
    mp = pytest.MonkeyPatch()
    mp.setenv("HWDRIFT_LANGUAGE", "en")
    request.addfinalizer(mp.undo)
    d = tmp_path_factory.mktemp("en")
    conn = open_db(d / "db.sqlite")
    generate(conn, "dust_then_clean", days=30, seed=11, dt_s=60.0)
    cfg = copy.deepcopy(DEFAULTS)
    cfg["data_dir"] = str(d)
    run_analysis(conn, cfg, low_priority=False)
    return conn, cfg, d


def test_alerts_and_hypotheses_are_english(english):
    conn, _cfg, _ = english
    texts = [r[0] + " " + r[1] for r in conn.execute("SELECT title, message FROM alerts")]
    texts += [r[0] for r in conn.execute("SELECT title FROM diagnoses")]
    assert texts and not [t for t in texts if ITALIAN_MARKERS.search(t)]
    assert any("rising" in t or "Dust" in t or "Did you do maintenance" in t for t in texts)
    actions = " ".join(r[0] for r in conn.execute("SELECT actions FROM diagnoses"))
    assert actions == "" or "Clean" in actions or "Check" in actions or "Replace" in actions


def test_report_is_english_and_accessible(english):
    conn, cfg, _ = english
    html = ReportBuilder(conn, cfg).build()
    assert '<html lang="en">' in html
    for phrase in ("Overall status", "Immediate errors", "Maintenance hypotheses", "Control charts",
                   "Coverage and data quality", "Maintenance effectiveness", "Skip to content",
                   "Warnings", "Phase I"):
        assert phrase in html, phrase
    visible = re.sub(r"<(style|svg)[\s\S]*?</\1>", " ", html)
    visible = re.sub(r"<[^>]+>", " ", visible)
    assert not ITALIAN_MARKERS.search(visible), ITALIAN_MARKERS.search(visible).group(0)
    assert "<script" not in html


def test_effectiveness_outcome_in_english(english):
    conn, cfg, _ = english
    table = ReportBuilder(conn, cfg).effectiveness()
    assert "recovered" in table or "improved" in table


def test_notifier_english(english, tmp_path):
    from pathlib import Path

    from hwdrift.alerts.notifier import Notifier
    from hwdrift.model import now_ms
    from hwdrift.storage.writer import BatchWriter

    _conn, cfg, _d = english
    conn2 = open_db(tmp_path / "n.sqlite")
    BatchWriter(conn2).open_rt_event(now_ms(), "cpu", "fan_stopped", "error", 88.0, {})
    db = Path(conn2.execute("PRAGMA database_list").fetchone()[2])
    n = Notifier(db, tmp_path, dict(cfg, alerts=dict(cfg["alerts"], toast=False)))
    n.check()
    title, body = n.sent[0]
    assert "fan stopped at high temperature" in title and "Immediate error" in body
    assert "Peak 88" in body


def test_cli_init_config_follows_language(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from hwdrift.cli import app

    monkeypatch.setenv("HWDRIFT_HOME", str(tmp_path / "h"))
    monkeypatch.delenv("HWDRIFT_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(app, ["init-config", "--path", str(tmp_path / "en.yaml")])
    assert r.exit_code == 0
    assert "example configuration" in (tmp_path / "en.yaml").read_text(encoding="utf-8")
    monkeypatch.setenv("HWDRIFT_LANGUAGE", "it")
    r = CliRunner().invoke(app, ["init-config", "--path", str(tmp_path / "it.yaml")])
    assert "configurazione di esempio" in (tmp_path / "it.yaml").read_text(encoding="utf-8")
