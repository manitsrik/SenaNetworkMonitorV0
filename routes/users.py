"""
User management API routes (Admin only)
"""
from flask import Blueprint, jsonify, request, session, current_app
from .auth import login_required, admin_required

users_bp = Blueprint('users', __name__)


def _get_db():
    return current_app.config['DB']


@users_bp.route('/api/users', methods=['GET'])
@admin_required
def get_users():
    """Get all users"""
    users = _get_db().get_all_users()
    return jsonify(users)


@users_bp.route('/api/users', methods=['POST'])
@admin_required
def create_user():
    """Create a new user"""
    data = request.json
    
    if not data.get('username') or not data.get('password'):
        return jsonify({'success': False, 'error': 'Username and password required'}), 400
    
    result = _get_db().add_user(
        username=data['username'],
        password=data['password'],
        role=data.get('role', 'viewer'),
        display_name=data.get('display_name'),
        email=data.get('email')
    )
    
    if result['success']:
        return jsonify(result), 201
    return jsonify(result), 400


@users_bp.route('/api/users/<int:user_id>', methods=['PUT'])
@admin_required
def update_user(user_id):
    """Update a user"""
    data = request.json
    result = _get_db().update_user(
        user_id,
        role=data.get('role'),
        display_name=data.get('display_name'),
        email=data.get('email'),
        is_active=data.get('is_active'),
        password=data.get('password')
    )
    return jsonify(result)


@users_bp.route('/api/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    """Delete a user"""
    result = _get_db().delete_user(user_id)
    return jsonify(result)


@users_bp.route('/api/users/me', methods=['GET'])
@login_required
def get_current_user():
    """Get current logged-in user info"""
    return jsonify({
        'id': session.get('user_id'),
        'username': session.get('username'),
        'role': session.get('role'),
        'display_name': session.get('display_name')
    })


@users_bp.route('/api/users/me/password', methods=['PUT'])
@login_required
def change_my_password():
    """Change current user's password"""
    data = request.json
    
    if not data.get('current_password') or not data.get('new_password'):
        return jsonify({'success': False, 'error': 'Current and new password required'}), 400
    
    db = _get_db()
    user = db.get_user_by_id(session.get('user_id'))
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404
    
    from werkzeug.security import check_password_hash
    if not check_password_hash(user['password_hash'], data['current_password']):
        return jsonify({'success': False, 'error': 'Current password incorrect'}), 401
    
    result = db.update_user(user['id'], password=data['new_password'])
    return jsonify(result)
