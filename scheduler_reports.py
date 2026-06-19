"""
Scheduled Reports Module for Network Monitor
Generates and sends daily email summaries of network status
"""
import smtplib
import json
from html import escape
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta


class ReportGenerator:
    def __init__(self, db):
        self.db = db
    
    def _get_setting(self, key, default=None):
        """Get a setting from database"""
        value = self.db.get_alert_setting(key)
        return value if value is not None else default
    
    def generate_daily_report(self):
        """Generate a daily summary report"""
        devices = self.db.get_all_devices()
        
        # Calculate statistics
        total = len(devices)
        up_count = sum(1 for d in devices if d.get('status') == 'up')
        down_count = sum(1 for d in devices if d.get('status') == 'down')
        slow_count = sum(1 for d in devices if d.get('status') == 'slow')
        unknown_count = total - up_count - down_count - slow_count
        
        uptime_percent = (up_count + slow_count) / total * 100 if total > 0 else 0
        
        # Get 24h SLA data
        sla_data = self.db.get_all_devices_sla(days=1, sla_target=99.9)
        avg_uptime = sum(d['uptime_percent'] for d in sla_data if d['uptime_percent']) / len([d for d in sla_data if d['uptime_percent']]) if sla_data else 0
        
        # Get down devices
        down_devices = [d for d in devices if d.get('status') == 'down']
        
        # Get slow devices
        slow_devices = [d for d in devices if d.get('status') == 'slow']
        
        # Get recent alerts (last 24 hours)
        alerts = self.db.get_alert_history(limit=50)
        yesterday = (datetime.now() - timedelta(days=1)).isoformat()
        recent_alerts = [a for a in alerts if a.get('created_at', '') > yesterday]
        
        return {
            'generated_at': datetime.now().isoformat(),
            'summary': {
                'total_devices': total,
                'up': up_count,
                'down': down_count,
                'slow': slow_count,
                'unknown': unknown_count,
                'uptime_percent': round(uptime_percent, 2),
                'avg_24h_uptime': round(avg_uptime, 4)
            },
            'down_devices': down_devices,
            'slow_devices': slow_devices,
            'recent_alerts': recent_alerts[:10],  # Top 10 recent alerts
            'alert_count': len(recent_alerts)
        }

    @staticmethod
    def _json_value(device, key, fallback):
        try:
            value = device.get(key)
            return json.loads(value) if value else fallback
        except (TypeError, ValueError):
            return fallback

    def generate_server_health_report(self):
        """Build a latest-state report for SSH/WinRM monitored servers."""
        servers, service_down, pending_reboot, disks = [], [], [], []
        for device in self.db.get_all_devices():
            if device.get('monitor_type') not in ('ssh', 'winrm', 'wmi'):
                continue
            server = {
                'id': device.get('id'), 'name': device.get('name') or 'Unknown',
                'ip_address': device.get('ip_address') or '',
                'status': device.get('status') or 'unknown',
                'cpu': device.get('cpu_usage'), 'ram': device.get('ram_usage'),
                'disk': device.get('disk_usage'), 'swap': device.get('swap_usage'),
                'pending_reboot': bool(device.get('pending_reboot')),
            }
            servers.append(server)
            if server['pending_reboot']:
                pending_reboot.append(server)
            for service in self._json_value(device, 'service_status_json', []):
                if not service.get('ok'):
                    service_down.append({
                        'device_name': server['name'], 'service': service.get('name') or 'Unknown',
                        'status': service.get('status') or 'unknown',
                    })
            for disk in self._json_value(device, 'disk_details_json', []):
                disks.append({
                    'device_name': server['name'],
                    'mount': disk.get('mount') or disk.get('name') or '-',
                    'use_percent': disk.get('use_percent'),
                })

        def top(items, key):
            def numeric(item):
                try:
                    return float(item.get(key))
                except (TypeError, ValueError):
                    return -1
            return sorted((i for i in items if i.get(key) is not None), key=numeric, reverse=True)[:10]

        return {
            'generated_at': datetime.now().isoformat(),
            'summary': {
                'total': len(servers),
                'up': sum(1 for s in servers if s['status'] == 'up'),
                'slow': sum(1 for s in servers if s['status'] == 'slow'),
                'down': sum(1 for s in servers if s['status'] == 'down'),
                'service_down': len(service_down), 'pending_reboot': len(pending_reboot),
            },
            'top_cpu': top(servers, 'cpu'), 'top_ram': top(servers, 'ram'),
            'top_disk': top(disks, 'use_percent'), 'service_down': service_down,
            'pending_reboot': pending_reboot,
        }

    def generate_server_health_html(self, data):
        """Render a compact server-health email without Flask dependencies."""
        summary = data['summary']

        def rows(items, value_key):
            if not items:
                return '<tr><td colspan="2">No data</td></tr>'
            output = []
            for item in items:
                label = escape(str(item.get('device_name') or item.get('name') or 'Unknown'))
                if item.get('mount'):
                    label += ' - ' + escape(str(item['mount']))
                output.append(f'<tr><td>{label}</td><td>{escape(str(item.get(value_key)))}%</td></tr>')
            return ''.join(output)

        service_rows = ''.join(
            f'<tr><td>{escape(str(i["device_name"]))}</td><td>{escape(str(i["service"]))} ({escape(str(i["status"]))})</td></tr>'
            for i in data['service_down']
        ) or '<tr><td colspan="2">All monitored services are running</td></tr>'
        reboot_rows = ''.join(
            f'<tr><td>{escape(str(i["name"]))}</td><td>{escape(str(i["ip_address"]))}</td></tr>'
            for i in data['pending_reboot']
        ) or '<tr><td colspan="2">No pending reboot</td></tr>'

        return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
body{{font-family:Segoe UI,Arial,sans-serif;background:#f4f6f8;color:#172033;padding:20px}}
.wrap{{max-width:760px;margin:auto;background:#fff;border:1px solid #dce2e8;padding:24px}}
.summary{{display:flex;flex-wrap:wrap;gap:12px;margin:20px 0}}.metric{{border-left:4px solid #238764;padding:8px 14px;min-width:80px}}
.value{{font-size:24px;font-weight:700}}.label{{font-size:12px;color:#667085}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:7px;border-bottom:1px solid #e5e7eb;text-align:left;font-size:13px}}th{{background:#f8fafc}}
h1{{font-size:22px}}h2{{font-size:16px;margin-top:22px}}.critical{{color:#b42318}}@media(max-width:620px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><div class="wrap"><h1>Server Health Report</h1><div>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
<div class="summary"><div class="metric"><div class="value">{summary['total']}</div><div class="label">Servers</div></div>
<div class="metric"><div class="value">{summary['up']}</div><div class="label">Up</div></div>
<div class="metric"><div class="value critical">{summary['down']}</div><div class="label">Down</div></div>
<div class="metric"><div class="value critical">{summary['service_down']}</div><div class="label">Services Down</div></div>
<div class="metric"><div class="value">{summary['pending_reboot']}</div><div class="label">Pending Reboot</div></div></div>
<div class="grid"><section><h2>Top CPU</h2><table><tr><th>Server</th><th>Usage</th></tr>{rows(data['top_cpu'], 'cpu')}</table></section>
<section><h2>Top RAM</h2><table><tr><th>Server</th><th>Usage</th></tr>{rows(data['top_ram'], 'ram')}</table></section>
<section><h2>Top Disk / Partition</h2><table><tr><th>Server / Disk</th><th>Usage</th></tr>{rows(data['top_disk'], 'use_percent')}</table></section>
<section><h2>Service Down</h2><table><tr><th>Server</th><th>Service</th></tr>{service_rows}</table></section></div>
<h2>Pending Reboot</h2><table><tr><th>Server</th><th>IP Address</th></tr>{reboot_rows}</table></div></body></html>'''
    
    def generate_html_report(self, report_data):
        """Generate HTML email content from report data"""
        summary = report_data['summary']
        
        # Status color
        if summary['down'] > 0:
            status_color = '#ef4444'
            status_text = '⚠️ Issues Detected'
        elif summary['slow'] > 0:
            status_color = '#f59e0b'
            status_text = '⚡ Some Devices Slow'
        else:
            status_color = '#22c55e'
            status_text = '✅ All Systems Operational'
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #1a1a2e; color: #e0e0e0; padding: 20px; }}
        .container {{ max-width: 600px; margin: 0 auto; background: #16213e; border-radius: 12px; padding: 24px; }}
        .header {{ text-align: center; padding-bottom: 20px; border-bottom: 1px solid #2a3a5e; }}
        .header h1 {{ color: #60a5fa; margin: 0; }}
        .status-banner {{ background: {status_color}; color: white; padding: 12px; border-radius: 8px; text-align: center; margin: 20px 0; font-weight: 600; }}
        .stats {{ display: flex; justify-content: space-around; text-align: center; margin: 20px 0; }}
        .stat {{ padding: 16px; }}
        .stat-value {{ font-size: 28px; font-weight: bold; color: #60a5fa; }}
        .stat-label {{ color: #9ca3af; font-size: 12px; text-transform: uppercase; }}
        .section {{ margin: 20px 0; padding: 16px; background: #1a2744; border-radius: 8px; }}
        .section-title {{ color: #60a5fa; font-size: 14px; font-weight: 600; margin-bottom: 12px; }}
        .device-item {{ padding: 8px 0; border-bottom: 1px solid #2a3a5e; }}
        .device-name {{ font-weight: 500; }}
        .device-ip {{ color: #9ca3af; font-size: 12px; }}
        .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; }}
        .badge-down {{ background: #ef4444; color: white; }}
        .badge-slow {{ background: #f59e0b; color: white; }}
        .footer {{ text-align: center; padding-top: 20px; color: #6b7280; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🌐 Network Monitor</h1>
            <p style="color: #9ca3af;">Daily Status Report</p>
        </div>
        
        <div class="status-banner">{status_text}</div>
        
        <div class="stats">
            <div class="stat">
                <div class="stat-value">{summary['total_devices']}</div>
                <div class="stat-label">Total</div>
            </div>
            <div class="stat">
                <div class="stat-value" style="color: #22c55e;">{summary['up']}</div>
                <div class="stat-label">Up</div>
            </div>
            <div class="stat">
                <div class="stat-value" style="color: #f59e0b;">{summary['slow']}</div>
                <div class="stat-label">Slow</div>
            </div>
            <div class="stat">
                <div class="stat-value" style="color: #ef4444;">{summary['down']}</div>
                <div class="stat-label">Down</div>
            </div>
            <div class="stat">
                <div class="stat-value">{summary['uptime_percent']}%</div>
                <div class="stat-label">Uptime</div>
            </div>
        </div>
"""
        
        # Down devices section
        if report_data['down_devices']:
            html += '<div class="section"><div class="section-title">🔴 Down Devices</div>'
            for d in report_data['down_devices'][:5]:
                html += f'''
                <div class="device-item">
                    <span class="device-name">{d.get('name', 'Unknown')}</span>
                    <span class="badge badge-down">DOWN</span>
                    <div class="device-ip">{d.get('ip_address', '')}</div>
                </div>'''
            if len(report_data['down_devices']) > 5:
                html += f'<p style="color: #9ca3af; font-size: 12px;">... and {len(report_data["down_devices"]) - 5} more</p>'
            html += '</div>'
        
        # Slow devices section
        if report_data['slow_devices']:
            html += '<div class="section"><div class="section-title">🟡 Slow Devices</div>'
            for d in report_data['slow_devices'][:5]:
                html += f'''
                <div class="device-item">
                    <span class="device-name">{d.get('name', 'Unknown')}</span>
                    <span class="badge badge-slow">{d.get('response_time', 'N/A')} ms</span>
                    <div class="device-ip">{d.get('ip_address', '')}</div>
                </div>'''
            html += '</div>'
        
        # Alerts section
        if report_data['alert_count'] > 0:
            html += f'<div class="section"><div class="section-title">📢 Alerts (Last 24h): {report_data["alert_count"]}</div></div>'
        
        html += f'''
        <div class="footer">
            <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>Network Monitor - Automated Daily Report</p>
        </div>
    </div>
</body>
</html>
'''
        return html
    
    def send_report_email(self, html_content, subject=None, to_email=None):
        """Send the report via email"""
        smtp_server = self._get_setting('smtp_server')
        smtp_port = int(self._get_setting('smtp_port', 587))
        smtp_user = self._get_setting('smtp_user')
        smtp_password = self._get_setting('smtp_password')
        smtp_from = self._get_setting('smtp_from')
        recipient = to_email or self._get_setting('report_recipient') or self._get_setting('email_recipient')
        
        if not all([smtp_server, smtp_user, smtp_password, recipient]):
            return {'success': False, 'error': 'Email settings not configured'}
        
        if subject is None:
            subject = f"🌐 Network Monitor - Daily Report ({datetime.now().strftime('%Y-%m-%d')})"
        
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = smtp_from or smtp_user
            msg['To'] = recipient
            
            # Attach HTML content
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            # Support multiple comma-separated recipients
            rcpt_list = [r.strip() for r in recipient.split(',') if r.strip()]
            
            # Send email
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.sendmail(msg['From'], rcpt_list, msg.as_string())
            
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def run_daily_report(self):
        """Generate and send the daily report"""
        print(f"[Report] Generating daily report at {datetime.now()}")
        
        # Check if reports are enabled
        if self._get_setting('reports_enabled') != 'true':
            print("[Report] Scheduled reports are disabled")
            return {'success': False, 'error': 'Reports disabled'}
        
        try:
            report_data = self.generate_daily_report()
            html_content = self.generate_html_report(report_data)
            result = self.send_report_email(html_content)
            
            if result['success']:
                print("[Report] Daily report sent successfully")
            else:
                print(f"[Report] Failed to send: {result.get('error')}")
            
            return result
        except Exception as e:
            print(f"[Report] Error generating report: {e}")
            return {'success': False, 'error': str(e)}

    def run_server_health_report(self):
        """Generate and send the configured server-health report."""
        try:
            data = self.generate_server_health_report()
            html_content = self.generate_server_health_html(data)
            recipient = self._get_setting('server_report_recipient') or None
            subject = f"Server Health Report ({datetime.now().strftime('%Y-%m-%d')})"
            return self.send_report_email(html_content, subject=subject, to_email=recipient)
        except Exception as exc:
            print(f"[Report] Error generating server health report: {exc}")
            return {'success': False, 'error': str(exc)}

    def run_scheduled_reports(self, now=None):
        """Dispatch due reports once, using settings for time and frequency."""
        now = now or datetime.now()
        if now.strftime('%H:%M') != self._get_setting('report_time', '08:00'):
            return {'success': True, 'sent': []}
        today = now.strftime('%Y-%m-%d')
        sent = []
        if self._get_setting('reports_enabled') == 'true' and self._get_setting('last_daily_report_date') != today:
            result = self.run_daily_report()
            if result.get('success'):
                self.db.save_alert_setting('last_daily_report_date', today)
                sent.append('network')
        frequency = self._get_setting('server_report_frequency', 'daily')
        weekday = int(self._get_setting('server_report_weekday', '0') or 0)
        server_due = frequency == 'daily' or (frequency == 'weekly' and now.weekday() == weekday)
        if (self._get_setting('server_reports_enabled') == 'true' and server_due
                and self._get_setting('last_server_report_date') != today):
            result = self.run_server_health_report()
            if result.get('success'):
                self.db.save_alert_setting('last_server_report_date', today)
                sent.append('server_health')
        return {'success': True, 'sent': sent}
