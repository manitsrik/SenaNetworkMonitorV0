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
            session['logged_in'] = True
            session['username'] = username
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['display_name'] = user.get('display_name') or username
            return redirect(url_for('pages.index'))
        else:
            return redirect(url_for('auth.login', error='invalid'))
    
    if 'logged_in' in session:
        return redirect(url_for('pages.index'))
    
    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    """Logout"""
    session.clear()
    return redirect(url_for('auth.login'))
