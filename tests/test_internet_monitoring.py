import json

from config import Config
from database import Database
from monitor import NetworkMonitor


class FakeWinRMResponse:
    def __init__(self, payload, status_code=0, stderr=b''):
        self.status_code = status_code
        self.std_out = json.dumps(payload).encode('utf-8') if payload is not None else b''
        self.std_err = stderr


class FakeWinRMSession:
    def __init__(self, response):
        self.response = response
        self.script = None

    def run_ps(self, script):
        self.script = script
        return self.response


def test_winrm_internet_check_parses_remote_result(monkeypatch):
    monkeypatch.setattr(Config, 'INTERNET_CHECK_URL', 'https://connectivity.example/check')
    monkeypatch.setattr(Config, 'INTERNET_CHECK_TIMEOUT', 5)
    monkeypatch.setattr(Config, 'INTERNET_CHECK_EXPECTED_STATUS', 204)
    monkeypatch.setattr(Config, 'INTERNET_CHECK_EXPECTED_CONTENT', 'connected')
    session = FakeWinRMSession(FakeWinRMResponse({
        'status': 'online',
        'latency_ms': 42.5,
        'dns_ok': True,
        'http_status': 204,
        'target': 'https://connectivity.example/check',
        'error': None,
    }))

    result = NetworkMonitor._check_winrm_internet(object.__new__(NetworkMonitor), session)

    assert result['status'] == 'online'
    assert result['latency_ms'] == 42.5
    assert result['dns_ok'] is True
    assert "Invoke-WebRequest" in session.script
    assert "GetHostAddressesAsync" in session.script
    assert "$dnsTask.Wait($dnsTimeoutMs)" in session.script
    assert "$dnsTimeoutMs = 5000" in session.script
    assert "Expected HTTP 204" in session.script
    assert "$expectedContent = 'connected'" in session.script


def test_winrm_internet_check_failure_does_not_raise(monkeypatch):
    monkeypatch.setattr(Config, 'INTERNET_CHECK_URL', 'https://connectivity.example/check')
    session = FakeWinRMSession(FakeWinRMResponse(None, status_code=1, stderr=b'access denied'))

    result = NetworkMonitor._check_winrm_internet(object.__new__(NetworkMonitor), session)

    assert result['status'] == 'unknown'
    assert result['error'] == 'access denied'


def test_database_persists_latest_and_history(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, 'DB_TYPE', 'sqlite')
    db = Database(str(tmp_path / 'internet-monitor.db'))
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO devices (name, ip_address, device_type, monitor_type) VALUES (?, ?, ?, ?)",
        ('Server A', '10.0.0.10', 'server', 'winrm'),
    )
    device_id = cursor.lastrowid
    conn.commit()
    db.release_connection(conn)

    assert db.update_internet_check(
        device_id, 'online', latency_ms=31.2, dns_ok=True,
        http_status=200, target='https://example.test/check'
    ) is True

    device = db.get_device(device_id)
    history = db.get_internet_check_history(device_id, minutes=30)
    assert device['internet_status'] == 'online'
    assert device['internet_latency_ms'] == 31.2
    assert len(history) == 1
    assert history[0]['status'] == 'online'


def test_server_dashboard_renders_internet_status_and_history():
    template = open('templates/server_dashboard.html', encoding='utf-8').read()

    assert 'id="stat-internet"' in template
    assert 'id="internet-chart"' in template
    assert 'renderInternetChart(performance.internet || [])' in template
    assert "event.kind === 'internet'" in template
    assert 'Internet Fail' in template


def test_server_dashboard_does_not_plot_failed_check_as_zero_latency():
    template = open('templates/server_dashboard.html', encoding='utf-8').read()

    assert "x: point.x, y: 0, status: point.status" not in template
    assert "rawLatency === null || rawLatency === undefined || rawLatency === ''" in template
    assert "yAxisID: 'status'" in template
    assert "label: 'Offline / failed check'" in template
    assert 'spanGaps: false' in template
