"""
Read-only assistant service for dashboard and website Q&A.
Answers are generated from live application data without external LLM calls.
"""
from datetime import datetime
from difflib import SequenceMatcher
import re


class AssistantService:
    FOLLOW_UP_TERMS = [
        "\u0e41\u0e25\u0e49\u0e27", "\u0e40\u0e09\u0e1e\u0e32\u0e30", "\u0e2a\u0e48\u0e27\u0e19", "\u0e02\u0e2d", "\u0e02\u0e2d\u0e07\u0e17\u0e35\u0e48", "\u0e17\u0e35\u0e48\u0e25\u0e48\u0e30", "\u0e25\u0e48\u0e30",
        "then", "what about", "how about", "and", "only", "just", "those", "them", "same",
    ]
    CONTEXTUAL_LOCATION_TERMS = [
        "\u0e17\u0e35\u0e48\u0e19\u0e35\u0e48", "\u0e17\u0e35\u0e48\u0e19\u0e31\u0e48\u0e19", "\u0e2a\u0e32\u0e02\u0e32\u0e19\u0e35\u0e49", "\u0e08\u0e38\u0e14\u0e19\u0e35\u0e49",
        "here", "there", "that branch", "that site", "this branch", "this site",
    ]
    CONTEXTUAL_DEVICE_TERMS = [
        "\u0e2d\u0e31\u0e19\u0e19\u0e31\u0e49\u0e19", "\u0e15\u0e31\u0e27\u0e19\u0e31\u0e49\u0e19", "\u0e15\u0e31\u0e27\u0e40\u0e21\u0e37\u0e48\u0e2d\u0e01\u0e35\u0e49", "\u0e17\u0e35\u0e48\u0e40\u0e21\u0e37\u0e48\u0e2d\u0e01\u0e35\u0e49",
        "\u0e15\u0e31\u0e27\u0e41\u0e23\u0e01", "\u0e15\u0e31\u0e27\u0e16\u0e31\u0e14\u0e44\u0e1b", "\u0e15\u0e31\u0e27\u0e2a\u0e38\u0e14\u0e17\u0e49\u0e32\u0e22",
        "that one", "this one", "the first one", "first one", "next one", "last one", "previous one", "the one before", "that device",
    ]
    THAI_DOWN = "\u0e25\u0e48\u0e21"
    THAI_DOWN_ALT = "\u0e14\u0e31\u0e1a"
    THAI_SLOW = "\u0e0a\u0e49\u0e32"
    THAI_NORMAL = "\u0e1b\u0e01\u0e15\u0e34"
    THAI_ONLINE = "\u0e2d\u0e2d\u0e19\u0e44\u0e25\u0e19\u0e4c"
    THAI_HELP = "\u0e0a\u0e48\u0e27\u0e22"
    THAI_ASK = "\u0e16\u0e32\u0e21\u0e2d\u0e30\u0e44\u0e23\u0e44\u0e14\u0e49"
    THAI_STATUS = "\u0e2a\u0e16\u0e32\u0e19\u0e30"
    THAI_DEVICE = "\u0e2d\u0e38\u0e1b\u0e01\u0e23\u0e13\u0e4c"
    THAI_SUMMARY = "\u0e2a\u0e23\u0e38\u0e1b"
    THAI_OVERVIEW = "\u0e20\u0e32\u0e1e\u0e23\u0e27\u0e21"
    THAI_ALL = "\u0e17\u0e31\u0e49\u0e07\u0e2b\u0e21\u0e14"
    THAI_WHAT = "\u0e21\u0e35\u0e2d\u0e30\u0e44\u0e23\u0e1a\u0e49\u0e32\u0e07"
    THAI_NOW = "\u0e15\u0e2d\u0e19\u0e19\u0e35\u0e49"
    THAI_LATEST = "\u0e25\u0e48\u0e32\u0e2a\u0e38\u0e14"
    THAI_INCIDENT = "\u0e40\u0e2b\u0e15\u0e38\u0e01\u0e32\u0e23\u0e13\u0e4c"
    THAI_PROBLEM = "\u0e1b\u0e31\u0e0d\u0e2b\u0e32"
    THAI_ANOMALY = "\u0e1c\u0e34\u0e14\u0e1b\u0e01\u0e15\u0e34"
    THAI_ALERT = "\u0e41\u0e08\u0e49\u0e07\u0e40\u0e15\u0e37\u0e2d\u0e19"
    THAI_TRAFFIC = "\u0e17\u0e23\u0e32\u0e1f\u0e1f\u0e34\u0e01"
    THAI_CHECK = "\u0e15\u0e23\u0e27\u0e08\u0e2a\u0e2d\u0e1a"
    THAI_CHECK_ALT = "\u0e40\u0e0a\u0e47\u0e01"
    THAI_CHECK_ALT2 = "\u0e40\u0e0a\u0e04"
    THAI_ROUTER = "\u0e40\u0e23\u0e32\u0e40\u0e15\u0e2d\u0e23\u0e4c"
    THAI_SWITCH = "\u0e2a\u0e27\u0e34\u0e15\u0e0a\u0e4c"
    THAI_SERVER = "\u0e40\u0e0b\u0e34\u0e23\u0e4c\u0e1f\u0e40\u0e27\u0e2d\u0e23\u0e4c"
    THAI_FIREWALL = "\u0e44\u0e1f\u0e23\u0e4c\u0e27\u0e2d\u0e25\u0e25\u0e4c"
    THAI_YES = "\u0e43\u0e0a\u0e49"
    THAI_NO = "\u0e44\u0e21\u0e48"

    NOISE_TERMS = {
        "a", "an", "the", "is", "are", "was", "were", "be", "to", "for", "of",
        "about", "please", "pls", "plz", "can", "could", "would", "you", "me",
        "show", "tell", "give", "need", "want", "know", "now", "today", "current",
        "currently", "right", "moment", "latest", "recent", "there", "any", "what",
        "which", "how", "many", "list", "some", "all", "just", "maybe", "kindly",
    }

    PHRASE_ALIASES = {
        "whats down": "down devices",
        "what's down": "down devices",
        "what is down": "down devices",
        "anything down": "down devices",
        "anything wrong": "problem devices",
        "what is wrong": "problem devices",
        "whats wrong": "problem devices",
        "what's wrong": "problem devices",
        "having issues": "problem devices",
        "having trouble": "problem devices",
        "need attention": "problem devices",
        "not healthy": "slow devices",
        "show me": "",
        "can you": "",
        "could you": "",
        "right now": "",
        "at the moment": "",
    }

    PROBLEM_TERMS = [
        "problem", "problems", "issue", "issues", "wrong", "broken", "failing",
        "failed", "trouble", "unstable", "critical", "alerting",
        THAI_PROBLEM,
    ]

    STATUS_TERMS = {
        "down": ["down", "offline", "outage", "critical", THAI_DOWN, THAI_DOWN_ALT],
        "slow": ["slow", "latency", "sluggish", THAI_SLOW],
        "up": ["up", "online", "healthy", THAI_NORMAL, THAI_ONLINE],
    }

    DEVICE_TYPE_ALIASES = {
        "router": ["router", "routers", THAI_ROUTER],
        "switch": ["switch", "switches", THAI_SWITCH, "switching"],
        "server": ["server", "servers", THAI_SERVER],
        "firewall": ["firewall", "firewalls", THAI_FIREWALL],
        "access point": ["access point", "ap", "wifi ap"],
    }

    MONITOR_TYPE_ALIASES = {
        "snmp": ["snmp"],
        "ping": ["ping", "icmp"],
        "http": ["http", "website", "web"],
        "tcp": ["tcp", "port"],
        "dns": ["dns"],
        "ssh": ["ssh"],
        "winrm": ["winrm", "wmi"],
    }

    HELP_QUICK_REPLIES = [
        f"{THAI_SUMMARY}\u0e23\u0e30\u0e1a\u0e1a{THAI_NOW}",
        f"\u0e21\u0e35{THAI_DEVICE} down {THAI_WHAT}",
        f"switch down {THAI_WHAT}",
        f"{THAI_STATUS} Branch A",
        f"top bandwidth {THAI_NOW}",
        f"\u0e21\u0e35 anomaly {THAI_WHAT}",
    ]

    def __init__(self, db):
        self.db = db
        self._locale = "th"

    def answer(self, question, context=None):
        prompt = (question or "").strip()
        previous_locale = self._locale
        self._locale = self._detect_locale(prompt)
        try:
            if not prompt:
                return self._response(
                    intent="empty",
                    answer=self._locale_text(
                        "\u0e2a\u0e2d\u0e1a\u0e16\u0e32\u0e21\u0e44\u0e14\u0e49\u0e40\u0e01\u0e35\u0e48\u0e22\u0e27\u0e01\u0e31\u0e1a\u0e2d\u0e38\u0e1b\u0e01\u0e23\u0e13\u0e4c, \u0e01\u0e32\u0e23\u0e41\u0e08\u0e49\u0e07\u0e40\u0e15\u0e37\u0e2d\u0e19, incident, anomaly, bandwidth \u0e2b\u0e23\u0e37\u0e2d SLA \u0e44\u0e14\u0e49\u0e40\u0e25\u0e22",
                        "Ask about devices, alerts, incidents, anomalies, bandwidth, or SLA.",
                    ),
                    sources=[],
                )

            normalized = self._normalize(prompt)
            devices = self.db.get_all_devices()
            filters = self._extract_filters(normalized, devices)
            effective_context = self._normalize_context(context)
            filters = self._merge_context_filters(normalized, filters, effective_context)

            direct_response = (
                self._try_device_action(normalized, devices, effective_context)
                or self._try_device_status(normalized, devices, effective_context)
                or self._try_named_device_detail(normalized, devices, effective_context)
                or self._try_location_summary(filters, devices)
                or self._try_filtered_device_summary(normalized, devices, filters, effective_context)
            )
            if direct_response:
                return self._with_context(direct_response, filters)

            if self._matches_any(normalized, ["help", "bot", "assistant", self.THAI_HELP, self.THAI_ASK]):
                return self._with_context(self._help_response(), filters)
            if self._matches_any(normalized, ["incident", "incidents", self.THAI_INCIDENT, self.THAI_PROBLEM]):
                return self._with_context(self._incident_summary(filters), filters)
            if self._matches_any(normalized, ["anomaly", "anomalies", self.THAI_ANOMALY]):
                return self._with_context(self._anomaly_summary(filters), filters)
            if self._matches_any(normalized, ["alert", "alerts", self.THAI_ALERT]):
                return self._with_context(self._alert_summary(filters), filters)
            if self._matches_any(normalized, ["bandwidth", "traffic", "interface", self.THAI_TRAFFIC]):
                return self._with_context(self._bandwidth_summary(filters), filters)
            if self._matches_any(normalized, ["sla", "uptime"]):
                return self._with_context(self._sla_summary(filters), filters)
            if self._matches_any(normalized, ["summary", "overview", "status", self.THAI_SUMMARY, self.THAI_OVERVIEW, self.THAI_ALL]):
                return self._with_context(self._device_summary(devices, filters=filters), filters)

            return self._with_context(self._help_response(prefix=self._locale_text(
                "\u0e22\u0e31\u0e07\u0e15\u0e35\u0e04\u0e27\u0e32\u0e21\u0e04\u0e33\u0e16\u0e32\u0e21\u0e19\u0e35\u0e49\u0e44\u0e21\u0e48\u0e44\u0e14\u0e49\u0e0a\u0e31\u0e14\u0e40\u0e08\u0e19 \u0e25\u0e2d\u0e07\u0e16\u0e32\u0e21\u0e15\u0e32\u0e21\u0e15\u0e31\u0e27\u0e2d\u0e22\u0e48\u0e32\u0e07\u0e14\u0e49\u0e32\u0e19\u0e25\u0e48\u0e32\u0e07\u0e44\u0e14\u0e49",
                "I could not map that question clearly yet. Try one of the example prompts below.",
            )), filters)
        finally:
            self._locale = previous_locale

    def _response(self, intent, answer, sources, quick_replies=None, actions=None, links=None, context_updates=None, device_details=None):
        return {
            "success": True,
            "intent": intent,
            "answer": answer,
            "sources": sources,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "quick_replies": quick_replies or self._quick_replies(),
            "actions": actions or [],
            "links": links or [],
            "context_updates": context_updates or {},
            "device_details": device_details,
        }

    def _with_context(self, response, filters):
        updates = response.pop("context_updates", {}) or {}
        response["context"] = {
            "filters": {
                "status": filters.get("status"),
                "device_type": filters.get("device_type"),
                "monitor_type": filters.get("monitor_type"),
                "location": filters.get("location"),
            },
            "intent": response.get("intent"),
            "locale": self._locale,
            "last_device": updates.get("last_device"),
            "recent_devices": updates.get("recent_devices", []),
        }
        return response

    def _normalize_context(self, context):
        context = context or {}
        filters = context.get("filters") or {}
        return {
            "filters": {
                "status": filters.get("status"),
                "device_type": filters.get("device_type"),
                "monitor_type": filters.get("monitor_type"),
                "location": filters.get("location"),
            },
            "intent": context.get("intent"),
            "locale": context.get("locale"),
            "last_device": context.get("last_device"),
            "recent_devices": context.get("recent_devices") or [],
        }

    def _is_follow_up_prompt(self, normalized):
        if self._matches_any(normalized, self.FOLLOW_UP_TERMS):
            return True
        tokens = normalized.split()
        return len(tokens) <= 5 and any(token in {"hq", "branch", "site"} for token in tokens)

    def _merge_context_filters(self, normalized, filters, context):
        previous_filters = (context or {}).get("filters") or {}
        if not previous_filters:
            return filters

        merged = dict(filters)
        if self._matches_any(normalized, self.CONTEXTUAL_LOCATION_TERMS) and previous_filters.get("location"):
            merged["location"] = previous_filters.get("location")

        if not self._is_follow_up_prompt(normalized):
            return merged

        for key in ("location", "device_type", "monitor_type"):
            if not merged.get(key) and previous_filters.get(key):
                merged[key] = previous_filters.get(key)
        if not merged.get("status") and previous_filters.get("status"):
            merged["status"] = previous_filters.get("status")
        return merged

    def _context_recent_devices(self, context):
        return (context or {}).get("recent_devices") or []

    def _is_device_only_prompt(self, normalized, device):
        normalized_name = self._normalize(device.get("name") or "")
        normalized_ip = self._normalize(device.get("ip_address") or "")
        lookup_values = [value for value in self._device_lookup_values(device) if value]
        if not normalized_name:
            return normalized in lookup_values
        compact_prompt = self._strip_noise(normalized)
        if normalized == normalized_name or compact_prompt == normalized_name:
            return True
        if normalized_ip and (normalized == normalized_ip or compact_prompt == normalized_ip):
            return True
        if any(compact_prompt == value or normalized == value for value in lookup_values):
            return True
        prompt_tokens = compact_prompt.split()
        name_tokens = normalized_name.split()
        if len(prompt_tokens) <= max(4, len(name_tokens) + 1) and all(token in compact_prompt for token in name_tokens):
            return True
        return False

    def _resolve_contextual_device(self, normalized, devices, context):
        context = context or {}
        recent_devices = self._context_recent_devices(context)
        if not recent_devices:
            last_device = context.get("last_device")
            if last_device:
                recent_devices = [last_device]
        if not recent_devices:
            return []

        by_id = {device.get("id"): device for device in devices if device.get("id")}
        candidates = [by_id.get(item.get("id")) for item in recent_devices if by_id.get(item.get("id"))]
        if not candidates:
            return []

        if self._matches_any(normalized, ["\u0e15\u0e31\u0e27\u0e41\u0e23\u0e01", "the first one", "first one"]):
            return [candidates[0]]
        if self._matches_any(normalized, ["\u0e15\u0e31\u0e27\u0e16\u0e31\u0e14\u0e44\u0e1b", "next one"]):
            return [candidates[1]] if len(candidates) > 1 else [candidates[0]]
        if self._matches_any(normalized, ["\u0e15\u0e31\u0e27\u0e2a\u0e38\u0e14\u0e17\u0e49\u0e32\u0e22", "last one"]):
            return [candidates[-1]]
        if self._matches_any(normalized, ["previous one", "the one before"]):
            return [candidates[-2]] if len(candidates) > 1 else [candidates[0]]
        if self._matches_any(normalized, self.CONTEXTUAL_DEVICE_TERMS):
            last_device = context.get("last_device")
            if last_device and by_id.get(last_device.get("id")):
                return [by_id[last_device.get("id")]]
            return [candidates[0]]
        return []

    def _detect_locale(self, prompt):
        prompt = str(prompt or "")
        thai_chars = len(re.findall(r"[\u0e00-\u0e7f]", prompt))
        latin_chars = len(re.findall(r"[A-Za-z]", prompt))
        if thai_chars > 0:
            return "th"
        return "en" if latin_chars > 0 else "th"

    def _is_thai_locale(self):
        return self._locale == "th"

    def _locale_text(self, thai_text, english_text):
        return thai_text if self._is_thai_locale() else english_text

    def _quick_replies(self):
        if self._is_thai_locale():
            return list(self.HELP_QUICK_REPLIES)
        return [
            "System summary now",
            "What devices are down?",
            "Show down switches",
            "Status for Branch A",
            "Top bandwidth right now",
            "Any anomalies right now?",
        ]

    def _display_device_type(self, value):
        normalized = self._normalize(value)
        if not self._is_thai_locale():
            return value or "-"
        mapping = {
            "router": self.THAI_ROUTER,
            "switch": self.THAI_SWITCH,
            "server": self.THAI_SERVER,
            "firewall": self.THAI_FIREWALL,
            "access point": "\u0e08\u0e38\u0e14\u0e01\u0e23\u0e30\u0e08\u0e32\u0e22\u0e2a\u0e31\u0e0d\u0e0d\u0e32\u0e13",
        }
        return mapping.get(normalized, value or "-")

    def _display_monitor_type(self, value):
        normalized = self._normalize(value)
        if not self._is_thai_locale():
            return value or "-"
        mapping = {
            "snmp": "SNMP",
            "ping": "Ping",
            "icmp": "Ping",
            "http": "HTTP",
            "tcp": "TCP",
            "dns": "DNS",
            "ssh": "SSH",
            "winrm": "WinRM",
            "wmi": "WMI",
        }
        return mapping.get(normalized, value or "-")

    def _display_severity(self, value):
        normalized = self._normalize(value)
        if not self._is_thai_locale():
            return value or "-"
        mapping = {
            "critical": "\u0e27\u0e34\u0e01\u0e24\u0e15",
            "warning": "\u0e40\u0e15\u0e37\u0e2d\u0e19",
            "info": "\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25",
            "minor": "\u0e40\u0e25\u0e47\u0e01\u0e19\u0e49\u0e2d\u0e22",
            "major": "\u0e23\u0e38\u0e19\u0e41\u0e23\u0e07",
        }
        return mapping.get(normalized, value or "-")

    def _display_anomaly_type(self, value):
        normalized = self._normalize(value)
        if not self._is_thai_locale():
            return value or "-"
        normalized = normalized.replace("-", "_").replace(" ", "_")
        mapping = {
            "response_time": "\u0e40\u0e27\u0e25\u0e32\u0e15\u0e2d\u0e1a\u0e2a\u0e19\u0e2d\u0e07\u0e1c\u0e34\u0e14\u0e1b\u0e01\u0e15\u0e34",
            "packet_loss": "\u0e01\u0e32\u0e23\u0e2a\u0e39\u0e0d\u0e2b\u0e32\u0e22\u0e02\u0e2d\u0e07 packet",
            "bandwidth": "Bandwidth \u0e1c\u0e34\u0e14\u0e1b\u0e01\u0e15\u0e34",
            "cpu": "CPU \u0e1c\u0e34\u0e14\u0e1b\u0e01\u0e15\u0e34",
            "memory": "Memory \u0e1c\u0e34\u0e14\u0e1b\u0e01\u0e15\u0e34",
        }
        if normalized in mapping:
            return mapping[normalized]
        compact = normalized.replace("_", "")
        for key, label in mapping.items():
            if compact == key.replace("_", ""):
                return label
        return value or "-"

    def _device_detail_segments(self, device, response_text):
        thai_segments = [
            f"IP: {device.get('ip_address', '-')}",
            f"\u0e1b\u0e23\u0e30\u0e40\u0e20\u0e17: {self._display_device_type(device.get('device_type'))}",
            f"\u0e21\u0e2d\u0e19\u0e34\u0e40\u0e15\u0e2d\u0e23\u0e4c: {self._display_monitor_type(device.get('monitor_type'))}",
        ]
        english_segments = [
            f"IP: {device.get('ip_address', '-')}",
            f"type: {device.get('device_type') or '-'}",
            f"monitor: {device.get('monitor_type') or '-'}",
        ]

        optional_fields = [
            ("location", "\u0e2a\u0e16\u0e32\u0e19\u0e17\u0e35\u0e48", "location"),
            ("site", "\u0e44\u0e0b\u0e15\u0e4c", "site"),
            ("vendor", "\u0e22\u0e35\u0e48\u0e2b\u0e49\u0e2d", "vendor"),
            ("brand", "\u0e22\u0e35\u0e48\u0e2b\u0e49\u0e2d", "brand"),
            ("model", "\u0e23\u0e38\u0e48\u0e19", "model"),
            ("serial_number", "\u0e2b\u0e21\u0e32\u0e22\u0e40\u0e25\u0e02 serial", "serial"),
            ("serial", "\u0e2b\u0e21\u0e32\u0e22\u0e40\u0e25\u0e02 serial", "serial"),
        ]
        seen_labels = set()
        for key, thai_label, english_label in optional_fields:
            value = device.get(key)
            if not value or english_label in seen_labels:
                continue
            thai_segments.append(f"{thai_label}: {value}")
            english_segments.append(f"{english_label}: {value}")
            seen_labels.add(english_label)

        thai_segments.extend([
            f"\u0e40\u0e27\u0e25\u0e32\u0e15\u0e2d\u0e1a\u0e2a\u0e19\u0e2d\u0e07: {response_text}",
            f"\u0e15\u0e23\u0e27\u0e08\u0e25\u0e48\u0e32\u0e2a\u0e38\u0e14: {device.get('last_check') or '-'}",
        ])
        english_segments.extend([
            f"response: {response_text}",
            f"last check: {device.get('last_check') or 'n/a'}",
        ])
        return thai_segments, english_segments

    def _build_device_details(self, device, response_text):
        return {
            "name": device.get("name"),
            "status": self._format_status(device.get("status")),
            "status_code": str(device.get("status") or "unknown").lower(),
            "ip_address": device.get("ip_address") or "-",
            "device_type": self._display_device_type(device.get("device_type")),
            "monitor_type": self._display_monitor_type(device.get("monitor_type")),
            "location": device.get("location"),
            "site": device.get("site"),
            "vendor": device.get("vendor") or device.get("brand"),
            "model": device.get("model"),
            "serial": device.get("serial_number") or device.get("serial"),
            "response_time": response_text,
            "last_check": device.get("last_check") or "-",
            "links": self._device_links(device),
        }

    def _device_lookup_values(self, device):
        return [
            self._normalize(device.get("name") or ""),
            self._normalize(device.get("ip_address") or ""),
            self._normalize(device.get("serial_number") or ""),
            self._normalize(device.get("serial") or ""),
            self._normalize(device.get("model") or ""),
            self._normalize(device.get("vendor") or ""),
            self._normalize(device.get("brand") or ""),
        ]

    def _normalize(self, value):
        normalized = str(value or "").strip().lower()
        normalized = re.sub(r"[^0-9a-z\u0e00-\u0e7f\s/-]+", " ", normalized)
        normalized = " ".join(normalized.split())
        for source, target in self.PHRASE_ALIASES.items():
            if source in normalized:
                normalized = normalized.replace(source, target)
        return " ".join(normalized.split())

    def _tokenize(self, value):
        return [token for token in self._normalize(value).split() if token]

    def _strip_noise(self, normalized):
        return " ".join(token for token in self._tokenize(normalized) if token not in self.NOISE_TERMS)

    def _contains_term(self, normalized, term):
        normalized_term = self._normalize(term)
        if not normalized_term:
            return False
        if normalized_term in normalized:
            return True

        tokens = normalized.split()
        term_tokens = normalized_term.split()
        if not term_tokens:
            return False
        return all(
            any(
                token == term_token
                or (
                    len(term_token) >= 3
                    and len(token) >= 3
                    and (token.startswith(term_token) or term_token.startswith(token))
                )
                for token in tokens
            )
            for term_token in term_tokens
        )

    def _matches_any(self, normalized, terms):
        compact = self._strip_noise(normalized)
        return any(self._contains_term(normalized, term) or self._contains_term(compact, term) for term in terms)

    def _similarity(self, left, right):
        return SequenceMatcher(None, self._normalize(left), self._normalize(right)).ratio()

    def _best_fuzzy_match(self, query, options, threshold=0.82):
        normalized_query = self._strip_noise(query)
        if not normalized_query:
            return None

        best_option = None
        best_score = 0.0
        for option in options:
            score = self._similarity(normalized_query, option)
            if score > best_score:
                best_option = option
                best_score = score
        if best_score >= threshold:
            return best_option
        return None

    def _format_status(self, status):
        if self._is_thai_locale():
            mapping = {
                "up": "\u0e1b\u0e01\u0e15\u0e34",
                "down": "\u0e25\u0e48\u0e21",
                "slow": "\u0e0a\u0e49\u0e32",
                "unknown": "\u0e44\u0e21\u0e48\u0e17\u0e23\u0e32\u0e1a",
                "disabled": "\u0e1b\u0e34\u0e14\u0e43\u0e0a\u0e49\u0e07\u0e32\u0e19",
            }
            return mapping.get(str(status or "").lower(), str(status or "\u0e44\u0e21\u0e48\u0e17\u0e23\u0e32\u0e1a"))
        mapping = {
            "up": "UP",
            "down": "DOWN",
            "slow": "SLOW",
            "unknown": "UNKNOWN",
            "disabled": "DISABLED",
        }
        return mapping.get(str(status or "").lower(), str(status or "UNKNOWN").upper())

    def _help_response(self, prefix=None):
        lines = []
        if prefix:
            lines.append(prefix)
        lines.extend([
            self._locale_text("\u0e15\u0e31\u0e27\u0e2d\u0e22\u0e48\u0e32\u0e07\u0e04\u0e33\u0e16\u0e32\u0e21:", "Try asking:"),
            self._locale_text(f"- {self.THAI_SUMMARY}\u0e23\u0e30\u0e1a\u0e1a{self.THAI_NOW}", "- System summary now"),
            self._locale_text(f"- \u0e21\u0e35{self.THAI_DEVICE} down {self.THAI_WHAT}", "- What devices are down?"),
            self._locale_text(f"- switch down {self.THAI_WHAT}", "- Which switches are down?"),
            self._locale_text(f"- {self.THAI_STATUS}\u0e02\u0e2d\u0e07 Core Router", "- Status of Core Router"),
            self._locale_text(f"- {self.THAI_STATUS} Branch A", "- Status of Branch A"),
            self._locale_text(f"- snmp devices {self.THAI_WHAT}", "- Show SNMP devices"),
            self._locale_text(f"- incident {self.THAI_NOW}", "- Active incidents now"),
            self._locale_text(f"- anomaly {self.THAI_NOW}", "- Active anomalies now"),
            self._locale_text(f"- top bandwidth {self.THAI_NOW}", "- Top bandwidth right now"),
            self._locale_text(f"- SLA 30 \u0e27\u0e31\u0e19{self.THAI_LATEST}", "- SLA for the last 30 days"),
        ])
        return self._response("help", "\n".join(lines), [])

    def _extract_filters(self, normalized, devices):
        filters = {
            "status": None,
            "device_type": None,
            "monitor_type": None,
            "location": None,
        }

        for canonical, terms in self.STATUS_TERMS.items():
            if self._matches_any(normalized, terms):
                filters["status"] = canonical
                break
        if not filters["status"] and self._matches_any(normalized, self.PROBLEM_TERMS):
            filters["status"] = "down"

        for canonical, terms in self.DEVICE_TYPE_ALIASES.items():
            if self._matches_any(normalized, terms):
                filters["device_type"] = canonical
                break

        for canonical, terms in self.MONITOR_TYPE_ALIASES.items():
            if self._matches_any(normalized, terms):
                filters["monitor_type"] = canonical
                break

        locations = {}
        for device in devices:
            location = str(device.get("location") or "").strip()
            if location:
                locations[self._normalize(location)] = location

        for normalized_location, original_location in locations.items():
            if normalized_location and normalized_location in normalized:
                filters["location"] = original_location
                break
        if not filters["location"] and locations:
            fuzzy_location = self._best_fuzzy_match(normalized, list(locations.keys()))
            if fuzzy_location:
                filters["location"] = locations[fuzzy_location]

        return filters

    def _apply_filters(self, devices, filters):
        result = list(devices)
        if filters.get("location"):
            result = [d for d in result if str(d.get("location") or "").strip() == filters["location"]]
        if filters.get("status"):
            result = [d for d in result if str(d.get("status") or "").lower() == filters["status"]]
        if filters.get("device_type"):
            needle = filters["device_type"]
            result = [d for d in result if needle in self._normalize(d.get("device_type") or "")]
        if filters.get("monitor_type"):
            needle = filters["monitor_type"]
            result = [d for d in result if needle == self._normalize(d.get("monitor_type") or "")]
        return result

    def _filter_label(self, filters):
        parts = []
        if filters.get("location"):
            parts.append(self._locale_text(f"\u0e2a\u0e16\u0e32\u0e19\u0e17\u0e35\u0e48 {filters['location']}", f"location {filters['location']}"))
        if filters.get("device_type"):
            parts.append(self._locale_text(
                f"\u0e1b\u0e23\u0e30\u0e40\u0e20\u0e17 {self._display_device_type(filters['device_type'])}",
                f"type {filters['device_type']}",
            ))
        if filters.get("monitor_type"):
            parts.append(self._locale_text(
                f"\u0e21\u0e2d\u0e19\u0e34\u0e40\u0e15\u0e2d\u0e23\u0e4c {self._display_monitor_type(filters['monitor_type'])}",
                f"monitor {filters['monitor_type']}",
            ))
        if filters.get("status"):
            parts.append(self._locale_text(f"\u0e2a\u0e16\u0e32\u0e19\u0e30 {self._format_status(filters['status'])}", f"status {self._format_status(filters['status'])}"))
        return ", ".join(parts)

    def _device_links(self, device):
        device_id = device.get("id")
        if not device_id:
            return []
        return [
            {"label": self._locale_text("\u0e14\u0e39 Topology", "Open Topology"), "url": f"/topology?highlight_device={device_id}"},
            {"label": self._locale_text("\u0e40\u0e1b\u0e34\u0e14\u0e2b\u0e19\u0e49\u0e32 Devices", "Open Devices"), "url": f"/devices?highlight_device={device_id}"},
            {"label": self._locale_text("\u0e14\u0e39\u0e1b\u0e23\u0e30\u0e27\u0e31\u0e15\u0e34", "Open History"), "url": f"/api/devices/{device_id}/history?minutes=1440&sample=50"},
            {"label": self._locale_text("\u0e14\u0e39 Bandwidth", "Open Bandwidth"), "url": f"/bandwidth?device_id={device_id}"},
        ]

    def _device_action(self, device):
        if not device.get("id"):
            return None
        return {
            "id": "check_device_now",
            "label": self._locale_text(f"\u0e15\u0e23\u0e27\u0e08\u0e2a\u0e2d\u0e1a {device.get('name')}", f"Check {device.get('name')}"),
            "description": self._locale_text(
                "\u0e23\u0e31\u0e19\u0e01\u0e32\u0e23\u0e15\u0e23\u0e27\u0e08\u0e2a\u0e16\u0e32\u0e19\u0e30\u0e2d\u0e38\u0e1b\u0e01\u0e23\u0e13\u0e4c\u0e19\u0e35\u0e49\u0e17\u0e31\u0e19\u0e17\u0e35\u0e41\u0e1a\u0e1a\u0e1b\u0e25\u0e2d\u0e14\u0e20\u0e31\u0e22",
                "Run an immediate safe status check for this device.",
            ),
            "payload": {"device_id": device.get("id")},
        }

    def _device_context_payload(self, devices):
        device_list = []
        for device in devices[:8]:
            if device.get("id"):
                device_list.append({"id": device.get("id"), "name": device.get("name")})
        return {
            "last_device": device_list[0] if device_list else None,
            "recent_devices": device_list,
        }

    def _find_named_device(self, normalized, devices, context=None):
        matches = []
        compact_prompt = self._strip_noise(normalized)
        prompt_tokens = compact_prompt.split()
        candidate_phrases = [compact_prompt]
        for size in range(2, min(len(prompt_tokens), 5) + 1):
            for index in range(len(prompt_tokens) - size + 1):
                candidate_phrases.append(" ".join(prompt_tokens[index:index + size]))

        for device in devices:
            name = str(device.get("name") or "").strip()
            normalized_name = self._normalize(name)
            normalized_ip = self._normalize(device.get("ip_address") or "")
            lookup_values = [value for value in self._device_lookup_values(device) if value]
            if normalized_name and (normalized_name in normalized or normalized_name in compact_prompt):
                matches.append(device)
                continue
            if normalized_ip and (normalized == normalized_ip or normalized_ip in normalized):
                matches.append(device)
                continue
            if any(value and (normalized == value or compact_prompt == value or value in normalized) for value in lookup_values):
                matches.append(device)
                continue

            tokens = [token for token in normalized_name.split() if len(token) >= 4]
            if tokens and all(token in normalized for token in tokens[:2]):
                matches.append(device)
                continue
            if tokens and sum(1 for token in tokens if token in prompt_tokens) >= min(2, len(tokens)):
                matches.append(device)
                continue

            fuzzy_match = self._best_fuzzy_match(
                normalized_name,
                candidate_phrases,
                threshold=0.78 if len(normalized_name) >= 8 else 0.9,
            )
            if fuzzy_match:
                matches.append(device)
                continue

            lookup_match = self._best_fuzzy_match(
                compact_prompt,
                lookup_values,
                threshold=0.9,
            )
            if lookup_match:
                matches.append(device)
        if matches:
            return matches
        return self._resolve_contextual_device(normalized, devices, context)

    def _try_device_action(self, normalized, devices, context=None):
        if not self._matches_any(normalized, ["check", "recheck", "refresh", "run check", self.THAI_CHECK, self.THAI_CHECK_ALT, self.THAI_CHECK_ALT2]):
            return None

        matches = self._find_named_device(normalized, devices, context=context)
        if not matches:
            return None

        device = matches[0]
        answer = self._locale_text(
            f"\u0e1c\u0e21\u0e40\u0e08\u0e2d {device.get('name')} \u0e41\u0e25\u0e30\u0e40\u0e15\u0e23\u0e35\u0e22\u0e21\u0e04\u0e33\u0e2a\u0e31\u0e48\u0e07\u0e15\u0e23\u0e27\u0e08\u0e2a\u0e16\u0e32\u0e19\u0e30\u0e17\u0e31\u0e19\u0e17\u0e35\u0e44\u0e27\u0e49\u0e41\u0e25\u0e49\u0e27 \u0e01\u0e14\u0e1b\u0e38\u0e48\u0e21\u0e14\u0e49\u0e32\u0e19\u0e25\u0e48\u0e32\u0e07\u0e44\u0e14\u0e49\u0e40\u0e25\u0e22\u0e16\u0e49\u0e32\u0e15\u0e49\u0e2d\u0e07\u0e01\u0e32\u0e23\u0e43\u0e2b\u0e49\u0e23\u0e31\u0e19",
            f"I found {device.get('name')} and prepared a safe action to run an immediate status check. Use the action button below if you want to trigger it.",
        )
        return self._response(
            "device_action_prepare",
            answer,
            ["devices"],
            actions=[self._device_action(device)],
            links=self._device_links(device),
            context_updates=self._device_context_payload([device]),
        )

    def _try_device_status(self, normalized, devices, context=None):
        if not self._matches_any(normalized, ["status", "device", "router", "switch", "server", self.THAI_STATUS, self.THAI_DEVICE]):
            return None

        matches = self._find_named_device(normalized, devices, context=context)
        if not matches:
            return None

        device = matches[0]
        response_time = device.get("response_time")
        response_text = f"{response_time} ms" if response_time is not None else self._locale_text("-", "n/a")
        thai_segments, english_segments = self._device_detail_segments(device, response_text)
        device_details = self._build_device_details(device, response_text)
        answer = self._locale_text(
            f"{device.get('name')} \u0e2a\u0e16\u0e32\u0e19\u0e30{self._format_status(device.get('status'))} " + ", ".join(thai_segments),
            f"{device.get('name')} is {self._format_status(device.get('status'))}. " + ", ".join(english_segments),
        )
        return self._response(
            "device_status",
            answer,
            ["devices"],
            actions=[self._device_action(device)],
            links=self._device_links(device),
            context_updates=self._device_context_payload([device]),
            device_details=device_details,
        )

    def _try_named_device_detail(self, normalized, devices, context=None):
        matches = self._find_named_device(normalized, devices, context=context)
        if not matches:
            return None
        device = matches[0]
        if not self._is_device_only_prompt(normalized, device):
            return None
        response_time = device.get("response_time")
        response_text = f"{response_time} ms" if response_time is not None else self._locale_text("-", "n/a")
        thai_segments, english_segments = self._device_detail_segments(device, response_text)
        device_details = self._build_device_details(device, response_text)
        answer = self._locale_text(
            f"{device.get('name')} \u0e2a\u0e16\u0e32\u0e19\u0e30{self._format_status(device.get('status'))} " + ", ".join(thai_segments),
            f"{device.get('name')} is {self._format_status(device.get('status'))}. " + ", ".join(english_segments),
        )
        return self._response(
            "device_status",
            answer,
            ["devices"],
            actions=[self._device_action(device)],
            links=self._device_links(device),
            context_updates=self._device_context_payload([device]),
            device_details=device_details,
        )

    def _try_location_summary(self, filters, devices):
        if not filters.get("location"):
            return None
        if filters.get("device_type") or filters.get("monitor_type") or filters.get("status"):
            return None
        return self._device_summary(devices, filters=filters, intent="location_status")

    def _try_filtered_device_summary(self, normalized, devices, filters, context=None):
        if not any(filters.values()):
            return None
        if self._is_follow_up_prompt(normalized):
            preferred_intent = ((context or {}).get("intent") or "device_summary")
            return self._device_summary(devices, filters=filters, intent=preferred_intent)
        keywords = [
            "device", "devices", "summary", "overview", "list",
            "problem devices", "anything wrong", "need attention", "having issues",
            self.THAI_WHAT, self.THAI_SUMMARY, self.THAI_ALL,
        ]
        if filters.get("status"):
            keywords.extend(self.STATUS_TERMS.get(filters["status"], []))
            if filters["status"] == "down":
                keywords.extend(self.PROBLEM_TERMS)
        if filters.get("device_type"):
            keywords.extend(self.DEVICE_TYPE_ALIASES.get(filters["device_type"], []))
        if filters.get("monitor_type"):
            keywords.extend(self.MONITOR_TYPE_ALIASES.get(filters["monitor_type"], []))
        if self._matches_any(normalized, keywords):
            preferred_intent = ((context or {}).get("intent") or "device_summary")
            return self._device_summary(devices, filters=filters, intent=preferred_intent)
        return None

    def _device_summary(self, devices, filters=None, intent="device_summary"):
        filters = filters or {}
        subset = self._apply_filters(devices, filters)

        down = [d for d in subset if d.get("status") == "down"]
        slow = [d for d in subset if d.get("status") == "slow"]
        up = [d for d in subset if d.get("status") == "up"]
        disabled = [d for d in subset if d.get("status") == "disabled"]
        label = self._filter_label(filters)
        prefix = self._locale_text(
            f"\u0e2a\u0e23\u0e38\u0e1b\u0e15\u0e32\u0e21\u0e40\u0e07\u0e37\u0e48\u0e2d\u0e19\u0e44\u0e02 ({label}): " if label else "\u0e2a\u0e23\u0e38\u0e1b\u0e23\u0e30\u0e1a\u0e1a: ",
            f"Filtered summary ({label}): " if label else "System summary: ",
        )

        answer = self._locale_text(
            f"{prefix}\u0e17\u0e31\u0e49\u0e07\u0e2b\u0e21\u0e14 {len(subset)} \u0e2d\u0e38\u0e1b\u0e01\u0e23\u0e13\u0e4c, "
            f"\u0e1b\u0e01\u0e15\u0e34 {len(up)}, \u0e25\u0e48\u0e21 {len(down)}, \u0e0a\u0e49\u0e32 {len(slow)}, \u0e1b\u0e34\u0e14\u0e43\u0e0a\u0e49\u0e07\u0e32\u0e19 {len(disabled)}",
            f"{prefix}{len(subset)} devices, {len(up)} UP, {len(down)} DOWN, {len(slow)} SLOW, {len(disabled)} DISABLED.",
        )

        if filters.get("status") == "down" and down:
            answer += self._locale_text(" \u0e2d\u0e38\u0e1b\u0e01\u0e23\u0e13\u0e4c\u0e17\u0e35\u0e48\u0e25\u0e48\u0e21: ", " Down devices: ") + ", ".join(
                f"{d.get('name', 'Unknown')} ({d.get('ip_address', '-')})" for d in down[:8]
            ) + ""
            intent = "down_devices"
        elif filters.get("status") == "slow" and slow:
            answer += self._locale_text(" \u0e2d\u0e38\u0e1b\u0e01\u0e23\u0e13\u0e4c\u0e17\u0e35\u0e48\u0e0a\u0e49\u0e32: ", " Slow devices: ") + ", ".join(
                f"{d.get('name', 'Unknown')} ({d.get('response_time') or '-'} ms)" for d in slow[:8]
            ) + ""
            intent = "slow_devices"
        elif len(subset) <= 8 and subset:
            answer += self._locale_text(" \u0e23\u0e32\u0e22\u0e01\u0e32\u0e23: ", " Devices: ") + ", ".join(d.get("name", "Unknown") for d in subset)

        if not subset:
            empty_label = label or self._locale_text("\u0e44\u0e21\u0e48\u0e21\u0e35\u0e40\u0e07\u0e37\u0e48\u0e2d\u0e19\u0e44\u0e02", "no filters")
            answer = self._locale_text(
                f"\u0e44\u0e21\u0e48\u0e1e\u0e1a\u0e2d\u0e38\u0e1b\u0e01\u0e23\u0e13\u0e4c\u0e17\u0e35\u0e48\u0e15\u0e23\u0e07\u0e01\u0e31\u0e1a\u0e40\u0e07\u0e37\u0e48\u0e2d\u0e19\u0e44\u0e02\u0e19\u0e35\u0e49 ({empty_label})",
                f"No devices matched the current filter set ({empty_label}).",
            )

        return self._response(
            intent,
            answer,
            ["devices"],
            context_updates=self._device_context_payload(subset),
        )

    def _alert_summary(self, filters):
        alerts = self.db.get_alert_history(limit=20)
        if filters.get("status"):
            alerts = [a for a in alerts if str(a.get("event_type") or "").lower() == filters["status"]]
        if filters.get("location"):
            alerts = [a for a in alerts if self._normalize(a.get("location") or "") == self._normalize(filters["location"])]

        if not alerts:
            return self._response(
                "recent_alerts",
                self._locale_text(
                    "\u0e44\u0e21\u0e48\u0e1e\u0e1a alert \u0e25\u0e48\u0e32\u0e2a\u0e38\u0e14\u0e15\u0e32\u0e21\u0e40\u0e07\u0e37\u0e48\u0e2d\u0e19\u0e44\u0e02\u0e19\u0e35\u0e49",
                    "No recent alerts were found for the current filter.",
                ),
                ["alert_history"],
            )

        lines = [self._locale_text(
            f"alert \u0e25\u0e48\u0e32\u0e2a\u0e38\u0e14 {len(alerts)} \u0e23\u0e32\u0e22\u0e01\u0e32\u0e23",
            f"Recent alerts: {len(alerts)} latest event(s).",
        )]
        for alert in alerts[:5]:
            lines.append(self._locale_text(
                f"- {alert.get('device_name') or 'Unknown'}: {self._format_status(alert.get('event_type') or 'event')} "
                f"\u0e1c\u0e48\u0e32\u0e19 {alert.get('channel') or '-'} \u0e40\u0e27\u0e25\u0e32 {alert.get('created_at') or '-'}",
                f"- {alert.get('device_name') or 'Unknown'}: {self._format_status(alert.get('event_type') or 'event')} "
                f"via {alert.get('channel') or '-'} at {alert.get('created_at') or '-'}",
            ))
        return self._response("recent_alerts", "\n".join(lines), ["alert_history"])

    def _incident_summary(self, filters):
        incidents = self.db.get_persistent_incidents(active_only=True, limit=20)
        if filters.get("location"):
            incidents = [
                incident for incident in incidents
                if self._normalize(((incident.get("payload") or {}).get("location") or "")) == self._normalize(filters["location"])
                or self._normalize(((incident.get("payload") or {}).get("root_cause_location") or "")) == self._normalize(filters["location"])
            ]

        if not incidents:
            return self._response(
                "incident_summary",
                self._locale_text(
                    "\u0e15\u0e2d\u0e19\u0e19\u0e35\u0e49\u0e44\u0e21\u0e48\u0e21\u0e35\u0e40\u0e2b\u0e15\u0e38\u0e01\u0e32\u0e23\u0e13\u0e4c\u0e17\u0e35\u0e48\u0e22\u0e31\u0e07\u0e40\u0e1b\u0e34\u0e14\u0e2d\u0e22\u0e39\u0e48",
                    "No active incidents are currently materialized.",
                ),
                ["persistent_incidents"],
            )

        lines = [self._locale_text(
            f"\u0e15\u0e2d\u0e19\u0e19\u0e35\u0e49\u0e21\u0e35\u0e40\u0e2b\u0e15\u0e38\u0e01\u0e32\u0e23\u0e13\u0e4c\u0e17\u0e35\u0e48\u0e22\u0e31\u0e07\u0e40\u0e1b\u0e34\u0e14\u0e2d\u0e22\u0e39\u0e48 {len(incidents)} \u0e23\u0e32\u0e22\u0e01\u0e32\u0e23",
            f"There are {len(incidents)} active incident(s).",
        )]
        for incident in incidents[:5]:
            payload = incident.get("payload") or {}
            lines.append(self._locale_text(
                f"- {incident.get('incident_id')}: {payload.get('summary') or incident.get('severity') or 'incident'} "
                f"(\u0e04\u0e27\u0e32\u0e21\u0e23\u0e38\u0e19\u0e41\u0e23\u0e07: {self._display_severity(incident.get('severity'))}, \u0e40\u0e27\u0e25\u0e32\u0e25\u0e48\u0e32\u0e2a\u0e38\u0e14: {incident.get('latest_at') or '-'})",
                f"- {incident.get('incident_id')}: {payload.get('summary') or incident.get('severity') or 'incident'} "
                f"(severity: {incident.get('severity') or '-'}, latest: {incident.get('latest_at') or '-'})",
            ))
        return self._response("incident_summary", "\n".join(lines), ["persistent_incidents"])

    def _anomaly_summary(self, filters):
        anomalies = self.db.get_anomaly_snapshots(active_only=True, limit=20)
        if filters.get("location"):
            anomalies = [anomaly for anomaly in anomalies if self._normalize(anomaly.get("location") or "") == self._normalize(filters["location"])]
        if filters.get("device_type"):
            anomalies = [anomaly for anomaly in anomalies if filters["device_type"] in self._normalize(anomaly.get("device_type") or "")]

        if not anomalies:
            return self._response(
                "anomaly_summary",
                self._locale_text(
                    "\u0e44\u0e21\u0e48\u0e1e\u0e1a\u0e04\u0e27\u0e32\u0e21\u0e1c\u0e34\u0e14\u0e1b\u0e01\u0e15\u0e34\u0e17\u0e35\u0e48\u0e01\u0e33\u0e25\u0e31\u0e07\u0e40\u0e01\u0e34\u0e14\u0e2d\u0e22\u0e39\u0e48",
                    "No active anomalies were found.",
                ),
                ["anomaly_snapshots"],
            )

        lines = [self._locale_text(
            f"\u0e1e\u0e1a\u0e04\u0e27\u0e32\u0e21\u0e1c\u0e34\u0e14\u0e1b\u0e01\u0e15\u0e34\u0e17\u0e35\u0e48\u0e01\u0e33\u0e25\u0e31\u0e07\u0e40\u0e01\u0e34\u0e14\u0e2d\u0e22\u0e39\u0e48 \u0e08\u0e33\u0e19\u0e27\u0e19 {len(anomalies)} \u0e23\u0e32\u0e22\u0e01\u0e32\u0e23",
            f"There are {len(anomalies)} active anomaly snapshot(s).",
        )]
        for anomaly in anomalies[:5]:
            lines.append(self._locale_text(
                f"- {anomaly.get('device_name') or 'Unknown'}: {self._display_anomaly_type(anomaly.get('anomaly_type'))} "
                f"(\u0e04\u0e27\u0e32\u0e21\u0e23\u0e38\u0e19\u0e41\u0e23\u0e07: {self._display_severity(anomaly.get('severity'))}, score: {anomaly.get('score') or '-'})",
                f"- {anomaly.get('device_name') or 'Unknown'}: {anomaly.get('anomaly_type') or 'anomaly'} "
                f"(severity: {anomaly.get('severity') or '-'}, score: {anomaly.get('score') or '-'})",
            ))
        return self._response("anomaly_summary", "\n".join(lines), ["anomaly_snapshots"])

    def _bandwidth_summary(self, filters):
        rows = self.db.get_top_bandwidth_interfaces(minutes=15, top_n=10)
        if filters.get("device_type"):
            rows = [row for row in rows if filters["device_type"] in self._normalize(row.get("device_type") or "")]
        if filters.get("location"):
            rows = [row for row in rows if self._normalize(row.get("location") or "") == self._normalize(filters["location"])]

        if not rows:
            return self._response(
                "bandwidth_summary",
                self._locale_text(
                    "\u0e44\u0e21\u0e48\u0e1e\u0e1a\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25 bandwidth \u0e25\u0e48\u0e32\u0e2a\u0e38\u0e14\u0e15\u0e32\u0e21\u0e40\u0e07\u0e37\u0e48\u0e2d\u0e19\u0e44\u0e02\u0e19\u0e35\u0e49",
                    "No recent bandwidth data is available for the current filter.",
                ),
                ["bandwidth_history"],
            )

        lines = [self._locale_text(
            "\u0e2d\u0e31\u0e19\u0e14\u0e31\u0e1a bandwidth \u0e2a\u0e39\u0e07\u0e2a\u0e38\u0e14\u0e43\u0e19 15 \u0e19\u0e32\u0e17\u0e35\u0e25\u0e48\u0e32\u0e2a\u0e38\u0e14:",
            "Top bandwidth interfaces in the last 15 minutes:",
        )]
        for row in rows[:5]:
            util_in = row.get("avg_util_in")
            util_out = row.get("avg_util_out")
            if util_in is not None and util_out is not None:
                util_text = self._locale_text(
                    f"\u0e02\u0e32\u0e40\u0e02\u0e49\u0e32 {round(float(util_in), 2)}% / \u0e02\u0e32\u0e2d\u0e2d\u0e01 {round(float(util_out), 2)}%",
                    f"in {round(float(util_in), 2)}% / out {round(float(util_out), 2)}%",
                )
            else:
                util_text = self._locale_text("\u0e22\u0e31\u0e07\u0e44\u0e21\u0e48\u0e21\u0e35 utilization", "utilization n/a")
            lines.append(
                f"- {row.get('device_name') or 'Unknown'} / {row.get('if_name') or 'interface'}: {util_text}"
            )
        return self._response("bandwidth_summary", "\n".join(lines), ["bandwidth_history"])

    def _sla_summary(self, filters):
        rows = self.db.get_all_devices_sla(days=30, sla_target=99.9)
        if filters.get("location"):
            rows = [row for row in rows if self._normalize(row.get("location") or "") == self._normalize(filters["location"])]
        if filters.get("device_type"):
            rows = [row for row in rows if filters["device_type"] in self._normalize(row.get("device_type") or "")]

        with_data = [row for row in rows if row.get("uptime_percent") is not None]
        if not with_data:
            return self._response(
                "sla_summary",
                self._locale_text("\u0e22\u0e31\u0e07\u0e44\u0e21\u0e48\u0e21\u0e35\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25 SLA", "No SLA data is available yet."),
                ["status_history"],
            )

        met = [row for row in with_data if row.get("sla_status") == "met"]
        breached = [row for row in with_data if row.get("sla_status") == "breached"]
        average = round(sum(row.get("uptime_percent", 0) for row in with_data) / len(with_data), 4)
        answer = self._locale_text(
            f"SLA \u0e22\u0e49\u0e2d\u0e19\u0e2b\u0e25\u0e31\u0e07 30 \u0e27\u0e31\u0e19: \u0e21\u0e35\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25 {len(with_data)} \u0e2d\u0e38\u0e1b\u0e01\u0e23\u0e13\u0e4c, "
            f"\u0e1c\u0e48\u0e32\u0e19\u0e40\u0e1b\u0e49\u0e32\u0e2b\u0e21\u0e32\u0e22 {len(met)}, \u0e44\u0e21\u0e48\u0e1c\u0e48\u0e32\u0e19 {len(breached)}, uptime \u0e40\u0e09\u0e25\u0e35\u0e48\u0e22 {average}%",
            f"SLA last 30 days: {len(with_data)} device(s) with data, {len(met)} met target, {len(breached)} breached, average uptime {average}%.",
        )
        if breached:
            answer += self._locale_text(" \u0e15\u0e31\u0e27\u0e2d\u0e22\u0e48\u0e32\u0e07\u0e17\u0e35\u0e48\u0e44\u0e21\u0e48\u0e1c\u0e48\u0e32\u0e19: ", " Breached examples: ") + ", ".join(
                f"{row.get('name')} ({row.get('uptime_percent')}%)" for row in breached[:5]
            )
        return self._response("sla_summary", answer, ["status_history"])
