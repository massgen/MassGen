# -*- coding: utf-8 -*-
"""
Base classes for MassGen memory system.

This module defines the abstract interfaces that all memory implementations
must follow, ensuring consistency across different storage backends.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Union


class MemoryBase(ABC):
    """
    Abstract base class for memory storage in MassGen.

    All memory implementations (conversation, persistent, etc.) should inherit
    from this class and implement the required methods.
    """

    @abstractmethod
    async def add(self, *args: Any, **kwargs: Any) -> None:
        """
        Add new items to memory.

        Args:
            *args: Variable positional arguments
            **kwargs: Variable keyword arguments
        """

    @abstractmethod
    async def delete(self, *args: Any, **kwargs: Any) -> None:
        """
        Remove items from memory.

        Args:
            *args: Variable positional arguments
            **kwargs: Variable keyword arguments
        """

    @abstractmethod
    async def retrieve(self, *args: Any, **kwargs: Any) -> Any:
        """
        Retrieve items from memory based on query.

        Args:
            *args: Variable positional arguments
            **kwargs: Variable keyword arguments

        Returns:
            Retrieved memory content
        """

    @abstractmethod
    async def size(self) -> int:
        """
        Get the current size of the memory.

        Returns:
            Number of items in memory
        """

    @abstractmethod
    async def clear(self) -> None:
        """Clear all content from memory."""

    @abstractmethod
    async def get_messages(self, *args: Any, **kwargs: Any) -> List[Dict[str, Any]]:
        """
        Get the stored messages in a format suitable for LLM consumption.

        Returns:
            List of message dictionaries
        """

    @abstractmethod
    def state_dict(self) -> Dict[str, Any]:
        """
        Export memory state for serialization.

        Returns:
            Dictionary containing the memory state
        """

    @abstractmethod
    def load_state_dict(self, state_dict: Dict[str, Any], strict: bool = True) -> None:
        """
        Load memory state from serialized data.

        Args:
            state_dict: Dictionary containing the memory state
            strict: If True, raise error on missing/extra keys
        """


class PersistentMemoryBase(ABC):
    """
    Abstract base class for long-term persistent memory.

    This type of memory is designed to store information across sessions,
    with support for semantic retrieval and knowledge management.

    Two modes of operation:
    1. Developer-controlled: Use `record()` and `retrieve()` methods programmatically
    2. Agent-controlled: Agent calls `save_to_memory()` and `recall_from_memory()` tools
    """

    async def record(
        self,
        messages: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> None:
        """
        Developer interface: Record information to persistent memory.

        This method is called by the framework to automatically save important
        information from conversations.

        Args:
            messages: List of message dictionaries to record
            **kwargs: Additional recording options
        """
        raise NotImplementedError(
            "The `record` method is not implemented in this memory backend.",
        )

    async def retrieve(
        self,
        query: Union[str, Dict[str, Any], List[Dict[str, Any]]],
        **kwargs: Any,
    ) -> str:
        """
        Developer interface: Retrieve relevant information from persistent memory.

        This method is called by the framework to automatically inject relevant
        historical knowledge into the current conversation.

        Args:
            query: Query message(s) or string to search for
            **kwargs: Additional retrieval options

        Returns:
            Retrieved information as formatted string
        """
        raise NotImplementedError(
            "The `retrieve` method is not implemented in this memory backend.",
        )

    async def save_to_memory(
        self,
        thinking: str,
        content: List[str],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Agent tool interface: Save important information to memory.

        This is a tool function that agents can call to explicitly save
        information they deem important for future reference.

        Args:
            thinking: Agent's reasoning about why this information is important
            content: List of information items to save
            **kwargs: Additional save options

        Returns:
            Tool response with status and saved memory IDs
        """
        raise NotImplementedError(
            "The `save_to_memory` tool is not implemented in this memory backend. " "Implement this method to allow agents to actively manage their memory.",
        )

    async def recall_from_memory(
        self,
        keywords: List[str],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Agent tool interface: Recall information based on keywords.

        This is a tool function that agents can call to retrieve relevant
        information from their long-term memory.

        Args:
            keywords: Keywords to search for (person names, dates, topics, etc.)
            **kwargs: Additional recall options

        Returns:
            Tool response with retrieved memories
        """
        raise NotImplementedError(
            "The `recall_from_memory` tool is not implemented in this memory backend. " "Implement this method to allow agents to actively query their memory.",
        )
