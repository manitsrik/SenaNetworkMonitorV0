"""
Database management for Network Monitor
Supports PostgreSQL (primary) and SQLite (fallback)
"""
import sqlite3
from datetime import datetime, timedelta
from config import Config

# PostgreSQL support
try:
    import psycopg2
    import psycopg2.extras
    import psycopg2.errors
    PG_AVAILABLE = True
except ImportError:
    PG_AVAILABLE = False

class Database:
    def __init__(self, db_path=None):
        self.db_type = Config.DB_TYPE
        self.db_path = db_path or Config.DATABASE_PATH
        
        if self.db_type == 'postgresql' and not PG_AVAILABLE:
            print("[WARNING] psycopg2 not installed, falling back to SQLite")
            self.db_type = 'sqlite'
        
        self.init_db()
    
    def get_connection(self):
        """Get database connection"""
        if self.db_type == 'postgresql':
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
    
    def _cursor(self, conn):
        """Get appropriate cursor"""
        if self.db_type == 'postgresql':
            return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        return conn.cursor()
    
    def _row_to_dict(self, row):
        """Convert a row to dict"""
        if row is None:
            return None
        if isinstance(row, dict):
            return row
        return dict(row)
    
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
                UNIQUE(ip_address, monitor_type, device_type)
            )
        ''')
        
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
                role TEXT NOT NULL DEFAULT 'viewer',
                display_name TEXT,
                email TEXT,
                is_active {bool_type} DEFAULT {bool_default_true},
                last_login TIMESTAMP,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default}
            )
        ''')

        # Dashboards table
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS dashboards (
                id {pk},
                name TEXT NOT NULL,
                description TEXT,
                layout_config TEXT,
                created_by INTEGER,
                is_public {bool_type} DEFAULT {bool_default_false},
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
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
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        ''')
        
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
        
        conn.commit()
        conn.close()
    
    def add_device(self, name, ip_address, device_type=None, location=None, 
                   monitor_type='ping', expected_status_code=200,
                   snmp_community='public', snmp_port=161, snmp_version='2c',
                   tcp_port=80, dns_query_domain='google.com', location_type='on-premise'):
        """Add a new device"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        
        # Strip whitespace from IP address to prevent ping failures
        ip_address = ip_address.strip() if ip_address else ip_address
        name = name.strip() if name else name
        
        try:
            if self.db_type == 'postgresql':
                cursor.execute('''
                    INSERT INTO devices (name, ip_address, device_type, location, 
                                       monitor_type, expected_status_code,
                                       snmp_community, snmp_port, snmp_version, tcp_port,
                                       dns_query_domain, location_type)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                ''', (name, ip_address, device_type or Config.DEFAULT_DEVICE_TYPE, 
                      location or Config.DEFAULT_LOCATION, monitor_type, expected_status_code,
                      snmp_community, snmp_port, snmp_version, tcp_port, dns_query_domain,
                      location_type or Config.DEFAULT_LOCATION_TYPE))
                device_id = cursor.fetchone()['id']
            else:
                cursor.execute('''
                    INSERT INTO devices (name, ip_address, device_type, location, 
                                       monitor_type, expected_status_code,
                                       snmp_community, snmp_port, snmp_version, tcp_port,
                                       dns_query_domain, location_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (name, ip_address, device_type or Config.DEFAULT_DEVICE_TYPE, 
                      location or Config.DEFAULT_LOCATION, monitor_type, expected_status_code,
                      snmp_community, snmp_port, snmp_version, tcp_port, dns_query_domain,
                      location_type or Config.DEFAULT_LOCATION_TYPE))
                device_id = cursor.lastrowid
            conn.commit()
            conn.close()
            return {'success': True, 'id': device_id}
        except (sqlite3.IntegrityError, Exception) as e:
            if 'unique' in str(e).lower() or 'duplicate' in str(e).lower() or 'UNIQUE constraint' in str(e):
                conn.rollback()
                conn.close()
                return {'success': False, 'error': 'Device with this IP/URL, monitor type, and device type already exists'}
            conn.rollback()
            conn.close()
            return {'success': False, 'error': str(e)}
    
    def get_all_devices(self):
        """Get all devices"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute('SELECT * FROM devices ORDER BY id')
        devices = self._rows_to_dicts(cursor.fetchall())
        conn.close()
        return devices
    
    def get_device(self, device_id):
        """Get a specific device"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute(f'SELECT * FROM devices WHERE id = {self._ph()}', (device_id,))
        device = cursor.fetchone()
        conn.close()
        return self._row_to_dict(device)
    
    def update_device(self, device_id, name=None, ip_address=None, 
                     device_type=None, location=None, monitor_type=None,
                     snmp_community=None, snmp_port=None, snmp_version=None,
                     tcp_port=None, dns_query_domain=None, location_type=None):
        """Update device information"""
        # Strip whitespace from IP address and name to prevent issues
        if ip_address:
            ip_address = ip_address.strip()
        if name:
            name = name.strip()
        
        conn = self.get_connection()
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
        if location:
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
        if tcp_port is not None:
            updates.append(f'tcp_port = {ph}')
            params.append(tcp_port)
        if dns_query_domain:
            updates.append(f'dns_query_domain = {ph}')
            params.append(dns_query_domain)
        if location_type:
            updates.append(f'location_type = {ph}')
            params.append(location_type)
        
        if updates:
            params.append(device_id)
            query = f"UPDATE devices SET {', '.join(updates)} WHERE id = {ph}"
            cursor.execute(query, params)
            conn.commit()
        
        conn.close()
        return {'success': True}
    
    def delete_device(self, device_id):
        """Delete a device"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        cursor.execute(f'DELETE FROM devices WHERE id = {ph}', (device_id,))
        cursor.execute(f'DELETE FROM topology WHERE device_id = {ph} OR connected_to = {ph}', 
                      (device_id, device_id))
        cursor.execute(f'DELETE FROM status_history WHERE device_id = {ph}', (device_id,))
        # Clean up sub-topology references
        cursor.execute(f'DELETE FROM sub_topology_devices WHERE device_id = {ph}', (device_id,))
        cursor.execute(f'DELETE FROM sub_topology_connections WHERE device_id = {ph} OR connected_to = {ph}',
                      (device_id, device_id))
        conn.commit()
        conn.close()
        return {'success': True}
    
    def update_device_status(self, device_id, status, response_time=None, http_status_code=None,
                             snmp_uptime=None, snmp_sysname=None, snmp_sysdescr=None,
                             snmp_syslocation=None, snmp_syscontact=None,
                             ssl_expiry_date=None, ssl_days_left=None, ssl_issuer=None, ssl_status=None):
        """Update device status"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        
        now = datetime.now().isoformat()
        
        # Build update query dynamically based on provided values
        update_parts = [f'status = {ph}', f'response_time = {ph}', f'last_check = {ph}', f'http_status_code = {ph}']
        params = [status, response_time, now, http_status_code]
        
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
        conn.close()
    
    def get_topology(self):
        """Get topology connections"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute('SELECT * FROM topology')
        topology = self._rows_to_dicts(cursor.fetchall())
        conn.close()
        return topology
    
    def add_topology_connection(self, device_id, connected_to, view_type='standard'):
        """Add a topology connection"""
        conn = self.get_connection()
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
            conn.close()
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
                VALUES ({self._ph(3)})
            ''', (device_id, connected_to, view_type))
            connection_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return {'success': True, 'id': connection_id}
    
    def delete_topology_connection(self, connection_id=None, device_id=None, connected_to=None):
        """Delete a topology connection by ID or by device pair"""
        conn = self.get_connection()
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
            conn.close()
            return {'success': False, 'error': 'Must provide connection_id or both device_id and connected_to'}
        
        conn.commit()
        conn.close()
        return {'success': True}
    
    def get_device_history(self, device_id, limit=100):
        """Get status history for a device"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        cursor.execute(f'''
            SELECT * FROM status_history 
            WHERE device_id = {ph} 
            ORDER BY checked_at DESC 
            LIMIT {ph}
        ''', (device_id, limit))
        history = self._rows_to_dicts(cursor.fetchall())
        conn.close()
        return history
    
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
        conn.close()
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
        conn.close()
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
        conn.close()
        return stats
    
    def get_device_type_trends(self, minutes=180):
        """Get average response time trends by device type"""
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

        query = f'''
            SELECT 
                d.device_type,
                {time_select} as timestamp,
                AVG(h.response_time) as avg_response_time
            FROM status_history h
            JOIN devices d ON h.device_id = d.id
            WHERE h.checked_at >= {ph} AND h.response_time IS NOT NULL AND h.status IN ('up', 'slow')
            GROUP BY d.device_type, {time_group}
            ORDER BY timestamp ASC
        '''
        
        cursor.execute(query, (start_time,))
        results = self._rows_to_dicts(cursor.fetchall())
        conn.close()
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
        conn.close()
        return {'success': True}
    
    def get_alert_setting(self, key):
        """Get a single alert setting"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute(f'SELECT setting_value FROM alert_settings WHERE setting_key = {self._ph()}', (key,))
        result = cursor.fetchone()
        conn.close()
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
        conn.close()
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
        conn.close()
    
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
        conn.close()
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
        conn.close()
        return history
    
    def get_failure_count(self, device_id):
        """Get current failure count for a device"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute(f'SELECT failure_count FROM devices WHERE id = {self._ph()}', (device_id,))
        result = cursor.fetchone()
        conn.close()
        if result is None:
            return 0
        r = self._row_to_dict(result)
        return r['failure_count'] if r and r['failure_count'] else 0
    
    def increment_failure_count(self, device_id):
        """Increment failure count for a device and return new count"""
        conn = self.get_connection()
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
        conn.close()
        r = self._row_to_dict(result)
        return r['failure_count'] if r else 1
    
    def reset_failure_count(self, device_id):
        """Reset failure count to 0 when device is up"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute(f'UPDATE devices SET failure_count = 0 WHERE id = {self._ph()}', (device_id,))
        conn.commit()
        conn.close()
    
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
            conn.close()
            return {'success': True, 'id': window_id}
        except Exception as e:
            conn.rollback()
            conn.close()
            return {'success': False, 'error': str(e)}
    
    def get_all_maintenance_windows(self):
        """Get all maintenance windows with device info"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute('''
            SELECT mw.*, d.name as device_name, d.ip_address
            FROM maintenance_windows mw
            LEFT JOIN devices d ON mw.device_id = d.id
            ORDER BY mw.start_time DESC
        ''')
        windows = self._rows_to_dicts(cursor.fetchall())
        conn.close()
        return windows
    
    def get_active_maintenance(self, device_id=None):
        """Get currently active maintenance windows for a device or all devices"""
        conn = self.get_connection()
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
        conn.close()
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
        conn.close()
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
        conn.close()
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
        conn.close()
        
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
        """Get SLA data for all devices"""
        devices = self.get_all_devices()
        result = []
        
        for device in devices:
            stats = self.get_device_uptime_stats(device['id'], days)
            
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

    # =========================================================================
    # User Management Methods
    # =========================================================================
    
    def get_user_by_username(self, username):
        """Get a user by username"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute(f'SELECT * FROM users WHERE username = {self._ph()}', (username,))
        row = cursor.fetchone()
        conn.close()
        return self._row_to_dict(row)
    
    def get_user_by_id(self, user_id):
        """Get a user by ID"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute(f'SELECT * FROM users WHERE id = {self._ph()}', (user_id,))
        row = cursor.fetchone()
        conn.close()
        return self._row_to_dict(row)
    
    def authenticate_user(self, username, password):
        """Authenticate a user and return user data if successful"""
        from werkzeug.security import check_password_hash
        
        user = self.get_user_by_username(username)
        if not user:
            return None
        
        if not user.get('is_active', True):
            return None
        
        if check_password_hash(user['password_hash'], password):
            self.update_last_login(user['id'])
            return user
        
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
        conn.close()
    
    def get_all_users(self):
        """Get all users (excluding password hashes)"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute('''
            SELECT id, username, role, display_name, email, is_active, 
                   last_login, created_at, updated_at 
            FROM users ORDER BY created_at DESC
        ''')
        users = self._rows_to_dicts(cursor.fetchall())
        conn.close()
        return users
    
    def add_user(self, username, password, role='viewer', display_name=None, email=None):
        """Add a new user"""
        from werkzeug.security import generate_password_hash
        
        if role not in ['admin', 'operator', 'viewer']:
            return {'success': False, 'error': 'Invalid role. Must be admin, operator, or viewer'}
        
        conn = self.get_connection()
        cursor = self._cursor(conn)
        
        try:
            if self.db_type == 'postgresql':
                cursor.execute('''
                    INSERT INTO users (username, password_hash, role, display_name, email, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                ''', (username, generate_password_hash(password), role, display_name, email, 
                      datetime.now().isoformat()))
                user_id = cursor.fetchone()['id']
            else:
                cursor.execute('''
                    INSERT INTO users (username, password_hash, role, display_name, email, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (username, generate_password_hash(password), role, display_name, email, 
                      datetime.now().isoformat()))
                user_id = cursor.lastrowid
            conn.commit()
            conn.close()
            return {'success': True, 'id': user_id}
        except Exception as e:
            conn.rollback()
            conn.close()
            if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
                return {'success': False, 'error': 'Username already exists'}
            return {'success': False, 'error': str(e)}
    
    def update_user(self, user_id, role=None, display_name=None, email=None, 
                    is_active=None, password=None):
        """Update user details"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        
        updates = []
        params = []
        
        if role is not None:
            if role not in ['admin', 'operator', 'viewer']:
                conn.close()
                return {'success': False, 'error': 'Invalid role'}
            updates.append(f'role = {ph}')
            params.append(role)
        
        if display_name is not None:
            updates.append(f'display_name = {ph}')
            params.append(display_name)
        
        if email is not None:
            updates.append(f'email = {ph}')
            params.append(email)
        
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
            conn.close()
            return {'success': False, 'error': 'No updates provided'}
        
        updates.append(f'updated_at = {ph}')
        params.append(datetime.now().isoformat())
        params.append(user_id)
        
        try:
            cursor.execute(f'''
                UPDATE users SET {', '.join(updates)} WHERE id = {ph}
            ''', params)
            conn.commit()
            conn.close()
            return {'success': True}
        except Exception as e:
            conn.rollback()
            conn.close()
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
                    conn.close()
                    return {'success': False, 'error': 'Cannot delete the last admin user'}
        
        cursor.execute(f'DELETE FROM users WHERE id = {ph}', (user_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
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
                INSERT INTO dashboards (name, layout_config, description, created_by, is_public)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            ''', (name, layout_config, description, created_by, is_public_val))
            dashboard_id = cursor.fetchone()['id']
        else:
            cursor.execute('''
                INSERT INTO dashboards (name, layout_config, description, created_by, is_public)
                VALUES (?, ?, ?, ?, ?)
            ''', (name, layout_config, description, created_by, is_public))
            dashboard_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
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
                    ORDER BY d.created_at DESC
                ''', (user_id,))
            else:
                cursor.execute(f'''
                    SELECT d.*, u.username as creator_name 
                    FROM dashboards d
                    LEFT JOIN users u ON d.created_by = u.id
                    WHERE d.is_public = 1 OR d.created_by = {ph}
                    ORDER BY d.created_at DESC
                ''', (user_id,))
        else:
            cursor.execute('''
                SELECT d.*, u.username as creator_name 
                FROM dashboards d
                LEFT JOIN users u ON d.created_by = u.id
                ORDER BY d.created_at DESC
            ''')
            
        dashboards = self._rows_to_dicts(cursor.fetchall())
        conn.close()
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
        conn.close()
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
            
        conn.close()
        return {'success': True}
    
    def delete_dashboard(self, dashboard_id):
        """Delete a dashboard"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute(f'DELETE FROM dashboards WHERE id = {self._ph()}', (dashboard_id,))
        conn.commit()
        conn.close()
        return {'success': True}

    # =========================================================================
    # Sub-Topology Methods
    # =========================================================================

    def create_sub_topology(self, name, description=None, created_by=None, background_image=None, background_zoom=100, node_positions=None, background_opacity=100):
        """Create a new sub-topology"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        
        if self.db_type == 'postgresql':
            cursor.execute('''
                INSERT INTO sub_topologies (name, description, created_by, background_image, background_zoom, node_positions, background_opacity)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (name, description, created_by, background_image, background_zoom, node_positions, background_opacity))
            sub_topo_id = cursor.fetchone()['id']
        else:
            cursor.execute('''
                INSERT INTO sub_topologies (name, description, created_by, background_image, background_zoom, node_positions, background_opacity)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (name, description, created_by, background_image, background_zoom, node_positions, background_opacity))
            sub_topo_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return {'success': True, 'id': sub_topo_id}

    def get_all_sub_topologies(self):
        """Get all sub-topologies"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        cursor.execute('SELECT * FROM sub_topologies ORDER BY name')
        result = self._rows_to_dicts(cursor.fetchall())
        conn.close()
        return result

    def get_sub_topology(self, sub_topo_id):
        """Get a sub-topology with its devices and connections"""
        conn = self.get_connection()
        cursor = self._cursor(conn)
        ph = self._ph()
        
        cursor.execute(f'SELECT * FROM sub_topologies WHERE id = {ph}', (sub_topo_id,))
        sub_topo = cursor.fetchone()
        if not sub_topo:
            conn.close()
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
        
        conn.close()
        return result

    def update_sub_topology(self, sub_topo_id, name=None, description=None, device_ids=None, connections=None, background_image=None, background_zoom=None, node_positions=None, background_opacity=None):
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
        conn.close()
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
        conn.close()
        return {'success': True}
