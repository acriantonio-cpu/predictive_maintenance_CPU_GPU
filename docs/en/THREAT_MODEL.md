# Threat model (requirement 15.3)

> English copy of [`THREAT_MODEL.md`](../../THREAT_MODEL.md) (Italian); keep them in sync.

Version 0.1 — to be reviewed before every release and after every new data source.

## Assets

| Asset | Why it matters |
|---|---|
| Operating-system integrity | the collector runs with elevated privileges and, with LHM in DLL mode, loads a kernel driver |
| Telemetry data and event log | may reveal usage habits (hours, games) |
| Correctness of the alarms | a false "all OK" can make a real overheating be ignored |
| Configuration (`hwdrift.yaml`) | decides which executables and URLs are used |

## Components and trust boundaries

```
[user] ──(CLI)──► hwdrift analyze/report/notify   (normal privileges, DB write / read-only)
                         │ SQLite (local file)
[Task Scheduler, admin] ─► hwdrift run (collector)   ◄── LHM web (loopback) / DLL + kernel driver
                                                    ◄── NVML, wevtutil, PowerShell, smartctl
```

- **Collector** (elevated): the only component with privileges. Reads sensors, writes the DB.
- **Analysis worker** (normal, low priority): reads and writes only analysis tables.
- **Notifier** (normal, user session): opens the DB **read-only** (`mode=ro`), writes only its own
  `notifier_state.json` and `status.json`.
- **Report**: static HTML file with Content-Security-Policy `default-src 'none'`, no scripts.

## Threats and countermeasures (STRIDE)

| # | Threat | Countermeasure | Verification |
|---|---|---|---|
| T1 | *Tampering*: a non-administrator user edits `hwdrift.yaml` to make the elevated collector run an arbitrary binary (e.g. `sources.smart.smartctl`) | the elevated collector must read its configuration from a folder writable only by administrators (see SECURITY.md, "recommended installation"); SMART devices validated with a regex; no shell (`subprocess` with an argument list) | review, `test_smart_collector` |
| T2 | *Spoofing / information disclosure*: the LHM URL is pointed to a remote host to exfiltrate or inject data | URL accepted only if loopback (`check_loopback`), no proxy (`ProxyHandler({})`) | `test_loopback_rejected` |
| T3 | *Tampering*: malformed or hostile LHM JSON, event-log XML or HWiNFO CSV | size limits (8 MB JSON, 4 MB XML), maximum JSON tree depth, rejection of DTD/XML entities, truncated CSV fields, non-numeric values ignored | parser tests; parser fuzzing (`tests/property/test_fuzz_parsers.py`) |
| T4 | *Injection* in the PowerShell toast through titles/texts | the text goes through environment variables, never interpolated into the script | review of `alerts/toast.py` |
| T5 | *SQL injection* | parameterized queries; the few composed strings use fixed table names | ruff `S608`, review |
| T6 | *Information disclosure* in the dataset export | anonymous export by default: only canonical channels, no raw name, note, path or process; random machine ID | `test_jsonl_valid_against_schemas_and_anonymous` |
| T7 | *Denial of service*: the collector slows the PC or games | overhead budget, adaptive interval, game-safe, selftest in CI | `hwdrift selftest` |
| T8 | *Elevation of privilege* via the LHM kernel driver | prefer `web` mode (driver in the LHM process, not in HWDrift); document Memory Integrity; no DLL redistribution | documentation |
| T9 | *Repudiation / alarm integrity*: a stopped collector interpreted as "healthy" | heartbeat, `status.*` channels, "collector stopped" notification, "insufficient data" state in the report | `test_notifier_stale_collector_and_power_info` |
| T10 | Database writable by other local users (data falsification) | data-folder ACLs limited to the user and administrators | to verify in M5 |
| T11 | *Supply chain* | dependencies pinned with hashes (`requirements/*.lock`), CycloneDX SBOM, releases signed with Sigstore, license check in CI | workflows `ci.yml`, `release.yml` |
| T12 | *Tampering* via the GUI: the GUI (normal user) writes `hwdrift.yaml` in the user's data folder; an elevated collector that read it would run paths chosen by a non-administrator | the elevated collector refuses the implicit configuration from the current folder and the documentation requires `--config` on a file in a protected folder; the GUI exposes neither the `smartctl` path nor other executables | `test_elevated_collector_refuses_cwd_config`, review |
| T13 | Local *DoS*: the `stop.request` and `live.active` files in the data folder let a user process stop the collector or make it write every second | accepted: the same user can already kill the process; `live.json` is a few KB and is written only while `live.active` is recent (< 10 s) | review |
| T14 | Code execution through the GUI executable started as administrator (UAC) | elevation happens only on an explicit button; the executable is distributed with a hash and a Sigstore signature | documentation |

## Residual risks

- The elevated collector imports Python modules from the virtual environment: if the venv folder
  is writable by a non-administrator user, that user can run code as administrator. **Install the
  venv in a protected folder** (e.g. `C:\Program Files\HWDrift\venv`) when the collector runs
  elevated.
- With LHM in `dll` mode the kernel driver is part of the attack surface.
- `health-check` generates heat: the cut-off thresholds are software-side.
