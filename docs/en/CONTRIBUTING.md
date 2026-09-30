# Contributing

> English copy of [`CONTRIBUTING.md`](../../CONTRIBUTING.md) (Italian); keep them in sync.

Thank you! Before starting read the [user guide](USER_GUIDE.md) and the
[methodology](methodology.md).

## Environment

```powershell
py -3.12 -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install --require-hashes -r requirements\dev.lock
pip install --no-deps -e .
```

To update dependencies: edit `pyproject.toml` and regenerate the locks with
`uv pip compile pyproject.toml --extra dev --universal --generate-hashes --python-version 3.12 -o requirements/dev.lock`.

## Rules

1. **Tests together with the code.** Every countermeasure of the failure modes (section 14 of the
   specification) has a test. SPC functions: hand-computed values + property tests.
2. **Documentation updated in the same commit — in both languages.** If a command, a default, an
   indicator or a rule changes, update `docs/GUIDA_UTENTE.md` **and** `docs/en/USER_GUIDE.md` (and
   the two methodology files if the method changes) and `CHANGELOG.md` / `docs/en/CHANGELOG.md`.
   `tests/unit/test_docs_sync.py` checks that the English and Italian copies have the same
   structure.
3. **Module boundaries.** `spc/` pure functions only; collectors produce only `Sample`; the core
   does not import Windows modules; the collector does not import numpy/scipy (verified by
   `tests/unit/test_portability.py`).
4. **No invented identifiers.** Uncertain sensor names, event IDs, NVML functions must be marked
   `TODO(M0)` with the way to verify them.
5. **User-visible texts go through `tr()`** (`src/hwdrift/i18n.py`): the Italian text in the code
   is the key, its English translation goes in `src/hwdrift/i18n_en.py`;
   `tests/unit/test_i18n.py` fails if a translation is missing.
6. **Local checks before pushing**: `ruff check src tests`, `pyright`, `pytest` (GUI tests need a
   display: on Linux `xvfb-run -a pytest`).
7. **Conventional commits** (`feat:`, `fix:`, `docs:`, `test:`...) with an SPDX header in new files
   and, if you used AI tools, the lines described in [AI_USAGE.md](AI_USAGE.md).
8. License of contributions: Apache-2.0.
