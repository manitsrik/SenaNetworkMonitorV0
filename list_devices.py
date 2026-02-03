from database import Database

db = Database()
devices = db.get_all_devices()

print("=" * 60)
print("รายการอุปกรณ์ทั้งหมดในระบบ")
print("=" * 60)
print(f"จำนวนอุปกรณ์ทั้งหมด: {len(devices)}\n")

if devices:
    for i, device in enumerate(devices, 1):
        print(f"{i}. {device['name']}")
        print(f"   ID: {device['id']}")
        print(f"   IP Address: {device['ip_address']}")
        print(f"   Type: {device['device_type']}")
        print(f"   Location: {device['location']}")
        print(f"   Status: {device['status']}")
        print(f"   Response Time: {device['response_time']} ms" if device['response_time'] else "   Response Time: N/A")
        print(f"   Last Check: {device['last_check']}" if device['last_check'] else "   Last Check: Never")
        print("-" * 60)
else:
    print("ไม่มีอุปกรณ์ในระบบ")

print("=" * 60)
