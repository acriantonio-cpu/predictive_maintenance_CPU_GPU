# SPDX-License-Identifier: Apache-2.0
import numpy as np
import pytest

from hwdrift.spc import assumptions as a


def ar1(phi, n, seed=0):
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    for i in range(1, n):
        x[i] = phi * x[i - 1] + rng.normal()
    return x


def test_acf_white_noise_and_ar1():
    assert abs(a.acf(np.random.default_rng(0).normal(size=2000))) < 0.06
    assert a.acf(ar1(0.8, 3000)) == pytest.approx(0.8, abs=0.05)


def test_ljung_box():
    _, p_white = a.ljung_box(np.random.default_rng(3).normal(size=300))
    _, p_ar = a.ljung_box(ar1(0.7, 300))
    assert p_white > 0.01 and p_ar < 1e-6


def test_check_flags():
    r = a.check(ar1(0.8, 200))
    assert r["autocorrelated"] is True
    skewed = np.random.default_rng(0).exponential(size=200)
    r2 = a.check(skewed)
    assert r2["non_normal"] is True and r2["sigma_recommended"] == "robust"


def test_ar1_residuals_whiten():
    res = a.ar1_residuals(ar1(0.8, 2000))
    assert abs(a.acf(res)) < 0.1
