"""System message builder for MassGen orchestration.

This module provides the SystemMessageBuilder class which centralizes all system
message construction logic for different orchestration phases (coordination,
presentation, and post-evaluation).

This was extracted from orchestrator.py to improve separation of concerns and
reduce coupling between orchestration logic and prompt construction.
"""

import re
from pathlib import Path
from typing import Any

from loguru import logger

from massgen.system_prompt_sections import (
    AgentIdentitySection,
    BroadcastCommunicationSection,
    CodeBasedToolsSection,
    CommandExecutionSection,
    CoreBehaviorsSection,
    DecompositionSection,
    EvaluationSection,
    EvolvingSkillsSection,
    FastModeGuidanceSection,
    FileSearchSection,
    FilesystemBestPracticesSection,
    FilesystemOperationsSection,
    GPT5GuidanceSection,
    GrokGuidanceSection,
    MainAgentCheckpointSection,
    MemorySection,
    MultimodalToolsSection,
    NoveltyPressureSection,
    OutputFirstVerificationSection,
    PermissionGuardrailSection,
    PlanningModeSection,
    PostEvaluationSection,
    ProjectInstructionsSection,
    SkillsSection,
    StandaloneCheckpointSection,
    SubagentSection,
    SystemPromptBuilder,
    TaskContextSection,
    TaskPlanningSection,
    WorkspaceStructureSection,
)


class SystemMessageBuilder:
    """Builds system messages for different orchestration phases.

    This class centralizes all system message construction logic and consolidates
    duplicated code across the three main phases:
    - Coordination: Complex multi-agent collaboration with skills, memory, evaluation
    - Presentation: Final answer presentation with media generation capabilities
    - Post-evaluation: Answer verification and quality checking

    Args:
        config: Orchestrator configuration
        message_templates: MessageTemplates instance for presentation logic
        agents: Dictionary of agent_id -> ChatAgent for memory scanning
    """

    def __init__(
        self,
        config,  # CoordinationConfig type
        message_templates,  # MessageTemplates type
        agents: dict[str, Any],  # Dict[str, ChatAgent]
        snapshot_storage: str | None = None,
        session_id: str | None = None,
        agent_temporary_workspace: str | None = None,
    ):
        """Initialize the system message builder.

        Args:
            config: Orchestrator coordination configuration
            message_templates: MessageTemplates instance
            agents: Dictionary of agents for memory scanning
            snapshot_storage: Path to snapshot storage directory (for archived memories)
            session_id: Session ID (for archived memories)
            agent_temporary_workspace: Path to temp workspace directory (for current agent memories)
        """
        self.config = config
        self.message_templates = message_templates
        self.agents = agents
        self.snapshot_storage = snapshot_storage
        self.session_id = session_id
        self.agent_temporary_workspace = agent_temporary_workspace

    @property
    def _changedoc_enabled(self) -> bool:
        """Return True when changedoc decision journal is enabled."""
        coord = getattr(self.config, "coordination_config", None)
        return bool(coord and getattr(coord, "enable_changedoc", True))

    @property
    def _learning_capture_mode(self) -> str:
        """Return configured learning capture mode."""
        coord = getattr(self.config, "coordination_config", None)
        return getattr(coord, "learning_capture_mode", "round")

    @property
    def _round_learning_capture_enabled(self) -> bool:
        """Return True when round-time learning capture should be enabled.

        In final_only mode, if final presentation is skipped (refinement-off flow),
        we must still enable round-time capture so there is a place to write
        evolving skills and memory.
        """
        if self._learning_capture_mode == "round":
            return True
        if self._learning_capture_mode == "final_only":
            coord = getattr(self.config, "coordination_config", None)
            disable_fallback = getattr(
                coord,
                "disable_final_only_round_capture_fallback",
                False,
            )
            if disable_fallback is True:
                return False
            if not getattr(self.config, "skip_final_presentation", False):
                return False
            if getattr(self.config, "skip_voting", False):
                return True
            return getattr(self.config, "final_answer_strategy", None) not in {"winner_present", "synthesize"}
        return False

    @property
    def _round_verification_capture_enabled(self) -> bool:
        """Return True when round-time verification replay capture should be enabled."""
        if self._round_learning_capture_enabled:
            return True
        return self._learning_capture_mode == "verification_and_final_only"

    @staticmethod
    def _filter_skills_by_enabled_names(
        all_skills: list[dict[str, Any]],
        enabled_skill_names: list[str] | None,
    ) -> list[dict[str, Any]]:
        """Filter discovered skills using an optional runtime allowlist.

        Args:
            all_skills: All discovered skills from scan_skills().
            enabled_skill_names: Optional list of enabled skill names. If None,
                no filtering is applied and all discovered skills are returned.

        Returns:
            Filtered list preserving original order.
        """
        if enabled_skill_names is None:
            return all_skills

        enabled = {(name or "").strip().lower() for name in enabled_skill_names}
        enabled = {name for name in enabled if name}
        if not enabled:
            return []

        filtered: list[dict[str, Any]] = []
        for skill in all_skills:
            skill_name = str(skill.get("name", "")).strip().lower()
            if skill_name in enabled:
                filtered.append(skill)
        return filtered

    def _discover_specialized_subagents(self, allowed_types: list[str] | None = None):
        """Discover specialized subagent types from disk (cached per builder instance)."""
        cache_key = tuple(sorted(allowed_types)) if allowed_types is not None else None
        if not hasattr(self, "_specialized_subagents_cache"):
            self._specialized_subagents_cache = {}
        if cache_key not in self._specialized_subagents_cache:
            from massgen.subagent.type_scanner import scan_subagent_types

            result = scan_subagent_types(allowed_types=allowed_types)
            self._specialized_subagents_cache[cache_key] = result
            if result:
                logger.info(
                    f"[SystemMessageBuilder] Discovered {len(result)} " f"specialized subagent types: {[t.name for t in result]}",
                )
        return self._specialized_subagents_cache[cache_key]

    def build_coordination_message(
        self,
        agent,  # ChatAgent
        agent_id: str,
        answers: dict[str, str] | None,
        planning_mode_enabled: bool,
        use_skills: bool,
        enable_memory: bool,
        enable_task_planning: bool,
        previous_turns: list[dict[str, Any]],
        human_qa_history: list[dict[str, str]] | None = None,
        vote_only: bool = False,
        agent_mapping: dict[str, str] | None = None,
        voting_sensitivity_override: str | None = None,
        voting_threshold: int | None = None,
        checklist_require_gap_report: bool = True,
        gap_report_mode: str = "changedoc",
        answers_used: int = 0,
        answer_cap: int | None = None,
        coordination_mode: str = "voting",
        agent_subtask: str | None = None,
        worktree_paths: dict[str, str] | None = None,
        branch_name: str | None = None,
        other_branches: dict[str, str] | None = None,
        branch_diff_summaries: dict[str, str] | None = None,
        novelty_pressure_data: dict[str, Any] | None = None,
        custom_checklist_items: list[str] | None = None,
        item_categories: dict[str, str] | None = None,
        item_verify_by: dict[str, str] | None = None,
        item_anti_patterns: dict[str, list[str]] | None = None,
        item_score_anchors: dict[str, dict[str, str]] | None = None,
        builder_enabled: bool = True,
        regression_guard_enabled: bool = False,
        essential_files_active: bool = False,
    ) -> str:
        """Build system message for coordination phase.

        This method assembles the system prompt using priority-based sections with
        XML structure, ensuring critical instructions (skills, memory) appear early.

        Args:
            agent: The agent instance
            agent_id: Agent identifier
            answers: Dict of current answers from agents
            planning_mode_enabled: Whether planning mode is active
            use_skills: Whether to include skills section
            enable_memory: Whether to include memory section
            enable_task_planning: Whether to include task planning guidance
            previous_turns: List of previous turn data for filesystem context
            human_qa_history: List of human Q&A pairs from broadcast channel (human mode only)
            vote_only: If True, agent has reached max answers and can only vote
            agent_mapping: Mapping from real agent ID to anonymous ID (e.g., agent_a -> agent1).
                          Pass from coordination_tracker.get_reverse_agent_mapping() for
                          global consistency with vote tool and injections.
            voting_sensitivity_override: Per-agent voting sensitivity override. If provided,
                                        takes precedence over the orchestrator-level setting.
            coordination_mode: "voting" (default) or "decomposition"
            agent_subtask: The agent's assigned subtask (decomposition mode)
            worktree_paths: Dict of worktree_path -> original_path for worktree-based workspaces
            branch_name: This agent's current git branch name (for display in system prompt)
            other_branches: Dict mapping anonymous ID to branch name (e.g. {"agent1": "massgen/abc123"})
            branch_diff_summaries: Dict mapping anonymous ID to diff summary string
                                   (e.g. {"agent1": "3 files (+45/-12)\n  M src/auth.py | ..."})

        Returns:
            Complete system prompt string with XML structure
        """
        builder = SystemPromptBuilder()

        # PRIORITY 1 (CRITICAL): Agent Identity - WHO they are
        agent_system_message = agent.get_configurable_system_message()
        # Use empty string if None to avoid showing "None" in prompt
        if agent_system_message is None:
            agent_system_message = ""
        builder.add_section(AgentIdentitySection(agent_system_message))

        # PRIORITY 1 (CRITICAL): Core Behaviors - HOW to act
        builder.add_section(CoreBehaviorsSection())

        # PRIORITY 2 (HIGH): Permission guardrails — only when the permission engine
        # is ACTIVE for this agent (enabled block + chokepoint-capable backend). The
        # policy is channel-based: authority comes only from this system prompt.
        from massgen.permissions.activation import guardrail_prompt_active

        if guardrail_prompt_active(agent.backend):
            _perms = agent.backend.config.get("permissions") or {}
            _role = _perms.get("role") if isinstance(_perms, dict) else None
            builder.add_section(PermissionGuardrailSection(role=_role))
            logger.info(f"[SystemMessageBuilder] Added permission guardrail section for {agent_id} (role={_role})")

        # PRIORITY 4: File Persistence Guidance (solution persistence + tool preambles)
        # Added for models that tend to output file contents in answers instead of using file tools
        # GPT-5.x: Based on OpenAI's prompting guides
        # Grok: Observed behavior of embedding HTML in answers instead of writing to files
        model_name = agent.backend.config.get("model", "").lower()
        if model_name.startswith("gpt-5") or model_name.startswith("grok"):
            builder.add_section(GPT5GuidanceSection())
            logger.info(f"[SystemMessageBuilder] Added GPT-5 guidance section for {agent_id} (model: {model_name})")
        # Grok-specific: Prevent HTML-escaping of file content (known Grok 4.1 issue with SVG/XML/HTML)
        if model_name.startswith("grok"):
            builder.add_section(GrokGuidanceSection())
            logger.info(f"[SystemMessageBuilder] Added Grok file encoding guidance for {agent_id} (model: {model_name})")

        # PRIORITY 1 (HIGH): Output-First Verification - verify outcomes, not implementations
        is_decomposition = coordination_mode == "decomposition"
        builder.add_section(
            OutputFirstVerificationSection(
                decomposition_mode=is_decomposition,
                fast_iteration_mode=getattr(
                    getattr(self.config, "coordination_config", None),
                    "fast_iteration_mode",
                    False,
                ),
            ),
        )

        # PRIORITY 2 (HIGH): Fast-mode guidance — initial prompt shaping for the
        # --fast preset and its orthogonal speed knobs. Only added when at least
        # one knob is active so we don't bloat normal-mode prompts.
        self._maybe_add_fast_mode_section(builder, agent)
        enable_subagents = bool(getattr(getattr(self.config, "coordination_config", None), "enable_subagents", False))
        # Check if agent-spawnable subagent types exist (None = defaults, [] = none)
        _subagent_types_cfg = getattr(
            getattr(self.config, "coordination_config", None),
            "subagent_types",
            None,
        )
        _has_agent_spawnable_types = _subagent_types_cfg is None or bool(_subagent_types_cfg)

        # PRIORITY 1 (CRITICAL): MassGen Coordination - vote/new_answer or decomposition primitives
        changedoc_enabled = self._changedoc_enabled
        if coordination_mode == "decomposition":
            decomp_sensitivity = voting_sensitivity_override or self.message_templates._voting_sensitivity
            builder.add_section(
                DecompositionSection(
                    subtask=agent_subtask,
                    voting_threshold=voting_threshold,
                    voting_sensitivity=decomp_sensitivity,
                    answers_used=answers_used,
                    answer_cap=answer_cap,
                    checklist_require_gap_report=checklist_require_gap_report,
                    gap_report_mode=gap_report_mode,
                    has_changedoc=changedoc_enabled,
                    custom_checklist_items=custom_checklist_items,
                    item_categories=item_categories,
                    item_verify_by=item_verify_by,
                    item_anti_patterns=item_anti_patterns,
                    item_score_anchors=item_score_anchors,
                    fast_iteration_mode=getattr(
                        getattr(self.config, "coordination_config", None),
                        "fast_iteration_mode",
                        False,
                    ),
                ),
            )
        else:
            # Use per-agent override if provided, otherwise fall back to orchestrator default
            voting_sensitivity = voting_sensitivity_override or self.message_templates._voting_sensitivity
            answer_novelty_requirement = self.message_templates._answer_novelty_requirement
            round_number = len(previous_turns) + 1 if previous_turns else 1

            improvements_cfg = dict(
                getattr(
                    getattr(self.config, "coordination_config", None),
                    "improvements",
                    {},
                )
                or {},
            )
            builder.add_section(
                EvaluationSection(
                    voting_sensitivity=voting_sensitivity,
                    answer_novelty_requirement=answer_novelty_requirement,
                    vote_only=vote_only,
                    round_number=round_number,
                    voting_threshold=voting_threshold,
                    checklist_require_gap_report=checklist_require_gap_report,
                    gap_report_mode=gap_report_mode,
                    answers_used=answers_used,
                    answer_cap=answer_cap,
                    has_changedoc=changedoc_enabled,
                    custom_checklist_items=custom_checklist_items,
                    item_categories=item_categories,
                    item_verify_by=item_verify_by,
                    item_anti_patterns=item_anti_patterns,
                    item_score_anchors=item_score_anchors,
                    has_existing_answers=bool(answers) or answers_used > 0,
                    builder_enabled=builder_enabled,
                    regression_guard_enabled=regression_guard_enabled,
                    improvements_cfg=improvements_cfg,
                    round_evaluator_before_checklist=getattr(
                        getattr(self.config, "coordination_config", None),
                        "round_evaluator_before_checklist",
                        False,
                    ),
                    orchestrator_managed_round_evaluator=getattr(
                        getattr(self.config, "coordination_config", None),
                        "orchestrator_managed_round_evaluator",
                        False,
                    ),
                    round_evaluator_transformation_pressure=getattr(
                        getattr(self.config, "coordination_config", None),
                        "round_evaluator_transformation_pressure",
                        "balanced",
                    ),
                    specialized_subagents_available=bool(enable_subagents) and _has_agent_spawnable_types,
                    evaluator_available=bool(enable_subagents)
                    and "evaluator" in ({t.lower() for t in _subagent_types_cfg} if _subagent_types_cfg is not None else {"evaluator", "explorer", "researcher", "critic"}),
                    enable_evaluator_personas=getattr(
                        getattr(self.config, "coordination_config", None),
                        "enable_evaluator_personas",
                        False,
                    ),
                    auto_trace_analysis=getattr(
                        getattr(self.config, "coordination_config", None),
                        "auto_trace_analysis",
                        False,
                    ),
                    fast_iteration_mode=getattr(
                        getattr(self.config, "coordination_config", None),
                        "fast_iteration_mode",
                        False,
                    ),
                    criteria_mode=getattr(
                        getattr(self.config, "coordination_config", None),
                        "criteria_mode",
                        "static",
                    ),
                ),
            )

        # PRIORITY 10 (MEDIUM): Novelty Pressure (conditional)
        if novelty_pressure_data is not None:
            novelty_injection = getattr(
                self.config.coordination_config,
                "novelty_injection",
                "none",
            )
            if novelty_injection != "none":
                builder.add_section(
                    NoveltyPressureSection(
                        novelty_level=novelty_injection,
                        consecutive_incremental_rounds=novelty_pressure_data.get("consecutive", 0),
                        restart_count=novelty_pressure_data.get("restart_count", 0),
                    ),
                )

        # PRIORITY 5 (HIGH): Skills - Must be visible early
        if use_skills:
            from massgen.filesystem_manager.skills_manager import scan_skills

            # Scan all available skills
            skills_dir = Path(self.config.coordination_config.skills_directory)

            # Check if we should load previous session skills
            logs_dir = None
            load_prev = getattr(self.config.coordination_config, "load_previous_session_skills", False)
            logger.info(f"[SystemMessageBuilder] load_previous_session_skills = {load_prev}")
            if load_prev:
                logs_dir = Path(".massgen/massgen_logs")
                logger.info(f"[SystemMessageBuilder] Will scan logs_dir: {logs_dir}")

            all_skills = scan_skills(skills_dir, logs_dir=logs_dir)
            enabled_skill_names = getattr(self.config.coordination_config, "enabled_skill_names", None)
            all_skills = self._filter_skills_by_enabled_names(all_skills, enabled_skill_names)

            # Log what we found
            builtin_count = len([s for s in all_skills if s["location"] == "builtin"])
            project_count = len([s for s in all_skills if s["location"] == "project"])
            user_count = len([s for s in all_skills if s["location"] == "user"])
            previous_count = len([s for s in all_skills if s["location"] == "previous_session"])
            logger.info(
                f"[SystemMessageBuilder] Scanned skills: {builtin_count} builtin, " f"{project_count} project, {user_count} user, {previous_count} previous_session",
            )
            if enabled_skill_names is not None:
                logger.info(
                    f"[SystemMessageBuilder] Runtime skill filter active: {len(all_skills)} enabled",
                )

            # Log details for each skill
            for skill in all_skills:
                name = skill.get("name", "unknown")
                location = skill.get("location", "unknown")
                source_path = skill.get("source_path", "")
                if source_path:
                    logger.info(f"[SystemMessageBuilder] Skill: {name} ({location}) - {source_path}")
                else:
                    logger.info(f"[SystemMessageBuilder] Skill: {name} ({location})")

            # Add skills section with all skills (both project and builtin)
            # Builtin skills are now treated the same as project skills - invoke with openskills read
            builder.add_section(SkillsSection(all_skills, skills_dir=skills_dir))

        # PRIORITY 5 (HIGH): Memory - Proactive usage
        if enable_memory:
            short_term_memories, long_term_memories = self._get_all_memories()
            temp_workspace_memories = self._load_temp_workspace_memories()
            archived_memories = self._load_archived_memories()

            # Always add memory section to show usage instructions, even if empty
            memory_config = {
                "short_term": {
                    "content": "\n".join([f"- {m}" for m in short_term_memories]) if short_term_memories else "",
                },
                "long_term": [{"id": f"mem_{i}", "summary": mem, "created_at": "N/A"} for i, mem in enumerate(long_term_memories)] if long_term_memories else [],
                "temp_workspace_memories": temp_workspace_memories,
                "archived_memories": archived_memories,
            }
            builder.add_section(
                MemorySection(
                    memory_config,
                    read_only=not self._round_learning_capture_enabled,
                    allow_verification_capture=self._round_verification_capture_enabled,
                ),
            )
            archived_count = len(archived_memories.get("short_term", {})) + len(archived_memories.get("long_term", {}))
            logger.info(
                f"[SystemMessageBuilder] Added memory section "
                f"({len(short_term_memories)} short-term, {len(long_term_memories)} long-term, "
                f"{len(temp_workspace_memories)} temp workspace, {archived_count} archived)",
            )

        # PRIORITY 5 (HIGH): Filesystem - Essential context
        if agent.backend.filesystem_manager:
            main_workspace = str(agent.backend.filesystem_manager.get_current_workspace())
            context_paths = agent.backend.filesystem_manager.path_permission_manager.get_context_paths() if agent.backend.filesystem_manager.path_permission_manager else []

            # Check if two-tier workspace is enabled
            # Note: use_two_tier_workspace is already suppressed (set to False) on the
            # filesystem manager when write_mode is active, so no extra check needed here
            use_two_tier_workspace = False
            if hasattr(agent.backend, "filesystem_manager") and agent.backend.filesystem_manager:
                use_two_tier_workspace = getattr(agent.backend.filesystem_manager, "use_two_tier_workspace", False)

            # Add project instructions section (CLAUDE.md / AGENTS.md discovery)
            # This comes BEFORE workspace structure so project context is established first
            # When worktree_paths is set, discover from worktrees (full checkouts with CLAUDE.md)
            # instead of original context paths (which may not be mounted in Docker)
            discovery_paths = context_paths
            if worktree_paths:
                discovery_paths = [{"path": wt_path} for wt_path in worktree_paths]
            if discovery_paths:
                logger.info(f"[SystemMessageBuilder] Checking for project instructions in {len(discovery_paths)} {'worktree' if worktree_paths else 'context'} paths")
                builder.add_section(ProjectInstructionsSection(discovery_paths, workspace_root=main_workspace))

            # Add workspace structure section (critical paths)
            context_path_strs = [p.get("path", "") for p in context_paths]
            logger.info(
                f"[SystemMessageBuilder] System prompt paths: "
                f"context_paths={context_path_strs}, "
                f"worktree_paths={list(worktree_paths.keys()) if worktree_paths else None}, "
                f"discovery_paths={[p.get('path', '') for p in discovery_paths] if discovery_paths else None}",
            )
            builder.add_section(
                WorkspaceStructureSection(
                    main_workspace,
                    context_path_strs,
                    use_two_tier_workspace=use_two_tier_workspace,
                    decomposition_mode=is_decomposition,
                    worktree_paths=worktree_paths,
                    branch_name=branch_name,
                    other_branches=other_branches,
                    branch_diff_summaries=branch_diff_summaries,
                ),
            )

            # Check command execution settings
            enable_command_execution = False
            docker_mode = False
            enable_sudo = False
            concurrent_tool_execution = False
            if hasattr(agent, "config") and agent.config:
                enable_command_execution = agent.config.backend_params.get("enable_mcp_command_line", False)
                docker_mode = agent.config.backend_params.get("command_line_execution_mode", "local") == "docker"
                enable_sudo = agent.config.backend_params.get("command_line_docker_enable_sudo", False)
                concurrent_tool_execution = agent.config.backend_params.get("concurrent_tool_execution", False)
            elif hasattr(agent, "backend") and hasattr(agent.backend, "backend_params"):
                enable_command_execution = agent.backend.backend_params.get("enable_mcp_command_line", False)
                docker_mode = agent.backend.backend_params.get("command_line_execution_mode", "local") == "docker"
                enable_sudo = agent.backend.backend_params.get("command_line_docker_enable_sudo", False)
                concurrent_tool_execution = agent.backend.backend_params.get("concurrent_tool_execution", False)

            # Build and add filesystem sections using consolidated helper
            fs_ops, fs_best, cmd_exec = self._build_filesystem_sections(
                agent=agent,
                all_answers=answers,
                previous_turns=previous_turns,
                enable_command_execution=enable_command_execution,
                docker_mode=docker_mode,
                enable_sudo=enable_sudo,
                concurrent_tool_execution=concurrent_tool_execution,
                agent_mapping=agent_mapping,
                decomposition_mode=is_decomposition,
                essential_files_active=essential_files_active,
            )

            builder.add_section(fs_ops)
            builder.add_section(fs_best)
            if cmd_exec:
                builder.add_section(cmd_exec)

            # Add lightweight file search guidance if command execution is available
            # (rg and sg are pre-installed in Docker and commonly available in local mode)
            builder.add_section(FileSearchSection())

            # Add multimodal tools section if enabled
            enable_multimodal = agent.backend.config.get("enable_multimodal_tools", False)
            if enable_multimodal:
                builder.add_section(MultimodalToolsSection())
                logger.info(f"[SystemMessageBuilder] Added multimodal tools section for {agent_id}")

            # Add code-based tools section if enabled (CodeAct paradigm)
            if agent.backend.filesystem_manager.enable_code_based_tools:
                workspace_path = str(agent.backend.filesystem_manager.get_current_workspace())
                shared_tools_path = None
                if agent.backend.filesystem_manager.shared_tools_directory:
                    shared_tools_path = str(agent.backend.filesystem_manager.shared_tools_directory)

                # Get MCP servers from backend for description lookup
                mcp_servers = getattr(agent.backend, "mcp_servers", []) or []

                builder.add_section(CodeBasedToolsSection(workspace_path, shared_tools_path, mcp_servers))
                logger.info(f"[SystemMessageBuilder] Added code-based tools section for {agent_id}")

        # PRIORITY 10 (MEDIUM): Subagent Delegation (conditional)
        enable_subagents = False
        if hasattr(self.config, "coordination_config") and hasattr(self.config.coordination_config, "enable_subagents"):
            enable_subagents = self.config.coordination_config.enable_subagents
            if enable_subagents:
                # Get workspace path for subagent section
                workspace_path = ""
                if agent.backend.filesystem_manager:
                    workspace_path = str(agent.backend.filesystem_manager.get_current_workspace())
                # Get max concurrent from config, default to 3
                max_concurrent = getattr(self.config.coordination_config, "subagent_max_concurrent", 3)
                default_timeout = getattr(self.config.coordination_config, "subagent_default_timeout", 300)
                # Discover specialized subagent types from disk, filtered by config
                from massgen.subagent.type_scanner import DEFAULT_SUBAGENT_TYPES

                _st_cfg = getattr(self.config.coordination_config, "subagent_types", None)
                _allowed = _st_cfg if _st_cfg is not None else DEFAULT_SUBAGENT_TYPES
                specialized_subagents = self._discover_specialized_subagents(allowed_types=_allowed)
                builder.add_section(
                    SubagentSection(
                        workspace_path,
                        max_concurrent,
                        default_timeout=default_timeout,
                        specialized_subagents=specialized_subagents,
                        round_evaluator_before_checklist=getattr(
                            self.config.coordination_config,
                            "round_evaluator_before_checklist",
                            False,
                        ),
                        orchestrator_managed_round_evaluator=getattr(
                            self.config.coordination_config,
                            "orchestrator_managed_round_evaluator",
                            False,
                        ),
                    ),
                )
                logger.info(f"[SystemMessageBuilder] Added subagent section for {agent_id} (max_concurrent: {max_concurrent}, specialized_types: {len(specialized_subagents)})")

        # PRIORITY 10 (MEDIUM): Task Context (when multimodal tools OR subagents are enabled)
        # This instructs agents to create CONTEXT.md before using tools that make external API calls.
        # We pass `subagents_enabled` so the section only advertises `spawn_subagents` when it's
        # actually wired — otherwise models hallucinate phantom subagent MCP calls (e.g.,
        # `mcp__subagent_<8hex>__list_subagents`) and retry-loop against a non-existent server.
        enable_multimodal = agent.backend.config.get("enable_multimodal_tools", False) if agent.backend else False
        if enable_multimodal or enable_subagents:
            builder.add_section(TaskContextSection(subagents_enabled=enable_subagents))
            logger.info(f"[SystemMessageBuilder] Added task context section for {agent_id} (multimodal: {enable_multimodal}, subagents: {enable_subagents})")

        # PRIORITY 10 (MEDIUM): Task Planning
        if enable_task_planning:
            filesystem_mode = (
                hasattr(self.config.coordination_config, "task_planning_filesystem_mode")
                and self.config.coordination_config.task_planning_filesystem_mode
                and hasattr(agent, "backend")
                and hasattr(agent.backend, "filesystem_manager")
                and agent.backend.filesystem_manager
                and agent.backend.filesystem_manager.cwd
            )
            # specialized_subagents is only defined when enable_subagents is True;
            # ternary is safe here because Python short-circuits on the False branch.
            _tp_subagents = specialized_subagents if enable_subagents else []
            _checkpoint_enabled = hasattr(self.config, "coordination_config") and self.config.coordination_config and getattr(self.config.coordination_config, "checkpoint_enabled", False)
            builder.add_section(
                TaskPlanningSection(
                    filesystem_mode=filesystem_mode,
                    decomposition_mode=is_decomposition,
                    specialized_subagents=_tp_subagents,
                    checkpoint_mode=_checkpoint_enabled,
                    fast_iteration_mode=getattr(
                        getattr(self.config, "coordination_config", None),
                        "fast_iteration_mode",
                        False,
                    ),
                ),
            )

        # PRIORITY 10 (MEDIUM): Checkpoint Coordination (main agent only)
        _checkpoint_enabled = hasattr(self.config, "coordination_config") and self.config.coordination_config and getattr(self.config.coordination_config, "checkpoint_enabled", False)
        if _checkpoint_enabled:
            _coord = self.config.coordination_config
            builder.add_section(
                MainAgentCheckpointSection(
                    checkpoint_guidance=getattr(_coord, "checkpoint_guidance", ""),
                    gated_patterns=getattr(_coord, "checkpoint_gated_patterns", []) or [],
                    checkpoint_mode=getattr(_coord, "checkpoint_mode", "conversation"),
                ),
            )

        # PRIORITY 5 (HIGH): Standalone Checkpoint MCP (single-agent in-session use).
        # Affordance is stripped at the source when disabled OR when the parent
        # is multi-agent (the orchestrator skips MCP injection in that case;
        # rendering the prompt section anyway would promise an unregistered tool).
        _standalone_ckpt_enabled = (
            hasattr(self.config, "coordination_config")
            and self.config.coordination_config
            and getattr(self.config.coordination_config, "standalone_checkpoint_enabled", False)
            and len(self.agents) == 1
        )
        if _standalone_ckpt_enabled:
            _coord_sc = self.config.coordination_config
            builder.add_section(
                StandaloneCheckpointSection(
                    mode=getattr(_coord_sc, "standalone_checkpoint_mode", "generate"),
                    single_checkpoint=getattr(_coord_sc, "standalone_checkpoint_single", False),
                    include_workspace_context=getattr(
                        _coord_sc,
                        "standalone_checkpoint_include_workspace_context",
                        False,
                    ),
                ),
            )

        # PRIORITY 10 (MEDIUM): Evolving Skills (when auto-discovery AND task planning are both enabled)
        # Both gates must be true: evolving skills are structured work plans that complement task planning
        auto_discover_enabled = False
        if hasattr(agent, "backend") and hasattr(agent.backend, "config"):
            auto_discover_enabled = agent.backend.config.get("auto_discover_custom_tools", False)
        if auto_discover_enabled and enable_task_planning and self._round_learning_capture_enabled:
            # Check for plan.json to provide plan-aware guidance
            plan_context = None
            if hasattr(agent, "backend") and hasattr(agent.backend, "filesystem_manager") and agent.backend.filesystem_manager:
                workspace_path = Path(agent.backend.filesystem_manager.get_current_workspace())
                plan_file = workspace_path / "tasks" / "plan.json"
                if plan_file.exists():
                    try:
                        import json

                        plan_context = json.loads(plan_file.read_text())
                        logger.info(f"[SystemMessageBuilder] Found plan.json with {len(plan_context.get('tasks', []))} tasks for evolving skills")
                    except Exception as e:
                        logger.warning(f"[SystemMessageBuilder] Failed to read plan.json: {e}")

            _fast_iter = getattr(
                getattr(self.config, "coordination_config", None),
                "fast_iteration_mode",
                False,
            )
            builder.add_section(
                EvolvingSkillsSection(
                    plan_context=plan_context,
                    fast_iteration_mode=_fast_iter,
                ),
            )
            logger.info(f"[SystemMessageBuilder] Added evolving skills section for {agent_id}")

        # PRIORITY 10 (MEDIUM): Broadcast Communication (conditional)
        if hasattr(self.config, "coordination_config") and hasattr(self.config.coordination_config, "broadcast"):
            broadcast_mode = self.config.coordination_config.broadcast
            if broadcast_mode and broadcast_mode is not False:
                builder.add_section(
                    BroadcastCommunicationSection(
                        broadcast_mode=broadcast_mode,
                        wait_by_default=getattr(self.config.coordination_config, "broadcast_wait_by_default", True),
                        sensitivity=getattr(self.config.coordination_config, "broadcast_sensitivity", "medium"),
                        human_qa_history=human_qa_history,
                    ),
                )
                sensitivity = getattr(self.config.coordination_config, "broadcast_sensitivity", "medium")
                qa_count = len(human_qa_history) if human_qa_history else 0
                logger.info(f"[SystemMessageBuilder] Added broadcast section (mode: {broadcast_mode}, sensitivity: {sensitivity}, human_qa: {qa_count})")

        # PRIORITY 10 (MEDIUM): Planning Mode (conditional)
        if planning_mode_enabled and self.config and hasattr(self.config, "coordination_config") and self.config.coordination_config and self.config.coordination_config.planning_mode_instruction:
            builder.add_section(PlanningModeSection(self.config.coordination_config.planning_mode_instruction))
            logger.info(f"[SystemMessageBuilder] Added planning mode instructions for {agent_id}")

        # PRIORITY 10 (MEDIUM): Changedoc (conditional)
        changedoc_enabled = self._changedoc_enabled
        if changedoc_enabled:
            from massgen.system_prompt_sections import ChangedocSection

            has_prior_answers = bool(answers)
            builder.add_section(
                ChangedocSection(
                    has_prior_answers=has_prior_answers,
                    gap_report_mode=gap_report_mode,
                    round_evaluator_before_checklist=getattr(
                        getattr(self.config, "coordination_config", None),
                        "round_evaluator_before_checklist",
                        False,
                    ),
                    orchestrator_managed_round_evaluator=getattr(
                        getattr(self.config, "coordination_config", None),
                        "orchestrator_managed_round_evaluator",
                        False,
                    ),
                    round_evaluator_transformation_pressure=getattr(
                        getattr(self.config, "coordination_config", None),
                        "round_evaluator_transformation_pressure",
                        "balanced",
                    ),
                    essential_files_active=essential_files_active,
                ),
            )
            logger.info(f"[SystemMessageBuilder] Added changedoc instructions for {agent_id} (prior_answers={has_prior_answers})")

        # Build and return the complete structured system prompt
        return builder.build()

    def build_presentation_message(
        self,
        agent,  # ChatAgent
        all_answers: dict[str, str],
        previous_turns: list[dict[str, Any]],
        enable_file_generation: bool = False,
        has_irreversible_actions: bool = False,
        enable_command_execution: bool = False,
        docker_mode: bool = False,
        enable_sudo: bool = False,
        concurrent_tool_execution: bool = False,
        agent_mapping: dict[str, str] | None = None,
        artifact_type: str | None = None,
    ) -> str:
        """Build system message for final presentation phase.

        This combines the agent's identity, presentation instructions, and filesystem
        operations using the structured section approach.

        Args:
            agent: The presenting agent
            all_answers: All answers from coordination phase
            previous_turns: List of previous turn data for filesystem context
            enable_file_generation: Whether file generation is enabled
            has_irreversible_actions: Whether agent has write access
            enable_command_execution: Whether command execution is enabled
            docker_mode: Whether commands run in Docker
            enable_sudo: Whether sudo is available
            concurrent_tool_execution: Whether tools execute in parallel
            agent_mapping: Mapping from real agent ID to anonymous ID (e.g., agent_a -> agent1).
                          Pass from coordination_tracker.get_reverse_agent_mapping() for
                          global consistency with vote tool and injections.

        Returns:
            Complete system message string
        """
        # Get agent's configurable system message
        agent_system_message = agent.get_configurable_system_message()
        if agent_system_message is None:
            agent_system_message = ""

        # Get presentation instructions from message_templates.
        presentation_instructions = self.message_templates.final_presentation_system_message(
            original_system_message=agent_system_message,
            enable_file_generation=enable_file_generation,
            has_irreversible_actions=has_irreversible_actions,
            enable_command_execution=enable_command_execution,
        )

        # If filesystem is available, prepend filesystem sections
        if agent.backend.filesystem_manager:
            # Build filesystem sections using consolidated helper
            fs_ops, fs_best, cmd_exec = self._build_filesystem_sections(
                agent=agent,
                all_answers=all_answers,
                previous_turns=previous_turns,
                enable_command_execution=enable_command_execution,
                docker_mode=docker_mode,
                enable_sudo=enable_sudo,
                concurrent_tool_execution=concurrent_tool_execution,
                agent_mapping=agent_mapping,
            )

            # Build sections list
            sections_content = [fs_ops.build_content(), fs_best.build_content()]
            if cmd_exec:
                sections_content.append(cmd_exec.build_content())

            # Add code-based tools section if enabled (CodeAct paradigm)
            if agent.backend.filesystem_manager.enable_code_based_tools:
                workspace_path = str(agent.backend.filesystem_manager.get_current_workspace())
                shared_tools_path = None
                if agent.backend.filesystem_manager.shared_tools_directory:
                    shared_tools_path = str(agent.backend.filesystem_manager.shared_tools_directory)

                # Get MCP servers from backend for description lookup
                mcp_servers = getattr(agent.backend, "mcp_servers", []) or []

                code_based_tools_section = CodeBasedToolsSection(workspace_path, shared_tools_path, mcp_servers)
                sections_content.append(code_based_tools_section.build_content())
                logger.info("[SystemMessageBuilder] Added code-based tools section for presentation")

            # Add evolving skill consolidation instructions if auto-discovery enabled
            auto_discover_enabled = False
            if hasattr(agent, "backend") and hasattr(agent.backend, "config"):
                auto_discover_enabled = agent.backend.config.get("auto_discover_custom_tools", False)
            if auto_discover_enabled:
                evolving_skill_instructions = """## Evolving Skill Output

**REQUIRED**: Write a consolidated evolving skill to the final workspace.

Each agent has created their own evolving skill at `tasks/evolving_skill/SKILL.md` in their workspace.
Review these and consolidate into a single `SKILL.md` in the output directory:

- **name**: Descriptive name for this workflow
- **description**: What it does and when to reuse it
- **## Overview**: Problem solved
- **## Workflow**: The actual steps that worked (combined from all agents)
- **## Tools to Create**: Scripts written (with purpose, inputs, outputs)
- **## Tools to Use**: servers/ and custom_tools/ that were helpful
- **## Skills**: Other skills that were used
- **## Packages**: Dependencies installed
- **## Expected Outputs**: What this workflow produces
- **## Learnings**: What worked well, what didn't, tips for future use

If `tasks/changedoc.md` exists, use it as the authoritative source for decision rationale and learnings
when synthesizing the final `SKILL.md`.

This makes the work reusable for similar future tasks."""
                sections_content.append(evolving_skill_instructions)
                logger.info("[SystemMessageBuilder] Added evolving skill output instructions for presentation")

            # Add changedoc consolidation instructions if enabled
            changedoc_enabled = self._changedoc_enabled
            if changedoc_enabled:
                from massgen.system_prompt_sections import (
                    _CHANGEDOC_PRESENTER_INSTRUCTIONS,
                )

                sections_content.append(_CHANGEDOC_PRESENTER_INSTRUCTIONS)
                logger.info("[SystemMessageBuilder] Added changedoc consolidation instructions for presentation")

            # Add memory consolidation instructions if memory mode is enabled
            coordination_config = getattr(self.config, "coordination_config", None)
            memory_enabled = bool(
                coordination_config and getattr(coordination_config, "enable_memory_filesystem_mode", False),
            )
            if memory_enabled:
                from massgen.system_prompt_sections import (
                    _MEMORY_PRESENTER_INSTRUCTIONS,
                )

                sections_content.append(_MEMORY_PRESENTER_INSTRUCTIONS)
                logger.info("[SystemMessageBuilder] Added memory consolidation instructions for presentation")

            # Add spec compliance instructions if executing against a spec
            if artifact_type == "spec":
                from massgen.system_prompt_sections import _SPEC_PRESENTER_INSTRUCTIONS

                sections_content.append(_SPEC_PRESENTER_INSTRUCTIONS)
                logger.info("[SystemMessageBuilder] Added spec compliance instructions for presentation")

            # Combine: filesystem sections + presentation instructions
            filesystem_content = "\n\n".join(sections_content)
            return f"{filesystem_content}\n\n## Instructions\n{presentation_instructions}"
        else:
            # Add changedoc consolidation instructions if enabled (no filesystem case)
            changedoc_enabled = self._changedoc_enabled
            if changedoc_enabled:
                from massgen.system_prompt_sections import (
                    _CHANGEDOC_PRESENTER_INSTRUCTIONS,
                )

                presentation_instructions += _CHANGEDOC_PRESENTER_INSTRUCTIONS

            # Add memory consolidation instructions if memory mode is enabled (no filesystem case)
            coordination_config = getattr(self.config, "coordination_config", None)
            memory_enabled = bool(
                coordination_config and getattr(coordination_config, "enable_memory_filesystem_mode", False),
            )
            if memory_enabled:
                from massgen.system_prompt_sections import (
                    _MEMORY_PRESENTER_INSTRUCTIONS,
                )

                presentation_instructions += _MEMORY_PRESENTER_INSTRUCTIONS

            # Add spec compliance instructions if executing against a spec
            if artifact_type == "spec":
                from massgen.system_prompt_sections import _SPEC_PRESENTER_INSTRUCTIONS

                presentation_instructions += _SPEC_PRESENTER_INSTRUCTIONS

            # No filesystem - just return presentation instructions
            return presentation_instructions

    def build_post_evaluation_message(
        self,
        agent,  # ChatAgent
        all_answers: dict[str, str],
        previous_turns: list[dict[str, Any]],
        agent_mapping: dict[str, str] | None = None,
    ) -> str:
        """Build system message for post-evaluation phase.

        This combines the agent's identity, post-evaluation instructions, and filesystem
        operations using the structured section approach.

        Args:
            agent: The evaluating agent
            all_answers: All answers from coordination phase
            previous_turns: List of previous turn data for filesystem context
            agent_mapping: Mapping from real agent ID to anonymous ID (e.g., agent_a -> agent1).
                          Pass from coordination_tracker.get_reverse_agent_mapping() for
                          global consistency with vote tool and injections.

        Returns:
            Complete system message string
        """
        # Get agent's configurable system message
        agent_system_message = agent.get_configurable_system_message()
        if agent_system_message is None:
            agent_system_message = ""

        # Start with agent identity if provided
        parts = []
        if agent_system_message:
            parts.append(agent_system_message)

        # If filesystem is available, add filesystem sections
        if agent.backend.filesystem_manager:
            # Build filesystem sections using consolidated helper
            # (No command execution in post-evaluation)
            fs_ops, fs_best, _ = self._build_filesystem_sections(
                agent=agent,
                all_answers=all_answers,
                previous_turns=previous_turns,
                enable_command_execution=False,
                docker_mode=False,
                enable_sudo=False,
                agent_mapping=agent_mapping,
            )

            parts.append(fs_ops.build_content())
            parts.append(fs_best.build_content())

            # Add code-based tools section if enabled (CodeAct paradigm)
            if agent.backend.filesystem_manager.enable_code_based_tools:
                workspace_path = str(agent.backend.filesystem_manager.get_current_workspace())
                shared_tools_path = None
                if agent.backend.filesystem_manager.shared_tools_directory:
                    shared_tools_path = str(agent.backend.filesystem_manager.shared_tools_directory)

                # Get MCP servers from backend for description lookup
                mcp_servers = getattr(agent.backend, "mcp_servers", []) or []

                code_based_tools_section = CodeBasedToolsSection(workspace_path, shared_tools_path, mcp_servers)
                parts.append(code_based_tools_section.build_content())
                logger.info("[SystemMessageBuilder] Added code-based tools section for post-evaluation")

        # Add post-evaluation instructions
        post_eval = PostEvaluationSection()
        parts.append(post_eval.build_content())

        return "\n\n".join(parts)

    @staticmethod
    def _get_tool_category_overrides(agent) -> dict[str, str]:
        """Get tool_category_overrides for an agent's backend."""
        from massgen.backend.native_tool_mixin import NativeToolBackendMixin

        if hasattr(agent, "backend") and isinstance(agent.backend, NativeToolBackendMixin):
            return agent.backend.get_tool_category_overrides()
        return {}

    def _maybe_add_fast_mode_section(self, builder: SystemPromptBuilder, agent) -> None:
        """Add FastModeGuidanceSection when any fast-mode knob is active.

        Detects scaffolding-file presence in the agent's current workspace to
        decide whether the skip-redundant-scaffolding hint should fire. Cheap:
        two path existence checks.
        """
        coord_cfg = getattr(self.config, "coordination_config", None)
        if coord_cfg is None:
            return

        max_verifications = getattr(coord_cfg, "max_verifications_per_round", None)
        max_fix_loops = getattr(coord_cfg, "max_internal_fix_loops", None)
        skip_scaffolding = getattr(coord_cfg, "skip_redundant_scaffolding", False)

        if max_verifications is None and max_fix_loops is None and not skip_scaffolding:
            return

        scaffolding_exists = False
        if skip_scaffolding and hasattr(agent, "backend") and hasattr(agent.backend, "filesystem_manager") and agent.backend.filesystem_manager:
            try:
                workspace_path = Path(agent.backend.filesystem_manager.get_current_workspace())
                scaffolding_exists = (workspace_path / "tasks" / "changedoc.md").exists() or (workspace_path / "CONTEXT.md").exists() or (workspace_path / "tasks" / "plan.json").exists()
            except Exception as e:  # pragma: no cover - defensive
                logger.debug(f"[SystemMessageBuilder] scaffolding check failed: {e}")

        builder.add_section(
            FastModeGuidanceSection(
                max_verifications_per_round=max_verifications,
                max_internal_fix_loops=max_fix_loops,
                skip_redundant_scaffolding=skip_scaffolding,
                scaffolding_exists=scaffolding_exists,
            ),
        )

    def _build_filesystem_sections(
        self,
        agent,  # ChatAgent
        all_answers: dict[str, str],
        previous_turns: list[dict[str, Any]],
        enable_command_execution: bool,
        docker_mode: bool = False,
        enable_sudo: bool = False,
        concurrent_tool_execution: bool = False,
        agent_mapping: dict[str, str] | None = None,
        decomposition_mode: bool = False,
        essential_files_active: bool = False,
    ) -> tuple[Any, Any, Any | None]:  # Tuple[FilesystemOperationsSection, FilesystemBestPracticesSection, Optional[CommandExecutionSection]]
        """Build filesystem-related sections.

        This consolidates the duplicated logic across all three builder methods
        for creating filesystem operations, best practices, and command execution sections.

        Args:
            agent: The agent instance
            all_answers: Dict of current answers from agents
            previous_turns: List of previous turn data for filesystem context
            enable_command_execution: Whether to include command execution section
            docker_mode: Whether commands run in Docker
            enable_sudo: Whether sudo is available
            concurrent_tool_execution: Whether tools execute in parallel
            agent_mapping: Mapping from real agent ID to anonymous ID (e.g., agent_a -> agent1).
                          Pass from coordination_tracker.get_reverse_agent_mapping() for
                          global consistency with vote tool and injections.

        Returns:
            Tuple of (FilesystemOperationsSection, FilesystemBestPracticesSection, Optional[CommandExecutionSection])
        """
        # Extract filesystem paths from agent
        main_workspace = str(agent.backend.filesystem_manager.get_current_workspace())
        temp_workspace = str(agent.backend.filesystem_manager.agent_temporary_workspace) if agent.backend.filesystem_manager.agent_temporary_workspace else None
        context_paths = agent.backend.filesystem_manager.path_permission_manager.get_context_paths() if agent.backend.filesystem_manager.path_permission_manager else []

        # When write_mode is active (not legacy), worktrees replace original context paths.
        # Don't show original paths in filesystem operations — the agent works in the worktree.
        write_mode = getattr(agent.backend.filesystem_manager, "write_mode", None)
        if write_mode and write_mode != "legacy":
            logger.info(
                f"[SystemMessageBuilder] FilesystemOps: suppressing context_paths " f"{[p.get('path', '') for p in context_paths]} (write_mode={write_mode})",
            )
            context_paths = []

        # Calculate previous turns context
        current_turn_num = len(previous_turns) + 1 if previous_turns else 1
        turns_to_show = [t for t in previous_turns if t["turn"] < current_turn_num - 1]
        workspace_prepopulated = len(previous_turns) > 0

        # Get code-based tools flag from agent
        enable_code_based_tools = agent.backend.filesystem_manager.enable_code_based_tools

        # Check if backend has native file tools
        overrides = self._get_tool_category_overrides(agent)
        has_native_tools = overrides.get("filesystem") == "skip"

        # Build filesystem operations section
        fs_ops = FilesystemOperationsSection(
            main_workspace=main_workspace,
            temp_workspace=temp_workspace,
            context_paths=context_paths,
            previous_turns=turns_to_show,
            workspace_prepopulated=workspace_prepopulated,
            agent_answers=all_answers,
            enable_command_execution=enable_command_execution,
            agent_mapping=agent_mapping,
            has_native_tools=has_native_tools,
            essential_files_active=essential_files_active,
        )

        # Build filesystem best practices section
        fs_best = FilesystemBestPracticesSection(enable_code_based_tools=enable_code_based_tools, decomposition_mode=decomposition_mode)

        # Build command execution section if enabled
        cmd_exec = None
        if enable_command_execution:
            cmd_exec = CommandExecutionSection(
                docker_mode=docker_mode,
                enable_sudo=enable_sudo,
                concurrent_tool_execution=concurrent_tool_execution,
            )

        return fs_ops, fs_best, cmd_exec

    def _get_all_memories(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Read all memories from all agents' workspaces.

        Returns:
            Tuple of (short_term_memories, long_term_memories)
            Each is a list of memory dictionaries with keys:
            - name, description, content, tier, agent_id, created, updated
        """
        short_term_memories = []
        long_term_memories = []

        # Scan all agents' workspaces
        for agent_id, agent in self.agents.items():
            if not (hasattr(agent, "backend") and hasattr(agent.backend, "filesystem_manager") and agent.backend.filesystem_manager):
                continue

            workspace = agent.backend.filesystem_manager.cwd
            if not workspace:
                continue

            memory_dir = Path(workspace) / "memory"
            if not memory_dir.exists():
                continue

            # Read short-term memories
            short_term_dir = memory_dir / "short_term"
            if short_term_dir.exists():
                for mem_file in short_term_dir.glob("*.md"):
                    try:
                        memory_data = self._parse_memory_file(mem_file)
                        if memory_data:
                            short_term_memories.append(memory_data)
                    except Exception as e:
                        logger.warning(f"[SystemMessageBuilder] Failed to parse memory file {mem_file}: {e}")

            # Read long-term memories
            long_term_dir = memory_dir / "long_term"
            if long_term_dir.exists():
                for mem_file in long_term_dir.glob("*.md"):
                    try:
                        memory_data = self._parse_memory_file(mem_file)
                        if memory_data:
                            long_term_memories.append(memory_data)
                    except Exception as e:
                        logger.warning(f"[SystemMessageBuilder] Failed to parse memory file {mem_file}: {e}")

        return short_term_memories, long_term_memories

    def _load_archived_memories(self) -> dict[str, dict[str, Any]]:
        """Load all archived memories from sessions directory with deduplication.

        Deduplicate by filename - for memories with the same name across multiple archives,
        only keep the most recent version by file modification timestamp.

        Returns:
            Dictionary mapping tier ("short_term", "long_term") to memory dictionaries:
            - Each memory dict maps filename to {"content": str, "source": str, "timestamp": float}
        """
        if not self.session_id:
            return {"short_term": {}, "long_term": {}}

        # Load from sessions/ directory (persistent), not snapshots/ (gets cleared)
        archive_base = Path(".massgen/sessions") / self.session_id / "archived_memories"
        if not archive_base.exists():
            return {"short_term": {}, "long_term": {}}

        # Track all memories by filename with metadata for deduplication
        # Format: {tier: {filename: [{"content": str, "source": str, "timestamp": float, "path": Path}, ...]}}
        all_memories: dict[str, dict[str, list]] = {"short_term": {}, "long_term": {}}

        # Scan all archived answer directories
        for archive_dir in sorted(archive_base.iterdir()):
            if not archive_dir.is_dir():
                continue

            # Parse source label from directory name
            dir_name = archive_dir.name
            source_label = dir_name.replace("_", " ").title()  # "Agent A Answer 0"

            # Process both tiers
            for tier in ["short_term", "long_term"]:
                tier_dir = archive_dir / tier
                if not tier_dir.exists():
                    continue

                for mem_file in tier_dir.glob("*.md"):
                    try:
                        filename = self._get_archived_memory_key(mem_file.stem, dir_name)
                        content = self._normalize_memory_content_paths(mem_file.read_text())
                        timestamp = mem_file.stat().st_mtime

                        # Initialize list for this filename if needed
                        if filename not in all_memories[tier]:
                            all_memories[tier][filename] = []

                        # Add this version
                        all_memories[tier][filename].append(
                            {
                                "content": content,
                                "source": source_label,
                                "timestamp": timestamp,
                                "path": mem_file,
                            },
                        )
                    except Exception as e:
                        logger.warning(f"[SystemMessageBuilder] Failed to read archived memory {mem_file}: {e}")

        # Deduplicate: for each filename, keep only the most recent version
        deduplicated = {"short_term": {}, "long_term": {}}
        for tier in ["short_term", "long_term"]:
            for filename, versions in all_memories[tier].items():
                # Sort by timestamp descending and take the most recent
                latest = max(versions, key=lambda v: v["timestamp"])
                deduplicated[tier][filename] = {
                    "content": latest["content"],
                    "source": latest["source"],
                    "timestamp": latest["timestamp"],
                }

        return deduplicated

    @staticmethod
    def _get_archived_memory_key(filename: str, archive_dir_name: str) -> str:
        """Return a dedupe key for archived memory files.

        Verification replay memories must remain distinct per agent even when they
        share the same canonical filename (`verification_latest.md`).
        """
        normalized = filename.strip()
        if normalized.startswith("verification_latest__"):
            return normalized
        if normalized != "verification_latest":
            return normalized

        match = re.match(r"^(?P<agent>.+)_answer_\d+$", archive_dir_name)
        if not match:
            return normalized
        return f"{normalized}__{match.group('agent')}"

    def _get_workspace_path_replacements(self) -> list[tuple[str, str]]:
        """Map agent workspace roots to temp workspace token paths."""
        if not self.agent_temporary_workspace:
            return []

        temp_base = Path(self.agent_temporary_workspace)
        replacements: list[tuple[str, str]] = []

        for agent in self.agents.values():
            backend = getattr(agent, "backend", None)
            filesystem_manager = getattr(backend, "filesystem_manager", None)
            if not filesystem_manager:
                continue

            source_workspace = getattr(filesystem_manager, "cwd", None)
            workspace_token = getattr(filesystem_manager, "workspace_token", None)
            if not source_workspace or not workspace_token:
                continue

            source_root = str(Path(source_workspace).resolve())
            temp_root = str((temp_base / workspace_token).resolve())
            if source_root != temp_root:
                replacements.append((source_root, temp_root))

        # Longest-first avoids partial-prefix replacement mismatches.
        replacements.sort(key=lambda pair: len(pair[0]), reverse=True)
        return replacements

    def _normalize_memory_content_paths(self, content: str) -> str:
        """Normalize absolute workspace paths in memory content for current context."""
        normalized = content
        for source_root, temp_root in self._get_workspace_path_replacements():
            normalized = normalized.replace(source_root, temp_root)
        return normalized

    def _load_temp_workspace_memories(self) -> list[dict[str, Any]]:
        """Load all memories from temp workspace directories.

        Returns:
            List of temp workspace memory dictionaries with keys:
            - agent_label: Anonymous agent label (e.g., "agent1", "agent2")
            - memories: Dict with short_term and long_term subdicts
                Each subdict maps memory filename to full memory data (including metadata)
        """
        if not self.agent_temporary_workspace:
            return []

        temp_workspace_base = Path(self.agent_temporary_workspace)
        if not temp_workspace_base.exists():
            return []

        temp_memories = []

        # Scan all agent directories in temp workspace
        for agent_dir in sorted(temp_workspace_base.iterdir()):
            if not agent_dir.is_dir():
                continue

            agent_label = agent_dir.name  # e.g., "agent1", "agent2"
            memory_dir = agent_dir / "memory"

            if not memory_dir.exists():
                continue

            memories = {"short_term": {}, "long_term": {}}

            # Load short_term memories
            short_term_dir = memory_dir / "short_term"
            if short_term_dir.exists():
                for mem_file in short_term_dir.glob("*.md"):
                    try:
                        memory_data = self._parse_memory_file(mem_file)
                        if memory_data:
                            memory_data["content"] = self._normalize_memory_content_paths(
                                str(memory_data.get("content", "")),
                            )
                            memories["short_term"][mem_file.stem] = memory_data
                        else:
                            # Fallback to raw content if parsing fails
                            memories["short_term"][mem_file.stem] = {
                                "name": mem_file.stem,
                                "content": self._normalize_memory_content_paths(mem_file.read_text()),
                            }
                    except Exception as e:
                        logger.warning(f"[SystemMessageBuilder] Failed to read temp workspace memory {mem_file}: {e}")

            # Load long_term memories
            long_term_dir = memory_dir / "long_term"
            if long_term_dir.exists():
                for mem_file in long_term_dir.glob("*.md"):
                    try:
                        memory_data = self._parse_memory_file(mem_file)
                        if memory_data:
                            memory_data["content"] = self._normalize_memory_content_paths(
                                str(memory_data.get("content", "")),
                            )
                            memories["long_term"][mem_file.stem] = memory_data
                        else:
                            # Fallback to raw content if parsing fails
                            memories["long_term"][mem_file.stem] = {
                                "name": mem_file.stem,
                                "content": self._normalize_memory_content_paths(mem_file.read_text()),
                            }
                    except Exception as e:
                        logger.warning(f"[SystemMessageBuilder] Failed to read temp workspace memory {mem_file}: {e}")

            # Only add if there are actual memories
            if memories["short_term"] or memories["long_term"]:
                temp_memories.append(
                    {
                        "agent_label": agent_label,
                        "memories": memories,
                    },
                )

        return temp_memories

    @staticmethod
    def _parse_memory_file(file_path: Path) -> dict[str, Any] | None:
        """Parse a memory markdown file with YAML frontmatter.

        Args:
            file_path: Path to the memory file

        Returns:
            Dictionary with memory data or None if parsing fails
        """
        try:
            content = file_path.read_text()

            # Split frontmatter from content
            if not content.startswith("---"):
                return None

            parts = content.split("---", 2)
            if len(parts) < 3:
                return None

            frontmatter_text = parts[1].strip()
            memory_content = parts[2].strip()

            # Parse frontmatter (simple key: value parser)
            metadata = {}
            for line in frontmatter_text.split("\n"):
                line = line.strip()
                if ":" in line:
                    key, value = line.split(":", 1)
                    metadata[key.strip()] = value.strip()

            # Return combined memory data
            return {
                "name": metadata.get("name", ""),
                "description": metadata.get("description", ""),
                "content": memory_content,
                "tier": metadata.get("tier", ""),
                "agent_id": metadata.get("agent_id", ""),
                "created": metadata.get("created", ""),
                "updated": metadata.get("updated", ""),
            }
        except Exception:
            return None
