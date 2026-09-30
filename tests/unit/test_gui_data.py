# SPDX-License-Identifier: Apache-2.0
"""Livello dati della GUI (senza tkinter)."""

from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path

import pytest

from hwdrift.config import ConfigError
from hwdrift.gui import data
from hwdrift.model import Sample, now_ms
from hwdrift.storage.writer import BatchWriter


def test_read_live_fresh_stale_and_broken(tmp_path):
    p = tmp_path / "live.json"
    assert data.read_live(p) is None
    p.write_text(json.dumps({"ts": now_ms(), "values": {"cpu.pkg.temp_c": 55, "x": "bad"}}))
    _ts, vals = data.read_live(p)
    assert vals == {"cpu.pkg.temp_c": 55.0}
    p.write_text(json.dumps({"ts": now_ms() - 60_000, "values": {"a": 1}}))
    assert data.read_live(p) is None  # vecchio: il collector non gira
    p.write_text("{troncato")
    assert data.read_live(p) is None


def test_live_buffer_push_dedup_window_and_downsample():
    b = data.LiveBuffer(window_s=10)
    for i in range(30):
        b.push(1000 * i, {"a": float(i)})
    b.push(5000, {"a": 99.0})  # timestamp vecchio: ignorato
    pts = b.series("a", 0)
    assert pts[0][0] >= 19_000 and pts[-1] == (29_000, 29.0) and b.latest("a") == 29.0
    big = data.LiveBuffer(window_s=1e9)
    for i in range(5000):
        big.push(i, {"a": 1.0})
    assert len(big.series("a", 0, max_points=600)) <= 601


def test_backfill_uses_aggregates_then_raw(conn):
    w = BatchWriter(conn)
    t0 = (now_ms() // 60_000) * 60_000 - 10 * 60_000
    w.add([Sample(t0 + i * 1000, "t", "x", "cpu", "x", 40.0 + i // 60, "°C", "cpu.pkg.temp_c")
           for i in range(9 * 60)])
    w.flush(t0 + 9 * 60_000 + 1000)
    b = data.LiveBuffer()
    b.backfill(conn, ["cpu.pkg.temp_c", "missing.channel"], t0 - 1)
    pts = b.series("cpu.pkg.temp_c", 0)
    assert len(pts) >= 8 and pts == sorted(pts)
    assert "missing.channel" not in b.data


def test_config_fields_cover_valid_keys_and_roundtrip(tmp_path):
    from hwdrift.config import DEFAULTS

    for f in data.ALL_FIELDS:
        data.get_path(DEFAULTS, f.key)  # ogni campo del modulo esiste nella configurazione
    path = tmp_path / "hwdrift.yaml"
    cfg = data.save_config(path, {"sampling.interval_s": data.parse_field(
        next(f for f in data.ALL_FIELDS if f.key == "sampling.interval_s"), "2,5"),
        "game_safe.processes": ["a.exe", "b.exe"], "alerts.toast": False})
    assert cfg["sampling"]["interval_s"] == 2.5 and cfg["alerts"]["toast"] is False
    # un secondo salvataggio mantiene il resto e crea la copia .bak
    data.save_config(path, {"regimes.mode": "adaptive"})
    assert (tmp_path / "hwdrift.yaml.bak").exists()
    from hwdrift.config import load_config

    c2 = load_config(path)
    assert c2["sampling"]["interval_s"] == 2.5 and c2["regimes"]["mode"] == "adaptive"
    assert c2["game_safe"]["processes"] == ["a.exe", "b.exe"]


def test_invalid_config_never_overwrites_good_file(tmp_path):
    path = tmp_path / "hwdrift.yaml"
    data.save_config(path, {"sampling.interval_s": 2.0})
    before = path.read_text(encoding="utf-8")
    with pytest.raises(ConfigError):
        data.save_config(path, {"sampling.interval_s": 500.0})
    with pytest.raises(ConfigError):
        data.save_config(path, raw_text="sampling:\n  intervall_s: 1\n")
    with pytest.raises(ConfigError):
        data.save_config(path, raw_text="- lista\n")
    assert path.read_text(encoding="utf-8") == before
    with pytest.raises(ValueError):
        data.parse_field(next(f for f in data.ALL_FIELDS if f.kind == "float"), "abc")


def test_diagnostic_bundle_has_no_database(tmp_path, conn):
    home = tmp_path / "home"
    home.mkdir()
    (home / "hwdrift.log").write_text("riga di log\n", encoding="utf-8")
    (home / "status.json").write_text("{}", encoding="utf-8")
    db = Path(conn.execute("PRAGMA database_list").fetchone()[2])
    cfgp = home / "hwdrift.yaml"
    cfgp.write_text("sampling:\n  interval_s: 1\n", encoding="utf-8")
    out = tmp_path / "b.zip"
    names = data.make_bundle(out, home, db, cfgp)
    with zipfile.ZipFile(out) as z:
        assert set(z.namelist()) == set(names) == {"hwdrift.log", "status.json", "hwdrift.yaml",
                                                   "info.json"}
        info = json.loads(z.read("info.json"))
    assert "schema_version" in info and info["hwdrift"]


def test_tail_and_collector_command(tmp_path, monkeypatch):
    p = tmp_path / "x.log"
    p.write_text("a" * 100 + "FINE", encoding="utf-8")
    assert data.tail(p, 10).endswith("FINE") and len(data.tail(p, 10)) == 10
    assert data.tail(tmp_path / "missing") == ""
    cmd = data.CollectorProcess.command(["--db", "x", "run"])
    assert cmd[1:3] == ["-m", "hwdrift"]
    monkeypatch.setattr("sys.frozen", True, raising=False)
    assert data.CollectorProcess.command(["run"])[1:] == ["run"]


def test_stop_request_stops_the_collector(tmp_path):
    """La GUI ferma il collector (anche elevato) con un file di richiesta."""
    import copy

    from hwdrift.collectors.simulator import SimulatorCollector
    from hwdrift.config import DEFAULTS
    from hwdrift.runner import Runner
    from hwdrift.storage.schema import open_db

    cfg = copy.deepcopy(DEFAULTS)
    cfg["data_dir"] = str(tmp_path)
    r = Runner(cfg, open_db(tmp_path / "s.sqlite"), [SimulatorCollector({"seed": 1})])
    (tmp_path / "stop.request").write_text("1")
    (tmp_path / "live.active").write_text("1")  # la GUI è aperta
    t0 = time.time()
    r.run(install_signals=False)  # senza la richiesta girerebbe all'infinito
    assert time.time() - t0 < 10 and not (tmp_path / "stop.request").exists()
    assert (tmp_path / "live.json").exists() and data.read_live(tmp_path / "live.json")


def test_launcher_dispatches_cli_or_gui(monkeypatch, capsys):
    from hwdrift.gui import launcher

    with pytest.raises(SystemExit) as exc:  # Typer termina con exit(0)
        launcher.main(["version"])
    assert exc.value.code == 0 and capsys.readouterr().out.strip()
    pytest.importorskip("tkinter")  # la parte GUI del launcher richiede Tk
    called = {}
    monkeypatch.setattr("hwdrift.gui.app.run_gui", lambda c, d: called.update(c=c, d=d))
    launcher.main(["--db", "x.sqlite"])
    assert str(called["d"]) == "x.sqlite"
