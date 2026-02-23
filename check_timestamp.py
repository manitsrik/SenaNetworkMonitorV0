from database import Database

db = Database()
conn = db.get_connection()
cursor = conn.cursor()

print("Checking 'checked_at' format (last 5 entries):")
cursor.execute("SELECT checked_at, response_time, status FROM status_history ORDER BY checked_at DESC LIMIT 5")
for row in cursor.fetchall():
    print(dict(row))

conn.close()
