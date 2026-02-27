"""
Configuration settings for Network Monitor
"""
import os

class Config:
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Database settings
    DB_TYPE = os.environ.get('DB_TYPE') or 'postgresql'  # 'sqlite' or 'postgresql'
    DATABASE_PATH = 'network_monitor.db'  # SQLite fallback path
    RETENTION_DAYS = 30 # Keep 30 days of history
    
    # PostgreSQL settings
    PG_HOST = os.environ.get('PG_HOST') or 'localhost'
    PG_PORT = int(os.environ.get('PG_PORT') or 5432)
    PG_DATABASE = os.environ.get('PG_DATABASE') or 'network_monitor'
    PG_USER = os.environ.get('PG_USER') or 'netmonitor'
    PG_PASSWORD = os.environ.get('PG_PASSWORD') or 'netmonitor_password'
    
    # Monitoring settings
    PING_INTERVAL = 30  # seconds between ping checks
    PING_TIMEOUT = 2    # seconds to wait for ping response
    PING_COUNT = 3      # number of pings per check
    
    # WebSocket settings
    SOCKETIO_ASYNC_MODE = 'threading'
    SOCKETIO_CORS_ALLOWED_ORIGINS = "*"
    
    
    # HTTP Monitoring settings
    HTTP_TIMEOUT = 10  # seconds to wait for HTTP response
    HTTP_USER_AGENT = 'NetworkMonitor/1.0'
    VERIFY_SSL = True  # Verify SSL certificates
    
    # Response time thresholds
    SLOW_RESPONSE_THRESHOLD = 500  # milliseconds - response time above this is considered slow
    
    # SSL Certificate settings
    SSL_WARNING_DAYS = 30  # Days before expiry to show warning
    
    # SNMP Monitoring settings
    SNMP_TIMEOUT = 5  # seconds to wait for SNMP response
    SNMP_DEFAULT_COMMUNITY = 'public'  # default community string
    SNMP_DEFAULT_PORT = 161  # default SNMP port
    SNMP_DEFAULT_VERSION = '2c'  # default SNMP version (1, 2c)
    
    # TCP Port Check settings
    TCP_TIMEOUT = 10  # seconds to wait for TCP connection (industry standard: 10-30s)
    
    # DNS Monitoring settings
    DNS_TIMEOUT = 5    # seconds timeout per DNS query
    DNS_LIFETIME = 15  # seconds total time for all retries (increased for stability)
    
    # Failure Threshold - require consecutive failures before marking as down
    FAILURE_THRESHOLD = 3  # device must fail 3 consecutive checks to be marked as down
    
    # Device defaults
    DEFAULT_DEVICE_TYPE = 'server'
    DEFAULT_LOCATION = 'Unknown'
    
    # Location Type options
    LOCATION_TYPES = ['cloud', 'internet', 'remote', 'on-premise']
    DEFAULT_LOCATION_TYPE = 'on-premise'
    
    # Alert Settings
    ALERT_COOLDOWN = 300  # seconds between alerts for same device (5 minutes)
    ALERT_ON_DOWN = True
    ALERT_ON_RECOVERY = True
    ALERT_ON_SSL_EXPIRY = True
    SSL_EXPIRY_ALERT_DAYS = 7  # Alert when SSL expires within this many days

