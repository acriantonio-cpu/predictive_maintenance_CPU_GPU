# SPDX-License-Identifier: Apache-2.0
"""Grafici SVG inline per il report (nessun JavaScript, nessuna rete).

Scelta di progetto: la specifica propone Plotly; qui si usa SVG statico perché il
file resta piccolo, funziona senza script (anche con criteri di sicurezza
restrittivi) e si rende accessibile con ``<title>``/``<desc>`` e una tabella dati
equivalente. Il colore non è mai l'unico canale: i segnali hanno una forma
diversa (triangolo) e sono elencati a parole.
"""

from __future__ import annotations

import html
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ..i18n import tr


@dataclass
class Series:
    ts: list[int]
    values: list[float]
    phase1_end: int | None = None
    signals: dict[int, str] = field(default_factory=dict)  # ts -> regole


@dataclass
class Lines:
    center: float | None = None
    ucl: float | None = None
    lcl: float | None = None
    ucl2: float | None = None
    lcl2: float | None = None


def _fmt_date(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, UTC).strftime("%d/%m")


def _nice(v: float) -> str:
    a = abs(v)
    if a == 0:
        return "0"
    if a >= 100:
        return f"{v:.0f}"
    if a >= 1:
        return f"{v:.2f}"
    return f"{v:.4f}"


def chart(series: Series, lines: Lines, title: str, desc: str, uid: str,
          events: list[tuple[int, str]] | None = None, width: int = 720,
          height: int = 220) -> str:
    ml, mr, mt, mb = 64, 16, 12, 28
    w, h = width - ml - mr, height - mt - mb
    xs, ys = series.ts, series.values
    if not xs:
        return ('<p class="empty" role="note">' + tr(
            "{title}: copertura insufficiente, nessuna osservazione.").format(
                title=html.escape(title)) + "</p>")
    vals = [v for v in ys if math.isfinite(v)]
    for v in (lines.ucl, lines.lcl, lines.center):
        if v is not None and math.isfinite(v):
            vals.append(v)
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-12:
        lo, hi = lo - 1, hi + 1
    pad = (hi - lo) * 0.08
    lo, hi = lo - pad, hi + pad
    x0, x1 = xs[0], xs[-1] if xs[-1] > xs[0] else xs[0] + 1

    def X(t: int) -> float:
        return ml + (t - x0) / (x1 - x0) * w

    def Y(v: float) -> float:
        return mt + (hi - v) / (hi - lo) * h

    tid, did = f"t-{uid}", f"d-{uid}"
    out = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
           f'aria-labelledby="{tid} {did}" xmlns="http://www.w3.org/2000/svg">',
           f'<title id="{tid}">{html.escape(title)}</title>',
           f'<desc id="{did}">{html.escape(desc)}</desc>',
           f'<rect x="{ml}" y="{mt}" width="{w}" height="{h}" class="plot"/>']
    if series.phase1_end is not None and x0 <= series.phase1_end:
        xe = min(X(series.phase1_end), ml + w)
        out.append(f'<rect x="{ml}" y="{mt}" width="{xe - ml:.1f}" height="{h}" class="phase1"/>')
        out.append(f'<text x="{ml + 4}" y="{mt + 12}" class="lbl">{tr("Fase I")}</text>')
    for t, kind in events or []:
        if x0 <= t <= x1:
            out.append(f'<line x1="{X(t):.1f}" x2="{X(t):.1f}" y1="{mt}" y2="{mt + h}" '
                       f'class="ev ev-{html.escape(kind.split(".")[0])}"/>')
    # griglia e assi
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        out.append(f'<line x1="{ml}" x2="{ml + w}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="grid"/>')
        out.append(f'<text x="{ml - 6}" y="{Y(v) + 4:.1f}" class="ax" text-anchor="end">'
                   f"{_nice(v)}</text>")
    for k in range(6):
        t = int(x0 + (x1 - x0) * k / 5)
        out.append(f'<text x="{X(t):.1f}" y="{height - 8}" class="ax" text-anchor="middle">'
                   f"{_fmt_date(t)}</text>")
    for v, cls, name in ((lines.ucl, "lim", "UCL"), (lines.lcl, "lim", "LCL"),
                         (lines.ucl2, "lim2", ""), (lines.lcl2, "lim2", ""),
                         (lines.center, "cl", "LC")):
        if v is not None and math.isfinite(v) and lo <= v <= hi:
            out.append(f'<line x1="{ml}" x2="{ml + w}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" '
                       f'class="{cls}"/>')
            if name:
                out.append(f'<text x="{ml + w - 2}" y="{Y(v) - 3:.1f}" class="lbl" '
                           f'text-anchor="end">{name}</text>')
    pts = [(X(t), Y(v)) for t, v in zip(xs, ys, strict=True) if math.isfinite(v)]
    if len(pts) > 1:
        d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        out.append(f'<polyline points="{d}" class="series"/>')
    r = 2.2 if len(pts) < 300 else 1.2
    for t, v in zip(xs, ys, strict=True):
        if not math.isfinite(v):
            continue
        if t in series.signals:
            x, y = X(t), Y(v)
            out.append(f'<path d="M{x:.1f},{y - 6:.1f} L{x + 5:.1f},{y + 4:.1f} '
                       f'L{x - 5:.1f},{y + 4:.1f} Z" class="sig"><title>'
                       f"{html.escape(series.signals[t])}</title></path>")
        else:
            out.append(f'<circle cx="{X(t):.1f}" cy="{Y(v):.1f}" r="{r}" class="pt"/>')
    out.append("</svg>")
    return "".join(out)
