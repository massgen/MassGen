# -*- coding: utf-8 -*-
"""
Conversation memory implementation for MassGen.

This module provides in-memory storage for conversation messages, optimized
for quick access during active chat sessions.
"""

import uuid
from typing import Any, Dict, Iterable, List, Optional, Union

from ._base import MemoryBase


class ConversationMemory(MemoryBase):
    """
    In-memory storage for conversation messages.

    This memory type is designed for short-term storage of ongoing conversations.
    It keeps messages in a simple list structure for fast access and iteration.

    Features:
    - Fast in-memory access
    - Duplicate detection based on message IDs
    - Index-based deletion
    - State serialization for session persistence

    Example:
        >>> memory = ConversationMemory()
        >>> await memory.add({"role": "user", "content": "Hello"})
        >>> messages = await memory.get_messages()
        >>> print(len(messages))  # 1
    """

    def __init__(self) -> None:
        """Initialize an empty conversation memory."""
        super().__init__()
        self.messages: List[Dict[str, Any]] = []

    def state_dict(self) -> Dict[str, Any]:
        """
        Serialize memory state to a dictionary.

        Returns:
            Dictionary with 'messages' key containing all stored messages
        """
        return {
            "messages": [msg.copy() for msg in self.messages],
        }

    def load_state_dict(
        self,
        state_dict: Dict[str, Any],
        strict: bool = True,
    ) -> None:
        """
        Load memory state from a serialized dictionary.

        Args:
            state_dict: Dictionary containing 'messages' key
            strict: If True, validates the state dictionary structure

        Raises:
            ValueError: If strict=True and state_dict is invalid
        """
        if strict and "messages" not in state_dict:
            raise ValueError(
                "State dictionary must contain 'messages' key when strict=True"
            )

        self.messages = []
        for msg_data in state_dict.get("messages", []):
            # Ensure each message is a proper dictionary
            if isinstance(msg_data, dict):
                self.messages.append(msg_data.copy())

    async def size(self) -> int:
        """
        Get the number of messages in memory.

        Returns:
            Count of stored messages
        """
        return len(self.messages)

    async def retrieve(self, *args: Any, **kwargs: Any) -> None:
        """
        Retrieve is not supported for basic conversation memory.

        Use get_messages() to access all messages directly.

        Raises:
            NotImplementedError: Always, as basic retrieval is not supported
        """
        raise NotImplementedError(
            f"The retrieve method is not implemented in {self.__class__.__name__}. "
            "Use get_messages() to access conversation history directly."
        )

    async def delete(self, index: Union[Iterable, int]) -> None:
        """
        Delete message(s) by index position.

        Args:
            index: Single index or iterable of indices to delete

        Raises:
            IndexError: If any index is out of range

        Example:
            >>> await memory.delete(0)  # Delete first message
            >>> await memory.delete([1, 3, 5])  # Delete multiple messages
        """
        if isinstance(index, int):
            index = [index]

        # Validate all indices first
        invalid_indices = [i for i in index if i < 0 or i >= len(self.messages)]

        if invalid_indices:
            raise IndexError(
                f"The following indices do not exist: {invalid_indices}. "
                f"Valid range is 0-{len(self.messages) - 1}"
            )

        # Create new list excluding deleted indices
        self.messages = [
            msg for idx, msg in enumerate(self.messages) if idx not in index
        ]

    async def add(
        self,
        messages: Union[List[Dict[str, Any]], Dict[str, Any], None],
        allow_duplicates: bool = False,
    ) -> None:
        """
        Add one or more messages to the conversation memory.

        Args:
            messages: Single message dict or list of message dicts to add.
                     Each message should have at minimum a 'role' and 'content'.
            allow_duplicates: If False, skip messages with duplicate IDs

        Raises:
            TypeError: If messages are not in the expected format

        Example:
            >>> # Add single message
            >>> await memory.add({"role": "user", "content": "Hello"})
            >>>
            >>> # Add multiple messages
            >>> await memory.add([
            ...     {"role": "user", "content": "Hi"},
            ...     {"role": "assistant", "content": "Hello!"}
            ... ])
        """
        if messages is None:
            return

        # Normalize to list
        if isinstance(messages, dict):
            messages = [messages]

        if not isinstance(messages, list):
            raise TypeError(
                f"Messages should be a list of dicts or a single dict, "
                f"but got {type(messages)}"
            )

        # Validate each message
        for msg in messages:
            if not isinstance(msg, dict):
                raise TypeError(
                    f"Each message should be a dictionary, but got {type(msg)}"
                )

        # Add message IDs if not present (for duplicate detection)
        processed_messages = []
        for msg in messages:
            msg_copy = msg.copy()
            if "id" not in msg_copy:
                msg_copy["id"] = f"msg_{uuid.uuid4().hex[:12]}"
            processed_messages.append(msg_copy)

        # Filter duplicates if needed
        if not allow_duplicates:
            existing_ids = {msg.get("id") for msg in self.messages if "id" in msg}
            processed_messages = [
                msg for msg in processed_messages
                if msg.get("id") not in existing_ids
            ]

        self.messages.extend(processed_messages)

    async def get_messages(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get all messages in the conversation.

        Args:
            limit: Optional limit on number of most recent messages to return

        Returns:
            List of message dictionaries (copies, not references)

        Example:
            >>> # Get all messages
            >>> all_msgs = await memory.get_messages()
            >>>
            >>> # Get last 10 messages
            >>> recent = await memory.get_messages(limit=10)
        """
        if limit is not None and limit > 0:
            return [msg.copy() for msg in self.messages[-limit:]]
        return [msg.copy() for msg in self.messages]

    async def clear(self) -> None:
        """
        Remove all messages from memory.

        Example:
            >>> await memory.clear()
            >>> assert await memory.size() == 0
        """
        self.messages = []

    async def get_last_message(self) -> Optional[Dict[str, Any]]:
        """
        Get the most recent message.

        Returns:
            Last message dictionary, or None if memory is empty
        """
        if not self.messages:
            return None
        return self.messages[-1].copy()

    async def get_messages_by_role(self, role: str) -> List[Dict[str, Any]]:
        """
        Filter messages by role.

        Args:
            role: Role to filter by (e.g., 'user', 'assistant', 'system')

        Returns:
            List of messages with matching role
        """
        return [msg.copy() for msg in self.messages if msg.get("role") == role]

    async def truncate_to_size(self, max_messages: int) -> None:
        """
        Keep only the most recent messages up to max_messages.

        This is useful for managing memory usage in long conversations.

        Args:
            max_messages: Maximum number of messages to keep

        Example:
            >>> # Keep only last 100 messages
            >>> await memory.truncate_to_size(100)
        """
        if max_messages < len(self.messages):
            self.messages = self.messages[-max_messages:]
