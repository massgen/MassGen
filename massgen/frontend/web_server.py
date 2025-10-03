#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MassGen Web UI Backend Server

FastAPI server providing REST API and WebSocket endpoints for the Web UI.
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import yaml

from ..orchestrator import Orchestrator
from ..chat_agent import ConfigurableAgent
from ..logger_config import logger


class TaskRequest(BaseModel):
    """Request model for task submission"""
    task: str
    config: Optional[Dict[str, Any]] = None


class TaskResponse(BaseModel):
    """Response model for task submission"""
    task_id: str
    status: str
    message: str


class AgentStatus(BaseModel):
    """Model for agent status"""
    id: str
    name: str
    status: str
    current_task: Optional[str] = None
    progress: float = 0.0
    backend: str
    model: str


class CoordinationStatus(BaseModel):
    """Model for overall coordination status"""
    task_id: str
    task: str
    status: str
    agents: List[AgentStatus]
    coordinator_message: Optional[str] = None
    progress: float = 0.0
    result: Optional[str] = None
    winning_agent: Optional[str] = None


class WebSocketManager:
    """Manages WebSocket connections for real-time updates"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")
    
    async def broadcast(self, message: str):
        """Broadcast message to all connected clients"""
        if not self.active_connections:
            return
            
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Error broadcasting to connection: {e}")
                disconnected.append(connection)
        
        # Clean up disconnected connections
        for connection in disconnected:
            self.disconnect(connection)


class MassGenWebServer:
    """Main Web UI server for MassGen"""
    
    def __init__(self, host: str = "127.0.0.1", port: int = 8000):
        self.host = host
        self.port = port
        self.app = FastAPI(
            title="MassGen Web UI",
            description="Web interface for Multi-Agent Scaling System",
            version="1.0.0"
        )
        
        # CORS middleware for development
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", f"http://{host}:{port}"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Mount static files
        static_dir = Path(__file__).parent / "static"
        if static_dir.exists():
            self.app.mount("/static", StaticFiles(directory=static_dir), name="static")
        
        self.websocket_manager = WebSocketManager()
        self.current_orchestrators: Dict[str, Orchestrator] = {}
        self.task_counter = 0
        
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup API routes"""
        
        @self.app.get("/")
        async def root():
            """Serve the main web UI"""
            static_dir = Path(__file__).parent / "static"
            index_file = static_dir / "index.html"
            
            if index_file.exists():
                from fastapi.responses import FileResponse
                return FileResponse(index_file)
            else:
                return {"message": "MassGen Web UI API", "version": "1.0.0", "note": "Static files not found"}
        
        @self.app.get("/api/health")
        async def health_check():
            return {"status": "healthy", "active_connections": len(self.websocket_manager.active_connections)}
        
        @self.app.post("/api/upload-config")
        async def upload_config(file: UploadFile = File(...)):
            """Upload and validate a configuration file"""
            try:
                # Validate file type
                if not file.filename.endswith(('.yaml', '.yml', '.json')):
                    raise HTTPException(
                        status_code=400, 
                        detail="Only YAML (.yaml, .yml) and JSON (.json) files are supported"
                    )
                
                # Read file content
                content = await file.read()
                
                # Parse configuration
                try:
                    if file.filename.endswith('.json'):
                        config = json.loads(content.decode('utf-8'))
                    else:  # YAML
                        config = yaml.safe_load(content.decode('utf-8'))
                except Exception as e:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid configuration file format: {str(e)}"
                    )
                
                # Basic validation
                if not isinstance(config, dict):
                    raise HTTPException(
                        status_code=400,
                        detail="Configuration must be a valid object/dictionary"
                    )
                
                # Check for required structure
                if "agent" not in config and "agents" not in config:
                    raise HTTPException(
                        status_code=400,
                        detail="Configuration must contain either 'agent' or 'agents' section"
                    )
                
                return {
                    "status": "success",
                    "message": "Configuration file uploaded and validated successfully",
                    "config": config,
                    "filename": file.filename
                }
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error processing config upload: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Error processing configuration file: {str(e)}"
                )
        
        @self.app.post("/api/tasks", response_model=TaskResponse)
        async def submit_task(request: TaskRequest):
            """Submit a new task for processing"""
            try:
                self.task_counter += 1
                task_id = f"task_{self.task_counter}"
                
                # Create and store orchestrator for real processing
                if request.config:
                    # Use provided config
                    config = request.config
                else:
                    # Create default config with OpenAI agent
                    config = {
                        "agent": {
                            "id": "web_agent",
                            "backend": {
                                "type": "openai",
                                "model": "gpt-4o-mini"
                            },
                            "system_message": "You are a helpful AI assistant."
                        },
                        "ui": {
                            "display_type": "web",
                            "logging_enabled": True
                        }
                    }
                
                # Start processing task in background
                asyncio.create_task(self._process_task_async(task_id, request.task, config))
                
                response = TaskResponse(
                    task_id=task_id,
                    status="submitted",
                    message=f"Task '{request.task}' submitted successfully"
                )
                
                # Broadcast task submission
                await self.websocket_manager.broadcast(json.dumps({
                    "type": "task_submitted",
                    "data": response.dict()
                }))
                
                return response
                
            except Exception as e:
                logger.error(f"Error submitting task: {e}")
                raise HTTPException(status_code=500, detail=f"Error submitting task: {str(e)}")
        
        @self.app.get("/api/tasks/{task_id}/status", response_model=CoordinationStatus)
        async def get_task_status(task_id: str):
            """Get status of a specific task"""
            try:
                # Check if orchestrator exists for this task
                if task_id in self.current_orchestrators:
                    orchestrator = self.current_orchestrators[task_id]
                    # Get real status from orchestrator
                    return await self._get_real_task_status(task_id, orchestrator)
                else:
                    # Task not found or completed
                    raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error getting task status: {e}")
                raise HTTPException(status_code=500, detail=f"Error getting task status: {str(e)}")
        
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket endpoint for real-time updates"""
            await self.websocket_manager.connect(websocket)
            try:
                while True:
                    # Wait for messages from client (keep connection alive)
                    data = await websocket.receive_text()
                    message = json.loads(data)
                    
                    if message.get("type") == "ping":
                        await websocket.send_text(json.dumps({"type": "pong"}))
                    
            except WebSocketDisconnect:
                self.websocket_manager.disconnect(websocket)
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                self.websocket_manager.disconnect(websocket)
    
    async def start_server(self):
        """Start the web server"""
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info"
        )
        server = uvicorn.Server(config)
        
        logger.info(f"Starting MassGen Web UI server at http://{self.host}:{self.port}")
        await server.serve()
    
    async def broadcast_coordination_update(self, task_id: str, status: CoordinationStatus):
        """Broadcast coordination status update to all connected clients"""
        message = {
            "type": "coordination_update",
            "task_id": task_id,
            "data": status.dict()
        }
        await self.websocket_manager.broadcast(json.dumps(message))
    
    async def _process_task_async(self, task_id: str, question: str, config: Dict[str, Any]):
        """Process a task asynchronously using MassGen orchestrator"""
        try:
            from ..cli import create_agents_from_config
            from ...orchestrator import Orchestrator
            from ...agent_config import AgentConfig
            from ..displays.web_display import WebDisplay
            
            logger.info(f"Starting task processing for {task_id}: {question}")
            
            # Create agents from config
            agents = create_agents_from_config(config)
            
            # Create orchestrator
            orchestrator_config = AgentConfig()
            orchestrator = Orchestrator(
                agents=agents,
                config=orchestrator_config
            )
            
            # Store orchestrator for status queries
            self.current_orchestrators[task_id] = orchestrator
            
            # Create web display for real-time updates
            web_display = WebDisplay(web_server=self)
            web_display.current_task_id = task_id
            web_display.initialize_display(list(agents.keys()))
            
            # Broadcast initial status
            await self._broadcast_task_started(task_id, question, agents)
            
            # Process question using orchestrator with web display
            try:
                # This is a simplified approach - in reality, we'd need to integrate
                # the web display into the orchestrator's display system
                web_display.display_question(question)
                
                # Simulate orchestrator processing
                # In a full implementation, we'd need to modify the orchestrator
                # to support web display integration
                final_result = await self._simulate_orchestrator_processing(
                    task_id, question, orchestrator, web_display
                )
                
                # Broadcast completion
                await self._broadcast_task_completed(task_id, final_result)
                
            except Exception as e:
                logger.error(f"Error during task processing {task_id}: {e}")
                await self._broadcast_task_error(task_id, str(e))
            
            # Clean up
            if task_id in self.current_orchestrators:
                del self.current_orchestrators[task_id]
                
        except Exception as e:
            logger.error(f"Fatal error processing task {task_id}: {e}")
            await self._broadcast_task_error(task_id, f"Fatal error: {str(e)}")
    
    async def _simulate_orchestrator_processing(self, task_id: str, question: str, orchestrator, web_display):
        """Simulate orchestrator processing - replace with real orchestrator integration"""
        import asyncio
        
        # Simulate agent responses
        agents = orchestrator.agents
        agent_responses = {}
        
        for i, (agent_id, agent) in enumerate(agents.items()):
            web_display.update_agent_status(agent_id, "thinking", "Processing question...")
            await asyncio.sleep(1)  # Simulate thinking time
            
            web_display.update_agent_status(agent_id, "working", "Generating response...")
            await asyncio.sleep(2)  # Simulate working time
            
            # Get actual response from agent
            try:
                messages = [{"role": "user", "content": question}]
                response_content = ""
                
                async for chunk in agent.chat(messages):
                    if chunk.type == "content" and chunk.content:
                        response_content += chunk.content
                        
                agent_responses[agent_id] = response_content
                web_display.update_agent_status(agent_id, "completed", "Response generated")
                
            except Exception as e:
                logger.error(f"Error getting response from agent {agent_id}: {e}")
                agent_responses[agent_id] = f"Error: {str(e)}"
                web_display.update_agent_status(agent_id, "error", f"Error: {str(e)}")
        
        # Select best response (simplified - just take first non-error response)
        winning_agent = None
        final_response = None
        
        for agent_id, response in agent_responses.items():
            if not response.startswith("Error:"):
                winning_agent = agent_id
                final_response = response
                break
        
        if not final_response:
            # All agents failed
            winning_agent = list(agent_responses.keys())[0]
            final_response = list(agent_responses.values())[0]
        
        web_display.display_final_result(final_response, winning_agent)
        
        return {
            "final_answer": final_response,
            "winning_agent": winning_agent,
            "agent_responses": agent_responses
        }
    
    async def _broadcast_task_started(self, task_id: str, question: str, agents):
        """Broadcast task started status"""
        agent_statuses = []
        for agent_id, agent in agents.items():
            backend_name = agent.backend.__class__.__name__.replace("Backend", "").lower()
            model_name = getattr(agent.config, 'model', 'unknown')
            
            agent_statuses.append(AgentStatus(
                id=agent_id,
                name=f"{agent_id.title()} Agent",
                status="waiting",
                current_task="Initializing...",
                progress=0.0,
                backend=backend_name,
                model=model_name
            ))
        
        status = CoordinationStatus(
            task_id=task_id,
            task=question,
            status="in_progress",
            agents=agent_statuses,
            coordinator_message="Task started, initializing agents...",
            progress=0.0
        )
        
        await self.broadcast_coordination_update(task_id, status)
    
    async def _broadcast_task_completed(self, task_id: str, result: Dict[str, Any]):
        """Broadcast task completion status"""
        message = {
            "type": "task_completed",
            "task_id": task_id,
            "data": {
                "final_answer": result.get("final_answer", ""),
                "winning_agent": result.get("winning_agent", ""),
                "status": "completed"
            }
        }
        await self.websocket_manager.broadcast(json.dumps(message))
    
    async def _broadcast_task_error(self, task_id: str, error: str):
        """Broadcast task error status"""
        message = {
            "type": "task_error",
            "task_id": task_id,
            "data": {
                "error": error,
                "status": "error"
            }
        }
        await self.websocket_manager.broadcast(json.dumps(message))
    
    async def _get_real_task_status(self, task_id: str, orchestrator) -> CoordinationStatus:
        """Get real task status from orchestrator"""
        # This is a simplified implementation
        # In a full implementation, we'd query the orchestrator's current state
        
        agents = orchestrator.agents
        agent_statuses = []
        
        for agent_id, agent in agents.items():
            backend_name = agent.backend.__class__.__name__.replace("Backend", "").lower()
            model_name = getattr(agent.config, 'model', 'unknown')
            
            agent_statuses.append(AgentStatus(
                id=agent_id,
                name=f"{agent_id.title()} Agent",
                status="working",  # Simplified status
                current_task="Processing...",
                progress=0.5,
                backend=backend_name,
                model=model_name
            ))
        
        return CoordinationStatus(
            task_id=task_id,
            task="Processing task...",
            status="in_progress",
            agents=agent_statuses,
            coordinator_message="Task in progress...",
            progress=0.5
        )


def create_web_server(host: str = "127.0.0.1", port: int = 8000) -> MassGenWebServer:
    """Factory function to create web server instance"""
    return MassGenWebServer(host=host, port=port)


async def run_web_server(host: str = "127.0.0.1", port: int = 8000):
    """Run the web server"""
    server = create_web_server(host=host, port=port)
    await server.start_server()


if __name__ == "__main__":
    asyncio.run(run_web_server())