import unittest

from flask import Flask

from routes.assistant import assistant_bp
from routes.auth import auth_bp


class FakeMonitor:
    def __init__(self):
        self.checked = []

    def check_device(self, device):
        self.checked.append(device['id'])
        return {
            'id': device['id'],
            'name': device['name'],
            'status': 'up',
            'last_check': '2026-04-16T10:30:00',
        }


class FakeSocketIO:
    def __init__(self):
        self.events = []

    def emit(self, event, payload, namespace='/'):
        self.events.append((event, payload, namespace))


class FakeDB:
    def __init__(self):
        self.audit = []

    def get_all_devices(self):
        return [
            {
                'id': 1,
                'name': 'Core Router',
                'ip_address': '10.0.0.1',
                'status': 'up',
                'response_time': 10,
                'location': 'HQ',
                'device_type': 'router',
                'monitor_type': 'snmp',
                'last_check': '2026-04-16T10:00:00',
            }
        ]

    def get_alert_history(self, limit=20):
        return []

    def get_persistent_incidents(self, active_only=True, limit=20):
        return []

    def get_anomaly_snapshots(self, active_only=True, limit=20):
        return []

    def get_top_bandwidth_interfaces(self, minutes=15, top_n=10):
        return []

    def get_all_devices_sla(self, days=30, sla_target=99.9):
        return []

    def add_audit_log(self, **kwargs):
        self.audit.append(kwargs)

    def get_device(self, device_id):
        if device_id == 1:
            return {
                'id': 1,
                'name': 'Core Router',
                'ip_address': '10.0.0.1',
                'status': 'up',
                'device_type': 'router',
                'monitor_type': 'snmp',
            }
        return None


class AssistantRouteTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDB()
        self.monitor = FakeMonitor()
        self.socketio = FakeSocketIO()

        app = Flask(__name__)
        app.config['SECRET_KEY'] = 'test-secret'
        app.config['TESTING'] = True
        app.config['DB'] = self.db
        app.config['MONITOR'] = self.monitor
        app.config['SOCKETIO'] = self.socketio
        app.register_blueprint(auth_bp)
        app.register_blueprint(assistant_bp)

        self.app = app
        self.client = app.test_client()

    def _login(self, role='admin'):
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['user_id'] = 1
            sess['username'] = 'tester'
            sess['role'] = role

    def test_chat_route_returns_actions_for_device_status(self):
        self._login('admin')
        resp = self.client.post('/api/assistant/chat', json={'message': 'status Core Router'})
        payload = resp.get_json()

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(payload['intent'], 'device_status')
        self.assertTrue(payload['actions'])
        self.assertEqual(payload['actions'][0]['id'], 'check_device_now')
        self.assertTrue(payload['links'])

    def test_action_route_runs_safe_device_check(self):
        self._login('operator')
        resp = self.client.post('/api/assistant/action', json={
            'action_id': 'check_device_now',
            'payload': {'device_id': 1},
        })
        payload = resp.get_json()

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(payload['success'])
        self.assertEqual(self.monitor.checked, [1])
        self.assertEqual(self.socketio.events[0][0], 'status_update')

    def test_action_route_requires_operator(self):
        self._login('viewer')
        resp = self.client.post('/api/assistant/action', json={
            'action_id': 'check_device_now',
            'payload': {'device_id': 1},
        })

        self.assertEqual(resp.status_code, 403)

    def test_chat_route_persists_follow_up_context_in_session(self):
        self._login('admin')
        first = self.client.post('/api/assistant/chat', json={'message': 'status HQ'})
        second = self.client.post('/api/assistant/chat', json={'message': 'เอาเฉพาะที่ปกติ'})

        first_payload = first.get_json()
        second_payload = second.get_json()

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first_payload['intent'], 'location_status')
        self.assertEqual(second_payload['intent'], 'location_status')
        self.assertIn('HQ', second_payload['answer'])
        self.assertIn('ปกติ', second_payload['answer'])

    def test_reset_context_route_clears_assistant_session(self):
        self._login('admin')
        self.client.post('/api/assistant/chat', json={'message': 'status HQ'})
        reset = self.client.post('/api/assistant/context/reset', json={})

        self.assertEqual(reset.status_code, 200)
        self.assertTrue(reset.get_json()['success'])

        with self.client.session_transaction() as sess:
            self.assertFalse(sess.get('assistant_context'))


if __name__ == '__main__':
    unittest.main()
