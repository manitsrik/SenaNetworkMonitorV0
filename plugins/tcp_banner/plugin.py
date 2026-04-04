import socket
import time


class Plugin:
    def check(self, device, context):
        ip_address = device.get('ip_address')
        port = int(device.get('tcp_port') or 80)
        timeout = 5
        plugin_config = device.get('plugin_config') or {}
        expected_banner = str(plugin_config.get('expected_banner') or '').strip()
        read_banner = bool(plugin_config.get('read_banner', True))
        match_mode = str(plugin_config.get('match_mode') or 'contains').strip().lower()

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        start = time.time()
        try:
            result = sock.connect_ex((ip_address, port))
            if result != 0:
                return {
                    'status': 'down',
                    'response_time': None,
                    'message': f'Port {port} is closed or unreachable'
                }

            if read_banner:
                try:
                    banner = sock.recv(512)
                except Exception:
                    banner = b''
            else:
                banner = b''

            response_time = round((time.time() - start) * 1000, 2)
            banner_text = banner.decode('utf-8', errors='ignore').strip()

            if expected_banner:
                matches = False
                if banner_text:
                    if match_mode == 'exact':
                        matches = banner_text.strip().lower() == expected_banner.lower()
                    else:
                        matches = expected_banner.lower() in banner_text.lower()

                if matches:
                    return {
                        'status': 'up',
                        'response_time': response_time,
                        'message': f'Expected banner matched on port {port}',
                        'banner': banner_text[:200]
                    }
                return {
                    'status': 'slow' if banner_text else 'warning',
                    'response_time': response_time,
                    'message': f'Connected to port {port}, but expected banner was not found',
                    'banner': banner_text[:200]
                }

            return {
                'status': 'up',
                'response_time': response_time,
                'message': f'Connected to port {port}',
                'banner': banner_text[:200]
            }
        finally:
            try:
                sock.close()
            except Exception:
                pass
