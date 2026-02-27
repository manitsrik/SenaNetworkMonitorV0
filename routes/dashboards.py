"""
Dashboard management API routes
"""
from flask import Blueprint, jsonify, request, session, current_app
import json
from .auth import login_required, admin_required

dashboards_bp = Blueprint('dashboards', __name__)


def _get_db():
    return current_app.config['DB']


@dashboards_bp.route('/api/dashboards', methods=['GET'])
@login_required
def get_dashboards():
    """Get all dashboards"""
    db = _get_db()
    user_id = session.get('user_id')
    dashboards = db.get_dashboards(user_id)
    
    for d in dashboards:
        try:
            if d['layout_config']:
                d['layout_config'] = json.loads(d['layout_config'])
        except:
            d['layout_config'] = []
            
    return jsonify(dashboards)


@dashboards_bp.route('/api/dashboards', methods=['POST'])
@admin_required
def create_dashboard():
    """Create a new dashboard"""
    data = request.json
    
    if not data.get('name'):
        return jsonify({'success': False, 'error': 'Name is required'}), 400
        
    layout_config = data.get('layout_config')
    if isinstance(layout_config, (dict, list)):
        layout_config = json.dumps(layout_config)
    
    result = _get_db().create_dashboard(
        name=data['name'],
        layout_config=layout_config,
        description=data.get('description'),
        created_by=session.get('user_id'),
        is_public=data.get('is_public', 0)
    )
    
    return jsonify(result)


@dashboards_bp.route('/api/dashboards/<int:dashboard_id>', methods=['GET'])
@login_required
def get_dashboard(dashboard_id):
    """Get a specific dashboard"""
    db = _get_db()
    dashboard = db.get_dashboard(dashboard_id)
    if not dashboard:
        return jsonify({'error': 'Dashboard not found'}), 404
        
    if not dashboard['is_public'] and dashboard['created_by'] != session.get('user_id'):
        return jsonify({'error': 'Access denied'}), 403
        
    try:
        if dashboard['layout_config']:
            dashboard['layout_config'] = json.loads(dashboard['layout_config'])
    except:
        dashboard['layout_config'] = []
        
    return jsonify(dashboard)


@dashboards_bp.route('/api/dashboards/<int:dashboard_id>', methods=['PUT'])
@admin_required
def update_dashboard(dashboard_id):
    """Update a dashboard"""
    data = request.json
    db = _get_db()
    
    dashboard = db.get_dashboard(dashboard_id)
    if not dashboard:
        return jsonify({'error': 'Dashboard not found'}), 404

    layout_config = data.get('layout_config')
    if layout_config is not None and isinstance(layout_config, (dict, list)):
        layout_config = json.dumps(layout_config)
        
    result = db.update_dashboard(
        dashboard_id,
        name=data.get('name'),
        layout_config=layout_config,
        description=data.get('description'),
        is_public=data.get('is_public')
    )
    
    return jsonify(result)


@dashboards_bp.route('/api/dashboards/<int:dashboard_id>', methods=['DELETE'])
@admin_required
def delete_dashboard(dashboard_id):
    """Delete a dashboard"""
    result = _get_db().delete_dashboard(dashboard_id)
    return jsonify(result)
