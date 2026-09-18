"""Read a host's security findings and say what they add up to.

Deterministic on purpose. The project's own assistant is rule-based and
bilingual, and a security assessment is exactly the wrong place for an answer
that varies between presses of the same button: an operator has to be able to
re-read it, quote it in a ticket, and get the same words.

Every conclusion here is drawn from counts that are on screen anyway. What it
adds is the part a table cannot show -- that nine failed sign-ins in one
window and nine in the next is a sustained attempt rather than someone
mistyping, that four hundred account names is a wordlist rather than a
misconfigured service, and that a source which has been failing and has also
succeeded is no longer an attempt at all.
"""

CRITICAL = 'critical'
WARNING = 'warning'
INFO = 'info'

DEFAULT_LANGUAGE = 'en'
SUPPORTED_LANGUAGES = ('en', 'th')

# A wordlist walking common account names looks nothing like a service with a
# stale password, which retries one name for ever. This is where one stops
# looking like the other.
SPRAY_ACCOUNT_THRESHOLD = 8
SUSTAINED_WINDOWS = 3
STALE_PATCH_DAYS = 365


def _text(language, thai, english):
    return thai if language == 'th' else english


def _finding(level, language, thai, english):
    return {'level': level, 'text': _text(language, thai, english)}


def _split(value):
    return [part.strip() for part in str(value or '').split(',') if part.strip() and part.strip() != '-']


def _collect(rows, field):
    seen = []
    for row in rows:
        for item in _split(row.get(field)):
            if item not in seen:
                seen.append(item)
    return seen


def analyse_events(events, language=DEFAULT_LANGUAGE):
    """What the collected sign-in activity amounts to."""
    if language not in SUPPORTED_LANGUAGES:
        language = DEFAULT_LANGUAGE
    events = list(events or [])
    if not events:
        return [_finding(
            INFO, language,
            'ยังไม่มีเหตุการณ์ที่เก็บได้ในช่วงนี้ จึงยังไม่มีอะไรให้วิเคราะห์',
            'No events have been collected in this window, so there is nothing to read yet.')]

    findings = []
    failed = [e for e in events if e.get('event_key') == 'failed_logon']
    succeeded = [e for e in events if e.get('event_key') == 'login_success']
    total_failed = sum(int(e.get('event_count') or 0) for e in failed)
    truncated = any(e.get('truncated') for e in failed)
    fail_sources = _collect(failed, 'sources')
    fail_accounts = _collect(failed, 'accounts')

    if failed:
        # The rate is read from complete windows only. The first collection on
        # a host reaches back as far as the lookback allows and stops at the
        # cap, so including it would report a rate the host has never seen.
        whole = [e for e in failed if not e.get('truncated')]
        rate = ''
        if len(whole) >= 2:
            per_window = sum(int(e.get('event_count') or 0) for e in whole) / float(len(whole))
            rate = _text(
                language,
                ' รอบที่เก็บได้ครบเฉลี่ยราว %d ครั้งต่อรอบ' % round(per_window),
                ', and the complete windows average about %d each' % round(per_window))
        findings.append(_finding(
            WARNING if total_failed else INFO, language,
            'ล็อกอินล้มเหลว %d ครั้ง ใน %d รอบเก็บ%s' % (total_failed, len(failed), rate),
            '%d failed sign-ins across %d collection windows%s.' % (
                total_failed, len(failed), rate)))

    if truncated:
        findings.append(_finding(
            WARNING, language,
            'อย่างน้อยหนึ่งรอบชนเพดานการเก็บ ตัวเลขจริงสูงกว่าที่แสดง',
            'At least one window hit the collection cap, so the real total is higher '
            'than the figure shown.'))

    # Sustained across several windows is the difference between somebody
    # fumbling a password and something running on a timer.
    if len(failed) >= SUSTAINED_WINDOWS:
        findings.append(_finding(
            WARNING, language,
            'เกิดต่อเนื่องอย่างน้อย %d รอบติดกัน ไม่ใช่เหตุการณ์ครั้งเดียว '
            'รูปแบบแบบนี้มาจากสิ่งที่ทำงานอัตโนมัติ ไม่ใช่คนพิมพ์รหัสผิด' % len(failed),
            'Sustained across at least %d consecutive windows rather than happening once. '
            'That shape comes from something running on a schedule, not from a person '
            'mistyping a password.' % len(failed))),

    if len(fail_sources) == 1 and total_failed > 0:
        findings.append(_finding(
            WARNING, language,
            'ทั้งหมดมาจากต้นทางเดียว: %s — ปิดกั้นที่อยู่นี้จะหยุดได้ทันที'
            % fail_sources[0],
            'All of it comes from one address: %s. Blocking that address stops it '
            'immediately.' % fail_sources[0]))
    elif len(fail_sources) > 1:
        findings.append(_finding(
            INFO, language,
            'ต้นทางที่พบ: %s' % ', '.join(fail_sources[:5]),
            'Sources seen: %s.' % ', '.join(fail_sources[:5])))

    if len(fail_accounts) >= SPRAY_ACCOUNT_THRESHOLD:
        findings.append(_finding(
            WARNING, language,
            'ลองชื่อบัญชีต่างกันอย่างน้อย %d ชื่อ นี่คือการไล่เดาจากรายชื่อสำเร็จรูป '
            'ไม่ใช่บริการที่ตั้งรหัสผ่านผิด เพราะบริการจะลองชื่อเดิมซ้ำ ๆ ไม่ใช่หลายชื่อ'
            % len(fail_accounts),
            'At least %d different account names were tried. That is a wordlist being '
            'walked, not a service with a stale password: a misconfigured service retries '
            'the same name, not many.' % len(fail_accounts)))
    elif fail_accounts:
        findings.append(_finding(
            INFO, language,
            'มุ่งไปที่บัญชี: %s' % ', '.join(fail_accounts[:5]),
            'Aimed at: %s.' % ', '.join(fail_accounts[:5])))

    # The one that changes what this is. A source that has been failing and
    # has also succeeded is no longer an attempt.
    shared = [source for source in _collect(succeeded, 'sources') if source in fail_sources]
    if shared:
        findings.append(_finding(
            CRITICAL, language,
            'ต้นทาง %s ทั้งล็อกอินล้มเหลวและ "สำเร็จ" ในช่วงเดียวกัน '
            'ให้ถือว่าเครื่องนี้ถูกเข้าถึงได้แล้ว เปลี่ยนรหัสผ่านและตรวจสอบทันที'
            % ', '.join(shared),
            'The address %s has both failed and SUCCEEDED in this window. Treat this host '
            'as accessed: change the credentials and investigate now.' % ', '.join(shared)))

    for event in events:
        if event.get('severity') != CRITICAL:
            continue
        key = event.get('event_key')
        if key == 'log_cleared':
            findings.append(_finding(
                CRITICAL, language,
                'มีการล้าง Security log ซึ่งเป็นสิ่งที่การดูแลระบบตามปกติไม่ทำ '
                'และเป็นวิธีลบร่องรอยหลังเข้าถึงระบบได้',
                'The Security log was cleared. Routine administration does not do that, '
                'and it is how traces are removed after access is gained.'))
        elif key in ('user_created', 'user_deleted'):
            findings.append(_finding(
                CRITICAL, language,
                'มีการสร้างหรือลบบัญชีในช่วงนี้ ถ้าไม่ใช่งานที่วางแผนไว้ '
                'ให้ถือเป็นการฝังตัวเพื่อกลับเข้ามาภายหลัง',
                'An account was created or deleted in this window. If that was not planned '
                'work, treat it as a way back in being set up.'))

    if not findings:
        findings.append(_finding(
            INFO, language,
            'ไม่พบรูปแบบที่น่ากังวลในช่วงนี้',
            'Nothing in this window forms a pattern worth acting on.'))
    return findings


def _failing(checks):
    return [check for check in (checks or []) if check.get('state') == 'fail']


def _has(checks, key, state='fail'):
    return any(check.get('key') == key and check.get('state') == state for check in (checks or []))


def _patch_age_days(checks):
    for check in (checks or []):
        if check.get('key') != 'patch_age':
            continue
        for word in str(check.get('detail') or '').split():
            if word.isdigit():
                return int(word)
    return None


def analyse_posture(checks, language=DEFAULT_LANGUAGE):
    """What a host's failing configuration checks add up to together."""
    if language not in SUPPORTED_LANGUAGES:
        language = DEFAULT_LANGUAGE
    checks = list(checks or [])
    if not checks:
        return [_finding(
            INFO, language,
            'ยังไม่เคยตรวจเครื่องนี้ จึงยังไม่มีอะไรให้วิเคราะห์',
            'This host has not been checked yet, so there is nothing to read.')]

    findings = []
    failing = _failing(checks)
    unreadable = [c for c in checks if c.get('state') == 'unknown']

    if not failing:
        findings.append(_finding(
            INFO, language,
            'ไม่มีข้อที่ไม่ผ่าน',
            'Nothing is failing.'))
    else:
        findings.append(_finding(
            WARNING, language,
            'ไม่ผ่าน %d ข้อ: %s' % (
                len(failing), ', '.join(str(c.get('label') or c.get('key')) for c in failing)),
            '%d checks are failing: %s.' % (
                len(failing), ', '.join(str(c.get('label') or c.get('key')) for c in failing))))

    # Each of these is a finding on its own. Together they describe a host an
    # attacker on the network can reach, break, and not be noticed on.
    reachable = _has(checks, 'smb1') or _has(checks, 'rdp_nla') or _has(checks, 'firewall')
    days = _patch_age_days(checks)
    unpatched = days is not None and days >= STALE_PATCH_DAYS
    unwatched = _has(checks, 'av_realtime') or _has(checks, 'av_realtime', 'unknown')
    if reachable and unpatched:
        findings.append(_finding(
            CRITICAL, language,
            'เครื่องนี้เข้าถึงได้จากเครือข่ายผ่านช่องทางที่อ่อน และค้างแพตช์มา %d วัน '
            'สองอย่างนี้รวมกันหมายความว่าช่องโหว่ที่เปิดเผยต่อสาธารณะแล้วยังใช้ได้กับเครื่องนี้'
            % days,
            'This host is reachable over the network through a weak path and is %d days '
            'behind on patches. Together that means published vulnerabilities still work '
            'against it.' % days))
    if reachable and unpatched and unwatched:
        findings.append(_finding(
            CRITICAL, language,
            'และไม่มีแอนตี้ไวรัสที่ตรวจสอบได้ ถ้ามีใครเข้ามาได้ จะไม่มีอะไรตรวจจับเลย',
            'And no antivirus could be confirmed, so if someone does get in there is '
            'nothing here to notice.'))

    if unreadable:
        findings.append(_finding(
            INFO, language,
            'อ่านไม่ได้ %d ข้อ จึงไม่ถูกนับในคะแนน — คะแนนของเครื่องนี้จึงเทียบกับ'
            'เครื่องที่ตรวจได้ครบไม่ได้ตรง ๆ' % len(unreadable),
            '%d checks could not be read and are left out of the score, so this host\'s '
            'percentage does not compare directly with one measured in full.'
            % len(unreadable)))

    return findings


def analyse(checks, events, language=DEFAULT_LANGUAGE):
    return {
        'language': language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE,
        'posture': analyse_posture(checks, language),
        'events': analyse_events(events, language),
    }
