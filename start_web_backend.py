#!/usr/bin/env python3
"""
Standalone Web Backend Launcher for MassGen Studio

Launches the FastAPI backend with minimal dependencies for testing.
"""

import uvicorn
import os
import sys
from pathlib import Path

# Add current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

def create_minimal_backend():
    """Create a minimal FastAPI backend for testing"""
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
    from fastapi.staticfiles import StaticFiles
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    import json
    import uuid
    from datetime import datetime
    from typing import Dict, List, Optional
    import asyncio
    
    # Import multimedia processor
    from massgen.web.backend.multimedia_processor import MultimediaProcessor
    
    app = FastAPI(title="MassGen Studio Backend", version="1.0.0")
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Simple WebSocket manager
    active_connections: Dict[str, WebSocket] = {}
    multimedia_processor = MultimediaProcessor()
    
    @app.websocket("/ws/{session_id}")
    async def websocket_endpoint(websocket: WebSocket, session_id: str):
        await websocket.accept()
        active_connections[session_id] = websocket
        print(f"WebSocket connected: {session_id}")
        
        try:
            while True:
                data = await websocket.receive_text()
                message = json.loads(data)
                
                if message.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                    
        except WebSocketDisconnect:
            if session_id in active_connections:
                del active_connections[session_id]
            print(f"WebSocket disconnected: {session_id}")
    
    @app.post("/api/sessions/{session_id}/upload")
    async def upload_media(session_id: str, file: UploadFile = File(...)):
        """Upload media file"""
        try:
            # Generate unique filename
            file_id = str(uuid.uuid4())
            safe_filename = f"{file_id}_{file.filename}"
            file_path = multimedia_processor.storage_dir / safe_filename
            
            # Save file
            content = await file.read()
            with open(file_path, "wb") as f:
                f.write(content)
            
            # Process file
            metadata = {"file_size": len(content)}
            if file.content_type.startswith('image/'):
                result = await multimedia_processor.process_image(str(file_path))
                metadata.update(result)
            
            media_file = {
                "id": file_id,
                "filename": file.filename,
                "content_type": file.content_type,
                "file_path": str(file_path),
                "upload_timestamp": datetime.now().isoformat(),
                "metadata": metadata
            }
            
            # Notify WebSocket clients
            if session_id in active_connections:
                await active_connections[session_id].send_text(json.dumps({
                    "type": "media_uploaded",
                    "media_file": media_file
                }))
            
            return {"status": "success", "media_file": media_file}
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/sessions/{session_id}/start")
    async def start_coordination(session_id: str, request: dict):
        """Start coordination session (demo version)"""
        try:
            task = request.get("task", "")
            agents = request.get("agents", [])
            
            if session_id in active_connections:
                # Send demo coordination updates
                await active_connections[session_id].send_text(json.dumps({
                    "type": "coordination_started",
                    "task": task,
                    "agents": ["analyst", "researcher"],
                    "media_files": []
                }))
                
                # Simulate agent activity
                await asyncio.sleep(1)
                await active_connections[session_id].send_text(json.dumps({
                    "type": "agent_status_update", 
                    "agent_id": "analyst",
                    "status": "working"
                }))
                
                await asyncio.sleep(1)
                await active_connections[session_id].send_text(json.dumps({
                    "type": "agent_content_update",
                    "agent_id": "analyst", 
                    "content": f"🤔 Analyzing task: {task}",
                    "content_type": "thinking",
                    "timestamp": datetime.now().isoformat()
                }))
                
                await asyncio.sleep(2)
                await active_connections[session_id].send_text(json.dumps({
                    "type": "agent_content_update",
                    "agent_id": "researcher",
                    "content": "📚 Gathering relevant information and research data...",
                    "content_type": "thinking", 
                    "timestamp": datetime.now().isoformat()
                }))
                
                await asyncio.sleep(1)
                await active_connections[session_id].send_text(json.dumps({
                    "type": "coordination_completed",
                    "status": "completed"
                }))
            
            return {"status": "success", "message": "Demo coordination started"}
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/health")
    async def health_check():
        return {"status": "healthy", "timestamp": datetime.now().isoformat()}
    
    # Create upload directory
    Path("web_uploads").mkdir(exist_ok=True)
    
    # Serve static files
    app.mount("/media", StaticFiles(directory="web_uploads"), name="media")
    
    return app

if __name__ == "__main__":
    print("🚀 Starting MassGen Studio Backend (Demo Mode)")
    print("=" * 50)
    
    # Create directories
    Path("web_uploads").mkdir(exist_ok=True)
    Path("web_uploads/thumbnails").mkdir(exist_ok=True)
    
    print("✅ Upload directories created")
    print("🌐 Backend will be available at: http://127.0.0.1:8000")
    print("📚 API docs at: http://127.0.0.1:8000/docs")
    print("🔗 WebSocket endpoint: ws://127.0.0.1:8000/ws/SESSION_ID")
    print("\n💡 Start the React frontend with: cd massgen-web && npm start")
    print("\nStarting server...")
    
    # Create and run app
    app = create_minimal_backend()
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="info"
    )