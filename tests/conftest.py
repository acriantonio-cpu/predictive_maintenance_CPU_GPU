# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from hwdrift import i18n
from hwdrift.config import DEFAULTS, _validate
from hwdrift.storage.schema import open_db


@pytest.fixture(autouse=True)
def italian_by_default(monkeypatch):
    """I test storici verificano i testi italiani: la lingua predefinita del prodotto è
    l'inglese, ma i test partono in italiano (quelli in inglese lo impostano esplicitamente
    con ``monkeypatch.setenv("HWDRIFT_LANGUAGE", "en")``). Ogni componente
    riallinea la lingua alla propria configurazione quando viene creato."""
    monkeypatch.setenv("HWDRIFT_LANGUAGE", "it")
    i18n.set_language("it")
    yield
    i18n.set_language("it")


@pytest.fixture
def cfg(tmp_path: Path) -> dict:
    c = copy.deepcopy(DEFAULTS)
    c["language"] = "it"
    c["data_dir"] = str(tmp_path / "data")
    (tmp_path / "data").mkdir()
    c["alerts"]["toast"] = False
    _validate(c)
    return c


@pytest.fixture
def conn(tmp_path: Path):
    c = open_db(tmp_path / "t.sqlite")
    yield c
    c.close()
