# Protocollo di validazione (sezione 12) e stato attuale

> Copia in inglese: [`docs/en/validation_protocol.md`](en/validation_protocol.md); i due file vanno tenuti allineati.

| Fase | Metodo | Stato | Strumento nel repository |
|---|---|---|---|
| 0. Simulazione statistica | generatore sintetico con degrado, cambi di carico, ambiente | **parziale**: scenari di coerenza e ARL di R1 su dati indipendenti | `hwdrift simulate`, `sim/`, `tests/integration/test_scenarios.py`, `tests/property/` |
| 1. Validazione software | confronto con HWiNFO/GPU-Z, 72 h, sospensione, sensori mancanti, reset driver, privilegi, overhead | da fare su hardware | `hwdrift selftest`, `scripts/m0_spike.py`, `hwdrift import-hwinfo` |
| 2. Replay su dati reali | log HWiNFO/LHM propri e di volontari | da fare | `hwdrift import-hwinfo` + `analyze` |
| 3. Guasti controllati | iniezioni reversibili in cieco, ≥ 3 ripetizioni | da fare | `hwdrift event add`, report "efficacia" |
| 4. Pilota sul campo | 10–30 macchine, 3–6 mesi, consenso informato | da fare | `hwdrift export` (anonimo) |
| 5. Confronto con alternative | soglia fissa, trend lineare, EWMA/CUSUM, Isolation Forest a pari ARL0 | da fare | `spc/trend.py` (trend lineare), EWMA/CUSUM già calcolati |

## Fase 0 — cosa resta da misurare

1. ARL0 e ARL1 delle carte **per finestra** (σ di lungo periodo, R1) e **giornaliere**
   (R1–R3, EWMA, CUSUM, MK) su serie AR(1) con φ ∈ {0; 0,3; 0,6; 0,9} e rumore non
   normale; confronto con i valori teorici (370 per R1 su dati indipendenti, verificato
   in `test_arl0_r1_close_to_370`).
2. Ritardo di rilevamento in funzione della magnitudo della deriva (dust `rate`
   0,005–0,05/giorno) e del gradino (ventola `severity` 0,2–0,8).
3. Sensibilità alla lunghezza e varietà della Fase I (`phase1_min_days` 3–14).
4. Falsi allarmi per macchina-mese sui controlli negativi con 20 semi diversi.
5. Regimi fissi vs adattivi vs modello continuo (RQ6).

Procedura suggerita:

```powershell
for ($s=1; $s -le 20; $s++) {
  hwdrift --db "f0-healthy-$s.sqlite" simulate healthy --days 60 --seed $s
  hwdrift --db "f0-healthy-$s.sqlite" analyze --no-report
}
```

e raccolta di `alerts`/`signals` con `hwdrift export --format jsonl`.

## Fase 3 — sicurezza delle prove

Non disattivare mai le protezioni termiche; definire per ogni macchina una soglia di
interruzione inferiore al limite di throttling; ogni iniezione deve essere annullabile
subito; registrare ogni iniezione con `hwdrift event add user.note --note "iniezione X"`
e l'istante preciso (analisi in cieco: chi analizza non vede il registro fino alla fine).

## Criteri di accettazione (proposte)

- ≤ ~1 allarme "azione" per macchina al mese;
- nessun allarme di manutenzione nei controlli negativi;
- overhead entro il budget (≤ 1% di un core, ≤ 100 MB; worker ≤ 300 MB, ≤ 30 s);
- ritardo massimo di rilevamento del surrogato di polvere: da fissare dopo la Fase 0.
