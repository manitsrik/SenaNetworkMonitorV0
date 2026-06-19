from datetime import datetime

from scheduler_reports import ReportGenerator


class FakeDB:
    def __init__(self, settings=None, devices=None):
        self.settings = settings or {}
        self.devices = devices or []

    def get_alert_setting(self, key):
        return self.settings.get(key)

    def save_alert_setting(self, key, value):
        self.settings[key] = value

    def get_all_devices(self):
        return self.devices


def test_server_health_report_filters_devices_and_escapes_html():
    db = FakeDB(devices=[
        {
            'id': 1, 'name': '<Server A>', 'ip_address': '10.0.0.1',
            'monitor_type': 'ssh', 'status': 'up', 'cpu_usage': 72,
            'ram_usage': 81, 'disk_usage': 55, 'pending_reboot': 0,
            'service_status_json': '[{"name":"nginx","status":"stopped","ok":false}]',
            'disk_details_json': '[{"mount":"/","use_percent":55}]',
        },
        {'id': 2, 'name': 'Switch', 'monitor_type': 'snmp', 'status': 'up'},
    ])
    generator = ReportGenerator(db)

    report = generator.generate_server_health_report()
    html = generator.generate_server_health_html(report)

    assert report['summary']['total'] == 1
    assert report['summary']['service_down'] == 1
    assert '&lt;Server A&gt;' in html
    assert '<Server A>' not in html


def test_weekly_server_report_sends_once_on_configured_day(monkeypatch):
    db = FakeDB(settings={
        'report_time': '08:00',
        'reports_enabled': 'false',
        'server_reports_enabled': 'true',
        'server_report_frequency': 'weekly',
        'server_report_weekday': '0',
    })
    generator = ReportGenerator(db)
    calls = []
    monkeypatch.setattr(generator, 'run_server_health_report', lambda: calls.append(True) or {'success': True})
    monday = datetime(2026, 6, 22, 8, 0)

    first = generator.run_scheduled_reports(monday)
    second = generator.run_scheduled_reports(monday)

    assert first['sent'] == ['server_health']
    assert second['sent'] == []
    assert len(calls) == 1


def test_scheduled_report_waits_for_configured_time(monkeypatch):
    db = FakeDB(settings={
        'report_time': '08:00',
        'server_reports_enabled': 'true',
        'server_report_frequency': 'daily',
    })
    generator = ReportGenerator(db)
    monkeypatch.setattr(generator, 'run_server_health_report', lambda: {'success': True})

    result = generator.run_scheduled_reports(datetime(2026, 6, 22, 7, 59))

    assert result['sent'] == []
    assert 'last_server_report_date' not in db.settings
