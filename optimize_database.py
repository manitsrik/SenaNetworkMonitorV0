"""
Database optimization script for Network Monitor
Supports both SQLite and PostgreSQL
"""
import time
import os
from datetime import datetime, timedelta
from config import Config

retention_days = getattr(Config, 'RETENTION_DAYS', 30)


def optimize_sqlite():
    """Optimize SQLite database"""
    import sqlite3
    
    db_path = Config.DATABASE_PATH
    if not os.path.exists(db_path):
        print(f"SQLite database {db_path} not found.")
        return

    print(f"Starting SQLite optimization for {db_path}...")
    start_total = time.time()
    
    conn = sqlite3.connect(db_path)
    conn.isolation_level = None  # Autocommit mode for some operations
    cursor = conn.cursor()

    try:
        # 1. Create Indexes
        print("--- Step 1: Creating Indexes ---")
        
        indexes = [
            ("idx_sh_checked_at", "status_history(checked_at)"),
            ("idx_sh_device_checked", "status_history(device_id, checked_at)"),
            ("idx_sh_device_status", "status_history(device_id, status, checked_at)"),
            ("idx_ah_device_event", "alert_history(device_id, event_type, created_at)"),
            ("idx_ah_created_at", "alert_history(created_at)"),
            ("idx_devices_type", "devices(device_type)"),
            ("idx_devices_status", "devices(status)"),
        ]
        
        for idx_name, idx_def in indexes:
            s = time.time()
            cursor.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_def}")
            print(f"  {idx_name}: {time.time() - s:.2f}s")

        # 2. Prune Old Data
        print("--- Step 2: Pruning Old Data ---")
        cutoff_date = (datetime.now() - timedelta(days=retention_days)).isoformat()
        print(f"Deleting data older than {retention_days} days ({cutoff_date})...")
        
        s = time.time()
        cursor.execute("DELETE FROM status_history WHERE checked_at < ?;", (cutoff_date,))
        print(f"  status_history: deleted {cursor.rowcount:,} rows in {time.time() - s:.2f}s")
        
        cursor.execute("DELETE FROM alert_history WHERE created_at < ?;", (cutoff_date,))
        print(f"  alert_history: deleted {cursor.rowcount:,} rows")

        # 3. Vacuum (Reclaim Space)
        print("--- Step 3: Reclaiming Space (VACUUM) ---")
        s = time.time()
        cursor.execute("VACUUM;")
        print(f"  VACUUM completed in {time.time() - s:.2f}s")

        # 4. Analyze (Update Statistics)
        print("--- Step 4: Updating Optimizer Statistics ---")
        cursor.execute("ANALYZE;")
        print("  ANALYZE completed.")

    except Exception as e:
        print(f"Error during optimization: {e}")
    finally:
        conn.close()

    print(f"\nOptimization complete! Total time: {time.time() - start_total:.2f}s")
    
    # Show final file size
    size_mb = os.path.getsize(db_path) / (1024 * 1024)
    print(f"Final database size: {size_mb:.2f} MB")


def optimize_postgresql():
    """Optimize PostgreSQL database"""
    try:
        import psycopg2
    except ImportError:
        print("psycopg2 not installed. Cannot optimize PostgreSQL.")
        return
    
    print(f"Starting PostgreSQL optimization...")
    print(f"  Host: {Config.PG_HOST}:{Config.PG_PORT}/{Config.PG_DATABASE}")
    start_total = time.time()
    
    try:
        conn = psycopg2.connect(
            host=Config.PG_HOST,
            port=Config.PG_PORT,
            dbname=Config.PG_DATABASE,
            user=Config.PG_USER,
            password=Config.PG_PASSWORD
        )
    except Exception as e:
        print(f"Failed to connect to PostgreSQL: {e}")
        return
    
    cursor = conn.cursor()
    
    try:
        # 1. Create Indexes
        print("--- Step 1: Creating/Verifying Indexes ---")
        indexes = [
            ("idx_sh_checked_at", "status_history(checked_at)"),
            ("idx_sh_device_checked", "status_history(device_id, checked_at)"),
            ("idx_sh_device_status", "status_history(device_id, status, checked_at)"),
            ("idx_ah_device_event", "alert_history(device_id, event_type, created_at)"),
            ("idx_ah_created_at", "alert_history(created_at)"),
            ("idx_devices_type", "devices(device_type)"),
            ("idx_devices_status", "devices(status)"),
        ]
        
        for idx_name, idx_def in indexes:
            s = time.time()
            cursor.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_def}")
            print(f"  {idx_name}: {time.time() - s:.2f}s")
        conn.commit()
        
        # 2. Prune Old Data
        print("--- Step 2: Pruning Old Data ---")
        cutoff_date = (datetime.now() - timedelta(days=retention_days)).isoformat()
        print(f"Deleting data older than {retention_days} days...")
        
        s = time.time()
        cursor.execute("DELETE FROM status_history WHERE checked_at < %s", (cutoff_date,))
        print(f"  status_history: deleted {cursor.rowcount:,} rows in {time.time() - s:.2f}s")
        
        cursor.execute("DELETE FROM alert_history WHERE created_at < %s", (cutoff_date,))
        print(f"  alert_history: deleted {cursor.rowcount:,} rows")
        conn.commit()
        
        # 3. VACUUM ANALYZE (requires autocommit)
        print("--- Step 3: VACUUM ANALYZE ---")
        conn.autocommit = True
        
        for table in ['status_history', 'alert_history', 'devices']:
            s = time.time()
            cursor.execute(f"VACUUM ANALYZE {table}")
            print(f"  {table}: {time.time() - s:.2f}s")
        
        # 4. Table size info
        print("--- Step 4: Table Sizes ---")
        conn.autocommit = False
        cursor.execute("""
            SELECT 
                relname as table_name,
                pg_size_pretty(pg_total_relation_size(relid)) as total_size,
                n_live_tup as row_count
            FROM pg_stat_user_tables
            WHERE schemaname = 'public'
            ORDER BY pg_total_relation_size(relid) DESC
        """)
        
        print(f"  {'Table':<30} {'Size':<15} {'Rows':<15}")
        print(f"  {'-'*30} {'-'*15} {'-'*15}")
        for row in cursor.fetchall():
            print(f"  {row[0]:<30} {row[1]:<15} {row[2]:<15}")
        
    except Exception as e:
        print(f"Error during optimization: {e}")
        conn.rollback()
    finally:
        conn.close()

    print(f"\nOptimization complete! Total time: {time.time() - start_total:.2f}s")


def optimize():
    """Run optimization based on configured database type"""
    print("=" * 60)
    print("Network Monitor — Database Optimization")
    print(f"DB Type: {Config.DB_TYPE}")
    print(f"Retention: {retention_days} days")
    print("=" * 60)
    
    if Config.DB_TYPE == 'postgresql':
        optimize_postgresql()
    else:
        optimize_sqlite()


if __name__ == "__main__":
    optimize()
