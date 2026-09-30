# SPDX-License-Identifier: Apache-2.0
"""Catalogo degli indicatori: nome, regimi, didascalia e ipotesi se sale."""

from __future__ import annotations

from dataclasses import dataclass

from ..i18n import tr


@dataclass(frozen=True)
class IndicatorDef:
    base: str  # nome senza suffisso di componente
    unit: str
    caption: str  # una riga: cosa mostra e come leggerla
    if_up: str
    kind: str = "imr"  # "imr" | "count"


DEFS: dict[str, IndicatorDef] = {
    "rth": IndicatorDef("rth", "°C/W",
                        "resistenza termica: se sale, il raffreddamento peggiora",
                        "pasta, dissipatore, airflow"),
    "hotspot_delta": IndicatorDef("hotspot_delta", "°C",
                                  "differenza hotspot-edge GPU: se sale, contatto chip-dissipatore "
                                  "peggiore", "pasta o pad GPU"),
    "fan_effort": IndicatorDef("fan_effort", "rpm",
                               "sforzo ventola a parità di potenza: se sale, le ventole lavorano "
                               "di più per smaltire lo stesso calore",
                               "polvere, ventola degradata"),
    "idle_temp": IndicatorDef("idle_temp", "°C",
                              "temperatura a riposo (rispetto al riferimento): se sale, airflow "
                              "o pasta", "airflow, pasta"),
    "case_delta": IndicatorDef("case_delta", "°C",
                               "scheda madre rispetto al riferimento sotto carico: se sale, "
                               "airflow del case peggiore", "polvere, airflow del case"),
    "throttle_frac": IndicatorDef("throttle_frac", "frazione",
                                  "quota del tempo sotto carico in throttling termico: se sale, "
                                  "il raffreddamento non basta", "limite termico"),
    "temp_resid": IndicatorDef("temp_resid", "°C",
                               "residuo del modello di baseline T ~ P + T_rif: se sale, a parità "
                               "di carico la temperatura è più alta", "raffreddamento peggiorato"),
    "temp_resid_fan": IndicatorDef("temp_resid_fan", "°C",
                                   "residuo del modello con la ventola come covariata (maschera "
                                   "il guasto ventola)", "pasta, dissipatore"),
    "temp_cont": IndicatorDef("temp_cont", "°C",
                              "residuo del modello continuo T ~ f(P, T_rif), senza regimi",
                              "raffreddamento peggiorato"),
    "ref_temp": IndicatorDef("ref_temp", "°C",
                             "temperatura di riferimento (ambiente o proxy): se sale insieme a "
                             "tutto il resto, la causa è l'ambiente", "ambiente, stagione"),
    "whea_corrected": IndicatorDef("whea_corrected", "eventi/giorno",
                                   "errori hardware corretti (WHEA) al giorno",
                                   "instabilità: overclock, undervolt, RAM, PCIe", "count"),
    "tdr": IndicatorDef("tdr", "eventi/giorno", "reset del driver video (TDR) al giorno",
                        "instabilità GPU o driver", "count"),
    "pcie_replay": IndicatorDef("pcie_replay", "eventi/giorno", "replay PCIe della GPU al giorno",
                                "collegamento PCIe instabile", "count"),
    "unexpected_shutdown": IndicatorDef("unexpected_shutdown", "eventi/giorno",
                                        "spegnimenti imprevisti e schermate blu al giorno",
                                        "instabilità, alimentazione, temperatura", "count"),
}

COUNT_EVENT_KINDS: dict[str, tuple[str, ...]] = {
    "whea_corrected": ("hw.whea_corrected",),
    "tdr": ("hw.tdr",),
    "unexpected_shutdown": ("hw.kernel_power", "hw.bugcheck"),
}

SECONDARY_BASES = {"temp_resid", "temp_resid_fan", "temp_cont", "case_delta", "ref_temp"}
# indicatori di contesto: possono raggiungere il livello "attenzione" (servono alle regole
# come controindicazione) ma non generano allarmi propri
CONTEXT_INDICATORS = {"ref_temp"}


def split(indicator: str) -> tuple[str, str]:
    """``"rth_cpu" -> ("rth", "cpu")``; gli indicatori di sistema hanno suffisso ""."""
    for base in sorted(DEFS, key=len, reverse=True):
        if indicator == base:
            return base, ""
        if indicator.startswith(base + "_"):
            return base, indicator[len(base) + 1:]
    return indicator, ""


def definition(indicator: str) -> IndicatorDef | None:
    return DEFS.get(split(indicator)[0])


def caption(indicator: str, regime: str) -> str:
    """Didascalia di una riga, nella lingua attiva."""
    base, comp = split(indicator)
    d = DEFS.get(base)
    label = {"cpu": "CPU", "gpu": "GPU", "": tr("sistema")}.get(comp, comp.upper())
    reg = {"idle": tr("a riposo"), "medium": tr("carico medio"), "high": tr("carico alto"),
           "all": tr("tutti i carichi"), "load": tr("sotto carico"),
           "day": tr("giornaliero")}.get(regime, regime)
    return tr("{base} {label}, {reg}: {caption}").format(
        base=base.replace("_", " "), label=label, reg=reg, caption=tr(d.caption) if d else "")
