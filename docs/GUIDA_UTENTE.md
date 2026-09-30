# HWDrift — Guida passo passo

> Come funziona e come farlo partire. Documento mantenuto insieme al codice: ogni
> modifica al comportamento del tool aggiorna anche questa guida
> (vedi [CONTRIBUTING.md](../CONTRIBUTING.md)). Ultimo aggiornamento: versione 0.1.0.dev0.

HWDrift è un monitor **locale e senza cloud** della salute termica e del raffreddamento
di CPU e GPU. Impara come si comporta *il tuo* PC quando è sano (il **baseline**) e ti
avvisa quando il percorso termico peggiora: polvere, pasta termica secca, ventola o
pompa che cedono, throttling grave.

Non è un oracolo: **rileva derive** rispetto al baseline e propone **ipotesi** di
manutenzione con una confidenza qualitativa. Non stima vita residua né probabilità di
guasto e non tocca mai l'hardware (niente curve ventola, niente limiti di potenza).

---

## Indice

1. [Come funziona, in 2 minuti](#1-come-funziona-in-2-minuti)
2. [Requisiti](#2-requisiti)
3. [Installazione](#3-installazione)
4. [Prova senza hardware (simulatore)](#4-prova-senza-hardware-simulatore)
5. [Primo avvio sul tuo PC (Windows 11)](#5-primo-avvio-sul-tuo-pc-windows-11)
6. [Esecuzione in background](#6-esecuzione-in-background)
7. [Leggere il report](#7-leggere-il-report)
8. [Registrare le manutenzioni](#8-registrare-le-manutenzioni)
9. [Baseline: quando rifarlo](#9-baseline-quando-rifarlo)
10. [Health-check attivo (opzionale)](#10-health-check-attivo-opzionale)
11. [Export dei dati](#11-export-dei-dati)
12. [Importare log di HWiNFO](#12-importare-log-di-hwinfo)
13. [Configurazione](#13-configurazione)
14. [Risoluzione dei problemi](#14-risoluzione-dei-problemi)
15. [Riferimento dei comandi](#15-riferimento-dei-comandi)
16. [Glossario](#16-glossario)

---

## 1. Come funziona, in 2 minuti

```
 sensori ──► COLLECTOR (leggero, 1 Hz) ──► SQLite ◄── WORKER DI ANALISI (ogni 15 min)
 LHM, NVML,   qualità dati, errori immediati            finestre, indicatori, carte,
 Event Log    (throttling in pochi secondi)             segnali, ipotesi, report HTML
                         │                                         │
                         └────────► NOTIFICATORE (senza privilegi) ◄┘
                                    toast di Windows + stato persistente
```

Il percorso di un dato, passo per passo:

1. **Raccolta (collector).** Ogni secondo il collector legge temperature, potenze,
   ventole, clock e motivi di throttling da LibreHardwareMonitor, NVML (GPU NVIDIA),
   contatori di Windows e Registro eventi. Ogni campione riceve un **flag di qualità**:
   i valori impossibili (0, 255, salti di 50 °C in un secondo), fuori scala o
   **congelati** (identici per 15 minuti) vengono marcati ed esclusi dai calcoli.
2. **Errori immediati.** Se la GPU segnala throttling termico, se la CPU rallenta
   sotto carico vicino al limite di temperatura o se una ventola è ferma con
   temperatura alta, dopo pochi secondi (debounce) nasce un **episodio** e arriva un
   toast. Non si aspetta l'analisi statistica.
3. **Scrittura.** Ogni 60 s il collector scrive in un'unica transazione i campioni
   grezzi (tenuti 48 ore) e le **mediane al minuto** (tenute per sempre).
4. **Finestre stazionarie.** Il worker cerca intervalli di 5 minuti in cui il carico è
   stabile (potenza con variazione < 10%, temperatura che non sale né scende, carico
   iniziato da almeno 3 minuti, nessun throttling, nessun cambio di configurazione).
   Solo lì si misura la salute: così **il carico non viene scambiato per un guasto**.
5. **Regimi.** Ogni finestra ricade in un regime di potenza: *idle*, *medio*, *alto*.
6. **Indicatori normalizzati.** Per ogni finestra:
   - **Rth** = (T − T_rif) / P, la *resistenza termica* in °C/W (quanti gradi per
     watt): se sale, il raffreddamento peggiora;
   - **sforzo ventola**: giri a parità di potenza;
   - **Δ hotspot − edge** della GPU: contatto chip-dissipatore;
   - **temperatura a riposo** rispetto al riferimento;
   - **quota di throttling** sotto carico, e conteggi di errori WHEA/TDR.
7. **Carte di controllo I-MR.** Per ogni indicatore e regime, i primi giorni (almeno
   25 osservazioni in 5 giorni e 5 sessioni) formano la **Fase I**: da lì si calcolano
   linea centrale e limiti a 3σ, che poi restano **bloccati** (Fase II). I nuovi punti
   si confrontano con quei limiti con le regole R1 (un punto oltre 3σ), R2 (9 punti
   dallo stesso lato), R3 (6 punti in salita), più EWMA, CUSUM e trend Mann-Kendall
   sulle serie giornaliere.
8. **Allarmi.** *Info* = un segnale isolato; *Attenzione* = segnale che persiste per 2
   giorni consecutivi; *Azione* = almeno due carte correlate a livello attenzione
   combinate da una regola di diagnosi.
9. **Ipotesi.** Regole dichiarative (file YAML) mappano le combinazioni di segnali su
   ipotesi: polvere, pasta, ventola, ambiente, profilo di potenza, instabilità. Ogni
   ipotesi riporta segnali a supporto, segnali contrari e verifiche ordinate dalla
   meno alla più invasiva.
10. **Report.** Un file HTML autonomo, senza script e senza rete, con semaforo per
    componente, carte, eventi, copertura dei dati ed efficacia delle manutenzioni.

| Cosa vedi | Cosa significa |
|---|---|
| Rth CPU e sforzo ventola salgono insieme | probabile **polvere** o flusso d'aria ostruito |
| Rth CPU sale, ventole stabili | probabile **pasta secca** o dissipatore montato male |
| Rth sale e le ventole girano meno | **ventola o pompa** che cede |
| Throttling in aumento senza Rth in salita | **limite di potenza o profilo**, non raffreddamento |
| Tutto si muove insieme al riferimento ambiente | **ambiente** (stagione, stanza): nessuna azione |
| Gradino subito dopo un aggiornamento driver/BIOS | **confondente**: la carta riparte, nessun allarme |

---

## 2. Requisiti

- **Windows 11** (piattaforma della v1). Il nucleo è indipendente dal sistema operativo:
  su Linux funzionano simulatore, analisi, report e un collector sperimentale.
- **Python 3.11 o 3.12** (consigliato 3.12).
- **LibreHardwareMonitor** (consigliato) per temperature CPU, scheda madre, ventole.
- Driver **NVIDIA** per la sorgente NVML (opzionale: senza GPU NVIDIA il tool funziona
  con meno indicatori).
- ~80 MB/giorno di spazio per i dati grezzi (tenuti 48 ore) e ~1,5 MB/giorno per gli
  aggregati permanenti.

---

## 3. Installazione

In PowerShell, nella cartella del progetto:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
# installazione riproducibile con dipendenze bloccate (hash verificati)
pip install --require-hashes -r requirements\dev.lock
pip install --no-deps -e .
# sorgenti Windows (NVML, contatori di prestazione, pythonnet per la DLL di LHM)
pip install -e ".[windows]"
hwdrift version
```

Con **uv** (più veloce): `uv venv && uv pip install --require-hashes -r requirements\dev.lock && uv pip install --no-deps -e .`

Da VS Code: apri la cartella, accetta le estensioni consigliate (Python, Pylance, Ruff,
Even Better TOML, YAML), seleziona l'interprete `.venv`. In *Run and Debug* trovi le
configurazioni **Run (simulator)**, **Run (hardware)**, **Simulate 30 giorni**,
**Analyze** e **Pytest**; in *Terminal → Run Task* lint, type check, test e selftest.

---

## 4. Prova senza hardware (simulatore)

Il modo più rapido per capire il tool: si generano settimane di dati sintetici in
pochi secondi, con un guasto iniettato.

```powershell
hwdrift simulate --list                         # scenari disponibili
hwdrift --db demo.sqlite simulate dust --days 30
hwdrift --db demo.sqlite analyze                # finestre, carte, ipotesi + report
hwdrift --db demo.sqlite status
start $env:LOCALAPPDATA\HWDrift\report.html     # apre il report
```

Nello scenario `dust` la polvere si accumula dal giorno 12: il report mostra Rth e
sforzo ventola in salita e l'ipotesi **"Polvere o flusso d'aria ostruito"** a livello
*Azione*, con le verifiche suggerite. Prova anche `paste`, `fan_fail`,
`dust_then_clean` (con la vista *Efficacia della manutenzione*) e i controlli negativi
`healthy`, `driver_change`, `ambient`, `power_limit`, che **non** devono produrre
allarmi di manutenzione.

Collector in tempo reale con simulatore (nessun privilegio necessario):

```powershell
hwdrift --db live.sqlite run --simulate throttle --fault-after 30
# dopo ~30 s la ventola simulata si ferma: in pochi secondi compare l'errore immediato
```

---

## 5. Primo avvio sul tuo PC (Windows 11)

### Passo 1 — Prepara LibreHardwareMonitor

1. Scarica LibreHardwareMonitor dalle release ufficiali e avvialo **come amministratore**.
2. Menu *Options → Remote Web Server → Run* (porta predefinita 8085). HWDrift legge
   `http://127.0.0.1:8085/data.json` e rifiuta qualsiasi indirizzo non di loopback.
3. In alternativa (modalità `dll`) imposta `sources.lhm.mode: dll` e `dll_path` verso
   `LibreHardwareMonitorLib.dll`: in quel caso è HWDrift a dover girare come
   amministratore. Attenzione a Memory Integrity e agli anti-cheat (vedi §14).

### Passo 2 — Pulisci il PC (consigliato)

Il baseline rappresenta lo stato **attuale** del PC. Se il PC è già sporco, il degrado
entra nei limiti e il tool non lo segnalerà (failure mode 1). Se puoi, pulisci filtri
e ventole prima di iniziare e dichiaralo al passo 5.

### Passo 3 — Crea la configurazione e verifica i sensori

```powershell
hwdrift init-config                              # crea hwdrift.yaml di esempio
hwdrift discover --write-profile profilo.yaml    # elenca i sensori e propone la mappatura
```

`discover` mostra per ogni sorgente i sensori trovati e il **canale canonico** proposto
(es. `cpu.pkg.temp_c`, `gpu0.power_w`). Controlla che ci siano almeno:

| Canale | Serve per |
|---|---|
| `cpu.pkg.temp_c`, `cpu.pkg.power_w` | Rth CPU (indispensabili) |
| `gpu0.temp_edge_c`, `gpu0.power_w` | Rth GPU |
| `cpu.fan_rpm` o `chassis.fan1_rpm`, `gpu0.fan_rpm`/`gpu0.fan_pct` | sforzo ventola |
| `gpu0.temp_hotspot_c` | Δ hotspot − edge |
| `ssd0.temp_c` o `mb.temp_c` | riferimento T_rif (proxy dell'ambiente) |
| `cpu.clock_eff_mhz`, `gpu0.throttle_reasons` | throttling |

Se un sensore non è mappato o è mappato male, copia la sezione `profile.mapping` da
`profilo.yaml` in `hwdrift.yaml` e correggila (un canale vuoto `''` esclude il sensore).

### Passo 4 — Misura l'overhead

```powershell
hwdrift selftest --seconds 60
```

Verifica che il collector stia entro il budget (≤ 1% di un core, ≤ 100 MB) e che tutte
le sorgenti siano `ok`. Esce con errore se il budget è superato.

### Passo 5 — Avvia la raccolta e dichiara lo stato del PC

```powershell
hwdrift baseline start --state clean   # oppure --state unknown se non hai pulito
hwdrift run                            # in un terminale amministratore; Ctrl+C per fermare
```

### Passo 6 — Usa il PC normalmente per almeno 5 giorni

La Fase I si chiude da sola quando ogni carta ha almeno 25 osservazioni, in 5 giorni
diversi e 5 sessioni. Prima di allora le carte sono **provvisorie** e il report dice
"baseline in costruzione": l'assenza di segnali **non** significa buona salute.
I regimi poco usati (es. carico alto su un PC da ufficio) possono restare senza carta:
il report lo dichiara come **copertura insufficiente**; vedi il §10 per rimediare.

### Passo 7 — Analizza e leggi il report

```powershell
hwdrift analyze        # rigenera anche %LOCALAPPDATA%\HWDrift\report.html
```

---

## 6. Esecuzione in background

Tre attività pianificate (Utilità di pianificazione):

| Attività | Quando | Privilegi |
|---|---|---|
| `HWDrift\Collector` → `hwdrift run` | all'accesso | elevati (sensori a basso livello) |
| `HWDrift\Analyze` → `hwdrift analyze` | ogni 15 minuti | normali, priorità BELOW_NORMAL |
| `HWDrift\Notify` → `hwdrift notify` | all'accesso | normali (sessione utente, database in sola lettura) |

```powershell
hwdrift schedule install            # mostra i comandi schtasks (prova a secco)
hwdrift schedule install --apply    # li crea (PowerShell come amministratore)
hwdrift schedule remove --apply
```

Il collector registra da solo i **gap** (sospensione, ibernazione, spegnimento) e i
**riavvii**; il notificatore avvisa se il collector è fermo da più di 5 minuti mentre
il PC è acceso. In modalità **game-safe** (processi anti-cheat in lista) le sorgenti
a basso livello si sospendono e restano NVML ed Event Log.

---

## 7. Leggere il report

Il report (`%LOCALAPPDATA%\HWDrift\report.html`) si apre offline, anche con tastiera e
lettore di schermo. Sezioni:

1. **Stato generale** — un semaforo per CPU, GPU, raffreddamento e dischi, con una
   frase che spiega il motivo. Stati: *OK*, *Attenzione*, *Azione*, *Dati insufficienti*
   (scritti a parole, non solo a colori).
2. **Errori immediati** — episodi di throttling grave o ventola ferma: ora, durata,
   componente, motivo, gravità; "episodio in corso" se non è finito.
3. **Ipotesi di manutenzione** — ipotesi attive con confidenza (bassa/media/alta),
   segnali a supporto e contrari, verifiche ordinate dalla meno invasiva.
4. **Allarmi** — tutti gli allarmi attivi con il livello.
5. **Carte di controllo** — la tabella dello stato di ogni carta (Fase I/II,
   provvisoria/definitiva, osservazioni, autocorrelazione); poi le carte principali
   (modalità semplice) e tutte le altre in *Modalità avanzata*. In ogni carta:
   - punti = osservazioni; zona ombreggiata = Fase I;
   - linea puntinata = linea centrale; continua = limiti a 3σ; tratteggiata = 2σ;
   - **triangoli** = segnali (la regola è nel tooltip e nell'elenco *Segnali*);
   - linee verticali = eventi (verde = manutenzione, arancio = configurazione);
   - sotto, la **carta MR** (range mobili: salti improvvisi);
   - *Tabella dati* = equivalente testuale del grafico.
6. **Eventi** — manutenzioni, cambi di driver/BIOS, riavvii, gap.
7. **Copertura e qualità dei dati** — finestre valide per regime e settimana; minuti
   con campioni esclusi per canale; ultimo dato ricevuto.
8. **Efficacia della manutenzione** — dopo una pulizia dichiarata, di quante σ
   l'indicatore è tornato verso il baseline ("recuperato", "migliorato", "non migliorato").
9. **Overhead** — CPU e RAM del collector nelle ultime 24 ore rispetto al budget.

**Livelli di allarme.** *Info*: da osservare, niente notifiche. *Attenzione*: segnale
persistente, arriva un toast. *Azione*: ipotesi supportata da più indicatori, arriva un
toast; segui le verifiche suggerite nell'ordine.

**Avvertenze.** Non è un avviso di sicurezza né una diagnosi di guasto. Aprire il PC
può invalidare la garanzia; sui portatili segui le procedure del produttore. In caso
di temperature elevate o spegnimenti, non attendere il tool: intervieni.

---

## 8. Registrare le manutenzioni

Ogni intervento va registrato: chiude il segmento delle carte, fa partire una nuova
Fase I e alimenta la vista "efficacia della manutenzione".

```powershell
hwdrift event kinds                                            # tipi disponibili
hwdrift event add maintenance.clean --note "filtri e ventole"
hwdrift event add maintenance.repaste --at "2026-09-28 18:30"
hwdrift event add config.profile --note "profilo ventole silenzioso"
hwdrift event list --days 60
```

Se un indicatore scende di colpo senza un evento registrato, il tool chiede
"Hai fatto manutenzione?" e propone di registrarla. I cambi di driver GPU e BIOS
vengono rilevati e registrati da soli.

---

## 9. Baseline: quando rifarlo

```powershell
hwdrift baseline status                     # stato di ogni carta
hwdrift baseline start --state clean        # nuova Fase I per tutte le carte
hwdrift baseline start --component gpu      # solo le carte GPU
hwdrift baseline start --chart "rth_cpu|high|daily"
hwdrift baseline lock                       # chiude la Fase I subito (limiti provvisori, più larghi)
hwdrift analyze --rebuild                   # ricalcola tutto dagli aggregati (nuovi regimi)
```

Rifai il baseline dopo: una manutenzione (automatico se registrata), un cambio di
hardware o di posizione del PC, un cambio di profilo ventole voluto. **Non** rifarlo
per "far sparire" un allarme: i limiti bloccati esistono proprio per non assorbire la
deriva.

---

## 10. Health-check attivo (opzionale)

Se non usi mai il PC a pieno carico, il regime "alto" resta senza carta. Il
health-check applica, **solo su tua richiesta**, un carico CPU breve e ripetibile, con
interruzione automatica se la temperatura supera la soglia (default 90 °C), se compare
throttling o se i dati smettono di arrivare.

```powershell
hwdrift run                              # il collector deve essere attivo
hwdrift healthcheck --yes                # 5 minuti di carico (config: healthcheck.duration_s)
```

Ripetilo ogni settimana nelle stesse condizioni per avere finestre confrontabili.

---

## 11. Export dei dati

```powershell
hwdrift export --format csv     --out export\          # anonimo per default
hwdrift export --format jsonl   --out export\          # conforme agli schemi in schemas/
hwdrift export --format parquet --out export\          # richiede: pip install -e ".[parquet]"
hwdrift export --format prometheus --out hwdrift.prom  # textfile collector di node_exporter
hwdrift export --format otlp    --out hwdrift-otlp.json
hwdrift export --no-anonymize --format csv --out privato\   # include le note libere
```

L'export anonimo contiene solo canali canonici e valori numerici: niente nomi di
processo, utente, percorsi, nomi grezzi dei sensori o note. L'ID macchina è casuale e
generato localmente, non derivato dall'hardware.

---

## 12. Importare log di HWiNFO

```powershell
hwdrift import-hwinfo C:\log\hwinfo.csv            # fuso orario locale
hwdrift import-hwinfo C:\log\hwinfo.csv --tz-offset 1
hwdrift analyze
```

Le colonne vengono mappate con regole sui nomi (in inglese; per altri nomi aggiungi la
chiave `"Nome colonna [unità]": canale` in `profile.mapping`).

---

## 13. Configurazione

Il file `hwdrift.yaml` (cartella corrente o `%LOCALAPPDATA%\HWDrift\`) sovrascrive i
default chiave per chiave; una chiave sconosciuta è un errore esplicito. Le chiavi più
utili (esempio completo in [`hwdrift.example.yaml`](../hwdrift.example.yaml)):

| Chiave | Default | Cosa fa |
|---|---|---|
| `sampling.interval_s` | 1.0 | intervallo di campionamento (0,5–5 s) |
| `sources.lhm.mode` | `web` | `web` (server di LHM) o `dll` (pythonnet) |
| `profile.reference.mode` | `channel` | T_rif: `channel` (proxy, es. `ssd0.temp_c`), `user` (valore fisso), `none` |
| `profile.cpu.tjmax_c` | 100 | limite termico CPU per gli errori immediati |
| `regimes.mode` | `fixed` | `fixed` (30%/65% della potenza max) o `adaptive` (terzili) |
| `spc.phase1_min_days` | 5 | giorni minimi di Fase I |
| `alerts.action_budget_per_month` | 2 | oltre, niente notifiche "azione": rivedere le soglie |
| `game_safe.processes` | anti-cheat comuni | processi che sospendono le sorgenti a basso livello |

Variabili d'ambiente: `HWDRIFT_HOME` (cartella dati), `HWDRIFT_CONFIG` (file di
configurazione).

---

## 14. Risoluzione dei problemi

| Problema | Soluzione |
|---|---|
| `lhm non disponibile: server web ... non raggiungibile` | Avvia LHM come amministratore e abilita *Remote Web Server* |
| Nessun sensore CPU con `mode: dll` | Avvia il terminale come amministratore; verifica Memory Integrity (Sicurezza di Windows → Isolamento core) e l'antivirus |
| Stutter nei giochi o conflitti con anti-cheat | Aggiungi il processo a `game_safe.processes`; usa `mode: web` |
| Report: "Baseline in costruzione" dopo giorni | Controlla la sezione *Copertura*: il regime non viene visitato → health-check |
| Report: "Dati non aggiornati" | Il collector è fermo: `hwdrift status`, controlla l'attività pianificata |
| Toast non visibili | Focus Assist o gioco a schermo intero: lo stato resta nel report e in `status.json` |
| Troppi allarmi | Il budget mensile li sospende; rivedi `spc`/`alerts` e le regole in `diagnosis/rules/default.yaml` |
| `Errore di configurazione: chiave sconosciuta` | Refuso in `hwdrift.yaml`: il messaggio indica la chiave |

Log: `%LOCALAPPDATA%\HWDrift\hwdrift.log` (rotazione a 2 MB). Aggiungi `-v` a qualsiasi
comando per il dettaglio.

---

## 15. Riferimento dei comandi

| Comando | Funzione |
|---|---|
| `hwdrift discover` | elenca i sensori e propone la mappatura sui canali canonici |
| `hwdrift run` | avvia il collector residente (`--simulate` per il simulatore) |
| `hwdrift analyze` | worker di analisi: finestre, indicatori, carte, segnali, ipotesi, report |
| `hwdrift baseline start / lock / status` | gestione della Fase I |
| `hwdrift event add / list / kinds` | registro delle manutenzioni e degli eventi |
| `hwdrift report` | genera il report HTML |
| `hwdrift export` | CSV, JSONL, Parquet, Prometheus, OTLP (anonimo per default) |
| `hwdrift import-hwinfo` | importa un log CSV di HWiNFO |
| `hwdrift selftest` | misura l'overhead e lo stato dei collector |
| `hwdrift healthcheck --yes` | carico breve con interruzione di sicurezza (opzionale) |
| `hwdrift simulate` | dati sintetici offline (scenari di guasto) |
| `hwdrift notify` | notificatore non privilegiato |
| `hwdrift status` | collector, episodi in corso, allarmi attivi |
| `hwdrift schedule install / remove` | attività pianificate di Windows |
| `hwdrift init-config` | crea `hwdrift.yaml` di esempio |

Opzioni globali: `--config FILE`, `--db FILE`, `-v`.

---

## 16. Glossario

- **Baseline / Fase I**: periodo in cui il PC è considerato sano e da cui si calcolano i
  limiti. **Fase II**: monitoraggio con limiti bloccati.
- **Rth**: resistenza termica, (T − T_rif)/P in °C/W.
- **T_rif**: temperatura di riferimento (ambiente o suo proxy interno).
- **Finestra stazionaria**: 5 minuti di carico stabile in cui gli indicatori sono confrontabili.
- **Regime**: fascia di potenza (idle, medio, alto).
- **Carta I-MR**: carta degli individuali e dei range mobili; limiti a ±3σ con
  σ = MR̄/1,128.
- **σ di lungo periodo**: deviazione standard campionaria, usata per le carte per
  finestra (autocorrelate).
- **EWMA, CUSUM, Mann-Kendall**: metodi sensibili alle derive lente, sulle serie giornaliere.
- **Throttling**: riduzione del clock per limite termico o di potenza.
- **WHEA**: errori hardware registrati da Windows; **TDR**: reset del driver video.
- **Copertura insufficiente**: troppe poche osservazioni per una carta; non significa
  che il componente sia sano.

Per i dettagli statistici vedi [metodologia.md](metodologia.md); per la validazione
[protocollo_validazione.md](protocollo_validazione.md).
