# SPDX-License-Identifier: Apache-2.0
from hwdrift.model import EventRecord, Quality, Sample
from hwdrift.storage.schema import SCHEMA_VERSION, connect, get_meta, migrate
from hwdrift.storage.writer import BatchWriter, aggregate


def smp(ch, v, ts, q=Quality.OK):
    return Sample(ts, "t", ch, "cpu", ch, v, "°C", ch, q)


def test_migration_idempotent_and_machine_id(conn):
    assert migrate(conn) == SCHEMA_VERSION
    mid = get_meta(conn, "machine_id")
    assert mid and len(mid) == 32
    migrate(conn)
    assert get_meta(conn, "machine_id") == mid
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_aggregate_excludes_bad_quality():
    med, lo, hi, n, frac = aggregate([(1.0, 0), (3.0, 0), (99.0, int(Quality.GLITCH)),
                                      (2.0, 0)])
    assert (med, lo, hi, n) == (2.0, 1.0, 3.0, 4)
    assert frac == 0.75
    assert aggregate([(None, 4)]) == (None, None, None, 1, 0.0)


def test_batch_flush_minutes_events_and_prune(conn):
    w = BatchWriter(conn, flush_s=60, raw_retention_h=1)
    t0 = 1_700_000_000_000 - (1_700_000_000_000 % 60_000)
    w.add([smp("cpu.pkg.temp_c", 40.0 + i % 3, t0 + i * 1000) for i in range(120)])
    w.add_event(EventRecord(t0, "system.collector_start"))
    assert not w.due(t0)
    assert w.due(t0 + 61_000)
    w.flush(t0 + 90_000)  # solo i minuti completi vengono aggregati (il secondo è in corso)
    assert conn.execute("SELECT COUNT(*) FROM raw_samples").fetchone()[0] == 120
    assert conn.execute("SELECT COUNT(*) FROM agg_1min").fetchone()[0] == 1
    row = conn.execute("SELECT median, min, max, n, valid_frac FROM agg_1min").fetchone()
    assert tuple(row) == (41.0, 40.0, 42.0, 60, 1.0)
    assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
    assert get_meta(conn, "heartbeat_ts") == str(t0 + 90_000)
    # la potatura elimina il grezzo più vecchio della ritenzione (1 h)
    w._last_prune_ms = 0
    w.flush(t0 + 3 * 3_600_000)
    assert conn.execute("SELECT COUNT(*) FROM raw_samples").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM agg_1min").fetchone()[0] == 2


def test_unmapped_samples_not_stored(conn):
    w = BatchWriter(conn)
    x = Sample(0, "t", "id", "cpu", "raw", 1.0, "")
    w.add([x])
    w.flush(120_000, final=True)
    assert conn.execute("SELECT COUNT(*) FROM raw_samples").fetchone()[0] == 0


def test_rt_events_written_immediately(conn):
    w = BatchWriter(conn)
    rid = w.open_rt_event(1000, "cpu", "thermal", "error", 95.0, {})
    assert conn.execute("SELECT severity FROM rt_events WHERE id=?", (rid,)).fetchone()[0] == \
        "error"
    w.update_rt_event(rid, peak=99.0, end_ts=5000)
    row = conn.execute("SELECT peak, end_ts FROM rt_events").fetchone()
    assert tuple(row) == (99.0, 5000)


def test_event_dedup_by_ext_id(conn):
    w = BatchWriter(conn)
    for _ in range(3):
        w.add_event(EventRecord(1, "hw.whea_corrected", ext_id="WHEA:42"))
    w.flush(60_000, final=True)
    assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1


def test_readonly_connection(tmp_path, conn):
    path = conn.execute("PRAGMA database_list").fetchone()[2]
    ro = connect(path, readonly=True)
    import sqlite3

    import pytest

    with pytest.raises(sqlite3.OperationalError):
        ro.execute("INSERT INTO meta(key, value) VALUES ('x', 'y')")


def test_import_does_not_overwrite_collector_data(conn):
    from hwdrift.storage.writer import write_minute_aggregates

    w = BatchWriter(conn)
    w.add([smp("cpu.pkg.temp_c", 50.0, 60_000 + i * 1000) for i in range(60)])
    w.flush(200_000, final=True)
    n = write_minute_aggregates(conn, [smp("cpu.pkg.temp_c", 99.0, 60_000)])
    assert n == 0
    assert conn.execute("SELECT median FROM agg_1min").fetchone()[0] == 50.0
