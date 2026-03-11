"""
SLA and historical data API routes
"""
from flask import Blueprint, jsonify, request, current_app

sla_bp = Blueprint('sla', __name__)


def _get_db():
    return current_app.config['DB']


@sla_bp.route('/api/devices/<int:device_id>/history', methods=['GET'])
def get_device_history(device_id):
    """Get status history for a device"""
    limit = request.args.get('limit', 150, type=int)
    minutes = request.args.get('minutes', type=int)
    sample_count = request.args.get('sample', type=int)
    history = _get_db().get_device_history(device_id, limit, minutes, sample_count)
    
    # Normalize datetime objects to ISO strings to prevent Flask from appending 'GMT' and shifting timezones
    from datetime import datetime
    for item in history:
        if isinstance(item.get('checked_at'), datetime):
            item['checked_at'] = item['checked_at'].isoformat()
            
    return jsonify(history)


@sla_bp.route('/api/history', methods=['GET'])
def get_historical_data():
    """Get historical data with optional filters"""
    db = _get_db()
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    device_id = request.args.get('device_id', type=int)
    device_ids = request.args.get('device_ids')
    device_type = request.args.get('device_type')
    
    if device_ids:
        device_id_list = [int(x.strip()) for x in device_ids.split(',') if x.strip().isdigit()]
        history = db.get_historical_data_multi(start_date, end_date, device_id_list)
    else:
        history = db.get_historical_data(start_date, end_date, device_id, device_type)
    return jsonify(history)


@sla_bp.route('/api/history/stats', methods=['GET'])
def get_historical_stats():
    """Get aggregated statistics for a time period"""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    stats = _get_db().get_aggregated_stats(start_date, end_date)
    return jsonify(stats)


@sla_bp.route('/api/sla', methods=['GET'])
def get_sla_data():
    """Get SLA data for all devices"""
    db = _get_db()
    days = request.args.get('days', 30, type=int)
    sla_target = request.args.get('target', 99.9, type=float)
    
    sla_data = db.get_all_devices_sla(days=days, sla_target=sla_target)
    
    devices_with_data = [d for d in sla_data if d['uptime_percent'] is not None]
    summary = {
        'total_devices': len(sla_data),
        'devices_with_data': len(devices_with_data),
        'sla_met': len([d for d in devices_with_data if d['sla_status'] == 'met']),
        'sla_warning': len([d for d in devices_with_data if d['sla_status'] == 'warning']),
        'sla_breached': len([d for d in devices_with_data if d['sla_status'] == 'breached']),
        'average_uptime': round(sum(d['uptime_percent'] for d in devices_with_data) / len(devices_with_data), 4) if devices_with_data else None,
        'days': days,
        'sla_target': sla_target
    }
    
    return jsonify({'summary': summary, 'devices': sla_data})


@sla_bp.route('/api/sla/<int:device_id>', methods=['GET'])
def get_device_sla(device_id):
    """Get SLA data for a specific device"""
    db = _get_db()
    days = request.args.get('days', 30, type=int)
    stats = db.get_device_uptime_stats(device_id, days=days)
    device = db.get_device(device_id)
    
    if not device:
        return jsonify({'error': 'Device not found'}), 404
    
    return jsonify({'device': device, **stats})


@sla_bp.route('/api/sla/export/csv', methods=['GET'])
def export_sla_csv():
    """Export SLA data as a CSV file"""
    import csv
    import io
    from flask import Response
    from datetime import datetime
    
    db = _get_db()
    days = request.args.get('days', 30, type=int)
    sla_target = request.args.get('target', 99.9, type=float)
    
    sla_data = db.get_all_devices_sla(days=days, sla_target=sla_target)
    
    # Create in-memory file
    si = io.StringIO()
    cw = csv.writer(si)
    
    # Write header
    cw.writerow([
        'Device Name', 
        'IP Address', 
        'Device Type', 
        'Location', 
        'Current Status', 
        f'Uptime % ({days} Days)', 
        'SLA Target %', 
        'SLA Status', 
        'Total Checks', 
        'Avg Response Time (ms)'
    ])
    
    # Write data
    for d in sla_data:
        uptime = d['uptime_percent']
        uptime_str = f"{uptime:.4f}" if uptime is not None else "N/A"
        avg_resp = d['avg_response_time']
        avg_resp_str = str(avg_resp) if avg_resp is not None else "N/A"
        
        cw.writerow([
            d['name'],
            d['ip_address'],
            d['device_type'] or '-',
            d['location'] or '-',
            d['current_status'] or 'unknown',
            uptime_str,
            d['sla_target'],
            d['sla_status'],
            d['total_checks'],
            avg_resp_str
        ])
    
    output = si.getvalue()
    
    # Send CSV response
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=sla_report_{days}days_{datetime.now().strftime('%Y%m%d')}.csv"}
    )

