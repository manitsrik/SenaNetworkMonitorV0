"""
Telegram Bot Handler
Interactive bot for querying network status via Telegram
"""

import requests
import threading
import time
from datetime import datetime


class TelegramBot:
    """Handle Telegram bot interactions"""
    
    def __init__(self, db):
        self.db = db
        self.bot_token = None
        self.chat_id = None
        self.last_update_id = 0
        self.running = False
        self.poll_thread = None
        
    def _get_settings(self):
        """Get Telegram settings from database"""
        settings = {}
        for key in ['telegram_bot_token', 'telegram_chat_id', 'telegram_enabled']:
            settings[key] = self.db.get_alert_setting(key) or ''
        return settings
    
    def is_enabled(self):
        """Check if Telegram bot is enabled"""
        settings = self._get_settings()
        return (settings.get('telegram_enabled') == 'true' and 
                settings.get('telegram_bot_token') and 
                settings.get('telegram_chat_id'))
    
    def start_polling(self):
        """Start the polling thread"""
        if self.running:
            return
            
        if not self.is_enabled():
            print("[TelegramBot] Not enabled or missing settings")
            return
            
        self.running = True
        self.poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.poll_thread.start()
        print("[TelegramBot] Started polling for commands")
    
    def stop_polling(self):
        """Stop the polling thread"""
        self.running = False
        if self.poll_thread:
            self.poll_thread.join(timeout=5)
        print("[TelegramBot] Stopped polling")
    
    def _poll_loop(self):
        """Main polling loop"""
        processed_updates = set()  # Track processed update IDs
        
        while self.running:
            try:
                if not self.is_enabled():
                    time.sleep(10)
                    continue
                    
                settings = self._get_settings()
                self.bot_token = settings.get('telegram_bot_token', '').strip()
                self.chat_id = settings.get('telegram_chat_id', '').strip()
                
                updates = self._get_updates()
                
                for update in updates:
                    update_id = update.get('update_id', 0)
                    
                    # Skip if already processed
                    if update_id in processed_updates:
                        continue
                    
                    # Update last_update_id immediately
                    if update_id > self.last_update_id:
                        self.last_update_id = update_id
                    
                    # Mark as processed
                    processed_updates.add(update_id)
                    
                    # Keep set small - remove old IDs
                    if len(processed_updates) > 100:
                        min_id = min(processed_updates)
                        processed_updates.discard(min_id)
                    
                    # Process the update
                    self._process_update(update)
                    
            except Exception as e:
                print(f"[TelegramBot] Error in poll loop: {e}")
                
            time.sleep(2)  # Poll every 2 seconds
    
    def _get_updates(self):
        """Get updates from Telegram"""
        try:
            url = f'https://api.telegram.org/bot{self.bot_token}/getUpdates'
            params = {
                'offset': self.last_update_id + 1,
                'timeout': 5
            }
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if data.get('ok') and data.get('result'):
                return data['result']
            return []
        except:
            return []
    
    def _process_update(self, update):
        """Process a single update"""
        try:
            message = update.get('message', {})
            text = message.get('text', '').strip()
            chat_id = str(message.get('chat', {}).get('id', ''))
            
            # Only respond to messages from authorized chat
            if chat_id != self.chat_id:
                return
            
            if text:
                self._handle_message(text, chat_id)
                
        except Exception as e:
            print(f"[TelegramBot] Error processing update: {e}")
    
    def _handle_message(self, text, chat_id):
        """Handle messages - both commands and natural language"""
        text_lower = text.lower().strip()
        
        # Handle slash commands
        if text.startswith('/'):
            parts = text.split()
            command = parts[0].lower().replace('@senamonitor_bot', '')
            args = parts[1:] if len(parts) > 1 else []
            
            if command == '/start' or command == '/help':
                self._send_help(chat_id)
            elif command == '/status':
                self._send_status(chat_id)
            elif command == '/devices':
                self._send_devices(chat_id)
            elif command == '/down':
                self._send_down_devices(chat_id)
            elif command == '/slow':
                self._send_slow_devices(chat_id)
            elif command == '/check':
                if args:
                    self._send_device_check(chat_id, ' '.join(args))
                else:
                    self._send_message(chat_id, "❌ กรุณาระบุชื่ออุปกรณ์\nตัวอย่าง: `/check Firewall-Main`")
            else:
                self._send_message(chat_id, f"❓ ไม่รู้จักคำสั่ง: {command}\nพิมพ์ /help เพื่อดูคำสั่งทั้งหมด")
            return
        
        # Natural language Thai keywords
        status_keywords = ['สถานะ', 'ภาพรวม', 'status', 'สถานะภาพรวม', 'รายงาน', 'ดูสถานะ', 'เช็คสถานะ', 'สรุป']
        devices_keywords = ['อุปกรณ์', 'รายการ', 'devices', 'ทั้งหมด', 'ลิสต์', 'list']
        down_keywords = ['ออฟไลน์', 'offline', 'down', 'ล่ม', 'ไม่ทำงาน', 'หยุด', 'ดับ', 'ใช้งานไม่ได้']
        slow_keywords = ['ช้า', 'slow', 'หน่วง', 'lag', 'แลค']
        help_keywords = ['ช่วยเหลือ', 'help', 'คำสั่ง', 'วิธีใช้', 'ใช้ยังไง', 'สอน']
        check_keywords = ['เช็ค', 'check', 'ดู', 'ตรวจ', 'หา']
        
        # Device type keywords
        type_keywords = ['router', 'switch', 'firewall', 'server', 'wireless', 'ap', 'camera', 
                        'เราเตอร์', 'สวิตช์', 'ไฟร์วอลล์', 'เซิฟเวอร์']
        
        # Location type keywords
        cloud_keywords = ['cloud', 'คลาวด์', 'azure', 'aws', 'gcp']
        onprem_keywords = ['on-premise', 'onprem', 'ออนพรีม', 'ในองค์กร', 'local']
        
        # Check for device check (e.g., "เช็ค Firewall" or "ดู Router-Main")
        for keyword in check_keywords:
            if text_lower.startswith(keyword):
                device_name = text[len(keyword):].strip()
                if device_name:
                    self._send_device_check(chat_id, device_name)
                    return
        
        # Check for type filter (e.g., "router", "switch")
        for type_kw in type_keywords:
            if type_kw in text_lower:
                self._send_devices_by_type(chat_id, type_kw)
                return
        
        # Check for location type filter
        if any(kw in text_lower for kw in cloud_keywords):
            self._send_devices_by_location_type(chat_id, 'cloud')
            return
        elif any(kw in text_lower for kw in onprem_keywords):
            self._send_devices_by_location_type(chat_id, 'on-premise')
            return
        
        # Check keywords and respond
        if any(kw in text_lower for kw in status_keywords):
            self._send_status(chat_id)
        elif any(kw in text_lower for kw in down_keywords):
            self._send_down_devices(chat_id)
        elif any(kw in text_lower for kw in slow_keywords):
            self._send_slow_devices(chat_id)
        elif any(kw in text_lower for kw in devices_keywords):
            self._send_devices(chat_id)
        elif any(kw in text_lower for kw in help_keywords):
            self._send_help(chat_id)
        else:
            # Try to find device by name or location
            devices = self.db.get_all_devices()
            matching = [d for d in devices if text_lower in d['name'].lower()]
            
            # Also try matching by location/zone
            if not matching:
                matching = [d for d in devices if d.get('location') and text_lower in d['location'].lower()]
            
            if matching:
                if len(matching) == 1:
                    self._send_device_check(chat_id, matching[0]['name'])
                else:
                    self._send_devices_filtered(chat_id, matching, f"🔍 '{text}'")
            else:
                # Unknown message - provide hint
                self._send_message(chat_id, 
                    "🤔 ไม่เข้าใจคำสั่ง\n\n"
                    "*ลองพิมพ์:*\n"
                    "• `สถานะ` - ดูภาพรวม\n"
                    "• `ออฟไลน์` - ดูอุปกรณ์ที่ดับ\n"
                    "• `router` - ดูเฉพาะ Router\n"
                    "• `cloud` - ดูอุปกรณ์บน Cloud\n"
                    "• `เช็ค Firewall` - ดูอุปกรณ์\n"
                    "• `/help` - ดูคำสั่งทั้งหมด"
                )

    
    def _send_message(self, chat_id, text, parse_mode='Markdown'):
        """Send a message to Telegram"""
        try:
            url = f'https://api.telegram.org/bot{self.bot_token}/sendMessage'
            data = {
                'chat_id': chat_id,
                'text': text,
                'parse_mode': parse_mode
            }
            requests.post(url, data=data, timeout=10)
        except Exception as e:
            print(f"[TelegramBot] Error sending message: {e}")
    
    def _send_help(self, chat_id):
        """Send help message"""
        help_text = """🤖 *Network Monitor Bot*

*พิมพ์ได้ตามใจ:*

📊 `สถานะ` `ภาพรวม` - ดูสรุป
❌ `ออฟไลน์` `ล่ม` - อุปกรณ์ดับ
⚠️ `ช้า` - อุปกรณ์ช้า

*กรองตามประเภท:*
📦 `router` `switch` `firewall` `server`

*กรองตาม Location:*
☁️ `cloud` - บน Cloud
🏢 `on-premise` - ในองค์กร

*เช็คอุปกรณ์:*
🔍 `เช็ค [ชื่อ]` หรือพิมพ์ชื่อตรงๆ

━━━━━━━━━━━━━━━
_SENA Network Monitor_"""
        self._send_message(chat_id, help_text)
    
    def _send_status(self, chat_id):
        """Send overall network status"""
        try:
            devices = self.db.get_all_devices()
            
            total = len(devices)
            online = sum(1 for d in devices if d.get('status') == 'up')
            offline = sum(1 for d in devices if d.get('status') == 'down')
            slow = sum(1 for d in devices if d.get('status') == 'slow')
            unknown = total - online - offline - slow
            
            # Calculate uptime percentage
            uptime = (online / total * 100) if total > 0 else 0
            
            status_text = f"""📊 *Network Status*

✅ Online: *{online}* อุปกรณ์
❌ Offline: *{offline}* อุปกรณ์
⚠️ Slow: *{slow}* อุปกรณ์
❓ Unknown: *{unknown}* อุปกรณ์

━━━━━━━━━━━━━━━
📈 Uptime: *{uptime:.1f}%*
📱 Total Devices: *{total}*
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
            
            self._send_message(chat_id, status_text)
            
        except Exception as e:
            self._send_message(chat_id, f"❌ Error: {e}")
    
    def _send_devices(self, chat_id):
        """Send device list"""
        try:
            devices = self.db.get_all_devices()
            
            if not devices:
                self._send_message(chat_id, "📋 ไม่มีอุปกรณ์ในระบบ")
                return
            
            # Group by status
            online_devices = [d for d in devices if d.get('status') == 'up']
            offline_devices = [d for d in devices if d.get('status') == 'down']
            slow_devices = [d for d in devices if d.get('status') == 'slow']
            
            text = "📋 *รายการอุปกรณ์*\n\n"
            
            if offline_devices:
                text += "❌ *Offline:*\n"
                for d in offline_devices[:10]:
                    text += f"  • {d['name']}\n"
                if len(offline_devices) > 10:
                    text += f"  _...และอีก {len(offline_devices)-10} อุปกรณ์_\n"
                text += "\n"
            
            if slow_devices:
                text += "⚠️ *Slow:*\n"
                for d in slow_devices[:10]:
                    rt = d.get('response_time', 0) or 0
                    text += f"  • {d['name']} ({rt}ms)\n"
                if len(slow_devices) > 10:
                    text += f"  _...และอีก {len(slow_devices)-10} อุปกรณ์_\n"
                text += "\n"
            
            text += f"✅ *Online:* {len(online_devices)} อุปกรณ์\n"
            text += f"\n━━━━━━━━━━━━━━━\n"
            text += f"📱 Total: {len(devices)} | ⏰ {datetime.now().strftime('%H:%M:%S')}"
            
            self._send_message(chat_id, text)
            
        except Exception as e:
            self._send_message(chat_id, f"❌ Error: {e}")
    
    def _send_down_devices(self, chat_id):
        """Send list of offline devices"""
        try:
            devices = self.db.get_all_devices()
            down_devices = [d for d in devices if d.get('status') == 'down']
            
            if not down_devices:
                self._send_message(chat_id, "✅ *ไม่มีอุปกรณ์ Offline*\n\nอุปกรณ์ทั้งหมดออนไลน์อยู่!")
                return
            
            text = f"❌ *อุปกรณ์ Offline ({len(down_devices)})*\n\n"
            
            for d in down_devices:
                text += f"🔴 *{d['name']}*\n"
                text += f"   IP: `{d.get('ip_address', 'N/A')}`\n"
                text += f"   Type: {d.get('device_type', 'N/A')}\n"
                if d.get('zone'):
                    text += f"   Zone: {d['zone']}\n"
                text += "\n"
            
            text += f"━━━━━━━━━━━━━━━\n"
            text += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            self._send_message(chat_id, text)
            
        except Exception as e:
            self._send_message(chat_id, f"❌ Error: {e}")
    
    def _send_slow_devices(self, chat_id):
        """Send list of slow devices"""
        try:
            devices = self.db.get_all_devices()
            slow_devices = [d for d in devices if d.get('status') == 'slow']
            
            if not slow_devices:
                self._send_message(chat_id, "✅ *ไม่มีอุปกรณ์ที่ช้า*\n\nทุกอุปกรณ์ตอบสนองเร็วดี!")
                return
            
            # Sort by response time descending
            slow_devices.sort(key=lambda x: x.get('response_time', 0) or 0, reverse=True)
            
            text = f"⚠️ *อุปกรณ์ที่ช้า ({len(slow_devices)})*\n\n"
            
            for d in slow_devices:
                rt = d.get('response_time', 0) or 0
                text += f"🟡 *{d['name']}* - {rt}ms\n"
                text += f"   IP: `{d.get('ip_address', 'N/A')}`\n"
            
            text += f"\n━━━━━━━━━━━━━━━\n"
            text += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            self._send_message(chat_id, text)
            
        except Exception as e:
            self._send_message(chat_id, f"❌ Error: {e}")
    
    def _send_device_check(self, chat_id, device_name):
        """Check and send status of specific device"""
        try:
            devices = self.db.get_all_devices()
            
            # Normalize search term (remove spaces, dashes, lowercase)
            search_term = device_name.lower().strip()
            search_normalized = search_term.replace(' ', '').replace('-', '').replace('_', '')
            
            matching = []
            
            # Strategy 1: Exact substring match in name
            for d in devices:
                name_lower = d['name'].lower()
                if search_term in name_lower:
                    matching.append(d)
                    continue
                    
                # Strategy 2: Normalized match (ignore spaces/dashes)
                name_normalized = name_lower.replace(' ', '').replace('-', '').replace('_', '')
                if search_normalized in name_normalized:
                    matching.append(d)
                    continue
                
                # Strategy 3: Match by IP address
                if d.get('ip_address') and search_term in d['ip_address']:
                    matching.append(d)
                    continue
                
                # Strategy 4: Match by device type
                if d.get('device_type') and search_term in d['device_type'].lower():
                    matching.append(d)
                    continue
                
                # Strategy 5: Match by location/zone
                if d.get('location') and search_term in d['location'].lower():
                    matching.append(d)
                    continue
                    
                # Strategy 6: Word-by-word partial match
                search_words = search_term.split()
                if len(search_words) > 1:
                    name_words = name_lower.replace('-', ' ').replace('_', ' ').split()
                    if all(any(sw in nw for nw in name_words) for sw in search_words):
                        matching.append(d)
            
            # Remove duplicates while preserving order
            seen = set()
            unique_matching = []
            for d in matching:
                if d['id'] not in seen:
                    seen.add(d['id'])
                    unique_matching.append(d)
            matching = unique_matching
            
            # Fallback: if no matches and multiple words, try OR matching (any word matches)
            if not matching and ' ' in search_term:
                search_words = search_term.split()
                for d in devices:
                    name_lower = d['name'].lower()
                    name_normalized = name_lower.replace(' ', '').replace('-', '').replace('_', '')
                    for sw in search_words:
                        sw_norm = sw.replace(' ', '').replace('-', '').replace('_', '')
                        if sw in name_lower or sw_norm in name_normalized:
                            if d['id'] not in seen:
                                seen.add(d['id'])
                                matching.append(d)
                            break
            
            if not matching:
                self._send_message(chat_id, f"❌ ไม่พบอุปกรณ์: *{device_name}*\n\nลองพิมพ์ `อุปกรณ์` เพื่อดูรายการทั้งหมด")
                return
            
            if len(matching) > 1:
                text = f"🔍 พบ *{len(matching)}* อุปกรณ์ที่ตรงกับ '{device_name}':\n\n"
                for d in matching[:10]:
                    status_emoji = {'up': '✅', 'down': '❌', 'slow': '⚠️'}.get(d.get('status'), '❓')
                    text += f"  {status_emoji} {d['name']}\n"
                if len(matching) > 10:
                    text += f"  _...และอีก {len(matching)-10} อุปกรณ์_\n"
                text += f"\nพิมพ์ชื่อเต็มเพื่อดูรายละเอียด"
                self._send_message(chat_id, text)
                return
            
            device = matching[0]
            status = device.get('status', 'unknown')
            status_emoji = {'up': '✅', 'down': '❌', 'slow': '⚠️'}.get(status, '❓')
            status_text = {'up': 'Online', 'down': 'Offline', 'slow': 'Slow'}.get(status, 'Unknown')
            
            rt = device.get('response_time')
            rt_text = f"{rt}ms" if rt is not None else "N/A"
            
            text = f"""🔍 *{device['name']}*

{status_emoji} Status: *{status_text}*
🌐 IP: `{device.get('ip_address', 'N/A')}`
⏱️ Response: *{rt_text}*
📦 Type: {device.get('device_type', 'N/A')}
🏢 Zone: {device.get('zone', 'N/A')}
🔌 Port: {device.get('port', 'N/A')}

━━━━━━━━━━━━━━━
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
            
            self._send_message(chat_id, text)
            
        except Exception as e:
            self._send_message(chat_id, f"❌ Error: {e}")
    
    def _send_devices_by_type(self, chat_id, device_type):
        """Send list of devices filtered by type"""
        try:
            devices = self.db.get_all_devices()
            
            # Filter by device type (case-insensitive partial match)
            type_lower = device_type.lower()
            filtered = [d for d in devices if d.get('device_type') and type_lower in d['device_type'].lower()]
            
            if not filtered:
                self._send_message(chat_id, f"📦 ไม่พบอุปกรณ์ประเภท: *{device_type}*")
                return
            
            self._send_devices_filtered(chat_id, filtered, f"📦 Type: {device_type.upper()}")
            
        except Exception as e:
            self._send_message(chat_id, f"❌ Error: {e}")
    
    def _send_devices_by_location_type(self, chat_id, location_type):
        """Send list of devices filtered by location type (cloud/on-premise)"""
        try:
            devices = self.db.get_all_devices()
            
            # Filter by location type
            filtered = [d for d in devices if d.get('location_type') == location_type]
            
            label = "☁️ Cloud" if location_type == 'cloud' else "🏢 On-Premise"
            
            if not filtered:
                self._send_message(chat_id, f"{label}: ไม่พบอุปกรณ์")
                return
            
            self._send_devices_filtered(chat_id, filtered, label)
            
        except Exception as e:
            self._send_message(chat_id, f"❌ Error: {e}")
    
    def _send_devices_filtered(self, chat_id, devices, title):
        """Send a filtered list of devices"""
        try:
            online = sum(1 for d in devices if d.get('status') == 'up')
            offline = sum(1 for d in devices if d.get('status') == 'down')
            slow = sum(1 for d in devices if d.get('status') == 'slow')
            
            text = f"*{title}*\n\n"
            text += f"📊 สรุป: ✅ {online} | ❌ {offline} | ⚠️ {slow}\n\n"
            
            # Show offline first
            offline_devices = [d for d in devices if d.get('status') == 'down']
            if offline_devices:
                text += "❌ *Offline:*\n"
                for d in offline_devices[:8]:
                    text += f"  • {d['name']}\n"
                if len(offline_devices) > 8:
                    text += f"  _+{len(offline_devices)-8} more_\n"
                text += "\n"
            
            # Show slow
            slow_devices = [d for d in devices if d.get('status') == 'slow']
            if slow_devices:
                text += "⚠️ *Slow:*\n"
                for d in slow_devices[:5]:
                    rt = d.get('response_time', 0) or 0
                    text += f"  • {d['name']} ({rt}ms)\n"
                if len(slow_devices) > 5:
                    text += f"  _+{len(slow_devices)-5} more_\n"
                text += "\n"
            
            # Summary of online
            online_devices = [d for d in devices if d.get('status') == 'up']
            if online_devices:
                text += f"✅ *Online:* {len(online_devices)} อุปกรณ์\n"
            
            text += f"\n━━━━━━━━━━━━━━━\n"
            text += f"📱 Total: {len(devices)} | ⏰ {datetime.now().strftime('%H:%M:%S')}"
            
            self._send_message(chat_id, text)
            
        except Exception as e:
            self._send_message(chat_id, f"❌ Error: {e}")
