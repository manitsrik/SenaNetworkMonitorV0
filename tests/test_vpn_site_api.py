from datetime import datetime, timedelta

import pytest
from flask import Flask

from routes.vpn import vpn_bp

from test_vpn_health_api import FakeDB, quality, site_device


class SiteFakeDB(FakeDB):
    def __init__(self, devices, quality=None, previous=None, outages=None,
                 series=None, timeline=None, outage_list=None, settings=None):
        FakeDB.__init__(self, devices, quality, settings)
        self.previous = previous or {}
        self.outages = outages or {}
        self.series = series or {}
        self.timeline = timeline or {}
        self.outage_list = outage_list or []

    def get_device(self, device_id):
        for device in self.devices:
            if device['id'] == device_id:
                return device
        return None

    def get_link_quality(self, device_ids, hours=24, offset_hours=0):
        source = self.previous if offset_hours else self.quality
        return {i: source[i] for i in device_ids if i in source}

    def get_outage_episodes(self, device_ids, hours=24):
        return {i: self.outages[i] for i in device_ids if i in self.outages}

    def get_link_quality_series(self, device_ids, hours=24, buckets=40):
        return {i: self.series[i] for i in device_ids if i in self.series}

    def get_status_timeline(self, device_ids, hours=24, buckets=96):
        result = {i: self.timeline.get(i, {'band': ['up'], 'mix': [[1, 0, 0]], 'counts': {}})
                  for i in device_ids}
        result['__labels__'] = ['2026-09-17 12:00:00']
        return result

    def get_outage_list(self, device_id, hours=24, limit=60):
        return self.outage_list


def client(devices, **kwargs):
    app = Flask(__name__)
    app.secret_key = 'test'
    app.config['DB'] = SiteFakeDB(devices, **kwargs)
    app.register_blueprint(vpn_bp)
    handle = app.test_client()
    with handle.session_transaction() as session:
        session['logged_in'] = True
    return handle


def fleet():
    return [
        site_device(id=1, name='Cozi-Taksin-Jomthong'),
        site_device(id=2, name='NICHE Mono Rama9'),
        site_device(id=3, name='viva-tepalak'),
        site_device(id=4, name='switched off', is_enabled=False),
        site_device(id=5, name='a switch', device_type='switch'),
    ]


def test_only_a_vpn_router_has_a_site_page():
    handle = client(fleet(), quality={1: quality()})
    assert handle.get('/api/vpn-site/1').status_code == 200
    assert handle.get('/api/vpn-site/5').status_code == 404, 'a switch is not a branch site'
    assert handle.get('/api/vpn-site/9999').status_code == 404


def test_the_page_carries_the_window_before_it_so_now_can_be_judged():
    # "p95 is 350 ms" is a fact; "and it was 120 ms yesterday" is the finding.
    handle = client(fleet(),
                    quality={1: quality(p95=350.0, jitter=120.0)},
                    previous={1: quality(p95=120.0, jitter=8.0)})
    data = handle.get('/api/vpn-site/1').get_json()

    assert data['site']['p95'] == 350.0
    assert data['previous']['p95'] == 120.0
    assert data['previous']['jitter'] == 8.0


def test_comparison_series_come_back_beside_the_site_itself():
    handle = client(fleet(),
                    quality={1: quality(), 2: quality(), 3: quality()},
                    series={1: {'peak': [10.0], 'typical': [7.0], 'jitter': [2.0]},
                            2: {'peak': [300.0], 'typical': [20.0], 'jitter': [180.0]},
                            3: {'peak': [250.0], 'typical': [18.0], 'jitter': [160.0]}})
    data = handle.get('/api/vpn-site/1?compare=2,3').get_json()

    # Both latency lines for the site under examination...
    assert data['peak_series'] == [10.0]
    assert data['typical_series'] == [7.0]
    assert [c['name'] for c in data['compare']] == ['NICHE Mono Rama9', 'viva-tepalak']
    assert data['compare'][0]['jitter_series'] == [180.0]
    # ...and only the slow line for the comparisons, or the chart becomes a thicket.
    assert data['compare'][0]['peak_series'] == [300.0]
    assert 'typical_series' not in data['compare'][0]


def test_a_site_cannot_be_compared_against_itself_or_against_what_is_not_there():
    handle = client(fleet(), quality={1: quality()})
    data = handle.get('/api/vpn-site/1?compare=1,4,5,9999,nonsense,').get_json()

    # itself, a disabled site, a switch, a missing id and a non-number.
    assert data['compare'] == []


def test_the_overlay_is_capped_so_the_chart_stays_readable():
    devices = fleet() + [site_device(id=i, name='site %d' % i) for i in range(10, 20)]
    handle = client(devices, quality={1: quality()})
    ids = ','.join(str(i) for i in range(10, 20))
    data = handle.get('/api/vpn-site/1?compare=' + ids).get_json()

    assert len(data['compare']) == 5


def test_every_other_enabled_site_is_offered_as_a_comparison():
    handle = client(fleet(), quality={1: quality()})
    data = handle.get('/api/vpn-site/1').get_json()

    names = [s['name'] for s in data['siblings']]
    assert 'NICHE Mono Rama9' in names and 'viva-tepalak' in names
    assert 'Cozi-Taksin-Jomthong' not in names, 'a site is not its own comparison'
    assert 'switched off' not in names, 'a site nobody checks has nothing to compare'
    assert 'a switch' not in names


def test_outages_are_listed_with_when_not_just_how_many():
    # A count cannot be matched against a change request or a power cut; a
    # start and an end can.
    started = datetime.now() - timedelta(hours=3)
    ended = started + timedelta(minutes=12)
    handle = client(fleet(), quality={1: quality()},
                    outages={1: {'downtime_seconds': 720, 'longest_outage_seconds': 720, 'episodes': 1}},
                    outage_list=[{'started': started.isoformat(), 'ended': ended.isoformat(), 'checks': 4}])
    data = handle.get('/api/vpn-site/1').get_json()

    assert data['episodes'] == 1
    assert data['downtime_seconds'] == 720
    assert data['outages'][0]['checks'] == 4
    assert data['outages'][0]['started'] == started.isoformat()


def test_a_site_that_never_dropped_out_reports_an_empty_list_not_an_error():
    handle = client(fleet(), quality={1: quality()})
    data = handle.get('/api/vpn-site/1').get_json()

    assert data['outages'] == []
    assert data['episodes'] == 0


def test_the_state_shown_is_the_one_the_fleet_page_would_show():
    # Two pages disagreeing about whether a site is degraded is worse than
    # either being wrong.
    handle = client(fleet(), quality={1: quality(p95=353.0)})
    data = handle.get('/api/vpn-site/1').get_json()
    assert data['site']['state'] == 'degraded'
    assert data['thresholds']['degraded_p95_ms'] == 100.0
