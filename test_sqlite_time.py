import sqlite3

conn = sqlite3.connect(':memory:')
cursor = conn.cursor()

# Create table
cursor.execute('CREATE TABLE test (ts TIMESTAMP)')

# Insert ISO format with T
cursor.execute("INSERT INTO test VALUES ('2023-10-27T10:30:00.123456')")

# Query with strftime
cursor.execute("SELECT strftime('%Y-%m-%d %H:%M', ts) FROM test")
result = cursor.fetchone()
print(f"Result with T: {result[0]}")

# Insert format with space
cursor.execute("INSERT INTO test VALUES ('2023-10-27 10:30:00.123456')")
cursor.execute("SELECT strftime('%Y-%m-%d %H:%M', ts) FROM test WHERE ts LIKE '% %'")
result = cursor.fetchone()
print(f"Result with space: {result[0]}")

conn.close()
