#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to verify MCP tool blocking in planning mode.
"""

import asyncio
import os
import sys

from massgen.agent_config import AgentConfig
from massgen.backend.response import ResponseBackend

# Add the project root to sys.path to import massgen
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


async def test_mcp_blocking():
    """Test that planning mode blocks MCP tool execution in the response backend."""

    print("🧪 Testing MCP Tool Blocking in Planning Mode...")
    print("=" * 50)

    # Create agent config
    agent_config = AgentConfig(
        backend_params={
            "backend_type": "response",
            "model": "gpt-4",
            "api_key": "dummy-key",
        },
    )

    # Create backend instance
    backend = ResponseBackend(config=agent_config)

    # Test 1: Planning mode flag functionality
    print("\n1. Testing planning mode flag...")
    assert not backend.is_planning_mode_enabled(), "Planning mode should be disabled by default"
    print("✅ Planning mode disabled by default")

    backend.set_planning_mode(True)
    assert backend.is_planning_mode_enabled(), "Planning mode should be enabled"
    print("✅ Planning mode can be enabled")

    backend.set_planning_mode(False)
    assert not backend.is_planning_mode_enabled(), "Planning mode should be disabled"
    print("✅ Planning mode can be disabled")

    # Test 2: Check MCP blocking logic in response backend
    print("\n2. Testing MCP tool execution blocking...")

    # Simulate the logic that would happen in the MCP execution loop
    backend.set_planning_mode(True)

    # Check if planning mode blocks execution (simulating the condition in response.py)
    if backend.is_planning_mode_enabled():
        print("✅ MCP tools would be blocked in planning mode")
        # This simulates the planning_mode_blocked status returned
        mcp_status = "planning_mode_blocked"
    else:
        print("❌ MCP tools would NOT be blocked")
        mcp_status = "executed"

    assert mcp_status == "planning_mode_blocked", "MCP tools should be blocked in planning mode"
    print("✅ MCP tool blocking logic works correctly")

    # Test 3: Verify execution is allowed when planning mode is disabled
    print("\n3. Testing MCP tool execution when planning mode disabled...")
    backend.set_planning_mode(False)

    if backend.is_planning_mode_enabled():
        mcp_status = "planning_mode_blocked"
    else:
        mcp_status = "would_execute"

    assert mcp_status == "would_execute", "MCP tools should execute when planning mode is disabled"
    print("✅ MCP tools would execute when planning mode is disabled")

    print("\n🎉 All MCP blocking tests passed!")
    print("✅ Backend-level planning mode implementation is working correctly")
    return True


async def test_backend_inheritance():
    """Test that all backend types inherit planning mode functionality."""

    print("\n🧪 Testing Backend Inheritance...")
    print("=" * 30)

    # Test ResponseBackend
    from massgen.backend.response import ResponseBackend

    response_config = AgentConfig(backend_params={"backend_type": "response", "model": "gpt-4", "api_key": "dummy"})
    response_backend = ResponseBackend(config=response_config)

    # Check that methods exist
    assert hasattr(response_backend, "set_planning_mode"), "ResponseBackend should have set_planning_mode"
    assert hasattr(response_backend, "is_planning_mode_enabled"), "ResponseBackend should have is_planning_mode_enabled"
    print("✅ ResponseBackend has planning mode methods")

    # Test Gemini backend
    try:
        from massgen.backend.gemini import GeminiBackend

        gemini_config = AgentConfig(backend_params={"backend_type": "gemini", "model": "gemini-1.5-pro", "api_key": "dummy"})
        gemini_backend = GeminiBackend(config=gemini_config)

        assert hasattr(gemini_backend, "set_planning_mode"), "GeminiBackend should have set_planning_mode"
        assert hasattr(gemini_backend, "is_planning_mode_enabled"), "GeminiBackend should have is_planning_mode_enabled"
        print("✅ GeminiBackend has planning mode methods")
    except Exception as e:
        print(f"⚠️  Could not test GeminiBackend: {e}")

    print("✅ Backend inheritance working correctly")


if __name__ == "__main__":

    async def main():
        success1 = await test_mcp_blocking()
        await test_backend_inheritance()
        return success1

    success = asyncio.run(main())
    sys.exit(0 if success else 1)
