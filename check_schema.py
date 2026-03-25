
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from database import Database

def check_schema():
    db = Database()
    conn = db.get_connection()
    cursor = db._cursor(conn)
    
    print("Indexes on 'devices' table:")
    if db.db_type == 'postgresql':
        cursor.execute("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'devices'")
    else:
        cursor.execute("PRAGMA index_list('devices')")
        
    rows = cursor.fetchall()
    for row in rows:
        print(row)
    
    db.release_connection(conn)

if __name__ == "__main__":
    check_schema()
