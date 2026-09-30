# SPDX-License-Identifier: Apache-2.0
"""Interfaccia a riga di comando (``hwdrift``), sezione 9.

Gli import pesanti (numpy, scipy) sono dentro i comandi di analisi: ``hwdrift run``
resta leggero.
"""

from __future__ import annotations

import contextlib
import json
import logging
import logging.handlers
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import typer

from . import __version__
from .config import ConfigError, data_dir, load_config
from .config import db_path as default_db_path

app = typer.Typer(help="HWDrift: deriva termica di CPU e GPU con carte di controllo (locale, "
                       "senza cloud).", no_args_is_help=True, add_completion=False)
baseline_app = typer.Typer(help="Fase I (baseline) delle carte di controllo.",
                           no_args_is_help=True)
event_app = typer.Typer(help="Registro eventi: manutenzioni, configurazione, note.",
                        no_args_is_help=True)
schedule_app = typer.Typer(help="Esecuzione in background (Utilità di pianificazione).",
                           no_args_is_help=True)
app.add_typer(baseline_app, name="baseline")
app.add_typer(event_app, name="event")
app.add_typer(schedule_app, name="schedule")

log = logging.getLogger("hwdrift")


class State:
    cfg: dict[str, Any]
    db: Path
    db_explicit: bool = False
    config_explicit: bool = False


state = State()


def _setup_logging(verbose: bool, logfile: Path | None) -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(logging.DEBUG if verbose else logging.WARNING)
    sh.setFormatter(fmt)
    root.handlers = [sh]
    if logfile is not None:
        try:
            fh = logging.handlers.RotatingFileHandler(logfile, maxBytes=2_000_000, backupCount=3,
                                                      encoding="utf-8")
            fh.setFormatter(fmt)
            root.addHandler(fh)
        except OSError:
            pass


@app.callback()
def main_callback(
    config: Path | None = typer.Option(None, "--config", "-c", help="file hwdrift.yaml"),
    db: Path | None = typer.Option(None, "--db", help="database SQLite (default: cartella dati)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="log dettagliato"),
) -> None:
    try:
        state.cfg = load_config(config)
    except ConfigError as exc:
        typer.echo(f"Errore di configurazione: {exc}", err=True)
        raise typer.Exit(2) from exc
    state.db = db if db is not None else default_db_path(state.cfg)
    state.db_explicit = db is not None
    state.config_explicit = config is not None
    _setup_logging(verbose, data_dir(state.cfg) / "hwdrift.log" if db is None else None)


def _open(readonly: bool = False):
    from .storage.schema import connect, open_db

    if readonly:
        if not state.db.exists():
            typer.echo(f"Database non trovato: {state.db}. Avviare prima 'hwdrift run' o "
                       "'hwdrift simulate'.", err=True)
            raise typer.Exit(1)
        return connect(state.db, readonly=True)
    return open_db(state.db)


def is_elevated() -> bool:
    try:
        if sys.platform == "win32":
            import ctypes

            return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
        import os

        return os.geteuid() == 0
    except Exception:
        return False


def _refuse_if_insecure_config(cfg: dict[str, Any]) -> None:
    """Un collector elevato non deve eseguire configurazioni trovate nella cartella
    corrente (potrebbero cambiare gli eseguibili esterni usati): THREAT_MODEL T1."""
    src = cfg.get("_source")
    if src and is_elevated() and Path(src).resolve().parent == Path.cwd().resolve() \
            and Path(src).name == "hwdrift.yaml" and not state.config_explicit:
        typer.echo("Rifiutato: con privilegi elevati la configurazione va indicata "
                   "esplicitamente con --config (non presa dalla cartella corrente).", err=True)
        raise typer.Exit(2)


def _parse_when(text: str | None) -> int | None:
    if text is None:
        return None
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise typer.BadParameter("data non valida: usare il formato ISO, es. "
                                 "2026-09-30 o '2026-09-30 18:30'") from exc
    if dt.tzinfo is None:
        dt = dt.astimezone()  # ora locale
    return int(dt.timestamp() * 1000)


# --------------------------------------------------------------------- comandi
@app.command()
def version() -> None:
    """Versione di HWDrift."""
    typer.echo(__version__)


@app.command()
def discover(
    write_profile: Path | None = typer.Option(None, help="scrive la mappatura proposta in YAML"),
    show_unmapped: bool = typer.Option(True, help="mostra anche i sensori non mappati"),
) -> None:
    """Elenca i sensori disponibili e propone la mappatura sui canali canonici."""
    import time

    from .collectors.base import CollectorUnavailable, build_collectors

    collectors = build_collectors(state.cfg)
    mapping: dict[str, str] = {}
    for c in collectors:
        typer.echo(f"\n== {c.name}" + (" (richiede privilegi elevati)" if c.needs_admin else ""))
        try:
            c.start()
            samples = c.poll(int(time.time() * 1000), time.monotonic())
        except CollectorUnavailable as exc:
            typer.echo(f"   non disponibile: {exc}")
            continue
        except Exception as exc:
            typer.echo(f"   errore: {exc}")
            continue
        finally:
            with contextlib.suppress(Exception):
                c.close()
        if not samples:
            typer.echo("   nessun sensore (sorgente di eventi o dati non ancora disponibili)")
        for s in samples:
            if s.channel is None and not show_unmapped:
                continue
            ch = s.channel or "—"
            val = "n/d" if s.value is None else f"{s.value:.2f} {s.unit}"
            typer.echo(f"   {ch:<28} {val:<16} {s.raw_name}  [{s.sensor_id}]")
            if s.channel:
                mapping[s.sensor_id] = s.channel
    if write_profile is not None:
        import yaml

        write_profile.write_text(
            "# Profilo macchina proposto da 'hwdrift discover': verificare e copiare la sezione\n"
            "# 'profile.mapping' in hwdrift.yaml. Un canale vuoto ('') esclude il sensore.\n"
            + yaml.safe_dump({"profile": {"mapping": mapping}}, allow_unicode=True,
                             sort_keys=True), encoding="utf-8")
        typer.echo(f"\nProfilo scritto in {write_profile}")


@app.command()
def run(
    simulate: str | None = typer.Option(None, help="usa il simulatore: healthy, throttle, "
                                                   "frozen, crash, power_limit"),
    interval: float | None = typer.Option(None, help="intervallo di campionamento (s)"),
    max_seconds: float | None = typer.Option(None, help="ferma dopo N secondi (test)"),
    fault_after: float | None = typer.Option(None, help="simulatore: secondi prima del guasto"),
) -> None:
    """Avvia il collector residente (Ctrl+C per fermare)."""
    from .runner import Runner
    from .storage.schema import open_db

    cfg = state.cfg
    if simulate:
        cfg["sources"]["simulator"].update(enabled=True, scenario=simulate)
        if fault_after is not None:
            cfg["sources"]["simulator"]["fault_after_s"] = fault_after
        if not state.db_explicit:
            # i dati simulati non devono mai finire nel database della macchina reale
            state.db = data_dir(cfg) / f"sim-{simulate}.sqlite"
    elif not state.db_explicit:
        _refuse_if_insecure_config(cfg)
    if interval is not None:
        cfg["sampling"]["interval_s"] = interval
    conn = open_db(state.db)
    runner = Runner(cfg, conn)
    ticks = None
    if max_seconds is not None:
        ticks = max(1, int(max_seconds / cfg["sampling"]["interval_s"]))
    typer.echo(f"Collector avviato (database: {state.db}). Ctrl+C per fermare.")
    runner.run(max_ticks=ticks)
    for st in runner.status():
        flag = "ok" if st["ok"] else ("sospeso" if st["suspended"] else "NON ATTIVO")
        extra = f" — {st['last_error']}" if st["last_error"] and not st["ok"] else ""
        typer.echo(f"  {st['name']:<14} {flag}{extra}")


@app.command()
def analyze(
    rebuild: bool = typer.Option(False, help="ricalcola tutto dagli aggregati (nuova "
                                             "calibrazione dei regimi)"),
    loop: float | None = typer.Option(None, help="ripeti ogni N minuti"),
    report: bool = typer.Option(True, help="rigenera il report HTML dopo l'analisi"),
) -> None:
    """Esegue il worker di analisi: finestre, indicatori, carte, segnali, diagnosi."""
    import time

    from .analysis.worker import rebuild as do_rebuild
    from .analysis.worker import run_analysis

    while True:
        conn = _open()
        if rebuild:
            do_rebuild(conn)
            rebuild = False
        s = run_analysis(conn, state.cfg)
        typer.echo(f"Analisi completata in {s['duration_s']} s: {s['windows_new']} nuove finestre,"
                   f" {s['signals_new']} nuovi segnali; allarmi attivi: {s['alerts']}")
        for w in s["warnings"]:
            typer.echo(f"  avviso: {w}")
        if report:
            from .reporting.html_report import write_report

            out = write_report(conn, state.cfg, data_dir(state.cfg) / "report.html")
            typer.echo(f"Report: {out}")
        conn.close()
        if loop is None:
            break
        time.sleep(loop * 60)


@baseline_app.command("start")
def baseline_start(
    chart: str | None = typer.Option(None, help="solo questa carta (indicatore|regime|livello)"),
    component: str | None = typer.Option(None, help="solo un componente: cpu, gpu"),
    state_: str = typer.Option("unknown", "--state", help="stato del PC: clean (appena pulito)"
                                                          " o unknown"),
    note: str = typer.Option("", help="nota"),
) -> None:
    """Apre una nuova Fase I (per tutte le carte, un componente o una carta)."""
    from .context.events import add_user_event
    from .model import now_ms
    from .storage.schema import get_meta, set_meta

    if state_ not in ("clean", "unknown"):
        raise typer.BadParameter("--state: clean | unknown")
    conn = _open()
    ts = now_ms()
    if chart:
        raw = get_meta(conn, "chart_breaks")
        cb = json.loads(raw) if raw else {}
        cb.setdefault(chart, []).append(ts)
        with conn:
            set_meta(conn, "chart_breaks", json.dumps(cb))
    else:
        detail = {"component": "gpu0" if component == "gpu" else component} if component else {}
        add_user_event(conn, "system.baseline_start", ts, note, detail)
    with conn:
        set_meta(conn, "baseline_state", state_)
    typer.echo("Nuova Fase I avviata. Il baseline rappresenta lo stato attuale del PC"
               + (" (dichiarato appena pulito)." if state_ == "clean" else
                  ": se il PC è sporco, il degrado entra nei limiti."))


@baseline_app.command("lock")
def baseline_lock(chart: str | None = typer.Option(None, help="carta da bloccare (default: "
                                                               "tutte)")) -> None:
    """Chiude la Fase I alla prossima analisi, anche prima dei criteri minimi (limiti
    provvisori, più larghi)."""
    from .storage.schema import set_meta

    conn = _open()
    with conn:
        set_meta(conn, "force_lock", json.dumps([chart or "*"]))
    typer.echo("Richiesta registrata: sarà applicata dal prossimo 'hwdrift analyze'.")


@baseline_app.command("status")
def baseline_status() -> None:
    """Stato delle carte (Fase I o II, provvisoria o definitiva)."""
    conn = _open(readonly=True)
    rows = conn.execute("SELECT chart_id, segment, phase, provisional, n_phase1, params FROM "
                        "chart_state WHERE closed_ts IS NULL ORDER BY chart_id").fetchall()
    if not rows:
        typer.echo("Nessuna carta: eseguire 'hwdrift analyze' dopo qualche giorno di raccolta.")
    for cid, seg, phase, prov, n1, params in rows:
        p = json.loads(params)
        st = ("Fase I: " + p.get("status", "")) if phase == "I" else (
            "provvisoria" if prov else "definitiva")
        typer.echo(f"{cid:<42} seg {seg}  {st:<24} n={p.get('n', 0):<6} FaseI={n1}")


@event_app.command("add")
def event_add(
    kind: str = typer.Argument(..., help="es. maintenance.clean, maintenance.repaste, "
                                         "config.driver (vedi 'hwdrift event kinds')"),
    at: str | None = typer.Option(None, help="data/ora ISO (default: adesso)"),
    note: str = typer.Option("", help="nota libera (non esportata in forma anonima)"),
) -> None:
    """Registra una manutenzione o un evento."""
    from .context.events import add_user_event

    conn = _open()
    try:
        eid = add_user_event(conn, kind, _parse_when(at), note)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    typer.echo(f"Evento {eid} registrato: {kind}.")
    if kind.startswith("maintenance."):
        typer.echo("Le carte chiudono il segmento e ripartono con una nuova Fase I; il report "
                   "mostrerà l'efficacia della manutenzione.")


@event_app.command("list")
def event_list(days: float = typer.Option(30, help="ultimi N giorni")) -> None:
    """Elenca gli eventi recenti."""
    from .context.events import describe, list_events
    from .model import now_ms

    conn = _open(readonly=True)
    for e in list_events(conn, since=now_ms() - int(days * 86_400_000)):
        when = datetime.fromtimestamp(e.ts / 1000).strftime("%Y-%m-%d %H:%M")
        typer.echo(f"{e.id:>6} {when} {e.kind:<24} {describe(e.kind)} {e.note}")


@event_app.command("kinds")
def event_kinds() -> None:
    """Tipi di evento registrabili a mano."""
    from .model import EVENT_KINDS, USER_EVENT_KINDS

    for k in USER_EVENT_KINDS:
        typer.echo(f"{k:<24} {EVENT_KINDS[k]}")


@app.command()
def report(out: Path | None = typer.Option(None, help="file HTML di uscita")) -> None:
    """Genera il report HTML con carte, segnali e diagnosi."""
    from .reporting.html_report import write_report

    conn = _open(readonly=True)
    p = write_report(conn, state.cfg, out or data_dir(state.cfg) / "report.html")
    typer.echo(f"Report: {p}")


@app.command()
def export(
    fmt: str = typer.Option("csv", "--format", help="csv | jsonl | parquet | prometheus | otlp"),
    out: Path = typer.Option(Path("hwdrift-export"), help="cartella o file di uscita"),
    anonymize: bool = typer.Option(True, help="export anonimo (default)"),
    since: str | None = typer.Option(None, help="solo dati da questa data (ISO)"),
) -> None:
    """Esporta il dataset (anche in forma anonima) o le metriche."""
    from .storage import export as ex

    conn = _open(readonly=True)
    s = _parse_when(since)
    if fmt == "csv":
        paths = ex.export_csv(conn, out, anonymize, s)
    elif fmt == "jsonl":
        paths = ex.export_jsonl(conn, out, anonymize, s)
    elif fmt == "parquet":
        paths = ex.export_parquet(conn, out, anonymize, s)
    elif fmt == "prometheus":
        target = out if out.suffix else out / "hwdrift.prom"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(ex.prometheus_text(conn), encoding="utf-8")
        paths = [target]
    elif fmt == "otlp":
        target = out if out.suffix else out / "hwdrift-otlp.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(ex.otlp_json(conn), indent=1), encoding="utf-8")
        paths = [target]
    else:
        raise typer.BadParameter("formato non valido")
    for p in paths:
        typer.echo(f"scritto {p}")


@app.command("import-hwinfo")
def import_hwinfo(
    file: Path = typer.Argument(..., exists=True, dir_okay=False, help="log CSV di HWiNFO"),
    tz_offset: float | None = typer.Option(None, help="fuso del log in ore (default: locale)"),
) -> None:
    """Importa un log CSV di HWiNFO (aggregato a 1 minuto)."""
    from .collectors.hwinfo_csv import parse_hwinfo_csv, read_text
    from .quality.sanity import QualityChecker
    from .storage.writer import write_minute_aggregates

    conn = _open()
    qc = QualityChecker()
    try:
        samples = [qc.check(s) for s in parse_hwinfo_csv(
            read_text(file), state.cfg["profile"]["mapping"], tz_offset)]
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    channels = sorted({s.channel for s in samples if s.channel})
    n = write_minute_aggregates(conn, samples)
    typer.echo(f"Importati {len(samples)} campioni in {n} aggregati da 1 minuto. Canali: "
               f"{', '.join(channels) or 'nessuno (controllare la mappatura)'}")


@app.command()
def selftest(seconds: float = typer.Option(30, help="durata della misura")) -> None:
    """Misura l'overhead del collector e verifica lo stato delle sorgenti."""
    from .selftest import run_selftest

    r = run_selftest(state.cfg, seconds)
    typer.echo(json.dumps(r, indent=1, default=str))
    if not r["within_budget"] or r["heavy_modules_loaded"]:
        typer.echo("SELFTEST FALLITO: budget superato o librerie pesanti caricate", err=True)
        raise typer.Exit(1)


@app.command()
def healthcheck(
    duration: float | None = typer.Option(None, help="durata del carico (s)"),
    yes: bool = typer.Option(False, "--yes", help="conferma: genera calore e occupa la CPU"),
) -> None:
    """Health-check attivo opzionale: carico CPU breve con interruzione di sicurezza."""
    import time

    from .healthcheck import healthcheck_event, read_live, run_healthcheck
    from .model import now_ms

    hc = state.cfg["healthcheck"]
    if not yes:
        typer.echo("Il health-check genera calore e occupa la CPU. Ripetere con --yes per "
                   "confermare. Il collector ('hwdrift run') deve essere in esecuzione.")
        raise typer.Exit(1)
    ddir = data_dir(state.cfg)
    req, live = ddir / "healthcheck.active", ddir / "live.json"
    req.write_text(str(now_ms()), encoding="utf-8")
    try:
        t_wait = time.monotonic()
        while read_live(live, "cpu.pkg.temp_c") is None:
            if time.monotonic() - t_wait > 10:
                typer.echo("Nessun dato live dal collector: avviare 'hwdrift run' e riprovare.",
                           err=True)
                raise typer.Exit(1)
            time.sleep(0.5)
        start = now_ms()
        typer.echo("Health-check in corso (Ctrl+C per interrompere)...")
        res = run_healthcheck(
            lambda: read_live(live, "cpu.pkg.temp_c"),
            lambda: (read_live(live, "cpu.throttle_thermal") or 0.0) >= 0.5,
            duration or hc["duration_s"], hc["abort_temp_c"], hc["workers"],
            stale_limit_s=10.0)
    finally:
        req.unlink(missing_ok=True)
    conn = _open()
    ev = healthcheck_event(res, start)
    with conn:
        conn.execute("INSERT INTO events(ts, kind, source, detail) VALUES (?, ?, 'user', ?)",
                     (ev.ts_ms, ev.kind, json.dumps(ev.detail)))
    typer.echo(f"Health-check {res.reason}: {res.duration_s:.0f} s, temperatura massima "
               f"{res.max_temp if res.max_temp is not None else 'n/d'} °C")


@app.command()
def simulate(
    scenario: str = typer.Argument("healthy", help="scenario di guasto (vedi --list)"),
    days: float = typer.Option(30, help="giorni da simulare"),
    seed: int = typer.Option(1, help="seme casuale (riproducibilità)"),
    list_: bool = typer.Option(False, "--list", help="elenca gli scenari"),
) -> None:
    """Genera dati sintetici offline (settimane in pochi secondi) nel database."""
    from .sim.generator import generate
    from .sim.scenarios import DESCRIPTIONS

    if list_:
        for k, v in DESCRIPTIONS.items():
            typer.echo(f"{k:<16} {v}")
        return
    if not state.db_explicit:
        state.db = data_dir(state.cfg) / f"simulate-{scenario}.sqlite"
    conn = _open()
    if conn.execute("SELECT COUNT(*) FROM agg_1min").fetchone()[0]:
        typer.echo("Il database contiene già dati: usare --db con un file nuovo per la "
                   "simulazione.", err=True)
        raise typer.Exit(2)
    r = generate(conn, scenario, days=days, seed=seed, dt_s=30.0)
    typer.echo(f"Simulati {days} giorni ({scenario}): {r.minutes} aggregati, {r.events} eventi. "
               f"Ora: hwdrift --db {state.db} analyze")


@app.command()
def notify(once: bool = typer.Option(False, help="un solo controllo e poi esci")) -> None:
    """Notificatore non privilegiato: toast per errori immediati e allarmi."""
    from .alerts.notifier import Notifier

    n = Notifier(state.db, data_dir(state.cfg), state.cfg)
    if once:
        typer.echo(json.dumps(n.check(), indent=1))
    else:
        n.loop()


@app.command()
def status() -> None:
    """Stato sintetico: collector, episodi in corso, allarmi attivi."""
    from .alerts.notifier import Notifier

    n = Notifier(state.db, data_dir(state.cfg), state.cfg)
    s = n.check(persist=False)
    typer.echo(f"Collector: {s.get('collector')}")
    from .storage.schema import get_meta

    conn = _open(readonly=True)
    raw = get_meta(conn, "collectors_status")
    for src in json.loads(raw) if raw else []:
        if not src.get("ok"):
            why = src.get("last_error") or ("sospesa" if src.get("suspended") else "")
            typer.echo(f"  sorgente {src['name']}: non attiva {why}".rstrip())
    for o in s.get("ongoing", []):
        typer.echo(f"IN CORSO: {o['component']} {o['reason']} ({o['severity']})")
    for a in s.get("alerts", []):
        if a["level"] != "info":
            typer.echo(f"{a['level'].upper():<10} {a['title']}")


@app.command("init-config")
def init_config(path: Path = typer.Option(Path("hwdrift.yaml"), help="file da creare")) -> None:
    """Crea un file di configurazione di esempio."""
    from importlib import resources

    if path.exists():
        typer.echo(f"{path} esiste già.", err=True)
        raise typer.Exit(1)
    text = resources.files("hwdrift").joinpath("hwdrift.example.yaml").read_text(encoding="utf-8")
    path.write_text(text, encoding="utf-8")
    typer.echo(f"Creato {path}")


def _tasks(exe: str) -> list[tuple[str, list[str]]]:
    """``exe`` è già un comando quotato (es. ``"C:\\...\\hwdrift.exe"``).
    TODO(M5): verificare su Windows 11 il quoting di /TR con percorsi con spazi."""
    return [
        ("HWDrift Collector", ["schtasks", "/Create", "/F", "/TN", r"HWDrift\Collector",
                               "/SC", "ONLOGON", "/RL", "HIGHEST", "/TR", f"{exe} run"]),
        ("HWDrift Analisi", ["schtasks", "/Create", "/F", "/TN", r"HWDrift\Analyze",
                             "/SC", "MINUTE", "/MO", "15", "/TR", f"{exe} analyze"]),
        ("HWDrift Notificatore", ["schtasks", "/Create", "/F", "/TN", r"HWDrift\Notify",
                                  "/SC", "ONLOGON", "/TR", f"{exe} notify"]),
    ]


@schedule_app.command("install")
def schedule_install(apply: bool = typer.Option(False, help="crea davvero le attività "
                                                            "(default: mostra i comandi)")) -> None:
    """Attività pianificate: collector all'accesso (privilegi elevati), analisi ogni 15
    minuti e notificatore all'accesso (senza privilegi)."""
    import shutil
    import subprocess

    found = shutil.which("hwdrift")
    exe = f'"{found}"' if found else f'"{sys.executable}" -m hwdrift'
    for name, cmd in _tasks(exe):
        typer.echo(f"{name}: {' '.join(cmd)}")
        if apply:
            if sys.platform != "win32":
                typer.echo("  (solo su Windows)")
                continue
            r = subprocess.run(cmd, capture_output=True, text=True, check=False)
            typer.echo("  ok" if r.returncode == 0 else f"  errore: {r.stderr.strip()}")


@schedule_app.command("remove")
def schedule_remove(apply: bool = typer.Option(False, help="rimuove davvero le attività")) -> None:
    """Rimuove le attività pianificate di HWDrift."""
    import subprocess

    for tn in (r"HWDrift\Collector", r"HWDrift\Analyze", r"HWDrift\Notify"):
        cmd = ["schtasks", "/Delete", "/F", "/TN", tn]
        typer.echo(" ".join(cmd))
        if apply and sys.platform == "win32":
            subprocess.run(cmd, capture_output=True, text=True, check=False)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
