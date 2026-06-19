"""
Device management API routes
"""
from flask import Blueprint, jsonify, request, Response, current_app, session
import csv
import io
import os
import json
from datetime import datetime
from .auth import login_required, operator_required
from .audit import log_audit

devices_bp = Blueprint('devices', __name__)


def _device_notes_dir():
    """Return the directory used for per-device text notes."""
    app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    notes_dir = os.path.join(app_root, 'device_notes')
    os.makedirs(notes_dir, exist_ok=True)
    return notes_dir


def _device_note_path(device_id):
    return os.path.join(_device_notes_dir(), f'{int(device_id)}.txt')


def _read_device_note(device_id):
    try:
        path = _device_note_path(device_id)
        if not os.path.exists(path):
            return ''
        with open(path, 'r', encoding='utf-8') as handle:
            return handle.read()
    except Exception:
        current_app.logger.exception('Failed to read note for device %s', device_id)
        return ''


def _simple_pdf(lines):
    """Create a dependency-free, text-based PDF document."""
    def pdf_text(value):
        text = str(value).encode('latin-1', 'replace').decode('latin-1')
        return text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')

    pages = [lines[index:index + 52] for index in range(0, len(lines), 52)] or [[]]
    objects = {
        1: b'<< /Type /Catalog /Pages 2 0 R >>',
        3: b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    }
    page_refs = []
    for index, page_lines in enumerate(pages):
        page_id = 4 + index * 2
        content_id = page_id + 1
        page_refs.append(f'{page_id} 0 R')
        stream_lines = ['BT', '/F1 10 Tf', '45 800 Td', '14 TL']
        for line in page_lines:
            stream_lines.extend([f'({pdf_text(line)}) Tj', 'T*'])
        stream_lines.append('ET')
        stream = '\n'.join(stream_lines).encode('latin-1')
        objects[page_id] = (
            f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] '
            f'/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>'
        ).encode('ascii')
        objects[content_id] = f'<< /Length {len(stream)} >>\nstream\n'.encode('ascii') + stream + b'\nendstream'
    objects[2] = f'<< /Type /Pages /Kids [{" ".join(page_refs)}] /Count {len(pages)} >>'.encode('ascii')

    output = bytearray(b'%PDF-1.4\n')
    offsets = [0] * (max(objects) + 1)
    for object_id in sorted(objects):
        offsets[object_id] = len(output)
        output.extend(f'{object_id} 0 obj\n'.encode('ascii'))
        output.extend(objects[object_id])
        output.extend(b'\nendobj\n')
    xref = len(output)
    output.extend(f'xref\n0 {len(offsets)}\n'.encode('ascii'))
    output.extend(b'0000000000 65535 f \n')
    for offset in offsets[1:]:
        output.extend(f'{offset:010d} 00000 n \n'.encode('ascii'))
    output.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode('ascii'))
    return bytes(output)


def _write_device_note(device_id, note):
    note_text = str(note or '').replace('\r\n', '\n').replace('\r', '\n')
    path = _device_note_path(device_id)
    if note_text.strip():
        with open(path, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(note_text)
    elif os.path.exists(path):
        os.remove(path)


def _get_db():
    return current_app.config['DB']

def _get_monitor():
    return current_app.config['MONITOR']

def _get_socketio():
    return current_app.config['SOCKETIO']

def _get_plugin_manager():
    return current_app.config['PLUGIN_MANAGER']


@devices_bp.route('/api/devices', methods=['GET'])
def get_devices():
    """Get all devices"""
    devices = _get_db().get_all_devices()
    for device in devices:
        if device.get('id') is not None:
            device['device_note'] = _read_device_note(device['id'])
    return jsonify(devices)


@devices_bp.route('/api/devices', methods=['POST'])
@operator_required
def add_device():
    """Add a new device"""
    data = request.json or {}
    
    if not data.get('name') or not data.get('ip_address'):
        return jsonify({'success': False, 'error': 'Name and IP/URL are required'}), 400

    monitor_type = data.get('monitor_type', 'ping')
    plugin_config_json = data.get('plugin_config_json')
    if str(monitor_type).startswith('plugin:'):
        try:
            plugin_config = plugin_config_json
            if isinstance(plugin_config_json, str):
                import json
                plugin_config = json.loads(plugin_config_json or '{}')
            validation = _get_plugin_manager().validate_plugin_config(monitor_type, plugin_config or {})
            if not validation.get('success'):
                return jsonify(validation), 400
            import json
            plugin_config_json = json.dumps(validation.get('config') or {}, ensure_ascii=False)
        except Exception as e:
            return jsonify({'success': False, 'error': f'Invalid plugin configuration: {e}'}), 400
    
    db = _get_db()
    result = db.add_device(
        name=data['name'],
        ip_address=data['ip_address'],
        device_type=data.get('device_type'),
        location=data.get('location'),
        monitor_type=monitor_type,
        expected_status_code=data.get('expected_status_code', 200),
        snmp_community=data.get('snmp_community', 'public'),
        snmp_port=data.get('snmp_port', 161),
        snmp_version=data.get('snmp_version', '2c'),
        snmp_v3_username=data.get('snmp_v3_username'),
        snmp_v3_auth_protocol=data.get('snmp_v3_auth_protocol', 'SHA'),
        snmp_v3_auth_password=data.get('snmp_v3_auth_password'),
        snmp_v3_priv_protocol=data.get('snmp_v3_priv_protocol', 'AES128'),
        snmp_v3_priv_password=data.get('snmp_v3_priv_password'),
        tcp_port=data.get('tcp_port', 80),
        dns_query_domain=data.get('dns_query_domain', 'google.com'),
        location_type=data.get('location_type', 'on-premise'),
        longitude=data.get('longitude'),
        is_enabled=data.get('is_enabled', True),
        parent_device_id=data.get('parent_device_id'),
        ssh_username=data.get('ssh_username'),
        ssh_password=data.get('ssh_password'),
        ssh_port=data.get('ssh_port', 22),
        wmi_username=data.get('wmi_username'),
        wmi_password=data.get('wmi_password'),
        expected_ports=data.get('expected_ports'),
        monitored_services=data.get('monitored_services'),
        cpu_threshold=data.get('cpu_threshold', 85),
        ram_threshold=data.get('ram_threshold', 90),
        disk_threshold=data.get('disk_threshold', 90),
        swap_threshold=data.get('swap_threshold', 80),
        threshold_duration_minutes=data.get('threshold_duration_minutes', 5),
        plugin_config_json=plugin_config_json
    )
    
    if result['success']:
        try:
            _write_device_note(result['id'], data.get('device_note', ''))
        except Exception as e:
            current_app.logger.exception('Failed to save note for device %s', result['id'])
            return jsonify({'success': False, 'error': f'Device added but note could not be saved: {e}'}), 500

        device = db.get_device(result['id'])
        # Only run initial check if monitoring is enabled
        if device.get('is_enabled'):
            monitor = _get_monitor()
            status = monitor.check_device(device)
            # Socket update for the initial check result
            socketio = _get_socketio()
            socketio.emit('status_update', status, namespace='/')
            
            # Global statistics update
            stats = monitor.get_statistics()
            socketio.emit('statistics_update', stats, namespace='/')
        else:
            # Broadcast the new device even if not checked yet
            socketio = _get_socketio()
            socketio.emit('status_update', {
                'id': device['id'],
                'name': device['name'],
                'ip_address': device['ip_address'],
                'device_type': device.get('device_type'),
                'monitor_type': device.get('monitor_type', 'ping'),
                'status': device['status'],
                'response_time': device['response_time'],
                'last_check': device.get('last_check')
            }, namespace='/')
        log_audit('create', 'device', 'device', result['id'], data['name'])
        return jsonify(result), 201
    else:
        return jsonify(result), 400


@devices_bp.route('/api/devices/<int:device_id>', methods=['PUT'])
@operator_required
def update_device(device_id):
    """Update a device"""
    data = request.json or {}
    monitor_type = data.get('monitor_type')
    plugin_config_json = data.get('plugin_config_json', '__NOT_SET__')
    if monitor_type and str(monitor_type).startswith('plugin:') and plugin_config_json != '__NOT_SET__':
        try:
            plugin_config = plugin_config_json
            if isinstance(plugin_config_json, str):
                import json
                plugin_config = json.loads(plugin_config_json or '{}')
            validation = _get_plugin_manager().validate_plugin_config(monitor_type, plugin_config or {})
            if not validation.get('success'):
                return jsonify(validation), 400
            import json
            plugin_config_json = json.dumps(validation.get('config') or {}, ensure_ascii=False)
        except Exception as e:
            return jsonify({'success': False, 'error': f'Invalid plugin configuration: {e}'}), 400
    # Handle parent_device_id — use sentinel to distinguish "not provided" vs "set to null"
    parent_kw = {}
    if 'parent_device_id' in data:
        parent_kw['parent_device_id'] = data.get('parent_device_id')
    
    result = _get_db().update_device(
        device_id=device_id,
        name=data.get('name'),
        ip_address=data.get('ip_address'),
        device_type=data.get('device_type'),
        location=data.get('location'),
        monitor_type=monitor_type,
        snmp_community=data.get('snmp_community'),
        snmp_port=data.get('snmp_port'),
        snmp_version=data.get('snmp_version'),
        snmp_v3_username=data.get('snmp_v3_username'),
        snmp_v3_auth_protocol=data.get('snmp_v3_auth_protocol'),
        snmp_v3_auth_password=data.get('snmp_v3_auth_password'),
        snmp_v3_priv_protocol=data.get('snmp_v3_priv_protocol'),
        snmp_v3_priv_password=data.get('snmp_v3_priv_password'),
        tcp_port=data.get('tcp_port'),
        dns_query_domain=data.get('dns_query_domain'),
        location_type=data.get('location_type'),
        latitude=data.get('latitude'),
        longitude=data.get('longitude'),
        is_enabled=data.get('is_enabled'),
        ssh_username=data.get('ssh_username', '__NOT_SET__'),
        ssh_password=data.get('ssh_password', '__NOT_SET__'),
        ssh_port=data.get('ssh_port', '__NOT_SET__'),
        wmi_username=data.get('wmi_username', '__NOT_SET__'),
        wmi_password=data.get('wmi_password', '__NOT_SET__'),
        expected_ports=data.get('expected_ports', '__NOT_SET__'),
        monitored_services=data.get('monitored_services', '__NOT_SET__'),
        cpu_threshold=data.get('cpu_threshold', '__NOT_SET__'),
        ram_threshold=data.get('ram_threshold', '__NOT_SET__'),
        disk_threshold=data.get('disk_threshold', '__NOT_SET__'),
        swap_threshold=data.get('swap_threshold', '__NOT_SET__'),
        threshold_duration_minutes=data.get('threshold_duration_minutes', '__NOT_SET__'),
        plugin_config_json=plugin_config_json,
        **parent_kw
    )
    if result.get('success') and 'device_note' in data:
        try:
            _write_device_note(device_id, data.get('device_note', ''))
        except Exception as e:
            current_app.logger.exception('Failed to save note for device %s', device_id)
            return jsonify({'success': False, 'error': f'Device updated but note could not be saved: {e}'}), 500

    log_audit('update', 'device', 'device', device_id, data.get('name'))
    return jsonify(result)


@devices_bp.route('/api/devices/<int:device_id>', methods=['DELETE'])
@operator_required
def delete_device(device_id):
    """Delete a device"""
    result = _get_db().delete_device(device_id)
    if result.get('success'):
        try:
            path = _device_note_path(device_id)
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            current_app.logger.exception('Failed to delete note for device %s', device_id)
    _get_socketio().emit('device_deleted', {'id': device_id}, namespace='/')
    log_audit('delete', 'device', 'device', device_id)
    return jsonify(result)


@devices_bp.route('/api/devices/<int:device_id>/children', methods=['GET'])
def get_device_children(device_id):
    """Get child devices (devices that depend on this device)"""
    db = _get_db()
    children = db.get_child_devices(device_id)
    downstream_count = db.count_downstream_devices(device_id)
    return jsonify({
        'device_id': device_id,
        'children': children,
        'total_downstream': downstream_count
    })


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
        device.get('snmp_version', '2c'),
        snmp_v3_username=device.get('snmp_v3_username'),
        snmp_v3_auth_protocol=device.get('snmp_v3_auth_protocol', 'SHA'),
        snmp_v3_auth_password=device.get('snmp_v3_auth_password'),
        snmp_v3_priv_protocol=device.get('snmp_v3_priv_protocol', 'AES128'),
        snmp_v3_priv_password=device.get('snmp_v3_priv_password')
    )
    
    return jsonify({
        'device_id': device_id,
        'device_name': device['name'],
        'interfaces': interfaces
    })

@devices_bp.route('/api/devices/<int:device_id>/performance', methods=['GET'])
def get_device_performance(device_id):
    """Get performance metrics history for a device"""
    hours = request.args.get('hours', 24, type=int)
    db = _get_db()
    device = db.get_device(device_id)
    if not device:
        return jsonify({'error': 'Device not found'}), 404
    
    cpu_history = db.get_system_metrics_history(device_id, 'cpu', hours)
    ram_history = db.get_system_metrics_history(device_id, 'ram', hours)
    disk_history = db.get_system_metrics_history(device_id, 'disk', hours)
    swap_history = db.get_system_metrics_history(device_id, 'swap', hours)
    inode_history = db.get_system_metrics_history(device_id, 'inode', hours)
    load1_history = db.get_system_metrics_history(device_id, 'load1', hours)
    load5_history = db.get_system_metrics_history(device_id, 'load5', hours)
    load15_history = db.get_system_metrics_history(device_id, 'load15', hours)
    network_in_history = db.get_system_metrics_history(device_id, 'network_in', hours)
    network_out_history = db.get_system_metrics_history(device_id, 'network_out', hours)
    disk_partition_history = db.get_disk_partition_history(device_id, hours)

    def _json_field(name, fallback):
        try:
            raw = device.get(name)
            return json.loads(raw) if raw else fallback
        except Exception:
            return fallback
    
    return jsonify({
        'device_id': device_id,
        'cpu': cpu_history,
        'ram': ram_history,
        'disk': disk_history,
        'swap': swap_history,
        'inode': inode_history,
        'load1': load1_history,
        'load5': load5_history,
        'load15': load15_history,
        'network_in': network_in_history,
        'network_out': network_out_history,
        'disk_partitions': disk_partition_history,
        'current': {
            'cpu': device.get('cpu_usage'),
            'ram': device.get('ram_usage'),
            'disk': device.get('disk_usage'),
            'swap': device.get('swap_usage'),
            'inode': device.get('inode_usage'),
            'load1': device.get('load1'),
            'load5': device.get('load5'),
            'load15': device.get('load15'),
            'pending_reboot': bool(device.get('pending_reboot')),
            'uptime_text': device.get('server_uptime_text'),
            'uptime_seconds': device.get('server_uptime_seconds'),
            'last_boot_time': device.get('last_boot_time'),
            'network_in_bps': device.get('network_in_bps'),
            'network_out_bps': device.get('network_out_bps'),
            'disk_details': _json_field('disk_details_json', []),
            'service_status': _json_field('service_status_json', []),
            'service_summary': _json_field('service_summary_json', {}),
        },
        'thresholds': {
            'cpu': device.get('cpu_threshold', 85),
            'ram': device.get('ram_threshold', 90),
            'disk': device.get('disk_threshold', 90),
            'swap': device.get('swap_threshold', 80),
            'duration_minutes': device.get('threshold_duration_minutes', 5),
        }
    })


@devices_bp.route('/api/server-health', methods=['GET'])
def get_server_health():
    """Get server-focused health summary for SSH/WinRM monitored devices."""
    devices = _get_db().get_all_devices()

    def _json_field(device, name, fallback):
        try:
            raw = device.get(name)
            return json.loads(raw) if raw else fallback
        except Exception:
            return fallback

    servers = []
    service_down = []
    pending_reboot = []
    disk_rows = []

    for device in devices:
        if device.get('monitor_type') not in ('ssh', 'winrm', 'wmi'):
            continue
        service_status = _json_field(device, 'service_status_json', [])
        service_summary = _json_field(device, 'service_summary_json', {})
        disk_details = _json_field(device, 'disk_details_json', [])
        server = {
            'id': device.get('id'),
            'name': device.get('name'),
            'ip_address': device.get('ip_address'),
            'monitor_type': device.get('monitor_type'),
            'status': device.get('status'),
            'cpu': device.get('cpu_usage'),
            'ram': device.get('ram_usage'),
            'disk': device.get('disk_usage'),
            'swap': device.get('swap_usage'),
            'inode': device.get('inode_usage'),
            'load1': device.get('load1'),
            'load5': device.get('load5'),
            'load15': device.get('load15'),
            'pending_reboot': bool(device.get('pending_reboot')),
            'uptime_text': device.get('server_uptime_text'),
            'last_boot_time': device.get('last_boot_time'),
            'service_status': service_status,
            'service_summary': service_summary,
            'disk_details': disk_details,
        }
        servers.append(server)
        if server['pending_reboot']:
            pending_reboot.append(server)
        for service in service_status:
            if not service.get('ok'):
                service_down.append({
                    'device_id': server['id'],
                    'device_name': server['name'],
                    'service': service.get('name'),
                    'status': service.get('status'),
                })
        for disk in disk_details:
            disk_rows.append({
                'device_id': server['id'],
                'device_name': server['name'],
                'mount': disk.get('mount') or disk.get('name'),
                'use_percent': disk.get('use_percent'),
                'size_kb': disk.get('size_kb'),
            })

    def _top(items, key, limit=10):
        def value(item):
            try:
                return float(item.get(key))
            except Exception:
                return -1
        return sorted([item for item in items if item.get(key) is not None], key=value, reverse=True)[:limit]

    return jsonify({
        'success': True,
        'summary': {
            'total_servers': len(servers),
            'up': sum(1 for s in servers if s.get('status') == 'up'),
            'slow': sum(1 for s in servers if s.get('status') == 'slow'),
            'down': sum(1 for s in servers if s.get('status') == 'down'),
            'pending_reboot': len(pending_reboot),
            'service_down': len(service_down),
        },
        'servers': servers,
        'top_cpu': _top(servers, 'cpu'),
        'top_ram': _top(servers, 'ram'),
        'top_disk': _top(disk_rows, 'use_percent'),
        'service_down': service_down,
        'pending_reboot': pending_reboot,
    })


@devices_bp.route('/api/server-health/export.csv', methods=['GET'])
def export_server_health_csv():
    """Export latest server metrics as CSV."""
    db = _get_db()
    devices = db.get_all_devices()

    def _json_field(device, name, fallback):
        try:
            raw = device.get(name)
            return json.loads(raw) if raw else fallback
        except Exception:
            return fallback

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'id', 'name', 'ip_address', 'monitor_type', 'status',
        'cpu_usage', 'ram_usage', 'disk_usage', 'swap_usage', 'inode_usage',
        'load1', 'load5', 'load15', 'pending_reboot',
        'uptime', 'last_boot_time', 'services', 'disks'
    ])

    for device in devices:
        if device.get('monitor_type') not in ('ssh', 'winrm', 'wmi'):
            continue
        services = _json_field(device, 'service_status_json', [])
        disks = _json_field(device, 'disk_details_json', [])
        service_text = '; '.join(f"{s.get('name')}={s.get('status')}" for s in services)
        disk_text = '; '.join(f"{d.get('mount') or d.get('name')}={d.get('use_percent')}%" for d in disks)
        writer.writerow([
            device.get('id'), device.get('name'), device.get('ip_address'), device.get('monitor_type'), device.get('status'),
            device.get('cpu_usage'), device.get('ram_usage'), device.get('disk_usage'), device.get('swap_usage'), device.get('inode_usage'),
            device.get('load1'), device.get('load5'), device.get('load15'), device.get('pending_reboot'),
            device.get('server_uptime_text'), device.get('last_boot_time'), service_text, disk_text
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=server_health.csv'}
    )


@devices_bp.route('/api/server-health/export.pdf', methods=['GET'])
def export_server_health_pdf():
    """Download the latest server-health snapshot as a PDF file."""
    lines = ['SERVER HEALTH REPORT', datetime.now().strftime('Generated: %Y-%m-%d %H:%M:%S'), '']
    servers = [
        device for device in _get_db().get_all_devices()
        if device.get('monitor_type') in ('ssh', 'winrm', 'wmi')
    ]
    lines.append(f'Total servers: {len(servers)}')
    lines.append(f'Down: {sum(1 for device in servers if device.get("status") == "down")}')
    lines.extend(['', 'SERVER DETAILS'])
    for device in servers:
        lines.append(
            f'{device.get("name", "Unknown")} | {device.get("ip_address", "")} | '
            f'{str(device.get("status", "unknown")).upper()} | CPU {device.get("cpu_usage", "-")}% | '
            f'RAM {device.get("ram_usage", "-")}% | Disk {device.get("disk_usage", "-")}%'
        )
        try:
            disks = json.loads(device.get('disk_details_json') or '[]')
        except (TypeError, ValueError):
            disks = []
        for disk in disks:
            lines.append(f'  Disk {disk.get("mount") or disk.get("name")}: {disk.get("use_percent", "-")}%')
        try:
            services = json.loads(device.get('service_status_json') or '[]')
        except (TypeError, ValueError):
            services = []
        stopped = [service for service in services if not service.get('ok')]
        for service in stopped:
            lines.append(f'  SERVICE DOWN: {service.get("name")} ({service.get("status", "unknown")})')
        if device.get('pending_reboot'):
            lines.append('  PENDING REBOOT')
    return Response(
        _simple_pdf(lines), mimetype='application/pdf',
        headers={'Content-Disposition': 'attachment; filename=server_health.pdf'},
    )


@devices_bp.route('/api/server-thresholds/apply', methods=['POST'])
@operator_required
def apply_server_thresholds_to_group():
    """Bulk apply server thresholds by location or device type."""
    data = request.get_json(silent=True) or {}
    group_type = data.get('group_type')
    group_value = str(data.get('group_value') or '').strip()
    if group_type not in ('location', 'device_type') or not group_value:
        return jsonify({'success': False, 'error': 'Group type and value are required'}), 400
    try:
        thresholds = {
            'cpu': float(data.get('cpu', 85)), 'ram': float(data.get('ram', 90)),
            'disk': float(data.get('disk', 90)), 'swap': float(data.get('swap', 80)),
            'duration_minutes': max(1, int(data.get('duration_minutes', 5))),
        }
        if any(value < 0 or value > 100 for key, value in thresholds.items() if key != 'duration_minutes'):
            raise ValueError('Thresholds must be between 0 and 100')
    except (TypeError, ValueError) as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    result = _get_db().apply_server_thresholds_to_group(group_type, group_value, thresholds)
    code = 200 if result.get('success') else 500
    if result.get('success'):
        log_audit('update', 'device', details={
            'action': 'apply_group_thresholds', 'group_type': group_type,
            'group_value': group_value, 'updated': result.get('updated'), **thresholds,
        })
    return jsonify(result), code

@devices_bp.route('/api/devices/<int:device_id>/ports', methods=['GET'])
def get_device_ports(device_id):
    """Fetch active TCP/UDP ports for a device (SSH/WinRM only)"""
    device = _get_db().get_device(device_id)
    if not device:
        return jsonify({'error': 'Device not found', 'success': False}), 404
        
    monitor_type = device.get('monitor_type')
    monitor = _get_monitor()
    
    if monitor_type == 'ssh':
        result = monitor.get_ssh_ports(
            device.get('ip_address'),
            device.get('ssh_username'),
            device.get('ssh_password'),
            device.get('ssh_port', 22)
        )
        return jsonify(result)
        
    elif monitor_type == 'winrm':
        result = monitor.get_winrm_ports(
            device.get('ip_address'),
            device.get('wmi_username'),
            device.get('wmi_password')
        )
        return jsonify(result)
        
    else:
        return jsonify({
            'success': False, 
            'error': f'Active ports viewer is not supported for monitor type: {monitor_type}'
        })


# ============================================================================
# Custom SNMP OID Routes
# ============================================================================

@devices_bp.route('/api/snmp/<int:device_id>/custom-oids', methods=['GET'])
def get_custom_oids(device_id):
    """Get all custom OIDs for a device"""
    db = _get_db()
    device = db.get_device(device_id)
    if not device:
        return jsonify({'error': 'Device not found'}), 404
    oids = db.get_custom_oids(device_id)
    return jsonify({'device_id': device_id, 'oids': oids})


@devices_bp.route('/api/snmp/<int:device_id>/custom-oids', methods=['POST'])
@operator_required
def add_custom_oid(device_id):
    """Add a custom OID for a device"""
    data = request.json
    if not data.get('oid') or not data.get('name'):
        return jsonify({'success': False, 'error': 'OID and Name are required'}), 400
    
    db = _get_db()
    device = db.get_device(device_id)
    if not device:
        return jsonify({'success': False, 'error': 'Device not found'}), 404
    
    result = db.add_custom_oid(
        device_id=device_id,
        oid=data['oid'].strip(),
        name=data['name'].strip(),
        unit=data.get('unit', '').strip()
    )
    if result['success']:
        return jsonify(result), 201
    return jsonify(result), 400


@devices_bp.route('/api/snmp/custom-oids/<int:oid_id>', methods=['DELETE'])
@operator_required
def delete_custom_oid(oid_id):
    """Delete a custom OID"""
    result = _get_db().delete_custom_oid(oid_id)
    return jsonify(result)


@devices_bp.route('/api/snmp/<int:device_id>/custom-oids/query', methods=['POST'])
@operator_required
def query_custom_oids(device_id):
    """Query all custom OIDs for a device (live SNMP query)"""
    db = _get_db()
    device = db.get_device(device_id)
    if not device:
        return jsonify({'error': 'Device not found'}), 404
    
    oids = db.get_custom_oids(device_id)
    if not oids:
        return jsonify({'results': [], 'message': 'No custom OIDs configured'})
    
    oid_list = [{'id': o['id'], 'oid': o['oid'], 'name': o['name'],
                 'unit': o.get('unit', '')} for o in oids]
    
    monitor = _get_monitor()
    results = monitor.query_custom_oids(
        device['ip_address'],
        device.get('snmp_community', 'public'),
        device.get('snmp_port', 161),
        device.get('snmp_version', '2c'),
        snmp_v3_username=device.get('snmp_v3_username'),
        snmp_v3_auth_protocol=device.get('snmp_v3_auth_protocol', 'SHA'),
        snmp_v3_auth_password=device.get('snmp_v3_auth_password'),
        snmp_v3_priv_protocol=device.get('snmp_v3_priv_protocol', 'AES128'),
        snmp_v3_priv_password=device.get('snmp_v3_priv_password'),
        oid_list=oid_list
    )
    
    # Update last values in DB
    for r in results:
        db.update_custom_oid_value(r['id'], r.get('value', ''))
    
    return jsonify({'device_id': device_id, 'results': results})


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
    """Get response time trends by device type or specific device"""
    minutes = request.args.get('minutes', 180, type=int)
    device_id = request.args.get('device_id', type=int)
    trends = _get_db().get_device_type_trends(minutes, device_id=device_id)
    return jsonify(trends)


@devices_bp.route('/api/anomalies', methods=['GET'])
def get_anomalies():
    """Get live anomaly detection results."""
    recent_minutes = request.args.get('recent_minutes', 30, type=int)
    baseline_hours = request.args.get('baseline_hours', 24, type=int)
    min_points = request.args.get('min_points', 5, type=int)
    anomalies = _get_db().detect_anomalies(
        recent_minutes=recent_minutes,
        baseline_hours=baseline_hours,
        min_points=min_points,
    )
    return jsonify(anomalies)


@devices_bp.route('/api/anomalies/materialized', methods=['GET'])
def get_materialized_anomalies():
    """Get persistent anomaly snapshots."""
    active_only = request.args.get('active_only', 'true').lower() != 'false'
    limit = request.args.get('limit', 100, type=int)
    anomalies = _get_db().get_anomaly_snapshots(active_only=active_only, limit=limit)
    return jsonify(anomalies)


@devices_bp.route('/api/anomalies/materialize', methods=['POST'])
@operator_required
def materialize_anomalies_now():
    """Run anomaly materialization on demand."""
    data = request.json or {}
    result = _get_db().sync_anomaly_snapshots(
        recent_minutes=data.get('recent_minutes', 30),
        baseline_hours=data.get('baseline_hours', 24),
        min_points=data.get('min_points', 5),
    )
    code = 200 if result.get('success') else 500
    return jsonify(result), code


@devices_bp.route('/api/anomalies/<path:anomaly_key>/status', methods=['POST'])
@operator_required
def update_anomaly_status(anomaly_key):
    """Update workflow status for an anomaly."""
    data = request.json or {}
    status = (data.get('status') or '').strip().lower()
    if status not in {'open', 'acknowledged', 'investigating', 'resolved'}:
        return jsonify({'success': False, 'error': 'Invalid status'}), 400

    result = _get_db().update_anomaly_state(
        anomaly_key=anomaly_key,
        status=status,
        user_id=session.get('user_id'),
        username=session.get('username'),
        note=(data.get('note') or '').strip() or None,
    )
    code = 200 if result.get('success') else 500
    return jsonify(result), code


@devices_bp.route('/api/anomalies/<path:anomaly_key>/owner', methods=['POST'])
@operator_required
def update_anomaly_owner(anomaly_key):
    """Assign or clear owner for an anomaly."""
    data = request.json or {}
    owner_user_id = data.get('owner_user_id')
    owner_username = None

    if owner_user_id not in (None, ''):
        try:
            owner_user_id = int(owner_user_id)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'Invalid owner_user_id'}), 400

        user = _get_db().get_user_by_id(owner_user_id)
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        owner_username = user.get('display_name') or user.get('username')
    else:
        owner_user_id = None

    result = _get_db().update_anomaly_owner(
        anomaly_key=anomaly_key,
        owner_user_id=owner_user_id,
        owner_username=owner_username,
        actor_user_id=session.get('user_id'),
        actor_username=session.get('username'),
        note=(data.get('note') or '').strip() or None,
    )
    code = 200 if result.get('success') else 500
    return jsonify(result), code


@devices_bp.route('/api/anomalies/<path:anomaly_key>/link-incident', methods=['POST'])
@operator_required
def link_anomaly_incident(anomaly_key):
    """Persistently link an anomaly to a materialized incident."""
    data = request.json or {}
    incident_id = (data.get('incident_id') or '').strip()
    if not incident_id:
        return jsonify({'success': False, 'error': 'incident_id is required'}), 400

    result = _get_db().link_anomaly_to_incident(
        anomaly_key=anomaly_key,
        incident_id=incident_id,
        actor_user_id=session.get('user_id'),
        actor_username=session.get('username'),
        note=(data.get('note') or '').strip() or None,
    )
    code = 200 if result.get('success') else 400
    return jsonify(result), code


@devices_bp.route('/api/anomalies/<path:anomaly_key>/link-incident', methods=['DELETE'])
@operator_required
def unlink_anomaly_incident(anomaly_key):
    """Remove a persisted anomaly-to-incident link."""
    data = request.json or {}
    result = _get_db().unlink_anomaly_from_incident(
        anomaly_key=anomaly_key,
        actor_user_id=session.get('user_id'),
        actor_username=session.get('username'),
        note=(data.get('note') or '').strip() or 'Link removed',
    )
    code = 200 if result.get('success') else 400
    return jsonify(result), code


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
        'snmp_v3_username', 'snmp_v3_auth_protocol', 'snmp_v3_priv_protocol',
        'tcp_port', 'dns_query_domain', 'expected_status_code'
    ]
    
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    
    for device in devices:
        row = {k: device.get(k, '') for k in fieldnames}
        writer.writerow(row)
    
    output.seek(0)
    log_audit('export', 'device', details={'format': 'csv', 'count': len(devices)})
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
            
            # Handle is_enabled if present in CSV
            is_enabled_raw = row.get('is_enabled', '').strip().lower()
            if is_enabled_raw == '':
                is_enabled = True # Default
            else:
                is_enabled = is_enabled_raw in ('true', '1', 'yes', 'on', 'enabled')

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
                expected_status_code=int(row.get('expected_status_code') or 200),
                is_enabled=is_enabled
            )
            
            if result['success']:
                results['imported'] += 1
            else:
                results['failed'] += 1
                results['errors'].append(f"Row {i}: {result.get('error', 'Unknown error')}")
        
        log_audit('import', 'device', details={'imported': results['imported'], 'failed': results['failed']})
        return jsonify(results)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@devices_bp.route('/api/devices/<int:device_id>/toggle', methods=['POST'])
@login_required
@operator_required
def toggle_device(device_id):
    """Toggle device monitoring status"""
    db = _get_db()
    result = db.toggle_device_monitoring(device_id)
    
    if result['success']:
        action = 'enabled' if result['is_enabled'] else 'disabled'
        log_audit(
            session.get('username', 'system'),
            'DEVICE_TOGGLE',
            f'Device "{result["name"]}" monitoring {action}',
            'devices',
            device_id
        )
        
    return jsonify(result), 200 if result['success'] else 400
