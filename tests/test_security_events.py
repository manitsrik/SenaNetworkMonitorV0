"""Tier 2: reading authentication activity off the hosts."""
from datetime import datetime, timedelta

from config import Config
from monitor import NetworkMonitor


def _monitor():
    return object.__new__(NetworkMonitor)


JOURNAL = '\n'.join([
    '2026-09-18T11:00:00+0700 srv sshd[123]: Failed password for root from 1.2.3.4 port 22 ssh2',
    '2026-09-18T11:00:05+0700 srv sshd[124]: Failed password for invalid user admin from 1.2.3.4 port 22 ssh2',
    '2026-09-18T11:01:00+0700 srv sshd[125]: Accepted publickey for monitorsena from 10.0.0.1 port 5 ssh2',
    '2026-09-18T11:02:00+0700 srv sudo: pam_unix(sudo:auth): authentication failure; '
    'logname=bob uid=1000 euid=0 tty=/dev/pts/0 ruser=bob rhost=  user=bob',
    '2026-09-18T11:02:01+0700 srv sudo: carol : 3 incorrect password attempts ; '
    'TTY=pts/1 ; PWD=/ ; USER=root ; COMMAND=/bin/ls',
])


# --- Linux ----------------------------------------------------------------

def test_the_journal_lines_sshd_actually_writes_all_parse():
    events, truncated, unreadable = _monitor()._parse_linux_events(JOURNAL, 500)

    assert unreadable is None
    assert truncated is False
    assert len(events) == 5
    by_key = {}
    for event in events:
        by_key.setdefault(event['event_key'], []).append(event)
    assert len(by_key['failed_logon']) == 2
    assert len(by_key['sudo_failed']) == 2
    assert by_key['login_success'][0]['account'] == 'monitorsena'


def test_an_invalid_user_attempt_records_the_name_that_was_tried():
    events, _, _ = _monitor()._parse_linux_events(JOURNAL, 500)
    attempted = [e['account'] for e in events if e['event_key'] == 'failed_logon']

    assert attempted == ['root', 'admin']


def test_sudo_failures_record_the_account_not_the_pam_module():
    # pam writes "pam_unix(sudo:auth): authentication failure; ... user=bob".
    # Matching the leading word would have recorded "pam_unix(sudo:auth)" as
    # the account on every sudo failure in the estate.
    events, _, _ = _monitor()._parse_linux_events(JOURNAL, 500)
    accounts = sorted(e['account'] for e in events if e['event_key'] == 'sudo_failed')

    assert accounts == ['bob', 'carol']


def test_ruser_is_not_mistaken_for_user():
    # The pam line carries both "ruser=bob" and "user=bob"; a pattern without
    # a word boundary matches the first and reads the wrong field.
    line = ('2026-09-18T11:02:00+0700 srv sudo: pam_unix(sudo:auth): authentication '
            'failure; logname=x uid=1000 ruser=attacker rhost=  user=victim')
    events, _, _ = _monitor()._parse_linux_events(line, 500)

    assert events[0]['account'] == 'victim'


def test_the_word_boundary_survived_being_written_to_the_file():
    # It did not, once: an escaping slip turned \b into a literal backspace
    # character, and the pattern silently matched nothing at all.
    for key, pattern in NetworkMonitor.LINUX_EVENT_PATTERNS:
        assert '\x08' not in pattern.pattern, key


def test_a_journal_the_account_cannot_read_says_so():
    events, truncated, unreadable = _monitor()._parse_linux_events(
        'unreadable|the journal could not be read by this account', 500)

    assert events == []
    assert unreadable == 'the journal could not be read by this account'


def test_hitting_the_line_cap_is_reported_as_truncated():
    lines = '\n'.join([
        '2026-09-18T11:00:0%d+0700 srv sshd[1]: Failed password for root from 1.2.3.4 port 22 ssh2' % i
        for i in range(5)
    ])
    _, truncated, _ = _monitor()._parse_linux_events(lines, 5)

    assert truncated is True


# --- Windows --------------------------------------------------------------

def test_windows_event_lines_parse_and_carry_the_truncation_marker():
    text = '\n'.join([
        'evt|failed_logon|2026-09-18T11:00:00|administrator|10.0.0.5',
        'evt|log_cleared|2026-09-18T11:05:00||',
        'trunc|1',
    ])

    events, truncated = _monitor()._parse_windows_events(text)

    assert truncated is True
    assert events[0] == {
        'event_key': 'failed_logon',
        'occurred_at': '2026-09-18T11:00:00',
        'account': 'administrator',
        'source': '10.0.0.5',
    }
    assert events[1]['event_key'] == 'log_cleared'


def test_the_windows_script_never_pulls_the_whole_log_into_powershell():
    # Get-WinEvent -LogName Security | Where-Object {...} reads every record
    # before filtering: on the 153,000-record log in this estate that is the
    # difference between 0.6 seconds and scanning the lot.
    script = NetworkMonitor.WINDOWS_EVENTS_SCRIPT

    assert 'FilterHashtable' in script
    assert '| Where-Object' not in script
    assert '-MaxEvents' in script


# --- aggregation ----------------------------------------------------------

def _raw(key, when, account='', source=''):
    return {'event_key': key, 'occurred_at': when, 'account': account, 'source': source}


def test_a_burst_becomes_one_row_not_thousands():
    raw = [_raw('failed_logon', '2026-09-18T11:00:%02d' % i, 'admin', '1.2.3.4')
           for i in range(40)]

    rows = NetworkMonitor._aggregate_security_events(raw, truncated=True)

    assert len(rows) == 1
    assert rows[0]['count'] == 40
    assert rows[0]['first_seen'] == '2026-09-18T11:00:00'
    assert rows[0]['last_seen'] == '2026-09-18T11:00:39'
    assert rows[0]['truncated'] is True


def test_only_a_handful_of_names_are_kept_from_a_sweep():
    # A brute force walking a username list should not write the whole list
    # into the row.
    raw = [_raw('failed_logon', '2026-09-18T11:00:00', 'user%d' % i, '1.2.3.%d' % i)
           for i in range(20)]

    row = NetworkMonitor._aggregate_security_events(raw)[0]

    assert row['count'] == 20
    assert len(row['accounts'].split(', ')) == 5
    assert len(row['sources'].split(', ')) == 5


def test_clearing_the_log_and_creating_an_account_outrank_a_failed_sign_in():
    severity = NetworkMonitor.SECURITY_EVENT_SEVERITY

    assert severity['log_cleared'] == 'critical'
    assert severity['user_created'] == 'critical'
    assert severity['user_deleted'] == 'critical'
    assert severity['failed_logon'] == 'warning'
    assert severity['login_success'] == 'info'


# --- cadence and watermark -------------------------------------------------

def test_collection_waits_for_its_interval(monkeypatch):
    monkeypatch.setattr(Config, 'SECURITY_EVENTS_ENABLED', True)
    monkeypatch.setattr(Config, 'SECURITY_EVENTS_INTERVAL_MINUTES', 15)
    monitor = _monitor()

    assert monitor._security_events_due({'security_events_collected_at': None}) is True
    assert monitor._security_events_due({
        'security_events_collected_at': (datetime.now() - timedelta(minutes=5)).isoformat()
    }) is False
    assert monitor._security_events_due({
        'security_events_collected_at': (datetime.now() - timedelta(minutes=20)).isoformat()
    }) is True


def test_collection_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(Config, 'SECURITY_EVENTS_ENABLED', False)

    assert _monitor()._security_events_due({'security_events_collected_at': None}) is False


def test_reading_resumes_from_the_watermark(monkeypatch):
    monkeypatch.setattr(Config, 'SECURITY_EVENTS_MAX_LOOKBACK_HOURS', 48)
    watermark = datetime.now() - timedelta(hours=1)

    since = _monitor()._security_events_since(
        {'security_events_watermark': watermark.isoformat()})

    assert abs((since - watermark).total_seconds()) < 2


def test_a_long_outage_does_not_ask_for_events_that_no_longer_exist(monkeypatch):
    # The Windows Security log here is circular and holds two to three days,
    # so asking for a fortnight only makes the query scan for records that
    # have already been overwritten.
    monkeypatch.setattr(Config, 'SECURITY_EVENTS_MAX_LOOKBACK_HOURS', 48)
    ancient = (datetime.now() - timedelta(days=14)).isoformat()

    since = _monitor()._security_events_since({'security_events_watermark': ancient})

    assert since > datetime.now() - timedelta(hours=49)


# --- alerting -------------------------------------------------------------

class FakeAlerter:
    def __init__(self):
        self.sent = []

    def trigger_alert(self, device, event_type, message):
        self.sent.append((event_type, message))


def _alerting_monitor():
    monitor = _monitor()
    monitor.alerter = FakeAlerter()
    return monitor


def test_a_burst_produces_one_alert_not_one_per_attempt(monkeypatch):
    monkeypatch.setattr(Config, 'SECURITY_EVENTS_FAILED_LOGIN_ALERT', 10)
    monitor = _alerting_monitor()
    raw = [_raw('failed_logon', '2026-09-18T11:00:%02d' % i, 'admin', '1.2.3.4')
           for i in range(40)]

    monitor._alert_on_security_events(
        {'id': 1, 'name': 'srv'}, NetworkMonitor._aggregate_security_events(raw))

    assert len(monitor.alerter.sent) == 1
    assert '40 failed sign-ins' in monitor.alerter.sent[0][1]


def test_a_few_failed_sign_ins_are_recorded_but_not_alerted(monkeypatch):
    monkeypatch.setattr(Config, 'SECURITY_EVENTS_FAILED_LOGIN_ALERT', 10)
    monitor = _alerting_monitor()
    raw = [_raw('failed_logon', '2026-09-18T11:00:00', 'admin', '1.2.3.4')] * 3

    monitor._alert_on_security_events(
        {'id': 1, 'name': 'srv'}, NetworkMonitor._aggregate_security_events(raw))

    # A mistyped password is not an incident.
    assert monitor.alerter.sent == []


def test_a_cleared_log_always_alerts_however_few():
    monitor = _alerting_monitor()
    raw = [_raw('log_cleared', '2026-09-18T11:00:00')]

    monitor._alert_on_security_events(
        {'id': 1, 'name': 'srv'}, NetworkMonitor._aggregate_security_events(raw))

    assert len(monitor.alerter.sent) == 1
    assert monitor.alerter.sent[0][0] == 'security_event_log_cleared'


def test_each_finding_keeps_its_own_cooldown_key():
    # Sharing one event type would let a cleared log silence a brute force
    # that starts inside the cooldown window.
    monitor = _alerting_monitor()
    raw = [_raw('log_cleared', '2026-09-18T11:00:00'),
           _raw('user_created', '2026-09-18T11:01:00', 'newadmin')]

    monitor._alert_on_security_events(
        {'id': 1, 'name': 'srv'}, NetworkMonitor._aggregate_security_events(raw))

    types = sorted(sent[0] for sent in monitor.alerter.sent)
    assert types == ['security_event_log_cleared', 'security_event_user_created']


def test_a_successful_sign_in_is_recorded_without_waking_anyone():
    monitor = _alerting_monitor()
    raw = [_raw('login_success', '2026-09-18T11:00:00', 'bob', '10.0.0.1')]

    monitor._alert_on_security_events(
        {'id': 1, 'name': 'srv'}, NetworkMonitor._aggregate_security_events(raw))

    assert monitor.alerter.sent == []


# --- the card -------------------------------------------------------------

from pathlib import Path


def _dashboard():
    return (
        Path(__file__).resolve().parents[1] / "templates" / "server_dashboard.html"
    ).read_text(encoding="utf-8")


def _function_body(template, name):
    return template.split("function %s(" % name, 1)[1].split("\nfunction ", 1)[0]


def test_nothing_collected_and_nothing_to_report_read_differently():
    template = _dashboard()
    body = _function_body(template, "renderSecurityEvents")

    assert "(payload && payload.collected_at)" in body
    assert "words.nothing.replace('%h', hours)" in body
    assert ": words.never;" in body
    # And both readings exist in both languages.
    for language in ("en:", "th:"):
        assert language in template
    assert "nothing: 'Nothing recorded in the last %h hours.'" in template
    assert "never: 'No collection has run on this host yet.'" in template
    assert "'ยังไม่เคยเก็บข้อมูลจากเครื่องนี้'" in template


def test_a_capped_collection_admits_the_total_is_higher():
    template = _dashboard()
    body = _function_body(template, "renderSecurityEvents")

    assert "if (event.truncated) facts.push(words.capped);" in body
    assert "capped: 'hit the collection cap, so the real total is higher'" in template


def test_the_events_card_failing_does_not_take_the_page_with_it():
    template = _dashboard()

    assert "renderSecurityEvents(securityEventsRes && securityEventsRes.ok" in template
    assert "renderSecurityEvents(null);" in template


def test_the_card_is_on_the_page_with_its_own_window():
    template = _dashboard()

    assert 'id="security-events"' in template
    assert "Security Events" in template
    assert "security-events?hours=24" in template


# --- analysis and the per-card language toggle ----------------------------

import security_analysis


def test_the_analysis_says_the_same_thing_every_time():
    # An operator has to be able to re-read it and quote it in a ticket, so it
    # is computed from the counts rather than generated afresh each press.
    events = [{'event_key': 'failed_logon', 'event_count': 9,
               'accounts': 'a, b, c', 'sources': '10.0.0.1', 'truncated': False}]

    first = security_analysis.analyse_events(events, 'en')
    second = security_analysis.analyse_events(events, 'en')

    assert first == second


def test_a_source_that_failed_and_also_succeeded_is_called_a_breach():
    # The rule that changes what the page is reporting.
    events = [
        {'event_key': 'failed_logon', 'event_count': 500, 'sources': '172.41.1.249',
         'accounts': 'a, b', 'truncated': False},
        {'event_key': 'login_success', 'event_count': 1, 'sources': '172.41.1.249',
         'accounts': 'Administrator', 'truncated': False},
    ]

    findings = security_analysis.analyse_events(events, 'en')
    critical = [f for f in findings if f['level'] == 'critical']

    assert critical, 'a success from an address that has been failing must be critical'
    assert 'SUCCEEDED' in critical[0]['text']


def test_many_account_names_read_as_a_wordlist_not_a_stale_password():
    events = [{'event_key': 'failed_logon', 'event_count': 40, 'sources': '10.0.0.1',
               'accounts': ', '.join('user%d' % i for i in range(12)), 'truncated': False}]

    text = ' '.join(f['text'] for f in security_analysis.analyse_events(events, 'en'))

    assert 'wordlist' in text
    assert 'retries the same name' in text


def test_a_backfill_window_does_not_set_the_reported_rate():
    # The first collection reaches back as far as the lookback allows and
    # stops at the cap; counting it would report a rate the host never saw.
    events = [
        {'event_key': 'failed_logon', 'event_count': 500, 'sources': '10.0.0.1',
         'accounts': 'a', 'truncated': True},
        {'event_key': 'failed_logon', 'event_count': 10, 'sources': '10.0.0.1',
         'accounts': 'a', 'truncated': False},
        {'event_key': 'failed_logon', 'event_count': 9, 'sources': '10.0.0.1',
         'accounts': 'a', 'truncated': False},
    ]

    first = security_analysis.analyse_events(events, 'en')[0]['text']

    assert 'average about 10' in first
    assert '173' not in first


def test_both_languages_answer_and_neither_is_empty():
    events = [{'event_key': 'failed_logon', 'event_count': 9, 'sources': '10.0.0.1',
               'accounts': 'a, b', 'truncated': False}]

    for language in ('en', 'th'):
        findings = security_analysis.analyse_events(events, language)
        assert findings
        for finding in findings:
            assert finding['text'].strip()


def test_a_reachable_unpatched_host_is_read_as_one_problem_not_two():
    checks = [
        {'key': 'smb1', 'label': 'SMBv1 disabled', 'state': 'fail'},
        {'key': 'patch_age', 'label': 'Patched recently', 'state': 'fail',
         'detail': 'Newest update KB4048953 installed 3150 days ago'},
    ]

    text = ' '.join(f['text'] for f in security_analysis.analyse_posture(checks, 'en'))

    assert 'published vulnerabilities still work' in text
    assert '3150' in text


def test_each_card_keeps_its_own_language():
    template = _dashboard()

    assert 'data-lang-card="posture"' in template
    assert 'data-lang-card="events"' in template
    assert "localStorage.setItem('securityLang.' + card, lang)" in template
    # Storage throws in a private window; the card still has to render.
    assert "// Not being able to remember the choice is not a reason to refuse it." in template


def test_the_analyse_panel_opens_and_closes_without_refetching_the_page():
    template = _dashboard()
    body = _function_body(template, "toggleAnalysis")

    assert 'data-analyse-card="posture"' in template
    assert 'data-analyse-card="events"' in template
    assert "securityAnalysisOpen[card] = !securityAnalysisOpen[card];" in body
    assert "security-analysis?lang=" in body


def test_the_monitors_own_sign_ins_are_not_recorded_as_events():
    # The monitor signs in every few minutes. Left in, its own sessions were
    # the whole card on every Linux host -- "root from 172.22.21.9" over and
    # over, which is the monitor letting itself in.
    events = [
        {'event_key': 'login_success', 'account': 'root', 'source': '172.22.21.9'},
        {'event_key': 'login_success', 'account': 'alice', 'source': '10.0.0.4'},
        {'event_key': 'failed_logon', 'account': 'root', 'source': '1.2.3.4'},
    ]

    kept = NetworkMonitor._drop_monitor_own_logins(events, 'root')

    assert [e['account'] for e in kept] == ['alice', 'root']
    # Only the success is dropped: the monitor failing to sign in is worth
    # knowing about, and it is a different event.
    assert kept[1]['event_key'] == 'failed_logon'


def test_dropping_own_logins_is_case_insensitive_and_safe_without_an_account():
    events = [{'event_key': 'login_success', 'account': 'MonitorSena', 'source': '127.0.0.1'}]

    assert NetworkMonitor._drop_monitor_own_logins(events, 'monitorsena') == []
    assert NetworkMonitor._drop_monitor_own_logins(events, None) == events
    assert NetworkMonitor._drop_monitor_own_logins(events, '') == events


def test_the_collectors_pass_the_account_they_signed_in_with():
    import inspect

    for name in ('_collect_ssh_security_events', '_collect_winrm_security_events'):
        signature = inspect.signature(getattr(NetworkMonitor, name))
        assert 'own_account' in signature.parameters, name

    source = inspect.getsource(NetworkMonitor.check_ssh)
    assert 'own_account=username' in source
    source = inspect.getsource(NetworkMonitor.check_winrm)
    assert 'own_account=username' in source


def test_the_language_control_is_two_flags_not_one_guessable_toggle():
    # A single flag has to mean either the language you have or the one you
    # would get, and every reader guesses differently. The sidebar already
    # shows both and dims the inactive one.
    template = _dashboard()

    assert 'data-lang-set="en"' in template
    assert 'data-lang-set="th"' in template
    assert '<span class="fi fi-us"></span>' in template
    assert '<span class="fi fi-th"></span>' in template
    assert "flag.classList.toggle('is-active'," in template


def test_pressing_the_flag_already_selected_does_nothing():
    body = _function_body(_dashboard(), "paintLanguageFlags")

    assert "flag.getAttribute('data-lang-set') === current" in body
    assert "if (!card || readCardLang(card) === next) return;" in _dashboard()


def test_the_events_list_fills_the_card_instead_of_scrolling_in_a_short_box():
    # The card stretches to match the posture card beside it in the grid row.
    # A fixed max-height left the list scrolling inside 260px with the rest of
    # the card empty below it.
    template = _dashboard()

    assert 'id="security-events-card"' in template
    assert "max-height: 260px;" not in template
    assert "#security-events-card .security-event-list {" in template
    # Without min-height: 0 a flex child refuses to shrink, and the list pushes
    # the card taller instead of scrolling inside it.
    assert template.count("min-height: 0;") >= 2


# --- the per-event explanation --------------------------------------------

import security_event_guide


def test_every_event_the_collector_can_report_has_an_explanation():
    # A row nobody can expand is worse than no arrow at all, and a new event
    # type added to the collector should fail here until it is written.
    assert set(security_event_guide.EVENTS) == set(NetworkMonitor.SECURITY_EVENT_SEVERITY)


def test_every_explanation_answers_the_same_four_questions_in_both_languages():
    for key, entry in security_event_guide.EVENTS.items():
        for section in security_event_guide.SECTIONS:
            for language in security_event_guide.SUPPORTED_LANGUAGES:
                text = (entry.get(section) or {}).get(language)
                assert text and text.strip(), '%s has no %s in %s' % (key, section, language)


def test_the_four_questions_are_asked_in_the_order_somebody_reads_them():
    # Where it came from, how it happens, what it does, what to do. Somebody
    # reading their fifth one should know where their answer will be.
    assert security_event_guide.SECTIONS == ('origin', 'mechanism', 'risk', 'fix')


def test_a_failed_sign_in_explains_the_thing_that_changes_the_verdict():
    entry = security_event_guide.guide_for('en')['events']['failed_logon']

    # The single most useful next step is to find out whether any of it worked.
    assert 'succeeded' in entry['fix']
    assert 'lockout' in entry['fix']


def test_clearing_the_log_points_at_the_copy_that_survived_it():
    # The host's own record is gone; this monitor's is not, and that is the
    # whole reason the events are stored here.
    for language in ('en', 'th'):
        text = security_event_guide.guide_for(language)['events']['log_cleared']['fix']
        assert 'monitor' in text


def test_a_new_service_is_not_advised_to_be_deleted_on_sight():
    # Deleting destroys the image path and the binary, which is what an
    # investigation needs.
    entry = security_event_guide.guide_for('en')['events']['service_installed']

    assert 'do not just delete it' in entry['fix']


def test_the_guide_falls_back_to_english_for_a_language_it_does_not_have():
    assert security_event_guide.guide_for('de')['events']['log_cleared']['risk'] == \
        security_event_guide.guide_for('en')['events']['log_cleared']['risk']


def test_each_event_row_opens_onto_its_explanation():
    template = _dashboard()
    body = _function_body(template, "renderEventGuide")

    assert "const guide = renderEventGuide(event.event_key);" in template
    assert "<summary>${head}</summary>" in template
    assert "const bundle = cachedAdvice('events');" in body
    assert "(guide.sections || [])" in body
    # A row with nothing to say stays a plain row rather than an arrow that
    # opens onto nothing.
    assert 'if (!guide) {' in template


def test_what_to_do_is_not_left_in_the_same_grey_as_the_explanation():
    template = _dashboard()

    assert "section.key === 'fix' ? 'is-fix' : ''" in template
    assert ".security-event-guide section.is-fix {" in template


def test_one_card_in_thai_does_not_leave_the_other_in_the_wrong_language():
    # The two cards each have their own flag, so nothing may hold "the current
    # language". A shared securityAdvice / securityEventGuide pair meant
    # whichever card loaded last won, and switching only the events card to
    # Thai left its explanations in English.
    template = _dashboard()

    assert "function cachedAdvice(card) {" in template
    assert "securityAdviceByLang[readCardLang(card)] || null;" in template
    assert "const bundle = cachedAdvice('posture');" in template
    assert "const bundle = cachedAdvice('events');" in template
    # No global holding one language for both cards.
    assert "let securityEventGuide" not in template
    assert "let securityRunContext" not in template
    assert "securityAdvice = securityAdviceByLang" not in template


def test_switching_either_card_loads_that_language_before_rendering():
    template = _dashboard()

    # The events card's explanations come from the same fetch as the posture
    # card's advice, so both need the load, not just posture.
    assert "await loadSecurityAdvice(next);\n        if (card === 'posture') {" in template
    assert "async function loadSecurityAdviceForCards() {" in template


def test_no_stray_markdown_in_text_that_is_rendered_as_plain_text():
    # The page escapes these strings, so an asterisk pair meant as emphasis
    # arrives on screen as literal asterisks. It did, in the Thai for
    # "succeeded", which is the word that most needed to read cleanly.
    import security_advice
    import security_analysis

    sources = []
    for module in (security_event_guide, security_advice, security_analysis):
        sources.append(open(module.__file__, encoding='utf-8').read())
    for text in sources:
        body = text.split('"""', 2)[-1]
        assert '**' not in body, 'markdown emphasis will render literally'


def test_the_thai_is_broken_into_paragraphs_and_the_page_shows_them():
    template = _dashboard()

    # Written with a blank line where the thought changes; without pre-line
    # they arrive as one wall of text.
    assert ".security-event-guide section > div {" in template
    assert "white-space: pre-line;" in template

    paragraphed = [
        key for key, entry in security_event_guide.EVENTS.items()
        if any('\n\n' in (entry[section].get('th') or '')
               for section in security_event_guide.SECTIONS)
    ]
    assert len(paragraphed) >= 6, 'most explanations should be broken up'


def test_the_thai_does_not_read_as_one_long_sentence():
    # A single unbroken clause chain is how a translation reads and how Thai
    # does not. Nothing here should run past a comfortable line.
    for key, entry in security_event_guide.EVENTS.items():
        for section in security_event_guide.SECTIONS:
            for part in (entry[section]['th'] or '').split('\n\n'):
                assert len(part) <= 220, '%s/%s has a %d-character run-on' % (
                    key, section, len(part))


# --- successful network sign-ins on Windows -------------------------------

def test_windows_now_collects_the_event_that_turns_an_attempt_into_a_breach():
    # Without 4624 the "failed and also succeeded from the same address" rule
    # can never fire on Windows. That is why the intrusion found on 2026-09-18
    # had to be dug out of the event log by hand.
    script = NetworkMonitor.WINDOWS_EVENTS_SCRIPT

    assert 'Id=4624' in script
    assert "Emit 'login_success'" in script


def test_the_noisy_kinds_of_success_are_dropped_on_the_host_not_over_the_wire():
    # 4624 is the highest-volume event in the log. Measured at 51-58 per
    # fifteen minutes here, of which the interesting ones were a handful.
    script = NetworkMonitor.WINDOWS_EVENTS_SCRIPT

    assert "if ($type -ne '3') { continue }" in script
    assert "$user -eq 'ANONYMOUS LOGON'" in script
    assert "$user.EndsWith('$')" in script
    assert "$src -eq '127.0.0.1'" in script


def test_dropping_the_monitors_own_sign_ins_needs_the_address_too():
    # The monitor signs in to some hosts as Administrator. Matching on the
    # name alone would have filtered away an intruder using that same name
    # from their own machine, which is exactly the event that matters most.
    monitor = _monitor()
    own = sorted(NetworkMonitor._own_addresses())[0]

    events = [
        {'event_key': 'login_success', 'account': 'Administrator', 'source': '127.0.0.1'},
        {'event_key': 'login_success', 'account': 'Administrator', 'source': '172.41.1.249'},
    ]
    kept = NetworkMonitor._drop_monitor_own_logins(events, 'Administrator')

    assert len(kept) == 1
    assert kept[0]['source'] == '172.41.1.249', 'an intruder reusing the name must survive'
    assert own  # the monitor knows at least one address of its own


def test_an_address_the_monitor_cannot_recognise_keeps_the_event():
    # Wrong in the safe direction: noise is recoverable, a hidden sign-in is
    # not.
    events = [{'event_key': 'login_success', 'account': 'svc', 'source': '10.9.9.9'}]

    assert NetworkMonitor._drop_monitor_own_logins(events, 'svc') == events


def test_the_monitor_finds_its_own_addresses_and_accepts_more_from_config(monkeypatch):
    NetworkMonitor._own_addresses_cache = None
    monkeypatch.setattr(Config, 'SECURITY_EVENTS_IGNORE_SOURCES', ['203.0.113.7'])
    try:
        found = NetworkMonitor._own_addresses()
        assert '127.0.0.1' in found
        assert '203.0.113.7' in found, 'a NAT or second path can be added by hand'
    finally:
        NetworkMonitor._own_addresses_cache = None
