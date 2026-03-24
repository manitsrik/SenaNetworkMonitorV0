"""
Bandwidth monitoring API routes
Provides SNMP-based interface traffic data
"""
from flask import Blueprint, jsonify, request, render_template, current_app
from .auth import login_required

bandwidth_bp = Blueprint('bandwidth', __name__)


def _get_db():
    return current_app.config['DB']

def _get_monitor():
    return current_app.config['MONITOR']


@bandwidth_bp.route('/bandwidth')
@login_required
def bandwidth_page():
    """Bandwidth monitoring page"""
    return render_template('bandwidth.html')


@bandwidth_bp.route('/api/bandwidth/devices')
@login_required
def bandwidth_devices():
    """Get list of SNMP devices for the device selector"""
    db = _get_db()
    devices = db.get_all_devices()
    snmp_devices = [
        {'id': d['id'], 'name': d['name'], 'ip_address': d['ip_address']}
        for d in devices if d.get('monitor_type') == 'snmp'
    ]
    return jsonify({'success': True, 'devices': snmp_devices})


@bandwidth_bp.route('/api/bandwidth/interfaces')
@login_required
def bandwidth_interfaces():
    """Get available interfaces for a device (from latest samples)"""
    device_id = request.args.get('device_id', type=int)
    if not device_id:
        return jsonify({'success': False, 'error': 'device_id required'}), 400
    
    db = _get_db()
    samples = db.get_latest_bandwidth_all_interfaces(device_id)
    interfaces = [
        {
            'if_index': s['if_index'],
            'if_name': s['if_name'],
            'if_speed': s.get('if_speed', 0),
            'bps_in': s.get('bps_in'),
            'bps_out': s.get('bps_out'),
            'util_in': s.get('util_in'),
            'util_out': s.get('util_out'),
        }
        for s in samples
    ]
    return jsonify({'success': True, 'interfaces': interfaces})


@bandwidth_bp.route('/api/bandwidth/history')
@login_required
def bandwidth_history():
    """Get bandwidth time-series data"""
    device_id = request.args.get('device_id', type=int)
    if_index = request.args.get('if_index', type=int)
    minutes = request.args.get('minutes', 60, type=int)
    
    if not device_id:
        return jsonify({'success': False, 'error': 'device_id required'}), 400
    
    db = _get_db()
    rows = db.get_bandwidth_history(device_id, if_index=if_index, minutes=minutes)
    
    # Convert timestamps to strings for JSON serialization
    for row in rows:
        if row.get('sampled_at'):
            row['sampled_at'] = str(row['sampled_at'])
    
    return jsonify({'success': True, 'history': rows})


@bandwidth_bp.route('/api/bandwidth/current')
@login_required
def bandwidth_current():
    """Get latest bandwidth for all SNMP devices (for dashboard/overview)"""
    db = _get_db()
    
    # Get top interfaces
    top = db.get_top_bandwidth_interfaces(minutes=5, top_n=20)
    
    # Get specific interfaces if requested (format: ids=1:3,2:5)
    ids_param = request.args.get('ids')
    specific = []
    if ids_param:
        try:
            interface_list = []
            for item in ids_param.split(','):
                if ':' in item:
                    dev_id, if_idx = item.split(':')
                    interface_list.append((int(dev_id), int(if_idx)))
            if interface_list:
                specific = db.get_bandwidth_interfaces_by_ids(interface_list, minutes=5)
        except Exception as e:
            print(f"[BW] Error parsing specific IDs: {e}")

    # Merge and deduplicate
    # We use (device_id, if_index) as unique key
    merged = top
    top_keys = set((row['device_id'], row['if_index']) for row in merged)
    
    for row in specific:
        if (row['device_id'], row['if_index']) not in top_keys:
            merged.append(row)

    # Format numbers for display
    for row in merged:
        for key in ('avg_bps_in', 'avg_bps_out', 'max_bps_in', 'max_bps_out',
                    'avg_util_in', 'avg_util_out'):
            if row.get(key) is not None:
                row[key] = round(float(row[key]), 2)
    
    return jsonify({'success': True, 'top_interfaces': merged})


@bandwidth_bp.route('/api/bandwidth/poll', methods=['POST'])
@login_required
def trigger_poll():
    """Manually trigger a bandwidth poll for one device (non-blocking)"""
    import eventlet
    data = request.json or {}
    device_id = data.get('device_id')
    
    if not device_id:
        return jsonify({'success': False, 'error': 'device_id required'}), 400
    
    db = _get_db()
    monitor = _get_monitor()
    device = db.get_device(device_id)
    
    if not device:
        return jsonify({'success': False, 'error': 'Device not found'}), 404
    
    if device.get('monitor_type') != 'snmp':
        return jsonify({'success': False, 'error': 'Device must use SNMP monitoring'}), 400
    
    # Run poll in background green thread — returns immediately
    def _do_poll():
        try:
            monitor.poll_bandwidth(device)
        except Exception as e:
            print(f"[BW] Manual poll error for {device.get('name')}: {e}")

    eventlet.spawn(_do_poll)
    return jsonify({
        'success': True,
        'message': f"Poll started for {device['name']}. Refresh in a few seconds to see data."
    })



@bandwidth_bp.route('/api/bandwidth/debug')
@login_required
def bandwidth_debug_list():
    """List all SNMP devices so user can find the correct device_id"""
    db = _get_db()
    devices = db.get_all_devices()
    snmp_devices = [
        {
            'id': d['id'],
            'name': d['name'],
            'ip_address': d['ip_address'],
            'monitor_type': d.get('monitor_type'),
            'debug_url': f"/api/bandwidth/debug/{d['id']}"
        }
        for d in devices if d.get('monitor_type') == 'snmp'
    ]
    return jsonify({
        'info': 'Copy a device_id and open the debug_url in your browser',
        'snmp_devices': snmp_devices
    })


@bandwidth_bp.route('/api/bandwidth/debug/<int:device_id>')
@login_required
def bandwidth_debug(device_id):
    """
    Fast diagnostic: tests SNMP for interface 1 only (4 OIDs), shows DB samples.
    Returns in <15s. Navigate to: /api/bandwidth/debug/<device_id>
    """
    import asyncio
    import eventlet.tpool

    db = _get_db()
    device = db.get_device(device_id)
    if not device:
        return jsonify({'error': 'Device not found'}), 404

    result = {
        'device': device['name'],
        'ip': device['ip_address'],
        'community': device.get('snmp_community', 'public'),
        'port': device.get('snmp_port', 161),
        'version': device.get('snmp_version', '2c'),
        'steps': [],
        'errors': [],
        'if1_raw': {},
        'db_sample_count': 0,
        'db_samples': []
    }

    # Test 1: SNMP GET for interface 1 only (4 OIDs)
    try:
        from pysnmp.hlapi.v3arch.asyncio import (
            SnmpEngine, get_cmd, UdpTransportTarget, ContextData,
            CommunityData, UsmUserData, ObjectType, ObjectIdentity
        )
        result['steps'].append('pysnmp import OK')
    except Exception as e:
        result['errors'].append(f'pysnmp import FAILED: {e}')
        return jsonify(result)

    def _snmp_test():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            community = device.get('snmp_community', 'public')
            port = device.get('snmp_port', 161)
            version = device.get('snmp_version', '2c')
            mp_model = 0 if version == '1' else 1
            auth_data = CommunityData(community, mpModel=mp_model)

            async def _run():
                engine = SnmpEngine()
                transport = await UdpTransportTarget.create(
                    (device['ip_address'], port), timeout=5, retries=1
                )
                # Query sysDescr (known-working OID) + if1 counters
                errInd, errStat, _, varBinds = await get_cmd(
                    engine, auth_data, transport, ContextData(),
                    ObjectType(ObjectIdentity('1.3.6.1.2.1.1.1.0')),       # sysDescr
                    ObjectType(ObjectIdentity('1.3.6.1.2.1.2.2.1.2.1')),   # ifDescr.1
                    ObjectType(ObjectIdentity('1.3.6.1.2.1.2.2.1.5.1')),   # ifSpeed.1
                    ObjectType(ObjectIdentity('1.3.6.1.2.1.2.2.1.10.1')),  # ifInOctets.1
                    ObjectType(ObjectIdentity('1.3.6.1.2.1.2.2.1.16.1')),  # ifOutOctets.1
                )
                return str(errInd or ''), str(errStat or ''), [
                    {'oid': str(vb[0]), 'value': str(vb[1]), 'type': type(vb[1]).__name__}
                    for vb in varBinds
                ]

            return loop.run_until_complete(_run())
        finally:
            loop.close()

    try:
        errInd, errStat, rows = eventlet.tpool.execute(_snmp_test)
        result['if1_raw'] = {'error_indication': errInd, 'error_status': errStat, 'varbinds': rows}
        if errInd:
            result['errors'].append(f'SNMP error: {errInd}')
        elif errStat:
            result['errors'].append(f'SNMP status: {errStat}')
        else:
            result['steps'].append(f'SNMP GET returned {len(rows)} varbinds')
    except Exception as e:
        result['errors'].append(f'SNMP tpool exception: {e}')

    # Check DB for existing samples
    try:
        samples = db.get_latest_bandwidth_all_interfaces(device_id)
        result['db_sample_count'] = len(samples)
        result['db_samples'] = [
            {'if_index': s['if_index'], 'if_name': s['if_name'],
             'bytes_in': s.get('bytes_in'), 'bps_in': s.get('bps_in'),
             'sampled_at': str(s.get('sampled_at', ''))}
            for s in samples[:5]
        ]
        result['steps'].append(f'DB has {len(samples)} interface samples')
    except Exception as e:
        result['errors'].append(f'DB error: {e}')

    return jsonify(result)
