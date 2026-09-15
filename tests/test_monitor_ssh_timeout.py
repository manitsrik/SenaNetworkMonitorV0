"""A hung SSH host must give the monitoring worker back on a fixed budget."""
from types import SimpleNamespace

from config import Config
import monitor as monitor_module
from monitor import NetworkMonitor


class HangingSSHClient:
    """Accepts the connection, then never answers."""

    def __init__(self, on_connect):
        self.on_connect = on_connect
        self.closed = False

    def set_missing_host_key_policy(self, _policy):
        pass

    def connect(self, *_args, **_kwargs):
        self.on_connect()

    def exec_command(self, _command):
        raise AssertionError('should never get this far')

    def close(self):
        self.closed = True


def fake_paramiko(client):
    return SimpleNamespace(SSHClient=lambda: client, AutoAddPolicy=lambda: object())


def test_timeout_is_reported_as_down_instead_of_propagating(monkeypatch):
    client = HangingSSHClient(
        lambda: (_ for _ in ()).throw(monitor_module.async_runtime.TimeoutError())
    )

    class NoopTimeout:
        def __init__(self, _seconds):
            self.cancelled = False

        def cancel(self):
            self.cancelled = True

    monkeypatch.setattr(monitor_module, 'paramiko', fake_paramiko(client))
    monkeypatch.setattr(monitor_module.async_runtime, 'Timeout', NoopTimeout)
    monkeypatch.setattr(Config, 'SSH_DEVICE_TIMEOUT', 45)

    result = NetworkMonitor.__new__(NetworkMonitor).check_ssh('10.0.0.1', 'user', 'password')

    assert result == {
        'status': 'down',
        'response_time': None,
        'error': 'SSH check exceeded 45s',
    }
    # The timeout unwinds through _ssh_task, so the socket is still released.
    assert client.closed is True


def test_real_eventlet_timeout_interrupts_a_stalled_session(monkeypatch):
    # Unlike the WinRM tpool path, the SSH session lives in this greenlet, so
    # the timeout genuinely abandons it.
    client = HangingSSHClient(lambda: monitor_module.async_runtime.sleep(30))
    monkeypatch.setattr(monitor_module, 'paramiko', fake_paramiko(client))
    monkeypatch.setattr(Config, 'SSH_DEVICE_TIMEOUT', 1)

    result = NetworkMonitor.__new__(NetworkMonitor).check_ssh('10.0.0.2', 'user', 'password')

    assert result['status'] == 'down'
    assert result['error'] == 'SSH check exceeded 1s'
    assert client.closed is True
