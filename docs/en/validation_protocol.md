# Validation protocol (section 12) and current status

> English copy of [`docs/protocollo_validazione.md`](../protocollo_validazione.md) (Italian); keep them in sync.

| Phase | Method | Status | Tool in the repository |
|---|---|---|---|
| 0. Statistical simulation | synthetic generator with degradation, load changes, environment | **partial**: consistency scenarios and R1 ARL on independent data | `hwdrift simulate`, `sim/`, `tests/integration/test_scenarios.py`, `tests/property/` |
| 1. Software validation | comparison with HWiNFO/GPU-Z, 72 h, sleep, missing sensors, driver reset, privileges, overhead | to do on hardware | `hwdrift selftest`, `scripts/m0_spike.py`, `hwdrift import-hwinfo` |
| 2. Replay on real data | own and volunteers' HWiNFO/LHM logs | to do | `hwdrift import-hwinfo` + `analyze` |
| 3. Controlled faults | blind reversible injections, ≥ 3 repetitions | to do | `hwdrift event add`, "effectiveness" report |
| 4. Field pilot | 10–30 machines, 3–6 months, informed consent | to do | `hwdrift export` (anonymous) |
| 5. Comparison with alternatives | fixed threshold, linear trend, EWMA/CUSUM, Isolation Forest at equal ARL0 | to do | `spc/trend.py` (linear trend), EWMA/CUSUM already computed |

## Phase 0 — what remains to be measured

1. ARL0 and ARL1 of the **per-window** charts (long-term σ, R1) and the **daily** charts (R1–R3,
   EWMA, CUSUM, MK) on AR(1) series with φ ∈ {0; 0.3; 0.6; 0.9} and non-normal noise; comparison
   with theoretical values (370 for R1 on independent data, verified in
   `test_arl0_r1_close_to_370`).
2. Detection delay as a function of drift magnitude (dust `rate` 0.005–0.05/day) and step size
   (fan `severity` 0.2–0.8).
3. Sensitivity to the length and variety of Phase I (`phase1_min_days` 3–14).
4. False alarms per machine-month on the negative controls with 20 different seeds.
5. Fixed vs adaptive regimes vs continuous model (RQ6).

Suggested procedure:

```powershell
for ($s=1; $s -le 20; $s++) {
  hwdrift --db "f0-healthy-$s.sqlite" simulate healthy --days 60 --seed $s
  hwdrift --db "f0-healthy-$s.sqlite" analyze --no-report
}
```

and collection of `alerts`/`signals` with `hwdrift export --format jsonl`.

## Phase 3 — test safety

Never disable thermal protections; define for each machine a cut-off threshold below the
throttling limit; every injection must be immediately reversible; record every injection with
`hwdrift event add user.note --note "injection X"` and the exact instant (blind analysis: whoever
analyzes does not see the log until the end).

## Acceptance criteria (proposals)

- ≤ ~1 "action" alarm per machine per month;
- no maintenance alarm in the negative controls;
- overhead within budget (≤ 1% of one core, ≤ 100 MB; worker ≤ 300 MB, ≤ 30 s);
- maximum detection delay for the dust surrogate: to be fixed after Phase 0.
