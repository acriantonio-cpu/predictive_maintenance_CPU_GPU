# SPDX-License-Identifier: Apache-2.0
"""Grafico a linee su ``tk.Canvas`` (nessuna dipendenza: niente matplotlib nell'eseguibile)."""

from __future__ import annotations

import math
import tkinter as tk
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime

PALETTE = ["#0b57d0", "#c2410c", "#15803d", "#7e22ce", "#b45309", "#0e7490"]
BG, FG, MUTED, GRID = "#ffffff", "#1a1a1a", "#555555", "#dddddd"
LIMIT, LIMIT2, CENTER, PHASE1 = "#b3261e", "#b45309", "#444444", "#e8eefc"


@dataclass
class HLine:
    value: float
    color: str = LIMIT
    dash: tuple[int, ...] = ()
    label: str = ""


@dataclass
class Spec:
    series: dict[str, Sequence[tuple[float, float]]] = field(default_factory=dict)
    x0: float | None = None
    x1: float | None = None
    hlines: list[HLine] = field(default_factory=list)
    shade_until: float | None = None  # zona Fase I (da x0 a questo valore)
    markers: dict[float, str] = field(default_factory=dict)  # x -> testo (triangoli)
    vlines: list[tuple[float, str]] = field(default_factory=list)  # (x, colore)
    xfmt: Callable[[float], str] = str
    empty_text: str = "nessun dato"
    y_min: float | None = None
    y_max: float | None = None


def nice_ticks(lo: float, hi: float, n: int = 4) -> list[float]:
    if hi - lo < 1e-12:
        return [lo]
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = min((s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw), default=raw)
    t = math.ceil(lo / step) * step
    out = []
    while t <= hi + 1e-9:
        out.append(round(t, 10))
        t += step
    return out


def fmt_num(v: float) -> str:
    a = abs(v)
    if a < 1e-9:
        return "0"
    if a >= 1000:
        return f"{v:.0f}"
    if a >= 100:
        return f"{v:.0f}"
    if a >= 1:
        return f"{v:.1f}"
    return f"{v:.3f}"


def time_fmt_relative(now_ms: float) -> Callable[[float], str]:
    def f(x: float) -> str:
        s = (x - now_ms) / 1000
        return "ora" if abs(s) < 1 else f"-{abs(s) / 60:.0f} min" if abs(s) >= 90 else f"{s:.0f} s"
    return f


def time_fmt_date(x: float) -> str:
    return datetime.fromtimestamp(x / 1000).strftime("%d/%m")


class LineChart(tk.Canvas):
    def __init__(self, master: tk.Misc, title: str, unit: str = "", height: int = 170,
                 **kw: object) -> None:
        super().__init__(master, height=height, bg=BG, highlightthickness=1,
                         highlightbackground=GRID, **kw)  # type: ignore[arg-type]
        self.title, self.unit = title, unit
        self.spec = Spec()
        self.bind("<Configure>", lambda _e: self.draw())

    def set(self, spec: Spec) -> None:
        self.spec = spec
        self.draw()

    def draw(self) -> None:
        self.delete("all")
        w, h = max(self.winfo_width(), 200), max(self.winfo_height(), 100)
        ml, mr, mt, mb = 52, 10, 36, 20
        pw, ph = w - ml - mr, h - mt - mb
        sp = self.spec
        allpts = [p for s in sp.series.values() for p in s]
        self.create_text(ml, 4, anchor="nw", text=f"{self.title}" + (f" [{self.unit}]"
                         if self.unit else ""), fill=FG, font=("TkDefaultFont", 9, "bold"))
        if not allpts:
            self.create_text(w / 2, h / 2, text=sp.empty_text, fill=MUTED)
            return
        x0 = sp.x0 if sp.x0 is not None else min(p[0] for p in allpts)
        x1 = sp.x1 if sp.x1 is not None else max(p[0] for p in allpts)
        if x1 <= x0:
            x1 = x0 + 1
        ys = [p[1] for p in allpts if p[0] >= x0] + [hl.value for hl in sp.hlines]
        lo = sp.y_min if sp.y_min is not None else min(ys)
        hi = sp.y_max if sp.y_max is not None else max(ys)
        if hi - lo < 1e-9:
            lo, hi = lo - 1, hi + 1
        pad = (hi - lo) * 0.08
        if sp.y_min is None:
            lo -= pad
        if sp.y_max is None:
            hi += pad

        def X(x: float) -> float:
            return ml + (x - x0) / (x1 - x0) * pw

        def Y(y: float) -> float:
            return mt + (hi - y) / (hi - lo) * ph

        self.create_rectangle(ml, mt, ml + pw, mt + ph, outline=GRID, fill="#fafafa")
        if sp.shade_until is not None and sp.shade_until > x0:
            self.create_rectangle(ml, mt, min(X(sp.shade_until), ml + pw), mt + ph,
                                  outline="", fill=PHASE1)
            self.create_text(ml + 4, mt + 2, anchor="nw", text="Fase I", fill=MUTED,
                             font=("TkDefaultFont", 8))
        for t in nice_ticks(lo, hi):
            self.create_line(ml, Y(t), ml + pw, Y(t), fill=GRID)
            self.create_text(ml - 4, Y(t), anchor="e", text=fmt_num(t), fill=MUTED,
                             font=("TkDefaultFont", 8))
        for k in range(5):
            xv = x0 + (x1 - x0) * k / 4
            self.create_text(X(xv), h - 4, anchor="se" if k == 4 else "s", text=sp.xfmt(xv),
                             fill=MUTED, font=("TkDefaultFont", 8))
        for xv, color in sp.vlines:
            if x0 <= xv <= x1:
                self.create_line(X(xv), mt, X(xv), mt + ph, fill=color, width=2)
        for hl in sp.hlines:
            if lo <= hl.value <= hi:
                opts: dict[str, object] = {"dash": hl.dash} if hl.dash else {}
                self.create_line(ml, Y(hl.value), ml + pw, Y(hl.value), fill=hl.color, width=1,
                                 **opts)  # type: ignore[arg-type]
                if hl.label:
                    self.create_text(ml + pw - 2, Y(hl.value) - 1, anchor="se", text=hl.label,
                                     fill=hl.color, font=("TkDefaultFont", 8))
        legend_x = ml
        for i, (name, pts) in enumerate(sp.series.items()):
            color = PALETTE[i % len(PALETTE)]
            vis = [(X(x), Y(y)) for x, y in pts if x0 <= x <= x1]
            if len(vis) > 1:
                self.create_line(*[c for p in vis for c in p], fill=color, width=1.6)
            elif len(vis) == 1:
                self.create_oval(vis[0][0] - 2, vis[0][1] - 2, vis[0][0] + 2, vis[0][1] + 2,
                                 fill=color, outline=color)
            if pts:
                last = pts[-1][1]
                txt = f"{name}: {fmt_num(last)}"
                tid = self.create_text(legend_x, 20, anchor="nw", text=txt, fill=color,
                                       font=("TkDefaultFont", 9))
                bb = self.bbox(tid)
                legend_x = (bb[2] + 14) if bb else legend_x + 90
        for x in sp.markers:
            for pts in sp.series.values():
                near = next((p for p in pts if p[0] == x), None)
                if near:
                    cx, cy = X(near[0]), Y(near[1])
                    self.create_polygon(cx, cy - 7, cx + 5, cy + 3, cx - 5, cy + 3, fill=LIMIT,
                                        outline="")
                    break
