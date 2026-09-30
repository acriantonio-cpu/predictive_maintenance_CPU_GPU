#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Valida i file JSONL di ``hwdrift export --format jsonl`` con gli schemi in ``schemas/``."""

import json
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]


def main(folder: str) -> int:
    n = 0
    for p in sorted(Path(folder).glob("*.jsonl")):
        schema = json.loads((ROOT / "schemas" / p.name.replace("s.jsonl", ".schema.json"))
                            .read_text(encoding="utf-8"))
        v = jsonschema.Draft202012Validator(schema)
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            errs = list(v.iter_errors(json.loads(line)))
            if errs:
                print(f"{p.name}:{i}: {errs[0].message}")
                return 1
            n += 1
    print(f"{n} record validi")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "hwdrift-export"))
