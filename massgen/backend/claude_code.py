"""
Claude Code Stream Backend - Streaming interface using claude-code-sdk-python.

This backend provides integration with Claude Code through the
claude-code-sdk-python, leveraging Claude Code's server-side session
persistence and tool execution capabilities.

Key Features:
- ✅ Native Claude Code streaming integration
- ✅ Server-side session persistence (no client-side session
  management needed)
- ✅ Built-in tool execution (Read, Write, Bash, WebSearch, etc.)
- ✅ MassGen workflow tool integration (new_answer, vote via system prompts)
- ✅ Single persistent client with automatic session ID tracking
- ✅ Cost tracking from server-side usage data
- ✅ MCP command line mode: Bash tool disabled, execute_command MCP used instead (Docker or local)

Architecture:
- Uses ClaudeSDKClient with minimal functionality overlay
- Claude Code server maintains conversation history
- Extracts session IDs from ResultMessage responses
- Injects MassGen workflow tools via system prompts
- Converts claude-code-sdk Messages to MassGen StreamChunks

Requirements:
- claude-code-sdk-python installed: uv add claude-code-sdk
- Claude Code CLI available in PATH
- ANTHROPIC_API_KEY configured OR Claude subscription authentication

Test Results:
✅ TESTED 2025-08-10: Single agent coordination working correctly
- Command: uv run python -m massgen.cli --config claude_code_single.yaml "2+2=?"
- Auto-created working directory: claude_code_workspace/
- Session: 42593707-bca6-40ad-b154-7dc1c222d319
- Model: claude-sonnet-4-20250514 (Claude Code default)
- Tools available: Task, Bash, Glob, Grep, LS, Read, Write, WebSearch, etc.
- Answer provided: "2 + 2 = 4"
- Coordination: Agent voted for itself, selected as final answer
- Performance: 70 seconds total (includes coordination overhead)

TODO:
- Consider including cwd/session_id in new_answer results for context preservation
- Investigate whether next iterations need working directory context
"""

from __future__ import annotations

import ast
import asyncio
import atexit
import json
import os
import shutil
import sys
import time
import uuid
import warnings
from collections.abc import AsyncGenerator, Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from claude_agent_sdk import (  # type: ignore
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    PermissionResultAllow,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from ..logger_config import (
    log_backend_activity,
    log_backend_agent_message,
    log_stream_chunk,
    logger,
)
from ..mcp_tools.backend_utils import MCPResourceManager
from ..structured_logging import get_current_round, get_tracer, log_token_usage
from ..tool import ToolManager
from ..utils.tool_argument_normalization import normalize_json_object_argument
from ._streaming_buffer_mixin import StreamingBufferMixin
from .base import (
    build_workflow_instructions,  # Used in _build_system_prompt_with_workflow_tools
)
from .base import (
    FilesystemSupport,
    LLMBackend,
    StreamChunk,
)
from .base import extract_structured_response as _extract_structured_response
from .base import (
    get_multimodal_tool_definitions,
)
from .base import parse_workflow_tool_calls as _parse_workflow_tool_calls
from .base_with_custom_tool_and_mcp import (
    BACKGROUND_TOOL_CANCEL_NAME,
    BACKGROUND_TOOL_LIST_NAME,
    BACKGROUND_TOOL_MANAGEMENT_NAMES,
    BACKGROUND_TOOL_RESULT_NAME,
    BACKGROUND_TOOL_START_NAME,
    BACKGROUND_TOOL_STATUS_NAME,
    BACKGROUND_TOOL_TERMINAL_STATUSES,
    BACKGROUND_TOOL_WAIT_DEFAULT_TIMEOUT_SECONDS,
    BACKGROUND_TOOL_WAIT_MAX_TIMEOUT_SECONDS,
    BACKGROUND_TOOL_WAIT_NAME,
    BACKGROUND_TOOL_WAIT_POLL_INTERVAL_SECONDS,
    BackgroundToolJob,
    ExecutionContext,
)
from .capabilities import normalize_backend_type
from .native_tool_mixin import NativeToolBackendMixin


class ClaudeCodeBackend(NativeToolBackendMixin, StreamingBufferMixin, LLMBackend):
    """Claude Code backend using claude-code-sdk-python.

    Provides streaming interface to Claude Code with built-in tool execution
    capabilities and MassGen workflow tool integration. Uses ClaudeSDKClient
    for direct communication with Claude Code server.

    TODO (v0.0.14 Context Sharing Enhancement - See docs/dev_notes/v0.0.14-context.md):
    - Implement permission enforcement during file/workspace operations
    - Add execute_with_permissions() method to check permissions before operations
    - Integrate with PermissionManager for access control validation
    - Add audit logging for all file system access attempts
    - Enforce workspace boundaries based on agent permissions
    - Prevent unauthorized access to other agents' workspaces
    - Support permission-aware tool execution (Read, Write, Bash, etc.)
    """

    supports_sdk_mcp = True

    def __init__(self, api_key: str | None = None, **kwargs):
        """Initialize ClaudeCodeBackend.

        Args:
            api_key: Anthropic API key (falls back to CLAUDE_CODE_API_KEY,
                    then ANTHROPIC_API_KEY env vars). If None, will attempt
                    to use Claude subscription authentication
            **kwargs: Additional configuration options including:
                - model: Claude model name
                - system_prompt: Base system prompt
                - allowed_tools: List of allowed tools
                - max_thinking_tokens: Maximum thinking tokens
                - cwd: Current working directory

        Note:
            Authentication is validated on first use. If neither API key nor
            subscription authentication is available, errors will surface when
            attempting to use the backend.
        """
        # Claude Code SDK doesn't support allowed_tools/disallowed_tools for MCP tools
        # See: https://github.com/anthropics/claude-code/issues/7328
        # Use mcpwrapped to filter tools at protocol level when exclude_file_operation_mcps is True
        if kwargs.get("exclude_file_operation_mcps", False):
            kwargs["use_mcpwrapped_for_tool_filtering"] = True
            logger.info("[ClaudeCodeBackend] Enabling mcpwrapped for MCP tool filtering (exclude_file_operation_mcps=True)")

        # Claude Code SDK uses MCP roots protocol which overrides our command-line paths
        # Use no-roots wrapper to prevent this and ensure both workspace and temp_workspaces are accessible
        # See: MAS-215 - Claude Code agents couldn't access temp_workspaces for voting/evaluation
        kwargs["use_no_roots_wrapper"] = True
        logger.debug("[ClaudeCodeBackend] Enabling no-roots wrapper for MCP filesystem")

        super().__init__(api_key, **kwargs)

        self.api_key = api_key or os.getenv("CLAUDE_CODE_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        self.use_subscription_auth = not bool(self.api_key)

        # Set API key in environment for SDK if provided
        if self.api_key:
            os.environ["ANTHROPIC_API_KEY"] = self.api_key

        # Set git-bash path for Windows compatibility
        if sys.platform == "win32" and not os.environ.get("CLAUDE_CODE_GIT_BASH_PATH"):
            import shutil

            bash_path = shutil.which("bash")
            if bash_path:
                os.environ["CLAUDE_CODE_GIT_BASH_PATH"] = bash_path
                logger.info(f"[ClaudeCodeBackend] Set CLAUDE_CODE_GIT_BASH_PATH={bash_path}")

        # Comprehensive Windows subprocess cleanup warning suppression
        if sys.platform == "win32":
            self._setup_windows_subprocess_cleanup_suppression()

        # Single ClaudeSDKClient for this backend instance
        self._client: Any | None = None  # ClaudeSDKClient
        self._current_session_id: str | None = None

        # Get workspace paths from filesystem manager (required for Claude Code)
        # The filesystem manager handles all workspace setup and management
        if not self.filesystem_manager:
            raise ValueError("Claude Code backend requires 'cwd' configuration for workspace management")

        self._cwd: str = str(Path(str(self.filesystem_manager.get_current_workspace())).resolve())

        self._pending_system_prompt: str | None = None  # Windows-only workaround

        # Track tool_use_id -> tool_name for matching ToolResultBlock to its ToolUseBlock
        # (ToolResultBlock only has tool_use_id, not the tool name)
        self._tool_id_to_name: dict[str, str] = {}
        # Track tool_use_id -> start time for elapsed_seconds calculation
        self._tool_start_times: dict[str, float] = {}

        # Background tool management state (parity with MCP-enabled backends)
        self._background_tool_jobs: dict[str, BackgroundToolJob] = {}
        self._background_tool_tasks: dict[str, asyncio.Task[Any]] = {}
        self._pending_background_tool_results: list[dict[str, Any]] = []
        self._background_tool_wait_seen_ids: set[str] = set()
        self._background_wait_interrupt_provider: Callable[[str], Any] | None = None
        self._background_tool_management_names: set[str] = set(
            BACKGROUND_TOOL_MANAGEMENT_NAMES,
        )
        self._background_mcp_client = None
        self._background_mcp_initialized = False
        self._background_tool_delegate: Any | None = None

        # Custom tools support - initialize ToolManager if custom_tools are provided
        self._custom_tool_manager: ToolManager | None = None
        custom_tools = kwargs.get("custom_tools", [])

        # Register multimodal tools if enabled
        enable_multimodal = self.config.get("enable_multimodal_tools", False) or kwargs.get("enable_multimodal_tools", False)

        # Build multimodal config - priority: explicit multimodal_config > individual config variables
        self._multimodal_config = self.config.get("multimodal_config", {}) or kwargs.get("multimodal_config", {})
        if not self._multimodal_config:
            # Build from individual generation config variables
            self._multimodal_config = {}
            for media_type in ["image", "video", "audio"]:
                backend = self.config.get(f"{media_type}_generation_backend")
                model = self.config.get(f"{media_type}_generation_model")
                if backend or model:
                    self._multimodal_config[media_type] = {}
                    if backend:
                        self._multimodal_config[media_type]["backend"] = backend
                    if model:
                        self._multimodal_config[media_type]["model"] = model

        if enable_multimodal:
            custom_tools = list(custom_tools) + get_multimodal_tool_definitions()
            logger.info("[ClaudeCode] Multimodal tools enabled: read_media, generate_media")

        if custom_tools:
            self._custom_tool_manager = ToolManager()
            self._register_custom_tools(custom_tools)

        # Always register MassGen custom-tool MCP server so background-management
        # helpers are available across all backends (even with zero user tools).
        self._register_massgen_custom_tools_server()

        # Initialize native hook adapter for MassGen hooks integration
        self.__init_native_tool_mixin__()
        self._init_native_hook_adapter(
            "massgen.mcp_tools.native_hook_adapters.ClaudeCodeNativeHookAdapter",
        )

        # Note: _execution_trace is initialized by StreamingBufferMixin
        # and configured with agent_id when _clear_streaming_buffer is called

    def _setup_windows_subprocess_cleanup_suppression(self):
        """Comprehensive Windows subprocess cleanup warning suppression."""
        # All warning filters
        warnings.filterwarnings("ignore", message="unclosed transport")
        warnings.filterwarnings("ignore", message="I/O operation on closed pipe")
        warnings.filterwarnings("ignore", category=ResourceWarning, message="unclosed transport")
        warnings.filterwarnings("ignore", category=ResourceWarning, message="unclosed event loop")
        warnings.filterwarnings("ignore", category=ResourceWarning, message="unclosed <socket.socket")
        warnings.filterwarnings("ignore", category=RuntimeWarning, message="coroutine")
        warnings.filterwarnings("ignore", message="Exception ignored in")
        warnings.filterwarnings("ignore", message="sys:1: ResourceWarning")
        warnings.filterwarnings("ignore", category=ResourceWarning, message="unclosed.*transport.*")
        warnings.filterwarnings("ignore", message=".*BaseSubprocessTransport.*")
        warnings.filterwarnings("ignore", message=".*_ProactorBasePipeTransport.*")
        warnings.filterwarnings("ignore", message=".*Event loop is closed.*")

        # Patch asyncio transport destructors to be silent
        try:
            import asyncio.base_subprocess
            import asyncio.proactor_events

            # Store originals
            original_subprocess_del = getattr(asyncio.base_subprocess.BaseSubprocessTransport, "__del__", None)
            original_pipe_del = getattr(asyncio.proactor_events._ProactorBasePipeTransport, "__del__", None)

            def silent_subprocess_del(self):
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        if original_subprocess_del:
                            original_subprocess_del(self)
                except Exception:
                    pass

            def silent_pipe_del(self):
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        if original_pipe_del:
                            original_pipe_del(self)
                except Exception:
                    pass

            # Apply patches
            if original_subprocess_del:
                asyncio.base_subprocess.BaseSubprocessTransport.__del__ = silent_subprocess_del
            if original_pipe_del:
                asyncio.proactor_events._ProactorBasePipeTransport.__del__ = silent_pipe_del
        except Exception:
            pass  # If patching fails, fall back to warning filters only

        # Setup exit handler for stderr suppression
        original_stderr = sys.stderr

        def suppress_exit_warnings():
            try:
                sys.stderr = open(os.devnull, "w")
                import time

                time.sleep(0.3)
            except Exception:
                pass
            finally:
                try:
                    if sys.stderr != original_stderr:
                        sys.stderr.close()
                    sys.stderr = original_stderr
                except Exception:
                    pass

        atexit.register(suppress_exit_warnings)

    def get_provider_name(self) -> str:
        """Get the name of this provider."""
        return "claude_code"

    def get_filesystem_support(self) -> FilesystemSupport:
        """Claude Code uses native tools (Read, Write, Edit, Bash, etc.) for filesystem ops.

        Native tools are protected by OS-level sandbox (Seatbelt/macOS,
        bubblewrap/Linux) and PathPermissionManager hooks. MCP filesystem/
        command_line servers are not injected; workspace_tools MCP is injected
        separately for media generation capabilities.
        """
        return FilesystemSupport.NATIVE

    def has_native_execution_sandbox(self) -> bool:
        """Claude Code confines its own execution via its OS-level sandbox."""
        return True

    def is_stateful(self) -> bool:
        """
        Claude Code backend is stateful - maintains conversation context.

        Returns:
            True - Claude Code maintains server-side session state
        """
        return True

    # supports_native_hooks(), get_native_hook_adapter(), set_native_hooks_config()
    # are provided by NativeToolBackendMixin

    def get_disallowed_tools(self, config: dict[str, Any]) -> list[str]:
        """Return native Claude Code tools to disable.

        Most native tools (Read, Write, Edit, etc.) are kept enabled,
        with security enforced by PathPermissionManager hooks and OS-level
        sandbox (local) or container isolation (Docker).

        Bash handling:
        - Disabled by default (safe default when no MCP command_line configured)
        - Enabled if enable_mcp_command_line=true (local mode - native Bash works)
        - Disabled if docker mode (must use execute_command MCP instead)

        Args:
            config: Backend config dict.

        Returns:
            List of tool names/patterns to disable via SDK disallowed_tools.
        """
        disallowed = [
            # Security restrictions (dangerous bash patterns)
            "Bash(rm*)",
            "Bash(sudo*)",
            "Bash(su*)",
            "Bash(chmod*)",
            "Bash(chown*)",
            # Not useful in MassGen context
            "Task",  # we have our own version of subagents
            "TodoWrite",
            "ExitPlanMode",
            "Skill",  # agents read skill files directly; Skill tool misused by weaker models
            "mcp__ide__getDiagnostics",
            "mcp__ide__executeCode",
        ]

        # Bash handling: disabled by default, enabled for local MCP mode, disabled for docker
        enable_mcp_command_line = config.get("enable_mcp_command_line", False)
        command_line_execution_mode = config.get("command_line_execution_mode", "local")

        if not enable_mcp_command_line:
            # No MCP command line configured - disable native Bash (safe default)
            disallowed.append("Bash")
        elif command_line_execution_mode == "docker":
            # Docker mode - must use execute_command MCP, disable native Bash
            disallowed.append("Bash")
        # else: enable_mcp_command_line=true + local mode - keep native Bash enabled

        # Conditionally keep web tools
        if not config.get("enable_web_search", False):
            disallowed.extend(["WebSearch", "WebFetch"])

        return disallowed

    def get_tool_category_overrides(self) -> dict[str, str]:
        """Return tool category overrides for Claude Code.

        Claude Code has native tools for filesystem, command execution, file search,
        web search, and planning. MassGen overrides the native Task tool with its
        own subagent spawning.
        """
        return {
            "filesystem": "skip",  # Native: Read, Write, Edit, MultiEdit, Glob, Grep, LS
            "command_execution": "skip",  # Native: Bash
            "file_search": "skip",  # Native: Grep, Glob
            "web_search": "skip",  # Native: WebSearch, WebFetch
            "planning": "skip",  # Native: EnterPlanMode, ExitPlanMode, TodoWrite
            "subagents": "override",  # Override native Task with MassGen spawn_subagents
        }

    def _get_execution_trace_hooks(self) -> dict[str, list[Any]]:
        """Create SDK hooks that capture tool executions for the execution trace.

        Returns:
            Dictionary with PreToolUse and PostToolUse hook configurations
        """
        from claude_agent_sdk import HookMatcher

        # Store pending tool calls to correlate with results
        self._pending_tool_calls: dict[str, dict[str, Any]] = {}

        async def pre_tool_use_hook(input_data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict[str, Any]:
            """Capture tool call before execution."""
            if self._execution_trace and input_data.get("hook_event_name") == "PreToolUse":
                tool_name = input_data.get("tool_name", "unknown")
                tool_input = input_data.get("tool_input", {})

                # Record the tool call
                self._execution_trace.add_tool_call(name=tool_name, args=tool_input)

                # Store for correlation with result
                if tool_use_id:
                    self._pending_tool_calls[tool_use_id] = {
                        "name": tool_name,
                        "input": tool_input,
                    }

                logger.debug(f"[ClaudeCodeBackend] Trace captured tool call: {tool_name}")

            # Return empty to allow the operation
            return {}

        async def post_tool_use_hook(input_data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict[str, Any]:
            """Capture tool result after execution."""
            if self._execution_trace and input_data.get("hook_event_name") == "PostToolUse":
                tool_name = input_data.get("tool_name", "unknown")
                tool_response = input_data.get("tool_response", "")

                # Convert response to string if needed
                if isinstance(tool_response, dict):
                    result_str = json.dumps(tool_response)
                else:
                    result_str = str(tool_response) if tool_response else ""

                # Record the tool result
                self._execution_trace.add_tool_result(
                    name=tool_name,
                    result=result_str,
                    is_error=False,  # PostToolUse is only for successful calls
                )

                # Clean up pending call
                if tool_use_id and tool_use_id in self._pending_tool_calls:
                    del self._pending_tool_calls[tool_use_id]

                logger.debug(f"[ClaudeCodeBackend] Trace captured tool result: {tool_name}")

            return {}

        return {
            "PreToolUse": [HookMatcher(hooks=[pre_tool_use_hook])],
            "PostToolUse": [HookMatcher(hooks=[post_tool_use_hook])],
        }

    async def _setup_code_based_tools_symlinks(self) -> None:
        """Setup symlinks to shared code-based tools if they already exist.

        This is called for ClaudeCodeBackend after client connection since it doesn't
        directly manage MCP clients like OpenAI backend does. If another backend has
        already generated the shared tools, this creates the necessary symlinks.
        """
        if not self.filesystem_manager.shared_tools_base:
            # No shared tools configured - tools are per-agent
            return

        # Compute the hash of our MCP configuration to find the shared tools path
        # We need to extract tool schemas to compute the hash, but we don't have direct
        # MCP client access. Instead, check if shared tools directory already exists.
        from pathlib import Path

        shared_tools_base = Path(self.filesystem_manager.shared_tools_base)
        if not shared_tools_base.exists():
            # No shared tools generated yet
            return

        # Find hash subdirectories in shared_tools_base
        # In a multi-agent setup, agent_a will have generated tools, so we look for existing hash dirs
        hash_dirs = [d for d in shared_tools_base.iterdir() if d.is_dir()]

        if not hash_dirs:
            # No hash directories found
            return

        # Use the first (and typically only) hash directory
        # In multi-agent setups with same MCP config, there should be exactly one hash dir
        target_path = hash_dirs[0]

        # Check if tools exist in this directory
        if (target_path / "servers").exists() and (target_path / ".mcp").exists():
            # Set shared_tools_directory and create symlinks
            self.filesystem_manager.shared_tools_directory = target_path
            self.filesystem_manager._add_shared_tools_to_allowed_paths(target_path)
            logger.info(f"[ClaudeCodeBackend] Created symlinks to existing shared tools: {target_path}")

    async def clear_history(self) -> None:
        """
        Clear Claude Code conversation history while preserving session.

        Uses the /clear slash command to clear conversation history without
        destroying the session, working directory, or other session state.
        """
        if self._client is None:
            # No active session to clear
            return

        try:
            # Send /clear command to clear history while preserving session
            await self._client.query("/clear")

            # The /clear command should preserve:
            # - Session ID
            # - Working directory
            # - Tool availability
            # - Permission settings
            # While clearing only the conversation history

        except Exception as e:
            # Fallback to full reset if /clear command fails
            logger.warning(f"/clear command failed ({e}), falling back to full reset")
            await self.reset_state()

    async def reset_state(self) -> None:
        """
        Reset Claude Code backend state.

        Properly disconnects and clears the current session and client connection to start fresh.

        Note: The Claude Agent SDK's disconnect() closes its anyio task group, which
        delivers cancellation to whatever asyncio task the cancel scope was bound to.
        In our architecture, anyio binds to the event loop's root task (the coordination
        task), so disconnect() inadvertently cancels the entire coordination. We reverse
        this by uncancelling any affected tasks after disconnect.
        """
        await self._cancel_all_background_tool_jobs()

        if self._client is not None:
            try:
                await self._client.disconnect()
            except asyncio.CancelledError:
                pass  # anyio cancel scope may raise CancelledError
            except Exception:
                pass  # Ignore cleanup errors

            # anyio's cancel scope propagation may have called task.cancel() on
            # parent tasks during disconnect(). Reverse any pending cancellations
            # to prevent killing the coordination loop.
            for task in asyncio.all_tasks():
                if not task.done() and task.cancelling() > 0:
                    task.uncancel()

        self._client = None
        self._current_session_id = None
        self._tool_id_to_name.clear()

    def update_token_usage_from_result_message(self, result_message) -> None:
        """Update token usage from Claude Code ResultMessage.

        Extracts actual token usage and cost data from Claude Code server
        response. This is more accurate than estimation-based methods.

        Args:
            result_message: ResultMessage from Claude Code with usage data
        """
        # Check if we have a valid ResultMessage
        if ResultMessage is not None and not isinstance(result_message, ResultMessage):
            return
        # Fallback: check if it has the expected attributes (for SDK compatibility)
        if not hasattr(result_message, "usage") or not hasattr(result_message, "total_cost_usd"):
            return

        # Extract usage information from ResultMessage
        if result_message.usage:
            usage_data = result_message.usage

            # Claude Code SDK returns:
            # - input_tokens: NEW uncached input tokens only
            # - cache_read_input_tokens: Tokens read from prompt cache (cache hits)
            # - cache_creation_input_tokens: Tokens written to prompt cache
            # Total input = input_tokens + cache_read + cache_creation

            if isinstance(usage_data, dict):
                # Base input tokens (uncached)
                base_input = usage_data.get("input_tokens", 0) or 0
                # Cache tokens
                cache_read = usage_data.get("cache_read_input_tokens", 0) or 0
                cache_creation = usage_data.get("cache_creation_input_tokens", 0) or 0
                # Total input is sum of all input-related tokens
                input_tokens = base_input + cache_read + cache_creation
                output_tokens = usage_data.get("output_tokens", 0) or 0
            else:
                # Object format - use getattr
                base_input = getattr(usage_data, "input_tokens", 0) or 0
                cache_read = getattr(usage_data, "cache_read_input_tokens", 0) or 0
                cache_creation = getattr(usage_data, "cache_creation_input_tokens", 0) or 0
                input_tokens = base_input + cache_read + cache_creation
                output_tokens = getattr(usage_data, "output_tokens", 0) or 0

            logger.info(
                f"[ClaudeCode] Token usage: input={input_tokens} " f"(base={base_input}, cache_read={cache_read}, cache_create={cache_creation}), " f"output={output_tokens}",
            )

            # Update cumulative tracking
            self.token_usage.input_tokens += input_tokens
            self.token_usage.output_tokens += output_tokens
            # Track cached tokens separately for detailed breakdown
            self.token_usage.cached_input_tokens += cache_read

        # Use actual cost from Claude Code (preferred over calculation)
        if result_message.total_cost_usd is not None:
            self.token_usage.estimated_cost += result_message.total_cost_usd
        else:
            # Fallback: calculate cost with litellm if not provided
            if result_message.usage:
                cost = self.token_calculator.calculate_cost_with_usage_object(
                    model=self.model,
                    usage=result_message.usage,
                    provider=self.get_provider_name(),
                )
                self.token_usage.estimated_cost += cost

    def update_token_usage(self, messages: list[dict[str, Any]], response_content: str, model: str):
        """Update token usage tracking (fallback method).

        Only used when no ResultMessage available. Provides estimated token
        tracking for compatibility with base class interface. Should only be
        called when ResultMessage data is not available.

        Args:
            messages: List of conversation messages
            response_content: Generated response content
            model: Model name for cost calculation
        """
        # This method should only be called when we don't have a
        # ResultMessage. It provides estimated tracking for compatibility
        # with base class interface

        # Estimate input tokens from messages
        input_text = "\n".join([msg.get("content", "") for msg in messages])
        input_tokens = self.estimate_tokens(input_text)

        # Estimate output tokens from response
        output_tokens = self.estimate_tokens(response_content)

        # Update totals
        self.token_usage.input_tokens += input_tokens
        self.token_usage.output_tokens += output_tokens

        # Calculate estimated cost (no ResultMessage available)
        cost = self.calculate_cost(input_tokens, output_tokens, model, result_message=None)
        self.token_usage.estimated_cost += cost

    def _resolve_skill_source(self) -> Path | None:
        """Resolve the best available skills source directory, if any."""
        fm = self.filesystem_manager
        if fm is not None:
            docker_manager = getattr(fm, "docker_manager", None)
            agent_id = getattr(self, "_current_agent_id", None) or getattr(fm, "agent_id", None)
            temp_skills_dirs = getattr(docker_manager, "temp_skills_dirs", None) if docker_manager else None
            if isinstance(temp_skills_dirs, dict) and agent_id in temp_skills_dirs:
                source = Path(temp_skills_dirs[agent_id])
                if source.exists():
                    return source

            local_skills_directory = getattr(fm, "local_skills_directory", None)
            if local_skills_directory:
                source = Path(local_skills_directory)
                if source.exists():
                    return source

        project_skills = Path(self._cwd) / ".agent" / "skills"
        if project_skills.exists():
            return project_skills

        home_skills = Path.home() / ".agent" / "skills"
        if home_skills.exists():
            return home_skills

        return None

    def _sync_skills_into_workspace(self, workspace_path: Path) -> None:
        """Copy discovered skills into workspace/.agent/skills for direct reading.

        Also creates a .claude/skills symlink pointing to .agent/skills so both
        conventional paths resolve to the same location.
        """
        source = self._resolve_skill_source()
        if source is None:
            return

        # Primary location: .agent/skills/
        agent_dir = workspace_path / ".agent"
        dest = agent_dir / "skills"
        dest.mkdir(parents=True, exist_ok=True)

        try:
            if source.resolve() == dest.resolve():
                return
        except OSError:
            pass

        copied_entries = 0
        try:
            for entry in source.iterdir():
                target = dest / entry.name
                if entry.is_dir():
                    shutil.copytree(entry, target, dirs_exist_ok=True)
                    copied_entries += 1
                elif entry.is_file():
                    shutil.copy2(entry, target)
                    copied_entries += 1
        except OSError as e:
            logger.warning(f"Claude Code skills sync failed from {source} to {dest}: {e}")
            return

        if copied_entries:
            logger.info(f"[ClaudeCodeBackend] Skills sync copied {copied_entries} entries from {source} to {dest}")

        # Symlink .claude/skills -> .agent/skills
        claude_skills = workspace_path / ".claude" / "skills"
        try:
            if claude_skills.is_symlink() or claude_skills.exists():
                if claude_skills.is_symlink():
                    claude_skills.unlink()
                elif claude_skills.is_dir():
                    shutil.rmtree(claude_skills)
            claude_skills.parent.mkdir(parents=True, exist_ok=True)
            claude_skills.symlink_to(dest)
        except OSError as e:
            logger.warning(f"Claude Code .claude/skills symlink failed: {e}")

    def get_supported_builtin_tools(self, enable_web_search: bool = False) -> list[str]:
        """Get list of builtin tools supported by Claude Code.

        Returns only tools that MassGen doesn't have native equivalents for.
        MassGen has native implementations for: read_file_content, save_file_content,
        append_file_content, run_shell_script, list_directory, and will add
        grep/glob tools (see issue 640).

        Args:
            enable_web_search: If True, include WebSearch and WebFetch tools.

        Returns:
            List of tool names that should be enabled for Claude Code.
        """
        tools: list[str] = []

        if enable_web_search:
            tools.extend(["WebSearch", "WebFetch"])

        return tools

    # Known tools for well-known MCP servers (used for tool filtering)
    # NOTE: Claude Code SDK does NOT support filtering MCP tools via allowed_tools/disallowed_tools.
    # These only work for built-in tools (Read, Write, Bash, etc.), not MCP tools.
    # See: https://github.com/anthropics/claude-code/issues/7328
    # Workaround options:
    # 1. Use mcp-remote with --ignore-tool to proxy and filter tools
    # 2. Don't add MCP servers with unwanted tools
    # 3. Accept that tools are visible but use disallowed_tools to block execution
    KNOWN_SERVER_TOOLS = {
        "filesystem": [
            "read_file",
            "read_text_file",
            "read_multiple_files",
            "write_file",
            "edit_file",
            "create_directory",
            "list_directory",
            "directory_tree",
            "move_file",
            "copy_file",
            "delete_file",
            "search_files",
            "get_file_info",
            "list_allowed_directories",
        ],
        "workspace_tools": [
            "read_file_content",
            "save_file_content",
            "append_file_content",
            "list_directory",
            "create_directory",
            "copy_file",
            "move_file",
            "delete_file",
            "compare_files",
            "text_to_image_generation",
            "text_to_audio_generation",
        ],
        "command_line": [
            "execute_command",
        ],
    }

    def _get_all_tools_for_server(self, server_name: str) -> list[str]:
        """Get all known tools for a server, prefixed with mcp__{server}__.

        Used when we need to explicitly list all tools (fallback when wildcards not supported).
        Handles both exact server names and pattern-based names (e.g., planning_agent_a).

        Args:
            server_name: Name of the MCP server

        Returns:
            List of prefixed tool names, or empty list if server is unknown
        """
        # Check for exact match first
        tools = self.KNOWN_SERVER_TOOLS.get(server_name)
        if tools:
            return [f"mcp__{server_name}__{tool}" for tool in tools]

        # Check for pattern-based servers (e.g., planning_agent_a -> planning)
        # These are dynamically named servers with predictable tool sets
        DYNAMIC_SERVER_PATTERNS = {
            "planning_": [
                "create_task_plan",
                "update_task_status",
                "get_task_status",
                "get_all_tasks",
                "add_task",
                "remove_task",
                "clear_completed",
            ],
            "memory_": [
                "save_memory",
                "load_memory",
                "list_memories",
                "delete_memory",
            ],
        }

        for prefix, pattern_tools in DYNAMIC_SERVER_PATTERNS.items():
            if server_name.startswith(prefix):
                return [f"mcp__{server_name}__{tool}" for tool in pattern_tools]

        return []

    def get_current_session_id(self) -> str | None:
        """Get current session ID from server-side session management.

        Returns:
            Current session ID if available, None otherwise
        """
        return self._current_session_id

    # TODO (v0.0.14 Context Sharing Enhancement - See docs/dev_notes/v0.0.14-context.md):
    # Add permission enforcement methods:
    # def execute_with_permissions(self, operation, path):
    #     """Execute operation only if permissions allow.
    #
    #     Args:
    #         operation: The operation to execute (e.g., tool call)
    #         path: The file/directory path being accessed
    #
    #     Raises:
    #         PermissionError: If agent lacks required access
    #     """
    #     if not self.check_permission(path, operation.type):
    #         raise PermissionError(f"Agent {self.agent_id} lacks {operation.type} access to {path}")
    #
    # def check_permission(self, path: str, access_type: str) -> bool:
    #     """Check if current agent has permission for path access."""
    #     # Will integrate with PermissionManager
    #     pass

    def _register_custom_tools(self, custom_tools: list[dict[str, Any]]) -> None:
        """Register custom tools with the tool manager.

        Supports flexible configuration:
        - function: str | List[str]
        - description: str (shared) | List[str] (1-to-1 mapping)
        - preset_args: dict (shared) | List[dict] (1-to-1 mapping)

        Examples:
            # Single function
            function: "my_func"
            description: "My description"

            # Multiple functions with shared description
            function: ["func1", "func2"]
            description: "Shared description"

            # Multiple functions with individual descriptions
            function: ["func1", "func2"]
            description: ["Description 1", "Description 2"]

            # Multiple functions with mixed (shared desc, individual args)
            function: ["func1", "func2"]
            description: "Shared description"
            preset_args: [{"arg1": "val1"}, {"arg1": "val2"}]

        Args:
            custom_tools: List of custom tool configurations
        """
        if not self._custom_tool_manager:
            logger.warning("Custom tool manager not initialized, cannot register tools")
            return

        # Collect unique categories and create them if needed
        categories = set()
        for tool_config in custom_tools:
            if isinstance(tool_config, dict):
                category = tool_config.get("category", "default")
                if category != "default":
                    categories.add(category)

        # Create categories that don't exist
        for category in categories:
            if category not in self._custom_tool_manager.tool_categories:
                self._custom_tool_manager.setup_category(
                    category_name=category,
                    description=f"Custom {category} tools",
                    enabled=True,
                )

        # Register each custom tool
        for tool_config in custom_tools:
            try:
                if isinstance(tool_config, dict):
                    # Extract base configuration
                    path = tool_config.get("path")
                    category = tool_config.get("category", "default")

                    # Normalize function field to list
                    func_field = tool_config.get("function")
                    if isinstance(func_field, str):
                        functions = [func_field]
                    elif isinstance(func_field, list):
                        functions = func_field
                    else:
                        logger.error(
                            f"Invalid function field type: {type(func_field)}. " f"Must be str or List[str].",
                        )
                        continue

                    if not functions:
                        logger.error("Empty function list in tool config")
                        continue

                    num_functions = len(functions)

                    # Process name field (can be str or List[str])
                    name_field = tool_config.get("name")
                    names = self._process_field_for_functions(
                        name_field,
                        num_functions,
                        "name",
                    )
                    if names is None:
                        continue  # Validation error, skip this tool

                    # Process description field (can be str or List[str])
                    desc_field = tool_config.get("description")
                    descriptions = self._process_field_for_functions(
                        desc_field,
                        num_functions,
                        "description",
                    )
                    if descriptions is None:
                        continue  # Validation error, skip this tool

                    # Process preset_args field (can be dict or List[dict])
                    preset_field = tool_config.get("preset_args")
                    preset_args_list = self._process_field_for_functions(
                        preset_field,
                        num_functions,
                        "preset_args",
                    )
                    if preset_args_list is None:
                        continue  # Validation error, skip this tool

                    # Register each function with its corresponding values
                    for i, func in enumerate(functions):
                        # Load the function first if custom name is needed
                        if names[i] and names[i] != func:
                            # Need to load function and apply custom name
                            if path:
                                loaded_func = self._custom_tool_manager._load_function_from_path(path, func)
                            else:
                                loaded_func = self._custom_tool_manager._load_builtin_function(func)

                            if loaded_func is None:
                                logger.error(f"Could not load function '{func}' from path: {path}")
                                continue

                            # Apply custom name by modifying __name__ attribute
                            loaded_func.__name__ = names[i]

                            # Register with loaded function (no path needed)
                            self._custom_tool_manager.add_tool_function(
                                path=None,
                                func=loaded_func,
                                category=category,
                                preset_args=preset_args_list[i],
                                description=descriptions[i],
                            )
                        else:
                            # No custom name or same as function name, use normal registration
                            self._custom_tool_manager.add_tool_function(
                                path=path,
                                func=func,
                                category=category,
                                preset_args=preset_args_list[i],
                                description=descriptions[i],
                            )

                        # Use custom name for logging if provided
                        registered_name = names[i] if names[i] else func
                        logger.info(
                            f"Registered custom tool: {registered_name} from {path} " f"(category: {category}, " f"desc: '{descriptions[i][:50] if descriptions[i] else 'None'}...')",
                        )

            except Exception as e:
                func_name = tool_config.get("function", "unknown")
                logger.error(
                    f"Failed to register custom tool {func_name}: {e}",
                    exc_info=True,
                )

    def _process_field_for_functions(
        self,
        field_value: Any,
        num_functions: int,
        field_name: str,
    ) -> list[Any] | None:
        """Process a config field that can be a single value or list.

        Conversion rules:
        - None → [None, None, ...] (repeated num_functions times)
        - Single value (not list) → [value, value, ...] (shared)
        - List with matching length → use as-is (1-to-1 mapping)
        - List with wrong length → ERROR (return None)

        Args:
            field_value: The field value from config
            num_functions: Number of functions being registered
            field_name: Name of the field (for error messages)

        Returns:
            List of values (one per function), or None if validation fails

        Examples:
            _process_field_for_functions(None, 3, "desc")
            → [None, None, None]

            _process_field_for_functions("shared", 3, "desc")
            → ["shared", "shared", "shared"]

            _process_field_for_functions(["a", "b", "c"], 3, "desc")
            → ["a", "b", "c"]

            _process_field_for_functions(["a", "b"], 3, "desc")
            → None (error logged)
        """
        # Case 1: None or missing field → use None for all functions
        if field_value is None:
            return [None] * num_functions

        # Case 2: Single value (not a list) → share across all functions
        if not isinstance(field_value, list):
            return [field_value] * num_functions

        # Case 3: List value → must match function count exactly
        if len(field_value) == num_functions:
            return field_value
        else:
            # Length mismatch → validation error
            logger.error(
                f"Configuration error: {field_name} is a list with "
                f"{len(field_value)} items, but there are {num_functions} functions. "
                f"Either use a single value (shared) or a list with exactly "
                f"{num_functions} items (1-to-1 mapping).",
            )
            return None

    def _register_massgen_custom_tools_server(self) -> None:
        """Register/update SDK MCP server exposing MassGen custom tools."""
        sdk_mcp_server = self._create_sdk_mcp_server_from_custom_tools()
        if not sdk_mcp_server:
            return

        if "mcp_servers" not in self.config:
            self.config["mcp_servers"] = {}

        if isinstance(self.config["mcp_servers"], dict):
            self.config["mcp_servers"]["massgen_custom_tools"] = sdk_mcp_server
        elif isinstance(self.config["mcp_servers"], list):
            replaced = False
            for server in self.config["mcp_servers"]:
                if isinstance(server, dict) and server.get("name") == "massgen_custom_tools":
                    server["__sdk_server__"] = sdk_mcp_server
                    replaced = True
                    break
            if not replaced:
                self.config["mcp_servers"].append(
                    {
                        "name": "massgen_custom_tools",
                        "__sdk_server__": sdk_mcp_server,
                    },
                )
        else:
            self.config["mcp_servers"] = {"massgen_custom_tools": sdk_mcp_server}

        logger.info(
            "[ClaudeCodeBackend] Registered SDK MCP server with %s MassGen tool(s)",
            len(self._get_massgen_custom_tool_schemas()),
        )

    def _get_massgen_custom_tool_schemas(self) -> list[dict[str, Any]]:
        """Return user custom-tool schemas plus internal background management tools."""
        schemas: list[dict[str, Any]] = []
        if self._custom_tool_manager:
            schemas.extend(self._custom_tool_manager.fetch_tool_schemas())
        schemas.extend(self._get_background_tool_management_schemas())
        return schemas

    @staticmethod
    def _build_background_management_schema(
        name: str,
        description: str,
        properties: dict[str, Any],
        required: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create OpenAI function schema for internal background management tools."""
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required or [],
                },
            },
        }

    def _get_background_tool_management_schemas(self) -> list[dict[str, Any]]:
        """Schemas for lifecycle management of background tool jobs."""
        return [
            self._build_background_management_schema(
                name=BACKGROUND_TOOL_START_NAME,
                description=(
                    "Start any custom or MCP tool in the background and return a job_id "
                    "for polling or cancellation. You can provide target arguments via "
                    "`arguments` (or `args`), or pass them as top-level fields."
                ),
                properties={
                    "tool_name": {
                        "type": "string",
                        "description": "Exact tool name to run (custom_tool__* or mcp__*).",
                    },
                    "tool": {
                        "type": "string",
                        "description": "Alias for tool_name.",
                    },
                    "arguments": {
                        "type": "object",
                        "description": "Arguments for the target tool.",
                        "default": {},
                    },
                    "args": {
                        "type": "object",
                        "description": "Alias for arguments.",
                        "default": {},
                    },
                },
                required=[],
            ),
            self._build_background_management_schema(
                name=BACKGROUND_TOOL_STATUS_NAME,
                description="Get lightweight status for a background tool job.",
                properties={
                    "job_id": {
                        "type": "string",
                        "description": "Background job identifier returned by start_background_tool.",
                    },
                },
                required=["job_id"],
            ),
            self._build_background_management_schema(
                name=BACKGROUND_TOOL_RESULT_NAME,
                description="Get the current or final result payload for a background tool job.",
                properties={
                    "job_id": {
                        "type": "string",
                        "description": "Background job identifier returned by start_background_tool.",
                    },
                },
                required=["job_id"],
            ),
            self._build_background_management_schema(
                name=BACKGROUND_TOOL_WAIT_NAME,
                description=("Block until the next unseen background tool job reaches a terminal " "state or the timeout elapses."),
                properties={
                    "timeout_seconds": {
                        "type": "number",
                        "description": ("Maximum seconds to wait for a completed background job. " "Default: 30."),
                        "default": BACKGROUND_TOOL_WAIT_DEFAULT_TIMEOUT_SECONDS,
                    },
                },
            ),
            self._build_background_management_schema(
                name=BACKGROUND_TOOL_CANCEL_NAME,
                description="Cancel a running background tool job.",
                properties={
                    "job_id": {
                        "type": "string",
                        "description": "Background job identifier returned by start_background_tool.",
                    },
                },
                required=["job_id"],
            ),
            self._build_background_management_schema(
                name=BACKGROUND_TOOL_LIST_NAME,
                description=("List background tool jobs. By default returns only currently running jobs; " "set include_all=true to include completed/error/cancelled history."),
                properties={
                    "include_all": {
                        "type": "boolean",
                        "description": "Include terminal jobs (completed/error/cancelled). Default false.",
                        "default": False,
                    },
                },
            ),
        ]

    async def _execute_massgen_custom_tool(
        self,
        tool_name: str,
        args: dict,
        *,
        force_foreground: bool = False,
    ) -> dict:
        """Execute a MassGen custom tool and convert result to MCP format.

        Args:
            tool_name: Name of the custom tool to execute
            args: Arguments for the tool
            force_foreground: When True, bypass auto-background dispatch and
                execute the tool directly in this call context.

        Returns:
            MCP-formatted response with content blocks
        """
        if tool_name in self._background_tool_management_names:
            management_result = await self._execute_background_management_tool(
                tool_name=tool_name,
                arguments=args or {},
            )
            return {
                "content": [
                    {"type": "text", "text": json.dumps(management_result)},
                ],
            }

        try:
            parsed_args, decode_passes = normalize_json_object_argument(
                args,
                field_name="arguments",
            )
        except ValueError as exc:
            payload = {
                "success": False,
                "error": str(exc),
            }
            return {
                "content": [
                    {"type": "text", "text": json.dumps(payload)},
                ],
            }
        if decode_passes > 1:
            logger.info(
                "[ClaudeCode] Normalized %s decode passes for %s arguments",
                decode_passes,
                tool_name,
            )
        auto_background = False
        if not force_foreground:
            auto_background = self._should_auto_background_execution(tool_name, parsed_args)
        if auto_background:
            background_args = self._strip_background_control_args(
                parsed_args,
                tool_name=tool_name,
            )
            try:
                background_job = await self._start_background_tool_job(
                    tool_name=tool_name,
                    arguments=background_args,
                )
                payload = {
                    "success": True,
                    "status": "background",
                    "job_id": background_job.job_id,
                    "tool_name": background_job.tool_name,
                    "message": f"{background_job.tool_name} is running in background",
                }
            except Exception as e:  # noqa: BLE001
                payload = {
                    "success": False,
                    "error": f"Error starting background execution for {tool_name}: {e}",
                }

            return {
                "content": [
                    {"type": "text", "text": json.dumps(payload)},
                ],
            }

        # Media tools default to background mode, so explicit foreground
        # overrides may include control args (for example background=false).
        # Strip these before direct execution.
        if self._is_default_media_background_tool(tool_name):
            parsed_args = self._strip_background_control_args(
                parsed_args,
                tool_name=tool_name,
            )

        if not self._custom_tool_manager:
            return {
                "content": [
                    {"type": "text", "text": "Error: Custom tool manager not initialized"},
                ],
            }

        # Build execution context for context param injection
        # The tool manager will only inject params that match @context_params decorator
        execution_context = {}
        if hasattr(self, "_execution_context") and self._execution_context:
            try:
                execution_context = self._execution_context.model_dump()
            except Exception:
                execution_context = {}

        task_context = None
        if self.filesystem_manager and self.filesystem_manager.cwd:
            from massgen.context.task_context import load_task_context

            task_context = load_task_context(
                str(self.filesystem_manager.cwd),
                required=False,
            )

        execution_context.setdefault("backend_name", self.get_provider_name())
        execution_context.setdefault(
            "backend_type",
            normalize_backend_type(self.get_provider_name()),
        )
        execution_context.setdefault("model", self.config.get("model", ""))
        execution_context.setdefault("current_stage", self.coordination_stage)
        if task_context is not None:
            execution_context["task_context"] = task_context

        # Ensure agent_cwd is always available for custom tools
        # Use filesystem_manager's cwd which is set to the agent's workspace
        if self.filesystem_manager:
            execution_context["agent_cwd"] = str(self.filesystem_manager.cwd)
            # Also add allowed_paths for path validation
            if hasattr(self.filesystem_manager, "path_permission_manager") and self.filesystem_manager.path_permission_manager:
                paths = self.filesystem_manager.path_permission_manager.get_mcp_filesystem_paths()
                if paths:
                    execution_context["allowed_paths"] = paths

        # Add multimodal_config for read_media/generate_media tools
        if hasattr(self, "_multimodal_config") and self._multimodal_config:
            execution_context["multimodal_config"] = self._multimodal_config

        tool_request = {
            "name": tool_name,
            "input": parsed_args,
        }

        # Add observability context (agent_id, round tracking)
        execution_context["agent_id"] = getattr(self, "_current_agent_id", None) or "unknown"
        # Add round tracking from context variable (set by orchestrator via set_current_round)
        round_number, round_type = get_current_round()
        if round_number is not None:
            execution_context["round_number"] = round_number
        if round_type:
            execution_context["round_type"] = round_type

        result_text = ""
        try:
            async for result in self._custom_tool_manager.execute_tool(
                tool_request,
                execution_context=execution_context,
            ):
                # Accumulate ExecutionResult blocks
                if hasattr(result, "output_blocks"):
                    for block in result.output_blocks:
                        if hasattr(block, "data"):
                            result_text += str(block.data)
                        elif hasattr(block, "content"):
                            result_text += str(block.content)
                elif hasattr(result, "content"):
                    result_text += str(result.content)
                else:
                    result_text += str(result)
        except Exception as e:
            logger.error(f"Error executing custom tool {tool_name}: {e}")
            result_text = f"Error: {str(e)}"

        # Return MCP format response
        return {
            "content": [
                {"type": "text", "text": result_text or "Tool executed successfully"},
            ],
        }

    def _is_background_management_tool(self, tool_name: str) -> bool:
        """Return whether a tool name is one of the internal background helpers."""
        return tool_name in self._background_tool_management_names

    @staticmethod
    def _normalize_background_target_tool_name(tool_name: str) -> str:
        """Normalize target names passed to background start requests."""
        normalized = (tool_name or "").strip()
        massgen_prefix = "mcp__massgen_custom_tools__"
        if normalized.startswith(massgen_prefix):
            normalized = normalized[len(massgen_prefix) :]
        return normalized

    def _mcp_tool_declares_argument(self, tool_name: str, argument_name: str) -> bool:
        """Return True when a known MCP tool schema declares an argument."""
        clients = [
            getattr(self, "_mcp_client", None),
            getattr(self, "_background_mcp_client", None),
        ]
        for client in clients:
            tools = getattr(client, "tools", None)
            if not isinstance(tools, dict) or tool_name not in tools:
                continue
            tool = tools[tool_name]
            schema = getattr(tool, "inputSchema", None)
            if not isinstance(schema, dict):
                schema = getattr(tool, "parameters", None)
            if not isinstance(schema, dict):
                continue
            properties = schema.get("properties")
            if isinstance(properties, dict) and argument_name in properties:
                return True
        return False

    def _strip_background_control_args(
        self,
        arguments: dict[str, Any],
        *,
        tool_name: str | None = None,
    ) -> dict[str, Any]:
        """Remove synthetic background control flags before dispatching target tools."""
        cleaned = dict(arguments)
        preserve_background = bool(tool_name) and self._mcp_tool_declares_argument(tool_name, "background")
        preserve_run_in_background = bool(tool_name) and self._mcp_tool_declares_argument(tool_name, "run_in_background")
        preserve_mode = bool(tool_name) and self._mcp_tool_declares_argument(tool_name, "mode")

        if not preserve_background and isinstance(cleaned.get("background"), bool):
            cleaned.pop("background", None)
        if not preserve_run_in_background and isinstance(cleaned.get("run_in_background"), bool):
            cleaned.pop("run_in_background", None)
        mode = cleaned.get("mode")
        if not preserve_mode and isinstance(mode, str) and mode.lower() in {"background"}:
            cleaned.pop("mode", None)
        return cleaned

    @staticmethod
    def _is_default_media_background_tool(tool_name: str) -> bool:
        """Return True for media tools that should default to background execution."""
        normalized = (tool_name or "").strip()
        normalized = ClaudeCodeBackend._normalize_background_target_tool_name(normalized)
        return normalized in {
            "read_media",
            "generate_media",
            "custom_tool__read_media",
            "custom_tool__generate_media",
        }

    @staticmethod
    def _is_explicit_foreground_request(arguments: dict[str, Any]) -> bool:
        """Return True when args explicitly request foreground/blocking behavior."""
        if arguments.get("background") is False:
            return True
        if arguments.get("run_in_background") is False:
            return True
        return False

    def _should_auto_background_execution(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> bool:
        """Return True when this tool call should be started in background mode."""
        if self._is_background_management_tool(tool_name):
            return False
        if tool_name in {"new_answer", "vote", "stop"}:
            return False
        if not isinstance(arguments, dict):
            return False

        if self._is_explicit_foreground_request(arguments):
            return False
        if self._is_default_media_background_tool(tool_name):
            return True

        # If the target MCP tool natively defines background controls, keep
        # execution in foreground and let that tool own the behavior (for
        # example spawn_subagents(background=True)).
        if self._mcp_tool_declares_argument(tool_name, "background") or self._mcp_tool_declares_argument(tool_name, "run_in_background") or self._mcp_tool_declares_argument(tool_name, "mode"):
            return False

        mode = arguments.get("mode")
        mode_is_background = isinstance(mode, str) and mode.lower() in {"background"}
        return arguments.get("background") is True or mode_is_background

    def _validate_background_tool_prerequisites(self, tool_name: str) -> None:
        """Validate required prerequisites before starting a background tool."""
        if not self._is_default_media_background_tool(tool_name):
            return

        workspace_path = getattr(self, "_cwd", None)
        try:
            from massgen.context.task_context import TaskContextError, load_task_context

            load_task_context(workspace_path, required=True)
        except TaskContextError as exc:
            raise ValueError(
                f"CONTEXT.md must be created before starting {tool_name} in background. {exc}",
            ) from exc

    def _resolve_background_tool_type(self, tool_name: str) -> tuple[str, str] | None:
        """Resolve background target to (tool_type, effective_tool_name)."""
        if not tool_name:
            return None

        raw_name = tool_name.strip()
        if raw_name in {"new_answer", "vote", "stop"}:
            return None
        if self._is_background_management_tool(raw_name):
            return None

        normalized_name = self._normalize_background_target_tool_name(raw_name)
        if self._is_background_management_tool(normalized_name):
            return None

        if self._custom_tool_manager and normalized_name in self._custom_tool_manager.registered_tools:
            return ("custom", normalized_name)

        if raw_name.startswith("mcp__"):
            return ("mcp", raw_name)

        return None

    @staticmethod
    def _is_subagent_spawn_target_tool(tool_name: str) -> bool:
        """Return True when tool_name resolves to subagent spawn MCP tool."""
        normalized = ClaudeCodeBackend._normalize_background_target_tool_name(
            str(tool_name or "").strip(),
        ).lower()
        return "spawn_subagent" in normalized and "subagent" in normalized

    @staticmethod
    def _normalize_subagent_spawn_background_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
        """Force wrapped subagent spawn requests into direct background mode."""
        normalized = dict(arguments)
        normalized["background"] = True
        normalized.pop("run_in_background", None)
        mode = normalized.get("mode")
        if not (isinstance(mode, str) and mode.lower() == "background"):
            normalized.pop("mode", None)
        return normalized

    @staticmethod
    def _parse_json_or_python_dict(raw_text: str) -> dict[str, Any] | None:
        """Parse dict payloads from JSON or Python repr text."""
        if not isinstance(raw_text, str):
            return None
        text = raw_text.strip()
        if not text:
            return None

        for parser in (json.loads, ast.literal_eval):
            try:
                parsed = parser(text)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(parsed, dict):
                return parsed
        return None

    @staticmethod
    def _looks_like_json_payload(raw_text: str) -> bool:
        stripped = str(raw_text or "").lstrip()
        return stripped.startswith("{") or stripped.startswith("[")

    @classmethod
    def _annotate_custom_tool_outcome_from_payload(
        cls,
        payload: dict[str, Any],
        *,
        ready: bool,
    ) -> None:
        """Attach tool-level outcome fields for terminal custom-tool jobs."""
        if not ready or payload.get("tool_type") != "custom":
            return

        status = str(payload.get("status") or "")
        if status in {"error", "cancelled"}:
            payload["tool_success"] = False
            payload["tool_error"] = str(payload.get("error") or "Custom tool execution failed")
            return

        if status != "completed":
            payload["tool_success"] = None
            return

        raw_result = str(payload.get("result") or "").strip()
        if not raw_result:
            payload["tool_success"] = False
            payload["tool_error"] = "No final result payload captured from custom tool execution"
            return

        parsed = cls._parse_json_or_python_dict(raw_result)
        if parsed is not None:
            parsed_success = parsed.get("success")
            if isinstance(parsed_success, bool):
                payload["tool_success"] = parsed_success
                if not parsed_success:
                    parsed_error = parsed.get("error")
                    payload["tool_error"] = str(parsed_error) if parsed_error is not None else "Custom tool reported success=false"
            else:
                payload["tool_success"] = True
            return

        if raw_result.startswith("Error:"):
            payload["tool_success"] = False
            payload["tool_error"] = raw_result
            return

        if cls._looks_like_json_payload(raw_result):
            payload["tool_success"] = None
            payload["result_parse_error"] = "Could not parse custom tool JSON result payload"
            return

        payload["tool_success"] = True

    @staticmethod
    def _format_unix_timestamp(timestamp: float | None) -> str | None:
        """Convert unix timestamp to ISO-8601 string."""
        if timestamp is None:
            return None
        return datetime.fromtimestamp(timestamp).isoformat()

    def _serialize_background_job(
        self,
        job: BackgroundToolJob,
        include_result: bool = False,
    ) -> dict[str, Any]:
        """Serialize background job state for tool responses and hook injection."""
        payload: dict[str, Any] = {
            "job_id": job.job_id,
            "tool_name": job.tool_name,
            "tool_type": job.tool_type,
            "status": job.status,
            "created_at": self._format_unix_timestamp(job.created_at),
            "started_at": self._format_unix_timestamp(job.started_at),
            "completed_at": self._format_unix_timestamp(job.completed_at),
            "source_call_id": job.source_call_id,
        }
        if include_result and job.result is not None:
            payload["result"] = job.result
        if job.error:
            payload["error"] = job.error
        return payload

    def _enqueue_completed_background_job(self, job: BackgroundToolJob) -> None:
        """Store completed job payload for post-tool hook injection."""
        self._pending_background_tool_results.append(
            self._serialize_background_job(job, include_result=True),
        )

    def get_pending_background_tool_results(self) -> list[dict[str, Any]]:
        """Return and clear completed background jobs pending injection."""
        pending = list(self._pending_background_tool_results)
        self._pending_background_tool_results.clear()
        return pending

    def register_background_delegate(self, delegate: Any) -> None:
        """Register a delegate that extends background lifecycle APIs (e.g., subagents)."""
        self._background_tool_delegate = delegate

    def _pop_next_pending_background_tool_result(self) -> dict[str, Any] | None:
        """Pop one completed background job payload from the shared delivery queue."""
        if not self._pending_background_tool_results:
            return None
        return self._pending_background_tool_results.pop(0)

    def set_background_wait_interrupt_provider(
        self,
        provider: Callable[[str], Any] | None,
    ) -> None:
        """Set an optional provider used to interrupt wait_for_background_tool."""
        self._background_wait_interrupt_provider = provider

    async def _get_background_wait_interrupt_payload(self) -> dict[str, Any] | None:
        """Return normalized wait interrupt payload, if any."""
        if not self._background_wait_interrupt_provider:
            return None

        agent_id = str(
            getattr(self, "agent_id", None) or self._current_agent_id or "unknown",
        )
        try:
            payload = self._background_wait_interrupt_provider(agent_id)
            if asyncio.iscoroutine(payload):
                payload = await payload
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "[ClaudeCodeBackend] Wait interrupt provider failed for %s: %s",
                agent_id,
                e,
                exc_info=True,
            )
            return None

        if not isinstance(payload, dict):
            return None

        raw_reason = payload.get("interrupt_reason", "runtime_injection_available")
        interrupt_reason = str(raw_reason).strip() or "runtime_injection_available"
        injected_content = payload.get("injected_content")
        if injected_content is not None:
            injected_content = str(injected_content)

        return {
            "interrupt_reason": interrupt_reason,
            "injected_content": injected_content,
        }

    @staticmethod
    def _extract_text_from_mcp_content(content: Any) -> str:
        """Extract text payload from MCP result content blocks."""
        if content is None:
            return ""

        blocks = content if isinstance(content, list) else [content]
        text_parts: list[str] = []

        for block in blocks:
            if isinstance(block, dict):
                text = block.get("text")
                if text is not None:
                    text_parts.append(str(text))
                    continue
                raw = block.get("content")
                if raw is not None:
                    text_parts.append(str(raw))
                    continue

            text_attr = getattr(block, "text", None)
            if text_attr is not None:
                text_parts.append(str(text_attr))
                continue

            content_attr = getattr(block, "content", None)
            if content_attr is not None:
                text_parts.append(str(content_attr))

        return "\n".join(part for part in text_parts if part).strip()

    @classmethod
    def _extract_text_from_mcp_response(cls, response: dict[str, Any]) -> str:
        """Extract text payload from MCP-style dict response."""
        content = response.get("content") if isinstance(response, dict) else None
        text = cls._extract_text_from_mcp_content(content)
        if text:
            return text
        return str(response)

    def _get_background_mcp_servers(self) -> list[dict[str, Any]]:
        """Return MCP server configs usable by background MCP execution."""
        servers = self.config.get("mcp_servers", [])
        result: list[dict[str, Any]] = []

        if isinstance(servers, dict):
            for name, cfg in servers.items():
                if name == "massgen_custom_tools":
                    continue
                if not isinstance(cfg, dict):
                    continue
                if "__sdk_server__" in cfg:
                    continue
                server_cfg = cfg.copy()
                server_cfg["name"] = name
                result.append(server_cfg)
            return result

        if isinstance(servers, list):
            for cfg in servers:
                if not isinstance(cfg, dict):
                    continue
                if cfg.get("name") == "massgen_custom_tools":
                    continue
                if "__sdk_server__" in cfg:
                    continue
                result.append(cfg)

        return result

    async def _get_background_mcp_client(self):
        """Create or return lazily-initialized MCP client for background jobs."""
        if self._background_mcp_client:
            return self._background_mcp_client
        if self._background_mcp_initialized:
            return None

        servers_to_use = self._get_background_mcp_servers()
        if not servers_to_use:
            self._background_mcp_initialized = True
            self._background_mcp_init_error = None
            return None

        try:
            # Derive timeout from server configs' tool_timeout_sec (set by the
            # orchestrator to subagent_default_timeout + 60).  This ensures the
            # MCP session read timeout is long enough for blocking
            # spawn_subagents calls whose duration scales with the configured
            # subagent timeout — rather than a hardcoded value that silently
            # caps long-running subagents.
            max_tool_timeout = max(
                (s.get("tool_timeout_sec", 0) for s in servers_to_use),
                default=0,
            )
            # Use the max tool_timeout_sec if available, otherwise fall back to
            # a sensible default.  The +60 buffer accounts for MCP overhead
            # beyond the tool execution itself.
            mcp_session_timeout = max(max_tool_timeout + 60, 1800)

            self._background_mcp_client = await MCPResourceManager.setup_mcp_client(
                servers=servers_to_use,
                allowed_tools=getattr(self, "allowed_tools", None),
                exclude_tools=getattr(self, "exclude_tools", None),
                circuit_breaker=getattr(self, "_mcp_tools_circuit_breaker", None),
                timeout_seconds=mcp_session_timeout,
                backend_name=self.get_provider_name(),
                agent_id=getattr(self, "agent_id", None),
            )
            self._background_mcp_initialized = True
            self._background_mcp_init_error = None
            return self._background_mcp_client
        except Exception as e:  # noqa: BLE001
            self._background_mcp_initialized = True
            self._background_mcp_init_error = str(e)
            logger.warning(
                "[ClaudeCodeBackend] Failed to initialize background MCP client: %s",
                e,
                exc_info=True,
            )
            return None

    async def _execute_background_tool_target(
        self,
        tool_name: str,
        tool_type: str,
        arguments: dict[str, Any],
    ) -> tuple[str, bool]:
        """Execute target tool for a background job."""
        if tool_type == "custom":
            response = await self._execute_massgen_custom_tool(
                tool_name,
                arguments,
                force_foreground=True,
            )
            result_text = self._extract_text_from_mcp_response(response)
            normalized_result = str(result_text or "").strip()
            if not normalized_result or normalized_result == "Tool executed successfully":
                return ("No final result payload captured from custom tool execution", True)
            return (normalized_result, normalized_result.startswith("Error:"))

        if tool_type == "mcp":
            mcp_client = await self._get_background_mcp_client()
            if not mcp_client:
                return (
                    "Error: MCP client not available for background execution",
                    True,
                )

            try:
                result = await mcp_client.call_tool(
                    name=tool_name,
                    arguments=arguments,
                )
                extracted = self._extract_text_from_mcp_content(
                    getattr(result, "content", None),
                )
                return (extracted or str(result), False)
            except Exception as e:  # noqa: BLE001
                return (f"Error: {e}", True)

        raise ValueError(f"Unsupported background tool type: {tool_type}")

    async def _run_background_tool_job(self, job_id: str) -> None:
        """Execute a background job and persist its terminal state."""
        job = self._background_tool_jobs.get(job_id)
        if not job:
            return

        job.started_at = time.time()
        try:
            result, is_error = await self._execute_background_tool_target(
                job.tool_name,
                job.tool_type,
                job.arguments,
            )
            if is_error:
                job.status = "error"
                job.error = result
            else:
                job.status = "completed"
                job.result = result
        except asyncio.CancelledError:
            job.status = "cancelled"
            job.error = job.error or "Background tool execution cancelled"
            raise
        except Exception as e:  # noqa: BLE001
            job.status = "error"
            job.error = f"Background tool failed: {e}"
            logger.warning(
                "[ClaudeCodeBackend] Background tool %s failed: %s",
                job.tool_name,
                e,
                exc_info=True,
            )
        finally:
            job.completed_at = time.time()
            self._background_tool_tasks.pop(job_id, None)
            if job.status in BACKGROUND_TOOL_TERMINAL_STATUSES:
                self._enqueue_completed_background_job(job)

    async def _start_background_tool_job(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        source_call_id: str | None = None,
    ) -> BackgroundToolJob:
        """Start a background job for a custom or MCP tool."""
        resolution = self._resolve_background_tool_type(tool_name)
        if resolution is None:
            raise ValueError(
                f"Tool '{tool_name}' is not available for background execution",
            )

        tool_type, effective_name = resolution
        self._validate_background_tool_prerequisites(effective_name)
        job_id = f"bgtool_{uuid.uuid4().hex[:12]}"
        job = BackgroundToolJob(
            job_id=job_id,
            tool_name=effective_name,
            tool_type=tool_type,
            arguments=dict(arguments),
            status="running",
            created_at=time.time(),
            source_call_id=source_call_id,
        )
        self._background_tool_jobs[job_id] = job
        self._background_tool_tasks[job_id] = asyncio.create_task(
            self._run_background_tool_job(job_id),
            name=f"background_tool:{effective_name}:{job_id}",
        )
        return job

    async def _start_background_subagent_spawn(
        self,
        tool_name: str,
        target_arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Treat wrapped subagent spawn starts like direct spawn_subagents(background=true)."""
        normalized_arguments = self._normalize_subagent_spawn_background_arguments(
            target_arguments,
        )
        mcp_client = await self._get_background_mcp_client()
        if not mcp_client:
            return {
                "success": False,
                "error": "MCP client not available for subagent background spawn",
            }

        try:
            result = await mcp_client.call_tool(
                name=tool_name,
                arguments=normalized_arguments,
            )
        except Exception as e:  # noqa: BLE001
            return {"success": False, "error": str(e)}

        extracted = self._extract_text_from_mcp_content(
            getattr(result, "content", None),
        )
        payload = self._parse_json_or_python_dict(extracted)
        if isinstance(payload, dict):
            if payload.get("success") is True and "mode" not in payload:
                payload["mode"] = "background"
            return self._attach_subagent_background_ids(payload)

        if extracted.startswith("Error:"):
            return {
                "success": False,
                "error": extracted.removeprefix("Error:").strip() or extracted,
            }

        return {
            "success": True,
            "operation": "spawn_subagents",
            "mode": "background",
            "result": extracted or str(result),
        }

    @staticmethod
    def _attach_subagent_background_ids(payload: dict[str, Any]) -> dict[str, Any]:
        """Ensure subagent background payloads expose both job and subagent IDs."""
        subagents_raw = payload.get("subagents")
        if not isinstance(subagents_raw, list):
            return payload

        subagents: list[dict[str, Any]] = []
        job_ids: list[str] = []
        for item in subagents_raw:
            if not isinstance(item, dict):
                continue
            entry = dict(item)
            subagent_id = str(entry.get("subagent_id") or entry.get("id") or "").strip()
            job_id = str(entry.get("job_id") or subagent_id).strip()
            if subagent_id:
                entry["subagent_id"] = subagent_id
            if job_id:
                entry["job_id"] = job_id
                job_ids.append(job_id)
            subagents.append(entry)

        if subagents:
            payload["subagents"] = subagents

        if not job_ids:
            return payload

        unique_job_ids = list(dict.fromkeys(job_ids))
        payload.setdefault("job_ids", unique_job_ids)

        if len(unique_job_ids) == 1:
            payload.setdefault("job_id", unique_job_ids[0])
            first_subagent_id = str(subagents[0].get("subagent_id") or "").strip() if subagents else ""
            if first_subagent_id:
                payload.setdefault("subagent_id", first_subagent_id)

        return payload

    async def _start_background_tool_from_request(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handle custom_tool__start_background_tool."""
        tool_name, target_arguments, parse_error = self._extract_background_start_request(arguments)
        if parse_error:
            return {"success": False, "error": parse_error}

        if self._is_subagent_spawn_target_tool(tool_name):
            return await self._start_background_subagent_spawn(
                tool_name,
                target_arguments,
            )

        try:
            job = await self._start_background_tool_job(tool_name, target_arguments)
        except Exception as e:  # noqa: BLE001
            return {"success": False, "error": str(e)}

        payload = self._serialize_background_job(job)
        payload.update(
            {
                "success": True,
                "message": f"Started {job.tool_name} in background",
            },
        )
        return payload

    def _extract_background_start_request(
        self,
        arguments: dict[str, Any],
    ) -> tuple[str, dict[str, Any], str | None]:
        """Extract target tool name/args from flexible start_background_tool payload."""
        tool_name = str(
            arguments.get("tool_name") or arguments.get("tool") or "",
        ).strip()
        if not tool_name:
            return ("", {}, "tool_name is required")

        if "arguments" in arguments and arguments.get("arguments") is not None:
            target_arguments: Any = arguments.get("arguments")
        elif "args" in arguments and arguments.get("args") is not None:
            target_arguments = arguments.get("args")
        else:
            target_arguments = {key: value for key, value in arguments.items() if key not in {"tool_name", "tool", "arguments", "args"}}

        if target_arguments is None:
            target_arguments = {}

        try:
            target_arguments, decode_passes = normalize_json_object_argument(
                target_arguments,
                field_name="arguments",
            )
        except ValueError:
            return ("", {}, "arguments must be a JSON object")
        if decode_passes > 1:
            logger.info(
                "[ClaudeCode] Normalized %s decode passes for start arguments (%s)",
                decode_passes,
                tool_name,
            )

        # Merge top-level extras (if any) without overriding explicit nested args.
        top_level_extras = {key: value for key, value in arguments.items() if key not in {"tool_name", "tool", "arguments", "args"}}
        for key, value in top_level_extras.items():
            target_arguments.setdefault(key, value)

        return (tool_name, target_arguments, None)

    async def _get_background_tool_status_from_request(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handle custom_tool__get_background_tool_status."""
        job_id = str(arguments.get("job_id", "")).strip()
        if not job_id:
            return {"success": False, "error": "job_id is required"}

        job = self._background_tool_jobs.get(job_id)
        if job:
            payload = self._serialize_background_job(job)
            payload["success"] = True
            return payload

        delegate = self._background_tool_delegate
        if delegate:
            try:
                if await delegate.owns(job_id):
                    return await delegate.get_status(job_id)
            except Exception:
                logger.debug(
                    "[ClaudeCodeBackend] Delegate get_status failed for %s",
                    job_id,
                    exc_info=True,
                )

        return {"success": False, "error": f"Background job not found: {job_id}"}

    async def _get_background_tool_result_from_request(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handle custom_tool__get_background_tool_result."""
        job_id = str(arguments.get("job_id", "")).strip()
        if not job_id:
            return {"success": False, "error": "job_id is required"}

        job = self._background_tool_jobs.get(job_id)
        if job:
            ready = job.status in BACKGROUND_TOOL_TERMINAL_STATUSES
            payload = self._serialize_background_job(job, include_result=True)
            payload.update({"success": True, "ready": ready})
            self._annotate_custom_tool_outcome_from_payload(payload, ready=ready)
            if not ready:
                payload["message"] = "Background tool still running"
            return payload

        delegate = self._background_tool_delegate
        if delegate:
            try:
                if await delegate.owns(job_id):
                    return await delegate.get_result(job_id)
            except Exception:
                logger.debug(
                    "[ClaudeCodeBackend] Delegate get_result failed for %s",
                    job_id,
                    exc_info=True,
                )

        return {"success": False, "error": f"Background job not found: {job_id}"}

    @staticmethod
    def _coerce_background_wait_timeout(arguments: dict[str, Any]) -> float:
        """Normalize wait timeout to a safe bounded value."""
        raw_timeout = arguments.get(
            "timeout_seconds",
            BACKGROUND_TOOL_WAIT_DEFAULT_TIMEOUT_SECONDS,
        )
        try:
            timeout_seconds = float(raw_timeout)
        except (TypeError, ValueError):
            timeout_seconds = BACKGROUND_TOOL_WAIT_DEFAULT_TIMEOUT_SECONDS
        if timeout_seconds < 0:
            return 0.0
        return min(timeout_seconds, BACKGROUND_TOOL_WAIT_MAX_TIMEOUT_SECONDS)

    def _next_waitable_background_job(self) -> BackgroundToolJob | None:
        """Get the next unseen terminal background job for wait calls."""
        candidates = [job for job in self._background_tool_jobs.values() if job.status in BACKGROUND_TOOL_TERMINAL_STATUSES and job.job_id not in self._background_tool_wait_seen_ids]
        if not candidates:
            return None
        candidates.sort(
            key=lambda job: (
                job.completed_at if job.completed_at is not None else job.created_at,
                job.created_at,
            ),
        )
        return candidates[0]

    async def _wait_for_background_tool_from_request(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handle custom_tool__wait_for_background_tool."""
        timeout_seconds = self._coerce_background_wait_timeout(arguments)
        wait_started_at = time.time()

        while True:
            payload = self._pop_next_pending_background_tool_result()
            if payload is not None:
                job_id = str(payload.get("job_id", "")).strip()
                if job_id:
                    self._background_tool_wait_seen_ids.add(job_id)
                payload.update(
                    {
                        "success": True,
                        "ready": True,
                        "waited_seconds": round(time.time() - wait_started_at, 3),
                    },
                )
                self._annotate_custom_tool_outcome_from_payload(payload, ready=True)
                return payload

            interrupt_payload = await self._get_background_wait_interrupt_payload()
            if interrupt_payload is not None:
                return {
                    "success": True,
                    "ready": False,
                    "interrupted": True,
                    "interrupt_reason": interrupt_payload.get("interrupt_reason"),
                    "injected_content": interrupt_payload.get("injected_content"),
                    "waited_seconds": round(time.time() - wait_started_at, 3),
                    "message": "Background wait interrupted by runtime input",
                }

            elapsed = time.time() - wait_started_at
            if elapsed >= timeout_seconds:
                return {
                    "success": True,
                    "ready": False,
                    "timed_out": True,
                    "waited_seconds": round(elapsed, 3),
                    "message": "No background tool completed before timeout",
                }

            sleep_seconds = min(
                BACKGROUND_TOOL_WAIT_POLL_INTERVAL_SECONDS,
                max(timeout_seconds - elapsed, 0.0),
            )
            if sleep_seconds <= 0:
                await asyncio.sleep(0)
            else:
                await asyncio.sleep(sleep_seconds)

    async def _cancel_background_tool_from_request(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handle custom_tool__cancel_background_tool."""
        job_id = str(arguments.get("job_id", "")).strip()
        if not job_id:
            return {"success": False, "error": "job_id is required"}

        job = self._background_tool_jobs.get(job_id)
        if job:
            task = self._background_tool_tasks.get(job_id)
            if task and not task.done():
                job.status = "cancelled"
                job.error = "Cancelled by user request"
                task.cancel()

            payload = self._serialize_background_job(job)
            payload["success"] = True
            return payload

        delegate = self._background_tool_delegate
        if delegate:
            try:
                if await delegate.owns(job_id):
                    return await delegate.cancel(job_id)
            except Exception:
                logger.debug(
                    "[ClaudeCodeBackend] Delegate cancel failed for %s",
                    job_id,
                    exc_info=True,
                )

        return {"success": False, "error": f"Background job not found: {job_id}"}

    @staticmethod
    def _coerce_include_all_background_jobs(arguments: dict[str, Any] | None) -> bool:
        """Normalize include_all flag for background list requests."""
        if not isinstance(arguments, dict):
            return False

        raw_include_all = arguments.get("include_all", arguments.get("all"))
        if isinstance(raw_include_all, bool):
            return raw_include_all
        if isinstance(raw_include_all, str):
            return raw_include_all.strip().lower() in {"1", "true", "yes", "on", "all"}
        return False

    async def _list_background_tools_from_request(self, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Handle custom_tool__list_background_tools."""
        include_all = self._coerce_include_all_background_jobs(arguments)
        jobs = [self._serialize_background_job(job) for job in self._background_tool_jobs.values() if include_all or job.status not in BACKGROUND_TOOL_TERMINAL_STATUSES]

        delegate = self._background_tool_delegate
        if delegate:
            try:
                delegate_jobs = await delegate.list_jobs(include_all=include_all)
                jobs.extend(delegate_jobs)
            except Exception:
                logger.debug(
                    "[ClaudeCodeBackend] Delegate list_jobs failed",
                    exc_info=True,
                )

        jobs.sort(key=lambda job: job.get("created_at") or "", reverse=True)
        return {
            "success": True,
            "count": len(jobs),
            "include_all": include_all,
            "jobs": jobs,
        }

    async def _execute_background_management_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Dispatch internal background-management tools."""
        if tool_name == BACKGROUND_TOOL_START_NAME:
            return await self._start_background_tool_from_request(arguments)
        if tool_name == BACKGROUND_TOOL_STATUS_NAME:
            return await self._get_background_tool_status_from_request(arguments)
        if tool_name == BACKGROUND_TOOL_RESULT_NAME:
            return await self._get_background_tool_result_from_request(arguments)
        if tool_name == BACKGROUND_TOOL_WAIT_NAME:
            return await self._wait_for_background_tool_from_request(arguments)
        if tool_name == BACKGROUND_TOOL_CANCEL_NAME:
            return await self._cancel_background_tool_from_request(arguments)
        if tool_name == BACKGROUND_TOOL_LIST_NAME:
            return await self._list_background_tools_from_request(arguments)

        return {"success": False, "error": f"Unknown background management tool: {tool_name}"}

    async def _cancel_all_background_tool_jobs(self) -> None:
        """Cancel all running background jobs."""
        running_tasks: list[asyncio.Task[Any]] = []
        for job_id, task in list(self._background_tool_tasks.items()):
            if task.done():
                continue
            job = self._background_tool_jobs.get(job_id)
            if job:
                job.status = "cancelled"
                job.error = "Cancelled during backend cleanup"
            task.cancel()
            running_tasks.append(task)

        if running_tasks:
            await asyncio.gather(*running_tasks, return_exceptions=True)

        self._background_tool_tasks.clear()

        if self._background_mcp_client is not None:
            try:
                await self._background_mcp_client.disconnect()
            except Exception:  # noqa: BLE001
                pass
            self._background_mcp_client = None
            self._background_mcp_initialized = False

    def _create_sdk_mcp_server_from_custom_tools(self):
        """Convert MassGen custom tools to SDK MCP Server.

        Returns:
            SDK MCP Server instance or None if no tools or SDK unavailable
        """
        try:
            from claude_agent_sdk import create_sdk_mcp_server, tool
        except ImportError:
            logger.warning("claude-agent-sdk not available, custom tools will not be registered")
            return None

        # Get all MassGen-managed tool schemas (user custom + internal background helpers)
        tool_schemas = self._get_massgen_custom_tool_schemas()
        if not tool_schemas:
            logger.info("No custom tools to register")
            return None

        # Convert each tool to MCP tool format
        mcp_tools = []
        for tool_schema in tool_schemas:
            try:
                tool_name = tool_schema["function"]["name"]
                tool_desc = tool_schema["function"].get("description", "")
                tool_params = tool_schema["function"]["parameters"]

                # Create async wrapper for MassGen tool
                # Use default argument to capture tool_name in closure
                async def tool_wrapper(args, tool_name=tool_name):
                    return await self._execute_massgen_custom_tool(tool_name, args)

                # Register using SDK tool decorator
                mcp_tool = tool(
                    name=tool_name,
                    description=tool_desc,
                    input_schema=tool_params,
                )(tool_wrapper)

                mcp_tools.append(mcp_tool)
                logger.info(f"Converted custom tool to MCP: {tool_name}")

            except Exception as e:
                logger.error(f"Failed to convert tool {tool_schema.get('function', {}).get('name', 'unknown')} to MCP: {e}")

        if not mcp_tools:
            logger.warning("No custom tools successfully converted to MCP")
            return None

        # Create SDK MCP server
        try:
            sdk_mcp_server = create_sdk_mcp_server(
                name="massgen_custom_tools",
                version="1.0.0",
                tools=mcp_tools,
            )
            logger.info(f"Created SDK MCP server with {len(mcp_tools)} custom tools")
            return sdk_mcp_server
        except Exception as e:
            logger.error(f"Failed to create SDK MCP server: {e}")
            return None

    def _build_system_prompt_with_workflow_tools(self, tools: list[dict[str, Any]], base_system: str | None = None) -> str:
        """Build system prompt that includes workflow tools information.

        Creates comprehensive system prompt that instructs Claude on tool
        usage, particularly for MassGen workflow coordination tools.

        Args:
            tools: List of available tools
            base_system: Base system prompt to extend (optional)

        Returns:
            Complete system prompt with tool instructions
        """
        system_parts = []

        # Start with base system prompt
        if base_system:
            system_parts.append(base_system)

        # Add MCP command line execution instruction if enabled
        enable_mcp_command_line = self.config.get("enable_mcp_command_line", False)
        command_line_execution_mode = self.config.get("command_line_execution_mode", "local")
        if enable_mcp_command_line:
            system_parts.append("\n--- Code Execution Environment ---")
            system_parts.append("- Use the execute_command MCP tool for all command execution")
            system_parts.append("- The Bash tool is disabled - use execute_command instead")
            if command_line_execution_mode == "docker":
                system_parts.append("- Commands run in isolated Docker container")
            # Below is necessary bc Claude Code is automatically loaded with knowledge of the current git repo;
            # this prompt is a temporary workaround before running fully within docker
            system_parts.append(
                "- Do NOT use any git repository information you may see as part of a broader directory. "
                "All git information must come from the execute_command tool and be focused solely on the "
                "directories you were told to work in, not any parent directories.",
            )

        # Add workflow tools section (shared with Codex backend)
        if tools:
            workflow_section = build_workflow_instructions(tools)
            if workflow_section:
                system_parts.append(workflow_section)

        return "\n".join(system_parts)

    async def _log_backend_input(self, messages, system_prompt, tools, kwargs):
        """Log backend inputs using StreamChunk for visibility (enabled by default)."""
        # Enable by default, but allow disabling via environment variable
        if os.getenv("MASSGEN_LOG_BACKENDS", "1") == "0":
            return

        try:
            # Create debug info using the logging approach that works in MassGen
            reset_mode = "🔄 RESET" if kwargs.get("reset_chat") else "💬 CONTINUE"
            tools_info = f"🔧 {len(tools)} tools" if tools else "🚫 No tools"

            debug_info = f"[BACKEND] {reset_mode} | {tools_info} | Session: {self._current_session_id}"

            if system_prompt and len(system_prompt) > 0:
                # Show full system prompt in debug logging
                debug_info += f"\n[SYSTEM_FULL] {system_prompt}"

            # Yield a debug chunk that will be captured by the logging system
            yield StreamChunk(type="debug", content=debug_info, source="claude_code_backend")

        except Exception as e:
            # Log the error but don't break backend execution
            yield StreamChunk(
                type="debug",
                content=f"[BACKEND_LOG_ERROR] {str(e)}",
                source="claude_code_backend",
            )

    def extract_structured_response(self, response_text: str) -> dict[str, Any] | None:
        """Extract structured JSON response — delegates to shared helper."""
        return _extract_structured_response(response_text)

    def _parse_workflow_tool_calls(self, text_content: str) -> list[dict[str, Any]]:
        """Parse workflow tool calls from text — delegates to shared helper."""
        return _parse_workflow_tool_calls(text_content)

    @staticmethod
    def _try_extract_workflow_mcp_result(result_str: str) -> dict[str, Any] | None:
        """Try to extract a workflow tool call from an MCP tool result string.

        Returns:
            Tool call dict in orchestrator format, or None.
        """
        from ..mcp_tools.workflow_tools_server import extract_workflow_tool_call

        try:
            result = json.loads(result_str)
            return extract_workflow_tool_call(result)
        except (json.JSONDecodeError, TypeError):
            return None

    def _build_claude_options(self, **options_kwargs) -> ClaudeAgentOptions:
        """Build ClaudeAgentOptions with provided parameters.

        Creates a secure configuration with only essential Claude Code tools enabled.
        MassGen has native implementations for most file/shell operations, so we only
        enable unique tools like Task (subagent spawning) and optionally web tools.

        Config options:
        - use_default_prompt (bool, default False): When True, uses Claude Code's
          default system prompt with MassGen instructions appended. When False,
          uses only MassGen's workflow system prompt for full control.
        - enable_web_search (bool, default False): When True, enables WebSearch
          and WebFetch tools. When False, these are disabled (use MassGen's crawl4ai).

        Returns:
            ClaudeAgentOptions configured with provided parameters and
            security restrictions
        """
        options_kwargs.get("cwd", os.getcwd())
        permission_mode = options_kwargs.get("permission_mode", "acceptEdits")
        enable_web_search = options_kwargs.get("enable_web_search", False)
        allowed_tools = options_kwargs.get("allowed_tools", self.get_supported_builtin_tools(enable_web_search))
        options_kwargs.get("disallowed_tools", [])

        # Skill tool is disabled (weaker models misuse it); agents read skill files directly.
        # skill_enabled = isinstance(allowed_tools, list) and "Skill" in allowed_tools
        # if isinstance(disallowed_tools, list) and "Skill" in disallowed_tools:
        #     skill_enabled = False
        skill_enabled = False

        # Filter out parameters handled separately or not for ClaudeAgentOptions
        excluded_params = self.get_base_excluded_config_params() | {
            # Claude Code specific exclusions
            "api_key",
            "allowed_tools",
            "permission_mode",
            "custom_tools",  # Handled separately via SDK MCP server conversion
            "instance_id",  # Used for Docker container naming, not for ClaudeAgentOptions
            "enable_rate_limit",  # Rate limiting parameter (handled at orchestrator level, not backend)
            # MassGen-specific config options (not ClaudeAgentOptions parameters)
            "enable_web_search",  # Handled above - controls WebSearch/WebFetch tool availability
            "use_default_prompt",  # Handled in stream_with_tools - controls system prompt mode
            "max_thinking_tokens",  # Deprecated: handled below via reasoning config
            "reasoning",  # Unified reasoning config → SDK thinking + effort fields
            "env",  # Handled separately: CLAUDECODE="" is always injected, then user overrides are merged
            # Note: use_mcpwrapped_for_tool_filtering and use_no_roots_wrapper are in base excluded params
            # Note: system_prompt is NOT excluded - it's needed for internal workflow prompt injection
            # Validation prevents it from being set in YAML backend config
        }

        # Get cwd from filesystem manager (always available since we require it in __init__)
        cwd_option = Path(str(self.filesystem_manager.get_current_workspace())).resolve()
        self._cwd = str(cwd_option)

        # Always sync skills so agents can read them via filesystem tools.
        self._sync_skills_into_workspace(cwd_option)

        # Keep settings isolated by default; load filesystem settings only when Skill is enabled.
        setting_sources = options_kwargs.get("setting_sources")
        if skill_enabled:
            if setting_sources is None:
                setting_sources = ["user", "project"]
        elif setting_sources is None:
            setting_sources = []

        # Get hooks configuration from filesystem manager (permission hooks)
        permission_hooks = self.filesystem_manager.get_claude_code_hooks_config()

        # Merge permission hooks with MassGen hooks (MidStreamInjection, user hooks, etc.)
        if self._massgen_hooks_config and self._native_hook_adapter:
            hooks_config = self._native_hook_adapter.merge_native_configs(
                permission_hooks,
                self._massgen_hooks_config,
            )
            logger.debug(
                f"[ClaudeCodeBackend] Merged hooks: " f"PreToolUse={len(hooks_config.get('PreToolUse', []))} total, " f"PostToolUse={len(hooks_config.get('PostToolUse', []))} total",
            )
        else:
            hooks_config = permission_hooks

        # Convert mcp_servers from list format to dict format for ClaudeAgentOptions
        # List format: [{"name": "server1", "type": "stdio", ...}, ...]
        # Dict format: {"server1": {"type": "stdio", ...}, ...}
        mcp_servers_dict = {}
        if "mcp_servers" in options_kwargs:
            mcp_servers = options_kwargs["mcp_servers"]
            if isinstance(mcp_servers, list):
                for server in mcp_servers:
                    if isinstance(server, dict):
                        if "__sdk_server__" in server:
                            # SDK MCP Server object (created via create_sdk_mcp_server)
                            server_name = server["name"]
                            mcp_servers_dict[server_name] = server["__sdk_server__"]
                        elif "name" in server:
                            # Regular dictionary configuration
                            server_config = {k: v for k, v in server.items() if k != "name"}
                            mcp_servers_dict[server["name"]] = server_config
                            # Log filesystem server args for debugging
                            if server["name"] == "filesystem":
                                logger.info(f"[ClaudeCodeBackend] Configuring filesystem MCP server with args: {server_config.get('args', [])}")
            elif isinstance(mcp_servers, dict):
                # Already in dict format
                mcp_servers_dict = mcp_servers

        # Get additional directories from filesystem manager for Claude Code access
        # IMPORTANT: add_dirs grants WRITE access - only include paths with write permission.
        # Read-only context paths must NOT be in add_dirs (OS sandbox allows reads anyway).
        # NOTE: cwd is already writable by default, so we exclude it from add_dirs.
        add_dirs = []
        if self.filesystem_manager:
            # Only get writable paths - add_dirs grants write access
            writable_paths = self.filesystem_manager.path_permission_manager.get_writable_paths()
            cwd_str = str(cwd_option)
            # Exclude cwd since it's already writable by default
            add_dirs = [p for p in writable_paths if p != cwd_str]
            if add_dirs:
                logger.info(f"[ClaudeCodeBackend._build_claude_options] Adding writable dirs for Claude Code access: {add_dirs}")

        # Enable OS-level sandbox for native tool security
        # Seatbelt on macOS, bubblewrap on Linux — restricts writes to cwd + add_dirs
        sandbox_settings = {
            "enabled": True,
            "autoAllowBashIfSandboxed": True,
        }

        # Clear CLAUDECODE env var so child Claude Code sessions are not blocked
        # by nested session detection (CLAUDECODE=1 is inherited from the parent).
        # Raise the SDK initialize timeout to avoid premature stream close on
        # slow cold-starts (default is 60 000 ms).
        env_overrides: dict[str, str] = {
            "CLAUDECODE": "",
            "CLAUDE_CODE_STREAM_CLOSE_TIMEOUT": "180000",  # 3 min in ms (default 60000)
        }
        if "env" in options_kwargs:
            env_overrides.update(options_kwargs["env"])

        options = {
            "cwd": str(cwd_option),
            "resume": self.get_current_session_id(),
            "permission_mode": permission_mode,
            "allowed_tools": allowed_tools,
            "add_dirs": add_dirs if add_dirs else [],
            "sandbox": sandbox_settings,
            "setting_sources": setting_sources,
            "env": env_overrides,
            **{k: v for k, v in options_kwargs.items() if k not in excluded_params},
        }

        # Add converted mcp_servers if present
        if mcp_servers_dict:
            options["mcp_servers"] = mcp_servers_dict
            # Debug log the full filesystem server config
            if "filesystem" in mcp_servers_dict:
                fs_config = mcp_servers_dict["filesystem"]
                logger.info(f"[ClaudeCodeBackend] Full filesystem MCP config being passed to SDK: {fs_config}")

        # System prompt handling based on use_default_prompt config
        # - use_default_prompt=True: Use Claude Code preset (for coding style guidelines)
        # - use_default_prompt=False (default): Use only MassGen's workflow prompt
        use_default_prompt = options_kwargs.get("use_default_prompt", False)
        if use_default_prompt and "system_prompt" not in options:
            # Use Claude Code preset as base (will be appended to in stream_with_tools)
            options["system_prompt"] = {"type": "preset", "preset": "claude_code"}
        # else: system_prompt will be set as plain string in stream_with_tools

        # Add hooks if available
        if hooks_config:
            options["hooks"] = hooks_config

        # Add can_use_tool hook to auto-grant tool permissions
        # Note: File access validation is handled by PreToolUse hooks (validate_context_access)
        # This callback just grants permission to call the tool itself
        async def can_use_tool(tool_name: str, tool_args: dict, context):
            """Auto-grant tool call permissions. PreToolUse hooks handle path validation."""
            # Return PermissionResultAllow for all tools
            # The PreToolUse hooks will still validate file paths for Read/Write/Bash/etc.
            return PermissionResultAllow(updated_input=tool_args)

        options["can_use_tool"] = can_use_tool

        # Capture stderr from the Claude Code subprocess.
        # Without this, stderr is inherited and dumps directly to the terminal.
        # Log at WARNING so errors (rate limits, API failures, auth issues) are
        # visible in INFO+ log files — previously DEBUG swallowed them silently.
        options["stderr"] = lambda line: logger.warning(f"[ClaudeCode stderr] {line.rstrip()}")

        # Enable CLI-level debug logging to stderr for diagnosing silent hangs.
        if os.getenv("MASSGEN_CLAUDE_CODE_DEBUG", "0") == "1":
            options.setdefault("extra_args", {})["debug-to-stderr"] = None
            logger.info("[ClaudeCodeBackend] Enabled debug-to-stderr for CLI diagnostics")

        # Parse unified reasoning config → SDK thinking + effort fields
        # Supports: reasoning: {type: adaptive, effort: high}
        # Backward compat: max_thinking_tokens: N → thinking: {type: enabled, budget_tokens: N}
        # Default: adaptive thinking + medium effort
        reasoning = options_kwargs.get("reasoning", {})
        max_thinking = options_kwargs.get("max_thinking_tokens")

        if reasoning:
            thinking_type = reasoning.get("type", "adaptive")
            if thinking_type == "adaptive":
                options["thinking"] = {"type": "adaptive"}
            elif thinking_type == "enabled":
                options["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": reasoning.get("budget_tokens", 32_000),
                }
            elif thinking_type == "disabled":
                options["thinking"] = {"type": "disabled"}
            if "effort" in reasoning:
                options["effort"] = reasoning["effort"]
        elif max_thinking:
            # Backward compat: max_thinking_tokens → thinking enabled
            options["thinking"] = {"type": "enabled", "budget_tokens": max_thinking}
        else:
            # Default: match CLI behavior (adaptive thinking)
            options["thinking"] = {"type": "adaptive"}

        # Default effort if not set by reasoning config
        if "effort" not in options:
            options["effort"] = "medium"

        # Debug: Log the full mcp_servers config being passed to SDK
        if "mcp_servers" in options and "filesystem" in options["mcp_servers"]:
            logger.info(f"[ClaudeCodeBackend] FINAL filesystem config to SDK: {options['mcp_servers']['filesystem']}")

        # Debug: Log add_dirs to verify they're being passed
        if options.get("add_dirs"):
            logger.info(f"[ClaudeCodeBackend] FINAL add_dirs to SDK: {options['add_dirs']}")

        return ClaudeAgentOptions(**options)

    def create_client(self, **options_kwargs) -> ClaudeSDKClient:
        """Create ClaudeSDKClient with configurable parameters.

        Args:
            **options_kwargs: ClaudeAgentOptions parameters

        Returns:
            ClaudeSDKClient instance
        """

        # Build options with all parameters
        options = self._build_claude_options(**options_kwargs)

        # Create ClaudeSDKClient with configured options
        self._client = ClaudeSDKClient(options)
        return self._client

    async def stream_with_tools(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], **kwargs) -> AsyncGenerator[StreamChunk]:
        """
        Stream a response with tool calling support using claude-code-sdk.

        Properly handle messages and tools context for Claude Code.

        Args:
            messages: List of conversation messages
            tools: List of available tools (includes workflow tools)
            **kwargs: Additional options for client configuration

        Yields:
            StreamChunk objects with response content and metadata
        """
        # Extract agent_id from kwargs if provided and store for tool execution context
        agent_id = kwargs.get("agent_id", None)
        self._current_agent_id = agent_id  # Store for custom tool execution

        # Clear streaming buffer at start (respects _compression_retry flag)
        # This also initializes execution trace via the mixin
        self._clear_streaming_buffer(**kwargs)

        # Initialize span tracking variables for proper cleanup in all code paths
        llm_span = None
        llm_span_cm = None  # Context manager for the span
        llm_span_open = False

        log_backend_activity(
            self.get_provider_name(),
            "Starting stream_with_tools",
            {"num_messages": len(messages), "num_tools": len(tools) if tools else 0},
            agent_id=agent_id,
        )
        # Merge constructor config with stream kwargs (stream kwargs take priority)
        all_params = {**self.config, **kwargs}

        # Load task context from CONTEXT.md if it exists (for multimodal tools and subagents)
        task_context = None
        if self.filesystem_manager and self.filesystem_manager.cwd:
            from massgen.context.task_context import load_task_context

            task_context = load_task_context(
                str(self.filesystem_manager.cwd),
                required=False,
            )

        # Extract system message from messages for append mode (always do this)
        # This must be done BEFORE checking if we have a client to ensure workflow_system_prompt is always defined
        system_msg = next((msg for msg in messages if msg.get("role") == "system"), None)
        if system_msg:
            system_content = system_msg.get("content", "")  # noqa: E128
        else:
            system_content = ""

        # Build execution context for custom tool injection parity with shared backends.
        self._execution_context = ExecutionContext(
            messages=messages,
            agent_system_message=kwargs.get("system_message", None),
            agent_id=agent_id or self.agent_id,
            backend_name=self.get_provider_name(),
            backend_type=normalize_backend_type(self.get_provider_name()),
            model=kwargs.get("model", self.config.get("model", "")),
            current_stage=self.coordination_stage,
            agent_cwd=str(self.filesystem_manager.cwd) if self.filesystem_manager else None,
            allowed_paths=(
                self.filesystem_manager.path_permission_manager.get_mcp_filesystem_paths()
                if self.filesystem_manager and hasattr(self.filesystem_manager, "path_permission_manager") and self.filesystem_manager.path_permission_manager
                else None
            ),
            multimodal_config=self._multimodal_config if hasattr(self, "_multimodal_config") else None,
            task_context=task_context,
        )

        # Use text-based workflow tools (JSON parsing) for Claude Code
        # TODO: MCP-based workflow tools not yet working with Claude Code SDK
        self._has_workflow_mcp = False
        workflow_system_prompt = self._build_system_prompt_with_workflow_tools(tools or [], system_content)

        # Check if we already have a client
        if self._client is not None:
            client = self._client
        else:
            # Set default disallowed_tools if not provided
            # Disable tools that MassGen has native implementations for
            enable_web_search = all_params.get("enable_web_search", False)

            if "disallowed_tools" not in all_params:
                all_params["disallowed_tools"] = self.get_disallowed_tools(all_params)
                default_allowed_tools = all_params.get("allowed_tools", self.get_supported_builtin_tools(enable_web_search))
                logger.info(
                    f"[ClaudeCodeBackend] Using builtin tool allowlist: {default_allowed_tools}",
                )

            # Additional disabling when MCP command_line is enabled
            # (redundant now since Bash is always disabled, but kept for explicit clarity)
            enable_mcp_command_line = all_params.get("enable_mcp_command_line", False)
            if enable_mcp_command_line:
                logger.info("[ClaudeCodeBackend] MCP command_line enabled, using execute_command for all commands")

            # Convert allowed_tools from MCP server configs to agent-level allowed_tools
            # Claude Agent SDK expects tool filtering at agent level, not server config level
            # Using allowed_tools (allowlist) hides tools entirely so Claude won't try to use them
            mcp_servers = all_params.get("mcp_servers", [])
            if isinstance(mcp_servers, list):
                # Check if any server has allowed_tools specified
                has_allowed_tools = any(isinstance(s, dict) and s.get("allowed_tools") for s in mcp_servers)

                if has_allowed_tools:
                    # Build complete allowed_tools list
                    # Start with current allowed_tools (builtin tools like Task)
                    current_allowed = all_params.get("allowed_tools", self.get_supported_builtin_tools(enable_web_search))
                    if isinstance(current_allowed, list):
                        merged_allowed = list(current_allowed)
                    else:
                        merged_allowed = [current_allowed] if current_allowed else []

                    # Add MCP tools from servers
                    for server in mcp_servers:
                        if not isinstance(server, dict):
                            continue

                        server_name = server.get("name")
                        if not server_name:
                            continue

                        server_allowed = server.get("allowed_tools")
                        if server_allowed:
                            # Server has explicit allowed_tools - add only those
                            for tool in server_allowed:
                                merged_allowed.append(f"mcp__{server_name}__{tool}")
                            logger.info(
                                f"[ClaudeCodeBackend] Server '{server_name}': allowing specific tools -> {server_allowed}",
                            )
                        else:
                            # Server has no allowed_tools - allow all its tools
                            # Use explicit tool list for known servers, wildcard for unknown
                            all_tools = self._get_all_tools_for_server(server_name)
                            if all_tools:
                                merged_allowed.extend(all_tools)
                                logger.info(
                                    f"[ClaudeCodeBackend] Server '{server_name}': allowing all {len(all_tools)} known tools",
                                )
                            else:
                                # Unknown server - use wildcard and hope it works
                                merged_allowed.append(f"mcp__{server_name}__*")
                                logger.warning(
                                    f"[ClaudeCodeBackend] Server '{server_name}': unknown server, using wildcard pattern",
                                )

                    all_params["allowed_tools"] = merged_allowed
                    logger.info(
                        f"[ClaudeCodeBackend] Set allowed_tools with {len(merged_allowed)} entries to hide filtered tools",
                    )

            # Windows-specific handling: detect long prompts that exceed CreateProcess limit
            # Windows CreateProcess has ~8,191 char limit for entire command line
            # Use conservative threshold of 4000 chars to account for other CLI arguments
            WINDOWS_PROMPT_THRESHOLD = 4000
            if sys.platform == "win32" and len(workflow_system_prompt) > WINDOWS_PROMPT_THRESHOLD:
                # Windows with long prompt: delay system prompt delivery
                # The prompt will be injected into the first user message (via stdin pipe) instead
                logger.info(
                    f"[ClaudeCodeBackend] Windows detected long system prompt " f"({len(workflow_system_prompt)} chars > {WINDOWS_PROMPT_THRESHOLD}), " "deferring delivery to first user message",
                )
                clean_params = {k: v for k, v in all_params.items() if k not in ["system_prompt"]}
                client = self.create_client(**clean_params)
                self._pending_system_prompt = workflow_system_prompt

            else:
                # Original approach for Mac/Linux and Windows with simple prompts
                try:
                    # System prompt handling based on use_default_prompt config
                    use_default_prompt = all_params.get("use_default_prompt", False)

                    if use_default_prompt:
                        # Use Claude Code preset with MassGen instructions appended
                        # This gives Claude Code's coding style guidelines + MassGen workflow tools
                        system_prompt_config = {
                            "type": "preset",
                            "preset": "claude_code",
                            "append": workflow_system_prompt,
                        }
                    else:
                        # Use only MassGen's workflow system prompt (no preset)
                        # This gives full control over agent behavior
                        system_prompt_config = workflow_system_prompt

                    client = self.create_client(**{**all_params, "system_prompt": system_prompt_config})
                    self._pending_system_prompt = None

                except Exception as create_error:
                    # Fallback for unexpected failures
                    if sys.platform == "win32":
                        clean_params = {k: v for k, v in all_params.items() if k not in ["system_prompt"]}
                        client = self.create_client(**clean_params)
                        self._pending_system_prompt = workflow_system_prompt
                    else:
                        # On Mac/Linux, re-raise the error since this shouldn't happen
                        raise create_error

        # Connect client if not already connected
        if not client._transport:
            try:
                await client.connect()

                # Setup code-based tools after connection (creates symlinks to shared tools if they exist)
                if self.filesystem_manager and self.filesystem_manager.enable_code_based_tools:
                    await self._setup_code_based_tools_symlinks()

            except Exception as e:
                yield StreamChunk(
                    type="error",
                    error=f"Failed to connect to Claude Code: {str(e)}",
                    source="claude_code",
                )
                return

        # Log backend inputs when we have workflow_system_prompt available
        if "workflow_system_prompt" in locals():
            async for debug_chunk in self._log_backend_input(messages, workflow_system_prompt, tools, kwargs):
                yield debug_chunk

        # Format the messages for Claude Code
        if not messages:
            log_stream_chunk(
                "backend.claude_code",
                "error",
                "No messages provided to stream_with_tools",
                agent_id,
            )
            # No messages to process - yield error
            yield StreamChunk(
                type="error",
                error="No messages provided to stream_with_tools",
                source="claude_code",
            )
            return

        # Validate messages - should only contain user messages for Claude Code
        user_messages = [msg for msg in messages if msg.get("role") == "user"]
        assistant_messages = [msg for msg in messages if msg.get("role") == "assistant"]

        if assistant_messages:
            log_stream_chunk(
                "backend.claude_code",
                "error",
                "Claude Code backend cannot accept assistant messages - it maintains its own conversation history",
                agent_id,
            )
            yield StreamChunk(
                type="error",
                error="Claude Code backend cannot accept assistant messages - it maintains its own conversation history",
                source="claude_code",
            )
            return

        if not user_messages:
            log_stream_chunk(
                "backend.claude_code",
                "error",
                "No user messages found to send to Claude Code",
                agent_id,
            )
            yield StreamChunk(
                type="error",
                error="No user messages found to send to Claude Code",
                source="claude_code",
            )
            return

        # Combine all user messages into a single query
        user_contents = []
        for user_msg in user_messages:
            content = user_msg.get("content", "").strip()
            if content:
                user_contents.append(content)

        if user_contents:
            # Join multiple user messages with newlines
            combined_query = "\n\n".join(user_contents)

            # Windows workaround: Inject pending system prompt into first user message
            # This avoids Windows CreateProcess command-line length limits
            if hasattr(self, "_pending_system_prompt") and self._pending_system_prompt:
                logger.info("[ClaudeCodeBackend] Injecting pending system prompt into first user message")
                combined_query = f"""<system_instructions>

                {self._pending_system_prompt}

                </system_instructions>
                ---
                {combined_query}"""

                # Clear the pending prompt after injection
                self._pending_system_prompt = None

            log_backend_agent_message(
                agent_id or "default",
                "SEND",
                {"system": workflow_system_prompt, "user": combined_query},
                backend_name=self.get_provider_name(),
            )

            # Create span for LLM interaction tracing
            tracer = get_tracer()
            model_name = self.config.get("model") or "claude-code-default"
            llm_span_attributes = {
                "llm.provider": "claude_code",
                "llm.model": model_name,
                "llm.operation": "stream",
                "gen_ai.system": "anthropic",
                "gen_ai.request.model": model_name,
            }
            if agent_id:
                llm_span_attributes["massgen.agent_id"] = agent_id
            # Get round tracking from context variable (set by orchestrator via set_current_round)
            llm_round_number, llm_round_type = get_current_round()
            if llm_round_number is not None:
                llm_span_attributes["massgen.round"] = llm_round_number
            if llm_round_type:
                llm_span_attributes["massgen.round_type"] = llm_round_type

            # Enter span context - will be closed when ResultMessage is received or on error
            # Note: tracer.span() returns a context manager, so we need to store it
            # and capture the actual span object from __enter__()
            llm_span_cm = tracer.span("llm.claude_code.stream", attributes=llm_span_attributes)
            llm_span = llm_span_cm.__enter__()
            llm_span_open = True

            await client.query(combined_query)
            logger.info(f"[ClaudeCodeBackend] Query sent ({len(combined_query)} chars), waiting for response...")

        else:
            log_stream_chunk("backend.claude_code", "error", "All user messages were empty", agent_id)
            yield StreamChunk(type="error", error="All user messages were empty", source="claude_code")
            return

        # Stream response and convert to MassGen StreamChunks
        accumulated_content = ""
        workflow_tool_calls_from_mcp: list[dict[str, Any]] = []
        try:
            async for message in client.receive_response():
                if isinstance(message, (AssistantMessage, UserMessage)):
                    # Process assistant message content
                    for block in message.content:
                        if isinstance(block, ThinkingBlock):
                            # Extended thinking content (summarized for Claude 4 models)
                            thinking_text = block.thinking
                            if thinking_text:
                                log_stream_chunk("backend.claude_code", "reasoning", thinking_text, agent_id)
                                yield StreamChunk(
                                    type="reasoning",
                                    content=thinking_text,
                                    reasoning_delta=thinking_text,
                                    source="claude_code",
                                )
                                # Add to streaming buffer for compression recovery
                                self._append_reasoning_to_buffer(thinking_text)

                        elif isinstance(block, TextBlock):
                            accumulated_content += block.text

                            # Yield content chunk
                            log_backend_agent_message(
                                agent_id or "default",
                                "RECV",
                                {"content": block.text},
                                backend_name=self.get_provider_name(),
                            )
                            log_stream_chunk("backend.claude_code", "content", block.text, agent_id)
                            yield StreamChunk(type="content", content=block.text, source="claude_code")
                            # Add to streaming buffer for compression recovery
                            self._append_to_streaming_buffer(block.text)
                            # Also add to execution trace as content (model's text output)
                            # This is distinct from ThinkingBlock which would be reasoning
                            if self._execution_trace:
                                self._execution_trace.add_content(block.text)

                        elif isinstance(block, ToolUseBlock):
                            # Claude Code's builtin tool usage
                            log_backend_activity(
                                self.get_provider_name(),
                                f"Builtin tool called: {block.name}",
                                {"tool_id": block.id},
                                agent_id=agent_id,
                            )
                            log_stream_chunk(
                                "backend.claude_code",
                                "tool_use",
                                {"name": block.name, "input": block.input},
                                agent_id,
                            )

                            # Capture workflow tools called as MCP (agent confusion fallback).
                            # When workflow tools are text-based (not MCP), the agent may
                            # still try to call them as MCP tools after using submit_checklist.
                            # Extract the bare tool name and capture as a workflow call.
                            if not self._has_workflow_mcp:
                                from ..tool.workflow_toolkits.base import (
                                    WORKFLOW_TOOL_NAMES as _WF_NAMES,
                                )

                                _bare = block.name.rsplit("__", 1)[-1] if "__" in block.name else block.name
                                if _bare in _WF_NAMES:
                                    _wf_args = block.input if isinstance(block.input, dict) else {}
                                    workflow_tool_calls_from_mcp.append(
                                        {
                                            "id": f"call_{block.id}",
                                            "type": "function",
                                            "function": {
                                                "name": _bare,
                                                "arguments": json.dumps(_wf_args),
                                            },
                                        },
                                    )
                                    logger.info(
                                        f"ClaudeCode: captured workflow tool from MCP-style call: " f"{block.name} -> {_bare}",
                                    )

                            # Track tool_id -> tool_name for ToolResultBlock matching
                            self._tool_id_to_name[block.id] = block.name
                            self._tool_start_times[block.id] = time.time()

                            # Emit structured tool_start event for TUI event pipeline
                            from ..logger_config import (
                                get_event_emitter as _get_emitter,
                            )

                            _emitter = _get_emitter()
                            if _emitter:
                                tool_args = block.input if isinstance(block.input, dict) else {"input": block.input}
                                _emitter.emit_tool_start(
                                    tool_id=block.id,
                                    tool_name=block.name,
                                    args=tool_args,
                                    server_name=None,
                                    agent_id=agent_id,
                                )

                            # Yield tool status chunks for non-Textual displays
                            # (Textual TUI uses structured events above instead)
                            yield StreamChunk(
                                type="mcp_status",
                                status="mcp_tool_called",
                                content=f"Calling {block.name}...",
                                source="claude_code",
                                tool_call_id=block.id,
                            )

                            args_str = json.dumps(block.input) if isinstance(block.input, dict) else str(block.input)
                            yield StreamChunk(
                                type="mcp_status",
                                status="function_call",
                                content=f"Arguments for Calling {block.name}: {args_str}",
                                source="claude_code",
                                tool_call_id=block.id,
                            )

                            # Add to streaming buffer for compression recovery
                            tool_args = block.input if isinstance(block.input, dict) else {"input": block.input}
                            self._append_tool_call_to_buffer([{"name": block.name, "arguments": tool_args}])

                        elif isinstance(block, ToolResultBlock):
                            # Tool result from Claude Code
                            # Look up tool name from our tracking map
                            tool_name = self._tool_id_to_name.pop(block.tool_use_id, "unknown")
                            elapsed = time.time() - self._tool_start_times.pop(block.tool_use_id, time.time())

                            is_error = block.is_error
                            result_str = str(block.content) if block.content else ""

                            # Check if this is a workflow MCP tool result
                            if self._has_workflow_mcp and tool_name.startswith("mcp__massgen_workflow_tools__"):
                                workflow_call = self._try_extract_workflow_mcp_result(result_str)
                                if workflow_call:
                                    workflow_tool_calls_from_mcp.append(workflow_call)
                                    logger.info(f"ClaudeCode: captured workflow tool call from MCP: {workflow_call['function']['name']}")
                                    continue  # Don't emit as regular content

                            log_stream_chunk(
                                "backend.claude_code",
                                "tool_result",
                                {"tool_name": tool_name, "is_error": is_error, "content": result_str[:200]},
                                agent_id,
                            )

                            # Emit structured tool_complete event for TUI event pipeline
                            from ..logger_config import (
                                get_event_emitter as _get_emitter,
                            )

                            _emitter = _get_emitter()
                            if _emitter:
                                _emitter.emit_tool_complete(
                                    tool_id=block.tool_use_id,
                                    tool_name=tool_name,
                                    result=result_str,
                                    elapsed_seconds=elapsed,
                                    status="error" if is_error else "success",
                                    is_error=is_error,
                                    agent_id=agent_id,
                                )

                            # Add to streaming buffer for compression recovery
                            self._append_tool_to_buffer(
                                tool_name=tool_name,
                                result_text=result_str,
                                is_error=is_error,
                            )

                    # Emit workflow tool calls (prefer MCP results, fallback to text parsing)
                    if workflow_tool_calls_from_mcp:
                        logger.info(f"ClaudeCode: {len(workflow_tool_calls_from_mcp)} workflow tool call(s) from MCP server")
                        yield StreamChunk(
                            type="tool_calls",
                            tool_calls=workflow_tool_calls_from_mcp,
                            source="claude_code",
                        )
                    else:
                        workflow_tool_calls = self._parse_workflow_tool_calls(accumulated_content)
                        if workflow_tool_calls:
                            log_stream_chunk(
                                "backend.claude_code",
                                "tool_calls",
                                workflow_tool_calls,
                                agent_id,
                            )
                            yield StreamChunk(
                                type="tool_calls",
                                tool_calls=workflow_tool_calls,
                                source="claude_code",
                            )

                    # Yield complete message
                    log_stream_chunk(
                        "backend.claude_code",
                        "complete_message",
                        accumulated_content[:200] if len(accumulated_content) > 200 else accumulated_content,
                        agent_id,
                    )
                    yield StreamChunk(
                        type="complete_message",
                        complete_message={
                            "role": "assistant",
                            "content": accumulated_content,
                        },
                        source="claude_code",
                    )

                elif isinstance(message, SystemMessage):
                    # System status updates
                    self._track_session_info(message=message)
                    log_stream_chunk(
                        "backend.claude_code",
                        "backend_status",
                        {"subtype": message.subtype, "data": message.data},
                        agent_id,
                    )
                    yield StreamChunk(
                        type="backend_status",
                        status=message.subtype,
                        content=json.dumps(message.data),
                        source="claude_code",
                    )

                elif isinstance(message, ResultMessage):
                    # Track session ID from server response
                    self._track_session_info(message)

                    # Update token usage using ResultMessage data
                    self.update_token_usage_from_result_message(message)

                    # Log structured token usage for observability
                    if message.usage:
                        usage_data = message.usage
                        if isinstance(usage_data, dict):
                            input_tokens = (usage_data.get("input_tokens", 0) or 0) + (usage_data.get("cache_read_input_tokens", 0) or 0) + (usage_data.get("cache_creation_input_tokens", 0) or 0)
                            output_tokens = usage_data.get("output_tokens", 0) or 0
                            cached_tokens = usage_data.get("cache_read_input_tokens", 0) or 0
                        else:
                            input_tokens = (
                                (getattr(usage_data, "input_tokens", 0) or 0) + (getattr(usage_data, "cache_read_input_tokens", 0) or 0) + (getattr(usage_data, "cache_creation_input_tokens", 0) or 0)
                            )
                            output_tokens = getattr(usage_data, "output_tokens", 0) or 0
                            cached_tokens = getattr(usage_data, "cache_read_input_tokens", 0) or 0

                        log_token_usage(
                            agent_id=agent_id or "unknown",
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            reasoning_tokens=0,  # Claude Code doesn't expose this separately
                            cached_tokens=cached_tokens,
                            estimated_cost=message.total_cost_usd or 0.0,
                            model=self.config.get("model") or "claude-code-default",
                        )

                    # Close LLM span on successful completion
                    if llm_span_open and llm_span_cm:
                        if message.duration_ms:
                            llm_span.set_attribute("llm.duration_ms", message.duration_ms)
                        if message.total_cost_usd:
                            llm_span.set_attribute("llm.cost_usd", message.total_cost_usd)
                        llm_span_cm.__exit__(None, None, None)
                        llm_span_open = False

                    # Yield completion
                    log_stream_chunk(
                        "backend.claude_code",
                        "complete_response",
                        {
                            "session_id": message.session_id,
                            "cost_usd": message.total_cost_usd,
                        },
                        agent_id,
                    )
                    yield StreamChunk(
                        type="complete_response",
                        complete_message={
                            "session_id": message.session_id,
                            "duration_ms": message.duration_ms,
                            "cost_usd": message.total_cost_usd,
                            "usage": message.usage,
                            "is_error": message.is_error,
                        },
                        source="claude_code",
                    )

                    # Finalize streaming buffer
                    self._finalize_streaming_buffer(agent_id=agent_id)

                    # Final done signal
                    log_stream_chunk("backend.claude_code", "done", None, agent_id)
                    yield StreamChunk(type="done", source="claude_code")
                    break

        except Exception as e:
            error_msg = str(e)
            import traceback

            logger.error(f"[ClaudeCodeBackend] Full traceback for streaming error:\n{traceback.format_exc()}")

            # Finalize streaming buffer even on error
            self._finalize_streaming_buffer(agent_id=agent_id)

            # Close LLM span on error
            if llm_span_open and llm_span_cm:
                llm_span.set_attribute("error", True)
                llm_span.set_attribute("error.message", error_msg[:500])
                llm_span_cm.__exit__(type(e), e, e.__traceback__)
                llm_span_open = False

            # Provide helpful Windows-specific guidance
            if "git-bash" in error_msg.lower() or "bash.exe" in error_msg.lower():
                error_msg += (
                    "\n\nWindows Setup Required:\n"
                    "1. Install Git Bash: https://git-scm.com/downloads/win\n"
                    "2. Ensure git-bash is in PATH, or set: "
                    "CLAUDE_CODE_GIT_BASH_PATH=C:\\Program Files\\Git\\bin\\bash.exe"
                )
            elif "exit code 1" in error_msg and "win32" in str(sys.platform):
                error_msg += "\n\nThis may indicate missing git-bash on Windows. Please install Git Bash from https://git-scm.com/downloads/win"

            log_stream_chunk("backend.claude_code", "error", error_msg, agent_id)
            yield StreamChunk(
                type="error",
                error=f"Claude Code streaming error: {str(error_msg)}",
                source="claude_code",
            )

    def _track_session_info(self, message) -> None:
        """Track session information from Claude Code server responses.

        Extracts and stores session ID, working directory, and other session
        metadata from ResultMessage and SystemMessage responses to enable
        session continuation and state management across multiple interactions.

        Args:
            message: Message from Claude Code (ResultMessage or SystemMessage)
                    potentially containing session information
        """
        if ResultMessage is not None and isinstance(message, ResultMessage):
            # ResultMessage contains definitive session information
            if hasattr(message, "session_id") and message.session_id:
                self._current_session_id = message.session_id

        elif SystemMessage is not None and isinstance(message, SystemMessage):
            # SystemMessage may contain session state updates
            if hasattr(message, "data") and isinstance(message.data, dict):
                # Extract session ID from system message data
                if "session_id" in message.data and message.data["session_id"]:
                    self._current_session_id = message.data["session_id"]

                # Extract working directory from system message data
                if "cwd" in message.data and message.data["cwd"]:
                    self._cwd = message.data["cwd"]

    async def interrupt(self):
        """Send interrupt signal to gracefully stop the current operation.

        This tells the Claude Code CLI to stop its current work cleanly,
        avoiding noisy stream-closed errors that occur when the process
        is killed abruptly.
        """
        if self._client is not None:
            try:
                await self._client.interrupt()
            except Exception:
                pass  # Ignore errors during interrupt

    async def disconnect(self):
        """Disconnect the ClaudeSDKClient and clean up resources.

        Properly closes the connection and resets internal state.
        Should be called when the backend is no longer needed.
        """
        await self._cancel_all_background_tool_jobs()

        if self._client is not None:
            try:
                await self._client.disconnect()
            except asyncio.CancelledError:
                pass  # anyio cancel scope may raise CancelledError
            except Exception:
                pass  # Ignore cleanup errors
            finally:
                # Reverse anyio cancel scope propagation (see reset_state docstring)
                for task in asyncio.all_tasks():
                    if not task.done() and task.cancelling() > 0:
                        task.uncancel()
                self._client = None
                self._current_session_id = None

    def __del__(self):
        """Cleanup on destruction.

        Note: This won't work for async cleanup in practice.
        Use explicit disconnect() calls for proper resource cleanup.
        """
        # Note: This won't work for async cleanup, but serves as documentation
        # Real cleanup should be done via explicit disconnect() calls
