"""
Migrate data from SQLite to PostgreSQL
Transfers all tables preserving IDs and sequences
"""
import sqlite3
import psycopg2
import psycopg2.extras
import sys
from config import Config

def get_sqlite_conn():
    conn = sqlite3.connect(Config.DATABASE_PATH, timeout=60)
    conn.row_factory = sqlite3.Row
    return conn

def get_pg_conn():
    return psycopg2.connect(
        host=Config.PG_HOST,
        port=Config.PG_PORT,
        dbname=Config.PG_DATABASE,
        user=Config.PG_USER,
        password=Config.PG_PASSWORD
    )

def get_table_count(conn, table, is_pg=False):
    if is_pg:
        cur = conn.cursor()
    else:
        cur = conn.cursor()
    cur.execute(f'SELECT COUNT(*) FROM {table}')
    return cur.fetchone()[0]

def migrate_table(sqlite_conn, pg_conn, table, columns, batch_size=1000):
    """Migrate a single table from SQLite to PostgreSQL"""
    cur_sqlite = sqlite_conn.cursor()
    cur_pg = pg_conn.cursor()
    
    # Check if table already has data
    cur_pg.execute(f'SELECT COUNT(*) FROM {table}')
    existing = cur_pg.fetchone()[0]
    
    cur_sqlite.execute(f'SELECT COUNT(*) FROM {table}')
    total = cur_sqlite.fetchone()[0]
    
    if existing > 0 and table == 'users':
        # For users table, clear default users first then re-insert from SQLite
        cur_pg.execute('DELETE FROM users')
        pg_conn.commit()
        existing = 0
    elif existing > 0:
        print(f"  [SKIP] {table}: already has {existing} rows, skipping")
        return existing
    
    if total == 0:
        print(f"  [SKIP] {table}: no data in SQLite")
        return 0
    
    cols_str = ', '.join(columns)
    placeholders = ', '.join(['%s'] * len(columns))
    
    cur_sqlite.execute(f'SELECT {cols_str} FROM {table} ORDER BY id')
    
    migrated = 0
    batch = []
    
    for row in cur_sqlite:
        values = []
        for i, col in enumerate(columns):
            val = row[i]
            # Convert SQLite boolean integers to Python bools for PostgreSQL
            if col in ('is_active', 'is_public') and val is not None:
                val = bool(val)
            values.append(val)
        batch.append(tuple(values))
        
        if len(batch) >= batch_size:
            psycopg2.extras.execute_batch(
                cur_pg,
                f'INSERT INTO {table} ({cols_str}) VALUES ({placeholders})',
                batch
            )
            migrated += len(batch)
            batch = []
            print(f"  ... {table}: {migrated}/{total}", end='\r')
    
    if batch:
        psycopg2.extras.execute_batch(
            cur_pg,
            f'INSERT INTO {table} ({cols_str}) VALUES ({placeholders})',
            batch
        )
        migrated += len(batch)
    
    # Reset sequence to max id
    cur_pg.execute(f"SELECT MAX(id) FROM {table}")
    max_id = cur_pg.fetchone()[0]
    if max_id:
        cur_pg.execute(f"SELECT setval('{table}_id_seq', {max_id})")
    
    pg_conn.commit()
    print(f"  [OK] {table}: {migrated} rows migrated")
    return migrated

def verify_migration(sqlite_conn, pg_conn, tables):
    """Verify record counts match"""
    print("\n" + "=" * 50)
    print("VERIFICATION")
    print("=" * 50)
    
    all_ok = True
    for table in tables:
        sqlite_count = get_table_count(sqlite_conn, table)
        pg_count = get_table_count(pg_conn, table, is_pg=True)
        
        status = "[OK]" if sqlite_count == pg_count else "[FAIL]"
        if sqlite_count != pg_count:
            all_ok = False
        
        print(f"  {status} {table}: SQLite={sqlite_count}, PostgreSQL={pg_count}")
    
    return all_ok

def main():
    verify_only = '--verify' in sys.argv
    
    print("=" * 50)
    print("SQLite -> PostgreSQL Data Migration")
    print("=" * 50)
    print(f"SQLite: {Config.DATABASE_PATH}")
    print(f"PostgreSQL: {Config.PG_HOST}:{Config.PG_PORT}/{Config.PG_DATABASE}")
    print()
    
    sqlite_conn = get_sqlite_conn()
    pg_conn = get_pg_conn()
    
    # Table definitions with their columns (in dependency order)
    tables = {
        'devices': ['id', 'name', 'ip_address', 'device_type', 'location', 'status',
                     'last_check', 'response_time', 'created_at', 'monitor_type',
                     'http_status_code', 'expected_status_code', 'snmp_community',
                     'snmp_port', 'snmp_version', 'snmp_uptime', 'snmp_sysname',
                     'snmp_sysdescr', 'snmp_syslocation', 'snmp_syscontact',
                     'tcp_port', 'dns_query_domain', 'ssl_expiry_date', 'ssl_days_left',
                     'ssl_issuer', 'ssl_status', 'location_type', 'failure_count'],
        'users': ['id', 'username', 'password_hash', 'role', 'display_name', 'email',
                  'is_active', 'last_login', 'created_at', 'updated_at'],
        'topology': ['id', 'device_id', 'connected_to', 'view_type'],
        'status_history': ['id', 'device_id', 'status', 'response_time', 'checked_at'],
        'alert_settings': ['id', 'setting_key', 'setting_value', 'updated_at'],
        'alert_history': ['id', 'device_id', 'event_type', 'message', 'channel',
                          'status', 'error_message', 'created_at'],
        'maintenance_windows': ['id', 'name', 'device_id', 'start_time', 'end_time',
                                'recurring', 'description', 'created_at'],
        'dashboards': ['id', 'name', 'description', 'layout_config', 'created_by',
                       'is_public', 'created_at', 'updated_at'],
        'sub_topologies': ['id', 'name', 'description', 'created_by', 'background_image',
                           'background_zoom', 'node_positions', 'background_opacity',
                           'created_at', 'updated_at'],
        'sub_topology_devices': ['id', 'sub_topology_id', 'device_id'],
        'sub_topology_connections': ['id', 'sub_topology_id', 'device_id', 'connected_to'],
    }
    
    if verify_only:
        verify_migration(sqlite_conn, pg_conn, list(tables.keys()))
    else:
        print("Migrating data...\n")
        for table, columns in tables.items():
            try:
                migrate_table(sqlite_conn, pg_conn, table, columns)
            except Exception as e:
                print(f"  [FAIL] {table}: ERROR - {e}")
                pg_conn.rollback()
        
        verify_migration(sqlite_conn, pg_conn, list(tables.keys()))
    
    sqlite_conn.close()
    pg_conn.close()
    print("\nDone!")

if __name__ == '__main__':
    main()
