"""
Page routes — HTML rendering
"""
from flask import Blueprint, render_template, request
from .auth import login_required, admin_required

pages_bp = Blueprint('pages', __name__)


def _get_db():
    from flask import current_app
    return current_app.config['DB']


@pages_bp.route('/')
@login_required
def index():
    """Redirect to the first available dashboard (default landing page)"""
    db = _get_db()
    from flask import session, redirect, url_for
    user_id = session.get('user_id')
    dashboards = db.get_dashboards(user_id)
    
    if dashboards:
        # Dashboards are already sorted by display_order in db.get_dashboards()
        first_dashboard_id = dashboards[0]['id']
        return redirect(url_for('pages.view_dashboard', dashboard_id=first_dashboard_id))
    
    # Fallback to dashboards list if none exist
    return redirect(url_for('pages.dashboards_list'))


@pages_bp.route('/topology')
@login_required
def topology():
    """Topology page"""
    return render_template('topology.html')


@pages_bp.route('/devices')
@login_required
def devices():
    """Device management page"""
    return render_template('devices.html')


@pages_bp.route('/history')
@login_required
def history():
    """Historical data page"""
    return render_template('history.html')


@pages_bp.route('/settings')
@login_required
def settings():
    """Alert settings page"""
    return render_template('settings.html')


@pages_bp.route('/users')
@admin_required
def users():
    """User management page (admin only)"""
    return render_template('users.html')


@pages_bp.route('/sla')
def sla_page():
    """SLA Dashboard page"""
    return render_template('sla.html')


@pages_bp.route('/dashboards')
@login_required
def dashboards_list():
    """List all dashboards page"""
    return render_template('dashboards.html')


@pages_bp.route('/dashboard/new')
@admin_required
def new_dashboard():
    """Dashboard creator page"""
    return render_template('dashboard_builder.html')


@pages_bp.route('/dashboard/<int:dashboard_id>/edit')
@admin_required
def edit_dashboard(dashboard_id):
    """Edit dashboard page"""
    return render_template('dashboard_builder.html', dashboard_id=dashboard_id)


@pages_bp.route('/dashboard/<int:dashboard_id>')
@login_required
def view_dashboard(dashboard_id):
    """View specific dashboard"""
    return render_template('dashboard_view.html', dashboard_id=dashboard_id)


@pages_bp.route('/traps')
@login_required
def traps_page():
    """SNMP Traps page"""
    return render_template('traps.html')


@pages_bp.route('/syslog')
@login_required
def syslog_page():
    """Syslog Viewer page"""
    return render_template('syslog.html')


@pages_bp.route('/sla/export/print')
def print_sla():
    """Printable SLA Report page"""
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
    
    # Sort data for print layout (by status, then uptime)
    sla_data.sort(key=lambda x: (
        x['uptime_percent'] is None, 
        x['uptime_percent'] if x['uptime_percent'] is not None else 0
    ))
    
    return render_template('reports/sla_print.html', summary=summary, devices=sla_data)


@pages_bp.route('/audit-log')
@admin_required
def audit_log_page():
    """Audit Log page (admin only)"""
    return render_template('audit_log.html')


@pages_bp.route('/set_lang/<lang>')
def set_lang(lang):
    """Switch language (th or en)"""
    from flask import session, redirect, request, url_for
    if lang in ['en', 'th']:
        session['lang'] = lang
    return redirect(request.referrer or url_for('pages.index'))


