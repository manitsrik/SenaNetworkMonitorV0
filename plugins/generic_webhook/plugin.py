import requests
import time


class Plugin:
    """Integration plugin that forwards alerts to an HTTP webhook endpoint."""

    def send(self, payload, config, context=None):
        context = context or {}
        config = config or {}

        url = str(config.get('url') or '').strip()
        if not url:
            return {'success': False, 'error': 'Webhook URL is required'}

        method = str(config.get('method') or 'POST').strip().upper()
        if method not in {'POST', 'PUT'}:
            return {'success': False, 'error': f'Unsupported method: {method}'}

        timeout_seconds = config.get('timeout_seconds', 10) or 10
        retry_attempts = int(config.get('retry_attempts', 2) or 0)
        retry_backoff_seconds = float(config.get('retry_backoff_seconds', 1) or 0)
        verify_tls = bool(config.get('verify_tls', True))
        bearer_token = str(config.get('bearer_token') or '').strip()
        header_name = str(config.get('header_name') or '').strip()
        header_value = str(config.get('header_value') or '').strip()

        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'NW-Monitor-Plugin/generic_webhook'
        }
        if bearer_token:
            headers['Authorization'] = f'Bearer {bearer_token}'
        if header_name and header_value:
            headers[header_name] = header_value

        request_payload = dict(payload)
        request_payload['integration_context'] = {
            'is_test': bool(context.get('is_test')),
            'plugin_id': 'generic_webhook'
        }

        last_error = None
        total_attempts = max(1, retry_attempts + 1)

        for attempt in range(1, total_attempts + 1):
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    json=request_payload,
                    headers=headers,
                    timeout=float(timeout_seconds),
                    verify=verify_tls,
                )
                success = response.status_code < 300
                should_retry = response.status_code >= 500 and attempt < total_attempts
                if success or not should_retry:
                    return {
                        'success': success,
                        'message': f'Webhook returned HTTP {response.status_code} on attempt {attempt}/{total_attempts}',
                        'status_code': response.status_code,
                        'attempts': attempt,
                        'response_excerpt': response.text[:200],
                        'error': None if success else f'HTTP {response.status_code}: {response.text[:200]}'
                    }
                last_error = f'HTTP {response.status_code}: {response.text[:200]}'
            except requests.exceptions.Timeout:
                last_error = 'Webhook request timed out'
            except requests.exceptions.ConnectionError as exc:
                last_error = f'Connection error: {str(exc)[:200]}'
            except Exception as exc:
                last_error = str(exc)
                if attempt >= total_attempts:
                    break

            if attempt < total_attempts and retry_backoff_seconds > 0:
                time.sleep(retry_backoff_seconds)

        return {
            'success': False,
            'error': last_error or 'Webhook delivery failed',
            'attempts': total_attempts,
        }
