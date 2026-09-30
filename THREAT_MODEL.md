# Modello di minaccia (requisito 15.3)

Versione 0.1 — da rivedere prima di ogni release e dopo ogni nuova sorgente di dati.

## Asset

| Asset | Perché conta |
|---|---|
| Integrità del sistema operativo | il collector gira con privilegi elevati e, con LHM in modalità DLL, carica un driver kernel |
| Dati di telemetria e registro eventi | possono rivelare abitudini d'uso (orari, giochi) |
| Correttezza degli allarmi | un falso "tutto ok" può far ignorare un surriscaldamento reale |
| Configurazione (`hwdrift.yaml`) | decide quali eseguibili e URL vengono usati |

## Componenti e confini di fiducia

```
[utente] ──(CLI)──► hwdrift analyze/report/notify   (privilegi normali, DB in scrittura / sola lettura)
                         │ SQLite (file locale)
[Task Scheduler, admin] ─► hwdrift run (collector)   ◄── LHM web (loopback) / DLL + driver kernel
                                                    ◄── NVML, wevtutil, PowerShell, smartctl
```

- **Collector** (elevato): unico componente con privilegi. Legge sensori, scrive il DB.
- **Worker di analisi** (normale, priorità bassa): legge e scrive solo tabelle di analisi.
- **Notificatore** (normale, sessione utente): apre il DB in **sola lettura** (`mode=ro`),
  scrive solo il proprio `notifier_state.json` e `status.json`.
- **Report**: file HTML statico con Content-Security-Policy `default-src 'none'`, nessuno script.

## Minacce e contromisure (STRIDE)

| # | Minaccia | Contromisura | Verifica |
|---|---|---|---|
| T1 | *Tampering*: un utente non amministratore modifica `hwdrift.yaml` per far eseguire un binario arbitrario al collector elevato (es. `sources.smart.smartctl`) | il collector elevato deve leggere la configurazione da una cartella scrivibile solo dagli amministratori (vedi SECURITY.md, "installazione consigliata"); dispositivi SMART validati con regex; nessuna shell (`subprocess` con lista di argomenti) | revisione, `test_smart_collector` |
| T2 | *Spoofing / information disclosure*: l'URL di LHM viene puntato a un host remoto per esfiltrare o iniettare dati | URL accettato solo se loopback (`check_loopback`), nessun proxy (`ProxyHandler({})`) | `test_loopback_rejected` |
| T3 | *Tampering*: JSON di LHM, XML del registro eventi o CSV di HWiNFO malformati o ostili | limiti di dimensione (8 MB JSON, 4 MB XML), profondità massima dell'albero JSON, rifiuto di DTD/entità XML, campi CSV troncati, valori non numerici ignorati | test dei parser; fuzzing da aggiungere (M5) |
| T4 | *Injection* nel toast PowerShell tramite titoli/testi | il testo passa tramite variabili d'ambiente, mai interpolato nello script | revisione di `alerts/toast.py` |
| T5 | *SQL injection* | query parametrizzate; le poche stringhe composte usano nomi di tabella fissi | ruff `S608`, revisione |
| T6 | *Information disclosure* nell'export del dataset | export anonimo di default: solo canali canonici, nessun nome grezzo, nota, percorso o processo; ID macchina casuale | `test_jsonl_valid_against_schemas_and_anonymous` |
| T7 | *Denial of service*: il collector rallenta il PC o i giochi | budget di overhead, intervallo adattivo, game-safe, selftest in CI | `hwdrift selftest` |
| T8 | *Elevation of privilege* via driver kernel di LHM | preferire la modalità `web` (driver nel processo LHM, non in HWDrift); documentare Memory Integrity; nessuna ridistribuzione della DLL | documentazione |
| T9 | *Repudiation / integrità degli allarmi*: collector fermo interpretato come "sano" | heartbeat, canali `status.*`, notifica "collector fermo", stato "dati insufficienti" nel report | `test_notifier_stale_collector_and_power_info` |
| T10 | Database scrivibile da altri utenti locali (falsificazione dei dati) | ACL della cartella dati limitate all'utente e agli amministratori | da verificare in M5 |
| T11 | *Supply chain* | dipendenze bloccate con hash (`requirements/*.lock`), SBOM CycloneDX, release firmate con Sigstore, controllo licenze in CI | workflow `ci.yml`, `release.yml` |

| T12 | *Tampering* via GUI: la GUI (utente normale) scrive `hwdrift.yaml` nella cartella dati dell'utente; un collector elevato che lo leggesse eseguirebbe percorsi scelti da un non amministratore | il collector elevato rifiuta la configurazione implicita dalla cartella corrente e la documentazione impone `--config` su un file in cartella protetta; la GUI non espone il percorso di `smartctl` né altri eseguibili | `test_elevated_collector_refuses_cwd_config`, revisione |
| T13 | *DoS* locale: file `stop.request` e `live.active` nella cartella dati permettono a un processo dell'utente di fermare il collector o farlo scrivere ogni secondo | accettato: lo stesso utente può già terminare il processo; `live.json` è di pochi KB e si scrive solo con `live.active` recente (< 10 s) | revisione |
| T14 | Esecuzione di codice tramite l'eseguibile della GUI avviato come amministratore (UAC) | l'elevazione avviene solo su pulsante esplicito; l'eseguibile si distribuisce con hash e firma Sigstore | documentazione |

## Rischi residui

- Il collector elevato importa moduli Python dall'ambiente virtuale: se la cartella del
  venv è scrivibile da un utente non amministratore, quell'utente può eseguire codice
  come amministratore. **Installare il venv in una cartella protetta** (es.
  `C:\Program Files\HWDrift\venv`) quando il collector gira elevato.
- Con LHM in modalità `dll` il driver kernel è parte della superficie d'attacco.
- `health-check` genera calore: le soglie di interruzione sono lato software.
