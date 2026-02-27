import sqlite3
import datetime

def check():
    conn = sqlite3.connect('network_monitor.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print(f"Current System Time: {datetime.datetime.now().isoformat()}")
    
    print("\n--- Last 5 Status History Entries ---")
    cursor.execute("SELECT checked_at, status, response_time FROM status_history ORDER BY checked_at DESC LIMIT 5")
    for row in cursor.fetchall():
        print(f"Time: {row['checked_at']}, Status: {row['status']}, RT: {row['response_time']}")
        
    print("\n--- Last 5 Device Updates ---")
    cursor.execute("SELECT name, last_check, status FROM devices ORDER BY last_check DESC LIMIT 5")
    for row in cursor.fetchall():
        print(f"Name: {row['name']}, Checked: {row['last_check']}, Status: {row['status']}")
        
    conn.close()

if __name__ == "__main__":
    check()
