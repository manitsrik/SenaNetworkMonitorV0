import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from flask import Flask

from alerter import Alerter
from plugin_manager import PluginManager
from routes.auth import auth_bp
from routes.plugins import plugins_bp
from secret_store import ENCRYPTED_PREFIX, decrypt_secret


class FakeDB:
    def __init__(self):
        self.settings = {}
        self.alert_logs = []

    def get_alert_setting(self, key):
        return self.settings.get(key)

    def save_alert_setting(self, key, value):
        self.settings[key] = value
        return {'success': True}

    def log_alert(self, device_id, event_type, message, channel, status, error=None):
        self.alert_logs.append({
            'device_id': device_id,
            'event_type': event_type,
            'message': message,
            'channel': channel,
            'status': status,
            'error': error,
        })
        return {'success': True}


class PluginIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDB()
        self.plugin_manager = PluginManager(self.db)
        self.alerter = Alerter(self.db)
        self.alerter.plugin_manager = self.plugin_manager

        app = Flask(__name__)
        app.config['SECRET_KEY'] = 'test-secret'
        app.config['TESTING'] = True
        app.config['DB'] = self.db
        app.config['PLUGIN_MANAGER'] = self.plugin_manager
        app.config['ALERTER'] = self.alerter
        app.register_blueprint(auth_bp)
        app.register_blueprint(plugins_bp)

        self.app = app
        self.client = app.test_client()

        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['role'] = 'admin'

    def test_generic_webhook_validation_rules(self):
        invalid_url = self.plugin_manager.validate_integration_config('generic_webhook', {
            'url': 'not-a-url',
            'method': 'POST',
            'timeout_seconds': 10,
            'verify_tls': True,
            'bearer_token': '',
            'header_name': '',
            'header_value': '',
        })
        self.assertFalse(invalid_url['success'])
        self.assertIn('valid HTTP/HTTPS URL', invalid_url['error'])

        invalid_timeout = self.plugin_manager.validate_integration_config('generic_webhook', {
            'url': 'https://example.com/webhook',
            'method': 'POST',
            'timeout_seconds': 120,
            'retry_attempts': 2,
            'retry_backoff_seconds': 1,
            'verify_tls': True,
            'bearer_token': '',
            'header_name': '',
            'header_value': '',
        })
        self.assertFalse(invalid_timeout['success'])
        self.assertIn('at most 60', invalid_timeout['error'])

        invalid_retries = self.plugin_manager.validate_integration_config('generic_webhook', {
            'url': 'https://example.com/webhook',
            'method': 'POST',
            'timeout_seconds': 10,
            'retry_attempts': 9,
            'retry_backoff_seconds': 1,
            'verify_tls': True,
            'bearer_token': '',
            'header_name': '',
            'header_value': '',
        })
        self.assertFalse(invalid_retries['success'])
        self.assertIn('at most 5', invalid_retries['error'])

    def test_secret_store_encrypts_and_decrypts(self):
        cipher = ENCRYPTED_PREFIX + 'x'
        encrypted = self.db.get_alert_setting('nonexistent')  # smoke no-op path
        self.assertIsNone(encrypted)

        from secret_store import encrypt_secret
        token = encrypt_secret('super-secret')
        self.assertTrue(token.startswith(ENCRYPTED_PREFIX))
        self.assertNotIn('super-secret', token)
        self.assertEqual(decrypt_secret(token), 'super-secret')

    def test_integration_secret_keep_replace_clear(self):
        create_resp = self.client.post(
            '/api/plugins/integrations/generic_webhook/settings',
            json={
                'enabled': True,
                'config': {
                    'url': 'https://example.com/webhook',
                    'method': 'POST',
                    'timeout_seconds': 5,
                    'retry_attempts': 2,
                    'retry_backoff_seconds': 0,
                    'verify_tls': True,
                    'bearer_token': 'first-token',
                    'header_name': 'X-Test-Source',
                    'header_value': 'first-header',
                },
                'secret_actions': {
                    'bearer_token': 'replace',
                    'header_value': 'replace',
                }
            }
        )
        self.assertEqual(create_resp.status_code, 200)
        stored_bearer = self.db.get_alert_setting('plugin_integration_generic_webhook_secret_bearer_token')
        stored_header = self.db.get_alert_setting('plugin_integration_generic_webhook_secret_header_value')
        self.assertTrue(stored_bearer.startswith(ENCRYPTED_PREFIX))
        self.assertTrue(stored_header.startswith(ENCRYPTED_PREFIX))
        self.assertEqual(decrypt_secret(stored_bearer), 'first-token')
        self.assertEqual(decrypt_secret(stored_header), 'first-header')

        stored_config = json.loads(self.db.get_alert_setting('plugin_integration_generic_webhook_config_json'))
        self.assertNotIn('bearer_token', stored_config)
        self.assertNotIn('header_value', stored_config)
        self.assertEqual(stored_config['header_name'], 'X-Test-Source')

        list_resp = self.client.get('/api/plugins/integration-types')
        self.assertEqual(list_resp.status_code, 200)
        generic = next(item for item in list_resp.get_json() if item['id'] == 'generic_webhook')
        self.assertNotIn('bearer_token', generic['runtime_config'])
        self.assertNotIn('header_value', generic['runtime_config'])
        self.assertTrue(generic['runtime_secret_fields']['bearer_token'])
        self.assertTrue(generic['runtime_secret_fields']['header_value'])

        keep_resp = self.client.post(
            '/api/plugins/integrations/generic_webhook/settings',
            json={
                'enabled': True,
                'config': {
                    'url': 'https://example.com/updated',
                    'method': 'PUT',
                    'timeout_seconds': 6,
                    'retry_attempts': 1,
                    'retry_backoff_seconds': 0,
                    'verify_tls': False,
                    'bearer_token': '',
                    'header_name': 'X-Test-Source',
                    'header_value': '',
                },
                'secret_actions': {
                    'bearer_token': 'keep',
                    'header_value': 'keep',
                }
            }
        )
        self.assertEqual(keep_resp.status_code, 200)
        self.assertEqual(
            decrypt_secret(self.db.get_alert_setting('plugin_integration_generic_webhook_secret_bearer_token')),
            'first-token'
        )
        self.assertEqual(
            decrypt_secret(self.db.get_alert_setting('plugin_integration_generic_webhook_secret_header_value')),
            'first-header'
        )

        replace_resp = self.client.post(
            '/api/plugins/integrations/generic_webhook/settings',
            json={
                'enabled': True,
                'config': {
                    'url': 'https://example.com/updated',
                    'method': 'PUT',
                    'timeout_seconds': 6,
                    'retry_attempts': 1,
                    'retry_backoff_seconds': 0,
                    'verify_tls': False,
                    'bearer_token': 'second-token',
                    'header_name': 'X-Test-Source',
                    'header_value': 'second-header',
                },
                'secret_actions': {
                    'bearer_token': 'replace',
                    'header_value': 'replace',
                }
            }
        )
        self.assertEqual(replace_resp.status_code, 200)
        self.assertEqual(
            decrypt_secret(self.db.get_alert_setting('plugin_integration_generic_webhook_secret_bearer_token')),
            'second-token'
        )
        self.assertEqual(
            decrypt_secret(self.db.get_alert_setting('plugin_integration_generic_webhook_secret_header_value')),
            'second-header'
        )

        clear_resp = self.client.post(
            '/api/plugins/integrations/generic_webhook/settings',
            json={
                'enabled': True,
                'config': {
                    'url': 'https://example.com/updated',
                    'method': 'PUT',
                    'timeout_seconds': 6,
                    'retry_attempts': 1,
                    'retry_backoff_seconds': 0,
                    'verify_tls': False,
                    'bearer_token': '',
                    'header_name': 'X-Test-Source',
                    'header_value': '',
                },
                'secret_actions': {
                    'bearer_token': 'clear',
                    'header_value': 'keep',
                }
            }
        )
        self.assertEqual(clear_resp.status_code, 200)
        self.assertEqual(self.db.get_alert_setting('plugin_integration_generic_webhook_secret_bearer_token'), '')
        self.assertEqual(
            decrypt_secret(self.db.get_alert_setting('plugin_integration_generic_webhook_secret_header_value')),
            'second-header'
        )

    def test_generic_webhook_delivery(self):
        received = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self_inner):
                length = int(self_inner.headers.get('Content-Length', '0'))
                body = self_inner.rfile.read(length).decode('utf-8')
                received['auth'] = self_inner.headers.get('Authorization')
                received['extra'] = self_inner.headers.get('X-Test-Source')
                received['payload'] = json.loads(body)
                self_inner.send_response(200)
                self_inner.end_headers()
                self_inner.wfile.write(b'{"ok": true}')

            def log_message(self_inner, format, *args):
                return

        server = HTTPServer(('127.0.0.1', 0), Handler)
        port = server.server_port
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()

        try:
            result = self.plugin_manager.execute_integration_plugin(
                'generic_webhook',
                payload={
                    'subject': 'Test Alert',
                    'message': 'Hello webhook',
                    'event_type': 'test',
                    'timestamp': '2026-04-02T00:00:00',
                    'source': 'NetMonitor'
                },
                plugin_config={
                    'url': f'http://127.0.0.1:{port}/ingest',
                    'method': 'POST',
                    'timeout_seconds': 5,
                    'retry_attempts': 0,
                    'retry_backoff_seconds': 0,
                    'verify_tls': True,
                    'bearer_token': 'abc123',
                    'header_name': 'X-Test-Source',
                    'header_value': 'nw-monitor-test',
                },
                integration_context={'is_test': True}
            )

            thread.join(timeout=5)
            self.assertTrue(result['success'])
            self.assertEqual(received['auth'], 'Bearer abc123')
            self.assertEqual(received['extra'], 'nw-monitor-test')
            self.assertEqual(received['payload']['subject'], 'Test Alert')
            self.assertTrue(received['payload']['integration_context']['is_test'])
            self.assertEqual(result['attempts'], 1)
        finally:
            server.server_close()

    def test_generic_webhook_retries_after_server_error(self):
        attempts = {'count': 0}

        class RetryHandler(BaseHTTPRequestHandler):
            def do_POST(self_inner):
                attempts['count'] += 1
                length = int(self_inner.headers.get('Content-Length', '0'))
                self_inner.rfile.read(length)
                if attempts['count'] == 1:
                    self_inner.send_response(500)
                    self_inner.end_headers()
                    self_inner.wfile.write(b'first failure')
                    return
                self_inner.send_response(200)
                self_inner.end_headers()
                self_inner.wfile.write(b'{"ok": true}')

            def log_message(self_inner, format, *args):
                return

        server = HTTPServer(('127.0.0.1', 0), RetryHandler)
        port = server.server_port
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            result = self.plugin_manager.execute_integration_plugin(
                'generic_webhook',
                payload={
                    'subject': 'Retry Test',
                    'message': 'Should succeed after retry',
                    'event_type': 'test',
                    'timestamp': '2026-04-02T00:00:00',
                    'source': 'NetMonitor'
                },
                plugin_config={
                    'url': f'http://127.0.0.1:{port}/retry',
                    'method': 'POST',
                    'timeout_seconds': 5,
                    'retry_attempts': 1,
                    'retry_backoff_seconds': 0,
                    'verify_tls': True,
                    'bearer_token': '',
                    'header_name': '',
                    'header_value': '',
                },
                integration_context={'is_test': True}
            )
            self.assertTrue(result['success'])
            self.assertEqual(result['attempts'], 2)
            self.assertEqual(attempts['count'], 2)
            self.assertEqual(result['status_code'], 200)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
