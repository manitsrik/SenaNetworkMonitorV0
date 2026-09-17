"""The link-quality queries run on both engines, so exercise them on SQLite.

PostgreSQL is what production uses, but the aggregation is written once for
both. Percentiles here are ranked with window functions rather than
percentile_cont for exactly that reason, and a query that silently returns
nothing would leave the dashboard looking merely quiet.
"""
from datetime import datetime, timedelta

import pytest

import database as database_module
from config import Config
from database import Database


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, 'DB_TYPE', 'sqlite')
    monkeypatch.setattr(Database, '_pool', None)
    monkeypatch.setattr(database_module.Config, 'DB_TYPE', 'sqlite')
    return Database(db_path=str(tmp_path / 'test.db'))


def add_site(db, name, ip):
    result = db.add_device(name, ip, device_type='vpnrouter', monitor_type='ping')
    return result['id'] if isinstance(result, dict) else result


def write_checks(db, device_id, rows, start=None, step=timedelta(minutes=1)):
    """rows: (status, response_time, packet_loss, rtt_min, rtt_max) oldest first."""
    conn = db.get_connection()
    cursor = db._cursor(conn)
    when = start or (datetime.now() - step * len(rows))
    for offset, row in enumerate(rows):
        checked_at = (when + step * offset).isoformat()
        cursor.execute(
            'INSERT INTO status_history '
            '(device_id, status, response_time, packet_loss, rtt_min, rtt_max, checked_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (device_id,) + tuple(row) + (checked_at,))
    conn.commit()
    db.release_connection(conn)


def test_status_history_takes_the_per_check_quality_columns(db):
    site = add_site(db, 'Cozi-Taksin-Jomthong', '10.12.1.2')
    db.update_device_status(site, 'up', 8.4, packet_loss=33.33, rtt_min=6.1, rtt_max=41.2)

    conn = db.get_connection()
    cursor = db._cursor(conn)
    cursor.execute('SELECT status, response_time, packet_loss, rtt_min, rtt_max '
                   'FROM status_history WHERE device_id = ?', (site,))
    row = db._row_to_dict(cursor.fetchone())
    db.release_connection(conn)

    assert row['response_time'] == 8.4
    assert row['packet_loss'] == pytest.approx(33.33)
    assert row['rtt_min'] == 6.1 and row['rtt_max'] == 41.2


def test_a_check_on_a_disabled_device_stores_no_quality_figures(db):
    site = add_site(db, 'BANGBUATHONG', '10.64.1.2')
    db.update_device(site, is_enabled=False)
    db.update_device_status(site, 'up', 5.0, packet_loss=0.0, rtt_min=4.0, rtt_max=6.0)

    conn = db.get_connection()
    cursor = db._cursor(conn)
    cursor.execute('SELECT status, packet_loss, rtt_min FROM status_history WHERE device_id = ?', (site,))
    row = db._row_to_dict(cursor.fetchone())
    db.release_connection(conn)

    # A disabled device is not being checked, so a 0% loss reading would be a
    # claim nobody made.
    assert row['status'] == 'disabled'
    assert row['packet_loss'] is None and row['rtt_min'] is None


def test_link_quality_summarises_reachability_latency_and_steadiness(db):
    site = add_site(db, 'Cozi-Taksin-Jomthong', '10.12.1.2')
    rows = [('up', 10.0, 0.0, 8.0, 12.0)] * 18
    rows += [('slow', 300.0, 33.33, 20.0, 480.0)] * 2
    write_checks(db, site, rows)

    stats = db.get_link_quality([site], hours=24)[site]

    assert stats['checks'] == 20
    assert stats['up_n'] == 18 and stats['slow_n'] == 2 and stats['down_n'] == 0
    assert stats['reach_pct'] == 100.0        # slow still answered
    assert stats['rtt_min'] == 8.0 and stats['rtt_max'] == 480.0
    # Jitter is the spread inside a check, averaged: 18 checks of 4 ms and 2 of 460.
    assert stats['jitter'] == pytest.approx((18 * 4 + 2 * 460) / 20, abs=0.01)
    assert stats['loss_pct'] == pytest.approx((2 * 33.33) / 20, abs=0.01)
    assert stats['loss_samples'] == 20


def test_p95_follows_the_slow_tail_not_the_average(db):
    # 90 fast replies and 10 slow ones: the average stays comfortable while the
    # tail a user actually notices sits ninety times higher.
    site = add_site(db, 'slow-tail', '10.0.0.9')
    write_checks(db, site, [('up', 10.0, 0.0, 9.0, 11.0)] * 90 + [('slow', 900.0, 0.0, 800.0, 1000.0)] * 10)

    stats = db.get_link_quality([site], hours=24)[site]

    assert stats['rtt_avg'] == pytest.approx(99.0, abs=0.5)
    assert stats['p95'] == 900.0


def test_flaps_count_every_crossing_not_the_time_spent_down(db):
    steady = add_site(db, 'one-long-outage', '10.0.0.1')
    flapping = add_site(db, 'six-short-outages', '10.0.0.2')

    up = ('up', 5.0, 0.0, 4.0, 6.0)
    down = ('down', None, 100.0, None, None)
    write_checks(db, steady, [up] * 2 + [down] * 6 + [up] * 2)
    write_checks(db, flapping, ([up] + [down]) * 5)

    quality = db.get_link_quality([steady, flapping], hours=24)

    # Both sites were unreachable for six checks; only one of them is unstable.
    assert quality[steady]['flaps'] == 2
    assert quality[flapping]['flaps'] == 9
    assert quality[steady]['reach_pct'] == pytest.approx(40.0)


def test_a_site_that_never_replied_reports_zero_reach_and_no_latency(db):
    site = add_site(db, 'Kith-Samrong', '10.245.1.2')
    write_checks(db, site, [('down', None, 100.0, None, None)] * 30)

    stats = db.get_link_quality([site], hours=24)[site]

    assert stats['reach_pct'] == 0.0
    assert stats['rtt_avg'] is None and stats['p95'] is None
    assert stats['loss_pct'] == 100.0
    # Down for the whole window is not a flap: nothing changed.
    assert stats['flaps'] == 0


def test_rows_written_before_the_columns_existed_do_not_read_as_a_perfect_link(db):
    site = add_site(db, 'legacy-rows', '10.0.0.3')
    write_checks(db, site, [('up', 7.0, None, None, None)] * 10)

    stats = db.get_link_quality([site], hours=24)[site]

    assert stats['rtt_avg'] == 7.0
    assert stats['loss_pct'] is None
    assert stats['jitter'] is None
    assert stats['loss_samples'] == 0


def test_latency_series_reports_both_percentiles_per_bucket(db):
    # One 15-minute bucket holding 18 fast replies and 2 slow ones: the median
    # must stay with the 18, the p95 must find the slow pair. Two, not one -
    # the 95th of twenty values is the 19th, so a single outlier sits above the
    # percentile by definition rather than because anything is wrong.
    #
    # Buckets are cut on a fixed epoch grid, so the run is anchored inside one
    # rather than left to fall wherever the clock happens to be.
    site = add_site(db, 'trend', '10.0.0.4')
    bucket_start = datetime.fromtimestamp((int(datetime.now().timestamp()) - 7200) // 900 * 900 + 30)
    write_checks(db, site, [('up', 8.0, 0.0, 7.0, 9.0)] * 18 + [('slow', 400.0, 0.0, 380.0, 420.0)] * 2,
                 start=bucket_start, step=timedelta(seconds=20))

    series = db.get_latency_percentile_series([site], hours=24, buckets=96)

    assert len(series['p50']) == 96
    assert len(series['labels']) == 96
    live = [(m, p) for m, p in zip(series['p50'], series['p95']) if p is not None]
    assert len(live) == 1, 'the whole run belongs to a single bucket'
    median, p95 = live[0]
    assert median == 8.0, 'one outlier must not drag the median'
    assert p95 == 400.0, 'p95 must find the outlier'


def test_buckets_with_no_reply_stay_empty_rather_than_being_bridged(db):
    site = add_site(db, 'gap', '10.0.0.5')
    # Checks only in the oldest part of the window, then nothing.
    write_checks(db, site, [('up', 9.0, 0.0, 8.0, 10.0)] * 5,
                 start=datetime.now() - timedelta(hours=20))

    series = db.get_latency_percentile_series([site], hours=24, buckets=48)

    assert any(v is None for v in series['p50']), 'a monitoring gap must stay a gap'
    assert any(v is not None for v in series['p50'])


def test_no_devices_returns_empty_rather_than_every_device(db):
    assert db.get_link_quality([], hours=24) == {}
    assert db.get_latency_percentile_series([], hours=24)['p50'] == []
