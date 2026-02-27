from flask import Flask, render_template, jsonify, request, session, redirect, url_for, Response
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import csv
import io
from apscheduler.schedulers.background import BackgroundScheduler
from database import Database
from monitor import NetworkMonitor
from alerter import Alerter
from telegram_bot import TelegramBot
from scheduler_reports import ReportGenerator
from config import Config
from functools import wraps
import atexit
import os
import json

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = Config.SECRET_KEY
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
CORS(app)

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins=Config.SOCKETIO_CORS_ALLOWED_ORIGINS,
                   async_mode=Config.SOCKETIO_ASYNC_MODE)

# Initialize Database, Monitor, Alerter, TelegramBot, and ReportGenerator
db = Database()
monitor = NetworkMonitor(db)
alerter = Alerter(db)
telegram_bot = TelegramBot(db)
report_generator = ReportGenerator(db)
monitor.alerter = alerter  # Connect alerter to monitor

# Background scheduler for monitoring
scheduler = BackgroundScheduler()

def monitor_devices():
    """Background task to monitor all devices"""
    print("Running scheduled device check...")
    results = monitor.check_all_devices()
    
    # Emit status updates via WebSocket
    for result in results:
        socketio.emit('status_update', result, namespace='/')
    
    # Emit statistics update
    stats = monitor.get_statistics()
    socketio.emit('statistics_update', stats, namespace='/')

def scheduled_daily_report():
    """Background task to send daily status report"""
    print("Running scheduled daily report...")
    report_generator.run_daily_report()

# Schedule monitoring task
scheduler.add_job(func=monitor_devices, trigger="interval", 
                 seconds=Config.PING_INTERVAL, id='monitor_job')

# Schedule daily report - default at 8:00 AM
# Note: Time can be configured in settings, but scheduler needs restart to apply
scheduler.add_job(func=scheduled_daily_report, trigger="cron", 
                 hour=8, minute=0, id='daily_report_job')

scheduler.start()

# Start Telegram bot polling
telegram_bot.start_polling()

# Shutdown scheduler and telegram bot when app exits
atexit.register(lambda: scheduler.shutdown())
atexit.register(lambda: telegram_bot.stop_polling())



# ============================================================================
# Authentication and RBAC
# ============================================================================

def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to require admin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

def operator_required(f):
    """Decorator to require operator or admin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        if session.get('role') not in ['admin', 'operator']:
            return jsonify({'error': 'Operator access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

# ============================================================================
# Web Routes
# ============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if not username or not password:
            return redirect(url_for('login', error='required'))
        
        user = db.authenticate_user(username, password)
        if user:
            session['logged_in'] = True
            session['username'] = username
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['display_name'] = user.get('display_name') or username
            return redirect(url_for('index'))
        else:
            return redirect(url_for('login', error='invalid'))
    
    # If already logged in, redirect to dashboard
    if 'logged_in' in session:
        return redirect(url_for('index'))
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout"""
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    """Dashboard page"""
    # Fetch Main Status dashboard (ID 1)
    # If it doesn't exist, it will be None and index.html handles it
    main_dashboard = db.get_dashboard(1)
    return render_template('index.html', dashboard=main_dashboard)

@app.route('/topology')
@login_required
def topology():
    """Topology page"""
    return render_template('topology.html')

@app.route('/devices')
@login_required
def devices():
    """Device management page"""
    return render_template('devices.html')

@app.route('/history')
@login_required
def history():
    """Historical data page"""
    return render_template('history.html')

@app.route('/settings')
@login_required
def settings():
    """Alert settings page"""
    return render_template('settings.html')

@app.route('/users')
@admin_required
def users():
    """User management page (admin only)"""
    return render_template('users.html')


# ============================================================================
# API Routes
# ============================================================================

@app.route('/api/devices', methods=['GET'])
def get_devices():
    """Get all devices"""
    devices = db.get_all_devices()
    return jsonify(devices)

@app.route('/api/devices', methods=['POST'])
@operator_required
def add_device():
    """Add a new device"""
    data = request.json
    
    if not data.get('name') or not data.get('ip_address'):
        return jsonify({'success': False, 'error': 'Name and IP/URL are required'}), 400
    
    result = db.add_device(
        name=data['name'],
        ip_address=data['ip_address'],
        device_type=data.get('device_type'),
        location=data.get('location'),
        monitor_type=data.get('monitor_type', 'ping'),
        expected_status_code=data.get('expected_status_code', 200),
        snmp_community=data.get('snmp_community', 'public'),
        snmp_port=data.get('snmp_port', 161),
        snmp_version=data.get('snmp_version', '2c'),
        tcp_port=data.get('tcp_port', 80),
        dns_query_domain=data.get('dns_query_domain', 'google.com'),
        location_type=data.get('location_type', 'on-premise')
    )
    
    if result['success']:
        # Immediately check the new device
        device = db.get_device(result['id'])
        status = monitor.check_device(device)
        socketio.emit('status_update', status, namespace='/')
        return jsonify(result), 201
    else:
        return jsonify(result), 400

@app.route('/api/devices/<int:device_id>', methods=['PUT'])
@operator_required
def update_device(device_id):
    """Update a device"""
    data = request.json
    result = db.update_device(
        device_id=device_id,
        name=data.get('name'),
        ip_address=data.get('ip_address'),
        device_type=data.get('device_type'),
        location=data.get('location'),
        monitor_type=data.get('monitor_type'),
        snmp_community=data.get('snmp_community'),
        snmp_port=data.get('snmp_port'),
        snmp_version=data.get('snmp_version'),
        tcp_port=data.get('tcp_port'),
        dns_query_domain=data.get('dns_query_domain'),
        location_type=data.get('location_type')
    )
    return jsonify(result)

@app.route('/api/devices/<int:device_id>', methods=['DELETE'])
@operator_required
def delete_device(device_id):
    """Delete a device"""
    result = db.delete_device(device_id)
    socketio.emit('device_deleted', {'id': device_id}, namespace='/')
    return jsonify(result)

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get current status of all devices"""
    devices = db.get_all_devices()
    return jsonify(devices)

@app.route('/api/statistics', methods=['GET'])
def get_statistics():
    """Get network statistics"""
    stats = monitor.get_statistics()
    return jsonify(stats)

@app.route('/api/snmp/<int:device_id>/interfaces', methods=['GET'])
def get_snmp_interfaces(device_id):
    """Get SNMP interface table for a device"""
    device = db.get_device(device_id)
    if not device:
        return jsonify({'error': 'Device not found'}), 404
    
    if device.get('monitor_type') != 'snmp':
        return jsonify({'error': 'Device is not SNMP monitored'}), 400
    
    community = device.get('snmp_community', 'public')
    port = device.get('snmp_port', 161)
    version = device.get('snmp_version', '2c')
    
    interfaces = monitor.get_snmp_interfaces(
        device['ip_address'], 
        community, 
        port, 
        version
    )
    
    return jsonify({
        'device_id': device_id,
        'device_name': device['name'],
        'interfaces': interfaces
    })

@app.route('/api/topology', methods=['GET'])
def get_topology():
    """Get topology configuration"""
    devices = db.get_all_devices()
    connections = db.get_topology()
    
    return jsonify({
        'devices': devices,
        'connections': connections
    })

@app.route('/api/topology/connection', methods=['POST'])
@operator_required
def add_topology_connection():
    """Add a topology connection"""
    data = request.json
    
    if not data.get('device_id') or not data.get('connected_to'):
        return jsonify({'success': False, 'error': 'device_id and connected_to are required'}), 400
    
    result = db.add_topology_connection(
        device_id=data['device_id'],
        connected_to=data['connected_to'],
        view_type=data.get('view_type', 'standard')
    )
    
    if result['success']:
        # Broadcast topology update
        socketio.emit('topology_updated', {
            'action': 'add',
            'connection': {
                'id': result['id'],
                'device_id': data['device_id'],
                'connected_to': data['connected_to'],
                'view_type': data.get('view_type', 'standard')
            }
        }, namespace='/')
        return jsonify(result), 201
    else:
        return jsonify(result), 400

@app.route('/api/topology/connection/<int:connection_id>', methods=['DELETE'])
@operator_required
def delete_topology_connection(connection_id):
    """Delete a topology connection"""
    result = db.delete_topology_connection(connection_id=connection_id)
    
    if result['success']:
        # Broadcast topology update
        socketio.emit('topology_updated', {
            'action': 'delete',
            'connection_id': connection_id
        }, namespace='/')
    
    return jsonify(result)

@app.route('/api/devices/<int:device_id>/history', methods=['GET'])
def get_device_history(device_id):
    """Get status history for a device"""
    limit = request.args.get('limit', 100, type=int)
    history = db.get_device_history(device_id, limit)
    return jsonify(history)

@app.route('/api/history', methods=['GET'])
def get_historical_data():
    """Get historical data with optional filters"""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    device_id = request.args.get('device_id', type=int)
    device_ids = request.args.get('device_ids')  # comma-separated: "1,2,3"
    device_type = request.args.get('device_type')
    
    # Support multiple device_ids
    if device_ids:
        device_id_list = [int(x.strip()) for x in device_ids.split(',') if x.strip().isdigit()]
        history = db.get_historical_data_multi(start_date, end_date, device_id_list)
    else:
        history = db.get_historical_data(start_date, end_date, device_id, device_type)
    return jsonify(history)

@app.route('/api/history/stats', methods=['GET'])
def get_historical_stats():
    """Get aggregated statistics for a time period"""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    stats = db.get_aggregated_stats(start_date, end_date)
    return jsonify(stats)

@app.route('/api/statistics/trend', methods=['GET'])
def get_trend_statistics():
    """Get response time trends by device type"""
    # Default to 3 hours (180 minutes)
    minutes = request.args.get('minutes', 180, type=int)
    trends = db.get_device_type_trends(minutes)
    return jsonify(trends)

@app.route('/api/check/<int:device_id>', methods=['POST'])
@operator_required
def check_device_now(device_id):
    """Immediately check a specific device"""
    device = db.get_device(device_id)
    if not device:
        return jsonify({'success': False, 'error': 'Device not found'}), 404
    
    result = monitor.check_device(device)
    socketio.emit('status_update', result, namespace='/')
    return jsonify(result)

# ============================================================================
# CSV Import/Export API Routes
# ============================================================================

@app.route('/api/devices/export/csv', methods=['GET'])
def export_devices_csv():
    """Export all devices as CSV"""
    devices = db.get_all_devices()
    
    # Define CSV columns
    fieldnames = [
        'name', 'ip_address', 'device_type', 'location', 'location_type',
        'monitor_type', 'snmp_community', 'snmp_port', 'snmp_version',
        'tcp_port', 'dns_query_domain', 'expected_status_code'
    ]
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    
    for device in devices:
        row = {k: device.get(k, '') for k in fieldnames}
        writer.writerow(row)
    
    # Return as downloadable file
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=devices_export.csv'}
    )

@app.route('/api/devices/import/csv', methods=['POST'])
@operator_required
def import_devices_csv():
    """Import devices from CSV file"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400
    
    if not file.filename.lower().endswith('.csv'):
        return jsonify({'success': False, 'error': 'File must be a CSV'}), 400
    
    try:
        # Read CSV content
        content = file.stream.read().decode('utf-8')
        reader = csv.DictReader(io.StringIO(content))
        
        results = {
            'success': True,
            'imported': 0,
            'failed': 0,
            'errors': []
        }
        
        for i, row in enumerate(reader, start=2):  # Start at 2 (1 is header)
            name = row.get('name', '').strip()
            ip_address = row.get('ip_address', '').strip()
            
            # Validate required fields
            if not name or not ip_address:
                results['failed'] += 1
                results['errors'].append(f"Row {i}: Name and IP address are required")
                continue
            
            # Add device
            result = db.add_device(
                name=name,
                ip_address=ip_address,
                device_type=row.get('device_type', '').strip() or 'server',
                location=row.get('location', '').strip() or None,
                location_type=row.get('location_type', '').strip() or 'on-premise',
                monitor_type=row.get('monitor_type', '').strip() or 'ping',
                snmp_community=row.get('snmp_community', '').strip() or 'public',
                snmp_port=int(row.get('snmp_port') or 161),
                snmp_version=row.get('snmp_version', '').strip() or '2c',
                tcp_port=int(row.get('tcp_port') or 80),
                dns_query_domain=row.get('dns_query_domain', '').strip() or 'google.com',
                expected_status_code=int(row.get('expected_status_code') or 200)
            )
            
            if result['success']:
                results['imported'] += 1
            else:
                results['failed'] += 1
                results['errors'].append(f"Row {i}: {result.get('error', 'Unknown error')}")
        
        return jsonify(results)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================================
# Alert API Routes
# ============================================================================

@app.route('/api/alert-settings', methods=['GET'])
def get_alert_settings():
    """Get all alert settings"""
    settings = db.get_all_alert_settings()
    # Convert to dict format
    settings_dict = {s['setting_key']: s['setting_value'] for s in settings}
    return jsonify(settings_dict)

@app.route('/api/alert-settings', methods=['POST'])
@operator_required
def save_alert_settings():
    """Save alert settings"""
    data = request.json
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    for key, value in data.items():
        db.save_alert_setting(key, str(value))
    
    # Clear alerter cache to pick up new settings
    alerter._cache_time = None
    
    return jsonify({'success': True})

@app.route('/api/alert-test/<channel>', methods=['POST'])
@operator_required
def test_alert(channel):
    """Send a test alert to verify configuration"""
    if channel not in ['email', 'line', 'telegram']:
        return jsonify({'success': False, 'error': 'Unknown channel'}), 400
    
    result = alerter.send_test_alert(channel)
    return jsonify(result)

@app.route('/api/alert-history', methods=['GET'])
def get_alert_history():
    """Get alert history"""
    limit = request.args.get('limit', 100, type=int)
    history = db.get_alert_history(limit)
    return jsonify(history)


# ============================================================================
# Scheduled Reports API Routes
# ============================================================================

@app.route('/api/reports/test', methods=['POST'])
@operator_required
def send_test_report():
    """Send a test scheduled report"""
    try:
        report_data = report_generator.generate_daily_report()
        html_content = report_generator.generate_html_report(report_data)
        result = report_generator.send_report_email(html_content, subject="🌐 Network Monitor - Test Report")
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# User Management API Routes (Admin only)
# ============================================================================

@app.route('/api/users', methods=['GET'])
@admin_required
def get_users():
    """Get all users"""
    users = db.get_all_users()
    return jsonify(users)

@app.route('/api/users', methods=['POST'])
@admin_required
def create_user():
    """Create a new user"""
    data = request.json
    
    if not data.get('username') or not data.get('password'):
        return jsonify({'success': False, 'error': 'Username and password required'}), 400
    
    result = db.add_user(
        username=data['username'],
        password=data['password'],
        role=data.get('role', 'viewer'),
        display_name=data.get('display_name'),
        email=data.get('email')
    )
    
    if result['success']:
        return jsonify(result), 201
    return jsonify(result), 400

@app.route('/api/users/<int:user_id>', methods=['PUT'])
@admin_required
def update_user(user_id):
    """Update a user"""
    data = request.json
    
    result = db.update_user(
        user_id,
        role=data.get('role'),
        display_name=data.get('display_name'),
        email=data.get('email'),
        is_active=data.get('is_active'),
        password=data.get('password')
    )
    
    return jsonify(result)

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    """Delete a user"""
    result = db.delete_user(user_id)
    return jsonify(result)

@app.route('/api/users/me', methods=['GET'])
@login_required
def get_current_user():
    """Get current logged-in user info"""
    return jsonify({
        'id': session.get('user_id'),
        'username': session.get('username'),
        'role': session.get('role'),
        'display_name': session.get('display_name')
    })

@app.route('/api/users/me/password', methods=['PUT'])
@login_required
def change_my_password():
    """Change current user's password"""
    data = request.json
    
    if not data.get('current_password') or not data.get('new_password'):
        return jsonify({'success': False, 'error': 'Current and new password required'}), 400
    
    user = db.get_user_by_id(session.get('user_id'))
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404
    
    from werkzeug.security import check_password_hash
    if not check_password_hash(user['password_hash'], data['current_password']):
        return jsonify({'success': False, 'error': 'Current password incorrect'}), 401
    
    result = db.update_user(user['id'], password=data['new_password'])
    return jsonify(result)


# ============================================================================
# Maintenance Windows API Routes
# ============================================================================

@app.route('/api/maintenance', methods=['GET'])
def get_maintenance_windows():
    """Get all maintenance windows"""
    windows = db.get_all_maintenance_windows()
    return jsonify(windows)

@app.route('/api/maintenance', methods=['POST'])
@operator_required
def add_maintenance_window():
    """Add a new maintenance window"""
    data = request.json
    
    if not data.get('name') or not data.get('start_time') or not data.get('end_time'):
        return jsonify({'success': False, 'error': 'Name, start_time, and end_time are required'}), 400
    
    result = db.add_maintenance_window(
        name=data['name'],
        start_time=data['start_time'],
        end_time=data['end_time'],
        device_id=data.get('device_id'),  # None = all devices
        recurring=data.get('recurring'),
        description=data.get('description')
    )
    
    if result['success']:
        return jsonify(result), 201
    return jsonify(result), 400

@app.route('/api/maintenance/<int:window_id>', methods=['DELETE'])
@operator_required
def delete_maintenance_window(window_id):
    """Delete a maintenance window"""
    result = db.delete_maintenance_window(window_id)
    return jsonify(result)

@app.route('/api/maintenance/active', methods=['GET'])
def get_active_maintenance():
    """Get currently active maintenance windows"""
    device_id = request.args.get('device_id', type=int)
    windows = db.get_active_maintenance(device_id)
    return jsonify(windows)

# ============================================================================
# SLA Dashboard Routes
# ============================================================================

@app.route('/sla')
def sla_page():
    """SLA Dashboard page"""
    return render_template('sla.html')

@app.route('/api/sla', methods=['GET'])
def get_sla_data():
    """Get SLA data for all devices"""
    days = request.args.get('days', 30, type=int)
    sla_target = request.args.get('target', 99.9, type=float)
    
    sla_data = db.get_all_devices_sla(days=days, sla_target=sla_target)
    
    # Calculate summary
    devices_with_data = [d for d in sla_data if d['uptime_percent'] is not None]
    summary = {
        'total_devices': len(sla_data),
        'devices_with_data': len(devices_with_data),
        'sla_met': len([d for d in devices_with_data if d['sla_status'] == 'met']),
        'sla_warning': len([d for d in devices_with_data if d['sla_status'] == 'warning']),
        'sla_breached': len([d for d in devices_with_data if d['sla_status'] == 'breached']),
        'average_uptime': round(sum(d['uptime_percent'] for d in devices_with_data) / len(devices_with_data), 4) if devices_with_data else None,
        'days': days,
        'sla_target': sla_target
    }
    
    return jsonify({
        'summary': summary,
        'devices': sla_data
    })

@app.route('/api/sla/<int:device_id>', methods=['GET'])
def get_device_sla(device_id):
    """Get SLA data for a specific device"""
    days = request.args.get('days', 30, type=int)
    stats = db.get_device_uptime_stats(device_id, days=days)
    device = db.get_device(device_id)
    
    if not device:
        return jsonify({'error': 'Device not found'}), 404
    
    return jsonify({
        'device': device,
        **stats
    })



# ============================================================================
# Dashboard Management Routes
# ============================================================================

@app.route('/dashboards')
@login_required
def dashboards_list():
    """List all dashboards page"""
    return render_template('dashboards.html')

@app.route('/dashboard/new')
@admin_required
def new_dashboard():
    """Dashboard creator page"""
    return render_template('dashboard_builder.html')

@app.route('/dashboard/<int:dashboard_id>/edit')
@admin_required
def edit_dashboard(dashboard_id):
    """Edit dashboard page"""
    return render_template('dashboard_builder.html', dashboard_id=dashboard_id)

@app.route('/dashboard/<int:dashboard_id>')
@login_required
def view_dashboard(dashboard_id):
    """View specific dashboard"""
    return render_template('dashboard_view.html', dashboard_id=dashboard_id)

@app.route('/api/dashboards', methods=['GET'])
@login_required
def get_dashboards():
    """Get all dashboards"""
    user_id = session.get('user_id')
    dashboards = db.get_dashboards(user_id)
    
    # Parse layout_config JSON string
    for d in dashboards:
        try:
            if d['layout_config']:
                d['layout_config'] = json.loads(d['layout_config'])
        except:
            d['layout_config'] = []
            
    return jsonify(dashboards)

@app.route('/api/dashboards', methods=['POST'])
@admin_required
def create_dashboard():
    """Create a new dashboard"""
    data = request.json
    
    if not data.get('name'):
        return jsonify({'success': False, 'error': 'Name is required'}), 400
        
    layout_config = data.get('layout_config')
    if isinstance(layout_config, (dict, list)):
        layout_config = json.dumps(layout_config)
    
    result = db.create_dashboard(
        name=data['name'],
        layout_config=layout_config,
        description=data.get('description'),
        created_by=session.get('user_id'),
        is_public=data.get('is_public', 0)
    )
    
    return jsonify(result)

@app.route('/api/dashboards/<int:dashboard_id>', methods=['GET'])
@login_required
def get_dashboard(dashboard_id):
    """Get a specific dashboard"""
    dashboard = db.get_dashboard(dashboard_id)
    if not dashboard:
        return jsonify({'error': 'Dashboard not found'}), 404
        
    # Check access
    if not dashboard['is_public'] and dashboard['created_by'] != session.get('user_id'):
        return jsonify({'error': 'Access denied'}), 403
        
    try:
        if dashboard['layout_config']:
            dashboard['layout_config'] = json.loads(dashboard['layout_config'])
    except:
        dashboard['layout_config'] = []
        
    return jsonify(dashboard)

@app.route('/api/dashboards/<int:dashboard_id>', methods=['PUT'])
@admin_required
def update_dashboard(dashboard_id):
    """Update a dashboard"""
    data = request.json
    
    # Check ownership or admin
    dashboard = db.get_dashboard(dashboard_id)
    if not dashboard:
        return jsonify({'error': 'Dashboard not found'}), 404
        
    # We are already in @admin_required, strictly enforcing admins only for now.
    # If we want regular users to update their own, we'd need different logic.
    # Current requirement says "Admin can define...", so @admin_required is safe.

    layout_config = data.get('layout_config')
    if layout_config is not None and isinstance(layout_config, (dict, list)):
        layout_config = json.dumps(layout_config)
        
    result = db.update_dashboard(
        dashboard_id,
        name=data.get('name'),
        layout_config=layout_config,
        description=data.get('description'),
        is_public=data.get('is_public')
    )
    
    return jsonify(result)

@app.route('/api/dashboards/<int:dashboard_id>', methods=['DELETE'])
@admin_required
def delete_dashboard(dashboard_id):
    """Delete a dashboard"""
    result = db.delete_dashboard(dashboard_id)
    return jsonify(result)

# ============================================================================
# Sub-Topology Routes
# ============================================================================

@app.route('/sub-topology/new')
@operator_required
def new_sub_topology():
    """Sub-topology builder page (create)"""
    return render_template('sub_topology_builder.html')

@app.route('/sub-topology/<int:sub_topo_id>/edit')
@operator_required
def edit_sub_topology(sub_topo_id):
    """Sub-topology builder page (edit)"""
    return render_template('sub_topology_builder.html', sub_topo_id=sub_topo_id)

@app.route('/sub-topology/<int:sub_topo_id>')
@login_required
def view_sub_topology(sub_topo_id):
    """View sub-topology"""
    return render_template('sub_topology_view.html', sub_topo_id=sub_topo_id)

@app.route('/api/sub-topologies', methods=['GET'])
@login_required
def get_sub_topologies():
    """Get all sub-topologies"""
    sub_topos = db.get_all_sub_topologies()
    return jsonify(sub_topos)

@app.route('/api/sub-topologies', methods=['POST'])
@operator_required
def create_sub_topology():
    """Create a new sub-topology"""
    data = request.json
    
    if not data.get('name'):
        return jsonify({'success': False, 'error': 'Name is required'}), 400
    
    result = db.create_sub_topology(
        name=data['name'],
        description=data.get('description'),
        created_by=session.get('user_id'),
        background_image=data.get('background_image'),
        background_zoom=data.get('background_zoom', 100),
        node_positions=data.get('node_positions'),
        background_opacity=data.get('background_opacity', 100)
    )
    
    if result['success']:
        sub_topo_id = result['id']
        # Save devices
        device_ids = data.get('device_ids', [])
        connections = data.get('connections', [])
        db.update_sub_topology(sub_topo_id, device_ids=device_ids, connections=connections)
        return jsonify(result), 201
    
    return jsonify(result), 400

@app.route('/api/sub-topologies/<int:sub_topo_id>', methods=['GET'])
@login_required
def get_sub_topology_detail(sub_topo_id):
    """Get a sub-topology with devices and connections"""
    sub_topo = db.get_sub_topology(sub_topo_id)
    if not sub_topo:
        return jsonify({'error': 'Sub-topology not found'}), 404
    return jsonify(sub_topo)

@app.route('/api/sub-topologies/<int:sub_topo_id>', methods=['PUT'])
@operator_required
def update_sub_topology_route(sub_topo_id):
    """Update a sub-topology"""
    data = request.json
    
    sub_topo = db.get_sub_topology(sub_topo_id)
    if not sub_topo:
        return jsonify({'error': 'Sub-topology not found'}), 404
    
    result = db.update_sub_topology(
        sub_topo_id,
        name=data.get('name'),
        description=data.get('description'),
        device_ids=data.get('device_ids'),
        connections=data.get('connections'),
        background_image=data.get('background_image'),
        background_zoom=data.get('background_zoom'),
        node_positions=data.get('node_positions'),
        background_opacity=data.get('background_opacity')
    )
    
    return jsonify(result)

@app.route('/api/sub-topologies/<int:sub_topo_id>', methods=['DELETE'])
@operator_required
def delete_sub_topology_route(sub_topo_id):
    """Delete a sub-topology"""
    result = db.delete_sub_topology(sub_topo_id)
    return jsonify(result)

@app.route('/api/sub-topologies/upload-bg', methods=['POST'])
@operator_required
def upload_sub_topology_bg():
    """Upload a background image for sub-topology"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400
    
    # Validate file type
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in allowed_extensions:
        return jsonify({'success': False, 'error': f'Invalid file type. Allowed: {allowed_extensions}'}), 400
    
    # Save file
    bg_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'backgrounds')
    os.makedirs(bg_dir, exist_ok=True)
    
    import uuid
    filename = f'bg_{uuid.uuid4().hex[:8]}.{ext}'
    filepath = os.path.join(bg_dir, filename)
    file.save(filepath)
    
    # Return URL path
    url_path = f'/static/uploads/backgrounds/{filename}'
    return jsonify({'success': True, 'url': url_path})


# ============================================================================
# WebSocket Events
# ============================================================================

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print('Client connected')
    # Send current statistics to newly connected client
    stats = monitor.get_statistics()
    emit('statistics_update', stats)
    
    # Send current device status
    devices = db.get_all_devices()
    for device in devices:
        emit('status_update', {
            'id': device['id'],
            'name': device['name'],
            'ip_address': device['ip_address'],
            'device_type': device.get('device_type'),
            'monitor_type': device.get('monitor_type', 'ping'),
            'status': device['status'],
            'response_time': device['response_time'],
            'http_status_code': device.get('http_status_code'),
            'last_check': device['last_check']
        })

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print('Client disconnected')

@socketio.on('request_status')
def handle_request_status():
    """Handle request for immediate status check"""
    print('Status check requested')
    monitor_devices()

# ============================================================================
# Main
# ============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("Network Monitor Server Starting...")
    print("=" * 60)
    print(f"Dashboard: http://localhost:5000")
    print(f"Topology:  http://localhost:5000/topology")
    print(f"Devices:   http://localhost:5000/devices")
    print(f"Monitoring interval: {Config.PING_INTERVAL} seconds")
    print("=" * 60)
    
    socketio.run(app, debug=False, host='0.0.0.0', port=5000, use_reloader=False, allow_unsafe_werkzeug=True)
