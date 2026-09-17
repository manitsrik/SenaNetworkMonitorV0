from datetime import datetime, timedelta

import pytest
from flask import Flask

from routes.vpn import (
    DEFAULT_DEGRADED_JITTER_MS,
    DEFAULT_DEGRADED_LOSS_PCT,
    DEFAULT_DEGRADED_P95_MS,
    _age_seconds,
    _classify,
    _thresholds,
    vpn_bp,
)


class FakeDB:
    def __init__(self, devices, quality=None, settings=None):
        self.devices = devices
        self.quality = quality or {}
        self.settings = settings or {}

    def get_all_devices(self):
        return self.devices

    def get_link_quality(self, device_ids, hours=24):
        return {i: self.quality.get(i, {}) for i in device_ids if i in self.quality}

    def get_alert_setting(self, key):
        return self.settings.get(key)

    def get_status_timeline(self, device_ids, hours=24, buckets=96):
        return {i: {'band': ['up'] * buckets, 'mix': [[1, 0, 0]] * buckets,
                    'counts': {'up': buckets, 'slow': 0, 'down': 0}} for i in device_ids}

    def get_latency_percentile_series(self, device_ids, hours=24, buckets=96):
        return {'labels': ['00:00'], 'p50': [8.0], 'p95': [40.0], 'samples': [12]}

    def get_status_counts_by_hour(self, device_ids, hours=24):
        return []


def site_device(**overrides):
    device = {
        'id': 1, 'name': 'Kith-Samrong', 'ip_address': '10.245.1.2', 'device_type': 'vpnrouter',
        'monitor_type': 'ping', 'status': 'up', 'response_time': 5.1, 'is_enabled': True,
        'latitude': 13.64, 'longitude': 100.59, 'location': 'Samrong',
        'last_check': datetime.now().isoformat(),
        'last_status_change': (datetime.now() - timedelta(days=16)).isoformat(),
    }
    device.update(overrides)
    return device


def quality(**overrides):
    stats = {
        'checks': 480, 'up_n': 480, 'slow_n': 0, 'down_n': 0, 'reach_pct': 100.0,
        'rtt_avg': 6.0, 'rtt_min': 4.0, 'rtt_max': 9.0, 'p95': 8.0, 'jitter': 2.0,
        'loss_pct': 0.0, 'loss_samples': 480, 'flaps': 0,
    }
    stats.update(overrides)
    return stats


def make_client(devices, quality_map=None, settings=None):
    app = Flask(__name__)
    app.secret_key = 'test'
    app.config['DB'] = FakeDB(devices, quality_map, settings)
    app.register_blueprint(vpn_bp)
    client = app.test_client()
    with client.session_transaction() as session:
        session['logged_in'] = True
        session['role'] = 'admin'
    return client


def get_health(devices, quality_map=None, settings=None):
    return make_client(devices, quality_map, settings).get('/api/vpn-health').get_json()


# ------------------------------------------------------------ classify ----

def default_thresholds():
    return {'degraded_p95_ms': DEFAULT_DEGRADED_P95_MS,
            'degraded_jitter_ms': DEFAULT_DEGRADED_JITTER_MS,
            'degraded_loss_pct': DEFAULT_DEGRADED_LOSS_PCT,
            'slow_ms': 200}


def test_a_site_that_is_not_answering_is_down_whatever_its_latency_was():
    # A down site still carries the latency of its last replies. Judging on
    # those first would file an outage under "degraded".
    site = {'status': 'down', 'reach_pct': 0.0, 'p95': 4.0, 'jitter': 0.5}
    assert _classify(site, default_thresholds()) == 'down'


def test_a_site_that_dropped_out_and_came_back_is_degraded_not_healthy():
    # This is the case the status column alone cannot show: up right now, but
    # down for most of the window.
    site = {'status': 'up', 'reach_pct': 9.9, 'p95': 17.5, 'jitter': 2.2}
    assert _classify(site, default_thresholds()) == 'degraded'


def test_a_reachable_site_is_degraded_on_p95_or_jitter_alone():
    slow = {'status': 'up', 'reach_pct': 100.0, 'p95': 353.0, 'jitter': 4.0}
    unsteady = {'status': 'up', 'reach_pct': 100.0, 'p95': 94.0, 'jitter': 39.7}
    assert _classify(slow, default_thresholds()) == 'degraded'
    assert _classify(unsteady, default_thresholds()) == 'degraded'


def test_a_site_answering_every_check_quickly_and_steadily_is_healthy():
    site = {'status': 'up', 'reach_pct': 100.0, 'p95': 8.0, 'jitter': 1.0}
    assert _classify(site, default_thresholds()) == 'healthy'


def test_missing_quality_figures_do_not_read_as_a_fault():
    # A site checked for the first time has no p95 yet; None must not compare
    # as though it were a large number.
    site = {'status': 'up', 'reach_pct': None, 'p95': None, 'jitter': None}
    assert _classify(site, default_thresholds()) == 'healthy'


# ----------------------------------------------------------------- age ----

def test_a_naive_timestamp_is_read_on_the_local_clock():
    # update_device_status writes both columns this page reads from one local
    # datetime.now(). Treating them as possibly-UTC shaved the whole UTC offset
    # off every age - seven hours here - and the error scaled with the offset
    # instead of failing loudly.
    local = (datetime.now() - timedelta(days=16)).isoformat()
    assert _age_seconds(local) == pytest.approx(16 * 86400, rel=0.001)


def test_an_offset_aware_timestamp_is_still_understood():
    from datetime import timezone as tz
    aware = datetime.now(tz.utc) - timedelta(minutes=5)
    assert _age_seconds(aware.isoformat()) == pytest.approx(300, abs=5)


@pytest.mark.parametrize('value', [None, '', 'not-a-date'])
def test_an_unreadable_timestamp_reports_no_age_rather_than_zero(value):
    assert _age_seconds(value) is None


# ---------------------------------------------------------- thresholds ----

def test_thresholds_come_from_settings_so_they_can_be_tuned_without_a_deploy():
    db = FakeDB([], settings={'vpn_degraded_p95_ms': '150', 'vpn_degraded_jitter_ms': '45'})
    values = _thresholds(db)
    assert values['degraded_p95_ms'] == 150
    assert values['degraded_jitter_ms'] == 45


@pytest.mark.parametrize('stored', [None, '', 'not-a-number', '0', '-5'])
def test_an_unusable_threshold_falls_back_instead_of_disabling_the_check(stored):
    # A blank or zero setting must not silently mark every site healthy.
    db = FakeDB([], settings={'vpn_degraded_p95_ms': stored, 'vpn_degraded_jitter_ms': stored})
    values = _thresholds(db)
    assert values['degraded_p95_ms'] == DEFAULT_DEGRADED_P95_MS
    assert values['degraded_jitter_ms'] == DEFAULT_DEGRADED_JITTER_MS


# ---------------------------------------------------------------- api ----

def test_only_vpn_routers_reach_the_dashboard():
    devices = [
        site_device(id=1),
        site_device(id=2, name='Core switch', device_type='switch'),
        site_device(id=3, name='Branch firewall', device_type='firewall'),
    ]
    data = get_health(devices, {1: quality(), 2: quality(), 3: quality()})
    assert [s['name'] for s in data['sites']] == ['Kith-Samrong']
    assert data['summary']['total_sites'] == 1


def test_disabled_sites_are_listed_but_kept_out_of_every_figure():
    devices = [site_device(id=1), site_device(id=2, name='BANGBUATHONG', is_enabled=False)]
    data = get_health(devices, {1: quality()})

    assert data['summary']['total_sites'] == 1
    assert data['summary']['configured_sites'] == 2
    assert data['summary']['disabled'] == 1
    assert [d['name'] for d in data['disabled_sites']] == ['BANGBUATHONG']


def test_an_outage_is_reported_from_its_own_start_not_from_the_window_edge():
    # Kith-Samrong had been down 16 days inside a 24-hour view. Capping the
    # figure at the window would have called a three-week outage "a day".
    started = datetime.now() - timedelta(days=16)
    devices = [site_device(status='down', last_status_change=started.isoformat())]
    data = get_health(devices, {1: quality(up_n=0, down_n=480, reach_pct=0.0,
                                           rtt_avg=None, p95=None, jitter=None)})

    site = data['sites'][0]
    assert site['state'] == 'down'
    assert site['state_age_seconds'] == pytest.approx(16 * 86400, rel=0.01)


def test_sites_are_ordered_worst_first():
    devices = [
        site_device(id=1, name='healthy'),
        site_device(id=2, name='down', status='down'),
        site_device(id=3, name='slow'),
    ]
    data = get_health(devices, {
        1: quality(),
        2: quality(reach_pct=0.0, p95=None),
        3: quality(p95=353.0),
    })
    assert [s['name'] for s in data['sites']] == ['down', 'slow', 'healthy']


def test_sites_without_coordinates_are_counted_so_the_map_can_admit_its_blind_spot():
    devices = [
        site_device(id=1, name='mapped'),
        site_device(id=2, name='unmapped', latitude=None, longitude=None),
    ]
    data = get_health(devices, {1: quality(), 2: quality()})

    assert data['summary']['mapped'] == 1
    assert data['summary']['unmapped'] == 1
    unmapped = [s for s in data['sites'] if not s['has_coordinates']]
    assert [s['name'] for s in unmapped] == ['unmapped']


def test_availability_is_averaged_per_site_not_per_check():
    # One site down all day next to one healthy site is 50%, however many
    # checks each of them happened to run.
    devices = [site_device(id=1, name='up'), site_device(id=2, name='down', status='down')]
    data = get_health(devices, {
        1: quality(checks=4000, reach_pct=100.0),
        2: quality(checks=40, reach_pct=0.0, up_n=0, down_n=40, p95=None),
    })
    assert data['summary']['availability_pct'] == pytest.approx(50.0)


def test_packet_loss_reports_how_many_checks_measured_it():
    # Rows written before the column existed carry NULL. The page needs to tell
    # "no loss" apart from "nothing measured it yet".
    devices = [site_device()]
    data = get_health(devices, {1: quality(loss_pct=None, loss_samples=0)})
    site = data['sites'][0]
    assert site['packet_loss_pct'] is None
    assert site['packet_loss_samples'] == 0


def test_timeline_and_latency_endpoints_answer_for_enabled_sites_only():
    devices = [site_device(id=1), site_device(id=2, name='off', is_enabled=False)]
    client = make_client(devices, {1: quality()})

    timeline = client.get('/api/vpn-health/status-timeline').get_json()
    assert [s['id'] for s in timeline['sites']] == [1]

    latency = client.get('/api/vpn-health/latency').get_json()
    assert latency['success'] is True
    assert latency['slow_threshold_ms'] == 200


def test_the_api_requires_a_session():
    app = Flask(__name__)
    app.config['DB'] = FakeDB([site_device()])
    app.register_blueprint(vpn_bp)
    # url_for('auth.login') has nothing to resolve against here, which is
    # itself proof the request never reached the handler.
    response = app.test_client().get('/api/vpn-health')
    assert response.status_code != 200


def test_disabled_sites_carry_what_the_map_needs_to_grey_them_out():
    # A branch with monitoring switched off is a blind spot, not an absent site.
    # It belongs on the map, greyed, and in none of the figures.
    devices = [
        site_device(id=1, name='watched'),
        site_device(id=2, name='switched off', is_enabled=False, latitude=13.73, longitude=100.43),
    ]
    data = get_health(devices, {1: quality()})

    off = data['disabled_sites']
    assert [d['name'] for d in off] == ['switched off']
    assert off[0]['state'] == 'disabled'
    assert off[0]['has_coordinates'] is True
    assert off[0]['latitude'] == 13.73 and off[0]['longitude'] == 100.43

    # ...and it is still in none of the counts.
    assert data['summary']['total_sites'] == 1
    assert data['summary']['mapped'] == 1
    assert data['summary']['unmapped'] == 0
    assert data['summary']['down'] == 0


def test_a_disabled_site_without_coordinates_is_reported_as_unmappable_too():
    devices = [site_device(id=2, name='off', is_enabled=False, latitude=None, longitude=None)]
    data = get_health(devices, {})

    assert data['disabled_sites'][0]['has_coordinates'] is False


def test_a_link_that_drops_packets_is_degraded_even_when_it_is_fast():
    # Latency is now measured from the packets that answered, so a link losing
    # one in three no longer shows up as a slow one. Without a line of its own,
    # loss would stop being visible anywhere on the page.
    devices = [site_device()]
    data = get_health(devices, {1: quality(loss_pct=3.2, p95=6.0, jitter=1.0)})

    assert data['sites'][0]['state'] == 'degraded'
    assert data['sites'][0]['packet_loss_pct'] == 3.2


def test_a_trace_of_loss_below_the_line_is_not_a_fault():
    devices = [site_device()]
    data = get_health(devices, {1: quality(loss_pct=0.2)})
    assert data['sites'][0]['state'] == 'healthy'


def test_the_loss_threshold_is_tunable_like_the_other_two():
    db = FakeDB([], settings={'vpn_degraded_loss_pct': '5'})
    assert _thresholds(db)['degraded_loss_pct'] == 5

    site = {'status': 'up', 'reach_pct': 100.0, 'p95': 6.0, 'jitter': 1.0, 'packet_loss_pct': 3.2}
    relaxed = dict(default_thresholds(), degraded_loss_pct=5.0)
    assert _classify(site, relaxed) == 'healthy'
    assert _classify(site, default_thresholds()) == 'degraded'


# ----------------------------------------------------------- top cards ----

class TopFakeDB(FakeDB):
    def __init__(self, devices, quality=None, previous=None, outages=None, series=None, settings=None):
        FakeDB.__init__(self, devices, quality, settings)
        self.previous = previous or {}
        self.outages = outages or {}
        self.series = series or {}

    def get_link_quality(self, device_ids, hours=24, offset_hours=0):
        source = self.previous if offset_hours else self.quality
        return {i: source.get(i, {}) for i in device_ids if i in source}

    def get_outage_episodes(self, device_ids, hours=24):
        return {i: self.outages[i] for i in device_ids if i in self.outages}

    def get_link_quality_series(self, device_ids, hours=24, buckets=40):
        return {i: self.series[i] for i in device_ids if i in self.series}


def top_client(devices, **kwargs):
    app = Flask(__name__)
    app.secret_key = 'test'
    app.config['DB'] = TopFakeDB(devices, **kwargs)
    app.register_blueprint(vpn_bp)
    client = app.test_client()
    with client.session_transaction() as session:
        session['logged_in'] = True
    return client


def cards_of(devices, **kwargs):
    data = top_client(devices, **kwargs).get('/api/vpn-health/top-metrics?limit=5').get_json()
    return {c['key']: c for c in data['cards']}


def test_deterioration_ranks_on_the_change_not_the_level():
    # The slowest site is not the story; the one that moved is. A 300 ms link
    # sitting still must not outrank an 8 ms link that tripled.
    devices = [site_device(id=1, name='steady and slow'), site_device(id=2, name='just got worse')]
    cards = cards_of(devices,
                     quality={1: quality(p95=300.0), 2: quality(p95=30.0)},
                     previous={1: quality(p95=298.0), 2: quality(p95=10.0)})

    rows = cards['deterioration']['rows']
    assert [r['name'] for r in rows] == ['just got worse']
    assert rows[0]['rank_value'] == 20.0
    assert rows[0]['previous'] == 10.0 and rows[0]['current'] == 30.0
    assert rows[0]['change_pct'] == 200


def test_a_rise_has_to_clear_both_a_relative_and_an_absolute_floor():
    devices = [
        site_device(id=1, name='noise on a fast link'),     # 5.0 -> 5.3: too small to mean anything
        site_device(id=2, name='noise on a slow link'),     # 300 -> 303: 3 ms on 300 is nothing
        site_device(id=3, name='real'),                     # 10 -> 14
    ]
    cards = cards_of(devices,
                     quality={1: quality(p95=5.3), 2: quality(p95=303.0), 3: quality(p95=14.0)},
                     previous={1: quality(p95=5.0), 2: quality(p95=300.0), 3: quality(p95=10.0)})

    assert [r['name'] for r in cards['deterioration']['rows']] == ['real']


def test_a_site_with_no_earlier_reading_is_not_called_a_deterioration():
    # A site added yesterday has nothing to compare against.
    devices = [site_device(id=1, name='new')]
    cards = cards_of(devices, quality={1: quality(p95=300.0)}, previous={})
    assert cards['deterioration']['rows'] == []
    assert 'No site is measurably slower' in cards['deterioration']['empty']


def test_downtime_offers_the_total_and_the_longest_run_as_separate_lists():
    # Six two-minute drops and one twelve-minute drop cost the same in total and
    # are not the same fault, so ranking one way cannot answer both questions.
    devices = [site_device(id=1, name='flaky'), site_device(id=2, name='one long drop')]
    cards = cards_of(devices, quality={1: quality(), 2: quality()}, outages={
        1: {'downtime_seconds': 720, 'longest_outage_seconds': 120, 'episodes': 6},
        2: {'downtime_seconds': 720, 'longest_outage_seconds': 720, 'episodes': 1},
    })

    card = cards['downtime']
    assert [r['rank_value'] for r in card['rows']] == [12.0, 12.0]
    assert [r['name'] for r in card['longest']] == ['one long drop', 'flaky']
    assert card['alt_label'] == 'Longest run'


def test_a_site_that_never_dropped_out_is_not_in_the_downtime_card():
    devices = [site_device(id=1, name='fine')]
    cards = cards_of(devices, quality={1: quality()}, outages={1: {'downtime_seconds': 0, 'episodes': 0}})
    assert cards['downtime']['rows'] == []


def test_jitter_and_latency_cards_carry_their_own_history():
    devices = [site_device(id=1)]
    cards = cards_of(devices,
                     quality={1: quality(p95=353.0, jitter=124.0, rtt_avg=143.0)},
                     series={1: {'peak': [8.0, 353.0], 'typical': [6.0, 40.0], 'jitter': [2.0, 124.0]}})

    assert cards['jitter']['rows'][0]['series'] == [2.0, 124.0]
    # The sparkline carries the slowest reply per bucket: a spotter for spikes,
    # which is what a 58px line can usefully show.
    assert cards['latency']['rows'][0]['series'] == [8.0, 353.0]
    # The card leads with p95 and is ranked by it; the live reading sits beside.
    assert cards['latency']['rows'][0]['rank_value'] == 353.0
    assert cards['latency']['rows'][0]['current'] == 5.1
    assert cards['latency']['rows'][0]['average'] == 143.0


def test_a_card_never_shows_more_than_the_requested_limit():
    devices = [site_device(id=i, name='site %d' % i) for i in range(1, 9)]
    quality_map = {i: quality(p95=float(100 + i)) for i in range(1, 9)}
    cards = cards_of(devices, quality=quality_map)
    assert len(cards['latency']['rows']) == 5
    assert [r['name'] for r in cards['latency']['rows']][0] == 'site 8'


def test_the_downtime_card_carries_the_band_that_shows_when():
    devices = [site_device(id=1, name='dropped out')]
    client = top_client(devices, quality={1: quality()},
                        outages={1: {'downtime_seconds': 600, 'longest_outage_seconds': 600, 'episodes': 1}})
    cards = {c['key']: c for c in client.get('/api/vpn-health/top-metrics').get_json()['cards']}

    row = cards['downtime']['rows'][0]
    assert row['band'], 'a total of minutes cannot say when the site was missing'
    assert set(row['band']) <= {'up', 'slow', 'down', 'unknown', 'none'}
    assert cards['downtime']['longest'][0]['band'] == row['band']
