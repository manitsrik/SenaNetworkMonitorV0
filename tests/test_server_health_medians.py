"""The page labels two figures "median". Both must be medians of readings.

The history the sparklines draw is bucketed, and each bucket is an average.
Taking a median across those buckets is a different statistic: on a spiky
metric the averaging lifts every bucket, so the result sits above every
reading the host actually produced. Against live data that gap reached 45%
on CPU. These tests hold both figures to the raw samples.
"""
from datetime import datetime

from flask import Flask

from routes.devices import devices_bp


class FakeDB:
    def __init__(self, devices):
        self.devices = devices
        self.series = {}
        self.cpu_medians = {}
        self.response_medians = {}
        self.median_calls = []
        self.response_median_calls = []

    def get_all_devices(self):
        return self.devices

    def get_partition_metric_types(self, device_ids, hours=24):
        return []

    def get_metric_series(self, device_ids, metric_types, hours=24, buckets=48):
        return self.series

    def get_internet_latency_series(self, device_ids, hours=24, buckets=48):
        return {}

    def get_recent_metric_medians(self, device_ids, metric_type, minutes):
        self.median_calls.append((metric_type, minutes))
        return self.cpu_medians

    def get_server_response_time_series(self, minutes=360, sample_count=60):
        return {'series': [
            {'device_id': 1, 'device_name': 'APP-1', 'values': [9000.0, 11000.0, 40000.0]},
            {'device_id': 2, 'device_name': 'DB-1', 'values': [1000.0, 1100.0]},
        ]}

    def get_response_time_medians(self, minutes=360):
        self.response_median_calls.append(minutes)
        return self.response_medians


def make_client(db):
    app = Flask(__name__)
    app.config['DB'] = db
    app.register_blueprint(devices_bp)
    return app.test_client()


def device(device_id=1, name='APP-1', **overrides):
    base = {
        'id': device_id, 'name': name, 'ip_address': '10.0.0.1', 'monitor_type': 'ssh',
        'status': 'up', 'cpu_threshold': 85.0, 'ram_threshold': 90.0, 'disk_threshold': 90.0,
        'cpu_usage': 40.0, 'ram_usage': 50.0, 'disk_usage': 10.0,
        'last_metrics_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    base.update(overrides)
    return base


def cpu_card(payload):
    return next(card for card in payload['cards'] if card['key'] == 'cpu')


# ------------------------------------------------------------- cpu ----

def test_cpu_ranks_on_the_raw_median_not_the_drawn_buckets():
    """The series averages to 20; the readings behind it have a median of 11.5."""
    db = FakeDB([device()])
    db.series = {(1, 'cpu'): [10.0, 12.0, 18.0, 40.0]}
    db.cpu_medians = {1: {'median': 11.5, 'samples': 900}}

    row = cpu_card(make_client(db).get('/api/server-health/top-metrics').get_json())['rows'][0]

    assert row['rank_value'] == 11.5
    # The bucketed history is still what gets drawn.
    assert row['series'] == [10.0, 12.0, 18.0, 40.0]


def test_cpu_median_covers_the_requested_window():
    db = FakeDB([device()])
    db.series = {(1, 'cpu'): [10.0, 12.0]}
    db.cpu_medians = {1: {'median': 11.0, 'samples': 10}}

    make_client(db).get('/api/server-health/top-metrics?hours=6')

    assert ('cpu', 6 * 60) in db.median_calls


def test_cpu_row_is_dropped_when_no_raw_median_exists():
    """No samples, no ranking figure: better absent than quietly estimated."""
    db = FakeDB([device()])
    db.series = {(1, 'cpu'): [10.0, 12.0, 18.0]}
    db.cpu_medians = {}

    assert cpu_card(make_client(db).get('/api/server-health/top-metrics').get_json())['rows'] == []


def test_cpu_ordering_follows_the_live_reading_the_card_shows():
    """The card leads with the current value, so that is what orders it.

    The medians here rank the hosts in exactly the opposite order, so a card
    that went back to ranking on them would fail this rather than pass by
    coincidence.
    """
    db = FakeDB([device(1, 'APP-1', cpu_usage=90.0),
                 device(2, 'DB-1', cpu_usage=10.0),
                 device(3, 'WEB-1', cpu_usage=50.0)])
    db.series = {(1, 'cpu'): [80.0, 90.0], (2, 'cpu'): [5.0, 6.0], (3, 'cpu'): [50.0, 50.0]}
    db.cpu_medians = {
        1: {'median': 4.0, 'samples': 900},
        2: {'median': 61.0, 'samples': 900},
        3: {'median': 30.0, 'samples': 900},
    }

    rows = cpu_card(make_client(db).get('/api/server-health/top-metrics').get_json())['rows']

    assert [row['name'] for row in rows] == ['APP-1', 'WEB-1', 'DB-1']
    # The median is still the raw one, now shown beside the figure as the
    # baseline it is being compared against rather than as the sort key.
    assert [row['rank_value'] for row in rows] == [4.0, 30.0, 61.0]
    assert [row['current'] for row in rows] == [90.0, 50.0, 10.0]


# ------------------------------------------------- collection times ----

def test_response_time_carries_a_median_measured_over_the_raw_checks():
    db = FakeDB([device(1, 'APP-1'), device(2, 'DB-1')])
    db.response_medians = {1: 10009.0, 2: 1082.0}

    payload = make_client(db).get('/api/server-health/response-time?minutes=360').get_json()
    medians = {entry['device_name']: entry['median_response_time'] for entry in payload['series']}

    # Not 11000, which is the median of the three bucket averages.
    assert medians == {'APP-1': 10009.0, 'DB-1': 1082.0}
    assert db.response_median_calls == [360]


def test_response_time_median_is_none_when_the_host_has_no_checks():
    """The page falls back to the drawn buckets rather than showing nothing."""
    db = FakeDB([device(1, 'APP-1'), device(2, 'DB-1')])
    db.response_medians = {1: 10009.0}

    payload = make_client(db).get('/api/server-health/response-time').get_json()
    entry = next(e for e in payload['series'] if e['device_name'] == 'DB-1')

    assert entry['median_response_time'] is None


def test_response_time_median_window_matches_the_series_window():
    db = FakeDB([device()])
    db.response_medians = {1: 500.0}

    make_client(db).get('/api/server-health/response-time?minutes=1440')

    assert db.response_median_calls == [1440]
