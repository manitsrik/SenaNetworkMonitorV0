"""
Test script to verify RBAC is working correctly
"""
import requests

BASE_URL = "http://localhost:5000"

def test_viewer_restrictions():
    # Create a session to maintain cookies
    session = requests.Session()
    
    # Login as viewer
    print("=" * 60)
    print("Testing RBAC for VIEWER role")
    print("=" * 60)
    
    login_resp = session.post(f"{BASE_URL}/login", data={
        'username': 'viewer',
        'password': 'viewer'
    }, allow_redirects=False)
    
    print(f"\n1. Login as viewer: {login_resp.status_code}")
    
    # Try to add a device (should be 403)
    print("\n2. Try to ADD device (POST /api/devices)...")
    add_resp = session.post(f"{BASE_URL}/api/devices", json={
        'name': 'Test Device',
        'ip_address': '192.168.1.999',
        'device_type': 'server'
    })
    print(f"   Status: {add_resp.status_code}")
    print(f"   Response: {add_resp.text[:200]}")
    
    # Try to update a device (should be 403)
    print("\n3. Try to UPDATE device (PUT /api/devices/1)...")
    update_resp = session.put(f"{BASE_URL}/api/devices/1", json={
        'name': 'Modified Name'
    })
    print(f"   Status: {update_resp.status_code}")
    print(f"   Response: {update_resp.text[:200]}")
    
    # Try to save alert settings (should be 403)
    print("\n4. Try to SAVE settings (POST /api/alert-settings)...")
    settings_resp = session.post(f"{BASE_URL}/api/alert-settings", json={
        'telegram_enabled': 'true'
    })
    print(f"   Status: {settings_resp.status_code}")
    print(f"   Response: {settings_resp.text[:200]}")
    
    # GET should still work
    print("\n5. Try to GET devices (GET /api/devices)...")
    get_resp = session.get(f"{BASE_URL}/api/devices")
    print(f"   Status: {get_resp.status_code}")
    print(f"   Response: {get_resp.text[:100]}...")
    
    print("\n" + "=" * 60)
    print("EXPECTED: Steps 2, 3, 4 should return 403 Forbidden")
    print("EXPECTED: Step 5 should return 200 OK")
    print("=" * 60)

if __name__ == "__main__":
    test_viewer_restrictions()
