# SPDX-License-Identifier: Apache-2.0
import pytest

from hwdrift.config import ConfigError, load_config


def write(tmp_path, text):
    p = tmp_path / "hwdrift.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_defaults_without_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HWDRIFT_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("HWDRIFT_CONFIG", raising=False)
    cfg = load_config()
    assert cfg["sampling"]["interval_s"] == 1.0
    assert cfg["_source"] is None


def test_override_and_int_to_float(tmp_path):
    cfg = load_config(write(tmp_path, "sampling:\n  interval_s: 2\n"))
    assert cfg["sampling"]["interval_s"] == 2.0 and isinstance(cfg["sampling"]["interval_s"],
                                                               float)


@pytest.mark.parametrize("text", [
    "sampling:\n  intervall_s: 2\n",  # refuso
    "sampling:\n  interval_s: veloce\n",
    "realtime:\n  enabled: 1\n",
    "sampling:\n  interval_s: 100\n",
    "profile:\n  reference:\n    mode: boh\n",
    "spc:\n  rules: [R9]\n",
    "spc:\n  phase1_min_obs: 5\n",
    "regimes:\n  fixed_fractions: [0.8, 0.3]\n",
    "profile:\n  mapping: [1, 2]\n",
    "- lista\n",
])
def test_invalid(tmp_path, text):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, text))


def test_missing_explicit_file(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "nope.yaml")


def test_example_config_is_valid_and_packaged():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    ex = root / "hwdrift.example.yaml"
    pkg = root / "src" / "hwdrift" / "hwdrift.example.yaml"
    assert ex.read_text(encoding="utf-8") == pkg.read_text(encoding="utf-8")
    load_config(ex)
