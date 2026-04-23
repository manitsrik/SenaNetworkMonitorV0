import unittest

from assistant_service import AssistantService


class FakeAssistantDB:
    def get_all_devices(self):
        return [
            {
                "id": 1,
                "name": "Core Router",
                "ip_address": "10.0.0.1",
                "status": "up",
                "response_time": 12.4,
                "last_check": "2026-04-16T10:00:00",
                "location": "HQ",
                "device_type": "router",
                "monitor_type": "snmp",
            },
            {
                "id": 2,
                "name": "Branch Switch",
                "ip_address": "10.0.1.5",
                "status": "down",
                "response_time": None,
                "last_check": "2026-04-16T09:59:40",
                "location": "Branch A",
                "device_type": "switch",
                "monitor_type": "snmp",
            },
            {
                "id": 3,
                "name": "HQ Web Server",
                "ip_address": "10.0.2.9",
                "status": "slow",
                "response_time": 450.0,
                "last_check": "2026-04-16T09:58:40",
                "location": "HQ",
                "device_type": "server",
                "monitor_type": "http",
            },
            {
                "id": 4,
                "name": "SENA448-FL4-AP02",
                "ip_address": "10.44.8.22",
                "status": "up",
                "response_time": 8.7,
                "last_check": "2026-04-16T10:01:40",
                "location": "Floor 4",
                "device_type": "access point",
                "monitor_type": "ping",
                "site": "SENA448",
                "vendor": "Cisco",
                "model": "CW9162I",
                "serial_number": "FTX1234ABC",
            },
        ]

    def get_alert_history(self, limit=10):
        return [
            {
                "device_name": "Branch Switch",
                "event_type": "down",
                "channel": "telegram",
                "created_at": "2026-04-16T09:59:00",
                "location": "Branch A",
            }
        ]

    def get_persistent_incidents(self, active_only=True, limit=10):
        return [
            {
                "incident_id": "inc-1",
                "severity": "critical",
                "latest_at": "2026-04-16T09:59:00",
                "payload": {"summary": "Branch outage", "location": "Branch A"},
            }
        ]

    def get_anomaly_snapshots(self, active_only=True, limit=10):
        return [
            {
                "device_name": "Core Router",
                "device_type": "router",
                "location": "HQ",
                "anomaly_type": "response_time",
                "severity": "warning",
                "score": 2.4,
            }
        ]

    def get_top_bandwidth_interfaces(self, minutes=15, top_n=5):
        return [
            {
                "device_name": "Core Router",
                "device_type": "router",
                "location": "HQ",
                "if_name": "Gi0/1",
                "avg_util_in": 70.5,
                "avg_util_out": 55.2,
            }
        ]

    def get_all_devices_sla(self, days=30, sla_target=99.9):
        return [
            {"name": "Core Router", "location": "HQ", "device_type": "router", "uptime_percent": 99.95, "sla_status": "met"},
            {"name": "Branch Switch", "location": "Branch A", "device_type": "switch", "uptime_percent": 97.10, "sla_status": "breached"},
        ]


class AssistantServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = AssistantService(FakeAssistantDB())

    def test_down_device_query(self):
        result = self.service.answer("\u0e21\u0e35\u0e2d\u0e38\u0e1b\u0e01\u0e23\u0e13\u0e4c down \u0e2d\u0e30\u0e44\u0e23\u0e1a\u0e49\u0e32\u0e07")
        self.assertTrue(result["success"])
        self.assertEqual(result["intent"], "down_devices")
        self.assertIn("Branch Switch", result["answer"])

    def test_device_status_query(self):
        result = self.service.answer("\u0e2a\u0e16\u0e32\u0e19\u0e30\u0e02\u0e2d\u0e07 Core Router")
        self.assertEqual(result["intent"], "device_status")
        self.assertIn("Core Router", result["answer"])
        self.assertIn("\u0e1b\u0e01\u0e15\u0e34", result["answer"])
        self.assertIn("\u0e40\u0e23\u0e32\u0e40\u0e15\u0e2d\u0e23\u0e4c", result["answer"])

    def test_device_name_only_query_returns_device_details(self):
        result = self.service.answer("SENA448-FL4-AP02")
        self.assertEqual(result["intent"], "device_status")
        self.assertIn("SENA448-FL4-AP02", result["answer"])
        self.assertIn("10.44.8.22", result["answer"])
        self.assertIn("site: SENA448", result["answer"])
        self.assertIn("vendor: Cisco", result["answer"])
        self.assertEqual(result["device_details"]["serial"], "FTX1234ABC")
        self.assertEqual(result["device_details"]["status_code"], "up")
        self.assertTrue(any(link["label"] in {"Open Topology", "ดู Topology"} for link in result["device_details"]["links"]))
        self.assertTrue(result["actions"])

    def test_ip_only_query_returns_device_details(self):
        result = self.service.answer("10.44.8.22")
        self.assertEqual(result["intent"], "device_status")
        self.assertIn("SENA448-FL4-AP02", result["answer"])
        self.assertIn("10.44.8.22", result["answer"])

    def test_vendor_lookup_returns_device_details(self):
        result = self.service.answer("Cisco")
        self.assertEqual(result["intent"], "device_status")
        self.assertIn("SENA448-FL4-AP02", result["answer"])

    def test_model_lookup_returns_device_details(self):
        result = self.service.answer("CW9162I")
        self.assertEqual(result["intent"], "device_status")
        self.assertIn("SENA448-FL4-AP02", result["answer"])

    def test_serial_lookup_returns_device_details(self):
        result = self.service.answer("FTX1234ABC")
        self.assertEqual(result["intent"], "device_status")
        self.assertIn("SENA448-FL4-AP02", result["answer"])

    def test_incident_query(self):
        result = self.service.answer("incident \u0e15\u0e2d\u0e19\u0e19\u0e35\u0e49")
        self.assertEqual(result["intent"], "incident_summary")
        self.assertIn("inc-1", result["answer"])
        self.assertIn("\u0e40\u0e2b\u0e15\u0e38\u0e01\u0e32\u0e23\u0e13\u0e4c", result["answer"])

    def test_location_query(self):
        result = self.service.answer("\u0e2a\u0e16\u0e32\u0e19\u0e30 Branch A")
        self.assertEqual(result["intent"], "location_status")
        self.assertIn("Branch A", result["answer"])
        self.assertIn("\u0e25\u0e48\u0e21", result["answer"])

    def test_device_type_query(self):
        result = self.service.answer("switch down \u0e21\u0e35\u0e2d\u0e30\u0e44\u0e23\u0e1a\u0e49\u0e32\u0e07")
        self.assertEqual(result["intent"], "down_devices")
        self.assertIn("\u0e1b\u0e23\u0e30\u0e40\u0e20\u0e17 \u0e2a\u0e27\u0e34\u0e15\u0e0a\u0e4c", result["answer"])
        self.assertIn("Branch Switch", result["answer"])

    def test_monitor_type_query(self):
        result = self.service.answer("snmp devices \u0e21\u0e35\u0e2d\u0e30\u0e44\u0e23\u0e1a\u0e49\u0e32\u0e07")
        self.assertEqual(result["intent"], "device_summary")
        self.assertIn("\u0e21\u0e2d\u0e19\u0e34\u0e40\u0e15\u0e2d\u0e23\u0e4c SNMP", result["answer"])
        self.assertIn("Core Router", result["answer"])

    def test_anomaly_query_uses_more_natural_thai_terms(self):
        result = self.service.answer("anomaly \u0e15\u0e2d\u0e19\u0e19\u0e35\u0e49")
        self.assertEqual(result["intent"], "anomaly_summary")
        self.assertIn("\u0e04\u0e27\u0e32\u0e21\u0e1c\u0e34\u0e14\u0e1b\u0e01\u0e15\u0e34", result["answer"])
        self.assertIn("\u0e40\u0e27\u0e25\u0e32\u0e15\u0e2d\u0e1a\u0e2a\u0e19\u0e2d\u0e07\u0e1c\u0e34\u0e14\u0e1b\u0e01\u0e15\u0e34", result["answer"])

    def test_sla_query(self):
        result = self.service.answer("sla \u0e25\u0e48\u0e32\u0e2a\u0e38\u0e14")
        self.assertEqual(result["intent"], "sla_summary")
        self.assertIn("uptime \u0e40\u0e09\u0e25\u0e35\u0e48\u0e22", result["answer"])

    def test_help_query(self):
        result = self.service.answer("\u0e0a\u0e48\u0e27\u0e22\u0e1a\u0e2d\u0e01\u0e27\u0e48\u0e32\u0e16\u0e32\u0e21\u0e2d\u0e30\u0e44\u0e23\u0e44\u0e14\u0e49\u0e1a\u0e49\u0e32\u0e07")
        self.assertEqual(result["intent"], "help")
        self.assertIn("\u0e2a\u0e23\u0e38\u0e1b", result["answer"])

    def test_conversational_problem_query_maps_to_down_devices(self):
        result = self.service.answer("Can you show me anything wrong at branch a right now?")
        self.assertEqual(result["intent"], "down_devices")
        self.assertIn("Branch Switch", result["answer"])
        self.assertIn("location Branch A", result["answer"])

    def test_fuzzy_device_name_query(self):
        result = self.service.answer("status for core routr please")
        self.assertEqual(result["intent"], "device_status")
        self.assertIn("Core Router", result["answer"])
        self.assertIn("is UP", result["answer"])
        self.assertIn("Open Devices", [link["label"] for link in result["links"]])

    def test_conversational_action_query(self):
        result = self.service.answer("could you please check brnch swich right now")
        self.assertEqual(result["intent"], "device_action_prepare")
        self.assertEqual(result["actions"][0]["id"], "check_device_now")
        self.assertEqual(result["actions"][0]["payload"]["device_id"], 2)
        self.assertIn("prepared a safe action", result["answer"])
        self.assertEqual(result["actions"][0]["label"], "Check Branch Switch")

    def test_english_help_response_uses_english_examples(self):
        result = self.service.answer("help")
        self.assertEqual(result["intent"], "help")
        self.assertIn("Try asking:", result["answer"])
        self.assertIn("System summary now", result["quick_replies"])

    def test_follow_up_query_reuses_previous_location(self):
        first = self.service.answer("\u0e2a\u0e16\u0e32\u0e19\u0e30 Branch A")
        second = self.service.answer(
            "\u0e40\u0e2d\u0e32\u0e40\u0e09\u0e1e\u0e32\u0e30\u0e17\u0e35\u0e48\u0e25\u0e48\u0e21",
            context=first["context"],
        )
        self.assertEqual(second["intent"], "down_devices")
        self.assertIn("Branch Switch", second["answer"])
        self.assertEqual(second["context"]["filters"]["location"], "Branch A")

    def test_follow_up_query_can_switch_location_with_previous_filters(self):
        first = self.service.answer("switch down \u0e21\u0e35\u0e2d\u0e30\u0e44\u0e23\u0e1a\u0e49\u0e32\u0e07")
        second = self.service.answer("แล้วของ HQ ล่ะ", context=first["context"])
        self.assertEqual(second["intent"], "down_devices")
        self.assertIn("HQ", second["answer"])

    def test_contextual_device_reference_supports_first_item(self):
        first = self.service.answer("snmp devices \u0e21\u0e35\u0e2d\u0e30\u0e44\u0e23\u0e1a\u0e49\u0e32\u0e07")
        second = self.service.answer("\u0e2a\u0e16\u0e32\u0e19\u0e30\u0e15\u0e31\u0e27\u0e41\u0e23\u0e01", context=first["context"])
        self.assertEqual(second["intent"], "device_status")
        self.assertIn("Core Router", second["answer"])

    def test_contextual_device_reference_supports_that_one(self):
        first = self.service.answer("\u0e2a\u0e16\u0e32\u0e19\u0e30 Core Router")
        second = self.service.answer("\u0e40\u0e0a\u0e47\u0e01\u0e2d\u0e31\u0e19\u0e19\u0e31\u0e49\u0e19", context=first["context"])
        self.assertEqual(second["intent"], "device_action_prepare")
        self.assertEqual(second["actions"][0]["payload"]["device_id"], 1)


if __name__ == "__main__":
    unittest.main()
