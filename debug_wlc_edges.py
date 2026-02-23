
import sqlite3
import os

db_path = r"c:\Project\NW MonitorV0\network_monitor.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

query = """
SELECT 
    t.id, 
    d1.name as source, 
    d2.name as target, 
    t.view_type 
FROM 
    topology t 
JOIN 
    devices d1 ON t.device_id = d1.id 
JOIN 
    devices d2 ON t.connected_to = d2.id 
WHERE 
    d1.name = 'WLC' OR d2.name = 'WLC'
ORDER BY 
    source, target
"""

cursor.execute(query)
rows = cursor.fetchall()
print(f"Total connections found: {len(rows)}")
for row in rows:
    print(row)

conn.close()
