# SPDX-License-Identifier: Apache-2.0
"""Punto di ingresso dell'eseguibile ``hwdrift-gui``.

Senza comandi apre la finestra. Se tra gli argomenti c'è un comando della CLI
(``hwdrift-gui run``, ``hwdrift-gui --db x.sqlite analyze``, ...) inoltra alla CLI: così
l'unico .exe serve anche da collector e nelle attività pianificate.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

COMMANDS = {"version", "discover", "run", "analyze", "report", "export", "import-hwinfo",
            "selftest", "healthcheck", "simulate", "notify", "status", "init-config", "baseline",
            "event", "schedule"}


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if sys.stderr is None:  # eseguibile "windowed": nessuna console
        sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stdout is None:
        sys.stdout = sys.stderr
    if COMMANDS & set(argv):
        from ..cli import main as cli_main

        sys.argv = ["hwdrift", *argv]
        cli_main()
        return
    ap = argparse.ArgumentParser(prog="hwdrift-gui", description="HWDrift — interfaccia grafica")
    ap.add_argument("--config", "-c", type=Path, default=None, help="file hwdrift.yaml")
    ap.add_argument("--db", type=Path, default=None, help="database SQLite")
    args = ap.parse_args(argv)
    from .app import run_gui

    run_gui(args.config, args.db)


if __name__ == "__main__":
    main()
