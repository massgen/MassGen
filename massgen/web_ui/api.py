"""
API routes for MassGen Web UI.
"""

import asyncio
import json
import tempfile
import uuid
from pathlib import Path
from typing import Dict, Any

from flask import Blueprint, request, jsonify
import yaml

from ..cli import (
    load_config_file, 
    create_agents_from_config, 
    validate_context_paths, 
    relocate_filesystem_paths,
    ConfigurationError
)
from ..agent_config import TimeoutConfig
from ..orchestrator import Orchestrator
from .websocket_handler import emit_agent_status, emit_coordination_event


api_bp = Blueprint('api', __name__)

# Global storage for active sessions
active_sessions: Dict[str, Dict[str, Any]] = {}


@api_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({'status': 'healthy'})


@api_bp.route('/upload-config', methods=['POST'])
def upload_config():
    """Upload and validate a configuration file."""
    try:
        if 'config_file' not in request.files:
            return jsonify({'error': 'No config file provided'}), 400
        
        file = request.files['config_file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Save temporarily and load config
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.yaml', delete=False) as tmp_file:
            content = file.read().decode('utf-8')
            tmp_file.write(content)
            tmp_file.flush()
            
            config = load_config_file(tmp_file.name)
            
            # Clean up temp file
            Path(tmp_file.name).unlink()
        
        # Validate config
        validate_context_paths(config)
        relocate_filesystem_paths(config)
        
        return jsonify({
            'success': True,
            'config': config,
            'message': 'Configuration loaded successfully'
        })
        
    except ConfigurationError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to load config: {str(e)}'}), 500


@api_bp.route('/create-session', methods=['POST'])
def create_session():
    """Create a new coordination session."""
    try:
        data = request.get_json()
        config = data.get('config')
        question = data.get('question')
        
        if not config:
            return jsonify({'error': 'Configuration required'}), 400
        if not question:
            return jsonify({'error': 'Question required'}), 400
        
        # Generate session ID
        session_id = str(uuid.uuid4())
        
        # Create agents from config
        orchestrator_cfg = config.get('orchestrator', {})
        agents = create_agents_from_config(config, orchestrator_cfg)
        
        # Create timeout config
        timeout_settings = config.get('timeout_settings', {})
        timeout_config = TimeoutConfig(**timeout_settings) if timeout_settings else TimeoutConfig()
        
        # Store session data
        active_sessions[session_id] = {
            'config': config,
            'agents': agents,
            'orchestrator_cfg': orchestrator_cfg,
            'timeout_config': timeout_config,
            'question': question,
            'status': 'created'
        }
        
        return jsonify({
            'session_id': session_id,
            'agents': list(agents.keys()),
            'message': 'Session created successfully'
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to create session: {str(e)}'}), 500


@api_bp.route('/start-coordination', methods=['POST'])
def start_coordination():
    """Start the coordination process."""
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        
        if not session_id or session_id not in active_sessions:
            return jsonify({'error': 'Invalid session ID'}), 400
        
        session_data = active_sessions[session_id]
        
        # Update status
        session_data['status'] = 'running'
        
        # Start coordination in background
        def run_coordination():
            """Run coordination in a separate thread."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(_run_coordination_async(session_id))
            finally:
                loop.close()
        
        import threading
        coordination_thread = threading.Thread(target=run_coordination)
        coordination_thread.daemon = True
        coordination_thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Coordination started'
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to start coordination: {str(e)}'}), 500


async def _run_coordination_async(session_id: str):
    """Run the coordination process asynchronously."""
    try:
        session_data = active_sessions[session_id]
        
        # Create orchestrator
        orchestrator_config = session_data['timeout_config']
        orchestrator_cfg = session_data['orchestrator_cfg']
        
        orchestrator = Orchestrator(
            agents=session_data['agents'],
            config=orchestrator_config,
            snapshot_storage=orchestrator_cfg.get('snapshot_storage'),
            agent_temporary_workspace=orchestrator_cfg.get('agent_temporary_workspace'),
        )
        
        # Start coordination with websocket events
        question = session_data['question']
        
        # Emit start event
        emit_coordination_event(session_id, {
            'type': 'coordination_started',
            'question': question,
            'agents': list(session_data['agents'].keys())
        })
        
        # Run coordination
        final_result = await orchestrator.coordinate(question)
        
        # Update session with result
        session_data['status'] = 'completed'
        session_data['result'] = final_result
        
        # Emit completion event
        emit_coordination_event(session_id, {
            'type': 'coordination_completed',
            'result': final_result
        })
        
    except Exception as e:
        # Update session with error
        session_data['status'] = 'error'
        session_data['error'] = str(e)
        
        # Emit error event
        emit_coordination_event(session_id, {
            'type': 'coordination_error',
            'error': str(e)
        })


@api_bp.route('/session-status/<session_id>', methods=['GET'])
def get_session_status(session_id: str):
    """Get the status of a coordination session."""
    if session_id not in active_sessions:
        return jsonify({'error': 'Session not found'}), 404
    
    session_data = active_sessions[session_id]
    
    response_data = {
        'session_id': session_id,
        'status': session_data['status'],
        'agents': list(session_data['agents'].keys()),
        'question': session_data['question']
    }
    
    if 'result' in session_data:
        response_data['result'] = session_data['result']
    
    if 'error' in session_data:
        response_data['error'] = session_data['error']
    
    return jsonify(response_data)


@api_bp.route('/stop-session/<session_id>', methods=['POST'])
def stop_session(session_id: str):
    """Stop and clean up a coordination session."""
    if session_id in active_sessions:
        session_data = active_sessions[session_id]
        session_data['status'] = 'stopped'
        
        # Clean up agents
        for agent in session_data.get('agents', {}).values():
            if hasattr(agent, 'cleanup'):
                agent.cleanup()
        
        # Remove from active sessions
        del active_sessions[session_id]
    
    return jsonify({'success': True})


@api_bp.route('/sample-configs', methods=['GET'])
def get_sample_configs():
    """Get sample configuration templates."""
    single_agent_config = {
        "agent": {
            "id": "agent1",
            "backend": {
                "type": "openai",
                "model": "gpt-4o-mini"
            },
            "system_message": "You are a helpful AI assistant."
        },
        "ui": {
            "display_type": "rich_terminal",
            "logging_enabled": True
        }
    }
    
    multi_agent_config = {
        "agents": [
            {
                "id": "analyst",
                "backend": {
                    "type": "openai", 
                    "model": "gpt-4o"
                },
                "system_message": "You are a data analyst focused on thorough analysis."
            },
            {
                "id": "creative",
                "backend": {
                    "type": "claude",
                    "model": "claude-3-5-sonnet-20241022"
                },
                "system_message": "You are a creative thinker focused on innovative solutions."
            }
        ],
        "orchestrator": {
            "snapshot_storage": ".massgen/snapshots",
            "agent_temporary_workspace": ".massgen/temp_workspaces",
            "session_storage": ".massgen/sessions"
        },
        "ui": {
            "display_type": "rich_terminal",
            "logging_enabled": True
        }
    }
    
    return jsonify({
        'single_agent': single_agent_config,
        'multi_agent': multi_agent_config
    })