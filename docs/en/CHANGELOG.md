# Changelog

> English copy of [`CHANGELOG.md`](../../CHANGELOG.md) (Italian); keep them in sync.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); semantic versioning.

## [Unreleased] — 0.1.0.dev0

### Added
- English localization: GUI, HTML report, alarms, diagnosis hypotheses, notifications and event
  descriptions are in English by default; Italian stays available (`language: it`,
  `HWDRIFT_LANGUAGE`, or the GUI's Configuration tab). Translation catalog with a test that
  fails on missing entries. Complete English copy of the documentation in `docs/en/`.
- `hwdrift-gui` graphical interface (tkinter, no new dependency): real-time charts, status and
  hypotheses, control charts, events and maintenance, configuration (form + validated YAML), log,
  diagnostic bundle, export; start/stop of the collector, also elevated (UAC), and demo mode.
  Executable with PyInstaller (`packaging/`, workflow `build-exe.yml`); the same executable
  accepts CLI commands.
- The collector publishes `live.json` only while a GUI is open (`live.active`) and stops with
  `stop.request`.
- Reboot/shutdown: episodes left "in progress" are closed at start; scheduled tasks use an XML
  without the 72-hour limit and without the battery block.
- M1: `Collector` interface, `Sample`, canonical channels and auto-discovery; LibreHardwareMonitor
  collector (web server on loopback or DLL with pythonnet), NVML, event log (`wevtutil`),
  performance counters, psutil, system information (driver/BIOS as events), smartmontools, HWiNFO
  CSV importer, simulator, experimental Linux collector.
- SQLite WAL storage with versioned schema, batch writes, 1-minute aggregates, 48-hour raw
  retention.
- Data-quality layer (physical ranges, glitches, impossible jumps, frozen values), watchdog with
  heartbeat and status channels, gaps on sleep/reboot, game-safe mode, self-monitoring and adaptive
  interval.
- Immediate-error detector (CPU/GPU thermal throttling, power limit, stopped fan) with debounce and
  severity; unprivileged notifier with toast and `status.json`.
- M2: stationary windows, regimes (fixed/adaptive), Rth, fan effort, Δ hotspot-edge, idle drift,
  case delta, throttling share, WHEA/TDR/PCIe replay counts; robust baseline models (Huber) with
  and without fan, continuous model; coverage per regime; active health check with safety cut-off.
- M3: I-MR charts (σ from MR, robust, long-term), rules R1–R4 and MR, EWMA, CUSUM, c/u charts,
  Mann-Kendall, autocorrelation and normality checks, Phase I with provisional limits and closure at
  the first prefix that meets the criteria.
- M4: alarm policy (info/warning/action, primary and secondary, monthly budget, "configuration"
  label), segments closed by maintenance and configuration changes, semi-automatic detection of
  cleanings, YAML diagnosis rules, complete CLI.
- M5 (partial): standalone accessible HTML report, scheduled tasks, overhead selftest,
  CSV/JSONL/Parquet/Prometheus/OTLP export with a versioned open schema.
- Code audit ([docs/en/AUDIT.md](AUDIT.md)): 21 fixes, among them simulation never in the real
  database, `status` not consuming notifications, CPU throttling without effective clock, grace
  period for "collector stopped", complete days only in the daily charts, visible source status,
  parser fuzzing.
- Documentation: step-by-step guide, methodology, validation protocol, sensor matrix, threat model,
  security, governance, AI use.
