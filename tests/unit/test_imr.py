# SPDX-License-Identifier: Apache-2.0
"""Carta I-MR: valori calcolati a mano (sezione 7: "le costanti vanno verificate con un
esempio calcolato a mano nei test")."""

import math

import numpy as np
import pytest

from hwdrift.spc.imr import D2, D4, imr_limits, moving_ranges, phase_one


def test_hand_computed_example():
    x = [10.0, 12.0, 11.0, 13.0, 12.0]
    # MR = |12-10|, |11-12|, |13-11|, |12-13| = 2, 1, 2, 1 -> MR_bar = 1.5
    assert list(moving_ranges(x)) == [2.0, 1.0, 2.0, 1.0]
    lim = imr_limits(x)
    assert lim.center == pytest.approx(11.6)
    assert lim.mr_bar == pytest.approx(1.5)
    assert lim.sigma == pytest.approx(1.5 / 1.128)
    # UCL = X_bar + 2.66 * MR_bar (2.66 = 3 / 1.128 arrotondato)
    assert lim.ucl == pytest.approx(11.6 + 3 * 1.5 / 1.128)
    assert lim.ucl == pytest.approx(11.6 + 2.66 * 1.5, abs=0.002)
    assert lim.lcl == pytest.approx(11.6 - 3 * 1.5 / 1.128)
    # UCL_MR = 3.267 * MR_bar
    assert lim.ucl_mr == pytest.approx(3.267 * 1.5)


def test_constants():
    assert D2 == 1.128
    assert D4 == 3.267
    assert pytest.approx(2.66, abs=0.001) == 3 / D2


def test_robust_sigma():
    x = [10.0, 12.0, 11.0, 13.0, 12.0]
    lim = imr_limits(x, "robust")
    assert lim.sigma == pytest.approx(np.median([2, 1, 2, 1]) / 0.954)


def test_longterm_sigma():
    x = [1.0, 2.0, 3.0, 4.0]
    assert imr_limits(x, "longterm").sigma == pytest.approx(np.std(x, ddof=1))


def test_widen_scales_limits_not_center():
    x = [1.0, 3.0, 2.0, 4.0, 3.0]
    a, b = imr_limits(x), imr_limits(x, widen=1.25)
    assert b.center == a.center
    assert (b.ucl - b.center) == pytest.approx(1.25 * (a.ucl - a.center))


def test_needs_two_points():
    with pytest.raises(ValueError):
        imr_limits([1.0])
    with pytest.raises(ValueError):
        imr_limits([1.0, 2.0], "bogus")


def test_phase_one_removes_assignable_cause():
    rng = np.random.default_rng(0)
    x = rng.normal(50, 1, 30)
    x[7] = 70.0  # causa assegnabile
    res = phase_one(x, max_iter=3)
    assert 7 in res.excluded
    assert res.limits.center == pytest.approx(np.delete(x, res.excluded).mean())
    assert res.iterations >= 1
    assert math.isfinite(res.limits.sigma)


def test_phase_one_stops_when_clean():
    x = np.array([5.0, 5.2, 4.9, 5.1, 5.0, 4.8, 5.1, 5.2, 4.9, 5.0] * 3)
    res = phase_one(x)
    assert res.excluded == []
    assert res.iterations == 0
