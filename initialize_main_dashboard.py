import sqlite3
import json
import os

DB_PATH = 'network_monitor.db'

def initialize_main_dashboard():
    layout_config = [
        # Top Stats Row
        {
            "id": "stats-row",
            "type": "stat_row",
            "title": "Network Statistics",
            "width": 12,
            "height": 180,
            "cards": [
                { "type": "stat_card", "statType": "uptime", "title": "SYSTEM UPTIME" },
                { "type": "stat_card", "statType": "up", "title": "ONLINE DEVICES" },
                { "type": "stat_card", "statType": "latency", "title": "AVG LATENCY" },
                { "type": "stat_card", "statType": "slow", "title": "SLOW DEVICES" },
                { "type": "stat_card", "statType": "down", "title": "ACTIVE ALERTS" }
            ]
        },
        # Left Column - Gauges and Trends
        {
            "id": "avg-response-gauge",
            "type": "gauge",
            "title": "Current Avg Response",
            "width": 4,
            "height": 350
        },
        # Right Column - Topology
        {
            "id": "main-topology",
            "type": "topology",
            "title": "Network Topology",
            "width": 8,
            "height": 350
        },
        # Left Column - Response Trends
        {
            "id": "response-trends",
            "type": "trends",
            "title": "Response Time Trends",
            "width": 4,
            "height": 350,
            "config": { "minutes": 180 }
        },
        # Right Column - Device Grid
        {
            "id": "device-grid",
            "type": "device_grid",
            "title": "Device Status Summaries",
            "width": 8,
            "height": 350
        },
        # Left Column - Active Alerts
        {
            "id": "active-alerts",
            "type": "alerts",
            "title": "Active Alerts",
            "width": 4,
            "height": 400
        },
        # Right Column - Recent Activity
        {
            "id": "recent-activity",
            "type": "activity",
            "title": "Recent Activity",
            "width": 8,
            "height": 400
        }
    ]

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if Main Status exists (ID 1)
    cursor.execute("SELECT id FROM dashboards WHERE id = 1")
    exists = cursor.fetchone()

    if exists:
        print("Main Status dashboard (ID 1) already exists. Updating layout...")
        cursor.execute(
            "UPDATE dashboards SET layout_config = ? WHERE id = 1",
            (json.dumps(layout_config),)
        )
    else:
        print("Creating Main Status dashboard (ID 1)...")
        cursor.execute(
            "INSERT INTO dashboards (id, name, description, layout_config, is_public) VALUES (?, ?, ?, ?, ?)",
            (1, "Main Status", "Primary system overview dashboard", json.dumps(layout_config), 1)
        )

    conn.commit()
    conn.close()
    print("Main Status dashboard initialized successfully.")

if __name__ == "__main__":
    initialize_main_dashboard()
