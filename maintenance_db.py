"""
Database Maintenance Script for Network Monitor
Prunes old records and optimizes indexes to maintain performance.
"""
import os
import sys
from datetime import datetime, timedelta
from database import Database
from config import Config

def run_maintenance():
    print(f"[{datetime.now()}] Starting Database Maintenance...")
    db = Database()
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # Define retention period (7 days for history, 30 days for alerts)
    history_retention_days = 7
    alert_retention_days = 30
    
    history_cutoff = (datetime.now() - timedelta(days=history_retention_days)).strftime('%Y-%m-%d %H:%M:%S')
    alert_cutoff = (datetime.now() - timedelta(days=alert_retention_days)).strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        # 1. Count before
        cursor.execute("SELECT COUNT(*) FROM status_history")
        before_count = cursor.fetchone()[0]
        print(f"Current status_history records: {before_count:,}")
        
        # 2. Prune status_history
        print(f"Pruning status_history records older than {history_cutoff}...")
        cursor.execute("DELETE FROM status_history WHERE checked_at < %s", (history_cutoff,))
        deleted_history = cursor.rowcount
        print(f"Successfully deleted {deleted_history:,} history records.")
        
        # 3. Prune alert_history
        print(f"Pruning alert_history records older than {alert_cutoff}...")
        cursor.execute("DELETE FROM alert_history WHERE created_at < %s", (alert_cutoff,))
        deleted_alerts = cursor.rowcount
        print(f"Successfully deleted {deleted_alerts:,} alert records.")
        
        # 4. Commit changes
        conn.commit()
        
        # 5. Optimize (PostgreSQL specific)
        if db.db_type == 'postgresql':
            print("Running VACUUM ANALYZE on PostgreSQL tables...")
            # VACUUM cannot run inside a transaction block
            conn.set_isolation_level(0) # AUTOCOMMIT
            cursor.execute("VACUUM ANALYZE status_history")
            cursor.execute("VACUUM ANALYZE alert_history")
            cursor.execute("VACUUM ANALYZE job_history")
            print("PostgreSQL optimization complete.")
            
        # 6. Count after
        cursor.execute("SELECT COUNT(*) FROM status_history")
        after_count = cursor.fetchone()[0]
        print(f"Final status_history records: {after_count:,}")
        print(f"Total space reclaimed effort completed.")

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Maintenance failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cursor.close()
        db.release_connection(conn)
        print(f"[{datetime.now()}] Maintenance Finished.")

if __name__ == "__main__":
    run_maintenance()
