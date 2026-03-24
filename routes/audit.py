"""
Audit Log API routes (Admin only)
"""
import csv
import io
import json
from flask import Blueprint, jsonify, request, session, current_app, Response
from .auth import login_required, admin_required

audit_bp = Blueprint('audit', __name__)


def _get_db():
    return current_app.config['DB']


def log_audit(action, category, target_type=None, target_id=None,
              target_name=None, details=None):
    """Helper to record an audit event from the current request context.
    Import and call this from any route:
        from .audit import log_audit
        log_audit('create', 'device', 'device', device_id, device_name)
    """
    try:
        db = current_app.config['DB']
        user_id = session.get('user_id')
        username = session.get('username', 'system')
        ip_address = request.remote_addr
        details_str = json.dumps(details, ensure_ascii=False) if isinstance(details, dict) else details
        db.add_audit_log(
            user_id=user_id,
            username=username,
            action=action,
            category=category,
            target_type=target_type,
            target_id=target_id,
            target_name=target_name,
            details=details_str,
            ip_address=ip_address
        )
    except Exception as e:
        print(f"[AUDIT] Failed to log: {e}")


@audit_bp.route('/api/audit-logs', methods=['GET'])
@admin_required
def get_audit_logs():
    """Get paginated audit logs with filtering"""
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    username = request.args.get('username')
    action = request.args.get('action')
    category = request.args.get('category')
    search = request.args.get('search')

    result = _get_db().get_audit_logs(
        limit=limit, offset=offset,
        username=username, action=action,
        category=category, search=search
    )
    return jsonify(result)


@audit_bp.route('/api/audit-logs/stats', methods=['GET'])
@admin_required
def get_audit_stats():
    """Get audit log statistics"""
    stats = _get_db().get_audit_stats()
    return jsonify(stats)


@audit_bp.route('/api/audit-logs/export/csv', methods=['GET'])
@admin_required
def export_audit_csv():
    """Export audit logs as CSV"""
    result = _get_db().get_audit_logs(limit=10000, offset=0)
    logs = result['logs']

    fieldnames = ['created_at', 'username', 'action', 'category',
                  'target_type', 'target_id', 'target_name', 'details', 'ip_address']

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    for log in logs:
        writer.writerow({k: log.get(k, '') for k in fieldnames})

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=audit_log_export.csv'}
    )
