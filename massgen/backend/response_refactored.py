"""
Response API backend implementation - REFACTORED VERSION.
Optimized for the standard Response API format using mixins and utilities.
"""

from __future__ import annotations
import os
import json
import asyncio
from typing import Dict, List, Any, AsyncGenerator, Optional, Literal
from urllib.parse import urljoin
import httpx

from .base import LLMBackend, StreamChunk, FilesystemSupport
from .mcp_integration import MCPIntegrationMixin
from .tool_handlers import ToolHandlerMixin, ToolFormat
from .token_management import TokenCostCalculator
from .utils import StreamAccumulator, StreamProcessor, parse_sse_chunk
from .utils import MessageConverter, APIRequestBuilder, ResponseParser
from ..logger_config import log_backend_activity, log_backend_agent_message, log_stream_chunk, logger

# Import MCP utilities for compatibility
try:
    from ..mcp_tools import MCPExecutionManager, MCPMessageManager
except ImportError:
    MCPExecutionManager = None
    MCPMessageManager = None


class ResponseBackend(LLMBackend, MCPIntegrationMixin, ToolHandlerMixin):
    """
    Backend using the standard Response API format - REFACTORED.
    Reduces from 1186 lines to ~700 lines through mixins and utilities.
    """
    
    # Parameters to exclude when building API requests
    EXCLUDED_API_PARAMS = LLMBackend.get_base_excluded_config_params().union({
        "base_url",
        "api_key",
        "allowed_tools",
        "exclude_tools",
    })
    
    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(api_key, **kwargs)
        
        # API configuration
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("API key required for Response API backend")
        
        # Initialize mixins
        self._init_mcp_integration(**kwargs)
        
        # Initialize utilities
        self.token_calculator = TokenCostCalculator()
        self.message_converter = MessageConverter()
        self.request_builder = APIRequestBuilder()
        self.response_parser = ResponseParser()
        
        # Backend identification
        self.backend_name = self.get_provider_name()
        self.agent_id = kwargs.get('agent_id', None)
        
        # Response API specific configuration
        self.base_url = kwargs.get('base_url', 'https://api.openai.com/v1')
        self.default_model = kwargs.get('model', 'gpt-4-turbo-preview')
    
    def get_provider_name(self) -> str:
        """Get the name of this provider."""
        return "Response API"
    
    def get_filesystem_support(self) -> FilesystemSupport:
        """Response API supports filesystem through MCP servers."""
        return FilesystemSupport.MCP if self.mcp_servers else FilesystemSupport.NONE
    
    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Stream response with tool support - REFACTORED.
        Uses mixins and utilities to reduce code from ~400 lines to ~100 lines.
        """
        agent_id = kwargs.get('agent_id', self.agent_id)
        
        log_backend_activity(
            self.backend_name,
            "Starting stream_with_tools",
            {"num_messages": len(messages), "num_tools": len(tools) if tools else 0},
            agent_id=agent_id
        )
        
        try:
            # Initialize MCP if needed (mixin)
            if self.mcp_servers and not self._mcp_initialized:
                await self._initialize_mcp_client()
            
            # Convert and filter tools (mixins)
            formatted_tools = self.convert_tools_format(tools, ToolFormat.RESPONSE_API)
            filtered_tools = self.filter_tools(
                formatted_tools, 
                allowed=self.allowed_tools,
                excluded=self.exclude_tools
            )
            
            # Add MCP tools if available
            if self._mcp_initialized and self.functions:
                mcp_tools = self._convert_mcp_tools_to_response_format()
                all_tools = self.merge_tool_definitions(filtered_tools, mcp_tools)
            else:
                all_tools = filtered_tools
            
            # Build request using helper
            api_params = self._build_api_params(messages, all_tools, kwargs)
            
            # Stream with accumulator and processor
            accumulator = StreamAccumulator()
            
            async for chunk in StreamProcessor.process_with_retry(
                lambda: self._stream_response_api(api_params),
                max_retries=kwargs.get('max_retries', 3)
            ):
                # Process chunk based on type
                if chunk.type == "content":
                    accumulator.add_content(chunk.content)
                    yield chunk
                    
                elif chunk.type == "tool_calls":
                    # Handle tool calls
                    for tool_call in chunk.tool_calls:
                        accumulator.add_tool_call(
                            tool_call.get("index", 0),
                            tool_call
                        )
                    
                    # Execute MCP tools if needed
                    if self._mcp_initialized:
                        mcp_results = await self._execute_mcp_tools(chunk.tool_calls)
                        for result in mcp_results:
                            yield StreamChunk(
                                type="tool_result",
                                content=result["content"]
                            )
                
                elif chunk.type == "error":
                    logger.error(f"Stream error: {chunk.error}")
                    yield chunk
                
                elif chunk.type == "done":
                    # Update token usage
                    self.token_calculator.update_token_usage(
                        self.token_usage,
                        messages,
                        accumulator.content,
                        "OpenAI",
                        kwargs.get("model", self.default_model)
                    )
                    yield chunk
            
        except Exception as e:
            logger.error(f"Response API error: {str(e)}")
            yield StreamChunk(type="error", error=str(e))
    
    async def _stream_response_api(
        self,
        api_params: Dict[str, Any]
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Stream from Response API endpoint.
        Simplified implementation using utilities.
        """
        url = urljoin(self.base_url, "/chat/completions")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                url,
                json=api_params,
                headers=headers
            ) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        chunk_data = parse_sse_chunk(line)
                        
                        if chunk_data and chunk_data.get("type") != "done":
                            # Convert to StreamChunk
                            chunk = self._parse_response_chunk(chunk_data)
                            if chunk:
                                yield chunk
                
                yield StreamChunk(type="done")
    
    def _build_api_params(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        kwargs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Build API request parameters using helpers.
        """
        # Start with base parameters
        params = {
            "model": kwargs.get("model", self.default_model),
            "messages": messages,
            "stream": True
        }
        
        # Add tools if available
        if tools:
            params["tools"] = tools
            params["tool_choice"] = kwargs.get("tool_choice", "auto")
        
        # Add generation config using helper
        params = self.request_builder.add_generation_config(
            params, kwargs, "response_api"
        )
        
        # Add streaming options
        params = self.request_builder.add_streaming_options(
            params, "response_api"
        )
        
        # Add any additional parameters not in excluded list
        for key, value in kwargs.items():
            if key not in self.EXCLUDED_API_PARAMS:
                params[key] = value
        
        return params
    
    def _parse_response_chunk(
        self,
        chunk_data: Dict[str, Any]
    ) -> Optional[StreamChunk]:
        """
        Parse Response API chunk into StreamChunk.
        """
        choices = chunk_data.get("choices", [])
        if not choices:
            return None
        
        choice = choices[0]
        delta = choice.get("delta", {})
        
        # Handle content
        if "content" in delta:
            return StreamChunk(
                type="content",
                content=delta["content"]
            )
        
        # Handle tool calls
        if "tool_calls" in delta:
            return StreamChunk(
                type="tool_calls",
                tool_calls=delta["tool_calls"]
            )
        
        # Handle finish reason
        if "finish_reason" in choice:
            return StreamChunk(
                type="finish",
                content=choice["finish_reason"]
            )
        
        return None
    
    def _convert_mcp_tools_to_response_format(self) -> List[Dict[str, Any]]:
        """
        Convert MCP tools to Response API format.
        Uses tool handler mixin for conversion.
        """
        if not self.functions:
            return []
        
        tools = []
        for func_name, func in self.functions.items():
            tool = {
                "type": "function",
                "name": func_name,
                "description": func.description or "",
                "parameters": func.input_schema or {}
            }
            tools.append(tool)
        
        # Convert to Response API format
        return self.convert_tools_format(tools, ToolFormat.RESPONSE_API)
    
    # Token and cost methods use mixins
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
        return self.token_calculator.calculate_cost(
            input_tokens, output_tokens, "OpenAI", model
        )
    
    def get_supported_builtin_tools(self) -> List[str]:
        """Response API doesn't have builtin tools."""
        return []
    
    # MCP execution loop handling (simplified)
    async def _handle_mcp_execution_loop(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        api_params: Dict[str, Any]
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Handle MCP tool execution loop - SIMPLIFIED.
        Most logic moved to mixin and utilities.
        """
        if not MCPExecutionManager or not MCPMessageManager:
            logger.warning("MCP utilities not available for execution loop")
            return
        
        # Use MCP execution manager from mcp_tools
        execution_context = {
            "messages": messages.copy(),
            "tools": tools,
            "max_iterations": 10
        }
        
        async for chunk in MCPExecutionManager.execute_with_tools(
            execution_context,
            self._execute_mcp_tools,
            self._stream_response_api
        ):
            yield chunk