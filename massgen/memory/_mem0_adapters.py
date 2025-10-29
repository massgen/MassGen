# -*- coding: utf-8 -*-
"""
Adapters for integrating MassGen backends with mem0 library.

This module provides bridge classes that allow MassGen's LLM and embedding
backends to work seamlessly with the mem0 memory system.
"""

import asyncio
import concurrent.futures
from typing import (
    TYPE_CHECKING,
    Any,
    Coroutine,
    Dict,
    List,
    Literal,
    Optional,
    TypeVar,
    Union,
)

from mem0.embeddings.base import EmbeddingBase
from mem0.llms.base import LLMBase

T = TypeVar("T")

if TYPE_CHECKING:
    from mem0.configs.embeddings.base import BaseEmbedderConfig
    from mem0.configs.llms.base import BaseLlmConfig
else:
    BaseEmbedderConfig = Any
    BaseLlmConfig = Any


def _run_async_safely(coro: Coroutine[Any, Any, T]) -> T:
    """
    Run async code properly, handling both sync and nested async contexts.

    This is needed because mem0's sync adapter interface (LLMBase.generate_response,
    EmbeddingBase.embed) can be called from async contexts when using AsyncMemory.

    The problem with naive asyncio.run():
    - If we're already in an event loop, asyncio.run() raises RuntimeError
    - If we force a new loop, httpcore connections get confused about which loop owns them
    - This causes "async generator ignored GeneratorExit" and lifecycle errors

    Solution:
    - Detect if we're in an async context (running event loop exists)
    - If YES: Run the coroutine in a separate thread with its own event loop
    - If NO: Use asyncio.run() normally

    Args:
        coro: Coroutine to execute

    Returns:
        Result of the coroutine

    Example:
        >>> async def get_data():
        ...     return "data"
        >>> result = _run_async_safely(get_data())  # Works in both sync and async contexts
    """
    try:
        # Check if we're already in an event loop
        asyncio.get_running_loop()

        # We are in an async context - run in a thread pool to avoid conflicts
        # This gives the coroutine its own event loop in a separate thread
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()

    except RuntimeError:
        # No running loop - safe to use asyncio.run() directly
        return asyncio.run(coro)


class MassGenLLMAdapter(LLMBase):
    """
    Adapter that wraps MassGen LLM backends for use with mem0.

    This allows mem0 to use any MassGen-compatible LLM backend for
    memory inference and summarization tasks.
    """

    def __init__(self, config: Optional[BaseLlmConfig] = None):
        """
        Initialize the adapter with a MassGen backend.

        Args:
            config: mem0 LLM configuration containing the MassGen backend instance
        """
        super().__init__(config)

        if self.config.model is None:
            raise ValueError("The 'model' parameter is required in config")

        # Store the MassGen backend instance
        # This should be a MassGen LLMBackend instance
        self.massgen_backend = self.config.model

    def generate_response(
        self,
        messages: List[Dict[str, str]],
        response_format: Optional[Any] = None,
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto",
    ) -> str:
        """
        Generate a response using the MassGen backend.

        Args:
            messages: List of message dicts with 'role' and 'content'
            response_format: Response format specification (not used)
            tools: Available tools (not used for memory operations)
            tool_choice: Tool selection strategy (not used)

        Returns:
            Generated response text

        Note:
            This method handles the async-to-sync conversion required by mem0's
            synchronous interface.
        """
        try:
            # Convert messages to MassGen format if needed
            massgen_messages = []
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")

                # Only include valid message roles
                if role in ["system", "user", "assistant", "tool"]:
                    massgen_messages.append(
                        {
                            "role": role,
                            "content": content,
                        },
                    )

            if not massgen_messages:
                return ""

            # Call the MassGen backend asynchronously
            async def _async_generate():
                # MassGen backends use stream_with_tools() method
                # We collect the streaming response into a single string
                response_text = ""

                async for chunk in self.massgen_backend.stream_with_tools(
                    messages=massgen_messages,
                    tools=tools or [],
                ):
                    # Extract text content from chunks
                    if hasattr(chunk, "content") and chunk.content:
                        response_text += chunk.content
                    elif hasattr(chunk, "type"):
                        # Handle different chunk types
                        if chunk.type == "content" and hasattr(chunk, "content"):
                            response_text += chunk.content or ""

                return response_text

            # Run the async function safely (handles both sync and async contexts)
            result = _run_async_safely(_async_generate())
            return result

        except Exception as e:
            raise RuntimeError(
                f"Error generating response with MassGen backend: {str(e)}",
            ) from e


class MassGenEmbeddingAdapter(EmbeddingBase):
    """
    Adapter that wraps MassGen embedding backends for use with mem0.

    This enables mem0 to use any MassGen-compatible embedding model for
    creating vector representations of memories.

    NOTE: Currently, we do not have any MassGen embedding backends integrated,
    so this adapter serves as a template for future implementations.
    """

    def __init__(self, config: Optional[BaseEmbedderConfig] = None):
        """
        Initialize the adapter with a MassGen embedding backend.

        Args:
            config: mem0 embedder configuration containing the MassGen backend
        """
        super().__init__(config)

        if self.config.model is None:
            raise ValueError("The 'model' parameter is required in config")

        # Store the MassGen embedding backend
        self.massgen_backend = self.config.model

    def embed(
        self,
        text: Union[str, List[str]],
        memory_action: Optional[Literal["add", "search", "update"]] = None,
    ) -> List[float]:
        """
        Generate embeddings using the MassGen backend.

        Args:
            text: Text string or list of strings to embed
            memory_action: Type of memory operation (not currently used)

        Returns:
            Embedding vector as list of floats

        Note:
            If text is a list, only the first element's embedding is returned,
            as mem0 typically processes one item at a time.
        """
        try:
            # Normalize input to list format
            text_list = [text] if isinstance(text, str) else text

            # Call the MassGen embedding backend asynchronously
            async def _async_embed():
                # MassGen embedding backends typically have an async call method
                # or similar interface
                if hasattr(self.massgen_backend, "__call__"):
                    response = await self.massgen_backend(text_list)
                elif hasattr(self.massgen_backend, "embed"):
                    response = await self.massgen_backend.embed(text_list)
                else:
                    raise AttributeError(
                        "MassGen backend must have __call__ or embed method",
                    )

                return response

            # Run async call safely (handles both sync and async contexts)
            response = _run_async_safely(_async_embed())

            # Extract embedding vector from response
            # MassGen embedding response format: response.embeddings[0]
            if hasattr(response, "embeddings") and response.embeddings:
                embedding = response.embeddings[0]

                # Handle both list and numpy array formats
                if hasattr(embedding, "tolist"):
                    return embedding.tolist()
                return list(embedding)

            raise ValueError("Could not extract embedding from backend response")

        except Exception as e:
            raise RuntimeError(
                f"Error generating embedding with MassGen backend: {str(e)}",
            ) from e
