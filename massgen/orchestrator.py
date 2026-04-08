"""
MassGen Orchestrator Agent - Chat interface that manages sub-agents internally.

The orchestrator presents a unified chat interface to users while coordinating
multiple sub-agents using the proven binary decision framework behind the scenes.

TODOs:

- Move CLI's coordinate_with_context logic to orchestrator and simplify CLI to just use orchestrator
- Implement orchestrator system message functionality to customize coordination behavior:

  * Custom voting strategies (consensus, expertise-weighted, domain-specific)
  * Message construction templates for sub-agent instructions
  * Conflict resolution approaches (evidence-based, democratic, expert-priority)
  * Workflow preferences (thorough vs fast, iterative vs single-pass)
  * Domain-specific coordination (research teams, technical reviews, creative brainstorming)
  * Dynamic agent selection based on task requirements and orchestrator instructions
"""

import ast
import asyncio
import concurrent.futures
import copy
import inspect
import json
import os
import secrets
import shutil
import sys
import time
import traceback
from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from ._broadcast_channel import BroadcastChannel
from .agent_config import AgentConfig, StepModeConfig
from .backend.base import StreamChunk
from .chat_agent import ChatAgent
from .configs.rate_limits import get_rate_limit_config
from .coordination_tracker import CoordinationTracker, EventType
from .events import EventType as StructuredEventType

if TYPE_CHECKING:
    from .dspy_paraphraser import QuestionParaphraser
    from .filesystem_manager import IsolationContextManager
    from .mcp_tools.hooks import RuntimeInboxPoller
    from .subagent.models import RoundEvaluatorResult, SubagentResult

from .filesystem_manager import has_meaningful_content
from .logger_config import get_log_session_dir  # Import to get log directory
from .logger_config import logger  # Import logger directly for INFO logging
from .logger_config import (
    get_event_emitter,
    log_coordination_step,
    log_orchestrator_activity,
    log_orchestrator_agent_message,
    log_stream_chunk,
    log_tool_call,
    set_log_attempt,
)
from .mcp_tools.hooks import (
    BackgroundToolCompleteHook,
    GeneralHookManager,
    HighPriorityTaskReminderHook,
    HookType,
    HumanInputHook,
    MediaCallLedgerHook,
    MidStreamInjectionHook,
    RoundTimeoutPostHook,
    RoundTimeoutPreHook,
    RoundTimeoutState,
    SubagentCompleteHook,
)
from .memory import ConversationMemory, PersistentMemoryBase
from .message_templates import MessageTemplates
from .persona_generator import PersonaGenerator
from .stream_chunk import ChunkType
from .structured_logging import (
    clear_current_round,
    get_tracer,
    log_agent_round_context,
    log_coordination_event,
    set_current_round,
)
from .system_message_builder import SystemMessageBuilder
from .tool import get_post_evaluation_tools, get_workflow_tools
from .tool.workflow_toolkits.base import WORKFLOW_TOOL_NAMES
from .utils import ActionType, AgentStatus, CoordinationStage


@dataclass
class AgentState:
    """Runtime state for an agent during coordination.

    Attributes:
        answer: The agent's current answer/summary, if any
        has_voted: Whether the agent has voted in the current round
        votes: Dictionary storing vote data for this agent
        restart_pending: Whether the agent should gracefully restart due to new answers
        is_killed: Whether this agent has been killed due to timeout/limits
        timeout_reason: Reason for timeout (if applicable)
        answer_count: Number of answers this agent has created (increments on new_answer)
        injection_count: Number of update injections this agent has received
        midstream_injections_this_round: Number of source-agent updates injected in current round
            (used to cap update fanout for stragglers).
        round_start_time: Timestamp when current round started (for per-round timeouts)
        round_timeout_hooks: Tuple of (post_hook, pre_hook) for per-round timeouts, or None
        round_timeout_state: Shared state for timeout hooks (tracks consecutive denials)
        decomposition_answer_streak: Number of consecutive new answers submitted by this
            agent without seeing unseen external answer revisions (decomposition mode).
        seen_answer_counts: Per-agent snapshot of answer revision counts this agent has
            already seen in its context.
    """

    answer: str | None = None
    has_voted: bool = False
    votes: dict[str, Any] = field(default_factory=dict)
    restart_pending: bool = False
    is_killed: bool = False
    timeout_reason: str | None = None
    error_reason: str | None = None
    last_context: dict[str, Any] | None = None  # Store the context sent to this agent
    paraphrase: str | None = None
    answer_count: int = 0  # Track number of answers for memory archiving
    injection_count: int = 0  # Track injections received for mid-stream injection timing
    midstream_injections_this_round: int = 0  # Count source updates injected in current round
    restart_count: int = 0  # Track full restarts (TUI round = restart_count + 1)
    known_answer_ids: set = field(default_factory=set)  # Agent IDs whose answers this agent has seen
    decomposition_answer_streak: int = 0  # Decomposition mode: consecutive answers since unseen external updates
    seen_answer_counts: dict[str, int] = field(default_factory=dict)  # agent_id -> number of answer revisions seen
    round_start_time: float | None = None  # For per-round timeouts
    round_timeout_hooks: tuple | None = None  # (post_hook, pre_hook) for resetting on new round
    round_timeout_state: Optional["RoundTimeoutState"] = None  # Shared timeout state
    # Convergence tracking for novelty injection
    checklist_history: list[dict[str, Any]] = field(default_factory=list)
    # Per-answer checklist call tracking (reset when agent submits new_answer)
    checklist_calls_this_round: int = 0
    # Latest injected answer labels pending checklist recheck allowance.
    pending_checklist_recheck_labels: set[str] = field(default_factory=set)
    # Decomposition mode fields
    stop_summary: str | None = None  # Summary from stop tool
    stop_status: str | None = None  # "complete" or "blocked"


class Orchestrator(ChatAgent):
    """
    Orchestrator Agent - Unified chat interface with sub-agent coordination.

    The orchestrator acts as a single agent from the user's perspective, but internally
    coordinates multiple sub-agents using the proven binary decision framework.

    Key Features:
    - Unified chat interface (same as any individual agent)
    - Automatic sub-agent coordination and conflict resolution
    - Transparent MassGen workflow execution
    - Real-time streaming with proper source attribution
    - Graceful restart mechanism for dynamic case transitions
    - Session management

    TODO - Missing Configuration Options:
    - Option to include/exclude voting details in user messages
    - Configurable timeout settings for agent responses
    - Configurable retry limits and backoff strategies
    - Custom voting strategies beyond simple majority
    - Configurable presentation formats for final answers
    - Advanced coordination workflows (hierarchical, weighted voting, etc.)

    TODO (v0.0.14 Context Sharing Enhancement - See docs/dev_notes/v0.0.14-context.md):
    - Add permission validation logic for agent workspace access
    - Implement validate_agent_access() method to check if agent has required permission for resource
    - Replace current prompt-based access control with explicit system-level enforcement
    - Add PermissionManager integration for managing agent access rules
    - Implement audit logging for all access attempts to workspace resources
    - Support dynamic permission negotiation during runtime
    - Add configurable policy framework for permission management
    - Integrate with workspace snapshot mechanism for controlled context sharing

    Restart Behavior:
    When an agent provides new_answer, all agents gracefully restart to ensure
    consistent coordination state. This allows all agents to transition to Case 2
    evaluation with the new answers available.
    """

    # TODO: derive this cap dynamically from model context limits per backend.
    _ENFORCEMENT_RETRY_BUFFER_MAX_CHARS = 120_000
    _ROUND_EVALUATOR_MAX_LAUNCH_FAILURES = 2

    def __init__(
        self,
        agents: dict[str, ChatAgent],
        orchestrator_id: str = "orchestrator",
        session_id: str | None = None,
        config: AgentConfig | None = None,
        dspy_paraphraser: Optional["QuestionParaphraser"] = None,
        snapshot_storage: str | None = None,
        agent_temporary_workspace: str | None = None,
        previous_turns: list[dict[str, Any]] | None = None,
        winning_agents_history: list[dict[str, Any]] | None = None,
        shared_conversation_memory: ConversationMemory | None = None,
        shared_persistent_memory: PersistentMemoryBase | None = None,
        enable_nlip: bool = False,
        nlip_config: dict[str, Any] | None = None,
        enable_rate_limit: bool = False,
        trace_classification: str = "legacy",
        generated_personas: dict[str, Any] | None = None,
        generated_evaluation_criteria: list | None = None,
        plan_session_id: str | None = None,
        step_mode: StepModeConfig | None = None,
        raw_config: dict[str, Any] | None = None,
    ):
        """
        Initialize MassGen orchestrator.

        Args:
            agents: Dictionary of {agent_id: ChatAgent} - can be individual agents or other orchestrators
            orchestrator_id: Unique identifier for this orchestrator (default: "orchestrator")
            session_id: Optional session identifier
            config: Optional AgentConfig for customizing orchestrator behavior
            dspy_paraphraser: Optional DSPy paraphraser for multi-agent question diversity
            snapshot_storage: Optional path to store agent workspace snapshots
            agent_temporary_workspace: Optional path for agent temporary workspaces
            previous_turns: List of previous turn metadata for multi-turn conversations (loaded by CLI)
            winning_agents_history: List of previous winning agents for memory sharing
                                   Format: [{"agent_id": "agent_b", "turn": 1}, ...]
                                   Loaded from session storage to persist across orchestrator recreations
            shared_conversation_memory: Optional shared conversation memory for all agents
            shared_persistent_memory: Optional shared persistent memory for all agents
            enable_nlip: Enable NLIP (Natural Language Interaction Protocol) support
            nlip_config: Optional NLIP configuration
            enable_rate_limit: Whether to enable rate limiting and cooldown delays (default: False)
            trace_classification: "legacy" (default) preserves current content traces; "strict" emits
                                  coordination/status as non-content for server mode.
            generated_personas: Pre-generated personas from previous turn (for multi-turn persistence)
                               Format: {agent_id: GeneratedPersona, ...}
            generated_evaluation_criteria: Pre-generated evaluation criteria from previous turn
                                          Format: [GeneratedCriterion, ...]
            plan_session_id: Optional plan session ID for plan execution mode (prevents workspace contamination)
            step_mode: Optional StepModeConfig for step mode execution (one agent, one step, exit)
        """
        super().__init__(
            session_id,
            shared_conversation_memory,
            shared_persistent_memory,
        )
        self.orchestrator_id = orchestrator_id
        self.agents = agents
        self.agent_states = {aid: AgentState() for aid in agents.keys()}
        self.config = config or AgentConfig.create_openai_config()
        self.dspy_paraphraser = dspy_paraphraser
        self._plan_session_id = plan_session_id

        # Debug: Log timeout config values
        logger.info(
            f"[Orchestrator] Timeout config: initial={self.config.timeout_config.initial_round_timeout_seconds}s, " f"subsequent={self.config.timeout_config.subsequent_round_timeout_seconds}s",
        )
        self.trace_classification = trace_classification

        # Shared memory for all agents
        self.shared_conversation_memory = shared_conversation_memory
        self.shared_persistent_memory = shared_persistent_memory

        # Get message templates from config
        self.message_templates = self.config.message_templates or MessageTemplates(
            voting_sensitivity=self.config.voting_sensitivity,
            answer_novelty_requirement=self.config.answer_novelty_requirement,
        )
        # Create system message builder for all phases (coordination, presentation, post-evaluation)
        self._system_message_builder: SystemMessageBuilder | None = None  # Lazy initialization
        # Decomposition mode: per-agent subtask assignments
        self._agent_subtasks: dict[str, str | None] = {}
        self._agent_subtask_criteria: dict[str, list] = {}

        # Create workflow tools for agents (vote, new_answer, and optionally broadcast)
        # Will be updated with broadcast tools after coordination config is set
        # Sort agent IDs for consistent anonymous mapping (agent1, agent2, etc.)
        # This ensures consistency with coordination_tracker.get_anonymous_agent_mapping()
        _is_decomposition = getattr(self.config, "coordination_mode", "voting") == "decomposition"
        self.workflow_tools = get_workflow_tools(
            valid_agent_ids=sorted(agents.keys()),
            template_overrides=getattr(
                self.message_templates,
                "_template_overrides",
                {},
            ),
            api_format="chat_completions",  # Default format, will be overridden per backend
            orchestrator=self,  # Pass self for broadcast tools
            broadcast_mode=False,  # Will be updated if broadcasts enabled
            broadcast_wait_by_default=True,
            decomposition_mode=_is_decomposition,
        )

        # Checkpoint-mode workflow tools (includes checkpoint tool for main agent)
        # Built separately so only the main agent gets the checkpoint tool.
        self._checkpoint_workflow_tools = get_workflow_tools(
            valid_agent_ids=sorted(agents.keys()),
            template_overrides=getattr(
                self.message_templates,
                "_template_overrides",
                {},
            ),
            api_format="chat_completions",
            orchestrator=self,
            broadcast_mode=False,
            broadcast_wait_by_default=True,
            decomposition_mode=False,
            checkpoint_mode=True,
        )

        # Client-provided tools (OpenAI-style). These are passed through to backends
        # so models can request them, but are never executed by MassGen.
        self._external_tools: list[dict[str, Any]] = []

        # Step mode configuration (loading deferred until after coordination_tracker init)
        self._step_mode: StepModeConfig | None = step_mode
        self._step_complete: bool = False
        self._step_action_data: dict[str, Any] | None = None

        # MassGen-specific state
        self.current_task: str | None = None
        self.workflow_phase: str = "idle"  # idle, coordinating, presenting

        # Internal coordination state
        self._coordination_messages: list[dict[str, str]] = []
        self._selected_agent: str | None = None
        self._final_presentation_content: str | None = None
        self._presentation_started: bool = False  # Guard against duplicate presentations

        # Per-agent workspace pre-population from cancelled/incomplete turn continuation.
        # When set, _clear_agent_workspaces() copies matched agent workspaces as writable
        # instead of using normal previous_turn pre-population.
        self._pre_populated_workspaces: dict[str, Path] | None = None

        # Track winning agents by turn for memory sharing
        # Format: [{"agent_id": "agent_b", "turn": 1}, {"agent_id": "agent_a", "turn": 2}]
        # Restore from session storage if provided (for multi-turn persistence)
        self._winning_agents_history: list[dict[str, Any]] = winning_agents_history or []
        if self._winning_agents_history:
            logger.info(
                f"📚 Restored {len(self._winning_agents_history)} winning agent(s) from session: {self._winning_agents_history}",
            )
        self._current_turn: int = 0

        # Timeout and resource tracking
        self.total_tokens: int = 0
        self.coordination_start_time: float = 0
        self.is_orchestrator_timeout: bool = False
        self.timeout_reason: str | None = None

        # Restart feature state tracking
        self.current_attempt: int = 0
        max_restarts = self.config.coordination_config.max_orchestration_restarts
        self.max_attempts: int = 1 + max_restarts
        self.restart_pending: bool = False
        self.restart_reason: str | None = None
        self.restart_instructions: str | None = None
        self.previous_attempt_answer: str | None = None  # Store previous winner's answer for restart context

        # Coordination state tracking for cleanup
        self._active_streams: dict = {}
        self._active_tasks: dict = {}
        # Fairness gate logging state to suppress repeated spam lines.
        self._fairness_pause_log_reasons: dict[str, str] = {}
        self._fairness_block_log_states: dict[str, tuple[int, int]] = {}

        # Per-round worktree tracking: {agent_id: branch_name}
        # Tracks the LATEST branch for each agent. Old branches accumulate
        # across rounds (not deleted mid-session) for cross-agent diff visibility.
        self._agent_current_branches: dict[str, str] = {}
        # Per-round isolation managers: {agent_id: IsolationContextManager}
        self._round_isolation_managers: dict[str, "IsolationContextManager"] = {}
        # Per-round worktree path mappings: {agent_id: {isolated_path: original_path}}
        self._round_worktree_paths: dict[str, dict[str, str]] = {}

        # Presentation-phase isolation state (used by _handle_presentation_phase / _review_isolated_changes)
        self._isolation_manager: Optional["IsolationContextManager"] = None
        self._isolation_worktree_paths: dict[str, str] = {}  # worktree_path -> original_path
        self._isolation_removed_paths: dict = {}  # original_path -> ManagedPath
        # Rework signal from review modal (set by _review_isolated_changes, consumed by caller)
        self._pending_review_rework: dict[str, Any] | None = None

        # TUI coordination UI (set externally by CoordinationUI.set_orchestrator())
        self.coordination_ui: Any | None = None

        # Human input hook for injecting user input during execution
        # Shared across all agents (one per orchestration session)
        self._human_input_hook: HumanInputHook | None = None
        # Runtime inbox poller for receiving messages from parent process (subagent mode)
        self._runtime_inbox_poller: "RuntimeInboxPoller | None" = None
        # Background subagent completion tracking
        # Stores pending results for each parent agent until they can be injected
        # Format: {parent_agent_id: [(subagent_id, SubagentResult), ...]}
        self._pending_subagent_results: dict[str, list[tuple[str, "SubagentResult"]]] = {}
        # Background trace analyzer tasks (asyncio.Task per agent)
        self._background_trace_tasks: dict[str, "asyncio.Task[None]"] = {}
        # Evolving criteria state
        self._criteria_evolution_count: int = 0
        self._criteria_evolution_completed_labels: set[tuple[str, ...]] = set()
        self._criteria_evolution_history: list[dict[str, Any]] = []
        # Latest answer-label tuples already critiqued by the orchestrator-owned
        # round_evaluator gate. Prevents duplicate launches for unchanged revisions.
        self._round_evaluator_completed_labels: dict[str, tuple[str, ...]] = {}
        # Tracks failed evaluator launches per answer-label set so deterministic
        # launch failures don't get retried forever.
        self._round_evaluator_launch_failures: dict[tuple[str, tuple[str, ...]], int] = {}
        # Evaluator persona state: set by set_evaluator_personas MCP tool,
        # consumed by _run_round_evaluator_pre_round_if_needed.
        # Pending is single-use; last is reuse fallback.
        self._pending_evaluator_personas: list[dict[str, str]] | None = None
        self._last_evaluator_personas: list[dict[str, str]] | None = None
        # Context blocks inserted at the start of the next parent round.
        self._round_start_context_blocks: dict[str, list[str]] = {}

        # Track which subagents have been injected to prevent duplicates
        # Format: {agent_id: set(subagent_id, ...)}
        self._injected_subagents: dict[str, set[str]] = {}
        # Hookless fallback cache for background tool completions that were polled
        # before the next safe checkpoint (consumed by enforcement-message injection).
        self._no_hook_pending_background_tool_results: dict[str, list[dict[str, Any]]] = {}

        # Per-agent injection directories for auto-populating planning MCP from draft_approach
        self._planning_injection_dirs: dict[str, Path] = {}

        # Background subagent configuration (parsed from coordination_config)
        background_subagent_config = {}
        if hasattr(self.config, "coordination_config"):
            background_subagent_config = getattr(self.config.coordination_config, "background_subagents", {}) or {}
        self._background_subagents_enabled = background_subagent_config.get("enabled", True)
        self._background_subagent_injection_strategy = background_subagent_config.get("injection_strategy", "tool_result")

        # Raw YAML config dict (used by checkpoint subprocess to generate sub-run configs)
        self._raw_config_dict: dict[str, Any] = raw_config or {}

        # Checkpoint coordination state (subprocess-based)
        self._main_agent_id: str | None = None  # Set by set_main_agent()
        self._checkpoint_active: bool = False  # True during checkpoint subprocess
        self._checkpoint_task: str | None = None  # Current checkpoint task
        self._checkpoint_number: int = 0  # Sequential checkpoint counter
        self._checkpoint_participants: dict[str, dict[str, Any]] = {}  # display_id -> info

        # Agent startup rate limiting (per model)
        # Load from centralized configuration file instead of hardcoding
        self._enable_rate_limit = enable_rate_limit
        self._agent_startup_times: dict[str, list[float]] = {}  # model -> [timestamps]
        self._rate_limits: dict[str, dict[str, int]] = self._load_rate_limits_from_config() if enable_rate_limit else {}

        # Context sharing for agents with filesystem support
        self._snapshot_storage: str | None = snapshot_storage
        self._agent_temporary_workspace: str | None = agent_temporary_workspace

        # Per-agent display round counter — increments every time _run_agent_turn
        # is called, so each agent execution (answer, vote, or final) gets a unique
        # round number for the UI.  Separate from coordination_tracker.agent_rounds
        # which only increments on answer-triggered restarts.
        self._agent_display_round: dict[str, int] = {}

        # DSPy paraphrase tracking
        self._agent_paraphrases: dict[str, str] = {}
        self._paraphrase_generation_errors: int = 0

        # Prompt evolution (per-round, from round evaluator)
        self._evolved_prompts: dict[str, str] = {}
        self._original_task: str | None = None  # Snapshot of task before any evolution

        # Persona generation tracking
        # If personas are passed in (from previous turn), use them and mark as already generated
        self._generated_personas: dict[str, Any] = generated_personas or {}  # agent_id -> GeneratedPersona
        self._personas_generated: bool = bool(
            generated_personas,
        )  # Skip generation if already have them
        self._original_system_messages: dict[
            str,
            str | None,
        ] = {}  # agent_id -> original message
        if self._personas_generated:
            logger.info(
                f"📝 Restored {len(self._generated_personas)} persona(s) from previous turn",
            )

        # Evaluation criteria generation tracking
        # If criteria are passed in (from previous turn), use them and mark as already generated
        self._generated_evaluation_criteria: list | None = generated_evaluation_criteria
        self._evaluation_criteria_generated: bool = bool(generated_evaluation_criteria)

        # Prompt improvement guard
        self._prompt_improved: bool = False
        # Guard to push criteria to TUI display at most once (checklist_gated does it in
        # _init_checklist_tool; non-checklist modes do it on first round).
        self._criteria_pushed_to_display: bool = False
        # Last resolved criteria payload for display (used when checklist criteria
        # are initialized before CoordinationUI/display is attached).
        self._criteria_display_payload: dict[str, Any] | None = None
        if self._evaluation_criteria_generated:
            logger.info(
                f"📝 Restored {len(self._generated_evaluation_criteria)} evaluation criteria from previous turn",
            )

        # Multi-turn session tracking (loaded by CLI, not managed by orchestrator)
        self._previous_turns: list[dict[str, Any]] = previous_turns or []

        # Coordination tracking - always enabled for analysis/debugging
        self.coordination_tracker = CoordinationTracker()
        # In step mode, include virtual agent IDs in coordination tracker
        # so anonymization covers both real and virtual agents
        if self._step_mode and self._step_mode.enabled:
            from .step_mode import load_session_dir_inputs

            _step_inputs = load_session_dir_inputs(self._step_mode.session_dir)
            all_agent_ids = sorted(set(list(agents.keys()) + list(_step_inputs.virtual_agents.keys())))
            self.coordination_tracker.initialize_session(all_agent_ids)
            # Pre-load ALL session dir answers into coordination tracker —
            # including the real agent's own prior answer. In step mode, the
            # agent starts fresh each step and should see all prior answers
            # (including its own) anonymized.
            for va_id, va_state in _step_inputs.virtual_agents.items():
                if va_state.latest_answer is not None:
                    self.coordination_tracker.add_agent_answer(va_id, va_state.latest_answer)
                    logger.info(
                        "[StepMode] Pre-loaded session agent %s (step %d, answer: %d chars)",
                        va_id,
                        va_state.latest_step,
                        len(va_state.latest_answer),
                    )
            self._step_inputs = _step_inputs
            # Pre-mark session dir answers as "seen" by real agents
            # so fairness/restart logic doesn't block on static answers
            for real_agent_id in agents.keys():
                for va_id, va_state in _step_inputs.virtual_agents.items():
                    if va_state.latest_answer is not None:
                        self.agent_states[real_agent_id].known_answer_ids.add(va_id)
        else:
            self.coordination_tracker.initialize_session(list(agents.keys()))
            self._step_inputs = None

        # Create snapshot storage and workspace directories if specified
        if snapshot_storage:
            self._snapshot_storage = snapshot_storage
            snapshot_path = Path(self._snapshot_storage)
            # Clean existing directory if it exists and has contents
            if snapshot_path.exists() and any(snapshot_path.iterdir()):

                def on_rm_error(func, path, exc_info):
                    # Handle read-only files (common in git repos on Windows)
                    import stat

                    try:
                        # Always try to force writable - os.access can be unreliable on Windows
                        os.chmod(path, stat.S_IWRITE)
                        func(path)
                    except Exception:
                        # If recovery failed, raise the new exception
                        raise

                if sys.version_info >= (3, 12):
                    shutil.rmtree(snapshot_path, onexc=on_rm_error)
                else:
                    shutil.rmtree(snapshot_path, onerror=on_rm_error)
            snapshot_path.mkdir(parents=True, exist_ok=True)

        # Configure orchestration paths for each agent with filesystem support
        # Get skills configuration if skills are enabled
        skills_directory = None
        massgen_skills = []
        load_previous_session_skills = False
        if hasattr(self.config, "coordination_config") and hasattr(
            self.config.coordination_config,
            "use_skills",
        ):
            if self.config.coordination_config.use_skills:
                skills_directory = self.config.coordination_config.skills_directory
                massgen_skills = self.config.coordination_config.massgen_skills
                load_previous_session_skills = getattr(
                    self.config.coordination_config,
                    "load_previous_session_skills",
                    False,
                )

        # Create dedicated subagent logs directory if subagents are enabled.
        # This directory is mounted into Docker containers so the subagent MCP
        # server (which runs inside Docker) can write logs. Using a dedicated
        # directory avoids mounting the entire .massgen/massgen_logs tree.
        self._subagent_logs_dir: Path | None = None
        self._delegation_dir: Path | None = None
        self._subagent_launch_watcher = None  # SubagentLaunchWatcher instance (host-side)
        if hasattr(self.config, "coordination_config") and getattr(self.config.coordination_config, "enable_subagents", False):
            try:
                log_session_dir = get_log_session_dir()
                if log_session_dir:
                    cwd = Path.cwd()
                    subagent_logs_base = cwd / ".massgen" / "subagent_logs"
                    subagent_logs_base.mkdir(parents=True, exist_ok=True)
                    run_id = secrets.token_hex(4)
                    self._subagent_logs_dir = subagent_logs_base / f"sa_{run_id}"
                    self._subagent_logs_dir.mkdir(parents=True, exist_ok=True)
                    subagent_entries_dir = self._subagent_logs_dir / "subagents"
                    subagent_entries_dir.mkdir(parents=True, exist_ok=True)
                    logger.info(
                        f"[Orchestrator] Created subagent logs directory: {self._subagent_logs_dir}",
                    )
                    # Symlink from session log dir for discoverability
                    symlink_path = log_session_dir / "subagents"
                    try:
                        if symlink_path.is_symlink():
                            symlink_path.unlink()
                        symlink_path.symlink_to(subagent_entries_dir)
                    except OSError as e:
                        logger.warning(
                            f"[Orchestrator] Could not create subagent logs symlink: {e}",
                        )

                    # Create delegation directory for file-based container-to-host launch
                    self._delegation_dir = self._subagent_logs_dir / "_delegation"
                    self._delegation_dir.mkdir(parents=True, exist_ok=True)
                    logger.info(
                        f"[Orchestrator] Created delegation directory: {self._delegation_dir}",
                    )
            except Exception as e:
                logger.warning(f"[Orchestrator] Could not create subagent logs directory: {e}")

        def _setup_agent_orchestration(agent_id: str, agent) -> None:
            """Setup orchestration paths for a single agent (can run in parallel)."""
            if not agent.backend.filesystem_manager:
                return

            # Add Docker mount for subagent logs directory if needed
            if self._subagent_logs_dir is not None:
                fm = agent.backend.filesystem_manager
                if hasattr(fm, "docker_manager") and fm.docker_manager is not None:
                    resolved = str(self._subagent_logs_dir.resolve())
                    fm.docker_manager.additional_mounts[resolved] = {
                        "bind": resolved,
                        "mode": "rw",
                    }
                    logger.info(
                        f"[Orchestrator] Added Docker mount for subagent logs: {resolved}",
                    )
                    # Also mount delegation directory for file-based container-to-host launch
                    if self._delegation_dir is not None:
                        del_resolved = str(self._delegation_dir.resolve())
                        fm.docker_manager.additional_mounts[del_resolved] = {
                            "bind": del_resolved,
                            "mode": "rw",
                        }
                        logger.info(
                            f"[Orchestrator] Added Docker mount for delegation dir: {del_resolved}",
                        )

            workspace_token = self.coordination_tracker.get_path_token(agent_id)
            agent.backend.filesystem_manager.setup_orchestration_paths(
                agent_id=agent_id,
                snapshot_storage=self._snapshot_storage,
                agent_temporary_workspace=self._agent_temporary_workspace,
                skills_directory=skills_directory,
                massgen_skills=massgen_skills,
                load_previous_session_skills=load_previous_session_skills,
                workspace_token=workspace_token,
            )
            # Setup workspace directories for massgen skills
            if hasattr(self.config, "coordination_config") and hasattr(
                self.config.coordination_config,
                "massgen_skills",
            ):
                if self.config.coordination_config.massgen_skills:
                    agent.backend.filesystem_manager.setup_massgen_skill_directories(
                        massgen_skills=self.config.coordination_config.massgen_skills,
                    )
            # Setup memory directories if memory filesystem mode is enabled
            if hasattr(self.config, "coordination_config") and hasattr(
                self.config.coordination_config,
                "enable_memory_filesystem_mode",
            ):
                if self.config.coordination_config.enable_memory_filesystem_mode:
                    agent.backend.filesystem_manager.setup_memory_directories()

                    # Restore memories from previous turn if available
                    if self._previous_turns:
                        previous_turn = self._previous_turns[-1]  # Get most recent turn
                        if "log_dir" in previous_turn:
                            from pathlib import Path as PathlibPath

                            prev_log_dir = PathlibPath(previous_turn["log_dir"])
                            # Look for final workspace from previous turn
                            prev_final_workspace = prev_log_dir / "final"
                            if prev_final_workspace.exists():
                                # Find the winning agent's workspace from previous turn
                                for agent_dir in prev_final_workspace.iterdir():
                                    if agent_dir.is_dir():
                                        prev_workspace = agent_dir / "workspace"
                                        if prev_workspace.exists():
                                            logger.info(
                                                f"[Orchestrator] Restoring memories from previous turn: {prev_workspace}",
                                            )
                                            agent.backend.filesystem_manager.restore_memories_from_previous_turn(
                                                prev_workspace,
                                            )
                                            break  # Only restore from one agent (the winner)

            # Update MCP config with agent_id for Docker mode (must be after setup_orchestration_paths)
            agent.backend.filesystem_manager.update_backend_mcp_config(
                agent.backend.config,
            )

        # Setup orchestration paths for all agents in parallel (Docker container creation is I/O bound)
        if len(self.agents) > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(self.agents)) as executor:
                futures = {executor.submit(_setup_agent_orchestration, agent_id, agent): agent_id for agent_id, agent in self.agents.items()}
                for future in concurrent.futures.as_completed(futures):
                    agent_id = futures[future]
                    try:
                        future.result()
                    except Exception as e:
                        logger.error(f"[Orchestrator] Failed to setup orchestration for {agent_id}: {e}")
                        raise
        else:
            # Single agent - no need for threading overhead
            for agent_id, agent in self.agents.items():
                _setup_agent_orchestration(agent_id, agent)

        # Create workspace symlinks in the log directory for easy inspection
        self.ensure_workspace_symlinks()

        # Initialize broadcast channel for agent-to-agent communication
        self.broadcast_channel = BroadcastChannel(self)
        logger.info("[Orchestrator] Broadcast channel initialized")

        # Set orchestrator reference on all agents
        for agent_id, agent in self.agents.items():
            if hasattr(agent, "_orchestrator"):
                agent._orchestrator = self
                logger.debug(
                    f"[Orchestrator] Set orchestrator reference on agent: {agent_id}",
                )

        # Validate and setup skills if enabled
        if hasattr(self.config, "coordination_config") and hasattr(
            self.config.coordination_config,
            "use_skills",
        ):
            if self.config.coordination_config.use_skills:
                logger.info("[Orchestrator] Skills enabled, validating configuration")
                self._validate_skills_config()
                logger.info("[Orchestrator] Skills validation complete")

        # Inject planning tools if enabled
        if hasattr(self.config, "coordination_config") and hasattr(
            self.config.coordination_config,
            "enable_agent_task_planning",
        ):
            if self.config.coordination_config.enable_agent_task_planning:
                logger.info(
                    f"[Orchestrator] Injecting planning tools for {len(self.agents)} agents",
                )
                self._inject_planning_tools_for_all_agents()
                logger.info("[Orchestrator] Planning tools injection complete")

        # Inject subagent tools if enabled
        if hasattr(self.config, "coordination_config") and hasattr(
            self.config.coordination_config,
            "enable_subagents",
        ):
            if self.config.coordination_config.enable_subagents:
                logger.info(
                    f"[Orchestrator] Injecting subagent tools for {len(self.agents)} agents",
                )
                self._inject_subagent_tools_for_all_agents()
                logger.info("[Orchestrator] Subagent tools injection complete")

        # Set compression target ratio on all agent backends
        if hasattr(self.config, "coordination_config") and hasattr(
            self.config.coordination_config,
            "compression_target_ratio",
        ):
            compression_ratio = self.config.coordination_config.compression_target_ratio
            for agent_id, agent in self.agents.items():
                if hasattr(agent, "backend") and agent.backend:
                    agent.backend._compression_target_ratio = compression_ratio
            logger.info(
                f"[Orchestrator] Set compression_target_ratio={compression_ratio} on {len(self.agents)} agent backends",
            )

        # NLIP Configuration
        self.enable_nlip = enable_nlip
        self.nlip_config = nlip_config or {}

        # Initialize NLIP routers for agents if enabled
        if self.enable_nlip:
            self._init_nlip_routing()

        # Initialize broadcast tools (independent of NLIP)
        self._init_broadcast_tools()

        # Initialize checklist MCP tool if using tool-gated mode
        self._init_checklist_tool()

        # Initialize checkpoint MCP tool if main agent is set
        self._init_checkpoint_tool()

        self._seed_plan_execution_workspaces(context="orchestrator_init")

    def _seed_plan_execution_workspaces(self, context: str) -> None:
        """Seed execute-mode plan or spec artifacts into agent workspaces."""
        if not self._plan_session_id:
            return

        try:
            from .plan_storage import PlanSession

            plan_session = PlanSession(self._plan_session_id)

            # Check artifact type to route to plan or spec workspace seeding
            try:
                _metadata = plan_session.load_metadata()
                _artifact_type = getattr(_metadata, "artifact_type", "plan")
            except Exception:
                logger.opt(exception=True).warning(
                    f"[Orchestrator] Could not load artifact_type from metadata for " f"plan_session={self._plan_session_id}; defaulting to 'plan'. " f"This may cause incorrect workspace seeding.",
                )
                _artifact_type = "plan"

            if _artifact_type == "spec":
                from .plan_execution import setup_agent_workspaces_for_spec_execution

                item_count = setup_agent_workspaces_for_spec_execution(
                    self.agents,
                    plan_session,
                )
                item_label = "requirements"
            else:
                from .plan_execution import setup_agent_workspaces_for_execution

                item_count = setup_agent_workspaces_for_execution(
                    self.agents,
                    plan_session,
                )
                item_label = "tasks"

            if item_count > 0:
                logger.info(
                    "[Orchestrator] Seeded plan execution workspace (%s, plan_session=%s, %s=%d)",
                    context,
                    self._plan_session_id,
                    item_label,
                    item_count,
                )
            else:
                logger.warning(
                    "[Orchestrator] Plan execution workspace seed produced no %s (%s, plan_session=%s)",
                    item_label,
                    context,
                    self._plan_session_id,
                )
        except Exception:
            logger.exception(
                "[Orchestrator] Failed to seed plan execution workspace (%s, plan_session=%s)",
                context,
                self._plan_session_id,
            )

    def _get_decomposition_criteria_for_agent(self, agent_id: str | None) -> list | None:
        """Return decomposition execution criteria for one agent when available."""
        if not agent_id or not self._is_decomposition_mode():
            return None

        explicit = self._agent_subtask_criteria.get(agent_id)
        if explicit:
            return explicit

        subtask = self._agent_subtasks.get(agent_id)
        if not subtask:
            return None

        from massgen.evaluation_criteria_generator import (
            build_decomposition_execution_criteria,
        )

        return build_decomposition_execution_criteria(subtask)

    def _get_active_criteria(
        self,
        agent_id: str | None = None,
    ) -> tuple[list[str] | None, dict[str, str] | None, dict[str, str] | None, dict[str, list[str]] | None, dict[str, dict[str, str]] | None]:
        """Return (items, categories, verify_by, anti_patterns, score_anchors) using the criteria priority waterfall.

        Priority: inline > decomposition-agent > generated > preset > None.
        Returns (None, None, None, None, None) when no custom criteria source is configured.
        This is used by both _init_checklist_tool and the system prompt builder
        to ensure criteria are consistent across the checklist MCP tool and
        the system prompt shown to the model.
        """

        def _to_tuple(criteria: list) -> tuple[list[str], dict[str, str], dict[str, str] | None, dict[str, list[str]] | None, dict[str, dict[str, str]] | None]:
            texts = [c.text for c in criteria]
            cats = {c.id: c.category for c in criteria}
            vby = {c.id: c.verify_by for c in criteria if c.verify_by}
            anti = {c.id: c.anti_patterns for c in criteria if getattr(c, "anti_patterns", None)}
            anchors = {c.id: c.score_anchors for c in criteria if getattr(c, "score_anchors", None)}
            return texts, cats, vby or None, anti or None, anchors or None

        inline = getattr(
            getattr(self.config, "coordination_config", None),
            "checklist_criteria_inline",
            None,
        )
        if inline:
            from massgen.evaluation_criteria_generator import criteria_from_inline

            return _to_tuple(criteria_from_inline(inline))

        decomposition_criteria = self._get_decomposition_criteria_for_agent(agent_id)
        if decomposition_criteria is not None:
            return _to_tuple(decomposition_criteria)

        if self._generated_evaluation_criteria is not None:
            return _to_tuple(self._generated_evaluation_criteria)

        preset = getattr(
            getattr(self.config, "coordination_config", None),
            "checklist_criteria_preset",
            None,
        )
        if preset:
            from massgen.evaluation_criteria_generator import get_criteria_for_preset

            return _to_tuple(get_criteria_for_preset(preset))

        return None, None, None, None, None

    def _resolve_effective_checklist_criteria(
        self,
        agent_id: str | None = None,
    ) -> tuple[list[str], dict[str, str], dict[str, str] | None, str, dict[str, list[str]] | None, dict[str, dict[str, str]] | None]:
        """Return checklist criteria with changedoc/generic fallback plus source.

        Returns:
            (items, categories, verify_by, source, anti_patterns, score_anchors)
        """
        from massgen.system_prompt_sections import (
            _CHECKLIST_ITEM_ANTI_PATTERNS,
            _CHECKLIST_ITEM_ANTI_PATTERNS_CHANGEDOC,
            _CHECKLIST_ITEM_CATEGORIES,
            _CHECKLIST_ITEM_CATEGORIES_CHANGEDOC,
            _CHECKLIST_ITEM_SCORE_ANCHORS,
            _CHECKLIST_ITEM_SCORE_ANCHORS_CHANGEDOC,
            _CHECKLIST_ITEMS,
            _CHECKLIST_ITEMS_CHANGEDOC,
        )

        custom_items, item_categories, item_verify_by, item_anti_patterns, item_score_anchors = self._get_active_criteria(agent_id)
        if custom_items is not None:
            inline = getattr(
                getattr(self.config, "coordination_config", None),
                "checklist_criteria_inline",
                None,
            )
            if inline:
                source = "inline"
            elif agent_id and self._get_decomposition_criteria_for_agent(agent_id) is not None:
                source = "decomposition_subtask"
            elif self._generated_evaluation_criteria is not None:
                source = "generated"
            else:
                source = "preset"
            return custom_items, item_categories or {}, item_verify_by, source, item_anti_patterns, item_score_anchors

        if self._is_changedoc_enabled():
            return (
                list(_CHECKLIST_ITEMS_CHANGEDOC),
                dict(_CHECKLIST_ITEM_CATEGORIES_CHANGEDOC),
                None,
                "changedoc",
                dict(_CHECKLIST_ITEM_ANTI_PATTERNS_CHANGEDOC),
                dict(_CHECKLIST_ITEM_SCORE_ANCHORS_CHANGEDOC),
            )

        return (
            list(_CHECKLIST_ITEMS),
            dict(_CHECKLIST_ITEM_CATEGORIES),
            None,
            "generic",
            dict(_CHECKLIST_ITEM_ANTI_PATTERNS),
            dict(_CHECKLIST_ITEM_SCORE_ANCHORS),
        )

    def _push_cached_criteria_to_display(self, *, force: bool = False) -> None:
        """Push cached evaluation criteria to the active display when available."""
        if getattr(self, "_criteria_pushed_to_display", False) and not force:
            return

        payload = getattr(self, "_criteria_display_payload", None)
        if not payload:
            return

        try:
            _emitter = get_event_emitter()
            if _emitter:
                _emitter.emit_raw(
                    StructuredEventType.EVALUATION_CRITERIA_SET,
                    criteria=payload["criteria"],
                    source=payload["source"],
                )
            display = getattr(self.coordination_ui, "display", None) if self.coordination_ui else None
            if display and hasattr(display, "set_evaluation_criteria"):
                display.set_evaluation_criteria(payload["criteria"], source=payload["source"])
                self._criteria_pushed_to_display = True
        except Exception:
            pass  # TUI notification is non-critical

    def _init_checklist_tool(self) -> None:
        """Register submit_checklist MCP tool if voting_sensitivity is checklist_gated.

        SDK-capable backends (ClaudeCode) get an in-process SDK MCP server.
        CLI-based backends (Codex) get state stored on the backend; the backend
        writes a stdio MCP server config at execution time when the workspace
        path is known.
        """
        sensitivity = getattr(self.config, "voting_sensitivity", "")
        if sensitivity != "checklist_gated":
            return

        from massgen.system_prompt_sections import (
            _checklist_confidence_cutoff,
            _checklist_effective_threshold,
            _checklist_required_true,
        )

        tracker = getattr(self, "coordination_tracker", None)
        display_payload: dict[str, Any] | None = None

        for agent_id, agent in self.agents.items():
            backend = agent.backend
            criteria_agent_id = agent_id if self._is_decomposition_mode() else None
            items, item_categories, item_verify_by, criteria_source, _anti, item_score_anchors = self._resolve_effective_checklist_criteria(
                criteria_agent_id,
            )

            logger.info(
                "[Orchestrator._init_checklist_tool] Agent %s criteria source: %s, count: %d",
                agent_id,
                criteria_source,
                len(items),
            )
            for i, item_text in enumerate(items):
                cat = item_categories.get(f"E{i + 1}", "unknown")
                logger.info(
                    "[Orchestrator._init_checklist_tool]   %s E%d (%s): %s",
                    agent_id,
                    i + 1,
                    cat,
                    item_text[:120],
                )

            if display_payload is None:
                criteria_dicts = [
                    {
                        "id": f"E{i + 1}",
                        "text": text,
                        "category": item_categories.get(f"E{i + 1}", "standard"),
                        "verify_by": (item_verify_by or {}).get(f"E{i + 1}"),
                    }
                    for i, text in enumerate(items)
                ]
                display_payload = {
                    "criteria": criteria_dicts,
                    "source": criteria_source,
                }

            # Create mutable state dict — orchestrator updates before each round
            threshold = getattr(self.config, "voting_threshold", 5) or 5
            total = self.config.max_new_answers_per_agent or 5
            remaining = total
            effective_t = _checklist_effective_threshold(threshold, remaining, total)
            # Determine active subagent types for novelty gating
            from massgen.subagent.type_scanner import DEFAULT_SUBAGENT_TYPES

            _active_subagent_types = getattr(
                getattr(self.config, "coordination_config", None),
                "subagent_types",
                None,
            )
            if _active_subagent_types is None:
                _active_subagent_types = DEFAULT_SUBAGENT_TYPES
            _lowered_types = {t.lower() for t in _active_subagent_types}

            checklist_state = {
                "threshold": threshold,
                "remaining": remaining,
                "total": total,
                "terminate_action": "stop" if self._is_decomposition_mode() else "vote",
                "iterate_action": "new_answer",
                "decomposition_mode": self._is_decomposition_mode(),
                "has_existing_answers": False,  # True once any answer exists for this agent
                "require_gap_report": bool(
                    getattr(self.config, "checklist_require_gap_report", True),
                ),
                "require_diagnostic_report": bool(
                    getattr(self.config, "checklist_require_gap_report", True),
                ),
                "checklist_first_answer": bool(
                    getattr(self.config, "checklist_first_answer", False),
                ),
                "max_checklist_calls_per_round": int(
                    getattr(self.config, "max_checklist_calls_per_round", 1) or 1,
                ),
                "checklist_calls_this_round": 0,
                "checklist_history": [],
                # Needed by checklist server to interpret item semantics.
                "changedoc_mode": self._is_changedoc_enabled(),
                "workspace_path": getattr(
                    getattr(backend, "filesystem_manager", None),
                    "cwd",
                    None,
                ),
                # Pre-computed so stdio server doesn't need massgen imports
                "required": _checklist_required_true(effective_t, num_items=len(items)),
                "cutoff": _checklist_confidence_cutoff(effective_t),
                # E-prefix for evaluation items (replaces legacy T-prefix)
                "item_prefix": "E",
                # Latest injected labels that must be re-scored before improvements can be proposed.
                "pending_checklist_recheck_labels": [],
                # Dynamic core/stretch categories for convergence off-ramp
                "item_categories": item_categories,
                "item_verify_by": item_verify_by or {},
                "item_score_anchors": item_score_anchors or {},
                "criteria_source": criteria_source,
                # Novelty subagent guidance only when novelty type is available
                "novelty_subagent_enabled": "novelty" in _lowered_types,
                # Critic subagent guidance only when critic type is available
                "critic_subagent_enabled": "critic" in _lowered_types,
                # Builder subagent guidance only when builder type is available
                "builder_subagent_enabled": "builder" in _lowered_types,
                # Regression guard: agent-initiated blind comparison before committing
                "regression_guard_subagent_enabled": "regression_guard" in _lowered_types,
                # Quality rethinking subagent: per-element craft improvements
                "quality_rethinking_subagent_enabled": "quality_rethinking" in _lowered_types,
                # Planning injection dir for auto-populating task plan from draft_approach
                "planning_injection_dir": str(getattr(self, "_planning_injection_dirs", {}).get(agent_id, "")),
                # Whether subagents are enabled (for delegation guidance in draft_approach message)
                "subagents_enabled": bool(
                    hasattr(self.config, "coordination_config") and hasattr(self.config.coordination_config, "enable_subagents") and self.config.coordination_config.enable_subagents,
                ),
                # Post-evaluator task mode: once round_evaluator has already
                # injected next tasks, the parent should skip checklist loops.
                "round_evaluator_auto_injected": False,
                "round_evaluator_primary_artifact_path": "",
                "round_evaluator_verdict_artifact_path": "",
                "round_evaluator_next_tasks_artifact_path": "",
                "round_evaluator_objective": "",
                "round_evaluator_primary_strategy": "",
                "round_evaluator_why_this_strategy": "",
                "round_evaluator_strategy_mode": "",
                "round_evaluator_incremental_override_reason": "",
                "round_evaluator_success_contract": {},
                "round_evaluator_deprioritize_or_remove": [],
                "allowed_external_report_paths": [],
                "agent_answer_count": (len(tracker.answers_by_agent.get(agent_id, [])) if tracker is not None and hasattr(tracker, "answers_by_agent") else 0),
                "current_answer_label": (tracker.get_latest_answer_label(agent_id) if tracker is not None else None),
                "enable_quality_rethink_on_iteration": bool(
                    getattr(
                        getattr(self.config, "coordination_config", None),
                        "enable_quality_rethink_on_iteration",
                        False,
                    ),
                ),
                "enable_novelty_on_iteration": bool(
                    getattr(
                        getattr(self.config, "coordination_config", None),
                        "enable_novelty_on_iteration",
                        False,
                    ),
                ),
                # Evaluator personas config (opt-in)
                "evaluator_team_size": self._get_evaluator_team_size(),
                "enable_evaluator_personas": bool(
                    getattr(
                        getattr(self.config, "coordination_config", None),
                        "enable_evaluator_personas",
                        False,
                    ),
                ),
                # Impact gate config for draft_approach validation
                "improvements": dict(
                    getattr(
                        getattr(self.config, "coordination_config", None),
                        "improvements",
                        {},
                    )
                    or {},
                ),
            }
            resolved_items = list(items)
            backend._checklist_state = checklist_state
            backend._checklist_items = resolved_items

            if getattr(backend, "supports_sdk_mcp", False):
                # SDK path: in-process MCP server (ClaudeCode)
                self._init_checklist_tool_sdk(
                    agent_id,
                    backend,
                    checklist_state,
                    resolved_items,
                )
            else:
                # Stdio path for backends with standard MCP infrastructure.
                # Write specs and register stdio MCP so the agent gets submit_checklist.
                if hasattr(backend, "mcp_servers"):
                    self._init_checklist_tool_stdio(agent_id, backend, checklist_state, resolved_items)
                else:
                    # Codex-like backends handle their own config writing.
                    logger.info(
                        f"[Orchestrator] Checklist tool for agent {agent_id}: " f"stdio mode (specs written at execution time)",
                    )

        if display_payload:
            self._criteria_display_payload = display_payload
            self._push_cached_criteria_to_display(force=True)

    def _init_checklist_tool_sdk(
        self,
        agent_id,
        backend,
        checklist_state,
        checklist_items,
    ) -> None:
        """Register checklist tool as an in-process SDK MCP server."""
        try:
            from claude_agent_sdk import create_sdk_mcp_server, tool
        except ImportError:
            logger.warning("claude-agent-sdk not available, checklist tool will not be registered")
            return

        from .mcp_tools.checklist_tools_server import (
            build_round_evaluator_task_mode_redirect,
            evaluate_checklist_submission,
            evaluate_draft_approach,
        )

        # Define tool schema — each score entry requires a reasoning string
        # to force the model to justify every item.
        _all_agent_ids = sorted(self.agents.keys())
        _is_decomposition = self._is_decomposition_mode()
        _is_multi_agent = len(_all_agent_ids) > 1 and not _is_decomposition
        if _is_multi_agent:
            _num_agents = len(_all_agent_ids)
            _anon_ids = [f"agent{i + 1}" for i in range(_num_agents)]
            _scores_desc = (
                "Your confidence scores with reasoning for each checklist item. "
                f"This session has {_num_agents} agents. "
                "Use per-agent format where keys are the most recent answer label "
                'for each agent (labels look like "agent1.1", "agent2.1", '
                '"agent1.2", etc. — if an agent updated their answer, use the '
                'latest label, e.g., "agent1.2" not "agent1.1"). '
                "Example keys for this session: " + ", ".join(f'"{aid}.1"' for aid in _anon_ids) + ". "
                "Score ALL agents whose answers you have seen. "
                "Each agent entry maps criterion IDs to "
                '{"score": N, "reasoning": "..."} objects.'
            )
        else:
            if _is_decomposition:
                _scores_desc = (
                    "Your confidence scores with reasoning for each checklist item for your current subtask output. "
                    "Use flat format: "
                    '{"E1": {"score": N, "reasoning": "..."}, ...}. '
                    "You may use peer answers as evidence, but score your own current work rather than ranking all agents."
                )
            else:
                _scores_desc = "Your confidence scores with reasoning for each checklist item. " "Use flat format: " '{"E1": {"score": N, "reasoning": "..."}, ...}.'
        input_schema = {
            "type": "object",
            "properties": {
                "scores": {
                    "type": "object",
                    "description": _scores_desc,
                    "additionalProperties": True,
                },
                "report_path": {
                    "type": "string",
                    "description": ("Path to the markdown gap report in the workspace. " "Required when checklist report gating is enabled."),
                },
            },
            "required": ["scores"],
        }

        # draft_approach input schema
        propose_schema = {
            "type": "object",
            "properties": {
                "vision": {
                    "type": "string",
                    "description": (
                        "Optional north star: what the ideal output would look " "like, independent of existing answers. Guides execution " "toward excellence rather than incremental fixes."
                    ),
                },
                "plan": {
                    "type": "object",
                    "description": (
                        "Map of criterion ID to list of entries describing what "
                        "to build. Each entry has 'plan' (what to do) and 'sources' "
                        "(which existing answers to draw from, or 'fresh' for new "
                        "ideas). Must cover ALL failing criteria."
                    ),
                    "additionalProperties": {
                        "type": "array",
                        "items": {
                            "oneOf": [
                                {"type": "string"},
                                {
                                    "type": "object",
                                    "properties": {
                                        "plan": {"type": "string"},
                                        "sources": {"type": "array", "items": {"type": "string"}},
                                    },
                                },
                            ],
                        },
                    },
                },
                "preserve": {
                    "type": "object",
                    "description": (
                        "Optional: specific elements from existing answers worth "
                        "bringing forward. Each entry has 'what' (strength to keep) "
                        "and 'source' (which answer). Can be empty when building fresh."
                    ),
                    "additionalProperties": {
                        "oneOf": [
                            {"type": "string"},
                            {
                                "type": "object",
                                "properties": {
                                    "what": {"type": "string"},
                                    "source": {"type": "string"},
                                },
                            },
                        ],
                    },
                },
            },
            "required": ["plan"],
        }

        # Create tool function with closure over mutable state
        state = checklist_state
        items = checklist_items

        # Capture orchestrator ref and agent_id for convergence tracking
        _orchestrator = self
        _agent_id = agent_id

        # Track last failed criteria for draft_approach validation
        _last_checklist_result: dict[str, Any] = {
            "status": "none",
            "verdict": None,
            "failed_criteria": [],
            "items": [],
            "all_criteria_ids": [],
            "failing_criteria_detail": [],
            "plateaued_criteria": [],
            "checklist_explanation": "",
            "diagnostic_report_path": "",
            "diagnostic_report_artifact_paths": [],
        }

        @tool(
            name="submit_checklist",
            description=(
                (
                    "Submit your checklist evaluation for your current subtask output. "
                    'Use flat scores like {"E1": {"score": 8, "reasoning": "..."}, ...}. '
                    "Each score entry needs 'score' (0-10) and 'reasoning'. "
                    "Use 'report_path' to pass a markdown gap report when required."
                )
                if _is_decomposition
                else (
                    "Submit your checklist evaluation. When multiple agents exist, "
                    "scores must use per-agent format: "
                    '{"agent1.1": {"E1": {"score": 8, "reasoning": "..."}, ...}, '
                    '"agent2.1": {...}}. '
                    "Each score entry needs 'score' (0-10) and 'reasoning'. "
                    "Use 'report_path' to pass a markdown gap report when required."
                )
            ),
            input_schema=input_schema,
        )
        async def submit_checklist_handler(args, _state=state):
            import json as _json

            agent_state = _orchestrator.agent_states.get(_agent_id)
            max_calls = getattr(_orchestrator.config, "max_checklist_calls_per_round", 1)
            checklist_first_answer = getattr(_orchestrator.config, "checklist_first_answer", False)
            redirect_message = build_round_evaluator_task_mode_redirect(_state)
            if redirect_message:
                return {
                    "content": [{"type": "text", "text": redirect_message}],
                    "isError": True,
                }
            raw_scores = args.get("scores", {})
            submitted_agent_labels = _orchestrator._extract_submitted_agent_labels(raw_scores)
            state_for_eval = _state
            using_recheck_exception = False

            # Block on first answer unless explicitly opted in — no prior answers to compare
            if not checklist_first_answer and agent_state is not None and agent_state.answer_count == 0:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "submit_checklist is not available before your first answer is submitted. "
                                "Build your initial answer, verify it, then call the `new_answer` workflow tool. "
                                "Checklist evaluation begins from round 2."
                            ),
                        },
                    ],
                    "isError": True,
                }

            # Block repeat calls after a new_answer verdict has already been issued this round
            if agent_state is not None and agent_state.checklist_calls_this_round >= max_calls:
                pending_recheck_labels = set(getattr(agent_state, "pending_checklist_recheck_labels", set()) or set())
                if not pending_recheck_labels:
                    blocked_msg = (
                        f"submit_checklist already called {agent_state.checklist_calls_this_round} time(s) "
                        f"this round (max: {max_calls}). You already have your improvement plan. "
                        "Implement your improvements, then verify the integrated result "
                        "(screenshots, file checks, confirming changes landed correctly), "
                        "then call the `new_answer` workflow tool "
                        "to submit your completed work. Do not call `submit_checklist` again."
                    )
                    return {
                        "content": [{"type": "text", "text": blocked_msg}],
                        "isError": True,
                    }

                # Injection exception: allow one post-injection recheck. Prefer delta-only labels,
                # but allow full latest context labels for model robustness.
                using_recheck_exception = True
                available_labels = set(_state.get("available_agent_labels") or [])
                is_decomposition = bool(_state.get("decomposition_mode", False))
                submitted_covers_full = is_decomposition or (bool(submitted_agent_labels) and (not available_labels or available_labels.issubset(submitted_agent_labels)))
                submitted_covers_delta = is_decomposition or (bool(submitted_agent_labels) and pending_recheck_labels.issubset(submitted_agent_labels))
                if submitted_covers_delta and not submitted_covers_full and not is_decomposition:
                    state_for_eval = dict(_state)
                    state_for_eval["available_agent_labels"] = sorted(pending_recheck_labels)

            result = evaluate_checklist_submission(
                scores=raw_scores,
                report_path=args.get("report_path", ""),
                items=items,
                state=state_for_eval,
                checklist_history=agent_state.checklist_history if agent_state else None,
            )
            result_status = str(
                result.get("status", "accepted" if result.get("verdict") else "validation_error"),
            )
            report_data = result.get("report") if isinstance(result.get("report"), dict) else {}
            resolved_path = str(report_data.get("resolved_path") or "")
            fallback_path = str(report_data.get("path") or "")
            _last_checklist_result["status"] = result_status
            _last_checklist_result["verdict"] = result.get("verdict")
            _last_checklist_result["failed_criteria"] = result.get("failed_criteria", [])
            _last_checklist_result["items"] = list(items)
            _last_checklist_result["all_criteria_ids"] = [f"E{i+1}" for i in range(len(items))]
            _last_checklist_result["failing_criteria_detail"] = list(result.get("failing_criteria_detail", []))
            _last_checklist_result["plateaued_criteria"] = list(result.get("plateaued_criteria", []))
            _last_checklist_result["checklist_explanation"] = str(result.get("explanation", ""))
            _last_checklist_result["diagnostic_report_path"] = resolved_path or fallback_path
            _last_checklist_result["diagnostic_report_artifact_paths"] = list(report_data.get("artifact_paths", []))

            # Only accepted checklist submissions should consume this round's quota.
            # Validation failures (incomplete/malformed payloads or gated rejections)
            # must allow the agent to resubmit within the same round.
            submission_has_validation_error = bool(
                (result_status != "accepted") or result.get("error") or result.get("incomplete_scores") or result.get("report_gate_triggered"),
            )

            # Store accepted checklist results for convergence detection and increment call counter.
            if agent_state is not None and not submission_has_validation_error:
                agent_state.checklist_history.append(
                    {
                        "verdict": result.get("verdict"),
                        "true_count": result.get("true_count"),
                        "total_score": sum(d["score"] for d in result.get("items", [])),
                        "items_detail": result.get("items", []),
                    },
                )
                agent_state.checklist_calls_this_round += 1
                if getattr(agent_state, "pending_checklist_recheck_labels", set()) and (
                    bool(_state.get("decomposition_mode", False)) or (submitted_agent_labels and getattr(agent_state, "pending_checklist_recheck_labels", set()).issubset(submitted_agent_labels))
                ):
                    setattr(agent_state, "pending_checklist_recheck_labels", set())
                elif using_recheck_exception and getattr(agent_state, "pending_checklist_recheck_labels", set()):
                    setattr(agent_state, "pending_checklist_recheck_labels", set())

            # When verdict is new_answer, append explicit next-step guidance so the agent
            # implements improvements and submits via the workflow tool rather than looping
            # back to submit_checklist.
            iterate_action = _state.get("iterate_action", "new_answer")
            if result_status == "accepted" and result.get("verdict") == iterate_action:
                result = dict(result)
                result["explanation"] = (
                    result.get("explanation", "") + " NEXT: Call `draft_approach` with specific improvements for each " "failing criterion. Then implement your plan and call `new_answer`."
                )

            return {
                "content": [
                    {
                        "type": "text",
                        "text": _json.dumps(result),
                    },
                ],
            }

        @tool(
            name="draft_approach",
            description=(
                "Propose what to build for your next answer. "
                "Must be called after submit_checklist returns an iterate verdict. "
                "Pass 'plan' mapping criterion IDs to lists of entries "
                "with 'plan' (what to do) and 'sources' (which answers to draw "
                "from, or 'fresh' for new ideas). Optionally pass 'preserve' for "
                "elements worth keeping from existing answers."
            ),
            input_schema=propose_schema,
        )
        async def draft_approach_handler(args, _state=state):
            import json as _json

            redirect_message = build_round_evaluator_task_mode_redirect(_state)
            if redirect_message:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": _json.dumps({"valid": False, "error": redirect_message}),
                        },
                    ],
                }
            iterate_action = _state.get("iterate_action", "new_answer")
            last_status = str(_last_checklist_result.get("status", "none"))
            last_verdict = _last_checklist_result.get("verdict")
            agent_state = _orchestrator.agent_states.get(_agent_id)
            if last_status != "accepted":
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": _json.dumps(
                                {
                                    "valid": False,
                                    "error": ("draft_approach is unavailable because your latest " "submit_checklist result was a validation error. " "Fix and resubmit submit_checklist first."),
                                },
                            ),
                        },
                    ],
                }
            if last_verdict != iterate_action:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": _json.dumps(
                                {
                                    "valid": False,
                                    "error": ("draft_approach is only available after " f"submit_checklist returns an iterate verdict ({iterate_action})."),
                                },
                            ),
                        },
                    ],
                }
            pending_recheck_labels = set(getattr(agent_state, "pending_checklist_recheck_labels", set()) or set())
            if pending_recheck_labels:
                pending_labels_text = ", ".join(sorted(pending_recheck_labels))
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": _json.dumps(
                                {
                                    "valid": False,
                                    "error": (
                                        "draft_approach is unavailable because newer injected answer labels "
                                        f"still require checklist re-evaluation: {pending_labels_text}. "
                                        "Re-run submit_checklist on the newest labels first."
                                    ),
                                },
                            ),
                        },
                    ],
                }

            # Accept both "plan" (new) and "improvements" (legacy fallback)
            improvements = args.get("plan") or args.get("improvements", {})
            preserve = args.get("preserve")
            vision = args.get("vision")
            result = evaluate_draft_approach(
                improvements=improvements,
                failed_criteria=_last_checklist_result["failed_criteria"],
                items=_last_checklist_result["items"] or list(items),
                all_criteria_ids=_last_checklist_result.get("all_criteria_ids"),
                preserve=preserve,
                state=_state,
                latest_evaluation={
                    "failed_criteria": _last_checklist_result.get("failed_criteria", []),
                    "failing_criteria_detail": _last_checklist_result.get("failing_criteria_detail", []),
                    "plateaued_criteria": _last_checklist_result.get("plateaued_criteria", []),
                    "checklist_explanation": _last_checklist_result.get("checklist_explanation", ""),
                    "diagnostic_report_path": _last_checklist_result.get("diagnostic_report_path", ""),
                    "diagnostic_report_artifact_paths": _last_checklist_result.get("diagnostic_report_artifact_paths", []),
                },
                vision=vision,
            )
            if result.get("valid"):
                _orchestrator._write_planning_injection(_agent_id, result["task_plan"])
                result = dict(result)  # Don't mutate original
                task_count = len(result["task_plan"])
                result["message"] = (
                    f"Your task plan has been pre-populated with {task_count} items. "
                    "Call get_task_plan to see the list and start executing. "
                    "Preserve items are guardrails — verify after implementing. "
                    "Do not skip criteria."
                )
                # Append subagent delegation hint if subagents are enabled
                _subagents_enabled = (
                    hasattr(_orchestrator.config, "coordination_config")
                    and hasattr(_orchestrator.config.coordination_config, "enable_subagents")
                    and _orchestrator.config.coordination_config.enable_subagents
                )
                if _subagents_enabled:
                    result["message"] += (
                        " Review the pre-populated plan for subagent delegation"
                        " opportunities. Tasks without mutual dependencies can be"
                        " spawned as parallel background subagents. Mark tasks"
                        " with execution.mode='delegate' plus subagent_type/subagent_id,"
                        " then spawn."
                    )
            return {
                "content": [
                    {
                        "type": "text",
                        "text": _json.dumps(result),
                    },
                ],
            }

        # --- set_evaluator_personas tool (opt-in via enable_evaluator_personas) ---
        _coord_cfg = getattr(self.config, "coordination_config", None)
        _personas_enabled = bool(
            _coord_cfg and getattr(_coord_cfg, "enable_evaluator_personas", False),
        )

        _personas_tool = None
        if _personas_enabled:
            set_personas_schema = {
                "type": "object",
                "properties": {
                    "personas": {
                        "type": "array",
                        "description": ("List of evaluator personas. Each persona configures " "one evaluator subagent's critique focus for the next round. " "Count must match evaluator team size."),
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {
                                    "type": "string",
                                    "description": "Short descriptive name for this evaluator persona.",
                                },
                                "instructions": {
                                    "type": "string",
                                    "description": "System prompt instructions shaping this evaluator's critique lens.",
                                },
                            },
                            "required": ["label", "instructions"],
                        },
                    },
                },
                "required": ["personas"],
            }

            @tool(
                name="set_evaluator_personas",
                description=(
                    "Configure distinct evaluation lenses for round evaluator subagents. "
                    "Call before new_answer to shape how evaluators critique your next submission. "
                    "Each persona defines a unique focus area for one evaluator."
                ),
                input_schema=set_personas_schema,
            )
            async def _set_evaluator_personas_impl(args):
                import json as _json

                personas = args.get("personas", [])
                error = _orchestrator._validate_evaluator_personas(personas)
                if error:
                    return {
                        "content": [
                            {"type": "text", "text": _json.dumps({"error": error})},
                        ],
                        "isError": True,
                    }
                _orchestrator._pending_evaluator_personas = [{"label": str(p["label"]).strip(), "instructions": str(p["instructions"]).strip()} for p in personas]
                labels = [p["label"] for p in _orchestrator._pending_evaluator_personas]
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": _json.dumps(
                                {
                                    "status": "accepted",
                                    "message": f"Evaluator personas set: {', '.join(labels)}. " "These will be applied to the next round evaluator run.",
                                },
                            ),
                        },
                    ],
                }

            _personas_tool = _set_evaluator_personas_impl

        # Create SDK MCP server with checklist tools
        _checklist_tools = [submit_checklist_handler, draft_approach_handler]
        if _personas_tool is not None:
            _checklist_tools.append(_personas_tool)
        sdk_server = create_sdk_mcp_server(
            name="massgen_checklist",
            version="1.0.0",
            tools=_checklist_tools,
        )

        # Inject into backend's MCP servers
        if not hasattr(backend, "config") or not isinstance(backend.config, dict):
            logger.warning(
                f"Agent {agent_id} backend has no dict config, skipping checklist tool",
            )
            return

        if "mcp_servers" not in backend.config:
            backend.config["mcp_servers"] = {}

        if isinstance(backend.config["mcp_servers"], dict):
            backend.config["mcp_servers"]["massgen_checklist"] = sdk_server
        elif isinstance(backend.config["mcp_servers"], list):
            backend.config["mcp_servers"].append(
                {
                    "name": "massgen_checklist",
                    "__sdk_server__": sdk_server,
                },
            )

        logger.info(
            f"[Orchestrator] Registered submit_checklist SDK MCP tool for agent {agent_id}",
        )

    def _init_checklist_tool_stdio(self, agent_id, backend, checklist_state, items):
        """Write checklist specs and add stdio MCP for standard MCP backends."""
        import tempfile

        from .mcp_tools.checklist_tools_server import (
            build_server_config as build_checklist_config,
        )
        from .mcp_tools.checklist_tools_server import (
            write_checklist_specs,
        )

        # Write specs to a temp directory (persists for session lifetime)
        specs_dir = Path(tempfile.mkdtemp(prefix=f"massgen_checklist_{agent_id}_"))
        specs_path = specs_dir / "checklist_specs.json"
        write_checklist_specs(items=items, state=checklist_state, output_path=specs_path)

        # Store path so we can re-write on state refresh
        backend._checklist_specs_path = specs_path

        # Add stdio MCP server config (replacing any existing checklist entry)
        checklist_mcp = build_checklist_config(specs_path)
        backend.mcp_servers = [s for s in backend.mcp_servers if not (isinstance(s, dict) and s.get("name") == "massgen_checklist")]
        backend.mcp_servers.append(checklist_mcp)

        logger.info(
            f"[Orchestrator] Registered submit_checklist stdio MCP for agent {agent_id} " f"(specs: {specs_path})",
        )

    def _init_checkpoint_tool(self) -> None:
        """Set up checkpoint tool for the main agent.

        The checkpoint tool schema is provided by the CheckpointToolkit
        (workflow toolkit) -- no MCP server needed. Execution is handled
        by the orchestrator's streaming loop interception which spawns a
        subprocess via CheckpointSubprocessManager.
        """
        if not self._main_agent_id:
            return
        logger.info(
            f"[Checkpoint] Checkpoint tool active for main agent " f"'{self._main_agent_id}' (via workflow toolkit + interception)",
        )

    def _detect_convergence(self, agent_id: str) -> tuple:
        """Detect whether an agent is converging (total score plateaued).

        Returns:
            Tuple of (is_converging: bool, consecutive_count: int).
            is_converging is True when 2+ consecutive checklist results show
            no meaningful score improvement (<=1 point gain).
        """
        self._sync_stdio_checklist_state_from_specs(agent_id)
        state = self.agent_states.get(agent_id)
        if state is None:
            return False, 0
        history = state.checklist_history
        consecutive = 0
        for i in range(len(history) - 1, 0, -1):
            curr = history[i].get("total_score", 0)
            prev = history[i - 1].get("total_score", 0)
            if curr <= prev + 1:
                consecutive += 1
            else:
                break
        return consecutive >= 2, consecutive

    def _sync_stdio_checklist_state_from_specs(self, agent_id: str) -> None:
        """Sync accepted stdio checklist progress back into AgentState.

        SDK-backed checklist calls mutate AgentState directly in-process. Stdio
        checklist calls persist their runtime state into the specs JSON, so the
        orchestrator needs to pull that state back in before using helper gates
        like `_has_successful_checklist_submit_this_round`.
        """
        agent = self.agents.get(agent_id)
        agent_state = self.agent_states.get(agent_id)
        if not agent or not agent_state:
            return
        if bool(getattr(agent.backend, "supports_sdk_mcp", False)):
            return

        specs_path = getattr(agent.backend, "_checklist_specs_path", None)
        if not specs_path:
            return

        try:
            with open(specs_path, encoding="utf-8") as f:
                specs_payload = json.load(f)
        except Exception:
            return

        persisted_state = specs_payload.get("state") or {}

        persisted_calls = persisted_state.get("checklist_calls_this_round")
        if isinstance(persisted_calls, (int, float)):
            agent_state.checklist_calls_this_round = max(
                agent_state.checklist_calls_this_round,
                int(persisted_calls),
            )

        persisted_history = persisted_state.get("checklist_history")
        if isinstance(persisted_history, list) and len(persisted_history) >= len(agent_state.checklist_history):
            agent_state.checklist_history = list(persisted_history)

        raw_pending = persisted_state.get("pending_checklist_recheck_labels")
        normalized_pending: set[str] = set()
        if isinstance(raw_pending, str):
            label = raw_pending.strip()
            if label:
                normalized_pending.add(label)
        elif isinstance(raw_pending, (list, tuple, set)):
            normalized_pending = {str(label).strip() for label in raw_pending if str(label).strip()}
        agent_state.pending_checklist_recheck_labels = normalized_pending

        # Sync evaluator personas from stdio specs into orchestrator state.
        raw_personas = persisted_state.get("pending_evaluator_personas")
        if isinstance(raw_personas, list) and raw_personas:
            self._pending_evaluator_personas = raw_personas

    def _refresh_checklist_state_for_agent(
        self,
        agent_id: str,
        prefer_local_runtime_state: bool = False,
    ) -> None:
        """Refresh the checklist tool's mutable state dict for an agent.

        Called after mid-stream injection so the submit_checklist tool sees
        up-to-date budget (remaining slots may change when decomposition
        streak is reset) and has_existing_answers.
        """
        agent = self.agents.get(agent_id)
        if not agent or not hasattr(agent.backend, "_checklist_state"):
            return

        if not prefer_local_runtime_state:
            self._sync_stdio_checklist_state_from_specs(agent_id)

        from massgen.system_prompt_sections import (
            _checklist_confidence_cutoff,
            _checklist_effective_threshold,
            _checklist_required_true,
        )

        _cl_remaining = max(
            0,
            (self.config.max_new_answers_per_agent or 5) - self._get_agent_answer_count_for_limit(agent_id),
        )
        _has_answers = bool(
            self.coordination_tracker.answers_by_agent.get(agent_id),
        )
        state = agent.backend._checklist_state
        agent_state = self.agent_states.get(agent_id)
        criteria_agent_id = agent_id if self._is_decomposition_mode() else None
        active_items, active_categories, active_verify_by, criteria_source, _anti, _score_anchors = self._resolve_effective_checklist_criteria(
            criteria_agent_id,
        )
        current_items = getattr(agent.backend, "_checklist_items", None)
        if isinstance(current_items, list):
            current_items[:] = list(active_items)
        else:
            agent.backend._checklist_items = list(active_items)
        effective_t = _checklist_effective_threshold(
            state.get("threshold", 5),
            _cl_remaining,
            state.get("total", 5),
        )
        pending_recheck_labels: list[str] = []
        if bool(getattr(agent.backend, "supports_sdk_mcp", False)):
            sdk_pending = getattr(self.agent_states.get(agent_id), "pending_checklist_recheck_labels", set()) or set()
            pending_recheck_labels = sorted(
                {str(label).strip() for label in sdk_pending if str(label).strip()},
            )
        else:
            raw_pending: Any = None
            specs_path = getattr(agent.backend, "_checklist_specs_path", None)
            if specs_path:
                try:
                    with open(specs_path, encoding="utf-8") as f:
                        specs_payload = json.load(f)
                    raw_pending = (specs_payload.get("state") or {}).get("pending_checklist_recheck_labels")
                except Exception:
                    raw_pending = None
            if raw_pending is None:
                raw_pending = state.get("pending_checklist_recheck_labels", [])
            if isinstance(raw_pending, str):
                pending_recheck_labels = [raw_pending.strip()] if raw_pending.strip() else []
            elif isinstance(raw_pending, (list, tuple, set)):
                pending_recheck_labels = sorted(
                    {str(label).strip() for label in raw_pending if str(label).strip()},
                )
        agent.backend._checklist_state.update(
            {
                "remaining": _cl_remaining,
                "has_existing_answers": _has_answers,
                "agent_answer_count": len(self.coordination_tracker.answers_by_agent.get(agent_id, [])),
                "current_answer_label": self.coordination_tracker.get_latest_answer_label(agent_id),
                "checklist_first_answer": bool(
                    getattr(self.config, "checklist_first_answer", False),
                ),
                "max_checklist_calls_per_round": int(
                    getattr(self.config, "max_checklist_calls_per_round", 1) or 1,
                ),
                "checklist_calls_this_round": (agent_state.checklist_calls_this_round if agent_state is not None else 0),
                "checklist_history": (list(agent_state.checklist_history) if agent_state is not None else []),
                "decomposition_mode": self._is_decomposition_mode(),
                "required": _checklist_required_true(
                    effective_t,
                    num_items=len(getattr(agent.backend, "_checklist_items", [])) or 4,
                ),
                "cutoff": _checklist_confidence_cutoff(effective_t),
                "require_gap_report": bool(
                    getattr(self.config, "checklist_require_gap_report", True),
                ),
                "require_diagnostic_report": bool(
                    getattr(self.config, "checklist_require_gap_report", True),
                ),
                "changedoc_mode": self._is_changedoc_enabled(),
                "workspace_path": getattr(
                    getattr(agent.backend, "filesystem_manager", None),
                    "cwd",
                    None,
                ),
                "item_categories": active_categories,
                "item_verify_by": active_verify_by or {},
                "criteria_source": criteria_source,
                # Preserve novelty gating from initial state (config-driven, doesn't change)
                "novelty_subagent_enabled": state.get("novelty_subagent_enabled", False),
                # Preserve critic gating from initial state
                "critic_subagent_enabled": state.get("critic_subagent_enabled", False),
                # Preserve builder gating from initial state
                "builder_subagent_enabled": state.get("builder_subagent_enabled", False),
                # Preserve regression_guard gating from initial state
                "regression_guard_subagent_enabled": state.get("regression_guard_subagent_enabled", False),
                # Preserve quality_rethinking gating from initial state
                "quality_rethinking_subagent_enabled": state.get("quality_rethinking_subagent_enabled", False),
                # Preserve quality-rethinking auto-injection toggle from initial state
                "enable_quality_rethink_on_iteration": state.get("enable_quality_rethink_on_iteration", False),
                # Preserve novelty auto-injection toggle from initial state
                "enable_novelty_on_iteration": state.get("enable_novelty_on_iteration", False),
                # Update available agent labels so checklist enforces complete coverage.
                # Includes labels injected mid-stream (updated by update_agent_context_with_new_answers).
                "available_agent_labels": list(
                    self.coordination_tracker.get_agent_context_labels(agent_id),
                ),
                "pending_checklist_recheck_labels": pending_recheck_labels,
                "round_evaluator_auto_injected": state.get("round_evaluator_auto_injected", False),
                "round_evaluator_primary_artifact_path": state.get("round_evaluator_primary_artifact_path", ""),
                "round_evaluator_verdict_artifact_path": state.get("round_evaluator_verdict_artifact_path", ""),
                "round_evaluator_next_tasks_artifact_path": state.get("round_evaluator_next_tasks_artifact_path", ""),
                "allowed_external_report_paths": list(state.get("allowed_external_report_paths", []) or []),
            },
        )
        # Re-write specs file for stdio backends so the MCP server sees updated state
        if hasattr(agent.backend, "_checklist_specs_path"):
            from .mcp_tools.checklist_tools_server import write_checklist_specs

            write_checklist_specs(
                items=agent.backend._checklist_items,
                state=agent.backend._checklist_state,
                output_path=agent.backend._checklist_specs_path,
            )

        logger.debug(
            "[Orchestrator] Refreshed checklist state for %s: remaining=%d, has_answers=%s",
            agent_id,
            _cl_remaining,
            _has_answers,
        )

    def _set_round_evaluator_task_mode(
        self,
        agent_id: str,
        *,
        enabled: bool,
        primary_artifact_path: str = "",
        verdict_artifact_path: str = "",
        next_tasks_artifact_path: str = "",
        objective: str = "",
        primary_strategy: str = "",
        why_this_strategy: str = "",
        strategy_mode: str = "",
        incremental_override_reason: str = "",
        success_contract: dict[str, Any] | None = None,
        deprioritize_or_remove: list[str] | None = None,
    ) -> None:
        """Persist whether an agent is in post-evaluator task mode."""
        agent = self.agents.get(agent_id)
        if not agent or not hasattr(agent.backend, "_checklist_state"):
            return

        state = agent.backend._checklist_state
        state["round_evaluator_auto_injected"] = bool(enabled)
        state["round_evaluator_primary_artifact_path"] = primary_artifact_path or ""
        state["round_evaluator_verdict_artifact_path"] = verdict_artifact_path or ""
        state["round_evaluator_next_tasks_artifact_path"] = next_tasks_artifact_path or ""
        state["round_evaluator_objective"] = objective or ""
        state["round_evaluator_primary_strategy"] = primary_strategy or ""
        state["round_evaluator_why_this_strategy"] = why_this_strategy or ""
        state["round_evaluator_strategy_mode"] = strategy_mode or ""
        state["round_evaluator_incremental_override_reason"] = incremental_override_reason or ""
        state["round_evaluator_success_contract"] = copy.deepcopy(success_contract) if isinstance(success_contract, dict) else {}
        state["round_evaluator_deprioritize_or_remove"] = list(deprioritize_or_remove or [])
        state["allowed_external_report_paths"] = [primary_artifact_path] if primary_artifact_path else []

        if hasattr(agent.backend, "_checklist_specs_path"):
            from .mcp_tools.checklist_tools_server import write_checklist_specs

            write_checklist_specs(
                items=getattr(agent.backend, "_checklist_items", []),
                state=state,
                output_path=agent.backend._checklist_specs_path,
            )

    # ------------------------------------------------------------------
    # Checkpoint coordination helpers
    # ------------------------------------------------------------------

    def set_main_agent(self, agent_id: str) -> None:
        """Designate an agent as the main orchestrating agent.

        In checkpoint mode, only the main agent runs during normal operation.
        It delegates work to the full team via the checkpoint() tool.

        Also triggers checkpoint MCP injection into the main agent's backend
        (since _init_checkpoint_tool() in __init__ runs before this is called).

        Args:
            agent_id: ID of the agent to designate as main.

        Raises:
            ValueError: If agent_id is not found in configured agents.
        """
        if agent_id not in self.agents:
            raise ValueError(
                f"Cannot set main_agent '{agent_id}': " f"not found in agents {list(self.agents.keys())}",
            )
        self._main_agent_id = agent_id
        logger.info(f"[Checkpoint] Main agent set to '{agent_id}'")

        # Inject checkpoint MCP tool now that main agent is known
        self._init_checkpoint_tool()

    @property
    def is_checkpoint_mode(self) -> bool:
        """Whether checkpoint coordination is configured."""
        return self._main_agent_id is not None

    def _is_agent_active_in_current_mode(self, agent_id: str) -> bool:
        """Check if an agent should be active in the current mode.

        Solo mode: only the main agent is active.
        Checkpoint mode: all agents are active.
        Normal mode (no main_agent): all agents are active.

        Args:
            agent_id: The agent to check.

        Returns:
            True if the agent should run.
        """
        if not self.is_checkpoint_mode:
            return True  # Normal multi-agent mode
        if self._checkpoint_active:
            return True  # All agents active during checkpoint
        # Solo mode: only main agent
        return agent_id == self._main_agent_id

    async def _activate_checkpoint(self, signal: dict[str, Any]) -> str:
        """Spawn a checkpoint subprocess and return the consensus result.

        Replaces the old in-process approach with a subprocess call:
        1. Emit checkpoint_activated event
        2. Spawn ``massgen --stream-events`` subprocess
        3. Relay events to parent EventEmitter with remapped agent IDs
        4. Sync workspace deliverables back to main agent
        5. Emit checkpoint_completed event
        6. Return consensus text for injection into main agent context

        Args:
            signal: The checkpoint signal dict from the main agent.

        Returns:
            The consensus text from the checkpoint subprocess.
        """
        from .mcp_tools.checkpoint._subprocess_manager import (
            CheckpointSubprocessManager,
        )

        self._checkpoint_active = True
        self._checkpoint_number += 1
        self._checkpoint_task = signal.get("task", "")

        # Track event on the coordination tracker
        self.coordination_tracker._add_event(
            EventType.CHECKPOINT_CALLED,
            agent_id=self._main_agent_id,
            details=f"Checkpoint #{self._checkpoint_number}: {self._checkpoint_task[:100]}",
            context={
                "task": self._checkpoint_task,
                "context": signal.get("context", ""),
            },
        )

        # Build participant info from parent config for display
        self._checkpoint_participants = {}
        for aid in self.agents:
            display_id = f"{aid}-ckpt{self._checkpoint_number}"
            model_name = ""
            if hasattr(self.agents[aid].backend, "get_model_name"):
                try:
                    model_name = self.agents[aid].backend.get_model_name()
                except Exception:
                    pass
            self._checkpoint_participants[display_id] = {
                "real_agent_id": aid,
                "model": model_name,
            }

        # Emit checkpoint_activated event for WebUI
        _emitter = get_event_emitter()
        if _emitter:
            _emitter.emit_checkpoint_activated(
                checkpoint_number=self._checkpoint_number,
                task=self._checkpoint_task,
                participants=self._checkpoint_participants,
                main_agent_id=self._main_agent_id,
            )

        # Resolve main agent workspace for subprocess
        main_agent = self.agents.get(self._main_agent_id)
        parent_workspace = None
        if main_agent:
            parent_workspace = getattr(
                getattr(main_agent.backend, "filesystem_manager", None),
                "cwd",
                None,
            )

        if not parent_workspace:
            logger.error("[Checkpoint] No parent workspace for subprocess")
            self._checkpoint_active = False
            return "Checkpoint failed: no workspace available"

        # Relay callback: re-emit subprocess events through parent emitter
        async def _relay_event(event):
            if _emitter:
                _emitter.emit(event)

        # Spawn subprocess
        manager = CheckpointSubprocessManager(
            parent_config=self._raw_config_dict,
            parent_workspace=parent_workspace,
            checkpoint_number=self._checkpoint_number,
        )

        result = await manager.spawn(
            signal=signal,
            on_event=_relay_event,
        )

        # Extract consensus
        consensus = result.get("output", "")
        workspace_changes = result.get("workspace_changes", [])

        # Copy subprocess logs into parent's log directory (like subagents)
        manager._copy_subprocess_logs()

        if result.get("success"):
            manager.cleanup()
        else:
            error = result.get("error", "Unknown error")
            consensus = f"Checkpoint failed: {error}"
            ws_path = manager._checkpoint_workspace
            logger.error(
                f"[Checkpoint] Subprocess failed: {error}. " f"Workspace preserved at: {ws_path}",
            )

        # Track completion
        self.coordination_tracker._add_event(
            EventType.CHECKPOINT_COMPLETED,
            agent_id=self._main_agent_id,
            details=f"Checkpoint #{self._checkpoint_number} completed",
            context={
                "consensus_preview": consensus[:200] if consensus else "",
                "files_changed": len(workspace_changes),
            },
        )

        # Emit checkpoint_completed event for WebUI
        if _emitter:
            _emitter.emit_checkpoint_completed(
                checkpoint_number=self._checkpoint_number,
                consensus=consensus,
                main_agent_id=self._main_agent_id,
            )

        self._checkpoint_active = False
        self._checkpoint_participants = {}

        logger.info(
            f"[Checkpoint] Completed checkpoint #{self._checkpoint_number}: " f"{self._checkpoint_task[:80]}",
        )

        return consensus

    def ensure_workspace_symlinks(self) -> None:
        """Ensure per-agent workspace symlinks exist in the current attempt log directory.

        In checkpoint solo mode, only creates symlinks for active agents
        (main agent in solo, all agents during checkpoint).
        """
        try:
            log_dir = get_log_session_dir()
            if log_dir:
                for agent_id, agent in self.agents.items():
                    # Skip inactive agents (e.g., non-main agents in solo mode)
                    if not self._is_agent_active_in_current_mode(agent_id):
                        continue
                    if not agent.backend.filesystem_manager or not agent.backend.filesystem_manager.cwd:
                        continue
                    agent_log_dir = log_dir / agent_id
                    agent_log_dir.mkdir(parents=True, exist_ok=True)
                    workspace_link = agent_log_dir / "workspace"
                    if workspace_link.exists():
                        continue
                    workspace_link.symlink_to(Path(agent.backend.filesystem_manager.cwd).resolve())
                    logger.info(
                        f"[Orchestrator] Symlinked {workspace_link} → {agent.backend.filesystem_manager.cwd}",
                    )
        except Exception as e:
            logger.debug(f"[Orchestrator] Failed to create workspace symlinks: {e}")

    def _init_nlip_routing(self) -> None:
        """Initialize NLIP routing for all agents."""
        logger.info(
            f"[Orchestrator] Initializing NLIP routing for {len(self.agents)} agents",
        )

        nlip_enabled_count = 0
        nlip_skipped_count = 0

        for agent_id, agent in self.agents.items():
            # Check if agent has config
            if not hasattr(agent, "config"):
                logger.debug(
                    f"[Orchestrator] Agent {agent_id} has no config, skipping NLIP",
                )
                nlip_skipped_count += 1
                continue

            # Check if backend supports NLIP (has custom_tool_manager)
            backend = getattr(agent, "backend", None)
            if not backend:
                logger.debug(
                    f"[Orchestrator] Agent {agent_id} has no backend, skipping NLIP",
                )
                nlip_skipped_count += 1
                continue

            tool_manager = getattr(backend, "custom_tool_manager", None)
            if not tool_manager:
                logger.info(
                    f"[Orchestrator] Agent {agent_id} backend does not support NLIP (no custom_tool_manager), skipping",
                )
                nlip_skipped_count += 1
                continue

            # Backend supports NLIP, enable it
            agent.config.enable_nlip = True
            agent.config.nlip_config = self.nlip_config

            # Initialize NLIP router for the agent
            mcp_executor = getattr(backend, "_execute_mcp_function_with_retry", None)
            agent.config.init_nlip_router(
                tool_manager=tool_manager,
                mcp_executor=mcp_executor,
            )

            # Inject NLIP router into backend
            if hasattr(backend, "set_nlip_router"):
                backend.set_nlip_router(
                    nlip_router=agent.config.nlip_router,
                    enabled=True,
                )

            logger.info(f"[Orchestrator] NLIP routing enabled for agent: {agent_id}")
            nlip_enabled_count += 1

        logger.info(
            f"[Orchestrator] NLIP initialization complete: {nlip_enabled_count} enabled, {nlip_skipped_count} skipped",
        )

    def _init_broadcast_tools(self) -> None:
        """Initialize broadcast tools if enabled in coordination config."""
        # Update workflow tools with broadcast if enabled
        has_coord = hasattr(self.config, "coordination_config")
        has_broadcast = hasattr(self.config.coordination_config, "broadcast") if has_coord else False
        logger.info(
            f"[Orchestrator] Checking broadcast config: has_coord={has_coord}, has_broadcast={has_broadcast}",
        )
        if hasattr(self.config, "coordination_config") and hasattr(
            self.config.coordination_config,
            "broadcast",
        ):
            broadcast_mode = self.config.coordination_config.broadcast
            logger.info(
                f"[Orchestrator] Broadcast mode value: {broadcast_mode}, type: {type(broadcast_mode)}",
            )
            if broadcast_mode and broadcast_mode is not False:
                logger.info(
                    f"[Orchestrator] Broadcasting enabled (mode: {broadcast_mode}). Adding broadcast tools to workflow",
                )

                # Use blocking mode (wait=True) for both agents and human
                # Priority system prevents deadlocks by requiring agents to respond to pending broadcasts first
                wait_by_default = True
                logger.info(
                    "[Orchestrator] Using blocking broadcasts (wait=True) with priority system to prevent deadlocks",
                )

                # Get broadcast sensitivity setting
                broadcast_sensitivity = getattr(
                    self.config.coordination_config,
                    "broadcast_sensitivity",
                    "medium",
                )
                logger.info(
                    f"[Orchestrator] Broadcast sensitivity: {broadcast_sensitivity}",
                )

                # Recreate workflow tools with broadcast enabled
                # Sort agent IDs for consistent anonymous mapping with coordination_tracker
                _is_decomposition = getattr(self.config, "coordination_mode", "voting") == "decomposition"
                self.workflow_tools = get_workflow_tools(
                    valid_agent_ids=sorted(self.agents.keys()),
                    template_overrides=getattr(
                        self.message_templates,
                        "_template_overrides",
                        {},
                    ),
                    api_format="chat_completions",  # Default, overridden per backend
                    orchestrator=self,
                    broadcast_mode=broadcast_mode,
                    broadcast_wait_by_default=wait_by_default,
                    decomposition_mode=_is_decomposition,
                )
                tool_names = [t.get("function", {}).get("name", "unknown") for t in self.workflow_tools]
                logger.info(
                    f"[Orchestrator] Broadcast tools added to workflow ({len(self.workflow_tools)} total tools): {tool_names}",
                )

                # Register broadcast tools as custom tools with backends for recursive execution
                self._register_broadcast_custom_tools(
                    broadcast_mode,
                    wait_by_default,
                    broadcast_sensitivity,
                )
            else:
                logger.info("[Orchestrator] Broadcasting disabled")
        else:
            logger.info("[Orchestrator] Broadcast config not found")

    def _register_broadcast_custom_tools(
        self,
        broadcast_mode: str,
        wait_by_default: bool,
        sensitivity: str = "medium",
    ) -> None:
        """
        Register broadcast tools as custom tools with all agent backends.

        This allows broadcast tools to be executed recursively by the backend,
        avoiding the need for orchestrator-level tool handling.

        Args:
            broadcast_mode: "agents" or "human"
            wait_by_default: Default waiting behavior for broadcasts
            sensitivity: How frequently to use ask_others() ("low", "medium", "high")
        """
        from .tool.workflow_toolkits.broadcast import BroadcastToolkit

        # Create broadcast toolkit instance
        broadcast_toolkit = BroadcastToolkit(
            orchestrator=self,
            broadcast_mode=broadcast_mode,
            wait_by_default=wait_by_default,
            sensitivity=sensitivity,
        )

        # Register with each agent's backend as custom tool functions
        for agent_id, agent in self.agents.items():
            backend = agent.backend

            # Check if backend supports custom tool registration
            # Note: Some backends use custom_tool_manager, others use _custom_tool_manager
            has_tool_manager = hasattr(backend, "custom_tool_manager") or hasattr(
                backend,
                "_custom_tool_manager",
            )
            if not has_tool_manager:
                logger.warning(
                    f"[Orchestrator] Agent {agent_id} backend doesn't support custom tool manager - broadcast tools will use orchestrator handling",
                )
                continue

            # Register ask_others as a custom tool
            if not hasattr(backend, "_broadcast_toolkit"):
                backend._broadcast_toolkit = broadcast_toolkit
                # Ensure _custom_tool_names exists (some backends may not have it)
                if not hasattr(backend, "_custom_tool_names"):
                    backend._custom_tool_names = set()
                backend._custom_tool_names.add("ask_others")
                logger.info(
                    f"[Orchestrator] Registered ask_others as custom tool for agent {agent_id}",
                )

            # Register respond_to_broadcast for agents mode
            if broadcast_mode == "agents":
                backend._custom_tool_names.add("respond_to_broadcast")
                logger.info(
                    f"[Orchestrator] Registered respond_to_broadcast as custom tool for agent {agent_id}",
                )

            # Register polling tools if needed
            if not wait_by_default:
                backend._custom_tool_names.add("check_broadcast_status")
                backend._custom_tool_names.add("get_broadcast_responses")
                logger.info(
                    f"[Orchestrator] Registered polling broadcast tools for agent {agent_id}",
                )

    async def _prepare_paraphrases_for_agents(self, question: str) -> None:
        """Generate and assign DSPy paraphrases for the current question."""

        # Reset paraphrases and evolved prompts before regenerating
        self._agent_paraphrases = {}
        self._evolved_prompts = {}
        for state in self.agent_states.values():
            state.paraphrase = None

        if not self.dspy_paraphraser:
            return

        if not question:
            return

        try:
            variants = await asyncio.to_thread(
                self.dspy_paraphraser.generate_variants,
                question,
            )
        except Exception as exc:
            self._paraphrase_generation_errors += 1
            logger.warning(f"Failed to generate DSPy paraphrases: {exc}")
            return

        if not variants:
            logger.warning(
                "DSPy paraphraser returned no variants; proceeding with original question for all agents.",
            )
            return

        agent_ids = list(self.agents.keys())
        if not agent_ids:
            return

        for idx, agent_id in enumerate(agent_ids):
            paraphrase = variants[idx % len(variants)]
            self._agent_paraphrases[agent_id] = paraphrase
            self.agent_states[agent_id].paraphrase = paraphrase

        # Log at INFO level so users know paraphrasing is active
        logger.info(
            f"DSPy paraphrasing enabled: {len(variants)} variant(s) generated and assigned to {len(agent_ids)} agent(s)",
        )
        for agent_id, paraphrase in self._agent_paraphrases.items():
            logger.info(f"  {agent_id}: {paraphrase}")

        log_coordination_step(
            "DSPy paraphrases prepared",
            {
                "variants": len(variants),
                "assigned_agents": self._agent_paraphrases,
            },
        )

    def get_paraphrase_status(self) -> dict[str, Any]:
        """Return current DSPy paraphrase assignments and metrics for observability."""

        status = {
            "paraphrases": self._agent_paraphrases.copy(),
            "generation_errors": self._paraphrase_generation_errors,
            "metrics": None,
        }

        if self.dspy_paraphraser:
            try:
                status["metrics"] = self.dspy_paraphraser.get_metrics()
            except Exception as exc:  # pragma: no cover - defensive guard
                logger.debug(f"Unable to fetch DSPy paraphraser metrics: {exc}")

        return status

    def _validate_skills_config(self) -> None:
        """
        Validate skills configuration.

        Checks that skills directory exists and is not empty. Agents access skills
        directly from the filesystem via workspace tools MCP (no dedicated skills
        MCP server needed).

        Raises:
            RuntimeError: If no skills are found
        """
        from pathlib import Path

        # Check if skills are available (external or built-in)
        skills_dir = Path(self.config.coordination_config.skills_directory)
        logger.info(
            f"[Orchestrator] Checking skills configuration - directory: {skills_dir}",
        )

        # Check for external skills (from openskills)
        has_external_skills = skills_dir.exists() and skills_dir.is_dir() and any(skills_dir.iterdir())

        # Check for built-in skills (bundled with MassGen)
        builtin_skills_dir = Path(__file__).parent / "skills"
        has_builtin_skills = builtin_skills_dir.exists() and any(
            builtin_skills_dir.iterdir(),
        )

        # At least one type of skills must be available
        if not has_external_skills and not has_builtin_skills:
            raise RuntimeError(
                f"No skills found. To use skills:\n"
                f"Install external skills: 'npm i -g openskills && openskills install anthropics/skills --universal -y'\n"
                f"This creates '{skills_dir}' with skills like pdf, xlsx, pptx, etc.\n\n"
                f"Built-in skills (file-search, serena, semtools) should be bundled with MassGen in {builtin_skills_dir}",
            )

        logger.info(
            f"[Orchestrator] Skills available (external: {has_external_skills}, builtin: {has_builtin_skills})",
        )

    def _inject_planning_tools_for_all_agents(self) -> None:
        """
        Inject planning MCP tools into all agents.

        This method adds the planning MCP server to each agent's backend
        configuration, enabling them to create and manage task plans.
        """
        for agent_id, agent in self.agents.items():
            self._inject_planning_tools_for_agent(agent_id, agent)

    def _planning_server_name(self, agent_id: str) -> str:
        """Return the anonymous MCP server name for this agent's planning tools."""
        token = self.coordination_tracker.get_path_token(agent_id)
        return f"planning_{token}"

    def _subagent_server_name(self, agent_id: str) -> str:
        """Return the anonymous MCP server name for this agent's subagent tools."""
        token = self.coordination_tracker.get_path_token(agent_id)
        return f"subagent_{token}"

    def _inject_planning_tools_for_agent(self, agent_id: str, agent: Any) -> None:
        """
        Inject planning MCP tools into a specific agent.

        Args:
            agent_id: ID of the agent
            agent: Agent instance
        """
        logger.info(f"[Orchestrator] Injecting planning tools for agent: {agent_id}")

        # Create planning MCP config
        planning_mcp_config = self._create_planning_mcp_config(agent_id, agent)
        logger.info(
            f"[Orchestrator] Created planning MCP config: {planning_mcp_config['name']}",
        )

        # Get existing mcp_servers configuration
        mcp_servers = agent.backend.config.get("mcp_servers", [])
        logger.info(
            f"[Orchestrator] Existing MCP servers for {agent_id}: {type(mcp_servers)} with {len(mcp_servers) if isinstance(mcp_servers, (list, dict)) else 0} entries",
        )

        # Handle both list format and dict format (Claude Code)
        if isinstance(mcp_servers, dict):
            # Claude Code dict format
            logger.info("[Orchestrator] Using dict format for MCP servers")
            mcp_servers[self._planning_server_name(agent_id)] = planning_mcp_config
        else:
            # Standard list format
            logger.info("[Orchestrator] Using list format for MCP servers")
            if not isinstance(mcp_servers, list):
                mcp_servers = []
            mcp_servers.append(planning_mcp_config)

        # Update backend config
        agent.backend.config["mcp_servers"] = mcp_servers
        logger.info(
            f"[Orchestrator] Updated MCP servers for {agent_id}, now has {len(mcp_servers) if isinstance(mcp_servers, (list, dict)) else 0} servers",
        )

    def _is_round_learning_capture_enabled(self) -> bool:
        """Return whether round-time learning capture should be enabled.

        In ``final_only`` mode, if final presentation is skipped (refinement-off
        flow), we must fall back to round-time capture because there is no later
        presenter stage to write evolving skills or memories.
        """
        coordination_config = getattr(self.config, "coordination_config", None)
        learning_capture_mode = getattr(
            coordination_config,
            "learning_capture_mode",
            "round",
        )
        if learning_capture_mode == "round":
            return True
        if learning_capture_mode == "final_only":
            disable_fallback = getattr(
                coordination_config,
                "disable_final_only_round_capture_fallback",
                False,
            )
            if disable_fallback is True:
                return False
            return not self._expects_final_presentation_stage()
        return False

    def _get_final_answer_strategy(self) -> str:
        """Return the effective final-answer strategy for the current run."""
        configured_strategy = getattr(self.config, "final_answer_strategy", None)
        valid_strategies = {"winner_reuse", "winner_present", "synthesize"}
        if configured_strategy in valid_strategies:
            return configured_strategy
        if configured_strategy is not None:
            logger.warning(
                f"[Orchestrator] Unknown final_answer_strategy={configured_strategy!r}; falling back to legacy behavior",
            )
        if getattr(self.config, "skip_final_presentation", False):
            return "winner_reuse"
        return "winner_present"

    def _expects_final_presentation_stage(self) -> bool:
        """Return whether the current config expects an explicit presenter stage."""
        if getattr(self.config, "coordination_mode", "voting") == "decomposition":
            return True
        if not getattr(self.config, "skip_final_presentation", False):
            return True
        if getattr(self.config, "skip_voting", False):
            return False
        return self._get_final_answer_strategy() in {"winner_present", "synthesize"}

    def _should_skip_vote_rounds_for_synthesize(self) -> bool:
        """Return whether quick multi-agent synthesize runs should skip vote rounds."""
        if self._is_decomposition_mode():
            return False
        if len(self.agents) <= 1:
            return False
        if self._get_final_answer_strategy() != "synthesize":
            return False
        # Don't skip voting when defer_voting is set — it implies
        # the caller wants a produce-then-vote (ensemble) pattern.
        if getattr(self.config, "defer_voting_until_all_answered", False):
            return False
        return getattr(self.config, "max_new_answers_per_agent", None) == 1

    def _is_round_verification_capture_enabled(self) -> bool:
        """Return whether round-time verification replay capture should be enabled."""
        if self._is_round_learning_capture_enabled():
            return True

        coordination_config = getattr(self.config, "coordination_config", None)
        learning_capture_mode = getattr(
            coordination_config,
            "learning_capture_mode",
            "round",
        )
        return learning_capture_mode == "verification_and_final_only"

    def _create_planning_mcp_config(self, agent_id: str, agent: Any) -> dict[str, Any]:
        """
        Create MCP server configuration for planning tools.

        Args:
            agent_id: ID of the agent
            agent: Agent instance (for accessing workspace path)

        Returns:
            MCP server configuration dictionary
        """
        from pathlib import Path as PathlibPath

        import massgen.mcp_tools.planning._planning_mcp_server as planning_module

        script_path = PathlibPath(planning_module.__file__).resolve()

        args = [
            "run",
            f"{script_path}:create_server",
            "--",
            "--agent-id",
            agent_id,
            "--orchestrator-id",
            self.orchestrator_id,
        ]

        # Add workspace path if filesystem mode is enabled
        logger.info(
            f"[Orchestrator] Checking task_planning_filesystem_mode for {agent_id}",
        )
        has_coord_config = hasattr(self.config, "coordination_config")
        logger.info(f"[Orchestrator] Has coordination_config: {has_coord_config}")

        if has_coord_config:
            has_filesystem_mode = hasattr(
                self.config.coordination_config,
                "task_planning_filesystem_mode",
            )
            logger.info(
                f"[Orchestrator] Has task_planning_filesystem_mode attr: {has_filesystem_mode}",
            )
            if has_filesystem_mode:
                value = self.config.coordination_config.task_planning_filesystem_mode
                logger.info(
                    f"[Orchestrator] task_planning_filesystem_mode value: {value}",
                )

        filesystem_mode_enabled = (
            hasattr(self.config, "coordination_config")
            and hasattr(
                self.config.coordination_config,
                "task_planning_filesystem_mode",
            )
            and self.config.coordination_config.task_planning_filesystem_mode
        )

        if filesystem_mode_enabled:
            logger.info("[Orchestrator] task_planning_filesystem_mode is enabled")
            if hasattr(agent, "backend") and hasattr(agent.backend, "filesystem_manager") and agent.backend.filesystem_manager:
                if agent.backend.filesystem_manager.cwd:
                    workspace_path = str(agent.backend.filesystem_manager.cwd)
                    args.extend(["--workspace-path", workspace_path])
                    logger.info(
                        f"[Orchestrator] Enabling filesystem mode for task planning: {workspace_path}",
                    )
                    # Pass anonymous workspace token so plan.json doesn't reveal real agent_id
                    _tracker = getattr(self, "coordination_tracker", None)
                    if _tracker is not None and hasattr(_tracker, "get_path_token"):
                        workspace_token = _tracker.get_path_token(agent_id)
                        args.extend(["--workspace-token", workspace_token])
                else:
                    logger.warning(
                        f"[Orchestrator] Agent {agent_id} filesystem_manager.cwd is None",
                    )
            else:
                logger.warning(
                    f"[Orchestrator] Agent {agent_id} has no filesystem_manager",
                )

        # Add feature flags for auto-inserting discovery tasks
        skills_enabled = hasattr(self.config, "coordination_config") and hasattr(self.config.coordination_config, "use_skills") and self.config.coordination_config.use_skills
        if skills_enabled:
            args.append("--skills-enabled")

        round_learning_capture_enabled = self._is_round_learning_capture_enabled()

        auto_discovery_enabled = False
        if hasattr(agent, "backend") and hasattr(agent.backend, "config"):
            auto_discovery_enabled = agent.backend.config.get(
                "auto_discover_custom_tools",
                False,
            )
        if auto_discovery_enabled and round_learning_capture_enabled:
            args.append("--auto-discovery-enabled")

        memory_enabled = (
            hasattr(self.config, "coordination_config")
            and hasattr(
                self.config.coordination_config,
                "enable_memory_filesystem_mode",
            )
            and self.config.coordination_config.enable_memory_filesystem_mode
        )
        if memory_enabled and round_learning_capture_enabled:
            args.append("--memory-enabled")
        if memory_enabled and self._is_round_verification_capture_enabled() and not round_learning_capture_enabled:
            args.append("--verification-memory-enabled")

        # Enable git commits on task completion if two-tier workspace is enabled
        # Suppressed when write_mode is active (write_mode replaces the old two-tier structure)
        coordination_config = getattr(self.config, "coordination_config", None)
        write_mode = getattr(coordination_config, "write_mode", None) if coordination_config else None
        use_two_tier_workspace = False
        if not (write_mode and write_mode != "legacy"):
            use_two_tier_workspace = bool(
                getattr(coordination_config, "use_two_tier_workspace", False),
            )
        logger.info(
            f"[Orchestrator] use_two_tier_workspace value for {agent_id}: {use_two_tier_workspace} (write_mode={write_mode})",
        )
        if use_two_tier_workspace:
            args.append("--use-two-tier-workspace")
            logger.info(
                f"[Orchestrator] Adding --use-two-tier-workspace flag to planning MCP for {agent_id}",
            )

        # Create injection directory for task injection from draft_approach.
        # Both checklist MCP and planning MCP need rw access to this dir.
        # In Docker mode, the log directory is NOT mounted into the container,
        # so we use a workspace-local path (workspace is always mounted rw).
        # IMPORTANT: resolve() to absolute path — MCP servers run as subprocesses
        # whose CWD may differ from the orchestrator's.
        _is_docker = hasattr(agent, "backend") and hasattr(agent.backend, "_is_docker_mode") and agent.backend._is_docker_mode
        if _is_docker and hasattr(agent, "backend") and hasattr(agent.backend, "filesystem_manager") and agent.backend.filesystem_manager and agent.backend.filesystem_manager.cwd:
            ws_root = Path(agent.backend.filesystem_manager.cwd)
            injection_dir = (ws_root / ".massgen_scratch" / "planning_injection" / agent_id).resolve()
        else:
            log_dir = get_log_session_dir()
            if log_dir:
                injection_dir = (log_dir / "planning_injection" / agent_id).resolve()
            else:
                import tempfile as _tempfile

                injection_dir = Path(_tempfile.mkdtemp(prefix=f"massgen_plan_inject_{agent_id}_"))
        injection_dir.mkdir(parents=True, exist_ok=True)
        if not hasattr(self, "_planning_injection_dirs"):
            self._planning_injection_dirs = {}
        self._planning_injection_dirs[agent_id] = injection_dir
        args.extend(["--injection-dir", str(injection_dir)])

        # Pass hook directory for MCP server-level hook injection (Codex)
        if hasattr(agent, "backend") and hasattr(agent.backend, "supports_mcp_server_hooks") and agent.backend.supports_mcp_server_hooks() and hasattr(agent.backend, "get_hook_dir"):
            hook_dir = agent.backend.get_hook_dir()
            args.extend(["--hook-dir", str(hook_dir)])

        logger.info(f"[Orchestrator] Planning MCP args for {agent_id}: {args}")

        config = {
            "name": self._planning_server_name(agent_id),
            "type": "stdio",
            "command": "fastmcp",
            "args": args,
            "env": {
                "FASTMCP_SHOW_CLI_BANNER": "false",
            },
        }

        return config

    def _write_planning_injection(self, agent_id: str, task_plan: list[dict]) -> None:
        """Write inject_tasks.json to agent's planning injection directory.

        Called after draft_approach returns a valid task_plan. The planning
        MCP server picks up the file on its next tool call.

        Args:
            agent_id: Agent whose planning MCP should receive the tasks
            task_plan: Raw task_plan from evaluate_draft_approach
        """
        if agent_id not in self._planning_injection_dirs:
            return

        from .mcp_tools.checklist_tools_server import _write_inject_file

        _write_inject_file(self._planning_injection_dirs[agent_id], task_plan)
        logger.info(
            f"[Orchestrator] Wrote planning injection for {agent_id}: {len(task_plan)} tasks",
        )

    def _inject_subagent_tools_for_all_agents(self) -> None:
        """
        Inject subagent MCP tools into all agents.

        This method adds the subagent MCP server to each agent's backend
        configuration, enabling them to spawn and manage subagents.
        """
        for agent_id, agent in self.agents.items():
            self._inject_subagent_tools_for_agent(agent_id, agent)

    def _inject_subagent_tools_for_agent(self, agent_id: str, agent: Any) -> None:
        """
        Inject subagent MCP tools into a specific agent.

        Args:
            agent_id: ID of the agent
            agent: Agent instance
        """
        # Only inject if agent has filesystem manager (needs workspace)
        if not hasattr(agent, "backend") or not hasattr(
            agent.backend,
            "filesystem_manager",
        ):
            logger.warning(
                f"[Orchestrator] Agent {agent_id} has no filesystem_manager, skipping subagent tools",
            )
            return

        if not agent.backend.filesystem_manager:
            logger.warning(
                f"[Orchestrator] Agent {agent_id} filesystem_manager is None, skipping subagent tools",
            )
            return

        if not agent.backend.filesystem_manager.cwd:
            logger.warning(
                f"[Orchestrator] Agent {agent_id} filesystem_manager.cwd is None, skipping subagent tools",
            )
            return

        logger.info(f"[Orchestrator] Injecting subagent tools for agent: {agent_id}")

        # Create subagent MCP config
        subagent_mcp_config = self._create_subagent_mcp_config(agent_id, agent)
        logger.info(
            f"[Orchestrator] Created subagent MCP config: {subagent_mcp_config['name']}",
        )

        # Get existing mcp_servers configuration
        mcp_servers = agent.backend.config.get("mcp_servers", [])
        logger.info(
            f"[Orchestrator] Existing MCP servers for {agent_id}: {type(mcp_servers)} with {len(mcp_servers) if isinstance(mcp_servers, (list, dict)) else 0} entries",
        )

        # Handle both list format and dict format (Claude Code)
        if isinstance(mcp_servers, dict):
            # Claude Code dict format
            logger.info("[Orchestrator] Using dict format for MCP servers")
            mcp_servers[self._subagent_server_name(agent_id)] = subagent_mcp_config
        else:
            # Standard list format
            logger.info("[Orchestrator] Using list format for MCP servers")
            if not isinstance(mcp_servers, list):
                mcp_servers = []
            mcp_servers.append(subagent_mcp_config)

        # Update backend config
        agent.backend.config["mcp_servers"] = mcp_servers
        logger.info(
            f"[Orchestrator] Updated MCP servers for {agent_id}, now has {len(mcp_servers) if isinstance(mcp_servers, (list, dict)) else 0} servers",
        )

        # Note: Subagent spawn callbacks are set up later when coordination_ui is available
        # See setup_subagent_spawn_callbacks() method

    def setup_subagent_spawn_callbacks(self) -> None:
        """Set up subagent spawn callbacks for all agents.

        This should be called AFTER coordination_ui is set on the orchestrator,
        as the callbacks need access to the display for TUI notifications.

        Called from CoordinationUI.set_orchestrator() after coordination_ui is assigned.
        """
        if not hasattr(self, "coordination_ui") or not self.coordination_ui:
            logger.debug("[Orchestrator] No coordination_ui, skipping subagent spawn callback setup")
            return

        for agent_id, agent in self.agents.items():
            if hasattr(agent, "backend") and hasattr(agent.backend, "set_subagent_spawn_callback"):
                self._setup_subagent_spawn_callback(agent_id, agent)

        # Share subagent message callback with TUI display
        self._share_subagent_message_callback_with_display()
        # Checklist criteria may have been resolved before the display existed.
        # Push cached criteria now that CoordinationUI/display is attached.
        self._push_cached_criteria_to_display()

    def _setup_subagent_spawn_callback(self, agent_id: str, agent: Any) -> None:
        """Set up callback to notify TUI when subagent spawning starts.

        This creates a wrapper callback that captures the agent_id and forwards
        spawn notifications to the TUI display for immediate visual feedback.

        Args:
            agent_id: ID of the agent
            agent: Agent instance
        """
        # Get display if available (coordination_ui.display)
        display = None
        if hasattr(self, "coordination_ui") and self.coordination_ui:
            display = getattr(self.coordination_ui, "display", None)

        if not display:
            logger.debug(f"[Orchestrator] No display available for subagent spawn callback on {agent_id}")
            return

        if not hasattr(display, "notify_subagent_spawn_started"):
            logger.debug(f"[Orchestrator] Display doesn't support notify_subagent_spawn_started for {agent_id}")
            return

        # Create wrapper callback that captures agent_id
        def spawn_callback(tool_name: str, args: dict[str, Any], call_id: str) -> None:
            """Forward spawn notification to TUI display."""
            try:
                display.notify_subagent_spawn_started(agent_id, tool_name, args, call_id)
                logger.debug(f"[Orchestrator] Notified TUI of subagent spawn for {agent_id}")
            except Exception as e:
                logger.debug(f"[Orchestrator] Failed to notify TUI of subagent spawn: {e}")

        # Set callback on backend
        if hasattr(agent.backend, "set_subagent_spawn_callback"):
            agent.backend.set_subagent_spawn_callback(spawn_callback)
            logger.info(f"[Orchestrator] Set subagent spawn callback for {agent_id}")
        else:
            logger.debug(f"[Orchestrator] Backend for {agent_id} doesn't support subagent spawn callback")

    def _write_subagent_type_dirs(self, workspace_root: Any) -> None:
        """Write SUBAGENT.md dirs to workspace_root/.massgen/subagent_types/.

        Called at MCP config creation and re-called at each round start so the
        lazy scanner in the MCP server always finds the files even after
        workspace clears between rounds.
        """
        import json
        from pathlib import Path as PathlibPath

        try:
            from massgen.subagent.type_scanner import (
                DEFAULT_SUBAGENT_TYPES,
                scan_subagent_types,
            )

            _subagent_types_cfg = getattr(
                getattr(self.config, "coordination_config", None),
                "subagent_types",
                None,
            )
            _allowed = _subagent_types_cfg if _subagent_types_cfg is not None else DEFAULT_SUBAGENT_TYPES
            specialized_types = scan_subagent_types(allowed_types=_allowed)
            if specialized_types:
                subagent_types_dir = PathlibPath(workspace_root) / ".massgen" / "subagent_types"
                subagent_types_dir.mkdir(parents=True, exist_ok=True)
                for t in specialized_types:
                    type_dir = subagent_types_dir / t.name
                    type_dir.mkdir(exist_ok=True)
                    frontmatter = f"---\nname: {t.name}\ndescription: {json.dumps(t.description)}\n"
                    if t.skills:
                        frontmatter += f"skills: {json.dumps(t.skills)}\n"
                    if t.expected_input:
                        frontmatter += f"expected_input: {json.dumps(t.expected_input)}\n"
                    frontmatter += "---\n"
                    (type_dir / "SUBAGENT.md").write_text(frontmatter + t.system_prompt)
                logger.info(
                    f"[Orchestrator] Wrote {len(specialized_types)} subagent type dirs to {subagent_types_dir}",
                )
        except ValueError as e:
            raise ValueError(f"Failed to discover specialized subagent types: {e}") from e
        except Exception as e:
            logger.warning(f"[Orchestrator] Failed to write subagent type dirs: {e}")

    def _build_parent_coordination_config_for_subagents(self) -> dict[str, Any]:
        """Collect parent coordination fields that child subagent runs may inherit."""
        parent_coordination_config: dict[str, Any] = {}
        coord_cfg = getattr(self.config, "coordination_config", None)
        if not coord_cfg:
            return parent_coordination_config

        if hasattr(coord_cfg, "enable_agent_task_planning"):
            parent_coordination_config["enable_agent_task_planning"] = coord_cfg.enable_agent_task_planning
        if hasattr(coord_cfg, "task_planning_filesystem_mode"):
            parent_coordination_config["task_planning_filesystem_mode"] = coord_cfg.task_planning_filesystem_mode
        if hasattr(coord_cfg, "learning_capture_mode"):
            parent_coordination_config["learning_capture_mode"] = coord_cfg.learning_capture_mode
        if hasattr(coord_cfg, "disable_final_only_round_capture_fallback"):
            parent_coordination_config["disable_final_only_round_capture_fallback"] = coord_cfg.disable_final_only_round_capture_fallback
        if hasattr(coord_cfg, "subagent_orchestrator"):
            so_cfg = coord_cfg.subagent_orchestrator
            if so_cfg:
                parent_coordination_config["subagent_orchestrator"] = so_cfg.to_dict()

        use_skills = getattr(coord_cfg, "use_skills", False)
        enabled_skill_names = getattr(coord_cfg, "enabled_skill_names", None)
        if use_skills or enabled_skill_names is not None:
            parent_coordination_config["use_skills"] = True
            parent_coordination_config["massgen_skills"] = getattr(coord_cfg, "massgen_skills", []) or []
            parent_coordination_config["skills_directory"] = getattr(
                coord_cfg,
                "skills_directory",
                ".agent/skills",
            )
            parent_coordination_config["load_previous_session_skills"] = getattr(
                coord_cfg,
                "load_previous_session_skills",
                False,
            )
            if enabled_skill_names is not None:
                parent_coordination_config["enabled_skill_names"] = enabled_skill_names

        if hasattr(coord_cfg, "subagent_round_timeouts") and coord_cfg.subagent_round_timeouts:
            parent_coordination_config["subagent_round_timeouts"] = coord_cfg.subagent_round_timeouts

        if hasattr(self.config, "timeout_config") and self.config.timeout_config:
            parent_coordination_config["parent_round_timeouts"] = {
                "initial_round_timeout_seconds": self.config.timeout_config.initial_round_timeout_seconds,
                "subsequent_round_timeout_seconds": self.config.timeout_config.subsequent_round_timeout_seconds,
                "round_timeout_grace_seconds": self.config.timeout_config.round_timeout_grace_seconds,
            }

        for setting in (
            "voting_sensitivity",
            "voting_threshold",
            "checklist_require_gap_report",
            "gap_report_mode",
            "max_checklist_calls_per_round",
            "checklist_first_answer",
        ):
            value = getattr(self.config, setting, None)
            if setting == "voting_threshold" and value is None:
                continue
            if value is not None:
                parent_coordination_config[setting] = value

        return parent_coordination_config

    def _create_subagent_mcp_config(self, agent_id: str, agent: Any) -> dict[str, Any]:
        """
        Create MCP server configuration for subagent tools.

        Args:
            agent_id: ID of the agent
            agent: Agent instance (for accessing workspace path)

        Returns:
            MCP server configuration dictionary
        """
        from pathlib import Path as PathlibPath

        import massgen.mcp_tools.subagent._subagent_mcp_server as subagent_module

        script_path = PathlibPath(subagent_module.__file__).resolve()

        fs_manager = agent.backend.filesystem_manager
        if hasattr(fs_manager, "get_workspace_root"):
            workspace_root = PathlibPath(fs_manager.get_workspace_root()).resolve()
        else:
            workspace_root = PathlibPath(fs_manager.cwd).resolve()
        workspace_path = str(workspace_root)
        agent_temporary_workspace_path = ""
        fs_temp_workspace = getattr(fs_manager, "agent_temporary_workspace", None)
        if fs_temp_workspace:
            agent_temporary_workspace_path = str(PathlibPath(fs_temp_workspace).resolve())
        else:
            orchestrator_temp_workspace = getattr(self, "_agent_temporary_workspace", None)
            if orchestrator_temp_workspace:
                agent_temporary_workspace_path = str(PathlibPath(orchestrator_temp_workspace).resolve())
        # Keep subagent MCP temp config files inside the mounted workspace so
        # Docker-based Codex can read them. Host /tmp paths are not guaranteed
        # to be mounted in the container.
        mcp_temp_dir = workspace_root / ".massgen" / "subagent_mcp"
        mcp_temp_dir.mkdir(parents=True, exist_ok=True)

        # Build list of all parent agent configs to pass to subagent manager
        # This allows subagents to inherit the exact same agent setup by default
        import json

        agent_configs = []
        for aid, a in self.agents.items():
            agent_cfg = {"id": aid}
            if hasattr(a.backend, "config"):
                # Filter out non-serializable or internal keys
                backend_cfg = {k: v for k, v in a.backend.config.items() if k not in ("mcp_servers", "_config_path")}
                # Codex/GeminiCLI extract model to self.model; ensure it's in the serialized config
                if "model" not in backend_cfg and hasattr(a.backend, "model") and a.backend.model:
                    backend_cfg["model"] = a.backend.model
                agent_cfg["backend"] = backend_cfg
            runtime_agent_config = getattr(a, "config", None)
            subagent_agents = getattr(runtime_agent_config, "subagent_agents", None)
            if isinstance(subagent_agents, list) and subagent_agents:
                agent_cfg["subagent_agents"] = json.loads(json.dumps(subagent_agents))
            agent_configs.append(agent_cfg)

        # Use anonymous token for config filenames (defense-in-depth against
        # agent ID leaks if .massgen/ exclusion is bypassed).
        _token = self.coordination_tracker.get_path_token(agent_id)

        # Write agent configs to a deterministic file to avoid command line
        # length limits.  Deterministic names (keyed by token) prevent
        # accumulation across runs — each run simply overwrites.
        agent_configs_path = str(mcp_temp_dir / f"{_token}_agent_configs.json")
        with open(agent_configs_path, "w") as f:
            json.dump(agent_configs, f)

        # Extract context_paths from orchestrator config to pass to subagents
        # This allows subagents to read the same codebase/files as the parent
        context_paths_path = ""
        parent_context_paths = []
        if hasattr(self, "config") and isinstance(getattr(self.config, "__dict__", {}), dict):
            # Try to get context_paths from the raw config dict stored on agents
            if hasattr(agent.backend, "config") and "context_paths" in agent.backend.config:
                parent_context_paths = agent.backend.config.get("context_paths", [])

        if parent_context_paths:
            context_paths_path = str(mcp_temp_dir / f"{_token}_context_paths.json")
            with open(context_paths_path, "w") as f:
                json.dump(parent_context_paths, f)
            logger.info(
                f"[Orchestrator] Passing {len(parent_context_paths)} context paths to subagent MCP",
            )

        # Extract coordination config to pass to subagents for planning tools inheritance
        coordination_config_path = ""
        if hasattr(self.config, "coordination_config") and self.config.coordination_config:
            parent_coordination_config = self._build_parent_coordination_config_for_subagents()
            if parent_coordination_config:
                coordination_config_path = str(mcp_temp_dir / f"{_token}_coordination_config.json")
                with open(coordination_config_path, "w") as f:
                    json.dump(parent_coordination_config, f)
                logger.info(
                    f"[Orchestrator] Passing coordination config to subagent MCP: {list(parent_coordination_config.keys())}",
                )

        # Get subagent configuration from coordination config
        max_concurrent = 3
        default_timeout = 300
        min_timeout = 60
        max_timeout = 600
        subagent_runtime_mode = "isolated"
        subagent_runtime_fallback_mode = ""
        subagent_host_launch_prefix: list[str] = []
        subagent_orchestrator_config_json = "{}"
        subagent_orchestrator_config_path = ""
        if hasattr(self.config, "coordination_config"):
            if hasattr(self.config.coordination_config, "subagent_max_concurrent"):
                max_concurrent = self.config.coordination_config.subagent_max_concurrent
            if hasattr(self.config.coordination_config, "subagent_default_timeout"):
                default_timeout = self.config.coordination_config.subagent_default_timeout
            if hasattr(self.config.coordination_config, "subagent_min_timeout"):
                min_timeout = self.config.coordination_config.subagent_min_timeout
            if hasattr(self.config.coordination_config, "subagent_max_timeout"):
                max_timeout = self.config.coordination_config.subagent_max_timeout
            # Auto-raise max_timeout when default_timeout exceeds it to avoid
            # silent capping (e.g. subagent_default_timeout: 900 capped to 600).
            if default_timeout > max_timeout:
                max_timeout = default_timeout
            # Get subagent_orchestrator config if present
            if hasattr(self.config.coordination_config, "subagent_orchestrator"):
                so_config = self.config.coordination_config.subagent_orchestrator
                if so_config:
                    so_payload = so_config.to_dict()
                    subagent_orchestrator_config_json = json.dumps(so_payload)
                    # Keep a file-based copy to avoid escaped JSON argument parsing
                    # inconsistencies across MCP runtimes.
                    subagent_orchestrator_config_path = str(
                        mcp_temp_dir / f"{_token}_orchestrator_config.json",
                    )
                    with open(subagent_orchestrator_config_path, "w") as f:
                        json.dump(so_payload, f)
            if hasattr(self.config.coordination_config, "subagent_runtime_mode"):
                subagent_runtime_mode = self.config.coordination_config.subagent_runtime_mode or "isolated"
            if hasattr(self.config.coordination_config, "subagent_runtime_fallback_mode"):
                fallback_mode = self.config.coordination_config.subagent_runtime_fallback_mode
                subagent_runtime_fallback_mode = fallback_mode if fallback_mode else ""
            if hasattr(self.config.coordination_config, "subagent_host_launch_prefix"):
                host_launch_prefix = self.config.coordination_config.subagent_host_launch_prefix
                if isinstance(host_launch_prefix, list):
                    subagent_host_launch_prefix = host_launch_prefix

        # Codex+Docker runs MCP servers in a containerized parent runtime.
        # Without a host-launch bridge, use the secure outbox delegation pattern instead.
        # This creates an isolated container for each subagent via SubagentLaunchWatcher,
        # avoiding Docker socket mounting (critical security risk).
        backend_cfg = None
        if hasattr(self, "agents") and isinstance(self.agents, dict):
            parent_agent = self.agents.get(agent_id)
            if parent_agent is not None and hasattr(parent_agent, "backend") and hasattr(parent_agent.backend, "config") and isinstance(parent_agent.backend.config, dict):
                backend_cfg = parent_agent.backend.config
        if backend_cfg is None and hasattr(agent, "backend") and hasattr(agent.backend, "config"):
            backend_cfg = agent.backend.config
        if (
            isinstance(backend_cfg, dict)
            and str(backend_cfg.get("type", "")).lower() == "codex"
            and str(backend_cfg.get("command_line_execution_mode", "local")).lower() == "docker"
            and subagent_runtime_mode == "isolated"
            and not subagent_runtime_fallback_mode
            and self._delegation_dir is not None
        ):
            subagent_runtime_mode = "delegated"
            logger.info(
                "[Orchestrator] Enabling delegated subagent mode for Codex Docker backend " f"(delegation_dir={self._delegation_dir})",
            )
            # Start the SubagentLaunchWatcher on the host (first time only)
            if self._subagent_launch_watcher is None:
                try:
                    from massgen.subagent.launch_watcher import SubagentLaunchWatcher

                    self._subagent_launch_watcher = SubagentLaunchWatcher(
                        delegation_dir=self._delegation_dir,
                        # Use the .massgen dir (parent of both subagent_logs/ and
                        # workspaces/) so actual subagent workspaces are accepted.
                        # Using only _subagent_logs_dir blocked all spawns because
                        # workspaces live under the sibling workspaces/ directory.
                        allowed_workspace_roots=[self._subagent_logs_dir.parent.parent],
                    )
                    import asyncio as _asyncio

                    _asyncio.get_event_loop().create_task(self._subagent_launch_watcher.start())
                    logger.info("[Orchestrator] Started SubagentLaunchWatcher")
                except Exception as e:
                    logger.warning(
                        f"[Orchestrator] Failed to start SubagentLaunchWatcher: {e}. " "Falling back to inherited mode.",
                    )
                    subagent_runtime_mode = "inherited"
                    subagent_runtime_fallback_mode = "inherited"
            # Register this agent's workspace as an allowed root for delegated spawns
            if self._subagent_launch_watcher is not None:
                self._subagent_launch_watcher.add_allowed_root(workspace_root)
        elif (
            isinstance(backend_cfg, dict)
            and str(backend_cfg.get("type", "")).lower() == "codex"
            and str(backend_cfg.get("command_line_execution_mode", "local")).lower() == "docker"
            and subagent_runtime_mode == "isolated"
            and not subagent_runtime_fallback_mode
        ):
            # delegation_dir not available — fall back to inherited (legacy behavior)
            subagent_runtime_fallback_mode = "inherited"
            logger.info(
                "[Orchestrator] Defaulting subagent runtime fallback to 'inherited' for Codex Docker mode " "(delegation directory not available)",
            )

        # Discover specialized subagent types and write SUBAGENT.md dirs to the workspace.
        # The MCP server scans these lazily on first spawn_subagents call instead of
        # reading from a JSON file at startup, eliminating a fragile file-path arg chain.
        # Also re-written at the start of each round in _stream_agent_execution so they
        # survive workspace clears between rounds.
        self._write_subagent_type_dirs(workspace_root)

        # Get log directory for subagent logs.
        # Use the dedicated subagent logs dir (Docker-mountable) if available,
        # otherwise fall back to the session log dir.
        log_directory = ""
        if self._subagent_logs_dir is not None:
            log_directory = str(self._subagent_logs_dir.resolve())
        else:
            try:
                log_dir = get_log_session_dir()
                if log_dir:
                    log_directory = str(log_dir.resolve())
            except Exception:
                pass  # Log directory not configured

        args = [
            "run",
            f"{script_path}:create_server",
            "--",
            "--agent-id",
            agent_id,
            "--orchestrator-id",
            self.orchestrator_id,
            "--workspace-path",
            workspace_path,
            "--agent-temporary-workspace",
            agent_temporary_workspace_path,
            "--agent-configs-file",
            agent_configs_path,
            "--max-concurrent",
            str(max_concurrent),
            "--default-timeout",
            str(default_timeout),
            "--min-timeout",
            str(min_timeout),
            "--max-timeout",
            str(max_timeout),
            "--orchestrator-config-file",
            subagent_orchestrator_config_path,
            "--log-directory",
            log_directory,
            "--context-paths-file",
            context_paths_path,
            "--coordination-config-file",
            coordination_config_path,
            "--runtime-mode",
            subagent_runtime_mode,
            "--runtime-fallback-mode",
            subagent_runtime_fallback_mode,
            "--host-launch-prefix",
            json.dumps(subagent_host_launch_prefix),
            "--delegation-directory",
            str(self._delegation_dir.resolve()) if self._delegation_dir is not None else "",
        ]
        if not subagent_orchestrator_config_path:
            args.extend(
                [
                    "--orchestrator-config",
                    subagent_orchestrator_config_json,
                ],
            )

        # Pass hook directory for MCP server-level hook injection (Codex)
        if hasattr(agent.backend, "supports_mcp_server_hooks") and agent.backend.supports_mcp_server_hooks():
            hook_dir = agent.backend.get_hook_dir()
            args.extend(["--hook-dir", str(hook_dir)])

        # Build env for the MCP server process. Codex replaces (not merges)
        # the process env with config.toml's "env" field, so we must explicitly
        # include API keys the subagent subprocess needs. Reuse the backend's
        # credential env builder if available (Codex backend), otherwise just
        # suppress the FastMCP banner.
        mcp_env: dict[str, str] = {"FASTMCP_SHOW_CLI_BANNER": "false"}
        if hasattr(agent.backend, "_build_custom_tools_mcp_env"):
            mcp_env = agent.backend._build_custom_tools_mcp_env()

        config: dict[str, Any] = {
            "name": self._subagent_server_name(agent_id),
            "type": "stdio",
            "command": "fastmcp",
            "args": args,
            "env": mcp_env,
            # Blocking spawn_subagents can run near subagent_default_timeout.
            # Raise per-tool timeout so Codex MCP does not fail at 60s.
            "tool_timeout_sec": int(default_timeout) + 60,
        }

        logger.info(
            f"[Orchestrator] Created subagent MCP config for {agent_id} with workspace: {workspace_path}",
        )

        return config

    # ------------------------------------------------------------------
    # Pre-collab shared helpers
    # ------------------------------------------------------------------

    def _build_parent_agent_configs(self) -> list[dict[str, Any]]:
        """Build simplified agent configs for subagent inheritance."""
        configs: list[dict[str, Any]] = []
        for agent_id, agent in self.agents.items():
            agent_cfg: dict[str, Any] = {"id": agent_id}
            if hasattr(agent, "backend") and hasattr(agent.backend, "config"):
                backend_cfg = {k: v for k, v in agent.backend.config.items() if k not in ("mcp_servers", "_config_path")}
                agent_cfg["backend"] = backend_cfg
            configs.append(agent_cfg)
        return configs

    def _get_parent_workspace(self, fallback_prefix: str = "massgen_precollab_") -> str:
        """Return the first agent's workspace path, or a temp dir."""
        for agent in self.agents.values():
            fm = getattr(getattr(agent, "backend", None), "filesystem_manager", None)
            if fm and fm.cwd:
                return str(fm.cwd)
        import tempfile

        return tempfile.mkdtemp(prefix=fallback_prefix)

    @staticmethod
    def _get_log_directory() -> str | None:
        """Return the current log session directory as a string, or None."""
        try:
            log_dir = get_log_session_dir()
            return str(log_dir) if log_dir else None
        except Exception:
            return None

    def _get_pre_collab_voting_threshold(self) -> int | None:
        """Return the voting threshold for pre-collab subagent runs."""
        threshold = getattr(
            self.config.coordination_config,
            "pre_collab_voting_threshold",
            None,
        )
        if threshold is None:
            threshold = getattr(self.config, "voting_threshold", None)
        return threshold

    def _get_fast_iteration_mode(self) -> bool:
        """Return whether fast iteration mode is enabled."""
        return getattr(
            getattr(self.config, "coordination_config", None),
            "fast_iteration_mode",
            False,
        )

    def _make_precollab_started_callback(
        self,
        anchor_agent: str | None,
        call_id: str,
        display: Any,
    ):
        """Build a callback for pre-collab subagent start notifications."""

        def _on_started(
            subagent_id: str,
            subagent_task: str,
            timeout_seconds: int,
            status_callback: Any,
            log_path: str | None,
        ) -> None:
            _emitter = get_event_emitter()
            if _emitter:
                _emitter.emit_raw(
                    StructuredEventType.PRE_COLLAB_STARTED,
                    agent_id=anchor_agent,
                    subagent_id=subagent_id,
                    task=subagent_task,
                    timeout_seconds=timeout_seconds,
                    call_id=call_id,
                    log_path=log_path,
                )
            if display and anchor_agent and hasattr(display, "notify_runtime_subagent_started"):
                try:
                    display.notify_runtime_subagent_started(
                        agent_id=anchor_agent,
                        subagent_id=subagent_id,
                        task=subagent_task,
                        timeout_seconds=timeout_seconds,
                        call_id=call_id,
                        status_callback=status_callback,
                        log_path=log_path,
                    )
                except Exception:
                    pass

        return _on_started

    def _notify_precollab_completed(
        self,
        anchor_agent: str | None,
        subagent_id: str,
        call_id: str,
        display: Any,
        *,
        status: str = "completed",
        answer_preview: str = "",
        error: str | None = None,
    ) -> None:
        """Emit event + notify display for a pre-collab phase completion."""
        _emitter = get_event_emitter()
        kwargs: dict[str, Any] = {
            "agent_id": anchor_agent,
            "subagent_id": subagent_id,
            "call_id": call_id,
            "status": status,
        }
        if error:
            kwargs["error"] = error
        if answer_preview:
            kwargs["answer_preview"] = answer_preview
        if _emitter and anchor_agent:
            _emitter.emit_raw(StructuredEventType.PRE_COLLAB_COMPLETED, **kwargs)

        if display and anchor_agent and hasattr(display, "notify_runtime_subagent_completed"):
            try:
                display.notify_runtime_subagent_completed(**kwargs)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Pre-collab phases
    # ------------------------------------------------------------------

    async def _generate_and_inject_personas(self) -> None:
        """Generate diverse personas for all agents and inject into their system messages."""
        if not hasattr(self.config, "coordination_config"):
            return
        if not hasattr(self.config.coordination_config, "persona_generator"):
            return
        if not self.config.coordination_config.persona_generator.enabled:
            logger.info("[Orchestrator] Persona generation disabled in config")
            return
        if self._personas_generated:
            logger.info("[Orchestrator] Personas already generated, skipping")
            return

        logger.info(
            f"[Orchestrator] Generating personas for {len(self.agents)} agents via subagent",
        )

        display = getattr(self.coordination_ui, "display", None) if self.coordination_ui else None
        anchor_agent = next(iter(self.agents.keys()), None)
        call_id = "persona_generation_persona_generation"

        try:
            pg_config = self.config.coordination_config.persona_generator
            generator = PersonaGenerator(
                guidelines=pg_config.persona_guidelines,
                diversity_mode=pg_config.diversity_mode,
            )

            existing_messages = {}
            for agent_id, agent in self.agents.items():
                if hasattr(agent, "get_configurable_system_message"):
                    existing_messages[agent_id] = agent.get_configurable_system_message()
                else:
                    existing_messages[agent_id] = None

            personas = await generator.generate_personas_via_subagent(
                agent_ids=list(self.agents.keys()),
                task=self.current_task or "Complete the assigned task",
                existing_system_messages=existing_messages,
                parent_agent_configs=self._build_parent_agent_configs(),
                parent_workspace=self._get_parent_workspace("massgen_persona_"),
                orchestrator_id=self.orchestrator_id,
                log_directory=self._get_log_directory(),
                on_subagent_started=self._make_precollab_started_callback(
                    anchor_agent,
                    call_id,
                    display,
                ),
                voting_sensitivity=getattr(self.config, "voting_sensitivity", None),
                voting_threshold=self._get_pre_collab_voting_threshold(),
                has_planning_spec_context=bool(self._plan_session_id),
                fast_iteration_mode=self._get_fast_iteration_mode(),
            )

            source = getattr(generator, "last_generation_source", "unknown")

            # Build preview from personas
            preview_entries: list[str] = []
            for aid, persona in personas.items():
                summary = persona.attributes.get(
                    "approach_summary",
                    persona.attributes.get("thinking_style", ""),
                )
                if summary:
                    preview_entries.append(f"{aid}: {summary}")
                if len(preview_entries) >= 2:
                    break
            preview = " | ".join(preview_entries)[:400]

            if source == "subagent":
                self._notify_precollab_completed(
                    anchor_agent,
                    "persona_generation",
                    call_id,
                    display,
                    answer_preview=preview or "Personas generated successfully.",
                )
            else:
                self._notify_precollab_completed(
                    anchor_agent,
                    "persona_generation",
                    call_id,
                    display,
                    status="failed",
                    error="Used fallback personas.",
                )

            self._generated_personas = personas
            self._original_system_messages = existing_messages
            self._personas_generated = True

            for agent_id, persona in personas.items():
                approach = persona.attributes.get(
                    "approach_summary",
                    persona.attributes.get("thinking_style", "unknown"),
                )
                logger.info(
                    f"[Orchestrator] Generated persona for {agent_id}: {approach}",
                )

            self._save_personas_to_log(personas)
            logger.info(
                f"[Orchestrator] Successfully generated and injected {len(personas)} personas",
            )

        except Exception as e:
            logger.error(f"[Orchestrator] Failed to generate personas: {e}")
            logger.warning("[Orchestrator] Continuing without persona generation")
            self._notify_precollab_completed(
                anchor_agent,
                "persona_generation",
                call_id,
                display,
                status="failed",
                error=str(e),
            )
            self._personas_generated = True  # Don't retry on failure

    async def _generate_and_inject_evaluation_criteria(self) -> None:
        """Generate task-specific evaluation criteria via a pre-collab subagent run."""
        if not hasattr(self.config, "coordination_config"):
            return
        if not hasattr(self.config.coordination_config, "evaluation_criteria_generator"):
            return
        if not self.config.coordination_config.evaluation_criteria_generator.enabled:
            logger.info("[Orchestrator] Evaluation criteria generation disabled in config")
            return
        if self._evaluation_criteria_generated:
            logger.info("[Orchestrator] Evaluation criteria already generated, skipping")
            return

        logger.info("[Orchestrator] Generating evaluation criteria via subagent")

        display = getattr(self.coordination_ui, "display", None) if self.coordination_ui else None
        anchor_agent = next(iter(self.agents.keys()), None)
        call_id = "criteria_generation_criteria_generation"

        try:
            from .evaluation_criteria_generator import EvaluationCriteriaGenerator

            ecg = self.config.coordination_config.evaluation_criteria_generator
            generator = EvaluationCriteriaGenerator()

            has_changedoc = getattr(
                self.config.coordination_config,
                "enable_changedoc",
                False,
            )

            criteria = await generator.generate_criteria_via_subagent(
                task=self.current_task or "",
                agent_configs=self._build_parent_agent_configs(),
                has_changedoc=has_changedoc,
                parent_workspace=self._get_parent_workspace("massgen_criteria_"),
                log_directory=self._get_log_directory(),
                orchestrator_id=self.orchestrator_id,
                min_criteria=ecg.min_criteria,
                max_criteria=ecg.max_criteria,
                on_subagent_started=self._make_precollab_started_callback(
                    anchor_agent,
                    call_id,
                    display,
                ),
                voting_sensitivity=getattr(self.config, "voting_sensitivity", None),
                voting_threshold=self._get_pre_collab_voting_threshold(),
                has_planning_spec_context=bool(self._plan_session_id),
                fast_iteration_mode=self._get_fast_iteration_mode(),
            )

            self._generated_evaluation_criteria = criteria
            self._evaluation_criteria_generated = True

            # Re-initialize checklist tool now that generated criteria are available.
            self._init_checklist_tool()
            self._save_evaluation_criteria_to_log(criteria)

            source = generator.last_generation_source
            logger.info(
                f"[Orchestrator] Generated {len(criteria)} evaluation criteria (source: {source})",
            )

            crit_preview = " | ".join(f"{c.id}: {c.text[:60]}..." if len(c.text) > 60 else f"{c.id}: {c.text}" for c in criteria[:3])
            if source == "subagent":
                self._notify_precollab_completed(
                    anchor_agent,
                    "criteria_generation",
                    call_id,
                    display,
                    answer_preview=crit_preview or f"{len(criteria)} criteria generated.",
                )
            else:
                self._notify_precollab_completed(
                    anchor_agent,
                    "criteria_generation",
                    call_id,
                    display,
                    answer_preview=f"Using {len(criteria)} fallback criteria.",
                )

        except Exception as e:
            logger.error(f"[Orchestrator] Failed to generate evaluation criteria: {e}")
            logger.warning("[Orchestrator] Continuing without criteria generation")
            self._evaluation_criteria_generated = True  # Don't retry on failure
            self._notify_precollab_completed(
                anchor_agent,
                "criteria_generation",
                call_id,
                display,
                status="failed",
                error=str(e),
            )

    async def _improve_and_inject_prompt(self) -> None:
        """Improve the task prompt via a pre-collab subagent consensus run."""
        if not hasattr(self.config, "coordination_config"):
            return
        if not hasattr(self.config.coordination_config, "prompt_improver"):
            return
        if not self.config.coordination_config.prompt_improver.enabled:
            return
        if self._prompt_improved:
            logger.info("[Orchestrator] Prompt already improved, skipping")
            return

        logger.info("[Orchestrator] Improving prompt via subagent")

        display = getattr(self.coordination_ui, "display", None) if self.coordination_ui else None
        anchor_agent = next(iter(self.agents.keys()), None)
        call_id = "prompt_improvement_prompt_improvement"

        try:
            from .prompt_improver import PromptImprover

            improver = PromptImprover()

            improved = await improver.improve_prompt_via_subagent(
                task=self.current_task or "",
                agent_configs=self._build_parent_agent_configs(),
                parent_workspace=self._get_parent_workspace("massgen_prompt_"),
                log_directory=self._get_log_directory(),
                orchestrator_id=self.orchestrator_id,
                on_subagent_started=self._make_precollab_started_callback(
                    anchor_agent,
                    call_id,
                    display,
                ),
                voting_sensitivity=getattr(self.config, "voting_sensitivity", None),
                voting_threshold=self._get_pre_collab_voting_threshold(),
                fast_iteration_mode=self._get_fast_iteration_mode(),
            )

            self._prompt_improved = True

            if improved:
                self.current_task = improved
                logger.info(
                    f"[Orchestrator] Prompt improved ({len(improved)} chars)",
                )
                if display and hasattr(display, "notify_prompt_improved"):
                    try:
                        display.notify_prompt_improved(improved)
                    except Exception:
                        pass
            else:
                logger.info(
                    "[Orchestrator] Prompt improvement returned no result, keeping original",
                )

            self._notify_precollab_completed(
                anchor_agent,
                "prompt_improvement",
                call_id,
                display,
                answer_preview=(f"Improved prompt ({len(improved)} chars)" if improved else "Using original prompt"),
            )

        except Exception as e:
            logger.error(f"[Orchestrator] Failed to improve prompt: {e}")
            logger.warning("[Orchestrator] Continuing without prompt improvement")
            self._prompt_improved = True
            self._notify_precollab_completed(
                anchor_agent,
                "prompt_improvement",
                call_id,
                display,
                status="failed",
                error=str(e),
            )

    def _save_evaluation_criteria_to_log(self, criteria: list) -> None:
        """Save generated evaluation criteria to a YAML file in the log directory."""
        try:
            import yaml

            log_dir = get_log_session_dir()
            criteria_file = log_dir / "generated_evaluation_criteria.yaml"
            criteria_data = [{"id": c.id, "text": c.text, "category": c.category, **({"verify_by": c.verify_by} if c.verify_by else {})} for c in criteria]
            with open(criteria_file, "w") as f:
                yaml.dump(criteria_data, f, default_flow_style=False)
            logger.info(f"[Orchestrator] Saved evaluation criteria to {criteria_file}")
        except Exception as e:
            logger.debug(f"[Orchestrator] Failed to save evaluation criteria to log: {e}")

    @staticmethod
    def _has_peer_answers(
        agent_id: str,
        answers: dict[str, Any] | None,
    ) -> bool:
        """Return True when at least one answer exists from another agent."""
        if not answers:
            return False
        return any(other_agent_id != agent_id for other_agent_id in answers.keys())

    def _get_persona_for_agent(
        self,
        agent_id: str,
        has_peer_answers: bool,
    ) -> str | None:
        """Get the appropriate persona text for an agent based on phase.

        Args:
            agent_id: The agent ID
            has_peer_answers: True if agent has seen answers from other agents (eased phase)

        Returns:
            The persona text to prepend, or None if no persona exists
        """
        if not self._generated_personas:
            return None

        persona = self._generated_personas.get(agent_id)
        if not persona:
            return None

        if has_peer_answers:
            mode = self.config.coordination_config.persona_generator.after_first_answer
            if mode == "drop":
                return None
            elif mode == "keep":
                return persona.persona_text
            else:  # "soften"
                return persona.get_softened_text()
        else:
            # Exploration phase - always use strong perspective
            return persona.persona_text

    def get_generated_personas(self) -> dict[str, Any]:
        """Get the generated personas for persistence across turns.

        Returns:
            Dictionary of agent_id -> GeneratedPersona
        """
        return self._generated_personas

    def get_generated_evaluation_criteria(self) -> list | None:
        """Get the generated evaluation criteria for persistence across turns.

        Returns:
            List of GeneratedCriterion objects, or None if not generated.
        """
        return self._generated_evaluation_criteria

    def _save_personas_to_log(self, personas: dict[str, Any]) -> None:
        """
        Save generated personas to a YAML file in the log directory.

        Args:
            personas: Dictionary mapping agent_id to GeneratedPersona
        """
        try:
            import yaml

            from .logger_config import get_log_session_dir

            log_dir = get_log_session_dir()
            personas_file = log_dir / "generated_personas.yaml"

            # Convert personas to serializable dict
            personas_data = {}
            for agent_id, persona in personas.items():
                personas_data[agent_id] = {
                    "persona_text": persona.persona_text,
                    "attributes": persona.attributes,
                }

            with open(personas_file, "w") as f:
                yaml.dump(personas_data, f, default_flow_style=False, sort_keys=False)

            logger.info(f"[Orchestrator] Saved personas to {personas_file}")

        except Exception as e:
            logger.warning(f"[Orchestrator] Failed to save personas to log: {e}")

    @staticmethod
    def _get_chunk_type_value(chunk) -> str:
        """
        Extract chunk type as string, handling both legacy and typed chunks.

        Args:
            chunk: StreamChunk, TextStreamChunk, or MultimodalStreamChunk

        Returns:
            String representation of chunk type (e.g., "content", "tool_calls")
        """
        chunk_type = chunk.type

        if isinstance(chunk_type, ChunkType):
            return chunk_type.value

        return str(chunk_type)

    def _trace_tuple(
        self,
        text: str,
        *,
        kind: str = "agent_status",
        tool_call_id: str | None = None,
    ) -> tuple:
        """Map coordination/status text to a non-content type when strict tracing is enabled.

        Returns a 3-tuple (type, content, tool_call_id) to preserve tool tracking info.
        """
        if self.trace_classification == "strict":
            return (kind, text, tool_call_id)
        return ("content", text, tool_call_id)

    @staticmethod
    def _is_tool_related_content(content: str) -> bool:
        """
        Defensive check: exclude tool-related output from clean answer text.

        This guards against backends (e.g., ClaudeCode) that may embed tool
        output or status messages in content-type chunks. Normally these are
        handled via separate chunk_type branches (mcp_status, backend_status,
        custom_tool_status), but this catches any that leak through.

        Args:
            content: The content string to check

        Returns:
            True if content is tool-related and should be excluded from clean answer
        """
        if not content:
            return False

        # Tool output prefixed by orchestrator for mcp_status / custom_tool_status
        if content.startswith("🔧 "):
            return True

        # Backend status messages (session info from ClaudeCode)
        if content.startswith("Final Temp Working directory:"):
            return True
        if content.startswith("Final Session ID:"):
            return True

        return False

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] = None,
        reset_chat: bool = False,
        clear_history: bool = False,
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Main chat interface - handles user messages and coordinates sub-agents.

        Args:
            messages: List of conversation messages
            tools: Ignored by orchestrator (uses internal workflow tools)
            reset_chat: If True, reset conversation and start fresh
            clear_history: If True, clear history before processing

        Yields:
            StreamChunk: Streaming response chunks
        """
        # External (client-provided) tools: these are passed through to backends so models
        # can request them, but MassGen will NOT execute them (backends treat unknown tools
        # as provider_calls and emit StreamChunk(type="tool_calls")).
        self._external_tools = tools or []

        # Handle conversation management
        if clear_history:
            self.conversation_history.clear()
        if reset_chat:
            self.reset()

        # Process all messages to build conversation context
        conversation_context = self._build_conversation_context(messages)
        user_message = conversation_context.get("current_message")

        if not user_message:
            log_stream_chunk(
                "orchestrator",
                "error",
                "No user message found in conversation",
            )
            yield StreamChunk(
                type="error",
                error="No user message found in conversation",
            )
            return

        # Add user message to history (skip on restart to avoid duplication)
        if self.current_attempt == 0:
            self.add_to_history("user", user_message)

        # Determine what to do based on current state and conversation context
        if self.workflow_phase == "idle":
            # Emit preparation status
            yield StreamChunk(
                type="preparation_status",
                status="Preparing coordination...",
                detail="Setting up orchestrator",
            )

            # New task - start MassGen coordination with full context
            self.current_task = user_message
            self._original_task = user_message  # Snapshot for prompt evolution

            # Prepare paraphrases if DSPy is enabled
            if self.dspy_paraphraser:
                yield StreamChunk(
                    type="preparation_status",
                    status="Generating prompt variants...",
                    detail="DSPy paraphrasing",
                )
            await self._prepare_paraphrases_for_agents(self.current_task)

            # Reinitialize session with user prompt now that we have it (MAS-199: includes log_path)
            log_dir = get_log_session_dir()
            log_path = str(log_dir) if log_dir else None
            self.coordination_tracker.initialize_session(
                list(self.agents.keys()),
                self.current_task,
                log_path=log_path,
            )
            self.workflow_phase = "coordinating"

            # Reset restart_pending flag at start of coordination (will be set again if restart needed)
            self.restart_pending = False
            self._fairness_pause_log_reasons.clear()
            self._fairness_block_log_states.clear()

            # Runtime-injection delivery history should be scoped to a single turn.
            if self.current_attempt == 0 and self._human_input_hook:
                clear_history = getattr(self._human_input_hook, "clear_delivery_history", None)
                if callable(clear_history):
                    clear_history()

            # Clear context path write tracking at start of each turn
            self._clear_context_path_write_tracking()

            # Clear agent workspaces for new turn (if this is a multi-turn conversation with history)
            # Skip on restart attempts - workspace should be preserved from previous attempt
            if (
                self.current_attempt == 0
                and conversation_context
                and conversation_context.get(
                    "conversation_history",
                )
            ):
                self._clear_agent_workspaces()

            # On restart, inject accumulated conversation history so agents have context
            if self.current_attempt > 0 and self.conversation_history:
                conversation_context["conversation_history"] = list(self.conversation_history)

            # Check if planning mode is enabled in config
            planning_mode_config_exists = (
                self.config.coordination_config and self.config.coordination_config.enable_planning_mode if self.config and hasattr(self.config, "coordination_config") else False
            )

            if planning_mode_config_exists:
                yield StreamChunk(
                    type="preparation_status",
                    status="Analyzing task...",
                    detail="Checking for irreversible operations",
                )
                # Analyze question for irreversibility and set planning mode accordingly
                # This happens silently - users don't see this analysis
                analysis_result = await self._analyze_question_irreversibility(
                    user_message,
                    conversation_context,
                )
                has_irreversible = analysis_result["has_irreversible"]
                blocked_tools = analysis_result["blocked_tools"]

                # Set planning mode and blocked tools for all agents based on analysis
                for agent_id, agent in self.agents.items():
                    if hasattr(agent.backend, "set_planning_mode"):
                        agent.backend.set_planning_mode(has_irreversible)
                        if hasattr(agent.backend, "set_planning_mode_blocked_tools"):
                            agent.backend.set_planning_mode_blocked_tools(blocked_tools)
                        log_orchestrator_activity(
                            self.orchestrator_id,
                            f"Set planning mode for {agent_id}",
                            {
                                "planning_mode_enabled": has_irreversible,
                                "blocked_tools_count": len(blocked_tools),
                                "reason": "irreversibility analysis",
                            },
                        )

            # Starting actual coordination
            yield StreamChunk(
                type="preparation_status",
                status="Starting coordination...",
                detail=f"{len(self.agents)} agents ready",
            )

            async for chunk in self._coordinate_agents_with_timeout(
                conversation_context,
            ):
                yield chunk

        elif self.workflow_phase == "presenting":
            # Handle follow-up question with full conversation context
            async for chunk in self._handle_followup(
                user_message,
                conversation_context,
            ):
                yield chunk
        else:
            # Already coordinating - provide status update
            log_stream_chunk(
                "orchestrator",
                "content",
                "🔄 Coordinating agents, please wait...",
            )
            chunk_type = "coordination" if self.trace_classification == "strict" else "content"
            yield StreamChunk(
                type=chunk_type,
                content="🔄 Coordinating agents, please wait...",
            )
            # Note: In production, you might want to queue follow-up questions

    async def chat_simple(self, user_message: str) -> AsyncGenerator[StreamChunk, None]:
        """
        Backwards compatible simple chat interface.

        Args:
            user_message: Simple string message from user

        Yields:
            StreamChunk: Streaming response chunks
        """
        messages = [{"role": "user", "content": user_message}]
        async for chunk in self.chat(messages):
            yield chunk

    def _build_conversation_context(
        self,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build conversation context from message list."""
        conversation_history = []
        current_message = None

        # Process messages to extract conversation history and current message
        for message in messages:
            role = message.get("role")
            content = message.get("content", "")

            if role == "user":
                current_message = content
                # Add to history (excluding the current message)
                if len(conversation_history) > 0 or len(messages) > 1:
                    conversation_history.append(message.copy())
            elif role == "assistant":
                conversation_history.append(message.copy())
            elif role == "tool":
                # Preserve tool results for multi-turn tool calling.
                conversation_history.append(message.copy())
            elif role == "system":
                # System messages are typically not part of conversation history
                pass

        # Remove the last user message from history since that's the current message
        if conversation_history and conversation_history[-1].get("role") == "user":
            conversation_history.pop()

        return {
            "current_message": current_message,
            "conversation_history": conversation_history,
            "full_messages": messages,
        }

    async def _inject_shared_memory_context(
        self,
        messages: list[dict[str, Any]],
        agent_id: str,
    ) -> list[dict[str, Any]]:
        """
        Inject shared memory context into agent messages.

        This allows all agents to see shared memories including what other agents
        have stored in the shared memory.

        Args:
            messages: Original messages to send to agent
            agent_id: ID of the agent receiving the messages

        Returns:
            Messages with shared memory context injected
        """
        if not self.shared_conversation_memory and not self.shared_persistent_memory:
            # No shared memory configured, return original messages
            return messages

        memory_context_parts = []

        # Get conversation memory content
        if self.shared_conversation_memory:
            try:
                conv_messages = await self.shared_conversation_memory.get_messages()
                if conv_messages:
                    memory_context_parts.append("=== SHARED CONVERSATION MEMORY ===")
                    for msg in conv_messages[-10:]:  # Last 10 messages
                        role = msg.get("role", "unknown")
                        content = msg.get("content", "")
                        agent_source = msg.get("agent_id", "unknown")
                        memory_context_parts.append(
                            f"[{agent_source}] {role}: {content}",
                        )
            except Exception as e:
                logger.warning(f"Failed to retrieve shared conversation memory: {e}")

        # Get persistent memory content
        if self.shared_persistent_memory:
            try:
                # Extract user message for retrieval
                user_messages = [msg for msg in messages if msg.get("role") == "user"]
                if user_messages:
                    retrieved = await self.shared_persistent_memory.retrieve(
                        user_messages,
                    )
                    if retrieved:
                        memory_context_parts.append(
                            "\n=== SHARED PERSISTENT MEMORY ===",
                        )
                        memory_context_parts.append(retrieved)
            except NotImplementedError:
                # Memory backend doesn't support retrieve
                pass
            except Exception as e:
                logger.warning(f"Failed to retrieve shared persistent memory: {e}")

        # Inject memory context if we have any
        if memory_context_parts:
            memory_message = {
                "role": "system",
                "content": ("You have access to shared memory that all agents can see and contribute to.\n" + "\n".join(memory_context_parts)),
            }

            # Insert after existing system messages but before user messages
            system_count = sum(1 for msg in messages if msg.get("role") == "system")
            modified_messages = messages.copy()
            modified_messages.insert(system_count, memory_message)
            return modified_messages

        return messages

    def _merge_agent_memories_to_winner(self, winning_agent_id: str) -> None:
        """
        Merge memory directories from all agents into the winning agent's workspace.

        This ensures memories created by any agent during coordination are preserved
        in the final snapshot, regardless of which agent won.

        Args:
            winning_agent_id: ID of the agent selected as final presenter
        """
        if not hasattr(self.config, "coordination_config") or not hasattr(
            self.config.coordination_config,
            "enable_memory_filesystem_mode",
        ):
            return

        if not self.config.coordination_config.enable_memory_filesystem_mode:
            logger.debug(
                "[Orchestrator] Memory filesystem mode not enabled, skipping memory merge",
            )
            return

        winning_agent = self.agents.get(winning_agent_id)
        if not winning_agent or not hasattr(winning_agent, "backend") or not winning_agent.backend.filesystem_manager:
            logger.warning(
                f"[Orchestrator] Cannot merge memories - winning agent {winning_agent_id} has no filesystem manager",
            )
            return

        winner_memory_base = Path(winning_agent.backend.filesystem_manager.cwd) / "memory"
        winner_memory_base.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"[Orchestrator] Merging memories from all agents into {winning_agent_id}'s workspace",
        )

        merged_count = 0
        for agent_id, agent in self.agents.items():
            if agent_id == winning_agent_id:
                continue  # Skip winner's own memories

            if not hasattr(agent, "backend") or not agent.backend.filesystem_manager:
                continue

            agent_memory_base = Path(agent.backend.filesystem_manager.cwd) / "memory"
            if not agent_memory_base.exists():
                continue

            # Merge short_term and long_term directories
            for tier in ["short_term", "long_term"]:
                source_tier_dir = agent_memory_base / tier
                if not source_tier_dir.exists():
                    continue

                dest_tier_dir = winner_memory_base / tier
                dest_tier_dir.mkdir(parents=True, exist_ok=True)

                # Copy all .md files from this agent's tier
                for memory_file in source_tier_dir.glob("*.md"):
                    dest_file = dest_tier_dir / memory_file.name

                    # If file already exists in winner's workspace, append with agent attribution
                    if dest_file.exists():
                        try:
                            existing_content = dest_file.read_text()
                            new_content = memory_file.read_text()
                            combined = f"{existing_content}\n\n---\n\n# From Agent {agent_id}\n\n{new_content}"
                            dest_file.write_text(combined)
                            logger.info(
                                f"[Orchestrator] Merged {memory_file.name} from {agent_id} (appended)",
                            )
                            merged_count += 1
                        except Exception as e:
                            logger.warning(
                                f"[Orchestrator] Failed to merge {memory_file.name} from {agent_id}: {e}",
                            )
                    else:
                        # File doesn't exist in winner's workspace, copy it
                        try:
                            import shutil

                            shutil.copy2(memory_file, dest_file)
                            logger.info(
                                f"[Orchestrator] Copied {memory_file.name} from {agent_id}",
                            )
                            merged_count += 1
                        except Exception as e:
                            logger.warning(
                                f"[Orchestrator] Failed to copy {memory_file.name} from {agent_id}: {e}",
                            )

        logger.info(
            f"[Orchestrator] Memory merge complete: {merged_count} files merged from other agents into {winning_agent_id}'s workspace",
        )

    async def _record_to_shared_memory(
        self,
        agent_id: str,
        content: str,
        role: str = "assistant",
    ) -> None:
        """
        Record agent's contribution to shared memory.

        Args:
            agent_id: ID of the agent contributing
            content: Content to record
            role: Role of the message (default: "assistant")
        """
        message = {
            "role": role,
            "content": content,
            "agent_id": agent_id,
            "timestamp": time.time(),
        }

        # Add to conversation memory
        if self.shared_conversation_memory:
            try:
                await self.shared_conversation_memory.add(message)
            except Exception as e:
                logger.warning(f"Failed to add to shared conversation memory: {e}")

        # Record to persistent memory
        if self.shared_persistent_memory:
            try:
                await self.shared_persistent_memory.record([message])
            except NotImplementedError:
                # Memory backend doesn't support record
                pass
            except Exception as e:
                logger.warning(f"Failed to record to shared persistent memory: {e}")

    def save_coordination_logs(self):
        """Public method to save coordination logs after final presentation is complete."""
        logger.info("[Orchestrator] save_coordination_logs called")
        # End the coordination session
        self.coordination_tracker._end_session()

        # Save coordination logs using the coordination tracker
        log_session_dir = get_log_session_dir()
        if log_session_dir:
            logger.info(f"[Orchestrator] Saving to {log_session_dir}")
            self.coordination_tracker.save_coordination_logs(log_session_dir)
            # Also save final status.json with complete token/cost data
            self.coordination_tracker.save_status_file(
                log_session_dir,
                orchestrator=self,
            )
            # Save detailed metrics files
            self.save_metrics(log_session_dir)

    def finalize_step_mode(self, log_dir: Path) -> None:
        """Write post-coordination artifacts for step mode runs.

        Replicates the normal-mode finalization sequence so that step mode
        log directories have the same structure (final/, status.json,
        coordination_events.json, metrics) that downstream tools expect.

        Args:
            log_dir: The log session directory.
        """
        import shutil

        action_data = self._step_action_data or {}
        agent_id = action_data.get("agent_id", "")
        action = action_data.get("action", "")
        answer_text = action_data.get("answer_text")
        workspace_path = action_data.get("workspace_path")

        # Write final/ directory for answer actions
        if action == "new_answer" and answer_text is not None:
            final_dir = log_dir / "final" / agent_id
            final_dir.mkdir(parents=True, exist_ok=True)

            # Normalize workspace paths so answer references the adjacent workspace/
            normalized_answer = answer_text
            if workspace_path:
                dest_workspace = str(final_dir / "workspace")
                normalized_answer = normalized_answer.replace(
                    str(workspace_path),
                    dest_workspace,
                )
                resolved_ws = str(Path(workspace_path).resolve())
                if resolved_ws != str(workspace_path):
                    normalized_answer = normalized_answer.replace(
                        resolved_ws,
                        dest_workspace,
                    )

            (final_dir / "answer.txt").write_text(normalized_answer)

            # Copy workspace to final/ if available
            if workspace_path:
                ws_src = Path(workspace_path)
                if ws_src.is_dir():
                    ws_dest = final_dir / "workspace"
                    shutil.copytree(ws_src, ws_dest, symlinks=True, dirs_exist_ok=True)

            # Record in coordination tracker
            self.coordination_tracker.set_final_answer(
                agent_id,
                answer_text,
                snapshot_timestamp="final",
            )

        # Save coordination logs (status.json, coordination_events.json, metrics)
        self.coordination_tracker._end_session()
        self.coordination_tracker.save_coordination_logs(log_dir)
        self.coordination_tracker.save_status_file(log_dir, orchestrator=self)
        self.save_metrics(log_dir)

    def save_metrics(self, log_dir: Path):
        """Save detailed metrics files for analysis.

        Outputs:
            - metrics_events.json: Detailed event log of all tool executions and round completions
            - metrics_summary.json: Aggregated summary with per-agent and global statistics
        """
        try:
            log_dir = Path(log_dir)

            # Collect all tool metrics and round history from agents
            all_tool_events = []
            all_round_events = []
            agent_metrics = {}

            for agent_id, agent in self.agents.items():
                if hasattr(agent, "backend") and agent.backend:
                    backend = agent.backend

                    # Collect detailed tool execution events
                    if hasattr(backend, "get_tool_metrics"):
                        tool_events = backend.get_tool_metrics()
                        all_tool_events.extend(tool_events)

                    # Collect round token history
                    if hasattr(backend, "get_round_token_history"):
                        round_history = backend.get_round_token_history()
                        all_round_events.extend(round_history)

                    # Collect per-agent summaries
                    agent_metrics[agent_id] = {
                        "tool_metrics": backend.get_tool_metrics_summary() if hasattr(backend, "get_tool_metrics_summary") else None,
                        "round_history": backend.get_round_token_history() if hasattr(backend, "get_round_token_history") else None,
                        "token_usage": (
                            {
                                "input_tokens": backend.token_usage.input_tokens if backend.token_usage else 0,
                                "output_tokens": backend.token_usage.output_tokens if backend.token_usage else 0,
                                "reasoning_tokens": backend.token_usage.reasoning_tokens if backend.token_usage else 0,
                                "cached_input_tokens": backend.token_usage.cached_input_tokens if backend.token_usage else 0,
                                "estimated_cost": (
                                    round(
                                        backend.token_usage.estimated_cost,
                                        6,
                                    )
                                    if backend.token_usage
                                    else 0
                                ),
                            }
                            if hasattr(backend, "token_usage")
                            else None
                        ),
                    }

            # Save detailed events log
            events_file = log_dir / "metrics_events.json"
            events_data = {
                "meta": {
                    "generated_at": time.time(),
                    "session_id": log_dir.name,
                    "question": self.current_task,
                },
                "tool_executions": all_tool_events,
                "round_completions": all_round_events,
            }
            with open(events_file, "w", encoding="utf-8") as f:
                json.dump(events_data, f, indent=2, default=str)

            # Build aggregated summary
            # Aggregate tool stats
            tools_summary = {
                "total_calls": 0,
                "total_failures": 0,
                "total_execution_time_ms": 0.0,
                "by_tool": {},
            }
            for event in all_tool_events:
                tools_summary["total_calls"] += 1
                if not event.get("success", True):
                    tools_summary["total_failures"] += 1
                tools_summary["total_execution_time_ms"] += event.get(
                    "execution_time_ms",
                    0,
                )

                tool_name = event.get("tool_name", "unknown")
                if tool_name not in tools_summary["by_tool"]:
                    tools_summary["by_tool"][tool_name] = {
                        "call_count": 0,
                        "success_count": 0,
                        "failure_count": 0,
                        "total_execution_time_ms": 0.0,
                        "total_input_chars": 0,
                        "total_output_chars": 0,
                        "tool_type": event.get("tool_type", "unknown"),
                    }
                tools_summary["by_tool"][tool_name]["call_count"] += 1
                if event.get("success", True):
                    tools_summary["by_tool"][tool_name]["success_count"] += 1
                else:
                    tools_summary["by_tool"][tool_name]["failure_count"] += 1
                tools_summary["by_tool"][tool_name]["total_execution_time_ms"] += event.get("execution_time_ms", 0)
                tools_summary["by_tool"][tool_name]["total_input_chars"] += event.get(
                    "input_chars",
                    0,
                )
                tools_summary["by_tool"][tool_name]["total_output_chars"] += event.get(
                    "output_chars",
                    0,
                )

            # Calculate tool averages and token estimates
            for tool_stats in tools_summary["by_tool"].values():
                count = tool_stats["call_count"]
                if count > 0:
                    tool_stats["avg_execution_time_ms"] = round(
                        tool_stats["total_execution_time_ms"] / count,
                        2,
                    )
                    tool_stats["input_tokens_est"] = tool_stats["total_input_chars"] // 4
                    tool_stats["output_tokens_est"] = tool_stats["total_output_chars"] // 4

            # Aggregate round stats
            rounds_summary = {
                "total_rounds": len(all_round_events),
                "by_outcome": {
                    "answer": 0,
                    "vote": 0,
                    "presentation": 0,
                    "post_evaluation": 0,
                    "restarted": 0,
                    "error": 0,
                    "timeout": 0,
                },
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_reasoning_tokens": 0,
                "total_estimated_cost": 0.0,
                "avg_context_usage_pct": 0.0,
            }
            total_context_pct = 0.0
            for r in all_round_events:
                outcome = r.get("outcome", "unknown")
                if outcome in rounds_summary["by_outcome"]:
                    rounds_summary["by_outcome"][outcome] += 1
                rounds_summary["total_input_tokens"] += r.get("input_tokens", 0)
                rounds_summary["total_output_tokens"] += r.get("output_tokens", 0)
                rounds_summary["total_reasoning_tokens"] += r.get("reasoning_tokens", 0)
                rounds_summary["total_estimated_cost"] += r.get("estimated_cost", 0.0)
                total_context_pct += r.get("context_usage_pct", 0.0)

            rounds_summary["total_estimated_cost"] = round(
                rounds_summary["total_estimated_cost"],
                6,
            )
            if len(all_round_events) > 0:
                rounds_summary["avg_context_usage_pct"] = round(
                    total_context_pct / len(all_round_events),
                    2,
                )

            # Calculate total costs across all agents
            total_cost = 0.0
            total_input_tokens = 0
            total_output_tokens = 0
            total_reasoning_tokens = 0
            for am in agent_metrics.values():
                tu = am.get("token_usage")
                if tu:
                    total_cost += tu.get("estimated_cost", 0)
                    total_input_tokens += tu.get("input_tokens", 0)
                    total_output_tokens += tu.get("output_tokens", 0)
                    total_reasoning_tokens += tu.get("reasoning_tokens", 0)

            # Collect subagent costs from status files
            subagents_summary = self._collect_subagent_costs(log_dir)
            subagent_total_cost = subagents_summary.get("total_estimated_cost", 0.0)

            # Aggregate API call timing metrics
            api_timing = {
                "total_calls": 0,
                "total_time_ms": 0.0,
                "avg_time_ms": 0.0,
                "avg_ttft_ms": 0.0,
                "by_round": {},
                "by_backend": {},
            }
            total_ttft_ms = 0.0

            for agent_id, agent in self.agents.items():
                if hasattr(agent, "backend") and agent.backend:
                    backend = agent.backend
                    if hasattr(backend, "get_api_call_history"):
                        for metric in backend.get_api_call_history():
                            api_timing["total_calls"] += 1
                            api_timing["total_time_ms"] += metric.duration_ms
                            total_ttft_ms += metric.time_to_first_token_ms

                            # By round
                            round_key = f"round_{metric.round_number}"
                            if round_key not in api_timing["by_round"]:
                                api_timing["by_round"][round_key] = {
                                    "calls": 0,
                                    "time_ms": 0.0,
                                    "ttft_ms": 0.0,
                                }
                            api_timing["by_round"][round_key]["calls"] += 1
                            api_timing["by_round"][round_key]["time_ms"] += metric.duration_ms
                            api_timing["by_round"][round_key]["ttft_ms"] += metric.time_to_first_token_ms

                            # By backend
                            if metric.backend_name not in api_timing["by_backend"]:
                                api_timing["by_backend"][metric.backend_name] = {
                                    "calls": 0,
                                    "time_ms": 0.0,
                                    "ttft_ms": 0.0,
                                }
                            api_timing["by_backend"][metric.backend_name]["calls"] += 1
                            api_timing["by_backend"][metric.backend_name]["time_ms"] += metric.duration_ms
                            api_timing["by_backend"][metric.backend_name]["ttft_ms"] += metric.time_to_first_token_ms

            # Calculate averages
            if api_timing["total_calls"] > 0:
                api_timing["avg_time_ms"] = round(
                    api_timing["total_time_ms"] / api_timing["total_calls"],
                    2,
                )
                api_timing["avg_ttft_ms"] = round(
                    total_ttft_ms / api_timing["total_calls"],
                    2,
                )

            # Round timing values
            api_timing["total_time_ms"] = round(api_timing["total_time_ms"], 2)
            for round_data in api_timing["by_round"].values():
                round_data["time_ms"] = round(round_data["time_ms"], 2)
                round_data["ttft_ms"] = round(round_data["ttft_ms"], 2)
            for backend_data in api_timing["by_backend"].values():
                backend_data["time_ms"] = round(backend_data["time_ms"], 2)
                backend_data["ttft_ms"] = round(backend_data["ttft_ms"], 2)

            # Save summary file
            summary_file = log_dir / "metrics_summary.json"
            summary_data = {
                "meta": {
                    "generated_at": time.time(),
                    "session_id": log_dir.name,
                    "question": self.current_task,
                    "num_agents": len(self.agents),
                    "winner": self.coordination_tracker.final_winner,
                },
                "totals": {
                    "estimated_cost": round(total_cost + subagent_total_cost, 6),
                    "agent_cost": round(total_cost, 6),
                    "subagent_cost": round(subagent_total_cost, 6),
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "reasoning_tokens": total_reasoning_tokens,
                },
                "tools": tools_summary,
                "rounds": rounds_summary,
                "api_timing": api_timing,
                "agents": agent_metrics,
                "subagents": subagents_summary,
            }
            with open(summary_file, "w", encoding="utf-8") as f:
                json.dump(summary_data, f, indent=2, default=str)

            logger.info(f"[Orchestrator] Saved metrics files to {log_dir}")

        except Exception as e:
            logger.warning(f"Failed to save metrics files: {e}", exc_info=True)

    def _collect_subagent_costs(self, log_dir: Path) -> dict[str, Any]:
        """
        Collect subagent costs and metrics from status.json and subprocess metrics.

        Args:
            log_dir: Path to the log directory (e.g., turn_1/attempt_1)

        Returns:
            Dictionary with total costs, timing data, and per-subagent breakdown
        """
        subagents_dir = log_dir / "subagents"
        if not subagents_dir.exists():
            return {
                "total_subagents": 0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_estimated_cost": 0.0,
                "total_api_time_ms": 0.0,
                "total_api_calls": 0,
                "subagents": [],
            }

        total_input_tokens = 0
        total_output_tokens = 0
        total_estimated_cost = 0.0
        total_api_time_ms = 0.0
        total_api_calls = 0
        subagent_details = []

        # Find all status.json files in subagent directories
        # Status file is at full_logs/status.json (written by subagent's Orchestrator)
        for subagent_path in subagents_dir.iterdir():
            if not subagent_path.is_dir():
                continue

            # Read from full_logs/status.json (the single source of truth)
            status_file = subagent_path / "full_logs" / "status.json"
            if not status_file.exists():
                continue

            try:
                # Read status.json for basic info
                with open(status_file, encoding="utf-8") as f:
                    status_data = json.load(f)

                # Extract costs from the new structure
                costs = status_data.get("costs", {})
                input_tokens = costs.get("total_input_tokens", 0)
                output_tokens = costs.get("total_output_tokens", 0)
                cost = costs.get("total_estimated_cost", 0.0)

                # Extract timing from meta
                meta = status_data.get("meta", {})
                elapsed_seconds = meta.get("elapsed_seconds", 0.0)

                # Extract coordination info
                coordination = status_data.get("coordination", {})
                phase = coordination.get("phase", "unknown")

                total_input_tokens += input_tokens
                total_output_tokens += output_tokens
                total_estimated_cost += cost

                # Initialize subagent detail entry
                subagent_detail = {
                    "subagent_id": subagent_path.name,
                    "status": phase,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "estimated_cost": round(cost, 6),
                    "elapsed_seconds": elapsed_seconds,
                    "task": meta.get("question", "")[:100],
                }

                # Try to read subprocess metrics for API timing data
                subprocess_logs_file = subagent_path / "subprocess_logs.json"
                if subprocess_logs_file.exists():
                    try:
                        with open(subprocess_logs_file, encoding="utf-8") as f:
                            subprocess_logs = json.load(f)

                        subprocess_log_dir = subprocess_logs.get("subprocess_log_dir")
                        if subprocess_log_dir:
                            # Read the subprocess's metrics_summary.json
                            metrics_file = Path(subprocess_log_dir) / "metrics_summary.json"
                            if metrics_file.exists():
                                with open(metrics_file, encoding="utf-8") as f:
                                    metrics_data = json.load(f)

                                # Extract API timing data
                                api_timing = metrics_data.get("api_timing", {})
                                if api_timing:
                                    subagent_api_time = api_timing.get(
                                        "total_time_ms",
                                        0.0,
                                    )
                                    subagent_api_calls = api_timing.get(
                                        "total_calls",
                                        0,
                                    )

                                    total_api_time_ms += subagent_api_time
                                    total_api_calls += subagent_api_calls

                                    subagent_detail["api_timing"] = {
                                        "total_time_ms": round(subagent_api_time, 2),
                                        "total_calls": subagent_api_calls,
                                        "avg_time_ms": api_timing.get(
                                            "avg_time_ms",
                                            0.0,
                                        ),
                                        "avg_ttft_ms": api_timing.get(
                                            "avg_ttft_ms",
                                            0.0,
                                        ),
                                    }
                    except Exception as e:
                        logger.debug(
                            f"Failed to read subprocess metrics for {subagent_path.name}: {e}",
                        )

                subagent_details.append(subagent_detail)

            except Exception as e:
                logger.debug(f"Failed to read subagent status from {status_file}: {e}")

        return {
            "total_subagents": len(subagent_details),
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_estimated_cost": round(total_estimated_cost, 6),
            "total_api_time_ms": round(total_api_time_ms, 2),
            "total_api_calls": total_api_calls,
            "subagents": subagent_details,
        }

    def _format_planning_mode_ui(
        self,
        has_irreversible: bool,
        blocked_tools: set,
        has_isolated_workspaces: bool,
        user_question: str,
    ) -> str:
        """
        Format a nice UI box for planning mode status.

        Args:
            has_irreversible: Whether irreversible operations were detected
            blocked_tools: Set of specific blocked tool names
            has_isolated_workspaces: Whether agents have isolated workspaces
            user_question: The user's question for context

        Returns:
            Formatted string with nice box UI
        """
        if not has_irreversible:
            # Planning mode disabled - brief message
            box = "\n╭─ Coordination Mode ────────────────────────────────────────╮\n"
            box += "│ ✅ Planning Mode: DISABLED                                │\n"
            box += "│                                                            │\n"
            box += "│ All tools available during coordination.                  │\n"
            box += "│ No irreversible operations detected.                      │\n"
            box += "╰────────────────────────────────────────────────────────────╯\n"
            return box

        # Planning mode enabled
        box = "\n╭─ Coordination Mode ────────────────────────────────────────╮\n"
        box += "│ 🧠 Planning Mode: ENABLED                                  │\n"
        box += "│                                                            │\n"

        if has_isolated_workspaces:
            box += "│ 🔒 Workspace: Isolated (filesystem ops allowed)           │\n"
            box += "│                                                            │\n"

        # Description
        box += "│ Agents will plan and coordinate without executing         │\n"
        box += "│ irreversible actions. The winning agent will implement    │\n"
        box += "│ the plan during final presentation.                       │\n"
        box += "│                                                            │\n"

        # Blocked tools section
        if blocked_tools:
            box += "│ 🚫 Blocked Tools:                                          │\n"
            # Format tools into nice columns
            sorted_tools = sorted(blocked_tools)
            for i, tool in enumerate(sorted_tools[:5], 1):  # Show max 5 tools
                # Shorten tool name if too long
                display_tool = tool if len(tool) <= 50 else tool[:47] + "..."
                box += f"│   {i}. {display_tool:<54} │\n"

            if len(sorted_tools) > 5:
                remaining = len(sorted_tools) - 5
                box += f"│   ... and {remaining} more tool(s)                              │\n"
            box += "│                                                            │\n"
        else:
            box += "│ 🚫 Blocking: ALL MCP tools                                 │\n"
            box += "│                                                            │\n"

        # Add brief analysis summary
        box += "│ 📊 Analysis:                                               │\n"
        # Create a brief summary from the question
        summary = user_question[:50] + "..." if len(user_question) > 50 else user_question
        # Wrap text to fit in box
        words = summary.split()
        line = "│   "
        for word in words:
            if len(line) + len(word) + 1 > 60:
                box += line.ljust(61) + "│\n"
                line = "│   " + word + " "
            else:
                line += word + " "
        if len(line) > 4:  # If there's content
            box += line.ljust(61) + "│\n"

        box += "╰────────────────────────────────────────────────────────────╯\n"
        return box

    async def _analyze_question_irreversibility(
        self,
        user_question: str,
        conversation_context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Analyze if the user's question involves MCP tools with irreversible outcomes.

        This method randomly selects an available agent to analyze whether executing
        the user's question would involve MCP tool operations with irreversible outcomes
        (e.g., sending Discord messages, posting tweets, deleting files) vs reversible
        read operations (e.g., reading Discord messages, searching tweets, listing files).

        Args:
            user_question: The user's question/request
            conversation_context: Full conversation context including history

        Returns:
            Dict with:
                - has_irreversible (bool): True if irreversible operations detected
                - blocked_tools (set): Set of MCP tool names to block (e.g., {'mcp__discord__discord_send'})
                                      Empty set means block ALL MCP tools
        """
        import random

        print("=" * 80, flush=True)
        print(
            "🔍 [INTELLIGENT PLANNING MODE] Analyzing question for irreversibility...",
            flush=True,
        )
        print(
            f"📝 Question: {user_question[:100]}{'...' if len(user_question) > 100 else ''}",
            flush=True,
        )
        print("=" * 80, flush=True)

        # Select a random agent for analysis
        available_agents = [aid for aid, agent in self.agents.items() if agent.backend is not None]
        if not available_agents:
            # No agents available, default to safe mode (planning enabled, block ALL)
            log_orchestrator_activity(
                self.orchestrator_id,
                "No agents available for irreversibility analysis, defaulting to planning mode",
                {},
            )
            return {"has_irreversible": True, "blocked_tools": set()}

        analyzer_agent_id = random.choice(available_agents)
        analyzer_agent = self.agents[analyzer_agent_id]

        print(f"🤖 Selected analyzer agent: {analyzer_agent_id}", flush=True)

        # Check if agents have isolated workspaces
        has_isolated_workspaces = False
        workspace_info = []
        for agent_id, agent in self.agents.items():
            if agent.backend and agent.backend.filesystem_manager:
                cwd = agent.backend.filesystem_manager.cwd
                if cwd and "workspace" in os.path.basename(cwd).lower():
                    has_isolated_workspaces = True
                    workspace_info.append(f"{agent_id}: {cwd}")

        if has_isolated_workspaces:
            print(
                "🔒 Detected isolated agent workspaces - filesystem ops will be allowed",
                flush=True,
            )

        log_orchestrator_activity(
            self.orchestrator_id,
            "Analyzing question irreversibility",
            {
                "analyzer_agent": analyzer_agent_id,
                "question_preview": user_question[:100] + "..." if len(user_question) > 100 else user_question,
                "has_isolated_workspaces": has_isolated_workspaces,
            },
        )

        # Build analysis prompt - now asking for specific tool names
        workspace_context = ""
        if has_isolated_workspaces:
            workspace_context = """
IMPORTANT - ISOLATED WORKSPACES:
The agents are working in isolated temporary workspaces (directories containing "workspace" in their name).
Filesystem operations (read_file, write_file, delete_file, list_files, etc.) within these isolated workspaces are SAFE and REVERSIBLE.
They should NOT be blocked because:
- These are temporary directories specific to this coordination session
- Files created/modified are isolated from external systems
- Changes are contained within the agent's sandbox
- The workspace can be cleared after coordination

Only block filesystem operations if they explicitly target paths OUTSIDE the isolated workspace.
"""

        analysis_prompt = f"""You are analyzing whether a user's request involves operations with irreversible outcomes.

USER REQUEST:
{user_question}
{workspace_context}
CONTEXT:
Your task is to determine if executing this request would involve MCP (Model Context Protocol) tools that have irreversible outcomes, and if so, identify which specific tools should be blocked.

MCP tools follow the naming convention: mcp__<server>__<tool_name>
Examples:
- mcp__discord__discord_send (irreversible - sends messages)
- mcp__discord__discord_read_channel (reversible - reads messages)
- mcp__twitter__post_tweet (irreversible - posts publicly)
- mcp__twitter__search_tweets (reversible - searches)
- mcp__filesystem__write_file (SAFE in isolated workspace - writes to temporary files)
- mcp__filesystem__read_file (reversible - reads files)

IRREVERSIBLE OPERATIONS:
- Sending messages (discord_send, slack_send, etc.)
- Posting content publicly (post_tweet, create_post, etc.)
- Deleting files or data OUTSIDE isolated workspace (delete_file on external paths, remove_data, etc.)
- Modifying external systems (write_file to external paths, update_record, etc.)
- Creating permanent records (create_issue, add_comment, etc.)
- Executing commands that change state (run_command, execute_script, etc.)

REVERSIBLE OPERATIONS (DO NOT BLOCK):
- Reading messages or data (read_channel, get_messages, etc.)
- Searching or querying information (search_tweets, query_data, etc.)
- Listing files or resources (list_files, list_channels, etc.)
- Fetching data from APIs (get_user, fetch_data, etc.)
- Viewing information (view_channel, get_info, etc.)
- Filesystem operations IN ISOLATED WORKSPACE (write_file, read_file, delete_file, list_files when in workspace*)

Respond in this EXACT format:
IRREVERSIBLE: YES/NO
BLOCKED_TOOLS: tool1, tool2, tool3

If IRREVERSIBLE is NO, leave BLOCKED_TOOLS empty.
If IRREVERSIBLE is YES, list the specific MCP tool names that should be blocked (e.g., mcp__discord__discord_send).

Your answer:"""

        # Create messages for the analyzer
        analysis_messages = [
            {"role": "user", "content": analysis_prompt},
        ]

        try:
            # Stream response from analyzer agent (but don't show to user)
            response_text = ""
            async for chunk in analyzer_agent.backend.stream_with_tools(
                messages=analysis_messages,
                tools=[],  # No tools needed for simple analysis
                agent_id=analyzer_agent_id,
            ):
                if chunk.type == "content" and chunk.content:
                    response_text += chunk.content

            # Parse response
            response_clean = response_text.strip()
            has_irreversible = False
            blocked_tools = set()

            # Parse IRREVERSIBLE line
            found_irreversible_line = False
            for line in response_clean.split("\n"):
                line = line.strip()
                if line.startswith("IRREVERSIBLE:"):
                    found_irreversible_line = True
                    # Extract the value after the colon
                    value = line.split(":", 1)[1].strip().upper()
                    # Check if the first word is YES
                    has_irreversible = value.startswith("YES")
                elif line.startswith("BLOCKED_TOOLS:"):
                    # Extract tool names after the colon
                    tools_part = line.split(":", 1)[1].strip()
                    if tools_part:
                        # Split by comma and clean up whitespace
                        blocked_tools = {tool.strip() for tool in tools_part.split(",") if tool.strip()}

            # Fallback: If no structured format found, look for YES/NO in the response
            if not found_irreversible_line:
                print(
                    "⚠️  [WARNING] No 'IRREVERSIBLE:' line found, using fallback parsing",
                    flush=True,
                )
                response_upper = response_clean.upper()
                # Look for clear YES/NO indicators
                if "YES" in response_upper and "NO" not in response_upper:
                    has_irreversible = True
                elif "NO" in response_upper:
                    has_irreversible = False
                else:
                    # Default to safe mode if unclear
                    has_irreversible = True

            log_orchestrator_activity(
                self.orchestrator_id,
                "Irreversibility analysis complete",
                {
                    "analyzer_agent": analyzer_agent_id,
                    "response": response_clean[:100],
                    "has_irreversible": has_irreversible,
                    "blocked_tools_count": len(blocked_tools),
                },
            )

            # Display nice UI box for planning mode status
            ui_box = self._format_planning_mode_ui(
                has_irreversible=has_irreversible,
                blocked_tools=blocked_tools,
                has_isolated_workspaces=has_isolated_workspaces,
                user_question=user_question,
            )
            print(ui_box, flush=True)

            return {
                "has_irreversible": has_irreversible,
                "blocked_tools": blocked_tools,
            }

        except Exception as e:
            # On error, default to safe mode (planning enabled, block ALL)
            log_orchestrator_activity(
                self.orchestrator_id,
                "Irreversibility analysis failed, defaulting to planning mode",
                {"error": str(e)},
            )
            return {"has_irreversible": True, "blocked_tools": set()}

    async def _continuous_status_updates(self):
        """Background task to continuously update status.json during coordination.

        This task runs every 2 seconds to provide real-time status monitoring
        for automation tools and LLM agents.
        """
        try:
            while True:
                # Check for cancellation before sleeping
                if hasattr(self, "cancellation_manager") and self.cancellation_manager and self.cancellation_manager.is_cancelled:
                    logger.info(
                        "Cancellation detected in status update task - stopping",
                    )
                    break

                await asyncio.sleep(2)  # Update every 2 seconds

                # Check for cancellation after sleeping
                if hasattr(self, "cancellation_manager") and self.cancellation_manager and self.cancellation_manager.is_cancelled:
                    logger.info(
                        "Cancellation detected in status update task - stopping",
                    )
                    break

                log_session_dir = get_log_session_dir()
                if log_session_dir:
                    try:
                        # Run synchronous save_status_file in thread pool to avoid blocking event loop
                        # This prevents delays in WebSocket broadcasts and other async operations
                        loop = asyncio.get_running_loop()
                        await loop.run_in_executor(
                            None,  # Use default thread pool executor
                            self.coordination_tracker.save_status_file,
                            log_session_dir,
                            self,
                        )
                    except Exception as e:
                        logger.debug(f"Failed to update status file in background: {e}")

                # Update timeout status for each agent in the display
                try:
                    display = None
                    if hasattr(self, "coordination_ui") and self.coordination_ui:
                        display = getattr(self.coordination_ui, "display", None)

                    if display and hasattr(display, "update_timeout_status"):
                        for agent_id in self.agents.keys():
                            timeout_state = self.get_agent_timeout_state(agent_id)
                            if timeout_state and timeout_state.get("active_timeout"):
                                display.update_timeout_status(agent_id, timeout_state)
                except Exception as e:
                    logger.warning(f"Failed to update timeout status in display: {e}")
        except asyncio.CancelledError:
            # Task was cancelled, this is expected behavior
            pass
        except Exception as e:
            logger.warning(f"Background status update task encountered error: {e}")

    async def _coordinate_agents_with_timeout(
        self,
        conversation_context: dict[str, Any] | None = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Execute coordination with orchestrator-level timeout protection.

        When restart is needed, this method completes and returns control to CLI,
        which will call coordinate() again (similar to multiturn pattern).
        """
        # Reset timing and state for this attempt
        self.coordination_start_time = time.time()
        self.total_tokens = 0
        self.is_orchestrator_timeout = False
        self.timeout_reason = None
        self._presentation_started = False  # Reset presentation guard for new attempt

        log_orchestrator_activity(
            self.orchestrator_id,
            f"Starting coordination attempt {self.current_attempt + 1}/{self.max_attempts}",
            {
                "timeout_seconds": self.config.timeout_config.orchestrator_timeout_seconds,
                "agents": list(self.agents.keys()),
                "has_restart_context": bool(self.restart_reason),
            },
        )

        # Set log attempt for directory organization (only if restart feature is enabled)
        # For restarts (attempt 2+), CLI sets this before creating the UI
        # For first attempt, we still need to set it here
        if self.config.coordination_config.max_orchestration_restarts > 0:
            from massgen.logger_config import get_current_attempt

            expected_attempt = self.current_attempt + 1
            # Only set if not already set to the expected value (CLI may have set it for restarts)
            if get_current_attempt() != expected_attempt:
                set_log_attempt(expected_attempt)

        # Track active coordination state for cleanup
        self._active_streams = {}
        self._active_tasks = {}

        timeout_seconds = self.config.timeout_config.orchestrator_timeout_seconds

        try:
            # Use asyncio.timeout for timeout protection
            async with asyncio.timeout(timeout_seconds):
                async for chunk in self._coordinate_agents(conversation_context):
                    # Track tokens if this is a content chunk (only for string content)
                    if hasattr(chunk, "content") and chunk.content and isinstance(chunk.content, str):
                        self.total_tokens += len(
                            chunk.content.split(),
                        )  # Rough token estimation

                    yield chunk

        except TimeoutError:
            self.is_orchestrator_timeout = True
            elapsed = time.time() - self.coordination_start_time
            self.timeout_reason = f"Time limit exceeded ({elapsed:.1f}s/{timeout_seconds}s)"
            # Track timeout for all agents that were still working
            for agent_id in self.agent_states.keys():
                if not self.agent_states[agent_id].has_voted:
                    self.coordination_tracker.track_agent_action(
                        agent_id,
                        ActionType.TIMEOUT,
                        self.timeout_reason,
                    )

            # Force cleanup of any active agent streams and tasks
            await self._cleanup_active_coordination()

        # Handle timeout by jumping to final presentation
        if self.is_orchestrator_timeout:
            async for chunk in self._handle_orchestrator_timeout():
                yield chunk

        # Exit here - if restart is needed, CLI will call coordinate() again

    async def _coordinate_agents(
        self,
        conversation_context: dict[str, Any] | None = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Execute unified MassGen coordination workflow with real-time streaming."""
        # Log structured coordination event for observability
        log_coordination_event(
            "coordination_started",
            details={
                "num_agents": len(self.agents),
                "agent_ids": list(self.agents.keys()),
                "task": self.current_task[:200] if self.current_task else None,
            },
        )

        log_coordination_step(
            "Starting multi-agent coordination",
            {
                "agents": list(self.agents.keys()),
                "has_context": conversation_context is not None,
            },
        )

        # Clean up orphaned massgen/* branches from previous crashed sessions
        coordination_config = getattr(self.config, "coordination_config", None)
        _wm = getattr(coordination_config, "write_mode", None) if coordination_config else None
        if _wm and _wm != "legacy":
            from .filesystem_manager import IsolationContextManager

            for agent_id_cleanup, agent_cleanup in self.agents.items():
                if hasattr(agent_cleanup, "backend") and hasattr(agent_cleanup.backend, "filesystem_manager") and agent_cleanup.backend.filesystem_manager:
                    ppm = agent_cleanup.backend.filesystem_manager.path_permission_manager
                    ctx_paths = ppm.get_context_paths() if ppm else []
                    for ctx_config in ctx_paths:
                        ctx_path = ctx_config.get("path", "")
                        if ctx_path:
                            cleaned = IsolationContextManager.cleanup_orphaned_branches(ctx_path)
                            if cleaned:
                                logger.info(f"[Orchestrator] Cleaned {cleaned} orphaned branches in {ctx_path}")
                            break  # Only need to clean once per repo

        # Restore state from a previous log BEFORE generating personas/criteria
        # so the guard flags (_evaluation_criteria_generated, _personas_generated)
        # are set and generation is skipped.
        resume_cfg = getattr(
            getattr(self.config, "coordination_config", None),
            "resume_from_log",
            None,
        )
        if resume_cfg:
            await self._restore_from_previous_log(resume_cfg)

        # Generate pre-collab steps if enabled (happens once per session)
        _persona_enabled = (
            hasattr(self.config, "coordination_config")
            and hasattr(self.config.coordination_config, "persona_generator")
            and self.config.coordination_config.persona_generator.enabled
            and not self._personas_generated
        )
        _criteria_enabled = (
            hasattr(self.config, "coordination_config")
            and hasattr(self.config.coordination_config, "evaluation_criteria_generator")
            and self.config.coordination_config.evaluation_criteria_generator.enabled
            and not self._evaluation_criteria_generated
        )
        _prompt_improver_enabled = (
            hasattr(self.config, "coordination_config")
            and hasattr(self.config.coordination_config, "prompt_improver")
            and self.config.coordination_config.prompt_improver.enabled
            and not self._prompt_improved
        )

        pre_collab_tasks: list = []
        pre_collab_labels: list[str] = []
        if _persona_enabled:
            pre_collab_tasks.append(self._generate_and_inject_personas())
            pre_collab_labels.append("personas")
        if _criteria_enabled:
            pre_collab_tasks.append(self._generate_and_inject_evaluation_criteria())
            pre_collab_labels.append("evaluation criteria")
        if _prompt_improver_enabled:
            pre_collab_tasks.append(self._improve_and_inject_prompt())
            pre_collab_labels.append("prompt improvement")

        if pre_collab_tasks:
            # Announce parallel pre-collab batch so TUI can open a unified screen.
            _parallel_ids = []
            if _persona_enabled:
                _parallel_ids.append("persona_generation")
            if _criteria_enabled:
                _parallel_ids.append("criteria_generation")
            if _prompt_improver_enabled:
                _parallel_ids.append("prompt_improvement")

            _emitter = get_event_emitter()
            if _emitter:
                _emitter.emit_raw(
                    StructuredEventType.PRE_COLLAB_BATCH_ANNOUNCED,
                    pre_collab_ids=_parallel_ids,
                )

            yield StreamChunk(
                type="preparation_status",
                status=f"Generating {', '.join(pre_collab_labels)}...",
                detail="Pre-collaboration consensus steps",
            )
            await asyncio.gather(*pre_collab_tasks)
        else:
            # No pre-collab enabled, still call persona generation for its guard logic
            await self._generate_and_inject_personas()

        # Notify TUI of persona assignments for parallel mode.
        if (
            getattr(self.config, "coordination_mode", "voting") != "decomposition"
            and hasattr(self.config, "coordination_config")
            and hasattr(self.config.coordination_config, "persona_generator")
            and self.config.coordination_config.persona_generator.enabled
            and self._generated_personas
        ):
            try:
                display = getattr(self.coordination_ui, "display", None) if self.coordination_ui else None
                persona_map: dict[str, str] = {}
                for aid, persona in self._generated_personas.items():
                    summary = persona.attributes.get(
                        "approach_summary",
                        persona.attributes.get("thinking_style"),
                    )
                    persona_map[aid] = summary.strip() if isinstance(summary, str) and summary.strip() else persona.persona_text
                _emitter = get_event_emitter()
                if _emitter:
                    _emitter.emit_raw(
                        StructuredEventType.PERSONAS_SET,
                        personas=persona_map,
                    )
                if display and hasattr(display, "set_agent_personas"):
                    display.set_agent_personas(persona_map)
            except Exception:
                pass  # TUI notification is non-critical

        # Auto-decompose task if in decomposition mode with no explicit subtasks
        if (
            getattr(self.config, "coordination_mode", "voting") == "decomposition"
            and not any(self._agent_subtasks.values())
            and hasattr(self.config, "coordination_config")
            and hasattr(self.config.coordination_config, "task_decomposer")
            and self.config.coordination_config.task_decomposer.enabled
        ):
            yield StreamChunk(
                type="preparation_status",
                status="Decomposing task...",
                detail="Spawning decomposition subagent to assign per-agent subtasks",
            )
            from .task_decomposer import TaskDecomposer

            decomposer = TaskDecomposer(self.config.coordination_config.task_decomposer)
            existing_sys_msgs = {}
            parent_configs = []
            for aid, agent in self.agents.items():
                existing_sys_msgs[aid] = agent.get_configurable_system_message()
                backend_config = getattr(getattr(agent, "backend", None), "config", None)
                if isinstance(backend_config, dict):
                    parent_configs.append({"id": aid, "backend": backend_config})

            parent_workspace = ""
            if self.agents:
                first_agent = next(iter(self.agents.values()))
                fs_manager = getattr(getattr(first_agent, "backend", None), "filesystem_manager", None)
                if fs_manager:
                    parent_workspace = str(fs_manager.agent_temporary_workspace or fs_manager.cwd or "")

            log_directory = None
            try:
                log_directory = str(get_log_session_dir())
            except Exception:
                log_directory = None

            display = getattr(self.coordination_ui, "display", None) if self.coordination_ui else None
            decomposition_anchor_agent = next(iter(self.agents.keys()), None)
            decomposition_call_id = "decomposition_task_decomposition"

            def _on_decomposition_subagent_started(
                subagent_id: str,
                subagent_task: str,
                timeout_seconds: int,
                status_callback: Any,
                log_path: str | None,
            ) -> None:
                _emitter = get_event_emitter()
                if _emitter:
                    _emitter.emit_raw(
                        StructuredEventType.PRE_COLLAB_STARTED,
                        agent_id=decomposition_anchor_agent,
                        subagent_id=subagent_id,
                        task=subagent_task,
                        timeout_seconds=timeout_seconds,
                        call_id=decomposition_call_id,
                        log_path=log_path,
                    )
                if display and decomposition_anchor_agent and hasattr(display, "notify_runtime_subagent_started"):
                    try:
                        display.notify_runtime_subagent_started(
                            agent_id=decomposition_anchor_agent,
                            subagent_id=subagent_id,
                            task=subagent_task,
                            timeout_seconds=timeout_seconds,
                            call_id=decomposition_call_id,
                            status_callback=status_callback,
                            log_path=log_path,
                        )
                    except Exception:
                        pass

            try:
                pre_collab_voting_threshold = getattr(
                    self.config.coordination_config,
                    "pre_collab_voting_threshold",
                    None,
                )
                if pre_collab_voting_threshold is None:
                    pre_collab_voting_threshold = getattr(self.config, "voting_threshold", None)

                self._agent_subtasks = await decomposer.generate_decomposition_via_subagent(
                    task=self.current_task or "",
                    agent_ids=list(self.agents.keys()),
                    existing_system_messages=existing_sys_msgs,
                    parent_agent_configs=parent_configs,
                    parent_workspace=parent_workspace,
                    orchestrator_id=self.orchestrator_id,
                    log_directory=log_directory,
                    on_subagent_started=_on_decomposition_subagent_started,
                    voting_sensitivity=getattr(self.config, "voting_sensitivity", None),
                    voting_threshold=pre_collab_voting_threshold,
                    has_planning_spec_context=bool(self._plan_session_id),
                    fast_iteration_mode=self._get_fast_iteration_mode(),
                )
                self._agent_subtask_criteria = {}
                subtask_specs = getattr(decomposer, "last_subtask_specs", {}) or {}
                if subtask_specs:
                    from massgen.evaluation_criteria_generator import (
                        criteria_from_inline,
                    )

                    for aid, spec in subtask_specs.items():
                        criteria_inline = spec.get("criteria") or []
                        if criteria_inline:
                            self._agent_subtask_criteria[aid] = criteria_from_inline(criteria_inline)

                source = getattr(decomposer, "last_generation_source", "unknown")

                # Emit event for replay
                _emitter = get_event_emitter()
                if _emitter and decomposition_anchor_agent:
                    if source == "subagent":
                        _subtask_preview = " | ".join(f"{aid}: {subtask}" for aid, subtask in list(self._agent_subtasks.items())[:2])[:400]
                        _emitter.emit_raw(
                            StructuredEventType.PRE_COLLAB_COMPLETED,
                            agent_id=decomposition_anchor_agent,
                            subagent_id="task_decomposition",
                            call_id=decomposition_call_id,
                            status="completed",
                            answer_preview=_subtask_preview or "Subtasks generated successfully.",
                        )
                    else:
                        _emitter.emit_raw(
                            StructuredEventType.PRE_COLLAB_COMPLETED,
                            agent_id=decomposition_anchor_agent,
                            subagent_id="task_decomposition",
                            call_id=decomposition_call_id,
                            status="failed",
                            error="Used fallback decomposition subtasks.",
                        )

                if display and decomposition_anchor_agent and hasattr(display, "notify_runtime_subagent_completed"):
                    try:
                        if source == "subagent":
                            subtask_preview = " | ".join(f"{aid}: {subtask}" for aid, subtask in list(self._agent_subtasks.items())[:2])[:400]
                            display.notify_runtime_subagent_completed(
                                agent_id=decomposition_anchor_agent,
                                subagent_id="task_decomposition",
                                call_id=decomposition_call_id,
                                status="completed",
                                answer_preview=subtask_preview or "Subtasks generated successfully.",
                            )
                        else:
                            display.notify_runtime_subagent_completed(
                                agent_id=decomposition_anchor_agent,
                                subagent_id="task_decomposition",
                                call_id=decomposition_call_id,
                                status="failed",
                                error="Used fallback decomposition subtasks.",
                            )
                    except Exception:
                        pass

                if source == "subagent":
                    yield StreamChunk(
                        type="preparation_status",
                        status="Decomposition ready",
                        detail=("Subtasks generated by decomposition subagent for " f"{len(self._agent_subtasks)} agent(s)"),
                    )
                else:
                    yield StreamChunk(
                        type="preparation_status",
                        status="Decomposition fallback",
                        detail="Subagent decomposition unavailable; using fallback subtasks",
                    )

                logger.info(
                    f"[Orchestrator] Auto-decomposed task into {len(self._agent_subtasks)} subtasks " f"(source={source})",
                )
            except Exception as e:
                logger.warning(
                    f"[Orchestrator] Auto-decomposition failed: {e}, agents will work without explicit subtasks",
                )
                _emitter = get_event_emitter()
                if _emitter and decomposition_anchor_agent:
                    _emitter.emit_raw(
                        StructuredEventType.PRE_COLLAB_COMPLETED,
                        agent_id=decomposition_anchor_agent,
                        subagent_id="task_decomposition",
                        call_id=decomposition_call_id,
                        status="failed",
                        error=str(e),
                    )
                if display and decomposition_anchor_agent and hasattr(display, "notify_runtime_subagent_completed"):
                    try:
                        display.notify_runtime_subagent_completed(
                            agent_id=decomposition_anchor_agent,
                            subagent_id="task_decomposition",
                            call_id=decomposition_call_id,
                            status="failed",
                            error=str(e),
                        )
                    except Exception:
                        pass

        # Notify TUI of subtask assignments (from config or auto-decomposition)
        if self._agent_subtasks and any(self._agent_subtasks.values()):
            _subtask_map = {k: v for k, v in self._agent_subtasks.items() if v}
            try:
                _emitter = get_event_emitter()
                if _emitter:
                    _emitter.emit_raw(
                        StructuredEventType.SUBTASKS_SET,
                        subtasks=_subtask_map,
                    )
                display = getattr(self.coordination_ui, "display", None) if self.coordination_ui else None
                if display and hasattr(display, "set_agent_subtasks"):
                    display.set_agent_subtasks(_subtask_map)
            except Exception:
                pass  # TUI notification is non-critical

        # Check if we should skip coordination rounds (debug/test mode)
        if self.config.skip_coordination_rounds:
            log_stream_chunk(
                "orchestrator",
                "content",
                "⚡ [DEBUG MODE] Skipping coordination rounds, going straight to final presentation...\n\n",
                self.orchestrator_id,
            )
            yield StreamChunk(
                type="content",
                content="⚡ [DEBUG MODE] Skipping coordination rounds, going straight to final presentation...\n\n",
                source=self.orchestrator_id,
            )

            # Select first agent as winner (or random if needed)
            self._selected_agent = list(self.agents.keys())[0]
            log_coordination_step(
                "Skipped coordination, selected first agent",
                {"selected_agent": self._selected_agent},
            )

            # Present final answer immediately
            async for chunk in self._present_final_answer():
                yield chunk
            return

        # Emit startup status update for UI
        yield StreamChunk(
            type="system_status",
            content="Initializing coordination...",
            source=self.orchestrator_id,
        )

        log_stream_chunk(
            "orchestrator",
            "content",
            "🚀 Starting multi-agent coordination...\n\n",
            self.orchestrator_id,
        )
        yield StreamChunk(
            type="content",
            content="🚀 Starting multi-agent coordination...\n\n",
            source=self.orchestrator_id,
        )

        # Emit status update: preparing agent environments
        yield StreamChunk(
            type="system_status",
            content=f"Preparing {len(self.agents)} agent environments...",
            source=self.orchestrator_id,
        )

        # Start background status update task for real-time monitoring
        status_update_task = asyncio.create_task(self._continuous_status_updates())
        # Store reference so it can be cancelled from outside if needed
        self._status_update_task = status_update_task

        votes = {}  # Track votes: voter_id -> {"agent_id": voted_for, "reason": reason}

        # Initialize all agents with has_voted = False and set restart flags
        for agent_id in self.agents.keys():
            self.agent_states[agent_id].has_voted = False
            self.agent_states[agent_id].restart_pending = True

        # Checkpoint solo mode: deactivate non-main agents at start
        if self.is_checkpoint_mode and not self._checkpoint_active:
            for agent_id in self.agents.keys():
                if agent_id != self._main_agent_id:
                    self.agent_states[agent_id].has_voted = True
            logger.info(
                f"[Checkpoint] Solo mode: only '{self._main_agent_id}' active",
            )

        # Emit status update: checking MCP/tool availability
        has_mcp_agents = any(hasattr(agent, "backend") and hasattr(agent.backend, "config") and agent.backend.config.get("mcp_servers") for agent in self.agents.values())
        if has_mcp_agents:
            yield StreamChunk(
                type="system_status",
                content="Connecting to MCP servers...",
                source=self.orchestrator_id,
            )

        log_stream_chunk(
            "orchestrator",
            "content",
            "## 📋 Agents Coordinating\n",
            self.orchestrator_id,
        )
        yield StreamChunk(
            type="content",
            content="## 📋 Agents Coordinating\n",
            source=self.orchestrator_id,
        )

        # Emit status update: coordination started
        yield StreamChunk(
            type="system_status",
            content="Agents working on task...",
            source=self.orchestrator_id,
        )

        # Emit status that agents are now starting to work
        yield StreamChunk(
            type="preparation_status",
            status="Agents working...",
            detail="Waiting for first response",
        )

        # Start streaming coordination with real-time agent output
        async for chunk in self._stream_coordination_with_agents(
            votes,
            conversation_context,
        ):
            yield chunk

        # Step mode: skip winner selection and final presentation
        if self._step_complete:
            logger.info("[StepMode] Skipping winner selection and final presentation")
            return

        # Determine final agent
        current_answers = {aid: state.answer for aid, state in self.agent_states.items() if state.answer}
        if getattr(self.config, "coordination_mode", "voting") == "decomposition":
            # Decomposition mode: use config-designated presenter or last agent
            presenter = getattr(self.config, "presenter_agent", None)
            if presenter and presenter not in self.agents:
                logger.warning(f"[Orchestrator] presenter_agent '{presenter}' not found in agents, falling back to last agent")
                presenter = None
            self._selected_agent = presenter or list(self.agents.keys())[-1]
        else:
            self._selected_agent = self._determine_final_agent_from_votes(
                votes,
                current_answers,
            )

        # Emit selection status for TUI event pipeline
        used_vote_selection = bool(votes)
        _vote_emitter = get_event_emitter()
        if _vote_emitter and self._selected_agent:
            status_message = f"Voting complete - selected agent: {self._selected_agent}" if used_vote_selection else f"Presenter selected for synthesis: {self._selected_agent}"
            _vote_emitter.emit_status(
                status_message,
                level="info",
                agent_id=self._selected_agent,
            )

        # Track winning agent for memory sharing in future turns
        self._current_turn += 1
        if self._selected_agent:
            winner_entry = {
                "agent_id": self._selected_agent,
                "turn": self._current_turn,
            }
            self._winning_agents_history.append(winner_entry)
            logger.info(
                f"🏆 Turn {self._current_turn} winner: {self._selected_agent} " f"(tracked for memory sharing)",
            )

        log_coordination_step(
            "Final agent selected" if used_vote_selection else "Final presenter selected",
            {"selected_agent": self._selected_agent, "votes": votes},
        )

        # Log structured event for observability
        log_coordination_event(
            "winner_selected",
            agent_id=self._selected_agent,
            details={
                "turn": self._current_turn,
                "vote_count": len(votes),
                "num_answers": len(current_answers),
            },
        )

        # Merge all agents' memories into winner's workspace before final presentation
        if self._selected_agent:
            self._merge_agent_memories_to_winner(self._selected_agent)

        # Cancel background status update task
        status_update_task.cancel()
        try:
            await status_update_task
        except asyncio.CancelledError:
            pass  # Expected

        # Present final answer
        async for chunk in self._present_final_answer():
            yield chunk

    async def _stream_coordination_with_agents(
        self,
        votes: dict[str, dict],
        conversation_context: dict[str, Any] | None = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Coordinate agents with real-time streaming of their outputs.

        Processes agent stream signals:
        - "content": Streams real-time agent output to user
        - "result": Records votes/answers, triggers restart_pending for other agents
        - "error": Displays error and closes agent stream (self-terminating)
        - "done": Closes agent stream gracefully

        Restart Mechanism:
        When any agent provides new_answer, all other agents get restart_pending=True
        and gracefully terminate their current work before restarting.
        """
        active_streams = {}
        active_tasks = {}  # Track active tasks to prevent duplicate task creation

        # Store references for timeout cleanup
        self._active_streams = active_streams
        self._active_tasks = active_tasks

        # Helper to check if coordination should end
        def _coordination_complete() -> bool:
            """Check if coordination is complete.

            Returns True when:
            - All agents have voted (normal case), OR
            - skip_voting=True and all agents have submitted at least one answer
            - All live agents have voted/answered and remaining agents are killed

            During an active checkpoint round, returns False even if all checkpoint
            agents voted — the checkpoint must be deactivated first and the main
            agent needs to resume solo.
            """
            # During active checkpoint, never signal completion — the checkpoint
            # deactivation handler inside the loop will handle the transition.
            if self._checkpoint_active:
                return False

            # Treat killed agents as effectively done — they will never vote or answer.
            live_states = [s for s in self.agent_states.values() if not s.is_killed]
            if not live_states:
                return True  # All agents killed — nothing left to coordinate

            all_voted = all(state.has_voted or state.is_killed for state in self.agent_states.values())
            if all_voted:
                return True

            # Check skip_voting mode: complete when all live agents have answered
            if self.config.skip_voting:
                all_answered = all(state.answer is not None or state.is_killed for state in self.agent_states.values())
                if all_answered:
                    logger.info("[skip_voting] All agents have answered - skipping voting, proceeding to presentation")
                    return True

            if self._should_skip_vote_rounds_for_synthesize():
                all_answered = all(state.answer is not None or state.is_killed for state in self.agent_states.values())
                if all_answered:
                    logger.info(
                        "[synthesize] All agents have answered - skipping vote rounds and proceeding to final presentation",
                    )
                    return True

            return False

        # Stream agent outputs in real-time until coordination is complete
        while not _coordination_complete():
            # Step mode: exit after one action (answer or vote)
            if self._step_complete:
                logger.info("[StepMode] Step complete — exiting coordination loop")
                break

            # Check for cancellation - stop coordination immediately
            if hasattr(self, "cancellation_manager") and self.cancellation_manager and self.cancellation_manager.is_cancelled:
                logger.info(
                    "Cancellation detected in main coordination loop - stopping",
                )
                break

            # Check for orchestrator timeout - stop spawning new agents
            if self.is_orchestrator_timeout:
                break
            # Start any agents that aren't running and haven't voted yet
            current_answers = self._get_current_answers_snapshot()
            gate_ready = await self._run_round_evaluator_pre_round_if_needed(
                current_answers,
                conversation_context,
            )
            if gate_ready is False:
                await asyncio.sleep(0.25)
                continue
            if gate_ready == "terminal_error":
                break

            # Criteria evolution gate: runs synchronously after round_evaluator,
            # before agents restart. Evolves criteria when agents are acing them.
            criteria_ready = await self._run_criteria_evolution_if_needed(
                current_answers,
            )
            if not criteria_ready:
                await asyncio.sleep(0.25)
                continue

            # Start new coordination iteration only after blocking pre-round gates complete.
            self.coordination_tracker.start_new_iteration()
            for agent_id in self.agents.keys():
                # Checkpoint mode: skip agents not active in current mode
                if not self._is_agent_active_in_current_mode(agent_id):
                    continue

                # Skip agents that are waiting for all answers before voting
                if self._is_waiting_for_all_answers(agent_id):
                    continue

                # In decomposition mode, hitting max_new_answers_per_agent should auto-stop
                # without spawning a fresh model round.
                if self._apply_decomposition_auto_stop_if_needed(agent_id):
                    continue

                pause_for_fairness, pause_reason = self._should_pause_agent_for_fairness(agent_id)
                self._update_fairness_pause_log_state(
                    agent_id,
                    pause_for_fairness,
                    pause_reason,
                )
                if pause_for_fairness:
                    continue

                if agent_id not in active_streams and not self.agent_states[agent_id].has_voted and not self.agent_states[agent_id].is_killed:
                    # Apply rate limiting before starting agent
                    await self._apply_agent_startup_rate_limit(agent_id)

                    # Create a copy for this agent to avoid cross-agent coupling
                    # Each agent needs its own baseline to detect new answers independently
                    per_agent_answers = dict(current_answers)

                    # Track which answers this agent knows about (for vote validation)
                    self.agent_states[agent_id].known_answer_ids = set(current_answers.keys())
                    # Mark that this agent has received the current answer revision set.
                    self._sync_decomposition_answer_visibility(agent_id)

                    # Use checkpoint task when checkpoint is active, original task otherwise
                    agent_task = self._checkpoint_task if self._checkpoint_active else self.current_task

                    active_streams[agent_id] = self._stream_agent_execution(
                        agent_id,
                        agent_task,
                        per_agent_answers,
                        conversation_context,
                        self._agent_paraphrases.get(agent_id),
                    )

            if not active_streams:
                # Before breaking, check if any agents are still eligible to run.
                # Agents between rounds (restart_pending, stream just closed) are
                # momentarily absent from active_streams but should be re-spawned.
                has_eligible = any(not state.has_voted and not state.is_killed for state in self.agent_states.values())
                if has_eligible:
                    logger.info(
                        "[Orchestrator] No active streams but eligible agents exist — waiting for re-spawn",
                    )
                    await asyncio.sleep(0.5)
                    continue
                break

            # Create tasks only for streams that don't already have active tasks
            for agent_id, stream in active_streams.items():
                if agent_id not in active_tasks:
                    active_tasks[agent_id] = asyncio.create_task(
                        self._get_next_chunk(stream),
                    )

            if not active_tasks:
                break

            done, _ = await asyncio.wait(
                active_tasks.values(),
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Check for cancellation after wait
            if hasattr(self, "cancellation_manager") and self.cancellation_manager and self.cancellation_manager.is_cancelled:
                logger.info("Cancellation detected after asyncio.wait - cleaning up")
                # Gracefully interrupt Claude Code backends before cancelling tasks
                for agent_id, agent in self.agents.items():
                    if hasattr(agent, "backend") and hasattr(agent.backend, "interrupt"):
                        try:
                            await agent.backend.interrupt()
                        except Exception:
                            pass
                # Cancel remaining tasks
                for task in active_tasks.values():
                    task.cancel()
                break

            # Collect results from completed agents
            reset_signal = False
            voted_agents = {}
            answered_agents = {}
            completed_agent_ids = set()  # Track all agents whose tasks completed, i.e., done, error, result.

            # Process completed stream chunks
            for task in done:
                agent_id = next(aid for aid, t in active_tasks.items() if t is task)
                # Remove completed task from active_tasks
                del active_tasks[agent_id]
                display_agent_id = agent_id

                try:
                    # Unpack chunk tuple - may be 2-tuple (type, data) or 3-tuple (type, data, tool_call_id)
                    chunk_tuple = await task
                    chunk_type = chunk_tuple[0]
                    chunk_data = chunk_tuple[1]
                    chunk_tool_call_id = chunk_tuple[2] if len(chunk_tuple) > 2 else None

                    if chunk_type == "content":
                        # Stream agent content in real-time with source info
                        log_stream_chunk(
                            "orchestrator",
                            "content",
                            chunk_data,
                            agent_id,
                        )
                        yield StreamChunk(
                            type="content",
                            content=chunk_data,
                            source=display_agent_id,
                        )

                    elif chunk_type == "coordination":
                        # Coordination traces (strict mode) - pass through as coordination type
                        log_stream_chunk(
                            "orchestrator",
                            "coordination",
                            chunk_data,
                            agent_id,
                        )
                        yield StreamChunk(
                            type="coordination",
                            content=chunk_data,
                            source=display_agent_id,
                        )

                    elif chunk_type == "external_tool_calls":
                        # Client-provided (non-workflow) tool calls must be surfaced to the caller
                        # and are never executed by MassGen.
                        yield StreamChunk(
                            type="tool_calls",
                            tool_calls=chunk_data,
                            source=display_agent_id,
                        )
                        # Close all active streams and stop coordination.
                        for aid in list(active_streams.keys()):
                            await self._close_agent_stream(aid, active_streams)
                        for t in list(active_tasks.values()):
                            t.cancel()
                        yield StreamChunk(type="done")
                        return

                    elif chunk_type == "reasoning":
                        # Stream reasoning content with proper attribution
                        log_stream_chunk(
                            "orchestrator",
                            "reasoning",
                            chunk_data,
                            agent_id,
                        )
                        yield chunk_data  # chunk_data is already a StreamChunk with source

                    elif chunk_type == "result":
                        # Agent completed with result
                        result_type, result_data = chunk_data
                        # Result ends the agent's current stream
                        completed_agent_ids.add(agent_id)
                        log_stream_chunk(
                            "orchestrator",
                            f"result.{result_type}",
                            result_data,
                            agent_id,
                        )

                        # Only emit "completed" status for votes - agents are truly done
                        # after voting. For answers, they still need to vote.
                        if result_type == "vote":
                            yield StreamChunk(
                                type="agent_status",
                                source=display_agent_id,
                                status="completed",
                                content="",
                            )
                        if result_type == "answer":
                            result_data = self._coerce_answer_content_to_text(result_data)
                            # Agent provided an answer (initial or improved)
                            agent = self.agents.get(agent_id)
                            # Get the context that was sent to this agent
                            agent_context = self.get_last_context(agent_id)
                            # Save snapshot (of workspace and answer) when agent provides new answer
                            answer_timestamp = await self._save_agent_snapshot(
                                agent_id,
                                answer_content=result_data,
                                context_data=agent_context,
                            )
                            if agent and agent.backend.filesystem_manager:
                                agent.backend.filesystem_manager.log_current_state(
                                    "after providing answer",
                                )
                            # Always record answers, even from restarting agents (orchestrator accepts them)

                            answered_agents[agent_id] = result_data
                            # Pass timestamp to coordination_tracker for mapping
                            self.coordination_tracker.add_agent_answer(
                                agent_id,
                                result_data,
                                snapshot_timestamp=answer_timestamp,
                            )
                            # Update the agent's own context label so submit_checklist
                            # accepts the new version (e.g. agent2.2 replaces agent2.1).
                            self.coordination_tracker.update_agent_context_with_new_answers(
                                agent_id,
                                [agent_id],
                            )
                            self._refresh_checklist_state_for_agent(
                                agent_id,
                                prefer_local_runtime_state=True,
                            )
                            # Attach changedoc from workspace if enabled
                            if self._is_changedoc_enabled() and agent and agent.backend.filesystem_manager:
                                from massgen.changedoc import (
                                    read_changedoc_from_workspace,
                                )

                                ws_path = agent.backend.filesystem_manager.cwd
                                if ws_path:
                                    changedoc_content = read_changedoc_from_workspace(Path(ws_path))
                                    if changedoc_content:
                                        answers_list = self.coordination_tracker.answers_by_agent.get(agent_id, [])
                                        if answers_list:
                                            label = answers_list[-1].label
                                            # Replace [SELF] placeholder with real answer label
                                            changedoc_content = changedoc_content.replace("[SELF]", label)
                                            answers_list[-1].changedoc = changedoc_content
                                            logger.info(
                                                "[Orchestrator] Attached changedoc (%d chars) to %s",
                                                len(changedoc_content),
                                                answers_list[-1].label,
                                            )
                            if self._is_decomposition_mode():
                                self.agent_states[agent_id].decomposition_answer_streak += 1
                                # Agent has produced a new self revision; keep its own seen
                                # revision count in sync without marking external updates as seen.
                                self.agent_states[agent_id].seen_answer_counts[agent_id] = len(
                                    self.coordination_tracker.answers_by_agent.get(agent_id, []),
                                )
                            # End round token tracking with "answer" outcome
                            if agent and hasattr(agent.backend, "end_round_tracking"):
                                agent.backend.end_round_tracking("answer")
                            # Emit answer_submitted event (unified pipeline for main + subagent TUI)
                            _ans_list = self.coordination_tracker.answers_by_agent.get(agent_id, [])
                            _answer_number = len(_ans_list)
                            _agent_num = self.coordination_tracker._get_agent_number(agent_id)
                            _answer_label = f"agent{_agent_num}.{_answer_number}"

                            _emitter = get_event_emitter()
                            if _emitter:
                                _emitter.emit_answer_submitted(
                                    agent_id=agent_id,
                                    content=result_data,
                                    answer_number=_answer_number,
                                    answer_label=_answer_label,
                                )

                            # Notify web display for browser tracking (non-TUI displays)
                            if hasattr(self, "coordination_ui") and self.coordination_ui:
                                display = getattr(self.coordination_ui, "display", None)
                                if display and hasattr(display, "send_new_answer") and not hasattr(display, "_app"):
                                    # Get the current round for this agent (0-indexed) and convert to 1-indexed
                                    _agent_round = self.coordination_tracker.get_agent_round(agent_id) + 1
                                    _workspace_path = None
                                    _log_session_dir = get_log_session_dir()
                                    if _log_session_dir and answer_timestamp:
                                        _workspace_path = str(
                                            Path(_log_session_dir) / agent_id / answer_timestamp / "workspace",
                                        )
                                    try:
                                        display.send_new_answer(
                                            agent_id=agent_id,
                                            content=result_data,
                                            answer_number=_answer_number,
                                            answer_label=_answer_label,
                                            workspace_path=_workspace_path,
                                            submission_round=_agent_round,
                                        )
                                    except TypeError:
                                        # Older display implementations may not accept submission_round
                                        display.send_new_answer(
                                            agent_id=agent_id,
                                            content=result_data,
                                            answer_number=_answer_number,
                                            answer_label=_answer_label,
                                            workspace_path=_workspace_path,
                                        )
                                    # Record for timeline visualization
                                    if hasattr(display, "record_answer_with_context"):
                                        _context = self.coordination_tracker.get_agent_context_labels(agent_id)
                                        display.record_answer_with_context(
                                            agent_id=agent_id,
                                            answer_label=_answer_label,
                                            context_sources=_context,
                                            round_num=_agent_round,
                                        )
                            # Update status file for real-time monitoring
                            # Run in executor to avoid blocking event loop
                            log_session_dir = get_log_session_dir()
                            if log_session_dir:
                                loop = asyncio.get_running_loop()
                                await loop.run_in_executor(
                                    None,
                                    self.coordination_tracker.save_status_file,
                                    log_session_dir,
                                    self,
                                )
                            await self._cancel_running_background_work_for_agent(agent_id)

                            # Trigger B: auto trace analysis per agent on new_answer.
                            # Trigger A (inside _run_round_evaluator_pre_round_if_needed)
                            # only fires for single-agent configs.  For multi-agent,
                            # this is the only trigger.  _should_spawn_trace_analyzer
                            # prevents double-spawning if Trigger A already fired.
                            if self._should_spawn_trace_analyzer(agent_id):
                                await self._spawn_trace_analyzer_background(agent_id)

                            restart_triggered_id = agent_id  # Last agent to provide new answer
                            reset_signal = True

                            # Step mode: record answer and signal completion
                            if self._step_mode and self._step_mode.enabled:
                                self._step_complete = True
                                workspace_path = self._resolve_step_mode_workspace(agent_id)
                                stale_paths = self._resolve_step_mode_stale_paths(agent_id)
                                self._step_action_data = {
                                    "action": "new_answer",
                                    "agent_id": agent_id,
                                    "answer_text": result_data,
                                    "workspace_path": workspace_path,
                                    "stale_workspace_paths": stale_paths,
                                }
                                logger.info("[StepMode] Agent %s submitted answer — step complete", agent_id)

                        elif result_type == "vote":
                            # Agent voted for existing answer
                            logger.debug(
                                f"VOTE BLOCK ENTERED for {agent_id}, result_data={result_data}",
                            )
                            # Ignore votes from agents with restart pending (votes are about current state).
                            # EXCEPTION 1: Single-agent run can clear stale restart_pending once it has an answer.
                            # EXCEPTION 2: Revision-aware stale detection clears restart_pending when no unseen
                            # latest peer updates remain.
                            # EXCEPTION 3: Hard timeout acts as fairness cutoff and clears restart_pending.
                            restart_pending = self._check_restart_pending(agent_id)
                            is_single_agent = len(self.agents) == 1
                            agent_has_answer = self.agent_states[agent_id].answer is not None
                            if restart_pending and is_single_agent and agent_has_answer:
                                # Single agent voting for itself - clear restart_pending and accept vote
                                self.agent_states[agent_id].restart_pending = False
                                restart_pending = False
                                logger.info(f"[Orchestrator] Single agent {agent_id} vote accepted (has own answer)")
                            if restart_pending:
                                unseen_sources = self._get_unseen_source_agent_ids(agent_id)
                                if self._is_hard_timeout_active(agent_id):
                                    self.agent_states[agent_id].restart_pending = False
                                    restart_pending = False
                                    logger.info(
                                        "[Orchestrator] Agent %s vote accepted at hard-timeout cutoff despite unseen updates",
                                        agent_id,
                                    )
                                elif not unseen_sources:
                                    # No unseen latest revisions remain - stale restart_pending.
                                    self.agent_states[agent_id].restart_pending = False
                                    restart_pending = False
                                    logger.info(
                                        f"[Orchestrator] Agent {agent_id} vote accepted (no unseen revisions, clearing stale restart_pending)",
                                    )
                            if restart_pending:
                                voted_for = result_data.get("agent_id", "<unknown>")
                                reason = result_data.get("reason", "No reason provided")
                                # Track the ignored vote action
                                self.coordination_tracker.track_agent_action(
                                    agent_id,
                                    ActionType.VOTE_IGNORED,
                                    f"Voted for {voted_for} but ignored due to restart",
                                )
                                # Save in coordination tracker that we waste a vote due to restart
                                log_stream_chunk(
                                    "orchestrator",
                                    "content",
                                    f"🔄 Vote for [{voted_for}] ignored (reason: {reason}) - restarting due to new answers",
                                    agent_id,
                                )
                                yield StreamChunk(
                                    type="agent_status" if self.trace_classification == "strict" else "content",
                                    content=f"🔄 Vote for [{voted_for}] ignored (reason: {reason}) - restarting due to new answers",
                                    source=display_agent_id,
                                )
                                # Clear the stale vote data to prevent it leaking into final results
                                self.agent_states[agent_id].votes = {}
                            else:
                                # Save vote snapshot (includes workspace)
                                vote_timestamp = await self._save_agent_snapshot(
                                    agent_id=agent_id,
                                    vote_data=result_data,
                                    context_data=self.get_last_context(agent_id),
                                )
                                # Log workspaces for current agent
                                agent = self.agents.get(agent_id)
                                if agent and agent.backend.filesystem_manager:
                                    self.agents.get(
                                        agent_id,
                                    ).backend.filesystem_manager.log_current_state(
                                        "after voting",
                                    )
                                voted_agents[agent_id] = result_data

                                # Check if this is a stop (decomposition mode) vs a vote
                                is_stop = result_data.get("_is_stop", False)
                                if is_stop:
                                    # Store stop metadata on AgentState
                                    self.agent_states[agent_id].stop_summary = result_data.get("stop_summary")
                                    self.agent_states[agent_id].stop_status = result_data.get("stop_status", "complete")
                                    # Record stop event in coordination tracker
                                    self.coordination_tracker.add_agent_stop(
                                        agent_id,
                                        result_data,
                                    )
                                else:
                                    # Pass timestamp to coordination_tracker for mapping
                                    self.coordination_tracker.add_agent_vote(
                                        agent_id,
                                        result_data,
                                        snapshot_timestamp=vote_timestamp,
                                    )
                                    # Step mode: record vote and signal completion
                                    if self._step_mode and self._step_mode.enabled:
                                        self._step_complete = True
                                        self._step_action_data = {
                                            "action": "vote",
                                            "agent_id": agent_id,
                                            "vote_target": result_data.get("agent_id", ""),
                                            "vote_reason": result_data.get("reason", ""),
                                            "workspace_path": None,
                                        }
                                        logger.info("[StepMode] Agent %s voted — step complete", agent_id)
                                # End round token tracking with "vote" outcome
                                if agent and hasattr(
                                    agent.backend,
                                    "end_round_tracking",
                                ):
                                    agent.backend.end_round_tracking("vote")
                                # Notify web display about the vote (not applicable for stop)
                                if not is_stop:
                                    logger.debug(
                                        f"Vote recorded - checking for coordination_ui: hasattr={hasattr(self, 'coordination_ui')}, coordination_ui={self.coordination_ui}",
                                    )
                                    if hasattr(self, "coordination_ui") and self.coordination_ui:
                                        display = getattr(
                                            self.coordination_ui,
                                            "display",
                                            None,
                                        )
                                        logger.debug(
                                            f"Got display: {display}, has update_vote_target: {hasattr(display, 'update_vote_target') if display else 'N/A'}",
                                        )
                                        if display and hasattr(
                                            display,
                                            "update_vote_target",
                                        ):
                                            logger.debug(
                                                f"Calling update_vote_target({agent_id}, {result_data.get('agent_id', '')}, ...)",
                                            )
                                            display.update_vote_target(
                                                voter_id=agent_id,
                                                target_id=result_data.get("agent_id", ""),
                                                reason=result_data.get("reason", ""),
                                            )
                                            # Record for timeline visualization
                                            if hasattr(display, "record_vote_with_context"):
                                                _vote_round = self.coordination_tracker.get_agent_round(agent_id) + 1
                                                _context = self.coordination_tracker.get_agent_context_labels(agent_id)
                                                _agent_idx = self.coordination_tracker.agent_ids.index(agent_id) + 1 if agent_id in self.coordination_tracker.agent_ids else 0
                                                _vote_count = len([m for m in (self.coordination_tracker.votes or []) if getattr(m, "voter_id", None) == agent_id])
                                                _vote_label = f"vote{_agent_idx}.{_vote_count}"
                                                display.record_vote_with_context(
                                                    voter_id=agent_id,
                                                    vote_label=_vote_label,
                                                    voted_for=result_data.get("agent_id", ""),
                                                    available_answers=_context,
                                                    voting_round=_vote_round,
                                                )
                                # Emit event (unified pipeline for main + subagent TUI)
                                _emitter = get_event_emitter()
                                if _emitter:
                                    if is_stop:
                                        _emitter.emit_stop(
                                            agent_id=agent_id,
                                            summary=result_data.get("stop_summary", ""),
                                            status=result_data.get("stop_status", "complete"),
                                        )
                                    else:
                                        _emitter.emit_vote(
                                            voter_id=agent_id,
                                            target_id=result_data.get("agent_id", ""),
                                            reason=result_data.get("reason", ""),
                                        )
                                # Update status file for real-time monitoring
                                # Run in executor to avoid blocking event loop
                                log_session_dir = get_log_session_dir()
                                logger.debug(f"Log session dir: {log_session_dir}")
                                if log_session_dir:
                                    loop = asyncio.get_running_loop()
                                    await loop.run_in_executor(
                                        None,
                                        self.coordination_tracker.save_status_file,
                                        log_session_dir,
                                        self,
                                    )

                                # Track event for logging only
                                # Note: The TUI displays votes/stops via tool cards,
                                # so we use agent_status type to avoid duplicate display
                                if is_stop:
                                    stop_status_str = result_data.get("stop_status", "complete")
                                    log_stream_chunk(
                                        "orchestrator",
                                        "agent_status",
                                        f"✅ Agent stopped ({stop_status_str})",
                                        agent_id,
                                    )
                                    yield StreamChunk(
                                        type="agent_status",
                                        content=f"✅ Agent stopped ({stop_status_str})",
                                        source=display_agent_id,
                                    )
                                else:
                                    log_stream_chunk(
                                        "orchestrator",
                                        "agent_status",
                                        f"✅ Vote recorded for [{result_data['agent_id']}]",
                                        agent_id,
                                    )
                                    yield StreamChunk(
                                        type="agent_status",
                                        content=f"✅ Vote recorded for [{result_data['agent_id']}]",
                                        source=display_agent_id,
                                    )

                        # IMPORTANT: close stream after snapshotting answer/vote.
                        # Closing the stream triggers _stream_agent_execution.finally, which may run
                        # round cleanup (including branch switch in write_mode workspace isolation).
                        # If we close first, snapshots can capture the post-cleanup workspace instead
                        # of the agent's round output.
                        await self._close_agent_stream(agent_id, active_streams)

                    elif chunk_type == "error":
                        # Agent error
                        self.agent_states[agent_id].error_reason = chunk_data
                        self.coordination_tracker.track_agent_action(
                            agent_id,
                            ActionType.ERROR,
                            chunk_data,
                        )
                        # End round token tracking with "error" outcome
                        agent = self.agents.get(agent_id)
                        if agent and hasattr(agent.backend, "end_round_tracking"):
                            agent.backend.end_round_tracking("error")
                        # Error ends the agent's current stream
                        completed_agent_ids.add(agent_id)
                        # Mark agent as killed to prevent respawning in the while loop
                        self.agent_states[agent_id].is_killed = True
                        log_stream_chunk("orchestrator", "error", chunk_data, agent_id)
                        yield StreamChunk(
                            type="agent_status" if self.trace_classification == "strict" else "content",
                            content=f"❌ {chunk_data}",
                            source=display_agent_id,
                        )
                        log_stream_chunk(
                            "orchestrator",
                            "agent_status",
                            "completed",
                            agent_id,
                        )
                        yield StreamChunk(
                            type="agent_status",
                            source=display_agent_id,
                            status="completed",
                            content="",
                        )
                        await self._close_agent_stream(agent_id, active_streams)

                    elif chunk_type == "debug":
                        # Debug information - forward as StreamChunk for logging
                        log_stream_chunk("orchestrator", "debug", chunk_data, agent_id)
                        yield StreamChunk(
                            type="debug",
                            content=chunk_data,
                            source=display_agent_id,
                        )

                    elif chunk_type == "mcp_status":
                        # MCP status messages - keep mcp_status type to preserve tool tracking
                        mcp_message = f"🔧 MCP: {chunk_data}"
                        log_stream_chunk("orchestrator", "mcp_status", chunk_data, agent_id)
                        yield StreamChunk(
                            type="mcp_status",
                            content=mcp_message,
                            source=display_agent_id,
                            tool_call_id=chunk_tool_call_id,
                        )

                    elif chunk_type == "custom_tool_status":
                        # Custom tool status messages - keep custom_tool_status type for tool tracking
                        custom_message = f"🔧 Custom Tool: {chunk_data}"
                        log_stream_chunk("orchestrator", "custom_tool_status", chunk_data, agent_id)
                        yield StreamChunk(
                            type="custom_tool_status",
                            content=custom_message,
                            source=display_agent_id,
                            tool_call_id=chunk_tool_call_id,
                        )

                    elif chunk_type == "hook_execution":
                        # Hook execution chunks - pass through for TUI display
                        # chunk_data is already a StreamChunk with hook_info and tool_call_id
                        log_stream_chunk("orchestrator", "hook_execution", str(chunk_data.hook_info), agent_id)
                        yield chunk_data

                    elif chunk_type == "agent_restart":
                        # Agent is starting a new round - notify UI to show fresh timeline
                        # chunk_data is a dict with agent_id and round
                        log_stream_chunk("orchestrator", "agent_restart", str(chunk_data), agent_id)
                        yield StreamChunk(
                            type="agent_restart",
                            content=chunk_data,
                            source=display_agent_id,
                        )

                    elif chunk_type == "done":
                        # Stream completed - this is just an end-of-stream marker
                        # DON'T emit "completed" status here - that's handled by the "result" handler
                        # when the agent actually provides an answer/vote.
                        # The "done" chunk just means the backend stream ended, which happens
                        # after every turn (including the first turn before any answer).
                        agent = self.agents.get(agent_id)
                        if agent and hasattr(agent.backend, "end_round_tracking"):
                            agent.backend.end_round_tracking("restarted")
                        completed_agent_ids.add(agent_id)
                        log_stream_chunk("orchestrator", "done", None, agent_id)

                        # Phase 13.1: Emit token usage update for TUI status ribbon
                        if agent and hasattr(agent.backend, "token_usage") and agent.backend.token_usage:
                            token_usage = agent.backend.token_usage
                            yield StreamChunk(
                                type="token_usage_update",
                                source=display_agent_id,
                                usage={
                                    "input_tokens": token_usage.input_tokens or 0,
                                    "output_tokens": token_usage.output_tokens or 0,
                                    "estimated_cost": token_usage.estimated_cost or 0,
                                },
                            )

                        # Note: Removed agent_status: completed emission here - it was causing
                        # agents to show "Done" immediately before they've done any work.
                        # Status updates are properly handled by the "result" handler.
                        await self._close_agent_stream(agent_id, active_streams)

                except Exception as e:
                    self.agent_states[agent_id].error_reason = f"Stream error - {e}"
                    self.coordination_tracker.track_agent_action(
                        agent_id,
                        ActionType.ERROR,
                        f"Stream error - {e}",
                    )
                    # End round token tracking with "error" outcome
                    agent = self.agents.get(agent_id)
                    if agent and hasattr(agent.backend, "end_round_tracking"):
                        agent.backend.end_round_tracking("error")
                    completed_agent_ids.add(agent_id)
                    # Mark agent as killed to prevent respawning in the while loop
                    self.agent_states[agent_id].is_killed = True
                    log_stream_chunk(
                        "orchestrator",
                        "error",
                        f"❌ Stream error - {e}",
                        agent_id,
                    )
                    error_type = "coordination" if self.trace_classification == "strict" else "content"
                    yield StreamChunk(
                        type=error_type,
                        content=f"❌ Stream error - {e}",
                        source=display_agent_id,
                    )
                    await self._close_agent_stream(agent_id, active_streams)

            # Apply all state changes atomically after processing all results
            if reset_signal:
                # In checkpoint solo mode, don't reset state — the main agent
                # runs continuously. Its new_answer is handled differently
                # (either ends the session in task mode, or is just recorded).
                if self.is_checkpoint_mode and not self._checkpoint_active:
                    logger.info(
                        "[Checkpoint] Solo mode — skipping vote/restart reset " "(main agent runs continuously)",
                    )
                    # Re-mark non-main agents as voted to keep them inactive
                    for aid in self.agents:
                        if aid != self._main_agent_id:
                            self.agent_states[aid].has_voted = True
                else:
                    # Normal mode: Reset all agents' has_voted to False
                    # (any new answer invalidates all votes/stops)
                    for state in self.agent_states.values():
                        state.has_voted = False
                        state.votes = {}  # Clear stale vote data
                        state.stop_summary = None  # Clear stop metadata (wakes up stopped agents)
                        state.stop_status = None
                    votes.clear()

                # Skip restart signaling when injection is disabled (multi-agent refinement OFF)
                # Agents work independently and don't need to see each other's answers
                # Also skip in checkpoint solo mode — the main agent runs continuously
                # and delegates via checkpoint(), not through restart cycles.
                if self.is_checkpoint_mode and not self._checkpoint_active:
                    logger.info(
                        "[Checkpoint] Solo mode — skipping restart signaling " "(main agent runs continuously)",
                    )
                elif not self.config.disable_injection:
                    for agent_id in self.agent_states.keys():
                        self.agent_states[agent_id].restart_pending = True

                    # Track restart signals
                    self.coordination_tracker.track_restart_signal(
                        restart_triggered_id,
                        list(self.agent_states.keys()),
                    )
                    # Note that the agent that sent the restart signal had its stream end so we should mark as completed. NOTE the below breaks it.
                    self.coordination_tracker.complete_agent_restart(restart_triggered_id)
                else:
                    logger.info(
                        "[disable_injection] Skipping restart signaling - agents work independently",
                    )
            # Set has_voted = True for agents that voted (only if no reset signal)
            else:
                for agent_id, vote_data in voted_agents.items():
                    self.agent_states[agent_id].has_voted = True
                    votes[agent_id] = vote_data

            # Update answers for agents that provided them
            for agent_id, answer in answered_agents.items():
                self.agent_states[agent_id].answer = self._coerce_answer_content_to_text(
                    answer,
                )

            # Update status based on what actions agents took
            for agent_id in completed_agent_ids:
                if agent_id in answered_agents:
                    self.coordination_tracker.change_status(
                        agent_id,
                        AgentStatus.ANSWERED,
                    )
                elif agent_id in voted_agents:
                    # Check if this was a stop (decomposition mode) vs a vote
                    is_stop = voted_agents[agent_id].get("_is_stop", False)
                    if is_stop:
                        self.coordination_tracker.change_status(agent_id, AgentStatus.STOPPED)
                    else:
                        self.coordination_tracker.change_status(agent_id, AgentStatus.VOTED)
                # Errors and timeouts are already tracked via track_agent_action

        # Cancel any remaining tasks and close streams, as all agents have voted (no more new answers)
        for agent_id, task in active_tasks.items():
            if not task.done():
                self.coordination_tracker.track_agent_action(
                    agent_id,
                    ActionType.CANCELLED,
                    "All agents voted - coordination complete",
                )
            task.cancel()
        for agent_id in list(active_streams.keys()):
            await self._close_agent_stream(agent_id, active_streams)

        # Finalize token tracking for all agents
        # This estimates tokens for any streams that were interrupted (e.g., due to restart_pending)
        for agent_id, agent in self.agents.items():
            if hasattr(agent.backend, "finalize_token_tracking"):
                agent.backend.finalize_token_tracking()

        # Note: checkpoint deactivation is handled inside the while loop above.
        # After deactivation, the main agent resumes solo and the loop continues
        # until the main agent votes (normal completion).

    async def _copy_all_snapshots_to_temp_workspace(
        self,
        agent_id: str,
    ) -> str | None:
        """Copy all agents' latest workspace snapshots to a temporary workspace for context sharing.

        TODO (v0.0.14 Context Sharing Enhancement - See docs/dev_notes/v0.0.14-context.md):
        - Validate agent permissions before restoring snapshots
        - Check if agent has read access to other agents' workspaces
        - Implement fine-grained control over which snapshots can be accessed
        - Add audit logging for snapshot access attempts

        Args:
            agent_id: ID of the Claude Code agent receiving the context

        Returns:
            Path to the agent's workspace directory if successful, None otherwise
        """
        agent = self.agents.get(agent_id)
        if not agent:
            return None

        # Check if agent has filesystem support
        if not agent.backend.filesystem_manager:
            return None

        # Create anonymous mapping for agent IDs
        # This ensures consistency with the anonymous IDs shown to agents
        agent_mapping = self.coordination_tracker.get_reverse_agent_mapping()

        # Collect snapshots from snapshot_storage directory
        all_snapshots = {}
        if self._snapshot_storage:
            snapshot_base = Path(self._snapshot_storage)
            for source_agent_id in self.agents.keys():
                source_snapshot = snapshot_base / source_agent_id
                if source_snapshot.exists() and source_snapshot.is_dir():
                    all_snapshots[source_agent_id] = source_snapshot

        # In step mode, also include virtual agent workspaces from the session dir
        if self._step_mode and self._step_mode.enabled and self._step_inputs:
            for va_id, va_state in self._step_inputs.virtual_agents.items():
                if va_id not in all_snapshots and va_state.latest_workspace:
                    va_ws = Path(va_state.latest_workspace)
                    if va_ws.exists() and va_ws.is_dir():
                        all_snapshots[va_id] = va_ws

        # Use the filesystem manager to copy snapshots to temp workspace
        workspace_path = await agent.backend.filesystem_manager.copy_snapshots_to_temp_workspace(
            all_snapshots,
            agent_mapping,
        )

        # Replace stale paths in copied workspace files
        if workspace_path:
            from massgen.filesystem_manager import replace_stale_paths_in_workspace

            for source_agent_id, snapshot_path in all_snapshots.items():
                anon_id = agent_mapping.get(source_agent_id, source_agent_id)
                dest_dir = workspace_path / anon_id
                if not dest_dir.exists():
                    continue
                replacements: dict[str, str] = {str(snapshot_path): str(dest_dir)}
                source_agent = self.agents.get(source_agent_id)
                if source_agent and source_agent.backend.filesystem_manager:
                    fm = source_agent.backend.filesystem_manager
                    if fm.cwd:
                        replacements[str(fm.cwd)] = str(dest_dir)
                replace_stale_paths_in_workspace(dest_dir, replacements)

        return str(workspace_path) if workspace_path else None

    async def _restore_from_previous_log(self, resume_config: dict[str, Any]) -> None:
        """Restore answers, workspaces, and changedocs from a previous log.

        Loads state from a previous run so the orchestrator can resume at a
        later round without re-running earlier rounds.

        Args:
            resume_config: Dict with 'log_path' (str) and 'round' (int).
                          Restores all answer snapshots up to and including
                          the specified round.
        """
        import shutil

        import yaml as _yaml

        log_path = Path(resume_config["log_path"])
        target_round = resume_config["round"]

        logger.info(
            f"[Orchestrator] Restoring from previous log: {log_path}, " f"resuming after round {target_round}",
        )

        # Load snapshot mappings
        mappings_file = log_path / "snapshot_mappings.json"
        if not mappings_file.exists():
            logger.error(f"[Orchestrator] snapshot_mappings.json not found in {log_path}")
            return

        import json as _json

        mappings = _json.loads(mappings_file.read_text())

        # Filter to answer snapshots up to target round
        answer_snapshots = {label: mapping for label, mapping in mappings.items() if mapping.get("type") == "answer" and mapping.get("round", 0) <= target_round}

        if not answer_snapshots:
            logger.warning(
                f"[Orchestrator] No answer snapshots found for round <= {target_round}",
            )
            return

        # Restore each answer in label order (agent1.1, agent1.2, agent2.1, etc.)
        for label in sorted(answer_snapshots.keys()):
            mapping = answer_snapshots[label]
            agent_id = mapping["agent_id"]
            timestamp = mapping["timestamp"]
            snap_dir = log_path / agent_id / timestamp

            # Read answer
            answer_file = snap_dir / "answer.txt"
            if not answer_file.exists():
                logger.warning(f"[Orchestrator] answer.txt not found: {answer_file}")
                continue
            answer_text = answer_file.read_text()

            # Read changedoc if present
            changedoc_file = snap_dir / "changedoc.md"
            changedoc_text = changedoc_file.read_text() if changedoc_file.exists() else None

            # Add answer to coordination tracker
            self.coordination_tracker.add_agent_answer(
                agent_id,
                answer_text,
                snapshot_timestamp=timestamp,
            )

            # Attach changedoc to the answer
            if changedoc_text:
                answers = self.coordination_tracker.answers_by_agent.get(agent_id, [])
                if answers:
                    answers[-1].changedoc = changedoc_text

            # Restore workspace if present and agent has filesystem_manager
            workspace_dir = snap_dir / "workspace"
            if workspace_dir.is_dir() and agent_id in self.agents:
                agent = self.agents[agent_id]
                fm = getattr(agent.backend, "filesystem_manager", None)
                if fm and hasattr(fm, "cwd") and fm.cwd:
                    dest = Path(fm.cwd)
                    dest.mkdir(parents=True, exist_ok=True)
                    for src_file in workspace_dir.rglob("*"):
                        if src_file.is_file():
                            rel = src_file.relative_to(workspace_dir)
                            dst = dest / rel
                            dst.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(str(src_file), str(dst))
                    # Clear stale task plan so agent starts with a fresh plan
                    stale_plan = dest / "tasks" / "plan.json"
                    try:
                        stale_plan.unlink()
                        logger.info(f"[Orchestrator] Cleared stale task plan from restored workspace for {agent_id}")
                    except FileNotFoundError:
                        pass

            logger.info(
                f"[Orchestrator] Restored {label}: agent={agent_id}, "
                f"round={mapping['round']}, answer_len={len(answer_text)}" + (f", changedoc_len={len(changedoc_text)}" if changedoc_text else ""),
            )

        # Set agent rounds to target_round + 1 (they've completed target_round)
        for agent_id in self.agents:
            self.coordination_tracker.set_agent_round(agent_id, target_round + 1)

        # Update agent states so the loop knows these agents have answered
        for agent_id in self.agents:
            answers = self.coordination_tracker.answers_by_agent.get(agent_id, [])
            if answers and agent_id in self.agent_states:
                self.agent_states[agent_id].answer = answers[-1].content
                self.agent_states[agent_id].answer_count = len(answers)

        # Load generated evaluation criteria from the log if no inline criteria override
        inline = getattr(
            getattr(self.config, "coordination_config", None),
            "checklist_criteria_inline",
            None,
        )
        if not inline and self._generated_evaluation_criteria is None:
            criteria_file = log_path / "generated_evaluation_criteria.yaml"
            if criteria_file.exists():
                try:
                    from massgen.evaluation_criteria_generator import GeneratedCriterion

                    criteria_data = _yaml.safe_load(criteria_file.read_text())
                    _legacy_cat_map = {"must": "standard", "core": "standard", "should": "standard", "could": "stretch"}
                    if isinstance(criteria_data, list):
                        self._generated_evaluation_criteria = [
                            GeneratedCriterion(
                                id=c.get("id", f"E{i + 1}"),
                                text=c.get("text") or c.get("description") or c.get("name", ""),
                                category=_legacy_cat_map.get(c.get("category", "standard"), c.get("category", "standard")),
                                verify_by=c.get("verify_by") or None,
                                anti_patterns=c.get("anti_patterns") if isinstance(c.get("anti_patterns"), list) else None,
                            )
                            for i, c in enumerate(criteria_data)
                            if c.get("text") or c.get("description") or c.get("name")
                        ]
                        self._evaluation_criteria_generated = True
                        logger.info(
                            f"[Orchestrator] Loaded {len(self._generated_evaluation_criteria)} " "evaluation criteria from previous log",
                        )
                except Exception as e:
                    logger.warning(
                        f"[Orchestrator] Failed to load evaluation criteria from log: {e}",
                    )

        # Load generated personas from the log if not already set
        if not self._generated_personas:
            personas_file = log_path / "generated_personas.yaml"
            if personas_file.exists():
                try:
                    from .persona_generator import GeneratedPersona

                    personas_data = _yaml.safe_load(personas_file.read_text())
                    if isinstance(personas_data, dict):
                        for agent_id, pdata in personas_data.items():
                            self._generated_personas[agent_id] = GeneratedPersona(
                                agent_id=agent_id,
                                persona_text=pdata.get("persona_text", ""),
                                attributes=pdata.get("attributes", {}),
                            )
                        self._personas_generated = True
                        logger.info(
                            f"[Orchestrator] Loaded {len(self._generated_personas)} " "personas from previous log",
                        )
                except Exception as e:
                    logger.warning(
                        f"[Orchestrator] Failed to load personas from log: {e}",
                    )

        logger.info(
            f"[Orchestrator] Resume complete: restored {len(answer_snapshots)} snapshots, " f"agents will start at round {target_round + 1}",
        )

    def _restore_workspace_from_latest_answer_dir(self, agent_id: str) -> bool:
        """Restore an agent's workspace from its most recent per-round answer directory.

        Used before final snapshot save in timeout/fallback paths where the live
        workspace has been cleared between rounds and only has scaffolding.

        Returns True if restoration happened, False otherwise.
        """
        agent = self.agents.get(agent_id)
        if not agent or not agent.backend.filesystem_manager:
            return False

        log_session_dir = get_log_session_dir()
        if not log_session_dir:
            return False

        agent_log_dir = log_session_dir / agent_id
        if not agent_log_dir.exists():
            return False

        # Find all timestamped answer directories (format: YYYYMMDD_HHMMSS_ffffff)
        # Sort descending to get most recent first
        answer_dirs = sorted(
            [d for d in agent_log_dir.iterdir() if d.is_dir() and d.name != "final" and (d / "workspace").is_dir()],
            key=lambda d: d.name,
            reverse=True,
        )

        if not answer_dirs:
            return False

        latest_workspace = answer_dirs[0] / "workspace"
        workspace_path = Path(agent.backend.filesystem_manager.cwd)

        # Copy items from the latest answer dir into the live workspace
        # (non-overwriting — preserve anything already there)
        items_restored = 0
        for item in latest_workspace.iterdir():
            if item.is_symlink():
                continue
            dest = workspace_path / item.name
            if dest.exists():
                continue
            if item.is_file():
                shutil.copy2(item, dest)
                items_restored += 1
            elif item.is_dir():
                shutil.copytree(
                    item,
                    dest,
                    symlinks=True,
                    ignore_dangling_symlinks=True,
                )
                items_restored += 1

        logger.info(
            f"[Orchestrator] Restored {items_restored} items from latest answer dir " f"{latest_workspace} to workspace for {agent_id}",
        )
        return items_restored > 0

    def _sync_applied_context_files_into_final_artifacts(
        self,
        agent_id: str,
        target_path: str,
        relative_paths: list[str],
    ) -> None:
        """Mirror approved context-path changes into saved final artifacts.

        Final presentation snapshots the agent workspace before isolated
        context-path changes are reviewed and copied back to the real target.
        After apply, overlay the delivered files into the persisted final
        artifacts so logs and snapshot_storage reflect what actually landed.
        """
        if not relative_paths:
            return

        agent = self.agents.get(agent_id)
        if not agent or not hasattr(agent, "backend"):
            return

        filesystem_manager = getattr(agent.backend, "filesystem_manager", None)
        if filesystem_manager is None:
            return

        source_root = Path(target_path)
        normalized_rel_paths: list[str] = []
        seen_rel_paths: set[str] = set()
        for rel_path in relative_paths:
            if not isinstance(rel_path, str):
                continue
            normalized = rel_path.replace("\\", "/").strip()
            if not normalized:
                normalized = source_root.name
            rel_obj = Path(normalized)
            if rel_obj.is_absolute() or ".." in rel_obj.parts:
                logger.warning(
                    "[Orchestrator] Skipping unsafe applied context path %r for %s",
                    rel_path,
                    agent_id,
                )
                continue
            rel_key = rel_obj.as_posix()
            if rel_key in seen_rel_paths:
                continue
            seen_rel_paths.add(rel_key)
            normalized_rel_paths.append(rel_key)

        if not normalized_rel_paths:
            return

        destination_roots: list[Path] = []
        log_session_dir = get_log_session_dir()
        if log_session_dir:
            destination_roots.append(Path(log_session_dir) / "final" / agent_id / "workspace")

        snapshot_storage = getattr(filesystem_manager, "snapshot_storage", None)
        if snapshot_storage:
            destination_roots.append(Path(snapshot_storage))

        if not destination_roots:
            return

        copied_count = 0
        removed_count = 0
        for destination_root in destination_roots:
            destination_root.mkdir(parents=True, exist_ok=True)

            for normalized in normalized_rel_paths:
                rel_obj = Path(normalized)
                source_path = source_root if source_root.is_file() else source_root / rel_obj
                destination_path = destination_root / rel_obj

                try:
                    if source_path.exists():
                        destination_path.parent.mkdir(parents=True, exist_ok=True)
                        if source_path.is_file():
                            shutil.copy2(source_path, destination_path)
                        elif source_path.is_dir():
                            shutil.copytree(
                                source_path,
                                destination_path,
                                dirs_exist_ok=True,
                                symlinks=True,
                                ignore_dangling_symlinks=True,
                            )
                        copied_count += 1
                    else:
                        if destination_path.is_file() or destination_path.is_symlink():
                            destination_path.unlink()
                            removed_count += 1
                        elif destination_path.is_dir():
                            shutil.rmtree(destination_path)
                            removed_count += 1
                except Exception as exc:
                    logger.warning(
                        "[Orchestrator] Failed to sync applied context file %s into %s for %s: %s",
                        normalized,
                        destination_root,
                        agent_id,
                        exc,
                    )

        logger.info(
            "[Orchestrator] Synced applied context files into final artifacts for %s: copied=%d removed=%d paths=%s",
            agent_id,
            copied_count,
            removed_count,
            normalized_rel_paths,
        )

    async def _save_agent_snapshot(
        self,
        agent_id: str,
        answer_content: str = None,
        vote_data: dict[str, Any] = None,
        is_final: bool = False,
        context_data: Any = None,
    ) -> str:
        """
        Save a snapshot of an agent's working directory and answer/vote with the same timestamp.

        Creates a timestamped directory structure:
        - agent_id/timestamp/workspace/ - Contains the workspace files
        - agent_id/timestamp/answer.txt - Contains the answer text (if provided)
        - agent_id/timestamp/vote.json - Contains the vote data (if provided)
        - agent_id/timestamp/context.txt - Contains the context used (if provided)

        Note on vote-only snapshots:
            When saving a vote without an answer (vote_data only), workspace snapshots are
            intentionally skipped. During voting, agents may create temporary verification
            files (e.g., check.py, test scripts) to help evaluate answers. Saving these would
            overwrite the actual deliverable files from the previous answer snapshot. The
            vote.json and context.txt are still saved for tracking purposes.

        Args:
            agent_id: ID of the agent
            answer_content: The answer content to save (if provided)
            vote_data: The vote data to save (if provided)
            is_final: If True, save as final snapshot for presentation
            context_data: The context data to save (conversation, answers, etc.)

        Returns:
            The timestamp used for this snapshot
        """
        logger.info(
            f"[Orchestrator._save_agent_snapshot] Called for agent_id={agent_id}, has_answer={bool(answer_content)}, has_vote={bool(vote_data)}, is_final={is_final}",
        )

        agent = self.agents.get(agent_id)
        if not agent:
            logger.warning(
                f"[Orchestrator._save_agent_snapshot] Agent {agent_id} not found in agents dict",
            )
            return None

        # Generate single timestamp for answer/vote and workspace
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

        # Save answer if provided (or create final directory structure even if empty)
        if answer_content is not None or is_final:
            try:
                log_session_dir = get_log_session_dir()
                if log_session_dir:
                    if is_final:
                        # For final, save to final directory
                        timestamped_dir = log_session_dir / "final" / agent_id
                    else:
                        # For regular snapshots, create timestamped directory
                        timestamped_dir = log_session_dir / agent_id / timestamp
                    timestamped_dir.mkdir(parents=True, exist_ok=True)
                    answer_file = timestamped_dir / "answer.txt"

                    # Write the answer content (even if empty for final snapshots)
                    content_to_write = answer_content if answer_content is not None else ""

                    # Normalize workspace paths in final answer so they reference
                    # the adjacent workspace/ directory in the log structure
                    if is_final and content_to_write and agent.backend.filesystem_manager:
                        original_cwd = getattr(agent.backend.filesystem_manager, "cwd", None)
                        if original_cwd:
                            dest_workspace = str(timestamped_dir / "workspace")
                            content_to_write = content_to_write.replace(
                                str(original_cwd),
                                dest_workspace,
                            )
                            # Also try resolved path in case they differ
                            resolved_cwd = str(Path(original_cwd).resolve())
                            if resolved_cwd != str(original_cwd):
                                content_to_write = content_to_write.replace(
                                    resolved_cwd,
                                    dest_workspace,
                                )

                    answer_file.write_text(content_to_write)
                    logger.info(
                        f"[Orchestrator._save_agent_snapshot] Saved answer to {answer_file}",
                    )

                    # Save changedoc alongside answer if enabled
                    if self._is_changedoc_enabled() and agent.backend.filesystem_manager:
                        from massgen.changedoc import read_changedoc_from_workspace

                        ws_path = agent.backend.filesystem_manager.cwd
                        if ws_path:
                            changedoc_content = read_changedoc_from_workspace(Path(ws_path))
                            if changedoc_content:
                                # Replace [SELF] with the label this answer will get
                                agent_num = self.coordination_tracker._get_agent_number(agent_id)
                                answer_num = len(self.coordination_tracker.answers_by_agent.get(agent_id, [])) + 1
                                label = f"agent{agent_num}.{answer_num}"
                                changedoc_content = changedoc_content.replace("[SELF]", label)
                                changedoc_file = timestamped_dir / "changedoc.md"
                                changedoc_file.write_text(changedoc_content)
                                logger.info(
                                    "[Orchestrator._save_agent_snapshot] Saved changedoc to %s",
                                    changedoc_file,
                                )

            except Exception as e:
                logger.warning(
                    f"[Orchestrator._save_agent_snapshot] Failed to save answer for {agent_id}: {e}",
                )

        # Save vote if provided
        if vote_data:
            try:
                log_session_dir = get_log_session_dir()
                if log_session_dir:
                    # Create timestamped directory for vote
                    timestamped_dir = log_session_dir / agent_id / timestamp
                    timestamped_dir.mkdir(parents=True, exist_ok=True)
                    vote_file = timestamped_dir / "vote.json"

                    # Get current state for context
                    current_answers = {aid: state.answer for aid, state in self.agent_states.items() if state.answer}

                    # Create anonymous agent mapping (agent1, agent2, etc.)
                    agent_mapping = self.coordination_tracker.get_anonymous_agent_mapping()

                    # Get answer labels from coordination tracker (e.g., "agent1.2", "agent2.1")
                    # Use the voter's context labels (what they were shown) to avoid race conditions
                    # in parallel execution where new answers may arrive while voting
                    available_answer_labels = []
                    answer_label_to_agent = {}  # Maps "agent1.2" -> "agent_a"
                    voted_for_label = None
                    voted_for_agent = vote_data.get("agent_id", "unknown")

                    if self.coordination_tracker:
                        # Get labels from voter's context (what they actually saw)
                        voter_context = self.coordination_tracker.get_agent_context_labels(agent_id)
                        for label in voter_context:
                            available_answer_labels.append(label)
                            # Extract agent number from label (e.g., "agent1.2" -> 1)
                            # and map back to agent ID
                            for aid in current_answers.keys():
                                aid_label = self.coordination_tracker.get_voted_for_label(
                                    agent_id,
                                    aid,
                                )
                                if aid_label == label:
                                    answer_label_to_agent[label] = aid

                        # Get the specific label for the voted-for agent
                        voted_for_label = self.coordination_tracker.get_voted_for_label(
                            agent_id,
                            voted_for_agent,
                        )

                    # Build comprehensive vote data
                    comprehensive_vote_data = {
                        "voter_id": agent_id,
                        "voter_anon_id": next(
                            (anon for anon, real in agent_mapping.items() if real == agent_id),
                            agent_id,
                        ),
                        "voted_for": voted_for_agent,
                        "voted_for_label": voted_for_label,  # e.g., "agent1.2"
                        "voted_for_anon": next(
                            (anon for anon, real in agent_mapping.items() if real == voted_for_agent),
                            "unknown",
                        ),
                        "reason": vote_data.get("reason", ""),
                        "timestamp": timestamp,
                        "unix_timestamp": time.time(),
                        "iteration": self.coordination_tracker.current_iteration if self.coordination_tracker else None,
                        "coordination_round": self.coordination_tracker.max_round if self.coordination_tracker else None,
                        "available_options": list(
                            current_answers.keys(),
                        ),  # agent IDs for backwards compatibility
                        "available_options_labels": available_answer_labels,  # e.g., ["agent1.2", "agent2.1"]
                        "answer_label_to_agent": answer_label_to_agent,  # Maps label -> agent_id
                        "available_options_anon": [
                            next(
                                (anon for anon, real in agent_mapping.items() if real == aid),
                                aid,
                            )
                            for aid in sorted(current_answers.keys())
                        ],
                        "agent_mapping": agent_mapping,
                        "vote_context": {
                            "total_agents": len(self.agents),
                            "agents_with_answers": len(current_answers),
                            "current_task": self.current_task,
                        },
                    }

                    # Write the comprehensive vote data
                    with open(vote_file, "w", encoding="utf-8") as f:
                        json.dump(comprehensive_vote_data, f, indent=2)
                    logger.info(
                        f"[Orchestrator._save_agent_snapshot] Saved comprehensive vote to {vote_file}",
                    )

            except Exception as e:
                logger.error(
                    f"[Orchestrator._save_agent_snapshot] Failed to save vote for {agent_id}: {e}",
                )
                logger.error(
                    f"[Orchestrator._save_agent_snapshot] Traceback: {traceback.format_exc()}",
                )

        # Save workspace snapshot with the same timestamp
        # Skip workspace saving for votes - workspace should be preserved from previous answer
        if agent.backend.filesystem_manager:
            if vote_data and not answer_content and not is_final:
                # Vote only - skip workspace snapshot to preserve previous answer's workspace
                logger.info(
                    "[Orchestrator._save_agent_snapshot] Skipping workspace snapshot for vote (preserving previous workspace)",
                )
            else:
                # Archive memories BEFORE clearing/snapshotting workspace
                workspace_path = agent.backend.filesystem_manager.get_current_workspace()
                if workspace_path:
                    self._archive_agent_memories(agent_id, Path(workspace_path))

                logger.info(
                    f"[Orchestrator._save_agent_snapshot] Agent {agent_id} has filesystem_manager, calling save_snapshot with timestamp={timestamp if not is_final else None}",
                )
                await agent.backend.filesystem_manager.save_snapshot(
                    timestamp=timestamp if not is_final else None,
                    is_final=is_final,
                    preserve_existing_snapshot=(answer_content is None and not is_final),
                )

                # Clear workspace after saving snapshot (but not for final snapshots).
                # In write_mode with active round isolation, defer clear until round cleanup
                # so cleanup_round() can auto-commit the actual round output.
                if not is_final:
                    pending_round_cleanup = agent_id in getattr(
                        self,
                        "_round_isolation_managers",
                        {},
                    )
                    if pending_round_cleanup:
                        logger.info(
                            f"[Orchestrator._save_agent_snapshot] Deferred workspace clear for {agent_id} " "(pending round isolation cleanup)",
                        )
                    else:
                        agent.backend.filesystem_manager.clear_workspace()
                        logger.info(
                            f"[Orchestrator._save_agent_snapshot] Cleared workspace for {agent_id} after saving snapshot",
                        )
                else:
                    # Final snapshot: restore workspace from snapshot_storage so
                    # post-evaluator can see the files
                    agent.backend.filesystem_manager.restore_from_snapshot_storage()
                    logger.info(
                        f"[Orchestrator._save_agent_snapshot] Restored workspace from snapshot_storage for {agent_id} (final snapshot)",
                    )
        else:
            logger.info(
                f"[Orchestrator._save_agent_snapshot] Agent {agent_id} does not have filesystem_manager",
            )

        # Save context if provided (unified context saving)
        if context_data:
            try:
                log_session_dir = get_log_session_dir()
                if log_session_dir:
                    if is_final:
                        timestamped_dir = log_session_dir / "final" / agent_id
                    else:
                        timestamped_dir = log_session_dir / agent_id / timestamp

                    # Ensure directory exists (may not have been created if no answer/vote)
                    timestamped_dir.mkdir(parents=True, exist_ok=True)
                    context_file = timestamped_dir / "context.txt"

                    # Handle different types of context data
                    if isinstance(context_data, dict):
                        # Pretty print dict/JSON data
                        context_file.write_text(
                            json.dumps(context_data, indent=2, default=str),
                        )
                    else:
                        # Save as string
                        context_file.write_text(str(context_data))

                    logger.info(
                        f"[Orchestrator._save_agent_snapshot] Saved context to {context_file}",
                    )
            except Exception as ce:
                logger.warning(
                    f"[Orchestrator._save_agent_snapshot] Failed to save context for {agent_id}: {ce}",
                )

        # Save execution trace whenever snapshotting is requested, including early-end
        # partial snapshots that may not contain an answer/vote yet.
        try:
            if hasattr(agent.backend, "_save_execution_trace"):
                # Save to log directory for historical tracking
                log_session_dir = get_log_session_dir()
                if log_session_dir:
                    if is_final:
                        timestamped_dir = log_session_dir / "final" / agent_id
                    else:
                        timestamped_dir = log_session_dir / agent_id / timestamp
                    timestamped_dir.mkdir(parents=True, exist_ok=True)
                    agent.backend._save_execution_trace(timestamped_dir)

                # Also save to snapshot_storage so other agents can access it
                # via temp_workspace when they receive context updates
                if agent.backend.filesystem_manager and agent.backend.filesystem_manager.snapshot_storage:
                    snapshot_storage = agent.backend.filesystem_manager.snapshot_storage
                    snapshot_storage.mkdir(parents=True, exist_ok=True)
                    agent.backend._save_execution_trace(snapshot_storage)
                    logger.debug(
                        f"[Orchestrator._save_agent_snapshot] Saved execution trace to snapshot_storage: {snapshot_storage}",
                    )
        except Exception as te:
            logger.warning(
                f"[Orchestrator._save_agent_snapshot] Failed to save execution trace for {agent_id}: {te}",
            )

        # Increment answer count and reset per-round checklist budget when an
        # actual answer is being saved.  This must live here (not inside
        # _archive_agent_memories) because memory archiving early-returns when
        # the agent has no memory/ directory, which would leave answer_count
        # stuck at 0 and block submit_checklist in subsequent rounds.
        if answer_content is not None and agent_id in self.agent_states:
            self.agent_states[agent_id].answer_count += 1
            self.agent_states[agent_id].checklist_calls_this_round = 0
            self.agent_states[agent_id].pending_checklist_recheck_labels = set()

        # Return the timestamp for tracking
        return timestamp if not is_final else "final"

    async def _save_partial_snapshots_for_early_termination(self) -> None:
        """Persist per-agent partial snapshots when orchestration ends before answer/vote."""
        for agent_id, state in self.agent_states.items():
            if state.is_killed:
                continue
            try:
                await self._save_agent_snapshot(
                    agent_id=agent_id,
                    answer_content=None,
                    vote_data=None,
                    is_final=False,
                    context_data=self.get_last_context(agent_id),
                )
            except Exception as e:
                logger.warning(
                    f"[Orchestrator] Failed to save early-termination snapshot for {agent_id}: {e}",
                )

    @staticmethod
    def _has_meaningful_workspace_content(path: Path | None) -> bool:
        """Return True when path includes deliverable files/directories."""
        return has_meaningful_content(path)

    @staticmethod
    def _copy_workspace_contents(
        source: Path,
        destination: Path,
        *,
        replace_destination: bool = False,
    ) -> int:
        """Copy top-level workspace contents from source to destination."""
        if not source.exists() or not source.is_dir():
            return 0

        if replace_destination and destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True, exist_ok=True)

        items_copied = 0
        for item in source.iterdir():
            if item.is_symlink():
                continue
            if item.is_file():
                shutil.copy2(item, destination / item.name)
                items_copied += 1
                continue
            if item.is_dir():
                shutil.copytree(
                    item,
                    destination / item.name,
                    dirs_exist_ok=True,
                    symlinks=True,
                    ignore_dangling_symlinks=True,
                )
                items_copied += 1
        return items_copied

    def _save_partial_workspace_snapshots_for_interrupted_turn(
        self,
        *,
        agent_id: str,
        backend: Any,
        timestamp: str,
        log_session_dir: Path | None,
    ) -> None:
        """Best-effort workspace snapshot persistence for interrupted turns."""
        filesystem_manager = getattr(backend, "filesystem_manager", None)
        if not filesystem_manager:
            return

        current_workspace = filesystem_manager.get_current_workspace()
        workspace_path = Path(current_workspace) if current_workspace else None
        if not workspace_path or not workspace_path.exists() or not workspace_path.is_dir():
            return

        snapshot_storage = filesystem_manager.snapshot_storage
        workspace_has_content = self._has_meaningful_workspace_content(workspace_path)
        snapshot_storage_has_content = self._has_meaningful_workspace_content(snapshot_storage)
        use_snapshot_storage_for_logs = not workspace_has_content and snapshot_storage_has_content

        if not workspace_has_content and not snapshot_storage_has_content:
            logger.debug(
                f"[Orchestrator] Skipping interrupted-turn workspace snapshot for {agent_id}: no meaningful content",
            )
            return

        if snapshot_storage:
            if snapshot_storage_has_content:
                # Never overwrite a submitted answer's snapshot during interrupted turn
                logger.info(
                    f"[Orchestrator] Preserving existing snapshot for {agent_id} during interrupted turn: " f"{snapshot_storage}",
                )
            elif workspace_has_content:
                copied = self._copy_workspace_contents(
                    workspace_path,
                    snapshot_storage,
                    replace_destination=True,
                )
                logger.info(
                    f"[Orchestrator] Saved interrupted-turn workspace snapshot for {agent_id} to " f"{snapshot_storage} ({copied} items)",
                )

        if log_session_dir:
            source_for_logs = snapshot_storage if use_snapshot_storage_for_logs else workspace_path
            if source_for_logs:
                workspace_log_dir = log_session_dir / agent_id / timestamp / "workspace"
                copied = self._copy_workspace_contents(
                    Path(source_for_logs),
                    workspace_log_dir,
                    replace_destination=False,
                )
                logger.info(
                    f"[Orchestrator] Saved interrupted-turn workspace log for {agent_id} to " f"{workspace_log_dir} ({copied} items)",
                )

    def _save_partial_execution_traces_for_interrupted_turn(self) -> None:
        """Best-effort trace/workspace persistence for interrupted turns."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        log_session_dir = get_log_session_dir()

        for agent_id, agent in self.agents.items():
            backend = getattr(agent, "backend", None)
            if not backend or not hasattr(backend, "_save_execution_trace"):
                continue

            try:
                self._save_partial_workspace_snapshots_for_interrupted_turn(
                    agent_id=agent_id,
                    backend=backend,
                    timestamp=timestamp,
                    log_session_dir=log_session_dir,
                )
            except Exception as e:
                logger.warning(
                    f"[Orchestrator] Failed to save interrupted-turn workspace snapshot for {agent_id}: {e}",
                )

            try:
                if log_session_dir:
                    trace_dir = log_session_dir / agent_id / timestamp
                    trace_dir.mkdir(parents=True, exist_ok=True)
                    backend._save_execution_trace(trace_dir)

                if backend.filesystem_manager and backend.filesystem_manager.snapshot_storage:
                    snapshot_storage = backend.filesystem_manager.snapshot_storage
                    snapshot_storage.mkdir(parents=True, exist_ok=True)
                    backend._save_execution_trace(snapshot_storage)
            except Exception as e:
                logger.warning(
                    f"[Orchestrator] Failed to save interrupted-turn trace for {agent_id}: {e}",
                )

    def get_last_context(self, agent_id: str) -> Any:
        """Get the last context for an agent, or None if not available."""
        return self.agent_states[agent_id].last_context if agent_id in self.agent_states else None

    async def _close_agent_stream(
        self,
        agent_id: str,
        active_streams: dict[str, AsyncGenerator],
    ) -> None:
        """Close and remove an agent stream safely."""
        if agent_id in active_streams:
            try:
                await active_streams[agent_id].aclose()
            except Exception:
                pass  # Ignore cleanup errors
            del active_streams[agent_id]

    def _check_restart_pending(self, agent_id: str) -> bool:
        """Check if agent should restart and yield restart message if needed. This will always be called when exiting out of _stream_agent_execution()."""
        restart_pending = self.agent_states[agent_id].restart_pending
        return restart_pending

    def _should_defer_restart_for_first_answer(self, agent_id: str) -> bool:
        """Check if restart/injection should be deferred for first-answer protection.

        Each agent is guaranteed to complete at least one full round and produce
        an answer before being restarted or injected with other agents' work.
        """
        state = self.agent_states.get(agent_id)
        if state is None:
            return False
        return state.answer is None

    async def _clear_framework_mcp_state(self, agent_id: str) -> None:
        """
        Clear in-memory state of framework MCP servers before agent restart.

        This ensures stateful MCPs like planning don't retain old data across
        answer submissions. Currently clears:
        - Task plans (planning MCP)

        Args:
            agent_id: ID of the agent being restarted
        """
        agent = self.agents.get(agent_id)
        if not agent or not hasattr(agent.backend, "_mcp_client") or not agent.backend._mcp_client:
            return

        # Find the planning MCP tool name for this agent
        planning_tool_name = None
        for tool_name in agent.backend._mcp_functions.keys():
            if "clear_task_plan" in tool_name and self._planning_server_name(agent_id) in tool_name:
                planning_tool_name = tool_name
                break

        if planning_tool_name:
            try:
                logger.info(
                    f"[Orchestrator] Clearing task plan for {agent_id} via {planning_tool_name}",
                )
                result, _ = await agent.backend._execute_mcp_function_with_retry(
                    planning_tool_name,
                    "{}",  # No arguments needed
                )
                logger.info(
                    f"[Orchestrator] Clear task plan result for {agent_id}: {result}",
                )
            except Exception as e:
                logger.warning(
                    f"[Orchestrator] Failed to clear task plan for {agent_id}: {e}",
                )

    def _compute_plan_progress_stats(self, workspace_path: str) -> dict[str, Any] | None:
        """Compute task/requirement progress stats for an agent's workspace.

        Reads the agent's tasks/plan.json or tasks/spec.json and computes how
        many items are completed vs total.  Works in both plan-and-execute mode
        and spec execution mode.

        Args:
            workspace_path: Path to the agent's workspace (temp workspace copy)

        Returns:
            Dict with progress stats, or None if not in execution mode or files missing
        """
        try:
            workspace = Path(workspace_path)
            tasks_plan = workspace / "tasks" / "plan.json"
            tasks_spec = workspace / "tasks" / "spec.json"

            # Check for plan.json first, then spec.json
            if tasks_plan.exists():
                artifact_file = tasks_plan
                items_key = "tasks"
            elif tasks_spec.exists():
                artifact_file = tasks_spec
                items_key = "requirements"
            else:
                return None

            # Read artifact
            tasks_data = json.loads(artifact_file.read_text())
            tasks = tasks_data.get(items_key, [])
            total_tasks = len(tasks)

            if total_tasks == 0:
                return None

            # Count by status (verified tasks count as completed for progress)
            completed = sum(1 for t in tasks if t.get("status") in ("completed", "verified"))
            in_progress = sum(1 for t in tasks if t.get("status") == "in_progress")
            pending = sum(1 for t in tasks if t.get("status") == "pending")

            return {
                "total": total_tasks,
                "completed": completed,
                "in_progress": in_progress,
                "pending": pending,
                "percent_complete": round(100 * completed / total_tasks, 1) if total_tasks > 0 else 0,
            }
        except Exception as e:
            logger.debug(f"[Orchestrator] Could not compute plan progress: {e}")
            return None

    def _build_tool_result_injection(
        self,
        agent_id: str,
        new_answers: dict[str, str],
        existing_answers: dict[str, str] | None = None,
    ) -> str:
        """Build compact injection content for appending to tool results.

        This creates a lighter-weight update message designed to be embedded
        in tool result content rather than sent as a separate user message.
        Used for mid-stream injection of peer updates during agent execution.

        Args:
            agent_id: The agent receiving the injection
            new_answers: Dict mapping agent_id to their NEW answer content
            existing_answers: Dict of answers agent already knew about (to detect updates)

        Returns:
            Formatted string to append to tool result content
        """
        existing_answers = existing_answers or {}

        # Normalize workspace paths for this agent's perspective
        normalized = self._normalize_workspace_paths_in_answers(
            new_answers,
            viewing_agent_id=agent_id,
        )

        # Get viewing agent's temporary workspace path
        temp_workspace_base = None
        viewing_agent = self.agents.get(agent_id)
        if viewing_agent and viewing_agent.backend.filesystem_manager:
            temp_workspace_base = str(
                viewing_agent.backend.filesystem_manager.agent_temporary_workspace,
            )

        # Create anonymous mapping (consistent with CURRENT ANSWERS format across all agents)
        agent_mapping = self.coordination_tracker.get_reverse_agent_mapping()
        context_labels = self.coordination_tracker.get_agent_context_labels(agent_id)

        # Format answers with workspace paths
        lines = []
        updated_agents = []
        new_agents = []
        updated_header_entries = []
        new_header_entries = []
        transition_lines = []

        for aid, answer in normalized.items():
            anon_id = agent_mapping.get(aid, f"agent_{aid}")
            is_update = aid in existing_answers

            if is_update:
                updated_agents.append(anon_id)
            else:
                new_agents.append(anon_id)

            # Build explicit answer-label transitions so agents can score newest labels.
            latest_revisions = self.coordination_tracker.answers_by_agent.get(aid, [])
            latest_label = str(getattr(latest_revisions[-1], "label", "")) if latest_revisions else ""
            old_label = ""
            if latest_label and "." in latest_label:
                label_prefix = latest_label.split(".", 1)[0] + "."
                old_label = next((lbl for lbl in context_labels if lbl.startswith(label_prefix)), "")

            if is_update and old_label and latest_label and old_label != latest_label:
                updated_header_entries.append(f"{anon_id} ({old_label} -> {latest_label})")
                transition_lines.append(
                    f"  - {anon_id}: {old_label} -> {latest_label}",
                )
            elif not is_update and latest_label:
                new_header_entries.append(f"{anon_id} ({latest_label})")
                transition_lines.append(
                    f"  - {anon_id}: now available as {latest_label}",
                )
            elif is_update:
                # Fallback if labels are unavailable in edge cases
                updated_header_entries.append(anon_id)
            else:
                new_header_entries.append(anon_id)

            # Truncate long answers for injection context
            truncated = answer[:500] + "..." if len(answer) > 500 else answer

            # Include workspace path for file access
            workspace_path = os.path.join(temp_workspace_base, anon_id) if temp_workspace_base else f"temp_workspaces/{anon_id}"
            lines.append(f"  [{anon_id}] (workspace: {workspace_path}):")

            # Compute and include progress stats if in plan execution mode
            progress = self._compute_plan_progress_stats(workspace_path)
            if progress:
                lines.append(
                    f"    📊 Progress: {progress['completed']}/{progress['total']} tasks completed "
                    f"({progress['percent_complete']}%) | {progress['in_progress']} in progress | {progress['pending']} pending",
                )
                lines.append("    ⚠️  Note: Progress stats are INFORMATIONAL - evaluate the DELIVERABLE quality, not task count")

            lines.append(f"    {truncated}")
            lines.append("")

        # Build header based on what changed
        if updated_agents and new_agents:
            header = f"[UPDATE: {', '.join(new_header_entries)} submitted new answer(s); " f"{', '.join(updated_header_entries)} updated their answer(s)]"
        elif updated_agents:
            header = f"[UPDATE: {', '.join(updated_header_entries)} updated their answer(s)]"
        else:
            header = f"[UPDATE: {', '.join(new_header_entries)} submitted new answer(s)]"

        # Use different framing for decomposition mode vs voting mode
        is_decomposition = getattr(self.config, "coordination_mode", "voting") == "decomposition"
        is_checklist_mode = getattr(self.config, "voting_sensitivity", "balanced") == "checklist_gated"

        if is_decomposition:
            injection_parts = [
                "",
                "=" * 60,
                "UPDATE: ANOTHER AGENT SUBMITTED WORK",
                "=" * 60,
                "",
                header,
                "",
                "ANSWER LABEL UPDATES:",
                *(transition_lines or ["  - (no label change details available)"]),
                "",
                *lines,
                "=" * 60,
            ]
            if is_checklist_mode:
                injection_parts.extend(
                    [
                        "CHECKLIST-GATED ACTIONS (REQUIRED):",
                        "=" * 60,
                        "",
                        "1. Read and understand their full work — maintain awareness of the entire project state",
                        "2. Keep ownership-first: spend most effort on your subtask; touch other areas only for adjacent integration",
                        "3. Integrate boundary dependencies (interfaces/contracts/shared assets) without taking over unrelated scopes",
                        "4. Use submit_checklist with the newest labels shown above before deciding to `stop` or continue iterating",
                        "5. If checklist was already accepted this round and this update is new:",
                        "   - Preferred: submit only the injected newest labels (delta recheck)",
                        "   - Also allowed: submit all latest labels in your current context",
                        "6. If submit_checklist returns a validation error, fix payload/report and call submit_checklist again",
                        "7. If checklist returns iterate (new_answer), call draft_approach, implement, then call new_answer",
                        "8. Call `stop` only after the latest checklist result supports stopping and you have no new work to share",
                        "",
                        "DO NOT ignore this update - checklist flow must be re-run on newest labels.",
                        "=" * 60,
                    ],
                )
            else:
                injection_parts.extend(
                    [
                        "RECOMMENDED ACTIONS:",
                        "=" * 60,
                        "",
                        "1. Read and understand their full work — maintain awareness of the entire project state",
                        "2. Keep ownership-first: spend most effort on your subtask; touch other areas only for adjacent integration",
                        "3. Integrate boundary dependencies (interfaces/contracts/shared assets) without taking over unrelated scopes",
                        "4. Continue refining your own work — fix issues, improve quality, incorporate insights",
                        "5. If you submit `new_answer`, include concrete deliverables + validation evidence + integration notes",
                        "6. Call `stop` only when you've reviewed everything and are satisfied — no new work to share",
                        "",
                        "=" * 60,
                    ],
                )
        else:
            injection_parts = [
                "",
                "=" * 60,
                "⚠️  IMPORTANT: NEW ANSWER RECEIVED - ACTION REQUIRED",
                "=" * 60,
                "",
                header,
                "",
                "ANSWER LABEL UPDATES:",
                *(transition_lines or ["  - (no label change details available)"]),
                "",
                *lines,
                "=" * 60,
            ]
            if is_checklist_mode:
                injection_parts.extend(
                    [
                        "CHECKLIST-GATED ACTIONS (REQUIRED):",
                        "=" * 60,
                        "",
                        "1. Add a task: 'Evaluate injected answer label updates and re-run checklist'",
                        "2. Read injected workspace files, then compare to your current work",
                        "3. Use submit_checklist with the newest labels shown above",
                        "4. If checklist was already accepted this round and this update is new:",
                        "   - Preferred: submit only the injected newest labels (delta recheck)",
                        "   - Also allowed: submit all latest labels in your current context",
                        "5. If submit_checklist returns a validation error, fix payload/report and call submit_checklist again",
                        "6. If checklist returns iterate (new_answer), call draft_approach, implement, then call new_answer",
                        "DO NOT ignore this update - checklist flow must be re-run on newest labels.",
                        "=" * 60,
                    ],
                )
            else:
                injection_parts.extend(
                    [
                        "REQUIRED ACTION - You MUST do one of the following:",
                        "=" * 60,
                        "",
                        "1. **ADD A TASK** to your plan: 'Evaluate agent answer(s) and decide next action'",
                        "   - Use update_task_status or create a new task to track this evaluation",
                        "   - Read their workspace files (paths above) to understand their solution",
                        "   - Compare their approach to yours",
                        "",
                        "2. **THEN CHOOSE ONE**:",
                        "   a) VOTE for their answer if it's complete and correct (use vote tool)",
                        "   b) BUILD on their work - improve/extend it and submit YOUR enhanced answer",
                        "   c) MERGE approaches - combine the best parts of their work with yours",
                        "   d) CONTINUE your own approach if you believe it's better",
                        "",
                        "DO NOT ignore this update - you must explicitly evaluate and decide!",
                        "=" * 60,
                    ],
                )

        # Append essential files from injected agents so the receiving agent
        # can evaluate without re-reading from workspace
        essential_files_block = self._build_essential_files_for_injection(
            agent_id,
            list(new_answers.keys()),
        )
        if essential_files_block:
            injection_parts.extend(["", essential_files_block])

        return "\n".join(injection_parts)

    def _build_essential_files_for_injection(
        self,
        receiving_agent_id: str,
        source_agent_ids: list[str],
    ) -> str | None:
        """Build essential files content for mid-stream injection.

        Loads manifests from the injected agents and formats pre-loaded
        content so the receiving agent can evaluate without re-reading.
        """
        if not self._snapshot_storage:
            return None

        # Load manifests only for the source agents being injected
        agent_mapping = self.coordination_tracker.get_reverse_agent_mapping()
        manifests: dict[str, Any] = {}
        snapshot_base = Path(self._snapshot_storage)

        for source_agent_id in source_agent_ids:
            anon_id = agent_mapping.get(source_agent_id, source_agent_id)
            manifest_path = snapshot_base / source_agent_id / "memory" / "short_term" / "essential_files_manifest.json"
            if not manifest_path.exists():
                continue
            try:
                manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
                if isinstance(manifest_data, dict) and manifest_data.get("version") == 1:
                    manifests[anon_id] = manifest_data
            except (json.JSONDecodeError, OSError):
                pass

        if not manifests:
            return None

        return self._format_essential_files_context_block(manifests, receiving_agent_id)

    def _on_subagent_complete(
        self,
        parent_agent_id: str,
        subagent_id: str,
        result: "SubagentResult",
    ) -> None:
        """Callback invoked when a background subagent completes.

        This is registered with SubagentManager and called asynchronously when
        any background subagent finishes execution. The result is queued for
        injection into the parent agent's context via SubagentCompleteHook.

        Args:
            parent_agent_id: ID of the parent agent that spawned the subagent
            subagent_id: ID of the completed subagent
            result: The SubagentResult from execution
        """
        if parent_agent_id not in self._pending_subagent_results:
            self._pending_subagent_results[parent_agent_id] = []
        self._pending_subagent_results[parent_agent_id].append((subagent_id, result))
        logger.info(
            f"[Orchestrator] Background subagent {subagent_id} completed for {parent_agent_id} " f"(status={result.status}, success={result.success})",
        )
        self._schedule_background_wait_interrupt_for_agent(
            parent_agent_id,
            trigger="background_subagent_complete",
        )

    def _on_background_subagent_complete(
        self,
        parent_agent_id: str,
        subagent_id: str,
        result: "SubagentResult",
    ) -> None:
        """Compatibility wrapper for orchestrator-owned background subagent completions."""
        self._on_subagent_complete(
            parent_agent_id,
            subagent_id,
            result,
        )

    def _schedule_background_wait_interrupt_for_agent(
        self,
        agent_id: str,
        trigger: str = "background_subagent_complete",
    ) -> None:
        """Best-effort scheduling for runtime wait interruption delivery."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        loop.create_task(
            self._maybe_interrupt_background_wait_for_agent(
                agent_id,
                trigger=trigger,
            ),
        )

    async def _get_pending_subagent_results_async(
        self,
        agent_id: str,
    ) -> list[tuple[str, "SubagentResult"]]:
        """Get pending subagent results for an agent by polling the MCP server.

        This is called by SubagentCompleteHook to retrieve completed subagent results
        for injection. Polls the subagent MCP server to find completed subagents,
        fetches their results, and tracks which ones have been injected.

        Args:
            agent_id: The agent to get pending results for

        Returns:
            List of (subagent_id, SubagentResult) tuples, or empty list
        """
        try:
            # Get the agent to access its backend MCP tool bridge.
            agent = self.agents.get(agent_id)
            if not agent:
                return []

            # Initialize injected set for this agent if needed
            if agent_id not in self._injected_subagents:
                self._injected_subagents[agent_id] = set()

            # Poll the subagent MCP server for all subagents.
            list_result = await self._call_subagent_mcp_tool_async(
                parent_agent_id=agent_id,
                tool_name="list_subagents",
                params={},
            )

            if not isinstance(list_result, dict):
                return []

            if not list_result.get("success") or not list_result.get("subagents"):
                return []

            # Import here to avoid circular import at module load.
            from massgen.subagent.models import SubagentResult as RuntimeSubagentResult

            # Find completed subagents that haven't been injected yet
            pending_results = []
            for subagent_info in list_result["subagents"]:
                subagent_id = subagent_info.get("subagent_id")
                status = subagent_info.get("status")

                # Skip if not completed or already injected
                if status != "completed" or subagent_id in self._injected_subagents[agent_id]:
                    continue

                # list_subagents includes a full result payload for completed in-memory
                # subagents. Registry-only historical entries may not include it.
                result_data = subagent_info.get("result")
                if not isinstance(result_data, dict):
                    continue

                try:
                    result = RuntimeSubagentResult.from_dict(result_data)
                except Exception:
                    result = RuntimeSubagentResult(
                        subagent_id=result_data.get("subagent_id", subagent_id),
                        success=result_data.get("success", False),
                        status=result_data.get("status", "error"),
                        answer=result_data.get("answer", ""),
                        error=result_data.get("error"),
                        workspace_path=result_data.get("workspace_path", result_data.get("workspace", "")),
                        execution_time_seconds=result_data.get("execution_time_seconds", 0.0),
                        token_usage=result_data.get("token_usage", {}),
                    )

                pending_results.append((subagent_id, result))
                # Mark as injected
                self._injected_subagents[agent_id].add(subagent_id)
                logger.debug(
                    f"[Orchestrator] Fetched completed subagent {subagent_id} for {agent_id} " f"(status={result.status})",
                )

            if pending_results:
                logger.debug(
                    f"[Orchestrator] Retrieved {len(pending_results)} completed subagent(s) for {agent_id}",
                )

            return pending_results

        except Exception as e:
            logger.error(f"[Orchestrator] Error polling for completed subagents: {e}", exc_info=True)
            return []

    async def _collect_pending_subagent_results_async(
        self,
        agent_id: str,
    ) -> list[tuple[str, "SubagentResult"]]:
        """Return deduplicated pending subagent results from local and MCP queues."""
        pending_subagent_results: list[tuple[str, "SubagentResult"]] = []

        local_pending = list(self._pending_subagent_results.get(agent_id, []))
        if local_pending:
            pending_subagent_results.extend(local_pending)

        polled_pending = await self._get_pending_subagent_results_async(agent_id)
        if polled_pending:
            pending_subagent_results.extend(polled_pending)

        if not pending_subagent_results:
            return []

        deduped_results: dict[str, "SubagentResult"] = {}
        for subagent_id, result in pending_subagent_results:
            deduped_results[subagent_id] = result

        return list(deduped_results.items())

    async def _cancel_running_subagents_for_agent(
        self,
        agent_id: str,
    ) -> int:
        """Cancel active subagents owned by a specific parent agent."""
        try:
            list_result = await self._call_subagent_mcp_tool_async(
                parent_agent_id=agent_id,
                tool_name="list_subagents",
                params={},
            )
        except Exception as exc:
            logger.debug(
                "[Orchestrator] Failed to list subagents for cancellation (%s): %s",
                agent_id,
                exc,
                exc_info=True,
            )
            return 0

        if not isinstance(list_result, dict) or not list_result.get("success"):
            return 0

        subagents = list_result.get("subagents")
        if not isinstance(subagents, list):
            return 0

        active_ids: set[str] = set()
        for entry in subagents:
            if not isinstance(entry, dict):
                continue
            subagent_id = str(entry.get("subagent_id") or "").strip()
            status = str(entry.get("status") or "").strip().lower()
            if subagent_id and status in {"running", "pending"}:
                active_ids.add(subagent_id)

        cancelled = 0
        for subagent_id in sorted(active_ids):
            try:
                cancel_result = await self._call_subagent_mcp_tool_async(
                    parent_agent_id=agent_id,
                    tool_name="cancel_subagent",
                    params={"subagent_id": subagent_id},
                )
            except Exception as exc:
                logger.debug(
                    "[Orchestrator] Failed to cancel subagent %s for %s: %s",
                    subagent_id,
                    agent_id,
                    exc,
                    exc_info=True,
                )
                continue

            if isinstance(cancel_result, dict) and cancel_result.get("success"):
                cancelled += 1

        return cancelled

    async def _cancel_running_background_work_for_agent(self, agent_id: str) -> None:
        """Cancel active subagents and background tool jobs for an agent at round end."""
        cancelled_subagents = await self._cancel_running_subagents_for_agent(agent_id)
        cancelled_background_jobs = False

        agent = self.agents.get(agent_id)
        backend = getattr(agent, "backend", None) if agent else None
        cancel_background_jobs = getattr(backend, "_cancel_all_background_tool_jobs", None)
        if callable(cancel_background_jobs):
            try:
                maybe_awaitable = cancel_background_jobs()
                if inspect.isawaitable(maybe_awaitable):
                    await maybe_awaitable
                cancelled_background_jobs = True
            except Exception as exc:
                logger.debug(
                    "[Orchestrator] Failed to cancel background jobs for %s: %s",
                    agent_id,
                    exc,
                    exc_info=True,
                )

        # Cancel in-flight trace analyzer task
        cancelled_trace = False
        trace_task = self._background_trace_tasks.pop(agent_id, None)
        if trace_task and not trace_task.done():
            trace_task.cancel()
            cancelled_trace = True

        if cancelled_subagents or cancelled_background_jobs or cancelled_trace:
            logger.info(
                "[Orchestrator] Round-end cleanup for %s: " "cancelled_subagents=%s, cancelled_background_jobs=%s, " "cancelled_trace_analyzer=%s",
                agent_id,
                cancelled_subagents,
                cancelled_background_jobs,
                cancelled_trace,
            )

    def _get_pending_subagent_results(
        self,
        agent_id: str,
    ) -> list[tuple[str, "SubagentResult"]]:
        """Sync wrapper for compatibility with existing sync call sites."""
        from .utils import run_async_safely

        return run_async_safely(self._get_pending_subagent_results_async(agent_id))

    def _setup_hook_manager_for_agent(
        self,
        agent_id: str,
        agent: ChatAgent,
        answers: dict[str, str],
    ) -> None:
        """Set up hooks for agent - uses native adapter for Claude Code, GeneralHookManager for others.

        This routes hook setup based on backend capabilities:
        - Backends with native hook support (Claude Code): Use NativeHookAdapter
        - Standard backends: Use GeneralHookManager

        Both paths set up the same hooks:
        1. MidStreamInjectionHook - injects answers from other agents into tool results
        2. HighPriorityTaskReminderHook - reminds to document high-priority task completions (round mode only)

        Args:
            agent_id: The agent identifier
            agent: The ChatAgent instance
            answers: Dict of existing answers when agent started (used to detect new answers)
        """
        # Runtime human input must work for all backends, including those that
        # don't support hook registration (hookless fallback / Codex path).
        self._ensure_runtime_human_input_hook_initialized()
        self._ensure_runtime_inbox_poller_initialized()

        # Check if backend supports native hooks (e.g., Claude Code)
        if hasattr(agent.backend, "supports_native_hooks") and agent.backend.supports_native_hooks():
            self._setup_native_hooks_for_agent(agent_id, agent, answers)
            return

        # Check if backend supports MCP server-level hooks (e.g., Codex)
        if hasattr(agent.backend, "supports_mcp_server_hooks") and agent.backend.supports_mcp_server_hooks():
            self._setup_codex_mcp_hooks(agent_id, agent, answers)
            return

        # Fall back to GeneralHookManager for standard backends
        if not hasattr(agent.backend, "set_general_hook_manager"):
            return

        # Create hook manager
        manager = GeneralHookManager()

        # Create mid-stream injection hook with closure-based callback
        mid_stream_hook = MidStreamInjectionHook()

        # Define the injection callback (captures agent_id and answers)
        # This is async to allow copying snapshots before injection
        async def get_injection_content() -> str | None:
            """Check if mid-stream injection is needed and return content."""
            # Skip injection if disabled (multi-agent refinement OFF mode)
            # Agents work independently without seeing each other's work
            if self.config.disable_injection:
                return None

            if not self._check_restart_pending(agent_id):
                return None

            # First-answer protection: don't inject into an agent that hasn't
            # produced its first answer yet.
            if self._should_defer_restart_for_first_answer(agent_id):
                self.agent_states[agent_id].restart_pending = False
                return None

            # In vote-only mode, skip injection and force a full restart instead.
            # Mid-stream injection can't update tool schemas, so agents in vote-only mode
            # wouldn't be able to vote for newly discovered answers (the vote enum is fixed
            # at stream start). A full restart gives them updated tool schemas.
            if self._is_vote_only_mode(agent_id):
                return None  # Let restart happen instead

            if self._should_defer_peer_updates_until_restart(agent_id):
                if self._has_unseen_answer_updates(agent_id):
                    self.agent_states[agent_id].restart_pending = True
                    logger.info(
                        "[Orchestrator] Deferring peer answer update injection until restart for %s",
                        agent_id,
                    )
                else:
                    self.agent_states[agent_id].restart_pending = False
                return None

            # Get CURRENT answers (includes virtual agents in step mode)
            current_answers = self._get_current_answers_snapshot()
            selected_answers, had_unseen_updates = self._select_midstream_answer_updates(
                agent_id,
                current_answers,
            )

            if not selected_answers:
                if had_unseen_updates:
                    # Keep restart pending when unseen updates still exist.
                    self.agent_states[agent_id].restart_pending = True
                    cap = getattr(self.config, "max_midstream_injections_per_round", 2)
                    logger.info(
                        "[Orchestrator] Skipping mid-stream injection for %s: per-round cap reached (%s)",
                        agent_id,
                        cap,
                    )
                else:
                    # No unseen updates remain: this was a stale restart_pending flag.
                    self.agent_states[agent_id].restart_pending = False
                return None

            # TIMING CONSTRAINT: Skip injection if too close to soft timeout
            if self._should_skip_injection_due_to_timeout(agent_id):
                return None  # Let restart happen instead

            # Copy snapshots from new answer agents to temp workspace BEFORE building injection
            # This ensures the workspace files are available when the agent tries to access them
            logger.info(
                f"[Orchestrator] Copying snapshots for mid-stream injection to {agent_id}",
            )
            await self._copy_all_snapshots_to_temp_workspace(agent_id)

            # Build injection content (pass existing answers to detect updates vs new)
            injection = self._build_tool_result_injection(
                agent_id,
                selected_answers,
                existing_answers=answers,
            )

            # Debug: Log what's in the temp workspace for each injected agent
            viewing_agent = self.agents.get(agent_id)
            if viewing_agent and viewing_agent.backend.filesystem_manager:
                temp_workspace_base = str(
                    viewing_agent.backend.filesystem_manager.agent_temporary_workspace,
                )
                agent_mapping = self.coordination_tracker.get_reverse_agent_mapping()
                for aid in selected_answers.keys():
                    anon_id = agent_mapping.get(aid, f"agent_{aid}")
                    workspace_path = os.path.join(temp_workspace_base, anon_id)
                    if os.path.exists(workspace_path):
                        try:
                            files = os.listdir(workspace_path)
                            logger.debug(
                                f"[Orchestrator] Injection workspace {workspace_path} contains: {files}",
                            )
                        except OSError as e:
                            logger.debug(
                                f"[Orchestrator] Could not list workspace {workspace_path}: {e}",
                            )
                    else:
                        logger.debug(
                            f"[Orchestrator] Injection workspace {workspace_path} does NOT exist!",
                        )

            # Increment injection count
            self.agent_states[agent_id].injection_count += 1
            self.agent_states[agent_id].midstream_injections_this_round += len(selected_answers)

            # Update answers to include newly injected answers (prevents re-injection)
            # This mutates the captured closure variable so future callbacks see updated state
            answers.update(selected_answers)

            # Update known_answer_ids so vote validation knows this agent has seen these
            self.agent_states[agent_id].known_answer_ids.update(selected_answers.keys())
            self._register_injected_answer_updates(agent_id, list(selected_answers.keys()))
            self._mark_pending_checklist_recheck_labels(agent_id, list(selected_answers.keys()))

            # Keep restart pending if additional unseen revisions still remain.
            self.agent_states[agent_id].restart_pending = self._has_unseen_answer_updates(agent_id)

            # Track the injection
            logger.info(
                f"[Orchestrator] Mid-stream injection for {agent_id}: {len(selected_answers)} answer update(s)",
            )
            # Log the actual injection content at debug level (may contain sensitive data)
            preview = injection[:2000] + ("..." if len(injection) > 2000 else "")
            logger.debug(f"[Orchestrator] Injection content (truncated):\n{preview}")
            self.coordination_tracker.track_agent_action(
                agent_id,
                ActionType.UPDATE_INJECTED,
                f"Mid-stream: {len(selected_answers)} answer(s)",
            )

            # Emit injection_received event for TUI

            _inj_emitter = get_event_emitter()
            if _inj_emitter:
                _inj_emitter.emit_injection_received(
                    agent_id=agent_id,
                    source_agents=list(selected_answers.keys()),
                    injection_type="mid_stream",
                )

            # Update agent's context labels first, then refresh checklist state so
            # available_agent_labels reflects the newly-injected labels (e.g. agent1.2
            # replacing agent1.1). Refreshing before updating would leave stale labels.
            self.coordination_tracker.update_agent_context_with_new_answers(
                agent_id,
                list(selected_answers.keys()),
            )
            self._refresh_checklist_state_for_agent(agent_id)

            return injection

        # Set callback on hook
        mid_stream_hook.set_callback(get_injection_content)

        # Register mid-stream injection hook first (maintains current behavior order)
        manager.register_global_hook(HookType.POST_TOOL_USE, mid_stream_hook)

        # Register high-priority task reminder hook (enabled round-wise when capture is enabled)
        if self._is_round_learning_capture_enabled():
            reminder_hook = HighPriorityTaskReminderHook()
            manager.register_global_hook(HookType.POST_TOOL_USE, reminder_hook)

        # Register media call ledger hook (read_media/generate_media provenance capture)
        manager.register_global_hook(HookType.POST_TOOL_USE, MediaCallLedgerHook())

        # Register human input hook (shared across all agents)
        manager.register_global_hook(HookType.POST_TOOL_USE, self._human_input_hook)

        # Register subagent completion hook for background result injection
        if self._background_subagents_enabled:
            subagent_hook = SubagentCompleteHook(
                injection_strategy=self._background_subagent_injection_strategy,
            )

            # Create a closure that captures agent_id for pending results retrieval
            def make_pending_getter(aid: str):
                return lambda: self._get_pending_subagent_results_async(aid)

            subagent_hook.set_pending_results_getter(make_pending_getter(agent_id))
            manager.register_global_hook(HookType.POST_TOOL_USE, subagent_hook)
            logger.debug(f"[Orchestrator] Registered SubagentCompleteHook for {agent_id}")

            # Wire background tool delegate so list/status/result/cancel route to subagents
            if hasattr(agent.backend, "register_background_delegate"):
                from massgen.subagent.background_delegate import (
                    SubagentBackgroundDelegate,
                )

                def _make_call_tool(aid: str):
                    return lambda tool_name, params: self._call_subagent_mcp_tool_async(
                        aid,
                        tool_name,
                        params,
                    )

                delegate = SubagentBackgroundDelegate(
                    call_tool=_make_call_tool(agent_id),
                    agent_id=agent_id,
                )
                agent.backend.register_background_delegate(delegate)
                logger.debug(f"[Orchestrator] Registered SubagentBackgroundDelegate for {agent_id}")

        # Register background tool completion hook for async tool result injection
        if hasattr(agent.backend, "get_pending_background_tool_results"):
            background_tool_hook = BackgroundToolCompleteHook()
            background_tool_hook.set_completed_jobs_getter(
                agent.backend.get_pending_background_tool_results,
            )
            manager.register_global_hook(HookType.POST_TOOL_USE, background_tool_hook)
            logger.debug(
                f"[Orchestrator] Registered BackgroundToolCompleteHook for {agent_id}",
            )
        # Register per-round timeout hooks if configured
        self._register_round_timeout_hooks(agent_id, manager)

        # Register user-configured hooks from agent backend config
        if hasattr(agent.backend, "config") and agent.backend.config:
            agent_hooks = agent.backend.config.get("hooks")
            if agent_hooks:
                manager.register_hooks_from_config(agent_hooks, agent_id=agent_id)
                logger.debug(
                    f"[Orchestrator] Registered user-configured hooks for {agent_id}",
                )

        # Set manager on backend
        agent.backend.set_general_hook_manager(manager)
        if hasattr(agent.backend, "set_background_wait_interrupt_provider"):

            async def _wait_interrupt_provider(
                requested_agent_id: str,
                *,
                _agent_id: str = agent_id,
            ) -> dict[str, Any] | None:
                target_agent_id = requested_agent_id or _agent_id
                if hasattr(self, "cancellation_manager") and self.cancellation_manager and self.cancellation_manager.is_cancelled:
                    return {
                        "interrupt_reason": "turn_cancelled",
                        "injected_content": None,
                    }

                runtime_sections = await self._collect_no_hook_runtime_fallback_sections(
                    target_agent_id,
                )
                if not runtime_sections:
                    return None
                return {
                    "interrupt_reason": "runtime_injection_available",
                    "injected_content": "\n".join(runtime_sections),
                }

            agent.backend.set_background_wait_interrupt_provider(
                _wait_interrupt_provider,
            )
        logger.debug(
            f"[Orchestrator] Set up hook manager for {agent_id} with mid-stream and reminder hooks",
        )

    def _setup_codex_mcp_hooks(
        self,
        agent_id: str,
        agent: ChatAgent,
        answers: dict[str, str],
    ) -> None:
        """Set up MCP server-level hook delivery for Codex backends.

        Instead of registering hooks on a GeneralHookManager, this stores a
        reference so the streaming loop can call _flush_codex_hook_payloads()
        to write injection files that the MCP middleware consumes.
        """
        # Mark this agent as using MCP server hooks
        if not hasattr(self, "_codex_mcp_hook_agents"):
            self._codex_mcp_hook_agents: dict[str, dict[str, Any]] = {}

        self._codex_mcp_hook_agents[agent_id] = {
            "agent": agent,
            "answers": answers,
        }

        # Set up the background wait interrupt provider (reuse existing pattern)
        if hasattr(agent.backend, "set_background_wait_interrupt_provider"):

            async def _wait_interrupt_provider(
                requested_agent_id: str,
                *,
                _agent_id: str = agent_id,
            ) -> dict[str, Any] | None:
                target_agent_id = requested_agent_id or _agent_id
                if hasattr(self, "cancellation_manager") and self.cancellation_manager and self.cancellation_manager.is_cancelled:
                    return {
                        "interrupt_reason": "turn_cancelled",
                        "injected_content": None,
                    }

                runtime_sections = await self._collect_no_hook_runtime_fallback_sections(
                    target_agent_id,
                )
                if not runtime_sections:
                    return None
                return {
                    "interrupt_reason": "runtime_injection_available",
                    "injected_content": "\n".join(runtime_sections),
                }

            agent.backend.set_background_wait_interrupt_provider(
                _wait_interrupt_provider,
            )

        logger.info(
            "[Orchestrator] Set up MCP server-level hook delivery for %s",
            agent_id,
        )

    async def _flush_codex_hook_payloads(
        self,
        agent_id: str,
        agent: ChatAgent,
        answers: dict[str, str],
    ) -> None:
        """Write pending injection content to hook file for MCP middleware.

        Called from the streaming loop. Checks for peer answer updates,
        human input, subagent completions, and background tool results.
        If any content is pending, writes it to the hook file.
        """
        if not hasattr(agent.backend, "write_post_tool_use_hook"):
            return

        # Skip injection if disabled
        if self.config.disable_injection:
            return

        injection_parts: list[str] = []
        wrote_subagent_payload = False

        # 0. Poll runtime inbox for messages from parent (subagent mode)
        self._poll_runtime_inbox()

        # 1. Check for human input
        if self._human_input_hook:
            if hasattr(self._human_input_hook, "has_pending_input_for_agent"):
                has_input = self._human_input_hook.has_pending_input_for_agent(agent_id)
            else:
                has_input = self._human_input_hook.has_pending_input()

            if has_input:
                # Collect human input for this agent
                pass

                ctx = {
                    "agent_id": agent_id,
                    "hook_type": "PostToolUse",
                    # Suppress inject callback — Codex hook file may not be consumed
                    # until a tool call or round-end carryforward. The TUI should only
                    # show "Delivered" when content is confirmed consumed by the model.
                    "suppress_inject_callback": True,
                }
                result = await self._human_input_hook.execute("_flush", "{}", ctx)
                if result.inject and result.inject.get("content"):
                    injection_parts.append(result.inject["content"])
                    # Track that we wrote human input with suppressed callback.
                    # At round-end, we'll fire the callback once delivery is confirmed.
                    if not hasattr(self, "_codex_pending_inject_confirmation"):
                        self._codex_pending_inject_confirmation: dict[str, str] = {}
                    self._codex_pending_inject_confirmation[agent_id] = result.inject["content"]

        # 2. Check for subagent completions
        if self._background_subagents_enabled:
            pending = await self._collect_pending_subagent_results_async(agent_id)
            if pending:
                from massgen.subagent.result_formatter import format_batch_results

                injection_parts.append(format_batch_results(pending))
                wrote_subagent_payload = True

        # 3. Check for background tool completions
        if hasattr(agent.backend, "get_pending_background_tool_results"):
            try:
                completed_jobs = agent.backend.get_pending_background_tool_results() or []
                if completed_jobs:
                    from massgen.mcp_tools.hooks import BackgroundToolCompleteHook

                    hook = BackgroundToolCompleteHook()
                    injection_parts.append(hook._format_completed_jobs(completed_jobs))
            except Exception as e:
                logger.warning(
                    "[Orchestrator] Failed to poll background tool results for %s: %s",
                    agent_id,
                    e,
                )

        # 4. Check for peer answer updates
        if self._check_restart_pending(agent_id):
            if not self._should_defer_restart_for_first_answer(agent_id):
                if not self._is_vote_only_mode(agent_id):
                    if self._should_defer_peer_updates_until_restart(agent_id):
                        if self._has_unseen_answer_updates(agent_id):
                            self.agent_states[agent_id].restart_pending = True
                            logger.info(
                                "[Orchestrator] Deferring MCP peer answer update injection until restart for %s",
                                agent_id,
                            )
                        else:
                            self.agent_states[agent_id].restart_pending = False
                    else:
                        current_answers = self._get_current_answers_snapshot()
                        selected_answers, _had_unseen_updates = self._select_midstream_answer_updates(
                            agent_id,
                            current_answers,
                        )

                        if selected_answers:
                            if not self._should_skip_injection_due_to_timeout(agent_id):
                                await self._copy_all_snapshots_to_temp_workspace(agent_id)

                                answer_injection = self._build_tool_result_injection(
                                    agent_id,
                                    selected_answers,
                                    existing_answers=answers,
                                )
                                injection_parts.append(answer_injection)

                                # Track the injection
                                self.agent_states[agent_id].injection_count += 1
                                self.agent_states[agent_id].midstream_injections_this_round += len(selected_answers)
                                answers.update(selected_answers)
                                self.agent_states[agent_id].known_answer_ids.update(selected_answers.keys())
                                self._register_injected_answer_updates(agent_id, list(selected_answers.keys()))
                                self._mark_pending_checklist_recheck_labels(agent_id, list(selected_answers.keys()))
                                # Update context labels BEFORE refreshing checklist state so
                                # available_agent_labels reflects the newly-injected labels
                                # (e.g. agent1.2 replacing agent1.1). Same ordering as the
                                # mid-stream hook path at _build_injection_callback.
                                self.coordination_tracker.update_agent_context_with_new_answers(
                                    agent_id,
                                    list(selected_answers.keys()),
                                )
                                self._refresh_checklist_state_for_agent(agent_id)
                                self.agent_states[agent_id].restart_pending = self._has_unseen_answer_updates(agent_id)

                                logger.info(
                                    "[Orchestrator] MCP hook: injecting %d peer answer(s) for %s",
                                    len(selected_answers),
                                    agent_id,
                                )

                                _inj_emitter = get_event_emitter()
                                if _inj_emitter:
                                    _inj_emitter.emit_injection_received(
                                        agent_id=agent_id,
                                        source_agents=list(selected_answers.keys()),
                                        injection_type="mid_stream",
                                    )

                                self.coordination_tracker.track_agent_action(
                                    agent_id,
                                    ActionType.UPDATE_INJECTED,
                                    f"Mid-stream (MCP hook): {len(selected_answers)} answer(s)",
                                )

        # Write combined content to hook file
        if injection_parts:
            combined = "\n".join(injection_parts)
            agent.backend.write_post_tool_use_hook(combined)
            if wrote_subagent_payload:
                self._pending_subagent_results.pop(agent_id, None)
            logger.info(
                "[Orchestrator] Wrote %d chars to hook file for %s (%d parts)",
                len(combined),
                agent_id,
                len(injection_parts),
            )

    def _backend_supports_midstream_hook_injection(self, agent: ChatAgent) -> bool:
        """Return whether backend supports orchestrator-managed mid-stream hook delivery."""
        backend = getattr(agent, "backend", None)
        if backend is None:
            return False

        if hasattr(backend, "supports_native_hooks") and backend.supports_native_hooks():
            return True

        # MCP server-level hooks (Codex): injection delivered via file IPC
        if hasattr(backend, "supports_mcp_server_hooks") and backend.supports_mcp_server_hooks():
            return True

        return hasattr(backend, "set_general_hook_manager")

    def _poll_no_hook_background_tool_updates(
        self,
        agent_id: str,
        agent: ChatAgent,
    ) -> bool:
        """Poll and cache completed background tool jobs for hookless delivery."""
        backend = getattr(agent, "backend", None)
        if backend is None or not hasattr(backend, "get_pending_background_tool_results"):
            return False

        try:
            completed_jobs = backend.get_pending_background_tool_results() or []
        except Exception as e:
            logger.error(
                "[Orchestrator] Failed to poll background tool completions for %s: %s",
                agent_id,
                e,
            )
            return False

        if not completed_jobs:
            return False

        self._no_hook_pending_background_tool_results.setdefault(agent_id, []).extend(
            completed_jobs,
        )
        logger.info(
            "[Orchestrator] Cached %s background tool completion(s) for hookless fallback (%s)",
            len(completed_jobs),
            agent_id,
        )
        return True

    async def _collect_no_hook_runtime_fallback_sections(
        self,
        agent_id: str,
    ) -> list[str]:
        """Collect hook-equivalent runtime payloads for hookless backends."""
        from massgen.mcp_tools.hooks import InjectionDeliveryStatus

        sections: list[str] = []

        # 0) Poll runtime inbox for messages from parent (subagent mode)
        self._poll_runtime_inbox()

        # 1) Human runtime input
        has_pending_for_agent = False
        if self._human_input_hook:
            if hasattr(self._human_input_hook, "has_pending_input_for_agent"):
                has_pending_for_agent = self._human_input_hook.has_pending_input_for_agent(agent_id)
            else:
                has_pending_for_agent = self._human_input_hook.has_pending_input()

        if has_pending_for_agent:
            human_result = await self._human_input_hook.execute(
                "no_hook_checkpoint",
                "{}",
                context={"agent_id": agent_id},
            )
            if human_result.inject and human_result.inject.get("content"):
                sections.append(str(human_result.inject["content"]))
                logger.info(
                    "[Orchestrator] Hookless runtime input delivery status=%s (%s)",
                    InjectionDeliveryStatus.DELIVERED.value,
                    agent_id,
                )
                _emitter = get_event_emitter()
                if _emitter:
                    _emitter.emit_injection_received(
                        agent_id=agent_id,
                        source_agents=["human"],
                        injection_type="hookless_human_input",
                    )

        # 2) Background subagent completions
        pending_subagent_results = await self._collect_pending_subagent_results_async(agent_id)
        if pending_subagent_results:
            subagent_hook = SubagentCompleteHook(
                get_pending_results=lambda: list(pending_subagent_results),
                injection_strategy=self._background_subagent_injection_strategy,
            )
            subagent_result = await subagent_hook.execute(
                "no_hook_checkpoint",
                "{}",
                context={"agent_id": agent_id},
            )
            if subagent_result.inject and subagent_result.inject.get("content"):
                # Delivery succeeded — now clear the source.
                self._pending_subagent_results.pop(agent_id, None)
                sections.append(str(subagent_result.inject["content"]))
                logger.info(
                    "[Orchestrator] Hookless subagent completion delivery status=%s (%s)",
                    InjectionDeliveryStatus.DELIVERED.value,
                    agent_id,
                )

        # 3) Background tool completions
        # Peek (copy) instead of pop — only clear after successful delivery.
        background_jobs = list(self._no_hook_pending_background_tool_results.get(agent_id, []))
        agent = self.agents.get(agent_id)
        if agent is not None:
            backend = getattr(agent, "backend", None)
            if backend is not None and hasattr(backend, "get_pending_background_tool_results"):
                try:
                    background_jobs.extend(backend.get_pending_background_tool_results() or [])
                except Exception as e:
                    logger.error(
                        "[Orchestrator] Failed to gather background tool completions for %s: %s",
                        agent_id,
                        e,
                    )

        if background_jobs:
            background_hook = BackgroundToolCompleteHook(
                get_completed_jobs=lambda: background_jobs,
            )
            background_result = await background_hook.execute(
                "no_hook_checkpoint",
                "{}",
                context={"agent_id": agent_id},
            )
            if background_result.inject and background_result.inject.get("content"):
                # Delivery succeeded — now clear the source.
                self._no_hook_pending_background_tool_results.pop(agent_id, None)
                sections.append(str(background_result.inject["content"]))
                logger.info(
                    "[Orchestrator] Hookless background-tool delivery status=%s (%s)",
                    InjectionDeliveryStatus.DELIVERED.value,
                    agent_id,
                )
                _emitter = get_event_emitter()
                if _emitter:
                    _emitter.emit_injection_received(
                        agent_id=agent_id,
                        source_agents=[],
                        injection_type="hookless_bg_tool",
                    )

        return sections

    def _build_runtime_user_instructions_context(self, agent_id: str) -> str | None:
        """Build a compact runtime-input history block for restart-aware prompts."""
        if not self._human_input_hook:
            return None

        getter = getattr(self._human_input_hook, "get_delivered_messages_for_agent", None)
        if not callable(getter):
            return None

        delivered_entries = getter(agent_id) or []
        if not delivered_entries:
            return None

        lines = [
            "<RUNTIME USER INSTRUCTIONS>",
            "The user provided these runtime instructions earlier in this turn.",
            "Continue honoring them unless newer instructions supersede them:",
        ]

        entry_index = 1
        for entry in delivered_entries:
            content = str((entry or {}).get("content", "")).strip()
            if not content:
                continue
            lines.append(f"{entry_index}. {content}")
            entry_index += 1

        if entry_index == 1:
            return None

        lines.append("<END OF RUNTIME USER INSTRUCTIONS>")
        return "\n".join(lines)

    def _insert_runtime_user_instructions_after_original_message(
        self,
        user_message: str,
        runtime_instructions_block: str,
    ) -> str:
        """Insert runtime instructions after the ORIGINAL/PARAPHRASED message section."""
        return self._insert_runtime_context_blocks_after_original_message(
            user_message,
            [runtime_instructions_block],
        )

    def _insert_runtime_context_blocks_after_original_message(
        self,
        user_message: str,
        context_blocks: Sequence[str | None],
    ) -> str:
        """Insert extra runtime context blocks after the ORIGINAL/PARAPHRASED message section."""
        normalized_blocks = [str(block or "").strip() for block in context_blocks if str(block or "").strip()]
        if not normalized_blocks:
            return user_message

        merged_block = "\n\n".join(normalized_blocks)
        current_user_message = user_message or ""
        if not current_user_message:
            return merged_block

        end_paraphrased = "<END OF PARAPHRASED MESSAGE>"
        end_original = "<END OF ORIGINAL MESSAGE>"

        insertion_anchor = None
        if end_paraphrased in current_user_message:
            insertion_anchor = end_paraphrased
        elif end_original in current_user_message:
            insertion_anchor = end_original

        if not insertion_anchor:
            return merged_block + "\n\n" + current_user_message

        anchor_start = current_user_message.find(insertion_anchor)
        if anchor_start < 0:
            return merged_block + "\n\n" + current_user_message

        anchor_end = anchor_start + len(insertion_anchor)
        before = current_user_message[:anchor_end]
        after = current_user_message[anchor_end:].lstrip("\n")

        if after:
            return f"{before}\n\n{merged_block}\n\n{after}"
        return f"{before}\n\n{merged_block}"

    async def _prepare_no_hook_midstream_enforcement(
        self,
        agent_id: str,
        answers: dict[str, str],
    ) -> str | None:
        """Prepare enforcement-style update delivery for backends without hook support.

        This is the no-hook fallback path for mid-stream updates. It mirrors hook-based
        injection behavior, but delivers update content as an enforcement message so
        `reset_chat=False` preserves in-flight chat/session buffers.
        """
        runtime_sections = await self._collect_no_hook_runtime_fallback_sections(agent_id)
        has_runtime_sections = bool(runtime_sections)

        defer_answer_updates = self._should_defer_restart_for_first_answer(agent_id)
        defer_peer_updates_until_restart = False
        selected_answers: dict[str, str] = {}
        had_unseen_updates = False

        if defer_answer_updates:
            # Preserve first-answer protection for peer-answer revisions, while still
            # allowing runtime control/completion payloads to be delivered.
            had_unseen_updates = self._has_unseen_answer_updates(agent_id)
            if had_unseen_updates:
                logger.info(
                    "[Orchestrator] No-hook mid-stream answer updates deferred (first-answer protection) for %s",
                    agent_id,
                )
            elif not has_runtime_sections:
                self.agent_states[agent_id].restart_pending = False
                return None
        elif self._should_defer_peer_updates_until_restart(agent_id):
            defer_peer_updates_until_restart = True
            had_unseen_updates = self._has_unseen_answer_updates(agent_id)
            if had_unseen_updates:
                logger.info(
                    "[Orchestrator] No-hook peer answer updates deferred until restart for %s",
                    agent_id,
                )
            elif not has_runtime_sections:
                self.agent_states[agent_id].restart_pending = False
                return None
        else:
            # Gather latest submitted answers and select unseen updates for this agent.
            current_answers = self._get_current_answers_snapshot()
            selected_answers, had_unseen_updates = self._select_midstream_answer_updates(
                agent_id,
                current_answers,
            )

        if not selected_answers:
            if had_unseen_updates:
                # Keep restart pending so orchestrator can retry delivery/restart.
                self.agent_states[agent_id].restart_pending = True
                if not has_runtime_sections:
                    if defer_peer_updates_until_restart:
                        logger.info(
                            "[Orchestrator] No-hook mid-stream fallback waiting for restart to deliver peer updates for %s",
                            agent_id,
                        )
                    else:
                        cap = getattr(self.config, "max_midstream_injections_per_round", 2)
                        logger.info(
                            "[Orchestrator] No-hook mid-stream fallback deferred for %s: per-round cap reached (%s)",
                            agent_id,
                            cap,
                        )
            else:
                # Stale restart signal: no unseen updates remain.
                self.agent_states[agent_id].restart_pending = False

            if not has_runtime_sections:
                return None

        injection_parts: list[str] = []

        if selected_answers:
            logger.info(
                "[Orchestrator] Delivering no-hook mid-stream peer updates via enforcement message for %s",
                agent_id,
            )

            # Ensure source files referenced in injected updates are accessible.
            await self._copy_all_snapshots_to_temp_workspace(agent_id)

            answer_injection = self._build_tool_result_injection(
                agent_id,
                selected_answers,
                existing_answers=answers,
            )
            injection_parts.append(answer_injection)

            # Track answer-update delivery.
            self.agent_states[agent_id].injection_count += 1
            self.agent_states[agent_id].midstream_injections_this_round += len(selected_answers)

            # Mutate captured `answers` so subsequent checks don't re-send same updates.
            answers.update(selected_answers)

            # Mark the selected source revisions as seen by this agent.
            self.agent_states[agent_id].known_answer_ids.update(selected_answers.keys())
            self._register_injected_answer_updates(agent_id, list(selected_answers.keys()))
            self._mark_pending_checklist_recheck_labels(agent_id, list(selected_answers.keys()))

            _inj_emitter = get_event_emitter()
            if _inj_emitter:
                _inj_emitter.emit_injection_received(
                    agent_id=agent_id,
                    source_agents=list(selected_answers.keys()),
                    injection_type="mid_stream",
                )

            self.coordination_tracker.track_agent_action(
                agent_id,
                ActionType.UPDATE_INJECTED,
                f"Mid-stream (no-hook fallback): {len(selected_answers)} answer(s)",
            )
            self.coordination_tracker.update_agent_context_with_new_answers(
                agent_id,
                list(selected_answers.keys()),
            )
            self._refresh_checklist_state_for_agent(agent_id)

        if runtime_sections:
            injection_parts.extend(runtime_sections)

        if not injection_parts:
            return None

        # Keep pending only if additional unseen revisions still exist.
        self.agent_states[agent_id].restart_pending = self._has_unseen_answer_updates(
            agent_id,
        )

        return "\n".join(injection_parts)

    def _ensure_runtime_human_input_hook_initialized(self) -> None:
        """Initialize and share the runtime human-input hook if needed."""
        if self._human_input_hook is None:
            self._human_input_hook = HumanInputHook()
            self._configure_human_input_hook_callbacks()
            self._share_human_input_hook_with_display()
            return

        self._configure_human_input_hook_callbacks()

    def _ensure_runtime_inbox_poller_initialized(self) -> None:
        """Initialize the runtime inbox poller for subagent mode.

        When running as a subagent, a file-based inbox allows the parent to
        send runtime messages. Messages are polled and fed into the human
        input hook for injection into the agent's context.
        """
        if self._runtime_inbox_poller is not None:
            return

        workspace_path: Path | None = None
        backend_workspace_path: Path | None = None

        for agent in self.agents.values():
            backend = getattr(agent, "backend", None)
            filesystem_manager = getattr(backend, "filesystem_manager", None) if backend else None
            if not filesystem_manager:
                continue

            get_workspace = getattr(filesystem_manager, "get_current_workspace", None)
            if callable(get_workspace):
                resolved = get_workspace()
                if resolved:
                    backend_workspace_path = Path(resolved)
                    break

            cwd = getattr(filesystem_manager, "cwd", None)
            if cwd:
                backend_workspace_path = Path(cwd)
                break

        # Prefer orchestrator workspace root derived from subagent temp workspace.
        # In subagent runs, backend cwd may point to per-agent subfolders
        # (e.g., workspace/agent_1_xxx), while parent-injected runtime inbox
        # messages are written under the orchestrator workspace root
        # (e.g., workspace/.massgen/runtime_inbox).
        if self._agent_temporary_workspace:
            temp_workspace = Path(self._agent_temporary_workspace)
            if temp_workspace.name == "temp" and temp_workspace.parent:
                workspace_path = temp_workspace.parent
            elif temp_workspace.name == "temp_workspaces":
                # This is a global pool directory in top-level runs, not a per-run workspace.
                workspace_path = None
            elif temp_workspace.parent.name == "temp_workspaces":
                # Some runs may provide a per-run path under temp_workspaces.
                workspace_path = temp_workspace

        # Fallback: use agent backend workspace when temp-root metadata is unavailable.
        if workspace_path is None:
            workspace_path = backend_workspace_path

        if workspace_path is None:
            return

        from massgen.mcp_tools.hooks import RuntimeInboxPoller

        inbox_dir = workspace_path / ".massgen" / "runtime_inbox"
        self._runtime_inbox_poller = RuntimeInboxPoller(inbox_dir=inbox_dir)
        logger.info(
            f"[Orchestrator] Initialized runtime inbox poller: {inbox_dir}",
        )

    def _poll_runtime_inbox(self) -> None:
        """Poll runtime inbox and feed messages into human input hook."""
        if not self._runtime_inbox_poller:
            return

        messages = self._runtime_inbox_poller.poll()
        if not messages:
            return

        self._ensure_runtime_human_input_hook_initialized()
        _inj_emitter = get_event_emitter()
        for msg in messages:
            content = msg["content"] if isinstance(msg, dict) else msg
            target_agents = msg.get("target_agents") if isinstance(msg, dict) else None
            source = msg.get("source") if isinstance(msg, dict) else None
            source_label = str(source or "parent")
            logger.info(
                f"[Orchestrator] Injecting runtime inbox message: '{content[:80]}' " f"(target={target_agents}, source={source_label})",
            )
            if self._human_input_hook:
                self._human_input_hook.set_pending_input(
                    content,
                    target_agents=target_agents,
                    source=source_label,
                )
            if _inj_emitter:
                if isinstance(target_agents, list):
                    recipient_agent_ids = [aid for aid in target_agents if isinstance(aid, str) and aid.strip()]
                else:
                    recipient_agent_ids = list(self.agents.keys())
                for recipient_agent_id in dict.fromkeys(recipient_agent_ids):
                    _inj_emitter.emit_injection_received(
                        agent_id=recipient_agent_id,
                        source_agents=[source_label],
                        injection_type="runtime_inbox_input",
                    )

    @staticmethod
    def _try_parse_json_dict_from_text(raw_text: str | None) -> dict[str, Any] | None:
        """Best-effort parse of a JSON object payload from text."""
        if not isinstance(raw_text, str):
            return None
        payload = raw_text.strip()
        if not payload:
            return None
        try:
            parsed = json.loads(payload)
        except Exception:
            try:
                parsed = ast.literal_eval(payload)
            except Exception:
                return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _extract_text_from_mcp_content_payload(content: Any) -> str | None:
        """Extract text blocks from MCP-style content payloads."""
        if content is None:
            return None

        if isinstance(content, str):
            return content

        if isinstance(content, dict):
            if "text" in content:
                return str(content["text"])
            nested = content.get("content")
            return Orchestrator._extract_text_from_mcp_content_payload(nested)

        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    text_parts.append(item)
                    continue
                if hasattr(item, "text"):
                    text_parts.append(str(item.text))
                    continue
                if isinstance(item, dict):
                    if "text" in item:
                        text_parts.append(str(item["text"]))
                        continue
                    nested = Orchestrator._extract_text_from_mcp_content_payload(item)
                    if nested:
                        text_parts.append(nested)
            return "\n".join(part for part in text_parts if part) or None

        return None

    @classmethod
    def _normalize_subagent_mcp_result(cls, raw_result: Any) -> dict[str, Any] | None:
        """Normalize backend/MCP tool call return values to dict payloads."""
        if raw_result is None:
            return None

        # Common backend path: (result_str, result_obj)
        if isinstance(raw_result, tuple) and len(raw_result) >= 2:
            tuple_obj = raw_result[1]
            if isinstance(tuple_obj, dict):
                return tuple_obj
            parsed_from_str = cls._try_parse_json_dict_from_text(
                raw_result[0] if isinstance(raw_result[0], str) else None,
            )
            if parsed_from_str is not None:
                return parsed_from_str
            raw_result = tuple_obj

        if isinstance(raw_result, dict):
            # Some MCP wrappers return {'content': [...]} instead of parsed JSON.
            if "success" not in raw_result and "content" in raw_result:
                content_text = cls._extract_text_from_mcp_content_payload(
                    raw_result.get("content"),
                )
                parsed_content = cls._try_parse_json_dict_from_text(content_text)
                if parsed_content is not None:
                    return parsed_content
            for key in ("structuredContent", "structured_content"):
                structured = raw_result.get(key)
                if isinstance(structured, dict):
                    return structured
            return raw_result

        if isinstance(raw_result, str):
            return cls._try_parse_json_dict_from_text(raw_result)

        # MCP CallToolResult-like object.
        for attr_name in ("structuredContent", "structured_content"):
            structured = getattr(raw_result, attr_name, None)
            if isinstance(structured, dict):
                return structured
        if hasattr(raw_result, "content"):
            content_text = cls._extract_text_from_mcp_content_payload(
                getattr(raw_result, "content", None),
            )
            parsed_content = cls._try_parse_json_dict_from_text(content_text)
            if parsed_content is not None:
                return parsed_content
            is_error = bool(getattr(raw_result, "isError", False))
            if content_text:
                return {"success": not is_error, "output": content_text}
            return {"success": not is_error}

        return None

    async def _call_subagent_mcp_tool_async(
        self,
        parent_agent_id: str,
        tool_name: str,
        params: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Async MCP bridge used by subagent helpers and delegates."""
        agent = self.agents.get(parent_agent_id)
        if not agent:
            return None

        full_tool_name = f"mcp__{self._subagent_server_name(parent_agent_id)}__{tool_name}"
        backend = getattr(agent, "backend", None)
        error_messages: list[str] = []
        attempted_path = False

        # Preferred path for OpenAI-compatible/Claude/Gemini/Grok style backends.
        mcp_executor = getattr(backend, "_execute_mcp_function_with_retry", None)
        if callable(mcp_executor):
            attempted_path = True
            try:
                raw_result = await mcp_executor(full_tool_name, json.dumps(params))
                normalized = self._normalize_subagent_mcp_result(raw_result)
                if normalized is not None:
                    return normalized
                error_messages.append(
                    f"Unparseable MCP result from executor for {full_tool_name}",
                )
            except Exception as exc:
                logger.debug(
                    "[Orchestrator] Backend MCP executor call failed for %s (%s): %s",
                    full_tool_name,
                    parent_agent_id,
                    exc,
                )
                error_messages.append(str(exc))

        # Claude Code backend path uses a lazily initialized background MCP client.
        background_client_getter = getattr(backend, "_get_background_mcp_client", None)
        if callable(background_client_getter):
            attempted_path = True
            try:
                client = await background_client_getter()
                if not client:
                    init_error = str(getattr(backend, "_background_mcp_init_error", "") or "").strip()
                    error_messages.append(
                        init_error or f"Background MCP client unavailable for {full_tool_name}",
                    )
                    raw_result = None
                else:
                    raw_result = None
                    background_error: Exception | None = None
                    retry_error: Exception | None = None
                    retry_attempted = False

                    try:
                        raw_result = await client.call_tool(
                            tool_name=full_tool_name,
                            arguments=params,
                        )
                    except Exception as exc:
                        background_error = exc
                        reconnect = getattr(client, "reconnect", None)
                        should_retry = callable(reconnect) and self._is_reconnectable_background_mcp_error(exc)
                        if should_retry:
                            retry_attempted = True
                            logger.info(
                                "[Orchestrator] Retrying %s for %s after background MCP reconnect",
                                full_tool_name,
                                parent_agent_id,
                            )
                            try:
                                reconnect_result = reconnect(max_retries=1)
                                if inspect.isawaitable(reconnect_result):
                                    reconnect_result = await reconnect_result
                                if reconnect_result:
                                    raw_result = await client.call_tool(
                                        tool_name=full_tool_name,
                                        arguments=params,
                                    )
                                    background_error = None
                                else:
                                    retry_error = RuntimeError(
                                        "Background MCP reconnect returned False",
                                    )
                            except Exception as reconnect_exc:
                                retry_error = reconnect_exc

                    if background_error is not None and raw_result is None:
                        logger.debug(
                            "[Orchestrator] Background MCP client call failed for %s (%s): %s",
                            full_tool_name,
                            parent_agent_id,
                            background_error,
                        )
                        error_messages.append(str(background_error))
                        if retry_attempted and retry_error is not None:
                            error_messages.append(
                                f"Reconnect retry failed for {full_tool_name}: {retry_error}",
                            )
                normalized = self._normalize_subagent_mcp_result(raw_result)
                if normalized is not None:
                    return normalized
                if raw_result is not None:
                    error_messages.append(
                        f"Unparseable MCP result from background client for {full_tool_name}",
                    )
            except Exception as exc:
                logger.debug(
                    "[Orchestrator] Background MCP client call failed for %s (%s): %s",
                    full_tool_name,
                    parent_agent_id,
                    exc,
                )
                error_messages.append(str(exc))

        # Legacy/fallback path used by tests and older adapters.
        mcp_client = getattr(agent, "mcp_client", None)
        if mcp_client and hasattr(mcp_client, "call_tool"):
            attempted_path = True
            try:
                call_result = mcp_client.call_tool(full_tool_name, params)
                if inspect.isawaitable(call_result):
                    call_result = await call_result
                normalized = self._normalize_subagent_mcp_result(call_result)
                if normalized is not None:
                    return normalized
                error_messages.append(
                    f"Unparseable MCP result from legacy client for {full_tool_name}",
                )
            except Exception as exc:
                logger.debug(
                    "[Orchestrator] Legacy MCP client call failed for %s (%s): %s",
                    full_tool_name,
                    parent_agent_id,
                    exc,
                )
                error_messages.append(str(exc))

        if error_messages:
            deduped_messages = list(dict.fromkeys(msg for msg in error_messages if msg))
            return {
                "success": False,
                "operation": tool_name,
                "error": "; ".join(deduped_messages),
            }
        if attempted_path:
            return {
                "success": False,
                "operation": tool_name,
                "error": f"No usable MCP result returned for {full_tool_name}",
            }
        return {
            "success": False,
            "operation": tool_name,
            "error": f"No programmatic MCP client available for {full_tool_name}",
        }

    @staticmethod
    def _is_reconnectable_background_mcp_error(error: Exception | str) -> bool:
        """Return whether a background MCP failure is likely recoverable via reconnect."""
        normalized = str(error or "").strip().lower()
        if not normalized:
            return False
        reconnect_markers = (
            "not connected",
            "disconnected",
            "connection closed",
            "connection lost",
            "broken pipe",
        )
        return any(marker in normalized for marker in reconnect_markers)

    def _call_subagent_mcp_tool(
        self,
        parent_agent_id: str,
        tool_name: str,
        params: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Sync wrapper for compatibility with legacy sync call sites."""
        from .utils import run_async_safely

        return run_async_safely(
            self._call_subagent_mcp_tool_async(parent_agent_id, tool_name, params),
        )

    def _has_subagent_mcp_for_agent(self, agent_id: str) -> bool:
        """Return True if *agent_id* has a connected subagent MCP server.

        The subagent MCP server is only injected when the agent has a valid
        ``filesystem_manager`` (see ``_inject_subagent_tools_for_agent``).
        Agents without one (e.g. codex backend with no explicit ``cwd``)
        need the direct spawn fallback.
        """
        agent = self.agents.get(agent_id)
        if not agent:
            return False
        fs_mgr = getattr(getattr(agent, "backend", None), "filesystem_manager", None)
        return fs_mgr is not None

    async def _direct_spawn_subagents(
        self,
        parent_agent_id: str,
        tasks: list[dict[str, Any]],
        refine: bool = True,
    ) -> dict[str, Any]:
        """Spawn subagents using the MCP server's logic directly.

        Configures the MCP module globals and calls ``spawn_subagents_direct``
        so that context-path normalization, temp-workspace auto-mounting, and
        specialized-type resolution all use the **same code path** as
        MCP-routed spawns — no duplicated logic.

        Uses the parent agent's existing workspace when available, matching
        the normal MCP-based subagent spawning path.  Falls back to creating
        a workspace under ``.massgen/workspaces/`` (same location the CLI
        uses for agent workspaces) when the parent has no filesystem_manager.
        """
        import uuid as _uuid

        from .mcp_tools.subagent import _subagent_mcp_server as mcp_mod

        # --- Resolve workspace root ---
        # Prefer the parent agent's existing workspace (same as the MCP path).
        # Fall back to .massgen/workspaces/ when no filesystem_manager exists.
        agent = self.agents.get(parent_agent_id)
        fs_mgr = getattr(getattr(agent, "backend", None), "filesystem_manager", None)
        if fs_mgr and fs_mgr.cwd:
            ws_root = Path(fs_mgr.cwd).resolve()
        else:
            spawn_id = _uuid.uuid4().hex[:8]
            ws_root = (Path(".massgen") / "workspaces" / f"direct_spawn_{parent_agent_id}_{spawn_id}").resolve()
            ws_root.mkdir(parents=True, exist_ok=True)

        # Write subagent type dirs and CONTEXT.md so the MCP module can
        # resolve specialized types from the workspace.
        self._write_subagent_type_dirs(ws_root)
        self._ensure_context_md_for_round_evaluator(ws_root, parent_agent_id)

        # --- Build parent agent configs ---
        agent_configs: list[dict[str, Any]] = []
        for aid, a in self.agents.items():
            agent_cfg: dict[str, Any] = {"id": aid}
            if hasattr(a.backend, "config"):
                backend_cfg = {k: v for k, v in a.backend.config.items() if k not in ("mcp_servers", "_config_path")}
                # The 'type' key is consumed by create_backend() and not
                # stored in self.config.  Inject it so subagent configs
                # inherit the correct backend type.
                if "type" not in backend_cfg and hasattr(a.backend, "get_provider_name"):
                    from .backend.capabilities import normalize_backend_type

                    backend_cfg["type"] = normalize_backend_type(a.backend.get_provider_name())
                agent_cfg["backend"] = backend_cfg
            agent_configs.append(agent_cfg)

        # --- Subagent orchestrator config ---
        coord_cfg = getattr(self.config, "coordination_config", None)
        sub_orch_config = getattr(coord_cfg, "subagent_orchestrator", None)
        if isinstance(sub_orch_config, dict):
            from .subagent.models import SubagentOrchestratorConfig as _SOC

            sub_orch_config = _SOC(**sub_orch_config)

        # --- Log directory ---
        # Use the active log session dir so SubagentManager writes to
        # log_session_dir/subagents/<id>/ where the TUI can find them.
        log_dir: str | None = None
        try:
            from massgen.logger_config import get_log_session_dir

            _log_session = get_log_session_dir()
            if _log_session:
                log_dir = str(_log_session)
        except Exception:
            pass
        if not log_dir:
            if hasattr(self, "_log_dir") and self._log_dir:
                log_dir = str(self._log_dir)
            elif hasattr(self, "log_directory") and self.log_directory:
                log_dir = str(self.log_directory)

        # --- Parent context paths (allowed roots for path validation) ---
        parent_context_paths: list[dict[str, str]] = []
        agent = self.agents.get(parent_agent_id)
        if agent and hasattr(agent.backend, "config"):
            raw_ctx = agent.backend.config.get("context_paths", [])
            if isinstance(raw_ctx, list):
                for entry in raw_ctx:
                    if isinstance(entry, str):
                        parent_context_paths.append(
                            {"path": entry, "permission": "read"},
                        )
                    elif isinstance(entry, dict) and "path" in entry:
                        parent_context_paths.append(entry)

        # Resolve temp workspace to absolute; only include if it exists.
        orch_temp = getattr(self, "_agent_temporary_workspace", None)
        orch_temp_resolved: str | None = None
        if orch_temp:
            _resolved = Path(orch_temp).resolve()
            if _resolved.exists():
                orch_temp_resolved = str(_resolved)
                parent_context_paths.append(
                    {"path": orch_temp_resolved, "permission": "read"},
                )

        # --- Timeout from config ---
        configured_timeout = getattr(coord_cfg, "subagent_default_timeout", 600) if coord_cfg else 600

        # --- Configure MCP module globals and spawn ---
        # Acquire lock to prevent concurrent direct spawns from corrupting
        # the shared module-level globals (configure → spawn → reset).
        lock = mcp_mod._get_direct_spawn_lock()
        async with lock:
            saved = mcp_mod.configure_direct_spawn(
                workspace_path=ws_root,
                parent_agent_id=parent_agent_id,
                orchestrator_id=getattr(self, "orchestrator_id", "unknown"),
                parent_agent_configs=agent_configs,
                subagent_orchestrator_config=sub_orch_config,
                log_directory=log_dir,
                agent_temporary_workspace=orch_temp_resolved,
                parent_context_paths=parent_context_paths,
                parent_coordination_config=(coord_cfg.__dict__ if coord_cfg and hasattr(coord_cfg, "__dict__") else None),
                default_timeout=configured_timeout,
                max_timeout=int(configured_timeout * 1.5),
            )
            try:
                return await mcp_mod.spawn_subagents_direct(
                    tasks=tasks,
                    refine=refine,
                    timeout_override=configured_timeout,
                )
            finally:
                mcp_mod.reset_direct_spawn(saved)

    def _send_runtime_message_via_direct_inbox_write(
        self,
        parent_agent_id: str,
        subagent_id: str,
        content: str,
        target_agents: list[str] | None = None,
    ) -> bool:
        """Fallback: write runtime message directly to subagent workspace inbox.

        This bypasses MCP request/response delivery and is useful when the
        subagent MCP server is busy handling a blocking spawn call.
        """
        parent_workspace = self._resolve_subagent_parent_workspace(parent_agent_id)
        if parent_workspace is None or not parent_workspace.exists():
            return False

        subagent_workspace = parent_workspace / "subagents" / subagent_id / "workspace"
        if not subagent_workspace.exists() or not subagent_workspace.is_dir():
            return False

        inbox_dir = subagent_workspace / ".massgen" / "runtime_inbox"
        inbox_dir.mkdir(parents=True, exist_ok=True)

        msg_data = {
            "content": content,
            "source": "parent",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "target_agents": target_agents,
        }
        file_stem = f"msg_{int(time.time())}_{secrets.token_hex(4)}"
        tmp_path = inbox_dir / f"{file_stem}.json.tmp"
        final_path = inbox_dir / f"{file_stem}.json"
        tmp_path.write_text(json.dumps(msg_data, indent=2))
        tmp_path.rename(final_path)

        logger.info(
            f"[Orchestrator] Runtime message delivered via direct inbox fallback for subagent {subagent_id} " f"(parent={parent_agent_id}, target={target_agents})",
        )
        return True

    def _resolve_subagent_parent_workspace(self, parent_agent_id: str) -> Path | None:
        """Resolve parent workspace root for subagent workspace operations."""
        agent = self.agents.get(parent_agent_id)
        backend = getattr(agent, "backend", None) if agent else None
        filesystem_manager = getattr(backend, "filesystem_manager", None) if backend else None

        backend_workspace_path: Path | None = None
        get_workspace = getattr(filesystem_manager, "get_current_workspace", None) if filesystem_manager else None
        if callable(get_workspace):
            try:
                resolved = get_workspace()
                if resolved:
                    backend_workspace_path = Path(resolved)
            except Exception:
                backend_workspace_path = None

        if backend_workspace_path is None and filesystem_manager is not None:
            cwd = getattr(filesystem_manager, "cwd", None)
            if cwd:
                backend_workspace_path = Path(cwd)

        workspace_path: Path | None = None
        if self._agent_temporary_workspace:
            temp_workspace = Path(self._agent_temporary_workspace)
            if temp_workspace.name == "temp" and temp_workspace.parent:
                workspace_path = temp_workspace.parent
            elif temp_workspace.name == "temp_workspaces":
                workspace_path = None
            elif temp_workspace.parent.name == "temp_workspaces":
                workspace_path = temp_workspace

        if workspace_path is None:
            workspace_path = backend_workspace_path

        if workspace_path is None:
            return None

        # Some backends expose per-agent subdirectories (workspace/agent_1_...).
        # Subagent workspaces are rooted one level up at workspace/subagents/.
        if not (workspace_path / "subagents").exists():
            parent_candidate = workspace_path.parent
            if (parent_candidate / "subagents").exists():
                workspace_path = parent_candidate

        return workspace_path

    def send_runtime_message_to_subagent(
        self,
        subagent_id: str,
        content: str,
        target_agents: list[str] | None = None,
    ) -> bool:
        """Route a runtime message to a running subagent via MCP tool call."""
        params: dict[str, Any] = {
            "subagent_id": subagent_id,
            "message": content,
        }
        if target_agents is not None:
            params["target_agents"] = target_agents

        for parent_agent_id in self.agents:
            result = self._call_subagent_mcp_tool(
                parent_agent_id=parent_agent_id,
                tool_name="send_message_to_subagent",
                params=params,
            )
            if isinstance(result, dict) and result.get("success"):
                logger.info(
                    f"[Orchestrator] Runtime message delivered to subagent {subagent_id} via {parent_agent_id} " f"(target={target_agents})",
                )
                return True
            if self._send_runtime_message_via_direct_inbox_write(
                parent_agent_id=parent_agent_id,
                subagent_id=subagent_id,
                content=content,
                target_agents=target_agents,
            ):
                return True
            logger.debug(
                f"[Orchestrator] Runtime message delivery attempt via {parent_agent_id} " f"failed for subagent {subagent_id} (result={result})",
            )
        logger.warning(
            f"[Orchestrator] Failed to deliver runtime message to subagent {subagent_id} " f"after trying {len(self.agents)} parent agent route(s)",
        )
        return False

    def continue_subagent_from_tui(
        self,
        subagent_id: str,
        message: str,
        timeout_seconds: int | None = None,
        background: bool = True,
    ) -> bool:
        """Continue a terminal subagent from TUI runtime controls."""
        params: dict[str, Any] = {
            "subagent_id": subagent_id,
            "message": message,
            "background": bool(background),
        }
        if timeout_seconds is not None:
            params["timeout_seconds"] = timeout_seconds

        for parent_agent_id in self.agents:
            result = self._call_subagent_mcp_tool(
                parent_agent_id=parent_agent_id,
                tool_name="continue_subagent",
                params=params,
            )
            if isinstance(result, dict) and result.get("success"):
                if background:
                    self._injected_subagents.setdefault(parent_agent_id, set()).discard(subagent_id)

                    display = None
                    if hasattr(self, "coordination_ui") and self.coordination_ui:
                        display = getattr(self.coordination_ui, "display", None)

                    continued_subagent_id = subagent_id
                    subagents_payload = result.get("subagents")
                    if isinstance(subagents_payload, list) and subagents_payload:
                        first = subagents_payload[0]
                        if isinstance(first, dict):
                            continued_subagent_id = str(first.get("subagent_id") or subagent_id)

                    if display and hasattr(display, "notify_runtime_subagent_started"):
                        try:
                            task_preview = message.strip() or f"Continue {continued_subagent_id}"
                            if len(task_preview) > 300:
                                task_preview = task_preview[:297] + "..."
                            timeout_for_display = int(
                                timeout_seconds or self.config.coordination_config.subagent_default_timeout or 300,
                            )
                            call_id = f"continue_{continued_subagent_id}_{int(time.time() * 1000)}"
                            display.notify_runtime_subagent_started(
                                agent_id=parent_agent_id,
                                subagent_id=continued_subagent_id,
                                task=task_preview,
                                timeout_seconds=timeout_for_display,
                                call_id=call_id,
                                status_callback=self._build_tui_continue_status_callback(
                                    parent_agent_id=parent_agent_id,
                                    fallback_task=task_preview,
                                    fallback_timeout_seconds=timeout_for_display,
                                ),
                                log_path=None,
                            )
                        except Exception:
                            logger.opt(exception=True).warning(
                                f"[Orchestrator] Failed to notify TUI of continued subagent " f"{subagent_id} for parent {parent_agent_id}",
                            )

                logger.info(
                    f"[Orchestrator] Continue request dispatched for subagent {subagent_id} via {parent_agent_id}",
                )
                return True
            logger.debug(
                "[Orchestrator] Continue subagent attempt via %s failed for %s (result=%s)",
                parent_agent_id,
                subagent_id,
                result,
            )

        logger.warning(
            f"[Orchestrator] Failed to continue subagent {subagent_id} after trying {len(self.agents)} parent agent route(s)",
        )
        return False

    def _build_tui_continue_status_callback(
        self,
        parent_agent_id: str,
        fallback_task: str,
        fallback_timeout_seconds: int | None,
    ):
        """Build status callback for TUI-initiated continue-subagent cards."""
        from .subagent.models import SubagentDisplayData

        def _map_status(raw_status: Any) -> tuple[str, int]:
            normalized = str(raw_status or "").lower().strip()
            if normalized == "completed":
                return "completed", 100
            if normalized in {"completed_but_timeout", "partial", "timeout"}:
                return "timeout", 100
            if normalized in {"failed", "error"}:
                return "failed", 0
            if normalized in {"cancelled", "canceled", "stopped"}:
                return "canceled", 0
            if normalized == "pending":
                return "pending", 0
            return "running", 0

        def _callback(subagent_id: str) -> SubagentDisplayData | None:
            payload = self._call_subagent_mcp_tool(
                parent_agent_id=parent_agent_id,
                tool_name="list_subagents",
                params={},
            )
            if not isinstance(payload, dict) or not payload.get("success"):
                return None

            subagents = payload.get("subagents")
            if not isinstance(subagents, list):
                return None

            matched_entry = None
            for entry in subagents:
                if not isinstance(entry, dict):
                    continue
                candidate_id = str(entry.get("subagent_id") or entry.get("id") or "").strip()
                if candidate_id == subagent_id:
                    matched_entry = entry
                    break

            if not isinstance(matched_entry, dict):
                return None

            result_payload = matched_entry.get("result")
            if not isinstance(result_payload, dict):
                result_payload = {}

            status_source = matched_entry.get("status", result_payload.get("status"))
            display_status, progress = _map_status(status_source)

            answer = result_payload.get("answer")
            answer_preview = None
            if isinstance(answer, str) and answer:
                answer_preview = answer[:200]

            error = result_payload.get("error")
            if not error:
                error = matched_entry.get("error")

            execution_time = result_payload.get("execution_time_seconds")
            if execution_time is None:
                execution_time = matched_entry.get("execution_time_seconds", 0.0)
            try:
                elapsed_seconds = float(execution_time or 0.0)
            except Exception:
                elapsed_seconds = 0.0

            timeout_seconds = matched_entry.get("timeout_seconds", fallback_timeout_seconds)
            try:
                timeout_value = float(timeout_seconds or fallback_timeout_seconds or 300)
            except Exception:
                timeout_value = float(fallback_timeout_seconds or 300)

            workspace = str(
                result_payload.get("workspace") or matched_entry.get("workspace") or "",
            )

            task = str(matched_entry.get("task") or fallback_task or "")

            return SubagentDisplayData(
                id=subagent_id,
                task=task,
                status=display_status,
                progress_percent=progress,
                elapsed_seconds=elapsed_seconds,
                timeout_seconds=timeout_value,
                workspace_path=workspace,
                workspace_file_count=0,
                last_log_line=str(error or ""),
                error=str(error) if isinstance(error, str) and error else None,
                answer_preview=answer_preview,
                log_path=result_payload.get("log_path"),
                context_paths=[],
                subagent_type=None,
            )

        return _callback

    def _configure_human_input_hook_callbacks(self) -> None:
        """Configure queue callbacks for runtime-input-aware wait interruption."""
        if not self._human_input_hook:
            return

        def _on_human_input_queued(
            _content: str,
            target_agents: list[str] | None = None,
            _message_id: int | None = None,
        ) -> None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # No active loop (e.g., teardown path) - nothing to schedule.
                return

            if target_agents:
                candidate_agent_ids = [aid for aid in target_agents if isinstance(aid, str) and aid in self.agents]
            else:
                candidate_agent_ids = list(self.agents.keys())

            for candidate_agent_id in candidate_agent_ids:
                loop.create_task(
                    self._maybe_interrupt_background_wait_for_agent(
                        candidate_agent_id,
                        trigger="queued_human_input",
                    ),
                )

        self._human_input_hook.set_queue_callback(_on_human_input_queued)
        self._human_input_hook.set_pre_execute_callback(self._poll_runtime_inbox)

    async def _maybe_interrupt_background_wait_for_agent(
        self,
        agent_id: str,
        trigger: str = "runtime_injection_available",
    ) -> bool:
        """Interrupt an actively waiting external background tool call, when possible."""
        agent = self.agents.get(agent_id)
        if agent is None:
            return False

        backend = getattr(agent, "backend", None)
        if backend is None:
            return False

        is_wait_active = getattr(backend, "is_background_wait_active", None)
        notify_interrupt = getattr(backend, "notify_background_wait_interrupt", None)
        if not callable(is_wait_active) or not callable(notify_interrupt):
            return False

        try:
            if not bool(is_wait_active()):
                return False
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "[Orchestrator] Failed checking background wait state for %s: %s",
                agent_id,
                e,
            )
            return False

        runtime_sections = await self._collect_no_hook_runtime_fallback_sections(agent_id)
        if not runtime_sections:
            return False

        payload = {
            "interrupt_reason": "runtime_injection_available",
            "injected_content": "\n".join(runtime_sections),
            "trigger": trigger,
            "agent_id": agent_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            signaled = bool(notify_interrupt(payload))
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "[Orchestrator] Failed sending background wait interrupt to %s: %s",
                agent_id,
                e,
                exc_info=True,
            )
            return False

        if signaled:
            logger.info(
                "[Orchestrator] Background wait interrupted for %s via %s",
                agent_id,
                trigger,
            )
        return signaled

    def _share_human_input_hook_with_display(self) -> None:
        """Share the human input hook reference with the TUI display.

        This allows the TUI to queue user input for injection during execution.
        Called once when the human input hook is first created.
        """
        if not self._human_input_hook:
            return

        # Get display from coordination_ui if available
        display = None
        if hasattr(self, "coordination_ui") and self.coordination_ui:
            display = getattr(self.coordination_ui, "display", None)

        if not display:
            logger.debug("[Orchestrator] No display available for human input hook sharing")
            return

        # Check if display supports human input hook
        if hasattr(display, "set_human_input_hook"):
            display.set_human_input_hook(self._human_input_hook)
            logger.info("[Orchestrator] Shared human input hook with TUI display")
        else:
            logger.debug("[Orchestrator] Display does not support human input hook")

    def _share_subagent_message_callback_with_display(self) -> None:
        """Share the subagent message callback with the TUI display.

        Called from setup_subagent_spawn_callbacks() when coordination_ui is available.
        """
        display = None
        if hasattr(self, "coordination_ui") and self.coordination_ui:
            display = getattr(self.coordination_ui, "display", None)
        if display and hasattr(display, "set_subagent_message_callback"):
            display.set_subagent_message_callback(self.send_runtime_message_to_subagent)
            logger.info("[Orchestrator] Shared subagent message callback with TUI display")
        if display and hasattr(display, "set_subagent_continue_callback"):
            display.set_subagent_continue_callback(self.continue_subagent_from_tui)
            logger.info("[Orchestrator] Shared subagent continue callback with TUI display")

    def _register_round_timeout_hooks(
        self,
        agent_id: str,
        manager: GeneralHookManager,
    ) -> None:
        """Register per-round timeout hooks if configured.

        This creates two hooks:
        1. RoundTimeoutPostHook (soft timeout) - Injects warning message after tool calls
        2. RoundTimeoutPreHook (hard timeout) - Blocks non-terminal tools after grace period

        The hooks are stored in agent_states so they can be reset when a new round starts.

        Args:
            agent_id: The agent identifier
            manager: The GeneralHookManager to register hooks with
        """
        # Get timeout config
        timeout_config = self.config.timeout_config
        initial_timeout = timeout_config.initial_round_timeout_seconds
        subsequent_timeout = timeout_config.subsequent_round_timeout_seconds
        grace_seconds = timeout_config.round_timeout_grace_seconds

        # Skip if no round timeouts configured
        if initial_timeout is None and subsequent_timeout is None:
            return

        logger.info(
            f"[Orchestrator] Registering round timeout hooks for {agent_id}: " f"initial={initial_timeout}s, subsequent={subsequent_timeout}s, grace={grace_seconds}s",
        )

        # Create closures that read from agent state
        def get_round_start_time() -> float:
            """Get the current round start time from agent state."""
            start_time = self.agent_states[agent_id].round_start_time
            if start_time is None:
                # Fallback to current time if not set (shouldn't happen)
                logger.warning(
                    f"[Orchestrator] round_start_time is None for {agent_id}, using current time as fallback",
                )
                return time.time()
            return start_time

        def get_agent_round() -> int:
            """Get the current round number from coordination tracker."""
            return self.coordination_tracker.get_agent_round(agent_id)

        # Create shared state for coordinating soft -> hard timeout progression
        # This ensures hard timeout only fires AFTER soft timeout has been injected
        timeout_state = RoundTimeoutState()

        # Get two-tier workspace setting from coordination config
        # Suppressed when write_mode is active (write_mode replaces the old two-tier structure)
        coordination_config = getattr(self.config, "coordination_config", None)
        write_mode = getattr(coordination_config, "write_mode", None) if coordination_config else None
        use_two_tier_workspace = False
        if not (write_mode and write_mode != "legacy"):
            use_two_tier_workspace = bool(
                getattr(coordination_config, "use_two_tier_workspace", False),
            )

        # Create soft timeout hook (POST_TOOL_USE - injects warning)
        post_hook = RoundTimeoutPostHook(
            name=f"round_timeout_soft_{agent_id}",
            get_round_start_time=get_round_start_time,
            get_agent_round=get_agent_round,
            initial_timeout_seconds=initial_timeout,
            subsequent_timeout_seconds=subsequent_timeout,
            grace_seconds=grace_seconds,
            agent_id=agent_id,
            shared_state=timeout_state,
            use_two_tier_workspace=use_two_tier_workspace,
        )

        # Create hard timeout hook (PRE_TOOL_USE - blocks non-terminal tools)
        pre_hook = RoundTimeoutPreHook(
            name=f"round_timeout_hard_{agent_id}",
            get_round_start_time=get_round_start_time,
            get_agent_round=get_agent_round,
            initial_timeout_seconds=initial_timeout,
            subsequent_timeout_seconds=subsequent_timeout,
            grace_seconds=grace_seconds,
            agent_id=agent_id,
            shared_state=timeout_state,
        )

        # Register hooks
        manager.register_global_hook(HookType.POST_TOOL_USE, post_hook)
        manager.register_global_hook(HookType.PRE_TOOL_USE, pre_hook)

        # Store hook references so we can reset them on new rounds
        self.agent_states[agent_id].round_timeout_hooks = (post_hook, pre_hook)
        # Store the shared state so we can check force_terminate in the orchestrator loop
        self.agent_states[agent_id].round_timeout_state = timeout_state

        logger.debug(f"[Orchestrator] Registered round timeout hooks for {agent_id}")

    def _setup_native_hooks_for_agent(
        self,
        agent_id: str,
        agent: ChatAgent,
        answers: dict[str, str],
    ) -> None:
        """Set up native hooks for backends that support them (e.g., Claude Code).

        This converts MassGen hooks to the backend's native format using the
        NativeHookAdapter interface. The hooks are then executed natively by
        the backend rather than through MassGen's GeneralHookManager.

        Args:
            agent_id: The agent identifier
            agent: The ChatAgent instance
            answers: Dict of existing answers when agent started (used to detect new answers)
        """
        # Get the native hook adapter from the backend
        adapter = agent.backend.get_native_hook_adapter()
        if not adapter:
            logger.warning(
                f"[Orchestrator] Backend supports native hooks but adapter unavailable for {agent_id}",
            )
            return

        # Create a GeneralHookManager to hold MassGen hooks
        # (We'll convert these to native format)
        manager = GeneralHookManager()

        # Create mid-stream injection hook with closure-based callback
        mid_stream_hook = MidStreamInjectionHook()

        # Define the injection callback (same logic as GeneralHookManager path)
        async def get_injection_content() -> str | None:
            """Check if mid-stream injection is needed and return content."""
            if self.config.disable_injection:
                return None

            if not self._check_restart_pending(agent_id):
                return None

            # First-answer protection: don't inject into an agent that hasn't
            # produced its first answer yet.
            if self._should_defer_restart_for_first_answer(agent_id):
                self.agent_states[agent_id].restart_pending = False
                return None

            # In vote-only mode, skip injection and force a full restart instead.
            if self._is_vote_only_mode(agent_id):
                return None

            if self._should_defer_peer_updates_until_restart(agent_id):
                if self._has_unseen_answer_updates(agent_id):
                    self.agent_states[agent_id].restart_pending = True
                    logger.info(
                        "[Orchestrator] Deferring native peer answer update injection until restart for %s",
                        agent_id,
                    )
                else:
                    self.agent_states[agent_id].restart_pending = False
                return None

            # Get CURRENT answers (includes virtual agents in step mode)
            current_answers = self._get_current_answers_snapshot()
            selected_answers, had_unseen_updates = self._select_midstream_answer_updates(
                agent_id,
                current_answers,
            )

            if not selected_answers:
                if had_unseen_updates:
                    self.agent_states[agent_id].restart_pending = True
                    cap = getattr(self.config, "max_midstream_injections_per_round", 2)
                    logger.info(
                        "[Orchestrator] Skipping native mid-stream injection for %s: per-round cap reached (%s)",
                        agent_id,
                        cap,
                    )
                else:
                    self.agent_states[agent_id].restart_pending = False
                return None

            # TIMING CONSTRAINT: Skip injection if too close to soft timeout
            if self._should_skip_injection_due_to_timeout(agent_id):
                return None  # Let restart happen instead

            # Copy snapshots from new answer agents to temp workspace
            logger.info(
                f"[Orchestrator] Copying snapshots for mid-stream injection to {agent_id}",
            )
            await self._copy_all_snapshots_to_temp_workspace(agent_id)

            # Build injection content
            injection = self._build_tool_result_injection(
                agent_id,
                selected_answers,
                existing_answers=answers,
            )

            # Increment injection count
            self.agent_states[agent_id].injection_count += 1
            self.agent_states[agent_id].midstream_injections_this_round += len(selected_answers)

            # Update answers to include newly injected answers (prevents re-injection)
            # This mutates the captured closure variable so future callbacks see updated state
            answers.update(selected_answers)

            # Update known_answer_ids so vote validation knows this agent has seen these
            self.agent_states[agent_id].known_answer_ids.update(selected_answers.keys())
            self._register_injected_answer_updates(agent_id, list(selected_answers.keys()))
            self._mark_pending_checklist_recheck_labels(agent_id, list(selected_answers.keys()))

            # Update context labels BEFORE refreshing checklist state so
            # available_agent_labels reflects the newly-injected labels
            # (e.g. agent1.2 replacing agent1.1). Same ordering as all other paths.
            self.coordination_tracker.update_agent_context_with_new_answers(
                agent_id,
                list(selected_answers.keys()),
            )

            # Refresh checklist tool state after injection (streak may have reset)
            self._refresh_checklist_state_for_agent(agent_id)

            # Keep restart pending if additional unseen revisions still remain.
            self.agent_states[agent_id].restart_pending = self._has_unseen_answer_updates(agent_id)

            # Emit injection_received event for TUI

            _inj_emitter = get_event_emitter()
            if _inj_emitter:
                _inj_emitter.emit_injection_received(
                    agent_id=agent_id,
                    source_agents=list(selected_answers.keys()),
                    injection_type="mid_stream",
                )

            # Track the injection
            logger.info(
                f"[Orchestrator] Mid-stream injection (native) for {agent_id}: {len(selected_answers)} answer update(s)",
            )
            self.coordination_tracker.track_agent_action(
                agent_id,
                ActionType.UPDATE_INJECTED,
                f"Mid-stream (native): {len(selected_answers)} answer(s)",
            )

            return injection

        # Set callback on hook
        mid_stream_hook.set_callback(get_injection_content)

        # Register mid-stream injection hook
        manager.register_global_hook(HookType.POST_TOOL_USE, mid_stream_hook)

        # Register high-priority task reminder hook (enabled round-wise when capture is enabled)
        if self._is_round_learning_capture_enabled():
            reminder_hook = HighPriorityTaskReminderHook()
            manager.register_global_hook(HookType.POST_TOOL_USE, reminder_hook)

        # Register media call ledger hook (read_media/generate_media provenance capture)
        manager.register_global_hook(HookType.POST_TOOL_USE, MediaCallLedgerHook())

        # Register human input hook (shared across all agents)
        self._ensure_runtime_human_input_hook_initialized()
        manager.register_global_hook(HookType.POST_TOOL_USE, self._human_input_hook)

        # Register subagent completion hook for background result injection
        if self._background_subagents_enabled:
            subagent_hook = SubagentCompleteHook(
                injection_strategy=self._background_subagent_injection_strategy,
            )

            # Create a closure that captures agent_id for pending results retrieval
            def make_pending_getter(aid: str):
                return lambda: self._get_pending_subagent_results_async(aid)

            subagent_hook.set_pending_results_getter(make_pending_getter(agent_id))
            manager.register_global_hook(HookType.POST_TOOL_USE, subagent_hook)
            logger.debug(f"[Orchestrator] Registered SubagentCompleteHook (native) for {agent_id}")

            # Wire background tool delegate so list/status/result/cancel route to subagents
            if hasattr(agent.backend, "register_background_delegate"):
                from massgen.subagent.background_delegate import (
                    SubagentBackgroundDelegate,
                )

                def _make_call_tool(aid: str):
                    return lambda tool_name, params: self._call_subagent_mcp_tool_async(
                        aid,
                        tool_name,
                        params,
                    )

                delegate = SubagentBackgroundDelegate(
                    call_tool=_make_call_tool(agent_id),
                    agent_id=agent_id,
                )
                agent.backend.register_background_delegate(delegate)
                logger.debug(f"[Orchestrator] Registered SubagentBackgroundDelegate (native) for {agent_id}")

        # Register background tool completion hook for async tool result injection
        if hasattr(agent.backend, "get_pending_background_tool_results"):
            background_tool_hook = BackgroundToolCompleteHook()
            background_tool_hook.set_completed_jobs_getter(
                agent.backend.get_pending_background_tool_results,
            )
            manager.register_global_hook(HookType.POST_TOOL_USE, background_tool_hook)
            logger.debug(
                f"[Orchestrator] Registered BackgroundToolCompleteHook (native) for {agent_id}",
            )
        # Register per-round timeout hooks if configured
        self._register_round_timeout_hooks(agent_id, manager)

        # Register user-configured hooks from agent backend config
        agent_hooks = agent.backend.config.get("hooks")
        if agent_hooks:
            manager.register_hooks_from_config(agent_hooks, agent_id=agent_id)

        # Register PathPermissionManagerHook for PRE_TOOL_USE validation.
        # Native backends like Copilot need MassGen-level path validation.
        # Claude Code already handles permissions via add_dirs, so skip it.
        backend_provider = agent.backend.get_provider_name() if hasattr(agent.backend, "get_provider_name") else ""
        if backend_provider != "claude_code":
            _fm = getattr(agent.backend, "filesystem_manager", None)
            if _fm:
                _ppm = getattr(_fm, "path_permission_manager", None)
                if _ppm:
                    from massgen.filesystem_manager import PathPermissionManagerHook

                    ppm_hook = PathPermissionManagerHook(_ppm)
                    manager.register_global_hook(HookType.PRE_TOOL_USE, ppm_hook)
                    logger.debug(
                        f"[Orchestrator] Registered PathPermissionManagerHook (PRE_TOOL_USE) for {agent_id}",
                    )

        # Create context factory for hooks
        def context_factory() -> dict[str, Any]:
            workspace_path = None
            filesystem_manager = getattr(agent.backend, "filesystem_manager", None)
            if filesystem_manager and hasattr(filesystem_manager, "get_current_workspace"):
                try:
                    workspace_path = str(filesystem_manager.get_current_workspace())
                except Exception:
                    workspace_path = None
            return {
                "session_id": getattr(self, "session_id", ""),
                "orchestrator_id": getattr(self, "orchestrator_id", ""),
                "agent_id": agent_id,
                "workspace_path": workspace_path,
            }

        # Convert to native format using adapter
        native_config = adapter.build_native_hooks_config(
            manager,
            agent_id=agent_id,
            context_factory=context_factory,
        )

        # Set native hooks config on backend
        agent.backend.set_native_hooks_config(native_config)
        if hasattr(agent.backend, "set_background_wait_interrupt_provider"):

            async def _wait_interrupt_provider(
                requested_agent_id: str,
                *,
                _agent_id: str = agent_id,
            ) -> dict[str, Any] | None:
                target_agent_id = requested_agent_id or _agent_id
                if hasattr(self, "cancellation_manager") and self.cancellation_manager and self.cancellation_manager.is_cancelled:
                    return {
                        "interrupt_reason": "turn_cancelled",
                        "injected_content": None,
                    }

                runtime_sections = await self._collect_no_hook_runtime_fallback_sections(
                    target_agent_id,
                )
                if not runtime_sections:
                    return None
                return {
                    "interrupt_reason": "runtime_injection_available",
                    "injected_content": "\n".join(runtime_sections),
                }

            agent.backend.set_background_wait_interrupt_provider(
                _wait_interrupt_provider,
            )
        logger.info(
            f"[Orchestrator] Set up native hooks for {agent_id}: " f"PreToolUse={len(native_config.get('PreToolUse', []))}, " f"PostToolUse={len(native_config.get('PostToolUse', []))} hooks",
        )

    @classmethod
    def _coerce_answer_content_to_text(cls, content: Any) -> str:
        """Normalize heterogeneous answer payloads into plain text."""
        if content is None:
            return ""

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts = [cls._coerce_answer_content_to_text(item).strip() for item in content]
            return "\n".join(part for part in parts if part)

        if isinstance(content, dict):
            for key in (
                "content",
                "description",
                "text",
                "message",
                "answer",
                "final_answer",
                "summary",
                "output",
            ):
                if key not in content:
                    continue
                text = cls._coerce_answer_content_to_text(content.get(key)).strip()
                if text:
                    return text

            title = cls._coerce_answer_content_to_text(content.get("title")).strip()
            if title:
                return title

            try:
                return json.dumps(content, ensure_ascii=False, sort_keys=True)
            except TypeError:
                return str(content)

        return str(content)

    def _normalize_workspace_paths_in_answers(
        self,
        answers: dict[str, Any],
        viewing_agent_id: str | None = None,
    ) -> dict[str, str]:
        """Normalize absolute workspace paths in agent answers to accessible temporary workspace paths.

        This addresses the issue where agents working in separate workspace directories
        reference the same logical files using different absolute paths, causing them
        to think they're working on different tasks when voting.

        Converts workspace paths to temporary workspace paths where the viewing agent can actually
        access other agents' files for verification during context sharing.

        TODO: Replace with Docker volume mounts to ensure consistent paths across agents.

        Args:
            answers: Dict mapping agent_id to their answer content
            viewing_agent_id: The agent who will be reading these answers.
                            If None, normalizes to generic "workspace/" prefix.

        Returns:
            Dict with same keys but normalized answer content with accessible paths
        """
        normalized_answers = {}

        # Get viewing agent's temporary workspace path for context sharing (full absolute path)
        temp_workspace_base = None
        if viewing_agent_id:
            viewing_agent = self.agents.get(viewing_agent_id)
            if viewing_agent and viewing_agent.backend.filesystem_manager:
                temp_workspace_base = str(
                    viewing_agent.backend.filesystem_manager.agent_temporary_workspace,
                )
        # Create anonymous agent mapping for consistent directory names
        agent_mapping = self.coordination_tracker.get_reverse_agent_mapping()

        for agent_id, answer in answers.items():
            normalized_answer = self._coerce_answer_content_to_text(answer)

            # Replace all workspace paths found in the answer with accessible paths
            for other_agent_id, other_agent in self.agents.items():
                if not other_agent.backend.filesystem_manager:
                    continue

                anon_agent_id = agent_mapping.get(
                    other_agent_id,
                    other_agent_id,
                )
                replace_path = os.path.join(temp_workspace_base, anon_agent_id) if temp_workspace_base else anon_agent_id
                other_workspace = str(
                    other_agent.backend.filesystem_manager.get_current_workspace(),
                )
                logger.debug(
                    f"[Orchestrator._normalize_workspace_paths_in_answers] Replacing {other_workspace} in answer from {agent_id} with path {replace_path}. original answer: {normalized_answer}",
                )
                normalized_answer = normalized_answer.replace(
                    other_workspace,
                    replace_path,
                )
                logger.debug(
                    f"[Orchestrator._normalize_workspace_paths_in_answers] Intermediate normalized answer: {normalized_answer}",
                )

            normalized_answers[agent_id] = normalized_answer

        return normalized_answers

    def _normalize_workspace_paths_for_comparison(
        self,
        content: Any,
        replacement_path: str = "/workspace",
    ) -> str:
        """
        Normalize all workspace paths in content to a canonical form for equality comparison.

        Unlike _normalize_workspace_paths_in_answers which normalizes paths for specific agents,
        this method normalizes ALL workspace paths to a neutral canonical form (like '/workspace')
        so that content can be compared for equality regardless of which agent workspace it came from.

        Args:
            content: Content that may contain workspace paths

        Returns:
            Content with all workspace paths normalized to canonical form
        """
        normalized_content = self._coerce_answer_content_to_text(content)

        # Replace all agent workspace paths with canonical '/workspace/'
        for _, agent in self.agents.items():
            if not agent.backend.filesystem_manager:
                continue

            # Get this agent's workspace path
            workspace_path = str(
                agent.backend.filesystem_manager.get_current_workspace(),
            )
            normalized_content = normalized_content.replace(
                workspace_path,
                replacement_path,
            )

        return normalized_content

    def _flush_pending_subagent_results(self) -> None:
        """Flush any pending subagent results before coordination ends.

        Called during cleanup to log warnings about subagents that completed
        after the parent agent finished, or are still running when coordination ends.
        """
        if not hasattr(self, "_pending_subagent_results"):
            return

        for agent_id, pending in self._pending_subagent_results.items():
            if pending:
                logger.warning(
                    f"[Orchestrator] {len(pending)} background subagent result(s) for {agent_id} " f"were not delivered (parent finished before injection). " f"IDs: {[p[0] for p in pending]}",
                )
                # Clear the pending results since they won't be delivered
                self._pending_subagent_results[agent_id] = []

    async def _cleanup_active_coordination(self) -> None:
        """Force cleanup of active coordination streams and tasks on timeout."""
        # Stop the SubagentLaunchWatcher if running
        if self._subagent_launch_watcher is not None:
            try:
                await self._subagent_launch_watcher.stop()
            except Exception as e:
                logger.warning(f"[Orchestrator] Error stopping SubagentLaunchWatcher: {e}")
            self._subagent_launch_watcher = None

        # Flush any pending subagent results that weren't delivered
        self._flush_pending_subagent_results()

        # Cancel and cleanup active tasks
        if hasattr(self, "_active_tasks") and self._active_tasks:
            # Gracefully interrupt Claude Code backends before cancelling tasks
            for agent_id, agent in self.agents.items():
                if hasattr(agent, "backend") and hasattr(agent.backend, "interrupt"):
                    try:
                        await agent.backend.interrupt()
                    except Exception:
                        pass
            for agent_id, task in self._active_tasks.items():
                if not task.done():
                    # Only track if not already tracked by timeout above
                    if not self.is_orchestrator_timeout:
                        self.coordination_tracker.track_agent_action(
                            agent_id,
                            ActionType.CANCELLED,
                            "Coordination cleanup",
                        )
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass  # Ignore cleanup errors
            self._active_tasks.clear()

        # Close active streams
        if hasattr(self, "_active_streams") and self._active_streams:
            for agent_id in list(self._active_streams.keys()):
                await self._close_agent_stream(agent_id, self._active_streams)

    async def _cleanup_background_shells_for_agent(self, agent_id: str) -> None:
        """Compatibility shim after removing command-line background shell MCP tools."""
        return

    # TODO (v0.0.14 Context Sharing Enhancement - See docs/dev_notes/v0.0.14-context.md):
    # Add the following permission validation methods:
    # async def validate_agent_access(self, agent_id: str, resource_path: str, access_type: str) -> bool:
    #     """Check if agent has required permission for resource.
    #
    #     Args:
    #         agent_id: ID of the agent requesting access
    #         resource_path: Path to the resource being accessed
    #         access_type: Type of access (read, write, read-write, execute)
    #
    #     Returns:
    #         bool: True if access is allowed, False otherwise
    #     """
    #     # Implementation will check against PermissionManager
    #     pass

    def _calculate_jaccard_similarity(self, text1: str, text2: str) -> float:
        """Calculate Jaccard similarity between two texts based on word tokens.

        Args:
            text1: First text to compare
            text2: Second text to compare

        Returns:
            Similarity score between 0.0 and 1.0
        """
        # Tokenize and normalize - simple word-based approach
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 and not words2:
            return 1.0  # Both empty, consider identical
        if not words1 or not words2:
            return 0.0  # One empty, one not

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    def _check_answer_novelty(
        self,
        new_answer: Any,
        existing_answers: dict[str, Any],
    ) -> tuple[bool, str | None]:
        """Check if a new answer is sufficiently different from existing answers.

        Args:
            new_answer: The proposed new answer
            existing_answers: Dictionary of existing answers {agent_id: answer_content}

        Returns:
            Tuple of (is_novel, error_message). is_novel=True if answer passes novelty check.
        """
        # Lenient mode: no checks (current behavior)
        if self.config.answer_novelty_requirement == "lenient":
            return (True, None)

        # Determine threshold based on setting
        is_decomposition = getattr(self.config, "coordination_mode", "voting") == "decomposition"
        terminal_action = "call `stop`" if is_decomposition else "vote for an existing answer"
        if self.config.answer_novelty_requirement == "strict":
            threshold = 0.50  # Reject if >50% overlap (strict)
            error_msg = f"Your answer is too similar to existing answers (>50% overlap). Please use a fundamentally different approach, employ different tools/techniques, or {terminal_action}."
        else:  # balanced
            threshold = 0.70  # Reject if >70% overlap (balanced)
            error_msg = (
                f"Your answer is too similar to existing answers (>70% overlap). "
                f"Please provide a meaningfully different solution with new insights, "
                f"approaches, or tools, or {terminal_action}."
            )

        normalized_new_answer = self._coerce_answer_content_to_text(new_answer)

        # Check similarity against all existing answers
        for agent_id, existing_answer in existing_answers.items():
            similarity = self._calculate_jaccard_similarity(
                normalized_new_answer,
                self._coerce_answer_content_to_text(existing_answer),
            )
            if similarity > threshold:
                logger.info(
                    f"[Orchestrator] Answer rejected: {similarity:.2%} similar to {agent_id}'s answer (threshold: {threshold:.0%})",
                )
                return (False, error_msg)

        # Answer is sufficiently novel
        return (True, None)

    def _is_decomposition_mode(self) -> bool:
        """Return True when orchestration is running in decomposition mode."""
        return getattr(self.config, "coordination_mode", "voting") == "decomposition"

    def _is_subagent_type_active(self, type_name: str) -> bool:
        """Return True when *type_name* is in the active subagent types."""
        from massgen.subagent.type_scanner import DEFAULT_SUBAGENT_TYPES

        _cfg_types = getattr(
            getattr(self.config, "coordination_config", None),
            "subagent_types",
            None,
        )
        types = _cfg_types if _cfg_types is not None else DEFAULT_SUBAGENT_TYPES
        return type_name in {t.lower() for t in types}

    def _is_builder_subagent_enabled(self) -> bool:
        """Return True when 'builder' is in the active subagent types."""
        return self._is_subagent_type_active("builder")

    def _is_regression_guard_subagent_enabled(self) -> bool:
        """Return True when 'regression_guard' is in the active subagent types."""
        return self._is_subagent_type_active("regression_guard")

    def _is_changedoc_enabled(self) -> bool:
        """Return True when changedoc decision journal is enabled."""
        coord = getattr(self.config, "coordination_config", None)
        return bool(coord and getattr(coord, "enable_changedoc", True))

    def _gather_agent_changedocs(self) -> dict[str, str] | None:
        """Collect latest changedocs from all agents, or None if disabled/empty."""
        if not self._is_changedoc_enabled():
            return None
        changedocs: dict[str, str] = {}
        for aid, ans_list in self.coordination_tracker.answers_by_agent.items():
            if ans_list and ans_list[-1].changedoc:
                changedocs[aid] = ans_list[-1].changedoc
        return changedocs or None

    def _is_fairness_enabled(self) -> bool:
        """Return True when fairness controls are enabled."""
        return bool(getattr(self.config, "fairness_enabled", True))

    def _is_checklist_gated_mode(self) -> bool:
        """Return True when checklist_gated coordination is active."""
        return getattr(self.config, "voting_sensitivity", "balanced") == "checklist_gated"

    def _allow_midstream_peer_updates_before_checklist_submit(self) -> bool:
        """Resolve whether checklist mode allows pre-submit peer updates mid-stream."""
        configured = getattr(
            self.config,
            "allow_midstream_peer_updates_before_checklist_submit",
            None,
        )
        if configured is not None:
            return bool(configured)
        return not bool(getattr(self.config, "defer_peer_updates_until_restart", False))

    def _has_successful_checklist_submit_this_round(self, agent_id: str) -> bool:
        """Return True after the first accepted submit_checklist for the current answer."""
        self._sync_stdio_checklist_state_from_specs(agent_id)
        state = self.agent_states.get(agent_id)
        return bool(state and state.checklist_calls_this_round > 0)

    def _should_defer_peer_updates_until_restart(self, agent_id: str) -> bool:
        """Return True when peer-answer updates should wait for the next restart."""
        if not bool(getattr(self.config, "defer_peer_updates_until_restart", False)):
            return False
        if not self._is_checklist_gated_mode():
            return True
        if not self._allow_midstream_peer_updates_before_checklist_submit():
            return True
        return self._has_successful_checklist_submit_this_round(agent_id)

    def _update_fairness_pause_log_state(
        self,
        agent_id: str,
        is_paused: bool,
        pause_reason: str | None,
    ) -> None:
        """Log fairness pre-start pause transitions once per state change."""
        if is_paused:
            reason = pause_reason or "waiting for peers"
            if self._fairness_pause_log_reasons.get(agent_id) == reason:
                return
            self._fairness_pause_log_reasons[agent_id] = reason
            logger.info(
                f"[Orchestrator] Pausing {agent_id} before round start due to fairness gate: {reason}",
            )
            return

        if agent_id in self._fairness_pause_log_reasons:
            self._fairness_pause_log_reasons.pop(agent_id, None)
            logger.info(
                f"[Orchestrator] Fairness gate cleared for {agent_id}; resuming round starts",
            )

    def _log_fairness_answer_lead_block(
        self,
        agent_id: str,
        projected_lead: int,
        lead_cap: int,
    ) -> None:
        """Log fairness lead-cap block once per distinct blocked state."""
        block_state = (projected_lead, lead_cap)
        if self._fairness_block_log_states.get(agent_id) == block_state:
            return
        self._fairness_block_log_states[agent_id] = block_state
        logger.info(
            f"[Orchestrator] Fairness gate blocked new_answer for {agent_id} " f"(projected_lead={projected_lead}, cap={lead_cap})",
        )

    def _clear_fairness_answer_lead_block_log(self, agent_id: str) -> None:
        """Clear per-agent fairness lead-cap block log state."""
        self._fairness_block_log_states.pop(agent_id, None)

    def _get_agent_answer_revision_count(self, agent_id: str) -> int:
        """Get total answer revisions submitted by an agent."""
        return len(self.coordination_tracker.answers_by_agent.get(agent_id, []))

    def _get_active_fairness_agents(self) -> list[str]:
        """Return agents currently active for fairness gating.

        Agents already done (has_voted/stop) or killed are excluded so fairness
        does not deadlock late-stage coordination.
        """
        active_agents: list[str] = []
        for aid, state in self.agent_states.items():
            if state.is_killed or state.has_voted:
                continue
            active_agents.append(aid)
        return active_agents

    def _terminal_action_wording(self) -> str:
        """Return mode-specific terminal action guidance for error messaging."""
        if self._is_decomposition_mode():
            return "call `stop`"
        return "vote for an existing answer"

    def _get_answer_revision_counts(self) -> dict[str, int]:
        """Get current answer revision counts for all orchestrated agents."""
        return {aid: len(self.coordination_tracker.answers_by_agent.get(aid, [])) for aid in self.agents.keys()}

    def _get_current_answers_snapshot(self) -> dict[str, str]:
        """Return latest submitted answer content for each agent that has one.

        In step mode, includes ALL session dir answers (including the real
        agent's own prior answer) so the agent sees everything anonymized.
        A new answer from the real agent takes precedence over the prior one.
        """
        snapshot = {aid: state.answer for aid, state in self.agent_states.items() if state.answer}
        if self._step_mode and self._step_mode.enabled and self._step_inputs:
            for va_id, va_state in self._step_inputs.virtual_agents.items():
                if va_state.latest_answer is not None:
                    snapshot.setdefault(va_id, va_state.latest_answer)
        return snapshot

    def _resolve_step_mode_workspace(self, agent_id: str) -> str | None:
        """Resolve the workspace path for step mode output.

        After _save_agent_snapshot runs, the agent's cwd is cleared but
        snapshot_storage has the full copy. Prefer snapshot_storage when it
        has content; fall back to cwd if snapshot_storage is missing.
        Returns None when the agent produced no workspace files.
        """
        agent = self.agents.get(agent_id)
        if not agent or not agent.backend.filesystem_manager:
            return None
        fm = agent.backend.filesystem_manager
        if fm.snapshot_storage and fm.snapshot_storage.is_dir() and any(fm.snapshot_storage.iterdir()):
            return str(fm.snapshot_storage)
        if fm.cwd and Path(fm.cwd).is_dir() and any(Path(fm.cwd).iterdir()):
            return str(fm.cwd)
        return None

    def _resolve_step_mode_stale_paths(self, agent_id: str) -> list[str]:
        """Collect workspace paths the agent may have referenced in its answer text.

        These paths (cwd, temp workspace) are ephemeral and won't exist when
        another step mode invocation loads the session directory. They need to
        be replaced with the session dir workspace path by save_step_mode_output.

        Args:
            agent_id: The agent whose paths to collect.

        Returns:
            List of stale path strings (may be empty).
        """
        stale: list[str] = []
        agent = self.agents.get(agent_id)
        if not agent or not agent.backend.filesystem_manager:
            return stale
        fm = agent.backend.filesystem_manager
        if fm.cwd:
            stale.append(str(fm.cwd))
        if fm.agent_temporary_workspace:
            stale.append(str(fm.agent_temporary_workspace))
        return stale

    def _sync_decomposition_answer_visibility(self, agent_id: str) -> None:
        """Update seen-answer revision snapshot for an agent.

        In decomposition mode this also resets the consecutive answer streak when
        unseen external updates were observed.
        """

        state = self.agent_states.get(agent_id)
        if not state:
            return

        current_counts = self._get_answer_revision_counts()
        saw_unseen_external_update = any(other_id != agent_id and current_count > state.seen_answer_counts.get(other_id, 0) for other_id, current_count in current_counts.items())

        if self._is_decomposition_mode() and saw_unseen_external_update and state.decomposition_answer_streak > 0:
            logger.info(
                "[Orchestrator] Reset decomposition answer streak for %s after seeing external answer updates",
                agent_id,
            )
            state.decomposition_answer_streak = 0

        state.seen_answer_counts = current_counts

    def _mark_seen_answer_revisions(self, agent_id: str, source_agent_ids: list[str]) -> None:
        """Mark current answer revisions from source agents as seen by `agent_id`."""
        state = self.agent_states.get(agent_id)
        if not state:
            return
        for source_agent_id in source_agent_ids:
            state.seen_answer_counts[source_agent_id] = self._get_agent_answer_revision_count(source_agent_id)

    def _get_latest_answer_revision_timestamp(self, source_agent_id: str) -> float:
        """Get timestamp of the latest answer revision for an agent."""
        revisions = self.coordination_tracker.answers_by_agent.get(source_agent_id, [])
        if not revisions:
            return 0.0
        latest_revision = revisions[-1]
        return float(getattr(latest_revision, "timestamp", 0.0) or 0.0)

    def _get_unseen_answer_update_candidates(
        self,
        agent_id: str,
        current_answers: dict[str, str],
    ) -> list[tuple[str, str, float]]:
        """Return unseen source answer updates sorted newest-first by revision timestamp."""
        state = self.agent_states.get(agent_id)
        if not state:
            return []

        unseen_candidates: list[tuple[str, str, float]] = []
        for source_agent_id, answer_content in current_answers.items():
            # Never inject an agent's own answer back into itself.
            if source_agent_id == agent_id:
                continue

            seen_revision_count = state.seen_answer_counts.get(source_agent_id, 0)
            current_revision_count = self._get_agent_answer_revision_count(source_agent_id)
            if current_revision_count <= seen_revision_count:
                continue

            unseen_candidates.append(
                (
                    source_agent_id,
                    answer_content,
                    self._get_latest_answer_revision_timestamp(source_agent_id),
                ),
            )

        unseen_candidates.sort(key=lambda item: item[2], reverse=True)
        return unseen_candidates

    def _get_unseen_source_agent_ids(self, agent_id: str) -> list[str]:
        """Return source agents whose latest revisions are unseen by `agent_id`."""
        unseen_candidates = self._get_unseen_answer_update_candidates(
            agent_id,
            self._get_current_answers_snapshot(),
        )
        return [source_agent_id for source_agent_id, _, _ in unseen_candidates]

    def _has_unseen_answer_updates(self, agent_id: str) -> bool:
        """Return True when `agent_id` still has unseen latest peer revisions."""
        return bool(self._get_unseen_source_agent_ids(agent_id))

    def _select_midstream_answer_updates(
        self,
        agent_id: str,
        current_answers: dict[str, str],
    ) -> tuple[dict[str, str], bool]:
        """Select answer updates for mid-stream injection.

        Returns:
            Tuple of (selected_answers, had_unseen_updates). selected_answers may be
            empty if unseen updates exist but fairness cap for this round is exhausted.
        """
        unseen_candidates = self._get_unseen_answer_update_candidates(
            agent_id,
            current_answers,
        )
        if not unseen_candidates:
            return ({}, False)

        state = self.agent_states.get(agent_id)
        if not state:
            return ({}, True)

        selected_candidates = unseen_candidates
        if self._is_fairness_enabled():
            cap = int(getattr(self.config, "max_midstream_injections_per_round", 2))
            remaining_slots = max(cap - state.midstream_injections_this_round, 0)
            if remaining_slots <= 0:
                return ({}, True)
            selected_candidates = unseen_candidates[:remaining_slots]

        selected_answers = {source_agent_id: answer for source_agent_id, answer, _ in selected_candidates}
        return (selected_answers, True)

    @staticmethod
    def _extract_submitted_agent_labels(scores_payload: Any) -> set[str]:
        """Extract first-level agent labels from a submit_checklist scores payload."""
        if not isinstance(scores_payload, dict):
            return set()
        if not scores_payload:
            return set()

        # Flat format (E1/E2/...) is not per-agent.
        top_level_keys = {str(k) for k in scores_payload.keys()}
        if any(k.startswith("E") or k.startswith("T") for k in top_level_keys):
            return set()
        return top_level_keys

    def _mark_pending_checklist_recheck_labels(
        self,
        agent_id: str,
        source_agent_ids: list[str],
    ) -> None:
        """Record injected latest labels so one post-injection checklist recheck is allowed."""
        state = self.agent_states.get(agent_id)
        if not state or not source_agent_ids:
            return

        agent = self.agents.get(agent_id)
        backend = getattr(agent, "backend", None) if agent is not None else None
        supports_sdk = bool(getattr(backend, "supports_sdk_mcp", False))

        pending: set[str] = set()
        if supports_sdk:
            pending = set(getattr(state, "pending_checklist_recheck_labels", set()) or set())
        else:
            raw_pending: Any = None
            specs_path = getattr(backend, "_checklist_specs_path", None) if backend is not None else None
            if specs_path:
                try:
                    with open(specs_path, encoding="utf-8") as f:
                        specs_payload = json.load(f)
                    raw_pending = (specs_payload.get("state") or {}).get("pending_checklist_recheck_labels")
                except Exception:
                    raw_pending = None
            if raw_pending is None and backend is not None and hasattr(backend, "_checklist_state"):
                raw_pending = getattr(backend, "_checklist_state", {}).get("pending_checklist_recheck_labels", [])
            if isinstance(raw_pending, str):
                label = raw_pending.strip()
                if label:
                    pending.add(label)
            elif isinstance(raw_pending, (list, tuple, set)):
                for raw in raw_pending:
                    label = str(raw).strip()
                    if label:
                        pending.add(label)

        for source_agent_id in source_agent_ids:
            revisions = self.coordination_tracker.answers_by_agent.get(source_agent_id, [])
            if not revisions:
                continue
            latest_label = getattr(revisions[-1], "label", None)
            if latest_label:
                pending.add(str(latest_label))
        setattr(state, "pending_checklist_recheck_labels", pending)
        if backend is not None and hasattr(backend, "_checklist_state"):
            backend._checklist_state["pending_checklist_recheck_labels"] = sorted(pending)
            if not supports_sdk and hasattr(backend, "_checklist_specs_path"):
                try:
                    from .mcp_tools.checklist_tools_server import write_checklist_specs

                    write_checklist_specs(
                        items=getattr(backend, "_checklist_items", []),
                        state=backend._checklist_state,
                        output_path=backend._checklist_specs_path,
                    )
                except Exception:
                    logger.debug(
                        "[Orchestrator] Unable to persist pending checklist recheck labels for %s",
                        agent_id,
                        exc_info=True,
                    )

    def _register_injected_answer_updates(self, agent_id: str, source_agent_ids: list[str]) -> None:
        """Apply per-agent state updates after mid-stream answer injection."""
        state = self.agent_states.get(agent_id)
        if not state or not source_agent_ids:
            return

        external_sources = [source_id for source_id in source_agent_ids if source_id != agent_id]
        if self._is_decomposition_mode() and external_sources and state.decomposition_answer_streak > 0:
            logger.info(
                "[Orchestrator] Reset decomposition answer streak for %s after mid-stream answer injection",
                agent_id,
            )
            state.decomposition_answer_streak = 0

        self._mark_seen_answer_revisions(agent_id, source_agent_ids)

    def _check_fairness_answer_lead_cap(self, agent_id: str) -> tuple[bool, str | None]:
        """Enforce max lead in answer revisions over slowest active peer."""
        if not self._is_fairness_enabled():
            self._clear_fairness_answer_lead_block_log(agent_id)
            return (True, None)

        lead_cap = getattr(self.config, "fairness_lead_cap_answers", 1)
        if lead_cap is None:
            self._clear_fairness_answer_lead_block_log(agent_id)
            return (True, None)

        active_agents = self._get_active_fairness_agents()
        if agent_id not in active_agents or len(active_agents) <= 1:
            self._clear_fairness_answer_lead_block_log(agent_id)
            return (True, None)

        peer_counts = [self._get_agent_answer_revision_count(aid) for aid in active_agents if aid != agent_id]
        if not peer_counts:
            self._clear_fairness_answer_lead_block_log(agent_id)
            return (True, None)

        current_count = self._get_agent_answer_revision_count(agent_id)
        projected_lead = (current_count + 1) - min(peer_counts)

        if projected_lead <= lead_cap:
            self._clear_fairness_answer_lead_block_log(agent_id)
            return (True, None)

        terminal_action = self._terminal_action_wording()
        error_msg = (
            f"Fairness lead cap reached: submitting another `new_answer` would put you {projected_lead} answer(s) "
            f"ahead of the slowest active peer (cap={lead_cap}). Please wait for peers to catch up or {terminal_action}."
        )
        self._log_fairness_answer_lead_block(
            agent_id,
            projected_lead,
            lead_cap,
        )
        return (False, error_msg)

    def _should_pause_agent_for_fairness(self, agent_id: str) -> tuple[bool, str | None]:
        """Return whether an agent should wait before starting due to fairness lead cap.

        This is a pre-round gate that prevents a fast agent from starting another
        expensive iteration when `new_answer` would be rejected anyway.
        """
        if not self._is_fairness_enabled():
            return (False, None)
        if self.config.disable_injection:
            return (False, None)

        state = self.agent_states.get(agent_id)
        if not state or state.has_voted or state.is_killed:
            return (False, None)

        # Never block first answer round.
        if self._get_agent_answer_revision_count(agent_id) == 0:
            return (False, None)

        # At hard timeout, allow terminal progress instead of pausing indefinitely.
        if self._is_hard_timeout_active(agent_id):
            return (False, None)

        fairness_ok, fairness_error = self._check_fairness_answer_lead_cap(agent_id)
        if fairness_ok:
            return (False, None)
        return (True, fairness_error)

    def _is_hard_timeout_active(self, agent_id: str) -> bool:
        """Return True when hard timeout is currently active for an agent."""
        state = self.agent_states.get(agent_id)
        if not state:
            return False

        timeout_config = getattr(self.config, "timeout_config", None)
        if timeout_config is None:
            return False

        grace_seconds = timeout_config.round_timeout_grace_seconds or 0
        shared_timeout_state = state.round_timeout_state
        if shared_timeout_state and shared_timeout_state.soft_timeout_fired_at is not None:
            return (time.time() - shared_timeout_state.soft_timeout_fired_at) >= grace_seconds

        if state.round_start_time is None:
            return False

        current_round = self.coordination_tracker.get_agent_round(agent_id)
        if current_round == 0:
            soft_timeout = timeout_config.initial_round_timeout_seconds
        else:
            soft_timeout = timeout_config.subsequent_round_timeout_seconds
        if soft_timeout is None:
            return False

        elapsed = time.time() - state.round_start_time
        return elapsed >= (soft_timeout + grace_seconds)

    def _get_agent_answer_count_for_limit(self, agent_id: str) -> int:
        """Get answer count used for per-agent answer limit enforcement."""
        if self._is_decomposition_mode():
            state = self.agent_states.get(agent_id)
            if state:
                return state.decomposition_answer_streak
        return len(self.coordination_tracker.answers_by_agent.get(agent_id, []))

    def _get_total_answer_count(self) -> int:
        """Get total number of answer revisions across all agents."""
        return sum(len(answer_revisions) for answer_revisions in self.coordination_tracker.answers_by_agent.values())

    def _is_global_answer_limit_reached(self) -> bool:
        """Check whether the optional global answer cap has been reached."""
        global_limit = getattr(self.config, "max_new_answers_global", None)
        if global_limit is None:
            return False
        return self._get_total_answer_count() >= global_limit

    def _check_answer_count_limit(self, agent_id: str) -> tuple[bool, str | None]:
        """Check if agent has reached their answer count limit.

        Args:
            agent_id: The agent attempting to provide a new answer

        Returns:
            Tuple of (can_answer, error_message). can_answer=True if agent can provide another answer.
        """
        is_decomposition = self._is_decomposition_mode()

        # Enforce optional global cap first.
        if self._is_global_answer_limit_reached():
            total_answer_count = self._get_total_answer_count()
            global_limit = self.config.max_new_answers_global
            if is_decomposition:
                error_msg = f"The global maximum of {global_limit} new answer(s) has been reached " "across all agents. Please call `stop` to signal you are done."
            else:
                error_msg = f"The global maximum of {global_limit} new answer(s) has been reached " "across all agents. Please vote for the best existing answer using the `vote` tool."
            logger.info(
                "[Orchestrator] Answer rejected: global answer limit reached (%s/%s), attempted by %s",
                total_answer_count,
                global_limit,
                agent_id,
            )
            return (False, error_msg)

        if self.config.max_new_answers_per_agent is not None:
            # In voting mode this is total answers by agent; in decomposition mode this is
            # the consecutive streak since the agent last saw external updates.
            answer_count = self._get_agent_answer_count_for_limit(agent_id)

            if answer_count >= self.config.max_new_answers_per_agent:
                if is_decomposition:
                    error_msg = (
                        f"You've reached the maximum of {self.config.max_new_answers_per_agent} "
                        "consecutive new answer(s) without seeing external updates. "
                        "Please call `stop` to signal you are done."
                    )
                else:
                    error_msg = f"You've reached the maximum of {self.config.max_new_answers_per_agent} " "new answer(s). Please vote for the best existing answer using the `vote` tool."
                logger.info(
                    "[Orchestrator] Answer rejected: %s has reached per-agent limit (%s/%s)",
                    agent_id,
                    answer_count,
                    self.config.max_new_answers_per_agent,
                )
                return (False, error_msg)

        fairness_ok, fairness_error = self._check_fairness_answer_lead_cap(agent_id)
        if not fairness_ok:
            return (False, fairness_error)

        return (True, None)

    def _is_vote_only_mode(self, agent_id: str) -> bool:
        """Check if agent has exhausted their answer limit and must vote (or auto-stop).

        When an agent reaches max_new_answers_per_agent, they should only
        have the vote tool available (no new_answer or broadcast tools).

        In decomposition mode, hitting the limit auto-stops the agent instead
        of switching to vote-only tools.

        When defer_voting_until_all_answered=True, also requires ALL agents
        to have answered before voting is allowed.

        Args:
            agent_id: The agent to check

        Returns:
            True if agent must vote (has hit answer limit AND can vote now), False otherwise.
        """
        per_agent_limit = self.config.max_new_answers_per_agent
        answer_count = self._get_agent_answer_count_for_limit(agent_id)
        hit_answer_limit = per_agent_limit is not None and answer_count >= per_agent_limit
        hit_global_limit = self._is_global_answer_limit_reached()

        if not hit_answer_limit and not hit_global_limit:
            return False

        # Decomposition mode: auto-stop the agent instead of switching to vote-only
        if self._is_decomposition_mode():
            if not self.agent_states[agent_id].has_voted:
                last_answer = self.agent_states[agent_id].answer or ""
                if hit_global_limit:
                    total_answers = self._get_total_answer_count()
                    global_limit = self.config.max_new_answers_global
                    stop_reason = f"reached global answer limit ({total_answers}/{global_limit})"
                else:
                    stop_reason = f"reached per-agent consecutive answer limit ({answer_count}/{per_agent_limit})"
                self.agent_states[agent_id].has_voted = True
                self.agent_states[agent_id].stop_summary = f"Auto-stopped: {stop_reason}. Last work: {last_answer[:200]}"
                self.agent_states[agent_id].stop_status = "complete"
                self.coordination_tracker.add_agent_stop(
                    agent_id,
                    {"summary": self.agent_states[agent_id].stop_summary, "status": "complete"},
                )
                logger.info(
                    "[Orchestrator] Auto-stopped agent %s in decomposition mode (%s)",
                    agent_id,
                    stop_reason,
                )
            return False  # Don't switch to vote-only tools, agent is already stopped

        if self._should_skip_vote_rounds_for_synthesize():
            return False

        # If defer_voting_until_all_answered is enabled, also check that all agents have answered
        # unless global answer cap has already been reached.
        if self.config.defer_voting_until_all_answered and not hit_global_limit:
            all_answered = all(state.answer is not None for state in self.agent_states.values())
            if not all_answered:
                # Agent hit their limit but others haven't answered yet
                # Return False - agent is in "waiting" state, handled by _is_waiting_for_all_answers
                return False

        return True

    def _apply_decomposition_auto_stop_if_needed(self, agent_id: str) -> bool:
        """Apply decomposition auto-stop gate after refreshing answer visibility.

        Returns True when the agent is currently considered done/stopped and
        should be skipped for execution in this coordination iteration.
        """
        if not self._is_decomposition_mode():
            return False

        state = self.agent_states[agent_id]
        # Refresh seen revision counts before evaluating streak limits so agents
        # can resume after peers submit newer answers.
        self._sync_decomposition_answer_visibility(agent_id)

        was_voted = state.has_voted
        self._is_vote_only_mode(agent_id)  # applies decomposition auto-stop side effect
        if not was_voted and state.has_voted:
            self.coordination_tracker.change_status(agent_id, AgentStatus.STOPPED)
            logger.info(
                f"[Orchestrator] Skipping execution for {agent_id} (auto-stopped at answer limit)",
            )

        return state.has_voted

    def _is_waiting_for_all_answers(self, agent_id: str) -> bool:
        """Check if agent is waiting for all agents to answer before voting.

        This happens when defer_voting_until_all_answered=True and this agent
        has hit their answer limit but other agents haven't answered yet.

        Args:
            agent_id: The agent to check

        Returns:
            True if agent should wait (not run), False otherwise.
        """
        if not self.config.defer_voting_until_all_answered and not self._should_skip_vote_rounds_for_synthesize():
            return False

        # If global answer cap is reached, unblock voting immediately to avoid deadlock.
        if self._is_global_answer_limit_reached():
            return False

        if self.config.max_new_answers_per_agent is None:
            return False

        answer_count = self._get_agent_answer_count_for_limit(agent_id)
        hit_answer_limit = answer_count >= self.config.max_new_answers_per_agent

        if not hit_answer_limit:
            return False

        # Check if all agents have answered (treat killed agents as done —
        # they will never answer, so don't block others waiting for them).
        all_answered = all(state.answer is not None or state.is_killed for state in self.agent_states.values())
        if all_answered:
            return False  # Can proceed to voting

        if self._should_skip_vote_rounds_for_synthesize():
            logger.debug(
                f"[synthesize] {agent_id} waiting for all agents to answer before final presentation",
            )
        else:
            logger.debug(
                f"[defer_voting] {agent_id} waiting for all agents to answer before voting",
            )
        return True

    def _is_round_evaluator_gate_enabled(self) -> bool:
        """Return whether the orchestrator should run the round_evaluator gate itself."""
        coord = getattr(self.config, "coordination_config", None)
        return bool(
            coord and getattr(coord, "round_evaluator_before_checklist", False) and getattr(coord, "orchestrator_managed_round_evaluator", False),
        )

    def _get_evaluator_team_size(self) -> int:
        """Return the number of evaluator subagents in the shared child team."""
        coord = getattr(self.config, "coordination_config", None)
        sub_orch = getattr(coord, "subagent_orchestrator", None) if coord else None
        if sub_orch is None:
            return 0
        if isinstance(sub_orch, dict):
            agents = sub_orch.get("agents", [])
        else:
            agents = getattr(sub_orch, "agents", None) or []
        return len(agents)

    def _validate_evaluator_personas(
        self,
        personas: Any,
    ) -> str | None:
        """Validate evaluator personas input. Return error string or None if valid."""
        if not isinstance(personas, list):
            return "personas must be a list"
        expected = self._get_evaluator_team_size()
        if len(personas) == 0:
            return f"personas list is empty; expected {expected} persona(s)"
        if len(personas) != expected:
            return f"Expected {expected} persona(s) to match evaluator team size, got {len(personas)}"
        for i, p in enumerate(personas):
            if not isinstance(p, dict):
                return f"Persona at index {i} must be an object with 'label' and 'instructions'"
            if "label" not in p:
                return f"Persona at index {i} is missing required 'label' field"
            if "instructions" not in p:
                return f"Persona at index {i} is missing required 'instructions' field"
            if not str(p.get("label", "")).strip():
                return f"Persona at index {i} has empty label"
            if not str(p.get("instructions", "")).strip():
                return f"Persona at index {i} has empty instructions"
        return None

    def _consume_evaluator_personas(self) -> list[dict[str, str]] | None:
        """Consume pending evaluator personas, falling back to last used set.

        Returns the personas to use for the current round evaluator spawn,
        or None if no personas are configured.
        """
        if self._pending_evaluator_personas is not None:
            consumed = self._pending_evaluator_personas
            self._last_evaluator_personas = consumed
            self._pending_evaluator_personas = None
            return consumed
        if self._last_evaluator_personas is not None:
            return self._last_evaluator_personas
        return None

    def _get_round_evaluator_latest_labels(
        self,
        answers: dict[str, str],
    ) -> tuple[str, ...]:
        """Return the latest answer labels for the current revision set."""
        labels: list[str] = []
        for answering_agent_id in sorted(answers.keys()):
            label = self.coordination_tracker.get_latest_answer_label(answering_agent_id)
            if label:
                labels.append(label)
        return tuple(labels)

    def _get_round_evaluator_upcoming_round(self, agent_id: str) -> int:
        """Return the next user-facing round number for programmatic tool events."""
        try:
            restart_count = self.agent_states[agent_id].restart_count
        except Exception:
            restart_count = 0
        try:
            return max(1, int(restart_count) + 1)
        except Exception:
            return 1

    def _get_round_evaluator_display_round(self, agent_id: str) -> int:
        """Attach round-evaluator tool cards to the completed parent round they analyze."""
        try:
            return max(1, int(self.coordination_tracker.get_agent_round(agent_id)))
        except Exception:
            return 1

    def _queue_round_start_context_block(self, agent_id: str, block: str) -> None:
        """Queue a context block for the next parent round."""
        normalized = str(block or "").strip()
        if not normalized:
            return
        self._round_start_context_blocks.setdefault(agent_id, []).append(normalized)

    def _consume_round_start_context_block(self, agent_id: str) -> str | None:
        """Pop and combine queued round-start context blocks for an agent."""
        blocks = self._round_start_context_blocks.pop(agent_id, [])
        normalized = [str(block or "").strip() for block in blocks if str(block or "").strip()]
        if not normalized:
            return None
        return "\n\n".join(normalized)

    def _load_essential_files_manifests(
        self,
        agent_id: str,
    ) -> dict[str, Any]:
        """Load essential_files_manifest.json from all agents' snapshots.

        Returns a dict mapping anonymous agent ID to parsed manifest data.
        Skips agents without manifests or with invalid JSON.
        """
        manifests: dict[str, Any] = {}
        if not self._snapshot_storage:
            return manifests

        agent_mapping = self.coordination_tracker.get_reverse_agent_mapping()
        snapshot_base = Path(self._snapshot_storage)

        for source_agent_id in self.agents:
            anon_id = agent_mapping.get(source_agent_id, source_agent_id)
            manifest_path = snapshot_base / source_agent_id / "memory" / "short_term" / "essential_files_manifest.json"
            if not manifest_path.exists():
                continue
            try:
                manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
                if not isinstance(manifest_data, dict) or manifest_data.get("version") != 1:
                    logger.warning(
                        f"[EssentialFiles] Invalid manifest version for {source_agent_id}, skipping",
                    )
                    continue
                manifests[anon_id] = manifest_data
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(
                    f"[EssentialFiles] Failed to load manifest for {source_agent_id}: {e}",
                )
        return manifests

    def _format_essential_files_context_block(
        self,
        manifests: dict[str, Any],
        agent_id: str,
    ) -> str | None:
        """Format essential files manifests as an XML context block for user message injection.

        Reads file contents for read_whole_file=true entries, includes read guidance
        for read_whole_file=false entries. Groups by agent with anonymous IDs.
        Uses the same eviction pattern as tool results for files exceeding 20K tokens.
        """
        if not manifests:
            return None

        agent_mapping = self.coordination_tracker.get_reverse_agent_mapping()
        # Get answer labels for each agent
        answer_labels: dict[str, str] = {}
        for aid, answers_list in self.coordination_tracker.answers_by_agent.items():
            anon = agent_mapping.get(aid, aid)
            if answers_list:
                answer_labels[anon] = answers_list[-1].label

        snapshot_base = Path(self._snapshot_storage) if self._snapshot_storage else None

        parts = [
            "<essential_files>",
            "<instructions>",
            "Files from previous answers are pre-loaded below, grouped by agent.",
            "DO NOT re-read pre-loaded files unless you modify them.",
            'Files listed under "Read These" at the end of each agent section were too large to',
            "pre-load — read ALL of them in parallel at the start of your round.",
            "</instructions>",
        ]

        for anon_id, manifest in sorted(manifests.items()):
            label = answer_labels.get(anon_id, anon_id)
            summary = manifest.get("summary", "")
            files = manifest.get("files", [])
            if not files:
                continue

            parts.append(f'\n<agent id="{anon_id}" answer_label="{label}">')
            if summary:
                parts.append(f"<summary>{summary}</summary>")

            preloaded_files = []
            read_guidance_files = []

            for file_entry in files:
                file_path = file_entry.get("path", "")
                why = file_entry.get("why", "")
                read_whole = file_entry.get("read_whole_file", False)
                how_to_read = file_entry.get("how_to_read")

                if not file_path:
                    continue

                if read_whole:
                    preloaded_files.append(file_entry)
                else:
                    read_guidance_files.append(file_entry)

            # Render pre-loaded files
            for file_entry in preloaded_files:
                file_path = file_entry["path"]
                display_path = f"{anon_id}/{file_path}"

                # Resolve actual file from snapshot
                content = None
                if snapshot_base:
                    # Find the real agent ID for this anon ID
                    real_agent_id = None
                    for aid, anon in agent_mapping.items():
                        if anon == anon_id:
                            real_agent_id = aid
                            break
                    if real_agent_id:
                        actual_path = snapshot_base / real_agent_id / file_path
                        if actual_path.exists() and actual_path.is_file():
                            try:
                                content = actual_path.read_text(encoding="utf-8")
                            except (OSError, UnicodeDecodeError) as e:
                                content = f"[Error reading file: {e}]"

                if content is not None:
                    # Check if content is too large (use same threshold as tool eviction)
                    from .filesystem_manager._constants import (
                        TOOL_RESULT_EVICTION_PREVIEW_TOKENS,
                        TOOL_RESULT_EVICTION_THRESHOLD_TOKENS,
                    )

                    # Rough token estimate: ~4 chars per token
                    estimated_tokens = len(content) // 4
                    if estimated_tokens > TOOL_RESULT_EVICTION_THRESHOLD_TOKENS:
                        # Show preview only
                        preview_chars = TOOL_RESULT_EVICTION_PREVIEW_TOKENS * 4
                        preview = content[:preview_chars]
                        parts.append(
                            f'\n<file path="{display_path}" preview="true" ' f'chars="0-{preview_chars}" total="{len(content)}">',
                        )
                        parts.append(preview)
                        parts.append("</file>")
                    else:
                        parts.append(f'\n<file path="{display_path}">')
                        parts.append(content)
                        parts.append("</file>")
                else:
                    parts.append(f'\n<file path="{display_path}">')
                    parts.append("[File not found in snapshot]")
                    parts.append("</file>")

            # Render read-guidance files at end
            if read_guidance_files:
                parts.append("\n<read_these>")
                parts.append(
                    "Read these files in parallel at the start of your round:\n",
                )
                for file_entry in read_guidance_files:
                    file_path = file_entry["path"]
                    why = file_entry.get("why", "")
                    how_to_read = file_entry.get("how_to_read", "")
                    display_path = f"{anon_id}/{file_path}"
                    parts.append(f"- `{display_path}` — {why}")
                    if how_to_read:
                        parts.append(f"  How to read: {how_to_read}")
                parts.append("</read_these>")

            parts.append("</agent>")

        parts.append("\n</essential_files>")
        return "\n".join(parts)

    def _rewrite_subagent_mcp_config_files(
        self,
        workspace_root: Any,
        agent_id: str,
    ) -> None:
        """Re-write the subagent MCP JSON config files that may have been lost
        when the workspace was cleared between rounds.

        These are the same files originally created by _create_subagent_mcp_config
        and referenced by path in the MCP server args.
        """
        import json
        from pathlib import Path as PathlibPath

        mcp_temp_dir = PathlibPath(workspace_root) / ".massgen" / "subagent_mcp"
        mcp_temp_dir.mkdir(parents=True, exist_ok=True)

        _token = self.coordination_tracker.get_path_token(agent_id)

        try:
            # agent_configs.json
            agent_configs = []
            for aid, a in self.agents.items():
                agent_cfg: dict[str, Any] = {"id": aid}
                if hasattr(a.backend, "config"):
                    backend_cfg = {k: v for k, v in a.backend.config.items() if k not in ("mcp_servers", "_config_path")}
                    agent_cfg["backend"] = backend_cfg
                runtime_agent_config = getattr(a, "config", None)
                subagent_agents = getattr(runtime_agent_config, "subagent_agents", None)
                if isinstance(subagent_agents, list) and subagent_agents:
                    agent_cfg["subagent_agents"] = json.loads(json.dumps(subagent_agents))
                agent_configs.append(agent_cfg)
            with open(mcp_temp_dir / f"{_token}_agent_configs.json", "w") as f:
                json.dump(agent_configs, f)

            # coordination_config.json
            coord_cfg = getattr(self.config, "coordination_config", None)
            if coord_cfg:
                parent_coordination_config = self._build_parent_coordination_config_for_subagents()
                if parent_coordination_config:
                    with open(mcp_temp_dir / f"{_token}_coordination_config.json", "w") as f:
                        json.dump(parent_coordination_config, f)

            # orchestrator_config.json
            if coord_cfg:
                so_cfg = getattr(coord_cfg, "subagent_orchestrator", None)
                if so_cfg:
                    with open(mcp_temp_dir / f"{_token}_orchestrator_config.json", "w") as f:
                        json.dump(so_cfg.to_dict(), f)

            logger.info(
                f"[Orchestrator] Re-wrote subagent MCP config files to {mcp_temp_dir}",
            )
        except Exception as e:
            logger.warning(f"[Orchestrator] Failed to re-write subagent MCP config files: {e}")

    def _ensure_context_md_for_round_evaluator(
        self,
        workspace_root: Any,
        parent_agent_id: str,
    ) -> None:
        """Write a CONTEXT.md into the parent workspace for the round evaluator.

        The SubagentManager requires CONTEXT.md in the parent workspace so it
        can auto-copy it into each evaluator subagent workspace.  When the
        orchestrator manages the spawn, the parent agent may not have created
        one (or it may have been cleared between rounds).
        """
        from pathlib import Path as PathlibPath

        context_path = PathlibPath(workspace_root) / "CONTEXT.md"
        if context_path.exists():
            return  # Parent already wrote one — don't overwrite

        task_summary = (self.current_task or "Task coordination")[:2000]
        content = f"# Task Context\n\n## Task\n{task_summary}\n"
        try:
            context_path.write_text(content, encoding="utf-8")
            logger.info(
                f"[Orchestrator] Wrote CONTEXT.md to {workspace_root} for round evaluator",
            )
        except Exception as e:
            logger.warning(f"[Orchestrator] Failed to write CONTEXT.md: {e}")

    def _build_round_evaluator_task(
        self,
        parent_agent_id: str,
        answers: dict[str, str],
    ) -> str:
        """Build the orchestrator-owned round_evaluator task brief."""
        criteria_agent_id = parent_agent_id if self._is_decomposition_mode() else None
        checklist_items, _, verify_by, _, _anti, _score_anchors = self._resolve_effective_checklist_criteria(criteria_agent_id)

        criteria_lines: list[str] = []
        for idx, item in enumerate(checklist_items or [], start=1):
            criterion_id = f"E{idx}"
            verify_line = ""
            if verify_by and verify_by.get(criterion_id):
                verify_line = f" (verify_by: {verify_by[criterion_id]})"
            criteria_lines.append(f"- {criterion_id}: {item}{verify_line}")
        criteria_block = "\n".join(criteria_lines) if criteria_lines else "- No explicit checklist criteria configured"

        normalized_answers = self._normalize_workspace_paths_in_answers(
            answers,
            viewing_agent_id=parent_agent_id,
        )
        # Use simple revision labels instead of internal agent labels (agent1.1)
        # to avoid confusion — the evaluator subagent has its own agent numbering.
        answer_sections: list[str] = []
        for revision_idx, answering_agent_id in enumerate(sorted(normalized_answers.keys()), start=1):
            label = f"Current answer (revision {revision_idx})" if len(normalized_answers) == 1 else f"Answer revision {revision_idx}"
            answer_sections.append(
                f"## {label}\n\n{normalized_answers[answering_agent_id]}",
            )

        answer_block = "\n\n".join(answer_sections) if answer_sections else "No answers available."
        coord_cfg = getattr(self.config, "coordination_config", None)
        transformation_pressure = getattr(
            coord_cfg,
            "round_evaluator_transformation_pressure",
            "balanced",
        )
        pressure_lines = [
            "TRANSFORMATION PRESSURE:",
            f"- Current setting: {transformation_pressure}.",
        ]
        if transformation_pressure == "gentle":
            pressure_lines.append(
                "- Exploit the current thesis longer and only escalate to a thesis shift when ceiling evidence is clear.",
            )
        elif transformation_pressure == "aggressive":
            pressure_lines.append(
                "- Search harder for a higher-leverage thesis or frontier move. Incremental-only follow-up or local convergence needs stronger justification.",
            )
        else:
            pressure_lines.append(
                "- Default balance: pursue a stronger thesis once the current line is plateauing, but do not chase novelty for its own sake.",
            )
        pressure_lines.append(
            "- Regardless of pressure, correctness-critical work still comes first and you must resolve your diagnosis into one committed next-round thesis.",
        )
        pressure_block = "\n".join(pressure_lines) + "\n\n"
        delegate_targets = self._get_parent_round_evaluator_delegate_targets()
        if delegate_targets:
            delegation_block = (
                "PARENT DELEGATION OPTIONS:\n"
                f"- The parent can delegate next-round work to these specialized subagents: {', '.join(delegate_targets)}.\n"
                "- These execution hints are for the parent's next round, not for this evaluator child runtime.\n"
                "- Base `execution` in `next_tasks.json` on what the parent can delegate, not by whether you can spawn subagents inside this evaluator run.\n"
                "- Do not emit `round_evaluator` as a delegate target.\n\n"
            )
        else:
            delegation_block = (
                "PARENT DELEGATION OPTIONS:\n"
                "- No parent-specialized subagents are available for delegation in the next round.\n"
                "- Keep execution hints inline unless the task brief explicitly provides a reusable subagent_id.\n\n"
            )
        # Include previous evolved prompt context so the evaluator can
        # see what directions were already tried (without using it as the
        # base to rewrite from — always rewrite from the original task).
        evolved_prompt_block = ""
        current_evolved = self._evolved_prompts.get(parent_agent_id)
        if current_evolved:
            evolved_prompt_block = "PREVIOUS EVOLVED PROMPT (for context — do NOT rewrite from this; " "always rewrite from the ORIGINAL TASK above):\n" f"{current_evolved}\n\n"

        return (
            "Produce one very critical cross-answer critique packet for the parent agent.\n\n"
            f"ORIGINAL TASK:\n{self._original_task or self.current_task or 'Task coordination'}\n\n"
            f"{evolved_prompt_block}"
            "EVALUATION CRITERIA:\n"
            f"{criteria_block}\n\n"
            f"{pressure_block}"
            f"{delegation_block}"
            "CANDIDATE ANSWERS:\n"
            f"{answer_block}\n\n"
            "Write the authoritative critique packet to `critique_packet.md`. "
            "Write machine-readable verdict metadata to `verdict.json`. "
            "When iteration is needed, write the implementation handoff to `next_tasks.json`. "
            "Keep your `answer` minimal and do not provide parent workflow recommendations."
        )

    def _get_parent_round_evaluator_delegate_targets(self) -> list[str]:
        """Return specialized subagent types the parent can delegate to next round."""
        coord = getattr(self.config, "coordination_config", None)
        if not coord or not getattr(coord, "enable_subagents", False):
            return []

        from massgen.subagent.type_scanner import DEFAULT_SUBAGENT_TYPES

        active_types = getattr(coord, "subagent_types", None)
        if active_types is None:
            active_types = DEFAULT_SUBAGENT_TYPES

        targets: list[str] = []
        seen: set[str] = set()
        for raw_type in active_types or []:
            type_name = str(raw_type or "").strip()
            if not type_name:
                continue
            lowered = type_name.lower()
            # Exclude analytical subagent types — they observe and report,
            # they don't execute fix/evolution tasks.
            analytical_types = {"round_evaluator", "execution_trace_analyzer"}
            if lowered in analytical_types or lowered in seen:
                continue
            seen.add(lowered)
            targets.append(type_name)
        return targets

    def _get_round_evaluator_context_paths(
        self,
        parent_agent_id: str,
        temp_workspace_path: str | None = None,
    ) -> list[str]:
        """Collect explicit read-only context paths for the round_evaluator task."""
        context_paths: list[str] = []
        seen: set[str] = set()

        def _add(path_value: Any) -> None:
            normalized = str(path_value or "").strip()
            if not normalized or normalized in seen:
                return
            # Resolve relative paths so the subagent MCP server can validate them.
            resolved = str(Path(normalized).resolve()) if normalized else normalized
            if resolved in seen:
                return
            # Skip non-existent paths — the MassGen subprocess validates
            # context paths exist and fails hard if they don't.
            if not Path(resolved).exists():
                return
            seen.add(resolved)
            context_paths.append(resolved)

        _add(temp_workspace_path)

        agent = self.agents.get(parent_agent_id)
        filesystem_manager = getattr(getattr(agent, "backend", None), "filesystem_manager", None)
        if filesystem_manager is not None:
            _add(getattr(filesystem_manager, "agent_temporary_workspace", None))
            get_workspace = getattr(filesystem_manager, "get_current_workspace", None)
            if callable(get_workspace):
                try:
                    workspace_path = get_workspace()
                except Exception:
                    workspace_path = None
                _add(workspace_path)
            _add(getattr(filesystem_manager, "cwd", None))

        _add(self._agent_temporary_workspace)
        return context_paths

    def _emit_round_evaluator_spawn_event(
        self,
        *,
        phase: str,
        agent_id: str,
        tool_call_id: str,
        round_number: int,
        args: dict[str, Any],
        result: dict[str, Any] | None = None,
        elapsed_seconds: float = 0.0,
        is_error: bool = False,
        status: str = "success",
    ) -> None:
        """Emit tool events so programmatic subagent launches reuse the TUI pipeline."""
        emitter = get_event_emitter()
        if not emitter:
            return

        if phase == "start":
            emitter.emit_raw(
                StructuredEventType.TOOL_START,
                agent_id=agent_id,
                round_number=round_number,
                tool_id=tool_call_id,
                tool_name="spawn_subagents",
                args=args,
                server_name=self._subagent_server_name(agent_id),
            )
            return

        emitter.emit_raw(
            StructuredEventType.TOOL_COMPLETE,
            agent_id=agent_id,
            round_number=round_number,
            tool_id=tool_call_id,
            tool_name="spawn_subagents",
            result=json.dumps(result or {}, ensure_ascii=False),
            elapsed_seconds=elapsed_seconds,
            status=status,
            is_error=is_error,
        )

    def _format_round_evaluator_result_block(
        self,
        subagent_id: str,
        result: "SubagentResult | RoundEvaluatorResult",
        auto_injected: bool = False,
    ) -> str:
        """Format the blocking round_evaluator result for next-round prompt injection."""
        from .subagent.models import RoundEvaluatorResult

        if isinstance(result, RoundEvaluatorResult):
            evaluator_result = result
        else:
            evaluator_result = RoundEvaluatorResult.from_subagent_result(result)
        return Orchestrator._format_round_evaluator_result_block_static(
            subagent_id=subagent_id,
            evaluator_result=evaluator_result,
            auto_injected=auto_injected,
        )

    @staticmethod
    def _strip_absolute_workspace_paths(text: str) -> str:
        """Replace absolute workspace paths with relative basenames.

        Evaluator packet text often contains deep absolute paths like
        ``/Users/.../workspace_abc/subagents/.../agent_1_xyz/critique_packet.md``.
        When the packet is injected into the parent's context, these paths
        cause the agent to waste many tool calls navigating the eval's
        internal directory tree.  Replace them with just the filename so
        the prose is still readable without triggering path-chasing.
        """
        import re

        # Match paths starting with / that contain /workspace and end with
        # a filename (letters, digits, dots, hyphens, underscores).
        return re.sub(
            r"/\S*?/(?:workspace|workspaces|subagents)/\S*?/([A-Za-z0-9_.-]+\.(?:md|json|txt|py|png|svg|yaml|yml))\b",
            r"`\1`",
            text,
        )

    @staticmethod
    def _format_round_evaluator_result_block_static(
        subagent_id: str,
        evaluator_result: "RoundEvaluatorResult",
        auto_injected: bool = False,
    ) -> str:
        """Format the blocking round_evaluator result for next-round prompt injection."""
        status = evaluator_result.status
        packet_text = evaluator_result.clean_packet_text or evaluator_result.packet_text or "(no packet produced)"
        critique_path = evaluator_result.primary_artifact_path or "(missing critique_packet.md path)"
        verdict_path = evaluator_result.verdict_artifact_path or "(missing verdict.json path)"
        next_tasks_path = evaluator_result.next_tasks_artifact_path or "(missing next_tasks.json path)"

        if auto_injected:
            sanitized_packet = Orchestrator._strip_absolute_workspace_paths(packet_text)
            strategy_lines: list[str] = []
            if evaluator_result.next_tasks_objective:
                strategy_lines.append(f"Chosen objective: {evaluator_result.next_tasks_objective}")
            if evaluator_result.next_tasks_primary_strategy:
                strategy_lines.append(f"Chosen strategy: {evaluator_result.next_tasks_primary_strategy}")
            if evaluator_result.next_tasks_why_this_strategy:
                strategy_lines.append(f"Why this strategy: {evaluator_result.next_tasks_why_this_strategy}")
            if evaluator_result.next_tasks_strategy_mode:
                strategy_lines.append(f"Strategy mode: {evaluator_result.next_tasks_strategy_mode}")
            if evaluator_result.next_tasks_incremental_override_reason:
                strategy_lines.append(
                    "Incremental override reason: " + evaluator_result.next_tasks_incremental_override_reason,
                )
            if evaluator_result.next_tasks_deprioritize_or_remove:
                strategy_lines.append(
                    "Deprioritize or remove: " + ", ".join(evaluator_result.next_tasks_deprioritize_or_remove),
                )
            success_contract = evaluator_result.next_tasks_success_contract or {}
            if success_contract:
                outcome_statement = str(success_contract.get("outcome_statement") or "").strip()
                quality_bar = str(success_contract.get("quality_bar") or "").strip()
                fail_if_any = [str(item).strip() for item in success_contract.get("fail_if_any", []) if str(item).strip()]
                required_evidence = [str(item).strip() for item in success_contract.get("required_evidence", []) if str(item).strip()]
                strategy_lines.append("Success contract:")
                if outcome_statement:
                    strategy_lines.append(f"- Outcome: {outcome_statement}")
                if quality_bar:
                    strategy_lines.append(f"- Quality bar: {quality_bar}")
                if fail_if_any:
                    strategy_lines.append(f"- Fail if any: {'; '.join(fail_if_any)}")
                if required_evidence:
                    strategy_lines.append(f"- Required evidence: {'; '.join(required_evidence)}")
            strategy_block = ("\n".join(strategy_lines) + "\n\n") if strategy_lines else ""
            return (
                "============================================================\n"
                f"ROUND EVALUATOR RESULT (status: {status})\n"
                "============================================================\n"
                "The orchestrator ran one blocking `round_evaluator` before this round.\n"
                "The evaluator's tasks have been auto-injected into your task plan.\n\n"
                f'<evaluator_summary subagent_id="{subagent_id}" status="{status}">\n'
                f"{sanitized_packet}\n"
                "</evaluator_summary>\n\n"
                f"{strategy_block}"
                "Workflow:\n"
                "1. Call `get_task_plan` — the evaluator's tasks are already there.\n"
                "2. Reference the authoritative evaluator artifacts when needed:\n"
                f"   - critique_packet.md: {critique_path}\n"
                f"   - verdict.json: {verdict_path}\n"
                f"   - next_tasks.json: {next_tasks_path}\n"
                "3. If the task plan includes correctness-critical tasks or tasks tied to\n"
                "   explicit correctness criteria, do those first.\n"
                "4. Then execute the remaining higher-order work and follow\n"
                "   `implementation_guidance` on each task as written.\n"
                "5. Finish with the final preserve/regression verification so\n"
                "   preserved strengths remain intact and earlier correctness fixes still\n"
                "   pass after later changes.\n"
                "6. If the deliverable is a pure text artifact, put the final\n"
                "   artifact body directly in `new_answer.content`.\n"
                "7. Otherwise, call `new_answer` with your usual concise summary.\n\n"
                "Do NOT call `submit_checklist`.\n"
                "Do NOT call `draft_approach`.\n"
                "Do NOT write a second diagnostic report.\n"
                "Do NOT spawn another `round_evaluator`.\n"
                "============================================================"
            )
        else:
            instructions = (
                "IMPORTANT: This evaluator packet is your sole diagnostic basis for\n"
                f"submit_checklist. Pass this exact path as report_path: {critique_path}\n"
                "Do NOT run a separate self-evaluation or author a second diagnostic\n"
                "report from scratch.\n"
            )

        return (
            "============================================================\n"
            f"ROUND EVALUATOR RESULT (status: {status})\n"
            "============================================================\n"
            "The orchestrator ran one blocking `round_evaluator` before this round.\n\n"
            f"{instructions}\n"
            f'<evaluator_packet subagent_id="{subagent_id}" status="{status}">\n'
            f"{packet_text}\n"
            "</evaluator_packet>\n"
            "============================================================"
        )

    @staticmethod
    def _format_round_evaluator_timeout_block_static(
        subagent_id: str,
        error_message: str,
    ) -> str:
        """Format a degraded timeout notice when no evaluator packet was produced."""
        normalized_error = str(error_message or "round_evaluator timed out before producing a packet").strip()
        return (
            "============================================================\n"
            "ROUND EVALUATOR RESULT (status: degraded)\n"
            "============================================================\n"
            "The orchestrator ran one blocking `round_evaluator` before this round,\n"
            "but it timed out before producing `critique_packet.md`.\n\n"
            f'<evaluator_timeout subagent_id="{subagent_id}" status="degraded">\n'
            f"{normalized_error}\n"
            "</evaluator_timeout>\n\n"
            "For this answer set, the orchestrator is degrading to the normal parent-owned checklist flow.\n"
            "Do NOT wait for evaluator artifacts for this revision.\n"
            "You may call `submit_checklist` and `draft_approach` as usual.\n"
            "============================================================"
        )

    @staticmethod
    def extract_all_evaluator_answers(
        log_path: str,
        workspace_path: str,
    ) -> dict[str, str] | None:
        """Read all evaluator agent answers from a round_evaluator's log directory.

        Reads status.json to discover agent IDs and timestamps, then reads
        each agent's answer.txt. Returns anonymized keys like
        ``{"Evaluator A": "...", "Evaluator B": "...", ...}``.

        Returns None if the log directory or status.json doesn't exist.
        """
        log_dir = Path(log_path)

        # log_path may be the base dir or a resolved events.jsonl path.
        # Walk up to find the directory containing full_logs/status.json.
        full_logs = log_dir / "full_logs"
        status_file = full_logs / "status.json"
        if not status_file.exists():
            # Try walking up from resolved path (e.g. .../full_logs/events.jsonl)
            for parent in [log_dir.parent, log_dir.parent.parent]:
                candidate = parent / "full_logs" / "status.json"
                if candidate.exists():
                    full_logs = parent / "full_logs"
                    status_file = candidate
                    break
            else:
                return None

        try:
            status_data = json.loads(status_file.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning(
                "[Orchestrator] Failed to read round_evaluator status.json from %s",
                status_file,
            )
            return None

        historical_list = status_data.get("historical_workspaces", [])
        if not isinstance(historical_list, list) or not historical_list:
            return None

        answers: dict[str, str] = {}
        anonymous_labels = iter(f"Evaluator {chr(65 + i)}" for i in range(26))

        for ws_info in historical_list:
            if not isinstance(ws_info, dict):
                continue
            agent_id = ws_info.get("agentId", "")
            timestamp = ws_info.get("timestamp", "")
            if not agent_id or not timestamp:
                continue

            # Try full_logs/{agentId}/{timestamp}/answer.txt
            answer_file = full_logs / agent_id / timestamp / "answer.txt"
            if answer_file.exists():
                try:
                    text = answer_file.read_text().strip()
                    if text:
                        label = next(anonymous_labels, f"Evaluator {len(answers)}")
                        answers[label] = text
                except OSError:
                    pass

        return answers if answers else None

    @staticmethod
    def extract_evaluator_workspace_paths(
        log_path: str,
    ) -> list[str]:
        """Return workspace paths for each eval agent in a round_evaluator run.

        Looks for ``full_logs/{agentId}/workspace/`` directories, which are
        the persisted snapshots of each evaluator's workspace.
        """
        log_dir = Path(log_path)

        # Same walk-up logic as extract_all_evaluator_answers
        full_logs = log_dir / "full_logs"
        if not full_logs.is_dir():
            for parent in [log_dir.parent, log_dir.parent.parent]:
                candidate = parent / "full_logs"
                if candidate.is_dir():
                    full_logs = candidate
                    break
            else:
                return []

        paths: list[str] = []
        for child in sorted(full_logs.iterdir()):
            if not child.is_dir():
                continue
            ws = child / "workspace"
            if ws.is_dir():
                paths.append(str(ws))
        return paths

    @staticmethod
    def format_multi_evaluator_result_block(
        all_answers: dict[str, str],
        auto_injected: bool = False,
    ) -> str:
        """Format multiple evaluator critiques as separate tagged blocks.

        Strips verdict_block JSON from each critique before injection so
        the parent reads the prose analysis only.
        """
        from .subagent.models import RoundEvaluatorResult

        n = len(all_answers)

        if auto_injected:
            instructions = (
                "Improvement tasks have been auto-injected into your task plan.\n"
                "Call `get_task_plan` to see them. Implement each task, then call `new_answer`.\n"
                "Do NOT call `submit_checklist` or `draft_approach` — already handled."
            )
        else:
            instructions = (
                "You received independent critiques from multiple evaluators.\n"
                "Synthesize them yourself:\n"
                "1. Read ALL critiques — each evaluator catches different issues.\n"
                "2. For each criterion, adopt the HARSHEST score across evaluators.\n"
                "3. Collect ALL unique concrete findings — even if only one evaluator mentions them.\n"
                "4. When evaluators flag the SAME issue, merge into one finding:\n"
                "   keep the most specific description, harshest severity, and\n"
                "   combine distinct evidence.\n"
                "5. Build one unified improvement plan from the combined findings.\n"
                "6. Save the synthesized diagnostic to your workspace\n"
                "   (e.g., tasks/diagnostic_report.md), then call `submit_checklist`\n"
                "   with that path as report_path.\n"
                "Do NOT discard findings just because other evaluators missed them.\n"
                "Do NOT average scores — use the lowest (harshest) per criterion.\n\n"
                "IMPORTANT: If any critique below is short or references a workspace\n"
                "file (e.g., 'refer to critique_packet.md'), browse that evaluator's\n"
                "workspace to read the full report. You have read-only access to all\n"
                "evaluator workspaces. Do NOT skip a thin answer — the real critique\n"
                "may be in the workspace."
            )

        parts = [
            "============================================================",
            f"ROUND EVALUATOR RESULTS ({n} independent evaluations)",
            "============================================================",
            instructions,
            "",
        ]

        for label, critique_text in all_answers.items():
            # Strip verdict_block from injected text (scores visible in prose)
            clean_text = RoundEvaluatorResult.strip_verdict_block(critique_text)
            parts.append(f'<evaluator_packet evaluator="{label}">')
            parts.append(clean_text)
            parts.append("</evaluator_packet>")
            parts.append("")

        parts.append("============================================================")
        return "\n".join(parts)

    @staticmethod
    def build_task_plan_from_evaluator_verdict(
        evaluator_result: "RoundEvaluatorResult",
    ) -> list[dict]:
        """Convert evaluator verdict improvements/preserve into a task_plan.

        Returns a list in the same format as ``evaluate_draft_approach()``
        output, ready for ``_write_inject_file()``.
        """
        if evaluator_result.verdict != "iterate":
            return []

        structured_next_tasks = evaluator_result.normalize_next_tasks_payload(
            evaluator_result.next_tasks,
        )
        if structured_next_tasks:
            task_plan = copy.deepcopy(structured_next_tasks.get("tasks", []))
            if evaluator_result.preserve:
                task_plan.append(
                    {
                        "type": "verify_preserve",
                        "description": ("Verify preserved strengths haven't regressed and that earlier " "correctness fixes still pass after later changes"),
                        "execution": {"mode": "inline"},
                        "items": [
                            {
                                "criterion_id": p.get("criterion_id", ""),
                                "what": p.get("what", ""),
                                "source": p.get("source", ""),
                            }
                            for p in evaluator_result.preserve
                        ],
                    },
                )
            return task_plan

        if not evaluator_result.improvements:
            return []

        task_plan: list[dict] = []

        # Opportunities (explore tasks) come first — they represent independent
        # ideas the evaluator identified that could be a leap forward, not just
        # corrections.  Placing them before improve tasks encourages the parent
        # to consider creative directions before falling back to patching.
        if evaluator_result.opportunities:
            for opp in evaluator_result.opportunities:
                task_plan.append(
                    {
                        "type": "explore",
                        "idea": opp.get("idea", ""),
                        "rationale": opp.get("rationale", ""),
                        "impact": opp.get("impact", "transformative"),
                        "relates_to": opp.get("relates_to", []),
                        "execution": {"mode": "delegate", "subagent_type": "builder"},
                    },
                )

        for imp in evaluator_result.improvements:
            entry: dict = {
                "type": "improve",
                "criterion_id": imp.get("criterion_id", ""),
                "criterion": imp.get("verification", ""),
                "plan": imp.get("plan", ""),
                "impact": imp.get("impact", "incremental"),
                "sources": imp.get("sources", []),
            }
            detail = imp.get("detail", "")
            if detail:
                entry["detail"] = detail
            if entry["impact"] in ("structural", "transformative"):
                entry["execution"] = {"mode": "delegate", "subagent_type": "builder"}
            else:
                entry["execution"] = {"mode": "inline"}
            task_plan.append(entry)

        if evaluator_result.preserve:
            task_plan.append(
                {
                    "type": "verify_preserve",
                    "description": ("Verify preserved strengths haven't regressed and that earlier " "correctness fixes still pass after later changes"),
                    "execution": {"mode": "inline"},
                    "items": [
                        {
                            "criterion_id": p.get("criterion_id", ""),
                            "what": p.get("what", ""),
                            "source": p.get("source", ""),
                        }
                        for p in evaluator_result.preserve
                    ],
                },
            )

        return task_plan

    def _handle_round_evaluator_gate_failure(
        self,
        *,
        parent_agent_id: str,
        latest_labels: tuple[str, ...],
        display_round: int,
        emitter: Any,
        elapsed_seconds: float,
        failure_payload: dict[str, Any] | None,
    ) -> bool | str:
        """Record a failed evaluator launch and decide whether to retry or abort."""
        failure_key = (parent_agent_id, latest_labels)
        attempt_number = self._round_evaluator_launch_failures.get(failure_key, 0) + 1
        self._round_evaluator_launch_failures[failure_key] = attempt_number

        payload = failure_payload if isinstance(failure_payload, dict) else {}
        error_message = str(
            payload.get("error") or payload.get("output") or "round_evaluator gate failed before producing a packet",
        ).strip()

        logger.warning(
            "[Orchestrator] round_evaluator gate failed for %s on attempt %s/%s: %s",
            parent_agent_id,
            attempt_number,
            self._ROUND_EVALUATOR_MAX_LAUNCH_FAILURES,
            error_message,
        )

        if emitter:
            emitter.emit_raw(
                StructuredEventType.ROUND_EVALUATOR_STAGE_COMPLETE,
                agent_id=parent_agent_id,
                round_number=display_round,
                status="error",
                execution_time_seconds=elapsed_seconds,
                packet_text_length=0,
                error=error_message,
            )

        if attempt_number < self._ROUND_EVALUATOR_MAX_LAUNCH_FAILURES:
            return False

        terminal_message = "Managed round evaluator failed " f"{attempt_number} time(s) for the current answer set. Last error: {error_message}"
        agent_state = self.agent_states.get(parent_agent_id)
        if agent_state is not None:
            agent_state.is_killed = True
            agent_state.error_reason = terminal_message
        self.coordination_tracker.track_agent_action(
            parent_agent_id,
            ActionType.ERROR,
            terminal_message,
        )
        return "terminal_error"

    def _handle_round_evaluator_timeout_degraded(
        self,
        *,
        parent_agent_id: str,
        latest_labels: tuple[str, ...],
        display_round: int,
        emitter: Any,
        elapsed_seconds: float,
        first_result: "SubagentResult",
        evaluator_result: "RoundEvaluatorResult",
    ) -> bool:
        """Allow coordination to continue when the evaluator timed out without a packet."""
        timeout_message = str(
            evaluator_result.error or first_result.error or "round_evaluator timed out before producing a packet",
        ).strip()

        logger.warning(
            "[Orchestrator] round_evaluator timed out for %s without artifacts; degrading to normal checklist flow: %s",
            parent_agent_id,
            timeout_message,
        )

        if emitter:
            emitter.emit_raw(
                StructuredEventType.ROUND_EVALUATOR_STAGE_COMPLETE,
                agent_id=parent_agent_id,
                round_number=display_round,
                status="degraded",
                execution_time_seconds=elapsed_seconds,
                packet_text_length=0,
                error=timeout_message,
            )

        self._queue_round_start_context_block(
            parent_agent_id,
            self._format_round_evaluator_timeout_block_static(
                first_result.subagent_id,
                timeout_message,
            ),
        )
        self._round_evaluator_launch_failures.pop((parent_agent_id, latest_labels), None)
        self._round_evaluator_completed_labels[parent_agent_id] = latest_labels
        return True

    @staticmethod
    def _split_combined_spawn_result(
        combined: dict[str, Any],
        evaluator_subagent_id: str,
        trace_subagent_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Split a combined spawn result into separate evaluator and trace dicts.

        When the round_evaluator and execution_trace_analyzer are spawned in a
        single ``spawn_subagents`` call the result payload contains entries for
        both.  This helper partitions them by matching ``subagent_id`` so that
        downstream processing can handle each independently.

        Returns:
            (evaluator_result_dict, trace_result_dict) — each shaped like a
            top-level spawn result with ``success``, ``results``, etc.
        """
        results = combined.get("results") or []
        eval_results: list[dict[str, Any]] = []
        trace_results: list[dict[str, Any]] = []
        for entry in results:
            sid = entry.get("subagent_id", "")
            if sid == trace_subagent_id:
                trace_results.append(entry)
            else:
                eval_results.append(entry)

        base = {k: v for k, v in combined.items() if k != "results"}
        eval_dict = {**base, "results": eval_results}
        trace_dict = {
            **base,
            "success": bool(trace_results),
            "results": trace_results,
        }
        return eval_dict, trace_dict

    @staticmethod
    def _format_trace_analyzer_for_memory_static(
        trace_result: "SubagentResult",
        round_number: int,
    ) -> str | None:
        """Format execution trace analyzer output as a memory block.

        The output starts with YAML frontmatter so the filesystem-based memory
        parser can pick it up automatically.
        """
        report_text = trace_result.answer or ""
        if not report_text.strip():
            return None

        frontmatter = "---\n" f"name: execution_trace_round_{round_number}\n" f"description: Process learnings from round {round_number}" " execution trace analysis\n" "tier: short_term\n" "---\n"
        return f"{frontmatter}\n{report_text}"

    @staticmethod
    def _strip_memory_frontmatter(content: str) -> str:
        """Return the body of a memory file, dropping YAML frontmatter when present."""
        normalized = content.strip()
        if not normalized.startswith("---"):
            return normalized

        lines = normalized.splitlines()
        if not lines or lines[0].strip() != "---":
            return normalized

        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                body = "\n".join(lines[index + 1 :]).strip()
                return body or normalized

        return normalized

    def _build_trace_analysis_injection_text(
        self,
        round_number: int,
        content: str,
    ) -> str | None:
        """Build the mid-stream injection payload for trace-analysis guidance."""
        body = self._strip_memory_frontmatter(content)
        if not body:
            return None

        return f"Trace analysis completed for round {round_number - 1}. " f"Apply this execution-process guidance immediately in round {round_number}.\n\n" f"{body}"

    def _build_trace_analysis_injection_result(
        self,
        trace_result: "SubagentResult",
        round_number: int,
        artifact_path: Path | None,
    ) -> Optional["SubagentResult"]:
        """Build the result payload queued for background injection."""
        injection_text: str | None = None

        if artifact_path is not None:
            try:
                artifact_content = artifact_path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning(
                    "[Orchestrator] Failed to read trace analysis artifact for injection %s: %s",
                    artifact_path,
                    exc,
                )
            else:
                injection_text = self._build_trace_analysis_injection_text(
                    round_number,
                    artifact_content,
                )

        if not injection_text and trace_result.answer:
            injection_text = self._build_trace_analysis_injection_text(
                round_number,
                trace_result.answer,
            )

        if not injection_text:
            return None

        return trace_result.__class__(
            subagent_id=trace_result.subagent_id,
            status=trace_result.status,
            success=trace_result.success,
            answer=injection_text,
            workspace_path=trace_result.workspace_path,
            execution_time_seconds=trace_result.execution_time_seconds,
            error=trace_result.error,
            token_usage=copy.deepcopy(trace_result.token_usage),
            log_path=trace_result.log_path,
            completion_percentage=trace_result.completion_percentage,
            warning=trace_result.warning,
        )

    @staticmethod
    def _get_trace_analysis_memory_filename(round_number: int) -> str:
        """Return the canonical short-term memory filename for trace analysis."""
        return f"trace_analysis_round_{round_number}.md"

    @classmethod
    def _candidate_trace_analysis_artifact_paths(
        cls,
        workspace_path: str | os.PathLike[str] | None,
        round_number: int,
    ) -> list[Path]:
        """Return likely locations for the analyzer's authoritative memory artifact."""
        if not workspace_path:
            return []

        filename = cls._get_trace_analysis_memory_filename(round_number)
        workspace = Path(workspace_path)
        candidates: list[tuple[int, float, Path]] = []
        seen: set[str] = set()

        def _add(path: Path, priority: int) -> None:
            if not path.exists() or not path.is_file():
                return
            try:
                key = str(path.resolve())
            except OSError:
                key = str(path)
            if key in seen:
                return
            seen.add(key)
            try:
                mtime = path.stat().st_mtime
            except OSError:
                mtime = 0.0
            candidates.append((priority, -mtime, path))

        _add(workspace / "deliverable" / filename, priority=0)
        _add(workspace / filename, priority=5)

        for pattern, priority in (
            (f"agent_*/deliverable/{filename}", 10),
            (f"agent_*/{filename}", 15),
            (f".massgen/sessions/*/turn_*/workspace/deliverable/{filename}", 20),
            (f".massgen/sessions/*/turn_*/workspace/{filename}", 25),
            (f".massgen/massgen_logs/*/turn_*/final/*/workspace/deliverable/{filename}", 30),
            (f".massgen/massgen_logs/*/turn_*/final/*/workspace/{filename}", 35),
        ):
            for candidate in workspace.glob(pattern):
                _add(candidate, priority=priority)

        candidates.sort(key=lambda item: (item[0], item[1], str(item[2])))
        return [path for _, _, path in candidates]

    @classmethod
    def _resolve_trace_analysis_artifact_path(
        cls,
        workspace_path: str | os.PathLike[str] | None,
        round_number: int,
    ) -> Path | None:
        """Return the first non-empty trace-analysis artifact with memory frontmatter."""
        for candidate in cls._candidate_trace_analysis_artifact_paths(
            workspace_path=workspace_path,
            round_number=round_number,
        ):
            try:
                content = candidate.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning(
                    "[Orchestrator] Failed to read trace analysis artifact %s: %s",
                    candidate,
                    exc,
                )
                continue

            stripped = content.strip()
            if not stripped:
                logger.warning(
                    "[Orchestrator] Trace analysis artifact is empty at %s",
                    candidate,
                )
                continue
            if not stripped.startswith("---") or "tier: short_term" not in content or "name:" not in content:
                logger.warning(
                    "[Orchestrator] Trace analysis artifact at %s is missing required memory frontmatter",
                    candidate,
                )
                continue
            return candidate

        return None

    # ------------------------------------------------------------------
    # Auto trace analysis (background execution_trace_analyzer)
    # ------------------------------------------------------------------

    def _should_spawn_trace_analyzer(self, agent_id: str) -> bool:
        """Return True if auto_trace_analysis should spawn for this agent."""
        coord = getattr(self.config, "coordination_config", None)
        if not coord:
            return False
        if not getattr(coord, "auto_trace_analysis", False):
            return False
        # Must be round 2+ (restart_count >= 1)
        state = self.agent_states.get(agent_id)
        if not state or getattr(state, "restart_count", 0) < 1:
            return False
        # Must not already have an in-flight trace task
        existing = self._background_trace_tasks.get(agent_id)
        if existing and not existing.done():
            return False
        return True

    def _get_execution_trace_path_for_agent(self, agent_id: str) -> Path | None:
        """Return the path to the latest execution_trace.md, or None."""
        agent = self.agents.get(agent_id)
        if not agent:
            return None
        fs_mgr = getattr(
            getattr(agent, "backend", None),
            "filesystem_manager",
            None,
        )
        if not fs_mgr or not fs_mgr.snapshot_storage:
            return None
        trace_path = fs_mgr.snapshot_storage / "execution_trace.md"
        return trace_path if trace_path.exists() else None

    def _get_execution_trace_context_path_for_agent(
        self,
        agent_id: str,
        temp_workspace_path: str | os.PathLike[str] | None = None,
    ) -> Path | None:
        """Return a subagent-readable execution trace path for the agent.

        Direct-spawned subagents can only read files mounted from the parent
        workspace and the agent temp-workspace shared-reference tree. The raw
        snapshot_storage path may exist on the host but still fail subagent
        validation if passed directly, so prefer the temp-workspace copy.
        """
        snapshot_trace = self._get_execution_trace_path_for_agent(agent_id)
        if not snapshot_trace:
            return None

        temp_roots: list[Path] = []

        if temp_workspace_path:
            temp_roots.append(Path(temp_workspace_path))

        agent = self.agents.get(agent_id)
        fs_mgr = getattr(
            getattr(agent, "backend", None),
            "filesystem_manager",
            None,
        )
        for candidate_root in (
            getattr(fs_mgr, "agent_temporary_workspace", None),
            getattr(self, "_agent_temporary_workspace", None),
        ):
            if candidate_root:
                temp_roots.append(Path(candidate_root))

        anon_id = agent_id
        tracker = getattr(self, "coordination_tracker", None)
        if tracker and hasattr(tracker, "get_reverse_agent_mapping"):
            try:
                anon_id = tracker.get_reverse_agent_mapping().get(agent_id, agent_id)
            except Exception:
                anon_id = agent_id

        seen: set[Path] = set()
        for temp_root in temp_roots:
            try:
                resolved_root = temp_root.resolve()
            except OSError:
                continue
            if resolved_root in seen:
                continue
            seen.add(resolved_root)
            trace_path = resolved_root / anon_id / "execution_trace.md"
            if trace_path.exists():
                return trace_path

        return None

    def _build_trace_analyzer_task(
        self,
        agent_id: str,
        round_number: int,
        trace_path: str,
    ) -> str:
        """Build the task string for the execution_trace_analyzer subagent."""
        original_task = getattr(self, "_original_task", None) or getattr(self, "current_task", None) or "Task coordination"
        memory_filename = self._get_trace_analysis_memory_filename(round_number)
        memory_artifact_path = f"deliverable/{memory_filename}"
        frontmatter = "---\n" f"name: execution_trace_round_{round_number}\n" f"description: Process learnings from round {round_number} execution trace analysis\n" "tier: short_term\n" "---"
        return (
            f"Analyze the execution trace from round {round_number - 1} "
            "and extract specific DO/DON'T guidance about the agent's "
            "EXECUTION PROCESS for the next round.\n\n"
            f"ORIGINAL TASK (for context only):\n{original_task}\n\n"
            f"The execution trace file is at: {trace_path}\n"
            "Read it and analyze HOW the agent worked — tool strategy, "
            "wasted effort, wrong assumptions, missing context gathering, "
            "backtracking, scope drift. Do NOT critique the deliverable "
            "quality (that is the round_evaluator's job). Focus on "
            "behavioral patterns that cost time or led the agent in "
            "wrong directions.\n\n"
            "Authoritative output contract:\n"
            f"1. If `deliverable/` does not exist in your workspace, create it.\n"
            f"2. Write the final memory artifact to `{memory_artifact_path}`.\n"
            "3. That file will be copied directly into the parent agent's "
            "`memory/short_term/`, so it must already contain valid YAML "
            "frontmatter exactly like this:\n"
            f"{frontmatter}\n\n"
            "4. After writing the file, keep your answer text brief: say "
            "whether you created the file and state its path. Do not paste "
            "the full report into the answer.\n\n"
            "Criticality rules:\n"
            "- Be skeptical. Bias toward DON'T / CRITICAL ERRORS unless the "
            "trace clearly proves a behavior helped.\n"
            "- Only put an item in `DO` when the trace shows direct evidence "
            "that it worked (for example: successful verification, later reuse "
            "without rollback, or avoided repeated failure).\n"
            "- If an action was merely attempted, completed once without proof, "
            "or only seems plausible, Do NOT promote it to `DO`.\n"
            "- If nothing is confidently confirmed, say so explicitly under "
            "`DO` instead of inventing a positive.\n"
            "- Every item must cite specific trace evidence: tool names, file "
            "paths, repeated commands, or exact error messages.\n\n"
            "Use the DO / DON'T / CRITICAL ERRORS section format from your "
            "instructions inside the artifact."
        )

    def _write_trace_analysis_to_memory(
        self,
        agent_id: str,
        round_number: int,
        memory_block: str,
    ) -> None:
        """Write trace analysis to agent's memory/short_term/ directory."""
        agent = self.agents.get(agent_id)
        if not agent:
            return
        fs_mgr = getattr(getattr(agent, "backend", None), "filesystem_manager", None)
        if not fs_mgr or not fs_mgr.cwd:
            return
        memory_dir = fs_mgr.cwd / "memory" / "short_term"
        try:
            memory_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return
        target = memory_dir / self._get_trace_analysis_memory_filename(round_number)
        try:
            target.write_text(memory_block, encoding="utf-8")
            logger.info(
                "[Orchestrator] Wrote trace analysis to %s for %s",
                target,
                agent_id,
            )
        except OSError as exc:
            logger.warning("[Orchestrator] Failed to write trace analysis memory: %s", exc)

    def _copy_trace_analysis_artifact_to_memory(
        self,
        agent_id: str,
        round_number: int,
        source_path: Path,
    ) -> None:
        """Copy the authoritative trace-analysis artifact into short-term memory."""
        agent = self.agents.get(agent_id)
        if not agent:
            return
        fs_mgr = getattr(getattr(agent, "backend", None), "filesystem_manager", None)
        if not fs_mgr or not fs_mgr.cwd:
            return
        memory_dir = fs_mgr.cwd / "memory" / "short_term"
        try:
            memory_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return

        target = memory_dir / self._get_trace_analysis_memory_filename(round_number)
        try:
            if source_path.resolve() == target.resolve():
                return
        except OSError:
            pass

        try:
            shutil.copy2(source_path, target)
            logger.info(
                "[Orchestrator] Copied trace analysis artifact %s to %s for %s",
                source_path,
                target,
                agent_id,
            )
        except OSError as exc:
            logger.warning("[Orchestrator] Failed to copy trace analysis artifact to memory: %s", exc)

    async def _run_trace_analyzer(
        self,
        parent_agent_id: str,
        round_number: int,
        trace_path: Path,
    ) -> None:
        """Background worker: spawn trace analyzer and process result."""
        from .subagent.models import SubagentResult

        subagent_id = f"trace_analyzer_{parent_agent_id}_r{round_number}"
        # Default 5 min, capped at half of subsequent_round_timeout_seconds
        trace_timeout = 300
        coord = getattr(self.config, "coordination_config", None)
        timeout_cfg = getattr(self.config, "timeout_config", None)
        subsequent_timeout = getattr(timeout_cfg, "subsequent_round_timeout_seconds", None)
        if not subsequent_timeout and coord:
            subsequent_timeout = getattr(coord, "subsequent_round_timeout_seconds", None)
        if subsequent_timeout and subsequent_timeout > 0:
            trace_timeout = min(trace_timeout, int(subsequent_timeout // 2))

        task_payload: dict[str, Any] = {
            "subagent_id": subagent_id,
            "task": self._build_trace_analyzer_task(
                parent_agent_id,
                round_number,
                str(trace_path),
            ),
            "subagent_type": "execution_trace_analyzer",
            "timeout_seconds": trace_timeout,
            "context_paths": [str(trace_path)],
        }

        tool_call_id = f"trace_analyzer_{parent_agent_id}_r{round_number}" f"_{int(time.time() * 1000)}"
        display_round = self._get_round_evaluator_display_round(parent_agent_id) if hasattr(self, "_get_round_evaluator_display_round") else round_number

        # Emit TUI spawn event
        self._emit_round_evaluator_spawn_event(
            phase="start",
            agent_id=parent_agent_id,
            tool_call_id=tool_call_id,
            round_number=display_round,
            args={"tasks": [task_payload], "background": True},
        )

        started_at = time.time()
        try:
            raw_result = await self._direct_spawn_subagents(
                parent_agent_id=parent_agent_id,
                tasks=[task_payload],
                refine=False,
            )
        except asyncio.CancelledError:
            elapsed = time.time() - started_at
            self._emit_round_evaluator_spawn_event(
                phase="complete",
                agent_id=parent_agent_id,
                tool_call_id=tool_call_id,
                round_number=display_round,
                args={"tasks": [task_payload], "background": True},
                result={"success": False, "error": "cancelled"},
                elapsed_seconds=elapsed,
                is_error=True,
                status="cancelled",
            )
            return

        elapsed = time.time() - started_at
        normalized = raw_result if isinstance(raw_result, dict) else {}
        success = bool(normalized.get("success"))

        self._emit_round_evaluator_spawn_event(
            phase="complete",
            agent_id=parent_agent_id,
            tool_call_id=tool_call_id,
            round_number=display_round,
            args={"tasks": [task_payload], "background": True},
            result=normalized,
            elapsed_seconds=elapsed,
            is_error=not success,
            status="success" if success else "error",
        )

        # Parse result
        results = normalized.get("results")
        if not isinstance(results, list) or not results:
            error = normalized.get("error", "")
            summary = normalized.get("summary", {})
            logger.warning(
                "[Orchestrator] Trace analyzer for %s r%d returned no results "
                "(success=%s, error=%s, summary=%s). "
                "Check that 'execution_trace_analyzer' is in subagent_types "
                "and its SUBAGENT.md is written to the workspace.",
                parent_agent_id,
                round_number,
                success,
                error,
                summary,
            )
            return

        try:
            trace_result = SubagentResult.from_dict(results[0])
        except Exception:
            logger.warning(
                "[Orchestrator] Failed to parse trace analyzer result for %s",
                parent_agent_id,
                exc_info=True,
            )
            return

        artifact_path = self._resolve_trace_analysis_artifact_path(
            workspace_path=trace_result.workspace_path,
            round_number=round_number,
        )
        if artifact_path:
            self._copy_trace_analysis_artifact_to_memory(
                parent_agent_id,
                round_number,
                artifact_path,
            )
        else:
            logger.warning(
                "[Orchestrator] Trace analyzer for %s r%d produced no authoritative artifact; " "falling back to answer text for memory persistence",
                parent_agent_id,
                round_number,
            )
            memory_block = self._format_trace_analyzer_for_memory_static(
                trace_result,
                round_number,
            )
            if memory_block:
                self._write_trace_analysis_to_memory(
                    parent_agent_id,
                    round_number,
                    memory_block,
                )

        # Enqueue the completed guidance so the running parent can receive it
        # immediately via the existing subagent-completion injection path.
        injection_result = self._build_trace_analysis_injection_result(
            trace_result,
            round_number,
            artifact_path=artifact_path,
        )
        if injection_result is not None:
            self._on_background_subagent_complete(
                parent_agent_id,
                subagent_id,
                injection_result,
            )

    async def _spawn_trace_analyzer_background(
        self,
        parent_agent_id: str,
    ) -> None:
        """Spawn background trace analyzer for the given agent at round 2+."""
        state = self.agent_states.get(parent_agent_id)
        restart_count = getattr(state, "restart_count", 0) if state else 0
        round_number = max(1, restart_count + 1)

        snapshot_trace_path = self._get_execution_trace_path_for_agent(parent_agent_id)
        if not snapshot_trace_path:
            logger.debug(
                "[Orchestrator] No execution trace available for %s, " "skipping trace analyzer",
                parent_agent_id,
            )
            return

        temp_workspace_path = await self._copy_all_snapshots_to_temp_workspace(parent_agent_id)
        trace_path = self._get_execution_trace_context_path_for_agent(
            parent_agent_id,
            temp_workspace_path=temp_workspace_path,
        )
        if not trace_path:
            logger.warning(
                "[Orchestrator] Execution trace exists for %s at %s but no " "subagent-readable temp-workspace copy was available; " "skipping trace analyzer",
                parent_agent_id,
                snapshot_trace_path,
            )
            return

        # Pre-flight: verify execution_trace_analyzer type dir exists in the
        # workspace so the spawn doesn't silently produce empty results.
        agent = self.agents.get(parent_agent_id)
        fs_mgr = getattr(getattr(agent, "backend", None), "filesystem_manager", None)
        if fs_mgr and fs_mgr.cwd:
            type_dir = Path(fs_mgr.cwd) / ".massgen" / "subagent_types" / "execution_trace_analyzer"
            if not type_dir.exists():
                # Write it now — may have been missing from DEFAULT_SUBAGENT_TYPES
                self._write_subagent_type_dirs(Path(fs_mgr.cwd))
                if not type_dir.exists():
                    logger.warning(
                        "[Orchestrator] execution_trace_analyzer type dir " "not found in workspace for %s — skipping. " "Add 'execution_trace_analyzer' to subagent_types " "in coordination config.",
                        parent_agent_id,
                    )
                    return

        task = asyncio.create_task(
            self._run_trace_analyzer(
                parent_agent_id,
                round_number,
                trace_path,
            ),
            name=f"trace_analyzer_{parent_agent_id}_r{round_number}",
        )
        self._background_trace_tasks[parent_agent_id] = task
        logger.info(
            "[Orchestrator] Spawned background trace analyzer for %s r%d",
            parent_agent_id,
            round_number,
        )

    # ------------------------------------------------------------------
    # Evolving evaluation criteria
    # ------------------------------------------------------------------

    def _bootstrap_evolution_criteria_from_config(self) -> None:
        """Populate _generated_evaluation_criteria from whatever active criteria exist.

        Called when evolving_criteria is enabled but the evaluation_criteria_generator
        was not used. Converts inline, preset, or default checklist criteria into
        GeneratedCriterion objects so evolution has something to work with.
        """
        items, cats, verify_by, source, anti_patterns, score_anchors = self._resolve_effective_checklist_criteria()
        if not items:
            return

        from .evaluation_criteria_generator import GeneratedCriterion

        # Build ID list from category dict keys (preserves original IDs)
        # or generate sequential IDs if categories are empty.
        if cats:
            id_list = list(cats.keys())
        else:
            id_list = [f"E{i + 1}" for i in range(len(items))]

        self._generated_evaluation_criteria = [
            GeneratedCriterion(
                id=id_list[i] if i < len(id_list) else f"E{i + 1}",
                text=text,
                category=(cats or {}).get(id_list[i] if i < len(id_list) else "", "standard"),
                verify_by=(verify_by or {}).get(id_list[i] if i < len(id_list) else ""),
                anti_patterns=(anti_patterns or {}).get(id_list[i] if i < len(id_list) else ""),
                score_anchors=(score_anchors or {}).get(id_list[i] if i < len(id_list) else ""),
            )
            for i, text in enumerate(items)
        ]

    def _should_evolve_criteria(self, current_answers: dict[str, str] | None = None) -> bool:
        """Return True if criteria evolution gate should run.

        Args:
            current_answers: Snapshot of current answers, used for idempotency
                tracking. When None, the idempotency check is skipped.
        """
        coord = getattr(self.config, "coordination_config", None)
        if not coord or not getattr(coord, "evolving_criteria", False):
            return False
        # Must have criteria to evolve — bootstrap from inline/preset if needed
        if not getattr(self, "_generated_evaluation_criteria", None):
            self._bootstrap_evolution_criteria_from_config()
        if not getattr(self, "_generated_evaluation_criteria", None):
            return False
        # Must be round 2+ — at least one agent must have answered once
        any_round2 = any(getattr(state, "restart_count", 0) >= 1 for state in self.agent_states.values())
        if not any_round2:
            return False
        # Hard cap on evolutions
        max_evolutions = getattr(coord, "evolving_criteria_max_evolutions", 2)
        if self._criteria_evolution_count >= max_evolutions:
            return False
        # Idempotency: check if we've already evolved for this exact set of answers
        if current_answers is not None:
            label_tuple = tuple(sorted(current_answers.keys()))
            if label_tuple in self._criteria_evolution_completed_labels:
                return False
        # Score threshold: at least N criteria scoring >= threshold in any agent
        threshold = getattr(coord, "evolving_criteria_score_threshold", 8)
        min_high = getattr(coord, "evolving_criteria_min_high_score_count", 2)
        high_count = 0
        for state in self.agent_states.values():
            history = getattr(state, "checklist_history", None) or []
            if not history:
                continue
            latest = history[-1]
            items_detail = latest.get("items_detail") or []
            for item in items_detail:
                score = item.get("score") or 0
                if score >= threshold:
                    high_count += 1
            if high_count >= min_high:
                return True
        return False

    def _collect_evolution_input_data(self) -> dict[str, Any]:
        """Gather all agents' execution trace paths and checklist histories."""
        histories: dict[str, list[dict[str, Any]]] = {}
        trace_paths: dict[str, Path | None] = {}

        for agent_id in self.agents:
            state = self.agent_states.get(agent_id)
            histories[agent_id] = list(getattr(state, "checklist_history", None) or [])
            raw = self._get_execution_trace_path_for_agent(agent_id)
            # snapshot_storage may be a relative Path; resolve to absolute so that
            # _preprocess_spawn_tasks does not mis-resolve it against workspace_root.
            trace_paths[agent_id] = raw.resolve() if raw is not None else None

        return {
            "trace_paths": trace_paths,
            "checklist_histories": histories,
            "current_criteria": list(self._generated_evaluation_criteria or []),
            "original_task": getattr(self, "_original_task", None) or "",
            "evolution_number": self._criteria_evolution_count + 1,
        }

    @staticmethod
    def _format_score_history_table(
        histories: dict[str, list[dict[str, Any]]],
    ) -> str:
        """Format per-agent score histories as a compact readable table."""
        lines: list[str] = []
        for agent_id, history in histories.items():
            lines.append(f"Agent {agent_id}:")
            if not history:
                lines.append("  (no history yet)")
                continue
            for round_idx, entry in enumerate(history, start=1):
                verdict = entry.get("verdict", "?")
                total = entry.get("total_score", "?")
                items = entry.get("items_detail") or []
                per_item = ", ".join(f"{it.get('id', '?')}={it.get('score', '?')}" for it in items)
                lines.append(f"  Round {round_idx}: verdict={verdict}, total={total}, scores=[{per_item}]")
        return "\n".join(lines)

    @staticmethod
    def _format_criteria_for_prompt(
        criteria: list[Any],
    ) -> str:
        """Format GeneratedCriterion list as a readable block for prompts."""
        lines: list[str] = []
        for c in criteria:
            lines.append(f"[{c.id}] ({getattr(c, 'category', 'standard')}) {c.text}")
            anti = getattr(c, "anti_patterns", None)
            if anti:
                lines.append(f"  Anti-patterns: {'; '.join(anti)}")
            anchors = getattr(c, "score_anchors", None)
            if anchors:
                for score_key in ("3", "5", "7", "9"):
                    if score_key in anchors:
                        lines.append(f"  {score_key}/10: {anchors[score_key]}")
        return "\n".join(lines)

    def _build_criteria_evolution_proposal_task(
        self,
        agent_id: str,
        evolution_data: dict[str, Any],
    ) -> str:
        """Build the task string for a criteria_evolver subagent."""
        original_task = evolution_data["original_task"]
        evolution_number = evolution_data["evolution_number"]
        criteria = evolution_data["current_criteria"]
        histories = evolution_data["checklist_histories"]
        trace_paths: dict[str, Path | None] = evolution_data["trace_paths"]

        criteria_block = self._format_criteria_for_prompt(criteria)
        score_table = self._format_score_history_table(histories)

        # Reference trace files by path — subagent reads them via its tools
        trace_lines: list[str] = []
        for aid, tpath in trace_paths.items():
            label = f"Agent {aid}" + (" (YOUR trace)" if aid == agent_id else "")
            if tpath:
                trace_lines.append(f"- {label}: read the file at `{tpath}`")
            else:
                trace_lines.append(f"- {label}: (no trace available for this agent)")
        trace_file_block = "\n".join(trace_lines)

        return (
            f"You are performing criteria evolution #{evolution_number} for a multi-agent task.\n\n"
            f"ORIGINAL TASK:\n{original_task}\n\n"
            f"CURRENT EVALUATION CRITERIA:\n{criteria_block}\n\n"
            f"CHECKLIST SCORE HISTORY (all agents, all rounds):\n{score_table}\n\n"
            "EXECUTION TRACES — read each file below using your file-reading tool:\n"
            f"{trace_file_block}\n\n"
            "Based on the score patterns and execution traces, propose evolved criteria that raise "
            "the bar on dimensions where agents are consistently scoring 8+ out of 10. "
            "Leave criteria that are still discriminating (showing score spread across agents) "
            "unchanged. Output JSON as described in your instructions."
        )

    def _build_criteria_evolution_synthesis_task(
        self,
        proposals: list[dict[str, Any]],
        current_criteria: list[Any],
        original_task: str,
    ) -> str:
        """Build the task string for the criteria_evolution_synthesizer subagent."""
        criteria_block = self._format_criteria_for_prompt(current_criteria)

        proposal_lines: list[str] = []
        for i, prop in enumerate(proposals, start=1):
            prop_json = json.dumps(prop, indent=2)
            proposal_lines.append(f"--- Proposal {i} ---\n{prop_json}")
        all_proposals = "\n\n".join(proposal_lines)

        return (
            f"ORIGINAL TASK:\n{original_task}\n\n"
            f"CURRENT CRITERIA:\n{criteria_block}\n\n"
            f"EVOLUTION PROPOSALS ({len(proposals)} total):\n{all_proposals}\n\n"
            "Synthesize these proposals into a single authoritative evolved criteria set. "
            "Apply the synthesis rules in your instructions and output JSON."
        )

    def _write_criteria_evolution_subagent_type_dirs(self, ws_root: Path) -> None:
        """Write criteria_evolver and criteria_evolution_synthesizer type dirs.

        These are orchestrator-internal types used only during the evolution gate.
        They are written directly to the spawn workspace and are NOT included in
        DEFAULT_SUBAGENT_TYPES, so agents cannot launch them via normal subagent calls.
        """
        import json as _json

        try:
            from massgen.subagent.type_scanner import scan_subagent_types

            evolution_types = scan_subagent_types(
                allowed_types=["criteria_evolver", "criteria_evolution_synthesizer"],
            )
            if not evolution_types:
                logger.warning(
                    "[Orchestrator] criteria_evolver / criteria_evolution_synthesizer "
                    "SUBAGENT.md files not found — criteria evolution subagents cannot run. "
                    "Check massgen/subagent_types/ for these directories.",
                )
                return
            subagent_types_dir = ws_root / ".massgen" / "subagent_types"
            subagent_types_dir.mkdir(parents=True, exist_ok=True)
            for t in evolution_types:
                type_dir = subagent_types_dir / t.name
                type_dir.mkdir(exist_ok=True)
                frontmatter = f"---\nname: {t.name}\ndescription: {_json.dumps(t.description)}\n"
                if t.expected_input:
                    frontmatter += f"expected_input: {_json.dumps(t.expected_input)}\n"
                frontmatter += "---\n"
                (type_dir / "SUBAGENT.md").write_text(frontmatter + t.system_prompt)
            logger.info(
                "[Orchestrator] Wrote %d criteria evolution type dirs to %s",
                len(evolution_types),
                subagent_types_dir,
            )
        except Exception:
            logger.warning(
                "[Orchestrator] Failed to write criteria evolution subagent type dirs",
                exc_info=True,
            )

    @staticmethod
    def _read_evolution_json_from_result(entry: dict[str, Any]) -> dict[str, Any] | None:
        """Read criteria-evolution JSON from a subagent result entry.

        Prefers the workspace file ``deliverable/evolved_criteria.json``
        (written by the subagent). Falls back to parsing the answer text.
        """
        # Prefer workspace file — search the same nested paths that
        # subagent workspaces use (inner agent dirs, snapshots, etc.)
        _FILENAME = "evolved_criteria.json"
        workspace = entry.get("workspace") or ""
        if workspace:
            ws = Path(workspace)
            candidates = [ws / "deliverable" / _FILENAME]
            for pattern in (
                f"agent_*/deliverable/{_FILENAME}",
                f"snapshots/*/*/deliverable/{_FILENAME}",
            ):
                candidates.extend(ws.glob(pattern))
            for candidate in candidates:
                if candidate.exists():
                    try:
                        data = json.loads(candidate.read_text(encoding="utf-8"))
                        if isinstance(data, dict):
                            return data
                    except Exception:
                        pass

        # Fall back to answer text
        answer_text = entry.get("answer") or ""
        if not answer_text:
            return None
        try:
            parsed = json.loads(answer_text)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
        # Try markdown fences
        for fence in ("```json", "```"):
            start = answer_text.find(fence)
            if start < 0:
                continue
            start += len(fence)
            end = answer_text.find("```", start)
            if end > start:
                try:
                    parsed = json.loads(answer_text[start:end].strip())
                    if isinstance(parsed, dict):
                        return parsed
                except (json.JSONDecodeError, ValueError):
                    pass
        return None

    async def _run_criteria_evolution_if_needed(
        self,
        answers: dict[str, str],
    ) -> bool:
        """Synchronous gate: evolve criteria between rounds if conditions are met.

        Returns True when ready to proceed. Returns False to signal the caller
        should wait and retry (same protocol as the round_evaluator gate).
        """
        if not self._should_evolve_criteria(current_answers=answers):
            return True

        coord = getattr(self.config, "coordination_config", None)
        timeout = getattr(coord, "evolving_criteria_timeout", 300)
        label_tuple = tuple(sorted(answers.keys()))

        logger.info(
            "[Orchestrator] Starting criteria evolution #%d for answer labels %s",
            self._criteria_evolution_count + 1,
            label_tuple,
        )

        evolution_data = self._collect_evolution_input_data()
        agent_ids = list(self.agents.keys())

        # Phase 1: Parallel proposals (one per agent perspective)
        # Pick a parent agent to own the spawn workspace
        primary_agent_id = agent_ids[0] if agent_ids else ""

        # Write criteria evolution subagent types directly to the spawn workspace.
        # These are orchestrator-internal — not in DEFAULT_SUBAGENT_TYPES — so agents
        # cannot launch them via normal subagent calls.
        primary_agent = self.agents.get(primary_agent_id)
        primary_fs_mgr = getattr(getattr(primary_agent, "backend", None), "filesystem_manager", None)
        if primary_fs_mgr and getattr(primary_fs_mgr, "cwd", None):
            self._write_criteria_evolution_subagent_type_dirs(Path(primary_fs_mgr.cwd))

        # Collect all trace paths for context_paths mounting
        all_trace_paths = [str(p) for p in evolution_data["trace_paths"].values() if p is not None]
        proposal_tasks: list[dict[str, Any]] = []
        for i, agent_id in enumerate(agent_ids):
            subagent_id = f"criteria_evolver_{self._criteria_evolution_count + 1}_{i}"
            task_str = self._build_criteria_evolution_proposal_task(agent_id, evolution_data)
            proposal_tasks.append(
                {
                    "subagent_id": subagent_id,
                    "task": task_str,
                    "subagent_type": "criteria_evolver",
                    "timeout_seconds": max(60, timeout // 2),
                    "context_paths": all_trace_paths,
                },
            )

        # Resolve display for TUI subagent cards
        display = getattr(self.coordination_ui, "display", None) if getattr(self, "coordination_ui", None) else None
        evo_num = self._criteria_evolution_count + 1
        proposal_call_id = f"criteria_evolution_{evo_num}_proposals"
        proposal_task_preview = f"Evolving criteria (v{evo_num}): analyzing score patterns across {len(agent_ids)} agent(s)"

        # Notify TUI: proposal phase started
        _proposal_subagent_id = proposal_tasks[0]["subagent_id"] if proposal_tasks else f"criteria_evolver_{evo_num}"
        try:
            _emitter = get_event_emitter()
            if _emitter:
                _emitter.emit_raw(
                    StructuredEventType.PRE_COLLAB_STARTED,
                    agent_id=primary_agent_id,
                    subagent_id=_proposal_subagent_id,
                    task=proposal_task_preview,
                    timeout_seconds=timeout,
                    call_id=proposal_call_id,
                    log_path=None,
                )
            if display and hasattr(display, "notify_runtime_subagent_started"):
                display.notify_runtime_subagent_started(
                    agent_id=primary_agent_id,
                    subagent_id=_proposal_subagent_id,
                    task=proposal_task_preview,
                    timeout_seconds=timeout,
                    call_id=proposal_call_id,
                    status_callback=None,
                    log_path=None,
                )
        except Exception:
            pass

        try:
            raw_proposals = await asyncio.wait_for(
                self._direct_spawn_subagents(
                    parent_agent_id=primary_agent_id,
                    tasks=proposal_tasks,
                    refine=False,
                ),
                timeout=timeout,
            )
        except TimeoutError:
            logger.warning("[Orchestrator] Criteria evolution proposals timed out; skipping")
            self._notify_precollab_completed(primary_agent_id, proposal_tasks[0]["subagent_id"] if proposal_tasks else "", proposal_call_id, display, status="timeout", error="timed out")
            self._criteria_evolution_completed_labels.add(label_tuple)
            return True
        except Exception:
            logger.warning("[Orchestrator] Criteria evolution proposals failed", exc_info=True)
            self._notify_precollab_completed(primary_agent_id, proposal_tasks[0]["subagent_id"] if proposal_tasks else "", proposal_call_id, display, status="error", error="spawn failed")
            self._criteria_evolution_completed_labels.add(label_tuple)
            return True

        # Parse proposal JSONs
        proposal_dicts: list[dict[str, Any]] = []
        results = (raw_proposals or {}).get("results") or []
        for entry in results:
            parsed = self._read_evolution_json_from_result(entry)
            if isinstance(parsed, dict):
                proposal_dicts.append(parsed)

        if not proposal_dicts:
            logger.warning("[Orchestrator] No valid criteria evolution proposals; skipping")
            self._notify_precollab_completed(
                primary_agent_id,
                proposal_tasks[0]["subagent_id"] if proposal_tasks else "",
                proposal_call_id,
                display,
                status="completed",
                answer_preview="No valid proposals",
            )
            self._criteria_evolution_completed_labels.add(label_tuple)
            return True

        # Notify TUI: proposal phase completed
        self._notify_precollab_completed(
            primary_agent_id,
            proposal_tasks[0]["subagent_id"] if proposal_tasks else "",
            proposal_call_id,
            display,
            status="completed",
            answer_preview=f"{len(proposal_dicts)} proposal(s) received",
        )

        # Phase 2: Synthesis
        synthesis_task_str = self._build_criteria_evolution_synthesis_task(
            proposal_dicts,
            evolution_data["current_criteria"],
            evolution_data["original_task"],
        )
        synthesis_subagent_id = f"criteria_evolution_synthesizer_{self._criteria_evolution_count + 1}"
        synthesis_call_id = f"criteria_evolution_{evo_num}_synthesis"
        synthesis_payload: list[dict[str, Any]] = [
            {
                "subagent_id": synthesis_subagent_id,
                "task": synthesis_task_str,
                "subagent_type": "criteria_evolution_synthesizer",
                "timeout_seconds": max(60, timeout // 3),
            },
        ]

        # Notify TUI: synthesis phase started
        _synth_task_preview = f"Synthesizing {len(proposal_dicts)} evolution proposal(s) into final criteria"
        try:
            _emitter = get_event_emitter()
            if _emitter:
                _emitter.emit_raw(
                    StructuredEventType.PRE_COLLAB_STARTED,
                    agent_id=primary_agent_id,
                    subagent_id=synthesis_subagent_id,
                    task=_synth_task_preview,
                    timeout_seconds=timeout // 2,
                    call_id=synthesis_call_id,
                    log_path=None,
                )
            if display and hasattr(display, "notify_runtime_subagent_started"):
                display.notify_runtime_subagent_started(
                    agent_id=primary_agent_id,
                    subagent_id=synthesis_subagent_id,
                    task=_synth_task_preview,
                    timeout_seconds=timeout // 2,
                    call_id=synthesis_call_id,
                    status_callback=None,
                    log_path=None,
                )
        except Exception:
            pass

        try:
            raw_synthesis = await asyncio.wait_for(
                self._direct_spawn_subagents(
                    parent_agent_id=primary_agent_id,
                    tasks=synthesis_payload,
                    refine=False,
                ),
                timeout=timeout // 2,
            )
        except TimeoutError:
            logger.warning("[Orchestrator] Criteria evolution synthesis timed out; skipping")
            self._notify_precollab_completed(primary_agent_id, synthesis_subagent_id, synthesis_call_id, display, status="timeout", error="timed out")
            self._criteria_evolution_completed_labels.add(label_tuple)
            return True
        except Exception:
            logger.warning("[Orchestrator] Criteria evolution synthesis failed", exc_info=True)
            self._notify_precollab_completed(primary_agent_id, synthesis_subagent_id, synthesis_call_id, display, status="error", error="spawn failed")
            self._criteria_evolution_completed_labels.add(label_tuple)
            return True

        # Parse synthesis result — prefer workspace file, fall back to answer text
        synth_results = (raw_synthesis or {}).get("results") or []
        synth_parsed = self._read_evolution_json_from_result(synth_results[0]) if synth_results else None
        synth_answer = json.dumps(synth_parsed) if synth_parsed else (synth_results[0].get("answer", "") if synth_results else "")

        from .evaluation_criteria_generator import parse_evolution_response

        evolved, summary, is_unchanged = parse_evolution_response(
            synth_answer,
            evolution_data["current_criteria"],
        )

        if is_unchanged:
            logger.info(
                "[Orchestrator] Criteria evolution synthesizer returned UNCHANGED; criteria are still effective",
            )
            self._notify_precollab_completed(primary_agent_id, synthesis_subagent_id, synthesis_call_id, display, status="completed", answer_preview="Criteria unchanged")
            self._criteria_evolution_completed_labels.add(label_tuple)
            return True

        if evolved is None:
            logger.warning("[Orchestrator] Failed to parse criteria evolution synthesis result; skipping")
            self._notify_precollab_completed(primary_agent_id, synthesis_subagent_id, synthesis_call_id, display, status="completed", answer_preview="Parse failed")
            self._criteria_evolution_completed_labels.add(label_tuple)
            return True

        # Notify TUI: synthesis completed successfully
        evolved_count = sum(1 for old_c, new_c in zip(evolution_data["current_criteria"], evolved) if old_c.text != new_c.text)
        self._notify_precollab_completed(
            primary_agent_id,
            synthesis_subagent_id,
            synthesis_call_id,
            display,
            status="completed",
            answer_preview=f"{evolved_count} criteria evolved",
        )

        # Apply evolved criteria
        old_criteria = list(evolution_data["current_criteria"])
        self._criteria_evolution_history.append(
            {
                "evolution_number": self._criteria_evolution_count + 1,
                "old_criteria": [{"id": c.id, "text": c.text} for c in old_criteria],
                "new_criteria": [{"id": c.id, "text": c.text} for c in evolved],
                "summary": summary,
            },
        )
        self._generated_evaluation_criteria = evolved
        self._evaluation_criteria_generated = True
        self._criteria_evolution_count += 1
        self._criteria_evolution_completed_labels.add(label_tuple)

        # Re-initialize checklist tool with new criteria
        try:
            self._init_checklist_tool()
        except Exception:
            logger.warning("[Orchestrator] Failed to re-init checklist tool after criteria evolution", exc_info=True)

        # Emit event + push updated criteria to TUI
        try:
            _emitter = get_event_emitter()
            evolved_count = sum(1 for old_c, new_c in zip(old_criteria, evolved) if old_c.text != new_c.text)
            if _emitter:
                _emitter.emit_raw(
                    StructuredEventType.EVALUATION_CRITERIA_EVOLVED,
                    evolution_number=self._criteria_evolution_count,
                    evolved_count=evolved_count,
                    total_count=len(evolved),
                    summary=summary or "",
                )
            # Re-push updated criteria so Ctrl+E shows the evolved set
            evolved_payload = [{"id": c.id, "text": c.text, "category": getattr(c, "category", "standard")} for c in evolved]
            if _emitter:
                _emitter.emit_raw(
                    StructuredEventType.EVALUATION_CRITERIA_SET,
                    criteria=evolved_payload,
                    source=f"evolved_v{self._criteria_evolution_count}",
                )
            display = getattr(self.coordination_ui, "display", None) if self.coordination_ui else None
            if display and hasattr(display, "set_evaluation_criteria"):
                display.set_evaluation_criteria(
                    evolved_payload,
                    source=f"evolved_v{self._criteria_evolution_count}",
                )
        except Exception:
            pass

        # Write memory to each agent
        self._write_criteria_evolution_memory(
            evolution_number=self._criteria_evolution_count,
            old_criteria=old_criteria,
            new_criteria=evolved,
            summary=summary,
        )

        # Queue round-start context block for each agent
        if summary:
            context_block = (
                f"[CRITERIA EVOLVED — round {self._criteria_evolution_count}]\n\n"
                f"{summary}\n\n"
                "The evaluation criteria have been updated based on your performance. "
                "Score your next answer against the NEW criteria visible in your checklist tool."
            )
            for agent_id in self.agents:
                self._queue_round_start_context_block(agent_id, context_block)

        logger.info(
            "[Orchestrator] Criteria evolved (evolution #%d): %d criteria updated",
            self._criteria_evolution_count,
            len(evolved),
        )
        return True

    def _write_criteria_evolution_memory(
        self,
        evolution_number: int,
        old_criteria: list[Any],
        new_criteria: list[Any],
        summary: str | None,
    ) -> None:
        """Write criteria evolution summary to each agent's short-term memory."""
        # Build diff block
        diff_lines: list[str] = []
        old_by_id = {c.id: c for c in old_criteria}
        for c in new_criteria:
            old = old_by_id.get(c.id)
            if old and old.text != c.text:
                diff_lines.append(f"**{c.id} (evolved)**")
                diff_lines.append(f"  Before: {old.text}")
                diff_lines.append(f"  After:  {c.text}")
            else:
                diff_lines.append(f"**{c.id} (unchanged)** {c.text}")

        diff_block = "\n".join(diff_lines)
        summary_block = summary or "Criteria evolved to raise the bar based on agent score trends."

        memory_block = (
            "---\n"
            f"name: criteria_evolution_{evolution_number}\n"
            f"description: Evaluation criteria evolved in round {evolution_number} — new bar is higher\n"
            "tier: short_term\n"
            "---\n\n"
            f"## Criteria Evolution #{evolution_number}\n\n"
            f"{summary_block}\n\n"
            "### What Changed\n\n"
            f"{diff_block}\n\n"
            "Score your NEXT answer against the NEW criteria above. "
            "The previous scores are no longer the benchmark — the bar has moved."
        )

        for agent_id, agent in self.agents.items():
            fs_mgr = getattr(getattr(agent, "backend", None), "filesystem_manager", None)
            if not fs_mgr or not getattr(fs_mgr, "cwd", None):
                continue
            memory_dir = fs_mgr.cwd / "memory" / "short_term"
            try:
                memory_dir.mkdir(parents=True, exist_ok=True)
                target = memory_dir / f"criteria_evolution_{evolution_number}.md"
                target.write_text(memory_block, encoding="utf-8")
                logger.info(
                    "[Orchestrator] Wrote criteria evolution memory to %s for %s",
                    target,
                    agent_id,
                )
            except OSError as exc:
                logger.warning(
                    "[Orchestrator] Failed to write criteria evolution memory for %s: %s",
                    agent_id,
                    exc,
                )

    async def _run_round_evaluator_pre_round_if_needed(
        self,
        answers: dict[str, str],
        conversation_context: dict[str, Any] | None = None,
    ) -> bool | str:
        """Run the round_evaluator gate between answer rounds when configured."""
        _ = conversation_context
        if not self._is_round_evaluator_gate_enabled():
            return True
        if not answers:
            return True
        if len(self.agents) != 1:
            return True
        if not all(state.answer is not None for state in self.agent_states.values()):
            return True

        parent_agent_id = next(iter(self.agents.keys()))
        latest_labels = self._get_round_evaluator_latest_labels(answers)
        if not latest_labels:
            return True
        if self._round_evaluator_completed_labels.get(parent_agent_id) == latest_labels:
            return True

        upcoming_round = self._get_round_evaluator_upcoming_round(parent_agent_id)
        display_round = self._get_round_evaluator_display_round(parent_agent_id)
        self._set_round_evaluator_task_mode(parent_agent_id, enabled=False)

        # Subagent type dirs and CONTEXT.md are written by
        # _direct_spawn_subagents into the parent agent's workspace.

        temp_workspace_path = await self._copy_all_snapshots_to_temp_workspace(parent_agent_id)
        coord_cfg = getattr(self.config, "coordination_config", None)
        evaluator_refine = bool(coord_cfg and getattr(coord_cfg, "round_evaluator_refine", False))
        spawn_task = self._build_round_evaluator_task(parent_agent_id, answers)
        spawn_context_paths = self._get_round_evaluator_context_paths(
            parent_agent_id,
            temp_workspace_path=temp_workspace_path,
        )
        pressure_label = getattr(coord_cfg, "round_evaluator_transformation_pressure", "balanced") or "balanced"
        display_subagent_type = f"round_evaluator·{pressure_label}" if pressure_label != "balanced" else "round_evaluator"
        configured_timeout = getattr(coord_cfg, "subagent_default_timeout", 300) if coord_cfg else 300
        task_payload: dict[str, Any] = {
            "subagent_id": f"round_eval_r{upcoming_round}",
            "task": spawn_task,
            "subagent_type": "round_evaluator",
            "context_paths": spawn_context_paths,
            "timeout_seconds": configured_timeout,
        }
        # Sync stdio checklist state so personas written by the stdio
        # set_evaluator_personas tool are available to the orchestrator.
        self._sync_stdio_checklist_state_from_specs(parent_agent_id)
        # Inject evaluator personas if configured by the main agent.
        consumed_personas = self._consume_evaluator_personas()
        if consumed_personas:
            task_payload["metadata"] = {"evaluator_personas": consumed_personas}
        spawn_args: dict[str, Any] = {
            "tasks": [task_payload],
            "background": False,
            "refine": evaluator_refine,
        }

        # TUI display args use the decorated type label so the card shows the pressure level.
        tui_task_payload = {**task_payload, "subagent_type": display_subagent_type}

        tui_spawn_args = {**spawn_args, "tasks": [tui_task_payload]}

        tool_call_id = f"round_evaluator_pre_round_{parent_agent_id}_r{upcoming_round}_{int(time.time() * 1000)}"
        emitter = get_event_emitter()
        if emitter:
            emitter.emit_raw(
                StructuredEventType.ROUND_EVALUATOR_STAGE_START,
                agent_id=parent_agent_id,
                round_number=display_round,
            )
        self._emit_round_evaluator_spawn_event(
            phase="start",
            agent_id=parent_agent_id,
            tool_call_id=tool_call_id,
            round_number=display_round,
            args=tui_spawn_args,
        )

        # --- Direct spawn (bypasses MCP routing entirely) ---
        # The orchestrator owns this spawn decision, so calling SubagentManager
        # directly is simpler and avoids requiring the parent agent to have an
        # MCP-connected subagent server (which depends on filesystem_manager).
        started_at = time.time()
        raw_result = await self._direct_spawn_subagents(
            parent_agent_id=parent_agent_id,
            tasks=[task_payload],
            refine=evaluator_refine,
        )
        elapsed_seconds = max(0.0, time.time() - started_at)
        normalized_result = raw_result if isinstance(raw_result, dict) else {}
        success = bool(normalized_result.get("success"))
        self._emit_round_evaluator_spawn_event(
            phase="complete",
            agent_id=parent_agent_id,
            tool_call_id=tool_call_id,
            round_number=display_round,
            args=spawn_args,
            result=normalized_result,
            elapsed_seconds=elapsed_seconds,
            is_error=not success,
            status="success" if success else "error",
        )

        # Notify TUI so subagent cards update to completed/failed status.
        # Without this, cards stay "running" indefinitely after cancellation.
        display = getattr(self.coordination_ui, "display", None) if self.coordination_ui else None
        if display and hasattr(display, "notify_runtime_subagent_completed"):
            try:
                display.notify_runtime_subagent_completed(
                    agent_id=parent_agent_id,
                    subagent_id=f"round_eval_r{upcoming_round}",
                    call_id=tool_call_id,
                    status="completed" if success else "failed",
                )
            except Exception:
                pass

        from .subagent.models import RoundEvaluatorResult, SubagentResult

        results = normalized_result.get("results")
        first_result: SubagentResult | None = None
        evaluator_result: RoundEvaluatorResult | None = None

        if not success:
            # Graceful degradation: the child MassGen run may have failed or
            # timed out, but the canonical recovery path (completed_but_timeout
            # / partial) may have salvaged an answer from the most recent
            # evaluator agent.  Check results before giving up.
            salvaged = False
            if isinstance(results, list) and results:
                try:
                    first_result = SubagentResult.from_dict(results[0])
                    if first_result.answer:
                        logger.info(
                            "[Orchestrator] round_evaluator spawn reported " "failure (status=%s) but first result has a " "recovered answer — using it for %s",
                            first_result.status,
                            parent_agent_id,
                        )
                        salvaged = True
                    else:
                        evaluator_result = RoundEvaluatorResult.from_subagent_result(
                            first_result,
                            elapsed=elapsed_seconds,
                        )
                        if evaluator_result.status == "success" and evaluator_result.packet_text:
                            logger.info(
                                "[Orchestrator] round_evaluator spawn reported failure (status=%s) but authoritative artifacts were recovered for %s",
                                first_result.status,
                                parent_agent_id,
                            )
                            salvaged = True
                        elif first_result.status == "timeout" and evaluator_result.status == "degraded":
                            degraded_ok = self._handle_round_evaluator_timeout_degraded(
                                parent_agent_id=parent_agent_id,
                                latest_labels=latest_labels,
                                display_round=display_round,
                                emitter=emitter,
                                elapsed_seconds=elapsed_seconds,
                                first_result=first_result,
                                evaluator_result=evaluator_result,
                            )
                            if degraded_ok is True and self._should_spawn_trace_analyzer(parent_agent_id):
                                await self._spawn_trace_analyzer_background(parent_agent_id)
                            return degraded_ok
                except Exception:
                    logger.warning(
                        "[Orchestrator] Failed to parse salvage result for %s",
                        parent_agent_id,
                        exc_info=True,
                    )

            if not salvaged:
                return self._handle_round_evaluator_gate_failure(
                    parent_agent_id=parent_agent_id,
                    latest_labels=latest_labels,
                    display_round=display_round,
                    emitter=emitter,
                    elapsed_seconds=elapsed_seconds,
                    failure_payload=normalized_result,
                )
        if not isinstance(results, list) or not results:
            return self._handle_round_evaluator_gate_failure(
                parent_agent_id=parent_agent_id,
                latest_labels=latest_labels,
                display_round=display_round,
                emitter=emitter,
                elapsed_seconds=elapsed_seconds,
                failure_payload={
                    "success": False,
                    "operation": "spawn_subagents",
                    "error": "round_evaluator returned no result payloads",
                },
            )

        try:
            first_result = first_result or SubagentResult.from_dict(results[0])
        except Exception as exc:
            return self._handle_round_evaluator_gate_failure(
                parent_agent_id=parent_agent_id,
                latest_labels=latest_labels,
                display_round=display_round,
                emitter=emitter,
                elapsed_seconds=elapsed_seconds,
                failure_payload={
                    "success": False,
                    "operation": "spawn_subagents",
                    "error": f"Failed to parse round_evaluator result payload: {exc}",
                },
            )

        evaluator_result = evaluator_result or RoundEvaluatorResult.from_subagent_result(
            first_result,
            elapsed=elapsed_seconds,
        )

        if evaluator_result.status != "success" or not evaluator_result.packet_text:
            return self._handle_round_evaluator_gate_failure(
                parent_agent_id=parent_agent_id,
                latest_labels=latest_labels,
                display_round=display_round,
                emitter=emitter,
                elapsed_seconds=elapsed_seconds,
                failure_payload={
                    "success": False,
                    "operation": "spawn_subagents",
                    "error": evaluator_result.error or "round_evaluator produced no packet",
                },
            )

        auto_injected = False
        if evaluator_result.verdict == "iterate" and evaluator_result.task_plan_source == "next_tasks_artifact":
            task_plan = self.build_task_plan_from_evaluator_verdict(evaluator_result)
            if task_plan:
                self._write_planning_injection(parent_agent_id, task_plan)
                auto_injected = True
                logger.info(
                    f"[Orchestrator] Auto-injected {len(task_plan)} tasks from evaluator next_tasks artifact for {parent_agent_id}",
                )
        elif evaluator_result.verdict == "iterate":
            logger.info(
                "[Orchestrator] Evaluator requested iteration for %s without a valid next_tasks.json artifact; using checklist fallback",
                parent_agent_id,
            )
        elif evaluator_result.verdict == "converged":
            logger.info(
                "[Orchestrator] Evaluator verdict: converged for %s",
                parent_agent_id,
            )
        else:
            logger.debug(
                "[Orchestrator] Missing or invalid verdict.json for %s; using checklist fallback",
                parent_agent_id,
            )

        # Store evolved prompt if evaluator produced one
        if evaluator_result.evolved_prompt:
            self._evolved_prompts[parent_agent_id] = evaluator_result.evolved_prompt
            logger.info(
                f"[Orchestrator] Evolved prompt stored for {parent_agent_id} "
                f"({len(evaluator_result.evolved_prompt)} chars, "
                f"rationale: {(evaluator_result.evolved_prompt_rationale or '')[:100]})",
            )
            # Notify TUI so the session info modal shows the evolved prompt
            _display = getattr(self.coordination_ui, "display", None) if self.coordination_ui else None
            if _display and hasattr(_display, "notify_prompt_improved"):
                try:
                    _display.notify_prompt_improved(evaluator_result.evolved_prompt)
                except Exception:
                    pass

        self._set_round_evaluator_task_mode(
            parent_agent_id,
            enabled=auto_injected,
            primary_artifact_path=evaluator_result.primary_artifact_path or "",
            verdict_artifact_path=evaluator_result.verdict_artifact_path or "",
            next_tasks_artifact_path=evaluator_result.next_tasks_artifact_path or "",
            objective=evaluator_result.next_tasks_objective or "",
            primary_strategy=evaluator_result.next_tasks_primary_strategy or "",
            why_this_strategy=evaluator_result.next_tasks_why_this_strategy or "",
            strategy_mode=evaluator_result.next_tasks_strategy_mode or "",
            incremental_override_reason=evaluator_result.next_tasks_incremental_override_reason or "",
            success_contract=evaluator_result.next_tasks_success_contract or {},
            deprioritize_or_remove=evaluator_result.next_tasks_deprioritize_or_remove or [],
        )

        self._queue_round_start_context_block(
            parent_agent_id,
            self._format_round_evaluator_result_block(
                first_result.subagent_id,
                evaluator_result,
                auto_injected=auto_injected,
            ),
        )

        # Add evaluator workspace as read-only context path so the
        # parent can read critique_packet.md / verdict.json / next_tasks.json.
        if first_result.workspace_path:
            parent_agent = self.agents.get(parent_agent_id)
            if parent_agent and hasattr(parent_agent, "backend"):
                fs_mgr = getattr(parent_agent.backend, "filesystem_manager", None)
                if fs_mgr:
                    ppm = getattr(fs_mgr, "path_permission_manager", None)
                    if ppm:
                        ppm.add_context_paths([{"path": first_result.workspace_path, "permission": "read"}])
                        logger.info(
                            f"[Orchestrator] Added evaluator workspace as read-only context for {parent_agent_id}: {first_result.workspace_path}",
                        )

        if emitter:
            emitter.emit_raw(
                StructuredEventType.ROUND_EVALUATOR_STAGE_COMPLETE,
                agent_id=parent_agent_id,
                round_number=display_round,
                status=evaluator_result.status,
                execution_time_seconds=elapsed_seconds,
                packet_text_length=len(evaluator_result.packet_text or ""),
            )

        self._round_evaluator_launch_failures.pop((parent_agent_id, latest_labels), None)
        self._round_evaluator_completed_labels[parent_agent_id] = latest_labels

        # Auto-spawn background trace analyzer for the upcoming round.
        if self._should_spawn_trace_analyzer(parent_agent_id):
            await self._spawn_trace_analyzer_background(parent_agent_id)

        return True

    def _get_buffer_content(self, agent: "ChatAgent") -> tuple[str | None, int]:
        """Get streaming buffer content from agent backend for enforcement tracking.

        Returns:
            Tuple of (buffer_preview: first 500 chars or None, buffer_chars: total char count)
        """
        buffer_content = None
        buffer_chars = 0

        if hasattr(agent.backend, "_get_streaming_buffer"):
            buffer_content = agent.backend._get_streaming_buffer()
            if buffer_content:
                buffer_chars = len(buffer_content)
                # Truncate preview to 500 chars
                buffer_content = buffer_content[:500] if len(buffer_content) > 500 else buffer_content

        return buffer_content, buffer_chars

    def _truncate_enforcement_buffer_content(self, buffer_content: str | None) -> str | None:
        """Bound enforcement retry buffer size to avoid prompt blowups."""
        if not buffer_content:
            return None

        normalized = buffer_content.strip()
        if not normalized:
            return None

        max_chars = self._ENFORCEMENT_RETRY_BUFFER_MAX_CHARS
        if len(normalized) <= max_chars:
            return normalized

        kept = normalized[:max_chars]
        removed = len(normalized) - len(kept)
        return f"[... earlier retry context truncated ({removed} chars removed); " f"showing first {len(kept)} chars ...]\n" f"{kept}"

    def _save_docker_logs_on_mcp_failure(
        self,
        agent: "ChatAgent",
        agent_id: str,
        mcp_status: str,
    ) -> None:
        """Save Docker container logs when MCP failure is detected.

        This helps debug why Docker-based MCP servers disconnect by capturing
        container state and logs at the time of failure.

        Args:
            agent: The ChatAgent instance.
            agent_id: Agent identifier.
            mcp_status: The MCP status that triggered this (e.g., 'mcp_tools_failed').
        """
        try:
            # Check if agent uses Docker mode
            if not hasattr(agent, "backend") or not hasattr(
                agent.backend,
                "filesystem_manager",
            ):
                return

            fm = agent.backend.filesystem_manager
            if not fm or not hasattr(fm, "docker_manager") or not fm.docker_manager:
                return

            docker_manager = fm.docker_manager

            # Get container health info
            health = docker_manager.get_container_health(agent_id)
            if not health.get("exists"):
                logger.warning(
                    f"[Docker] Container not found for {agent_id} during MCP failure - may have been cleaned up",
                )
                return

            # Log container health status
            logger.info(
                f"[Docker] Container health for {agent_id} during MCP failure ({mcp_status}): "
                f"status={health.get('status')}, running={health.get('running')}, "
                f"exit_code={health.get('exit_code')}, oom_killed={health.get('oom_killed')}, "
                f"error={health.get('error')}",
            )

            # Save logs to the session log directory
            from .logger_config import get_log_session_dir

            log_dir = get_log_session_dir()
            if log_dir:
                import time

                timestamp = time.strftime("%H%M%S")
                log_filename = f"docker_logs_{agent_id}_{mcp_status}_{timestamp}.txt"
                log_path = log_dir / log_filename
                docker_manager.save_container_logs(agent_id, log_path, tail=500)

        except (OSError, AttributeError, KeyError) as e:
            # OSError: File I/O errors when saving logs
            # AttributeError: Missing attributes on agent/backend/manager objects
            # KeyError: Missing dict keys in health info
            logger.warning(
                f"[Docker] Failed to save container logs on MCP failure: {e}",
            )

    def _get_docker_health(
        self,
        agent: "ChatAgent",
        agent_id: str,
    ) -> dict[str, Any] | None:
        """Get Docker container health info for reliability metrics.

        Args:
            agent: The ChatAgent instance.
            agent_id: Agent identifier.

        Returns:
            Docker health dict or None if not using Docker.
        """
        try:
            if not hasattr(agent, "backend") or not hasattr(
                agent.backend,
                "filesystem_manager",
            ):
                return None

            fm = agent.backend.filesystem_manager
            if not fm or not hasattr(fm, "docker_manager") or not fm.docker_manager:
                return None

            return fm.docker_manager.get_container_health(agent_id)
        except (AttributeError, KeyError) as e:
            # AttributeError: Missing attributes on agent/backend/manager objects
            # KeyError: Missing dict keys when accessing container state
            logger.debug(f"[Docker] Failed to get container health: {e}")
            return None

    def _create_tool_error_messages(
        self,
        agent: "ChatAgent",
        tool_calls: list[dict[str, Any]],
        primary_error_msg: str,
        secondary_error_msg: str = None,
    ) -> list[dict[str, Any]]:
        """
        Create tool error messages for all tool calls in a response.

        Args:
            agent: The ChatAgent instance for backend access
            tool_calls: List of tool calls that need error responses
            primary_error_msg: Error message for the first tool call
            secondary_error_msg: Error message for additional tool calls (defaults to primary_error_msg)

        Returns:
            List of tool result messages that can be sent back to the agent
        """
        if not tool_calls:
            return []

        if secondary_error_msg is None:
            secondary_error_msg = primary_error_msg

        enforcement_msgs = []

        # Send primary error for the first tool call
        first_tool_call = tool_calls[0]
        error_result_msg = agent.backend.create_tool_result_message(
            first_tool_call,
            primary_error_msg,
        )
        # Handle both single dict (Chat Completions) and list (Response API) returns
        if isinstance(error_result_msg, list):
            enforcement_msgs.extend(error_result_msg)
        else:
            enforcement_msgs.append(error_result_msg)

        # Send secondary error messages for any additional tool calls (API requires response to ALL calls)
        for additional_tool_call in tool_calls[1:]:
            neutral_msg = agent.backend.create_tool_result_message(
                additional_tool_call,
                secondary_error_msg,
            )
            # Handle both single dict (Chat Completions) and list (Response API) returns
            if isinstance(neutral_msg, list):
                enforcement_msgs.extend(neutral_msg)
            else:
                enforcement_msgs.append(neutral_msg)

        return enforcement_msgs

    def _split_disallowed_workflow_tool_calls(
        self,
        agent: "ChatAgent",
        tool_calls: list[dict[str, Any]],
        allowed_workflow_tool_names: set[str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        """Split tool calls into allowed and disallowed workflow calls for this round.

        Args:
            agent: Agent used to extract tool names from backend-specific call objects.
            tool_calls: Raw tool calls returned by model/backend.
            allowed_workflow_tool_names: Workflow tools available in this round.

        Returns:
            Tuple of:
            - allowed_calls: Calls that can be processed this round
            - disallowed_calls: Workflow calls not available this round
            - disallowed_names: Ordered list of disallowed workflow tool names
        """
        allowed_calls: list[dict[str, Any]] = []
        disallowed_calls: list[dict[str, Any]] = []
        disallowed_names: list[str] = []

        for tool_call in tool_calls:
            tool_name = agent.backend.extract_tool_name(tool_call)
            if tool_name in WORKFLOW_TOOL_NAMES and tool_name not in allowed_workflow_tool_names:
                disallowed_calls.append(tool_call)
                disallowed_names.append(tool_name)
                continue
            allowed_calls.append(tool_call)

        return allowed_calls, disallowed_calls, disallowed_names

    def _load_rate_limits_from_config(self) -> dict[str, dict[str, int]]:
        """
        Load rate limits from centralized configuration file.

        Converts RPM (Requests Per Minute) values from rate_limits.yaml
        into agent startup rate limits for the orchestrator.

        Returns:
            Dictionary mapping model names to rate limit configs:
            {"model-name": {"max_starts": N, "time_window": 60}}
        """
        rate_limits = {}

        try:
            config = get_rate_limit_config()

            # Load Gemini models
            gemini_models = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini"]
            for model in gemini_models:
                limits = config.get_limits("gemini", model, use_defaults=True)
                rpm = limits.get("rpm")

                if rpm:
                    # Use RPM directly as max_starts for conservative limiting
                    # For very limited models (rpm <= 2), be extra conservative
                    if rpm <= 2:
                        max_starts = 1  # Very conservative for Pro (actual: 2 RPM)
                    elif rpm <= 10:
                        max_starts = max(1, rpm - 1)  # Conservative buffer
                    else:
                        max_starts = rpm

                    rate_limits[model] = {
                        "max_starts": max_starts,
                        "time_window": 60,  # Always use 60s window (1 minute)
                    }
                    logger.info(
                        f"[Orchestrator] Loaded rate limit for {model}: " f"{max_starts} starts/min (from RPM: {rpm})",
                    )

            # Fallback defaults if config loading failed
            if not rate_limits:
                logger.warning(
                    "[Orchestrator] No rate limits loaded from config, using fallback defaults",
                )
                rate_limits = {
                    "gemini-2.5-flash": {"max_starts": 9, "time_window": 60},
                    "gemini-2.5-pro": {"max_starts": 2, "time_window": 60},
                    "gemini": {"max_starts": 7, "time_window": 60},
                }

        except Exception as e:
            logger.error(f"[Orchestrator] Failed to load rate limits from config: {e}")
            # Fallback to safe defaults
            rate_limits = {
                "gemini-2.5-flash": {"max_starts": 9, "time_window": 60},
                "gemini-2.5-pro": {"max_starts": 2, "time_window": 60},
                "gemini": {"max_starts": 7, "time_window": 60},
            }

        return rate_limits

    async def _apply_agent_startup_rate_limit(self, agent_id: str) -> None:
        """
        Apply rate limiting for agent startup based on model.

        Ensures that agents using rate-limited models (like Gemini Flash/Pro)
        don't exceed the allowed startup rate.

        Args:
            agent_id: ID of the agent to start
        """
        # Skip rate limiting if not enabled
        if not self._enable_rate_limit:
            return

        agent = self.agents.get(agent_id)
        if not agent or not hasattr(agent, "backend"):
            return

        # Get model name from backend config
        model_key = None
        if hasattr(agent.backend, "config") and isinstance(agent.backend.config, dict):
            model_name = agent.backend.config.get("model", "")
            # Check for specific models first
            if "gemini-2.5-flash" in model_name.lower():
                model_key = "gemini-2.5-flash"
            elif "gemini-2.5-pro" in model_name.lower():
                model_key = "gemini-2.5-pro"
            elif "gemini" in model_name.lower():
                model_key = "gemini"

        # Fallback: try backend type
        if not model_key:
            if hasattr(agent.backend, "get_provider_name"):
                backend_type = agent.backend.get_provider_name()
                if backend_type in self._rate_limits:
                    model_key = backend_type

        # Check if this model has rate limits
        if not model_key or model_key not in self._rate_limits:
            return

        rate_limit = self._rate_limits[model_key]
        max_starts = rate_limit["max_starts"]
        time_window = rate_limit["time_window"]

        # Initialize tracking for this model if needed
        if model_key not in self._agent_startup_times:
            self._agent_startup_times[model_key] = []

        current_time = time.time()
        startup_times = self._agent_startup_times[model_key]

        # Remove timestamps outside the current window
        startup_times[:] = [t for t in startup_times if t > current_time - time_window]

        # If we've hit the limit, wait until the oldest startup falls outside the window
        if len(startup_times) >= max_starts:
            oldest_time = startup_times[0]
            wait_time = (oldest_time + time_window) - current_time

            if wait_time > 0:
                log_orchestrator_activity(
                    self.orchestrator_id,
                    f"Rate limit reached for {model_key}",
                    {
                        "agent_id": agent_id,
                        "model": model_key,
                        "current_starts": len(startup_times),
                        "max_starts": max_starts,
                        "time_window": time_window,
                        "wait_time": round(wait_time, 2),
                    },
                )
                logger.info(
                    f"[Orchestrator] Rate limit: {len(startup_times)}/{max_starts} {model_key} agents " f"started in {time_window}s window. Waiting {wait_time:.2f}s before starting {agent_id}...",
                )

                await asyncio.sleep(wait_time)

                # After waiting, clean up old timestamps again
                current_time = time.time()
                startup_times[:] = [t for t in startup_times if t > current_time - time_window]

        # Record this startup
        startup_times.append(time.time())

        log_orchestrator_activity(
            self.orchestrator_id,
            "Agent startup allowed",
            {
                "agent_id": agent_id,
                "model": model_key,
                "current_starts": len(startup_times),
                "max_starts": max_starts,
            },
        )

        # Add mandatory cooldown after startup to prevent burst API calls
        # This gives the backend rate limiter time to properly queue requests
        cooldown_delays = {
            "gemini-2.5-flash": 3.0,  # 3 second cooldown between Flash agent starts
            "gemini-2.5-pro": 10.0,  # 10 second cooldown between Pro agent starts (very limited!)
            "gemini": 5.0,  # 5 second default cooldown
        }

        if model_key in cooldown_delays:
            cooldown = cooldown_delays[model_key]
            logger.info(
                f"[Orchestrator] Applying {cooldown}s cooldown after starting {agent_id} ({model_key})",
            )
            await asyncio.sleep(cooldown)

    async def _stream_agent_execution(
        self,
        agent_id: str,
        task: str,
        answers: dict[str, str],
        conversation_context: dict[str, Any] | None = None,
        paraphrase: str | None = None,
    ) -> AsyncGenerator[tuple, None]:
        """
        Stream agent execution with real-time content and final result.

        Yields:
            ("content", str): Real-time agent output (source attribution added by caller)
            ("result", (type, data)): Final result - ("vote", vote_data) or ("answer", content)
            ("external_tool_calls", List[Dict]): Client-provided tool calls that must be surfaced externally (not executed)
            ("error", str): Error message (self-terminating)
            ("done", None): Graceful completion signal

        Restart Behavior:
            If restart_pending is True, agent gracefully terminates with "done" signal.
            restart_pending is cleared at the beginning of execution.
        """
        from massgen.mcp_tools.hooks import InjectionDeliveryStatus

        agent = self.agents[agent_id]

        # Get backend name for logging
        backend_name = None
        if hasattr(agent, "backend") and hasattr(agent.backend, "get_provider_name"):
            backend_name = agent.backend.get_provider_name()

        log_orchestrator_activity(
            self.orchestrator_id,
            f"Starting agent execution: {agent_id}",
            {
                "agent_id": agent_id,
                "backend": backend_name,
                "task": task if task else None,
                "paraphrased_task": paraphrase,
                "agent_view_task": paraphrase or task,
                "has_answers": bool(answers),
                "num_answers": len(answers) if answers else 0,
            },
        )

        # Add periodic heartbeat logging for stuck agents
        paraphrase_note = " (with DSPy paraphrased question)" if paraphrase else ""
        logger.info(
            f"[Orchestrator] Agent {agent_id} starting execution loop...{paraphrase_note}",
        )

        # Initialize agent state
        self.agent_states[agent_id].is_killed = False
        self.agent_states[agent_id].timeout_reason = None
        self.agent_states[agent_id].error_reason = None
        self.agent_states[agent_id].midstream_injections_this_round = 0

        # Track whether we've notified TUI of new round (done once per real execution)
        _notified_round = False
        _mid_stream_injection = False

        # Set round start time for per-round timeout tracking
        self.agent_states[agent_id].round_start_time = time.time()

        # Reset timeout hooks if they exist (for new round after restart)
        if self.agent_states[agent_id].round_timeout_hooks:
            post_hook, pre_hook = self.agent_states[agent_id].round_timeout_hooks
            post_hook.reset_for_new_round()
            pre_hook.reset_for_new_round()
            logger.debug(f"[Orchestrator] Reset round timeout hooks for {agent_id}")

        # Clean up any background shells from the previous round
        await self._cleanup_background_shells_for_agent(agent_id)

        # Note: Do NOT clear restart_pending here - let the injection logic inside the iteration
        # loop handle it (see line ~1969). This ensures agents receive updates via injection
        # instead of restarting from scratch, even if they haven't started streaming yet.
        # The injection logic will:
        # - Inject new answers if they exist (and continue working)
        # - Clear the flag if no new answers exist (agent already has full context)

        # Copy all agents' snapshots to temp workspace for context sharing.
        # Non-fatal: transient permission errors should not abort the round.
        try:
            await self._copy_all_snapshots_to_temp_workspace(agent_id)
        except OSError as e:
            logger.warning(
                f"[Orchestrator] Failed to copy snapshots to temp workspace for {agent_id}: {e} — continuing without shared context",
            )

        # Clear the agent's workspace to prepare for new execution
        # This preserves the previous agent's output for logging while giving a clean slate
        if agent.backend.filesystem_manager:
            # agent.backend.filesystem_manager.clear_workspace()  # Don't clear for now.
            agent.backend.filesystem_manager.log_current_state("before execution")

            # Re-write SUBAGENT.md dirs and MCP config JSON files each round so
            # the lazy scanner / deferred loader in the MCP server always finds
            # them — workspace clears between rounds can remove .massgen/.
            if hasattr(self.config, "coordination_config") and getattr(self.config.coordination_config, "enable_subagents", False):
                workspace_root = agent.backend.filesystem_manager.get_workspace_root()
                self._write_subagent_type_dirs(workspace_root)
                self._rewrite_subagent_mcp_config_files(workspace_root, agent_id)

            # For single-agent mode with skip_voting (refinement OFF), enable context write access
            # from the START of coordination so the agent can write directly to context paths
            if self.config.skip_voting and self._has_write_context_paths(agent):
                logger.info(
                    f"[Orchestrator] Single-agent mode: enabling context write access from start for {agent_id}",
                )
                # Snapshot BEFORE enabling writes (to track what gets written)
                agent.backend.filesystem_manager.path_permission_manager.snapshot_writable_context_paths()
                agent.backend.filesystem_manager.path_permission_manager.set_context_write_access_enabled(True)

        # Create agent execution span for hierarchical tracing in Logfire
        # This groups all tool calls, LLM calls, and events under this agent's execution
        tracer = get_tracer()
        current_round = self.coordination_tracker.get_agent_round(agent_id)
        context_labels = self.coordination_tracker.get_agent_context_labels(agent_id)
        if self._is_decomposition_mode():
            round_type = "decomposition_refinement" if answers else "decomposition_initial"
        else:
            round_type = "voting" if answers else "initial_answer"

        # Emit round_start event for UI display (round banners)
        # Use _agent_display_round (monotonically increasing per agent) so every
        # execution — answer, vote, or final — gets a unique round number.
        display_round = self._agent_display_round.get(agent_id, -1) + 1
        self._agent_display_round[agent_id] = display_round

        event_emitter = get_event_emitter()
        if event_emitter:
            event_emitter.emit_round_start(round_number=display_round, agent_id=agent_id)

        span_attributes = {
            "massgen.agent_id": agent_id,
            "massgen.iteration": self.coordination_tracker.current_iteration,
            "massgen.round": current_round,
            "massgen.round_type": round_type,
            "massgen.backend": backend_name or "unknown",
            "massgen.num_context_answers": len(answers) if answers else 0,
        }
        if context_labels:
            span_attributes["massgen.context_labels"] = ",".join(context_labels)

        _agent_span_cm = tracer.span(
            f"agent.{agent_id}.round_{current_round}",
            attributes=span_attributes,
        )
        _agent_span = _agent_span_cm.__enter__()  # Capture the yielded span for set_attribute()

        # Set the round context for nested tool calls to use
        set_current_round(current_round, round_type)

        # Per-round worktree setup: create isolated worktree for this agent's round
        round_worktree_paths: dict[str, str] | None = None
        write_mode = None
        if self.config.coordination_config:
            write_mode = getattr(self.config.coordination_config, "write_mode", None)
        if write_mode and write_mode != "legacy" and agent.backend.filesystem_manager:
            # Defensive cleanup: if a previous round's isolation manager was
            # never cleaned up (e.g. the generator's finally block didn't run),
            # do it now before creating a new one.
            prev_iso = self._round_isolation_managers.pop(agent_id, None)
            if prev_iso is not None:
                for ctx_info in list(prev_iso.list_contexts()):
                    ctx_path = ctx_info.get("original_path") if ctx_info else None
                    if not ctx_path:
                        continue
                    try:
                        prev_iso.move_scratch_to_workspace(ctx_path)
                        prev_iso.cleanup_round(ctx_path)
                    except Exception as _err:
                        logger.warning(
                            f"[Orchestrator] Defensive round cleanup failed for {agent_id}: {_err}",
                        )
                self._round_worktree_paths.pop(agent_id, None)
                logger.info(
                    f"[Orchestrator] Cleaned up previous round isolation for {agent_id}",
                )

            try:
                from .filesystem_manager import IsolationContextManager

                workspace_path = str(agent.backend.filesystem_manager.get_current_workspace())

                # Check for explicit context paths and filter to writable ones
                # Read-only paths don't need worktree isolation
                ppm = agent.backend.filesystem_manager.path_permission_manager
                context_paths = ppm.get_context_paths() if ppm else []
                writable_context_paths = [cp for cp in context_paths if cp.get("will_be_writable", False)]

                # Skip isolation entirely if all context paths are read-only
                if context_paths and not writable_context_paths:
                    logger.info(
                        f"[Orchestrator] All context paths are read-only for {agent_id}, " "skipping per-round worktree isolation",
                    )
                else:
                    round_suffix = secrets.token_hex(4)
                    round_isolation_mgr = IsolationContextManager(
                        session_id=f"{self.session_id}-{round_suffix}",
                        write_mode=write_mode,
                        workspace_path=workspace_path,
                    )
                    round_worktree_paths = {}

                    if writable_context_paths:
                        # Create worktrees only for writable context paths
                        for ctx_config in writable_context_paths:
                            ctx_path = ctx_config.get("path", "")
                            if ctx_path:
                                isolated = round_isolation_mgr.initialize_context(ctx_path, agent_id)
                                round_worktree_paths[isolated] = ctx_path
                    else:
                        # No context paths at all: use workspace itself with scratch + branches
                        round_isolation_mgr.setup_workspace_scratch(workspace_path, agent_id)
                        round_worktree_paths[workspace_path] = workspace_path

                    # Track the new branch name
                    for ctx_info in round_isolation_mgr.list_contexts():
                        branch = ctx_info.get("branch_name") if ctx_info else None
                        if branch:
                            self._agent_current_branches[agent_id] = branch
                            break

                    # Store for cleanup in finally block
                    self._round_isolation_managers[agent_id] = round_isolation_mgr
                    self._round_worktree_paths[agent_id] = round_worktree_paths
                    logger.info(
                        f"[Orchestrator] Created per-round worktree for {agent_id}: {round_worktree_paths}",
                    )
            except Exception as e:
                logger.warning(f"[Orchestrator] Failed to create per-round worktree for {agent_id}: {e}")
                round_worktree_paths = None

        # Track outcome for span attributes (set in finally block)
        _agent_outcome = None  # "vote", "answer", or "error"
        _agent_voted_for = None  # Only set for votes
        _agent_answer_label = None  # Only set for answers (e.g., "agent1.1")
        _agent_voted_for_label = None  # Only set for votes (e.g., "agent2.1")
        _agent_error_message = None  # Only set for errors

        try:
            # Normalize workspace paths in agent answers for better comparison from this agent's perspective
            normalized_answers = self._normalize_workspace_paths_in_answers(answers, agent_id) if answers else answers

            # Log structured context for this agent's round (for observability/debugging)
            # Get agent's log directory path for hybrid access pattern (MAS-199)
            log_session_dir = get_log_session_dir()
            agent_log_path = str(log_session_dir / agent_id) if log_session_dir else None
            log_agent_round_context(
                agent_id=agent_id,
                round_number=current_round,
                round_type=round_type,
                answers_in_context=normalized_answers,
                answer_labels=context_labels,
                agent_log_path=agent_log_path,
            )

            # Log the normalized answers this agent will see
            if normalized_answers:
                logger.info(
                    f"[Orchestrator] Agent {agent_id} sees normalized answers: {normalized_answers}",
                )
            else:
                logger.info(f"[Orchestrator] Agent {agent_id} sees no existing answers")

            # Check if planning mode is enabled for coordination phase
            # Use the ACTUAL backend planning mode status (set by intelligent analysis)
            # instead of the static config setting
            is_coordination_phase = self.workflow_phase == "coordinating"
            planning_mode_enabled = agent.backend.is_planning_mode_enabled() if is_coordination_phase else False

            # Build new structured system message FIRST (before conversation building)
            logger.info(
                f"[Orchestrator] Building structured system message for {agent_id}",
            )
            # Get human Q&A history for context injection (human broadcast mode only)
            human_qa_history = None
            if hasattr(self, "broadcast_channel") and self.broadcast_channel:
                human_qa_history = self.broadcast_channel.get_human_qa_history()

            # Check if agent is in vote-only mode (reached max_new_answers_per_agent)
            # This affects both the system message and available tools
            vote_only_for_system_message = self._is_vote_only_mode(agent_id)
            if vote_only_for_system_message:
                logger.info(
                    f"[Orchestrator] Agent {agent_id} in vote-only mode for system message (answer limit reached)",
                )

            # Compute branch info for this agent's system prompt
            agent_branch = self._agent_current_branches.get(agent_id)
            # Map other agents' branches to anonymous IDs (e.g. {"agent1": "massgen/abc123"})
            _branch_agent_mapping = self.coordination_tracker.get_reverse_agent_mapping()
            other_agent_branches = {_branch_agent_mapping.get(aid, aid): branch for aid, branch in self._agent_current_branches.items() if aid != agent_id and branch}

            # Generate diff summaries for other agents' branches (passive code visibility)
            branch_diff_summaries = None
            if other_agent_branches and agent_id in self._round_isolation_managers:
                round_iso = self._round_isolation_managers[agent_id]
                branch_diff_summaries = round_iso.generate_branch_summaries(other_agent_branches)
                if branch_diff_summaries:
                    logger.info(f"[Orchestrator] Generated diff summaries for {agent_id}: {list(branch_diff_summaries.keys())}")

            # Compute novelty pressure data for system prompt
            novelty_injection = getattr(self.config.coordination_config, "novelty_injection", "none")
            novelty_data = None
            if novelty_injection != "none":
                is_converging, consecutive = self._detect_convergence(agent_id)
                restart_count = self.agent_states[agent_id].restart_count
                logger.info(
                    f"[Orchestrator] Novelty check for {agent_id}: "
                    f"mode={novelty_injection}, restart_count={restart_count}, "
                    f"is_converging={is_converging}, consecutive_incremental={consecutive}",
                )
                if novelty_injection == "aggressive" and restart_count > 0:
                    novelty_data = {"consecutive": consecutive, "restart_count": restart_count}
                elif is_converging:
                    novelty_data = {"consecutive": consecutive, "restart_count": restart_count}
                if novelty_data:
                    logger.info(f"[Orchestrator] Novelty pressure APPLIED for {agent_id}: {novelty_data}")
                else:
                    logger.info(
                        f"[Orchestrator] Novelty pressure NOT applied for {agent_id}: "
                        f"aggressive requires restart_count>0 (got {restart_count}), "
                        f"fallback requires is_converging=True (got {is_converging})",
                    )

            # Resolve active criteria once for both system prompt and checklist tool state.
            criteria_agent_id = agent_id if self._is_decomposition_mode() else None
            _active_items, _active_categories, _active_verify_by, _criteria_source, _active_anti_patterns, _active_score_anchors = self._resolve_effective_checklist_criteria(
                criteria_agent_id,
            )

            # Push criteria to TUI display on first round (non-checklist modes;
            # checklist_gated mode already pushes from _init_checklist_tool).
            should_refresh_criteria_display = not self._criteria_pushed_to_display or (
                self._is_decomposition_mode() and getattr(self.config, "voting_sensitivity", "") == "checklist_gated" and _criteria_source == "decomposition_subtask"
            )
            if should_refresh_criteria_display and _active_items:
                try:
                    _ui_display = getattr(self.coordination_ui, "display", None) if self.coordination_ui else None
                    _crit_dicts = [
                        {
                            "id": f"E{_i + 1}",
                            "text": _t,
                            "category": (_active_categories or {}).get(f"E{_i + 1}", "standard"),
                            "verify_by": (_active_verify_by or {}).get(f"E{_i + 1}"),
                        }
                        for _i, _t in enumerate(_active_items)
                    ]
                    _emitter = get_event_emitter()
                    if _emitter:
                        _emitter.emit_raw(
                            StructuredEventType.EVALUATION_CRITERIA_SET,
                            criteria=_crit_dicts,
                            source=_criteria_source,
                        )
                    if _ui_display and hasattr(_ui_display, "set_evaluation_criteria"):
                        _ui_display.set_evaluation_criteria(_crit_dicts, source=_criteria_source)
                        self._criteria_display_payload = {
                            "criteria": _crit_dicts,
                            "source": _criteria_source,
                        }
                        self._criteria_pushed_to_display = True
                except Exception:
                    pass  # TUI notification is non-critical

            # Check if essential files manifests exist for this round
            _essential_files_active = False
            if normalized_answers and current_round > 0 and self._snapshot_storage:
                _ef_base = Path(self._snapshot_storage)
                _essential_files_active = any((_ef_base / aid / "memory" / "short_term" / "essential_files_manifest.json").exists() for aid in self.agents)

            system_message = self._get_system_message_builder().build_coordination_message(
                agent=agent,
                agent_id=agent_id,
                answers=normalized_answers,
                planning_mode_enabled=planning_mode_enabled,
                use_skills=hasattr(self.config.coordination_config, "use_skills") and self.config.coordination_config.use_skills,
                enable_memory=hasattr(
                    self.config.coordination_config,
                    "enable_memory_filesystem_mode",
                )
                and self.config.coordination_config.enable_memory_filesystem_mode,
                enable_task_planning=self.config.coordination_config.enable_agent_task_planning,
                previous_turns=self._previous_turns,
                human_qa_history=human_qa_history,
                vote_only=vote_only_for_system_message,
                agent_mapping=self.coordination_tracker.get_reverse_agent_mapping(),
                voting_sensitivity_override=getattr(agent, "voting_sensitivity", None),
                voting_threshold=getattr(self.config, "voting_threshold", None),
                checklist_require_gap_report=getattr(
                    self.config,
                    "checklist_require_gap_report",
                    True,
                ),
                gap_report_mode=getattr(
                    self.config,
                    "gap_report_mode",
                    "changedoc",
                ),
                answers_used=self._get_agent_answer_count_for_limit(agent_id),
                answer_cap=self.config.max_new_answers_per_agent,
                coordination_mode=getattr(self.config, "coordination_mode", "voting"),
                agent_subtask=self._agent_subtasks.get(agent_id),
                worktree_paths=round_worktree_paths,
                branch_name=agent_branch,
                other_branches=other_agent_branches if other_agent_branches else None,
                branch_diff_summaries=branch_diff_summaries,
                novelty_pressure_data=novelty_data,
                custom_checklist_items=_active_items,
                item_categories=_active_categories,
                item_verify_by=_active_verify_by,
                item_anti_patterns=_active_anti_patterns,
                item_score_anchors=_active_score_anchors,
                builder_enabled=self._is_builder_subagent_enabled(),
                regression_guard_enabled=self._is_regression_guard_subagent_enabled(),
                essential_files_active=_essential_files_active,
            )

            # Update checklist tool state if registered (mutable dict — tool closure reads this)
            if hasattr(agent.backend, "_checklist_state"):
                agent.backend._checklist_state.update(
                    {
                        "threshold": getattr(self.config, "voting_threshold", 5) or 5,
                        "total": self.config.max_new_answers_per_agent or 5,
                        "require_gap_report": bool(
                            getattr(
                                self.config,
                                "checklist_require_gap_report",
                                True,
                            ),
                        ),
                        "require_diagnostic_report": bool(
                            getattr(
                                self.config,
                                "checklist_require_gap_report",
                                True,
                            ),
                        ),
                        "workspace_path": getattr(
                            getattr(agent.backend, "filesystem_manager", None),
                            "cwd",
                            None,
                        ),
                        "report_cutoff": 7,
                    },
                )

            # Inject phase-appropriate persona if enabled.
            # Use peer-only visibility (exclude the agent's own prior answer) so
            # persona easing starts only after true cross-agent exposure.
            persona_enabled = (
                hasattr(self.config, "coordination_config") and hasattr(self.config.coordination_config, "persona_generator") and self.config.coordination_config.persona_generator.enabled
            )
            if persona_enabled:
                has_peer_answers = self._has_peer_answers(agent_id, normalized_answers)
                persona_text = self._get_persona_for_agent(agent_id, has_peer_answers)
                if persona_text:
                    phase = "eased" if has_peer_answers else "exploration"
                    logger.info(f"[Orchestrator] Injecting {phase} persona for {agent_id}")
                    system_message = f"{persona_text}\n\n{system_message}"
                elif has_peer_answers:
                    logger.info(
                        f"[Orchestrator] Persona dropped for {agent_id} " f"(after_first_answer={self.config.coordination_config.persona_generator.after_first_answer})",
                    )

            logger.info(
                f"[Orchestrator] Structured system message built for {agent_id} (length: {len(system_message)} chars)",
            )

            # Note: Broadcast communication section is now integrated in SystemMessageBuilder
            # as BroadcastCommunicationSection when broadcast is enabled in coordination config

            # Substitute evolved prompt as the task if available (prompt evolution)
            effective_task = self._evolved_prompts.get(agent_id, task)

            # Build conversation with context support (for user message and conversation history)
            # We pass the NEW system_message so it gets tracked in context JSONs
            # Sort agent IDs for consistent anonymous mapping with coordination_tracker
            sorted_answer_ids = sorted(normalized_answers.keys()) if normalized_answers else None
            # Get global agent mapping for consistent anonymous IDs across all components
            agent_mapping = self.coordination_tracker.get_reverse_agent_mapping()
            answer_label_mapping = self.coordination_tracker.get_answer_label_mapping()
            _is_decomp = getattr(self.config, "coordination_mode", "voting") == "decomposition"
            # Gather changedocs from coordination tracker if enabled
            _agent_changedocs = self._gather_agent_changedocs()
            if conversation_context and conversation_context.get(
                "conversation_history",
            ):
                # Use conversation context-aware building
                conversation = self.message_templates.build_conversation_with_context(
                    current_task=effective_task,
                    conversation_history=conversation_context.get(
                        "conversation_history",
                        [],
                    ),
                    agent_summaries=normalized_answers,
                    valid_agent_ids=sorted_answer_ids,
                    base_system_message=system_message,  # Use NEW structured message
                    paraphrase=paraphrase,
                    agent_mapping=agent_mapping,
                    decomposition_mode=_is_decomp,
                    agent_changedocs=_agent_changedocs,
                    answer_label_mapping=answer_label_mapping,
                )
            else:
                # Fallback to standard conversation building
                conversation = self.message_templates.build_initial_conversation(
                    task=effective_task,
                    agent_summaries=normalized_answers,
                    valid_agent_ids=sorted_answer_ids,
                    base_system_message=system_message,  # Use NEW structured message
                    paraphrase=paraphrase,
                    agent_mapping=agent_mapping,
                    decomposition_mode=_is_decomp,
                    agent_changedocs=_agent_changedocs,
                    answer_label_mapping=answer_label_mapping,
                )

            # Inject restart context if this is a restart attempt (like multi-turn context)
            if self.restart_reason and self.restart_instructions:
                # Check if workspace has files from previous attempt
                workspace_populated = False
                agent_obj = self.agents.get(agent_id)
                if agent_obj and agent_obj.backend.filesystem_manager:
                    ws = agent_obj.backend.filesystem_manager.get_current_workspace()
                    if ws and ws.exists() and any(ws.iterdir()):
                        workspace_populated = True
                # Compute branch info for restart context (with anonymous labels)
                branch_info = None
                if self._agent_current_branches:
                    _restart_mapping = self.coordination_tracker.get_reverse_agent_mapping()
                    branch_info = {
                        "own_branch": self._agent_current_branches.get(agent_id),
                        "other_branches": {_restart_mapping.get(aid, aid): b for aid, b in self._agent_current_branches.items() if aid != agent_id and b},
                    }
                restart_context = self.message_templates.format_restart_context(
                    self.restart_reason,
                    self.restart_instructions,
                    previous_answer=self.previous_attempt_answer,
                    workspace_populated=workspace_populated,
                    branch_info=branch_info,
                )
                # Prepend restart context to user message
                conversation["user_message"] = restart_context + "\n\n" + conversation["user_message"]

            round_start_context = self._consume_round_start_context_block(agent_id)
            if round_start_context:
                logger.info(
                    f"[Orchestrator] Injecting round_start_context_block for {agent_id}" f" ({len(round_start_context)} chars," f" first 300: {round_start_context[:300]!r})",
                )
            runtime_user_instructions = self._build_runtime_user_instructions_context(agent_id)
            # When an evolved prompt replaced the task, warn that existing
            # peer answers may not satisfy the new requirements.
            stale_answer_note = None
            if agent_id in self._evolved_prompts and normalized_answers:
                stale_answer_note = "Note: The answers below were produced for an earlier " "version of this task and may not fully satisfy the " "evolved requirements above."

            # Load and inject essential files manifests from previous rounds
            essential_files_block = None
            if normalized_answers and current_round > 0:
                manifests = self._load_essential_files_manifests(agent_id)
                if manifests:
                    essential_files_block = self._format_essential_files_context_block(
                        manifests,
                        agent_id,
                    )
                    if essential_files_block:
                        logger.info(
                            f"[Orchestrator] Injecting essential_files block for {agent_id}" f" ({len(essential_files_block)} chars," f" {len(manifests)} agent manifest(s))",
                        )

            conversation["user_message"] = self._insert_runtime_context_blocks_after_original_message(
                conversation["user_message"],
                [stale_answer_note, round_start_context, essential_files_block, runtime_user_instructions],
            )

            # Track all the context used for this agent execution
            # Now conversation["system_message"] contains the NEW structured message
            self.coordination_tracker.track_agent_context(
                agent_id,
                answers,
                conversation.get("conversation_history", []),
                conversation,
            )
            self._refresh_checklist_state_for_agent(agent_id)

            # Notify display of context received (for TUI to show context labels)
            if answers:
                context_labels = self.coordination_tracker.get_agent_context_labels(agent_id)
                if context_labels and hasattr(self, "display") and self.display and hasattr(self.display, "notify_context_received"):
                    self.display.notify_context_received(agent_id, context_labels)
                # Emit to events.jsonl for subagent TUI parity

                _emitter = get_event_emitter()
                if _emitter:
                    _emitter.emit_context_received(agent_id=agent_id, context_labels=context_labels)

            # Store the context in agent state for later use when saving snapshots
            self.agent_states[agent_id].last_context = conversation

            # Log the messages being sent to the agent with backend info
            backend_name = None
            if hasattr(agent, "backend") and hasattr(
                agent.backend,
                "get_provider_name",
            ):
                backend_name = agent.backend.get_provider_name()

            log_orchestrator_agent_message(
                agent_id,
                "SEND",
                {
                    "system": conversation["system_message"],  # NEW structured message logged
                    "user": conversation["user_message"],
                },
                backend_name=backend_name,
            )

            # Set planning mode on the agent's backend to control MCP tool execution
            if hasattr(agent.backend, "set_planning_mode"):
                agent.backend.set_planning_mode(planning_mode_enabled)
                if planning_mode_enabled:
                    logger.info(
                        f"[Orchestrator] Backend planning mode ENABLED for {agent_id} - MCP tools blocked",
                    )
                else:
                    logger.info(
                        f"[Orchestrator] Backend planning mode DISABLED for {agent_id} - MCP tools allowed",
                    )

            # Set up hook manager for mid-stream injection and reminder extraction
            self._setup_hook_manager_for_agent(agent_id, agent, answers)

            # Build proper conversation messages with system + user messages
            max_attempts = 3

            # Add broadcast guidance if enabled
            if self.config.coordination_config.broadcast and self.config.coordination_config.broadcast is not False:
                # Use blocking mode for both agents and human (priority system prevents deadlocks)
                broadcast_mode = self.config.coordination_config.broadcast
                wait_by_default = True
                broadcast_sensitivity = getattr(
                    self.config.coordination_config,
                    "broadcast_sensitivity",
                    "medium",
                )

                broadcast_guidance = self.message_templates.get_broadcast_guidance(
                    broadcast_mode=broadcast_mode,
                    wait_by_default=wait_by_default,
                    sensitivity=broadcast_sensitivity,
                )
                system_message = system_message + broadcast_guidance
                logger.info(
                    f"📢 [{agent_id}] Added broadcast guidance to system message",
                )

            conversation_messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": conversation["user_message"]},
            ]

            # In decomposition mode, wrap the user message with subtask scope
            if getattr(self.config, "coordination_mode", "voting") == "decomposition":
                subtask = self._agent_subtasks.get(agent_id)
                if subtask:
                    original_msg = conversation_messages[1]["content"]
                    conversation_messages[1]["content"] = (
                        f"[YOUR ASSIGNED SUBTASK: {subtask}]\n"
                        f"Use ownership-first execution: keep most effort on your assigned subtask, "
                        f"and only do adjacent cross-scope work for integration boundaries "
                        f"(interfaces/contracts/shared styles/tests). "
                        f"There may be overlap with other agents' existing work in your area; "
                        f"you may refine/integrate that overlap, but do NOT implement unrelated parts.\n\n"
                        f"{original_msg}"
                    )

            # Inject shared memory context
            conversation_messages = await self._inject_shared_memory_context(
                conversation_messages,
                agent_id,
            )

            # Inject unconsumed MCP hook content from previous round
            # (e.g., human input written to hook file but model only used native tools)
            unconsumed = getattr(self, "_unconsumed_mcp_injections", {}).pop(agent_id, None)
            if unconsumed:
                conversation_messages[1]["content"] += (
                    "\n\n[IMPORTANT — Runtime update from user that arrived during your previous round" " but could not be delivered mid-stream. You MUST address this now.]\n" + unconsumed
                )
                logger.info(
                    "[Orchestrator] Injected %d chars of unconsumed MCP hook content into user message for %s",
                    len(unconsumed),
                    agent_id,
                )
                # Now that unconsumed content is truly delivered to the model,
                # fire the inject callback so TUI shows "Delivered".
                if self._human_input_hook and self._human_input_hook._on_inject_callback:
                    try:
                        self._human_input_hook._on_inject_callback(unconsumed, agent_id)
                    except Exception:
                        pass  # Best-effort TUI notification

            enforcement_msg = self.message_templates.enforcement_message()

            # Update agent status to STREAMING
            self.coordination_tracker.change_status(agent_id, AgentStatus.STREAMING)

            # Start round token tracking for this agent
            # Note: round_type was computed earlier as "voting" if answers else "initial_answer"
            current_round = self.coordination_tracker.get_agent_round(agent_id)
            if hasattr(agent.backend, "start_round_tracking"):
                agent.backend.start_round_tracking(
                    round_number=current_round,
                    round_type=round_type,  # Use computed round_type (voting or initial_answer)
                    agent_id=agent_id,
                )

            # Use while loop for retry attempts
            attempt = 0
            is_first_real_attempt = True  # Track first LLM call separately from attempt counter

            def _restore_round_start_context_for_retry() -> None:
                nonlocal round_start_context
                if round_start_context:
                    self._queue_round_start_context_block(agent_id, round_start_context)
                    round_start_context = None

            while attempt < max_attempts:
                logger.info(
                    f"[Orchestrator] Agent {agent_id} workflow enforcement attempt {attempt + 1}/{max_attempts}",
                )

                has_hook_delivery = self._backend_supports_midstream_hook_injection(agent)
                if not has_hook_delivery and not is_first_real_attempt and not self._check_restart_pending(agent_id):
                    # Poll runtime inbox for messages from parent (subagent mode)
                    self._poll_runtime_inbox()

                    has_pending_runtime_updates = False

                    has_pending_runtime_input = False
                    if self._human_input_hook:
                        if hasattr(self._human_input_hook, "has_pending_input_for_agent"):
                            has_pending_runtime_input = self._human_input_hook.has_pending_input_for_agent(agent_id)
                        else:
                            has_pending_runtime_input = self._human_input_hook.has_pending_input()

                    if has_pending_runtime_input:
                        has_pending_runtime_updates = True
                        logger.info(
                            "[Orchestrator] Hookless runtime input delivery status=%s (%s)",
                            InjectionDeliveryStatus.QUEUED.value,
                            agent_id,
                        )

                    if self._background_subagents_enabled and self._pending_subagent_results.get(agent_id):
                        has_pending_runtime_updates = True
                        logger.info(
                            "[Orchestrator] Hookless subagent completion delivery status=%s (%s)",
                            InjectionDeliveryStatus.QUEUED.value,
                            agent_id,
                        )

                    if self._poll_no_hook_background_tool_updates(agent_id, agent):
                        has_pending_runtime_updates = True
                        logger.info(
                            "[Orchestrator] Hookless background-tool delivery status=%s (%s)",
                            InjectionDeliveryStatus.QUEUED.value,
                            agent_id,
                        )

                    if has_pending_runtime_updates:
                        # Reuse restart_pending as the safe-checkpoint trigger for hookless
                        # runtime payload delivery via enforcement messages.
                        self.agent_states[agent_id].restart_pending = True

                if self._check_restart_pending(agent_id):
                    # First-answer protection: let the agent finish its first round
                    # before acting on restart signals from other agents.
                    if self._should_defer_restart_for_first_answer(agent_id):
                        logger.info(
                            f"[Orchestrator] Deferring restart for {agent_id} - first answer not yet produced",
                        )
                        self.agent_states[agent_id].restart_pending = False
                    else:
                        logger.info(
                            f"[Orchestrator] Agent {agent_id} has restart_pending flag",
                        )

                        # Clear framework MCP state before restart (e.g., task plans)
                        await self._clear_framework_mcp_state(agent_id)

                        if has_hook_delivery and self._should_defer_peer_updates_until_restart(agent_id):
                            if self._has_unseen_answer_updates(agent_id):
                                logger.info(
                                    "[Orchestrator] Forcing restart for %s to deliver deferred peer updates on the next round",
                                    agent_id,
                                )
                                _restore_round_start_context_for_retry()
                                self.agent_states[agent_id].restart_pending = False
                                yield ("done", None)
                                return
                            self.agent_states[agent_id].restart_pending = False

                        # In vote-only mode, always restart to get updated tool schemas.
                        # Mid-stream injection can't update the vote enum, so we need a full restart.
                        if self._is_vote_only_mode(agent_id):
                            logger.info(
                                f"[Orchestrator] Agent {agent_id} in vote-only mode - forcing restart for updated vote options",
                            )
                            _restore_round_start_context_for_retry()
                            self.agent_states[agent_id].restart_pending = False
                            yield ("done", None)
                            return

                        if not has_hook_delivery:
                            # No hook callback path (defensive fallback — all current backends have hooks): if a stream is already in progress
                            # for this execution, convert the update into an enforcement message so
                            # reset_chat=False preserves buffer/session state.
                            if not is_first_real_attempt:
                                fallback_injection = await self._prepare_no_hook_midstream_enforcement(
                                    agent_id,
                                    answers,
                                )
                                if fallback_injection:
                                    enforcement_msg = fallback_injection
                                    _mid_stream_injection = True
                                elif self._check_restart_pending(agent_id):
                                    # Could not deliver mid-stream (e.g., fairness cap reached) - force
                                    # a clean restart so the next round can continue making progress.
                                    logger.info(
                                        "[Orchestrator] Forcing restart for %s (no-hook backend, pending unseen updates)",
                                        agent_id,
                                    )
                                    self.agent_states[agent_id].restart_pending = False
                                    self.agent_states[agent_id].injection_count += 1
                                    yield ("done", None)
                                    return
                            else:
                                # No in-flight buffer yet; normal restart is equivalent and simpler.
                                logger.info(
                                    f"[Orchestrator] Agent {agent_id} backend has no hooks - restarting to apply new context",
                                )
                                _restore_round_start_context_for_retry()
                                self.agent_states[agent_id].restart_pending = False
                                self.agent_states[agent_id].injection_count += 1
                                yield ("done", None)
                                return
                        else:
                            # Mid-stream callback will handle via tool results.
                            # Do NOT clear restart_pending — the callback checks and
                            # clears it after injecting content.
                            if not is_first_real_attempt:
                                _mid_stream_injection = True

                # Track restarts for TUI round display - only when agent is about to do real work
                # (not if it's exiting immediately due to restart_pending)
                if not _notified_round and not _mid_stream_injection:
                    _notified_round = True
                    self.agent_states[agent_id].restart_count += 1
                    # Reset per-round checklist budget so the agent can
                    # evaluate from scratch on this new round.  Without
                    # this, an agent restarted mid-improvement (after
                    # submit_checklist but before new_answer) carries a
                    # stale counter and gets blocked from submitting.
                    self.agent_states[agent_id].checklist_calls_this_round = 0
                    self.agent_states[agent_id].pending_checklist_recheck_labels = set()
                    current_round = self.agent_states[agent_id].restart_count

                    # If this is a restart (round > 1), notify the UI to show fresh timeline
                    if current_round > 1:
                        # Determine restart reason based on context
                        restart_reason = "new answer"  # Default - most common case
                        if answers:
                            restart_reason = "new answer"
                        logger.info(
                            f"[Orchestrator] Agent {agent_id} starting round {current_round} (restart: {restart_reason})",
                        )
                        yield (
                            "agent_restart",
                            {
                                "agent_id": agent_id,
                                "round": current_round,
                                "restart_reason": restart_reason,
                            },
                        )

                # TODO: Need to still log this redo enforcement msg in the context.txt, and this & others in the coordination tracker.

                # Determine which workflow tools to use for this agent
                # If agent has hit answer limit, only provide vote tool (no new_answer/broadcast)
                vote_only = self._is_vote_only_mode(agent_id)
                if vote_only:
                    # Sort agent IDs for consistent anonymous mapping with coordination_tracker
                    # Get agents with answers using global numbering for vote enum
                    anon_ids_with_answers = self.coordination_tracker.get_agents_with_answers_anon(answers) if answers else None
                    agent_workflow_tools = get_workflow_tools(
                        valid_agent_ids=sorted(self.agents.keys()),
                        template_overrides=getattr(
                            self.message_templates,
                            "_template_overrides",
                            {},
                        ),
                        api_format="chat_completions",
                        vote_only=True,
                        anon_agent_ids=anon_ids_with_answers,
                    )
                    logger.info(
                        f"[Orchestrator] Agent {agent_id} in vote-only mode (answer limit reached)",
                    )
                else:
                    # In checkpoint solo mode, main agent gets checkpoint tool
                    if self.is_checkpoint_mode and not self._checkpoint_active and agent_id == self._main_agent_id:
                        agent_workflow_tools = self._checkpoint_workflow_tools
                    else:
                        agent_workflow_tools = self.workflow_tools

                # Combined tools: per-agent workflow tools + any client-provided external tools
                combined_tools = list(agent_workflow_tools) + (list(self._external_tools) if self._external_tools else [])

                if is_first_real_attempt:
                    # First attempt: orchestrator provides initial conversation
                    # But we need the agent to have this in its history for subsequent calls
                    # First attempt: provide complete conversation and reset agent's history
                    # Pass current turn and previous winners for memory sharing
                    chat_stream = agent.chat(
                        conversation_messages,
                        combined_tools,
                        reset_chat=True,
                        current_stage=CoordinationStage.INITIAL_ANSWER,
                        orchestrator_turn=self._current_turn + 1,  # Next turn number
                        previous_winners=self._winning_agents_history.copy(),
                        vote_only=vote_only,  # Pass vote-only flag for Gemini schema
                    )
                    is_first_real_attempt = False  # Only first LLM call uses this path
                else:
                    # Subsequent attempts: send enforcement message (set by error handling)

                    # Log enforcement message preview before sending to chat
                    if isinstance(enforcement_msg, list):
                        msg_preview = str(enforcement_msg)[:500]
                        logger.info(
                            f"[Orchestrator] Sending enforcement message to {agent_id} (list, {len(enforcement_msg)} items): {msg_preview}...",
                        )
                    else:
                        msg_preview = enforcement_msg[:500] if len(enforcement_msg) > 500 else enforcement_msg
                        logger.info(
                            f"[Orchestrator] Sending enforcement message to {agent_id} ({len(enforcement_msg)} chars): {msg_preview}...",
                        )

                    if isinstance(enforcement_msg, list):
                        # Tool message array
                        chat_stream = agent.chat(
                            enforcement_msg,
                            combined_tools,
                            reset_chat=False,
                            current_stage=CoordinationStage.ENFORCEMENT,
                            orchestrator_turn=self._current_turn + 1,
                            previous_winners=self._winning_agents_history.copy(),
                            vote_only=vote_only,  # Pass vote-only flag for Gemini schema
                        )
                    else:
                        # Single user message
                        enforcement_message = {
                            "role": "user",
                            "content": enforcement_msg,
                        }
                        chat_stream = agent.chat(
                            [enforcement_message],
                            combined_tools,
                            reset_chat=False,
                            current_stage=CoordinationStage.ENFORCEMENT,
                            orchestrator_turn=self._current_turn + 1,
                            previous_winners=self._winning_agents_history.copy(),
                            vote_only=vote_only,  # Pass vote-only flag for Gemini schema
                        )
                response_text = ""
                tool_calls = []
                unknown_tool_calls: list[dict] = []
                workflow_tool_found = False
                # Determine internal tool names for this run (uses agent-specific tools to respect vote-only mode).
                internal_tool_names = {(t.get("function", {}) or {}).get("name") for t in (agent_workflow_tools or []) if isinstance(t, dict)}

                logger.info(
                    f"[Orchestrator] Agent {agent_id} starting to stream chat response...",
                )

                async for chunk in chat_stream:
                    # Flush pending hook payloads for MCP server-level hooks (Codex)
                    # on each chunk so the middleware can pick them up on the next tool call.
                    if has_hook_delivery and hasattr(agent.backend, "supports_mcp_server_hooks") and agent.backend.supports_mcp_server_hooks():
                        await self._flush_codex_hook_payloads(agent_id, agent, answers)

                    chunk_type = self._get_chunk_type_value(chunk)
                    if chunk_type == "content":
                        response_text += chunk.content
                        # In strict mode, agent content during coordination goes to traces
                        # Only final presentation content should be the actual response
                        if self.trace_classification == "strict":
                            yield ("coordination", chunk.content)
                        else:
                            yield ("content", chunk.content)
                        # Log received content
                        backend_name = None
                        if hasattr(agent, "backend") and hasattr(
                            agent.backend,
                            "get_provider_name",
                        ):
                            backend_name = agent.backend.get_provider_name()
                        log_orchestrator_agent_message(
                            agent_id,
                            "RECV",
                            {"content": chunk.content},
                            backend_name=backend_name,
                        )
                    elif chunk_type in [
                        "reasoning",
                        "reasoning_done",
                        "reasoning_summary",
                        "reasoning_summary_done",
                    ]:
                        # Emit structured event directly for TUI pipeline
                        from massgen.events import EventType

                        _emitter = get_event_emitter()
                        if _emitter:
                            is_done = chunk_type in ("reasoning_done", "reasoning_summary_done")
                            reasoning_delta = getattr(chunk, "reasoning_delta", None)
                            reasoning_text = getattr(chunk, "reasoning_text", None)
                            summary_delta = getattr(chunk, "reasoning_summary_delta", None)
                            content = reasoning_delta or reasoning_text or summary_delta or ""
                            if content or is_done:
                                _emitter.emit_raw(
                                    EventType.THINKING,
                                    content=content,
                                    done=is_done,
                                    agent_id=agent_id,
                                )

                        # Stream reasoning content as tuple format for Rich display
                        reasoning_chunk = StreamChunk(
                            type=chunk.type,
                            content=chunk.content,
                            source=agent_id,
                            reasoning_delta=getattr(chunk, "reasoning_delta", None),
                            reasoning_text=getattr(chunk, "reasoning_text", None),
                            reasoning_summary_delta=getattr(
                                chunk,
                                "reasoning_summary_delta",
                                None,
                            ),
                            reasoning_summary_text=getattr(
                                chunk,
                                "reasoning_summary_text",
                                None,
                            ),
                            item_id=getattr(chunk, "item_id", None),
                            content_index=getattr(chunk, "content_index", None),
                            summary_index=getattr(chunk, "summary_index", None),
                        )
                        yield ("reasoning", reasoning_chunk)
                    elif chunk_type == "backend_status":
                        pass
                    elif chunk_type == "mcp_status":
                        # Forward MCP status messages preserving type for tool tracking
                        yield (
                            "mcp_status",
                            chunk.content,
                            getattr(chunk, "tool_call_id", None),
                        )

                        # Track MCP failures in reliability metrics
                        mcp_status = getattr(chunk, "status", None)
                        if mcp_status in (
                            "mcp_tools_failed",
                            "mcp_unavailable",
                            "mcp_error",
                        ):
                            buffer_preview, buffer_chars = self._get_buffer_content(
                                agent,
                            )

                            # Get Docker health info for reliability metrics (non-blocking)
                            docker_health = await asyncio.to_thread(
                                self._get_docker_health,
                                agent,
                                agent_id,
                            )

                            self.coordination_tracker.track_enforcement_event(
                                agent_id=agent_id,
                                reason="mcp_disconnected",
                                attempt=attempt + 1,
                                max_attempts=max_attempts,
                                tool_calls=[],
                                error_message=chunk.content[:500] if chunk.content else None,
                                buffer_preview=buffer_preview,
                                buffer_chars=buffer_chars,
                                docker_health=docker_health,
                            )

                            # Save Docker container logs on MCP failure for debugging (fire-and-forget)
                            asyncio.create_task(
                                asyncio.to_thread(
                                    self._save_docker_logs_on_mcp_failure,
                                    agent,
                                    agent_id,
                                    mcp_status,
                                ),
                            )
                    elif chunk_type == "custom_tool_status":
                        # Forward custom tool status messages preserving type for tool tracking
                        yield (
                            "custom_tool_status",
                            chunk.content,
                            getattr(chunk, "tool_call_id", None),
                        )
                    elif chunk_type == "hook_execution":
                        # Forward hook execution chunks for TUI display
                        # Include hook_info and tool_call_id for injection subcard display
                        hook_chunk = StreamChunk(
                            type="hook_execution",
                            content=chunk.content,
                            source=agent_id,
                            hook_info=getattr(chunk, "hook_info", None),
                            tool_call_id=getattr(chunk, "tool_call_id", None),
                        )
                        yield ("hook_execution", hook_chunk)
                    elif chunk_type == "debug":
                        # Forward debug chunks
                        yield ("debug", chunk.content)
                    elif chunk_type == "tool_calls":
                        # Use the correct tool_calls field
                        chunk_tool_calls = getattr(chunk, "tool_calls", []) or []
                        tool_calls.extend(chunk_tool_calls)

                        # Stream tool calls to show agent actions
                        # Get backend name for logging
                        backend_name = None
                        if hasattr(agent, "backend") and hasattr(
                            agent.backend,
                            "get_provider_name",
                        ):
                            backend_name = agent.backend.get_provider_name()

                        # Build set of client-provided external tool names
                        external_tool_names = {(t.get("function", {}) or {}).get("name") for t in (self._external_tools or []) if isinstance(t, dict)}

                        external_tool_calls = []
                        for tool_call in chunk_tool_calls:
                            tool_name = agent.backend.extract_tool_name(tool_call)
                            tool_args = agent.backend.extract_tool_arguments(tool_call)

                            # Client-provided external tools: surface to caller and end the turn
                            if tool_name and tool_name in external_tool_names:
                                external_tool_calls.append(tool_call)
                                continue

                            # Intercept checkpoint tool (both MCP and workflow name)
                            # Add to tool_calls for post-stream workflow processing
                            if tool_name in ("checkpoint", "mcp__massgen_checkpoint__checkpoint"):
                                logger.info(
                                    f"[Orchestrator] Agent {agent_id} called checkpoint tool '{tool_name}'",
                                )
                                tool_calls.append(tool_call)
                                continue

                            # Check if this is an MCP or custom tool (handled by backend)
                            is_mcp = hasattr(
                                agent.backend,
                                "is_mcp_tool_call",
                            ) and agent.backend.is_mcp_tool_call(tool_name)
                            is_custom = hasattr(
                                agent.backend,
                                "is_custom_tool_call",
                            ) and agent.backend.is_custom_tool_call(tool_name)

                            # MCP and custom tools are handled by backend - just log for UI, don't warn
                            if is_mcp or is_custom:
                                tool_type = "MCP" if is_mcp else "Custom"
                                logger.debug(
                                    f"[Orchestrator] Agent {agent_id} called {tool_type} tool '{tool_name}' (handled by backend)",
                                )
                                # Don't yield UI message here - backend streams its own status messages
                                continue

                            # Tool exists but is unavailable this round (e.g., new_answer in vote-only mode)
                            if tool_name and tool_name in WORKFLOW_TOOL_NAMES and tool_name not in internal_tool_names:
                                logger.info(
                                    f"[Orchestrator] Agent {agent_id} called unavailable workflow tool '{tool_name}' for this round",
                                )
                                yield self._trace_tuple(
                                    f"⚠️ Tool unavailable this round: {tool_name}",
                                    kind="coordination",
                                )
                                continue

                            # Unknown tools (not workflow, not MCP, not custom, not external): log warning
                            # This handles hallucinated tool names or model prefixes like "default_api:"
                            if tool_name and tool_name not in internal_tool_names:
                                logger.warning(
                                    f"[Orchestrator] Agent {agent_id} called unknown tool '{tool_name}' - not registered as workflow, MCP, or custom tool",
                                )
                                yield self._trace_tuple(
                                    f"⚠️ Unknown tool: {tool_name} (not registered)",
                                    kind="coordination",
                                )
                                # Track this call so enforcement doesn't create an orphaned
                                # tool_result for it (backends like Claude strip unknown tool_use
                                # blocks from history, making a tool_result invalid → API 400).
                                unknown_tool_calls.append(tool_call)
                                continue

                            if tool_name == "new_answer":
                                content = self._coerce_answer_content_to_text(
                                    tool_args.get("content", ""),
                                )
                                yield self._trace_tuple(
                                    f'💡 Providing answer: "{content}"',
                                    kind="coordination",
                                )
                                log_tool_call(
                                    agent_id,
                                    "new_answer",
                                    {"content": content},
                                    None,
                                    backend_name,
                                )  # Full content for debug logging
                            elif tool_name == "vote":
                                agent_voted_for = tool_args.get("agent_id", "")
                                reason = tool_args.get("reason", "")
                                log_tool_call(
                                    agent_id,
                                    "vote",
                                    {"agent_id": agent_voted_for, "reason": reason},
                                    None,
                                    backend_name,
                                )  # Full reason for debug logging

                                # Convert anonymous agent ID to real agent ID for display
                                # Use global agent mapping (consistent with vote validation)
                                agent_mapping = self.coordination_tracker.get_anonymous_agent_mapping()
                                real_agent_id = agent_mapping.get(
                                    agent_voted_for,
                                    agent_voted_for,
                                )

                                # Show which agents have answers using global numbering
                                options_anon = self.coordination_tracker.get_agents_with_answers_anon(
                                    answers,
                                )

                                yield (
                                    "coordination" if self.trace_classification == "strict" else "content",
                                    f"🗳️ Voting for [{real_agent_id}] (options: {', '.join(options_anon)}) : {reason}",
                                )
                            elif tool_name == "stop":
                                # Decomposition mode stop tool
                                summary = tool_args.get("summary", "")
                                status = tool_args.get("status", "complete")
                                log_tool_call(
                                    agent_id,
                                    "stop",
                                    {"summary": summary, "status": status},
                                    None,
                                    backend_name,
                                )
                                yield (
                                    "coordination" if self.trace_classification == "strict" else "content",
                                    f"🛑 Stopping ({status}): {summary[:100]}",
                                )
                            elif tool_name == "ask_others":
                                # Broadcast tool - handled as custom tool by backend
                                question = tool_args.get("question", "")
                                yield self._trace_tuple(
                                    f"📢 Asking others: {question[:80]}...",
                                    kind="coordination",
                                )
                                log_tool_call(
                                    agent_id,
                                    "ask_others",
                                    tool_args,
                                    None,
                                    backend_name,
                                )
                            elif tool_name in [
                                "check_broadcast_status",
                                "get_broadcast_responses",
                            ]:
                                # Polling broadcast tools - handled as custom tools by backend
                                request_id = tool_args.get("request_id", "")
                                yield self._trace_tuple(
                                    f"📢 Checking broadcast {request_id[:8]}...",
                                    kind="coordination",
                                )
                                log_tool_call(
                                    agent_id,
                                    tool_name,
                                    tool_args,
                                    None,
                                    backend_name,
                                )
                            else:
                                yield self._trace_tuple(
                                    f"🔧 Using {tool_name}",
                                    kind="coordination",
                                )
                                log_tool_call(
                                    agent_id,
                                    tool_name,
                                    tool_args,
                                    None,
                                    backend_name,
                                )

                        if external_tool_calls:
                            # Surface external tool calls (do NOT execute) and terminate this agent execution.
                            yield ("external_tool_calls", external_tool_calls)
                            yield ("done", None)
                            return
                    elif chunk_type == "error":
                        # Stream error information to user interface
                        error_msg = getattr(chunk, "error", str(chunk.content)) if hasattr(chunk, "error") else str(chunk.content)
                        is_fatal_backend_error = getattr(chunk, "status", None) == "fatal"
                        if is_fatal_backend_error:
                            yield ("error", error_msg)
                        else:
                            yield ("content", f"❌ Error: {error_msg}\n")

                        # Track API/streaming error in reliability metrics
                        buffer_preview, buffer_chars = self._get_buffer_content(agent)
                        self.coordination_tracker.track_enforcement_event(
                            agent_id=agent_id,
                            reason="fatal_api_error" if is_fatal_backend_error else "api_error",
                            attempt=attempt + 1,
                            max_attempts=max_attempts,
                            tool_calls=[],
                            error_message=error_msg[:500] if error_msg else None,
                            buffer_preview=buffer_preview,
                            buffer_chars=buffer_chars,
                        )
                        if is_fatal_backend_error:
                            yield ("done", None)
                            return
                    elif chunk_type == "incomplete_response_recovery":
                        # Handle incomplete response recovery - API stream ended early
                        # Buffer content is preserved in chunk.content
                        buffer_size = len(chunk.content or "") if chunk.content else 0
                        detail = getattr(chunk, "detail", "")
                        logger.info(
                            f"[Orchestrator] Agent {agent_id} recovering from incomplete response - " f"preserved {buffer_size} chars of content. {detail}",
                        )
                        # Yield status message for visibility
                        yield (
                            "content",
                            f"⚠️ API stream ended early - recovering with preserved context ({detail})\n",
                        )

                        # Track connection recovery in reliability metrics
                        self.coordination_tracker.track_enforcement_event(
                            agent_id=agent_id,
                            reason="connection_recovery",
                            attempt=attempt + 1,
                            max_attempts=max_attempts,
                            tool_calls=[],
                            error_message=detail,
                            buffer_preview=chunk.content[:500] if chunk.content else None,
                            buffer_chars=buffer_size,
                        )
                        # Note: The orchestrator's while loop will continue and make a new API call
                        # The buffer content has already been yielded as stream content, so it's already in the context

                    # Check if force_terminate was triggered by too many consecutive denied tool calls
                    timeout_state = self.agent_states[agent_id].round_timeout_state
                    if timeout_state and timeout_state.force_terminate:
                        logger.error(
                            f"[Orchestrator] FORCE TERMINATE for {agent_id} - "
                            f"{timeout_state.consecutive_hard_denials} consecutive denied tool calls. "
                            f"Agent stuck in denial loop, terminating turn.",
                        )
                        yield (
                            "error",
                            f"Agent terminated: {timeout_state.consecutive_hard_denials} consecutive blocked " f"tool calls after hard timeout. Agent failed to submit vote/answer.",
                        )
                        yield ("done", None)
                        return

                # After streaming ends, check for unconsumed MCP hook content.
                # If the hook file still exists, the middleware never delivered it
                # (e.g., Codex only used native tools). Carry it forward.
                if hasattr(agent.backend, "read_unconsumed_hook_content"):
                    leftover = agent.backend.read_unconsumed_hook_content()
                    if leftover:
                        if not hasattr(self, "_unconsumed_mcp_injections"):
                            self._unconsumed_mcp_injections: dict[str, str] = {}
                        self._unconsumed_mcp_injections[agent_id] = leftover
                        logger.info(
                            "[Orchestrator] Unconsumed MCP hook content for %s (%d chars) — will include in next round",
                            agent_id,
                            len(leftover),
                        )
                    else:
                        # Hook file was consumed by MCP middleware (model saw it
                        # during a tool call). Fire the suppressed inject callback
                        # so TUI shows "Delivered".
                        pending_content = getattr(self, "_codex_pending_inject_confirmation", {}).pop(agent_id, None)
                        if pending_content and self._human_input_hook and self._human_input_hook._on_inject_callback:
                            try:
                                self._human_input_hook._on_inject_callback(pending_content, agent_id)
                            except Exception:
                                pass  # Best-effort TUI notification

                # Filter workflow tool calls that are not allowed in this round.
                # This enforces vote-only/stop-only modes at execution time in case a model
                # emits stale tool names from previous context.  Must run BEFORE vote
                # deduplication so disallowed vote calls (e.g. from text-parsing fallback
                # in decomposition mode) are removed before they pollute vote_calls.
                (
                    tool_calls,
                    disallowed_workflow_calls,
                    disallowed_workflow_names,
                ) = self._split_disallowed_workflow_tool_calls(
                    agent,
                    tool_calls,
                    internal_tool_names,
                )

                # Handle multiple vote calls - take the last vote (agent's final decision)
                vote_calls = [tc for tc in tool_calls if agent.backend.extract_tool_name(tc) == "vote"]
                if len(vote_calls) > 1:
                    # Take the last vote - represents the agent's final, most refined decision
                    num_votes = len(vote_calls)
                    final_vote_call = vote_calls[-1]
                    final_vote_args = agent.backend.extract_tool_arguments(
                        final_vote_call,
                    )
                    final_voted_agent = final_vote_args.get("agent_id", "unknown")

                    # Replace tool_calls with deduplicated list (all non-votes + final vote)
                    vote_calls = [final_vote_call]
                    tool_calls = [tc for tc in tool_calls if agent.backend.extract_tool_name(tc) != "vote"] + [final_vote_call]

                    logger.info(
                        f"[Orchestrator] Agent {agent_id} made {num_votes} votes - using last vote: {final_voted_agent}",
                    )
                if disallowed_workflow_calls:
                    disallowed_unique = sorted(set(disallowed_workflow_names))
                    allowed_workflow_unique = sorted(name for name in internal_tool_names if name)
                    allowed_display = ", ".join(allowed_workflow_unique) if allowed_workflow_unique else "none"
                    is_decomposition = getattr(self.config, "coordination_mode", "voting") == "decomposition"
                    if vote_only and "new_answer" in disallowed_unique:
                        if is_decomposition:
                            error_msg = "You have reached your answer limit. The `new_answer` tool is disabled. " "You MUST call `stop` now."
                        else:
                            error_msg = "You have reached your answer limit. The `new_answer` tool is disabled. " "You MUST use the `vote` tool now."
                        enforcement_reason = "answer_limit"
                    else:
                        error_msg = f"Tool(s) not available this round: {', '.join(disallowed_unique)}. " f"Available workflow tool(s): {allowed_display}."
                        enforcement_reason = "no_workflow_tool"

                    if attempt < max_attempts - 1:
                        yield (
                            "content",
                            f"❌ Retry ({attempt + 1}/{max_attempts}): {error_msg}",
                        )

                        # Track enforcement event before retry
                        buffer_preview, buffer_chars = self._get_buffer_content(agent)
                        self.coordination_tracker.track_enforcement_event(
                            agent_id=agent_id,
                            reason=enforcement_reason,
                            attempt=attempt + 1,
                            max_attempts=max_attempts,
                            tool_calls=disallowed_unique,
                            error_message=error_msg,
                            buffer_preview=buffer_preview,
                            buffer_chars=buffer_chars,
                        )

                        # Return tool errors for the unavailable workflow tool calls
                        enforcement_msg = self._create_tool_error_messages(
                            agent,
                            disallowed_workflow_calls,
                            error_msg,
                        )
                        attempt += 1  # Error counts as an attempt
                        continue
                    else:
                        yield (
                            "error",
                            f"Agent used unavailable workflow tool(s) after {max_attempts} attempts: {', '.join(disallowed_unique)}",
                        )
                        yield ("done", None)
                        return

                # Check for mixed new_answer and vote calls - violates binary decision framework
                new_answer_calls = [tc for tc in tool_calls if agent.backend.extract_tool_name(tc) == "new_answer"]
                if len(vote_calls) > 0 and len(new_answer_calls) > 0:
                    if attempt < max_attempts - 1:
                        # Note: restart_pending is handled by mid-stream callback on next tool call
                        error_msg = "Cannot use both 'vote' and 'new_answer' in same response. Choose one: vote for existing answer OR provide new answer."
                        yield (
                            "content",
                            f"❌ Retry ({attempt + 1}/{max_attempts}): {error_msg}",
                        )

                        # Track enforcement event before retry
                        buffer_preview, buffer_chars = self._get_buffer_content(agent)
                        self.coordination_tracker.track_enforcement_event(
                            agent_id=agent_id,
                            reason="vote_and_answer",
                            attempt=attempt + 1,
                            max_attempts=max_attempts,
                            tool_calls=["vote", "new_answer"],
                            error_message=error_msg,
                            buffer_preview=buffer_preview,
                            buffer_chars=buffer_chars,
                        )

                        # Send tool error response for all tool calls that caused the violation
                        enforcement_msg = self._create_tool_error_messages(
                            agent,
                            tool_calls,
                            error_msg,
                        )
                        attempt += 1  # Error counts as an attempt
                        continue  # Retry this attempt
                    else:
                        yield (
                            "error",
                            "Agent used both vote and new_answer tools in single response after max attempts",
                        )
                        yield ("done", None)
                        return

                # Process all tool calls
                if tool_calls:
                    for tool_call in tool_calls:
                        tool_name = agent.backend.extract_tool_name(tool_call)
                        tool_args = agent.backend.extract_tool_arguments(tool_call)

                        if tool_name == "vote":
                            # Fetch fresh answers (includes virtual agents in step mode)
                            answers = self._get_current_answers_snapshot()

                            # Log which agents we are choosing from
                            logger.info(
                                f"[Orchestrator] Agent {agent_id} voting from options: {list(answers.keys()) if answers else 'No answers available'}",
                            )
                            # Note: restart_pending is handled by mid-stream callback on next tool call

                            workflow_tool_found = True
                            # Vote for existing answer (requires existing answers)
                            if not answers:
                                # Invalid - can't vote when no answers exist
                                if attempt < max_attempts - 1:
                                    # Note: restart_pending is handled by mid-stream callback on next tool call
                                    error_msg = "Cannot vote when no answers exist. Use new_answer tool."
                                    yield (
                                        "content",
                                        f"❌ Retry ({attempt + 1}/{max_attempts}): {error_msg}",
                                    )

                                    # Track enforcement event before retry
                                    buffer_preview, buffer_chars = self._get_buffer_content(agent)
                                    self.coordination_tracker.track_enforcement_event(
                                        agent_id=agent_id,
                                        reason="vote_no_answers",
                                        attempt=attempt + 1,
                                        max_attempts=max_attempts,
                                        tool_calls=["vote"],
                                        error_message=error_msg,
                                        buffer_preview=buffer_preview,
                                        buffer_chars=buffer_chars,
                                    )

                                    # Create proper tool error message for retry
                                    enforcement_msg = self._create_tool_error_messages(
                                        agent,
                                        [tool_call],
                                        error_msg,
                                    )
                                    attempt += 1  # Error counts as an attempt
                                    continue
                                else:
                                    yield (
                                        "error",
                                        "Cannot vote when no answers exist after max attempts",
                                    )
                                    yield ("done", None)
                                    return

                            voted_agent_anon = tool_args.get("agent_id")
                            reason = tool_args.get("reason", "")

                            # Convert anonymous agent ID back to real agent ID
                            # Use global agent mapping (consistent with vote tool enum and injection)
                            agent_mapping = self.coordination_tracker.get_anonymous_agent_mapping()

                            voted_agent = agent_mapping.get(
                                voted_agent_anon,
                                voted_agent_anon,
                            )

                            # Handle invalid agent_id - check if voted agent has an answer
                            if voted_agent not in answers:
                                if attempt < max_attempts - 1:
                                    # Note: restart_pending is handled by mid-stream callback on next tool call
                                    # Build valid agents list using global numbering (consistent with enum)
                                    valid_anon_agents = self.coordination_tracker.get_agents_with_answers_anon(
                                        answers,
                                    )
                                    error_msg = f"Invalid agent_id '{voted_agent_anon}'. Valid agents: {', '.join(valid_anon_agents)}"
                                    # Send tool error result back to agent
                                    yield (
                                        "content",
                                        f"❌ Retry ({attempt + 1}/{max_attempts}): {error_msg}",
                                    )

                                    # Track enforcement event before retry
                                    buffer_preview, buffer_chars = self._get_buffer_content(agent)
                                    self.coordination_tracker.track_enforcement_event(
                                        agent_id=agent_id,
                                        reason="invalid_vote_id",
                                        attempt=attempt + 1,
                                        max_attempts=max_attempts,
                                        tool_calls=["vote"],
                                        error_message=error_msg,
                                        buffer_preview=buffer_preview,
                                        buffer_chars=buffer_chars,
                                    )

                                    # Create proper tool error message for retry
                                    enforcement_msg = self._create_tool_error_messages(
                                        agent,
                                        [tool_call],
                                        error_msg,
                                    )
                                    attempt += 1  # Error counts as an attempt
                                    continue  # Retry with updated conversation
                                else:
                                    yield (
                                        "error",
                                        f"Invalid agent_id after {max_attempts} attempts",
                                    )
                                    yield ("done", None)
                                    return
                            # Record the vote locally (but orchestrator may still ignore it)
                            self.agent_states[agent_id].votes = {
                                "agent_id": voted_agent,
                                "reason": reason,
                            }

                            # Record vote to shared memory
                            vote_message = f"Voted for {voted_agent}. Reason: {reason}"
                            await self._record_to_shared_memory(
                                agent_id=agent_id,
                                content=vote_message,
                                role="assistant",
                            )

                            # Send tool result - orchestrator will decide if vote is accepted
                            # Vote submitted (result will be shown by orchestrator)
                            _agent_outcome = "vote"
                            _agent_voted_for = voted_agent
                            # Get the answer label that this voter was shown for voted-for agent
                            _agent_voted_for_label = self.coordination_tracker.get_voted_for_label(
                                agent_id,
                                voted_agent,
                            )

                            # Record vote to execution trace (if available)
                            if hasattr(agent.backend, "_add_vote_to_trace"):
                                # Get available answer labels from voter's context
                                available_options = self.coordination_tracker.get_agent_context_labels(
                                    agent_id,
                                )
                                agent.backend._add_vote_to_trace(
                                    voted_for_agent=voted_agent,
                                    voted_for_label=_agent_voted_for_label,
                                    reason=reason,
                                    available_options=available_options,
                                )

                            yield (
                                "result",
                                ("vote", {"agent_id": voted_agent, "reason": reason}),
                            )
                            yield ("done", None)
                            return

                        elif tool_name == "stop":
                            workflow_tool_found = True
                            # Decomposition mode: agent signals subtask is complete
                            summary = tool_args.get("summary", "")
                            status = tool_args.get("status", "complete")
                            log_tool_call(
                                agent_id,
                                "stop",
                                {"summary": summary, "status": status},
                                None,
                                backend_name,
                            )

                            # Record to shared memory
                            stop_message = f"Stopped ({status}): {summary}"
                            await self._record_to_shared_memory(
                                agent_id=agent_id,
                                content=stop_message,
                                role="assistant",
                            )

                            # Reuse the vote result pipeline — orchestrator processes
                            # stop the same way as vote (sets has_voted = True)
                            yield (
                                "result",
                                (
                                    "vote",
                                    {
                                        "agent_id": agent_id,
                                        "reason": summary,
                                        "stop_summary": summary,
                                        "stop_status": status,
                                        "_is_stop": True,
                                    },
                                ),
                            )
                            yield ("done", None)
                            return

                        elif tool_name == "checkpoint" or tool_name == "mcp__massgen_checkpoint__checkpoint":
                            # Reject recursive checkpoint calls during active checkpoint
                            if self._checkpoint_active:
                                yield self._trace_tuple(
                                    "Checkpoint tool unavailable during checkpoint round",
                                    kind="coordination",
                                )
                                continue
                            workflow_tool_found = True
                            # Main agent is delegating a task to the team
                            checkpoint_task = tool_args.get("task", "")
                            checkpoint_context = tool_args.get("context", "")
                            checkpoint_eval_criteria = tool_args.get("eval_criteria", [])
                            checkpoint_personas = tool_args.get("personas")
                            checkpoint_gated = tool_args.get("gated_actions") or tool_args.get("expected_actions", [])

                            # Validate required params — models don't always
                            # respect schema constraints
                            from massgen.mcp_tools.checkpoint._checkpoint_mcp_server import (
                                build_checkpoint_signal,
                                validate_checkpoint_params,
                            )

                            try:
                                validated = validate_checkpoint_params(
                                    task=checkpoint_task,
                                    context=checkpoint_context,
                                    eval_criteria=checkpoint_eval_criteria,
                                    personas=checkpoint_personas,
                                    gated_actions=checkpoint_gated,
                                )
                            except ValueError as e:
                                yield self._trace_tuple(
                                    f"❌ Checkpoint rejected: {e}",
                                    kind="coordination",
                                )
                                continue

                            yield self._trace_tuple(
                                f"📋 Checkpoint: {checkpoint_task[:80]}",
                                kind="coordination",
                            )

                            signal = build_checkpoint_signal(
                                task=validated["task"],
                                context=validated["context"],
                                eval_criteria=validated["eval_criteria"],
                                personas=validated["personas"],
                                gated_actions=validated["gated_actions"],
                            )

                            # Spawn subprocess and wait for completion
                            consensus = await self._activate_checkpoint(signal)

                            # Return consensus as tool result; agent continues
                            yield (
                                "result",
                                (
                                    "answer",
                                    f"[CHECKPOINT COMPLETE] {consensus[:2000]}",
                                ),
                            )
                            yield ("done", None)
                            return

                        elif tool_name == "new_answer":
                            workflow_tool_found = True
                            # Agent provided new answer
                            content = self._coerce_answer_content_to_text(
                                tool_args.get("content", response_text.strip()),
                            )

                            # Check answer count limit
                            can_answer, count_error = self._check_answer_count_limit(
                                agent_id,
                            )
                            if not can_answer:
                                if attempt < max_attempts - 1:
                                    # Note: restart_pending is handled by mid-stream callback on next tool call
                                    yield (
                                        "content",
                                        f"❌ Retry ({attempt + 1}/{max_attempts}): {count_error}",
                                    )

                                    # Track enforcement event before retry
                                    buffer_preview, buffer_chars = self._get_buffer_content(agent)
                                    self.coordination_tracker.track_enforcement_event(
                                        agent_id=agent_id,
                                        reason="answer_limit",
                                        attempt=attempt + 1,
                                        max_attempts=max_attempts,
                                        tool_calls=["new_answer"],
                                        error_message=count_error,
                                        buffer_preview=buffer_preview,
                                        buffer_chars=buffer_chars,
                                    )

                                    # Create proper tool error message for retry
                                    enforcement_msg = self._create_tool_error_messages(
                                        agent,
                                        [tool_call],
                                        count_error,
                                    )
                                    attempt += 1  # Error counts as an attempt
                                    continue
                                else:
                                    yield (
                                        "error",
                                        f"Answer count limit reached after {max_attempts} attempts",
                                    )
                                    yield ("done", None)
                                    return

                            # Check answer novelty (similarity to existing answers)
                            is_novel, novelty_error = self._check_answer_novelty(
                                content,
                                answers,
                            )
                            if not is_novel:
                                if attempt < max_attempts - 1:
                                    # Note: restart_pending is handled by mid-stream callback on next tool call
                                    yield (
                                        "content",
                                        f"❌ Retry ({attempt + 1}/{max_attempts}): {novelty_error}",
                                    )

                                    # Track enforcement event before retry
                                    buffer_preview, buffer_chars = self._get_buffer_content(agent)
                                    self.coordination_tracker.track_enforcement_event(
                                        agent_id=agent_id,
                                        reason="answer_novelty",
                                        attempt=attempt + 1,
                                        max_attempts=max_attempts,
                                        tool_calls=["new_answer"],
                                        error_message=novelty_error,
                                        buffer_preview=buffer_preview,
                                        buffer_chars=buffer_chars,
                                    )

                                    # Create proper tool error message for retry
                                    enforcement_msg = self._create_tool_error_messages(
                                        agent,
                                        [tool_call],
                                        novelty_error,
                                    )
                                    attempt += 1  # Error counts as an attempt
                                    continue
                                else:
                                    yield (
                                        "error",
                                        f"Answer novelty requirement not met after {max_attempts} attempts",
                                    )
                                    yield ("done", None)
                                    return

                            # Check for duplicate answer
                            # Normalize both new content and existing content to neutral paths for comparison
                            normalized_new_content = self._normalize_workspace_paths_for_comparison(content)

                            for existing_agent_id, existing_content in answers.items():
                                normalized_existing_content = self._normalize_workspace_paths_for_comparison(
                                    existing_content,
                                )
                                if normalized_new_content.strip() == normalized_existing_content.strip():
                                    if attempt < max_attempts - 1:
                                        # Note: restart_pending is handled by mid-stream callback on next tool call
                                        error_msg = f"Answer already provided by {existing_agent_id}. Provide different answer or vote for existing one."
                                        yield (
                                            "content",
                                            f"❌ Retry ({attempt + 1}/{max_attempts}): {error_msg}",
                                        )

                                        # Track enforcement event before retry
                                        buffer_preview, buffer_chars = self._get_buffer_content(agent)
                                        self.coordination_tracker.track_enforcement_event(
                                            agent_id=agent_id,
                                            reason="answer_duplicate",
                                            attempt=attempt + 1,
                                            max_attempts=max_attempts,
                                            tool_calls=["new_answer"],
                                            error_message=error_msg,
                                            buffer_preview=buffer_preview,
                                            buffer_chars=buffer_chars,
                                        )

                                        # Create proper tool error message for retry
                                        enforcement_msg = self._create_tool_error_messages(
                                            agent,
                                            [tool_call],
                                            error_msg,
                                        )
                                        attempt += 1  # Error counts as an attempt
                                        continue
                                    else:
                                        yield (
                                            "error",
                                            f"Duplicate answer provided after {max_attempts} attempts",
                                        )
                                        yield ("done", None)
                                        return
                            # Send successful tool result back to agent
                            # Answer recorded (result will be shown by orchestrator)

                            # Record to shared memory
                            await self._record_to_shared_memory(
                                agent_id=agent_id,
                                content=content,
                                role="assistant",
                            )

                            _agent_outcome = "answer"
                            # Compute the answer label that will be assigned (e.g., "agent1.1")
                            agent_num = self.coordination_tracker._get_agent_number(
                                agent_id,
                            )
                            current_answers = len(
                                self.coordination_tracker.answers_by_agent.get(
                                    agent_id,
                                    [],
                                ),
                            )
                            _agent_answer_label = f"agent{agent_num}.{current_answers + 1}"
                            yield ("result", ("answer", content))
                            yield ("done", None)
                            return
                        elif tool_name in (
                            "ask_others",
                            "check_broadcast_status",
                            "get_broadcast_responses",
                        ):
                            # Broadcast tools - check if backend already executed it
                            # For most backends, custom tools are executed during streaming
                            # For Claude Code, tools are parsed from text and need orchestrator execution
                            is_claude_code = hasattr(agent.backend, "get_provider_name") and agent.backend.get_provider_name() == "claude_code"

                            if is_claude_code and hasattr(
                                agent.backend,
                                "_broadcast_toolkit",
                            ):
                                # Claude Code: Execute broadcast tool here since backend doesn't execute it
                                import json

                                broadcast_toolkit = agent.backend._broadcast_toolkit

                                if tool_name == "ask_others":
                                    args_json = json.dumps(tool_args)
                                    yield (
                                        "content",
                                        f"📢 Asking others: {tool_args.get('question', '')[:80]}...\n",
                                    )
                                    result = await broadcast_toolkit.execute_ask_others(
                                        args_json,
                                        agent_id,
                                    )
                                    # Inject result back to agent's conversation
                                    result_msg = {
                                        "role": "user",
                                        "content": f"[Broadcast Response]\n{result}",
                                    }
                                    conversation_messages.append(result_msg)
                                    yield (
                                        "content",
                                        "📢 Received broadcast responses\n",
                                    )
                                elif tool_name == "check_broadcast_status":
                                    args_json = json.dumps(tool_args)
                                    result = await broadcast_toolkit.execute_check_broadcast_status(
                                        args_json,
                                        agent_id,
                                    )
                                    result_msg = {
                                        "role": "user",
                                        "content": f"[Broadcast Status]\n{result}",
                                    }
                                    conversation_messages.append(result_msg)
                                elif tool_name == "get_broadcast_responses":
                                    args_json = json.dumps(tool_args)
                                    result = await broadcast_toolkit.execute_get_broadcast_responses(
                                        args_json,
                                        agent_id,
                                    )
                                    result_msg = {
                                        "role": "user",
                                        "content": f"[Broadcast Responses]\n{result}",
                                    }
                                    conversation_messages.append(result_msg)

                            # Mark as workflow tool found to avoid retry enforcement
                            # The agent will continue and provide new_answer or vote after receiving broadcast response
                            workflow_tool_found = True
                            # Don't return - let the loop continue so agent can process broadcast result
                            # and provide a proper workflow response (new_answer or vote)
                        elif (hasattr(agent.backend, "is_mcp_tool_call") and agent.backend.is_mcp_tool_call(tool_name)) or (
                            hasattr(agent.backend, "is_custom_tool_call") and agent.backend.is_custom_tool_call(tool_name)
                        ):
                            # MCP and custom tools are handled by the backend
                            # Tool results are streamed separately via StreamChunks
                            # Only mark as workflow progress if agent can still provide answers.
                            # If they've hit their answer limit, they MUST vote - MCP tools shouldn't delay this.
                            can_answer, _ = self._check_answer_count_limit(agent_id)
                            if can_answer:
                                workflow_tool_found = True
                            # else: agent must vote, don't set workflow_tool_found so enforcement triggers
                        else:
                            # Non-workflow tools not yet implemented
                            yield (
                                "coordination" if self.trace_classification == "strict" else "content",
                                f"🔧 used {tool_name} tool (not implemented)",
                            )

                # Case 3: Non-workflow response, need enforcement (only if no workflow tool was found)
                if not workflow_tool_found:
                    # Note: restart_pending is handled by mid-stream callback on next tool call
                    if attempt < max_attempts - 1:
                        # Determine enforcement reason and message
                        is_decomposition = getattr(self.config, "coordination_mode", "voting") == "decomposition"
                        if tool_calls:
                            # Use vote-only/stop-only enforcement message if agent has hit answer limit
                            if vote_only:
                                if is_decomposition:
                                    error_msg = "You have reached your answer limit. You MUST call `stop` now to signal you are done."
                                else:
                                    error_msg = (
                                        "You have reached your answer limit. You MUST use the `vote` tool now to vote for the best existing answer. The `new_answer` tool is no longer available."
                                    )
                            else:
                                if is_decomposition:
                                    error_msg = "You must use workflow tools (stop or new_answer) to complete the task."
                                else:
                                    error_msg = "You must use workflow tools (vote or new_answer) to complete the task."
                            enforcement_reason = "no_workflow_tool"
                            tool_names_called = [agent.backend.extract_tool_name(tc) for tc in tool_calls]
                        else:
                            # No tool calls, just a plain text response - use default enforcement
                            if is_decomposition:
                                error_msg = "You must use workflow tools (stop or new_answer) to complete the task."
                            else:
                                error_msg = "You must use workflow tools (vote or new_answer) to complete the task."
                            enforcement_reason = "no_tool_calls"
                            tool_names_called = []

                        yield (
                            "content",
                            f"❌ Retry ({attempt + 1}/{max_attempts}): {error_msg}",
                        )

                        # Get full buffer content for injection into retry message.
                        # We keep only a bounded recent tail to avoid retry prompt blowups.
                        full_buffer_content = None
                        if hasattr(agent.backend, "_get_streaming_buffer"):
                            full_buffer_content = agent.backend._get_streaming_buffer()
                        truncated_buffer_content = self._truncate_enforcement_buffer_content(full_buffer_content)

                        # Track enforcement event before retry (with truncated preview for logging)
                        buffer_preview = full_buffer_content[:500] if full_buffer_content and len(full_buffer_content) > 500 else full_buffer_content
                        buffer_chars = len(full_buffer_content) if full_buffer_content else 0
                        self.coordination_tracker.track_enforcement_event(
                            agent_id=agent_id,
                            reason=enforcement_reason,
                            attempt=attempt + 1,
                            max_attempts=max_attempts,
                            tool_calls=tool_names_called,
                            error_message=error_msg,
                            buffer_preview=buffer_preview,
                            buffer_chars=buffer_chars,
                        )

                        # If there were tool calls, we must provide tool results before continuing
                        # (Response API requires function_call + function_call_output pairs).
                        # Filter out unknown tool calls first: backends like Claude strip their
                        # tool_use blocks from history, so a tool_result for them causes a 400.
                        enforcement_tool_calls = (
                            agent.backend.filter_enforcement_tool_calls(
                                tool_calls,
                                unknown_tool_calls,
                            )
                            if tool_calls
                            else []
                        )
                        if enforcement_tool_calls:
                            enforcement_msg = self._create_tool_error_messages(
                                agent,
                                enforcement_tool_calls,
                                error_msg,
                            )
                        else:
                            # Include buffer content so agent can continue from where it left off
                            if full_buffer_content:
                                if truncated_buffer_content and len(truncated_buffer_content) < len(full_buffer_content):
                                    logger.info(
                                        "[Orchestrator] Truncated enforcement buffer for %s from %d to %d chars",
                                        agent_id,
                                        len(full_buffer_content),
                                        len(truncated_buffer_content),
                                    )
                                logger.info(
                                    f"[Orchestrator] Injecting {len(truncated_buffer_content or '')} chars of buffer content into enforcement retry for {agent_id}",
                                )
                            enforcement_msg = self.message_templates.enforcement_message(
                                buffer_content=truncated_buffer_content,
                            )
                        attempt += 1  # Error counts as an attempt
                        continue  # Retry with updated conversation
                    else:
                        # Last attempt failed, agent did not provide proper workflow response
                        yield (
                            "error",
                            f"Agent failed to use workflow tools after {max_attempts} attempts",
                        )
                        yield ("done", None)
                        return

        except Exception as e:
            _agent_outcome = "error"
            _agent_error_message = str(e)
            yield ("error", f"Agent execution failed: {str(e)}")
            yield ("done", None)
        finally:
            # Hook manager cleanup is automatic - no explicit cleanup needed
            # The GeneralHookManager is recreated for each agent run

            # Add outcome attributes to agent execution span
            if _agent_outcome:
                _agent_span.set_attribute("massgen.outcome", _agent_outcome)
            if _agent_voted_for:
                _agent_span.set_attribute("massgen.voted_for", _agent_voted_for)
            if _agent_voted_for_label:
                _agent_span.set_attribute(
                    "massgen.voted_for_label",
                    _agent_voted_for_label,
                )
            if _agent_answer_label:
                _agent_span.set_attribute("massgen.answer_label", _agent_answer_label)
            if _agent_error_message:
                _agent_span.set_attribute("massgen.error_message", _agent_error_message)

            # Add token usage and cost to agent execution span before closing
            # Note: Use "usage" instead of "tokens" to avoid logfire's security scrubbing
            if hasattr(agent.backend, "token_usage") and agent.backend.token_usage:
                token_usage = agent.backend.token_usage
                _agent_span.set_attribute(
                    "massgen.usage.input",
                    token_usage.input_tokens or 0,
                )
                _agent_span.set_attribute(
                    "massgen.usage.output",
                    token_usage.output_tokens or 0,
                )
                _agent_span.set_attribute(
                    "massgen.usage.reasoning",
                    token_usage.reasoning_tokens or 0,
                )
                _agent_span.set_attribute(
                    "massgen.usage.cached_input",
                    token_usage.cached_input_tokens or 0,
                )
                _agent_span.set_attribute(
                    "massgen.usage.cost",
                    round(token_usage.estimated_cost or 0, 6),
                )

            # Close the agent execution span for hierarchical tracing
            # Wrap in broad try/except so span-exit errors cannot prevent
            # round-isolation cleanup below from executing.
            try:
                _agent_span_cm.__exit__(None, None, None)
            except Exception as e:
                # Context detach failures are expected in async generators.
                # Any other error is logged but must not block cleanup.
                if isinstance(e, ValueError) and ("context" in str(e).lower() or "detach" in str(e).lower()):
                    pass
                else:
                    logger.debug(f"Error closing agent span (non-fatal): {e}")

            # Per-round worktree cleanup: move scratch, remove worktree, keep branch
            if agent_id in self._round_isolation_managers:
                round_iso = self._round_isolation_managers.pop(agent_id)
                # Use anonymous ID for human-readable archive directory name
                _agent_mapping = self.coordination_tracker.get_reverse_agent_mapping()
                _archive_label = _agent_mapping.get(agent_id, agent_id)
                for ctx_info in list(round_iso.list_contexts()):
                    ctx_path = ctx_info.get("original_path") if ctx_info else None
                    if not ctx_path:
                        continue
                    try:
                        round_iso.move_scratch_to_workspace(ctx_path, archive_label=_archive_label)
                        round_iso.cleanup_round(ctx_path)
                    except Exception as _cleanup_err:
                        logger.warning(f"[Orchestrator] Round worktree cleanup failed for {agent_id}: {_cleanup_err}")
                self._round_worktree_paths.pop(agent_id, None)

            # Clear the round context
            clear_current_round()

    async def _get_next_chunk(self, stream: AsyncGenerator[tuple, None]) -> tuple:
        """Get the next chunk from an agent stream."""
        try:
            return await stream.__anext__()
        except StopAsyncIteration:
            return ("done", None)
        except asyncio.CancelledError:
            raise  # Must re-raise CancelledError
        except Exception as e:
            return ("error", str(e))

    def _has_write_context_paths(self, agent: "ChatAgent") -> bool:
        """
        Check if agent has any context paths with write permission configured.

        Args:
            agent: The agent to check

        Returns:
            True if agent has write context paths, False otherwise
        """
        if not hasattr(agent, "backend") or not agent.backend:
            return False
        filesystem_manager = getattr(agent.backend, "filesystem_manager", None)
        if not filesystem_manager:
            return False
        ppm = getattr(filesystem_manager, "path_permission_manager", None)
        if not ppm:
            return False
        return any(mp.will_be_writable for mp in ppm.managed_paths if mp.path_type == "context")

    def _enable_context_write_access(self, agent: "ChatAgent") -> None:
        """
        Enable write access for context paths on the given agent.

        Args:
            agent: The agent to enable write access for
        """
        if not hasattr(agent, "backend") or not agent.backend:
            return
        filesystem_manager = getattr(agent.backend, "filesystem_manager", None)
        if not filesystem_manager:
            return
        ppm = getattr(filesystem_manager, "path_permission_manager", None)
        if not ppm:
            return
        ppm.set_context_write_access_enabled(True)
        logger.info(f"[Orchestrator] Enabled context write access for agent: {agent.agent_id}")

    def get_context_path_writes(self) -> list[str]:
        """
        Get list of files written to context paths by the final agent.

        Returns:
            List of file paths written to context paths
        """
        if not self._selected_agent:
            return []
        agent = self.agents.get(self._selected_agent)
        if not agent or not hasattr(agent, "backend") or not agent.backend:
            return []
        filesystem_manager = getattr(agent.backend, "filesystem_manager", None)
        if not filesystem_manager:
            return []
        ppm = getattr(filesystem_manager, "path_permission_manager", None)
        if not ppm:
            return []
        return ppm.get_context_path_writes()

    def get_context_path_writes_categorized(self) -> dict[str, list[str]]:
        """
        Get categorized lists of new and modified files in context paths.

        Returns:
            Dict with 'new' and 'modified' keys, each containing a list of file paths
        """
        if not self._selected_agent:
            return {"new": [], "modified": []}
        agent = self.agents.get(self._selected_agent)
        if not agent or not hasattr(agent, "backend") or not agent.backend:
            return {"new": [], "modified": []}
        filesystem_manager = getattr(agent.backend, "filesystem_manager", None)
        if not filesystem_manager:
            return {"new": [], "modified": []}
        ppm = getattr(filesystem_manager, "path_permission_manager", None)
        if not ppm:
            return {"new": [], "modified": []}
        return ppm.get_context_path_writes_categorized()

    def _clear_context_path_write_tracking(self) -> None:
        """Clear context path write tracking for all agents at the start of each turn."""
        for agent_id, agent in self.agents.items():
            if not hasattr(agent, "backend") or not agent.backend:
                continue
            filesystem_manager = getattr(agent.backend, "filesystem_manager", None)
            if not filesystem_manager:
                continue
            ppm = getattr(filesystem_manager, "path_permission_manager", None)
            if ppm and hasattr(ppm, "clear_context_path_writes"):
                ppm.clear_context_path_writes()
                logger.debug(f"[Orchestrator] Cleared context path write tracking for {agent_id}")

    async def _yield_existing_answer_finalization(
        self,
        *,
        selected_agent_id: str,
        vote_results: dict[str, Any],
        force_workspace_snapshot: bool = False,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Finalize by reusing an already-available answer without a presenter pass."""
        existing_answer = self.agent_states[selected_agent_id].answer
        if not existing_answer:
            return

        agent = self.agents.get(selected_agent_id)

        _emitter = get_event_emitter()
        if _emitter:
            _emitter.emit_winner_selected(
                winner_id=selected_agent_id,
                vote_results=vote_results,
            )
            _emitter.emit_answer_locked(
                agent_id=selected_agent_id,
            )

        log_stream_chunk(
            "orchestrator",
            "content",
            f"\n{existing_answer}\n",
            selected_agent_id,
        )
        yield StreamChunk(
            type="content",
            content=f"\n{existing_answer}\n",
            source=selected_agent_id,
        )
        self._final_presentation_content = existing_answer

        if force_workspace_snapshot and agent and hasattr(agent, "backend") and agent.backend:
            filesystem_manager = getattr(agent.backend, "filesystem_manager", None)
            if filesystem_manager:
                await filesystem_manager.save_snapshot(
                    timestamp=None,
                    is_final=True,
                )

        # Restore workspace from latest per-round answer dir before final save.
        # In timeout/fallback paths, the workspace may have been cleared between
        # rounds and only has scaffolding — the real deliverables are in the
        # per-round answer directories.
        self._restore_workspace_from_latest_answer_dir(selected_agent_id)

        final_context = self.get_last_context(selected_agent_id)
        await self._save_agent_snapshot(
            selected_agent_id,
            answer_content=existing_answer,
            is_final=True,
            context_data=final_context,
        )

        self.coordination_tracker.set_final_answer(
            selected_agent_id,
            existing_answer,
            snapshot_timestamp="final",
        )

        if agent and agent.backend.filesystem_manager:
            agent.backend.filesystem_manager.path_permission_manager.compute_context_path_writes()

        self.add_to_history("assistant", existing_answer)
        self.save_coordination_logs()
        self.workflow_phase = "presenting"
        await self._show_workspace_modal_if_needed()

        log_stream_chunk("orchestrator", "done", None, selected_agent_id)
        yield StreamChunk(type="done", source=selected_agent_id)

    async def _present_final_answer(self) -> AsyncGenerator[StreamChunk, None]:
        """Present the final coordinated answer with optional post-evaluation and restart loop."""

        # Select the best agent based on current state
        if not self._selected_agent:
            self._selected_agent = self._determine_final_agent_from_states()

        if not self._selected_agent:
            error_msg = "❌ Unable to provide coordinated answer - no successful agents"
            await self._save_partial_snapshots_for_early_termination()
            self.add_to_history("assistant", error_msg)
            log_stream_chunk("orchestrator", "error", error_msg)
            yield StreamChunk(type="content", content=error_msg)
            self.workflow_phase = "presenting"
            log_stream_chunk("orchestrator", "done", None)
            yield StreamChunk(type="done")
            return

        # Get vote results for presentation
        vote_results = self._get_vote_results()

        # Emit status event for TUI event pipeline

        _emitter = get_event_emitter()
        if _emitter:
            _emitter.emit_status(
                "Presenting final coordinated answer",
                level="info",
                agent_id=self._selected_agent,
            )

        log_stream_chunk("orchestrator", "content", "## 🎯 Final Coordinated Answer\n")
        yield StreamChunk(
            type="coordination" if self.trace_classification == "strict" else "content",
            content="## 🎯 Final Coordinated Answer\n",
        )

        # Stream final presentation from winning agent
        log_stream_chunk(
            "orchestrator",
            "content",
            f"🏆 Selected Agent: {self._selected_agent}\n",
        )
        yield StreamChunk(
            type="coordination" if self.trace_classification == "strict" else "content",
            content=f"🏆 Selected Agent: {self._selected_agent}\n",
        )

        # Check if we should skip final presentation (quick mode - refinement OFF)
        if self.config.skip_final_presentation:
            # Check if we have write context paths - this affects whether we can skip
            agent = self.agents.get(self._selected_agent)
            has_write_context_paths = self._has_write_context_paths(agent) if agent else False
            is_single_agent_mode = self.config.skip_voting  # skip_voting implies single-agent mode
            final_answer_strategy = self._get_final_answer_strategy()
            should_skip_presentation = is_single_agent_mode or (final_answer_strategy == "winner_reuse" and not has_write_context_paths)

            # Decision matrix:
            # - Single agent + write paths: Enable writes directly (no LLM call), skip presentation
            # - Multi-agent + winner_reuse + write paths: Need final presentation to copy files
            # - Multi-agent + winner_present/synthesize: Keep presenter stage even without write paths

            if is_single_agent_mode and has_write_context_paths:
                # Single agent mode with write context paths:
                # Write access was already enabled at start of coordination (in _stream_agent_execution)
                # and snapshot was taken then, so we just skip to the presentation logic
                logger.info(
                    "[skip_final_presentation] Single agent mode with write context paths - writes already enabled at coordination start",
                )

            elif final_answer_strategy == "winner_reuse" and has_write_context_paths:
                logger.info(
                    "[skip_final_presentation] Multi-agent winner_reuse with write context paths - falling through to final presentation",
                )

            elif final_answer_strategy in {"winner_present", "synthesize"}:
                logger.info(
                    "[skip_final_presentation] Keeping presenter stage because final_answer_strategy=%s",
                    final_answer_strategy,
                )

            if should_skip_presentation:
                if self.agent_states[self._selected_agent].answer:
                    async for chunk in self._yield_existing_answer_finalization(
                        selected_agent_id=self._selected_agent,
                        vote_results=vote_results,
                        force_workspace_snapshot=is_single_agent_mode,
                    ):
                        yield chunk
                    return
                else:
                    # No existing answer - fall through to normal presentation
                    logger.warning(
                        f"[skip_final_presentation] No existing answer for {self._selected_agent}, falling back to normal presentation",
                    )

        # Stream the final presentation (with full tool support)
        presentation_content = ""
        async for chunk in self.get_final_presentation(
            self._selected_agent,
            vote_results,
        ):
            if chunk.type == "content" and chunk.content:
                presentation_content += chunk.content
            yield chunk

        # NOTE: end_round_tracking("presentation") and save_coordination_logs() are now called
        # inside _handle_presentation_phase BEFORE yielding the done chunk.
        # This is necessary because UI consumers break out of the loop on "done" chunk,
        # so cleanup must happen before the done is yielded.

        # Check if post-evaluation should run
        # Skip post-evaluation on final attempt (user clarification #4)
        is_final_attempt = self.current_attempt >= (self.max_attempts - 1)
        should_evaluate = self.max_attempts > 1 and not is_final_attempt

        if should_evaluate:
            # Run post-evaluation
            final_answer_to_evaluate = self._final_presentation_content or presentation_content
            async for chunk in self.post_evaluate_answer(
                self._selected_agent,
                final_answer_to_evaluate,
            ):
                yield chunk

            # End round tracking for post-evaluation phase (moved from post_evaluate_answer finally block
            # to ensure it completes before save_coordination_logs is called)
            if self._selected_agent:
                selected_agent = self.agents.get(self._selected_agent)
                if selected_agent and hasattr(
                    selected_agent.backend,
                    "end_round_tracking",
                ):
                    selected_agent.backend.end_round_tracking("post_evaluation")

        # Show workspace modal in no-git mode (runs before clear_workspace below)
        await self._show_workspace_modal_if_needed()

        # Review isolated changes if write_mode isolation was enabled
        # Runs AFTER post-evaluation so the user sees the full picture before approving files
        if self._isolation_manager:
            selected_agent = self.agents.get(self._selected_agent)
            if selected_agent:
                # Re-add removed context paths so ChangeApplier can write back
                ppm = selected_agent.backend.filesystem_manager.path_permission_manager
                for orig_path, removed_mp in self._isolation_removed_paths.items():
                    ppm.re_add_context_path(removed_mp)

                async for chunk in self._review_isolated_changes(
                    agent=selected_agent,
                    isolation_manager=self._isolation_manager,
                    selected_agent_id=self._selected_agent,
                ):
                    yield chunk

            # Check if rework was requested — if so, keep isolation alive
            if self._pending_review_rework:
                # Isolation is preserved; the display layer will handle
                # re-submission with feedback. Do NOT clear references.
                logger.info(
                    "[Orchestrator] Review rework requested: %s",
                    self._pending_review_rework,
                )
            else:
                # Clear the references after review
                self._isolation_manager = None
                self._isolation_worktree_paths = {}
                self._isolation_removed_paths = {}

            # Check if restart was requested
            if self.restart_pending and self.current_attempt < (self.max_attempts - 1):
                # Show restart banner
                restart_banner = f"""

🔄 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   ORCHESTRATION RESTART (Attempt {self.current_attempt + 2}/{self.max_attempts})
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

REASON:
{self.restart_reason}

INSTRUCTIONS FOR NEXT ATTEMPT:
{self.restart_instructions}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
                log_stream_chunk("orchestrator", "status", restart_banner)
                yield StreamChunk(
                    type="restart_banner",
                    content=restart_banner,
                    source="orchestrator",
                )

                # Reset state for restart (prepare for next coordinate() call)
                self.handle_restart()

                # Don't add to history or set workflow phase - restart is pending
                # Exit here - CLI will detect restart_pending and call coordinate() again
                return

        # No restart - emit answer_locked event now that answer is confirmed

        _emitter = get_event_emitter()
        if _emitter:
            _emitter.emit_answer_locked(agent_id=self._selected_agent)

        # Clear workspace after submit since orchestration is complete
        if self._selected_agent:
            agent = self.agents.get(self._selected_agent)
            if agent and agent.backend.filesystem_manager:
                agent.backend.filesystem_manager.clear_workspace()
                logger.info(
                    f"[Orchestrator._present_final_answer] Cleared workspace for {self._selected_agent} after submit",
                )

        # Add final answer to conversation history
        if self._final_presentation_content:
            self.add_to_history("assistant", self._final_presentation_content)

        # NOTE: save_coordination_logs() is already called inside _handle_presentation_phase
        # before yielding the done chunk. This code path is never reached because UI breaks
        # on the done chunk from _handle_presentation_phase.

        # Update workflow phase
        self.workflow_phase = "presenting"
        log_stream_chunk("orchestrator", "done", None)
        yield StreamChunk(type="done")

    async def _handle_orchestrator_timeout(self) -> AsyncGenerator[StreamChunk, None]:
        """Handle orchestrator timeout by salvaging the best available answer."""
        # Count available answers
        available_answers = {aid: state.answer for aid, state in self.agent_states.items() if state.answer and not state.is_killed}

        # Determine best available agent for presentation (if any answers exist)
        current_votes = {aid: state.votes for aid, state in self.agent_states.items() if state.votes and not state.is_killed}
        selected_agent = None
        selection_reason = "no answers available"

        if available_answers:
            if current_votes:
                selected_agent = self._determine_final_agent_from_votes(
                    current_votes,
                    available_answers,
                )
                selection_reason = "most votes"
            else:
                selected_agent = self._determine_final_agent_from_states()
                if selected_agent not in available_answers:
                    selected_agent = next(iter(available_answers))
                selection_reason = "latest answer"

        # Build per-agent summary
        agent_answer_summary = {}
        for aid, state in self.agent_states.items():
            if state.is_killed:
                continue
            vote_count = 0
            for v in current_votes.values():
                if v.get("agent_id") == aid:
                    vote_count += 1
            agent_answer_summary[aid] = {
                "has_answer": bool(state.answer),
                "vote_count": vote_count,
            }

        # Emit structured event for TUI

        _timeout_emitter = get_event_emitter()
        if _timeout_emitter:
            _timeout_emitter.emit_orchestrator_timeout(
                timeout_reason=self.timeout_reason or "Unknown",
                available_answers=len(available_answers),
                selected_agent=selected_agent,
                selection_reason=selection_reason,
                agent_answer_summary=agent_answer_summary,
            )

        # Also yield as StreamChunk for non-TUI displays
        log_stream_chunk(
            "orchestrator",
            "content",
            f"\n⚠️ **Orchestrator Timeout**: {self.timeout_reason}\n",
            self.orchestrator_id,
        )
        yield StreamChunk(
            type="content",
            content=f"\n⚠️ **Orchestrator Timeout**: {self.timeout_reason}\n",
            source=self.orchestrator_id,
        )

        # If no answers available, provide fallback with timeout explanation
        if len(available_answers) == 0:
            await self._save_partial_snapshots_for_early_termination()
            log_stream_chunk(
                "orchestrator",
                "error",
                "❌ No answers available from any agents due to timeout. No agents had enough time to provide responses.\n",
                self.orchestrator_id,
            )
            yield StreamChunk(
                type="content",
                content="❌ No answers available from any agents due to timeout. No agents had enough time to provide responses.\n",
                source=self.orchestrator_id,
            )
            self.workflow_phase = "presenting"
            log_stream_chunk("orchestrator", "done", None)
            yield StreamChunk(type="done")
            return

        self._selected_agent = selected_agent

        vote_results = self._get_vote_results()
        log_stream_chunk(
            "orchestrator",
            "content",
            f"🎯 Using available answer from {self._selected_agent} (selected despite timeout)\n",
            self.orchestrator_id,
        )
        yield StreamChunk(
            type="content",
            content=f"🎯 Using available answer from {self._selected_agent} (selected despite timeout)\n",
            source=self.orchestrator_id,
        )

        async for chunk in self._yield_existing_answer_finalization(
            selected_agent_id=self._selected_agent,
            vote_results=vote_results,
        ):
            yield chunk

        # NOTE: end_round_tracking("presentation") and save_coordination_logs() are now called
        # inside _handle_presentation_phase BEFORE yielding the done chunk.
        # This code path is never reached because UI breaks on the done chunk.

    def _determine_final_agent_from_votes(
        self,
        votes: dict[str, dict],
        agent_answers: dict[str, str],
    ) -> str:
        """Determine which agent should present the final answer based on votes."""
        if not votes:
            # No votes yet, return first agent with an answer (earliest by generation time)
            return next(iter(agent_answers)) if agent_answers else None

        # Count votes for each agent
        vote_counts = {}
        for vote_data in votes.values():
            voted_for = vote_data.get("agent_id")
            if voted_for:
                vote_counts[voted_for] = vote_counts.get(voted_for, 0) + 1

        if not vote_counts:
            return next(iter(agent_answers)) if agent_answers else None

        # Find agents with maximum votes
        max_votes = max(vote_counts.values())
        tied_agents = [agent_id for agent_id, count in vote_counts.items() if count == max_votes]

        # Break ties by agent registration order (order in agent_states dict)
        for agent_id in agent_answers.keys():
            if agent_id in tied_agents:
                return agent_id

        # Fallback to first tied agent
        return tied_agents[0] if tied_agents else next(iter(agent_answers)) if agent_answers else None

    async def get_final_presentation(
        self,
        selected_agent_id: str,
        vote_results: dict[str, Any],
    ) -> AsyncGenerator[StreamChunk, None]:
        """Ask the winning agent to present their final answer with voting context."""
        # Guard against duplicate presentations (e.g., if timeout handler runs after presentation started)
        if self._presentation_started:
            logger.warning(
                f"Presentation already started, skipping duplicate call for {selected_agent_id}",
            )
            yield StreamChunk(
                type="status",
                content="Presentation already in progress, skipping duplicate...",
            )
            return
        self._presentation_started = True

        # Start tracking the final round
        self.coordination_tracker.start_final_round(selected_agent_id)

        if selected_agent_id not in self.agents:
            log_stream_chunk(
                "orchestrator",
                "error",
                f"Selected agent {selected_agent_id} not found",
            )
            yield StreamChunk(
                type="error",
                error=f"Selected agent {selected_agent_id} not found",
            )
            return

        agent = self.agents[selected_agent_id]

        # Create presentation span for hierarchical tracing in Logfire
        tracer = get_tracer()
        final_round = self.coordination_tracker.get_agent_round(selected_agent_id)
        backend_name = agent.backend.get_provider_name() if hasattr(agent.backend, "get_provider_name") else "unknown"

        span_attributes = {
            "massgen.agent_id": selected_agent_id,
            "massgen.iteration": self.coordination_tracker.current_iteration,
            "massgen.round": final_round,
            "massgen.round_type": "presentation",
            "massgen.backend": backend_name,
            "massgen.is_winner": True,
            "massgen.vote_count": vote_results.get("vote_counts", {}).get(
                selected_agent_id,
                0,
            ),
        }

        _presentation_span_cm = tracer.span(
            f"agent.{selected_agent_id}.presentation",
            attributes=span_attributes,
        )
        _presentation_span = _presentation_span_cm.__enter__()  # Capture yielded span for set_attribute()

        # Set the round context for nested tool calls to use
        set_current_round(final_round, "presentation")

        # Enable write access for final agent on context paths. This ensures that those paths marked `write` by the user are now writable (as all previous agents were read-only).
        if agent.backend.filesystem_manager:
            # Snapshot context paths BEFORE enabling write access (for tracking what gets written)
            agent.backend.filesystem_manager.path_permission_manager.snapshot_writable_context_paths()

            # Initialize isolated write context if write_mode is enabled
            # Creates worktree inside agent workspace and demotes original to read-only
            self._isolation_manager = None
            self._isolation_worktree_paths = {}  # worktree_path -> original_path
            write_mode = None
            if self.config.coordination_config:
                write_mode = getattr(self.config.coordination_config, "write_mode", None)

            logger.info(f"[Orchestrator] write_mode check: coordination_config={bool(self.config.coordination_config)}, write_mode={write_mode}")

            if write_mode and write_mode != "legacy":
                from .filesystem_manager import IsolationContextManager

                try:
                    workspace_path = str(agent.backend.filesystem_manager.get_current_workspace())
                    # Use winner's branch as base for the worktree so final presentation
                    # starts from the winner's committed work (not empty HEAD)
                    winner_branch = self._agent_current_branches.get(selected_agent_id)
                    self._isolation_manager = IsolationContextManager(
                        session_id=self.session_id,
                        write_mode=write_mode,
                        workspace_path=workspace_path,
                        base_commit=winner_branch,
                        branch_label="presenter",
                    )

                    # Initialize isolated contexts for writable context paths
                    # Remove the original from PPM so the agent only sees the worktree
                    ppm = agent.backend.filesystem_manager.path_permission_manager
                    self._isolation_removed_paths = {}  # original_path -> ManagedPath (for re-adding after review)
                    logger.info(f"[Orchestrator] Checking {len(ppm.managed_paths)} managed paths for isolation")
                    for managed_path in list(ppm.managed_paths):  # copy list since we modify
                        logger.debug(f"[Orchestrator] Checking path: {managed_path.path}, type={managed_path.path_type}, will_be_writable={managed_path.will_be_writable}")
                        if managed_path.path_type == "context" and managed_path.will_be_writable:
                            original_path = str(managed_path.path)
                            isolated_path = self._isolation_manager.initialize_context(
                                original_path,
                                agent_id=selected_agent_id,
                            )
                            # Remove original from PPM — agent only sees the worktree in workspace
                            removed_mp = ppm.remove_context_path(original_path)
                            if removed_mp:
                                self._isolation_removed_paths[original_path] = removed_mp
                            self._isolation_worktree_paths[isolated_path] = original_path
                            logger.info(
                                f"[Orchestrator] Isolation: worktree at {isolated_path}, " f"original removed from agent view: {original_path}",
                            )

                except Exception as e:
                    logger.warning(f"[Orchestrator] Failed to initialize isolated context: {e}, falling back to direct writes")
                    # Re-add any paths we removed before the failure
                    if self._isolation_removed_paths:
                        ppm = agent.backend.filesystem_manager.path_permission_manager
                        for orig_path, removed_mp in self._isolation_removed_paths.items():
                            ppm.re_add_context_path(removed_mp)
                        self._isolation_removed_paths = {}
                    if self._isolation_manager:
                        try:
                            self._isolation_manager.cleanup_all()
                        except Exception:
                            pass
                    self._isolation_manager = None
                    self._isolation_worktree_paths = {}
                    yield StreamChunk(
                        type="status",
                        content="⚠️  File isolation unavailable — changes will be written directly without review.",
                        source=selected_agent_id,
                    )

            # Recreate Docker container with write access to context paths
            # The original container was created with read-only mounts for context paths
            # (to prevent race conditions during coordination). For final presentation,
            # we need write access so the agent can write to context paths via shell commands.
            if agent.backend.filesystem_manager.docker_manager:
                skills_directory = None
                massgen_skills = []
                load_previous_session_skills = False
                if self.config.coordination_config:
                    if self.config.coordination_config.use_skills:
                        skills_directory = self.config.coordination_config.skills_directory
                        massgen_skills = self.config.coordination_config.massgen_skills or []
                        load_previous_session_skills = getattr(
                            self.config.coordination_config,
                            "load_previous_session_skills",
                            False,
                        )
                # Build extra mounts for worktree isolation in Docker mode
                extra_mounts = None
                if self._isolation_worktree_paths:
                    extra_mounts = [(wt_path, wt_path, "rw") for wt_path in self._isolation_worktree_paths]

                agent.backend.filesystem_manager.recreate_container_for_write_access(
                    skills_directory=skills_directory,
                    massgen_skills=massgen_skills,
                    load_previous_session_skills=load_previous_session_skills,
                    extra_mount_paths=extra_mounts,
                )

            # Enable write access in PathPermissionManager (for MCP filesystem tools)
            agent.backend.filesystem_manager.path_permission_manager.set_context_write_access_enabled(
                True,
            )

        # Reset backend planning mode to allow MCP tool execution during final presentation
        if hasattr(agent.backend, "set_planning_mode"):
            agent.backend.set_planning_mode(False)
            logger.info(
                f"[Orchestrator] Backend planning mode DISABLED for final presentation: {selected_agent_id} - MCP tools now allowed",
            )

        # Copy all agents' snapshots to temp workspace to preserve context from coordination phase
        # This allows the agent to reference and access previous work
        temp_workspace_path = await self._copy_all_snapshots_to_temp_workspace(
            selected_agent_id,
        )
        yield StreamChunk(
            type="debug",
            content=f"Restored workspace context for final presentation: {temp_workspace_path}",
            source=selected_agent_id,
        )

        presentation_strategy = self._get_final_answer_strategy()

        # Prepare context about the voting
        vote_counts = vote_results.get("vote_counts", {})
        voter_details = vote_results.get("voter_details", {})
        is_tie = vote_results.get("is_tie", False)

        # Build voting summary -- note we only include the number of votes and reasons for the selected agent. There is no information about the distribution of votes beyond this.
        if presentation_strategy == "synthesize" and not vote_counts and not voter_details:
            voting_summary = "No voting round was run. You were selected as the presenter to " "synthesize the final answer from all completed answers."
        else:
            voting_summary = f"You received {vote_counts.get(selected_agent_id, 0)} vote(s)"
            if voter_details.get(selected_agent_id):
                reasons = [v["reason"] for v in voter_details[selected_agent_id]]
                voting_summary += f" with feedback: {'; '.join(reasons)}"

            if is_tie:
                voting_summary += " (tie-broken by registration order)"

        # Get all answers for context
        all_answers = {aid: s.answer for aid, s in self.agent_states.items() if s.answer}

        # Normalize workspace paths in both voting summary and all answers for final presentation. Use same function for consistency.
        normalized_voting_summary = self._normalize_workspace_paths_in_answers(
            {selected_agent_id: voting_summary},
            selected_agent_id,
        )[selected_agent_id]
        normalized_all_answers = self._normalize_workspace_paths_in_answers(
            all_answers,
            selected_agent_id,
        )

        # Build the presentation message
        is_decomposition = getattr(self.config, "coordination_mode", "voting") == "decomposition"
        if is_decomposition:
            # Decomposition mode: presenter synthesizes all agents' work
            agent_work_sections = []
            for aid, answer in normalized_all_answers.items():
                subtask = self._agent_subtasks.get(aid, "No specific subtask assigned")
                stop_summary = self.agent_states[aid].stop_summary or "No stop summary"
                agent_work_sections.append(
                    f"**{aid}** (subtask: {subtask})\n" f"Stop summary: {stop_summary}\n" f"Work: {answer}\n",
                )
            presentation_content = (
                f"ORIGINAL TASK:\n{self.current_task or 'Task coordination'}\n\n"
                f"AGENT WORK SUMMARIES:\n{''.join(agent_work_sections)}\n\n"
                "Your job is to assemble the final deliverable from the work each agent produced. "
                "Ensure quality, fill any gaps, resolve conflicts, and answer the original query comprehensively."
            )
        else:
            if presentation_strategy == "winner_reuse":
                # If we still reached presenter stage, winner_reuse could not be honored directly
                # (for example because write-path delivery requires a presentation pass).
                presentation_strategy = "winner_present"
            # Gather changedocs for final presentation
            _pres_changedocs = self._gather_agent_changedocs()
            presentation_content = self.message_templates.build_final_presentation_message(
                original_task=self.current_task or "Task coordination",
                vote_summary=normalized_voting_summary,
                all_answers=normalized_all_answers,
                selected_agent_id=selected_agent_id,
                agent_changedocs=_pres_changedocs,
                final_answer_strategy=presentation_strategy,
                had_voting=bool(vote_counts),
            )

        # Add worktree location to presentation message
        # The agent only sees the worktree — the original context path has been
        # removed from its view, so we just tell it where the project is.
        if self._isolation_worktree_paths:
            worktree_instructions = "\n\nPROJECT PATHS:\n"
            for wt_path, orig_path in self._isolation_worktree_paths.items():
                # Compute the specific subdirectory within the worktree
                # that corresponds to the original context path
                ctx_info = self._isolation_manager.get_context_info(orig_path) if self._isolation_manager else None
                repo_root = ctx_info.get("repo_root") if ctx_info else None
                if repo_root and repo_root != orig_path:
                    relative = os.path.relpath(orig_path, repo_root)
                    target_dir = os.path.join(wt_path, relative)
                    worktree_instructions += (
                        f"The project files are at `{target_dir}` " f"(inside worktree at `{wt_path}`). " f"Write all your changes there. " f"Changes will be reviewed before being applied.\n"
                    )
                else:
                    worktree_instructions += f"The project is checked out at `{wt_path}`. " f"Write all your changes there. " f"Changes will be reviewed before being applied.\n"

            # Add scratch and branch info for final presentation
            worktree_instructions += "\n**Scratch Space**: `.massgen_scratch/` inside the checkout is git-excluded and invisible to reviewers.\n"
            # Show other agents' latest branches with anonymous labels
            _pres_mapping = self.coordination_tracker.get_reverse_agent_mapping()
            other_branches = {_pres_mapping.get(aid, aid): branch for aid, branch in self._agent_current_branches.items() if aid != selected_agent_id and branch}
            if other_branches:
                worktree_instructions += "\n**Other agents' code branches** (latest only):\n"
                for label, branch in other_branches.items():
                    worktree_instructions += f"- {label}: `{branch}`\n"
                worktree_instructions += "Use `git diff <branch>` to compare, `git merge <branch>` to incorporate.\n"

            presentation_content += worktree_instructions

        # Get agent's configurable system message using the standard interface
        agent.get_configurable_system_message()

        # Extract command execution parameters
        enable_command_execution = False
        docker_mode = False
        enable_sudo = False
        concurrent_tool_execution = False
        if hasattr(agent, "config") and agent.config:
            enable_command_execution = agent.config.backend_params.get(
                "enable_mcp_command_line",
                False,
            )
            docker_mode = agent.config.backend_params.get("command_line_execution_mode", "local") == "docker"
            enable_sudo = agent.config.backend_params.get(
                "command_line_docker_enable_sudo",
                False,
            )
            concurrent_tool_execution = agent.config.backend_params.get(
                "concurrent_tool_execution",
                False,
            )
        elif hasattr(agent, "backend") and hasattr(agent.backend, "backend_params"):
            enable_command_execution = agent.backend.backend_params.get(
                "enable_mcp_command_line",
                False,
            )
            docker_mode = agent.backend.backend_params.get("command_line_execution_mode", "local") == "docker"
            enable_sudo = agent.backend.backend_params.get(
                "command_line_docker_enable_sudo",
                False,
            )
            concurrent_tool_execution = agent.backend.backend_params.get(
                "concurrent_tool_execution",
                False,
            )
        # Check if file generation is enabled for this agent
        enable_file_generation = False
        if hasattr(agent, "config") and agent.config:
            enable_file_generation = agent.config.backend_params.get(
                "enable_file_generation",
                False,
            )
        elif hasattr(agent, "backend") and hasattr(agent.backend, "backend_params"):
            enable_file_generation = agent.backend.backend_params.get(
                "enable_file_generation",
                False,
            )

        # Check if agent has write access to context paths (requires file delivery)
        has_irreversible_actions = False
        if agent.backend.filesystem_manager:
            context_paths = agent.backend.filesystem_manager.path_permission_manager.get_context_paths()
            # Check if any context path has write permission
            has_irreversible_actions = any(cp.get("permission") == "write" for cp in context_paths)

        # Build system message using section architecture
        # Determine artifact_type for spec-aware presenter instructions
        _presenter_artifact_type = None
        if self._plan_session_id:
            try:
                from massgen.plan_storage import PlanSession

                _ps = PlanSession(self._plan_session_id)
                _pm = _ps.load_metadata()
                _presenter_artifact_type = getattr(_pm, "artifact_type", None)
            except Exception:
                logger.opt(exception=True).warning(
                    f"[Orchestrator] Could not load artifact_type for presenter agent " f"(plan_session={self._plan_session_id}); artifact type context will be omitted.",
                )

        base_system_message = self._get_system_message_builder().build_presentation_message(
            agent=agent,
            all_answers=all_answers,
            previous_turns=self._previous_turns,
            enable_file_generation=enable_file_generation,
            has_irreversible_actions=has_irreversible_actions,
            enable_command_execution=enable_command_execution,
            docker_mode=docker_mode,
            enable_sudo=enable_sudo,
            concurrent_tool_execution=concurrent_tool_execution,
            agent_mapping=self.coordination_tracker.get_reverse_agent_mapping(),
            artifact_type=_presenter_artifact_type,
        )

        # Change the status of all agents that were not selected to AgentStatus.COMPLETED
        for aid, _ in self.agent_states.items():
            if aid != selected_agent_id:
                self.coordination_tracker.change_status(aid, AgentStatus.COMPLETED)

        self.coordination_tracker.set_final_agent(
            selected_agent_id,
            voting_summary,
            all_answers,
        )
        # Update status file for real-time monitoring
        # Run in executor to avoid blocking event loop
        log_session_dir = get_log_session_dir()
        if log_session_dir:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                self.coordination_tracker.save_status_file,
                log_session_dir,
                self,
            )

        # Create conversation with system and user messages
        presentation_messages = [
            {
                "role": "system",
                "content": base_system_message,
            },
            {"role": "user", "content": presentation_content},
        ]

        # Store the final context in agent state for saving
        self.agent_states[selected_agent_id].last_context = {
            "messages": presentation_messages,
            "is_final": True,
            "vote_summary": voting_summary,
            "all_answers": all_answers,
            "complete_vote_results": vote_results,  # Include ALL vote data
            "vote_counts": vote_counts,
            "voter_details": voter_details,
            "all_votes": {aid: state.votes for aid, state in self.agent_states.items() if state.votes},  # All individual votes
        }

        log_stream_chunk(
            "orchestrator",
            "status",
            f"🎤  [{selected_agent_id}] presenting final answer\n",
        )
        yield StreamChunk(
            type="status",
            content=f"🎤  [{selected_agent_id}] presenting final answer\n",
        )

        # Notify TUI to show fresh final presentation view
        # Build answer labels mapping for vote display (agent_id -> "A1.1" style label)
        answer_labels = {}
        if vote_counts:
            for aid in vote_counts.keys():
                label = self.coordination_tracker.get_latest_answer_label(aid)
                if label:
                    # Convert "agent1.1" to "A1.1"
                    answer_labels[aid] = label.replace("agent", "A")

        yield StreamChunk(
            type="final_presentation_start",
            content={
                "agent_id": selected_agent_id,
                "vote_counts": vote_counts,
                "answer_labels": answer_labels,
            },
            source=selected_agent_id,
        )

        # Emit event for unified pipeline

        _fp_emitter = get_event_emitter()
        if _fp_emitter:
            _fp_emitter.emit_final_presentation_start(
                agent_id=selected_agent_id,
                vote_counts=vote_counts,
                answer_labels=answer_labels,
                is_tie=vote_results.get("is_tie", False) if vote_results else False,
            )

        # Start round token tracking for final presentation
        final_round = self.coordination_tracker.get_agent_round(selected_agent_id)
        if hasattr(agent.backend, "start_round_tracking"):
            agent.backend.start_round_tracking(
                round_number=final_round,
                round_type="presentation",
                agent_id=selected_agent_id,
            )

        # Use agent's chat method with proper system message (reset chat for clean presentation)
        presentation_content = ""  # All content for display/logging
        clean_answer_content = ""  # Only clean text for answer.txt (excludes tool calls/results)
        submitted_answer = None  # Clean answer submitted via new_answer tool (preferred over clean_answer_content)
        final_snapshot_saved = False  # Track whether snapshot was saved during stream
        was_cancelled = False  # Track if we broke out due to cancellation

        # Build presentation tools: only new_answer (no vote/broadcast)
        from massgen.tool.workflow_toolkits import NewAnswerToolkit

        _na_toolkit = NewAnswerToolkit()
        presentation_tools = _na_toolkit.get_tools({"api_format": "chat_completions"})

        try:
            # Track final round iterations (each chunk is like an iteration)
            async for chunk in agent.chat(
                presentation_messages,
                presentation_tools,
                reset_chat=True,  # Reset conversation history for clean presentation
                current_stage=CoordinationStage.PRESENTATION,
                orchestrator_turn=self._current_turn,
                previous_winners=self._winning_agents_history.copy(),
            ):
                # Check for cancellation at the start of each chunk
                if hasattr(self, "cancellation_manager") and self.cancellation_manager and self.cancellation_manager.is_cancelled:
                    logger.info(
                        "Cancellation detected during final presentation - stopping streaming",
                    )
                    was_cancelled = True
                    # Yield a cancellation chunk so the UI knows to stop
                    yield StreamChunk(
                        type="cancelled",
                        content="Final presentation cancelled by user",
                        source=selected_agent_id,
                    )
                    break

                chunk_type = self._get_chunk_type_value(chunk)
                # Start new iteration for this chunk
                self.coordination_tracker.start_new_iteration()
                # Use the same streaming approach as regular coordination
                if chunk_type == "content" and chunk.content:
                    presentation_content += chunk.content
                    # Only add to clean answer if not tool-related content
                    if not self._is_tool_related_content(chunk.content):
                        clean_answer_content += chunk.content
                    log_stream_chunk(
                        "orchestrator",
                        "content",
                        chunk.content,
                        selected_agent_id,
                    )
                    yield StreamChunk(
                        type="content",
                        content=chunk.content,
                        source=selected_agent_id,
                    )
                    # Emit chunk event for unified pipeline
                    if _fp_emitter:
                        _fp_emitter.emit_final_presentation_chunk(
                            agent_id=selected_agent_id,
                            content=chunk.content,
                        )
                elif chunk_type in [
                    "reasoning",
                    "reasoning_done",
                    "reasoning_summary",
                    "reasoning_summary_done",
                ]:
                    # Emit structured event for TUI pipeline (same as main coordination loop)
                    if _fp_emitter:
                        is_done = chunk_type in ("reasoning_done", "reasoning_summary_done")
                        reasoning_delta = getattr(chunk, "reasoning_delta", None)
                        reasoning_text = getattr(chunk, "reasoning_text", None)
                        summary_delta = getattr(chunk, "reasoning_summary_delta", None)
                        _thinking_content = reasoning_delta or reasoning_text or summary_delta or ""
                        if _thinking_content or is_done:
                            from massgen.events import EventType

                            _fp_emitter.emit_raw(
                                EventType.THINKING,
                                content=_thinking_content,
                                done=is_done,
                                agent_id=selected_agent_id,
                            )

                    # Stream reasoning content with proper attribution (same as main coordination)
                    reasoning_chunk = StreamChunk(
                        type=chunk_type,
                        content=chunk.content,
                        source=selected_agent_id,
                        reasoning_delta=getattr(chunk, "reasoning_delta", None),
                        reasoning_text=getattr(chunk, "reasoning_text", None),
                        reasoning_summary_delta=getattr(
                            chunk,
                            "reasoning_summary_delta",
                            None,
                        ),
                        reasoning_summary_text=getattr(
                            chunk,
                            "reasoning_summary_text",
                            None,
                        ),
                        item_id=getattr(chunk, "item_id", None),
                        content_index=getattr(chunk, "content_index", None),
                        summary_index=getattr(chunk, "summary_index", None),
                    )
                    # Use the same format as main coordination for consistency
                    log_stream_chunk(
                        "orchestrator",
                        chunk.type,
                        chunk.content,
                        selected_agent_id,
                    )
                    yield reasoning_chunk
                elif chunk_type == "backend_status":
                    import json

                    status_json = json.loads(chunk.content)
                    cwd = status_json["cwd"]
                    session_id = status_json["session_id"]
                    content = f"""Final Temp Working directory: {cwd}.
    Final Session ID: {session_id}.
    """

                    log_stream_chunk(
                        "orchestrator",
                        "content",
                        content,
                        selected_agent_id,
                    )
                    yield StreamChunk(
                        type="content",
                        content=content,
                        source=selected_agent_id,
                    )
                elif chunk_type == "mcp_status":
                    # MCP status - preserve type for TUI tool tracking
                    mcp_content = f"🔧 MCP: {chunk.content}"
                    log_stream_chunk("orchestrator", "mcp_status", chunk.content, selected_agent_id)
                    yield StreamChunk(
                        type="mcp_status",
                        content=mcp_content,
                        source=selected_agent_id,
                        tool_call_id=getattr(chunk, "tool_call_id", None),
                    )
                elif chunk_type == "custom_tool_status":
                    # Custom tool status - preserve type for TUI tool tracking
                    custom_content = f"🔧 Custom Tool: {chunk.content}"
                    log_stream_chunk("orchestrator", "custom_tool_status", chunk.content, selected_agent_id)
                    yield StreamChunk(
                        type="custom_tool_status",
                        content=custom_content,
                        source=selected_agent_id,
                        tool_call_id=getattr(chunk, "tool_call_id", None),
                    )
                elif chunk_type == "tool_calls":
                    # Intercept new_answer tool calls to extract clean answer
                    chunk_tool_calls = getattr(chunk, "tool_calls", []) or []
                    for tool_call in chunk_tool_calls:
                        tool_name = agent.backend.extract_tool_name(tool_call)
                        if tool_name == "new_answer":
                            tool_args = agent.backend.extract_tool_arguments(tool_call)
                            if isinstance(tool_args, dict):
                                submitted_answer = self._coerce_answer_content_to_text(
                                    tool_args.get("content", ""),
                                )
                            elif isinstance(tool_args, str):
                                import json as _json

                                try:
                                    submitted_answer = self._coerce_answer_content_to_text(
                                        _json.loads(tool_args).get("content", ""),
                                    )
                                except (ValueError, AttributeError):
                                    submitted_answer = self._coerce_answer_content_to_text(
                                        tool_args,
                                    )
                    # Yield tool calls through so TUI can display them
                    yield StreamChunk(
                        type="tool_calls",
                        content=chunk.content,
                        source=selected_agent_id,
                        tool_calls=chunk_tool_calls,
                    )
                elif chunk_type == "hook_execution":
                    # Hook execution - pass through with source
                    log_stream_chunk(
                        "orchestrator",
                        "hook_execution",
                        str(getattr(chunk, "hook_info", "")),
                        selected_agent_id,
                    )
                    yield StreamChunk(
                        type="hook_execution",
                        content=chunk.content,
                        source=selected_agent_id,
                        hook_info=getattr(chunk, "hook_info", None),
                        tool_call_id=getattr(chunk, "tool_call_id", None),
                    )
                elif chunk_type == "done":
                    # Save the final workspace snapshot (from final workspace directory)
                    # Prefer submitted_answer (from new_answer tool) over clean_answer_content
                    if submitted_answer and submitted_answer.strip():
                        final_answer = submitted_answer.strip()
                    elif clean_answer_content.strip():
                        final_answer = clean_answer_content.strip()
                    else:
                        final_answer = self._coerce_answer_content_to_text(
                            self.agent_states[selected_agent_id].answer,
                        )
                    final_context = self.get_last_context(selected_agent_id)
                    await self._save_agent_snapshot(
                        self._selected_agent,
                        answer_content=final_answer,
                        is_final=True,
                        context_data=final_context,
                    )

                    # Track the final answer in coordination tracker (use clean content)
                    self.coordination_tracker.set_final_answer(
                        selected_agent_id,
                        final_answer,
                        snapshot_timestamp="final",
                    )

                    # Mark snapshot as saved
                    final_snapshot_saved = True

                    # End round tracking for presentation phase BEFORE yielding done
                    # (UI consumers break out of loop on "done" chunk, so cleanup must happen first)
                    agent = self.agents.get(self._selected_agent)
                    if agent and hasattr(agent.backend, "end_round_tracking"):
                        agent.backend.end_round_tracking("presentation")

                    # Save coordination logs BEFORE yielding done
                    # (ensures all round data is captured before UI breaks out of loop)
                    self.save_coordination_logs()

                    log_stream_chunk("orchestrator", "done", None, selected_agent_id)
                    yield StreamChunk(type="done", source=selected_agent_id)
                elif chunk_type == "error":
                    log_stream_chunk(
                        "orchestrator",
                        "error",
                        chunk.error,
                        selected_agent_id,
                    )
                    yield StreamChunk(
                        type="error",
                        error=chunk.error,
                        source=selected_agent_id,
                    )
                # Pass through other chunk types as-is but with source
                else:
                    if hasattr(chunk, "source"):
                        log_stream_chunk(
                            "orchestrator",
                            chunk_type,
                            getattr(chunk, "content", ""),
                            selected_agent_id,
                        )
                        yield StreamChunk(
                            type=chunk_type,
                            content=getattr(chunk, "content", ""),
                            source=selected_agent_id,
                            **{
                                k: v
                                for k, v in chunk.__dict__.items()
                                if k
                                not in [
                                    "type",
                                    "content",
                                    "source",
                                    "timestamp",
                                    "sequence_number",
                                ]
                            },
                        )
                    else:
                        log_stream_chunk(
                            "orchestrator",
                            chunk_type,
                            getattr(chunk, "content", ""),
                            selected_agent_id,
                        )
                        yield StreamChunk(
                            type=chunk_type,
                            content=getattr(chunk, "content", ""),
                            source=selected_agent_id,
                            **{
                                k: v
                                for k, v in chunk.__dict__.items()
                                if k
                                not in [
                                    "type",
                                    "content",
                                    "source",
                                    "timestamp",
                                    "sequence_number",
                                ]
                            },
                        )

        finally:
            # Ensure final snapshot is always saved (even if "done" chunk wasn't yielded)
            if not final_snapshot_saved:
                # Restore workspace in case it was cleared between rounds
                self._restore_workspace_from_latest_answer_dir(self._selected_agent)

                # Use clean_answer_content (excludes tool calls/results) for answer.txt
                final_answer = (
                    clean_answer_content.strip()
                    if clean_answer_content.strip()
                    else self._coerce_answer_content_to_text(
                        self.agent_states[selected_agent_id].answer,
                    )
                )
                final_context = self.get_last_context(selected_agent_id)
                await self._save_agent_snapshot(
                    self._selected_agent,
                    answer_content=final_answer,
                    is_final=True,
                    context_data=final_context,
                )

                # Track the final answer in coordination tracker (use clean content)
                self.coordination_tracker.set_final_answer(
                    selected_agent_id,
                    final_answer,
                    snapshot_timestamp="final",
                )

            # Store the final presentation content for post-evaluation and history
            # Prefer submitted_answer (from new_answer tool) over clean_answer_content
            _display_answer = submitted_answer.strip() if submitted_answer and submitted_answer.strip() else clean_answer_content.strip()
            if _display_answer:
                # Store the clean final answer (used by post-evaluation and conversation history)
                self._final_presentation_content = _display_answer

                # Emit final_answer event for TUI event pipeline

                _fa_emitter = get_event_emitter()
                if _fa_emitter:
                    _fa_emitter.emit_final_answer(
                        self._final_presentation_content,
                        agent_id=selected_agent_id,
                    )
            elif not was_cancelled:
                # Only yield fallback content if NOT cancelled - yielding after cancellation
                # causes display issues since the UI has already raised CancellationRequested
                stored_answer = self.agent_states[selected_agent_id].answer
                if stored_answer:
                    fallback_content = f"\n📋 Using stored answer as final presentation:\n\n{stored_answer}"
                    log_stream_chunk(
                        "orchestrator",
                        "content",
                        fallback_content,
                        selected_agent_id,
                    )
                    yield StreamChunk(
                        type="content",
                        content=fallback_content,
                        source=selected_agent_id,
                    )
                    self._final_presentation_content = stored_answer
                else:
                    log_stream_chunk(
                        "orchestrator",
                        "error",
                        "\n❌ No content generated for final presentation and no stored answer available.",
                        selected_agent_id,
                    )
                    yield StreamChunk(
                        type="content",
                        content="\n❌ No content generated for final presentation and no stored answer available.",
                        source=selected_agent_id,
                    )
            else:
                # Cancelled - use stored answer without yielding
                stored_answer = self.agent_states[selected_agent_id].answer
                if stored_answer:
                    self._final_presentation_content = stored_answer

            # Emit final_presentation_end event for unified pipeline
            if _fp_emitter:
                _fp_emitter.emit_final_presentation_end(agent_id=selected_agent_id)

            # Note: end_round_tracking for presentation is called from _present_final_answer
            # after the async for loop completes, to ensure reliable timing before save_coordination_logs

            # Mark final round as completed
            self.coordination_tracker.change_status(
                selected_agent_id,
                AgentStatus.COMPLETED,
            )

            # Compute context path writes (compare current state to snapshot taken before presentation)
            if agent.backend.filesystem_manager:
                agent.backend.filesystem_manager.path_permission_manager.compute_context_path_writes()

            # Add token usage and cost to presentation span before closing
            if hasattr(agent.backend, "token_usage") and agent.backend.token_usage:
                token_usage = agent.backend.token_usage
                _presentation_span.set_attribute(
                    "massgen.usage.input",
                    token_usage.input_tokens or 0,
                )
                _presentation_span.set_attribute(
                    "massgen.usage.output",
                    token_usage.output_tokens or 0,
                )
                _presentation_span.set_attribute(
                    "massgen.usage.reasoning",
                    token_usage.reasoning_tokens or 0,
                )
                _presentation_span.set_attribute(
                    "massgen.usage.cached_input",
                    token_usage.cached_input_tokens or 0,
                )
                _presentation_span.set_attribute(
                    "massgen.usage.cost",
                    round(token_usage.estimated_cost or 0, 6),
                )

            # Close the presentation span for hierarchical tracing
            # Wrap in try/except to handle OpenTelemetry context issues in async generators
            try:
                _presentation_span_cm.__exit__(None, None, None)
            except ValueError as e:
                # Context detach failures are expected in async generators - safe to ignore
                if "context" not in str(e).lower() and "detach" not in str(e).lower():
                    logger.debug(
                        f"Unexpected ValueError closing presentation span: {e}",
                    )

            # Clear the round context
            clear_current_round()

        # Don't yield done here - let _present_final_answer handle final done after post-evaluation

    async def _review_isolated_changes(
        self,
        agent: "ChatAgent",
        isolation_manager: "IsolationContextManager",
        selected_agent_id: str,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Review and apply changes from isolated write context.

        This method collects changes from the isolated context, shows a review
        modal to the user (if TUI is available), and applies approved changes
        to the original context paths.

        Args:
            agent: The presenting agent
            isolation_manager: IsolationContextManager with active contexts
            selected_agent_id: ID of the selected agent
        """
        from .filesystem_manager import ChangeApplier, ReviewResult

        logger.info(f"[Orchestrator] Starting _review_isolated_changes for {selected_agent_id}")

        def _count_diff_files(diff_text: str) -> int:
            if not diff_text:
                return 0
            return sum(1 for line in diff_text.splitlines() if line.startswith("diff --git "))

        def _normalize_approved_files_by_context(metadata: Any) -> dict[str, list[str]]:
            if not isinstance(metadata, dict):
                return {}
            raw_mapping = metadata.get("approved_files_by_context")
            if not isinstance(raw_mapping, dict):
                return {}

            normalized: dict[str, list[str]] = {}
            for context_path, approved_paths in raw_mapping.items():
                if not isinstance(context_path, str):
                    continue
                if not isinstance(approved_paths, list):
                    continue
                normalized[os.path.abspath(context_path)] = [path for path in approved_paths if isinstance(path, str)]
            return normalized

        def _normalize_approved_hunks_by_context(
            metadata: Any,
        ) -> dict[str, dict[str, list[int]]]:
            if not isinstance(metadata, dict):
                return {}
            raw_mapping = metadata.get("approved_hunks_by_context")
            if not isinstance(raw_mapping, dict):
                return {}

            normalized: dict[str, dict[str, list[int]]] = {}
            for context_path, hunks_by_file in raw_mapping.items():
                if not isinstance(context_path, str):
                    continue
                if not isinstance(hunks_by_file, dict):
                    continue
                context_hunks: dict[str, list[int]] = {}
                for file_path, hunk_indexes in hunks_by_file.items():
                    if not isinstance(file_path, str):
                        continue
                    if not isinstance(hunk_indexes, list):
                        continue
                    normalized_indexes: list[int] = []
                    for hunk_idx in hunk_indexes:
                        try:
                            hunk_idx_int = int(hunk_idx)
                        except (TypeError, ValueError):
                            continue
                        if hunk_idx_int >= 0:
                            normalized_indexes.append(hunk_idx_int)
                    context_hunks[file_path] = sorted(set(normalized_indexes))
                normalized[os.path.abspath(context_path)] = context_hunks
            return normalized

        def _is_in_context_prefix(rel_path: str, context_prefix: str) -> bool:
            normalized_rel = rel_path.replace("\\", "/").strip("/")
            normalized_prefix = context_prefix.replace("\\", "/").strip("/")
            if normalized_prefix in ("", "."):
                return True
            return normalized_rel == normalized_prefix or normalized_rel.startswith(f"{normalized_prefix}/")

        # 1. Collect all changes from isolated contexts
        all_changes = []
        for ctx_info in isolation_manager.list_contexts():
            if not ctx_info:
                continue
            original_path = ctx_info.get("original_path")
            if not original_path:
                continue

            changes = isolation_manager.get_changes(
                original_path,
                include_committed_since_base=True,
            )
            diff = isolation_manager.get_diff(
                original_path,
                include_committed_since_base=True,
            )

            if changes or diff:
                # For worktree mode, repo_root may differ from original_path
                # (context path can be a subdirectory of the git root).
                repo_root = os.path.abspath(ctx_info.get("repo_root") or original_path)
                original_abs = os.path.abspath(original_path)
                context_prefix = "."
                try:
                    if os.path.commonpath([original_abs, repo_root]) == repo_root:
                        context_prefix = os.path.relpath(original_abs, repo_root)
                    else:
                        # Fail closed: if context is outside repo_root, apply nothing.
                        context_prefix = "__massgen_out_of_scope__"
                        logger.warning(
                            "[Orchestrator] Context path is outside repo_root; " "writes will be blocked for this context: " f"context={original_abs}, repo_root={repo_root}",
                        )
                except ValueError:
                    context_prefix = "__massgen_out_of_scope__"
                    logger.warning(
                        "[Orchestrator] Could not compare context path and repo_root; " "writes will be blocked for this context: " f"context={original_abs}, repo_root={repo_root}",
                    )

                filtered_changes = [change for change in changes if isinstance(change, dict) and isinstance(change.get("path"), str) and _is_in_context_prefix(change["path"], context_prefix)]

                # Preserve diff-only contexts (e.g., staged-only workflows where
                # change enumeration can occasionally be empty).
                has_relevant_changes = bool(filtered_changes) or (not changes and bool(diff))
                if not has_relevant_changes:
                    continue

                all_changes.append(
                    {
                        "original_path": original_abs,
                        "isolated_path": ctx_info.get("isolated_path"),
                        "repo_root": repo_root,
                        "base_ref": ctx_info.get("base_ref"),
                        "context_prefix": context_prefix,
                        "changes": filtered_changes,
                        "diff": diff,
                    },
                )

        # 2. If no changes, skip review and cleanup
        if not all_changes:
            logger.info("[Orchestrator] No isolated changes to review")
            # Move scratch to archive before cleanup
            for ctx_info in isolation_manager.list_contexts():
                ctx_path = ctx_info.get("original_path") if ctx_info else None
                if ctx_path:
                    isolation_manager.move_scratch_to_workspace(ctx_path)
            isolation_manager.cleanup_session()
            # Contexts are now cleaned up; if this was a write-mode run with no
            # isolated diffs, still open the final answer/workspace modal.
            await self._show_workspace_modal_if_needed()
            return

        # 3. Yield status chunk to inform user about review phase
        total_changes = sum(len(c.get("changes", [])) or _count_diff_files(c.get("diff", "")) for c in all_changes)
        yield StreamChunk(
            type="status",
            content=f"Reviewing {total_changes} file change(s) from isolated context...",
            source=selected_agent_id,
        )

        # 4. Show review modal (TUI) or auto-approve (non-TUI)
        review_result = ReviewResult(approved=True, approved_files=None)

        # Get display via coordination_ui (orchestrator doesn't have a display attr directly)
        display = None
        if hasattr(self, "coordination_ui") and self.coordination_ui:
            display = getattr(self.coordination_ui, "display", None)

        logger.info(f"[Orchestrator] Review phase: display={display}, has_final_answer_modal={hasattr(display, 'show_final_answer_modal') if display else False}")

        if display and hasattr(display, "show_final_answer_modal"):
            try:
                logger.info("[Orchestrator] Showing final answer modal...")
                # Build context_paths summary from the changes
                context_paths_summary: dict[str, list[str]] | None = None
                new_files: list[str] = []
                modified_files: list[str] = []
                for ctx in all_changes:
                    for change in ctx.get("changes", []):
                        path = change.get("path", "")
                        status = change.get("status", "")
                        if status == "A":
                            new_files.append(path)
                        elif status in ("M", "D", "R"):
                            modified_files.append(path)
                if new_files or modified_files:
                    context_paths_summary = {"new": new_files, "modified": modified_files}

                model_name = ""
                if agent and hasattr(agent, "backend") and hasattr(agent.backend, "config"):
                    model_name = agent.backend.config.get("model", "")

                # Resolve workspace path (final from logs, fallback to live)
                workspace_path = self._resolve_final_workspace_path(selected_agent_id)
                if not workspace_path and agent and hasattr(agent, "backend"):
                    fm = getattr(agent.backend, "filesystem_manager", None)
                    if fm is not None:
                        try:
                            workspace_path = str(fm.get_current_workspace())
                        except Exception:
                            pass

                review_result = await display.show_final_answer_modal(
                    changes=all_changes,
                    answer_content=self._final_presentation_content or "",
                    vote_results=self._get_vote_results(),
                    agent_id=selected_agent_id,
                    model_name=model_name,
                    context_paths=context_paths_summary,
                    workspace_path=workspace_path,
                )
                logger.info(f"[Orchestrator] Final answer modal returned: approved={review_result.approved}")
            except Exception as e:
                logger.warning(f"[Orchestrator] Final answer modal failed: {e}, rejecting for safety")
                review_result = ReviewResult(approved=False, metadata={"error": str(e)})
        elif display and hasattr(display, "show_change_review_modal"):
            try:
                logger.info("[Orchestrator] Showing review modal (fallback)...")
                review_result = await display.show_change_review_modal(all_changes)
                logger.info(f"[Orchestrator] Review modal returned: approved={review_result.approved}")
            except Exception as e:
                logger.warning(f"[Orchestrator] Review modal failed: {e}, rejecting for safety")
                review_result = ReviewResult(approved=False, metadata={"error": str(e)})
        else:
            # Non-TUI mode: auto-approve all changes
            logger.info("[Orchestrator] Non-TUI mode: auto-approving isolated changes")

        # 5. Handle rework/quick_fix: keep isolation alive, signal caller
        if getattr(review_result, "action", None) in ("rework", "quick_fix"):
            self._pending_review_rework = {
                "action": review_result.action,
                "feedback": getattr(review_result, "feedback", None),
                "agent_id": selected_agent_id,
            }
            yield StreamChunk(
                type="status",
                content="Rework requested — isolation preserved for re-presentation...",
                source=selected_agent_id,
            )
            return  # Skip cleanup — isolation stays alive for the rework turn

        # 6. Apply approved changes
        if review_result.approved:
            applier = ChangeApplier()
            applied_files: list[str] = []
            drifted_files_all: list[str] = []
            approved_files_by_context = _normalize_approved_files_by_context(review_result.metadata)
            approved_hunks_by_context = _normalize_approved_hunks_by_context(review_result.metadata)
            drift_conflict_policy = (
                getattr(
                    getattr(self.config, "coordination_config", None),
                    "drift_conflict_policy",
                    "skip",
                )
                or "skip"
            )
            if drift_conflict_policy not in {"skip", "prefer_presenter", "fail"}:
                logger.warning(
                    "[Orchestrator] Invalid drift_conflict_policy=%s; defaulting to 'skip'",
                    drift_conflict_policy,
                )
                drift_conflict_policy = "skip"

            logger.info(
                "[Orchestrator] Applying approved changes: " f"approved_files={review_result.approved_files}, " f"contexts={len(all_changes)}, " f"drift_conflict_policy={drift_conflict_policy}",
            )

            def _format_file_list(file_paths: list[str], max_items: int = 10) -> str:
                deduped = sorted({path for path in file_paths if isinstance(path, str) and path.strip()})
                if len(deduped) <= max_items:
                    return ", ".join(deduped)
                remaining = len(deduped) - max_items
                return f"{', '.join(deduped[:max_items])}, +{remaining} more"

            apply_plan: list[dict[str, Any]] = []
            for ctx in all_changes:
                try:
                    context_path = os.path.abspath(ctx["original_path"])
                    target = context_path
                    context_prefix = ctx.get("context_prefix")
                    approved_files_for_context: list[str] | None
                    approved_hunks_for_context: dict[str, list[int]] | None = approved_hunks_by_context.get(context_path)

                    if review_result.approved_files is None:
                        approved_files_for_context = None
                    elif context_path in approved_files_by_context:
                        approved_files_for_context = approved_files_by_context[context_path]
                    else:
                        # Backward compatibility: support both legacy flat paths
                        # and context-keyed entries ("{context}::{path}").
                        approved_files_for_context = []
                        for approved_entry in review_result.approved_files:
                            if not isinstance(approved_entry, str):
                                continue
                            if "::" in approved_entry:
                                approved_context, approved_path = approved_entry.split("::", 1)
                                if os.path.abspath(approved_context) == context_path and approved_path:
                                    approved_files_for_context.append(approved_path)
                            else:
                                approved_files_for_context.append(approved_entry)

                    logger.info(
                        "[Orchestrator] ChangeApplier: " f"source={ctx['isolated_path']}, " f"target={target}, " f"context_prefix={context_prefix}",
                    )
                    drifted_files = applier.detect_target_drift(
                        source_path=ctx["isolated_path"],
                        target_path=target,
                        base_ref=ctx.get("base_ref"),
                        approved_files=approved_files_for_context,
                        context_prefix=context_prefix,
                    )
                    if drifted_files:
                        drifted_files_all.extend(drifted_files)
                        logger.warning(
                            "[Orchestrator] Detected drifted files for context " f"{context_path}: {drifted_files}",
                        )

                    apply_plan.append(
                        {
                            "source_path": ctx["isolated_path"],
                            "target_path": target,
                            "approved_files_for_context": approved_files_for_context,
                            "approved_hunks_for_context": approved_hunks_for_context,
                            "context_prefix": context_prefix,
                            "base_ref": ctx.get("base_ref"),
                            "drifted_files": drifted_files,
                            "combined_diff": ctx.get("diff"),
                        },
                    )
                except Exception as e:
                    logger.error(f"[Orchestrator] Failed to apply changes to {ctx['original_path']}: {e}")
                    yield StreamChunk(
                        type="error",
                        error=f"Failed to apply some changes: {e}",
                        source=selected_agent_id,
                    )

            drifted_files_unique = sorted(set(drifted_files_all))
            drifted_files_total = len(drifted_files_unique)
            drifted_file_list = _format_file_list(drifted_files_unique) if drifted_files_unique else ""

            if drifted_files_total and drift_conflict_policy == "fail":
                yield StreamChunk(
                    type="status",
                    content=(f"Detected {drifted_files_total} drifted file(s) (policy=fail): " f"{drifted_file_list}"),
                    source=selected_agent_id,
                )
                yield StreamChunk(
                    type="error",
                    error=("Drift conflict policy is 'fail'; no changes were applied. " "Resolve drift or use coordination.drift_conflict_policy " "set to 'skip' or 'prefer_presenter'."),
                    source=selected_agent_id,
                )
            else:
                if drifted_files_total and drift_conflict_policy == "prefer_presenter":
                    yield StreamChunk(
                        type="status",
                        content=(f"Detected {drifted_files_total} drifted file(s) " f"(policy=prefer_presenter): {drifted_file_list}"),
                        source=selected_agent_id,
                    )

                for plan_entry in apply_plan:
                    blocked_files = plan_entry["drifted_files"] if drift_conflict_policy == "skip" else None
                    files = applier.apply_changes(
                        source_path=plan_entry["source_path"],
                        target_path=plan_entry["target_path"],
                        approved_files=plan_entry["approved_files_for_context"],
                        approved_hunks=plan_entry["approved_hunks_for_context"],
                        context_prefix=plan_entry["context_prefix"],
                        base_ref=plan_entry["base_ref"],
                        blocked_files=blocked_files,
                        combined_diff=plan_entry["combined_diff"],
                    )
                    if files:
                        self._sync_applied_context_files_into_final_artifacts(
                            agent_id=selected_agent_id,
                            target_path=plan_entry["target_path"],
                            relative_paths=files,
                        )
                    applied_files.extend(files)

            if applied_files:
                yield StreamChunk(
                    type="status",
                    content=f"Applied {len(applied_files)} file change(s): {_format_file_list(applied_files)}",
                    source=selected_agent_id,
                )

                # Report skipped files (approved but not applied due to drift)
                if drifted_files_total and drift_conflict_policy == "skip":
                    yield StreamChunk(
                        type="status",
                        content=(f"Skipped {drifted_files_total} drifted file(s) " f"(policy=skip): {drifted_file_list}"),
                        source=selected_agent_id,
                    )

                # Report rejected files (user deselected in review modal)
                if review_result.approved_files is not None:
                    total_available = sum(len(ctx.get("changes", [])) for ctx in all_changes)
                    rejected_count = total_available - len(review_result.approved_files)
                    if rejected_count > 0:
                        yield StreamChunk(
                            type="status",
                            content=f"User excluded {rejected_count} file(s) from apply",
                            source=selected_agent_id,
                        )

                logger.info(f"[Orchestrator] Applied isolated changes: {applied_files}")
            else:
                logger.warning("[Orchestrator] Review approved but no files were applied (empty change set)")
                yield StreamChunk(
                    type="status",
                    content="Review approved but no changed files were found to apply",
                    source=selected_agent_id,
                )
                if drifted_files_total and drift_conflict_policy == "skip":
                    yield StreamChunk(
                        type="status",
                        content=(f"Skipped {drifted_files_total} drifted file(s) " f"(policy=skip): {drifted_file_list}"),
                        source=selected_agent_id,
                    )
        else:
            yield StreamChunk(
                type="status",
                content="Changes rejected - no files were modified",
                source=selected_agent_id,
            )
            logger.info("[Orchestrator] User rejected isolated changes")

        # 6. Move scratch to archive and cleanup all isolated contexts + branches
        for ctx_info in isolation_manager.list_contexts():
            ctx_path = ctx_info.get("original_path") if ctx_info else None
            if ctx_path:
                isolation_manager.move_scratch_to_workspace(ctx_path)
        isolation_manager.cleanup_session()

    async def post_evaluate_answer(
        self,
        selected_agent_id: str,
        final_answer: str,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Post-evaluation phase where winning agent evaluates its own answer.

        The agent reviews the final answer and decides whether to submit or restart
        with specific improvement instructions.

        Args:
            selected_agent_id: The agent that won the vote and presented the answer
            final_answer: The final answer that was presented

        Yields:
            StreamChunk: Stream chunks from the evaluation process
        """
        if selected_agent_id not in self.agents:
            log_stream_chunk(
                "orchestrator",
                "error",
                f"Selected agent {selected_agent_id} not found for post-evaluation",
            )
            yield StreamChunk(
                type="error",
                error=f"Selected agent {selected_agent_id} not found",
            )
            return

        agent = self.agents[selected_agent_id]

        # Use debug override on first attempt if configured
        eval_answer = final_answer
        if self.config.debug_final_answer and self.current_attempt == 0:
            eval_answer = self.config.debug_final_answer
            log_stream_chunk(
                "orchestrator",
                "debug",
                f"Using debug override for post-evaluation: {self.config.debug_final_answer}",
            )
            yield StreamChunk(
                type="debug",
                content=f"[DEBUG MODE] Overriding answer for evaluation: {self.config.debug_final_answer}",
                source="orchestrator",
            )

        # Build evaluation message
        evaluation_content = f"""{self.message_templates.format_original_message(self.current_task or "Task")}

FINAL ANSWER TO EVALUATE:
{eval_answer}

Review this answer carefully and determine if it fully addresses the original task. Use your available tools to verify claims and check files as needed.
Then call either submit(confirmed=True) if the answer is satisfactory, or restart_orchestration(reason, instructions) if improvements are needed."""

        # Get all answers for context
        all_answers = {aid: s.answer for aid, s in self.agent_states.items() if s.answer}

        # Build post-evaluation system message using section architecture
        base_system_message = self._get_system_message_builder().build_post_evaluation_message(
            agent=agent,
            all_answers=all_answers,
            previous_turns=self._previous_turns,
        )

        # Create evaluation messages
        evaluation_messages = [
            {"role": "system", "content": base_system_message},
            {"role": "user", "content": evaluation_content},
        ]

        # Get post-evaluation tools
        api_format = "chat_completions"  # Default format
        if hasattr(agent.backend, "api_format"):
            api_format = agent.backend.api_format
        post_eval_tools = get_post_evaluation_tools(api_format=api_format)

        log_stream_chunk(
            "orchestrator",
            "status",
            "🔍 Post-evaluation: Reviewing final answer\n",
        )
        yield StreamChunk(
            type="status",
            content="🔍 Post-evaluation: Reviewing final answer\n",
            source="orchestrator",
        )

        # Emit post_evaluation start event for unified pipeline

        _pe_emitter = get_event_emitter()
        if _pe_emitter:
            _pe_emitter.emit_post_evaluation(
                phase="start",
                content="Post-evaluation: Reviewing final answer",
                agent_id=selected_agent_id,
            )

        # Start round token tracking for post-evaluation
        post_eval_round = self.coordination_tracker.get_agent_round(selected_agent_id) + 1
        if hasattr(agent.backend, "start_round_tracking"):
            agent.backend.start_round_tracking(
                round_number=post_eval_round,
                round_type="post_evaluation",
                agent_id=selected_agent_id,
            )

        # Stream evaluation with tools (with timeout protection)
        evaluation_complete = False
        tool_call_detected = False
        accumulated_content = ""  # Buffer to detect inline JSON across chunks

        try:
            timeout_seconds = self.config.timeout_config.orchestrator_timeout_seconds
            async with asyncio.timeout(timeout_seconds):
                async for chunk in agent.chat(
                    messages=evaluation_messages,
                    tools=post_eval_tools,
                    reset_chat=True,  # Reset conversation history for clean evaluation
                    current_stage=CoordinationStage.POST_EVALUATION,
                    orchestrator_turn=self._current_turn,
                    previous_winners=self._winning_agents_history.copy(),
                ):
                    chunk_type = self._get_chunk_type_value(chunk)

                    # Skip content/reasoning after evaluation decision (submit/restart)
                    # to prevent stray text appearing after answer_locked
                    if evaluation_complete and chunk_type in (
                        "content",
                        "reasoning",
                        "reasoning_done",
                        "reasoning_summary",
                        "reasoning_summary_done",
                    ):
                        continue

                    if chunk_type == "content" and chunk.content:
                        log_stream_chunk(
                            "orchestrator",
                            "content",
                            chunk.content,
                            selected_agent_id,
                        )
                        yield StreamChunk(
                            type="content",
                            content=chunk.content,
                            source=selected_agent_id,
                        )
                        # Emit post_evaluation content for unified pipeline
                        if _pe_emitter:
                            _pe_emitter.emit_post_evaluation(
                                phase="content",
                                content=chunk.content,
                                agent_id=selected_agent_id,
                            )

                        # Accumulate content for JSON parsing across chunks
                        accumulated_content += chunk.content

                        # Fallback: parse inline JSON tool calls from accumulated content
                        # Some backends output submit/restart as JSON text instead of tool_calls
                        if not evaluation_complete and not tool_call_detected:
                            # Try to extract and parse JSON from accumulated content
                            import json
                            import re

                            # Find JSON objects in the content (handle nested braces)
                            # Look for { ... "action_type" ... } allowing nested braces
                            json_matches = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*"action_type"[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', accumulated_content, re.DOTALL)
                            for json_str in json_matches:
                                try:
                                    data = json.loads(json_str)
                                    action_type = data.get("action_type")

                                    if action_type == "submit":
                                        tool_call_detected = True
                                        log_stream_chunk(
                                            "orchestrator",
                                            "status",
                                            "✅ Evaluation complete - answer approved\n",
                                        )
                                        yield StreamChunk(
                                            type="status",
                                            content="✅ Evaluation complete - answer approved\n",
                                            source="orchestrator",
                                        )
                                        evaluation_complete = True
                                        break
                                    elif action_type == "restart_orchestration":
                                        tool_call_detected = True
                                        restart_data = data.get("restart_data", {})
                                        self.restart_reason = restart_data.get("reason", data.get("reason", "Answer needs improvement"))
                                        self.restart_instructions = restart_data.get("instructions", data.get("instructions", ""))
                                        self.restart_pending = True

                                        log_stream_chunk(
                                            "orchestrator",
                                            "status",
                                            "🔄 Restart requested\n",
                                        )
                                        yield StreamChunk(
                                            type="status",
                                            content="🔄 Restart requested\n",
                                            source="orchestrator",
                                        )
                                        evaluation_complete = True
                                        break
                                except json.JSONDecodeError:
                                    # Not valid JSON yet, keep accumulating
                                    pass
                    elif chunk_type in [
                        "reasoning",
                        "reasoning_done",
                        "reasoning_summary",
                        "reasoning_summary_done",
                    ]:
                        reasoning_chunk = StreamChunk(
                            type=chunk_type,
                            content=chunk.content,
                            source=selected_agent_id,
                            reasoning_delta=getattr(chunk, "reasoning_delta", None),
                            reasoning_text=getattr(chunk, "reasoning_text", None),
                            reasoning_summary_delta=getattr(
                                chunk,
                                "reasoning_summary_delta",
                                None,
                            ),
                            reasoning_summary_text=getattr(
                                chunk,
                                "reasoning_summary_text",
                                None,
                            ),
                            item_id=getattr(chunk, "item_id", None),
                            content_index=getattr(chunk, "content_index", None),
                            summary_index=getattr(chunk, "summary_index", None),
                        )
                        log_stream_chunk(
                            "orchestrator",
                            chunk.type,
                            chunk.content,
                            selected_agent_id,
                        )
                        yield reasoning_chunk
                        # Emit thinking events for the unified event pipeline
                        if _pe_emitter and chunk.content:
                            _pe_emitter.emit_thinking(
                                content=chunk.content,
                                agent_id=selected_agent_id,
                            )
                        if _pe_emitter and chunk_type in ("reasoning_done", "reasoning_summary_done"):
                            from massgen.events import EventType as _EvType

                            _pe_emitter.emit_raw(
                                _EvType.THINKING,
                                content="",
                                done=True,
                                agent_id=selected_agent_id,
                            )
                    elif chunk_type == "tool_calls":
                        # Post-evaluation tool call detected - only set flag if valid tool found
                        if hasattr(chunk, "tool_calls") and chunk.tool_calls:
                            for tool_call in chunk.tool_calls:
                                # Use backend's tool extraction (same as regular coordination)
                                tool_name = agent.backend.extract_tool_name(tool_call)
                                tool_args = agent.backend.extract_tool_arguments(
                                    tool_call,
                                )

                                # Only set tool_call_detected if we got a valid tool name
                                if tool_name:
                                    tool_call_detected = True

                                if tool_name == "submit":
                                    log_stream_chunk(
                                        "orchestrator",
                                        "status",
                                        "✅ Evaluation complete - answer approved\n",
                                    )
                                    yield StreamChunk(
                                        type="status",
                                        content="✅ Evaluation complete - answer approved\n",
                                        source="orchestrator",
                                    )
                                    evaluation_complete = True
                                elif tool_name == "restart_orchestration":
                                    # Parse restart parameters from extracted args
                                    self.restart_reason = tool_args.get(
                                        "reason",
                                        "No reason provided",
                                    )
                                    self.restart_instructions = tool_args.get(
                                        "instructions",
                                        "No instructions provided",
                                    )
                                    self.restart_pending = True

                                    # Save the current winning answer for next attempt's context
                                    if self._selected_agent and self._selected_agent in self.agent_states:
                                        self.previous_attempt_answer = self.agent_states[self._selected_agent].answer
                                        logger.info(
                                            f"Saved previous attempt answer from {self._selected_agent} for restart context",
                                        )

                                    log_stream_chunk(
                                        "orchestrator",
                                        "status",
                                        "🔄 Restart requested\n",
                                    )
                                    yield StreamChunk(
                                        type="status",
                                        content="🔄 Restart requested\n",
                                        source="orchestrator",
                                    )
                                    evaluation_complete = True
                    elif chunk_type == "done":
                        log_stream_chunk(
                            "orchestrator",
                            "done",
                            None,
                            selected_agent_id,
                        )
                        yield StreamChunk(type="done", source=selected_agent_id)
                    elif chunk_type == "error":
                        log_stream_chunk(
                            "orchestrator",
                            "error",
                            chunk.error,
                            selected_agent_id,
                        )
                        yield StreamChunk(
                            type="error",
                            error=chunk.error,
                            source=selected_agent_id,
                        )
                    else:
                        # Pass through other chunk types
                        log_stream_chunk(
                            "orchestrator",
                            chunk_type,
                            getattr(chunk, "content", ""),
                            selected_agent_id,
                        )
                        yield StreamChunk(
                            type=chunk_type,
                            content=getattr(chunk, "content", ""),
                            source=selected_agent_id,
                            **{
                                k: v
                                for k, v in chunk.__dict__.items()
                                if k
                                not in [
                                    "type",
                                    "content",
                                    "source",
                                    "timestamp",
                                    "sequence_number",
                                ]
                            },
                        )
        except TimeoutError:
            log_stream_chunk(
                "orchestrator",
                "status",
                "⏱️ Post-evaluation timed out - auto-submitting answer\n",
            )
            yield StreamChunk(
                type="status",
                content="⏱️ Post-evaluation timed out - auto-submitting answer\n",
                source="orchestrator",
            )
            evaluation_complete = True
            # Don't set restart_pending - let it default to False (auto-submit)
        finally:
            # Note: end_round_tracking for post_evaluation is called from _present_final_answer
            # after the async for loop completes, to ensure reliable timing before save_coordination_logs

            # Emit post_evaluation end event for unified pipeline
            if _pe_emitter:
                winner = selected_agent_id if not self.restart_pending else None
                _pe_emitter.emit_post_evaluation(
                    phase="end",
                    winner=winner,
                    agent_id=selected_agent_id,
                )

            # If evaluation didn't complete (no submit/restart called), auto-submit
            # This handles cases where:
            # 1. No tool was called at all
            # 2. Tools were called but not submit/restart (e.g., read_file for verification)
            if not evaluation_complete:
                log_stream_chunk(
                    "orchestrator",
                    "status",
                    "✅ Evaluation complete - answer approved\n",
                )
                yield StreamChunk(
                    type="status",
                    content="✅ Evaluation complete - answer approved\n",
                    source="orchestrator",
                )

    def handle_restart(self):
        """Reset orchestration state for restart attempt.

        Clears agent states and coordination messages while preserving
        restart reason and instructions for the next attempt.
        """
        log_orchestrator_activity(
            "handle_restart",
            f"Resetting state for restart attempt {self.current_attempt + 1}",
        )

        # Reset agent states
        for agent_id in self.agent_states:
            self.agent_states[agent_id] = AgentState()

        # Clear coordination messages
        self._coordination_messages = []
        self._selected_agent = None
        self._final_presentation_content = None

        # Reset coordination tracker for new attempt (MAS-199: includes log_path)
        self.coordination_tracker = CoordinationTracker()
        log_dir = get_log_session_dir()
        log_path = str(log_dir) if log_dir else None
        self.coordination_tracker.initialize_session(
            list(self.agents.keys()),
            log_path=log_path,
        )

        # Reset MCP initialization flag to force tool re-setup on next agent.chat()
        # This ensures agents get full tool set after restart (not limited set from timeout)
        for agent_key, agent in self.agents.items():
            if hasattr(agent.backend, "_mcp_initialized"):
                agent.backend._mcp_initialized = False
                logger.info(
                    f"[Orchestrator] Reset MCP initialized flag for agent {agent_key}",
                )

        # Reset workflow phase to idle so next coordinate() call starts fresh
        self.workflow_phase = "idle"

        # Increment attempt counter
        self.current_attempt += 1

        log_orchestrator_activity(
            "handle_restart",
            f"State reset complete - starting attempt {self.current_attempt + 1}",
        )

    def _should_skip_injection_due_to_timeout(self, agent_id: str) -> bool:
        """Check if mid-stream injection should be skipped due to approaching timeout.

        If the agent doesn't have enough time remaining before soft timeout to properly
        consider a new answer, it's better to skip injection and let the agent restart
        with fresh context so they get a full round to think.

        Args:
            agent_id: The agent to check

        Returns:
            True if injection should be skipped, False otherwise
        """
        timeout_config = self.config.timeout_config
        round_start = self.agent_states[agent_id].round_start_time

        if round_start is None:
            return False

        current_round = self.coordination_tracker.get_agent_round(agent_id)
        if current_round == 0:
            soft_timeout = timeout_config.initial_round_timeout_seconds
        else:
            soft_timeout = timeout_config.subsequent_round_timeout_seconds

        if soft_timeout is None:
            return False

        elapsed = time.time() - round_start
        min_thinking_time = timeout_config.round_timeout_grace_seconds
        remaining = soft_timeout - elapsed

        if remaining < min_thinking_time:
            logger.info(
                f"[Orchestrator] Skipping mid-stream injection for {agent_id} - " f"only {remaining:.0f}s until soft timeout (need {min_thinking_time}s to think)",
            )
            return True

        return False

    def _resolve_final_workspace_path(self, agent_id: str | None) -> str | None:
        """Resolve the final workspace path from the log directory.

        After a run completes, the live workspace is cleared. The final snapshot
        lives under log_session_dir/turn_*/attempt_*/final/agent_*/workspace.
        """
        if not agent_id:
            return None
        log_dir = get_log_session_dir()
        if not log_dir:
            return None

        log_path = Path(log_dir)
        # Try turn_*/attempt_*/final/agent_*/workspace (most common)
        for turn_dir in sorted(log_path.glob("turn_*"), reverse=True):
            for attempt_dir in sorted(turn_dir.glob("attempt_*"), reverse=True):
                ws = attempt_dir / "final" / agent_id / "workspace"
                if ws.exists() and ws.is_dir():
                    return str(ws)

        # Fallback: direct final/ directory
        ws = log_path / "final" / agent_id / "workspace"
        if ws.exists() and ws.is_dir():
            return str(ws)

        return None

    async def _show_workspace_modal_if_needed(self) -> None:
        """Show the final answer modal with workspace tab in no-git (no-isolation) mode.

        Called from _present_final_answer in both the skip-presentation and
        normal-presentation paths.  Must run BEFORE clear_workspace().
        """
        if self._isolation_manager:
            try:
                active_contexts = [ctx for ctx in self._isolation_manager.list_contexts() if ctx]
            except Exception as e:
                # Fail closed: if we cannot inspect isolation state, keep existing behavior.
                logger.warning("[Orchestrator] Failed to inspect isolation state: %s", e)
                active_contexts = [object()]

            if active_contexts:
                return

        display = None
        if hasattr(self, "coordination_ui") and self.coordination_ui:
            display = getattr(self.coordination_ui, "display", None)

        if not display or not hasattr(display, "show_final_answer_modal"):
            return

        agent = self.agents.get(self._selected_agent)

        # Try final workspace from logs first, fall back to live workspace
        # (live workspace hasn't been cleared yet at this point)
        workspace_path = self._resolve_final_workspace_path(self._selected_agent)
        if not workspace_path and agent:
            fm = getattr(getattr(agent, "backend", None), "filesystem_manager", None)
            if fm:
                try:
                    ws = fm.get_current_workspace()
                    if ws and Path(ws).is_dir() and any(Path(ws).iterdir()):
                        workspace_path = str(ws)
                except Exception:
                    pass

        logger.info(
            f"[Orchestrator] No-git workspace modal: workspace_path={workspace_path}, " f"agent={self._selected_agent}",
        )

        if not workspace_path:
            logger.info(
                "[Orchestrator] No-git workspace path unavailable; " "opening answer-only final modal",
            )

        try:
            model_name = ""
            if agent and hasattr(agent, "backend") and hasattr(agent.backend, "config"):
                model_name = agent.backend.config.get("model", "")

            await display.show_final_answer_modal(
                changes=[],
                answer_content=self._final_presentation_content or "",
                vote_results=self._get_vote_results(),
                agent_id=self._selected_agent or "",
                model_name=model_name,
                workspace_path=workspace_path,
            )
        except Exception as e:
            logger.warning(f"[Orchestrator] Workspace modal failed: {e}")

    def _get_vote_results(self) -> dict[str, Any]:
        """Get current vote results and statistics."""
        agent_answers = {aid: state.answer for aid, state in self.agent_states.items() if state.answer}
        votes = {aid: state.votes for aid, state in self.agent_states.items() if state.votes}

        # Count votes for each agent
        vote_counts = {}
        voter_details = {}

        for voter_id, vote_data in votes.items():
            voted_for = vote_data.get("agent_id")
            if voted_for:
                vote_counts[voted_for] = vote_counts.get(voted_for, 0) + 1
                if voted_for not in voter_details:
                    voter_details[voted_for] = []
                voter_details[voted_for].append(
                    {
                        "voter": voter_id,
                        "reason": vote_data.get("reason", "No reason provided"),
                    },
                )

        # Determine winner
        winner = None
        is_tie = False
        if vote_counts:
            max_votes = max(vote_counts.values())
            tied_agents = [agent_id for agent_id, count in vote_counts.items() if count == max_votes]
            is_tie = len(tied_agents) > 1

            # Break ties by agent registration order
            for agent_id in agent_answers.keys():
                if agent_id in tied_agents:
                    winner = agent_id
                    break

            if not winner:
                winner = tied_agents[0] if tied_agents else None

        # Create agent mapping for anonymous display
        # Use global mapping (all agents) for consistency with vote tool and injections
        agent_mapping = self.coordination_tracker.get_anonymous_agent_mapping()

        return {
            "vote_counts": vote_counts,
            "voter_details": voter_details,
            "winner": winner,
            "is_tie": is_tie,
            "total_votes": len(votes),
            "agents_with_answers": len(agent_answers),
            "agents_voted": len([v for v in votes.values() if v.get("agent_id")]),
            "agent_mapping": agent_mapping,
        }

    def _determine_final_agent_from_states(self) -> str | None:
        """Determine final agent based on current agent states.

        When no winner or votes exist, selects the agent whose most recent
        answer has the latest timestamp — that agent has the most context
        from prior iterations.
        """
        # Find agents with answers
        agents_with_answers = {aid: state.answer for aid, state in self.agent_states.items() if state.answer}

        if not agents_with_answers:
            return None

        # Select agent with the most recent answer by timestamp
        latest_agent = None
        latest_ts = -1.0
        for aid in agents_with_answers:
            agent_answers = self.coordination_tracker.answers_by_agent.get(aid, [])
            if agent_answers:
                last_answer = agent_answers[-1]
                if last_answer.timestamp > latest_ts:
                    latest_ts = last_answer.timestamp
                    latest_agent = aid

        return latest_agent or next(iter(agents_with_answers))

    async def _handle_followup(
        self,
        user_message: str,
        conversation_context: dict[str, Any] | None = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Handle follow-up questions after presenting final answer with conversation context."""
        # Analyze the follow-up question for irreversibility before re-coordinating
        has_irreversible = await self._analyze_question_irreversibility(
            user_message,
            conversation_context or {},
        )

        # Set planning mode for all agents based on analysis
        for agent_id, agent in self.agents.items():
            if hasattr(agent.backend, "set_planning_mode"):
                agent.backend.set_planning_mode(has_irreversible)
                log_orchestrator_activity(
                    self.orchestrator_id,
                    f"Set planning mode for {agent_id} (follow-up)",
                    {
                        "planning_mode_enabled": has_irreversible,
                        "reason": "follow-up irreversibility analysis",
                    },
                )

        # For now, acknowledge with context awareness
        # Future: implement full re-coordination with follow-up context

        if conversation_context and len(conversation_context.get("conversation_history", [])) > 0:
            log_stream_chunk(
                "orchestrator",
                "content",
                f"🤔 Thank you for your follow-up question in our ongoing conversation. I understand you're asking: "
                f"'{user_message}'. Currently, the coordination is complete, but I can help clarify the answer or "
                f"coordinate a new task that takes our conversation history into account.",
            )
            yield StreamChunk(
                type="content",
                content=f"🤔 Thank you for your follow-up question in our ongoing conversation. I understand you're "
                f"asking: '{user_message}'. Currently, the coordination is complete, but I can help clarify the answer "
                f"or coordinate a new task that takes our conversation history into account.",
            )
        else:
            log_stream_chunk(
                "orchestrator",
                "content",
                f"🤔 Thank you for your follow-up: '{user_message}'. The coordination is complete, but I can help clarify the answer or coordinate a new task if needed.",
            )
            yield StreamChunk(
                type="content",
                content=f"🤔 Thank you for your follow-up: '{user_message}'. The coordination is complete, but I can help clarify the answer or coordinate a new task if needed.",
            )

        log_stream_chunk("orchestrator", "done", None)
        yield StreamChunk(type="done")

    # =============================================================================
    # PUBLIC API METHODS
    # =============================================================================

    def add_agent(self, agent_id: str, agent: ChatAgent) -> None:
        """Add a new sub-agent to the orchestrator."""
        self.agents[agent_id] = agent
        self.agent_states[agent_id] = AgentState()

    def remove_agent(self, agent_id: str) -> None:
        """Remove a sub-agent from the orchestrator."""
        if agent_id in self.agents:
            del self.agents[agent_id]
        if agent_id in self.agent_states:
            del self.agent_states[agent_id]

    def get_final_result(self) -> dict[str, Any] | None:
        """
        Get final result for session persistence.

        Returns:
            Dict with final_answer, winning_agent_id, workspace_path, and winning_agents_history,
            or None if not available
        """
        if not self._selected_agent or not self._final_presentation_content:
            return None

        # Use the final log directory workspace which we just saved
        # This is guaranteed to have the correct content (from either workspace or snapshot_storage)
        from massgen.logger_config import get_log_session_dir

        workspace_path = None
        log_session_dir = get_log_session_dir()
        if log_session_dir:
            final_workspace = log_session_dir / "final" / self._selected_agent / "workspace"
            if final_workspace.exists():
                workspace_path = str(final_workspace)
                logger.info(f"[Orchestrator] Using final log workspace for session persistence: {workspace_path}")

        return {
            "final_answer": self._final_presentation_content,
            "winning_agent_id": self._selected_agent,
            "workspace_path": workspace_path,
            "winning_agents_history": self._winning_agents_history.copy(),  # For cross-turn memory sharing
        }

    def get_partial_result(self) -> dict[str, Any] | None:
        """Get partial coordination result for interrupted sessions.

        Captures whatever state is available mid-coordination, useful when
        a user cancels with Ctrl+C before coordination completes.

        Returns:
            Dict with partial state including:
            - status: Always "incomplete"
            - phase: Current workflow phase
            - current_task: The task being worked on
            - answers: Dict of agent_id -> answer data for agents with answers
            - workspaces: Dict of agent_id -> workspace path
            - selected_agent: Winning agent if voting completed, else None
            - coordination_tracker: Coordination state if available

            Returns None if no answers have been generated yet.

        Example:
            >>> partial = orchestrator.get_partial_result()
            >>> if partial:
            ...     save_partial_turn(session_id, turn, task, partial)
        """
        # Best-effort trace flush for cancellation/interrupt flows where snapshot
        # code paths may not have run yet.
        self._save_partial_execution_traces_for_interrupted_turn()

        # Collect any answers that have been submitted
        answers = {}
        for agent_id, state in self.agent_states.items():
            if state.answer:
                answers[agent_id] = {
                    "answer": state.answer,
                    "has_voted": state.has_voted,
                    "votes": state.votes if state.has_voted else None,
                    "answer_count": state.answer_count,
                }

        # Get all agent workspaces (even those without answers)
        workspaces = self.get_all_agent_workspaces()

        def has_files_recursive(directory: Path) -> bool:
            """Check if directory contains any files (recursively)."""
            if not directory.is_dir():
                return False
            for item in directory.iterdir():
                if item.is_file():
                    return True
                if item.is_dir() and has_files_recursive(item):
                    return True
            return False

        # Check if any workspaces have content (actual files, not just empty dirs)
        workspaces_with_content = {}
        for agent_id, ws_path in workspaces.items():
            if ws_path and Path(ws_path).exists():
                ws = Path(ws_path)
                if has_files_recursive(ws):
                    workspaces_with_content[agent_id] = ws_path

        # If no answers AND no workspaces with content, nothing worth saving
        if not answers and not workspaces_with_content:
            return None

        # Check if voting is complete (all non-killed agents have voted)
        active_agents = [state for state in self.agent_states.values() if not state.is_killed]
        voting_complete = all(state.has_voted for state in active_agents) if active_agents else False

        # Build partial result
        result = {
            "status": "incomplete",
            "phase": self.workflow_phase,
            "current_task": self.current_task,
            "answers": answers,
            "workspaces": workspaces_with_content,  # Only include workspaces with content
            "selected_agent": self._selected_agent,  # May be None if voting incomplete
            "voting_complete": voting_complete,  # Whether all agents had voted before cancellation
        }

        # Include coordination tracker state if available
        if self.coordination_tracker:
            try:
                result["coordination_tracker"] = self.coordination_tracker.to_dict()
            except Exception:
                # Don't fail if tracker serialization fails
                pass

        # Best-effort: create the final/ directory so downstream consumers
        # (e.g., resolve_next_tasks_artifact for round_evaluator auto-injection)
        # find artifacts at the standard path. Normally the presentation phase
        # creates this, but on SIGTERM/timeout the process is killed before
        # presentation runs.
        self._ensure_final_directory_on_shutdown(answers, workspaces_with_content)

        return result

    def _ensure_final_directory_on_shutdown(
        self,
        answers: dict[str, Any],
        workspaces: dict[str, str],
    ) -> None:
        """Best-effort creation of final/ directory during shutdown.

        When the process is terminated (SIGTERM) before the presentation phase,
        the normal final snapshot path never runs.  This method creates a
        minimal final/ directory from the winning agent's snapshot_storage so
        that downstream consumers (resolve_next_tasks_artifact, session
        persistence) find artifacts at the standard path.
        """
        log_session_dir = get_log_session_dir()
        if not log_session_dir:
            return

        # Determine the best agent to use for the final snapshot
        selected = self._selected_agent or self._determine_final_agent_from_states()
        if not selected:
            return

        # Skip if final/ already exists (presentation phase already ran)
        final_dir = log_session_dir / "final" / selected
        if final_dir.exists():
            return

        # Find the agent's snapshot source — prefer snapshot_storage, then
        # live workspace
        agent = self.agents.get(selected)
        if not agent:
            return
        fm = getattr(agent.backend, "filesystem_manager", None) if hasattr(agent, "backend") else None
        if not fm:
            return

        source: Path | None = None
        snapshot_storage = getattr(fm, "snapshot_storage", None)
        if snapshot_storage and Path(snapshot_storage).exists():
            from .filesystem_manager._filesystem_manager import has_meaningful_content

            if has_meaningful_content(Path(snapshot_storage)):
                source = Path(snapshot_storage)
        if source is None:
            ws = fm.get_current_workspace() if hasattr(fm, "get_current_workspace") else getattr(fm, "cwd", None)
            if ws and Path(ws).exists():
                source = Path(ws)
        if source is None:
            return

        try:
            import shutil

            workspace_dest = final_dir / "workspace"
            workspace_dest.mkdir(parents=True, exist_ok=True)
            for item in source.iterdir():
                if item.is_symlink():
                    continue
                if item.is_file():
                    shutil.copy2(item, workspace_dest / item.name)
                elif item.is_dir():
                    shutil.copytree(
                        item,
                        workspace_dest / item.name,
                        symlinks=True,
                        ignore_dangling_symlinks=True,
                    )

            # Write answer.txt alongside workspace
            answer_data = answers.get(selected)
            if answer_data and answer_data.get("answer"):
                answer_content = answer_data["answer"]
                # Normalize workspace paths to reference adjacent workspace/
                dest_workspace = str(final_dir / "workspace")
                original_cwd = getattr(fm, "cwd", None)
                if original_cwd:
                    answer_content = answer_content.replace(
                        str(original_cwd),
                        dest_workspace,
                    )
                    resolved_cwd = str(Path(original_cwd).resolve())
                    if resolved_cwd != str(original_cwd):
                        answer_content = answer_content.replace(
                            resolved_cwd,
                            dest_workspace,
                        )
                if str(source) != dest_workspace:
                    answer_content = answer_content.replace(
                        str(source),
                        dest_workspace,
                    )
                (final_dir / "answer.txt").write_text(answer_content)

            logger.info(
                "[Orchestrator] Created final/ directory on shutdown for %s at %s",
                selected,
                final_dir,
            )
        except Exception as exc:
            logger.warning(
                "[Orchestrator] Failed to create final/ directory on shutdown: %s",
                exc,
            )

    def get_all_agent_workspaces(self) -> dict[str, str | None]:
        """Get workspace paths for all agents.

        Returns:
            Dict mapping agent_id to workspace path (or None if no workspace)
        """
        workspaces = {}
        for agent_id, agent in self.agents.items():
            if hasattr(agent, "backend") and hasattr(
                agent.backend,
                "filesystem_manager",
            ):
                fm = agent.backend.filesystem_manager
                if fm:
                    workspaces[agent_id] = str(fm.get_current_workspace())
                else:
                    workspaces[agent_id] = None
            else:
                workspaces[agent_id] = None
        return workspaces

    def get_coordination_result(self) -> dict[str, Any]:
        """Get comprehensive coordination result for API consumption.

        Returns:
            Dict with all coordination metadata:
            - final_answer: The final presented answer
            - selected_agent: ID of the winning agent
            - log_directory: Root log directory path
            - final_answer_path: Path to final/ directory
            - answers: List of answers with labels (answerX.Y), paths, and content
            - vote_results: Full voting details
        """
        from pathlib import Path

        from .logger_config import get_log_session_dir, get_log_session_root

        # Get log paths
        log_root = None
        log_session_dir = None
        final_path = None
        try:
            log_root = get_log_session_root()
            log_session_dir = get_log_session_dir()
            final_path = log_session_dir / "final"
        except Exception:
            pass  # Log paths not available

        # Build answers list from snapshot_mappings with full log paths
        answers = []
        if self.coordination_tracker and self.coordination_tracker.snapshot_mappings:
            for label, mapping in self.coordination_tracker.snapshot_mappings.items():
                if mapping.get("type") == "answer":
                    # Build full path from log_session_dir + relative path
                    answer_dir = None
                    if log_session_dir and mapping.get("path"):
                        answer_dir = str(log_session_dir / Path(mapping["path"]).parent)

                    # Get answer content from agent state
                    agent_id = mapping.get("agent_id")
                    content = None
                    if agent_id and agent_id in self.agent_states:
                        content = self.agent_states[agent_id].answer

                    answers.append(
                        {
                            "label": label,  # e.g., "agent1.1"
                            "agent_id": agent_id,
                            "answer_path": answer_dir,
                            "content": content,
                        },
                    )

        # Get vote results
        vote_results = self._get_vote_results()

        # Aggregate token usage across all agents
        total_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        for agent in self.agents.values():
            backend = getattr(agent, "backend", None)
            if backend and hasattr(backend, "token_usage") and backend.token_usage:
                # Finalize tracking if available
                if hasattr(backend, "finalize_token_tracking"):
                    try:
                        backend.finalize_token_tracking()
                    except Exception:
                        pass
                tu = backend.token_usage
                prompt = tu.input_tokens + tu.cached_input_tokens + tu.cache_creation_tokens
                completion = tu.output_tokens + tu.reasoning_tokens
                total_usage["prompt_tokens"] += prompt
                total_usage["completion_tokens"] += completion
                total_usage["total_tokens"] += prompt + completion

        return {
            "final_answer": self._final_presentation_content or "",
            "selected_agent": self._selected_agent,
            "log_directory": str(log_root) if log_root else None,
            "final_answer_path": str(final_path) if final_path else None,
            "answers": answers,
            "vote_results": vote_results,
            "usage": total_usage,
            "is_orchestrator_timeout": self.is_orchestrator_timeout,
            "timeout_reason": self.timeout_reason,
        }

    def get_status(self) -> dict[str, Any]:
        """Get current orchestrator status."""
        # Calculate vote results
        vote_results = self._get_vote_results()

        return {
            "session_id": self.session_id,
            "workflow_phase": self.workflow_phase,
            "current_task": self.current_task,
            "selected_agent": self._selected_agent,
            "final_presentation_content": self._final_presentation_content,
            "vote_results": vote_results,
            "agents": {
                aid: {
                    "agent_status": agent.get_status(),
                    "coordination_state": {
                        "answer": state.answer,
                        "has_voted": state.has_voted,
                    },
                }
                for aid, (agent, state) in zip(
                    self.agents.keys(),
                    zip(self.agents.values(), self.agent_states.values()),
                )
            },
            "conversation_length": len(self.conversation_history),
        }

    def get_agent_timeout_state(self, agent_id: str) -> dict[str, Any] | None:
        """Get timeout state for display purposes.

        Returns timeout countdown and status information for a specific agent,
        used by TUI and WebUI to show per-agent timeout progress.

        Args:
            agent_id: The agent identifier

        Returns:
            Dictionary with timeout state, or None if agent not found.
            Contains:
                - round_number: Current coordination round
                - round_start_time: When current round started
                - active_timeout: Soft timeout for current round type (initial/subsequent)
                - grace_seconds: Grace period before hard block
                - elapsed: Seconds elapsed since round start
                - remaining_soft: Seconds until soft timeout
                - remaining_hard: Seconds until hard block
                - soft_timeout_fired: Whether soft timeout warning was injected
                - is_hard_blocked: Whether hard timeout is active (tools blocked)
        """
        state = self.agent_states.get(agent_id)
        if not state:
            return None

        timeout_config = self.config.timeout_config
        round_num = self.coordination_tracker.get_agent_round(agent_id)

        # Determine active timeout based on round
        if round_num == 0:
            active_timeout = timeout_config.initial_round_timeout_seconds
        else:
            active_timeout = timeout_config.subsequent_round_timeout_seconds

        # Calculate elapsed and remaining
        elapsed: float | None = None
        remaining_soft: float | None = None
        remaining_hard: float | None = None

        if state.round_start_time and active_timeout:
            elapsed = time.time() - state.round_start_time
            remaining_soft = max(0, active_timeout - elapsed)
            grace = timeout_config.round_timeout_grace_seconds or 0
            remaining_hard = max(0, active_timeout + grace - elapsed)

        # Get soft timeout fired status from hook
        soft_timeout_fired = False
        if state.round_timeout_hooks:
            post_hook, _ = state.round_timeout_hooks
            # Access the private attribute that tracks if soft timeout fired
            soft_timeout_fired = getattr(post_hook, "_soft_timeout_fired", False)

        return {
            "round_number": round_num,
            "round_start_time": state.round_start_time,
            "active_timeout": active_timeout,
            "grace_seconds": timeout_config.round_timeout_grace_seconds or 0,
            "elapsed": elapsed,
            "remaining_soft": remaining_soft,
            "remaining_hard": remaining_hard,
            "soft_timeout_fired": soft_timeout_fired,
            "is_hard_blocked": remaining_hard == 0 if remaining_hard is not None else False,
        }

    def get_configurable_system_message(self) -> str | None:
        """
        Get the configurable system message for the orchestrator.

        This can define how the orchestrator should coordinate agents, construct messages,
        handle conflicts, make decisions, etc. For example:
        - Custom voting strategies
        - Message construction templates
        - Conflict resolution approaches
        - Coordination workflow preferences

        Returns:
            Orchestrator's configurable system message if available, None otherwise
        """
        if self.config and hasattr(self.config, "get_configurable_system_message"):
            return self.config.get_configurable_system_message()
        elif self.config and hasattr(self.config, "_custom_system_instruction"):
            # Access private attribute to avoid deprecation warning
            return self.config._custom_system_instruction
        elif self.config and self.config.backend_params:
            # Check for backend-specific system prompts
            backend_params = self.config.backend_params
            if "system_prompt" in backend_params:
                return backend_params["system_prompt"]
            elif "append_system_prompt" in backend_params:
                return backend_params["append_system_prompt"]
        return None

    def _get_system_message_builder(self) -> SystemMessageBuilder:
        """Get or create the SystemMessageBuilder instance.

        Returns:
            SystemMessageBuilder instance initialized with orchestrator's config and state
        """
        if self._system_message_builder is None:
            self._system_message_builder = SystemMessageBuilder(
                config=self.config,
                message_templates=self.message_templates,
                agents=self.agents,
                snapshot_storage=self._snapshot_storage,
                session_id=self.session_id,
                agent_temporary_workspace=self._agent_temporary_workspace,
            )
        return self._system_message_builder

    def _clear_agent_workspaces(self) -> None:
        """
        Clear all agent workspaces and pre-populate with previous turn's results.

        This creates a WRITABLE copy of turn n-1 in each agent's workspace.
        Note: CLI separately provides turn n-1 as a READ-ONLY context path, allowing
        agents to both modify files (in workspace) and reference originals (via context path).
        """
        # Get previous turn (n-1) workspace for pre-population
        previous_turn_workspace = None
        if self._previous_turns:
            # Get the most recent turn (last in list)
            latest_turn = self._previous_turns[-1]
            previous_turn_workspace = Path(latest_turn["path"])

        for agent_id, agent in self.agents.items():
            if agent.backend.filesystem_manager:
                workspace_path = agent.backend.filesystem_manager.get_current_workspace()
                if workspace_path and Path(workspace_path).exists():
                    # Archive memories BEFORE clearing workspace
                    self._archive_agent_memories(agent_id, Path(workspace_path))

                    # Clear workspace contents but keep the directory
                    for item in Path(workspace_path).iterdir():
                        # Preserve .massgen metadata across turns (e.g. subagent MCP config files).
                        if item.name == ".massgen":
                            continue
                        if item.is_symlink():
                            # Remove symlinks directly (don't follow them)
                            item.unlink()
                        elif item.is_file():
                            item.unlink()
                        elif item.is_dir():
                            shutil.rmtree(item)
                    logger.info(
                        f"[Orchestrator] Cleared workspace for {agent_id}: {workspace_path}",
                    )

                    # Per-agent workspace pre-population from cancelled/incomplete turn
                    if self._pre_populated_workspaces and agent_id in self._pre_populated_workspaces:
                        source = self._pre_populated_workspaces[agent_id]
                        if source.exists():
                            logger.info(
                                f"[Orchestrator] Pre-populating {agent_id} workspace " f"with writable copy from cancelled turn: {source}",
                            )
                            for item in source.iterdir():
                                dest = Path(workspace_path) / item.name
                                if item.is_file():
                                    shutil.copy2(item, dest)
                                elif item.is_dir():
                                    shutil.copytree(
                                        item,
                                        dest,
                                        dirs_exist_ok=True,
                                        symlinks=True,
                                        ignore_dangling_symlinks=True,
                                    )
                    # Normal pre-populate with previous turn's results (creates writable copy).
                    # In execute mode, this preserves chunk-to-chunk workspace continuity.
                    elif previous_turn_workspace and previous_turn_workspace.exists():
                        if self._plan_session_id:
                            logger.info(
                                "[Orchestrator] Plan execution mode: restoring previous chunk " "workspace for %s from %s (plan_session: %s)",
                                agent_id,
                                previous_turn_workspace,
                                self._plan_session_id,
                            )
                        logger.info(
                            f"[Orchestrator] Pre-populating {agent_id} workspace with writable copy of turn n-1 from {previous_turn_workspace}",
                        )
                        for item in previous_turn_workspace.iterdir():
                            dest = Path(workspace_path) / item.name
                            if item.is_file():
                                shutil.copy2(item, dest)
                            elif item.is_dir():
                                shutil.copytree(
                                    item,
                                    dest,
                                    dirs_exist_ok=True,
                                    symlinks=True,
                                    ignore_dangling_symlinks=True,
                                )
                        logger.info(
                            f"[Orchestrator] Pre-populated {agent_id} workspace with writable copy of turn n-1",
                        )
                    elif self._plan_session_id:
                        logger.info(
                            "[Orchestrator] Plan execution mode: no previous turn workspace " "available to restore (plan_session: %s)",
                            self._plan_session_id,
                        )

        # Clear pre-populated workspaces after use (only needed for first turn after resume)
        if self._pre_populated_workspaces is not None:
            self._pre_populated_workspaces = None

        # In plan execution mode, workspace clear removes tasks/plan.json; re-seed immediately.
        self._seed_plan_execution_workspaces(context="workspace_clear")

    def _archive_agent_memories(self, agent_id: str, workspace_path: Path) -> None:
        """
        Archive memories from agent workspace before clearing.

        Copies all memory files from workspace/memory/ to archived_memories/{agent_id}_answer_{n}/
        This preserves memories from discarded answers so they're not lost.

        Args:
            agent_id: ID of the agent whose memories to archive
            workspace_path: Path to the agent's current workspace
        """
        memory_dir = workspace_path / "memory"
        if not memory_dir.exists():
            logger.info(
                f"[Orchestrator] No memory directory for {agent_id}, skipping archive",
            )
            return

        # Get current answer count for this agent
        answer_num = self.agent_states[agent_id].answer_count

        # Archive path: .massgen/sessions/{session_id}/archived_memories/agent_id_answer_n/
        # Use hardcoded session storage path (not snapshot_storage which gets cleared)
        if not self.session_id:
            logger.warning("[Orchestrator] Cannot archive memories: no session_id")
            return

        # Archives must be in sessions/ directory for persistence, not snapshots/
        archive_base = Path(".massgen/sessions") / self.session_id / "archived_memories"
        archive_path = archive_base / f"{agent_id}_answer_{answer_num}"

        # Copy entire memory/ directory to archive
        try:
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(
                memory_dir,
                archive_path,
                dirs_exist_ok=True,
                symlinks=True,
                ignore_dangling_symlinks=True,
            )
            self._namespace_verification_memory_files(archive_path, agent_id)
            logger.info(
                f"[Orchestrator] Archived memories for {agent_id} answer {answer_num} to {archive_path}",
            )
        except Exception as e:
            logger.error(
                f"[Orchestrator] Failed to archive memories for {agent_id}: {e}",
            )

    def _namespace_verification_memory_files(self, archive_path: Path, agent_id: str) -> None:
        """Namespace verification_latest and essential_files_manifest so per-agent files never collide."""
        token = self.coordination_tracker.get_path_token(agent_id)
        namespaced_name = f"verification_latest__{token}.md"
        namespaced_manifest = f"essential_files_manifest__{token}.json"
        for tier in ("short_term", "long_term"):
            tier_dir = archive_path / tier
            if not tier_dir.exists():
                continue

            legacy_file = tier_dir / "verification_latest.md"
            if legacy_file.exists():
                namespaced_file = tier_dir / namespaced_name
                if namespaced_file.exists():
                    namespaced_file.unlink()
                legacy_file.rename(namespaced_file)

            manifest_file = tier_dir / "essential_files_manifest.json"
            if manifest_file.exists():
                namespaced_mf = tier_dir / namespaced_manifest
                if namespaced_mf.exists():
                    namespaced_mf.unlink()
                manifest_file.rename(namespaced_mf)

    def _get_previous_turns_context_paths(self) -> list[dict[str, Any]]:
        """
        Get previous turns as context paths for current turn's agents.

        Returns:
            List of previous turn information with path, turn number, and task
        """
        return self._previous_turns

    async def reset(self) -> None:
        """Reset orchestrator state for new task."""
        self.conversation_history.clear()
        self.current_task = None
        self.workflow_phase = "idle"
        self._coordination_messages.clear()
        self._selected_agent = None
        self._final_presentation_content = None

        # Reset agent states
        for state in self.agent_states.values():
            state.answer = None
            state.has_voted = False
            state.votes = {}  # Clear stale vote data
            state.restart_pending = False
            state.is_killed = False
            state.timeout_reason = None
            state.error_reason = None
            state.answer_count = 0
            state.injection_count = 0
            state.midstream_injections_this_round = 0
            state.checklist_calls_this_round = 0
            state.pending_checklist_recheck_labels = set()
            state.restart_count = 0
            state.known_answer_ids = set()
            state.decomposition_answer_streak = 0
            state.seen_answer_counts = {}
            state.stop_summary = None
            state.stop_status = None

        # Reset orchestrator timeout tracking
        self.total_tokens = 0
        self.coordination_start_time = 0
        self.is_orchestrator_timeout = False
        self.timeout_reason = None

        # Clear coordination state
        self._active_streams = {}
        self._active_tasks = {}
        self._fairness_pause_log_reasons = {}
        self._fairness_block_log_states = {}
        self._round_isolation_managers = {}
        self._round_worktree_paths = {}
        self._agent_current_branches = {}

        if self.dspy_paraphraser:
            self.dspy_paraphraser.clear_cache()


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def create_orchestrator(
    agents: list[tuple],
    orchestrator_id: str = "orchestrator",
    session_id: str | None = None,
    config: AgentConfig | None = None,
    snapshot_storage: str | None = None,
    agent_temporary_workspace: str | None = None,
) -> Orchestrator:
    """
    Create a MassGen orchestrator with sub-agents.

    Args:
        agents: List of (agent_id, ChatAgent) tuples
        orchestrator_id: Unique identifier for this orchestrator (default: "orchestrator")
        session_id: Optional session ID
        config: Optional AgentConfig for orchestrator customization
        snapshot_storage: Optional path to store agent workspace snapshots
        agent_temporary_workspace: Optional path for agent temporary workspaces (for Claude Code context sharing)

    Returns:
        Configured Orchestrator
    """
    agents_dict = {agent_id: agent for agent_id, agent in agents}

    return Orchestrator(
        agents=agents_dict,
        orchestrator_id=orchestrator_id,
        session_id=session_id,
        config=config,
        snapshot_storage=snapshot_storage,
        agent_temporary_workspace=agent_temporary_workspace,
    )
