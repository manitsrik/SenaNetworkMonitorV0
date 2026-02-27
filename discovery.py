"""
Auto Device Discovery Module
Scans network subnets to find active hosts using ping sweep,
DNS reverse lookup, and common port detection.
"""
import subprocess
import socket
import ipaddress
import concurrent.futures
import platform
from datetime import datetime


class DeviceDiscovery:
    """Network device auto-discovery scanner"""
    
    # Common ports and their typical device/service types
    COMMON_PORTS = {
        22: ('ssh', 'server'),
        23: ('telnet', 'network'),
        53: ('dns', 'server'),
        80: ('http', 'server'),
        443: ('https', 'server'),
        161: ('snmp', 'network'),
        3306: ('mysql', 'server'),
        5432: ('postgresql', 'server'),
        3389: ('rdp', 'server'),
        8080: ('http-alt', 'server'),
        8443: ('https-alt', 'server'),
        21: ('ftp', 'server'),
        25: ('smtp', 'server'),
        110: ('pop3', 'server'),
        143: ('imap', 'server'),
        445: ('smb', 'server'),
        514: ('syslog', 'network'),
        179: ('bgp', 'network'),
    }
    
    def __init__(self, timeout=1, max_workers=50):
        self.timeout = timeout
        self.max_workers = max_workers
        self._is_scanning = False
        self._scan_progress = 0
        self._scan_total = 0
        self._scan_results = []
    
    @property
    def is_scanning(self):
        return self._is_scanning
    
    @property
    def progress(self):
        if self._scan_total == 0:
            return 0
        return int(self._scan_progress / self._scan_total * 100)
    
    def ping_host(self, ip):
        """Ping a single host, return True if alive"""
        try:
            param = '-n' if platform.system().lower() == 'windows' else '-c'
            timeout_param = '-w' if platform.system().lower() == 'windows' else '-W'
            timeout_val = str(self.timeout * 1000) if platform.system().lower() == 'windows' else str(self.timeout)
            
            result = subprocess.run(
                ['ping', param, '1', timeout_param, timeout_val, str(ip)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=self.timeout + 2
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, Exception):
            return False
    
    def resolve_hostname(self, ip):
        """Reverse DNS lookup for an IP"""
        try:
            hostname, _, _ = socket.gethostbyaddr(str(ip))
            return hostname
        except (socket.herror, socket.gaierror, OSError):
            return None
    
    def scan_ports(self, ip, ports=None):
        """Scan common ports on a host"""
        if ports is None:
            ports = list(self.COMMON_PORTS.keys())
        
        open_ports = []
        for port in ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.5)
                result = sock.connect_ex((str(ip), port))
                if result == 0:
                    port_info = self.COMMON_PORTS.get(port, ('unknown', 'unknown'))
                    open_ports.append({
                        'port': port,
                        'service': port_info[0],
                        'device_type_hint': port_info[1]
                    })
                sock.close()
            except (socket.timeout, OSError):
                pass
        
        return open_ports
    
    def guess_device_type(self, open_ports):
        """Guess device type based on open ports"""
        if not open_ports:
            return 'unknown'
        
        port_numbers = {p['port'] for p in open_ports}
        
        # Network equipment indicators
        if 161 in port_numbers and 23 in port_numbers:
            return 'router'
        if 161 in port_numbers:
            return 'switch'
        if 179 in port_numbers:
            return 'router'
        
        # Printer
        if 9100 in port_numbers or 515 in port_numbers:
            return 'printer'
        
        # Web server
        if 80 in port_numbers or 443 in port_numbers:
            if 3306 in port_numbers or 5432 in port_numbers:
                return 'server'
            return 'server'
        
        # Database server
        if 3306 in port_numbers or 5432 in port_numbers:
            return 'server'
        
        # Windows desktop/server
        if 3389 in port_numbers:
            return 'server'
        
        # SSH server
        if 22 in port_numbers:
            return 'server'
        
        return 'unknown'
    
    def guess_monitor_type(self, open_ports):
        """Suggest the best monitor type based on open ports"""
        port_numbers = {p['port'] for p in open_ports}
        
        if 161 in port_numbers:
            return 'snmp'
        if 443 in port_numbers:
            return 'http'
        if 80 in port_numbers:
            return 'http'
        return 'ping'
    
    def _scan_single_host(self, ip):
        """Scan a single IP address"""
        ip_str = str(ip)
        
        # Step 1: Ping
        is_alive = self.ping_host(ip_str)
        self._scan_progress += 1
        
        if not is_alive:
            return None
        
        # Step 2: Reverse DNS
        hostname = self.resolve_hostname(ip_str)
        
        # Step 3: Port scan
        open_ports = self.scan_ports(ip_str)
        
        # Step 4: Guess device type and monitor type
        device_type = self.guess_device_type(open_ports)
        monitor_type = self.guess_monitor_type(open_ports)
        
        return {
            'ip_address': ip_str,
            'hostname': hostname,
            'name': hostname or ip_str,
            'device_type': device_type,
            'monitor_type': monitor_type,
            'open_ports': open_ports,
            'discovered_at': datetime.now().isoformat()
        }
    
    def scan_subnet(self, subnet_str, skip_ips=None):
        """
        Scan an entire subnet for active hosts.
        
        Args:
            subnet_str: CIDR notation subnet (e.g., "192.168.1.0/24")
            skip_ips: Set of IPs to skip (already monitored)
        
        Returns:
            List of discovered device dicts
        """
        if self._is_scanning:
            return {'error': 'A scan is already running'}
        
        try:
            network = ipaddress.ip_network(subnet_str, strict=False)
        except ValueError as e:
            return {'error': f'Invalid subnet: {e}'}
        
        # Get list of IPs to scan (skip network and broadcast)
        hosts = list(network.hosts())
        
        # Filter out already-monitored IPs
        skip_set = set(skip_ips or [])
        hosts_to_scan = [h for h in hosts if str(h) not in skip_set]
        
        self._is_scanning = True
        self._scan_progress = 0
        self._scan_total = len(hosts_to_scan)
        self._scan_results = []
        
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {executor.submit(self._scan_single_host, ip): ip for ip in hosts_to_scan}
                
                for future in concurrent.futures.as_completed(futures):
                    try:
                        result = future.result(timeout=30)
                        if result:
                            self._scan_results.append(result)
                    except Exception:
                        pass
        finally:
            self._is_scanning = False
        
        # Sort by IP
        self._scan_results.sort(key=lambda d: ipaddress.ip_address(d['ip_address']))
        
        return {
            'success': True,
            'subnet': subnet_str,
            'total_scanned': len(hosts_to_scan),
            'total_skipped': len(skip_set),
            'discovered': len(self._scan_results),
            'devices': self._scan_results
        }
    
    def get_scan_status(self):
        """Get current scan status"""
        return {
            'is_scanning': self._is_scanning,
            'progress': self.progress,
            'scanned': self._scan_progress,
            'total': self._scan_total,
            'discovered_so_far': len(self._scan_results)
        }
