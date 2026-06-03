"""
Subagent Data Models for MassGen

Provides dataclasses for configuring, tracking, and returning results from subagents.
"""

import copy
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic.dataclasses import dataclass as pydantic_dataclass

logger = logging.getLogger(__name__)

DEFAULT_SHARED_CHILD_TEAM_TYPES = ["round_evaluator"]

# Subagent timeout defaults (in seconds)
# These are defaults; actual min/max are configurable via YAML
SUBAGENT_MIN_TIMEOUT = 60  # 1 minute (default minimum)
SUBAGENT_MAX_TIMEOUT = 600  # 10 minutes (default maximum)
SUBAGENT_DEFAULT_TIMEOUT = 300  # 5 minutes


@dataclass
class SpecializedSubagentConfig:
    """
    Configuration for a specialized subagent type discovered from disk.

    Types are defined as directories containing SUBAGENT.md with YAML frontmatter.
    Discovered at startup and listed in the system prompt so agents know to use them.

    Attributes:
        name: Type identifier (e.g., "evaluator", "explorer")
        description: Short description of what this type does
        system_prompt: Full system prompt for the subagent (body of SUBAGENT.md)
        skills: Skill names to pre-load for the subagent
        expected_input: Parent-task brief checklist for this subagent type
        source_path: Path to the SUBAGENT.md file for provenance
    """

    name: str
    description: str
    system_prompt: str = ""
    skills: list[str] = field(default_factory=list)
    expected_input: list[str] = field(default_factory=list)
    source_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "skills": self.skills.copy(),
            "expected_input": self.expected_input.copy(),
            "source_path": self.source_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SpecializedSubagentConfig":
        """Create from dictionary."""
        allowed_keys = {"name", "description", "system_prompt", "skills", "expected_input", "source_path"}
        unsupported_keys = sorted(set(data.keys()) - allowed_keys)
        if unsupported_keys:
            keys = ", ".join(unsupported_keys)
            raise ValueError(
                f"Unsupported specialized subagent config fields: {keys}. " "Allowed fields: name, description, system_prompt, skills, expected_input, source_path",
            )

        expected_input = data.get("expected_input", [])
        if expected_input is None:
            expected_input = []
        if not isinstance(expected_input, list) or any(not isinstance(item, str) for item in expected_input):
            raise ValueError("Invalid specialized subagent config field 'expected_input': expected list[str]")

        return cls(
            name=data["name"],
            description=data.get("description", ""),
            system_prompt=data.get("system_prompt", ""),
            skills=data.get("skills", []),
            expected_input=expected_input,
            source_path=data.get("source_path", ""),
        )


@dataclass
class SubagentConfig:
    """
    Configuration for spawning a subagent.

    Attributes:
        id: Unique subagent identifier (UUID if not provided)
        task: The task/prompt for the subagent to execute
        parent_agent_id: ID of the agent that spawned this subagent
        model: Optional model override (inherits from parent if None)
        timeout_seconds: Maximum execution time (clamped to configured min/max range)
        context_files: List of file paths the subagent can READ (read-only access enforced)
        context_paths: Extra read-only paths beyond the parent workspace (e.g., peer workspaces)
        include_parent_workspace: Mount parent agent workspace read-only (default True)
        use_docker: Whether to use Docker container (inherits from parent settings)
        system_prompt: Optional custom system prompt for the subagent
    """

    id: str
    task: str
    parent_agent_id: str
    model: str | None = None
    timeout_seconds: int = 300
    context_files: list[str] = field(default_factory=list)
    context_paths: list[str] = field(default_factory=list)
    include_parent_workspace: bool = True
    use_docker: bool = True
    system_prompt: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        task: str,
        parent_agent_id: str,
        subagent_id: str | None = None,
        model: str | None = None,
        timeout_seconds: int = SUBAGENT_DEFAULT_TIMEOUT,
        context_files: list[str] | None = None,
        context_paths: list[str] | None = None,
        include_parent_workspace: bool = True,
        use_docker: bool = True,
        system_prompt: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "SubagentConfig":
        """
        Factory method to create a SubagentConfig with auto-generated ID.

        Args:
            task: The task for the subagent
            parent_agent_id: ID of the parent agent
            subagent_id: Optional custom ID (generates UUID if not provided)
            model: Optional model override
            timeout_seconds: Execution timeout (clamped at manager level to configured range)
            context_files: File paths subagent can read (read-only, no write access)
            context_paths: Extra read-only paths beyond the parent workspace.
                Use for peer workspace paths (from CURRENT_ANSWERS) or other allowed paths.
                Parent workspace is always included unless include_parent_workspace=False.
            include_parent_workspace: If True (default), the parent agent's workspace is
                automatically mounted read-only. Set False for fully isolated subagents.
            use_docker: Whether to use Docker
            system_prompt: Optional custom system prompt
            metadata: Additional metadata

        Returns:
            Configured SubagentConfig instance
        """
        # Note: timeout clamping is done at SubagentManager level with configurable min/max
        return cls(
            id=subagent_id or f"sub_{uuid.uuid4().hex[:8]}",
            task=task,
            parent_agent_id=parent_agent_id,
            model=model,
            timeout_seconds=timeout_seconds,
            context_files=context_files or [],
            context_paths=context_paths or [],
            include_parent_workspace=include_parent_workspace,
            use_docker=use_docker,
            system_prompt=system_prompt,
            metadata=metadata or {},
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary for serialization."""
        return {
            "id": self.id,
            "task": self.task,
            "parent_agent_id": self.parent_agent_id,
            "model": self.model,
            "timeout_seconds": self.timeout_seconds,
            "context_files": self.context_files.copy(),
            "context_paths": self.context_paths.copy(),
            "include_parent_workspace": self.include_parent_workspace,
            "use_docker": self.use_docker,
            "system_prompt": self.system_prompt,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata.copy(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SubagentConfig":
        """Create config from dictionary."""
        # Note: timeout clamping is done at SubagentManager level with configurable min/max
        return cls(
            id=data["id"],
            task=data["task"],
            parent_agent_id=data["parent_agent_id"],
            model=data.get("model"),
            timeout_seconds=data.get("timeout_seconds", SUBAGENT_DEFAULT_TIMEOUT),
            context_files=data.get("context_files", []),
            context_paths=data.get("context_paths", []),
            include_parent_workspace=data.get("include_parent_workspace", True),
            use_docker=data.get("use_docker", True),
            system_prompt=data.get("system_prompt"),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.now(),
            metadata=data.get("metadata", {}),
        )


@pydantic_dataclass
class SubagentOrchestratorConfig:
    """
    Configuration for subagent orchestrator mode.

    When enabled, subagents use a full Orchestrator with multiple agents.
    This enables multi-agent coordination within subagent execution.

    Attributes:
        enabled: Whether orchestrator mode is enabled (default False = single agent)
        agents: Shared common agent configurations for the subagent orchestrator.
                These are primarily used as the default child team for
                `round_evaluator`. Other subagent types prefer per-parent
                child-team config or spawning-parent backend inheritance.
                Each agent config can have: id (optional, auto-generated if missing),
                backend (with type, model, base_url, etc.)
                If empty/None, no shared common agents are added.
        inherit_spawning_agent_backend: If True, synthesize a parent-local subagent
                agent from the spawning parent's backend when that parent has no
                explicit `subagent_agents` configured.
        shared_child_team_types: Subagent types that should use the shared
                `subagent_orchestrator.agents` pool when configured. Defaults to
                `["round_evaluator"]`. Leave out a type to keep it anchored to the
                spawning parent's own child-team config by default. Use `["*"]`
                to apply the shared pool to every subagent type.
        coordination: Optional coordination config subset (broadcast, planning, etc.)
        max_new_answers: Maximum new answers per agent before forcing consensus.
                        Default 3 for iterative (refine=True) subagent runs.
                        The refine=False path forces max_new_answers_per_agent=1 regardless.
        enable_web_search: Whether to enable web search for subagents (None = inherit from parent).
                          This is set in YAML config, not by agents at runtime.
        parse_at_references: Whether subagent subprocess CLI should parse @path/@path:w
            references from task text into context paths. Default False because
            subagent task text is AI-generated and frequently contains literal '@'
            characters (CSS @media, @keyframes, font URLs like wght@400) that
            would be misinterpreted as file path references. Context paths for
            subagents are provided explicitly via the spawn API's context_paths
            parameter. Set True only if subagent tasks intentionally use @path
            syntax.
        final_answer_strategy: Optional child orchestrator final-answer policy.
            Mirrors the top-level orchestrator setting for multi-agent subagent runs.
        disable_injection: Whether agents work independently without seeing peer answers.
            Default True (ensemble pattern: isolated production for answer diversity).
        defer_voting_until_all_answered: Whether to hold voting until all agents
            have submitted at least one answer. Default True (ensemble pattern).
    """

    enabled: bool = False
    agents: list[dict[str, Any]] = field(default_factory=list)
    inherit_spawning_agent_backend: bool = False
    shared_child_team_types: list[str] = field(default_factory=lambda: DEFAULT_SHARED_CHILD_TEAM_TYPES.copy())
    coordination: dict[str, Any] = field(default_factory=dict)
    max_new_answers: int = 3  # Used for refine=True iterative mode; refine=False forces 1
    enable_web_search: bool | None = None  # None = inherit from parent
    parse_at_references: bool = False
    final_answer_strategy: Literal["winner_reuse", "winner_present", "synthesize"] | None = None
    disable_injection: bool = True  # Ensemble default: agents work independently
    defer_voting_until_all_answered: bool = True  # Ensemble default: vote after all produce

    @property
    def num_agents(self) -> int:
        """Number of agents configured (defaults to 1 if no agents specified)."""
        return len(self.agents) if self.agents else 1

    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.agents and len(self.agents) > 10:
            raise ValueError("Cannot have more than 10 agents for subagents")
        if not isinstance(self.shared_child_team_types, list) or any(not isinstance(item, str) or not item.strip() for item in self.shared_child_team_types):
            raise ValueError(
                "Invalid shared_child_team_types: expected a list of non-empty strings",
            )
        self.shared_child_team_types = [item.strip() for item in self.shared_child_team_types]

    def get_agent_config(self, agent_index: int, subagent_id: str) -> dict[str, Any]:
        """
        Get the config for a specific agent index.

        Args:
            agent_index: 0-based index of the agent
            subagent_id: ID of the parent subagent (for auto-generating agent IDs)

        Returns:
            Agent config dict with id and backend, or empty dict if not specified
        """
        if self.agents and agent_index < len(self.agents):
            config = self.agents[agent_index].copy()
            # Auto-generate ID if not provided
            if "id" not in config:
                config["id"] = f"{subagent_id}_agent_{agent_index + 1}"
            return config
        return {}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SubagentOrchestratorConfig":
        """Create config from dictionary (YAML parsing)."""
        # Note: 'blocking' key is ignored (kept for backwards compatibility)
        return cls(
            enabled=data.get("enabled", False),
            agents=data.get("agents", []),
            inherit_spawning_agent_backend=data.get("inherit_spawning_agent_backend", False),
            shared_child_team_types=data.get("shared_child_team_types", DEFAULT_SHARED_CHILD_TEAM_TYPES.copy()),
            coordination=data.get("coordination", {}),
            max_new_answers=data.get("max_new_answers", 3),
            enable_web_search=data.get("enable_web_search"),
            parse_at_references=data.get("parse_at_references", False),
            final_answer_strategy=data.get("final_answer_strategy"),
            disable_injection=data.get("disable_injection", True),
            defer_voting_until_all_answered=data.get("defer_voting_until_all_answered", True),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary for serialization."""
        result = {
            "enabled": self.enabled,
            "agents": [a.copy() for a in self.agents] if self.agents else [],
            "inherit_spawning_agent_backend": self.inherit_spawning_agent_backend,
            "shared_child_team_types": self.shared_child_team_types.copy(),
            "coordination": self.coordination.copy() if self.coordination else {},
            "max_new_answers": self.max_new_answers,
            "parse_at_references": self.parse_at_references,
            "disable_injection": self.disable_injection,
            "defer_voting_until_all_answered": self.defer_voting_until_all_answered,
        }
        if self.enable_web_search is not None:
            result["enable_web_search"] = self.enable_web_search
        if self.final_answer_strategy is not None:
            result["final_answer_strategy"] = self.final_answer_strategy
        return result


@dataclass
class SubagentResult:
    """
    Structured result returned from subagent execution.

    Attributes:
        subagent_id: ID of the subagent
        status: Final status - one of:
            - completed: Normal successful completion
            - completed_but_timeout: Work completed but parent timed out (recovered answer)
            - partial: Partial work available (in voting phase, no winner)
            - timeout: Timed out with no recoverable work
            - error: Failed with error
        success: Whether execution was successful
        answer: Final answer text from the subagent (includes relevant file paths)
        workspace_path: Path to the subagent's workspace (always set, even on timeout/error)
        execution_time_seconds: How long the subagent ran
        error: Error message if status is error/timeout
        token_usage: Token usage statistics (if available)
        log_path: Path to subagent log directory (for debugging on failure/timeout)
        completion_percentage: Coordination completion percentage (0-100) if available
    """

    subagent_id: str
    status: Literal["completed", "completed_but_timeout", "partial", "timeout", "error"]
    success: bool
    answer: str | None = None
    workspace_path: str = ""
    execution_time_seconds: float = 0.0
    error: str | None = None
    token_usage: dict[str, int] = field(default_factory=dict)
    log_path: str | None = None
    completion_percentage: int | None = None
    warning: str | None = None  # Warning messages (e.g., context truncation)

    @staticmethod
    def resolve_events_path(base_log_dir: Path) -> str | None:
        """Resolve the path to events.jsonl from a base log directory.

        This method finds the exact events.jsonl file path from a subagent's
        base log directory, checking both completed and live subagent paths.

        Priority:
        1. full_logs/events.jsonl (completed subagents)
        2. full_logs/turn_1/attempt_1/events.jsonl (legacy completed layout)
        3. live_logs/log_*/turn_1/attempt_1/events.jsonl (running subagents)
        4. subprocess_logs.json reference (fallback)

        Args:
            base_log_dir: Base log directory for the subagent (e.g., /logs/sub_abc123/)

        Returns:
            Full path to events.jsonl if found, None otherwise
        """
        # Check full_logs (completed subagents)
        full_logs_events = base_log_dir / "full_logs" / "events.jsonl"
        if full_logs_events.exists():
            return str(full_logs_events.resolve())

        # Legacy layout: full_logs/turn_1/attempt_1/events.jsonl
        legacy_full_logs = base_log_dir / "full_logs" / "turn_1" / "attempt_1" / "events.jsonl"
        if legacy_full_logs.exists():
            return str(legacy_full_logs.resolve())

        # Check live_logs (running subagents)
        live_logs = base_log_dir / "live_logs"
        if live_logs.exists():
            try:
                for subdir in sorted(live_logs.glob("log_*"), reverse=True):
                    candidate = subdir / "turn_1" / "attempt_1" / "events.jsonl"
                    if candidate.exists():
                        return str(candidate.resolve())
                    # Fallback if events.jsonl lives at root of log_* (older layout)
                    candidate = subdir / "events.jsonl"
                    if candidate.exists():
                        return str(candidate.resolve())
            except Exception:
                pass

        # Read subprocess_logs.json for live path
        subprocess_ref = base_log_dir / "subprocess_logs.json"
        if subprocess_ref.exists():
            try:
                ref_data = json.loads(subprocess_ref.read_text())
                subprocess_log_dir = ref_data.get("subprocess_log_dir")
                if subprocess_log_dir:
                    live_events = Path(subprocess_log_dir) / "events.jsonl"
                    if live_events.exists():
                        return str(live_events.resolve())
            except (json.JSONDecodeError, OSError):
                pass

        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary for tool return value."""
        result = {
            "subagent_id": self.subagent_id,
            "status": self.status,
            "success": self.success,
            "answer": self.answer,
            "workspace": self.workspace_path,
            "execution_time_seconds": self.execution_time_seconds,
            "error": self.error,
            "token_usage": self.token_usage.copy(),
        }
        # Include log_path if available (useful for debugging failed/timed out subagents)
        # Resolve to the events.jsonl file path for TUI consumption
        if self.log_path:
            log_dir = Path(self.log_path)
            resolved = SubagentResult.resolve_events_path(log_dir)
            result["log_path"] = resolved or self.log_path
        # Include completion_percentage if available (for timeout recovery)
        if self.completion_percentage is not None:
            result["completion_percentage"] = self.completion_percentage
        # Include warning if present (e.g., context truncation)
        if self.warning:
            result["warning"] = self.warning
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SubagentResult":
        """Create result from dictionary."""
        return cls(
            subagent_id=data["subagent_id"],
            status=data["status"],
            success=data["success"],
            answer=data.get("answer"),
            workspace_path=data.get("workspace", ""),
            execution_time_seconds=data.get("execution_time_seconds", 0.0),
            error=data.get("error"),
            token_usage=data.get("token_usage", {}),
            log_path=data.get("log_path"),
            completion_percentage=data.get("completion_percentage"),
            warning=data.get("warning"),
        )

    @classmethod
    def create_success(
        cls,
        subagent_id: str,
        answer: str,
        workspace_path: str,
        execution_time_seconds: float,
        token_usage: dict[str, int] | None = None,
        log_path: str | None = None,
        warning: str | None = None,
    ) -> "SubagentResult":
        """Create a successful result."""
        return cls(
            subagent_id=subagent_id,
            status="completed",
            success=True,
            answer=answer,
            workspace_path=workspace_path,
            execution_time_seconds=execution_time_seconds,
            token_usage=token_usage or {},
            log_path=log_path,
            warning=warning,
        )

    @classmethod
    def create_timeout(
        cls,
        subagent_id: str,
        workspace_path: str,
        timeout_seconds: float,
        log_path: str | None = None,
        warning: str | None = None,
    ) -> "SubagentResult":
        """Create a timeout result."""
        return cls(
            subagent_id=subagent_id,
            status="timeout",
            success=False,
            answer=None,
            workspace_path=workspace_path,
            execution_time_seconds=timeout_seconds,
            error=f"Subagent exceeded timeout of {timeout_seconds} seconds",
            log_path=log_path,
            warning=warning,
        )

    @classmethod
    def create_error(
        cls,
        subagent_id: str,
        error: str,
        workspace_path: str = "",
        execution_time_seconds: float = 0.0,
        log_path: str | None = None,
        warning: str | None = None,
    ) -> "SubagentResult":
        """Create an error result."""
        return cls(
            subagent_id=subagent_id,
            status="error",
            success=False,
            answer=None,
            workspace_path=workspace_path,
            execution_time_seconds=execution_time_seconds,
            error=error,
            log_path=log_path,
            warning=warning,
        )

    @classmethod
    def create_timeout_with_recovery(
        cls,
        subagent_id: str,
        workspace_path: str,
        timeout_seconds: float,
        recovered_answer: str | None = None,
        completion_percentage: int | None = None,
        token_usage: dict[str, Any] | None = None,
        log_path: str | None = None,
        is_partial: bool = False,
        warning: str | None = None,
    ) -> "SubagentResult":
        """
        Create a timeout result with recovered work from the workspace.

        This factory method is used when a subagent times out but has completed
        or partial work that can be recovered from its workspace.

        Args:
            subagent_id: ID of the subagent
            workspace_path: Path to subagent workspace (always provided)
            timeout_seconds: How long the subagent ran before timeout
            recovered_answer: Answer extracted from workspace (None if no work)
            completion_percentage: Coordination completion percentage (0-100)
            token_usage: Token costs extracted from status.json
            log_path: Path to log directory
            is_partial: True if work is partial (no winner selected)
            warning: Warning message (e.g., context truncation)

        Returns:
            SubagentResult with appropriate status:
            - completed_but_timeout: Full answer recovered (success=True)
            - partial: Partial work recovered (success=False)
            - timeout: No work recovered (success=False)
        """
        if recovered_answer is not None:
            if is_partial:
                status = "partial"
                success = False
            else:
                status = "completed_but_timeout"
                success = True
        else:
            status = "timeout"
            success = False

        return cls(
            subagent_id=subagent_id,
            status=status,
            success=success,
            answer=recovered_answer,
            workspace_path=workspace_path,
            execution_time_seconds=timeout_seconds,
            error=f"Subagent exceeded timeout of {timeout_seconds} seconds",
            token_usage=token_usage or {},
            log_path=log_path,
            completion_percentage=completion_percentage,
            warning=warning,
        )


@dataclass
class RoundEvaluatorResult:
    """Typed result contract for blocking round_evaluator runs.

    The parent receives this from the evaluator stage and uses ``packet_text``
    as the human-readable critique packet.

    On the normal path, the parent reads authoritative artifacts from the
    evaluator workspace:

    - ``critique_packet.md`` for the human-readable packet
    - ``verdict.json`` for machine-readable verdict metadata
    - ``next_tasks.json`` for iterate-only implementation handoff

    ``packet_text`` is the authoritative source loaded from ``critique_packet.md``,
    not from the subagent's answer field.
    """

    packet_text: str | None = None
    status: Literal["success", "degraded", "error"] = "error"
    degraded_fallback_used: bool = False
    execution_time_seconds: float = 0.0
    error: str | None = None
    subagent_id: str = ""
    log_path: str | None = None
    primary_artifact_path: str | None = None
    verdict_artifact_path: str | None = None
    next_tasks_artifact_path: str | None = None
    task_plan_source: Literal["next_tasks_artifact"] | None = None
    # Structured verdict fields (populated from verdict.json)
    verdict: Literal["iterate", "converged"] | None = None
    scores: dict[str, int] | None = None
    improvements: list[dict] | None = None
    preserve: list[dict] | None = None
    opportunities: list[dict] | None = None  # Independent ideas, not corrections
    next_tasks: dict[str, Any] | None = None
    next_tasks_objective: str | None = None
    next_tasks_primary_strategy: str | None = None
    next_tasks_why_this_strategy: str | None = None
    next_tasks_deprioritize_or_remove: list[str] | None = None
    next_tasks_execution_scope: dict[str, Any] | None = None
    next_tasks_strategy_mode: Literal["incremental_refinement", "thesis_shift"] | None = None
    next_tasks_incremental_override_reason: str | None = None
    next_tasks_success_contract: dict[str, Any] | None = None
    evolved_prompt: str | None = None
    evolved_prompt_rationale: str | None = None
    clean_packet_text: str | None = None  # packet_text with verdict_block stripped

    _VERDICT_BLOCK_RE = re.compile(
        r"(?:```|~~~)json\s+verdict_block\s*\n(.*?)\n(?:```|~~~)",
        re.DOTALL,
    )

    @staticmethod
    def parse_verdict_block(packet_text: str) -> dict | None:
        """Extract and parse a structured verdict_block from critique text.

        Returns the parsed dict if a valid verdict_block is found with the
        required ``verdict`` key, otherwise returns None.
        """
        match = RoundEvaluatorResult._VERDICT_BLOCK_RE.search(packet_text)
        if not match:
            return None
        try:
            data = json.loads(match.group(1))
        except (json.JSONDecodeError, TypeError):
            logger.warning("[RoundEvaluatorResult] Malformed JSON in verdict_block — skipped; orchestrator will fall back to verdict.json artifact")
            return None
        if not isinstance(data, dict) or "verdict" not in data:
            logger.warning("[RoundEvaluatorResult] verdict_block missing required 'verdict' key")
            return None
        return data

    @staticmethod
    def strip_verdict_block(packet_text: str) -> str:
        """Return packet_text with the verdict_block fence removed."""
        return RoundEvaluatorResult._VERDICT_BLOCK_RE.sub("", packet_text).strip()

    @staticmethod
    def normalize_verdict_payload(verdict_payload: Any) -> dict[str, Any] | None:
        """Return a validated verdict payload or None."""
        if not isinstance(verdict_payload, dict):
            return None

        verdict = str(verdict_payload.get("verdict") or "").strip().lower()
        if verdict not in {"iterate", "converged"}:
            return None

        raw_scores = verdict_payload.get("scores")
        if not isinstance(raw_scores, dict) or not raw_scores:
            return None

        scores: dict[str, int] = {}
        for key, value in raw_scores.items():
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return None
            scores[str(key)] = int(value)

        normalized = copy.deepcopy(verdict_payload)
        normalized["schema_version"] = str(normalized.get("schema_version") or "1")
        normalized["verdict"] = verdict
        normalized["scores"] = scores
        return normalized

    @staticmethod
    def normalize_next_tasks_payload(next_tasks: Any) -> dict[str, Any] | None:
        """Return a validated next_tasks payload or None."""
        if not isinstance(next_tasks, dict):
            return None

        success_contract = next_tasks.get("success_contract")
        if not isinstance(success_contract, dict):
            return None
        outcome_statement = str(success_contract.get("outcome_statement") or "").strip()
        quality_bar = str(success_contract.get("quality_bar") or "").strip()
        fail_if_any = success_contract.get("fail_if_any")
        required_evidence = success_contract.get("required_evidence")
        if not outcome_statement or not quality_bar:
            return None
        if not isinstance(fail_if_any, list) or not [str(item).strip() for item in fail_if_any if str(item).strip()]:
            return None
        if not isinstance(required_evidence, list) or not [str(item).strip() for item in required_evidence if str(item).strip()]:
            return None

        strategy_mode = str(next_tasks.get("strategy_mode") or "").strip()
        if strategy_mode not in {"incremental_refinement", "thesis_shift"}:
            return None

        approach_assessment = next_tasks.get("approach_assessment")
        if not isinstance(approach_assessment, dict):
            return None
        ceiling_status = str(approach_assessment.get("ceiling_status") or "").strip()
        if ceiling_status not in {"ceiling_not_reached", "ceiling_approaching", "ceiling_reached"}:
            return None

        incremental_override_reason = str(next_tasks.get("incremental_override_reason") or "").strip()
        if ceiling_status in {"ceiling_approaching", "ceiling_reached"} and strategy_mode == "incremental_refinement" and not incremental_override_reason:
            # Soft validation: accept the payload with a default reason rather
            # than discarding valid task data over a missing metadata field.
            import logging as _logging

            _logging.getLogger(__name__).warning(
                "next_tasks payload has %s + incremental_refinement but no " "incremental_override_reason — defaulting to placeholder",
                ceiling_status,
            )
            incremental_override_reason = "Evaluator did not provide override reasoning"

        tasks = next_tasks.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            return None

        normalized = copy.deepcopy(next_tasks)
        # Backfill the default override reason if it was populated above.
        if incremental_override_reason and not str(normalized.get("incremental_override_reason") or "").strip():
            normalized["incremental_override_reason"] = incremental_override_reason
        thesis_shift_task_count = 0
        for task in normalized.get("tasks", []):
            if not isinstance(task, dict):
                return None
            description = str(task.get("description") or "").strip()
            verification = str(task.get("verification") or "").strip()
            metadata = task.get("metadata")
            success_criteria = str(task.get("success_criteria") or "").strip()
            failure_signals = task.get("failure_signals")
            required_task_evidence = task.get("required_evidence")
            if not description:
                return None
            if not verification:
                if not isinstance(metadata, dict):
                    return None
                metadata_verification = str(metadata.get("verification") or "").strip()
                if not metadata_verification:
                    return None
            if not success_criteria:
                return None
            if not isinstance(failure_signals, list) or not [str(item).strip() for item in failure_signals if str(item).strip()]:
                return None
            if not isinstance(required_task_evidence, list) or not [str(item).strip() for item in required_task_evidence if str(item).strip()]:
                return None
            strategy_role = str(task.get("strategy_role") or "").strip()
            if strategy_role:
                if strategy_role not in {"thesis_shift", "supporting_fix"}:
                    return None
                if strategy_role == "thesis_shift":
                    thesis_shift_task_count += 1

        if strategy_mode == "thesis_shift" and thesis_shift_task_count < 1:
            return None

        # Soft validation for evolved_prompt: extract if well-formed, remove if not.
        evolved_prompt_raw = normalized.get("evolved_prompt")
        if evolved_prompt_raw is not None:
            if not isinstance(evolved_prompt_raw, dict) or not str(evolved_prompt_raw.get("prompt") or "").strip():
                import logging as _logging

                _logging.getLogger(__name__).warning(
                    "next_tasks payload has malformed or empty evolved_prompt — ignoring",
                )
                normalized.pop("evolved_prompt", None)

        return normalized

    @staticmethod
    def extract_next_tasks_strategy(next_tasks: dict[str, Any] | None) -> dict[str, Any]:
        """Extract the top-level strategy fields from a normalized next_tasks payload."""
        if not isinstance(next_tasks, dict):
            return {
                "objective": None,
                "primary_strategy": None,
                "why_this_strategy": None,
                "deprioritize_or_remove": None,
                "execution_scope": None,
                "strategy_mode": None,
                "incremental_override_reason": None,
                "success_contract": None,
            }

        objective = str(next_tasks.get("objective") or "").strip() or None
        primary_strategy = str(next_tasks.get("primary_strategy") or "").strip() or None
        why_this_strategy = str(next_tasks.get("why_this_strategy") or "").strip() or None

        deprioritize_raw = next_tasks.get("deprioritize_or_remove")
        deprioritize_or_remove = None
        if isinstance(deprioritize_raw, list):
            normalized_items = [str(item).strip() for item in deprioritize_raw if str(item).strip()]
            if normalized_items:
                deprioritize_or_remove = normalized_items

        execution_scope = next_tasks.get("execution_scope")
        normalized_execution_scope = copy.deepcopy(execution_scope) if isinstance(execution_scope, dict) else None
        strategy_mode = str(next_tasks.get("strategy_mode") or "").strip() or None
        incremental_override_reason = str(next_tasks.get("incremental_override_reason") or "").strip() or None
        success_contract = next_tasks.get("success_contract")
        normalized_success_contract = copy.deepcopy(success_contract) if isinstance(success_contract, dict) else None

        evolved_prompt = None
        evolved_prompt_rationale = None
        evolved_prompt_obj = next_tasks.get("evolved_prompt")
        if isinstance(evolved_prompt_obj, dict):
            evolved_prompt = str(evolved_prompt_obj.get("prompt") or "").strip() or None
            evolved_prompt_rationale = str(evolved_prompt_obj.get("evolution_rationale") or "").strip() or None

        return {
            "objective": objective,
            "primary_strategy": primary_strategy,
            "why_this_strategy": why_this_strategy,
            "deprioritize_or_remove": deprioritize_or_remove,
            "execution_scope": normalized_execution_scope,
            "strategy_mode": strategy_mode,
            "incremental_override_reason": incremental_override_reason,
            "success_contract": normalized_success_contract,
            "evolved_prompt": evolved_prompt,
            "evolved_prompt_rationale": evolved_prompt_rationale,
        }

    @classmethod
    def _candidate_next_tasks_artifact_paths(
        cls,
        workspace_path: str | None,
        log_path: str | None = None,
    ) -> list[Path]:
        """Return likely locations for ``next_tasks.json`` in priority order."""
        return cls._candidate_artifact_paths(
            "next_tasks.json",
            workspace_path=workspace_path,
            log_path=log_path,
        )

    @classmethod
    def _candidate_artifact_paths(
        cls,
        artifact_name: str,
        workspace_path: str | None,
        log_path: str | None = None,
    ) -> list[Path]:
        """Return likely locations for a round_evaluator artifact in priority order."""
        candidates: list[tuple[int, float, Path]] = []
        seen: set[str] = set()

        def _add_candidate(path: Path, priority: int) -> None:
            if not path.exists():
                return
            key = str(path.resolve())
            if key in seen:
                return
            seen.add(key)
            try:
                mtime = path.stat().st_mtime
            except OSError:
                mtime = 0.0
            candidates.append((priority, -mtime, path))

        if workspace_path:
            workspace = Path(workspace_path)
            _add_candidate(workspace / artifact_name, priority=0)
            # Inner agent directories (subagent_orchestrator layout):
            # When the round evaluator runs as a multi-agent MassGen instance,
            # the winning agent writes artifacts into workspace/agent_<id>/.
            for candidate in workspace.glob(f"agent_*/{artifact_name}"):
                _add_candidate(candidate, priority=5)
            for pattern in (
                f".massgen/sessions/*/turn_*/workspace/{artifact_name}",
                f".massgen/massgen_logs/*/turn_*/final/*/workspace/{artifact_name}",
                f".massgen/massgen_logs/*/turn_*/attempt_*/final/*/workspace/{artifact_name}",
            ):
                for candidate in workspace.glob(pattern):
                    _add_candidate(candidate, priority=10)

        if log_path:
            log_file = Path(log_path)
            search_roots = [log_file.parent, *list(log_file.parents[:4])]
            for root in search_roots:
                for pattern in (
                    f"full_logs/final/*/workspace/{artifact_name}",
                    f"live_logs/*/turn_*/final/*/workspace/{artifact_name}",
                ):
                    for candidate in root.glob(pattern):
                        _add_candidate(candidate, priority=20)

        candidates.sort(key=lambda item: (item[0], item[1], str(item[2])))
        return [path for _, _, path in candidates]

    @classmethod
    def resolve_packet_artifact(
        cls,
        workspace_path: str | None,
        log_path: str | None = None,
    ) -> tuple[str | None, Path | None]:
        """Load the best available ``critique_packet.md`` artifact."""
        for packet_path in cls._candidate_artifact_paths(
            "critique_packet.md",
            workspace_path=workspace_path,
            log_path=log_path,
        ):
            try:
                packet_text = packet_path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning(
                    "[RoundEvaluatorResult] Failed to read critique packet from %s: %s",
                    packet_path,
                    exc,
                )
                continue
            if not packet_text.strip():
                logger.warning(
                    "[RoundEvaluatorResult] critique_packet.md at %s is empty",
                    packet_path,
                )
                continue
            return packet_text, packet_path
        return None, None

    @classmethod
    def resolve_verdict_artifact(
        cls,
        workspace_path: str | None,
        log_path: str | None = None,
    ) -> tuple[dict[str, Any] | None, Path | None]:
        """Load and validate the best available ``verdict.json`` artifact."""
        for verdict_path in cls._candidate_artifact_paths(
            "verdict.json",
            workspace_path=workspace_path,
            log_path=log_path,
        ):
            try:
                raw_payload = json.loads(verdict_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, TypeError) as exc:
                logger.warning(
                    "[RoundEvaluatorResult] Failed to read verdict artifact from %s: %s",
                    verdict_path,
                    exc,
                )
                continue

            normalized = cls.normalize_verdict_payload(raw_payload)
            if normalized is None:
                logger.warning(
                    "[RoundEvaluatorResult] Invalid verdict artifact at %s",
                    verdict_path,
                )
                continue
            return normalized, verdict_path

        return None, None

    @classmethod
    def resolve_next_tasks_artifact(
        cls,
        workspace_path: str | None,
        log_path: str | None = None,
    ) -> tuple[dict[str, Any] | None, Path | None]:
        """Load and validate the best available ``next_tasks.json`` artifact."""
        for next_tasks_path in cls._candidate_next_tasks_artifact_paths(
            workspace_path=workspace_path,
            log_path=log_path,
        ):
            try:
                raw_payload = json.loads(next_tasks_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, TypeError) as exc:
                logger.warning(
                    "[RoundEvaluatorResult] Failed to read next_tasks artifact from %s: %s",
                    next_tasks_path,
                    exc,
                )
                continue

            normalized = cls.normalize_next_tasks_payload(raw_payload)
            if normalized is None:
                logger.warning(
                    "[RoundEvaluatorResult] Invalid next_tasks artifact at %s",
                    next_tasks_path,
                )
                continue
            return normalized, next_tasks_path

        return None, None

    @classmethod
    def from_subagent_result(
        cls,
        result: "SubagentResult",
        elapsed: float = 0.0,
    ) -> "RoundEvaluatorResult":
        """Build from a raw ``SubagentResult``."""
        packet_text, packet_path = cls.resolve_packet_artifact(
            workspace_path=result.workspace_path,
            log_path=result.log_path,
        )
        if packet_text is None:
            return cls(
                status="degraded",
                degraded_fallback_used=True,
                execution_time_seconds=elapsed or result.execution_time_seconds,
                error=result.error or "No evaluator critique_packet.md artifact produced",
                subagent_id=result.subagent_id,
                log_path=result.log_path,
            )

        verdict_data, verdict_path = cls.resolve_verdict_artifact(
            workspace_path=result.workspace_path,
            log_path=result.log_path,
        )

        verdict = None
        scores = None
        improvements = None
        preserve = None
        opportunities = None
        next_tasks = None
        next_tasks_artifact_path = None
        task_plan_source = None
        next_tasks_strategy = cls.extract_next_tasks_strategy(None)

        if verdict_data:
            verdict = verdict_data.get("verdict")
            scores = verdict_data.get("scores")
            improvements = verdict_data.get("improvements")
            preserve = verdict_data.get("preserve")
            opportunities = verdict_data.get("opportunities")

        if verdict == "iterate":
            artifact_next_tasks, artifact_path = cls.resolve_next_tasks_artifact(
                workspace_path=result.workspace_path,
                log_path=result.log_path,
            )
            if artifact_next_tasks:
                next_tasks = artifact_next_tasks
                next_tasks_artifact_path = str(artifact_path) if artifact_path else None
                task_plan_source = "next_tasks_artifact"
                next_tasks_strategy = cls.extract_next_tasks_strategy(artifact_next_tasks)

        return cls(
            packet_text=packet_text,
            status="success",
            degraded_fallback_used=False,
            execution_time_seconds=elapsed or result.execution_time_seconds,
            subagent_id=result.subagent_id,
            log_path=result.log_path,
            primary_artifact_path=str(packet_path) if packet_path else None,
            verdict_artifact_path=str(verdict_path) if verdict_path else None,
            next_tasks_artifact_path=next_tasks_artifact_path,
            task_plan_source=task_plan_source,
            verdict=verdict,
            scores=scores,
            improvements=improvements,
            preserve=preserve,
            opportunities=opportunities,
            next_tasks=next_tasks,
            next_tasks_objective=next_tasks_strategy.get("objective"),
            next_tasks_primary_strategy=next_tasks_strategy.get("primary_strategy"),
            next_tasks_why_this_strategy=next_tasks_strategy.get("why_this_strategy"),
            next_tasks_deprioritize_or_remove=next_tasks_strategy.get("deprioritize_or_remove"),
            next_tasks_execution_scope=next_tasks_strategy.get("execution_scope"),
            next_tasks_strategy_mode=next_tasks_strategy.get("strategy_mode"),
            next_tasks_incremental_override_reason=next_tasks_strategy.get("incremental_override_reason"),
            next_tasks_success_contract=next_tasks_strategy.get("success_contract"),
            evolved_prompt=next_tasks_strategy.get("evolved_prompt"),
            evolved_prompt_rationale=next_tasks_strategy.get("evolved_prompt_rationale"),
            clean_packet_text=cls.strip_verdict_block(packet_text) if packet_text else None,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "packet_text": self.packet_text,
            "status": self.status,
            "degraded_fallback_used": self.degraded_fallback_used,
            "execution_time_seconds": self.execution_time_seconds,
            "error": self.error,
            "subagent_id": self.subagent_id,
            "log_path": self.log_path,
            "primary_artifact_path": self.primary_artifact_path,
            "verdict_artifact_path": self.verdict_artifact_path,
            "next_tasks_artifact_path": self.next_tasks_artifact_path,
            "task_plan_source": self.task_plan_source,
            "verdict": self.verdict,
            "scores": self.scores,
            "improvements": self.improvements,
            "preserve": self.preserve,
            "opportunities": self.opportunities,
            "next_tasks": self.next_tasks,
            "next_tasks_objective": self.next_tasks_objective,
            "next_tasks_primary_strategy": self.next_tasks_primary_strategy,
            "next_tasks_why_this_strategy": self.next_tasks_why_this_strategy,
            "next_tasks_deprioritize_or_remove": self.next_tasks_deprioritize_or_remove,
            "next_tasks_execution_scope": self.next_tasks_execution_scope,
            "next_tasks_strategy_mode": self.next_tasks_strategy_mode,
            "next_tasks_incremental_override_reason": self.next_tasks_incremental_override_reason,
            "next_tasks_success_contract": self.next_tasks_success_contract,
            "evolved_prompt": self.evolved_prompt,
            "evolved_prompt_rationale": self.evolved_prompt_rationale,
            "clean_packet_text": self.clean_packet_text,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RoundEvaluatorResult":
        """Deserialize from dictionary."""
        return cls(
            packet_text=data.get("packet_text"),
            status=data.get("status", "error"),
            degraded_fallback_used=data.get("degraded_fallback_used", False),
            execution_time_seconds=data.get("execution_time_seconds", 0.0),
            error=data.get("error"),
            subagent_id=data.get("subagent_id", ""),
            log_path=data.get("log_path"),
            primary_artifact_path=data.get("primary_artifact_path"),
            verdict_artifact_path=data.get("verdict_artifact_path"),
            next_tasks_artifact_path=data.get("next_tasks_artifact_path"),
            task_plan_source=data.get("task_plan_source"),
            verdict=data.get("verdict"),
            scores=data.get("scores"),
            improvements=data.get("improvements"),
            preserve=data.get("preserve"),
            opportunities=data.get("opportunities"),
            next_tasks=data.get("next_tasks"),
            next_tasks_objective=data.get("next_tasks_objective"),
            next_tasks_primary_strategy=data.get("next_tasks_primary_strategy"),
            next_tasks_why_this_strategy=data.get("next_tasks_why_this_strategy"),
            next_tasks_deprioritize_or_remove=data.get("next_tasks_deprioritize_or_remove"),
            next_tasks_execution_scope=data.get("next_tasks_execution_scope"),
            next_tasks_strategy_mode=data.get("next_tasks_strategy_mode"),
            next_tasks_incremental_override_reason=data.get("next_tasks_incremental_override_reason"),
            next_tasks_success_contract=data.get("next_tasks_success_contract"),
            evolved_prompt=data.get("evolved_prompt"),
            evolved_prompt_rationale=data.get("evolved_prompt_rationale"),
            clean_packet_text=data.get("clean_packet_text"),
        )


@dataclass
class SubagentPointer:
    """
    Pointer to a subagent for tracking in plan.json.

    Used to track subagents spawned during task execution and provide
    visibility into their workspaces and results.

    Attributes:
        id: Subagent identifier
        task: Task description given to the subagent
        workspace: Path to the subagent's workspace
        status: Current status (running/completed/failed/timeout)
        created_at: When the subagent was spawned
        completed_at: When the subagent finished (if applicable)
        result_summary: Brief summary of the result (if completed)
    """

    id: str
    task: str
    workspace: str
    status: Literal["running", "completed", "failed", "timeout"]
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    result_summary: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert pointer to dictionary for serialization."""
        return {
            "id": self.id,
            "task": self.task,
            "workspace": self.workspace,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result_summary": self.result_summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SubagentPointer":
        """Create pointer from dictionary."""
        return cls(
            id=data["id"],
            task=data["task"],
            workspace=data["workspace"],
            status=data["status"],
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            result_summary=data.get("result_summary"),
        )

    def mark_completed(self, result: SubagentResult) -> None:
        """Update pointer when subagent completes."""
        self.status = "completed" if result.success else ("timeout" if result.status == "timeout" else "failed")
        self.completed_at = datetime.now()
        if result.answer:
            # Truncate summary to first 200 chars
            self.result_summary = result.answer[:200] + ("..." if len(result.answer) > 200 else "")


@dataclass
class SubagentState:
    """
    Runtime state of a subagent for tracking during execution.

    Used internally by SubagentManager to track active subagents.

    Attributes:
        config: The subagent configuration
        status: Current execution status
        workspace_path: Path to subagent workspace
        started_at: When execution started
        finished_at: When execution finished
        result: Final result (when completed)
    """

    config: SubagentConfig
    status: Literal[
        "pending",
        "running",
        "completed",
        "completed_but_timeout",
        "partial",
        "failed",
        "timeout",
        "cancelled",
        "error",
    ] = "pending"
    workspace_path: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: SubagentResult | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert state to dictionary."""
        return {
            "config": self.config.to_dict(),
            "status": self.status,
            "workspace_path": self.workspace_path,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "result": self.result.to_dict() if self.result else None,
        }


@dataclass
class SubagentDisplayData:
    """
    Display data for rendering a subagent in the TUI.

    Used by SubagentCard to show live progress, activity, and status.
    Provides a snapshot of subagent state optimized for display purposes.

    Attributes:
        id: Subagent identifier
        task: The task description
        status: Current execution status
        progress_percent: Progress estimate (0-100), based on elapsed/timeout
        elapsed_seconds: Time elapsed since start
        timeout_seconds: Maximum allowed execution time
        workspace_path: Path to subagent workspace directory
        workspace_file_count: Number of files in workspace
        last_log_line: Most recent log line for activity display
        error: Error message if status is error/failed/canceled
        answer_preview: First ~100 chars of answer if completed
        subagent_type: Specialized type label when task used subagent_type
    """

    id: str
    task: str
    status: Literal["pending", "running", "completed", "error", "timeout", "failed", "canceled"]
    progress_percent: int  # 0-100, based on elapsed/timeout
    elapsed_seconds: float
    timeout_seconds: float
    workspace_path: str
    workspace_file_count: int
    last_log_line: str
    error: str | None = None
    answer_preview: str | None = None
    log_path: str | None = None  # Path to log directory for log streaming
    context_paths: list[str] = field(default_factory=list)
    context_paths_labeled: list[dict[str, str]] = field(default_factory=list)
    subagent_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "task": self.task,
            "status": self.status,
            "progress_percent": self.progress_percent,
            "elapsed_seconds": self.elapsed_seconds,
            "timeout_seconds": self.timeout_seconds,
            "workspace_path": self.workspace_path,
            "workspace_file_count": self.workspace_file_count,
            "last_log_line": self.last_log_line,
            "error": self.error,
            "answer_preview": self.answer_preview,
            "log_path": self.log_path,
            "context_paths": self.context_paths.copy(),
            "context_paths_labeled": [e.copy() for e in self.context_paths_labeled],
            "subagent_type": self.subagent_type,
        }
