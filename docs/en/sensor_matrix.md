# Sensor matrix (to be filled in during M0)

> English copy of [`docs/matrice_sensori.md`](../matrice_sensori.md) (Italian); keep them in sync.

The script `scripts/m0_spike.py` produces, for each machine, a `summary.json` with the availability
of the canonical channels and of the throttling flags. Copy the results here.

## Sources

| Source | Module | Privileges | Main channels | Notes / TODO(M0) |
|---|---|---|---|---|
| LibreHardwareMonitor (web) | `collectors/lhm.py` | LHM as admin; HWDrift not | `cpu.pkg.*`, `gpu*.temp_*`, fans, `mb.temp_c`, `ssd*.temp_c` | loopback only; verify sensor names per LHM version |
| LibreHardwareMonitor (DLL) | `collectors/lhm.py` | admin | as above | kernel driver: check Memory Integrity and anti-cheat |
| NVML | `collectors/nvml.py` | no | `gpu*.temp_edge_c`, `power_w`, `clock_mhz`, `fan_pct`, `util_pct`, `throttle_*`, `pcie_replay` | hotspot/memory junction not exposed on consumer GPUs: from LHM |
| Event log | `collectors/eventlog.py` | to verify | events `hw.whea_*`, `hw.tdr`, `hw.kernel_power`, `hw.bugcheck` | catalog of IDs to be confirmed |
| Performance counters | `collectors/perfcounters.py` | no | `cpu.clock_eff_mhz`, `cpu.clock_nominal_mhz`, `cpu.load_pct` | compare with HWiNFO's effective clock |
| psutil | `collectors/psutil_basic.py` | no | `cpu.load_pct` | no thermal sensors on Windows |
| System information | `collectors/wmi_info.py` | no | events `config.driver`, `config.bios` | PowerShell `Get-CimInstance` |
| smartmontools | `collectors/smart.py` | admin | `ssd*.temp_c` | external executable; devices listed by hand |
| HWiNFO CSV | `collectors/hwinfo_csv.py` | no | as LHM | English column names; other languages via `profile.mapping` |
| Simulator | `collectors/simulator.py` | no | all | tests and development |
| Linux hwmon (experimental) | `collectors/linux_hwmon.py` | RAPL often root-only | `cpu.pkg.temp_c`, `cpu.pkg.power_w`, fans | outside the v1 scope |

## Availability per machine (template)

| Channel | Machine A | Machine B | Machine C |
|---|---|---|---|
| `cpu.pkg.temp_c` | | | |
| `cpu.pkg.power_w` | | | |
| `cpu.clock_eff_mhz` | | | |
| `cpu.throttle_thermal` (direct flag) | | | |
| `cpu.fan_rpm` / `chassis.fan1_rpm` | | | |
| `gpu0.temp_edge_c` | | | |
| `gpu0.temp_hotspot_c` | | | |
| `gpu0.temp_mem_c` | | | |
| `gpu0.power_w` | | | |
| `gpu0.fan_rpm` / `gpu0.fan_pct` | | | |
| `gpu0.throttle_reasons` | | | |
| `mb.temp_c` | | | |
| `ssd0.temp_c` | | | |
| Time in idle / medium / high | | | |
| Collector overhead (CPU %, MB) | | | |

## NVML throttle-reason bits used

| Bit | Name | Use |
|---|---|---|
| 0x1 | GpuIdle | ignored |
| 0x2 | ApplicationsClocksSetting | ignored |
| 0x4 | SwPowerCap | power limit (info) |
| 0x8 | HwSlowdown | thermal/severe |
| 0x20 | SwThermalSlowdown | thermal |
| 0x40 | HwThermalSlowdown | thermal |
| 0x80 | HwPowerBrakeSlowdown | severe |

TODO(M0): confirm the values with the installed version of `nvidia-ml-py`.
