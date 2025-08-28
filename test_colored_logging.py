#!/usr/bin/env python3
"""Test script for color-coded logging."""

from massgen.logger_config import (
    setup_logging,
    log_orchestrator_activity,
    log_agent_message,
    log_backend_activity,
    log_tool_call,
    log_coordination_step
)

def test_colored_logging():
    """Test all logging functions with colors."""
    # Enable debug mode
    setup_logging(debug=True)
    
    print("\n" + "="*60)
    print("Testing Color-Coded Debug Logging")
    print("="*60 + "\n")
    
    # Test orchestrator activities (Magenta)
    log_orchestrator_activity("main", "Starting orchestration", {"task": "test_task", "agents": 3})
    log_orchestrator_activity("main", "Allocating resources", {"memory": "2GB", "cpu": "4 cores"})
    
    # Test agent messages (Blue for SEND, Green for RECV)
    log_agent_message("agent_1", "SEND", {"role": "user", "content": "Please analyze this data"})
    log_agent_message("agent_1", "RECV", {"role": "assistant", "content": "Analysis complete. Found 3 patterns."})
    log_agent_message("agent_2", "SEND", {"role": "system", "content": "Initialize context"})
    log_agent_message("agent_2", "RECV", {"role": "assistant", "content": "Context initialized successfully"})
    
    # Test backend activities (Yellow)
    log_backend_activity("openai", "API call initiated", {"model": "gpt-4", "tokens": 1500})
    log_backend_activity("claude", "Connection established", {"endpoint": "api.anthropic.com", "version": "v1"})
    log_backend_activity("openai", "Response received", {"status": 200, "latency": "1.2s"})
    
    # Test tool calls (Light-black/Gray)
    log_tool_call("agent_1", "search_database", {"query": "SELECT * FROM users", "limit": 10})
    log_tool_call("agent_1", "search_database", {"query": "SELECT * FROM users", "limit": 10}, result={"rows": 10, "time": "0.05s"})
    
    # Test coordination steps (Red)
    log_coordination_step("Workflow initialized", {"workflow": "data_pipeline", "steps": 5})
    log_coordination_step("Step 1 completed", {"status": "success", "duration": "2.3s"})
    
    print("\n" + "="*60)
    print("Color Legend:")
    print("- Magenta: Orchestrator activities (🎯)")
    print("- Blue: Messages sent from orchestrator (📤)")
    print("- Green: Messages received from agents (📥)")
    print("- Yellow: Backend activities (⚙️)")
    print("- Light-black: Tool calls (🔧)")
    print("- Red: Coordination steps (🔄)")
    print("="*60 + "\n")

if __name__ == "__main__":
    test_colored_logging()