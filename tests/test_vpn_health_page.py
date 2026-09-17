from pathlib import Path


def _template():
    return (Path(__file__).resolve().parents[1] / 'templates' / 'vpn_health.html').read_text(encoding='utf-8')


def _function_body(template, name):
    body = template.split('function %s(' % name, 1)[1]
    end = body.find('\n    function ')
    return body[:end] if end != -1 else body


def test_the_map_says_how_many_sites_it_cannot_show():
    # Eleven of the branch sites have no coordinates. A map that just leaves
    # them out reads as "all clear" over an area where a site may be down.
    template = _template()
    body = _function_body(template, 'renderMap')

    assert "chip.hidden = unmapped.length === 0;" in body
    assert "' monitored sites not on the map'" in body


def test_a_coordinate_that_cannot_be_a_place_is_not_plotted():
    # Leaflet throws on a bad latitude and takes the whole map down with it, so
    # a typo in one device must not blank the page for the other twenty-five.
    template = _template()
    body = _function_body(template, 'plottable')

    assert 'isFinite(site.latitude) && isFinite(site.longitude)' in body
    assert 'Math.abs(site.latitude) <= 90 && Math.abs(site.longitude) <= 180' in body


def test_a_site_needing_attention_says_when_it_cannot_be_found_on_the_map():
    # Eleven monitored sites have no coordinates. Someone reading the rail and
    # then hunting the map for the marker has to be told there isn't one.
    template = _template()
    body = _function_body(template, 'renderAttention')

    assert "s.has_coordinates ? '' : ' <span class=\"vpn-nogeo\">not on map</span>'" in body


def test_thresholds_are_read_from_the_api_not_written_into_the_page():
    # They live in alert_settings so they can be tuned without a deploy; the
    # page must not carry its own copy that drifts from the server's.
    template = _template()

    assert 'health.thresholds.degraded_jitter_ms' in template
    assert 'health.thresholds.degraded_p95_ms' in template
    assert 'health.thresholds.slow_ms' in template
    assert 'All three thresholds are editable in Settings.' in template
    assert 'health.thresholds.degraded_loss_pct' in template


def test_the_latency_chart_breaks_the_line_where_no_check_ran():
    # Bridging a monitoring gap draws a flat, healthy-looking line across the
    # exact window where nothing was being watched.
    template = _template()
    body = _function_body(template, 'renderChart')

    assert 'spanGaps: false' in body
    assert 'return { x: x, y: (v === null || v === undefined) ? null : v };' in body


def test_the_chart_scale_always_includes_the_slow_threshold():
    # Otherwise the threshold line falls outside the plot on a quiet day and
    # the reader loses the only reference point on the chart.
    template = _template()
    body = _function_body(template, 'renderChart')

    assert 'suggestedMax: Math.ceil(Math.max(thr, Math.max.apply(null, live)) * 1.1)' in body


def test_both_vpn_pages_chart_the_way_the_server_dashboard_does():
    # Three pages, one charting style: a line has to mean the same thing
    # wherever an operator meets it.
    templates = Path(__file__).resolve().parents[1] / 'templates'
    dashboard = (templates / 'server_dashboard.html').read_text(encoding='utf-8')
    for name in ('vpn_health.html', 'vpn_site.html'):
        template = (templates / name).read_text(encoding='utf-8')
        for src in ('chart.js@4.4.0/dist/chart.umd.min.js', 'chartjs-adapter-date-fns@3.0.0'):
            assert src in template, '%s is missing %s' % (name, src)
            assert src in dashboard, 'diverged from the server dashboard: %s' % src
        for setting in ("type: 'time'", 'tension: 0.18', 'pointRadius: 0', 'spanGaps: false'):
            assert setting in template, '%s is missing %s' % (name, setting)


def test_the_fleet_canvas_is_repainted_when_the_theme_flips():
    # Chart.js writes its colours onto the canvas at draw time.
    template = _template()
    assert "window.addEventListener('themechange', function () {" in template
    assert 'if (latency) { renderChart(); }' in template


def test_packet_loss_distinguishes_zero_from_never_measured():
    template = _template()
    body = _function_body(template, 'renderTable')

    assert "s.packet_loss_samples" in body
    assert "not yet recorded" in body


def test_the_page_refreshes_itself_and_stops_on_unload():
    template = _template()

    assert 'refreshTimer = setInterval(load, refreshMs());' in template
    assert "window.addEventListener('beforeunload', function () { clearInterval(refreshTimer); });" in template


def test_a_longer_window_is_polled_less_often():
    # The 30-day view costs the database roughly 3.7 seconds of queries. Asking
    # for that every 30 seconds, from every open browser, buys nothing: a month
    # of history does not change between one minute and the next.
    template = _template()
    body = _function_body(template, 'refreshMs')

    assert 'if (hours <= 24) { return 30000; }' in body
    assert 'if (hours <= 168) { return 120000; }' in body
    assert 'return 300000;' in body
    # Changing the range has to re-arm the timer, or the old cadence survives
    # and the 30-day view keeps polling at the 24-hour rate.
    range_handler = template.split('hours = +b.dataset.hours;', 1)[1][:400]
    assert 'startRefresh();' in range_handler


def test_every_colour_comes_from_a_token_defined_for_both_themes():
    # The page is used in the app's dark theme as often as its light one.
    template = _template()
    scoped = template.split('.vpn-page {', 1)[1].split('</style>', 1)[0]

    assert '[data-theme="dark"] .vpn-page {' in scoped
    for token in ('--vpn-good', '--vpn-warn', '--vpn-crit', '--vpn-accent'):
        assert token in scoped.split('[data-theme="dark"]', 1)[0], '%s must exist before the dark block' % token
    # Tiles are drawn for a light page, so dark mode has to do something about
    # them or the map becomes the one blinding rectangle on the screen.
    assert '[data-theme="dark"] .vpn-page .leaflet-tile-pane' in scoped


def test_the_map_uses_the_same_tiles_as_the_geographical_map_page():
    # Operators already read the estate on that page; a second map with its own
    # cartography would make the same city look like somewhere else.
    template = _template()
    existing = (Path(__file__).resolve().parents[1] / 'templates' / 'map.html').read_text(encoding='utf-8')

    assert 'leaflet@1.9.4' in template and 'leaflet@1.9.4' in existing
    assert 'tile.openstreetmap.org' in template


def test_a_refresh_keeps_the_map_where_the_reader_left_it():
    # The page reloads every 30 seconds. Rebuilding the map or refitting the
    # bounds would yank the view back mid-investigation.
    template = _template()
    body = _function_body(template, 'renderMap')

    assert 'if (!leafletMap) {' in body, 'the map must be built once, not per refresh'
    assert 'if (!fittedOnce && bounds.isValid())' in body
    assert 'fittedOnce = true;' in body


def test_map_markers_match_the_geographical_map_page():
    # Same glyph in the same white-ringed disc, so one estate does not appear
    # as two different products on two pages.
    template = _template()
    existing = (Path(__file__).resolve().parents[1] / 'static' / 'js' / 'map.js').read_text(encoding='utf-8')

    assert 'fa-network-wired' in template, 'VPN routers keep their device glyph'
    assert 'fa-network-wired' in existing
    for rule in ('width: 32px; height: 32px;', "border: 2px solid #fff;"):
        assert rule in template

    body = _function_body(template, 'markerHtml')
    assert "'<div class=\"vpn-mk is-' + s.state + '\"" in body
    assert 'vpn-mk-pulse' in body and 'vpn-mk-core' in body


def test_a_worse_site_beats_faster():
    # The pulse carries severity, so the rates have to stay ordered: down is the
    # fastest thing on the map, healthy the slowest. Equal rates would make the
    # animation decoration.
    template = _template()
    scoped = template.split('.vpn-page {', 1)[1].split('</style>', 1)[0]

    rates = {}
    for state in ('healthy', 'degraded', 'down'):
        marker = '.vpn-mk.is-%s .vpn-mk-pulse { animation: vpn-pulse-%s ' % (state, state)
        assert marker in scoped, 'no pulse defined for %s' % state
        rates[state] = float(scoped.split(marker, 1)[1].split('s ', 1)[0])

    assert rates['down'] < rates['degraded'] < rates['healthy']


def test_the_pulse_stops_for_readers_who_ask_for_less_motion():
    template = _template()
    assert '@media (prefers-reduced-motion: reduce)' in template
    assert '.vpn-page * { animation: none !important; transition: none !important; }' in template


def test_a_switched_off_site_shows_grey_and_perfectly_still():
    # A heartbeat on a site nobody is checking would be a lie, so the disabled
    # marker is the one that does not move.
    template = _template()
    scoped = template.split('.vpn-page {', 1)[1].split('</style>', 1)[0]

    assert '--vpn-mk-disabled: #64748b;' in scoped
    assert '.vpn-mk.is-disabled .vpn-mk-pulse { display: none; }' in scoped

    body = _function_body(template, 'renderMap')
    assert "var mappedOff = (health.disabled_sites || []).filter(plottable);" in body
    assert 'Not monitored</em>' in body
    # Drawn first, so a live marker always wins an overlap.
    assert body.index('mappedOff.forEach') < body.index('mapped.forEach')


def test_the_unmapped_count_stays_about_sites_that_are_being_watched():
    # Two different absences share the map now. Merging them would hide the one
    # that matters: a monitored site nobody can locate.
    template = _template()
    body = _function_body(template, 'renderMap')

    assert "' monitored sites not on the map'" in body
    assert 'unmapped.length' in body and 'mappedOff' not in body.split('var chip')[1].split('\n')[2]


def test_only_the_sites_that_need_someone_are_named_on_the_map():
    template = _template()
    body = _function_body(template, 'markerHtml')

    assert "var named = s.state === 'down' || s.state === 'degraded';" in body


def test_the_top_cards_sit_above_the_map_where_they_will_be_seen():
    # Below the table they would need a scroll nobody performs.
    template = _template()
    body = template.split('{% block content %}', 1)[1]

    assert body.index('id="vpn-topcards"') < body.index('id="vpn-map"')
    assert body.index('id="vpn-kpis"') < body.index('id="vpn-topcards"')


def test_the_downtime_toggle_switches_lists_rather_than_re_sorting_one():
    # Total minutes and the longest single run are different questions, and the
    # server answers them with two lists. The page must not reorder one of them.
    template = _template()
    body = _function_body(template, 'renderTopCards')

    assert "var rows = mode === 'longest' ? card.longest : card.rows;" in body
    assert "var rankedBy = mode === 'longest' ? card.alt_ranked_by : card.ranked_by;" in body


def test_a_deterioration_row_shows_what_it_moved_from():
    # "+35 ms" alone is unreadable - the reader needs the other end of the
    # change. The compact figure carries where it came from; the percentage,
    # which will not fit, is on hover.
    template = _template()

    assert "if (card.key === 'deterioration') { return 'was ' + ms(row.previous); }" in _function_body(template, 'topStat')
    assert "up ' + row.change_pct + '%'" in _function_body(template, 'renderTopCards')


def test_picking_a_site_from_a_card_selects_it_everywhere_else():
    template = _template()
    body = _function_body(template, 'renderTopCards')
    assert "b.addEventListener('click', function () { select(+b.dataset.id); });" in body

    select_body = _function_body(template, 'select')
    assert "document.querySelectorAll('.vpn-toprow')" in select_body


def test_a_single_point_is_not_drawn_as_a_trend():
    # Jitter has only existed since the collector was upgraded, so early on a
    # site has one bucket. A one-point sparkline draws a flat line that reads as
    # a steady history nobody measured.
    template = _template()
    body = _function_body(template, 'topSpark')

    assert "if (real.length < 2) { return '<span class=\"vpn-topspark\"></span>'; }" in body


def test_the_top_cards_use_the_same_anatomy_as_the_server_health_cards():
    # Operators read both pages; a card that ranks the same way but looks
    # different makes them relearn the layout for no reason.
    template = _template()
    existing = (Path(__file__).resolve().parents[1] / 'templates' / 'server_health.html').read_text(encoding='utf-8')

    for rule in ('repeat(auto-fit, minmax(290px, 1fr))',
                 'grid-template-columns: 18px minmax(0, 1fr) auto 58px'):
        assert rule in template, 'missing %s' % rule
        assert rule.replace(', ', ',') in existing.replace(', ', ','), 'diverged from server health: %s' % rule

    # Only the top three ranks are coloured, same three tokens, same order.
    for position, token in ((1, '--danger'), (2, '--warning'), (3, '--info')):
        assert '.vpn-toprow:nth-child(%d) .vpn-toprank { background: var(%s); color: #fff; }' % (position, token) in template
        assert '.topcard-row:nth-child(%d) .topcard-rank { background: var(%s); color: #fff; }' % (position, token) in existing


def test_a_collection_gap_breaks_the_sparkline_instead_of_being_drawn_through():
    # One fill spanning a hole draws a line the data never crossed - the same
    # reason the fleet latency chart breaks its line.
    template = _template()
    body = _function_body(template, 'topSpark')

    assert 'if (v === null) { if (run.length) { runs.push(run); } run = []; return; }' in body
    assert 'runs.filter(function (p) { return p.length > 1; })' in body


def test_the_figure_is_coloured_by_what_it_means_not_by_its_position():
    # The rank badge already carries the ordering. Colouring the value by rank
    # too would say a site is critical merely for being first in a quiet list.
    template = _template()
    body = _function_body(template, 'topTone')

    assert 't.degraded_p95_ms * 2' in body and 't.degraded_jitter_ms * 2' in body
    assert 'TONE[row.state]' in body


def test_packet_loss_says_how_much_of_the_window_it_actually_covers():
    # After the collector upgrade, loss was averaged over 24 checks while the
    # reachability figure beside it covered 492. "20.8% loss, 99.4% reachable"
    # read as a contradiction because the two are not over the same checks.
    template = _template()
    body = _function_body(template, 'renderTable')

    assert 'var partial = s.packet_loss_samples < s.checks;' in body
    assert "'<small>of ' + s.packet_loss_samples + ' checks</small>'" in body
    assert 'not all ' in body, 'the tooltip has to name the other population'


def test_a_flagged_site_is_headed_by_the_figure_that_flagged_it():
    # Heading every row with p95 meant a site listed purely for losing packets
    # led with a latency that was inside every threshold.
    template = _template()
    body = _function_body(template, 'trigger')

    assert "if ((s.p95 || 0) >= t.degraded_p95_ms) { return { head: ms(s.p95) + ' p95', by: 'p95' }; }" in body
    assert "by: 'jitter'" in body and "by: 'loss'" in body

    reason = _function_body(template, 'reason')
    assert "if (by !== 'p95') { bits.push('p95 <b>' + ms(s.p95) + '</b>'); }" in reason, \
        'the detail line must not repeat the heading'


def test_the_downtime_card_shows_when_the_site_was_missing():
    # A total of minutes leaves open the question the card exists to answer:
    # one long outage overnight is not the same as the same minutes scattered
    # through the working day.
    template = _template()

    body = _function_body(template, 'renderTopCards')
    assert "card.key === 'downtime' ? topBand(row.band) : topSpark(row.series, tone)" in body

    band = _function_body(template, 'topBand')
    assert 'BAND_TONE[state] || BAND_TONE.none' in band
    # A bucket nobody checked is not a bucket that came back clean.
    assert "none: 'var(--vpn-nodata)'" in template


def test_the_attention_rail_ends_where_the_map_ends():
    # It used to stop at a hard-coded 568px - a guess at the map's height that
    # left a strip of dead space under it and would drift the moment the map
    # was resized.
    template = _template()
    scoped = template.split('.vpn-page {', 1)[1].split('</style>', 1)[0]

    assert 'align-items: stretch;' in scoped, 'the rail cannot match a row it does not stretch to'
    assert '.vpn-att { flex: 1 1 auto; min-height: 0; overflow-y: auto; }' in scoped
    assert 'max-height: 568px' not in scoped, 'the guessed height is back'
    # Without min-height:0 a flex child refuses to shrink and pushes the panel
    # past its track instead of scrolling inside it.
    assert '.vpn-stack > .vpn-panel { display: flex; flex-direction: column; min-height: 0; }' in scoped
