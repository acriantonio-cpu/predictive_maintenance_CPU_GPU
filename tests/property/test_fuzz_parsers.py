# SPDX-License-Identifier: Apache-2.0
"""Fuzzing dei parser di input non fidati (THREAT_MODEL T3): nessuna eccezione non
gestita, nessun valore non finito che arrivi ai canali."""

import contextlib
import math
import xml.etree.ElementTree as ET

from hypothesis import given, settings
from hypothesis import strategies as st

from hwdrift.collectors.eventlog import parse_events
from hwdrift.collectors.hwinfo_csv import parse_hwinfo_csv
from hwdrift.collectors.lhm import iter_sensors, parse_value
from hwdrift.model import Quality
from hwdrift.quality.sanity import QualityChecker

cell = st.one_of(st.text(max_size=12), st.floats(allow_nan=True).map(str),
                 st.sampled_from(["Yes", "No", "", "55,5", "1e308", "-inf", "nan", "255"]))


@given(st.lists(st.lists(cell, min_size=2, max_size=6), max_size=8))
@settings(max_examples=300, deadline=None)
def test_hwinfo_parser_never_crashes(rows):
    header = '"Date","Time","CPU Package [°C]","GPU Power [W]","Total CPU Usage [%]"\n'
    body = "".join(",".join(f'"{c}"' for c in r) + "\n" for r in rows)
    qc = QualityChecker()
    for s in parse_hwinfo_csv(header + body, tz_offset_h=0):
        s = qc.check(s)
        if s.quality == Quality.OK:
            assert s.value is not None and math.isfinite(s.value)


@given(st.text(max_size=300))
@settings(max_examples=300, deadline=None)
def test_hwinfo_rejects_non_hwinfo_text(text):
    with contextlib.suppress(ValueError):  # l'unico errore ammesso
        list(parse_hwinfo_csv(text))


@given(st.text(max_size=400))
@settings(max_examples=300, deadline=None)
def test_eventlog_parser_only_expected_errors(text):
    try:
        evs = parse_events(text)
    except (ValueError, ET.ParseError):
        return
    for e in evs:
        assert isinstance(e["event_id"], int)


json_like = st.recursive(
    st.one_of(st.none(), st.booleans(), st.integers(), st.floats(allow_nan=True),
              st.text(max_size=10)),
    lambda children: st.one_of(
        st.lists(children, max_size=4),
        st.dictionaries(st.sampled_from(["Children", "SensorId", "Value", "Text", "Type"]),
                        children, max_size=5)),
    max_leaves=30)


@given(json_like)
@settings(max_examples=300, deadline=None)
def test_lhm_tree_walk_never_crashes(tree):
    for node in iter_sensors(tree if isinstance(tree, dict) else {"Children": [tree]}):
        assert isinstance(node["SensorId"], str)
        parse_value(str(node.get("Value", "")))
