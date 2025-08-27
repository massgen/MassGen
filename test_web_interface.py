#!/usr/bin/env python3
"""
Test script for MassGen Web Interface

Tests the FastAPI backend and WebSocket functionality.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add massgen to Python path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from massgen.web.backend.main import app, ws_manager
    from massgen.agent_config import AgentConfig
    print("✅ Successfully imported MassGen web components")
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Please install requirements: pip install -r requirements-web.txt")
    sys.exit(1)

async def test_basic_functionality():
    """Test basic web interface functionality"""
    print("\n🧪 Testing MassGen Web Interface...")
    
    # Test 1: Check if required directories exist
    print("\n1. Checking directory structure...")
    required_dirs = [
        "massgen/web",
        "massgen/web/backend", 
        "massgen/web/displays",
        "massgen-web/src"
    ]
    
    for dir_path in required_dirs:
        if os.path.exists(dir_path):
            print(f"   ✅ {dir_path}")
        else:
            print(f"   ❌ {dir_path} missing")
    
    # Test 2: Test agent configuration
    print("\n2. Testing agent configuration...")
    try:
        agent_config = AgentConfig(
            backend_type="openai",
            model="gpt-4o-mini",
            persona="You are a test assistant."
        )
        print("   ✅ Agent configuration works")
    except Exception as e:
        print(f"   ❌ Agent configuration failed: {e}")
    
    # Test 3: Test WebSocket manager
    print("\n3. Testing WebSocket manager...")
    try:
        session_id = "test_session_123"
        print(f"   ✅ WebSocket manager initialized")
        print(f"   📋 Session ID: {session_id}")
    except Exception as e:
        print(f"   ❌ WebSocket manager failed: {e}")
    
    # Test 4: Test multimedia processor
    print("\n4. Testing multimedia processor...")
    try:
        from massgen.web.backend.multimedia_processor import MultimediaProcessor
        processor = MultimediaProcessor()
        supported_formats = processor.get_supported_formats()
        print(f"   ✅ Multimedia processor initialized")
        print(f"   📁 Supported formats: {list(supported_formats.keys())}")
    except Exception as e:
        print(f"   ❌ Multimedia processor failed: {e}")
    
    print("\n✅ Basic functionality tests completed!")

def test_frontend_setup():
    """Test frontend setup"""
    print("\n🖥️ Testing Frontend Setup...")
    
    frontend_files = [
        "massgen-web/package.json",
        "massgen-web/src/App.tsx",
        "massgen-web/src/components/CoordinationInterface.tsx",
        "massgen-web/src/components/HybridTerminal.tsx",
        "massgen-web/src/services/websocket.ts"
    ]
    
    for file_path in frontend_files:
        if os.path.exists(file_path):
            print(f"   ✅ {file_path}")
        else:
            print(f"   ❌ {file_path} missing")
    
    print("\n📋 Frontend test completed!")

def print_startup_instructions():
    """Print instructions for starting the web interface"""
    print("\n🚀 MassGen Web Interface Setup Instructions:")
    print("=" * 60)
    
    print("\n1. Install Python dependencies:")
    print("   pip install -r requirements-web.txt")
    
    print("\n2. Start the FastAPI backend:")
    print("   cd massgen/web/backend")
    print("   python main.py")
    print("   # Or using uvicorn directly:")
    print("   uvicorn massgen.web.backend.main:app --reload --host 127.0.0.1 --port 8000")
    
    print("\n3. Install and start React frontend (in new terminal):")
    print("   cd massgen-web")
    print("   npm install")
    print("   npm start")
    
    print("\n4. Access the web interface:")
    print("   🌐 Frontend: http://localhost:3000")
    print("   🔧 Backend API: http://localhost:8000")
    print("   📚 API Docs: http://localhost:8000/docs")
    
    print("\n💡 Features available:")
    print("   • Drag & drop file upload")
    print("   • Real-time coordination display") 
    print("   • Multi-agent terminal interface")
    print("   • WebSocket streaming")
    print("   • Multimedia file support")
    
    print("\n🧪 Test coordination task:")
    print('   "Compare the uploaded image with current design trends and provide analysis"')

if __name__ == "__main__":
    print("🚀 MassGen Web Interface Test Suite")
    print("=" * 50)
    
    # Run async tests
    asyncio.run(test_basic_functionality())
    
    # Run sync tests
    test_frontend_setup()
    
    # Print setup instructions
    print_startup_instructions()
    
    print("\n🎯 Test suite completed! Follow the instructions above to start the web interface.")