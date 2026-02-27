"""
Routes package - Flask Blueprints for modular architecture
"""
from .auth import auth_bp, login_required, admin_required, operator_required
from .pages import pages_bp
from .devices import devices_bp
from .topology import topology_bp
from .dashboards import dashboards_bp
from .discovery import discovery_bp
from .alerts import alerts_bp
from .users import users_bp
from .sla import sla_bp
from .maintenance import maintenance_bp
from .discovery import discovery_bp

ALL_BLUEPRINTS = [
    auth_bp,
    pages_bp,
    devices_bp,
    topology_bp,
    dashboards_bp,
    alerts_bp,
    users_bp,
    sla_bp,
    maintenance_bp,
    discovery_bp,
]
