from database import Database

db = Database()
conn = db.get_connection()
cursor = conn.cursor()

print("Status distribution in status_history:")
cursor.execute("SELECT status, COUNT(*) FROM status_history GROUP BY status")
for row in cursor.fetchall():
    print(f"{row['status']}: {row[1]}")

conn.close()
