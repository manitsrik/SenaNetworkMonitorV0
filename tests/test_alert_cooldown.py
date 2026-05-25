from datetime import datetime, timedelta
import unittest

from alerter import Alerter


class FakeAlertDB:
    def __init__(self):
        self.settings = {}
        self.last_alerts = {}

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
        return self.last_alerts.get((device_id, event_type))


class AlertCooldownTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeAlertDB()
        self.alerter = Alerter(self.db)

    def test_ssl_expiry_uses_dedicated_default_cooldown(self):
        self.db.settings['alert_cooldown'] = '300'
        self.db.last_alerts[(1, 'ssl_expiry')] = (
            datetime.now() - timedelta(minutes=10)
        ).isoformat()

        self.assertFalse(self.alerter.should_alert(1, 'ssl_expiry'))

    def test_ssl_expiry_dedicated_cooldown_can_be_configured(self):
        self.db.settings['alert_cooldown'] = '300'
        self.db.settings['ssl_alert_cooldown'] = '60'
        self.db.last_alerts[(1, 'ssl_expiry')] = (
            datetime.now() - timedelta(minutes=10)
        ).isoformat()

        self.assertTrue(self.alerter.should_alert(1, 'ssl_expiry'))


if __name__ == '__main__':
    unittest.main()
