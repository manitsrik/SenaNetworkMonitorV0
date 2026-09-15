"""The Down sparkline must mean what the Down figure above it means.

The hourly series counted every device that was down at any point in the
hour, so a host that failed twice and recovered left the line at 2 while the
card beside it read 1. Each point now reports the status each device held as
the hour ended.
"""
from database import fold_hourly_statuses


def row(hour, device_id, status):
    return {'hour_label': hour, 'device_id': device_id, 'status': status}


def test_a_host_that_recovered_within_the_hour_is_not_counted_as_down():
    counts = fold_hourly_statuses([
        row('10:00', 1, 'up'),
        row('10:00', 2, 'up'),
    ])

    assert counts == [{'hour_label': '10:00', 'seen_n': 2,
                       'down_n': 0, 'slow_n': 0, 'up_n': 2}]


def test_the_status_counted_is_the_last_one_in_the_hour():
    """Rows arrive already reduced to one per device per hour."""
    counts = fold_hourly_statuses([row('10:00', 1, 'down'), row('10:00', 2, 'up')])

    assert counts[0]['down_n'] == 1
    assert counts[0]['up_n'] == 1


def test_a_device_keeps_its_status_through_hours_it_was_not_checked_in():
    counts = fold_hourly_statuses([
        row('10:00', 1, 'down'), row('10:00', 2, 'up'),
        row('11:00', 2, 'up'),                     # host 1 not checked at all
        row('12:00', 1, 'up'), row('12:00', 2, 'up'),
    ])

    assert [c['down_n'] for c in counts] == [1, 1, 0]
    # It stays down through 11:00 because nothing said otherwise.
    assert [c['up_n'] for c in counts] == [1, 1, 2]


def test_seen_counts_only_the_devices_actually_checked():
    """So a collection outage reads as the dip it is, not a flat line."""
    counts = fold_hourly_statuses([
        row('10:00', 1, 'up'), row('10:00', 2, 'up'), row('10:00', 3, 'up'),
        row('11:00', 1, 'up'),
        row('12:00', 1, 'up'), row('12:00', 2, 'up'), row('12:00', 3, 'up'),
    ])

    assert [c['seen_n'] for c in counts] == [3, 1, 3]
    # The other two are still counted as up while unchecked.
    assert [c['up_n'] for c in counts] == [3, 3, 3]


def test_every_hour_accounts_for_each_known_device_exactly_once():
    counts = fold_hourly_statuses([
        row('10:00', 1, 'up'), row('10:00', 2, 'slow'), row('10:00', 3, 'down'),
        row('11:00', 1, 'slow'), row('11:00', 2, 'slow'), row('11:00', 3, 'up'),
    ])

    for entry in counts:
        assert entry['down_n'] + entry['slow_n'] + entry['up_n'] == 3


def test_a_device_first_seen_later_joins_from_that_hour_on():
    counts = fold_hourly_statuses([
        row('10:00', 1, 'up'),
        row('11:00', 1, 'up'), row('11:00', 2, 'down'),
    ])

    assert [c['down_n'] for c in counts] == [0, 1]
    assert [c['seen_n'] for c in counts] == [1, 2]


def test_an_empty_window_produces_no_points():
    assert fold_hourly_statuses([]) == []


def test_an_unrecognised_status_is_counted_in_none_of_the_three():
    """`pending` and friends must not be silently folded into up."""
    counts = fold_hourly_statuses([row('10:00', 1, 'pending'), row('10:00', 2, 'up')])

    assert counts[0] == {'hour_label': '10:00', 'seen_n': 2,
                         'down_n': 0, 'slow_n': 0, 'up_n': 1}
