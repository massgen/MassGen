#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for workflow toolkits implementation.
"""

import os
import sys

from massgen.toolkits import toolkit_registry
from massgen.toolkits.workflow_toolkits import (
    NewAnswerToolkit,
    VoteToolkit,
    get_workflow_tools,
    register_workflow_toolkits,
)

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_workflow_toolkit_registration():
    """Test workflow toolkit registration and retrieval."""
    print("=" * 60)
    print("Testing Workflow Toolkit System")
    print("=" * 60)

    # 1. Register workflow toolkits
    print("\n1. Registering workflow toolkits...")
    register_workflow_toolkits()

    # Check registration
    all_toolkits = toolkit_registry.list_all_toolkits()
    print(f"   All registered toolkits: {list(all_toolkits.keys())}")

    # Verify workflow toolkits are registered
    assert "new_answer" in all_toolkits, "new_answer toolkit not registered"
    assert "vote" in all_toolkits, "vote toolkit not registered"
    print("   ✓ Workflow toolkits registered successfully")

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

    # 4. Test provider associations
    print("\n4. Testing provider associations...")
    openai_toolkits = toolkit_registry.get_provider_toolkits("openai")
    print(f"   OpenAI provider toolkits: {openai_toolkits}")

    claude_toolkits = toolkit_registry.get_provider_toolkits("claude")
    print(f"   Claude provider toolkits: {claude_toolkits}")

    # Both should have workflow tools
    assert "new_answer" in openai_toolkits, "OpenAI missing new_answer"
    assert "vote" in openai_toolkits, "OpenAI missing vote"
    assert "new_answer" in claude_toolkits, "Claude missing new_answer"
    assert "vote" in claude_toolkits, "Claude missing vote"
    print("   ✓ Provider associations correct")

    # 5. Test getting provider tools with config
    print("\n5. Testing provider tools retrieval with config...")
    config = {
        "enable_workflow_tools": True,
        "api_format": "chat_completions",
        "valid_agent_ids": ["agent1", "agent2", "agent3"],
    }

    provider_tools = toolkit_registry.get_provider_tools("openai", config)
    workflow_tool_names = []
    for tool in provider_tools:
        if "function" in tool:
            name = tool["function"]["name"]
            if name in ["new_answer", "vote"]:
                workflow_tool_names.append(name)

    print(f"   Found workflow tools: {workflow_tool_names}")
    assert "new_answer" in workflow_tool_names, "new_answer not in provider tools"
    assert "vote" in workflow_tool_names, "vote not in provider tools"
    print("   ✓ Provider tools retrieval working")

    # 6. Test disabling workflow tools
    print("\n6. Testing workflow tools can be disabled...")
    disabled_config = {
        "enable_workflow_tools": False,
        "api_format": "chat_completions",
    }

    new_answer_toolkit = NewAnswerToolkit()
    assert new_answer_toolkit.is_enabled(config) is True, "Should be enabled"
    assert new_answer_toolkit.is_enabled(disabled_config) is False, "Should be disabled"
    print("   ✓ Workflow tools can be disabled")

    print("\n" + "=" * 60)
    print("All workflow toolkit tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    test_workflow_toolkit_registration()
