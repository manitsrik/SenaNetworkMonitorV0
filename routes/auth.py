"""
Authentication and RBAC routes
"""
from flask import Blueprint, session, redirect, url_for, render_template, request, jsonify
from functools import wraps

auth_bp = Blueprint('auth', __name__)


def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorator to require admin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('auth.login'))
        if session.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function


def operator_required(f):
    """Decorator to require operator or admin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('auth.login'))
        if session.get('role') not in ['admin', 'operator']:
            return jsonify({'error': 'Operator access required'}), 403
        return f(*args, **kwargs)
    return decorated_function


def _get_db():
    from flask import current_app
    return current_app.config['DB']


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if not username or not password:
            return redirect(url_for('auth.login', error='required'))
        
        db = _get_db()
        user = db.authenticate_user(username, password)
        if user:
            # Check if MFA is enabled for this user
            mfa_secret, mfa_enabled = db.get_mfa_secret(user['id'])
            if mfa_enabled and mfa_secret:
                # Store pending MFA data in session (NOT logged in yet)
                session['mfa_pending'] = True
                session['mfa_user_id'] = user['id']
                session['mfa_username'] = username
                session['mfa_role'] = user['role']
                session['mfa_display_name'] = user.get('display_name') or username
                return redirect(url_for('auth.login_mfa'))
            
            # No MFA — complete login directly
            session['logged_in'] = True
            session['username'] = username
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['display_name'] = user.get('display_name') or username
            # Audit: successful login
            from .audit import log_audit
            log_audit('login', 'auth', details={'role': user['role']})
            return redirect(url_for('pages.index'))
        else:
            # Audit: failed login attempt
            try:
                from flask import current_app
                db2 = current_app.config['DB']
                db2.add_audit_log(
                    user_id=None, username=username,
                    action='failed_login', category='auth',
                    ip_address=request.remote_addr
                )
            except Exception:
                pass
            return redirect(url_for('auth.login', error='invalid'))
    
    if 'logged_in' in session:
        return redirect(url_for('pages.index'))
    
    return render_template('login.html')


@auth_bp.route('/login/mfa', methods=['GET', 'POST'])
def login_mfa():
    """MFA verification page — enter TOTP code after password authentication"""
    # Must have pending MFA
    if not session.get('mfa_pending'):
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        totp_code = request.form.get('totp_code', '').strip()
        user_id = session.get('mfa_user_id')
        
        if not totp_code or not user_id:
            return render_template('login_mfa.html', error='Please enter your verification code')
        
        db = _get_db()
        mfa_secret, mfa_enabled = db.get_mfa_secret(user_id)
        
        if mfa_secret and mfa_enabled:
            import pyotp
            totp = pyotp.TOTP(mfa_secret)
            # valid_window=1 allows 1 step before/after (30 sec tolerance)
            if totp.verify(totp_code, valid_window=1):
                # MFA verified — complete login
                username = session.get('mfa_username')
                role = session.get('mfa_role')
                display_name = session.get('mfa_display_name')
                
                # Clear MFA pending data
                session.pop('mfa_pending', None)
                session.pop('mfa_user_id', None)
                session.pop('mfa_username', None)
                session.pop('mfa_role', None)
                session.pop('mfa_display_name', None)
                
                # Set real session
                session['logged_in'] = True
                session['username'] = username
                session['user_id'] = user_id
                session['role'] = role
                session['display_name'] = display_name
                
                db.update_last_login(user_id)
                
                from .audit import log_audit
                log_audit('login', 'auth', details={'role': role, 'mfa': True})
                return redirect(url_for('pages.index'))
            else:
                # Audit: failed MFA
                try:
                    db.add_audit_log(
                        user_id=user_id,
                        username=session.get('mfa_username', ''),
                        action='failed_mfa',
                        category='auth',
                        ip_address=request.remote_addr
                    )
                except Exception:
                    pass
                return render_template('login_mfa.html', error='Invalid verification code. Please try again.')
        
        # Fallback: MFA config issue
        session.clear()
        return redirect(url_for('auth.login', error='mfa_error'))
    
    return render_template('login_mfa.html')


@auth_bp.route('/logout')
def logout():
    """Logout"""
    # Audit: logout
    if 'logged_in' in session:
        try:
            from .audit import log_audit
            log_audit('logout', 'auth')
        except Exception:
            pass
    session.clear()
    return redirect(url_for('auth.login'))
