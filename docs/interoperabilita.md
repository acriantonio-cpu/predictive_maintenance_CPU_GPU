# Standard e interoperabilità (requisito 15.6)

> Copia in inglese: [`docs/en/interoperability.md`](en/interoperability.md); i due file vanno tenuti allineati.

## Schema aperto

`schemas/*.schema.json` (JSON Schema 2020-12, versione `1.0`) descrive campioni
aggregati, indicatori, eventi di manutenzione, stato delle carte e segnali.
`hwdrift export --format jsonl` produce record conformi; `scripts/validate_export.py`
li valida ed è eseguito in CI.

Principi: timestamp UTC in millisecondi interi; nomi di canale `componente.misura_unità`
in minuscolo (`cpu.pkg.temp_c`, `gpu0.power_w`); nessun identificatore hardware;
`machine_id` casuale locale; eventi `maintenance.*` come etichette per la validazione.

## Prometheus / OpenMetrics

`hwdrift export --format prometheus --out C:\node_exporter\textfile\hwdrift.prom`
produce il formato di esposizione testuale per il *textfile collector* di
node_exporter / windows_exporter:

- `hwdrift_indicator{indicator,regime,level}`: ultimo valore di ogni indicatore;
- `hwdrift_chart_limit{indicator,regime,level,limit=center|ucl|lcl}`;
- `hwdrift_active_alerts{level}`;
- `hwdrift_last_sample_timestamp_seconds`.

Nessun server HTTP: il file si rigenera con un'attività pianificata dopo `analyze`.

## OpenTelemetry

`hwdrift export --format otlp` scrive un file OTLP/JSON (`resourceMetrics` →
`scopeMetrics` → gauge `hwdrift.indicator` con attributi `indicator`, `regime`,
`level`; risorsa `service.name=hwdrift`, `host.id=<machine_id>`). Nessun invio di rete:
il file può essere letto da un OpenTelemetry Collector con il receiver `otlpjsonfile`.

## Convenzioni esistenti da verificare prima di estendere lo schema

- OpenTelemetry semantic conventions *hardware* (`hw.temperature`, `hw.fan.speed`,
  `hw.power`, `hw.status`, attributi `hw.id`, `hw.type`): possibile mappatura 1:1 dei
  canali canonici in una versione futura dell'export.
- node_exporter `node_hwmon_temp_celsius`, `node_hwmon_fan_rpm`: nomi utili per chi usa
  già Prometheus su Linux.
- Formato dei log di HWiNFO e LibreHardwareMonitor: supportati in import.
