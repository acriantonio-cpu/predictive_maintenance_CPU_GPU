# SPDX-License-Identifier: Apache-2.0
"""Collector reali con sorgenti finte: NVML, server web LHM su loopback, hwmon, smartctl."""

from __future__ import annotations

import json
import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from hwdrift.collectors.base import CollectorUnavailable, build_collectors
from hwdrift.collectors.lhm import LhmCollector
from hwdrift.collectors.nvml import NvmlCollector
from hwdrift.collectors.psutil_basic import PsutilCollector


def fake_pynvml(reasons=0x20 | 0x4):
    m = types.ModuleType("pynvml")
    m.NVML_TEMPERATURE_GPU = 0
    m.NVML_CLOCK_GRAPHICS = 0
    m.nvmlInit = lambda: None
    m.nvmlShutdown = lambda: None
    m.nvmlDeviceGetCount = lambda: 1
    m.nvmlDeviceGetHandleByIndex = lambda i: f"h{i}"
    m.nvmlSystemGetDriverVersion = lambda: b"560.20"
    m.nvmlDeviceGetTemperature = lambda h, s: 71
    m.nvmlDeviceGetPowerUsage = lambda h: 215_000
    m.nvmlDeviceGetClockInfo = lambda h, c: 1800
    m.nvmlDeviceGetFanSpeed = lambda h: 55

    def unsupported(h):
        raise RuntimeError("NVML_ERROR_NOT_SUPPORTED")

    m.nvmlDeviceGetUtilizationRates = lambda h: types.SimpleNamespace(gpu=97)
    m.nvmlDeviceGetCurrentClocksEventReasons = lambda h: reasons
    m.nvmlDeviceGetPcieReplayCounter = unsupported
    return m


def test_nvml_collector(monkeypatch):
    monkeypatch.setitem(sys.modules, "pynvml", fake_pynvml())
    c = NvmlCollector({})
    c.start()
    ev = c.drain_events()
    assert ev[0].kind == "observe" and ev[0].detail["value"] == "560.20"
    got = {s.channel: s.value for s in c.poll(0, 0.0)}
    assert got["gpu0.temp_edge_c"] == 71 and got["gpu0.power_w"] == 215.0
    assert got["gpu0.util_pct"] == 97 and got["gpu0.fan_pct"] == 55
    assert got["gpu0.throttle_thermal"] == 1.0 and got["gpu0.throttle_power"] == 1.0
    assert "gpu0.pcie_replay" not in got  # non supportato: nessun campione
    c.close()


def test_nvml_unavailable(monkeypatch):
    monkeypatch.setitem(sys.modules, "pynvml", None)
    with pytest.raises(CollectorUnavailable):
        NvmlCollector({}).start()


LHM = {"Children": [{"Text": "PC", "Children": [
    {"Text": "CPU Package", "Value": "61.0 °C", "SensorId": "/amdcpu/0/temperature/2",
     "Type": "Temperature"},
    {"Text": "Package", "Value": "88,5 W", "SensorId": "/amdcpu/0/power/0", "Type": "Power"},
    {"Text": "GPU Hot Spot", "Value": "80.1 °C", "SensorId": "/gpu-nvidia/0/temperature/2",
     "Type": "Temperature"},
    {"Text": "Fan #1", "Value": "900 RPM", "SensorId": "/lpc/nct6798d/fan/0", "Type": "Fan"},
]}]}


@pytest.fixture
def lhm_server():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps(LHM).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/data.json"
    srv.shutdown()


def test_lhm_web_collector(lhm_server):
    c = LhmCollector({"mode": "web", "url": lhm_server, "timeout_s": 2})
    c.start()
    got = {s.channel: s.value for s in c.poll(0, 0.0)}
    assert got["cpu.pkg.temp_c"] == 61.0
    assert got["cpu.pkg.power_w"] == 88.5
    assert got["gpu0.temp_hotspot_c"] == pytest.approx(80.1)
    assert got["chassis.fan1_rpm"] == 900


def test_lhm_unreachable_and_non_loopback():
    with pytest.raises(CollectorUnavailable):
        LhmCollector({"mode": "web", "url": "http://127.0.0.1:9/data.json",
                      "timeout_s": 0.5}).start()
    with pytest.raises(ValueError):
        LhmCollector({"mode": "web", "url": "http://10.0.0.5:8085/data.json"}).start()
    with pytest.raises(CollectorUnavailable):
        LhmCollector({"mode": "dll", "dll_path": None}).start()


def test_psutil_collector():
    c = PsutilCollector({})
    c.start()
    s = c.poll(0, 0.0)[0]
    assert s.channel == "cpu.load_pct" and 0 <= s.value <= 100


def test_linux_hwmon(tmp_path, monkeypatch):
    from hwdrift.collectors import linux_hwmon as lh

    chip = tmp_path / "hwmon0"
    chip.mkdir()
    (chip / "name").write_text("k10temp\n")
    (chip / "temp1_input").write_text("55125\n")
    (chip / "temp1_label").write_text("Tctl\n")
    (chip / "fan1_input").write_text("1200\n")
    rapl = tmp_path / "energy_uj"
    rapl.write_text("1000000")
    monkeypatch.setattr(lh, "HWMON", tmp_path)
    monkeypatch.setattr(lh, "RAPL", rapl)
    c = lh.LinuxHwmonCollector({})
    c.start()
    c.poll(0, 0.0)
    rapl.write_text("51000000")  # +50 J in 1 s = 50 W
    got = {s.channel: s.value for s in c.poll(1000, 1.0)}
    assert got["cpu.pkg.temp_c"] == pytest.approx(55.125)
    assert got["cpu.pkg.power_w"] == pytest.approx(50.0)


def test_smart_collector(tmp_path):
    from hwdrift.collectors.smart import SmartCollector

    exe = tmp_path / "smartctl"
    exe.write_text("#!/bin/sh\necho '{\"temperature\": {\"current\": 41}}'\n")
    exe.chmod(0o755)
    c = SmartCollector({"devices": ["/dev/sda"], "smartctl": str(exe)})
    if sys.platform == "win32":
        pytest.skip("script shell")
    c.start()
    assert c.poll(0, 0.0)[0].value == 41.0
    with pytest.raises(ValueError):
        SmartCollector({"devices": ["/dev/sda; rm -rf /"]}).start()
    with pytest.raises(CollectorUnavailable):
        SmartCollector({"devices": []}).start()


def test_sysinfo_linux(monkeypatch, tmp_path):
    from hwdrift.collectors import wmi_info

    if sys.platform == "win32":
        pytest.skip("percorso Linux")
    c = wmi_info.SysInfoCollector({})
    c.start()
    c.poll(0, 0.0)  # non deve sollevare anche senza /sys/class/dmi
    assert all(e.kind == "observe" for e in c.drain_events())


def test_eventlog_unavailable_off_windows():
    from hwdrift.collectors.eventlog import EventLogCollector

    if sys.platform == "win32":
        pytest.skip("solo fuori da Windows")
    with pytest.raises(CollectorUnavailable):
        EventLogCollector({}).start()


def test_build_collectors_respects_config(cfg):
    names = [c.name for c in build_collectors(cfg)]
    assert names[:3] == ["lhm", "nvml", "eventlog"] and "smart" not in names
    cfg["sources"]["simulator"]["enabled"] = True
    assert [c.name for c in build_collectors(cfg)] == ["simulator"]


def test_selftest_with_simulator(cfg):
    from hwdrift.selftest import run_selftest

    cfg["sources"]["simulator"]["enabled"] = True
    r = run_selftest(cfg, seconds=1.5)
    assert r["ticks"] >= 1 and r["collectors"][0]["ok"]
    assert r["rss_mb_peak"] > 0


def test_healthcheck_aborts_on_temperature():
    from hwdrift.healthcheck import healthcheck_event, run_healthcheck

    temps = iter([60.0, 70.0, 95.0, 96.0])
    res = run_healthcheck(lambda: next(temps, 96.0), lambda: False, duration_s=10,
                          abort_temp_c=90, workers=1, poll_s=0.05)
    assert not res.completed and "temperatura" in res.reason and res.max_temp == 95.0
    assert healthcheck_event(res, 0).detail["completed"] is False
    res2 = run_healthcheck(lambda: None, lambda: False, duration_s=5, abort_temp_c=90,
                           workers=1, poll_s=0.05, stale_limit_s=0.2)
    assert "nessun dato" in res2.reason
    res3 = run_healthcheck(lambda: 50.0, lambda: False, duration_s=0.2, abort_temp_c=90,
                           workers=1, poll_s=0.05)
    assert res3.completed
