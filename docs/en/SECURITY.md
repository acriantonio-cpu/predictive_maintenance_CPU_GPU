# Security

> English copy of [`SECURITY.md`](../../SECURITY.md) (Italian); keep them in sync.

## Reporting a vulnerability

Do not open a public issue. Use the **"Report a vulnerability"** feature (GitHub Security
Advisories) of the repository. You will receive a reply within 7 days; the fix and disclosure are
coordinated with the reporter (responsible disclosure, normally within 90 days).

## Supported versions

Only the latest published version receives security fixes.

## Recommended installation (collector with elevated privileges)

1. Install HWDrift and its virtual environment in a folder writable only by administrators (e.g.
   `C:\Program Files\HWDrift`), not in the user folder.
2. Put the configuration file used by the elevated collector in a protected folder and pass it
   with `--config`: a file the user can edit can change the external executables used
   (`smartctl`). The GUI saves the configuration in the user's data folder: do not point an
   elevated collector at that file.
3. Prefer LibreHardwareMonitor in `web` mode (loopback): HWDrift does not load the kernel driver
   in its own process.
4. Notifier and analysis run **without** privileges (see `hwdrift schedule install`).

## Principles

- No network connection by default; the only HTTP request is to the LHM server on loopback,
  without proxy.
- No action on the hardware.
- All external inputs (LHM JSON, event-log XML, HWiNFO CSV, smartctl output) are treated as
  untrusted.

Details in the [threat model](THREAT_MODEL.md).
