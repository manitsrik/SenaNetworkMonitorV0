"""
Syslog API Routes
"""
from flask import Blueprint, jsonify, request, current_app

syslog_bp = Blueprint('syslog', __name__)

def _get_db():
    return current_app.config['DB']


@syslog_bp.route('/api/syslog')
def get_syslogs():
    """Get syslog messages with optional filters and pagination"""
    db = _get_db()
    limit = int(request.args.get('limit', 100))
    offset = int(request.args.get('offset', 0))
    severity = request.args.get('severity')
    source_ip = request.args.get('source_ip')
    search = request.args.get('search')
    
    result = db.get_syslogs(limit=limit, offset=offset, severity=severity,
                            source_ip=source_ip, search=search)
    return jsonify(result)


@syslog_bp.route('/api/syslog/stats')
def get_syslog_stats():
    """Get syslog statistics"""
    db = _get_db()
    stats = db.get_syslog_stats()
    return jsonify(stats)
