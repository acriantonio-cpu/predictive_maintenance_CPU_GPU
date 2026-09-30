# SPDX-License-Identifier: Apache-2.0
"""Dalla raccolta alla diagnosi su scenari di guasto sintetici (Fase 0, criteri di M2-M4).

Ogni scenario simula 26 giorni: Fase I nei primi giorni, guasto dal giorno 12-17.
I controlli negativi (sano, cambio driver, ambiente, limite di potenza) non devono
produrre allarmi di manutenzione.
"""

from __future__ import annotations

import copy
import json

import pytest

from hwdrift.analysis.worker import run_analysis
from hwdrift.config import DEFAULTS
from hwdrift.reporting.html_report import ReportBuilder
from hwdrift.sim.generator import generate
from hwdrift.storage.schema import open_db

pytestmark = pytest.mark.slow
DAYS = 26
MAINTENANCE_RULES = {"dust_airflow", "paste_contact", "fan_failure"}


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    cache: dict[str, tuple] = {}

    def _run(scenario: str, days: float = DAYS):
        if scenario not in cache:
            d = tmp_path_factory.mktemp(scenario)
            conn = open_db(d / "db.sqlite")
            generate(conn, scenario, days=days, seed=11, dt_s=60.0)
            cfg = copy.deepcopy(DEFAULTS)
            cfg["data_dir"] = str(d)
            summary = run_analysis(conn, cfg, low_priority=False)
            cache[scenario] = (conn, cfg, summary)
        return cache[scenario]

    return _run


def diagnoses(conn):
    return {r[0]: r[1] for r in conn.execute(
        "SELECT d.rule_id, a.level FROM diagnoses d JOIN alerts a ON a.key = 'diag:' || "
        "d.rule_id WHERE d.active=1 AND a.active=1")}


def action_alerts(conn):
    return [r[0] for r in conn.execute("SELECT key FROM alerts WHERE active=1 AND "
                                       "level='action'")]


@pytest.mark.parametrize("scenario", ["healthy", "driver_change", "ambient", "power_limit"])
def test_negative_controls_no_maintenance_alarm(run, scenario):
    conn, _, summary = run(scenario)
    assert summary["windows_new"] > 1000
    assert action_alerts(conn) == []
    assert not MAINTENANCE_RULES & set(diagnoses(conn))


@pytest.mark.parametrize(("scenario", "rule"), [
    ("dust", "dust_airflow"),
    ("paste", "paste_contact"),
    ("fan_fail", "fan_failure"),
])
def test_fault_produces_signal_and_consistent_hypothesis(run, scenario, rule):
    conn, _, _ = run(scenario)
    d = diagnoses(conn)
    assert rule in d, d
    assert d[rule] == "action"
    # l'ipotesi giusta è la prima (ordinamento per livello e confidenza)
    top = conn.execute("SELECT d.rule_id FROM diagnoses d JOIN alerts a ON a.key='diag:' || "
                       "d.rule_id WHERE d.active=1 ORDER BY CASE a.level WHEN 'action' THEN 0 "
                       "ELSE 1 END, CASE d.confidence WHEN 'high' THEN 0 WHEN 'medium' THEN 1 "
                       "ELSE 2 END").fetchone()[0]
    assert top == rule
    # i segnali partono dopo l'inizio del guasto, non in Fase I
    first = conn.execute("SELECT MIN(ts) FROM signals WHERE label='maintenance' AND rule='R1' "
                         "AND side='upper' AND chart_id LIKE 'rth_cpu|%'").fetchone()[0]
    assert first is not None and (first - 1_767_225_600_000) / 86_400_000 > 11


def test_driver_change_reopens_phase_one_and_asks_confirmation(run):
    conn, _, _ = run("driver_change")
    segs = conn.execute("SELECT MAX(segment) FROM chart_state WHERE chart_id LIKE "
                        "'rth_gpu|%'").fetchone()[0]
    assert segs == 2
    cpu_segs = conn.execute("SELECT MAX(segment) FROM chart_state WHERE chart_id LIKE "
                            "'rth_cpu|%'").fetchone()[0]
    assert cpu_segs == 1  # il cambio driver GPU non tocca le carte CPU
    assert conn.execute("SELECT COUNT(*) FROM alerts WHERE key LIKE 'config:%'").fetchone()[0] >= 1


def test_phase_one_and_regimes(run):
    conn, cfg, _ = run("healthy")
    b = json.loads(conn.execute("SELECT value FROM meta WHERE key='regimes:cpu'").fetchone()[0])
    assert b["mode"] == "fixed" and b["lo"] < b["hi"]
    regs = {r[0] for r in conn.execute("SELECT DISTINCT regime FROM windows")}
    assert regs == {"idle", "medium", "high"}
    row = conn.execute("SELECT phase, provisional, n_phase1, params FROM chart_state WHERE "
                       "chart_id='rth_cpu|high|window'").fetchone()
    assert row[0] == "II" and row[1] == 0 and row[2] >= cfg["spc"]["phase1_min_obs"]
    p = json.loads(row[3])
    assert p["phase1_days"] >= cfg["spc"]["phase1_min_days"]
    assert p["method"] == "longterm"
    daily = conn.execute("SELECT phase, n_phase1 FROM chart_state WHERE "
                         "chart_id='rth_cpu|high|daily'").fetchone()
    # carta giornaliera: Fase I = le prime 25 mediane giornaliere
    assert daily[0] == "I" or daily[1] == cfg["spc"]["phase1_min_obs"]
    # modelli di baseline e residui presenti
    assert conn.execute("SELECT COUNT(*) FROM indicators WHERE indicator='temp_resid_cpu'"
                        ).fetchone()[0] > 100


def test_throttling_feeds_throttle_indicator_not_rth(run):
    conn, _, _ = run("throttle")
    # durante il throttling la potenza oscilla: niente finestre stazionarie, quindi Rth
    # non viene "migliorato" dal clock in calo; la quota di throttling invece sale
    leaked = conn.execute(
        "SELECT COUNT(*) FROM indicators i JOIN windows w ON w.id=i.window_id WHERE "
        "w.throttled=1 AND i.indicator LIKE 'rth_%'").fetchone()[0]
    assert leaked == 0
    frac = conn.execute("SELECT MAX(value) FROM indicators WHERE indicator='throttle_frac_cpu'"
                        ).fetchone()[0]
    assert frac > 0.1
    sig = conn.execute("SELECT COUNT(*) FROM signals WHERE chart_id LIKE 'throttle_frac_cpu|%' "
                       "AND side='upper'").fetchone()[0]
    assert sig > 0
    assert conn.execute("SELECT COUNT(*) FROM rt_events").fetchone()[0] == 0  # solo offline


def test_frozen_sensor_does_not_create_windows(run):
    conn, _, _ = run("frozen_sensor")
    day14 = 1_767_225_600_000 + 14 * 86_400_000
    # il sensore si congela a mezzanotte, il PC si accende alle 8: il valore identico viene
    # marcato FROZEN dopo 15 minuti (latenza di rilevamento = freeze_s)
    start = day14 + 8 * 3_600_000 + 20 * 60_000
    n = conn.execute("SELECT COUNT(*) FROM windows WHERE component='cpu' AND start_ts >= ? AND "
                     "start_ts < ?", (start, day14 + 86_400_000)).fetchone()[0]
    assert n == 0
    assert action_alerts(conn) == []


def test_cleaning_closes_segment_and_shows_recovery(run):
    conn, cfg, _ = run("dust_then_clean", 30)
    closed = conn.execute("SELECT COUNT(*) FROM chart_state WHERE closed_ts IS NOT NULL AND "
                          "chart_id LIKE 'rth_cpu|%'").fetchone()[0]
    assert closed >= 1
    html = ReportBuilder(conn, cfg).effectiveness()
    assert "recuperato" in html or "migliorato" in html


def test_whea_counts_charted(run):
    conn, _, _ = run("whea")
    sig = conn.execute("SELECT COUNT(*) FROM signals WHERE chart_id LIKE 'whea_corrected|%' "
                       "AND rule='C'").fetchone()[0]
    assert sig > 0
    assert "instability_whea" in diagnoses(conn)


def test_incremental_analysis_is_idempotent(run):
    conn, cfg, _ = run("healthy")
    n_ind = conn.execute("SELECT COUNT(*) FROM indicators").fetchone()[0]
    n_sig = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    s = run_analysis(conn, cfg, low_priority=False)
    assert s["windows_new"] == 0 and s["signals_new"] == 0
    assert conn.execute("SELECT COUNT(*) FROM indicators").fetchone()[0] == n_ind
    assert conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0] == n_sig


def test_report_renders_all_views(run):
    conn, cfg, _ = run("dust")
    html = ReportBuilder(conn, cfg).build()
    for section in ("Stato generale", "Errori immediati", "Ipotesi di manutenzione",
                    "Carte di controllo", "Copertura e qualità dei dati",
                    "Efficacia della manutenzione", "Overhead", "Polvere"):
        assert section in html
    assert '<html lang="it">' in html and "<script" not in html
    assert html.count("<svg") == html.count('role="img"')
    assert "Azione" in html
