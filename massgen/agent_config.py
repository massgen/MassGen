"""
Agent configuration for MassGen framework following input_cases_reference.md
Simplified configuration focused on the proven binary decision approach.

TODO: This file is outdated - check claude_code config and
deprecated patterns. Update to reflect current backend architecture.
"""

import copy
import logging
import warnings
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

from .evaluation_criteria_generator import EvaluationCriteriaGeneratorConfig
from .persona_generator import PersonaGeneratorConfig
from .task_decomposer import TaskDecomposerConfig

if TYPE_CHECKING:
    from .message_templates import MessageTemplates
    from .subagent.models import SubagentOrchestratorConfig


@dataclass
class StepModeConfig:
    """Configuration for step mode execution.

    Step mode runs one agent for one step (new_answer or vote), then exits.
    Prior answers/workspaces are loaded from a session directory.

    Args:
        enabled: Whether step mode is active.
        session_dir: Path to session directory with inputs/outputs.
    """

    enabled: bool = False
    session_dir: str = ""


@dataclass
class TimeoutConfig:
    """Configuration for timeout settings in MassGen.

    Args:
        orchestrator_timeout_seconds: Maximum time for orchestrator coordination (default: 1800s = 30min)
        initial_round_timeout_seconds: Soft timeout for round 0 (initial answer). After this time,
                                       a warning is injected telling the agent to submit. None = disabled.
        subsequent_round_timeout_seconds: Soft timeout for rounds 1+ (voting/refinement). After this time,
                                          a warning is injected telling the agent to submit. None = disabled.
        round_timeout_grace_seconds: Grace period after soft timeout before hard timeout kicks in.
                                     After hard timeout, non-terminal tool calls are blocked - only
                                     vote and new_answer are allowed. Default: 120 seconds.
    """

    orchestrator_timeout_seconds: int = 1800  # 30 minutes
    initial_round_timeout_seconds: int | None = None  # None = disabled
    subsequent_round_timeout_seconds: int | None = None  # None = disabled
    round_timeout_grace_seconds: int = 120  # Grace period before hard block


@dataclass
class PromptImproverConfig:
    """Configuration for pre-collab prompt improvement.

    When enabled, spawns a multi-agent consensus call before coordination
    to rewrite the user's task prompt for clarity, specificity, and ambition.
    """

    enabled: bool = False
    persist_across_turns: bool = False


@dataclass
class CoordinationConfig:
    """Configuration for coordination behavior in MassGen.

    Args:
        enable_planning_mode: If True, agents plan without executing actions during coordination.
                             Only the winning agent executes actions during final presentation.
                             If False, agents execute actions during coordination (default behavior).
        planning_mode_instruction: Custom instruction to add when planning mode is enabled.
        max_orchestration_restarts: Maximum number of times orchestration can be restarted after
                                   post-evaluation determines the answer is insufficient.
                                   For example, max_orchestration_restarts=2 allows 3 total attempts
                                   (initial + 2 restarts). Default is 0 (no restarts).
        enable_agent_task_planning: If True, agents receive task planning MCP tools for managing
                                    their own task lists with dependencies. This enables agents
                                    to break down complex work, track progress, and coordinate
                                    based on dependencies.
        max_tasks_per_plan: Maximum number of tasks allowed in an agent's task plan.
        broadcast: Broadcast mode for agent-to-agent communication.
                  - False: Broadcasting disabled (default)
                  - "agents": Agent-to-agent communication only
                  - "human": Agents can ask agents + human (human gets prompted)
        broadcast_sensitivity: How frequently agents should use ask_others() for collaboration.
                             - "low": Only for critical decisions/when blocked
                             - "medium": For significant decisions and design choices (default)
                             - "high": Frequently - whenever considering options or proposing approaches
        response_depth: Controls test-time compute scaling for shadow agent responses.
                       Determines how thorough/complex suggested solutions should be.
                       - "low": Quick, simple responses; minimal solutions (e.g., basic HTML/CSS)
                       - "medium": Balanced effort; standard solutions (default)
                       - "high": Thorough responses; sophisticated solutions (e.g., React + Next.js)
        broadcast_timeout: Maximum time to wait for broadcast responses (seconds).
        broadcast_wait_by_default: If True, ask_others() blocks until responses collected (blocking mode).
                                   If False, ask_others() returns immediately for polling (polling mode).
        max_broadcasts_per_agent: Maximum number of active broadcasts per agent.
        task_planning_filesystem_mode: If True, task planning MCP writes tasks to tasks/ directory
                                       in agent workspace for transparency and cross-agent visibility.
        enable_memory_filesystem_mode: If True, enables filesystem-based memory system with two-tier
                                       hierarchy (short-term and long-term). Agents create memories
                                       by writing Markdown files to memory/ directories. Short-term
                                       memories auto-inject into all agents' system prompts. Long-term
                                       memories are read on-demand. Inspired by Letta's context hierarchy.
        learning_capture_mode: Controls when evolving-skill + memory capture is produced.
            - "round": Existing behavior. Capture can be produced in coordination rounds.
            - "final_only": Keep changedoc behavior, but defer evolving-skill + memory
                            production to the final presenter stage. Coordination rounds
                            remain read-focused.
            - "verification_and_final_only" (default): Round-time verification replay memo
                            only; full consolidation remains presenter/final-time.
        disable_final_only_round_capture_fallback: If True, final_only mode remains read-focused
                                                  even when skip_final_presentation is enabled.
                                                  This disables the default fallback that re-enables
                                                  round-time learning capture when there is no presenter stage.
        compression_target_ratio: Target ratio for reactive compression when context limit is exceeded.
                                 Value between 0 and 1, where 0.2 means preserve 20% of messages and
                                 summarize the remaining 80%. Lower values = more aggressive compression.
        use_skills: If True, enables skills system using openskills. Agents can invoke skills
                   via bash commands (openskills read <skill-name>). Requires command line
                   execution to be enabled.
        massgen_skills: List of MassGen built-in skills to enable. Available skills:
                       - "file_search": File search skill (no dir needed)
                       When workspace/ is needed for file operations, it is created automatically.
        skills_directory: Path to the skills directory. Default is .agent/skills which is where
                         openskills installs skills. This directory is scanned for available skills.
        load_previous_session_skills: If True, scan .massgen/massgen_logs/ for SKILL.md files from
                                     previous sessions and include them as available skills.
        persona_generator: Configuration for automatic persona generation to increase agent diversity.
                          When enabled, an LLM generates diverse system message personas for each agent.
        evaluation_criteria_generator: Configuration for task-specific evaluation criteria generation.
                                      When enabled, generates GEPA-style criteria tailored to the task.
        pre_collab_voting_threshold: Optional voting threshold override for pre-collaboration
                                    subagent runs (persona generation, evaluation criteria generation,
                                    and decomposition). When unset, pre-collab runs use the main
                                    orchestrator voting_threshold.
        enable_subagents: If True, agents receive subagent MCP tools for spawning independent
                         agent instances with fresh context and isolated workspaces. Useful for
                         parallel task execution and avoiding context pollution.
        subagent_default_timeout: Default timeout in seconds for subagent execution (default 300).
        subagent_min_timeout: Minimum allowed timeout in seconds (default 60). Prevents too-short timeouts.
        subagent_max_timeout: Maximum allowed timeout in seconds (default 600). Prevents runaway subagents.
        subagent_max_concurrent: Maximum number of concurrent subagents an agent can spawn (default 3).
        subagent_round_timeouts: Optional per-round timeout settings for subagents.
        subagent_runtime_mode: Runtime boundary mode for subagent execution.
                              - "isolated" (default): require isolated runtime semantics
                              - "inherited": run in parent runtime boundary
        subagent_runtime_fallback_mode: Optional fallback when isolated runtime prerequisites are unavailable.
                                       - None (default): strict isolation (fail if unavailable)
                                       - "inherited": explicit opt-in fallback to shared runtime
        subagent_host_launch_prefix: Optional command prefix used to launch isolated subagents
                                    when running inside a containerized parent runtime.
                                    Example: ["host-launch", "--exec"]
        subagent_orchestrator: Configuration for subagent orchestrator mode. When enabled, subagents
                              use a full Orchestrator with multiple agents. This enables multi-agent coordination within
                              subagent execution.
        background_subagents: Configuration for background subagent execution. When enabled, agents can spawn
                        subagents with background=True to run in the background while continuing work.
                        Results are automatically injected when subagents complete.
                        - enabled: bool (default True) - Whether to allow background subagent execution
                        - injection_strategy: str (default "tool_result") - How to inject results:
                          - "tool_result": Append result to next tool call output
                          - "user_message": Inject as separate user message
        use_two_tier_workspace: DEPRECATED - Use write_mode instead.
                               If True, agent workspaces are structured with scratch/ and deliverable/
                               directories. Superseded by write_mode which provides git worktree
                               isolation with in-worktree scratch space.
        write_mode: Controls how agent file writes are isolated during coordination.
                   - "auto": Automatically detect (worktree for git repos, shadow for non-git)
                   - "worktree": Use git worktrees for isolation (requires git repo)
                   - "isolated": Use shadow repos for full isolation
                   - "legacy": Use direct writes (no isolation, current behavior)
                   - None: Disabled (default, same as "legacy")
        drift_conflict_policy: How to handle target-file drift when applying isolated
                              presenter changes back to source context.
                              - "skip": Skip drifted files, apply remaining files (default)
                              - "prefer_presenter": Apply presenter changes even on drift
                              - "fail": Block apply if any drift is detected
    """

    enable_planning_mode: bool = False
    planning_mode_instruction: str = (
        "During coordination, describe what you would do without actually executing actions. Only provide concrete implementation details without calling external APIs or tools."
    )
    plan_depth: str | None = None  # "dynamic" | "shallow" | "medium" | "deep" - Task planning mode depth
    plan_target_steps: int | None = None  # Optional explicit task-count target (None = dynamic)
    plan_target_chunks: int | None = None  # Optional explicit chunk-count target (None = dynamic)
    max_orchestration_restarts: int = 0
    enable_agent_task_planning: bool = False
    max_tasks_per_plan: int = 10
    broadcast: Any = False  # False | "agents" | "human"
    broadcast_sensitivity: str = "medium"  # "low" | "medium" | "high" - Used in BroadcastCommunicationSection system prompts
    response_depth: str = "medium"  # "low" | "medium" | "high" - Controls test-time compute scaling for shadow agents
    broadcast_timeout: int = 90   # Max seconds to wait for ALL broadcast responses (was 300)
    shadow_timeout: int = 90      # Max seconds for a single shadow agent LLM call
    broadcast_wait_by_default: bool = True
    max_broadcasts_per_agent: int = 10
    task_planning_filesystem_mode: bool = False
    enable_memory_filesystem_mode: bool = False
    learning_capture_mode: str = "verification_and_final_only"  # "round" | "verification_and_final_only" | "final_only"
    disable_final_only_round_capture_fallback: bool = False
    compression_target_ratio: float = 0.20  # Preserve 20% of messages on context overflow
    use_skills: bool = False
    massgen_skills: list[str] = field(default_factory=list)
    skills_directory: str = ".agent/skills"
    load_previous_session_skills: bool = False
    persona_generator: PersonaGeneratorConfig = field(default_factory=PersonaGeneratorConfig)
    evaluation_criteria_generator: EvaluationCriteriaGeneratorConfig = field(
        default_factory=EvaluationCriteriaGeneratorConfig,
    )
    prompt_improver: PromptImproverConfig = field(
        default_factory=PromptImproverConfig,
    )
    pre_collab_voting_threshold: int | None = None
    enable_subagents: bool = False
    subagent_default_timeout: int = 300
    subagent_min_timeout: int = 60  # Minimum 1 minute
    subagent_max_timeout: int = 600  # Maximum 10 minutes
    subagent_max_concurrent: int = 3
    subagent_round_timeouts: dict[str, Any] | None = None
    subagent_runtime_mode: str = "isolated"  # "isolated" | "inherited"
    subagent_runtime_fallback_mode: str | None = None  # None | "inherited"
    subagent_host_launch_prefix: list[str] | None = None  # Optional command prefix for containerized isolated launch
    subagent_orchestrator: Optional["SubagentOrchestratorConfig"] = None
    # Background subagent execution configuration
    background_subagents: dict[str, Any] | None = None  # {enabled: bool, injection_strategy: str}
    use_two_tier_workspace: bool = False  # Enable scratch/deliverable structure + git versioning
    task_decomposer: TaskDecomposerConfig = field(default_factory=TaskDecomposerConfig)
    write_mode: str = "auto"  # "auto" | "worktree" | "isolated" | "legacy"
    enable_changedoc: bool = True  # Write changedoc.md decision journal during coordination
    drift_conflict_policy: str = "skip"  # "skip" | "prefer_presenter" | "fail"
    subagent_types: list[str] | None = None  # None = use DEFAULT_SUBAGENT_TYPES (excludes novelty)
    round_evaluator_before_checklist: bool = False  # Round 2+ must run round_evaluator before checklist submit
    orchestrator_managed_round_evaluator: bool = False  # Gate orchestrator-owned round_evaluator launch; default prompt-guidance only
    round_evaluator_skip_synthesis: bool = False  # Skip synthesis stage; pass all raw critiques to parent directly
    round_evaluator_refine: bool = False  # Allow evaluator agents to iterate (multi-round with voting)
    round_evaluator_transformation_pressure: str = "balanced"  # "gentle" | "balanced" | "aggressive"
    enable_quality_rethink_on_iteration: bool = False  # Auto-inject quality_rethinking spawn task on iteration 2+
    enable_novelty_on_iteration: bool = False  # Auto-inject novelty/quality spawn task on iteration 2+
    enable_execution_trace_analyzer: bool = False  # Run execution_trace_analyzer in parallel with round_evaluator
    auto_trace_analysis: bool = False  # Auto-spawn background trace analyzer at round 2+ start
    evolving_criteria: bool = False  # Evolve evaluation criteria between rounds based on score trends
    evolving_criteria_score_threshold: int = 8  # Min score to flag a criterion as "too easy"
    evolving_criteria_max_evolutions: int = 2  # Hard cap on total criteria evolutions per session
    evolving_criteria_min_high_score_count: int = 2  # Min number of criteria at threshold to trigger evolution
    evolving_criteria_timeout: int = 300  # Seconds for the full evolution gate (proposals + synthesis)
    enable_evaluator_personas: bool = False  # Expose set_evaluator_personas tool for agent-driven evaluator diversity
    novelty_injection: str = "none"  # "none" | "gentle" | "moderate" | "aggressive"
    improvements: dict[str, Any] = field(default_factory=dict)  # Quality gate config for draft_approach
    checklist_criteria_preset: str | None = None  # "persona" | "decomposition" | "evaluation" | "prompt" | "analysis" | "planning" | "spec" | "round_evaluator"
    checklist_criteria_inline: list[dict[str, str]] | None = None  # [{text, category: primary|standard|stretch, anti_patterns?, verify_by?}]
    resume_from_log: dict[str, Any] | None = None  # {log_path: str, round: int}
    # Checkpoint coordination fields
    checkpoint_enabled: bool = False  # Enable checkpoint coordination mode
    checkpoint_mode: str = "conversation"  # "conversation" | "task"
    checkpoint_guidance: str = ""  # Appended to main agent system prompt
    checkpoint_gated_patterns: list[str] = field(default_factory=list)  # fnmatch patterns for gated tools
    web_review: bool = False  # Enable change review modal in WebUI (requires --web)
    fast_iteration_mode: bool = False  # Streamline post-candidate phases to submit faster and iterate across rounds

    def __post_init__(self):
        """Validate configuration after initialization."""
        self._validate_broadcast_config()
        self._validate_timeout_config()
        self._validate_subagent_runtime_config()
        self._validate_drift_conflict_policy()
        self._validate_novelty_injection()
        self._validate_round_evaluator_transformation_pressure()
        self._validate_learning_capture_mode()
        self._validate_pre_collab_voting_threshold()
        self._validate_improvements()

    def _validate_timeout_config(self):
        """Validate subagent timeout configuration."""
        logger = logging.getLogger(__name__)

        if self.subagent_min_timeout <= 0:
            raise ValueError(f"subagent_min_timeout must be positive, got {self.subagent_min_timeout}")

        if self.subagent_max_timeout <= 0:
            raise ValueError(f"subagent_max_timeout must be positive, got {self.subagent_max_timeout}")

        if self.subagent_min_timeout > self.subagent_max_timeout:
            raise ValueError(
                f"subagent_min_timeout ({self.subagent_min_timeout}) must be <= " f"subagent_max_timeout ({self.subagent_max_timeout})",
            )

        if not (self.subagent_min_timeout <= self.subagent_default_timeout <= self.subagent_max_timeout):
            logger.warning(
                f"subagent_default_timeout ({self.subagent_default_timeout}) is outside the " f"range [{self.subagent_min_timeout}, {self.subagent_max_timeout}]. " f"It will be clamped at runtime.",
            )

    def _validate_broadcast_config(self):
        """Validate broadcast configuration settings."""
        logger = logging.getLogger(__name__)

        if self.broadcast:
            # Validate broadcast mode
            if self.broadcast not in [False, "agents", "human"]:
                raise ValueError(f"Invalid broadcast mode: {self.broadcast}. Must be False, 'agents', or 'human'")

            # Validate sensitivity
            if self.broadcast_sensitivity not in ["low", "medium", "high"]:
                raise ValueError(f"Invalid broadcast_sensitivity: {self.broadcast_sensitivity}. Must be 'low', 'medium', or 'high'")

            # Validate response_depth
            if self.response_depth not in ["low", "medium", "high"]:
                raise ValueError(f"Invalid response_depth: {self.response_depth}. Must be 'low', 'medium', or 'high'")

            # Warn if both task planning and high-sensitivity broadcasts enabled
            if self.enable_agent_task_planning and self.broadcast_sensitivity == "high":
                logger.warning(
                    "Both task planning and high-sensitivity broadcasts are enabled. " "This may create extensive coordination overhead. " "Consider using 'medium' or 'low' broadcast sensitivity.",
                )

            # Warn if timeout is very low
            if self.broadcast_timeout < 30:
                logger.warning(f"Broadcast timeout is very low ({self.broadcast_timeout}s). Agents may not have enough time to respond.")

            # Warn if shadow_timeout exceeds broadcast_timeout (shadow would never be cut by broadcast guard)
            if self.shadow_timeout > self.broadcast_timeout:
                logger.warning(
                    f"shadow_timeout ({self.shadow_timeout}s) > broadcast_timeout ({self.broadcast_timeout}s). "
                    "The broadcast_timeout guard may fire before individual shadow timeouts. "
                    "Consider setting shadow_timeout <= broadcast_timeout.",
                )

    def _validate_drift_conflict_policy(self):
        """Validate drift conflict policy for isolated change apply."""
        valid_policies = {"skip", "prefer_presenter", "fail"}
        if self.drift_conflict_policy not in valid_policies:
            raise ValueError(
                "Invalid drift_conflict_policy: " f"{self.drift_conflict_policy}. " f"Must be one of: {sorted(valid_policies)}",
            )

    def _validate_novelty_injection(self):
        """Validate novelty_injection setting."""
        valid_values = {"none", "gentle", "moderate", "aggressive"}
        if self.novelty_injection not in valid_values:
            raise ValueError(
                f"Invalid novelty_injection: '{self.novelty_injection}'. " f"Must be one of: {sorted(valid_values)}",
            )

    def _validate_round_evaluator_transformation_pressure(self):
        """Validate round_evaluator_transformation_pressure setting."""
        valid_values = {"gentle", "balanced", "aggressive"}
        if self.round_evaluator_transformation_pressure not in valid_values:
            raise ValueError(
                "Invalid round_evaluator_transformation_pressure: " f"'{self.round_evaluator_transformation_pressure}'. " f"Must be one of: {sorted(valid_values)}",
            )

    def _validate_learning_capture_mode(self):
        """Validate learning_capture_mode setting."""
        valid_values = {"round", "verification_and_final_only", "final_only"}
        if self.learning_capture_mode not in valid_values:
            raise ValueError(
                f"Invalid learning_capture_mode: '{self.learning_capture_mode}'. " f"Must be one of: {sorted(valid_values)}",
            )

    def _validate_pre_collab_voting_threshold(self):
        """Validate optional pre-collab checklist threshold override."""
        threshold = self.pre_collab_voting_threshold
        if threshold is None:
            return
        if isinstance(threshold, bool) or not isinstance(threshold, int) or threshold < 1:
            raise ValueError(
                "pre_collab_voting_threshold must be a positive integer or None",
            )

    def _validate_improvements(self):
        """Validate improvements quality-gate configuration."""
        if self.improvements is None:
            self.improvements = {}
            return

        if not isinstance(self.improvements, dict):
            raise ValueError(
                "improvements must be a dictionary",
            )

        for key in ("min_transformative", "min_structural", "min_non_incremental"):
            if key not in self.improvements:
                continue
            value = self.improvements[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(
                    f"improvements.{key} must be a non-negative integer",
                )

    def _validate_subagent_runtime_config(self):
        """Validate subagent runtime mode/fallback configuration."""
        valid_modes = {"isolated", "inherited", "delegated"}
        if self.subagent_runtime_mode not in valid_modes:
            raise ValueError(
                f"Invalid subagent_runtime_mode: '{self.subagent_runtime_mode}'. " f"Must be one of: {sorted(valid_modes)}",
            )

        valid_fallback_modes = {None, "inherited"}
        if self.subagent_runtime_fallback_mode not in valid_fallback_modes:
            raise ValueError(
                "Invalid subagent_runtime_fallback_mode: " f"'{self.subagent_runtime_fallback_mode}'. Must be one of: [None, 'inherited']",
            )

        if self.subagent_runtime_mode != "isolated" and self.subagent_runtime_fallback_mode is not None:
            raise ValueError(
                "subagent_runtime_fallback_mode is only valid when subagent_runtime_mode is 'isolated'",
            )

        if self.subagent_host_launch_prefix is not None:
            if not isinstance(self.subagent_host_launch_prefix, list) or any(not isinstance(item, str) or not item.strip() for item in self.subagent_host_launch_prefix):
                raise ValueError(
                    "subagent_host_launch_prefix must be a list of non-empty strings when set",
                )


@dataclass
class AgentConfig:
    """Configuration for MassGen agents using the proven binary decision framework.

    This configuration implements the simplified approach from input_cases_reference.md
    that eliminates perfectionism loops through clear binary decisions.

    Args:
        backend_params: Settings passed directly to LLM backend (includes tool enablement)
        message_templates: Custom message templates (None=default)
        agent_id: Optional agent identifier for this configuration
        custom_system_instruction: Additional system instruction prepended to evaluation message
        timeout_config: Timeout and resource limit configuration
        coordination_config: Coordination behavior configuration (e.g., planning mode)
        skip_coordination_rounds: Debug/test mode - skip voting rounds and go straight to final presentation (default: False)
        voting_sensitivity: Controls how critical agents are when voting ("lenient", "balanced", "strict")
        max_new_answers_per_agent: Maximum number of new answers each agent can provide (None = unlimited)
        max_new_answers_global: Maximum number of new answers across all agents (None = unlimited)
        checklist_require_gap_report: In checklist_gated mode, require a markdown gap report before verdict (default: True)
        answer_novelty_requirement: How different new answers must be from existing ones ("lenient", "balanced", "strict")
        fairness_enabled: Enable fairness controls across all coordination modes (default: True)
        fairness_lead_cap_answers: Maximum allowed lead in answer revisions over slowest active peer
        max_midstream_injections_per_round: Maximum unseen source updates injected per agent per round
        defer_peer_updates_until_restart: Queue unseen peer answer updates until the agent
            restarts instead of injecting them mid-stream (default: False)
        allow_midstream_peer_updates_before_checklist_submit: In checklist_gated mode, allow
            peer updates mid-stream before the first accepted submit_checklist for the current
            answer. ``None`` uses the orchestrator default policy.
        max_checklist_calls_per_round: Maximum submit_checklist calls per answer before blocking
            (default 1). After a new_answer verdict, the agent must implement and submit
            new_answer rather than calling submit_checklist again.
        checklist_first_answer: Allow submit_checklist before the first answer is submitted
            (default False). When False, checklist evaluation begins from round 2 — agents
            build and submit their first answer directly without checklist gating.
    """

    # Core backend configuration (includes tool enablement)
    backend_params: dict[str, Any] = field(default_factory=dict)

    # Framework configuration
    message_templates: Optional["MessageTemplates"] = None

    # Voting behavior configuration
    voting_sensitivity: str = "lenient"
    voting_threshold: int | None = None  # Numeric threshold for ROI-style voting (e.g., 15 = 15% improvement required)
    max_new_answers_per_agent: int | None = None
    max_new_answers_global: int | None = None
    checklist_require_gap_report: bool = True
    gap_report_mode: str = "changedoc"  # "changedoc" | "separate" | "none"
    answer_novelty_requirement: str = "lenient"
    fairness_enabled: bool = True
    fairness_lead_cap_answers: int = 2
    max_midstream_injections_per_round: int = 2
    defer_peer_updates_until_restart: bool = False
    allow_midstream_peer_updates_before_checklist_submit: bool | None = None
    max_checklist_calls_per_round: int = 1
    checklist_first_answer: bool = False

    # Agent customization
    agent_id: str | None = None
    subagent_agents: list[dict[str, Any]] = field(default_factory=list)
    _custom_system_instruction: str | None = field(default=None, init=False)

    # Timeout and resource limits
    timeout_config: TimeoutConfig = field(default_factory=TimeoutConfig)

    # Coordination behavior configuration
    coordination_config: CoordinationConfig = field(default_factory=CoordinationConfig)

    # Debug/test mode - skip coordination rounds and go straight to final presentation
    skip_coordination_rounds: bool = False

    # Skip voting enforcement (used by TUI single-agent mode with refinement OFF)
    # When True, agent doesn't need to vote and can go straight to new_answer → final answer
    skip_voting: bool = False

    # Skip final presentation phase (used by TUI when refinement is OFF)
    # When True, uses the existing answer directly without an additional LLM call
    skip_final_presentation: bool = False

    # Final answer strategy after coordination completes.
    # None preserves legacy behavior:
    # - winner_reuse when skip_final_presentation=True
    # - winner_present otherwise
    # Explicit values:
    # - winner_reuse: use the selected answer directly when presentation can be skipped
    # - winner_present: selected winner performs a final presentation pass
    # - synthesize: selected presenter combines the strongest parts of all answers
    final_answer_strategy: str | None = None

    # Disable injection of other agents' answers (used by TUI multi-agent refinement OFF)
    # When True, agents work independently without seeing each other's work mid-stream
    disable_injection: bool = False

    # Defer voting until all agents have answered (used by TUI multi-agent refinement OFF)
    # When True, voting only starts after all agents submit their answers
    # Prevents wasteful restarts when agents vote before everyone has answered
    defer_voting_until_all_answered: bool = False

    # Coordination mode: "voting" (default) or "decomposition"
    # In decomposition mode, each agent works on an assigned subtask and calls stop when done.
    # A presenter agent synthesizes the final output.
    coordination_mode: str = "voting"
    # Agent ID that presents the final synthesized output (decomposition mode)
    presenter_agent: str | None = None

    # Debug mode for restart feature - override final answer on attempt 1 only
    debug_final_answer: str | None = None

    # NLIP (Natural Language Interaction Protocol) Configuration
    enable_nlip: bool = False
    nlip_config: dict[str, Any] | None = None
    _nlip_router: Any = field(default=None, init=False, repr=False)

    @property
    def custom_system_instruction(self) -> str | None:
        """
        DEPRECATED: Use backend-specific system prompt parameters instead.

        For Claude Code: use append_system_prompt or system_prompt in backend_params
        For other backends: use their respective system prompt parameters
        """
        if self._custom_system_instruction is not None:
            warnings.warn(
                "custom_system_instruction is deprecated. Use backend-specific " "system prompt parameters instead (e.g., append_system_prompt for Claude Code)",
                DeprecationWarning,
                stacklevel=2,
            )
        return self._custom_system_instruction

    @custom_system_instruction.setter
    def custom_system_instruction(self, value: str | None) -> None:
        if value is not None:
            warnings.warn(
                "custom_system_instruction is deprecated. Use backend-specific " "system prompt parameters instead (e.g., append_system_prompt for Claude Code)",
                DeprecationWarning,
                stacklevel=2,
            )
        self._custom_system_instruction = value

    def init_nlip_router(
        self,
        tool_manager: Any | None = None,
        mcp_executor: Any | None = None,
    ) -> None:
        """Initialize NLIP router if NLIP is enabled.

        Args:
            tool_manager: Optional tool manager instance to use with router
            mcp_executor: Optional callable to execute MCP tools directly
        """
        if self.enable_nlip and self._nlip_router is None:
            from .nlip.router import NLIPRouter

            self._nlip_router = NLIPRouter(
                tool_manager=tool_manager,
                mcp_executor=mcp_executor,
                enable_nlip=True,
                config=self.nlip_config or {},
            )

    @property
    def nlip_router(self) -> Any | None:
        """Get NLIP router instance."""
        return self._nlip_router

    @classmethod
    def create_chatcompletion_config(
        cls,
        model: str = "gpt-oss-120b",
        enable_web_search: bool = False,
        enable_code_interpreter: bool = False,
        **kwargs,
    ) -> "AgentConfig":
        """Create ChatCompletion configuration following proven patterns.

        Args:
            model: Opensource Model Name
            enable_web_search: Enable web search via Responses API
            enable_code_interpreter: Enable code execution for computational tasks
            **kwargs: Additional backend parameters

        Examples:
            # Basic configuration
            config = AgentConfig.create_chatcompletion_config("gpt-oss-120b")

            # Research task with web search
            config = AgentConfig.create_chatcompletion_config("gpt-oss-120b", enable_web_search=True)

            # Computational task with code execution
            config = AgentConfig.create_chatcompletion_config("gpt-oss-120b", enable_code_interpreter=True)
        """
        backend_params = {"model": model, **kwargs}

        # Add tool enablement to backend_params
        if enable_web_search:
            backend_params["enable_web_search"] = True
        if enable_code_interpreter:
            backend_params["enable_code_interpreter"] = True

        return cls(backend_params=backend_params)

    @classmethod
    def create_openai_config(
        cls,
        model: str = "gpt-4o-mini",
        enable_web_search: bool = False,
        enable_code_interpreter: bool = False,
        **kwargs,
    ) -> "AgentConfig":
        """Create OpenAI configuration following proven patterns.

        Args:
            model: OpenAI model name
            enable_web_search: Enable web search via Responses API
            enable_code_interpreter: Enable code execution for computational tasks
            **kwargs: Additional backend parameters

        Examples:
            # Basic configuration
            config = AgentConfig.create_openai_config("gpt-4o-mini")

            # Research task with web search
            config = AgentConfig.create_openai_config("gpt-4o", enable_web_search=True)

            # Computational task with code execution
            config = AgentConfig.create_openai_config("gpt-4o", enable_code_interpreter=True)
        """
        backend_params = {"model": model, **kwargs}

        # Add tool enablement to backend_params
        if enable_web_search:
            backend_params["enable_web_search"] = True
        if enable_code_interpreter:
            backend_params["enable_code_interpreter"] = True

        return cls(backend_params=backend_params)

    @classmethod
    def create_claude_config(
        cls,
        model: str = "claude-3-sonnet-20240229",
        enable_web_search: bool = False,
        enable_code_execution: bool = False,
        **kwargs,
    ) -> "AgentConfig":
        """Create Anthropic Claude configuration.

        Args:
            model: Claude model name
            enable_web_search: Enable builtin web search tool
            enable_code_execution: Enable builtin code execution tool
            **kwargs: Additional backend parameters
        """
        backend_params = {"model": model, **kwargs}

        if enable_web_search:
            backend_params["enable_web_search"] = True

        if enable_code_execution:
            backend_params["enable_code_execution"] = True

        return cls(backend_params=backend_params)

    @classmethod
    def create_grok_config(
        cls,
        model: str = "grok-2-1212",
        enable_web_search: bool = False,
        enable_x_search: bool = False,
        enable_code_execution: bool = False,
        **kwargs,
    ) -> "AgentConfig":
        """Create xAI Grok configuration.

        Args:
            model: Grok model name
            enable_web_search: Enable xAI web search
            enable_x_search: Enable xAI X search
            enable_code_execution: Enable xAI code execution
            **kwargs: Additional backend parameters
        """
        backend_params = {"model": model, **kwargs}

        # Add tool enablement to backend_params
        if enable_web_search:
            backend_params["enable_web_search"] = True
        if enable_x_search:
            backend_params["enable_x_search"] = True
        if enable_code_execution:
            backend_params["enable_code_execution"] = True

        return cls(backend_params=backend_params)

    @classmethod
    def create_lmstudio_config(
        cls,
        model: str = "gpt-4o-mini",
        enable_web_search: bool = False,
        **kwargs,
    ) -> "AgentConfig":
        """Create LM Studio configuration (OpenAI-compatible local server).

        Args:
            model: Local model name exposed by LM Studio
            enable_web_search: No builtin web search; kept for interface parity
            **kwargs: Additional backend parameters (e.g., base_url, api_key)
        """
        backend_params = {"model": model, **kwargs}
        if enable_web_search:
            backend_params["enable_web_search"] = True
        return cls(backend_params=backend_params)

    @classmethod
    def create_vllm_config(cls, model: str | None = None, **kwargs) -> "AgentConfig":
        """Create vLLM configuration (OpenAI-compatible local server)."""
        backend_params = {"model": model, **kwargs}
        if model is None:
            raise ValueError("Model is required for vLLM configuration")

        return cls(backend_params=backend_params)

    @classmethod
    def create_sglang_config(cls, model: str | None = None, **kwargs) -> "AgentConfig":
        """Create SGLang configuration (OpenAI-compatible local server)."""
        backend_params = {"model": model, **kwargs}
        if model is None:
            raise ValueError("Model is required for SGLang configuration")

        return cls(backend_params=backend_params)

    @classmethod
    def create_gemini_config(
        cls,
        model: str = "gemini-2.5-flash",
        enable_web_search: bool = False,
        enable_code_execution: bool = False,
        **kwargs,
    ) -> "AgentConfig":
        """Create Google Gemini configuration.

        Args:
            model: Gemini model name
            enable_web_search: Enable Google Search retrieval tool
            enable_code_execution: Enable code execution tool
            **kwargs: Additional backend parameters
        """
        backend_params = {"model": model, **kwargs}

        # Add tool enablement to backend_params
        if enable_web_search:
            backend_params["enable_web_search"] = True
        if enable_code_execution:
            backend_params["enable_code_execution"] = True

        return cls(backend_params=backend_params)

    @classmethod
    def create_zai_config(
        cls,
        model: str = "glm-4.5",
        base_url: str = "https://api.z.ai/api/paas/v4/",
        **kwargs,
    ) -> "AgentConfig":
        """Create ZAI configuration (OpenAI Chat Completions compatible).

        Args:
            model: ZAI model name (e.g., "glm-4.5")
            base_url: ZAI OpenAI-compatible API base URL
            **kwargs: Additional backend parameters (e.g., temperature, top_p)
        """
        backend_params = {"model": model, "base_url": base_url, **kwargs}

        return cls(backend_params=backend_params)

    @classmethod
    def create_azure_openai_config(
        cls,
        deployment_name: str = "gpt-4",
        endpoint: str | None = None,
        api_key: str | None = None,
        api_version: str = "2024-02-15-preview",
        **kwargs,
    ) -> "AgentConfig":
        """Create Azure OpenAI configuration.

        Args:
            deployment_name: Azure OpenAI deployment name (e.g., "gpt-4", "gpt-35-turbo")
            endpoint: Azure OpenAI endpoint URL (optional, uses AZURE_OPENAI_ENDPOINT env var)
            api_key: Azure OpenAI API key (optional, uses AZURE_OPENAI_API_KEY env var)
            api_version: Azure OpenAI API version (default: 2024-02-15-preview)
            **kwargs: Additional backend parameters (e.g., temperature, max_tokens)

        Examples:
            Basic configuration using environment variables::

                config = AgentConfig.create_azure_openai_config("gpt-4")

            Custom endpoint and API key::

                config = AgentConfig.create_azure_openai_config(
                    deployment_name="gpt-4-turbo",
                    endpoint="https://your-resource.openai.azure.com/",
                    api_key="your-api-key"
                )
        """
        backend_params = {
            "type": "azure_openai",
            "model": deployment_name,  # For Azure OpenAI, model is the deployment name
            "api_version": api_version,
            **kwargs,
        }

        # Add Azure-specific parameters if provided
        if endpoint:
            backend_params["base_url"] = endpoint
        if api_key:
            backend_params["api_key"] = api_key

        return cls(backend_params=backend_params)

    @classmethod
    def create_claude_code_config(
        cls,
        model: str = "claude-sonnet-4-20250514",
        system_prompt: str | None = None,
        allowed_tools: list | None = None,  # Legacy support
        disallowed_tools: list | None = None,  # Preferred approach
        reasoning: dict | None = None,
        cwd: str | None = None,
        **kwargs,
    ) -> "AgentConfig":
        """Create Claude Code Stream configuration using claude-code-sdk.

        This backend provides native integration with ALL Claude Code built-in tools
        by default, with security enforced through disallowed_tools. This gives maximum
        power while maintaining safety.

        Args:
            model: Claude model name (default: claude-sonnet-4-20250514)
            system_prompt: Custom system prompt for the agent
            allowed_tools: [LEGACY] List of allowed tools (use disallowed_tools instead)
            disallowed_tools: List of dangerous operations to block
                            (default: ["Bash(rm*)", "Bash(sudo*)", "Bash(su*)", "Bash(chmod*)", "Bash(chown*)"])
            reasoning: Reasoning configuration dict. Preferred keys:
                - type: "adaptive" (default), "enabled", or "disabled"
                - effort: "low", "medium", "high" (default), or "max"
                - budget_tokens: int (only for type="enabled")
            cwd: Current working directory for file operations
            **kwargs: Additional backend parameters

        Examples:
            Maximum power configuration (recommended)::

                config = AgentConfig.create_claude_code_config()

            Custom reasoning config::

                config = AgentConfig.create_claude_code_config(
                    reasoning={"type": "adaptive", "effort": "max"}
                )

            Custom security restrictions::

                config = AgentConfig.create_claude_code_config(
                    disallowed_tools=["Bash(rm*)", "Bash(sudo*)", "WebSearch"]
                )

            Development task with custom directory::

                config = AgentConfig.create_claude_code_config(
                    cwd="/path/to/project",
                    system_prompt="You are an expert developer assistant."
                )
        """
        backend_params = {"model": model, **kwargs}

        # Claude Code Stream specific parameters
        if system_prompt:
            backend_params["system_prompt"] = system_prompt
        if allowed_tools:
            # Legacy support - warn that disallowed_tools is preferred
            backend_params["allowed_tools"] = allowed_tools
        if disallowed_tools:
            backend_params["disallowed_tools"] = disallowed_tools
        if reasoning:
            backend_params["reasoning"] = reasoning
        if cwd:
            backend_params["cwd"] = cwd

        return cls(backend_params=backend_params)

    # =============================================================================
    # AGENT CUSTOMIZATION
    # =============================================================================

    def with_custom_instruction(self, instruction: str) -> "AgentConfig":
        """Create a copy with custom system instruction."""
        import copy

        new_config = copy.deepcopy(self)
        # Set private attribute directly to avoid deprecation warning
        new_config._custom_system_instruction = instruction
        return new_config

    def with_agent_id(self, agent_id: str) -> "AgentConfig":
        """Create a copy with specified agent ID."""
        import copy

        new_config = copy.deepcopy(self)
        new_config.agent_id = agent_id
        return new_config

    # =============================================================================
    # PROVEN PATTERN CONFIGURATIONS
    # =============================================================================

    @classmethod
    def for_research_task(cls, model: str = "gpt-4o", backend: str = "openai") -> "AgentConfig":
        """Create configuration optimized for research tasks.

        Based on econometrics test success patterns:
        - Enables web search for literature review
        - Uses proven model defaults
        """
        if backend == "openai":
            return cls.create_openai_config(model, enable_web_search=True)
        elif backend == "grok":
            return cls.create_grok_config(model, enable_web_search=True)
        elif backend == "claude":
            return cls.create_claude_config(model, enable_web_search=True)
        elif backend == "gemini":
            return cls.create_gemini_config(model, enable_web_search=True)
        elif backend == "claude_code":
            # Maximum power research config - all tools available
            return cls.create_claude_code_config(model)
        else:
            raise ValueError(f"Research configuration not available for backend: {backend}")

    @classmethod
    def for_computational_task(cls, model: str = "gpt-4o", backend: str = "openai") -> "AgentConfig":
        """Create configuration optimized for computational tasks.

        Based on Tower of Hanoi test success patterns:
        - Enables code execution for calculations
        - Uses proven model defaults
        """
        if backend == "openai":
            return cls.create_openai_config(model, enable_code_interpreter=True)
        elif backend == "grok":
            return cls.create_grok_config(model, enable_code_execution=True)
        elif backend == "claude":
            return cls.create_claude_config(model, enable_code_execution=True)
        elif backend == "gemini":
            return cls.create_gemini_config(model, enable_code_execution=True)
        elif backend == "claude_code":
            # Maximum power computational config - all tools available
            return cls.create_claude_code_config(model)
        else:
            raise ValueError(f"Computational configuration not available for backend: {backend}")

    @classmethod
    def for_analytical_task(cls, model: str = "gpt-4o-mini", backend: str = "openai") -> "AgentConfig":
        """Create configuration optimized for analytical tasks.

        Based on general reasoning test patterns:
        - No special tools needed
        - Uses efficient model defaults
        """
        if backend == "openai":
            return cls.create_openai_config(model)
        elif backend == "claude":
            return cls.create_claude_config(model)
        elif backend == "grok":
            return cls.create_grok_config(model)
        elif backend == "gemini":
            return cls.create_gemini_config(model)
        elif backend == "claude_code":
            # Maximum power analytical config - all tools available
            return cls.create_claude_code_config(model)
        else:
            raise ValueError(f"Analytical configuration not available for backend: {backend}")

    @classmethod
    def for_expert_domain(
        cls,
        domain: str,
        expertise_level: str = "expert",
        model: str = "gpt-4o",
        backend: str = "openai",
    ) -> "AgentConfig":
        """Create configuration for domain expertise.

        Args:
            domain: Domain of expertise (e.g., "econometrics", "computer science")
            expertise_level: Level of expertise ("expert", "specialist", "researcher")
            model: Model to use
            backend: Backend provider
        """
        instruction = f"You are a {expertise_level} in {domain}. Apply your deep domain knowledge and methodological expertise when evaluating answers and providing solutions."

        if backend == "openai":
            config = cls.create_openai_config(model, enable_web_search=True)
        elif backend == "grok":
            config = cls.create_grok_config(model, enable_web_search=True)
        elif backend == "gemini":
            config = cls.create_gemini_config(model, enable_web_search=True)
        else:
            raise ValueError(f"Domain expert configuration not available for backend: {backend}")

        # Set private attribute directly to avoid deprecation warning
        config._custom_system_instruction = instruction
        return config

    # =============================================================================
    # CONVERSATION BUILDING
    # =============================================================================

    def build_conversation(
        self,
        task: str,
        agent_summaries: dict[str, str] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Build conversation using the proven MassGen approach.

        Returns complete conversation configuration ready for backend.
        Automatically determines Case 1 vs Case 2 based on agent_summaries.
        """
        from .message_templates import get_templates

        templates = self.message_templates or get_templates()

        # Derive valid agent IDs from agent summaries
        # Sort for consistent anonymous mapping with coordination_tracker
        valid_agent_ids = sorted(agent_summaries.keys()) if agent_summaries else None

        # Build base conversation
        conversation = templates.build_initial_conversation(task=task, agent_summaries=agent_summaries, valid_agent_ids=valid_agent_ids)

        # Add custom system instruction if provided
        # Access private attribute to avoid deprecation warning
        if self._custom_system_instruction:
            base_system = conversation["system_message"]
            conversation["system_message"] = f"{self._custom_system_instruction}\n\n{base_system}"

        # Add backend configuration
        conversation.update(
            {
                "backend_params": self.get_backend_params(),
                "session_id": session_id,
                "agent_id": self.agent_id,
            },
        )

        return conversation

    def add_enforcement_message(self, conversation_messages: list) -> list:
        """Add enforcement message to conversation (Case 3 handling).

        Args:
            conversation_messages: Existing conversation messages

        Returns:
            Updated conversation messages with enforcement
        """
        from .message_templates import get_templates

        templates = self.message_templates or get_templates()
        return templates.add_enforcement_message(conversation_messages)

    def continue_conversation(
        self,
        existing_messages: list,
        additional_message: Any = None,
        additional_message_role: str = "user",
        enforce_tools: bool = False,
    ) -> dict[str, Any]:
        """Continue an existing conversation (Cases 3 & 4).

        Args:
            existing_messages: Previous conversation messages
            additional_message: Additional message (str or dict for tool results)
            additional_message_role: Role for additional message ("user", "tool", "assistant")
            enforce_tools: Whether to add tool enforcement message

        Returns:
            Updated conversation configuration
        """
        messages = existing_messages.copy()

        # Add additional message if provided
        if additional_message is not None:
            if isinstance(additional_message, dict):
                # Full message object provided
                messages.append(additional_message)
            else:
                # String content provided
                messages.append(
                    {
                        "role": additional_message_role,
                        "content": str(additional_message),
                    },
                )

        # Add enforcement if requested (Case 3)
        if enforce_tools:
            messages = self.add_enforcement_message(messages)

        # Build conversation with continued messages
        from .message_templates import get_templates

        templates = self.message_templates or get_templates()

        return {
            "messages": messages,
            "tools": templates.get_standard_tools(),  # Same tools as initial
            "backend_params": self.get_backend_params(),
            "session_id": None,  # Maintain existing session
            "agent_id": self.agent_id,
        }

    def handle_case3_enforcement(self, existing_messages: list) -> dict[str, Any]:
        """Handle Case 3: Non-workflow response requiring enforcement.

        Args:
            existing_messages: Messages from agent that didn't use tools

        Returns:
            Conversation with enforcement message added
        """
        return self.continue_conversation(existing_messages=existing_messages, enforce_tools=True)

    def add_tool_result(self, existing_messages: list, tool_call_id: str, result: str) -> dict[str, Any]:
        """Add tool result to conversation.

        Args:
            existing_messages: Previous conversation messages
            tool_call_id: ID of the tool call this responds to
            result: Tool execution result (success or error)

        Returns:
            Conversation with tool result added
        """
        tool_message = {"role": "tool", "tool_call_id": tool_call_id, "content": result}

        return self.continue_conversation(existing_messages=existing_messages, additional_message=tool_message)

    def handle_case4_error_recovery(self, existing_messages: list, clarification: str | None = None) -> dict[str, Any]:
        """Handle Case 4: Error recovery after tool failure.

        Args:
            existing_messages: Messages including tool error response
            clarification: Optional clarification message

        Returns:
            Conversation ready for retry
        """
        return self.continue_conversation(
            existing_messages=existing_messages,
            additional_message=clarification,
            additional_message_role="user",
            enforce_tools=False,  # Agent should retry naturally
        )

    def get_backend_params(self) -> dict[str, Any]:
        """Get backend parameters (already includes tool enablement)."""
        return self.backend_params.copy()

    # =============================================================================
    # SERIALIZATION
    # =============================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "backend_params": self.backend_params,
            "agent_id": self.agent_id,
            "subagent_agents": copy.deepcopy(self.subagent_agents),
            # Access private attribute to avoid deprecation warning
            "custom_system_instruction": self._custom_system_instruction,
            "voting_sensitivity": self.voting_sensitivity,
            "voting_threshold": self.voting_threshold,
            "max_new_answers_per_agent": self.max_new_answers_per_agent,
            "max_new_answers_global": self.max_new_answers_global,
            "checklist_require_gap_report": self.checklist_require_gap_report,
            "answer_novelty_requirement": self.answer_novelty_requirement,
            "fairness_enabled": self.fairness_enabled,
            "fairness_lead_cap_answers": self.fairness_lead_cap_answers,
            "max_midstream_injections_per_round": self.max_midstream_injections_per_round,
            "defer_peer_updates_until_restart": self.defer_peer_updates_until_restart,
            "allow_midstream_peer_updates_before_checklist_submit": self.allow_midstream_peer_updates_before_checklist_submit,
            "max_checklist_calls_per_round": self.max_checklist_calls_per_round,
            "checklist_first_answer": self.checklist_first_answer,
            "timeout_config": {
                "orchestrator_timeout_seconds": self.timeout_config.orchestrator_timeout_seconds,
                "initial_round_timeout_seconds": self.timeout_config.initial_round_timeout_seconds,
                "subsequent_round_timeout_seconds": self.timeout_config.subsequent_round_timeout_seconds,
                "round_timeout_grace_seconds": self.timeout_config.round_timeout_grace_seconds,
            },
        }

        # Handle coordination_config serialization
        result["coordination_config"] = {
            "enable_planning_mode": self.coordination_config.enable_planning_mode,
            "planning_mode_instruction": self.coordination_config.planning_mode_instruction,
            "max_orchestration_restarts": self.coordination_config.max_orchestration_restarts,
            "drift_conflict_policy": self.coordination_config.drift_conflict_policy,
            "round_evaluator_transformation_pressure": self.coordination_config.round_evaluator_transformation_pressure,
            "checkpoint_enabled": self.coordination_config.checkpoint_enabled,
            "checkpoint_mode": self.coordination_config.checkpoint_mode,
            "checkpoint_guidance": self.coordination_config.checkpoint_guidance,
            "checkpoint_gated_patterns": self.coordination_config.checkpoint_gated_patterns,
            "web_review": self.coordination_config.web_review,
            "fast_iteration_mode": self.coordination_config.fast_iteration_mode,
        }

        # Handle debug fields
        result["debug_final_answer"] = self.debug_final_answer

        # Handle message_templates serialization
        if self.message_templates is not None:
            try:
                if hasattr(self.message_templates, "_template_overrides"):
                    overrides = self.message_templates._template_overrides
                    if all(not callable(v) for v in overrides.values()):
                        result["message_templates"] = overrides
                    else:
                        result["message_templates"] = "<contains_callable_functions>"
                else:
                    result["message_templates"] = "<custom_message_templates>"
            except (AttributeError, TypeError):
                result["message_templates"] = "<non_serializable>"

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentConfig":
        """Create from dictionary (for deserialization)."""
        # Extract basic fields
        backend_params = data.get("backend_params", {})
        agent_id = data.get("agent_id")
        subagent_agents = data.get("subagent_agents", [])
        custom_system_instruction = data.get("custom_system_instruction")
        voting_sensitivity = data.get("voting_sensitivity", "lenient")
        voting_threshold = data.get("voting_threshold")
        max_new_answers_per_agent = data.get("max_new_answers_per_agent")
        max_new_answers_global = data.get("max_new_answers_global")
        checklist_require_gap_report = data.get("checklist_require_gap_report", True)
        answer_novelty_requirement = data.get("answer_novelty_requirement", "lenient")
        fairness_enabled = data.get("fairness_enabled", True)
        fairness_lead_cap_answers = data.get("fairness_lead_cap_answers", 2)
        max_midstream_injections_per_round = data.get("max_midstream_injections_per_round", 2)
        defer_peer_updates_until_restart = data.get("defer_peer_updates_until_restart", False)
        allow_midstream_peer_updates_before_checklist_submit = data.get(
            "allow_midstream_peer_updates_before_checklist_submit",
        )
        max_checklist_calls_per_round = data.get("max_checklist_calls_per_round", 1)
        checklist_first_answer = data.get("checklist_first_answer", False)

        # Handle timeout_config
        timeout_config = TimeoutConfig()
        timeout_data = data.get("timeout_config", {})
        if timeout_data:
            timeout_config = TimeoutConfig(**timeout_data)

        # Handle coordination_config
        coordination_config = CoordinationConfig()
        coordination_data = data.get("coordination_config", {})
        if coordination_data:
            coordination_config = CoordinationConfig(**coordination_data)

        # Handle debug fields
        debug_final_answer = data.get("debug_final_answer")

        # Handle message_templates
        message_templates = None
        template_data = data.get("message_templates")
        if isinstance(template_data, dict):
            from .message_templates import MessageTemplates

            message_templates = MessageTemplates(**template_data)

        config = cls(
            backend_params=backend_params,
            message_templates=message_templates,
            agent_id=agent_id,
            subagent_agents=copy.deepcopy(subagent_agents),
            voting_sensitivity=voting_sensitivity,
            voting_threshold=voting_threshold,
            max_new_answers_per_agent=max_new_answers_per_agent,
            max_new_answers_global=max_new_answers_global,
            checklist_require_gap_report=checklist_require_gap_report,
            answer_novelty_requirement=answer_novelty_requirement,
            fairness_enabled=fairness_enabled,
            fairness_lead_cap_answers=fairness_lead_cap_answers,
            max_midstream_injections_per_round=max_midstream_injections_per_round,
            defer_peer_updates_until_restart=defer_peer_updates_until_restart,
            allow_midstream_peer_updates_before_checklist_submit=allow_midstream_peer_updates_before_checklist_submit,
            max_checklist_calls_per_round=max_checklist_calls_per_round,
            checklist_first_answer=checklist_first_answer,
            timeout_config=timeout_config,
            coordination_config=coordination_config,
        )
        config.debug_final_answer = debug_final_answer

        # Set custom_system_instruction separately to avoid deprecation warning
        if custom_system_instruction is not None:
            config._custom_system_instruction = custom_system_instruction

        return config


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def create_research_config(model: str = "gpt-4o", backend: str = "openai") -> AgentConfig:
    """Create configuration for research tasks (web search enabled)."""
    return AgentConfig.for_research_task(model, backend)


def create_computational_config(model: str = "gpt-4o", backend: str = "openai") -> AgentConfig:
    """Create configuration for computational tasks (code execution enabled)."""
    return AgentConfig.for_computational_task(model, backend)


def create_analytical_config(model: str = "gpt-4o-mini", backend: str = "openai") -> AgentConfig:
    """Create configuration for analytical tasks (no special tools)."""
    return AgentConfig.for_analytical_task(model, backend)
