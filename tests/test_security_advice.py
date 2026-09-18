"""Remediation notes: coverage, translation, and the warnings that matter."""
from flask import Flask

import security_advice
from monitor import NetworkMonitor
from routes.devices import devices_bp


def _expected_keys():
    """Every check key the collectors can actually produce.

    pending_reboot is not in either label map: it is built by
    _reboot_security_check from the flag the metric pass already collected,
    so it has to be added by hand here.
    """
    return {
        'windows': set(NetworkMonitor.WINDOWS_SECURITY_LABELS) | {'pending_reboot'},
        'linux': set(NetworkMonitor.LINUX_SECURITY_KEYS) | {'pending_reboot'},
    }


def test_every_check_the_collector_can_report_has_advice():
    # A finding with no fix under it is the thing this feature exists to
    # avoid. If a new check is added to the collector, this fails until its
    # advice is written.
    for platform, keys in _expected_keys().items():
        missing = keys - set(security_advice.PLATFORMS[platform])
        assert not missing, 'no advice for %s: %s' % (platform, ', '.join(sorted(missing)))


def test_no_advice_is_written_for_a_check_that_does_not_exist():
    for platform, keys in _expected_keys().items():
        extra = set(security_advice.PLATFORMS[platform]) - keys
        assert not extra, 'advice for a check nothing emits: %s' % ', '.join(sorted(extra))


def test_every_entry_says_what_can_go_wrong():
    # Several of these fixes can lock you out of the host -- enabling a
    # firewall without allowing SSH, turning off the password login this
    # monitor uses. The warning is the point, not a garnish.
    for platform, entries in security_advice.PLATFORMS.items():
        for key, entry in entries.items():
            where = '%s/%s' % (platform, key)
            for field in ('label', 'fix', 'warning'):
                for language in security_advice.SUPPORTED_LANGUAGES:
                    text = (entry.get(field) or {}).get(language)
                    assert text and text.strip(), '%s has no %s in %s' % (where, field, language)


def test_the_two_ways_to_lock_yourself_out_are_both_called_out():
    linux = security_advice.LINUX

    # ufw enable before allowing SSH drops your session and the monitor's.
    assert 'ufw allow OpenSSH' in linux['firewall']['command']
    assert linux['firewall']['command'].index('allow OpenSSH') < \
        linux['firewall']['command'].index('ufw enable')
    for language in ('en', 'th'):
        assert 'SSH' in linux['firewall']['warning'][language]

    # This monitor signs in over SSH with a password, so turning password
    # authentication off without moving it to a key first cuts it off.
    for language in ('en', 'th'):
        assert 'key' in linux['ssh_password_auth']['warning'][language].lower() \
            or 'key' in linux['ssh_password_auth']['warning'][language]


def test_commands_are_never_translated():
    # A quoted registry path or a shell flag means the same thing in every
    # language, and translating one silently breaks it.
    english = security_advice.advice_for('en')
    thai = security_advice.advice_for('th')

    for platform in security_advice.PLATFORMS:
        for key, entry in english[platform].items():
            assert entry['command'] == thai[platform][key]['command'], key


def test_thai_is_returned_for_thai_and_english_for_anything_else():
    thai = security_advice.advice_for('th')
    assert thai['windows']['smb1']['label'] == 'ปิดโปรโตคอล SMBv1'

    for language in ('en', 'fr', '', None):
        english = security_advice.advice_for(language)
        assert english['windows']['smb1']['label'] == 'SMBv1 disabled'


def test_a_half_translated_entry_falls_back_field_by_field(monkeypatch):
    # Adding a language should not mean translating all of it before any of
    # it can be used.
    entry = {
        'label': {'en': 'English label', 'th': 'ป้ายไทย'},
        'fix': {'en': 'English fix'},
        'warning': {'en': 'English warning'},
        'command': 'whoami',
    }
    monkeypatch.setitem(security_advice.PLATFORMS, 'windows', {'demo': entry})

    result = security_advice.advice_for('th')['windows']['demo']

    assert result['label'] == 'ป้ายไทย'
    assert result['fix'] == 'English fix'


def test_monitor_types_map_onto_the_right_platform():
    assert security_advice.platform_for('winrm') == 'windows'
    assert security_advice.platform_for('wmi') == 'windows'
    assert security_advice.platform_for('ssh') == 'linux'
    assert security_advice.platform_for('ping') is None
    assert security_advice.platform_for(None) is None


# --- the endpoint ---------------------------------------------------------

def _client():
    app = Flask(__name__)
    app.secret_key = 'test'
    app.register_blueprint(devices_bp)
    return app.test_client()


def test_the_endpoint_serves_the_requested_language():
    response = _client().get('/api/security-advice?lang=th')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['language'] == 'th'
    assert payload['advice']['linux']['ssh_root_login']['label'] == 'จำกัดการล็อกอิน root ผ่าน SSH'


def test_the_endpoint_falls_back_to_english_for_a_language_it_does_not_have():
    payload = _client().get('/api/security-advice?lang=de').get_json()

    assert payload['language'] == 'en'
    assert payload['advice']['linux']['ssh_root_login']['label'] == 'SSH root login restricted'


# --- where the commands are meant to be run -------------------------------

def test_every_platform_says_which_shell_and_what_privilege():
    # Without this the reader has to work out for themselves that
    # Set-SmbServerConfiguration is not something cmd.exe will accept.
    for platform in security_advice.PLATFORMS:
        assert platform in security_advice.RUN_CONTEXT
        for language in security_advice.SUPPORTED_LANGUAGES:
            text = security_advice.RUN_CONTEXT[platform].get(language)
            assert text and text.strip(), '%s has no run context in %s' % (platform, language)

    english = security_advice.run_context_for('en')
    assert 'PowerShell' in english['windows']
    assert 'Administrator' in english['windows']
    assert 'SSH' in english['linux']


def test_the_run_context_is_translated_but_the_shell_name_is_not():
    thai = security_advice.run_context_for('th')

    # "PowerShell" and "SSH" are the names of the things, not English words to
    # be replaced -- translating either would send somebody looking for a
    # program that does not exist.
    assert 'PowerShell' in thai['windows']
    assert 'SSH' in thai['linux']
    assert 'บนเครื่องที่ต้องแก้' in thai['windows']


def test_the_endpoint_sends_the_run_context_alongside_the_advice():
    payload = _client().get('/api/security-advice?lang=th').get_json()

    assert 'PowerShell' in payload['run_context']['windows']
    assert 'บนเครื่องที่ต้องแก้' in payload['run_context']['linux']
