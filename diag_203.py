import sqlite3

try:
    conn = sqlite3.connect('network_monitor.db')
    c = conn.cursor()
    print("--- Last 50 Status Checks ---")
    c.execute('''
        SELECT checked_at, status, response_time 
        FROM status_history 
        WHERE device_id=18 
        ORDER BY checked_at DESC 
        LIMIT 50
    ''')
    for row in c.fetchall():
        print(row)
        
    print("\n--- Last 20 Alerts ---")
    c.execute('''
        SELECT created_at, event_type, message, status, error_message 
        FROM alert_history 
        WHERE device_id=18 
        ORDER BY created_at DESC 
        LIMIT 20
    ''')
    for row in c.fetchall():
        print(row)
        
except Exception as e:
    print(f"Error: {e}")
finally:
    if 'conn' in locals():
        conn.close()
