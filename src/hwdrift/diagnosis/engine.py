# SPDX-License-Identifier: Apache-2.0
"""Motore di diagnosi dichiarativo.

Il tool non emette diagnosi certe: mappa combinazioni di segnali su ipotesi
ordinate, con supporti e controindicazioni, e propone verifiche. La confidenza è
qualitativa (bassa, media, alta).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from ..i18n import tr

LEVELS = ("none", "info", "attention", "action")
CONF = ("low", "medium", "high")


def level_ge(a: str, b: str) -> bool:
    return LEVELS.index(a) >= LEVELS.index(b)


@dataclass
class IndicatorState:
    """Stato di un indicatore nel periodo di osservazione (tutti i regimi)."""

    upper: str = "none"  # livello più alto dei segnali sul lato superiore
    lower: str = "none"
    locked: bool = False  # almeno una carta bloccata (necessaria per "stable")
    charts_upper: dict[str, str] = field(default_factory=dict)  # chart_id -> livello
    charts_lower: dict[str, str] = field(default_factory=dict)


@dataclass
class Evidence:
    indicators: dict[str, IndicatorState]
    config_event_hours: float | None  # ore dall'evento di configurazione più vicino
    maintenance_event_hours: float | None
    primary: list[str]


@dataclass
class Diagnosis:
    rule_id: str
    title: str
    confidence: str
    level: str
    supports: list[str]
    contradicts: list[str]
    actions: list[str]
    charts: list[str]


def load_rules(path: str | Path | None = None) -> list[dict[str, Any]]:
    if path is None:
        text = resources.files("hwdrift.diagnosis").joinpath("rules/default.yaml").read_text(
            encoding="utf-8")
    else:
        text = Path(path).read_text(encoding="utf-8")
    doc = yaml.safe_load(text)
    rules = doc.get("rules", []) if isinstance(doc, dict) else []
    for r in rules:
        _validate_rule(r)
    return rules


_REGIMES = {"idle", "medium", "high", "all", "load", "day"}


def _validate_rule(r: dict[str, Any]) -> None:
    for key in ("id", "title", "requires", "confidence", "max_level"):
        if key not in r:
            raise ValueError(f"regola {r.get('id', '?')}: manca '{key}'")
    if r["max_level"] not in LEVELS[1:]:
        raise ValueError(f"regola {r['id']}: max_level non valido")
    if r["confidence"].get("base") not in CONF:
        raise ValueError(f"regola {r['id']}: confidence.base non valida")
    for sec in ("requires", "supports", "contradicts"):
        for c in r.get(sec, []) or []:
            if "indicator" in c:
                if c.get("signal") not in ("upper", "lower", "stable", "any"):
                    raise ValueError(f"regola {r['id']}: signal non valido in {sec}")
                if c.get("regimes") is not None and not set(c["regimes"]) <= _REGIMES:
                    raise ValueError(f"regola {r['id']}: regimi non validi in {sec}")
            elif "event" in c:
                if c["event"] not in ("config", "maintenance"):
                    raise ValueError(f"regola {r['id']}: evento non valido")
            else:
                raise ValueError(f"regola {r['id']}: condizione non riconosciuta in {sec}")


def _names(cond: dict[str, Any], ev: Evidence) -> list[str]:
    ind = cond["indicator"]
    if ind == "any_primary":
        return list(ev.primary)
    return [ind] if isinstance(ind, str) else list(ind)


def _component(indicator: str) -> str:
    from ..indicators.definitions import split

    return split(indicator)[1] or "system"


def _side_charts(st: IndicatorState, side: str, regimes: list[str] | None) -> dict[str, str]:
    charts = st.charts_upper if side == "upper" else st.charts_lower
    if regimes:
        return {cid: lvl for cid, lvl in charts.items() if cid.split("|")[1] in regimes}
    return charts


def _match(cond: dict[str, Any], ev: Evidence, min_level: str = "info"
           ) -> tuple[str, list[str], list[str]]:
    """Restituisce (livello raggiunto, descrizioni, carte coinvolte) per una condizione."""
    if "event" in cond:
        hours = ev.config_event_hours if cond["event"] == "config" else ev.maintenance_event_hours
        if hours is not None and hours <= float(cond.get("within_hours", 24)):
            return "action", [tr("evento {event} {hours} h fa").format(
                event=cond["event"], hours=f"{hours:.0f}")], []
        return "none", [], []
    sig = cond["signal"]
    regimes = cond.get("regimes")
    best = "none"
    desc: list[str] = []
    charts: list[str] = []
    comps: set[str] = set()
    for name in _names(cond, ev):
        st = ev.indicators.get(name)
        if st is None:
            continue
        if sig == "stable":
            # stabile = carta bloccata senza segnali persistenti (i segnali isolati di
            # livello info sono rumore atteso quando le carte sono molte)
            levels = [lvl for side in ("upper", "lower")
                      for lvl in _side_charts(st, side, regimes).values()]
            if st.locked and not any(level_ge(lvl, "attention") for lvl in levels):
                best = "action"  # la stabilità non limita il livello
                desc.append(tr("{name} stabile").format(name=name))
            continue
        for side in (("upper", "lower") if sig == "any" else (sig,)):
            sel = {c: lvl for c, lvl in _side_charts(st, side, regimes).items()
                   if level_ge(lvl, min_level)}
            if not sel:
                continue
            lvl = max(sel.values(), key=LEVELS.index)
            comps.add(_component(name))
            charts += list(sel)
            desc.append(tr("{name} in salita ({lvl})" if side == "upper"
                           else "{name} in calo ({lvl})").format(name=name, lvl=lvl))
            if level_ge(lvl, best):
                best = lvl
    need = int(cond.get("distinct_components", 1))
    if best != "none" and need > 1 and len(comps) < need:
        return "none", [], []
    return best, desc, charts


def diagnose(rules: list[dict[str, Any]], ev: Evidence) -> list[Diagnosis]:
    """Applica le regole all'evidenza e restituisce le ipotesi ordinate."""
    out: list[Diagnosis] = []
    for r in rules:
        req_levels: list[str] = []
        req_desc: list[str] = []
        charts: list[str] = []
        ok = True
        for c in r["requires"]:
            lvl, desc, chs = _match(c, ev)
            if lvl == "none":
                ok = False
                break
            req_levels.append(lvl)
            req_desc += desc
            charts += chs
        if not ok:
            continue
        sup: list[str] = []
        for c in r.get("supports", []) or []:
            lvl, desc, chs = _match(c, ev)
            if lvl != "none":
                sup += desc
                charts += chs
        con: list[str] = []
        blocked = False
        for c in r.get("contradicts", []) or []:
            # una controindicazione conta solo se persistente (livello attenzione)
            lvl, desc, _ = _match(c, ev, min_level="attention")
            if lvl != "none":
                con += desc or [str(c)]
                blocked |= bool(c.get("blocking"))
        if blocked:
            continue
        conf = r["confidence"]
        confidence = conf["base"]
        if sup and "with_supports" in conf:
            confidence = conf["with_supports"]
        if con:
            confidence = CONF[max(0, CONF.index(confidence) - 1)]
        # livello: il minimo tra i requisiti; "azione" solo con almeno 2 carte
        # correlate a livello attenzione e nessuna controindicazione (sezione 7)
        level = min(req_levels, key=LEVELS.index)
        if level == "action":
            level = "attention"
        attention_charts = {ch for ch in charts if _chart_level(ch, ev) == "attention"}
        if level_ge(level, "attention") and len(attention_charts) >= 2 and not con:
            level = "action"
        if not level_ge(r["max_level"], level):
            level = r["max_level"]
        if not level_ge(level, "attention") and r["max_level"] != "info":
            continue  # un segnale isolato non basta per proporre un'ipotesi di guasto
        out.append(Diagnosis(r["id"], tr(r["title"]), confidence, level, req_desc + sup, con,
                             [tr(a) for a in r.get("actions", [])], sorted(set(charts))))
    out.sort(key=lambda d: (-LEVELS.index(d.level), -CONF.index(d.confidence)))
    return out


def _chart_level(chart_id: str, ev: Evidence) -> str:
    st = ev.indicators.get(chart_id.split("|")[0])
    if not st:
        return "none"
    return max(st.charts_upper.get(chart_id, "none"), st.charts_lower.get(chart_id, "none"),
               key=LEVELS.index)
