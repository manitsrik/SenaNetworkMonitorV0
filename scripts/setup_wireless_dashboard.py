import sqlite3
import json
import os

DB_PATH = 'network_monitor.db'

def setup_wireless_dashboard():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if exists, delete if so to update layout
    cursor.execute("SELECT id FROM dashboards WHERE name = 'Wireless Dashboard'")
    existing = cursor.fetchone()
    
    if existing:
        print("Wireless Dashboard exists. Updating layout...")
        # We will delete and recreate or just update. Updating is safer to keep ID.
        dashboard_id = existing[0]
    else:
        print("Creating new Wireless Dashboard...")
        dashboard_id = None

    # Define layout configuration matching the redesign
    # Row 1: 5 Stat Cards (Total, Up, Slow, Down, Latency)
    # Row 2: Gauge (3), Topology (6), Device Grid (3)
    # Row 3: Alerts (6), Activity (6)
    
    layout_config = [
        # Row 1: Stat Cards (Width 2-3 to fit 5 items? 12cols / 5 = 2.4. Let's use 2 and 3)
        # Actually in 12-col grid, 5 items is hard. 2,2,2,2,4? Or 2.4? Visjs grid doesn't support fractional.
        # Let's do 5 items of width 2? That's 10 cols. Centered?
        # Or Just 4 items width 3?
        # The image shows 5 cards.
        # Let's try width 2 for all, they will take 10 cols. Maybe add a spacer or just let them be left aligned.
        # Or width 2, 2, 2, 2, 4?
        # Let's try to fit meaningful stats. Uptime, Online, Latency, Slow, Alerts.
        

        { 
            "type": "stat_row", 
            "title": "Statistics", 
            "width": 12, 
            "cards": [
                { "type": "stat_card", "title": "Wireless Uptime", "statType": "uptime", "config": { "deviceType": "wireless" } },
                { "type": "stat_card", "title": "Online APs", "statType": "up", "config": { "deviceType": "wireless" } },
                { "type": "stat_card", "title": "Avg AP Latency", "statType": "latency", "config": { "deviceType": "wireless" } },
                { "type": "stat_card", "title": "Slow APs", "statType": "slow", "config": { "deviceType": "wireless" } },
                { "type": "stat_card", "title": "Alerts", "statType": "down", "config": { "deviceType": "wireless" } }
            ]
        },
        
        # Row 2: Main Content



        { "type": "performance", "title": "Avg Latency & Slow Devices", "width": 3, "config": { "deviceType": "wireless" } },
        { "type": "topology", "title": "Wireless Mesh Topology", "width": 6, "config": { "deviceType": "wireless" } },

        { "type": "alerts", "title": "Active Wireless Alerts", "width": 3, "config": { "deviceType": "wireless" } },
        
        # Row 3: Bottom
        { "type": "activity", "title": "Recent Activity", "width": 12, "config": { "deviceType": "wireless" } }
    ]
    
    # Get admin user id
    cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
    admin_user = cursor.fetchone()
    admin_id = admin_user[0] if admin_user else 1

    if dashboard_id:
        cursor.execute('''
            UPDATE dashboards 
            SET layout_config = ?, description = ?
            WHERE id = ?
        ''', (json.dumps(layout_config), 'Monitor wireless access points and mesh networks', dashboard_id))
    else:
        cursor.execute('''
            INSERT INTO dashboards (name, description, layout_config, created_by, is_public)
            VALUES (?, ?, ?, ?, ?)
        ''', ('Wireless Dashboard', 'Monitor wireless access points and mesh networks', json.dumps(layout_config), admin_id, 1))
    
    conn.commit()
    print("Wireless Dashboard updated successfully.")
    conn.close()

if __name__ == "__main__":
    setup_wireless_dashboard()
