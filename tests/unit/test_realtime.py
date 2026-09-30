# SPDX-License-Identifier: Apache-2.0
"""Failure mode 11: errori immediati con debounce, gravità e una notifica per episodio."""

from hwdrift.quality.realtime_events import (
    NVML_GPU_IDLE,
    NVML_HW_THERMAL,
    NVML_SW_POWER_CAP,
    RealtimeConfig,
    RealtimeDetector,
)


def make():
    events = []
    det = RealtimeDetector(RealtimeConfig(debounce_s=5, release_s=10, nominal_clock_mhz=3600),
                           lambda action, ep: events.append((action, ep.component, ep.reason,
                                                             ep.severity)))
    return det, events


CPU_THROTTLE = {"cpu.pkg.temp_c": 97.0, "cpu.load_pct": 100.0, "cpu.clock_eff_mhz": 1800.0,
                "cpu.pkg.power_w": 40.0}


def test_debounce_then_single_open_and_close():
    det, ev = make()
    for t in range(4):
        det.update(CPU_THROTTLE, float(t), t * 1000)
    assert ev == []  # sotto il debounce
    for t in range(4, 30):
        det.update(CPU_THROTTLE, float(t), t * 1000)
    assert [e[0] for e in ev].count("open") == 1
    assert ev[0][1:] == ("cpu", "thermal", "error")  # carico non prolungato -> errore
    for t in range(30, 45):
        det.update({"cpu.pkg.temp_c": 60.0, "cpu.load_pct": 100.0}, float(t), t * 1000)
    assert ev[-1][0] == "close"


def test_short_blip_is_ignored():
    det, ev = make()
    det.update(CPU_THROTTLE, 0.0, 0)
    det.update(CPU_THROTTLE, 2.0, 2000)
    for t in range(3, 30):
        det.update({"cpu.pkg.temp_c": 60.0}, float(t), t * 1000)
    assert ev == []


def test_sustained_high_load_is_warning():
    det, ev = make()
    base = {"cpu.pkg.temp_c": 70.0, "cpu.load_pct": 100.0, "cpu.clock_eff_mhz": 4000.0,
            "cpu.pkg.power_w": 120.0}
    for t in range(0, 15 * 60):
        det.update(base, float(t), t * 1000)
    hot = dict(base, **{"cpu.pkg.temp_c": 96.0, "cpu.clock_eff_mhz": 2000.0,
                        "cpu.pkg.power_w": 110.0})
    for t in range(15 * 60, 15 * 60 + 20):
        det.update(hot, float(t), t * 1000)
    assert ("open", "cpu", "thermal", "warning") in ev


def test_power_limit_is_info_and_gpu_idle_ignored():
    det, ev = make()
    for t in range(20):
        det.update({"gpu0.throttle_reasons": float(NVML_SW_POWER_CAP), "gpu0.power_w": 200.0},
                   float(t), t * 1000)
    assert ("open", "gpu0", "power_limit", "info") in ev
    det2, ev2 = make()
    for t in range(20):
        det2.update({"gpu0.throttle_reasons": float(NVML_GPU_IDLE)}, float(t), t * 1000)
    assert ev2 == []


def test_gpu_thermal_and_escalation():
    det, ev = make()
    for t in range(20):
        det.update({"gpu0.throttle_reasons": float(NVML_SW_POWER_CAP), "gpu0.power_w": 200.0},
                   float(t), t * 1000)
    for t in range(20, 40):
        det.update({"gpu0.throttle_reasons": float(NVML_HW_THERMAL), "gpu0.power_w": 100.0,
                    "gpu0.temp_edge_c": 88.0}, float(t), t * 1000)
    assert any(e[0] == "open" and e[2] == "thermal" and e[3] == "error" for e in ev)


def test_fan_stopped():
    det, ev = make()
    for t in range(20):
        det.update({"cpu.fan_rpm": 0.0, "cpu.pkg.temp_c": 85.0}, float(t), t * 1000)
    assert ("open", "cpu", "fan_stopped", "error") in ev
    det2, ev2 = make()  # ventola GPU ferma a riposo: normale
    for t in range(20):
        det2.update({"gpu0.fan_rpm": 0.0, "gpu0.temp_edge_c": 40.0, "gpu0.util_pct": 2.0},
                    float(t), t * 1000)
    assert ev2 == []


def test_cpu_at_tjmax_without_clock_data():
    """Audit: con solo LHM (nessun clock effettivo) il throttling CPU va rilevato lo stesso."""
    det, ev = make()
    for t in range(20):
        det.update({"cpu.pkg.temp_c": 99.5, "cpu.load_pct": 95.0}, float(t), t * 1000)
    assert any(e[0] == "open" and e[2] == "thermal" for e in ev)
