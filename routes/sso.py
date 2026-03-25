"""
SSO (OAuth2/OIDC) authentication routes
Supports Google, Microsoft Entra ID, GitHub, Okta, Keycloak, etc.
"""
from flask import Blueprint, session, redirect, url_for, request, jsonify, current_app
from .auth import admin_required
from .audit import log_audit

sso_bp = Blueprint('sso', __name__)


def _get_db():
    return current_app.config['DB']


def _get_oauth_client():
    """Build an Authlib OAuth client from stored SSO settings"""
    from authlib.integrations.flask_client import OAuth

    db = _get_db()
    settings = db.get_sso_settings()

    if settings.get('sso_enabled', 'false').lower() != 'true':
        return None, settings

    oauth = OAuth(current_app)

    client_kwargs = {'scope': settings.get('sso_scopes', 'openid email profile')}

    # Build server metadata for OIDC autodiscovery or manual URLs
    server_metadata = {}
    if settings.get('sso_discovery_url'):
        server_metadata['server_metadata_url'] = settings['sso_discovery_url']

    oauth.register(
        name='sso',
        client_id=settings.get('sso_client_id', ''),
        client_secret=settings.get('sso_client_secret', ''),
        authorize_url=settings.get('sso_authorize_url', ''),
        access_token_url=settings.get('sso_token_url', ''),
        userinfo_endpoint=settings.get('sso_userinfo_url', ''),
        client_kwargs=client_kwargs,
        **server_metadata
    )

    return oauth, settings


# =========================================================================
# SSO Login Flow
# =========================================================================

@sso_bp.route('/sso/login')
def sso_login():
    """Redirect user to OAuth2 provider for authentication"""
    try:
        oauth, settings = _get_oauth_client()
        if oauth is None:
            return redirect(url_for('auth.login', error='sso_disabled'))

        callback_url = url_for('sso.sso_callback', _external=True)
        return oauth.sso.authorize_redirect(callback_url)
    except Exception as e:
        print(f"[SSO] Login redirect error: {e}")
        return redirect(url_for('auth.login', error='sso_error'))


@sso_bp.route('/sso/callback')
def sso_callback():
    """Handle OAuth2 callback from provider"""
    try:
        oauth, settings = _get_oauth_client()
        if oauth is None:
            return redirect(url_for('auth.login', error='sso_disabled'))

        # Exchange authorization code for token
        token = oauth.sso.authorize_access_token()

        # Get user info
        userinfo = None

        # Try OIDC id_token first
        if 'userinfo' in token:
            userinfo = token['userinfo']
        else:
            # Fetch from userinfo endpoint
            try:
                resp = oauth.sso.get(settings.get('sso_userinfo_url', ''))
                userinfo = resp.json()
            except Exception:
                pass

        if not userinfo:
            # Try parsing id_token
            try:
                userinfo = oauth.sso.parse_id_token(token)
            except Exception:
                pass

        if not userinfo:
            return redirect(url_for('auth.login', error='sso_no_userinfo'))

        # Extract user fields (handle different provider formats)
        email = (userinfo.get('email') or
                 userinfo.get('mail') or
                 userinfo.get('preferred_username') or
                 userinfo.get('login'))

        display_name = (userinfo.get('name') or
                        userinfo.get('displayName') or
                        userinfo.get('given_name', '') + ' ' + userinfo.get('family_name', '') or
                        email)

        if not email:
            return redirect(url_for('auth.login', error='sso_no_email'))

        # Derive username from email (before @)
        username = email.split('@')[0] if '@' in email else email
        provider_name = settings.get('sso_provider_name', 'SSO')

        db = _get_db()

        # Find existing user by username or email
        user = db.get_user_by_username(username)

        if user:
            # Existing user — check if active
            if not user.get('is_active', True):
                return redirect(url_for('auth.login', error='sso_inactive'))

            # Update display name if needed
            if display_name and display_name.strip():
                db.update_user(user['id'], display_name=display_name.strip(), email=email)
        else:
            # Auto-create user if enabled
            auto_create = settings.get('sso_auto_create', 'true').lower() == 'true'
            if not auto_create:
                return redirect(url_for('auth.login', error='sso_no_account'))

            default_role = settings.get('sso_default_role', 'viewer')
            result = db.add_user(
                username=username,
                password='SSO_EXTERNAL_AUTH',
                role=default_role,
                display_name=display_name.strip() if display_name else username,
                email=email,
                auth_type='sso'
            )

            if not result.get('success'):
                # Username might conflict, try with email as username
                result = db.add_user(
                    username=email,
                    password='SSO_EXTERNAL_AUTH',
                    role=default_role,
                    display_name=display_name.strip() if display_name else email,
                    email=email,
                    auth_type='sso'
                )

            if not result.get('success'):
                print(f"[SSO] Failed to create user: {result.get('error')}")
                return redirect(url_for('auth.login', error='sso_create_failed'))

            user = db.get_user_by_username(username) or db.get_user_by_username(email)
            if user:
                db.update_user(user['id'], auth_type='sso')

        if not user:
            return redirect(url_for('auth.login', error='sso_error'))

        # Set session (same as normal login)
        session['logged_in'] = True
        session['username'] = user['username']
        session['user_id'] = user['id']
        session['role'] = user['role']
        session['display_name'] = user.get('display_name') or user['username']
        session['auth_type'] = 'sso'

        db.update_last_login(user['id'])

        # Audit log
        log_audit('sso_login', 'auth', details={
            'provider': provider_name,
            'email': email,
            'role': user['role']
        })

        return redirect(url_for('pages.index'))

    except Exception as e:
        print(f"[SSO] Callback error: {e}")
        import traceback
        traceback.print_exc()
        return redirect(url_for('auth.login', error='sso_error'))


# =========================================================================
# SSO Settings API (Admin only)
# =========================================================================

@sso_bp.route('/api/sso/settings', methods=['GET'])
@admin_required
def get_sso_settings():
    """Get all SSO settings"""
    settings = _get_db().get_sso_settings()
    # Mask client secret for security
    if settings.get('sso_client_secret'):
        secret = settings['sso_client_secret']
        if len(secret) > 8:
            settings['sso_client_secret'] = secret[:4] + '••••' + secret[-4:]
    return jsonify(settings)


@sso_bp.route('/api/sso/settings', methods=['POST'])
@admin_required
def save_sso_settings():
    """Save SSO settings"""
    data = request.json
    db = _get_db()

    for key, value in data.items():
        # Only save sso_ prefixed keys
        if key.startswith('sso_'):
            db.save_sso_setting(key, value)

    log_audit('update', 'settings', 'sso', details={'keys': list(data.keys())})
    return jsonify({'success': True})


@sso_bp.route('/api/sso/enabled', methods=['GET'])
def is_sso_enabled():
    """Public endpoint to check if SSO is enabled (for login page)"""
    settings = _get_db().get_sso_settings()
    return jsonify({
        'enabled': settings.get('sso_enabled', 'false').lower() == 'true',
        'provider_name': settings.get('sso_provider_name', 'SSO')
    })
