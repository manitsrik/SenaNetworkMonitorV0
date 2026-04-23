"""
Read-only assistant API routes.
"""
from flask import Blueprint, current_app, jsonify, request, session
from .auth import login_required, operator_required
from assistant_service import AssistantService


assistant_bp = Blueprint('assistant', __name__)


def _get_db():
    return current_app.config['DB']


def _get_monitor():
    return current_app.config['MONITOR']


def _get_socketio():
    return current_app.config['SOCKETIO']


@assistant_bp.route('/api/assistant/chat', methods=['POST'])
@login_required
def assistant_chat():
    data = request.json or {}
    question = (data.get('message') or '').strip()
    assistant_context = session.get('assistant_context') or {}

    service = AssistantService(_get_db())
    result = service.answer(question, context=assistant_context)
    session['assistant_context'] = result.get('context') or {}

    try:
        _get_db().add_audit_log(
            user_id=session.get('user_id'),
            username=session.get('username'),
            action='assistant_chat',
            category='assistant',
            target_type='assistant',
            target_name='read_only_assistant',
            details=question[:1000],
            ip_address=request.remote_addr,
        )
    except Exception:
        pass

    return jsonify(result)


@assistant_bp.route('/api/assistant/context/reset', methods=['POST'])
@login_required
def assistant_reset_context():
    session.pop('assistant_context', None)

    try:
        _get_db().add_audit_log(
            user_id=session.get('user_id'),
            username=session.get('username'),
            action='assistant_context_reset',
            category='assistant',
            target_type='assistant',
            target_name='read_only_assistant',
            details='context_reset',
            ip_address=request.remote_addr,
        )
    except Exception:
        pass

    return jsonify({
        'success': True,
        'message': 'Assistant context cleared.',
    })


@assistant_bp.route('/api/assistant/action', methods=['POST'])
@operator_required
def assistant_action():
    data = request.json or {}
    action_id = (data.get('action_id') or '').strip()
    payload = data.get('payload') or {}

    if action_id != 'check_device_now':
        return jsonify({'success': False, 'error': 'Unsupported assistant action'}), 400

    try:
        device_id = int(payload.get('device_id'))
    except Exception:
        return jsonify({'success': False, 'error': 'device_id is required'}), 400

    db = _get_db()
    device = db.get_device(device_id)
    if not device:
        return jsonify({'success': False, 'error': 'Device not found'}), 404

    result = _get_monitor().check_device(device)
    _get_socketio().emit('status_update', result, namespace='/')

    try:
        db.add_audit_log(
            user_id=session.get('user_id'),
            username=session.get('username'),
            action='assistant_action',
            category='assistant',
            target_type='device',
            target_id=device_id,
            target_name=device.get('name'),
            details=f'check_device_now:{device_id}',
            ip_address=request.remote_addr,
        )
    except Exception:
        pass

    return jsonify({
        'success': True,
        'action_id': action_id,
        'message': f"Device check completed for {device.get('name')}.",
        'result': result,
        'timestamp': result.get('last_check') or '',
    })
