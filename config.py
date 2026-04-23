"""
Configuration settings for Network Monitor
"""
import os


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def _env_list(name, default=''):
    value = os.environ.get(name, default)
    if value is None:
        return []
    return [item.strip() for item in str(value).split(',') if item.strip()]


def _load_env_file():
    """Load key=value pairs from a local .env file if present."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if not os.path.exists(env_path):
        return

    try:
        with open(env_path, 'r', encoding='utf-8') as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)
    except Exception:
        # Keep config import resilient even if .env is malformed.
        pass


_load_env_file()

class Config:
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SECRET_ENCRYPTION_KEY = os.environ.get('SECRET_ENCRYPTION_KEY') or SECRET_KEY
    TESTING = _env_bool('TESTING', False)
    
    # Server settings
    SERVER_HOST = os.environ.get('SERVER_HOST') or '0.0.0.0'
    SERVER_PORT = int(os.environ.get('SERVER_PORT') or 5000)
    DEBUG = _env_bool('DEBUG', False)
    STRICT_STARTUP_VALIDATION = _env_bool('STRICT_STARTUP_VALIDATION', False)
    ENABLE_SWAGGER_UI = _env_bool('ENABLE_SWAGGER_UI', True)
    EXPOSE_INTERNAL_DOCS = _env_bool('EXPOSE_INTERNAL_DOCS', False)
    
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
    
    # Connection Pool settings (PostgreSQL only)
    PG_POOL_MIN = int(os.environ.get('PG_POOL_MIN') or 2)
    PG_POOL_MAX = int(os.environ.get('PG_POOL_MAX') or 30)  # Increased from 15 to handle concurrent monitoring and API headroom
    
    # Monitoring settings
    PING_INTERVAL = 60  # seconds between ping checks
    PING_TIMEOUT = 2    # seconds to wait for ping response
    PING_COUNT = 3      # number of pings per check
    MONITOR_MAX_WORKERS = int(os.environ.get('MONITOR_MAX_WORKERS') or 12)  # parallel workers
    
    # WebSocket settings
    SOCKETIO_ASYNC_MODE = os.environ.get('SOCKETIO_ASYNC_MODE') or 'eventlet'
    CORS_ALLOWED_ORIGINS = _env_list('CORS_ALLOWED_ORIGINS', '')
    SOCKETIO_CORS_ALLOWED_ORIGINS = _env_list(
        'SOCKETIO_CORS_ALLOWED_ORIGINS',
        ','.join(CORS_ALLOWED_ORIGINS)
    )
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE') or 'Lax'
    SESSION_COOKIE_SECURE = _env_bool('SESSION_COOKIE_SECURE', False)
    
    
    # HTTP Monitoring settings
    HTTP_TIMEOUT = 10  # seconds to wait for HTTP response
    HTTP_USER_AGENT = 'NetworkMonitor/1.0'
    VERIFY_SSL = True  # Verify SSL certificates
    
    # Response time thresholds (ms) per monitor type
    MONITOR_THRESHOLDS = {
        'ping': 200,      # Faster for local network
        'website': 2000,  # Web apps typically have higher latency
        'http': 2000,
        'tcp': 500,       # Port checks should be fast
        'dns': 500,       # DNS lookups should be fast
        'snmp': 2000,     # SNMP queries are slightly heavier
        'ssh': 5000,      # Agent checks are heavy
        'winrm': 5000,    # WinRM/PowerShell is heaviest
    }
    
    # Default fallback threshold
    DEFAULT_SLOW_THRESHOLD = 500
    
    # SSL Certificate settings
    SSL_WARNING_DAYS = 30  # Days before expiry to show warning
    
    # SNMP Monitoring settings
    SNMP_TIMEOUT = 5  # seconds to wait for SNMP response
    SNMP_DEFAULT_COMMUNITY = 'public'  # default community string
    SNMP_DEFAULT_PORT = 161  # default SNMP port
    SNMP_DEFAULT_VERSION = '2c'  # default SNMP version (1, 2c, 3)
    SNMP_V3_DEFAULT_AUTH_PROTOCOL = 'SHA'  # SHA or MD5
    SNMP_V3_DEFAULT_PRIV_PROTOCOL = 'AES128'  # AES128 or DES
    
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

    @classmethod
    def is_production_like(cls):
        return not cls.DEBUG and not cls.TESTING

    @classmethod
    def runtime_warnings(cls):
        warnings = []

        if cls.SECRET_KEY == 'dev-secret-key-change-in-production':
            warnings.append('SECRET_KEY is using the development default.')

        if cls.SECRET_ENCRYPTION_KEY == cls.SECRET_KEY:
            warnings.append('SECRET_ENCRYPTION_KEY matches SECRET_KEY; use a separate value.')

        if cls.DB_TYPE == 'postgresql' and cls.PG_PASSWORD == 'netmonitor_password':
            warnings.append('PG_PASSWORD is using the default placeholder password.')

        if '*' in cls.CORS_ALLOWED_ORIGINS or '*' in cls.SOCKETIO_CORS_ALLOWED_ORIGINS:
            warnings.append('Wildcard CORS origins are enabled; restrict them for production use.')

        return warnings

    @classmethod
    def validate_runtime(cls):
        warnings = cls.runtime_warnings()
        if cls.STRICT_STARTUP_VALIDATION and cls.is_production_like() and warnings:
            raise ValueError('Invalid runtime configuration: ' + ' '.join(warnings))
        return warnings

