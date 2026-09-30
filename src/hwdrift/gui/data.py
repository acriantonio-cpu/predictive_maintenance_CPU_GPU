# SPDX-License-Identifier: Apache-2.0
"""Accesso ai dati per la GUI: tempo reale, stato, carte, configurazione, pacchetto diagnostico."""

from __future__ import annotations

import json
import os
import platform
import sqlite3
import subprocess
import sys
import tempfile
import time
import zipfile
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .. import __version__
from ..config import ConfigError, load_config
from ..model import now_ms

# ------------------------------------------------------------------- grafici live
# (titolo, unità, [(canale, etichetta)]) — una sola unità per grafico
LIVE_CHARTS: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("CPU: temperatura", "°C", [("cpu.pkg.temp_c", "package"), ("mb.temp_c", "scheda madre")]),
    ("GPU: temperatura", "°C", [("gpu0.temp_edge_c", "edge"), ("gpu0.temp_hotspot_c", "hotspot"),
                                ("gpu0.temp_mem_c", "memoria")]),
    ("CPU: potenza", "W", [("cpu.pkg.power_w", "package")]),
    ("GPU: potenza", "W", [("gpu0.power_w", "scheda")]),
    ("Ventole", "rpm", [("cpu.fan_rpm", "CPU"), ("chassis.fan1_rpm", "case"),
                        ("gpu0.fan_rpm", "GPU")]),
    ("Carico", "%", [("cpu.load_pct", "CPU"), ("gpu0.util_pct", "GPU"),
                     ("gpu0.fan_pct", "ventola GPU")]),
    ("Clock", "MHz", [("cpu.clock_eff_mhz", "CPU effettivo"), ("gpu0.clock_mhz", "GPU")]),
    ("Throttling (1 = attivo)", "", [("cpu.throttle_thermal", "CPU termico"),
                                     ("gpu0.throttle_thermal", "GPU termico"),
                                     ("gpu0.throttle_power", "GPU potenza")]),
]
KPI = [("CPU temperatura", "cpu.pkg.temp_c", "°C"), ("CPU potenza", "cpu.pkg.power_w", "W"),
       ("GPU temperatura", "gpu0.temp_edge_c", "°C"), ("GPU potenza", "gpu0.power_w", "W"),
       ("Ventola CPU", "cpu.fan_rpm", "rpm"), ("Ventola GPU", "gpu0.fan_rpm", "rpm")]
ALL_LIVE_CHANNELS = sorted({ch for _, _, ser in LIVE_CHARTS for ch, _ in ser})


def read_live(path: Path, max_age_s: float = 5.0) -> tuple[int, dict[str, float]] | None:
    """Ultimo snapshot pubblicato dal collector, o ``None`` se assente/vecchio/illeggibile."""
    for _ in range(2):  # su Windows la sostituzione atomica può collidere con la lettura
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            time.sleep(0.02)
            continue
        if not isinstance(data, dict):
            return None
        ts = int(data.get("ts", 0))
        vals = data.get("values", {})
        if (now_ms() - ts) / 1000 > max_age_s or not isinstance(vals, dict):
            return None
        return ts, {k: float(v) for k, v in vals.items() if isinstance(v, (int, float))}
    return None


@dataclass
class LiveBuffer:
    """Buffer circolare per canale: storia dal database + punti live."""

    window_s: float = 3600.0
    data: dict[str, deque[tuple[int, float]]] = field(default_factory=dict)

    def push(self, ts_ms: int, values: dict[str, float]) -> None:
        cutoff = ts_ms - int(self.window_s * 1000)
        for ch, v in values.items():
            dq = self.data.setdefault(ch, deque())
            if dq and ts_ms <= dq[-1][0]:
                continue
            dq.append((ts_ms, v))
            while dq and dq[0][0] < cutoff:
                dq.popleft()

    def backfill(self, conn: sqlite3.Connection, channels: list[str], since_ms: int) -> None:
        """Storia recente: mediane al minuto + campioni grezzi più recenti (il collector li
        scrive ogni 60 s), così i grafici non partono vuoti."""
        ids = {r[1]: r[0] for r in conn.execute("SELECT id, name FROM channels")}
        for ch in channels:
            if ch not in ids:
                continue
            agg = conn.execute(
                "SELECT ts + 30000, median FROM agg_1min WHERE channel_id=? AND ts>=? AND "
                "median IS NOT NULL ORDER BY ts", (ids[ch], since_ms)).fetchall()
            last_agg = agg[-1][0] if agg else since_ms
            raw = conn.execute(
                "SELECT ts, value FROM raw_samples WHERE channel_id=? AND ts>? AND quality=0 "
                "AND value IS NOT NULL ORDER BY ts", (ids[ch], last_agg)).fetchall()
            old = self.data.get(ch, deque())
            merged = deque((int(t), float(v)) for t, v in [*agg, *raw])
            last = merged[-1][0] if merged else -1
            merged.extend(p for p in old if p[0] > last)
            self.data[ch] = merged

    def series(self, ch: str, since_ms: int, max_points: int = 600) -> list[tuple[int, float]]:
        pts = [p for p in self.data.get(ch, ()) if p[0] >= since_ms]
        if len(pts) > max_points:
            step = len(pts) / max_points
            pts = [pts[int(i * step)] for i in range(max_points)] + [pts[-1]]
        return pts

    def latest(self, ch: str) -> float | None:
        dq = self.data.get(ch)
        return dq[-1][1] if dq else None


# ------------------------------------------------------------------------ stato
def collect_status(conn: sqlite3.Connection, cfg: dict[str, Any]) -> dict[str, Any]:
    from ..quality import watchdog
    from ..reporting.html_report import ReportBuilder

    rb = ReportBuilder(conn, cfg)
    states = rb.chart_states()
    _, tiles = rb.overall(states)
    alerts = [dict(r) for r in conn.execute(
        "SELECT key, level, title, message, first_ts FROM alerts WHERE active=1 ORDER BY CASE "
        "level WHEN 'action' THEN 0 WHEN 'attention' THEN 1 ELSE 2 END, last_ts DESC")]
    diags = []
    for d in conn.execute("SELECT * FROM diagnoses WHERE active=1 ORDER BY ts DESC"):
        diags.append({"title": d["title"], "confidence": d["confidence"],
                      "supports": json.loads(d["supports"]), "contradicts": json.loads(
                          d["contradicts"]), "actions": json.loads(d["actions"]),
                      "level": rb._diag_level(d["rule_id"])})
    rt = [dict(r) for r in conn.execute(
        "SELECT * FROM rt_events WHERE start_ts >= ? ORDER BY start_ts DESC LIMIT 100",
        (now_ms() - 30 * 86_400_000,))]
    health = watchdog.check(conn, cfg["alerts"]["stale_heartbeat_min"])
    return {"tiles": tiles, "alerts": alerts, "diagnoses": diags, "rt": rt, "health": health,
            "charts": len(states)}


def list_charts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    out = []
    for r in conn.execute("SELECT * FROM chart_state WHERE closed_ts IS NULL ORDER BY chart_id"):
        d = dict(r)
        d["params"] = json.loads(d["params"] or "{}")
        ind, reg, lvl = d["chart_id"].split("|")
        d.update(indicator=ind, regime=reg, level=lvl)
        out.append(d)
    return out


def chart_series(conn: sqlite3.Connection, st: dict[str, Any]) -> dict[str, Any]:
    rows = conn.execute("SELECT ts, value FROM indicators WHERE indicator=? AND regime=? AND "
                        "level=? AND ts>=? ORDER BY ts",
                        (st["indicator"], st["regime"], st["level"], st["start_ts"])).fetchall()
    sigs: dict[int, str] = {}
    for r in conn.execute("SELECT ts, rule, side, label FROM signals WHERE chart_id=? AND "
                          "segment=? ORDER BY ts", (st["chart_id"], st["segment"])):
        txt = f"{r['rule']} {'sopra' if r['side'] == 'upper' else 'sotto'}"
        if r["label"] != "maintenance":
            txt += f" [{r['label']}]"
        sigs[r["ts"]] = f"{sigs[r['ts']]}; {txt}" if r["ts"] in sigs else txt
    return {"ts": [int(r[0]) for r in rows], "values": [float(r[1]) for r in rows],
            "signals": sigs}


def list_events(conn: sqlite3.Connection, days: int = 90) -> list[sqlite3.Row]:
    return conn.execute("SELECT id, ts, kind, source, note, detail FROM events WHERE ts>=? "
                        "ORDER BY ts DESC LIMIT 500", (now_ms() - days * 86_400_000,)).fetchall()


# ------------------------------------------------------------------ configurazione
@dataclass(frozen=True)
class Field:
    key: str  # percorso con punti, es. "sources.lhm.url"
    label: str
    kind: str  # "float" | "int" | "bool" | "str" | "choice" | "list"
    choices: tuple[str, ...] = ()
    help: str = ""


CONFIG_FIELDS: list[tuple[str, list[Field]]] = [
    ("Campionamento", [
        Field("sampling.interval_s", "Intervallo di campionamento (s)", "float",
              help="0,5–5 s. Più corto = più carico sul PC."),
        Field("sampling.cpu_budget_pct", "Budget CPU del collector (% di un core)", "float"),
        Field("sampling.adaptive", "Allunga l'intervallo se supera il budget", "bool"),
    ]),
    ("Sorgenti", [
        Field("sources.lhm.enabled", "LibreHardwareMonitor", "bool"),
        Field("sources.lhm.mode", "Modalità LHM", "choice", ("web", "dll"),
              "web = server web di LHM su loopback; dll = pythonnet (richiede amministratore)"),
        Field("sources.lhm.url", "URL del server web di LHM (solo loopback)", "str"),
        Field("sources.nvml.enabled", "GPU NVIDIA (NVML)", "bool"),
        Field("sources.eventlog.enabled", "Registro eventi di Windows (WHEA, TDR, ...)", "bool"),
        Field("sources.perfcounters.enabled", "Contatori di prestazione (clock effettivo)",
              "bool"),
        Field("sources.sysinfo.enabled", "Versioni driver/BIOS come eventi", "bool"),
    ]),
    ("Riferimento e limiti", [
        Field("profile.reference.mode", "Temperatura di riferimento (T_rif)", "choice",
              ("channel", "user", "none"), "channel = sensore interno (proxy ambiente)"),
        Field("profile.reference.channel", "Canale di riferimento", "str"),
        Field("profile.reference.value_c", "Valore fisso di T_rif (°C, modalità 'user')", "float"),
        Field("profile.cpu.tjmax_c", "Tjmax CPU (°C)", "float"),
        Field("profile.gpu.thermal_limit_c", "Limite termico GPU (°C)", "float"),
        Field("profile.baseline_state", "Stato del PC all'inizio del baseline", "choice",
              ("unknown", "clean")),
    ]),
    ("Analisi e allarmi", [
        Field("regimes.mode", "Confini dei regimi di carico", "choice", ("fixed", "adaptive")),
        Field("spc.phase1_min_days", "Giorni minimi di Fase I", "int"),
        Field("alerts.action_budget_per_month", "Budget di allarmi 'azione' al mese", "int"),
        Field("alerts.toast", "Notifiche toast", "bool"),
        Field("game_safe.enabled", "Modalità game-safe", "bool"),
        Field("game_safe.processes", "Processi che attivano game-safe (separati da virgola)",
              "list"),
    ]),
]
ALL_FIELDS = [f for _, fs in CONFIG_FIELDS for f in fs]


def get_path(d: dict[str, Any], key: str) -> Any:
    cur: Any = d
    for part in key.split("."):
        cur = cur[part]
    return cur


def set_path(d: dict[str, Any], key: str, value: Any) -> None:
    parts = key.split(".")
    cur = d
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = cur[part] = {}
        cur = nxt
    cur[parts[-1]] = value


def parse_field(f: Field, text: str | bool) -> Any:
    if f.kind == "bool":
        return bool(text)
    s = str(text).strip()
    if f.kind == "float":
        return float(s.replace(",", "."))
    if f.kind == "int":
        return int(float(s.replace(",", ".")))
    if f.kind == "list":
        return [x.strip() for x in s.split(",") if x.strip()]
    return s


def save_config(path: Path, changes: dict[str, Any] | None = None,
                raw_text: str | None = None) -> dict[str, Any]:
    """Valida e salva. ``changes`` = chiavi con punti da aggiornare nel file dell'utente;
    ``raw_text`` = contenuto YAML completo (editor avanzato). Solleva ``ConfigError`` (il file
    esistente non viene toccato) se la configurazione risultante non è valida. Mantiene una
    copia ``.bak``. I commenti del file vengono persi se si salva dal modulo."""
    if raw_text is not None:
        text = raw_text
    else:
        current: dict[str, Any] = {}
        if path.exists():
            current = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(current, dict):
                raise ConfigError("il file di configurazione non contiene un dizionario")
        for k, v in (changes or {}).items():
            set_path(current, k, v)
        text = yaml.safe_dump(current, allow_unicode=True, sort_keys=False)
    fd, tmp = tempfile.mkstemp(suffix=".yaml")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        cfg = load_config(tmp)  # solleva ConfigError se non valida
    finally:
        os.unlink(tmp)
    if path.exists():
        path.with_suffix(path.suffix + ".bak").write_text(path.read_text(encoding="utf-8"),
                                                          encoding="utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return cfg


# ----------------------------------------------------------------- pacchetto log
def make_bundle(zip_path: Path, home: Path, db: Path, config_path: Path | None) -> list[str]:
    """Pacchetto diagnostico: log, stato, configurazione, versioni. NON include il database
    né i dati grezzi (per quelli c'è l'export, anonimo per default)."""
    names: list[str] = []
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for fn in ("hwdrift.log", "hwdrift.log.1", "hwdrift.log.2", "status.json",
                   "notifier_state.json"):
            p = home / fn
            if p.exists():
                z.write(p, fn)
                names.append(fn)
        if config_path is not None and config_path.exists():
            z.write(config_path, "hwdrift.yaml")
            names.append("hwdrift.yaml")
        info = {"hwdrift": __version__, "python": sys.version, "platform": platform.platform(),
                "frozen": bool(getattr(sys, "frozen", False)), "database": str(db),
                "created": time.strftime("%Y-%m-%d %H:%M:%S")}
        if db.exists():
            try:
                from ..storage.schema import connect, get_meta

                conn = connect(db, readonly=True)
                info["collectors_status"] = json.loads(get_meta(conn, "collectors_status")
                                                       or "[]")
                info["heartbeat_ts"] = get_meta(conn, "heartbeat_ts")
                info["schema_version"] = get_meta(conn, "schema_version")
                conn.close()
            except (sqlite3.Error, ValueError):
                info["database_error"] = "non leggibile"
        z.writestr("info.json", json.dumps(info, indent=1, ensure_ascii=False))
        names.append("info.json")
    return names


def tail(path: Path, max_bytes: int = 60_000) -> str:
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - max_bytes))
            return fh.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


# ------------------------------------------------------------- processo collector
class CollectorProcess:
    """Avvia e ferma il collector come sottoprocesso (modalità normale o demo)."""

    def __init__(self) -> None:
        self.proc: subprocess.Popen[bytes] | None = None

    @staticmethod
    def command(args: list[str]) -> list[str]:
        if getattr(sys, "frozen", False):
            return [sys.executable, *args]  # l'eseguibile della GUI accetta anche i comandi CLI
        return [sys.executable, "-m", "hwdrift", *args]

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, args: list[str], env_extra: dict[str, str] | None = None) -> None:
        if self.alive():
            return
        flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        env = {**os.environ, **(env_extra or {})}
        self.proc = subprocess.Popen(self.command(args), env=env, creationflags=flags,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def start_elevated(self, args: list[str]) -> bool:
        """UAC: il collector con privilegi elevati (sensori a basso livello). Solo Windows."""
        if sys.platform != "win32":
            return False
        import ctypes

        cmd = self.command(args)
        params = subprocess.list2cmdline(cmd[1:])
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", cmd[0], params, None, 0)  # type: ignore[attr-defined]
        return rc > 32

    def stop(self, home: Path, timeout: float = 8.0) -> None:
        """Arresto pulito via ``stop.request`` (funziona anche per un collector elevato)."""
        (home / "stop.request").write_text("1", encoding="utf-8")
        if self.proc is not None:
            try:
                self.proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.proc.terminate()
            self.proc = None
