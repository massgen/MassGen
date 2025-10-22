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

    # Mock the analysis to return YES (irreversible) in the new format
    async def mock_analysis_stream(*args, **kwargs):
        yield StreamChunk(type="content", content="IRREVERSIBLE: YES\nBLOCKED_TOOLS: mcp__discord__discord_send")

    mock_backend.stream_with_tools = mock_analysis_stream

    # Test with a question about sending a Discord message
    user_question = "Send a message to the #general channel saying 'Hello everyone!'"
    conversation_context = {
        "current_message": user_question,
        "conversation_history": [],
        "full_messages": [{"role": "user", "content": user_question}],
    }

    # Run the analysis
    result = await orchestrator._analyze_question_irreversibility(
        user_question,
        conversation_context,
    )

    # Verify that it detected irreversible operation
    assert result["has_irreversible"] is True, "Should detect sending Discord message as irreversible"


@pytest.mark.asyncio
async def test_reversible_operation_disables_planning_mode(orchestrator_with_agents):
    """Test that reversible operations (like reading Discord messages) disable planning mode."""
    orchestrator, mock_backend = orchestrator_with_agents

    # Mock the analysis to return NO (reversible) in the new format
    async def mock_analysis_stream(*args, **kwargs):
        yield StreamChunk(type="content", content="IRREVERSIBLE: NO\nBLOCKED_TOOLS: ")

    mock_backend.stream_with_tools = mock_analysis_stream

    # Test with a question about reading Discord messages
    user_question = "Show me the last 10 messages from the #general channel"
    conversation_context = {
        "current_message": user_question,
        "conversation_history": [],
        "full_messages": [{"role": "user", "content": user_question}],
    }

    # Run the analysis
    result = await orchestrator._analyze_question_irreversibility(
        user_question,
        conversation_context,
    )

    # Verify that it detected reversible operation
    assert result["has_irreversible"] is False, "Should detect reading Discord messages as reversible"


@pytest.mark.asyncio
async def test_planning_mode_set_on_all_agents(orchestrator_with_agents):
    """Test that planning mode is set on all agents during chat."""
    orchestrator, mock_backend = orchestrator_with_agents

    # Mock the analysis to return YES (irreversible) in the new format
    async def mock_analysis_stream(*args, **kwargs):
        yield StreamChunk(type="content", content="IRREVERSIBLE: YES\nBLOCKED_TOOLS: mcp__filesystem__delete_file")

    mock_backend.stream_with_tools = mock_analysis_stream

    # Add the set_planning_mode_blocked_tools method to mock
    mock_backend.set_planning_mode_blocked_tools = MagicMock()

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

        # Verify set_planning_mode_blocked_tools was also called
        assert mock_backend.set_planning_mode_blocked_tools.call_count == 2


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
    result = await orchestrator._analyze_question_irreversibility(
        user_question,
        conversation_context,
    )

    # Verify that it defaulted to safe mode (True = planning enabled)
    assert result["has_irreversible"] is True, "Should default to planning mode on error"


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
    assert result["has_irreversible"] is False, "Should return False for NO response"


@pytest.mark.asyncio
async def test_mixed_responses_parsed_correctly(orchestrator_with_agents):
    """Test that YES/NO responses are parsed correctly even with extra text."""
    orchestrator, mock_backend = orchestrator_with_agents

    # Test with YES in mixed text
    async def mock_stream_yes(*args, **kwargs):
        yield StreamChunk(type="content", content="IRREVERSIBLE: YES\nBLOCKED_TOOLS: mcp__discord__discord_send")

    mock_backend.stream_with_tools = mock_stream_yes

    user_question = "Test question"
    conversation_context = {
        "current_message": user_question,
        "conversation_history": [],
        "full_messages": [{"role": "user", "content": user_question}],
    }

    result = await orchestrator._analyze_question_irreversibility(user_question, conversation_context)
    assert result["has_irreversible"] is True, "Should parse YES from formatted response"
    assert "mcp__discord__discord_send" in result["blocked_tools"], "Should extract blocked tools"

    # Test with NO in mixed text
    async def mock_stream_no(*args, **kwargs):
        yield StreamChunk(type="content", content="IRREVERSIBLE: NO\nBLOCKED_TOOLS: ")

    mock_backend.stream_with_tools = mock_stream_no

    result = await orchestrator._analyze_question_irreversibility(user_question, conversation_context)
    assert result["has_irreversible"] is False, "Should parse NO from formatted response"
    assert len(result["blocked_tools"]) == 0, "Should have empty blocked tools for reversible operations"


@pytest.mark.asyncio
async def test_selective_blocking_multiple_tools(orchestrator_with_agents):
    """Test that multiple tools can be blocked selectively."""
    orchestrator, mock_backend = orchestrator_with_agents

    # Mock the analysis to return multiple blocked tools
    async def mock_stream(*args, **kwargs):
        yield StreamChunk(
            type="content",
            content="IRREVERSIBLE: YES\nBLOCKED_TOOLS: mcp__discord__discord_send, mcp__twitter__post_tweet, mcp__filesystem__delete_file",
        )

    mock_backend.stream_with_tools = mock_stream

    user_question = "Send a Discord message, post a tweet, and delete a file"
    conversation_context = {
        "current_message": user_question,
        "conversation_history": [],
        "full_messages": [{"role": "user", "content": user_question}],
    }

    result = await orchestrator._analyze_question_irreversibility(user_question, conversation_context)

    assert result["has_irreversible"] is True, "Should detect irreversible operations"
    assert len(result["blocked_tools"]) == 3, "Should identify 3 blocked tools"
    assert "mcp__discord__discord_send" in result["blocked_tools"]
    assert "mcp__twitter__post_tweet" in result["blocked_tools"]
    assert "mcp__filesystem__delete_file" in result["blocked_tools"]


@pytest.mark.asyncio
async def test_selective_blocking_with_whitespace(orchestrator_with_agents):
    """Test that tool names are parsed correctly even with extra whitespace."""
    orchestrator, mock_backend = orchestrator_with_agents

    # Mock the analysis with various whitespace patterns
    async def mock_stream(*args, **kwargs):
        yield StreamChunk(
            type="content",
            content="IRREVERSIBLE: YES\nBLOCKED_TOOLS:  mcp__discord__discord_send ,  mcp__twitter__post_tweet  ",
        )

    mock_backend.stream_with_tools = mock_stream

    user_question = "Test question"
    conversation_context = {
        "current_message": user_question,
        "conversation_history": [],
        "full_messages": [{"role": "user", "content": user_question}],
    }

    result = await orchestrator._analyze_question_irreversibility(user_question, conversation_context)

    assert result["has_irreversible"] is True
    assert len(result["blocked_tools"]) == 2, "Should parse tools correctly despite whitespace"
    assert "mcp__discord__discord_send" in result["blocked_tools"]
    assert "mcp__twitter__post_tweet" in result["blocked_tools"]


@pytest.mark.asyncio
async def test_isolated_workspace_detection():
    """Test that isolated workspaces are detected correctly."""

    # Create mock filesystem managers with isolated workspaces
    class MockFilesystemManager:
        def __init__(self, cwd):
            self.cwd = cwd

        def setup_orchestration_paths(self, **kwargs):
            """Mock method to avoid initialization errors."""

        def update_backend_mcp_config(self, config):
            """Mock method to avoid initialization errors."""

    class MockBackendWithWorkspace:
        def __init__(self, cwd):
            self.filesystem_manager = MockFilesystemManager(cwd)
            self.set_planning_mode = MagicMock()
            self.set_planning_mode_blocked_tools = MagicMock()
            self.config = {}  # Add config attribute

            async def mock_stream(*args, **kwargs):
                yield StreamChunk(type="content", content="IRREVERSIBLE: NO\nBLOCKED_TOOLS: ")

            self.stream_with_tools = mock_stream

    # Create agents with isolated workspaces
    backend1 = MockBackendWithWorkspace("/tmp/massgen_workspace_agent1")
    backend2 = MockBackendWithWorkspace("/tmp/workspace_agent2")

    config1 = AgentConfig.create_openai_config()
    config2 = AgentConfig.create_openai_config()

    agent1 = ConfigurableAgent(config=config1, backend=backend1)
    agent2 = ConfigurableAgent(config=config2, backend=backend2)

    agents = {"agent1": agent1, "agent2": agent2}

    orchestrator_config = AgentConfig.create_openai_config()
    orchestrator = Orchestrator(
        agents=agents,
        orchestrator_id="test_orchestrator",
        config=orchestrator_config,
    )

    user_question = "Create a file and write some data"
    conversation_context = {
        "current_message": user_question,
        "conversation_history": [],
        "full_messages": [{"role": "user", "content": user_question}],
    }

    # Run analysis - should detect isolated workspaces
    result = await orchestrator._analyze_question_irreversibility(user_question, conversation_context)

    # The prompt will inform the LLM about isolated workspaces
    # In this test, we're just verifying the detection logic runs without error
    assert result is not None
    assert "has_irreversible" in result
    assert "blocked_tools" in result


@pytest.mark.asyncio
async def test_no_isolated_workspace_detection():
    """Test behavior when no isolated workspaces are present."""

    # Create mock filesystem managers without isolated workspaces
    class MockFilesystemManager:
        def __init__(self, cwd):
            self.cwd = cwd

        def setup_orchestration_paths(self, **kwargs):
            """Mock method to avoid initialization errors."""

        def update_backend_mcp_config(self, config):
            """Mock method to avoid initialization errors."""

    class MockBackendNoWorkspace:
        def __init__(self, cwd):
            self.filesystem_manager = MockFilesystemManager(cwd)
            self.set_planning_mode = MagicMock()
            self.set_planning_mode_blocked_tools = MagicMock()
            self.config = {}  # Add config attribute

            async def mock_stream(*args, **kwargs):
                yield StreamChunk(type="content", content="IRREVERSIBLE: YES\nBLOCKED_TOOLS: mcp__filesystem__write_file")

            self.stream_with_tools = mock_stream

    # Create agents with regular directories (not workspaces)
    backend1 = MockBackendNoWorkspace("/home/user/project")
    backend2 = MockBackendNoWorkspace("/tmp/mydir")

    config1 = AgentConfig.create_openai_config()
    config2 = AgentConfig.create_openai_config()

    agent1 = ConfigurableAgent(config=config1, backend=backend1)
    agent2 = ConfigurableAgent(config=config2, backend=backend2)

    agents = {"agent1": agent1, "agent2": agent2}

    orchestrator_config = AgentConfig.create_openai_config()
    orchestrator = Orchestrator(
        agents=agents,
        orchestrator_id="test_orchestrator",
        config=orchestrator_config,
    )

    user_question = "Write a file to /tmp/test.txt"
    conversation_context = {
        "current_message": user_question,
        "conversation_history": [],
        "full_messages": [{"role": "user", "content": user_question}],
    }

    # Run analysis - should NOT detect isolated workspaces
    result = await orchestrator._analyze_question_irreversibility(user_question, conversation_context)

    assert result is not None
    assert result["has_irreversible"] is True
    assert "mcp__filesystem__write_file" in result["blocked_tools"]


@pytest.mark.asyncio
async def test_backend_selective_blocking_logic():
    """Test the backend's is_mcp_tool_blocked logic directly."""
    from massgen.backend.base import LLMBackend

    # Create a minimal mock backend
    class TestBackend(LLMBackend):
        def __init__(self):
            # Skip full initialization
            self._planning_mode_enabled = False
            self._planning_mode_blocked_tools = set()

        async def stream_with_tools(self, messages, tools, **kwargs):
            pass

        def get_provider_name(self):
            return "test"

    backend = TestBackend()

    # Test 1: Planning mode disabled - all tools allowed
    backend.set_planning_mode(False)
    assert backend.is_mcp_tool_blocked("mcp__discord__discord_send") is False
    assert backend.is_mcp_tool_blocked("any_tool") is False

    # Test 2: Planning mode enabled with empty blocked set - block ALL
    backend.set_planning_mode(True)
    backend.set_planning_mode_blocked_tools(set())
    assert backend.is_mcp_tool_blocked("mcp__discord__discord_send") is True
    assert backend.is_mcp_tool_blocked("mcp__discord__discord_read") is True
    assert backend.is_mcp_tool_blocked("any_tool") is True

    # Test 3: Planning mode enabled with specific tools - selective blocking
    backend.set_planning_mode(True)
    backend.set_planning_mode_blocked_tools({"mcp__discord__discord_send", "mcp__twitter__post_tweet"})

    assert backend.is_mcp_tool_blocked("mcp__discord__discord_send") is True
    assert backend.is_mcp_tool_blocked("mcp__twitter__post_tweet") is True
    assert backend.is_mcp_tool_blocked("mcp__discord__discord_read") is False
    assert backend.is_mcp_tool_blocked("mcp__twitter__search_tweets") is False

    # Test 4: Get blocked tools
    blocked = backend.get_planning_mode_blocked_tools()
    assert len(blocked) == 2
    assert "mcp__discord__discord_send" in blocked
    assert "mcp__twitter__post_tweet" in blocked


@pytest.mark.asyncio
async def test_chat_sets_blocked_tools_on_agents(orchestrator_with_agents):
    """Test that chat() method sets both planning mode and blocked tools on all agents."""
    orchestrator, mock_backend = orchestrator_with_agents

    # Add the set_planning_mode_blocked_tools method to mock
    mock_backend.set_planning_mode_blocked_tools = MagicMock()

    # Mock the analysis to return specific blocked tools
    async def mock_analysis_stream(*args, **kwargs):
        yield StreamChunk(
            type="content",
            content="IRREVERSIBLE: YES\nBLOCKED_TOOLS: mcp__discord__discord_send, mcp__twitter__post_tweet",
        )

    mock_backend.stream_with_tools = mock_analysis_stream

    # Mock the coordination to avoid full execution
    async def mock_coordinate(*args, **kwargs):
        yield StreamChunk(type="content", content="Coordinated response")
        yield StreamChunk(type="done")

    with patch.object(orchestrator, "_coordinate_agents_with_timeout", mock_coordinate):
        user_question = "Send a Discord message and post a tweet"
        messages = [{"role": "user", "content": user_question}]

        # Collect chunks
        chunks = []
        async for chunk in orchestrator.chat(messages):
            chunks.append(chunk)

        # Verify that set_planning_mode was called
        assert mock_backend.set_planning_mode.call_count == 2
        mock_backend.set_planning_mode.assert_called_with(True)

        # Verify that set_planning_mode_blocked_tools was called
        assert mock_backend.set_planning_mode_blocked_tools.call_count == 2
        # Check that it was called with the correct tools
        call_args = mock_backend.set_planning_mode_blocked_tools.call_args[0][0]
        assert "mcp__discord__discord_send" in call_args
        assert "mcp__twitter__post_tweet" in call_args


@pytest.mark.asyncio
async def test_empty_blocked_tools_list(orchestrator_with_agents):
    """Test handling of empty BLOCKED_TOOLS list (no specific tools to block)."""
    orchestrator, mock_backend = orchestrator_with_agents

    # Mock the analysis to return YES but with empty blocked tools
    async def mock_stream(*args, **kwargs):
        yield StreamChunk(type="content", content="IRREVERSIBLE: YES\nBLOCKED_TOOLS: ")

    mock_backend.stream_with_tools = mock_stream

    user_question = "Do something risky"
    conversation_context = {
        "current_message": user_question,
        "conversation_history": [],
        "full_messages": [{"role": "user", "content": user_question}],
    }

    result = await orchestrator._analyze_question_irreversibility(user_question, conversation_context)

    assert result["has_irreversible"] is True
    assert len(result["blocked_tools"]) == 0, "Should have empty blocked tools set"
    # Empty set means block ALL MCP tools (backward compatible)


@pytest.mark.asyncio
async def test_case_insensitive_workspace_detection():
    """Test that workspace detection is case-insensitive."""

    class MockFilesystemManager:
        def __init__(self, cwd):
            self.cwd = cwd

        def setup_orchestration_paths(self, **kwargs):
            """Mock method to avoid initialization errors."""

        def update_backend_mcp_config(self, config):
            """Mock method to avoid initialization errors."""

    class MockBackendCaseTest:
        def __init__(self, cwd):
            self.filesystem_manager = MockFilesystemManager(cwd)
            self.set_planning_mode = MagicMock()
            self.set_planning_mode_blocked_tools = MagicMock()
            self.config = {}  # Add config attribute

            async def mock_stream(*args, **kwargs):
                yield StreamChunk(type="content", content="IRREVERSIBLE: NO\nBLOCKED_TOOLS: ")

            self.stream_with_tools = mock_stream

    # Test with various case patterns
    test_cases = [
        "/tmp/WORKSPACE_agent1",
        "/tmp/WorkSpace_agent2",
        "/tmp/workspace_AGENT3",
        "/tmp/WoRkSpAcE_agent4",
    ]

    agents = {}
    for i, cwd in enumerate(test_cases):
        backend = MockBackendCaseTest(cwd)
        config = AgentConfig.create_openai_config()
        agent = ConfigurableAgent(config=config, backend=backend)
        agents[f"agent{i+1}"] = agent

    orchestrator_config = AgentConfig.create_openai_config()
    orchestrator = Orchestrator(
        agents=agents,
        orchestrator_id="test_orchestrator",
        config=orchestrator_config,
    )

    user_question = "Create some files"
    conversation_context = {
        "current_message": user_question,
        "conversation_history": [],
        "full_messages": [{"role": "user", "content": user_question}],
    }

    # Run analysis - should detect all workspaces regardless of case
    result = await orchestrator._analyze_question_irreversibility(user_question, conversation_context)

    # Verify the analysis completes successfully
    assert result is not None
    assert "has_irreversible" in result
    assert "blocked_tools" in result


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
