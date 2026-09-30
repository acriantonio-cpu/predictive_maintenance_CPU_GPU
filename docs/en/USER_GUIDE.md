# HWDrift — Step-by-step guide

> English copy of [`docs/GUIDA_UTENTE.md`](../GUIDA_UTENTE.md) (Italian). Both files are kept
> in sync: every change to the tool's behavior updates both (see
> [CONTRIBUTING.md](CONTRIBUTING.md)). Last update: version 0.1.0.dev0.

HWDrift is a **local, cloud-free** monitor of the thermal health and cooling of your CPU and
GPU. It learns how *your* PC behaves when it is healthy (the **baseline**) and warns you when
the thermal path gets worse: dust, dried-out thermal paste, a failing fan or pump, severe
throttling.

It is not an oracle: it **detects drift** from the baseline and proposes maintenance
**hypotheses** with a qualitative confidence. It does not estimate remaining life or failure
probability, and it never touches the hardware (no fan curves, no power limits).

---

## Contents

1. [How it works, in 2 minutes](#1-how-it-works-in-2-minutes)
2. [Requirements](#2-requirements)
3. [Installation](#3-installation)
4. [Try it without hardware (simulator)](#4-try-it-without-hardware-simulator)
5. [First run on your PC (Windows 11)](#5-first-run-on-your-pc-windows-11)
6. [Running in the background](#6-running-in-the-background)
   - [6A. The graphical interface (`hwdrift-gui.exe`)](#6a-the-graphical-interface-hwdrift-guiexe)
   - [6B. Shutdown, restart and sleep](#6b-shutdown-restart-and-sleep)
7. [Reading the report](#7-reading-the-report)
8. [Recording maintenance](#8-recording-maintenance)
9. [Baseline: when to redo it](#9-baseline-when-to-redo-it)
10. [Active health check (optional)](#10-active-health-check-optional)
11. [Exporting data](#11-exporting-data)
12. [Importing HWiNFO logs](#12-importing-hwinfo-logs)
13. [Configuration](#13-configuration)
14. [Troubleshooting](#14-troubleshooting)
15. [Command reference](#15-command-reference)
16. [Glossary](#16-glossary)

---

## 1. How it works, in 2 minutes

```
 sensors ──► COLLECTOR (light, 1 Hz) ──► SQLite ◄── ANALYSIS WORKER (every 15 min)
 LHM, NVML,   data quality, immediate errors         windows, indicators, charts,
 Event Log    (throttling within seconds)            signals, hypotheses, HTML report
                         │                                         │
                         └────────► NOTIFIER (unprivileged) ◄──────┘
                                    Windows toast + persistent status
```

The journey of a data point, step by step:

1. **Collection (collector).** Every second the collector reads temperatures, powers, fans,
   clocks and throttle reasons from LibreHardwareMonitor, NVML (NVIDIA GPU), Windows
   counters and the event log. Each sample gets a **quality flag**: impossible values (0, 255,
   50 °C jumps in one second), out-of-range or **frozen** ones (identical for 15 minutes) are
   marked and excluded from calculations.
2. **Immediate errors.** If the GPU reports thermal throttling, if the CPU slows down under
   load close to its temperature limit (or reaches Tjmax, when the effective clock is not
   available), or if a fan is stopped at high temperature, after a few seconds (debounce) an
   **episode** is created and a toast appears. The statistical analysis is not awaited.
3. **Writing.** Every 60 s the collector writes, in a single transaction, the raw samples
   (kept 48 hours) and the **per-minute medians** (kept forever).
4. **Stationary windows.** The worker looks for 5-minute intervals in which the load is
   stable (power variation < 10%, temperature neither rising nor falling, load started at
   least 3 minutes earlier, no throttling, no configuration change). Health is measured only
   there, so **load is never mistaken for a fault**.
5. **Regimes.** Each window falls in a power regime: *idle*, *medium*, *high*.
6. **Normalized indicators.** For every window:
   - **Rth** = (T − T_ref) / P, the *thermal resistance* in °C/W (degrees per watt): if it
     rises, cooling is getting worse;
   - **fan effort**: rpm at equal power;
   - **GPU Δ hotspot − edge**: chip-to-heatsink contact;
   - **idle temperature** relative to the reference;
   - **throttling share** under load, and WHEA/TDR error counts.
7. **I-MR control charts.** For each indicator and regime, the first days (at least 25
   observations over 5 days and 5 sessions) form **Phase I**: from them the center line and
   the 3σ limits are computed, which then stay **locked** (Phase II). New points are compared
   with those limits using rules R1 (a point beyond 3σ), R2 (9 points on the same side), R3
   (6 points rising), plus EWMA, CUSUM and the Mann-Kendall trend on the daily series.
8. **Alarms.** *Info* = an isolated signal; *Warning* = a signal persisting for 2 consecutive
   days; *Action* = at least two correlated charts at warning level combined by a diagnosis
   rule.
9. **Hypotheses.** Declarative rules (YAML files) map signal combinations to hypotheses:
   dust, paste, fan, environment, power profile, instability. Each hypothesis lists
   supporting signals, contradicting signals and checks ordered from least to most invasive.
10. **Report.** A standalone HTML file, with no scripts and no network, with a traffic light
    per component, charts, events, data coverage and maintenance effectiveness.

| What you see | What it means |
|---|---|
| CPU Rth and fan effort rise together | probably **dust** or blocked airflow |
| CPU Rth rises, fans stable | probably **dried-out paste** or a badly mounted heatsink |
| Rth rises and fans spin less | a failing **fan or pump** |
| Throttling increases without Rth rising | **power limit or profile**, not cooling |
| Everything moves together with the ambient reference | **environment** (season, room): no action |
| Step right after a driver/BIOS update | **confounder**: the chart restarts, no alarm |

---

## 2. Requirements

- **Windows 11** (v1 platform). The core is operating-system independent: on Linux the
  simulator, analysis, report and an experimental collector work.
- **Python 3.11 or 3.12** (3.12 recommended).
- **LibreHardwareMonitor** (recommended) for CPU, motherboard and fan temperatures.
- **NVIDIA** driver for the NVML source (optional: without an NVIDIA GPU the tool works with
  fewer indicators).
- ~80 MB/day of space for raw data (kept 48 hours) and ~1.5 MB/day for the permanent
  aggregates.

---

## 3. Installation

In PowerShell, in the project folder:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
# reproducible installation with pinned dependencies (hashes verified)
pip install --require-hashes -r requirements\dev.lock
pip install --no-deps -e .
# Windows sources (NVML, performance counters, pythonnet for the LHM DLL)
pip install -e ".[windows]"
hwdrift version
```

With **uv** (faster): `uv venv && uv pip install --require-hashes -r requirements\dev.lock && uv pip install --no-deps -e .`

From VS Code: open the folder, accept the recommended extensions (Python, Pylance, Ruff, Even
Better TOML, YAML), select the `.venv` interpreter. Under *Run and Debug* you find the
**Run (simulator)**, **Run (hardware)**, **Simulate 30 giorni**, **Analyze** and **Pytest**
configurations; under *Terminal → Run Task* lint, type check, tests and selftest.

---

## 4. Try it without hardware (simulator)

The quickest way to understand the tool: generate weeks of synthetic data in a few seconds,
with an injected fault. Simulated data **never ends up** in the real database: without `--db`
it goes to `simulate-<scenario>.sqlite` (or `sim-<scenario>.sqlite` for `run --simulate`) in
the data folder.

```powershell
hwdrift simulate --list                         # available scenarios
hwdrift --db demo.sqlite simulate dust --days 30
hwdrift --db demo.sqlite analyze                # windows, charts, hypotheses + report
hwdrift --db demo.sqlite status
start $env:LOCALAPPDATA\HWDrift\report.html     # opens the report
```

In the `dust` scenario dust builds up from day 12: the report shows Rth and fan effort
rising and the hypothesis **"Dust or blocked airflow"** at *Action* level, with the
suggested checks. Also try `paste`, `fan_fail`, `dust_then_clean` (with the *Maintenance
effectiveness* view) and the negative controls `healthy`, `driver_change`, `ambient`,
`power_limit`, which must **not** produce maintenance alarms.

Real-time collector with the simulator (no privileges needed):

```powershell
hwdrift --db live.sqlite run --simulate throttle --fault-after 30
# after ~30 s the simulated fan stops: within seconds the immediate error appears
```

---

## 5. First run on your PC (Windows 11)

### Step 1 — Prepare LibreHardwareMonitor

1. Download LibreHardwareMonitor from the official releases and start it **as administrator**.
2. Menu *Options → Remote Web Server → Run* (default port 8085). HWDrift reads
   `http://127.0.0.1:8085/data.json` and rejects any non-loopback address.
3. Alternatively (`dll` mode) set `sources.lhm.mode: dll` and `dll_path` to
   `LibreHardwareMonitorLib.dll`: in that case HWDrift itself must run as administrator. Beware
   of Memory Integrity and anti-cheat software (see §14).

### Step 2 — Clean the PC (recommended)

The baseline represents the PC's **current** state. If the PC is already dirty, the
degradation ends up in the limits and the tool will not flag it (failure mode 1). If you
can, clean filters and fans before starting and declare it in step 5.

### Step 3 — Create the configuration and check the sensors

```powershell
hwdrift init-config                              # creates an example hwdrift.yaml
hwdrift discover --write-profile profile.yaml    # lists sensors and proposes the mapping
```

`discover` shows, for each source, the sensors found and the proposed **canonical channel**
(e.g. `cpu.pkg.temp_c`, `gpu0.power_w`). Check that at least the following are present:

| Channel | Needed for |
|---|---|
| `cpu.pkg.temp_c`, `cpu.pkg.power_w` | CPU Rth (essential) |
| `gpu0.temp_edge_c`, `gpu0.power_w` | GPU Rth |
| `cpu.fan_rpm` or `chassis.fan1_rpm`, `gpu0.fan_rpm`/`gpu0.fan_pct` | fan effort |
| `gpu0.temp_hotspot_c` | Δ hotspot − edge |
| `ssd0.temp_c` or `mb.temp_c` | T_ref reference (ambient proxy) |
| `cpu.clock_eff_mhz`, `gpu0.throttle_reasons` | throttling |

If a sensor is not mapped or is mapped wrongly, copy the `profile.mapping` section from
`profile.yaml` into `hwdrift.yaml` and fix it (an empty channel `''` excludes the sensor).

### Step 4 — Measure the overhead

```powershell
hwdrift selftest --seconds 60
```

Checks that the collector stays within budget (≤ 1% of one core, ≤ 100 MB) and that all
sources are `ok`. It exits with an error if the budget is exceeded.

### Step 5 — Start collecting and declare the PC's state

```powershell
hwdrift baseline start --state clean   # or --state unknown if you did not clean
hwdrift run                            # in an administrator terminal; Ctrl+C to stop
```

> Prefer a window? After step 3 you can do everything from the GUI: see section 6A.

### Step 6 — Use the PC normally for at least 5 days (and a month for the daily charts)

Phase I closes by itself when every chart has at least 25 observations, over 5 different days
and 5 sessions. Before that the charts are **provisional** and the report says "baseline
under construction": the absence of signals does **not** mean good health. The **daily**
charts (day median, with sequence rules, EWMA, CUSUM and trend) need 25 complete days: in the
first month drift shows up on the per-window charts. Rarely used regimes (e.g. high load on an
office PC) may stay without a chart: the report states it as **insufficient coverage**; see
§10 for a remedy.

### Step 7 — Analyze and read the report

```powershell
hwdrift analyze        # also regenerates %LOCALAPPDATA%\HWDrift\report.html
```

---

## 6. Running in the background

Three scheduled tasks (Task Scheduler):

| Task | When | Privileges |
|---|---|---|
| `HWDrift\Collector` → `hwdrift run` | at logon | elevated (low-level sensors) |
| `HWDrift\Analyze` → `hwdrift analyze` | every 15 minutes | normal, BELOW_NORMAL priority |
| `HWDrift\Notify` → `hwdrift notify` | at logon | normal (user session, read-only database) |

```powershell
hwdrift schedule install            # shows what it would do (dry run)
hwdrift schedule install --apply    # creates them (PowerShell as administrator)
hwdrift schedule remove --apply
```

The collector records **gaps** (sleep, hibernation, shutdown) and **reboots** by itself; the
notifier warns if the collector has been stopped for more than 5 minutes while the PC is on.
In **game-safe** mode (anti-cheat processes in the list) low-level sources are suspended and
NVML and the Event Log remain.

---

## 6A. The graphical interface (`hwdrift-gui.exe`)

A single window to see what is happening **in real time**, read the status, manage the
configuration and save logs and data. It does not read the sensors: it shows what the
collector publishes, so the collector must be running (the window can start it).

**How to get it.**
- *Executable*: the GitHub "Build exe" pipeline (`.github/workflows/build-exe.yml`) produces
  `hwdrift-gui.exe` as an artifact (and in releases, with a SHA-256 hash and a Sigstore
  signature). Locally, on Windows: `pwsh packaging\build_exe.ps1` → `dist\hwdrift-gui.exe`.
  The executable is **not signed with a Windows certificate**: on first launch SmartScreen
  may show "Windows protected your PC" → *More info* → *Run anyway* (verify the hash first).
- *From source*: `hwdrift-gui` (installed with the package) or `python -m hwdrift.gui`. It
  needs Tk, included in the Windows Python installer.

The executable is also the CLI: `hwdrift-gui.exe run`, `hwdrift-gui.exe analyze`, ... work the
same (and `hwdrift schedule install` registers exactly that executable).
Options: `--config file.yaml`, `--db file.sqlite`.

**Language.** The interface, the reports, the alarms and the hypotheses are in **English** by
default. Italian is available: set `language: it` in `hwdrift.yaml`, use the *Language* field in
the *Configuration* tab (applies when the window is restarted), or set the environment variable
`HWDRIFT_LANGUAGE=it` (it takes precedence over the file). Command-line help and log messages
stay in Italian.

**Tabs.**

| Tab | What it offers |
|---|---|
| **Real time** | six big values (temperatures, powers, fans) and eight charts scrolling every second: CPU and GPU temperature, powers, fans, load, clock, throttling. Window from 5 to 60 minutes. A red warning if a throttling episode or a stopped fan is in progress. On opening, the charts fill with recent history from the database |
| **Status and hypotheses** | the traffic light for CPU, GPU, cooling and drives; active alarms; hypotheses with supporting/contradicting signals and checks. Buttons **Analyze now** (in the background, regenerates the report) and **Open the HTML report** |
| **Control charts** | pick a chart and see the I chart and the moving-range chart with limits, Phase I, signals (triangles) and maintenance |
| **Events and maintenance** | list of events and a form to record cleanings, re-pastes, fan changes, profiles |
| **Configuration** | a form with the main settings (language, interval, sources, reference, limits, regimes, notifications, game-safe) and, in the *Advanced YAML* tab, the full file. Every save is **validated**: an invalid configuration never replaces the good one, and a `.bak` copy remains. Comments in the file are lost when saving from the form |
| **Log and data** | live log; **Save log…**, **Diagnostic bundle (.zip)** (log, status, configuration, versions; *not* the database), **Save HTML report…**, **Export data** (CSV, JSONL, Parquet, Prometheus, OTLP; anonymous by default), **Open data folder** |

**Top bar.**
- **▶ Start collector**: starts it without elevated privileges (some low-level sensors may be
  missing; LibreHardwareMonitor in web mode does not need them).
- **▶ Start as administrator** (Windows): UAC prompt; the elevated collector sees all sensors.
- **■ Stop**: clean stop (writes pending data). It also works for a collector already running
  as a scheduled task.
- **Demo (simulated data)**: 30 simulated days with dust build-up plus a simulated real-time
  collector, in a separate folder (`demo`). It does not touch the real database; it is meant
  to show what the tool looks like. A red banner reminds you that the data is fake. The demo
  restarts from fresh data every time.

How real time works: the window updates the `live.active` file every 2 seconds; while it is
recent the collector writes the values to `live.json` every second (a few KB). When the window
is closed the collector stops writing it. On closing, the GUI asks whether to stop the
collector it started.

**Mind the configuration and privileges.** The GUI writes `hwdrift.yaml` in your data folder,
which your user can modify. An **elevated** collector must not read a configuration that a
non-administrator user can modify (see `SECURITY.md`): if you use one, keep a copy of the file
in a protected folder and pass it with `--config`.

---

## 6B. Shutdown, restart and sleep

Turning the PC off and on again **is not a problem**: the tool handles and records it, does not
mistake it for a fault, and does not lose the baseline. In detail:

| Situation | What happens |
|---|---|
| **Normal shutdown or reboot** | the collector stops; the last minute or so of raw data may be lost (writing happens every 60 s). The database (SQLite WAL) stays intact even if power is cut |
| **Power-on** | the collector restarts **at Windows logon** (not at boot): between power-on and logon there is no data. At start it records a `system.collector_start` event, a `system.gap` (interval without data) and, if the Windows boot time changed, a `system.reboot` |
| **Episode in progress at shutdown** (e.g. throttling) | at the next start it is closed at the last instant the collector was alive: it does not stay "in progress" forever |
| **Control charts** | windows containing a gap, a reboot or a collector start are discarded; baseline and limits do **not** change. No maintenance alarm for a shutdown |
| **Sleep / hibernation** | on resume the collector detects the clock jump, records the gap and closes open episodes |
| **Windows 11 Fast Startup** | the "hybrid" shutdown may not change the boot time, so the `system.reboot` may be missing; the **gap** is still recorded by the heartbeat |
| **Forced shutdown** (power button, mains) | Windows logs Kernel-Power 41: HWDrift counts it in the `unexpected_shutdown` indicator (c chart). A normal shutdown does not produce it |
| **Laptop on battery** | the tasks created by `hwdrift schedule install` also start on battery, have no 72-hour Windows limit and restart if they end |

For a clean stop use **■ Stop** in the GUI or `Ctrl+C` in the terminal: it also writes pending
data. Known limit: these behaviors are verified with simulated-clock tests (abrupt shutdown,
reboot, sleep), **not yet on a Windows PC** (see `docs/en/AUDIT.md`, R1).

---

## 7. Reading the report

The report (`%LOCALAPPDATA%\HWDrift\report.html`) opens offline, also with keyboard and screen
reader. Sections:

1. **Overall status** — a traffic light for CPU, GPU, cooling and drives, with a sentence
   explaining why. States: *OK*, *Warning*, *Action*, *Insufficient data* (written in words,
   not only in colors).
2. **Immediate errors** — severe throttling or stopped-fan episodes: time, duration,
   component, reason, severity; "ongoing episode" if not finished.
3. **Maintenance hypotheses** — active hypotheses with confidence (low/medium/high),
   supporting and contradicting signals, checks ordered from least invasive.
4. **Alarms** — all active alarms with their level.
5. **Control charts** — the table of each chart's state (Phase I/II, provisional/final,
   observations, autocorrelation); then the main charts (simple mode) and all the others in
   *Advanced mode*. In every chart:
   - points = observations; shaded area = Phase I;
   - dotted line = center line; solid = 3σ limits; dashed = 2σ;
   - **triangles** = signals (the rule is in the tooltip and in the *Signals* list);
   - vertical lines = events (green = maintenance, orange = configuration);
   - below, the **MR chart** (moving ranges: sudden jumps);
   - *Data table* = text equivalent of the chart.
6. **Events** — maintenance, driver/BIOS changes, reboots, gaps.
7. **Coverage and data quality** — valid windows per regime and week; minutes with excluded
   samples per channel; last data received.
8. **Maintenance effectiveness** — after a declared cleaning, by how many σ the indicator went
   back toward the baseline ("recovered", "improved", "not improved").
9. **Overhead** — the collector's CPU and RAM over the last 24 hours against the budget.

**Alarm levels.** *Info*: worth watching, no notifications. *Warning*: persistent signal, a
toast appears. *Action*: hypothesis supported by several indicators, a toast appears; follow
the suggested checks in order.

**Warnings.** This is not a safety warning or a fault diagnosis. Opening the PC may void the
warranty; on laptops follow the manufacturer's procedures. In case of high temperatures or
shutdowns, do not wait for the tool: act.

---

## 8. Recording maintenance

Every intervention should be recorded: it closes the charts' segment, starts a new Phase I and
feeds the "maintenance effectiveness" view.

```powershell
hwdrift event kinds                                            # available types
hwdrift event add maintenance.clean --note "filters and fans"
hwdrift event add maintenance.repaste --at "2026-09-28 18:30"
hwdrift event add config.profile --note "silent fan profile"
hwdrift event list --days 60
```

If an indicator suddenly drops with no recorded event, the tool asks "Did you do
maintenance?" and suggests recording it. GPU driver and BIOS changes are detected and
recorded automatically.

---

## 9. Baseline: when to redo it

```powershell
hwdrift baseline status                     # state of each chart
hwdrift baseline start --state clean        # new Phase I for all charts
hwdrift baseline start --component gpu      # only the GPU charts
hwdrift baseline start --chart "rth_cpu|high|daily"
hwdrift baseline lock                       # closes Phase I now (provisional, wider limits)
hwdrift analyze --rebuild                   # recomputes everything from the aggregates (new regimes)
```

Redo the baseline after: maintenance (automatic if recorded), a hardware change or moving the
PC, an intended fan-profile change. **Do not** redo it to "make an alarm go away": the locked
limits exist precisely so as not to absorb the drift.

---

## 10. Active health check (optional)

If you never use the PC at full load, the "high" regime stays without a chart. The health check
applies, **only on your request**, a short, repeatable CPU load, with automatic interruption if
the temperature exceeds the threshold (default 90 °C), if throttling appears or if data stops
arriving.

```powershell
hwdrift run                              # the collector must be running
hwdrift healthcheck --yes                # 5 minutes of load (config: healthcheck.duration_s)
```

Repeat it every week under the same conditions to get comparable windows.

---

## 11. Exporting data

```powershell
hwdrift export --format csv     --out export\          # anonymous by default
hwdrift export --format jsonl   --out export\          # conforms to the schemas in schemas/
hwdrift export --format parquet --out export\          # requires: pip install -e ".[parquet]"
hwdrift export --format prometheus --out hwdrift.prom  # node_exporter textfile collector
hwdrift export --format otlp    --out hwdrift-otlp.json
hwdrift export --no-anonymize --format csv --out private\   # includes free-text notes
```

The anonymous export contains only canonical channels and numeric values: no process names,
user names, paths, raw sensor names or notes. The machine ID is random and generated locally,
not derived from the hardware.

---

## 12. Importing HWiNFO logs

```powershell
hwdrift import-hwinfo C:\log\hwinfo.csv            # local time zone
hwdrift import-hwinfo C:\log\hwinfo.csv --tz-offset 1
hwdrift analyze
```

Columns are mapped with rules on their names (in English; for other names add the key
`"Column name [unit]": channel` to `profile.mapping`).

---

## 13. Configuration

The `hwdrift.yaml` file (current folder or `%LOCALAPPDATA%\HWDrift\`) overrides the defaults key
by key; an unknown key is an explicit error. The most useful keys (full example in
[`hwdrift.example.yaml`](../../hwdrift.example.yaml)):

| Key | Default | What it does |
|---|---|---|
| `language` | `en` | `en` or `it`: interface, reports, alarms, hypotheses, notifications |
| `sampling.interval_s` | 1.0 | sampling interval (0.5–5 s) |
| `sources.lhm.mode` | `web` | `web` (LHM server) or `dll` (pythonnet) |
| `profile.reference.mode` | `channel` | T_ref: `channel` (proxy, e.g. `ssd0.temp_c`), `user` (fixed value), `none` |
| `profile.cpu.tjmax_c` | 100 | CPU thermal limit for immediate errors |
| `regimes.mode` | `fixed` | `fixed` (30%/65% of max power) or `adaptive` (terciles) |
| `spc.phase1_min_days` | 5 | minimum Phase I days |
| `alerts.action_budget_per_month` | 2 | beyond that, no "action" notifications: review the thresholds |
| `game_safe.processes` | common anti-cheat | processes that suspend low-level sources |

Environment variables: `HWDRIFT_HOME` (data folder), `HWDRIFT_CONFIG` (configuration file),
`HWDRIFT_LANGUAGE` (`en` or `it`, overrides the file).

---

## 14. Troubleshooting

| Problem | Solution |
|---|---|
| `lhm non disponibile: server web ... non raggiungibile` (LHM unavailable: web server unreachable) | Start LHM as administrator and enable *Remote Web Server* |
| No CPU sensors with `mode: dll` | Start the terminal as administrator; check Memory Integrity (Windows Security → Core isolation) and the antivirus |
| Stutter in games or conflicts with anti-cheat | Add the process to `game_safe.processes`; use `mode: web` |
| Report: "Baseline under construction" after days | Check the *Coverage* section: the regime is not visited → health check |
| Report: "Data not up to date" | The collector is stopped: `hwdrift status`, check the scheduled task |
| A source is missing from the indicators | `hwdrift status` and the report's *Data sources* section show which sources did not start and why |
| `Rifiutato: con privilegi elevati la configurazione va indicata esplicitamente` (Refused: with elevated privileges the configuration must be given explicitly) | With the administrator terminal pass the file with `--config` (security measure) |
| The GUI shows "Waiting for the collector…" | The collector is not running: use **▶ Start collector** or check the scheduled task |
| The GUI does not open from source (`No module named tkinter`) | Reinstall Python including *tcl/tk and IDLE* (Windows installer) or, on Linux, `python3-tk` |
| Toasts not visible | Focus Assist or a full-screen game: the status remains in the report and in `status.json` |
| Too many alarms | The monthly budget suspends them; review `spc`/`alerts` and the rules in `diagnosis/rules/default.yaml` |
| `Errore di configurazione: chiave sconosciuta` (Configuration error: unknown key) | Typo in `hwdrift.yaml`: the message names the key |

Log: `%LOCALAPPDATA%\HWDrift\hwdrift.log` (2 MB rotation). Add `-v` to any command for detail.
Command-line messages and log lines are in Italian.

---

## 15. Command reference

| Command | Function |
|---|---|
| `hwdrift discover` | lists the sensors and proposes the mapping to canonical channels |
| `hwdrift run` | starts the resident collector (`--simulate` for the simulator) |
| `hwdrift analyze` | analysis worker: windows, indicators, charts, signals, hypotheses, report |
| `hwdrift baseline start / lock / status` | Phase I management |
| `hwdrift event add / list / kinds` | log of maintenance and events |
| `hwdrift report` | generates the HTML report |
| `hwdrift export` | CSV, JSONL, Parquet, Prometheus, OTLP (anonymous by default) |
| `hwdrift import-hwinfo` | imports a HWiNFO CSV log |
| `hwdrift selftest` | measures the overhead and the collectors' state |
| `hwdrift healthcheck --yes` | short load with a safety cut-off (optional) |
| `hwdrift simulate` | offline synthetic data (fault scenarios) |
| `hwdrift notify` | unprivileged notifier |
| `hwdrift status` | collector, ongoing episodes, active alarms |
| `hwdrift schedule install / remove` | Windows scheduled tasks |
| `hwdrift init-config` | creates an example `hwdrift.yaml` (in the configured language) |
| `hwdrift-gui` / `hwdrift-gui.exe` | graphical interface (with a command from the table it works like the CLI) |

Global options: `--config FILE`, `--db FILE`, `-v`.

---

## 16. Glossary

- **Baseline / Phase I**: period in which the PC is considered healthy and from which the
  limits are computed. **Phase II**: monitoring with locked limits.
- **Rth**: thermal resistance, (T − T_ref)/P in °C/W.
- **T_ref**: reference temperature (ambient or its internal proxy).
- **Stationary window**: 5 minutes of stable load in which indicators are comparable.
- **Regime**: power band (idle, medium, high).
- **I-MR chart**: individuals and moving-range chart; limits at ±3σ with σ = MR̄/1.128.
- **Long-term σ**: sample standard deviation, used for the per-window (autocorrelated) charts.
- **EWMA, CUSUM, Mann-Kendall**: methods sensitive to slow drift, on the daily series.
- **Throttling**: clock reduction because of a thermal or power limit.
- **WHEA**: hardware errors logged by Windows; **TDR**: video driver reset.
- **Insufficient coverage**: too few observations for a chart; it does not mean the component
  is healthy.

For the statistical details see [methodology.md](methodology.md); for validation
[validation_protocol.md](validation_protocol.md).
