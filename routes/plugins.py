import json
from flask import Blueprint, jsonify, current_app, render_template, request
from .auth import login_required, operator_required
from secret_store import encrypt_secret


plugins_bp = Blueprint('plugins', __name__)


def _get_plugin_manager():
    return current_app.config['PLUGIN_MANAGER']


def _get_db():
    return current_app.config['DB']


def _get_alerter():
    return current_app.config['ALERTER']


def _integration_secret_setting_key(plugin_id, field_key):
    return f'plugin_integration_{plugin_id}_secret_{field_key}'


def _load_integration_runtime(plugin):
    db = _get_db()
    plugin_id = plugin.get('id')
    raw_config = db.get_alert_setting(f'plugin_integration_{plugin_id}_config_json') or '{}'
    try:
        config = json.loads(raw_config or '{}')
    except Exception:
        config = {}

    secret_state = {}
    for key in _get_plugin_manager().get_secret_field_keys(
        plugin_id=plugin_id,
        plugin_type='integration',
        schema=plugin.get('config_schema') or []
    ):
        secret_value = db.get_alert_setting(_integration_secret_setting_key(plugin_id, key))
        secret_state[key] = bool(secret_value)
        config.pop(key, None)

    return {
        'enabled': str(db.get_alert_setting(f'plugin_integration_{plugin_id}_enabled') or 'false').lower() == 'true',
        'config': config,
        'secret_state': secret_state,
    }


@plugins_bp.route('/plugins')
@login_required
def plugins_page():
    return render_template('plugins.html')


@plugins_bp.route('/api/plugins', methods=['GET'])
@login_required
def get_plugins():
    return jsonify(_get_plugin_manager().list_plugins())


@plugins_bp.route('/api/plugins/monitor-types', methods=['GET'])
@login_required
def get_plugin_monitor_types():
    return jsonify(_get_plugin_manager().get_monitor_plugins())


@plugins_bp.route('/api/plugins/integration-types', methods=['GET'])
@login_required
def get_plugin_integration_types():
    items = []
    for plugin in _get_plugin_manager().get_integration_plugins():
        item = dict(plugin)
        runtime = _load_integration_runtime(plugin)
        item['runtime_enabled'] = runtime['enabled']
        item['runtime_config'] = runtime['config']
        item['runtime_secret_fields'] = runtime['secret_state']
        items.append(item)
    return jsonify(items)


@plugins_bp.route('/api/plugins/integrations/<plugin_id>/settings', methods=['POST'])
@operator_required
def save_plugin_integration_settings(plugin_id):
    data = request.json or {}
    enabled = bool(data.get('enabled', False))
    config = dict(data.get('config') or {})
    secret_actions = data.get('secret_actions') or {}

    plugin = _get_plugin_manager().get_plugin(plugin_id, plugin_type='integration')
    if plugin is None:
        return jsonify({'success': False, 'error': f'No integration plugin registered: {plugin_id}'}), 404

    db = _get_db()
    secret_keys = _get_plugin_manager().get_secret_field_keys(
        plugin_id=plugin_id,
        plugin_type='integration',
        schema=plugin.get('config_schema') or []
    )
    existing_secret_keys = set()
    secrets_to_store = {}
    secrets_to_clear = set()

    validation_config = dict(config)
    for key in secret_keys:
        incoming = str(config.get(key) or '').strip()
        action = str(secret_actions.get(key) or 'keep').strip().lower()
        has_existing = bool(db.get_alert_setting(_integration_secret_setting_key(plugin_id, key)))

        if action == 'clear':
            secrets_to_clear.add(key)
            validation_config[key] = ''
            continue

        if incoming:
            secrets_to_store[key] = incoming
            validation_config[key] = incoming
            continue

        validation_config[key] = ''
        if has_existing:
            existing_secret_keys.add(key)

    validation = _get_plugin_manager().validate_integration_config(
        plugin_id,
        validation_config,
        existing_secret_keys=existing_secret_keys
    )
    if not validation.get('success'):
        return jsonify(validation), 400

    normalized_config = dict(validation.get('config') or {})
    for key in secret_keys:
        normalized_config.pop(key, None)

    db.save_alert_setting(f'plugin_integration_{plugin_id}_enabled', 'true' if enabled else 'false')
    db.save_alert_setting(
        f'plugin_integration_{plugin_id}_config_json',
        json.dumps(normalized_config, ensure_ascii=False)
    )

    for key in secret_keys:
        secret_setting_key = _integration_secret_setting_key(plugin_id, key)
        if key in secrets_to_clear:
            db.save_alert_setting(secret_setting_key, '')
        elif key in secrets_to_store:
            db.save_alert_setting(secret_setting_key, encrypt_secret(secrets_to_store[key]))

    _get_alerter()._cache_time = None
    runtime = _load_integration_runtime(plugin)
    return jsonify({
        'success': True,
        'enabled': enabled,
        'config': runtime['config'],
        'secret_state': runtime['secret_state']
    })


@plugins_bp.route('/api/plugins/integrations/<plugin_id>/test', methods=['POST'])
@operator_required
def test_plugin_integration(plugin_id):
    result = _get_alerter().send_test_alert(f'plugin:{plugin_id}')
    code = 200 if result.get('success') else 400
    return jsonify(result), code


@plugins_bp.route('/api/plugins/reload', methods=['POST'])
@operator_required
def reload_plugins():
    plugins = _get_plugin_manager().reload_plugins()
    return jsonify({'success': True, 'count': len(plugins), 'plugins': plugins})
