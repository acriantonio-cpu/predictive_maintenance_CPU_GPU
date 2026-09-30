# SPDX-License-Identifier: Apache-2.0
import numpy as np

from hwdrift.spc.imr import Limits
from hwdrift.spc.rules import evaluate, false_alarm_arl_r1

LIM = Limits(center=0.0, sigma=1.0, mr_bar=1.128, ucl=3.0, lcl=-3.0, ucl_mr=3.267 * 1.128)


def rules_of(sigs):
    return {(s.rule, s.side, s.index) for s in sigs}


def test_r1_both_sides():
    s = evaluate([0, 3.5, 0, -3.2], LIM, ["R1"], include_mr=False)
    assert rules_of(s) == {("R1", "upper", 1), ("R1", "lower", 3)}


def test_r2_nine_same_side():
    x = [0.5] * 8
    assert not evaluate(x, LIM, ["R2"], include_mr=False)
    x = [0.5] * 9
    s = evaluate(x, LIM, ["R2"], include_mr=False)
    assert rules_of(s) == {("R2", "upper", 8)}
    assert s[0].points == tuple(range(9))


def test_r2_reset_on_center():
    x = [0.5] * 5 + [0.0] + [0.5] * 5
    assert not evaluate(x, LIM, ["R2"], include_mr=False)


def test_r3_six_increasing():
    x = [0, 0.1, 0.2, 0.3, 0.4]  # 5 punti: non basta
    assert not evaluate(x, LIM, ["R3"], include_mr=False)
    x = [0, 0.1, 0.2, 0.3, 0.4, 0.5]
    s = evaluate(x, LIM, ["R3"], include_mr=False)
    assert rules_of(s) == {("R3", "upper", 5)}
    s = evaluate(list(reversed(x)), LIM, ["R3"], include_mr=False)
    assert rules_of(s) == {("R3", "lower", 5)}


def test_r3_flat_breaks_run():
    x = [0, 0.1, 0.2, 0.2, 0.3, 0.4, 0.5]
    assert not evaluate(x, LIM, ["R3"], include_mr=False)


def test_r4_two_of_three():
    x = [2.5, 0, 2.2]
    s = evaluate(x, LIM, ["R4"], include_mr=False)
    assert ("R4", "upper", 2) in rules_of(s)
    assert not evaluate([2.5, 0, 0], LIM, ["R4"], include_mr=False)


def test_mr_step():
    x = [0, 0, 5, 5]
    s = evaluate(x, LIM, [], include_mr=True)
    assert ("MR", "upper", 2) in rules_of(s)


def test_arl0_r1_theory():
    assert 369 < false_alarm_arl_r1() < 372


def test_empty():
    assert evaluate(np.array([]), LIM) == []
