# SPDX-License-Identifier: Apache-2.0
"""Criteri di M1: il simulatore scrive dati validi, un sensore congelato viene escluso,
un collector fermato produce un avviso, un throttling forzato produce un errore entro pochi
secondi."""

from __future__ import annotations

from hwdrift.collectors.base import Collector
from hwdrift.collectors.simulator import SimulatorCollector
from hwdrift.model import Quality, Sample
from hwdrift.quality import watchdog
from hwdrift.runner import Clock, Runner


class FakeClock(Clock):
    def __init__(self, start_ms: int = 1_767_225_600_000) -> None:
        self.t = 0.0
        self.start = start_ms
        super().__init__(monotonic=lambda: self.t, wall_ms=lambda: self.start + int(self.t * 1000),
                         sleep=self._sleep)

    def _sleep(self, s: float) -> None:
        self.t += s


class Dummy(Collector):
    name = "dummy"

    def poll(self, ts_ms, mono_s):
        return [Sample(ts_ms, self.name, "d", "board", "d", 30.0, "°C", "mb.temp_c",
                       mono_s=mono_s)]


def sim(scenario: str, fault_after: float = 0.0) -> SimulatorCollector:
    return SimulatorCollector({"scenario": scenario, "seed": 3, "fault_after_s": fault_after})


def test_simulator_writes_valid_data(cfg, conn):
    clock = FakeClock()
    r = Runner(cfg, conn, [sim("healthy")], clock)
    r.run(max_ticks=180, install_signals=False)
    n = conn.execute("SELECT COUNT(*) FROM agg_1min").fetchone()[0]
    assert n >= 2 * 15
    bad = conn.execute("SELECT COUNT(*) FROM raw_samples WHERE quality != 0").fetchone()[0]
    assert bad == 0
    chans = {x[0] for x in conn.execute("SELECT name FROM channels")}
    assert {"cpu.pkg.temp_c", "gpu0.power_w", "status.simulator", "hwdrift.cpu_pct"} <= chans
    kinds = {x[0] for x in conn.execute("SELECT kind FROM events")}
    assert "system.collector_start" in kinds


def test_forced_throttle_raises_error_within_seconds(cfg, conn):
    clock = FakeClock()
    r = Runner(cfg, conn, [sim("throttle", fault_after=5)], clock)
    r.run(max_ticks=900, install_signals=False)
    rows = conn.execute("SELECT start_ts, component, reason, severity FROM rt_events "
                        "ORDER BY start_ts").fetchall()
    reasons = {(c, why) for _, c, why, _ in rows}
    assert ("cpu", "fan_stopped") in reasons
    assert ("cpu", "thermal") in reasons
    first_ts = rows[0][0]
    assert (first_ts - clock.start) / 1000 < 5 + 60  # appena la temperatura sale
    # l'episodio viene scritto subito, prima del flush in batch
    assert all(sev in ("error", "warning") for *_, sev in rows if _[2] != "power_limit")


def test_frozen_sensor_excluded(cfg, conn):
    clock = FakeClock()
    r = Runner(cfg, conn, [sim("frozen", fault_after=10)], clock)
    r.run(max_ticks=1300, install_signals=False)
    frozen = conn.execute(
        "SELECT COUNT(*) FROM raw_samples r JOIN channels c ON c.id=r.channel_id WHERE "
        "c.name='cpu.pkg.temp_c' AND r.quality=?", (int(Quality.FROZEN),)).fetchone()[0]
    assert frozen > 100
    vf = conn.execute(
        "SELECT MIN(valid_frac) FROM agg_1min a JOIN channels c ON c.id=a.channel_id WHERE "
        "c.name='cpu.pkg.temp_c'").fetchone()[0]
    assert vf == 0.0  # i minuti congelati non producono una mediana valida


def test_failing_collector_does_not_stop_others_and_is_reported(cfg, conn):
    clock = FakeClock()
    r = Runner(cfg, conn, [sim("crash", fault_after=30), Dummy()], clock)
    r.run(max_ticks=300, install_signals=False)
    st = {s["name"]: s for s in r.status()}
    assert not st["simulator"]["ok"] and st["dummy"]["ok"]
    assert "guasto simulato" in st["simulator"]["last_error"]
    h = watchdog.check(conn, now=clock.wall_ms())
    assert h.failing_collectors == ["simulator"]
    n_mb = conn.execute("SELECT COUNT(*) FROM agg_1min a JOIN channels c ON c.id=a.channel_id "
                        "WHERE c.name='mb.temp_c'").fetchone()[0]
    assert n_mb >= 4


def test_suspend_produces_gap_event(cfg, conn):
    clock = FakeClock()
    r = Runner(cfg, conn, [Dummy()], clock)
    r._startup_events()
    for _ in range(5):
        r.tick()
        clock.t += 1
    clock.start += 3_600_000  # l'orologio di parete salta di un'ora (ibernazione)
    r.tick()
    r.shutdown()
    gaps = conn.execute("SELECT detail FROM events WHERE kind='system.gap'").fetchall()
    assert len(gaps) == 1 and "sospensione" in gaps[0][0]


def test_observation_generates_config_event_only_on_change(cfg, conn):
    from hwdrift.collectors.base import observation

    clock = FakeClock()
    r = Runner(cfg, conn, [Dummy()], clock)
    r._observe(observation("gpu_driver", "555.1", "config.driver"))
    r._observe(observation("gpu_driver", "555.1", "config.driver"))
    r._observe(observation("gpu_driver", "560.2", "config.driver"))
    r.writer.flush(clock.wall_ms(), final=True)
    rows = conn.execute("SELECT kind, detail FROM events").fetchall()
    assert len(rows) == 1 and rows[0][0] == "config.driver" and "560.2" in rows[0][1]


def test_game_safe_suspends_low_level(cfg, conn, monkeypatch):
    import psutil

    class P:
        info = {"name": "EasyAntiCheat.exe"}

    monkeypatch.setattr(psutil, "process_iter", lambda attrs: [P()])

    class LowLevel(Dummy):
        name = "lowlevel"
        low_level = True

    clock = FakeClock()
    r = Runner(cfg, conn, [LowLevel(), Dummy()], clock)
    r.tick()
    assert r.game_safe
    st = {s["name"]: s for s in r.status()}
    assert st["lowlevel"]["suspended"] and not st["dummy"]["suspended"]


def test_healthcheck_live_snapshot(cfg, conn, tmp_path):
    import json
    from pathlib import Path

    from hwdrift.healthcheck import read_live

    clock = FakeClock()
    r = Runner(cfg, conn, [sim("healthy")], clock)
    Path(cfg["data_dir"], "healthcheck.active").write_text("1")
    r.tick()
    live = Path(cfg["data_dir"], "live.json")
    data = json.loads(live.read_text())
    assert "cpu.pkg.temp_c" in data["values"]
    assert read_live(live, "cpu.pkg.temp_c", max_age_s=1e12) is not None


def test_unavailable_source_is_recorded(cfg, conn):
    """Audit A6: una sorgente mai partita resta visibile nello stato salvato."""
    import json

    from hwdrift.collectors.base import CollectorUnavailable
    from hwdrift.storage.schema import get_meta

    class Missing(Dummy):
        name = "lhm"

        def start(self):
            raise CollectorUnavailable("server web di LHM non raggiungibile")

    clock = FakeClock()
    r = Runner(cfg, conn, [Missing(), Dummy()], clock)
    r.run(max_ticks=70, install_signals=False)
    st = {s["name"]: s for s in json.loads(get_meta(conn, "collectors_status"))}
    assert not st["lhm"]["started"] and "LHM" in st["lhm"]["last_error"]
    assert st["dummy"]["ok"]
