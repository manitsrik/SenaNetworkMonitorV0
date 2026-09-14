"""Regression tests for escalation bookkeeping.

`mark_device_escalated` used to carry a duplicated copy of the body of
`get_active_maintenance`.  That copy referenced `ph` and `now`, neither of which
exists in its scope, so every call raised ``NameError: name 'ph' is not
defined`` *after* the UPDATE had already committed.

The exception escaped into ``check_alert_escalations`` (app.py), which meant the
escalation pass died part-way through: devices queued behind the first one were
skipped, and the resource-alert escalation that runs after the device loop never
executed at all.
"""
from datetime import datetime, timedelta

from config import Config
from database import Database


def _make_db(tmp_path, monkeypatch, name='escalation.db'):
    monkeypatch.setattr(Config, 'DB_TYPE', 'sqlite')
    return Database(str(tmp_path / name))


def _add_device(db, name, ip, status='down'):
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO devices (name, ip_address, device_type, status) VALUES (?, ?, ?, ?)",
        (name, ip, 'server', status),
    )
    device_id = cursor.lastrowid
    conn.commit()
    db.release_connection(conn)
    return device_id


def _escalation_level(db, device_id):
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT escalation_level FROM devices WHERE id = ?", (device_id,))
    level = cursor.fetchone()[0]
    db.release_connection(conn)
    return level


def test_mark_device_escalated_records_the_level(tmp_path, monkeypatch):
    db = _make_db(tmp_path, monkeypatch)
    device_id = _add_device(db, 'Router A', '10.0.0.1')

    # Used to raise NameError before the duplicated block was removed.
    db.mark_device_escalated(device_id)

    assert _escalation_level(db, device_id) == 1


def test_mark_device_escalated_honours_an_explicit_level(tmp_path, monkeypatch):
    db = _make_db(tmp_path, monkeypatch)
    device_id = _add_device(db, 'Router B', '10.0.0.2')

    db.mark_device_escalated(device_id, level=3)

    assert _escalation_level(db, device_id) == 3


def test_mark_device_escalated_returns_nothing(tmp_path, monkeypatch):
    """The stray copy ended in `return windows`, leaking maintenance rows."""
    db = _make_db(tmp_path, monkeypatch)
    device_id = _add_device(db, 'Router C', '10.0.0.3')

    assert db.mark_device_escalated(device_id) is None


def test_whole_escalation_batch_is_processed(tmp_path, monkeypatch):
    """Mirrors the loop in app.check_alert_escalations.

    The NameError aborted that loop on its first iteration, so only one device
    was ever escalated per pass and the resource-alert stage that follows it was
    unreachable.
    """
    db = _make_db(tmp_path, monkeypatch)
    device_ids = [
        _add_device(db, 'Device %d' % i, '10.0.1.%d' % i) for i in range(1, 4)
    ]

    reached_resource_stage = False
    for device_id in device_ids:
        db.mark_device_escalated(device_id)
    reached_resource_stage = True

    assert reached_resource_stage
    assert [_escalation_level(db, d) for d in device_ids] == [1, 1, 1]


def test_mark_device_escalated_can_be_called_repeatedly(tmp_path, monkeypatch):
    """The stray block released an already-released connection a second time."""
    db = _make_db(tmp_path, monkeypatch)
    device_id = _add_device(db, 'Router E', '10.0.4.1')

    for level in (1, 2, 3):
        db.mark_device_escalated(device_id, level=level)

    assert _escalation_level(db, device_id) == 3


def test_get_active_maintenance_still_works(tmp_path, monkeypatch):
    """Guards the original function the stray block was copied from."""
    db = _make_db(tmp_path, monkeypatch)
    device_id = _add_device(db, 'Router D', '10.0.3.1', status='up')

    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO maintenance_windows (name, device_id, start_time, end_time) "
        "VALUES (?, ?, ?, ?)",
        (
            'Planned reboot',
            device_id,
            (datetime.now() - timedelta(hours=1)).isoformat(),
            (datetime.now() + timedelta(hours=1)).isoformat(),
        ),
    )
    conn.commit()
    db.release_connection(conn)

    windows = db.get_active_maintenance(device_id)

    assert [w['name'] for w in windows] == ['Planned reboot']
    assert db.is_device_in_maintenance(device_id) is True
