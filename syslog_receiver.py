"""
Syslog Receiver for Network Monitor
Listens for Syslog messages on UDP port 514 and stores them in the database
"""
import socket
import threading
import re
from datetime import datetime

class SyslogReceiver:
    """Receives Syslog messages on UDP port 514"""
    
    def __init__(self, db, port=514):
        self.db = db
        self.port = port
        self.host = '0.0.0.0'
        self._thread = None
        self._running = False
        self._socket = None
        
        # Regex to match RFC 3164 Syslog header: <PRV>Timestamp Hostname Program[PID]: Message
        # The priority <PRV> is required, others are handled gracefully if missing.
        self._syslog_regex = re.compile(r'^<(\d+)>([^:]+):?\s*(.*)$')
    
    def start(self):
        """Start listening for Syslog messages in a background thread"""
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop the syslog receiver"""
        self._running = False
        if self._socket:
            try:
                self._socket.close()
            except:
                pass
        print("[SyslogReceiver] Stopped")
    
    def _run(self):
        """Main syslog receiver loop"""
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.bind((self.host, self.port))
            print(f"[SyslogReceiver] Started listening on UDP port {self.port}")
            
            while self._running:
                try:
                    data, addr = self._socket.recvfrom(4096)
                    if not data:
                        continue
                    
                    # Run processing in a separate lightweight method to free the listener quickly
                    self._process_message(data, addr[0])
                    
                except socket.error as e:
                    if self._running:
                        print(f"[SyslogReceiver] Socket error: {e}")
                except Exception as e:
                    if self._running:
                        print(f"[SyslogReceiver] Error receiving data: {e}")
                        
        except PermissionError:
            print(f"[SyslogReceiver] ERROR: Permission denied on port {self.port}. "
                  f"Run as administrator or use port > 1024.")
            self._running = False
        except OSError as e:
            if 'address already in use' in str(e).lower() or '10048' in str(e):
                print(f"[SyslogReceiver] ERROR: Port {self.port} already in use")
            else:
                print(f"[SyslogReceiver] ERROR: {e}")
            self._running = False
        except Exception as e:
            print(f"[SyslogReceiver] ERROR: {e}")
            self._running = False
            
    def _process_message(self, data, source_ip):
        """Process a single syslog message"""
        try:
            message_str = data.decode('utf-8', errors='replace').strip()
            
            # Parse Priority
            facility = 1  # User-level messages
            severity = 5  # Notice
            program = 'Unknown'
            message_body = message_str
            
            match = self._syslog_regex.match(message_str)
            if match:
                prv = int(match.group(1))
                facility = prv >> 3
                severity = prv & 7
                
                # The rest of the message might contain timestamp, hostname, program
                rest = match.group(2) + ":" + match.group(3) if match.group(3) else match.group(2)
                
                # very basic extraction trying to find the program name before the message
                # format is often 'Mmm dd hh:mm:ss hostname program[pid]: message'
                # or 'program: message'
                parts = rest.split(': ', 1)
                
                if len(parts) == 2:
                    potential_header = parts[0]
                    message_body = parts[1]
                    
                    # Try to extract program name (last word before colon)
                    header_parts = potential_header.split()
                    if header_parts:
                        prog_cand = header_parts[-1]
                        # Remove PID if present e.g. sshd[1234]
                        prog_cand = prog_cand.split('[')[0]
                        if prog_cand:
                            program = prog_cand
                else:
                    message_body = rest

            # Try to match source IP to a known device
            device_id = None
            device_name = None
            try:
                # Limit DB calls by doing a quick lookup or using a small connection
                # This could be cached in memory if performance becomes an issue
                devices = self.db.get_all_devices()
                for d in devices:
                    if d.get('ip_address') == source_ip:
                        device_id = d['id']
                        device_name = d['name']
                        break
            except:
                pass
            
            # Store in database
            self.db.add_syslog(
                source_ip=source_ip,
                facility=facility,
                severity=severity,
                program=program,
                message=message_body,
                device_id=device_id,
                device_name=device_name
            )
            
        except Exception as e:
            print(f"[SyslogReceiver] Error parsing logic for {source_ip}: {e}")
