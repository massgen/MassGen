"""
Base class for backends using OpenAI Chat Completions API format - REFACTORED VERSION.
Handles common message processing, tool conversion, and streaming patterns.

Supported Providers and Environment Variables:
- OpenAI: OPENAI_API_KEY
- Cerebras AI: CEREBRAS_API_KEY
- Together AI: TOGETHER_API_KEY
- Fireworks AI: FIREWORKS_API_KEY
- Groq: GROQ_API_KEY
- Kimi/Moonshot: MOONSHOT_API_KEY or KIMI_API_KEY
- Nebius AI Studio: NEBIUS_API_KEY
- OpenRouter: OPENROUTER_API_KEY
- ZAI: ZAI_API_KEY
"""

from __future__ import annotations

import asyncio
import os
from typing import Dict, List, Any, AsyncGenerator, Optional, Tuple, Callable

from openai import AsyncOpenAI

from .base import LLMBackend, StreamChunk, FilesystemSupport
from .mcp_integration import MCPIntegrationMixin
from .tool_handlers import ToolHandlerMixin, ToolFormat
from .token_management import TokenCostCalculator
from .utils.streaming_utils import StreamAccumulator, StreamProcessor
from .utils.message_converters import MessageConverter
from .utils.api_helpers import APIRequestBuilder

from ..logger_config import (
    log_backend_activity,
    log_backend_agent_message,
    log_stream_chunk,
    logger,
)


class ChatCompletionsBackend(LLMBackend, MCPIntegrationMixin, ToolHandlerMixin):
    """
    Complete OpenAI-compatible Chat Completions API backend - REFACTORED.
    Reduces from 1703 lines to ~1000 lines through mixins and utilities.
    """

    # Internal helper class for stream processing
    class StreamHandler:
        """Handles stream processing for Chat Completions format."""
        
        def __init__(self, backend: 'ChatCompletionsBackend', agent_id: Optional[str]):
            self.backend = backend
            self.agent_id = agent_id
            self.accumulator = StreamAccumulator()
            self.provider_name = backend.get_provider_name()
            self.log_prefix = f"backend.{self.provider_name.lower().replace(' ', '_')}"
        
        async def process_stream(
            self,
            stream: AsyncGenerator,
            enable_web_search: bool = False
        ) -> AsyncGenerator[StreamChunk, None]:
            """Process standard Chat Completions stream."""
            current_tool_calls = {}
            search_sources_used = 0
            
            async for chunk in stream:
                try:
                    if hasattr(chunk, "choices") and chunk.choices:
                        choice = chunk.choices[0]
                        
                        if hasattr(choice, "delta") and choice.delta:
                            delta = choice.delta
                            
                            # Handle content
                            if getattr(delta, "content", None):
                                content_chunk = delta.content
                                self.accumulator.add_content(content_chunk)
                                
                                log_backend_agent_message(
                                    self.agent_id or "default",
                                    "RECV",
                                    {"content": content_chunk},
                                    backend_name=self.provider_name
                                )
                                log_stream_chunk(
                                    self.log_prefix, "content", content_chunk, self.agent_id
                                )
                                yield StreamChunk(type="content", content=content_chunk)
                            
                            # Handle reasoning (provider-specific)
                            if getattr(delta, "reasoning_content", None):
                                reasoning_delta = delta.reasoning_content
                                log_stream_chunk(
                                    self.log_prefix, "reasoning", reasoning_delta, self.agent_id
                                )
                                yield StreamChunk(
                                    type="reasoning",
                                    content=reasoning_delta,
                                    reasoning_delta=reasoning_delta
                                )
                            
                            # Handle tool calls
                            if getattr(delta, "tool_calls", None):
                                for tool_call_delta in delta.tool_calls:
                                    index = getattr(tool_call_delta, "index", 0)
                                    self.accumulator.add_tool_call(index, {
                                        "id": getattr(tool_call_delta, "id", None),
                                        "function": tool_call_delta.function if hasattr(tool_call_delta, "function") else None
                                    })
                        
                        # Handle finish reason
                        if getattr(choice, "finish_reason", None):
                            if choice.finish_reason == "tool_calls" and current_tool_calls:
                                final_tool_calls = self.accumulator.get_final_tool_calls()
                                log_stream_chunk(
                                    self.log_prefix, "tool_calls", final_tool_calls, self.agent_id
                                )
                                yield StreamChunk(type="tool_calls", tool_calls=final_tool_calls)
                                yield StreamChunk(type="done")
                                return
                            
                            elif choice.finish_reason in ["stop", "length"]:
                                if search_sources_used > 0 and enable_web_search:
                                    msg = f"\n✅ [Live Search Complete] Used {search_sources_used} sources\n"
                                    yield StreamChunk(type="content", content=msg)
                                
                                yield StreamChunk(type="done")
                                return
                    
                    # Handle usage metadata
                    if hasattr(chunk, "usage") and chunk.usage:
                        if getattr(chunk.usage, "num_sources_used", 0) > 0:
                            search_sources_used = chunk.usage.num_sources_used
                            if enable_web_search:
                                msg = f"\n📊 [Live Search] Using {search_sources_used} sources\n"
                                yield StreamChunk(type="content", content=msg)
                
                except Exception as e:
                    error_msg = f"Chunk processing error: {e}"
                    log_stream_chunk(self.log_prefix, "error", error_msg, self.agent_id)
                    yield StreamChunk(type="error", error=error_msg)
                    continue
            
            # Fallback
            log_stream_chunk(self.log_prefix, "done", None, self.agent_id)
            yield StreamChunk(type="done")
    
    # Parameters to exclude when building API requests
    EXCLUDED_API_PARAMS = LLMBackend.get_base_excluded_config_params().union({
        "base_url",
        "enable_web_search",
        "enable_code_interpreter",
        "allowed_tools",
        "exclude_tools",
    })
    
    def __init__(self, api_key: Optional[str] = None, **kwargs):
        """Initialize ChatCompletionsBackend - REFACTORED."""
        super().__init__(api_key, **kwargs)
        
        # Initialize mixins
        self._init_mcp_integration(**kwargs)
        
        # Initialize utilities
        self.token_calculator = TokenCostCalculator()
        self.message_converter = MessageConverter()
        self.api_builder = APIRequestBuilder()
        
        # Configuration
        self.backend_name = self.get_provider_name()
        self.agent_id = kwargs.get("agent_id", None)
    
    def get_provider_name(self) -> str:
        """Get the name of this provider."""
        # Check explicit config
        if "provider" in self.config:
            return self.config["provider"]
        elif "provider_name" in self.config:
            return self.config["provider_name"]
        
        # Infer from base_url
        base_url = self.config.get("base_url", "")
        url_mappings = {
            "openai.com": "OpenAI",
            "cerebras.ai": "Cerebras AI",
            "together.xyz": "Together AI",
            "fireworks.ai": "Fireworks AI",
            "groq.com": "Groq",
            "openrouter.ai": "OpenRouter",
            "z.ai": "ZAI",
            "bigmodel.cn": "ZAI",
            "nebius.com": "Nebius AI Studio",
            "moonshot.ai": "Kimi",
            "moonshot.cn": "Kimi",
        }
        
        for domain, name in url_mappings.items():
            if domain in base_url:
                return name
        
        return "ChatCompletion"
    
    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Stream response using OpenAI-compatible Chat Completions API - REFACTORED.
        Reduces from ~400 lines to ~100 lines using mixins and utilities.
        """
        agent_id = kwargs.get("agent_id", None)
        
        log_backend_activity(
            self.get_provider_name(),
            "Starting stream_with_tools",
            {"num_messages": len(messages), "num_tools": len(tools) if tools else 0},
            agent_id=agent_id
        )
        
        # Check if MCP is configured
        if self.mcp_servers:
            async with self:
                client = self._create_openai_client(**kwargs)
                
                # Determine if MCP processing is needed
                use_mcp = bool(self.functions)
                
                if use_mcp:
                    # MCP mode with recursive execution
                    logger.info("Using recursive MCP execution mode")
                    
                    # Initialize MCP if needed
                    await self._initialize_mcp_client()
                    
                    # Stream with MCP
                    async for chunk in self._stream_mcp_recursive(
                        messages, tools, client, **kwargs
                    ):
                        yield chunk
                else:
                    # Non-MCP mode
                    async for chunk in self._stream_without_mcp(
                        client, messages, tools, kwargs, agent_id
                    ):
                        yield chunk
        else:
            # No MCP configured
            client = None
            try:
                client = self._create_openai_client(**kwargs)
                async for chunk in self._stream_without_mcp(
                    client, messages, tools, kwargs, agent_id
                ):
                    yield chunk
            except Exception as e:
                logger.error(f"Chat Completions API error: {str(e)}")
                yield StreamChunk(type="error", error=str(e))
            finally:
                await self._cleanup_client(client)
    
    async def _stream_without_mcp(
        self,
        client: AsyncOpenAI,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        all_params: Dict[str, Any],
        agent_id: Optional[str]
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream without MCP - simplified using utilities."""
        # Build API parameters using utilities
        api_params = self._build_api_params(messages, tools, all_params)
        
        log_backend_agent_message(
            agent_id or "default",
            "SEND",
            {
                "messages": api_params["messages"],
                "tools": len(api_params.get("tools", []))
            },
            backend_name=self.get_provider_name()
        )
        
        try:
            stream = await client.chat.completions.create(**api_params)
            
            # Use StreamHandler helper
            handler = self.StreamHandler(self, agent_id)
            async for chunk in handler.process_stream(
                stream, all_params.get("enable_web_search", False)
            ):
                yield chunk
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield StreamChunk(type="error", error=str(e))
    
    async def _stream_mcp_recursive(
        self,
        current_messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        client: AsyncOpenAI,
        **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Recursively stream MCP responses - simplified using mixins.
        """
        # Build API params
        all_params = {**self.config, **kwargs}
        api_params = self._build_api_params(current_messages, tools, all_params)
        
        # Stream response
        stream = await client.chat.completions.create(**api_params)
        
        # Process stream and collect function calls
        accumulator = StreamAccumulator()
        captured_function_calls = []
        response_completed = False
        
        async for chunk in stream:
            chunk_data = self._process_streaming_chunk(chunk)
            if chunk_data:
                if chunk_data["type"] == "content":
                    accumulator.add_content(chunk_data["content"])
                    yield StreamChunk(type="content", content=chunk_data["content"])
                elif chunk_data["type"] == "tool_calls":
                    captured_function_calls = chunk_data["tool_calls"]
                    yield StreamChunk(type="tool_calls", tool_calls=captured_function_calls)
                    response_completed = True
                    break
                elif chunk_data["type"] == "done":
                    response_completed = True
                    yield StreamChunk(type="done")
                    return
        
        # Execute MCP function calls if any
        if captured_function_calls and response_completed:
            # Execute tools using mixin
            results = await self._execute_mcp_tools(captured_function_calls)
            
            # Update messages with results
            updated_messages = current_messages.copy()
            
            # Add assistant message with tool calls
            updated_messages.append({
                "role": "assistant",
                "content": accumulator.content.strip() if accumulator.content else None,
                "tool_calls": captured_function_calls
            })
            
            # Add tool results
            for result in results:
                updated_messages.append({
                    "role": "tool",
                    "tool_call_id": result["tool_call_id"],
                    "content": result["content"]
                })
                
                yield StreamChunk(
                    type="mcp_status",
                    status="mcp_tool_response",
                    content=f"✅ [MCP Tool] {result.get('name', 'unknown')} completed"
                )
            
            # Recursive call with updated messages
            async for chunk in self._stream_mcp_recursive(
                updated_messages, tools, client, **kwargs
            ):
                yield chunk
        else:
            # No function calls, we're done
            yield StreamChunk(type="done")
    
    def _build_api_params(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        all_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build API parameters using utilities."""
        # Convert messages
        converted_messages = self.message_converter.convert_messages(
            messages, 
            from_format="response_api",
            to_format="openai"
        )
        
        # Build base parameters
        api_params = {
            "messages": converted_messages,
            "stream": True,
        }
        
        # Add tools if present
        if tools:
            converted_tools = self.convert_tools_format(
                tools, 
                ToolFormat.OPENAI,
                ToolFormat.OPENAI
            )
            api_params["tools"] = converted_tools
        
        # Add MCP tools if available
        if self.functions:
            mcp_tools = self._convert_mcp_tools_to_format()
            if mcp_tools:
                if "tools" not in api_params:
                    api_params["tools"] = []
                api_params["tools"].extend(mcp_tools)
        
        # Add other parameters
        for key, value in all_params.items():
            if key not in self.EXCLUDED_API_PARAMS and value is not None:
                api_params[key] = value
        
        return api_params
    
    def _process_streaming_chunk(self, chunk: Any) -> Optional[Dict[str, Any]]:
        """Process a streaming chunk into structured data."""
        try:
            if hasattr(chunk, "choices") and chunk.choices:
                choice = chunk.choices[0]
                
                if hasattr(choice, "delta") and choice.delta:
                    delta = choice.delta
                    
                    # Content delta
                    if getattr(delta, "content", None):
                        return {"type": "content", "content": delta.content}
                    
                    # Tool calls
                    if getattr(delta, "tool_calls", None):
                        tool_calls = []
                        for tc in delta.tool_calls:
                            if hasattr(tc, "function"):
                                tool_calls.append({
                                    "id": getattr(tc, "id", ""),
                                    "type": "function",
                                    "function": {
                                        "name": getattr(tc.function, "name", ""),
                                        "arguments": getattr(tc.function, "arguments", "{}")
                                    }
                                })
                        if tool_calls:
                            return {"type": "tool_calls", "tool_calls": tool_calls}
                
                # Finish reason
                if getattr(choice, "finish_reason", None):
                    if choice.finish_reason in ["stop", "length"]:
                        return {"type": "done"}
                    elif choice.finish_reason == "tool_calls":
                        return {"type": "tool_calls_complete"}
            
            return None
        except Exception as e:
            logger.warning(f"Error processing chunk: {e}")
            return None
    
    def _create_openai_client(self, **kwargs) -> AsyncOpenAI:
        """Create OpenAI client with configuration."""
        import openai
        
        all_params = {**self.config, **kwargs}
        base_url = all_params.get("base_url", "https://api.openai.com/v1")
        return openai.AsyncOpenAI(api_key=self.api_key, base_url=base_url)
    
    async def _cleanup_client(self, client: Optional[AsyncOpenAI]) -> None:
        """Clean up OpenAI client resources."""
        try:
            if client is not None and hasattr(client, "aclose"):
                await client.aclose()
        except Exception:
            pass
    
    # Token and cost methods using calculator
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count using unified calculator."""
        return self.token_calculator.estimate_tokens(text)
    
    def calculate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str
    ) -> float:
        """Calculate cost using unified calculator."""
        provider = self.get_provider_name()
        return self.token_calculator.calculate_cost(
            input_tokens, output_tokens, provider, model
        )
    
    # Tool format helpers from mixin
    def extract_tool_name(self, tool_call: Dict[str, Any]) -> str:
        """Extract tool name from Chat Completions format."""
        return tool_call.get("function", {}).get("name", "unknown")
    
    def extract_tool_arguments(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """Extract tool arguments from Chat Completions format."""
        import json
        arguments = tool_call.get("function", {}).get("arguments", {})
        if isinstance(arguments, str):
            try:
                return json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError:
                return {}
        return arguments
    
    def extract_tool_call_id(self, tool_call: Dict[str, Any]) -> str:
        """Extract tool call ID from Chat Completions format."""
        return tool_call.get("id", "")
    
    def create_tool_result_message(
        self,
        tool_call: Dict[str, Any],
        result_content: str
    ) -> Dict[str, Any]:
        """Create tool result message for Chat Completions format."""
        return {
            "role": "tool",
            "tool_call_id": self.extract_tool_call_id(tool_call),
            "content": result_content,
        }
    
    def get_filesystem_support(self) -> FilesystemSupport:
        """Chat Completions supports filesystem through MCP servers."""
        return FilesystemSupport.MCP
    
    def get_supported_builtin_tools(self) -> List[str]:
        """Get list of builtin tools supported by this provider."""
        # Base Chat Completions doesn't support builtin tools
        # Subclasses can override this
        return []
    
    async def __aenter__(self) -> "ChatCompletionsBackend":
        """Async context manager entry."""
        await self._setup_mcp_tools()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.cleanup_mcp()
        return False