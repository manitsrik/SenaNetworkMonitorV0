from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask

from routes.devices import (
    SERVER_HEALTH_STALE_AFTER_SECONDS,
    _age_seconds,
    _slow_threshold_ms,
    devices_bp,
)


class FakeDB:
    def __init__(self, devices):
        self.devices = devices

    def get_all_devices(self):
        return self.devices


def make_client(devices):
    app = Flask(__name__)
    app.config['DB'] = FakeDB(devices)
    app.register_blueprint(devices_bp)
    return app.test_client()


def ssh_device(**overrides):
    device = {
        'id': 1, 'name': 'APP-1', 'ip_address': '10.0.0.1', 'monitor_type': 'ssh',
        'status': 'up', 'response_time': 1178, 'cpu_usage': 3.1, 'ram_usage': 21.1,
        'disk_usage': 9.0, 'pending_reboot': 0, 'monitored_services': 'nginx',
        'service_status_json': '[{"name":"nginx","ok":true}]',
        'disk_details_json': '[{"mount":"/","use_percent":9.0}]',
        'last_metrics_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    device.update(overrides)
    return device


# --------------------------------------------------------------- age ----

def test_age_seconds_reads_local_and_utc_naive_timestamps():
    """`last_check` is written in local time, `last_metrics_time` in UTC."""
    local = (datetime.now() - timedelta(minutes=2)).isoformat()
    utc = (datetime.utcnow() - timedelta(minutes=3)).strftime('%Y-%m-%d %H:%M:%S')

    assert _age_seconds(local) == pytest.approx(120, abs=5)
    assert _age_seconds(utc) == pytest.approx(180, abs=5)


def test_age_seconds_reads_aware_and_datetime_values():
    aware = datetime.now(timezone.utc) - timedelta(seconds=45)
    assert _age_seconds(aware.isoformat()) == pytest.approx(45, abs=5)
    assert _age_seconds(datetime.now() - timedelta(minutes=10)) == pytest.approx(600, abs=5)


@pytest.mark.parametrize('value', [None, '', 'not-a-date'])
def test_age_seconds_returns_none_for_unusable_values(value):
    assert _age_seconds(value) is None


def test_stale_flag_follows_metric_age():
    fresh = ssh_device(id=1, name='fresh')
    old = ssh_device(
        id=2, name='old',
        last_metrics_time=(datetime.now() - timedelta(seconds=SERVER_HEALTH_STALE_AFTER_SECONDS + 120))
        .strftime('%Y-%m-%d %H:%M:%S'),
    )

    payload = make_client([fresh, old]).get('/api/server-health').get_json()
    by_name = {server['name']: server for server in payload['servers']}

    assert by_name['fresh']['is_stale'] is False
    assert by_name['old']['is_stale'] is True
    assert payload['summary']['stale'] == 1


def test_server_without_metrics_reports_unknown_age():
    device = ssh_device(last_metrics_time=None, last_check=None)
    payload = make_client([device]).get('/api/server-health').get_json()

    assert payload['servers'][0]['metrics_age_seconds'] is None
    assert payload['servers'][0]['is_stale'] is False


def test_disk_rows_carry_owning_server_freshness():
    stale_at = (datetime.now() - timedelta(seconds=SERVER_HEALTH_STALE_AFTER_SECONDS + 60))
    device = ssh_device(status='down', last_metrics_time=stale_at.strftime('%Y-%m-%d %H:%M:%S'))

    payload = make_client([device]).get('/api/server-health').get_json()
    disk = payload['top_disk'][0]

    assert disk['status'] == 'down'
    assert disk['is_stale'] is True


# ---------------------------------------------------------- services ----

def test_services_configured_distinguishes_zero_from_unconfigured():
    configured = ssh_device(id=1, name='watched', monitored_services='nginx')
    unconfigured = ssh_device(
        id=2, name='unwatched', monitored_services='   ', service_status_json='[]',
    )

    payload = make_client([configured, unconfigured]).get('/api/server-health').get_json()
    by_name = {server['name']: server for server in payload['servers']}

    assert by_name['watched']['services_configured'] is True
    assert by_name['unwatched']['services_configured'] is False
    # Zero stopped services is only good news across the one watched server.
    assert payload['summary']['service_down'] == 0
    assert payload['summary']['service_monitored_servers'] == 1


# -------------------------------------------------------- thresholds ----

def test_slow_threshold_matches_the_monitor_per_collection_method():
    assert _slow_threshold_ms('ssh') == 10000
    assert _slow_threshold_ms('winrm') == 10000
    # WMI is stricter, so a 6s collection is already slow there.
    assert _slow_threshold_ms('wmi') == 5000


def test_each_server_carries_its_own_thresholds():
    wmi = ssh_device(id=2, name='WMI-BOX', monitor_type='wmi', response_time=6200)
    payload = make_client([ssh_device(), wmi]).get('/api/server-health').get_json()
    by_name = {server['name']: server for server in payload['servers']}

    assert by_name['APP-1']['slow_threshold_ms'] == 10000
    assert by_name['APP-1']['critical_threshold_ms'] == 30000
    assert by_name['WMI-BOX']['slow_threshold_ms'] == 5000
    assert by_name['WMI-BOX']['critical_threshold_ms'] == 15000

    assert payload['thresholds']['slow_ms'] == {'ssh': 10000, 'winrm': 10000, 'wmi': 5000}
    assert payload['thresholds']['stale_after_seconds'] == SERVER_HEALTH_STALE_AFTER_SECONDS


def test_non_server_monitor_types_are_still_excluded():
    switch = {'id': 9, 'name': 'Switch', 'monitor_type': 'snmp', 'status': 'up'}
    payload = make_client([ssh_device(), switch]).get('/api/server-health').get_json()

    assert payload['summary']['total_servers'] == 1
    assert [server['name'] for server in payload['servers']] == ['APP-1']
