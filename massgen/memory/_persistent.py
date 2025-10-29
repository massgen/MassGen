# -*- coding: utf-8 -*-
"""
Persistent memory implementation for MassGen using mem0.

This module provides long-term memory storage with semantic retrieval capabilities,
enabling agents to remember and recall information across multiple sessions.
"""

from importlib import metadata
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from pydantic import field_validator

from ._base import PersistentMemoryBase
from ._fact_extraction_prompts import get_fact_extraction_prompt

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
        llm_config: Optional[Dict[str, Any]] = None,
        embedding_backend: Optional[Any] = None,
        embedding_config: Optional[Dict[str, Any]] = None,
        vector_store_config: Optional[VectorStoreConfig] = None,
        mem0_config: Optional[MemoryConfig] = None,
        memory_type: Optional[str] = None,
        qdrant_client: Optional[Any] = None,
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

            llm_backend: DEPRECATED. Use llm_config instead.
                Legacy support: MassGen LLM backend object (uses MassGenLLMAdapter)

            llm_config: RECOMMENDED. Configuration dict for mem0's native LLMs.
                Supports mem0's built-in providers: openai, anthropic, groq, together, etc.
                Example: {"provider": "openai", "model": "gpt-4.1-nano-2025-04-14", "api_key": "..."}
                Default: {"provider": "openai", "model": "gpt-4.1-nano-2025-04-14"} if not specified

                When to use each approach:
                - Use llm_config (native mem0): For standard providers (OpenAI, Anthropic, etc.)
                  Simpler, no adapter overhead, no async complexity, direct mem0 integration
                - Use llm_backend (custom): Only if you need a custom MassGen backend
                  that mem0 doesn't natively support (requires async adapter)

            embedding_backend: DEPRECATED. Use embedding_config instead.
                Legacy support: MassGen embedding backend object (uses MassGenEmbeddingAdapter)

            embedding_config: RECOMMENDED. Configuration dict for mem0's native embedders.
                Supports mem0's built-in providers: openai, together, azure_openai, gemini, etc.
                Example: {"provider": "openai", "model": "text-embedding-3-small", "api_key": "..."}

                When to use each approach:
                - Use embedding_config (native mem0): For standard providers (OpenAI, Together, etc.)
                  Simpler, no adapter overhead, direct mem0 integration
                - Use embedding_backend (custom): Only if you need a custom MassGen backend
                  that mem0 doesn't natively support

            vector_store_config: mem0 vector store configuration
            mem0_config: Full mem0 configuration (overrides individual configs)
            memory_type: Type of memory storage (None for semantic, "procedural_memory" for procedural)
            qdrant_client: Optional shared QdrantClient instance (for multi-agent concurrent access)
                Note: Local file-based Qdrant doesn't support concurrent access.
                Use qdrant_client from a Qdrant server for multi-agent scenarios.
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
            from mem0.utils.factory import EmbedderFactory, LlmFactory
            from packaging import version

            # Check mem0 version for compatibility
            current_version = metadata.version("mem0ai")
            is_legacy_version = version.parse(current_version) <= version.parse(
                "0.1.115",
            )

            # Register MassGen adapters with mem0's factory system
            EmbedderFactory.provider_to_class["massgen"] = "massgen.memory._mem0_adapters.MassGenEmbeddingAdapter"

            if is_legacy_version:
                LlmFactory.provider_to_class["massgen"] = "massgen.memory._mem0_adapters.MassGenLLMAdapter"
            else:
                # Newer mem0 versions use tuple format
                LlmFactory.provider_to_class["massgen"] = (
                    "massgen.memory._mem0_adapters.MassGenLLMAdapter",
                    BaseLlmConfig,
                )

        except ImportError as e:
            raise ImportError(
                "mem0 library is required for persistent memory. " "Install it with: pip install mem0ai",
            ) from e

        # Create custom config classes
        _LlmConfig, _EmbedderConfig = _create_massgen_mem0_config_classes()

        # Validate metadata requirements
        if not any([agent_name, user_name, session_name]):
            raise ValueError(
                "At least one of agent_name, user_name, or session_name must be provided " "to organize memories.",
            )

        # Store identifiers for memory operations
        self.agent_id = agent_name
        self.user_id = user_name
        self.session_id = session_name

        # Configure mem0 instance
        if mem0_config is not None:
            # Use provided mem0_config, optionally overriding components

            # Handle LLM configuration (prefer llm_config over llm_backend)
            if llm_config is not None:
                # Use mem0's native LLM (RECOMMENDED)
                from mem0.llms.configs import LlmConfig

                mem0_config.llm = LlmConfig(**llm_config)
            elif llm_backend is not None:
                # Use custom MassGen backend via adapter (LEGACY)
                mem0_config.llm = _LlmConfig(
                    provider="massgen",
                    config={"model": llm_backend},
                )

            # Handle embedder configuration (prefer embedding_config over embedding_backend)
            if embedding_config is not None:
                # Use mem0's native embedder (RECOMMENDED)
                from mem0.embeddings.configs import EmbedderConfig

                mem0_config.embedder = EmbedderConfig(**embedding_config)
            elif embedding_backend is not None:
                # Use custom MassGen backend via adapter (LEGACY)
                mem0_config.embedder = _EmbedderConfig(
                    provider="massgen",
                    config={"model": embedding_backend},
                )

            if vector_store_config is not None:
                mem0_config.vector_store = vector_store_config

            # Add custom fact extraction prompt if not already set
            if not hasattr(mem0_config, "custom_fact_extraction_prompt") or mem0_config.custom_fact_extraction_prompt is None:
                mem0_config.custom_fact_extraction_prompt = get_fact_extraction_prompt("default")

        else:
            # Build mem0_config from scratch

            # Require at least one LLM configuration
            if llm_config is None and llm_backend is None:
                raise ValueError(
                    "Either llm_config or llm_backend is required when mem0_config is not provided.\n"
                    "RECOMMENDED: Use llm_config with mem0's native LLMs.\n"
                    "Example: llm_config={'provider': 'openai', 'model': 'gpt-4.1-nano-2025-04-14'}",
                )

            # Require at least one embedding configuration
            if embedding_config is None and embedding_backend is None:
                raise ValueError(
                    "Either embedding_config or embedding_backend is required when mem0_config is not provided.\n"
                    "RECOMMENDED: Use embedding_config with mem0's native embedders.\n"
                    "Example: embedding_config={'provider': 'openai', 'model': 'text-embedding-3-small'}",
                )

            # Configure LLM (prefer llm_config)
            if llm_config is not None:
                # Use mem0's native LLM (RECOMMENDED)
                from mem0.llms.configs import LlmConfig

                llm = LlmConfig(**llm_config)
            else:
                # Use custom MassGen backend via adapter (LEGACY)
                llm = _LlmConfig(
                    provider="massgen",
                    config={"model": llm_backend},
                )

            # Configure embedder (prefer embedding_config)
            if embedding_config is not None:
                # Use mem0's native embedder (RECOMMENDED)
                from mem0.embeddings.configs import EmbedderConfig

                embedder = EmbedderConfig(**embedding_config)
            else:
                # Use custom MassGen backend via adapter (LEGACY)
                embedder = _EmbedderConfig(
                    provider="massgen",
                    config={"model": embedding_backend},
                )

            # Add custom fact extraction prompt for better memory quality
            custom_prompt = get_fact_extraction_prompt("default")

            mem0_config = mem0.configs.base.MemoryConfig(
                llm=llm,
                embedder=embedder,
                custom_fact_extraction_prompt=custom_prompt,
            )

            # Configure vector store
            if vector_store_config is not None:
                mem0_config.vector_store = vector_store_config
            elif qdrant_client is not None:
                # Use shared Qdrant client (for multi-agent scenarios)
                # NOTE: Must be from a Qdrant server, not local file-based storage
                mem0_config.vector_store = mem0.vector_stores.configs.VectorStoreConfig(
                    config={"client": qdrant_client},
                )
            else:
                # Default to Qdrant with disk persistence (single agent only)
                # WARNING: File-based Qdrant doesn't support concurrent access
                persist = kwargs.get("on_disk", True)
                mem0_config.vector_store = mem0.vector_stores.configs.VectorStoreConfig(
                    config={"on_disk": persist},
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
                    },
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
                    memories = [item["memory"] for item in search_result["results"]]
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
        from ..logger_config import logger

        if not messages:
            return

        # Filter out None values, system messages, and messages with None/empty content
        valid_messages = []
        for msg in messages:
            if msg is None:
                continue

            # Skip system messages (orchestrator prompts, not conversation content)
            role = msg.get("role")
            if role == "system":
                logger.debug("⏭️  Skipping system message from memory recording (not conversation content)")
                continue

            # Skip messages with None or empty content
            content = msg.get("content")
            if content is None or (isinstance(content, str) and not content.strip()):
                logger.warning(f"⚠️  Skipping message with None/empty content: role={role}")
                continue

            valid_messages.append(msg)

        if not valid_messages:
            logger.warning("⚠️  No valid messages to record (all were None or empty)")
            return

        # Convert to mem0 format
        # Combine all messages into a single conversation context for mem0
        # mem0's LLM will extract facts from this combined content
        conversation_parts = []
        for msg in valid_messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            # Format: "role: content" for each message
            conversation_parts.append(f"{role}: {content}")

        mem0_messages = [
            {
                "role": "assistant",
                "content": "\n".join(conversation_parts),
                "name": "conversation",
            },
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
        from ..logger_config import logger

        try:
            # Logging - show what we're sending to mem0
            logger.info(f"🔍 [_mem0_add] Recording to mem0 (agent={self.agent_id}, session={self.session_id}, turn={kwargs.get('metadata', {}).get('turn', 'N/A')})")

            # Debug: Show message preview
            if isinstance(messages, str):
                preview = messages[:100] + "..." if len(messages) > 100 else messages
                logger.debug(f"   messages (string): {preview}")
            elif isinstance(messages, list):
                logger.debug(f"   messages: {len(messages)} message(s)")
                for i, msg in enumerate(messages[:1]):  # Show first one
                    if msg is None:
                        logger.warning(f"      ⚠️  Message [{i}] is None!")
                        continue
                    content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
                    preview = content[:100] + "..." if len(content) > 100 else content
                    logger.debug(f"      {msg.get('role', 'unknown') if isinstance(msg, dict) else 'str'}: {preview}")

            # Call mem0
            results = await self.mem0_memory.add(
                messages=messages,
                agent_id=self.agent_id,
                user_id=self.user_id,
                run_id=self.session_id,
                memory_type=memory_type or self.default_memory_type,
                infer=infer,
                **kwargs,
            )

            # Show results
            if isinstance(results, dict):
                result_count = len(results.get("results", []))
                relation_count = len(results.get("relations", []))
                logger.info(f"   ✅ mem0 extracted {result_count} fact(s), {relation_count} relation(s)")
            else:
                logger.info("   ✅ mem0.add() completed")

            return results

        except Exception as e:
            # Enhanced error logging
            logger.error(f"❌ mem0.add() failed: {type(e).__name__}: {str(e)}")
            logger.error(f"   agent_id={self.agent_id}, user_id={self.user_id}, run_id={self.session_id}")

            if "PointStruct" in str(e) or "vector" in str(e).lower():
                logger.error("   💡 Hint: This usually means embedding generation returned None")
                logger.error("   Check: 1) API key is set, 2) Model name is correct, 3) API is accessible")
                logger.error("   Debug: Run 'uv run python scripts/test_memory_setup.py' to isolate the issue")

            raise

    async def retrieve(
        self,
        query: Union[str, Dict[str, Any], List[Dict[str, Any]]],
        limit: int = 5,
        previous_winners: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> str:
        """
        Developer interface: Retrieve relevant memories for a query.

        This is called automatically by the framework to inject relevant
        historical knowledge into the current conversation.

        Args:
            query: Query string or message(s) to search for
            limit: Maximum number of memories to retrieve per agent
            previous_winners: List of previous winning agents with turns
                             Format: [{"agent_id": "agent_b", "turn": 1}, ...]
                             If provided, also searches winners' memories from their winning turns
            **kwargs: Additional mem0 search options

        Returns:
            Formatted string of retrieved memories (own + previous winners')
        """
        from ..logger_config import logger

        logger.info(f"🔍 [retrieve] Searching memories (agent={self.agent_id}, limit={limit}, winners={len(previous_winners) if previous_winners else 0})")
        logger.debug(f"   Previous winners: {previous_winners}" if previous_winners else "   No previous winners")

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
            logger.warning("   ⚠️  No valid query strings extracted")
            return ""

        logger.debug(f"   Queries: {len(query_strings)} query string(s)")

        # Search mem0 for each query string
        all_results = []

        # 1. Search own agent's memories first
        logger.debug(f"   🔎 Searching own memories ({self.agent_id})...")
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
                logger.debug(f"      → Found {len(memories)} memory/memories")
                all_results.extend(memories)

        # 2. Search previous winning agents' memories (turn-filtered)
        if previous_winners:
            logger.debug(f"   🔎 Searching {len(previous_winners)} previous winner(s)...")
            for winner in previous_winners:
                winner_agent_id = winner.get("agent_id")
                winner_turn = winner.get("turn")

                # Skip if winner is self
                if winner_agent_id == self.agent_id:
                    continue

                logger.debug(f"      → Searching {winner_agent_id} (turn {winner_turn})...")

                # Search each query string for this winner
                for query_str in query_strings:
                    search_result = await self.mem0_memory.search(
                        query=query_str,
                        agent_id=winner_agent_id,
                        user_id=self.user_id,
                        run_id=self.session_id,
                        limit=limit,
                        metadata_filters={"turn": winner_turn} if winner_turn else None,
                    )

                    if search_result and "results" in search_result:
                        memories = [f"[From {winner_agent_id} Turn {winner_turn}] {item['memory']}" for item in search_result["results"]]
                        logger.debug(f"         Found {len(memories)} memory/memories")
                        all_results.extend(memories)

        # Format results as a readable string
        logger.info(f"   ✅ Total: {len(all_results)} memories retrieved")
        if all_results:
            # Show first 2 memories as preview
            for i, mem in enumerate(all_results[:2]):
                preview = mem[:100] + "..." if len(mem) > 100 else mem
                logger.debug(f"      [{i+1}] {preview}")

        return "\n".join(all_results) if all_results else ""
