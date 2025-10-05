"""
WebSocket handler for real-time communication in MassGen Web UI.
"""

from flask_socketio import SocketIO, emit
from typing import Dict, Any

# Initialize SocketIO
socketio = SocketIO(cors_allowed_origins="*")

# Store active sessions and their socket rooms
session_rooms: Dict[str, str] = {}


@socketio.on('connect')
def handle_connect():
    """Handle client connection."""
    print(f"Client connected: {request.sid}")
    emit('connected', {'message': 'Connected to MassGen WebSocket'})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection."""
    print(f"Client disconnected: {request.sid}")


@socketio.on('join_session')
def handle_join_session(data):
    """Join a coordination session room."""
    session_id = data.get('session_id')
    if session_id:
        join_room(session_id)
        session_rooms[request.sid] = session_id
        emit('joined_session', {'session_id': session_id})


@socketio.on('leave_session')
def handle_leave_session(data):
    """Leave a coordination session room."""
    session_id = data.get('session_id')
    if session_id and request.sid in session_rooms:
        leave_room(session_id)
        del session_rooms[request.sid]
        emit('left_session', {'session_id': session_id})


def emit_agent_status(session_id: str, agent_id: str, status_data: Dict[str, Any]):
    """Emit agent status update to session room."""
    socketio.emit('agent_status', {
        'agent_id': agent_id,
        'status': status_data
    }, room=session_id)


def emit_coordination_event(session_id: str, event_data: Dict[str, Any]):
    """Emit coordination event to session room."""
    socketio.emit('coordination_event', event_data, room=session_id)


def emit_agent_output(session_id: str, agent_id: str, output_data: Dict[str, Any]):
    """Emit agent output to session room."""
    socketio.emit('agent_output', {
        'agent_id': agent_id,
        'output': output_data
    }, room=session_id)


def emit_voting_event(session_id: str, voting_data: Dict[str, Any]):
    """Emit voting event to session room."""
    socketio.emit('voting_event', voting_data, room=session_id)


# Import after defining socketio to avoid circular imports
from flask import request
from flask_socketio import join_room, leave_room