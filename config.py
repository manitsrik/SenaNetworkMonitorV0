"""
Configuration settings for Network Monitor
"""
import os


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


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
    # Reload Jinja templates when their files change, without a server restart.
    # Only useful while developing, and it stats every template on each render.
    TEMPLATES_AUTO_RELOAD = _env_bool('TEMPLATES_AUTO_RELOAD', DEBUG)
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
    # The check is executed on the remote server through WinRM, so it verifies
    # that the monitored host itself can resolve DNS and reach the Internet.
    INTERNET_CHECK_URL = os.environ.get('INTERNET_CHECK_URL') or 'http://www.msftconnecttest.com/connecttest.txt'
    INTERNET_CHECK_TIMEOUT = max(1, int(os.environ.get('INTERNET_CHECK_TIMEOUT') or 8))
    INTERNET_CHECK_EXPECTED_STATUS = int(os.environ.get('INTERNET_CHECK_EXPECTED_STATUS') or 200)
    INTERNET_CHECK_EXPECTED_CONTENT = os.environ.get('INTERNET_CHECK_EXPECTED_CONTENT', 'Microsoft Connect Test')
    # A single unhealthy Windows host must not hold the shared monitoring job
    # open for several minutes. The transport values cap individual WSMan
    # operations; WINRM_DEVICE_TIMEOUT caps the complete multi-command check.
    WINRM_OPERATION_TIMEOUT = max(5, int(os.environ.get('WINRM_OPERATION_TIMEOUT') or 20))
    WINRM_READ_TIMEOUT = max(
        WINRM_OPERATION_TIMEOUT + 1,
        int(os.environ.get('WINRM_READ_TIMEOUT') or 30),
    )
    WINRM_DEVICE_TIMEOUT = max(
        WINRM_READ_TIMEOUT + 1,
        int(os.environ.get('WINRM_DEVICE_TIMEOUT') or 50),
    )
    WINRM_SLOW_COMMAND_SECONDS = max(
        1,
        int(os.environ.get('WINRM_SLOW_COMMAND_SECONDS') or 5),
    )
    # Paramiko's connect timeout only covers the TCP handshake and banner, so a
    # host that accepts the session but never answers a command can hold a
    # monitoring worker open indefinitely. This caps the whole check, retry
    # included.
    SSH_DEVICE_TIMEOUT = max(15, int(os.environ.get('SSH_DEVICE_TIMEOUT') or 45))
    
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
    # Additional intermediate/root certificates used by HTTPS monitors. This
    # keeps verification enabled for sites whose servers omit an intermediate
    # certificate that browsers can retrieve through AIA automatically.
    HTTP_EXTRA_CA_CERTS = [
        path if os.path.isabs(path) else os.path.join(BASE_DIR, path)
        for path in _env_list(
            'HTTP_EXTRA_CA_CERTS',
            os.path.join('certs', 'globalsign-gcc-r46-alphassl-ca-2025.pem')
        )
    ]
    
    # Response time thresholds (ms) per monitor type
    MONITOR_THRESHOLDS = {
        'ping': 200,      # Faster for local network
        'website': 2000,  # Web apps typically have higher latency
        'http': 2000,
        'tcp': 500,       # Port checks should be fast
        'dns': 500,       # DNS lookups should be fast
        'snmp': 2000,     # SNMP queries are slightly heavier
        'ssh': 10000,     # Agent checks are heavy
        'winrm': 10000,   # WinRM/PowerShell is heaviest
        'wmi': 5000,      # WMI uses the same heavy Windows agent path as WinRM
    }
    
    # An internet probe fetches a few bytes, so a second is already slow. Kept
    # separate from the device thresholds because it measures the path out to
    # the internet rather than the host.
    INTERNET_SLOW_LATENCY_MS = int(os.environ.get('INTERNET_SLOW_LATENCY_MS') or 800)

    # How close to its own limit a metric has to be before the overview calls
    # it out, as a percentage of that limit.
    ATTENTION_MIN_PERCENT = int(os.environ.get('ATTENTION_MIN_PERCENT') or 75)

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
    FAILURE_THRESHOLD = max(1, int(os.environ.get('FAILURE_THRESHOLD') or 2))
    
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

