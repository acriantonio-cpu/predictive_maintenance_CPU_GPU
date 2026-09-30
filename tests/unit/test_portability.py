# SPDX-License-Identifier: Apache-2.0
"""Requisito 15.2: il nucleo non usa API di Windows; sezione 2: il collector non importa
librerie scientifiche."""

import ast
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "hwdrift"
CORE = ["storage", "context", "indicators", "spc", "diagnosis", "reporting", "analysis",
        "quality", "sim", "alerts/policy.py", "model.py", "channels.py", "config.py"]
WINDOWS_MODULES = {"win32api", "win32pdh", "win32evtlog", "pywintypes", "wmi", "clr",
                   "winreg", "win32com", "pythoncom", "LibreHardwareMonitor", "ctypes"}


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.add(node.module.split(".")[0])
    return out


def test_core_has_no_windows_imports():
    files = []
    for c in CORE:
        p = SRC / c
        files += list(p.rglob("*.py")) if p.is_dir() else [p]
    offenders = {str(f.relative_to(SRC)): imported_modules(f) & WINDOWS_MODULES for f in files}
    assert {k: v for k, v in offenders.items() if v} == {}


def test_spc_is_pure():
    for f in (SRC / "spc").glob("*.py"):
        mods = imported_modules(f)
        assert not mods & {"sqlite3", "hwdrift", "plotly", "matplotlib"}, f


def test_collector_side_does_not_load_numpy():
    code = ("import sys, hwdrift.runner, hwdrift.collectors.simulator, hwdrift.alerts.notifier, "
            "hwdrift.cli; heavy=[m for m in ('numpy','scipy','pandas') if m in sys.modules]; "
            "print(heavy); sys.exit(1 if heavy else 0)")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
