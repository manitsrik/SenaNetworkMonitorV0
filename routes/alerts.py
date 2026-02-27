"""
Alert settings and history API routes
"""
from flask import Blueprint, jsonify, request, current_app
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
