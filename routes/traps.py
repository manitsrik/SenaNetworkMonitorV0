"""
SNMP Traps API Routes
"""
from flask import Blueprint, jsonify, request, current_app

traps_bp = Blueprint('traps', __name__)

def _get_db():
    return current_app.config['DB']


@traps_bp.route('/api/traps')
def get_traps():
    """Get traps with optional filters and pagination"""
    db = _get_db()
    limit = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))
    severity = request.args.get('severity')
    source_ip = request.args.get('source_ip')
    ack = request.args.get('acknowledged')
    acknowledged = None
    if ack is not None:
        acknowledged = ack.lower() in ('1', 'true', 'yes')
    
    result = db.get_traps(limit=limit, offset=offset, severity=severity,
                          source_ip=source_ip, acknowledged=acknowledged)
    return jsonify(result)


@traps_bp.route('/api/traps/stats')
def get_trap_stats():
    """Get trap statistics"""
    db = _get_db()
    stats = db.get_trap_stats()
    return jsonify(stats)


@traps_bp.route('/api/traps/<int:trap_id>/ack', methods=['POST'])
def acknowledge_trap(trap_id):
    """Acknowledge a trap"""
    db = _get_db()
    result = db.acknowledge_trap(trap_id)
    return jsonify(result)


@traps_bp.route('/api/traps/ack-all', methods=['POST'])
def acknowledge_all():
    """Acknowledge all unacknowledged traps"""
    db = _get_db()
    result = db.acknowledge_all_traps()
    return jsonify(result)


@traps_bp.route('/api/traps/<int:trap_id>', methods=['DELETE'])
def delete_trap(trap_id):
    """Delete a trap"""
    db = _get_db()
    result = db.delete_trap(trap_id)
    return jsonify(result)
