"""
Page routes — HTML rendering
"""
from flask import Blueprint, render_template
from .auth import login_required, admin_required

pages_bp = Blueprint('pages', __name__)


def _get_db():
    from flask import current_app
    return current_app.config['DB']


@pages_bp.route('/')
@login_required
def index():
    """Dashboard page"""
    db = _get_db()
    main_dashboard = db.get_dashboard(1)
    return render_template('index.html', dashboard=main_dashboard)


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
