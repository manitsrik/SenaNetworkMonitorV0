
import sys
import os
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from database import Database

def check_devices():
    db = Database()
    devices = db.get_all_devices()
    print("ALL Devices matching 172.41.1.63:")
    found_any = False
    for d in devices:
        if '172.41.1.63' in str(d.get('ip_address', '')):
            print(f"ID: {d['id']}, Name: {d['name']}, IP: {d['ip_address']}, "
                  f"Monitor: {d['monitor_type']}, Type: {d['device_type']}, Port: {d.get('tcp_port')}")
            found_any = True
    if not found_any:
        print("No devices found matching 172.41.1.63.")

if __name__ == "__main__":
    check_devices()
