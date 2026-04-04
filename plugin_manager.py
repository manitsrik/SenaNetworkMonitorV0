"""
Plugin system foundation for Network Monitor.

MVP scope:
- Load monitor plugins from the local `plugins/` directory
- Expose metadata for UI/API
- Execute monitor plugins by monitor_type `plugin:<plugin_id>`
"""
import importlib.util
import json
import os
import re
from datetime import datetime
from urllib.parse import urlparse


class PluginManager:
    def __init__(self, database=None, plugin_dir=None):
        self.db = database
        self.plugin_dir = plugin_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'plugins')
        self._plugins = {}
        self.reload_plugins()

    def reload_plugins(self):
        """Reload plugin manifests and Python entrypoints from disk."""
        self._plugins = {}
        os.makedirs(self.plugin_dir, exist_ok=True)

        for entry in os.listdir(self.plugin_dir):
            plugin_path = os.path.join(self.plugin_dir, entry)
            if not os.path.isdir(plugin_path):
                continue

            manifest_path = os.path.join(plugin_path, 'manifest.json')
            entrypoint_path = os.path.join(plugin_path, 'plugin.py')
            if not os.path.exists(manifest_path) or not os.path.exists(entrypoint_path):
                continue

            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)

                plugin_id = str(manifest.get('id') or '').strip()
                if not plugin_id:
                    raise ValueError('Plugin manifest missing id')

                spec = importlib.util.spec_from_file_location(f'nw_plugin_{plugin_id}', entrypoint_path)
                if spec is None or spec.loader is None:
                    raise ValueError('Unable to create import spec')
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                plugin_class = getattr(module, 'Plugin', None)
                if plugin_class is None:
                    raise ValueError('Plugin class not found in plugin.py')

                instance = plugin_class()
                plugin_type = manifest.get('type', 'monitor')
                monitor_type = manifest.get('monitor_type') or f'plugin:{plugin_id}'
                self._plugins[plugin_id] = {
                    'id': plugin_id,
                    'name': manifest.get('name', plugin_id),
                    'version': manifest.get('version', '0.1.0'),
                    'description': manifest.get('description', ''),
                    'type': plugin_type,
                    'monitor_type': monitor_type,
                    'ui_hint': manifest.get('ui_hint', 'generic'),
                    'config_schema': manifest.get('config_schema', []),
                    'enabled': bool(manifest.get('enabled', True)),
                    'path': plugin_path,
                    'loaded_at': datetime.now().isoformat(),
                    'instance': instance,
                    'manifest': manifest,
                }
            except Exception as e:
                plugin_id = entry
                self._plugins[plugin_id] = {
                    'id': plugin_id,
                    'name': plugin_id,
                    'version': 'error',
                    'description': str(e),
                    'type': 'invalid',
                    'monitor_type': f'plugin:{plugin_id}',
                    'ui_hint': 'generic',
                    'config_schema': [],
                    'enabled': False,
                    'path': plugin_path,
                    'loaded_at': datetime.now().isoformat(),
                    'instance': None,
                    'manifest': {},
                    'load_error': str(e),
                }

        return self.list_plugins()

    def list_plugins(self, plugin_type=None):
        """List plugin metadata without live instances."""
        items = []
        for plugin in self._plugins.values():
            if plugin_type and plugin.get('type') != plugin_type:
                continue
            item = {k: v for k, v in plugin.items() if k not in {'instance', 'manifest'}}
            items.append(item)
        items.sort(key=lambda p: (p.get('type') or '', p.get('name') or p.get('id') or ''))
        return items

    def get_monitor_plugins(self):
        """Return enabled monitor plugins for device UI consumption."""
        return [
            plugin for plugin in self.list_plugins(plugin_type='monitor')
            if plugin.get('enabled')
        ]

    def get_integration_plugins(self):
        """Return enabled integration plugins for alert delivery."""
        return [
            plugin for plugin in self.list_plugins(plugin_type='integration')
            if plugin.get('enabled')
        ]

    def get_plugin(self, plugin_id, plugin_type=None, enabled_only=False):
        """Get a plugin by id with optional type/enabled filters."""
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            return None
        if plugin_type and plugin.get('type') != plugin_type:
            return None
        if enabled_only and not plugin.get('enabled'):
            return None
        return plugin

    def get_secret_field_keys(self, plugin_id=None, plugin_type=None, schema=None):
        """Return secret field keys defined in plugin schema."""
        resolved_schema = schema
        if resolved_schema is None and plugin_id:
            plugin = self.get_plugin(plugin_id, plugin_type=plugin_type)
            resolved_schema = (plugin or {}).get('config_schema') or []
        return [
            field.get('key')
            for field in (resolved_schema or [])
            if field.get('key') and field.get('type') == 'secret'
        ]

    def get_plugin_by_monitor_type(self, monitor_type):
        """Get an enabled monitor plugin by monitor_type value."""
        for plugin in self._plugins.values():
            if plugin.get('type') != 'monitor':
                continue
            if not plugin.get('enabled'):
                continue
            if plugin.get('monitor_type') == monitor_type:
                return plugin
        return None

    def _validate_schema_config(self, schema, plugin_config, existing_secret_keys=None):
        """Validate config against a generic manifest schema."""
        config = plugin_config or {}
        normalized = {}
        existing_secret_keys = set(existing_secret_keys or [])

        for field in schema or []:
            key = field.get('key')
            if not key:
                continue

            field_type = field.get('type', 'text')
            required = bool(field.get('required', False))
            default = field.get('default')
            raw_value = config.get(key, default)

            if field_type == 'boolean':
                if isinstance(raw_value, str):
                    value = raw_value.strip().lower() in {'1', 'true', 'yes', 'on'}
                else:
                    value = bool(raw_value)
            elif field_type == 'number':
                if raw_value in (None, ''):
                    value = None
                else:
                    try:
                        value = int(raw_value) if str(raw_value).isdigit() else float(raw_value)
                    except Exception:
                        return {'success': False, 'error': f'Invalid number for {field.get("label") or key}'}
            else:
                value = '' if raw_value is None else str(raw_value).strip()

            if required and field_type == 'secret' and value in (None, '') and key not in existing_secret_keys:
                return {'success': False, 'error': f'{field.get("label") or key} is required'}

            if required and field_type not in {'boolean', 'secret'} and value in (None, ''):
                return {'success': False, 'error': f'{field.get("label") or key} is required'}

            options = field.get('options') or []
            if options and value not in (None, ''):
                allowed_values = [opt.get('value') if isinstance(opt, dict) else opt for opt in options]
                if value not in allowed_values:
                    return {'success': False, 'error': f'Invalid option for {field.get("label") or key}'}

            if field_type == 'number' and value is not None:
                min_value = field.get('min')
                max_value = field.get('max')
                if min_value is not None and value < min_value:
                    return {'success': False, 'error': f'{field.get("label") or key} must be at least {min_value}'}
                if max_value is not None and value > max_value:
                    return {'success': False, 'error': f'{field.get("label") or key} must be at most {max_value}'}

            if value not in (None, '') and field.get('pattern'):
                try:
                    if not re.fullmatch(field.get('pattern'), str(value)):
                        return {'success': False, 'error': f'{field.get("label") or key} has invalid format'}
                except re.error:
                    return {'success': False, 'error': f'Invalid validation pattern for {field.get("label") or key}'}

            if value not in (None, '') and field.get('format') == 'url':
                parsed = urlparse(str(value))
                if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
                    return {'success': False, 'error': f'{field.get("label") or key} must be a valid HTTP/HTTPS URL'}

            normalized[key] = value

        return {'success': True, 'config': normalized}

    def validate_plugin_config(self, monitor_type, plugin_config):
        """Validate plugin config against manifest schema."""
        plugin = self.get_plugin_by_monitor_type(monitor_type)
        if plugin is None:
            return {'success': False, 'error': f'No plugin registered for monitor type: {monitor_type}'}
        return self._validate_schema_config(plugin.get('config_schema') or [], plugin_config)

    def validate_integration_config(self, plugin_id, plugin_config, existing_secret_keys=None):
        """Validate config for an integration plugin by id."""
        plugin = self.get_plugin(plugin_id, plugin_type='integration')
        if plugin is None:
            return {'success': False, 'error': f'No integration plugin registered: {plugin_id}'}
        return self._validate_schema_config(
            plugin.get('config_schema') or [],
            plugin_config,
            existing_secret_keys=existing_secret_keys
        )

    def execute_monitor_plugin(self, monitor_type, device, monitor_context=None):
        """Execute a monitor plugin and normalize its result shape."""
        plugin = self.get_plugin_by_monitor_type(monitor_type)
        if plugin is None:
            return {
                'status': 'down',
                'response_time': None,
                'error': f'No plugin registered for monitor type: {monitor_type}'
            }

        instance = plugin.get('instance')
        if instance is None or not hasattr(instance, 'check'):
            return {
                'status': 'down',
                'response_time': None,
                'error': f'Plugin {plugin["id"]} is not executable'
            }

        if device.get('plugin_config') is None and device.get('plugin_config_json'):
            try:
                device = dict(device)
                device['plugin_config'] = json.loads(device.get('plugin_config_json') or '{}')
            except Exception:
                device = dict(device)
                device['plugin_config'] = {}

        result = instance.check(device, monitor_context or {})
        if not isinstance(result, dict):
            raise ValueError(f'Plugin {plugin["id"]} returned invalid result type')

        if 'status' not in result:
            result['status'] = 'down'
        if 'response_time' not in result:
            result['response_time'] = None
        result.setdefault('plugin_id', plugin.get('id'))
        result.setdefault('plugin_name', plugin.get('name'))
        return result

    def execute_integration_plugin(self, plugin_id, payload, plugin_config=None, integration_context=None):
        """Execute an integration plugin and normalize its result shape."""
        plugin = self.get_plugin(plugin_id, plugin_type='integration', enabled_only=True)
        if plugin is None:
            return {'success': False, 'error': f'No enabled integration plugin registered: {plugin_id}'}

        instance = plugin.get('instance')
        if instance is None or not hasattr(instance, 'send'):
            return {'success': False, 'error': f'Integration plugin {plugin_id} is not executable'}

        validation = self.validate_integration_config(plugin_id, plugin_config or {})
        if not validation.get('success'):
            return validation

        result = instance.send(payload, validation.get('config') or {}, integration_context or {})
        if not isinstance(result, dict):
            raise ValueError(f'Plugin {plugin_id} returned invalid result type')

        result.setdefault('success', False)
        result.setdefault('plugin_id', plugin.get('id'))
        result.setdefault('plugin_name', plugin.get('name'))
        return result
