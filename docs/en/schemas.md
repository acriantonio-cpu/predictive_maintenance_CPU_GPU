# Open HWDrift schema (v1.0)

> English copy of [`schemas/README.md`](../../schemas/README.md) (Italian); keep them in sync.

JSON Schemas (draft 2020-12) for hardware-condition telemetry and maintenance events.
`hwdrift export --format jsonl` produces one file per type, one record per line, conforming to
these schemas; CI validates them.

| File | Contents |
|---|---|
| `sample.schema.json` | 1-minute aggregate of a canonical channel (`cpu.pkg.temp_c`, ...) |
| `indicator.schema.json` | health indicator per window or daily |
| `event.schema.json` | maintenance, configuration changes, gaps, hardware errors |
| `chart_state.schema.json` | limits and phase of a chart segment |
| `signal.schema.json` | a chart signal (rule, side, label) |

Conventions: UTC timestamps in integer milliseconds; lowercase channel names separated by dots;
random local `machine_id`. Before extending the schema, check the existing conventions
(OpenTelemetry semantic conventions for `hw.*`, Prometheus metric names of node_exporter
`node_hwmon_*`) and reuse them where possible: see [interoperability.md](interoperability.md).
