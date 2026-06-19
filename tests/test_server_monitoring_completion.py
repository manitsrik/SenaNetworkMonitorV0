from alerter import Alerter
from routes.devices import _simple_pdf


class FakeDB:
    def __init__(self):
        self.settings = {
            'telegram_bot_token': 'token',
            'telegram_chat_id': '12345',
        }

    def get_all_alert_settings(self):
        return [
            {'setting_key': key, 'setting_value': value}
            for key, value in self.settings.items()
        ]


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


def test_simple_pdf_is_downloadable_document():
    content = _simple_pdf(['Server Health', 'CPU 10%', 'RAM 20%'])

    assert content.startswith(b'%PDF-1.4')
    assert content.endswith(b'%%EOF')
    assert b'Server Health' in content


def test_telegram_retries_plain_text_after_markdown_parse_error(monkeypatch):
    calls = []

    def fake_post(url, data, timeout):
        calls.append(dict(data))
        if len(calls) == 1:
            return FakeResponse(400, {'description': "Bad Request: can't parse entities"})
        return FakeResponse(200, {'ok': True})

    monkeypatch.setattr('alerter.requests.post', fake_post)
    result = Alerter(FakeDB()).send_telegram('resource_cpu is above threshold')

    assert result['success'] is True
    assert calls[0]['parse_mode'] == 'Markdown'
    assert 'parse_mode' not in calls[1]
