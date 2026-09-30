# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from hwdrift.config import DEFAULTS, _validate
from hwdrift.storage.schema import open_db


@pytest.fixture
def cfg(tmp_path: Path) -> dict:
    c = copy.deepcopy(DEFAULTS)
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
