# Audit del codice — HWDrift 0.1.0.dev0

> Copia in inglese: [`en/AUDIT.md`](en/AUDIT.md); i due file vanno tenuti allineati.

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

---

## 6. Addendum — riavvio del PC e interfaccia grafica

Richiesta: verificare cosa succede spegnendo e riaccendendo il PC, e aggiungere una GUI.

### 6.1 Problemi trovati e corretti

| # | Gravità | Problema | Correzione | Test di regressione |
|---|---|---|---|---|
| A22 | **Alta** | Uno spegnimento durante un episodio di throttling lasciava l'episodio "in corso" per sempre (report e stato continuavano a mostrare un'emergenza inesistente) | all'avvio del collector gli episodi aperti vengono chiusi all'ultimo battito noto | `test_reboot_closes_orphan_episodes_and_records_gap_and_reboot` |
| A23 | **Alta** (portatili) | `schtasks /Create` applica di default "non avviare a batteria", "ferma se passa a batteria" e "ferma dopo 72 ore": il collector non sarebbe partito a batteria e si sarebbe fermato dopo tre giorni | attività definite con XML: nessun limite di tempo, partenza a batteria, riavvio automatico se termina | `test_task_xml_is_valid_and_survives_laptop_and_72h_defaults` |
| A24 | Bassa | `hwdrift status` stampava righe "NOTIFICA" (rumore) | modalità silenziosa | `test_status_is_quiet_and_does_not_log_notifications` |
| A25 | Bassa | Con `--db` esplicito il collector non scriveva il log su file: la scheda log della GUI e il pacchetto diagnostico sarebbero stati vuoti | il log va sempre nella cartella dati | prova con la GUI |
| A26 | Bassa | `HWDRIFT_HOME` non prevaleva su `data_dir` della configurazione: la demo della GUI avrebbe potuto scrivere nella cartella reale | l'override esplicito di ambiente ha la precedenza | `test_window_shows_status_charts_events_and_saves_config` |

### 6.2 Cosa succede a un riavvio (verificato con orologio simulato)

Spegnimento brusco → riavvio dopo 10 ore: nessun episodio orfano, un `system.gap`, due
`system.collector_start`, dati regolari dopo il riavvio, baseline invariato. Limiti
residui: si perdono fino a ~60 s di dati grezzi; tra accensione e accesso a Windows non ci
sono dati (il collector parte all'accesso); l'Avvio rapido di Windows può nascondere il
`system.reboot`, ma il gap è registrato dal battito.

### 6.3 GUI — controlli

- Livello dati (`gui/data.py`, senza Tk): 9 test unitari; finestra reale: test di integrazione
  sotto Xvfb (stato, carte, tempo reale da `live.json`, registrazione eventi, salvataggio
  configurazione valida e rifiuto di una non valida, analisi in background, pacchetto
  diagnostico, chiusura). Il test si salta se non c'è un display.
- Revisione visiva (screenshot): corretti layout del modulo di configurazione (campi tagliati),
  legenda sovrapposta al titolo, etichette dei valori, etichetta d'asse troncata.
- Eseguibile: costruito con PyInstaller **su Linux** (stessa spec) per validare import
  dinamici, dati inclusi e dispatch CLI/GUI: CLI completa (simulate, analyze, status, report,
  run) e finestra funzionanti dall'eseguibile congelato (63 MB).

### 6.4 Rischi residui

| # | Priorità | Rischio | Raccomandazione |
|---|---|---|---|
| R11 | **Alta** | Il `.exe` Windows non è stato costruito né provato qui (nessun Windows): Tk su Windows, richiesta UAC (`ShellExecute runas`), importazione dell'XML di `schtasks`, nascondere la console | eseguire il workflow "Build exe" e provare su Windows 11 (elenco in `docs/GUIDA_UTENTE.md` §6A); `TODO` in `cli._tasks`/`task_definitions` |
| R12 | Media | Eseguibile non firmato: SmartScreen e alcuni antivirus possono segnalare gli eseguibili PyInstaller (falsi positivi) | firma Authenticode (certificato) o distribuzione tramite installer firmato; pubblicare hash e firma Sigstore; UPX disattivato |
| R13 | Media | La GUI scrive `hwdrift.yaml` modificabile dall'utente: un collector elevato che lo leggesse riaprirebbe THREAT_MODEL T1 | il collector elevato usa un file in cartella protetta con `--config` (avviso nella GUI e nel rifiuto della CLI) |
| R14 | Bassa | I grafici della GUI non hanno tabella dati equivalente né navigazione da tastiera del canvas (il report HTML sì) | accettato per la v1; la GUI non sostituisce il report accessibile |
| R15 | Bassa | Il collector elevato e la GUI devono condividere la cartella dati (`LOCALAPPDATA` dello stesso utente); con UAC con credenziali di un altro amministratore le cartelle differiscono | passare `--db`/`HWDRIFT_HOME` espliciti |

---

## 7. Addendum — localizzazione inglese

Richiesta: tradurre la GUI in inglese e creare una copia inglese della documentazione.

### 7.1 Impostazione

- **Catalogo** (`src/hwdrift/i18n.py`, `i18n_en.py`): il testo italiano nel codice è la *chiave*,
  `tr("...")` restituisce la traduzione inglese con lingua `en` (predefinita) e il testo italiano
  con `it`. Un testo assente dal catalogo torna in italiano (mai un errore). La lingua si sceglie
  con `language` in configurazione, sovrascritta dalla variabile d'ambiente `HWDRIFT_LANGUAGE`.
- **Cosa si traduce**: tutta la GUI, il report HTML, gli allarmi, le ipotesi di diagnosi (titoli,
  azioni, supporti), notifiche e toast, descrizioni di eventi e indicatori, avvisi dell'analisi e
  configurazione di esempio (`init-config`). Gli allarmi sono generati dal worker e salvati nel
  database: nascono nella lingua configurata; un cambio lingua si vede alla prossima analisi.
- **Cosa non si traduce**: aiuto e messaggi della riga di comando (Typer) e righe di log restano
  in italiano (limite di ambito voluto: la richiesta riguardava la GUI e ciò che mostra).

### 7.2 Osservazioni

| # | Gravità | Osservazione | Azione |
|---|---|---|---|
| L1 | Media | Rischio di buchi silenziosi: una chiave sbagliata mostrerebbe italiano nella GUI inglese | `tests/unit/test_i18n.py` scandisce ogni letterale `tr("…")` nei sorgenti (più testi delle regole di diagnosi, descrizioni di indicatori/eventi, etichette dei campi della GUI) e fallisce se manca una voce; controlla anche che i `{segnaposto}` coincidano tra le lingue |
| L2 | Bassa | La lingua della GUI deve seguire i contenuti creati dal worker, altrimenti l'analisi pianificata (italiano) e la GUI (inglese) si sovrascriverebbero i testi degli allarmi | una sola lingua per installazione (`language`), applicata da ogni componente alla creazione |
| L3 | Bassa | I test esistenti verificano testi italiani | la fixture globale dei test gira in italiano (`HWDRIFT_LANGUAGE=it`); i test nuovi (`test_english.py`, test della finestra bilingue) verificano l'inglese, compresa l'assenza di marcatori italiani nel report inglese |
| L4 | Bassa | Due copie della documentazione possono divergere | `tests/unit/test_docs_sync.py` verifica che ogni documento inglese esista, rimandi al suo originale italiano e abbia lo stesso numero di titoli; CONTRIBUTING impone di aggiornare entrambi |

### 7.3 Rischi residui

| # | Priorità | Rischio | Raccomandazione |
|---|---|---|---|
| R16 | Media | Le traduzioni inglesi sono state scritte da uno strumento di AI e non riviste da un madrelingua | far rileggere il catalogo (`i18n_en.py`) e `docs/en/` (vedi AI_USAGE.md) |
| R17 | Bassa | Messaggi della CLI e log restano in italiano: la scheda log della GUI inglese mostra righe italiane | tradurre i messaggi di log e l'aiuto della CLI se il tool esce dalla cerchia italofona |
| R18 | Bassa | La lingua dei testi di allarme già salvati cambia solo alla prossima analisi | accettato; eseguire **Analyze now** dopo il cambio lingua |
