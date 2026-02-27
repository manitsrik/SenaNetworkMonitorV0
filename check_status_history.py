import sqlite3

db_path = 'network_monitor.db'

def get_status_history_info():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("Schema for status_history:")
    cursor.execute("SELECT sql FROM sqlite_master WHERE name='status_history'")
    print(cursor.fetchone()[0])
    
    print("\nIndexes for status_history:")
    cursor.execute("PRAGMA index_list('status_history')")
    indexes = cursor.fetchall()
    for idx in indexes:
        idx_name = idx[1]
        print(f"\nIndex: {idx_name}")
        cursor.execute(f"PRAGMA index_info('{idx_name}')")
        cols = cursor.fetchall()
        for col in cols:
            print(f"  - Column: {col[2]}")
            
    conn.close()

if __name__ == "__main__":
    get_status_history_info()
