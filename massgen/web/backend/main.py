"""
FastAPI Backend for MassGen Web Interface

Provides WebSocket streaming and multimedia upload capabilities.
"""

import os
import json
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

# Import MassGen components
try:
    from ...orchestrator import Orchestrator
    from ...agent_config import AgentConfig
    from ..displays.web_display import WebDisplay
    from .multimedia_processor import MultimediaProcessor
except ImportError as e:
    print(f"Warning: Could not import some MassGen components: {e}")
    print("Some features may not be available.")
    
    # Define minimal stubs for testing
    class Orchestrator:
        def __init__(self, agents): pass
        async def chat_stream(self, messages): 
            yield type('StreamChunk', (), {'to_dict': lambda: {}, 'content': 'Test response'})()
    
    class AgentConfig:
        @classmethod
        def from_dict(cls, config): return cls()
        def create_agent(self): return type('Agent', (), {'backend': type('Backend', (), {'get_provider_name': lambda: 'test'})()})()
    
    from .multimedia_processor import MultimediaProcessor
    
    class WebDisplay:
        def __init__(self, *args, **kwargs): pass
        def initialize(self, *args, **kwargs): pass
        def update_agent_content(self, *args, **kwargs): pass

@dataclass
class MediaFile:
    id: str
    filename: str
    content_type: str
    file_path: str
    thumbnail_path: Optional[str]
    upload_timestamp: str
    metadata: Dict[str, Any]

@dataclass  
class CoordinationSession:
    session_id: str
    task: str
    agents: List[str]
    media_files: List[MediaFile]
    orchestrator: Optional[Orchestrator]
    web_display: Optional[WebDisplay]
    status: str
    created_at: str

class MultimediaWebSocketManager:
    """Manages WebSocket connections and coordination sessions"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.coordination_sessions: Dict[str, CoordinationSession] = {}
        self.multimedia_processor = MultimediaProcessor()
        
    async def connect(self, session_id: str, websocket: WebSocket):
        """Connect a WebSocket client"""
        await websocket.accept()
        self.active_connections[session_id] = websocket
        print(f"WebSocket connected: {session_id}")
        
    async def disconnect(self, session_id: str):
        """Disconnect a WebSocket client"""
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            print(f"WebSocket disconnected: {session_id}")
            
    async def stream_coordination_update(self, session_id: str, update: dict):
        """Stream coordination updates to client"""
        if session_id in self.active_connections:
            try:
                await self.active_connections[session_id].send_text(json.dumps(update))
            except Exception as e:
                print(f"Error streaming to {session_id}: {e}")
                await self.disconnect(session_id)
                
    async def process_media_file(self, session_id: str, file: UploadFile) -> MediaFile:
        """Process uploaded media file"""
        # Generate unique filename
        file_id = str(uuid.uuid4())
        safe_filename = f"{file_id}_{file.filename}"
        file_path = self.multimedia_processor.storage_dir / safe_filename
        
        # Save file
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
            
        # Process based on content type
        metadata = {}
        thumbnail_path = None
        
        if file.content_type.startswith('image/'):
            result = await self.multimedia_processor.process_image(str(file_path))
            metadata = result
            thumbnail_path = result.get('thumbnail_path')
        elif file.content_type.startswith('audio/'):
            metadata = await self.multimedia_processor.process_audio(str(file_path))
        elif file.content_type.startswith('video/'):
            metadata = await self.multimedia_processor.process_video(str(file_path))
            
        media_file = MediaFile(
            id=file_id,
            filename=file.filename,
            content_type=file.content_type,
            file_path=str(file_path),
            thumbnail_path=thumbnail_path,
            upload_timestamp=datetime.now().isoformat(),
            metadata=metadata
        )
        
        # Add to session
        if session_id in self.coordination_sessions:
            self.coordination_sessions[session_id].media_files.append(media_file)
            
        return media_file
        
    async def start_coordination(self, session_id: str, task: str, agent_configs: List[Dict]):
        """Start a coordination session"""
        try:
            # Create agents from configs
            agents = {}
            agent_ids = []
            
            for config in agent_configs:
                agent_config = AgentConfig.from_dict(config)
                agent = agent_config.create_agent()
                agent_id = config.get('id', f'agent_{len(agents)}')
                agents[agent_id] = agent
                agent_ids.append(agent_id)
                
            # Create orchestrator
            orchestrator = Orchestrator(agents)
            
            # Create web display
            web_display = WebDisplay(agent_ids, session_id, ws_manager=self)
            
            # Create session
            session = CoordinationSession(
                session_id=session_id,
                task=task,
                agents=agent_ids,
                media_files=self.coordination_sessions.get(session_id, CoordinationSession(
                    session_id, "", [], [], None, None, "created", ""
                )).media_files,
                orchestrator=orchestrator,
                web_display=web_display,
                status="coordinating",
                created_at=datetime.now().isoformat()
            )
            
            self.coordination_sessions[session_id] = session
            
            # Start coordination in background
            asyncio.create_task(self._run_coordination(session_id, task))
            
            return session
            
        except Exception as e:
            print(f"Error starting coordination: {e}")
            raise HTTPException(status_code=500, detail=str(e))
            
    async def _run_coordination(self, session_id: str, task: str):
        """Run coordination session"""
        session = self.coordination_sessions[session_id]
        
        try:
            # Initialize display
            session.web_display.initialize(task)
            
            # Add media context to task if files exist
            if session.media_files:
                media_context = "\n\nAttached media files:\n"
                for media in session.media_files:
                    media_context += f"- {media.filename} ({media.content_type})\n"
                task_with_media = task + media_context
            else:
                task_with_media = task
                
            # Stream coordination
            await self.stream_coordination_update(session_id, {
                "type": "coordination_started",
                "task": task,
                "agents": session.agents,
                "media_files": [asdict(mf) for mf in session.media_files]
            })
            
            # Run orchestrator
            async for chunk in session.orchestrator.chat_stream([{"role": "user", "content": task_with_media}]):
                # Stream chunk to web client
                await self.stream_coordination_update(session_id, {
                    "type": "coordination_chunk",
                    "chunk": chunk.to_dict() if hasattr(chunk, 'to_dict') else str(chunk),
                    "source": getattr(chunk, 'source', 'orchestrator')
                })
                
                # Update web display
                if hasattr(chunk, 'source') and hasattr(chunk, 'content'):
                    session.web_display.update_agent_content(
                        chunk.source, 
                        chunk.content,
                        getattr(chunk, 'type', 'thinking')
                    )
                    
            session.status = "completed"
            await self.stream_coordination_update(session_id, {
                "type": "coordination_completed",
                "status": "completed"
            })
            
        except Exception as e:
            print(f"Coordination error: {e}")
            session.status = "error"
            await self.stream_coordination_update(session_id, {
                "type": "coordination_error",
                "error": str(e)
            })

# Global manager instance
ws_manager = MultimediaWebSocketManager()

# FastAPI app
app = FastAPI(title="MassGen Web Interface", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time coordination"""
    await ws_manager.connect(session_id, websocket)
    try:
        while True:
            # Keep connection alive and handle client messages
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                
    except WebSocketDisconnect:
        await ws_manager.disconnect(session_id)

@app.post("/api/sessions/{session_id}/upload")
async def upload_media(session_id: str, file: UploadFile = File(...)):
    """Upload media file to session"""
    try:
        media_file = await ws_manager.process_media_file(session_id, file)
        
        # Notify client
        await ws_manager.stream_coordination_update(session_id, {
            "type": "media_uploaded",
            "media_file": asdict(media_file)
        })
        
        return {"status": "success", "media_file": asdict(media_file)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sessions/{session_id}/start")
async def start_coordination_session(session_id: str, request: dict):
    """Start coordination with task and agent configuration"""
    try:
        task = request.get("task", "")
        agent_configs = request.get("agents", [
            {
                "id": "agent1",
                "backend": {"type": "openai", "model": "gpt-4o-mini"},
                "persona": "You are a helpful assistant"
            }
        ])
        
        session = await ws_manager.start_coordination(session_id, task, agent_configs)
        
        return {"status": "success", "session": {
            "session_id": session.session_id,
            "task": session.task,
            "agents": session.agents,
            "status": session.status
        }}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sessions/{session_id}/status")
async def get_session_status(session_id: str):
    """Get session status"""
    if session_id in ws_manager.coordination_sessions:
        session = ws_manager.coordination_sessions[session_id]
        return {
            "session_id": session.session_id,
            "status": session.status,
            "agents": session.agents,
            "media_files": [asdict(mf) for mf in session.media_files]
        }
    else:
        raise HTTPException(status_code=404, detail="Session not found")

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# Serve static files for media
app.mount("/media", StaticFiles(directory="web_uploads"), name="media")

if __name__ == "__main__":
    # Create upload directory
    Path("web_uploads").mkdir(exist_ok=True)
    
    uvicorn.run(
        "massgen.web.backend.main:app", 
        host="127.0.0.1", 
        port=8000, 
        reload=True,
        log_level="info"
    )