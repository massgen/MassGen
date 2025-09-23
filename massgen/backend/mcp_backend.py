from __future__ import annotations
import asyncio
from abc import abstractmethod
from typing import Dict, List, Any, AsyncGenerator, Optional, Callable

# Import base LLM backend
from .base import LLMBackend, StreamChunk
from ..logger_config import logger, log_backend_activity

# Optional MCP imports with fallbacks
try:
    from ..mcp_tools import (
        MultiMCPClient, MCPError, MCPConnectionError, 
        MCPTimeoutError, MCPServerError, Function, MCPHandler
    )
except ImportError:
    MultiMCPClient = None
    MCPError = ImportError
    MCPConnectionError = ImportError
    MCPTimeoutError = ImportError
    MCPServerError = ImportError
    Function = None
    MCPHandler = None


class MCPBackend(LLMBackend):
    """MCP-enabled backend base class that leverages the existing MCPHandler."""
    
    def __init__(self, api_key: Optional[str] = None, **kwargs):
        """Initialize MCPBackend with MCP configuration."""
        # Call parent constructor
        super().__init__(api_key, **kwargs)        
        
        # Extract MCP configuration
        self.mcp_servers = self.config.get('mcp_servers', [])
        self.allowed_tools = self.config.get('allowed_tools', None)
        self.exclude_tools = self.config.get('exclude_tools', None)
        
        # Initialize MCP state variables
        self._mcp_client: Optional[MultiMCPClient] = None
        self._mcp_initialized = False
        self._mcp_tool_calls_count = 0
        self._mcp_tool_failures = 0
        
        # Initialize circuit breaker variables
        self._circuit_breakers_enabled = self.config.get('circuit_breakers_enabled', True)

        # Initialize function registry
        self._mcp_functions: Dict[str, Function] = {}

        # Initialize thread safety
        self._stats_lock = asyncio.Lock()

        # Initialize message history limit
        self._max_mcp_message_history = self.config.get('max_mcp_message_history', 200)
        
        # Set backend identification
        self.backend_name = self.__class__.__name__
        self.agent_id = self.config.get('agent_id', None)
        
        # Initialize MCPHandler only if MCP dependencies are available
        if MCPHandler is not None:
            self.mcp_handler = MCPHandler(self)
            # Setup circuit breaker
            self.mcp_handler.setup_circuit_breaker()
        else:
            self.mcp_handler = None
    
    async def stream_with_mcp_support(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs) -> AsyncGenerator[StreamChunk, None]:
        """Coordinate MCP setup, streaming, and cleanup with comprehensive error handling."""
        async with self:
            try:
                # Check if MCP handler is available
                if self.mcp_handler is None:
                    # MCP dependencies not available, use non-MCP mode
                    yield StreamChunk(
                        type="mcp_status",
                        status="mcp_unavailable",
                        content="MCP tools not available - dependencies missing"
                    )
                    async for chunk in self._stream_without_mcp(messages, tools, **kwargs):
                        yield chunk
                    return
                
                # Determine if MCP processing is needed
                if self.mcp_handler.should_use_mcp():
                    # Yield the connected status chunk if available
                    if hasattr(self, '_mcp_connection_status_chunk') and self._mcp_connection_status_chunk:
                        yield self._mcp_connection_status_chunk

                    # Use MCP mode
                    async for chunk in self._stream_with_mcp_recursive(messages, tools, **kwargs):
                        yield chunk
                else:
                    # Show status message if needed (only when not using MCP)
                    if self.mcp_handler.should_show_no_mcp_message():
                        yield StreamChunk(
                            type="mcp_status",
                            status="mcp_unconfigured",
                            content="No MCP tools configured"
                        )

                    # Use non-MCP mode
                    async for chunk in self._stream_without_mcp(messages, tools, **kwargs):
                        yield chunk
                        
            except (MCPError, MCPConnectionError, MCPTimeoutError, MCPServerError) as e:
                logger.error(f"MCP error in {self.backend_name}: {e}")
                # Handle MCP error with fallback
                async for chunk in self._handle_mcp_error_fallback(messages, tools, e, **kwargs):
                    yield chunk
            except Exception as e:
                logger.error(f"Unexpected error in {self.backend_name}: {e}")
                # Fallback to non-MCP streaming
                async for chunk in self._stream_without_mcp(messages, tools, **kwargs):
                    yield chunk
    
    async def _stream_with_mcp_recursive(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs) -> AsyncGenerator[StreamChunk, None]:
        """Build callback functions for backend-specific operations and delegate to MCPHandler."""
        
        # Build callback functions with proper error handling
        def _build_api_params_callback():
            async def callback(msgs, tls, kwargs):
                try:
                    return await self._build_api_params(msgs, tls, kwargs)
                except Exception as e:
                    logger.error(f"Error building API params in {self.backend_name}: {e}")
                    raise
            return callback
        
        def _create_stream_callback():
            async def callback(api_params):
                try:
                    return await self._create_stream(api_params)
                except Exception as e:
                    logger.error(f"Error creating stream in {self.backend_name}: {e}")
                    raise
            return callback
        
        def _detect_function_calls_callback():
            def callback(chunk, current_call, captured_calls):
                try:
                    return self._detect_function_calls(chunk, current_call, captured_calls)
                except Exception as e:
                    logger.error(f"Error detecting function calls in {self.backend_name}: {e}")
                    return current_call, captured_calls, False
            return callback
        
        def _process_chunk_callback():
            def callback(chunk):
                try:
                    return self._process_chunk(chunk)
                except Exception as e:
                    logger.error(f"Error processing chunk in {self.backend_name}: {e}")
                    return StreamChunk(type="error", content=f"Chunk processing error: {e}")
            return callback
        
        def _format_tool_result_callback():
            def callback(tool_call, result_content):
                try:
                    return self._format_tool_result(tool_call, result_content)
                except Exception as e:
                    logger.error(f"Error formatting tool result in {self.backend_name}: {e}")
                    return {"type": "error", "content": f"Tool result formatting error: {e}"}
            return callback
        
        def _fallback_stream_callback():
            async def callback(msgs, tls, **kwargs):
                try:
                    async for chunk in self._stream_without_mcp(msgs, tls, **kwargs):
                        yield chunk
                except Exception as e:
                    logger.error(f"Error in fallback stream for {self.backend_name}: {e}")
                    yield StreamChunk(type="error", content=f"Fallback streaming error: {e}")
            return callback
        
        # Delegate to MCPHandler with callbacks
        async for chunk in self.mcp_handler.execute_mcp_functions_and_recurse(
            current_messages=messages,
            tools=tools,
            client=None,
            build_api_params_callback=_build_api_params_callback(),
            create_stream_callback=_create_stream_callback(),
            detect_function_calls_callback=_detect_function_calls_callback(),
            process_chunk_callback=_process_chunk_callback(),
            format_tool_result_callback=_format_tool_result_callback(),
            fallback_stream_callback=_fallback_stream_callback(),
            **kwargs
        ):
            yield chunk
    
    async def _handle_mcp_error_fallback(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], error: Exception, **kwargs) -> AsyncGenerator[StreamChunk, None]:
        """Enhanced error handling with correct MCPHandler fallback wiring."""

        # Build backend-specific API params (consistent usage of messages, tools, kwargs)
        api_params = await self._build_api_params(messages, tools, kwargs)

        # Determine provider-specific tools from merged configuration
        merged_params = {**self.config, **kwargs}
        provider_tools = self._get_provider_tools(merged_params)

        # Define stream function that consumes API params and yields processed chunks
        async def stream_func(params: Dict[str, Any]):
            stream = await self._create_stream(params)
            async for chunk in stream:
                processed = self._process_chunk(chunk)
                if processed.type == "complete_response":
                    # Yield the complete response then signal completion
                    yield processed
                    yield StreamChunk(type="done")
                else:
                    yield processed

        # Delegate to MCPHandler for error handling and fallback with correct signature
        async for chunk in self.mcp_handler.handle_mcp_error_and_fallback(
            error=error,
            api_params=api_params,
            provider_tools=provider_tools,
            stream_func=stream_func,
        ):
            yield chunk
    
    async def __aenter__(self):
        """Context manager entry - delegate to MCPHandler."""
        if self.mcp_handler is not None:
            await self.mcp_handler.setup_context_manager()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - delegate to MCPHandler."""
        if self.mcp_handler is not None:
            await self.mcp_handler.cleanup_mcp()
    
    # Abstract methods that must be implemented by backend-specific classes
    
    @abstractmethod
    async def _build_api_params(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build backend-specific API parameters.
        
        Each backend has different parameter requirements:
        - Response API: uses 'input' instead of 'messages', 'max_output_tokens' instead of 'max_tokens'
        - Claude: uses 'messages', 'max_tokens', specific system message handling
        - Chat Completions: uses 'messages', 'max_tokens', standard OpenAI format
        
        Args:
            messages: List of message dictionaries
            tools: List of tool definitions
            kwargs: Additional parameters
            
        Returns:
            Dict containing backend-specific API parameters
        """
        pass
    
    @abstractmethod
    async def _create_stream(self, api_params: Dict[str, Any]) -> Any:
        """
        Create backend-specific streaming iterator.

        Each backend uses different clients and methods:
        - Response API: openai.AsyncOpenAI().responses.create()
        - Claude: anthropic.AsyncAnthropic().messages.create()
        - Chat Completions: openai.AsyncOpenAI().chat.completions.create()

        Args:
            api_params: Backend-specific API parameters

        Returns:
            Streaming iterator for the specific backend
        """
        pass

    @abstractmethod
    def _detect_function_calls(self, chunk: Any, current_call: Optional[Dict[str, Any]], captured_calls: List[Dict[str, Any]]) -> tuple:
        """
        Detect function calls from backend-specific chunks.

        Each backend has different chunk structures for function calls:
        - Response API: "response.output_item.added" with chunk.item.type == "function_call"
        - Claude: "content_block_start" with type "tool_use"
        - Chat Completions: "tool_calls" in delta with function details

        Args:
            chunk: Backend-specific chunk object
            current_call: Currently building function call
            captured_calls: List of completed function calls

        Returns:
            Tuple of (current_function_call, captured_calls, consumed)
        """
        pass

    @abstractmethod
    def _process_chunk(self, chunk: Any) -> StreamChunk:
        """
        Convert backend-specific chunks to StreamChunk format.

        Each backend has different chunk event types:
        - Response API: "response.output_text.delta", "response.reasoning_text.delta", etc.
        - Claude: "content_block_delta", "message_delta", etc.
        - Chat Completions: delta format with "content", "role", etc.

        Args:
            chunk: Backend-specific chunk object

        Returns:
            StreamChunk object with standardized format
        """
        pass

    # create_tool_result_message is inherited from LLMBackend base class

    @abstractmethod
    async def _stream_without_mcp(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs) -> AsyncGenerator[StreamChunk, None]:
        """
        Stream without MCP functionality (fallback mode).

        This should implement the basic streaming functionality for the backend
        without any MCP tool integration.

        Args:
            messages: List of message dictionaries
            tools: List of tool definitions
            **kwargs: Additional parameters

        Yields:
            StreamChunk objects
        """
        pass

    @abstractmethod
    def _get_provider_tools(self, kwargs: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Get provider-specific tools.

        Each backend may have different built-in tools:
        - Response API: web search, code interpreter
        - Claude: computer use, text editor
        - Chat Completions: function calling

        Args:
            kwargs: Configuration parameters

        Returns:
            List of provider-specific tool definitions
        """
        pass