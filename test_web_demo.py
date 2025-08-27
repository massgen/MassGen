#!/usr/bin/env python3
"""
Test script to demonstrate MassGen Studio functionality
"""

import requests
import time

def test_web_interface():
    """Test the web interface endpoints"""
    print("🧪 Testing MassGen Studio Web Interface")
    print("=" * 50)
    
    base_url = "http://127.0.0.1:8000"
    
    # Test health endpoint
    try:
        response = requests.get(f"{base_url}/api/health")
        if response.status_code == 200:
            health_data = response.json()
            print(f"✅ Backend Health: {health_data['status']}")
            print(f"📊 Active connections: {health_data['active_connections']}")
            print(f"📁 Active sessions: {health_data['active_sessions']}")
        else:
            print(f"❌ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False
    
    # Test session status
    session_id = "test_session_123"
    try:
        response = requests.get(f"{base_url}/api/sessions/{session_id}/status")
        if response.status_code == 200:
            session_data = response.json()
            print(f"✅ Session endpoint working")
            print(f"📋 Session: {session_data['session_id']}")
            print(f"🟢 Status: {session_data['status']}")
        else:
            print(f"⚠️ Session endpoint: {response.status_code}")
    except Exception as e:
        print(f"❌ Session test failed: {e}")
    
    return True

def print_usage_guide():
    """Print usage guide for the web interface"""
    print("\n🚀 MassGen Studio Usage Guide")
    print("=" * 40)
    print("\n📱 Access Points:")
    print("   🌐 Frontend: http://localhost:3000")
    print("   🔧 Backend:  http://127.0.0.1:8000")
    print("   📚 API Docs: http://127.0.0.1:8000/docs")
    
    print("\n🎯 How to Use:")
    print("   1. Open http://localhost:3000 in your browser")
    print("   2. Wait for 🟢 Connected status in top right")
    print("   3. Enter a task in the left panel:")
    print("      Example: 'Analyze current trends in AI development'")
    print("   4. Optional: Upload an image file via drag & drop")
    print("   5. Click '🚀 Start Coordination'")
    print("   6. Watch real-time coordination in the terminal")
    
    print("\n💡 What You'll See:")
    print("   • Left Panel: Task input and file upload")
    print("   • Center: Terminal with coordination logs")
    print("   • Right Panel: Agent status and events")
    print("   • Real-time updates via WebSocket")
    print("   • Demo agents: 'analyst' and 'researcher'")
    
    print("\n🔧 Features Demonstrated:")
    print("   ✅ Real-time WebSocket communication")
    print("   ✅ File upload with multimedia processing")
    print("   ✅ Multi-agent coordination simulation")
    print("   ✅ Responsive web interface")
    print("   ✅ Terminal-style coordination display")
    print("   ✅ Agent status monitoring")
    
    print("\n🐛 Troubleshooting:")
    print("   • Red connection status: Backend may not be running")
    print("   • Frontend not loading: Check npm start output")
    print("   • Upload errors: Check backend console for errors")
    print("   • WebSocket issues: Check browser developer tools")

if __name__ == "__main__":
    success = test_web_interface()
    print_usage_guide()
    
    if success:
        print("\n✅ MassGen Studio is ready for testing!")
        print("🎯 Open http://localhost:3000 to start coordinating")
    else:
        print("\n❌ Setup issues detected. Check backend status.")