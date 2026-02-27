from app import app
import json

def test():
    client = app.test_client()
    response = client.get('/api/statistics/trend?minutes=180')
    data = json.loads(response.data)
    
    cctv_items = [item for item in data if item.get('device_type') == 'cctv']
    print(f"Total CCTV items: {len(cctv_items)}")
    for item in cctv_items[:10]:
        print(f"Timestamp: {item['timestamp']}, Avg Response Time: {item['avg_response_time']}")

if __name__ == "__main__":
    test()
