from database import Database
from datetime import datetime, timedelta

db = Database()

# Check latest entries in status_history
print("\n--- Latest status_history entries ---")
conn = db.get_connection()
cursor = conn.cursor()
cursor.execute('SELECT * FROM status_history ORDER BY checked_at DESC LIMIT 5')
rows = cursor.fetchall()
for row in rows:
    print(dict(row))
conn.close()

# Check get_device_type_trends output
print("\n--- get_device_type_trends(180) output ---")
try:
    trends = db.get_device_type_trends(180)
    print(f"Count: {len(trends)}")
    for t in trends[:5]:
        print(t)
except Exception as e:
    print(f"Error: {e}")
