# SPDX-License-Identifier: Apache-2.0
"""Rete di sicurezza della localizzazione: ogni testo passato a ``tr()`` nei sorgenti (e ogni
testo delle regole di diagnosi) deve avere la traduzione inglese; i segnaposto devono coincidere."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from hwdrift import i18n
from hwdrift.diagnosis.engine import load_rules
from hwdrift.gui import data as gui_data
from hwdrift.i18n_en import EN
from hwdrift.indicators.definitions import DEFS
from hwdrift.model import EVENT_KINDS, RT_REASONS

SRC = Path(__file__).resolve().parents[2] / "src" / "hwdrift"
# dizionari i cui valori italiani vengono tradotti al momento dell'uso (chiave di catalogo)
EXTRA_KEYS = (
    [d.caption for d in DEFS.values()] + [d.if_up for d in DEFS.values()]
    + [d.unit for d in DEFS.values() if d.unit not in ("°C", "°C/W", "rpm")]
    + list(EVENT_KINDS.values()) + list(RT_REASONS.values())
    + [t for t, u, series in gui_data.LIVE_CHARTS for x in (t, u, *[lb for _, lb in series]) if x
       for t in [x]]
    + [label for label, _ch, _u in gui_data.KPI]
    + [g for g, _ in gui_data.CONFIG_FIELDS]
    + [x for _, fs in gui_data.CONFIG_FIELDS for f in fs for x in (f.label, f.help) if x]
)


def literals(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.IfExp):
        return literals(node.body) + literals(node.orelse)
    return []


def used_keys() -> dict[str, str]:
    out: dict[str, str] = {}
    for f in SRC.rglob("*.py"):
        if f.name == "i18n_en.py":
            continue
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "tr"
                    and n.args):
                for lit in literals(n.args[0]):
                    out.setdefault(lit, f"{f.relative_to(SRC)}:{n.lineno}")
    return out


def test_every_tr_literal_has_an_english_translation():
    missing = {k: w for k, w in used_keys().items() if k not in EN}
    assert not missing, "\n".join(f"{w}: {k!r}" for k, w in missing.items())


def test_indicator_event_and_rule_texts_are_translated():
    rules = load_rules()
    texts = EXTRA_KEYS + [r["title"] for r in rules] + [a for r in rules
                                                        for a in r.get("actions", [])]
    missing = [t for t in texts if t not in EN]
    assert not missing, missing


def test_placeholders_match_between_languages():
    bad = []
    for it, en in EN.items():
        ph = re.compile(r"{(\w+)}")
        if sorted(ph.findall(it)) != sorted(ph.findall(en)):
            bad.append(it)
    assert not bad, bad


def test_tr_falls_back_to_italian_and_switches_language():
    i18n.set_language("it")
    assert i18n.tr("Ventola o pompa guasta") == "Ventola o pompa guasta"
    i18n.set_language("en")
    assert i18n.tr("Ventola o pompa guasta") == "Failed fan or pump"
    assert i18n.tr("testo non in catalogo") == "testo non in catalogo"
    i18n.set_language("xx")  # lingua sconosciuta: default
    assert i18n.get_language() == "en"
