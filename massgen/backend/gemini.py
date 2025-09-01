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

import os
import json
import enum
import logging
import asyncio
import re
from typing import Dict, List, Any, AsyncGenerator, Optional, Literal
from .base import LLMBackend, StreamChunk

try:
    from pydantic import BaseModel, Field
except ImportError:
    BaseModel = None
    Field = None

# MCP integration imports

try:
    from ..mcp_tools import MultiMCPClient, MCPError, MCPConnectionError
    from ..mcp_tools.config_validator import MCPConfigValidator
    from ..mcp_tools.exceptions import (
        MCPConfigurationError,
        MCPValidationError,
        MCPTimeoutError,
        MCPServerError,
    )
except ImportError:  # MCP not installed or import failed within mcp_tools
    MultiMCPClient = None  # type: ignore[assignment]
    MCPError = ImportError  # type: ignore[assignment]
    MCPConnectionError = ImportError  # type: ignore[assignment]
    MCPConfigValidator = None  # type: ignore[assignment]
    MCPConfigurationError = ImportError  # type: ignore[assignment]
    MCPValidationError = ImportError  # type: ignore[assignment]
    MCPTimeoutError = ImportError  # type: ignore[assignment]
    MCPServerError = ImportError  # type: ignore[assignment]

# Set up logging
logger = logging.getLogger(__name__)


class ActionType(enum.Enum):
    """Action types for structured output."""

    VOTE = "vote"
    NEW_ANSWER = "new_answer"


class VoteAction(BaseModel):
    """Structured output for voting action."""

    action: ActionType = Field(default=ActionType.VOTE, description="Action type")
    agent_id: str = Field(
        description="Anonymous agent ID to vote for (e.g., 'agent1', 'agent2')"
    )
    reason: str = Field(description="Brief reason why this agent has the best answer")


class NewAnswerAction(BaseModel):
    """Structured output for new answer action."""

    action: ActionType = Field(default=ActionType.NEW_ANSWER, description="Action type")
    content: str = Field(
        description="Your improved answer. If any builtin tools like search or code execution were used, include how they are used here."
    )


class CoordinationResponse(BaseModel):
    """Structured response for coordination actions."""

    action_type: ActionType = Field(description="Type of action to take")
    vote_data: Optional[VoteAction] = Field(
        default=None, description="Vote data if action is vote"
    )
    answer_data: Optional[NewAnswerAction] = Field(
        default=None, description="Answer data if action is new_answer"
    )


class GeminiBackend(LLMBackend):
    """Google Gemini backend using structured output for coordination and MCP tool integration."""

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(api_key, **kwargs)
        self.api_key = (
            api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        )
        self.search_count = 0
        self.code_execution_count = 0

        # MCP integration
        self.mcp_servers = kwargs.pop("mcp_servers", [])
        self.allowed_tools = kwargs.pop("allowed_tools", None)
        self.exclude_tools = kwargs.pop("exclude_tools", None)
        self._mcp_client: Optional[MultiMCPClient] = None
        self._mcp_initialized = False

        # MCP tool execution monitoring
        self._mcp_tool_calls_count = 0
        self._mcp_tool_failures = 0
        self._mcp_tool_successes = 0

        # Limit for message history growth within MCP execution loop
        self._max_mcp_message_history = kwargs.pop("max_mcp_message_history", 200)
        self._mcp_connection_retries = 0

        # Circuit breaker configuration (previously missing in gemini.py)
        self._circuit_breakers_enabled = kwargs.pop("circuit_breaker_enabled", True)
        self._mcp_tools_circuit_breaker = None

        # Initialize circuit breaker if enabled
        if self._circuit_breakers_enabled:
            try:
                from ..mcp_tools.circuit_breaker import MCPCircuitBreaker
                from ..mcp_tools.backend_utils import MCPConfigHelper

                # Use shared utility to build circuit breaker configuration
                mcp_tools_config = MCPConfigHelper.build_circuit_breaker_config("mcp_tools")
                if mcp_tools_config:
                    self._mcp_tools_circuit_breaker = MCPCircuitBreaker(mcp_tools_config)
                    logger.debug("Circuit breaker initialized for Gemini MCP tools")
                else:
                    logger.warning("Circuit breaker config not available, disabling circuit breaker functionality")
                    self._circuit_breakers_enabled = False
            except ImportError:
                logger.warning("Circuit breaker not available, disabling circuit breaker functionality")
                self._circuit_breakers_enabled = False

        if BaseModel is None:
            raise ImportError(
                "pydantic is required for Gemini backend. Install with: pip install pydantic"
            )

    def _normalize_mcp_servers(self) -> List[Dict[str, Any]]:
        """Validate and normalize mcp_servers into a list of dicts."""
        from ..mcp_tools.backend_utils import MCPSetupManager
        return MCPSetupManager.normalize_mcp_servers(self.mcp_servers)

    async def _setup_mcp_tools(self) -> None:
        """Initialize MCP client (sessions only)."""
        if not self.mcp_servers or self._mcp_initialized:
            return

        if MultiMCPClient is None:
            reason = "MCP import failed - MultiMCPClient not available"
            logger.warning(
                "MCP support import failed (%s). mcp_servers were provided; falling back to workflow tools without MCP. Ensure the 'mcp' package is installed and compatible with this codebase.",
                reason,
            )
            # Clear MCP servers to prevent further attempts
            self.mcp_servers = []
            return

        try:
            # Validate MCP configuration before initialization
            validated_config = {
                "mcp_servers": self.mcp_servers,
                "allowed_tools": self.allowed_tools,
                "exclude_tools": self.exclude_tools
            }
            
            if MCPConfigValidator is not None:
                try:
                    backend_config = {
                        "mcp_servers": self.mcp_servers,
                        "allowed_tools": self.allowed_tools,
                        "exclude_tools": self.exclude_tools
                    }
                    # Use the comprehensive validator class for enhanced validation
                    validator = MCPConfigValidator()
                    validated_config = validator.validate_backend_mcp_config(
                        backend_config
                    )
                    self.mcp_servers = validated_config.get(
                        "mcp_servers", self.mcp_servers
                    )
                    logger.debug(
                        f"MCP configuration validation passed for {len(self.mcp_servers)} servers"
                    )

                    # Log validated server names for debugging
                    if logger.isEnabledFor(logging.DEBUG):
                        server_names = [
                            server.get("name", "unnamed") for server in self.mcp_servers
                        ]
                        logger.debug(
                            f"Validated MCP servers: {', '.join(server_names)}"
                        )
                except MCPConfigurationError as e:
                    logger.error(
                        f"MCP configuration validation failed: {e.original_message}"
                    )
                    self._mcp_client = None  # Clear client state for consistency
                    raise RuntimeError(
                        f"Invalid MCP configuration: {e.original_message}"
                    ) from e
                except MCPValidationError as e:
                    logger.error(f"MCP validation failed: {e.original_message}")
                    self._mcp_client = None  # Clear client state for consistency
                    raise RuntimeError(
                        f"MCP validation error: {e.original_message}"
                    ) from e
                except Exception as e:
                    if isinstance(e, (ImportError, AttributeError)):
                        logger.debug(f"MCP validation not available: {e}")
                        # Don't clear client for import errors - validation just unavailable
                    else:
                        logger.warning(f"MCP validation error: {e}")
                        self._mcp_client = None  # Clear client state for consistency
                        raise RuntimeError(
                            f"MCP configuration validation failed: {e}"
                        ) from e
            else:
                logger.debug(
                    "MCP validation not available, proceeding without validation"
                )

            normalized_servers = self._normalize_mcp_servers()
            logger.info(
                f"Setting up MCP sessions with {len(normalized_servers)} servers"
            )

            # Apply circuit breaker filtering before connection attempts
            filtered_servers = self._apply_mcp_tools_circuit_breaker_filtering(normalized_servers)
            if not filtered_servers:
                logger.warning("All MCP servers are circuit breaker blocked")
                return

            if len(filtered_servers) < len(normalized_servers):
                logger.info(f"Circuit breaker filtered {len(normalized_servers) - len(filtered_servers)} servers")

            # Extract tool filtering parameters from validated config
            allowed_tools = validated_config.get("allowed_tools")
            exclude_tools = validated_config.get("exclude_tools")

            # Log tool filtering if configured
            if allowed_tools:
                logger.info(f"MCP tool filtering - allowed tools: {allowed_tools}")
            if exclude_tools:
                logger.info(f"MCP tool filtering - excluding: {exclude_tools}")

            self._mcp_client = await MultiMCPClient.create_and_connect(
                filtered_servers,
                timeout_seconds=30,
                allowed_tools=allowed_tools,
                exclude_tools=exclude_tools
            )

            # Record success for circuit breaker
            await self._record_mcp_tools_success(filtered_servers)

            self._mcp_initialized = True
            logger.info("Successfully initialized MCP sessions")

        except Exception as e:
            # Record failure for circuit breaker
            await self._record_mcp_tools_failure(self.mcp_servers, str(e))

            # Enhanced error handling for different MCP error types
            if isinstance(e, RuntimeError) and "MCP configuration" in str(e):
                raise
            elif isinstance(e, MCPConnectionError):
                logger.error(f"MCP connection failed during setup: {e}")
                self._mcp_client = None
                raise RuntimeError(f"Failed to establish MCP connections: {e}") from e
            elif isinstance(e, MCPTimeoutError):
                logger.error(f"MCP connection timed out during setup: {e}")
                self._mcp_client = None
                raise RuntimeError(f"MCP connection timeout: {e}") from e
            elif isinstance(e, MCPServerError):
                logger.error(f"MCP server error during setup: {e}")
                self._mcp_client = None
                raise RuntimeError(f"MCP server error: {e}") from e
            elif isinstance(e, MCPError):
                logger.warning(f"MCP error during setup: {e}")
                self._mcp_client = None
                return

            else:
                logger.warning(f"Failed to setup MCP sessions: {e}")
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

    def build_structured_output_prompt(
        self, base_content: str, valid_agent_ids: Optional[List[str]] = None
    ) -> str:
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

    def extract_structured_response(
        self, response_text: str
    ) -> Optional[Dict[str, Any]]:
        """Extract structured JSON response from model output."""
        try:
            # Strategy 0: Look for JSON inside markdown code blocks first
            markdown_json_pattern = r"```json\s*(\{.*?\})\s*```"
            markdown_matches = re.findall(
                markdown_json_pattern, response_text, re.DOTALL
            )

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

    def convert_structured_to_tool_calls(
        self, structured_response: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
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
                }
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
                }
            ]

        return []

    def _mcp_error_details(self, error: Exception, context: Optional[str] = None, *, log: bool = False) -> tuple[str, str, str]:
        """Return standardized MCP error info and optionally log."""
        from ..mcp_tools.backend_utils import MCPErrorHandler
        return MCPErrorHandler.get_error_details(error, context, log=log)

    async def _handle_mcp_retry_error(
        self, error: Exception, retry_count: int, max_retries: int
    ) -> tuple[bool, AsyncGenerator[StreamChunk, None]]:
        """Handle MCP retry errors with specific messaging and fallback logic.

        Returns:
            tuple: (should_continue_retrying, error_chunks_generator)
        """
        log_type, user_message, _ = self._mcp_error_details(error)
        
        # Log the retry attempt
        logger.warning(f"MCP {log_type} on attempt {retry_count}: {error}")

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
            return
            yield  # Make this a generator

        return True, empty_chunks()

    async def _handle_mcp_error_and_fallback(
        self,
        error: Exception,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Handle MCP errors with specific messaging"""
        self._mcp_tool_failures += 1

        log_type, user_message, _ = self._mcp_error_details(error)

        # Log with specific error type
        logger.warning(
            f"MCP tool call #{self._mcp_tool_calls_count} failed - {log_type}: {error}"
        )

        # Yield user-friendly error message
        yield StreamChunk(
            type="content",
            content=f"\n⚠️  {user_message} ({error}); continuing without MCP tools\n",
        )

    def _trim_message_history(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Trim message history to prevent unbounded growth in MCP execution loop."""
        from ..mcp_tools.backend_utils import MCPMessageManager
        max_items = getattr(self, '_max_mcp_message_history', 200)
        return MCPMessageManager.trim_message_history(messages, max_items)

    def _is_transient_error(self, error: Exception) -> bool:
        """Determine if an error is transient and should be retried."""
        from ..mcp_tools.backend_utils import MCPErrorHandler
        return MCPErrorHandler.is_transient_error(error)

    def _log_mcp_error(self, error: Exception, context: str) -> None:
        """Log MCP error with appropriate level and context."""
        from ..mcp_tools.backend_utils import MCPErrorHandler
        MCPErrorHandler.log_error(error, context)

    def _apply_mcp_tools_circuit_breaker_filtering(self, servers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter MCP tools servers based on circuit breaker state."""
        from ..mcp_tools.backend_utils import MCPCircuitBreakerManager

        if not self._circuit_breakers_enabled or not self._mcp_tools_circuit_breaker:
            return servers

        return MCPCircuitBreakerManager.apply_circuit_breaker_filtering(servers, self._mcp_tools_circuit_breaker)

    async def _record_mcp_tools_success(self, servers: List[Dict[str, Any]]) -> None:
        """Record successful MCP tools operation for circuit breaker."""
        from ..mcp_tools.backend_utils import MCPCircuitBreakerManager

        if self._circuit_breakers_enabled and self._mcp_tools_circuit_breaker:
            await MCPCircuitBreakerManager.record_success(servers, self._mcp_tools_circuit_breaker)

    async def _record_mcp_tools_failure(self, servers: List[Dict[str, Any]], error_message: str) -> None:
        """Record connection failure for mcp_tools servers in circuit breaker."""
        from ..mcp_tools.backend_utils import MCPCircuitBreakerManager

        if self._circuit_breakers_enabled and self._mcp_tools_circuit_breaker:
            await MCPCircuitBreakerManager.record_failure(servers, self._mcp_tools_circuit_breaker, error_message)

    async def _record_mcp_tools_event(
        self,
        servers: List[Dict[str, Any]],
        event: Literal["success", "failure"],
        error_message: Optional[str] = None,
    ) -> None:
        """Record success/failure for mcp_tools servers in circuit breaker."""
        from ..mcp_tools.backend_utils import MCPCircuitBreakerManager

        if self._circuit_breakers_enabled and self._mcp_tools_circuit_breaker:
            await MCPCircuitBreakerManager.record_event(servers, self._mcp_tools_circuit_breaker, event, error_message)

    async def _execute_mcp_function_with_retry(
        self, function_name: str, args: Dict[str, Any]
    ) -> Any:
        """Execute MCP function with exponential backoff retry logic."""
        from ..mcp_tools.backend_utils import MCPExecutionManager

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
                await self._record_mcp_tools_failure(self.mcp_servers, error_msg)
            else:
                await self._record_mcp_tools_success(self.mcp_servers)

        return await MCPExecutionManager.execute_function_with_retry(
            function_name=function_name,
            args=args,
            functions=self.functions,
            max_retries=3,
            stats_callback=stats_callback,
            circuit_breaker_callback=circuit_breaker_callback,
            logger_instance=logger
        )

    async def stream_with_tools(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream response using Gemini API with structured output for coordination and MCP tool support."""
        try:
            from google import genai

            # Setup MCP tools if not already initialized
            await self._setup_mcp_tools()

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
                            agent_id_param = (
                                func_def.get("parameters", {})
                                .get("properties", {})
                                .get("agent_id", {})
                            )
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
                conversation_content = self.build_structured_output_prompt(
                    conversation_content, valid_agent_ids
                )

            # Combine system message and conversation
            full_content = ""
            if system_message:
                full_content += f"{system_message}\n\n"
            full_content += conversation_content

            # Use google-genai package
            client = genai.Client(api_key=self.api_key)
            
            # Setup builtin tools (only when not using SDK MCP sessions)
            builtin_tools = []
            if not using_sdk_mcp:
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
            excluded_params = {
                "enable_web_search", "enable_code_execution", "agent_id", "session_id",
                # MCP-specific parameters that should not be passed to Gemini
                "use_multi_mcp", "mcp_servers", "mcp_sdk_auto", "type"
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

            # Branch 1: SDK auto-calling via MCP sessions (reuse existing MultiMCPClient sessions)
            if using_sdk_mcp and self.mcp_servers:
                if (
                    not self._mcp_client
                    or not getattr(self._mcp_client, "is_connected", lambda: False)()
                ):
                    # Retry MCP connection up to 5 times before falling back
                    max_mcp_retries = 5
                    mcp_connected = False

                    for retry_count in range(1, max_mcp_retries + 1):
                        try:
                            # Track retry attempts
                            self._mcp_connection_retries = retry_count

                            if retry_count > 1:
                                logger.info(
                                    f"MCP connection retry {retry_count}/{max_mcp_retries}"
                                )
                                # Brief delay between retries
                                await asyncio.sleep(
                                    0.5 * retry_count
                                )  # Progressive backoff

                            # Apply circuit breaker filtering before retry attempts
                            filtered_retry_servers = self._apply_mcp_tools_circuit_breaker_filtering(self.mcp_servers)
                            if not filtered_retry_servers:
                                logger.warning("All MCP servers circuit breaker blocked during retry")
                                using_sdk_mcp = False
                                break

                            # Get validated config for tool filtering parameters
                            backend_config = {"mcp_servers": self.mcp_servers}
                            if MCPConfigValidator is not None:
                                try:
                                    validator = MCPConfigValidator()
                                    validated_config_retry = validator.validate_backend_mcp_config(
                                        backend_config
                                    )
                                    allowed_tools_retry = validated_config_retry.get("allowed_tools")
                                    exclude_tools_retry = validated_config_retry.get("exclude_tools")
                                except Exception:
                                    allowed_tools_retry = None
                                    exclude_tools_retry = None
                            else:
                                allowed_tools_retry = None
                                exclude_tools_retry = None

                            self._mcp_client = await MultiMCPClient.create_and_connect(
                                filtered_retry_servers,
                                timeout_seconds=30,
                                allowed_tools=allowed_tools_retry,
                                exclude_tools=exclude_tools_retry
                            )

                            # Record success for circuit breaker
                            await self._record_mcp_tools_success(filtered_retry_servers)
                            mcp_connected = True
                            logger.info(
                                f"MCP connection successful on attempt {retry_count}"
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
                            await self._record_mcp_tools_failure(self.mcp_servers, str(e))

                            (
                                should_continue,
                                error_chunks,
                            ) = await self._handle_mcp_retry_error(
                                e, retry_count, max_mcp_retries
                            )
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

            # Use streaming for real-time response
            full_content_text = ""
            final_response = None

            if using_sdk_mcp and self.mcp_servers:
                # Reuse active sessions from MultiMCPClient
                try:
                    if not self._mcp_client:
                        raise RuntimeError("MCP client not initialized")
                    mcp_sessions = self._mcp_client.get_active_sessions()
                    if not mcp_sessions:
                        raise RuntimeError("No active MCP sessions available")

                    # Apply sessions as tools, do not mix with builtin or function_declarations
                    session_config = dict(config)
                    session_config["tools"] = mcp_sessions

                    # Track MCP tool usage attempt
                    self._mcp_tool_calls_count += 1
                    logger.debug(
                        f"MCP tool call #{self._mcp_tool_calls_count} initiated"
                    )

                    # Use async streaming call with sessions (SDK supports auto-calling MCP here)
                    # The SDK's session feature will still handle tool calling automatically
                    stream = await client.aio.models.generate_content_stream(
                        model=model_name, contents=full_content, config=session_config
                    )

                    # Iterate over the asynchronous stream to get chunks as they arrive
                    async for chunk in stream:
                        # Track successful MCP tool execution (only on first chunk)
                        if not hasattr(self, '_mcp_stream_started'):
                            self._mcp_tool_successes += 1
                            self._mcp_stream_started = True
                            logger.debug(
                                f"MCP tool call #{self._mcp_tool_calls_count} succeeded"
                            )

                        # Direct text extraction for MCP path
                        if hasattr(chunk, "text") and chunk.text:
                            chunk_text = chunk.text
                            full_content_text += chunk_text
                            yield StreamChunk(type="content", content=chunk_text)

                        # Keep track of the final response for tool processing
                        if hasattr(chunk, "candidates"):
                            final_response = chunk

                    # Reset stream tracking
                    if hasattr(self, '_mcp_stream_started'):
                        delattr(self, '_mcp_stream_started')

                    # Add MCP usage indicator
                    yield StreamChunk(
                        type="content",
                        content="🔧 [MCP Tools] Session-based tools used\n",
                    )
                except (
                    MCPConnectionError,
                    MCPTimeoutError,
                    MCPServerError,
                    MCPError,
                    Exception,
                ) as e:
                    # Emit user-friendly error message
                    async for chunk in self._handle_mcp_error_and_fallback(e):
                        yield chunk

                    # Fallback to non-MCP streaming with manual configuration
                    manual_config = dict(config)
                    if all_tools:
                        manual_config["tools"] = all_tools

                    stream = await client.aio.models.generate_content_stream(
                        model=model_name, contents=full_content, config=manual_config
                    )
                    async for chunk in stream:
                        if hasattr(chunk, "text") and chunk.text:
                            chunk_text = chunk.text
                            full_content_text += chunk_text
                            yield StreamChunk(type="content", content=chunk_text)

                        if hasattr(chunk, "candidates"):
                            final_response = chunk

                        if (
                            (not using_sdk_mcp)
                            and builtin_tools
                            and hasattr(chunk, "candidates")
                            and chunk.candidates
                        ):
                            candidate = chunk.candidates[0]

                            if (
                                enable_code_execution
                                and hasattr(candidate, "content")
                                and hasattr(candidate.content, "parts")
                            ):
                                for part in candidate.content.parts:
                                    if (
                                        hasattr(part, "executable_code")
                                        and part.executable_code
                                    ):
                                        code_content = getattr(
                                            part.executable_code,
                                            "code",
                                            str(part.executable_code),
                                        )
                                        yield StreamChunk(
                                            type="content",
                                            content=f"\n💻 [Code Executed]\n```python\n{code_content}\n```\n",
                                        )
                                    elif (
                                        hasattr(part, "code_execution_result")
                                        and part.code_execution_result
                                    ):
                                        result_content = getattr(
                                            part.code_execution_result,
                                            "output",
                                            str(part.code_execution_result),
                                        )
                                        yield StreamChunk(
                                            type="content",
                                            content=f"📊 [Result] {result_content}\n",
                                        )
            else:
                # Non-MCP path (existing behavior)
                stream = await client.aio.models.generate_content_stream(
                    model=model_name, contents=full_content, config=config
                )
                async for chunk in stream:
                    if hasattr(chunk, "text") and chunk.text:
                        chunk_text = chunk.text
                        full_content_text += chunk_text
                        yield StreamChunk(type="content", content=chunk_text)

                    if hasattr(chunk, "candidates"):
                        final_response = chunk

                    if (
                        (not using_sdk_mcp)
                        and builtin_tools
                        and hasattr(chunk, "candidates")
                        and chunk.candidates
                    ):
                        candidate = chunk.candidates[0]

                        if (
                            enable_code_execution
                            and hasattr(candidate, "content")
                            and hasattr(candidate.content, "parts")
                        ):
                            for part in candidate.content.parts:
                                if (
                                    hasattr(part, "executable_code")
                                    and part.executable_code
                                ):
                                    code_content = getattr(
                                        part.executable_code,
                                        "code",
                                        str(part.executable_code),
                                    )
                                    yield StreamChunk(
                                        type="content",
                                        content=f"\n💻 [Code Executed]\n```python\n{code_content}\n```\n",
                                    )
                                elif (
                                    hasattr(part, "code_execution_result")
                                    and part.code_execution_result
                                ):
                                    result_content = getattr(
                                        part.code_execution_result,
                                        "output",
                                        str(part.code_execution_result),
                                    )
                                    yield StreamChunk(
                                        type="content",
                                        content=f"📊 [Result] {result_content}\n",
                                    )

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

                if (
                    structured_response
                    and isinstance(structured_response, dict)
                    and "action_type" in structured_response
                ):
                    # Convert to tool calls
                    tool_calls = self.convert_structured_to_tool_calls(
                        structured_response
                    )
                    if tool_calls:
                        tool_calls_detected = tool_calls

            # Process builtin tool results if any tools were used
            if (
                not using_sdk_mcp
                and builtin_tools
                and final_response
                and hasattr(final_response, "candidates")
                and final_response.candidates
            ):
                # Check for grounding or code execution results
                candidate = final_response.candidates[0]

                # Check for web search results - only show if actually used
                if (
                    hasattr(candidate, "grounding_metadata")
                    and candidate.grounding_metadata
                ):
                    # Check if web search was actually used by looking for queries or chunks
                    search_actually_used = False
                    search_queries = []

                    # Look for web search queries
                    if (
                        hasattr(candidate.grounding_metadata, "web_search_queries")
                        and candidate.grounding_metadata.web_search_queries
                    ):
                        try:
                            for (
                                query
                            ) in candidate.grounding_metadata.web_search_queries:
                                if query and query.strip():
                                    search_queries.append(query.strip())
                                    search_actually_used = True
                        except (TypeError, AttributeError):
                            pass

                    # Look for grounding chunks (indicates actual search results)
                    if (
                        hasattr(candidate.grounding_metadata, "grounding_chunks")
                        and candidate.grounding_metadata.grounding_chunks
                    ):
                        try:
                            if len(candidate.grounding_metadata.grounding_chunks) > 0:
                                search_actually_used = True
                        except (TypeError, AttributeError):
                            pass

                    # Only show indicators if search was actually used
                    if search_actually_used:
                        yield StreamChunk(
                            type="content",
                            content="🔍 [Builtin Tool: Web Search] Results integrated\n",
                        )

                        # Show search queries
                        for query in search_queries:
                            yield StreamChunk(
                                type="content", content=f"🔍 [Search Query] '{query}'\n"
                            )

                        self.search_count += 1

                # Check for code execution in the response parts
                if (
                    enable_code_execution
                    and hasattr(candidate, "content")
                    and hasattr(candidate.content, "parts")
                ):
                    # Look for executable_code and code_execution_result parts
                    code_parts = []
                    for part in candidate.content.parts:
                        if hasattr(part, "executable_code") and part.executable_code:
                            code_content = getattr(
                                part.executable_code, "code", str(part.executable_code)
                            )
                            code_parts.append(f"Code: {code_content}")
                        elif (
                            hasattr(part, "code_execution_result")
                            and part.code_execution_result
                        ):
                            result_content = getattr(
                                part.code_execution_result,
                                "output",
                                str(part.code_execution_result),
                            )
                            code_parts.append(f"Result: {result_content}")

                    if code_parts:
                        # Code execution was actually used
                        yield StreamChunk(
                            type="content",
                            content="💻 [Builtin Tool: Code Execution] Code executed\n",
                        )
                        # Also show the actual code and result
                        for part in code_parts:
                            if part.startswith("Code: "):
                                code_content = part[6:]  # Remove "Code: " prefix
                                yield StreamChunk(
                                    type="content",
                                    content=f"💻 [Code Executed]\n```python\n{code_content}\n```\n",
                                )
                            elif part.startswith("Result: "):
                                result_content = part[8:]  # Remove "Result: " prefix
                                yield StreamChunk(
                                    type="content",
                                    content=f"📊 [Result] {result_content}\n",
                                )

                        self.code_execution_count += 1

            # Yield coordination tool calls if detected
            if tool_calls_detected:
                yield StreamChunk(type="tool_calls", tool_calls=tool_calls_detected)

            # Build complete message
            complete_message = {"role": "assistant", "content": content.strip()}
            if tool_calls_detected:
                complete_message["tool_calls"] = tool_calls_detected

            yield StreamChunk(
                type="complete_message", complete_message=complete_message
            )
            yield StreamChunk(type="done")

        except Exception as e:
            yield StreamChunk(type="error", error=f"Gemini API error: {e}")

    def get_provider_name(self) -> str:
        """Get the provider name."""
        return "Gemini"

    def get_supported_builtin_tools(self) -> List[str]:
        """Get list of builtin tools supported by Gemini."""
        return ["google_search_retrieval", "code_execution"]

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text (Gemini uses ~4 chars per token)."""
        return len(text) // 4

    def calculate_cost(
        self, input_tokens: int, output_tokens: int, model: str
    ) -> float:
        """Calculate cost for Gemini token usage (2025 pricing)."""
        model_lower = model.lower()

        if "gemini-2.5-pro" in model_lower:
            # Gemini 2.5 Pro pricing
            input_cost = (input_tokens / 1_000_000) * 1.25
            output_cost = (output_tokens / 1_000_000) * 5.0
        elif "gemini-2.5-flash" in model_lower:
            if "lite" in model_lower:
                # Gemini 2.5 Flash-Lite pricing
                input_cost = (input_tokens / 1_000_000) * 0.075
                output_cost = (output_tokens / 1_000_000) * 0.30
            else:
                # Gemini 2.5 Flash pricing
                input_cost = (input_tokens / 1_000_000) * 0.15
                output_cost = (output_tokens / 1_000_000) * 0.60
        else:
            # Default fallback (assume Flash pricing)
            input_cost = (input_tokens / 1_000_000) * 0.15
            output_cost = (output_tokens / 1_000_000) * 0.60

        # Add tool usage costs (estimates)
        tool_costs = 0.0
        if self.search_count > 0:
            tool_costs += self.search_count * 0.01  # Estimated search cost

        if self.code_execution_count > 0:
            tool_costs += self.code_execution_count * 0.005  # Estimated execution cost

        return input_cost + output_cost + tool_costs

    def reset_tool_usage(self):
        """Reset tool usage tracking."""
        self.search_count = 0
        self.code_execution_count = 0
        # Reset MCP monitoring metrics
        self._mcp_tool_calls_count = 0
        self._mcp_tool_failures = 0
        self._mcp_tool_successes = 0
        self._mcp_connection_retries = 0
        super().reset_token_usage()

    async def cleanup_mcp(self):
        """Cleanup MCP connections."""
        if self._mcp_client:
            try:
                await self._mcp_client.disconnect()
                logger.info("MCP client disconnected successfully")
            except (
                MCPConnectionError,
                MCPTimeoutError,
                MCPServerError,
                MCPError,
                Exception,
            ) as e:
                self._mcp_error_details(e, "disconnect", log=True)
            finally:
                self._mcp_client = None
                self._mcp_initialized = False