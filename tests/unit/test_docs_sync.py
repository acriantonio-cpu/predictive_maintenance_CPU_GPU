# SPDX-License-Identifier: Apache-2.0
"""La copia inglese della documentazione deve esistere, rimandare all'originale italiano e avere
la stessa struttura (stesso numero di titoli per livello)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PAIRS = {
    "docs/GUIDA_UTENTE.md": "docs/en/USER_GUIDE.md",
    "docs/metodologia.md": "docs/en/methodology.md",
    "docs/protocollo_validazione.md": "docs/en/validation_protocol.md",
    "docs/matrice_sensori.md": "docs/en/sensor_matrix.md",
    "docs/interoperabilita.md": "docs/en/interoperability.md",
    "docs/AUDIT.md": "docs/en/AUDIT.md",
    "THREAT_MODEL.md": "docs/en/THREAT_MODEL.md",
    "SECURITY.md": "docs/en/SECURITY.md",
    "CONTRIBUTING.md": "docs/en/CONTRIBUTING.md",
    "GOVERNANCE.md": "docs/en/GOVERNANCE.md",
    "AI_USAGE.md": "docs/en/AI_USAGE.md",
    "CODE_OF_CONDUCT.md": "docs/en/CODE_OF_CONDUCT.md",
    "CHANGELOG.md": "docs/en/CHANGELOG.md",
    "README.md": "README.en.md",
    "schemas/README.md": "docs/en/schemas.md",
}


def headings(path: Path) -> list[int]:
    out, in_code = [], False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            in_code = not in_code
        elif not in_code and (m := re.match(r"^(#{1,4}) \S", line)):
            out.append(len(m.group(1)))
    return out


def links(path: Path) -> list[str]:
    return re.findall(r"\]\((?!https?:|#|mailto:)([^)#\s]+)", path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(("it", "en"), PAIRS.items())
def test_english_copy_exists_and_mirrors_structure(it, en):
    p_it, p_en = ROOT / it, ROOT / en
    assert p_en.exists(), f"manca la copia inglese {en}"
    assert headings(p_it) == headings(p_en), f"{it} e {en} hanno titoli diversi"


@pytest.mark.parametrize(("it", "en"), PAIRS.items())
def test_links_resolve_and_point_back(it, en):
    p_it, p_en = ROOT / it, ROOT / en
    for doc in (p_it, p_en):
        for target in links(doc):
            assert (doc.parent / target).resolve().exists(), f"{doc.name}: link rotto {target}"
    # l'inglese rimanda all'originale italiano e viceversa
    assert any((p_en.parent / t).resolve() == p_it.resolve() for t in links(p_en)), en
    assert any((p_it.parent / t).resolve() == p_en.resolve() for t in links(p_it)), it
