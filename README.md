# HWDrift

**Manutenzione predittiva locale per PC: deriva termica di CPU e GPU con carte di controllo.**

HWDrift costruisce il baseline individuale del tuo PC e rileva, con carte di controllo
I-MR su indicatori normalizzati per il carico, la deriva del percorso termico
(polvere, pasta termica, ventola, pompa) e il throttling grave. Tutto locale: nessun
cloud, nessun account, nessuna connessione di rete di default.

- Rileva derive rispetto al baseline, **non** stima vita residua né probabilità di guasto.
- Propone **ipotesi** di manutenzione con confidenza qualitativa e verifiche ordinate
  dalla meno alla più invasiva.
- Segnala **subito** (pochi secondi) il throttling grave e le ventole ferme.
- Non modifica mai l'hardware (curve ventola, limiti di potenza).

> **Guida passo passo (come funziona e come farlo partire): [docs/GUIDA_UTENTE.md](docs/GUIDA_UTENTE.md)**
>
> **Interfaccia grafica** (`hwdrift-gui.exe`): grafici in tempo reale, stato, carte, eventi,
> configurazione e salvataggio di log e dati — vedi la sezione 6A della guida.

## Avvio rapido

```powershell
py -3.12 -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install --require-hashes -r requirements\dev.lock
pip install --no-deps -e .

# prova senza hardware: 30 giorni simulati con accumulo di polvere
hwdrift --db demo.sqlite simulate dust --days 30
hwdrift --db demo.sqlite analyze          # genera anche il report HTML
hwdrift --db demo.sqlite status

# sul tuo PC (Windows 11, LibreHardwareMonitor con Remote Web Server attivo)
hwdrift discover                          # sensori trovati e mappatura proposta
hwdrift baseline start --state clean      # se hai appena pulito il PC
hwdrift run                               # collector (terminale amministratore)
hwdrift analyze                           # ogni tanto, o come attività pianificata
hwdrift schedule install --apply          # esecuzione in background
```

## Architettura

Due processi e un database: un **collector** leggero (senza numpy, ≤ 1% di un core)
scrive in SQLite; un **worker di analisi** a bassa priorità calcola finestre
stazionarie, indicatori, carte e ipotesi e rigenera il report; un **notificatore**
senza privilegi legge il database in sola lettura e mostra i toast.

```
src/hwdrift/
├── collectors/   lhm, nvml, eventlog, perfcounters, psutil, wmi_info, smart,
│                 hwinfo_csv, simulator, linux_hwmon (sperimentale)
├── channels.py   canali canonici e mappatura dei sensori
├── storage/      schema versionato, writer in batch, export
├── quality/      qualità dei dati, watchdog, errori immediati
├── context/      regimi, finestre stazionarie, eventi
├── indicators/   Rth, sforzo ventola, hotspot, baseline e residui, copertura
├── spc/          I-MR, regole, EWMA, CUSUM, carte c/u, Mann-Kendall, presupposti
├── analysis/     worker e gestione delle carte (Fase I/II, segmenti)
├── diagnosis/    motore e regole YAML
├── alerts/       politica di allarme, toast, notificatore
├── reporting/    report HTML accessibile (SVG, nessuno script)
├── sim/          modello termico sintetico e scenari di guasto
├── gui/          interfaccia grafica (tkinter): data.py (testabile senza Tk), widgets, app
├── healthcheck.py, selftest.py, runner.py, cli.py
packaging/        PyInstaller (hwdrift-gui.spec, build_exe.ps1) · .github/workflows/build-exe.yml
```

## Documentazione

| Documento | Contenuto |
|---|---|
| [docs/GUIDA_UTENTE.md](docs/GUIDA_UTENTE.md) | come funziona e come farlo partire, passo passo |
| [docs/metodologia.md](docs/metodologia.md) | indicatori, finestre, regimi, SPC, diagnosi, scelte di progetto |
| [docs/protocollo_validazione.md](docs/protocollo_validazione.md) | fasi 0–5 e stato attuale |
| [docs/matrice_sensori.md](docs/matrice_sensori.md) | sorgenti, canali, disponibilità da compilare in M0 |
| [docs/interoperabilita.md](docs/interoperabilita.md) | schema aperto, Prometheus, OpenTelemetry |
| [docs/AUDIT.md](docs/AUDIT.md) | audit del codice e stato delle correzioni |
| [schemas/](schemas/) | JSON Schema di campioni, indicatori, eventi, carte, segnali |
| [SECURITY.md](SECURITY.md), [THREAT_MODEL.md](THREAT_MODEL.md) | sicurezza e modello di minaccia |
| [CONTRIBUTING.md](CONTRIBUTING.md), [GOVERNANCE.md](GOVERNANCE.md), [AI_USAGE.md](AI_USAGE.md) | contributi, governance, uso dell'AI |

## Sviluppo

```powershell
ruff check src tests      # lint
pyright                   # type check
pytest                    # test (esclusi quelli con marker hardware)
pytest -m "not slow"      # solo i test veloci
hwdrift selftest          # overhead del collector
```

Script di spike M0 (24 ore di campionamento dei sensori reali):
`python scripts/m0_spike.py --hours 24 --out m0-%COMPUTERNAME%`.

## Licenza

Apache-2.0 (vedi [LICENSE](LICENSE)). LibreHardwareMonitor è MPL-2.0 ed è una
dipendenza esterna opzionale, non ridistribuita; smartmontools si usa come eseguibile
esterno, non linkato.
