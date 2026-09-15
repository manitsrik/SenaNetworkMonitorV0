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


def test_top_lists_exclude_hosts_that_stopped_reporting():
    """A reading from days ago is not a current top consumer."""
    stale_at = (datetime.now() - timedelta(seconds=SERVER_HEALTH_STALE_AFTER_SECONDS + 60))
    live = ssh_device(id=1, name='live', cpu_usage=10, ram_usage=10)
    dead = ssh_device(
        id=2, name='dead', status='down', cpu_usage=99, ram_usage=99,
        last_metrics_time=stale_at.strftime('%Y-%m-%d %H:%M:%S'),
        disk_details_json='[{"mount":"/","use_percent":99.0}]',
    )

    payload = make_client([live, dead]).get('/api/server-health').get_json()

    # 'dead' has the highest numbers and would otherwise top every list.
    assert [row['name'] for row in payload['top_cpu']] == ['live']
    assert [row['name'] for row in payload['top_ram']] == ['live']
    assert [row['device_name'] for row in payload['top_disk']] == ['live']
    # The count is reported so the panel can say something was left out.
    assert payload['hidden_stale']['cpu'] == 1
    assert payload['hidden_stale']['disk'] == 1
    # The server itself is still listed in full; only the ranking drops it.
    assert {s['name'] for s in payload['servers']} == {'live', 'dead'}


def test_disk_rows_carry_owning_server_freshness():
    """The freshness fields are what let _top decide which rows are live."""
    stale_at = (datetime.now() - timedelta(seconds=SERVER_HEALTH_STALE_AFTER_SECONDS + 60))
    device = ssh_device(status='down', last_metrics_time=stale_at.strftime('%Y-%m-%d %H:%M:%S'))

    payload = make_client([device]).get('/api/server-health').get_json()

    assert payload['top_disk'] == []
    assert payload['hidden_stale']['disk'] == 1


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
    assert _slow_threshold_ms({'monitor_type': 'ssh'}) == 10000
    assert _slow_threshold_ms({'monitor_type': 'winrm'}) == 10000
    # WMI is stricter, so a 6s collection is already slow there.
    assert _slow_threshold_ms({'monitor_type': 'wmi'}) == 5000


def test_device_slow_threshold_overrides_the_shared_default():
    """A host whose agent is simply slow should not report SLOW on every poll."""
    device = {'monitor_type': 'winrm', 'slow_threshold_ms': 45000}
    assert _slow_threshold_ms(device) == 45000


@pytest.mark.parametrize('override', [None, '', 0, -1, 'abc'])
def test_unusable_override_falls_back_to_the_default(override):
    device = {'monitor_type': 'winrm', 'slow_threshold_ms': override}
    assert _slow_threshold_ms(device) == 10000


def test_payload_flags_a_custom_threshold():
    plain = ssh_device(id=1, name='plain')
    tuned = ssh_device(id=2, name='tuned', monitor_type='winrm', slow_threshold_ms=45000)

    payload = make_client([plain, tuned]).get('/api/server-health').get_json()
    by_name = {server['name']: server for server in payload['servers']}

    assert by_name['plain']['slow_threshold_ms'] == 10000
    assert by_name['plain']['slow_threshold_is_custom'] is False
    assert by_name['tuned']['slow_threshold_ms'] == 45000
    assert by_name['tuned']['slow_threshold_is_custom'] is True
    assert by_name['tuned']['critical_threshold_ms'] == 135000


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


# ------------------------------------------------------- attention ------

def test_attention_ranks_by_share_of_each_hosts_own_limit():
    """94% against a 95% limit is nearer the edge than 83% against 90%."""
    tight = ssh_device(id=1, name='tight', ram_usage=94.0, ram_threshold=95.0)
    loose = ssh_device(id=2, name='loose', ram_usage=83.0, ram_threshold=90.0)

    payload = make_client([tight, loose]).get('/api/server-health').get_json()
    ram = [item for item in payload['attention'] if item['kind'] == 'ram']

    # Raw usage would order these the same way; the limits are what differ.
    assert [item['name'] for item in ram] == ['tight', 'loose']
    assert ram[0]['percent'] == pytest.approx(98.9, abs=0.1)
    assert ram[1]['percent'] == pytest.approx(92.2, abs=0.1)


def test_attention_ignores_metrics_that_are_not_close_to_their_limit():
    payload = make_client([ssh_device(cpu_usage=5, ram_usage=5, disk_usage=5)]).get('/api/server-health').get_json()
    assert payload['attention'] == []
    assert payload['summary']['attention'] == 0


def test_attention_marks_a_breach_as_critical():
    over = ssh_device(ram_usage=96.0, ram_threshold=95.0)
    item = [i for i in make_client([over]).get('/api/server-health').get_json()['attention']
            if i['kind'] == 'ram'][0]
    assert item['severity'] == 'critical'


def test_attention_leaves_out_hosts_that_stopped_reporting():
    stale_at = datetime.now() - timedelta(seconds=SERVER_HEALTH_STALE_AFTER_SECONDS + 60)
    dead = ssh_device(
        id=1, name='dead', status='down', ram_usage=99.0,
        last_metrics_time=stale_at.strftime('%Y-%m-%d %H:%M:%S'),
    )
    live = ssh_device(id=2, name='live', ram_usage=93.0, ram_threshold=95.0)

    payload = make_client([dead, live]).get('/api/server-health').get_json()
    assert [item['name'] for item in payload['attention']] == ['live']


# -------------------------------------------------------- internet ------

def test_internet_failure_outranks_any_metric_climbing():
    """A lost connection is not a trend; it sorts above one."""
    failing = ssh_device(id=1, name='offline', internet_status='dns_error')
    climbing = ssh_device(id=2, name='climbing', ram_usage=94.9, ram_threshold=95.0)

    payload = make_client([failing, climbing]).get('/api/server-health').get_json()
    assert payload['attention'][0]['kind'] == 'internet'
    assert payload['attention'][0]['severity'] == 'critical'


def test_slow_internet_is_a_warning_not_a_failure():
    from config import Config
    slow = ssh_device(internet_status='online',
                      internet_latency_ms=Config.INTERNET_SLOW_LATENCY_MS + 200)
    item = [i for i in make_client([slow]).get('/api/server-health').get_json()['attention']
            if i['kind'] == 'internet'][0]
    assert item['severity'] == 'warning'


def test_fast_internet_raises_nothing():
    fast = ssh_device(internet_status='online', internet_latency_ms=60)
    assert make_client([fast]).get('/api/server-health').get_json()['attention'] == []


def test_summary_separates_unchecked_internet_from_working_internet():
    online = ssh_device(id=1, name='a', internet_status='online', internet_latency_ms=50)
    broken = ssh_device(id=2, name='b', internet_status='offline')
    never = ssh_device(id=3, name='c', internet_status=None)

    summary = make_client([online, broken, never]).get('/api/server-health').get_json()['summary']
    assert summary['internet_online'] == 1
    assert summary['internet_problem'] == 1
    # Never checked is not the same as working, and not the same as broken.
    assert summary['internet_unchecked'] == 1
