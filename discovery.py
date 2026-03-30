"""
Auto Device Discovery Module
Scans network subnets to find active hosts using TCP port probing,
DNS reverse lookup, and common port detection.

Uses a single flat eventlet GreenPool (no nesting) for fast,
non-blocking scanning that keeps Flask responsive.
"""
import socket
import ipaddress
import eventlet
from datetime import datetime
from pythonping import ping


class DeviceDiscovery:
    """Network device auto-discovery scanner"""
    
    # Common ports and their typical device/service types
    COMMON_PORTS = {
        22: ('ssh', 'server'),
        23: ('telnet', 'router'),
        53: ('dns', 'dns'),
        80: ('http', 'website'),
        443: ('https', 'website'),
        161: ('snmp', 'switch'),
        3306: ('mysql', 'server'),
        5432: ('postgresql', 'server'),
        3389: ('rdp', 'server'),
        8080: ('http-alt', 'website'),
        8443: ('https-alt', 'website'),
        21: ('ftp', 'server'),
        25: ('smtp', 'server'),
        110: ('pop3', 'server'),
        143: ('imap', 'server'),
        445: ('smb', 'server'),
        514: ('syslog', 'router'),
        179: ('bgp', 'router'),
        5060: ('sip', 'ippbx'),
        5061: ('sip-tls', 'ippbx'),
        554: ('rtsp', 'cctv'),
        8000: ('http-alt', 'server'),
        902: ('vmware', 'vmware'),
    }

    # Quick-check ports for liveness (only the most common 4)
    QUICK_PORTS = [80, 443, 22, 3389]
    
    def __init__(self, timeout=0.5, max_workers=100):
        self.timeout = timeout
        self.max_workers = max_workers
        self._is_scanning = False
        self._cancel_requested = False
        self._scan_progress = 0
        self._scan_total = 0
        self._scan_skipped = 0
        self._scan_results = []
    
    @property
    def is_scanning(self):
        return self._is_scanning
    
    @property
    def progress(self):
        if self._scan_total == 0:
            return 0
        return int(self._scan_progress / self._scan_total * 100)
    
    def cancel_scan(self):
        """Request scan cancellation. Workers will stop on next iteration."""
        self._cancel_requested = True
    
    def _tcp_connect(self, ip_str, port, timeout=None):
        """Try a single TCP connect. Returns True if port is open."""
        t = timeout or self.timeout
        try:
            with eventlet.Timeout(t, False):
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(t)
                result = sock.connect_ex((ip_str, port))
                sock.close()
                return result == 0
        except Exception:
            pass
        return False
    
    def check_host_alive(self, ip_str):
        """
        Fast host liveness check - ICMP ping followed by TCP connect to a few ports.
        Returns True as soon as any check succeeds.
        """
        if self._cancel_requested:
            return False
            
        # 1. Try ICMP Ping (Fastest if allowed)
        try:
            # count=1, timeout=0.2 for maximum speed in discovery
            response = ping(ip_str, count=1, timeout=0.2, verbose=False)
            if response.success():
                return True
        except Exception:
            # Fall back to TCP if ping fails (e.g. permission issues or blocked ICMP)
            pass

        # 2. Try TCP Probes
        for port in self.QUICK_PORTS:
            if self._cancel_requested:
                return False
            if self._tcp_connect(ip_str, port, timeout=0.2):
                return True
        return False
    
    def resolve_hostname(self, ip):
        """Reverse DNS lookup for an IP with timeout guard."""
        try:
            with eventlet.Timeout(1, False):
                hostname, _, _ = socket.gethostbyaddr(str(ip))
                return hostname
        except Exception:
            return None
        return None
    
    def scan_ports(self, ip, ports=None):
        """Scan common ports sequentially. No nested GreenPool."""
        if ports is None:
            ports = list(self.COMMON_PORTS.keys())
        
        open_ports = []
        for port in ports:
            if self._cancel_requested:
                break
            if self._tcp_connect(str(ip), port, timeout=0.5):
                port_info = self.COMMON_PORTS.get(port, ('unknown', 'unknown'))
                open_ports.append({
                    'port': port,
                    'service': port_info[0],
                    'device_type_hint': port_info[1]
                })
        
        return open_ports
    
    def guess_device_type(self, open_ports):
        """Guess device type based on open ports
        Uses types matching Devices page: router, switch, server, firewall,
        wireless, website, dns, vmware, ippbx, cctv, vpnrouter, other
        """
        if not open_ports:
            return 'other'
        
        port_numbers = {p['port'] for p in open_ports}
        
        if 902 in port_numbers:
            return 'vmware'
        if 5060 in port_numbers or 5061 in port_numbers:
            return 'ippbx'
        if 554 in port_numbers:
            return 'cctv'
        if 161 in port_numbers and 23 in port_numbers:
            return 'router'
        if 179 in port_numbers:
            return 'router'
        if 161 in port_numbers:
            return 'switch'
        if 53 in port_numbers:
            return 'dns'
        if 80 in port_numbers or 443 in port_numbers:
            if 3306 in port_numbers or 5432 in port_numbers:
                return 'server'
            return 'website'
        if 3306 in port_numbers or 5432 in port_numbers:
            return 'server'
        if 3389 in port_numbers:
            return 'server'
        if 22 in port_numbers:
            return 'server'
        
        return 'other'
    
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
        """Scan a single IP. Never raises - returns None on error or cancel."""
        if self._cancel_requested:
            return None
        ip_str = str(ip)
        try:
            is_alive = self.check_host_alive(ip_str)
            self._scan_progress += 1
            
            # Yield to event loop so Flask can serve requests
            eventlet.sleep(0)
            
            if not is_alive or self._cancel_requested:
                return None
            
            hostname = self.resolve_hostname(ip_str)
            open_ports = self.scan_ports(ip_str)
            
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
        except Exception:
            self._scan_progress += 1
            return None
    
    def scan_subnet(self, subnet_str, skip_ips=None):
        """
        Scan an entire subnet for active hosts.
        Uses a single flat GreenPool - no nesting.
        """
        if self._is_scanning:
            return {'error': 'A scan is already running'}
        
        try:
            network = ipaddress.ip_network(subnet_str, strict=False)
        except ValueError as e:
            return {'error': f'Invalid subnet: {e}'}
        
        hosts = list(network.hosts())
        skip_set = set(skip_ips or [])
        hosts_to_scan = [h for h in hosts if str(h) not in skip_set]
        
        self._is_scanning = True
        self._cancel_requested = False
        self._scan_progress = 0
        self._scan_total = len(hosts_to_scan)
        self._scan_skipped = len(skip_set)
        self._scan_results = []
        
        try:
            pool = eventlet.GreenPool(self.max_workers)
            for result in pool.imap(self._scan_single_host, hosts_to_scan):
                if result:
                    self._scan_results.append(result)
                if self._cancel_requested:
                    break
            
            self._scan_results.sort(
                key=lambda d: ipaddress.ip_address(d['ip_address']))
        except Exception:
            pass
        finally:
            self._is_scanning = False
            self._cancel_requested = False
        
        return {
            'success': True,
            'subnet': subnet_str,
            'total_scanned': self._scan_total,
            'total_skipped': self._scan_skipped,
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
            'skipped': self._scan_skipped,
            'discovered_so_far': len(self._scan_results)
        }
