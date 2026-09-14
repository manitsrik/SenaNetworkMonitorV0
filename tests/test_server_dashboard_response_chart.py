from pathlib import Path


def test_response_chart_connects_sparse_bucket_samples():
    template = (
        Path(__file__).resolve().parents[1] / 'templates' / 'server_dashboard.html'
    ).read_text(encoding='utf-8')
    render_response_chart = template.split(
        'function renderResponseChart(', 1
    )[1].split(
        '\nfunction ', 1
    )[0]

    assert (
        'const points = insertTimeGaps(rows.map(timestampPoint).filter(Boolean));'
        in render_response_chart
    )
    assert (
        'const points = rows.map(timestampPointWithNull).filter(Boolean);'
        not in render_response_chart
    )
