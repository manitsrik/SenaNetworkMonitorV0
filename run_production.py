"""
Network Monitor — Production Server Entry Point
Uses eventlet for production-grade WebSocket + WSGI support on Windows
"""
import eventlet
eventlet.monkey_patch()

import logging
import sys
from datetime import datetime

# Configure production logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('NetworkMonitor')

# Import app after monkey patching
from app import app, socketio
from config import Config

if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("Network Monitor — Production Server")
    logger.info("=" * 60)
    logger.info(f"Host: {Config.SERVER_HOST}:{Config.SERVER_PORT}")
    logger.info(f"Database: {Config.DB_TYPE}")
    logger.info(f"Monitor workers: {Config.MONITOR_MAX_WORKERS}")
    logger.info(f"Pool: min={Config.PG_POOL_MIN}, max={Config.PG_POOL_MAX}")
    logger.info(f"WSGI: eventlet (production)")
    logger.info(f"Started at: {datetime.now().isoformat()}")
    logger.info("=" * 60)
    
    socketio.run(
        app,
        host=Config.SERVER_HOST,
        port=Config.SERVER_PORT,
        debug=Config.DEBUG,
        use_reloader=False,
        log_output=True
    )
