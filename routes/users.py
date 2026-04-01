"""
User management API routes (Admin only)
"""
from flask import Blueprint, jsonify, request, session, current_app
from .auth import login_required, admin_required
from .audit import log_audit
import pyotp
import qrcode
import io

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
        email=data.get('email'),
        telegram_chat_id=data.get('telegram_chat_id'),
        auth_type=data.get('auth_type', 'local')
    )
    
    if result['success']:
        log_audit('create', 'user', 'user', result.get('id'), data['username'],
                  details={'role': data.get('role', 'viewer')})
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
        telegram_chat_id=data.get('telegram_chat_id'),
        is_active=data.get('is_active'),
        password=data.get('password'),
        auth_type=data.get('auth_type')
    )
    log_audit('update', 'user', 'user', user_id, details={'fields': list(data.keys())})
    return jsonify(result)


@users_bp.route('/api/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    """Delete a user"""
    result = _get_db().delete_user(user_id)
    log_audit('delete', 'user', 'user', user_id)
    return jsonify(result)


@users_bp.route('/api/users/me', methods=['GET'])
@login_required
def get_current_user():
    """Get current logged-in user info"""
    db = _get_db()
    user = db.get_user_by_id(session.get('user_id'))
    if user:
        # Don't return sensitive info
        user.pop('password_hash', None)
        user.pop('mfa_secret', None)
        return jsonify(user)
    return jsonify({'error': 'User not found'}), 404



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
    log_audit('update', 'user', 'user', user['id'], session.get('username'),
              details={'action': 'password_change'})
    return jsonify(result)


# ============================================================================
# MFA (Two-Factor Authentication) Routes
# ============================================================================

@users_bp.route('/api/users/me/mfa/setup', methods=['POST'])
@login_required
def mfa_setup():
    """Generate a new TOTP secret and return QR code provisioning URI"""
    user_id = session.get('user_id')
    username = session.get('username')
    
    db = _get_db()
    _, mfa_enabled = db.get_mfa_secret(user_id)
    if mfa_enabled:
        return jsonify({'success': False, 'error': 'MFA is already enabled. Disable it first.'}), 400
    
    # Generate a new secret
    secret = pyotp.random_base32()
    
    # Build provisioning URI for QR code
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name=username or 'user',
        issuer_name='Network Monitor'
    )
    
    # Store secret temporarily in session until verified
    session['mfa_setup_secret'] = secret
    
    return jsonify({
        'success': True,
        'secret': secret,
        'provisioning_uri': provisioning_uri
    })


@users_bp.route('/api/users/me/mfa/verify', methods=['POST'])
@login_required
def mfa_verify():
    """Verify TOTP code and activate MFA"""
    data = request.json
    totp_code = data.get('code', '').strip()
    
    if not totp_code:
        return jsonify({'success': False, 'error': 'Verification code is required'}), 400
    
    secret = session.get('mfa_setup_secret')
    if not secret:
        return jsonify({'success': False, 'error': 'No MFA setup in progress. Please start setup first.'}), 400
    
    # Verify the code
    totp = pyotp.TOTP(secret)
    if not totp.verify(totp_code, valid_window=1):
        return jsonify({'success': False, 'error': 'Invalid code. Please check your authenticator app and try again.'}), 400
    
    # Code verified — save secret and enable MFA
    user_id = session.get('user_id')
    db = _get_db()
    result = db.enable_mfa(user_id, secret)
    
    if result['success']:
        session.pop('mfa_setup_secret', None)
        log_audit('update', 'user', 'user', user_id, session.get('username'),
                  details={'action': 'mfa_enabled'})
    
    return jsonify(result)


@users_bp.route('/api/users/me/mfa/disable', methods=['POST'])
@login_required
def mfa_disable():
    """Disable MFA for current user (requires password confirmation)"""
    data = request.json
    password = data.get('password', '').strip()
    
    if not password:
        return jsonify({'success': False, 'error': 'Password confirmation required'}), 400
    
    user_id = session.get('user_id')
    db = _get_db()
    user = db.get_user_by_id(user_id)
    
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404
    
    from werkzeug.security import check_password_hash
    if not check_password_hash(user['password_hash'], password):
        return jsonify({'success': False, 'error': 'Password incorrect'}), 401
    
    return jsonify(result)


@users_bp.route('/api/users/me/activity', methods=['GET'])
@login_required
def get_my_activity():
    """Get recent activity for the current user"""
    limit = request.args.get('limit', 10, type=int)
    db = _get_db()
    username = session.get('username')
    
    # We'll use the existing DB method but filter by username
    result = db.get_audit_logs(limit=limit, username=username)
    return jsonify(result.get('logs', []))


@users_bp.route('/api/users/me/mfa/status', methods=['GET'])

@login_required
def mfa_status():
    """Get MFA status for current user"""
    user_id = session.get('user_id')
    db = _get_db()
    _, mfa_enabled = db.get_mfa_secret(user_id)
    return jsonify({'mfa_enabled': mfa_enabled})


@users_bp.route('/api/users/<int:user_id>/mfa/reset', methods=['POST'])
@admin_required
def mfa_admin_reset(user_id):
    """Admin: Reset MFA for another user"""
    db = _get_db()
    user = db.get_user_by_id(user_id)
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404
    
    result = db.disable_mfa(user_id)
    if result['success']:
        log_audit('update', 'user', 'user', user_id, user.get('username'),
                  details={'action': 'mfa_reset_by_admin'})
    
    return jsonify(result)


@users_bp.route('/api/users/me/mfa/qrcode', methods=['GET'])
@login_required
def mfa_qrcode():
    """Generate QR code image for MFA setup"""
    from flask import send_file
    
    secret = session.get('mfa_setup_secret')
    if not secret:
        return jsonify({'error': 'No MFA setup in progress'}), 400
    
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(
        name=session.get('username', 'user'),
        issuer_name='Network Monitor'
    )
    
    # Generate QR code image
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    
    return send_file(buf, mimetype='image/png', download_name='mfa_qrcode.png')
