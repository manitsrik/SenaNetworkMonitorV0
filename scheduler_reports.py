"""
Scheduled Reports Module for Network Monitor
Generates and sends daily email summaries of network status
"""
import smtplib
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
    
    def send_report_email(self, html_content, subject=None):
        """Send the report via email"""
        smtp_server = self._get_setting('smtp_server')
        smtp_port = int(self._get_setting('smtp_port', 587))
        smtp_user = self._get_setting('smtp_user')
        smtp_password = self._get_setting('smtp_password')
        smtp_from = self._get_setting('smtp_from')
        recipient = self._get_setting('report_recipient') or self._get_setting('email_recipient')
        
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
            
            # Send email
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.sendmail(msg['From'], [recipient], msg.as_string())
            
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
