from pathlib import Path


def _template(name='vpn_site.html'):
    return (Path(__file__).resolve().parents[1] / 'templates' / name).read_text(encoding='utf-8')


def _function_body(template, name):
    body = template.split('function %s(' % name, 1)[1]
    end = body.find('\n    function ')
    return body[:end] if end != -1 else body


def test_the_chart_lines_do_not_borrow_the_status_colours():
    # Good/warning/critical mean state. Drawing the second series in the status
    # green would read as a verdict on the reading rather than as the other of
    # two lines. The series colours come from the documented categorical order.
    template = _template()
    script = template.split('</style>', 1)[1]

    assert "var typical = dark ? '#3987e5' : '#2a78d6';" in script
    for status in ('#1b7f5a', '#25966a', '#d98324', '#b98a00', '#d13438', '#c74a4d'):
        assert status not in _function_body(template, 'seriesFor'), \
            'the status colour %s is being used as a series colour' % status


def test_the_chart_is_drawn_with_the_same_library_and_settings_as_the_server_dashboard():
    # Operators read both pages. A second charting style would make the same
    # kind of line mean something different depending on which page it is on.
    template = _template()
    existing = (Path(__file__).resolve().parents[1] / 'templates' / 'server_dashboard.html').read_text(encoding='utf-8')

    for src in ('chart.js@4.4.0/dist/chart.umd.min.js',
                'chartjs-adapter-date-fns@3.0.0'):
        assert src in template, 'missing %s' % src
        assert src in existing, 'diverged from the server dashboard: %s' % src

    body = _function_body(template, 'drawMetric')
    for setting in ("type: 'time'", 'tension: 0.18', 'pointRadius: 0',
                    'pointHoverRadius: 4', 'spanGaps: false', 'animation: false',
                    "interaction: { mode: 'nearest', axis: 'x', intersect: false }"):
        assert setting in body, 'missing %s' % setting
        assert setting in existing, 'diverged from the server dashboard: %s' % setting


def test_the_slow_line_is_the_one_carrying_the_fill():
    # The slowest reply is what the chart is about; the typical one is the
    # baseline it is read against, so only the first gets a filled area.
    template = _template()
    body = _function_body(template, 'seriesFor')

    assert "var own = dark ? '#e2e8f0' : '#334155';" in body
    assert 'stroke: own, fillColour: ownFill' in body
    assert "fillColour: 'transparent'" in body


def test_a_bucket_of_four_replies_is_not_called_a_percentile():
    # 488 checks over 120 buckets is three to six replies each, and the 95th
    # percentile of four values is the largest of them. Labelling that p95 put a
    # 13 ms site on a chart that peaked at 670 and read as a contradiction.
    template = _template()
    body = _function_body(template, 'renderChart')

    assert 'Slowest and typical reply in each bucket' in body
    assert 'p95 over the whole window is ' in body, \
        'the window figure has to be stated, or the card and the chart read as contradicting each other'
    # The threshold is a window figure, so the line says so rather than looking
    # like a rule each bucket is breaking.
    assert "'Degraded when the window p95 passes '" in body


def test_the_chart_breaks_its_line_where_nothing_was_measured():
    # A line drawn through a bucket nobody measured claims the link was fine at
    # a moment nothing was watching it.
    template = _template()
    body = _function_body(template, 'drawMetric')

    assert 'spanGaps: false' in body
    assert 'return { x: x, y: (v === null || v === undefined) ? null : v };' in body


def test_latency_and_jitter_are_two_charts_stacked_not_one_toggled():
    # They are both milliseconds and different questions, so they cannot share a
    # scale. Stacked rather than side by side: the x axis is the same on both,
    # and halving the width of a chart this dense would smear it.
    template = _template()

    assert 'data-metric=' not in template, 'the toggle is gone'
    assert 'id="vs-latency-chart"' in template and 'id="vs-jitter-chart"' in template

    body = _function_body(template, 'renderChart')
    assert body.index("metric: 'latency'") < body.index("metric: 'jitter'")

    series = _function_body(template, 'seriesFor')
    assert "if (metric === 'jitter') {" in series
    assert "points: data.peak_series || []" in series and "points: data.typical_series || []" in series


def test_the_two_plots_line_up_so_a_spike_can_be_read_straight_down():
    # Chart.js sizes the y axis from its tick labels, and "800 ms" is wider than
    # "40 ms" - left to itself the two plots would start at different x and
    # stacking them would buy nothing.
    template = _template()
    body = _function_body(template, 'drawMetric')

    assert 'afterFit: function (scale) { scale.width = Y_AXIS_WIDTH; }' in body
    assert 'var Y_AXIS_WIDTH = 56;' in template


def test_the_jitter_panel_hides_itself_until_it_has_something_to_say():
    # Jitter only exists since the collector was upgraded, so over a long window
    # the panel would be an empty rectangle taking up the page.
    template = _template()
    body = _function_body(template, 'renderChart')

    assert "document.getElementById('vs-jitter-panel').hidden = !drew;" in body


def test_each_chart_carries_the_threshold_that_applies_to_it():
    template = _template()
    caller = _function_body(template, 'renderChart')

    assert 'threshold: t.degraded_p95_ms,' in caller
    assert 'threshold: t.degraded_jitter_ms,' in caller

    # The scale always reaches the threshold, or the line falls outside the plot
    # on a quiet day and the reader loses the only reference point on the chart.
    body = _function_body(template, 'drawMetric')
    assert 'suggestedMax: Math.ceil(Math.max(threshold, Math.max.apply(null, all)) * 1.1)' in body


def test_a_legend_names_every_line_where_there_is_more_than_one():
    # Identity must never rest on colour alone. A single-series chart needs no
    # legend box - its title names it.
    template = _template()
    body = _function_body(template, 'drawMetric')

    assert 'display: lines.length > 1,' in body
    assert "position: 'bottom'" in body
    assert 'label: l.name' in body


def test_a_theme_switch_repaints_the_canvas():
    # Chart.js writes its colours onto the canvas at draw time, so the grid and
    # ticks keep the old theme's ink until something redraws them.
    template = _template()

    assert "window.addEventListener('themechange', function () {" in template
    assert 'if (data) { renderChart(); }' in template


def test_a_figure_is_read_against_the_window_before_it():
    template = _template()
    body = _function_body(template, 'delta')

    # Direction, not sign: a latency going up is worse, a reachability going up
    # is better, and the same arrow must not be coloured the same way for both.
    assert 'var worse = lowerIsBetter ? diff > 0 : diff < 0;' in body
    assert 'nothing to compare with' in body

    # Both directions are actually used: latency lower-is-better, availability
    # higher-is-better. An unexercised branch is a claim nobody checks.
    figures = _function_body(template, 'renderFigures')
    assert 'delta(s.p95, p.p95, true)' in figures
    assert 'delta(s.reach_pct, p.reach_pct, false)' in figures


def test_packet_loss_says_how_much_of_the_window_it_covers_here_too():
    # The same trap as the fleet table: loss is averaged over the checks that
    # recorded it, reachability over all of them.
    template = _template()
    body = _function_body(template, 'renderFigures')

    assert "s.packet_loss_samples < s.checks" in body
    assert "'over ' + s.packet_loss_samples + ' of ' + s.checks + ' checks'" in body


def test_the_page_says_what_it_cannot_show_without_snmp():
    template = _template()
    body = _function_body(template, 'renderPending')

    assert 'el.hidden = data.site.snmp_metrics_enabled;' in body
    assert 'Collect SNMP metrics' in body, 'name the switch the operator has to find'


def test_the_fleet_page_offers_a_way_into_each_site():
    fleet = _template('vpn_health.html')

    assert "href=\"/vpn-site/' + s.id + '\">Open</a>" in fleet, 'the table row has no way through'
    assert "href=\"/vpn-site/' + s.id + '\">Open this site</a>" in fleet, 'the map popup is a dead end otherwise'
    assert '.vpn-open {' in fleet


def test_a_multi_day_axis_carries_the_date():
    # Over a 7-day window the marks fall tens of hours apart, so the clock alone
    # printed 16:50, 10:49, 22:49 - correctly ordered and reading exactly like
    # time running backwards.
    for name in ('vpn_site.html', 'vpn_health.html'):
        template = _template(name)
        body = _function_body(template, 'axisLabel')
        assert "return hours <= 24 ? text.slice(11, 16)" in body, '%s: no short-window form' % name
        assert "text.slice(8, 10) + '/' + text.slice(5, 7)" in body, '%s: no date on the long form' % name
        assert 'slice(11, 16)) + ' not in template, '%s: an axis is still printing the clock alone' % name


def test_jitter_gets_a_shorter_plot_than_latency():
    # Jitter is read for its shape and whether it crosses its line; latency is
    # read for values. Merging them into one chart was the alternative and it
    # fails on the quiet sites, where jitter is a fraction of latency and would
    # flatten against the axis.
    template = _template()
    scoped = template.split('.vs-page {', 1)[1].split('</style>', 1)[0]

    assert '.vs-chartbox { position: relative; height: 240px;' in scoped
    assert '.vs-chartbox.is-compact { height: 130px; }' in scoped
    assert 'class="vs-chartbox is-compact" id="vs-jitter-box"' in template
    assert 'class="vs-chartbox" id="vs-latency-box"' in template

    # A short plot with the usual tick count crowds its own labels.
    body = _function_body(template, 'drawMetric')
    assert 'maxTicksLimit: spec.compact ? 4 : 8,' in body
