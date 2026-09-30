#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verifica che ogni file Python abbia l'intestazione SPDX (requisito 15.1)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
missing = [str(p.relative_to(ROOT)) for d in ("src", "tests", "scripts")
           for p in (ROOT / d).rglob("*.py")
           if p.stat().st_size and "SPDX-License-Identifier" not in p.read_text(encoding="utf-8")
           .splitlines()[:3].__str__()]
if missing:
    print("File senza intestazione SPDX:\n  " + "\n  ".join(missing))
    sys.exit(1)
print("intestazioni SPDX: ok")
