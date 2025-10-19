# -*- coding: utf-8 -*-
"""
Persistent memory implementation for MassGen using mem0.

This module provides long-term memory storage with semantic retrieval capabilities,
enabling agents to remember and recall information across multiple sessions.
"""

import json
from importlib import metadata
from typing import Any, Dict, List, Optional, TYPE_CHECKING, Union

from pydantic import field_validator

from ._base import PersistentMemoryBase

if TYPE_CHECKING:
    from mem0.configs.base import MemoryConfig
    from mem0.vector_stores.configs import VectorStoreConfig
else:
    MemoryConfig = Any
    VectorStoreConfig = Any


def _create_massgen_mem0_config_classes():
    """
    Create custom config classes for MassGen mem0 integration.

    This is necessary because mem0's default validation hardcodes provider names.
    We override the validation to accept 'massgen' as a valid provider.
    """
    from mem0.embeddings.configs import EmbedderConfig
    from mem0.llms.configs import LlmConfig

    class _MassGenLlmConfig(LlmConfig):
        """Custom LLM config that accepts MassGen backends."""

        @field_validator("config")
        @classmethod
        def validate_config(cls, v: Any, values: Any) -> Any:
            """Validate LLM configuration with MassGen provider support."""
            from mem0.utils.factory import LlmFactory

            provider = values.data.get("provider")
            if provider in LlmFactory.provider_to_class:
                return v
            # If provider is not in factory but config is valid, allow it
            # This supports custom providers like 'massgen'
            return v

    class _MassGenEmbedderConfig(EmbedderConfig):
        """Custom embedder config that accepts MassGen backends."""

        @field_validator("config")
        @classmethod
        def validate_config(cls, v: Any, values: Any) -> Any:
            """Validate embedder configuration with MassGen provider support."""
            from mem0.utils.factory import EmbedderFactory

            provider = values.data.get("provider")
            if provider in EmbedderFactory.provider_to_class:
                return v
            # Allow custom providers
            return v

    return _MassGenLlmConfig, _MassGenEmbedderConfig


class PersistentMemory(PersistentMemoryBase):
    """
    Long-term persistent memory using mem0 as the storage backend.

    This memory system provides:
    - Semantic search across historical conversations
    - Automatic memory summarization and organization
    - Persistent storage across sessions
    - Metadata-based filtering (agent, user, session)

    Example:
        >>> # Initialize with MassGen backends
        >>> memory = PersistentMemory(
        ...     agent_name="research_agent",
        ...     llm_backend=my_llm_backend,
        ...     embedding_backend=my_embedding_backend
        ... )
        >>>
        >>> # Record information
        >>> await memory.record([
        ...     {"role": "user", "content": "What is quantum computing?"},
        ...     {"role": "assistant", "content": "Quantum computing uses..."}
        ... ])
        >>>
        >>> # Retrieve relevant memories
        >>> relevant = await memory.retrieve("quantum computing concepts")
    """

    def __init__(
        self,
        agent_name: Optional[str] = None,
        user_name: Optional[str] = None,
        session_name: Optional[str] = None,
        llm_backend: Optional[Any] = None,
        embedding_backend: Optional[Any] = None,
        vector_store_config: Optional[VectorStoreConfig] = None,
        mem0_config: Optional[MemoryConfig] = None,
        memory_type: str = "semantic",
        **kwargs: Any,
    ) -> None:
        """
        Initialize persistent memory with mem0 backend.

        Args:
            agent_name: Name/ID of the agent (used for memory filtering)
            user_name: Name/ID of the user (used for memory filtering)
            session_name: Name/ID of the session (used for memory filtering)

        Note:
            At least one of agent_name, user_name, or session_name is required.
            These serve as metadata for organizing and filtering memories.

            llm_backend: MassGen LLM backend for memory summarization
            embedding_backend: MassGen embedding backend for vector search
            vector_store_config: mem0 vector store configuration
            mem0_config: Full mem0 configuration (overrides individual configs)
            memory_type: Type of memory storage ('semantic' or 'procedural')
            **kwargs: Additional options (e.g., on_disk=True for persistence)

        Raises:
            ValueError: If neither mem0_config nor required backends are provided
            ImportError: If mem0 library is not installed
        """
        super().__init__()

        # Import and configure mem0
        try:
            import mem0
            from mem0.configs.llms.base import BaseLlmConfig
            from mem0.utils.factory import LlmFactory, EmbedderFactory
            from packaging import version

            # Check mem0 version for compatibility
            current_version = metadata.version("mem0ai")
            is_legacy_version = version.parse(current_version) <= version.parse(
                "0.1.115"
            )

            # Register MassGen adapters with mem0's factory system
            EmbedderFactory.provider_to_class[
                "massgen"
            ] = "massgen.memory._mem0_adapters.MassGenEmbeddingAdapter"

            if is_legacy_version:
                LlmFactory.provider_to_class[
                    "massgen"
                ] = "massgen.memory._mem0_adapters.MassGenLLMAdapter"
            else:
                # Newer mem0 versions use tuple format
                LlmFactory.provider_to_class["massgen"] = (
                    "massgen.memory._mem0_adapters.MassGenLLMAdapter",
                    BaseLlmConfig,
                )

        except ImportError as e:
            raise ImportError(
                "mem0 library is required for persistent memory. "
                "Install it with: pip install mem0ai"
            ) from e

        # Create custom config classes
        _LlmConfig, _EmbedderConfig = _create_massgen_mem0_config_classes()

        # Validate metadata requirements
        if not any([agent_name, user_name, session_name]):
            raise ValueError(
                "At least one of agent_name, user_name, or session_name must be provided "
                "to organize memories."
            )

        # Store identifiers for memory operations
        self.agent_id = agent_name
        self.user_id = user_name
        self.session_id = session_name

        # Configure mem0 instance
        if mem0_config is not None:
            # Use provided mem0_config, optionally overriding components
            if llm_backend is not None:
                mem0_config.llm = _LlmConfig(
                    provider="massgen",
                    config={"model": llm_backend},
                )

            if embedding_backend is not None:
                mem0_config.embedder = _EmbedderConfig(
                    provider="massgen",
                    config={"model": embedding_backend},
                )

            if vector_store_config is not None:
                mem0_config.vector_store = vector_store_config

        else:
            # Build mem0_config from scratch
            if llm_backend is None or embedding_backend is None:
                raise ValueError(
                    "Both llm_backend and embedding_backend are required "
                    "when mem0_config is not provided."
                )

            mem0_config = mem0.configs.base.MemoryConfig(
                llm=_LlmConfig(
                    provider="massgen",
                    config={"model": llm_backend},
                ),
                embedder=_EmbedderConfig(
                    provider="massgen",
                    config={"model": embedding_backend},
                ),
            )

            # Configure vector store
            if vector_store_config is not None:
                mem0_config.vector_store = vector_store_config
            else:
                # Default to Qdrant with disk persistence
                persist = kwargs.get("on_disk", True)
                mem0_config.vector_store = mem0.vector_stores.configs.VectorStoreConfig(
                    config={"on_disk": persist}
                )

        # Initialize async mem0 instance
        self.mem0_memory = mem0.AsyncMemory(mem0_config)
        self.default_memory_type = memory_type

    async def save_to_memory(
        self,
        thinking: str,
        content: List[str],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Agent tool: Explicitly save important information to memory.

        This method is exposed as a tool that agents can call to save information
        they determine is important for future reference.

        Args:
            thinking: Agent's reasoning about why this information matters
            content: List of information items to save

        Returns:
            Dictionary with 'success' status and 'memory_ids' of saved items

        Example:
            >>> result = await memory.save_to_memory(
            ...     thinking="User mentioned their birthday",
            ...     content=["User's birthday is March 15"]
            ... )
            >>> print(result['success'])  # True
        """
        try:
            # Combine thinking and content for better context
            full_content = []
            if thinking:
                full_content.append(f"Context: {thinking}")
            full_content.extend(content)

            # Record to mem0
            results = await self._mem0_add(
                [
                    {
                        "role": "assistant",
                        "content": "\n".join(full_content),
                        "name": "memory_save",
                    }
                ],
                **kwargs,
            )

            return {
                "success": True,
                "message": f"Successfully saved {len(content)} items to memory",
                "memory_ids": results.get("results", []),
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Error saving to memory: {str(e)}",
                "memory_ids": [],
            }

    async def recall_from_memory(
        self,
        keywords: List[str],
        limit: int = 5,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Agent tool: Retrieve memories based on keywords.

        This method is exposed as a tool that agents can call to search their
        long-term memory for relevant information.

        Args:
            keywords: Keywords to search for (names, dates, topics, etc.)
            limit: Maximum number of memories to retrieve per keyword

        Returns:
            Dictionary with 'success' status and 'memories' list

        Example:
            >>> result = await memory.recall_from_memory(
            ...     keywords=["quantum computing", "algorithms"]
            ... )
            >>> for memory in result['memories']:
            ...     print(memory)
        """
        try:
            all_memories = []

            for keyword in keywords:
                search_result = await self.mem0_memory.search(
                    query=keyword,
                    agent_id=self.agent_id,
                    user_id=self.user_id,
                    run_id=self.session_id,
                    limit=limit,
                )

                if search_result and "results" in search_result:
                    memories = [
                        item["memory"] for item in search_result["results"]
                    ]
                    all_memories.extend(memories)

            return {
                "success": True,
                "memories": all_memories,
                "count": len(all_memories),
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Error retrieving memories: {str(e)}",
                "memories": [],
            }

    async def record(
        self,
        messages: List[Dict[str, Any]],
        memory_type: Optional[str] = None,
        infer: bool = True,
        **kwargs: Any,
    ) -> None:
        """
        Developer interface: Record conversation messages to persistent memory.

        This is called automatically by the framework to save conversation history.

        Args:
            messages: List of message dictionaries to record
            memory_type: Type of memory ('semantic' or 'procedural')
            infer: Whether to let mem0 infer key information
            **kwargs: Additional mem0 recording options
        """
        if not messages:
            return

        # Filter out None values
        valid_messages = [msg for msg in messages if msg is not None]

        if not valid_messages:
            return

        # Convert to mem0 format
        mem0_messages = [
            {
                "role": "assistant",
                "content": "\n".join([
                    f"{msg.get('role', 'unknown')}: {msg.get('content', '')}"
                    for msg in valid_messages
                ]),
                "name": "conversation",
            }
        ]

        await self._mem0_add(
            mem0_messages,
            memory_type=memory_type,
            infer=infer,
            **kwargs,
        )

    async def _mem0_add(
        self,
        messages: Union[str, List[Dict]],
        memory_type: Optional[str] = None,
        infer: bool = True,
        **kwargs: Any,
    ) -> Dict:
        """
        Internal helper to add memories to mem0.

        Args:
            messages: String or message dictionaries to store
            memory_type: Override default memory type
            infer: Whether mem0 should infer structured information
            **kwargs: Additional mem0 options

        Returns:
            mem0 add operation result
        """
        results = await self.mem0_memory.add(
            messages=messages,
            agent_id=self.agent_id,
            user_id=self.user_id,
            run_id=self.session_id,
            memory_type=memory_type or self.default_memory_type,
            infer=infer,
            **kwargs,
        )
        return results

    async def retrieve(
        self,
        query: Union[str, Dict[str, Any], List[Dict[str, Any]]],
        limit: int = 5,
        **kwargs: Any,
    ) -> str:
        """
        Developer interface: Retrieve relevant memories for a query.

        This is called automatically by the framework to inject relevant
        historical knowledge into the current conversation.

        Args:
            query: Query string or message(s) to search for
            limit: Maximum number of memories to retrieve
            **kwargs: Additional mem0 search options

        Returns:
            Formatted string of retrieved memories
        """
        # Convert query to string format
        query_strings = []

        if isinstance(query, str):
            query_strings = [query]
        elif isinstance(query, dict):
            # Single message dict
            content = query.get("content", "")
            if content:
                query_strings = [str(content)]
        elif isinstance(query, list):
            # List of message dicts
            for msg in query:
                if isinstance(msg, dict):
                    content = msg.get("content", "")
                    if content:
                        query_strings.append(str(content))

        if not query_strings:
            return ""

        # Search mem0 for each query string
        all_results = []
        for query_str in query_strings:
            search_result = await self.mem0_memory.search(
                query=query_str,
                agent_id=self.agent_id,
                user_id=self.user_id,
                run_id=self.session_id,
                limit=limit,
            )

            if search_result and "results" in search_result:
                memories = [item["memory"] for item in search_result["results"]]
                all_results.extend(memories)

        # Format results as a readable string
        return "\n".join(all_results) if all_results else ""
