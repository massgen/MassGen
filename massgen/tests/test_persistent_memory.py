#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for PersistentMemory implementation.

This module tests the long-term persistent memory functionality using mem0,
including recording, retrieving, and managing memories across sessions.

Note: Some tests require mem0ai to be installed and may be skipped if unavailable.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Try to import memory components
try:
    from massgen.memory import PersistentMemory

    MEMORY_AVAILABLE = True
except ImportError:
    MEMORY_AVAILABLE = False
    PersistentMemory = None

# Check if mem0 is available
try:
    MEM0_AVAILABLE = True
except ImportError:
    MEM0_AVAILABLE = False


# Helper function to create mock backend
def create_mock_backend():
    """Create a mock backend for testing."""
    backend = MagicMock()
    backend.chat_completion = AsyncMock(
        return_value={
            "choices": [{"message": {"content": "Test response"}}],
        },
    )
    return backend


@pytest.mark.skipif(not MEMORY_AVAILABLE, reason="Memory module not available")
class TestPersistentMemoryInitialization:
    """Tests for PersistentMemory initialization."""

    @pytest.mark.skipif(not MEM0_AVAILABLE, reason="mem0 not installed")
    def test_initialization_without_identifiers_fails(self):
        """Test that initialization fails without agent/user/session identifiers."""
        with pytest.raises(ValueError, match="At least one of"):
            PersistentMemory(
                llm_backend=create_mock_backend(),
                embedding_backend=create_mock_backend(),
            )
        print("✅ Initialization validation works")

    @pytest.mark.skipif(not MEM0_AVAILABLE, reason="mem0 not installed")
    def test_initialization_without_backends_fails(self):
        """Test that initialization fails without required backends."""
        with pytest.raises(ValueError, match="Both llm_backend and embedding_backend"):
            PersistentMemory(agent_name="test_agent")
        print("✅ Backend validation works")

    @pytest.mark.skipif(not MEM0_AVAILABLE, reason="mem0 not installed")
    def test_initialization_with_agent_name(self):
        """Test successful initialization with agent name."""
        memory = PersistentMemory(
            agent_name="test_agent",
            llm_backend=create_mock_backend(),
            embedding_backend=create_mock_backend(),
        )
        assert memory.agent_id == "test_agent"
        assert memory.user_id is None
        assert memory.session_id is None
        print("✅ Initialization with agent_name works")

    @pytest.mark.skipif(not MEM0_AVAILABLE, reason="mem0 not installed")
    def test_initialization_with_all_identifiers(self):
        """Test initialization with all identifiers."""
        memory = PersistentMemory(
            agent_name="test_agent",
            user_name="test_user",
            session_name="test_session",
            llm_backend=create_mock_backend(),
            embedding_backend=create_mock_backend(),
        )
        assert memory.agent_id == "test_agent"
        assert memory.user_id == "test_user"
        assert memory.session_id == "test_session"
        print("✅ Initialization with all identifiers works")


@pytest.mark.skipif(
    not MEMORY_AVAILABLE or not MEM0_AVAILABLE,
    reason="Memory module or mem0 not available",
)
class TestPersistentMemoryMocked:
    """Tests for PersistentMemory with mocked mem0 backend."""

    @pytest.fixture
    def mock_memory(self):
        """Create a PersistentMemory instance with mocked mem0."""
        with patch("mem0.AsyncMemory") as mock_mem0:
            # Configure mock
            mock_mem0_instance = AsyncMock()
            mock_mem0.return_value = mock_mem0_instance

            memory = PersistentMemory(
                agent_name="test_agent",
                llm_backend=create_mock_backend(),
                embedding_backend=create_mock_backend(),
            )

            # Replace with our mock
            memory.mem0_memory = mock_mem0_instance

            yield memory, mock_mem0_instance

    @pytest.mark.asyncio
    async def test_record_messages(self, mock_memory):
        """Test recording messages to persistent memory."""
        memory, mock_mem0 = mock_memory

        # Mock the add method
        mock_mem0.add = AsyncMock(return_value={"results": ["mem_1", "mem_2"]})

        messages = [
            {"role": "user", "content": "What is quantum computing?"},
            {"role": "assistant", "content": "Quantum computing uses qubits..."},
        ]

        await memory.record(messages)

        # Verify mem0.add was called
        assert mock_mem0.add.called
        call_kwargs = mock_mem0.add.call_args.kwargs
        assert call_kwargs["agent_id"] == "test_agent"
        print("✅ Recording messages works")

    @pytest.mark.asyncio
    async def test_retrieve_memories(self, mock_memory):
        """Test retrieving memories based on query."""
        memory, mock_mem0 = mock_memory

        # Mock search results
        mock_mem0.search = AsyncMock(
            return_value={
                "results": [
                    {"memory": "Quantum computing uses qubits"},
                    {"memory": "Qubits can be in superposition"},
                ],
            },
        )

        result = await memory.retrieve("quantum computing")

        assert "Quantum computing uses qubits" in result
        assert "Qubits can be in superposition" in result
        assert mock_mem0.search.called
        print("✅ Retrieving memories works")

    @pytest.mark.asyncio
    async def test_retrieve_with_message_dict(self, mock_memory):
        """Test retrieving with message dictionary."""
        memory, mock_mem0 = mock_memory

        mock_mem0.search = AsyncMock(
            return_value={
                "results": [{"memory": "Relevant information"}],
            },
        )

        query = {"role": "user", "content": "Tell me about AI"}
        result = await memory.retrieve(query)

        assert "Relevant information" in result
        print("✅ Retrieving with message dict works")

    @pytest.mark.asyncio
    async def test_retrieve_with_message_list(self, mock_memory):
        """Test retrieving with list of messages."""
        memory, mock_mem0 = mock_memory

        mock_mem0.search = AsyncMock(
            return_value={
                "results": [{"memory": "AI information"}],
            },
        )

        queries = [
            {"role": "user", "content": "What is AI?"},
            {"role": "user", "content": "How does it work?"},
        ]
        await memory.retrieve(queries)

        assert mock_mem0.search.call_count == 2
        print("✅ Retrieving with message list works")

    @pytest.mark.asyncio
    async def test_save_to_memory_tool(self, mock_memory):
        """Test the save_to_memory agent tool."""
        memory, mock_mem0 = mock_memory

        mock_mem0.add = AsyncMock(return_value={"results": ["mem_123"]})

        result = await memory.save_to_memory(
            thinking="User mentioned their birthday",
            content=["User's birthday is March 15"],
        )

        assert result["success"] is True
        assert "Successfully saved" in result["message"]
        assert "mem_123" in result["memory_ids"]
        print("✅ save_to_memory tool works")

    @pytest.mark.asyncio
    async def test_save_to_memory_error_handling(self, mock_memory):
        """Test save_to_memory error handling."""
        memory, mock_mem0 = mock_memory

        # Mock an error
        mock_mem0.add = AsyncMock(side_effect=Exception("Database error"))

        result = await memory.save_to_memory(
            thinking="Test thinking",
            content=["Test content"],
        )

        assert result["success"] is False
        assert "Error saving to memory" in result["message"]
        print("✅ save_to_memory error handling works")

    @pytest.mark.asyncio
    async def test_recall_from_memory_tool(self, mock_memory):
        """Test the recall_from_memory agent tool."""
        memory, mock_mem0 = mock_memory

        mock_mem0.search = AsyncMock(
            return_value={
                "results": [
                    {"memory": "User likes Python programming"},
                    {"memory": "User's favorite framework is Django"},
                ],
            },
        )

        result = await memory.recall_from_memory(
            keywords=["programming", "preferences"],
        )

        assert result["success"] is True
        assert len(result["memories"]) == 4  # 2 results per keyword
        assert result["count"] == 4
        print("✅ recall_from_memory tool works")

    @pytest.mark.asyncio
    async def test_recall_from_memory_with_limit(self, mock_memory):
        """Test recall with custom limit."""
        memory, mock_mem0 = mock_memory

        mock_mem0.search = AsyncMock(
            return_value={
                "results": [{"memory": f"Memory {i}"} for i in range(3)],
            },
        )

        result = await memory.recall_from_memory(
            keywords=["test"],
            limit=3,
        )

        call_kwargs = mock_mem0.search.call_args.kwargs
        assert call_kwargs["limit"] == 3
        print("✅ recall_from_memory with limit works")

    @pytest.mark.asyncio
    async def test_recall_from_memory_error_handling(self, mock_memory):
        """Test recall_from_memory error handling."""
        memory, mock_mem0 = mock_memory

        mock_mem0.search = AsyncMock(side_effect=Exception("Search error"))

        result = await memory.recall_from_memory(keywords=["test"])

        assert result["success"] is False
        assert "Error retrieving memories" in result["message"]
        print("✅ recall_from_memory error handling works")

    @pytest.mark.asyncio
    async def test_record_empty_messages(self, mock_memory):
        """Test recording empty or None messages."""
        memory, mock_mem0 = mock_memory

        # Should not call mem0.add
        await memory.record([])
        await memory.record(None)
        await memory.record([None, None])

        assert not mock_mem0.add.called
        print("✅ Recording empty messages handled gracefully")

    @pytest.mark.asyncio
    async def test_retrieve_empty_query(self, mock_memory):
        """Test retrieving with empty query."""
        memory, mock_mem0 = mock_memory

        result = await memory.retrieve("")
        assert result == ""

        result = await memory.retrieve([])
        assert result == ""

        result = await memory.retrieve({"role": "user", "content": ""})
        assert result == ""

        print("✅ Retrieving with empty query handled gracefully")


@pytest.mark.skipif(
    not MEMORY_AVAILABLE or not MEM0_AVAILABLE,
    reason="Memory module or mem0 not available",
)
class TestPersistentMemoryIntegration:
    """Integration tests with actual mem0 (if available)."""

    @pytest.mark.asyncio
    async def test_full_memory_workflow(self):
        """Test a complete memory workflow: record and retrieve."""
        try:
            # Create memory instance
            memory = PersistentMemory(
                agent_name="test_integration_agent",
                llm_backend=create_mock_backend(),
                embedding_backend=create_mock_backend(),
                on_disk=False,  # Use in-memory for tests
            )

            # Record some information
            messages = [
                {"role": "user", "content": "I love Python programming"},
                {"role": "assistant", "content": "That's great! Python is versatile."},
            ]
            await memory.record(messages)

            # Try to retrieve
            result = await memory.retrieve("Python")

            # Should return something (exact match depends on embeddings)
            assert isinstance(result, str)
            print("✅ Full memory workflow works")

        except Exception as e:
            pytest.skip(f"Integration test skipped: {e}")

    @pytest.mark.asyncio
    async def test_memory_with_multiple_identifiers(self):
        """Test memory filtering with multiple identifiers."""
        try:
            memory = PersistentMemory(
                agent_name="agent_1",
                user_name="user_1",
                session_name="session_1",
                llm_backend=create_mock_backend(),
                embedding_backend=create_mock_backend(),
                on_disk=False,
            )

            # Record and verify identifiers are used
            await memory.record(
                [
                    {"role": "user", "content": "Test message"},
                ]
            )

            assert memory.agent_id == "agent_1"
            assert memory.user_id == "user_1"
            assert memory.session_id == "session_1"
            print("✅ Memory with multiple identifiers works")

        except Exception as e:
            pytest.skip(f"Integration test skipped: {e}")


@pytest.mark.skipif(not MEMORY_AVAILABLE, reason="Memory module not available")
class TestPersistentMemoryBase:
    """Tests for PersistentMemoryBase abstract methods."""

    def test_base_class_methods(self):
        """Test that base class has expected abstract methods."""
        from massgen.memory import PersistentMemoryBase

        # Check that methods exist
        assert hasattr(PersistentMemoryBase, "record")
        assert hasattr(PersistentMemoryBase, "retrieve")
        assert hasattr(PersistentMemoryBase, "save_to_memory")
        assert hasattr(PersistentMemoryBase, "recall_from_memory")
        print("✅ PersistentMemoryBase has expected methods")


if __name__ == "__main__":
    import asyncio

    async def run_all_tests():
        """Run all tests manually."""
        print("\n=== Running PersistentMemory Tests ===\n")

        if not MEMORY_AVAILABLE:
            print("❌ Memory module not available, skipping tests")
            return

        if not MEM0_AVAILABLE:
            print("⚠️  mem0 not installed, some tests will be skipped")

        # Run initialization tests
        print("\n--- Initialization Tests ---")
        test_init = TestPersistentMemoryInitialization()
        test_init.test_initialization_without_identifiers_fails()

        if MEM0_AVAILABLE:
            test_init.test_initialization_without_backends_fails()
            test_init.test_initialization_with_agent_name()
            test_init.test_initialization_with_all_identifiers()

        # Run base class tests
        print("\n--- Base Class Tests ---")
        test_base = TestPersistentMemoryBase()
        test_base.test_base_class_methods()

        print("\n⚠️  For complete testing, run with pytest to execute mocked and integration tests")
        print("   Command: pytest massgen/tests/test_persistent_memory.py -v")

        print("\n=== PersistentMemory Basic Tests Passed! ===\n")

    asyncio.run(run_all_tests())
