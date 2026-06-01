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

import asyncio
import concurrent.futures
import functools
import json
import os
import secrets
import shutil
import sys
import time
from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from ._broadcast_channel import BroadcastChannel
from .agent_config import AgentConfig, StepModeConfig
from .backend.base import StreamChunk
from .chat_agent import ChatAgent
from .coordination_tracker import CoordinationTracker
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
    PythonCallableHook,
    RoundTimeoutPostHook,
    RoundTimeoutPreHook,
    RoundTimeoutState,
    SubagentCompleteHook,
)
from .memory import ConversationMemory, PersistentMemoryBase
from .message_templates import MessageTemplates
from .orchestrator_collaborators import (
    ActiveCoordinationCleanup,
    AgentOrchestrationSetup,
    AnswerLimitGate,
    AnswerTextNormalizer,
    BootstrapCriteriaEngine,
    BroadcastToolInitializer,
    ChangedocCoordinator,
    ChecklistGateManager,
    CheckpointCoordinator,
    ContextPathWriteTracker,
    CriteriaEvolutionRunner,
    DspyParaphraseCoordinator,
    EvaluationCriteriaGeneratorCollaborator,
    EvaluatorResultExtractor,
    FairnessGate,
    FinalPresentationRunner,
    FinalResultReporter,
    IsolatedChangeReviewer,
    MetricsReporter,
    MidStreamInjectionHookInstaller,
    NlipRoutingInitializer,
    OrchestratorTimeoutCalculator,
    PeerAnswerVisibilityTracker,
    PersonaInjector,
    PlanningToolInjector,
    PostEvaluationRunner,
    PreCollabHelpers,
    PreviousLogRestorer,
    PromptImproverCollaborator,
    QuestionIrreversibilityAnalyzer,
    RateLimitController,
    RoundEvaluatorGateConfig,
    RoundEvaluatorRunner,
    RoundStartContextQueue,
    RunModeStrategyResolver,
    RuntimeInputDelivery,
    SkillsConfigValidator,
    SnapshotManager,
    SubagentLifecycleCoordinator,
    SubagentToolInjector,
    TraceAnalyzerRunner,
    WorkspaceLifecycleManager,
    WorkspaceModalPresenter,
)
from .persona_generator import (  # noqa: F401  re-export so tests can patch massgen.orchestrator.PersonaGenerator
    PersonaGenerator,
)
from .stream_chunk import ChunkType
from .structured_logging import (
    clear_current_round,
    get_tracer,
    log_agent_round_context,
    log_coordination_event,
    set_current_round,
)
from .system_message_builder import SystemMessageBuilder
from .tool import get_post_evaluation_tools, get_workflow_tools  # noqa: F401
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
    # Discriminative criteria emergence (v0.1.85): proposals this agent has
    # emitted in the current round that are pending merge into the orchestrator
    # accumulator at round transition. Each entry: {text, category, anti_patterns?}.
    criteria_proposals: list[dict[str, Any]] = field(default_factory=list)


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

    # --- Extracted collaborators (lazy, see massgen/orchestrator_collaborators) ---
    # Defined as cached_property so they construct on first access and work even
    # when the Orchestrator is created via __new__ (bypassing __init__).
    @functools.cached_property
    def _skills_validator(self) -> SkillsConfigValidator:
        return SkillsConfigValidator(self)

    @functools.cached_property
    def _agent_orchestration_setup(self) -> AgentOrchestrationSetup:
        return AgentOrchestrationSetup(self)

    @functools.cached_property
    def _rate_limit_controller(self) -> RateLimitController:
        return RateLimitController(self)

    @functools.cached_property
    def _nlip_routing_initializer(self) -> NlipRoutingInitializer:
        return NlipRoutingInitializer()

    @functools.cached_property
    def _run_mode_strategy_resolver(self) -> RunModeStrategyResolver:
        return RunModeStrategyResolver(self)

    @functools.cached_property
    def _runtime_input_delivery(self) -> RuntimeInputDelivery:
        return RuntimeInputDelivery(self)

    @functools.cached_property
    def _subagent_lifecycle_coordinator(self) -> SubagentLifecycleCoordinator:
        return SubagentLifecycleCoordinator(self)

    @functools.cached_property
    def _context_path_write_tracker(self) -> ContextPathWriteTracker:
        return ContextPathWriteTracker(self)

    @functools.cached_property
    def _round_evaluator_gate_config(self) -> RoundEvaluatorGateConfig:
        return RoundEvaluatorGateConfig(self)

    @functools.cached_property
    def _round_evaluator_runner(self) -> RoundEvaluatorRunner:
        return RoundEvaluatorRunner(self)

    @functools.cached_property
    def _round_start_context_queue(self) -> RoundStartContextQueue:
        return RoundStartContextQueue(self)

    @functools.cached_property
    def _dspy_paraphrase_coordinator(self) -> DspyParaphraseCoordinator:
        return DspyParaphraseCoordinator(self)

    @functools.cached_property
    def _answer_text_normalizer(self) -> AnswerTextNormalizer:
        return AnswerTextNormalizer(self)

    @functools.cached_property
    def _evaluator_result_extractor(self) -> EvaluatorResultExtractor:
        return EvaluatorResultExtractor(self)

    @functools.cached_property
    def _orchestrator_timeout_calculator(self) -> OrchestratorTimeoutCalculator:
        return OrchestratorTimeoutCalculator(self)

    @functools.cached_property
    def _workspace_modal_presenter(self) -> WorkspaceModalPresenter:
        return WorkspaceModalPresenter(self)

    @functools.cached_property
    def _final_result_reporter(self) -> FinalResultReporter:
        return FinalResultReporter(self)

    @functools.cached_property
    def _metrics_reporter(self) -> MetricsReporter:
        return MetricsReporter(self)

    @functools.cached_property
    def _workspace_lifecycle_manager(self) -> WorkspaceLifecycleManager:
        return WorkspaceLifecycleManager(self)

    @functools.cached_property
    def _broadcast_tool_initializer(self) -> BroadcastToolInitializer:
        return BroadcastToolInitializer(self)

    @functools.cached_property
    def _bootstrap_criteria_engine(self) -> BootstrapCriteriaEngine:
        return BootstrapCriteriaEngine(self)

    @functools.cached_property
    def _isolated_change_reviewer(self) -> IsolatedChangeReviewer:
        return IsolatedChangeReviewer(self)

    @functools.cached_property
    def _active_coordination_cleanup(self) -> ActiveCoordinationCleanup:
        return ActiveCoordinationCleanup(self)

    @functools.cached_property
    def _checkpoint_coordinator(self) -> CheckpointCoordinator:
        return CheckpointCoordinator(self)

    @functools.cached_property
    def _fairness_gate(self) -> FairnessGate:
        return FairnessGate(self)

    @functools.cached_property
    def _planning_tool_injector(self) -> PlanningToolInjector:
        return PlanningToolInjector(self)

    @functools.cached_property
    def _answer_limit_gate(self) -> AnswerLimitGate:
        return AnswerLimitGate(self)

    @functools.cached_property
    def _subagent_tool_injector(self) -> SubagentToolInjector:
        return SubagentToolInjector(self)

    @functools.cached_property
    def _post_evaluation_runner(self) -> PostEvaluationRunner:
        return PostEvaluationRunner(self)

    @functools.cached_property
    def _final_presentation_runner(self) -> FinalPresentationRunner:
        return FinalPresentationRunner(self)

    @functools.cached_property
    def _pre_collab_helpers(self) -> PreCollabHelpers:
        return PreCollabHelpers(self)

    @functools.cached_property
    def _peer_answer_visibility_tracker(self) -> PeerAnswerVisibilityTracker:
        return PeerAnswerVisibilityTracker(self)

    @functools.cached_property
    def _midstream_injection_hook_installer(self) -> MidStreamInjectionHookInstaller:
        return MidStreamInjectionHookInstaller(self)

    @functools.cached_property
    def _checklist_gate_manager(self) -> ChecklistGateManager:
        return ChecklistGateManager(self)

    @functools.cached_property
    def _trace_analyzer_runner(self) -> TraceAnalyzerRunner:
        return TraceAnalyzerRunner(self)

    @functools.cached_property
    def _criteria_evolution_runner(self) -> CriteriaEvolutionRunner:
        return CriteriaEvolutionRunner(self)

    @functools.cached_property
    def _snapshot_manager(self) -> SnapshotManager:
        return SnapshotManager(self)

    @functools.cached_property
    def _persona_injector(self) -> PersonaInjector:
        return PersonaInjector(self)

    @functools.cached_property
    def _evaluation_criteria_generator_collaborator(self) -> EvaluationCriteriaGeneratorCollaborator:
        return EvaluationCriteriaGeneratorCollaborator(self)

    @functools.cached_property
    def _previous_log_restorer(self) -> PreviousLogRestorer:
        return PreviousLogRestorer(self)

    @functools.cached_property
    def _prompt_improver_collaborator(self) -> PromptImproverCollaborator:
        return PromptImproverCollaborator(self)

    @functools.cached_property
    def _question_irreversibility_analyzer(self) -> QuestionIrreversibilityAnalyzer:
        return QuestionIrreversibilityAnalyzer(self)

    @functools.cached_property
    def _changedoc_coordinator(self) -> ChangedocCoordinator:
        return ChangedocCoordinator(self)

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

        # Discriminative criteria emergence (v0.1.85): accumulator of criteria
        # emitted by agents (Variant A) or a between-rounds critic (Variant B).
        # Each entry: {text, category, anti_patterns?, verify_by?}. Merged across
        # rounds; capped by coordination_config.bootstrap_max_total.
        self._bootstrap_criteria_accumulator: list[dict[str, Any]] = []
        self._bootstrap_round_index: int = 0
        # Most recent per-agent per-criterion scores ({label: {Ei: score}}), used
        # to demote non-discriminative ("free-pass") criteria in bootstrap mode.
        self._last_per_agent_criterion_scores: dict[str, dict[str, Any]] = {}

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
            """Delegates to AgentOrchestrationSetup collaborator."""
            self._agent_orchestration_setup.setup_agent_orchestration(
                agent_id,
                agent,
                skills_directory,
                massgen_skills,
                load_previous_session_skills,
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

        # Extracted collaborators (see massgen/orchestrator_collaborators) are
        # exposed as lazy ``cached_property`` accessors defined on the class, so
        # they resolve correctly even when an Orchestrator is built via
        # ``__new__`` (e.g. in tests that bypass ``__init__``). The delegator
        # methods keep all existing call sites working unchanged.

        # Initialize NLIP routers for agents if enabled
        if self.enable_nlip:
            self._init_nlip_routing()

        # Initialize broadcast tools (independent of NLIP)
        self._init_broadcast_tools()

        # Initialize checklist MCP tool if using tool-gated mode
        self._init_checklist_tool()

        # Initialize checkpoint MCP tool if main agent is set
        self._init_checkpoint_tool()

        # Inject standalone checkpoint MCP into a single agent if enabled.
        self._init_standalone_checkpoint_tool()

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
        """Delegates to ChecklistGateManager."""
        return self._checklist_gate_manager.get_decomposition_criteria_for_agent(agent_id)

    def _get_active_criteria(
        self,
        agent_id: str | None = None,
    ) -> tuple[list[str] | None, dict[str, str] | None, dict[str, str] | None, dict[str, list[str]] | None, dict[str, dict[str, str]] | None]:
        """Delegates to ChecklistGateManager."""
        return self._checklist_gate_manager.get_active_criteria(agent_id)

    def _drain_pending_criteria_proposals(self) -> None:
        """Delegates to BootstrapCriteriaEngine."""
        self._bootstrap_criteria_engine.drain_pending_criteria_proposals()

    async def _maybe_run_bootstrap_discriminator(self, current_answers: dict[str, str]) -> int:
        """Delegates to BootstrapCriteriaEngine."""
        return await self._bootstrap_criteria_engine.maybe_run_bootstrap_discriminator(current_answers)

    async def _run_bootstrap_discriminator_step(self) -> int:
        """Delegates to BootstrapCriteriaEngine."""
        return await self._bootstrap_criteria_engine.run_bootstrap_discriminator_step()

    def _drain_at_session_end(self) -> None:
        """Delegates to BootstrapCriteriaEngine."""
        self._bootstrap_criteria_engine.drain_at_session_end()

    def _persist_bootstrap_accumulator(self) -> None:
        """Delegates to BootstrapCriteriaEngine."""
        self._bootstrap_criteria_engine.persist_bootstrap_accumulator()

    def _resolve_effective_checklist_criteria(
        self,
        agent_id: str | None = None,
    ) -> tuple[list[str], dict[str, str], dict[str, str] | None, str, dict[str, list[str]] | None, dict[str, dict[str, str]] | None]:
        """Delegates to ChecklistGateManager."""
        return self._checklist_gate_manager.resolve_effective_checklist_criteria(agent_id)

    def _push_cached_criteria_to_display(self, *, force: bool = False) -> None:
        """Delegates to ChecklistGateManager."""
        self._checklist_gate_manager.push_cached_criteria_to_display(force=force)

    def _init_checklist_tool(self) -> None:
        """Delegates to ChecklistGateManager."""
        self._checklist_gate_manager.init_checklist_tool()

    def _init_checklist_tool_sdk(
        self,
        agent_id,
        backend,
        checklist_state,
        checklist_items,
    ) -> None:
        """Delegates to ChecklistGateManager."""
        self._checklist_gate_manager.init_checklist_tool_sdk(
            agent_id,
            backend,
            checklist_state,
            checklist_items,
        )

    def _init_checklist_tool_stdio(self, agent_id, backend, checklist_state, items):
        """Delegates to ChecklistGateManager."""
        self._checklist_gate_manager.init_checklist_tool_stdio(
            agent_id,
            backend,
            checklist_state,
            items,
        )

    def _init_checkpoint_tool(self) -> None:
        """Set up checkpoint tool for the main agent (delegates to CheckpointCoordinator)."""
        self._checkpoint_coordinator.init_checkpoint_tool()

    _STANDALONE_CHECKPOINT_SERVER_NAME = "massgen_checkpoint_standalone"

    def _strip_standalone_checkpoint_from_all_agents(self) -> None:
        """Delegates to CheckpointCoordinator."""
        self._checkpoint_coordinator.strip_standalone_checkpoint_from_all_agents()

    def _init_standalone_checkpoint_tool(self) -> None:
        """Delegates to CheckpointCoordinator."""
        self._checkpoint_coordinator.init_standalone_checkpoint_tool()

    def _detect_convergence(self, agent_id: str) -> tuple:
        """Delegates to ChecklistGateManager."""
        return self._checklist_gate_manager.detect_convergence(agent_id)

    def _sync_stdio_checklist_state_from_specs(self, agent_id: str) -> None:
        """Delegates to ChecklistGateManager."""
        self._checklist_gate_manager.sync_stdio_checklist_state_from_specs(agent_id)

    def _refresh_checklist_state_for_agent(
        self,
        agent_id: str,
        prefer_local_runtime_state: bool = False,
    ) -> None:
        """Delegates to ChecklistGateManager."""
        self._checklist_gate_manager.refresh_checklist_state_for_agent(
            agent_id,
            prefer_local_runtime_state=prefer_local_runtime_state,
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
        success_contract: "dict | None" = None,
        deprioritize_or_remove: "list | None" = None,
    ) -> None:
        """Delegates to ChecklistGateManager."""
        self._checklist_gate_manager.set_round_evaluator_task_mode(
            agent_id,
            enabled=enabled,
            primary_artifact_path=primary_artifact_path,
            verdict_artifact_path=verdict_artifact_path,
            next_tasks_artifact_path=next_tasks_artifact_path,
            objective=objective,
            primary_strategy=primary_strategy,
            why_this_strategy=why_this_strategy,
            strategy_mode=strategy_mode,
            incremental_override_reason=incremental_override_reason,
            success_contract=success_contract,
            deprioritize_or_remove=deprioritize_or_remove,
        )

    # ------------------------------------------------------------------
    # Checkpoint coordination helpers
    # ------------------------------------------------------------------

    def set_main_agent(self, agent_id: str) -> None:
        """Designate an agent as the main orchestrating agent (delegates to CheckpointCoordinator)."""
        self._checkpoint_coordinator.set_main_agent(agent_id)

    @property
    def is_checkpoint_mode(self) -> bool:
        """Whether checkpoint coordination is configured (delegates to CheckpointCoordinator)."""
        return self._checkpoint_coordinator.is_checkpoint_mode()

    def _is_agent_active_in_current_mode(self, agent_id: str) -> bool:
        """Check if an agent should be active in the current mode (delegates to CheckpointCoordinator)."""
        return self._checkpoint_coordinator.is_agent_active_in_current_mode(agent_id)

    async def _activate_checkpoint(self, signal: dict[str, Any]) -> str:
        """Spawn a checkpoint subprocess and return the consensus result (delegates to CheckpointCoordinator)."""
        return await self._checkpoint_coordinator.activate_checkpoint(signal)

    def ensure_workspace_symlinks(self) -> None:
        """Ensure per-agent workspace symlinks (delegates to AgentOrchestrationSetup)."""
        self._agent_orchestration_setup.ensure_workspace_symlinks()

    def _init_nlip_routing(self) -> None:
        """Initialize NLIP routing for all agents (delegates to NlipRoutingInitializer)."""
        self._nlip_routing_initializer.initialize(self.agents, self.nlip_config)

    def _init_broadcast_tools(self) -> None:
        """Delegates to BroadcastToolInitializer."""
        self._broadcast_tool_initializer.init_broadcast_tools()

    def _register_broadcast_custom_tools(
        self,
        broadcast_mode: str,
        wait_by_default: bool,
        sensitivity: str = "medium",
    ) -> None:
        """Delegates to BroadcastToolInitializer."""
        self._broadcast_tool_initializer.register_broadcast_custom_tools(
            broadcast_mode,
            wait_by_default,
            sensitivity,
        )

    async def _prepare_paraphrases_for_agents(self, question: str) -> None:
        """Generate and assign DSPy paraphrases (delegates to DspyParaphraseCoordinator)."""
        await self._dspy_paraphrase_coordinator.prepare_paraphrases_for_agents(question)

    def get_paraphrase_status(self) -> dict[str, Any]:
        """Return current DSPy paraphrase assignments and metrics (delegates to DspyParaphraseCoordinator)."""
        return self._dspy_paraphrase_coordinator.get_paraphrase_status()

    def _validate_skills_config(self) -> None:
        """Validate skills configuration (delegates to SkillsConfigValidator)."""
        self._skills_validator.validate()

    def _inject_planning_tools_for_all_agents(self) -> None:
        """Inject planning MCP tools into all agents (delegates to PlanningToolInjector)."""
        self._planning_tool_injector.inject_planning_tools_for_all_agents()

    def _planning_server_name(self, agent_id: str) -> str:
        """Return the anonymous MCP server name for this agent's planning tools (delegates)."""
        return self._planning_tool_injector.planning_server_name(agent_id)

    def _subagent_server_name(self, agent_id: str) -> str:
        """Return the anonymous MCP server name for this agent's subagent tools (delegates to SubagentToolInjector)."""
        return self._subagent_tool_injector.subagent_server_name(agent_id)

    def _inject_planning_tools_for_agent(self, agent_id: str, agent: Any) -> None:
        """Inject planning MCP tools into a specific agent (delegates to PlanningToolInjector)."""
        self._planning_tool_injector.inject_planning_tools_for_agent(agent_id, agent)

    def _is_round_learning_capture_enabled(self) -> bool:
        """Return whether round-time learning capture should be enabled.

        Delegates to RunModeStrategyResolver.
        """
        return self._run_mode_strategy_resolver.is_round_learning_capture_enabled()

    def _get_final_answer_strategy(self) -> str:
        """Return the effective final-answer strategy (delegates to RunModeStrategyResolver)."""
        return self._run_mode_strategy_resolver.get_final_answer_strategy()

    def _expects_final_presentation_stage(self) -> bool:
        """Return whether the config expects a presenter stage (delegates to RunModeStrategyResolver)."""
        return self._run_mode_strategy_resolver.expects_final_presentation_stage()

    def _should_skip_vote_rounds_for_synthesize(self) -> bool:
        """Return whether quick synthesize runs skip vote rounds (delegates to RunModeStrategyResolver)."""
        return self._run_mode_strategy_resolver.should_skip_vote_rounds_for_synthesize()

    def _is_round_verification_capture_enabled(self) -> bool:
        """Return whether round-time verification capture is enabled (delegates to RunModeStrategyResolver)."""
        return self._run_mode_strategy_resolver.is_round_verification_capture_enabled()

    def _create_planning_mcp_config(self, agent_id: str, agent: Any) -> dict[str, Any]:
        """Create MCP server configuration for planning tools (delegates to PlanningToolInjector)."""
        return self._planning_tool_injector.create_planning_mcp_config(agent_id, agent)

    def _write_planning_injection(self, agent_id: str, task_plan: list[dict]) -> None:
        """Write inject_tasks.json to agent's planning injection directory (delegates to PlanningToolInjector)."""
        self._planning_tool_injector.write_planning_injection(agent_id, task_plan)

    def _inject_subagent_tools_for_all_agents(self) -> None:
        """Inject subagent MCP tools into all agents (delegates to SubagentToolInjector)."""
        self._subagent_tool_injector.inject_subagent_tools_for_all_agents()

    def _inject_subagent_tools_for_agent(self, agent_id: str, agent: Any) -> None:
        """Inject subagent MCP tools into a specific agent (delegates to SubagentToolInjector)."""
        self._subagent_tool_injector.inject_subagent_tools_for_agent(agent_id, agent)

    def setup_subagent_spawn_callbacks(self) -> None:
        """Set up subagent spawn callbacks for all agents (delegates to SubagentToolInjector).

        Called from ``CoordinationUI.set_orchestrator()`` after coordination_ui is assigned.
        """
        self._subagent_tool_injector.setup_subagent_spawn_callbacks()

    def _setup_subagent_spawn_callback(self, agent_id: str, agent: Any) -> None:
        """Set up TUI spawn callback for a specific agent (delegates to SubagentToolInjector)."""
        self._subagent_tool_injector.setup_subagent_spawn_callback(agent_id, agent)

    def _write_subagent_type_dirs(self, workspace_root: Any) -> None:
        """Write SUBAGENT.md dirs to workspace_root (delegates to SubagentToolInjector)."""
        self._subagent_tool_injector.write_subagent_type_dirs(workspace_root)

    def _build_parent_coordination_config_for_subagents(self) -> dict[str, Any]:
        """Collect parent coordination fields for subagent inheritance (delegates to SubagentToolInjector)."""
        return self._subagent_tool_injector.build_parent_coordination_config_for_subagents()

    def _create_subagent_mcp_config(self, agent_id: str, agent: Any) -> dict[str, Any]:
        """Create MCP server configuration for subagent tools (delegates to SubagentToolInjector)."""
        return self._subagent_tool_injector.create_subagent_mcp_config(agent_id, agent)

    def _build_parent_agent_configs(self) -> list[dict[str, Any]]:
        """Build simplified agent configs for subagent inheritance (delegates to PreCollabHelpers)."""
        return self._pre_collab_helpers.build_parent_agent_configs()

    def _get_parent_workspace(self, fallback_prefix: str = "massgen_precollab_") -> str:
        """Return the first agent's workspace path, or a temp dir (delegates to PreCollabHelpers)."""
        return self._pre_collab_helpers.get_parent_workspace(fallback_prefix)

    @staticmethod
    def _get_log_directory() -> str | None:
        """Return the current log session directory as a string, or None (delegates to PreCollabHelpers)."""
        return PreCollabHelpers.get_log_directory()

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
        """Build a callback for pre-collab subagent start notifications (delegates to PreCollabHelpers)."""
        return self._pre_collab_helpers.make_precollab_started_callback(anchor_agent, call_id, display)

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
        """Emit event + notify display for a pre-collab phase completion (delegates to PreCollabHelpers)."""
        self._pre_collab_helpers.notify_precollab_completed(
            anchor_agent,
            subagent_id,
            call_id,
            display,
            status=status,
            answer_preview=answer_preview,
            error=error,
        )

    # ------------------------------------------------------------------
    # Pre-collab phases
    # ------------------------------------------------------------------

    async def _generate_and_inject_personas(self) -> None:
        """Delegates to persona_injector; see collaborator for full docs."""
        return await self._persona_injector.generate_and_inject_personas()

    async def _generate_and_inject_evaluation_criteria(self) -> None:
        """Delegates to evaluation_criteria_generator collaborator."""
        return await self._evaluation_criteria_generator_collaborator.generate_and_inject_evaluation_criteria()

    async def _improve_and_inject_prompt(self) -> None:
        """Delegates to prompt_improver_collaborator; see collaborator for full docs."""
        await self._prompt_improver_collaborator.improve_and_inject_prompt()

    def _save_evaluation_criteria_to_log(self, criteria: list) -> None:
        """Delegates to evaluation_criteria_generator collaborator."""
        return self._evaluation_criteria_generator_collaborator.save_evaluation_criteria_to_log(criteria)

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
        """Delegates to persona_injector; see collaborator for full docs."""
        return self._persona_injector.get_persona_for_agent(agent_id, has_peer_answers)

    def get_generated_personas(self) -> dict[str, Any]:
        """Delegates to persona_injector; see collaborator for full docs."""
        return self._persona_injector.get_generated_personas()

    def get_generated_evaluation_criteria(self) -> list | None:
        """Delegates to evaluation_criteria_generator collaborator."""
        return self._evaluation_criteria_generator_collaborator.get_generated_evaluation_criteria()

    def _save_personas_to_log(self, personas: dict[str, Any]) -> None:
        """Delegates to persona_injector; see collaborator for full docs."""
        return self._persona_injector.save_personas_to_log(personas)

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
        """Delegator: see SnapshotManager."""
        return await self._snapshot_manager.inject_shared_memory_context(messages, agent_id)

    def _merge_agent_memories_to_winner(self, winning_agent_id: str) -> None:
        """Delegates to WorkspaceLifecycleManager; see collaborator for full docs."""
        self._workspace_lifecycle_manager.merge_agent_memories_to_winner(winning_agent_id)

    async def _record_to_shared_memory(
        self,
        agent_id: str,
        content: str,
        role: str = "assistant",
    ) -> None:
        """Delegator: see SnapshotManager."""
        await self._snapshot_manager.record_to_shared_memory(agent_id, content, role)

    def save_coordination_logs(self):
        """Delegator: see MetricsReporter."""
        return self._metrics_reporter.save_coordination_logs()

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
        """Delegator: see MetricsReporter."""
        return self._metrics_reporter.save_metrics(log_dir)

    def _collect_subagent_costs(self, log_dir: Path) -> dict[str, Any]:
        """Delegator: see MetricsReporter."""
        return self._metrics_reporter.collect_subagent_costs(log_dir)

    def _format_planning_mode_ui(
        self,
        has_irreversible: bool,
        blocked_tools: set,
        has_isolated_workspaces: bool,
        user_question: str,
    ) -> str:
        """Delegates to QuestionIrreversibilityAnalyzer.format_planning_mode_ui (@staticmethod)."""
        return self._question_irreversibility_analyzer.format_planning_mode_ui(
            has_irreversible,
            blocked_tools,
            has_isolated_workspaces,
            user_question,
        )

    async def _analyze_question_irreversibility(
        self,
        user_question: str,
        conversation_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Delegate to :class:`QuestionIrreversibilityAnalyzer`.

        Kept on Orchestrator with an identical signature because numerous
        tests (e.g. ``test_intelligent_planning_mode.py``) and internal call
        sites invoke ``orch._analyze_question_irreversibility(...)`` directly.
        """
        return await self._question_irreversibility_analyzer.analyze(
            user_question,
            conversation_context,
        )

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

            # Bootstrap discriminator gate (Variant B): runs once per unique
            # answer-label set when criteria_mode == "bootstrap_subagent".
            # Emits gap-driven criteria from a critic and merges into the
            # accumulator before agents restart. No-op for static / inline.
            try:
                await self._maybe_run_bootstrap_discriminator(current_answers)
            except Exception as exc:
                logger.warning("[bootstrap_criteria] discriminator gate failed: %s", exc)

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
        """Delegator: see SnapshotManager."""
        return await self._snapshot_manager.copy_all_snapshots_to_temp_workspace(agent_id)

    async def _restore_from_previous_log(self, resume_config: dict[str, Any]) -> None:
        """Delegates to previous_log_restorer; see collaborator for full docs."""
        return await self._previous_log_restorer.restore_from_previous_log(resume_config)

    def _restore_workspace_from_latest_answer_dir(self, agent_id: str) -> bool:
        """Delegates to previous_log_restorer; see collaborator for full docs."""
        return self._previous_log_restorer.restore_workspace_from_latest_answer_dir(agent_id)

    def _sync_applied_context_files_into_final_artifacts(
        self,
        agent_id: str,
        target_path: str,
        relative_paths: list[str],
    ) -> None:
        """Delegator: see ChangedocCoordinator."""
        return self._changedoc_coordinator.sync_applied_context_files_into_final_artifacts(
            agent_id,
            target_path,
            relative_paths,
        )

    async def _save_agent_snapshot(
        self,
        agent_id: str,
        answer_content: str = None,
        vote_data: dict[str, Any] = None,
        is_final: bool = False,
        context_data: Any = None,
    ) -> str:
        """Delegator: see SnapshotManager.

        Saves a snapshot of an agent's working directory and answer/vote with the same timestamp.

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
        return await self._snapshot_manager.save_agent_snapshot(
            agent_id=agent_id,
            answer_content=answer_content,
            vote_data=vote_data,
            is_final=is_final,
            context_data=context_data,
        )

    async def _save_partial_snapshots_for_early_termination(self) -> None:
        """Delegator: see SnapshotManager."""
        await self._snapshot_manager.save_partial_snapshots_for_early_termination()

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
        """Delegator: see SnapshotManager."""
        self._snapshot_manager.save_partial_workspace_snapshots_for_interrupted_turn(
            agent_id=agent_id,
            backend=backend,
            timestamp=timestamp,
            log_session_dir=log_session_dir,
        )

    def _save_partial_execution_traces_for_interrupted_turn(self) -> None:
        """Delegator: see SnapshotManager."""
        self._snapshot_manager.save_partial_execution_traces_for_interrupted_turn()

    def get_last_context(self, agent_id: str) -> Any:
        """Get the last context for an agent, or None if not available."""
        return self.agent_states[agent_id].last_context if agent_id in self.agent_states else None

    async def _close_agent_stream(
        self,
        agent_id: str,
        active_streams: dict[str, AsyncGenerator],
    ) -> None:
        """Delegator: see MidStreamInjectionHookInstaller."""
        await self._midstream_injection_hook_installer.close_agent_stream(agent_id, active_streams)

    def _check_restart_pending(self, agent_id: str) -> bool:
        """Delegator: see MidStreamInjectionHookInstaller."""
        return self._midstream_injection_hook_installer.check_restart_pending(agent_id)

    def _should_defer_restart_for_first_answer(self, agent_id: str) -> bool:
        """Delegator: see MidStreamInjectionHookInstaller."""
        return self._midstream_injection_hook_installer.should_defer_restart_for_first_answer(agent_id)

    async def _clear_framework_mcp_state(self, agent_id: str) -> None:
        """Delegator: see MidStreamInjectionHookInstaller."""
        await self._midstream_injection_hook_installer.clear_framework_mcp_state(agent_id)

    def _compute_plan_progress_stats(self, workspace_path: str) -> dict[str, Any] | None:
        """Delegator: see MidStreamInjectionHookInstaller."""
        return self._midstream_injection_hook_installer.compute_plan_progress_stats(workspace_path)

    def _build_tool_result_injection(
        self,
        agent_id: str,
        new_answers: dict[str, str],
        existing_answers: dict[str, str] | None = None,
    ) -> str:
        """Delegator: see MidStreamInjectionHookInstaller."""
        return self._midstream_injection_hook_installer.build_tool_result_injection(
            agent_id,
            new_answers,
            existing_answers,
        )

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
        """Delegator: see SubagentLifecycleCoordinator."""
        self._subagent_lifecycle_coordinator.on_subagent_complete(
            parent_agent_id,
            subagent_id,
            result,
        )

    def _on_background_subagent_complete(
        self,
        parent_agent_id: str,
        subagent_id: str,
        result: "SubagentResult",
    ) -> None:
        """Delegator: see SubagentLifecycleCoordinator."""
        self._subagent_lifecycle_coordinator.on_background_subagent_complete(
            parent_agent_id,
            subagent_id,
            result,
        )

    def _schedule_background_wait_interrupt_for_agent(
        self,
        agent_id: str,
        trigger: str = "background_subagent_complete",
    ) -> None:
        """Delegator: see SubagentLifecycleCoordinator."""
        self._subagent_lifecycle_coordinator.schedule_background_wait_interrupt_for_agent(
            agent_id,
            trigger=trigger,
        )

    async def _get_pending_subagent_results_async(
        self,
        agent_id: str,
    ) -> list[tuple[str, "SubagentResult"]]:
        """Delegator: see SubagentLifecycleCoordinator."""
        return await self._subagent_lifecycle_coordinator.get_pending_subagent_results_async(agent_id)

    async def _collect_pending_subagent_results_async(
        self,
        agent_id: str,
    ) -> list[tuple[str, "SubagentResult"]]:
        """Delegator: see SubagentLifecycleCoordinator."""
        return await self._subagent_lifecycle_coordinator.collect_pending_subagent_results_async(agent_id)

    async def _cancel_running_subagents_for_agent(
        self,
        agent_id: str,
    ) -> int:
        """Delegator: see SubagentLifecycleCoordinator."""
        return await self._subagent_lifecycle_coordinator.cancel_running_subagents_for_agent(agent_id)

    async def _cancel_running_background_work_for_agent(self, agent_id: str) -> None:
        """Delegator: see SubagentLifecycleCoordinator."""
        await self._subagent_lifecycle_coordinator.cancel_running_background_work_for_agent(agent_id)

    def _get_pending_subagent_results(
        self,
        agent_id: str,
    ) -> list[tuple[str, "SubagentResult"]]:
        """Delegator: see SubagentLifecycleCoordinator."""
        return self._subagent_lifecycle_coordinator.get_pending_subagent_results(agent_id)

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

        backend = getattr(agent, "backend", None)
        backend_provider = backend.get_provider_name() if backend and hasattr(backend, "get_provider_name") else ""

        # Codex uses a hybrid path: native Bash hooks plus MCP/file-based payload delivery.
        if (
            backend_provider == "codex"
            and hasattr(agent.backend, "supports_native_hooks")
            and agent.backend.supports_native_hooks()
            and hasattr(agent.backend, "supports_mcp_server_hooks")
            and agent.backend.supports_mcp_server_hooks()
        ):
            self._setup_codex_hybrid_hooks(agent_id, agent, answers)
            return

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

    def _setup_codex_hybrid_hooks(
        self,
        agent_id: str,
        agent: ChatAgent,
        answers: dict[str, str],
    ) -> None:
        """Set up Codex's hybrid delivery path.

        Codex native hooks currently cover Bash-only ``PreToolUse`` and
        ``PostToolUse``. MassGen runtime payload delivery still flows through the
        shared ``hook_post_tool_use.json`` file and the MCP/file carry-forward
        path, so we register a lightweight native Bash bridge and keep the
        existing Codex MCP setup in place.
        """
        adapter = agent.backend.get_native_hook_adapter()
        if not adapter:
            logger.warning(
                "[Orchestrator] Codex backend reported native hooks but no adapter was available for %s",
                agent_id,
            )
            self._setup_codex_mcp_hooks(agent_id, agent, answers)
            return

        manager = GeneralHookManager()
        manager.register_global_hook(
            HookType.POST_TOOL_USE,
            PythonCallableHook(
                name="codex_post_tool_bridge",
                handler=lambda _event: None,
                matcher="Bash",
            ),
        )

        native_config = adapter.build_native_hooks_config(
            manager,
            agent_id=agent_id,
        )
        agent.backend.set_native_hooks_config(native_config)
        # Codex's native hook surface is Bash-only, but the TUI and manual
        # wrap-up flow still need real timeout hook objects in agent state.
        # Register those separately so request_answer_now() and timeout status
        # work on the hybrid path without changing the native hooks config.
        timeout_manager = GeneralHookManager()
        self._register_round_timeout_hooks(agent_id, timeout_manager)
        self._setup_codex_mcp_hooks(agent_id, agent, answers)

        hooks = native_config.get("hooks", {}) if isinstance(native_config, dict) else {}
        logger.info(
            "[Orchestrator] Set up Codex hybrid hooks for %s: PreToolUse=%d, PostToolUse=%d",
            agent_id,
            len(hooks.get("PreToolUse", [])),
            len(hooks.get("PostToolUse", [])),
        )

    async def _collect_round_timeout_runtime_sections(
        self,
        agent_id: str,
    ) -> list[str]:
        """Collect timeout/wrap-up injection content for hybrid or hookless delivery paths."""
        state = self.agent_states.get(agent_id)
        if not state or not state.round_timeout_hooks:
            return []

        post_hook, _ = state.round_timeout_hooks
        execute = getattr(post_hook, "execute", None)
        if not callable(execute):
            return []

        try:
            result = await execute(
                "codex_runtime_timeout_flush",
                "{}",
                _context={"agent_id": agent_id, "hook_type": "PostToolUse"},
            )
        except Exception as e:
            logger.warning(
                "[Orchestrator] Failed to evaluate round timeout hook for %s: %s",
                agent_id,
                e,
            )
            return []

        inject = getattr(result, "inject", None) or {}
        content = inject.get("content")
        if not content:
            return []

        display = None
        if hasattr(self, "coordination_ui") and self.coordination_ui:
            display = getattr(self.coordination_ui, "display", None)
        timeout_state = self.get_agent_timeout_state(agent_id)
        if display and hasattr(display, "update_timeout_status") and timeout_state:
            display.update_timeout_status(agent_id, timeout_state)

        return [str(content)]

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

        # 0.5. Check for soft-timeout / manual wrap-up injections.
        injection_parts.extend(
            await self._collect_round_timeout_runtime_sections(agent_id),
        )

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
                f"[Orchestrator] Wrote {len(combined)} chars to hook file for {agent_id} " f"({len(injection_parts)} parts)",
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

        # 0.5) Round timeout / manual wrap-up
        sections.extend(
            await self._collect_round_timeout_runtime_sections(agent_id),
        )

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
        """Delegator: see RuntimeInputDelivery."""
        return self._runtime_input_delivery.build_runtime_user_instructions_context(agent_id)

    def _insert_runtime_user_instructions_after_original_message(  # noqa: PLR6301
        self,
        user_message: str,
        runtime_instructions_block: str,
    ) -> str:
        """Pure delegator to RuntimeInputDelivery — does NOT use self. Stays an
        instance method (not @staticmethod) so existing test usage like
        ``Orchestrator._insert_..._after_original_message(None, ...)`` keeps working."""
        return RuntimeInputDelivery.insert_runtime_user_instructions_after_original_message(
            user_message,
            runtime_instructions_block,
        )

    def _insert_runtime_context_blocks_after_original_message(  # noqa: PLR6301
        self,
        user_message: str,
        context_blocks: Sequence[str | None],
    ) -> str:
        """Pure delegator to RuntimeInputDelivery — does NOT use self."""
        return RuntimeInputDelivery.insert_runtime_context_blocks_after_original_message(
            user_message,
            context_blocks,
        )

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
        """Delegator: see RuntimeInputDelivery."""
        self._runtime_input_delivery.ensure_runtime_human_input_hook_initialized()

    def _ensure_runtime_inbox_poller_initialized(self) -> None:
        """Delegator: see RuntimeInputDelivery."""
        self._runtime_input_delivery.ensure_runtime_inbox_poller_initialized()

    def _poll_runtime_inbox(self) -> None:
        """Delegator: see RuntimeInputDelivery."""
        self._runtime_input_delivery.poll_runtime_inbox()

    @staticmethod
    def _try_parse_json_dict_from_text(raw_text: str | None) -> dict[str, Any] | None:
        """Delegator: see SubagentLifecycleCoordinator."""
        return SubagentLifecycleCoordinator.try_parse_json_dict_from_text(raw_text)

    @staticmethod
    def _extract_text_from_mcp_content_payload(content: Any) -> str | None:
        """Delegator: see SubagentLifecycleCoordinator."""
        return SubagentLifecycleCoordinator.extract_text_from_mcp_content_payload(content)

    @classmethod
    def _normalize_subagent_mcp_result(cls, raw_result: Any) -> dict[str, Any] | None:
        """Delegator: see SubagentLifecycleCoordinator."""
        return SubagentLifecycleCoordinator.normalize_subagent_mcp_result(raw_result)

    async def _call_subagent_mcp_tool_async(
        self,
        parent_agent_id: str,
        tool_name: str,
        params: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Delegator: see SubagentLifecycleCoordinator."""
        return await self._subagent_lifecycle_coordinator.call_subagent_mcp_tool_async(
            parent_agent_id,
            tool_name,
            params,
        )

    @staticmethod
    def _is_reconnectable_background_mcp_error(error: Exception | str) -> bool:
        """Delegator: see SubagentLifecycleCoordinator."""
        return SubagentLifecycleCoordinator.is_reconnectable_background_mcp_error(error)

    def _call_subagent_mcp_tool(
        self,
        parent_agent_id: str,
        tool_name: str,
        params: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Delegator: see SubagentLifecycleCoordinator."""
        return self._subagent_lifecycle_coordinator.call_subagent_mcp_tool(
            parent_agent_id,
            tool_name,
            params,
        )

    def _has_subagent_mcp_for_agent(self, agent_id: str) -> bool:
        """Delegator: see SubagentLifecycleCoordinator."""
        return self._subagent_lifecycle_coordinator.has_subagent_mcp_for_agent(agent_id)

    async def _direct_spawn_subagents(
        self,
        parent_agent_id: str,
        tasks: list[dict[str, Any]],
        refine: bool = True,
    ) -> dict[str, Any]:
        """Delegator: see SubagentLifecycleCoordinator."""
        return await self._subagent_lifecycle_coordinator.direct_spawn_subagents(
            parent_agent_id,
            tasks,
            refine=refine,
        )

    def _send_runtime_message_via_direct_inbox_write(
        self,
        parent_agent_id: str,
        subagent_id: str,
        content: str,
        target_agents: list[str] | None = None,
    ) -> bool:
        """Delegator: see SubagentLifecycleCoordinator."""
        return self._subagent_lifecycle_coordinator.send_runtime_message_via_direct_inbox_write(
            parent_agent_id=parent_agent_id,
            subagent_id=subagent_id,
            content=content,
            target_agents=target_agents,
        )

    def _resolve_subagent_parent_workspace(self, parent_agent_id: str) -> Path | None:
        """Delegator: see SubagentLifecycleCoordinator."""
        return self._subagent_lifecycle_coordinator.resolve_subagent_parent_workspace(parent_agent_id)

    def send_runtime_message_to_subagent(
        self,
        subagent_id: str,
        content: str,
        target_agents: list[str] | None = None,
    ) -> bool:
        """Delegator: see SubagentLifecycleCoordinator."""
        return self._subagent_lifecycle_coordinator.send_runtime_message_to_subagent(
            subagent_id=subagent_id,
            content=content,
            target_agents=target_agents,
        )

    def continue_subagent_from_tui(
        self,
        subagent_id: str,
        message: str,
        timeout_seconds: int | None = None,
        background: bool = True,
    ) -> bool:
        """Delegator: see SubagentLifecycleCoordinator."""
        return self._subagent_lifecycle_coordinator.continue_subagent_from_tui(
            subagent_id=subagent_id,
            message=message,
            timeout_seconds=timeout_seconds,
            background=background,
        )

    def _build_tui_continue_status_callback(
        self,
        parent_agent_id: str,
        fallback_task: str,
        fallback_timeout_seconds: int | None,
    ):
        """Delegator: see SubagentLifecycleCoordinator."""
        return self._subagent_lifecycle_coordinator.build_tui_continue_status_callback(
            parent_agent_id=parent_agent_id,
            fallback_task=fallback_task,
            fallback_timeout_seconds=fallback_timeout_seconds,
        )

    def _configure_human_input_hook_callbacks(self) -> None:
        """Delegator: see RuntimeInputDelivery."""
        self._runtime_input_delivery.configure_human_input_hook_callbacks()

    async def _maybe_interrupt_background_wait_for_agent(
        self,
        agent_id: str,
        trigger: str = "runtime_injection_available",
    ) -> bool:
        """Delegator: see RuntimeInputDelivery."""
        return await self._runtime_input_delivery.maybe_interrupt_background_wait_for_agent(
            agent_id,
            trigger=trigger,
        )

    def _share_human_input_hook_with_display(self) -> None:
        """Delegator: see RuntimeInputDelivery."""
        self._runtime_input_delivery.share_human_input_hook_with_display()

    def _share_subagent_message_callback_with_display(self) -> None:
        """Delegator: see SubagentLifecycleCoordinator."""
        self._subagent_lifecycle_coordinator.share_subagent_message_callback_with_display()

    def request_answer_now(self) -> dict[str, list[str]]:
        """Delegator: see RuntimeInputDelivery."""
        return self._runtime_input_delivery.request_answer_now()

    def _consume_pending_answer_now_injection(self, agent_id: str) -> str | None:
        """Delegator: see RuntimeInputDelivery."""
        return self._runtime_input_delivery.consume_pending_answer_now_injection(agent_id)

    def _prime_answer_now_hook_payload(self, agent_id: str) -> bool:
        """Delegator: see RuntimeInputDelivery."""
        return self._runtime_input_delivery.prime_answer_now_hook_payload(agent_id)

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
        """Normalize heterogeneous answer payloads into plain text (delegates to AnswerTextNormalizer)."""
        return AnswerTextNormalizer.coerce_answer_content_to_text(content)

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
        return self._answer_text_normalizer.normalize_workspace_paths_in_answers(answers, viewing_agent_id)

    def _normalize_workspace_paths_for_comparison(
        self,
        content: Any,
        replacement_path: str = "/workspace",
    ) -> str:
        """
        Normalize all workspace paths in content to a canonical form for equality comparison.

        Delegates to AnswerTextNormalizer.
        """
        return self._answer_text_normalizer.normalize_workspace_paths_for_comparison(content, replacement_path)

    def _flush_pending_subagent_results(self) -> None:
        """Delegator: see SubagentLifecycleCoordinator."""
        self._subagent_lifecycle_coordinator.flush_pending_subagent_results()

    async def _cleanup_active_coordination(self) -> None:
        """Force cleanup of active coordination streams and tasks on timeout.

        Thin delegator; implementation lives in
        :class:`massgen.orchestrator_collaborators.ActiveCoordinationCleanup`.
        """
        await self._active_coordination_cleanup.cleanup()

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
        """Calculate Jaccard similarity between two texts (delegates to AnswerTextNormalizer)."""
        return self._answer_text_normalizer.calculate_jaccard_similarity(text1, text2)

    def _check_answer_novelty(
        self,
        new_answer: Any,
        existing_answers: dict[str, Any],
    ) -> tuple[bool, str | None]:
        """Check if a new answer is sufficiently different from existing answers (delegates to AnswerTextNormalizer)."""
        return self._answer_text_normalizer.check_answer_novelty(new_answer, existing_answers)

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
        """Delegator: see ChangedocCoordinator."""
        return self._changedoc_coordinator.is_changedoc_enabled()

    def _gather_agent_changedocs(self) -> dict[str, str] | None:
        """Delegator: see ChangedocCoordinator."""
        return self._changedoc_coordinator.gather_agent_changedocs()

    def _is_fairness_enabled(self) -> bool:
        """Return True when fairness controls are enabled (delegates to FairnessGate)."""
        return self._fairness_gate.is_fairness_enabled()

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
        """Log fairness pre-start pause transitions (delegates to FairnessGate)."""
        self._fairness_gate.update_fairness_pause_log_state(agent_id, is_paused, pause_reason)

    def _log_fairness_answer_lead_block(
        self,
        agent_id: str,
        projected_lead: int,
        lead_cap: int,
    ) -> None:
        """Log fairness lead-cap block (delegates to FairnessGate)."""
        self._fairness_gate.log_fairness_answer_lead_block(agent_id, projected_lead, lead_cap)

    def _clear_fairness_answer_lead_block_log(self, agent_id: str) -> None:
        """Clear per-agent fairness lead-cap block log state (delegates to FairnessGate)."""
        self._fairness_gate.clear_fairness_answer_lead_block_log(agent_id)

    def _get_agent_answer_revision_count(self, agent_id: str) -> int:
        """Get total answer revisions submitted by an agent (delegates to PeerAnswerVisibilityTracker)."""
        return self._peer_answer_visibility_tracker.get_agent_answer_revision_count(agent_id)

    def _get_active_fairness_agents(self) -> list[str]:
        """Return agents currently active for fairness gating (delegates to FairnessGate)."""
        return self._fairness_gate.get_active_fairness_agents()

    def _terminal_action_wording(self) -> str:
        """Return mode-specific terminal action guidance (delegates to AnswerLimitGate)."""
        return self._answer_limit_gate.terminal_action_wording()

    def _get_answer_revision_counts(self) -> dict[str, int]:
        """Get current answer revision counts (delegates to PeerAnswerVisibilityTracker)."""
        return self._peer_answer_visibility_tracker.get_answer_revision_counts()

    def _get_current_answers_snapshot(self) -> dict[str, str]:
        """Return latest submitted answer content (delegates to PeerAnswerVisibilityTracker)."""
        return self._peer_answer_visibility_tracker.get_current_answers_snapshot()

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
        """Update seen-answer revision snapshot (delegates to PeerAnswerVisibilityTracker)."""
        self._peer_answer_visibility_tracker.sync_decomposition_answer_visibility(agent_id)

    def _mark_seen_answer_revisions(self, agent_id: str, source_agent_ids: list[str]) -> None:
        """Mark seen answer revisions (delegates to PeerAnswerVisibilityTracker)."""
        self._peer_answer_visibility_tracker.mark_seen_answer_revisions(agent_id, source_agent_ids)

    def _get_latest_answer_revision_timestamp(self, source_agent_id: str) -> float:
        """Get latest revision timestamp (delegates to PeerAnswerVisibilityTracker)."""
        return self._peer_answer_visibility_tracker.get_latest_answer_revision_timestamp(source_agent_id)

    def _get_unseen_answer_update_candidates(
        self,
        agent_id: str,
        current_answers: dict[str, str],
    ) -> list[tuple[str, str, float]]:
        """Return unseen source answer updates (delegates to PeerAnswerVisibilityTracker)."""
        return self._peer_answer_visibility_tracker.get_unseen_answer_update_candidates(
            agent_id,
            current_answers,
        )

    def _get_unseen_source_agent_ids(self, agent_id: str) -> list[str]:
        """Return unseen source agent ids (delegates to PeerAnswerVisibilityTracker)."""
        return self._peer_answer_visibility_tracker.get_unseen_source_agent_ids(agent_id)

    def _has_unseen_answer_updates(self, agent_id: str) -> bool:
        """Return True when there are unseen peer revisions (delegates to PeerAnswerVisibilityTracker)."""
        return self._peer_answer_visibility_tracker.has_unseen_answer_updates(agent_id)

    def _select_midstream_answer_updates(
        self,
        agent_id: str,
        current_answers: dict[str, str],
    ) -> tuple[dict[str, str], bool]:
        """Select mid-stream answer updates (delegates to PeerAnswerVisibilityTracker)."""
        return self._peer_answer_visibility_tracker.select_midstream_answer_updates(
            agent_id,
            current_answers,
        )

    @staticmethod
    def _extract_submitted_agent_labels(scores_payload: Any) -> set[str]:
        """Extract first-level agent labels (delegates to PeerAnswerVisibilityTracker)."""
        return PeerAnswerVisibilityTracker.extract_submitted_agent_labels(scores_payload)

    def _mark_pending_checklist_recheck_labels(
        self,
        agent_id: str,
        source_agent_ids: list[str],
    ) -> None:
        """Record injected labels for post-injection checklist recheck (delegates to PeerAnswerVisibilityTracker)."""
        self._peer_answer_visibility_tracker.mark_pending_checklist_recheck_labels(
            agent_id,
            source_agent_ids,
        )

    def _register_injected_answer_updates(self, agent_id: str, source_agent_ids: list[str]) -> None:
        """Apply post-injection state updates (delegates to PeerAnswerVisibilityTracker)."""
        self._peer_answer_visibility_tracker.register_injected_answer_updates(
            agent_id,
            source_agent_ids,
        )

    def _check_fairness_answer_lead_cap(self, agent_id: str) -> tuple[bool, str | None]:
        """Enforce max lead in answer revisions (delegates to FairnessGate)."""
        return self._fairness_gate.check_fairness_answer_lead_cap(agent_id)

    def _should_pause_agent_for_fairness(self, agent_id: str) -> tuple[bool, str | None]:
        """Return whether an agent should wait before starting (delegates to FairnessGate)."""
        return self._fairness_gate.should_pause_agent_for_fairness(agent_id)

    def _is_hard_timeout_active(self, agent_id: str) -> bool:
        """Return True when hard timeout is currently active (delegates to AnswerLimitGate)."""
        return self._answer_limit_gate.is_hard_timeout_active(agent_id)

    def _get_agent_answer_count_for_limit(self, agent_id: str) -> int:
        """Get answer count for per-agent limit enforcement (delegates to AnswerLimitGate)."""
        return self._answer_limit_gate.get_agent_answer_count_for_limit(agent_id)

    def _get_total_answer_count(self) -> int:
        """Get total number of answer revisions (delegates to AnswerLimitGate)."""
        return self._answer_limit_gate.get_total_answer_count()

    def _is_global_answer_limit_reached(self) -> bool:
        """Check whether global answer cap is reached (delegates to AnswerLimitGate)."""
        return self._answer_limit_gate.is_global_answer_limit_reached()

    def _check_answer_count_limit(self, agent_id: str) -> tuple[bool, str | None]:
        """Check answer-count limit (delegates to AnswerLimitGate)."""
        return self._answer_limit_gate.check_answer_count_limit(agent_id)

    def _is_vote_only_mode(self, agent_id: str) -> bool:
        """Check if agent must vote (delegates to AnswerLimitGate).

        PUBLIC SURFACE (tested by test_vote_only_mode.py). Preserves the
        decomposition-mode auto-stop side effect on agent_states /
        coordination_tracker.
        """
        return self._answer_limit_gate.is_vote_only_mode(agent_id)

    def _apply_decomposition_auto_stop_if_needed(self, agent_id: str) -> bool:
        """Apply decomposition auto-stop gate (delegates to AnswerLimitGate)."""
        return self._answer_limit_gate.apply_decomposition_auto_stop_if_needed(agent_id)

    def _is_waiting_for_all_answers(self, agent_id: str) -> bool:
        """Check if agent is waiting for peers to answer (delegates to AnswerLimitGate)."""
        return self._answer_limit_gate.is_waiting_for_all_answers(agent_id)

    def _is_round_evaluator_gate_enabled(self) -> bool:
        """Return whether the orchestrator should run the round_evaluator gate itself (delegates to RoundEvaluatorGateConfig)."""
        return self._round_evaluator_gate_config.is_round_evaluator_gate_enabled()

    def _get_evaluator_team_size(self) -> int:
        """Return the number of evaluator subagents in the shared child team (delegates to RoundEvaluatorGateConfig)."""
        return self._round_evaluator_gate_config.get_evaluator_team_size()

    def _validate_evaluator_personas(
        self,
        personas: Any,
    ) -> str | None:
        """Validate evaluator personas input (delegates to RoundEvaluatorGateConfig)."""
        return self._round_evaluator_gate_config.validate_evaluator_personas(personas)

    def _consume_evaluator_personas(self) -> list[dict[str, str]] | None:
        """Consume pending evaluator personas (delegates to RoundEvaluatorGateConfig)."""
        return self._round_evaluator_gate_config.consume_evaluator_personas()

    def _get_round_evaluator_latest_labels(
        self,
        answers: dict[str, str],
    ) -> tuple[str, ...]:
        """Return the latest answer labels for the current revision set (delegates to RoundEvaluatorGateConfig)."""
        return self._round_evaluator_gate_config.get_round_evaluator_latest_labels(answers)

    def _get_round_evaluator_upcoming_round(self, agent_id: str) -> int:
        """Return the next user-facing round number for programmatic tool events (delegates to RoundEvaluatorGateConfig)."""
        return self._round_evaluator_gate_config.get_round_evaluator_upcoming_round(agent_id)

    def _get_round_evaluator_display_round(self, agent_id: str) -> int:
        """Attach round-evaluator tool cards to the completed parent round they analyze (delegates to RoundEvaluatorGateConfig)."""
        return self._round_evaluator_gate_config.get_round_evaluator_display_round(agent_id)

    def _queue_round_start_context_block(self, agent_id: str, block: str) -> None:
        """Queue a context block for the next parent round (delegates to RoundStartContextQueue)."""
        self._round_start_context_queue.queue(agent_id, block)

    def _consume_round_start_context_block(self, agent_id: str) -> str | None:
        """Pop and combine queued round-start context blocks for an agent (delegates to RoundStartContextQueue)."""
        return self._round_start_context_queue.consume(agent_id)

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
        workspace_root,
        agent_id: str,
    ) -> None:
        """Delegates to SubagentToolInjector.rewrite_subagent_mcp_config_files."""
        self._subagent_tool_injector.rewrite_subagent_mcp_config_files(workspace_root, agent_id)

    def _ensure_context_md_for_round_evaluator(
        self,
        workspace_root: Any,
        parent_agent_id: str,
    ) -> None:
        """Thin delegator — see RoundEvaluatorRunner."""
        return self._round_evaluator_runner.ensure_context_md_for_round_evaluator(
            workspace_root,
            parent_agent_id,
        )

    def _build_round_evaluator_task(
        self,
        parent_agent_id: str,
        answers: dict[str, str],
    ) -> str:
        """Thin delegator — see RoundEvaluatorRunner."""
        return self._round_evaluator_runner.build_round_evaluator_task(
            parent_agent_id,
            answers,
        )

    def _get_parent_round_evaluator_delegate_targets(self) -> list[str]:
        """Thin delegator — see RoundEvaluatorRunner."""
        return self._round_evaluator_runner.get_parent_round_evaluator_delegate_targets()

    def _get_round_evaluator_context_paths(
        self,
        parent_agent_id: str,
        temp_workspace_path: str | None = None,
    ) -> list[str]:
        """Thin delegator — see RoundEvaluatorRunner."""
        return self._round_evaluator_runner.get_round_evaluator_context_paths(
            parent_agent_id,
            temp_workspace_path=temp_workspace_path,
        )

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
        """Thin delegator — see RoundEvaluatorRunner."""
        return self._round_evaluator_runner.emit_round_evaluator_spawn_event(
            phase=phase,
            agent_id=agent_id,
            tool_call_id=tool_call_id,
            round_number=round_number,
            args=args,
            result=result,
            elapsed_seconds=elapsed_seconds,
            is_error=is_error,
            status=status,
        )

    def _format_round_evaluator_result_block(
        self,
        subagent_id: str,
        result: "SubagentResult | RoundEvaluatorResult",
        auto_injected: bool = False,
    ) -> str:
        """Thin delegator — see RoundEvaluatorRunner."""
        return self._round_evaluator_runner.format_round_evaluator_result_block(
            subagent_id,
            result,
            auto_injected=auto_injected,
        )

    @staticmethod
    def _strip_absolute_workspace_paths(text: str) -> str:
        """Replace absolute workspace paths with relative basenames.

        Delegates to RoundEvaluatorRunner. Kept here so external callers
        (tests) can still use ``Orchestrator._strip_absolute_workspace_paths``
        unbound.
        """
        return RoundEvaluatorRunner._strip_absolute_workspace_paths(text)

    @staticmethod
    def _format_round_evaluator_result_block_static(
        subagent_id: str,
        evaluator_result: "RoundEvaluatorResult",
        auto_injected: bool = False,
    ) -> str:
        """Static delegator — see RoundEvaluatorRunner.

        Kept as @staticmethod on Orchestrator so unbound callers
        (``Orchestrator._format_round_evaluator_result_block_static(...)``)
        in tests continue to work.
        """
        return RoundEvaluatorRunner.format_round_evaluator_result_block_static(
            subagent_id=subagent_id,
            evaluator_result=evaluator_result,
            auto_injected=auto_injected,
        )

    @staticmethod
    def _format_round_evaluator_timeout_block_static(
        subagent_id: str,
        error_message: str,
    ) -> str:
        """Static delegator — see RoundEvaluatorRunner."""
        return RoundEvaluatorRunner.format_round_evaluator_timeout_block_static(
            subagent_id=subagent_id,
            error_message=error_message,
        )

    @staticmethod
    def extract_all_evaluator_answers(
        log_path: str,
        workspace_path: str,
    ) -> dict[str, str] | None:
        """Static delegator — see EvaluatorResultExtractor."""
        return EvaluatorResultExtractor.extract_all_evaluator_answers(
            log_path,
            workspace_path,
        )

    @staticmethod
    def extract_evaluator_workspace_paths(
        log_path: str,
    ) -> list[str]:
        """Static delegator — see EvaluatorResultExtractor."""
        return EvaluatorResultExtractor.extract_evaluator_workspace_paths(log_path)

    @staticmethod
    def format_multi_evaluator_result_block(
        all_answers: dict[str, str],
        auto_injected: bool = False,
    ) -> str:
        """Static delegator — see EvaluatorResultExtractor."""
        return EvaluatorResultExtractor.format_multi_evaluator_result_block(
            all_answers,
            auto_injected=auto_injected,
        )

    @staticmethod
    def build_task_plan_from_evaluator_verdict(
        evaluator_result: "RoundEvaluatorResult",
    ) -> list[dict]:
        """Static delegator — see EvaluatorResultExtractor."""
        return EvaluatorResultExtractor.build_task_plan_from_evaluator_verdict(
            evaluator_result,
        )

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
        """Thin delegator — see RoundEvaluatorRunner."""
        return self._round_evaluator_runner.handle_round_evaluator_gate_failure(
            parent_agent_id=parent_agent_id,
            latest_labels=latest_labels,
            display_round=display_round,
            emitter=emitter,
            elapsed_seconds=elapsed_seconds,
            failure_payload=failure_payload,
        )

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
        """Thin delegator — see RoundEvaluatorRunner."""
        return self._round_evaluator_runner.handle_round_evaluator_timeout_degraded(
            parent_agent_id=parent_agent_id,
            latest_labels=latest_labels,
            display_round=display_round,
            emitter=emitter,
            elapsed_seconds=elapsed_seconds,
            first_result=first_result,
            evaluator_result=evaluator_result,
        )

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
        """Delegator: see TraceAnalyzerRunner.format_trace_analyzer_for_memory_static.

        Kept as a @staticmethod so unbound ``Orchestrator._format_trace_analyzer_for_memory_static(...)``
        usage (see test_execution_trace_analyzer.py / test_auto_trace_analysis.py) continues to work.
        """
        return TraceAnalyzerRunner.format_trace_analyzer_for_memory_static(trace_result, round_number)

    @staticmethod
    def _strip_memory_frontmatter(content: str) -> str:
        """Delegator: see TraceAnalyzerRunner.strip_memory_frontmatter."""
        return TraceAnalyzerRunner.strip_memory_frontmatter(content)

    def _build_trace_analysis_injection_text(
        self,
        round_number: int,
        content: str,
    ) -> str | None:
        """Delegator: see TraceAnalyzerRunner."""
        return self._trace_analyzer_runner.build_trace_analysis_injection_text(round_number, content)

    def _build_trace_analysis_injection_result(
        self,
        trace_result: "SubagentResult",
        round_number: int,
        artifact_path: Path | None,
    ) -> Optional["SubagentResult"]:
        """Delegator: see TraceAnalyzerRunner."""
        return self._trace_analyzer_runner.build_trace_analysis_injection_result(
            trace_result,
            round_number,
            artifact_path,
        )

    @staticmethod
    def _get_trace_analysis_memory_filename(round_number: int) -> str:
        """Delegator: see TraceAnalyzerRunner."""
        return TraceAnalyzerRunner.get_trace_analysis_memory_filename(round_number)

    @classmethod
    def _candidate_trace_analysis_artifact_paths(
        cls,
        workspace_path: str | os.PathLike[str] | None,
        round_number: int,
    ) -> list[Path]:
        """Delegator: see TraceAnalyzerRunner."""
        return TraceAnalyzerRunner.candidate_trace_analysis_artifact_paths(workspace_path, round_number)

    @classmethod
    def _resolve_trace_analysis_artifact_path(
        cls,
        workspace_path: str | os.PathLike[str] | None,
        round_number: int,
    ) -> Path | None:
        """Delegator: see TraceAnalyzerRunner."""
        return TraceAnalyzerRunner.resolve_trace_analysis_artifact_path(workspace_path, round_number)

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
        """Delegator: see TraceAnalyzerRunner."""
        return self._trace_analyzer_runner.get_execution_trace_path_for_agent(agent_id)

    def _get_execution_trace_context_path_for_agent(
        self,
        agent_id: str,
        temp_workspace_path: str | os.PathLike[str] | None = None,
    ) -> Path | None:
        """Delegator: see TraceAnalyzerRunner."""
        return self._trace_analyzer_runner.get_execution_trace_context_path_for_agent(
            agent_id,
            temp_workspace_path=temp_workspace_path,
        )

    def _build_trace_analyzer_task(
        self,
        agent_id: str,
        round_number: int,
        trace_path: str,
    ) -> str:
        """Delegator: see TraceAnalyzerRunner."""
        return self._trace_analyzer_runner.build_trace_analyzer_task(agent_id, round_number, trace_path)

    def _write_trace_analysis_to_memory(
        self,
        agent_id: str,
        round_number: int,
        memory_block: str,
    ) -> None:
        """Delegator: see TraceAnalyzerRunner."""
        self._trace_analyzer_runner.write_trace_analysis_to_memory(agent_id, round_number, memory_block)

    def _copy_trace_analysis_artifact_to_memory(
        self,
        agent_id: str,
        round_number: int,
        source_path: Path,
    ) -> None:
        """Delegator: see TraceAnalyzerRunner."""
        self._trace_analyzer_runner.copy_trace_analysis_artifact_to_memory(
            agent_id,
            round_number,
            source_path,
        )

    async def _run_trace_analyzer(
        self,
        parent_agent_id: str,
        round_number: int,
        trace_path: Path,
    ) -> None:
        """Delegator: see TraceAnalyzerRunner."""
        await self._trace_analyzer_runner.run_trace_analyzer(
            parent_agent_id,
            round_number,
            trace_path,
        )

    async def _spawn_trace_analyzer_background(
        self,
        parent_agent_id: str,
    ) -> None:
        """Delegator: see TraceAnalyzerRunner."""
        await self._trace_analyzer_runner.spawn_trace_analyzer_background(parent_agent_id)

    # ------------------------------------------------------------------
    # Evolving evaluation criteria
    # ------------------------------------------------------------------

    def _bootstrap_evolution_criteria_from_config(self) -> None:
        """Thin delegator — see CriteriaEvolutionRunner."""
        return self._criteria_evolution_runner.bootstrap_evolution_criteria_from_config()

    def _should_evolve_criteria(self, current_answers: dict[str, str] | None = None) -> bool:
        """Thin delegator — see CriteriaEvolutionRunner."""
        return self._criteria_evolution_runner.should_evolve_criteria(current_answers=current_answers)

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
        """Thin delegator — see CriteriaEvolutionRunner."""
        return self._criteria_evolution_runner.build_criteria_evolution_proposal_task(agent_id, evolution_data)

    def _build_criteria_evolution_synthesis_task(
        self,
        proposals: list[dict[str, Any]],
        current_criteria: list[Any],
        original_task: str,
    ) -> str:
        """Thin delegator — see CriteriaEvolutionRunner."""
        return self._criteria_evolution_runner.build_criteria_evolution_synthesis_task(proposals, current_criteria, original_task)

    def _write_criteria_evolution_subagent_type_dirs(self, ws_root: Path) -> None:
        """Thin delegator — see CriteriaEvolutionRunner."""
        return self._criteria_evolution_runner.write_criteria_evolution_subagent_type_dirs(ws_root)

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
        """Thin delegator — see CriteriaEvolutionRunner."""
        return await self._criteria_evolution_runner.run_criteria_evolution_if_needed(answers)

    def _write_criteria_evolution_memory(
        self,
        evolution_number: int,
        old_criteria: list[Any],
        new_criteria: list[Any],
        summary: str | None,
    ) -> None:
        """Thin delegator — see CriteriaEvolutionRunner."""
        return self._criteria_evolution_runner.write_criteria_evolution_memory(
            evolution_number=evolution_number,
            old_criteria=old_criteria,
            new_criteria=new_criteria,
            summary=summary,
        )

    async def _run_round_evaluator_pre_round_if_needed(
        self,
        answers: dict[str, str],
        conversation_context: dict[str, Any] | None = None,
    ) -> bool | str:
        """Thin delegator — see RoundEvaluatorRunner."""
        return await self._round_evaluator_runner.run_round_evaluator_pre_round_if_needed(
            answers,
            conversation_context,
        )

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
        """Thin delegator — see :class:`RateLimitController`."""
        return self._rate_limit_controller.load_from_config()

    async def _apply_agent_startup_rate_limit(self, agent_id: str) -> None:
        """Thin delegator — see :class:`RateLimitController`."""
        await self._rate_limit_controller.apply_agent_startup_rate_limit(agent_id)

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
            # Position-bias counterbalancing: rotate candidate presentation so this
            # scoring agent's OWN answer lands last in its view, distributing the
            # primacy slot across agents (reduces first-position bias + self-preference).
            # Derived from the answering subset so it stays correct when only some
            # agents have answered. Deterministic.
            _order_seed = None
            if normalized_answers and len(normalized_answers) > 1:
                _order_seed = self.message_templates.compute_own_last_order_seed(
                    agent_id,
                    list(normalized_answers.keys()),
                    agent_mapping,
                )
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
                    order_seed=_order_seed,
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
                    order_seed=_order_seed,
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

                            # Exact-equality only: `mcp__massgen_checkpoint_standalone__checkpoint`
                            # must fall through (its server owns its own subprocess lifecycle).
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

                        # Exact-equality only — standalone server's checkpoint tool must fall through.
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
        """Check if agent has writable context paths (delegates to ContextPathWriteTracker)."""
        return self._context_path_write_tracker.has_write_context_paths(agent)

    def _enable_context_write_access(self, agent: "ChatAgent") -> None:
        """Enable write access for context paths (delegates to ContextPathWriteTracker)."""
        self._context_path_write_tracker.enable_context_write_access(agent)

    def get_context_path_writes(self) -> list[str]:
        """Get files written to context paths by the final agent (delegates to ContextPathWriteTracker)."""
        return self._context_path_write_tracker.get_context_path_writes()

    def get_context_path_writes_categorized(self) -> dict[str, list[str]]:
        """Get categorized context-path writes (delegates to ContextPathWriteTracker)."""
        return self._context_path_write_tracker.get_context_path_writes_categorized()

    def _clear_context_path_write_tracking(self) -> None:
        """Clear context path write tracking (delegates to ContextPathWriteTracker)."""
        self._context_path_write_tracker.clear_context_path_write_tracking()

    async def _yield_existing_answer_finalization(
        self,
        *,
        selected_agent_id: str,
        vote_results: dict[str, Any],
        force_workspace_snapshot: bool = False,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Delegates to :class:`FinalPresentationRunner`."""
        async for chunk in self._final_presentation_runner.yield_existing_answer_finalization(
            selected_agent_id=selected_agent_id,
            vote_results=vote_results,
            force_workspace_snapshot=force_workspace_snapshot,
        ):
            yield chunk

    async def _present_final_answer(self) -> AsyncGenerator[StreamChunk, None]:
        """Delegates to :class:`FinalPresentationRunner`."""
        async for chunk in self._final_presentation_runner.present_final_answer():
            yield chunk

    async def _handle_orchestrator_timeout(self) -> AsyncGenerator[StreamChunk, None]:
        """Delegates to :class:`FinalPresentationRunner`."""
        async for chunk in self._final_presentation_runner.handle_orchestrator_timeout():
            yield chunk

    def _determine_final_agent_from_votes(
        self,
        votes: dict[str, dict],
        agent_answers: dict[str, str],
    ) -> str:
        """Delegates to :class:`FinalPresentationRunner`."""
        return FinalPresentationRunner.determine_final_agent_from_votes(votes, agent_answers)

    async def get_final_presentation(
        self,
        selected_agent_id: str,
        vote_results: dict[str, Any],
    ) -> AsyncGenerator[StreamChunk, None]:
        """Delegates to :class:`FinalPresentationRunner`."""
        async for chunk in self._final_presentation_runner.get_final_presentation(
            selected_agent_id,
            vote_results,
        ):
            yield chunk

    async def _review_isolated_changes(
        self,
        agent: "ChatAgent",
        isolation_manager: "IsolationContextManager",
        selected_agent_id: str,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Review and apply changes from isolated write context.

        Thin delegator; implementation lives in
        :class:`massgen.orchestrator_collaborators.IsolatedChangeReviewer`.
        """
        async for chunk in self._isolated_change_reviewer.review(
            agent=agent,
            isolation_manager=isolation_manager,
            selected_agent_id=selected_agent_id,
        ):
            yield chunk

    async def post_evaluate_answer(
        self,
        selected_agent_id: str,
        final_answer: str,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Delegates to :class:`PostEvaluationRunner`."""
        async for chunk in self._post_evaluation_runner.post_evaluate_answer(
            selected_agent_id=selected_agent_id,
            final_answer=final_answer,
        ):
            yield chunk

    def handle_restart(self):
        """Delegates to :class:`PostEvaluationRunner`."""
        self._post_evaluation_runner.handle_restart()

    def _should_skip_injection_due_to_timeout(self, agent_id: str) -> bool:
        """Check if mid-stream injection should be skipped due to approaching timeout (delegates to OrchestratorTimeoutCalculator)."""
        return self._orchestrator_timeout_calculator.should_skip_injection_due_to_timeout(agent_id)

    def _resolve_final_workspace_path(self, agent_id: str | None) -> str | None:
        """Delegates to FinalResultReporter."""
        return self._final_result_reporter.resolve_final_workspace_path(agent_id)

    async def _show_workspace_modal_if_needed(self) -> None:
        """Delegates to WorkspaceModalPresenter."""
        await self._workspace_modal_presenter.show_if_needed()

    def _get_vote_results(self) -> dict[str, Any]:
        """Delegates to FinalResultReporter."""
        return self._final_result_reporter.get_vote_results()

    def _determine_final_agent_from_states(self) -> str | None:
        """Delegates to FinalResultReporter."""
        return self._final_result_reporter.determine_final_agent_from_states()

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
        # Standalone checkpoint is single-agent only; adding a second agent
        # invalidates that invariant and the registration must be stripped.
        self._init_standalone_checkpoint_tool()

    def remove_agent(self, agent_id: str) -> None:
        """Remove a sub-agent from the orchestrator."""
        if agent_id in self.agents:
            del self.agents[agent_id]
        if agent_id in self.agent_states:
            del self.agent_states[agent_id]
        # Removing back down to a single agent may now satisfy the gate.
        self._init_standalone_checkpoint_tool()

    def get_final_result(self) -> dict[str, Any] | None:
        """Delegates to FinalResultReporter."""
        return self._final_result_reporter.get_final_result()

    def get_partial_result(self) -> dict[str, Any] | None:
        """Delegates to FinalResultReporter."""
        return self._final_result_reporter.get_partial_result()

    def _ensure_final_directory_on_shutdown(
        self,
        answers: dict[str, Any],
        workspaces: dict[str, str],
    ) -> None:
        """Delegates to FinalResultReporter."""
        self._final_result_reporter.ensure_final_directory_on_shutdown(answers, workspaces)

    def get_all_agent_workspaces(self) -> dict[str, str | None]:
        """Delegates to FinalResultReporter."""
        return self._final_result_reporter.get_all_agent_workspaces()

    def get_coordination_result(self) -> dict[str, Any]:
        """Delegates to FinalResultReporter."""
        return self._final_result_reporter.get_coordination_result()

    def get_status(self) -> dict[str, Any]:
        """Delegates to FinalResultReporter."""
        return self._final_result_reporter.get_status()

    def get_agent_timeout_state(self, agent_id: str) -> dict[str, Any] | None:
        """Get timeout state for display purposes (delegates to OrchestratorTimeoutCalculator)."""
        return self._orchestrator_timeout_calculator.get_agent_timeout_state(agent_id)

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
        """Delegates to WorkspaceLifecycleManager."""
        self._workspace_lifecycle_manager.clear_agent_workspaces()

    def _archive_agent_memories(self, agent_id: str, workspace_path: Path) -> None:
        """Delegates to WorkspaceLifecycleManager."""
        self._workspace_lifecycle_manager.archive_agent_memories(agent_id, workspace_path)

    def _namespace_verification_memory_files(self, archive_path: Path, agent_id: str) -> None:
        """Delegates to WorkspaceLifecycleManager."""
        self._workspace_lifecycle_manager.namespace_verification_memory_files(archive_path, agent_id)

    def _get_previous_turns_context_paths(self) -> list[dict[str, Any]]:
        """Delegates to previous_log_restorer; see collaborator for full docs."""
        return self._previous_log_restorer.get_previous_turns_context_paths()

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
