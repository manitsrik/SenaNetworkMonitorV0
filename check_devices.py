import sqlite3

try:
    conn = sqlite3.connect('network_monitor.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, ip_address, device_type FROM devices WHERE name LIKE '%WLC%' OR name LIKE '%AP%'")
    rows = cursor.fetchall()
    for row in rows:
        print(row)
    conn.close()
except Exception as e:
    print(f"Error: {e}")
