import sqlite3
import time
import os
from datetime import datetime, timedelta
from config import Config

db_path = Config.DATABASE_PATH
retention_days = getattr(Config, 'RETENTION_DAYS', 30)

def optimize():
    if not os.path.exists(db_path):
        print(f"Database {db_path} not found.")
        return

    print(f"Starting database optimization for {db_path}...")
    start_total = time.time()
    
    conn = sqlite3.connect(db_path)
    conn.isolation_level = None # Autocommit mode for some operations
    cursor = conn.cursor()

    try:
        # 1. Create Indexes
        print("--- Step 1: Creating Indexes ---")
        
        # Index on checked_at for fast time-based filtering (Trends/SLA)
        print("Creating index idx_status_history_checked_at...")
        s = time.time()
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_status_history_checked_at ON status_history(checked_at);")
        print(f"Done in {time.time() - s:.2f}s")

        # Composite index for device-specific history lookups
        print("Creating index idx_status_history_device_checked...")
        s = time.time()
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_status_history_device_checked ON status_history(device_id, checked_at);")
        print(f"Done in {time.time() - s:.2f}s")

        # 2. Prune Old Data
        print("--- Step 2: Pruning Old Data ---")
        cutoff_date = (datetime.now() - timedelta(days=retention_days)).isoformat()
        print(f"Deleting status history older than {retention_days} days ({cutoff_date})...")
        
        s = time.time()
        cursor.execute("DELETE FROM status_history WHERE checked_at < ?;", (cutoff_date,))
        deleted_count = cursor.rowcount
        print(f"Deleted {deleted_count:,} rows in {time.time() - s:.2f}s")
        
        print("Deleting old alerts...")
        cursor.execute("DELETE FROM alert_history WHERE created_at < ?;", (cutoff_date,))
        print(f"Deleted {cursor.rowcount} alerts.")

        # 3. Vacuum (Reclaim Space)
        print("--- Step 3: Reclaiming Space (VACUUM) ---")
        print("This may take a several minutes for large databases...")
        s = time.time()
        cursor.execute("VACUUM;")
        print(f"VACUUM completed in {time.time() - s:.2f}s")

        # 4. Analyze (Update Statistics)
        print("--- Step 4: Updating Optimizer Statistics ---")
        cursor.execute("ANALYZE;")
        print("ANALYZE completed.")

    except Exception as e:
        print(f"Error during optimization: {e}")
    finally:
        conn.close()

    print(f"\nOptimization complete! Total time: {time.time() - start_total:.2f}s")
    
    # Show final file size
    size_mb = os.path.getsize(db_path) / (1024 * 1024)
    print(f"Final database size: {size_mb:.2f} MB")

if __name__ == "__main__":
    optimize()
