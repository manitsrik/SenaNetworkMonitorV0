"""
Network Monitor - Main Application
Slim entry point: initializes Flask, registers Blueprints, starts services
"""
import eventlet
eventlet.monkey_patch(all=True)

import asyncio
import sys
if sys.platform == 'win32':
    # Force SelectorEventLoop so asyncio uses select(), which eventlet monkey-patches.
    # This prevents PySNMP (which uses asyncio) from deadlocking the server on Windows.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from flask import Flask, jsonify, request
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from database import Database
from monitor import NetworkMonitor
from alerter import Alerter
from telegram_bot import TelegramBot
from scheduler_reports import ReportGenerator
from discovery import DeviceDiscovery
from service_manager import ServiceManager
from task_scheduler import TaskScheduler
from snmp_trap_receiver import SnmpTrapReceiver
from syslog_receiver import SyslogReceiver
from plugin_manager import PluginManager
from config import Config
import atexit
import os

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = Config.SECRET_KEY
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
CORS(app)

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins=Config.SOCKETIO_CORS_ALLOWED_ORIGINS,
                   async_mode='eventlet')

# Initialize Babel
from flask_babel import Babel, gettext as _
from flask import session

def get_locale():
    # if a user is logged in, use the locale from the session
    return session.get('lang', 'en')

babel = Babel(app, locale_selector=get_locale)
app.config['BABEL_DEFAULT_LOCALE'] = 'en'
app.config['BABEL_TRANSLATION_DIRECTORIES'] = 'translations'

# Initialize core services
db = Database()
monitor = NetworkMonitor(db)
alerter = Alerter(db)
telegram_bot = TelegramBot(db)
report_generator = ReportGenerator(db)
discovery = DeviceDiscovery()
trap_receiver = SnmpTrapReceiver(db)
syslog_receiver = SyslogReceiver(db)
plugin_manager = PluginManager(db)
monitor.alerter = alerter
monitor.plugin_manager = plugin_manager
alerter.plugin_manager = plugin_manager

# Store shared instances in app.config for Blueprint access
app.config['DB'] = db
app.config['MONITOR'] = monitor
app.config['ALERTER'] = alerter
app.config['SOCKETIO'] = socketio
app.config['REPORT_GENERATOR'] = report_generator
app.config['DISCOVERY'] = discovery
app.config['TRAP_RECEIVER'] = trap_receiver
app.config['SYSLOG_RECEIVER'] = syslog_receiver
app.config['PLUGIN_MANAGER'] = plugin_manager

# ============================================================================
# Register Blueprints
# ============================================================================

from routes import ALL_BLUEPRINTS

for bp in ALL_BLUEPRINTS:
    app.register_blueprint(bp)

# Swagger API Documentation UI
from flask_swagger_ui import get_swaggerui_blueprint
SWAGGER_URL = '/api/docs'
API_SPEC_URL = '/static/swagger/openapi.yaml'
swagger_bp = get_swaggerui_blueprint(SWAGGER_URL, API_SPEC_URL,
    config={'app_name': 'NW Monitor API', 'layout': 'BaseLayout'})
app.register_blueprint(swagger_bp, url_prefix=SWAGGER_URL)

@app.route('/sw.js')
def serve_sw():
    from flask import send_from_directory
    return send_from_directory('static', 'sw.js', mimetype='application/javascript')

@app.route('/manifest.json')
def serve_manifest():
    from flask import send_from_directory
    return send_from_directory('static', 'manifest.json', mimetype='application/json')

@app.route('/PLUGIN_DEVELOPMENT.md')
def serve_plugin_development_guide():
    from flask import send_from_directory
    return send_from_directory('.', 'PLUGIN_DEVELOPMENT.md', mimetype='text/markdown')

# ============================================================================
# Task Scheduler & Service Manager
# ============================================================================

task_scheduler = TaskScheduler(db)

def monitor_devices():
    """Background task to monitor all devices"""
    print(f"Running scheduled device check (workers={monitor.max_workers})...")
    results = monitor.check_all_devices()
    
    for result in results:
        socketio.emit('status_update', result, namespace='/')
    
    stats = monitor.get_statistics()
    socketio.emit('statistics_update', stats, namespace='/')
    return results

def scheduled_daily_report():
    """Background task to send daily status report"""
    print("Running scheduled daily report...")
    report_generator.run_daily_report()

def scheduled_data_cleanup():
    """Background task to clean up old data"""
    print("Running scheduled data cleanup...")
    db.cleanup_old_data()
    db.cleanup_job_history(days=7)

def check_alert_escalations():
    """Background task to check for and trigger escalated alerts"""
    enabled = db.get_alert_setting('escalation_enabled')
    if str(enabled).lower() != 'true':
        return
        
    minutes_str = db.get_alert_setting('escalation_time_minutes')
    try:
        minutes = int(minutes_str) if minutes_str else 15
    except ValueError:
        minutes = 15
        
    devices_to_escalate = db.get_devices_for_escalation(minutes)
    if not devices_to_escalate:
        return
        
    print(f"Running scheduled escalation check: found {len(devices_to_escalate)} devices ready for escalation...")
    for device in devices_to_escalate:
        success = alerter.trigger_escalated_alert(device, minutes)
        if success:
            db.mark_device_escalated(device['id'])

def check_custom_reports_schedule():
    """Background task to generate and send custom reports according to their schedule"""
    reports = db.get_custom_reports()
    from flask import render_template
    from routes.reports import view_report_page
    from datetime import datetime, timedelta
    
    now = datetime.now()
    current_time_str = now.strftime('%H:%M')
    current_day_week = now.strftime('%a')[:3] # Mon, Tue, Wed...
    current_day_month = str(now.day)
    
    for r in reports:
        if r.get('schedule_type') == 'none':
            continue
            
        # Time must match exactly (HH:MM) since this runs every minute
        if r.get('schedule_time') != current_time_str:
            continue
            
        if r.get('schedule_type') == 'weekly' and r.get('schedule_day') != current_day_week:
            continue
            
        if r.get('schedule_type') == 'monthly':
            if r.get('schedule_day') == 'last':
                tomorrow = now + timedelta(days=1)
                if tomorrow.day != 1:
                    continue
            elif r.get('schedule_day') != current_day_month:
                continue
                
        # Send it
        recipients = r.get('email_recipients', '')
        if not recipients:
            continue
            
        print(f"[CustomReports] Triggering scheduled report: {r['name']}")
        try:
            report_full = db.get_custom_report(r['id'])
            
            # Build widget data manually similar to routes/reports.py
            widget_data = {}
            if 'widgets' in report_full:
                import json
                from datetime import timedelta
                for w in report_full['widgets']:
                    try:
                        if w['config'] and isinstance(w['config'], str):
                            w['config'] = json.loads(w['config'])
                    except:
                        w['config'] = {}
                        
                    w_type = w['widget_type']
                    wid = w['id']
                    
                    if w_type == 'uptime_summary':
                        devices = db.get_all_devices()
                        total = len(devices)
                        up_count = sum(1 for d in devices if d.get('status') == 'up')
                        down_count = sum(1 for d in devices if d.get('status') == 'down')
                        slow_count = sum(1 for d in devices if d.get('status') == 'slow')
                        uptime_percent = (up_count + slow_count) / total * 100 if total > 0 else 0
                        widget_data[wid] = {
                            'total': total, 'up': up_count, 'down': down_count,
                            'slow': slow_count, 'uptime_percent': round(uptime_percent, 2)
                        }
                    elif w_type == 'down_devices':
                        devices = db.get_all_devices()
                        widget_data[wid] = [d for d in devices if d.get('status') == 'down']
                    elif w_type == 'slow_devices':
                        devices = db.get_all_devices()
                        widget_data[wid] = [d for d in devices if d.get('status') == 'slow']
                    elif w_type == 'recent_alerts':
                        alerts = db.get_alert_history(limit=20)
                        yesterday = (datetime.now() - timedelta(days=1)).isoformat()
                        widget_data[wid] = [a for a in alerts if a.get('created_at', '') > yesterday]
                    elif w_type == 'bandwidth_top':
                        conn = db.get_connection()
                        cursor = db._cursor(conn)
                        ph = db._ph()
                        cursor.execute(f'''
                            SELECT d.name as device_name, b.if_name, b.util_in, b.util_out, b.bps_in, b.bps_out
                            FROM bandwidth_history b
                            JOIN devices d ON b.device_id = d.id
                            WHERE b.sampled_at > {ph}
                            ORDER BY (b.util_in + b.util_out) DESC
                            LIMIT 10
                        ''', ((datetime.now() - timedelta(hours=1)).isoformat(),))
                        try:
                            widget_data[wid] = db._rows_to_dicts(cursor.fetchall())
                        except:
                            widget_data[wid] = []
                        db.release_connection(conn)

            # Render HTML and send using app context
            with app.app_context():
                html_content = render_template('report_view.html', report=report_full, widget_data=widget_data)
            
            subject = f"Network Report: {r['name']}"
            result = report_generator.send_report_email(html_content, subject=subject, to_email=recipients)
            if result.get('success'):
                print(f"[CustomReports] Sent report '{r['name']}' to {recipients}")
            else:
                print(f"[CustomReports] Failed to send report: {result.get('error')}")
                
        except Exception as e:
            print(f"[CustomReports] Task error for {r['name']}: {e}")


def materialize_incidents():
    """Background task to persist correlated incident snapshots."""
    print("Running persistent incident materialization...")
    return db.sync_persistent_incidents(limit=500, window_minutes=10, dedupe_minutes=2)


def materialize_anomalies():
    """Background task to persist anomaly snapshots."""
    print("Running anomaly detection materialization...")
    return db.sync_anomaly_snapshots(recent_minutes=30, baseline_hours=24, min_points=5)


# Register tasks with metadata and history tracking
task_scheduler.add_task('monitor_job', 'Device Monitoring', monitor_devices,
                        trigger='interval', seconds=Config.PING_INTERVAL)
task_scheduler.add_task('bandwidth_poll', 'Bandwidth Polling',
                        lambda: monitor.poll_bandwidth_all_snmp_devices(),
                        trigger='interval', seconds=60)
task_scheduler.add_task('alert_escalation', 'Alert Escalation Check', check_alert_escalations,
                        trigger='interval', minutes=1)
task_scheduler.add_task('custom_reports', 'Custom Reports Dispatch', check_custom_reports_schedule,
                        trigger='interval', minutes=1)
task_scheduler.add_task('incident_materialize', 'Incident Materialization', materialize_incidents,
                        trigger='interval', minutes=1)
task_scheduler.add_task('anomaly_detection', 'Anomaly Detection', materialize_anomalies,
                        trigger='interval', minutes=5)
task_scheduler.add_task('daily_report', 'Daily Report', scheduled_daily_report,
                        trigger='cron', hour=8, minute=0)
task_scheduler.add_task('cleanup', 'Data Cleanup', scheduled_data_cleanup,
                        trigger='cron', hour=3, minute=0)

# Service Manager — centralized lifecycle management
manager = ServiceManager()
manager.register('task_scheduler', task_scheduler, start_fn='start', stop_fn='shutdown')
manager.register('telegram_bot', telegram_bot, start_fn='start_polling', stop_fn='stop_polling')
# manager.register('trap_receiver', trap_receiver, start_fn='start', stop_fn='stop')
manager.register('syslog_receiver', syslog_receiver, start_fn='start', stop_fn='stop')
manager.register('db_pool', db, stop_fn='close_pool')

# Start all services
manager.start_all()

# Store for API access
app.config['SERVICE_MANAGER'] = manager
app.config['TASK_SCHEDULER'] = task_scheduler

# Shutdown hook
atexit.register(lambda: manager.stop_all())

# ============================================================================
# Service & Task Management API
# ============================================================================

@app.route('/api/services/status')
def api_services_status():
    """Get status of all background services"""
    status = manager.get_status()
    status['monitor_workers'] = monitor.max_workers
    status['db_type'] = db.db_type
    status['db_pool_active'] = db._pool is not None if hasattr(db, '_pool') else False
    return jsonify(status)

@app.route('/api/tasks')
def api_tasks_list():
    """Get all scheduled tasks with their status"""
    tasks = task_scheduler.get_tasks()
    return jsonify({'tasks': tasks})

@app.route('/api/tasks/<job_id>/run', methods=['POST'])
def api_task_run(job_id):
    """Run a task immediately"""
    result = task_scheduler.run_now(job_id)
    return jsonify(result)

@app.route('/api/tasks/<job_id>/pause', methods=['POST'])
def api_task_pause(job_id):
    """Pause a scheduled task"""
    result = task_scheduler.pause_task(job_id)
    return jsonify(result)

@app.route('/api/tasks/<job_id>/resume', methods=['POST'])
def api_task_resume(job_id):
    """Resume a paused task"""
    result = task_scheduler.resume_task(job_id)
    return jsonify(result)

@app.route('/api/tasks/history')
def api_tasks_history():
    """Get job execution history"""
    job_id = request.args.get('job_id')
    limit = int(request.args.get('limit', 50))
    history = task_scheduler.get_history(job_id=job_id, limit=limit)
    return jsonify({'history': history})

# ============================================================================
# WebSocket Events
# ============================================================================

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print('Client connected')
    stats = monitor.get_statistics()
    emit('statistics_update', stats)
    
    devices = db.get_all_devices()
    for device in devices:
        # Convert datetime to string for JSON serialization
        last_check_val = device.get('last_check')
        if hasattr(last_check_val, 'isoformat'):
            last_check_val = last_check_val.isoformat()
            
        emit('status_update', {
            'id': device['id'],
            'name': device['name'],
            'ip_address': device['ip_address'],
            'device_type': device.get('device_type'),
            'monitor_type': device.get('monitor_type', 'ping'),
            'status': device['status'],
            'response_time': device['response_time'],
            'http_status_code': device.get('http_status_code'),
            'last_check': last_check_val
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
    print(f"Dashboard: http://localhost:{Config.SERVER_PORT}")
    print(f"Topology:  http://localhost:{Config.SERVER_PORT}/topology")
    print(f"Devices:   http://localhost:{Config.SERVER_PORT}/devices")
    print(f"Monitoring interval: {Config.PING_INTERVAL} seconds")
    print(f"Monitor workers: {Config.MONITOR_MAX_WORKERS}")
    print(f"Database: {Config.DB_TYPE}")
    print(f"WSGI: eventlet (production)")
    print("=" * 60)
    
    socketio.run(app, debug=Config.DEBUG, host=Config.SERVER_HOST,
                 port=Config.SERVER_PORT, use_reloader=False, log_output=True)

