"""
OpenAI Codex Backend - Integration with OpenAI Codex CLI for MassGen.

This backend provides integration with OpenAI's Codex CLI through subprocess
wrapping and JSON event stream parsing. Supports OAuth authentication via
ChatGPT subscription or API key authentication.

Key Features:
- OAuth authentication via ChatGPT subscription (browser or device flow)
- API key fallback (OPENAI_API_KEY)
- Session persistence and resumption
- JSON event stream parsing for real-time streaming
- MCP tool support via project-scoped .codex/config.toml in workspace
- System prompt injection via .codex/AGENTS.md + model_instructions_file
- Skills mirroring into .codex/skills for CODEX_HOME-scoped discovery
- Full conversation context maintained across turns
- Uses CODEX_HOME env var to isolate config from user's global ~/.codex/

Architecture:
- Wraps `codex exec --json` CLI command
- Parses JSONL event stream for streaming responses
- Tracks session_id for multi-turn conversation continuity
- Delegates tool execution to Codex CLI (MCP servers, file ops, etc.)

Tool & Sandbox Design Decisions:
- Codex has native tools: shell (command exec), apply_patch (file edit),
  web_search, image_view. These are NOT duplicated by MassGen MCP tools.
- MassGen disables the native view_image tool in generated .codex/config.toml
  via [tools].view_image = false.
- MassGen's filesystem/command_line MCPs are SKIPPED for Codex since Codex
  handles file ops and shell natively via its own sandbox.
- MassGen-specific MCPs (planning, memory, workspace_tools for media gen,
  custom tools) ARE injected via .codex/config.toml [mcp_servers].
- For docker execution mode: the Codex CLI runs inside a MassGen Docker
  container (via DockerManager exec_create/exec_start with streaming).
  Uses --sandbox danger-full-access since the container provides isolation.
  Host ~/.codex/ is mounted read-only for OAuth token access.

Sandbox Limitations (IMPORTANT):
- Codex sandbox is OS-level (Seatbelt on macOS, Landlock on Linux).
- The OS sandbox ONLY restricts WRITES - reads are NOT blocked!
- This means Codex can read files from anywhere on the filesystem, including
  sensitive directories outside the workspace and context_paths.
- MassGen can add limited Bash-only guardrails via native Codex hooks, but it
  still cannot fully intercept Codex-native Write/WebSearch/MCP/non-shell tool
  calls.
- For security-sensitive workloads, PREFER DOCKER MODE which provides full
  filesystem isolation via container boundaries.
- When running without Docker, the writable_roots config restricts writes
  to workspace + context_paths with write permission, but reads are unrestricted.

Requirements:
- Codex CLI installed: npm install -g @openai/codex
- Either: ChatGPT Plus/Pro subscription OR OPENAI_API_KEY

Authentication Flow:
1. Check OPENAI_API_KEY environment variable
2. If not found, check for cached OAuth tokens at ~/.codex/auth.json
3. If not found, initiate OAuth flow (browser or device code)
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import time
import uuid
from collections.abc import AsyncGenerator, Callable
from pathlib import Path
from typing import Any

try:
    import tomli_w
except ImportError:
    tomli_w = None

from ..logger_config import get_event_emitter, logger
from ..mcp_tools.backend_utils import MCPResourceManager
from ..utils.redact_secrets import redact_secrets_in_text
from ._streaming_buffer_mixin import StreamingBufferMixin
from .base import (
    FilesystemSupport,
    LLMBackend,
    StreamChunk,
    get_multimodal_tool_definitions,
    parse_workflow_tool_calls,
)
from .native_tool_mixin import NativeToolBackendMixin

# Large tool results and final answers can produce oversized JSONL events.
# Bump the asyncio StreamReader limit so line-based parsing doesn't trip
# LimitOverrunError before we can process the event.
SUBPROCESS_STREAM_LIMIT = 4 * 1024 * 1024


class CodexBackend(StreamingBufferMixin, NativeToolBackendMixin, LLMBackend):
    """OpenAI Codex backend using CLI subprocess with JSON event stream.

    Provides streaming interface to Codex with OAuth support and session
    persistence. Uses `codex exec --json` for programmatic control.
    """

    # Codex event types mapped to StreamChunk types (reference only;
    # actual parsing is in _parse_codex_event / _parse_item)
    EVENT_TYPE_MAP = {
        "thread.started": "agent_status",
        "turn.started": "agent_status",
        "turn.completed": "done",
        "turn.failed": "error",
        "item.started": "content",  # wrapper: check nested item.type
        "item.completed": "content",  # wrapper: check nested item.type
        "error": "error",
    }
    RUNTIME_INPUT_PRIORITY_GUIDANCE = (
        "## Runtime Input Priority\n"
        "When a tool result contains a line starting with `[Human Input]:`, "
        "treat it as a high-priority runtime instruction from the user.\n"
        "Apply that instruction before continuing your previous plan.\n"
        "In your next response, explicitly state how you incorporated it.\n"
        "If you cannot apply it safely, briefly explain why and continue with "
        "the best valid alternative."
    )

    def __init__(self, api_key: str | None = None, **kwargs):
        """Initialize CodexBackend.

        Args:
            api_key: OpenAI API key (falls back to OPENAI_API_KEY env var).
                    If None, will attempt OAuth authentication.
            **kwargs: Additional configuration options including:
                - model: Model name (default: gpt-5.4)
                - model_reasoning_effort: Reasoning effort level (low, medium, high, xhigh)
                - cwd: Current working directory for Codex
                - system_prompt: System prompt to prepend
                - approval_mode: Codex approval mode (full-auto, full-access, suggest)
        """
        super().__init__(api_key, **kwargs)
        # The base class may have injected the command_line MCP server (when
        # enable_mcp_command_line=True). In Docker mode the CLI runs *inside*
        # the container, so the MCP server script (a host-only path) and the
        # massgen package (not installed in the container) are both unavailable.
        # Remove it here; Codex's built-in tools cover all execution needs.
        if kwargs.get("command_line_execution_mode") == "docker":
            self._remove_injected_command_line_mcp()
        self.__init_native_tool_mixin__()
        self._init_native_hook_adapter(
            "massgen.mcp_tools.native_hook_adapters.CodexNativeHookAdapter",
        )

        # Authentication setup
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.use_oauth = not bool(self.api_key)
        self.auth_file = Path.home() / ".codex" / "auth.json"

        # Session management
        self.session_id: str | None = None
        self._session_file: Path | None = None

        # Configuration
        self.model = kwargs.get("model", "gpt-5.4")
        # Prefer native Codex setting, but accept OpenAI-style nesting for compatibility:
        # backend.reasoning.effort -> model_reasoning_effort
        self.model_reasoning_effort = kwargs.get("model_reasoning_effort")  # low, medium, high, xhigh
        if self.model_reasoning_effort is None:
            reasoning_cfg = kwargs.get("reasoning")
            if isinstance(reasoning_cfg, dict):
                effort = reasoning_cfg.get("effort")
                if isinstance(effort, str) and effort.strip():
                    self.model_reasoning_effort = effort.strip()
        if self.model_reasoning_effort is None and str(self.model).strip().lower() == "gpt-5.4":
            # GPT-5.4 supports xhigh reasoning, but default to high for a
            # better cost/quality tradeoff unless the caller explicitly overrides.
            self.model_reasoning_effort = "high"
        self._config_cwd = kwargs.get("cwd")  # May be relative; resolved at execution time

        # Mid-round interrupt-and-resume steering (kill + `codex exec resume`).
        self._enable_interrupt_resume = kwargs.get("enable_interrupt_resume", True)
        self._interrupt_poll_seconds = float(kwargs.get("interrupt_poll_seconds", 2.0))
        self._max_interrupts_per_turn = int(kwargs.get("max_interrupts_per_turn", 25))
        self.system_prompt = kwargs.get("system_prompt", "")
        self.approval_mode = kwargs.get("approval_mode", "full-auto")
        self.mcp_servers = kwargs.get("mcp_servers", [])
        self._workspace_config_written = False
        self._custom_tools_specs_path: Path | None = None
        self._background_wait_interrupt_file: Path | None = None
        self._active_background_wait_calls: set[str] = set()
        self._background_wait_interrupt_provider: Callable[[str], Any] | None = None
        self._background_mcp_client = None
        self._background_mcp_initialized = False
        self._background_mcp_init_error: str | None = None

        # Hook IPC for MCP server-level PostToolUse injection
        self._hook_sequence: int = 0

        # Agent ID (needed for Docker container lookup)
        self.agent_id = kwargs.get("agent_id")

        # Tool event tracking (for emit_tool_start/emit_tool_complete)
        self._tool_start_times: dict[str, float] = {}
        self._tool_id_to_name: dict[str, str] = {}
        self._workflow_call_emitted_this_turn = False
        self._workflow_mcp_item_ids_emitted: set[str] = set()
        self._last_turn_missing_workflow_call = False

        # Docker execution mode
        self._docker_execution = kwargs.get("command_line_execution_mode") == "docker"
        self._docker_codex_verified = False
        adapter = self.get_native_hook_adapter()
        if adapter and hasattr(adapter, "hook_dir"):
            adapter.hook_dir = self.get_hook_dir()
        if adapter and hasattr(adapter, "docker_mode"):
            adapter.docker_mode = self._docker_execution

        # Custom tools: wrap as MCP server for Codex to connect to
        custom_tools = list(kwargs.get("custom_tools", []))

        # Register multimodal tools if enabled (Codex doesn't inherit from
        # BaseWithCustomToolAndMCP which normally handles this)
        enable_multimodal = self.config.get(
            "enable_multimodal_tools",
            False,
        ) or kwargs.get("enable_multimodal_tools", False)
        if enable_multimodal:
            custom_tools.extend(get_multimodal_tool_definitions())
            logger.info("Codex backend: multimodal tools enabled (read_media, generate_media)")

        # Codex exposes MassGen custom tools through an MCP wrapper server.
        # Always configure this server so framework background lifecycle tools
        # are available even when no user custom tools are defined.
        self._setup_custom_tools_mcp(custom_tools)

        # Verify Codex CLI is available (skip in docker mode — resolved inside container)
        if self._docker_execution:
            self._codex_path = "codex"
        else:
            self._codex_path = self._find_codex_cli()
            if not self._codex_path:
                raise RuntimeError(
                    "Codex CLI not found. Install with: npm install -g @openai/codex",
                )

        # Ensure authentication is available
        if self.use_oauth and not self._has_cached_credentials():
            logger.warning(
                "No API key or cached OAuth credentials found. " "Authentication will be required on first use.",
            )

    def _remove_injected_command_line_mcp(self) -> None:
        """Remove the command_line MCP server injected by the base class, if present."""
        mcp_servers = self.config.get("mcp_servers")
        if not mcp_servers:
            return
        if isinstance(mcp_servers, list):
            filtered = [s for s in mcp_servers if not (isinstance(s, dict) and s.get("name") == "command_line")]
            if len(filtered) < len(mcp_servers):
                self.config["mcp_servers"] = filtered
                logger.info("Codex Docker mode: removed command_line MCP server (host-only paths not available in container)")
        elif isinstance(mcp_servers, dict) and "command_line" in mcp_servers:
            del mcp_servers["command_line"]
            logger.info("Codex Docker mode: removed command_line MCP server (host-only paths not available in container)")

    @property
    def cwd(self) -> str:
        """Resolve the working directory, preferring filesystem_manager's workspace."""
        if self.filesystem_manager:
            return str(Path(str(self.filesystem_manager.get_current_workspace())).resolve())
        return self._config_cwd or os.getcwd()

    def _find_codex_cli(self) -> str | None:
        """Find the Codex CLI executable."""
        codex_path = shutil.which("codex")
        if codex_path:
            return codex_path

        # Check common npm global paths
        npm_paths = [
            Path.home() / ".npm-global" / "bin" / "codex",
            Path("/usr/local/bin/codex"),
            Path.home() / "node_modules" / ".bin" / "codex",
        ]
        for path in npm_paths:
            if path.exists():
                return str(path)

        return None

    def _resolve_background_wait_interrupt_file(self) -> Path:
        """Return the per-workspace interrupt signal file for wait tool calls."""
        signal_path = Path(self.cwd) / ".codex" / "background_wait_interrupt.json"
        signal_path.parent.mkdir(parents=True, exist_ok=True)
        self._background_wait_interrupt_file = signal_path
        return signal_path

    def is_background_wait_active(self) -> bool:
        """Return whether a wait_for_background_tool call is currently in flight."""
        return bool(self._active_background_wait_calls)

    def notify_background_wait_interrupt(self, payload: dict[str, Any]) -> bool:
        """Signal the custom-tools server to interrupt an active wait call.

        Returns True when a signal was written, False when no active wait exists
        or the signal could not be written.
        """
        if not self.is_background_wait_active():
            return False

        signal_path = self._resolve_background_wait_interrupt_file()
        normalized_payload = {
            "interrupt_reason": str(
                payload.get("interrupt_reason", "runtime_injection_available"),
            ),
            "injected_content": payload.get("injected_content"),
        }
        if normalized_payload["injected_content"] is not None:
            normalized_payload["injected_content"] = str(
                normalized_payload["injected_content"],
            )

        tmp_path = signal_path.with_suffix(".tmp")
        try:
            tmp_path.write_text(
                json.dumps(normalized_payload, default=str),
                encoding="utf-8",
            )
            tmp_path.replace(signal_path)
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "Failed writing Codex wait interrupt signal at %s: %s",
                signal_path,
                e,
                exc_info=True,
            )
            return False

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

        agent_id = str(self.agent_id or "unknown")
        try:
            payload = self._background_wait_interrupt_provider(agent_id)
            if asyncio.iscoroutine(payload):
                payload = await payload
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "[CodexBackend] Wait interrupt provider failed for %s: %s",
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

    async def _maybe_signal_background_wait_interrupt(self, wait_call_id: str) -> None:
        """Signal wait interruption when runtime payload is already pending."""
        if not self.is_background_wait_active():
            return

        interrupt_payload = await self._get_background_wait_interrupt_payload()
        if not interrupt_payload:
            return

        signaled = self.notify_background_wait_interrupt(interrupt_payload)
        if signaled:
            logger.info(
                "[CodexBackend] Background wait interrupt signaled on wait start (%s)",
                wait_call_id,
            )

    def _has_cached_credentials(self) -> bool:
        """Check if OAuth tokens exist at ~/.codex/auth.json."""
        return self.auth_file.exists()

    # ------------------------------------------------------------------
    # MCP server-level hook IPC
    # ------------------------------------------------------------------

    def supports_mcp_server_hooks(self) -> bool:
        """Return True — Codex uses MCP server middleware for PostToolUse injection."""
        return True

    def supports_interrupt_resume(self) -> bool:
        """Codex can be killed mid-turn and resumed via `codex exec resume <id>`,
        preserving full conversation context. We use this to deliver steering /
        mid-round injection at ANY point in a long round (the MCP-middleware path
        only fires if the agent calls a MassGen MCP tool while a payload is
        pending — unreliable across 30-min rounds)."""
        return getattr(self, "_enable_interrupt_resume", True)

    @staticmethod
    async def _terminate_proc(proc: asyncio.subprocess.Process, grace: float = 2.0) -> None:
        """SIGTERM the subprocess and wait up to ``grace`` before SIGKILL."""
        if proc.returncode is not None:
            return
        try:
            proc.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(proc.wait(), timeout=grace)
        except TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                return
            try:
                await asyncio.wait_for(proc.wait(), timeout=grace)
            except TimeoutError:
                logger.error("Codex: process did not exit after SIGKILL")

    def get_hook_dir(self) -> Path:
        """Return the directory used for hook IPC files."""
        return Path(self.cwd) / ".codex"

    def write_post_tool_use_hook(
        self,
        content: str,
        tool_matcher: str = "*",
        ttl_seconds: float = 30.0,
    ) -> None:
        """Atomic write of hook_post_tool_use.json for MCP middleware to consume.

        Args:
            content: Injection text to append to the next tool result.
            tool_matcher: Glob pattern for which tools should receive the injection.
            ttl_seconds: Time-to-live before the payload expires.
        """
        self._hook_sequence += 1
        hook_dir = self.get_hook_dir()
        hook_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "inject": {"content": content, "strategy": "tool_result"},
            "tool_matcher": tool_matcher,
            "expires_at": time.time() + ttl_seconds,
            "sequence": self._hook_sequence,
        }

        hook_file = hook_dir / "hook_post_tool_use.json"
        tmp_file = hook_file.with_suffix(".tmp")
        tmp_file.write_text(json.dumps(payload), encoding="utf-8")
        tmp_file.replace(hook_file)

        logger.info(
            f"Wrote hook_post_tool_use.json (seq={self._hook_sequence}, {len(content)} chars)",
        )

    def read_unconsumed_hook_content(self) -> str | None:
        """Read and remove any unconsumed hook payload.

        Called after a streaming round ends. If the hook file still exists,
        the MCP middleware never consumed it. Returns the injection content
        so the orchestrator can carry it forward to the next round.
        """
        hook_file = self.get_hook_dir() / "hook_post_tool_use.json"
        try:
            data = json.loads(hook_file.read_text(encoding="utf-8"))
            hook_file.unlink(missing_ok=True)
            # Honor payload freshness: a stale carryforward could trigger an
            # unexpected interrupt/resume on the next round. Mirror the
            # middleware's expires_at handling (hook_middleware.py).
            expires_at = data.get("expires_at")
            if expires_at is not None:
                try:
                    if time.time() > float(expires_at):
                        logger.debug(f"Dropping expired unconsumed hook (expires_at={expires_at})")
                        return None
                except (TypeError, ValueError):
                    logger.warning(f"Invalid expires_at {expires_at!r} in hook file; treating as non-expiring")
            inject = data.get("inject", {})
            content = inject.get("content")
            if content:
                logger.info(
                    f"Read unconsumed hook content ({len(content)} chars) — carrying forward",
                )
            return content
        except FileNotFoundError:
            return None
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed reading unconsumed hook file: {e}")
            hook_file.unlink(missing_ok=True)
            return None

    def clear_hook_files(self) -> None:
        """Remove stale hook files. Called at start of each turn."""
        hook_dir = self.get_hook_dir()
        for filename in ("hook_post_tool_use.json", "hook_post_tool_use.tmp"):
            (hook_dir / filename).unlink(missing_ok=True)

    async def _ensure_authenticated(self) -> None:
        """Ensure Codex is authenticated before making requests."""
        if self.api_key:
            # API key auth - set environment variable
            os.environ["OPENAI_API_KEY"] = self.api_key
            return

        if self._has_cached_credentials():
            # OAuth tokens exist
            return

        # Need to authenticate
        logger.info("Codex authentication required. Initiating OAuth flow...")
        await self._initiate_oauth_flow()

    async def _initiate_oauth_flow(self, use_device_flow: bool = False) -> None:
        """Trigger Codex OAuth authentication.

        Args:
            use_device_flow: If True, use device code flow (for headless environments).
                           If False, use browser-based OAuth.
        """
        if use_device_flow:
            # Device code flow for headless/SSH environments
            cmd = [self._codex_path, "login", "--device-auth"]
            logger.info(
                "Starting device code authentication. " "Follow the instructions to complete login.",
            )
        else:
            # Browser-based OAuth
            cmd = [self._codex_path, "login"]
            logger.info("Opening browser for Codex authentication...")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            raise RuntimeError(f"Codex authentication failed: {error_msg}")

        # Device flow prints instructions to stdout
        if use_device_flow and stdout:
            print(stdout.decode())

        logger.info("Codex authentication successful.")

    def _build_custom_tools_mcp_env(self) -> dict[str, str]:
        """Build environment variables for the custom tools MCP server.

        Mirrors Docker credential configuration when available; otherwise
        returns only the FastMCP banner suppression flag.
        """
        env_vars = {"FASTMCP_SHOW_CLI_BANNER": "false"}

        if not self.config:
            return env_vars

        creds = self.config.get("command_line_docker_credentials") or {}
        if not creds:
            return env_vars

        # Helper to load .env files (simple KEY=VALUE lines)
        def _load_env_file(env_file_path: Path) -> dict[str, str]:
            loaded: dict[str, str] = {}
            try:
                with open(env_file_path) as f:
                    for line_num, line in enumerate(f, start=1):
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip()
                        # Strip surrounding quotes (same as DockerManager)
                        if value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]
                        elif value.startswith("'") and value.endswith("'"):
                            value = value[1:-1]
                        if key:
                            loaded[key] = value
                        else:
                            logger.warning(f"⚠️ [Codex] Skipping invalid line {line_num} in {env_file_path}: {line}")
            except Exception as e:
                logger.warning(f"⚠️ [Codex] Failed to read env file {env_file_path}: {e}")
            return loaded

        # Pass all env vars if configured
        if creds.get("pass_all_env"):
            env_vars.update(os.environ)

        # Load from env_file (filtered if env_vars_from_file is set).
        # Search multiple locations (same as DockerManager) so subagent
        # workspaces that lack a local .env still pick up global keys.
        env_file = creds.get("env_file")
        if env_file:
            home_env = Path.home() / ".massgen" / ".env"
            provided_path = Path(env_file).expanduser().resolve()
            local_env = Path(".env").resolve()

            seen: set[Path] = set()
            candidates: list[Path] = []
            for p in [home_env, provided_path, local_env]:
                resolved = p.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    candidates.append(resolved)

            file_env: dict[str, str] = {}
            for env_path in candidates:
                if env_path.exists():
                    file_env.update(_load_env_file(env_path))

            if file_env:
                filter_list = creds.get("env_vars_from_file")
                if filter_list:
                    filtered_env = {k: v for k, v in file_env.items() if k in filter_list}
                    env_vars.update(filtered_env)
                else:
                    env_vars.update(file_env)
            elif not any(c.exists() for c in candidates):
                logger.warning(
                    f"⚠️ [Codex] Env file not found in any location: " f"{[str(c) for c in candidates]}",
                )

        # Pass specific env vars from host
        for var_name in creds.get("env_vars", []) or []:
            if var_name in os.environ:
                env_vars[var_name] = os.environ[var_name]
            else:
                logger.warning(f"⚠️ [Codex] Requested env var '{var_name}' not found in host environment")

        # Bridge Claude Code login state to MCP-launched subprocesses.
        # Codex Docker can mount ~/.claude into /home/massgen/.claude via
        # command_line_docker_credentials.mount: ["claude_config"].
        if "CLAUDE_CONFIG_DIR" not in env_vars:
            docker_mode = str(self.config.get("command_line_execution_mode", "")).lower() == "docker"
            mount_list = creds.get("mount", []) or []
            if docker_mode and "claude_config" in mount_list:
                env_vars["CLAUDE_CONFIG_DIR"] = "/home/massgen/.claude"

        # Always enforce banner suppression
        env_vars["FASTMCP_SHOW_CLI_BANNER"] = "false"
        return env_vars

    def _collect_background_mcp_servers(self) -> list[dict[str, Any]]:
        """Collect MCP server configs available for background target execution."""
        merged: list[dict[str, Any]] = []

        config_mcp = self.config.get("mcp_servers") if self.config else None
        if isinstance(config_mcp, dict):
            for name, server_cfg in config_mcp.items():
                if not isinstance(server_cfg, dict):
                    continue
                entry = server_cfg.copy()
                entry["name"] = name
                merged.append(entry)
        elif isinstance(config_mcp, list):
            for server_cfg in config_mcp:
                if isinstance(server_cfg, dict):
                    merged.append(server_cfg.copy())

        existing_names = {s.get("name") for s in merged if isinstance(s, dict)}
        for server_cfg in self.mcp_servers:
            if not isinstance(server_cfg, dict):
                continue
            name = server_cfg.get("name")
            if name in existing_names:
                continue
            merged.append(server_cfg.copy())

        filtered: list[dict[str, Any]] = []
        for server_cfg in merged:
            if not isinstance(server_cfg, dict):
                continue
            server_cfg = self._normalize_background_server_config(server_cfg)
            name = server_cfg.get("name")
            if not isinstance(name, str) or not name:
                continue
            if name == "massgen_custom_tools":
                continue
            if server_cfg.get("type") == "sdk":
                continue
            if "__sdk_server__" in server_cfg:
                continue
            filtered.append(server_cfg)

        return filtered

    @staticmethod
    def _normalize_background_server_config(server_cfg: dict[str, Any]) -> dict[str, Any]:
        """Rewrite server config details that only make sense in model-facing runtimes."""
        name = server_cfg.get("name")
        if not isinstance(name, str) or not name.startswith("subagent_"):
            return server_cfg

        args = server_cfg.get("args")
        if not isinstance(args, list):
            return server_cfg

        rewritten_args = CodexBackend._rewrite_subagent_runtime_mode_for_background(args)
        if rewritten_args is args:
            return server_cfg

        normalized = server_cfg.copy()
        normalized["args"] = rewritten_args
        return normalized

    @staticmethod
    def _rewrite_subagent_runtime_mode_for_background(args: list[Any]) -> list[Any]:
        """Host-side background clients should launch subagent MCP servers in isolated mode."""
        rewritten = list(args)
        changed = False

        for index, token in enumerate(rewritten[:-1]):
            if token != "--runtime-mode":
                continue
            runtime_mode = rewritten[index + 1]
            if str(runtime_mode).strip().lower() != "delegated":
                continue
            rewritten[index + 1] = "isolated"
            changed = True

        return rewritten if changed else args

    async def _get_background_mcp_client(self):
        """Create or return a host-side MCP client for orchestrator-managed tool calls.

        Codex owns the model-facing MCP connections internally via the CLI, but the
        orchestrator still needs a programmatic path for out-of-band operations such
        as managed round evaluator spawns. This mirrors the Claude Code backend's
        sidecar MCP client shape so the orchestrator can stay backend-agnostic.
        """
        if self._background_mcp_client:
            return self._background_mcp_client
        if self._background_mcp_initialized:
            return None

        servers_to_use = self._collect_background_mcp_servers()
        if not servers_to_use:
            self._background_mcp_initialized = True
            self._background_mcp_init_error = None
            return None

        try:
            max_tool_timeout = max(
                (server.get("tool_timeout_sec", 0) for server in servers_to_use if isinstance(server, dict)),
                default=0,
            )
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
                "[CodexBackend] Failed to initialize background MCP client: %s",
                e,
                exc_info=True,
            )
            return None

    async def _disconnect_background_mcp_client(self) -> None:
        """Disconnect any cached host-side MCP client and clear init state."""
        if self._background_mcp_client is not None:
            try:
                await self._background_mcp_client.disconnect()
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "[CodexBackend] Failed disconnecting background MCP client: %s",
                    e,
                )
            finally:
                self._background_mcp_client = None

        self._background_mcp_initialized = False
        self._background_mcp_init_error = None

    def _setup_custom_tools_mcp(self, custom_tools: list[dict[str, Any]]) -> None:
        """Wrap MassGen custom tools as an MCP server and add to mcp_servers.

        Writes a tool specs JSON file and creates an MCP server config entry
        that Codex can connect to via stdio transport.
        """
        try:
            from ..mcp_tools.custom_tools_server import (
                build_server_config,
                write_tool_specs,
            )
        except ImportError:
            logger.warning("custom_tools_server not available, skipping custom tools")
            return

        # Store raw config so specs can be re-written after workspace cleanup
        self._custom_tools_config = custom_tools

        # Write specs to workspace
        specs_path = Path(self.cwd) / ".codex" / "custom_tool_specs.json"
        write_tool_specs(
            custom_tools,
            specs_path,
            background_mcp_servers=self._collect_background_mcp_servers(),
        )
        self._custom_tools_specs_path = specs_path

        # Build MCP server config and add to mcp_servers
        server_config = build_server_config(
            tool_specs_path=specs_path,
            allowed_paths=[self.cwd],
            agent_id="codex",
            backend_type="codex",
            model=self.model,
            env=self._build_custom_tools_mcp_env(),
            wait_interrupt_file=self._resolve_background_wait_interrupt_file(),
            hook_dir=self.get_hook_dir(),
        )
        # Replace existing massgen_custom_tools entry if present
        self.mcp_servers = [s for s in self.mcp_servers if not (isinstance(s, dict) and s.get("name") == "massgen_custom_tools")]
        self.mcp_servers.append(server_config)
        logger.info(
            "Custom tools MCP server configured with %s user tool config(s) + background lifecycle tools",
            len(custom_tools),
        )

    def _write_workspace_config(self) -> None:
        """Write config.toml to workspace/.codex directory.

        This configures MCP servers and other settings for this agent's session.
        The CODEX_HOME env var is set to workspace/.codex when running Codex,
        so it reads this config instead of ~/.codex/config.toml.
        """
        config: dict[str, Any] = {}
        config_dir = Path(self.cwd) / ".codex"
        config_dir.mkdir(parents=True, exist_ok=True)
        adapter = self.get_native_hook_adapter()
        if adapter and hasattr(adapter, "hook_dir"):
            adapter.hook_dir = config_dir
        if adapter and hasattr(adapter, "docker_mode"):
            adapter.docker_mode = self._docker_execution

        # Model settings
        if self.model:
            config["model"] = self.model
        if self.model_reasoning_effort:
            config["model_reasoning_effort"] = self.model_reasoning_effort

        # Disable Codex's native image-reading tool globally for MassGen runs.
        config["tools"] = {"view_image": False}

        # Always write custom tool specs to current workspace (cwd may change between runs).
        # Includes framework background lifecycle tools even when user custom_tools is empty.
        if hasattr(self, "_custom_tools_config"):
            from ..mcp_tools.custom_tools_server import (
                build_server_config,
                write_tool_specs,
            )

            specs_path = config_dir / "custom_tool_specs.json"
            write_tool_specs(
                self._custom_tools_config,
                specs_path,
                background_mcp_servers=self._collect_background_mcp_servers(),
            )
            self._custom_tools_specs_path = specs_path
            # Update the MCP server config to point to current workspace
            for s in self.mcp_servers:
                if isinstance(s, dict) and s.get("name") == "massgen_custom_tools":
                    s.update(
                        build_server_config(
                            tool_specs_path=specs_path,
                            allowed_paths=[self.cwd],
                            agent_id="codex",
                            backend_type="codex",
                            model=self.model,
                            env=self._build_custom_tools_mcp_env(),
                            wait_interrupt_file=self._resolve_background_wait_interrupt_file(),
                            hook_dir=self.get_hook_dir(),
                        ),
                    )
                    break

        # Write checklist specs file and add stdio MCP config if checklist is active.
        # The orchestrator stores _checklist_state/_checklist_items on the backend;
        # we write the specs here because the workspace path is now resolved.
        if hasattr(self, "_checklist_state") and hasattr(self, "_checklist_items"):
            from ..mcp_tools.checklist_tools_server import (
                build_server_config as build_checklist_config,
            )
            from ..mcp_tools.checklist_tools_server import (
                write_checklist_specs,
            )

            specs_path = config_dir / "checklist_specs.json"
            write_checklist_specs(
                items=self._checklist_items,
                state=self._checklist_state,
                output_path=specs_path,
            )
            # Store path so orchestrator can sync state back (e.g. evaluator personas)
            self._checklist_specs_path = specs_path
            checklist_mcp = build_checklist_config(specs_path, hook_dir=self.get_hook_dir())
            # Replace any previous checklist entry
            self.mcp_servers = [s for s in self.mcp_servers if not (isinstance(s, dict) and s.get("name") == "massgen_checklist")]
            self.mcp_servers.append(checklist_mcp)

        # Convert MassGen mcp_servers list to Codex config.toml format
        # Merge orchestrator-injected servers (self.config) with init-time servers (self.mcp_servers)
        # which may include custom_tools MCP added by _setup_custom_tools_mcp()
        config_mcp = self.config.get("mcp_servers") if self.config else None
        logger.info(f"Codex _write_workspace_config: self.config mcp_servers={config_mcp is not None}, self.mcp_servers={len(self.mcp_servers)} entries")

        # Start with orchestrator servers, then add any from init (custom tools)
        mcp_servers = []
        if config_mcp is not None:
            if isinstance(config_mcp, dict):
                for name, srv_config in config_mcp.items():
                    if isinstance(srv_config, dict) and srv_config.get("type") != "sdk":
                        srv_config["name"] = name
                        mcp_servers.append(srv_config)
            elif isinstance(config_mcp, list):
                mcp_servers.extend(config_mcp)
        # Merge in self.mcp_servers (custom tools etc.) avoiding duplicates by name
        existing_names = {s.get("name") for s in mcp_servers if isinstance(s, dict)}
        logger.info(
            "Codex config merge: from orchestrator config=%s, from self.mcp_servers=%s",
            [s.get("name", "?") for s in mcp_servers if isinstance(s, dict)],
            [s.get("name", "?") for s in self.mcp_servers if isinstance(s, dict)],
        )
        for s in self.mcp_servers:
            if isinstance(s, dict) and s.get("name") not in existing_names:
                mcp_servers.append(s)
        if mcp_servers:
            server_names = [s.get("name", "?") for s in mcp_servers if isinstance(s, dict)]
            logger.info(f"Codex workspace config: writing {len(mcp_servers)} MCP server(s): {server_names}")
        if mcp_servers:
            mcp_section: dict[str, Any] = {}

            for server in mcp_servers:
                # Support both list-of-dicts and dict formats
                if isinstance(server, dict):
                    name = server.get("name", "")
                    if not name:
                        continue
                    server_type = server.get("type", "stdio")

                    # Skip SDK MCP servers — they are in-process Python objects
                    # that cannot be serialized to config.toml.
                    if server_type == "sdk":
                        logger.info(f"Codex: skipping SDK server '{name}' (not serializable to config.toml)")
                        continue

                    entry: dict[str, Any] = {}

                    if server_type == "stdio":
                        if server.get("command"):
                            entry["command"] = server["command"]
                        if server.get("args"):
                            entry["args"] = server["args"]
                        if server.get("env"):
                            entry["env"] = server["env"]
                        if server.get("cwd"):
                            entry["cwd"] = server["cwd"]
                    elif server_type == "http":
                        if server.get("url"):
                            entry["url"] = server["url"]
                        if server.get("bearer_token_env_var"):
                            entry["bearer_token_env_var"] = server["bearer_token_env_var"]

                    # Optional fields
                    if server.get("startup_timeout_sec"):
                        entry["startup_timeout_sec"] = server["startup_timeout_sec"]
                    if server.get("tool_timeout_sec"):
                        entry["tool_timeout_sec"] = server["tool_timeout_sec"]
                    if server.get("allowed_tools"):
                        entry["enabled_tools"] = server["allowed_tools"]
                    if server.get("exclude_tools"):
                        entry["disabled_tools"] = server["exclude_tools"]

                    # `codex exec` has no UI to answer MCP approval prompts.
                    # `approval_policy = "never"` covers shell approvals, while
                    # MCP tools have their own server/tool approval mode.
                    if not self._is_docker_mode and self.approval_mode in ("full-auto", "auto-edit", "full-access"):
                        entry["default_tools_approval_mode"] = "approve"

                    mcp_section[name] = entry

            if mcp_section:
                config["mcp_servers"] = mcp_section
                logger.info(f"Codex config.toml MCP servers written: {list(mcp_section.keys())}")
                for sname, sconf in mcp_section.items():
                    cmd = sconf.get("command", "?")
                    args_preview = str(sconf.get("args", []))[:120]
                    logger.info(f"  MCP [{sname}]: command={cmd}, args={args_preview}")

        # Mirror skills into CODEX_HOME/skills so Codex skill discovery can find
        # project/merged skills under the same scoped home directory.
        self._sync_skills_into_codex_home(config_dir)

        # Inject system prompt + workflow instructions via .codex/AGENTS.md and
        # point Codex at it explicitly via model_instructions_file.
        full_prompt = self.system_prompt or ""
        pending = getattr(self, "_pending_workflow_instructions", "")
        if pending:
            full_prompt = (full_prompt + "\n" + pending) if full_prompt else pending
        if full_prompt:
            if self.RUNTIME_INPUT_PRIORITY_GUIDANCE not in full_prompt:
                full_prompt = f"{full_prompt}\n\n{self.RUNTIME_INPUT_PRIORITY_GUIDANCE}"
            agents_md_path = config_dir / "AGENTS.md"
            agents_md_path.write_text(full_prompt, encoding="utf-8")
            config["model_instructions_file"] = str(agents_md_path)
            logger.info(f"Wrote Codex AGENTS.md: {agents_md_path} ({len(full_prompt)} chars)")

        permission_hooks_config = self._build_permission_hooks_config(config_dir)
        merged_hooks_config = permission_hooks_config
        if adapter and self._massgen_hooks_config:
            merged_hooks_config = adapter.merge_native_configs(
                permission_hooks_config,
                self._massgen_hooks_config,
            )
        elif self._massgen_hooks_config:
            merged_hooks_config = self._massgen_hooks_config

        hooks_path = config_dir / "hooks.json"
        hooks_section = merged_hooks_config.get("hooks", {}) if merged_hooks_config else {}
        if hooks_section:
            self._prepare_native_hook_script(config_dir)
            hooks_path.write_text(json.dumps(merged_hooks_config, indent=2), encoding="utf-8")
            config.setdefault("features", {})["codex_hooks"] = True
        else:
            hooks_path.unlink(missing_ok=True)
            (config_dir / "codex_hook_script.py").unlink(missing_ok=True)

        # Force approval bypass for non-interactive runs. MassGen always invokes
        # Codex via `codex exec` with no human in the loop. Two knobs needed:
        #   - top-level `approval_policy = "never"` covers Codex's shell/patch
        #     approval path. Without it, the deprecated "on-failure" default
        #     escalates failures to a non-existent user.
        #   - per-server `default_tools_approval_mode = "approve"` (set above
        #     when serializing each [mcp_servers.<name>] block) covers the
        #     SEPARATE MCP tool-call approval gate. Setting only
        #     `approval_policy` is not enough — external MCP calls otherwise
        #     fail with "user cancelled MCP tool call" in `codex exec`.
        # dangerous-no-sandbox bypasses both via the CLI flag.
        if not self._is_docker_mode and self.approval_mode in ("full-auto", "auto-edit", "full-access"):
            config["approval_policy"] = "never"

        # Configure sandbox for local (non-Docker) workspace-write mode.
        # Codex OS-level sandbox (Seatbelt on macOS, Landlock on Linux) restricts writes to:
        #   cwd (workspace) + /tmp + writable_roots
        # MassGen pattern: workspace=write, context_paths per permission.
        # Use get_writable_paths() to get context paths with write permission.
        if not self._is_docker_mode and self.approval_mode in ("full-auto", "auto-edit"):
            # Enable workspace-write sandbox mode
            config["sandbox_mode"] = "workspace-write"

            writable_roots = []
            if self.filesystem_manager:
                ppm = getattr(self.filesystem_manager, "path_permission_manager", None)
                if ppm and hasattr(ppm, "get_writable_paths"):
                    writable_roots = ppm.get_writable_paths()
                    # Filter out cwd since workspace is already writable by default
                    writable_roots = [p for p in writable_roots if p != self.cwd]

            if writable_roots:
                config["sandbox_workspace_write"] = {
                    "writable_roots": writable_roots,
                    "network_access": True,
                }
                logger.info(f"Codex sandbox writable_roots: {writable_roots}")
            else:
                # Still configure sandbox_workspace_write for network access even without extra roots
                config["sandbox_workspace_write"] = {
                    "network_access": True,
                }
                logger.info("Codex sandbox: workspace-write mode enabled (no additional writable_roots)")

        elif self._is_docker_mode:
            # Docker mode: fully disable Codex's internal sandbox since container provides isolation.
            # This prevents Landlock initialization failures in containers lacking kernel capabilities.
            config["sandbox_mode"] = "danger-full-access"
            logger.info("Codex Docker mode: sandbox_mode set to danger-full-access")

        if not config:
            return

        # Write config
        config_path = config_dir / "config.toml"

        if tomli_w:
            with open(config_path, "wb") as f:
                tomli_w.dump(config, f)
        else:
            # Fallback: manual TOML generation for simple structures
            self._write_toml_fallback(config, config_path)

        self._workspace_config_written = True
        # Debug: read back and log the written config
        try:
            written = config_path.read_text(encoding="utf-8")
            redacted_written = redact_secrets_in_text(written)
            logger.info(
                f"Codex config.toml written ({len(written)} chars): " f"{self._truncate_line(redacted_written, max_chars=800)}",
            )
        except Exception:
            pass

    @staticmethod
    def _toml_value(v: Any) -> str:
        """Convert a Python value to a TOML-compatible string."""
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, str):
            if "\n" in v:
                # Use TOML multiline basic string for content with newlines
                escaped = v.replace("\\", "\\\\").replace('"""', '\\"""')
                return f'"""\n{escaped}"""'
            return json.dumps(v)  # JSON string quoting works for TOML
        if isinstance(v, (int, float)):
            return str(v)
        if isinstance(v, list):
            return "[" + ", ".join(CodexBackend._toml_value(item) for item in v) + "]"
        if isinstance(v, dict):
            # TOML inline table: {key = "value", key2 = "value2"}
            pairs = [f"{k} = {CodexBackend._toml_value(val)}" for k, val in v.items()]
            return "{" + ", ".join(pairs) + "}"
        return json.dumps(v)

    @staticmethod
    def _write_toml_fallback(config: dict[str, Any], path: Path) -> None:
        """Write a simple TOML file without tomli_w dependency.

        Follows the Codex config.toml format from the OpenAI docs:
        - MCP servers use [mcp_servers.<name>] table headers
        - Nested dicts (like env) use [mcp_servers.<name>.<key>] sub-tables
        - Arrays and strings use standard TOML syntax
        """
        lines: list[str] = []
        # Write top-level scalar keys FIRST (before any [table] sections),
        # otherwise TOML parsers assign them to the last open table.
        table_keys: list[str] = []
        for section_key, section_val in config.items():
            if isinstance(section_val, dict):
                table_keys.append(section_key)
            else:
                lines.append(f"{section_key} = {CodexBackend._toml_value(section_val)}")
        if lines:
            lines.append("")  # blank line before tables

        for section_key in table_keys:
            section_val = config[section_key]
            # Check if this is a table-of-tables (like mcp_servers) or a simple table
            # (like sandbox_workspace_write). A table-of-tables has all dict values.
            is_table_of_tables = all(isinstance(v, dict) for v in section_val.values())

            if is_table_of_tables and section_val:
                # Table-of-tables: [section_key.name] for each entry
                for name, entry in section_val.items():
                    lines.append(f"[{section_key}.{name}]")
                    # Separate simple values from sub-tables (dicts)
                    sub_tables: list[tuple] = []
                    for k, v in entry.items():
                        if isinstance(v, dict):
                            sub_tables.append((k, v))
                        else:
                            lines.append(f"{k} = {CodexBackend._toml_value(v)}")
                    lines.append("")
                    # Write sub-tables after simple values
                    for sub_key, sub_val in sub_tables:
                        lines.append(f"[{section_key}.{name}.{sub_key}]")
                        for sk, sv in sub_val.items():
                            lines.append(f"{sk} = {CodexBackend._toml_value(sv)}")
                        lines.append("")
            else:
                # Simple table: [section_key] with key = value pairs
                lines.append(f"[{section_key}]")
                for k, v in section_val.items():
                    lines.append(f"{k} = {CodexBackend._toml_value(v)}")
                lines.append("")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _build_permission_manifest(self) -> dict[str, Any] | None:
        """Serialize managed path permissions for the standalone Codex hook script."""
        fm = getattr(self, "filesystem_manager", None)
        if fm is None:
            return None

        ppm = getattr(fm, "path_permission_manager", None)
        managed_paths = getattr(ppm, "managed_paths", None)
        if ppm is None or not managed_paths:
            return None

        return {
            "version": 1,
            "workspace": str(Path(self.cwd).resolve()),
            "managed_paths": [
                {
                    "path": str(Path(mp.path).resolve()),
                    "permission": mp.permission.value,
                    "path_type": mp.path_type,
                    "is_file": bool(mp.is_file),
                    "protected_paths": [str(Path(p).resolve()) for p in (mp.protected_paths or [])],
                }
                for mp in managed_paths
            ],
        }

    def _prepare_native_hook_script(self, config_dir: Path) -> Path | None:
        """Copy the standalone Codex hook script into the workspace hook dir."""
        try:
            from ..mcp_tools.native_hook_adapters.codex_adapter import (
                _HOOK_SCRIPT_NAME,
                _HOOK_SCRIPT_PATH,
            )
        except ImportError:
            logger.warning("Codex native hook adapter not available, skipping hook script copy")
            return None

        destination = config_dir / _HOOK_SCRIPT_NAME
        shutil.copy2(_HOOK_SCRIPT_PATH, destination)
        return destination

    def _native_hook_command(self, config_dir: Path, event_name: str) -> str:
        """Build the command string Codex should execute for a native hook event."""
        hook_script_path = config_dir / "codex_hook_script.py"
        python_exe = "python3" if self._docker_execution else sys.executable
        return f"{python_exe} {hook_script_path}" f" --hook-dir {config_dir}" f" --event {event_name}"

    def _build_permission_hooks_config(self, config_dir: Path) -> dict[str, Any]:
        manifest_path = config_dir / "permission_manifest.json"
        """Codex Bash PreToolUse hooks are disabled; remove any stale manifest."""
        manifest_path.unlink(missing_ok=True)
        return {}

    def _cleanup_workspace_config(self) -> None:
        """Remove the project-scoped .codex/ directory we created."""
        if not self._workspace_config_written and not self._custom_tools_specs_path:
            return
        config_dir = Path(self.cwd) / ".codex"
        try:
            # Remove individual files we created
            for filename in (
                "config.toml",
                "custom_tool_specs.json",
                "workflow_tool_specs.json",
                "checklist_specs.json",
                "AGENTS.md",
                "hooks.json",
                "permission_manifest.json",
                "codex_hook_script.py",
            ):
                filepath = config_dir / filename
                if filepath.exists():
                    filepath.unlink()
            # Remove dir if empty
            if config_dir.exists() and not any(config_dir.iterdir()):
                config_dir.rmdir()
            # Cleanup legacy workspace-root AGENTS.md (older backend behavior).
            agents_md = Path(self.cwd) / "AGENTS.md"
            if agents_md.exists():
                agents_md.unlink()
            logger.info("Cleaned up Codex workspace config.")
        except OSError as e:
            logger.warning(f"Failed to clean up Codex workspace config: {e}")

        self._workspace_config_written = False
        self._custom_tools_specs_path = None

    @property
    def _is_docker_mode(self) -> bool:
        """Check if we should execute Codex inside a Docker container."""
        if not self._docker_execution:
            return False
        if not self.filesystem_manager:
            return False
        dm = getattr(self.filesystem_manager, "docker_manager", None)
        if dm is None:
            return False
        # Check if a container exists for this agent
        agent_id = self.agent_id or getattr(self.filesystem_manager, "agent_id", None)
        if agent_id and dm.get_container(agent_id):
            return True
        return False

    def _resolve_codex_skills_source(self) -> Path | None:
        """Resolve the best available skills source directory, if any."""
        fm = self.filesystem_manager
        if fm is not None:
            if self._is_docker_mode:
                dm = getattr(fm, "docker_manager", None)
                agent_id = self.agent_id or getattr(fm, "agent_id", None)
                temp_skills_dirs = getattr(dm, "temp_skills_dirs", None) if dm else None
                if isinstance(temp_skills_dirs, dict) and agent_id in temp_skills_dirs:
                    source = Path(temp_skills_dirs[agent_id])
                    if source.exists():
                        return source

            local_skills_directory = getattr(fm, "local_skills_directory", None)
            if local_skills_directory:
                source = Path(local_skills_directory)
                if source.exists():
                    return source

        project_skills = Path(self.cwd) / ".agent" / "skills"
        if project_skills.exists():
            return project_skills

        home_skills = Path.home() / ".agent" / "skills"
        if home_skills.exists():
            return home_skills

        return None

    def _sync_skills_into_codex_home(self, codex_home: Path) -> None:
        """Copy discovered skills into CODEX_HOME/skills for Codex discovery."""
        source = self._resolve_codex_skills_source()
        if source is None:
            return

        dest = codex_home / "skills"
        dest.mkdir(parents=True, exist_ok=True)

        try:
            if source.resolve() == dest.resolve():
                return
        except OSError:
            # Continue best-effort copy if either path cannot be resolved.
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
            logger.warning(f"Codex skills sync failed from {source} to {dest}: {e}")
            return

        if copied_entries:
            logger.info(f"Codex skills sync: copied {copied_entries} entries from {source} to {dest}")

    def _get_docker_container(self):
        """Get the Docker container for this agent.

        Returns:
            Container object

        Raises:
            RuntimeError: If no container is available
        """
        dm = self.filesystem_manager.docker_manager
        agent_id = self.agent_id or getattr(self.filesystem_manager, "agent_id", None)
        if not agent_id:
            raise RuntimeError("No agent_id set on Codex backend for Docker execution")
        container = dm.get_container(agent_id)
        if not container:
            raise RuntimeError(f"No Docker container found for agent {agent_id}")
        return container

    def _build_exec_command(
        self,
        prompt: str,
        resume_session: bool = False,
        for_docker: bool = False,
    ) -> list[str]:
        """Build the codex exec command with appropriate flags.

        Args:
            prompt: The user prompt to send
            resume_session: Whether to resume an existing session

        Returns:
            Command list for subprocess
        """
        codex_bin = "codex" if for_docker else self._codex_path
        cmd = [codex_bin, "exec"]

        # Resume existing session or start new
        # `codex exec resume` is a subcommand with its own limited flags
        # (--json, prompt only) — model/sandbox/cwd flags are NOT accepted.
        if resume_session and self.session_id:
            cmd.extend(["resume", self.session_id])
            cmd.append("--json")
            cmd.append(prompt)
            return cmd

        # --- New session path ---
        # JSON output for parsing
        cmd.append("--json")

        # Model selection
        if self.model:
            cmd.extend(["--model", self.model])

        # Sandbox + approval mode:
        # In Docker mode, the container IS the sandbox — bypass Codex's own sandbox
        # entirely. Using --dangerously-bypass-approvals-and-sandbox (--yolo) instead
        # of --full-auto -s danger-full-access because the latter still initializes
        # Landlock on Linux, which fails in containers without the required kernel
        # capabilities (error: "Sandbox(LandlockRestrict)").
        if for_docker:
            cmd.append("--dangerously-bypass-approvals-and-sandbox")
        elif self.approval_mode == "full-access":
            # Full filesystem access but still auto-approve via --full-auto
            cmd.extend(["--full-auto", "-s", "danger-full-access"])
        elif self.approval_mode == "dangerous-no-sandbox":
            cmd.append("--dangerously-bypass-approvals-and-sandbox")
        elif self.approval_mode in ("full-auto", "auto-edit"):
            # Sandboxed to workspace dir (default for MassGen)
            cmd.append("--full-auto")
        # "suggest" / default: no flag (but MassGen defaults to full-auto)

        # Working directory flag
        if self.cwd:
            cmd.extend(["-C", self.cwd])

        # Skip git repo requirement (MassGen workspaces may not be git repos)
        cmd.append("--skip-git-repo-check")

        # Add the prompt
        cmd.append(prompt)

        return cmd

    def _remove_runtime_mcp_server(self, server_name: str) -> None:
        """Remove a transient runtime MCP server from the active server list."""
        self.mcp_servers = [server for server in self.mcp_servers if not (isinstance(server, dict) and server.get("name") == server_name)]

    @staticmethod
    def _truncate_line(line: str, max_chars: int = 200) -> str:
        """Truncate long diagnostic lines to keep logs readable."""
        if len(line) <= max_chars:
            return line
        return f"{line[:max_chars]}..."

    @staticmethod
    def _looks_like_json_event_line(line: str) -> bool:
        """Return True when a stream line resembles a JSON event object."""
        stripped = line.lstrip()
        return stripped.startswith("{") or stripped.startswith("[")

    def _decode_codex_event_line(self, line_str: str) -> dict[str, Any] | None:
        """Decode one Codex stream line, tolerating plain-text diagnostics.

        Codex occasionally emits non-JSON status or hook error text alongside the
        JSON event stream. Those lines are useful diagnostics, but they are not
        protocol parse failures and should not be logged as such.

        Error-shaped lines (anything containing " ERROR " or "error=") are
        surfaced at WARNING so regressions like a failed MCP server startup
        ("ERROR codex_core::tools::router: error=MCP startup failed: ...")
        don't disappear into DEBUG-only logs and waste hours of debugging.
        """
        try:
            return json.loads(line_str)
        except json.JSONDecodeError:
            truncated = self._truncate_line(redact_secrets_in_text(line_str))
            if self._looks_like_json_event_line(line_str):
                logger.warning(f"Failed to parse Codex event: {truncated}")
            elif " ERROR " in line_str or "error=" in line_str:
                logger.warning(f"Codex stderr error: {truncated}")
            elif "Command blocked by PreToolUse hook" in line_str:
                logger.info(f"Codex non-JSON output: {truncated}")
            else:
                logger.debug(f"Skipping non-JSON Codex output: {truncated}")
            return None

    def _parse_codex_event(self, event: dict[str, Any]) -> list[StreamChunk]:
        """Parse a Codex JSON event into StreamChunks.

        Handles both the documented item.started/item.completed wrapper format
        (with nested item.type) and legacy direct event names as fallback.

        Args:
            event: Parsed JSON event from Codex

        Returns:
            List of StreamChunks (empty list if event should be skipped)
        """
        event_type = event.get("type", "")

        # Extract session ID from thread.started
        if event_type == "thread.started":
            self.session_id = event.get("session_id") or event.get("thread_id")
            logger.info(f"Codex session started: {self.session_id}")
            return [
                StreamChunk(
                    type="agent_status",
                    status="session_started",
                    detail=f"Session: {self.session_id}",
                ),
            ]

        # Handle item.started / item.completed wrapper format
        # These wrap a nested "item" dict with its own "type" field
        if event_type in ("item.started", "item.completed"):
            item = event.get("item", {})
            item_type = item.get("type", "")
            is_completed = event_type == "item.completed"
            return self._parse_item(item_type, item, is_completed=is_completed)

        # Legacy direct event names (fallback)
        if event_type.startswith("item."):
            return self._parse_item(event_type, event, is_completed=True)

        # Handle turn completion
        if event_type == "turn.completed":
            self._active_background_wait_calls.clear()
            usage = event.get("usage", {})
            cached_input_tokens = usage.get("cached_input_tokens", 0)
            return [
                StreamChunk(
                    type="done",
                    usage={
                        "prompt_tokens": usage.get("input_tokens", 0),
                        "completion_tokens": usage.get("output_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0),
                        "cached_input_tokens": cached_input_tokens,
                    },
                ),
            ]

        if event_type == "turn.started":
            return [
                StreamChunk(
                    type="agent_status",
                    status="turn_started",
                ),
            ]

        # Handle errors - message is at top level, not nested
        if event_type in ("turn.failed", "error"):
            self._active_background_wait_calls.clear()
            error_msg = event.get("message") or event.get("error", {}).get("message") or str(event)
            return [StreamChunk(type="error", error=error_msg)]

        # Skip unknown events
        logger.debug(f"Skipping unknown Codex event type: {event_type}")
        return []

    def _parse_item(self, item_type: str, item: dict[str, Any], *, is_completed: bool = True) -> list[StreamChunk]:
        """Parse an item by its type, emitting structured tool events.

        Returns a list of StreamChunks. Tool items emit mcp_status chunks
        (for non-Textual displays) and fire emit_tool_start/emit_tool_complete
        events (for the Textual TUI event pipeline), following the same pattern
        as claude_code.py.

        Args:
            item_type: The Codex item type string
            item: The item dict from the event
            is_completed: True for item.completed events, False for item.started
        """
        agent_id = self.agent_id

        # Agent message (main content output)
        if item_type in ("agent_message", "message", "item.message"):
            text = item.get("text") or item.get("content", "")
            if isinstance(text, list):
                text_parts = [c.get("text", "") for c in text if c.get("type") == "text"]
                text = "".join(text_parts)
            if text:
                self._append_to_streaming_buffer(text)
                if self._execution_trace:
                    self._execution_trace.add_content(text)
            return [StreamChunk(type="content", content=text)]

        # Reasoning / thinking
        if item_type in ("reasoning", "item.reasoning"):
            reasoning_text = item.get("text") or item.get("content", "")
            if reasoning_text:
                self._append_reasoning_to_buffer(reasoning_text)
            return [
                StreamChunk(
                    type="reasoning",
                    reasoning_delta=reasoning_text,
                ),
            ]

        # Command execution (shell commands)
        if item_type in ("command_execution", "command", "item.command"):
            command = item.get("command", "")
            item_id = item.get("id") or str(uuid.uuid4())
            tool_name = "codex_shell"

            if not is_completed:
                # item.started — record start time, emit tool_start
                self._tool_start_times[item_id] = time.time()
                self._tool_id_to_name[item_id] = tool_name
                self._append_tool_call_to_buffer(
                    [{"name": tool_name, "arguments": {"command": command}}],
                )
                emitter = get_event_emitter()
                if emitter:
                    emitter.emit_tool_start(
                        tool_id=item_id,
                        tool_name=tool_name,
                        args={"command": command},
                        server_name="codex",
                        agent_id=agent_id,
                    )
                return [
                    StreamChunk(
                        type="mcp_status",
                        status="mcp_tool_called",
                        content=f"Calling {tool_name}...",
                        source="codex",
                        tool_call_id=item_id,
                    ),
                    StreamChunk(
                        type="mcp_status",
                        status="function_call",
                        content=f"Arguments for Calling {tool_name}: {json.dumps({'command': command})}",
                        source="codex",
                        tool_call_id=item_id,
                    ),
                ]
            else:
                # item.completed — emit tool_complete with result
                output = item.get("aggregated_output") or item.get("output", "")
                exit_code = item.get("exit_code")
                is_error = exit_code is not None and exit_code != 0
                suffix = f" (exit {exit_code})" if is_error else ""
                result_str = f"$ {command}{suffix}\n{output}".rstrip()
                self._append_tool_to_buffer(
                    tool_name=tool_name,
                    result_text=result_str,
                    is_error=is_error,
                )

                elapsed = time.time() - self._tool_start_times.pop(item_id, time.time())
                self._tool_id_to_name.pop(item_id, None)
                emitter = get_event_emitter()
                if emitter:
                    emitter.emit_tool_complete(
                        tool_id=item_id,
                        tool_name=tool_name,
                        result=result_str,
                        elapsed_seconds=elapsed,
                        status="error" if is_error else "success",
                        is_error=is_error,
                        agent_id=agent_id,
                    )
                return [
                    StreamChunk(
                        type="mcp_status",
                        status="function_call_output",
                        content=result_str,
                        source="codex",
                        tool_call_id=item_id,
                    ),
                ]

        # File write / change — only arrives as item.completed
        if item_type in ("file_write", "file_change", "fileChange", "item.file_change"):
            item_id = item.get("id") or str(uuid.uuid4())
            tool_name = "codex_file_edit"

            # Build display info from changes list or simple path
            changes = item.get("changes", [])
            if changes:
                paths = [c.get("path", "unknown") for c in changes]
                parts = []
                for change in changes:
                    path = change.get("path", "unknown")
                    kind = change.get("kind", "edit")
                    parts.append(f"[File {kind}: {path}]")
                result_str = "\n".join(parts)
                args = {"paths": paths}
            else:
                file_path = item.get("path", "unknown")
                result_str = f"[File written: {file_path}]"
                args = {"path": file_path}

            self._append_tool_call_to_buffer([{"name": tool_name, "arguments": args}])
            self._append_tool_to_buffer(
                tool_name=tool_name,
                result_text=result_str,
                is_error=False,
            )

            # Emit both start + complete (file_change only arrives as completed)
            emitter = get_event_emitter()
            if emitter:
                emitter.emit_tool_start(
                    tool_id=item_id,
                    tool_name=tool_name,
                    args=args,
                    server_name="codex",
                    agent_id=agent_id,
                )
                emitter.emit_tool_complete(
                    tool_id=item_id,
                    tool_name=tool_name,
                    result=result_str,
                    elapsed_seconds=0.0,
                    status="success",
                    is_error=False,
                    agent_id=agent_id,
                )
            return [
                StreamChunk(
                    type="mcp_status",
                    status="mcp_tool_called",
                    content=f"Calling {tool_name}...",
                    source="codex",
                    tool_call_id=item_id,
                ),
                StreamChunk(
                    type="mcp_status",
                    status="function_call",
                    content=f"Arguments for Calling {tool_name}: {json.dumps(args)}",
                    source="codex",
                    tool_call_id=item_id,
                ),
                StreamChunk(
                    type="mcp_status",
                    status="function_call_output",
                    content=result_str,
                    source="codex",
                    tool_call_id=item_id,
                ),
            ]

        # MCP tool calls (mcpToolCall {server, tool, status, arguments, result, error})
        if item_type in ("mcp_tool_call", "mcpToolCall", "tool_call", "item.tool_call"):
            tool_name = item.get("tool") or item.get("name", "")
            server = item.get("server", "")
            item_id = item.get("id") or str(uuid.uuid4())
            full_tool_name = f"{server}/{tool_name}" if server else tool_name
            is_background_wait_call = server == "massgen_custom_tools" and tool_name == "custom_tool__wait_for_background_tool"

            if not is_completed:
                # item.started (in_progress) — emit tool_start
                if server == "massgen_workflow_tools":
                    workflow_call = self._build_workflow_tool_call_from_codex_item(
                        tool_name=tool_name,
                        arguments=item.get("arguments", {}),
                        item_id=item_id,
                    )
                    if workflow_call:
                        if self._workflow_call_emitted_this_turn:
                            logger.info(
                                "Codex: suppressing additional workflow MCP start " "after first accepted call (%s)",
                                tool_name,
                            )
                            return []
                        self._workflow_call_emitted_this_turn = True
                        self._workflow_mcp_item_ids_emitted.add(item_id)
                        return [
                            StreamChunk(
                                type="tool_calls",
                                tool_calls=[workflow_call],
                                source="codex",
                            ),
                        ]
                    return []
                if is_background_wait_call:
                    self._active_background_wait_calls.add(item_id)
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(
                            self._maybe_signal_background_wait_interrupt(item_id),
                        )
                    except RuntimeError:
                        # No active event loop in this context.
                        pass
                self._tool_start_times[item_id] = time.time()
                self._tool_id_to_name[item_id] = full_tool_name
                arguments = item.get("arguments", {})
                self._append_tool_call_to_buffer(
                    [{"name": full_tool_name, "arguments": arguments}],
                )
                emitter = get_event_emitter()
                if emitter:
                    emitter.emit_tool_start(
                        tool_id=item_id,
                        tool_name=full_tool_name,
                        args=arguments if isinstance(arguments, dict) else {"input": arguments},
                        server_name=server or None,
                        agent_id=agent_id,
                    )
                # Event emitter handles TUI rendering — no mcp_status StreamChunks
                # needed (they caused duplicate tool entries in the Textual TUI).
                return []
            else:
                # item.completed — emit tool_complete or workflow tool_calls
                result = item.get("result", "")

                # Workflow MCP tools: extract as tool_calls (preserve existing behavior)
                if server == "massgen_workflow_tools":
                    if item_id in self._workflow_mcp_item_ids_emitted:
                        return []
                    if self._workflow_call_emitted_this_turn:
                        logger.info(
                            "Codex: ignoring additional workflow MCP completion " "after first accepted call (%s)",
                            tool_name,
                        )
                        return []
                    workflow_call = self._try_extract_workflow_mcp_result_from_codex(result)
                    if not workflow_call:
                        workflow_call = self._build_workflow_tool_call_from_codex_item(
                            tool_name=tool_name,
                            arguments=item.get("arguments", {}),
                            item_id=item_id,
                        )
                    if workflow_call:
                        self._workflow_call_emitted_this_turn = True
                        self._workflow_mcp_item_ids_emitted.add(item_id)
                        return [
                            StreamChunk(
                                type="tool_calls",
                                tool_calls=[workflow_call],
                                source="codex",
                            ),
                        ]
                    return []

                # Non-workflow: emit tool_complete
                result_str = self._stringify_mcp_result(result)
                is_error = bool(item.get("error"))
                if is_error:
                    result_str = f"[Error]: {item.get('error', '')}"
                if is_background_wait_call:
                    self._active_background_wait_calls.discard(item_id)
                self._append_tool_to_buffer(
                    tool_name=full_tool_name,
                    result_text=result_str,
                    is_error=is_error,
                )

                elapsed = time.time() - self._tool_start_times.pop(item_id, time.time())
                self._tool_id_to_name.pop(item_id, None)
                emitter = get_event_emitter()
                if emitter:
                    emitter.emit_tool_complete(
                        tool_id=item_id,
                        tool_name=full_tool_name,
                        result=result_str,
                        elapsed_seconds=elapsed,
                        status="error" if is_error else "success",
                        is_error=is_error,
                        agent_id=agent_id,
                    )
                # Event emitter handles TUI rendering — no mcp_status StreamChunks.
                return []

        # Web search — typically only item.completed
        if item_type in ("web_search", "webSearch"):
            item_id = item.get("id") or str(uuid.uuid4())
            tool_name = "codex_web_search"
            query = item.get("query", "")
            result_str = f"[Web search: {query}]"
            self._append_tool_call_to_buffer(
                [{"name": tool_name, "arguments": {"query": query}}],
            )
            self._append_tool_to_buffer(
                tool_name=tool_name,
                result_text=result_str,
                is_error=False,
            )

            emitter = get_event_emitter()
            if emitter:
                emitter.emit_tool_start(
                    tool_id=item_id,
                    tool_name=tool_name,
                    args={"query": query},
                    server_name="codex",
                    agent_id=agent_id,
                )
                emitter.emit_tool_complete(
                    tool_id=item_id,
                    tool_name=tool_name,
                    result=result_str,
                    elapsed_seconds=0.0,
                    status="success",
                    is_error=False,
                    agent_id=agent_id,
                )
            return [
                StreamChunk(
                    type="mcp_status",
                    status="mcp_tool_called",
                    content=f"Calling {tool_name}...",
                    source="codex",
                    tool_call_id=item_id,
                ),
                StreamChunk(
                    type="mcp_status",
                    status="function_call",
                    content=f"Arguments for Calling {tool_name}: {json.dumps({'query': query})}",
                    source="codex",
                    tool_call_id=item_id,
                ),
                StreamChunk(
                    type="mcp_status",
                    status="function_call_output",
                    content=result_str,
                    source="codex",
                    tool_call_id=item_id,
                ),
            ]

        # Image view — typically only item.completed
        if item_type in ("image_view", "imageView"):
            item_id = item.get("id") or str(uuid.uuid4())
            tool_name = "codex_image_view"
            img_path = item.get("path", "")
            result_str = f"[Image: {img_path}]"
            self._append_tool_call_to_buffer(
                [{"name": tool_name, "arguments": {"path": img_path}}],
            )
            self._append_tool_to_buffer(
                tool_name=tool_name,
                result_text=result_str,
                is_error=False,
            )

            emitter = get_event_emitter()
            if emitter:
                emitter.emit_tool_start(
                    tool_id=item_id,
                    tool_name=tool_name,
                    args={"path": img_path},
                    server_name="codex",
                    agent_id=agent_id,
                )
                emitter.emit_tool_complete(
                    tool_id=item_id,
                    tool_name=tool_name,
                    result=result_str,
                    elapsed_seconds=0.0,
                    status="success",
                    is_error=False,
                    agent_id=agent_id,
                )
            return [
                StreamChunk(
                    type="mcp_status",
                    status="mcp_tool_called",
                    content=f"Calling {tool_name}...",
                    source="codex",
                    tool_call_id=item_id,
                ),
                StreamChunk(
                    type="mcp_status",
                    status="function_call",
                    content=f"Arguments for Calling {tool_name}: {json.dumps({'path': img_path})}",
                    source="codex",
                    tool_call_id=item_id,
                ),
                StreamChunk(
                    type="mcp_status",
                    status="function_call_output",
                    content=result_str,
                    source="codex",
                    tool_call_id=item_id,
                ),
            ]

        logger.debug(f"Skipping unknown Codex item type: {item_type}")
        return []

    async def stream_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        **kwargs,
    ) -> AsyncGenerator[StreamChunk]:
        """Stream a response from Codex with tool support.

        Codex handles tools internally via MCP servers configured in
        ~/.codex/config.toml. The tools parameter is used for MassGen's
        workflow tools (new_answer, vote, etc.) which are injected via
        system prompt.

        Args:
            messages: Conversation messages
            tools: Available tools schema (used for system prompt injection)
            **kwargs: Additional parameters

        Yields:
            StreamChunk: Standardized response chunks
        """
        await self._ensure_authenticated()
        agent_id = kwargs.get("agent_id") or self.agent_id
        buffer_kwargs = dict(kwargs)
        if buffer_kwargs.get("agent_id") is None and agent_id is not None:
            buffer_kwargs["agent_id"] = agent_id
        self._clear_streaming_buffer(**buffer_kwargs)

        # Clear stale hook files from previous turns
        self.clear_hook_files()

        # Extract system message from messages and merge into instructions file
        # The orchestrator injects the full system prompt (task context, coordination
        # instructions, etc.) as the first system message.  Codex only receives a
        # single user-prompt via CLI, so we must surface the system content through
        # the model_instructions_file.
        system_from_messages = ""
        for msg in messages:
            if msg.get("role") == "system":
                c = msg.get("content", "")
                if isinstance(c, str):
                    system_from_messages = c
                elif isinstance(c, list):
                    system_from_messages = "".join(p.get("text", "") for p in c if p.get("type") == "text")
                break  # Use first system message only

        if system_from_messages:
            # Override the backend's system_prompt so _write_workspace_config picks it up
            self.system_prompt = system_from_messages
            logger.info(f"Codex: injected system message from orchestrator ({len(system_from_messages)} chars)")

        # Setup workflow tools as MCP server (preferred) or text instructions (fallback)
        tool_names = [t.get("function", {}).get("name", "?") for t in (tools or [])]
        logger.info(f"Codex stream_with_tools: received {len(tools or [])} tools: {tool_names}")

        self._remove_runtime_mcp_server("massgen_workflow_tools")

        # Use shared mixin method to setup workflow tools
        workflow_mcp_config, self._pending_workflow_instructions = self._setup_workflow_tools(
            tools or [],
            str(Path(self.cwd) / ".codex"),
            mcp_tool_prefix="massgen_workflow_tools/",
        )
        if workflow_mcp_config:
            self.mcp_servers.append(workflow_mcp_config)

        has_workflow_mcp = workflow_mcp_config is not None

        # Write project-scoped config with MCP servers (+ workflow instructions if fallback)
        self._write_workspace_config()

        # Extract the latest user message as the prompt
        prompt = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    prompt = content
                elif isinstance(content, list):
                    # Handle content blocks
                    text_parts = [c.get("text", "") for c in content if c.get("type") == "text"]
                    prompt = "".join(text_parts)
                break

        if not prompt:
            yield StreamChunk(type="error", error="No user message found in messages")
            return

        # Resume session if we have one — Codex maintains server-side history,
        # so even single-message enforcement retries should resume the session
        resume_session = self.session_id is not None
        if has_workflow_mcp and resume_session and self._last_turn_missing_workflow_call:
            logger.info(
                "Codex: forcing fresh session because previous workflow turn " "ended without a workflow tool decision",
            )
            resume_session = False
            self.session_id = None

        # Start API call timing
        self.start_api_call_timing(self.model)

        # Accumulate text content to parse workflow tool calls after streaming
        accumulated_content = ""
        held_done_chunk = None
        has_workflow = has_workflow_mcp or bool(self._pending_workflow_instructions)
        got_workflow_tool_calls = False
        self._workflow_call_emitted_this_turn = False
        self._workflow_mcp_item_ids_emitted.clear()

        try:
            stream = self._stream_docker(prompt, resume_session) if self._is_docker_mode else self._stream_local(prompt, resume_session)
            async for chunk in stream:
                if chunk.type == "content" and chunk.content:
                    accumulated_content += chunk.content
                # Track if workflow tool_calls arrived from MCP (via _parse_item)
                if chunk.type == "tool_calls" and has_workflow_mcp:
                    got_workflow_tool_calls = True
                # Hold the done chunk so we can attach workflow tool calls to it
                if chunk.type == "done" and has_workflow:
                    held_done_chunk = chunk
                    continue
                yield chunk

            # Text parsing fallback — only if MCP didn't produce workflow tool calls
            if not got_workflow_tool_calls and has_workflow and accumulated_content:
                workflow_tool_calls = parse_workflow_tool_calls(accumulated_content)
                if workflow_tool_calls:
                    logger.info(f"Codex: parsed {len(workflow_tool_calls)} workflow tool call(s) from text")
                    got_workflow_tool_calls = True
                    yield StreamChunk(type="tool_calls", tool_calls=workflow_tool_calls, source="codex")
            if held_done_chunk:
                yield held_done_chunk
        finally:
            self._last_turn_missing_workflow_call = has_workflow and not got_workflow_tool_calls
            self._finalize_streaming_buffer(agent_id=agent_id)

    async def _stream_docker(
        self,
        prompt: str,
        resume_session: bool,
    ) -> AsyncGenerator[StreamChunk]:
        """Stream Codex output by running inside a Docker container."""
        try:
            container = self._get_docker_container()

            # Verify codex exists in container (first call only)
            if not self._docker_codex_verified:
                exit_code, output = container.exec_run("which codex")
                if exit_code != 0:
                    yield StreamChunk(
                        type="error",
                        error=("codex CLI not found in Docker container. " "Add '@openai/codex' to command_line_docker_packages.preinstall.npm " "or use a Docker image with codex pre-installed."),
                    )
                    self.end_api_call_timing(success=False, error="codex not found in container")
                    return
                self._docker_codex_verified = True

            # Build command for docker execution
            cmd = self._build_exec_command(prompt, resume_session=resume_session, for_docker=True)

            # Set CODEX_HOME to workspace/.codex so Codex reads config from there.
            # Copy auth.json from host ~/.codex/ for OAuth tokens.
            workspace = self.cwd
            codex_dir = Path(workspace) / ".codex"
            codex_dir.mkdir(parents=True, exist_ok=True)
            host_auth = Path.home() / ".codex" / "auth.json"
            if host_auth.exists():
                shutil.copy2(str(host_auth), str(codex_dir / "auth.json"))
                logger.info("Codex Docker auth: copied OAuth tokens to workspace .codex/")
            else:
                logger.warning("Codex Docker auth: no ~/.codex/auth.json found on host")

            exec_env = {"NO_COLOR": "1", "CODEX_HOME": str(codex_dir)}

            logger.info(f"Running Codex in Docker: {cmd}")

            # Create exec instance — pass cmd as list to avoid shell escaping issues
            exec_id = container.client.api.exec_create(
                container.id,
                cmd=cmd,
                stdout=True,
                stderr=True,
                workdir=self.cwd,
                environment=exec_env,
            )["Id"]

            # Stream output using a queue for async iteration
            output_gen = container.client.api.exec_start(exec_id, stream=True, detach=False)

            loop = asyncio.get_event_loop()
            queue: asyncio.Queue = asyncio.Queue()

            async def _read_output():
                """Read Docker output in executor and push lines to queue."""
                buffer = ""

                def _iterate():
                    nonlocal buffer
                    for raw_chunk in output_gen:
                        text = raw_chunk.decode("utf-8", errors="replace")
                        buffer += text
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            line = line.strip()
                            if line:
                                # Put line synchronously from executor thread
                                pass

                                # Use a thread-safe approach
                                loop.call_soon_threadsafe(queue.put_nowait, line)
                    # Flush remaining buffer
                    if buffer.strip():
                        loop.call_soon_threadsafe(queue.put_nowait, buffer.strip())
                    loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

                await loop.run_in_executor(None, _iterate)

            # Start reader task
            reader_task = asyncio.ensure_future(_read_output())

            first_content = True

            while True:
                line_str = await queue.get()
                if line_str is None:
                    break

                event = self._decode_codex_event_line(line_str)
                if event is None:
                    continue

                redacted_event = redact_secrets_in_text(json.dumps(event, default=str))
                logger.info(
                    f"Codex raw event (docker): {self._truncate_line(redacted_event, max_chars=500)}",
                )
                chunks = self._parse_codex_event(event)
                for chunk in chunks:
                    if first_content and chunk.type == "content":
                        self.record_first_token()
                        first_content = False

                    yield chunk

                    if chunk.type == "done" and chunk.usage:
                        self._update_token_usage_from_api_response(
                            chunk.usage,
                            self.model,
                        )

            await reader_task

            # Check exec exit code
            exec_inspect = container.client.api.exec_inspect(exec_id)
            exit_code = exec_inspect.get("ExitCode", -1)
            if exit_code != 0:
                yield StreamChunk(type="error", error=f"Codex exited with code {exit_code}")
                self.end_api_call_timing(success=False, error=f"Exit code {exit_code}")
            else:
                self.end_api_call_timing(success=True)

        except Exception as e:
            logger.error(f"Codex Docker backend error: {e}")
            self.end_api_call_timing(success=False, error=str(e))
            yield StreamChunk(type="error", error=str(e))

    async def _stream_local(
        self,
        prompt: str,
        resume_session: bool,
    ) -> AsyncGenerator[StreamChunk]:
        """Stream Codex output via local subprocess.

        Supports **mid-round interrupt-and-resume steering**: a concurrent watcher
        polls the hook file the orchestrator writes pending steering / injection
        into. When content appears, it terminates Codex mid-turn; this generator
        then re-invokes ``codex exec resume <session_id> "<steering>"`` — Codex
        resumes with full context + the workspace files (which persist on disk),
        so the steering lands at ANY point in a long round, not just when an MCP
        tool happens to be called. Verified: resume recalls prior-turn context
        across a process kill.
        """
        # Set CODEX_HOME to workspace/.codex so Codex reads config from there
        # instead of ~/.codex. This avoids needing to modify the user's global
        # config with trust entries.
        codex_home = str(Path(self.cwd) / ".codex")
        Path(codex_home).mkdir(parents=True, exist_ok=True)
        host_auth = Path.home() / ".codex" / "auth.json"
        if host_auth.exists():
            shutil.copy2(str(host_auth), str(Path(codex_home) / "auth.json"))
            logger.debug("Copied OAuth tokens to workspace CODEX_HOME")

        current_prompt = prompt
        current_resume = resume_session
        interrupts = 0
        first_content = True

        while True:
            cmd = self._build_exec_command(current_prompt, resume_session=current_resume)
            logger.info(f"Running Codex command: {' '.join(cmd)}")

            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    limit=SUBPROCESS_STREAM_LIMIT,
                    cwd=self.cwd,
                    env={**os.environ, "NO_COLOR": "1", "CODEX_HOME": codex_home},
                )
            except Exception as e:
                logger.error(f"Codex backend error: {e}")
                self.end_api_call_timing(success=False, error=str(e))
                yield StreamChunk(type="error", error=str(e))
                return

            # Concurrent steering watcher — polls the hook file and, on pending
            # content, terminates Codex so this turn ends and we resume below.
            steer_holder: dict[str, str | None] = {"content": None}
            watch_stop = asyncio.Event()

            async def _watch(p: asyncio.subprocess.Process = proc) -> None:
                while not watch_stop.is_set():
                    try:
                        await asyncio.wait_for(watch_stop.wait(), timeout=self._interrupt_poll_seconds)
                        return
                    except TimeoutError:
                        pass
                    # Only interrupt once we have a session id to resume, and below
                    # the per-turn interrupt cap.
                    if not (self.supports_interrupt_resume() and self.session_id):
                        continue
                    if interrupts >= self._max_interrupts_per_turn:
                        continue
                    steer = self.read_unconsumed_hook_content()
                    if steer:
                        steer_holder["content"] = steer
                        logger.info("Codex: steering detected mid-turn — terminating to resume")
                        await self._terminate_proc(p)
                        return

            watcher = asyncio.create_task(_watch())
            try:
                async for line in proc.stdout:
                    line_str = line.decode().strip()
                    if not line_str:
                        continue
                    event = self._decode_codex_event_line(line_str)
                    if event is None:
                        continue
                    redacted_event = redact_secrets_in_text(json.dumps(event, default=str))
                    logger.info(f"Codex raw event: {self._truncate_line(redacted_event, max_chars=500)}")
                    chunks = self._parse_codex_event(event)
                    for chunk in chunks:
                        if first_content and chunk.type == "content":
                            self.record_first_token()
                            first_content = False
                        yield chunk
                        if chunk.type == "done" and chunk.usage:
                            self._update_token_usage_from_api_response(chunk.usage, self.model)
            except Exception as e:
                logger.error(f"Codex backend error: {e}")
                watch_stop.set()
                watcher.cancel()
                self.end_api_call_timing(success=False, error=str(e))
                yield StreamChunk(type="error", error=str(e))
                return
            finally:
                watch_stop.set()
                watcher.cancel()
                try:
                    await watcher
                except asyncio.CancelledError:
                    pass
                except Exception:
                    # A non-cancellation failure here means a real watcher bug
                    # during interrupt/resume finalization — don't mask it.
                    logger.debug("Codex: watcher failed during cleanup", exc_info=True)

            await proc.wait()

            # Interrupted by steering → resume the session with it as the prompt.
            if steer_holder["content"]:
                interrupts += 1
                logger.info(
                    f"Codex: interrupt #{interrupts} — resuming session {self.session_id} with steering ({len(steer_holder['content'])} chars)",
                )
                yield StreamChunk(type="content", content="\n[Steering delivered — resuming Codex session]\n")
                current_prompt = steer_holder["content"]
                current_resume = True
                continue

            if proc.returncode != 0:
                stderr = await proc.stderr.read()
                error_msg = stderr.decode() if stderr else f"Exit code {proc.returncode}"
                yield StreamChunk(type="error", error=f"Codex error: {error_msg}")
                self.end_api_call_timing(success=False, error=error_msg)
            else:
                self.end_api_call_timing(success=True)
            return

    @staticmethod
    def _try_extract_workflow_mcp_result_from_codex(result: Any) -> dict[str, Any] | None:
        """Extract a workflow tool call from a Codex MCP tool result.

        Codex MCP results come as dicts like:
            {'content': [{'text': '{"status":"ok","server":"massgen_workflow_tools",...}', 'type': 'text'}],
             'structured_content': None}

        Or sometimes as raw JSON strings.

        Returns:
            Tool call dict in orchestrator format, or None.
        """
        from ..mcp_tools.workflow_tools_server import extract_workflow_tool_call

        json_str = None

        if isinstance(result, dict):
            # Codex wraps MCP results in {'content': [{'text': '...', 'type': 'text'}], ...}
            content_list = result.get("content", [])
            if isinstance(content_list, list):
                for item in content_list:
                    if isinstance(item, dict) and item.get("type") == "text":
                        json_str = item.get("text", "")
                        break
            if not json_str:
                # Try the result dict itself
                return extract_workflow_tool_call(result)
        elif isinstance(result, str):
            json_str = result

        if not json_str:
            return None

        try:
            parsed = json.loads(json_str)
            return extract_workflow_tool_call(parsed)
        except (json.JSONDecodeError, TypeError):
            return None

    @staticmethod
    def _build_workflow_tool_call_from_codex_item(
        tool_name: str,
        arguments: Any,
        item_id: str,
    ) -> dict[str, Any] | None:
        """Build a workflow tool call directly from a Codex MCP item payload."""
        if not tool_name:
            return None

        normalized_args = arguments
        if isinstance(normalized_args, str):
            try:
                normalized_args = json.loads(normalized_args)
            except json.JSONDecodeError:
                normalized_args = {}
        if not isinstance(normalized_args, dict):
            normalized_args = {}

        return {
            "id": f"call_{item_id}",
            "type": "function",
            "function": {
                "name": tool_name,
                "arguments": normalized_args,
            },
        }

    @staticmethod
    def _stringify_mcp_result(result: Any) -> str:
        """Normalize Codex MCP results into a frontend-friendly string payload.

        Codex commonly wraps MCP output in ``{"content": [{"type": "text",
        "text": "..."}], ...}``. For WebUI consumers, the inner text is the
        useful payload. For other structured objects, prefer JSON serialization
        over Python repr so clients can parse planning/custom-tool responses.
        """
        if isinstance(result, str):
            return result

        if isinstance(result, dict):
            content_list = result.get("content", [])
            if isinstance(content_list, list):
                for item in content_list:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text = item.get("text")
                        if isinstance(text, str) and text:
                            return text

            try:
                return json.dumps(result, ensure_ascii=False)
            except (TypeError, ValueError):
                return str(result)

        if isinstance(result, list):
            try:
                return json.dumps(result, ensure_ascii=False)
            except (TypeError, ValueError):
                return str(result)

        return str(result)

    def get_disallowed_tools(self, config: dict[str, Any]) -> list[str]:
        """Return Codex native tools to disable.

        Codex keeps all its native tools (shell, file_read, file_write,
        file_edit, web_search) since MassGen skips attaching MCP equivalents
        for categories the backend handles natively (see tool_category_overrides).
        Native image viewing is disabled directly in generated config.toml
        via [tools].view_image = false.

        Tool filtering for MCP servers is handled separately via
        enabled_tools/disabled_tools in .codex/config.toml per server.

        Codex also supports disabling built-in tools via config.toml:
        - [features].shell_tool = false
        - web_search = "disabled"
        - [tools].view_image = false

        Args:
            config: Backend config dict.

        Returns:
            Empty list — all native tools are kept.
        """
        return []

    def get_tool_category_overrides(self) -> dict[str, str]:
        """Return tool category overrides for Codex.

        Codex has native tools for filesystem, command execution, file search,
        and web search. MassGen overrides native planning and subagent tools
        with its own implementations.
        """
        return {
            "filesystem": "skip",  # Native: file_read, file_write, file_edit
            "command_execution": "skip",  # Native: shell
            "file_search": "skip",  # Native: shell (rg/sg available)
            "web_search": "skip",  # Native: web_search
            "planning": "override",  # Override with MassGen planning MCP
            "subagents": "override",  # Override with MassGen spawn_subagents
        }

    def get_provider_name(self) -> str:
        """Get the name of this provider."""
        return "codex"

    def is_mcp_tool_call(self, tool_name: str) -> bool:
        """Check if a tool call is an MCP function.

        Codex uses server_name/tool_name format (e.g., massgen_custom_tools/custom_tool__generate_media).
        """
        # Check for Codex MCP naming convention (server/tool)
        if "/" in tool_name:
            return True
        # Also check standard MCP naming (mcp__server__tool)
        if tool_name.startswith("mcp__"):
            return True
        return False

    def is_custom_tool_call(self, tool_name: str) -> bool:
        """Check if a tool call is a custom tool function.

        Custom tools in Codex are wrapped as MCP and use the massgen_custom_tools server.
        """
        return tool_name.startswith("massgen_custom_tools/")

    def get_filesystem_support(self) -> FilesystemSupport:
        """Codex has native filesystem support via built-in tools."""
        return FilesystemSupport.NATIVE

    def is_stateful(self) -> bool:
        """Codex maintains session state via session files."""
        return True

    async def reset_state(self) -> None:
        """Reset session state for new conversation."""
        await self._disconnect_background_mcp_client()
        self.session_id = None
        self._session_file = None
        self._pending_workflow_instructions = ""
        self._tool_start_times.clear()
        self._tool_id_to_name.clear()
        self._workflow_call_emitted_this_turn = False
        self._workflow_mcp_item_ids_emitted.clear()
        self._last_turn_missing_workflow_call = False
        self._cleanup_workspace_config()
        logger.info("Codex session state reset.")

    async def clear_history(self) -> None:
        """Clear conversation history while maintaining session.

        For Codex, this starts a fresh session.
        """
        await self._disconnect_background_mcp_client()
        self.session_id = None
        self._session_file = None
        self._last_turn_missing_workflow_call = False
        self._cleanup_workspace_config()


# Register backend in the factory (add to cli.py create_backend function)
# "codex" -> CodexBackend
