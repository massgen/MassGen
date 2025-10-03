# -*- coding: utf-8 -*-
"""
Web Display for MassGen

Provides integration between the orchestrator and the web UI.
"""

import asyncio
import json
from typing import Any, Dict, List, Optional

from .base_display import BaseDisplay
from ..web_server import MassGenWebServer, CoordinationStatus, AgentStatus
from ...logger_config import logger


class WebDisplay(BaseDisplay):
    """Web-based display that integrates with the FastAPI web server"""
    
    def __init__(self, web_server: Optional[MassGenWebServer] = None, **kwargs):
        super().__init__(**kwargs)
        self.web_server = web_server
        self.current_task_id: Optional[str] = None
        
    def initialize_display(self, agent_ids: List[str]) -> None:
        """Initialize the web display"""
        self.agent_ids = agent_ids
        logger.info(f"WebDisplay initialized for agents: {agent_ids}")
        
        if self.web_server:
            # Send initial status to web clients
            asyncio.create_task(self._broadcast_initial_status())
    
    async def _broadcast_initial_status(self):
        """Broadcast initial status to web clients"""
        if not self.web_server:
            return
            
        try:
            # Create initial agent statuses
            agents = []
            for agent_id in self.agent_ids:
                agents.append(AgentStatus(
                    id=agent_id,
                    name=f"{agent_id.title()} Agent",
                    status="waiting",
                    current_task=None,
                    progress=0.0,
                    backend="unknown",
                    model="unknown"
                ))
            
            status = CoordinationStatus(
                task_id=self.current_task_id or "unknown",
                task="Waiting for task...",
                status="waiting",
                agents=agents,
                coordinator_message="Ready to coordinate agents",
                progress=0.0
            )
            
            await self.web_server.broadcast_coordination_update(
                task_id=self.current_task_id or "unknown",
                status=status
            )
            
        except Exception as e:
            logger.error(f"Error broadcasting initial status: {e}")
    
    def update_agent_status(self, agent_id: str, status: str, message: str = "") -> None:
        """Update status of a specific agent"""
        if self.web_server and self.current_task_id:
            asyncio.create_task(self._update_agent_in_web_ui(agent_id, status, message))
    
    async def _update_agent_in_web_ui(self, agent_id: str, status: str, message: str):
        """Update agent status in web UI"""
        try:
            # This would typically fetch current status and update the specific agent
            # For now, we'll broadcast a generic update
            agents = []
            for aid in self.agent_ids:
                agent_status = status if aid == agent_id else "waiting"
                progress = 0.5 if aid == agent_id and status == "working" else 0.0
                
                agents.append(AgentStatus(
                    id=aid,
                    name=f"{aid.title()} Agent",
                    status=agent_status,
                    current_task=message if aid == agent_id else None,
                    progress=progress,
                    backend="unknown",
                    model="unknown"
                ))
            
            coordination_status = CoordinationStatus(
                task_id=self.current_task_id,
                task="Agent coordination in progress",
                status="in_progress",
                agents=agents,
                coordinator_message=f"Agent {agent_id} is {status}",
                progress=0.3
            )
            
            await self.web_server.broadcast_coordination_update(
                task_id=self.current_task_id,
                status=coordination_status
            )
            
        except Exception as e:
            logger.error(f"Error updating agent status in web UI: {e}")
    
    def display_question(self, question: str) -> None:
        """Display the question being processed"""
        self.current_task_id = f"task_{hash(question) % 10000}"
        logger.info(f"WebDisplay processing question: {question}")
        
        if self.web_server:
            asyncio.create_task(self._broadcast_question_update(question))
    
    async def _broadcast_question_update(self, question: str):
        """Broadcast question update to web clients"""
        try:
            agents = []
            for agent_id in self.agent_ids:
                agents.append(AgentStatus(
                    id=agent_id,
                    name=f"{agent_id.title()} Agent",
                    status="thinking",
                    current_task="Processing question",
                    progress=0.1,
                    backend="unknown",
                    model="unknown"
                ))
            
            status = CoordinationStatus(
                task_id=self.current_task_id,
                task=question,
                status="in_progress",
                agents=agents,
                coordinator_message="Agents are analyzing the question...",
                progress=0.1
            )
            
            await self.web_server.broadcast_coordination_update(
                task_id=self.current_task_id,
                status=status
            )
            
        except Exception as e:
            logger.error(f"Error broadcasting question update: {e}")
    
    def display_agent_response(self, agent_id: str, content: str) -> None:
        """Display agent response"""
        logger.info(f"WebDisplay agent response from {agent_id}: {content[:100]}...")
        self.update_agent_status(agent_id, "completed", "Response generated")
    
    def display_final_result(self, result: str, winning_agent: str) -> None:
        """Display final result"""
        logger.info(f"WebDisplay final result from {winning_agent}: {result[:100]}...")
        
        if self.web_server and self.current_task_id:
            asyncio.create_task(self._broadcast_final_result(result, winning_agent))
    
    async def _broadcast_final_result(self, result: str, winning_agent: str):
        """Broadcast final result to web clients"""
        try:
            agents = []
            for agent_id in self.agent_ids:
                status = "completed" if agent_id == winning_agent else "waiting"
                agents.append(AgentStatus(
                    id=agent_id,
                    name=f"{agent_id.title()} Agent",
                    status=status,
                    current_task="Task completed",
                    progress=1.0 if agent_id == winning_agent else 0.5,
                    backend="unknown",
                    model="unknown"
                ))
            
            coordination_status = CoordinationStatus(
                task_id=self.current_task_id,
                task="Task completed successfully",
                status="completed",
                agents=agents,
                coordinator_message="Task completed successfully!",
                progress=1.0,
                result=result,
                winning_agent=winning_agent
            )
            
            await self.web_server.broadcast_coordination_update(
                task_id=self.current_task_id,
                status=coordination_status
            )
            
        except Exception as e:
            logger.error(f"Error broadcasting final result: {e}")
    
    def display_error(self, error: str) -> None:
        """Display error message"""
        logger.error(f"WebDisplay error: {error}")
        
        if self.web_server and self.current_task_id:
            asyncio.create_task(self._broadcast_error(error))
    
    async def _broadcast_error(self, error: str):
        """Broadcast error to web clients"""
        try:
            agents = []
            for agent_id in self.agent_ids:
                agents.append(AgentStatus(
                    id=agent_id,
                    name=f"{agent_id.title()} Agent",
                    status="error",
                    current_task="Error occurred",
                    progress=0.0,
                    backend="unknown",
                    model="unknown"
                ))
            
            coordination_status = CoordinationStatus(
                task_id=self.current_task_id or "error",
                task="Error occurred",
                status="error",
                agents=agents,
                coordinator_message=f"Error: {error}",
                progress=0.0
            )
            
            await self.web_server.broadcast_coordination_update(
                task_id=self.current_task_id or "error",
                status=coordination_status
            )
            
        except Exception as e:
            logger.error(f"Error broadcasting error message: {e}")
    
    def cleanup(self) -> None:
        """Cleanup display resources"""
        logger.info("WebDisplay cleanup")
        self.current_task_id = None