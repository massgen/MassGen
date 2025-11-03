#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for ConversationMemory implementation.

This module tests the in-memory conversation storage functionality,
including adding, retrieving, deleting, and managing messages.
"""

import pytest

from massgen.memory import ConversationMemory


@pytest.mark.asyncio
async def test_conversation_memory_initialization():
    """Test that ConversationMemory initializes correctly."""
    memory = ConversationMemory()

    assert await memory.size() == 0
    assert memory.messages == []
    print("✅ ConversationMemory initialization works")


@pytest.mark.asyncio
async def test_add_single_message():
    """Test adding a single message to memory."""
    memory = ConversationMemory()

    message = {"role": "user", "content": "Hello, world!"}
    await memory.add(message)

    assert await memory.size() == 1
    messages = await memory.get_messages()
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello, world!"
    assert "id" in messages[0]  # Auto-generated ID
    print("✅ Adding single message works")


@pytest.mark.asyncio
async def test_add_multiple_messages():
    """Test adding multiple messages at once."""
    memory = ConversationMemory()

    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
        {"role": "user", "content": "How are you?"},
    ]
    await memory.add(messages)

    assert await memory.size() == 3
    retrieved = await memory.get_messages()
    assert len(retrieved) == 3
    assert retrieved[0]["content"] == "Hello"
    assert retrieved[1]["content"] == "Hi there!"
    assert retrieved[2]["content"] == "How are you?"
    print("✅ Adding multiple messages works")


@pytest.mark.asyncio
async def test_duplicate_prevention():
    """Test that duplicate messages are prevented by default."""
    memory = ConversationMemory()

    message = {"id": "msg_123", "role": "user", "content": "Hello"}

    # Add same message twice
    await memory.add(message)
    await memory.add(message)

    # Should only have one message
    assert await memory.size() == 1
    print("✅ Duplicate prevention works")


@pytest.mark.asyncio
async def test_allow_duplicates():
    """Test allowing duplicate messages when explicitly enabled."""
    memory = ConversationMemory()

    message = {"id": "msg_123", "role": "user", "content": "Hello"}

    # Add same message twice with allow_duplicates=True
    await memory.add(message, allow_duplicates=True)
    await memory.add(message, allow_duplicates=True)

    # Should have two messages
    assert await memory.size() == 2
    print("✅ Allowing duplicates works")


@pytest.mark.asyncio
async def test_delete_by_index():
    """Test deleting messages by index."""
    memory = ConversationMemory()

    messages = [
        {"role": "user", "content": "Message 1"},
        {"role": "assistant", "content": "Message 2"},
        {"role": "user", "content": "Message 3"},
    ]
    await memory.add(messages)

    # Delete middle message
    await memory.delete(1)

    assert await memory.size() == 2
    retrieved = await memory.get_messages()
    assert retrieved[0]["content"] == "Message 1"
    assert retrieved[1]["content"] == "Message 3"
    print("✅ Deleting by index works")


@pytest.mark.asyncio
async def test_delete_multiple_indices():
    """Test deleting multiple messages at once."""
    memory = ConversationMemory()

    messages = [{"role": "user", "content": f"Message {i}"} for i in range(5)]
    await memory.add(messages)

    # Delete indices 1 and 3
    await memory.delete([1, 3])

    assert await memory.size() == 3
    retrieved = await memory.get_messages()
    assert retrieved[0]["content"] == "Message 0"
    assert retrieved[1]["content"] == "Message 2"
    assert retrieved[2]["content"] == "Message 4"
    print("✅ Deleting multiple indices works")


@pytest.mark.asyncio
async def test_delete_invalid_index():
    """Test that deleting invalid index raises error."""
    memory = ConversationMemory()

    await memory.add({"role": "user", "content": "Hello"})

    # Try to delete out of range index
    with pytest.raises(IndexError):
        await memory.delete(10)

    print("✅ Invalid index deletion raises error correctly")


@pytest.mark.asyncio
async def test_get_last_message():
    """Test getting the last message."""
    memory = ConversationMemory()

    # Empty memory
    assert await memory.get_last_message() is None

    # Add messages
    messages = [
        {"role": "user", "content": "First"},
        {"role": "assistant", "content": "Second"},
        {"role": "user", "content": "Third"},
    ]
    await memory.add(messages)

    last = await memory.get_last_message()
    assert last is not None
    assert last["content"] == "Third"
    print("✅ Getting last message works")


@pytest.mark.asyncio
async def test_get_messages_by_role():
    """Test filtering messages by role."""
    memory = ConversationMemory()

    messages = [
        {"role": "user", "content": "User 1"},
        {"role": "assistant", "content": "Assistant 1"},
        {"role": "user", "content": "User 2"},
        {"role": "assistant", "content": "Assistant 2"},
        {"role": "system", "content": "System 1"},
    ]
    await memory.add(messages)

    user_messages = await memory.get_messages_by_role("user")
    assert len(user_messages) == 2
    assert all(msg["role"] == "user" for msg in user_messages)

    assistant_messages = await memory.get_messages_by_role("assistant")
    assert len(assistant_messages) == 2
    assert all(msg["role"] == "assistant" for msg in assistant_messages)

    system_messages = await memory.get_messages_by_role("system")
    assert len(system_messages) == 1

    print("✅ Filtering by role works")


@pytest.mark.asyncio
async def test_get_messages_with_limit():
    """Test getting messages with limit."""
    memory = ConversationMemory()

    messages = [{"role": "user", "content": f"Message {i}"} for i in range(10)]
    await memory.add(messages)

    # Get last 3 messages
    recent = await memory.get_messages(limit=3)
    assert len(recent) == 3
    assert recent[0]["content"] == "Message 7"
    assert recent[1]["content"] == "Message 8"
    assert recent[2]["content"] == "Message 9"
    print("✅ Getting messages with limit works")


@pytest.mark.asyncio
async def test_truncate_to_size():
    """Test truncating memory to a maximum size."""
    memory = ConversationMemory()

    messages = [{"role": "user", "content": f"Message {i}"} for i in range(10)]
    await memory.add(messages)

    # Truncate to last 5 messages
    await memory.truncate_to_size(5)

    assert await memory.size() == 5
    retrieved = await memory.get_messages()
    assert retrieved[0]["content"] == "Message 5"
    assert retrieved[4]["content"] == "Message 9"
    print("✅ Truncating to size works")


@pytest.mark.asyncio
async def test_clear_memory():
    """Test clearing all messages from memory."""
    memory = ConversationMemory()

    messages = [{"role": "user", "content": f"Message {i}"} for i in range(5)]
    await memory.add(messages)

    assert await memory.size() == 5

    await memory.clear()

    assert await memory.size() == 0
    assert await memory.get_messages() == []
    print("✅ Clearing memory works")


@pytest.mark.asyncio
async def test_state_dict_serialization():
    """Test state serialization and deserialization."""
    memory1 = ConversationMemory()

    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi!"},
    ]
    await memory1.add(messages)

    # Export state
    state = memory1.state_dict()
    assert "messages" in state
    assert len(state["messages"]) == 2

    # Load into new memory
    memory2 = ConversationMemory()
    memory2.load_state_dict(state)

    assert await memory2.size() == 2
    retrieved = await memory2.get_messages()
    assert retrieved[0]["content"] == "Hello"
    assert retrieved[1]["content"] == "Hi!"
    print("✅ State serialization works")


@pytest.mark.asyncio
async def test_state_dict_strict_mode():
    """Test state loading with strict mode validation."""
    memory = ConversationMemory()

    # Invalid state dict (missing 'messages' key)
    invalid_state = {"wrong_key": []}

    # Should raise error in strict mode
    with pytest.raises(ValueError):
        memory.load_state_dict(invalid_state, strict=True)

    # Should not raise error in non-strict mode
    memory.load_state_dict(invalid_state, strict=False)
    assert await memory.size() == 0

    print("✅ State dict strict mode works")


@pytest.mark.asyncio
async def test_add_none_message():
    """Test that adding None message is handled gracefully."""
    memory = ConversationMemory()

    await memory.add(None)
    assert await memory.size() == 0
    print("✅ Adding None message handled gracefully")


@pytest.mark.asyncio
async def test_add_invalid_message_type():
    """Test that adding invalid message type raises error."""
    memory = ConversationMemory()

    # Try to add a string instead of dict
    with pytest.raises(TypeError):
        await memory.add("invalid message")

    # Try to add list of non-dicts
    with pytest.raises(TypeError):
        await memory.add(["invalid", "messages"])

    print("✅ Invalid message type raises error correctly")


@pytest.mark.asyncio
async def test_retrieve_not_implemented():
    """Test that retrieve method raises NotImplementedError."""
    memory = ConversationMemory()

    with pytest.raises(NotImplementedError):
        await memory.retrieve("some query")

    print("✅ Retrieve method correctly not implemented")


@pytest.mark.asyncio
async def test_message_isolation():
    """Test that returned messages are copies, not references."""
    memory = ConversationMemory()

    original = {"role": "user", "content": "Original"}
    await memory.add(original)

    # Get messages and modify
    retrieved = await memory.get_messages()
    retrieved[0]["content"] = "Modified"

    # Original in memory should be unchanged
    messages = await memory.get_messages()
    assert messages[0]["content"] == "Original"
    print("✅ Message isolation works correctly")


if __name__ == "__main__":
    import asyncio

    async def run_all_tests():
        """Run all tests manually."""
        print("\n=== Running ConversationMemory Tests ===\n")

        await test_conversation_memory_initialization()
        await test_add_single_message()
        await test_add_multiple_messages()
        await test_duplicate_prevention()
        await test_allow_duplicates()
        await test_delete_by_index()
        await test_delete_multiple_indices()
        await test_delete_invalid_index()
        await test_get_last_message()
        await test_get_messages_by_role()
        await test_get_messages_with_limit()
        await test_truncate_to_size()
        await test_clear_memory()
        await test_state_dict_serialization()
        await test_state_dict_strict_mode()
        await test_add_none_message()
        await test_add_invalid_message_type()
        await test_retrieve_not_implemented()
        await test_message_isolation()

        print("\n=== All ConversationMemory Tests Passed! ===\n")

    asyncio.run(run_all_tests())
