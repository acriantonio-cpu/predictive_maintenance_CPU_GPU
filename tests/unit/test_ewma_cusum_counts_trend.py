# SPDX-License-Identifier: Apache-2.0
import numpy as np
import pytest

from hwdrift.spc.count_charts import c_chart, c_signals, u_chart
from hwdrift.spc.cusum import cusum
from hwdrift.spc.ewma import ewma
from hwdrift.spc.trend import linear_trend, mann_kendall


def test_ewma_hand_values():
    r = ewma([1.0, 1.0], mu=0.0, sigma=1.0, lam=0.2, L=3.0)
    assert r.z[0] == pytest.approx(0.2)
    assert r.z[1] == pytest.approx(0.2 * 1 + 0.8 * 0.2)
    # limite al primo punto: L*sigma*sqrt(lam/(2-lam)*(1-(1-lam)^2))
    w1 = 3 * np.sqrt(0.2 / 1.8 * (1 - 0.8 ** 2))
    assert r.ucl[0] == pytest.approx(w1)


def test_ewma_detects_small_shift_before_r1():
    rng = np.random.default_rng(1)
    x = np.r_[rng.normal(0, 1, 50), rng.normal(1.0, 1, 50)]
    r = ewma(x, 0.0, 1.0)
    first = [i for i, side in r.signals if side == "upper"]
    assert first and first[0] >= 50


def test_ewma_bad_lambda():
    with pytest.raises(ValueError):
        ewma([1.0], 0, 1, lam=0)


def test_cusum_hand_values():
    r = cusum([1.0, 1.0, 1.0], mu=0.0, sigma=1.0, k=0.5, h=0.9)
    assert list(r.c_plus) == pytest.approx([0.5, 1.0, 1.5])
    assert r.signals == [(1, "upper")]


def test_cusum_lower_and_sigma_check():
    r = cusum([-2.0] * 5, 0.0, 1.0, 0.5, 4.0)
    assert (2, "lower") in r.signals
    with pytest.raises(ValueError):
        cusum([1.0], 0.0, 0.0)


def test_c_chart():
    lim = c_chart([4, 4, 4, 4])
    assert lim.center == 4 and lim.ucl == pytest.approx(10.0) and lim.lcl == 0.0
    assert c_signals([3, 11, 10], lim) == [1]
    zero = c_chart([0, 0, 0])
    assert zero.ucl == 0.0 and c_signals([0, 1], zero) == [1]


def test_u_chart():
    ubar, ucl, _lcl = u_chart([2, 4], [10, 10])
    assert ubar == pytest.approx(0.3)
    assert ucl[0] == pytest.approx(0.3 + 3 * np.sqrt(0.03))
    with pytest.raises(ValueError):
        u_chart([1], [0])


def test_mann_kendall_hand():
    # x = 1,2,3: S = 3 (tutte le coppie crescenti), var = 3*2*11/18
    r = mann_kendall([1.0, 2.0, 3.0])
    assert r.s == 3
    assert r.var_s == pytest.approx(3 * 2 * 11 / 18)
    assert r.tau == pytest.approx(1.0)
    assert r.sen_slope == pytest.approx(1.0)


def test_mann_kendall_detects_trend_and_ties():
    x = np.arange(30) * 0.1 + np.random.default_rng(0).normal(0, 0.2, 30)
    r = mann_kendall(x)
    assert r.p < 0.01 and r.tau > 0
    flat = mann_kendall([1.0] * 10)
    assert flat.s == 0 and flat.p == 1.0


def test_linear_trend():
    slope, p = linear_trend(np.arange(20) * 2.0 + 1)
    assert slope == pytest.approx(2.0) and p < 1e-6
