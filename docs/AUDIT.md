# Audit del codice — HWDrift 0.1.0.dev0

Data: 30 settembre 2026. Ambito: tutto il codice in `src/hwdrift`, test, workflow CI,
configurazione e documentazione, rispetto alla specifica "HWDrift — Specifica di progetto
e piano di implementazione". Ambiente di verifica: Linux, Python 3.11 e 3.12 (lock
installato in un ambiente pulito), simulatore; **nessun hardware Windows reale**.

## 1. Metodo

1. Rilettura avversaria dei moduli critici (collector residente, writer, rilevatore in
   tempo reale, motore delle carte, politica di allarme, notificatore, CLI, parser).
2. Controlli automatici: `ruff` (regole E, F, W, I, B, UP, SIM, S = bandit, RUF),
   `pyright` in modalità standard, ricerca mirata di `subprocess`, SQL composto,
   `yaml.load`, `eval`, rete.
3. Test: 176 test (unitari con valori calcolati a mano, proprietà con hypothesis,
   **fuzzing dei parser**, integrazione del runner con orologio simulato, 12 scenari di
   guasto dalla raccolta alla diagnosi, CLI).
4. Revisione visiva del report HTML (Chromium, tema chiaro e scuro).
5. Misura dell'overhead rispetto al budget della sezione 2.

## 2. Esito sintetico

| Area | Stato |
|---|---|
| Lint / type check | `ruff check`: 0 problemi · `pyright`: 0 errori |
| Test | 176 verdi; copertura 88% (le sorgenti Windows sono coperte con finti `pynvml`, server LHM su loopback, sysfs e smartctl finti) |
| Confini dei moduli | verificati da test: il nucleo non importa moduli Windows; il collector non carica numpy/scipy; `spc/` è puro |
| Overhead collector | 0,1% di un core, 23 MB di picco (budget: 1%, 100 MB) — simulatore, 30 s |
| Overhead worker | 45 giorni in 9 s e 111 MB di picco alla prima analisi; 1 s nelle analisi incrementali (budget: 30 s, 300 MB) |
| Disco | ~0,9 MB/giorno di aggregati a 1 minuto con 18 canali (stima della specifica: 1,5 MB/giorno) |
| Controlli negativi (simulatore) | sano, cambio driver, ambiente, limite di potenza: nessun allarme di manutenzione |
| Guasti (simulatore) | polvere, pasta, ventola: ipotesi corretta, livello azione, prima in classifica |

## 3. Problemi trovati e corretti

| # | Gravità | Problema | Correzione | Test di regressione |
|---|---|---|---|---|
| A1 | **Alta** | `hwdrift run --simulate` e `hwdrift simulate` senza `--db` scrivevano dati sintetici nel database reale della macchina (baseline contaminato per sempre) | senza `--db` la simulazione usa `sim-<scenario>.sqlite` / `simulate-<scenario>.sqlite` | `test_simulation_never_touches_real_database` |
| A2 | **Alta** | `hwdrift status` chiamava il notificatore in modalità normale: marcava episodi e allarmi come "già notificati", sopprimendo i toast veri | `Notifier.check(persist=False)`: nessuna notifica, nessuna scrittura di stato | `test_status_does_not_consume_notifications` |
| A3 | **Alta** | Con solo LibreHardwareMonitor (nessun clock effettivo) il throttling termico della CPU non veniva mai rilevato in tempo reale | CPU a Tjmax − 1 °C sotto carico = throttling termico | `test_cpu_at_tjmax_without_clock_data` |
| A4 | Media | A ogni accesso il notificatore avvisava "collector fermo" (heartbeat della sessione precedente) | periodo di grazia dopo l'avvio del PC e del notificatore | `test_stale_grace_after_login` |
| A5 | Media | Le mediane giornaliere del giorno in corso (parziali) entravano nelle carte: un segnale su un valore poi cambiato restava registrato | indicatori giornalieri solo per giorni completi | `test_daily_indicators_only_for_complete_days` |
| A6 | Media | Una sorgente mai partita (es. LHM non avviato) non lasciava traccia: nessun indicatore, nessun avviso | stato delle sorgenti salvato a ogni flush, mostrato nel report e in `hwdrift status` | `test_unavailable_source_is_recorded` |
| A7 | Media | Soglia di plausibilità 25 °C/s: gli spike reali del package CPU all'avvio di un carico sarebbero stati marcati come glitch | 50 °C/s | `test_impossible_jump_is_glitch_and_does_not_poison_reference` |
| A8 | Media | Collector elevato con `hwdrift.yaml` preso dalla cartella corrente: un file non fidato può cambiare gli eseguibili esterni (THREAT_MODEL T1) | con privilegi elevati la configurazione della cartella corrente è rifiutata senza `--config` esplicito | `test_elevated_collector_refuses_cwd_config` |
| A9 | Media | Il segmento di una carta veniva chiuso da una manutenzione **prima** di calcolarne la Fase I quando l'analisi recuperava più giorni insieme: baseline precedente vuoto, vista "efficacia" vuota | il segmento si elabora con i dati fino alla chiusura, poi si archivia | `test_cleaning_closes_segment_and_shows_recovery` |
| A10 | Media | In analisi "in blocco" i segnali provvisori di Fase I non venivano calcolati (diversi dall'esercizio incrementale) | stessa valutazione in entrambi i percorsi | `test_throttling_feeds_throttle_indicator_not_rth` |
| A11 | Media | Serie costanti in Fase I (es. throttling sempre a zero) davano carte degeneri senza limiti: il throttling successivo non era segnalato | σ minima per indicatore anche nei limiti provvisori | stesso test |
| A12 | Media | **Falsi allarmi da autocorrelazione**: con σ = MR̄/d₂ sulle serie per finestra il caso sano produceva decine di migliaia di segnali e un falso "azione" | σ di lungo periodo e sola R1 sulle carte per finestra; regole di sequenza, EWMA, CUSUM, MK sulle giornaliere (vedi metodologia §5) | `test_negative_controls_no_maintenance_alarm` |
| A13 | Media | Controllo negativo "ambiente": una stanza più fredda produce la stessa firma di una ventola degradata | `ref_temp` in calo è controindicazione bloccante per `fan_failure` | `test_negative_controls_no_maintenance_alarm[ambient]` |
| A14 | Bassa | Fuzzing: un `\r` isolato nel CSV di HWiNFO sollevava `csv.Error` non gestito | errore trasformato in `ValueError` con numero di riga | `test_hwinfo_rejects_non_hwinfo_text` |
| A15 | Bassa | Export CSV non anonimo: la colonna `note` spariva se il primo evento non aveva note | colonne fisse per tipo di record | `test_csv_non_anonymous_keeps_note_column` |
| A16 | Bassa | `import-hwinfo` poteva sovrascrivere minuti già registrati dal collector | `INSERT OR IGNORE` per gli import | `test_import_does_not_overwrite_collector_data` |
| A17 | Bassa | Nomi di canale arbitrari nella mappatura (es. `CPU Package`) entravano nel database e violavano lo schema di export | validazione in configurazione | `test_invalid` |
| A18 | Bassa | Una lettura lenta (PowerShell, `wevtutil`) poteva essere scambiata per una sospensione (falso gap che invalida le finestre) | soglia a 90 s, timeout dei processi esterni ≤ 15–30 s | `test_suspend_produces_gap_event` |
| A19 | Bassa | Stato del notificatore senza potatura (crescita illimitata del file) | si tengono solo gli episodi degli ultimi 7 giorni e gli allarmi attivi | `test_notifier_dedup_escalation_and_readonly` |
| A20 | Bassa | `notify-send`: titolo che inizia con `-` interpretabile come opzione | separatore `--` | revisione |
| A21 | Bassa | Comando `schedule` con fallback `python -m hwdrift` quotato male per `/TR` | quoting separato di eseguibile e argomenti | revisione (TODO verifica su Windows) |

## 4. Rischi residui e raccomandazioni (non corretti in questo giro)

| # | Priorità | Rischio | Raccomandazione |
|---|---|---|---|
| R1 | **Alta** | Nessuna prova su hardware Windows: nomi dei sensori LHM/HWiNFO, ID del registro eventi, bit NVML, contatori PDH, toast e `schtasks` sono verificati solo con finti (`TODO(M0)` nel codice) | eseguire `scripts/m0_spike.py` su 2–3 macchine e `pytest -m hardware`; compilare `docs/matrice_sensori.md` |
| R2 | Alta | Collector elevato che importa codice da un venv scrivibile dall'utente = esecuzione di codice come amministratore | installare in `C:\Program Files\HWDrift` (SECURITY.md); valutare un servizio firmato in v2 |
| R3 | Media | Le carte giornaliere (con R2/R3/EWMA/CUSUM/MK) chiudono la Fase I dopo 25 giorni completi: nel primo mese le derive lente si vedono solo sulle carte per finestra (R1) | valutare in Fase 0 Fase I giornaliera da 20 giorni o carte settimanali |
| R4 | Media | Un proxy interno di T_rif (SSD) si contamina con la polvere | sensore USB di ambiente o valore utente (`reference.mode: user`) dove possibile |
| R5 | Media | Soglie e regole di diagnosi calibrate solo sul simulatore (ipotesi fisiche documentate in metodologia §7) | Fasi 0–3 del protocollo; rivedere `default.yaml` con i dati reali |
| R6 | Media | Il rilevamento dei valori congelati ha una latenza di 15 minuti | accettato; documentato |
| R7 | Bassa | Riavvio del collector nello stesso minuto: l'aggregato di quel minuto viene sostituito da quello parziale | accettato (perdita ≤ 1 minuto) |
| R8 | Bassa | `import-hwinfo` carica il file intero in memoria | streaming se servono log di più GB |
| R9 | Bassa | L'arresto forzato del collector (fine attività pianificata) perde fino a 60 s di dati | accettato; il gap viene registrato al riavvio |
| R10 | Bassa | Le cartelle dati non hanno ACL dedicate (THREAT_MODEL T10) | impostare le ACL in fase di installazione (M5) |

## 5. Conformità alla specifica (sintesi)

| Requisito | Stato |
|---|---|
| Due processi, collector senza librerie scientifiche | ✔ verificato da test |
| Sorgenti LHM, NVML, Event Log, contatori, SMART, WMI, psutil, HWiNFO CSV, simulatore | ✔ implementate; da verificare su hardware (R1) |
| Qualità dei dati, watchdog, errori immediati con debounce e gravità | ✔ |
| SQLite WAL, schema versionato, batch 60 s, ritenzione 48 h | ✔ |
| Finestre stazionarie, regimi fissi/adattivi, esclusione del throttling | ✔ |
| Indicatori, residui di baseline, modello continuo, copertura | ✔ |
| I-MR, EWMA, CUSUM, c/u, R1–R4, presupposti, Mann-Kendall, Fase I/II, limiti provvisori | ✔ (σ di lungo periodo per le carte per finestra: scostamento motivato) |
| Politica di allarme, budget, configurazione ±24 h, pulizia semi-automatica | ✔ |
| Diagnosi YAML con supporti e controindicazioni | ✔ |
| CLI completa, report accessibile, export anonimo, schema aperto, Prometheus/OTLP | ✔ (SVG invece di Plotly: scostamento motivato) |
| Health-check con interruzione di sicurezza, selftest di overhead | ✔ |
| Documenti di governance, sicurezza, AI, CI Windows, lock con hash, SBOM, firma | ✔ (workflow da eseguire su GitHub) |
| Validazione Fasi 0–5 | ⏳ solo controlli di coerenza sul simulatore |
