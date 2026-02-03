"""
Network Monitoring Service
Handles ping, HTTP, and SNMP monitoring with status updates
"""
from pythonping import ping
from datetime import datetime, timezone
from config import Config
import time
import requests
from urllib.parse import urlparse
import asyncio
import ssl
import socket

# SNMP imports
try:
    from pysnmp.hlapi.v3arch.asyncio import *
    SNMP_AVAILABLE = True
except ImportError:
    SNMP_AVAILABLE = False
    print("Warning: pysnmp not installed. SNMP monitoring disabled.")

class NetworkMonitor:
    def __init__(self, database):
        self.db = database
        self.monitoring_active = False
        self.alerter = None  # Will be set by app.py
    
    def ping_device(self, ip_address):
        """
        Ping a device and return status and response time
        Returns: dict with 'status' ('up' or 'down') and 'response_time' (ms)
        """
        try:
            # Perform ping
            response = ping(ip_address, count=Config.PING_COUNT, 
                          timeout=Config.PING_TIMEOUT, verbose=False)
            
            # Check if any pings were successful
            if response.success():
                # Calculate average response time in milliseconds
                avg_time = response.rtt_avg_ms
                # Check if response time is slow
                status = 'slow' if avg_time > Config.SLOW_RESPONSE_THRESHOLD else 'up'
                return {
                    'status': status,
                    'response_time': round(avg_time, 2)
                }
            else:
                return {
                    'status': 'down',
                    'response_time': None
                }
        except Exception as e:
            print(f"Error pinging {ip_address}: {e}")
            return {
                'status': 'down',
                'response_time': None
            }
    
    def check_tcp_port(self, ip_address, port=80):
        """
        Check if a TCP port is open on a device
        Returns: dict with 'status' ('up' or 'down') and 'response_time' (ms)
        """
        import socket
        
        try:
            # Create socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(Config.TCP_TIMEOUT)
            
            # Measure connection time
            start_time = time.time()
            result = sock.connect_ex((ip_address, int(port)))
            response_time = (time.time() - start_time) * 1000  # Convert to ms
            
            sock.close()
            
            if result == 0:
                # Port is open
                status = 'slow' if response_time > Config.SLOW_RESPONSE_THRESHOLD else 'up'
                return {
                    'status': status,
                    'response_time': round(response_time, 2)
                }
            else:
                # Port is closed or filtered
                return {
                    'status': 'down',
                    'response_time': None
                }
        except socket.timeout:
            print(f"TCP timeout connecting to {ip_address}:{port}")
            return {
                'status': 'down',
                'response_time': None
            }
            return {
                'status': 'down',
                'response_time': None
            }
    
    def check_dns(self, dns_server, query_domain='google.com'):
        """
        Check if a DNS server responds to queries using dnspython
        Returns: dict with 'status' ('up' or 'down'), 'response_time' (ms), and 'resolved_ip'
        """
        import dns.resolver
        import dns.exception
        
        try:
            # Create custom resolver pointing to specific DNS server
            resolver = dns.resolver.Resolver(configure=False)
            resolver.nameservers = [dns_server]
            resolver.timeout = Config.DNS_TIMEOUT      # timeout per query
            resolver.lifetime = Config.DNS_LIFETIME    # total time for all retries
            
            # Measure query time
            start_time = time.time()
            answers = resolver.resolve(query_domain, 'A')
            response_time = (time.time() - start_time) * 1000  # Convert to ms
            
            # Get first resolved IP
            resolved_ip = str(answers[0]) if answers else None
            
            # Determine status based on response time
            status = 'slow' if response_time > Config.SLOW_RESPONSE_THRESHOLD else 'up'
            print(f"DNS OK for {dns_server}: query={query_domain}, resolved={resolved_ip}, response={round(response_time, 2)}ms")
            
            return {
                'status': status,
                'response_time': round(response_time, 2),
                'resolved_ip': resolved_ip
            }
            
        except dns.resolver.Timeout:
            print(f"DNS timeout querying {dns_server}")
            return {
                'status': 'down',
                'response_time': None,
                'resolved_ip': None
            }
        except dns.resolver.NXDOMAIN:
            print(f"DNS NXDOMAIN for {query_domain} on {dns_server}")
            return {
                'status': 'down',
                'response_time': None,
                'resolved_ip': None
            }
        except dns.resolver.NoAnswer:
            print(f"DNS NoAnswer for {query_domain} on {dns_server}")
            return {
                'status': 'down',
                'response_time': None,
                'resolved_ip': None
            }
        except dns.resolver.NoNameservers:
            print(f"DNS NoNameservers - {dns_server} unreachable")
            return {
                'status': 'down',
                'response_time': None,
                'resolved_ip': None
            }
        except Exception as e:
            print(f"Error checking DNS {dns_server}: {e}")
            return {
                'status': 'down',
                'response_time': None,
                'resolved_ip': None
            }
    
    def check_ssl_certificate(self, hostname, port=443):
        """
        Check SSL certificate expiry for a hostname
        Returns: dict with 'valid', 'days_until_expiry', 'expiry_date', 'issuer', 'subject'
        """
        original_hostname = hostname
        try:
            # Remove protocol prefix if present
            if hostname.startswith('https://'):
                hostname = hostname[8:]
            elif hostname.startswith('http://'):
                hostname = hostname[7:]
            
            # Remove path and port from hostname
            hostname = hostname.split('/')[0]
            if ':' in hostname:
                hostname, port = hostname.split(':')
                port = int(port)
            
            cert = None
            verified = True
            
            # First try with verification
            try:
                context = ssl.create_default_context()
                with socket.create_connection((hostname, port), timeout=Config.HTTP_TIMEOUT) as sock:
                    with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                        cert = ssock.getpeercert()
            except ssl.SSLCertVerificationError:
                # If verification fails, try without verification to get cert info
                verified = False
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                with socket.create_connection((hostname, port), timeout=Config.HTTP_TIMEOUT) as sock:
                    with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                        # Get certificate in DER format and decode
                        cert_der = ssock.getpeercert(binary_form=True)
                        if cert_der:
                            # Decode certificate using cryptography library if available
                            try:
                                from cryptography import x509
                                from cryptography.hazmat.backends import default_backend
                                cert_obj = x509.load_der_x509_certificate(cert_der, default_backend())
                                
                                # Extract info
                                expiry_date = cert_obj.not_valid_after_utc
                                now = datetime.now(timezone.utc)
                                days_until_expiry = (expiry_date - now).days
                                
                                # Get issuer
                                issuer = ''
                                for attr in cert_obj.issuer:
                                    if attr.oid.dotted_string == '2.5.4.10':  # Organization
                                        issuer = attr.value
                                        break
                                
                                return {
                                    'valid': verified,
                                    'days_until_expiry': days_until_expiry,
                                    'expiry_date': expiry_date.isoformat(),
                                    'issuer': issuer,
                                    'subject': hostname
                                }
                            except ImportError:
                                # cryptography not available, return partial info
                                return {
                                    'valid': False,
                                    'days_until_expiry': None,
                                    'expiry_date': None,
                                    'issuer': 'Certificate exists (verification failed)',
                                    'subject': hostname,
                                    'error': 'cryptography library not installed'
                                }
            
            if not cert:
                return {
                    'valid': False,
                    'days_until_expiry': None,
                    'expiry_date': None,
                    'issuer': None,
                    'subject': None,
                    'error': 'No certificate found'
                }
            
            # Parse expiry date
            expiry_str = cert.get('notAfter', '')
            if expiry_str:
                # Parse SSL date format: 'Mar 15 12:00:00 2025 GMT'
                expiry_date = datetime.strptime(expiry_str, '%b %d %H:%M:%S %Y %Z')
                expiry_date = expiry_date.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                days_until_expiry = (expiry_date - now).days
            else:
                expiry_date = None
                days_until_expiry = None
            
            # Get issuer
            issuer_parts = cert.get('issuer', ())
            issuer = ''
            for item in issuer_parts:
                for key, value in item:
                    if key == 'organizationName':
                        issuer = value
                        break
            
            # Get subject (Common Name)
            subject_parts = cert.get('subject', ())
            subject = ''
            for item in subject_parts:
                for key, value in item:
                    if key == 'commonName':
                        subject = value
                        break
            
            return {
                'valid': verified,
                'days_until_expiry': days_until_expiry,
                'expiry_date': expiry_date.isoformat() if expiry_date else None,
                'issuer': issuer,
                'subject': subject
            }
            
        except Exception as e:
            print(f"Error checking SSL certificate for {hostname}: {e}")
            return {
                'valid': False,
                'days_until_expiry': None,
                'expiry_date': None,
                'issuer': None,
                'subject': None,
                'error': str(e)
            }
    
    def check_website(self, url, expected_status_code=200):
        """
        Check a website via HTTP/HTTPS and return status and response time
        Returns: dict with 'status', 'response_time' (ms), 'http_status_code', and SSL info if HTTPS
        """
        try:
            # Ensure URL has a scheme
            original_url = url
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            is_https = url.startswith('https://')
            
            # Perform HTTP GET request
            start_time = time.time()
            response = requests.get(
                url,
                timeout=Config.HTTP_TIMEOUT,
                verify=Config.VERIFY_SSL,
                headers={'User-Agent': Config.HTTP_USER_AGENT},
                allow_redirects=True
            )
            response_time = (time.time() - start_time) * 1000  # Convert to ms
            
            # Check if status code matches expected
            if response.status_code == expected_status_code:
                # Check if response time is slow
                status = 'slow' if response_time > Config.SLOW_RESPONSE_THRESHOLD else 'up'
            else:
                status = 'down'
            
            result = {
                'status': status,
                'response_time': round(response_time, 2),
                'http_status_code': response.status_code
            }
            
            # Check SSL certificate for HTTPS sites
            if is_https:
                ssl_info = self.check_ssl_certificate(url)
                result['ssl_valid'] = ssl_info.get('valid', False)
                result['ssl_days_left'] = ssl_info.get('days_until_expiry')
                result['ssl_expiry_date'] = ssl_info.get('expiry_date')
                result['ssl_issuer'] = ssl_info.get('issuer')
                
                # Warn if certificate expires soon
                if ssl_info.get('days_until_expiry') is not None:
                    if ssl_info['days_until_expiry'] <= 0:
                        result['ssl_status'] = 'expired'
                    elif ssl_info['days_until_expiry'] <= Config.SSL_WARNING_DAYS:
                        result['ssl_status'] = 'warning'
                    else:
                        result['ssl_status'] = 'ok'
                else:
                    result['ssl_status'] = 'unknown'
            
            return result
            
        except requests.exceptions.SSLError as e:
            print(f"SSL Error checking {url}: {e}")
            return {
                'status': 'down',
                'response_time': None,
                'http_status_code': None,
                'ssl_valid': False,
                'ssl_status': 'error',
                'ssl_error': str(e)
            }
        except requests.exceptions.Timeout:
            print(f"Timeout checking {url}")
            return {
                'status': 'down',
                'response_time': None,
                'http_status_code': None
            }
        except requests.exceptions.ConnectionError as e:
            print(f"Connection error checking {url}: {e}")
            return {
                'status': 'down',
                'response_time': None,
                'http_status_code': None
            }
        except Exception as e:
            print(f"Error checking {url}: {e}")
            return {
                'status': 'down',
                'response_time': None,
                'http_status_code': None
            }
    
    async def _check_snmp_async(self, ip_address, community='public', port=161, version='2c'):
        """
        Async SNMP check implementation
        """
        # Set SNMP version
        if version == '1':
            mp_model = 0
        else:  # v2c
            mp_model = 1
        
        start_time = time.time()
        
        # Query system info using async API
        snmp_engine = SnmpEngine()
        
        transport = await UdpTransportTarget.create(
            (ip_address, port), 
            timeout=Config.SNMP_TIMEOUT, 
            retries=1
        )
        
        # Query all system MIB objects
        errorIndication, errorStatus, errorIndex, varBinds = await get_cmd(
            snmp_engine,
            CommunityData(community, mpModel=mp_model),
            transport,
            ContextData(),
            ObjectType(ObjectIdentity('1.3.6.1.2.1.1.1.0')),  # sysDescr
            ObjectType(ObjectIdentity('1.3.6.1.2.1.1.3.0')),  # sysUptime
            ObjectType(ObjectIdentity('1.3.6.1.2.1.1.4.0')),  # sysContact
            ObjectType(ObjectIdentity('1.3.6.1.2.1.1.5.0')),  # sysName
            ObjectType(ObjectIdentity('1.3.6.1.2.1.1.6.0'))   # sysLocation
        )
        
        response_time = (time.time() - start_time) * 1000  # Convert to ms
        
        if errorIndication:
            raise Exception(f"SNMP Error: {errorIndication}")
        
        if errorStatus:
            raise Exception(f"SNMP Error: {errorStatus.prettyPrint()} at {errorIndex}")
        
        # Parse results
        result = {
            'uptime': None,
            'sysname': None,
            'sysdescr': None,
            'syslocation': None,
            'syscontact': None
        }
        
        for varBind in varBinds:
            oid = str(varBind[0])
            value = varBind[1]
            
            if '1.3.6.1.2.1.1.1.0' in oid:  # sysDescr
                result['sysdescr'] = str(value)[:255]  # Limit length
            elif '1.3.6.1.2.1.1.3.0' in oid:  # sysUptime
                try:
                    ticks = int(value)
                    seconds = ticks / 100
                    days = int(seconds // 86400)
                    hours = int((seconds % 86400) // 3600)
                    minutes = int((seconds % 3600) // 60)
                    result['uptime'] = f"{days}d {hours}h {minutes}m"
                except:
                    result['uptime'] = str(value)
            elif '1.3.6.1.2.1.1.4.0' in oid:  # sysContact
                result['syscontact'] = str(value)
            elif '1.3.6.1.2.1.1.5.0' in oid:  # sysName
                result['sysname'] = str(value)
            elif '1.3.6.1.2.1.1.6.0' in oid:  # sysLocation
                result['syslocation'] = str(value)
        
        return response_time, result

    def check_snmp(self, ip_address, community='public', port=161, version='2c'):
        """
        Check a device via SNMP and return status, response time, and system info
        Uses asyncio.run() to run the async SNMP check
        Returns: dict with 'status', 'response_time' (ms), and all system info
        """
        if not SNMP_AVAILABLE:
            print(f"SNMP not available for {ip_address}")
            return {
                'status': 'down',
                'response_time': None,
                'uptime': None,
                'sysname': None,
                'sysdescr': None,
                'syslocation': None,
                'syscontact': None
            }
        
        try:
            # Run async SNMP check in new event loop
            response_time, snmp_data = asyncio.run(
                self._check_snmp_async(ip_address, community, port, version)
            )
            
            # Determine status based on response time
            status = 'slow' if response_time > Config.SLOW_RESPONSE_THRESHOLD else 'up'
            
            print(f"SNMP OK for {ip_address}: sysname={snmp_data['sysname']}, uptime={snmp_data['uptime']}, response={round(response_time, 2)}ms")
            
            return {
                'status': status,
                'response_time': round(response_time, 2),
                'uptime': snmp_data['uptime'],
                'sysname': snmp_data['sysname'],
                'sysdescr': snmp_data['sysdescr'],
                'syslocation': snmp_data['syslocation'],
                'syscontact': snmp_data['syscontact']
            }
            
        except Exception as e:
            print(f"SNMP Error checking {ip_address}: {e}")
            return {
                'status': 'down',
                'response_time': None,
                'uptime': None,
                'sysname': None,
                'sysdescr': None,
                'syslocation': None,
                'syscontact': None
            }
    
    def check_device(self, device):
        """Check a single device and update database"""
        monitor_type = device.get('monitor_type', 'ping')
        previous_status = device.get('status', 'unknown')
        
        # Route to appropriate monitoring method
        if monitor_type == 'http':
            expected_code = device.get('expected_status_code', 200)
            result = self.check_website(device['ip_address'], expected_code)
        elif monitor_type == 'snmp':
            community = device.get('snmp_community', Config.SNMP_DEFAULT_COMMUNITY)
            port = device.get('snmp_port', Config.SNMP_DEFAULT_PORT)
            version = device.get('snmp_version', Config.SNMP_DEFAULT_VERSION)
            result = self.check_snmp(device['ip_address'], community, port, version)
        elif monitor_type == 'tcp':
            tcp_port = device.get('tcp_port', 80)
            result = self.check_tcp_port(device['ip_address'], tcp_port)
        elif monitor_type == 'dns':
            query_domain = device.get('dns_query_domain', 'google.com')
            result = self.check_dns(device['ip_address'], query_domain)
        else:
            result = self.ping_device(device['ip_address'])
        
        # ==== Consecutive Failure Threshold Logic ====
        raw_status = result['status']
        final_status = raw_status
        
        # Get current failure count BEFORE updating
        previous_failure_count = self.db.get_failure_count(device['id'])
        
        if raw_status == 'down':
            # Increment failure count
            failure_count = self.db.increment_failure_count(device['id'])
            
            # Only mark as down if failure count >= threshold
            if failure_count >= Config.FAILURE_THRESHOLD:
                final_status = 'down'
                print(f"[THRESHOLD] {device['name']}: {failure_count} consecutive failures - marked as DOWN")
            else:
                # Keep previous status (don't change to down yet)
                final_status = previous_status if previous_status in ('up', 'slow') else 'unknown'
                print(f"[THRESHOLD] {device['name']}: {failure_count}/{Config.FAILURE_THRESHOLD} failures - keeping status as {final_status}")
        else:
            # Success! Reset failure count
            self.db.reset_failure_count(device['id'])
            final_status = raw_status
            
            # Log recovery if there were previous failures
            if previous_failure_count > 0:
                print(f"[THRESHOLD] {device['name']}: recovered after {previous_failure_count} failures")
        
        # Update the result with final status
        result['status'] = final_status
        
        # Update database
        self.db.update_device_status(
            device['id'],
            final_status,
            result['response_time'],
            result.get('http_status_code'),
            result.get('uptime'),
            result.get('sysname'),
            result.get('sysdescr'),
            result.get('syslocation'),
            result.get('syscontact'),
            result.get('ssl_expiry_date'),
            result.get('ssl_days_left'),
            result.get('ssl_issuer'),
            result.get('ssl_status')
        )
        
        # ==== Alert Triggers ====
        if self.alerter:
            # Alert on device DOWN (status changed to down) - only after threshold reached
            if final_status == 'down' and previous_status != 'down':
                self.alerter.trigger_alert(
                    device, 'down', 
                    f"Device is DOWN. Previous status: {previous_status}"
                )
            
            # Alert on device RECOVERY 
            # Trigger when: 1) status was down and now up, OR 2) had failures (threshold reached) and now success
            should_alert_recovery = (
                (previous_status == 'down' and final_status in ('up', 'slow')) or
                (previous_failure_count >= Config.FAILURE_THRESHOLD and final_status in ('up', 'slow'))
            )
            if should_alert_recovery:
                self.alerter.trigger_alert(
                    device, 'recovery',
                    f"Device has RECOVERED. Current status: {final_status}"
                )
            
            # Alert on SSL certificate expiring soon
            ssl_days = result.get('ssl_days_left')
            if ssl_days is not None and ssl_days <= Config.SSL_EXPIRY_ALERT_DAYS:
                self.alerter.trigger_alert(
                    device, 'ssl_expiry',
                    f"SSL Certificate expires in {ssl_days} days!"
                )
        
        return {
            'id': device['id'],
            'name': device['name'],
            'ip_address': device['ip_address'],
            'device_type': device.get('device_type', 'other'),
            'monitor_type': monitor_type,
            'status': final_status,
            'response_time': result['response_time'],
            'http_status_code': result.get('http_status_code'),
            'snmp_uptime': result.get('uptime'),
            'snmp_sysname': result.get('sysname'),
            'snmp_sysdescr': result.get('sysdescr'),
            'snmp_syslocation': result.get('syslocation'),
            'snmp_syscontact': result.get('syscontact'),
            'ssl_expiry_date': result.get('ssl_expiry_date'),
            'ssl_days_left': result.get('ssl_days_left'),
            'ssl_issuer': result.get('ssl_issuer'),
            'ssl_status': result.get('ssl_status'),
            'last_check': datetime.now().isoformat()
        }
    
    def check_all_devices(self):
        """Check all devices and return their status"""
        devices = self.db.get_all_devices()
        results = []
        
        for device in devices:
            result = self.check_device(device)
            results.append(result)
        
        return results
    
    def get_statistics(self):
        """Get overall network statistics"""
        devices = self.db.get_all_devices()
        
        total = len(devices)
        up = sum(1 for d in devices if d['status'] == 'up')
        slow = sum(1 for d in devices if d['status'] == 'slow')
        down = sum(1 for d in devices if d['status'] == 'down')
        unknown = sum(1 for d in devices if d['status'] == 'unknown')
        
        # Calculate average response time for devices that are up
        response_times = [d['response_time'] for d in devices 
                         if d['response_time'] is not None]
        avg_response = round(sum(response_times) / len(response_times), 2) if response_times else 0
        
        return {
            'total_devices': total,
            'devices_up': up,
            'devices_slow': slow,
            'devices_down': down,
            'devices_unknown': unknown,
            'uptime_percentage': round((up / total * 100), 2) if total > 0 else 0,
            'average_response_time': avg_response
        }

    async def _get_snmp_interfaces_async(self, ip_address, community='public', port=161, version='2c'):
        """
        Get interface table via SNMP - query first 28 interfaces
        """
        # Set SNMP version
        if version == '1':
            mp_model = 0
        else:  # v2c
            mp_model = 1
        
        snmp_engine = SnmpEngine()
        
        transport = await UdpTransportTarget.create(
            (ip_address, port), 
            timeout=5,
            retries=1
        )
        
        interfaces = {}
        
        # Query 28 interfaces x 2 OIDs = 56 OIDs (within reasonable limit)
        objects = []
        for i in range(1, 29):  # Query interfaces 1-28
            objects.append(ObjectType(ObjectIdentity(f'1.3.6.1.2.1.2.2.1.2.{i}')))   # ifDescr
            objects.append(ObjectType(ObjectIdentity(f'1.3.6.1.2.1.2.2.1.8.{i}')))   # ifOperStatus
        
        errorIndication, errorStatus, errorIndex, varBinds = await get_cmd(
            snmp_engine,
            CommunityData(community, mpModel=mp_model),
            transport,
            ContextData(),
            *objects
        )
        
        if errorIndication:
            print(f"SNMP Interface Error: {errorIndication}")
            return []
        
        # Parse results
        for varBind in varBinds:
            oid = str(varBind[0])
            value = varBind[1]
            
            # Skip noSuchInstance
            if 'noSuch' in str(type(value).__name__):
                continue
            
            try:
                parts = oid.split('.')
                if_index = int(parts[-1])
                oid_type = parts[-2]
            except:
                continue
            
            if if_index not in interfaces:
                interfaces[if_index] = {
                    'index': if_index,
                    'name': '',
                    'speed': 'N/A',
                    'oper_status': 'unknown',
                    'bytes_in': 0,
                    'bytes_out': 0
                }
            
            if oid_type == '2':  # ifDescr
                interfaces[if_index]['name'] = str(value)
            elif oid_type == '8':  # ifOperStatus
                interfaces[if_index]['oper_status'] = 'up' if int(value) == 1 else 'down'
        
        # Convert to list
        result = []
        for if_index, if_data in sorted(interfaces.items()):
            if if_data.get('name'):
                result.append(if_data)
        
        return result

    def get_snmp_interfaces(self, ip_address, community='public', port=161, version='2c'):
        """
        Get interface table - synchronous wrapper
        """
        if not SNMP_AVAILABLE:
            return []
        
        try:
            result = asyncio.run(
                self._get_snmp_interfaces_async(ip_address, community, port, version)
            )
            return result
        except Exception as e:
            print(f"SNMP Interface Error for {ip_address}: {e}")
            return []
