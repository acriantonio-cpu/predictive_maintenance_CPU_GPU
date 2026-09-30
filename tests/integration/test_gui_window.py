# SPDX-License-Identifier: Apache-2.0
"""Smoke test della finestra reale. Richiede tkinter e un display (su Linux: ``xvfb-run``);
altrimenti viene saltato."""

from __future__ import annotations

import contextlib
import copy
import json
import time

import pytest

tk = pytest.importorskip("tkinter")
pytestmark = pytest.mark.slow


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"nessun display: {exc}")
    yield r
    with contextlib.suppress(tk.TclError):
        r.destroy()


def pump(root, sec):
    end = time.time() + sec
    while time.time() < end:
        root.update()
        time.sleep(0.02)


@pytest.mark.parametrize(("lang", "dust", "obs", "value", "done", "tab"), [
    ("it", "Polvere", "osservazioni", "valore", "Analisi completata", "Stato e ipotesi"),
    ("en", "Dust", "observations", "value", "Analysis completed", "Status and hypotheses"),
])
def test_window_shows_status_charts_events_and_saves_config(
        root, tmp_path, monkeypatch, lang, dust, obs, value, done, tab):
    from hwdrift.analysis.worker import run_analysis
    from hwdrift.config import DEFAULTS
    from hwdrift.gui import data
    from hwdrift.gui.app import App
    from hwdrift.model import now_ms
    from hwdrift.sim.generator import generate
    from hwdrift.storage.schema import open_db

    monkeypatch.setenv("HWDRIFT_HOME", str(tmp_path))
    monkeypatch.setenv("HWDRIFT_LANGUAGE", lang)
    cfg = copy.deepcopy(DEFAULTS)
    db = tmp_path / "demo.sqlite"
    conn = open_db(db)
    generate(conn, "dust", days=24, seed=5, dt_s=60.0, start_ms=now_ms() - 24 * 86_400_000)
    run_analysis(conn, cfg, low_priority=False)
    conn.close()

    app = App(root, None, db, cfg)
    pump(root, 0.5)
    # stato: semaforo, allarmi e ipotesi dal database
    assert app.status and any(t["status"] == "action" for t in app.status["tiles"])
    assert app.alert_tree.get_children()
    assert dust in app.diag_text.get("1.0", "end")
    assert tab in [app.nb.tab(i, "text") for i in range(app.nb.index("end"))]
    # carte: selezione di una carta e disegno di I + MR
    assert app._charts_cache and app.chart_var.get()
    assert app.chart_i.spec.series[value] and app.chart_i.spec.hlines
    assert obs in app.chart_info.get()
    # tempo reale: la GUI chiede i dati al collector e li mostra
    (tmp_path / "live.json").write_text(json.dumps(
        {"ts": now_ms(), "values": {"cpu.pkg.temp_c": 61.5, "cpu.pkg.power_w": 88}}))
    pump(root, 1.3)
    assert (tmp_path / "live.active").exists()
    assert app.kpi_vars["cpu.pkg.temp_c"].get() == "61.5"
    assert app.live_charts[0].spec.series["package"][-1][1] == 61.5
    # eventi: registra una manutenzione dal modulo
    app.ev_kind.set("maintenance.clean")
    app.ev_note.set("pulizia di prova")
    app.add_event()
    assert any("maintenance.clean" in str(app.ev_tree.item(i)["values"])
               for i in app.ev_tree.get_children())
    # configurazione: modifica dal modulo e salvataggio validato
    app.cfg_vars["sampling.interval_s"].set("2")
    app.cfg_vars["game_safe.processes"].set("a.exe, b.exe")
    app.save_form()
    saved = (tmp_path / "hwdrift.yaml").read_text(encoding="utf-8")
    assert "interval_s: 2.0" in saved and "b.exe" in saved
    # configurazione non valida: nessuna scrittura (il dialogo viene intercettato)
    errors = []
    monkeypatch.setattr("tkinter.messagebox.showerror", lambda *a, **k: errors.append(a))
    app.cfg_vars["sampling.interval_s"].set("500")
    app.save_form()
    assert errors and "interval_s: 2.0" in (tmp_path / "hwdrift.yaml").read_text(encoding="utf-8")
    # analizza ora in background
    app.analyze_now()
    pump(root, 6)
    assert done in app.notice_var.get()
    assert (tmp_path / "report.html").exists()
    assert data.make_bundle(tmp_path / "b.zip", tmp_path, db, tmp_path / "hwdrift.yaml")
    app.close()
    assert not (tmp_path / "live.active").exists()
