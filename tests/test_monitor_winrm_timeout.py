from types import SimpleNamespace

from config import Config
import monitor as monitor_module
from monitor import NetworkMonitor


def make_monitor():
    return NetworkMonitor.__new__(NetworkMonitor)


def test_check_winrm_passes_bounded_transport_timeouts(monkeypatch):
    captured = {}

    class FakeSession:
        def __init__(self, *_args, **kwargs):
            captured.update(kwargs)

        def run_ps(self, _script):
            raise RuntimeError('stop after session creation')

    monkeypatch.setattr(monitor_module, 'WINRM_AVAILABLE', True)
    monkeypatch.setattr(monitor_module, 'winrm', SimpleNamespace(Session=FakeSession))
    monkeypatch.setattr(monitor_module.async_runtime, 'tpool_execute', lambda func: func())
    monkeypatch.setattr(Config, 'WINRM_OPERATION_TIMEOUT', 17)
    monkeypatch.setattr(Config, 'WINRM_READ_TIMEOUT', 27)

    result = make_monitor().check_winrm('10.0.0.1', 'user', 'password')

    assert result['status'] == 'down'
    assert captured['operation_timeout_sec'] == 17
    assert captured['read_timeout_sec'] == 27


def test_check_winrm_returns_timeout_without_raising(monkeypatch):
    class ImmediateTimeout:
        def __init__(self, _seconds):
            self.cancelled = False

        def cancel(self):
            self.cancelled = True

    monkeypatch.setattr(monitor_module, 'WINRM_AVAILABLE', True)
    monkeypatch.setattr(monitor_module.async_runtime, 'Timeout', ImmediateTimeout)
    monkeypatch.setattr(
        monitor_module.async_runtime,
        'tpool_execute',
        lambda _func: (_ for _ in ()).throw(monitor_module.async_runtime.TimeoutError()),
    )
    monkeypatch.setattr(Config, 'WINRM_DEVICE_TIMEOUT', 50)

    result = make_monitor().check_winrm('10.0.0.2', 'user', 'password')

    assert result == {
        'status': 'down',
        'response_time': None,
        'error': 'WinRM check exceeded 50s',
    }
