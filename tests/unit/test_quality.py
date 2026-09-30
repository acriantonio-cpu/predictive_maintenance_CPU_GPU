# SPDX-License-Identifier: Apache-2.0
"""Failure mode 7: dati non affidabili (glitch, fuori scala, congelati)."""

from hwdrift.model import Quality, Sample
from hwdrift.quality.sanity import QualityChecker


def s(ch, v, t):
    return Sample(int(t * 1000), "test", ch, "cpu", ch, v, "", ch, mono_s=t)


def test_glitch_and_range():
    qc = QualityChecker()
    assert qc.check(s("cpu.pkg.temp_c", 255.0, 0)).quality == Quality.GLITCH
    assert qc.check(s("cpu.pkg.temp_c", 0.0, 1)).quality == Quality.GLITCH
    assert qc.check(s("cpu.pkg.temp_c", 140.0, 2)).quality == Quality.OUT_OF_RANGE
    assert qc.check(s("cpu.pkg.temp_c", 45.0, 3)).quality == Quality.OK
    assert qc.check(s("cpu.pkg.temp_c", None, 4)).quality == Quality.MISSING
    assert qc.check(s("cpu.pkg.temp_c", float("nan"), 5)).quality == Quality.MISSING


def test_impossible_jump_is_glitch_and_does_not_poison_reference():
    qc = QualityChecker()
    assert qc.check(s("cpu.pkg.temp_c", 45.0, 0)).quality == Quality.OK
    assert qc.check(s("cpu.pkg.temp_c", 95.0, 1)).quality == Quality.GLITCH  # +50 °C in 1 s
    assert qc.check(s("cpu.pkg.temp_c", 46.0, 2)).quality == Quality.OK


def test_frozen_value_detected():
    qc = QualityChecker()
    q = [qc.check(s("cpu.pkg.temp_c", 50.0, t)).quality for t in range(0, 1000, 10)]
    assert q[0] == Quality.OK
    assert Quality.FROZEN in q
    first_frozen = q.index(Quality.FROZEN) * 10
    assert 900 <= first_frozen <= 910
    # appena il valore cambia torna OK
    assert qc.check(s("cpu.pkg.temp_c", 50.5, 1000)).quality == Quality.OK


def test_power_and_fans_never_frozen():
    qc = QualityChecker()
    q = {qc.check(s("gpu0.fan_rpm", 0.0, t)).quality for t in range(0, 3000, 10)}
    assert q == {Quality.OK}  # zero-rpm a riposo è legittimo


def test_unmapped_and_unknown_channel():
    qc = QualityChecker()
    x = Sample(0, "t", "id", "cpu", "raw", 1.0, "")
    assert qc.check(x).quality == Quality.UNMAPPED
    assert qc.check(s("custom.thing_x", 1e9, 0)).quality == Quality.OK
