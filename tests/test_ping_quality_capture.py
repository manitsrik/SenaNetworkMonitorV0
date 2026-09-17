"""Every ping check already sends several packets; these guard what we keep."""
import pytest

import monitor as monitor_module
from monitor import NetworkMonitor
from config import Config


class FakePacket:
    def __init__(self, ms, ok=True):
        self.time_elapsed_ms = ms
        self.success = ok


class FakeResponse:
    """Stands in for pythonping's ResponseList.

    Its rtt_avg/min/max fold in every packet at its full elapsed time, timeouts
    included - which is the behaviour these tests exist to stop leaking out.
    """

    def __init__(self, ok, avg=None, low=None, high=None, loss=0.0, loss_raises=False,
                 packets=None, not_iterable=False):
        self._ok = ok
        self.rtt_avg_ms = avg
        self.rtt_min_ms = low
        self.rtt_max_ms = high
        self._loss = loss
        self._loss_raises = loss_raises
        self._packets = packets
        self._not_iterable = not_iterable

    def __iter__(self):
        if self._not_iterable:
            raise TypeError('not iterable')
        if self._packets is None:
            # Default: every packet answered at the average.
            return iter([FakePacket(self.rtt_avg_ms)])
        return iter(self._packets)

    def success(self):
        return self._ok

    @property
    def packet_loss(self):
        if self._loss_raises:
            raise AttributeError('packet_loss')
        return self._loss


@pytest.fixture
def pinger(monkeypatch):
    """A Monitor whose ping returns whatever the test hands it."""
    sent = {}

    def fake_ping(ip, count=None, timeout=None, verbose=False):
        sent['ip'] = ip
        sent['count'] = count
        return sent['response']

    monkeypatch.setattr(monitor_module, 'ping', fake_ping)
    probe = NetworkMonitor.__new__(NetworkMonitor)
    return probe, sent


def test_a_successful_check_keeps_the_spread_across_its_packets(pinger):
    probe, sent = pinger
    sent['response'] = FakeResponse(
        True, avg=18.57, low=6.1, high=41.2, loss=0.0,
        packets=[FakePacket(6.1), FakePacket(8.4), FakePacket(41.2)])

    result = probe.ping_device('10.12.1.2')

    assert result['status'] == 'up'
    assert result['response_time'] == pytest.approx(18.57, abs=0.01)
    assert result['rtt_min'] == 6.1
    assert result['rtt_max'] == 41.2
    assert result['packet_loss'] == 0.0


def test_the_loss_ratio_is_reported_as_a_percentage(pinger):
    # A third of three packets lost is 33.33%, not 0.33.
    probe, sent = pinger
    sent['response'] = FakeResponse(
        True, avg=8.4, low=6.1, high=2000.0, loss=1 / 3,
        packets=[FakePacket(6.1), FakePacket(8.4), FakePacket(2000.0, ok=False)])

    assert probe.ping_device('10.12.1.2')['packet_loss'] == pytest.approx(33.33, abs=0.01)


def test_a_check_with_no_reply_records_total_loss_rather_than_nothing(pinger):
    probe, sent = pinger
    sent['response'] = FakeResponse(False)

    result = probe.ping_device('10.245.1.2')

    assert result['status'] == 'down'
    assert result['response_time'] is None
    assert result['packet_loss'] == 100.0
    assert result['rtt_min'] is None and result['rtt_max'] is None


def test_a_check_that_cannot_report_loss_says_so_instead_of_claiming_zero(pinger):
    # An older pythonping build raises here. Recording 0 would read as a clean
    # link, which is the opposite of "we do not know".
    probe, sent = pinger
    sent['response'] = FakeResponse(True, avg=5.0, low=5.0, high=5.0, loss_raises=True)

    assert probe.ping_device('10.0.16.2')['packet_loss'] is None


def test_an_unreachable_host_that_raises_records_no_loss_figure(pinger):
    probe, sent = pinger

    def boom(ip, count=None, timeout=None, verbose=False):
        raise OSError('network unreachable')

    import monitor as m
    original = m.ping
    m.ping = boom
    try:
        result = probe.ping_device('10.0.0.1')
    finally:
        m.ping = original

    assert result['status'] == 'down'
    # The check never ran, so there is no loss ratio to report - unlike a check
    # that ran and got nothing back, which is a real 100%.
    assert result['packet_loss'] is None


def test_the_slow_threshold_still_decides_up_from_slow(pinger):
    probe, sent = pinger
    threshold = Config.MONITOR_THRESHOLDS.get('ping', Config.DEFAULT_SLOW_THRESHOLD)
    sent['response'] = FakeResponse(True, avg=threshold + 1, low=1.0, high=threshold + 40)

    assert probe.ping_device('10.12.1.2')['status'] == 'slow'


def test_a_lost_packet_is_not_recorded_as_a_slow_reply(pinger):
    """The bug this page exists to stop reporting.

    A branch that answers at 1.5 ms but drops one packet in three was recorded
    at 669 ms - pythonping folds the timed-out packet into the average at the
    full 2000 ms timeout. That figure then sat in the same column, the same
    chart and against the same 200 ms threshold as a genuine latency, so a loss
    problem was filed as a speed problem everywhere in the product.
    """
    probe, sent = pinger
    sent['response'] = FakeResponse(
        True, avg=669.73, low=1.53, high=2000.0, loss=1 / 3,
        packets=[FakePacket(1.53), FakePacket(8.0), FakePacket(2000.0, ok=False)])

    result = probe.ping_device('10.241.1.2')

    # Latency describes the packets that came back: (1.53 + 8.0) / 2.
    assert result['response_time'] == pytest.approx(4.77, abs=0.01)
    assert result['rtt_min'] == 1.53
    assert result['rtt_max'] == 8.0
    # ...and the packet that did not is reported as loss, which has its own column.
    assert result['packet_loss'] == pytest.approx(33.33, abs=0.01)
    # A 1.5 ms link is not slow, whatever the library's own average said.
    assert result['status'] == 'up'


def test_jitter_is_not_manufactured_by_a_timeout(pinger):
    # rtt_max - rtt_min is how jitter is measured. Letting a 2000 ms timeout set
    # rtt_max reports 1998 ms of jitter on a link that never wavered.
    probe, sent = pinger
    sent['response'] = FakeResponse(
        True, avg=671.0, low=2.0, high=2000.0, loss=1 / 3,
        packets=[FakePacket(2.0), FakePacket(2.1), FakePacket(2000.0, ok=False)])

    result = probe.ping_device('10.241.1.2')
    assert result['rtt_max'] - result['rtt_min'] == pytest.approx(0.1, abs=0.01)


def test_a_clean_check_is_unchanged_by_the_filtering(pinger):
    probe, sent = pinger
    sent['response'] = FakeResponse(
        True, avg=6.0, low=4.0, high=9.0, loss=0.0,
        packets=[FakePacket(4.0), FakePacket(5.0), FakePacket(9.0)])

    result = probe.ping_device('10.12.1.2')
    assert result['response_time'] == 6.0
    assert result['rtt_min'] == 4.0 and result['rtt_max'] == 9.0
    assert result['packet_loss'] == 0.0


def test_a_response_that_cannot_be_walked_falls_back_to_the_library(pinger):
    # An older build may not expose the packets. Reporting a latency of zero
    # would be worse than reporting the library's contaminated average.
    probe, sent = pinger
    sent['response'] = FakeResponse(True, avg=6.0, low=4.0, high=9.0, not_iterable=True)

    result = probe.ping_device('10.12.1.2')
    assert result['response_time'] == 6.0
    assert result['rtt_min'] == 4.0 and result['rtt_max'] == 9.0
