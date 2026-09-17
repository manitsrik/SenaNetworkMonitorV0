"""SNMP metric collection is independent of what decides up and down.

A branch router is judged reachable by ping - that is the only check that
measures the tunnel itself - while its interface counters only exist over SNMP.
Tying both to monitor_type forced a choice between reachability and throughput.
"""
import pytest

import monitor as monitor_module
import database as database_module
from config import Config
from database import Database
from monitor import NetworkMonitor


class FakePool:
    def __init__(self, size=None):
        self.size = size

    def imap(self, fn, items):
        return [fn(item) for item in items]


@pytest.fixture
def probe(monkeypatch):
    monkeypatch.setattr(monitor_module.async_runtime, 'GreenPool', FakePool)
    monkeypatch.setattr(monitor_module, 'SNMP_AVAILABLE', True, raising=False)
    instance = NetworkMonitor.__new__(NetworkMonitor)
    polled = []
    instance.poll_bandwidth = lambda device: polled.append(device['name'])
    return instance, polled


def device(**overrides):
    base = {'id': 1, 'name': 'site', 'ip_address': '10.0.0.1', 'monitor_type': 'ping',
            'is_enabled': True, 'snmp_metrics_enabled': False}
    base.update(overrides)
    return base


def run(probe, devices):
    instance, polled = probe
    instance.db = type('DB', (), {'get_all_devices': staticmethod(lambda: devices)})()
    instance.poll_bandwidth_all_snmp_devices()
    return polled


def test_a_ping_monitored_site_with_the_flag_is_polled(probe):
    devices = [device(name='Kith-Samrong', monitor_type='ping', snmp_metrics_enabled=True)]
    assert run(probe, devices) == ['Kith-Samrong']


def test_an_snmp_monitored_device_is_still_polled_without_the_flag(probe):
    # The flag adds a way in; it does not become the only way in.
    devices = [device(name='core-switch', monitor_type='snmp', snmp_metrics_enabled=False)]
    assert run(probe, devices) == ['core-switch']


def test_a_ping_monitored_site_without_the_flag_is_left_alone(probe):
    devices = [device(name='plain-site', monitor_type='ping', snmp_metrics_enabled=False)]
    assert run(probe, devices) == []


def test_a_disabled_device_is_never_polled_however_it_is_flagged(probe):
    devices = [
        device(id=1, name='off-flagged', snmp_metrics_enabled=True, is_enabled=False),
        device(id=2, name='off-snmp', monitor_type='snmp', is_enabled=False),
    ]
    assert run(probe, devices) == []


def test_a_device_row_without_the_column_does_not_break_the_poll(probe):
    # Rows read before the migration ran carry no key at all.
    legacy = {'id': 9, 'name': 'legacy', 'ip_address': '10.0.0.9',
              'monitor_type': 'ping', 'is_enabled': True}
    assert run(probe, [legacy]) == []


def test_the_flag_survives_a_save(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, 'DB_TYPE', 'sqlite')
    monkeypatch.setattr(database_module.Config, 'DB_TYPE', 'sqlite')
    monkeypatch.setattr(Database, '_pool', None)
    db = Database(db_path=str(tmp_path / 'flag.db'))

    created = db.add_device('Kith-Samrong', '10.245.1.2', device_type='vpnrouter', monitor_type='ping')
    device_id = created['id'] if isinstance(created, dict) else created

    assert not db.get_device(device_id).get('snmp_metrics_enabled')

    # A device created with the switch already on keeps it, rather than needing
    # a second save to make the setting stick.
    born_on = db.add_device('born-on', '10.245.1.3', device_type='vpnrouter',
                            monitor_type='ping', snmp_metrics_enabled=True)
    born_on_id = born_on['id'] if isinstance(born_on, dict) else born_on
    assert db.get_device(born_on_id)['snmp_metrics_enabled']

    db.update_device(device_id, snmp_metrics_enabled=True)
    assert db.get_device(device_id)['snmp_metrics_enabled']

    db.update_device(device_id, snmp_metrics_enabled=False)
    assert not db.get_device(device_id)['snmp_metrics_enabled']


def test_an_unrelated_save_leaves_the_flag_alone(tmp_path, monkeypatch):
    # The form posts every field; a save that omits this one must not clear it.
    monkeypatch.setattr(Config, 'DB_TYPE', 'sqlite')
    monkeypatch.setattr(database_module.Config, 'DB_TYPE', 'sqlite')
    monkeypatch.setattr(Database, '_pool', None)
    db = Database(db_path=str(tmp_path / 'flag2.db'))

    created = db.add_device('site', '10.0.0.7', device_type='vpnrouter', monitor_type='ping')
    device_id = created['id'] if isinstance(created, dict) else created
    db.update_device(device_id, snmp_metrics_enabled=True)

    db.update_device(device_id, name='site renamed')

    device = db.get_device(device_id)
    assert device['name'] == 'site renamed'
    assert device['snmp_metrics_enabled']
