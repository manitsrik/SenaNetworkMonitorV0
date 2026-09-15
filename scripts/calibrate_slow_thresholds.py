"""Derive each server's SLOW threshold from how that server actually behaves.

There is no standard figure for agent collection time: it measures the
collection path, not the server. On this fleet an SSH check settles around
1-2s while a WinRM check on the same kind of work takes 7-38s, so one shared
default either screams on every poll for the slow hosts or never fires at all
for the fast ones. Both make the SLOW status meaningless.

The threshold is taken from the host's own distribution instead:

    threshold = max(p99 x SAFETY, p50 x MIN_HEADROOM)

p99 keeps normal variation quiet; the p50 term stops a host with a very tight
distribution from getting a threshold it will trip on ordinary jitter. SLOW
then means "this host is behaving unlike itself" rather than "this host
speaks WinRM".

Usage:
    python scripts/calibrate_slow_thresholds.py                 # dry run
    python scripts/calibrate_slow_thresholds.py --apply
    python scripts/calibrate_slow_thresholds.py --apply --days 14
    python scripts/calibrate_slow_thresholds.py --reset         # back to defaults

Raising a threshold makes the alert honest; it does not make the host fast.
A host whose p50 sits far above its peers is worth investigating regardless of
what this script writes, and the report says so.
"""
import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from database import Database

SERVER_MONITOR_TYPES = ('ssh', 'winrm', 'wmi')

# p99 x 1.25 leaves room for a slow day without swallowing a real regression.
SAFETY = 1.25
# Never sit closer than 2x the median, however tight the distribution is.
MIN_HEADROOM = 2.0
# Below this many samples the percentiles are not worth trusting.
MIN_SAMPLES = 200
# A host this much more variable than its median is genuinely erratic: the
# spikes are real events, not a mis-set threshold.
ERRATIC_RATIO = 3.0


def percentile(values, p):
    ordered = sorted(values)
    if not ordered:
        return None
    k = (len(ordered) - 1) * p / 100.0
    low = int(k)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (k - low)


def round_up(ms):
    """Round to a figure a human would have typed."""
    step = 1000 if ms <= 10000 else 5000
    return int(-(-ms // step) * step)


def collect(db, days):
    """Response times per server device over the window, from status_history."""
    conn = db.get_connection()
    try:
        cursor = db._cursor(conn)
        cutoff = (
            f"NOW() - INTERVAL '{days} days'" if db.db_type == 'postgresql'
            else f"datetime('now', '-{days} days')"
        )
        cursor.execute(f'''
            SELECT d.id, d.name, d.monitor_type, d.slow_threshold_ms, h.response_time
            FROM status_history h
            JOIN devices d ON d.id = h.device_id
            WHERE d.monitor_type IN {SERVER_MONITOR_TYPES}
              AND h.checked_at >= {cutoff}
              AND h.response_time IS NOT NULL
              AND h.status IN ('up', 'slow')
        ''')
        rows = db._rows_to_dicts(cursor.fetchall())
    finally:
        db.release_connection(conn)

    samples = {}
    for row in rows:
        entry = samples.setdefault(row['id'], {
            'id': row['id'],
            'name': row['name'],
            'monitor_type': row['monitor_type'],
            'current': row['slow_threshold_ms'],
            'values': [],
        })
        entry['values'].append(float(row['response_time']))
    return samples


def analyse(entry):
    values = entry['values']
    default = Config.MONITOR_THRESHOLDS.get(entry['monitor_type'], Config.DEFAULT_SLOW_THRESHOLD)
    p50 = percentile(values, 50)
    p99 = percentile(values, 99)
    effective = entry['current'] or default

    result = dict(entry)
    result.pop('values')
    result.update({
        'samples': len(values),
        'p50': round(p50),
        'p95': round(percentile(values, 95)),
        'p99': round(p99),
        'max': round(max(values)),
        'default': default,
        'effective': effective,
        'breach_rate': sum(1 for v in values if v > effective) / len(values),
        'erratic': (p99 / p50) >= ERRATIC_RATIO if p50 else False,
    })

    if len(values) < MIN_SAMPLES:
        result['suggested'] = None
        result['skip_reason'] = f'only {len(values)} samples'
    else:
        result['suggested'] = round_up(max(p99 * SAFETY, p50 * MIN_HEADROOM))
        result['skip_reason'] = None
    return result


def report(findings):
    print(f"\n{'server':24s} {'type':6s} {'n':>6s} {'p50':>7s} {'p99':>7s} "
          f"{'now':>7s} {'new':>7s} {'fires now':>10s}")
    print('-' * 82)
    for f in findings:
        new = str(f['suggested']) if f['suggested'] else 'skip'
        fires = f"{f['breach_rate'] * 100:.0f}%"
        print(f"{f['name'][:24]:24s} {f['monitor_type']:6s} {f['samples']:6d} "
              f"{f['p50']:7d} {f['p99']:7d} {f['effective']:7d} {new:>7s} {fires:>10s}")

    erratic = [f for f in findings if f['erratic']]
    if erratic:
        print('\nGenuinely erratic (p99 at least %.0fx the median) -- the spikes are real '
              'events,\nso a higher threshold quiets the alert without addressing them:'
              % ERRATIC_RATIO)
        for f in erratic:
            print(f"  - {f['name']}: {f['p50']}ms typical, {f['max']}ms worst")

    slowest = max((f for f in findings if f['suggested']), key=lambda f: f['p50'], default=None)
    if slowest and slowest['p50'] > 15000:
        print(f"\n{slowest['name']} takes {slowest['p50'] / 1000:.0f}s on a typical collection. "
              f"Raising its\nthreshold stops the false alarms; it does not make the host healthy.")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--days', type=int, default=7,
                        help='window of history to baseline against (default: 7)')
    parser.add_argument('--apply', action='store_true',
                        help='write the thresholds (default is a dry run)')
    parser.add_argument('--reset', action='store_true',
                        help='clear every per-device threshold, restoring the shared defaults')
    args = parser.parse_args()

    db = Database()

    if args.reset:
        devices = [d for d in db.get_all_devices() if d.get('monitor_type') in SERVER_MONITOR_TYPES]
        if not args.apply:
            print(f'Dry run: would clear the threshold on {len(devices)} servers. '
                  'Re-run with --apply.')
            return 0
        for device in devices:
            db.update_device(device['id'], slow_threshold_ms=None)
        print(f'Cleared the threshold on {len(devices)} servers.')
        return 0

    samples = collect(db, args.days)
    if not samples:
        print(f'No response-time history in the last {args.days} days.')
        return 1

    findings = sorted((analyse(e) for e in samples.values()), key=lambda f: -f['p50'])
    report(findings)

    changes = [f for f in findings if f['suggested'] and f['suggested'] != f['current']]
    if not changes:
        print('\nEvery threshold already matches its baseline. Nothing to do.')
        return 0

    if not args.apply:
        print(f'\nDry run: {len(changes)} thresholds would change. Re-run with --apply to write them.')
        return 0

    # Keep what was there, so the change can be undone without re-deriving it.
    backup_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'backups',
        f'slow_thresholds_{datetime.now():%Y%m%d_%H%M%S}.json',
    )
    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
    with open(backup_path, 'w', encoding='utf-8') as handle:
        json.dump([{'id': f['id'], 'name': f['name'], 'slow_threshold_ms': f['current']}
                   for f in findings], handle, indent=2)
    print(f'\nPrevious values saved to {backup_path}')

    for f in changes:
        db.update_device(f['id'], slow_threshold_ms=f['suggested'])
        print(f"  {f['name'][:28]:28s} {str(f['current'] or 'default'):>8s} -> {f['suggested']}")

    print(f'\nWrote {len(changes)} thresholds. They take effect on the next monitoring cycle.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
