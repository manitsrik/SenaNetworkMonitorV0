from database import Database

db = Database()
users = db.get_all_users()

print("Users in Database:")
print("-" * 50)
for u in users:
    print(f"  Username: {u['username']}")
    print(f"  Role: {u['role']}")
    print(f"  Active: {u.get('is_active', True)}")
    print("-" * 50)
