from flask import Blueprint, request, jsonify, current_app
from .auth import login_required, admin_required

assignments_bp = Blueprint('assignments', __name__, url_prefix='/api/assignments')

@assignments_bp.route('/device/<int:device_id>', methods=['GET'])
@login_required
def get_device_assignments(device_id):
    """Get users assigned to a specific device"""
    db = current_app.config['DB']
    assignments = db.get_device_assignments(device_id)
    return jsonify(assignments)

@assignments_bp.route('/user/<int:user_id>', methods=['GET'])
@login_required
def get_user_assignments(user_id):
    """Get devices assigned to a specific user"""
    db = current_app.config['DB']
    assignments = db.get_user_assignments(user_id)
    return jsonify(assignments)

@assignments_bp.route('/assign', methods=['POST'])
@admin_required
def assign_user():
    """Assign a user to a device"""
    db = current_app.config['DB']
    data = request.get_json()
    user_id = data.get('user_id')
    device_id = data.get('device_id')
    
    if not user_id or not device_id:
        return jsonify({'success': False, 'error': 'user_id and device_id are required'}), 400
        
    result = db.assign_user_to_device(user_id, device_id)
    return jsonify(result)

@assignments_bp.route('/unassign', methods=['POST'])
@admin_required
def unassign_user():
    """Remove a user assignment from a device"""
    db = current_app.config['DB']
    data = request.get_json()
    user_id = data.get('user_id')
    device_id = data.get('device_id')
    
    if not user_id or not device_id:
        return jsonify({'success': False, 'error': 'user_id and device_id are required'}), 400
        
    result = db.unassign_user_from_device(user_id, device_id)
    return jsonify(result)
