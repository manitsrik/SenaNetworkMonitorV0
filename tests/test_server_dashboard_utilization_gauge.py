from pathlib import Path


def _dashboard_template():
    return (
        Path(__file__).resolve().parents[1] / "templates" / "server_dashboard.html"
    ).read_text(encoding="utf-8")


def test_utilization_gauge_does_not_treat_stale_current_value_as_live_data():
    template = _dashboard_template()
    render_gauge = template.split(
        "function renderUtilizationGauge(", 1
    )[1].split("\nfunction ", 1)[0]

    assert "const hasData = historyValues.length > 0" in render_gauge
    assert "!['down', 'disabled'].includes(normalizedStatus)" in render_gauge
    assert "formattedValue: hasData ? `${value.toFixed(1)}%` : 'No data'" in render_gauge


def test_gauge_plugin_skips_the_needle_when_data_is_unavailable():
    template = _dashboard_template()
    gauge_plugin = template.split(
        "const responseGaugePlugin =", 1
    )[1].split("\nfunction renderUtilizationGauge(", 1)[0]

    no_data_guard = gauge_plugin.index("if (gauge.hasData === false)")
    needle_rotation = gauge_plugin.index("ctx.rotate(angle)")

    assert no_data_guard < needle_rotation
    assert "ctx.fillText(gauge.formattedValue" in gauge_plugin[no_data_guard:needle_rotation]
    assert "return;" in gauge_plugin[no_data_guard:needle_rotation]
