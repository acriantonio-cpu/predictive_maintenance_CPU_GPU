# HWDrift

> English version of [`README.md`](README.md) (Italian). The full English documentation is in
> [`docs/en/`](docs/en/).

**Local predictive maintenance for PCs: CPU and GPU thermal drift with control charts.**

HWDrift builds your PC's individual baseline and detects, with I-MR control charts on
load-normalized indicators, the drift of the thermal path (dust, thermal paste, fan, pump) and
severe throttling. Everything is local: no cloud, no account, no network connection by default.

- It detects drift from the baseline; it does **not** estimate remaining life or failure probability.
- It proposes maintenance **hypotheses** with a qualitative confidence and checks ordered from
  least to most invasive.
- It reports severe throttling and stopped fans **immediately** (within seconds).
- It never modifies the hardware (fan curves, power limits).

> **Step-by-step guide (how it works and how to start it): [docs/en/USER_GUIDE.md](docs/en/USER_GUIDE.md)**
>
> **Graphical interface** (`hwdrift-gui.exe`): real-time charts, status, control charts, events,
> configuration and saving of logs and data — see section 6A of the guide. The interface, reports
> and alarms are in **English** by default (`language: it` for Italian).

## Quick start

```powershell
py -3.12 -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install --require-hashes -r requirements\dev.lock
pip install --no-deps -e .

# try without hardware: 30 simulated days with dust build-up
hwdrift --db demo.sqlite simulate dust --days 30
hwdrift --db demo.sqlite analyze          # also generates the HTML report
hwdrift --db demo.sqlite status

# on your PC (Windows 11, LibreHardwareMonitor with Remote Web Server enabled)
hwdrift discover                          # sensors found and proposed mapping
hwdrift baseline start --state clean      # if you have just cleaned the PC
hwdrift run                               # collector (administrator terminal)
hwdrift analyze                           # now and then, or as a scheduled task
hwdrift schedule install --apply          # run in the background
hwdrift-gui                               # the window (or hwdrift-gui.exe)
```

## Architecture

Two processes and a database: a light **collector** (no numpy, ≤ 1% of one core) writes to
SQLite; a low-priority **analysis worker** computes stationary windows, indicators, charts and
hypotheses and regenerates the report; an unprivileged **notifier** reads the database read-only
and shows the toasts.

```
src/hwdrift/
├── collectors/   lhm, nvml, eventlog, perfcounters, psutil, wmi_info, smart,
│                 hwinfo_csv, simulator, linux_hwmon (experimental)
├── channels.py   canonical channels and sensor mapping
├── storage/      versioned schema, batch writer, export
├── quality/      data quality, watchdog, immediate errors
├── context/      regimes, stationary windows, events
├── indicators/   Rth, fan effort, hotspot, baseline and residuals, coverage
├── spc/          I-MR, rules, EWMA, CUSUM, c/u charts, Mann-Kendall, assumptions
├── analysis/     worker and chart management (Phase I/II, segments)
├── diagnosis/    engine and YAML rules
├── alerts/       alarm policy, toast, notifier
├── reporting/    accessible HTML report (SVG, no script)
├── sim/          synthetic thermal model and fault scenarios
├── gui/          graphical interface (tkinter): data.py (testable without Tk), widgets, app
├── i18n.py, i18n_en.py   localization (English default, Italian available)
├── healthcheck.py, selftest.py, runner.py, cli.py
packaging/        PyInstaller (hwdrift-gui.spec, build_exe.ps1) · .github/workflows/build-exe.yml
```

## Documentation

| Document | Contents |
|---|---|
| [docs/en/USER_GUIDE.md](docs/en/USER_GUIDE.md) | how it works and how to start it, step by step |
| [docs/en/methodology.md](docs/en/methodology.md) | indicators, windows, regimes, SPC, diagnosis, design choices |
| [docs/en/validation_protocol.md](docs/en/validation_protocol.md) | phases 0–5 and current status |
| [docs/en/sensor_matrix.md](docs/en/sensor_matrix.md) | sources, channels, availability to fill in during M0 |
| [docs/en/interoperability.md](docs/en/interoperability.md) | open schema, Prometheus, OpenTelemetry |
| [docs/en/AUDIT.md](docs/en/AUDIT.md) | code audit and status of the fixes |
| [schemas/](schemas/) ([docs/en/schemas.md](docs/en/schemas.md)) | JSON Schemas of samples, indicators, events, charts, signals |
| [docs/en/SECURITY.md](docs/en/SECURITY.md), [docs/en/THREAT_MODEL.md](docs/en/THREAT_MODEL.md) | security and threat model |
| [docs/en/CONTRIBUTING.md](docs/en/CONTRIBUTING.md), [docs/en/GOVERNANCE.md](docs/en/GOVERNANCE.md), [docs/en/AI_USAGE.md](docs/en/AI_USAGE.md), [docs/en/CODE_OF_CONDUCT.md](docs/en/CODE_OF_CONDUCT.md), [docs/en/CHANGELOG.md](docs/en/CHANGELOG.md) | contributions, governance, AI use, code of conduct, changelog |

## Development

```powershell
ruff check src tests      # lint
pyright                   # type check
pytest                    # tests (hardware-marked ones excluded; GUI tests need a display)
pytest -m "not slow"      # fast tests only
hwdrift selftest          # collector overhead
```

M0 spike script (24 hours of real-sensor sampling):
`python scripts/m0_spike.py --hours 24 --out m0-%COMPUTERNAME%`.

## License

Apache-2.0 (see [LICENSE](LICENSE)). LibreHardwareMonitor is MPL-2.0 and is an optional external
dependency, not redistributed; smartmontools is used as an external executable, not linked.
