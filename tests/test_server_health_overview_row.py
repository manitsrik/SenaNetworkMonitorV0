"""The overview row declares its column count by hand.

`.health-overview` lists one column per summary card plus the hero, so adding
a card without raising that number drops the new card onto a second row by
itself. That is what happened when the security card was added, and nothing
failed to say so.
"""
import re
from pathlib import Path


def _template():
    return (
        Path(__file__).resolve().parents[1] / "templates" / "server_health.html"
    ).read_text(encoding="utf-8")


def _summary_card_count(template):
    # Only the markup, not the CSS rules that also name the class.
    return len(re.findall(r'<div class="health-summary-card [^"]*"', template))


def _wide_column_count(template):
    match = re.search(
        r"\.health-overview\s*\{[^}]*grid-template-columns:\s*[\d.]+fr\s+repeat\((\d+),",
        template,
        re.DOTALL,
    )
    assert match, "could not find the wide .health-overview grid definition"
    return int(match.group(1))


def test_the_overview_row_has_a_column_for_every_summary_card():
    template = _template()
    cards = _summary_card_count(template)

    assert cards > 0, "no summary cards found -- has the markup changed?"
    assert _wide_column_count(template) == cards, (
        "the overview grid declares %d card columns for %d cards, so the "
        "extras wrap onto their own row" % (_wide_column_count(template), cards)
    )


def test_the_narrow_layout_still_reflows_instead_of_overflowing():
    # Below 1440px the hero spans the full width and the cards flow three to
    # a row, so the count above does not need to change there.
    template = _template()

    assert "grid-template-columns: repeat(3, minmax(150px, 1fr));" in template
    assert "grid-column: 1 / -1;" in template
