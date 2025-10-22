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
import enum
import hashlib
import json
import os
import re
import time
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, List, Optional

from ..logger_config import (
    log_backend_activity,
    log_backend_agent_message,
    log_stream_chunk,
    log_tool_call,
    logger,
)
from .base import FilesystemSupport, LLMBackend, StreamChunk

try:
    from pydantic import BaseModel, Field
except ImportError:
    BaseModel = None
    Field = None

# MCP integration imports
try:
    from ..mcp_tools import MCPClient, MCPConnectionError, MCPError
    from ..mcp_tools.config_validator import MCPConfigValidator
    from ..mcp_tools.exceptions import (
        MCPConfigurationError,
        MCPServerError,
        MCPTimeoutError,
        MCPValidationError,
    )
except ImportError:  # MCP not installed or import failed within mcp_tools
    MCPClient = None  # type: ignore[assignment]
    MCPError = ImportError  # type: ignore[assignment]
    MCPConnectionError = ImportError  # type: ignore[assignment]
    MCPConfigValidator = None  # type: ignore[assignment]
    MCPConfigurationError = ImportError  # type: ignore[assignment]
    MCPValidationError = ImportError  # type: ignore[assignment]
    MCPTimeoutError = ImportError  # type: ignore[assignment]
    MCPServerError = ImportError  # type: ignore[assignment]

# Import MCP backend utilities
try:
    from ..mcp_tools.backend_utils import (
        MCPCircuitBreakerManager,
        MCPConfigHelper,
        MCPErrorHandler,
        MCPExecutionManager,
        MCPMessageManager,
        MCPSetupManager,
    )
except ImportError:
    MCPErrorHandler = None  # type: ignore[assignment]
    MCPSetupManager = None  # type: ignore[assignment]
    MCPMessageManager = None  # type: ignore[assignment]
    MCPCircuitBreakerManager = None  # type: ignore[assignment]
    MCPExecutionManager = None  # type: ignore[assignment]
    MCPConfigHelper = None  # type: ignore[assignment]


class ActionType(enum.Enum):
    """Action types for structured output."""

    VOTE = "vote"
    NEW_ANSWER = "new_answer"


class VoteAction(BaseModel):
    """Structured output for voting action."""

    action: ActionType = Field(default=ActionType.VOTE, description="Action type")
    agent_id: str = Field(description="Anonymous agent ID to vote for (e.g., 'agent1', 'agent2')")
    reason: str = Field(description="Brief reason why this agent has the best answer")


class NewAnswerAction(BaseModel):
    """Structured output for new answer action."""

    action: ActionType = Field(default=ActionType.NEW_ANSWER, description="Action type")
    content: str = Field(description="Your improved answer. If any builtin tools like search or code execution were used, include how they are used here.")


class CoordinationResponse(BaseModel):
    """Structured response for coordination actions."""

    action_type: ActionType = Field(description="Type of action to take")
    vote_data: Optional[VoteAction] = Field(default=None, description="Vote data if action is vote")
    answer_data: Optional[NewAnswerAction] = Field(default=None, description="Answer data if action is new_answer")


class MCPResponseTracker:
    """
    Tracks MCP tool responses across streaming chunks to handle deduplication.

    Similar to MCPCallTracker but for tracking tool responses to avoid duplicate output.
    """

    def __init__(self):
        """Initialize the tracker with empty storage."""
        self.processed_responses = set()  # Store hashes of processed responses
        self.response_history = []  # Store all unique responses with timestamps

    def get_response_hash(self, tool_name: str, tool_response: Any) -> str:
        """
        Generate a unique hash for a tool response based on name and response content.

        Args:
            tool_name: Name of the tool that responded
            tool_response: Response from the tool

        Returns:
            MD5 hash string identifying this specific response
        """
        # Create a deterministic string representation
        content = f"{tool_name}:{str(tool_response)}"
        return hashlib.md5(content.encode()).hexdigest()

    def is_new_response(self, tool_name: str, tool_response: Any) -> bool:
        """
        Check if this is a new tool response we haven't seen before.

        Args:
            tool_name: Name of the tool that responded
            tool_response: Response from the tool

        Returns:
            True if this is a new response, False if already processed
        """
        response_hash = self.get_response_hash(tool_name, tool_response)
        return response_hash not in self.processed_responses

    def add_response(self, tool_name: str, tool_response: Any) -> Dict[str, Any]:
        """
        Add a new response to the tracker.

        Args:
            tool_name: Name of the tool that responded
            tool_response: Response from the tool

        Returns:
            Dictionary containing response details and timestamp
        """
        response_hash = self.get_response_hash(tool_name, tool_response)
        self.processed_responses.add(response_hash)

        record = {
            "tool_name": tool_name,
            "response": tool_response,
            "hash": response_hash,
            "timestamp": time.time(),
        }
        self.response_history.append(record)
        return record


class MCPCallTracker:
    """
    Tracks MCP tool calls across streaming chunks to handle deduplication.

    Uses hashing to identify unique tool calls and timestamps to track when they occurred.
    This ensures we don't double-count the same tool call appearing in multiple chunks.
    """

    def __init__(self):
        """Initialize the tracker with empty storage."""
        self.processed_calls = set()  # Store hashes of processed calls
        self.call_history = []  # Store all unique calls with timestamps
        self.last_chunk_calls = []  # Track calls from the last chunk for deduplication
        self.dedup_window = 0.5  # Time window in seconds for deduplication

    def get_call_hash(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        """
        Generate a unique hash for a tool call based on name and arguments.

        Args:
            tool_name: Name of the tool being called
            tool_args: Arguments passed to the tool

        Returns:
            MD5 hash string identifying this specific call
        """
        # Create a deterministic string representation
        content = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
        return hashlib.md5(content.encode()).hexdigest()

    def is_new_call(self, tool_name: str, tool_args: Dict[str, Any]) -> bool:
        """
        Check if this is a new tool call we haven't seen before.

        Uses a time-window based approach: identical calls within the dedup_window
        are considered duplicates (likely from streaming chunks), while those outside
        the window are considered new calls (likely intentional repeated calls).

        Args:
            tool_name: Name of the tool being called
            tool_args: Arguments passed to the tool

        Returns:
            True if this is a new call, False if we've seen it before
        """
        call_hash = self.get_call_hash(tool_name, tool_args)
        current_time = time.time()

        # Check if this call exists in recent history within the dedup window
        for call in self.call_history[-10:]:  # Check last 10 calls for efficiency
            if call.get("hash") == call_hash:
                time_diff = current_time - call.get("timestamp", 0)
                if time_diff < self.dedup_window:
                    # This is likely a duplicate from streaming chunks
                    return False
                # If outside the window, treat as a new intentional call

        # Mark as processed
        self.processed_calls.add(call_hash)
        return True

    def add_call(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add a new tool call to the history.

        Args:
            tool_name: Name of the tool being called
            tool_args: Arguments passed to the tool

        Returns:
            Dictionary containing the call details with timestamp and hash
        """
        call_record = {
            "name": tool_name,
            "arguments": tool_args,
            "timestamp": time.time(),
            "hash": self.get_call_hash(tool_name, tool_args),
            "sequence": len(self.call_history),  # Add sequence number for ordering
        }
        self.call_history.append(call_record)

        # Clean up old history to prevent memory growth
        if len(self.call_history) > 100:
            self.call_history = self.call_history[-50:]

        return call_record

    def get_summary(self) -> str:
        """
        Get a summary of all tracked tool calls.

        Returns:
            Human-readable summary of tool usage
        """
        if not self.call_history:
            return "No MCP tools called"

        tool_names = [call["name"] for call in self.call_history]
        unique_tools = list(dict.fromkeys(tool_names))  # Preserve order
        return f"Used {len(self.call_history)} MCP tool calls: {', '.join(unique_tools)}"


class MCPResponseExtractor:
    """
    Extracts MCP tool calls and responses from Gemini SDK stream chunks.

    This class parses the internal SDK chunks to capture:
    - function_call parts (tool invocations)
    - function_response parts (tool results)
    - Paired call-response data for tracking complete tool executions
    """

    def __init__(self):
        """Initialize the extractor with empty storage."""
        self.mcp_calls = []  # All tool calls
        self.mcp_responses = []  # All tool responses
        self.call_response_pairs = []  # Matched call-response pairs
        self._pending_call = None  # Track current call awaiting response

    def extract_function_call(self, function_call) -> Optional[Dict[str, Any]]:
        """
        Extract tool call information from SDK function_call object.

        Tries multiple methods to extract data from different SDK versions:
        1. Direct attributes (name, args)
        2. Dictionary-like interface (get method)
        3. __dict__ attributes
        4. Protobuf _pb attributes
        """
        tool_name = None
        tool_args = None

        # Method 1: Direct attributes
        tool_name = getattr(function_call, "name", None)
        tool_args = getattr(function_call, "args", None)

        # Method 2: Dictionary-like object
        if tool_name is None:
            try:
                if hasattr(function_call, "get"):
                    tool_name = function_call.get("name", None)
                    tool_args = function_call.get("args", None)
            except Exception:
                pass

        # Method 3: __dict__ inspection
        if tool_name is None:
            try:
                if hasattr(function_call, "__dict__"):
                    fc_dict = function_call.__dict__
                    tool_name = fc_dict.get("name", None)
                    tool_args = fc_dict.get("args", None)
            except Exception:
                pass

        # Method 4: Protobuf _pb attribute
        if tool_name is None:
            try:
                if hasattr(function_call, "_pb"):
                    pb = function_call._pb
                    if hasattr(pb, "name"):
                        tool_name = pb.name
                    if hasattr(pb, "args"):
                        tool_args = pb.args
            except Exception:
                pass

        if tool_name:
            call_data = {
                "name": tool_name,
                "arguments": tool_args or {},
                "timestamp": time.time(),
                "raw": str(function_call)[:200],  # Truncate for logging
            }
            self.mcp_calls.append(call_data)
            self._pending_call = call_data
            return call_data

        return None

    def extract_function_response(self, function_response) -> Optional[Dict[str, Any]]:
        """
        Extract tool response information from SDK function_response object.

        Uses same extraction methods as function_call for consistency.
        """
        tool_name = None
        tool_response = None

        # Method 1: Direct attributes
        tool_name = getattr(function_response, "name", None)
        tool_response = getattr(function_response, "response", None)

        # Method 2: Dictionary-like object
        if tool_name is None:
            try:
                if hasattr(function_response, "get"):
                    tool_name = function_response.get("name", None)
                    tool_response = function_response.get("response", None)
            except Exception:
                pass

        # Method 3: __dict__ inspection
        if tool_name is None:
            try:
                if hasattr(function_response, "__dict__"):
                    fr_dict = function_response.__dict__
                    tool_name = fr_dict.get("name", None)
                    tool_response = fr_dict.get("response", None)
            except Exception:
                pass

        # Method 4: Protobuf _pb attribute
        if tool_name is None:
            try:
                if hasattr(function_response, "_pb"):
                    pb = function_response._pb
                    if hasattr(pb, "name"):
                        tool_name = pb.name
                    if hasattr(pb, "response"):
                        tool_response = pb.response
            except Exception:
                pass

        if tool_name:
            response_data = {
                "name": tool_name,
                "response": tool_response or {},
                "timestamp": time.time(),
                "raw": str(function_response)[:500],  # Truncate for logging
            }
            self.mcp_responses.append(response_data)

            # Pair with pending call if names match
            if self._pending_call and self._pending_call["name"] == tool_name:
                self.call_response_pairs.append(
                    {
                        "call": self._pending_call,
                        "response": response_data,
                        "duration": response_data["timestamp"] - self._pending_call["timestamp"],
                        "paired_at": time.time(),
                    },
                )
                self._pending_call = None

            return response_data

        return None

    def get_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all extracted MCP tool interactions.
        """
        return {
            "total_calls": len(self.mcp_calls),
            "total_responses": len(self.mcp_responses),
            "paired_interactions": len(self.call_response_pairs),
            "pending_call": self._pending_call is not None,
            "tool_names": list(set(call["name"] for call in self.mcp_calls)),
            "average_duration": (sum(pair["duration"] for pair in self.call_response_pairs) / len(self.call_response_pairs) if self.call_response_pairs else 0),
        }

    def clear(self):
        """Clear all stored data."""
        self.mcp_calls.clear()
        self.mcp_responses.clear()
        self.call_response_pairs.clear()
        self._pending_call = None


class GeminiBackend(LLMBackend):
    """Google Gemini backend using structured output for coordination and MCP tool integration."""

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(api_key, **kwargs)
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        self.search_count = 0
        self.code_execution_count = 0

        # MCP integration (filesystem MCP server may have been injected by base class)
        self.mcp_servers = self.config.get("mcp_servers", [])
        self.allowed_tools = kwargs.pop("allowed_tools", None)
        self.exclude_tools = kwargs.pop("exclude_tools", None)
        self._mcp_client: Optional[MCPClient] = None
        self._mcp_initialized = False

        # MCP tool execution monitoring
        self._mcp_tool_calls_count = 0
        self._mcp_tool_failures = 0
        self._mcp_tool_successes = 0

        # MCP Response Extractor for capturing tool interactions
        self.mcp_extractor = MCPResponseExtractor()

        # Limit for message history growth within MCP execution loop
        self._max_mcp_message_history = kwargs.pop("max_mcp_message_history", 200)
        self._mcp_connection_retries = 0

        # Circuit breaker configuration
        self._circuit_breakers_enabled = kwargs.pop("circuit_breaker_enabled", True)
        self._mcp_tools_circuit_breaker = None

        # Initialize agent_id for use throughout the class
        self.agent_id = kwargs.get("agent_id", None)

        # Initialize circuit breaker if enabled
        if self._circuit_breakers_enabled:
            # Fail fast if required utilities are missing
            if MCPCircuitBreakerManager is None:
                raise RuntimeError("Circuit breakers enabled but MCPCircuitBreakerManager is not available")

            try:
                from ..mcp_tools.circuit_breaker import MCPCircuitBreaker

                # Use shared utility to build circuit breaker configuration
                if MCPConfigHelper is not None:
                    mcp_tools_config = MCPConfigHelper.build_circuit_breaker_config("mcp_tools", backend_name="gemini")
                else:
                    mcp_tools_config = None
                if mcp_tools_config:
                    self._mcp_tools_circuit_breaker = MCPCircuitBreaker(mcp_tools_config, backend_name="gemini", agent_id=self.agent_id)
                    log_backend_activity(
                        "gemini",
                        "Circuit breaker initialized for MCP tools",
                        {"enabled": True},
                        agent_id=self.agent_id,
                    )
                else:
                    log_backend_activity(
                        "gemini",
                        "Circuit breaker config unavailable",
                        {"fallback": "disabled"},
                        agent_id=self.agent_id,
                    )
                    self._circuit_breakers_enabled = False
            except ImportError:
                log_backend_activity(
                    "gemini",
                    "Circuit breaker import failed",
                    {"fallback": "disabled"},
                    agent_id=self.agent_id,
                )
                self._circuit_breakers_enabled = False

    def _setup_permission_hooks(self):
        """Override base class - Gemini uses session-based permissions, not function hooks."""
        logger.debug("[Gemini] Using session-based permissions, skipping function hook setup")

    async def _setup_mcp_with_status_stream(self, agent_id: Optional[str] = None) -> AsyncGenerator[StreamChunk, None]:
        """Initialize MCP client with status streaming."""
        status_queue: asyncio.Queue[StreamChunk] = asyncio.Queue()

        async def status_callback(status: str, details: Dict[str, Any]) -> None:
            """Callback to queue status updates as StreamChunks."""
            chunk = StreamChunk(
                type="mcp_status",
                status=status,
                content=details.get("message", ""),
                source="mcp_tools",
            )
            await status_queue.put(chunk)

        # Start the actual setup in background
        setup_task = asyncio.create_task(self._setup_mcp_tools_internal(agent_id, status_callback))

        # Yield status updates while setup is running
        while not setup_task.done():
            try:
                chunk = await asyncio.wait_for(status_queue.get(), timeout=0.1)
                yield chunk
            except asyncio.TimeoutError:
                continue

        # Wait for setup to complete and handle any final errors
        try:
            await setup_task
        except Exception as e:
            yield StreamChunk(
                type="mcp_status",
                status="error",
                content=f"MCP setup failed: {e}",
                source="mcp_tools",
            )

    async def _setup_mcp_tools(self, agent_id: Optional[str] = None) -> None:
        """Initialize MCP client (sessions only) - backward compatibility."""
        if not self.mcp_servers or self._mcp_initialized:
            return
        # Consume status updates without yielding them
        async for _ in self._setup_mcp_with_status_stream(agent_id):
            pass

    async def _setup_mcp_tools_internal(
        self,
        agent_id: Optional[str] = None,
        status_callback: Optional[Callable[[str, Dict[str, Any]], Awaitable[None]]] = None,
    ) -> None:
        """Internal MCP setup logic."""
        if not self.mcp_servers or self._mcp_initialized:
            return

        if MCPClient is None:
            reason = "MCP import failed - MCPClient not available"
            log_backend_activity(
                "gemini",
                "MCP import failed",
                {"reason": reason, "fallback": "workflow_tools"},
                agent_id=agent_id,
            )
            if status_callback:
                await status_callback(
                    "error",
                    {"message": "MCP import failed - falling back to workflow tools"},
                )
            # Clear MCP servers to prevent further attempts
            self.mcp_servers = []
            return

        try:
            # Validate MCP configuration before initialization
            validated_config = {
                "mcp_servers": self.mcp_servers,
                "allowed_tools": self.allowed_tools,
                "exclude_tools": self.exclude_tools,
            }

            if MCPConfigValidator is not None:
                try:
                    backend_config = {
                        "mcp_servers": self.mcp_servers,
                        "allowed_tools": self.allowed_tools,
                        "exclude_tools": self.exclude_tools,
                    }
                    # Use the comprehensive validator class for enhanced validation
                    validator = MCPConfigValidator()
                    validated_config = validator.validate_backend_mcp_config(backend_config)
                    self.mcp_servers = validated_config.get("mcp_servers", self.mcp_servers)
                    log_backend_activity(
                        "gemini",
                        "MCP configuration validated",
                        {"server_count": len(self.mcp_servers)},
                        agent_id=agent_id,
                    )
                    if status_callback:
                        await status_callback(
                            "info",
                            {"message": f"MCP configuration validated: {len(self.mcp_servers)} servers"},
                        )

                    # Log validated server names for debugging
                    if True:
                        server_names = [server.get("name", "unnamed") for server in self.mcp_servers]
                        log_backend_activity(
                            "gemini",
                            "MCP servers validated",
                            {"servers": server_names},
                            agent_id=agent_id,
                        )
                except MCPConfigurationError as e:
                    log_backend_activity(
                        "gemini",
                        "MCP configuration validation failed",
                        {"error": e.original_message},
                        agent_id=agent_id,
                    )
                    if status_callback:
                        await status_callback(
                            "error",
                            {"message": f"Invalid MCP configuration: {e.original_message}"},
                        )
                    self._mcp_client = None  # Clear client state for consistency
                    raise RuntimeError(f"Invalid MCP configuration: {e.original_message}") from e
                except MCPValidationError as e:
                    log_backend_activity(
                        "gemini",
                        "MCP validation failed",
                        {"error": e.original_message},
                        agent_id=agent_id,
                    )
                    if status_callback:
                        await status_callback(
                            "error",
                            {"message": f"MCP validation error: {e.original_message}"},
                        )
                    self._mcp_client = None  # Clear client state for consistency
                    raise RuntimeError(f"MCP validation error: {e.original_message}") from e
                except Exception as e:
                    if isinstance(e, (ImportError, AttributeError)):
                        log_backend_activity(
                            "gemini",
                            "MCP validation unavailable",
                            {"reason": str(e)},
                            agent_id=agent_id,
                        )
                        # Don't clear client for import errors - validation just unavailable
                    else:
                        log_backend_activity(
                            "gemini",
                            "MCP validation error",
                            {"error": str(e)},
                            agent_id=agent_id,
                        )
                        self._mcp_client = None  # Clear client state for consistency
                        raise RuntimeError(f"MCP configuration validation failed: {e}") from e
            else:
                log_backend_activity(
                    "gemini",
                    "MCP validation skipped",
                    {"reason": "validator_unavailable"},
                    agent_id=agent_id,
                )

            # Instead of the current fallback logic
            normalized_servers = MCPSetupManager.normalize_mcp_servers(self.mcp_servers)
            log_backend_activity(
                "gemini",
                "Setting up MCP sessions",
                {"server_count": len(normalized_servers)},
                agent_id=agent_id,
            )
            if status_callback:
                await status_callback(
                    "info",
                    {"message": f"Setting up MCP sessions for {len(normalized_servers)} servers"},
                )

            # Apply circuit breaker filtering before connection attempts
            if self._circuit_breakers_enabled and self._mcp_tools_circuit_breaker:
                filtered_servers = MCPCircuitBreakerManager.apply_circuit_breaker_filtering(
                    normalized_servers,
                    self._mcp_tools_circuit_breaker,
                    backend_name="gemini",
                    agent_id=agent_id,
                )
            else:
                filtered_servers = normalized_servers
            if not filtered_servers:
                log_backend_activity(
                    "gemini",
                    "All MCP servers blocked by circuit breaker",
                    {},
                    agent_id=agent_id,
                )
                if status_callback:
                    await status_callback(
                        "warning",
                        {"message": "All MCP servers blocked by circuit breaker"},
                    )
                return

            if len(filtered_servers) < len(normalized_servers):
                log_backend_activity(
                    "gemini",
                    "Circuit breaker filtered servers",
                    {"filtered_count": len(normalized_servers) - len(filtered_servers)},
                    agent_id=agent_id,
                )
                if status_callback:
                    await status_callback(
                        "warning",
                        {"message": f"Circuit breaker filtered {len(normalized_servers) - len(filtered_servers)} servers"},
                    )

            # Extract tool filtering parameters from validated config
            allowed_tools = validated_config.get("allowed_tools")
            exclude_tools = validated_config.get("exclude_tools")

            # Log tool filtering if configured
            if allowed_tools:
                log_backend_activity(
                    "gemini",
                    "MCP tool filtering configured",
                    {"allowed_tools": allowed_tools},
                    agent_id=agent_id,
                )
            if exclude_tools:
                log_backend_activity(
                    "gemini",
                    "MCP tool filtering configured",
                    {"exclude_tools": exclude_tools},
                    agent_id=agent_id,
                )

            # Create client with status callback and hooks
            self._mcp_client = MCPClient(
                filtered_servers,
                timeout_seconds=30,
                allowed_tools=allowed_tools,
                exclude_tools=exclude_tools,
                status_callback=status_callback,
                hooks=self.filesystem_manager.get_pre_tool_hooks() if self.filesystem_manager else {},
            )

            # Connect the client
            await self._mcp_client.connect()

            # Determine which servers actually connected
            try:
                connected_server_names = self._mcp_client.get_server_names()
            except Exception:
                connected_server_names = []

            if not connected_server_names:
                # Treat as connection failure: no active servers
                if self._circuit_breakers_enabled and self._mcp_tools_circuit_breaker:
                    await MCPCircuitBreakerManager.record_event(
                        filtered_servers,
                        self._mcp_tools_circuit_breaker,
                        "failure",
                        error_message="No servers connected",
                        backend_name="gemini",
                        agent_id=agent_id,
                    )

                log_backend_activity(
                    "gemini",
                    "MCP connection failed: no servers connected",
                    {},
                    agent_id=agent_id,
                )
                if status_callback:
                    await status_callback(
                        "error",
                        {"message": "MCP connection failed: no servers connected"},
                    )
                self._mcp_client = None
                return

            # Record success ONLY for servers that actually connected
            connected_server_configs = [server for server in filtered_servers if server.get("name") in connected_server_names]
            if connected_server_configs:
                if self._circuit_breakers_enabled and self._mcp_tools_circuit_breaker:
                    await MCPCircuitBreakerManager.record_event(
                        connected_server_configs,
                        self._mcp_tools_circuit_breaker,
                        "success",
                        backend_name="gemini",
                        agent_id=agent_id,
                    )

            self._mcp_initialized = True
            log_backend_activity("gemini", "MCP sessions initialized successfully", {}, agent_id=agent_id)
            if status_callback:
                await status_callback(
                    "success",
                    {"message": f"MCP sessions initialized successfully with {len(connected_server_names)} servers"},
                )

        except Exception as e:
            # Record failure for circuit breaker
            if self._circuit_breakers_enabled and self._mcp_tools_circuit_breaker:
                servers = MCPSetupManager.normalize_mcp_servers(self.mcp_servers)
                await MCPCircuitBreakerManager.record_event(
                    servers,
                    self._mcp_tools_circuit_breaker,
                    "failure",
                    error_message=str(e),
                    backend_name="gemini",
                    agent_id=agent_id,
                )

            # Enhanced error handling for different MCP error types
            if isinstance(e, RuntimeError) and "MCP configuration" in str(e):
                raise
            elif isinstance(e, MCPConnectionError):
                log_backend_activity(
                    "gemini",
                    "MCP connection failed during setup",
                    {"error": str(e)},
                    agent_id=agent_id,
                )
                if status_callback:
                    await status_callback(
                        "error",
                        {"message": f"Failed to establish MCP connections: {e}"},
                    )
                self._mcp_client = None
                raise RuntimeError(f"Failed to establish MCP connections: {e}") from e
            elif isinstance(e, MCPTimeoutError):
                log_backend_activity(
                    "gemini",
                    "MCP connection timeout during setup",
                    {"error": str(e)},
                    agent_id=agent_id,
                )
                if status_callback:
                    await status_callback("error", {"message": f"MCP connection timeout: {e}"})
                self._mcp_client = None
                raise RuntimeError(f"MCP connection timeout: {e}") from e
            elif isinstance(e, MCPServerError):
                log_backend_activity(
                    "gemini",
                    "MCP server error during setup",
                    {"error": str(e)},
                    agent_id=agent_id,
                )
                if status_callback:
                    await status_callback("error", {"message": f"MCP server error: {e}"})
                self._mcp_client = None
                raise RuntimeError(f"MCP server error: {e}") from e
            elif isinstance(e, MCPError):
                log_backend_activity(
                    "gemini",
                    "MCP error during setup",
                    {"error": str(e)},
                    agent_id=agent_id,
                )
                if status_callback:
                    await status_callback("error", {"message": f"MCP error during setup: {e}"})
                self._mcp_client = None
                return

            else:
                log_backend_activity(
                    "gemini",
                    "MCP session setup failed",
                    {"error": str(e)},
                    agent_id=agent_id,
                )
                if status_callback:
                    await status_callback("error", {"message": f"MCP session setup failed: {e}"})
                self._mcp_client = None

    def detect_coordination_tools(self, tools: List[Dict[str, Any]]) -> bool:
        """Detect if tools contain vote/new_answer coordination tools."""
        if not tools:
            return False

        tool_names = set()
        for tool in tools:
            if tool.get("type") == "function":
                if "function" in tool:
                    tool_names.add(tool["function"].get("name", ""))
                elif "name" in tool:
                    tool_names.add(tool.get("name", ""))

        return "vote" in tool_names and "new_answer" in tool_names

    def build_structured_output_prompt(self, base_content: str, valid_agent_ids: Optional[List[str]] = None) -> str:
        """Build prompt that encourages structured output for coordination."""
        agent_list = ""
        if valid_agent_ids:
            agent_list = f"Valid agents: {', '.join(valid_agent_ids)}"

        return f"""{base_content}

IMPORTANT: You must respond with a structured JSON decision at the end of your response.

If you want to VOTE for an existing agent's answer:
{{
  "action_type": "vote",
  "vote_data": {{
    "action": "vote",
    "agent_id": "agent1",  // Choose from: {agent_list or "agent1, agent2, agent3, etc."}
    "reason": "Brief reason for your vote"
  }}
}}

If you want to provide a NEW ANSWER:
{{
  "action_type": "new_answer",
  "answer_data": {{
    "action": "new_answer",
    "content": "Your complete improved answer here"
  }}
}}

Make your decision and include the JSON at the very end of your response."""

    def extract_structured_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Extract structured JSON response from model output."""
        try:
            # Strategy 0: Look for JSON inside markdown code blocks first
            markdown_json_pattern = r"```json\s*(\{.*?\})\s*```"
            markdown_matches = re.findall(markdown_json_pattern, response_text, re.DOTALL)

            for match in reversed(markdown_matches):
                try:
                    parsed = json.loads(match.strip())
                    if isinstance(parsed, dict) and "action_type" in parsed:
                        return parsed
                except json.JSONDecodeError:
                    continue

            # Strategy 1: Look for complete JSON blocks with proper braces
            json_pattern = r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"
            json_matches = re.findall(json_pattern, response_text, re.DOTALL)

            # Try parsing each match (in reverse order - last one first)
            for match in reversed(json_matches):
                try:
                    cleaned_match = match.strip()
                    parsed = json.loads(cleaned_match)
                    if isinstance(parsed, dict) and "action_type" in parsed:
                        return parsed
                except json.JSONDecodeError:
                    continue

            # Strategy 2: Look for JSON blocks with nested braces (more complex)
            brace_count = 0
            json_start = -1

            for i, char in enumerate(response_text):
                if char == "{":
                    if brace_count == 0:
                        json_start = i
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0 and json_start >= 0:
                        # Found a complete JSON block
                        json_block = response_text[json_start : i + 1]
                        try:
                            parsed = json.loads(json_block)
                            if isinstance(parsed, dict) and "action_type" in parsed:
                                return parsed
                        except json.JSONDecodeError:
                            pass
                        json_start = -1

            # Strategy 3: Line-by-line approach (fallback)
            lines = response_text.strip().split("\n")
            json_candidates = []

            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("{") and stripped.endswith("}"):
                    json_candidates.append(stripped)
                elif stripped.startswith("{"):
                    # Multi-line JSON - collect until closing brace
                    json_text = stripped
                    for j in range(i + 1, len(lines)):
                        json_text += "\n" + lines[j].strip()
                        if lines[j].strip().endswith("}"):
                            json_candidates.append(json_text)
                            break

            # Try to parse each candidate
            for candidate in reversed(json_candidates):
                try:
                    parsed = json.loads(candidate)
                    if isinstance(parsed, dict) and "action_type" in parsed:
                        return parsed
                except json.JSONDecodeError:
                    continue

            return None

        except Exception:
            return None

    def convert_structured_to_tool_calls(self, structured_response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert structured response to tool call format."""
        action_type = structured_response.get("action_type")

        if action_type == "vote":
            vote_data = structured_response.get("vote_data", {})
            return [
                {
                    "id": f"vote_{abs(hash(str(vote_data))) % 10000 + 1}",
                    "type": "function",
                    "function": {
                        "name": "vote",
                        "arguments": {
                            "agent_id": vote_data.get("agent_id", ""),
                            "reason": vote_data.get("reason", ""),
                        },
                    },
                },
            ]

        elif action_type == "new_answer":
            answer_data = structured_response.get("answer_data", {})
            return [
                {
                    "id": f"new_answer_{abs(hash(str(answer_data))) % 10000 + 1}",
                    "type": "function",
                    "function": {
                        "name": "new_answer",
                        "arguments": {"content": answer_data.get("content", "")},
                    },
                },
            ]

        return []

    async def _handle_mcp_retry_error(self, error: Exception, retry_count: int, max_retries: int) -> tuple[bool, AsyncGenerator[StreamChunk, None]]:
        """Handle MCP retry errors with specific messaging and fallback logic.

        Returns:
            tuple: (should_continue_retrying, error_chunks_generator)
        """
        log_type, user_message, _ = MCPErrorHandler.get_error_details(error, None, log=False)

        # Log the retry attempt
        log_backend_activity(
            "gemini",
            f"MCP {log_type} on retry",
            {"attempt": retry_count, "error": str(error)},
            agent_id=self.agent_id,
        )

        # Check if we've exhausted retries
        if retry_count >= max_retries:

            async def error_chunks():
                yield StreamChunk(
                    type="content",
                    content=f"\n⚠️  {user_message} after {max_retries} attempts; falling back to workflow tools\n",
                )

            return False, error_chunks()

        # Continue retrying
        async def empty_chunks():
            # Empty generator - just return without yielding anything
            if False:  # Make this a generator without actually yielding
                yield

        return True, empty_chunks()

    async def _handle_mcp_error_and_fallback(
        self,
        error: Exception,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Handle MCP errors with specific messaging"""
        self._mcp_tool_failures += 1

        log_type, user_message, _ = MCPErrorHandler.get_error_details(error, None, log=False)

        # Log with specific error type
        log_backend_activity(
            "gemini",
            "MCP tool call failed",
            {
                "call_number": self._mcp_tool_calls_count,
                "error_type": log_type,
                "error": str(error),
            },
            agent_id=self.agent_id,
        )

        # Yield user-friendly error message
        yield StreamChunk(
            type="content",
            content=f"\n⚠️  {user_message} ({error}); continuing without MCP tools\n",
        )

    async def _execute_mcp_function_with_retry(self, function_name: str, args: Dict[str, Any], agent_id: Optional[str] = None) -> Any:
        """Execute MCP function with exponential backoff retry logic."""
        if MCPExecutionManager is None:
            raise RuntimeError("MCPExecutionManager is not available - MCP backend utilities are missing")

        # Stats callback for tracking
        async def stats_callback(action: str) -> int:
            if action == "increment_calls":
                self._mcp_tool_calls_count += 1
                return self._mcp_tool_calls_count
            elif action == "increment_failures":
                self._mcp_tool_failures += 1
                return self._mcp_tool_failures
            return 0

        # Circuit breaker callback
        async def circuit_breaker_callback(event: str, error_msg: str) -> None:
            if event == "failure":
                if self._circuit_breakers_enabled and self._mcp_tools_circuit_breaker:
                    servers = MCPSetupManager.normalize_mcp_servers(self.mcp_servers)
                    await MCPCircuitBreakerManager.record_event(
                        servers,
                        self._mcp_tools_circuit_breaker,
                        "failure",
                        error_message=error_msg,
                        backend_name="gemini",
                        agent_id=agent_id,
                    )
            else:
                # Record success only for currently connected servers
                connected_names: List[str] = []
                try:
                    if self._mcp_client:
                        connected_names = self._mcp_client.get_server_names()
                except Exception:
                    connected_names = []

                if connected_names:
                    servers_to_record = [{"name": name} for name in connected_names]
                    if self._circuit_breakers_enabled and self._mcp_tools_circuit_breaker:
                        await MCPCircuitBreakerManager.record_event(
                            servers_to_record,
                            self._mcp_tools_circuit_breaker,
                            "success",
                            backend_name="gemini",
                            agent_id=agent_id,
                        )

        return await MCPExecutionManager.execute_function_with_retry(
            function_name=function_name,
            args=args,
            functions=self.functions,
            max_retries=3,
            stats_callback=stats_callback,
            circuit_breaker_callback=circuit_breaker_callback,
            logger_instance=logger,
        )

    async def stream_with_tools(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs) -> AsyncGenerator[StreamChunk, None]:
        """Stream response using Gemini API with structured output for coordination and MCP tool support."""
        # Use instance agent_id (from __init__) or get from kwargs if not set
        agent_id = self.agent_id or kwargs.get("agent_id", None)
        client = None
        stream = None

        log_backend_activity(
            "gemini",
            "Starting stream_with_tools",
            {"num_messages": len(messages), "num_tools": len(tools) if tools else 0},
            agent_id=agent_id,
        )

        # Only trim when MCP tools will be used
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

            # Setup MCP with status streaming if not already initialized
            if not self._mcp_initialized and self.mcp_servers:
                async for chunk in self._setup_mcp_with_status_stream(agent_id):
                    yield chunk
            elif not self._mcp_initialized:
                # Setup MCP without streaming for backward compatibility
                await self._setup_mcp_tools(agent_id)

            # Merge constructor config with stream kwargs (stream kwargs take priority)
            all_params = {**self.config, **kwargs}

            # Extract framework-specific parameters
            enable_web_search = all_params.get("enable_web_search", False)
            enable_code_execution = all_params.get("enable_code_execution", False)

            # Always use SDK MCP sessions when mcp_servers are configured
            using_sdk_mcp = bool(self.mcp_servers)

            # Analyze tool types
            is_coordination = self.detect_coordination_tools(tools)

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

            # Build content string from messages (include tool results for multi-turn tool calling)
            conversation_content = ""
            system_message = ""

            for msg in messages:
                role = msg.get("role")
                if role == "system":
                    system_message = msg.get("content", "")
                elif role == "user":
                    conversation_content += f"User: {msg.get('content', '')}\n"
                elif role == "assistant":
                    conversation_content += f"Assistant: {msg.get('content', '')}\n"
                elif role == "tool":
                    # Ensure tool outputs are visible to the model on the next turn
                    tool_output = msg.get("content", "")
                    conversation_content += f"Tool Result: {tool_output}\n"

            # For coordination requests, modify the prompt to use structured output
            if is_coordination:
                conversation_content = self.build_structured_output_prompt(conversation_content, valid_agent_ids)

            # Combine system message and conversation
            full_content = ""
            if system_message:
                full_content += f"{system_message}\n\n"
            full_content += conversation_content

            # Use google-genai package
            client = genai.Client(api_key=self.api_key)

            # Setup builtin tools (only when not using SDK MCP sessions)
            builtin_tools = []
            if enable_web_search:
                try:
                    from google.genai import types

                    grounding_tool = types.Tool(google_search=types.GoogleSearch())
                    builtin_tools.append(grounding_tool)
                except ImportError:
                    yield StreamChunk(
                        type="content",
                        content="\n⚠️  Web search requires google.genai.types\n",
                    )

            if enable_code_execution:
                try:
                    from google.genai import types

                    code_tool = types.Tool(code_execution=types.ToolCodeExecution())
                    builtin_tools.append(code_tool)
                except ImportError:
                    yield StreamChunk(
                        type="content",
                        content="\n⚠️  Code execution requires google.genai.types\n",
                    )

            # Build config with direct parameter passthrough
            config = {}

            # Direct passthrough of all parameters except those handled separately
            excluded_params = self.get_base_excluded_config_params() | {
                # Gemini specific exclusions
                "enable_web_search",
                "enable_code_execution",
                "use_multi_mcp",
                "mcp_sdk_auto",
                "allowed_tools",
                "exclude_tools",
            }
            for key, value in all_params.items():
                if key not in excluded_params and value is not None:
                    # Handle Gemini-specific parameter mappings
                    if key == "max_tokens":
                        config["max_output_tokens"] = value
                    elif key == "model":
                        model_name = value
                    else:
                        config[key] = value

            # Setup tools configuration (builtins only when not using sessions)
            all_tools = []

            # Branch 1: SDK auto-calling via MCP sessions (reuse existing MCPClient sessions)
            if using_sdk_mcp and self.mcp_servers:
                if not self._mcp_client or not getattr(self._mcp_client, "is_connected", lambda: False)():
                    # Retry MCP connection up to 5 times before falling back
                    max_mcp_retries = 5
                    mcp_connected = False

                    for retry_count in range(1, max_mcp_retries + 1):
                        try:
                            # Track retry attempts
                            self._mcp_connection_retries = retry_count

                            if retry_count > 1:
                                log_backend_activity(
                                    "gemini",
                                    "MCP connection retry",
                                    {
                                        "attempt": retry_count,
                                        "max_retries": max_mcp_retries,
                                    },
                                    agent_id=agent_id,
                                )
                                # Yield retry status
                                yield StreamChunk(
                                    type="mcp_status",
                                    status="mcp_retry",
                                    content=f"Retrying MCP connection (attempt {retry_count}/{max_mcp_retries})",
                                    source="mcp_tools",
                                )
                                # Brief delay between retries
                                await asyncio.sleep(0.5 * retry_count)  # Progressive backoff

                            # Apply circuit breaker filtering before retry attempts
                            if self._circuit_breakers_enabled and self._mcp_tools_circuit_breaker:
                                filtered_retry_servers = MCPCircuitBreakerManager.apply_circuit_breaker_filtering(
                                    self.mcp_servers,
                                    self._mcp_tools_circuit_breaker,
                                    backend_name="gemini",
                                    agent_id=agent_id,
                                )
                            else:
                                filtered_retry_servers = self.mcp_servers
                            if not filtered_retry_servers:
                                log_backend_activity(
                                    "gemini",
                                    "All MCP servers blocked during retry",
                                    {},
                                    agent_id=agent_id,
                                )
                                # Yield blocked status
                                yield StreamChunk(
                                    type="mcp_status",
                                    status="mcp_blocked",
                                    content="All MCP servers blocked by circuit breaker",
                                    source="mcp_tools",
                                )
                                using_sdk_mcp = False
                                break

                            # Get validated config for tool filtering parameters
                            backend_config = {"mcp_servers": self.mcp_servers}
                            if MCPConfigValidator is not None:
                                try:
                                    validator = MCPConfigValidator()
                                    validated_config_retry = validator.validate_backend_mcp_config(backend_config)
                                    allowed_tools_retry = validated_config_retry.get("allowed_tools")
                                    exclude_tools_retry = validated_config_retry.get("exclude_tools")
                                except Exception:
                                    allowed_tools_retry = None
                                    exclude_tools_retry = None
                            else:
                                allowed_tools_retry = None
                                exclude_tools_retry = None

                            self._mcp_client = await MCPClient.create_and_connect(
                                filtered_retry_servers,
                                timeout_seconds=30,
                                allowed_tools=allowed_tools_retry,
                                exclude_tools=exclude_tools_retry,
                            )

                            # Record success for circuit breaker
                            if self._circuit_breakers_enabled and self._mcp_tools_circuit_breaker:
                                await MCPCircuitBreakerManager.record_event(
                                    filtered_retry_servers,
                                    self._mcp_tools_circuit_breaker,
                                    "success",
                                    backend_name="gemini",
                                    agent_id=agent_id,
                                )
                            mcp_connected = True
                            log_backend_activity(
                                "gemini",
                                "MCP connection successful on retry",
                                {"attempt": retry_count},
                                agent_id=agent_id,
                            )
                            # Yield success status
                            yield StreamChunk(
                                type="mcp_status",
                                status="mcp_connected",
                                content=f"MCP connection successful on attempt {retry_count}",
                                source="mcp_tools",
                            )
                            break

                        except (
                            MCPConnectionError,
                            MCPTimeoutError,
                            MCPServerError,
                            MCPError,
                            Exception,
                        ) as e:
                            # Record failure for circuit breaker
                            if self._circuit_breakers_enabled and self._mcp_tools_circuit_breaker:
                                servers = MCPSetupManager.normalize_mcp_servers(self.mcp_servers)
                                await MCPCircuitBreakerManager.record_event(
                                    servers,
                                    self._mcp_tools_circuit_breaker,
                                    "failure",
                                    error_message=str(e),
                                    backend_name="gemini",
                                    agent_id=agent_id,
                                )

                            (
                                should_continue,
                                error_chunks,
                            ) = await self._handle_mcp_retry_error(e, retry_count, max_mcp_retries)
                            if not should_continue:
                                async for chunk in error_chunks:
                                    yield chunk
                                using_sdk_mcp = False

                    # If all retries failed, ensure we fall back gracefully
                    if not mcp_connected:
                        using_sdk_mcp = False
                        self._mcp_client = None

            if not using_sdk_mcp:
                all_tools.extend(builtin_tools)
                if all_tools:
                    config["tools"] = all_tools

            # For coordination requests, use JSON response format (may conflict with tools/sessions)
            if is_coordination:
                # Only request JSON schema when no tools are present
                if (not using_sdk_mcp) and (not all_tools):
                    config["response_mime_type"] = "application/json"
                    config["response_schema"] = CoordinationResponse.model_json_schema()
                else:
                    # Tools or sessions are present; fallback to text parsing
                    pass
            # Log messages being sent after builtin_tools is defined
            log_backend_agent_message(
                agent_id or "default",
                "SEND",
                {
                    "content": full_content,
                    "builtin_tools": len(builtin_tools) if builtin_tools else 0,
                },
                backend_name="gemini",
            )

            # Use streaming for real-time response
            full_content_text = ""
            final_response = None
            if using_sdk_mcp and self.mcp_servers:
                # Reuse active sessions from MCPClient
                try:
                    if not self._mcp_client:
                        raise RuntimeError("MCP client not initialized")
                    mcp_sessions = self._mcp_client.get_active_sessions()
                    if not mcp_sessions:
                        raise RuntimeError("No active MCP sessions available")

                    # Convert sessions to permission sessions if filesystem manager is available
                    if self.filesystem_manager:
                        logger.info(f"[Gemini] Converting {len(mcp_sessions)} MCP sessions to permission sessions")
                        try:
                            from ..mcp_tools.hooks import (
                                convert_sessions_to_permission_sessions,
                            )

                            mcp_sessions = convert_sessions_to_permission_sessions(mcp_sessions, self.filesystem_manager.path_permission_manager)
                        except Exception as e:
                            logger.error(f"[Gemini] Failed to convert sessions to permission sessions: {e}")
                            # Continue with regular sessions on error
                    else:
                        logger.debug("[Gemini] No filesystem manager found, using standard sessions")

                    # Apply sessions as tools, do not mix with builtin or function_declarations
                    session_config = dict(config)

                    # Get available tools from MCP client for logging
                    available_tools = []
                    if self._mcp_client:
                        available_tools = list(self._mcp_client.tools.keys())

                    # Check planning mode - selectively block MCP tools during coordination phase
                    if self.is_planning_mode_enabled():
                        blocked_tools = self.get_planning_mode_blocked_tools()

                        if not blocked_tools:
                            # Empty set means block ALL MCP tools (backward compatible)
                            logger.info("[Gemini] Planning mode enabled - blocking ALL MCP tools during coordination")
                            # Don't set tools at all - this prevents any MCP tool execution
                            log_backend_activity(
                                "gemini",
                                "All MCP tools blocked in planning mode",
                                {
                                    "blocked_tools": len(available_tools),
                                    "session_count": len(mcp_sessions),
                                },
                                agent_id=agent_id,
                            )
                        else:
                            # Selective blocking - allow non-blocked tools to be called
                            # The execution layer (_execute_mcp_function_with_retry) will enforce blocking
                            # but we still register all tools so non-blocked ones can be used
                            logger.info(f"[Gemini] Planning mode enabled - allowing non-blocked MCP tools, blocking {len(blocked_tools)} specific tools")

                            # Pass all sessions - the backend's is_mcp_tool_blocked() will handle selective blocking
                            session_config["tools"] = mcp_sessions

                            log_backend_activity(
                                "gemini",
                                "Selective MCP tools blocked in planning mode",
                                {
                                    "total_tools": len(available_tools),
                                    "blocked_tools": len(blocked_tools),
                                    "allowed_tools": len(available_tools) - len(blocked_tools),
                                },
                                agent_id=agent_id,
                            )
                    else:
                        # Planning mode disabled - allow all MCP tools
                        logger.debug(f"[Gemini] Passing {len(mcp_sessions)} sessions to SDK: {[type(s).__name__ for s in mcp_sessions]}")

                        session_config["tools"] = mcp_sessions

                    # Track MCP tool usage attempt
                    self._mcp_tool_calls_count += 1

                    log_backend_activity(
                        "gemini",
                        "MCP tool call initiated",
                        {
                            "call_number": self._mcp_tool_calls_count,
                            "session_count": len(mcp_sessions),
                            "available_tools": available_tools[:],  # Log first 10 tools for brevity
                            "total_tools": len(available_tools),
                        },
                        agent_id=agent_id,
                    )

                    # Log MCP tool usage (SDK handles actual tool calling automatically)
                    log_tool_call(
                        agent_id,
                        "mcp_session_tools",
                        {
                            "session_count": len(mcp_sessions),
                            "call_number": self._mcp_tool_calls_count,
                            "available_tools": available_tools,
                        },
                        backend_name="gemini",
                    )

                    # Yield detailed MCP status as StreamChunk
                    tools_info = f" ({len(available_tools)} tools available)" if available_tools else ""
                    yield StreamChunk(
                        type="mcp_status",
                        status="mcp_tools_initiated",
                        content=f"MCP tool call initiated (call #{self._mcp_tool_calls_count}){tools_info}: {', '.join(available_tools[:5])}{'...' if len(available_tools) > 5 else ''}",
                        source="mcp_tools",
                    )

                    # Use async streaming call with sessions (SDK supports auto-calling MCP here)
                    # The SDK's session feature will still handle tool calling automatically
                    stream = await client.aio.models.generate_content_stream(model=model_name, contents=full_content, config=session_config)

                    # Initialize MCPCallTracker and MCPResponseTracker for deduplication across chunks
                    mcp_tracker = MCPCallTracker()
                    mcp_response_tracker = MCPResponseTracker()
                    mcp_tools_used = []  # Keep for backward compatibility

                    # Iterate over the asynchronous stream to get chunks as they arrive
                    async for chunk in stream:
                        # ============================================
                        # 1. Process MCP function calls/responses
                        # ============================================
                        if hasattr(chunk, "automatic_function_calling_history") and chunk.automatic_function_calling_history:
                            for history_item in chunk.automatic_function_calling_history:
                                if hasattr(history_item, "parts") and history_item.parts is not None:
                                    for part in history_item.parts:
                                        # Check for function_call part
                                        if hasattr(part, "function_call") and part.function_call:
                                            # Use MCPResponseExtractor to extract call data
                                            call_data = self.mcp_extractor.extract_function_call(part.function_call)

                                            if call_data:
                                                tool_name = call_data["name"]
                                                tool_args = call_data["arguments"]

                                                # Check if this is a new call using the tracker
                                                if mcp_tracker.is_new_call(tool_name, tool_args):
                                                    # Add to tracker history
                                                    call_record = mcp_tracker.add_call(tool_name, tool_args)

                                                    # Add to legacy list for compatibility
                                                    mcp_tools_used.append(
                                                        {
                                                            "name": tool_name,
                                                            "arguments": tool_args,
                                                            "timestamp": call_record["timestamp"],
                                                        },
                                                    )

                                                    # Format timestamp for display
                                                    timestamp_str = time.strftime(
                                                        "%H:%M:%S",
                                                        time.localtime(call_record["timestamp"]),
                                                    )

                                                    # Yield detailed MCP tool call information
                                                    yield StreamChunk(
                                                        type="mcp_status",
                                                        status="mcp_tool_called",
                                                        content=f"🔧 MCP Tool Called: {tool_name} at {timestamp_str} with args: {json.dumps(tool_args, indent=2)}",
                                                        source="mcp_tools",
                                                    )

                                                    # Log the specific tool call
                                                    log_tool_call(
                                                        agent_id,
                                                        tool_name,
                                                        tool_args,
                                                        backend_name="gemini",
                                                    )

                                        # Check for function_response part
                                        elif hasattr(part, "function_response") and part.function_response:
                                            # Use MCPResponseExtractor to extract response data
                                            response_data = self.mcp_extractor.extract_function_response(part.function_response)

                                            if response_data:
                                                tool_name = response_data["name"]
                                                tool_response = response_data["response"]

                                                # Check if this is a new response using the tracker
                                                if mcp_response_tracker.is_new_response(tool_name, tool_response):
                                                    # Add to tracker history
                                                    response_record = mcp_response_tracker.add_response(tool_name, tool_response)

                                                    # Extract text content from CallToolResult
                                                    response_text = None
                                                    if isinstance(tool_response, dict) and "result" in tool_response:
                                                        result = tool_response["result"]
                                                        # Check if result has content attribute (CallToolResult object)
                                                        if hasattr(result, "content") and result.content:
                                                            # Get the first content item (TextContent object)
                                                            first_content = result.content[0]
                                                            # Extract the text attribute
                                                            if hasattr(first_content, "text"):
                                                                response_text = first_content.text

                                                    # Use extracted text or fallback to string representation
                                                    if response_text is None:
                                                        response_text = str(tool_response)

                                                    # Format timestamp for display
                                                    timestamp_str = time.strftime(
                                                        "%H:%M:%S",
                                                        time.localtime(response_record["timestamp"]),
                                                    )

                                                    # Yield MCP tool response information
                                                    yield StreamChunk(
                                                        type="mcp_status",
                                                        status="mcp_tool_response",
                                                        content=f"✅ MCP Tool Response from {tool_name} at {timestamp_str}: {response_text}",
                                                        source="mcp_tools",
                                                    )

                                                    # Log the tool response
                                                    log_backend_activity(
                                                        "gemini",
                                                        "MCP tool response received",
                                                        {
                                                            "tool_name": tool_name,
                                                            "response_preview": str(tool_response)[:],
                                                        },
                                                        agent_id=agent_id,
                                                    )

                            # Track successful MCP tool execution (only on first chunk with MCP history)
                            if not hasattr(self, "_mcp_stream_started"):
                                self._mcp_tool_successes += 1
                                self._mcp_stream_started = True
                                log_backend_activity(
                                    "gemini",
                                    "MCP tool call succeeded",
                                    {"call_number": self._mcp_tool_calls_count},
                                    agent_id=agent_id,
                                )

                                # Log MCP tool success as a tool call event
                                log_tool_call(
                                    agent_id,
                                    "mcp_session_tools",
                                    {
                                        "session_count": len(mcp_sessions),
                                        "call_number": self._mcp_tool_calls_count,
                                    },
                                    result="success",
                                    backend_name="gemini",
                                )

                                # Yield MCP success status as StreamChunk
                                yield StreamChunk(
                                    type="mcp_status",
                                    status="mcp_tools_success",
                                    content=f"MCP tool call succeeded (call #{self._mcp_tool_calls_count})",
                                    source="mcp_tools",
                                )

                        # ============================================
                        # 2. Process text content
                        # ============================================
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

                    # Reset stream tracking
                    if hasattr(self, "_mcp_stream_started"):
                        delattr(self, "_mcp_stream_started")

                    # Add MCP usage indicator with detailed summary using tracker
                    tools_summary = mcp_tracker.get_summary()
                    if not tools_summary or tools_summary == "No MCP tools called":
                        tools_summary = "MCP session completed (no tools explicitly called)"
                    else:
                        tools_summary = f"MCP session complete - {tools_summary}"

                    log_stream_chunk("backend.gemini", "mcp_indicator", tools_summary, agent_id)
                    yield StreamChunk(
                        type="mcp_status",
                        status="mcp_session_complete",
                        content=f"MCP session complete - {tools_summary}",
                        source="mcp_tools",
                    )
                except (
                    MCPConnectionError,
                    MCPTimeoutError,
                    MCPServerError,
                    MCPError,
                    Exception,
                ) as e:
                    log_stream_chunk("backend.gemini", "mcp_error", str(e), agent_id)

                    # Emit user-friendly error message
                    async for chunk in self._handle_mcp_error_and_fallback(e):
                        yield chunk

                    # Fallback to non-MCP streaming with manual configuration
                    manual_config = dict(config)
                    if all_tools:
                        manual_config["tools"] = all_tools

                    # Need to create a new stream for fallback since stream is None
                    stream = await client.aio.models.generate_content_stream(model=model_name, contents=full_content, config=manual_config)

                    async for chunk in stream:
                        # Process text content
                        if hasattr(chunk, "text") and chunk.text:
                            chunk_text = chunk.text
                            full_content_text += chunk_text
                            # Log fallback content chunks
                            log_stream_chunk(
                                "backend.gemini",
                                "fallback_content",
                                chunk_text,
                                agent_id,
                            )
                            yield StreamChunk(type="content", content=chunk_text)

            else:
                # Non-MCP path (existing behavior)
                # Create stream for non-MCP path
                stream = await client.aio.models.generate_content_stream(model=model_name, contents=full_content, config=config)

                async for chunk in stream:
                    # ============================================
                    # 1. Process text content
                    # ============================================
                    if hasattr(chunk, "text") and chunk.text:
                        chunk_text = chunk.text
                        full_content_text += chunk_text

                        # Enhanced logging for non-MCP streaming chunks
                        log_stream_chunk("backend.gemini", "content", chunk_text, agent_id)
                        log_backend_agent_message(
                            agent_id,
                            "RECV",
                            {"content": chunk_text},
                            backend_name="gemini",
                        )

                        yield StreamChunk(type="content", content=chunk_text)

            content = full_content_text

            # Process tool calls - only coordination tool calls (MCP manual mode removed)
            tool_calls_detected: List[Dict[str, Any]] = []

            # Then, process coordination tools if present
            if is_coordination and content.strip() and not tool_calls_detected:
                # For structured output mode, the entire content is JSON
                structured_response = None
                # Try multiple parsing strategies
                try:
                    # Strategy 1: Parse entire content as JSON (works for both modes)
                    structured_response = json.loads(content.strip())
                except json.JSONDecodeError:
                    # Strategy 2: Extract JSON from mixed text content (handles markdown-wrapped JSON)
                    structured_response = self.extract_structured_response(content)

                if structured_response and isinstance(structured_response, dict) and "action_type" in structured_response:
                    # Convert to tool calls
                    tool_calls = self.convert_structured_to_tool_calls(structured_response)
                    if tool_calls:
                        tool_calls_detected = tool_calls
                        # Log conversion to tool calls (summary)
                        log_stream_chunk("backend.gemini", "tool_calls", tool_calls, agent_id)

                        # Log each coordination tool call for analytics/debugging
                        try:
                            for tool_call in tool_calls:
                                log_tool_call(
                                    agent_id,
                                    tool_call.get("function", {}).get("name", "unknown_coordination_tool"),
                                    tool_call.get("function", {}).get("arguments", {}),
                                    result="coordination_tool_called",
                                    backend_name="gemini",
                                )
                        except Exception:
                            # Ensure logging does not interrupt flow
                            pass

            # Process builtin tool results if any tools were used
            if builtin_tools and final_response and hasattr(final_response, "candidates") and final_response.candidates:
                # Check for grounding or code execution results
                candidate = final_response.candidates[0]

                # Check for web search results - only show if actually used
                if hasattr(candidate, "grounding_metadata") and candidate.grounding_metadata:
                    # Check if web search was actually used by looking for queries or chunks
                    search_actually_used = False
                    search_queries = []

                    # Look for web search queries
                    if hasattr(candidate.grounding_metadata, "web_search_queries") and candidate.grounding_metadata.web_search_queries:
                        try:
                            for query in candidate.grounding_metadata.web_search_queries:
                                if query and query.strip():
                                    search_queries.append(query.strip())
                                    search_actually_used = True
                        except (TypeError, AttributeError):
                            pass

                    # Look for grounding chunks (indicates actual search results)
                    if hasattr(candidate.grounding_metadata, "grounding_chunks") and candidate.grounding_metadata.grounding_chunks:
                        try:
                            if len(candidate.grounding_metadata.grounding_chunks) > 0:
                                search_actually_used = True
                        except (TypeError, AttributeError):
                            pass

                    # Only show indicators if search was actually used
                    if search_actually_used:
                        # Enhanced web search logging
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
                                "chunks_found": len(candidate.grounding_metadata.grounding_chunks) if hasattr(candidate.grounding_metadata, "grounding_chunks") else 0,
                            },
                            result="search_completed",
                            backend_name="gemini",
                        )
                        yield StreamChunk(
                            type="content",
                            content="🔍 [Builtin Tool: Web Search] Results integrated\n",
                        )

                        # Show search queries
                        for query in search_queries:
                            log_stream_chunk(
                                "backend.gemini",
                                "web_search_result",
                                {"queries": search_queries, "results_integrated": True},
                                agent_id,
                            )
                            yield StreamChunk(type="content", content=f"🔍 [Search Query] '{query}'\n")

                        self.search_count += 1

                # Check for code execution in the response parts
                if enable_code_execution and hasattr(candidate, "content") and hasattr(candidate.content, "parts"):
                    # Look for executable_code and code_execution_result parts
                    code_parts = []
                    for part in candidate.content.parts:
                        if hasattr(part, "executable_code") and part.executable_code:
                            code_content = getattr(part.executable_code, "code", str(part.executable_code))
                            code_parts.append(f"Code: {code_content}")
                        elif hasattr(part, "code_execution_result") and part.code_execution_result:
                            result_content = getattr(
                                part.code_execution_result,
                                "output",
                                str(part.code_execution_result),
                            )
                            code_parts.append(f"Result: {result_content}")

                    if code_parts:
                        # Code execution was actually used
                        log_stream_chunk(
                            "backend.gemini",
                            "code_execution",
                            "Code executed",
                            agent_id,
                        )

                        # Log code execution as a tool call event
                        try:
                            log_tool_call(
                                agent_id,
                                "code_execution",
                                {"code_parts_count": len(code_parts)},
                                result="code_executed",
                                backend_name="gemini",
                            )
                        except Exception:
                            pass

                        yield StreamChunk(
                            type="content",
                            content="💻 [Builtin Tool: Code Execution] Code executed\n",
                        )
                        # Also show the actual code and result
                        for part in code_parts:
                            if part.startswith("Code: "):
                                code_content = part[6:]  # Remove "Code: " prefix
                                log_stream_chunk(
                                    "backend.gemini",
                                    "code_execution_result",
                                    {
                                        "code_parts": len(code_parts),
                                        "execution_successful": True,
                                        "snippet": code_content,
                                    },
                                    agent_id,
                                )
                                yield StreamChunk(
                                    type="content",
                                    content=f"💻 [Code Executed]\n```python\n{code_content}\n```\n",
                                )
                            elif part.startswith("Result: "):
                                result_content = part[8:]  # Remove "Result: " prefix
                                log_stream_chunk(
                                    "backend.gemini",
                                    "code_execution_result",
                                    {
                                        "code_parts": len(code_parts),
                                        "execution_successful": True,
                                        "result": result_content,
                                    },
                                    agent_id,
                                )
                                yield StreamChunk(
                                    type="content",
                                    content=f"📊 [Result] {result_content}\n",
                                )

                        self.code_execution_count += 1

            # Yield coordination tool calls if detected
            if tool_calls_detected:
                # Enhanced tool calls summary logging
                log_stream_chunk(
                    "backend.gemini",
                    "tool_calls_yielded",
                    {
                        "tool_count": len(tool_calls_detected),
                        "tool_names": [tc.get("function", {}).get("name") for tc in tool_calls_detected],
                    },
                    agent_id,
                )
                yield StreamChunk(type="tool_calls", tool_calls=tool_calls_detected)

            # Build complete message
            complete_message = {"role": "assistant", "content": content.strip()}
            if tool_calls_detected:
                complete_message["tool_calls"] = tool_calls_detected

            # Enhanced complete message logging with metadata
            log_stream_chunk(
                "backend.gemini",
                "complete_message",
                {
                    "content_length": len(content.strip()),
                    "has_tool_calls": bool(tool_calls_detected),
                },
                agent_id,
            )
            yield StreamChunk(type="complete_message", complete_message=complete_message)
            log_stream_chunk("backend.gemini", "done", None, agent_id)
            yield StreamChunk(type="done")

        except Exception as e:
            error_msg = f"Gemini API error: {e}"
            # Enhanced error logging with structured details
            log_stream_chunk(
                "backend.gemini",
                "stream_error",
                {"error_type": type(e).__name__, "error_message": str(e)},
                agent_id,
            )
            yield StreamChunk(type="error", error=error_msg)
        finally:
            # Cleanup resources
            await self._cleanup_resources(stream, client)
            # Ensure context manager exit for MCP cleanup
            try:
                await self.__aexit__(None, None, None)
            except Exception as e:
                log_backend_activity(
                    "gemini",
                    "MCP cleanup failed",
                    {"error": str(e)},
                    agent_id=self.agent_id,
                )

    def get_provider_name(self) -> str:
        """Get the provider name."""
        return "Gemini"

    def get_filesystem_support(self) -> FilesystemSupport:
        """Gemini supports filesystem through MCP servers."""
        return FilesystemSupport.MCP

    def get_supported_builtin_tools(self) -> List[str]:
        """Get list of builtin tools supported by Gemini."""
        return ["google_search_retrieval", "code_execution"]

    def get_mcp_results(self) -> Dict[str, Any]:
        """
        Get all captured MCP tool calls and responses.

        Returns:
            Dict containing:
            - calls: List of all MCP tool calls
            - responses: List of all MCP tool responses
            - pairs: List of matched call-response pairs
            - summary: Statistical summary of interactions
        """
        return {
            "calls": self.mcp_extractor.mcp_calls,
            "responses": self.mcp_extractor.mcp_responses,
            "pairs": self.mcp_extractor.call_response_pairs,
            "summary": self.mcp_extractor.get_summary(),
        }

    def get_mcp_paired_results(self) -> List[Dict[str, Any]]:
        """
        Get only the paired MCP tool calls and responses.

        Returns:
            List of dictionaries containing matched call-response pairs
        """
        return self.mcp_extractor.call_response_pairs

    def get_mcp_summary(self) -> Dict[str, Any]:
        """
        Get a summary of MCP tool interactions.

        Returns:
            Dictionary with statistics about MCP tool usage
        """
        return self.mcp_extractor.get_summary()

    def clear_mcp_results(self):
        """Clear all stored MCP interaction data."""
        self.mcp_extractor.clear()

    def reset_tool_usage(self):
        """Reset tool usage tracking."""
        self.search_count = 0
        self.code_execution_count = 0
        # Reset MCP monitoring metrics
        self._mcp_tool_calls_count = 0
        self._mcp_tool_failures = 0
        self._mcp_tool_successes = 0
        self._mcp_connection_retries = 0
        # Clear MCP extractor data
        self.mcp_extractor.clear()
        super().reset_token_usage()

    async def cleanup_mcp(self):
        """Cleanup MCP connections."""
        if self._mcp_client:
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
                MCPErrorHandler.get_error_details(e, "disconnect", log=True)
            finally:
                self._mcp_client = None
                self._mcp_initialized = False

    async def _cleanup_resources(self, stream, client):
        """Cleanup google-genai resources to avoid unclosed aiohttp sessions."""
        # Close stream
        try:
            if stream is not None:
                close_fn = getattr(stream, "aclose", None) or getattr(stream, "close", None)
                if close_fn is not None:
                    maybe = close_fn()
                    if hasattr(maybe, "__await__"):
                        await maybe
        except Exception as e:
            log_backend_activity(
                "gemini",
                "Stream cleanup failed",
                {"error": str(e)},
                agent_id=self.agent_id,
            )
        # Close internal aiohttp session held by google-genai BaseApiClient
        try:
            if client is not None:
                base_client = getattr(client, "_api_client", None)
                if base_client is not None:
                    session = getattr(base_client, "_aiohttp_session", None)
                    if session is not None and hasattr(session, "close"):
                        if not session.closed:
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
        # Close internal async transport if exposed
        try:
            if client is not None and hasattr(client, "aio") and client.aio is not None:
                aio_obj = client.aio
                for method_name in ("close", "stop"):
                    method = getattr(aio_obj, method_name, None)
                    if method:
                        maybe = method()
                        if hasattr(maybe, "__await__"):
                            await maybe
                        break
        except Exception as e:
            log_backend_activity(
                "gemini",
                "Client AIO cleanup failed",
                {"error": str(e)},
                agent_id=self.agent_id,
            )

        # Close client
        try:
            if client is not None:
                for method_name in ("aclose", "close"):
                    method = getattr(client, method_name, None)
                    if method:
                        maybe = method()
                        if hasattr(maybe, "__await__"):
                            await maybe
                        break
        except Exception as e:
            log_backend_activity(
                "gemini",
                "Client cleanup failed",
                {"error": str(e)},
                agent_id=self.agent_id,
            )

    async def __aenter__(self) -> "GeminiBackend":
        """Async context manager entry."""
        try:
            await self._setup_mcp_tools(agent_id=self.agent_id)
        except Exception as e:
            log_backend_activity(
                "gemini",
                "MCP setup failed during context entry",
                {"error": str(e)},
                agent_id=self.agent_id,
            )
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
            await self.cleanup_mcp()
        except Exception as e:
            log_backend_activity(
                "gemini",
                "Backend cleanup error",
                {"error": str(e)},
                agent_id=self.agent_id,
            )
