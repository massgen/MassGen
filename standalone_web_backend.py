#!/usr/bin/env python3
"""
Standalone Web Backend for MassGen Studio Phase 1 Demo

Self-contained FastAPI backend that demonstrates the web interface
without dependencies on the main MassGen package.
"""

import uvicorn
import os
import json
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import shutil

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Standalone multimedia processor
class StandaloneMultimediaProcessor:
    """Simplified multimedia processor for demo"""
    
    def __init__(self, storage_dir: str = "./web_uploads"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True)
        (self.storage_dir / "thumbnails").mkdir(exist_ok=True)
    
    async def process_image(self, file_path: str) -> Dict:
        """Basic image processing"""
        try:
            # Try to use Pillow if available
            from PIL import Image
            
            image = Image.open(file_path)
            
            # Create thumbnail
            thumbnail = image.copy()
            thumbnail.thumbnail((200, 200), Image.Resampling.LANCZOS)
            
            file_stem = Path(file_path).stem
            thumbnail_path = self.storage_dir / "thumbnails" / f"{file_stem}_thumb.jpg"
            thumbnail.save(thumbnail_path, "JPEG")
            
            return {
                "dimensions": image.size,
                "format": image.format,
                "thumbnail_path": str(thumbnail_path),
                "file_size": os.path.getsize(file_path)
            }
        except ImportError:
            # Fallback without Pillow
            return {
                "dimensions": None,
                "format": None,
                "thumbnail_path": None,
                "file_size": os.path.getsize(file_path),
                "error": "Pillow not available"
            }
        except Exception as e:
            return {
                "error": str(e),
                "file_size": os.path.getsize(file_path)
            }
    
    async def process_audio(self, file_path: str) -> Dict:
        """Basic audio processing"""
        return {
            "duration": None,
            "file_size": os.path.getsize(file_path),
            "error": "Audio processing not implemented in demo"
        }
    
    def get_supported_formats(self) -> Dict[str, List[str]]:
        """Get supported file formats"""
        return {
            "images": [".jpg", ".jpeg", ".png", ".gif", ".webp"],
            "audio": [".mp3", ".wav", ".m4a", ".ogg"],
            "video": [".mp4", ".webm", ".mov", ".avi"]
        }

def create_demo_app():
    """Create demo FastAPI application"""
    app = FastAPI(title="MassGen Studio Demo", version="1.0.0")
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Global state
    active_connections: Dict[str, WebSocket] = {}
    sessions: Dict[str, Dict] = {}
    multimedia_processor = StandaloneMultimediaProcessor()
    
    @app.websocket("/ws/{session_id}")
    async def websocket_endpoint(websocket: WebSocket, session_id: str):
        """WebSocket endpoint for real-time coordination"""
        await websocket.accept()
        active_connections[session_id] = websocket
        print(f"✅ WebSocket connected: {session_id}")
        
        try:
            while True:
                data = await websocket.receive_text()
                message = json.loads(data)
                
                if message.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                    
        except WebSocketDisconnect:
            if session_id in active_connections:
                del active_connections[session_id]
            print(f"❌ WebSocket disconnected: {session_id}")
    
    @app.post("/api/sessions/{session_id}/upload")
    async def upload_media(session_id: str, file: UploadFile = File(...)):
        """Upload media file to session"""
        try:
            # Generate unique filename
            file_id = str(uuid.uuid4())
            safe_filename = f"{file_id}_{file.filename}"
            file_path = multimedia_processor.storage_dir / safe_filename
            
            # Save file
            content = await file.read()
            with open(file_path, "wb") as f:
                f.write(content)
            
            print(f"📁 Uploaded: {file.filename} ({len(content)} bytes)")
            
            # Process based on content type
            metadata = {"file_size": len(content)}
            thumbnail_path = None
            
            if file.content_type.startswith('image/'):
                result = await multimedia_processor.process_image(str(file_path))
                metadata.update(result)
                thumbnail_path = result.get('thumbnail_path')
            elif file.content_type.startswith('audio/'):
                result = await multimedia_processor.process_audio(str(file_path))
                metadata.update(result)
            
            media_file = {
                "id": file_id,
                "filename": file.filename,
                "content_type": file.content_type,
                "file_path": str(file_path),
                "thumbnail_path": thumbnail_path,
                "upload_timestamp": datetime.now().isoformat(),
                "metadata": metadata
            }
            
            # Store in session
            if session_id not in sessions:
                sessions[session_id] = {"media_files": []}
            sessions[session_id]["media_files"].append(media_file)
            
            # Notify WebSocket clients
            if session_id in active_connections:
                await active_connections[session_id].send_text(json.dumps({
                    "type": "media_uploaded",
                    "media_file": media_file
                }))
            
            return {"status": "success", "media_file": media_file}
            
        except Exception as e:
            print(f"❌ Upload error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/sessions/{session_id}/start")
    async def start_coordination(session_id: str, request: dict):
        """Start coordination session (demo version)"""
        try:
            task = request.get("task", "")
            agent_configs = request.get("agents", [])
            
            print(f"🚀 Starting coordination for session {session_id}")
            print(f"📋 Task: {task}")
            
            if session_id in active_connections:
                # Initialize session if needed
                if session_id not in sessions:
                    sessions[session_id] = {"media_files": []}
                
                media_files = sessions[session_id].get("media_files", [])
                
                # Send coordination started
                await active_connections[session_id].send_text(json.dumps({
                    "type": "coordination_started",
                    "task": task,
                    "agents": ["analyst", "researcher"],
                    "media_files": media_files
                }))
                
                # Create background task for demo coordination
                asyncio.create_task(run_demo_coordination(session_id, task, media_files))
            
            return {"status": "success", "message": "Demo coordination started"}
            
        except Exception as e:
            print(f"❌ Coordination error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def run_demo_coordination(session_id: str, task: str, media_files: List[Dict]):
        """Run demo coordination sequence"""
        if session_id not in active_connections:
            return
        
        ws = active_connections[session_id]
        
        try:
            # Agent initialization
            await asyncio.sleep(0.5)
            await ws.send_text(json.dumps({
                "type": "agent_status_update",
                "agent_id": "analyst", 
                "status": "working"
            }))
            
            await asyncio.sleep(0.3)
            await ws.send_text(json.dumps({
                "type": "agent_status_update",
                "agent_id": "researcher",
                "status": "working" 
            }))
            
            # Analyst thinking
            await asyncio.sleep(1)
            await ws.send_text(json.dumps({
                "type": "agent_content_update",
                "agent_id": "analyst",
                "content": f"🤔 Analyzing task: '{task}'",
                "content_type": "thinking",
                "timestamp": datetime.now().isoformat()
            }))
            
            await asyncio.sleep(1.5)
            await ws.send_text(json.dumps({
                "type": "agent_content_update", 
                "agent_id": "analyst",
                "content": "Breaking down the problem into key components...",
                "content_type": "thinking",
                "timestamp": datetime.now().isoformat()
            }))
            
            # Media file awareness
            if media_files:
                await asyncio.sleep(1)
                await ws.send_text(json.dumps({
                    "type": "agent_content_update",
                    "agent_id": "analyst",
                    "content": f"📎 I notice {len(media_files)} media file(s) attached to this task.",
                    "content_type": "thinking",
                    "timestamp": datetime.now().isoformat()
                }))
            
            # Researcher activity
            await asyncio.sleep(1)
            await ws.send_text(json.dumps({
                "type": "agent_content_update",
                "agent_id": "researcher",
                "content": "📚 Gathering relevant background information...",
                "content_type": "thinking",
                "timestamp": datetime.now().isoformat()
            }))
            
            await asyncio.sleep(2)
            await ws.send_text(json.dumps({
                "type": "agent_content_update",
                "agent_id": "researcher", 
                "content": "🔍 Cross-referencing current trends and best practices.",
                "content_type": "thinking",
                "timestamp": datetime.now().isoformat()
            }))
            
            # Tool usage simulation
            await asyncio.sleep(1)
            await ws.send_text(json.dumps({
                "type": "agent_content_update",
                "agent_id": "analyst",
                "content": "🔧 Using analysis tools to evaluate the request...",
                "content_type": "tool",
                "timestamp": datetime.now().isoformat()
            }))
            
            # Orchestrator events
            await asyncio.sleep(1)
            await ws.send_text(json.dumps({
                "type": "orchestrator_event",
                "event": "📊 Agents are collaborating on analysis",
                "timestamp": datetime.now().isoformat()
            }))
            
            # Final coordination
            await asyncio.sleep(2)
            await ws.send_text(json.dumps({
                "type": "agent_content_update",
                "agent_id": "analyst",
                "content": "💡 Providing comprehensive analysis based on available information and research.",
                "content_type": "presentation",
                "timestamp": datetime.now().isoformat()
            }))
            
            # Completion
            await asyncio.sleep(1)
            await ws.send_text(json.dumps({
                "type": "agent_status_update",
                "agent_id": "analyst",
                "status": "completed"
            }))
            
            await ws.send_text(json.dumps({
                "type": "agent_status_update", 
                "agent_id": "researcher",
                "status": "completed"
            }))
            
            await ws.send_text(json.dumps({
                "type": "coordination_completed",
                "status": "completed"
            }))
            
            print(f"✅ Demo coordination completed for {session_id}")
            
        except Exception as e:
            print(f"❌ Demo coordination error: {e}")
    
    @app.get("/api/sessions/{session_id}/status")
    async def get_session_status(session_id: str):
        """Get session status"""
        if session_id in sessions:
            return {
                "session_id": session_id,
                "status": "active",
                "media_files": sessions[session_id].get("media_files", [])
            }
        else:
            return {
                "session_id": session_id,
                "status": "new",
                "media_files": []
            }
    
    @app.get("/api/health")
    async def health_check():
        """Health check endpoint"""
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "active_sessions": len(sessions),
            "active_connections": len(active_connections)
        }
    
    # Create directories
    Path("web_uploads").mkdir(exist_ok=True)
    Path("web_uploads/thumbnails").mkdir(exist_ok=True)
    
    # Serve static files
    app.mount("/media", StaticFiles(directory="web_uploads"), name="media")
    
    return app

def main():
    print("🚀 MassGen Studio Phase 1 Demo Backend")
    print("=" * 50)
    print("✅ Standalone backend (no MassGen dependencies)")
    print("✅ WebSocket streaming support") 
    print("✅ File upload and processing")
    print("✅ Demo coordination sequence")
    print("=" * 50)
    
    print("🌐 Backend: http://127.0.0.1:8000")
    print("📚 API Docs: http://127.0.0.1:8000/docs")
    print("🔗 WebSocket: ws://127.0.0.1:8000/ws/{session_id}")
    print("\n💡 Start React frontend: cd massgen-web && npm start")
    print("🎯 Frontend: http://localhost:3000")
    print("\nStarting server...\n")
    
    app = create_demo_app()
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="info"
    )

if __name__ == "__main__":
    main()