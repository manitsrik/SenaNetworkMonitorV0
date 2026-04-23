import importlib
import os
import sys
import unittest


class ConfigSecurityTests(unittest.TestCase):
    def _reload_config(self, overrides):
        module_name = 'config'
        previous = {key: os.environ.get(key) for key in overrides}

        try:
            for key, value in overrides.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

            if module_name in sys.modules:
                del sys.modules[module_name]
            module = importlib.import_module(module_name)
            return module.Config
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            if module_name in sys.modules:
                del sys.modules[module_name]

    def test_runtime_warnings_flag_insecure_defaults(self):
        Config = self._reload_config({
            'DEBUG': 'false',
            'TESTING': 'false',
            'SECRET_KEY': 'dev-secret-key-change-in-production',
            'SECRET_ENCRYPTION_KEY': 'dev-secret-key-change-in-production',
            'DB_TYPE': 'postgresql',
            'PG_PASSWORD': 'netmonitor_password',
            'CORS_ALLOWED_ORIGINS': 'https://app.example.com,*',
        })

        warnings = Config.runtime_warnings()

        self.assertTrue(any('SECRET_KEY' in item for item in warnings))
        self.assertTrue(any('SECRET_ENCRYPTION_KEY matches SECRET_KEY' in item for item in warnings))
        self.assertTrue(any('PG_PASSWORD' in item for item in warnings))
        self.assertTrue(any('Wildcard CORS origins' in item for item in warnings))

    def test_validate_runtime_raises_in_strict_production_mode(self):
        Config = self._reload_config({
            'DEBUG': 'false',
            'TESTING': 'false',
            'STRICT_STARTUP_VALIDATION': 'true',
            'SECRET_KEY': 'dev-secret-key-change-in-production',
            'SECRET_ENCRYPTION_KEY': 'dev-secret-key-change-in-production',
        })

        with self.assertRaises(ValueError):
            Config.validate_runtime()

    def test_origin_lists_are_parsed_from_csv(self):
        Config = self._reload_config({
            'CORS_ALLOWED_ORIGINS': 'https://app.example.com, https://ops.example.com ',
            'SOCKETIO_CORS_ALLOWED_ORIGINS': 'https://ws.example.com',
        })

        self.assertEqual(
            Config.CORS_ALLOWED_ORIGINS,
            ['https://app.example.com', 'https://ops.example.com']
        )
        self.assertEqual(Config.SOCKETIO_CORS_ALLOWED_ORIGINS, ['https://ws.example.com'])


if __name__ == '__main__':
    unittest.main()
