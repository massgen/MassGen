#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Orchestrator Shared Memory.

This module tests the shared memory functionality in the Orchestrator,
including how agents can access and contribute to shared memory that
all agents can see.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List, Dict, Any

# Import orchestrator and memory classes
from massgen.orchestrator import Orchestrator
from massgen.chat_agent import SingleAgent
from massgen.memory import ConversationMemory, PersistentMemory
from massgen.agent_config import AgentConfig


# Helper functions
def create_mock_backend(agent_responses: List[str] = None):
    """Create a mock backend with predefined responses."""
    if agent_responses is None:
        agent_responses = ["Test response"]

    backend = MagicMock()
    backend.is_stateful = MagicMock(return_value=False)
    backend.set_stage = MagicMock()
    backend.set_planning_mode = MagicMock()
    backend.extract_tool_name = MagicMock(side_effect=lambda tc: tc.get("name", ""))
    backend.extract_tool_arguments = MagicMock(side_effect=lambda tc: tc.get("arguments", {}))
    backend.get_provider_name = MagicMock(return_value="test_provider")
    backend.filesystem_manager = None

    # Track which response to return
    response_index = [0]

    async def mock_stream():
        idx = response_index[0]
        response = agent_responses[idx % len(agent_responses)]
        response_index[0] += 1

        yield MagicMock(type="content", content=response)
        yield MagicMock(
            type="complete_message",
            complete_message={"role": "assistant", "content": response}
        )
        yield MagicMock(type="done")

    backend.stream_with_tools = MagicMock(return_value=mock_stream())
    return backend


def create_mock_agent(agent_id: str, backend=None):
    """Create a mock agent for testing."""
    if backend is None:
        backend = create_mock_backend()

    agent = SingleAgent(
        backend=backend,
        agent_id=agent_id,
        system_message=f"You are {agent_id}"
    )
    return agent


def create_mock_persistent_memory():
    """Create a mock persistent memory."""
    memory = MagicMock()
    memory.record = AsyncMock()
    memory.retrieve = AsyncMock(return_value="")
    return memory


@pytest.mark.asyncio
class TestOrchestratorSharedConversationMemory:
    """Tests for Orchestrator with shared ConversationMemory."""

    async def test_orchestrator_with_shared_conversation_memory(self):
        """Test that orchestrator initializes with shared conversation memory."""
        shared_memory = ConversationMemory()
        agents = {
            "agent1": create_mock_agent("agent1"),
            "agent2": create_mock_agent("agent2"),
        }

        orchestrator = Orchestrator(
            agents=agents,
            shared_conversation_memory=shared_memory
        )

        assert orchestrator.shared_conversation_memory is shared_memory
        assert orchestrator.shared_persistent_memory is None
        print("✅ Orchestrator with shared conversation memory initialization works")

    async def test_shared_memory_injection_to_agents(self):
        """Test that shared memory content is injected into agent messages."""
        shared_memory = ConversationMemory()

        # Add some messages to shared memory first
        await shared_memory.add([
            {"role": "assistant", "content": "Previous insight", "agent_id": "agent1"},
            {"role": "assistant", "content": "Another finding", "agent_id": "agent2"},
        ])

        agents = {
            "agent1": create_mock_agent("agent1"),
        }

        orchestrator = Orchestrator(
            agents=agents,
            shared_conversation_memory=shared_memory
        )

        # Test the injection method
        original_messages = [
            {"role": "system", "content": "You are an agent"},
            {"role": "user", "content": "Solve this task"}
        ]

        injected_messages = await orchestrator._inject_shared_memory_context(
            original_messages, "agent1"
        )

        # Should have an additional system message with shared memory
        assert len(injected_messages) > len(original_messages)

        # Find the memory injection message
        memory_messages = [msg for msg in injected_messages if "SHARED CONVERSATION MEMORY" in msg.get("content", "")]
        assert len(memory_messages) == 1

        memory_content = memory_messages[0]["content"]
        assert "Previous insight" in memory_content
        assert "Another finding" in memory_content

        print("✅ Shared memory injection to agents works")

    async def test_agent_contributions_recorded_to_shared_memory(self):
        """Test that agent contributions are recorded to shared memory."""
        shared_memory = ConversationMemory()
        agents = {
            "agent1": create_mock_agent("agent1"),
        }

        orchestrator = Orchestrator(
            agents=agents,
            shared_conversation_memory=shared_memory
        )

        # Simulate recording to shared memory
        await orchestrator._record_to_shared_memory(
            agent_id="agent1",
            content="I found the solution",
            role="assistant"
        )

        # Check if the message was recorded
        memory_size = await shared_memory.size()
        assert memory_size == 1

        messages = await shared_memory.get_messages()
        assert len(messages) == 1
        assert messages[0]["content"] == "I found the solution"
        assert messages[0]["agent_id"] == "agent1"

        print("✅ Agent contributions recorded to shared memory")

    async def test_multiple_agents_share_same_memory(self):
        """Test that multiple agents can see the same shared memory."""
        shared_memory = ConversationMemory()

        # Agent1 contributes to memory
        await shared_memory.add({
            "role": "assistant",
            "content": "Agent1's discovery",
            "agent_id": "agent1"
        })

        agents = {
            "agent1": create_mock_agent("agent1"),
            "agent2": create_mock_agent("agent2"),
        }

        orchestrator = Orchestrator(
            agents=agents,
            shared_conversation_memory=shared_memory
        )

        # Both agents should see the same memory
        messages1 = await orchestrator._inject_shared_memory_context(
            [{"role": "user", "content": "Task"}], "agent1"
        )
        messages2 = await orchestrator._inject_shared_memory_context(
            [{"role": "user", "content": "Task"}], "agent2"
        )

        # Both should have memory injection
        assert any("Agent1's discovery" in msg.get("content", "") for msg in messages1)
        assert any("Agent1's discovery" in msg.get("content", "") for msg in messages2)

        print("✅ Multiple agents share the same memory")

    async def test_shared_memory_accumulates_over_time(self):
        """Test that shared memory accumulates contributions from multiple agents."""
        shared_memory = ConversationMemory()
        agents = {
            "agent1": create_mock_agent("agent1"),
            "agent2": create_mock_agent("agent2"),
            "agent3": create_mock_agent("agent3"),
        }

        orchestrator = Orchestrator(
            agents=agents,
            shared_conversation_memory=shared_memory
        )

        # Simulate multiple agents contributing
        await orchestrator._record_to_shared_memory("agent1", "First finding", "assistant")
        await orchestrator._record_to_shared_memory("agent2", "Second finding", "assistant")
        await orchestrator._record_to_shared_memory("agent3", "Third finding", "assistant")

        # Check memory size
        memory_size = await shared_memory.size()
        assert memory_size == 3

        # All contributions should be visible
        messages = await shared_memory.get_messages()
        contents = [msg["content"] for msg in messages]
        assert "First finding" in contents
        assert "Second finding" in contents
        assert "Third finding" in contents

        print("✅ Shared memory accumulates over time")


@pytest.mark.asyncio
class TestOrchestratorSharedPersistentMemory:
    """Tests for Orchestrator with shared PersistentMemory."""

    async def test_orchestrator_with_shared_persistent_memory(self):
        """Test that orchestrator initializes with shared persistent memory."""
        persistent_memory = create_mock_persistent_memory()
        agents = {
            "agent1": create_mock_agent("agent1"),
            "agent2": create_mock_agent("agent2"),
        }

        orchestrator = Orchestrator(
            agents=agents,
            shared_persistent_memory=persistent_memory
        )

        assert orchestrator.shared_persistent_memory is persistent_memory
        print("✅ Orchestrator with shared persistent memory initialization works")

    async def test_persistent_memory_retrieval_for_agents(self):
        """Test that persistent memory is retrieved and injected for agents."""
        persistent_memory = create_mock_persistent_memory()
        persistent_memory.retrieve = AsyncMock(return_value="Historical context: Previous session insights")

        agents = {
            "agent1": create_mock_agent("agent1"),
        }

        orchestrator = Orchestrator(
            agents=agents,
            shared_persistent_memory=persistent_memory
        )

        # Test injection
        original_messages = [
            {"role": "user", "content": "New task"}
        ]

        injected_messages = await orchestrator._inject_shared_memory_context(
            original_messages, "agent1"
        )

        # Should have persistent memory context
        memory_content = "\n".join([msg.get("content", "") for msg in injected_messages])
        assert "SHARED PERSISTENT MEMORY" in memory_content
        assert "Historical context" in memory_content

        print("✅ Persistent memory retrieval for agents works")

    async def test_persistent_memory_recording(self):
        """Test that agent contributions are recorded to persistent memory."""
        persistent_memory = create_mock_persistent_memory()
        agents = {
            "agent1": create_mock_agent("agent1"),
        }

        orchestrator = Orchestrator(
            agents=agents,
            shared_persistent_memory=persistent_memory
        )

        # Record to memory
        await orchestrator._record_to_shared_memory(
            agent_id="agent1",
            content="Important discovery",
            role="assistant"
        )

        # Verify record was called
        assert persistent_memory.record.called
        call_args = persistent_memory.record.call_args[0][0]
        assert len(call_args) == 1
        assert call_args[0]["content"] == "Important discovery"

        print("✅ Persistent memory recording works")


@pytest.mark.asyncio
class TestOrchestratorBothMemories:
    """Tests for Orchestrator with both shared memories."""

    async def test_orchestrator_with_both_shared_memories(self):
        """Test orchestrator with both conversation and persistent memory."""
        conv_memory = ConversationMemory()
        persist_memory = create_mock_persistent_memory()

        agents = {
            "agent1": create_mock_agent("agent1"),
            "agent2": create_mock_agent("agent2"),
        }

        orchestrator = Orchestrator(
            agents=agents,
            shared_conversation_memory=conv_memory,
            shared_persistent_memory=persist_memory
        )

        assert orchestrator.shared_conversation_memory is conv_memory
        assert orchestrator.shared_persistent_memory is persist_memory

        print("✅ Orchestrator with both shared memories works")

    async def test_both_memories_used_together(self):
        """Test that both memory types are used together correctly."""
        conv_memory = ConversationMemory()
        await conv_memory.add({
            "role": "assistant",
            "content": "Recent conversation",
            "agent_id": "agent1"
        })

        persist_memory = create_mock_persistent_memory()
        persist_memory.retrieve = AsyncMock(return_value="Long-term knowledge")

        agents = {
            "agent1": create_mock_agent("agent1"),
        }

        orchestrator = Orchestrator(
            agents=agents,
            shared_conversation_memory=conv_memory,
            shared_persistent_memory=persist_memory
        )

        # Inject both memories
        injected_messages = await orchestrator._inject_shared_memory_context(
            [{"role": "user", "content": "Task"}], "agent1"
        )

        # Should have both memory types
        all_content = "\n".join([msg.get("content", "") for msg in injected_messages])
        assert "SHARED CONVERSATION MEMORY" in all_content
        assert "Recent conversation" in all_content
        assert "SHARED PERSISTENT MEMORY" in all_content
        assert "Long-term knowledge" in all_content

        print("✅ Both memories used together works")

    async def test_recording_to_both_memories(self):
        """Test that recordings go to both memory types."""
        conv_memory = ConversationMemory()
        persist_memory = create_mock_persistent_memory()

        agents = {
            "agent1": create_mock_agent("agent1"),
        }

        orchestrator = Orchestrator(
            agents=agents,
            shared_conversation_memory=conv_memory,
            shared_persistent_memory=persist_memory
        )

        # Record once
        await orchestrator._record_to_shared_memory(
            agent_id="agent1",
            content="Shared finding",
            role="assistant"
        )

        # Check conversation memory
        conv_size = await conv_memory.size()
        assert conv_size == 1

        # Check persistent memory was called
        assert persist_memory.record.called

        print("✅ Recording to both memories works")


@pytest.mark.asyncio
class TestSharedMemoryErrorHandling:
    """Tests for error handling in shared memory operations."""

    async def test_orchestrator_without_shared_memory(self):
        """Test that orchestrator works without shared memory."""
        agents = {
            "agent1": create_mock_agent("agent1"),
        }

        orchestrator = Orchestrator(agents=agents)

        assert orchestrator.shared_conversation_memory is None
        assert orchestrator.shared_persistent_memory is None

        # Injection should return original messages
        messages = [{"role": "user", "content": "Task"}]
        injected = await orchestrator._inject_shared_memory_context(messages, "agent1")
        assert injected == messages

        # Recording should not fail
        await orchestrator._record_to_shared_memory("agent1", "test", "assistant")

        print("✅ Orchestrator works without shared memory")

    async def test_memory_failure_doesnt_crash_orchestrator(self):
        """Test that memory failures don't crash the orchestrator."""
        # Create faulty memory
        conv_memory = MagicMock()
        conv_memory.get_messages = AsyncMock(side_effect=Exception("Memory error"))
        conv_memory.add = AsyncMock(side_effect=Exception("Memory error"))

        agents = {
            "agent1": create_mock_agent("agent1"),
        }

        orchestrator = Orchestrator(
            agents=agents,
            shared_conversation_memory=conv_memory
        )

        # Injection should not crash even if memory fails
        messages = [{"role": "user", "content": "Task"}]
        injected = await orchestrator._inject_shared_memory_context(messages, "agent1")
        # Should return something (at least original messages)
        assert injected is not None

        # Recording should not crash
        await orchestrator._record_to_shared_memory("agent1", "test", "assistant")

        print("✅ Memory failures don't crash orchestrator")

    async def test_persistent_memory_not_implemented_handled(self):
        """Test that NotImplementedError from persistent memory is handled."""
        persist_memory = MagicMock()
        persist_memory.retrieve = AsyncMock(side_effect=NotImplementedError())
        persist_memory.record = AsyncMock(side_effect=NotImplementedError())

        agents = {
            "agent1": create_mock_agent("agent1"),
        }

        orchestrator = Orchestrator(
            agents=agents,
            shared_persistent_memory=persist_memory
        )

        # Should handle NotImplementedError gracefully
        messages = [{"role": "user", "content": "Task"}]
        injected = await orchestrator._inject_shared_memory_context(messages, "agent1")
        assert injected is not None

        await orchestrator._record_to_shared_memory("agent1", "test", "assistant")

        print("✅ NotImplementedError from persistent memory handled")


@pytest.mark.asyncio
class TestCrossAgentMemoryVisibility:
    """Tests for verifying agents can see each other's memory contributions."""

    async def test_agent_can_see_other_agents_contributions(self):
        """Test that one agent can see another agent's contributions in shared memory."""
        shared_memory = ConversationMemory()

        agents = {
            "agent1": create_mock_agent("agent1"),
            "agent2": create_mock_agent("agent2"),
        }

        orchestrator = Orchestrator(
            agents=agents,
            shared_conversation_memory=shared_memory
        )

        # Agent1 makes a contribution
        await orchestrator._record_to_shared_memory(
            agent_id="agent1",
            content="Agent1 discovered X",
            role="assistant"
        )

        # Agent2 should see Agent1's contribution
        messages_for_agent2 = await orchestrator._inject_shared_memory_context(
            [{"role": "user", "content": "Continue the work"}],
            "agent2"
        )

        # Check that agent2 can see agent1's contribution
        all_content = "\n".join([msg.get("content", "") for msg in messages_for_agent2])
        assert "agent1" in all_content.lower()
        assert "Agent1 discovered X" in all_content

        print("✅ Agent can see other agents' contributions")

    async def test_memory_shows_agent_attribution(self):
        """Test that shared memory properly attributes contributions to agents."""
        shared_memory = ConversationMemory()

        agents = {
            "agent1": create_mock_agent("agent1"),
            "agent2": create_mock_agent("agent2"),
            "agent3": create_mock_agent("agent3"),
        }

        orchestrator = Orchestrator(
            agents=agents,
            shared_conversation_memory=shared_memory
        )

        # Multiple agents contribute
        await orchestrator._record_to_shared_memory("agent1", "Finding A", "assistant")
        await orchestrator._record_to_shared_memory("agent2", "Finding B", "assistant")
        await orchestrator._record_to_shared_memory("agent3", "Finding C", "assistant")

        # Check that any agent can see all contributions with attribution
        messages = await orchestrator._inject_shared_memory_context(
            [{"role": "user", "content": "Task"}],
            "agent1"
        )

        all_content = "\n".join([msg.get("content", "") for msg in messages])

        # Should show all agents' contributions with attribution
        assert "[agent1]" in all_content
        assert "Finding A" in all_content
        assert "[agent2]" in all_content
        assert "Finding B" in all_content
        assert "[agent3]" in all_content
        assert "Finding C" in all_content

        print("✅ Memory shows agent attribution")


if __name__ == "__main__":
    import asyncio

    async def run_all_tests():
        """Run all tests manually."""
        print("\n=== Running Orchestrator Shared Memory Tests ===\n")

        # Shared conversation memory tests
        print("\n--- Orchestrator with Shared Conversation Memory ---")
        test_conv = TestOrchestratorSharedConversationMemory()
        await test_conv.test_orchestrator_with_shared_conversation_memory()
        await test_conv.test_shared_memory_injection_to_agents()
        await test_conv.test_agent_contributions_recorded_to_shared_memory()
        await test_conv.test_multiple_agents_share_same_memory()
        await test_conv.test_shared_memory_accumulates_over_time()

        # Shared persistent memory tests
        print("\n--- Orchestrator with Shared Persistent Memory ---")
        test_persist = TestOrchestratorSharedPersistentMemory()
        await test_persist.test_orchestrator_with_shared_persistent_memory()
        await test_persist.test_persistent_memory_retrieval_for_agents()
        await test_persist.test_persistent_memory_recording()

        # Both memories tests
        print("\n--- Orchestrator with Both Shared Memories ---")
        test_both = TestOrchestratorBothMemories()
        await test_both.test_orchestrator_with_both_shared_memories()
        await test_both.test_both_memories_used_together()
        await test_both.test_recording_to_both_memories()

        # Error handling tests
        print("\n--- Shared Memory Error Handling ---")
        test_errors = TestSharedMemoryErrorHandling()
        await test_errors.test_orchestrator_without_shared_memory()
        await test_errors.test_memory_failure_doesnt_crash_orchestrator()
        await test_errors.test_persistent_memory_not_implemented_handled()

        # Cross-agent visibility tests
        print("\n--- Cross-Agent Memory Visibility ---")
        test_cross = TestCrossAgentMemoryVisibility()
        await test_cross.test_agent_can_see_other_agents_contributions()
        await test_cross.test_memory_shows_agent_attribution()

        print("\n=== All Orchestrator Shared Memory Tests Passed! ===\n")

    asyncio.run(run_all_tests())
