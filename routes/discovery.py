"""
Network discovery API routes
"""
import eventlet
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
    """Start a subnet scan in the background and return immediately."""
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

    # Run scan directly in a green thread.
    # Green threads yield during socket I/O, so Flask stays responsive.
    def _run_scan():
        try:
            discovery.scan_subnet(subnet, existing_ips)
        except Exception:
            discovery._is_scanning = False

    eventlet.spawn(_run_scan)
    
    return jsonify({'success': True, 'started': True, 'message': 'Scan started in background. Poll /api/discovery/status for progress.'})


@discovery_bp.route('/api/discovery/status', methods=['GET'])
@operator_required
def scan_status():
    """Get current scan status"""
    discovery = _get_discovery()
    return jsonify(discovery.get_scan_status())


@discovery_bp.route('/api/discovery/results', methods=['GET'])
@operator_required
def scan_results():
    """Get the completed scan results"""
    discovery = _get_discovery()
    if discovery.is_scanning:
        return jsonify({'success': False, 'error': 'Scan still running'}), 409
    
    import ipaddress
    results = discovery._scan_results or []
    
    return jsonify({
        'success': True,
        'total_scanned': discovery._scan_total,
        'total_skipped': discovery._scan_skipped,
        'discovered': len(results),
        'devices': results
    })


@discovery_bp.route('/api/discovery/reset', methods=['POST'])
@operator_required
def force_reset_scan():
    """Force reset / cancel the scan"""
    discovery = _get_discovery()
    discovery.cancel_scan()
    # Give workers a moment to notice the cancel flag
    eventlet.sleep(0.5)
    # Force clear state in case workers are stuck
    discovery._is_scanning = False
    discovery._cancel_requested = False
    discovery._scan_progress = 0
    discovery._scan_total = 0
    return jsonify({'success': True, 'message': 'Scan cancelled.'})


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
