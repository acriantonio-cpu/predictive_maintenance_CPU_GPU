# SPDX-License-Identifier: Apache-2.0
"""Report HTML autonomo (``hwdrift report``), apribile senza rete (sezione 9).

Viste: stato generale, errori immediati, ipotesi, allarmi, carte I e MR con eventi
sovrapposti, copertura e qualità dei dati, efficacia della manutenzione, overhead.

Principi di accessibilità (WCAG): lingua dichiarata, gerarchia dei titoli, link
"salta al contenuto", tabelle con intestazioni, grafici con titolo/descrizione e
tabella dati equivalente, stato espresso a parole oltre che con il colore,
contrasto adeguato in tema chiaro e scuro, nessuno script.
"""

from __future__ import annotations

import html
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from .. import __version__
from ..context.events import describe
from ..indicators.definitions import SECONDARY_BASES, caption, definition, split
from ..quality import watchdog
from ..spc.imr import moving_ranges
from ..storage.schema import get_meta
from .svg import Lines, Series, chart

DAY_MS = 86_400_000
MAX_POINTS = 600
E = html.escape

STATUS_TEXT = {"ok": "OK", "attention": "Attenzione", "action": "Azione",
               "unknown": "Dati insufficienti", "error": "Errore"}
LEVEL_TEXT = {"info": "Info", "attention": "Attenzione", "action": "Azione"}
SEV_TEXT = {"info": "Info", "warning": "Attenzione", "error": "Errore immediato"}
REASON_TEXT = {"thermal": "throttling termico", "power_limit": "limite di potenza",
               "fan_stopped": "ventola ferma con temperatura alta"}
RULE_TEXT = {"R1": "punto oltre 3σ", "R2": "9 punti dallo stesso lato",
             "R3": "6 punti in salita/discesa", "R4": "2 su 3 oltre 2σ",
             "MR": "salto (range mobile)", "EWMA": "EWMA", "CUSUM": "CUSUM",
             "MK": "trend Mann-Kendall", "C": "conteggio oltre il limite"}


def fmt_ts(ts: int | None) -> str:
    if ts is None:
        return "—"
    return datetime.fromtimestamp(ts / 1000, UTC).astimezone().strftime("%Y-%m-%d %H:%M")


def _status_badge(status: str) -> str:
    return (f'<span class="badge b-{status}"><span aria-hidden="true">●</span> '
            f"{STATUS_TEXT[status]}</span>")


def _level_badge(level: str) -> str:
    cls = {"info": "unknown", "attention": "attention", "action": "action"}[level]
    return f'<span class="badge b-{cls}">{LEVEL_TEXT[level]}</span>'


def _table(caption_text: str, headers: list[str], rows: list[list[str]],
           raw: bool = False) -> str:
    if not rows:
        return f'<p class="empty">{E(caption_text)}: nessun dato.</p>'
    h = "".join(f'<th scope="col">{E(x)}</th>' for x in headers)
    body = "".join("<tr>" + "".join(f"<td>{c if raw else E(c)}</td>" for c in r) + "</tr>"
                   for r in rows)
    return (f'<div class="tw"><table><caption>{E(caption_text)}</caption><thead><tr>{h}</tr>'
            f"</thead><tbody>{body}</tbody></table></div>")


def recovery_outcome(zpre: float, zpost: float) -> str:
    """Esito di una manutenzione per un indicatore che peggiora salendo (unità di σ)."""
    if zpre < 1.0:
        return "nessuna deriva prima"
    if zpost <= 1.5:
        return "recuperato"  # tornato al baseline (o sotto: meglio di prima)
    if zpost < zpre - 0.5:
        return "migliorato"
    return "non migliorato"


class ReportBuilder:
    def __init__(self, conn: sqlite3.Connection, cfg: dict[str, Any], now: int | None = None
                 ) -> None:
        self.conn = conn
        self.cfg = cfg
        row = conn.execute("SELECT MAX(ts) FROM agg_1min").fetchone()
        self.last_ts: int | None = row[0] if row else None
        real_now = int(datetime.now(UTC).timestamp() * 1000)
        self.now = now if now is not None else real_now
        # per i dati simulati/importati il "presente" è la fine dei dati
        self.ref_now = min(self.now, (self.last_ts or self.now) + 60_000)

    # ---------------------------------------------------------------- data
    def _q(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        return self.conn.execute(sql, args).fetchall()

    def chart_states(self) -> list[dict[str, Any]]:
        out = []
        for r in self._q("SELECT * FROM chart_state WHERE closed_ts IS NULL ORDER BY chart_id"):
            d = dict(r)
            d["params"] = json.loads(d["params"] or "{}")
            ind, regime, level = d["chart_id"].split("|")
            d.update(indicator=ind, regime=regime, level=level)
            out.append(d)
        return out

    def _chart_status(self, st: dict[str, Any]) -> str:
        if st["phase"] == "I":
            return ("copertura insufficiente" if st["params"].get("status") == "insufficient"
                    else "provvisoria (Fase I in corso)")
        if st["params"].get("degenerate"):
            return "costante (nessuna variabilità)"
        return "provvisoria" if st["provisional"] else "definitiva"

    # ------------------------------------------------------------- sections
    def overall(self, states: list[dict[str, Any]]) -> tuple[str, list[dict[str, str]]]:
        health = watchdog.check(self.conn, self.cfg["alerts"]["stale_heartbeat_min"],
                                self.ref_now)
        alerts = self._q("SELECT key, level, title FROM alerts WHERE active=1")
        diags = self._q("SELECT rule_id, title, confidence, charts FROM diagnoses WHERE active=1")
        rt = self._q("SELECT component, reason, severity, end_ts FROM rt_events "
                     "WHERE start_ts >= ?", (self.ref_now - DAY_MS,))
        comps = {"cpu": "CPU", "gpu": "GPU"}
        tiles: list[dict[str, str]] = []
        stale = health.stale_min is None or health.stale_min > 0
        for suffix, label in comps.items():
            charts = [s for s in states if split(s["indicator"])[1] == suffix]
            if not charts:
                continue
            locked = [s for s in charts if s["phase"] == "II"]
            level = "ok"
            reason = "Nessuna deriva rispetto al baseline."
            comp_key = "cpu" if suffix == "cpu" else "gpu0"
            for a in alerts:
                ind = a["key"].split(":")[1].split("|")[0] if a["key"].startswith("chart:") else ""
                if ind and split(ind)[1] == suffix and a["level"] == "attention" and level == "ok":
                    level, reason = "attention", f"Segnale persistente: {a['title']}."
            for d in diags:
                chs = json.loads(d["charts"] or "[]")
                if any(split(c.split("|")[0])[1] == suffix for c in chs):
                    lvl = self._diag_level(d["rule_id"])
                    if lvl == "action":
                        level, reason = "action", f"Ipotesi: {d['title']} ({d['confidence']})."
                    elif lvl == "attention" and level == "ok":
                        level, reason = "attention", f"Ipotesi: {d['title']}."
            for r in rt:
                if r["component"] == comp_key and r["severity"] == "error":
                    level = "action"
                    reason = f"Errore immediato: {REASON_TEXT.get(r['reason'], r['reason'])}" + (
                        " (in corso)." if r["end_ts"] is None else " nelle ultime 24 ore.")
            if level == "ok" and not locked:
                level, reason = "unknown", ("Baseline in costruzione: nessuna carta definitiva. "
                                            "L'assenza di segnali non indica buona salute.")
            if stale and level == "ok":
                level, reason = "unknown", "Dati non aggiornati: stato non verificabile."
            tiles.append({"label": label, "status": level, "reason": reason})
        cool = [d for d in diags if d["rule_id"] in ("dust_airflow", "paste_contact",
                                                     "fan_failure")]
        if cool:
            d = cool[0]
            lvl = self._diag_level(d["rule_id"])
            tiles.append({"label": "Raffreddamento",
                          "status": "action" if lvl == "action" else "attention",
                          "reason": f"{d['title']} (confidenza {d['confidence']})."})
        elif tiles:
            ok = all(t["status"] == "ok" for t in tiles)
            tiles.append({"label": "Raffreddamento", "status": "ok" if ok else "unknown",
                          "reason": "Nessuna ipotesi di manutenzione attiva." if ok else
                          "Valutazione limitata dalla copertura dei dati."})
        ssd = self._q("SELECT c.name, MAX(a.max) AS mx FROM agg_1min a JOIN channels c "
                      "ON c.id=a.channel_id WHERE c.name LIKE 'ssd%.temp_c' AND a.ts >= ? "
                      "GROUP BY c.name", (self.ref_now - 7 * DAY_MS,))
        if ssd:
            hot = [r for r in ssd if r["mx"] is not None and r["mx"] >= 70]
            tiles.append({"label": "Dischi", "status": "attention" if hot else "ok",
                          "reason": ("Temperatura massima SSD negli ultimi 7 giorni: "
                                     + ", ".join(f"{r['name'].split('.')[0]} {r['mx']:.0f} °C"
                                                 for r in ssd) + ". Solo monitoraggio della "
                                     "temperatura: nessuna previsione di guasto.")})
        html_tiles = "".join(
            f'<div class="tile t-{t["status"]}"><h3>{E(t["label"])}</h3>'
            f'{_status_badge(t["status"])}<p>{E(t["reason"])}</p></div>' for t in tiles)
        coll = ("attivo" if not stale else
                (f"fermo da {health.stale_min:.0f} minuti" if health.stale_min else "mai avviato"))
        extra = (f'<p>Ultimo campione: <strong>{E(fmt_ts(self.last_ts))}</strong>. Collector: '
                 f"<strong>{E(coll)}</strong>.")
        if health.failing_collectors:
            extra += f" Sorgenti in errore: {E(', '.join(health.failing_collectors))}."
        extra += "</p>"
        extra += self.sources()
        if get_meta(self.conn, "alert_budget_exceeded") == "1":
            extra += ('<p class="warn">Budget di allarmi superato: le notifiche di livello azione '
                      "sono sospese. Rivedere soglie e regole.</p>")
        bstate = get_meta(self.conn, "baseline_state") or self.cfg["profile"]["baseline_state"]
        if bstate == "unknown":
            extra += ('<p class="note">Stato del PC all\'inizio del baseline: <em>sconosciuto</em>.'
                      " Il tool riporta solo i cambiamenti rispetto al baseline, non uno stato "
                      "assoluto: se il PC era già sporco, il degrado è incluso nei limiti. Per un "
                      "riferimento affidabile pulire il PC e avviare una nuova Fase I "
                      "(<code>hwdrift baseline start --state clean</code>).</p>")
        return f'<div class="tiles">{html_tiles}</div>{extra}', tiles

    def sources(self) -> str:
        raw = get_meta(self.conn, "collectors_status")
        if not raw:
            return ""
        try:
            st = json.loads(raw)
        except ValueError:
            return ""
        rows = []
        for s in st:
            state = ("attiva" if s.get("ok") else "sospesa (game-safe)" if s.get("suspended")
                     else "non disponibile" if not s.get("started") else "in errore")
            rows.append([s.get("name", ""), state, str(s.get("last_error", ""))[:160]])
        return ("<details><summary>Sorgenti di dati</summary>"
                + _table("Stato delle sorgenti all'ultimo salvataggio del collector",
                         ["Sorgente", "Stato", "Ultimo errore"], rows) + "</details>")

    def _diag_level(self, rule_id: str) -> str:
        r = self.conn.execute("SELECT level FROM alerts WHERE key=?", (f"diag:{rule_id}",)
                              ).fetchone()
        return r[0] if r else "info"

    def realtime(self) -> str:
        rows = self._q("SELECT * FROM rt_events WHERE start_ts >= ? ORDER BY start_ts DESC "
                       "LIMIT 200", (self.ref_now - 30 * DAY_MS,))
        ongoing = [r for r in rows if r["end_ts"] is None]
        head = ""
        if ongoing:
            head = ('<p class="warn" role="status"><strong>Episodio in corso:</strong> '
                    + "; ".join(f"{r['component'].upper()} {REASON_TEXT.get(r['reason'], '')}"
                                for r in ongoing) + "</p>")
        body = []
        for r in rows:
            dur = ("in corso" if r["end_ts"] is None
                   else f"{(r['end_ts'] - r['start_ts']) / 1000:.0f} s")
            body.append([fmt_ts(r["start_ts"]), dur, r["component"].upper(),
                         REASON_TEXT.get(r["reason"], r["reason"]), SEV_TEXT[r["severity"]],
                         "—" if r["peak"] is None else f"{r['peak']:.1f}"])
        return head + _table("Episodi di throttling grave e ventole ferme (ultimi 30 giorni)",
                             ["Inizio", "Durata", "Componente", "Motivo", "Gravità", "Picco"],
                             body)

    def hypotheses(self) -> str:
        rows = self._q("SELECT * FROM diagnoses WHERE active=1 ORDER BY ts DESC")
        if not rows:
            return '<p class="empty">Nessuna ipotesi di manutenzione attiva.</p>'
        out = []
        for d in rows:
            lvl = self._diag_level(d["rule_id"])
            sup = json.loads(d["supports"])
            con = json.loads(d["contradicts"])
            acts = json.loads(d["actions"])
            out.append(
                f'<article class="diag"><h3>{E(d["title"])} {_level_badge(lvl)}</h3>'
                f'<p>Confidenza: <strong>{E(d["confidence"])}</strong> (qualitativa, non una '
                f"probabilità). Aggiornata il {E(fmt_ts(d['ts']))}.</p>"
                "<h4>Segnali a supporto</h4><ul>"
                + "".join(f"<li>{E(s)}</li>" for s in sup) + "</ul>"
                + ("<h4>Segnali contrari</h4><ul>" + "".join(f"<li>{E(s)}</li>" for s in con)
                   + "</ul>" if con else "<p>Nessun segnale contrario.</p>")
                + "<h4>Verifiche suggerite (dalla meno alla più invasiva)</h4><ol>"
                + "".join(f"<li>{E(a)}</li>" for a in acts) + "</ol></article>")
        return "".join(out)

    def alerts(self) -> str:
        rows = self._q("SELECT * FROM alerts WHERE active=1 ORDER BY CASE level WHEN 'action' "
                       "THEN 0 WHEN 'attention' THEN 1 ELSE 2 END, last_ts DESC")
        body = [[_level_badge(r["level"]), E(r["title"]), E(r["message"]),
                 E(fmt_ts(r["first_ts"]))] for r in rows]
        return _table("Allarmi attivi", ["Livello", "Titolo", "Dettaglio", "Dal"], body,
                      raw=True)

    def _events_for_chart(self, since: int) -> list[tuple[int, str]]:
        return [(r[0], r[1]) for r in self._q(
            "SELECT ts, kind FROM events WHERE ts >= ? AND (kind LIKE 'maintenance.%' OR kind "
            "LIKE 'config.%' OR kind IN ('system.gap', 'system.baseline_start'))", (since,))]

    def chart_block(self, st: dict[str, Any], uid: str) -> str:
        ind, regime, level = st["indicator"], st["regime"], st["level"]
        rows = self._q("SELECT ts, value FROM indicators WHERE indicator=? AND regime=? AND "
                       "level=? AND ts >= ? ORDER BY ts", (ind, regime, level, st["start_ts"]))
        ts = [r[0] for r in rows][-MAX_POINTS:]
        vals = [r[1] for r in rows][-MAX_POINTS:]
        sigs: dict[int, str] = {}
        for r in self._q("SELECT ts, rule, side, label FROM signals WHERE chart_id=? AND "
                         "segment=? ORDER BY ts", (st["chart_id"], st["segment"])):
            txt = f"{RULE_TEXT.get(r['rule'], r['rule'])} ({'sopra' if r['side'] == 'upper' else 'sotto'})"
            if r["label"] != "maintenance":
                txt += f" [{r['label']}]"
            sigs[r["ts"]] = (sigs[r["ts"]] + "; " + txt) if r["ts"] in sigs else txt
        c, s = st["center"], st["sigma"]
        widen = st["params"].get("widen", 1.0)
        lines = Lines(c, st["ucl"], st["lcl"])
        if c is not None and s:
            lines.ucl2, lines.lcl2 = c + 2 * s * widen, c - 2 * s * widen
        d = definition(ind)
        unit = d.unit if d else ""
        status = self._chart_status(st)
        cap = caption(ind, regime)
        title = f"{ind} — {regime} — {'per finestra' if level == 'window' else 'giornaliera'}"
        desc = (f"Carta I, {len(ts)} punti. Stato: {status}. "
                + (f"Linea centrale {c:.4g} {unit}, limiti {st['lcl']:.4g}–{st['ucl']:.4g}. "
                   if c is not None and st["ucl"] is not None else "")
                + f"Segnali: {len([t for t in ts if t in sigs])}.")
        events = self._events_for_chart(ts[0] if ts else 0)
        svg_i = chart(Series(ts, vals, st["locked_ts"], {t: v for t, v in sigs.items()}), lines,
                      title, desc, uid, events)
        mr_html = ""
        if len(vals) > 2 and d is not None and d.kind != "count":
            mr = list(moving_ranges(np.array(vals)))
            mr_lines = Lines(st["mr_bar"], st["ucl_mr"], None)
            mr_html = chart(Series(ts[1:], mr, st["locked_ts"]), mr_lines,
                            f"Range mobili — {title}",
                            "Carta MR: differenza assoluta tra punti consecutivi; i salti oltre "
                            "il limite indicano un cambiamento improvviso.", uid + "-mr", events,
                            height=140)
        sig_list = [f"{fmt_ts(t)}: {txt}" for t, txt in sigs.items() if t >= (ts[0] if ts else 0)]
        table_rows = [[fmt_ts(t), f"{v:.5g}", sigs.get(t, "")] for t, v in
                      zip(ts[-100:], vals[-100:], strict=True)]
        return (f'<section class="chartbox" aria-labelledby="h-{uid}"><h3 id="h-{uid}">'
                f"{E(title)}</h3><p class=\"cap\">{E(cap)}</p>"
                f"<p>Stato della carta: <strong>{E(status)}</strong>; segmento "
                f"{st['segment']}; unità: {E(unit)}. Linee: continua = limiti a 3σ, "
                "tratteggiata = 2σ, punteggiata = linea centrale; triangoli = segnali; zona "
                "ombreggiata = Fase I.</p>"
                + svg_i + mr_html
                + ("<details><summary>Segnali ({})</summary><ul>{}</ul></details>".format(
                    len(sig_list), "".join(f"<li>{E(x)}</li>" for x in sig_list[-50:]))
                   if sig_list else "<p>Nessun segnale nel segmento corrente.</p>")
                + "<details><summary>Tabella dati (ultimi 100 punti)</summary>"
                + _table(f"Dati di {title}", ["Data", "Valore", "Segnali"], table_rows)
                + "</details></section>")

    def charts(self, states: list[dict[str, Any]]) -> str:
        primary = set(self.cfg["alerts"]["primary"])
        main, other = [], []
        for i, st in enumerate(states):
            base = split(st["indicator"])[0]
            is_main = (st["indicator"] in primary and base not in SECONDARY_BASES
                       and st["level"] == "daily")
            (main if is_main else other).append((i, st))
        if not main:  # nessuna carta giornaliera ancora: mostra quelle per finestra
            main = [(i, st) for i, st in other if st["indicator"] in primary
                    and st["level"] == "window"]
            other = [(i, st) for i, st in other if (i, st) not in main]
        simple = "".join(self.chart_block(st, f"c{i}") for i, st in main)
        adv = "".join(self.chart_block(st, f"c{i}") for i, st in other)
        return (f"<h3>Modalità semplice: carte principali</h3>{simple or '<p class=empty>Nessuna carta: copertura insufficiente.</p>'}"
                f"<details class=\"adv\"><summary>Modalità avanzata: tutte le altre carte "
                f"({len(other)})</summary>{adv}</details>")

    def chart_summary(self, states: list[dict[str, Any]]) -> str:
        rows = []
        for st in states:
            rows.append([st["indicator"], st["regime"], st["level"], self._chart_status(st),
                         str(st["params"].get("n", 0)), str(st["n_phase1"]),
                         st["params"].get("method", "") or "",
                         "sì" if st["params"].get("assumptions", {}).get("autocorrelated") else
                         "no"])
        return _table("Stato delle carte (segmento corrente)",
                      ["Indicatore", "Regime", "Livello", "Stato", "Osservazioni", "Fase I (n)",
                       "Sigma", "Autocorrelata"], rows)

    def events(self) -> str:
        rows = self._q("SELECT ts, kind, source, note, detail FROM events WHERE ts >= ? AND kind "
                       "NOT IN ('system.collector_start') ORDER BY ts DESC LIMIT 200",
                       (self.ref_now - 60 * DAY_MS,))
        body = [[fmt_ts(r["ts"]), describe(r["kind"]), r["source"], r["note"] or "",
                 r["detail"] if r["detail"] != "{}" else ""] for r in rows]
        return _table("Eventi (ultimi 60 giorni)", ["Data", "Evento", "Origine", "Nota",
                                                    "Dettaglio"], body)

    def coverage(self) -> str:
        from ..indicators.coverage import weekly_coverage

        cov = weekly_coverage(self.conn)
        rows = [[c["component"], c["regime"], c["week"], str(c["valid"]), str(c["throttled"])]
                for c in cov]
        q = self._q("SELECT c.name, COUNT(*) AS n, SUM(CASE WHEN a.valid_frac < 1 THEN 1 ELSE 0 "
                    "END) AS bad, MAX(a.ts) AS last FROM agg_1min a JOIN channels c ON "
                    "c.id=a.channel_id WHERE a.ts >= ? AND c.name NOT LIKE 'hwdrift.%' GROUP BY "
                    "c.name ORDER BY c.name", (self.ref_now - 7 * DAY_MS,))
        qrows = [[r["name"], str(r["n"]), f"{100 * (r['bad'] or 0) / r['n']:.1f}%",
                  fmt_ts(r["last"])] for r in q]
        return (_table("Finestre valide per regime e settimana (le finestre con throttling non "
                       "entrano in Rth)", ["Componente", "Regime", "Settimana", "Valide",
                                           "Con throttling"], rows)
                + _table("Qualità dei dati (ultimi 7 giorni): minuti con campioni esclusi",
                         ["Canale", "Minuti", "Con esclusioni", "Ultimo dato"], qrows))

    def effectiveness(self) -> str:
        rows = []
        for ev in self._q("SELECT ts, kind FROM events WHERE kind LIKE 'maintenance.%' "
                          "ORDER BY ts"):
            for st in self._q("SELECT * FROM chart_state WHERE closed_ts=?", (ev["ts"],)):
                if not st["sigma"]:
                    continue
                ind, regime, level = st["chart_id"].split("|")
                pre = [r[0] for r in self._q(
                    "SELECT value FROM indicators WHERE indicator=? AND regime=? AND level=? AND "
                    "ts < ? ORDER BY ts DESC LIMIT 10", (ind, regime, level, ev["ts"]))]
                post = [r[0] for r in self._q(
                    "SELECT value FROM indicators WHERE indicator=? AND regime=? AND level=? AND "
                    "ts >= ? ORDER BY ts LIMIT 10", (ind, regime, level, ev["ts"]))]
                if len(pre) < 3 or len(post) < 3:
                    continue
                zpre = (float(np.median(pre)) - st["center"]) / st["sigma"]
                zpost = (float(np.median(post)) - st["center"]) / st["sigma"]
                rows.append([fmt_ts(ev["ts"]), describe(ev["kind"]), ind, regime, level,
                             f"{zpre:+.1f}σ", f"{zpost:+.1f}σ", recovery_outcome(zpre, zpost)])
        return _table("Efficacia della manutenzione: indicatore prima e dopo, rispetto al "
                      "baseline precedente (unità di σ)",
                      ["Data", "Intervento", "Indicatore", "Regime", "Livello", "Prima", "Dopo",
                       "Esito"], rows)

    def overhead(self) -> str:
        smp = self.cfg["sampling"]
        rows = []
        for ch, budget in (("hwdrift.cpu_pct", smp["cpu_budget_pct"]),
                           ("hwdrift.rss_mb", smp["rss_budget_mb"])):
            r = self.conn.execute(
                "SELECT AVG(a.median), MAX(a.max) FROM agg_1min a JOIN channels c ON "
                "c.id=a.channel_id WHERE c.name=? AND a.ts >= ?", (ch, self.ref_now - DAY_MS)
            ).fetchone()
            if r and r[0] is not None:
                rows.append([ch, f"{r[0]:.2f}", f"{r[1]:.2f}", f"{budget}",
                             "entro il budget" if r[1] <= budget else "OLTRE il budget"])
        return _table("Uso di risorse del collector (ultime 24 ore)",
                      ["Canale", "Media", "Massimo", "Budget", "Esito"], rows)

    # ---------------------------------------------------------------- page
    def build(self) -> str:
        states = self.chart_states()
        overall, _ = self.overall(states)
        mid = (get_meta(self.conn, "machine_id") or "")[:8]
        first = self.conn.execute("SELECT MIN(ts) FROM agg_1min").fetchone()[0]
        sections = [
            ("stato", "Stato generale", overall),
            ("errori", "Errori immediati", self.realtime()),
            ("ipotesi", "Ipotesi di manutenzione", self.hypotheses()),
            ("allarmi", "Allarmi", self.alerts()),
            ("carte", "Carte di controllo", self.chart_summary(states) + self.charts(states)),
            ("eventi", "Eventi", self.events()),
            ("copertura", "Copertura e qualità dei dati", self.coverage()),
            ("efficacia", "Efficacia della manutenzione", self.effectiveness()),
            ("overhead", "Overhead", self.overhead()),
        ]
        nav = "".join(f'<li><a href="#{sid}">{E(t)}</a></li>' for sid, t, _ in sections)
        body = "".join(f'<section id="{sid}" aria-labelledby="h-{sid}"><h2 id="h-{sid}">{E(t)}'
                       f"</h2>{content}</section>" for sid, t, content in sections)
        return f"""<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:">
<title>HWDrift — report</title><style>{CSS}</style></head>
<body><a class="skip" href="#main">Salta al contenuto</a>
<header><h1>HWDrift — salute termica di CPU e GPU</h1>
<p>Macchina <code>{E(mid)}</code> · dati dal {E(fmt_ts(first))} al {E(fmt_ts(self.last_ts))} ·
report generato il {E(fmt_ts(self.now))} · HWDrift {E(__version__)}</p>
<nav aria-label="Sezioni del report"><ul>{nav}</ul></nav></header>
<main id="main">{body}</main>
<footer><h2>Avvertenze</h2><ul>
<li>Non è un avviso di sicurezza né una diagnosi di guasto: le ipotesi hanno una confidenza
qualitativa e vanno verificate.</li>
<li>Aprire il PC può invalidare la garanzia; sui portatili seguire le procedure del
produttore.</li>
<li>In caso di temperature elevate o spegnimenti, non attendere il tool: intervenire.</li>
<li>Il tool rileva derive rispetto al baseline della macchina; non stima vita residua né
probabilità di guasto.</li></ul></footer></body></html>"""


CSS = """
:root{--bg:#fff;--fg:#1a1a1a;--muted:#555;--line:#d0d0d0;--plot:#fafafa;--ok:#1b6e20;
--att:#8a5a00;--act:#b3261e;--unk:#5a5a5a;--accent:#0b57d0;--ph1:#e8eefc;--series:#0b57d0}
@media (prefers-color-scheme:dark){:root{--bg:#121212;--fg:#ececec;--muted:#b5b5b5;
--line:#444;--plot:#1c1c1c;--ok:#7fd88a;--att:#f5c16c;--act:#ff8a80;--unk:#bdbdbd;
--accent:#8ab4f8;--ph1:#1f2a3d;--series:#8ab4f8}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
header,main,footer{max-width:1100px;margin:0 auto;padding:0 16px}
h1{font-size:1.6rem;margin:1rem 0 .3rem}h2{border-bottom:1px solid var(--line);padding-top:1rem}
a{color:var(--accent)}a:focus,summary:focus{outline:3px solid var(--accent);outline-offset:2px}
.skip{position:absolute;left:-999px}.skip:focus{left:8px;top:8px;background:var(--bg);padding:6px}
nav ul{display:flex;flex-wrap:wrap;gap:.2rem 1rem;padding:0;list-style:none}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
.tile{border:1px solid var(--line);border-left:8px solid var(--unk);border-radius:6px;padding:8px 12px}
.tile h3{margin:.2rem 0}.t-ok{border-left-color:var(--ok)}.t-attention{border-left-color:var(--att)}
.t-action{border-left-color:var(--act)}.badge{font-weight:700;white-space:nowrap}
.b-ok{color:var(--ok)}.b-attention{color:var(--att)}.b-action{color:var(--act)}.b-unknown{color:var(--unk)}
.warn{border-left:6px solid var(--act);padding:4px 10px}.note{border-left:6px solid var(--att);padding:4px 10px}
.empty{color:var(--muted);font-style:italic}.tw{overflow-x:auto}
table{border-collapse:collapse;width:100%;margin:.5rem 0;font-size:.92rem}
caption{text-align:left;font-weight:600;padding:.3rem 0}
th,td{border:1px solid var(--line);padding:4px 6px;text-align:left;vertical-align:top}
.chartbox{border:1px solid var(--line);border-radius:6px;padding:4px 12px;margin:12px 0}
.cap{color:var(--muted);margin:0}svg.chart{width:100%;height:auto;display:block}
.plot{fill:var(--plot);stroke:var(--line)}.phase1{fill:var(--ph1)}
.grid{stroke:var(--line);stroke-width:.5}.ax,.lbl{fill:var(--muted);font-size:11px}
.lim{stroke:var(--act);stroke-width:1.2}.lim2{stroke:var(--att);stroke-dasharray:5 4}
.cl{stroke:var(--fg);stroke-dasharray:1 3}.series{fill:none;stroke:var(--series);stroke-width:.8;opacity:.6}
.pt{fill:var(--series)}.sig{fill:var(--act)}.ev{stroke:var(--muted);stroke-dasharray:2 2}
.ev-maintenance{stroke:var(--ok);stroke-width:2;stroke-dasharray:none}
.ev-config{stroke:var(--att);stroke-width:2}.diag{border:1px solid var(--line);border-radius:6px;
padding:4px 12px;margin:8px 0}footer{margin-top:2rem;color:var(--muted)}
@media (max-width:600px){body{font-size:15px}}
"""


def write_report(conn: sqlite3.Connection, cfg: dict[str, Any], out: Path,
                 now: int | None = None) -> Path:
    html_text = ReportBuilder(conn, cfg, now).build()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_text, encoding="utf-8")
    return out
