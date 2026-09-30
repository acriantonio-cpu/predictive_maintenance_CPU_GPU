# SPDX-License-Identifier: Apache-2.0
import numpy as np
import pytest

from hwdrift.context.components import components
from hwdrift.context.minutes import MinuteFrame
from hwdrift.context.regimes import RegimeBounds, calibrate
from hwdrift.context.windows import find_windows
from hwdrift.indicators import baseline as bl
from hwdrift.indicators.rth import window_indicators

PARAMS = {"length_min": 5, "warmup_min": 3, "power_cv_max": 0.10, "temp_slope_max": 0.5,
          "util_std_max": 10.0, "min_valid_frac": 0.8, "min_power_w": 1.0}
CPU = components({"cpu.pkg.power_w", "cpu.pkg.temp_c"})[0]


def frame(power, temp, thr=None, valid=None, t0=0):
    n = len(power)
    ts = np.arange(n, dtype=np.int64) * 60_000 + t0
    med = {"cpu.pkg.power_w": np.asarray(power, float), "cpu.pkg.temp_c": np.asarray(temp, float)}
    mx = dict(med)
    if thr is not None:
        med["cpu.throttle_thermal"] = np.asarray(thr, float)
        mx["cpu.throttle_thermal"] = np.asarray(thr, float)
    v = np.ones(n) if valid is None else np.asarray(valid, float)
    return MinuteFrame(ts, med, dict(med), mx, {k: v for k in med})


def test_stable_block_produces_non_overlapping_windows():
    mf = frame([50.0] * 20, [60.0] * 20)
    w = find_windows(mf, CPU, PARAMS, [], None)
    assert len(w) == 3  # minuti 3-7, 8-12, 13-17 (3 di riscaldamento)
    assert w[0].start_ts == 3 * 60_000 and w[0].end_ts == 8 * 60_000
    assert not w[0].throttled and w[0].summary["p"] == pytest.approx(50.0)


def test_transient_and_unstable_power_excluded():
    ramp = frame([50.0] * 20, list(np.linspace(40, 60, 20)))  # +1 °C/min
    assert find_windows(ramp, CPU, PARAMS, [], None) == []
    noisy = frame([50, 80] * 10, [60.0] * 20)
    assert find_windows(noisy, CPU, PARAMS, [], None) == []


def test_warmup_required_after_load_change():
    mf = frame([10.0] * 10 + [50.0] * 7, [30.0] * 10 + [60.0] * 7)
    w = find_windows(mf, CPU, PARAMS, [], None)
    assert all(x.power_mean < 20 or x.start_ts >= 13 * 60_000 for x in w)


def test_gap_and_bad_quality_and_confounder_excluded():
    mf = frame([50.0] * 20, [60.0] * 20, valid=[1.0] * 5 + [0.5] + [1.0] * 14)
    w = find_windows(mf, CPU, PARAMS, [], None)
    assert all(x.start_ts > 5 * 60_000 for x in w)
    mf2 = frame([50.0] * 20, [60.0] * 20)
    mf2.ts[10:] += 3_600_000  # buco di un'ora
    assert all(x.end_ts <= 10 * 60_000 or x.start_ts >= mf2.ts[13] for x in
               find_windows(mf2, CPU, PARAMS, [], None))
    w3 = find_windows(frame([50.0] * 20, [60.0] * 20), CPU, PARAMS, [6 * 60_000], None)
    assert all(not (x.start_ts - 3 * 60_000 <= 6 * 60_000 <= x.end_ts) for x in w3)


def test_throttled_window_marked_and_excluded_from_rth():
    mf = frame([50.0] * 12, [60.0] * 12, thr=[0] * 5 + [1] + [0] * 6)
    w = find_windows(mf, CPU, PARAMS, [], None)
    assert w[0].throttled and w[0].summary["throttle_thermal"]
    assert window_indicators("cpu", "high", w[0].summary, True, False) == []


def test_window_indicators():
    s = {"t": 70.0, "p": 100.0, "tref": 30.0, "fan": 1500.0, "hotspot": 80.0, "mb": 35.0}
    got = dict(window_indicators("cpu", "high", s, False, True))
    assert got["rth_cpu"] == pytest.approx(0.4)
    assert got["fan_effort_cpu"] == 1500.0
    assert got["case_delta_cpu"] == pytest.approx(5.0)
    idle = dict(window_indicators("gpu", "idle", dict(s, fan=0.0), False, True))
    assert "rth_gpu" not in idle and idle["idle_temp_gpu"] == pytest.approx(40.0)
    assert "fan_effort_gpu" not in idle  # ventola ferma a riposo: non è uno sforzo


def test_regimes_fixed_and_adaptive():
    wp = np.r_[np.full(50, 10.0), np.full(30, 50.0), np.full(20, 100.0)]
    b = calibrate(wp, np.r_[wp, [300.0]], "fixed", [0.3, 0.65])
    assert b.pmax == pytest.approx(np.percentile(np.r_[wp, [300.0]], 99))
    assert b.assign(5) == "idle" and b.assign(b.hi + 1) == "high"
    a = calibrate(wp, wp, "adaptive", [0.3, 0.65])
    assert a.lo == pytest.approx(10.0) and a.hi == pytest.approx(50.0)
    assert RegimeBounds.from_dict(a.to_dict()) == a
    with pytest.raises(ValueError):
        calibrate(np.array([]), np.array([]), "fixed", [0.3, 0.6])


def test_huber_recovers_coefficients_despite_outliers():
    rng = np.random.default_rng(0)
    p = rng.uniform(20, 120, 200)
    tref = rng.uniform(20, 30, 200)
    y = 5 + 0.3 * p + 1.0 * tref + rng.normal(0, 0.3, 200)
    y[:10] += 30  # outlier
    m = bl.fit({"p": p, "tref": tref}, ("1", "p", "tref"), y)
    assert m.coef[1] == pytest.approx(0.3, abs=0.01)
    assert m.coef[2] == pytest.approx(1.0, abs=0.05)
    r = bl.residuals(m, {"p": p, "tref": tref}, y)
    assert np.median(np.abs(r[10:])) < 0.5
    assert bl.LinearModel.from_dict(m.to_dict()) == m
    with pytest.raises(ValueError):
        bl.huber_fit(np.ones((2, 3)), np.ones(2))


def test_continuous_design_has_square_term():
    X = bl.design(bl.CONTINUOUS, {"p": np.array([2.0]), "tref": np.array([1.0])})
    assert X.tolist() == [[1.0, 2.0, 4.0, 1.0]]


def test_recovery_outcome():
    from hwdrift.reporting.html_report import recovery_outcome

    assert recovery_outcome(3.0, -2.5) == "recuperato"  # sotto il baseline: meglio di prima
    assert recovery_outcome(3.0, 1.0) == "recuperato"
    assert recovery_outcome(5.0, 3.0) == "migliorato"
    assert recovery_outcome(3.0, 3.2) == "non migliorato"
    assert recovery_outcome(0.2, 0.1) == "nessuna deriva prima"
