#!/usr/bin/env python3
"""
Test script for MassGen Web UI functionality.
"""

import sys
import os
from pathlib import Path

# Add massgen to path
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Test that all web UI modules can be imported."""
    try:
        from massgen.web_ui import create_app, api_bp, socketio
        print("✓ Web UI modules imported successfully")
        return True
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False

def test_app_creation():
    """Test that the Flask app can be created."""
    try:
        from massgen.web_ui import create_app
        app = create_app()
        print("✓ Flask app created successfully")
        return True
    except Exception as e:
        print(f"✗ App creation error: {e}")
        return False

def test_api_routes():
    """Test that API routes are registered."""
    try:
        from massgen.web_ui import create_app
        app = create_app()
        
        with app.app_context():
            # Check if routes exist
            routes = [str(rule) for rule in app.url_map.iter_rules()]
            expected_routes = [
                '/api/health',
                '/api/upload-config',
                '/api/create-session',
                '/api/start-coordination',
                '/api/sample-configs'
            ]
            
            for route in expected_routes:
                if route in routes:
                    print(f"✓ Route {route} registered")
                else:
                    print(f"✗ Route {route} missing")
                    return False
                    
        return True
    except Exception as e:
        print(f"✗ Route test error: {e}")
        return False

def main():
    """Run all tests."""
    print("🧪 Testing MassGen Web UI")
    print("=" * 40)
    
    tests = [
        ("Import test", test_imports),
        ("App creation test", test_app_creation),
        ("API routes test", test_api_routes)
    ]
    
    passed = 0
    for test_name, test_func in tests:
        print(f"\n{test_name}:")
        if test_func():
            passed += 1
    
    print(f"\n{'='*40}")
    print(f"Tests passed: {passed}/{len(tests)}")
    
    if passed == len(tests):
        print("🎉 All tests passed!")
        return 0
    else:
        print("❌ Some tests failed!")
        return 1

if __name__ == '__main__':
    sys.exit(main())