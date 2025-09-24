# -*- coding: utf-8 -*-
"""
Claude backend implementation using Anthropic's Messages API.
Production-ready implementation with full multi-tool support.

✅ FEATURES IMPLEMENTED:
- ✅ Messages API integration with streaming support
- ✅ Multi-tool support (server-side + user-defined tools combined)
- ✅ Web search tool integration with pricing tracking
- ✅ Code execution tool integration with session management
- ✅ Tool message format conversion for MassGen compatibility
- ✅ Advanced streaming with tool parameter streaming
- ✅ Error handling and token usage tracking
- ✅ Production-ready pricing calculations (2025 rates)

Multi-Tool Capabilities:
- Can combine web search + code execution + user functions in single request
- No API limitations unlike other providers
- Parallel and sequential tool execution supported
- Perfect integration with MassGen StreamChunk pattern
"""
from __future__ import annotations

import json
import os
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

from ..logger_config import (
    log_backend_activity,
    log_backend_agent_message,
    log_stream_chunk,
    logger,
)

# MCP imports are handled by the base class MCPBackend
from ..mcp_tools import MCPConnectionError, MCPError, MCPServerError, MCPTimeoutError
from ..mcp_tools.backend_utils import (
    MCPCircuitBreakerManager,
    MCPErrorHandler,
    MCPSetupManager,
)
from .base import FilesystemSupport, StreamChunk
from .base_with_mcp import MCPBackend


class ClaudeBackend(MCPBackend):
    """Claude backend using Anthropic's Messages API with full multi-tool support."""

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(api_key, **kwargs)
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.search_count = 0  # Track web search usage for pricing
        self.code_session_hours = 0.0  # Track code execution usage

    async def _handle_mcp_error_and_fallback_claude(
        self,
        error: Exception,
        api_params: Dict[str, Any],
        provider_tools: List[Dict[str, Any]],
        stream_func: Callable[[Dict[str, Any]], AsyncGenerator[StreamChunk, None]],
    ) -> AsyncGenerator[StreamChunk, None]:
        """Handle MCP errors with user-friendly messaging and fallback to non-MCP tools."""

        async with self._stats_lock:
            self._mcp_tool_failures += 1
            call_index_snapshot = self._mcp_tool_calls_count

        if MCPErrorHandler:
            log_type, user_message, _ = MCPErrorHandler.get_error_details(error)  # type: ignore[assignment]
        else:
            log_type, user_message = "mcp_error", "[MCP] Error occurred"

        logger.warning(f"MCP tool call #{call_index_snapshot} failed - {log_type}: {error}")

        yield StreamChunk(
            type="content",
            content=f"\n⚠️  {user_message} ({error}); continuing without MCP tools\n",
        )

        # Build non-MCP configuration and stream fallback
        fallback_params = dict(api_params)

        # Remove any MCP tools from the tools list
        if "tools" in fallback_params and self._mcp_functions:
            mcp_names = set(self._mcp_functions.keys())
            non_mcp_tools = []
            for tool in fallback_params["tools"]:
                name = tool.get("name")
                if name in mcp_names:
                    continue
                non_mcp_tools.append(tool)
            fallback_params["tools"] = non_mcp_tools

        # Add back provider tools if they were present
        if provider_tools:
            if "tools" not in fallback_params:
                fallback_params["tools"] = []
            fallback_params["tools"].extend(provider_tools)

        async for chunk in stream_func(fallback_params):
            yield chunk

    async def _execute_mcp_function_with_retry_claude(
        self,
        function_name: str,
        arguments_json: str,
        max_retries: int = 3,
    ) -> List[str | Any]:
        """Execute MCP function with Claude-specific formatting."""
        # Use parent class method which returns tuple
        result_str, result_obj = await super()._execute_mcp_function_with_retry(
            function_name,
            arguments_json,
            max_retries,
        )

        # Convert to list format expected by Claude streaming
        if result_str.startswith("Error:"):
            return [result_str]
        return [result_str, result_obj]

    async def _build_claude_api_params(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        all_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build Anthropic Messages API parameters with MCP integration."""
        # Convert messages to Claude format and extract system message
        converted_messages, system_message = self.message_formatter.to_claude_format(messages)

        # Combine tools
        combined_tools: List[Dict[str, Any]] = []

        # Server-side tools
        enable_web_search = all_params.get("enable_web_search", False)
        enable_code_execution = all_params.get("enable_code_execution", False)
        if enable_web_search:
            combined_tools.append({"type": "web_search_20250305", "name": "web_search"})
        if enable_code_execution:
            combined_tools.append({"type": "code_execution_20250522", "name": "code_execution"})

        # User-defined tools
        if tools:
            converted_tools = self.tool_formatter.to_claude_format(tools)
            combined_tools.extend(converted_tools)

        # MCP tools
        if self._mcp_functions:
            mcp_tools = self.get_mcp_tools_formatted(self.mcp_tool_formatter)
            combined_tools.extend(mcp_tools)

        # Build API parameters
        api_params: Dict[str, Any] = {"messages": converted_messages, "stream": True}

        if system_message:
            api_params["system"] = system_message
        if combined_tools:
            api_params["tools"] = combined_tools

        # Direct passthrough of all parameters except those handled separately
        # Use base class exclusions plus Claude-specific ones
        excluded_params = self.get_base_excluded_config_params().union(
            {
                "enable_web_search",
                "enable_code_execution",
                "allowed_tools",
                "exclude_tools",
            },
        )
        for key, value in all_params.items():
            if key not in excluded_params and value is not None:
                api_params[key] = value

        # Claude API requires max_tokens - add default if not provided
        if "max_tokens" not in api_params:
            api_params["max_tokens"] = 4096

        if all_params.get("enable_code_execution"):
            api_params["betas"] = ["code-execution-2025-05-22"]

        return api_params

    async def _stream_mcp_recursive(
        self,
        current_messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        client,
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Recursively stream responses, executing MCP function calls when detected."""

        # Build API params for this iteration
        all_params = {**self.config, **kwargs}
        api_params = await self._build_claude_api_params(current_messages, tools, all_params)

        agent_id = kwargs.get("agent_id", None)

        # Create stream (handle code execution beta)
        if "betas" in api_params:
            stream = await client.beta.messages.create(**api_params)
        else:
            stream = await client.messages.create(**api_params)

        content = ""
        current_tool_uses: Dict[str, Dict[str, Any]] = {}
        mcp_tool_calls: List[Dict[str, Any]] = []
        response_completed = False

        async for event in stream:
            try:
                if event.type == "message_start":
                    continue
                elif event.type == "content_block_start":
                    if hasattr(event, "content_block"):
                        if event.content_block.type == "tool_use":
                            tool_id = event.content_block.id
                            tool_name = event.content_block.name
                            current_tool_uses[tool_id] = {
                                "id": tool_id,
                                "name": tool_name,
                                "input": "",
                                "index": getattr(event, "index", None),
                            }
                        elif event.content_block.type == "server_tool_use":
                            tool_id = event.content_block.id
                            tool_name = event.content_block.name
                            current_tool_uses[tool_id] = {
                                "id": tool_id,
                                "name": tool_name,
                                "input": "",
                                "index": getattr(event, "index", None),
                                "server_side": True,
                            }
                            if tool_name == "code_execution":
                                yield StreamChunk(
                                    type="content",
                                    content="\n💻 [Code Execution] Starting...\n",
                                )
                            elif tool_name == "web_search":
                                yield StreamChunk(
                                    type="content",
                                    content="\n🔍 [Web Search] Starting search...\n",
                                )
                        elif event.content_block.type == "code_execution_tool_result":
                            result_block = event.content_block
                            result_parts = []
                            if hasattr(result_block, "stdout") and result_block.stdout:
                                result_parts.append(f"Output: {result_block.stdout.strip()}")
                            if hasattr(result_block, "stderr") and result_block.stderr:
                                result_parts.append(f"Error: {result_block.stderr.strip()}")
                            if hasattr(result_block, "return_code") and result_block.return_code != 0:
                                result_parts.append(f"Exit code: {result_block.return_code}")
                            if result_parts:
                                result_text = f"\n💻 [Code Execution Result]\n{chr(10).join(result_parts)}\n"
                                yield StreamChunk(type="content", content=result_text)
                elif event.type == "content_block_delta":
                    if hasattr(event, "delta"):
                        if event.delta.type == "text_delta":
                            text_chunk = event.delta.text
                            content += text_chunk
                            log_backend_agent_message(
                                agent_id or "default",
                                "RECV",
                                {"content": text_chunk},
                                backend_name="claude",
                            )
                            log_stream_chunk("backend.claude", "content", text_chunk, agent_id)
                            yield StreamChunk(type="content", content=text_chunk)
                        elif event.delta.type == "input_json_delta":
                            if hasattr(event, "index"):
                                for tool_id, tool_data in current_tool_uses.items():
                                    if tool_data.get("index") == event.index:
                                        partial_json = getattr(event.delta, "partial_json", "")
                                        tool_data["input"] += partial_json
                                        break
                elif event.type == "content_block_stop":
                    if hasattr(event, "index"):
                        for tool_id, tool_data in current_tool_uses.items():
                            if tool_data.get("index") == event.index and tool_data.get("server_side"):
                                tool_name = tool_data.get("name", "")
                                tool_input = tool_data.get("input", "")
                                try:
                                    parsed_input = json.loads(tool_input) if tool_input else {}
                                except json.JSONDecodeError:
                                    parsed_input = {"raw_input": tool_input}
                                if tool_name == "code_execution":
                                    code = parsed_input.get("code", "")
                                    if code:
                                        yield StreamChunk(type="content", content=f"💻 [Code] {code}\n")
                                    yield StreamChunk(
                                        type="content",
                                        content="✅ [Code Execution] Completed\n",
                                    )
                                elif tool_name == "web_search":
                                    query = parsed_input.get("query", "")
                                    if query:
                                        yield StreamChunk(
                                            type="content",
                                            content=f"🔍 [Query] '{query}'\n",
                                        )
                                    yield StreamChunk(
                                        type="content",
                                        content="✅ [Web Search] Completed\n",
                                    )
                                tool_data["processed"] = True
                                break
                elif event.type == "message_delta":
                    pass
                elif event.type == "message_stop":
                    # Identify MCP and non-MCP tool calls among current_tool_uses
                    non_mcp_tool_calls = []
                    if current_tool_uses:
                        for tool_use in current_tool_uses.values():
                            tool_name = tool_use.get("name", "")
                            is_server_side = tool_use.get("server_side", False)
                            if is_server_side:
                                continue
                            # Parse accumulated JSON input for tool
                            tool_input = tool_use.get("input", "")
                            try:
                                parsed_input = json.loads(tool_input) if tool_input else {}
                            except json.JSONDecodeError:
                                parsed_input = {"raw_input": tool_input}

                            if self.is_mcp_tool_call(tool_name):
                                mcp_tool_calls.append(
                                    {
                                        "id": tool_use["id"],
                                        "type": "function",
                                        "function": {
                                            "name": tool_name,
                                            "arguments": parsed_input,
                                        },
                                    },
                                )
                            else:
                                non_mcp_tool_calls.append(
                                    {
                                        "id": tool_use["id"],
                                        "type": "function",
                                        "function": {
                                            "name": tool_name,
                                            "arguments": parsed_input,
                                        },
                                    },
                                )
                    # Emit non-MCP tool calls for the caller to execute
                    if non_mcp_tool_calls:
                        log_stream_chunk("backend.claude", "tool_calls", non_mcp_tool_calls, agent_id)
                        yield StreamChunk(type="tool_calls", tool_calls=non_mcp_tool_calls)
                    response_completed = True
                    break
            except Exception as event_error:
                error_msg = f"Event processing error: {event_error}"
                log_stream_chunk("backend.claude", "error", error_msg, agent_id)
                yield StreamChunk(type="error", error=error_msg)
                continue

        # If we captured MCP tool calls, execute them and recurse
        if response_completed and mcp_tool_calls:
            # Circuit breaker pre-execution check using base class method
            if not await self._check_circuit_breaker_before_execution():
                yield StreamChunk(
                    type="mcp_status",
                    status="mcp_blocked",
                    content="⚠️ [MCP] All servers blocked by circuit breaker",
                    source="circuit_breaker",
                )
                yield StreamChunk(type="done")
                return

            updated_messages = current_messages.copy()

            # Build assistant message with tool_use blocks for all MCP tool calls
            assistant_content = []
            if content:  # Add text content if any
                assistant_content.append({"type": "text", "text": content})

            for tool_call in mcp_tool_calls:
                tool_name = tool_call["function"]["name"]
                tool_args = tool_call["function"]["arguments"]
                tool_id = tool_call["id"]

                assistant_content.append(
                    {
                        "type": "tool_use",
                        "id": tool_id,
                        "name": tool_name,
                        "input": tool_args,
                    },
                )

            # Append the assistant message with tool uses
            updated_messages.append({"role": "assistant", "content": assistant_content})

            # Now execute the MCP tool calls and append results
            for tool_call in mcp_tool_calls:
                function_name = tool_call["function"]["name"]

                # Yield MCP tool call status
                yield StreamChunk(
                    type="mcp_status",
                    status="mcp_tool_called",
                    content=f"🔧 [MCP Tool] Calling {function_name}...",
                    source=f"mcp_{function_name}",
                )

                try:
                    # Execute MCP function
                    args_json = json.dumps(tool_call["function"]["arguments"]) if isinstance(tool_call["function"].get("arguments"), (dict, list)) else tool_call["function"].get("arguments", "{}")
                    result_list = await self._execute_mcp_function_with_retry_claude(function_name, args_json)
                    if not result_list or (isinstance(result_list[0], str) and result_list[0].startswith("Error:")):
                        logger.warning(f"MCP function {function_name} failed after retries: {result_list[0] if result_list else 'unknown error'}")
                        continue
                    result_str = result_list[0]
                    result_obj = result_list[1] if len(result_list) > 1 else None
                except Exception as e:
                    logger.error(f"Unexpected error in MCP function execution: {e}")
                    continue

                # Build tool result message: { "role":"user", "content":[{ "type":"tool_result", "tool_use_id": tool_call["id"], "content": result_str }] }
                tool_result_msg = {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_call["id"],
                            "content": result_str,
                        },
                    ],
                }

                # Append to updated_messages
                updated_messages.append(tool_result_msg)

                yield StreamChunk(
                    type="mcp_status",
                    status="function_call",
                    content=f"Arguments for Calling {function_name}: {json.dumps(tool_call['function'].get('arguments', {}))}",
                    source=f"mcp_{function_name}",
                )

                # If result_obj might be structured, try to display summary
                result_display = None
                try:
                    if hasattr(result_obj, "content") and result_obj.content:
                        part = result_obj.content[0]
                        if hasattr(part, "text"):
                            result_display = str(part.text)
                except Exception:
                    result_display = None
                if result_display:
                    yield StreamChunk(
                        type="mcp_status",
                        status="function_call_output",
                        content=f"Results for Calling {function_name}: {result_display}",
                        source=f"mcp_{function_name}",
                    )
                else:
                    yield StreamChunk(
                        type="mcp_status",
                        status="function_call_output",
                        content=f"Results for Calling {function_name}: {result_str}",
                        source=f"mcp_{function_name}",
                    )

                logger.info(f"Executed MCP function {function_name} (stdio/streamable-http)")
                yield StreamChunk(
                    type="mcp_status",
                    status="mcp_tool_response",
                    content=f"✅ [MCP Tool] {function_name} completed",
                    source=f"mcp_{function_name}",
                )

            # Trim updated_messages using base class method
            updated_messages = self._trim_message_history(updated_messages)

            # After processing all MCP calls, recurse: async for chunk in self._stream_mcp_recursive(updated_messages, tools, client, **kwargs): yield chunk
            async for chunk in self._stream_mcp_recursive(updated_messages, tools, client, **kwargs):
                yield chunk
            return
        else:
            # No MCP function calls; finalize this turn
            # Ensure termination with a done chunk when no further tool calls
            complete_message = {
                "role": "assistant",
                "content": content.strip(),
            }
            log_stream_chunk("backend.claude", "complete_message", complete_message, agent_id)
            yield StreamChunk(type="complete_message", complete_message=complete_message)
            yield StreamChunk(
                type="mcp_status",
                status="mcp_session_complete",
                content="✅ [MCP] Session completed",
                source="mcp_session",
            )
            yield StreamChunk(type="done")
            return

    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream response using Claude's Messages API with MCP integration and fallback."""
        agent_id = kwargs.get("agent_id", None)

        log_backend_activity(
            "claude",
            "Starting stream_with_tools",
            {"num_messages": len(messages), "num_tools": len(tools) if tools else 0},
            agent_id=agent_id,
        )

        # Use async context manager for proper MCP resource management
        try:
            async with self:
                import anthropic

                client = anthropic.AsyncAnthropic(api_key=self.api_key)
                try:
                    # Determine if MCP processing is needed
                    use_mcp = bool(self._mcp_functions)

                    # If MCP is configured but unavailable, inform the user and fall back
                    if self.mcp_servers and not use_mcp:
                        yield StreamChunk(
                            type="mcp_status",
                            status="mcp_unavailable",
                            content="⚠️ [MCP] Setup failed or no tools available; continuing without MCP",
                            source="mcp_setup",
                        )

                    # Yield MCP connection status if MCP tools are available
                    if use_mcp and self.mcp_servers:
                        server_count = self.get_mcp_server_count()
                        if server_count > 0:
                            yield StreamChunk(
                                type="mcp_status",
                                status="mcp_connected",
                                content=f"✅ [MCP] Connected to {server_count} servers",
                                source="mcp_setup",
                            )

                    if use_mcp:
                        # MCP MODE
                        logger.info("Using recursive MCP execution mode (Claude)")
                        current_messages = self._trim_message_history(messages.copy())
                        yield StreamChunk(
                            type="mcp_status",
                            status="mcp_tools_initiated",
                            content=f"🔧 [MCP] {len(self._mcp_functions)} tools available",
                            source="mcp_session",
                        )
                        async for chunk in self._stream_mcp_recursive(current_messages, tools, client, **kwargs):
                            yield chunk
                    else:
                        # NON-MCP MODE
                        all_params = {**self.config, **kwargs}
                        api_params = await self._build_claude_api_params(messages, tools, all_params)

                        # Helper to run a stream with given params (used also for fallback)
                        async def run_stream(params: Dict[str, Any]):
                            # Log messages being sent (limited to non-MCP for now)
                            converted_messages = params.get("messages", [])
                            combined_tools = params.get("tools", [])
                            log_backend_agent_message(
                                agent_id or "default",
                                "SEND",
                                {
                                    "messages": converted_messages,
                                    "tools": len(combined_tools) if combined_tools else 0,
                                },
                                backend_name="claude",
                            )
                            if "betas" in params:
                                st = await client.beta.messages.create(**params)
                            else:
                                st = await client.messages.create(**params)

                            content_local = ""
                            current_tool_uses_local: Dict[str, Dict[str, Any]] = {}

                            async for event in st:
                                try:
                                    if event.type == "message_start":
                                        continue
                                    elif event.type == "content_block_start":
                                        if hasattr(event, "content_block"):
                                            if event.content_block.type == "tool_use":
                                                tool_id = event.content_block.id
                                                tool_name = event.content_block.name
                                                current_tool_uses_local[tool_id] = {
                                                    "id": tool_id,
                                                    "name": tool_name,
                                                    "input": "",
                                                    "index": getattr(event, "index", None),
                                                }
                                            elif event.content_block.type == "server_tool_use":
                                                tool_id = event.content_block.id
                                                tool_name = event.content_block.name
                                                current_tool_uses_local[tool_id] = {
                                                    "id": tool_id,
                                                    "name": tool_name,
                                                    "input": "",
                                                    "index": getattr(event, "index", None),
                                                    "server_side": True,
                                                }
                                                if tool_name == "code_execution":
                                                    yield StreamChunk(
                                                        type="content",
                                                        content="\n💻 [Code Execution] Starting...\n",
                                                    )
                                                elif tool_name == "web_search":
                                                    yield StreamChunk(
                                                        type="content",
                                                        content="\n🔍 [Web Search] Starting search...\n",
                                                    )
                                            elif event.content_block.type == "code_execution_tool_result":
                                                result_block = event.content_block
                                                result_parts = []
                                                if hasattr(result_block, "stdout") and result_block.stdout:
                                                    result_parts.append(f"Output: {result_block.stdout.strip()}")
                                                if hasattr(result_block, "stderr") and result_block.stderr:
                                                    result_parts.append(f"Error: {result_block.stderr.strip()}")
                                                if hasattr(result_block, "return_code") and result_block.return_code != 0:
                                                    result_parts.append(f"Exit code: {result_block.return_code}")
                                                if result_parts:
                                                    result_text = f"\n💻 [Code Execution Result]\n{chr(10).join(result_parts)}\n"
                                                    yield StreamChunk(
                                                        type="content",
                                                        content=result_text,
                                                    )
                                    elif event.type == "content_block_delta":
                                        if hasattr(event, "delta"):
                                            if event.delta.type == "text_delta":
                                                text_chunk = event.delta.text
                                                content_local += text_chunk
                                                log_backend_agent_message(
                                                    agent_id or "default",
                                                    "RECV",
                                                    {"content": text_chunk},
                                                    backend_name="claude",
                                                )
                                                log_stream_chunk(
                                                    "backend.claude",
                                                    "content",
                                                    text_chunk,
                                                    agent_id,
                                                )
                                                yield StreamChunk(type="content", content=text_chunk)
                                            elif event.delta.type == "input_json_delta":
                                                if hasattr(event, "index"):
                                                    for (
                                                        tool_id,
                                                        tool_data,
                                                    ) in current_tool_uses_local.items():
                                                        if tool_data.get("index") == event.index:
                                                            partial_json = getattr(
                                                                event.delta,
                                                                "partial_json",
                                                                "",
                                                            )
                                                            tool_data["input"] += partial_json
                                                            break
                                    elif event.type == "content_block_stop":
                                        if hasattr(event, "index"):
                                            for (
                                                tool_id,
                                                tool_data,
                                            ) in current_tool_uses_local.items():
                                                if tool_data.get("index") == event.index and tool_data.get("server_side"):
                                                    tool_name = tool_data.get("name", "")
                                                    tool_input = tool_data.get("input", "")
                                                    try:
                                                        parsed_input = json.loads(tool_input) if tool_input else {}
                                                    except json.JSONDecodeError:
                                                        parsed_input = {"raw_input": tool_input}
                                                    if tool_name == "code_execution":
                                                        code = parsed_input.get("code", "")
                                                        if code:
                                                            yield StreamChunk(
                                                                type="content",
                                                                content=f"💻 [Code] {code}\n",
                                                            )
                                                        yield StreamChunk(
                                                            type="content",
                                                            content="✅ [Code Execution] Completed\n",
                                                        )
                                                    elif tool_name == "web_search":
                                                        query = parsed_input.get("query", "")
                                                        if query:
                                                            yield StreamChunk(
                                                                type="content",
                                                                content=f"🔍 [Query] '{query}'\n",
                                                            )
                                                        yield StreamChunk(
                                                            type="content",
                                                            content="✅ [Web Search] Completed\n",
                                                        )
                                                    tool_data["processed"] = True
                                                    break
                                    elif event.type == "message_delta":
                                        pass
                                    elif event.type == "message_stop":
                                        # Build final response and yield tool_calls for user-defined non-MCP tools
                                        user_tool_calls = []
                                        for tool_use in current_tool_uses_local.values():
                                            tool_name = tool_use.get("name", "")
                                            is_server_side = tool_use.get("server_side", False)
                                            if not is_server_side and tool_name not in ["web_search", "code_execution"]:
                                                tool_input = tool_use.get("input", "")
                                                try:
                                                    parsed_input = json.loads(tool_input) if tool_input else {}
                                                except json.JSONDecodeError:
                                                    parsed_input = {"raw_input": tool_input}
                                                user_tool_calls.append(
                                                    {
                                                        "id": tool_use["id"],
                                                        "type": "function",
                                                        "function": {
                                                            "name": tool_name,
                                                            "arguments": parsed_input,
                                                        },
                                                    },
                                                )

                                        if user_tool_calls:
                                            log_stream_chunk(
                                                "backend.claude",
                                                "tool_calls",
                                                user_tool_calls,
                                                agent_id,
                                            )
                                            yield StreamChunk(
                                                type="tool_calls",
                                                tool_calls=user_tool_calls,
                                            )

                                        complete_message = {
                                            "role": "assistant",
                                            "content": content_local.strip(),
                                        }
                                        if user_tool_calls:
                                            complete_message["tool_calls"] = user_tool_calls
                                        log_stream_chunk(
                                            "backend.claude",
                                            "complete_message",
                                            complete_message,
                                            agent_id,
                                        )
                                        yield StreamChunk(
                                            type="complete_message",
                                            complete_message=complete_message,
                                        )

                                        # Track usage for pricing
                                        if all_params.get("enable_web_search", False):
                                            self.search_count += 1
                                        if all_params.get("enable_code_execution", False):
                                            self.code_session_hours += 0.083

                                        log_stream_chunk("backend.claude", "done", None, agent_id)
                                        yield StreamChunk(type="done")
                                        return
                                except Exception as event_error:
                                    error_msg = f"Event processing error: {event_error}"
                                    log_stream_chunk("backend.claude", "error", error_msg, agent_id)
                                    yield StreamChunk(type="error", error=error_msg)
                                    continue

                        # Run normal stream
                        async for chunk in run_stream(api_params):
                            yield chunk

                except Exception as e:
                    # Enhanced error handling for MCP-related errors during streaming
                    if isinstance(
                        e,
                        (MCPConnectionError, MCPTimeoutError, MCPServerError, MCPError),
                    ):
                        # Record failure for circuit breaker
                        if self._circuit_breakers_enabled and self._mcp_tools_circuit_breaker and MCPSetupManager and MCPCircuitBreakerManager:
                            try:
                                normalized_servers = MCPSetupManager.normalize_mcp_servers(self.mcp_servers)  # type: ignore[union-attr]
                                mcp_tools_servers = MCPSetupManager.separate_stdio_streamable_servers(normalized_servers)  # type: ignore[union-attr]
                                await MCPCircuitBreakerManager.record_failure(
                                    mcp_tools_servers,
                                    self._mcp_tools_circuit_breaker,
                                    str(e),
                                    backend_name=self.backend_name,
                                    agent_id=agent_id,
                                )  # type: ignore[union-attr]
                            except Exception as cb_error:
                                logger.warning(f"Failed to record circuit breaker failure: {cb_error}")

                        # Build params and provider tools for fallback
                        all_params = {**self.config, **kwargs}
                        api_params = await self._build_claude_api_params(messages, tools, all_params)
                        provider_tools = []
                        if all_params.get("enable_web_search", False):
                            provider_tools.append({"type": "web_search_20250305", "name": "web_search"})
                        if all_params.get("enable_code_execution", False):
                            provider_tools.append(
                                {
                                    "type": "code_execution_20250522",
                                    "name": "code_execution",
                                },
                            )

                        async def fallback_stream(params: Dict[str, Any]):
                            # Reuse the non-MCP run_stream helper
                            async for chunk in run_stream(params):
                                yield chunk

                        async for chunk in self._handle_mcp_error_and_fallback_claude(e, api_params, provider_tools, fallback_stream):
                            yield chunk
                    else:
                        logger.error(f"Streaming error: {e}")
                        yield StreamChunk(type="error", error=str(e))
                finally:
                    try:
                        if hasattr(client, "aclose"):
                            await client.aclose()
                    except Exception:
                        pass
        except Exception as e:
            # Handle exceptions that occur during MCP setup (__aenter__) or teardown
            try:
                import anthropic

                client = anthropic.AsyncAnthropic(api_key=self.api_key)

                all_params = {**self.config, **kwargs}
                api_params = await self._build_claude_api_params(messages, tools, all_params)

                provider_tools = []
                if all_params.get("enable_web_search", False):
                    provider_tools.append({"type": "web_search_20250305", "name": "web_search"})
                if all_params.get("enable_code_execution", False):
                    provider_tools.append({"type": "code_execution_20250522", "name": "code_execution"})

                async def fallback_stream(params: Dict[str, Any]):
                    # Minimal non-MCP streaming for fallback
                    if "betas" in params:
                        st = await client.beta.messages.create(**params)
                    else:
                        st = await client.messages.create(**params)
                    content_local = ""
                    async for event in st:
                        if event.type == "content_block_delta" and hasattr(event, "delta") and event.delta.type == "text_delta":
                            text_chunk = event.delta.text
                            content_local += text_chunk
                            yield StreamChunk(type="content", content=text_chunk)
                        elif event.type == "message_stop":
                            yield StreamChunk(
                                type="complete_message",
                                complete_message={
                                    "role": "assistant",
                                    "content": content_local.strip(),
                                },
                            )
                            yield StreamChunk(type="done")
                            return

                if isinstance(e, (MCPConnectionError, MCPTimeoutError, MCPServerError, MCPError)):
                    async for chunk in self._handle_mcp_error_and_fallback(e, api_params, provider_tools, fallback_stream):
                        yield chunk
                else:
                    if self.mcp_servers:
                        yield StreamChunk(
                            type="mcp_status",
                            status="mcp_unavailable",
                            content=f"⚠️ [MCP] Setup failed; continuing without MCP ({e})",
                            source="mcp_setup",
                        )
                    async for chunk in fallback_stream(api_params):
                        yield chunk
            except Exception as inner_e:
                logger.error(f"Streaming error during MCP setup fallback: {inner_e}")
                yield StreamChunk(type="error", error=str(inner_e))
            finally:
                try:
                    if "client" in locals() and hasattr(client, "aclose"):
                        await client.aclose()
                except Exception:
                    pass

    def get_provider_name(self) -> str:
        """Get the provider name."""
        return "Claude"

    def get_supported_builtin_tools(self) -> List[str]:
        """Get list of builtin tools supported by Claude."""
        return ["web_search", "code_execution"]

    def create_tool_result_message(self, tool_call: Dict[str, Any], result_content: str) -> Dict[str, Any]:
        """Create tool result message in Claude's expected format."""
        tool_call_id = self.extract_tool_call_id(tool_call)
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "content": result_content,
                },
            ],
        }

    def get_filesystem_support(self) -> FilesystemSupport:
        """Claude supports filesystem through MCP servers."""
        return FilesystemSupport.MCP

    def extract_tool_result_content(self, tool_result_message: Dict[str, Any]) -> str:
        """Extract content from Claude tool result message."""
        content = tool_result_message.get("content", [])
        if isinstance(content, list) and content:
            for item in content:
                if isinstance(item, dict) and item.get("type") == "tool_result":
                    return item.get("content", "")
        return ""

    def reset_tool_usage(self):
        """Reset tool usage tracking."""
        self.search_count = 0
        self.code_session_hours = 0.0
        super().reset_token_usage()
