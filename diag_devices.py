from database import Database
from config import Config
import json

db = Database()
devices = db.get_all_devices()

print(f"Total devices: {len(devices)}")
for d in devices:
    print(f"ID: {d['id']}, Name: {d['name']}, IP: {d['ip_address']}, Status: {d['status']}, Last Check: {d['last_check']}")

print("\nConfig Settings:")
print(f"PING_INTERVAL: {Config.PING_INTERVAL}")
print(f"MONITOR_MAX_WORKERS: {Config.MONITOR_MAX_WORKERS}")
print(f"FAILURE_THRESHOLD: {Config.FAILURE_THRESHOLD}")
