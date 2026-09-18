import base64
import inspect
from datetime import datetime, timedelta

from config import Config
from monitor import NetworkMonitor


def _monitor():
    return object.__new__(NetworkMonitor)


class FakeWinRMResponse:
    def __init__(self, stdout='', status_code=0, stderr=b''):
        self.status_code = status_code
        self.std_out = stdout.encode('utf-8') if isinstance(stdout, str) else stdout
        self.std_err = stderr


class FakeWinRMSession:
    """Answers each fragment by what it contains, and records every script."""

    def __init__(self, responses=None, default=None):
        self.responses = responses or {}
        self.default = default if default is not None else FakeWinRMResponse('')
        self.scripts = []

    def run_ps(self, script):
        self.scripts.append(script)
        for needle, response in self.responses.items():
            if needle in script:
                return response
        return self.default


class FakeSSHStream:
    def __init__(self, data):
        self.data = data

    def read(self):
        return self.data


class FakeSSHClient:
    def __init__(self, stdout=b'', stderr=b''):
        self.stdout = stdout
        self.stderr = stderr
        self.command = None

    def exec_command(self, command):
        self.command = command
        return None, FakeSSHStream(self.stdout), FakeSSHStream(self.stderr)


def _checks(*states):
    return [
        NetworkMonitor._security_check('c%d' % i, 'Check %d' % i, state)
        for i, state in enumerate(states)
    ]


# --- scoring --------------------------------------------------------------

def test_a_check_that_could_not_be_read_is_not_counted_as_a_pass():
    # The monitoring account is often refused these states. Scoring an
    # unreadable check as a pass would let a host the monitor cannot see
    # into outrank one it can, which is exactly backwards.
    verdict = NetworkMonitor._score_security_checks(_checks('pass', 'pass', 'unknown'))

    assert verdict['score'] == 100.0
    assert verdict['pass_count'] == 2
    assert verdict['unknown_count'] == 1
    assert verdict['state'] == 'ok'


def test_a_host_whose_every_check_is_unreadable_scores_nothing_at_all():
    verdict = NetworkMonitor._score_security_checks(_checks('unknown', 'unknown'))

    assert verdict['state'] == 'unknown'
    assert verdict['score'] is None
    assert verdict['error'] == 'No security check could be read'


def test_one_failing_check_outweighs_any_number_of_passes():
    # Five passes do not cancel out a disabled firewall, so the arithmetic
    # never decides the verdict on its own.
    verdict = NetworkMonitor._score_security_checks(
        _checks('pass', 'pass', 'pass', 'pass', 'pass', 'fail'))

    assert verdict['state'] == 'risk'
    assert verdict['fail_count'] == 1
    assert verdict['score'] > 80


def test_a_warning_is_worth_half_a_pass():
    verdict = NetworkMonitor._score_security_checks(_checks('pass', 'warn'))

    assert verdict['score'] == 75.0
    assert verdict['state'] == 'warn'


def test_a_sweep_that_did_not_finish_cannot_report_a_clean_bill_of_health():
    # Found on a real Windows host: every command failed, the one free check
    # that needs no command passed, and the host was reported as 100% and
    # healthy. An absence of findings is not evidence when the checks never
    # ran.
    verdict = NetworkMonitor._score_security_checks(
        _checks('pass'), error='The command line is too long.')

    assert verdict['state'] == 'unknown'
    assert verdict['score'] is None


def test_a_positive_finding_survives_an_incomplete_sweep():
    # The other half of the same rule: what the sweep did manage to see is
    # still true, so a check that actually failed stays a finding.
    verdict = NetworkMonitor._score_security_checks(
        _checks('fail', 'unknown'), error='session lost')

    assert verdict['state'] == 'risk'


# --- Windows --------------------------------------------------------------

# Windows caps a command line near 8191 characters and WinRM sends each
# script as `powershell -EncodedCommand <base64 UTF-16LE>`, which is about
# 2.7x its length. A single script holding every check went over that and the
# whole sweep came back "The command line is too long." The margin below
# leaves room for the prefix and for a site that lengthens the antivirus
# service list.
ENCODED_LIMIT = 7000


def _encoded_lengths(monitor):
    return {
        keys: len(base64.b64encode(
            monitor._apply_security_thresholds(fragment).encode('utf-16-le')).decode())
        for keys, fragment in NetworkMonitor.WINDOWS_SECURITY_FRAGMENTS
    }


def test_no_windows_fragment_can_overflow_the_windows_command_line():
    for keys, length in _encoded_lengths(_monitor()).items():
        assert length < ENCODED_LIMIT, '%s encodes to %d' % (','.join(keys), length)


def test_a_site_that_names_more_antivirus_products_still_fits(monkeypatch):
    # The antivirus fragment is the longest one and grows with this setting,
    # so it is the one that would quietly cross the limit again.
    monkeypatch.setattr(
        Config, 'SECURITY_ANTIVIRUS_SERVICES',
        '|'.join('SomeVendorAgentService%02d' % i for i in range(40)))

    for keys, length in _encoded_lengths(_monitor()).items():
        assert length < ENCODED_LIMIT, '%s encodes to %d' % (','.join(keys), length)


def test_windows_sweep_reports_each_fragment_and_keeps_the_reboot_finding():
    session = FakeWinRMSession(responses={
        'Get-NetFirewallProfile': FakeWinRMResponse('firewall|fail|Disabled profiles: Public\n'),
        'Get-MpComputerStatus': FakeWinRMResponse(
            'av_realtime|pass|Real-time protection is on\n'
            'av_signature|warn|Signatures are 9 days old\n'),
    })

    verdict = NetworkMonitor._check_winrm_security(_monitor(), session, pending_reboot=True)

    by_key = {check['key']: check for check in verdict['checks']}
    assert by_key['firewall']['state'] == 'fail'
    assert by_key['firewall']['detail'] == 'Disabled profiles: Public'
    assert by_key['av_signature']['state'] == 'warn'
    # The reboot flag comes free from the metric pass, so it costs no extra
    # round trip but still counts as a finding.
    assert verdict['checks'][0]['key'] == 'pending_reboot'
    assert verdict['checks'][0]['state'] == 'warn'
    assert verdict['state'] == 'risk'


def test_a_fragment_that_says_nothing_leaves_its_checks_unreadable():
    # A silent fragment must not shorten the list. A report that simply
    # omits what it could not read looks tidier than one that says so, and
    # reads as if those checks had passed.
    session = FakeWinRMSession(responses={
        'Get-NetFirewallProfile': FakeWinRMResponse('firewall|pass|All 3 profiles are enabled\n'),
    })

    verdict = NetworkMonitor._check_winrm_security(_monitor(), session, pending_reboot=False)

    by_key = {check['key']: check for check in verdict['checks']}
    for key in NetworkMonitor.WINDOWS_SECURITY_LABELS:
        assert key in by_key
    assert by_key['patch_age']['state'] == 'unknown'
    assert by_key['guest_account']['state'] == 'unknown'
    assert verdict['state'] == 'ok'
    assert verdict['unknown_count'] == 6


def test_one_broken_fragment_does_not_cost_the_others():
    session = FakeWinRMSession(
        responses={
            'Get-HotFix': FakeWinRMResponse('', status_code=1, stderr=b'access denied'),
        },
        default=FakeWinRMResponse('firewall|pass|All 3 profiles are enabled\n'),
    )

    verdict = NetworkMonitor._check_winrm_security(_monitor(), session, pending_reboot=False)

    by_key = {check['key']: check for check in verdict['checks']}
    assert by_key['patch_age']['state'] == 'unknown'
    assert 'access denied' in by_key['patch_age']['detail']
    assert by_key['firewall']['state'] == 'pass'
    # Not every fragment failed, so the sweep as a whole still has a verdict.
    assert verdict['error'] is None


def test_windows_sweep_thresholds_come_from_config(monkeypatch):
    monkeypatch.setattr(Config, 'SECURITY_SIGNATURE_WARN_DAYS', 3)
    monkeypatch.setattr(Config, 'SECURITY_PATCH_WARN_DAYS', 20)
    monkeypatch.setattr(Config, 'SECURITY_PATCH_FAIL_DAYS', 40)
    session = FakeWinRMSession()

    NetworkMonitor._check_winrm_security(_monitor(), session)

    joined = '\n'.join(session.scripts)
    assert '$age -gt 3' in joined
    assert '$d -ge 40' in joined
    assert '$d -ge 20' in joined
    assert '__PATCH_WARN_DAYS__' not in joined


def test_windows_sweep_failure_reports_the_error_without_raising():
    session = FakeWinRMSession(
        default=FakeWinRMResponse('', status_code=1, stderr=b'The command line is too long.'))

    verdict = NetworkMonitor._check_winrm_security(_monitor(), session, pending_reboot=False)

    assert verdict['error'] == 'The command line is too long.'
    assert verdict['state'] == 'unknown'
    assert verdict['score'] is None


# --- Linux ----------------------------------------------------------------

def test_linux_sweep_reads_one_line_per_check():
    client = FakeSSHClient(stdout=(
        b'firewall|pass|ufw is active\n'
        b'ssh_root_login|fail|PermitRootLogin yes\n'
        b'patch_updates|warn|3 updates are pending, none flagged security\n'
    ))

    verdict = NetworkMonitor._check_ssh_security(_monitor(), client, pending_reboot=False)

    by_key = {check['key']: check for check in verdict['checks']}
    assert by_key['ssh_root_login']['state'] == 'fail'
    assert by_key['ssh_root_login']['detail'] == 'PermitRootLogin yes'
    # The shell emits keys; the wording is applied on this side.
    assert by_key['firewall']['label'] == 'Host firewall active'
    # Keys the shell never reached are listed as unreadable, not dropped.
    assert by_key['empty_passwords']['state'] == 'unknown'
    assert verdict['state'] == 'risk'


def test_linux_sweep_treats_a_permission_error_as_unreadable_not_as_a_finding():
    # ufw, iptables and /etc/shadow are all root-only on a normal host. A
    # monitoring account that is refused the answer must not be able to
    # raise an alarm that looks like a firewall somebody switched off.
    client = FakeSSHClient(stdout=(
        b'firewall|unknown|ufw status could not be read; it usually needs root\n'
        b'empty_passwords|unknown|/etc/shadow is not readable; it needs root\n'
        b'root_equivalent_accounts|pass|root is the only UID 0 account\n'
    ))

    verdict = NetworkMonitor._check_ssh_security(_monitor(), client, pending_reboot=False)

    assert verdict['state'] == 'ok'
    assert verdict['fail_count'] == 0
    assert verdict['pass_count'] == 2


def test_linux_sweep_with_no_output_reports_why():
    client = FakeSSHClient(stdout=b'', stderr=b'Permission denied')

    verdict = NetworkMonitor._check_ssh_security(_monitor(), client, pending_reboot=None)

    assert verdict['error'] == 'Permission denied'
    assert verdict['state'] == 'unknown'
    assert verdict['score'] is None


def test_ssh_password_login_severity_follows_the_configured_policy(monkeypatch):
    monkeypatch.setattr(Config, 'SECURITY_SSH_PASSWORD_AUTH_IS_FAILURE', False)
    assert 'emit ssh_password_auth warn ' in NetworkMonitor._linux_security_script(_monitor())

    monkeypatch.setattr(Config, 'SECURITY_SSH_PASSWORD_AUTH_IS_FAILURE', True)
    script = NetworkMonitor._linux_security_script(_monitor())
    assert 'emit ssh_password_auth fail ' in script
    assert '__SSH_PASSWORD_STATE__' not in script


# --- cadence --------------------------------------------------------------

def test_the_sweep_runs_on_its_own_clock_not_on_every_poll(monkeypatch):
    monkeypatch.setattr(Config, 'SECURITY_CHECK_ENABLED', True)
    monkeypatch.setattr(Config, 'SECURITY_CHECK_INTERVAL_HOURS', 6)
    monitor = _monitor()

    assert monitor._security_check_due({'security_checked_at': None}) is True
    assert monitor._security_check_due({
        'security_checked_at': (datetime.now() - timedelta(hours=1)).isoformat()
    }) is False
    assert monitor._security_check_due({
        'security_checked_at': (datetime.now() - timedelta(hours=7)).isoformat()
    }) is True


def test_the_sweep_can_be_switched_off_entirely(monkeypatch):
    monkeypatch.setattr(Config, 'SECURITY_CHECK_ENABLED', False)

    assert _monitor()._security_check_due({'security_checked_at': None}) is False


# --- antivirus on a server, where neither direct question can be asked ----

def test_a_running_antivirus_service_answers_the_check():
    checks = NetworkMonitor._antivirus_from_services(
        _monitor(), 'Spooler,WinDefend,W32Time')

    by_key = {check['key']: check for check in checks}
    assert by_key['av_realtime']['state'] == 'pass'
    assert 'WinDefend' in by_key['av_realtime']['detail']
    # Nothing in this path reports how old the definitions are, and guessing
    # would be worse than saying so.
    assert by_key['av_signature']['state'] == 'unknown'


def test_no_antivirus_service_at_all_is_a_finding_not_a_shrug():
    # Five Windows Servers in this estate reach exactly this branch: no
    # Defender module, no Security Center, and nothing antivirus-shaped
    # running. That is a real answer, so it is reported as one.
    checks = NetworkMonitor._antivirus_from_services(
        _monitor(), 'Spooler,W32Time,LanmanServer')

    by_key = {check['key']: check for check in checks}
    assert by_key['av_realtime']['state'] == 'fail'
    # The detail says what was searched, so a site whose product runs under
    # another name can see why the answer is wrong and fix the setting.
    assert 'known antivirus service names' in by_key['av_realtime']['detail']
    assert '3 running services' in by_key['av_realtime']['detail']


def test_the_antivirus_names_come_from_config(monkeypatch):
    # The setting names services as Windows registers them, with the version
    # suffix optional. It is deliberately not a substring match any more:
    # that is what let 'avp' answer for 'avpsus'.
    monkeypatch.setattr(Config, 'SECURITY_ANTIVIRUS_SERVICES', 'HouseBrandShield')

    checks = NetworkMonitor._antivirus_from_services(
        _monitor(), 'Spooler,HouseBrandShield')
    assert checks[0]['state'] == 'pass'

    checks = NetworkMonitor._antivirus_from_services(
        _monitor(), 'Spooler,HouseBrandShield.2026.1')
    assert checks[0]['state'] == 'pass', 'a version suffix is still the same product'

    checks = NetworkMonitor._antivirus_from_services(
        _monitor(), 'Spooler,HouseBrandShieldUpdater')
    assert checks[0]['state'] == 'fail', 'a different service is a different service'

    checks = NetworkMonitor._antivirus_from_services(_monitor(), 'Spooler,WinDefend')
    assert checks[0]['state'] == 'fail'


def test_the_service_list_is_matched_here_not_pasted_into_the_script():
    # Pasting the pattern into PowerShell made the fragment grow with the
    # setting, back towards the command-line limit that had already broken
    # the sweep once. The script now hands back names and Python decides.
    fragment = dict(
        (keys, text) for keys, text in NetworkMonitor.WINDOWS_SECURITY_FRAGMENTS
    )[('av_realtime', 'av_signature')]

    assert '__AV_SERVICES__' not in fragment
    assert '"av_services|ok|$((Get-Service' in fragment


def test_a_server_without_defender_still_gets_an_antivirus_verdict():
    session = FakeWinRMSession(responses={
        'Get-MpComputerStatus': FakeWinRMResponse('av_services|ok|Spooler,W32Time\n'),
    })

    verdict = NetworkMonitor._check_winrm_security(_monitor(), session, pending_reboot=False)

    by_key = {check['key']: check for check in verdict['checks']}
    assert by_key['av_realtime']['state'] == 'fail'
    assert verdict['state'] == 'risk'


def test_a_real_defender_answer_beats_the_inference():
    session = FakeWinRMSession(responses={
        'Get-MpComputerStatus': FakeWinRMResponse(
            'av_realtime|pass|Microsoft Defender real-time protection is on\n'
            'av_signature|pass|Defender signatures are 0 days old\n'
            'av_services|ok|Spooler\n'),
    })

    verdict = NetworkMonitor._check_winrm_security(_monitor(), session, pending_reboot=False)

    by_key = {check['key']: check for check in verdict['checks']}
    assert by_key['av_realtime']['state'] == 'pass'
    assert 'Defender' in by_key['av_realtime']['detail']


# --- the Linux checks try sudo before giving up ---------------------------

def test_root_only_checks_go_through_sudo_when_it_is_allowed():
    script = NetworkMonitor._linux_security_script(_monitor())

    # sudo -n never prompts, so a host that refuses it fails fast and the
    # command runs unprivileged instead of hanging the whole sweep.
    assert 'elif sudo -n true 2>/dev/null; then' in script
    assert 'out=$(run_priv ufw status)' in script
    assert 'out=$(run_priv iptables -S)' in script


def test_the_unreadable_message_says_what_to_grant():
    script = NetworkMonitor._linux_security_script(_monitor())

    assert "sudo -n /usr/sbin/ufw status" in script
    # Never suggest sudo access to awk: that is full root by another name.
    assert "/etc/shadow needs root" in script
    assert "sudo -n /usr/bin/awk" not in script


def test_no_password_hash_ever_crosses_the_wire():
    script = NetworkMonitor._linux_security_script(_monitor())

    # The awk runs on the host and prints only account names. The END marker
    # is what separates "no empty passwords" from "could not open the file",
    # which are otherwise both silent.
    assert 'run_priv awk -F: \'($2==""){print "EMPTY:"$1} END{print "READ_OK"}\' /etc/shadow' in script
    assert '*READ_OK*)' in script
    assert 'cat /etc/shadow' not in script


# --- asking for a sweep now -----------------------------------------------

def test_a_host_swept_minutes_ago_is_not_due_on_the_schedule(monkeypatch):
    # Which is the whole problem: the interval is measured from a timestamp in
    # the database, so after fixing something there was no way to ask again.
    # Restarting the monitor does not reset it, and the existing "check now"
    # button honours it too.
    monkeypatch.setattr(Config, 'SECURITY_CHECK_ENABLED', True)
    monkeypatch.setattr(Config, 'SECURITY_CHECK_INTERVAL_HOURS', 6)

    assert _monitor()._security_check_due(
        {'security_checked_at': datetime.now().isoformat()}) is False


def test_check_device_can_be_told_to_sweep_anyway():
    signature = inspect.signature(NetworkMonitor.check_device)

    assert 'force_security' in signature.parameters
    assert signature.parameters['force_security'].default is False


def test_both_collectors_honour_the_force_flag():
    source = inspect.getsource(NetworkMonitor.check_device)

    # Windows and Linux both, or the button would work on half the estate.
    assert source.count(
        'collect_security=force_security or self._security_check_due(device)') == 2


# --- telling an antivirus engine from its updater -------------------------

def test_an_updater_running_alone_is_a_failure_not_a_pass():
    # Found on a compromised host: Kaspersky's AVP scanning service was
    # stopped while avpsus kept updating definitions, and the check reported
    # the host as protected. It was not.
    checks = NetworkMonitor._antivirus_from_services(
        _monitor(), 'Spooler,avpsus,klnagent,W32Time')
    realtime = next(c for c in checks if c['key'] == 'av_realtime')

    assert realtime['state'] == 'fail'
    assert 'installed but not running' in realtime['detail']
    assert 'avpsus' in realtime['detail']


def test_a_substring_no_longer_answers_for_the_service_it_is_inside():
    # The root cause: 'avp' is inside 'avpsus', so a substring match let the
    # updater stand in for the engine.
    assert 'avp' in 'avpsus'
    assert NetworkMonitor._service_tokens('avpsus') == {'avpsus'}
    assert NetworkMonitor._service_tokens('AVP') == {'avp'}
    assert NetworkMonitor._service_tokens('avpsus') & NetworkMonitor._service_tokens('AVP') == set()


def test_a_versioned_service_name_still_matches_its_product():
    # Kaspersky registers as AVP on one host and AVP.KES.21.19 on another.
    assert 'avp' in NetworkMonitor._service_tokens('AVP.KES.21.19')

    checks = NetworkMonitor._antivirus_from_services(
        _monitor(), 'Spooler,AVP.KES.21.19,avpsus.KES.21.19')
    realtime = next(c for c in checks if c['key'] == 'av_realtime')

    assert realtime['state'] == 'pass'
    assert 'AVP.KES.21.19' in realtime['detail']
    # The updater is not offered as evidence of protection.
    assert 'avpsus' not in realtime['detail']


def test_nothing_running_still_reads_as_nothing_installed():
    checks = NetworkMonitor._antivirus_from_services(
        _monitor(), 'Spooler,W32Time,LanmanServer')
    realtime = next(c for c in checks if c['key'] == 'av_realtime')

    assert realtime['state'] == 'fail'
    assert 'No antivirus found' in realtime['detail']


def test_the_two_service_lists_do_not_overlap():
    # A name in both would make the engine test answer for the updater again.
    import re as _re

    def names(pattern):
        return {p.strip().lower() for p in _re.split(r'[|,]', pattern) if p.strip()}

    engines = names(Config.SECURITY_ANTIVIRUS_SERVICES)
    helpers = names(Config.SECURITY_ANTIVIRUS_HELPER_SERVICES)

    assert engines & helpers == set()
    assert 'avp' in engines and 'avpsus' in helpers
