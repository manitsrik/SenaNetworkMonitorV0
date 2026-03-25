"""
LDAP/AD configuration API routes (Admin only)
"""
from flask import Blueprint, jsonify, request, current_app
from .auth import admin_required
from .audit import log_audit

ldap_bp = Blueprint('ldap', __name__)

def _get_db():
    return current_app.config['DB']

@ldap_bp.route('/api/ldap/settings', methods=['GET'])
@admin_required
def get_ldap_settings():
    """Get all LDAP settings"""
    settings = _get_db().get_ldap_settings()
    return jsonify(settings)

@ldap_bp.route('/api/ldap/settings', methods=['POST'])
@admin_required
def save_ldap_settings():
    """Save LDAP settings"""
    data = request.json
    db = _get_db()
    
    for key, value in data.items():
        db.save_ldap_setting(key, value)
        
    log_audit('update', 'settings', 'ldap', details={'keys': list(data.keys())})
    return jsonify({'success': True})

@ldap_bp.route('/api/ldap/test', methods=['POST'])
@admin_required
def test_ldap_connection():
    """Test LDAP connection with provided settings"""
    data = request.json
    username = data.get('test_username')
    password = data.get('test_password')
    
    if not username or not password:
        return jsonify({'success': False, 'error': 'Test username and password required'}), 400
        
    db = _get_db()
    
    # Temporarily override settings for testing
    import ldap3
    from ldap3 import Server, Connection, ALL, Tls
    import ssl
    
    try:
        server_url = data.get('ldap_server')
        port = int(data.get('ldap_port', 389))
        use_ssl = data.get('ldap_use_ssl', 'false').lower() == 'true'
        
        if not server_url:
            return jsonify({'success': False, 'error': 'LDAP server URL required'}), 400
            
        tls = None
        if use_ssl:
            tls = Tls(validate=ssl.CERT_NONE, version=ssl.PROTOCOL_TLSv1_2)
            
        server = Server(server_url, port=port, use_ssl=use_ssl, tls=tls, get_info=ALL)
        
        # 1. Test Bind (Admin or Anonymous)
        bind_dn = data.get('ldap_bind_dn')
        bind_pw = data.get('ldap_bind_password')
        
        if bind_dn and bind_pw:
            conn = Connection(server, user=bind_dn, password=bind_pw, auto_bind=True)
        else:
            conn = Connection(server, auto_bind=True)
            
        # 2. Test Search
        base_dn = data.get('ldap_base_dn', '')
        user_filter = data.get('ldap_user_filter', '(sAMAccountName={username})').replace('{username}', username)
        
        conn.search(base_dn, user_filter, attributes=['displayName', 'mail'])
        
        if not conn.entries:
            conn.unbind()
            return jsonify({'success': False, 'error': f'User "{username}" not found with provided filter'})
            
        target_dn = conn.entries[0].entry_dn
        display_name = str(conn.entries[0].displayName) if hasattr(conn.entries[0], 'displayName') else username
        conn.unbind()
        
        # 3. Test User Auth
        user_conn = Connection(server, user=target_dn, password=password)
        if user_conn.bind():
            user_conn.unbind()
            return jsonify({
                'success': True, 
                'message': f'Successfully authenticated as {display_name} ({target_dn})'
            })
        else:
            return jsonify({'success': False, 'error': 'Invalid credentials for test user'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
