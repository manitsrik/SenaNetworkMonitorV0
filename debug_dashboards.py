import sqlite3
import json

def debug():
    conn = sqlite3.connect('network_monitor.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, layout_config FROM dashboards')
    rows = cursor.fetchall()
    for row in rows:
        print(f"ID: {row['id']}, Name: {row['name']}")
        try:
            config = json.loads(row['layout_config'])
            # Look for trends widget and its config
            for widget in config:
                if widget.get('type') == 'trends':
                    print(f"  Trends Widget Config: {widget.get('config')}")
        except Exception as e:
            print(f"  Error parsing config: {e}")
    conn.close()

if __name__ == "__main__":
    debug()
