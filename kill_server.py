import subprocess
import os
import signal

out = subprocess.getoutput('wmic process where "name=\'python.exe\'" get commandline,processid')
my_pid = os.getpid()
for line in out.splitlines():
    if 'NW MonitorV0' in line and str(my_pid) not in line:
        parts = line.split()
        if parts:
            pid_str = parts[-1]
            if pid_str.isdigit():
                pid = int(pid_str)
                print(f"Killing old python process {pid}...")
                try:
                    os.kill(pid, signal.SIGTERM)
                except Exception as e:
                    print(e)
