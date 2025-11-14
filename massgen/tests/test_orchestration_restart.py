#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for orchestration restart feature.
"""

import os
import sys

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def test_coordination_config_restart_params():
    """Test that CoordinationConfig has restart parameters."""
    from massgen.agent_config import CoordinationConfig

    config = CoordinationConfig()
    assert hasattr(config, "max_orchestration_restarts")
    assert config.max_orchestration_restarts == 0  # Default


def test_agent_config_debug_final_answer():
    """Test that AgentConfig has debug_final_answer parameter."""
    from massgen.agent_config import AgentConfig

    config = AgentConfig()
    assert hasattr(config, "debug_final_answer")
    assert config.debug_final_answer is None  # Default


def test_post_evaluation_toolkit_import():
    """Test that PostEvaluationToolkit can be imported."""
    from massgen.tool.workflow_toolkits import PostEvaluationToolkit

    assert PostEvaluationToolkit is not None


def test_post_evaluation_tools_function():
    """Test that get_post_evaluation_tools function exists."""
    from massgen.tool import get_post_evaluation_tools

    tools = get_post_evaluation_tools()
    assert len(tools) == 2
    assert tools[0]["function"]["name"] == "submit"
    assert tools[1]["function"]["name"] == "restart_orchestration"


def test_submit_tool_schema():
    """Test submit tool has correct schema."""
    from massgen.tool import get_post_evaluation_tools

    tools = get_post_evaluation_tools()
    submit_tool = tools[0]

    assert submit_tool["function"]["name"] == "submit"
    assert "confirmed" in submit_tool["function"]["parameters"]["properties"]
    assert submit_tool["function"]["parameters"]["properties"]["confirmed"]["enum"] == [True]


def test_restart_orchestration_tool_schema():
    """Test restart_orchestration tool has correct schema."""
    from massgen.tool import get_post_evaluation_tools

    tools = get_post_evaluation_tools()
    restart_tool = tools[1]

    assert restart_tool["function"]["name"] == "restart_orchestration"
    params = restart_tool["function"]["parameters"]["properties"]
    assert "reason" in params
    assert "instructions" in params
    assert set(restart_tool["function"]["parameters"]["required"]) == {"reason", "instructions"}


def test_message_templates_post_evaluation():
    """Test that MessageTemplates has post-evaluation methods."""
    from massgen.message_templates import MessageTemplates

    templates = MessageTemplates()
    assert hasattr(templates, "format_restart_context")

    # Test post-evaluation section
    from massgen.system_prompt_sections import PostEvaluationSection

    post_eval_section = PostEvaluationSection()
    post_eval_msg = post_eval_section.build_content()
    assert isinstance(post_eval_msg, str)
    assert "Post-Presentation Evaluation" in post_eval_msg

    restart_context = templates.format_restart_context("test reason", "test instructions")
    assert isinstance(restart_context, str)
    assert "PREVIOUS ATTEMPT FEEDBACK" in restart_context


def test_orchestrator_restart_state():
    """Test that Orchestrator has restart state tracking."""
    from massgen.agent_config import AgentConfig, CoordinationConfig
    from massgen.orchestrator import Orchestrator

    config = AgentConfig()
    config.coordination_config = CoordinationConfig(max_orchestration_restarts=2)

    orchestrator = Orchestrator(agents={}, config=config)

    assert hasattr(orchestrator, "current_attempt")
    assert hasattr(orchestrator, "max_attempts")
    assert hasattr(orchestrator, "restart_pending")
    assert hasattr(orchestrator, "restart_reason")
    assert hasattr(orchestrator, "restart_instructions")

    assert orchestrator.current_attempt == 0
    assert orchestrator.max_attempts == 3  # 1 + 2 restarts
    assert orchestrator.restart_pending is False


def test_orchestrator_post_evaluate_method():
    """Test that Orchestrator has post_evaluate_answer method."""
    import inspect

    from massgen.orchestrator import Orchestrator

    assert hasattr(Orchestrator, "post_evaluate_answer")
    sig = inspect.signature(Orchestrator.post_evaluate_answer)
    assert "selected_agent_id" in sig.parameters
    assert "final_answer" in sig.parameters


def test_orchestrator_handle_restart_method():
    """Test that Orchestrator has handle_restart method."""
    from massgen.orchestrator import Orchestrator

    assert hasattr(Orchestrator, "handle_restart")


def test_handle_restart_resets_state():
    """Test that handle_restart resets orchestrator state."""
    from massgen.agent_config import AgentConfig, CoordinationConfig
    from massgen.orchestrator import Orchestrator

    config = AgentConfig()
    config.coordination_config = CoordinationConfig(max_orchestration_restarts=2)

    # Initialize with empty agents dict (simpler for testing)
    orchestrator = Orchestrator(agents={}, config=config)

    # Simulate state after first attempt
    orchestrator.current_attempt = 0
    orchestrator.restart_reason = "test reason"
    orchestrator.restart_instructions = "test instructions"
    orchestrator.workflow_phase = "presenting"
    orchestrator._selected_agent = "agent1"
    orchestrator._final_presentation_content = "some content"

    # Call handle_restart
    orchestrator.handle_restart()

    # Verify state reset
    assert orchestrator.current_attempt == 1
    assert orchestrator.workflow_phase == "idle"
    assert orchestrator._selected_agent is None
    assert orchestrator._final_presentation_content is None
    # Restart reason/instructions should be preserved for next attempt
    assert orchestrator.restart_reason == "test reason"
    assert orchestrator.restart_instructions == "test instructions"


def test_base_display_restart_methods():
    """Test that BaseDisplay has restart abstract methods."""
    import inspect

    from massgen.frontend.displays.base_display import BaseDisplay

    abstract_methods = {name for name, method in inspect.getmembers(BaseDisplay, predicate=inspect.isfunction) if getattr(method, "__isabstractmethod__", False)}

    assert "show_post_evaluation_content" in abstract_methods
    assert "show_restart_banner" in abstract_methods
    assert "show_restart_context_panel" in abstract_methods


@pytest.mark.asyncio
async def test_post_evaluation_tools_api_formats():
    """Test post-evaluation tools work with different API formats."""
    from massgen.tool import get_post_evaluation_tools

    # Test chat_completions format (default)
    tools_chat = get_post_evaluation_tools(api_format="chat_completions")
    assert len(tools_chat) == 2
    assert tools_chat[0]["type"] == "function"

    # Test claude format
    tools_claude = get_post_evaluation_tools(api_format="claude")
    assert len(tools_claude) == 2
    assert "input_schema" in tools_claude[0]

    # Test response format
    tools_response = get_post_evaluation_tools(api_format="response")
    assert len(tools_response) == 2
    assert tools_response[0]["type"] == "function"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
