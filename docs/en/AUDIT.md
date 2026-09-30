# Code audit — HWDrift 0.1.0.dev0

> English copy of [`docs/AUDIT.md`](../AUDIT.md) (Italian); keep them in sync.

Date: 30 September 2026. Scope: all the code in `src/hwdrift`, tests, CI workflows, configuration
and documentation, against the specification "HWDrift — Project specification and implementation
plan". Verification environment: Linux, Python 3.11 and 3.12 (lock installed in a clean
environment), simulator; **no real Windows hardware**.

## 1. Method

1. Adversarial re-reading of the critical modules (resident collector, writer, real-time detector,
   chart engine, alarm policy, notifier, CLI, parsers).
2. Automatic checks: `ruff` (rules E, F, W, I, B, UP, SIM, S = bandit, RUF), `pyright` in standard
   mode, targeted search for `subprocess`, composed SQL, `yaml.load`, `eval`, network.
3. Tests: 176 tests (unit with hand-computed values, property-based with hypothesis, **parser
   fuzzing**, runner integration with a simulated clock, 12 fault scenarios from collection to
   diagnosis, CLI).
4. Visual review of the HTML report (Chromium, light and dark theme).
5. Measurement of the overhead against the budget of section 2.

## 2. Summary of results

| Area | Status |
|---|---|
| Lint / type check | `ruff check`: 0 problems · `pyright`: 0 errors |
| Tests | 176 green; coverage 88% (the Windows sources are covered with fake `pynvml`, an LHM server on loopback, fake sysfs and smartctl) |
| Module boundaries | verified by tests: the core does not import Windows modules; the collector does not load numpy/scipy; `spc/` is pure |
| Collector overhead | 0.1% of one core, 23 MB peak (budget: 1%, 100 MB) — simulator, 30 s |
| Worker overhead | 45 days in 9 s and 111 MB peak on the first analysis; 1 s on incremental analyses (budget: 30 s, 300 MB) |
| Disk | ~0.9 MB/day of 1-minute aggregates with 18 channels (specification estimate: 1.5 MB/day) |
| Negative controls (simulator) | healthy, driver change, environment, power limit: no maintenance alarm |
| Faults (simulator) | dust, paste, fan: correct hypothesis, action level, ranked first |

## 3. Problems found and fixed

| # | Severity | Problem | Fix | Regression test |
|---|---|---|---|---|
| A1 | **High** | `hwdrift run --simulate` and `hwdrift simulate` without `--db` wrote synthetic data into the machine's real database (baseline contaminated forever) | without `--db` the simulation uses `sim-<scenario>.sqlite` / `simulate-<scenario>.sqlite` | `test_simulation_never_touches_real_database` |
| A2 | **High** | `hwdrift status` called the notifier in normal mode: it marked episodes and alarms as "already notified", suppressing the real toasts | `Notifier.check(persist=False)`: no notification, no state writing | `test_status_does_not_consume_notifications` |
| A3 | **High** | With LibreHardwareMonitor only (no effective clock) CPU thermal throttling was never detected in real time | CPU at Tjmax − 1 °C under load = thermal throttling | `test_cpu_at_tjmax_without_clock_data` |
| A4 | Medium | At every logon the notifier warned "collector stopped" (heartbeat of the previous session) | grace period after PC and notifier start | `test_stale_grace_after_login` |
| A5 | Medium | The current day's (partial) daily medians entered the charts: a signal on a value that later changed stayed recorded | daily indicators only for complete days | `test_daily_indicators_only_for_complete_days` |
| A6 | Medium | A source that never started (e.g. LHM not running) left no trace: no indicator, no warning | source status saved at every flush, shown in the report and in `hwdrift status` | `test_unavailable_source_is_recorded` |
| A7 | Medium | Plausibility threshold of 25 °C/s: real CPU package spikes at load start would have been marked as glitches | 50 °C/s | `test_impossible_jump_is_glitch_and_does_not_poison_reference` |
| A8 | Medium | Elevated collector with `hwdrift.yaml` taken from the current folder: an untrusted file can change the external executables (THREAT_MODEL T1) | with elevated privileges the configuration from the current folder is refused without an explicit `--config` | `test_elevated_collector_refuses_cwd_config` |
| A9 | Medium | A chart's segment was closed by a maintenance **before** its Phase I was computed when the analysis caught up several days at once: empty previous baseline, empty "effectiveness" view | the segment is processed with the data up to the closure, then archived | `test_cleaning_closes_segment_and_shows_recovery` |
| A10 | Medium | In "bulk" analysis the provisional Phase I signals were not computed (different from incremental operation) | same evaluation on both paths | `test_throttling_feeds_throttle_indicator_not_rth` |
| A11 | Medium | Constant series in Phase I (e.g. throttling always zero) gave degenerate charts with no limits: later throttling was not flagged | minimum σ per indicator also in the provisional limits | same test |
| A12 | Medium | **False alarms from autocorrelation**: with σ = MR̄/d₂ on the per-window series the healthy case produced tens of thousands of signals and a false "action" | long-term σ and R1 only on the per-window charts; sequence rules, EWMA, CUSUM, MK on the daily ones (see methodology §5) | `test_negative_controls_no_maintenance_alarm` |
| A13 | Medium | "Environment" negative control: a colder room produces the same signature as a degraded fan | falling `ref_temp` is a blocking contradiction for `fan_failure` | `test_negative_controls_no_maintenance_alarm[ambient]` |
| A14 | Low | Fuzzing: a lone `\r` in the HWiNFO CSV raised an unhandled `csv.Error` | error turned into a `ValueError` with the line number | `test_hwinfo_rejects_non_hwinfo_text` |
| A15 | Low | Non-anonymous CSV export: the `note` column vanished if the first event had no notes | fixed columns per record type | `test_csv_non_anonymous_keeps_note_column` |
| A16 | Low | `import-hwinfo` could overwrite minutes already recorded by the collector | `INSERT OR IGNORE` for imports | `test_import_does_not_overwrite_collector_data` |
| A17 | Low | Arbitrary channel names in the mapping (e.g. `CPU Package`) entered the database and violated the export schema | validation in the configuration | `test_invalid` |
| A18 | Low | A slow read (PowerShell, `wevtutil`) could be mistaken for a sleep (false gap that invalidates windows) | 90 s threshold, external process timeouts ≤ 15–30 s | `test_suspend_produces_gap_event` |
| A19 | Low | Notifier state without pruning (unbounded file growth) | only the last 7 days of episodes and the active alarms are kept | `test_notifier_dedup_escalation_and_readonly` |
| A20 | Low | `notify-send`: a title starting with `-` could be read as an option | `--` separator | review |
| A21 | Low | `schedule` command with `python -m hwdrift` fallback badly quoted for `/TR` | separate quoting of executable and arguments | review (TODO verify on Windows) |

## 4. Residual risks and recommendations (not fixed in this round)

| # | Priority | Risk | Recommendation |
|---|---|---|---|
| R1 | **High** | No test on Windows hardware: LHM/HWiNFO sensor names, event-log IDs, NVML bits, PDH counters, toasts and `schtasks` are verified only with fakes (`TODO(M0)` in the code) | run `scripts/m0_spike.py` on 2–3 machines and `pytest -m hardware`; fill in `docs/en/sensor_matrix.md` |
| R2 | High | Elevated collector importing code from a venv writable by the user = code execution as administrator | install in `C:\Program Files\HWDrift` (SECURITY.md); consider a signed service in v2 |
| R3 | Medium | The daily charts (with R2/R3/EWMA/CUSUM/MK) close Phase I after 25 complete days: in the first month slow drift shows only on the per-window charts (R1) | evaluate in Phase 0 a daily Phase I of 20 days or weekly charts |
| R4 | Medium | An internal T_ref proxy (SSD) gets contaminated by dust | USB ambient sensor or user value (`reference.mode: user`) where possible |
| R5 | Medium | Diagnosis thresholds and rules calibrated only on the simulator (physical assumptions documented in methodology §7) | Phases 0–3 of the protocol; review `default.yaml` with real data |
| R6 | Medium | Frozen-value detection has a 15-minute latency | accepted; documented |
| R7 | Low | Collector restart within the same minute: that minute's aggregate is replaced by the partial one | accepted (loss ≤ 1 minute) |
| R8 | Low | `import-hwinfo` loads the whole file in memory | streaming if multi-GB logs are needed |
| R9 | Low | A forced stop of the collector (end of scheduled task) loses up to 60 s of data | accepted; the gap is recorded at restart |
| R10 | Low | Data folders have no dedicated ACLs (THREAT_MODEL T10) | set the ACLs at installation time (M5) |

## 5. Conformance to the specification (summary)

| Requirement | Status |
|---|---|
| Two processes, collector without scientific libraries | ✔ verified by tests |
| Sources LHM, NVML, Event Log, counters, SMART, WMI, psutil, HWiNFO CSV, simulator | ✔ implemented; to verify on hardware (R1) |
| Data quality, watchdog, immediate errors with debounce and severity | ✔ |
| SQLite WAL, versioned schema, 60 s batch, 48 h retention | ✔ |
| Stationary windows, fixed/adaptive regimes, throttling exclusion | ✔ |
| Indicators, baseline residuals, continuous model, coverage | ✔ |
| I-MR, EWMA, CUSUM, c/u, R1–R4, assumptions, Mann-Kendall, Phase I/II, provisional limits | ✔ (long-term σ for the per-window charts: motivated departure) |
| Alarm policy, budget, ±24 h configuration, semi-automatic cleaning | ✔ |
| YAML diagnosis with supports and contradictions | ✔ |
| Complete CLI, accessible report, anonymous export, open schema, Prometheus/OTLP | ✔ (SVG instead of Plotly: motivated departure) |
| Health check with safety cut-off, overhead selftest | ✔ |
| Governance, security, AI documents, Windows CI, hashed locks, SBOM, signing | ✔ (workflows to be run on GitHub) |
| Validation Phases 0–5 | ⏳ only consistency checks on the simulator |

---

## 6. Addendum — PC restart and graphical interface

Request: verify what happens when switching the PC off and on again, and add a GUI.

### 6.1 Problems found and fixed

| # | Severity | Problem | Fix | Regression test |
|---|---|---|---|---|
| A22 | **High** | A shutdown during a throttling episode left the episode "in progress" forever (report and status kept showing a non-existent emergency) | at collector start the open episodes are closed at the last known heartbeat | `test_reboot_closes_orphan_episodes_and_records_gap_and_reboot` |
| A23 | **High** (laptops) | `schtasks /Create` applies by default "do not start on battery", "stop if switching to battery" and "stop after 72 hours": the collector would not have started on battery and would have stopped after three days | tasks defined with XML: no time limit, start on battery, automatic restart if it ends | `test_task_xml_is_valid_and_survives_laptop_and_72h_defaults` |
| A24 | Low | `hwdrift status` printed "NOTIFICA" lines (noise) | quiet mode | `test_status_is_quiet_and_does_not_log_notifications` |
| A25 | Low | With an explicit `--db` the collector did not write the log to file: the GUI log tab and the diagnostic bundle would have been empty | the log always goes to the data folder | GUI test |
| A26 | Low | `HWDRIFT_HOME` did not take precedence over the configuration's `data_dir`: the GUI demo could have written into the real folder | the explicit environment override takes precedence | `test_window_shows_status_charts_events_and_saves_config` |

### 6.2 What happens at a restart (verified with a simulated clock)

Abrupt shutdown → restart after 10 hours: no orphan episode, one `system.gap`, two
`system.collector_start`, regular data after the restart, baseline unchanged. Residual limits: up
to ~60 s of raw data is lost; between power-on and Windows logon there is no data (the collector
starts at logon); Windows Fast Startup may hide the `system.reboot`, but the gap is recorded by the
heartbeat.

### 6.3 GUI — checks

- Data layer (`gui/data.py`, without Tk): 9 unit tests; real window: integration test under Xvfb
  (status, charts, real time from `live.json`, event recording, saving a valid configuration and
  rejecting an invalid one, background analysis, diagnostic bundle, closing). The test is skipped
  when there is no display.
- Visual review (screenshots): fixed the configuration form layout (cut-off fields), legend
  overlapping the title, value labels, truncated axis label.
- Executable: built with PyInstaller **on Linux** (same spec) to validate dynamic imports, included
  data and CLI/GUI dispatch: full CLI (simulate, analyze, status, report, run) and window working
  from the frozen executable (63 MB).

### 6.4 Residual risks

| # | Priority | Risk | Recommendation |
|---|---|---|---|
| R11 | **High** | The Windows `.exe` was neither built nor tested here (no Windows): Tk on Windows, UAC request (`ShellExecute runas`), importing the `schtasks` XML, hiding the console | run the "Build exe" workflow and test on Windows 11 (list in `docs/en/USER_GUIDE.md` §6A); `TODO` in `cli._tasks`/`task_definitions` |
| R12 | Medium | Unsigned executable: SmartScreen and some antivirus programs may flag PyInstaller executables (false positives) | Authenticode signing (certificate) or distribution through a signed installer; publish hash and Sigstore signature; UPX disabled |
| R13 | Medium | The GUI writes a user-modifiable `hwdrift.yaml`: an elevated collector that read it would reopen THREAT_MODEL T1 | the elevated collector uses a file in a protected folder with `--config` (notice in the GUI and in the CLI refusal) |
| R14 | Low | The GUI charts have no equivalent data table nor keyboard navigation of the canvas (the HTML report does) | accepted for v1; the GUI does not replace the accessible report |
| R15 | Low | The elevated collector and the GUI must share the data folder (`LOCALAPPDATA` of the same user); with UAC using another administrator's credentials the folders differ | pass explicit `--db`/`HWDRIFT_HOME` |

---

## 7. Addendum — English localization

Request: translate the GUI into English and create an English copy of the documentation.

### 7.1 Design

- **Catalog approach** (`src/hwdrift/i18n.py`, `i18n_en.py`): the Italian text in the code is the
  *key*, `tr("...")` returns the English translation when the language is `en` (default) and the
  Italian text when it is `it`. A text missing from the catalog falls back to Italian (never an
  error). The language is chosen by `language` in the configuration, overridden by the
  `HWDRIFT_LANGUAGE` environment variable.
- **What is translated**: the whole GUI, the HTML report, the alarms, the diagnosis hypotheses
  (titles, actions, supports), the notifications and toasts, event and indicator descriptions,
  the analysis warnings and the example configuration (`init-config`). Because the alarm texts are
  generated by the worker and stored in the database, they are created in the configured
  language; a language change is reflected at the next analysis.
- **What is not translated**: command-line help and messages (Typer) and the log lines stay in
  Italian (a deliberate scope limit — the request was for the GUI and its content).

### 7.2 Findings

| # | Severity | Finding | Action |
|---|---|---|---|
| L1 | Medium | Risk of silent gaps: a mistyped key would show Italian text inside the English GUI | `tests/unit/test_i18n.py` scans every `tr("…")` literal in the sources (and the diagnosis rule texts, indicator/event descriptions, GUI field labels) and fails on a missing catalog entry; it also checks that `{placeholders}` match between languages |
| L2 | Low | The GUI language had to follow the content created by the worker; otherwise the scheduled analysis (Italian) and the GUI (English) would overwrite each other's alarm texts | one language for the whole installation (`language`), applied by every component when it is created |
| L3 | Low | Existing tests assert Italian texts | the global test fixture runs in Italian (`HWDRIFT_LANGUAGE=it`); new tests (`test_english.py`, bilingual GUI window test) check English, including that no Italian marker appears in the English report |
| L4 | Low | Two copies of the documentation can drift apart | `tests/unit/test_docs_sync.py` checks that each English document exists, links to its Italian original, and has the same number of headings; CONTRIBUTING requires updating both |

### 7.3 Residual risks

| # | Priority | Risk | Recommendation |
|---|---|---|---|
| R16 | Medium | The English translations were written by an AI tool and not proofread by a native speaker | have the catalog (`i18n_en.py`) and `docs/en/` reviewed (see AI_USAGE.md) |
| R17 | Low | CLI messages and logs remain Italian: the English GUI log tab shows Italian log lines | translate log messages and CLI help if the tool is distributed beyond Italian speakers |
| R18 | Low | The language of already-stored alarm texts changes only at the next analysis | accepted; run **Analyze now** after switching language |
