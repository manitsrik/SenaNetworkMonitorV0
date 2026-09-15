"""The SSH reconnect path must not report values from the failed attempt."""
from types import SimpleNamespace

import monitor as monitor_module
from monitor import NetworkMonitor


class FakeStream:
    def __init__(self, value=''):
        self.value = value.encode()

    def read(self):
        return self.value


def full_output(command):
    if command.startswith('grep -c ^processor'):
        return '4\n 11:20 up 2 days, load average: 0.40, 0.30, 0.20'
    if command == 'free -m | grep Mem':
        return 'Mem: 1000 500 100 0 400 500'
    if command.startswith('df -P -k'):
        return '/dev/sda1 100000 20000 80000 20% /'
    if command.startswith("free -m | awk '/^Swap:"):
        return '0 0'
    if command.startswith('df -Pi'):
        return '5'
    if command.startswith('cat /proc/uptime'):
        return '172800'
    if command.startswith('uptime -s'):
        return '2026-07-15 11:20:00'
    if command.startswith('cat /proc/net/dev'):
        return '1000 2000'
    return ''


def output_without_uptime_and_network(command):
    """A host that answers the resource commands but not the uptime ones."""
    if command.startswith(('cat /proc/uptime', 'uptime -s', 'cat /proc/net/dev')):
        return ''
    return full_output(command)


class FakeSSHClient:
    def __init__(self, output_for=full_output, fail_at_command=None):
        self.output_for = output_for
        self.fail_at_command = fail_at_command
        self.command_count = 0

    def set_missing_host_key_policy(self, _policy):
        pass

    def connect(self, *_args, **_kwargs):
        pass

    def exec_command(self, command):
        self.command_count += 1
        if self.command_count == self.fail_at_command:
            raise RuntimeError('No existing session')
        return None, FakeStream(self.output_for(command)), FakeStream()

    def close(self):
        pass


def test_reconnect_discards_metrics_from_the_failed_attempt(monkeypatch):
    # The first session dies after it has already collected uptime and boot
    # time; the retry reaches a host that answers neither.
    clients = [
        FakeSSHClient(fail_at_command=8),
        FakeSSHClient(output_for=output_without_uptime_and_network),
    ]
    monkeypatch.setattr(monitor_module, 'paramiko', SimpleNamespace(
        SSHClient=lambda: clients.pop(0),
        AutoAddPolicy=lambda: object(),
    ))

    result = NetworkMonitor.__new__(NetworkMonitor).check_ssh('10.0.0.1', 'user', 'password')

    assert result['status'] in ('up', 'slow')
    assert clients == []
    assert result['cpu'] == 10.0
    assert result['uptime_seconds'] is None
    assert result['uptime_text'] is None
    assert result['last_boot_time'] is None
    assert result['net_in'] is None
