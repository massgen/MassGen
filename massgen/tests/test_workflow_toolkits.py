#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for workflow toolkits implementation.
"""

import os
import sys

from massgen.tool.workflow_toolkits import (
    NewAnswerToolkit,
    VoteToolkit,
    get_workflow_tools,
)

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_workflow_toolkit_basic():
    """Test basic workflow toolkit functionality."""
    print("=" * 60)
    print("Testing Workflow Toolkit System")
    print("=" * 60)

    # 1. Test creating toolkits
    print("\n1. Creating workflow toolkits...")
    new_answer_toolkit = NewAnswerToolkit()
    vote_toolkit = VoteToolkit(valid_agent_ids=["agent1", "agent2"])
    
    print(f"   NewAnswerToolkit ID: {new_answer_toolkit.toolkit_id}")
    print(f"   VoteToolkit ID: {vote_toolkit.toolkit_id}")
    print("   ✓ Toolkits created successfully")

    # 2. Test getting workflow tools with different formats
    print("\n2. Testing workflow tools with different API formats...")

    # Test Chat Completions format
    agent_ids = ["agent1", "agent2", "agent3"]
    chat_tools = get_workflow_tools(
        valid_agent_ids=agent_ids,
        api_format="chat_completions",
    )
    print(f"   Chat Completions format: {len(chat_tools)} tools")
    for tool in chat_tools:
        if "function" in tool:
            print(f"     - {tool['function']['name']}")

    # Test Claude format
    claude_tools = get_workflow_tools(
        valid_agent_ids=agent_ids,
        api_format="claude",
    )
    print(f"   Claude format: {len(claude_tools)} tools")
    for tool in claude_tools:
        print(f"     - {tool['name']}")

    # Test Response API format
    response_tools = get_workflow_tools(
        valid_agent_ids=agent_ids,
        api_format="response",
    )
    print(f"   Response API format: {len(response_tools)} tools")
    for tool in response_tools:
        if "function" in tool:
            print(f"     - {tool['function']['name']}")

    # 3. Test vote tool with valid agent IDs
    print("\n3. Testing vote tool with agent ID constraints...")
    vote_toolkit = VoteToolkit(valid_agent_ids=["agent1", "agent2"])
    vote_tools = vote_toolkit.get_tools({"api_format": "chat_completions"})

    vote_tool = vote_tools[0]
    agent_id_param = vote_tool["function"]["parameters"]["properties"]["agent_id"]

    if "enum" in agent_id_param:
        print(f"   Valid agent IDs in enum: {agent_id_param['enum']}")
        assert agent_id_param["enum"] == ["agent1", "agent2"], "Incorrect enum values"
        print("   ✓ Agent ID constraints working correctly")

    # 4. Test is_enabled functionality
    print("\n4. Testing is_enabled functionality...")
    
    config_enabled = {"enable_workflow_tools": True}
    config_disabled = {"enable_workflow_tools": False}
    
    assert new_answer_toolkit.is_enabled(config_enabled), "Should be enabled"
    assert not new_answer_toolkit.is_enabled(config_disabled), "Should be disabled"
    assert vote_toolkit.is_enabled(config_enabled), "Should be enabled"
    assert not vote_toolkit.is_enabled(config_disabled), "Should be disabled"
    print("   ✓ is_enabled working correctly")

    # 5. Test template overrides
    print("\n5. Testing template overrides...")
    
    custom_tool = {
        "type": "function",
        "function": {
            "name": "custom_new_answer",
            "description": "Custom description",
            "parameters": {
                "type": "object",
                "properties": {
                    "custom_field": {"type": "string"}
                },
                "required": ["custom_field"]
            }
        }
    }
    
    template_overrides = {
        "new_answer_tool": custom_tool
    }
    
    custom_toolkit = NewAnswerToolkit(template_overrides=template_overrides)
    custom_tools = custom_toolkit.get_tools({"api_format": "chat_completions"})
    
    assert len(custom_tools) == 1, "Should have one tool"
    assert custom_tools[0]["function"]["name"] == "custom_new_answer", "Should use custom template"
    print("   ✓ Template overrides working correctly")

    print("\n✅ All tests passed!")


def test_workflow_tools_integration():
    """Test workflow tools integration."""
    print("\n" + "=" * 60)
    print("Testing Workflow Tools Integration")
    print("=" * 60)

    # Test that all formats produce valid tool definitions
    print("\n1. Testing tool definition validity...")
    
    agent_ids = ["agent1", "agent2"]
    
    for api_format in ["chat_completions", "claude", "response"]:
        tools = get_workflow_tools(
            valid_agent_ids=agent_ids,
            api_format=api_format
        )
        
        assert len(tools) == 2, f"Should have 2 tools for {api_format}"
        
        for tool in tools:
            if api_format == "claude":
                assert "name" in tool, f"Claude tool missing name"
                assert "description" in tool, f"Claude tool missing description"
                assert "input_schema" in tool, f"Claude tool missing input_schema"
            else:
                assert "type" in tool, f"{api_format} tool missing type"
                assert "function" in tool, f"{api_format} tool missing function"
                assert "name" in tool["function"], f"{api_format} tool missing function name"
                assert "parameters" in tool["function"], f"{api_format} tool missing parameters"
        
        print(f"   ✓ {api_format} format produces valid tools")

    # Test dynamic agent ID updates
    print("\n2. Testing dynamic agent ID updates...")
    
    vote_toolkit = VoteToolkit()
    
    # Initially no agent IDs
    tools = vote_toolkit.get_tools({"api_format": "chat_completions"})
    vote_tool = tools[0]
    agent_param = vote_tool["function"]["parameters"]["properties"]["agent_id"]
    assert "enum" not in agent_param, "Should not have enum without agent IDs"
    
    # Set agent IDs
    vote_toolkit.set_valid_agent_ids(["agent1", "agent2", "agent3"])
    tools = vote_toolkit.get_tools({"api_format": "chat_completions"})
    vote_tool = tools[0]
    agent_param = vote_tool["function"]["parameters"]["properties"]["agent_id"]
    assert "enum" in agent_param, "Should have enum with agent IDs"
    assert agent_param["enum"] == ["agent1", "agent2", "agent3"], "Should have correct agent IDs"
    
    print("   ✓ Dynamic agent ID updates working correctly")

    print("\n✅ Integration tests passed!")


if __name__ == "__main__":
    test_workflow_toolkit_basic()
    test_workflow_tools_integration()
    
    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 60)