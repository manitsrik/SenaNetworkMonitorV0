"""Every alert event type needs a switch an operator can actually flip."""
from alerter import Alerter


class FakeAlertDB:
    def __init__(self):
        self.settings = {}
        self.recipient_lookups = 0

    def get_all_alert_settings(self):
        return [
            {'setting_key': key, 'setting_value': value}
            for key, value in self.settings.items()
        ]

    def is_device_in_maintenance(self, device_id):
        return False

    def is_parent_device_down(self, device_id):
        return None

    def get_last_alert_time(self, device_id, event_type):
        return None

    def get_device_recipients(self, device_id):
        self.recipient_lookups += 1
        return {'emails': [], 'telegram_ids': []}


DEVICE = {'id': 1, 'name': 'app-01', 'ip_address': '10.0.0.1'}


def make_alerter():
    db = FakeAlertDB()
    return db, Alerter(db)


def test_internet_events_are_sent_by_default():
    db, alerter = make_alerter()

    alerter.trigger_alert(DEVICE, 'internet_down', 'DNS lookup failed')

    assert db.recipient_lookups == 1


def test_internet_events_can_be_switched_off():
    db, alerter = make_alerter()
    db.settings['alert_on_internet'] = 'false'

    alerter.trigger_alert(DEVICE, 'internet_down', 'DNS lookup failed')
    alerter.trigger_alert(DEVICE, 'internet_recovery', 'Back online')

    assert db.recipient_lookups == 0


def test_switching_internet_events_off_leaves_down_alerts_alone():
    db, alerter = make_alerter()
    db.settings['alert_on_internet'] = 'false'

    alerter.trigger_alert(DEVICE, 'down', 'No response')

    assert db.recipient_lookups == 1
