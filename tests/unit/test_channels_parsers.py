# SPDX-License-Identifier: Apache-2.0
import json

import pytest

from hwdrift.channels import ChannelMap, is_valid_channel_name, propose_channel, spec_for
from hwdrift.collectors.eventlog import EVENT_MAP, _iso_to_ms, parse_events
from hwdrift.collectors.hwinfo_csv import map_column, parse_hwinfo_csv
from hwdrift.collectors.lhm import check_loopback, hw_from_id, iter_sensors, parse_value


@pytest.mark.parametrize(("hw", "kind", "name", "sid", "expected"), [
    ("cpu", "Temperature", "CPU Package", "/intelcpu/0/temperature/0", "cpu.pkg.temp_c"),
    ("cpu", "Temperature", "Core (Tctl/Tdie)", "/amdcpu/0/temperature/2", "cpu.pkg.temp_c"),
    ("cpu", "Power", "Package", "/amdcpu/0/power/0", "cpu.pkg.power_w"),
    ("cpu", "Load", "CPU Total", "/intelcpu/0/load/0", "cpu.load_pct"),
    ("gpu", "Temperature", "GPU Core", "/gpu-nvidia/0/temperature/0", "gpu0.temp_edge_c"),
    ("gpu", "Temperature", "GPU Hot Spot", "/gpu-nvidia/1/temperature/2", "gpu1.temp_hotspot_c"),
    ("gpu", "Power", "GPU Package", "/gpu-nvidia/0/power/0", "gpu0.power_w"),
    ("superio", "Fan", "Fan #2", "/lpc/nct6798d/fan/1", "chassis.fan2_rpm"),
    ("superio", "Fan", "CPU Fan", "/lpc/nct6798d/fan/0", "cpu.fan_rpm"),
    ("storage", "Temperature", "Temperature", "/nvme/0/temperature/0", "ssd0.temp_c"),
    ("cpu", "Voltage", "Core", "/intelcpu/0/voltage/0", None),
])
def test_propose_channel(hw, kind, name, sid, expected):
    assert propose_channel(hw, kind, name, sid) == expected


def test_channel_map_override_and_exclusion():
    m = ChannelMap({"/a": "mb.temp_c", "/b": ""}, auto=True)
    assert m.resolve("/a", "x", "y", "z") == "mb.temp_c"
    assert m.resolve("/b", "cpu", "Temperature", "CPU Package") is None
    assert ChannelMap({}, auto=False).resolve("/c", "cpu", "Temperature", "CPU Package") is None


def test_specs_and_names():
    assert spec_for("gpu3.temp_hotspot_c").unit == "°C"
    assert spec_for("status.lhm").unit == "flag"
    assert spec_for("banana") is None
    assert is_valid_channel_name("cpu.pkg.temp_c")
    assert not is_valid_channel_name("CPU Package")


LHM_JSON = {"id": 0, "Text": "Sensor", "Children": [{"Text": "PC", "Children": [
    {"Text": "Intel Core i7", "Children": [{"Text": "Temperatures", "Children": [
        {"Text": "CPU Package", "Value": "55,5 °C", "SensorId": "/intelcpu/0/temperature/0",
         "Type": "Temperature"}]}]},
    {"Text": "Powers", "Children": [
        {"Text": "Package", "Value": "35.2 W", "SensorId": "/intelcpu/0/power/0",
         "Type": "Power"},
        {"Text": "Broken", "Value": "-", "SensorId": "/intelcpu/0/power/9", "Type": "Power"}]},
]}]}


def test_lhm_tree_parsing():
    nodes = list(iter_sensors(json.loads(json.dumps(LHM_JSON))))
    assert [n["SensorId"] for n in nodes] == ["/intelcpu/0/temperature/0",
                                              "/intelcpu/0/power/0", "/intelcpu/0/power/9"]
    assert parse_value("55,5 °C") == (55.5, "°C")
    assert parse_value("-") == (None, "")
    assert hw_from_id("/gpu-amd/0/x") == "gpu"


def test_lhm_depth_limit():
    node: dict = {"Text": "x"}
    cur = node
    for _ in range(100):
        nxt: dict = {"Text": "x"}
        cur["Children"] = [nxt]
        cur = nxt
    cur["SensorId"] = "/deep"
    assert list(iter_sensors(node)) == []


@pytest.mark.parametrize("url", ["http://127.0.0.1:8085/data.json", "http://localhost:8085/x",
                                 "http://[::1]:8085/data.json"])
def test_loopback_ok(url):
    check_loopback(url)


@pytest.mark.parametrize("url", ["http://192.168.1.2:8085/data.json", "https://127.0.0.1/",
                                 "http://example.com/data.json"])
def test_loopback_rejected(url):
    with pytest.raises(ValueError):
        check_loopback(url)


WEVT = """<Event xmlns='http://schemas.microsoft.com/win/2004/08/events/event'><System>
<Provider Name='Microsoft-Windows-WHEA-Logger' Guid='{x}'/><EventID>19</EventID>
<TimeCreated SystemTime='2026-09-01T10:00:00.1234567Z'/><EventRecordID>4242</EventRecordID>
</System></Event><Event xmlns='http://schemas.microsoft.com/win/2004/08/events/event'><System>
<Provider Name='Display'/><EventID>4101</EventID><EventRecordID>7</EventRecordID></System></Event>"""


def test_eventlog_parse():
    evs = parse_events(WEVT)
    assert [(e["provider"], e["event_id"], e["record_id"]) for e in evs] == [
        ("Microsoft-Windows-WHEA-Logger", 19, "4242"), ("Display", 4101, "7")]
    assert EVENT_MAP[("Display", 4101)] == "hw.tdr"
    assert _iso_to_ms("2026-09-01T10:00:00.1234567Z", 0) == 1788256800123
    assert _iso_to_ms("garbage", 5) == 5


def test_eventlog_rejects_dtd():
    with pytest.raises(ValueError):
        parse_events('<!DOCTYPE x [<!ENTITY a "b">]><Event/>')


HWINFO = (
    '"Date","Time","CPU Package [°C]","CPU Package Power [W]","Total CPU Usage [%]",'
    '"GPU Temperature [°C]","GPU Hot Spot Temperature [°C]","Core Thermal Throttling [Yes/No]",'
    '"Drive Temperature [°C]","Drive Temperature [°C]","Something Else [V]",\n'
    '"30.9.2026","12:00:00.123","55,0","30.5","12","45","52","No","35","38","1.2",\n'
    '"30.9.2026","12:00:02.123","56","31","14","46","53","Yes","35","38","1.2",\n'
    '"30.9.2026","bad time","x","x","x","x","x","x","x","x","x",\n'
    '"Date","Time","CPU Package [°C]",\n'
    '"","","CPU [#0]: Intel",\n'
)


def test_hwinfo_parse():
    samples = list(parse_hwinfo_csv(HWINFO, tz_offset_h=0))
    chans = sorted({s.channel for s in samples})
    assert chans == ["cpu.load_pct", "cpu.pkg.power_w", "cpu.pkg.temp_c", "cpu.throttle_thermal",
                     "gpu0.temp_edge_c", "gpu0.temp_hotspot_c", "ssd0.temp_c", "ssd1.temp_c"]
    t = [s for s in samples if s.channel == "cpu.pkg.temp_c"]
    assert [x.value for x in t] == [55.0, 56.0]
    assert t[0].ts_ms == 1790769600123  # 2026-09-30T12:00:00.123Z
    thr = [s.value for s in samples if s.channel == "cpu.throttle_thermal"]
    assert thr == [0.0, 1.0]


def test_hwinfo_mapping_override_and_bad_file():
    samples = list(parse_hwinfo_csv(HWINFO, {"Something Else [V]": "cpu.vcore_v",
                                             "CPU Package [°C]": ""}, 0))
    chans = {s.channel for s in samples}
    assert "cpu.vcore_v" in chans and "cpu.pkg.temp_c" not in chans
    with pytest.raises(ValueError):
        list(parse_hwinfo_csv("a,b,c\n1,2,3\n"))
    assert map_column("GPU Fan [RPM]", 0) == ("gpu0.fan_rpm", "RPM")
