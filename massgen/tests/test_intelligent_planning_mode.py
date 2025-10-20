# -*- coding: utf-8 -*-
"""
Test intelligent planning mode that analyzes questions for irreversibility.

This test verifies that the orchestrator can:
1. Analyze user questions to determine if they involve irreversible MCP operations
2. Automatically enable planning mode for irreversible operations (e.g., send Discord message)
3. Automatically disable planning mode for reversible operations (e.g., read Discord messages)
4. All analysis happens silently - users don't see the internal analysis
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from massgen.agent_config import AgentConfig
from massgen.backend.base import StreamChunk
from massgen.backend.response import ResponseBackend
from massgen.chat_agent import ConfigurableAgent
from massgen.orchestrator import Orchestrator

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture
def mock_backend():
    """Create a mock backend with planning mode support."""
    backend = MagicMock(spec=ResponseBackend)
    backend.set_planning_mode = MagicMock()
    backend.is_planning_mode_enabled = MagicMock(return_value=False)
    backend.stream_with_tools = AsyncMock()
    backend.filesystem_manager = None
    return backend


@pytest.fixture
def orchestrator_with_agents(mock_backend):
    """Create an orchestrator with mock agents."""
    # Create agent configs
    config1 = AgentConfig.create_openai_config(model="gpt-4")
    config2 = AgentConfig.create_openai_config(model="gpt-4")

    # Create agents with mock backends
    agent1 = ConfigurableAgent(config=config1, backend=mock_backend)
    agent2 = ConfigurableAgent(config=config2, backend=mock_backend)

    agents = {
        "agent1": agent1,
        "agent2": agent2,
    }

    # Create orchestrator
    orchestrator_config = AgentConfig.create_openai_config()
    orchestrator = Orchestrator(
        agents=agents,
        orchestrator_id="test_orchestrator",
        config=orchestrator_config,
    )

    return orchestrator, mock_backend


@pytest.mark.asyncio
async def test_irreversible_operation_enables_planning_mode(orchestrator_with_agents):
    """Test that irreversible operations (like sending Discord messages) enable planning mode."""
    orchestrator, mock_backend = orchestrator_with_agents

    # Mock the analysis to return YES (irreversible)
    async def mock_analysis_stream(*args, **kwargs):
        yield StreamChunk(type="content", content="YES")

    mock_backend.stream_with_tools = mock_analysis_stream

    # Test with a question about sending a Discord message
    user_question = "Send a message to the #general channel saying 'Hello everyone!'"
    conversation_context = {
        "current_message": user_question,
        "conversation_history": [],
        "full_messages": [{"role": "user", "content": user_question}],
    }

    # Run the analysis
    has_irreversible = await orchestrator._analyze_question_irreversibility(
        user_question,
        conversation_context,
    )

    # Verify that it detected irreversible operation
    assert has_irreversible is True, "Should detect sending Discord message as irreversible"


@pytest.mark.asyncio
async def test_reversible_operation_disables_planning_mode(orchestrator_with_agents):
    """Test that reversible operations (like reading Discord messages) disable planning mode."""
    orchestrator, mock_backend = orchestrator_with_agents

    # Mock the analysis to return NO (reversible)
    async def mock_analysis_stream(*args, **kwargs):
        yield StreamChunk(type="content", content="NO")

    mock_backend.stream_with_tools = mock_analysis_stream

    # Test with a question about reading Discord messages
    user_question = "Show me the last 10 messages from the #general channel"
    conversation_context = {
        "current_message": user_question,
        "conversation_history": [],
        "full_messages": [{"role": "user", "content": user_question}],
    }

    # Run the analysis
    has_irreversible = await orchestrator._analyze_question_irreversibility(
        user_question,
        conversation_context,
    )

    # Verify that it detected reversible operation
    assert has_irreversible is False, "Should detect reading Discord messages as reversible"


@pytest.mark.asyncio
async def test_planning_mode_set_on_all_agents(orchestrator_with_agents):
    """Test that planning mode is set on all agents during chat."""
    orchestrator, mock_backend = orchestrator_with_agents

    # Mock the analysis to return YES (irreversible)
    async def mock_analysis_stream(*args, **kwargs):
        yield StreamChunk(type="content", content="YES")

    mock_backend.stream_with_tools = mock_analysis_stream

    # Mock the coordination to avoid full execution
    async def mock_coordinate(*args, **kwargs):
        yield StreamChunk(type="content", content="Coordinated response")
        yield StreamChunk(type="done")

    with patch.object(orchestrator, "_coordinate_agents_with_timeout", mock_coordinate):
        # Simulate a chat interaction
        user_question = "Delete all files in the temp directory"
        messages = [{"role": "user", "content": user_question}]

        # Collect chunks
        chunks = []
        async for chunk in orchestrator.chat(messages):
            chunks.append(chunk)

        # Verify that set_planning_mode was called on the backend
        # It should be called twice (once for each agent)
        assert mock_backend.set_planning_mode.call_count == 2
        # Verify it was called with True (planning mode enabled)
        mock_backend.set_planning_mode.assert_called_with(True)


@pytest.mark.asyncio
async def test_error_defaults_to_safe_mode(orchestrator_with_agents):
    """Test that errors during analysis default to safe mode (planning enabled)."""
    orchestrator, mock_backend = orchestrator_with_agents

    # Mock the analysis to raise an error
    async def mock_analysis_error(*args, **kwargs):
        raise Exception("Analysis failed")

    mock_backend.stream_with_tools = mock_analysis_error

    # Test with any question
    user_question = "Test question"
    conversation_context = {
        "current_message": user_question,
        "conversation_history": [],
        "full_messages": [{"role": "user", "content": user_question}],
    }

    # Run the analysis
    has_irreversible = await orchestrator._analyze_question_irreversibility(
        user_question,
        conversation_context,
    )

    # Verify that it defaulted to safe mode (True = planning enabled)
    assert has_irreversible is True, "Should default to planning mode on error"


@pytest.mark.asyncio
async def test_analysis_uses_random_agent():
    """Test that the analysis randomly selects an available agent."""
    # Create multiple agents with different IDs
    agent_ids = ["agent1", "agent2", "agent3"]
    agents = {}

    for agent_id in agent_ids:
        backend = MagicMock(spec=ResponseBackend)
        backend.set_planning_mode = MagicMock()
        backend.filesystem_manager = None

        # Mock stream to return NO
        async def mock_stream(*args, **kwargs):
            yield StreamChunk(type="content", content="NO")

        backend.stream_with_tools = mock_stream

        config = AgentConfig.create_openai_config()
        agent = ConfigurableAgent(config=config, backend=backend)
        agents[agent_id] = agent

    orchestrator_config = AgentConfig.create_openai_config()
    orchestrator = Orchestrator(
        agents=agents,
        orchestrator_id="test_orchestrator",
        config=orchestrator_config,
    )

    # Run analysis multiple times to verify random selection
    user_question = "Test question"
    conversation_context = {
        "current_message": user_question,
        "conversation_history": [],
        "full_messages": [{"role": "user", "content": user_question}],
    }

    # Run analysis once
    result = await orchestrator._analyze_question_irreversibility(
        user_question,
        conversation_context,
    )

    # Just verify it completes without error
    # (Random selection is hard to test deterministically)
    assert result is False, "Should return False for NO response"


@pytest.mark.asyncio
async def test_mixed_responses_parsed_correctly(orchestrator_with_agents):
    """Test that YES/NO responses are parsed correctly even with extra text."""
    orchestrator, mock_backend = orchestrator_with_agents

    # Test with YES in mixed text
    async def mock_stream_yes(*args, **kwargs):
        yield StreamChunk(type="content", content="Based on my analysis, the answer is YES, this is irreversible.")

    mock_backend.stream_with_tools = mock_stream_yes

    user_question = "Test question"
    conversation_context = {
        "current_message": user_question,
        "conversation_history": [],
        "full_messages": [{"role": "user", "content": user_question}],
    }

    result = await orchestrator._analyze_question_irreversibility(user_question, conversation_context)
    assert result is True, "Should parse YES from mixed text"

    # Test with NO in mixed text
    async def mock_stream_no(*args, **kwargs):
        yield StreamChunk(type="content", content="After careful consideration, NO, this is reversible.")

    mock_backend.stream_with_tools = mock_stream_no

    result = await orchestrator._analyze_question_irreversibility(user_question, conversation_context)
    assert result is False, "Should parse NO from mixed text"


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
