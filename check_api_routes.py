
from app import app
from database import Database
import json
import unittest

class APITest(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()
        self.db = Database()

    def login(self, username, password):
        return self.client.post('/login', data=dict(
            username=username,
            password=password
        ), follow_redirects=True)

    def test_dashboard_lifecyle(self):
        print("\nTesting Dashboard API...")

        # 1. Login as admin
        login_resp = self.login('admin', 'admin')
        with self.client.session_transaction() as sess:
            if not sess.get('logged_in'):
                self.fail("[FAIL] Login failed")
            print("[PASS] Login successful")

        # 2. Create Dashboard
        payload = {
            "name": "API Test Dashboard",
            "description": "Created via test script",
            "layout_config": [{"type": "test"}],
            "is_public": 1
        }
        resp = self.client.post('/api/dashboards', 
                        data=json.dumps(payload), 
                        content_type='application/json')

        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertTrue(data['success'])
        print(f"[PASS] Create dashboard: ID {data['id']}")
        dash_id = data['id']

        # 3. Get Dashboards
        resp = self.client.get('/api/dashboards')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        found = False
        for d in data:
            if d['id'] == dash_id:
                found = True
                break
        self.assertTrue(found, "Dashboard not found in list")
        print("[PASS] Get dashboards lists new dashboard")

        # 4. Get Single Dashboard
        resp = self.client.get(f'/api/dashboards/{dash_id}')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data['name'], "API Test Dashboard")
        print("[PASS] Get single dashboard")

        # 5. Delete Dashboard
        resp = self.client.delete(f'/api/dashboards/{dash_id}')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertTrue(data['success'])
        print("[PASS] Delete dashboard")

if __name__ == '__main__':
    unittest.main()
