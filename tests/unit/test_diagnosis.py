# SPDX-License-Identifier: Apache-2.0
import pytest

from hwdrift.diagnosis.engine import Evidence, IndicatorState, diagnose, load_rules


def ind(upper=None, lower=None, locked=True):
    st = IndicatorState(locked=locked)
    for side, charts in (("upper", upper or {}), ("lower", lower or {})):
        for cid, lvl in charts.items():
            (st.charts_upper if side == "upper" else st.charts_lower)[cid] = lvl
            cur = getattr(st, side)
            order = ["none", "info", "attention", "action"]
            if order.index(lvl) > order.index(cur):
                setattr(st, side, lvl)
    return st


PRIMARY = ["rth_cpu", "rth_gpu", "fan_effort_cpu", "fan_effort_gpu"]


def ev(indicators, cfg_h=None, maint_h=None):
    return Evidence(indicators, cfg_h, maint_h, PRIMARY)


def test_rules_load_and_validate():
    rules = load_rules()
    ids = {r["id"] for r in rules}
    assert {"dust_airflow", "paste_contact", "fan_failure", "environment",
            "instability_whea", "power_profile"} <= ids


def test_dust_action_with_two_correlated_charts():
    e = ev({"rth_cpu": ind({"rth_cpu|high|daily": "attention"}),
            "fan_effort_cpu": ind({"fan_effort_cpu|medium|daily": "attention"}),
            "fan_effort_gpu": ind()})
    d = diagnose(load_rules(), e)
    assert d[0].rule_id == "dust_airflow" and d[0].level == "action"
    assert "Pulire" in d[0].actions[0]


def test_single_info_signal_gives_no_hypothesis():
    e = ev({"rth_cpu": ind({"rth_cpu|high|window": "info"}),
            "fan_effort_cpu": ind({"fan_effort_cpu|high|window": "info"})})
    assert [x for x in diagnose(load_rules(), e) if x.rule_id != "environment"] == []


def test_paste_requires_stable_fans_and_is_blocked_by_fan_drop():
    base = {"rth_cpu": ind({"rth_cpu|high|daily": "attention", "rth_cpu|medium|daily":
                            "attention"}),
            "fan_effort_cpu": ind(), "fan_effort_gpu": ind(), "case_delta_cpu": ind()}
    d = diagnose(load_rules(), ev(base))
    assert d[0].rule_id == "paste_contact" and d[0].level == "action"
    broken = dict(base, fan_effort_cpu=ind(lower={"fan_effort_cpu|high|daily": "attention"}))
    ids = [x.rule_id for x in diagnose(load_rules(), ev(broken))]
    assert "fan_failure" in ids and "paste_contact" not in ids


def test_config_event_blocks_maintenance_hypotheses():
    e = ev({"rth_cpu": ind({"rth_cpu|high|daily": "attention"}),
            "fan_effort_cpu": ind({"fan_effort_cpu|high|daily": "attention"})}, cfg_h=3.0)
    ids = [x.rule_id for x in diagnose(load_rules(), e)]
    assert "dust_airflow" not in ids


def test_unlocked_chart_is_not_stable():
    e = ev({"rth_cpu": ind({"rth_cpu|high|daily": "attention"}),
            "fan_effort_cpu": ind(locked=False), "fan_effort_gpu": ind(locked=False)})
    assert "paste_contact" not in [x.rule_id for x in diagnose(load_rules(), e)]


def test_contradiction_lowers_confidence_and_prevents_action():
    e = ev({"rth_cpu": ind({"rth_cpu|high|daily": "attention"}),
            "fan_effort_cpu": ind({"fan_effort_cpu|high|daily": "attention"},
                                  {"fan_effort_cpu|medium|daily": "attention"})})
    d = next(x for x in diagnose(load_rules(), e) if x.rule_id == "dust_airflow")
    assert d.confidence == "low" and d.level == "attention"


def test_invalid_rule_file(tmp_path):
    p = tmp_path / "r.yaml"
    p.write_text("rules:\n  - id: x\n    title: t\n    requires: [{indicator: a, signal: up}]\n"
                 "    confidence: {base: medium}\n    max_level: info\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_rules(p)
