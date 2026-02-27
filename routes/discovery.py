"""
Network discovery API routes
"""
from flask import Blueprint, jsonify, request, render_template, current_app
from .auth import login_required, operator_required

discovery_bp = Blueprint('discovery', __name__)


def _get_db():
    return current_app.config['DB']

def _get_discovery():
    return current_app.config['DISCOVERY']


@discovery_bp.route('/discovery')
@operator_required
def discovery_page():
    """Device discovery page"""
    return render_template('discovery.html')


@discovery_bp.route('/api/discovery/scan', methods=['POST'])
@operator_required
def start_scan():
    """Start a subnet scan"""
    data = request.json
    subnet = data.get('subnet', '').strip()
    
    if not subnet:
        return jsonify({'success': False, 'error': 'Subnet is required (e.g., 192.168.1.0/24)'}), 400
    
    db = _get_db()
    discovery = _get_discovery()
    
    if discovery.is_scanning:
        return jsonify({'success': False, 'error': 'A scan is already running'}), 409
    
    # Get existing device IPs to skip
    existing_devices = db.get_all_devices()
    existing_ips = {d['ip_address'] for d in existing_devices}
    
    # Run scan (this may take a while for large subnets)
    result = discovery.scan_subnet(subnet, skip_ips=existing_ips)
    
    if isinstance(result, dict) and 'error' in result:
        return jsonify({'success': False, 'error': result['error']}), 400
    
    return jsonify(result)


@discovery_bp.route('/api/discovery/status', methods=['GET'])
@operator_required
def scan_status():
    """Get current scan status"""
    discovery = _get_discovery()
    return jsonify(discovery.get_scan_status())


@discovery_bp.route('/api/discovery/add', methods=['POST'])
@operator_required
def add_discovered_devices():
    """Add selected discovered devices to monitoring"""
    data = request.json
    devices = data.get('devices', [])
    
    if not devices:
        return jsonify({'success': False, 'error': 'No devices selected'}), 400
    
    db = _get_db()
    added = 0
    failed = 0
    errors = []
    
    for device in devices:
        result = db.add_device(
            name=device.get('name', device['ip_address']),
            ip_address=device['ip_address'],
            device_type=device.get('device_type', 'unknown'),
            monitor_type=device.get('monitor_type', 'ping'),
            location=device.get('location'),
            location_type=device.get('location_type', 'on-premise')
        )
        
        if result['success']:
            added += 1
        else:
            failed += 1
            errors.append(f"{device['ip_address']}: {result.get('error', 'Unknown error')}")
    
    return jsonify({
        'success': True,
        'added': added,
        'failed': failed,
        'errors': errors
    })
