"""
Alert Service Module for Network Monitor
Handles sending alerts via Email and LINE Notify
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import requests


class Alerter:
    """Alert service for sending notifications"""
    
    def __init__(self, database):
        self.db = database
        self._settings_cache = {}
        self._cache_time = None
        self._cache_duration = timedelta(seconds=30)
        # In-memory lock to prevent duplicate alerts (race condition prevention)
        self._recent_alerts = {}  # key: (device_id, event_type), value: datetime
        self._alert_lock_duration = timedelta(seconds=30)  # Minimum 30 seconds between same alerts
    
    def _get_settings(self):
        """Get alert settings from database with caching"""
        now = datetime.now()
        if self._cache_time and (now - self._cache_time) < self._cache_duration:
            return self._settings_cache
        
        settings = self.db.get_all_alert_settings()
        self._settings_cache = {s['setting_key']: s['setting_value'] for s in settings}
        self._cache_time = now
        return self._settings_cache
    
    def _get_setting(self, key, default=None):
        """Get a single setting value"""
        settings = self._get_settings()
        return settings.get(key, default)
    
    def is_enabled(self, channel):
        """Check if a notification channel is enabled"""
        return self._get_setting(f'{channel}_enabled', 'false').lower() == 'true'
    
    def send_email(self, subject, message, recipient=None):
        """
        Send email notification via SMTP
        Supports multiple recipients (comma-separated)
        Returns: dict with 'success' and 'error' (if failed)
        """
        settings = self._get_settings()
        
        smtp_server = settings.get('smtp_server', '').strip()
        smtp_port = int(settings.get('smtp_port', 587))
        smtp_user = settings.get('smtp_user', '').strip()
        smtp_password = settings.get('smtp_password', '')
        smtp_from = settings.get('smtp_from', '').strip() or smtp_user
        recipient_str = (recipient or settings.get('email_recipient', '')).strip()
        
        # Support multiple recipients (comma-separated)
        recipients = [r.strip() for r in recipient_str.split(',') if r.strip()]
        
        if not all([smtp_server, smtp_user, smtp_password]) or not recipients:
            return {'success': False, 'error': 'Email settings incomplete'}
        
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = smtp_from
            msg['To'] = ', '.join(recipients)  # Display all recipients
            msg['Subject'] = f"[Network Monitor] {subject}"
            
            # Add body
            body = f"""
Network Monitor Alert
=====================

{message}

Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---
This is an automated message from Network Monitor.
"""
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
            
            # Connect and send
            if smtp_port == 465:
                # Use SSL directly for port 465
                server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=30)
            else:
                # Use STARTTLS for port 587 and others
                server = smtplib.SMTP(smtp_server, smtp_port, timeout=30)
                server.ehlo()
                server.starttls()
                server.ehlo()
            
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
            server.quit()
            
            return {'success': True}
            
        except smtplib.SMTPAuthenticationError as e:
            return {'success': False, 'error': f'SMTP authentication failed: {str(e)}'}
        except smtplib.SMTPException as e:
            return {'success': False, 'error': f'SMTP error: {str(e)}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def send_line_notify(self, message):
        """
        Send LINE Notify message (DEPRECATED - service ended March 2025)
        Returns: dict with 'success' and 'error' (if failed)
        """
        token = self._get_setting('line_notify_token', '')
        
        if not token:
            return {'success': False, 'error': 'LINE Notify token not configured'}
        
        try:
            url = 'https://notify-api.line.me/api/notify'
            headers = {
                'Authorization': f'Bearer {token}'
            }
            data = {
                'message': f"\n🔔 Network Monitor Alert\n\n{message}\n\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            }
            
            response = requests.post(url, headers=headers, data=data, timeout=10)
            
            if response.status_code == 200:
                return {'success': True}
            elif response.status_code == 401:
                return {'success': False, 'error': 'Invalid LINE Notify token'}
            else:
                return {'success': False, 'error': f'LINE API error: {response.status_code}'}
                
        except requests.exceptions.Timeout:
            return {'success': False, 'error': 'LINE Notify timeout'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def send_telegram(self, message):
        """
        Send Telegram message via Bot API
        Returns: dict with 'success' and 'error' (if failed)
        """
        bot_token = self._get_setting('telegram_bot_token', '').strip()
        chat_id_str = self._get_setting('telegram_chat_id', '').strip()
        
        if not bot_token or not chat_id_str:
            return {'success': False, 'error': 'Telegram settings incomplete (need Bot Token and Chat ID)'}
        
        # Support multiple chat IDs
        chat_ids = [id.strip() for id in chat_id_str.split(',') if id.strip()]
        
        if not chat_ids:
             return {'success': False, 'error': 'No valid Telegram Chat IDs found'}
             
        success_count = 0
        errors = []
        
        for chat_id in chat_ids:
            try:
                url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
                
                # Format message with emoji
                formatted_message = f"🔔 *Network Monitor Alert*\n\n{message}\n\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                
                data = {
                    'chat_id': chat_id,
                    'text': formatted_message,
                    'parse_mode': 'Markdown'
                }
                
                response = requests.post(url, data=data, timeout=10)
                result = response.json()
                
                if response.status_code == 200 and result.get('ok'):
                    success_count += 1
                elif response.status_code == 401:
                    errors.append(f"Invalid Token for {chat_id}")
                else:
                    error_desc = result.get('description', 'Bad request')
                    errors.append(f"Error for {chat_id}: {error_desc}")
                    
            except requests.exceptions.Timeout:
                errors.append(f"Timeout for {chat_id}")
            except Exception as e:
                errors.append(f"Error for {chat_id}: {str(e)}")
        
        if success_count > 0:
            if len(errors) > 0:
                return {'success': True, 'warning': f"Sent to {success_count}/{len(chat_ids)}, Errors: {'; '.join(errors)}"}
            return {'success': True}
        else:
            return {'success': False, 'error': f"All attempts failed: {'; '.join(errors)}"}
                
        except requests.exceptions.Timeout:
            return {'success': False, 'error': 'Telegram timeout'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def should_alert(self, device_id, event_type):
        """
        Check if we should send an alert (rate limiting and maintenance check)
        Returns True if enough time has passed since last alert and device is not in maintenance
        """
        now = datetime.now()
        alert_key = (device_id, event_type)
        
        # Check if device is in maintenance mode
        if self.db.is_device_in_maintenance(device_id):
            print(f"[Alert] Skipping alert - device {device_id} is in maintenance mode")
            return False
        
        # First check in-memory lock (prevents race conditions)
        if alert_key in self._recent_alerts:
            last_memory_time = self._recent_alerts[alert_key]
            if (now - last_memory_time) < self._alert_lock_duration:
                return False
        
        # Then check database cooldown
        cooldown = int(self._get_setting('alert_cooldown', 300))  # Default 5 minutes
        last_alert = self.db.get_last_alert_time(device_id, event_type)
        
        if not last_alert:
            return True
        
        try:
            last_time = datetime.fromisoformat(last_alert)
            return (now - last_time).total_seconds() >= cooldown
        except:
            return True
    
    def _mark_alert_sent(self, device_id, event_type):
        """Mark alert as sent in memory lock"""
        alert_key = (device_id, event_type)
        self._recent_alerts[alert_key] = datetime.now()
        
        # Clean up old entries (older than 10 minutes)
        cutoff = datetime.now() - timedelta(minutes=10)
        self._recent_alerts = {
            k: v for k, v in self._recent_alerts.items() 
            if v > cutoff
        }
    
    def trigger_alert(self, device, event_type, message):
        """
        Trigger an alert for a device event
        Sends to all enabled channels
        """
        device_id = device.get('id')
        device_name = device.get('name', 'Unknown')
        
        # Check rate limiting
        if not self.should_alert(device_id, event_type):
            print(f"[Alert] Skipping alert for {device_name} ({event_type}) - cooldown active")
            return
        
        # Immediately mark as sent to prevent race conditions
        self._mark_alert_sent(device_id, event_type)
        
        # Check if alerts are enabled for this event type
        alert_on_down = self._get_setting('alert_on_down', 'true').lower() == 'true'
        alert_on_recovery = self._get_setting('alert_on_recovery', 'true').lower() == 'true'
        alert_on_ssl = self._get_setting('alert_on_ssl_expiry', 'true').lower() == 'true'
        
        if event_type == 'down' and not alert_on_down:
            return
        if event_type == 'recovery' and not alert_on_recovery:
            return
        if event_type == 'ssl_expiry' and not alert_on_ssl:
            return
        
        # Format message with device info
        full_message = f"Device: {device_name}\nIP: {device.get('ip_address', 'N/A')}\n\n{message}"
        
        # Determine emoji/prefix based on event type
        if event_type == 'down':
            subject = f"🔴 Device DOWN: {device_name}"
        elif event_type == 'recovery':
            subject = f"🟢 Device RECOVERED: {device_name}"
        elif event_type == 'ssl_expiry':
            subject = f"⚠️ SSL Expiring: {device_name}"
        else:
            subject = f"Alert: {device_name}"
        
        sent_any = False
        
        # Send via Email
        if self.is_enabled('email'):
            result = self.send_email(subject, full_message)
            self.db.log_alert(
                device_id, event_type, message, 'email',
                'sent' if result['success'] else 'failed',
                result.get('error')
            )
            if result['success']:
                sent_any = True
                print(f"[Alert] Email sent for {device_name}: {event_type}")
            else:
                print(f"[Alert] Email failed for {device_name}: {result.get('error')}")
        
        # Send via LINE Notify (DEPRECATED)
        if self.is_enabled('line'):
            line_message = f"{subject}\n\n{full_message}"
            result = self.send_line_notify(line_message)
            self.db.log_alert(
                device_id, event_type, message, 'line',
                'sent' if result['success'] else 'failed',
                result.get('error')
            )
            if result['success']:
                sent_any = True
                print(f"[Alert] LINE sent for {device_name}: {event_type}")
            else:
                print(f"[Alert] LINE failed for {device_name}: {result.get('error')}")
        
        # Send via Telegram
        if self.is_enabled('telegram'):
            telegram_message = f"{subject}\n\n{full_message}"
            result = self.send_telegram(telegram_message)
            self.db.log_alert(
                device_id, event_type, message, 'telegram',
                'sent' if result['success'] else 'failed',
                result.get('error')
            )
            if result['success']:
                sent_any = True
                print(f"[Alert] Telegram sent for {device_name}: {event_type}")
            else:
                print(f"[Alert] Telegram failed for {device_name}: {result.get('error')}")
        
        if not sent_any:
            print(f"[Alert] No channels enabled or all failed for {device_name}")
    
    def send_test_alert(self, channel):
        """
        Send a test alert to verify configuration
        Returns: dict with 'success' and 'error' (if failed)
        """
        test_message = "This is a test alert from Network Monitor.\n\nIf you received this message, your notification settings are working correctly!"
        
        if channel == 'email':
            return self.send_email("Test Alert", test_message)
        elif channel == 'line':
            return self.send_line_notify(f"🧪 Test Alert\n\n{test_message}")
        elif channel == 'telegram':
            return self.send_telegram(f"🧪 *Test Alert*\n\n{test_message}")
        else:
            return {'success': False, 'error': f'Unknown channel: {channel}'}
