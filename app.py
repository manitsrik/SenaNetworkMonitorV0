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

# Initialize core services
db = Database()
monitor = NetworkMonitor(db)
alerter = Alerter(db)
telegram_bot = TelegramBot(db)
report_generator = ReportGenerator(db)
discovery = DeviceDiscovery()
trap_receiver = SnmpTrapReceiver(db)
syslog_receiver = SyslogReceiver(db)
monitor.alerter = alerter

# Store shared instances in app.config for Blueprint access
app.config['DB'] = db
app.config['MONITOR'] = monitor
app.config['ALERTER'] = alerter
app.config['SOCKETIO'] = socketio
app.config['REPORT_GENERATOR'] = report_generator
app.config['DISCOVERY'] = discovery
app.config['TRAP_RECEIVER'] = trap_receiver
app.config['SYSLOG_RECEIVER'] = syslog_receiver

# ============================================================================
# Register Blueprints
# ============================================================================

from routes import ALL_BLUEPRINTS

for bp in ALL_BLUEPRINTS:
    app.register_blueprint(bp)

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

# Register tasks with metadata and history tracking
task_scheduler.add_task('monitor_job', 'Device Monitoring', monitor_devices,
                        trigger='interval', seconds=Config.PING_INTERVAL)
task_scheduler.add_task('bandwidth_poll', 'Bandwidth Polling',
                        lambda: monitor.poll_bandwidth_all_snmp_devices(),
                        trigger='interval', seconds=60)
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

