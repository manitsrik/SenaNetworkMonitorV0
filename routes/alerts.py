"""
Alert settings and history API routes
"""
from flask import Blueprint, jsonify, request, current_app, session
from .auth import operator_required

alerts_bp = Blueprint('alerts', __name__)


def _get_db():
    return current_app.config['DB']

def _get_alerter():
    return current_app.config['ALERTER']

def _get_report_generator():
    return current_app.config['REPORT_GENERATOR']


@alerts_bp.route('/api/alert-settings', methods=['GET'])
def get_alert_settings():
    """Get all alert settings"""
    settings = _get_db().get_all_alert_settings()
    settings_dict = {s['setting_key']: s['setting_value'] for s in settings}
    return jsonify(settings_dict)


@alerts_bp.route('/api/alert-settings', methods=['POST'])
@operator_required
def save_alert_settings():
    """Save alert settings"""
    data = request.json
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    db = _get_db()
    for key, value in data.items():
        db.save_alert_setting(key, str(value))
    
    # Clear alerter cache to pick up new settings
    alerter = _get_alerter()
    alerter._cache_time = None
    
    return jsonify({'success': True})


@alerts_bp.route('/api/alert-test/<channel>', methods=['POST'])
@operator_required
def test_alert(channel):
    """Send a test alert to verify configuration"""
    if channel not in ['email', 'line', 'telegram']:
        return jsonify({'success': False, 'error': 'Unknown channel'}), 400
    
    result = _get_alerter().send_test_alert(channel)
    return jsonify(result)


@alerts_bp.route('/api/alert-history', methods=['GET'])
def get_alert_history():
    """Get alert history"""
    limit = request.args.get('limit', 100, type=int)
    history = _get_db().get_alert_history(limit)
    return jsonify(history)


@alerts_bp.route('/api/alert-incidents', methods=['GET'])
def get_alert_incidents():
    """Get correlated alert incidents (MVP)."""
    limit = request.args.get('limit', 200, type=int)
    window_minutes = request.args.get('window_minutes', 10, type=int)
    dedupe_minutes = request.args.get('dedupe_minutes', 2, type=int)

    incidents = _get_db().get_alert_incidents(
        limit=limit,
        window_minutes=window_minutes,
        dedupe_minutes=dedupe_minutes,
    )
    return jsonify(incidents)


@alerts_bp.route('/api/alert-incidents/materialized', methods=['GET'])
def get_materialized_alert_incidents():
    """Get persistent incident snapshots."""
    active_only = request.args.get('active_only', 'true').lower() != 'false'
    limit = request.args.get('limit', 100, type=int)
    incidents = _get_db().get_persistent_incidents(active_only=active_only, limit=limit)
    return jsonify(incidents)


@alerts_bp.route('/api/alert-incidents/materialize', methods=['POST'])
@operator_required
def materialize_alert_incidents():
    """Run incident materialization on demand."""
    data = request.json or {}
    result = _get_db().sync_persistent_incidents(
        limit=data.get('limit', 500),
        window_minutes=data.get('window_minutes', 10),
        dedupe_minutes=data.get('dedupe_minutes', 2),
    )
    code = 200 if result.get('success') else 500
    return jsonify(result), code


@alerts_bp.route('/api/alert-incidents/<incident_id>/status', methods=['POST'])
@operator_required
def update_alert_incident_status(incident_id):
    """Update workflow status for a correlated incident."""
    data = request.json or {}
    status = (data.get('status') or '').strip().lower()
    note = (data.get('note') or '').strip() or None

    allowed = {'open', 'acknowledged', 'investigating', 'resolved'}
    if status not in allowed:
        return jsonify({'success': False, 'error': 'Invalid status'}), 400

    result = _get_db().update_incident_state(
        incident_id=incident_id,
        status=status,
        user_id=session.get('user_id'),
        username=session.get('username'),
        note=note,
    )
    code = 200 if result.get('success') else 500
    return jsonify(result), code


@alerts_bp.route('/api/alert-incidents/<incident_id>/owner', methods=['POST'])
@operator_required
def update_alert_incident_owner(incident_id):
    """Assign or clear owner for a correlated incident."""
    data = request.json or {}
    owner_user_id = data.get('owner_user_id')
    note = (data.get('note') or '').strip() or None

    owner_username = None
    owner_id = None

    if owner_user_id not in [None, '', 0, '0']:
        try:
            owner_id = int(owner_user_id)
        except Exception:
            return jsonify({'success': False, 'error': 'Invalid owner_user_id'}), 400

        user = _get_db().get_user_by_id(owner_id)
        if not user or not user.get('is_active'):
            return jsonify({'success': False, 'error': 'Owner not found or inactive'}), 400
        owner_username = user.get('display_name') or user.get('username')

    result = _get_db().update_incident_owner(
        incident_id=incident_id,
        owner_user_id=owner_id,
        owner_username=owner_username,
        actor_user_id=session.get('user_id'),
        actor_username=session.get('username'),
        note=note,
    )
    code = 200 if result.get('success') else 500
    return jsonify(result), code


@alerts_bp.route('/api/reports/test', methods=['POST'])
@operator_required
def send_test_report():
    """Send a test scheduled report"""
    try:
        rg = _get_report_generator()
        report_data = rg.generate_daily_report()
        html_content = rg.generate_html_report(report_data)
        result = rg.send_report_email(html_content, subject="Network Monitor - Test Report")
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
