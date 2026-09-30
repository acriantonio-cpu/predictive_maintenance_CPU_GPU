# Schema aperto HWDrift (v1.0)

> Copia in inglese: [`../docs/en/schemas.md`](../docs/en/schemas.md); i due file vanno tenuti allineati.

Schemi JSON (draft 2020-12) per telemetria di condizione hardware ed eventi di
manutenzione. `hwdrift export --format jsonl` produce un file per tipo, un record per
riga, conforme a questi schemi; la CI li valida.

| File | Contenuto |
|---|---|
| `sample.schema.json` | aggregato a 1 minuto di un canale canonico (`cpu.pkg.temp_c`, ...) |
| `indicator.schema.json` | indicatore di salute per finestra o giornaliero |
| `event.schema.json` | manutenzioni, cambi di configurazione, gap, errori hardware |
| `chart_state.schema.json` | limiti e fase di un segmento di carta |
| `signal.schema.json` | segnale di una carta (regola, lato, etichetta) |

Convenzioni: timestamp UTC in millisecondi interi; nomi dei canali in minuscolo
separati da punti; `machine_id` casuale locale. Prima di estendere lo schema,
verificare le convenzioni esistenti (OpenTelemetry semantic conventions per
`hw.*`, nomi di metriche Prometheus di node_exporter `node_hwmon_*`) e riusarle
dove possibile: vedi `docs/interoperabilita.md`.
