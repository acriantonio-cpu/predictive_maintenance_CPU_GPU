# SPDX-License-Identifier: Apache-2.0
"""Localizzazione minima: italiano (lingua dei sorgenti) e inglese (default).

I testi nei sorgenti sono in italiano e fanno da *chiave*: ``tr("Testo")`` restituisce la
traduzione inglese dal catalogo ``i18n_en.EN`` quando la lingua attiva è ``en`` e il testo
stesso quando è ``it``. Un testo mancante dal catalogo torna in italiano (mai un errore);
``tests/unit/test_i18n.py`` verifica che ogni ``tr("...")`` dei sorgenti sia nel catalogo.

Testi con parti variabili: chiave con segnaposto ``{nome}`` e ``tr("...").format(nome=...)``.
Quali testi si traducono: interfaccia grafica, report HTML, allarmi, ipotesi di diagnosi,
notifiche e descrizioni degli eventi. Messaggi di log e aiuto della CLI restano in italiano.
"""

from __future__ import annotations

SUPPORTED = ("en", "it")
DEFAULT = "en"
_lang = DEFAULT


def resolve_language(cfg: dict | None) -> str | None:
    """Lingua da usare: ``HWDRIFT_LANGUAGE`` (override esplicito) prevale sulla configurazione."""
    import os

    return os.environ.get("HWDRIFT_LANGUAGE") or (cfg or {}).get("language")


def set_language(lang: str | None) -> None:
    global _lang
    _lang = lang if lang in SUPPORTED else DEFAULT


def get_language() -> str:
    return _lang


def tr(text: str) -> str:
    """Traduce ``text`` (italiano) nella lingua attiva."""
    if _lang == "it":
        return text
    from .i18n_en import EN

    return EN.get(text, text)
