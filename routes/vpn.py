"""
VPN branch-site health API routes

The server-health endpoints answer "how is this machine"; these answer "how is
the link to this branch". The devices are monitored by ICMP, so there is no CPU
or memory to report - what matters instead is whether the site answers, how fast
it answers, and how steady that answer is.
"""
from flask import Blueprint, jsonify, request, current_app
from datetime import datetime, timezone

from config import Config
from .auth import login_required

vpn_bp = Blueprint('vpn', __name__)

# Which devices this dashboard speaks for. Branch routers only: mixing in
# firewalls or core routers would put hardware with different latency budgets
# under one set of thresholds.
VPN_DEVICE_TYPES = ('vpnrouter',)

# A site that has not been checked in this long is reporting history, not state.
VPN_STALE_AFTER_SECONDS = max(600, int(getattr(Config, 'PING_INTERVAL', 60)) * 10)

# Fallbacks for the tunable thresholds, used only when the settings row is
# missing or unparseable. The live values come from alert_settings.
DEFAULT_DEGRADED_P95_MS = 100.0
DEFAULT_DEGRADED_JITTER_MS = 30.0
DEFAULT_DEGRADED_LOSS_PCT = 1.0


def _get_db():
    return current_app.config['DB']


def _parse_timestamp(raw):
    """Parse a timestamp from either the SQLite or PostgreSQL driver."""
    if raw is None or raw == '':
        return None
    if isinstance(raw, datetime):
        return raw
    text = str(raw).strip().replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S'):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
    return None


def _age_seconds(raw):
    """Age of a stored timestamp in seconds, or None when it cannot be read.

    Both columns this page reads - `last_check` and `last_status_change` - are
    written by update_device_status from a single local `datetime.now()`, so a
    naive value here is local time and nothing else.

    The server-health helper guesses between the local and UTC clocks because it
    also reads `last_metrics_time`, which the database fills in UTC. Reusing that
    guess here quietly subtracted the UTC offset from every age: a site down for
    16 days reported 15 days 17 hours, and the error grew with the offset rather
    than showing up as an obvious wrong answer.
    """
    parsed = _parse_timestamp(raw)
    if parsed is None:
        return None
    if parsed.tzinfo is not None:
        return max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds())
    return max(0.0, (datetime.now() - parsed).total_seconds())


def _setting_float(db, key, default):
    try:
        value = float(db.get_alert_setting(key))
        return value if value > 0 else default
    except (TypeError, ValueError):
        return default


def _thresholds(db):
    """The two numbers that decide what counts as degraded.

    They live in alert_settings rather than Config because they are new and will
    need tuning against real traffic; a deploy should not be the price of moving
    a threshold by 20 ms.
    """
    return {
        'degraded_p95_ms': _setting_float(db, 'vpn_degraded_p95_ms', DEFAULT_DEGRADED_P95_MS),
        'degraded_jitter_ms': _setting_float(db, 'vpn_degraded_jitter_ms', DEFAULT_DEGRADED_JITTER_MS),
        'degraded_loss_pct': _setting_float(db, 'vpn_degraded_loss_pct', DEFAULT_DEGRADED_LOSS_PCT),
        'slow_ms': Config.MONITOR_THRESHOLDS.get('ping', Config.DEFAULT_SLOW_THRESHOLD),
        'stale_after_seconds': VPN_STALE_AFTER_SECONDS,
        'ping_count': Config.PING_COUNT,
    }


def _vpn_devices(db, include_disabled=True):
    devices = [d for d in db.get_all_devices() if d.get('device_type') in VPN_DEVICE_TYPES]
    if include_disabled:
        return devices
    return [d for d in devices if d.get('is_enabled')]


def _classify(site, thresholds):
    """down | degraded | healthy, from the evidence in that order.

    Reachability is settled first because a site that is not answering cannot be
    judged on latency. Among the sites that do answer, two different faults land
    in the same bucket: a link that is slow or unsteady right now, and one that
    dropped out earlier in the window and came back. Both need a person to look.
    """
    if site['status'] == 'down':
        return 'down'
    if site['reach_pct'] is not None and site['reach_pct'] < 99.5:
        return 'degraded'
    if (site['p95'] or 0) >= thresholds['degraded_p95_ms']:
        return 'degraded'
    if (site['jitter'] or 0) >= thresholds['degraded_jitter_ms']:
        return 'degraded'
    # A link that answers every check but drops packets inside them. Nothing
    # else on the page would show this: the check succeeded, and the latency is
    # measured from the packets that made it back.
    if (site.get('packet_loss_pct') or 0) >= thresholds['degraded_loss_pct']:
        return 'degraded'
    return 'healthy'


def _build_sites(db, hours=24):
    devices = _vpn_devices(db)
    enabled = [d for d in devices if d.get('is_enabled')]
    quality = db.get_link_quality([d['id'] for d in enabled], hours=hours)
    thresholds = _thresholds(db)

    sites = []
    for device in enabled:
        stats = quality.get(device['id'], {})
        age = _age_seconds(device.get('last_check'))
        site = {
            'id': device['id'],
            'name': device.get('name'),
            'ip_address': device.get('ip_address'),
            'location': device.get('location'),
            'status': device.get('status'),
            'latitude': device.get('latitude'),
            'longitude': device.get('longitude'),
            'has_coordinates': device.get('latitude') is not None and device.get('longitude') is not None,
            'snmp_metrics_enabled': bool(device.get('snmp_metrics_enabled')),
            'response_time': device.get('response_time'),
            'last_check': device.get('last_check'),
            'last_status_change': device.get('last_status_change'),
            'checks': stats.get('checks', 0),
            'up_checks': int(stats.get('up_n') or 0),
            'slow_checks': int(stats.get('slow_n') or 0),
            'down_checks': int(stats.get('down_n') or 0),
            'reach_pct': stats.get('reach_pct'),
            'rtt_avg': stats.get('rtt_avg'),
            'rtt_min': stats.get('rtt_min'),
            'rtt_max': stats.get('rtt_max'),
            'p95': stats.get('p95'),
            'jitter': stats.get('jitter'),
            'packet_loss_pct': stats.get('loss_pct'),
            'packet_loss_samples': stats.get('loss_samples', 0),
            'flaps': stats.get('flaps', 0),
            'metrics_age_seconds': round(age, 1) if age is not None else None,
            'is_stale': bool(age is not None and age > VPN_STALE_AFTER_SECONDS),
        }
        site['state'] = _classify(site, thresholds)
        # How long the current state has held. For a site that is down this is
        # the outage itself, and it is not capped by the reporting window: an
        # outage that started three weeks ago should not read as 24 hours.
        change_age = _age_seconds(device.get('last_status_change'))
        site['state_age_seconds'] = round(change_age) if change_age is not None else None
        sites.append(site)

    rank = {'down': 0, 'degraded': 1, 'healthy': 2}
    sites.sort(key=lambda s: (rank.get(s['state'], 2), -(s['p95'] or 0), s['name'] or ''))
    return sites, devices, thresholds


@vpn_bp.route('/api/vpn-health', methods=['GET'])
@login_required
def get_vpn_health():
    """Branch-site health summary for every VPN router."""
    hours = max(1, min(request.args.get('hours', 24, type=int) or 24, 30 * 24))
    db = _get_db()
    sites, devices, thresholds = _build_sites(db, hours=hours)

    # Disabled sites carry their coordinates so the map can show them greyed
    # out. A branch nobody is checking is a blind spot, not an absent site, and
    # leaving it off the map makes the area look covered when it is not. They
    # stay out of every count below.
    disabled = [
        {'id': d['id'], 'name': d.get('name'), 'ip_address': d.get('ip_address'),
         'location': d.get('location'), 'last_check': d.get('last_check'),
         'latitude': d.get('latitude'), 'longitude': d.get('longitude'),
         'has_coordinates': d.get('latitude') is not None and d.get('longitude') is not None,
         'state': 'disabled'}
        for d in devices if not d.get('is_enabled')
    ]
    unmapped = [s for s in sites if not s['has_coordinates']]
    reachable = [s['reach_pct'] for s in sites if s['reach_pct'] is not None]

    return jsonify({
        'success': True,
        'hours': hours,
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'summary': {
            'total_sites': len(sites),
            'configured_sites': len(devices),
            'disabled': len(disabled),
            'down': sum(1 for s in sites if s['state'] == 'down'),
            'degraded': sum(1 for s in sites if s['state'] == 'degraded'),
            'healthy': sum(1 for s in sites if s['state'] == 'healthy'),
            'stale': sum(1 for s in sites if s['is_stale']),
            'mapped': len(sites) - len(unmapped),
            'unmapped': len(unmapped),
            'flaps': sum(s['flaps'] for s in sites),
            # Availability is averaged per site, not per check, so one busy site
            # cannot outvote a quiet one that was down all day.
            'availability_pct': round(sum(reachable) / len(reachable), 3) if reachable else None,
        },
        'sites': sites,
        'disabled_sites': disabled,
        'thresholds': thresholds,
    })


@vpn_bp.route('/api/vpn-health/status-timeline', methods=['GET'])
@login_required
def get_vpn_status_timeline():
    """Per-site status band over the window, worst site first."""
    hours = max(1, min(request.args.get('hours', 24, type=int) or 24, 30 * 24))
    buckets = max(12, min(request.args.get('buckets', 96, type=int) or 96, 480))

    db = _get_db()
    devices = {d['id']: d for d in _vpn_devices(db, include_disabled=False)}
    if not devices:
        return jsonify({'success': True, 'hours': hours, 'buckets': buckets, 'sites': []})

    timeline = db.get_status_timeline(list(devices), hours=hours, buckets=buckets)
    quality = db.get_link_quality(list(devices), hours=hours)
    thresholds = _thresholds(db)

    sites = []
    for device_id, device in devices.items():
        entry = timeline.get(device_id, {})
        counts = entry.get('counts') or {}
        total = sum(counts.values())
        stats = quality.get(device_id, {})
        row = {
            'id': device_id,
            'name': device.get('name'),
            'ip_address': device.get('ip_address'),
            'status': device.get('status'),
            'band': entry.get('band') or ['none'] * buckets,
            'mix': entry.get('mix') or [None] * buckets,
            'checks': total,
            'reach_pct': stats.get('reach_pct'),
            'p95': stats.get('p95'),
            'jitter': stats.get('jitter'),
            'packet_loss_pct': stats.get('loss_pct'),
        }
        row['state'] = _classify({
            'status': device.get('status'),
            'reach_pct': row['reach_pct'],
            'p95': row['p95'],
            'jitter': row['jitter'],
            'packet_loss_pct': row['packet_loss_pct'],
        }, thresholds)
        sites.append(row)

    rank = {'down': 0, 'degraded': 1, 'healthy': 2}
    sites.sort(key=lambda s: (rank.get(s['state'], 2), s['reach_pct'] if s['reach_pct'] is not None else 101,
                              -(s['p95'] or 0), s['name'] or ''))

    return jsonify({
        'success': True,
        'hours': hours,
        'buckets': buckets,
        'labels': timeline.get('__labels__', []),
        'sites': sites,
    })


@vpn_bp.route('/api/vpn-health/latency', methods=['GET'])
@login_required
def get_vpn_latency():
    """Fleet latency over time: the middle reply and the slow tail."""
    hours = max(1, min(request.args.get('hours', 24, type=int) or 24, 30 * 24))
    buckets = max(12, min(request.args.get('buckets', 96, type=int) or 96, 480))

    db = _get_db()
    device_ids = [d['id'] for d in _vpn_devices(db, include_disabled=False)]
    series = db.get_latency_percentile_series(device_ids, hours=hours, buckets=buckets)

    return jsonify({
        'success': True,
        'hours': hours,
        'buckets': buckets,
        'slow_threshold_ms': Config.MONITOR_THRESHOLDS.get('ping', Config.DEFAULT_SLOW_THRESHOLD),
        **series,
    })


@vpn_bp.route('/api/vpn-health/top-metrics', methods=['GET'])
@login_required
def get_vpn_top_metrics():
    """The five worst sites per measure, each with its own history beside it.

    Deliberately not a re-sort of the table below: two of these cards rank on
    figures the table does not carry at all - how much a site changed since the
    period before, and how its unreachable time was shaped - and the other two
    add the history that one number per site cannot show.
    """
    hours = max(1, min(request.args.get('hours', 24, type=int) or 24, 30 * 24))
    buckets = max(8, min(request.args.get('buckets', 40, type=int) or 40, 120))
    limit = max(3, min(request.args.get('limit', 5, type=int) or 5, 25))

    db = _get_db()
    devices = {d['id']: d for d in _vpn_devices(db, include_disabled=False)}
    if not devices:
        return jsonify({'success': True, 'hours': hours, 'buckets': buckets, 'cards': []})

    ids = list(devices)
    thresholds = _thresholds(db)
    current = db.get_link_quality(ids, hours=hours)
    previous = db.get_link_quality(ids, hours=hours, offset_hours=hours)
    outages = db.get_outage_episodes(ids, hours=hours)
    series = db.get_link_quality_series(ids, hours=hours, buckets=buckets)
    # The downtime card has no line to draw - a total is one number. What it can
    # show in that space is when the site was missing, which is the question a
    # total leaves open: one long outage overnight reads very differently from
    # the same minutes scattered through the working day.
    bands = db.get_status_timeline(ids, hours=hours, buckets=buckets)

    def base(device_id):
        device = devices[device_id]
        stats = current.get(device_id, {})
        site = {
            'status': device.get('status'),
            'reach_pct': stats.get('reach_pct'),
            'p95': stats.get('p95'),
            'jitter': stats.get('jitter'),
            'packet_loss_pct': stats.get('loss_pct'),
        }
        return {
            'id': device_id,
            'name': device.get('name'),
            'ip_address': device.get('ip_address'),
            'state': _classify(site, thresholds),
        }

    # --- deterioration: ranked on the change, not the level ------------------
    #
    # A rise has to clear both an absolute and a relative floor. Without the
    # first, a site going from 5.0 to 5.3 ms tops the card; without the second,
    # a 2 ms move on a 300 ms link counts for as much as one that doubled.
    deterioration = []
    for device_id in ids:
        now_p95 = (current.get(device_id) or {}).get('p95')
        was_p95 = (previous.get(device_id) or {}).get('p95')
        if now_p95 is None or was_p95 is None:
            continue
        delta = now_p95 - was_p95
        if delta < 1.0 or delta < was_p95 * 0.1:
            continue
        deterioration.append(dict(base(device_id),
                                  rank_value=round(delta, 1),
                                  current=now_p95, previous=was_p95,
                                  change_pct=round(delta / was_p95 * 100) if was_p95 else None,
                                  unit='ms',
                                  series=(series.get(device_id) or {}).get('peak', [])))

    # --- downtime: the same minutes, shaped two different ways ---------------
    downtime, longest = [], []
    for device_id in ids:
        entry = outages.get(device_id) or {}
        total = entry.get('downtime_seconds') or 0
        worst = entry.get('longest_outage_seconds') or 0
        band = (bands.get(device_id) or {}).get('band') or []
        if total > 0:
            downtime.append(dict(base(device_id), rank_value=round(total / 60, 1),
                                 current=round(total / 60, 1), episodes=entry.get('episodes', 0),
                                 unit='min', series=[], band=band))
        if worst > 0:
            longest.append(dict(base(device_id), rank_value=round(worst / 60, 1),
                                current=round(worst / 60, 1), episodes=entry.get('episodes', 0),
                                unit='min', series=[], band=band))

    # --- jitter and latency: the table's figures, plus their history ---------
    jitter_rows, latency_rows = [], []
    for device_id in ids:
        stats = current.get(device_id) or {}
        points = series.get(device_id) or {}
        if stats.get('jitter') is not None:
            jitter_rows.append(dict(base(device_id), rank_value=stats['jitter'],
                                    current=stats['jitter'], unit='ms',
                                    series=points.get('jitter', [])))
        if stats.get('p95') is not None:
            latency_rows.append(dict(base(device_id), rank_value=stats['p95'],
                                     current=devices[device_id].get('response_time'),
                                     average=stats.get('rtt_avg'), unit='ms',
                                     series=points.get('peak', [])))

    def top(rows):
        return sorted(rows, key=lambda r: -(r.get('rank_value') or 0))[:limit]

    return jsonify({
        'success': True,
        'hours': hours,
        'buckets': buckets,
        'cards': [
            {'key': 'deterioration', 'title': 'Biggest Deterioration', 'unit': 'ms',
             'ranked_by': 'how far p95 rose against the same length of time before it',
             'empty': 'No site is measurably slower than it was in the period before.',
             'rows': top(deterioration)},
            {'key': 'downtime', 'title': 'Most Downtime', 'unit': 'min',
             'ranked_by': 'minutes with no reply over the window',
             'empty': 'Every site answered every check.',
             'rows': top(downtime), 'longest': top(longest),
             'alt_label': 'Longest run',
             'alt_ranked_by': 'the single longest unbroken run of failed checks'},
            {'key': 'jitter', 'title': 'Top Jitter', 'unit': 'ms',
             'ranked_by': 'the average spread between the fastest and slowest packet inside one check',
             'empty': 'No jitter has been recorded yet.',
             'rows': top(jitter_rows)},
            {'key': 'latency', 'title': 'Top Latency', 'unit': 'ms',
             'ranked_by': 'p95 over the window, with the latest reading beside it',
             'empty': 'No replies recorded in this window.',
             'rows': top(latency_rows)},
        ],
    })


@vpn_bp.route('/api/vpn-site/<int:device_id>', methods=['GET'])
@login_required
def get_vpn_site(device_id):
    """One branch in detail, and the others it can be held against.

    The fleet view can say six sites are unsteady; only an overlay can say
    whether they are unsteady at the same moments, which is the difference
    between six faults and one shared cause.
    """
    hours = max(1, min(request.args.get('hours', 24, type=int) or 24, 30 * 24))
    buckets = max(24, min(request.args.get('buckets', 120, type=int) or 120, 480))

    db = _get_db()
    device = db.get_device(device_id)
    if not device or device.get('device_type') not in VPN_DEVICE_TYPES:
        return jsonify({'success': False, 'error': 'Not a VPN site'}), 404

    thresholds = _thresholds(db)
    stats = (db.get_link_quality([device_id], hours=hours) or {}).get(device_id, {})
    previous = (db.get_link_quality([device_id], hours=hours, offset_hours=hours) or {}).get(device_id, {})
    outage_summary = (db.get_outage_episodes([device_id], hours=hours) or {}).get(device_id, {})

    # Only other enabled VPN sites can be compared against, and only ones the
    # caller named: overlaying all twenty-five would draw a thicket.
    raw = (request.args.get('compare') or '').split(',')
    wanted = []
    for value in raw:
        try:
            wanted.append(int(value))
        except (TypeError, ValueError):
            continue
    allowed = {d['id']: d for d in _vpn_devices(db, include_disabled=False)}
    compare_ids = [i for i in wanted if i in allowed and i != device_id][:5]

    series = db.get_link_quality_series([device_id] + compare_ids, hours=hours, buckets=buckets)
    timeline = db.get_status_timeline([device_id], hours=hours, buckets=buckets)
    own = series.get(device_id) or {}

    age = _age_seconds(device.get('last_check'))
    site = {
        'id': device_id,
        'name': device.get('name'),
        'ip_address': device.get('ip_address'),
        'location': device.get('location'),
        'status': device.get('status'),
        'response_time': device.get('response_time'),
        'latitude': device.get('latitude'),
        'longitude': device.get('longitude'),
        'has_coordinates': device.get('latitude') is not None and device.get('longitude') is not None,
        'snmp_metrics_enabled': bool(device.get('snmp_metrics_enabled')),
        'last_check': device.get('last_check'),
        'last_status_change': device.get('last_status_change'),
        'checks': stats.get('checks', 0),
        'up_checks': int(stats.get('up_n') or 0),
        'slow_checks': int(stats.get('slow_n') or 0),
        'down_checks': int(stats.get('down_n') or 0),
        'reach_pct': stats.get('reach_pct'),
        'rtt_avg': stats.get('rtt_avg'),
        'rtt_min': stats.get('rtt_min'),
        'rtt_max': stats.get('rtt_max'),
        'p95': stats.get('p95'),
        'jitter': stats.get('jitter'),
        'packet_loss_pct': stats.get('loss_pct'),
        'packet_loss_samples': stats.get('loss_samples', 0),
        'flaps': stats.get('flaps', 0),
        'metrics_age_seconds': round(age, 1) if age is not None else None,
        'is_stale': bool(age is not None and age > VPN_STALE_AFTER_SECONDS),
    }
    site['state'] = _classify(site, thresholds)
    change_age = _age_seconds(device.get('last_status_change'))
    site['state_age_seconds'] = round(change_age) if change_age is not None else None

    entry = timeline.get(device_id, {})
    return jsonify({
        'success': True,
        'hours': hours,
        'buckets': buckets,
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'site': site,
        # The same figures over the window before this one, so the page can say
        # whether what it shows is normal for this branch or new.
        'previous': {
            'p95': previous.get('p95'),
            'jitter': previous.get('jitter'),
            'reach_pct': previous.get('reach_pct'),
            'packet_loss_pct': previous.get('loss_pct'),
        },
        'downtime_seconds': outage_summary.get('downtime_seconds'),
        'longest_outage_seconds': outage_summary.get('longest_outage_seconds'),
        'episodes': outage_summary.get('episodes', 0),
        'outages': db.get_outage_list(device_id, hours=hours),
        'labels': timeline.get('__labels__', []),
        'band': entry.get('band') or [],
        'mix': entry.get('mix') or [],
        'peak_series': own.get('peak', []),
        'typical_series': own.get('typical', []),
        'jitter_series': own.get('jitter', []),
        'compare': [
            {'id': i, 'name': allowed[i].get('name'), 'ip_address': allowed[i].get('ip_address'),
             'peak_series': (series.get(i) or {}).get('peak', []),
             'jitter_series': (series.get(i) or {}).get('jitter', [])}
            for i in compare_ids
        ],
        'siblings': [
            {'id': d['id'], 'name': d.get('name')}
            for d in sorted(allowed.values(), key=lambda x: (x.get('name') or '').lower())
            if d['id'] != device_id
        ],
        'thresholds': thresholds,
    })


@vpn_bp.route('/api/vpn-health/summary-trend', methods=['GET'])
@login_required
def get_vpn_summary_trend():
    """Hourly site counts behind the headline figures, for the KPI sparklines."""
    hours = max(2, min(request.args.get('hours', 24, type=int) or 24, 7 * 24))

    db = _get_db()
    device_ids = [d['id'] for d in _vpn_devices(db, include_disabled=False)]
    rows = db.get_status_counts_by_hour(device_ids, hours=hours)

    return jsonify({
        'success': True,
        'hours': hours,
        'labels': [row['hour_label'] for row in rows],
        'up': [int(row['up_n'] or 0) for row in rows],
        'slow': [int(row['slow_n'] or 0) for row in rows],
        'down': [int(row['down_n'] or 0) for row in rows],
        'seen': [int(row['seen_n'] or 0) for row in rows],
    })
