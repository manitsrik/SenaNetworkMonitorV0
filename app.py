"""
Network Monitor - Main Application
Slim entry point: initializes Flask, registers Blueprints, starts services
"""
from flask import Flask
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
from database import Database
from monitor import NetworkMonitor
from alerter import Alerter
from telegram_bot import TelegramBot
from scheduler_reports import ReportGenerator
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
                   async_mode=Config.SOCKETIO_ASYNC_MODE)

# Initialize core services
db = Database()
monitor = NetworkMonitor(db)
alerter = Alerter(db)
telegram_bot = TelegramBot(db)
report_generator = ReportGenerator(db)
monitor.alerter = alerter

# Store shared instances in app.config for Blueprint access
app.config['DB'] = db
app.config['MONITOR'] = monitor
app.config['ALERTER'] = alerter
app.config['SOCKETIO'] = socketio
app.config['REPORT_GENERATOR'] = report_generator

# ============================================================================
# Register Blueprints
# ============================================================================

from routes import ALL_BLUEPRINTS

for bp in ALL_BLUEPRINTS:
    app.register_blueprint(bp)

# ============================================================================
# Background Scheduler
# ============================================================================

scheduler = BackgroundScheduler()

def monitor_devices():
    """Background task to monitor all devices"""
    print("Running scheduled device check...")
    results = monitor.check_all_devices()
    
    for result in results:
        socketio.emit('status_update', result, namespace='/')
    
    stats = monitor.get_statistics()
    socketio.emit('statistics_update', stats, namespace='/')

def scheduled_daily_report():
    """Background task to send daily status report"""
    print("Running scheduled daily report...")
    report_generator.run_daily_report()

scheduler.add_job(func=monitor_devices, trigger="interval", 
                 seconds=Config.PING_INTERVAL, id='monitor_job')
scheduler.add_job(func=scheduled_daily_report, trigger="cron", 
                 hour=8, minute=0, id='daily_report_job')
scheduler.start()

# Start Telegram bot polling
telegram_bot.start_polling()

# Shutdown hooks
atexit.register(lambda: scheduler.shutdown())
atexit.register(lambda: telegram_bot.stop_polling())

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
