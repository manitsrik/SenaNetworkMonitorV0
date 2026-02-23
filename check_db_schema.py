
from database import Database
import json
import os

db_path = r"c:\Project\NW MonitorV0\network_monitor.db"
# Ensure we use the correct DB path
db = Database(db_path=db_path)

print("Checking dashboards table...")
conn = db.get_connection()
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='dashboards'")
if cursor.fetchone():
    print("[PASS] Table 'dashboards' exists.")
else:
    print("[FAIL] Table 'dashboards' does not exist.")
    exit(1)

print("Testing CRUD operations...")
# Create
layout = json.dumps([{"type": "gauge", "title": "Test Gauge"}])
result = db.create_dashboard("Test Dashboard", layout, "Description", 1, 0)
if result['success']:
    print(f"[PASS] Create dashboard: ID {result['id']}")
    dash_id = result['id']
else:
    print("[FAIL] Create dashboard failed")
    exit(1)

# Read
dash = db.get_dashboard(dash_id)
if dash and dash['name'] == "Test Dashboard":
    print("[PASS] Get dashboard")
else:
    print("[FAIL] Get dashboard mismatch")

# Update
db.update_dashboard(dash_id, name="Updated Dashboard")
dash = db.get_dashboard(dash_id)
if dash and dash['name'] == "Updated Dashboard":
    print("[PASS] Update dashboard")
else:
    print("[FAIL] Update dashboard mismatch")

# Delete
db.delete_dashboard(dash_id)
dash = db.get_dashboard(dash_id)
if not dash:
    print("[PASS] Delete dashboard")
else:
    print("[FAIL] Delete dashboard failed")

print("All tests passed.")
