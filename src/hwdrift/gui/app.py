# SPDX-License-Identifier: Apache-2.0
"""Finestra principale di HWDrift: tempo reale, stato, carte, eventi, configurazione, log."""

from __future__ import annotations

import contextlib
import copy
import json
import os
import queue
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import tkinter as tk
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from .. import __version__
from ..config import ConfigError, data_dir, load_config
from ..model import USER_EVENT_KINDS, now_ms
from ..storage.schema import connect, open_db
from . import data
from .widgets import HLine, LineChart, Spec, time_fmt_date, time_fmt_relative

STATUS_COLORS = {"ok": "#1b6e20", "attention": "#8a5a00", "action": "#b3261e",
                 "unknown": "#555555", "error": "#b3261e"}
STATUS_TEXT = {"ok": "OK", "attention": "Attenzione", "action": "Azione",
               "unknown": "Dati insufficienti", "error": "Errore"}
LEVEL_TEXT = {"info": "Info", "attention": "Attenzione", "action": "Azione"}
REASON = {"thermal": "throttling termico", "power_limit": "limite di potenza",
          "fan_stopped": "ventola ferma con temperatura alta"}
WINDOWS_MIN = {"5 minuti": 5, "15 minuti": 15, "30 minuti": 30, "60 minuti": 60}


class App:
    def __init__(self, root: tk.Tk, config_path: Path | None = None, db: Path | None = None,
                 cfg: dict[str, Any] | None = None) -> None:
        self.root = root
        self.config_path = config_path
        self.cfg = cfg if cfg is not None else load_config(config_path)
        self.home = data_dir(self.cfg)
        self.db = db if db is not None else self.home / "hwdrift.sqlite"
        self.demo = False
        self.collector = data.CollectorProcess()
        self.live = data.LiveBuffer()
        self.jobs: queue.Queue[Callable[[], None]] = queue.Queue()
        self.last_live_ts = 0
        self.status: dict[str, Any] | None = None
        self._last_touch = 0.0
        self._charts_cache: list[dict[str, Any]] = []
        root.title(f"HWDrift {__version__} — salute termica di CPU e GPU")
        root.geometry("1240x820")
        root.minsize(900, 600)
        self._build()
        self._backfill()
        self.refresh_slow()
        self.tick_live()
        self.tick_log()
        self.root.after(100, self._pump)
        root.protocol("WM_DELETE_WINDOW", self.close)

    # ----------------------------------------------------------------- helpers
    def conn(self, write: bool = False) -> sqlite3.Connection | None:
        try:
            if write:
                return open_db(self.db)
            if not self.db.exists():
                return None
            return connect(self.db, readonly=True)
        except sqlite3.Error:
            return None

    def background(self, work: Callable[[], Any], done: Callable[[Any, Exception | None], None]
                   ) -> None:
        def run() -> None:
            try:
                res, err = work(), None
            except Exception as exc:
                res, err = None, exc
            self.jobs.put(lambda: done(res, err))
        threading.Thread(target=run, daemon=True).start()

    def _pump(self) -> None:
        while True:
            try:
                self.jobs.get_nowait()()
            except queue.Empty:
                break
        self.root.after(150, self._pump)

    def notice(self, text: str) -> None:
        self.notice_var.set(text)

    # ------------------------------------------------------------------- build
    def _build(self) -> None:
        top = ttk.Frame(self.root, padding=(8, 6))
        top.pack(fill="x")
        self.coll_var = tk.StringVar(value="Collector: …")
        ttk.Label(top, textvariable=self.coll_var, font=("TkDefaultFont", 10, "bold")).pack(
            side="left")
        self.demo_var = tk.StringVar()
        ttk.Label(top, textvariable=self.demo_var, foreground="#b3261e").pack(side="left", padx=8)
        for text, cmd in (("Demo (dati simulati)", self.start_demo),
                          ("■ Ferma", self.stop_collector),
                          ("▶ Avvia collector", self.start_collector)):
            ttk.Button(top, text=text, command=cmd).pack(side="right", padx=2)
        if sys.platform == "win32":
            ttk.Button(top, text="▶ Avvia come amministratore",
                       command=self.start_elevated).pack(side="right", padx=2)
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self._tab_live()
        self._tab_status()
        self._tab_charts()
        self._tab_events()
        self._tab_config()
        self._tab_log()
        bar = ttk.Frame(self.root, padding=(8, 2))
        bar.pack(fill="x")
        self.notice_var = tk.StringVar(value="")
        ttk.Label(bar, textvariable=self.notice_var).pack(side="left")
        self.db_var = tk.StringVar(value=f"Database: {self.db}")
        ttk.Label(bar, textvariable=self.db_var, foreground="#555555").pack(side="right")

    # tab: tempo reale ------------------------------------------------------
    def _tab_live(self) -> None:
        f = ttk.Frame(self.nb, padding=6)
        self.nb.add(f, text="Tempo reale")
        head = ttk.Frame(f)
        head.pack(fill="x")
        self.kpi_vars: dict[str, tk.StringVar] = {}
        for i, (label, ch, _unit) in enumerate(data.KPI):
            box = ttk.LabelFrame(head, text=label)
            box.grid(row=0, column=i, padx=3, sticky="ew")
            head.columnconfigure(i, weight=1)
            v = tk.StringVar(value="—")
            self.kpi_vars[ch] = v
            ttk.Label(box, textvariable=v, font=("TkDefaultFont", 15, "bold"), width=9,
                      anchor="center").pack(padx=6, pady=(2, 0))
            ttk.Label(box, text=_unit, foreground="#555555", font=("TkDefaultFont", 8)).pack()
        self.ongoing_var = tk.StringVar()
        ttk.Label(f, textvariable=self.ongoing_var, foreground="#b3261e",
                  font=("TkDefaultFont", 10, "bold")).pack(fill="x", pady=(4, 0))
        ctl = ttk.Frame(f)
        ctl.pack(fill="x", pady=2)
        ttk.Label(ctl, text="Finestra:").pack(side="left")
        self.win_var = tk.StringVar(value="15 minuti")
        cb = ttk.Combobox(ctl, textvariable=self.win_var, values=list(WINDOWS_MIN), width=12,
                          state="readonly")
        cb.pack(side="left", padx=4)
        cb.bind("<<ComboboxSelected>>", lambda _e: self._draw_live())
        self.live_msg = tk.StringVar()
        ttk.Label(ctl, textvariable=self.live_msg, foreground="#555555").pack(side="left", padx=8)
        grid = ttk.Frame(f)
        grid.pack(fill="both", expand=True)
        self.live_charts: list[LineChart] = []
        for i, (title, unit, _series) in enumerate(data.LIVE_CHARTS):
            ch = LineChart(grid, title, unit)
            ch.grid(row=i // 2, column=i % 2, sticky="nsew", padx=2, pady=2)
            self.live_charts.append(ch)
        for c in range(2):
            grid.columnconfigure(c, weight=1)
        for r in range((len(data.LIVE_CHARTS) + 1) // 2):
            grid.rowconfigure(r, weight=1)

    # tab: stato --------------------------------------------------------------
    def _tab_status(self) -> None:
        f = ttk.Frame(self.nb, padding=6)
        self.nb.add(f, text="Stato e ipotesi")
        bar = ttk.Frame(f)
        bar.pack(fill="x")
        ttk.Button(bar, text="Analizza ora", command=self.analyze_now).pack(side="left")
        ttk.Button(bar, text="Aggiorna", command=self.refresh_slow).pack(side="left", padx=4)
        ttk.Button(bar, text="Apri il report HTML", command=self.open_report).pack(side="left")
        self.tiles = ttk.Frame(f)
        self.tiles.pack(fill="x", pady=6)
        ttk.Label(f, text="Allarmi attivi", font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        cols = ("level", "title", "message")
        self.alert_tree = ttk.Treeview(f, columns=cols, show="headings", height=6)
        for c, t, w in (("level", "Livello", 90), ("title", "Titolo", 260), ("message",
                                                                                 "Dettaglio", 760)):
            self.alert_tree.heading(c, text=t)
            self.alert_tree.column(c, width=w, anchor="w")
        self.alert_tree.pack(fill="x")
        ttk.Label(f, text="Ipotesi di manutenzione (confidenza qualitativa, da verificare)",
                  font=("TkDefaultFont", 10, "bold")).pack(anchor="w", pady=(8, 0))
        self.diag_text = tk.Text(f, height=10, wrap="word", state="disabled", bg="#fafafa")
        self.diag_text.pack(fill="both", expand=True)
        ttk.Label(f, text="Non è un avviso di sicurezza né una diagnosi di guasto. In caso di "
                          "temperature elevate o spegnimenti non attendere il tool: intervieni.",
                  foreground="#555555", wraplength=1100).pack(anchor="w", pady=2)

    # tab: carte --------------------------------------------------------------
    def _tab_charts(self) -> None:
        f = ttk.Frame(self.nb, padding=6)
        self.nb.add(f, text="Carte di controllo")
        bar = ttk.Frame(f)
        bar.pack(fill="x")
        ttk.Label(bar, text="Carta:").pack(side="left")
        self.chart_var = tk.StringVar()
        self.chart_cb = ttk.Combobox(bar, textvariable=self.chart_var, width=58,
                                     state="readonly")
        self.chart_cb.pack(side="left", padx=4)
        self.chart_cb.bind("<<ComboboxSelected>>", lambda _e: self.draw_control_chart())
        ttk.Button(bar, text="Ricarica", command=self.refresh_slow).pack(side="left")
        self.chart_info = tk.StringVar()
        ttk.Label(f, textvariable=self.chart_info, foreground="#444444", wraplength=1150,
                  justify="left").pack(fill="x", pady=4)
        self.chart_i = LineChart(f, "Carta I", height=300)
        self.chart_i.pack(fill="both", expand=True)
        self.chart_mr = LineChart(f, "Range mobili (MR)", height=150)
        self.chart_mr.pack(fill="x", pady=(4, 0))
        ttk.Label(f, text="Linea rossa = limiti a 3σ; arancio tratteggiato = 2σ; grigia = linea "
                          "centrale; triangoli = segnali; zona azzurra = Fase I.",
                  foreground="#555555").pack(anchor="w")

    # tab: eventi -------------------------------------------------------------
    def _tab_events(self) -> None:
        f = ttk.Frame(self.nb, padding=6)
        self.nb.add(f, text="Eventi e manutenzioni")
        form = ttk.LabelFrame(f, text="Registra una manutenzione o un evento", padding=6)
        form.pack(fill="x")
        ttk.Label(form, text="Tipo").grid(row=0, column=0, sticky="w")
        self.ev_kind = tk.StringVar(value="maintenance.clean")
        ttk.Combobox(form, textvariable=self.ev_kind, values=list(USER_EVENT_KINDS), width=26,
                     state="readonly").grid(row=0, column=1, padx=4)
        ttk.Label(form, text="Data/ora (vuoto = adesso, formato 2026-09-30 18:30)").grid(
            row=0, column=2, padx=(12, 0))
        self.ev_when = tk.StringVar()
        ttk.Entry(form, textvariable=self.ev_when, width=20).grid(row=0, column=3, padx=4)
        ttk.Label(form, text="Nota").grid(row=1, column=0, sticky="w")
        self.ev_note = tk.StringVar()
        ttk.Entry(form, textvariable=self.ev_note, width=70).grid(row=1, column=1, columnspan=3,
                                                                  sticky="w", padx=4, pady=4)
        ttk.Button(form, text="Registra", command=self.add_event).grid(row=1, column=4)
        ttk.Label(f, text="Una manutenzione chiude il segmento delle carte e avvia una nuova "
                          "Fase I; il report mostra quanto l'indicatore è tornato al baseline.",
                  foreground="#555555").pack(anchor="w", pady=4)
        cols = ("ts", "kind", "source", "note")
        self.ev_tree = ttk.Treeview(f, columns=cols, show="headings")
        for c, t, w in (("ts", "Data", 150), ("kind", "Tipo", 190), ("source", "Origine", 80),
                        ("note", "Nota / dettaglio", 700)):
            self.ev_tree.heading(c, text=t)
            self.ev_tree.column(c, width=w, anchor="w")
        self.ev_tree.pack(fill="both", expand=True)

    # tab: configurazione -----------------------------------------------------
    def _tab_config(self) -> None:
        f = ttk.Frame(self.nb, padding=6)
        self.nb.add(f, text="Configurazione")
        sub = ttk.Notebook(f)
        sub.pack(fill="both", expand=True)
        form_tab = ttk.Frame(sub, padding=6)
        yaml_tab = ttk.Frame(sub, padding=6)
        sub.add(form_tab, text="Impostazioni")
        sub.add(yaml_tab, text="YAML avanzato")
        inner = ttk.Frame(form_tab)
        inner.pack(fill="both", expand=True)
        inner.columnconfigure(0, weight=1)
        inner.columnconfigure(1, weight=1)
        self.cfg_vars: dict[str, tk.Variable] = {}
        for g, (group, fields) in enumerate(data.CONFIG_FIELDS):
            box = ttk.LabelFrame(inner, text=group, padding=6)
            box.grid(row=g // 2, column=g % 2, sticky="nsew", padx=4, pady=4)
            box.columnconfigure(1, weight=1)
            r = 0
            for fd in fields:
                if fd.kind == "bool":
                    var: tk.Variable = tk.BooleanVar()
                    ttk.Checkbutton(box, text=fd.label, variable=var).grid(
                        row=r, column=0, columnspan=2, sticky="w")
                else:
                    var = tk.StringVar()
                    ttk.Label(box, text=fd.label).grid(row=r, column=0, sticky="w", padx=(0, 8))
                    if fd.kind == "choice":
                        ttk.Combobox(box, textvariable=var, values=list(fd.choices), width=18,
                                     state="readonly").grid(row=r, column=1, sticky="ew")
                    else:
                        ttk.Entry(box, textvariable=var, width=30).grid(row=r, column=1,
                                                                        sticky="ew")
                r += 1
                if fd.help:
                    ttk.Label(box, text=fd.help, foreground="#666666", wraplength=520).grid(
                        row=r, column=0, columnspan=2, sticky="w")
                    r += 1
                self.cfg_vars[fd.key] = var
        bar = ttk.Frame(form_tab)
        bar.pack(side="bottom", fill="x", pady=4)
        ttk.Button(bar, text="Salva configurazione", command=self.save_form).pack(side="left")
        ttk.Button(bar, text="Ricarica dal file", command=self.load_config_into_form).pack(
            side="left", padx=4)
        self.cfg_path_var = tk.StringVar()
        ttk.Label(bar, textvariable=self.cfg_path_var, foreground="#555555").pack(side="left",
                                                                                   padx=8)
        ttk.Label(yaml_tab, text="Modifica diretta del file. Viene validato prima del "
                                 "salvataggio; una copia .bak del file precedente resta accanto.",
                  foreground="#555555").pack(anchor="w")
        self.yaml_text = tk.Text(yaml_tab, wrap="none", font=("TkFixedFont", 10))
        self.yaml_text.pack(fill="both", expand=True)
        yb = ttk.Frame(yaml_tab)
        yb.pack(fill="x", pady=4)
        ttk.Button(yb, text="Valida e salva", command=self.save_yaml).pack(side="left")
        ttk.Button(yb, text="Inserisci la configurazione di esempio",
                   command=self.insert_example).pack(side="left", padx=4)
        ttk.Label(f, text="Le modifiche hanno effetto al prossimo avvio del collector. Per un "
                          "collector con privilegi elevati usa un file di configurazione in una "
                          "cartella protetta (vedi SECURITY.md).", foreground="#555555",
                  wraplength=1150).pack(anchor="w", pady=2)
        self.load_config_into_form()

    # tab: log e dati ---------------------------------------------------------
    def _tab_log(self) -> None:
        f = ttk.Frame(self.nb, padding=6)
        self.nb.add(f, text="Log e dati")
        bar = ttk.Frame(f)
        bar.pack(fill="x")
        for text, cmd in (("Salva log…", self.save_log), ("Pacchetto diagnostico (.zip)…",
                                                           self.save_bundle),
                          ("Salva report HTML…", self.save_report),
                          ("Apri cartella dati", self.open_folder)):
            ttk.Button(bar, text=text, command=cmd).pack(side="left", padx=2)
        ex = ttk.LabelFrame(f, text="Esporta i dati", padding=6)
        ex.pack(fill="x", pady=6)
        self.exp_fmt = tk.StringVar(value="csv")
        ttk.Combobox(ex, textvariable=self.exp_fmt, width=12, state="readonly",
                     values=["csv", "jsonl", "parquet", "prometheus", "otlp"]).pack(side="left")
        self.exp_anon = tk.BooleanVar(value=True)
        ttk.Checkbutton(ex, text="Anonimo (senza note, nomi grezzi, percorsi)",
                        variable=self.exp_anon).pack(side="left", padx=8)
        ttk.Button(ex, text="Esporta in…", command=self.export_data).pack(side="left")
        self.log_text = tk.Text(f, wrap="none", font=("TkFixedFont", 9), state="disabled",
                                bg="#fafafa")
        ys = ttk.Scrollbar(f, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=ys.set)
        ys.pack(side="right", fill="y")
        self.log_text.pack(fill="both", expand=True)

    # ============================================================== timers/update
    def _backfill(self) -> None:
        conn = self.conn()
        if conn is None:
            return
        with contextlib.closing(conn):
            self.live.backfill(conn, data.ALL_LIVE_CHANNELS, now_ms() - 3600 * 1000)

    def tick_live(self) -> None:
        live_active = self.home / "live.active"
        now = time.time()
        if now - self._last_touch > 2:  # dice al collector di pubblicare i valori
            with contextlib.suppress(OSError):
                live_active.write_text(str(int(now)), encoding="utf-8")
            self._last_touch = now
        snap = data.read_live(self.home / "live.json")
        if snap is not None and snap[0] != self.last_live_ts:
            self.last_live_ts = snap[0]
            self.live.push(snap[0], snap[1])
        self._draw_live(fresh=snap is not None)
        self.root.after(1000, self.tick_live)

    def _draw_live(self, fresh: bool | None = None) -> None:
        if fresh is None:
            fresh = (now_ms() - self.last_live_ts) < 5000
        minutes = WINDOWS_MIN.get(self.win_var.get(), 15)
        now = now_ms()
        since = now - minutes * 60_000
        for ch, var in self.kpi_vars.items():
            v = self.live.latest(ch) if fresh else None
            var.set("—" if v is None else f"{v:.0f}" if abs(v) >= 100 else f"{v:.1f}")
        for chart, (_t, _u, series) in zip(self.live_charts, data.LIVE_CHARTS, strict=True):
            sp = Spec(x0=since, x1=now, xfmt=time_fmt_relative(now),
                      empty_text="nessun dato (canale non disponibile su questo PC)")
            for ch, label in series:
                pts = self.live.series(ch, since)
                if pts:
                    sp.series[label] = pts
            chart.set(sp)
        if fresh:
            self.live_msg.set("Aggiornamento in tempo reale (1 s)")
        elif self.last_live_ts == 0:
            self.live_msg.set("In attesa del collector… avvialo con il pulsante in alto "
                              "(i grafici mostrano intanto la storia recente dal database).")
        else:
            self.live_msg.set("Collector non in esecuzione: grafici fermi all'ultimo dato.")

    def refresh_slow(self) -> None:
        conn = self.conn()
        if conn is None:
            self.coll_var.set("Collector: nessun database (avvia il collector o la demo)")
            self._schedule_slow()
            return
        with contextlib.closing(conn):
            try:
                st = data.collect_status(conn, self.cfg)
                charts = data.list_charts(conn)
                events = data.list_events(conn)
            except sqlite3.Error as exc:
                self.notice(f"Database non leggibile: {exc}")
                self._schedule_slow()
                return
        self.status = st
        self._charts_cache = charts
        self._render_status(st)
        self._render_charts_list(charts)
        self._render_events(events)
        self._schedule_slow()

    def _schedule_slow(self) -> None:
        if getattr(self, "_slow_after", None):
            self.root.after_cancel(self._slow_after)
        self._slow_after = self.root.after(10_000, self.refresh_slow)

    def _render_status(self, st: dict[str, Any]) -> None:
        h = st["health"]
        if h.heartbeat_ts is None:
            state = "mai avviato"
        elif h.stale_min:
            state = f"fermo da {h.stale_min:.0f} minuti"
        else:
            state = "attivo"
        alive = " (avviato da questa finestra)" if self.collector.alive() else ""
        fails = f" — sorgenti in errore: {', '.join(h.failing_collectors)}" \
            if h.failing_collectors else ""
        self.coll_var.set(f"Collector: {state}{alive}{fails}")
        self.demo_var.set("MODALITÀ DEMO — dati simulati" if self.demo else "")
        ongoing = [r for r in st["rt"] if r["end_ts"] is None]
        self.ongoing_var.set("⚠ EPISODIO IN CORSO: " + "; ".join(
            f"{r['component'].upper()} {REASON.get(r['reason'], r['reason'])}" for r in ongoing)
                             if ongoing else "")
        for w in self.tiles.winfo_children():
            w.destroy()
        for i, t in enumerate(st["tiles"]):
            box = tk.Frame(self.tiles, bd=1, relief="solid", padx=8, pady=4)
            box.grid(row=0, column=i, padx=4, sticky="nsew")
            self.tiles.columnconfigure(i, weight=1)
            color = STATUS_COLORS[t["status"]]
            tk.Label(box, text=t["label"], font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
            tk.Label(box, text="● " + STATUS_TEXT[t["status"]], fg=color,
                     font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
            tk.Label(box, text=t["reason"], wraplength=260, justify="left").pack(anchor="w")
        self.alert_tree.delete(*self.alert_tree.get_children())
        for a in st["alerts"]:
            self.alert_tree.insert("", "end", values=(LEVEL_TEXT[a["level"]], a["title"],
                                                      a["message"]))
        self.diag_text.configure(state="normal")
        self.diag_text.delete("1.0", "end")
        if not st["diagnoses"]:
            self.diag_text.insert("end", "Nessuna ipotesi di manutenzione attiva.\n")
        for d in st["diagnoses"]:
            self.diag_text.insert("end", f"{d['title']}  [{LEVEL_TEXT[d['level']]} · confidenza "
                                         f"{d['confidence']}]\n")
            for s in d["supports"]:
                self.diag_text.insert("end", f"   + {s}\n")
            for s in d["contradicts"]:
                self.diag_text.insert("end", f"   − contrario: {s}\n")
            for i, a in enumerate(d["actions"], 1):
                self.diag_text.insert("end", f"   {i}. {a}\n")
            self.diag_text.insert("end", "\n")
        self.diag_text.configure(state="disabled")

    def _render_charts_list(self, charts: list[dict[str, Any]]) -> None:
        labels = []
        for c in charts:
            st = ("Fase I" if c["phase"] == "I" else "provvisoria" if c["provisional"]
                  else "definitiva")
            labels.append(f"{c['indicator']} · {c['regime']} · {c['level']} ({st})")
        self._chart_labels = labels
        self.chart_cb.configure(values=labels)
        if labels and self.chart_var.get() not in labels:
            pref = next((i for i, c in enumerate(charts) if c["indicator"].startswith("rth_")
                         and c["level"] == "window"), 0)
            self.chart_var.set(labels[pref])
        self.draw_control_chart()

    def draw_control_chart(self) -> None:
        label = self.chart_var.get()
        if not label or label not in getattr(self, "_chart_labels", []):
            self.chart_i.set(Spec(empty_text="nessuna carta: serve qualche giorno di raccolta e "
                                             "un'analisi (scheda «Stato e ipotesi»)"))
            self.chart_mr.set(Spec(empty_text=""))
            self.chart_info.set("")
            return
        st = self._charts_cache[self._chart_labels.index(label)]
        conn = self.conn()
        if conn is None:
            return
        with contextlib.closing(conn):
            cs = data.chart_series(conn, st)
            events = [(r[0], r[1]) for r in conn.execute(
                "SELECT ts, kind FROM events WHERE ts>=? AND (kind LIKE 'maintenance.%' OR kind "
                "LIKE 'config.%')", (st["start_ts"],))]
        ts, vals = cs["ts"], cs["values"]
        unit = data_unit(st["indicator"])
        self.chart_i.title, self.chart_i.unit = f"{st['indicator']} — {st['regime']}", unit
        sp = Spec(series={"valore": list(zip(ts, vals, strict=True))}, xfmt=time_fmt_date,
                  shade_until=st["locked_ts"],
                  empty_text="copertura insufficiente: nessuna osservazione")
        c, s = st["center"], st["sigma"]
        if c is not None and s is not None:
            w = st["params"].get("widen", 1.0)
            sp.hlines = [HLine(c, "#444444", (2, 3), "LC"), HLine(st["ucl"], "#b3261e", (),
                                                                  "UCL"),
                         HLine(st["lcl"], "#b3261e", (), "LCL"),
                         HLine(c + 2 * s * w, "#b45309", (4, 3)),
                         HLine(c - 2 * s * w, "#b45309", (4, 3))]
        sp.markers = {t: txt for t, txt in cs["signals"].items() if t in set(ts)}
        sp.vlines = [(t, "#1b6e20" if k.startswith("maintenance") else "#b45309")
                     for t, k in events]
        self.chart_i.set(sp)
        mr = [(ts[i], abs(vals[i] - vals[i - 1])) for i in range(1, len(vals))]
        sm = Spec(series={"MR": mr}, xfmt=time_fmt_date, empty_text="")
        if st["ucl_mr"]:
            sm.hlines = [HLine(st["ucl_mr"], "#b3261e", (), "UCL MR")]
        self.chart_mr.set(sm)
        status = ("copertura insufficiente" if st["params"].get("status") == "insufficient"
                  else "Fase I in corso (limiti provvisori)" if st["phase"] == "I"
                  else "limiti provvisori" if st["provisional"] else "limiti definitivi")
        sig_txt = "; ".join(f"{datetime.fromtimestamp(t / 1000):%d/%m %H:%M} {x}"
                            for t, x in list(cs["signals"].items())[-5:])
        self.chart_info.set(f"{status} · {len(vals)} osservazioni · segmento {st['segment']}"
                            + (f" · ultimi segnali: {sig_txt}" if sig_txt else ""))

    def _render_events(self, events: list[sqlite3.Row]) -> None:
        self.ev_tree.delete(*self.ev_tree.get_children())
        for e in events:
            when = datetime.fromtimestamp(e["ts"] / 1000).strftime("%Y-%m-%d %H:%M")
            detail = e["note"] or ("" if e["detail"] in ("{}", "", None) else e["detail"])
            self.ev_tree.insert("", "end", values=(when, e["kind"], e["source"], detail))

    def tick_log(self) -> None:
        text = data.tail(self.home / "hwdrift.log")
        cur = self.log_text.get("1.0", "end-1c")
        if text and text != cur:
            self.log_text.configure(state="normal")
            self.log_text.delete("1.0", "end")
            self.log_text.insert("end", text)
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self.root.after(3000, self.tick_log)

    # =================================================================== azioni
    def add_event(self) -> None:
        from ..context.events import add_user_event

        when = self.ev_when.get().strip()
        try:
            ts = int(datetime.fromisoformat(when).astimezone().timestamp() * 1000) if when \
                else now_ms()
        except ValueError:
            messagebox.showerror("Data non valida", "Usa il formato 2026-09-30 oppure "
                                                    "2026-09-30 18:30")
            return
        conn = self.conn(write=True)
        if conn is None:
            messagebox.showerror("Database", "Impossibile aprire il database.")
            return
        with contextlib.closing(conn):
            add_user_event(conn, self.ev_kind.get(), ts, self.ev_note.get())
        self.ev_note.set("")
        self.notice(f"Evento registrato: {self.ev_kind.get()}")
        self.refresh_slow()

    def analyze_now(self) -> None:
        from ..analysis.worker import run_analysis
        from ..reporting.html_report import write_report

        self.notice("Analisi in corso…")
        cfg, db, home = self.cfg, self.db, self.home

        def work() -> dict[str, Any]:
            conn = open_db(db)
            try:
                s = run_analysis(conn, cfg, low_priority=False)
                write_report(conn, cfg, home / "report.html")
                return s
            finally:
                conn.close()

        def done(res: Any, err: Exception | None) -> None:
            if err is not None:
                self.notice(f"Analisi fallita: {err}")
                messagebox.showerror("Analisi", str(err))
                return
            self.notice(f"Analisi completata in {res['duration_s']} s: {res['windows_new']} nuove "
                        f"finestre, {res['signals_new']} nuovi segnali.")
            self.refresh_slow()

        self.background(work, done)

    def open_report(self) -> None:
        p = self.home / "report.html"
        if not p.exists():
            self.notice("Nessun report: premi prima «Analizza ora».")
            return
        import webbrowser

        webbrowser.open(p.as_uri())

    def _collector_args(self, extra: list[str]) -> list[str]:
        args = ["--db", str(self.db)]
        if self.config_path is not None:
            args = ["--config", str(self.config_path), *args]
        return [*args, "run", *extra]

    def start_collector(self) -> None:
        if self.collector.alive():
            self.notice("Il collector è già in esecuzione.")
            return
        env = {"HWDRIFT_HOME": str(self.home)}
        self.collector.start(self._collector_args([]), env)
        self.notice("Collector avviato senza privilegi elevati: i sensori a basso livello "
                    "possono mancare. Per tutti i sensori usa «Avvia come amministratore».")
        self.root.after(2500, self.refresh_slow)

    def start_elevated(self) -> None:
        ok = self.collector.start_elevated(self._collector_args([]))
        self.notice("Richiesta di elevazione inviata (UAC)." if ok
                    else "Elevazione annullata o non disponibile.")
        self.root.after(4000, self.refresh_slow)

    def stop_collector(self) -> None:
        self.notice("Arresto del collector…")
        def done(_r: Any, _e: Exception | None) -> None:
            self.notice("Richiesta di arresto inviata.")
            self.refresh_slow()

        self.background(lambda: self.collector.stop(self.home), done)

    def start_demo(self) -> None:
        """Dati simulati in una cartella separata: 30 giorni di storia con polvere + collector
        simulato in tempo reale. Non tocca il database reale."""
        if self.collector.alive():
            messagebox.showinfo("Demo", "Ferma prima il collector in esecuzione.")
            return
        from ..analysis.worker import run_analysis
        from ..sim.generator import generate

        home = self.home.parent / "demo" if self.home.name != "demo" else self.home
        home.mkdir(parents=True, exist_ok=True)
        db = home / "demo.sqlite"
        self.notice("Preparazione della demo (30 giorni simulati)…")

        def work() -> None:
            conn = open_db(db)
            try:
                if conn.execute("SELECT COUNT(*) FROM agg_1min").fetchone()[0] == 0:
                    generate(conn, "dust", days=30, seed=3, dt_s=60.0,
                             start_ms=now_ms() - 30 * 86_400_000)
                    run_analysis(conn, self.cfg, low_priority=False)
            finally:
                conn.close()

        def done(_r: Any, err: Exception | None) -> None:
            if err is not None:
                self.notice(f"Demo fallita: {err}")
                return
            self.switch_to(home, db, demo=True)
            self.collector.start(["--db", str(db), "run", "--simulate", "healthy"],
                                 {"HWDRIFT_HOME": str(home)})
            self.notice("Demo in corso: storia simulata con accumulo di polvere + tempo reale "
                        "simulato.")

        self.background(work, done)

    def switch_to(self, home: Path, db: Path, demo: bool) -> None:
        self.home, self.db, self.demo = home, db, demo
        self.live = data.LiveBuffer()
        self.last_live_ts = 0
        self.db_var.set(f"Database: {db}")
        self._backfill()
        self.refresh_slow()

    # configurazione ----------------------------------------------------------
    def _cfg_file(self) -> Path:
        return self.config_path if self.config_path is not None else self.home / "hwdrift.yaml"

    def load_config_into_form(self) -> None:
        path = self._cfg_file()
        try:
            cfg = load_config(path) if path.exists() else load_config(None)
        except ConfigError as exc:
            messagebox.showerror("Configurazione", str(exc))
            return
        for fd in data.ALL_FIELDS:
            val = data.get_path(cfg, fd.key)
            var = self.cfg_vars[fd.key]
            if fd.kind == "bool":
                var.set(bool(val))
            elif fd.kind == "list":
                var.set(", ".join(val))
            else:
                var.set("" if val is None else str(val))
        self.cfg_path_var.set(f"File: {path}" + ("" if path.exists() else " (verrà creato)"))
        self.yaml_text.delete("1.0", "end")
        self.yaml_text.insert("end", path.read_text(encoding="utf-8") if path.exists()
                              else "# nessun file di configurazione: si usano i valori "
                                   "predefiniti\n")

    def save_form(self) -> None:
        try:
            changes = {fd.key: data.parse_field(fd, self.cfg_vars[fd.key].get())
                       for fd in data.ALL_FIELDS}
            cfg = data.save_config(self._cfg_file(), changes)
        except (ValueError, ConfigError) as exc:
            messagebox.showerror("Configurazione non valida", str(exc))
            return
        self.cfg = cfg
        self.load_config_into_form()
        self.notice("Configurazione salvata. Riavvia il collector per applicarla.")

    def save_yaml(self) -> None:
        try:
            cfg = data.save_config(self._cfg_file(), raw_text=self.yaml_text.get("1.0", "end"))
        except (ValueError, ConfigError) as exc:
            messagebox.showerror("YAML non valido", str(exc))
            return
        self.cfg = cfg
        self.load_config_into_form()
        self.notice("Configurazione salvata. Riavvia il collector per applicarla.")

    def insert_example(self) -> None:
        from importlib import resources

        self.yaml_text.delete("1.0", "end")
        self.yaml_text.insert("end", resources.files("hwdrift").joinpath(
            "hwdrift.example.yaml").read_text(encoding="utf-8"))

    # log, export, cartelle -----------------------------------------------------
    def save_log(self) -> None:
        src = self.home / "hwdrift.log"
        if not src.exists():
            messagebox.showinfo("Log", "Nessun file di log ancora.")
            return
        dst = filedialog.asksaveasfilename(defaultextension=".log",
                                           initialfile=f"hwdrift-{datetime.now():%Y%m%d-%H%M}.log")
        if dst:
            shutil.copyfile(src, dst)
            self.notice(f"Log salvato in {dst}")

    def save_bundle(self) -> None:
        dst = filedialog.asksaveasfilename(defaultextension=".zip", initialfile=(
            f"hwdrift-diagnostica-{datetime.now():%Y%m%d-%H%M}.zip"))
        if not dst:
            return
        names = data.make_bundle(Path(dst), self.home, self.db,
                                 self.config_path if self.config_path else self._cfg_file())
        self.notice(f"Pacchetto diagnostico salvato ({', '.join(names)}). Non contiene il "
                    "database né i dati grezzi.")

    def save_report(self) -> None:
        from ..reporting.html_report import write_report

        dst = filedialog.asksaveasfilename(defaultextension=".html", initialfile="hwdrift-report"
                                                                                 ".html")
        if not dst:
            return
        conn = self.conn()
        if conn is None:
            messagebox.showinfo("Report", "Nessun database.")
            return
        with contextlib.closing(conn):
            write_report(conn, self.cfg, Path(dst))
        self.notice(f"Report salvato in {dst}")

    def export_data(self) -> None:
        from ..storage import export as ex

        folder = filedialog.askdirectory(title="Cartella di destinazione")
        if not folder:
            return
        fmt, anon, out, db = self.exp_fmt.get(), self.exp_anon.get(), Path(folder), self.db
        self.notice("Esportazione in corso…")

        def work() -> list[Path]:
            conn = connect(db, readonly=True)
            try:
                if fmt == "csv":
                    return ex.export_csv(conn, out, anon)
                if fmt == "jsonl":
                    return ex.export_jsonl(conn, out, anon)
                if fmt == "parquet":
                    return ex.export_parquet(conn, out, anon)
                if fmt == "prometheus":
                    p = out / "hwdrift.prom"
                    p.write_text(ex.prometheus_text(conn), encoding="utf-8")
                    return [p]
                p = out / "hwdrift-otlp.json"
                p.write_text(json.dumps(ex.otlp_json(conn), indent=1), encoding="utf-8")
                return [p]
            finally:
                conn.close()

        def done(res: Any, err: Exception | None) -> None:
            if err is not None:
                self.notice(f"Esportazione fallita: {err}")
                messagebox.showerror("Esportazione", str(err))
            else:
                self.notice(f"Esportati {len(res)} file in {out}")

        self.background(work, done)

    def open_folder(self) -> None:
        if sys.platform == "win32":
            os.startfile(self.home)  # type: ignore[attr-defined]  # noqa: S606
        else:
            with contextlib.suppress(OSError):
                subprocess.Popen(["xdg-open", str(self.home)])

    # chiusura ------------------------------------------------------------------
    def close(self) -> None:
        with contextlib.suppress(OSError):
            (self.home / "live.active").unlink()
        if self.collector.alive() and messagebox.askyesno(
                "Collector", "Il collector avviato da questa finestra è ancora in esecuzione. "
                             "Fermarlo?"):
            self.collector.stop(self.home)
        self.root.destroy()


def data_unit(indicator: str) -> str:
    from ..indicators.definitions import definition

    d = definition(indicator)
    return d.unit if d else ""


def run_gui(config_path: Path | None = None, db: Path | None = None) -> None:
    root = tk.Tk()
    ttk.Style(root).theme_use("clam" if "clam" in ttk.Style(root).theme_names() else "default")
    App(root, config_path, db, copy.deepcopy(load_config(config_path)))
    root.mainloop()

