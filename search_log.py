import os

log_file = 'server.log'
search_ip = '172.22.20.203'
chunk_size = 1024 * 1024 * 5 # 5 MB

try:
    file_size = os.path.getsize(log_file)
    with open(log_file, 'rb') as f:
        # Read the last 5MB
        start_pos = max(0, file_size - chunk_size)
        f.seek(start_pos)
        content = f.read().decode('utf-8', errors='replace')
        
    lines = content.split('\n')
    matching_lines = [line for line in lines if search_ip in line]
    
    print(f"Found {len(matching_lines)} lines mentioning {search_ip} in the last 5MB of server.log")
    for line in matching_lines[-20:]: # show last 20
        print(line)
        
except Exception as e:
    print(f"Error: {e}")
