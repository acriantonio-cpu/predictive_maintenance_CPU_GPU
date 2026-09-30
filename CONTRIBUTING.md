# Contribuire

Grazie! Prima di iniziare leggi la [guida utente](docs/GUIDA_UTENTE.md) e la
[metodologia](docs/metodologia.md).

## Ambiente

```powershell
py -3.12 -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install --require-hashes -r requirements\dev.lock
pip install --no-deps -e .
```

Aggiornare le dipendenze: modificare `pyproject.toml` e rigenerare i lock con
`uv pip compile pyproject.toml --extra dev --universal --generate-hashes --python-version 3.12 -o requirements/dev.lock`.

## Regole

1. **Test insieme al codice.** Ogni contromisura dei failure mode (sezione 14 della
   specifica) ha un test. Funzioni SPC: valori calcolati a mano + test di proprietà.
2. **Documentazione aggiornata nello stesso commit.** Se cambia un comando, un default,
   un indicatore o una regola, aggiorna `docs/GUIDA_UTENTE.md` (e `docs/metodologia.md`
   se cambia il metodo) e `CHANGELOG.md`.
3. **Confini tra moduli.** `spc/` solo funzioni pure; i collector producono solo `Sample`;
   il nucleo non importa moduli di Windows; il collector non importa numpy/scipy
   (verificato da `tests/unit/test_portability.py`).
4. **Nessun identificatore inventato.** Nomi di sensori, ID di eventi, funzioni NVML
   incerti vanno marcati `TODO(M0)` con il modo di verificarli.
5. **Controlli locali prima del push**: `ruff check src tests`, `pyright`, `pytest`.
6. **Commit convenzionali** (`feat:`, `fix:`, `docs:`, `test:`...) con intestazione SPDX
   nei nuovi file e, se hai usato strumenti di AI, le righe descritte in
   [AI_USAGE.md](AI_USAGE.md).
7. Licenza dei contributi: Apache-2.0.
