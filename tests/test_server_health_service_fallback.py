"""The Service Down card falls back to what Windows already reports.

No device in the estate had named the services it needs, so the card read
"Not set up" while every Windows host was already reporting how many of its
own auto-start services were stopped. The fallback uses that, without letting
it pass for the stronger, named check.
"""
import json
from datetime import datetime
from pathlib import Path

from flask import Flask

from routes.devices import devices_bp


class FakeDB:
    def __init__(self, devices):
        self.devices = devices

    def get_all_devices(self):
        return self.devices

    def get_recent_metric_medians(self, device_ids, metric_type, minutes):
        return {}


def make_client(devices):
    app = Flask(__name__)
    app.config['DB'] = FakeDB(devices)
    app.register_blueprint(devices_bp)
    return app.test_client()


def _now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def windows_device(device_id=1, name='WIN-1', auto_stopped=6, monitored_services='',
                   service_status='[]'):
    summary = {'total': 293, 'running': 141, 'stopped': 152, 'source': 'windows'}
    if auto_stopped is not None:
        summary['auto_stopped'] = auto_stopped
    return {
        'id': device_id, 'name': name, 'ip_address': '10.0.0.%d' % device_id,
        'monitor_type': 'winrm', 'status': 'up', 'response_time': 900,
        'cpu_usage': 5.0, 'ram_usage': 40.0, 'disk_usage': 50.0, 'pending_reboot': 0,
        'monitored_services': monitored_services,
        'service_status_json': service_status,
        'service_summary_json': json.dumps(summary),
        'disk_details_json': '[]',
        'last_metrics_time': _now(),
    }


def linux_device(device_id=9, name='APP-1', monitored_services=''):
    # The SSH collector only ever knows the names it was given, so it reports
    # no whole-host figure to fall back on.
    return {
        'id': device_id, 'name': name, 'ip_address': '10.0.1.%d' % device_id,
        'monitor_type': 'ssh', 'status': 'up', 'response_time': 1100,
        'cpu_usage': 3.0, 'ram_usage': 20.0, 'disk_usage': 10.0, 'pending_reboot': 0,
        'monitored_services': monitored_services,
        'service_status_json': '[]',
        'service_summary_json': '{"monitored":0,"running":0,"stopped":0,"source":"selected"}',
        'disk_details_json': '[]',
        'last_metrics_time': _now(),
    }


def _summary(devices):
    response = make_client(devices).get('/api/server-health')
    assert response.status_code == 200
    return response.get_json()['summary']


def test_unconfigured_windows_hosts_contribute_their_auto_stopped_count():
    summary = _summary([
        windows_device(1, 'WIN-1', auto_stopped=6),
        windows_device(2, 'WIN-2', auto_stopped=9),
    ])

    assert summary['service_auto_stopped'] == 15
    assert summary['service_auto_stopped_servers'] == 2


def test_a_host_with_named_checks_is_left_out_of_the_fallback():
    # A named check is the better answer for that host, and counting both
    # would report the same machine twice under two different questions.
    summary = _summary([
        windows_device(1, 'WIN-1', auto_stopped=6),
        windows_device(2, 'WIN-2', auto_stopped=9, monitored_services='W3SVC',
                       service_status='[{"name":"W3SVC","ok":false}]'),
    ])

    assert summary['service_auto_stopped'] == 6
    assert summary['service_auto_stopped_servers'] == 1
    # The named check is still counted where it belongs.
    assert summary['service_down'] == 1
    assert summary['service_monitored_servers'] == 1


def test_linux_hosts_report_no_fallback_figure():
    summary = _summary([linux_device(9), linux_device(10)])

    assert summary['service_auto_stopped'] == 0
    assert summary['service_auto_stopped_servers'] == 0


def test_a_windows_host_that_reports_no_auto_stopped_figure_is_not_counted_as_zero():
    # "Did not report" and "reported none stopped" are different, and only the
    # second one should make the host part of the denominator.
    summary = _summary([windows_device(1, 'WIN-1', auto_stopped=None)])

    assert summary['service_auto_stopped_servers'] == 0

    summary = _summary([windows_device(1, 'WIN-1', auto_stopped=0)])

    assert summary['service_auto_stopped_servers'] == 1
    assert summary['service_auto_stopped'] == 0


def test_service_down_keeps_meaning_only_the_checks_somebody_named():
    # The daily report counts service_down the same way. Widening it here
    # would quietly change what that report claims.
    summary = _summary([
        windows_device(1, 'WIN-1', auto_stopped=6),
        linux_device(9, monitored_services='nginx'),
    ])

    assert summary['service_down'] == 0
    assert summary['service_auto_stopped'] == 6


# --- the page ------------------------------------------------------------


def _template():
    return (
        Path(__file__).resolve().parents[1] / "templates" / "server_health.html"
    ).read_text(encoding="utf-8")


def _function_body(template, name):
    return template.split("function %s(" % name, 1)[1].split("\nfunction ", 1)[0]


def test_the_page_tells_a_named_check_apart_from_the_windows_fallback():
    state = _function_body(_template(), "serviceState")

    assert "source: 'named'," in state
    assert "return { source: 'auto', count: auto };" in state
    assert "return { source: 'none', count: null };" in state


def test_the_fallback_does_not_borrow_the_badge_a_named_check_earns():
    template = _template()

    # A named check renders as a status badge; the weaker figure does not, so
    # the table cannot make them look like the same kind of statement.
    assert '<span class="service-auto is-stopped"' in template
    assert ".service-auto.is-stopped {" in template
    assert "auto-stopped</span>" in template


def test_the_card_says_which_question_the_number_answers():
    summary = _function_body(_template(), "setSummary")

    assert "} else if (autoServers) {" in summary
    assert "setText('delta-service', 'auto-start');" in summary
    assert "Auto-start, ${autoServers} Windows host" in summary
    # And still says so plainly when there is genuinely nothing to show.
    assert "serviceValue.textContent = 'Not set up';" in summary


def test_the_column_appears_when_either_source_has_something_to_say():
    template = _template()

    assert "!servers.some(server => serviceState(server).source !== 'none'));" in template
    assert "match: server => (serviceState(server).count || 0) > 0 }" in template
