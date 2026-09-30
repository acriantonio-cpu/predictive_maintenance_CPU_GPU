# SPDX-License-Identifier: Apache-2.0
"""Test di proprietà (hypothesis) e ARL su serie sintetiche (sezione 7)."""

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from hwdrift.spc.imr import imr_limits
from hwdrift.spc.rules import evaluate

series = st.lists(st.floats(-1e3, 1e3, allow_nan=False), min_size=3, max_size=60).filter(
    lambda x: np.std(x) > 1e-6)
scale = st.floats(0.01, 1e3)
shift = st.floats(-1e4, 1e4)


@given(series, scale, shift)
@settings(max_examples=200, deadline=None)
def test_limits_affine_equivariant(x, a, b):
    lim = imr_limits(x)
    lim2 = imr_limits(np.asarray(x) * a + b)
    assert lim2.center == pytest.approx(lim.center * a + b, rel=1e-6, abs=1e-6)
    assert lim2.sigma == pytest.approx(lim.sigma * a, rel=1e-6, abs=1e-9)
    assert lim2.ucl == pytest.approx(lim.ucl * a + b, rel=1e-6, abs=1e-6)


@given(series, scale, shift)
@settings(max_examples=100, deadline=None)
def test_signals_invariant_under_positive_affine_transform(x, a, b):
    x = np.asarray(x)
    s1 = {(s.index, s.rule, s.side) for s in evaluate(x, imr_limits(x), ["R1", "R2", "R3"])}
    y = x * a + b
    s2 = {(s.index, s.rule, s.side) for s in evaluate(y, imr_limits(y), ["R1", "R2", "R3"])}
    # l'unica differenza ammessa è su punti a filo del limite (arrotondamento)
    assert len(s1 ^ s2) <= 1


@given(series, st.floats(1.0, 3.0))
@settings(max_examples=100, deadline=None)
def test_widening_is_monotone(x, w):
    a, b = imr_limits(x), imr_limits(x, widen=w)
    assert b.ucl >= a.ucl - 1e-9 and b.lcl <= a.lcl + 1e-9
    n1 = len(evaluate(x, a, ["R1"], include_mr=False))
    n2 = len(evaluate(x, b, ["R1"], include_mr=False))
    assert n2 <= n1


@given(series)
@settings(max_examples=100, deadline=None)
def test_mr_sigma_nonnegative_and_limits_ordered(x):
    lim = imr_limits(x)
    assert lim.sigma >= 0 and lim.lcl <= lim.center <= lim.ucl and lim.ucl_mr >= 0


def run_lengths(rng, n_runs, shift_sigma=0.0, max_len=5000):
    out = []
    for _ in range(n_runs):
        x = rng.normal(shift_sigma, 1.0, max_len)
        hit = np.flatnonzero(np.abs(x) > 3)
        out.append(int(hit[0]) + 1 if hit.size else max_len)
    return np.array(out)


def test_arl0_r1_close_to_370():
    rng = np.random.default_rng(2026)
    rl = run_lengths(rng, 800)
    # ARL0 teorico 370.4; con 800 corse l'errore standard è ~13
    assert 320 < rl.mean() < 420


def test_arl1_decreases_with_shift():
    rng = np.random.default_rng(7)
    arl = [run_lengths(rng, 300, s).mean() for s in (0.0, 1.0, 2.0, 3.0)]
    assert arl[0] > arl[1] > arl[2] > arl[3]
    assert arl[3] < 3  # shift di 3 sigma: ~2 punti
