"""
Network Monitoring Service
Handles ping, HTTP, and SNMP monitoring with status updates
"""
from pythonping import ping
import eventlet
from eventlet import tpool
from datetime import datetime, timezone
# from concurrent.futures import ThreadPoolExecutor, as_completed
from config import Config
import time
import requests
from urllib.parse import urlparse
import asyncio
import socket
import threading
import sys
import ssl

# Remote monitoring imports
try:
    import paramiko
    SSH_AVAILABLE = True
except ImportError:
    SSH_AVAILABLE = False

try:
    import winrm
    WINRM_AVAILABLE = True
except ImportError:
    WINRM_AVAILABLE = False

# SNMP imports
try:
    from pysnmp.hlapi.v3arch.asyncio import *
    SNMP_AVAILABLE = True
except ImportError:
    SNMP_AVAILABLE = False
    print("Warning: pysnmp not installed. SNMP monitoring disabled.")

# SNMP v3 protocol mappings
if SNMP_AVAILABLE:
    SNMP_AUTH_PROTOCOLS = {
        'MD5': usmHMACMD5AuthProtocol,
        'SHA': usmHMACSHAAuthProtocol,
    }
    SNMP_PRIV_PROTOCOLS = {
        'DES': usmDESPrivProtocol,
        'AES128': usmAesCfb128Protocol,
        'AES': usmAesCfb128Protocol,
    }
else:
    SNMP_AUTH_PROTOCOLS = {}
    SNMP_PRIV_PROTOCOLS = {}
class NetworkMonitor:
    def __init__(self, database):
        self.db = database
        self.monitoring_active = False
        self.alerter = None  # Will be set by app.py
        self.max_workers = Config.MONITOR_MAX_WORKERS
        
        # Dedicated Asyncio thread for SNMP (Stable Architecture)
        self._loop = None
        self._thread = None
        if SNMP_AVAILABLE:
            self._start_asyncio_thread()
    
    def _start_asyncio_thread(self):
        """Start a persistent background thread with an asyncio event loop"""
        self._loop = asyncio.new_event_loop()
        def _run_loop(loop):
            asyncio.set_event_loop(loop)
            if sys.platform == 'win32':
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            loop.run_forever()
        
        import sys
        self._thread = threading.Thread(target=_run_loop, args=(self._loop,), daemon=True)
        self._thread.start()
        print("[MONITOR] Dedicated Asyncio Worker Thread started (SNMP-ready)")
    
    def ping_device(self, ip_address):
        """
        Ping a device and return status and response time
        Returns: dict with 'status' ('up' or 'down') and 'response_time' (ms)
        """
        try:
            # Perform ping natively (patched sockets make it yield)
            response = ping(ip_address, count=Config.PING_COUNT, 
                            timeout=Config.PING_TIMEOUT, verbose=False)
            
            # Check if any pings were successful
            if response.success():
                # Calculate average response time in milliseconds
                avg_time = response.rtt_avg_ms
                # Check if response time is slow
                status = 'slow' if avg_time > Config.MONITOR_THRESHOLDS.get('ping', Config.DEFAULT_SLOW_THRESHOLD) else 'up'
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
            
            # Call natively - socket is patched by eventlet
            result = sock.connect_ex((ip_address, int(port)))
            
            response_time = (time.time() - start_time) * 1000  # Convert to ms
            
            sock.close()
            
            if result == 0:
                # Port is open
                status = 'slow' if response_time > Config.MONITOR_THRESHOLDS.get('tcp', Config.DEFAULT_SLOW_THRESHOLD) else 'up'
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
            status = 'slow' if response_time > Config.MONITOR_THRESHOLDS.get('dns', Config.DEFAULT_SLOW_THRESHOLD) else 'up'
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
            
            # Perform HTTP GET request natively (requests uses patched sockets)
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
                status = 'slow' if response_time > Config.MONITOR_THRESHOLDS.get('http', Config.DEFAULT_SLOW_THRESHOLD) else 'up'
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
    
    @staticmethod
    async def _check_snmp_async_standalone(ip_address, community='public', port=161, version='2c',
                                           snmp_v3_username=None, snmp_v3_auth_protocol='SHA',
                                           snmp_v3_auth_password=None, snmp_v3_priv_protocol='AES128',
                                           snmp_v3_priv_password=None):
        """
        Standalone async SNMP check for subprocess execution.
        Same logic as _check_snmp_async but without self dependency.
        """
        start_time = time.time()
        
        # Build auth data based on SNMP version
        if version == '3':
            auth_proto = SNMP_AUTH_PROTOCOLS.get(snmp_v3_auth_protocol, usmHMACSHAAuthProtocol)
            priv_proto = SNMP_PRIV_PROTOCOLS.get(snmp_v3_priv_protocol, usmAesCfb128Protocol)
            
            if snmp_v3_auth_password and snmp_v3_priv_password:
                auth_data = UsmUserData(
                    userName=snmp_v3_username or '',
                    authKey=snmp_v3_auth_password,
                    privKey=snmp_v3_priv_password,
                    authProtocol=auth_proto,
                    privProtocol=priv_proto
                )
            elif snmp_v3_auth_password:
                auth_data = UsmUserData(
                    userName=snmp_v3_username or '',
                    authKey=snmp_v3_auth_password,
                    authProtocol=auth_proto
                )
            else:
                auth_data = UsmUserData(userName=snmp_v3_username or '')
        else:
            mp_model = 0 if version == '1' else 1
            auth_data = CommunityData(community, mpModel=mp_model)
        
        snmp_engine = SnmpEngine()
        transport = await UdpTransportTarget.create(
            (ip_address, port),
            timeout=Config.SNMP_TIMEOUT,
            retries=1
        )
        
        errorIndication, errorStatus, errorIndex, varBinds = await get_cmd(
            snmp_engine,
            auth_data,
            transport,
            ContextData(),
            ObjectType(ObjectIdentity('1.3.6.1.2.1.1.1.0')),
            ObjectType(ObjectIdentity('1.3.6.1.2.1.1.3.0')),
            ObjectType(ObjectIdentity('1.3.6.1.2.1.1.4.0')),
            ObjectType(ObjectIdentity('1.3.6.1.2.1.1.5.0')),
            ObjectType(ObjectIdentity('1.3.6.1.2.1.1.6.0'))
        )
        
        response_time = (time.time() - start_time) * 1000
        
        if errorIndication:
            raise Exception(f"SNMP Error: {errorIndication}")
        if errorStatus:
            raise Exception(f"SNMP Error: {errorStatus.prettyPrint()} at {errorIndex}")
        
        result = {'uptime': None, 'sysname': None, 'sysdescr': None, 'syslocation': None, 'syscontact': None}
        
        for varBind in varBinds:
            oid = str(varBind[0])
            value = varBind[1]
            if '1.3.6.1.2.1.1.1.0' in oid:
                result['sysdescr'] = str(value)[:255]
            elif '1.3.6.1.2.1.1.3.0' in oid:
                try:
                    ticks = int(value)
                    seconds = ticks / 100
                    days = int(seconds // 86400)
                    hours = int((seconds % 86400) // 3600)
                    minutes = int((seconds % 3600) // 60)
                    result['uptime'] = f"{days}d {hours}h {minutes}m"
                except:
                    result['uptime'] = str(value)
            elif '1.3.6.1.2.1.1.4.0' in oid:
                result['syscontact'] = str(value)
            elif '1.3.6.1.2.1.1.5.0' in oid:
                result['sysname'] = str(value)
            elif '1.3.6.1.2.1.1.6.0' in oid:
                result['syslocation'] = str(value)
        
        return response_time, result

    async def _check_snmp_async(self, ip_address, community='public', port=161, version='2c',
                                 snmp_v3_username=None, snmp_v3_auth_protocol='SHA',
                                 snmp_v3_auth_password=None, snmp_v3_priv_protocol='AES128',
                                 snmp_v3_priv_password=None):
        """
        Async SNMP check implementation
        Supports SNMP v1, v2c (CommunityData) and v3 (UsmUserData)
        """
        start_time = time.time()
        
        # Build auth data based on SNMP version
        if version == '3':
            # SNMP v3 — User-based Security Model
            auth_proto = SNMP_AUTH_PROTOCOLS.get(snmp_v3_auth_protocol, usmHMACSHAAuthProtocol)
            priv_proto = SNMP_PRIV_PROTOCOLS.get(snmp_v3_priv_protocol, usmAesCfb128Protocol)
            
            if snmp_v3_auth_password and snmp_v3_priv_password:
                # authPriv — authentication + encryption
                auth_data = UsmUserData(
                    userName=snmp_v3_username or '',
                    authKey=snmp_v3_auth_password,
                    privKey=snmp_v3_priv_password,
                    authProtocol=auth_proto,
                    privProtocol=priv_proto
                )
            elif snmp_v3_auth_password:
                # authNoPriv — authentication only
                auth_data = UsmUserData(
                    userName=snmp_v3_username or '',
                    authKey=snmp_v3_auth_password,
                    authProtocol=auth_proto
                )
            else:
                # noAuthNoPriv
                auth_data = UsmUserData(userName=snmp_v3_username or '')
        else:
            # SNMP v1/v2c — Community-based
            mp_model = 0 if version == '1' else 1
            auth_data = CommunityData(community, mpModel=mp_model)
        
        # Query system info using async API
        snmp_engine = SnmpEngine()
        try:
            transport = await UdpTransportTarget.create(
                (ip_address, port), 
                timeout=Config.SNMP_TIMEOUT, 
                retries=1
            )
            
            # Query all system MIB objects
            errorIndication, errorStatus, errorIndex, varBinds = await get_cmd(
                snmp_engine,
                auth_data,
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
        finally:
            snmp_engine.close_dispatcher()

    def check_snmp(self, ip_address, community='public', port=161, version='2c',
                   snmp_v3_username=None, snmp_v3_auth_protocol='SHA',
                   snmp_v3_auth_password=None, snmp_v3_priv_protocol='AES128',
                   snmp_v3_priv_password=None):
        """
        Check a device via SNMP and return status, response time, and system info
        Uses asyncio.run() to run the async SNMP check
        Supports v1, v2c, and v3
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
            # Run coroutine in the dedicated asyncio thread
            coro = self._check_snmp_async(
                ip_address, community, port, version,
                snmp_v3_username, snmp_v3_auth_protocol,
                snmp_v3_auth_password, snmp_v3_priv_protocol,
                snmp_v3_priv_password
            )
            
            def _wait_for_result():
                future = asyncio.run_coroutine_threadsafe(coro, self._loop)
                return future.result(timeout=12)
            
            try:
                response_time, snmp_data = tpool.execute(_wait_for_result)
            except Exception as e:
                print(f"[ERROR] SNMP worker thread call failed for {ip_address}: {e}")
                return {
                    'status': 'down',
                    'response_time': None,
                    'uptime': None,
                    'sysname': None,
                    'sysdescr': None,
                    'syslocation': None,
                    'syscontact': None
                }
            
            # Determine status based on response time
            status = 'slow' if response_time > Config.MONITOR_THRESHOLDS.get('snmp', Config.DEFAULT_SLOW_THRESHOLD) else 'up'
            
            print(f"SNMP OK for {ip_address} (v{version}): sysname={snmp_data['sysname']}, uptime={snmp_data['uptime']}, response={round(response_time, 2)}ms")
            
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
            print(f"SNMP Error checking {ip_address} (v{version}): {e}")
            return {
                'status': 'down',
                'response_time': None,
                'uptime': None,
                'sysname': None,
                'sysdescr': None,
                'syslocation': None,
                'syscontact': None
            }

    def check_ssh(self, ip_address, username, password, port=22):
        """
        Check a Linux device via SSH and return status and system metrics
        Returns: dict with 'status', 'response_time', 'cpu', 'ram', 'disk'
        """
        if not SSH_AVAILABLE:
            return {'status': 'down', 'response_time': None, 'error': 'Paramiko not installed'}
        
        start_time = time.time()
        result = {'cpu': None, 'ram': None, 'disk': None, 'net_in': None, 'net_out': None}
        
        def _ssh_task():
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                client.connect(ip_address, port=int(port), username=username, password=password, timeout=10)
                
                # Get CPU Usage (1 min load average vs cores)
                _, stdout, _ = client.exec_command("grep -c ^processor /proc/cpuinfo && uptime")
                out = stdout.read().decode().strip().split('\n')
                cores = int(out[0]) if out[0].isdigit() else 1
                load = float(out[1].split('load average:')[1].split(',')[0].strip())
                result['cpu'] = min(100.0, round((load / cores) * 100, 2))
                
                # Get RAM Usage
                _, stdout, _ = client.exec_command("free -m | grep Mem")
                out = stdout.read().decode().strip().split()
                # Mem: total used free shared buff/cache available
                total_ram = int(out[1])
                used_ram = int(out[2])
                result['ram'] = round((used_ram / total_ram) * 100, 2)
                
                # Get Disk Usage (Root partition)
                _, stdout, _ = client.exec_command("df -h / | tail -1")
                out = stdout.read().decode().strip().split()
                # Filesystem Size Used Avail Use% Mounted
                result['disk'] = float(out[4].replace('%', ''))
                
                # Get Network Traffic (Total excluding loopback)
                _, stdout, _ = client.exec_command("cat /proc/net/dev | awk 'NR>2 && $1 != \"lo:\" {i+=$2; o+=$10} END {print i, o}'")
                out = stdout.read().decode().strip().split()
                if len(out) >= 2:
                    result['net_in'] = int(out[0])
                    result['net_out'] = int(out[1])
                
                client.close()
                return True
            except Exception as e:
                print(f"[SSH] Error connecting to {ip_address}: {e}")
                if client: client.close()
                return False

        try:
            success = tpool.execute(_ssh_task)
            response_time = (time.time() - start_time) * 1000
            
            if success:
                status = 'slow' if response_time > Config.MONITOR_THRESHOLDS.get('ssh', Config.DEFAULT_SLOW_THRESHOLD) else 'up'
                return {
                    'status': status,
                    'response_time': round(response_time, 2),
                    'cpu': result['cpu'],
                    'ram': result['ram'],
                    'disk': result['disk'],
                    'net_in': result['net_in'],
                    'net_out': result['net_out']
                }
            else:
                return {'status': 'down', 'response_time': None}
        except Exception as e:
            print(f"[SSH] Task execution failed for {ip_address}: {e}")
            return {'status': 'down', 'response_time': None}

    def check_winrm(self, ip_address, username, password):
        """
        Check a Windows device via WinRM and return status and system metrics
        Returns: dict with 'status', 'response_time', 'cpu', 'ram', 'disk'
        """
        if not WINRM_AVAILABLE:
            return {'status': 'down', 'response_time': None, 'error': 'pywinrm not installed'}
            
        start_time = time.time()
        result = {'cpu': None, 'ram': None, 'disk': None, 'net_in': None, 'net_out': None}
        
        def _winrm_task():
            try:
                # Use NTLM or basic auth over HTTP/HTTPS
                # For lab environments, we often use transport='ntlm' or 'basic'
                session = winrm.Session(ip_address, auth=(username, password), transport='ntlm', server_cert_validation='ignore')
                
                # Get CPU Usage
                ps_cpu = "Get-WmiObject Win32_Processor | Measure-Object -Property LoadPercentage -Average | Select-Object -ExpandProperty Average"
                r = session.run_ps(ps_cpu)
                if r.status_code == 0:
                    result['cpu'] = float(r.std_out.decode().strip())
                
                # Get RAM Usage
                ps_ram = "$m = Get-WmiObject Win32_OperatingSystem; [math]::Round((($m.TotalVisibleMemorySize - $m.FreePhysicalMemory) / $m.TotalVisibleMemorySize) * 100, 2)"
                r = session.run_ps(ps_ram)
                if r.status_code == 0:
                    result['ram'] = float(r.std_out.decode().strip())
                    
                # Get Disk Usage (C: Drive)
                ps_disk = "$d = Get-WmiObject Win32_LogicalDisk -Filter \"DeviceID='C:'\"; [math]::Round((($d.Size - $d.FreeSpace) / $d.Size) * 100, 2)"
                r = session.run_ps(ps_disk)
                if r.status_code == 0:
                    result['disk'] = float(r.std_out.decode().strip())
                
                # Get Network Traffic (Sum of all adapters) - Using more universal WMI class
                ps_net = "$n = Get-WmiObject Win32_PerfRawData_Tcpip_NetworkInterface; $in = ($n | Measure-Object -Property BytesReceivedPersec -Sum).Sum; $out = ($n | Measure-Object -Property BytesSentPersec -Sum).Sum; \"$in $out\""
                r = session.run_ps(ps_net)
                if r.status_code == 0:
                    parts = r.std_out.decode().strip().split()
                    if len(parts) >= 2:
                        result['net_in'] = int(parts[0])
                        result['net_out'] = int(parts[1])
                
                return True
            except Exception as e:
                print(f"[WinRM] Error connecting to {ip_address}: {e}")
                return False

        try:
            success = tpool.execute(_winrm_task)
            response_time = (time.time() - start_time) * 1000
            
            if success:
                status = 'slow' if response_time > Config.MONITOR_THRESHOLDS.get('winrm', Config.DEFAULT_SLOW_THRESHOLD) else 'up'
                return {
                    'status': status,
                    'response_time': round(response_time, 2),
                    'cpu': result['cpu'],
                    'ram': result['ram'],
                    'disk': result['disk'],
                    'net_in': result['net_in'],
                    'net_out': result['net_out']
                }
            else:
                return {'status': 'down', 'response_time': None}
        except Exception as e:
            print(f"[WinRM] Task execution failed for {ip_address}: {e}")
            return {'status': 'down', 'response_time': None}
    
    def check_device(self, device):
        """
        Check a single device using its configured monitor type.
        Returns a dictionary with the check results.
        """
        # Safety Guard: Do not check disabled devices
        if not device.get('is_enabled'):
            # Ensure status is 'disabled' in the database
            self.db.update_device_status(device['id'], 'disabled')
            return {
                'id': device['id'],
                'name': device['name'],
                'ip_address': device['ip_address'],
                'status': 'disabled',
                'last_check': datetime.now().isoformat(),
                'response_time': None
            }
            
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
            result = self.check_snmp(
                device['ip_address'], community, port, version,
                snmp_v3_username=device.get('snmp_v3_username'),
                snmp_v3_auth_protocol=device.get('snmp_v3_auth_protocol', 'SHA'),
                snmp_v3_auth_password=device.get('snmp_v3_auth_password'),
                snmp_v3_priv_protocol=device.get('snmp_v3_priv_protocol', 'AES128'),
                snmp_v3_priv_password=device.get('snmp_v3_priv_password')
            )
        elif monitor_type == 'ssh':
            result = self.check_ssh(
                device['ip_address'], 
                device.get('ssh_username'), 
                device.get('ssh_password'),
                device.get('ssh_port', 22)
            )
        elif monitor_type == 'winrm' or monitor_type == 'wmi':
            result = self.check_winrm(
                device['ip_address'], 
                device.get('wmi_username'), 
                device.get('wmi_password')
            )
        elif monitor_type == 'tcp':
            tcp_port = device.get('tcp_port', 80)
            result = self.check_tcp_port(device['ip_address'], tcp_port)
        elif monitor_type == 'dns':
            query_domain = device.get('dns_query_domain', 'google.com')
            result = self.check_dns(device['ip_address'], query_domain)
        else:
            result = self.ping_device(device['ip_address'])
            
        # Post-check logic (Specific handling for metrics and extra info)
        if result.get('status') != 'down':
            # 1. Custom OIDs (SNMP only)
            if monitor_type == 'snmp':
                try:
                    custom_oids = self.db.get_custom_oids(device['id'])
                    if custom_oids:
                        community = device.get('snmp_community', Config.SNMP_DEFAULT_COMMUNITY)
                        port = device.get('snmp_port', Config.SNMP_DEFAULT_PORT)
                        version = device.get('snmp_version', Config.SNMP_DEFAULT_VERSION)
                        oid_results = self.query_custom_oids(
                            device['ip_address'], community, port, version,
                            snmp_v3_username=device.get('snmp_v3_username'),
                            snmp_v3_auth_protocol=device.get('snmp_v3_auth_protocol', 'SHA'),
                            snmp_v3_auth_password=device.get('snmp_v3_auth_password'),
                            snmp_v3_priv_protocol=device.get('snmp_v3_priv_protocol', 'AES128'),
                            snmp_v3_priv_password=device.get('snmp_v3_priv_password'),
                            oid_list=custom_oids
                        )
                        for r in oid_results:
                            self.db.update_custom_oid_value(r['id'], r.get('value', ''))
                except Exception as e:
                    print(f"[Custom OID] Error querying OIDs for {device['name']}: {e}")
            
            # 2. System Metrics (SSH/WinRM/WMI only)
            if monitor_type in ['ssh', 'winrm', 'wmi']:
                try:
                    # Calculate Bandwidth BPS
                    net_in_bps = None
                    net_out_bps = None
                    
                    raw_in = result.get('net_in')
                    raw_out = result.get('net_out')
                    
                    prev_in = device.get('last_network_in')
                    prev_out = device.get('last_network_out')
                    prev_time_str = device.get('last_metrics_time')
                    
                    if raw_in is not None and raw_out is not None and prev_in is not None and prev_out is not None and prev_time_str:
                        try:
                            # Parse last metrics time
                            # Handle different timestamp formats (PostgreSQL vs SQLite)
                            if ' ' in prev_time_str:
                                prev_time = datetime.strptime(prev_time_str.split('.')[0], '%Y-%m-%d %H:%M:%S')
                            else:
                                prev_time = datetime.fromisoformat(prev_time_str.replace('Z', '+00:00'))
                            
                            elapsed = (datetime.now() - prev_time).total_seconds()
                            
                            if elapsed > 0:
                                # Convert bytes delta to bits per second
                                # Handle counter wrap-around (basic check)
                                delta_in = raw_in - prev_in if raw_in >= prev_in else raw_in
                                delta_out = raw_out - prev_out if raw_out >= prev_out else raw_out
                                
                                net_in_bps = (delta_in * 8) / elapsed
                                net_out_bps = (delta_out * 8) / elapsed
                        except Exception as e:
                            print(f"[METRICS] Error calculating BPS for {device['name']}: {e}")

                    self.db.update_system_metrics(
                        device['id'],
                        cpu=result.get('cpu'),
                        ram=result.get('ram'),
                        disk=result.get('disk'),
                        network_in=net_in_bps,
                        network_out=net_out_bps,
                        raw_in=raw_in,
                        raw_out=raw_out
                    )
                except Exception as e:
                    print(f"[METRICS] Error updating metrics for {device['name']}: {e}")
        
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
        
        # Update database and get transactional state changes
        db_state = self.db.update_device_status(
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
            # Trigger when: 
            # 1) status was down and now up (using transactional DB state for accuracy)
            # 2) it was up/slow but had an active escalation level (missed recovery)
            db_old_status = db_state.get('old_status', 'unknown')
            db_old_escalation = db_state.get('old_escalation_level', 0)
            
            should_alert_recovery = (
                (db_old_status == 'down' and final_status in ('up', 'slow')) or
                (db_old_escalation > 0 and final_status in ('up', 'slow')) or
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
        """Check all devices in parallel using eventlet GreenPool"""
        all_devices = self.db.get_all_devices()
        # Filter for enabled devices only
        devices = [d for d in all_devices if d.get('is_enabled')]
        results = []
        
        if not devices:
            return results
        
        # Use GreenPool for cooperative multitasking (standard for Eventlet)
        pool = eventlet.GreenPool(size=self.max_workers)
        
        # Use imap to run checks and collect results as they complete
        for result in pool.imap(self._safe_check_device, devices):
            if result is not None:
                results.append(result)
        
        return results
    
    def _safe_check_device(self, device):
        """Check device with error isolation — failures don't crash other checks"""
        try:
            return self.check_device(device)
        except Exception as e:
            print(f"[ERROR] Failed to check {device.get('name', 'unknown')}: {e}")
            return None
    
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
            'devices_disabled': sum(1 for d in devices if not d.get('is_enabled')),
            'uptime_percentage': round((up / (up + slow + down) * 100), 2) if (up + slow + down) > 0 else 0,
            'average_response_time': avg_response
        }

    async def _get_snmp_interfaces_async(self, ip_address, community='public', port=161, version='2c',
                                          snmp_v3_username=None, snmp_v3_auth_protocol='SHA',
                                          snmp_v3_auth_password=None, snmp_v3_priv_protocol='AES128',
                                          snmp_v3_priv_password=None):
        """
        Get interface table via SNMP - query first 28 interfaces
        Supports v1, v2c, and v3
        """
        # Build auth data based on SNMP version
        if version == '3':
            auth_proto = SNMP_AUTH_PROTOCOLS.get(snmp_v3_auth_protocol, usmHMACSHAAuthProtocol)
            priv_proto = SNMP_PRIV_PROTOCOLS.get(snmp_v3_priv_protocol, usmAesCfb128Protocol)
            
            if snmp_v3_auth_password and snmp_v3_priv_password:
                auth_data = UsmUserData(
                    userName=snmp_v3_username or '',
                    authKey=snmp_v3_auth_password,
                    privKey=snmp_v3_priv_password,
                    authProtocol=auth_proto,
                    privProtocol=priv_proto
                )
            elif snmp_v3_auth_password:
                auth_data = UsmUserData(
                    userName=snmp_v3_username or '',
                    authKey=snmp_v3_auth_password,
                    authProtocol=auth_proto
                )
            else:
                auth_data = UsmUserData(userName=snmp_v3_username or '')
        else:
            mp_model = 0 if version == '1' else 1
            auth_data = CommunityData(community, mpModel=mp_model)
        
        snmp_engine = SnmpEngine()
        try:
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
                auth_data,
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
        finally:
            snmp_engine.close_dispatcher()

    def get_snmp_interfaces(self, ip_address, community='public', port=161, version='2c',
                            snmp_v3_username=None, snmp_v3_auth_protocol='SHA',
                            snmp_v3_auth_password=None, snmp_v3_priv_protocol='AES128',
                            snmp_v3_priv_password=None):
        """
        Get interface table - synchronous wrapper
        Supports v1, v2c, and v3
        """
        if not SNMP_AVAILABLE:
            return []
        
        try:
            coro = self._get_snmp_interfaces_async(
                ip_address, community, port, version,
                snmp_v3_username, snmp_v3_auth_protocol,
                snmp_v3_auth_password, snmp_v3_priv_protocol,
                snmp_v3_priv_password
            )
            
            def _wait_for_snmp_interfaces():
                future = asyncio.run_coroutine_threadsafe(coro, self._loop)
                return future.result(timeout=15)
                
            return tpool.execute(_wait_for_snmp_interfaces)
        except Exception as e:
            print(f"SNMP Interface Error for {ip_address}: {e}")
            return []

    def _build_snmp_auth_data(self, community, version,
                               snmp_v3_username=None, snmp_v3_auth_protocol='SHA',
                               snmp_v3_auth_password=None, snmp_v3_priv_protocol='AES128',
                               snmp_v3_priv_password=None):
        """Build SNMP auth data based on version (reusable helper)"""
        if version == '3':
            auth_proto = SNMP_AUTH_PROTOCOLS.get(snmp_v3_auth_protocol, usmHMACSHAAuthProtocol)
            priv_proto = SNMP_PRIV_PROTOCOLS.get(snmp_v3_priv_protocol, usmAesCfb128Protocol)
            if snmp_v3_auth_password and snmp_v3_priv_password:
                return UsmUserData(
                    userName=snmp_v3_username or '',
                    authKey=snmp_v3_auth_password,
                    privKey=snmp_v3_priv_password,
                    authProtocol=auth_proto,
                    privProtocol=priv_proto
                )
            elif snmp_v3_auth_password:
                return UsmUserData(
                    userName=snmp_v3_username or '',
                    authKey=snmp_v3_auth_password,
                    authProtocol=auth_proto
                )
            else:
                return UsmUserData(userName=snmp_v3_username or '')
        else:
            mp_model = 0 if version == '1' else 1
            return CommunityData(community, mpModel=mp_model)

    async def _query_custom_oids_async(self, ip_address, community, port, version,
                                        snmp_v3_username, snmp_v3_auth_protocol,
                                        snmp_v3_auth_password, snmp_v3_priv_protocol,
                                        snmp_v3_priv_password, oid_list):
        """
        Query multiple custom OIDs asynchronously
        oid_list: list of {'id': int, 'oid': str, 'name': str, 'unit': str}
        Returns: list of {'id': int, 'oid': str, 'name': str, 'value': str, 'unit': str}
        """
        auth_data = self._build_snmp_auth_data(
            community, version, snmp_v3_username, snmp_v3_auth_protocol,
            snmp_v3_auth_password, snmp_v3_priv_protocol, snmp_v3_priv_password
        )

        snmp_engine = SnmpEngine()
        try:
            transport = await UdpTransportTarget.create(
                (ip_address, port), timeout=Config.SNMP_TIMEOUT, retries=1
            )

            # Build OID objects
            objects = [ObjectType(ObjectIdentity(item['oid'])) for item in oid_list]

            errorIndication, errorStatus, errorIndex, varBinds = await get_cmd(
                snmp_engine, auth_data, transport, ContextData(), *objects
            )

            results = []
            if errorIndication:
                print(f"Custom OID Error: {errorIndication}")
                for item in oid_list:
                    results.append({**item, 'value': f'Error: {errorIndication}'})
                return results

            if errorStatus:
                print(f"Custom OID Error: {errorStatus.prettyPrint()}")
                for item in oid_list:
                    results.append({**item, 'value': f'Error: {errorStatus.prettyPrint()}'})
                return results

            # Map results back to OID list
            for i, varBind in enumerate(varBinds):
                value = varBind[1]
                val_str = str(value) if 'noSuch' not in str(type(value).__name__) else 'N/A'
                if i < len(oid_list):
                    results.append({**oid_list[i], 'value': val_str})

            return results
        finally:
            snmp_engine.close_dispatcher()

    def query_custom_oids(self, ip_address, community='public', port=161, version='2c',
                          snmp_v3_username=None, snmp_v3_auth_protocol='SHA',
                          snmp_v3_auth_password=None, snmp_v3_priv_protocol='AES128',
                          snmp_v3_priv_password=None, oid_list=None):
        """Query custom OIDs - synchronous wrapper"""
        if not SNMP_AVAILABLE or not oid_list:
            return []
        try:
            coro = self._query_custom_oids_async(
                ip_address, community, port, version,
                snmp_v3_username, snmp_v3_auth_protocol,
                snmp_v3_auth_password, snmp_v3_priv_protocol,
                snmp_v3_priv_password, oid_list
            )
            
            def _wait_for_custom_oids():
                future = asyncio.run_coroutine_threadsafe(coro, self._loop)
                return future.result(timeout=20)
                
            return tpool.execute(_wait_for_custom_oids)
        except Exception as e:
            print(f"Custom OID Query Error: {e}")
            return [{'id': item['id'], 'oid': item['oid'], 'name': item['name'],
                     'value': f'Error: {e}', 'unit': item.get('unit', '')} for item in oid_list]

    async def _poll_bandwidth_async(self, ip_address, community='public', port=161, version='2c',
                                    snmp_v3_username=None, snmp_v3_auth_protocol='SHA',
                                    snmp_v3_auth_password=None, snmp_v3_priv_protocol='AES128',
                                    snmp_v3_priv_password=None, max_interfaces=28):
        """
        Poll ifDescr, ifSpeed, ifInOctets, ifOutOctets using get_cmd.
        4 separate get_cmd calls (one per column), same pattern as _check_snmp_async.
        """
        # Build auth data — identical to _check_snmp_async
        if version == '3':
            auth_proto = SNMP_AUTH_PROTOCOLS.get(snmp_v3_auth_protocol, usmHMACSHAAuthProtocol)
            priv_proto = SNMP_PRIV_PROTOCOLS.get(snmp_v3_priv_protocol, usmAesCfb128Protocol)
            if snmp_v3_auth_password and snmp_v3_priv_password:
                auth_data = UsmUserData(
                    userName=snmp_v3_username or '',
                    authKey=snmp_v3_auth_password, privKey=snmp_v3_priv_password,
                    authProtocol=auth_proto, privProtocol=priv_proto
                )
            elif snmp_v3_auth_password:
                auth_data = UsmUserData(
                    userName=snmp_v3_username or '',
                    authKey=snmp_v3_auth_password, authProtocol=auth_proto
                )
            else:
                auth_data = UsmUserData(userName=snmp_v3_username or '')
        else:
            mp_model = 0 if version == '1' else 1
            auth_data = CommunityData(community, mpModel=mp_model)

        snmp_engine = SnmpEngine()
        try:
            transport = await UdpTransportTarget.create((ip_address, port), timeout=Config.SNMP_TIMEOUT, retries=1)


            interfaces = {}
            batch_size = 4  # 4 interfaces × 4 OIDs = 16 OIDs per GET — safe for all switches

            found_any = True
            for batch_start in range(1, max_interfaces + 1, batch_size):
                if not found_any:
                    break
                batch_indices = list(range(batch_start, min(batch_start + batch_size, max_interfaces + 1)))

                # Build OID list for this batch: all 4 columns for each interface index
                oids = []
                col_map = {}
                for idx in batch_indices:
                    for col_num, field in [(2, 'if_name'), (5, 'if_speed'), (10, 'bytes_in'), (16, 'bytes_out')]:
                        oid_str = f'1.3.6.1.2.1.2.2.1.{col_num}.{idx}'
                        oids.append(ObjectType(ObjectIdentity(oid_str)))
                        col_map[oid_str] = (idx, field)

                try:
                    errInd, errStat, errIdx, varBinds = await get_cmd(
                        snmp_engine, auth_data, transport, ContextData(), *oids
                    )
                except Exception as e:
                    print(f"[BW] get_cmd exception batch if{batch_start}-{batch_indices[-1]} @ {ip_address}: {e}")
                    break

                if errInd:
                    print(f"[BW] get_cmd error batch if{batch_start} @ {ip_address}: {errInd}")
                    break
                if errStat:
                    print(f"[BW] SNMP error batch if{batch_start} @ {ip_address}: {errStat.prettyPrint()}")
                    break

                found_any = False
                for vb in varBinds:
                    oid_str = str(vb[0])
                    val = vb[1]
                    val_type = type(val).__name__
                    if 'noSuch' in val_type or 'endOf' in val_type:
                        continue
                    if oid_str not in col_map:
                        continue
                    if_idx, field = col_map[oid_str]
                    if if_idx not in interfaces:
                        interfaces[if_idx] = {'if_index': if_idx, 'if_name': '',
                                              'if_speed': 0, 'bytes_in': 0, 'bytes_out': 0}
                    parser = str if field == 'if_name' else int
                    try:
                        interfaces[if_idx][field] = parser(val)
                        found_any = True
                    except Exception:
                        pass

            result = list(interfaces.values())
            print(f"[BW] Polled {len(result)} interfaces from {ip_address}")
            return result
        finally:
            snmp_engine.close_dispatcher()

    def poll_bandwidth(self, device):
        """
        Poll bandwidth counters for one SNMP device and save to DB.
        Calculates bps by comparing to the previous sample.
        """
        if not SNMP_AVAILABLE:
            return
        device_id = device['id']
        ip_address = device['ip_address']
        community = device.get('snmp_community', 'public')
        port = device.get('snmp_port', 161)
        version = device.get('snmp_version', '2c')
        kwargs = dict(
            snmp_v3_username=device.get('snmp_v3_username'),
            snmp_v3_auth_protocol=device.get('snmp_v3_auth_protocol', 'SHA'),
            snmp_v3_auth_password=device.get('snmp_v3_auth_password'),
            snmp_v3_priv_protocol=device.get('snmp_v3_priv_protocol', 'AES128'),
            snmp_v3_priv_password=device.get('snmp_v3_priv_password'),
        )

        try:
            # Run coroutine in the dedicated asyncio thread
            coro = self._poll_bandwidth_async(ip_address, community, port, version, **kwargs)
            
            def _wait_for_bandwidth():
                future = asyncio.run_coroutine_threadsafe(coro, self._loop)
                return future.result(timeout=25)
            
            try:
                samples = tpool.execute(_wait_for_bandwidth)
            except Exception as e:
                print(f"[ERROR] Bandwidth worker thread call failed for {ip_address}: {e}")
                return
        except Exception as e:
            print(f"[BW] Poll error for {ip_address}: {e}")
            return

        now = datetime.now()
        for s in samples:
            if_index = s['if_index']
            prev = self.db.get_last_bandwidth_sample(device_id, if_index)

            bps_in = bps_out = util_in = util_out = None
            if prev:
                try:
                    prev_time = datetime.fromisoformat(str(prev['sampled_at']))
                    elapsed = (now - prev_time).total_seconds()
                    if elapsed > 0:
                        # 32-bit counter wrap-around: max is 2^32
                        COUNTER_MAX = 4294967296
                        delta_in = s['bytes_in'] - prev['bytes_in']
                        delta_out = s['bytes_out'] - prev['bytes_out']
                        if delta_in < 0:
                            delta_in += COUNTER_MAX
                        if delta_out < 0:
                            delta_out += COUNTER_MAX
                        bps_in = (delta_in * 8) / elapsed
                        bps_out = (delta_out * 8) / elapsed
                        if_speed = s.get('if_speed') or 0
                        if if_speed > 0:
                            util_in = min((bps_in / if_speed) * 100, 100)
                            util_out = min((bps_out / if_speed) * 100, 100)
                except Exception as e:
                    print(f"[BW] Delta calc error if{if_index}: {e}")

            self.db.save_bandwidth_sample(
                device_id=device_id,
                if_index=if_index,
                if_name=s['if_name'],
                bytes_in=s['bytes_in'],
                bytes_out=s['bytes_out'],
                bps_in=bps_in,
                bps_out=bps_out,
                if_speed=s.get('if_speed'),
                util_in=util_in,
                util_out=util_out
            )
        print(f"[BW] Polled {len(samples)} interfaces on {ip_address}")

    def poll_bandwidth_all_snmp_devices(self):
        """Poll bandwidth for all SNMP devices. Called by scheduler every 60s."""
        all_devices = self.db.get_all_devices()
        # Filter for enabled SNMP devices
        snmp_devices = [d for d in all_devices if d.get('monitor_type') == 'snmp' and d.get('is_enabled')]
        if not snmp_devices:
            return
        
        print(f"[BW] Polling {len(snmp_devices)} SNMP device(s)...")
        
        # Use GreenPool for cooperative multitasking
        pool = eventlet.GreenPool(size=min(10, len(snmp_devices)))
        
        # Run polls and wait for all to complete
        for _ in pool.imap(self.poll_bandwidth, snmp_devices):
            pass

