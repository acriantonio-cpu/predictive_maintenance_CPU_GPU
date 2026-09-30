# SPDX-License-Identifier: Apache-2.0
"""Definizione dei componenti monitorati e dei canali che li descrivono."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Component:
    key: str  # "cpu", "gpu0", ...
    suffix: str  # suffisso degli indicatori: "cpu", "gpu", "gpu1"
    power: str
    temp: str
    util: str
    throttle_thermal: str
    throttle_power: str
    fans: tuple[str, ...]
    hotspot: str | None = None
    label: str = ""


def components(channel_names: set[str]) -> list[Component]:
    """Componenti per cui esistono almeno potenza e temperatura."""
    out: list[Component] = []
    cpu = Component("cpu", "cpu", "cpu.pkg.power_w", "cpu.pkg.temp_c", "cpu.load_pct",
                    "cpu.throttle_thermal", "cpu.throttle_power",
                    ("cpu.fan_rpm", "chassis.fan1_rpm"), label="CPU")
    if cpu.power in channel_names and cpu.temp in channel_names:
        out.append(cpu)
    for i in range(8):
        g = f"gpu{i}"
        comp = Component(g, "gpu" if i == 0 else g, f"{g}.power_w", f"{g}.temp_edge_c",
                         f"{g}.util_pct", f"{g}.throttle_thermal", f"{g}.throttle_power",
                         (f"{g}.fan_rpm", f"{g}.fan_pct"), f"{g}.temp_hotspot_c",
                         label="GPU" if i == 0 else f"GPU {i}")
        if comp.power in channel_names and comp.temp in channel_names:
            out.append(comp)
    return out
