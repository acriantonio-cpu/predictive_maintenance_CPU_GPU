# Methodology

> English copy of [`docs/metodologia.md`](../metodologia.md) (Italian); keep them in sync.

This document explains **how** HWDrift turns telemetry into signals and hypotheses, and **why**
some choices depart from, or refine, the specification. Every choice is a project hypothesis to
be confirmed in the validation phases ([validation_protocol.md](validation_protocol.md)).

## 1. From sample to aggregate

| Step | Where | Rule |
|---|---|---|
| Sampling | `runner.py` | 1 Hz (0.5–5 s), monotonic clock for timing, UTC ms in the database |
| Quality | `quality/sanity.py` | physical range per channel, failed-read values (0, 255, −128), jump beyond `max_rate`·Δt, identical value for `freeze_s` (900 s for temperatures) |
| Aggregation | `storage/writer.py` | per minute: median, min, max of the OK samples only; `n` and `valid_frac` document the exclusions |
| Retention | writer | raw 48 h; aggregates, events and analysis never expire |

Frozen-value detection has a **latency equal to `freeze_s`**: windows starting in the first 15
minutes of a frozen sensor may pass. It is a trade-off between false positives (integer
temperatures stable at idle) and reactivity; the test
`test_frozen_sensor_does_not_create_windows` documents it.

## 2. Stationary windows

A 5-minute window, not overlapping the previous ones, is valid if: power CV < 10%,
|temperature slope| < 0.5 °C/min, the 3 preceding minutes have the same power (warm-up),
utilization standard deviation < 10 points, all minutes present with `valid_frac` ≥ 0.8, no
configuration event, gap or reboot. Windows with thermal or power throttling are marked
`throttled` and excluded from the indicators (failure mode 5). A note that emerged from the
simulator: during real throttling power oscillates and stationary windows often **do not**
form; for this reason the throttling share is computed on the minutes under load, not on the
windows.

## 3. Regimes

Default `fixed`: idle < 30% and high ≥ 65% of the 99th percentile of the per-minute power
observed in the calibration period (first 30 stationary windows). The specification cites
50%/80% as an example; with those values a game with medium CPU load (40–50% of TDP) would fall
in idle, so lower thresholds were chosen, configurable. The `adaptive` mode (terciles) remains
available: on a PC that is almost always idle the terciles all fall in idle. Boundaries stay
locked; `hwdrift analyze --rebuild` recomputes them.

## 4. Indicators

| Indicator | Formula | Regimes | Primary |
|---|---|---|---|
| `rth_cpu`, `rth_gpu` | (T − T_ref)/P | medium, high | yes |
| `hotspot_delta_gpu` | T_hotspot − T_edge | medium, high | yes |
| `fan_effort_*` | mean rpm (or % duty) in the window, only if > 0 | all | yes |
| `idle_temp_*` | T − T_ref | idle | yes |
| `throttle_frac_*` | minutes with thermal throttling / minutes under load | daily | yes |
| `whea_corrected`, `tdr`, `pcie_replay_gpu`, `unexpected_shutdown` | counts per day | daily | yes (c chart) |
| `case_delta_cpu` | T_motherboard − T_ref | medium, high | no |
| `temp_resid[_fan]_*` | Huber residual T ~ P + T_ref (+ fan) | per regime | no |
| `temp_cont_*` | residual of T ~ P + P² + T_ref | all | no |
| `ref_temp` | T_ref at idle | idle, daily | context |

**T_ref.** Default: the SSD temperature (`ssd0.temp_c`) as an ambient proxy. The proxy gets
contaminated if airflow worsens (in the simulator the SSD rises with dust): for this reason
`ref_temp` is a *context* indicator, used as a contradiction only where the environment explains
the pattern (see §7).

## 5. Control charts

Two levels for each indicator and regime:

| Level | Observation | σ | Rules |
|---|---|---|---|
| `window` | one per stationary window | **long-term** (sample standard deviation of Phase I) | R1 only |
| `daily` | daily median (≥ 2 windows), **complete** days only | MR̄/1.128, or robust median(MR)/0.954 if the data is strongly skewed | R1, R2, R3 (R4 optional), MR, EWMA (λ=0.2, L=2.86), CUSUM (k=0.5, h=5), Mann-Kendall (α=0.01) |

**Why long-term σ on windows.** On simulated data the lag-1 autocorrelation of the per-window
series was 0.3–0.85: windows of the same session resemble each other, so MR̄/d₂ underestimates
the between-session variability. With σ from MR and all rules the healthy case generated tens of
thousands of signals and a false "action" alarm in 30 days; with long-term σ and R1 only the
signals drop to a few hundred and there is no maintenance alarm. Sequence rules and methods with
memory stay on the daily chart, which is nearly independent. It is the countermeasure of
section 7 of the specification ("switch to daily aggregation") made explicit.

**Phase I.** It closes at the first instant in which the chart has ≥ 25 observations, over ≥ 5
days and ≥ 5 sessions (a session = a pause > 2 h or a change of day). The *minimal chronological
prefix* is always used, so an analysis that catches up weeks at once does not include the fault in
the limits. Points beyond 3σ are cleaned in at most 3 iterations (recorded). Before closing, with
≥ 12 observations, points are compared with provisional limits 1.25× wider computed only on the
preceding points: the signals are labeled `provisional` and remain informational. The provisional
evaluation is the same both with incremental analyses every 15 minutes and with an analysis that
catches up weeks at once. `baseline lock` forces closure with provisional limits. Constant series:
a minimum σ per indicator (e.g. 0.01 for the throttling share), otherwise the chart would be
degenerate.

**Segments.** Maintenance and `baseline start` close the segment of all charts; a configuration
change (driver, BIOS, profile) closes only those of the component indicated in
`detail.component` (e.g. the GPU driver does not touch the CPU charts). The closed segment is first
processed with the data up to the closure, then archived.

## 6. Alarm policy

- **Info**: at least one signal (any rule) in the observation period (14 days).
- **Warning**: R1/R2/R3/R4/MR/C signals on the same side on **2 consecutive days**.
- **Action**: a diagnosis hypothesis whose requirements are met and that involves at least
  **2 charts at warning level** (different indicators or regimes), with no contradictions.
- Secondary indicators: at most *info*. Context indicators: may reach *warning* but do not
  generate alarms of their own.
- Signals within ±24 h of a configuration event: label `configuration`, no maintenance alarm;
  a notice asks to confirm the change.
- Budget: beyond `action_budget_per_month` "action" alarms in 30 days, the notifier suspends
  action-level toasts (except fatal errors) and the report asks to review thresholds and rules.

## 7. Diagnosis

Rules in `src/hwdrift/diagnosis/rules/default.yaml`. Conditions on indicators (side, regimes,
number of components) and events. Contradictions only count at warning level (isolated info
signals are expected noise with ~50 charts); a `blocking` contradiction cancels the hypothesis. A
hypothesis is proposed only at level ≥ warning (except informational rules such as
"environment"). Titles and suggested actions are translated through the catalog
`src/hwdrift/i18n_en.py`.

Simulation assumptions to verify in Phase 3: the fan follows the *heatsink* temperature, so dried
paste raises Rth but not fan effort. A colder room slows the fans and raises Rth: the same
signature as a degraded fan. For this reason `fan_failure` has a falling `ref_temp` as a blocking
contradiction; dust does not, because a proxy contaminated by dust would hide it.

## 8. Simulator results (Phase 0, preliminary)

26 days per scenario, fault from day 12–17, seed 11 (`tests/integration/test_scenarios.py`):

| Scenario | Expected | Obtained |
|---|---|---|
| healthy, driver_change, ambient, power_limit | no maintenance alarm | no "action" alarm, no maintenance hypothesis |
| dust | dust | `dust_airflow`, action, first hypothesis |
| paste | paste | `paste_contact`, action, first hypothesis |
| fan_fail | fan | `fan_failure`, action, first hypothesis |
| throttle | throttling share rising, Rth not falsified | signals on `throttle_frac_cpu`, no Rth from throttled windows |
| dust_then_clean | closed segment, visible recovery | effectiveness view "recovered" |
| whea | c chart | `C` signals, instability hypothesis |

These are software consistency checks, not a validation of the method: ARL0/ARL1 as a function of
magnitude, sensitivity to Phase I length and comparison with the alternatives remain to be
measured (full Phase 0).

## 9. Departures from the specification

| Specification | Implementation | Reason |
|---|---|---|
| Report with Plotly | static inline SVG, no script | smaller file, works under a strict CSP, accessible with `<title>`/`<desc>` and a data table |
| Configuration with pydantic | dictionaries with explicit validation | the collector does not load pydantic (memory) |
| statsmodels for Ljung-Box | direct implementation with scipy | one dependency fewer |
| pywin32 for the Event Log | `wevtutil` as an external process | no dependency, fixed arguments |
| Regimes: 50%/80% example | default 30%/65% | see §3 |
| R2/R3 on all charts | only on the daily charts | autocorrelation (see §5) |
| Windows only | experimental Linux collector | shows the core's independence (requirement 15.2) |
| Italian document and UI | English by default, Italian available (`language`) | international audience; the code's texts are Italian and act as translation keys (`i18n.py`) |
