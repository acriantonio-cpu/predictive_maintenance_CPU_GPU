# Metodologia

Questo documento spiega **come** HWDrift trasforma la telemetria in segnali e ipotesi, e
**perché** alcune scelte si discostano dalla specifica o la precisano. Ogni scelta è
un'ipotesi di progetto da confermare nelle fasi di validazione
([protocollo_validazione.md](protocollo_validazione.md)).

## 1. Dal campione all'aggregato

| Passo | Dove | Regola |
|---|---|---|
| Campionamento | `runner.py` | 1 Hz (0,5–5 s), orologio monotono per i tempi, UTC ms nel database |
| Qualità | `quality/sanity.py` | range fisico per canale, valori di lettura fallita (0, 255, −128), salto oltre `max_rate`·Δt, valore identico per `freeze_s` (900 s per le temperature) |
| Aggregazione | `storage/writer.py` | per minuto: mediana, min, max dei soli campioni OK; `n` e `valid_frac` documentano le esclusioni |
| Ritenzione | writer | grezzo 48 h; aggregati, eventi e analisi senza scadenza |

Il rilevamento dei valori congelati ha una **latenza pari a `freeze_s`**: le finestre che
iniziano nei primi 15 minuti di un sensore congelato possono passare. È un compromesso
tra falsi positivi (temperature intere stabili a riposo) e reattività; il test
`test_frozen_sensor_does_not_create_windows` lo documenta.

## 2. Finestre stazionarie

Finestra di 5 minuti, non sovrapposta alle precedenti, valida se: CV della potenza < 10%,
|pendenza della temperatura| < 0,5 °C/min, i 3 minuti precedenti hanno la stessa potenza
(riscaldamento), deviazione standard dell'utilizzo < 10 punti, tutti i minuti presenti e
con `valid_frac` ≥ 0,8, nessun evento di configurazione, gap o riavvio. Le finestre con
throttling termico o di potenza sono marcate `throttled` ed escluse dagli indicatori
(failure mode 5). Nota emersa dal simulatore: durante un throttling vero la potenza
oscilla e spesso **non** si formano finestre stazionarie; per questo la quota di
throttling si calcola sui minuti sotto carico, non sulle finestre.

## 3. Regimi

Default `fixed`: idle < 30% e alto ≥ 65% del 99° percentile della potenza per minuto
osservata nel periodo di calibrazione (prime 30 finestre stazionarie). La specifica
cita 50%/80% come esempio; con quei valori un gioco a carico CPU medio (40–50% del TDP)
cadrebbe in idle, quindi si sono scelte soglie più basse, configurabili. La modalità
`adaptive` (terzili) resta disponibile: su un PC quasi sempre inattivo i terzili cadono
tutti in idle. I confini restano bloccati; `hwdrift analyze --rebuild` li ricalcola.

## 4. Indicatori

| Indicatore | Formula | Regimi | Primario |
|---|---|---|---|
| `rth_cpu`, `rth_gpu` | (T − T_rif)/P | medio, alto | sì |
| `hotspot_delta_gpu` | T_hotspot − T_edge | medio, alto | sì |
| `fan_effort_*` | rpm (o % duty) medi nella finestra, solo se > 0 | tutti | sì |
| `idle_temp_*` | T − T_rif | idle | sì |
| `throttle_frac_*` | minuti con throttling termico / minuti sotto carico | giornaliero | sì |
| `whea_corrected`, `tdr`, `pcie_replay_gpu`, `unexpected_shutdown` | conteggi al giorno | giornaliero | sì (carta c) |
| `case_delta_cpu` | T_scheda madre − T_rif | medio, alto | no |
| `temp_resid[_fan]_*` | residuo di Huber T ~ P + T_rif (+ ventola) | per regime | no |
| `temp_cont_*` | residuo di T ~ P + P² + T_rif | tutti | no |
| `ref_temp` | T_rif a riposo | idle, giornaliero | contesto |

**T_rif.** Default: temperatura dell'SSD (`ssd0.temp_c`) come proxy dell'ambiente. Il
proxy si contamina se l'airflow peggiora (nel simulatore l'SSD sale con la polvere):
per questo `ref_temp` è un indicatore di *contesto*, usato come controindicazione solo
dove l'ambiente spiega il pattern (vedi §7).

## 5. Carte di controllo

Due livelli per ogni indicatore e regime:

| Livello | Osservazione | σ | Regole |
|---|---|---|---|
| `window` | una per finestra stazionaria | **di lungo periodo** (deviazione standard campionaria di Fase I) | solo R1 |
| `daily` | mediana giornaliera (≥ 2 finestre), solo giorni **completi** | MR̄/1,128, oppure robusta mediana(MR)/0,954 se i dati sono fortemente asimmetrici | R1, R2, R3 (R4 opzionale), MR, EWMA (λ=0,2, L=2,86), CUSUM (k=0,5, h=5), Mann-Kendall (α=0,01) |

**Perché σ di lungo periodo sulle finestre.** Sui dati simulati l'autocorrelazione a
lag 1 delle serie per finestra era 0,3–0,85: finestre della stessa sessione si
somigliano, quindi MR̄/d₂ sottostima la variabilità tra sessioni. Con σ da MR e tutte le regole il caso
sano generava decine di migliaia di segnali e un falso allarme "azione" in 30 giorni; con σ di lungo periodo e sola R1 i segnali scendono a poche centinaia e nessun allarme di manutenzione. Le regole
di sequenza e i metodi con memoria restano sulla carta giornaliera, quasi indipendente.
È la contromisura della sezione 7 ("si passa all'aggregazione giornaliera") resa
esplicita.

**Fase I.** Si chiude al primo istante in cui la carta ha ≥ 25 osservazioni, in ≥ 5
giorni e ≥ 5 sessioni (una sessione = pausa > 2 h o cambio di giorno). Si usa sempre il
*prefisso cronologico minimo*, così un'analisi che recupera settimane in un colpo solo
non include il guasto nei limiti. Pulizia dei punti oltre 3σ in massimo 3 iterazioni
(registrate). Prima della chiusura, con ≥ 12 osservazioni, i punti si confrontano con
limiti provvisori larghi 1,25× calcolati sui soli punti precedenti: i segnali sono
etichettati `provisional` e restano informativi. La valutazione provvisoria
è la stessa sia con analisi incrementali ogni 15 minuti sia con un'analisi che recupera
settimane in un colpo solo. `baseline lock` forza la chiusura con limiti provvisori. Serie costanti: σ minima per indicatore (es. 0,01 per la quota di
throttling), altrimenti la carta sarebbe degenerata.

**Segmenti.** Manutenzioni e `baseline start` chiudono il segmento di tutte le carte;
un cambio di configurazione (driver, BIOS, profilo) chiude solo quelle del componente
indicato in `detail.component` (es. il driver GPU non tocca le carte CPU). Il segmento
chiuso viene prima elaborato con i dati fino alla chiusura, poi archiviato.

## 6. Politica di allarme

- **Info**: almeno un segnale (qualsiasi regola) nel periodo di osservazione (14 giorni).
- **Attenzione**: segnali R1/R2/R3/R4/MR/C sullo stesso lato in **2 giorni consecutivi**.
- **Azione**: ipotesi di diagnosi i cui requisiti sono soddisfatti e che coinvolge almeno
  **2 carte a livello attenzione** (indicatori o regimi diversi), senza controindicazioni.
- Indicatori secondari: al massimo *info*. Indicatori di contesto: possono arrivare ad
  *attenzione* ma non generano allarmi propri.
- Segnali entro ±24 h da un evento di configurazione: etichetta `configuration`, nessun
  allarme di manutenzione; avviso che chiede conferma del cambio.
- Budget: oltre `action_budget_per_month` allarmi "azione" in 30 giorni, il notificatore
  sospende i toast di livello azione (tranne gli errori fatali) e il report chiede di
  rivedere soglie e regole.

## 7. Diagnosi

Regole in `src/hwdrift/diagnosis/rules/default.yaml`. Condizioni su indicatori (lato,
regimi, numero di componenti) ed eventi. Le controindicazioni contano solo a livello
attenzione (i segnali info isolati sono rumore atteso con ~50 carte); una
controindicazione `blocking` annulla l'ipotesi. Un'ipotesi viene proposta solo a livello
≥ attenzione (tranne le regole informative come "ambiente").

Ipotesi di simulazione da verificare in Fase 3: la ventola segue la temperatura del
*dissipatore*, quindi la pasta secca alza Rth ma non lo sforzo ventola. Una stanza più
fredda rallenta le ventole e alza Rth: stessa firma di una ventola degradata. Per questo
`fan_failure` ha come controindicazione bloccante `ref_temp` in calo; la polvere invece
no, perché un proxy contaminato dalla polvere la nasconderebbe.

## 8. Risultati sul simulatore (Fase 0, preliminari)

26 giorni per scenario, guasto dal giorno 12–17, seme 11 (`tests/integration/test_scenarios.py`):

| Scenario | Atteso | Ottenuto |
|---|---|---|
| healthy, driver_change, ambient, power_limit | nessun allarme di manutenzione | nessun allarme "azione", nessuna ipotesi di manutenzione |
| dust | polvere | `dust_airflow`, azione, prima ipotesi |
| paste | pasta | `paste_contact`, azione, prima ipotesi |
| fan_fail | ventola | `fan_failure`, azione, prima ipotesi |
| throttle | quota di throttling in salita, Rth non falsato | segnali su `throttle_frac_cpu`, nessun Rth da finestre con throttling |
| dust_then_clean | segmento chiuso, recupero visibile | vista efficacia "recuperato" |
| whea | carta c | segnali `C`, ipotesi instabilità |

Sono controlli di coerenza del software, non una validazione del metodo: ARL0/ARL1 in
funzione della magnitudo, sensibilità alla lunghezza della Fase I e confronto con le
alternative restano da misurare (Fase 0 completa).

## 9. Scostamenti dalla specifica

| Specifica | Implementazione | Motivo |
|---|---|---|
| Report con Plotly | SVG statico inline, nessuno script | file più piccolo, funziona con CSP restrittiva, accessibile con `<title>`/`<desc>` e tabella dati |
| Configurazione con pydantic | dizionari con validazione esplicita | il collector non carica pydantic (memoria) |
| statsmodels per Ljung-Box | implementazione diretta con scipy | una dipendenza in meno |
| pywin32 per l'Event Log | `wevtutil` come processo esterno | nessuna dipendenza, argomenti fissi |
| Regimi: esempio 50%/80% | default 30%/65% | vedi §3 |
| R2/R3 su tutte le carte | solo sulle carte giornaliere | autocorrelazione (vedi §5) |
| Solo Windows | collector Linux sperimentale | dimostra l'indipendenza del nucleo (requisito 15.2) |
