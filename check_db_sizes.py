import sqlite3
import os

db_path = 'network_monitor.db'

def get_table_sizes():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    
    print(f"{'Table Name':<20} | {'Row Count':>15}")
    print("-" * 38)
    
    for table in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"{table:<20} | {count:>15,}")
            
            # Print schema
            cursor.execute(f"SELECT sql FROM sqlite_master WHERE name='{table}'")
            sql = cursor.fetchone()[0]
            print(f"Schema: {sql}")
            
            # Get indexes
            cursor.execute(f"PRAGMA index_list('{table}')")
            indexes = cursor.fetchall()
            if indexes:
                print("Indexes:")
                for idx in indexes:
                    print(f"  - {idx[1]}")
            print("-" * 38)
        except Exception as e:
            print(f"{table:<20} | Error: {e}")
            
    conn.close()

if __name__ == "__main__":
    if os.path.exists(db_path):
        get_table_sizes()
    else:
        print("Database not found.")
