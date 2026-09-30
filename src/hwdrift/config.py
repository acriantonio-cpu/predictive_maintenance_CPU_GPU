# SPDX-License-Identifier: Apache-2.0
"""Configurazione (``hwdrift.yaml``) con valori di default e validazione.

La configurazione è un dizionario annidato: i default sono qui sotto, il file
YAML dell'utente li sovrascrive chiave per chiave. Le chiavi sconosciute e i tipi
sbagliati producono un errore esplicito (un refuso non deve spegnere in silenzio
una funzione di sicurezza come il rilevatore di throttling).
"""

from __future__ import annotations

import copy
import os
import sys
from pathlib import Path
from typing import Any

import yaml

DEFAULTS: dict[str, Any] = {
    "language": "en",  # "en" | "it": interfaccia grafica, report, allarmi, ipotesi, notifiche
    "data_dir": None,  # None = cartella dati di piattaforma (vedi default_data_dir)
    "sampling": {
        "interval_s": 1.0,  # 0.5–5 s (sezione 2)
        "flush_s": 60.0,  # scrittura in batch
        "raw_retention_h": 48.0,
        "adaptive": True,  # allunga l'intervallo se l'overhead supera il budget
        "cpu_budget_pct": 1.0,  # % di un core
        "rss_budget_mb": 100.0,
        "selfmon_s": 10.0,
    },
    "sources": {
        "simulator": {"enabled": False, "scenario": "healthy", "seed": 1,
                      "fault_after_s": 600.0},
        "lhm": {"enabled": True, "mode": "web", "url": "http://127.0.0.1:8085/data.json",
                "dll_path": None, "timeout_s": 2.0, "low_level": True},
        "nvml": {"enabled": True},
        "eventlog": {"enabled": True, "interval_s": 60.0, "max_events": 200},
        "perfcounters": {"enabled": True},
        "psutil": {"enabled": True},
        "sysinfo": {"enabled": True, "interval_s": 900.0},
        "smart": {"enabled": False, "devices": [], "interval_s": 300.0,
                  "smartctl": "smartctl", "low_level": True},
        "linux_hwmon": {"enabled": False},
    },
    "profile": {
        "auto_mapping": True,
        "mapping": {},  # sensor_id -> canale canonico ("" = escludi)
        # Riferimento di temperatura T_ref (sezione 6): "user" | "channel" | "none"
        "reference": {"mode": "channel", "channel": "ssd0.temp_c", "value_c": 22.0},
        "cpu": {"nominal_clock_mhz": None, "tjmax_c": 100.0},
        "gpu": {"thermal_limit_c": 83.0},
        "baseline_state": "unknown",  # "clean" (appena pulito) | "unknown"
    },
    "realtime": {
        "enabled": True,
        "debounce_s": 7.0,
        "release_s": 15.0,
        "cpu_clock_ratio": 0.70,  # clock effettivo / nominale sotto cui c'è throttling
        "cpu_load_min_pct": 80.0,
        "cpu_temp_margin_c": 10.0,  # "vicino al limite" = tjmax - margine
        "sustained_high_min": 10.0,  # carico alto da almeno N minuti = throttling "atteso"
        "fan_stop_temp_c": 75.0,
        "high_power_fraction": 0.65,
    },
    "windows": {
        "length_min": 5,
        "warmup_min": 3,
        "power_cv_max": 0.10,
        "temp_slope_max": 0.5,  # °C/min
        "util_std_max": 10.0,  # punti percentuali
        "min_valid_frac": 0.8,
        "min_power_w": 1.0,
    },
    "regimes": {
        "mode": "fixed",  # "fixed" | "adaptive" (terzili)
        "fixed_fractions": [0.30, 0.65],
        "calibration_windows": 30,
    },
    "spc": {
        "phase1_min_obs": 25,
        "count_phase1_obs": 14,  # giorni di Fase I per le carte c (conteggi)
        "phase1_min_days": 5,
        "phase1_min_sessions": 5,
        "provisional_min_obs": 12,
        "provisional_widen": 1.25,
        "phase1_max_iterations": 3,
        "rules": ["R1", "R2", "R3"],  # carte giornaliere
        "window_rules": ["R1"],  # carte per finestra (autocorrelate)
        "r2_run": 9,
        "r3_run": 6,
        "sigma": "auto",  # "mr" | "robust" | "auto"
        "acf_threshold": 0.3,
        "ewma_lambda": 0.2,
        "ewma_L": 2.86,
        "cusum_k": 0.5,
        "cusum_h": 5.0,
        "mk_alpha": 0.01,
        "mk_min_days": 10,
        "min_windows_per_day": 2,
        "min_windows_for_model": 20,
    },
    "alerts": {
        "primary": ["rth_cpu", "rth_gpu", "fan_effort_cpu", "fan_effort_gpu",
                    "hotspot_delta_gpu", "idle_temp_cpu", "idle_temp_gpu",
                    "throttle_frac_cpu", "throttle_frac_gpu", "whea_corrected", "tdr",
                    "pcie_replay_gpu", "unexpected_shutdown"],
        "config_window_h": 24.0,
        "lookback_days": 14.0,
        "action_budget_per_month": 2,
        "toast": True,
        "stale_heartbeat_min": 5.0,
    },
    "game_safe": {
        "enabled": True,
        "check_s": 30.0,
        # Nomi processo (minuscoli) che attivano la modalità: si sospende il polling a
        # basso livello (LHM, SMART) e restano NVML ed Event Log.
        "processes": ["easyanticheat.exe", "beservice.exe", "vgc.exe", "faceit.exe",
                      "eaanticheat.gameservice.exe"],
    },
    "healthcheck": {"duration_s": 300.0, "abort_temp_c": 90.0, "workers": 0},
    "export": {"anonymize": True},
}


class ConfigError(ValueError):
    pass


def default_data_dir() -> Path:
    env = os.environ.get("HWDRIFT_HOME")
    if env:
        return Path(env)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "HWDrift"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "hwdrift"


def _merge(defaults: dict[str, Any], user: dict[str, Any], path: str) -> dict[str, Any]:
    out = copy.deepcopy(defaults)
    for key, val in user.items():
        where = f"{path}.{key}" if path else key
        if key not in defaults:
            # mapping e sorgenti hanno chiavi libere solo dove previsto
            raise ConfigError(f"chiave di configurazione sconosciuta: {where}")
        dval = defaults[key]
        if isinstance(dval, dict) and key != "mapping":
            if not isinstance(val, dict):
                raise ConfigError(f"{where}: atteso un dizionario")
            out[key] = _merge(dval, val, where)
        elif key == "mapping":
            if not isinstance(val, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in val.items()
            ):
                raise ConfigError(f"{where}: atteso un dizionario sensor_id -> canale")
            out[key] = dict(val)
        else:
            out[key] = _check_type(dval, val, where)
    return out


def _check_type(dval: Any, val: Any, where: str) -> Any:
    if dval is None or val is None:
        return val
    if isinstance(dval, bool):
        if not isinstance(val, bool):
            raise ConfigError(f"{where}: atteso true/false")
        return val
    if isinstance(dval, (int, float)) and not isinstance(dval, bool):
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise ConfigError(f"{where}: atteso un numero")
        return type(dval)(val) if isinstance(dval, float) else val
    if isinstance(dval, list):
        if not isinstance(val, list):
            raise ConfigError(f"{where}: attesa una lista")
        return val
    if isinstance(dval, str) and not isinstance(val, str):
        raise ConfigError(f"{where}: attesa una stringa")
    return val


def _validate(cfg: dict[str, Any]) -> None:
    if cfg["language"] not in ("en", "it"):
        raise ConfigError("language: en | it")
    s = cfg["sampling"]
    if not 0.1 <= s["interval_s"] <= 60:
        raise ConfigError("sampling.interval_s deve essere tra 0.1 e 60 s")
    if s["flush_s"] < s["interval_s"]:
        raise ConfigError("sampling.flush_s deve essere >= interval_s")
    ref = cfg["profile"]["reference"]
    if ref["mode"] not in ("user", "channel", "none"):
        raise ConfigError("profile.reference.mode: user | channel | none")
    if cfg["profile"]["baseline_state"] not in ("clean", "unknown"):
        raise ConfigError("profile.baseline_state: clean | unknown")
    if cfg["regimes"]["mode"] not in ("fixed", "adaptive"):
        raise ConfigError("regimes.mode: fixed | adaptive")
    f = cfg["regimes"]["fixed_fractions"]
    if len(f) != 2 or not 0 < f[0] < f[1] < 1:
        raise ConfigError("regimes.fixed_fractions: due frazioni crescenti in (0, 1)")
    if cfg["spc"]["sigma"] not in ("mr", "robust", "auto"):
        raise ConfigError("spc.sigma: mr | robust | auto")
    bad = set(cfg["spc"]["rules"] + cfg["spc"]["window_rules"]) - {"R1", "R2", "R3", "R4"}
    if bad:
        raise ConfigError(f"spc.rules: regole sconosciute {sorted(bad)}")
    from .channels import is_valid_channel_name

    bad_map = [f"{k} -> {v}" for k, v in cfg["profile"]["mapping"].items()
               if v and not is_valid_channel_name(v)]
    if bad_map:
        raise ConfigError("profile.mapping: nomi di canale non validi (es. cpu.pkg.temp_c): "
                          + "; ".join(bad_map[:5]))
    if cfg["sources"]["lhm"]["mode"] not in ("web", "dll"):
        raise ConfigError("sources.lhm.mode: web | dll")
    if cfg["spc"]["phase1_min_obs"] < 20:
        raise ConfigError("spc.phase1_min_obs: almeno 20 osservazioni (sezione 7)")


def load_config(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Carica la configurazione: default + file YAML (se presente)."""
    user: dict[str, Any] = {}
    candidates: list[Path] = []
    if path is not None:
        candidates = [Path(path)]
        if not candidates[0].exists():
            raise ConfigError(f"file di configurazione non trovato: {path}")
    else:
        env = os.environ.get("HWDRIFT_CONFIG")
        if env:
            candidates.append(Path(env))
        candidates += [Path("hwdrift.yaml"), default_data_dir() / "hwdrift.yaml"]
    source: Path | None = None
    for c in candidates:
        if c.is_file():
            with c.open("r", encoding="utf-8") as fh:
                loaded = yaml.safe_load(fh) or {}
            if not isinstance(loaded, dict):
                raise ConfigError(f"{c}: il file deve contenere un dizionario YAML")
            user = loaded
            source = c
            break
    cfg = _merge(DEFAULTS, user, "")
    _validate(cfg)
    cfg["_source"] = str(source) if source else None
    from .i18n import resolve_language, set_language

    set_language(resolve_language(cfg))
    return cfg


def data_dir(cfg: dict[str, Any]) -> Path:
    """Cartella dati. ``HWDRIFT_HOME`` (override esplicito, usato anche dalla modalità demo
    della GUI) prevale su ``data_dir`` della configurazione."""
    env = os.environ.get("HWDRIFT_HOME")
    d = Path(env) if env else Path(cfg["data_dir"]) if cfg.get("data_dir") else default_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path(cfg: dict[str, Any]) -> Path:
    return data_dir(cfg) / "hwdrift.sqlite"
