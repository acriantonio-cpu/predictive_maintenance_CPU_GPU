# SPDX-License-Identifier: Apache-2.0
"""Schema SQLite versionato con migrazioni (sezione 5).

Regole: timestamp UTC in millisecondi interi; un solo processo scrive i dati
grezzi (``writer.py``); il worker scrive solo le tabelle di analisi.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

# Ogni migrazione porta lo schema dalla versione i alla i+1.
_M1 = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS channels (
    id       INTEGER PRIMARY KEY,
    name     TEXT NOT NULL UNIQUE,
    unit     TEXT NOT NULL DEFAULT '',
    source   TEXT NOT NULL DEFAULT '',
    raw_name TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS raw_samples (
    ts         INTEGER NOT NULL,
    channel_id INTEGER NOT NULL REFERENCES channels(id),
    value      REAL,
    quality    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_raw_ch_ts ON raw_samples(channel_id, ts);
CREATE INDEX IF NOT EXISTS ix_raw_ts ON raw_samples(ts);
CREATE TABLE IF NOT EXISTS agg_1min (
    ts         INTEGER NOT NULL,
    channel_id INTEGER NOT NULL REFERENCES channels(id),
    median     REAL,
    min        REAL,
    max        REAL,
    n          INTEGER NOT NULL,
    valid_frac REAL NOT NULL,
    PRIMARY KEY (channel_id, ts)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_agg_ts ON agg_1min(ts);
CREATE TABLE IF NOT EXISTS events (
    id     INTEGER PRIMARY KEY,
    ts     INTEGER NOT NULL,
    kind   TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'auto',
    detail TEXT NOT NULL DEFAULT '{}',
    note   TEXT NOT NULL DEFAULT '',
    ext_id TEXT
);
CREATE INDEX IF NOT EXISTS ix_events_ts ON events(ts);
CREATE UNIQUE INDEX IF NOT EXISTS ux_events_ext ON events(kind, ext_id) WHERE ext_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS rt_events (
    id        INTEGER PRIMARY KEY,
    start_ts  INTEGER NOT NULL,
    end_ts    INTEGER,
    component TEXT NOT NULL,
    reason    TEXT NOT NULL,
    severity  TEXT NOT NULL,
    peak      REAL,
    detail    TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_rt_start ON rt_events(start_ts);
CREATE TABLE IF NOT EXISTS windows (
    id         INTEGER PRIMARY KEY,
    component  TEXT NOT NULL,
    start_ts   INTEGER NOT NULL,
    end_ts     INTEGER NOT NULL,
    regime     TEXT,
    power_mean REAL NOT NULL,
    power_cv   REAL NOT NULL,
    temp_slope REAL NOT NULL,
    throttled  INTEGER NOT NULL DEFAULT 0,
    summary    TEXT NOT NULL DEFAULT '{}',
    ind_done   INTEGER NOT NULL DEFAULT 0,
    UNIQUE (component, start_ts)
);
CREATE INDEX IF NOT EXISTS ix_windows_ts ON windows(start_ts);
CREATE TABLE IF NOT EXISTS indicators (
    id        INTEGER PRIMARY KEY,
    ts        INTEGER NOT NULL,
    indicator TEXT NOT NULL,
    regime    TEXT NOT NULL,
    level     TEXT NOT NULL,           -- 'window' | 'daily'
    value     REAL NOT NULL,
    window_id INTEGER REFERENCES windows(id),
    n         INTEGER NOT NULL DEFAULT 1,
    UNIQUE (indicator, regime, level, ts)
);
CREATE INDEX IF NOT EXISTS ix_ind ON indicators(indicator, regime, level, ts);
CREATE TABLE IF NOT EXISTS chart_state (
    chart_id    TEXT NOT NULL,
    segment     INTEGER NOT NULL,
    phase       TEXT NOT NULL,          -- 'I' | 'II'
    provisional INTEGER NOT NULL DEFAULT 1,
    start_ts    INTEGER NOT NULL,
    locked_ts   INTEGER,
    closed_ts   INTEGER,
    center      REAL,
    sigma       REAL,
    mr_bar      REAL,
    ucl         REAL,
    lcl         REAL,
    ucl_mr      REAL,
    n_phase1    INTEGER NOT NULL DEFAULT 0,
    params      TEXT NOT NULL DEFAULT '{}',
    updated_ts  INTEGER NOT NULL,
    PRIMARY KEY (chart_id, segment)
);
CREATE TABLE IF NOT EXISTS signals (
    id       INTEGER PRIMARY KEY,
    chart_id TEXT NOT NULL,
    segment  INTEGER NOT NULL,
    ts       INTEGER NOT NULL,
    rule     TEXT NOT NULL,
    side     TEXT NOT NULL,             -- 'upper' | 'lower'
    value    REAL,
    points   TEXT NOT NULL DEFAULT '[]',
    severity TEXT NOT NULL DEFAULT 'info',
    label    TEXT NOT NULL DEFAULT 'maintenance', -- 'maintenance'|'configuration'|'provisional'
    UNIQUE (chart_id, segment, ts, rule)
);
CREATE INDEX IF NOT EXISTS ix_signals_ts ON signals(ts);
CREATE TABLE IF NOT EXISTS diagnoses (
    id          INTEGER PRIMARY KEY,
    ts          INTEGER NOT NULL,
    rule_id     TEXT NOT NULL,
    title       TEXT NOT NULL,
    confidence  TEXT NOT NULL,
    supports    TEXT NOT NULL DEFAULT '[]',
    contradicts TEXT NOT NULL DEFAULT '[]',
    actions     TEXT NOT NULL DEFAULT '[]',
    charts      TEXT NOT NULL DEFAULT '[]',
    active      INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS alerts (
    id       INTEGER PRIMARY KEY,
    key      TEXT NOT NULL UNIQUE,
    first_ts INTEGER NOT NULL,
    last_ts  INTEGER NOT NULL,
    level    TEXT NOT NULL,             -- 'info' | 'attention' | 'action'
    title    TEXT NOT NULL,
    message  TEXT NOT NULL,
    active   INTEGER NOT NULL DEFAULT 1
);
"""

MIGRATIONS: list[str] = [_M1]
SCHEMA_VERSION = len(MIGRATIONS)


def connect(path: str | Path, readonly: bool = False, timeout: float = 30.0) -> sqlite3.Connection:
    """Apre il database. In sola lettura usa ``mode=ro`` (notificatore, report)."""
    p = Path(path)
    if readonly:
        uri = p.resolve().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=timeout)
    else:
        p.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(p), timeout=timeout)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def migrate(conn: sqlite3.Connection) -> int:
    """Applica le migrazioni mancanti; restituisce la versione finale."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise RuntimeError(
            f"database creato da una versione più recente (schema {version} > {SCHEMA_VERSION})"
        )
    for i in range(version, SCHEMA_VERSION):
        with conn:
            conn.executescript(MIGRATIONS[i])
            conn.execute(f"PRAGMA user_version={i + 1}")
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES ('machine_id', ?)",
            (uuid.uuid4().hex,),  # ID casuale locale, NON derivato dall'hardware
        )
        conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)",
                     (str(SCHEMA_VERSION),))
    return SCHEMA_VERSION


def open_db(path: str | Path) -> sqlite3.Connection:
    conn = connect(path)
    migrate(conn)
    return conn


def get_meta(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (key, value))


def channel_ids(conn: sqlite3.Connection) -> dict[str, int]:
    return {r[1]: r[0] for r in conn.execute("SELECT id, name FROM channels")}


def ensure_channel(conn: sqlite3.Connection, name: str, unit: str = "", source: str = "",
                   raw_name: str = "", cache: dict[str, int] | None = None) -> int:
    if cache is not None and name in cache:
        return cache[name]
    conn.execute(
        "INSERT OR IGNORE INTO channels(name, unit, source, raw_name) VALUES (?, ?, ?, ?)",
        (name, unit, source, raw_name),
    )
    cid = conn.execute("SELECT id FROM channels WHERE name=?", (name,)).fetchone()[0]
    if cache is not None:
        cache[name] = cid
    return int(cid)

