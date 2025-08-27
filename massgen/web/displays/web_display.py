"""
Web Display for MassGen Coordination

Extends BaseDisplay to stream coordination updates to web clients via WebSocket.
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, List, Any, Optional

from ...frontend.displays.base_display import BaseDisplay

class WebDisplay(BaseDisplay):
    """Web-based display that streams coordination to browser clients"""
    
    def __init__(self, agent_ids: List[str], session_id: str, ws_manager=None, **kwargs):
        super().__init__(agent_ids, **kwargs)
        self.session_id = session_id
        self.ws_manager = ws_manager
        self.coordination_log = []
        
    def initialize(self, question: str, log_filename: Optional[str] = None):
        """Initialize the display with question and optional log file."""
        self.question = question
        self.log_filename = log_filename
        
        # Stream initialization to web client
        if self.ws_manager:
            asyncio.create_task(self.ws_manager.stream_coordination_update(self.session_id, {
                "type": "display_initialized",
                "question": question,
                "agent_ids": self.agent_ids,
                "log_filename": log_filename,
                "timestamp": datetime.now().isoformat()
            }))
            
    def update_agent_content(
        self, agent_id: str, content: str, content_type: str = "thinking"
    ):
        """Update content for a specific agent."""
        if agent_id not in self.agent_ids:
            return
            
        # Process content using parent class method
        processed_content = self.process_reasoning_content(content_type, content, agent_id)
        
        # Store in local state
        self.agent_outputs[agent_id].append({
            "content": processed_content,
            "type": content_type,
            "timestamp": datetime.now().isoformat()
        })
        
        # Stream to web client
        if self.ws_manager:
            asyncio.create_task(self.ws_manager.stream_coordination_update(self.session_id, {
                "type": "agent_content_update",
                "agent_id": agent_id,
                "content": processed_content,
                "content_type": content_type,
                "timestamp": datetime.now().isoformat()
            }))
            
    def update_agent_status(self, agent_id: str, status: str):
        """Update status for a specific agent."""
        if agent_id not in self.agent_ids:
            return
            
        old_status = self.agent_status.get(agent_id)
        self.agent_status[agent_id] = status
        
        # Stream status update to web client
        if self.ws_manager:
            asyncio.create_task(self.ws_manager.stream_coordination_update(self.session_id, {
                "type": "agent_status_update",
                "agent_id": agent_id,
                "status": status,
                "previous_status": old_status,
                "timestamp": datetime.now().isoformat()
            }))
            
    def add_orchestrator_event(self, event: str):
        """Add an orchestrator coordination event."""
        self.orchestrator_events.append({
            "event": event,
            "timestamp": datetime.now().isoformat()
        })
        
        # Stream event to web client
        if self.ws_manager:
            asyncio.create_task(self.ws_manager.stream_coordination_update(self.session_id, {
                "type": "orchestrator_event",
                "event": event,
                "timestamp": datetime.now().isoformat()
            }))
            
    def show_final_answer(self, answer: str, vote_results=None, selected_agent=None):
        """Display the final coordinated answer."""
        final_data = {
            "answer": answer,
            "vote_results": vote_results,
            "selected_agent": selected_agent,
            "timestamp": datetime.now().isoformat()
        }
        
        # Stream final answer to web client
        if self.ws_manager:
            asyncio.create_task(self.ws_manager.stream_coordination_update(self.session_id, {
                "type": "final_answer",
                **final_data
            }))
            
    def cleanup(self):
        """Clean up display resources."""
        # Stream cleanup event
        if self.ws_manager:
            asyncio.create_task(self.ws_manager.stream_coordination_update(self.session_id, {
                "type": "display_cleanup",
                "timestamp": datetime.now().isoformat()
            }))
            
    def get_session_summary(self) -> Dict[str, Any]:
        """Get complete session summary for web client"""
        return {
            "session_id": self.session_id,
            "question": getattr(self, 'question', ''),
            "agent_ids": self.agent_ids,
            "agent_outputs": self.agent_outputs,
            "agent_status": self.agent_status,
            "orchestrator_events": self.orchestrator_events,
            "coordination_log": self.coordination_log,
            "timestamp": datetime.now().isoformat()
        }