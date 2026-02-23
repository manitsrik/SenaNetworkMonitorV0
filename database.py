"""
Database management for Network Monitor
"""
import sqlite3
from datetime import datetime, timedelta
from config import Config

class Database:
    def __init__(self, db_path=None):
        self.db_path = db_path or Config.DATABASE_PATH
        self.init_db()
    
    def get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        return conn
    
    def init_db(self):
        """Initialize database tables"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Devices table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                ip_address TEXT NOT NULL,
                device_type TEXT,
                location TEXT,
                status TEXT DEFAULT 'unknown',
                last_check TIMESTAMP,
                response_time REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                monitor_type TEXT DEFAULT 'ping',
                http_status_code INTEGER,
                expected_status_code INTEGER DEFAULT 200,
                UNIQUE(ip_address, monitor_type, device_type)
            )
        ''')
        
        # Migrate existing database - add new columns if they don't exist
        self._migrate_database(cursor)
        
        # Topology table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS topology (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER,
                connected_to INTEGER,
                FOREIGN KEY (device_id) REFERENCES devices(id),
                FOREIGN KEY (connected_to) REFERENCES devices(id)
            )
        ''')
        
        # Status history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS status_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER,
                status TEXT,
                response_time REAL,
                checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (device_id) REFERENCES devices(id)
            )
        ''')
        
        # Alert settings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alert_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                setting_key TEXT UNIQUE NOT NULL,
                setting_value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Alert history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alert_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER,
                event_type TEXT,
                message TEXT,
                channel TEXT,
                status TEXT,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (device_id) REFERENCES devices(id)
            )
        ''')
        
        # Maintenance windows table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS maintenance_windows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                device_id INTEGER,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                recurring TEXT,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (device_id) REFERENCES devices(id)
            )
        ''')
        
        # Users table for multi-user RBAC
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'viewer',
                display_name TEXT,
                email TEXT,
                is_active INTEGER DEFAULT 1,
                last_login TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Dashboards table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dashboards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                layout_config TEXT,
                created_by INTEGER,
                is_public INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users (id)
            )
        ''')
        
        # Sub-topologies table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sub_topologies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        ''')
        
        # Devices belonging to a sub-topology
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sub_topology_devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sub_topology_id INTEGER NOT NULL,
                device_id INTEGER NOT NULL,
                FOREIGN KEY (sub_topology_id) REFERENCES sub_topologies(id) ON DELETE CASCADE,
                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
                UNIQUE(sub_topology_id, device_id)
            )
        ''')
        
        # Custom connections within a sub-topology
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sub_topology_connections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        
        # Default admin user (password: admin)
        cursor.execute('SELECT id FROM users WHERE username = ?', ('admin',))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO users (username, password_hash, role, display_name)
                VALUES (?, ?, ?, ?)
            ''', ('admin', generate_password_hash('admin'), 'admin', 'Administrator'))
        
        # Default operator user (password: operator)
        cursor.execute('SELECT id FROM users WHERE username = ?', ('operator',))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO users (username, password_hash, role, display_name)
                VALUES (?, ?, ?, ?)
            ''', ('operator', generate_password_hash('operator'), 'operator', 'Operator User'))
        
        # Default viewer user (password: viewer)
        cursor.execute('SELECT id FROM users WHERE username = ?', ('viewer',))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO users (username, password_hash, role, display_name)
                VALUES (?, ?, ?, ?)
            ''', ('viewer', generate_password_hash('viewer'), 'viewer', 'Viewer User'))
        
        conn.commit()
        conn.close()
    
    def _migrate_database(self, cursor):
        """Migrate database to add new columns for website and SNMP monitoring"""
        # Check if monitor_type column exists
        cursor.execute("PRAGMA table_info(devices)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'monitor_type' not in columns:
            cursor.execute("ALTER TABLE devices ADD COLUMN monitor_type TEXT DEFAULT 'ping'")
            print("[OK] Added monitor_type column to devices table")
        
        if 'http_status_code' not in columns:
            cursor.execute("ALTER TABLE devices ADD COLUMN http_status_code INTEGER")
            print("[OK] Added http_status_code column to devices table")
        
        if 'expected_status_code' not in columns:
            cursor.execute("ALTER TABLE devices ADD COLUMN expected_status_code INTEGER DEFAULT 200")
            print("[OK] Added expected_status_code column to devices table")
        
        # SNMP columns
        if 'snmp_community' not in columns:
            cursor.execute("ALTER TABLE devices ADD COLUMN snmp_community TEXT DEFAULT 'public'")
            print("[OK] Added snmp_community column to devices table")
        
        if 'snmp_port' not in columns:
            cursor.execute("ALTER TABLE devices ADD COLUMN snmp_port INTEGER DEFAULT 161")
            print("[OK] Added snmp_port column to devices table")
        
        if 'snmp_version' not in columns:
            cursor.execute("ALTER TABLE devices ADD COLUMN snmp_version TEXT DEFAULT '2c'")
            print("[OK] Added snmp_version column to devices table")
        
        if 'snmp_uptime' not in columns:
            cursor.execute("ALTER TABLE devices ADD COLUMN snmp_uptime TEXT")
            print("[OK] Added snmp_uptime column to devices table")
        
        if 'snmp_sysname' not in columns:
            cursor.execute("ALTER TABLE devices ADD COLUMN snmp_sysname TEXT")
            print("[OK] Added snmp_sysname column to devices table")
        
        # SNMP Phase 1: Extended system info
        if 'snmp_sysdescr' not in columns:
            cursor.execute("ALTER TABLE devices ADD COLUMN snmp_sysdescr TEXT")
            print("[OK] Added snmp_sysdescr column to devices table")
        
        if 'snmp_syslocation' not in columns:
            cursor.execute("ALTER TABLE devices ADD COLUMN snmp_syslocation TEXT")
            print("[OK] Added snmp_syslocation column to devices table")
        
        if 'snmp_syscontact' not in columns:
            cursor.execute("ALTER TABLE devices ADD COLUMN snmp_syscontact TEXT")
            print("[OK] Added snmp_syscontact column to devices table")
        
        # TCP Port Check column
        if 'tcp_port' not in columns:
            cursor.execute("ALTER TABLE devices ADD COLUMN tcp_port INTEGER DEFAULT 80")
            print("[OK] Added tcp_port column to devices table")
        
        # DNS Query domain column
        if 'dns_query_domain' not in columns:
            cursor.execute("ALTER TABLE devices ADD COLUMN dns_query_domain TEXT DEFAULT 'google.com'")
            print("[OK] Added dns_query_domain column to devices table")
        
        # SSL Certificate columns
        if 'ssl_expiry_date' not in columns:
            cursor.execute("ALTER TABLE devices ADD COLUMN ssl_expiry_date TEXT")
            print("[OK] Added ssl_expiry_date column to devices table")
        
        if 'ssl_days_left' not in columns:
            cursor.execute("ALTER TABLE devices ADD COLUMN ssl_days_left INTEGER")
            print("[OK] Added ssl_days_left column to devices table")
        
        if 'ssl_issuer' not in columns:
            cursor.execute("ALTER TABLE devices ADD COLUMN ssl_issuer TEXT")
            print("[OK] Added ssl_issuer column to devices table")
        
        if 'ssl_status' not in columns:
            cursor.execute("ALTER TABLE devices ADD COLUMN ssl_status TEXT")
            print("[OK] Added ssl_status column to devices table")
        
        # Location Type column
        if 'location_type' not in columns:
            cursor.execute("ALTER TABLE devices ADD COLUMN location_type TEXT DEFAULT 'on-premise'")
            print("[OK] Added location_type column to devices table")
        
        # Failure count for consecutive failure threshold
        if 'failure_count' not in columns:
            cursor.execute("ALTER TABLE devices ADD COLUMN failure_count INTEGER DEFAULT 0")
            print("[OK] Added failure_count column to devices table")
            
        # Check if view_type column exists in topology table
        cursor.execute("PRAGMA table_info(topology)")
        topology_columns = [column[1] for column in cursor.fetchall()]
        
        if 'view_type' not in topology_columns:
            cursor.execute("ALTER TABLE topology ADD COLUMN view_type TEXT DEFAULT 'standard'")
            print("[OK] Added view_type column to topology table")
        
        # Migrate unique constraint from ip_address to (ip_address, monitor_type)
        self._migrate_unique_constraint(cursor)
        
        # Add background_image column to sub_topologies table
        cursor.execute("PRAGMA table_info(sub_topologies)")
        sub_topo_columns = [column[1] for column in cursor.fetchall()]
        if 'background_image' not in sub_topo_columns:
            cursor.execute("ALTER TABLE sub_topologies ADD COLUMN background_image TEXT")
            print("[OK] Added background_image column to sub_topologies table")
        if 'background_zoom' not in sub_topo_columns:
            cursor.execute("ALTER TABLE sub_topologies ADD COLUMN background_zoom INTEGER DEFAULT 100")
            print("[OK] Added background_zoom column to sub_topologies table")
        if 'node_positions' not in sub_topo_columns:
            cursor.execute("ALTER TABLE sub_topologies ADD COLUMN node_positions TEXT")
            print("[OK] Added node_positions column to sub_topologies table")
        if 'background_opacity' not in sub_topo_columns:
            cursor.execute("ALTER TABLE sub_topologies ADD COLUMN background_opacity INTEGER DEFAULT 100")
            print("[OK] Added background_opacity column to sub_topologies table")
    
    def _migrate_unique_constraint(self, cursor):
        """Migrate the unique constraint from ip_address to (ip_address, monitor_type)"""
        # Check current unique constraint by trying to get index info
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='devices'")
        result = cursor.fetchone()
        if result:
            create_sql = result[0]
            # If old schema has UNIQUE on ip_address alone or just (ip_address, monitor_type), we need to migrate
            if ('ip_address TEXT NOT NULL UNIQUE' in create_sql or 
                ('UNIQUE(ip_address, monitor_type)' in create_sql and 'UNIQUE(ip_address, monitor_type, device_type)' not in create_sql)):
                print("[INFO] Migrating unique constraint to (ip_address, monitor_type, device_type)...")
                
                # Get current columns
                cursor.execute("PRAGMA table_info(devices)")
                all_columns = [column[1] for column in cursor.fetchall()]
                columns_str = ', '.join(all_columns)
                
                # Create new table with updated schema
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS devices_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        ip_address TEXT NOT NULL,
                        device_type TEXT,
                        location TEXT,
                        status TEXT DEFAULT 'unknown',
                        last_check TIMESTAMP,
                        response_time REAL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
                        UNIQUE(ip_address, monitor_type, device_type)
                    )
                ''')
                
                # Copy data from old table
                cursor.execute(f'INSERT INTO devices_new ({columns_str}) SELECT {columns_str} FROM devices')
                
                # Drop old table and rename new table
                cursor.execute('DROP TABLE devices')
                cursor.execute('ALTER TABLE devices_new RENAME TO devices')
                
                print("[OK] Migrated unique constraint to (ip_address, monitor_type, device_type)")
    
    def add_device(self, name, ip_address, device_type=None, location=None, 
                   monitor_type='ping', expected_status_code=200,
                   snmp_community='public', snmp_port=161, snmp_version='2c',
                   tcp_port=80, dns_query_domain='google.com', location_type='on-premise'):
        """Add a new device"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Strip whitespace from IP address to prevent ping failures
        ip_address = ip_address.strip() if ip_address else ip_address
        name = name.strip() if name else name
        
        try:
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
            conn.commit()
            device_id = cursor.lastrowid
            conn.close()
            return {'success': True, 'id': device_id}
        except sqlite3.IntegrityError:
            conn.close()
            return {'success': False, 'error': 'Device with this IP/URL, monitor type, and device type already exists'}
    
    def get_all_devices(self):
        """Get all devices"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM devices ORDER BY id')
        devices = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return devices
    
    def get_device(self, device_id):
        """Get a specific device"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM devices WHERE id = ?', (device_id,))
        device = cursor.fetchone()
        conn.close()
        return dict(device) if device else None
    
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
        cursor = conn.cursor()
        
        updates = []
        params = []
        
        if name:
            updates.append('name = ?')
            params.append(name)
        if ip_address:
            updates.append('ip_address = ?')
            params.append(ip_address)
        if device_type:
            updates.append('device_type = ?')
            params.append(device_type)
        if location:
            updates.append('location = ?')
            params.append(location)
        if monitor_type:
            updates.append('monitor_type = ?')
            params.append(monitor_type)
        if snmp_community:
            updates.append('snmp_community = ?')
            params.append(snmp_community)
        if snmp_port is not None:
            updates.append('snmp_port = ?')
            params.append(snmp_port)
        if snmp_version:
            updates.append('snmp_version = ?')
            params.append(snmp_version)
        if tcp_port is not None:
            updates.append('tcp_port = ?')
            params.append(tcp_port)
        if dns_query_domain:
            updates.append('dns_query_domain = ?')
            params.append(dns_query_domain)
        if location_type:
            updates.append('location_type = ?')
            params.append(location_type)
        
        if updates:
            params.append(device_id)
            query = f"UPDATE devices SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, params)
            conn.commit()
        
        conn.close()
        return {'success': True}
    
    def delete_device(self, device_id):
        """Delete a device"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM devices WHERE id = ?', (device_id,))
        cursor.execute('DELETE FROM topology WHERE device_id = ? OR connected_to = ?', 
                      (device_id, device_id))
        cursor.execute('DELETE FROM status_history WHERE device_id = ?', (device_id,))
        # Clean up sub-topology references
        cursor.execute('DELETE FROM sub_topology_devices WHERE device_id = ?', (device_id,))
        cursor.execute('DELETE FROM sub_topology_connections WHERE device_id = ? OR connected_to = ?',
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
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        # Build update query dynamically based on provided values
        update_parts = ['status = ?', 'response_time = ?', 'last_check = ?', 'http_status_code = ?']
        params = [status, response_time, now, http_status_code]
        
        if snmp_uptime is not None:
            update_parts.append('snmp_uptime = ?')
            params.append(snmp_uptime)
        
        if snmp_sysname is not None:
            update_parts.append('snmp_sysname = ?')
            params.append(snmp_sysname)
        
        if snmp_sysdescr is not None:
            update_parts.append('snmp_sysdescr = ?')
            params.append(snmp_sysdescr)
        
        if snmp_syslocation is not None:
            update_parts.append('snmp_syslocation = ?')
            params.append(snmp_syslocation)
        
        if snmp_syscontact is not None:
            update_parts.append('snmp_syscontact = ?')
            params.append(snmp_syscontact)
        
        # SSL Certificate fields
        if ssl_expiry_date is not None:
            update_parts.append('ssl_expiry_date = ?')
            params.append(ssl_expiry_date)
        
        if ssl_days_left is not None:
            update_parts.append('ssl_days_left = ?')
            params.append(ssl_days_left)
        
        if ssl_issuer is not None:
            update_parts.append('ssl_issuer = ?')
            params.append(ssl_issuer)
        
        if ssl_status is not None:
            update_parts.append('ssl_status = ?')
            params.append(ssl_status)
        
        params.append(device_id)
        
        cursor.execute(f'''
            UPDATE devices 
            SET {', '.join(update_parts)}
            WHERE id = ?
        ''', params)
        
        # Log to history
        cursor.execute('''
            INSERT INTO status_history (device_id, status, response_time, checked_at)
            VALUES (?, ?, ?, ?)
        ''', (device_id, status, response_time, now))
        
        conn.commit()
        conn.close()
    
    def get_topology(self):
        """Get topology connections"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM topology')
        topology = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return topology
    


    def add_topology_connection(self, device_id, connected_to, view_type='standard'):
        """Add a topology connection"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Check if connection already exists in this view
        cursor.execute('''
            SELECT id FROM topology 
            WHERE ((device_id = ? AND connected_to = ?) 
               OR (device_id = ? AND connected_to = ?))
               AND (view_type = ? OR view_type IS NULL)
        ''', (device_id, connected_to, connected_to, device_id, view_type))
        
        if cursor.fetchone():
            conn.close()
            return {'success': False, 'error': 'Connection already exists in this view'}
        
        cursor.execute('''
            INSERT INTO topology (device_id, connected_to, view_type)
            VALUES (?, ?, ?)
        ''', (device_id, connected_to, view_type))
        conn.commit()
        connection_id = cursor.lastrowid
        conn.close()
        return {'success': True, 'id': connection_id}
    
    def delete_topology_connection(self, connection_id=None, device_id=None, connected_to=None):
        """Delete a topology connection by ID or by device pair"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if connection_id:
            cursor.execute('DELETE FROM topology WHERE id = ?', (connection_id,))
        elif device_id and connected_to:
            cursor.execute('''
                DELETE FROM topology 
                WHERE (device_id = ? AND connected_to = ?) 
                   OR (device_id = ? AND connected_to = ?)
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
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM status_history 
            WHERE device_id = ? 
            ORDER BY checked_at DESC 
            LIMIT ?
        ''', (device_id, limit))
        history = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return history
    
    def get_historical_data(self, start_date=None, end_date=None, device_id=None, device_type=None):
        """Get historical data with optional filters"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        query = '''
            SELECT h.*, d.name, d.ip_address, d.device_type, d.location
            FROM status_history h
            JOIN devices d ON h.device_id = d.id
            WHERE 1=1
        '''
        params = []
        
        if start_date:
            query += ' AND h.checked_at >= ?'
            params.append(start_date)
        
        if end_date:
            query += ' AND h.checked_at <= ?'
            params.append(end_date)
        
        if device_id:
            query += ' AND h.device_id = ?'
            params.append(device_id)
        
        if device_type:
            query += ' AND d.device_type = ?'
            params.append(device_type)
        
        query += ' ORDER BY h.checked_at ASC'
        
        cursor.execute(query, params)
        history = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return history
    
    def get_historical_data_multi(self, start_date=None, end_date=None, device_ids=None):
        """Get historical data for multiple devices"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        query = '''
            SELECT h.*, d.name, d.ip_address, d.device_type, d.location
            FROM status_history h
            JOIN devices d ON h.device_id = d.id
            WHERE 1=1
        '''
        params = []
        
        if start_date:
            query += ' AND h.checked_at >= ?'
            params.append(start_date)
        
        if end_date:
            query += ' AND h.checked_at <= ?'
            params.append(end_date)
        
        if device_ids and len(device_ids) > 0:
            placeholders = ','.join(['?' for _ in device_ids])
            query += f' AND h.device_id IN ({placeholders})'
            params.extend(device_ids)
        
        query += ' ORDER BY h.checked_at ASC'
        
        cursor.execute(query, params)
        history = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return history
    
    def get_aggregated_stats(self, start_date=None, end_date=None):
        """Get aggregated statistics for a time period"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
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
            query += ' AND h.checked_at >= ?'
            params.append(start_date)
        
        if end_date:
            query += ' AND h.checked_at <= ?'
            params.append(end_date)
        
        query += ' GROUP BY d.device_type'
        
        cursor.execute(query, params)
        stats = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return stats
    
    
    def get_device_type_trends(self, minutes=180):
        """Get average response time trends by device type"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Calculate start time
        start_time = (datetime.now() - timedelta(minutes=minutes)).isoformat()
        
        # Determine grouping interval based on requested duration
        if minutes <= 10:
            # Group by 30-second intervals for short durations (Ping interval is ~30s)
            # We use sqlite's strftime with seconds, but we need to bin them
            # Simplest way: Group by HH:MM and (SS/30) ? 
            # Or just return raw checked_at and average in python? 
            # Let's try to group by 30s in SQL:
            # unixepoch / 30 
            time_group = "CAST(strftime('%s', h.checked_at) / 30 AS INTEGER)"
            # For display, we can just take the min(checked_at) of the group
            time_select = "datetime(MIN(h.checked_at))" 
        else:
            # Group by minute
            time_group = "strftime('%Y-%m-%d %H:%M', h.checked_at)"
            time_select = "strftime('%Y-%m-%d %H:%M', h.checked_at)"

        query = f'''
            SELECT 
                d.device_type,
                {time_select} as timestamp,
                AVG(h.response_time) as avg_response_time
            FROM status_history h
            JOIN devices d ON h.device_id = d.id
            WHERE h.checked_at >= ? AND h.response_time IS NOT NULL AND h.status IN ('up', 'slow')
            GROUP BY d.device_type, {time_group}
            ORDER BY timestamp ASC
        '''
        
        cursor.execute(query, (start_time,))
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results

    # =========================================================================
    # Alert Settings Methods
    # =========================================================================
    
    def save_alert_setting(self, key, value):
        """Save or update an alert setting"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
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
        cursor = conn.cursor()
        cursor.execute('SELECT setting_value FROM alert_settings WHERE setting_key = ?', (key,))
        result = cursor.fetchone()
        conn.close()
        return result['setting_value'] if result else None
    
    def get_all_alert_settings(self):
        """Get all alert settings"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT setting_key, setting_value FROM alert_settings')
        settings = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return settings
    
    def log_alert(self, device_id, event_type, message, channel, status, error=None):
        """Log an alert to history"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO alert_history (device_id, event_type, message, channel, status, error_message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (device_id, event_type, message, channel, status, error, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
    
    def get_last_alert_time(self, device_id, event_type):
        """Get the last alert time for a device and event type (for cooldown)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT created_at FROM alert_history 
            WHERE device_id = ? AND event_type = ? AND status = 'sent'
            ORDER BY created_at DESC LIMIT 1
        ''', (device_id, event_type))
        result = cursor.fetchone()
        conn.close()
        return result['created_at'] if result else None
    
    def get_alert_history(self, limit=100):
        """Get alert history with device info"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT ah.*, d.name as device_name, d.ip_address
            FROM alert_history ah
            LEFT JOIN devices d ON ah.device_id = d.id
            ORDER BY ah.created_at DESC
            LIMIT ?
        ''', (limit,))
        history = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return history
    
    def get_failure_count(self, device_id):
        """Get current failure count for a device"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT failure_count FROM devices WHERE id = ?', (device_id,))
        result = cursor.fetchone()
        conn.close()
        return result['failure_count'] if result and result['failure_count'] else 0
    
    def increment_failure_count(self, device_id):
        """Increment failure count for a device and return new count"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE devices 
            SET failure_count = COALESCE(failure_count, 0) + 1
            WHERE id = ?
        ''', (device_id,))
        cursor.execute('SELECT failure_count FROM devices WHERE id = ?', (device_id,))
        result = cursor.fetchone()
        conn.commit()
        conn.close()
        return result['failure_count'] if result else 1
    
    def reset_failure_count(self, device_id):
        """Reset failure count to 0 when device is up"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE devices SET failure_count = 0 WHERE id = ?', (device_id,))
        conn.commit()
        conn.close()
    
    # =========================================================================
    # Maintenance Windows Methods
    # =========================================================================
    
    def add_maintenance_window(self, name, start_time, end_time, device_id=None, 
                                recurring=None, description=None):
        """Add a new maintenance window"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO maintenance_windows (name, device_id, start_time, end_time, 
                                                  recurring, description, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (name, device_id, start_time, end_time, recurring, description, 
                  datetime.now().isoformat()))
            conn.commit()
            window_id = cursor.lastrowid
            conn.close()
            return {'success': True, 'id': window_id}
        except Exception as e:
            conn.close()
            return {'success': False, 'error': str(e)}
    
    def get_all_maintenance_windows(self):
        """Get all maintenance windows with device info"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT mw.*, d.name as device_name, d.ip_address
            FROM maintenance_windows mw
            LEFT JOIN devices d ON mw.device_id = d.id
            ORDER BY mw.start_time DESC
        ''')
        windows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return windows
    
    def get_active_maintenance(self, device_id=None):
        """Get currently active maintenance windows for a device or all devices"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        if device_id:
            # Check for device-specific or global (device_id=NULL) maintenance
            cursor.execute('''
                SELECT * FROM maintenance_windows 
                WHERE (device_id = ? OR device_id IS NULL)
                  AND start_time <= ? 
                  AND end_time >= ?
            ''', (device_id, now, now))
        else:
            cursor.execute('''
                SELECT * FROM maintenance_windows 
                WHERE start_time <= ? AND end_time >= ?
            ''', (now, now))
        
        windows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return windows
    
    def is_device_in_maintenance(self, device_id):
        """Check if a device is currently in maintenance window"""
        windows = self.get_active_maintenance(device_id)
        return len(windows) > 0
    
    def delete_maintenance_window(self, window_id):
        """Delete a maintenance window"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM maintenance_windows WHERE id = ?', (window_id,))
        conn.commit()
        conn.close()
        return {'success': True}
    
    def cleanup_expired_maintenance(self):
        """Remove non-recurring maintenance windows that have ended"""
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute('''
            DELETE FROM maintenance_windows 
            WHERE end_time < ? AND (recurring IS NULL OR recurring = '')
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
        cursor = conn.cursor()
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Get all status checks in the time period
        cursor.execute('''
            SELECT status, response_time, checked_at
            FROM status_history 
            WHERE device_id = ? 
              AND checked_at >= ?
            ORDER BY checked_at
        ''', (device_id, start_date.isoformat()))
        
        records = cursor.fetchall()
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
        
        # Calculate average response time for successful checks
        response_times = [r['response_time'] for r in records 
                          if r['response_time'] is not None and r['status'] != 'down']
        avg_response = sum(response_times) / len(response_times) if response_times else None
        
        # Calculate uptime (up + slow = available, just slower)
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
            
            # Determine SLA status
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
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    def get_user_by_id(self, user_id):
        """Get a user by ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    def authenticate_user(self, username, password):
        """Authenticate a user and return user data if successful"""
        from werkzeug.security import check_password_hash
        
        user = self.get_user_by_username(username)
        if not user:
            return None
        
        if not user.get('is_active', True):
            return None
        
        if check_password_hash(user['password_hash'], password):
            # Update last login time
            self.update_last_login(user['id'])
            return user
        
        return None
    
    def update_last_login(self, user_id):
        """Update the last login timestamp for a user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users SET last_login = ? WHERE id = ?
        ''', (datetime.now().isoformat(), user_id))
        conn.commit()
        conn.close()
    
    def get_all_users(self):
        """Get all users (excluding password hashes)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, username, role, display_name, email, is_active, 
                   last_login, created_at, updated_at 
            FROM users ORDER BY created_at DESC
        ''')
        users = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return users
    
    def add_user(self, username, password, role='viewer', display_name=None, email=None):
        """Add a new user"""
        from werkzeug.security import generate_password_hash
        
        if role not in ['admin', 'operator', 'viewer']:
            return {'success': False, 'error': 'Invalid role. Must be admin, operator, or viewer'}
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO users (username, password_hash, role, display_name, email, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (username, generate_password_hash(password), role, display_name, email, 
                  datetime.now().isoformat()))
            conn.commit()
            user_id = cursor.lastrowid
            conn.close()
            return {'success': True, 'id': user_id}
        except Exception as e:
            conn.close()
            if 'UNIQUE constraint failed' in str(e):
                return {'success': False, 'error': 'Username already exists'}
            return {'success': False, 'error': str(e)}
    
    def update_user(self, user_id, role=None, display_name=None, email=None, 
                    is_active=None, password=None):
        """Update user details"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        updates = []
        params = []
        
        if role is not None:
            if role not in ['admin', 'operator', 'viewer']:
                conn.close()
                return {'success': False, 'error': 'Invalid role'}
            updates.append('role = ?')
            params.append(role)
        
        if display_name is not None:
            updates.append('display_name = ?')
            params.append(display_name)
        
        if email is not None:
            updates.append('email = ?')
            params.append(email)
        
        if is_active is not None:
            updates.append('is_active = ?')
            params.append(1 if is_active else 0)
        
        if password is not None:
            from werkzeug.security import generate_password_hash
            updates.append('password_hash = ?')
            params.append(generate_password_hash(password))
        
        if not updates:
            conn.close()
            return {'success': False, 'error': 'No updates provided'}
        
        updates.append('updated_at = ?')
        params.append(datetime.now().isoformat())
        params.append(user_id)
        
        try:
            cursor.execute(f'''
                UPDATE users SET {', '.join(updates)} WHERE id = ?
            ''', params)
            conn.commit()
            conn.close()
            return {'success': True}
        except Exception as e:
            conn.close()
            return {'success': False, 'error': str(e)}
    
    def delete_user(self, user_id):
        """Delete a user (cannot delete the last admin)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Check if this is the last admin
        cursor.execute('SELECT role FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        if user and user['role'] == 'admin':
            cursor.execute('SELECT COUNT(*) as count FROM users WHERE role = ?', ('admin',))
            admin_count = cursor.fetchone()['count']
            if admin_count <= 1:
                conn.close()
                return {'success': False, 'error': 'Cannot delete the last admin user'}
        
        cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
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
        cursor = conn.cursor()
        
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
        cursor = conn.cursor()
        
        if user_id:
            cursor.execute('''
                SELECT d.*, u.username as creator_name 
                FROM dashboards d
                LEFT JOIN users u ON d.created_by = u.id
                WHERE d.is_public = 1 OR d.created_by = ?
                ORDER BY d.created_at DESC
            ''', (user_id,))
        else:
            cursor.execute('''
                SELECT d.*, u.username as creator_name 
                FROM dashboards d
                LEFT JOIN users u ON d.created_by = u.id
                ORDER BY d.created_at DESC
            ''')
            
        dashboards = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return dashboards
    
    def get_dashboard(self, dashboard_id):
        """Get a specific dashboard"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT d.*, u.username as creator_name 
            FROM dashboards d
            LEFT JOIN users u ON d.created_by = u.id
            WHERE d.id = ?
        ''', (dashboard_id,))
        
        result = cursor.fetchone()
        conn.close()
        return dict(result) if result else None
    
    def update_dashboard(self, dashboard_id, name=None, layout_config=None, description=None, is_public=None):
        """Update a dashboard"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        updates = []
        params = []
        
        if name is not None:
            updates.append('name = ?')
            params.append(name)
        
        if layout_config is not None:
            updates.append('layout_config = ?')
            params.append(layout_config)
            
        if description is not None:
            updates.append('description = ?')
            params.append(description)
            
        if is_public is not None:
            updates.append('is_public = ?')
            params.append(is_public)
            
        updates.append('updated_at = ?')
        params.append(datetime.now().isoformat())
        
        if updates:
            params.append(dashboard_id)
            cursor.execute(f'''
                UPDATE dashboards 
                SET {', '.join(updates)}
                WHERE id = ?
            ''', params)
            conn.commit()
            
        conn.close()
        return {'success': True}
    
    def delete_dashboard(self, dashboard_id):
        """Delete a dashboard"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM dashboards WHERE id = ?', (dashboard_id,))
        conn.commit()
        conn.close()
        return {'success': True}

    # =========================================================================
    # Sub-Topology Methods
    # =========================================================================

    def create_sub_topology(self, name, description=None, created_by=None, background_image=None, background_zoom=100, node_positions=None, background_opacity=100):
        """Create a new sub-topology"""
        conn = self.get_connection()
        cursor = conn.cursor()
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
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM sub_topologies ORDER BY name')
        result = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return result

    def get_sub_topology(self, sub_topo_id):
        """Get a sub-topology with its devices and connections"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Get sub-topology info
        cursor.execute('SELECT * FROM sub_topologies WHERE id = ?', (sub_topo_id,))
        sub_topo = cursor.fetchone()
        if not sub_topo:
            conn.close()
            return None
        
        result = dict(sub_topo)
        
        # Get device IDs
        cursor.execute('''
            SELECT d.* FROM devices d
            JOIN sub_topology_devices std ON d.id = std.device_id
            WHERE std.sub_topology_id = ?
            ORDER BY d.name
        ''', (sub_topo_id,))
        result['devices'] = [dict(row) for row in cursor.fetchall()]
        
        # Get connections
        cursor.execute('''
            SELECT * FROM sub_topology_connections
            WHERE sub_topology_id = ?
        ''', (sub_topo_id,))
        result['connections'] = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        return result

    def update_sub_topology(self, sub_topo_id, name=None, description=None, device_ids=None, connections=None, background_image=None, background_zoom=None, node_positions=None, background_opacity=None):
        """Update a sub-topology"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Update name/description/background
        updates = []
        params = []
        if name is not None:
            updates.append('name = ?')
            params.append(name)
        if description is not None:
            updates.append('description = ?')
            params.append(description)
        if background_image is not None:
            updates.append('background_image = ?')
            params.append(background_image)
        if background_zoom is not None:
            updates.append('background_zoom = ?')
            params.append(background_zoom)
        if node_positions is not None:
            updates.append('node_positions = ?')
            params.append(node_positions)
        if background_opacity is not None:
            updates.append('background_opacity = ?')
            params.append(background_opacity)
        updates.append('updated_at = ?')
        params.append(datetime.now().isoformat())
        
        if updates:
            params.append(sub_topo_id)
            cursor.execute(f"UPDATE sub_topologies SET {', '.join(updates)} WHERE id = ?", params)
        
        # Replace devices
        if device_ids is not None:
            cursor.execute('DELETE FROM sub_topology_devices WHERE sub_topology_id = ?', (sub_topo_id,))
            for did in device_ids:
                cursor.execute('''
                    INSERT INTO sub_topology_devices (sub_topology_id, device_id)
                    VALUES (?, ?)
                ''', (sub_topo_id, did))
        
        # Replace connections
        if connections is not None:
            cursor.execute('DELETE FROM sub_topology_connections WHERE sub_topology_id = ?', (sub_topo_id,))
            for conn_item in connections:
                cursor.execute('''
                    INSERT INTO sub_topology_connections (sub_topology_id, device_id, connected_to)
                    VALUES (?, ?, ?)
                ''', (sub_topo_id, conn_item['device_id'], conn_item['connected_to']))
        
        conn.commit()
        conn.close()
        return {'success': True}

    def delete_sub_topology(self, sub_topo_id):
        """Delete a sub-topology and its related data"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM sub_topology_connections WHERE sub_topology_id = ?', (sub_topo_id,))
        cursor.execute('DELETE FROM sub_topology_devices WHERE sub_topology_id = ?', (sub_topo_id,))
        cursor.execute('DELETE FROM sub_topologies WHERE id = ?', (sub_topo_id,))
        conn.commit()
        conn.close()
        return {'success': True}
