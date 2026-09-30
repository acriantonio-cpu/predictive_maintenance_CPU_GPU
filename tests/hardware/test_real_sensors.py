# SPDX-License-Identifier: Apache-2.0
"""Test su sensori reali (marker ``hardware``): esclusi dalla CI, da eseguire a mano su
Windows 11 con ``pytest -m hardware`` (terminale amministratore per LHM in modalità dll)."""

import time

import pytest

from hwdrift.collectors.base import CollectorUnavailable, build_collectors
from hwdrift.config import load_config

pytestmark = pytest.mark.hardware


def test_real_sources_produce_key_channels():
    cfg = load_config()
    found: set[str] = set()
    for c in build_collectors(cfg):
        try:
            c.start()
            found |= {s.channel for s in c.poll(int(time.time() * 1000), time.monotonic())
                      if s.channel and s.value is not None}
            c.close()
        except CollectorUnavailable:
            continue
    assert {"cpu.pkg.temp_c", "cpu.load_pct"} <= found, sorted(found)


def test_selftest_within_budget():
    from hwdrift.selftest import run_selftest

    r = run_selftest(load_config(), seconds=60)
    assert r["within_budget"], r
    assert not r["heavy_modules_loaded"]
