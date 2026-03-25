"""
Custom Reports management API routes
"""
from flask import Blueprint, jsonify, request, session, current_app, render_template
from datetime import datetime, timedelta
import json
from .auth import login_required, admin_required
from .audit import log_audit

reports_bp = Blueprint('reports', __name__)

def _get_db():
    return current_app.config['DB']

@reports_bp.route('/reports/builder', methods=['GET'])
@login_required
def reports_builder_page():
    return render_template('reports_builder.html')

@reports_bp.route('/reports/view/<int:report_id>', methods=['GET'])
@login_required
def view_report_page(report_id):
    db = _get_db()
    report = db.get_custom_report(report_id)
    if not report:
        return "Report not found", 404
        
    # Gather data for each widget
    widget_data = {}
    if 'widgets' in report:
        for w in report['widgets']:
            try:
                if w['config'] and isinstance(w['config'], str):
                    w['config'] = json.loads(w['config'])
            except:
                w['config'] = {}
                
            w_type = w['widget_type']
            wid = w['id']
            
            if w_type == 'uptime_summary':
                devices = db.get_all_devices()
                total = len(devices)
                up_count = sum(1 for d in devices if d.get('status') == 'up')
                down_count = sum(1 for d in devices if d.get('status') == 'down')
                slow_count = sum(1 for d in devices if d.get('status') == 'slow')
                uptime_percent = (up_count + slow_count) / total * 100 if total > 0 else 0
                widget_data[wid] = {
                    'total': total, 'up': up_count, 'down': down_count,
                    'slow': slow_count, 'uptime_percent': round(uptime_percent, 2)
                }
            elif w_type == 'down_devices':
                devices = db.get_all_devices()
                down_devices = [d for d in devices if d.get('status') == 'down']
                widget_data[wid] = down_devices
            elif w_type == 'slow_devices':
                devices = db.get_all_devices()
                slow_devices = [d for d in devices if d.get('status') == 'slow']
                widget_data[wid] = slow_devices
            elif w_type == 'recent_alerts':
                alerts = db.get_alert_history(limit=20)
                yesterday = (datetime.now() - timedelta(days=1)).isoformat()
                recent_alerts = [a for a in alerts if a.get('created_at', '') > yesterday]
                widget_data[wid] = recent_alerts
            elif w_type == 'bandwidth_top':
                # Simplified top bandwidth: this requires bandwidth_history query
                # For now, just pass an empty list or fetch basic interface stats if available
                # Wait, bandwidth_history has util_in, util_out
                # Let's get latest from db
                conn = db.get_connection()
                cursor = db._cursor(conn)
                ph = db._ph()
                cursor.execute(f'''
                    SELECT d.name as device_name, b.if_name, b.util_in, b.util_out, b.bps_in, b.bps_out
                    FROM bandwidth_history b
                    JOIN devices d ON b.device_id = d.id
                    WHERE b.sampled_at > {ph}
                    ORDER BY (b.util_in + b.util_out) DESC
                    LIMIT 10
                ''', ((datetime.now() - timedelta(hours=1)).isoformat(),))
                try:
                    widget_data[wid] = db._rows_to_dicts(cursor.fetchall())
                except:
                    widget_data[wid] = []
                db.release_connection(conn)
                
    return render_template('report_view.html', report=report, widget_data=widget_data)

@reports_bp.route('/api/reports', methods=['GET'])
@login_required
def get_reports():
    """Get all custom reports"""
    db = _get_db()
    reports = db.get_custom_reports()
    return jsonify(reports)

@reports_bp.route('/api/reports', methods=['POST'])
@admin_required
def create_report():
    """Create a new custom report"""
    data = request.json
    
    if not data.get('name'):
        return jsonify({'success': False, 'error': 'Name is required'}), 400
        
    # Serialize configs to string if they are dicts
    if 'widgets' in data:
        for w in data['widgets']:
            if 'config' in w and isinstance(w['config'], dict):
                w['config'] = json.dumps(w['config'])
                
    # Inject created_by
    data['created_by'] = session.get('user_id')
    
    result = _get_db().create_custom_report(data)
    if result.get('success'):
        log_audit('create', 'report', 'custom_report', result.get('id'), data['name'])
    return jsonify(result)

@reports_bp.route('/api/reports/<int:report_id>', methods=['GET'])
@login_required
def get_report(report_id):
    """Get a specific custom report"""
    db = _get_db()
    report = db.get_custom_report(report_id)
    if not report:
        return jsonify({'error': 'Report not found'}), 404
        
    # Deserialize configs
    if 'widgets' in report:
        for w in report['widgets']:
            try:
                if w['config']:
                    w['config'] = json.loads(w['config'])
            except:
                w['config'] = {}
                
    return jsonify(report)

@reports_bp.route('/api/reports/<int:report_id>', methods=['PUT'])
@admin_required
def update_report(report_id):
    """Update a custom report"""
    data = request.json
    db = _get_db()
    
    report = db.get_custom_report(report_id)
    if not report:
        return jsonify({'error': 'Report not found'}), 404

    # Serialize configs back to string if they are dicts
    if 'widgets' in data:
        for w in data['widgets']:
            if 'config' in w and isinstance(w['config'], dict):
                w['config'] = json.dumps(w['config'])
                
    result = db.update_custom_report(report_id, data)
    if result.get('success'):
        log_audit('update', 'report', 'custom_report', report_id, data.get('name'))
    return jsonify(result)

@reports_bp.route('/api/reports/<int:report_id>', methods=['DELETE'])
@admin_required
def delete_report(report_id):
    """Delete a custom report"""
    result = _get_db().delete_custom_report(report_id)
    if result.get('success'):
        log_audit('delete', 'report', 'custom_report', report_id)
    return jsonify(result)
