# SPDX-License-Identifier: Apache-2.0
"""Importatore dei log CSV di HWiNFO (log storici).

Formato atteso: prima riga di intestazione ``Date,Time,<Sensore [unità]>,...``;
le ultime righe ripetono intestazione e nomi dei gruppi. I nomi dei sensori
cambiano con lingua e macchina: la mappatura colonna -> canale usa regole
euristiche ed è sovrascrivibile dal profilo (chiave = intestazione di colonna).

Il file è input non fidato: righe troppo lunghe, date o numeri non validi e
colonne duplicate sono gestiti senza eccezioni non controllate.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..channels import spec_for
from ..model import Sample

MAX_FIELD = 1024
_COL = re.compile(r"^(.*?)\s*\[([^\]]*)\]\s*$")

# (regex sul nome colonna senza unità, unità attesa o None, canale)
# TODO(M0): verificare i nomi di colonna con log reali in italiano e in inglese.
COLUMN_RULES: list[tuple[re.Pattern[str], str | None, str]] = [
    (re.compile(r"^(cpu package|cpu \(tctl/tdie\)|core \(tctl/tdie\)|cpu tctl/tdie)$", re.I),
     "°C", "cpu.pkg.temp_c"),
    (re.compile(r"^cpu package power$", re.I), "W", "cpu.pkg.power_w"),
    (re.compile(r"^total cpu usage$", re.I), "%", "cpu.load_pct"),
    (re.compile(r"^(core effective clocks \(avg\)|average effective clock)$", re.I), "MHz",
     "cpu.clock_eff_mhz"),
    (re.compile(r"^(core thermal throttling|thermal throttling \(htc\)|ia: prochot)$", re.I),
     None, "cpu.throttle_thermal"),
    (re.compile(r"^(package/ring power limit exceeded|ia: package-level rapl/pbm pl1)$",
                re.I), None, "cpu.throttle_power"),
    (re.compile(r"^gpu temperature$", re.I), "°C", "gpu0.temp_edge_c"),
    (re.compile(r"^gpu hot ?spot temperature$", re.I), "°C", "gpu0.temp_hotspot_c"),
    (re.compile(r"^gpu memory junction temperature$", re.I), "°C", "gpu0.temp_mem_c"),
    (re.compile(r"^(gpu power|total gpu power|gpu asic power)$", re.I), "W", "gpu0.power_w"),
    (re.compile(r"^(gpu core load|gpu utilization)$", re.I), "%", "gpu0.util_pct"),
    (re.compile(r"^gpu fan ?1?$", re.I), "RPM", "gpu0.fan_rpm"),
    (re.compile(r"^(gpu thermal limit|performance limit - thermal)$", re.I), None,
     "gpu0.throttle_thermal"),
    (re.compile(r"^(gpu power limit|performance limit - power)$", re.I), None,
     "gpu0.throttle_power"),
    (re.compile(r"^cpu$", re.I), "RPM", "cpu.fan_rpm"),
    (re.compile(r"^(motherboard|system|mainboard)$", re.I), "°C", "mb.temp_c"),
    (re.compile(r"^(drive temperature|drive temperature 1)$", re.I), "°C", "ssd{n}.temp_c"),
]


def map_column(header: str, occurrence: int) -> tuple[str | None, str]:
    m = _COL.match(header)
    name, unit = (m.group(1), m.group(2)) if m else (header, "")
    for rx, u, ch in COLUMN_RULES:
        if rx.match(name.strip()) and (u is None or u.lower() == unit.lower()):
            ch = ch.format(n=occurrence)
            if "{n}" not in ch and occurrence > 0 and not ch.startswith("ssd"):
                return None, unit  # colonna duplicata: si tiene solo la prima
            return ch, unit
    return None, unit


def _parse_float(text: str) -> float | None:
    t = text.strip()
    if not t:
        return None
    low = t.lower()
    if low in ("yes", "sì", "si", "true"):
        return 1.0
    if low in ("no", "false"):
        return 0.0
    try:
        return float(t.replace(",", "."))
    except ValueError:
        return None


def _parse_ts(date: str, time_: str, tz: timezone | None) -> int | None:
    for fmt in ("%d.%m.%Y %H:%M:%S.%f", "%d.%m.%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S.%f", "%d/%m/%Y %H:%M:%S"):
        try:
            dt = datetime.strptime(f"{date.strip()} {time_.strip()}", fmt)
        except ValueError:
            continue
        dt = dt.replace(tzinfo=tz) if tz is not None else dt.astimezone()
        return int(dt.timestamp() * 1000)
    return None


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def parse_hwinfo_csv(text: str, mapping: dict[str, str] | None = None,
                     tz_offset_h: float | None = None) -> Iterator[Sample]:
    """Converte un log HWiNFO in ``Sample`` (solo le colonne mappate)."""
    mapping = mapping or {}
    tz = timezone(timedelta(hours=tz_offset_h)) if tz_offset_h is not None else None
    csv.field_size_limit(MAX_FIELD * 64)
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader)
    except StopIteration:
        return
    except csv.Error as exc:
        raise ValueError(f"CSV non valido: {exc}") from exc
    if len(header) < 3 or header[0].strip().lower() != "date":
        raise ValueError("non sembra un log CSV di HWiNFO (manca la colonna Date)")
    cols: list[tuple[int, str, str, str]] = []  # (indice, canale, unità, intestazione)
    seen: dict[str, int] = {}
    for i, h in enumerate(header[2:], start=2):
        h = h[:MAX_FIELD]
        m = _COL.match(h)
        base = m.group(1).strip().lower() if m else h.lower()
        occ = seen.get(base, 0)
        seen[base] = occ + 1
        if h in mapping:
            ch = mapping[h] or None
            unit = m.group(2) if m else ""
        else:
            ch, unit = map_column(h, occ)
        if ch:
            cols.append((i, ch, unit, h))
    mono0: int | None = None
    while True:
        try:
            row = next(reader)
        except StopIteration:
            break
        except csv.Error as exc:
            raise ValueError(f"CSV non valido alla riga {reader.line_num}: {exc}") from exc
        if len(row) < 2 or row[0].strip().lower() == "date":
            continue  # righe di intestazione ripetute in coda
        ts = _parse_ts(row[0], row[1], tz)
        if ts is None:
            continue
        if mono0 is None:
            mono0 = ts
        mono = (ts - mono0) / 1000.0
        for i, ch, unit, h in cols:
            if i >= len(row):
                continue
            v = _parse_float(row[i][:64])
            spec = spec_for(ch)
            yield Sample(ts, "hwinfo_csv", h, "hwinfo", h, v, spec.unit if spec else unit,
                         channel=ch, mono_s=mono)
