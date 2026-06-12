"""Single source of truth for config params never forwarded to provider APIs.

Historically this list was hand-duplicated in two places
(``backend.base.get_base_excluded_config_params`` and
``api_params_handler._api_params_handler_base.get_base_excluded_params``), which
guaranteed drift — a new non-API param added to one but not the other would leak
to the provider API from the other code path. Both now derive from this set.

This module imports nothing so it stays a dependency leaf (no import cycles).
"""

from __future__ import annotations

# Parameters handled by the base class / orchestrator and never passed directly
# to provider API calls. Backends extend this with their own specific exclusions.
BASE_EXCLUDED_CONFIG_PARAMS: frozenset[str] = frozenset(
    {
        # Filesystem manager parameters (handled by base class)
        "cwd",
        "agent_temporary_workspace",
        "agent_temporary_workspace_parent",
        "context_paths",
        "context_write_access_enabled",
        "enforce_read_before_delete",
        "enable_image_generation",
        "enable_audio_generation",
        "enable_file_generation",
        "enable_video_generation",
        "enable_mcp_command_line",
        "command_line_allowed_commands",
        "command_line_blocked_commands",
        "command_line_execution_mode",
        "command_line_docker_image",
        "command_line_docker_memory_limit",
        "command_line_docker_cpu_limit",
        "command_line_docker_network_mode",
        "command_line_docker_enable_sudo",
        # Docker credential and package management (nested dicts)
        "command_line_docker_credentials",
        "command_line_docker_packages",
        # SRT (OS-level sandbox-runtime) execution mode parameters
        "command_line_srt_network_allowed_domains",
        "command_line_srt_deny_read",
        "command_line_srt_allow_unix_sockets",
        "command_line_srt_read_mode",
        "command_line_srt_allow_read",
        "exclude_file_operation_mcps",
        "use_mcpwrapped_for_tool_filtering",
        "use_no_roots_wrapper",
        # Code-based tools (CodeAct paradigm)
        "enable_code_based_tools",
        "custom_tools_path",
        "auto_discover_custom_tools",
        "exclude_custom_tools",
        "direct_mcp_servers",
        "shared_tools_directory",
        # Backend identification (handled by orchestrator)
        "type",
        "agent_id",
        "session_id",  # Memory/conversation session ID from chat_agent
        "filesystem_session_id",  # Docker filesystem session mount
        "session_storage_base",
        # MCP configuration (handled by base class for MCP backends)
        "mcp_servers",
        # NLIP configuration belongs to MassGen routing, never provider APIs
        "enable_nlip",
        "nlip",
        "nlip_config",
        # Parallelization
        "instance_id",
        # Rate limiting (handled by rate_limiter.py)
        "enable_rate_limit",
        "concurrent_tool_execution",  # Local execution control (not sent to API)
        "max_concurrent_tools",  # Local execution control (not sent to API)
        # Coordination parameters (handled by orchestrator, not passed to API)
        "vote_only",  # Vote-only mode flag for coordination
        "plan_depth",
        "plan_thoroughness",
        "plan_target_steps",
        "plan_target_chunks",
        "use_two_tier_workspace",  # Two-tier workspace (scratch/deliverable) + git versioning
        "write_mode",  # Isolated write context mode (auto/worktree/isolated/legacy)
        "drift_conflict_policy",  # Isolated apply drift resolution policy
        "subagent_types",  # Which subagent types to expose (handled by orchestrator)
        "round_evaluator_before_checklist",  # Coordination-only evaluator-first loop control
        "orchestrator_managed_round_evaluator",  # Gate for orchestrator-owned round_evaluator launch
        "round_evaluator_skip_synthesis",  # Skip synthesis; pass raw critiques to parent directly
        "round_evaluator_refine",  # Allow evaluator agents to iterate (multi-round with voting)
        "round_evaluator_transformation_pressure",  # Coordination-only bias for evaluator thesis boldness
        "enable_quality_rethink_on_iteration",  # Coordination-only quality task injection toggle
        "enable_novelty_on_iteration",  # Coordination-only novelty task injection toggle
        "enable_execution_trace_analyzer",  # Coordination-only execution trace analysis toggle
        "novelty_injection",  # Novelty pressure level (none/gentle/moderate/aggressive)
        "improvements",  # draft_approach gate settings (orchestrator/checklist only)
        "learning_capture_mode",  # Learning capture timing (round/verification_and_final_only/final_only)
        "criteria_mode",  # Discriminative criteria emergence mode (static/bootstrap_inline/bootstrap_subagent)
        "bootstrap_max_per_agent_per_round",  # Cap on per-round, per-agent criteria proposals
        "bootstrap_max_total",  # Global FIFO cap on bootstrap accumulator
        "disable_final_only_round_capture_fallback",  # Coordination-only fallback control for final_only+skip_final_presentation
        # Multimodal tools configuration (handled by CustomToolAndMCPBackend)
        "enable_multimodal_tools",
        "multimodal_config",
        "image_generation_backend",
        "image_generation_model",
        "video_generation_backend",
        "video_generation_model",
        "audio_generation_backend",
        "audio_generation_model",
        # Hook framework (handled by base class)
        "hooks",
        # Permissions system (handled by the hook installer)
        "permissions",
        # Debug options (not passed to API)
        "debug_delay_seconds",
        "debug_delay_after_n_tools",
        # Per-agent voting sensitivity (coordination config, not API param)
        "voting_sensitivity",
        "voting_threshold",
        "checklist_require_gap_report",
        "gap_report_mode",
        # Decomposition mode parameters (handled by orchestrator, not passed to API)
        "coordination_mode",
        "presenter_agent",
        "final_answer_strategy",
        "subtask",
        # Fairness controls (handled by orchestrator, not passed to API)
        "fairness_enabled",
        "fairness_lead_cap_answers",
        "max_midstream_injections_per_round",
        # WebSocket mode (transport control, not an API parameter)
        "websocket_mode",
        "defer_peer_updates_until_restart",
        "allow_midstream_peer_updates_before_checklist_submit",
        "max_checklist_calls_per_round",
        "checklist_first_answer",
        # Checkpoint coordination (handled by orchestrator, not passed to API)
        "main_agent",
        "checkpoint_enabled",
        "checkpoint_mode",
        "checkpoint_guidance",
        "checkpoint_gated_patterns",
        "standalone_checkpoint_enabled",
        "standalone_checkpoint_team_config",
        "standalone_checkpoint_mode",
        "standalone_checkpoint_single",
        "standalone_checkpoint_include_workspace_context",
    },
)
