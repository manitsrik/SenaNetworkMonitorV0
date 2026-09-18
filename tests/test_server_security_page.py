from pathlib import Path


def _template(name):
    return (Path(__file__).resolve().parents[1] / "templates" / name).read_text(encoding="utf-8")


def _function_body(template, name):
    return template.split("function %s(" % name, 1)[1].split("\nfunction ", 1)[0]


def test_the_fleet_page_leads_with_the_count_of_hosts_at_risk():
    template = _template("server_health.html")

    assert 'class="health-summary-card is-security"' in template
    assert 'id="sum-security"' in template
    assert 'id="sum-security-note"' in template


def test_no_failing_checks_reads_as_not_checked_until_something_has_been_swept():
    # "Security At Risk: 0" is only good news once a sweep has run. On a
    # fleet nobody has swept it is the same number, and it would be read as
    # reassurance rather than as an empty column.
    summary = _function_body(_template("server_health.html"), "setSummary")

    assert "if (!securityRisk && !securityWarn && !securityOk) {" in summary
    assert "securityValue.textContent = 'Not checked';" in summary
    assert "have not been swept yet." in summary


def test_the_table_carries_a_sortable_security_column():
    template = _template("server_health.html")

    assert 'data-sort-key="security"' in template
    assert '<td class="col-security">${renderSecurityCell(server)}</td>' in template
    # Eleven columns now, so the loading and empty rows still span the table.
    assert 'colspan="10"' not in template
    assert 'colspan="11"' in template


def test_the_column_sorts_by_what_it_leads_with():
    sort = _function_body(_template("server_health.html"), "sortValue")

    # Three failing checks outrank one whatever the two percentages say, and
    # any failure outranks every host with none. Sorting on the score alone
    # would put an 88%-with-a-failure below a 60%-with-none.
    assert "case 'security': {" in sort
    assert "const failing = Number(server.security_fail_count) || 0;" in sort
    assert "return failing ? -(failing * 100) - (100 - base) : base;" in sort
    # An unswept host has no verdict to rank, so it sorts as missing rather
    # than as a perfect score.
    assert "if (!state || state === 'unknown') return null;" in sort


def test_an_unswept_host_and_an_unreadable_one_are_told_apart():
    state = _function_body(_template("server_health.html"), "securityState")

    assert "key: 'unchecked', label: 'Not checked'" in state
    assert "else detail = 'none readable';" in state


def test_the_security_column_hides_itself_until_a_sweep_has_run():
    template = _template("server_health.html")

    assert ".server-health-table.hide-security .col-security {" in template
    assert "table.classList.toggle('hide-security', !servers.some(server => server.security_state));" in template


def test_the_fleet_page_can_filter_down_to_the_hosts_at_risk():
    template = _template("server_health.html")

    assert "label: 'Security at risk'," in template
    assert "dropEmptyFocus('security', securityRisk);" in template


def test_the_server_dashboard_lists_what_actually_failed():
    template = _template("server_dashboard.html")

    assert 'id="security-checks"' in template
    assert 'id="security-score-pill"' in template
    assert "Security Posture" in template
    # The card is filled from the same payload the rest of the page uses.
    assert "renderSecurityPosture(server);" in _function_body(template, "renderDetails")


def test_the_dashboard_puts_the_failing_checks_first():
    body = _function_body(_template("server_dashboard.html"), "renderSecurityPosture")

    assert "const SECURITY_CHECK_ORDER = { fail: 0, warn: 1, unknown: 2, pass: 3 };" in _template(
        "server_dashboard.html")
    assert "SECURITY_CHECK_ORDER[a.state]" in body


def test_the_dashboard_says_why_a_sweep_produced_nothing():
    body = _function_body(_template("server_dashboard.html"), "renderSecurityPosture")

    assert "The last sweep could not complete:" in body
    assert "No security sweep has run on this host yet." in body


def test_the_security_alert_can_be_turned_off_like_every_other_event():
    settings = _template("settings.html")

    assert 'id="alert_on_security"' in settings


def test_the_score_says_how_many_checks_it_was_scored_on():
    template = _template("server_health.html")
    cell = _function_body(template, "renderSecurityCell")

    # Unreadable checks leave the score entirely, so two hosts showing 50%
    # may have been measured on five checks and on eight. The column has to
    # carry that, because nobody scanning it opens a tooltip first.
    assert "const { counted, total } = securityCoverage(server);" in cell
    assert "const partial = total > 0 && counted < total;" in cell
    assert "const sub = [scoreText, partial ? `${counted}/${total}` : '']" in cell


def test_the_cell_leads_with_what_needs_doing_not_with_the_percentage():
    # A percentage is a proportion of the checks that could be read, and hosts
    # are read to different depths, so it does not compare between rows --
    # while "2 failing" means the same thing on every row. Led by the
    # percentage, this column invited the reading that 88% was safer than 60%,
    # when the 88% host was the one with a real failure.
    cell = _function_body(_template("server_health.html"), "renderSecurityCell")

    assert '<span class="security-headline">${esc(state.detail)}</span>' in cell
    assert "<small>${sub}</small>" in cell


def test_a_fully_measured_host_carries_no_caveat():
    cell = _function_body(_template("server_health.html"), "renderSecurityCell")

    # A host measured on everything needs no fraction; printing 8/8 on every
    # healthy row would bury the rows where the number actually matters.
    assert "partial ? `${counted}/${total}` : ''" in cell
    assert ".filter(Boolean)" in cell
    assert "` Scored on all ${total} checks.`" in cell
    assert "could not be read.`" in cell


def test_the_cell_carries_one_colour_meaning_not_three():
    # The headline shows the state; everything below it is supporting detail
    # in the same muted tone. An earlier version coloured the percentage, the
    # wording and the coverage fraction separately, putting three meanings in
    # one small cell.
    template = _template("server_health.html")

    assert ".security-cell.is-risk .security-headline { color: var(--danger); }" in template
    assert "security-coverage" not in template
    assert "security-score" not in template


def test_coverage_counts_only_the_states_that_carry_a_verdict():
    template = _template("server_health.html")
    body = _function_body(template, "securityCoverage")

    assert "const SECURITY_COUNTED_STATES = ['pass', 'warn', 'fail'];" in template
    assert "checks.filter(check => SECURITY_COUNTED_STATES.includes(check.state)).length" in body


# --- remediation on the dashboard card ------------------------------------

def test_only_a_check_with_something_to_do_opens():
    template = _template("server_dashboard.html")
    body = _function_body(template, "renderSecurityPosture")

    # A passing row with a disclosure arrow that reveals nothing is worse
    # than no arrow. "unknown" is excluded too: its detail already says what
    # access the monitor needs.
    assert "const SECURITY_ADVICE_STATES = ['fail', 'warn'];" in template
    assert "if (!advice || !SECURITY_ADVICE_STATES.includes(check.state)) {" in body
    assert 'return `<li class="security-check ${tone.css}">${head}</li>`;' in body
    assert "<summary>${head}</summary>" in body


def test_the_translated_label_wins_but_the_evidence_is_left_alone():
    body = _function_body(_template("server_dashboard.html"), "renderSecurityPosture")

    # The detail carries a KB number, a day count, a service name -- evidence
    # rather than prose, and it is stored as the host reported it.
    assert "const label = (advice && advice.label) || check.label || check.key;" in body
    assert "${esc(check.detail || tone.label)}" in body


def test_copying_a_command_works_over_plain_http():
    # navigator.clipboard needs a secure context and this app is served over
    # plain HTTP on the LAN, so without the fallback the button would look
    # like it worked and copy nothing.
    template = _template("server_dashboard.html")
    body = _function_body(template, "copyText")

    assert "if (navigator.clipboard && window.isSecureContext) {" in body
    assert "document.execCommand('copy')" in body
    assert "button.textContent = copied ? 'Copied' : 'Press Ctrl+C';" in template


def test_the_warning_is_not_allowed_to_read_as_fine_print():
    template = _template("server_dashboard.html")

    # It is the part that stops somebody locking themselves out of a host.
    assert ".security-advice-warning {" in template
    assert "border-left: 3px solid var(--warning);" in template
    assert 'class="security-advice-warning"' in template


def test_the_advice_is_fetched_once_not_on_every_refresh():
    template = _template("server_dashboard.html")
    body = _function_body(template, "loadSecurityAdvice")

    assert "if (securityAdvice) return securityAdvice;" in body
    assert "loadSecurityAdvice()," in template


def test_the_command_block_says_which_shell_it_belongs_in():
    template = _template("server_dashboard.html")
    body = _function_body(template, "renderAdvice")

    # A bare command block left the reader to work out that
    # Set-SmbServerConfiguration is not something cmd.exe accepts, and that it
    # belongs on the monitored host rather than on the monitor.
    assert "function renderAdvice(advice, runContext)" in template
    assert '<div class="security-advice-run">' in body
    assert "<span>${esc(runContext || '')}</span>" in body
    assert "${renderAdvice(advice, runContextFor(server))}" in template


def test_the_run_context_follows_the_host_not_the_check():
    template = _template("server_dashboard.html")
    body = _function_body(template, "runContextFor")

    # Windows fixes are elevated PowerShell and Linux fixes are shell over
    # SSH, whichever check produced them.
    assert "const platform = platformOf(server);" in body
    assert "return securityRunContext[platform] || '';" in body


def test_the_card_can_ask_for_a_sweep_now():
    template = _template("server_dashboard.html")

    # The scheduled sweep is hours away, and the moment somebody most wants a
    # verdict is right after they have fixed something.
    assert 'id="security-recheck"' in template
    assert "/api/security-recheck/${encodeURIComponent(server.id)}" in template
    assert "method: 'POST'," in template


def test_a_re_check_updates_the_card_without_waiting_for_the_next_poll():
    body = _function_body(_template("server_dashboard.html"), "recheckSecurity")

    assert "Object.assign(server, {" in body
    assert "renderSecurityPosture(server);" in body


def test_a_failed_re_check_says_so_instead_of_going_quiet():
    # Going quiet would leave the stale verdict on screen looking fresh.
    body = _function_body(_template("server_dashboard.html"), "recheckSecurity")

    assert "Failed" in body
    assert "button.title = String(error && error.message ? error.message : error);" in body
    assert "button.disabled = false;" in body


def test_every_headline_leads_with_a_count():
    # The column is scanned down one edge, so a passing host says how many
    # checks passed rather than breaking the pattern with a bare word.
    state = _function_body(_template("server_health.html"), "securityState")

    assert "if (fail) detail = `${fail} failing`;" in state
    assert "else if (warn) detail = `${warn} to review`;" in state
    assert "detail = Number.isFinite(pass) ? `${pass} passed` : 'passed';" in state
    # And nothing in the column runs long enough to crowd the score beneath it.
    assert "'all checks passed'" not in state
    assert "'nothing could be read'" not in state


def test_the_security_cell_links_through_to_the_card():
    # The cell reporting the problem is the obvious thing to press to go and
    # read about it, rather than crossing the row to the Dashboard button.
    cell = _function_body(_template("server_health.html"), "renderSecurityCell")

    assert "const href = `/server-dashboard/${encodeURIComponent(server.id)}#security-posture`;" in cell
    assert '<a class="security-cell-link" href="${href}"' in cell


def test_arriving_from_the_table_lands_on_the_card_and_says_so():
    template = _template("server_dashboard.html")
    body = _function_body(template, "focusRequestedSection")

    assert 'id="security-posture"' in template
    assert "window.location.hash !== '#security-posture'" in body
    assert "card.scrollIntoView({ behavior: 'smooth', block: 'center' });" in body
    assert "card.classList.add('is-flashed');" in body


def test_the_page_does_not_yank_the_scroll_back_on_every_refresh():
    # loadDashboard runs every thirty seconds; re-scrolling each time would
    # make the page unusable for anyone reading something else on it.
    template = _template("server_dashboard.html")
    body = _function_body(template, "focusRequestedSection")

    assert "let hasFocusedRequestedSection = false;" in template
    assert "if (hasFocusedRequestedSection) return;" in body
    assert "hasFocusedRequestedSection = true;" in body


def test_the_flash_respects_a_reduced_motion_preference():
    template = _template("server_dashboard.html")

    assert "@media (prefers-reduced-motion: reduce) {" in template
    assert "animation: security-flash 1.8s ease-out;" in template
