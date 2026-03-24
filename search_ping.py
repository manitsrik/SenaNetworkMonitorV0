import os

log_file = 'server.log'
search_ip = '172.22.20.203'
chunk_size = 1024 * 1024 * 10 # 10 MB

try:
    file_size = os.path.getsize(log_file)
    with open(log_file, 'rb') as f:
        start_pos = max(0, file_size - chunk_size)
        f.seek(start_pos)
        content = f.read().decode('utf-8', errors='replace')
        
    lines = content.split('\n')
    matching_lines = [line for line in lines if search_ip in line]
    
    ping_down = [line for line in matching_lines if 'down' in line.lower() or 'timeout' in line.lower() or 'error checking' in line.lower()]
    print(f"Found {len(ping_down)} potential error/down lines for {search_ip} in the last 10MB of server.log")
    
    # Just show a sample
    for line in set(ping_down) if len(ping_down) > 0 else []:
        print(line)
        
except Exception as e:
    print(f"Error: {e}")
