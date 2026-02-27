"""
Device management API routes
"""
from flask import Blueprint, jsonify, request, Response, current_app
import csv
import io
from .auth import login_required, operator_required

devices_bp = Blueprint('devices', __name__)


def _get_db():
    return current_app.config['DB']

def _get_monitor():
    return current_app.config['MONITOR']

def _get_socketio():
    return current_app.config['SOCKETIO']


@devices_bp.route('/api/devices', methods=['GET'])
def get_devices():
    """Get all devices"""
    devices = _get_db().get_all_devices()
    return jsonify(devices)


@devices_bp.route('/api/devices', methods=['POST'])
@operator_required
def add_device():
    """Add a new device"""
    data = request.json
    
    if not data.get('name') or not data.get('ip_address'):
        return jsonify({'success': False, 'error': 'Name and IP/URL are required'}), 400
    
    db = _get_db()
    result = db.add_device(
        name=data['name'],
        ip_address=data['ip_address'],
        device_type=data.get('device_type'),
        location=data.get('location'),
        monitor_type=data.get('monitor_type', 'ping'),
        expected_status_code=data.get('expected_status_code', 200),
        snmp_community=data.get('snmp_community', 'public'),
        snmp_port=data.get('snmp_port', 161),
        snmp_version=data.get('snmp_version', '2c'),
        tcp_port=data.get('tcp_port', 80),
        dns_query_domain=data.get('dns_query_domain', 'google.com'),
        location_type=data.get('location_type', 'on-premise')
    )
    
    if result['success']:
        device = db.get_device(result['id'])
        monitor = _get_monitor()
        status = monitor.check_device(device)
        _get_socketio().emit('status_update', status, namespace='/')
        return jsonify(result), 201
    else:
        return jsonify(result), 400


@devices_bp.route('/api/devices/<int:device_id>', methods=['PUT'])
@operator_required
def update_device(device_id):
    """Update a device"""
    data = request.json
    result = _get_db().update_device(
        device_id=device_id,
        name=data.get('name'),
        ip_address=data.get('ip_address'),
        device_type=data.get('device_type'),
        location=data.get('location'),
        monitor_type=data.get('monitor_type'),
        snmp_community=data.get('snmp_community'),
        snmp_port=data.get('snmp_port'),
        snmp_version=data.get('snmp_version'),
        tcp_port=data.get('tcp_port'),
        dns_query_domain=data.get('dns_query_domain'),
        location_type=data.get('location_type')
    )
    return jsonify(result)


@devices_bp.route('/api/devices/<int:device_id>', methods=['DELETE'])
@operator_required
def delete_device(device_id):
    """Delete a device"""
    result = _get_db().delete_device(device_id)
    _get_socketio().emit('device_deleted', {'id': device_id}, namespace='/')
    return jsonify(result)


@devices_bp.route('/api/status', methods=['GET'])
def get_status():
    """Get current status of all devices"""
    devices = _get_db().get_all_devices()
    return jsonify(devices)


@devices_bp.route('/api/statistics', methods=['GET'])
def get_statistics():
    """Get network statistics"""
    stats = _get_monitor().get_statistics()
    return jsonify(stats)


@devices_bp.route('/api/snmp/<int:device_id>/interfaces', methods=['GET'])
def get_snmp_interfaces(device_id):
    """Get SNMP interface table for a device"""
    db = _get_db()
    device = db.get_device(device_id)
    if not device:
        return jsonify({'error': 'Device not found'}), 404
    
    if device.get('monitor_type') != 'snmp':
        return jsonify({'error': 'Device is not SNMP monitored'}), 400
    
    monitor = _get_monitor()
    interfaces = monitor.get_snmp_interfaces(
        device['ip_address'],
        device.get('snmp_community', 'public'),
        device.get('snmp_port', 161),
        device.get('snmp_version', '2c')
    )
    
    return jsonify({
        'device_id': device_id,
        'device_name': device['name'],
        'interfaces': interfaces
    })


@devices_bp.route('/api/check/<int:device_id>', methods=['POST'])
@operator_required
def check_device_now(device_id):
    """Immediately check a specific device"""
    db = _get_db()
    device = db.get_device(device_id)
    if not device:
        return jsonify({'success': False, 'error': 'Device not found'}), 404
    
    monitor = _get_monitor()
    result = monitor.check_device(device)
    _get_socketio().emit('status_update', result, namespace='/')
    return jsonify(result)


@devices_bp.route('/api/statistics/trend', methods=['GET'])
def get_trend_statistics():
    """Get response time trends by device type"""
    minutes = request.args.get('minutes', 180, type=int)
    trends = _get_db().get_device_type_trends(minutes)
    return jsonify(trends)


# ============================================================================
# CSV Import/Export
# ============================================================================

@devices_bp.route('/api/devices/export/csv', methods=['GET'])
def export_devices_csv():
    """Export all devices as CSV"""
    devices = _get_db().get_all_devices()
    
    fieldnames = [
        'name', 'ip_address', 'device_type', 'location', 'location_type',
        'monitor_type', 'snmp_community', 'snmp_port', 'snmp_version',
        'tcp_port', 'dns_query_domain', 'expected_status_code'
    ]
    
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    
    for device in devices:
        row = {k: device.get(k, '') for k in fieldnames}
        writer.writerow(row)
    
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=devices_export.csv'}
    )


@devices_bp.route('/api/devices/import/csv', methods=['POST'])
@operator_required
def import_devices_csv():
    """Import devices from CSV file"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400
    
    if not file.filename.lower().endswith('.csv'):
        return jsonify({'success': False, 'error': 'File must be a CSV'}), 400
    
    try:
        content = file.stream.read().decode('utf-8')
        reader = csv.DictReader(io.StringIO(content))
        
        db = _get_db()
        results = {
            'success': True,
            'imported': 0,
            'failed': 0,
            'errors': []
        }
        
        for i, row in enumerate(reader, start=2):
            name = row.get('name', '').strip()
            ip_address = row.get('ip_address', '').strip()
            
            if not name or not ip_address:
                results['failed'] += 1
                results['errors'].append(f"Row {i}: Name and IP address are required")
                continue
            
            result = db.add_device(
                name=name,
                ip_address=ip_address,
                device_type=row.get('device_type', '').strip() or 'server',
                location=row.get('location', '').strip() or None,
                location_type=row.get('location_type', '').strip() or 'on-premise',
                monitor_type=row.get('monitor_type', '').strip() or 'ping',
                snmp_community=row.get('snmp_community', '').strip() or 'public',
                snmp_port=int(row.get('snmp_port') or 161),
                snmp_version=row.get('snmp_version', '').strip() or '2c',
                tcp_port=int(row.get('tcp_port') or 80),
                dns_query_domain=row.get('dns_query_domain', '').strip() or 'google.com',
                expected_status_code=int(row.get('expected_status_code') or 200)
            )
            
            if result['success']:
                results['imported'] += 1
            else:
                results['failed'] += 1
                results['errors'].append(f"Row {i}: {result.get('error', 'Unknown error')}")
        
        return jsonify(results)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
