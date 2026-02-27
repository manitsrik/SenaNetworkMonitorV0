"""
Topology and Sub-Topology API routes
"""
from flask import Blueprint, jsonify, request, session, render_template, current_app
import os
import uuid
from .auth import login_required, operator_required

topology_bp = Blueprint('topology', __name__)


def _get_db():
    return current_app.config['DB']

def _get_socketio():
    return current_app.config['SOCKETIO']


@topology_bp.route('/api/topology', methods=['GET'])
def get_topology():
    """Get topology configuration"""
    db = _get_db()
    devices = db.get_all_devices()
    connections = db.get_topology()
    return jsonify({'devices': devices, 'connections': connections})


@topology_bp.route('/api/topology/connection', methods=['POST'])
@operator_required
def add_topology_connection():
    """Add a topology connection"""
    data = request.json
    
    if not data.get('device_id') or not data.get('connected_to'):
        return jsonify({'success': False, 'error': 'device_id and connected_to are required'}), 400
    
    result = _get_db().add_topology_connection(
        device_id=data['device_id'],
        connected_to=data['connected_to'],
        view_type=data.get('view_type', 'standard')
    )
    
    if result['success']:
        _get_socketio().emit('topology_updated', {
            'action': 'add',
            'connection': {
                'id': result['id'],
                'device_id': data['device_id'],
                'connected_to': data['connected_to'],
                'view_type': data.get('view_type', 'standard')
            }
        }, namespace='/')
        return jsonify(result), 201
    else:
        return jsonify(result), 400


@topology_bp.route('/api/topology/connection/<int:connection_id>', methods=['DELETE'])
@operator_required
def delete_topology_connection(connection_id):
    """Delete a topology connection"""
    result = _get_db().delete_topology_connection(connection_id=connection_id)
    
    if result['success']:
        _get_socketio().emit('topology_updated', {
            'action': 'delete',
            'connection_id': connection_id
        }, namespace='/')
    
    return jsonify(result)


# ============================================================================
# Sub-Topology Routes
# ============================================================================

@topology_bp.route('/sub-topology/new')
@operator_required
def new_sub_topology():
    """Sub-topology builder page (create)"""
    return render_template('sub_topology_builder.html')


@topology_bp.route('/sub-topology/<int:sub_topo_id>/edit')
@operator_required
def edit_sub_topology(sub_topo_id):
    """Sub-topology builder page (edit)"""
    return render_template('sub_topology_builder.html', sub_topo_id=sub_topo_id)


@topology_bp.route('/sub-topology/<int:sub_topo_id>')
@login_required
def view_sub_topology(sub_topo_id):
    """View sub-topology"""
    return render_template('sub_topology_view.html', sub_topo_id=sub_topo_id)


@topology_bp.route('/api/sub-topologies', methods=['GET'])
@login_required
def get_sub_topologies():
    """Get all sub-topologies"""
    sub_topos = _get_db().get_all_sub_topologies()
    return jsonify(sub_topos)


@topology_bp.route('/api/sub-topologies', methods=['POST'])
@operator_required
def create_sub_topology():
    """Create a new sub-topology"""
    data = request.json
    
    if not data.get('name'):
        return jsonify({'success': False, 'error': 'Name is required'}), 400
    
    db = _get_db()
    result = db.create_sub_topology(
        name=data['name'],
        description=data.get('description'),
        created_by=session.get('user_id'),
        background_image=data.get('background_image'),
        background_zoom=data.get('background_zoom', 100),
        node_positions=data.get('node_positions'),
        background_opacity=data.get('background_opacity', 100)
    )
    
    if result['success']:
        sub_topo_id = result['id']
        device_ids = data.get('device_ids', [])
        connections = data.get('connections', [])
        db.update_sub_topology(sub_topo_id, device_ids=device_ids, connections=connections)
        return jsonify(result), 201
    
    return jsonify(result), 400


@topology_bp.route('/api/sub-topologies/<int:sub_topo_id>', methods=['GET'])
@login_required
def get_sub_topology_detail(sub_topo_id):
    """Get a sub-topology with devices and connections"""
    sub_topo = _get_db().get_sub_topology(sub_topo_id)
    if not sub_topo:
        return jsonify({'error': 'Sub-topology not found'}), 404
    return jsonify(sub_topo)


@topology_bp.route('/api/sub-topologies/<int:sub_topo_id>', methods=['PUT'])
@operator_required
def update_sub_topology_route(sub_topo_id):
    """Update a sub-topology"""
    data = request.json
    db = _get_db()
    
    sub_topo = db.get_sub_topology(sub_topo_id)
    if not sub_topo:
        return jsonify({'error': 'Sub-topology not found'}), 404
    
    result = db.update_sub_topology(
        sub_topo_id,
        name=data.get('name'),
        description=data.get('description'),
        device_ids=data.get('device_ids'),
        connections=data.get('connections'),
        background_image=data.get('background_image'),
        background_zoom=data.get('background_zoom'),
        node_positions=data.get('node_positions'),
        background_opacity=data.get('background_opacity')
    )
    
    return jsonify(result)


@topology_bp.route('/api/sub-topologies/<int:sub_topo_id>', methods=['DELETE'])
@operator_required
def delete_sub_topology_route(sub_topo_id):
    """Delete a sub-topology"""
    result = _get_db().delete_sub_topology(sub_topo_id)
    return jsonify(result)


@topology_bp.route('/api/sub-topologies/upload-bg', methods=['POST'])
@operator_required
def upload_sub_topology_bg():
    """Upload a background image for sub-topology"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400
    
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in allowed_extensions:
        return jsonify({'success': False, 'error': f'Invalid file type. Allowed: {allowed_extensions}'}), 400
    
    bg_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'backgrounds')
    os.makedirs(bg_dir, exist_ok=True)
    
    filename = f'bg_{uuid.uuid4().hex[:8]}.{ext}'
    filepath = os.path.join(bg_dir, filename)
    file.save(filepath)
    
    url_path = f'/static/uploads/backgrounds/{filename}'
    return jsonify({'success': True, 'url': url_path})
