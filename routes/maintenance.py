"""
Maintenance windows API routes
"""
from flask import Blueprint, jsonify, request, current_app
from .auth import operator_required

maintenance_bp = Blueprint('maintenance', __name__)


def _get_db():
    return current_app.config['DB']


@maintenance_bp.route('/api/maintenance', methods=['GET'])
def get_maintenance_windows():
    """Get all maintenance windows"""
    windows = _get_db().get_all_maintenance_windows()
    return jsonify(windows)


@maintenance_bp.route('/api/maintenance', methods=['POST'])
@operator_required
def add_maintenance_window():
    """Add a new maintenance window"""
    data = request.json
    
    if not data.get('name') or not data.get('start_time') or not data.get('end_time'):
        return jsonify({'success': False, 'error': 'Name, start_time, and end_time are required'}), 400
    
    result = _get_db().add_maintenance_window(
        name=data['name'],
        start_time=data['start_time'],
        end_time=data['end_time'],
        device_id=data.get('device_id'),
        recurring=data.get('recurring'),
        description=data.get('description')
    )
    
    if result['success']:
        return jsonify(result), 201
    return jsonify(result), 400


@maintenance_bp.route('/api/maintenance/<int:window_id>', methods=['DELETE'])
@operator_required
def delete_maintenance_window(window_id):
    """Delete a maintenance window"""
    result = _get_db().delete_maintenance_window(window_id)
    return jsonify(result)


@maintenance_bp.route('/api/maintenance/active', methods=['GET'])
def get_active_maintenance():
    """Get currently active maintenance windows"""
    device_id = request.args.get('device_id', type=int)
    windows = _get_db().get_active_maintenance(device_id)
    return jsonify(windows)
