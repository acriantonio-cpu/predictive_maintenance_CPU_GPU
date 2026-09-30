# Matrice dei sensori (da compilare in M0)

Lo script `scripts/m0_spike.py` produce per ogni macchina `summary.json` con la
disponibilità dei canali canonici e dei flag di throttling. Copiare qui i risultati.

## Sorgenti

| Sorgente | Modulo | Privilegi | Canali principali | Note / TODO(M0) |
|---|---|---|---|---|
| LibreHardwareMonitor (web) | `collectors/lhm.py` | LHM come admin; HWDrift no | `cpu.pkg.*`, `gpu*.temp_*`, ventole, `mb.temp_c`, `ssd*.temp_c` | solo loopback; verificare i nomi dei sensori per versione di LHM |
| LibreHardwareMonitor (DLL) | `collectors/lhm.py` | admin | come sopra | driver kernel: verificare Memory Integrity e anti-cheat |
| NVML | `collectors/nvml.py` | no | `gpu*.temp_edge_c`, `power_w`, `clock_mhz`, `fan_pct`, `util_pct`, `throttle_*`, `pcie_replay` | hotspot/memory junction non esposti su GPU consumer: da LHM |
| Registro eventi | `collectors/eventlog.py` | da verificare | eventi `hw.whea_*`, `hw.tdr`, `hw.kernel_power`, `hw.bugcheck` | catalogo degli ID da confermare |
| Contatori di prestazione | `collectors/perfcounters.py` | no | `cpu.clock_eff_mhz`, `cpu.clock_nominal_mhz`, `cpu.load_pct` | confrontare con il clock effettivo di HWiNFO |
| psutil | `collectors/psutil_basic.py` | no | `cpu.load_pct` | nessun sensore termico su Windows |
| Informazioni di sistema | `collectors/wmi_info.py` | no | eventi `config.driver`, `config.bios` | PowerShell `Get-CimInstance` |
| smartmontools | `collectors/smart.py` | admin | `ssd*.temp_c` | eseguibile esterno; dispositivi elencati a mano |
| HWiNFO CSV | `collectors/hwinfo_csv.py` | no | come LHM | nomi di colonna in inglese; altre lingue via `profile.mapping` |
| Simulatore | `collectors/simulator.py` | no | tutti | test e sviluppo |
| Linux hwmon (sperimentale) | `collectors/linux_hwmon.py` | RAPL spesso solo root | `cpu.pkg.temp_c`, `cpu.pkg.power_w`, ventole | fuori perimetro v1 |

## Disponibilità per macchina (modello)

| Canale | Macchina A | Macchina B | Macchina C |
|---|---|---|---|
| `cpu.pkg.temp_c` | | | |
| `cpu.pkg.power_w` | | | |
| `cpu.clock_eff_mhz` | | | |
| `cpu.throttle_thermal` (flag diretto) | | | |
| `cpu.fan_rpm` / `chassis.fan1_rpm` | | | |
| `gpu0.temp_edge_c` | | | |
| `gpu0.temp_hotspot_c` | | | |
| `gpu0.temp_mem_c` | | | |
| `gpu0.power_w` | | | |
| `gpu0.fan_rpm` / `gpu0.fan_pct` | | | |
| `gpu0.throttle_reasons` | | | |
| `mb.temp_c` | | | |
| `ssd0.temp_c` | | | |
| Tempo in idle / medio / alto | | | |
| Overhead collector (CPU %, MB) | | | |

## Bit delle throttle reasons NVML usati

| Bit | Nome | Uso |
|---|---|---|
| 0x1 | GpuIdle | ignorato |
| 0x2 | ApplicationsClocksSetting | ignorato |
| 0x4 | SwPowerCap | limite di potenza (info) |
| 0x8 | HwSlowdown | termico/grave |
| 0x20 | SwThermalSlowdown | termico |
| 0x40 | HwThermalSlowdown | termico |
| 0x80 | HwPowerBrakeSlowdown | grave |

TODO(M0): confermare i valori con la versione installata di `nvidia-ml-py`.
