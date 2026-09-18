from pathlib import Path
from types import SimpleNamespace

import monitor as monitor_module
from monitor import NetworkMonitor


class FakeStream:
    def __init__(self, value=''):
        self.value = value.encode()

    def read(self):
        return self.value


def command_output(command):
    if command.startswith("grep '^cpu '"):
        # the /proc/stat counters, then uptime.
        return ('cpu  1000 0 500 8000 500 0 0 0\n'
                ' 11:20 up 2 days, load average: 0.40, 0.30, 0.20')
    if command == 'free -m | grep Mem':
        return 'Mem: 1000 500 100 0 400 500'
    if command.startswith('df -P -k'):
        return '/dev/sda1 100000 20000 80000 20% /'
    if command.startswith("free -m | awk '/^Swap:"):
        return '0 0'
    if command.startswith('df -Pi'):
        return '5'
    if command.startswith("cat /proc/uptime"):
        return '172800'
    if command.startswith('uptime -s'):
        return '2026-07-15 11:20:00'
    if command.startswith('cat /proc/net/dev'):
        return '1000 2000'
    return ''


class FakeSSHClient:
    def __init__(self, fail_first_command=False):
        self.fail_first_command = fail_first_command
        self.command_count = 0
        self.closed = False

    def set_missing_host_key_policy(self, _policy):
        pass

    def connect(self, *_args, **_kwargs):
        pass

    def exec_command(self, command):
        self.command_count += 1
        if self.fail_first_command and self.command_count == 1:
            raise RuntimeError('No existing session')
        return None, FakeStream(command_output(command)), FakeStream()

    def close(self):
        self.closed = True


def make_monitor():
    # check_ssh does not need the database or the SNMP background thread.
    return NetworkMonitor.__new__(NetworkMonitor)


def test_check_ssh_stays_out_of_eventlet_native_tpool(monkeypatch):
    client = FakeSSHClient()
    fake_paramiko = SimpleNamespace(
        SSHClient=lambda: client,
        AutoAddPolicy=lambda: object(),
    )
    monkeypatch.setattr(monitor_module, 'paramiko', fake_paramiko)
    monkeypatch.setattr(
        monitor_module.async_runtime,
        'tpool_execute',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError('native tpool used')),
    )

    result = make_monitor().check_ssh('10.0.0.1', 'user', 'password')

    assert result['status'] in ('up', 'slow')
    assert result['load1'] == 0.40
    assert result['cpu'] is None
    assert result['ram'] == 50.0
    assert client.closed is True


def test_check_ssh_reconnects_once_for_missing_session(monkeypatch):
    clients = [FakeSSHClient(fail_first_command=True), FakeSSHClient()]
    fake_paramiko = SimpleNamespace(
        SSHClient=lambda: clients.pop(0),
        AutoAddPolicy=lambda: object(),
    )
    monkeypatch.setattr(monitor_module, 'paramiko', fake_paramiko)

    result = make_monitor().check_ssh('10.0.0.1', 'user', 'password')

    assert result['status'] in ('up', 'slow')
    assert clients == []


def test_server_health_does_not_render_null_response_as_zero():
    # Number(null) is 0, so a response time the collector never recorded would
    # render as a confident "0.0 ms" without this guard.
    #
    # This test used to also cover responseClass() and renderResponseCell().
    # Those drew a Response column the fleet table no longer has, so nothing
    # called them any more and they were removed; the assertions went with
    # them. The figure itself is still shown -- by the Collection Time card
    # and the top-response card -- and both go through formatMs, which is what
    # is guarded here.
    template = Path('templates/server_health.html').read_text(encoding='utf-8')
    format_ms = template.split('function formatMs(', 1)[1].split('\nfunction ', 1)[0]

    assert "if (value === null || value === undefined || value === '') return '-';" in format_ms
    assert "Number.isFinite(num) ? `${num.toFixed(num >= 100 ? 0 : 1)} ms` : '-'" in format_ms
    assert 'formatMs(row.median)' in template
