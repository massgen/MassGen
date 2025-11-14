# -*- coding: utf-8 -*-
"""
Gemini backend implementation using structured output for voting and answer submission.

APPROACH: Uses structured output instead of function declarations to handle the limitation
where Gemini API cannot combine builtin tools with user-defined function declarations.

KEY FEATURES:
- ✅ Structured output for vote and new_answer mechanisms
- ✅ Builtin tools support (code_execution + grounding)
- ✅ Streaming with proper token usage tracking
- ✅ Error handling and response parsing
- ✅ Compatible with MassGen StreamChunk architecture

TECHNICAL SOLUTION:
- Uses Pydantic models to define structured output schemas
- Prompts model to use specific JSON format for voting/answering
- Converts structured responses to standard tool call format
- Maintains compatibility with existing MassGen workflow
"""

import asyncio
import json
import logging
import os
from typing import Any, AsyncGenerator, Dict, List, Optional

from ..api_params_handler._gemini_api_params_handler import GeminiAPIParamsHandler
from ..formatter._gemini_formatter import GeminiFormatter
from ..logger_config import (
    log_backend_activity,
    log_backend_agent_message,
    log_stream_chunk,
    log_tool_call,
    logger,
)
from .base import FilesystemSupport, StreamChunk
from .base_with_custom_tool_and_mcp import (
    CustomToolAndMCPBackend,
    CustomToolChunk,
    ToolExecutionConfig,
)
from .gemini_utils import CoordinationResponse, PostEvaluationResponse


# Suppress Gemini SDK logger warning about non-text parts in response
# Using custom filter per https://github.com/googleapis/python-genai/issues/850
class NoFunctionCallWarning(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if "there are non-text parts in the response:" in message:
            return False
        return True


logging.getLogger("google_genai.types").addFilter(NoFunctionCallWarning())

# MCP integration imports
try:
    from ..mcp_tools import (
        MCPConnectionError,
        MCPError,
        MCPServerError,
        MCPTimeoutError,
    )
except ImportError:  # MCP not installed or import failed within mcp_tools
    MCPError = ImportError  # type: ignore[assignment]
    MCPConnectionError = ImportError  # type: ignore[assignment]
    MCPTimeoutError = ImportError  # type: ignore[assignment]
    MCPServerError = ImportError  # type: ignore[assignment]

# Import MCP backend utilities
try:
    from ..mcp_tools.backend_utils import (
        MCPErrorHandler,
        MCPMessageManager,
        MCPResourceManager,
    )
except ImportError:
    MCPErrorHandler = None  # type: ignore[assignment]
    MCPMessageManager = None  # type: ignore[assignment]
    MCPResourceManager = None  # type: ignore[assignment]


def format_tool_response_as_json(response_text: str) -> str:
    """
    Format tool response text as pretty-printed JSON if possible.

    Args:
        response_text: The raw response text from a tool

    Returns:
        Pretty-printed JSON string if response is valid JSON, otherwise original text
    """
    try:
        # Try to parse as JSON
        parsed = json.loads(response_text)
        # Return pretty-printed JSON with 2-space indentation
        return json.dumps(parsed, indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        # If not valid JSON, return original text
        return response_text


class GeminiBackend(CustomToolAndMCPBackend):
    """Google Gemini backend using structured output for coordination and MCP tool integration."""

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        # Store Gemini-specific API key before calling parent init
        gemini_api_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

        # Call parent class __init__ - this initializes custom_tool_manager and MCP-related attributes
        super().__init__(gemini_api_key, **kwargs)

        # Override API key with Gemini-specific value
        self.api_key = gemini_api_key

        # Gemini-specific counters for builtin tools
        self.search_count = 0
        self.code_execution_count = 0

        # New components for separation of concerns
        self.formatter = GeminiFormatter()
        self.api_params_handler = GeminiAPIParamsHandler(self)

        # Gemini-specific MCP monitoring (additional to parent class)
        self._mcp_tool_successes = 0
        self._mcp_connection_retries = 0

        # Active tool result capture during manual tool execution
        self._active_tool_result_store: Optional[Dict[str, str]] = None

    def _setup_permission_hooks(self):
        """Override base class - Gemini uses session-based permissions, not function hooks."""
        logger.debug("[Gemini] Using session-based permissions, skipping function hook setup")

    async def _process_stream(self, stream, all_params, agent_id: Optional[str] = None) -> AsyncGenerator[StreamChunk, None]:
        """
        Required by CustomToolAndMCPBackend abstract method.
        Not used by Gemini - Gemini SDK handles streaming directly in stream_with_tools().
        """
        if False:
            yield  # Make this an async generator
        raise NotImplementedError("Gemini uses custom streaming logic in stream_with_tools()")

    async def _setup_mcp_tools(self) -> None:
        """
        Override parent class - Use base class MCP setup for manual execution pattern.
        This method is called by the parent class's __aenter__() context manager.
        """
        await super()._setup_mcp_tools()

    def supports_upload_files(self) -> bool:
        """
        Override parent class - Gemini does not support upload_files preprocessing.
        Returns False to skip upload_files processing in parent class methods.
        """
        return False

    def _create_client(self, **kwargs):
        pass

    async def _stream_with_custom_and_mcp_tools(
        self,
        current_messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        client,
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        yield StreamChunk(type="error", error="Not implemented")

    async def stream_with_tools(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs) -> AsyncGenerator[StreamChunk, None]:
        """Stream response using Gemini API with manual MCP execution pattern.

        Tool Execution Behavior:
        - Custom tools: Always executed (not blocked by planning mode or circuit breaker)
        - MCP tools: Blocked by planning mode during coordination, blocked by circuit breaker when servers fail
        - Provider tools (vote/new_answer): Emitted as StreamChunks but not executed (handled by orchestrator)
        """
        # Use instance agent_id (from __init__) or get from kwargs if not set
        agent_id = self.agent_id or kwargs.get("agent_id", None)
        client = None
        stream = None

        # Build execution context for tools (generic, not tool-specific)
        # This is required for custom tool execution
        from .base_with_custom_tool_and_mcp import ExecutionContext

        self._execution_context = ExecutionContext(
            messages=messages,
            agent_system_message=kwargs.get("system_message", None),
            agent_id=self.agent_id,
            backend_name="gemini",
            current_stage=self.coordination_stage,
        )

        if self._nlip_enabled:
            logger.info(
                f"[Gemini] NLIP routing enabled for agent {agent_id or self.agent_id}",
            )

        # Track whether MCP tools were actually used in this turn
        mcp_used = False

        log_backend_activity(
            "gemini",
            "Starting stream_with_tools",
            {"num_messages": len(messages), "num_tools": len(tools) if tools else 0},
            agent_id=agent_id,
        )

        # Trim message history for MCP if needed
        if self.mcp_servers and MCPMessageManager is not None and hasattr(self, "_max_mcp_message_history") and self._max_mcp_message_history > 0:
            original_count = len(messages)
            messages = MCPMessageManager.trim_message_history(messages, self._max_mcp_message_history)
            if len(messages) < original_count:
                log_backend_activity(
                    "gemini",
                    "Trimmed MCP message history",
                    {
                        "original": original_count,
                        "trimmed": len(messages),
                        "limit": self._max_mcp_message_history,
                    },
                    agent_id=agent_id,
                )

        try:
            from google import genai
            from google.genai import types

            # Setup MCP using base class if not already initialized
            if not self._mcp_initialized and self.mcp_servers:
                await self._setup_mcp_tools()
                if self._mcp_initialized:
                    yield StreamChunk(
                        type="mcp_status",
                        status="mcp_initialized",
                        content="✅ [MCP] Tools initialized",
                        source="mcp_tools",
                    )

            # Merge constructor config with stream kwargs
            all_params = {**self.config, **kwargs}

            # Detect custom tools
            using_custom_tools = bool(self.custom_tool_manager and len(self._custom_tool_names) > 0)

            # Detect coordination mode
            is_coordination = self.formatter.has_coordination_tools(tools)
            is_post_evaluation = self.formatter.has_post_evaluation_tools(tools)

            valid_agent_ids = None

            if is_coordination:
                # Extract valid agent IDs from vote tool enum if available
                for tool in tools:
                    if tool.get("type") == "function":
                        func_def = tool.get("function", {})
                        if func_def.get("name") == "vote":
                            agent_id_param = func_def.get("parameters", {}).get("properties", {}).get("agent_id", {})
                            if "enum" in agent_id_param:
                                valid_agent_ids = agent_id_param["enum"]
                            break

            # Build content string from messages using formatter
            full_content = self.formatter.format_messages(messages)
            # For coordination requests, modify the prompt to use structured output
            if is_coordination:
                full_content = self.formatter.build_structured_output_prompt(full_content, valid_agent_ids)
            elif is_post_evaluation:
                # For post-evaluation, modify prompt to use structured output
                full_content = self.formatter.build_post_evaluation_prompt(full_content)

            # Create Gemini client
            client = genai.Client(api_key=self.api_key)

            # Setup builtin tools via API params handler
            builtin_tools = self.api_params_handler.get_provider_tools(all_params)

            # Build config via API params handler
            config = await self.api_params_handler.build_api_params(messages, tools, all_params)

            # Extract model name
            model_name = all_params.get("model")

            # ====================================================================
            # Tool Registration Phase: Convert and register tools for manual execution
            # ====================================================================
            tools_to_apply = []

            # Add custom tools if available
            if using_custom_tools:
                try:
                    # Get custom tools schemas (in OpenAI format)
                    custom_tools_schemas = self._get_custom_tools_schemas()
                    if custom_tools_schemas:
                        # Convert to Gemini SDK format using formatter
                        custom_tools_functions = self.formatter.format_custom_tools(
                            custom_tools_schemas,
                            return_sdk_objects=True,
                        )

                        if custom_tools_functions:
                            # Wrap FunctionDeclarations in a Tool object for Gemini SDK
                            custom_tool = types.Tool(function_declarations=custom_tools_functions)
                            tools_to_apply.append(custom_tool)

                            logger.debug(f"[Gemini] Registered {len(custom_tools_functions)} custom tools for manual execution")

                            yield StreamChunk(
                                type="custom_tool_status",
                                status="custom_tools_registered",
                                content=f"🔧 [Custom Tools] Registered {len(custom_tools_functions)} tools",
                                source="custom_tools",
                            )
                except Exception as e:
                    logger.warning(f"[Gemini] Failed to register custom tools: {e}")

            # Add MCP tools if available (unless blocked by planning mode)
            if self._mcp_initialized and self._mcp_functions:
                # Check planning mode
                if self.is_planning_mode_enabled():
                    blocked_tools = self.get_planning_mode_blocked_tools()

                    if not blocked_tools:
                        # Empty set means block ALL MCP tools (backward compatible)
                        logger.info("[Gemini] Planning mode enabled - blocking ALL MCP tools during coordination")
                        yield StreamChunk(
                            type="mcp_status",
                            status="planning_mode_blocked",
                            content="🚫 [MCP] Planning mode active - all MCP tools blocked during coordination",
                            source="planning_mode",
                        )

                    else:
                        # Selective blocking - register all MCP tools, execution layer will block specific ones
                        logger.info(f"[Gemini] Planning mode enabled - registering all MCP tools, will block {len(blocked_tools)} at execution")
                        try:
                            # Convert MCP tools using formatter
                            mcp_tools_functions = self.formatter.format_mcp_tools(self._mcp_functions, return_sdk_objects=True)

                            if mcp_tools_functions:
                                # Wrap in Tool object
                                mcp_tool = types.Tool(function_declarations=mcp_tools_functions)
                                tools_to_apply.append(mcp_tool)

                                # Mark MCP as used since tools are registered (even with selective blocking)
                                mcp_used = True

                                logger.debug(f"[Gemini] Registered {len(mcp_tools_functions)} MCP tools for selective blocking")

                                yield StreamChunk(
                                    type="mcp_status",
                                    status="mcp_tools_registered",
                                    content=f"🔧 [MCP] Registered {len(mcp_tools_functions)} tools (selective blocking enabled)",
                                    source="mcp_tools",
                                )
                        except Exception as e:
                            logger.warning(f"[Gemini] Failed to register MCP tools: {e}")
                else:
                    # No planning mode - register all MCP tools
                    try:
                        # Convert MCP tools using formatter
                        mcp_tools_functions = self.formatter.format_mcp_tools(self._mcp_functions, return_sdk_objects=True)

                        if mcp_tools_functions:
                            # Wrap in Tool object
                            mcp_tool = types.Tool(function_declarations=mcp_tools_functions)
                            tools_to_apply.append(mcp_tool)

                            # Mark MCP as used since tools are registered
                            mcp_used = True

                            logger.debug(f"[Gemini] Registered {len(mcp_tools_functions)} MCP tools for manual execution")

                            yield StreamChunk(
                                type="mcp_status",
                                status="mcp_tools_registered",
                                content=f"🔧 [MCP] Registered {len(mcp_tools_functions)} tools",
                                source="mcp_tools",
                            )
                    except Exception as e:
                        logger.warning(f"[Gemini] Failed to register MCP tools: {e}")

            # Apply tools to config
            if tools_to_apply:
                config["tools"] = tools_to_apply
                # Disable automatic function calling for manual execution
                config["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(disable=True)
                logger.debug("[Gemini] Disabled automatic function calling for manual execution")
            else:
                # No custom/MCP tools, add builtin tools if any
                if builtin_tools:
                    config["tools"] = builtin_tools

            # For coordination/post-evaluation requests, use JSON response format when no tools present
            if not tools_to_apply and not builtin_tools:
                if is_coordination:
                    config["response_mime_type"] = "application/json"
                    config["response_schema"] = CoordinationResponse.model_json_schema()
                elif is_post_evaluation:
                    config["response_mime_type"] = "application/json"
                    config["response_schema"] = PostEvaluationResponse.model_json_schema()

            # Log messages being sent
            log_backend_agent_message(
                agent_id or "default",
                "SEND",
                {
                    "content": full_content,
                    "custom_tools": len(tools_to_apply) if tools_to_apply else 0,
                },
                backend_name="gemini",
            )

            # ====================================================================
            # Streaming Phase: Stream with simple function call detection
            # ====================================================================
            stream = await client.aio.models.generate_content_stream(
                model=model_name,
                contents=full_content,
                config=config,
            )

            # Simple list accumulation for function calls (no trackers)
            captured_function_calls = []
            full_content_text = ""
            last_response_with_candidates = None

            # Stream chunks and capture function calls
            async for chunk in stream:
                # Detect function calls in candidates
                if hasattr(chunk, "candidates") and chunk.candidates:
                    for candidate in chunk.candidates:
                        if hasattr(candidate, "content") and candidate.content:
                            if hasattr(candidate.content, "parts") and candidate.content.parts:
                                for part in candidate.content.parts:
                                    # Check for function_call part
                                    if hasattr(part, "function_call") and part.function_call:
                                        # Extract call data
                                        tool_name = part.function_call.name
                                        tool_args = dict(part.function_call.args) if part.function_call.args else {}

                                        # Create call record
                                        call_id = f"call_{len(captured_function_calls)}"
                                        captured_function_calls.append(
                                            {
                                                "call_id": call_id,
                                                "name": tool_name,
                                                "arguments": json.dumps(tool_args),
                                            },
                                        )

                                        logger.info(f"[Gemini] Function call detected: {tool_name}")

                # Process text content
                if hasattr(chunk, "text") and chunk.text:
                    chunk_text = chunk.text
                    full_content_text += chunk_text
                    log_backend_agent_message(
                        agent_id,
                        "RECV",
                        {"content": chunk_text},
                        backend_name="gemini",
                    )
                    log_stream_chunk("backend.gemini", "content", chunk_text, agent_id)
                    yield StreamChunk(type="content", content=chunk_text)

                # Buffer last chunk with candidates
                if hasattr(chunk, "candidates") and chunk.candidates:
                    last_response_with_candidates = chunk

            # ====================================================================
            # Structured Coordination Output Parsing
            # ====================================================================
            # Check for structured coordination output when no function calls captured
            if is_coordination and not captured_function_calls and full_content_text:
                # Try to parse structured response from text content
                parsed = self.formatter.extract_structured_response(full_content_text)

                if parsed and isinstance(parsed, dict):
                    # Convert structured response to tool calls
                    tool_calls = self.formatter.convert_structured_to_tool_calls(parsed)

                    if tool_calls:
                        # Categorize the tool calls
                        mcp_calls, custom_calls, provider_calls = self._categorize_tool_calls(tool_calls)

                        # Handle provider (workflow) calls - these are coordination actions
                        # We yield StreamChunk entries but do NOT execute them
                        if provider_calls:
                            # Convert provider calls to tool_calls format for orchestrator
                            workflow_tool_calls = []
                            for call in provider_calls:
                                tool_name = call.get("name", "")
                                tool_args_str = call.get("arguments", "{}")

                                # Parse arguments if they're a string
                                if isinstance(tool_args_str, str):
                                    try:
                                        tool_args = json.loads(tool_args_str)
                                    except json.JSONDecodeError:
                                        tool_args = {}
                                else:
                                    tool_args = tool_args_str

                                # Log the coordination action
                                logger.info(f"[Gemini] Structured coordination action: {tool_name}")
                                log_tool_call(
                                    agent_id,
                                    tool_name,
                                    tool_args,
                                    None,
                                    backend_name="gemini",
                                )

                                # Build tool call in standard format
                                workflow_tool_calls.append(
                                    {
                                        "id": call.get("call_id", f"call_{len(workflow_tool_calls)}"),
                                        "type": "function",
                                        "function": {
                                            "name": tool_name,
                                            "arguments": tool_args,
                                        },
                                    },
                                )

                            # Emit tool_calls chunk for orchestrator to process
                            if workflow_tool_calls:
                                log_stream_chunk("backend.gemini", "tool_calls", workflow_tool_calls, agent_id)
                                yield StreamChunk(
                                    type="tool_calls",
                                    tool_calls=workflow_tool_calls,
                                    source="gemini",
                                )

                        # Do not execute workflow tools - just return after yielding
                        # The orchestrator will handle these coordination actions
                        if provider_calls:
                            # Emit completion status if MCP was actually used
                            if mcp_used:
                                yield StreamChunk(
                                    type="mcp_status",
                                    status="mcp_session_complete",
                                    content="✅ [MCP] Session completed",
                                    source="mcp_tools",
                                )

                            yield StreamChunk(type="done")
                            return

            # ====================================================================
            # Tool Execution Phase: Execute captured function calls using base class
            # ====================================================================
            if captured_function_calls:
                # Categorize function calls using base class helper
                mcp_calls, custom_calls, provider_calls = self._categorize_tool_calls(captured_function_calls)

                # ====================================================================
                # Handle provider (workflow) calls - emit as StreamChunks but do NOT execute
                # ====================================================================
                if provider_calls:
                    # Convert provider calls to tool_calls format for orchestrator
                    workflow_tool_calls = []
                    for call in provider_calls:
                        tool_name = call.get("name", "")
                        tool_args_str = call.get("arguments", "{}")

                        # Parse arguments if they're a string
                        if isinstance(tool_args_str, str):
                            try:
                                tool_args = json.loads(tool_args_str)
                            except json.JSONDecodeError:
                                tool_args = {}
                        else:
                            tool_args = tool_args_str

                        # Log the coordination action
                        logger.info(f"[Gemini] Function call coordination action: {tool_name}")
                        log_tool_call(
                            agent_id,
                            tool_name,
                            tool_args,
                            None,
                            backend_name="gemini",
                        )

                        # Build tool call in standard format
                        workflow_tool_calls.append(
                            {
                                "id": call.get("call_id", f"call_{len(workflow_tool_calls)}"),
                                "type": "function",
                                "function": {
                                    "name": tool_name,
                                    "arguments": tool_args,
                                },
                            },
                        )

                    # Emit tool_calls chunk for orchestrator to process
                    if workflow_tool_calls:
                        log_stream_chunk("backend.gemini", "tool_calls", workflow_tool_calls, agent_id)
                        yield StreamChunk(
                            type="tool_calls",
                            tool_calls=workflow_tool_calls,
                            source="gemini",
                        )

                    if mcp_used:
                        yield StreamChunk(
                            type="mcp_status",
                            status="mcp_session_complete",
                            content="✅ [MCP] Session completed",
                            source="mcp_tools",
                        )

                    yield StreamChunk(type="done")
                    return

                # Initialize for execution
                updated_messages = messages.copy()
                processed_call_ids = set()

                # Configuration for custom tool execution
                CUSTOM_TOOL_CONFIG = ToolExecutionConfig(
                    tool_type="custom",
                    chunk_type="custom_tool_status",
                    emoji_prefix="🔧 [Custom Tool]",
                    success_emoji="✅ [Custom Tool]",
                    error_emoji="❌ [Custom Tool Error]",
                    source_prefix="custom_",
                    status_called="custom_tool_called",
                    status_response="custom_tool_response",
                    status_error="custom_tool_error",
                    execution_callback=self._execute_custom_tool,
                )

                # Configuration for MCP tool execution
                MCP_TOOL_CONFIG = ToolExecutionConfig(
                    tool_type="mcp",
                    chunk_type="mcp_status",
                    emoji_prefix="🔧 [MCP Tool]",
                    success_emoji="✅ [MCP Tool]",
                    error_emoji="❌ [MCP Tool Error]",
                    source_prefix="mcp_",
                    status_called="mcp_tool_called",
                    status_response="mcp_tool_response",
                    status_error="mcp_tool_error",
                    execution_callback=self._execute_mcp_function_with_retry,
                )

                # Capture tool execution results for continuation loop
                tool_results: Dict[str, str] = {}
                self._active_tool_result_store = tool_results

                try:
                    # Execute custom tools
                    for call in custom_calls:
                        if self._nlip_enabled and self._nlip_router:
                            logger.info(f"[NLIP] Using NLIP routing for custom tool {call['name']}")
                            try:
                                async for chunk in self._stream_tool_execution_via_nlip(
                                    call,
                                    CUSTOM_TOOL_CONFIG,
                                    updated_messages,
                                    processed_call_ids,
                                ):
                                    yield chunk
                            except Exception as exc:
                                logger.warning(
                                    f"[NLIP] Routing failed for {call['name']}: {exc}. " f"Falling back to direct execution.",
                                )
                                async for chunk in self._execute_tool_with_logging(
                                    call,
                                    CUSTOM_TOOL_CONFIG,
                                    updated_messages,
                                    processed_call_ids,
                                ):
                                    yield chunk
                        else:
                            reason = "disabled" if not self._nlip_enabled else "router unavailable"
                            logger.info(
                                f"[Custom Tool] Direct execution for {call['name']} (NLIP {reason})",
                            )
                            async for chunk in self._execute_tool_with_logging(
                                call,
                                CUSTOM_TOOL_CONFIG,
                                updated_messages,
                                processed_call_ids,
                            ):
                                yield chunk

                    # Check circuit breaker before MCP tool execution
                    if mcp_calls and not await self._check_circuit_breaker_before_execution():
                        logger.warning("[Gemini] All MCP servers blocked by circuit breaker")
                        yield StreamChunk(
                            type="mcp_status",
                            status="mcp_blocked",
                            content="⚠️ [MCP] All servers blocked by circuit breaker",
                            source="circuit_breaker",
                        )
                        # Clear mcp_calls to skip execution
                        mcp_calls = []

                    # Execute MCP tools
                    for call in mcp_calls:
                        # Mark MCP as used when at least one MCP call is about to be executed
                        mcp_used = True

                        if self._nlip_enabled and self._nlip_router:
                            logger.info(f"[NLIP] Using NLIP routing for MCP tool {call['name']}")
                            try:
                                async for chunk in self._stream_tool_execution_via_nlip(
                                    call,
                                    MCP_TOOL_CONFIG,
                                    updated_messages,
                                    processed_call_ids,
                                ):
                                    yield chunk
                            except Exception as exc:
                                logger.warning(
                                    f"[NLIP] Routing failed for {call['name']}: {exc}. " f"Falling back to direct execution.",
                                )
                                async for chunk in self._execute_tool_with_logging(
                                    call,
                                    MCP_TOOL_CONFIG,
                                    updated_messages,
                                    processed_call_ids,
                                ):
                                    yield chunk
                        else:
                            reason = "disabled" if not self._nlip_enabled else "router unavailable"
                            logger.info(
                                f"[MCP Tool] Direct execution for {call['name']} (NLIP {reason})",
                            )
                            async for chunk in self._execute_tool_with_logging(
                                call,
                                MCP_TOOL_CONFIG,
                                updated_messages,
                                processed_call_ids,
                            ):
                                yield chunk
                finally:
                    self._active_tool_result_store = None

                executed_calls = custom_calls + mcp_calls

                # Build initial conversation history using SDK Content objects
                conversation_history: List[types.Content] = [
                    types.Content(parts=[types.Part(text=full_content)], role="user"),
                ]

                if executed_calls:
                    model_parts = []
                    for call in executed_calls:
                        args_payload: Any = call.get("arguments", {})
                        if isinstance(args_payload, str):
                            try:
                                args_payload = json.loads(args_payload)
                            except json.JSONDecodeError:
                                args_payload = {}
                        if not isinstance(args_payload, dict):
                            args_payload = {}
                        model_parts.append(
                            types.Part.from_function_call(
                                name=call.get("name", ""),
                                args=args_payload,
                            ),
                        )
                    if model_parts:
                        conversation_history.append(types.Content(parts=model_parts, role="model"))

                    response_parts = []
                    for call in executed_calls:
                        call_id = call.get("call_id")
                        result_text = tool_results.get(call_id or "", "No result")
                        response_parts.append(
                            types.Part.from_function_response(
                                name=call.get("name", ""),
                                response={"result": result_text},
                            ),
                        )
                    if response_parts:
                        conversation_history.append(types.Content(parts=response_parts, role="user"))

                last_continuation_chunk = None

                while True:
                    continuation_stream = await client.aio.models.generate_content_stream(
                        model=model_name,
                        contents=conversation_history,
                        config=config,
                    )
                    stream = continuation_stream

                    new_function_calls = []
                    continuation_text = ""

                    async for chunk in continuation_stream:
                        if hasattr(chunk, "candidates") and chunk.candidates:
                            last_continuation_chunk = chunk
                            for candidate in chunk.candidates:
                                if hasattr(candidate, "content") and candidate.content:
                                    if hasattr(candidate.content, "parts") and candidate.content.parts:
                                        for part in candidate.content.parts:
                                            if hasattr(part, "function_call") and part.function_call:
                                                tool_name = part.function_call.name
                                                tool_args = dict(part.function_call.args) if part.function_call.args else {}
                                                call_id = f"call_{len(new_function_calls)}"
                                                new_function_calls.append(
                                                    {
                                                        "call_id": call_id,
                                                        "name": tool_name,
                                                        "arguments": json.dumps(tool_args),
                                                    },
                                                )

                        if hasattr(chunk, "text") and chunk.text:
                            chunk_text = chunk.text
                            continuation_text += chunk_text
                            log_backend_agent_message(
                                agent_id,
                                "RECV",
                                {"content": chunk_text},
                                backend_name="gemini",
                            )
                            log_stream_chunk("backend.gemini", "content", chunk_text, agent_id)
                            yield StreamChunk(type="content", content=chunk_text)

                    if continuation_text:
                        conversation_history.append(
                            types.Content(parts=[types.Part(text=continuation_text)], role="model"),
                        )
                        full_content_text += continuation_text

                    if last_continuation_chunk:
                        last_response_with_candidates = last_continuation_chunk

                    if not new_function_calls:
                        # ====================================================================
                        # Continuation Structured Coordination Output Parsing
                        # ====================================================================
                        # Check for structured coordination output when no function calls in continuation
                        if is_coordination and full_content_text:
                            # Try to parse structured response from accumulated text content
                            parsed = self.formatter.extract_structured_response(full_content_text)

                            if parsed and isinstance(parsed, dict):
                                # Convert structured response to tool calls
                                tool_calls = self.formatter.convert_structured_to_tool_calls(parsed)

                                if tool_calls:
                                    # Categorize the tool calls
                                    mcp_calls, custom_calls, provider_calls = self._categorize_tool_calls(tool_calls)

                                    if provider_calls:
                                        # Convert provider calls to tool_calls format for orchestrator
                                        workflow_tool_calls = []
                                        for call in provider_calls:
                                            tool_name = call.get("name", "")
                                            tool_args_str = call.get("arguments", "{}")

                                            # Parse arguments if they're a string
                                            if isinstance(tool_args_str, str):
                                                try:
                                                    tool_args = json.loads(tool_args_str)
                                                except json.JSONDecodeError:
                                                    tool_args = {}
                                            else:
                                                tool_args = tool_args_str

                                            # Log the coordination action
                                            logger.info(f"[Gemini] Continuation structured coordination action: {tool_name}")
                                            log_tool_call(
                                                agent_id,
                                                tool_name,
                                                tool_args,
                                                None,
                                                backend_name="gemini",
                                            )

                                            # Build tool call in standard format
                                            workflow_tool_calls.append(
                                                {
                                                    "id": call.get("call_id", f"call_{len(workflow_tool_calls)}"),
                                                    "type": "function",
                                                    "function": {
                                                        "name": tool_name,
                                                        "arguments": tool_args,
                                                    },
                                                },
                                            )

                                        # Emit tool_calls chunk for orchestrator to process
                                        if workflow_tool_calls:
                                            log_stream_chunk("backend.gemini", "tool_calls", workflow_tool_calls, agent_id)
                                            yield StreamChunk(
                                                type="tool_calls",
                                                tool_calls=workflow_tool_calls,
                                                source="gemini",
                                            )

                                        if mcp_used:
                                            yield StreamChunk(
                                                type="mcp_status",
                                                status="mcp_session_complete",
                                                content="✅ [MCP] Session completed",
                                                source="mcp_tools",
                                            )

                                        yield StreamChunk(type="done")
                                        return

                        # No structured output found, break continuation loop
                        break

                    next_mcp_calls, next_custom_calls, provider_calls = self._categorize_tool_calls(new_function_calls)

                    # Handle provider calls emitted during continuation
                    if provider_calls:
                        workflow_tool_calls = []
                        for call in provider_calls:
                            tool_name = call.get("name", "")
                            tool_args_str = call.get("arguments", "{}")

                            if isinstance(tool_args_str, str):
                                try:
                                    tool_args = json.loads(tool_args_str)
                                except json.JSONDecodeError:
                                    tool_args = {}
                            else:
                                tool_args = tool_args_str

                            logger.info(f"[Gemini] Continuation coordination action: {tool_name}")
                            log_tool_call(
                                agent_id,
                                tool_name,
                                tool_args,
                                None,
                                backend_name="gemini",
                            )

                            workflow_tool_calls.append(
                                {
                                    "id": call.get("call_id", f"call_{len(workflow_tool_calls)}"),
                                    "type": "function",
                                    "function": {
                                        "name": tool_name,
                                        "arguments": tool_args,
                                    },
                                },
                            )

                        if workflow_tool_calls:
                            log_stream_chunk("backend.gemini", "tool_calls", workflow_tool_calls, agent_id)
                            yield StreamChunk(
                                type="tool_calls",
                                tool_calls=workflow_tool_calls,
                                source="gemini",
                            )

                        if mcp_used:
                            yield StreamChunk(
                                type="mcp_status",
                                status="mcp_session_complete",
                                content="✅ [MCP] Session completed",
                                source="mcp_tools",
                            )

                        yield StreamChunk(type="done")
                        return

                    new_tool_results: Dict[str, str] = {}
                    self._active_tool_result_store = new_tool_results

                    try:
                        for call in next_custom_calls:
                            async for chunk in self._execute_tool_with_logging(
                                call,
                                CUSTOM_TOOL_CONFIG,
                                updated_messages,
                                processed_call_ids,
                            ):
                                yield chunk

                        if next_mcp_calls and not await self._check_circuit_breaker_before_execution():
                            logger.warning("[Gemini] All MCP servers blocked by circuit breaker during continuation")
                            yield StreamChunk(
                                type="mcp_status",
                                status="mcp_blocked",
                                content="⚠️ [MCP] All servers blocked by circuit breaker",
                                source="circuit_breaker",
                            )
                            next_mcp_calls = []

                        for call in next_mcp_calls:
                            mcp_used = True

                            async for chunk in self._execute_tool_with_logging(
                                call,
                                MCP_TOOL_CONFIG,
                                updated_messages,
                                processed_call_ids,
                            ):
                                yield chunk
                    finally:
                        self._active_tool_result_store = None

                    if new_tool_results:
                        tool_results.update(new_tool_results)

                    executed_calls = next_custom_calls + next_mcp_calls

                    if executed_calls:
                        model_parts = []
                        for call in executed_calls:
                            args_payload: Any = call.get("arguments", {})
                            if isinstance(args_payload, str):
                                try:
                                    args_payload = json.loads(args_payload)
                                except json.JSONDecodeError:
                                    args_payload = {}
                            if not isinstance(args_payload, dict):
                                args_payload = {}
                            model_parts.append(
                                types.Part.from_function_call(
                                    name=call.get("name", ""),
                                    args=args_payload,
                                ),
                            )
                        if model_parts:
                            conversation_history.append(types.Content(parts=model_parts, role="model"))

                        response_parts = []
                        for call in executed_calls:
                            call_id = call.get("call_id")
                            result_text = new_tool_results.get(call_id or "", "No result")
                            response_parts.append(
                                types.Part.from_function_response(
                                    name=call.get("name", ""),
                                    response={"result": result_text},
                                ),
                            )
                        if response_parts:
                            conversation_history.append(types.Content(parts=response_parts, role="user"))

            # ====================================================================
            # Completion Phase: Process structured tool calls and builtin indicators
            # ====================================================================
            final_response = last_response_with_candidates

            tool_calls_detected: List[Dict[str, Any]] = []

            if (is_coordination or is_post_evaluation) and full_content_text.strip():
                content = full_content_text
                structured_response = None

                try:
                    structured_response = json.loads(content.strip())
                except json.JSONDecodeError:
                    structured_response = self.formatter.extract_structured_response(content)

                if structured_response and isinstance(structured_response, dict) and structured_response.get("action_type"):
                    raw_tool_calls = self.formatter.convert_structured_to_tool_calls(structured_response)

                    if raw_tool_calls:
                        tool_type = "post_evaluation" if is_post_evaluation else "coordination"
                        workflow_tool_calls: List[Dict[str, Any]] = []

                        for call in raw_tool_calls:
                            tool_name = call.get("name", "")
                            tool_args_str = call.get("arguments", "{}")

                            if isinstance(tool_args_str, str):
                                try:
                                    tool_args = json.loads(tool_args_str)
                                except json.JSONDecodeError:
                                    tool_args = {}
                            else:
                                tool_args = tool_args_str

                            try:
                                log_tool_call(
                                    agent_id,
                                    tool_name or f"unknown_{tool_type}_tool",
                                    tool_args,
                                    result=f"{tool_type}_tool_called",
                                    backend_name="gemini",
                                )
                            except Exception:
                                pass

                            workflow_tool_calls.append(
                                {
                                    "id": call.get("call_id", f"call_{len(workflow_tool_calls)}"),
                                    "type": "function",
                                    "function": {
                                        "name": tool_name,
                                        "arguments": tool_args,
                                    },
                                },
                            )

                        if workflow_tool_calls:
                            tool_calls_detected = workflow_tool_calls
                            log_stream_chunk("backend.gemini", "tool_calls", workflow_tool_calls, agent_id)

            if tool_calls_detected:
                yield StreamChunk(type="tool_calls", tool_calls=tool_calls_detected, source="gemini")

                if mcp_used:
                    yield StreamChunk(
                        type="mcp_status",
                        status="mcp_session_complete",
                        content="✅ [MCP] Session completed",
                        source="mcp_tools",
                    )

                yield StreamChunk(type="done")
                return

            if builtin_tools and final_response and hasattr(final_response, "candidates") and final_response.candidates:
                candidate = final_response.candidates[0]

                if hasattr(candidate, "grounding_metadata") and candidate.grounding_metadata:
                    search_actually_used = False
                    search_queries: List[str] = []

                    if hasattr(candidate.grounding_metadata, "web_search_queries") and candidate.grounding_metadata.web_search_queries:
                        try:
                            for query in candidate.grounding_metadata.web_search_queries:
                                if query and isinstance(query, str) and query.strip():
                                    trimmed_query = query.strip()
                                    search_queries.append(trimmed_query)
                                    search_actually_used = True
                        except (TypeError, AttributeError):
                            pass

                    if hasattr(candidate.grounding_metadata, "grounding_chunks") and candidate.grounding_metadata.grounding_chunks:
                        try:
                            if len(candidate.grounding_metadata.grounding_chunks) > 0:
                                search_actually_used = True
                        except (TypeError, AttributeError):
                            pass

                    if search_actually_used:
                        log_stream_chunk(
                            "backend.gemini",
                            "web_search_result",
                            {"queries": search_queries, "results_integrated": True},
                            agent_id,
                        )
                        log_tool_call(
                            agent_id,
                            "google_search_retrieval",
                            {
                                "queries": search_queries,
                                "chunks_found": len(getattr(candidate.grounding_metadata, "grounding_chunks", []) or []),
                            },
                            result="search_completed",
                            backend_name="gemini",
                        )

                        yield StreamChunk(
                            type="content",
                            content="🔍 [Builtin Tool: Web Search] Results integrated\n",
                        )

                        for query in search_queries:
                            log_stream_chunk(
                                "backend.gemini",
                                "web_search_result",
                                {"queries": search_queries, "results_integrated": True},
                                agent_id,
                            )
                            yield StreamChunk(type="content", content=f"🔍 [Search Query] '{query}'\n")

                        self.search_count += 1

                enable_code_execution = bool(
                    all_params.get("enable_code_execution") or all_params.get("code_execution"),
                )

                if enable_code_execution and hasattr(candidate, "content") and hasattr(candidate.content, "parts"):
                    code_parts: List[str] = []

                    for part in candidate.content.parts:
                        if hasattr(part, "executable_code") and part.executable_code:
                            code_content = getattr(part.executable_code, "code", str(part.executable_code))
                            code_parts.append(f"Code: {code_content}")
                        elif hasattr(part, "code_execution_result") and part.code_execution_result:
                            result_content = getattr(part.code_execution_result, "output", str(part.code_execution_result))
                            code_parts.append(f"Result: {result_content}")

                    if code_parts:
                        log_stream_chunk(
                            "backend.gemini",
                            "code_execution",
                            "Code executed",
                            agent_id,
                        )
                        log_tool_call(
                            agent_id,
                            "code_execution",
                            {"details": code_parts},
                            result="code_execution_completed",
                            backend_name="gemini",
                        )

                        yield StreamChunk(
                            type="content",
                            content="🧮 [Builtin Tool: Code Execution] Results integrated\n",
                        )

                        for entry in code_parts:
                            yield StreamChunk(type="content", content=f"🧮 {entry}\n")

                        self.code_execution_count += 1

            elif final_response and hasattr(final_response, "candidates") and final_response.candidates:
                for candidate in final_response.candidates:
                    if hasattr(candidate, "grounding_metadata"):
                        self.search_count += 1
                        logger.debug(f"[Gemini] Grounding (web search) used, count: {self.search_count}")

                    if hasattr(candidate, "content") and candidate.content:
                        if hasattr(candidate.content, "parts") and candidate.content.parts:
                            for part in candidate.content.parts:
                                if hasattr(part, "executable_code") or hasattr(part, "code_execution_result"):
                                    self.code_execution_count += 1
                                    logger.debug(f"[Gemini] Code execution used, count: {self.code_execution_count}")
                                    break

            # Emit completion status
            if mcp_used:
                yield StreamChunk(
                    type="mcp_status",
                    status="mcp_session_complete",
                    content="✅ [MCP] Session completed",
                    source="mcp_tools",
                )

            yield StreamChunk(type="done")

        except Exception as e:
            logger.error(f"[Gemini] Error in stream_with_tools: {e}")
            raise

        finally:
            await self._cleanup_genai_resources(stream, client)

    async def _try_close_resource(
        self,
        resource: Any,
        method_names: tuple,
        resource_label: str,
    ) -> bool:
        """Try to close a resource using one of the provided method names.

        Args:
            resource: Object to close
            method_names: Method names to try (e.g., ("aclose", "close"))
            resource_label: Label for error logging

        Returns:
            True if closed successfully, False otherwise
        """
        if resource is None:
            return False

        for method_name in method_names:
            close_method = getattr(resource, method_name, None)
            if close_method is not None:
                try:
                    result = close_method()
                    if hasattr(result, "__await__"):
                        await result
                    return True
                except Exception as e:
                    log_backend_activity(
                        "gemini",
                        f"{resource_label} cleanup failed",
                        {"error": str(e), "method": method_name},
                        agent_id=self.agent_id,
                    )
                    return False
        return False

    async def _cleanup_genai_resources(self, stream, client) -> None:
        """Cleanup google-genai resources to avoid unclosed aiohttp sessions.

        Cleanup order is critical: stream → session → transport → client.
        Each resource is cleaned independently with error isolation.
        """
        # 1. Close stream
        await self._try_close_resource(stream, ("aclose", "close"), "Stream")

        # 2. Close internal aiohttp session (requires special handling)
        if client is not None:
            base_client = getattr(client, "_api_client", None)
            if base_client is not None:
                session = getattr(base_client, "_aiohttp_session", None)
                if session is not None and not getattr(session, "closed", True):
                    try:
                        await session.close()
                        log_backend_activity(
                            "gemini",
                            "Closed google-genai aiohttp session",
                            {},
                            agent_id=self.agent_id,
                        )
                        base_client._aiohttp_session = None
                        # Yield control to allow connector cleanup
                        await asyncio.sleep(0)
                    except Exception as e:
                        log_backend_activity(
                            "gemini",
                            "Failed to close google-genai aiohttp session",
                            {"error": str(e)},
                            agent_id=self.agent_id,
                        )

        # 3. Close internal async transport
        if client is not None:
            aio_obj = getattr(client, "aio", None)
            await self._try_close_resource(aio_obj, ("close", "stop"), "Client AIO")

        # 4. Close client
        await self._try_close_resource(client, ("aclose", "close"), "Client")

    def _append_tool_result_message(
        self,
        updated_messages: List[Dict[str, Any]],
        call: Dict[str, Any],
        result: Any,
        tool_type: str,
    ) -> None:
        """Append tool result to messages in Gemini conversation format.

        Gemini uses a different message format than OpenAI/Response API.
        We need to append messages in a format that Gemini SDK can understand
        when making recursive calls.

        Args:
            updated_messages: Message list to append to
            call: Tool call dictionary with call_id, name, arguments
            result: Tool execution result
            tool_type: "custom" or "mcp"
        """
        tool_result_msg = {
            "role": "tool",
            "name": call.get("name", ""),
            "content": str(result),
        }
        updated_messages.append(tool_result_msg)

        tool_results_store = getattr(self, "_active_tool_result_store", None)
        call_id = call.get("call_id")
        if isinstance(tool_results_store, dict) and call_id:
            tool_results_store[call_id] = str(result)

    def _append_tool_error_message(
        self,
        updated_messages: List[Dict[str, Any]],
        call: Dict[str, Any],
        error_msg: str,
        tool_type: str,
    ) -> None:
        """Append tool error to messages in Gemini conversation format.

        Args:
            updated_messages: Message list to append to
            call: Tool call dictionary with call_id, name, arguments
            error_msg: Error message string
            tool_type: "custom" or "mcp"
        """
        # Append error as function result
        error_result_msg = {
            "role": "tool",
            "name": call.get("name", ""),
            "content": f"Error: {error_msg}",
        }
        updated_messages.append(error_result_msg)

        tool_results_store = getattr(self, "_active_tool_result_store", None)
        call_id = call.get("call_id")
        if isinstance(tool_results_store, dict) and call_id:
            tool_results_store[call_id] = f"Error: {error_msg}"

    async def _execute_custom_tool(self, call: Dict[str, Any]) -> AsyncGenerator[CustomToolChunk, None]:
        """Execute custom tool with streaming support - async generator for base class.

        This method is called by _execute_tool_with_logging and yields CustomToolChunk
        objects for intermediate streaming output. The base class detects the async
        generator and streams intermediate results to users in real-time.

        Args:
            call: Tool call dictionary with name and arguments

        Yields:
            CustomToolChunk objects with streaming data

        Note:
            - Intermediate chunks (completed=False) are streamed to users in real-time
            - Final chunk (completed=True) contains the accumulated result for message history
            - The base class automatically handles extracting and displaying intermediate chunks
        """
        async for chunk in self.stream_custom_tool_execution(call):
            yield chunk

    def get_provider_name(self) -> str:
        """Get the provider name."""
        return "Gemini"

    def get_filesystem_support(self) -> FilesystemSupport:
        """Gemini supports filesystem through MCP servers."""
        return FilesystemSupport.MCP

    def get_supported_builtin_tools(self) -> List[str]:
        """Get list of builtin tools supported by Gemini."""
        return ["google_search_retrieval", "code_execution"]

    def reset_tool_usage(self):
        """Reset tool usage tracking."""
        self.search_count = 0
        self.code_execution_count = 0
        # Reset MCP monitoring metrics when available
        for attr in (
            "_mcp_tool_calls_count",
            "_mcp_tool_failures",
            "_mcp_tool_successes",
            "_mcp_connection_retries",
        ):
            if hasattr(self, attr):
                setattr(self, attr, 0)
        super().reset_token_usage()

    async def cleanup_mcp(self):
        """Cleanup MCP connections - override parent class to use Gemini-specific cleanup."""
        if MCPResourceManager:
            try:
                await super().cleanup_mcp()
                return
            except Exception as error:
                log_backend_activity(
                    "gemini",
                    "MCP cleanup via resource manager failed",
                    {"error": str(error)},
                    agent_id=self.agent_id,
                )
                # Fall back to manual cleanup below

        if not self._mcp_client:
            return

        try:
            await self._mcp_client.disconnect()
            log_backend_activity("gemini", "MCP client disconnected", {}, agent_id=self.agent_id)
        except (
            MCPConnectionError,
            MCPTimeoutError,
            MCPServerError,
            MCPError,
            Exception,
        ) as e:
            if MCPErrorHandler:
                MCPErrorHandler.get_error_details(e, "disconnect", log=True)
            else:
                logger.exception("[Gemini] MCP disconnect error during cleanup")
        finally:
            self._mcp_client = None
            self._mcp_initialized = False
            if hasattr(self, "_mcp_functions"):
                self._mcp_functions.clear()
            if hasattr(self, "_mcp_function_names"):
                self._mcp_function_names.clear()

    async def __aenter__(self) -> "GeminiBackend":
        """Async context manager entry."""
        # Call parent class __aenter__ which handles MCP setup
        await super().__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[object],
    ) -> None:
        """Async context manager exit with automatic resource cleanup."""
        # Parameters are required by context manager protocol but not used
        _ = (exc_type, exc_val, exc_tb)
        try:
            await super().__aexit__(exc_type, exc_val, exc_tb)
        finally:
            if not MCPResourceManager:
                try:
                    await self.cleanup_mcp()
                except Exception as e:
                    log_backend_activity(
                        "gemini",
                        "Backend cleanup error",
                        {"error": str(e)},
                        agent_id=self.agent_id,
                    )
