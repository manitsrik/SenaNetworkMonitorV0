"""
Database management for Network Monitor
Supports PostgreSQL (primary) and SQLite (fallback)
"""
import sqlite3
import hashlib
import json
import math
from datetime import datetime, timedelta
from config import Config

# PostgreSQL support
try:
    import psycopg2
    import psycopg2.extras
    import psycopg2.errors
    import psycopg2.pool
    PG_AVAILABLE = True
except ImportError:
    PG_AVAILABLE = False

class Database:
    _pool = None  # Class-level pool (shared across instances)
    
    def __init__(self, db_path=None):
        self.db_type = Config.DB_TYPE
        self.db_path = db_path or Config.DATABASE_PATH
        
        if self.db_type == 'postgresql' and not PG_AVAILABLE:
            print("[WARNING] psycopg2 not installed, falling back to SQLite")
            self.db_type = 'sqlite'
        
        # Initialize connection pool for PostgreSQL
        if self.db_type == 'postgresql' and Database._pool is None:
            try:
                Database._pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=Config.PG_POOL_MIN,
                    maxconn=Config.PG_POOL_MAX,
                    host=Config.PG_HOST,
                    port=Config.PG_PORT,
                    dbname=Config.PG_DATABASE,
                    user=Config.PG_USER,
                    password=Config.PG_PASSWORD
                )
                print(f"[DB] Connection pool created (min={Config.PG_POOL_MIN}, max={Config.PG_POOL_MAX})")
            except Exception as e:
                print(f"[WARNING] Failed to create connection pool: {e}, falling back to SQLite")
                self.db_type = 'sqlite'
                Database._pool = None
        
        self.init_db()
    
    def get_connection(self):
        """Get database connection (from pool for PostgreSQL)"""
        if self.db_type == 'postgresql' and Database._pool:
            conn = Database._pool.getconn()
            conn.autocommit = False
            return conn
        elif self.db_type == 'postgresql':
            # Fallback: direct connection if pool not available
            conn = psycopg2.connect(
                host=Config.PG_HOST,
                port=Config.PG_PORT,
                dbname=Config.PG_DATABASE,
                user=Config.PG_USER,
                password=Config.PG_PASSWORD
            )
            conn.autocommit = False
            return conn
        else:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA journal_mode=WAL')
            return conn
    
    def release_connection(self, conn):
        """Return connection to pool (PostgreSQL) or close it (SQLite)"""
        if conn is None:
            return
        if self.db_type == 'postgresql' and Database._pool:
            try:
                Database._pool.putconn(conn)
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
        else:
            try:
                conn.close()
            except Exception:
                pass
    
    def close_pool(self):
        """Close all connections in the pool (call on shutdown)"""
        if Database._pool:
            Database._pool.closeall()
            Database._pool = None
            print("[DB] Connection pool closed")
    
    def _cursor(self, conn):
        """Get appropriate cursor"""
        if self.db_type == 'postgresql':
            return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        return conn.cursor()
    
    def _row_to_dict(self, row):
        """Convert a row to dict and serialize datetimes"""
        if row is None:
            return None
            
        result = {}
        if isinstance(row, dict):
            for k, v in row.items():
                if isinstance(v, datetime):
                    result[k] = v.isoformat()
                else:
                    result[k] = v
            return result
            
        for k in row.keys():
            v = row[k]
            if isinstance(v, datetime):
                result[k] = v.isoformat()
            else:
                result[k] = v
        if 'plugin_config_json' in result:
            try:
                result['plugin_config'] = json.loads(result['plugin_config_json']) if result['plugin_config_json'] else {}
            except Exception:
                result['plugin_config'] = {}
        return result
    
    def _rows_to_dicts(self, rows):
        """Convert rows to list of dicts"""
        return [self._row_to_dict(r) for r in rows]
    
    def _ph(self, count=1):
        """Get placeholder(s) for parameterized queries"""
        ph = '%s' if self.db_type == 'postgresql' else '?'
        if count == 1:
            return ph
        return ', '.join([ph] * count)
    
    def init_db(self):
        """Initialize database tables"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        
        # Use appropriate syntax
        serial_type = 'SERIAL' if self.db_type == 'postgresql' else 'INTEGER'
        autoincrement = '' if self.db_type == 'postgresql' else 'AUTOINCREMENT'
        pk = f'{serial_type} PRIMARY KEY {autoincrement}'.strip()
        bool_type = 'BOOLEAN' if self.db_type == 'postgresql' else 'INTEGER'
        bool_default_true = 'TRUE' if self.db_type == 'postgresql' else '1'
        bool_default_false = 'FALSE' if self.db_type == 'postgresql' else '0'
        timestamp_default = 'CURRENT_TIMESTAMP'
        
        # Devices table
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS devices (
                id {pk},
                name TEXT NOT NULL,
                ip_address TEXT NOT NULL,
                device_type TEXT,
                location TEXT,
                status TEXT DEFAULT 'unknown',
                last_check TIMESTAMP,
                response_time REAL,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                monitor_type TEXT DEFAULT 'ping',
                http_status_code INTEGER,
                expected_status_code INTEGER DEFAULT 200,
                snmp_community TEXT DEFAULT 'public',
                snmp_port INTEGER DEFAULT 161,
                snmp_version TEXT DEFAULT '2c',
                snmp_v3_username TEXT,
                snmp_v3_auth_protocol TEXT DEFAULT 'SHA',
                snmp_v3_auth_password TEXT,
                snmp_v3_priv_protocol TEXT DEFAULT 'AES128',
                snmp_v3_priv_password TEXT,
                snmp_uptime TEXT,
                snmp_sysname TEXT,
                snmp_sysdescr TEXT,
                snmp_syslocation TEXT,
                snmp_syscontact TEXT,
                tcp_port INTEGER DEFAULT 80,
                dns_query_domain TEXT DEFAULT 'google.com',
                ssl_expiry_date TEXT,
                ssl_days_left INTEGER,
                ssl_issuer TEXT,
                ssl_status TEXT,
                location_type TEXT DEFAULT 'on-premise',
                failure_count INTEGER DEFAULT 0,
                latitude REAL,
                longitude REAL,
                is_enabled {bool_type} DEFAULT {bool_default_true},
                ssh_username TEXT,
                ssh_password TEXT,
                ssh_port INTEGER DEFAULT 22,
                wmi_username TEXT,
                wmi_password TEXT,
                plugin_config_json TEXT,
                cpu_usage REAL,
                ram_usage REAL,
                disk_usage REAL,
                UNIQUE(ip_address, monitor_type, device_type)
            )
        ''')
        
        # Migration: Add SNMP v3 columns to existing devices table
        snmp_v3_columns = [
            ('snmp_v3_username', 'TEXT'),
            ('snmp_v3_auth_protocol', "TEXT DEFAULT 'SHA'"),
            ('snmp_v3_auth_password', 'TEXT'),
            ('snmp_v3_priv_protocol', "TEXT DEFAULT 'AES128'"),
            ('snmp_v3_priv_password', 'TEXT'),
        ]
        for col_name, col_type in snmp_v3_columns:
            try:
                if self.db_type == 'postgresql':
                    conn.rollback()
                    cursor.execute(f'ALTER TABLE devices ADD COLUMN {col_name} {col_type}')
                    conn.commit()
                else:
                    cursor.execute(f'ALTER TABLE devices ADD COLUMN {col_name} {col_type}')
            except Exception:
                if self.db_type == 'postgresql':
                    conn.rollback()
                # Column already exists — ignore
        
        # Migration: Add latitude and longitude columns to existing devices table
        location_columns = [
            ('latitude', 'REAL'),
            ('longitude', 'REAL'),
        ]
        for col_name, col_type in location_columns:
            try:
                if self.db_type == 'postgresql':
                    conn.rollback()
                    cursor.execute(f'ALTER TABLE devices ADD COLUMN {col_name} {col_type}')
                    conn.commit()
                else:
                    cursor.execute(f'ALTER TABLE devices ADD COLUMN {col_name} {col_type}')
            except Exception:
                if self.db_type == 'postgresql':
                    conn.rollback()
                # Column already exists — ignore

        # Migration: Add escalation columns
        escalation_columns = [
            ('last_status_change', 'TIMESTAMP'),
            ('escalation_level', 'INTEGER DEFAULT 0'),
        ]
        for col_name, col_type in escalation_columns:
            try:
                if self.db_type == 'postgresql':
                    conn.rollback()
                    cursor.execute(f'ALTER TABLE devices ADD COLUMN {col_name} {col_type}')
                    conn.commit()
                else:
                    cursor.execute(f'ALTER TABLE devices ADD COLUMN {col_name} {col_type}')
            except Exception:
                if self.db_type == 'postgresql':
                    conn.rollback()
        # Column already exists — ignore
        
        # Migration: Add is_enabled column to existing devices table
        try:
            if self.db_type == 'postgresql':
                conn.rollback()
                cursor.execute(f'ALTER TABLE devices ADD COLUMN is_enabled {bool_type} DEFAULT {bool_default_true}')
                conn.commit()
            else:
                cursor.execute(f'ALTER TABLE devices ADD COLUMN is_enabled {bool_type} DEFAULT {bool_default_true}')
        except Exception:
            if self.db_type == 'postgresql':
                conn.rollback()
            # Column already exists — ignore
        
        # Migration: Add parent_device_id column for Alert Dependencies
        try:
            if self.db_type == 'postgresql':
                conn.rollback()
                cursor.execute('ALTER TABLE devices ADD COLUMN parent_device_id INTEGER REFERENCES devices(id) ON DELETE SET NULL')
                conn.commit()
            else:
                cursor.execute('ALTER TABLE devices ADD COLUMN parent_device_id INTEGER REFERENCES devices(id) ON DELETE SET NULL')
        except Exception:
            if self.db_type == 'postgresql':
                conn.rollback()
            # Column already exists — ignore
        
        # Migration: Add SSH/WMI and Metrics columns
        metrics_columns = [
            ('ssh_username', 'TEXT'),
            ('ssh_password', 'TEXT'),
            ('ssh_port', 'INTEGER DEFAULT 22'),
            ('wmi_username', 'TEXT'),
            ('wmi_password', 'TEXT'),
            ('plugin_config_json', 'TEXT'),
            ('expected_ports', 'TEXT'),
            ('cpu_usage', 'REAL'),
            ('ram_usage', 'REAL'),
            ('disk_usage', 'REAL'),
            ('network_in_bps', 'REAL'),
            ('network_out_bps', 'REAL'),
            ('last_network_in', 'BIGINT'),
            ('last_network_out', 'BIGINT'),
            ('last_metrics_time', 'TIMESTAMP'),
        ]
        for col_name, col_type in metrics_columns:
            try:
                if self.db_type == 'postgresql':
                    conn.rollback()
                    cursor.execute(f'ALTER TABLE devices ADD COLUMN {col_name} {col_type}')
                    conn.commit()
                else:
                    cursor.execute(f'ALTER TABLE devices ADD COLUMN {col_name} {col_type}')
            except Exception:
                if self.db_type == 'postgresql':
                    conn.rollback()
                # Column already exists — ignore
        
        # Default Alert Escalation Settings Let's ensure these exist 
        default_escalation_settings = {
            'escalation_enabled': 'false',
            'escalation_time_minutes': '15',
            'escalation_email_recipient': '',
            'escalation_telegram_chat_id': ''
        }
        for k, v in default_escalation_settings.items():
            try:
                if self.db_type == 'postgresql':
                    cursor.execute(f'INSERT INTO alert_settings (setting_key, setting_value) VALUES ({ph}, {ph}) ON CONFLICT (setting_key) DO NOTHING', (k, v))
                else:
                    cursor.execute(f'INSERT OR IGNORE INTO alert_settings (setting_key, setting_value) VALUES (?, ?)', (k, v))
            except Exception:
                pass
        
        # Topology table
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS topology (
                id {pk},
                device_id INTEGER,
                connected_to INTEGER,
                view_type TEXT DEFAULT 'standard',
                FOREIGN KEY (device_id) REFERENCES devices(id),
                FOREIGN KEY (connected_to) REFERENCES devices(id)
            )
        ''')
        
        # Status history table
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS status_history (
                id {pk},
                device_id INTEGER,
                status TEXT,
                response_time REAL,
                checked_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (device_id) REFERENCES devices(id)
            )
        ''')
        
        # Alert settings table
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS alert_settings (
                id {pk},
                setting_key TEXT UNIQUE NOT NULL,
                setting_value TEXT,
                updated_at TIMESTAMP DEFAULT {timestamp_default}
            )
        ''')
        
        # Alert history table
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS alert_history (
                id {pk},
                device_id INTEGER,
                event_type TEXT,
                message TEXT,
                channel TEXT,
                status TEXT,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (device_id) REFERENCES devices(id)
            )
        ''')

        # Maintenance windows table
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS maintenance_windows (
                id {pk},
                name TEXT NOT NULL,
                device_id INTEGER,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                recurring TEXT,
                description TEXT,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (device_id) REFERENCES devices(id)
            )
        ''')
        
        # Users table for multi-user RBAC
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS users (
                id {pk},
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                auth_type TEXT DEFAULT 'local',
                role TEXT NOT NULL DEFAULT 'viewer',
                display_name TEXT,
                email TEXT,
                telegram_chat_id TEXT,
                is_active {bool_type} DEFAULT {bool_default_true},
                last_login TIMESTAMP,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default}
            )
        ''')

        # Incident workflow state table
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS incident_states (
                id {pk},
                incident_id TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                note TEXT,
                owner_user_id INTEGER,
                owner_username TEXT,
                acknowledged_by_user_id INTEGER,
                acknowledged_by_username TEXT,
                acknowledged_at TIMESTAMP,
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (owner_user_id) REFERENCES users(id),
                FOREIGN KEY (acknowledged_by_user_id) REFERENCES users(id)
            )
        ''')

        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS incident_activity (
                id {pk},
                incident_id TEXT NOT NULL,
                action TEXT NOT NULL,
                old_status TEXT,
                new_status TEXT,
                note TEXT,
                actor_user_id INTEGER,
                actor_username TEXT,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (actor_user_id) REFERENCES users(id)
            )
        ''')

        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS persistent_incidents (
                id {pk},
                incident_id TEXT UNIQUE NOT NULL,
                started_at TIMESTAMP,
                latest_at TIMESTAMP,
                severity TEXT,
                alert_count INTEGER DEFAULT 0,
                device_count INTEGER DEFAULT 0,
                root_cause_device_id INTEGER,
                root_cause_device_name TEXT,
                workflow_status TEXT,
                workflow_owner_username TEXT,
                is_active {bool_type} DEFAULT {bool_default_true},
                payload_json TEXT,
                last_materialized_at TIMESTAMP DEFAULT {timestamp_default},
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (root_cause_device_id) REFERENCES devices(id)
            )
        ''')

        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS anomaly_snapshots (
                id {pk},
                anomaly_key TEXT UNIQUE NOT NULL,
                device_id INTEGER,
                device_name TEXT,
                anomaly_type TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                severity TEXT NOT NULL,
                score REAL,
                summary TEXT,
                details_json TEXT,
                detected_at TIMESTAMP DEFAULT {timestamp_default},
                last_seen_at TIMESTAMP DEFAULT {timestamp_default},
                is_active {bool_type} DEFAULT {bool_default_true},
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (device_id) REFERENCES devices(id)
            )
        ''')

        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS anomaly_states (
                id {pk},
                anomaly_key TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                note TEXT,
                owner_user_id INTEGER,
                owner_username TEXT,
                acknowledged_by_user_id INTEGER,
                acknowledged_by_username TEXT,
                acknowledged_at TIMESTAMP,
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (owner_user_id) REFERENCES users(id),
                FOREIGN KEY (acknowledged_by_user_id) REFERENCES users(id)
            )
        ''')

        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS anomaly_activity (
                id {pk},
                anomaly_key TEXT NOT NULL,
                action TEXT NOT NULL,
                old_status TEXT,
                new_status TEXT,
                note TEXT,
                actor_user_id INTEGER,
                actor_username TEXT,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (actor_user_id) REFERENCES users(id)
            )
        ''')

        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS anomaly_incident_links (
                id {pk},
                anomaly_key TEXT UNIQUE NOT NULL,
                incident_id TEXT NOT NULL,
                note TEXT,
                linked_by_user_id INTEGER,
                linked_by_username TEXT,
                linked_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (linked_by_user_id) REFERENCES users(id)
            )
        ''')

        # Commit baseline schema before PostgreSQL migration blocks that may rollback.
        conn.commit()

        # Migration: Add telegram_chat_id to users table
        try:
            if self.db_type == 'postgresql':
                conn.rollback()
                cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_chat_id TEXT")
                conn.commit()
            else:
                cursor.execute("ALTER TABLE users ADD COLUMN telegram_chat_id TEXT")
                conn.commit()
        except Exception:
            if self.db_type == 'postgresql':
                conn.rollback()

        # Migration: Add incident owner columns
        try:
            if self.db_type == 'postgresql':
                conn.rollback()
                cursor.execute("ALTER TABLE incident_states ADD COLUMN IF NOT EXISTS owner_user_id INTEGER REFERENCES users(id)")
                cursor.execute("ALTER TABLE incident_states ADD COLUMN IF NOT EXISTS owner_username TEXT")
                conn.commit()
            else:
                cursor.execute("ALTER TABLE incident_states ADD COLUMN owner_user_id INTEGER")
                cursor.execute("ALTER TABLE incident_states ADD COLUMN owner_username TEXT")
                conn.commit()
        except Exception:
            if self.db_type == 'postgresql':
                conn.rollback()

        # Migration: Add anomaly owner columns
        try:
            if self.db_type == 'postgresql':
                conn.rollback()
                cursor.execute("ALTER TABLE anomaly_states ADD COLUMN IF NOT EXISTS owner_user_id INTEGER REFERENCES users(id)")
                cursor.execute("ALTER TABLE anomaly_states ADD COLUMN IF NOT EXISTS owner_username TEXT")
                conn.commit()
            else:
                cursor.execute("ALTER TABLE anomaly_states ADD COLUMN owner_user_id INTEGER")
                cursor.execute("ALTER TABLE anomaly_states ADD COLUMN owner_username TEXT")
                conn.commit()
        except Exception:
            if self.db_type == 'postgresql':
                conn.rollback()

        # Migration: Add auth_type column to users table
        try:
            if self.db_type == 'postgresql':
                conn.rollback()
                cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_type TEXT DEFAULT 'local'")
                conn.commit()
            else:
                cursor.execute("ALTER TABLE users ADD COLUMN auth_type TEXT DEFAULT 'local'")
                conn.commit()
        except Exception:
            if self.db_type == 'postgresql':
                conn.rollback()
            # Column likely exists

        # Migration: Add MFA columns to users table
        mfa_columns = [
            ('mfa_secret', 'TEXT'),
            ('mfa_enabled', f'{bool_type} DEFAULT {bool_default_false}'),
        ]
        for col_name, col_type in mfa_columns:
            try:
                if self.db_type == 'postgresql':
                    conn.rollback()
                    cursor.execute(f'ALTER TABLE users ADD COLUMN {col_name} {col_type}')
                    conn.commit()
                else:
                    cursor.execute(f'ALTER TABLE users ADD COLUMN {col_name} {col_type}')
            except Exception:
                if self.db_type == 'postgresql':
                    conn.rollback()
                # Column already exists — ignore

        # Dashboards table
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS dashboards (
                id {pk},
                name TEXT NOT NULL,
                description TEXT,
                layout_config TEXT,
                created_by INTEGER,
                is_public {bool_type} DEFAULT {bool_default_false},
                display_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (created_by) REFERENCES users (id)
            )
        ''')
        
        # Migration: Add display_order to dashboards if missing
        try:
            if self.db_type == 'postgresql':
                conn.rollback()
                cursor.execute('ALTER TABLE dashboards ADD COLUMN IF NOT EXISTS display_order INTEGER DEFAULT 0')
                conn.commit()
            else:
                cursor.execute('ALTER TABLE dashboards ADD COLUMN display_order INTEGER DEFAULT 0')
                conn.commit()
        except Exception:
            if self.db_type == 'postgresql':
                conn.rollback()
            # Column likely exists
        
        # Dashboard Templates table
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS dashboard_templates (
                id {pk},
                name TEXT NOT NULL,
                description TEXT,
                layout_config TEXT,
                variables TEXT,
                category TEXT DEFAULT 'custom',
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (created_by) REFERENCES users (id)
            )
        ''')
        
        # Sub-topologies table
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS sub_topologies (
                id {pk},
                name TEXT NOT NULL,
                description TEXT,
                created_by INTEGER,
                background_image TEXT,
                background_zoom INTEGER DEFAULT 100,
                node_positions TEXT,
                background_opacity INTEGER DEFAULT 100,
                theme_mode TEXT DEFAULT 'standard',
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        ''')

        # Migration: Add theme_mode
        try:
            if self.db_type == 'postgresql':
                conn.rollback()
                cursor.execute("ALTER TABLE sub_topologies ADD COLUMN IF NOT EXISTS theme_mode TEXT DEFAULT 'standard'")
                conn.commit()
            else:
                cursor.execute("ALTER TABLE sub_topologies ADD COLUMN theme_mode TEXT DEFAULT 'standard'")
                conn.commit()
        except Exception:
            if self.db_type == 'postgresql':
                conn.rollback()

        # LDAP settings table
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS ldap_settings (
                id {pk},
                setting_key TEXT UNIQUE NOT NULL,
                setting_value TEXT,
                updated_at TIMESTAMP DEFAULT {timestamp_default}
            )
        ''')

        # Default LDAP Settings
        default_ldap_settings = {
            'ldap_enabled': 'false',
            'ldap_server': '',
            'ldap_port': '389',
            'ldap_use_ssl': 'false',
            'ldap_base_dn': '',
            'ldap_bind_dn': '',
            'ldap_bind_password': '',
            'ldap_user_filter': '(sAMAccountName={username})',
            'ldap_auto_create': 'true',
            'ldap_default_role': 'viewer'
        }
        for k, v in default_ldap_settings.items():
            try:
                if self.db_type == 'postgresql':
                    cursor.execute(f'INSERT INTO ldap_settings (setting_key, setting_value) VALUES ({ph}, {ph}) ON CONFLICT (setting_key) DO NOTHING', (k, v))
                else:
                    cursor.execute(f'INSERT OR IGNORE INTO ldap_settings (setting_key, setting_value) VALUES (?, ?)', (k, v))
            except Exception:
                pass
        
        # Devices belonging to a sub-topology
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS sub_topology_devices (
                id {pk},
                sub_topology_id INTEGER NOT NULL,
                device_id INTEGER NOT NULL,
                FOREIGN KEY (sub_topology_id) REFERENCES sub_topologies(id) ON DELETE CASCADE,
                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
                UNIQUE(sub_topology_id, device_id)
            )
        ''')
        
        # Custom connections within a sub-topology
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS sub_topology_connections (
                id {pk},
                sub_topology_id INTEGER NOT NULL,
                device_id INTEGER NOT NULL,
                connected_to INTEGER NOT NULL,
                FOREIGN KEY (sub_topology_id) REFERENCES sub_topologies(id) ON DELETE CASCADE,
                FOREIGN KEY (device_id) REFERENCES devices(id),
                FOREIGN KEY (connected_to) REFERENCES devices(id)
            )
        ''')
        # Custom SNMP OIDs table
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS custom_oids (
                id {pk},
                device_id INTEGER NOT NULL,
                oid TEXT NOT NULL,
                name TEXT NOT NULL,
                unit TEXT DEFAULT '',
                last_value TEXT,
                last_checked TIMESTAMP,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
                UNIQUE(device_id, oid)
            )
        ''')
        
        # Job execution history table
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS job_history (
                id {pk},
                job_id TEXT NOT NULL,
                job_name TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                duration_seconds REAL,
                result_summary TEXT,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT {timestamp_default}
            )
        ''')
        
        # SNMP Traps table
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS snmp_traps (
                id {pk},
                source_ip TEXT NOT NULL,
                device_id INTEGER,
                device_name TEXT,
                trap_oid TEXT,
                trap_name TEXT,
                severity TEXT DEFAULT 'info',
                varbinds TEXT,
                raw_data TEXT,
                received_at TIMESTAMP DEFAULT {timestamp_default},
                acknowledged INTEGER DEFAULT 0
            )
        ''')
        
        # Syslog Messages table
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS syslog_messages (
                id {pk},
                source_ip TEXT NOT NULL,
                device_id INTEGER,
                device_name TEXT,
                facility INTEGER,
                severity INTEGER,
                program TEXT,
                message TEXT,
                received_at TIMESTAMP DEFAULT {timestamp_default}
            )
        ''')
        
        # Bandwidth History table -- SNMP interface counter samples
        bigint_type = 'BIGINT' if self.db_type == 'postgresql' else 'INTEGER'
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS bandwidth_history (
                id          {pk},
                device_id   INTEGER NOT NULL,
                if_index    INTEGER NOT NULL,
                if_name     TEXT,
                bytes_in    {bigint_type},
                bytes_out   {bigint_type},
                bps_in      REAL,
                bps_out     REAL,
                if_speed    {bigint_type},
                util_in     REAL,
                util_out    REAL,
                sampled_at  TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
            )
        ''')
        
        # System Metrics History table -- Agent (SSH/WinRM) performance samples
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS system_metrics_history (
                id          {pk},
                device_id   INTEGER NOT NULL,
                metric_type TEXT NOT NULL,
                value       REAL,
                timestamp   TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
            )
        ''')
        
        # Audit Logs table
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS audit_logs (
                id          {pk},
                user_id     INTEGER,
                username    TEXT NOT NULL,
                action      TEXT NOT NULL,
                category    TEXT NOT NULL,
                target_type TEXT,
                target_id   INTEGER,
                target_name TEXT,
                details     TEXT,
                ip_address  TEXT,
                created_at  TIMESTAMP DEFAULT {timestamp_default}
            )
        ''')
        
        # User-Device Assignments table for specific notifications
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS user_device_assignments (
                id {pk},
                user_id INTEGER NOT NULL,
                device_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
                UNIQUE(user_id, device_id)
            )
        ''')
        
        # Create default users if not exists
        from werkzeug.security import generate_password_hash
        
        ph = self._ph()
        
        # Default admin user (password: admin)
        cursor.execute(f'SELECT id FROM users WHERE username = {ph}', ('admin',))
        if not cursor.fetchone():
            cursor.execute(f'''
                INSERT INTO users (username, password_hash, role, display_name)
                VALUES ({self._ph(4)})
            ''', ('admin', generate_password_hash('admin'), 'admin', 'Administrator'))
        
        # Default operator user (password: operator)
        cursor.execute(f'SELECT id FROM users WHERE username = {ph}', ('operator',))
        if not cursor.fetchone():
            cursor.execute(f'''
                INSERT INTO users (username, password_hash, role, display_name)
                VALUES ({self._ph(4)})
            ''', ('operator', generate_password_hash('operator'), 'operator', 'Operator User'))
        
        # Default viewer user (password: viewer)
        cursor.execute(f'SELECT id FROM users WHERE username = {ph}', ('viewer',))
        if not cursor.fetchone():
            cursor.execute(f'''
                INSERT INTO users (username, password_hash, role, display_name)
                VALUES ({self._ph(4)})
            ''', ('viewer', generate_password_hash('viewer'), 'viewer', 'Viewer User'))
        
        # Custom Reports table
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS custom_reports (
                id {pk},
                name TEXT NOT NULL,
                description TEXT,
                schedule_type TEXT DEFAULT 'none',
                schedule_time TEXT,
                schedule_day TEXT,
                email_recipients TEXT,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        ''')
        
        # Custom Report Widgets table
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS custom_report_widgets (
                id {pk},
                report_id INTEGER NOT NULL,
                widget_type TEXT NOT NULL,
                widget_title TEXT,
                config TEXT,
                sort_order INTEGER DEFAULT 0,
                FOREIGN KEY (report_id) REFERENCES custom_reports(id) ON DELETE CASCADE
            )
        ''')

        # =========================================================================
        # Performance Indexes
        # =========================================================================
        
        # status_history indexes (critical for time-series queries)
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sh_checked_at ON status_history(checked_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sh_device_checked ON status_history(device_id, checked_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sh_device_status ON status_history(device_id, status, checked_at)')
        
        # alert_history indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ah_device_event ON alert_history(device_id, event_type, created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ah_created_at ON alert_history(created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_incident_states_status ON incident_states(status, updated_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_incident_activity_incident ON incident_activity(incident_id, created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_persistent_incidents_active ON persistent_incidents(is_active, latest_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_anomaly_snapshots_active ON anomaly_snapshots(is_active, detected_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_anomaly_states_status ON anomaly_states(status, updated_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_anomaly_activity_key ON anomaly_activity(anomaly_key, created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_anomaly_incident_links_incident ON anomaly_incident_links(incident_id, updated_at)')
        
        # devices indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_devices_type ON devices(device_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_devices_status ON devices(status)')
        
        # bandwidth_history indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_bw_device_sampled ON bandwidth_history(device_id, sampled_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_bw_sampled_at ON bandwidth_history(sampled_at)')
        
        # system_metrics_history indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_smh_device_sampled ON system_metrics_history(device_id, timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_smh_timestamp ON system_metrics_history(timestamp)')
        
        # audit_logs indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_logs(created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(username, created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_category ON audit_logs(category, created_at)')
        
        conn.commit()
        self.release_connection(conn)
    
    def add_device(self, name, ip_address, device_type=None, location=None, 
                   monitor_type='ping', expected_status_code=200,
                   snmp_community='public', snmp_port=161, snmp_version='2c',
                   snmp_v3_username=None, snmp_v3_auth_protocol='SHA',
                   snmp_v3_auth_password=None, snmp_v3_priv_protocol='AES128',
                   snmp_v3_priv_password=None,
                   tcp_port=80, dns_query_domain='google.com', location_type='on-premise',
                   latitude=None, longitude=None, is_enabled=True, parent_device_id=None,
                   ssh_username=None, ssh_password=None, ssh_port=22,
                   wmi_username=None, wmi_password=None, expected_ports=None,
                   plugin_config_json=None):
        """Add a new device"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        
        # Strip whitespace from IP address to prevent ping failures
        ip_address = ip_address.strip() if ip_address else ip_address
        name = name.strip() if name else name
        
        try:
            if self.db_type == 'postgresql':
                status_init = 'disabled' if not is_enabled else 'unknown'
                cursor.execute('''
                    INSERT INTO devices (name, ip_address, device_type, location, 
                                       status, monitor_type, expected_status_code,
                                       snmp_community, snmp_port, snmp_version,
                                       snmp_v3_username, snmp_v3_auth_protocol,
                                       snmp_v3_auth_password, snmp_v3_priv_protocol,
                                       snmp_v3_priv_password,
                                       tcp_port, dns_query_domain, location_type,
                                       latitude, longitude, is_enabled, parent_device_id,
                                       ssh_username, ssh_password, ssh_port,
                                       wmi_username, wmi_password, expected_ports, plugin_config_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                ''', (name, ip_address, device_type or Config.DEFAULT_DEVICE_TYPE, 
                      location or Config.DEFAULT_LOCATION, status_init, monitor_type, expected_status_code,
                      snmp_community, snmp_port, snmp_version,
                      snmp_v3_username, snmp_v3_auth_protocol,
                      snmp_v3_auth_password, snmp_v3_priv_protocol,
                      snmp_v3_priv_password,
                      tcp_port, dns_query_domain,
                      location_type or Config.DEFAULT_LOCATION_TYPE,
                      latitude, longitude, is_enabled, parent_device_id,
                      ssh_username, ssh_password, ssh_port,
                      wmi_username, wmi_password, expected_ports, plugin_config_json))
                device_id = cursor.fetchone()['id']
            else:
                status_init = 'disabled' if not is_enabled else 'unknown'
                cursor.execute('''
                    INSERT INTO devices (name, ip_address, device_type, location, 
                                       status, monitor_type, expected_status_code,
                                       snmp_community, snmp_port, snmp_version,
                                       snmp_v3_username, snmp_v3_auth_protocol,
                                       snmp_v3_auth_password, snmp_v3_priv_protocol,
                                       snmp_v3_priv_password,
                                       tcp_port, dns_query_domain, location_type,
                                       latitude, longitude, is_enabled, parent_device_id,
                                       ssh_username, ssh_password, ssh_port,
                                       wmi_username, wmi_password, expected_ports, plugin_config_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (name, ip_address, device_type or Config.DEFAULT_DEVICE_TYPE, 
                      location or Config.DEFAULT_LOCATION, status_init, monitor_type, expected_status_code,
                      snmp_community, snmp_port, snmp_version,
                      snmp_v3_username, snmp_v3_auth_protocol,
                      snmp_v3_auth_password, snmp_v3_priv_protocol,
                      snmp_v3_priv_password,
                      tcp_port, dns_query_domain,
                      location_type or Config.DEFAULT_LOCATION_TYPE,
                      latitude, longitude, 1 if is_enabled else 0, parent_device_id,
                      ssh_username, ssh_password, ssh_port,
                      wmi_username, wmi_password, expected_ports, plugin_config_json))
                device_id = cursor.lastrowid
            conn.commit()
            return {'success': True, 'id': device_id}
        except (sqlite3.IntegrityError, Exception) as e:
            if conn: conn.rollback()
            if 'unique' in str(e).lower() or 'duplicate' in str(e).lower() or 'UNIQUE constraint' in str(e):
                return {'success': False, 'error': 'Device with this IP/URL, monitor type, and device type already exists'}
            return {'success': False, 'error': str(e)}
        finally:
            self.release_connection(conn)
    
    def get_all_devices(self):
        """Get all devices"""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            cursor.execute('SELECT * FROM devices ORDER BY id')
            devices = self._rows_to_dicts(cursor.fetchall())
            return devices
        finally:
            self.release_connection(conn)
    
    def get_device(self, device_id):
        """Get a specific device"""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            cursor.execute(f'SELECT * FROM devices WHERE id = {self._ph()}', (device_id,))
            device = cursor.fetchone()
            return self._row_to_dict(device)
        finally:
            self.release_connection(conn)
    
    def update_device(self, device_id, name=None, ip_address=None, 
                     device_type=None, location='__NOT_SET__', monitor_type=None,
                     snmp_community=None, snmp_port=None, snmp_version=None,
                     snmp_v3_username=None, snmp_v3_auth_protocol=None,
                     snmp_v3_auth_password=None, snmp_v3_priv_protocol=None,
                     snmp_v3_priv_password=None,
                     tcp_port=None, dns_query_domain=None, location_type=None,
                     latitude='__NOT_SET__', longitude='__NOT_SET__', is_enabled=None,
                     parent_device_id='__NOT_SET__',
                     ssh_username='__NOT_SET__', ssh_password='__NOT_SET__', 
                     ssh_port='__NOT_SET__',
                     wmi_username='__NOT_SET__', wmi_password='__NOT_SET__', expected_ports='__NOT_SET__',
                     plugin_config_json='__NOT_SET__'):
        """Update device information"""
        # Strip whitespace from IP address and name
        if ip_address:
            ip_address = ip_address.strip()
        if name:
            name = name.strip()
        if isinstance(location, str) and location != '__NOT_SET__':
            location = location.strip()
        
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            ph = self._ph()
            
            updates = []
            params = []
            
            if name:
                updates.append(f'name = {ph}')
                params.append(name)
            if ip_address:
                updates.append(f'ip_address = {ph}')
                params.append(ip_address)
            if device_type:
                updates.append(f'device_type = {ph}')
                params.append(device_type)
            if location != '__NOT_SET__':
                updates.append(f'location = {ph}')
                params.append(location)
            if monitor_type:
                updates.append(f'monitor_type = {ph}')
                params.append(monitor_type)
            if snmp_community:
                updates.append(f'snmp_community = {ph}')
                params.append(snmp_community)
            if snmp_port is not None:
                updates.append(f'snmp_port = {ph}')
                params.append(snmp_port)
            if snmp_version:
                updates.append(f'snmp_version = {ph}')
                params.append(snmp_version)
            if snmp_v3_username is not None:
                updates.append(f'snmp_v3_username = {ph}')
                params.append(snmp_v3_username)
            if snmp_v3_auth_protocol is not None:
                updates.append(f'snmp_v3_auth_protocol = {ph}')
                params.append(snmp_v3_auth_protocol)
            if snmp_v3_auth_password is not None:
                updates.append(f'snmp_v3_auth_password = {ph}')
                params.append(snmp_v3_auth_password)
            if snmp_v3_priv_protocol is not None:
                updates.append(f'snmp_v3_priv_protocol = {ph}')
                params.append(snmp_v3_priv_protocol)
            if snmp_v3_priv_password is not None:
                updates.append(f'snmp_v3_priv_password = {ph}')
                params.append(snmp_v3_priv_password)
            if tcp_port is not None:
                updates.append(f'tcp_port = {ph}')
                params.append(tcp_port)
            if dns_query_domain:
                updates.append(f'dns_query_domain = {ph}')
                params.append(dns_query_domain)
            if location_type:
                updates.append(f'location_type = {ph}')
                params.append(location_type)
            if latitude != '__NOT_SET__':
                updates.append(f'latitude = {ph}')
                params.append(latitude)
            if longitude != '__NOT_SET__':
                updates.append(f'longitude = {ph}')
                params.append(longitude)
            
            # SSH and WMI fields
            if ssh_username != '__NOT_SET__':
                updates.append(f'ssh_username = {ph}')
                params.append(ssh_username)
            if ssh_password != '__NOT_SET__':
                updates.append(f'ssh_password = {ph}')
                params.append(ssh_password)
            if ssh_port != '__NOT_SET__':
                updates.append(f'ssh_port = {ph}')
                params.append(ssh_port)
            if wmi_username != '__NOT_SET__':
                updates.append(f'wmi_username = {ph}')
                params.append(wmi_username)
            if wmi_password != '__NOT_SET__':
                updates.append(f'wmi_password = {ph}')
                params.append(wmi_password)
            if expected_ports != '__NOT_SET__':
                updates.append(f'expected_ports = {ph}')
                params.append(expected_ports)
            if plugin_config_json != '__NOT_SET__':
                updates.append(f'plugin_config_json = {ph}')
                params.append(plugin_config_json)
            
            if is_enabled is not None:
                updates.append(f'is_enabled = {ph}')
                if self.db_type == 'postgresql':
                    params.append(is_enabled)
                else:
                    params.append(1 if is_enabled else 0)
                
                # Update status and reset response time when toggled via modal
                updates.append(f"status = {ph}")
                params.append('disabled' if not is_enabled else 'unknown')
                updates.append("response_time = NULL")
            
            # parent_device_id uses sentinel value to distinguish "not provided" from "set to None"
            if parent_device_id != '__NOT_SET__':
                updates.append(f'parent_device_id = {ph}')
                params.append(parent_device_id)
            
            if updates:
                params.append(device_id)
                query = f"UPDATE devices SET {', '.join(updates)} WHERE id = {ph}"
                cursor.execute(query, params)
                conn.commit()
            
            return {'success': True}
        except Exception as e:
            if conn: conn.rollback()
            return {'success': False, 'error': str(e)}
        finally:
            self.release_connection(conn)
            
    def update_system_metrics(self, device_id, cpu=None, ram=None, disk=None, 
                             network_in=None, network_out=None, raw_in=None, raw_out=None):
        """Update current system metrics for a device and add to historical data"""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            ph = self._ph()
            
            # Update current metrics in devices table
            updates = []
            params = []
            if cpu is not None:
                updates.append(f"cpu_usage = {ph}")
                params.append(cpu)
            if ram is not None:
                updates.append(f"ram_usage = {ph}")
                params.append(ram)
            if disk is not None:
                updates.append(f"disk_usage = {ph}")
                params.append(disk)
            if network_in is not None:
                updates.append(f"network_in_bps = {ph}")
                params.append(network_in)
            if network_out is not None:
                updates.append(f"network_out_bps = {ph}")
                params.append(network_out)
            if raw_in is not None:
                updates.append(f"last_network_in = {ph}")
                params.append(raw_in)
            if raw_out is not None:
                updates.append(f"last_network_out = {ph}")
                params.append(raw_out)
            
            if updates:
                # Always update last_metrics_time when any metric is updated
                updates.append(f"last_metrics_time = CURRENT_TIMESTAMP")
                
                params.append(device_id)
                query = f"UPDATE devices SET {', '.join(updates)} WHERE id = {ph}"
                cursor.execute(query, params)
                
                # Add to history
                if cpu is not None:
                    cursor.execute(f"INSERT INTO system_metrics_history (device_id, metric_type, value) VALUES ({self._ph(3)})", (device_id, 'cpu', cpu))
                if ram is not None:
                    cursor.execute(f"INSERT INTO system_metrics_history (device_id, metric_type, value) VALUES ({self._ph(3)})", (device_id, 'ram', ram))
                if disk is not None:
                    cursor.execute(f"INSERT INTO system_metrics_history (device_id, metric_type, value) VALUES ({self._ph(3)})", (device_id, 'disk', disk))
                if network_in is not None:
                    cursor.execute(f"INSERT INTO system_metrics_history (device_id, metric_type, value) VALUES ({self._ph(3)})", (device_id, 'network_in', network_in))
                if network_out is not None:
                    cursor.execute(f"INSERT INTO system_metrics_history (device_id, metric_type, value) VALUES ({self._ph(3)})", (device_id, 'network_out', network_out))
                
                conn.commit()
            return True
        except Exception as e:
            if conn: conn.rollback()
            print(f"[DB ERROR] update_system_metrics: {e}")
            return False
        finally:
            self.release_connection(conn)

    def get_system_metrics_history(self, device_id, metric_type, hours=24):
        """Get system metrics history for a device"""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            ph = self._ph()
            
            if self.db_type == 'postgresql':
                query = f"""
                    SELECT value, timestamp 
                    FROM system_metrics_history 
                    WHERE device_id = {ph} AND metric_type = {ph} 
                    AND timestamp >= NOW() - INTERVAL '{hours} hours'
                    ORDER BY timestamp ASC
                """
            else:
                query = f"""
                    SELECT value, timestamp 
                    FROM system_metrics_history 
                    WHERE device_id = {ph} AND metric_type = {ph} 
                    AND timestamp >= datetime('now', '-{hours} hours')
                    ORDER BY timestamp ASC
                """
            
            cursor.execute(query, (device_id, metric_type))
            return self._rows_to_dicts(cursor.fetchall())
        except Exception as e:
            print(f"[DB ERROR] get_system_metrics_history: {e}")
            return []
        finally:
            self.release_connection(conn)
            
    # =========================================================================
    # Alert Dependencies — Helper Functions
    # =========================================================================
    
    def is_parent_device_down(self, device_id):
        """Check if any ancestor device is currently down (walk up dependency chain).
        Returns the first down parent device dict, or None if all parents are up."""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            visited = set()
            current_id = device_id
            
            while current_id and current_id not in visited:
                visited.add(current_id)
                cursor.execute(
                    f'SELECT parent_device_id FROM devices WHERE id = {self._ph()}',
                    (current_id,)
                )
                row = cursor.fetchone()
                if not row:
                    break
                
                parent_id = row['parent_device_id'] if isinstance(row, dict) else row[0]
                if not parent_id:
                    break
                
                # Check if parent is down
                cursor.execute(
                    f'SELECT id, name, ip_address, status FROM devices WHERE id = {self._ph()}',
                    (parent_id,)
                )
                parent = cursor.fetchone()
                if parent:
                    parent_dict = self._row_to_dict(parent)
                    if parent_dict.get('status') == 'down':
                        return parent_dict
                
                current_id = parent_id
            
            return None
        finally:
            self.release_connection(conn)
    
    def get_child_devices(self, device_id):
        """Get all devices whose parent_device_id equals this device (direct children only)"""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            cursor.execute(
                f'SELECT * FROM devices WHERE parent_device_id = {self._ph()}',
                (device_id,)
            )
            return self._rows_to_dicts(cursor.fetchall())
        finally:
            self.release_connection(conn)
    
    def count_downstream_devices(self, device_id):
        """Count all downstream devices (recursive children)"""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            count = 0
            queue = [device_id]
            visited = set()
            
            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                
                cursor.execute(
                    f'SELECT id FROM devices WHERE parent_device_id = {self._ph()}',
                    (current,)
                )
                children = cursor.fetchall()
                for child in children:
                    child_id = child['id'] if isinstance(child, dict) else child[0]
                    if child_id not in visited:
                        count += 1
                        queue.append(child_id)
            
            return count
        finally:
            self.release_connection(conn)
    
    def get_dependency_info(self, device_id):
        """Get parent device name for a given device"""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            cursor.execute(
                f'''SELECT p.id, p.name, p.ip_address, p.status 
                    FROM devices d 
                    JOIN devices p ON d.parent_device_id = p.id 
                    WHERE d.id = {self._ph()}''',
                (device_id,)
            )
            row = cursor.fetchone()
            return self._row_to_dict(row) if row else None
        finally:
            self.release_connection(conn)
    
    def toggle_device_monitoring(self, device_id):
        """Toggle the is_enabled status of a device"""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            ph = self._ph()
            
            # Get current status
            cursor.execute(f'SELECT is_enabled, name FROM devices WHERE id = {ph}', (device_id,))
            device = cursor.fetchone()
            if not device:
                return {'success': False, 'error': 'Device not found'}
            
            new_status = not bool(device['is_enabled'])
            
            # When disabling, set status to 'disabled'
            # When enabling, set status to 'unknown' to trigger re-check
            status_update = 'disabled' if not new_status else 'unknown'
            
            if self.db_type == 'postgresql':
                cursor.execute(f'''
                    UPDATE devices 
                    SET is_enabled = %s, status = %s, response_time = NULL 
                    WHERE id = %s
                ''', (new_status, status_update, device_id))
            else:
                cursor.execute(f'''
                    UPDATE devices 
                    SET is_enabled = ?, status = ?, response_time = NULL 
                    WHERE id = ?
                ''', (1 if new_status else 0, status_update, device_id))
                
            conn.commit()
            return {
                'success': True, 
                'is_enabled': new_status, 
                'name': device['name'],
                'status': status_update
            }
        except Exception as e:
            if conn: conn.rollback()
            return {'success': False, 'error': str(e)}
        finally:
            self.release_connection(conn)
    
    def delete_device(self, device_id):
        """Delete a device and all its associated data"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        
        try:
            # 1. Delete from child tables first to avoid FK constraints
            # Topology
            cursor.execute(f'DELETE FROM topology WHERE device_id = {ph} OR connected_to = {ph}', (device_id, device_id))
            
            # History
            cursor.execute(f'DELETE FROM status_history WHERE device_id = {ph}', (device_id,))
            cursor.execute(f'DELETE FROM alert_history WHERE device_id = {ph}', (device_id,))
            
            # Sub-topology references
            cursor.execute(f'DELETE FROM sub_topology_devices WHERE device_id = {ph}', (device_id,))
            cursor.execute(f'DELETE FROM sub_topology_connections WHERE device_id = {ph} OR connected_to = {ph}', (device_id, device_id))
            
            # Maintenance windows
            cursor.execute(f'DELETE FROM maintenance_windows WHERE device_id = {ph}', (device_id,))
            
            # Traps and Syslog (optional relations)
            cursor.execute(f'DELETE FROM snmp_traps WHERE device_id = {ph}', (device_id,))
            cursor.execute(f'DELETE FROM syslog_messages WHERE device_id = {ph}', (device_id,))
            
            # 2. Finally delete the device itself
            # Note: custom_oids and bandwidth_history have ON DELETE CASCADE, 
            # so they will be handled automatically by the DB.
            cursor.execute(f'DELETE FROM devices WHERE id = {ph}', (device_id,))
            
            conn.commit()
            return {'success': True}
        except Exception as e:
            conn.rollback()
            print(f"Error deleting device {device_id}: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            self.release_connection(conn)
    
    def update_device_status(self, device_id, status, response_time=None, http_status_code=None,
                             snmp_uptime=None, snmp_sysname=None, snmp_sysdescr=None,
                             snmp_syslocation=None, snmp_syscontact=None,
                             ssl_expiry_date=None, ssl_days_left=None, ssl_issuer=None, ssl_status=None):
        """Update device status"""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            ph = self._ph()
            
            now = datetime.now().isoformat()
            
            # Get old status, escalation level and enabled state to detect changes accurately
            cursor.execute(f'SELECT status, escalation_level, is_enabled FROM devices WHERE id = {ph}', (device_id,))
            current_row = cursor.fetchone()
            if current_row:
                old_status = current_row['status']
                old_escalation_level = current_row.get('escalation_level', 0)
                is_enabled = bool(current_row.get('is_enabled', True))
            else:
                old_status = 'unknown'
                old_escalation_level = 0
                is_enabled = True
            
            # Force status to 'disabled' if device is disabled
            if not is_enabled:
                status = 'disabled'
                response_time = None
                http_status_code = None
            
            # Build update query dynamically based on provided values
            update_parts = [f'status = {ph}', f'response_time = {ph}', f'last_check = {ph}', f'http_status_code = {ph}']
            params = [status, response_time, now, http_status_code]
            
            # Reset escalation track and record the state timestamp if device status transitioned
            if status != old_status:
                update_parts.append(f'last_status_change = {ph}')
                params.append(now)
                update_parts.append(f'escalation_level = {ph}')
                params.append(0)
            
            if snmp_uptime is not None:
                update_parts.append(f'snmp_uptime = {ph}')
                params.append(snmp_uptime)
            if snmp_sysname is not None:
                update_parts.append(f'snmp_sysname = {ph}')
                params.append(snmp_sysname)
            if snmp_sysdescr is not None:
                update_parts.append(f'snmp_sysdescr = {ph}')
                params.append(snmp_sysdescr)
            if snmp_syslocation is not None:
                update_parts.append(f'snmp_syslocation = {ph}')
                params.append(snmp_syslocation)
            if snmp_syscontact is not None:
                update_parts.append(f'snmp_syscontact = {ph}')
                params.append(snmp_syscontact)
            if ssl_expiry_date is not None:
                update_parts.append(f'ssl_expiry_date = {ph}')
                params.append(ssl_expiry_date)
            if ssl_days_left is not None:
                update_parts.append(f'ssl_days_left = {ph}')
                params.append(ssl_days_left)
            if ssl_issuer is not None:
                update_parts.append(f'ssl_issuer = {ph}')
                params.append(ssl_issuer)
            if ssl_status is not None:
                update_parts.append(f'ssl_status = {ph}')
                params.append(ssl_status)
            
            params.append(device_id)
            
            cursor.execute(f'''
                UPDATE devices 
                SET {', '.join(update_parts)}
                WHERE id = {ph}
            ''', params)
            
            # Log to history
            cursor.execute(f'''
                INSERT INTO status_history (device_id, status, response_time, checked_at)
                VALUES ({self._ph(4)})
            ''', (device_id, status, response_time, now))
            
            conn.commit()
            
            return {
                'old_status': old_status,
                'old_escalation_level': old_escalation_level,
                'new_status': status
            }
        except Exception as e:
            if conn: conn.rollback()
            raise e
        finally:
            self.release_connection(conn)
    
    def get_topology(self):
        """Get topology connections"""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            cursor.execute('SELECT * FROM topology')
            topology = self._rows_to_dicts(cursor.fetchall())
            return topology
        finally:
            self.release_connection(conn)
    
    def add_topology_connection(self, device_id, connected_to, view_type='standard'):
        """Add a topology connection"""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            ph = self._ph()
            
            # Check if connection already exists in this view
            cursor.execute(f'''
                SELECT id FROM topology 
                WHERE ((device_id = {ph} AND connected_to = {ph}) 
                   OR (device_id = {ph} AND connected_to = {ph}))
                   AND (view_type = {ph} OR view_type IS NULL)
            ''', (device_id, connected_to, connected_to, device_id, view_type))
            
            if cursor.fetchone():
                return {'success': False, 'error': 'Connection already exists in this view'}
            
            if self.db_type == 'postgresql':
                cursor.execute(f'''
                    INSERT INTO topology (device_id, connected_to, view_type)
                    VALUES ({self._ph(3)})
                    RETURNING id
                ''', (device_id, connected_to, view_type))
                connection_id = cursor.fetchone()['id']
            else:
                cursor.execute(f'''
                    INSERT INTO topology (device_id, connected_to, view_type)
                    VALuES ({self._ph(3)})
                ''', (device_id, connected_to, view_type))
                connection_id = cursor.lastrowid
            conn.commit()
            return {'success': True, 'id': connection_id}
        except Exception as e:
            if conn: conn.rollback()
            return {'success': False, 'error': str(e)}
        finally:
            self.release_connection(conn)
    
    def delete_topology_connection(self, connection_id=None, device_id=None, connected_to=None):
        """Delete a topology connection by ID or by device pair"""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            ph = self._ph()
            
            if connection_id:
                cursor.execute(f'DELETE FROM topology WHERE id = {ph}', (connection_id,))
            elif device_id and connected_to:
                cursor.execute(f'''
                    DELETE FROM topology 
                    WHERE (device_id = {ph} AND connected_to = {ph}) 
                       OR (device_id = {ph} AND connected_to = {ph})
                ''', (device_id, connected_to, connected_to, device_id))
            else:
                return {'success': False, 'error': 'Must provide connection_id or both device_id and connected_to'}
            
            conn.commit()
            return {'success': True}
        except Exception as e:
            if conn: conn.rollback()
            return {'success': False, 'error': str(e)}
        finally:
            self.release_connection(conn)
    
    def get_device_history(self, device_id, limit=100, minutes=None, sample_count=None):
        """Get status history for a device, optionally sampled and padded into N points"""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            ph = self._ph()
            
            if sample_count and minutes:
                # Time-bucket sampling logic
                sample_count = int(sample_count)
                minutes = int(minutes)
                bucket_size_sec = max(1, (minutes * 60) / sample_count)
                
                if self.db_type == 'postgresql':
                    time_group = "FLOOR(EXTRACT(EPOCH FROM h.checked_at::timestamp) / %d)" % bucket_size_sec
                    time_select = "to_char(MIN(h.checked_at::timestamp), 'YYYY-MM-DD HH24:MI:SS')"
                    time_filter = "NOW() - INTERVAL '%d minutes'" % minutes
                else:
                    time_group = "CAST(strftime('%%s', h.checked_at) / %d AS INTEGER)" % bucket_size_sec
                    time_select = "datetime(MIN(h.checked_at))"
                    time_filter = "datetime('now', '-%d minutes')" % minutes
                    
                query = f'''
                    SELECT 
                        {time_select} as checked_at,
                        AVG(response_time) as response_time,
                        {time_group} as bucket_id
                    FROM status_history h
                    WHERE device_id = {ph} 
                    AND checked_at >= {time_filter}
                    GROUP BY {time_group}
                    ORDER BY checked_at DESC
                '''
                import calendar
                now_naive = datetime.now()  # local wall-clock time, no tzinfo
                now_ts = int(calendar.timegm(now_naive.timetuple()))  # treat as UTC, matching SQL
                current_bucket_id = int(now_ts / bucket_size_sec)
                start_bucket_id = current_bucket_id - sample_count + 1
                
                query = f'''
                    SELECT 
                        {time_select} as checked_at,
                        AVG(response_time) as response_time,
                        {time_group} as bucket_id
                    FROM status_history h
                    WHERE device_id = {ph} 
                    AND checked_at >= {time_filter}
                    GROUP BY {time_group}
                    ORDER BY bucket_id ASC
                '''
                cursor.execute(query, (device_id,))
                raw_sampled = self._rows_to_dicts(cursor.fetchall())
                
                # Map existing data to buckets
                data_map = {int(row['bucket_id']): row for row in raw_sampled}
                
                padded_history = []
                for b_id in range(start_bucket_id, current_bucket_id + 1):
                    if b_id in data_map:
                        row = data_map[b_id]
                        padded_history.append({
                            'checked_at': row['checked_at'],
                            'response_time': row['response_time'],
                            'status': 'up' if row['response_time'] is not None else 'down'
                        })
                    else:
                        bucket_start_ts = b_id * bucket_size_sec
                        bucket_time = datetime.utcfromtimestamp(bucket_start_ts).isoformat()
                        padded_history.append({
                            'checked_at': bucket_time,
                            'response_time': None,
                            'status': 'unknown'
                        })
                
                return padded_history
            
            # Standard raw history
            where_clause = f"WHERE device_id = {ph}"
            params = [device_id]
            
            if minutes:
                if self.db_type == 'postgresql':
                    where_clause += " AND checked_at >= NOW() - INTERVAL '%s minutes'" % int(minutes)
                else:
                    where_clause += " AND checked_at >= datetime('now', '-%d minutes')" % int(minutes)
                
            cursor.execute(f'''
                SELECT * FROM status_history 
                {where_clause}
                ORDER BY checked_at DESC 
                LIMIT {ph}
            ''', (*params, limit))
                
            history = self._rows_to_dicts(cursor.fetchall())
            return history
        finally:
            self.release_connection(conn)
    
    def get_historical_data(self, start_date=None, end_date=None, device_id=None, device_type=None):
        """Get historical data with optional filters"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        
        query = '''
            SELECT h.*, d.name, d.ip_address, d.device_type, d.location
            FROM status_history h
            JOIN devices d ON h.device_id = d.id
            WHERE 1=1
        '''
        params = []
        
        if start_date:
            query += f' AND h.checked_at >= {ph}'
            params.append(start_date)
        if end_date:
            query += f' AND h.checked_at <= {ph}'
            params.append(end_date)
        if device_id:
            query += f' AND h.device_id = {ph}'
            params.append(device_id)
        if device_type:
            query += f' AND d.device_type = {ph}'
            params.append(device_type)
        
        query += ' ORDER BY h.checked_at ASC'
        
        cursor.execute(query, params)
        history = self._rows_to_dicts(cursor.fetchall())
        self.release_connection(conn)
        return history
    
    def get_historical_data_multi(self, start_date=None, end_date=None, device_ids=None):
        """Get historical data for multiple devices"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        
        query = '''
            SELECT h.*, d.name, d.ip_address, d.device_type, d.location
            FROM status_history h
            JOIN devices d ON h.device_id = d.id
            WHERE 1=1
        '''
        params = []
        
        if start_date:
            query += f' AND h.checked_at >= {ph}'
            params.append(start_date)
        if end_date:
            query += f' AND h.checked_at <= {ph}'
            params.append(end_date)
        if device_ids and len(device_ids) > 0:
            placeholders = ','.join([ph for _ in device_ids])
            query += f' AND h.device_id IN ({placeholders})'
            params.extend(device_ids)
        
        query += ' ORDER BY h.checked_at ASC'
        
        cursor.execute(query, params)
        history = self._rows_to_dicts(cursor.fetchall())
        self.release_connection(conn)
        return history
    
    def get_aggregated_stats(self, start_date=None, end_date=None):
        """Get aggregated statistics for a time period"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        
        query = '''
            SELECT 
                d.device_type,
                COUNT(DISTINCT h.device_id) as device_count,
                AVG(CASE WHEN h.response_time IS NOT NULL THEN h.response_time END) as avg_response_time,
                MIN(CASE WHEN h.response_time IS NOT NULL THEN h.response_time END) as min_response_time,
                MAX(CASE WHEN h.response_time IS NOT NULL THEN h.response_time END) as max_response_time,
                SUM(CASE WHEN h.status = 'up' THEN 1 ELSE 0 END) as up_count,
                SUM(CASE WHEN h.status = 'slow' THEN 1 ELSE 0 END) as slow_count,
                SUM(CASE WHEN h.status = 'down' THEN 1 ELSE 0 END) as down_count,
                COUNT(*) as total_checks
            FROM status_history h
            JOIN devices d ON h.device_id = d.id
            WHERE 1=1
        '''
        params = []
        
        if start_date:
            query += f' AND h.checked_at >= {ph}'
            params.append(start_date)
        if end_date:
            query += f' AND h.checked_at <= {ph}'
            params.append(end_date)
        
        query += ' GROUP BY d.device_type'
        
        cursor.execute(query, params)
        stats = self._rows_to_dicts(cursor.fetchall())
        self.release_connection(conn)
        return stats
    
    def get_device_type_trends(self, minutes=180, device_id=None):
        """Get average response time trends by device type or specific device"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        
        # Calculate start time
        start_time = (datetime.now() - timedelta(minutes=minutes)).isoformat()
        
        if self.db_type == 'postgresql':
            if minutes <= 10:
                time_group = "FLOOR(EXTRACT(EPOCH FROM h.checked_at::timestamp) / 30)"
                time_select = "to_char(MIN(h.checked_at::timestamp), 'YYYY-MM-DD HH24:MI:SS')"
            else:
                time_group = "to_char(h.checked_at::timestamp, 'YYYY-MM-DD HH24:MI')"
                time_select = "to_char(h.checked_at::timestamp, 'YYYY-MM-DD HH24:MI')"
        else:
            if minutes <= 10:
                time_group = "CAST(strftime('%s', h.checked_at) / 30 AS INTEGER)"
                time_select = "datetime(MIN(h.checked_at))"
            else:
                time_group = "strftime('%Y-%m-%d %H:%M', h.checked_at)"
                time_select = "strftime('%Y-%m-%d %H:%M', h.checked_at)"

        where_clause = f"WHERE h.checked_at >= {ph} AND h.response_time IS NOT NULL AND h.status IN ('up', 'slow')"
        params = [start_time]
        
        if device_id:
            where_clause += f" AND h.device_id = {ph}"
            params.append(device_id)

        query = f'''
            SELECT 
                d.device_type,
                d.name as device_name,
                d.id as device_id,
                {time_select} as timestamp,
                AVG(h.response_time) as avg_response_time
            FROM status_history h
            JOIN devices d ON h.device_id = d.id
            {where_clause}
            GROUP BY d.device_type, d.name, d.id, {time_group}
            ORDER BY timestamp ASC
        '''
        
        cursor.execute(query, tuple(params))
        results = self._rows_to_dicts(cursor.fetchall())
        self.release_connection(conn)
        return results

    # =========================================================================
    # Alert Settings Methods
    # =========================================================================
    
    def save_alert_setting(self, key, value):
        """Save or update an alert setting"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        
        if self.db_type == 'postgresql':
            cursor.execute('''
                INSERT INTO alert_settings (setting_key, setting_value, updated_at)
                VALUES (%s, %s, %s)
                ON CONFLICT(setting_key) DO UPDATE SET 
                    setting_value = EXCLUDED.setting_value,
                    updated_at = EXCLUDED.updated_at
            ''', (key, value, datetime.now().isoformat()))
        else:
            cursor.execute('''
                INSERT INTO alert_settings (setting_key, setting_value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(setting_key) DO UPDATE SET 
                    setting_value = excluded.setting_value,
                    updated_at = excluded.updated_at
            ''', (key, value, datetime.now().isoformat()))
        
        conn.commit()
        self.release_connection(conn)
        return {'success': True}
    
    def get_alert_setting(self, key):
        """Get a single alert setting"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute(f'SELECT setting_value FROM alert_settings WHERE setting_key = {self._ph()}', (key,))
        result = cursor.fetchone()
        self.release_connection(conn)
        if result is None:
            return None
        r = self._row_to_dict(result)
        return r['setting_value'] if r else None
    
    def get_all_alert_settings(self):
        """Get all alert settings"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute('SELECT setting_key, setting_value FROM alert_settings')
        settings = self._rows_to_dicts(cursor.fetchall())
        self.release_connection(conn)
        return settings
    
    def log_alert(self, device_id, event_type, message, channel, status, error=None):
        """Log an alert to history"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        
        cursor.execute(f'''
            INSERT INTO alert_history (device_id, event_type, message, channel, status, error_message, created_at)
            VALUES ({self._ph(7)})
        ''', (device_id, event_type, message, channel, status, error, datetime.now().isoformat()))
        
        conn.commit()
        self.release_connection(conn)
    
    def get_last_alert_time(self, device_id, event_type):
        """Get the last alert time for a device and event type (for cooldown)"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        cursor.execute(f'''
            SELECT created_at FROM alert_history 
            WHERE device_id = {ph} AND event_type = {ph} AND status = 'sent'
            ORDER BY created_at DESC LIMIT 1
        ''', (device_id, event_type))
        result = cursor.fetchone()
        self.release_connection(conn)
        if result is None:
            return None
        r = self._row_to_dict(result)
        return r['created_at'] if r else None
    
    def get_alert_history(self, limit=100):
        """Get alert history with device info"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute(f'''
            SELECT ah.*, d.name as device_name, d.ip_address
            FROM alert_history ah
            LEFT JOIN devices d ON ah.device_id = d.id
            ORDER BY ah.created_at DESC
            LIMIT {self._ph()}
        ''', (limit,))
        history = self._rows_to_dicts(cursor.fetchall())
        self.release_connection(conn)
        return history

    def get_alert_incidents(self, limit=200, window_minutes=10, dedupe_minutes=2):
        """
        Correlate recent alert history into incident groups.

        MVP correlation rules:
        - Deduplicate multi-channel alert sends for the same device/event in a short window
        - Group alerts that happen close in time and are related by:
          - same device
          - direct parent/child dependency
          - topology connection
        """
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            ph = self._ph()

            cursor.execute(f'''
                SELECT ah.*, d.name as device_name, d.ip_address, d.location, d.device_type,
                       d.parent_device_id
                FROM alert_history ah
                LEFT JOIN devices d ON ah.device_id = d.id
                WHERE ah.status = 'sent'
                ORDER BY ah.created_at DESC
                LIMIT {ph}
            ''', (limit,))
            raw_alerts = self._rows_to_dicts(cursor.fetchall())

            if not raw_alerts:
                return []

            cursor.execute('SELECT id, name, parent_device_id, location, device_type FROM devices')
            devices = self._rows_to_dicts(cursor.fetchall())
            device_map = {d['id']: d for d in devices if d.get('id') is not None}

            cursor.execute('SELECT device_id, connected_to FROM topology')
            topology_rows = self._rows_to_dicts(cursor.fetchall())

            graph = {}

            def _link(a, b):
                if not a or not b:
                    return
                graph.setdefault(a, set()).add(b)
                graph.setdefault(b, set()).add(a)

            for d in devices:
                parent_id = d.get('parent_device_id')
                if parent_id:
                    _link(d.get('id'), parent_id)

            for row in topology_rows:
                _link(row.get('device_id'), row.get('connected_to'))

            def _parse_dt(value):
                if not value:
                    return None
                try:
                    return datetime.fromisoformat(str(value))
                except Exception:
                    return None

            dedupe_delta = timedelta(minutes=max(1, dedupe_minutes))
            incident_delta = timedelta(minutes=max(1, window_minutes))

            # Work oldest -> newest so grouping is stable.
            alerts = list(reversed(raw_alerts))
            unique_events = []

            for alert in alerts:
                alert_dt = _parse_dt(alert.get('created_at'))
                if alert_dt is None:
                    continue

                duplicate = False
                for existing in reversed(unique_events):
                    if existing.get('device_id') != alert.get('device_id'):
                        continue
                    if existing.get('event_type') != alert.get('event_type'):
                        continue

                    existing_dt = existing.get('_dt')
                    if existing_dt is None:
                        continue

                    if abs(alert_dt - existing_dt) <= dedupe_delta:
                        channels = existing.setdefault('channels', [])
                        if alert.get('channel') and alert.get('channel') not in channels:
                            channels.append(alert.get('channel'))
                        duplicate = True
                        break

                if duplicate:
                    continue

                copied = dict(alert)
                copied['_dt'] = alert_dt
                copied['channels'] = [alert.get('channel')] if alert.get('channel') else []
                unique_events.append(copied)

            incidents = []

            def _is_related(device_a, device_b):
                if not device_a or not device_b:
                    return False
                if device_a == device_b:
                    return True
                neighbors = graph.get(device_a, set())
                if device_b in neighbors:
                    return True
                reverse_neighbors = graph.get(device_b, set())
                if device_a in reverse_neighbors:
                    return True
                return False

            for event in unique_events:
                event_dt = event.get('_dt')
                event_device = event.get('device_id')
                matched = None

                for incident in reversed(incidents):
                    if event_dt - incident['_latest_dt'] > incident_delta:
                        continue

                    related = False
                    for member in incident['alerts']:
                        if _is_related(event_device, member.get('device_id')):
                            related = True
                            break

                    if related:
                        matched = incident
                        break

                if matched is None:
                    matched = {
                        'id': f"incident-{len(incidents) + 1}",
                        'started_at': event.get('created_at'),
                        'latest_at': event.get('created_at'),
                        '_latest_dt': event_dt,
                        'devices': set(),
                        'channels': set(),
                        'event_types': set(),
                        'alerts': [],
                    }
                    incidents.append(matched)

                matched['alerts'].append({
                    'device_id': event.get('device_id'),
                    'device_name': event.get('device_name'),
                    'ip_address': event.get('ip_address'),
                    'location': event.get('location'),
                    'device_type': event.get('device_type'),
                    'event_type': event.get('event_type'),
                    'message': event.get('message'),
                    'created_at': event.get('created_at'),
                    'channels': event.get('channels', []),
                })
                if event_dt > matched['_latest_dt']:
                    matched['_latest_dt'] = event_dt
                    matched['latest_at'] = event.get('created_at')
                if event.get('device_id'):
                    matched['devices'].add(event.get('device_id'))
                for channel in event.get('channels', []):
                    matched['channels'].add(channel)
                if event.get('event_type'):
                    matched['event_types'].add(event.get('event_type'))

            formatted = []
            for index, incident in enumerate(reversed(incidents), start=1):
                device_ids = sorted([d for d in incident['devices'] if d is not None])
                root_cause = None

                for device_id in device_ids:
                    device = device_map.get(device_id) or {}
                    if device.get('parent_device_id') in device_ids:
                        continue
                    root_cause = {
                        'device_id': device_id,
                        'device_name': device.get('name'),
                    }
                    break

                if root_cause is None and incident['alerts']:
                    first = incident['alerts'][0]
                    root_cause = {
                        'device_id': first.get('device_id'),
                        'device_name': first.get('device_name'),
                    }

                severity = 'warning'
                if any(a.get('event_type') == 'down' for a in incident['alerts']):
                    severity = 'critical'
                elif any(a.get('event_type') == 'ssl_expiry' for a in incident['alerts']):
                    severity = 'warning'
                elif any(a.get('event_type') == 'recovery' for a in incident['alerts']):
                    severity = 'info'

                stable_source = '|'.join([
                    str(incident['started_at'] or ''),
                    ','.join(str(d) for d in device_ids),
                    ','.join(sorted(incident['event_types'])),
                    str((root_cause or {}).get('device_id') or ''),
                ])
                incident_id = f"inc-{hashlib.sha1(stable_source.encode('utf-8')).hexdigest()[:16]}"

                state = self.get_incident_state(incident_id)
                activity = self.get_incident_activity(incident_id, limit=10)

                formatted.append({
                    'id': incident_id,
                    'sequence': index,
                    'started_at': incident['started_at'],
                    'latest_at': incident['latest_at'],
                    'severity': severity,
                    'alert_count': len(incident['alerts']),
                    'device_count': len(device_ids),
                    'device_ids': device_ids,
                    'channels': sorted(incident['channels']),
                    'event_types': sorted(incident['event_types']),
                    'root_cause_candidate': root_cause,
                    'summary': f"{len(incident['alerts'])} alert(s) across {len(device_ids)} device(s)",
                    'workflow_status': (state or {}).get('status', 'open'),
                    'workflow_note': (state or {}).get('note'),
                    'workflow_updated_at': (state or {}).get('updated_at'),
                    'workflow_acknowledged_at': (state or {}).get('acknowledged_at'),
                    'workflow_acknowledged_by': (state or {}).get('acknowledged_by_username'),
                    'workflow_owner_user_id': (state or {}).get('owner_user_id'),
                    'workflow_owner_username': (state or {}).get('owner_username'),
                    'activity': activity,
                    'alerts': list(reversed(incident['alerts'])),
                })

            return formatted
        finally:
            self.release_connection(conn)

    def get_incident_state(self, incident_id):
        """Get persisted workflow state for a correlated incident."""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            cursor.execute(
                f'SELECT * FROM incident_states WHERE incident_id = {self._ph()}',
                (incident_id,)
            )
            row = cursor.fetchone()
            return self._row_to_dict(row)
        finally:
            self.release_connection(conn)

    def update_incident_state(self, incident_id, status, user_id=None, username=None, note=None):
        """Create or update workflow state for a correlated incident."""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            now = datetime.now().isoformat()

            existing = self.get_incident_state(incident_id)
            old_status = (existing or {}).get('status')
            if existing:
                cursor.execute(f'''
                    UPDATE incident_states
                    SET status = {self._ph()},
                        note = {self._ph()},
                        acknowledged_by_user_id = {self._ph()},
                        acknowledged_by_username = {self._ph()},
                        acknowledged_at = {self._ph()},
                        updated_at = {self._ph()}
                    WHERE incident_id = {self._ph()}
                ''', (
                    status,
                    note,
                    user_id,
                    username,
                    now,
                    now,
                    incident_id,
                ))
            else:
                cursor.execute(f'''
                    INSERT INTO incident_states (
                        incident_id, status, note, acknowledged_by_user_id,
                        acknowledged_by_username, acknowledged_at, updated_at
                    )
                    VALUES ({self._ph(7)})
                ''', (
                    incident_id,
                    status,
                    note,
                    user_id,
                    username,
                    now,
                    now,
                ))

            self.add_incident_activity(
                incident_id=incident_id,
                action='status_change',
                old_status=old_status,
                new_status=status,
                note=note,
                actor_user_id=user_id,
                actor_username=username,
                conn=conn,
                cursor=cursor,
            )

            conn.commit()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            self.release_connection(conn)

    def update_incident_owner(self, incident_id, owner_user_id=None, owner_username=None,
                              actor_user_id=None, actor_username=None, note=None):
        """Assign or reassign an owner for a correlated incident."""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            now = datetime.now().isoformat()
            existing = self.get_incident_state(incident_id) or {}
            old_owner = existing.get('owner_username')

            if existing:
                cursor.execute(f'''
                    UPDATE incident_states
                    SET owner_user_id = {self._ph()},
                        owner_username = {self._ph()},
                        updated_at = {self._ph()}
                    WHERE incident_id = {self._ph()}
                ''', (
                    owner_user_id,
                    owner_username,
                    now,
                    incident_id,
                ))
            else:
                cursor.execute(f'''
                    INSERT INTO incident_states (
                        incident_id, status, note, owner_user_id, owner_username,
                        acknowledged_by_user_id, acknowledged_by_username, acknowledged_at, updated_at
                    )
                    VALUES ({self._ph(9)})
                ''', (
                    incident_id,
                    'open',
                    None,
                    owner_user_id,
                    owner_username,
                    None,
                    None,
                    None,
                    now,
                ))

            self.add_incident_activity(
                incident_id=incident_id,
                action='owner_change',
                old_status=old_owner,
                new_status=owner_username or 'unassigned',
                note=note,
                actor_user_id=actor_user_id,
                actor_username=actor_username,
                conn=conn,
                cursor=cursor,
            )

            conn.commit()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            self.release_connection(conn)

    def add_incident_activity(self, incident_id, action, old_status=None, new_status=None,
                              note=None, actor_user_id=None, actor_username=None,
                              conn=None, cursor=None):
        """Append an activity log entry for an incident."""
        own_conn = conn is None or cursor is None
        if own_conn:
            conn = self.get_connection()
            cursor = self._cursor(conn)
        try:
            now = datetime.now().isoformat()
            cursor.execute(f'''
                INSERT INTO incident_activity (
                    incident_id, action, old_status, new_status, note,
                    actor_user_id, actor_username, created_at
                )
                VALUES ({self._ph(8)})
            ''', (
                incident_id,
                action,
                old_status,
                new_status,
                note,
                actor_user_id,
                actor_username,
                now,
            ))
            if own_conn:
                conn.commit()
            return {'success': True}
        except Exception as e:
            if own_conn:
                return {'success': False, 'error': str(e)}
            raise
        finally:
            if own_conn:
                self.release_connection(conn)

    def get_incident_activity(self, incident_id, limit=20):
        """Get recent activity log entries for an incident."""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            cursor.execute(f'''
                SELECT * FROM incident_activity
                WHERE incident_id = {self._ph()}
                ORDER BY created_at DESC
                LIMIT {self._ph()}
            ''', (incident_id, limit))
            return self._rows_to_dicts(cursor.fetchall())
        finally:
            self.release_connection(conn)

    def sync_persistent_incidents(self, limit=500, window_minutes=10, dedupe_minutes=2):
        """
        Materialize current correlated incidents into a persistent table.

        This keeps a durable incident snapshot for reporting, analytics, and
        future lifecycle extensions while correlation is still computed live.
        """
        incidents = self.get_alert_incidents(
            limit=limit,
            window_minutes=window_minutes,
            dedupe_minutes=dedupe_minutes,
        )

        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            now = datetime.now().isoformat()
            ph = self._ph()

            # Mark everything inactive first; current incidents will be reactivated below.
            if self.db_type == 'postgresql':
                cursor.execute('UPDATE persistent_incidents SET is_active = FALSE, updated_at = %s', (now,))
            else:
                cursor.execute('UPDATE persistent_incidents SET is_active = 0, updated_at = ?', (now,))

            for incident in incidents:
                root = incident.get('root_cause_candidate') or {}
                payload_json = json.dumps(incident, ensure_ascii=False)
                active_flag = True if self.db_type == 'postgresql' else 1

                if self.db_type == 'postgresql':
                    cursor.execute(f'''
                        INSERT INTO persistent_incidents (
                            incident_id, started_at, latest_at, severity, alert_count, device_count,
                            root_cause_device_id, root_cause_device_name, workflow_status,
                            workflow_owner_username, is_active, payload_json,
                            last_materialized_at, created_at, updated_at
                        )
                        VALUES ({self._ph(15)})
                        ON CONFLICT (incident_id) DO UPDATE SET
                            started_at = EXCLUDED.started_at,
                            latest_at = EXCLUDED.latest_at,
                            severity = EXCLUDED.severity,
                            alert_count = EXCLUDED.alert_count,
                            device_count = EXCLUDED.device_count,
                            root_cause_device_id = EXCLUDED.root_cause_device_id,
                            root_cause_device_name = EXCLUDED.root_cause_device_name,
                            workflow_status = EXCLUDED.workflow_status,
                            workflow_owner_username = EXCLUDED.workflow_owner_username,
                            is_active = EXCLUDED.is_active,
                            payload_json = EXCLUDED.payload_json,
                            last_materialized_at = EXCLUDED.last_materialized_at,
                            updated_at = EXCLUDED.updated_at
                    ''', (
                        incident.get('id'),
                        incident.get('started_at'),
                        incident.get('latest_at'),
                        incident.get('severity'),
                        incident.get('alert_count', 0),
                        incident.get('device_count', 0),
                        root.get('device_id'),
                        root.get('device_name'),
                        incident.get('workflow_status'),
                        incident.get('workflow_owner_username'),
                        active_flag,
                        payload_json,
                        now,
                        now,
                        now,
                    ))
                else:
                    cursor.execute(f'''
                        INSERT INTO persistent_incidents (
                            incident_id, started_at, latest_at, severity, alert_count, device_count,
                            root_cause_device_id, root_cause_device_name, workflow_status,
                            workflow_owner_username, is_active, payload_json,
                            last_materialized_at, created_at, updated_at
                        )
                        VALUES ({self._ph(15)})
                        ON CONFLICT(incident_id) DO UPDATE SET
                            started_at = excluded.started_at,
                            latest_at = excluded.latest_at,
                            severity = excluded.severity,
                            alert_count = excluded.alert_count,
                            device_count = excluded.device_count,
                            root_cause_device_id = excluded.root_cause_device_id,
                            root_cause_device_name = excluded.root_cause_device_name,
                            workflow_status = excluded.workflow_status,
                            workflow_owner_username = excluded.workflow_owner_username,
                            is_active = excluded.is_active,
                            payload_json = excluded.payload_json,
                            last_materialized_at = excluded.last_materialized_at,
                            updated_at = excluded.updated_at
                    ''', (
                        incident.get('id'),
                        incident.get('started_at'),
                        incident.get('latest_at'),
                        incident.get('severity'),
                        incident.get('alert_count', 0),
                        incident.get('device_count', 0),
                        root.get('device_id'),
                        root.get('device_name'),
                        incident.get('workflow_status'),
                        incident.get('workflow_owner_username'),
                        active_flag,
                        payload_json,
                        now,
                        now,
                        now,
                    ))

            conn.commit()
            return {
                'success': True,
                'materialized': len(incidents),
                'window_minutes': window_minutes,
                'dedupe_minutes': dedupe_minutes,
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            self.release_connection(conn)

    def get_persistent_incidents(self, active_only=True, limit=100):
        """Read back materialized incident snapshots."""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            query = 'SELECT * FROM persistent_incidents'
            params = []
            if active_only:
                query += f' WHERE is_active = {self._ph()}'
                params.append(True if self.db_type == 'postgresql' else 1)
            query += f' ORDER BY latest_at DESC LIMIT {self._ph()}'
            params.append(limit)
            cursor.execute(query, params)
            rows = self._rows_to_dicts(cursor.fetchall())
            for row in rows:
                if row.get('payload_json'):
                    try:
                        row['payload'] = json.loads(row['payload_json'])
                    except Exception:
                        row['payload'] = None
            return rows
        finally:
            self.release_connection(conn)

    def _calc_mean_std(self, values):
        values = [float(v) for v in values if v is not None]
        if not values:
            return 0.0, 0.0
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return mean, math.sqrt(variance)

    def _attach_anomaly_workflow(self, anomalies, activity_limit=10):
        """Attach persisted workflow state and recent activity to anomalies."""
        if not anomalies:
            return anomalies

        for anomaly in anomalies:
            anomaly_key = anomaly.get('anomaly_key')
            state = self.get_anomaly_state(anomaly_key) if anomaly_key else None
            activity = self.get_anomaly_activity(anomaly_key, limit=activity_limit) if anomaly_key else []
            linked_incident = self.get_anomaly_incident_link(anomaly_key) if anomaly_key else None
            anomaly['workflow_status'] = (state or {}).get('status', 'open')
            anomaly['workflow_note'] = (state or {}).get('note')
            anomaly['workflow_updated_at'] = (state or {}).get('updated_at')
            anomaly['workflow_acknowledged_at'] = (state or {}).get('acknowledged_at')
            anomaly['workflow_acknowledged_by'] = (state or {}).get('acknowledged_by_username')
            anomaly['workflow_owner_user_id'] = (state or {}).get('owner_user_id')
            anomaly['workflow_owner_username'] = (state or {}).get('owner_username')
            anomaly['activity'] = activity
            anomaly['linked_incident'] = linked_incident
        return self._attach_anomaly_incident_suggestions(anomalies)

    def _attach_anomaly_incident_suggestions(self, anomalies, incident_limit=200):
        """Attach likely related incidents to anomalies using device, location, and time proximity."""
        if not anomalies:
            return anomalies

        incidents = self.get_persistent_incidents(active_only=True, limit=incident_limit)
        if not incidents:
            for anomaly in anomalies:
                anomaly['related_incidents'] = []
                anomaly['related_incident_count'] = 0
                anomaly['primary_incident_suggestion'] = None
            return anomalies

        def _parse_dt(value):
            if not value:
                return None
            if isinstance(value, datetime):
                return value
            text = str(value).strip()
            if not text:
                return None
            try:
                return datetime.fromisoformat(text.replace('Z', '+00:00'))
            except Exception:
                return None

        for anomaly in anomalies:
            anomaly_device_id = anomaly.get('device_id')
            anomaly_location = (anomaly.get('location') or '').strip().lower()
            anomaly_time = _parse_dt(anomaly.get('last_seen_at') or anomaly.get('detected_at'))
            linked_incident = anomaly.get('linked_incident') or {}
            matches = []

            for incident in incidents:
                payload = incident.get('payload') or {}
                incident_device_ids = set(payload.get('device_ids') or [])
                incident_locations = {
                    str(alert.get('location')).strip().lower()
                    for alert in (payload.get('alerts') or [])
                    if alert.get('location')
                }
                score = 0
                reasons = []

                if anomaly_device_id and anomaly_device_id in incident_device_ids:
                    score += 5
                    reasons.append('same device')
                elif anomaly_device_id and incident.get('root_cause_device_id') == anomaly_device_id:
                    score += 4
                    reasons.append('same root cause device')

                if anomaly_location and anomaly_location in incident_locations:
                    score += 2
                    reasons.append('same location')

                incident_latest = _parse_dt(incident.get('latest_at'))
                if anomaly_time and incident_latest:
                    minutes_apart = abs((anomaly_time - incident_latest).total_seconds()) / 60.0
                    if minutes_apart <= 15:
                        score += 3
                        reasons.append('within 15 minutes')
                    elif minutes_apart <= 60:
                        score += 2
                        reasons.append('within 1 hour')
                    elif minutes_apart <= 180:
                        score += 1
                        reasons.append('within 3 hours')

                if score <= 0:
                    continue

                matches.append({
                    'incident_id': incident.get('incident_id'),
                    'severity': incident.get('severity'),
                    'workflow_status': incident.get('workflow_status'),
                    'summary': (payload or {}).get('summary') or f"{incident.get('alert_count', 0)} alert(s)",
                    'latest_at': incident.get('latest_at'),
                    'started_at': incident.get('started_at'),
                    'score': score,
                    'reasons': reasons,
                    'root_cause_device_id': incident.get('root_cause_device_id'),
                    'root_cause_device_name': incident.get('root_cause_device_name'),
                    'device_ids': payload.get('device_ids') or [],
                    'is_linked': linked_incident.get('incident_id') == incident.get('incident_id'),
                })

            matches = sorted(matches, key=lambda item: (-(item.get('score') or 0), item.get('latest_at') or ''))
            matches = matches[:3]
            anomaly['related_incidents'] = matches
            anomaly['related_incident_count'] = len(matches)
            anomaly['primary_incident_suggestion'] = matches[0] if matches else None
        return anomalies

    def detect_anomalies(self, recent_minutes=30, baseline_hours=24, min_points=5):
        """
        Detect anomalies from response time, bandwidth utilization, and system metrics.

        MVP rules:
        - Compare recent window averages against a rolling baseline
        - Flag when z-score is large or value is materially above baseline
        """
        devices = self.get_all_devices()
        if not devices:
            return []

        device_map = {d['id']: d for d in devices}
        recent_cutoff = (datetime.now() - timedelta(minutes=recent_minutes)).isoformat()
        baseline_cutoff = (datetime.now() - timedelta(hours=baseline_hours)).isoformat()

        anomalies = []
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            ph = self._ph()

            # Response time anomalies
            cursor.execute(f'''
                SELECT device_id, response_time, checked_at
                FROM status_history
                WHERE checked_at >= {ph}
                  AND response_time IS NOT NULL
                  AND status IN ('up', 'slow')
                ORDER BY checked_at ASC
            ''', (baseline_cutoff,))
            rows = self._rows_to_dicts(cursor.fetchall())
            response_by_device = {}
            for row in rows:
                response_by_device.setdefault(row['device_id'], []).append(row)

            for device_id, samples in response_by_device.items():
                baseline = [r['response_time'] for r in samples if r['checked_at'] < recent_cutoff]
                recent = [r['response_time'] for r in samples if r['checked_at'] >= recent_cutoff]
                if len(baseline) < min_points or len(recent) < 2:
                    continue
                mean, std = self._calc_mean_std(baseline)
                recent_avg = sum(recent) / len(recent)
                score = (recent_avg - mean) / std if std > 0 else (recent_avg / mean if mean > 0 else 0)
                if (std > 0 and score >= 2.5) or (std == 0 and mean > 0 and recent_avg >= mean * 1.75 and recent_avg - mean >= 50):
                    device = device_map.get(device_id, {})
                    anomalies.append({
                        'anomaly_key': f"anomaly-rt-{device_id}",
                        'device_id': device_id,
                        'device_name': device.get('name'),
                        'anomaly_type': 'response_time',
                        'metric_name': 'avg_response_time',
                        'severity': 'critical' if score >= 4 else 'warning',
                        'score': round(float(score), 2),
                        'summary': f"Response time elevated for {device.get('name', device_id)}",
                        'details': {
                            'baseline_mean': round(mean, 2),
                            'baseline_stddev': round(std, 2),
                            'recent_average': round(recent_avg, 2),
                            'recent_samples': len(recent),
                            'baseline_samples': len(baseline),
                        },
                    })

            # Bandwidth anomalies (utilization)
            cursor.execute(f'''
                SELECT device_id, util_in, util_out, sampled_at
                FROM bandwidth_history
                WHERE sampled_at >= {ph}
            ''', (baseline_cutoff,))
            rows = self._rows_to_dicts(cursor.fetchall())
            bandwidth_by_device = {}
            for row in rows:
                util = max(row.get('util_in') or 0, row.get('util_out') or 0)
                bandwidth_by_device.setdefault(row['device_id'], []).append({
                    'value': util,
                    'sampled_at': row['sampled_at'],
                })

            for device_id, samples in bandwidth_by_device.items():
                baseline = [r['value'] for r in samples if r['sampled_at'] < recent_cutoff]
                recent = [r['value'] for r in samples if r['sampled_at'] >= recent_cutoff]
                if len(baseline) < min_points or len(recent) < 2:
                    continue
                mean, std = self._calc_mean_std(baseline)
                recent_avg = sum(recent) / len(recent)
                score = (recent_avg - mean) / std if std > 0 else (recent_avg / mean if mean > 0 else 0)
                if recent_avg >= 70 and ((std > 0 and score >= 2.5) or (std == 0 and mean > 0 and recent_avg >= mean * 1.5)):
                    device = device_map.get(device_id, {})
                    anomalies.append({
                        'anomaly_key': f"anomaly-bw-{device_id}",
                        'device_id': device_id,
                        'device_name': device.get('name'),
                        'anomaly_type': 'bandwidth',
                        'metric_name': 'utilization',
                        'severity': 'critical' if recent_avg >= 85 else 'warning',
                        'score': round(float(score), 2),
                        'summary': f"Bandwidth utilization spike on {device.get('name', device_id)}",
                        'details': {
                            'baseline_mean': round(mean, 2),
                            'baseline_stddev': round(std, 2),
                            'recent_average': round(recent_avg, 2),
                            'recent_samples': len(recent),
                            'baseline_samples': len(baseline),
                        },
                    })

            # System metric anomalies (CPU/RAM/Disk)
            cursor.execute(f'''
                SELECT device_id, metric_type, value, timestamp
                FROM system_metrics_history
                WHERE timestamp >= {ph}
                  AND metric_type IN ('cpu', 'ram', 'disk')
            ''', (baseline_cutoff,))
            rows = self._rows_to_dicts(cursor.fetchall())
            metric_by_device = {}
            for row in rows:
                metric_by_device.setdefault((row['device_id'], row['metric_type']), []).append(row)

            for (device_id, metric_type), samples in metric_by_device.items():
                baseline = [r['value'] for r in samples if r['timestamp'] < recent_cutoff]
                recent = [r['value'] for r in samples if r['timestamp'] >= recent_cutoff]
                if len(baseline) < min_points or len(recent) < 2:
                    continue
                mean, std = self._calc_mean_std(baseline)
                recent_avg = sum(recent) / len(recent)
                score = (recent_avg - mean) / std if std > 0 else (recent_avg / mean if mean > 0 else 0)
                hard_threshold = 85 if metric_type in ('cpu', 'ram') else 90
                if recent_avg >= hard_threshold and ((std > 0 and score >= 2.0) or (std == 0 and mean > 0 and recent_avg >= mean * 1.3)):
                    device = device_map.get(device_id, {})
                    anomalies.append({
                        'anomaly_key': f"anomaly-{metric_type}-{device_id}",
                        'device_id': device_id,
                        'device_name': device.get('name'),
                        'anomaly_type': 'system_metric',
                        'metric_name': metric_type,
                        'severity': 'critical' if recent_avg >= 95 else 'warning',
                        'score': round(float(score), 2),
                        'summary': f"{metric_type.upper()} anomaly on {device.get('name', device_id)}",
                        'details': {
                            'baseline_mean': round(mean, 2),
                            'baseline_stddev': round(std, 2),
                            'recent_average': round(recent_avg, 2),
                            'recent_samples': len(recent),
                            'baseline_samples': len(baseline),
                        },
                    })

            anomalies.sort(key=lambda a: (0 if a['severity'] == 'critical' else 1, -(a.get('score') or 0)))
            return self._attach_anomaly_workflow(anomalies)
        finally:
            self.release_connection(conn)

    def sync_anomaly_snapshots(self, recent_minutes=30, baseline_hours=24, min_points=5):
        """Materialize current anomaly results into a persistent snapshot table."""
        anomalies = self.detect_anomalies(
            recent_minutes=recent_minutes,
            baseline_hours=baseline_hours,
            min_points=min_points,
        )

        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            now = datetime.now().isoformat()
            active_flag = True if self.db_type == 'postgresql' else 1
            inactive_flag = False if self.db_type == 'postgresql' else 0

            cursor.execute(f'UPDATE anomaly_snapshots SET is_active = {self._ph()}, updated_at = {self._ph()}', (inactive_flag, now))

            for anomaly in anomalies:
                details_json = json.dumps(anomaly.get('details') or {}, ensure_ascii=False)
                if self.db_type == 'postgresql':
                    cursor.execute(f'''
                        INSERT INTO anomaly_snapshots (
                            anomaly_key, device_id, device_name, anomaly_type, metric_name,
                            severity, score, summary, details_json, detected_at,
                            last_seen_at, is_active, created_at, updated_at
                        )
                        VALUES ({self._ph(14)})
                        ON CONFLICT (anomaly_key) DO UPDATE SET
                            device_id = EXCLUDED.device_id,
                            device_name = EXCLUDED.device_name,
                            anomaly_type = EXCLUDED.anomaly_type,
                            metric_name = EXCLUDED.metric_name,
                            severity = EXCLUDED.severity,
                            score = EXCLUDED.score,
                            summary = EXCLUDED.summary,
                            details_json = EXCLUDED.details_json,
                            last_seen_at = EXCLUDED.last_seen_at,
                            is_active = EXCLUDED.is_active,
                            updated_at = EXCLUDED.updated_at
                    ''', (
                        anomaly['anomaly_key'],
                        anomaly.get('device_id'),
                        anomaly.get('device_name'),
                        anomaly.get('anomaly_type'),
                        anomaly.get('metric_name'),
                        anomaly.get('severity'),
                        anomaly.get('score'),
                        anomaly.get('summary'),
                        details_json,
                        now,
                        now,
                        active_flag,
                        now,
                        now,
                    ))
                else:
                    cursor.execute(f'''
                        INSERT INTO anomaly_snapshots (
                            anomaly_key, device_id, device_name, anomaly_type, metric_name,
                            severity, score, summary, details_json, detected_at,
                            last_seen_at, is_active, created_at, updated_at
                        )
                        VALUES ({self._ph(14)})
                        ON CONFLICT(anomaly_key) DO UPDATE SET
                            device_id = excluded.device_id,
                            device_name = excluded.device_name,
                            anomaly_type = excluded.anomaly_type,
                            metric_name = excluded.metric_name,
                            severity = excluded.severity,
                            score = excluded.score,
                            summary = excluded.summary,
                            details_json = excluded.details_json,
                            last_seen_at = excluded.last_seen_at,
                            is_active = excluded.is_active,
                            updated_at = excluded.updated_at
                    ''', (
                        anomaly['anomaly_key'],
                        anomaly.get('device_id'),
                        anomaly.get('device_name'),
                        anomaly.get('anomaly_type'),
                        anomaly.get('metric_name'),
                        anomaly.get('severity'),
                        anomaly.get('score'),
                        anomaly.get('summary'),
                        details_json,
                        now,
                        now,
                        active_flag,
                        now,
                        now,
                    ))

            conn.commit()
            return {'success': True, 'count': len(anomalies)}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            self.release_connection(conn)

    def get_anomaly_snapshots(self, active_only=True, limit=100):
        """Get materialized anomaly snapshots."""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            query = 'SELECT * FROM anomaly_snapshots'
            params = []
            if active_only:
                query += f' WHERE is_active = {self._ph()}'
                params.append(True if self.db_type == 'postgresql' else 1)
            if self.db_type == 'postgresql':
                query += f' ORDER BY severity DESC, score DESC NULLS LAST, detected_at DESC LIMIT {self._ph()}'
            else:
                query += f' ORDER BY severity DESC, score DESC, detected_at DESC LIMIT {self._ph()}'
            params.append(limit)
            cursor.execute(query, params)
            rows = self._rows_to_dicts(cursor.fetchall())
            for row in rows:
                if row.get('details_json'):
                    try:
                        row['details'] = json.loads(row['details_json'])
                    except Exception:
                        row['details'] = None
            return self._attach_anomaly_workflow(rows)
        finally:
            self.release_connection(conn)

    def get_anomaly_state(self, anomaly_key):
        """Get persisted workflow state for an anomaly."""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            cursor.execute(
                f'SELECT * FROM anomaly_states WHERE anomaly_key = {self._ph()}',
                (anomaly_key,)
            )
            row = cursor.fetchone()
            return self._row_to_dict(row)
        finally:
            self.release_connection(conn)

    def get_persistent_incident_by_id(self, incident_id):
        """Get one materialized incident snapshot by incident id."""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            cursor.execute(
                f'SELECT * FROM persistent_incidents WHERE incident_id = {self._ph()}',
                (incident_id,)
            )
            row = self._row_to_dict(cursor.fetchone())
            if row and row.get('payload_json'):
                try:
                    row['payload'] = json.loads(row['payload_json'])
                except Exception:
                    row['payload'] = None
            return row
        finally:
            self.release_connection(conn)

    def get_anomaly_incident_link(self, anomaly_key):
        """Get a persisted anomaly -> incident link."""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            cursor.execute(
                f'SELECT * FROM anomaly_incident_links WHERE anomaly_key = {self._ph()}',
                (anomaly_key,)
            )
            row = self._row_to_dict(cursor.fetchone())
            if not row:
                return None
            incident = self.get_persistent_incident_by_id(row.get('incident_id'))
            row['incident'] = incident
            return row
        finally:
            self.release_connection(conn)

    def link_anomaly_to_incident(self, anomaly_key, incident_id, actor_user_id=None, actor_username=None, note=None):
        """Link an anomaly to a materialized incident."""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            now = datetime.now().isoformat()
            existing = self.get_anomaly_incident_link(anomaly_key)
            old_incident_id = (existing or {}).get('incident_id')

            if self.get_persistent_incident_by_id(incident_id) is None:
                return {'success': False, 'error': 'Incident not found'}

            if existing:
                cursor.execute(f'''
                    UPDATE anomaly_incident_links
                    SET incident_id = {self._ph()},
                        note = {self._ph()},
                        linked_by_user_id = {self._ph()},
                        linked_by_username = {self._ph()},
                        updated_at = {self._ph()}
                    WHERE anomaly_key = {self._ph()}
                ''', (
                    incident_id,
                    note,
                    actor_user_id,
                    actor_username,
                    now,
                    anomaly_key,
                ))
            else:
                cursor.execute(f'''
                    INSERT INTO anomaly_incident_links (
                        anomaly_key, incident_id, note, linked_by_user_id,
                        linked_by_username, linked_at, updated_at
                    )
                    VALUES ({self._ph(7)})
                ''', (
                    anomaly_key,
                    incident_id,
                    note,
                    actor_user_id,
                    actor_username,
                    now,
                    now,
                ))

            self.add_anomaly_activity(
                anomaly_key=anomaly_key,
                action='incident_link',
                old_status=old_incident_id,
                new_status=incident_id,
                note=note,
                actor_user_id=actor_user_id,
                actor_username=actor_username,
                conn=conn,
                cursor=cursor,
            )
            conn.commit()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            self.release_connection(conn)

    def unlink_anomaly_from_incident(self, anomaly_key, actor_user_id=None, actor_username=None, note=None):
        """Remove a persisted anomaly -> incident link."""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            existing = self.get_anomaly_incident_link(anomaly_key)
            if not existing:
                return {'success': False, 'error': 'Link not found'}

            cursor.execute(
                f'DELETE FROM anomaly_incident_links WHERE anomaly_key = {self._ph()}',
                (anomaly_key,)
            )
            self.add_anomaly_activity(
                anomaly_key=anomaly_key,
                action='incident_unlink',
                old_status=existing.get('incident_id'),
                new_status=None,
                note=note,
                actor_user_id=actor_user_id,
                actor_username=actor_username,
                conn=conn,
                cursor=cursor,
            )
            conn.commit()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            self.release_connection(conn)

    def update_anomaly_state(self, anomaly_key, status, user_id=None, username=None, note=None):
        """Create or update workflow state for an anomaly."""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            now = datetime.now().isoformat()

            existing = self.get_anomaly_state(anomaly_key)
            old_status = (existing or {}).get('status')
            if existing:
                cursor.execute(f'''
                    UPDATE anomaly_states
                    SET status = {self._ph()},
                        note = {self._ph()},
                        acknowledged_by_user_id = {self._ph()},
                        acknowledged_by_username = {self._ph()},
                        acknowledged_at = {self._ph()},
                        updated_at = {self._ph()}
                    WHERE anomaly_key = {self._ph()}
                ''', (
                    status,
                    note,
                    user_id,
                    username,
                    now,
                    now,
                    anomaly_key,
                ))
            else:
                cursor.execute(f'''
                    INSERT INTO anomaly_states (
                        anomaly_key, status, note, acknowledged_by_user_id,
                        acknowledged_by_username, acknowledged_at, updated_at
                    )
                    VALUES ({self._ph(7)})
                ''', (
                    anomaly_key,
                    status,
                    note,
                    user_id,
                    username,
                    now,
                    now,
                ))

            self.add_anomaly_activity(
                anomaly_key=anomaly_key,
                action='status_change',
                old_status=old_status,
                new_status=status,
                note=note,
                actor_user_id=user_id,
                actor_username=username,
                conn=conn,
                cursor=cursor,
            )

            conn.commit()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            self.release_connection(conn)

    def update_anomaly_owner(self, anomaly_key, owner_user_id=None, owner_username=None,
                             actor_user_id=None, actor_username=None, note=None):
        """Assign or reassign an owner for an anomaly."""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            now = datetime.now().isoformat()
            existing = self.get_anomaly_state(anomaly_key) or {}
            old_owner = existing.get('owner_username')

            if existing:
                cursor.execute(f'''
                    UPDATE anomaly_states
                    SET owner_user_id = {self._ph()},
                        owner_username = {self._ph()},
                        updated_at = {self._ph()}
                    WHERE anomaly_key = {self._ph()}
                ''', (
                    owner_user_id,
                    owner_username,
                    now,
                    anomaly_key,
                ))
            else:
                cursor.execute(f'''
                    INSERT INTO anomaly_states (
                        anomaly_key, status, note, owner_user_id, owner_username,
                        acknowledged_by_user_id, acknowledged_by_username, acknowledged_at, updated_at
                    )
                    VALUES ({self._ph(9)})
                ''', (
                    anomaly_key,
                    'open',
                    None,
                    owner_user_id,
                    owner_username,
                    None,
                    None,
                    None,
                    now,
                ))

            self.add_anomaly_activity(
                anomaly_key=anomaly_key,
                action='owner_change',
                old_status=old_owner,
                new_status=owner_username or 'unassigned',
                note=note,
                actor_user_id=actor_user_id,
                actor_username=actor_username,
                conn=conn,
                cursor=cursor,
            )

            conn.commit()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            self.release_connection(conn)

    def add_anomaly_activity(self, anomaly_key, action, old_status=None, new_status=None,
                             note=None, actor_user_id=None, actor_username=None,
                             conn=None, cursor=None):
        """Append an activity log entry for an anomaly."""
        own_conn = conn is None or cursor is None
        if own_conn:
            conn = self.get_connection()
            cursor = self._cursor(conn)
        try:
            now = datetime.now().isoformat()
            cursor.execute(f'''
                INSERT INTO anomaly_activity (
                    anomaly_key, action, old_status, new_status, note,
                    actor_user_id, actor_username, created_at
                )
                VALUES ({self._ph(8)})
            ''', (
                anomaly_key,
                action,
                old_status,
                new_status,
                note,
                actor_user_id,
                actor_username,
                now,
            ))
            if own_conn:
                conn.commit()
            return {'success': True}
        except Exception as e:
            if own_conn:
                return {'success': False, 'error': str(e)}
            raise
        finally:
            if own_conn:
                self.release_connection(conn)

    def get_anomaly_activity(self, anomaly_key, limit=20):
        """Get recent activity log entries for an anomaly."""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            cursor.execute(f'''
                SELECT * FROM anomaly_activity
                WHERE anomaly_key = {self._ph()}
                ORDER BY created_at DESC
                LIMIT {self._ph()}
            ''', (anomaly_key, limit))
            return self._rows_to_dicts(cursor.fetchall())
        finally:
            self.release_connection(conn)
    
    def get_failure_count(self, device_id):
        """Get current consecutive failure count for a device"""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            cursor.execute(f'SELECT failure_count FROM devices WHERE id = {self._ph()}', (device_id,))
            result = cursor.fetchone()
            if result is None:
                return 0
            r = self._row_to_dict(result)
            return r['failure_count'] if r and r['failure_count'] else 0
        finally:
            self.release_connection(conn)
    
    def increment_failure_count(self, device_id):
        """Increment failure count for a device and return new count"""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            ph = self._ph()
            cursor.execute(f'''
                UPDATE devices 
                SET failure_count = COALESCE(failure_count, 0) + 1
                WHERE id = {ph}
            ''', (device_id,))
            cursor.execute(f'SELECT failure_count FROM devices WHERE id = {ph}', (device_id,))
            result = cursor.fetchone()
            conn.commit()
            r = self._row_to_dict(result)
            return r['failure_count'] if r else 1
        except Exception as e:
            if conn: conn.rollback()
            raise e
        finally:
            self.release_connection(conn)
    
    def reset_failure_count(self, device_id):
        """Reset failure count to 0 when device is up"""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            cursor.execute(f'UPDATE devices SET failure_count = 0 WHERE id = {self._ph()}', (device_id,))
            conn.commit()
        except Exception as e:
            if conn: conn.rollback()
            raise e
        finally:
            self.release_connection(conn)
    
    # =========================================================================
    # Maintenance Windows Methods
    # =========================================================================
    
    def add_maintenance_window(self, name, start_time, end_time, device_id=None, 
                                recurring=None, description=None):
        """Add a new maintenance window"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        
        try:
            if self.db_type == 'postgresql':
                cursor.execute('''
                    INSERT INTO maintenance_windows (name, device_id, start_time, end_time, 
                                                      recurring, description, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                ''', (name, device_id, start_time, end_time, recurring, description, 
                      datetime.now().isoformat()))
                window_id = cursor.fetchone()['id']
            else:
                cursor.execute('''
                    INSERT INTO maintenance_windows (name, device_id, start_time, end_time, 
                                                      recurring, description, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (name, device_id, start_time, end_time, recurring, description, 
                      datetime.now().isoformat()))
                window_id = cursor.lastrowid
            conn.commit()
            self.release_connection(conn)
            return {'success': True, 'id': window_id}
        except Exception as e:
            conn.rollback()
            self.release_connection(conn)
            return {'success': False, 'error': str(e)}
    
    def get_all_maintenance_windows(self):
        """Get all maintenance windows with device info"""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            cursor.execute('''
                SELECT mw.*, d.name as device_name, d.ip_address
                FROM maintenance_windows mw
                LEFT JOIN devices d ON mw.device_id = d.id
                ORDER BY mw.start_time DESC
            ''')
            windows = self._rows_to_dicts(cursor.fetchall())
            return windows
        finally:
            self.release_connection(conn)
    
    def get_active_maintenance(self, device_id=None):
        """Get currently active maintenance windows for a device or all devices"""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            ph = self._ph()
            
            now = datetime.now().isoformat()
            
            if device_id:
                cursor.execute(f'''
                    SELECT * FROM maintenance_windows 
                    WHERE (device_id = {ph} OR device_id IS NULL)
                      AND start_time <= {ph} 
                      AND end_time >= {ph}
                ''', (device_id, now, now))
            else:
                cursor.execute(f'''
                    SELECT * FROM maintenance_windows 
                    WHERE start_time <= {ph} AND end_time >= {ph}
                ''', (now, now))
            
            windows = self._rows_to_dicts(cursor.fetchall())
            return windows
        finally:
            self.release_connection(conn)
        
    def get_devices_for_escalation(self, minutes):
        """Get list of ALL devices that have been down for more than 'minutes' and haven't been escalated yet"""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            
            if self.db_type == 'postgresql':
                query = f'''
                    SELECT id, name, ip_address, device_type, status, last_status_change, location
                    FROM devices 
                    WHERE status = 'down' 
                    AND escalation_level = 0
                    AND is_enabled = TRUE
                    AND last_status_change <= NOW() - INTERVAL '{int(minutes)} minutes'
                '''
            else:
                query = f'''
                    SELECT id, name, ip_address, device_type, status, last_status_change, location
                    FROM devices 
                    WHERE status = 'down' 
                    AND escalation_level = 0
                    AND is_enabled = 1
                    AND last_status_change <= datetime('now', '-{int(minutes)} minutes')
                '''
                
            cursor.execute(query)
            devices = self._rows_to_dicts(cursor.fetchall())
            return devices
        finally:
            self.release_connection(conn)
        
    def mark_device_escalated(self, device_id, level=1):
        """Mark a device as having had its alert escalated"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute(f'UPDATE devices SET escalation_level = {self._ph()} WHERE id = {self._ph()}', (level, device_id))
        conn.commit()
        self.release_connection(conn)
        
        if device_id:
            cursor.execute(f'''
                SELECT * FROM maintenance_windows 
                WHERE (device_id = {ph} OR device_id IS NULL)
                  AND start_time <= {ph} 
                  AND end_time >= {ph}
            ''', (device_id, now, now))
        else:
            cursor.execute(f'''
                SELECT * FROM maintenance_windows 
                WHERE start_time <= {ph} AND end_time >= {ph}
            ''', (now, now))
        
        windows = self._rows_to_dicts(cursor.fetchall())
        self.release_connection(conn)
        return windows
    
    def is_device_in_maintenance(self, device_id):
        """Check if a device is currently in maintenance window"""
        windows = self.get_active_maintenance(device_id)
        return len(windows) > 0
    
    def delete_maintenance_window(self, window_id):
        """Delete a maintenance window"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute(f'DELETE FROM maintenance_windows WHERE id = {self._ph()}', (window_id,))
        conn.commit()
        self.release_connection(conn)
        return {'success': True}
    
    def cleanup_expired_maintenance(self):
        """Remove non-recurring maintenance windows that have ended"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        now = datetime.now().isoformat()
        cursor.execute(f'''
            DELETE FROM maintenance_windows 
            WHERE end_time < {ph} AND (recurring IS NULL OR recurring = '')
        ''', (now,))
        deleted = cursor.rowcount
        conn.commit()
        self.release_connection(conn)
        return deleted

    # =========================================================================
    # SLA (Service Level Agreement) Methods
    # =========================================================================
    
    def get_device_uptime_stats(self, device_id, days=30):
        """Calculate uptime statistics for a device over specified days"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        cursor.execute(f'''
            SELECT status, response_time, checked_at
            FROM status_history 
            WHERE device_id = {ph} 
              AND checked_at >= {ph}
            ORDER BY checked_at
        ''', (device_id, start_date.isoformat()))
        
        records = self._rows_to_dicts(cursor.fetchall())
        self.release_connection(conn)
        
        if not records:
            return {
                'uptime_percent': None,
                'total_checks': 0,
                'up_checks': 0,
                'down_checks': 0,
                'slow_checks': 0,
                'avg_response_time': None,
                'days': days
            }
        
        total = len(records)
        up_count = sum(1 for r in records if r['status'] == 'up')
        down_count = sum(1 for r in records if r['status'] == 'down')
        slow_count = sum(1 for r in records if r['status'] == 'slow')
        
        response_times = [r['response_time'] for r in records 
                          if r['response_time'] is not None and r['status'] != 'down']
        avg_response = sum(response_times) / len(response_times) if response_times else None
        
        available_count = up_count + slow_count
        uptime_percent = (available_count / total * 100) if total > 0 else None
        
        return {
            'uptime_percent': round(uptime_percent, 4) if uptime_percent else None,
            'total_checks': total,
            'up_checks': up_count,
            'down_checks': down_count,
            'slow_checks': slow_count,
            'avg_response_time': round(avg_response, 2) if avg_response else None,
            'days': days
        }
    
    def get_all_devices_sla(self, days=30, sla_target=99.9):
        """Get SLA data for all devices (optimized: single aggregate query)"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        
        start_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        # Single aggregate query instead of N+1 queries
        cursor.execute(f'''
            SELECT 
                h.device_id,
                COUNT(*) as total_checks,
                SUM(CASE WHEN h.status = 'up' THEN 1 ELSE 0 END) as up_checks,
                SUM(CASE WHEN h.status = 'down' THEN 1 ELSE 0 END) as down_checks,
                SUM(CASE WHEN h.status = 'slow' THEN 1 ELSE 0 END) as slow_checks,
                AVG(CASE WHEN h.status != 'down' AND h.response_time IS NOT NULL 
                    THEN h.response_time END) as avg_response_time
            FROM status_history h
            WHERE h.checked_at >= {ph}
            GROUP BY h.device_id
        ''', (start_date,))
        
        stats_map = {}
        for row in self._rows_to_dicts(cursor.fetchall()):
            device_id = row['device_id']
            total = row['total_checks']
            up = row['up_checks']
            down = row['down_checks']
            slow = row['slow_checks']
            available = up + slow
            uptime = (available / total * 100) if total > 0 else None
            
            stats_map[device_id] = {
                'uptime_percent': round(uptime, 4) if uptime else None,
                'total_checks': total,
                'up_checks': up,
                'down_checks': down,
                'slow_checks': slow,
                'avg_response_time': round(row['avg_response_time'], 2) if row['avg_response_time'] else None,
                'days': days
            }
        
        self.release_connection(conn)
        
        # Combine with device info
        devices = self.get_all_devices()
        result = []
        
        empty_stats = {
            'uptime_percent': None,
            'total_checks': 0,
            'up_checks': 0,
            'down_checks': 0,
            'slow_checks': 0,
            'avg_response_time': None,
            'days': days
        }
        
        for device in devices:
            stats = stats_map.get(device['id'], empty_stats)
            
            uptime = stats['uptime_percent']
            if uptime is None:
                sla_status = 'no_data'
            elif uptime >= sla_target:
                sla_status = 'met'
            elif uptime >= sla_target - 1:
                sla_status = 'warning'
            else:
                sla_status = 'breached'
            
            result.append({
                'id': device['id'],
                'name': device['name'],
                'ip_address': device['ip_address'],
                'device_type': device.get('device_type'),
                'location': device.get('location'),
                'current_status': device.get('status'),
                'sla_target': sla_target,
                'sla_status': sla_status,
                **stats
            })
        
        return result
    
    def cleanup_old_data(self):
        """Remove old data beyond retention period (works with both SQLite and PostgreSQL)"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        
        cutoff_date = (datetime.now() - timedelta(days=Config.RETENTION_DAYS)).isoformat()
        
        try:
            # Delete old status history
            cursor.execute(f'DELETE FROM status_history WHERE checked_at < {ph}', (cutoff_date,))
            deleted_history = cursor.rowcount
            
            # Delete old alert history  
            cursor.execute(f'DELETE FROM alert_history WHERE created_at < {ph}', (cutoff_date,))
            deleted_alerts = cursor.rowcount
            
            # Delete old bandwidth history (7-day retention for bandwidth data)
            bw_cutoff = (datetime.now() - timedelta(days=7)).isoformat()
            cursor.execute(f'DELETE FROM bandwidth_history WHERE sampled_at < {ph}', (bw_cutoff,))
            deleted_bw = cursor.rowcount
            
            conn.commit()
            
            # PostgreSQL: VACUUM ANALYZE for space reclaim and stats update
            if self.db_type == 'postgresql':
                conn.autocommit = True
                cursor.execute('VACUUM ANALYZE status_history')
                cursor.execute('VACUUM ANALYZE alert_history')
                conn.autocommit = False
            
            print(f"[DB Cleanup] Deleted {deleted_history} old status records, {deleted_alerts} old alerts, {deleted_bw} old bandwidth samples (retention: {Config.RETENTION_DAYS} days)")
            
        except Exception as e:
            conn.rollback()
            print(f"[DB Cleanup] Error: {e}")
        finally:
            self.release_connection(conn)

    # =========================================================================
    # Bandwidth Monitoring Methods
    # =========================================================================
    
    def save_bandwidth_sample(self, device_id, if_index, if_name,
                              bytes_in, bytes_out,
                              bps_in=None, bps_out=None,
                              if_speed=None, util_in=None, util_out=None):
        """Save a bandwidth sample for one interface"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        now = datetime.now().isoformat()
        try:
            cursor.execute(f'''
                INSERT INTO bandwidth_history
                    (device_id, if_index, if_name, bytes_in, bytes_out,
                     bps_in, bps_out, if_speed, util_in, util_out, sampled_at)
                VALUES ({self._ph(11)})
            ''', (device_id, if_index, if_name, bytes_in, bytes_out,
                  bps_in, bps_out, if_speed, util_in, util_out, now))
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"[BW] save_bandwidth_sample error: {e}")
        finally:
            self.release_connection(conn)
    
    def get_last_bandwidth_sample(self, device_id, if_index):
        """Get the most recent bandwidth sample for a device/interface (for delta calc)"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        cursor.execute(f'''
            SELECT * FROM bandwidth_history
            WHERE device_id = {ph} AND if_index = {ph}
            ORDER BY sampled_at DESC
            LIMIT 1
        ''', (device_id, if_index))
        row = cursor.fetchone()
        self.release_connection(conn)
        return self._row_to_dict(row)
    
    def get_bandwidth_history(self, device_id, if_index=None, minutes=60, limit=500):
        """Get bandwidth time-series for a device (and optionally a specific interface)"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        
        cutoff = (datetime.now() - timedelta(minutes=minutes)).isoformat()
        params = [device_id, cutoff]
        query = f'''
            SELECT * FROM bandwidth_history
            WHERE device_id = {ph} AND sampled_at >= {ph}
        '''
        if if_index is not None:
            query += f' AND if_index = {ph}'
            params.append(if_index)
        query += ' ORDER BY if_index ASC, sampled_at ASC'
        if limit:
            query += f' LIMIT {ph}'
            params.append(limit)
        
        cursor.execute(query, params)
        rows = self._rows_to_dicts(cursor.fetchall())
        self.release_connection(conn)
        return rows
    
    def get_latest_bandwidth_all_interfaces(self, device_id):
        """Get most recent sample per interface for a device"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        
        if self.db_type == 'postgresql':
            cursor.execute(f'''
                SELECT DISTINCT ON (if_index) *
                FROM bandwidth_history
                WHERE device_id = {ph}
                ORDER BY if_index, sampled_at DESC
            ''', (device_id,))
        else:
            cursor.execute(f'''
                SELECT * FROM bandwidth_history
                WHERE id IN (
                    SELECT MAX(id) FROM bandwidth_history
                    WHERE device_id = {ph}
                    GROUP BY if_index
                )
                ORDER BY if_index
            ''', (device_id,))
        
        rows = self._rows_to_dicts(cursor.fetchall())
        self.release_connection(conn)
        return rows
    
    def get_top_bandwidth_interfaces(self, minutes=5, top_n=10):
        """Get top N most active interfaces across all devices (by bps_in + bps_out)"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        
        cutoff = (datetime.now() - timedelta(minutes=minutes)).isoformat()
        cursor.execute(f'''
            SELECT b.device_id, d.name as device_name, d.ip_address,
                   b.if_index, b.if_name,
                   AVG(b.bps_in) as avg_bps_in,
                   AVG(b.bps_out) as avg_bps_out,
                   MAX(b.bps_in) as max_bps_in,
                   MAX(b.bps_out) as max_bps_out,
                   AVG(b.util_in) as avg_util_in,
                   AVG(b.util_out) as avg_util_out,
                   b.if_speed
            FROM bandwidth_history b
            JOIN devices d ON b.device_id = d.id
            WHERE b.sampled_at >= {ph}
            GROUP BY b.device_id, d.name, d.ip_address, b.if_index, b.if_name, b.if_speed
            ORDER BY (AVG(b.bps_in) + AVG(b.bps_out)) DESC
            LIMIT {ph}
        ''', (cutoff, top_n))
        
        rows = self._rows_to_dicts(cursor.fetchall())
        self.release_connection(conn)
        return rows

    def get_bandwidth_interfaces_by_ids(self, interface_list, minutes=5):
        """
        Get bandwidth data for a specific list of interfaces.
        interface_list: list of (device_id, if_index) tuples
        """
        if not interface_list:
            return []
            
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        
        cutoff = (datetime.now() - timedelta(minutes=minutes)).isoformat()
        
        results = []
        for device_id, if_index in interface_list:
            cursor.execute(f'''
                SELECT b.device_id, d.name as device_name, d.ip_address as hostname,
                       b.if_index, b.if_name,
                       AVG(b.bps_in) as avg_bps_in,
                       AVG(b.bps_out) as avg_bps_out,
                       MAX(b.bps_in) as max_bps_in,
                       MAX(b.bps_out) as max_bps_out,
                       AVG(b.util_in) as avg_util_in,
                       AVG(b.util_out) as avg_util_out,
                       b.if_speed
                FROM bandwidth_history b
                JOIN devices d ON b.device_id = d.id
                WHERE b.device_id = {ph} AND b.if_index = {ph} AND b.sampled_at >= {ph}
                GROUP BY b.device_id, d.name, d.ip_address, b.if_index, b.if_name, b.if_speed
            ''', (device_id, if_index, cutoff))
            row = cursor.fetchone()
            if row:
                results.append(self._row_to_dict(row))
        
        self.release_connection(conn)
        return results

    # =========================================================================
    # User Management Methods
    # =========================================================================
    
    def get_user_by_username(self, username):
        """Get a user by username"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute(f'SELECT * FROM users WHERE username = {self._ph()}', (username,))
        row = cursor.fetchone()
        self.release_connection(conn)
        return self._row_to_dict(row)
    
    def get_user_by_id(self, user_id):
        """Get a user by ID"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute(f'SELECT * FROM users WHERE id = {self._ph()}', (user_id,))
        row = cursor.fetchone()
        self.release_connection(conn)
        return self._row_to_dict(row)
    
    def get_ldap_settings(self):
        """Get all LDAP settings as a dict"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute('SELECT setting_key, setting_value FROM ldap_settings')
        rows = cursor.fetchall()
        self.release_connection(conn)
        return {row['setting_key']: row['setting_value'] for row in rows}

    def save_ldap_setting(self, key, value):
        """Save an LDAP setting"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        if self.db_type == 'postgresql':
            cursor.execute(f'''
                INSERT INTO ldap_settings (setting_key, setting_value, updated_at) 
                VALUES ({ph}, {ph}, CURRENT_TIMESTAMP)
                ON CONFLICT (setting_key) DO UPDATE SET setting_value = EXCLUDED.setting_value, updated_at = CURRENT_TIMESTAMP
            ''', (key, str(value)))
        else:
            cursor.execute(f'''
                INSERT OR REPLACE INTO ldap_settings (setting_key, setting_value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (key, str(value)))
        conn.commit()
        self.release_connection(conn)
        return True

    # =========================================================================
    # SSO (OAuth2/OIDC) Settings Methods
    # =========================================================================

    def get_sso_settings(self):
        """Get all SSO settings as a dict (stored in ldap_settings table with sso_ prefix)"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        cursor.execute(f"SELECT setting_key, setting_value FROM ldap_settings WHERE setting_key LIKE {ph}", ('sso_%',))
        rows = cursor.fetchall()
        self.release_connection(conn)
        return {row['setting_key']: row['setting_value'] for row in rows}

    def save_sso_setting(self, key, value):
        """Save an SSO setting (stored in ldap_settings table)"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        if self.db_type == 'postgresql':
            cursor.execute(f'''
                INSERT INTO ldap_settings (setting_key, setting_value, updated_at) 
                VALUES ({ph}, {ph}, CURRENT_TIMESTAMP)
                ON CONFLICT (setting_key) DO UPDATE SET setting_value = EXCLUDED.setting_value, updated_at = CURRENT_TIMESTAMP
            ''', (key, str(value)))
        else:
            cursor.execute(f'''
                INSERT OR REPLACE INTO ldap_settings (setting_key, setting_value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (key, str(value)))
        conn.commit()
        self.release_connection(conn)
        return True

    def authenticate_ldap(self, username, password):
        """
        Authenticate a user against LDAP/AD.
        Returns user info (dict) on success, None on failure.
        """
        settings = self.get_ldap_settings()
        if settings.get('ldap_enabled', 'false').lower() != 'true':
            return None

        import ldap3
        from ldap3 import Server, Connection, ALL, Tls
        import ssl

        try:
            server_url = settings.get('ldap_server')
            port = int(settings.get('ldap_port', 389))
            use_ssl = settings.get('ldap_use_ssl', 'false').lower() == 'true'
            
            if not server_url:
                return None

            # Setup server
            tls = None
            if use_ssl:
                tls = Tls(validate=ssl.CERT_NONE, version=ssl.PROTOCOL_TLSv1_2)
            
            server = Server(server_url, port=port, use_ssl=use_ssl, tls=tls, get_info=ALL)
            
            # Bind with admin user to find the user DN
            bind_dn = settings.get('ldap_bind_dn')
            bind_pw = settings.get('ldap_bind_password')
            
            if bind_dn and bind_pw:
                conn = Connection(server, user=bind_dn, password=bind_pw, auto_bind=True)
            else:
                # Anonymous bind
                conn = Connection(server, auto_bind=True)

            # Search for the user
            base_dn = settings.get('ldap_base_dn', '')
            user_filter = settings.get('ldap_user_filter', '(sAMAccountName={username})').replace('{username}', username)
            
            conn.search(base_dn, user_filter, attributes=['displayName', 'mail', 'cn'])
            
            if not conn.entries:
                conn.unbind()
                return None
            
            user_dn = conn.entries[0].entry_dn
            user_info = {
                'username': username,
                'display_name': str(conn.entries[0].displayName) if hasattr(conn.entries[0], 'displayName') else username,
                'email': str(conn.entries[0].mail) if hasattr(conn.entries[0], 'mail') else None
            }
            conn.unbind()

            # Now try to bind as the user to verify password
            user_conn = Connection(server, user=user_dn, password=password)
            if user_conn.bind():
                user_conn.unbind()
                return user_info
            
            return None
        except Exception as e:
            print(f"[LDAP] Auth error for {username}: {e}")
            return None

    def authenticate_user(self, username, password):
        """Authenticate a user and return user data if successful"""
        from werkzeug.security import check_password_hash
        
        user = self.get_user_by_username(username)
        
        # 1. Try Local Authentication first if user exists
        if user:
            if not user.get('is_active', True):
                return None
                
            # Check if it's a local user or LDAP user with local fallback
            if user.get('auth_type', 'local') == 'local':
                if check_password_hash(user['password_hash'], password):
                    self.update_last_login(user['id'])
                    return user
            elif user.get('auth_type') == 'ldap':
                # LDAP user - try LDAP bind
                ldap_res = self.authenticate_ldap(username, password)
                if ldap_res:
                    self.update_last_login(user['id'])
                    # Optional: update display_name/email from LDAP
                    return user
                return None

        # 2. Try LDAP Authentication (Auto-provisioning)
        settings = self.get_ldap_settings()
        if settings.get('ldap_enabled', 'false').lower() == 'true' and settings.get('ldap_auto_create', 'true').lower() == 'true':
            ldap_res = self.authenticate_ldap(username, password)
            if ldap_res:
                # User authenticated via LDAP but not in local DB yet
                # Auto-create local profile (Option A)
                role = settings.get('ldap_default_role', 'viewer')
                res = self.add_user(
                    username=username,
                    password='LDAP_EXTERNAL_AUTH', # Dummy password
                    role=role,
                    display_name=ldap_res.get('display_name'),
                    email=ldap_res.get('email')
                )
                if res['success']:
                    new_user = self.get_user_by_id(res['id'])
                    # Set auth_type to ldap
                    self.update_user(new_user['id'], auth_type='ldap')
                    self.update_last_login(new_user['id'])
                    return new_user

        return None
    
    def update_last_login(self, user_id):
        """Update the last login timestamp for a user"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        cursor.execute(f'''
            UPDATE users SET last_login = {ph} WHERE id = {ph}
        ''', (datetime.now().isoformat(), user_id))
        conn.commit()
        self.release_connection(conn)
    
    # =========================================================================
    # MFA (Two-Factor Authentication) Methods
    # =========================================================================
    
    def enable_mfa(self, user_id, secret):
        """Enable MFA for a user by saving the TOTP secret"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        try:
            if self.db_type == 'postgresql':
                cursor.execute(f'UPDATE users SET mfa_secret = {ph}, mfa_enabled = TRUE WHERE id = {ph}', (secret, user_id))
            else:
                cursor.execute(f'UPDATE users SET mfa_secret = {ph}, mfa_enabled = 1 WHERE id = {ph}', (secret, user_id))
            conn.commit()
            self.release_connection(conn)
            return {'success': True}
        except Exception as e:
            conn.rollback()
            self.release_connection(conn)
            return {'success': False, 'error': str(e)}
    
    def disable_mfa(self, user_id):
        """Disable MFA for a user"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        try:
            if self.db_type == 'postgresql':
                cursor.execute(f'UPDATE users SET mfa_secret = NULL, mfa_enabled = FALSE WHERE id = {ph}', (user_id,))
            else:
                cursor.execute(f'UPDATE users SET mfa_secret = NULL, mfa_enabled = 0 WHERE id = {ph}', (user_id,))
            conn.commit()
            self.release_connection(conn)
            return {'success': True}
        except Exception as e:
            conn.rollback()
            self.release_connection(conn)
            return {'success': False, 'error': str(e)}
    
    def get_mfa_secret(self, user_id):
        """Get the MFA secret for a user"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        cursor.execute(f'SELECT mfa_secret, mfa_enabled FROM users WHERE id = {ph}', (user_id,))
        row = cursor.fetchone()
        self.release_connection(conn)
        if row:
            r = self._row_to_dict(row)
            return r.get('mfa_secret'), bool(r.get('mfa_enabled'))
        return None, False

    def enable_mfa(self, user_id, secret):
        """Enable MFA for a user and save the secret"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        try:
            if self.db_type == 'postgresql':
                mfa_enabled = True
            else:
                mfa_enabled = 1
            
            cursor.execute(f'UPDATE users SET mfa_secret = {ph}, mfa_enabled = {ph} WHERE id = {ph}',
                          (secret, mfa_enabled, user_id))
            conn.commit()
            self.release_connection(conn)
            return {'success': True}
        except Exception as e:
            conn.rollback()
            self.release_connection(conn)
            return {'success': False, 'error': str(e)}

    def disable_mfa(self, user_id):
        """Disable MFA for a user"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        try:
            if self.db_type == 'postgresql':
                mfa_enabled = False
            else:
                mfa_enabled = 0
            
            cursor.execute(f'UPDATE users SET mfa_secret = NULL, mfa_enabled = {ph} WHERE id = {ph}',
                          (mfa_enabled, user_id))
            conn.commit()
            self.release_connection(conn)
            return {'success': True}
        except Exception as e:
            conn.rollback()
            self.release_connection(conn)
            return {'success': False, 'error': str(e)}

    
    def get_all_users(self):
        """Get all users (excluding password hashes)"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute('''
            SELECT id, username, role, display_name, email, telegram_chat_id, is_active, auth_type,
                   mfa_enabled, last_login, created_at, updated_at 
            FROM users ORDER BY created_at DESC
        ''')
        users = self._rows_to_dicts(cursor.fetchall())
        self.release_connection(conn)
        return users
    
    def add_user(self, username, password, role='viewer', display_name=None, email=None, telegram_chat_id=None, auth_type='local'):
        """Add a new user"""
        from werkzeug.security import generate_password_hash
        
        if role not in ['admin', 'operator', 'viewer']:
            return {'success': False, 'error': 'Invalid role. Must be admin, operator, or viewer'}
        
        conn = self.get_connection()
        cursor = self._cursor(conn)
        
        # LDAP users use a dummy password hash
        pw_hash = 'LDAP_EXTERNAL_AUTH' if password == 'LDAP_EXTERNAL_AUTH' else generate_password_hash(password)
        
        try:
            if self.db_type == 'postgresql':
                cursor.execute('''
                    INSERT INTO users (username, password_hash, role, display_name, email, telegram_chat_id, auth_type, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                ''', (username, pw_hash, role, display_name, email, telegram_chat_id, auth_type,
                      datetime.now().isoformat()))
                user_id = cursor.fetchone()['id']
            else:
                cursor.execute('''
                    INSERT INTO users (username, password_hash, role, display_name, email, telegram_chat_id, auth_type, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (username, pw_hash, role, display_name, email, telegram_chat_id, auth_type,
                      datetime.now().isoformat()))
                user_id = cursor.lastrowid
            conn.commit()
            self.release_connection(conn)
            return {'success': True, 'id': user_id}
        except Exception as e:
            conn.rollback()
            self.release_connection(conn)
            if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
                return {'success': False, 'error': 'Username already exists'}
            return {'success': False, 'error': str(e)}
    
    def update_user(self, user_id, role=None, display_name=None, email=None, 
                    telegram_chat_id=None, is_active=None, password=None, auth_type=None):
        """Update user details"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        
        updates = []
        params = []
        
        if role is not None:
            if role not in ['admin', 'operator', 'viewer']:
                self.release_connection(conn)
                return {'success': False, 'error': 'Invalid role'}
            updates.append(f'role = {ph}')
            params.append(role)
        
        if display_name is not None:
            updates.append(f'display_name = {ph}')
            params.append(display_name)
        
        if email is not None:
            updates.append(f'email = {ph}')
            params.append(email)
            
        if telegram_chat_id is not None:
            updates.append(f'telegram_chat_id = {ph}')
            params.append(telegram_chat_id)
            
        if auth_type is not None:
            updates.append(f'auth_type = {ph}')
            params.append(auth_type)
        
        if is_active is not None:
            updates.append(f'is_active = {ph}')
            if self.db_type == 'postgresql':
                params.append(bool(is_active))
            else:
                params.append(1 if is_active else 0)
        
        if password is not None:
            from werkzeug.security import generate_password_hash
            updates.append(f'password_hash = {ph}')
            params.append(generate_password_hash(password))
        
        if not updates:
            self.release_connection(conn)
            return {'success': False, 'error': 'No updates provided'}
        
        updates.append(f'updated_at = {ph}')
        params.append(datetime.now().isoformat())
        params.append(user_id)
        
        try:
            cursor.execute(f'''
                UPDATE users SET {', '.join(updates)} WHERE id = {ph}
            ''', params)
            conn.commit()
            self.release_connection(conn)
            return {'success': True}
        except Exception as e:
            conn.rollback()
            self.release_connection(conn)
            return {'success': False, 'error': str(e)}
    
    def delete_user(self, user_id):
        """Delete a user (cannot delete the last admin)"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        
        cursor.execute(f'SELECT role FROM users WHERE id = {ph}', (user_id,))
        user = cursor.fetchone()
        if user:
            u = self._row_to_dict(user)
            if u['role'] == 'admin':
                cursor.execute(f'SELECT COUNT(*) as count FROM users WHERE role = {ph}', ('admin',))
                admin_count = self._row_to_dict(cursor.fetchone())['count']
                if admin_count <= 1:
                    self.release_connection(conn)
                    return {'success': False, 'error': 'Cannot delete the last admin user'}
        
        cursor.execute(f'DELETE FROM users WHERE id = {ph}', (user_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        self.release_connection(conn)
        
        return {'success': deleted}

    # =========================================================================
    # Dashboard Methods
    # =========================================================================
    
    def create_dashboard(self, name, layout_config, description=None, created_by=None, is_public=0):
        """Create a new dashboard"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        
        if self.db_type == 'postgresql':
            is_public_val = bool(is_public)
            cursor.execute('''
                INSERT INTO dashboards (name, layout_config, description, created_by, is_public, display_order)
                VALUES (%s, %s, %s, %s, %s, (SELECT COALESCE(MAX(display_order), 0) + 1 FROM dashboards))
                RETURNING id
            ''', (name, layout_config, description, created_by, is_public_val))
            dashboard_id = cursor.fetchone()['id']
        else:
            cursor.execute('''
                INSERT INTO dashboards (name, layout_config, description, created_by, is_public, display_order)
                VALUES (?, ?, ?, ?, ?, (SELECT COALESCE(MAX(display_order), 0) + 1 FROM dashboards))
            ''', (name, layout_config, description, created_by, is_public))
            dashboard_id = cursor.lastrowid
        
        conn.commit()
        self.release_connection(conn)
        return {'success': True, 'id': dashboard_id}
    
    def get_dashboards(self, user_id=None):
        """Get all dashboards visible to a user"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        
        if user_id:
            if self.db_type == 'postgresql':
                cursor.execute(f'''
                    SELECT d.*, u.username as creator_name 
                    FROM dashboards d
                    LEFT JOIN users u ON d.created_by = u.id
                    WHERE d.is_public = TRUE OR d.created_by = {ph}
                    ORDER BY d.display_order ASC, d.created_at DESC
                ''', (user_id,))
            else:
                cursor.execute(f'''
                    SELECT d.*, u.username as creator_name 
                    FROM dashboards d
                    LEFT JOIN users u ON d.created_by = u.id
                    WHERE d.is_public = 1 OR d.created_by = {ph}
                    ORDER BY d.display_order ASC, d.created_at DESC
                ''', (user_id,))
        else:
            cursor.execute('''
                SELECT d.*, u.username as creator_name 
                FROM dashboards d
                LEFT JOIN users u ON d.created_by = u.id
                ORDER BY d.display_order ASC, d.created_at DESC
            ''')
            
        dashboards = self._rows_to_dicts(cursor.fetchall())
        self.release_connection(conn)
        return dashboards
    
    def get_dashboard(self, dashboard_id):
        """Get a specific dashboard"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        
        cursor.execute(f'''
            SELECT d.*, u.username as creator_name 
            FROM dashboards d
            LEFT JOIN users u ON d.created_by = u.id
            WHERE d.id = {self._ph()}
        ''', (dashboard_id,))
        
        result = cursor.fetchone()
        self.release_connection(conn)
        return self._row_to_dict(result)
    
    def update_dashboard(self, dashboard_id, name=None, layout_config=None, description=None, is_public=None):
        """Update a dashboard"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        
        updates = []
        params = []
        
        if name is not None:
            updates.append(f'name = {ph}')
            params.append(name)
        if layout_config is not None:
            updates.append(f'layout_config = {ph}')
            params.append(layout_config)
        if description is not None:
            updates.append(f'description = {ph}')
            params.append(description)
        if is_public is not None:
            updates.append(f'is_public = {ph}')
            if self.db_type == 'postgresql':
                params.append(bool(is_public))
            else:
                params.append(is_public)
            
        updates.append(f'updated_at = {ph}')
        params.append(datetime.now().isoformat())
        
        if updates:
            params.append(dashboard_id)
            cursor.execute(f'''
                UPDATE dashboards 
                SET {', '.join(updates)}
                WHERE id = {ph}
            ''', params)
            conn.commit()
            
        self.release_connection(conn)
        return {'success': True}
    
    def delete_dashboard(self, dashboard_id):
        """Delete a dashboard"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute(f'DELETE FROM dashboards WHERE id = {self._ph()}', (dashboard_id,))
        conn.commit()
        self.release_connection(conn)
        return {'success': True}

    def reorder_dashboards(self, dashboard_ids):
        """Update display order for dashboards"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        
        try:
            for index, d_id in enumerate(dashboard_ids):
                cursor.execute(f'UPDATE dashboards SET display_order = {ph} WHERE id = {ph}', (index, d_id))
            conn.commit()
            return {'success': True}
        except Exception as e:
            conn.rollback()
            return {'success': False, 'error': str(e)}
        finally:
            self.release_connection(conn)

    # =========================================================================
    # Dashboard Template Methods
    # =========================================================================

    def create_dashboard_template(self, name, layout_config, description=None,
                                   variables=None, category='custom', created_by=None):
        """Create a new dashboard template"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        
        try:
            if self.db_type == 'postgresql':
                cursor.execute('''
                    INSERT INTO dashboard_templates (name, description, layout_config, variables, category, created_by, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                ''', (name, description, layout_config, variables, category, created_by,
                      datetime.now().isoformat()))
                template_id = cursor.fetchone()['id']
            else:
                cursor.execute('''
                    INSERT INTO dashboard_templates (name, description, layout_config, variables, category, created_by, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (name, description, layout_config, variables, category, created_by,
                      datetime.now().isoformat()))
                template_id = cursor.lastrowid
            conn.commit()
            self.release_connection(conn)
            return {'success': True, 'id': template_id}
        except Exception as e:
            conn.rollback()
            self.release_connection(conn)
            return {'success': False, 'error': str(e)}

    def get_dashboard_templates(self, category=None):
        """Get all dashboard templates, optionally filtered by category"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        
        if category:
            cursor.execute(f'''
                SELECT dt.*, u.username as creator_name
                FROM dashboard_templates dt
                LEFT JOIN users u ON dt.created_by = u.id
                WHERE dt.category = {ph}
                ORDER BY dt.created_at DESC
            ''', (category,))
        else:
            cursor.execute('''
                SELECT dt.*, u.username as creator_name
                FROM dashboard_templates dt
                LEFT JOIN users u ON dt.created_by = u.id
                ORDER BY dt.created_at DESC
            ''')
        
        templates = self._rows_to_dicts(cursor.fetchall())
        self.release_connection(conn)
        return templates

    def get_dashboard_template(self, template_id):
        """Get a specific dashboard template"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute(f'''
            SELECT dt.*, u.username as creator_name
            FROM dashboard_templates dt
            LEFT JOIN users u ON dt.created_by = u.id
            WHERE dt.id = {self._ph()}
        ''', (template_id,))
        result = cursor.fetchone()
        self.release_connection(conn)
        return self._row_to_dict(result)

    def delete_dashboard_template(self, template_id):
        """Delete a dashboard template"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute(f'DELETE FROM dashboard_templates WHERE id = {self._ph()}', (template_id,))
        conn.commit()
        self.release_connection(conn)
        return {'success': True}

    # =========================================================================
    # Sub-Topology Methods
    # =========================================================================

    def create_sub_topology(self, name, description=None, created_by=None, background_image=None, background_zoom=100, node_positions=None, background_opacity=100, theme_mode='standard'):
        """Create a new sub-topology"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        
        if self.db_type == 'postgresql':
            cursor.execute('''
                INSERT INTO sub_topologies (name, description, created_by, background_image, background_zoom, node_positions, background_opacity, theme_mode)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (name, description, created_by, background_image, background_zoom, node_positions, background_opacity, theme_mode))
            sub_topo_id = cursor.fetchone()['id']
        else:
            cursor.execute('''
                INSERT INTO sub_topologies (name, description, created_by, background_image, background_zoom, node_positions, background_opacity, theme_mode)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (name, description, created_by, background_image, background_zoom, node_positions, background_opacity, theme_mode))
            sub_topo_id = cursor.lastrowid
        conn.commit()
        self.release_connection(conn)
        return {'success': True, 'id': sub_topo_id}

    def get_all_sub_topologies(self):
        """Get all sub-topologies"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute('SELECT * FROM sub_topologies ORDER BY name')
        result = self._rows_to_dicts(cursor.fetchall())
        self.release_connection(conn)
        return result

    def get_sub_topology(self, sub_topo_id):
        """Get a sub-topology with its devices and connections"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        
        cursor.execute(f'SELECT * FROM sub_topologies WHERE id = {ph}', (sub_topo_id,))
        sub_topo = cursor.fetchone()
        if not sub_topo:
            self.release_connection(conn)
            return None
        
        result = self._row_to_dict(sub_topo)
        
        cursor.execute(f'''
            SELECT d.* FROM devices d
            JOIN sub_topology_devices std ON d.id = std.device_id
            WHERE std.sub_topology_id = {ph}
            ORDER BY d.name
        ''', (sub_topo_id,))
        result['devices'] = self._rows_to_dicts(cursor.fetchall())
        
        cursor.execute(f'''
            SELECT * FROM sub_topology_connections
            WHERE sub_topology_id = {ph}
        ''', (sub_topo_id,))
        result['connections'] = self._rows_to_dicts(cursor.fetchall())
        
        self.release_connection(conn)
        return result

    def update_sub_topology(self, sub_topo_id, name=None, description=None, device_ids=None, connections=None, background_image=None, background_zoom=None, node_positions=None, background_opacity=None, theme_mode=None):
        """Update a sub-topology"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        
        updates = []
        params = []
        if name is not None:
            updates.append(f'name = {ph}')
            params.append(name)
        if description is not None:
            updates.append(f'description = {ph}')
            params.append(description)
        if background_image is not None:
            updates.append(f'background_image = {ph}')
            params.append(background_image)
        if background_zoom is not None:
            updates.append(f'background_zoom = {ph}')
            params.append(background_zoom)
        if node_positions is not None:
            updates.append(f'node_positions = {ph}')
            params.append(node_positions)
        if background_opacity is not None:
            updates.append(f'background_opacity = {ph}')
            params.append(background_opacity)
        if theme_mode is not None:
            updates.append(f'theme_mode = {ph}')
            params.append(theme_mode)
        updates.append(f'updated_at = {ph}')
        params.append(datetime.now().isoformat())
        
        if updates:
            params.append(sub_topo_id)
            cursor.execute(f"UPDATE sub_topologies SET {', '.join(updates)} WHERE id = {ph}", params)
        
        # Replace devices
        if device_ids is not None:
            cursor.execute(f'DELETE FROM sub_topology_devices WHERE sub_topology_id = {ph}', (sub_topo_id,))
            for did in device_ids:
                cursor.execute(f'''
                    INSERT INTO sub_topology_devices (sub_topology_id, device_id)
                    VALUES ({self._ph(2)})
                ''', (sub_topo_id, did))
        
        # Replace connections
        if connections is not None:
            cursor.execute(f'DELETE FROM sub_topology_connections WHERE sub_topology_id = {ph}', (sub_topo_id,))
            for conn_item in connections:
                cursor.execute(f'''
                    INSERT INTO sub_topology_connections (sub_topology_id, device_id, connected_to)
                    VALUES ({self._ph(3)})
                ''', (sub_topo_id, conn_item['device_id'], conn_item['connected_to']))
        
        conn.commit()
        self.release_connection(conn)
        return {'success': True}

    def delete_sub_topology(self, sub_topo_id):
        """Delete a sub-topology and its related data"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        cursor.execute(f'DELETE FROM sub_topology_connections WHERE sub_topology_id = {ph}', (sub_topo_id,))
        cursor.execute(f'DELETE FROM sub_topology_devices WHERE sub_topology_id = {ph}', (sub_topo_id,))
        cursor.execute(f'DELETE FROM sub_topologies WHERE id = {ph}', (sub_topo_id,))
        conn.commit()
        self.release_connection(conn)
        return {'success': True}

    # =========================================================================
    # Custom SNMP OID Methods
    # =========================================================================

    def add_custom_oid(self, device_id, oid, name, unit=''):
        """Add a custom SNMP OID to monitor for a device"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        try:
            if self.db_type == 'postgresql':
                cursor.execute('''
                    INSERT INTO custom_oids (device_id, oid, name, unit)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                ''', (device_id, oid, name, unit))
                oid_id = cursor.fetchone()['id']
            else:
                cursor.execute('''
                    INSERT INTO custom_oids (device_id, oid, name, unit)
                    VALUES (?, ?, ?, ?)
                ''', (device_id, oid, name, unit))
                oid_id = cursor.lastrowid
            conn.commit()
            self.release_connection(conn)
            return {'success': True, 'id': oid_id}
        except Exception as e:
            if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
                conn.rollback()
                self.release_connection(conn)
                return {'success': False, 'error': 'This OID already exists for this device'}
            conn.rollback()
            self.release_connection(conn)
            return {'success': False, 'error': str(e)}

    def get_custom_oids(self, device_id):
        """Get all custom OIDs for a device"""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            cursor.execute(
                f'SELECT * FROM custom_oids WHERE device_id = {self._ph()} ORDER BY id',
                (device_id,)
            )
            oids = self._rows_to_dicts(cursor.fetchall())
            return oids
        finally:
            self.release_connection(conn)

    def update_custom_oid_value(self, oid_id, value):
        """Update the last queried value of a custom OID"""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            ph = self._ph()
            now = datetime.now().isoformat()
            cursor.execute(
                f'UPDATE custom_oids SET last_value = {ph}, last_checked = {ph} WHERE id = {ph}',
                (value, now, oid_id)
            )
            conn.commit()
        except Exception as e:
            if conn: conn.rollback()
            raise e
        finally:
            self.release_connection(conn)

    def delete_custom_oid(self, oid_id):
        """Delete a custom OID"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute(f'DELETE FROM custom_oids WHERE id = {self._ph()}', (oid_id,))
        conn.commit()
        self.release_connection(conn)
        return {'success': True}

    # =========================================================================
    # Job History Methods
    # =========================================================================

    def log_job_start(self, job_id, job_name):
        """Log that a job has started, return the history row ID"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        now = datetime.now().isoformat()
        try:
            if self.db_type == 'postgresql':
                cursor.execute('''
                    INSERT INTO job_history (job_id, job_name, status, started_at)
                    VALUES (%s, %s, 'running', %s)
                    RETURNING id
                ''', (job_id, job_name, now))
                row_id = cursor.fetchone()['id']
            else:
                cursor.execute('''
                    INSERT INTO job_history (job_id, job_name, status, started_at)
                    VALUES (?, ?, 'running', ?)
                ''', (job_id, job_name, now))
                row_id = cursor.lastrowid
            conn.commit()
            return row_id
        except Exception as e:
            conn.rollback()
            print(f"[DB] Failed to log job start: {e}")
            return None
        finally:
            self.release_connection(conn)

    def log_job_complete(self, history_id, result_summary=None):
        """Log that a job has completed successfully"""
        if not history_id:
            return
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        now = datetime.now().isoformat()
        try:
            cursor.execute(f'''
                UPDATE job_history 
                SET status = 'success', 
                    completed_at = {ph}, 
                    duration_seconds = EXTRACT(EPOCH FROM ({ph}::timestamp - started_at)),
                    result_summary = {ph}
                WHERE id = {ph}
            ''', (now, now, result_summary, history_id)) if self.db_type == 'postgresql' else \
            cursor.execute(f'''
                UPDATE job_history 
                SET status = 'success', 
                    completed_at = {ph},
                    duration_seconds = (julianday({ph}) - julianday(started_at)) * 86400,
                    result_summary = {ph}
                WHERE id = {ph}
            ''', (now, now, result_summary, history_id))
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"[DB] Failed to log job complete: {e}")
        finally:
            self.release_connection(conn)

    def log_job_error(self, history_id, error_message):
        """Log that a job has failed"""
        if not history_id:
            return
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        now = datetime.now().isoformat()
        try:
            if self.db_type == 'postgresql':
                cursor.execute(f'''
                    UPDATE job_history 
                    SET status = 'error', 
                        completed_at = {ph},
                        duration_seconds = EXTRACT(EPOCH FROM ({ph}::timestamp - started_at)),
                        error_message = {ph}
                    WHERE id = {ph}
                ''', (now, now, error_message, history_id))
            else:
                cursor.execute(f'''
                    UPDATE job_history 
                    SET status = 'error', 
                        completed_at = {ph},
                        duration_seconds = (julianday({ph}) - julianday(started_at)) * 86400,
                        error_message = {ph}
                    WHERE id = {ph}
                ''', (now, now, error_message, history_id))
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"[DB] Failed to log job error: {e}")
        finally:
            self.release_connection(conn)

    def get_job_history(self, job_id=None, limit=50):
        """Get job execution history, optionally filtered by job_id"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        if job_id:
            cursor.execute(f'''
                SELECT * FROM job_history 
                WHERE job_id = {ph} 
                ORDER BY created_at DESC LIMIT {limit}
            ''', (job_id,))
        else:
            cursor.execute(f'''
                SELECT * FROM job_history 
                ORDER BY created_at DESC LIMIT {limit}
            ''')
        rows = self._rows_to_dicts(cursor.fetchall())
        self.release_connection(conn)
        return rows

    def cleanup_job_history(self, days=7):
        """Remove job history older than specified days"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        cursor.execute(f'DELETE FROM job_history WHERE created_at < {ph}', (cutoff,))
        deleted = cursor.rowcount
        conn.commit()
        self.release_connection(conn)
        return deleted

    # =========================================================================
    # SNMP Trap Methods
    # =========================================================================

    def add_trap(self, source_ip, trap_oid, trap_name=None, severity='info',
                 varbinds=None, raw_data=None, device_id=None, device_name=None):
        """Store a received SNMP trap"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        now = datetime.now().isoformat()
        try:
            if self.db_type == 'postgresql':
                cursor.execute('''
                    INSERT INTO snmp_traps (source_ip, device_id, device_name, trap_oid,
                                           trap_name, severity, varbinds, raw_data, received_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                ''', (source_ip, device_id, device_name, trap_oid,
                      trap_name, severity, varbinds, raw_data, now))
                trap_id = cursor.fetchone()['id']
            else:
                cursor.execute('''
                    INSERT INTO snmp_traps (source_ip, device_id, device_name, trap_oid,
                                           trap_name, severity, varbinds, raw_data, received_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (source_ip, device_id, device_name, trap_oid,
                      trap_name, severity, varbinds, raw_data, now))
                trap_id = cursor.lastrowid
            conn.commit()
            return trap_id
        except Exception as e:
            conn.rollback()
            print(f"[DB] Failed to add trap: {e}")
            return None
        finally:
            self.release_connection(conn)

    def get_traps(self, limit=100, offset=0, severity=None, source_ip=None, acknowledged=None):
        """Get traps with optional filters"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        
        conditions = []
        params = []
        if severity:
            conditions.append(f"severity = {ph}")
            params.append(severity)
        if source_ip:
            conditions.append(f"source_ip = {ph}")
            params.append(source_ip)
        if acknowledged is not None:
            conditions.append(f"acknowledged = {ph}")
            params.append(int(acknowledged))
        
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        
        cursor.execute(f'''
            SELECT * FROM snmp_traps {where}
            ORDER BY received_at DESC LIMIT {limit} OFFSET {offset}
        ''', params)
        rows = self._rows_to_dicts(cursor.fetchall())
        
        # Get total count
        cursor.execute(f'SELECT COUNT(*) as cnt FROM snmp_traps {where}', params)
        total = cursor.fetchone()['cnt'] if self.db_type == 'postgresql' else cursor.fetchone()[0]
        
        self.release_connection(conn)
        return {'traps': rows, 'total': total}

    def acknowledge_trap(self, trap_id):
        """Acknowledge a trap"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute(f'UPDATE snmp_traps SET acknowledged = 1 WHERE id = {self._ph()}', (trap_id,))
        conn.commit()
        self.release_connection(conn)
        return {'success': True}

    def acknowledge_all_traps(self):
        """Acknowledge all unacknowledged traps"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute('UPDATE snmp_traps SET acknowledged = 1 WHERE acknowledged = 0')
        count = cursor.rowcount
        conn.commit()
        self.release_connection(conn)
        return {'success': True, 'count': count}

    def delete_trap(self, trap_id):
        """Delete a trap"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute(f'DELETE FROM snmp_traps WHERE id = {self._ph()}', (trap_id,))
        conn.commit()
        self.release_connection(conn)
        return {'success': True}

    def get_trap_stats(self):
        """Get trap statistics"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        stats = {}
        
        cursor.execute('SELECT COUNT(*) as cnt FROM snmp_traps')
        row = cursor.fetchone()
        stats['total'] = row['cnt'] if self.db_type == 'postgresql' else row[0]
        
        cursor.execute('SELECT COUNT(*) as cnt FROM snmp_traps WHERE acknowledged = 0')
        row = cursor.fetchone()
        stats['unacknowledged'] = row['cnt'] if self.db_type == 'postgresql' else row[0]
        
        cursor.execute("SELECT COUNT(*) as cnt FROM snmp_traps WHERE severity = 'critical'")
        row = cursor.fetchone()
        stats['critical'] = row['cnt'] if self.db_type == 'postgresql' else row[0]
        
        cursor.execute("SELECT COUNT(*) as cnt FROM snmp_traps WHERE severity = 'warning'")
        row = cursor.fetchone()
        stats['warning'] = row['cnt'] if self.db_type == 'postgresql' else row[0]
        
        self.release_connection(conn)
        return stats

    def cleanup_old_traps(self, days=30):
        """Remove traps older than specified days"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        cursor.execute(f'DELETE FROM snmp_traps WHERE received_at < {ph}', (cutoff,))
        deleted = cursor.rowcount
        conn.commit()
        self.release_connection(conn)
        return deleted

    # =========================================================================
    # Syslog Methods
    # =========================================================================

    def add_syslog(self, source_ip, facility, severity, program, message, device_id=None, device_name=None):
        """Store a received syslog message"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        now = datetime.now().isoformat()
        try:
            if self.db_type == 'postgresql':
                cursor.execute('''
                    INSERT INTO syslog_messages (source_ip, device_id, device_name, facility,
                                                severity, program, message, received_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                ''', (source_ip, device_id, device_name, facility,
                      severity, program, message, now))
                syslog_id = cursor.fetchone()['id']
            else:
                cursor.execute('''
                    INSERT INTO syslog_messages (source_ip, device_id, device_name, facility,
                                                severity, program, message, received_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (source_ip, device_id, device_name, facility,
                      severity, program, message, now))
                syslog_id = cursor.lastrowid
            conn.commit()
            return syslog_id
        except Exception as e:
            conn.rollback()
            print(f"[DB] Failed to add syslog: {e}")
            return None
        finally:
            self.release_connection(conn)

    def get_syslogs(self, limit=100, offset=0, severity=None, source_ip=None, search=None):
        """Get syslog messages with optional filters"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        
        conditions = []
        params = []
        if severity is not None:
            conditions.append(f"severity <= {ph}") # lower number = higher severity
            params.append(int(severity))
        if source_ip:
            conditions.append(f"source_ip = {ph}")
            params.append(source_ip)
        if search:
            conditions.append(f"message LIKE {ph}")
            params.append(f"%{search}%")
        
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        
        cursor.execute(f'''
            SELECT * FROM syslog_messages {where}
            ORDER BY received_at DESC LIMIT {limit} OFFSET {offset}
        ''', params)
        rows = self._rows_to_dicts(cursor.fetchall())
        
        # Get total count
        cursor.execute(f'SELECT COUNT(*) as cnt FROM syslog_messages {where}', params)
        total = cursor.fetchone()['cnt'] if self.db_type == 'postgresql' else cursor.fetchone()[0]
        
        self.release_connection(conn)
        return {'syslogs': rows, 'total': total}

    def get_syslog_stats(self):
        """Get syslog statistics based on severity levels"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        stats = {
            'total': 0,
            'emergency': 0, # 0
            'alert': 0,     # 1
            'critical': 0,  # 2
            'error': 0,     # 3
            'warning': 0,   # 4
            'notice': 0,    # 5
            'info': 0,      # 6
            'debug': 0      # 7
        }
        
        cursor.execute('SELECT severity, COUNT(*) as cnt FROM syslog_messages GROUP BY severity')
        rows = cursor.fetchall()
        
        for row in rows:
            sev = row['severity'] if self.db_type == 'postgresql' else row[0]
            cnt = row['cnt'] if self.db_type == 'postgresql' else row[1]
            stats['total'] += cnt
            
            if sev == 0: stats['emergency'] += cnt
            elif sev == 1: stats['alert'] += cnt
            elif sev == 2: stats['critical'] += cnt
            elif sev == 3: stats['error'] += cnt
            elif sev == 4: stats['warning'] += cnt
            elif sev == 5: stats['notice'] += cnt
            elif sev == 6: stats['info'] += cnt
            elif sev == 7: stats['debug'] += cnt
            
        self.release_connection(conn)
        return stats

    def cleanup_old_syslogs(self, days=30):
        """Remove syslog messages older than specified days"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        cursor.execute(f'DELETE FROM syslog_messages WHERE received_at < {ph}', (cutoff,))
        deleted = cursor.rowcount
        conn.commit()
        self.release_connection(conn)
        return deleted

    # =========================================================================
    # Audit Log Methods
    # =========================================================================

    def add_audit_log(self, user_id, username, action, category,
                      target_type=None, target_id=None, target_name=None,
                      details=None, ip_address=None):
        """Record an audit log entry"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        try:
            cursor.execute(f'''
                INSERT INTO audit_logs (user_id, username, action, category,
                    target_type, target_id, target_name, details, ip_address)
                VALUES ({self._ph(9)})
            ''', (user_id, username, action, category,
                  target_type, target_id, target_name, details, ip_address))
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"[AUDIT] Error logging audit event: {e}")
        finally:
            self.release_connection(conn)

    def get_audit_logs(self, limit=100, offset=0, username=None,
                       action=None, category=None, search=None):
        """Get paginated audit logs with filtering"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()

        conditions = []
        params = []

        if username:
            conditions.append(f'username = {ph}')
            params.append(username)
        if action:
            conditions.append(f'action = {ph}')
            params.append(action)
        if category:
            conditions.append(f'category = {ph}')
            params.append(category)
        if search:
            like_op = 'ILIKE' if self.db_type == 'postgresql' else 'LIKE'
            conditions.append(f'(target_name {like_op} {ph} OR details {like_op} {ph} OR username {like_op} {ph})')
            search_term = f'%{search}%'
            params.extend([search_term, search_term, search_term])

        where_clause = ''
        if conditions:
            where_clause = 'WHERE ' + ' AND '.join(conditions)

        # Get total count
        cursor.execute(f'SELECT COUNT(*) as cnt FROM audit_logs {where_clause}', params)
        row = cursor.fetchone()
        total = row['cnt'] if isinstance(row, dict) else row[0]

        # Get paginated results
        params_page = params + [limit, offset]
        cursor.execute(f'''
            SELECT * FROM audit_logs {where_clause}
            ORDER BY created_at DESC
            LIMIT {ph} OFFSET {ph}
        ''', params_page)

        logs = self._rows_to_dicts(cursor.fetchall())
        self.release_connection(conn)
        return {'logs': logs, 'total': total}

    def get_audit_stats(self):
        """Get audit log statistics by action type"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute('SELECT action, COUNT(*) as cnt FROM audit_logs GROUP BY action')
        rows = cursor.fetchall()

        stats = {'total': 0, 'login': 0, 'logout': 0, 'create': 0,
                 'update': 0, 'delete': 0, 'export': 0, 'import': 0, 'other': 0}
        for row in rows:
            if isinstance(row, dict):
                action, cnt = row['action'], row['cnt']
            else:
                action, cnt = row[0], row[1]
            stats['total'] += cnt
            if action in stats:
                stats[action] += cnt
            else:
                stats['other'] += cnt

        self.release_connection(conn)
        return stats

    def cleanup_old_audit_logs(self, days=90):
        """Remove audit logs older than specified days"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        cursor.execute(f'DELETE FROM audit_logs WHERE created_at < {ph}', (cutoff,))
        deleted = cursor.rowcount
        conn.commit()
        self.release_connection(conn)
        return deleted

    # =========================================================================
    # Custom Reports Methods
    # =========================================================================
    
    def get_custom_reports(self):
        """Get all custom reports"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute('SELECT * FROM custom_reports ORDER BY created_at DESC')
        reports = self._rows_to_dicts(cursor.fetchall())
        self.release_connection(conn)
        return reports

    def get_custom_report(self, report_id):
        """Get a specific custom report and its widgets"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        
        cursor.execute(f'SELECT * FROM custom_reports WHERE id = {ph}', (report_id,))
        report = self._row_to_dict(cursor.fetchone())
        
        if report:
            cursor.execute(f'SELECT * FROM custom_report_widgets WHERE report_id = {ph} ORDER BY sort_order ASC', (report_id,))
            report['widgets'] = self._rows_to_dicts(cursor.fetchall())
            
        self.release_connection(conn)
        return report

    def create_custom_report(self, data):
        """Create a new custom report"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        
        try:
            if self.db_type == 'postgresql':
                cursor.execute(f'''
                    INSERT INTO custom_reports (name, description, schedule_type, schedule_time, schedule_day, email_recipients, created_by)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                    RETURNING id
                ''', (data.get('name'), data.get('description'), data.get('schedule_type', 'none'),
                      data.get('schedule_time'), data.get('schedule_day'), data.get('email_recipients'),
                      data.get('created_by')))
                report_id = cursor.fetchone()['id']
            else:
                cursor.execute(f'''
                    INSERT INTO custom_reports (name, description, schedule_type, schedule_time, schedule_day, email_recipients, created_by)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                ''', (data.get('name'), data.get('description'), data.get('schedule_type', 'none'),
                      data.get('schedule_time'), data.get('schedule_day'), data.get('email_recipients'),
                      data.get('created_by')))
                report_id = cursor.lastrowid
                
            # Insert widgets if provided
            widgets = data.get('widgets', [])
            if widgets:
                for idx, w in enumerate(widgets):
                    cursor.execute(f'''
                        INSERT INTO custom_report_widgets (report_id, widget_type, widget_title, config, sort_order)
                        VALUES ({ph}, {ph}, {ph}, {ph}, {ph})
                    ''', (report_id, w.get('widget_type'), w.get('widget_title'), w.get('config', '{}'), idx))
                    
            conn.commit()
            return {'success': True, 'id': report_id}
        except Exception as e:
            conn.rollback()
            return {'success': False, 'error': str(e)}
        finally:
            self.release_connection(conn)

    def update_custom_report(self, report_id, data):
        """Update an existing custom report"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        
        try:
            updates = []
            params = []
            for field in ['name', 'description', 'schedule_type', 'schedule_time', 'schedule_day', 'email_recipients']:
                if field in data:
                    updates.append(f'{field} = {ph}')
                    params.append(data[field])
                    
            if updates:
                params.append(report_id)
                cursor.execute(f"UPDATE custom_reports SET {', '.join(updates)} WHERE id = {ph}", params)
            
            # Update widgets if provided (replace all)
            if 'widgets' in data:
                cursor.execute(f'DELETE FROM custom_report_widgets WHERE report_id = {ph}', (report_id,))
                for idx, w in enumerate(data['widgets']):
                    cursor.execute(f'''
                        INSERT INTO custom_report_widgets (report_id, widget_type, widget_title, config, sort_order)
                        VALUES ({ph}, {ph}, {ph}, {ph}, {ph})
                    ''', (report_id, w.get('widget_type'), w.get('widget_title'), w.get('config', '{}'), idx))
                    
            conn.commit()
            return {'success': True}
        except Exception as e:
            conn.rollback()
            return {'success': False, 'error': str(e)}
        finally:
            self.release_connection(conn)

    def delete_custom_report(self, report_id):
        """Delete a custom report"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        try:
            cursor.execute(f'DELETE FROM custom_report_widgets WHERE report_id = {ph}', (report_id,))
            cursor.execute(f'DELETE FROM custom_reports WHERE id = {ph}', (report_id,))
            conn.commit()
            return {'success': True}
        except Exception as e:
            conn.rollback()
            return {'success': False, 'error': str(e)}
        finally:
            self.release_connection(conn)

    # =========================================================================
    # User-Device Assignment Methods
    # =========================================================================

    def assign_user_to_device(self, user_id, device_id):
        """Assign a user to a device for notifications"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        try:
            if self.db_type == 'postgresql':
                cursor.execute('INSERT INTO user_device_assignments (user_id, device_id) VALUES (%s, %s) ON CONFLICT DO NOTHING', (user_id, device_id))
            else:
                cursor.execute('INSERT OR IGNORE INTO user_device_assignments (user_id, device_id) VALUES (?, ?)', (user_id, device_id))
            conn.commit()
            return {'success': True}
        except Exception as e:
            if conn: conn.rollback()
            return {'success': False, 'error': str(e)}
        finally:
            self.release_connection(conn)

    def unassign_user_from_device(self, user_id, device_id):
        """Remove user assignment from a device"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        try:
            cursor.execute(f'DELETE FROM user_device_assignments WHERE user_id = {self._ph()} AND device_id = {self._ph()}', (user_id, device_id))
            conn.commit()
            return {'success': True}
        except Exception as e:
            if conn: conn.rollback()
            return {'success': False, 'error': str(e)}
        finally:
            self.release_connection(conn)

    def get_device_assignments(self, device_id):
        """Get all users assigned to a device"""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            cursor.execute(f'''
                SELECT u.id, u.username, u.display_name, u.email 
                FROM users u
                JOIN user_device_assignments a ON u.id = a.user_id
                WHERE a.device_id = {self._ph()}
            ''', (device_id,))
            return self._rows_to_dicts(cursor.fetchall())
        finally:
            self.release_connection(conn)

    def get_user_assignments(self, user_id):
        """Get all devices assigned to a user"""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            cursor.execute(f'''
                SELECT d.* 
                FROM devices d
                JOIN user_device_assignments a ON d.id = a.device_id
                WHERE a.user_id = {self._ph()}
            ''', (user_id,))
            return self._rows_to_dicts(cursor.fetchall())
        finally:
            self.release_connection(conn)

    def get_device_recipients(self, device_id):
        """Get emails and telegram IDs for users assigned to a device"""
        conn = self.get_connection()
        try:
            cursor = self._cursor(conn)
            cursor.execute(f'''
                SELECT email, telegram_chat_id FROM users u
                JOIN user_device_assignments a ON u.id = a.user_id
                WHERE a.device_id = {self._ph()} AND u.is_active = {self._ph()}
            ''', (device_id, True if self.db_type == 'postgresql' else 1))
            rows = cursor.fetchall()
            emails = [row['email'] for row in rows if row.get('email')]
            telegram_ids = [row['telegram_chat_id'] for row in rows if row.get('telegram_chat_id')]
            return {'emails': emails, 'telegram_ids': telegram_ids}
        finally:
            self.release_connection(conn)
