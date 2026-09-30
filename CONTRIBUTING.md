# Contribuire

> Copia in inglese: [`docs/en/CONTRIBUTING.md`](docs/en/CONTRIBUTING.md); i due file vanno tenuti allineati.

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
2. **Documentazione aggiornata nello stesso commit — in entrambe le lingue.** Se cambia un
   comando, un default, un indicatore o una regola, aggiorna `docs/GUIDA_UTENTE.md` **e**
   `docs/en/USER_GUIDE.md` (e le due metodologie se cambia il metodo) e `CHANGELOG.md` /
   `docs/en/CHANGELOG.md`. `tests/unit/test_docs_sync.py` verifica che le copie inglese e
   italiana abbiano la stessa struttura.
3. **Confini tra moduli.** `spc/` solo funzioni pure; i collector producono solo `Sample`;
   il nucleo non importa moduli di Windows; il collector non importa numpy/scipy
   (verificato da `tests/unit/test_portability.py`).
4. **Nessun identificatore inventato.** Nomi di sensori, ID di eventi, funzioni NVML
   incerti vanno marcati `TODO(M0)` con il modo di verificarli.
5. **I testi visibili all'utente passano da `tr()`** (`src/hwdrift/i18n.py`): il testo italiano
   nel codice è la chiave, la traduzione inglese va in `src/hwdrift/i18n_en.py`;
   `tests/unit/test_i18n.py` fallisce se manca una traduzione.
6. **Controlli locali prima del push**: `ruff check src tests`, `pyright`, `pytest` (i test della
   GUI richiedono un display: su Linux `xvfb-run -a pytest`).
7. **Commit convenzionali** (`feat:`, `fix:`, `docs:`, `test:`...) con intestazione SPDX
   nei nuovi file e, se hai usato strumenti di AI, le righe descritte in
   [AI_USAGE.md](AI_USAGE.md).
8. Licenza dei contributi: Apache-2.0.
