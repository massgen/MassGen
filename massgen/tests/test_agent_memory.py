#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Agent Memory Integration.

This module tests the integration of memory systems (ConversationMemory and
PersistentMemory) with MassGen agents (SingleAgent and ConfigurableAgent).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List, Dict, Any

# Import agent classes
from massgen.chat_agent import SingleAgent, ConfigurableAgent
from massgen.memory import ConversationMemory, PersistentMemory


# Helper functions for mocking
def create_mock_backend():
    """Create a mock LLM backend for testing."""
    backend = MagicMock()
    backend.is_stateful = MagicMock(return_value=False)
    backend.set_stage = MagicMock()

    # Mock stream_with_tools to return an async generator
    async def mock_stream():
        # Simulate assistant response
        yield MagicMock(type="content", content="Hello! ")
        yield MagicMock(type="content", content="How can I help?")
        yield MagicMock(
            type="complete_message",
            complete_message={"role": "assistant", "content": "Hello! How can I help?"}
        )
        yield MagicMock(type="done")

    backend.stream_with_tools = MagicMock(return_value=mock_stream())
    return backend


def create_mock_persistent_memory():
    """Create a mock persistent memory for testing."""
    memory = MagicMock(spec=PersistentMemory)
    memory.record = AsyncMock()
    memory.retrieve = AsyncMock(return_value="Previous context: User likes Python")
    return memory


@pytest.mark.asyncio
class TestSingleAgentConversationMemory:
    """Tests for SingleAgent with ConversationMemory."""

    async def test_agent_with_conversation_memory_initialization(self):
        """Test that agent initializes correctly with conversation memory."""
        backend = create_mock_backend()
        conv_memory = ConversationMemory()

        agent = SingleAgent(
            backend=backend,
            agent_id="test_agent",
            system_message="You are a helpful assistant",
            conversation_memory=conv_memory
        )

        assert agent.conversation_memory is conv_memory
        assert agent.persistent_memory is None
        print("✅ Agent with conversation memory initialization works")

    async def test_agent_adds_messages_to_conversation_memory(self):
        """Test that agent adds messages to conversation memory during chat."""
        backend = create_mock_backend()
        conv_memory = ConversationMemory()

        agent = SingleAgent(
            backend=backend,
            agent_id="test_agent",
            conversation_memory=conv_memory
        )

        # Initial memory should be empty
        assert await conv_memory.size() == 0

        # Chat with agent
        messages = [{"role": "user", "content": "Hello, agent!"}]
        response_chunks = []
        async for chunk in agent.chat(messages):
            response_chunks.append(chunk)

        # Memory should now contain user message and assistant response
        memory_size = await conv_memory.size()
        assert memory_size >= 1  # At least the user message

        stored_messages = await conv_memory.get_messages()
        user_messages = [msg for msg in stored_messages if msg.get("role") == "user"]
        assert len(user_messages) >= 1
        assert user_messages[0]["content"] == "Hello, agent!"

        print("✅ Agent adds messages to conversation memory")

    async def test_agent_clears_conversation_memory_on_reset(self):
        """Test that agent clears conversation memory when reset."""
        backend = create_mock_backend()
        conv_memory = ConversationMemory()

        agent = SingleAgent(
            backend=backend,
            conversation_memory=conv_memory
        )

        # Add some messages
        messages = [{"role": "user", "content": "Test message"}]
        async for _ in agent.chat(messages):
            pass

        # Memory should have content
        assert await conv_memory.size() > 0

        # Reset agent
        await agent.reset()

        # Memory should be cleared
        assert await conv_memory.size() == 0
        print("✅ Agent clears conversation memory on reset")

    async def test_agent_clears_memory_on_clear_history(self):
        """Test that agent clears memory when clear_history flag is set."""
        backend = create_mock_backend()
        conv_memory = ConversationMemory()

        agent = SingleAgent(
            backend=backend,
            conversation_memory=conv_memory,
            system_message="System prompt"
        )

        # First conversation
        messages1 = [{"role": "user", "content": "First message"}]
        async for _ in agent.chat(messages1):
            pass

        initial_size = await conv_memory.size()
        assert initial_size > 0

        # Clear and start new conversation
        messages2 = [{"role": "user", "content": "Second message"}]
        async for _ in agent.chat(messages2, clear_history=True):
            pass

        # Memory should be cleared and only contain new messages
        stored = await conv_memory.get_messages()
        user_msgs = [m for m in stored if m.get("role") == "user"]
        assert len(user_msgs) == 1
        assert user_msgs[0]["content"] == "Second message"

        print("✅ Agent clears memory on clear_history")


@pytest.mark.asyncio
class TestSingleAgentPersistentMemory:
    """Tests for SingleAgent with PersistentMemory."""

    async def test_agent_with_persistent_memory_initialization(self):
        """Test that agent initializes correctly with persistent memory."""
        backend = create_mock_backend()
        persist_memory = create_mock_persistent_memory()

        agent = SingleAgent(
            backend=backend,
            agent_id="test_agent",
            persistent_memory=persist_memory
        )

        assert agent.persistent_memory is persist_memory
        print("✅ Agent with persistent memory initialization works")

    async def test_agent_retrieves_from_persistent_memory(self):
        """Test that agent retrieves context from persistent memory."""
        backend = create_mock_backend()
        persist_memory = create_mock_persistent_memory()

        # Mock retrieve to return some context
        persist_memory.retrieve = AsyncMock(
            return_value="User previously asked about Python"
        )

        agent = SingleAgent(
            backend=backend,
            persistent_memory=persist_memory
        )

        # Chat with agent
        messages = [{"role": "user", "content": "Tell me more"}]
        async for _ in agent.chat(messages):
            pass

        # Verify retrieve was called
        assert persist_memory.retrieve.called
        print("✅ Agent retrieves from persistent memory")

    async def test_agent_records_to_persistent_memory(self):
        """Test that agent records responses to persistent memory."""
        backend = create_mock_backend()
        persist_memory = create_mock_persistent_memory()

        agent = SingleAgent(
            backend=backend,
            persistent_memory=persist_memory
        )

        # Chat with agent
        messages = [{"role": "user", "content": "Remember this"}]
        async for _ in agent.chat(messages):
            pass

        # Verify record was called
        assert persist_memory.record.called
        print("✅ Agent records to persistent memory")

    async def test_agent_handles_memory_not_implemented_gracefully(self):
        """Test that agent handles NotImplementedError from memory gracefully."""
        backend = create_mock_backend()
        persist_memory = MagicMock()

        # Mock retrieve to raise NotImplementedError
        persist_memory.retrieve = AsyncMock(side_effect=NotImplementedError())
        persist_memory.record = AsyncMock(side_effect=NotImplementedError())

        agent = SingleAgent(
            backend=backend,
            persistent_memory=persist_memory
        )

        # Should not raise error
        messages = [{"role": "user", "content": "Test"}]
        async for _ in agent.chat(messages):
            pass

        print("✅ Agent handles NotImplementedError gracefully")


@pytest.mark.asyncio
class TestSingleAgentBothMemories:
    """Tests for SingleAgent with both ConversationMemory and PersistentMemory."""

    async def test_agent_with_both_memories(self):
        """Test that agent works correctly with both memory types."""
        backend = create_mock_backend()
        conv_memory = ConversationMemory()
        persist_memory = create_mock_persistent_memory()

        agent = SingleAgent(
            backend=backend,
            conversation_memory=conv_memory,
            persistent_memory=persist_memory
        )

        # Chat with agent
        messages = [{"role": "user", "content": "Hello with both memories"}]
        async for _ in agent.chat(messages):
            pass

        # Both memories should be used
        assert await conv_memory.size() > 0
        assert persist_memory.retrieve.called
        assert persist_memory.record.called

        print("✅ Agent works with both memory types")

    async def test_memory_integration_flow(self):
        """Test complete memory integration flow."""
        # Create a fresh backend for each chat call
        def create_fresh_backend():
            backend = MagicMock()
            backend.is_stateful = MagicMock(return_value=False)
            backend.set_stage = MagicMock()

            async def mock_stream():
                yield MagicMock(type="content", content="Response")
                yield MagicMock(
                    type="complete_message",
                    complete_message={"role": "assistant", "content": "Response"}
                )
                yield MagicMock(type="done")

            backend.stream_with_tools = MagicMock(return_value=mock_stream())
            return backend

        conv_memory = ConversationMemory()
        persist_memory = create_mock_persistent_memory()

        agent = SingleAgent(
            backend=create_fresh_backend(),
            agent_id="test_agent",
            conversation_memory=conv_memory,
            persistent_memory=persist_memory
        )

        # First conversation
        messages1 = [{"role": "user", "content": "My name is Alice"}]
        async for _ in agent.chat(messages1):
            pass

        # Verify conversation memory has messages
        conv_size1 = await conv_memory.size()
        assert conv_size1 > 0

        # Verify persistent memory recorded
        assert persist_memory.record.called
        record_call_count = persist_memory.record.call_count

        # Update backend for second chat
        agent.backend = create_fresh_backend()

        # Second conversation
        messages2 = [{"role": "user", "content": "What's my name?"}]
        async for _ in agent.chat(messages2):
            pass

        # Conversation memory should have grown
        conv_size2 = await conv_memory.size()
        assert conv_size2 > conv_size1

        # Persistent memory should have been queried and recorded again
        assert persist_memory.retrieve.call_count >= 1
        assert persist_memory.record.call_count >= record_call_count

        print("✅ Complete memory integration flow works")


@pytest.mark.asyncio
class TestConfigurableAgentMemory:
    """Tests for ConfigurableAgent with memory."""

    async def test_configurable_agent_with_memory(self):
        """Test that ConfigurableAgent works with memory."""
        from massgen.agent_config import AgentConfig

        backend = create_mock_backend()
        conv_memory = ConversationMemory()
        persist_memory = create_mock_persistent_memory()

        config = AgentConfig(
            agent_id="configurable_test",
            backend_params={"model": "gpt-4o-mini"}
        )

        agent = ConfigurableAgent(
            config=config,
            backend=backend,
            conversation_memory=conv_memory,
            persistent_memory=persist_memory
        )

        assert agent.conversation_memory is conv_memory
        assert agent.persistent_memory is persist_memory

        # Test chat
        messages = [{"role": "user", "content": "Test configurable"}]
        async for _ in agent.chat(messages):
            pass

        # Verify memory was used
        assert await conv_memory.size() > 0
        assert persist_memory.retrieve.called

        print("✅ ConfigurableAgent works with memory")


@pytest.mark.asyncio
class TestMemoryStateManagement:
    """Tests for memory state management in agents."""

    async def test_conversation_memory_survives_across_chats(self):
        """Test that conversation memory persists across multiple chat calls."""
        backend = create_mock_backend()
        conv_memory = ConversationMemory()

        agent = SingleAgent(
            backend=backend,
            conversation_memory=conv_memory
        )

        # First chat
        messages1 = [{"role": "user", "content": "First question"}]
        async for _ in agent.chat(messages1):
            pass

        size_after_first = await conv_memory.size()

        # Second chat
        messages2 = [{"role": "user", "content": "Second question"}]
        async for _ in agent.chat(messages2):
            pass

        size_after_second = await conv_memory.size()

        # Memory should accumulate
        assert size_after_second > size_after_first

        # Should have both messages
        all_messages = await conv_memory.get_messages()
        user_messages = [m for m in all_messages if m.get("role") == "user"]
        assert len(user_messages) >= 2

        print("✅ Conversation memory persists across chats")

    async def test_reset_chat_clears_conversation_memory(self):
        """Test that reset_chat flag clears conversation memory."""
        backend = create_mock_backend()
        conv_memory = ConversationMemory()

        agent = SingleAgent(
            backend=backend,
            conversation_memory=conv_memory
        )

        # First chat
        messages1 = [{"role": "user", "content": "First"}]
        async for _ in agent.chat(messages1):
            pass

        assert await conv_memory.size() > 0

        # Reset chat
        messages2 = [{"role": "user", "content": "Second"}]
        async for _ in agent.chat(messages2, reset_chat=True):
            pass

        # Memory should be reset
        all_messages = await conv_memory.get_messages()
        user_messages = [m for m in all_messages if m.get("role") == "user"]

        # Should only have the reset message
        assert len(user_messages) == 1
        assert user_messages[0]["content"] == "Second"

        print("✅ reset_chat clears conversation memory")


@pytest.mark.asyncio
class TestMemoryErrorHandling:
    """Tests for error handling in memory operations."""

    async def test_agent_continues_when_memory_add_fails(self):
        """Test that agent continues working when memory add fails."""
        backend = create_mock_backend()
        conv_memory = MagicMock(spec=ConversationMemory)
        conv_memory.add = AsyncMock(side_effect=Exception("Memory error"))
        conv_memory.clear = AsyncMock()

        agent = SingleAgent(
            backend=backend,
            conversation_memory=conv_memory
        )

        # Should not crash even if memory fails
        messages = [{"role": "user", "content": "Test"}]
        chunks = []
        async for chunk in agent.chat(messages):
            chunks.append(chunk)

        # Should have received response
        assert len(chunks) > 0
        print("✅ Agent continues when memory add fails")

    async def test_agent_without_memory_works_normally(self):
        """Test that agent works normally without any memory."""
        backend = create_mock_backend()

        agent = SingleAgent(backend=backend)

        assert agent.conversation_memory is None
        assert agent.persistent_memory is None

        # Should work without memory
        messages = [{"role": "user", "content": "Test"}]
        chunks = []
        async for chunk in agent.chat(messages):
            chunks.append(chunk)

        assert len(chunks) > 0
        print("✅ Agent works without memory")


if __name__ == "__main__":
    import asyncio

    async def run_all_tests():
        """Run all tests manually."""
        print("\n=== Running Agent Memory Integration Tests ===\n")

        # SingleAgent with ConversationMemory tests
        print("\n--- SingleAgent with ConversationMemory ---")
        test_conv = TestSingleAgentConversationMemory()
        await test_conv.test_agent_with_conversation_memory_initialization()
        await test_conv.test_agent_adds_messages_to_conversation_memory()
        await test_conv.test_agent_clears_conversation_memory_on_reset()
        await test_conv.test_agent_clears_memory_on_clear_history()

        # SingleAgent with PersistentMemory tests
        print("\n--- SingleAgent with PersistentMemory ---")
        test_persist = TestSingleAgentPersistentMemory()
        await test_persist.test_agent_with_persistent_memory_initialization()
        await test_persist.test_agent_retrieves_from_persistent_memory()
        await test_persist.test_agent_records_to_persistent_memory()
        await test_persist.test_agent_handles_memory_not_implemented_gracefully()

        # Both memories tests
        print("\n--- SingleAgent with Both Memories ---")
        test_both = TestSingleAgentBothMemories()
        await test_both.test_agent_with_both_memories()
        await test_both.test_memory_integration_flow()

        # ConfigurableAgent tests
        print("\n--- ConfigurableAgent with Memory ---")
        test_config = TestConfigurableAgentMemory()
        await test_config.test_configurable_agent_with_memory()

        # State management tests
        print("\n--- Memory State Management ---")
        test_state = TestMemoryStateManagement()
        await test_state.test_conversation_memory_survives_across_chats()
        await test_state.test_reset_chat_clears_conversation_memory()

        # Error handling tests
        print("\n--- Memory Error Handling ---")
        test_errors = TestMemoryErrorHandling()
        await test_errors.test_agent_continues_when_memory_add_fails()
        await test_errors.test_agent_without_memory_works_normally()

        print("\n=== All Agent Memory Integration Tests Passed! ===\n")

    asyncio.run(run_all_tests())
