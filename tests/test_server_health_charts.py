"""Capacity-outlook and availability-timeline endpoints."""
from datetime import datetime, timedelta

import pytest
from flask import Flask

from routes.devices import (
    SERVER_HEALTH_STALE_AFTER_SECONDS,
    _linear_slope_per_day,
    devices_bp,
)


class FakeDB:
    """Stands in for the database, returning whatever the test prepared."""

    def __init__(self, devices, capacity=None, timeline=None):
        self.devices = devices
        self.capacity = capacity or {}
        self.timeline = timeline or {}
        self.capacity_calls = []

    def get_all_devices(self):
        return self.devices

    def get_capacity_samples(self, device_ids, metric, days=30, buckets=40):
        self.capacity_calls.append((tuple(device_ids), metric, days, buckets))
        return self.capacity

    def get_status_timeline(self, device_ids, hours=24, buckets=96):
        return self.timeline


def make_client(db):
    app = Flask(__name__)
    app.config['DB'] = db
    app.register_blueprint(devices_bp)
    return app.test_client()


def device(device_id=1, name='APP-1', fresh=True, **overrides):
    age = timedelta(seconds=30) if fresh else timedelta(seconds=SERVER_HEALTH_STALE_AFTER_SECONDS + 3600)
    base = {
        'id': device_id, 'name': name, 'ip_address': '10.0.0.1', 'monitor_type': 'ssh',
        'status': 'up', 'ram_threshold': 90.0, 'disk_threshold': 90.0, 'cpu_threshold': 85.0,
        'last_metrics_time': (datetime.now() - age).strftime('%Y-%m-%d %H:%M:%S'),
    }
    base.update(overrides)
    return base


def ramp(start, per_day, days=30, points=30):
    """Samples rising linearly, newest last, as get_capacity_samples returns."""
    step = days / (points - 1)
    return [
        {
            'bucket': f'2026-09-{(i % 28) + 1:02d} 00:00:00',
            'age_days': days - i * step,
            'value': start + per_day * (i * step),
        }
        for i in range(points)
    ]


# ------------------------------------------------------------- slope ----

def test_slope_recovers_a_known_rate():
    # 0.5 points per day, sampled backwards in time.
    points = [(float(day), 50.0 - 0.5 * day) for day in range(30)]
    assert _linear_slope_per_day(points) == pytest.approx(0.5, abs=1e-9)


def test_slope_of_a_flat_series_is_zero():
    assert _linear_slope_per_day([(float(d), 42.0) for d in range(30)]) == pytest.approx(0, abs=1e-9)


@pytest.mark.parametrize('points', [[], [(1.0, 2.0)], [(1.0, 2.0), (2.0, 3.0)]])
def test_slope_needs_at_least_three_points(points):
    assert _linear_slope_per_day(points) is None


def test_slope_survives_samples_that_share_a_timestamp():
    assert _linear_slope_per_day([(5.0, 1.0), (5.0, 2.0), (5.0, 3.0)]) is None


# ---------------------------------------------------------- capacity ----

def test_capacity_projects_to_the_devices_own_threshold():
    db = FakeDB([device(ram_threshold=80.0)], capacity={1: ramp(50.0, 0.5)})
    payload = make_client(db).get('/api/server-health/capacity?metric=ram').get_json()
    entry = payload['servers'][0]

    assert entry['limit'] == 80.0
    assert entry['slope_per_day'] == pytest.approx(0.5, abs=0.01)
    # 65% now, 15 points to go at 0.5/day.
    assert entry['days_to_limit'] == pytest.approx(30, abs=1)
    assert entry['over_limit'] is False


def test_capacity_marks_a_server_already_past_its_limit():
    db = FakeDB([device(ram_threshold=60.0)], capacity={1: ramp(50.0, 0.5)})
    entry = make_client(db).get('/api/server-health/capacity?metric=ram').get_json()['servers'][0]

    assert entry['over_limit'] is True
    assert entry['days_to_limit'] is None


def test_capacity_gives_no_forecast_for_a_falling_series():
    db = FakeDB([device()], capacity={1: ramp(80.0, -0.5)})
    entry = make_client(db).get('/api/server-health/capacity?metric=ram').get_json()['servers'][0]

    assert entry['slope_per_day'] < 0
    assert entry['days_to_limit'] is None


def test_capacity_refuses_to_forecast_from_stale_data():
    """A host that stopped reporting has history, not a trajectory."""
    db = FakeDB([device(fresh=False)], capacity={1: ramp(50.0, 0.5)})
    entry = make_client(db).get('/api/server-health/capacity?metric=ram').get_json()['servers'][0]

    assert entry['is_stale'] is True
    assert entry['days_to_limit'] is None


def test_capacity_sorts_most_urgent_first_and_stale_last():
    devices = [
        device(1, 'soon', ram_threshold=90.0),
        device(2, 'later', ram_threshold=90.0),
        device(3, 'over', ram_threshold=60.0),
        device(4, 'stale', fresh=False, ram_threshold=90.0),
    ]
    db = FakeDB(devices, capacity={
        1: ramp(80.0, 0.3),
        2: ramp(20.0, 0.1),
        3: ramp(50.0, 0.5),
        4: ramp(80.0, 0.3),
    })
    names = [s['name'] for s in make_client(db).get('/api/server-health/capacity?metric=ram').get_json()['servers']]

    assert names[0] == 'over'
    assert names.index('soon') < names.index('later')
    assert names[-1] == 'stale'


def test_capacity_rejects_an_unknown_metric():
    response = make_client(FakeDB([device()])).get('/api/server-health/capacity?metric=voltage')
    assert response.status_code == 400
    assert response.get_json()['success'] is False


def test_capacity_only_asks_about_server_devices():
    switch = {'id': 9, 'name': 'Switch', 'monitor_type': 'snmp', 'status': 'up'}
    db = FakeDB([device(), switch], capacity={1: ramp(50.0, 0.5)})
    make_client(db).get('/api/server-health/capacity?metric=ram').get_json()

    requested_ids, metric, _, _ = db.capacity_calls[0]
    assert requested_ids == (1,)
    assert metric == 'ram'


@pytest.mark.parametrize('days,expected', [(1, 2), (30, 30), (500, 90)])
def test_capacity_window_is_clamped(days, expected):
    db = FakeDB([device()], capacity={1: ramp(50.0, 0.5)})
    payload = make_client(db).get(f'/api/server-health/capacity?metric=ram&days={days}').get_json()
    assert payload['days'] == expected


# ---------------------------------------------------------- timeline ----

def test_timeline_reports_the_status_mix_per_server():
    db = FakeDB(
        [device(1, 'flaky')],
        timeline={
            1: {'band': ['up', 'down', 'slow', 'none'], 'counts': {'up': 6, 'slow': 3, 'down': 1}},
            '__labels__': ['t0', 't1', 't2', 't3'],
        },
    )
    entry = make_client(db).get('/api/server-health/status-timeline').get_json()['servers'][0]

    assert entry['band'] == ['up', 'down', 'slow', 'none']
    assert entry['checks'] == 10
    assert entry['up_pct'] == 60.0
    assert entry['slow_pct'] == 30.0
    assert entry['down_pct'] == 10.0


def test_timeline_covers_a_server_with_no_history_at_all():
    db = FakeDB([device(1, 'silent')], timeline={'__labels__': ['t0']})
    entry = make_client(db).get('/api/server-health/status-timeline?buckets=12').get_json()['servers'][0]

    assert entry['checks'] == 0
    assert entry['up_pct'] is None
    # A server with no data must still occupy a row rather than vanish.
    assert set(entry['band']) == {'none'}


def test_timeline_puts_the_worst_servers_first():
    db = FakeDB(
        [device(1, 'healthy'), device(2, 'broken'), device(3, 'sluggish')],
        timeline={
            1: {'band': ['up'], 'counts': {'up': 10, 'slow': 0, 'down': 0}},
            2: {'band': ['down'], 'counts': {'up': 0, 'slow': 0, 'down': 10}},
            3: {'band': ['slow'], 'counts': {'up': 5, 'slow': 5, 'down': 0}},
            '__labels__': ['t0'],
        },
    )
    names = [s['name'] for s in make_client(db).get('/api/server-health/status-timeline').get_json()['servers']]
    assert names == ['broken', 'sluggish', 'healthy']


# 0 is treated as "unset" and falls back to the default; a negative value is a
# real number and gets clamped to the floor.
@pytest.mark.parametrize('hours,expected', [(0, 24), (-5, 1), (24, 24), (10000, 720)])
def test_timeline_window_is_clamped(hours, expected):
    db = FakeDB([device()], timeline={'__labels__': []})
    payload = make_client(db).get(f'/api/server-health/status-timeline?hours={hours}').get_json()
    assert payload['hours'] == expected
