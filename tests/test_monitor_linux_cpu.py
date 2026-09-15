"""Linux CPU must be utilisation, not the load average it used to be.

`cpu` was load1/cores*100. The load average counts processes blocked on disk
alongside processes actually running, so a host waiting on I/O reported as
busy while its CPUs were idle -- and that number sat in the same column, the
same chart and the same 85% threshold as the true percentage the Windows
hosts report. These tests hold the Linux figure to /proc/stat.
"""
from types import SimpleNamespace

import monitor as monitor_module
from monitor import NetworkMonitor


def stat(user=0, nice=0, system=0, idle=0, iowait=0, irq=0, softirq=0, steal=0):
    return 'cpu  %d %d %d %d %d %d %d %d' % (
        user, nice, system, idle, iowait, irq, softirq, steal)


def fresh():
    """A monitor without the database __init__ wants."""
    return NetworkMonitor.__new__(NetworkMonitor)


# ------------------------------------------------------- the measurement ----

def test_first_reading_has_nothing_to_difference_against():
    assert fresh()._cpu_percent_from_proc_stat('h', stat(user=100, idle=900)) is None


def test_second_reading_is_the_share_of_the_interval_spent_working():
    monitor = fresh()
    monitor._cpu_percent_from_proc_stat('h', stat(user=100, idle=900))
    # 30 ticks of work against 70 idle in the interval since.
    value = monitor._cpu_percent_from_proc_stat('h', stat(user=130, idle=970))

    assert value == 30.0


def test_iowait_counts_as_idle_not_as_work():
    """The exact case the load average got wrong: waiting on disk, CPU idle."""
    monitor = fresh()
    monitor._cpu_percent_from_proc_stat('h', stat(idle=0, iowait=0))
    value = monitor._cpu_percent_from_proc_stat('h', stat(idle=200, iowait=800))

    assert value == 0.0


def test_a_fully_busy_interval_reads_as_one_hundred():
    monitor = fresh()
    monitor._cpu_percent_from_proc_stat('h', stat(user=500, idle=500))
    assert monitor._cpu_percent_from_proc_stat('h', stat(user=1500, idle=500)) == 100.0


def test_system_and_steal_time_count_as_work():
    monitor = fresh()
    monitor._cpu_percent_from_proc_stat('h', stat())
    value = monitor._cpu_percent_from_proc_stat('h', stat(system=100, steal=100, idle=800))

    assert value == 20.0


def test_each_host_is_differenced_against_its_own_previous_reading():
    monitor = fresh()
    monitor._cpu_percent_from_proc_stat('a', stat(user=100, idle=900))
    monitor._cpu_percent_from_proc_stat('b', stat(user=5000, idle=5000))

    assert monitor._cpu_percent_from_proc_stat('a', stat(user=200, idle=1800)) == 10.0
    assert monitor._cpu_percent_from_proc_stat('b', stat(user=5900, idle=5100)) == 90.0


# ------------------------------------------------------------- bad input ----

def test_counters_going_backwards_give_no_reading():
    """A reboot resets /proc/stat; the delta would be meaningless."""
    monitor = fresh()
    monitor._cpu_percent_from_proc_stat('h', stat(user=9000, idle=9000))
    assert monitor._cpu_percent_from_proc_stat('h', stat(user=10, idle=10)) is None


def test_an_unchanged_counter_gives_no_reading():
    monitor = fresh()
    monitor._cpu_percent_from_proc_stat('h', stat(user=100, idle=900))
    assert monitor._cpu_percent_from_proc_stat('h', stat(user=100, idle=900)) is None


def test_a_reboot_still_leaves_the_host_measurable_afterwards():
    monitor = fresh()
    monitor._cpu_percent_from_proc_stat('h', stat(user=9000, idle=9000))
    monitor._cpu_percent_from_proc_stat('h', stat(user=10, idle=10))
    # The rejected reading is still stored, so the next poll works normally.
    assert monitor._cpu_percent_from_proc_stat('h', stat(user=35, idle=85)) == 25.0


def test_unparsable_or_truncated_lines_give_no_reading():
    monitor = fresh()
    for line in ('', '   ', None, 'cpu', 'cpu  1 2 3 4', 'cpu  a b c d e', 'intr 1 2 3 4 5'):
        assert monitor._cpu_percent_from_proc_stat('h', line) is None


# --------------------------------------------------------- end to end ----

class FakeStream:
    def __init__(self, value=''):
        self.value = value.encode()

    def read(self):
        return self.value


class FakeSSHClient:
    """Answers the commands check_ssh issues, with a settable /proc/stat."""

    def __init__(self, counters):
        self.counters = counters

    def set_missing_host_key_policy(self, _policy):
        pass

    def connect(self, *_args, **_kwargs):
        pass

    def exec_command(self, command):
        return None, FakeStream(self.output_for(command)), FakeStream()

    def output_for(self, command):
        if command.startswith("grep '^cpu '"):
            return '%s\n 11:20 up 2 days, load average: 3.90, 3.80, 3.70' % self.counters
        if command == 'free -m | grep Mem':
            return 'Mem: 1000 500 100 0 400 500'
        if command.startswith('df -P -k'):
            return '/dev/sda1 100000 20000 80000 20% /'
        if command.startswith("free -m | awk '/^Swap:"):
            return '0 0'
        if command.startswith('df -Pi'):
            return '5'
        return ''

    def close(self):
        pass


def run_checks(monkeypatch, first, second):
    clients = [FakeSSHClient(first), FakeSSHClient(second)]
    monkeypatch.setattr(monitor_module, 'paramiko', SimpleNamespace(
        SSHClient=lambda: clients.pop(0),
        AutoAddPolicy=lambda: object(),
    ))
    monitor = fresh()
    return (monitor.check_ssh('10.0.0.1', 'user', 'password'),
            monitor.check_ssh('10.0.0.1', 'user', 'password'))


def test_check_ssh_reports_utilisation_across_two_polls(monkeypatch):
    first, second = run_checks(
        monkeypatch,
        stat(user=1000, idle=8000, iowait=500),
        stat(user=1200, idle=8700, iowait=600),
    )

    assert first['cpu'] is None
    # 200 ticks of work in an interval of 1000.
    assert second['cpu'] == 20.0


def test_check_ssh_keeps_reporting_the_load_averages(monkeypatch):
    """Still collected, and still shown beside the figure -- just not as CPU."""
    _, second = run_checks(monkeypatch, stat(idle=1000), stat(idle=2000))

    assert second['load1'] == 3.90
    assert second['load5'] == 3.80
    assert second['load15'] == 3.70


def test_a_host_at_high_load_but_idle_cpus_no_longer_reads_as_busy(monkeypatch):
    """load1 3.90 on 4 cores was reported as 97.5% CPU. The CPUs are asleep."""
    _, second = run_checks(
        monkeypatch,
        stat(user=100, idle=100, iowait=100),
        stat(user=100, idle=200, iowait=1000),
    )

    assert second['cpu'] == 0.0
