"""
Subagent Manager for MassGen

Manages the lifecycle of subagents: creation, workspace setup, execution, and result collection.
"""

import asyncio
import json
import os
import shutil
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from massgen.events import MassGenEvent

import yaml
from loguru import logger

from massgen.structured_logging import (
    log_subagent_complete,
    log_subagent_spawn,
    trace_subagent_execution,
)
from massgen.subagent.models import (
    SUBAGENT_DEFAULT_TIMEOUT,
    SUBAGENT_MAX_TIMEOUT,
    SUBAGENT_MIN_TIMEOUT,
    SubagentConfig,
    SubagentDisplayData,
    SubagentOrchestratorConfig,
    SubagentPointer,
    SubagentResult,
    SubagentState,
)

# Subagent event streams can include large JSON lines for final answers or
# verbose tool payloads. Raise the asyncio reader limit so line-based parsing
# can consume those events without hitting LimitOverrunError.
SUBPROCESS_STREAM_LIMIT = 4 * 1024 * 1024


class SubagentManager:
    """
    Manages subagent lifecycle, workspaces, and execution.

    Responsible for:
    - Creating isolated workspaces for subagents
    - Spawning and executing subagent tasks
    - Collecting and formatting results
    - Tracking active subagents
    - Cleanup on completion

    Subagents cannot spawn their own subagents (no nesting).
    """

    @staticmethod
    def _clean_subprocess_env() -> dict[str, str]:
        """Return a copy of ``os.environ`` with ``CLAUDECODE`` removed.

        Child MassGen processes inherit the parent environment.  When the
        parent is itself a Claude Code session ``CLAUDECODE=1`` is set,
        which blocks nested Claude Code SDK initialisation.  Stripping the
        variable ensures subagent processes can launch their own Claude Code
        backends without hitting nested-session detection.
        """
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)
        return env

    def __init__(
        self,
        parent_workspace: str,
        parent_agent_id: str,
        orchestrator_id: str,
        parent_agent_configs: list[dict[str, Any]],
        max_concurrent: int = 3,
        default_timeout: int = SUBAGENT_DEFAULT_TIMEOUT,
        min_timeout: int = SUBAGENT_MIN_TIMEOUT,
        max_timeout: int = SUBAGENT_MAX_TIMEOUT,
        subagent_orchestrator_config: SubagentOrchestratorConfig | None = None,
        log_directory: str | None = None,
        parent_context_paths: list[dict[str, str]] | None = None,
        parent_coordination_config: dict[str, Any] | None = None,
        agent_temporary_workspace: str | None = None,
        subagent_runtime_mode: str = "isolated",
        subagent_runtime_fallback_mode: str | None = None,
        subagent_host_launch_prefix: list[str] | None = None,
        delegation_directory: str | None = None,
    ):
        """
        Initialize SubagentManager.

        Args:
            parent_workspace: Path to parent agent's workspace
            parent_agent_id: ID of the parent agent
            orchestrator_id: ID of the orchestrator
            parent_agent_configs: List of parent agent configurations to inherit.
                Each config should have 'id' and 'backend' keys.
            max_concurrent: Maximum concurrent subagents (default 3)
            default_timeout: Default timeout in seconds (default 300)
            min_timeout: Minimum allowed timeout in seconds (default 60)
            max_timeout: Maximum allowed timeout in seconds (default 600)
            subagent_orchestrator_config: Configuration for subagent orchestrator mode.
                When enabled, subagents use a full Orchestrator with multiple agents
                instead of a single ConfigurableAgent.
            log_directory: Path to main run's log directory for subagent logs.
                Subagent logs will be written to {log_directory}/subagents/{subagent_id}/
            parent_context_paths: List of context paths from the parent orchestrator.
                These are passed to subagents as read-only context paths so they can
                access the same codebase/files as the parent agent.
            parent_coordination_config: Coordination config from the parent orchestrator.
                Used to inherit settings like enable_agent_task_planning for subagents.
            agent_temporary_workspace: Path to agent temporary workspace parent directory.
                When provided, list_subagents() will scan all agent temp workspaces to
                show subagents from all agents (following workspace visibility principles).
            subagent_runtime_mode: Runtime boundary mode for subagent execution.
                - "isolated": default; require isolated launch semantics
                - "inherited": run in parent runtime boundary
            subagent_runtime_fallback_mode: Optional fallback when isolated runtime
                prerequisites are unavailable. None (default) is strict isolation;
                "inherited" explicitly opts into shared-runtime fallback.
            subagent_host_launch_prefix: Optional command prefix used for isolated
                launch when parent runtime is containerized.
            delegation_directory: Path to shared delegation directory for file-based
                container-to-host subagent launch (delegated mode). The container writes
                request files here; the host-side SubagentLaunchWatcher picks them up.
        """
        self.parent_workspace = Path(parent_workspace)
        self.parent_agent_id = parent_agent_id
        self.orchestrator_id = orchestrator_id
        self.parent_agent_configs = parent_agent_configs or []
        self.max_concurrent = max_concurrent
        self.default_timeout = default_timeout
        self.min_timeout = min_timeout
        self.max_timeout = max_timeout
        # Auto-raise max_timeout when default_timeout exceeds it to avoid
        # silent capping (e.g. subagent_default_timeout: 900 capped to 600).
        if self.default_timeout > self.max_timeout:
            logger.info(
                f"[SubagentManager] default_timeout ({self.default_timeout}s) > " f"max_timeout ({self.max_timeout}s), raising max_timeout to match",
            )
            self.max_timeout = self.default_timeout
        self._subagent_orchestrator_config = subagent_orchestrator_config
        self._parent_context_paths = self._normalize_parent_context_paths(parent_context_paths)
        self._parent_coordination_config = parent_coordination_config or {}
        if self._subagent_orchestrator_config is None:
            # Fallback path: preserve inherit mode even if runtime startup loses
            # inline orchestrator JSON args by recovering from coordination payload.
            fallback_subagent_orchestrator = self._parent_coordination_config.get("subagent_orchestrator")
            if isinstance(fallback_subagent_orchestrator, dict):
                try:
                    self._subagent_orchestrator_config = SubagentOrchestratorConfig.from_dict(
                        fallback_subagent_orchestrator,
                    )
                    logger.info(
                        "[SubagentManager] Loaded subagent_orchestrator fallback from parent_coordination_config",
                    )
                except (TypeError, ValueError) as e:
                    logger.warning(
                        "[SubagentManager] Ignoring invalid parent subagent_orchestrator fallback: %s",
                        e,
                    )
        self._agent_temporary_workspace = Path(agent_temporary_workspace) if agent_temporary_workspace else None
        self._subagent_runtime_mode = subagent_runtime_mode or "isolated"
        self._subagent_runtime_fallback_mode = subagent_runtime_fallback_mode
        self._subagent_host_launch_prefix = subagent_host_launch_prefix[:] if subagent_host_launch_prefix else []
        self._delegation_directory = delegation_directory
        self._running_inside_container = os.path.exists("/.dockerenv")
        self._validate_runtime_configuration()

        # Log directory for subagent logs (in main run's log dir)
        self._log_directory = Path(log_directory) if log_directory else None
        if self._log_directory:
            self._subagent_logs_base = self._log_directory / "subagents"
            try:
                self._subagent_logs_base.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                logger.warning(
                    f"[SubagentManager] Cannot create log directory {self._subagent_logs_base} " f"(permission denied). Subagent log capture disabled.",
                )
                self._subagent_logs_base = None
        else:
            self._subagent_logs_base = None

        # Base path for all subagent workspaces
        self.subagents_base = self.parent_workspace / "subagents"
        self.subagents_base.mkdir(parents=True, exist_ok=True)

        # Track active and completed subagents
        self._subagents: dict[str, SubagentState] = {}
        # Track background tasks for non-blocking execution
        self._background_tasks: dict[str, asyncio.Task] = {}
        # Track active subprocess handles for graceful cancellation
        self._active_processes: dict[str, asyncio.subprocess.Process] = {}
        # Track session IDs for each subagent (for continuation support)
        self._subagent_sessions: dict[str, str] = {}  # subagent_id -> session_id
        self._semaphore = asyncio.Semaphore(max_concurrent)
        # Callbacks to invoke when background subagents complete
        self._completion_callbacks: list[Callable[[str, SubagentResult], None]] = []
        # Sequence counter for runtime inbox messages
        self._message_seq: int = 0

        logger.info(
            f"[SubagentManager] Initialized for parent {parent_agent_id}, "
            f"workspace: {self.subagents_base}, max_concurrent: {max_concurrent}, "
            f"timeout: {default_timeout}s (min: {min_timeout}s, max: {max_timeout}s)" + (f", log_dir: {self._subagent_logs_base}" if self._subagent_logs_base else ""),
        )

    def send_message_to_subagent(
        self,
        subagent_id: str,
        content: str,
        target_agents: list[str] | None = None,
    ) -> tuple[bool, str | None]:
        """Write a runtime message to a running subagent's inbox.

        Messages are written as JSON files to
        {workspace}/.massgen/runtime_inbox/msg_{timestamp}_{seq}.json
        using an atomic write pattern (write .tmp, then rename).

        Args:
            subagent_id: ID of the subagent to message
            content: Message content to deliver
            target_agents: Optional list of inner agent IDs to target.
                None broadcasts to all inner agents.

        Returns:
            Tuple of (success, error_message). error_message is None on success.
        """
        state = self._subagents.get(subagent_id)
        if state is None:
            msg = f"Subagent '{subagent_id}' not found"
            logger.warning(f"[SubagentManager] Cannot send message: {msg}")
            return (False, msg)

        if state.status != "running":
            msg = f"Subagent '{subagent_id}' is {state.status}, not running"
            logger.warning(f"[SubagentManager] Cannot send message: {msg}")
            return (False, msg)

        workspace = Path(state.workspace_path)

        # Race condition guard: subprocess may have finished but parent status
        # hasn't been updated yet. Check for answer.txt as a completion signal.
        answer_file = workspace / "answer.txt"
        if answer_file.exists():
            msg = f"Subagent '{subagent_id}' has already completed" " (answer.txt found in workspace)"
            logger.warning(f"[SubagentManager] Cannot send message: {msg}")
            return (False, msg)

        inbox_dir = workspace / ".massgen" / "runtime_inbox"
        inbox_dir.mkdir(parents=True, exist_ok=True)

        self._message_seq += 1
        timestamp = int(time.time())
        filename = f"msg_{timestamp}_{self._message_seq}.json"

        msg_data = {
            "content": content,
            "source": "parent",
            "timestamp": datetime.now().isoformat(),
            "target_agents": target_agents,
        }

        # Atomic write: write to .tmp then rename
        tmp_path = inbox_dir / f"{filename}.tmp"
        final_path = inbox_dir / filename
        tmp_path.write_text(json.dumps(msg_data, indent=2))
        tmp_path.rename(final_path)

        logger.info(
            f"[SubagentManager] Sent runtime message to {subagent_id}: " f"'{content[:50]}...' -> {final_path}",
        )
        return (True, None)

    def get_running_subagent_ids(self) -> list[str]:
        """Return IDs of currently running subagents."""
        return [sid for sid, state in self._subagents.items() if state.status == "running"]

    def _validate_runtime_configuration(self) -> None:
        """Validate runtime mode/fallback configuration."""
        valid_runtime_modes = {"isolated", "inherited", "delegated"}
        if self._subagent_runtime_mode not in valid_runtime_modes:
            raise ValueError(
                f"Invalid subagent_runtime_mode: '{self._subagent_runtime_mode}'. " f"Must be one of: {sorted(valid_runtime_modes)}",
            )

        valid_fallback_modes = {None, "inherited"}
        if self._subagent_runtime_fallback_mode not in valid_fallback_modes:
            raise ValueError(
                "Invalid subagent_runtime_fallback_mode: " f"'{self._subagent_runtime_fallback_mode}'. Must be one of [None, 'inherited']",
            )

        if self._subagent_runtime_mode not in {"isolated", "delegated"} and self._subagent_runtime_fallback_mode is not None:
            raise ValueError(
                "subagent_runtime_fallback_mode is only valid when subagent_runtime_mode is 'isolated' or 'delegated'",
            )

        if self._subagent_host_launch_prefix and any(not isinstance(token, str) or not token.strip() for token in self._subagent_host_launch_prefix):
            raise ValueError("subagent_host_launch_prefix must contain only non-empty string tokens")

    def _clamp_timeout(self, timeout: int | None) -> int:
        """
        Clamp timeout to configured min/max range.

        Args:
            timeout: Requested timeout in seconds (None uses default)

        Returns:
            Timeout clamped to [min_timeout, max_timeout] range
        """
        effective_timeout = timeout if timeout is not None else self.default_timeout
        return max(self.min_timeout, min(self.max_timeout, effective_timeout))

    def _resolve_effective_runtime_mode(self) -> tuple[str, str | None]:
        """
        Resolve the effective runtime mode for subagent launch.

        Returns:
            Tuple of (effective_mode, warning_message).
            warning_message is populated only when explicit fallback is used.
        """
        if self._subagent_runtime_mode == "inherited":
            return "inherited", None

        if self._subagent_runtime_mode == "delegated":
            if not self._running_inside_container:
                raise RuntimeError(
                    "Subagent runtime mode 'delegated' requires running inside a container " "(/.dockerenv must exist). Use 'isolated' or 'inherited' for non-containerized runtimes.",
                )
            if not self._delegation_directory:
                raise RuntimeError(
                    "Subagent runtime mode 'delegated' requires delegation_directory to be set. " "The delegation directory is the shared path for container-to-host communication.",
                )
            return "delegated", None

        # isolated mode requested
        if not self._running_inside_container:
            return "isolated", None

        if self._subagent_host_launch_prefix:
            return "isolated", None

        error_message = (
            "Subagent runtime isolation requested, but parent runtime is containerized and no "
            "host launch bridge is configured. Configure coordination.subagent_host_launch_prefix "
            "for isolated launch, or set coordination.subagent_runtime_fallback_mode: inherited "
            "to explicitly opt into shared-runtime fallback."
        )

        if self._subagent_runtime_fallback_mode == "inherited":
            warning = (
                "Subagent runtime isolation prerequisites unavailable; using explicit fallback "
                "mode 'inherited'. Configure coordination.subagent_host_launch_prefix to restore "
                "isolated launch behavior."
            )
            logger.warning(f"[SubagentManager] {warning}")
            return "inherited", warning

        raise RuntimeError(error_message)

    def _build_subagent_command(
        self,
        yaml_path: Path,
        answer_file: Path,
        full_task: str,
        runtime_mode: str,
    ) -> list[str]:
        """Build the subprocess command for a subagent launch."""
        parse_at_references = False  # Subagent tasks are AI-generated; default off
        if self._subagent_orchestrator_config is not None:
            parse_at_references = self._subagent_orchestrator_config.parse_at_references

        base_cmd = [
            "uv",
            "run",
            "massgen",
            "--config",
            str(yaml_path),
            "--automation",
            "--output-file",
            str(answer_file),
        ]
        if not parse_at_references:
            base_cmd.append("--no-parse-at-references")
        base_cmd.append(full_task)

        if runtime_mode == "isolated" and self._running_inside_container and self._subagent_host_launch_prefix:
            return [*self._subagent_host_launch_prefix, *base_cmd]

        return base_cmd

    @staticmethod
    def _combine_warnings(primary: str | None, secondary: str | None) -> str | None:
        """Combine two optional warning strings without duplication."""
        warnings = [w for w in (primary, secondary) if w]
        if not warnings:
            return None
        if len(warnings) == 1:
            return warnings[0]
        if warnings[0] == warnings[1]:
            return warnings[0]
        return f"{warnings[0]} | {warnings[1]}"

    def _normalize_parent_context_paths(
        self,
        context_paths: list[dict[str, Any]] | None,
    ) -> list[dict[str, str]]:
        """
        Normalize parent context paths to absolute, read-only entries and always include the parent workspace.
        """
        normalized: list[dict[str, str]] = []
        seen: set[str] = set()
        workspace_path = str(self.parent_workspace.resolve())

        if context_paths:
            for entry in context_paths:
                raw_path = None
                if isinstance(entry, str):
                    raw_path = entry
                elif isinstance(entry, dict):
                    raw_path = entry.get("path")
                if not raw_path:
                    continue
                path_obj = Path(raw_path)
                resolved_path = path_obj if path_obj.is_absolute() else (self.parent_workspace / path_obj)
                resolved_str = str(resolved_path.resolve())
                if resolved_str in seen:
                    continue
                seen.add(resolved_str)
                normalized.append({"path": resolved_str, "permission": "read"})

        if workspace_path not in seen:
            normalized.insert(0, {"path": workspace_path, "permission": "read"})

        return normalized

    def _resolve_context_paths_for_subagent(
        self,
        config: "SubagentConfig",
    ) -> list[dict[str, str]]:
        """Resolve and validate context_paths from a subagent config.

        Resolves relative paths against the parent workspace and validates that
        each resolved path falls within an allowed root: either the parent
        workspace itself or one of the inherited parent context path roots.

        Paths that escape all allowed roots are rejected with a warning log
        to prevent path traversal attacks from model-supplied input.

        Args:
            config: SubagentConfig with context_paths to resolve.

        Returns:
            List of validated context path dicts with "path" and "permission" keys.
        """
        resolved_paths: list[dict[str, str]] = []

        parent_ws_resolved = self.parent_workspace.resolve()

        # Build set of allowed roots based on config flags.
        # include_parent_workspace (default True): allow explicit context_paths under parent ws.
        # agent_temporary_workspace: always allowed when configured (contains only peer
        # snapshots visible to this agent — framework-managed, safe to always allow).
        # Parent context path roots (from orchestrator config) are always allowed.
        allowed_roots: list[Path] = []
        if config.include_parent_workspace:
            allowed_roots.append(parent_ws_resolved)
        for pcp in self._parent_context_paths:
            root = Path(pcp["path"])
            if root not in allowed_roots:
                allowed_roots.append(root)
        # Always allow agent_temporary_workspace paths (agent-specific dir containing
        # only peer snapshots this agent is already allowed to see).
        if self._agent_temporary_workspace:
            temp_root = self._agent_temporary_workspace
            if not temp_root.is_absolute():
                temp_root = (self.parent_workspace / temp_root).resolve()
            else:
                temp_root = temp_root.resolve()
            if temp_root not in allowed_roots:
                allowed_roots.append(temp_root)

        if not config.context_paths:
            return resolved_paths

        seen: set[str] = set()
        for rel_path in config.context_paths:
            candidate = Path(rel_path)
            if candidate.is_absolute():
                resolved = candidate.resolve()
            else:
                resolved = (self.parent_workspace / rel_path).resolve()

            # Validate: resolved path must be within an allowed root
            is_allowed = any(resolved == root or resolved.is_relative_to(root) for root in allowed_roots)
            if not is_allowed:
                logger.warning(
                    f"[SubagentManager] Rejecting context_path '{rel_path}': " f"resolved to {resolved} which is outside allowed roots",
                )
                continue

            path_str = str(resolved)
            if path_str not in seen:
                seen.add(path_str)
                resolved_paths.append({"path": path_str, "permission": "read"})
                logger.info(f"[SubagentManager] Mounting context path: {path_str}")

        return resolved_paths

    def register_completion_callback(
        self,
        callback: Callable[[str, "SubagentResult"], None],
    ) -> None:
        """
        Register a callback to be invoked when any background subagent completes.

        The callback receives the subagent_id and SubagentResult when a background
        subagent finishes execution (success, timeout, or error). This is used
        to notify the Orchestrator about completed background subagents so results
        can be injected into the parent agent's context.

        Args:
            callback: Function that takes (subagent_id: str, result: SubagentResult)

        Example:
            def on_complete(subagent_id: str, result: SubagentResult):
                print(f"Subagent {subagent_id} completed: {result.status}")

            manager.register_completion_callback(on_complete)
        """
        self._completion_callbacks.append(callback)
        logger.debug(
            f"[SubagentManager] Registered completion callback, " f"total callbacks: {len(self._completion_callbacks)}",
        )

    def _invoke_completion_callbacks(
        self,
        subagent_id: str,
        result: "SubagentResult",
    ) -> None:
        """
        Invoke all registered completion callbacks for a finished subagent.

        Errors in individual callbacks are caught and logged but don't
        prevent other callbacks from executing.

        Args:
            subagent_id: ID of the completed subagent
            result: The subagent's execution result
        """
        for callback in self._completion_callbacks:
            try:
                callback(subagent_id, result)
            except Exception as e:
                logger.error(
                    f"[SubagentManager] Completion callback error for {subagent_id}: {e}",
                    exc_info=True,
                )

    def _create_workspace(self, subagent_id: str) -> Path:
        """
        Create isolated workspace for a subagent.

        Args:
            subagent_id: Unique subagent identifier

        Returns:
            Path to the subagent's workspace directory
        """
        subagent_dir = self.subagents_base / subagent_id
        workspace = subagent_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)

        # Create metadata file
        metadata = {
            "subagent_id": subagent_id,
            "parent_agent_id": self.parent_agent_id,
            "created_at": datetime.now().isoformat(),
            "workspace_path": str(workspace),
        }
        metadata_file = subagent_dir / "_metadata.json"
        metadata_file.write_text(json.dumps(metadata, indent=2))

        logger.info(f"[SubagentManager] Created workspace for {subagent_id}: {workspace}")
        return workspace

    def _get_subagent_log_dir(self, subagent_id: str) -> Path | None:
        """
        Get or create the log directory for a subagent.

        Args:
            subagent_id: Subagent identifier

        Returns:
            Path to subagent log directory, or None if logging not configured
        """
        if not self._subagent_logs_base:
            return None

        log_dir = self._subagent_logs_base / subagent_id
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir

    def _create_live_logs_symlink(self, subagent_id: str, workspace: Path) -> None:
        """Create a symlink to the subprocess's live log directory.

        This enables the TUI to stream logs in real-time during subagent execution.
        The symlink points to workspace/.massgen/massgen_logs/ where the subprocess
        writes its logs. After completion, full_logs/ contains the copied logs.

        Args:
            subagent_id: Subagent identifier
            workspace: Subagent workspace path
        """
        if not self._subagent_logs_base:
            return

        log_dir = self._subagent_logs_base / subagent_id
        log_dir.mkdir(parents=True, exist_ok=True)

        live_logs_link = log_dir / "live_logs"
        target = workspace / ".massgen" / "massgen_logs"

        # Create the target directory so the symlink is valid immediately
        # The subprocess will populate it when it starts
        target.mkdir(parents=True, exist_ok=True)

        try:
            # Remove existing symlink if present
            if live_logs_link.is_symlink():
                live_logs_link.unlink()
            elif live_logs_link.exists():
                # Not a symlink but exists - skip to avoid data loss
                logger.warning(f"[SubagentManager] live_logs exists but is not a symlink: {live_logs_link}")
                return

            live_logs_link.symlink_to(target)
            logger.debug(f"[SubagentManager] Created live_logs symlink: {live_logs_link} -> {target}")
        except Exception as e:
            logger.warning(f"[SubagentManager] Failed to create live_logs symlink: {e}")

    def _append_conversation(
        self,
        subagent_id: str,
        role: str,
        content: str,
        agent_id: str | None = None,
    ) -> None:
        """
        Append a message to the conversation log.

        Args:
            subagent_id: Subagent identifier
            role: Message role (user, assistant, system)
            content: Message content
            agent_id: Optional agent ID for multi-agent orchestrator mode
        """
        log_dir = self._get_subagent_log_dir(subagent_id)
        if not log_dir:
            return

        conversation_file = log_dir / "conversation.json"

        # Read existing conversation
        conversation = []
        if conversation_file.exists():
            try:
                conversation = json.loads(conversation_file.read_text())
            except json.JSONDecodeError:
                logger.warning(
                    f"[SubagentManager] Corrupted conversation log {conversation_file}; starting fresh",
                )

        # Append new message
        message = {
            "timestamp": datetime.now().isoformat(),
            "role": role,
            "content": content,
        }
        if agent_id:
            message["agent_id"] = agent_id

        conversation.append(message)
        conversation_file.write_text(json.dumps(conversation, indent=2))

    def _save_subagent_to_registry(
        self,
        subagent_id: str,
        session_id: str | None,
        config: SubagentConfig,
        result: SubagentResult,
        continuable_via: str = "session",
    ) -> None:
        """Save subagent metadata to parent workspace registry.

        This registry tracks all subagents spawned in the current parent session,
        enabling continuation and discovery across turns.

        Registry format matches MCP server's _save_subagents_to_filesystem() format:
        {
            "parent_agent_id": "...",
            "orchestrator_id": "...",
            "subagents": [{"subagent_id": "...", ...}, ...]
        }

        Args:
            subagent_id: Unique subagent identifier
            session_id: Session ID for continuation (None if not yet available)
            config: Subagent configuration
            result: Execution result
            continuable_via: How this subagent can be continued ("session" or "context_recovery")
        """
        registry_file = self.subagents_base / "_registry.json"

        # Load existing registry or create new one with list format
        if registry_file.exists():
            try:
                registry = json.loads(registry_file.read_text())
                # Ensure subagents is a list (handle old dict format)
                if isinstance(registry.get("subagents"), dict):
                    # Convert old dict format to list format
                    old_dict = registry["subagents"]
                    registry["subagents"] = [{"subagent_id": k, **v} for k, v in old_dict.items()]
            except json.JSONDecodeError:
                logger.warning("[SubagentManager] Failed to parse registry, creating new one")
                registry = {
                    "parent_agent_id": self.parent_agent_id,
                    "orchestrator_id": self.orchestrator_id,
                    "subagents": [],
                }
        else:
            registry = {
                "parent_agent_id": self.parent_agent_id,
                "orchestrator_id": self.orchestrator_id,
                "subagents": [],
            }

        # Ensure metadata fields exist
        registry.setdefault("parent_agent_id", self.parent_agent_id)
        registry.setdefault("orchestrator_id", self.orchestrator_id)

        # Update or append subagent entry in list
        subagent_data = {
            "subagent_id": subagent_id,
            "session_id": session_id,
            "task": config.task[:200],  # Truncate for readability
            "status": result.status,
            "workspace": str(result.workspace_path),
            "created_at": datetime.now().isoformat(),
            "execution_time_seconds": result.execution_time_seconds,
            "success": result.success,
            "continuable": True,
            "continuable_via": continuable_via,
            "source_agent": self.parent_agent_id,
        }

        # Find and update existing entry, or append new one
        subagents_list = registry["subagents"]
        found = False
        for i, entry in enumerate(subagents_list):
            if entry.get("subagent_id") == subagent_id:
                subagents_list[i] = subagent_data
                found = True
                break

        if not found:
            subagents_list.append(subagent_data)

        # Write back to disk
        registry_file.write_text(json.dumps(registry, indent=2))
        logger.debug(f"[SubagentManager] Saved subagent {subagent_id} to registry")

    def _copy_context_files(
        self,
        subagent_id: str,
        context_files: list[str],
        workspace: Path,
    ) -> list[str]:
        """
        Copy context files from parent workspace to subagent workspace.

        Also automatically copies CONTEXT.md if it exists in parent workspace,
        ensuring subagents have task context for external API calls.

        Args:
            subagent_id: Subagent identifier
            context_files: List of relative paths to copy
            workspace: Subagent workspace path

        Returns:
            List of successfully copied files
        """
        copied = []

        # Auto-copy CONTEXT.md if it exists (for task context)
        context_md = self.parent_workspace / "CONTEXT.md"
        if context_md.exists() and context_md.is_file():
            dst = workspace / "CONTEXT.md"
            try:
                shutil.copy2(context_md, dst)
                copied.append("CONTEXT.md")
                logger.info(f"[SubagentManager] Auto-copied CONTEXT.md for {subagent_id}")
            except Exception as e:
                logger.warning(f"[SubagentManager] Failed to copy CONTEXT.md: {e}")

        for rel_path in context_files:
            src = self.parent_workspace / rel_path
            if not src.exists():
                logger.warning(f"[SubagentManager] Context file not found: {src}")
                continue

            # Preserve directory structure
            dst = workspace / rel_path
            dst.parent.mkdir(parents=True, exist_ok=True)

            if src.is_file():
                shutil.copy2(src, dst)
                copied.append(rel_path)
            elif src.is_dir():
                shutil.copytree(
                    src,
                    dst,
                    dirs_exist_ok=True,
                    symlinks=True,
                    ignore_dangling_symlinks=True,
                )
                copied.append(rel_path)

        logger.info(f"[SubagentManager] Copied {len(copied)} context files for {subagent_id}")
        return copied

    def _build_subagent_system_prompt(
        self,
        config: SubagentConfig,
        workspace: Path | None = None,
    ) -> tuple[str, str | None]:
        """
        Build system prompt for subagent.

        Subagents get a minimal system prompt focused on their specific task.
        They cannot spawn their own subagents.

        Args:
            config: Subagent configuration
            workspace: Optional workspace path to read CONTEXT.md from

        Returns:
            Tuple of (system_prompt, context_warning).
            context_warning is set if CONTEXT.md was truncated.
        """
        base_prompt = config.system_prompt

        # Load task context from CONTEXT.md (required)
        context_section = ""
        task_context = None
        context_warning = None

        # Try to read CONTEXT.md from workspace using shared utility
        if workspace:
            from massgen.context.task_context import load_task_context_with_warning

            task_context, context_warning = load_task_context_with_warning(str(workspace))

        # CONTEXT.md is required for subagents
        # Note: This should have been validated earlier in spawn_subagent/spawn_subagent_background
        # If we reach here without task_context, something went wrong in the validation
        if not task_context:
            logger.warning(
                "[SubagentManager] CONTEXT.md missing in system prompt builder " "(should have been validated earlier)",
            )
            # Use empty context rather than crashing
            context_section = ""
        else:
            context_section = f"""
**Task Context:**
{task_context}

"""

        subagent_prompt = f"""## Subagent Context

You are a subagent spawned to work on a specific task. Your workspace is isolated and independent.
{context_section}
**Important:**
- Focus only on the task you were given
- Create any necessary files in your workspace
- You cannot spawn additional subagents
- Do not ask the human or request human input; subagents cannot broadcast to humans

**Output Requirements:**
- In your final answer, clearly list all files you want the parent agent to see along with their FULL ABSOLUTE PATHS. You can also list directories if needed.
- You should NOT list every single file as the parent agent does not need to know every file you created -- this context isolation is a main feature of subagents.
- The parent agent will copy files from your workspace based on your answer
- Format file paths clearly, e.g.: "Files created: /path/to/file1.md, /path/to/file2.py"

**Your Task:**
{config.task}
"""
        if base_prompt:
            subagent_prompt = f"{base_prompt}\n\n{subagent_prompt}"

        return subagent_prompt, context_warning

    async def _execute_subagent(
        self,
        config: SubagentConfig,
        workspace: Path,
    ) -> SubagentResult:
        """
        Execute a subagent task - routes to single agent or orchestrator mode.

        Args:
            config: Subagent configuration
            workspace: Path to subagent workspace

        Returns:
            SubagentResult with execution outcome
        """
        start_time = time.time()

        # Capture context warning early so it's available for all error paths
        from massgen.context.task_context import load_task_context_with_warning

        _, context_warning = load_task_context_with_warning(str(workspace))

        # Determine effective runtime mode
        try:
            runtime_mode, _ = self._resolve_effective_runtime_mode()
        except RuntimeError as e:
            return SubagentResult.create_error(
                subagent_id=config.id,
                error=str(e),
                workspace_path=str(workspace),
                execution_time_seconds=0.0,
                warning=context_warning,
            )

        try:
            if runtime_mode == "delegated":
                result = await self._execute_delegated(
                    config,
                    workspace,
                    start_time,
                    context_warning,
                )
            else:
                # Always use orchestrator mode for non-delegated execution
                result = await self._execute_with_orchestrator(
                    config,
                    workspace,
                    start_time,
                    context_warning,
                )

        except TimeoutError:
            execution_time = time.time() - start_time
            log_dir = self._get_subagent_log_dir(config.id)
            # Attempt to recover completed work from workspace
            result = self._create_timeout_result_with_recovery(
                subagent_id=config.id,
                workspace=workspace,
                timeout_seconds=execution_time,
                log_path=str(log_dir) if log_dir else None,
                warning=context_warning,
            )

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"[SubagentManager] Error executing subagent {config.id}: {e}")
            result = SubagentResult.create_error(
                subagent_id=config.id,
                error=str(e),
                workspace_path=str(workspace),
                execution_time_seconds=execution_time,
                warning=context_warning,
            )

        self._persist_round_evaluator_packet_if_needed(config, workspace, result)
        return result

    def _persist_round_evaluator_packet_if_needed(
        self,
        config: SubagentConfig,
        workspace: Path,
        result: SubagentResult,
    ) -> None:
        """Persist a stable synthesized critique packet for round_evaluator subagents."""
        subagent_type = str((config.metadata or {}).get("subagent_type") or "").strip().lower()
        if subagent_type != "round_evaluator":
            return

        from .models import RoundEvaluatorResult

        packet_path = workspace / "critique_packet.md"
        packet_text, packet_source = RoundEvaluatorResult.resolve_packet_artifact(
            workspace_path=str(workspace),
            log_path=result.log_path,
        )
        if packet_text and packet_source and not packet_path.exists():
            try:
                packet_path.write_text(packet_text, encoding="utf-8")
            except OSError as exc:
                logger.warning(
                    "[SubagentManager] Failed to persist canonical round_evaluator packet for %s: %s",
                    config.id,
                    exc,
                )

        verdict_path = workspace / "verdict.json"
        verdict_data, _verdict_source = RoundEvaluatorResult.resolve_verdict_artifact(
            workspace_path=str(workspace),
            log_path=result.log_path,
        )
        if verdict_data and not verdict_path.exists():
            try:
                verdict_path.write_text(
                    json.dumps(verdict_data, indent=2),
                    encoding="utf-8",
                )
            except OSError as exc:
                logger.warning(
                    "[SubagentManager] Failed to persist canonical verdict artifact for %s: %s",
                    config.id,
                    exc,
                )

        next_tasks_path = workspace / "next_tasks.json"
        next_tasks, _artifact_path = RoundEvaluatorResult.resolve_next_tasks_artifact(
            workspace_path=str(workspace),
            log_path=result.log_path,
        )
        if not next_tasks or next_tasks_path.exists():
            return

        try:
            next_tasks_path.write_text(
                json.dumps(next_tasks, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning(
                "[SubagentManager] Failed to persist canonical next_tasks payload for %s: %s",
                config.id,
                exc,
            )

    async def _execute_with_orchestrator(
        self,
        config: SubagentConfig,
        workspace: Path,
        start_time: float,
        context_warning: str | None = None,
    ) -> SubagentResult:
        """
        Execute subagent by spawning a separate MassGen process.

        This approach avoids nested MCP/async issues by running the subagent
        as a completely independent MassGen instance with its own YAML config.

        Args:
            config: Subagent configuration
            workspace: Path to subagent workspace
            start_time: Execution start time
            context_warning: Warning message if CONTEXT.md was truncated

        Returns:
            SubagentResult with execution outcome
        """
        orch_config = self._subagent_orchestrator_config

        # Build context paths from config.context_files
        # These are ALWAYS read-only - subagents cannot write to context paths.
        # If the parent agent needs changes from the subagent, it should copy
        # the desired files from the subagent's workspace after completion.
        context_paths: list[dict[str, str]] = []
        if config.context_files:
            for ctx_file in config.context_files:
                src_path = Path(ctx_file)
                if src_path.exists():
                    context_paths.append(
                        {
                            "path": str(src_path.resolve()),
                            "permission": "read",
                        },
                    )
                    logger.info(f"[SubagentManager] Adding read-only context path: {src_path}")
                else:
                    logger.warning(f"[SubagentManager] Context file not found: {ctx_file}")

        # Resolve config.context_paths with path traversal validation
        validated_ctx_paths = self._resolve_context_paths_for_subagent(config)
        existing = {p["path"] for p in context_paths}
        for vcp in validated_ctx_paths:
            if vcp["path"] not in existing:
                context_paths.append(vcp)
                existing.add(vcp["path"])

        workspace_abs = workspace.resolve()

        # Generate temporary YAML config for the subagent
        subagent_yaml = self._generate_subagent_yaml_config(config, workspace, context_paths)
        yaml_path = workspace_abs / f"subagent_config_{config.id}.yaml"
        yaml_path.write_text(yaml.dump(subagent_yaml, default_flow_style=False))

        num_agents = orch_config.num_agents if orch_config else 1
        logger.info(
            f"[SubagentManager] Executing subagent {config.id} via subprocess " f"({num_agents} agents), config: {yaml_path}",
        )

        # Build the task - system prompt already includes the task at the end
        # Pass workspace to read CONTEXT.md for task context
        # Note: context_warning is passed in from _execute_subagent, so we ignore the one from _build_subagent_system_prompt
        system_prompt, _ = self._build_subagent_system_prompt(config, workspace)
        full_task = system_prompt
        runtime_mode, runtime_warning = self._resolve_effective_runtime_mode()
        combined_warning = self._combine_warnings(context_warning, runtime_warning)

        # Build command to run MassGen as subprocess.
        # In isolated mode on containerized parent runtimes, an optional host launch
        # prefix is used to cross runtime boundaries.
        answer_file = workspace_abs / "answer.txt"
        cmd = self._build_subagent_command(
            yaml_path=yaml_path,
            answer_file=answer_file,
            full_task=full_task,
            runtime_mode=runtime_mode,
        )

        logger.info(
            f"[SubagentManager] Launching {config.id} with runtime_mode={runtime_mode}, " f"containerized_parent={self._running_inside_container}",
        )

        process: asyncio.subprocess.Process | None = None
        try:
            # Use async subprocess for graceful cancellation support
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=SUBPROCESS_STREAM_LIMIT,
                cwd=str(workspace_abs),
                env=self._clean_subprocess_env(),
            )

            # Track the process for potential cancellation
            self._active_processes[config.id] = process

            # Create symlink to live logs for TUI streaming
            # The subprocess writes to workspace/.massgen/massgen_logs/
            # We symlink this to _subagent_logs_base/{id}/live_logs for easy access
            self._create_live_logs_symlink(config.id, workspace)

            # Wait with timeout (clamped to configured min/max)
            timeout = self._clamp_timeout(config.timeout_seconds)
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except TimeoutError:
                # Kill the process on timeout
                logger.warning(f"[SubagentManager] Subagent {config.id} timed out, terminating...")
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except TimeoutError:
                    process.kill()
                    await process.wait()
                raise
            finally:
                # Remove from active processes
                self._active_processes.pop(config.id, None)

            if process.returncode == 0:
                # Read answer from the output file
                if answer_file.exists():
                    answer = answer_file.read_text().strip()
                else:
                    # Fallback to stdout if file wasn't created
                    answer = stdout.decode() if stdout else ""

                execution_time = time.time() - start_time

                # Get token usage, log path, and session ID from subprocess's status.json
                token_usage, subprocess_log_dir, session_id = self._parse_subprocess_status(workspace)

                # Track session ID for continuation support
                if session_id:
                    self._subagent_sessions[config.id] = session_id
                    logger.info(f"[SubagentManager] Tracked session ID for {config.id}: {session_id}")

                # Write reference to subprocess log directory
                self._write_subprocess_log_reference(config.id, subprocess_log_dir)

                # Get log directory path for the result
                log_dir = self._get_subagent_log_dir(config.id)

                return SubagentResult.create_success(
                    subagent_id=config.id,
                    answer=answer,
                    workspace_path=str(workspace),
                    execution_time_seconds=execution_time,
                    token_usage=token_usage,
                    log_path=str(log_dir) if log_dir else None,
                    warning=combined_warning,
                )
            else:
                stderr_text = stderr.decode() if stderr else ""
                stdout_text = stdout.decode() if stdout else ""
                error_msg = stderr_text.strip() or stdout_text.strip()[:500] or f"Subprocess exited with code {process.returncode}"

                # Log detailed error information for debugging
                logger.error(
                    f"[SubagentManager] Subagent {config.id} failed with exit code {process.returncode}\n"
                    f"Command: {' '.join(cmd)}\n"
                    f"Working directory: {workspace}\n"
                    f"STDERR: {stderr_text[:1000]}\n"  # First 1000 chars of stderr
                    f"STDOUT: {stdout_text[:500]}",  # First 500 chars of stdout
                )

                # Still try to get log path for debugging
                _, subprocess_log_dir, _ = self._parse_subprocess_status(workspace)
                self._write_subprocess_log_reference(config.id, subprocess_log_dir, error=error_msg)
                log_dir = self._get_subagent_log_dir(config.id)
                return SubagentResult.create_error(
                    subagent_id=config.id,
                    error=error_msg,
                    workspace_path=str(workspace),
                    execution_time_seconds=time.time() - start_time,
                    log_path=str(log_dir) if log_dir else None,
                    warning=combined_warning,
                )

        except TimeoutError:
            logger.error(f"[SubagentManager] Subagent {config.id} timed out")
            # Still copy logs even on timeout - they contain useful debugging info
            _, subprocess_log_dir, _ = self._parse_subprocess_status(workspace)
            self._write_subprocess_log_reference(config.id, subprocess_log_dir, error="Subagent timed out")
            log_dir = self._get_subagent_log_dir(config.id)
            # Attempt to recover completed work from workspace
            return self._create_timeout_result_with_recovery(
                subagent_id=config.id,
                workspace=workspace,
                timeout_seconds=timeout,  # Use the clamped timeout
                log_path=str(log_dir) if log_dir else None,
                warning=combined_warning,
            )
        except asyncio.CancelledError:
            # Handle graceful cancellation (e.g., from Ctrl+C)
            logger.warning(f"[SubagentManager] Subagent {config.id} cancelled")
            if process and process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except TimeoutError:
                    process.kill()
            self._active_processes.pop(config.id, None)
            # Still copy logs even on cancellation - they contain useful debugging info
            _, subprocess_log_dir, _ = self._parse_subprocess_status(workspace)
            self._write_subprocess_log_reference(config.id, subprocess_log_dir, error="Subagent cancelled")
            log_dir = self._get_subagent_log_dir(config.id)
            # Attempt to recover completed work from workspace
            return self._create_timeout_result_with_recovery(
                subagent_id=config.id,
                workspace=workspace,
                timeout_seconds=time.time() - start_time,
                log_path=str(log_dir) if log_dir else None,
                warning=combined_warning,
            )
        except Exception as e:
            logger.error(f"[SubagentManager] Subagent {config.id} error: {e}")
            # Still copy logs even on error - they contain useful debugging info
            _, subprocess_log_dir, _ = self._parse_subprocess_status(workspace)
            self._write_subprocess_log_reference(config.id, subprocess_log_dir, error=str(e))
            log_dir = self._get_subagent_log_dir(config.id)
            return SubagentResult.create_error(
                subagent_id=config.id,
                error=str(e),
                workspace_path=str(workspace),
                execution_time_seconds=time.time() - start_time,
                log_path=str(log_dir) if log_dir else None,
                warning=combined_warning,
            )

    async def _execute_delegated(
        self,
        config: "SubagentConfig",
        workspace: Path,
        start_time: float,
        context_warning: str | None = None,
    ) -> "SubagentResult":
        """
        Execute a subagent via file-based delegation to a host-side watcher.

        The container writes a DelegationRequest file; the host-side
        SubagentLaunchWatcher creates an isolated Docker container and writes back
        a DelegationResponse.  This avoids Docker-in-Docker and Docker socket
        mounting inside the parent container.

        Args:
            config: Subagent configuration
            workspace: Path to subagent workspace (already created)
            start_time: Execution start time (from time.time())
            context_warning: Optional CONTEXT.md warning to propagate

        Returns:
            SubagentResult with execution outcome
        """
        import secrets

        import yaml

        from massgen.subagent.delegation_protocol import (
            DELEGATION_PROTOCOL_VERSION,
            DelegationRequest,
            DelegationResponse,
            response_path,
            write_cancel_sentinel,
        )

        delegation_dir = Path(self._delegation_directory)  # type: ignore[arg-type]
        delegation_dir.mkdir(parents=True, exist_ok=True)

        # Build context paths for YAML config
        context_paths: list[dict[str, str]] = []
        if config.context_files:
            for ctx_file in config.context_files:
                src_path = Path(ctx_file)
                if src_path.exists():
                    context_paths.append({"path": str(src_path.resolve()), "permission": "read"})
        validated_ctx_paths = self._resolve_context_paths_for_subagent(config)
        existing = {p["path"] for p in context_paths}
        for vcp in validated_ctx_paths:
            if vcp["path"] not in existing:
                context_paths.append(vcp)
                existing.add(vcp["path"])

        workspace_abs = workspace.resolve()

        # Generate YAML config and write to workspace (for reference / debugging)
        subagent_yaml = self._generate_subagent_yaml_config(config, workspace, context_paths)
        yaml_path = workspace_abs / f"subagent_config_{config.id}.yaml"
        yaml_path.write_text(yaml.dump(subagent_yaml, default_flow_style=False))

        # Build system prompt / task string
        full_task, _ = self._build_subagent_system_prompt(config, workspace)

        answer_file = workspace_abs / "answer.txt"
        request_id = secrets.token_hex(8)

        # Create live logs symlink BEFORE writing request (TUI can start watching immediately)
        self._create_live_logs_symlink(config.id, workspace)

        # Write delegation request (atomic)
        timeout = self._clamp_timeout(config.timeout_seconds)
        req = DelegationRequest(
            version=DELEGATION_PROTOCOL_VERSION,
            subagent_id=config.id,
            request_id=request_id,
            task=full_task,
            yaml_config=subagent_yaml,
            answer_file=str(answer_file),
            workspace=str(workspace_abs),
            timeout_seconds=timeout,
        )
        req.to_file(delegation_dir)

        logger.info(
            f"[SubagentManager] Delegated request written for {config.id}, " f"timeout={timeout}s, delegation_dir={delegation_dir}",
        )

        # Poll for response file with timeout + 30s grace
        grace_seconds = 30
        poll_deadline = start_time + timeout + grace_seconds
        poll_interval = 0.5

        response: DelegationResponse | None = None
        resp_path = response_path(delegation_dir, config.id)

        try:
            while True:
                remaining = poll_deadline - time.time()
                if remaining <= 0:
                    logger.warning(f"[SubagentManager] Delegated subagent {config.id} timed out waiting for response")
                    write_cancel_sentinel(delegation_dir, config.id)
                    log_dir = self._get_subagent_log_dir(config.id)
                    return self._create_timeout_result_with_recovery(
                        subagent_id=config.id,
                        workspace=workspace,
                        timeout_seconds=timeout,
                        log_path=str(log_dir) if log_dir else None,
                        warning=context_warning,
                    )

                if resp_path.exists():
                    try:
                        response = DelegationResponse.from_file(resp_path)
                        break
                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        logger.debug(f"[SubagentManager] Response not yet ready for {config.id}: {e}")

                await asyncio.sleep(poll_interval)

        except asyncio.CancelledError:
            logger.warning(f"[SubagentManager] Delegated subagent {config.id} cancelled")
            write_cancel_sentinel(delegation_dir, config.id)
            log_dir = self._get_subagent_log_dir(config.id)
            return self._create_timeout_result_with_recovery(
                subagent_id=config.id,
                workspace=workspace,
                timeout_seconds=time.time() - start_time,
                log_path=str(log_dir) if log_dir else None,
                warning=context_warning,
            )

        finally:
            # Clean up request and response files
            try:
                req_file = delegation_dir / f"request_{config.id}.json"
                if req_file.exists():
                    req_file.unlink()
                if resp_path.exists():
                    resp_path.unlink()
            except OSError as e:
                logger.debug(f"[SubagentManager] Cleanup of delegation files for {config.id}: {e}")

        # Process response
        execution_time = time.time() - start_time
        log_dir = self._get_subagent_log_dir(config.id)

        if response.status == "completed" and response.exit_code == 0:
            answer = answer_file.read_text().strip() if answer_file.exists() else ""
            token_usage, subprocess_log_dir, session_id = self._parse_subprocess_status(workspace)
            self._write_subprocess_log_reference(config.id, subprocess_log_dir)
            if session_id:
                self._subagent_sessions[config.id] = session_id
            return SubagentResult(
                subagent_id=config.id,
                status="completed",
                success=True,
                answer=answer,
                workspace_path=str(workspace),
                execution_time_seconds=execution_time,
                token_usage=token_usage,
                log_path=str(log_dir) if log_dir else None,
                warning=context_warning,
            )

        elif response.status == "timeout":
            return self._create_timeout_result_with_recovery(
                subagent_id=config.id,
                workspace=workspace,
                timeout_seconds=timeout,
                log_path=str(log_dir) if log_dir else None,
                warning=context_warning,
            )

        else:
            # error or cancelled
            error_msg = f"Delegated subagent {config.id} {response.status} " f"(exit_code={response.exit_code}): {response.stderr_tail[:500]}"
            logger.error(f"[SubagentManager] {error_msg}")
            _, subprocess_log_dir, _ = self._parse_subprocess_status(workspace)
            self._write_subprocess_log_reference(config.id, subprocess_log_dir, error=error_msg)
            return SubagentResult.create_error(
                subagent_id=config.id,
                error=error_msg,
                workspace_path=str(workspace),
                execution_time_seconds=execution_time,
                log_path=str(log_dir) if log_dir else None,
                warning=context_warning,
            )

    async def execute_with_streaming(
        self,
        config: SubagentConfig,
        on_event: "Callable[[MassGenEvent], Awaitable[None]]",
        refine: bool = True,
    ) -> SubagentResult:
        """Execute subagent with real-time event streaming.

        This method spawns a subagent subprocess with --stream-events flag,
        allowing real-time event streaming to a callback (typically the TUI
        subagent modal). Events are parsed from stdout as JSON lines.

        Args:
            config: Subagent configuration
            on_event: Async callback to receive each MassGenEvent
            refine: If True (default), allow multi-round coordination.
                    If False, return first answer without iteration.

        Returns:
            SubagentResult with execution outcome
        """
        from massgen.events import MassGenEvent

        start_time = time.time()

        # Create workspace
        workspace = self._create_workspace(config.id)

        # Copy context files
        self._copy_context_files(config.id, config.context_files or [], workspace)

        # Verify CONTEXT.md exists (required for subagents)
        context_md = workspace / "CONTEXT.md"
        if not context_md.exists():
            error_msg = "CONTEXT.md not found in workspace. " "Before spawning subagents, create a CONTEXT.md file with task context."
            logger.error(f"[SubagentManager] {error_msg}")
            return SubagentResult.create_error(
                subagent_id=config.id,
                error=error_msg,
                workspace_path=str(workspace),
            )

        # Load context warning for the result
        from massgen.context.task_context import load_task_context_with_warning

        _, context_warning = load_task_context_with_warning(str(workspace))

        # Track state
        state = SubagentState(
            config=config,
            status="running",
            workspace_path=str(workspace),
            started_at=datetime.now(),
        )
        self._subagents[config.id] = state

        # Build context paths from config.context_files
        context_paths: list[dict[str, str]] = []
        if config.context_files:
            for ctx_file in config.context_files:
                src_path = Path(ctx_file)
                if src_path.exists():
                    context_paths.append(
                        {
                            "path": str(src_path.resolve()),
                            "permission": "read",
                        },
                    )

        # Resolve config.context_paths with path traversal validation
        validated_ctx_paths = self._resolve_context_paths_for_subagent(config)
        existing = {p["path"] for p in context_paths}
        for vcp in validated_ctx_paths:
            if vcp["path"] not in existing:
                context_paths.append(vcp)
                existing.add(vcp["path"])

        workspace_abs = workspace.resolve()

        # Generate YAML config
        config.metadata = config.metadata or {}
        config.metadata["refine"] = refine
        subagent_yaml = self._generate_subagent_yaml_config(config, workspace, context_paths)
        yaml_path = workspace_abs / f"subagent_config_{config.id}.yaml"
        yaml_path.write_text(yaml.dump(subagent_yaml, default_flow_style=False))

        # Build system prompt and task
        system_prompt, _ = self._build_subagent_system_prompt(config, workspace)
        full_task = system_prompt
        try:
            runtime_mode, runtime_warning = self._resolve_effective_runtime_mode()
        except RuntimeError as e:
            result = SubagentResult.create_error(
                subagent_id=config.id,
                error=str(e),
                workspace_path=str(workspace),
                execution_time_seconds=time.time() - start_time,
                warning=context_warning,
            )
            state.status = "failed"
            state.result = result
            return result
        combined_warning = self._combine_warnings(context_warning, runtime_warning)

        # Build command with --stream-events for real-time event streaming
        answer_file = workspace_abs / "answer.txt"
        base_cmd = self._build_subagent_command(
            yaml_path=yaml_path,
            answer_file=answer_file,
            full_task=full_task,
            runtime_mode=runtime_mode,
        )
        cmd = base_cmd[:]
        if "--automation" in cmd:
            cmd.remove("--automation")
        if "--stream-events" not in cmd:
            output_idx = cmd.index("--output-file")
            cmd.insert(output_idx, "--stream-events")  # implies --automation

        logger.info(
            f"[SubagentManager] Streaming launch for {config.id} with runtime_mode={runtime_mode}, " f"containerized_parent={self._running_inside_container}",
        )

        logger.info(
            f"[SubagentManager] Executing subagent {config.id} with streaming, " f"config: {yaml_path}",
        )

        process: asyncio.subprocess.Process | None = None
        try:
            # Use async subprocess for real-time streaming
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=SUBPROCESS_STREAM_LIMIT,
                cwd=str(workspace_abs),
                env=self._clean_subprocess_env(),
            )

            # Track the process for potential cancellation
            self._active_processes[config.id] = process

            # Create symlink to live logs for TUI streaming
            self._create_live_logs_symlink(config.id, workspace)

            # Read stdout line by line, parse events, call callback
            non_event_stdout_lines: list[str] = []

            async def stream_events():
                if process.stdout:
                    async for line in process.stdout:
                        try:
                            line_str = line.decode().strip()
                            if line_str:
                                event = MassGenEvent.from_json(line_str)
                                await on_event(event)
                        except json.JSONDecodeError:
                            # Capture non-JSON lines for error diagnostics
                            non_event_stdout_lines.append(line.decode().strip())
                        except Exception as e:
                            logger.warning(f"[SubagentManager] Error processing event: {e}")

            # Drain stderr concurrently to prevent pipe buffer deadlock
            stderr_chunks: list[bytes] = []

            async def drain_stderr():
                if process.stderr:
                    async for line in process.stderr:
                        stderr_chunks.append(line)

            # Stream events with timeout, draining stderr concurrently
            timeout = self._clamp_timeout(config.timeout_seconds)
            stderr_task = asyncio.create_task(drain_stderr())
            try:
                await asyncio.wait_for(stream_events(), timeout=timeout)
                # Wait for process to complete after streaming is done
                await process.wait()
            except TimeoutError:
                logger.warning(f"[SubagentManager] Subagent {config.id} timed out, terminating...")
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except TimeoutError:
                    process.kill()
                    await process.wait()
                raise
            finally:
                # Clean up stderr drain task
                stderr_task.cancel()
                try:
                    await stderr_task
                except asyncio.CancelledError:
                    pass
                # Remove from active processes
                self._active_processes.pop(config.id, None)

            if process.returncode == 0:
                # Read answer from the output file
                if answer_file.exists():
                    answer = answer_file.read_text().strip()
                else:
                    answer = ""

                execution_time = time.time() - start_time

                # Get token usage and session ID from subprocess's status.json
                token_usage, subprocess_log_dir, session_id = self._parse_subprocess_status(workspace)

                # Track session ID for continuation support
                if session_id:
                    self._subagent_sessions[config.id] = session_id

                # Write reference to subprocess log directory
                self._write_subprocess_log_reference(config.id, subprocess_log_dir)

                # Get log directory path for the result
                log_dir = self._get_subagent_log_dir(config.id)

                result = SubagentResult.create_success(
                    subagent_id=config.id,
                    answer=answer,
                    workspace_path=str(workspace),
                    execution_time_seconds=execution_time,
                    token_usage=token_usage,
                    log_path=str(log_dir) if log_dir else None,
                    warning=combined_warning,
                )
            else:
                stderr_text = b"".join(stderr_chunks).decode(errors="replace")
                stdout_text = "\n".join(non_event_stdout_lines)
                error_msg = stderr_text.strip() or stdout_text.strip()[:500] or f"Subprocess exited with code {process.returncode}"

                logger.error(
                    f"[SubagentManager] Subagent {config.id} failed with exit code {process.returncode}\n" f"STDERR: {stderr_text[:1000]}\n" f"STDOUT (non-event): {stdout_text[:500]}",
                )

                _, subprocess_log_dir, _ = self._parse_subprocess_status(workspace)
                self._write_subprocess_log_reference(config.id, subprocess_log_dir, error=error_msg)
                log_dir = self._get_subagent_log_dir(config.id)

                result = SubagentResult.create_error(
                    subagent_id=config.id,
                    error=error_msg,
                    workspace_path=str(workspace),
                    execution_time_seconds=time.time() - start_time,
                    log_path=str(log_dir) if log_dir else None,
                    warning=combined_warning,
                )

            # Update state
            if result.success:
                state.status = "completed"
            else:
                state.status = "failed"
            state.result = result

            return result

        except TimeoutError:
            log_dir = self._get_subagent_log_dir(config.id)
            result = self._create_timeout_result_with_recovery(
                subagent_id=config.id,
                workspace=workspace,
                timeout_seconds=config.timeout_seconds or self.default_timeout,
                log_path=str(log_dir) if log_dir else None,
                warning=combined_warning,
            )
            state.status = "timeout"
            state.result = result
            return result

        except asyncio.CancelledError:
            logger.warning(f"[SubagentManager] Subagent {config.id} cancelled")
            if process and process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except TimeoutError:
                    process.kill()
            self._active_processes.pop(config.id, None)
            log_dir = self._get_subagent_log_dir(config.id)
            result = self._create_timeout_result_with_recovery(
                subagent_id=config.id,
                workspace=workspace,
                timeout_seconds=time.time() - start_time,
                log_path=str(log_dir) if log_dir else None,
                warning=combined_warning,
            )
            state.status = "cancelled"
            state.result = result
            return result

        except Exception as e:
            logger.error(f"[SubagentManager] Subagent {config.id} error: {e}")
            log_dir = self._get_subagent_log_dir(config.id)
            result = SubagentResult.create_error(
                subagent_id=config.id,
                error=str(e),
                workspace_path=str(workspace),
                execution_time_seconds=time.time() - start_time,
                log_path=str(log_dir) if log_dir else None,
                warning=combined_warning,
            )
            state.status = "failed"
            state.result = result
            return result

    def _generate_subagent_yaml_config(
        self,
        config: SubagentConfig,
        workspace: Path,
        context_paths: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """
        Generate a YAML config dict for the subagent MassGen process.

        Inherits relevant settings from parent agent configs but adjusts
        paths and disables subagent nesting.

        Args:
            config: Subagent configuration
            workspace: Workspace path for the subagent
            context_paths: Optional list of context path configs for file access

        Returns:
            Dictionary suitable for YAML serialization
        """
        orch_config = self._subagent_orchestrator_config
        refine = config.metadata.get("refine", True)
        subagent_type = str(config.metadata.get("subagent_type") or "").strip()
        inherit_spawning_agent_backend = bool(
            orch_config and getattr(orch_config, "inherit_spawning_agent_backend", False),
        )
        shared_child_team_types = list(getattr(orch_config, "shared_child_team_types", ["round_evaluator"])) if orch_config is not None else ["round_evaluator"]
        use_shared_common_agents_for_type = "*" in shared_child_team_types or subagent_type in shared_child_team_types
        matched_parent = next(
            (a for a in self.parent_agent_configs if str(a.get("id", "")).strip() == self.parent_agent_id),
            None,
        )

        common_agents = list(orch_config.agents) if orch_config and orch_config.agents else []
        local_agents: list[dict[str, Any]] = []
        synthetic_local = False

        if matched_parent is not None:
            local_agents = list(matched_parent.get("subagent_agents") or [])

        # Only types listed in shared_child_team_types default to the shared child
        # team. Other subagent types stay anchored to the spawning parent's backend
        # unless the parent explicitly defines its own child-team overrides.
        should_default_to_spawning_parent_backend = not use_shared_common_agents_for_type
        if not local_agents and (inherit_spawning_agent_backend or should_default_to_spawning_parent_backend):
            if matched_parent is None:
                if inherit_spawning_agent_backend:
                    raise ValueError(
                        "Unable to inherit backend for spawning parent agent " f"'{self.parent_agent_id}': parent agent config not found",
                    )
            else:
                local_agents = [
                    {
                        "id": matched_parent.get("id", self.parent_agent_id),
                        "backend": dict(matched_parent.get("backend", {})),
                    },
                ]
                synthetic_local = True

        source_agents_with_origin: list[tuple[dict[str, Any], str]]
        if common_agents and use_shared_common_agents_for_type:
            source_agents_with_origin = [(agent_cfg, "common") for agent_cfg in common_agents]
        elif local_agents:
            local_origin = "synthetic" if synthetic_local else "local"
            source_agents_with_origin = [(agent_cfg, local_origin) for agent_cfg in local_agents]
        elif common_agents:
            source_agents_with_origin = [(agent_cfg, "common") for agent_cfg in common_agents]
        else:
            source_agents_with_origin = [(agent_cfg, "legacy") for agent_cfg in self.parent_agent_configs]

        # Build agent configs - each agent needs a unique workspace directory
        agents = []
        num_agents = len(source_agents_with_origin) if source_agents_with_origin else 1

        for i in range(num_agents):
            # Create unique workspace for each agent
            agent_workspace = workspace / f"agent_{i+1}"
            agent_workspace.mkdir(parents=True, exist_ok=True)

            # Get source config for this agent
            if source_agents_with_origin and i < len(source_agents_with_origin):
                source_config, source_origin = source_agents_with_origin[i]
            else:
                source_config = {}
                source_origin = "legacy"

            # Build agent ID - use source id or auto-generate
            agent_id = source_config.get("id", f"{config.id}_agent_{i+1}")

            # Get backend config from source or use defaults
            source_backend = source_config.get("backend", {})

            # Shared/common entries fall back to the first parent backend.
            # Parent-local and synthesized entries fall back to the spawning parent's backend.
            if source_origin in {"local", "synthetic"} and matched_parent is not None:
                fallback_backend = matched_parent.get("backend", {})
            else:
                fallback_backend = self.parent_agent_configs[0].get("backend", {}) if self.parent_agent_configs else {}
            enable_mcp_command_line = source_backend.get("enable_mcp_command_line")
            if enable_mcp_command_line is None:
                enable_mcp_command_line = fallback_backend.get("enable_mcp_command_line", False)

            backend_config = {
                "type": source_backend.get("type") or fallback_backend.get("type", "openai"),
                "model": source_backend.get("model") or config.model or fallback_backend.get("model"),
                "cwd": str(agent_workspace),  # Each agent gets unique workspace
                # Inherit relevant backend settings from first parent
                "enable_mcp_command_line": enable_mcp_command_line,
            }

            # Only include execution mode when command-line MCP execution is enabled.
            if enable_mcp_command_line:
                backend_config["command_line_execution_mode"] = source_backend.get("command_line_execution_mode") or fallback_backend.get("command_line_execution_mode", "local")

            # Handle enable_web_search: orchestrator config > inherit from parent
            # Note: This is set in YAML config, not by agents at runtime
            if orch_config and orch_config.enable_web_search is not None:
                backend_config["enable_web_search"] = orch_config.enable_web_search
            elif "enable_web_search" in fallback_backend:
                backend_config["enable_web_search"] = fallback_backend["enable_web_search"]

            # Inherit Docker settings if using docker mode.
            # Prefer source_backend (explicit child config) over fallback_backend (parent).
            if backend_config.get("command_line_execution_mode") == "docker":
                docker_settings = [
                    "command_line_docker_image",
                    "command_line_docker_network_mode",
                    "command_line_docker_enable_sudo",
                    "command_line_docker_credentials",
                ]
                for setting in docker_settings:
                    if setting in source_backend:
                        backend_config[setting] = source_backend[setting]
                    elif setting in fallback_backend:
                        backend_config[setting] = fallback_backend[setting]

            # Inherit SRT settings if using srt mode (parity with Docker). Without
            # this, a subagent inherits srt MODE but not the parent's network
            # allowlist / read-denies, so commands that worked in the parent (e.g.
            # an install reaching an allowlisted domain) would fail under the child's
            # deny-all default, and parent-protected reads would become readable.
            if backend_config.get("command_line_execution_mode") == "srt":
                srt_settings = [
                    "command_line_srt_network_allowed_domains",
                    "command_line_srt_deny_read",
                    "command_line_srt_allow_unix_sockets",
                ]
                for setting in srt_settings:
                    if setting in source_backend:
                        backend_config[setting] = source_backend[setting]
                    elif setting in fallback_backend:
                        backend_config[setting] = fallback_backend[setting]

            # Inherit code-based tools settings
            code_tools_settings = [
                "enable_code_based_tools",
                "exclude_file_operation_mcps",
                "shared_tools_directory",
                "auto_discover_custom_tools",
                "exclude_custom_tools",
                "direct_mcp_servers",
            ]
            for setting in code_tools_settings:
                if setting in fallback_backend:
                    backend_config[setting] = fallback_backend[setting]

            # Inherit multimodal tool settings so subagents can use generate_media/read_media.
            multimodal_tool_settings = [
                "enable_multimodal_tools",
                "multimodal_config",
                "image_generation_backend",
                "image_generation_model",
                "video_generation_backend",
                "video_generation_model",
                "audio_generation_backend",
                "audio_generation_model",
            ]
            for setting in multimodal_tool_settings:
                if setting in source_backend:
                    backend_config[setting] = source_backend[setting]
                elif setting in fallback_backend:
                    backend_config[setting] = fallback_backend[setting]

            # Add base_url if specified (source or fallback)
            base_url = source_backend.get("base_url") or fallback_backend.get("base_url")
            if base_url:
                backend_config["base_url"] = base_url

            # Copy reasoning config if present (from source or fallback)
            if "reasoning" in source_backend:
                backend_config["reasoning"] = source_backend["reasoning"]
            elif "reasoning" in fallback_backend and "type" not in source_backend:
                backend_config["reasoning"] = fallback_backend["reasoning"]

            # Preserve additional backend options from explicit common/local entries
            # and synthesized parent-local inheritance unless explicitly overridden above.
            if source_origin != "legacy":
                passthrough_exclusions = {
                    "cwd",
                    "type",
                    "model",
                    "enable_mcp_command_line",
                    "command_line_execution_mode",
                    # Runtime-injected keys that must not leak from parent
                    # to child configs (they are re-computed by the CLI for
                    # each subagent run).  `agent_id` in particular causes
                    # "got multiple values for keyword argument 'agent_id'"
                    # in create_backend() when it is also passed explicitly.
                    "agent_id",
                    "instance_id",
                    "filesystem_session_id",
                    "session_storage_base",
                    "agent_temporary_workspace",
                }
                for setting, value in source_backend.items():
                    if setting in passthrough_exclusions:
                        continue
                    backend_config.setdefault(setting, value)

            # Inject evaluator persona as system_prompt if available.
            evaluator_personas = (config.metadata or {}).get("evaluator_personas")
            if evaluator_personas and isinstance(evaluator_personas, list) and i < len(evaluator_personas):
                persona = evaluator_personas[i]
                persona_label = str(persona.get("label", "")).strip()
                persona_instructions = str(persona.get("instructions", "")).strip()
                if persona_label and persona_instructions:
                    backend_config["system_prompt"] = (
                        f"## Evaluator Persona: {persona_label}\n\n" f"{persona_instructions}\n\n" "Apply this evaluation lens consistently across " "all criteria and candidate answers."
                    )

            agent_config = {
                "id": agent_id,
                "backend": backend_config,
            }

            agents.append(agent_config)

        # Build coordination config - disable subagents to prevent nesting
        coord_settings = orch_config.coordination.copy() if orch_config and orch_config.coordination else {}
        explicit_coord_settings = set(coord_settings.keys())
        subagent_type = str((config.metadata or {}).get("subagent_type") or "").strip().lower()
        is_round_evaluator = subagent_type == "round_evaluator"
        checklist_top_level_settings = (
            "voting_sensitivity",
            "voting_threshold",
            "checklist_require_gap_report",
            "gap_report_mode",
            "max_checklist_calls_per_round",
            "checklist_first_answer",
        )
        if is_round_evaluator and not refine:
            # Quick round_evaluator runs are critique-only and should not expose
            # checklist-gated child orchestration inside the subagent run.
            for setting in (
                "voting_sensitivity",
                "voting_threshold",
                "checklist_require_gap_report",
                "gap_report_mode",
                "max_checklist_calls_per_round",
                "checklist_first_answer",
            ):
                coord_settings.pop(setting, None)
                explicit_coord_settings.discard(setting)
        coord_settings["enable_subagents"] = False  # CRITICAL: prevent nesting
        # Subagents should not broadcast to humans (e.g., ask_others with broadcast=human)
        if coord_settings.get("broadcast") == "human":
            coord_settings["broadcast"] = False

        # Inherit coordination settings from parent if not explicitly set in subagent config.
        # This allows subagents to use parent-enabled planning and skills behavior by default.
        coordination_settings_to_inherit = [
            "enable_agent_task_planning",
            "task_planning_filesystem_mode",
            "use_skills",
            "massgen_skills",
            "skills_directory",
            "load_previous_session_skills",
            "enabled_skill_names",
        ]
        for setting in coordination_settings_to_inherit:
            if setting not in coord_settings and setting in self._parent_coordination_config:
                coord_settings[setting] = self._parent_coordination_config[setting]
                logger.info(
                    f"[SubagentManager] Inherited {setting}={self._parent_coordination_config[setting]} from parent",
                )

        # Subagents always use final_only learning capture: capturing per-round learnings
        # is wasteful overhead for short-lived tasks.
        coord_settings["learning_capture_mode"] = "final_only"
        # Keep subagents read-focused in final_only mode even when quick-mode sets
        # skip_final_presentation=True (no evolving-skill/memory capture in rounds).
        coord_settings["disable_final_only_round_capture_fallback"] = True

        orchestrator_config = {
            "snapshot_storage": str(workspace / "snapshots"),
            "agent_temporary_workspace": str(workspace / "temp"),
            "coordination": coord_settings,
        }

        # Promote top-level orchestrator voting settings if callers provided
        # them under coordination for convenience/backward compatibility.
        # The main config parser reads these fields at orchestrator level.
        for setting in (
            "voting_sensitivity",
            "voting_threshold",
            "checklist_require_gap_report",
            "gap_report_mode",
            "max_checklist_calls_per_round",
            "checklist_first_answer",
        ):
            if setting in explicit_coord_settings and setting in coord_settings:
                orchestrator_config[setting] = coord_settings.pop(setting)

        if refine:
            for setting in checklist_top_level_settings:
                if setting in orchestrator_config:
                    continue
                if setting not in self._parent_coordination_config:
                    continue
                value = self._parent_coordination_config[setting]
                if setting == "voting_threshold" and value is None:
                    continue
                orchestrator_config[setting] = value

        effective_child_voting_sensitivity = orchestrator_config.get("voting_sensitivity")
        if (
            is_round_evaluator
            and refine
            and effective_child_voting_sensitivity == "checklist_gated"
            and not coord_settings.get("checklist_criteria_inline")
            and "checklist_criteria_preset" not in coord_settings
        ):
            coord_settings["checklist_criteria_preset"] = "round_evaluator"

        # Apply max_new_answers limit to prevent runaway iterations
        # This must be at the top level of orchestrator config (not inside coordination)
        if orch_config and orch_config.max_new_answers:
            orchestrator_config["max_new_answers_per_agent"] = orch_config.max_new_answers
        if orch_config and orch_config.final_answer_strategy is not None:
            orchestrator_config["final_answer_strategy"] = orch_config.final_answer_strategy
        # Propagate ensemble defaults (disable_injection, defer_voting) only
        # for non-refine runs.  refine=True means collaborative iteration where
        # agents should see each other's work — ensemble isolation would break that.
        if orch_config and not refine:
            orchestrator_config.setdefault("disable_injection", orch_config.disable_injection)
            orchestrator_config.setdefault("defer_voting_until_all_answered", orch_config.defer_voting_until_all_answered)

        # Apply refinement overrides for quick mode (matches TUI behavior)
        if not refine:
            orchestrator_config["max_new_answers_per_agent"] = 1
            if num_agents == 1:
                orchestrator_config["skip_final_presentation"] = True
                orchestrator_config["skip_voting"] = True
            else:
                orchestrator_config["disable_injection"] = True
                orchestrator_config["defer_voting_until_all_answered"] = True
                if "final_answer_strategy" not in orchestrator_config:
                    orchestrator_config["final_answer_strategy"] = "synthesize"
                # round_evaluator: optionally skip synthesis so the parent
                # reads all raw critiques directly (no lossy merge step).
                skip_synthesis = self._parent_coordination_config.get(
                    "round_evaluator_skip_synthesis",
                    False,
                )
                if is_round_evaluator and skip_synthesis:
                    orchestrator_config["skip_final_presentation"] = True
                    orchestrator_config["skip_voting"] = True
                elif is_round_evaluator:
                    # Synthesize mode: presenter merges all critiques
                    orchestrator_config["final_answer_strategy"] = "synthesize"
                    orchestrator_config["skip_final_presentation"] = False
                else:
                    # Non-round-evaluator multi-agent quick subagents skip presentation
                    orchestrator_config["skip_final_presentation"] = True

        # Round evaluator defaults that apply regardless of refine mode.
        # When refine=True the block above is skipped, but round_evaluator
        # still needs synthesize strategy and skip_synthesis handling.
        if is_round_evaluator and refine:
            if "final_answer_strategy" not in orchestrator_config:
                orchestrator_config["final_answer_strategy"] = "synthesize"
            skip_synthesis = self._parent_coordination_config.get(
                "round_evaluator_skip_synthesis",
                False,
            )
            if skip_synthesis:
                orchestrator_config["skip_final_presentation"] = True
                orchestrator_config["skip_voting"] = True
            elif "skip_final_presentation" not in orchestrator_config:
                orchestrator_config["skip_final_presentation"] = False

        # Merge context paths: parent context paths + task-specific context paths
        # Parent context paths are always read-only (subagents can read the codebase)
        # Task-specific context paths from context_files are also read-only
        merged_context_paths: list[dict[str, str]] = []

        # Determine which parent workspace path to exclude when include_parent_workspace=False
        parent_ws_str = str(self.parent_workspace.resolve())

        # Add parent context paths (always read-only for subagents).
        # When include_parent_workspace=False, skip the parent workspace entry so the
        # subagent runs in full isolation without access to the parent's files.
        if self._parent_context_paths:
            for parent_path in self._parent_context_paths:
                path_str = parent_path.get("path", "")
                if not config.include_parent_workspace and path_str == parent_ws_str:
                    continue
                merged_context_paths.append(
                    {
                        "path": path_str,
                        "permission": "read",  # Always read for subagents
                    },
                )
            logger.info(
                f"[SubagentManager] Inherited {len(self._parent_context_paths)} context paths from parent",
            )

        # Add task-specific context paths (from context_files parameter)
        if context_paths:
            existing_paths = {p.get("path") for p in merged_context_paths}
            for ctx_path in context_paths:
                if ctx_path.get("path") not in existing_paths:
                    merged_context_paths.append(ctx_path)
                    existing_paths.add(ctx_path.get("path"))

        if is_round_evaluator and self._agent_temporary_workspace:
            temp_root = str(self._agent_temporary_workspace.resolve())
            existing_paths = {p.get("path") for p in merged_context_paths}
            if temp_root not in existing_paths:
                merged_context_paths.append({"path": temp_root, "permission": "read"})

        if merged_context_paths:
            orchestrator_config["context_paths"] = merged_context_paths

        yaml_config = {
            "agents": agents,
            "orchestrator": orchestrator_config,
        }

        # If specialized subagent type has skills, enable skills for this subagent
        skills_list = config.metadata.get("skills")
        if skills_list:
            coord_settings["use_skills"] = True
            coord_settings["massgen_skills"] = skills_list
            coord_settings["enabled_skill_names"] = skills_list
            logger.info(
                f"[SubagentManager] Enabling skills for subagent {config.id}: {skills_list}",
            )

        # Configure per-round timeouts for subagents, with parent inheritance
        subagent_round_timeouts = self._parent_coordination_config.get("subagent_round_timeouts") or {}
        parent_round_timeouts = self._parent_coordination_config.get("parent_round_timeouts") or {}
        effective_round_timeouts = {}
        if parent_round_timeouts:
            effective_round_timeouts.update(parent_round_timeouts)
        for key, value in subagent_round_timeouts.items():
            if value is not None:
                effective_round_timeouts[key] = value
        if effective_round_timeouts:
            timeout_settings = {}
            for key in (
                "initial_round_timeout_seconds",
                "subsequent_round_timeout_seconds",
                "round_timeout_grace_seconds",
            ):
                if key in effective_round_timeouts and effective_round_timeouts[key] is not None:
                    timeout_settings[key] = effective_round_timeouts[key]
            if timeout_settings:
                yaml_config["timeout_settings"] = timeout_settings

        return yaml_config

    def _parse_subprocess_status(self, workspace: Path) -> tuple[dict[str, Any], str | None, str | None]:
        """
        Parse token usage, log path, and session ID from the subprocess.

        Session ID is read from the sentinel file ({workspace}/.massgen/.session_id)
        which is written at subprocess startup. The status.json meta.session_id field
        is NOT used because it stores "attempt_1" (the log_dir.name), not the real
        session identifier.

        Args:
            workspace: Workspace path where status.json might be

        Returns:
            Tuple of (token_usage dict, subprocess_log_dir path or None, session_id or None)
        """
        # Read session_id from sentinel file (written at subprocess startup)
        sentinel_file = workspace / ".massgen" / ".session_id"
        session_id = None
        if sentinel_file.exists():
            try:
                session_id = sentinel_file.read_text().strip()
            except OSError:
                pass

        # Look for status.json in the subprocess's .massgen logs for token usage
        massgen_logs = workspace / ".massgen" / "massgen_logs"
        if not massgen_logs.exists():
            return {}, None, session_id

        # Find most recent log directory
        for log_dir in sorted(massgen_logs.glob("log_*"), reverse=True):
            status_file = log_dir / "turn_1" / "attempt_1" / "status.json"
            if status_file.exists():
                try:
                    data = json.loads(status_file.read_text())
                    costs = data.get("costs", {})
                    token_usage = {
                        "input_tokens": costs.get("total_input_tokens", 0),
                        "output_tokens": costs.get("total_output_tokens", 0),
                        "estimated_cost": costs.get("total_estimated_cost", 0.0),
                    }
                    return token_usage, str(log_dir / "turn_1" / "attempt_1"), session_id
                except (json.JSONDecodeError, OSError, KeyError, TypeError) as e:
                    logger.warning(
                        f"[SubagentManager] Failed to parse {status_file}: {e}",
                    )
        return {}, None, session_id

    def _session_has_saved_turns(self, workspace: Path, session_id: str | None) -> bool:
        """Return True when workspace-local session storage has at least one saved turn."""
        normalized_session_id = str(session_id or "").strip()
        if not normalized_session_id:
            return False

        session_dir = workspace / ".massgen" / "sessions" / normalized_session_id
        if not session_dir.exists() or not session_dir.is_dir():
            return False

        try:
            for item in session_dir.iterdir():
                if item.is_dir() and item.name.startswith("turn_"):
                    return True
        except OSError as e:
            logger.debug(
                f"[SubagentManager] OSError checking session turns for {session_dir}: {e}",
            )
            return False

        return False

    def _write_subprocess_log_reference(
        self,
        subagent_id: str,
        subprocess_log_dir: str | None,
        error: str | None = None,
    ) -> None:
        """
        Write a reference file pointing to the subprocess's log directory
        and copy the full subprocess logs to the main log directory.

        This ensures logs are preserved even if the agent cleans up subagent
        workspaces during execution.

        Args:
            subagent_id: Subagent identifier
            subprocess_log_dir: Path to subprocess's log directory
            error: Optional error message if subprocess failed
        """
        log_dir = self._get_subagent_log_dir(subagent_id)
        if not log_dir:
            return

        reference_file = log_dir / "subprocess_logs.json"
        reference_data = {
            "subagent_id": subagent_id,
            "subprocess_log_dir": subprocess_log_dir,
            "timestamp": datetime.now().isoformat(),
        }
        if error:
            reference_data["error"] = error

        reference_file.write_text(json.dumps(reference_data, indent=2))

        # Copy the full subprocess logs to the main log directory
        # This preserves logs even if the agent deletes subagents/ during cleanup
        if subprocess_log_dir:
            subprocess_log_path = Path(subprocess_log_dir)
            if subprocess_log_path.exists() and subprocess_log_path.is_dir():
                dest_logs_dir = log_dir / "full_logs"
                try:
                    if dest_logs_dir.exists():
                        shutil.rmtree(dest_logs_dir)
                    # Copy with symlinks=True to handle any symlinks gracefully
                    shutil.copytree(
                        subprocess_log_path,
                        dest_logs_dir,
                        symlinks=True,
                        ignore_dangling_symlinks=True,
                    )
                    logger.info(f"[SubagentManager] Copied subprocess logs for {subagent_id} to {dest_logs_dir}")
                except Exception as e:
                    logger.warning(f"[SubagentManager] Failed to copy subprocess logs for {subagent_id}: {e}")

        # Also copy the subagent workspace (config, generated files)
        # This preserves the subagent's working directory including its config
        subagent_workspace = self.subagents_base / subagent_id / "workspace"
        if subagent_workspace.exists() and subagent_workspace.is_dir():
            dest_workspace_dir = log_dir / "workspace"
            try:
                if dest_workspace_dir.exists():
                    shutil.rmtree(dest_workspace_dir)
                # Copy workspace, skipping symlinks at top level but preserving content
                dest_workspace_dir.mkdir(parents=True, exist_ok=True)
                for item in subagent_workspace.iterdir():
                    if item.is_symlink():
                        continue  # Skip symlinks (shared_tools, etc.)
                    dest_item = dest_workspace_dir / item.name
                    if item.is_file():
                        shutil.copy2(item, dest_item)
                    elif item.is_dir():
                        # Skip .massgen logs (already copied above) and large dirs
                        if item.name in (".massgen", "node_modules", ".pnpm-store", "__pycache__"):
                            continue
                        shutil.copytree(
                            item,
                            dest_item,
                            symlinks=True,
                            ignore_dangling_symlinks=True,
                        )
                logger.info(f"[SubagentManager] Copied subagent workspace for {subagent_id} to {dest_workspace_dir}")
            except Exception as e:
                logger.warning(f"[SubagentManager] Failed to copy subagent workspace for {subagent_id}: {e}")

        # Synthesize final/ snapshot if the subprocess was cancelled before
        # its internal orchestrator could run finalization.
        dest_logs_dir = log_dir / "full_logs"
        if dest_logs_dir.exists():
            self._synthesize_final_snapshot(dest_logs_dir)

    def _synthesize_final_snapshot(self, full_logs: Path) -> None:
        """Synthesize a ``final/`` directory from per-round answer dirs.

        When a subagent is cancelled externally, its internal orchestrator
        never runs finalization so ``final/<agent_id>/workspace/`` is never
        created.  This method reconstructs it from the per-round answer
        directories that *do* exist in ``full_logs/<agent_id>/<timestamp>/``.

        Selection: winner (from status.json) > most recent answer by timestamp.
        """
        if (full_logs / "final").exists():
            return  # Already finalized — nothing to do

        # Read status.json for winner/historical_workspaces
        status: dict = {}
        status_file = full_logs / "status.json"
        if status_file.exists():
            try:
                status = json.loads(status_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass

        winner = status.get("winner")

        # Build a map of agent_id -> list of (timestamp, workspace_path)
        # from directory structure: full_logs/<agent_id>/<timestamp>/workspace/
        _skip_dirs = {
            "final",
            "agent_outputs",
            "planning_injection",
            "shared_tools",
            "snapshots",
        }
        agent_answers: dict[str, list[tuple[str, Path]]] = {}
        for item in full_logs.iterdir():
            if not item.is_dir() or item.name.startswith(".") or item.name in _skip_dirs:
                continue
            # Check if this looks like an agent dir (has timestamped subdirs)
            for ts_dir in item.iterdir():
                if ts_dir.is_dir() and (ts_dir / "workspace").is_dir():
                    agent_answers.setdefault(item.name, []).append(
                        (ts_dir.name, ts_dir / "workspace"),
                    )

        if not agent_answers:
            return

        # Select the best agent
        selected_agent = None
        if winner and winner in agent_answers:
            selected_agent = winner
        else:
            # Pick agent with the most recent timestamp across all answers
            best_ts = ""
            for agent_id, answers in agent_answers.items():
                latest = max(answers, key=lambda x: x[0])
                if latest[0] > best_ts:
                    best_ts = latest[0]
                    selected_agent = agent_id

        if not selected_agent:
            return

        # Get the most recent answer dir for the selected agent
        answers = sorted(agent_answers[selected_agent], key=lambda x: x[0], reverse=True)
        latest_workspace = answers[0][1]

        # Create final/<agent_id>/workspace/ by copying
        final_ws = full_logs / "final" / selected_agent / "workspace"
        try:
            final_ws.mkdir(parents=True, exist_ok=True)
            for src_item in latest_workspace.iterdir():
                if src_item.is_symlink():
                    continue
                dest = final_ws / src_item.name
                if src_item.is_file():
                    shutil.copy2(src_item, dest)
                elif src_item.is_dir():
                    shutil.copytree(
                        src_item,
                        dest,
                        symlinks=True,
                        ignore_dangling_symlinks=True,
                    )
            logger.info(
                f"[SubagentManager] Synthesized final snapshot for " f"{selected_agent} from {latest_workspace}",
            )
        except Exception as e:
            logger.warning(
                f"[SubagentManager] Failed to synthesize final snapshot: {e}",
            )

    async def spawn_subagent(
        self,
        task: str,
        subagent_id: str | None = None,
        model: str | None = None,
        timeout_seconds: int | None = None,
        context_files: list[str] | None = None,
        context_paths: list[str] | None = None,
        include_parent_workspace: bool = True,
        system_prompt: str | None = None,
        refine: bool = True,
        skills: list[str] | None = None,
        subagent_type: str | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> SubagentResult:
        """
        Spawn a single subagent to work on a task.

        Context is loaded from CONTEXT.md in the workspace (required).

        Args:
            task: The task for the subagent
            subagent_id: Optional custom ID
            model: Optional model override
            timeout_seconds: Optional timeout (uses default if not specified)
            context_files: Optional files to copy to subagent workspace
            context_paths: Extra read-only paths (e.g., peer workspace paths)
            include_parent_workspace: Mount parent workspace read-only (default True)
            system_prompt: Optional custom system prompt
            refine: If True (default), allow multi-round coordination and refinement.
                    If False, return first answer without iteration (faster).
            skills: Optional list of skill names to pre-load for the subagent
            extra_metadata: Optional extra metadata to merge into the subagent config
                (e.g., evaluator_personas for round evaluator spawns)

        Returns:
            SubagentResult with execution outcome
        """
        # Create config with clamped timeout
        clamped_timeout = self._clamp_timeout(timeout_seconds)
        metadata = {"refine": refine}
        if skills:
            metadata["skills"] = skills
        if subagent_type:
            metadata["subagent_type"] = subagent_type
        if extra_metadata:
            metadata.update(extra_metadata)
        config = SubagentConfig.create(
            task=task,
            parent_agent_id=self.parent_agent_id,
            subagent_id=subagent_id,
            model=model,
            timeout_seconds=clamped_timeout,
            context_files=context_files or [],
            context_paths=context_paths or [],
            include_parent_workspace=include_parent_workspace,
            system_prompt=system_prompt,
            metadata=metadata,
        )

        logger.info(f"[SubagentManager] Spawning subagent {config.id} for task: {task[:100]}...")

        # Log subagent spawn event for structured logging
        log_subagent_spawn(
            subagent_id=config.id,
            parent_agent_id=self.parent_agent_id,
            task=task,
            model=config.model,
            timeout_seconds=config.timeout_seconds,
            context_files=config.context_files,
            execution_mode="foreground",
        )

        # Create workspace
        workspace = self._create_workspace(config.id)

        # Copy context files (always called to auto-copy CONTEXT.md even if no explicit context_files)
        self._copy_context_files(config.id, config.context_files or [], workspace)

        # Verify CONTEXT.md exists (required for subagents)
        context_md = workspace / "CONTEXT.md"
        if not context_md.exists():
            error_msg = "CONTEXT.md not found in workspace. " "Before spawning subagents, create a CONTEXT.md file with task context. " "This helps subagents understand what they're working on."
            logger.error(f"[SubagentManager] {error_msg}")
            return SubagentResult.create_error(
                subagent_id=config.id,
                error=error_msg,
                workspace_path=str(workspace),
            )

        # Track state
        state = SubagentState(
            config=config,
            status="running",
            workspace_path=str(workspace),
            started_at=datetime.now(),
        )
        self._subagents[config.id] = state

        # Initialize conversation logging (status comes from full_logs/status.json)
        self._append_conversation(config.id, "user", task)

        # Execute with semaphore and timeout, wrapped in tracing span
        with trace_subagent_execution(
            subagent_id=config.id,
            parent_agent_id=self.parent_agent_id,
            task=task,
            model=config.model,
            timeout_seconds=config.timeout_seconds,
        ) as span:
            async with self._semaphore:
                try:
                    result = await asyncio.wait_for(
                        self._execute_subagent(config, workspace),
                        timeout=config.timeout_seconds,
                    )
                except TimeoutError:
                    # Attempt to recover completed work from workspace
                    log_dir = self._get_subagent_log_dir(config.id)
                    # Load context warning for the result
                    from massgen.context.task_context import (
                        load_task_context_with_warning,
                    )

                    _, context_warning = load_task_context_with_warning(str(workspace))
                    result = self._create_timeout_result_with_recovery(
                        subagent_id=config.id,
                        workspace=workspace,
                        timeout_seconds=config.timeout_seconds,
                        log_path=str(log_dir) if log_dir else None,
                        warning=context_warning,
                    )

            # Set span attributes based on result
            span.set_attribute("subagent.success", result.success)
            span.set_attribute("subagent.status", result.status)
            span.set_attribute("subagent.execution_time_seconds", result.execution_time_seconds)

        # Update state - use result.status directly for recovered states
        # Status can be: completed, completed_but_timeout, partial, timeout, error
        if result.success:
            state.status = "completed"
        elif result.status in ("timeout", "completed_but_timeout", "partial"):
            state.status = result.status
        else:
            state.status = "failed"
        state.result = result

        # Log conversation on success
        if result.success and result.answer:
            self._append_conversation(config.id, "assistant", result.answer)

        logger.info(
            f"[SubagentManager] Subagent {config.id} finished with status: {result.status}, " f"time: {result.execution_time_seconds:.2f}s",
        )

        # Log subagent completion event for structured logging
        log_subagent_complete(
            subagent_id=config.id,
            parent_agent_id=self.parent_agent_id,
            status=result.status,
            execution_time_seconds=result.execution_time_seconds,
            success=result.success,
            token_usage=result.token_usage,
            error_message=result.error,
            answer_preview=result.answer[:200] if result.answer else None,
        )

        # Save to registry for continuation support
        session_id = self._subagent_sessions.get(config.id)
        if session_id:
            self._save_subagent_to_registry(config.id, session_id, config, result)

        return result

    async def spawn_parallel(
        self,
        tasks: list[dict[str, Any]],
        timeout_seconds: int | None = None,
        refine: bool = True,
    ) -> list[SubagentResult]:
        """
        Spawn multiple subagents to run in parallel.

        Context is loaded from CONTEXT.md in the workspace (required).

        Args:
            tasks: List of task configurations, each with:
                   - task (required): Task description
                   - subagent_id (optional): Custom ID
                   - model (optional): Model override
                   - context_files (optional): Files to copy
            timeout_seconds: Optional timeout for all subagents
            refine: If True (default), allow multi-round coordination and refinement.
                    If False, return first answer without iteration (faster).

        Returns:
            List of SubagentResults in same order as input tasks
        """
        logger.info(f"[SubagentManager] Spawning {len(tasks)} subagents in parallel")

        # Create coroutines for each task
        coroutines = []
        for task_config in tasks:
            coro = self.spawn_subagent(
                task=task_config["task"],
                subagent_id=task_config.get("subagent_id"),
                model=task_config.get("model"),
                timeout_seconds=timeout_seconds or task_config.get("timeout_seconds"),
                context_files=task_config.get("context_files"),
                context_paths=task_config.get("context_paths"),
                include_parent_workspace=task_config.get("include_parent_workspace", True),
                system_prompt=task_config.get("system_prompt"),
                refine=refine,
                skills=task_config.get("skills"),
                subagent_type=task_config.get("subagent_type"),
                extra_metadata=task_config.get("metadata"),
            )
            coroutines.append(coro)

        # Execute all in parallel (semaphore limits concurrency)
        results = await asyncio.gather(*coroutines, return_exceptions=True)

        # Convert exceptions to error results
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                task_id = tasks[i].get("subagent_id", f"sub_{i}")
                final_results.append(
                    SubagentResult.create_error(
                        subagent_id=task_id,
                        error=str(result),
                    ),
                )
            else:
                final_results.append(result)

        return final_results

    def spawn_subagent_background(
        self,
        task: str,
        subagent_id: str | None = None,
        model: str | None = None,
        timeout_seconds: int | None = None,
        context_files: list[str] | None = None,
        context_paths: list[str] | None = None,
        include_parent_workspace: bool = True,
        system_prompt: str | None = None,
        refine: bool = True,
        skills: list[str] | None = None,
        subagent_type: str | None = None,
    ) -> dict[str, Any]:
        """
        Spawn a subagent in the background (non-blocking).

        Returns immediately with subagent info. When the subagent completes,
        registered completion callbacks are invoked to notify about results.
        Poll via list_subagents() or generic background lifecycle tools to check progress.

        Args:
            task: The task for the subagent
            subagent_id: Optional custom ID
            model: Optional model override
            timeout_seconds: Optional timeout (uses default if not specified)
            context_files: Optional files to copy to subagent workspace
            context_paths: Extra read-only paths (e.g., peer workspace paths)
            include_parent_workspace: Mount parent workspace read-only (default True)
            system_prompt: Optional custom system prompt
            skills: Optional list of skill names to pre-load for the subagent

        Returns:
            Dictionary with subagent_id and status_file path
        """
        # Create config with clamped timeout
        clamped_timeout = self._clamp_timeout(timeout_seconds)
        metadata = {"refine": refine}
        if skills:
            metadata["skills"] = skills
        if subagent_type:
            metadata["subagent_type"] = subagent_type
        config = SubagentConfig.create(
            task=task,
            parent_agent_id=self.parent_agent_id,
            subagent_id=subagent_id,
            model=model,
            timeout_seconds=clamped_timeout,
            context_files=context_files or [],
            context_paths=context_paths or [],
            include_parent_workspace=include_parent_workspace,
            system_prompt=system_prompt,
            metadata=metadata,
        )

        logger.info(f"[SubagentManager] Spawning background subagent {config.id} for task: {task[:100]}...")

        # Log subagent spawn event for structured logging
        log_subagent_spawn(
            subagent_id=config.id,
            parent_agent_id=self.parent_agent_id,
            task=task,
            model=config.model,
            timeout_seconds=config.timeout_seconds,
            context_files=config.context_files,
            execution_mode="background",
        )

        # Create workspace
        workspace = self._create_workspace(config.id)

        # Copy context files (always called to auto-copy CONTEXT.md even if no explicit context_files)
        self._copy_context_files(config.id, config.context_files or [], workspace)

        # Verify CONTEXT.md exists (required for subagents)
        context_md = workspace / "CONTEXT.md"
        if not context_md.exists():
            error_msg = "CONTEXT.md not found in workspace. " "Before spawning subagents, create a CONTEXT.md file with task context. " "This helps subagents understand what they're working on."
            logger.error(f"[SubagentManager] {error_msg}")
            # For background mode, we can't return SubagentResult directly
            # Store the error state and return info dict
            state = SubagentState(
                config=config,
                status="error",
                workspace_path=str(workspace),
                started_at=datetime.now(),
            )
            self._subagents[config.id] = state
            # Return error info
            return {
                "subagent_id": config.id,
                "status": "error",
                "workspace": str(workspace),
                "error": error_msg,
                **({"subagent_type": subagent_type} if subagent_type else {}),
            }

        # Track state
        state = SubagentState(
            config=config,
            status="running",
            workspace_path=str(workspace),
            started_at=datetime.now(),
        )
        self._subagents[config.id] = state

        # Initialize conversation logging (status comes from full_logs/status.json)
        self._append_conversation(config.id, "user", task)

        # Create background task
        async def _run_background():
            async with self._semaphore:
                try:
                    result = await asyncio.wait_for(
                        self._execute_subagent(config, workspace),
                        timeout=config.timeout_seconds,
                    )
                except TimeoutError:
                    # Attempt to recover completed work from workspace
                    log_dir = self._get_subagent_log_dir(config.id)
                    # Load context warning for the result
                    from massgen.context.task_context import (
                        load_task_context_with_warning,
                    )

                    _, context_warning = load_task_context_with_warning(str(workspace))
                    result = self._create_timeout_result_with_recovery(
                        subagent_id=config.id,
                        workspace=workspace,
                        timeout_seconds=config.timeout_seconds,
                        log_path=str(log_dir) if log_dir else None,
                        warning=context_warning,
                    )
                except asyncio.CancelledError:
                    # Task was cancelled (e.g., via cancel_subagent).
                    # Fall through to the cancellation-preservation logic below.
                    result = SubagentResult.create_error(
                        subagent_id=config.id,
                        error="Subagent cancelled",
                        workspace_path=str(workspace),
                    )
                except Exception as e:
                    # Load context warning for the result
                    from massgen.context.task_context import (
                        load_task_context_with_warning,
                    )

                    _, context_warning = load_task_context_with_warning(str(workspace))
                    result = SubagentResult.create_error(
                        subagent_id=config.id,
                        error=str(e),
                        workspace_path=str(workspace),
                        warning=context_warning,
                    )

            # Preserve explicit cancellation if cancel_subagent() already marked the
            # subagent terminal while this background task was still unwinding.
            cancelled_statuses = {"cancelled", "canceled"}
            if str(state.status).lower() in cancelled_statuses:
                if state.result is None:
                    elapsed = 0.0
                    if state.started_at is not None:
                        elapsed = max(
                            0.0,
                            (datetime.now() - state.started_at).total_seconds(),
                        )
                    state.result = SubagentResult.create_error(
                        subagent_id=config.id,
                        error="Subagent cancelled",
                        workspace_path=str(workspace),
                        execution_time_seconds=elapsed,
                    )
                result = state.result
            else:
                # Update state - use result.status directly for recovered states
                # Status can be: completed, completed_but_timeout, partial, timeout, error
                if result.success:
                    state.status = "completed"
                elif result.status in ("timeout", "completed_but_timeout", "partial"):
                    state.status = result.status
                else:
                    state.status = "failed"
                state.result = result

            completion_status = "cancelled" if str(state.status).lower() in cancelled_statuses else result.status

            # Invoke registered completion callbacks to notify about background completion
            self._invoke_completion_callbacks(config.id, result)

            # Log conversation on success
            if result.success and result.answer:
                self._append_conversation(config.id, "assistant", result.answer)

            logger.info(
                f"[SubagentManager] Background subagent {config.id} finished with status: {completion_status}, " f"time: {result.execution_time_seconds:.2f}s",
            )

            # Log subagent completion event for structured logging
            log_subagent_complete(
                subagent_id=config.id,
                parent_agent_id=self.parent_agent_id,
                status=completion_status,
                execution_time_seconds=result.execution_time_seconds,
                success=result.success,
                token_usage=result.token_usage,
                error_message=result.error,
                answer_preview=result.answer[:200] if result.answer else None,
            )

            # Save to registry for continuation support
            session_id = self._subagent_sessions.get(config.id)
            if session_id:
                self._save_subagent_to_registry(config.id, session_id, config, result)

            # Clean up task reference
            if config.id in self._background_tasks:
                del self._background_tasks[config.id]

            return result

        # Schedule the background task
        bg_task = asyncio.create_task(_run_background())
        self._background_tasks[config.id] = bg_task

        # Get status file path (now points to full_logs/status.json)
        status_file = None
        if self._subagent_logs_base:
            status_file = str(self._subagent_logs_base / config.id / "full_logs" / "status.json")

        return {
            "subagent_id": config.id,
            "status": "running",
            "workspace": str(workspace),
            "status_file": status_file,
            **({"subagent_type": subagent_type} if subagent_type else {}),
        }

    def remove_immediately_failed_subagent(self, subagent_id: str) -> None:
        """Remove a subagent that failed before doing any real work (pre-flight error).

        Called by the MCP server when a spawn immediately errors (e.g. CONTEXT.md
        missing) so the auto-generated ID slot can be reclaimed for the next spawn.
        Only removes subagents with error status — never touches running/completed ones.
        """
        state = self._subagents.get(subagent_id)
        if state is not None and str(getattr(state, "status", "")).lower() in {"error", "failed"}:
            del self._subagents[subagent_id]
            logger.info(f"[SubagentManager] Freed immediately-failed subagent slot: {subagent_id}")

    def continue_subagent_background(
        self,
        subagent_id: str,
        new_message: str,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Continue a subagent in background mode (non-blocking).

        This schedules ``continue_subagent`` on a background asyncio task and
        returns immediately with running status metadata.

        Args:
            subagent_id: ID of the subagent to continue
            new_message: Continuation message
            timeout_seconds: Optional timeout override

        Returns:
            Dictionary with background status metadata.
        """
        normalized_id = str(subagent_id or "").strip()
        normalized_message = str(new_message or "").strip()

        if not normalized_id:
            return {
                "subagent_id": "",
                "status": "error",
                "error": "Missing required 'subagent_id' parameter",
            }
        if not normalized_message:
            return {
                "subagent_id": normalized_id,
                "status": "error",
                "error": "Missing required 'message' parameter",
            }

        existing_task = self._background_tasks.get(normalized_id)
        if existing_task:
            if existing_task.done():
                self._background_tasks.pop(normalized_id, None)
            else:
                return {
                    "subagent_id": normalized_id,
                    "status": "error",
                    "error": (f"Subagent {normalized_id} is already running in background. " "Use send_message_to_subagent() to steer the active run."),
                }

        state = self._subagents.get(normalized_id)
        if state and state.status in ("running", "pending"):
            return {
                "subagent_id": normalized_id,
                "status": "error",
                "error": (f"Subagent {normalized_id} is currently running. " "Use send_message_to_subagent() for runtime steering."),
            }

        workspace_hint = ""
        if state and state.workspace_path:
            workspace_hint = str(state.workspace_path)

        if not workspace_hint:
            for entry in self.list_subagents():
                if str(entry.get("subagent_id") or "") == normalized_id:
                    workspace_hint = str(entry.get("workspace") or "")
                    break

        if not workspace_hint:
            return {
                "subagent_id": normalized_id,
                "status": "error",
                "error": f"Subagent {normalized_id} not found in any registry.",
            }

        if state is not None:
            state.status = "running"
            state.result = None
            state.started_at = datetime.now()
            state.finished_at = None

        clamped_timeout = self._clamp_timeout(timeout_seconds)

        async def _run_background_continue() -> SubagentResult:
            async with self._semaphore:
                try:
                    result = await self.continue_subagent(
                        subagent_id=normalized_id,
                        new_message=normalized_message,
                        timeout_seconds=clamped_timeout,
                    )
                except asyncio.CancelledError:
                    current_state = self._subagents.get(normalized_id)
                    workspace_path = current_state.workspace_path if current_state and current_state.workspace_path else workspace_hint
                    result = SubagentResult.create_error(
                        subagent_id=normalized_id,
                        error="Subagent cancelled",
                        workspace_path=workspace_path,
                    )
                    if current_state is not None:
                        current_state.status = "cancelled"
                        current_state.result = result
                        current_state.finished_at = datetime.now()
                except Exception as e:
                    logger.opt(exception=True).error(
                        f"[SubagentManager] Background continue failed for {normalized_id}: {e}",
                    )
                    current_state = self._subagents.get(normalized_id)
                    workspace_path = current_state.workspace_path if current_state and current_state.workspace_path else workspace_hint
                    result = SubagentResult.create_error(
                        subagent_id=normalized_id,
                        error=str(e),
                        workspace_path=workspace_path,
                    )
                    if current_state is not None:
                        current_state.status = "failed"
                        current_state.result = result
                        current_state.finished_at = datetime.now()

            self._invoke_completion_callbacks(normalized_id, result)
            self._background_tasks.pop(normalized_id, None)
            return result

        self._background_tasks[normalized_id] = asyncio.create_task(_run_background_continue())

        status_file = None
        if self._subagent_logs_base:
            status_file = str(self._subagent_logs_base / normalized_id / "full_logs" / "status.json")

        return {
            "subagent_id": normalized_id,
            "status": "running",
            "workspace": workspace_hint,
            "status_file": status_file,
        }

    async def _continue_via_context_recovery(
        self,
        subagent_id: str,
        subagent_entry: dict[str, Any],
        new_message: str,
        timeout_seconds: int | None,
        *,
        reuse_subagent_id: bool = False,
    ) -> SubagentResult:
        """Continue a subagent via fresh spawn with execution trace context.

        Fallback for when the subprocess was killed before writing the session_id
        sentinel. Gathers any execution traces from snapshots and starts a new
        subagent with the original task + new message.

        Args:
            subagent_id: Original subagent identifier
            subagent_entry: Registry entry for the cancelled subagent
            new_message: New message to continue with
            timeout_seconds: Optional timeout override
            reuse_subagent_id: If True, continue using the original subagent_id

        Returns:
            SubagentResult from the fresh spawn
        """
        workspace = Path(subagent_entry.get("workspace", ""))
        original_task = subagent_entry.get("task", "")
        context_files: list[str] = []

        # Gather execution traces from snapshots
        snapshots = workspace / "snapshots"
        if snapshots.exists():
            for agent_dir in snapshots.iterdir():
                if not agent_dir.is_dir():
                    continue
                trace = agent_dir / "execution_trace.md"
                if trace.exists():
                    context_files.append(str(trace))

        # Build recovery task with original context and new message
        task = f"{original_task}\n\n{new_message}"
        fresh_id = subagent_id if reuse_subagent_id else f"{subagent_id}_recovery_{int(time.time())}"

        logger.info(
            f"[SubagentManager] Context recovery for {subagent_id} → " f"spawning {fresh_id} with {len(context_files)} trace file(s)",
        )

        return await self.spawn_subagent(
            task=task,
            subagent_id=fresh_id,
            context_files=context_files or None,
            timeout_seconds=timeout_seconds,
        )

    async def continue_subagent(
        self,
        subagent_id: str,
        new_message: str,
        timeout_seconds: int | None = None,
    ) -> SubagentResult:
        """Continue a previously spawned subagent with a new message.

        Uses the existing --session-id mechanism to restore the conversation
        and append the new message. This allows continuing timed-out, failed,
        or even completed subagents for refinement or follow-up questions.

        Args:
            subagent_id: ID of the subagent to continue
            new_message: New message to append to the conversation
            timeout_seconds: Optional timeout override

        Returns:
            SubagentResult with execution outcome
        """
        start_time = time.time()

        # Load registry to find the subagent
        # First check our own registry
        subagent_entry = None
        registry_file = self.subagents_base / "_registry.json"

        if registry_file.exists():
            try:
                registry = json.loads(registry_file.read_text())
                # Registry format: {"subagents": [{"subagent_id": "...", ...}, ...]}
                subagents_list = registry.get("subagents", [])
                for entry in subagents_list:
                    if entry.get("subagent_id") == subagent_id:
                        subagent_entry = entry
                        break
            except json.JSONDecodeError:
                logger.warning("[SubagentManager] Failed to parse own registry file")

        # If not found in our registry and we have temp workspaces, search all agent registries
        if not subagent_entry and self._agent_temporary_workspace and self._agent_temporary_workspace.exists():
            for agent_dir in self._agent_temporary_workspace.iterdir():
                if not agent_dir.is_dir():
                    continue

                agent_registry_file = agent_dir / "subagents" / "_registry.json"
                if not agent_registry_file.exists():
                    continue

                try:
                    agent_registry = json.loads(agent_registry_file.read_text())
                    subagents_list = agent_registry.get("subagents", [])
                    for entry in subagents_list:
                        if entry.get("subagent_id") == subagent_id:
                            subagent_entry = entry
                            registry = agent_registry
                            registry_file = agent_registry_file
                            logger.info(
                                f"[SubagentManager] Found subagent {subagent_id} in agent {agent_dir.name}'s registry",
                            )
                            break
                    if subagent_entry:
                        break
                except json.JSONDecodeError:
                    logger.warning(f"[SubagentManager] Failed to parse registry for agent {agent_dir.name}")

        # If not found in any registry, check in-memory state (cancelled subagents
        # that were saved to registry might not be discoverable if registry write failed)
        if not subagent_entry:
            in_memory = self._subagents.get(subagent_id)
            if in_memory and in_memory.status in ("cancelled", "canceled"):
                subagent_entry = {
                    "subagent_id": subagent_id,
                    "session_id": self._subagent_sessions.get(subagent_id),
                    "task": in_memory.config.task,
                    "workspace": in_memory.workspace_path or "",
                    "continuable_via": "context_recovery",
                }
                # Create a minimal registry structure for _persist_continuation_outcome
                registry = {
                    "parent_agent_id": self.parent_agent_id,
                    "orchestrator_id": self.orchestrator_id,
                    "subagents": [subagent_entry],
                }

        if not subagent_entry:
            return SubagentResult.create_error(
                subagent_id=subagent_id,
                error=f"Subagent {subagent_id} not found in any registry.",
            )

        session_id = subagent_entry.get("session_id")
        continuable_via = subagent_entry.get("continuable_via", "session")
        if not session_id:
            if continuable_via == "context_recovery":
                return await self._continue_via_context_recovery(
                    subagent_id,
                    subagent_entry,
                    new_message,
                    timeout_seconds,
                    reuse_subagent_id=True,
                )
            return SubagentResult.create_error(
                subagent_id=subagent_id,
                error=f"Subagent {subagent_id} has no session_id and no recovery path.",
            )

        # Get the existing workspace from the registry
        workspace = Path(subagent_entry.get("workspace", "")).resolve()
        if not workspace.exists():
            return SubagentResult.create_error(
                subagent_id=subagent_id,
                error=f"Subagent workspace not found: {workspace}",
            )

        # Sentinel recovery can produce a session_id before any turn is flushed.
        # Detect this upfront to avoid noisy session restore failures.
        if not self._session_has_saved_turns(workspace, session_id):
            logger.warning(
                f"[SubagentManager] Session {session_id} for {subagent_id} has no saved turns; " "continuing via context recovery",
            )
            return await self._continue_via_context_recovery(
                subagent_id,
                subagent_entry,
                new_message,
                timeout_seconds,
                reuse_subagent_id=True,
            )

        state = self._subagents.get(subagent_id)
        if state is None:
            resumed_task = str(subagent_entry.get("task") or "")
            resumed_config = SubagentConfig(
                id=subagent_id,
                task=resumed_task,
                parent_agent_id=self.parent_agent_id,
                timeout_seconds=self._clamp_timeout(timeout_seconds),
            )
            state = SubagentState(
                config=resumed_config,
                status="running",
                workspace_path=str(workspace),
                started_at=datetime.now(),
                finished_at=None,
                result=None,
            )
            self._subagents[subagent_id] = state
        else:
            state.status = "running"
            state.workspace_path = str(workspace)
            state.started_at = datetime.now()
            state.finished_at = None
            state.result = None

        def _state_status_from_result(result: SubagentResult) -> str:
            if result.success:
                return "completed"
            if result.status in ("timeout", "completed_but_timeout", "partial"):
                return result.status
            return "failed"

        def _persist_continuation_outcome(
            result: SubagentResult,
            *,
            resumed_session_id: str | None = None,
        ) -> None:
            state.status = _state_status_from_result(result)
            state.result = result
            state.finished_at = datetime.now()

            if resumed_session_id:
                self._subagent_sessions[subagent_id] = resumed_session_id
                subagent_entry["session_id"] = resumed_session_id
            elif subagent_id not in self._subagent_sessions and subagent_entry.get("session_id"):
                self._subagent_sessions[subagent_id] = str(subagent_entry.get("session_id"))

            subagent_entry["status"] = state.status
            subagent_entry["workspace"] = str(workspace)
            subagent_entry["success"] = result.success
            subagent_entry["execution_time_seconds"] = result.execution_time_seconds
            subagent_entry["last_continued_at"] = datetime.now().isoformat()

            try:
                registry_file.write_text(json.dumps(registry, indent=2))
            except Exception as exc:
                logger.warning(
                    f"[SubagentManager] Failed to persist continuation metadata for {subagent_id}: {exc}",
                )

        logger.info(
            f"[SubagentManager] Continuing subagent {subagent_id} with session {session_id}, " f"message: {new_message[:100]}...",
        )

        # Use clamped timeout
        timeout = self._clamp_timeout(timeout_seconds)
        try:
            runtime_mode, runtime_warning = self._resolve_effective_runtime_mode()
        except RuntimeError as e:
            return SubagentResult.create_error(
                subagent_id=subagent_id,
                error=str(e),
                workspace_path=str(workspace),
                execution_time_seconds=time.time() - start_time,
            )

        # Build command to continue the session
        # Use --session-id to restore the conversation, then append new message
        answer_file = workspace / "answer_continued.txt"
        base_cmd = [
            "uv",
            "run",
            "massgen",
            "--session-id",
            session_id,  # Restore existing session
            "--automation",
            "--output-file",
            str(answer_file),
            new_message,  # New message to append
        ]
        if runtime_mode == "isolated" and self._running_inside_container and self._subagent_host_launch_prefix:
            cmd = [*self._subagent_host_launch_prefix, *base_cmd]
        else:
            cmd = base_cmd

        logger.info(
            f"[SubagentManager] Continuing {subagent_id} with runtime_mode={runtime_mode}, " f"containerized_parent={self._running_inside_container}",
        )

        process: asyncio.subprocess.Process | None = None
        try:
            # Use async subprocess for graceful cancellation support
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=SUBPROCESS_STREAM_LIMIT,
                cwd=str(workspace),
                env=self._clean_subprocess_env(),
            )

            # Track the process for potential cancellation
            # Use a continuation-specific ID to avoid conflicts
            continuation_id = f"{subagent_id}_cont_{int(time.time())}"
            self._active_processes[continuation_id] = process

            # Wait with timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except TimeoutError:
                # Kill the process on timeout
                logger.warning(f"[SubagentManager] Continuation of {subagent_id} timed out, terminating...")
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except TimeoutError:
                    process.kill()
                    await process.wait()

                execution_time = time.time() - start_time
                log_dir = self._get_subagent_log_dir(subagent_id)
                timeout_result = SubagentResult.create_error(
                    subagent_id=subagent_id,
                    error=f"Continuation timed out after {timeout}s",
                    workspace_path=str(workspace),
                    execution_time_seconds=execution_time,
                    log_path=str(log_dir) if log_dir else None,
                    warning=runtime_warning,
                )
                _persist_continuation_outcome(timeout_result)
                return timeout_result
            finally:
                # Remove from active processes
                self._active_processes.pop(continuation_id, None)

            if process.returncode == 0:
                # Read answer from the output file
                if answer_file.exists():
                    answer = answer_file.read_text().strip()
                else:
                    # Fallback to stdout if file wasn't created
                    answer = stdout.decode() if stdout else ""

                execution_time = time.time() - start_time

                # Get token usage and log path from subprocess's status.json
                token_usage, subprocess_log_dir, resumed_session_id = self._parse_subprocess_status(workspace)

                # Write reference to subprocess log directory
                self._write_subprocess_log_reference(subagent_id, subprocess_log_dir)

                # Get log directory path for the result
                log_dir = self._get_subagent_log_dir(subagent_id)

                result = SubagentResult.create_success(
                    subagent_id=subagent_id,
                    answer=answer,
                    workspace_path=str(workspace),
                    execution_time_seconds=execution_time,
                    token_usage=token_usage,
                    log_path=str(log_dir) if log_dir else None,
                    warning=runtime_warning,
                )
                _persist_continuation_outcome(result, resumed_session_id=resumed_session_id)
                return result
            else:
                stderr_text = stderr.decode() if stderr else ""
                stdout_text = stdout.decode() if stdout else ""
                error_msg = stderr_text.strip() or stdout_text.strip()[:500] or f"Subprocess exited with code {process.returncode}"

                # Log detailed error information for debugging
                logger.error(
                    f"[SubagentManager] Continuation of {subagent_id} failed with exit code {process.returncode}\n"
                    f"Command: {' '.join(cmd)}\n"
                    f"Working directory: {workspace}\n"
                    f"STDERR: {stderr_text[:1000]}\n"  # First 1000 chars of stderr
                    f"STDOUT: {stdout_text[:500]}",  # First 500 chars of stdout
                )

                # Still try to get log path for debugging
                _, subprocess_log_dir, _ = self._parse_subprocess_status(workspace)
                self._write_subprocess_log_reference(subagent_id, subprocess_log_dir, error=error_msg)

                # Session-based continuation failed — fall back to context recovery
                # using workspace files from the cancelled run
                logger.warning(
                    f"[SubagentManager] Session continuation failed for {subagent_id} " f"(exit code {process.returncode}), falling back to context recovery",
                )
                return await self._continue_via_context_recovery(
                    subagent_id,
                    subagent_entry,
                    new_message,
                    timeout_seconds,
                    reuse_subagent_id=True,
                )

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"[SubagentManager] Error continuing subagent {subagent_id}: {e}")
            error_result = SubagentResult.create_error(
                subagent_id=subagent_id,
                error=str(e),
                workspace_path=str(workspace),
                execution_time_seconds=execution_time,
                warning=runtime_warning,
            )
            _persist_continuation_outcome(error_result)
            return error_result

    def get_subagent_status(self, subagent_id: str) -> dict[str, Any] | None:
        """
        Get the current status of a subagent.

        Reads from full_logs/status.json (written by Orchestrator) and transforms
        the rich status into a simplified view for MCP consumers.

        Args:
            subagent_id: Subagent identifier

        Returns:
            Simplified status dictionary, or None if not found
        """
        # First check in-memory state exists
        state = self._subagents.get(subagent_id)
        if not state:
            return None

        # Try to read from full_logs/status.json (the single source of truth)
        if self._subagent_logs_base:
            status_file = self._subagent_logs_base / subagent_id / "full_logs" / "status.json"
            if status_file.exists():
                try:
                    raw_status = json.loads(status_file.read_text())
                    return self._transform_orchestrator_status(subagent_id, raw_status, state)
                except json.JSONDecodeError:
                    pass

        # Fall back to in-memory state if file doesn't exist yet
        return {
            "subagent_id": subagent_id,
            "status": "pending" if state.status == "running" else state.status,
            "task": state.config.task,
            "workspace": state.workspace_path,
            "started_at": state.started_at.isoformat() if state.started_at else None,
        }

    def get_subagent_display_data(self, subagent_id: str) -> SubagentDisplayData | None:
        """
        Get display data for a subagent (for TUI rendering).

        Returns a SubagentDisplayData object with progress, file count, and
        last log line - optimized for the SubagentCard widget.

        Args:
            subagent_id: Subagent identifier

        Returns:
            SubagentDisplayData if found, None otherwise
        """

        state = self._subagents.get(subagent_id)
        if not state:
            return None

        # Calculate elapsed time and progress.
        # For terminal subagents, freeze elapsed at finished time/result duration.
        elapsed = 0.0
        terminal_statuses = {"completed", "completed_but_timeout", "partial", "failed", "timeout", "cancelled"}
        if state.started_at:
            if state.finished_at is not None:
                elapsed = (state.finished_at - state.started_at).total_seconds()
            elif state.result and state.result.execution_time_seconds is not None and state.status in terminal_statuses:
                elapsed = float(state.result.execution_time_seconds)
            else:
                elapsed = (datetime.now() - state.started_at).total_seconds()
            elapsed = max(0.0, elapsed)
        elif state.result and state.result.execution_time_seconds is not None:
            elapsed = max(0.0, float(state.result.execution_time_seconds))

        timeout = state.config.timeout_seconds
        progress = min(100, int(elapsed / timeout * 100)) if timeout > 0 else 0

        # Determine status
        status = state.status
        if status == "completed_but_timeout":
            status = "timeout"
        elif status == "partial":
            status = "error"

        # Count workspace files
        workspace_file_count = 0
        workspace_path = Path(state.workspace_path) if state.workspace_path else None
        if workspace_path and workspace_path.exists():
            try:
                workspace_file_count = sum(1 for p in workspace_path.rglob("*") if p.is_file())
            except OSError:
                pass

        # Get last log line
        last_log_line = ""
        if self._subagent_logs_base and workspace_path:
            log_path = self._subagent_logs_base / subagent_id / "full_logs" / "massgen.log"
            if log_path.exists():
                try:
                    # Tail last line efficiently
                    with open(log_path, "rb") as f:
                        f.seek(0, 2)  # End of file
                        size = f.tell()
                        if size > 0:
                            # Read last ~500 bytes
                            f.seek(max(0, size - 500))
                            content = f.read().decode("utf-8", errors="replace")
                            lines = content.strip().split("\n")
                            if lines:
                                last_log_line = lines[-1][:100]  # Truncate
                except OSError:
                    pass

        # Get error message if failed
        error = None
        if state.result and state.result.error:
            error = state.result.error

        # Get answer preview if completed
        answer_preview = None
        if state.result and state.result.answer:
            answer_preview = state.result.answer[:200]
            if len(state.result.answer) > 200:
                answer_preview += "..."

        # Get exact path to events.jsonl for TUI
        # Uses SubagentResult.resolve_events_path() for consistent path resolution
        events_jsonl_path = None
        if self._subagent_logs_base:
            subagent_log_dir = self._subagent_logs_base / subagent_id
            events_jsonl_path = SubagentResult.resolve_events_path(subagent_log_dir)

        return SubagentDisplayData(
            id=subagent_id,
            task=state.config.task,
            status=status,
            progress_percent=progress,
            elapsed_seconds=elapsed,
            timeout_seconds=float(timeout),
            workspace_path=state.workspace_path or "",
            workspace_file_count=workspace_file_count,
            last_log_line=last_log_line,
            error=error,
            answer_preview=answer_preview,
            log_path=events_jsonl_path,
            context_paths=list(state.config.context_paths or []),
        )

    def _transform_orchestrator_status(
        self,
        subagent_id: str,
        raw_status: dict[str, Any],
        state: SubagentState,
    ) -> dict[str, Any]:
        """
        Transform Orchestrator's rich status.json into simplified status for MCP.

        Args:
            subagent_id: Subagent identifier
            raw_status: Raw status from full_logs/status.json
            state: In-memory subagent state

        Returns:
            Simplified status dictionary
        """
        # Extract coordination info
        coordination = raw_status.get("coordination", {})
        phase = coordination.get("phase")
        completion_pct = coordination.get("completion_percentage")

        # Derive simple status from phase.
        # Preserve explicit cancellation from in-memory state even when the
        # result payload uses a generic error status.
        if str(state.status).lower() in {"cancelled", "canceled"}:
            derived_status = "cancelled"
        elif state.result:
            derived_status = state.result.status
        elif phase in ("initial_answer", "enforcement", "presentation"):
            derived_status = "running"
        else:
            derived_status = "pending"

        # Extract costs
        costs = raw_status.get("costs", {})
        token_usage = {}
        if costs:
            token_usage = {
                "input_tokens": costs.get("total_input_tokens", 0),
                "output_tokens": costs.get("total_output_tokens", 0),
                "estimated_cost": costs.get("total_estimated_cost", 0.0),
            }

        # Extract elapsed time
        meta = raw_status.get("meta", {})
        elapsed_seconds = meta.get("elapsed_seconds", 0.0)

        result = {
            "subagent_id": subagent_id,
            "status": derived_status,
            "phase": phase,
            "completion_percentage": completion_pct,
            "task": state.config.task,
            "workspace": state.workspace_path,
            "elapsed_seconds": elapsed_seconds,
            "token_usage": token_usage,
        }

        # Add started_at if available
        if state.started_at:
            result["started_at"] = state.started_at.isoformat()

        return result

    async def wait_for_subagent(self, subagent_id: str, timeout: float | None = None) -> SubagentResult | None:
        """
        Wait for a background subagent to complete.

        Args:
            subagent_id: Subagent identifier
            timeout: Optional timeout in seconds

        Returns:
            SubagentResult if completed, None if not found or timeout
        """
        task = self._background_tasks.get(subagent_id)
        if not task:
            # Check if already completed
            state = self._subagents.get(subagent_id)
            if state and state.result:
                return state.result
            return None

        try:
            if timeout:
                return await asyncio.wait_for(task, timeout=timeout)
            else:
                return await task
        except TimeoutError:
            return None
        except asyncio.CancelledError:
            # Task was cancelled (e.g., via cancel_subagent).
            # Return the result that cancel_subagent already stored.
            state = self._subagents.get(subagent_id)
            if state and state.result:
                return state.result
            return None

    def list_subagents(self) -> list[dict[str, Any]]:
        """
        List all subagents spawned by this manager.

        When agent_temporary_workspace is provided, this will scan all agent temp workspaces
        and merge their registries to show subagents from all agents (following workspace
        visibility principles - agents can only see subagents from other agents after seeing
        their answers via injection).

        Returns:
            List of subagent info dictionaries, each containing:
                - subagent_id: Unique identifier
                - status: Current status (running, completed, timeout, failed)
                - workspace: Path to subagent workspace
                - task: Task description (truncated)
                - session_id: Session ID for continuation
                - continuable: Whether this subagent can be continued
                - source_agent: Agent ID that spawned this subagent (when merging registries)
                - created_at, execution_time_seconds, success, last_continued_at, etc.
        """
        subagents: dict[str, dict[str, Any]] = {}

        # First, load this agent's own registry
        registry_file = self.subagents_base / "_registry.json"
        if registry_file.exists():
            try:
                registry = json.loads(registry_file.read_text())
                # Registry format: {"subagents": [{"subagent_id": "...", ...}, ...]}
                subagents_list = registry.get("subagents", [])
                for entry in subagents_list:
                    subagent_id = entry.get("subagent_id")
                    if not subagent_id:
                        continue
                    subagents[subagent_id] = {
                        "subagent_id": subagent_id,
                        "status": entry.get("status"),
                        "workspace": entry.get("workspace"),
                        "task": entry.get("task"),
                        "created_at": entry.get("created_at"),
                        "execution_time_seconds": entry.get("execution_time_seconds"),
                        "success": entry.get("success"),
                        "session_id": entry.get("session_id"),
                        "last_continued_at": entry.get("last_continued_at"),
                        "continuable": bool(entry.get("session_id")),
                        "source_agent": self.parent_agent_id,
                    }
            except json.JSONDecodeError:
                logger.warning("[SubagentManager] Failed to parse registry for list_subagents")

        # If agent_temporary_workspace is provided, scan all agent temp workspaces
        # to merge registries from all agents
        if self._agent_temporary_workspace and self._agent_temporary_workspace.exists():
            for agent_dir in self._agent_temporary_workspace.iterdir():
                if not agent_dir.is_dir():
                    continue

                agent_id = agent_dir.name
                agent_registry_file = agent_dir / "subagents" / "_registry.json"

                if not agent_registry_file.exists():
                    continue

                try:
                    agent_registry = json.loads(agent_registry_file.read_text())
                    # Registry format: {"subagents": [{"subagent_id": "...", ...}, ...]}
                    subagents_list = agent_registry.get("subagents", [])
                    for entry in subagents_list:
                        subagent_id = entry.get("subagent_id")
                        if not subagent_id:
                            continue

                        # Use a prefixed key to avoid collisions between agents
                        # (each agent can have its own subagent with the same ID)
                        prefixed_id = f"{agent_id}_{subagent_id}"

                        # Skip if we already have this subagent from our own registry
                        # (our own registry takes precedence)
                        if subagent_id in subagents and agent_id == self.parent_agent_id:
                            continue

                        subagents[prefixed_id] = {
                            "subagent_id": subagent_id,
                            "status": entry.get("status"),
                            "workspace": entry.get("workspace"),
                            "task": entry.get("task"),
                            "created_at": entry.get("created_at"),
                            "execution_time_seconds": entry.get("execution_time_seconds"),
                            "success": entry.get("success"),
                            "session_id": entry.get("session_id"),
                            "last_continued_at": entry.get("last_continued_at"),
                            "continuable": bool(entry.get("session_id")),
                            "source_agent": agent_id,
                        }
                except json.JSONDecodeError:
                    logger.warning(
                        f"[SubagentManager] Failed to parse registry for agent {agent_id}",
                    )

        # Update with currently tracked subagents (in-memory state takes precedence)
        for subagent_id, state in self._subagents.items():
            task_preview = state.config.task[:100] + ("..." if len(state.config.task) > 100 else "")
            current_entry = subagents.get(subagent_id, {})
            current_entry.update(
                {
                    "subagent_id": subagent_id,
                    "status": state.status,
                    "workspace": state.workspace_path,
                    "started_at": state.started_at.isoformat() if state.started_at else None,
                    "task": task_preview,
                    "session_id": self._subagent_sessions.get(subagent_id, current_entry.get("session_id")),
                    "continuable": bool(self._subagent_sessions.get(subagent_id, current_entry.get("session_id"))),
                    "source_agent": self.parent_agent_id,
                },
            )

            # For running subagents expose elapsed/timeout so the parent agent can
            # calibrate patience and avoid premature cancellation.
            if state.status == "running" and state.started_at:
                elapsed = max(0.0, (datetime.now() - state.started_at).total_seconds())
                timeout = float(state.config.timeout_seconds)
                current_entry.update(
                    {
                        "elapsed_seconds": round(elapsed, 1),
                        "timeout_seconds": timeout,
                        "seconds_remaining": round(max(0.0, timeout - elapsed), 1),
                    },
                )

            # Include full result payload for completed in-memory subagents so callers
            # can retrieve answers from list_subagents without a second fetch tool.
            if state.result:
                result_status = state.result.status
                # Preserve explicit cancellation from in-memory state even when
                # the result payload uses a generic error status.
                if str(state.status).lower() in {"cancelled", "canceled"}:
                    result_status = "cancelled"
                result_payload = state.result.to_dict()
                if result_status == "cancelled":
                    result_payload["status"] = "cancelled"
                current_entry.update(
                    {
                        "status": result_status,
                        "success": state.result.success,
                        "execution_time_seconds": state.result.execution_time_seconds,
                        "result": result_payload,
                    },
                )
            else:
                current_entry.pop("result", None)

            subagents[subagent_id] = current_entry

        return list(subagents.values())

    def get_subagent_result(self, subagent_id: str) -> SubagentResult | None:
        """
        Get result for a specific subagent.

        Args:
            subagent_id: Subagent identifier

        Returns:
            SubagentResult if subagent exists and completed, None otherwise
        """
        state = self._subagents.get(subagent_id)
        if state and state.result:
            return state.result
        return None

    def get_subagent_costs_summary(self) -> dict[str, Any]:
        """
        Get aggregated cost summary for all subagents.

        Returns:
            Dictionary with total costs and per-subagent breakdown
        """
        total_input_tokens = 0
        total_output_tokens = 0
        total_estimated_cost = 0.0
        subagent_details = []

        for subagent_id, state in self._subagents.items():
            if state.result and state.result.token_usage:
                tu = state.result.token_usage
                input_tokens = tu.get("input_tokens", 0)
                output_tokens = tu.get("output_tokens", 0)
                cost = tu.get("estimated_cost", 0.0)

                total_input_tokens += input_tokens
                total_output_tokens += output_tokens
                total_estimated_cost += cost

                subagent_details.append(
                    {
                        "subagent_id": subagent_id,
                        "status": state.result.status,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "estimated_cost": round(cost, 6),
                        "execution_time_seconds": state.result.execution_time_seconds,
                    },
                )

        return {
            "total_subagents": len(self._subagents),
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_estimated_cost": round(total_estimated_cost, 6),
            "subagents": subagent_details,
        }

    def get_subagent_pointer(self, subagent_id: str) -> SubagentPointer | None:
        """
        Get pointer for a subagent (for plan.json tracking).

        Args:
            subagent_id: Subagent identifier

        Returns:
            SubagentPointer if subagent exists, None otherwise
        """
        state = self._subagents.get(subagent_id)
        if not state:
            return None

        pointer = SubagentPointer(
            id=subagent_id,
            task=state.config.task,
            workspace=state.workspace_path,
            status=state.status,
            created_at=state.config.created_at,
        )

        if state.result:
            pointer.mark_completed(state.result)

        return pointer

    def cleanup_subagent(self, subagent_id: str, remove_workspace: bool = False) -> bool:
        """
        Clean up a subagent.

        Args:
            subagent_id: Subagent identifier
            remove_workspace: If True, also remove the workspace directory

        Returns:
            True if cleanup successful, False if subagent not found
        """
        if subagent_id not in self._subagents:
            return False

        if remove_workspace:
            workspace_dir = self.subagents_base / subagent_id
            if workspace_dir.exists():
                shutil.rmtree(workspace_dir)
                logger.info(f"[SubagentManager] Removed workspace for {subagent_id}")

        del self._subagents[subagent_id]
        return True

    async def cancel_subagent(self, subagent_id: str) -> dict[str, Any]:
        """
        Cancel a single running subagent.

        Internal method called by the background tool delegate — not exposed
        as a model-facing MCP tool.

        Args:
            subagent_id: ID of the subagent to cancel

        Returns:
            Dict with success status and details
        """
        state = self._subagents.get(subagent_id)
        if state is None:
            return {"success": False, "error": f"Subagent not found: {subagent_id}"}

        terminal_statuses = {
            "completed",
            "completed_but_timeout",
            "partial",
            "failed",
            "timeout",
            "cancelled",
            "canceled",
            "error",
        }
        if state.status in terminal_statuses:
            return {
                "success": False,
                "error": f"Subagent {subagent_id} already in terminal state: {state.status}",
            }

        # Delegated mode: write cancel sentinel and cancel background task.
        if self._subagent_runtime_mode == "delegated" and self._delegation_directory:
            try:
                from massgen.subagent.delegation_protocol import write_cancel_sentinel

                write_cancel_sentinel(Path(self._delegation_directory), subagent_id)
                logger.info(f"[SubagentManager] Wrote cancel sentinel for delegated subagent {subagent_id}")
            except Exception as e:
                logger.error(f"[SubagentManager] Failed to write cancel sentinel for {subagent_id}: {e}")

            bg_task = self._background_tasks.get(subagent_id)
            if bg_task and not bg_task.done():
                bg_task.cancel()
                logger.info(f"[SubagentManager] Cancelled background task for delegated subagent {subagent_id}")

            state.status = "cancelled"
            if state.finished_at is None:
                state.finished_at = datetime.now()
            return {"success": True, "subagent_id": subagent_id, "status": "cancelled"}

        # Graceful shutdown: send SIGINT BEFORE cancelling bg_task.
        # bg_task.cancel() raises CancelledError into _execute_with_orchestrator,
        # whose handler calls process.terminate()/kill() — which would kill the
        # subprocess before SIGINT can be processed by CancellationManager.
        process = self._active_processes.get(subagent_id)
        if process and process.returncode is None:
            try:
                import signal as sig

                # SIGINT triggers CancellationManager → save_partial_turn()
                # which saves per-agent workspaces, answers, and execution traces
                process.send_signal(sig.SIGINT)
                try:
                    await asyncio.wait_for(process.wait(), timeout=10.0)
                    logger.info(
                        f"[SubagentManager] Graceful SIGINT shutdown for {subagent_id}",
                    )
                except TimeoutError:
                    logger.warning(
                        f"[SubagentManager] SIGINT timeout, sending SIGTERM to {subagent_id}",
                    )
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5.0)
                    except TimeoutError:
                        logger.warning(
                            f"[SubagentManager] Force killing {subagent_id}",
                        )
                        process.kill()
                        await process.wait()
            except Exception as e:
                logger.error(f"[SubagentManager] Error cancelling {subagent_id}: {e}")

        # Cancel asyncio background task AFTER process exit — the process is already
        # dead so CancelledError handler won't race with our SIGINT shutdown.
        bg_task = self._background_tasks.get(subagent_id)
        if bg_task and not bg_task.done():
            bg_task.cancel()
            logger.info(f"[SubagentManager] Cancelled background task for {subagent_id}")

        state.status = "cancelled"
        if state.finished_at is None:
            state.finished_at = datetime.now()
        if state.result is None:
            elapsed = 0.0
            if state.started_at is not None:
                elapsed = max(0.0, (state.finished_at - state.started_at).total_seconds())
            state.result = SubagentResult.create_error(
                subagent_id=subagent_id,
                error="Subagent cancelled",
                workspace_path=state.workspace_path or "",
                execution_time_seconds=elapsed,
            )

        # Best-effort session_id recovery from sentinel file
        workspace = Path(state.workspace_path) if state.workspace_path else None
        session_id_recovered = None
        if workspace and workspace.exists():
            _, _, recovered_id = self._parse_subprocess_status(workspace)
            if recovered_id and self._session_has_saved_turns(workspace, recovered_id):
                session_id_recovered = recovered_id
                self._subagent_sessions[subagent_id] = recovered_id
            elif recovered_id:
                logger.info(
                    f"[SubagentManager] Ignoring empty recovered session for {subagent_id}: {recovered_id}",
                )

        # Always save to registry so continue_subagent can find this entry
        continuable_via = "session" if session_id_recovered else "context_recovery"
        self._save_subagent_to_registry(
            subagent_id=subagent_id,
            session_id=session_id_recovered,
            config=state.config,
            result=state.result,
            continuable_via=continuable_via,
        )

        logger.info(f"[SubagentManager] Cancelled subagent {subagent_id}")

        return {
            "success": True,
            "operation": "cancel_subagent",
            "subagent_id": subagent_id,
            "status": "cancelled",
        }

    async def cancel_all_subagents(self) -> int:
        """
        Cancel all running subagent processes gracefully.

        This should be called when the parent process receives a termination
        signal (e.g., Ctrl+C) to ensure all child processes are cleaned up.

        Returns:
            Number of subagents that were cancelled
        """
        cancelled_count = 0
        cancelled_subagent_ids: set[str] = set()
        for subagent_id, process in list(self._active_processes.items()):
            if process.returncode is None:  # Still running
                logger.warning(f"[SubagentManager] Cancelling subagent {subagent_id}...")
                try:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5.0)
                    except TimeoutError:
                        logger.warning(f"[SubagentManager] Force killing subagent {subagent_id}")
                        process.kill()
                        await process.wait()
                    cancelled_count += 1
                    cancelled_subagent_ids.add(subagent_id)
                except Exception as e:
                    logger.error(f"[SubagentManager] Error cancelling {subagent_id}: {e}")

        self._active_processes.clear()

        # Also cancel any background tasks
        cancelled_background_tasks: list = []
        for task_id, task in list(self._background_tasks.items()):
            if not task.done():
                logger.warning(f"[SubagentManager] Cancelling background task {task_id}...")
                task.cancel()
                cancelled_count += 1
                cancelled_subagent_ids.add(task_id)
                cancelled_background_tasks.append(task)

        # R5: await the cancellations so each task runs its CancelledError handler
        # (cancelled-status preservation + idempotent self-pop) against the LIVE
        # registry, before we clear it — instead of resuming after this method
        # returns and operating on an already-cleared dict.
        if cancelled_background_tasks:
            await asyncio.gather(*cancelled_background_tasks, return_exceptions=True)

        self._background_tasks.clear()

        # Keep in-memory subagent states consistent with cancellation so list/status
        # surfaces (including TUI cards) do not continue to show stale "running".
        terminal_statuses = {
            "completed",
            "completed_but_timeout",
            "partial",
            "failed",
            "timeout",
            "cancelled",
            "canceled",
            "error",
        }
        for subagent_id, state in self._subagents.items():
            if str(state.status).lower() in terminal_statuses:
                continue
            if cancelled_subagent_ids and subagent_id not in cancelled_subagent_ids:
                # cancel_all_subagents is called during global shutdown/cleanup;
                # any remaining non-terminal subagent should be treated as cancelled.
                cancelled_subagent_ids.add(subagent_id)
            state.status = "cancelled"
            if state.finished_at is None:
                state.finished_at = datetime.now()
            if state.result is None:
                elapsed = 0.0
                if state.started_at is not None:
                    elapsed = max(0.0, (state.finished_at - state.started_at).total_seconds())
                state.result = SubagentResult.create_error(
                    subagent_id=subagent_id,
                    error="Subagent cancelled",
                    workspace_path=state.workspace_path or "",
                    execution_time_seconds=elapsed,
                )

        return cancelled_count

    def cleanup_all(self, remove_workspaces: bool = False) -> int:
        """
        Clean up all subagents.

        Args:
            remove_workspaces: If True, also remove workspace directories

        Returns:
            Number of subagents cleaned up
        """
        count = len(self._subagents)
        subagent_ids = list(self._subagents.keys())

        for subagent_id in subagent_ids:
            self.cleanup_subagent(subagent_id, remove_workspace=remove_workspaces)

        return count

    # =========================================================================
    # Timeout Recovery Methods
    # =========================================================================

    def _extract_status_from_workspace(self, workspace: Path) -> dict[str, Any]:
        """
        Extract coordination status from a subagent's workspace.

        Reads the status.json file from the subagent's full_logs directory
        to determine completion state, winner, and costs.

        Args:
            workspace: Path to the subagent's workspace directory

        Returns:
            Dictionary with:
            - phase: Coordination phase (initial_answer, enforcement, presentation)
            - completion_percentage: 0-100 progress
            - winner: Agent ID of winner if selected
            - votes: Vote counts by agent
            - has_completed_work: True if any useful work was done
            - costs: Token usage costs if available
        """
        result = {
            "phase": None,
            "completion_percentage": None,
            "winner": None,
            "votes": {},
            "has_completed_work": False,
            "costs": {},
            "historical_workspaces": {},
            "historical_workspaces_raw": [],  # Raw list with agentId/timestamp for log path lookup
        }

        # Try multiple locations for status.json:
        # 1. full_logs/status.json in workspace (standard location)
        # 2. .massgen/.../status.json in workspace (nested orchestrator logs)
        status_file = workspace / "full_logs" / "status.json"
        if not status_file.exists():
            # Try to find status.json in nested .massgen logs
            massgen_logs = workspace / ".massgen" / "massgen_logs"
            if massgen_logs.exists():
                # Find most recent log directory
                log_dirs = sorted(massgen_logs.glob("log_*"), reverse=True)
                for log_dir in log_dirs:
                    nested_status = log_dir / "turn_1" / "attempt_1" / "status.json"
                    if nested_status.exists():
                        status_file = nested_status
                        break

        if not status_file.exists():
            return result

        try:
            status_data = json.loads(status_file.read_text())

            # Extract coordination phase (nested structure)
            coordination = status_data.get("coordination", {})
            result["phase"] = coordination.get("phase")
            result["completion_percentage"] = coordination.get("completion_percentage")

            # Extract winner and votes (nested structure)
            results_data = status_data.get("results", {})
            result["winner"] = results_data.get("winner")
            result["votes"] = results_data.get("votes", {})

            # Extract historical workspaces for answer lookup
            # Key by both answerLabel (for votes) and agentId (for winner)
            historical_list = status_data.get("historical_workspaces", [])
            if isinstance(historical_list, list):
                result["historical_workspaces_raw"] = historical_list  # Keep raw for log path lookup
                workspaces_dict = {}
                for i, ws in enumerate(historical_list):
                    if isinstance(ws, dict) and ws.get("workspacePath"):
                        path = ws.get("workspacePath", "")
                        # Key by answerLabel (matches votes dict keys like "agent2.1")
                        answer_label = ws.get("answerLabel")
                        if answer_label:
                            workspaces_dict[answer_label] = path
                        # Also key by agentId (matches winner field)
                        agent_id = ws.get("agentId", ws.get("answerId", f"agent_{i}"))
                        if agent_id:
                            workspaces_dict[agent_id] = path
                result["historical_workspaces"] = workspaces_dict
            else:
                result["historical_workspaces"] = historical_list

            # Extract costs (nested structure)
            costs_data = status_data.get("costs", {})
            if costs_data:
                result["costs"] = {
                    "input_tokens": costs_data.get("total_input_tokens", 0),
                    "output_tokens": costs_data.get("total_output_tokens", 0),
                    "estimated_cost": costs_data.get("total_estimated_cost", 0.0),
                }

            # Determine if there's completed work
            phase = result["phase"]
            if phase == "presentation":
                result["has_completed_work"] = True
            elif phase == "enforcement":
                # In enforcement phase, we have answers if there are votes or workspaces
                result["has_completed_work"] = bool(result["votes"]) or bool(result["historical_workspaces"])
            elif phase == "initial_answer":
                # In initial phase, check if any workspaces exist
                result["has_completed_work"] = bool(result["historical_workspaces"])

        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"[SubagentManager] Failed to read status.json: {e}")

        return result

    def _extract_answer_from_workspace(
        self,
        workspace: Path,
        winner_agent_id: str | None = None,
        votes: dict[str, int] | None = None,
        historical_workspaces: dict[str, str] | None = None,
        historical_workspaces_raw: list[dict[str, Any]] | None = None,
        log_path: Path | None = None,
    ) -> str | None:
        """
        Extract the best available answer from a subagent's workspace.

        Follows the same selection logic as the orchestrator's graceful timeout:
        1. If winner_agent_id is set, use that agent's answer
        2. If votes exist, select agent with most votes (ties broken by registration order)
        3. Fall back to agent with most recent answer by timestamp
        4. Check answer.txt if no agent workspaces

        Args:
            workspace: Path to the subagent's workspace
            winner_agent_id: Agent ID of explicit winner (from status.json)
            votes: Vote counts by agent (for selection when no winner)
            historical_workspaces: Pre-extracted workspace paths from status.json (optional)
            historical_workspaces_raw: Raw list from status.json with agentId/timestamp (optional)
            log_path: Path to log directory for checking full_logs/{agentId}/{timestamp}/answer.txt

        Returns:
            Answer text if found, None otherwise
        """
        # First check for answer.txt (written by orchestrator on completion)
        answer_file = workspace / "answer.txt"
        if answer_file.exists():
            try:
                return answer_file.read_text().strip()
            except OSError:
                pass

        # Use provided historical_workspaces or try to extract from workspace
        if historical_workspaces is None:
            status = self._extract_status_from_workspace(workspace)
            historical_workspaces = status.get("historical_workspaces", {})

        # If winner specified but not in historical_workspaces, try standard path
        if winner_agent_id and winner_agent_id not in historical_workspaces:
            standard_winner_path = workspace / "workspaces" / winner_agent_id
            if standard_winner_path.exists():
                historical_workspaces[winner_agent_id] = str(standard_winner_path)

        # If no historical workspaces, try to discover from standard workspaces dir
        if not historical_workspaces:
            workspaces_dir = workspace / "workspaces"
            if workspaces_dir.exists():
                for agent_dir in workspaces_dir.iterdir():
                    if agent_dir.is_dir():
                        historical_workspaces[agent_dir.name] = str(agent_dir)

        if not historical_workspaces:
            return None

        # Determine which agent's answer to use
        selected_agent = None

        if winner_agent_id and winner_agent_id in historical_workspaces:
            selected_agent = winner_agent_id
        elif votes:
            # Select by vote count (most votes wins, ties broken by dict order)
            vote_counts = votes if isinstance(votes, dict) else {}
            if vote_counts:
                max_votes = max(vote_counts.values())
                for agent_id in historical_workspaces.keys():
                    if vote_counts.get(agent_id, 0) == max_votes:
                        selected_agent = agent_id
                        break

        # Fall back to most recent answer by timestamp (most context from iterations)
        if not selected_agent and historical_workspaces:
            if historical_workspaces_raw:
                best_ts = ""
                for ws_info in historical_workspaces_raw:
                    ts = ws_info.get("timestamp", "")
                    candidate = ws_info.get("answerLabel") or ws_info.get("agentId")
                    if ts > best_ts and candidate and candidate in historical_workspaces:
                        best_ts = ts
                        selected_agent = candidate
            if not selected_agent:
                selected_agent = list(historical_workspaces.keys())[-1]

        if not selected_agent:
            return None

        # Try to find answer in log directory first (persisted location)
        # Check full_logs/{agentId}/{timestamp}/answer.txt
        if log_path and historical_workspaces_raw:
            for ws_info in historical_workspaces_raw:
                agent_id = ws_info.get("agentId")
                answer_label = ws_info.get("answerLabel")
                timestamp = ws_info.get("timestamp")
                # Match by either agentId or answerLabel
                if (agent_id == selected_agent or answer_label == selected_agent) and timestamp:
                    log_answer_path = log_path / "full_logs" / agent_id / timestamp / "answer.txt"
                    if log_answer_path.exists():
                        try:
                            return log_answer_path.read_text().strip()
                        except OSError:
                            pass

        # Read answer from selected agent's workspace
        # The workspacePath points to the workspace/ subdirectory, but answer.txt
        # is in the parent directory (the timestamped snapshot directory)
        agent_workspace = Path(historical_workspaces[selected_agent])

        # Check parent directory first (where orchestrator saves answer.txt)
        parent_dir = agent_workspace.parent
        for answer_filename in ["answer.txt", "answer.md"]:
            answer_path = parent_dir / answer_filename
            if answer_path.exists():
                try:
                    return answer_path.read_text().strip()
                except OSError:
                    continue

        # Fall back to checking inside workspace
        for answer_filename in ["answer.md", "answer.txt", "response.md", "response.txt"]:
            answer_path = agent_workspace / answer_filename
            if answer_path.exists():
                try:
                    return answer_path.read_text().strip()
                except OSError:
                    continue

        return None

    def _extract_costs_from_status(self, workspace: Path) -> dict[str, Any]:
        """
        Extract token usage costs from a subagent's status.json.

        Args:
            workspace: Path to the subagent's workspace

        Returns:
            Dictionary with input_tokens, output_tokens, estimated_cost
            Empty dict if no costs available
        """
        status = self._extract_status_from_workspace(workspace)
        return status.get("costs", {})

    def _create_timeout_result_with_recovery(
        self,
        subagent_id: str,
        workspace: Path,
        timeout_seconds: float,
        log_path: str | None = None,
        warning: str | None = None,
    ) -> SubagentResult:
        """
        Create a SubagentResult for a timed-out subagent, recovering any completed work.

        This method attempts to extract useful results from a subagent that
        timed out but may have completed work before the timeout.

        Args:
            subagent_id: ID of the subagent
            workspace: Path to subagent workspace
            timeout_seconds: How long the subagent ran
            log_path: Path to log directory
            warning: Warning message (e.g., context truncation)

        Returns:
            SubagentResult with recovered answer and costs if available
        """
        # Extract status - prefer log_path/full_logs/status.json if available
        status = {}
        if log_path:
            log_dir = Path(log_path)
            status = self._extract_status_from_workspace(log_dir)

        # Fall back to workspace if no status from log_path
        if not status.get("phase"):
            status = self._extract_status_from_workspace(workspace)

        # Extract answer from log workspace first (has answer.txt), then runtime workspace
        # Pass historical_workspaces from status so we don't re-read from wrong path
        historical_workspaces = status.get("historical_workspaces", {})
        historical_workspaces_raw = status.get("historical_workspaces_raw", [])
        recovered_answer = None
        if log_path:
            log_dir = Path(log_path)
            log_workspace = log_dir / "workspace"
            if log_workspace.exists():
                recovered_answer = self._extract_answer_from_workspace(
                    log_workspace,
                    winner_agent_id=status.get("winner"),
                    votes=status.get("votes"),
                    historical_workspaces=historical_workspaces,
                    historical_workspaces_raw=historical_workspaces_raw,
                    log_path=log_dir,
                )

        if not recovered_answer:
            recovered_answer = self._extract_answer_from_workspace(
                workspace,
                winner_agent_id=status.get("winner"),
                votes=status.get("votes"),
                historical_workspaces=historical_workspaces,
                historical_workspaces_raw=historical_workspaces_raw,
                log_path=Path(log_path) if log_path else None,
            )

        # Extract costs
        token_usage = status.get("costs", {})

        # Determine if this is partial or complete
        is_partial = False
        if recovered_answer is not None:
            phase = status.get("phase")
            # Partial if we have an answer but no winner and not in presentation
            if phase != "presentation" and not status.get("winner"):
                is_partial = True

        return SubagentResult.create_timeout_with_recovery(
            subagent_id=subagent_id,
            workspace_path=str(workspace),
            timeout_seconds=timeout_seconds,
            recovered_answer=recovered_answer,
            completion_percentage=status.get("completion_percentage"),
            token_usage=token_usage,
            log_path=log_path,
            is_partial=is_partial,
            warning=warning,
        )
