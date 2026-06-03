#!/usr/bin/env python3
"""CLI entry points: argument parser and main dispatch.

Part of the massgen.cli package (extracted from the legacy monolithic cli.py).
"""

import argparse
import asyncio
import copy
import json
import sys
import threading
import webbrowser
from pathlib import Path
from typing import (
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    pass


from ..agent_config import AgentConfig
from ..config_builder import ConfigBuilder
from ..logger_config import logger, save_execution_metadata, setup_logging
from ..orchestrator import Orchestrator
from ..utils import get_backend_type_from_model

# --- cross-module references within the cli package ---
from ._constants import (
    BRIGHT_CYAN,
    BRIGHT_GREEN,
    BRIGHT_RED,
    BRIGHT_YELLOW,
    EXIT_CONFIG_ERROR,
    EXIT_EXECUTION_ERROR,
    EXIT_INTERRUPTED,
    EXIT_TIMEOUT,
    RESET,
    SESSION_STORAGE,
)
from .backends import create_agents_from_config, create_dspy_paraphraser_from_config
from .config_loading import (
    ConfigurationError,
    _scope_agent_temporary_workspace,
    _scope_snapshot_storage,
    apply_cli_cwd_context_path,
    create_simple_config,
    inject_prompt_context_paths,
    load_config_file,
    relocate_filesystem_paths,
    resolve_config_path,
    validate_context_paths,
)
from .config_parsing import (
    _apply_orchestrator_runtime_params,
    _parse_coordination_config,
    _parse_timeout_config,
)
from .docker_setup import setup_computer_use_docker, setup_docker
from .env import _automation_print, _setup_logfire_observability, load_env_file
from .examples import (
    _print_backends_table,
    interactive_config_selector,
    print_example_config,
    show_available_examples,
)
from .input import _restore_terminal_for_input
from .mode_flags import (
    _build_cli_overrides_dict,
    add_mode_flags_to_parser,
    apply_mode_flags_to_config,
    build_cli_mode_defaults,
    filter_agents_for_single_mode,
    validate_mode_flag_combinations,
)
from .plan_commands import run_execute_plan, run_execute_spec, run_plan_and_execute
from .planning import (
    _disable_evaluation_criteria_generation_for_planning,
    _inject_checklist_criteria_preset_into_config,
    _inject_eval_criteria_into_config,
    _load_eval_criteria,
    _set_planning_checklist_criteria_defaults,
)
from .prompts import get_spec_creation_prompt_prefix, get_task_planning_prompt_prefix
from .quickstart import (
    _ensure_quickstart_skills_ready,
    _headless_quickstart_output_path_from_config_arg,
    _parse_quickstart_agent_specs,
    _print_headless_quickstart_summary,
    _pull_docker_image_headless,
    _quickstart_filename_from_config_arg,
    should_run_builder,
)
from .run import run_interactive_mode, run_single_question
from .streaming import (
    _build_coordination_ui,
    _setup_event_streaming,
    _setup_timeline_event_recording,
)


async def main(args):
    """Main CLI entry point (async operations only)."""
    # Setup logging (only for actual agent runs, not special commands)
    setup_logging(debug=args.debug)

    # Configure event streaming to stdout if requested
    # This enables parent processes (TUI subagent modal) to receive real-time updates
    if getattr(args, "stream_events", False):
        # --stream-events implies --automation
        args.automation = True
        _setup_event_streaming()
        _setup_timeline_event_recording()

    # Configure Logfire observability if requested
    if getattr(args, "logfire", False):
        _setup_logfire_observability()

    if args.debug:
        logger.info("Debug mode enabled")
        logger.debug(f"Command line arguments: {vars(args)}")

    # Initialize streaming buffer saving if requested
    if args.save_streaming_buffers:
        from ..backend._streaming_buffer_mixin import set_save_streaming_buffers

        set_save_streaming_buffers(True)

    _metadata_saved_for_failure = False

    def _save_prompt_metadata_failure_fallback(
        failure_stage: str,
        failure_error: Exception | None = None,
    ) -> None:
        """Persist prompt metadata even when execution stops early."""
        nonlocal _metadata_saved_for_failure

        if _metadata_saved_for_failure:
            return

        if not getattr(args, "question", None):
            return

        try:
            cli_args = vars(args).copy()
            cli_args["failure_stage"] = failure_stage
            if failure_error is not None:
                cli_args["failure_error"] = str(failure_error)

            save_execution_metadata(
                query=args.question,
                config_path=str(resolved_path) if "resolved_path" in locals() and resolved_path else None,
                config_content=raw_config_for_metadata if "raw_config_for_metadata" in locals() else None,
                cli_args=cli_args,
            )
            _metadata_saved_for_failure = True
        except Exception as exc:  # pragma: no cover - best-effort metadata write
            logger.debug(f"Failed to save fallback execution metadata: {exc}")

    # Check if bare `massgen` with no args - use default config if it exists
    if not args.backend and not args.model and not args.config:
        # Use resolve_config_path to check project-level then global config
        resolved_default = resolve_config_path(None)
        if resolved_default:
            # Use discovered config for interactive mode (no question) or single query (with question)
            args.config = str(resolved_default)
        else:
            # No default config - this will be handled by wizard trigger in cli_main()
            if args.question:
                # User provided a question but no config exists - this is an error
                print(
                    "❌ Configuration error: No default configuration found.",
                    file=sys.stderr,
                    flush=True,
                )
                print(
                    "Run 'massgen --init' to create one, or use 'massgen --model MODEL \"question\"'",
                    file=sys.stderr,
                    flush=True,
                )
                _save_prompt_metadata_failure_fallback("missing_default_config")
                sys.exit(EXIT_CONFIG_ERROR)
            # No question and no config - wizard will be triggered in cli_main()
            return

    # Session config was already loaded in cli_main() if --session-id or --continue was used
    # Try to use config from session if it was set
    if args.session_id and not args.config and not args.model and not args.backend:
        from massgen.session import SessionRegistry

        registry = SessionRegistry()
        session_metadata = registry.get_session(args.session_id)
        if session_metadata:
            session_config_path = session_metadata.get("config_path")
            if session_config_path:
                args.config = session_config_path
                print(
                    f"   Using config from session: {Path(session_config_path).name}",
                    flush=True,
                )

    # Validate arguments (only if we didn't auto-set config above)
    if not args.backend:
        if not args.model and not args.config:
            print(
                "❌ Configuration error: Either --config, --model, or --backend must be specified",
                file=sys.stderr,
                flush=True,
            )
            _save_prompt_metadata_failure_fallback("missing_execution_source")
            sys.exit(EXIT_CONFIG_ERROR)

    # Track config path for error messages
    resolved_path = None

    try:
        # Load or create configuration
        if args.config:
            # Resolve config path (handles @examples/, paths, ~/.config/massgen/agents/)
            resolved_path = resolve_config_path(args.config)
            if resolved_path is None:
                # This shouldn't happen if we reached here, but handle it
                raise ConfigurationError("Could not resolve config path")
            config, raw_config_for_metadata = load_config_file(str(resolved_path))
            if args.debug:
                logger.debug(f"Resolved config path: {resolved_path}")
                logger.debug(f"Config content: {json.dumps(config, indent=2)}")

            # Capture prompt from config as early as possible for metadata capture on early failures
            if not args.question and "prompt" in config:
                args.question = config["prompt"]

            # Check if this is a computer use docker example - setup required
            config_filename = resolved_path.name if resolved_path else ""
            if "computer_use_docker_example" in config_filename:
                print(
                    f"\n{BRIGHT_CYAN}🖥️  Computer Use Docker Configuration Detected{RESET}",
                )
                print(
                    f"{BRIGHT_YELLOW}This configuration requires a special Docker container for GUI automation.{RESET}\n",
                )

                # Check if container exists and is running
                import subprocess

                try:
                    result = subprocess.run(
                        [
                            "docker",
                            "ps",
                            "--filter",
                            "name=cua-container",
                            "--format",
                            "{{.Names}}",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    container_running = "cua-container" in result.stdout
                except Exception:
                    container_running = False

                if not container_running:
                    print(
                        f"{BRIGHT_YELLOW}⚠️  Computer Use Docker container not found or not running{RESET}",
                    )
                    print(f"{BRIGHT_CYAN}Starting automatic setup...{RESET}\n")

                    if not setup_computer_use_docker():
                        print(
                            f"\n{BRIGHT_RED}❌ Failed to setup Computer Use Docker container{RESET}",
                        )
                        print(
                            f"{BRIGHT_YELLOW}Computer use features will not work without this container.{RESET}",
                        )
                        print(
                            f"{BRIGHT_YELLOW}You can try manual setup with: scripts/setup_docker_cua.sh{RESET}\n",
                        )
                        sys.exit(EXIT_CONFIG_ERROR)
                else:
                    print(
                        f"{BRIGHT_GREEN}✓ Computer Use Docker container is ready{RESET}\n",
                    )

            # Automatic config validation (unless --skip-validation flag is set)
            if not args.skip_validation:
                from ..config_validator import ConfigValidator

                validator = ConfigValidator()
                validation_result = validator.validate_config(config)

                # Show errors if any
                if validation_result.has_errors():
                    print(validation_result.format_errors(), file=sys.stderr)
                    print(
                        f"\n{BRIGHT_RED}❌ Config validation failed. Fix errors above or use --skip-validation to bypass.{RESET}\n",
                    )
                    sys.exit(EXIT_CONFIG_ERROR)

                # Show warnings (non-blocking unless --strict-validation)
                if validation_result.has_warnings():
                    print(validation_result.format_warnings())
                    if args.strict_validation:
                        print(
                            f"\n{BRIGHT_RED}❌ Config validation failed in strict mode (warnings treated as errors).{RESET}\n",
                        )
                        sys.exit(EXIT_CONFIG_ERROR)
                    print()  # Extra newline for readability
        else:
            model = args.model
            if args.backend:
                backend = args.backend
            else:
                backend = get_backend_type_from_model(model=model)
            if args.system_message:
                system_message = args.system_message
            else:
                system_message = None
            config = create_simple_config(
                backend_type=backend,
                model=model,
                system_message=system_message,
                base_url=args.base_url,
            )
            # For simple configs, there's no env var expansion, so raw = config
            raw_config_for_metadata = copy.deepcopy(config)
            if args.debug:
                logger.debug(
                    f"Created simple config with backend: {backend}, model: {model}",
                )
                logger.debug(f"Config content: {json.dumps(config, indent=2)}")

        # Apply CLI override for CWD context path before validating paths.
        apply_cli_cwd_context_path(config, args.cwd_context)

        # Validate that all context paths exist before proceeding
        validate_context_paths(config)

        # Relocate all filesystem paths to .massgen/ directory
        relocate_filesystem_paths(config)

        # Generate unique instance ID for parallel execution safety
        # This prevents Docker container naming conflicts when running multiple instances
        import uuid

        instance_id = uuid.uuid4().hex[:8]

        # Inject instance_id to all agent backend configs for Docker container naming
        # Note: Workspace suffixing is now handled in create_agents_from_config() for all entrypoints
        agent_entries = [config["agent"]] if "agent" in config else config.get("agents", [])
        for agent_data in agent_entries:
            backend_config = agent_data.get("backend", {})
            backend_config["instance_id"] = instance_id

        # Apply command-line overrides
        ui_config = config.get("ui", {})
        # Set default display type to textual_terminal if not specified
        if "display_type" not in ui_config:
            ui_config["display_type"] = "textual_terminal"
        if args.automation:
            # Automation mode: silent display, keep logging enabled for status.json
            ui_config["display_type"] = "silent"
            ui_config["logging_enabled"] = True
            ui_config["automation_mode"] = True
        if args.skip_agent_selector:
            ui_config["skip_agent_selector"] = True
        if args.no_display:
            ui_config["display_type"] = "simple"
        # --display flag overrides --no-display if both specified
        if args.display:
            display_type_map = {"rich": "rich_terminal", "textual": "textual_terminal"}
            ui_config["display_type"] = display_type_map.get(
                args.display,
                "rich_terminal",
            )

        # Deprecation warning for rich_terminal (unless explicitly overridden with --display rich)
        if ui_config.get("display_type") == "rich_terminal" and not (args.display == "rich"):
            import warnings

            warnings.warn(
                "display_type 'rich_terminal' is deprecated. The Textual TUI will be used instead. " "Update your config to use 'textual_terminal', or use '--display rich' to force Rich display.",
                DeprecationWarning,
                stacklevel=2,
            )
            # Override to textual_terminal
            ui_config["display_type"] = "textual_terminal"

        # Persist UI overrides onto config so downstream helpers (for example
        # plan-and-execute phases) see the same resolved display settings.
        config["ui"] = ui_config

        if args.no_logs:
            ui_config["logging_enabled"] = False
        if args.debug:
            ui_config["debug"] = True
            # Enable logging if debug is on
            ui_config["logging_enabled"] = True
            # # Force simple UI in debug mode
            # ui_config["display_type"] = "simple"

        # Apply timeout overrides from CLI arguments
        timeout_settings = config.get("timeout_settings", {})
        if args.orchestrator_timeout is not None:
            timeout_settings["orchestrator_timeout_seconds"] = args.orchestrator_timeout

        # Update config with timeout settings
        config["timeout_settings"] = timeout_settings

        # Handle --plan mode: auto-configure for task planning
        if getattr(args, "plan", False):
            # Ensure orchestrator section exists
            if "orchestrator" not in config:
                config["orchestrator"] = {}
            orchestrator_cfg_plan = config["orchestrator"]

            # Ensure coordination section exists
            if "coordination" not in orchestrator_cfg_plan:
                orchestrator_cfg_plan["coordination"] = {}

            # Broadcast mode: CLI flag wins; otherwise default to autonomous ("false")
            broadcast_arg = getattr(args, "broadcast", None)
            if broadcast_arg == "false":
                orchestrator_cfg_plan["coordination"]["broadcast"] = False
            elif broadcast_arg is not None:
                orchestrator_cfg_plan["coordination"]["broadcast"] = broadcast_arg
            else:
                orchestrator_cfg_plan["coordination"].setdefault("broadcast", False)

            # Set plan_depth and plan_thoroughness
            orchestrator_cfg_plan["coordination"]["plan_depth"] = getattr(
                args,
                "plan_depth",
                "dynamic",
            )
            orchestrator_cfg_plan["coordination"]["plan_thoroughness"] = getattr(
                args,
                "plan_thoroughness",
                "standard",
            )
            orchestrator_cfg_plan["coordination"]["plan_target_steps"] = getattr(
                args,
                "plan_steps",
                None,
            )
            resolved_plan_target_chunks = getattr(
                args,
                "plan_chunks",
                None,
            )
            if resolved_plan_target_chunks is None:
                existing_chunk_target = orchestrator_cfg_plan["coordination"].get("plan_target_chunks")
                if isinstance(existing_chunk_target, int) and existing_chunk_target > 0:
                    resolved_plan_target_chunks = existing_chunk_target
                else:
                    resolved_plan_target_chunks = 1
            orchestrator_cfg_plan["coordination"]["plan_target_chunks"] = resolved_plan_target_chunks

            if _disable_evaluation_criteria_generation_for_planning(orchestrator_cfg_plan["coordination"]):
                logger.info("[Plan Mode] Disabled evaluation criteria generation for planning turn")
            if _set_planning_checklist_criteria_defaults(orchestrator_cfg_plan["coordination"]):
                logger.info("[Plan Mode] Defaulted checklist_criteria_preset=planning")

            logger.info(
                "[Plan Mode] Enabled with depth=%s, target_steps=%s, target_chunks=%s, broadcast=%s",
                args.plan_depth,
                getattr(args, "plan_steps", None),
                resolved_plan_target_chunks,
                orchestrator_cfg_plan["coordination"].get("broadcast"),
            )

        # Apply CLI mode flags (--quick, --coordination-mode, --personas, --single-agent)
        apply_mode_flags_to_config(config, args)

        # Handle --eval-criteria: load JSON file and inject into coordination config
        if getattr(args, "eval_criteria", None):
            criteria = _load_eval_criteria(args.eval_criteria)
            _inject_eval_criteria_into_config(config, criteria)
            logger.info(
                "[CLI] Injected %d eval criteria from %s",
                len(criteria),
                args.eval_criteria,
            )

        # Handle --checklist-criteria-preset: inject preset into coordination config
        if getattr(args, "checklist_criteria_preset", None):
            _inject_checklist_criteria_preset_into_config(config, args.checklist_criteria_preset)
            logger.info(
                "[CLI] Set checklist_criteria_preset=%s",
                args.checklist_criteria_preset,
            )

        # Check for prompt in config if not provided via CLI
        if not args.question and "prompt" in config:
            args.question = config["prompt"]
            logger.info(f"Using prompt from config file: {args.question}")

        # Get rate limiting flag from CLI
        enable_rate_limit = args.rate_limit

        # Create agents
        if args.debug:
            logger.debug("Creating agents from config...")
            logger.debug(f"Rate limiting enabled: {enable_rate_limit}")
        # Extract orchestrator config for agent setup
        orchestrator_cfg = config.get("orchestrator", {})

        # Check if any agent has cwd (filesystem support) and validate orchestrator config
        agent_entries = [config["agent"]] if "agent" in config else config.get("agents", [])
        has_cwd = any("cwd" in agent.get("backend", {}) for agent in agent_entries)

        if has_cwd:
            if not orchestrator_cfg:
                raise ConfigurationError(
                    "Agents with 'cwd' (filesystem support) require orchestrator configuration.\n"
                    "Please add an 'orchestrator' section to your config file.\n\n"
                    "Example (customize paths as needed):\n"
                    "orchestrator:\n"
                    '  snapshot_storage: "your_snapshot_dir"\n'
                    '  agent_temporary_workspace: "your_temp_dir"',
                )

            # Check for required fields in orchestrator config
            if "snapshot_storage" not in orchestrator_cfg:
                raise ConfigurationError(
                    "Missing 'snapshot_storage' in orchestrator configuration.\n"
                    "This is required for agents with filesystem support (cwd).\n\n"
                    "Add to your orchestrator section:\n"
                    '  snapshot_storage: "your_snapshot_dir"  # Directory for workspace snapshots',
                )

            if "agent_temporary_workspace" not in orchestrator_cfg:
                raise ConfigurationError(
                    "Missing 'agent_temporary_workspace' in orchestrator configuration.\n"
                    "This is required for agents with filesystem support (cwd).\n\n"
                    "Add to your orchestrator section:\n"
                    '  agent_temporary_workspace: "your_temp_dir"  # Directory for temporary agent workspaces',
                )

        # Create unified session ID for memory system (before creating agents)
        # This ensures memory is isolated per session and unifies orchestrator + memory sessions
        memory_session_id = None
        restore_existing_session = False  # Flag to indicate if we should restore session data

        # Determine model name for metadata (used in session registration and kwargs)
        model_name = None
        if "agent" in config:
            model_name = config["agent"].get("backend", {}).get("model")
        elif "agents" in config and config["agents"]:
            model_name = config["agents"][0].get("backend", {}).get("model")

        # Priority order: CLI arg > config file > generate new
        if args.session_id:
            # Use session_id from CLI argument (already validated) - RESTORE existing
            memory_session_id = args.session_id
            restore_existing_session = True
            logger.info(f"📚 Using session from CLI: {memory_session_id}")
        elif "session_id" in config:
            # Use session_id from YAML config - RESTORE existing
            memory_session_id = config["session_id"]
            restore_existing_session = True
            logger.info(f"📚 Using session from config: {memory_session_id}")
        else:
            # Generate new session for both interactive and single-question modes - DON'T restore
            from datetime import datetime

            memory_session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            restore_existing_session = False
            mode = "single-question" if args.question else "interactive"
            logger.info(f"📝 Created session for {mode} mode: {memory_session_id}")

            # Write session_id sentinel for parent process discovery.
            # Subprocess cwd is the workspace (set via cwd= in manager.py),
            # so this writes to {workspace}/.massgen/.session_id.
            _sentinel_dir = Path(".massgen")
            _sentinel_dir.mkdir(parents=True, exist_ok=True)
            (Path(".massgen") / ".session_id").write_text(memory_session_id)

            # Register new session immediately (before first turn runs)
            # Get log directory for session metadata
            from massgen.logger_config import get_log_session_dir, get_log_session_root
            from massgen.session import SessionRegistry

            log_dir = get_log_session_root()
            log_dir_name = log_dir.name

            # Print LOG_DIR for automation mode (LLM agents need this to monitor progress)
            # LOG_DIR is the main session directory, STATUS includes turn/attempt subdirectory
            if args.automation:
                full_log_dir = get_log_session_dir()
                _automation_print(f"LOG_DIR: {Path(log_dir).resolve()}")
                _automation_print(f"STATUS: {Path(full_log_dir).resolve() / 'status.json'}")

            # Only register in global session registry if not suppressed (e.g., subagent runs)
            if not getattr(args, "no_session_registry", False):
                registry = SessionRegistry()

                # Auto-detect subagent sessions by session_id prefix
                is_subagent = memory_session_id.startswith("subagent_")

                registry.register_session(
                    session_id=memory_session_id,
                    config_path=str(resolved_path) if resolved_path else None,
                    model=model_name,
                    log_directory=log_dir_name,
                    subagent=is_subagent,  # Label subagent sessions
                )
                logger.info(
                    f"📝 Registered {'subagent' if is_subagent else 'new'} session in registry: {memory_session_id}",
                )
            else:
                logger.debug(
                    f"📝 Skipping session registry (--no-session-registry): {memory_session_id}",
                )

        # Parse @references from prompt BEFORE creating agents
        # This allows context_paths to be set up before FilesystemManager initialization
        if args.question:
            args.question, config = inject_prompt_context_paths(
                args.question,
                config,
                parse_at_references=getattr(args, "parse_at_references", True),
            )
            # Update orchestrator_cfg with any new context_paths
            orchestrator_cfg = config.get("orchestrator", {})

        # Textual mode handles plan/spec prompt prefixes from mode state at turn time.
        # For non-textual displays, keep CLI-side prefixing behavior.
        is_textual_display = ui_config.get("display_type") == "textual_terminal"

        # Prepend task planning instructions if --plan mode is active
        if args.question and getattr(args, "plan", False) and not is_textual_display:
            plan_depth = getattr(args, "plan_depth", "dynamic")
            plan_target_steps = getattr(args, "plan_steps", None)
            plan_target_chunks = getattr(args, "plan_chunks", None)
            # Check if subagents are enabled in config
            coordination_cfg = config.get("orchestrator", {}).get("coordination", {})
            enable_subagents = coordination_cfg.get("enable_subagents", False)
            if plan_target_steps is None:
                cfg_steps = coordination_cfg.get("plan_target_steps")
                if isinstance(cfg_steps, int) and cfg_steps > 0:
                    plan_target_steps = cfg_steps
            if plan_target_chunks is None:
                cfg_chunks = coordination_cfg.get("plan_target_chunks")
                if isinstance(cfg_chunks, int) and cfg_chunks > 0:
                    plan_target_chunks = cfg_chunks
            if plan_target_chunks is None:
                plan_target_chunks = 1

            # Broadcast mode priority: CLI arg > config > default false
            cli_broadcast = getattr(args, "broadcast", None)
            if cli_broadcast == "false":
                broadcast_mode = False
            elif cli_broadcast is not None:
                broadcast_mode = cli_broadcast
            else:
                broadcast_mode = coordination_cfg.get("broadcast", False)

            plan_thoroughness = getattr(args, "plan_thoroughness", "standard")
            planning_prefix = get_task_planning_prompt_prefix(
                plan_depth,
                target_steps=plan_target_steps,
                target_chunks=plan_target_chunks,
                enable_subagents=enable_subagents,
                broadcast_mode=broadcast_mode,
                thoroughness=plan_thoroughness,
            )
            args.question = planning_prefix + args.question
            logger.info(
                f"[Plan Mode] Prepended task planning instructions (depth={plan_depth}, thoroughness={plan_thoroughness}, "
                f"target_steps={plan_target_steps}, target_chunks={plan_target_chunks}, "
                f"subagents={enable_subagents}, broadcast={broadcast_mode})",
            )

        # Prepend spec creation instructions if --spec mode is active
        if args.question and getattr(args, "spec", False) and not getattr(args, "plan", False) and not is_textual_display:
            coordination_cfg = config.get("orchestrator", {}).get("coordination", {})
            plan_target_chunks = getattr(args, "plan_chunks", None)
            if plan_target_chunks is None:
                cfg_chunks = coordination_cfg.get("plan_target_chunks")
                if isinstance(cfg_chunks, int) and cfg_chunks > 0:
                    plan_target_chunks = cfg_chunks
            if plan_target_chunks is None:
                plan_target_chunks = 1

            # Broadcast mode priority: CLI arg > config > default false
            cli_broadcast = getattr(args, "broadcast", None)
            if cli_broadcast == "false":
                broadcast_mode = False
            elif cli_broadcast is not None:
                broadcast_mode = cli_broadcast
            else:
                broadcast_mode = coordination_cfg.get("broadcast", False)

            spec_prefix = get_spec_creation_prompt_prefix(
                broadcast_mode=broadcast_mode,
                target_chunks=plan_target_chunks,
            )
            args.question = spec_prefix + args.question
            logger.info(
                f"[Spec Mode] Prepended spec creation instructions " f"(target_chunks={plan_target_chunks}, broadcast={broadcast_mode})",
            )

        # For interactive mode without initial question, defer agent creation until first prompt
        # This allows @path references in the first prompt to be included in Docker mounts
        is_interactive_without_question = not args.question and not getattr(
            args,
            "interactive_with_initial_question",
            None,
        )

        if is_interactive_without_question:
            # Defer agent creation - will be done in run_interactive_mode after first prompt
            agents = None
        else:
            agents = create_agents_from_config(
                config,
                orchestrator_cfg,
                enable_rate_limit=enable_rate_limit,
                config_path=str(resolved_path) if resolved_path else None,
                memory_session_id=memory_session_id,
                debug=args.debug,
                # Session mount support for multi-turn Docker (pre-mount session dir)
                filesystem_session_id=memory_session_id,
                session_storage_base=SESSION_STORAGE,
            )

            if not agents:
                raise ConfigurationError("No agents configured")

            # Apply --single-agent filtering
            if getattr(args, "single_agent", None) is not None:
                try:
                    agents = filter_agents_for_single_mode(agents, args.single_agent)
                    logger.info(f"[CLI] Single-agent mode: using agent '{next(iter(agents.keys()))}'")
                except ValueError as e:
                    print(f"❌ {e}")
                    sys.exit(EXIT_CONFIG_ERROR)

        if args.debug and agents:
            logger.debug(f"Created {len(agents)} agent(s): {list(agents.keys())}")

        # Create timeout config from settings and put it in kwargs
        timeout_settings = config.get("timeout_settings", {})
        timeout_config = _parse_timeout_config(timeout_settings)

        kwargs = {
            "timeout_config": timeout_config,
            "model_name": model_name,  # For session registration
            "config_path": (str(resolved_path) if resolved_path else None),  # For session registration
        }

        # Add orchestrator configuration if present
        if "orchestrator" in config:
            kwargs["orchestrator"] = config["orchestrator"]

        # Add raw agent configs for subtask parsing in decomposition mode
        if "agents" in config:
            kwargs["agents_config"] = config["agents"]
        elif "agent" in config:
            kwargs["agents_config"] = [config["agent"]]

        # Pass raw config dict for checkpoint subprocess config generation
        kwargs["raw_config"] = config

        # Add rate limit flag to kwargs for interactive mode
        kwargs["enable_rate_limit"] = enable_rate_limit
        kwargs["parse_at_references"] = getattr(args, "parse_at_references", True)

        # Add output file if specified
        if args.output_file:
            kwargs["output_file"] = args.output_file

        # Seed Textual Ctrl+P CWD mode when explicitly requested via CLI.
        if args.cwd_context:
            kwargs["cwd_context_mode"] = args.cwd_context

        # Pass CLI mode defaults to TUI for initial mode bar state
        cli_mode_defaults = build_cli_mode_defaults(args)
        if cli_mode_defaults:
            kwargs["cli_mode_defaults"] = cli_mode_defaults

        # Optionally enable DSPy paraphrasing
        dspy_paraphraser = create_dspy_paraphraser_from_config(
            config,
            config_path=str(resolved_path) if resolved_path else None,
        )
        if dspy_paraphraser:
            kwargs["dspy_paraphraser"] = dspy_paraphraser

        # Save execution metadata for debugging and reconstruction
        if args.question:
            # For single question mode, save metadata now (use raw config to avoid logging secrets)
            save_execution_metadata(
                query=args.question,
                config_path=(str(resolved_path) if args.config and "resolved_path" in locals() else None),
                config_content=raw_config_for_metadata,
                cli_args=vars(args),
            )

        # Handle step mode: run one agent for one step, then exit
        if getattr(args, "step", False):
            from ..agent_config import StepModeConfig
            from ..step_mode import (
                save_step_mode_output,
                validate_step_mode_args,
                validate_step_mode_config,
            )

            try:
                validate_step_mode_args(args)
                validate_step_mode_config(config)
            except ValueError as e:
                print(f"❌ Step mode validation error: {e}")
                sys.exit(1)

            # Step mode implies automation
            args.automation = True
            ui_config["display_type"] = "silent"
            ui_config["logging_enabled"] = True
            ui_config["automation_mode"] = True

            step_config = StepModeConfig(enabled=True, session_dir=args.session_dir)

            if not args.question:
                print("❌ --step requires a question/task")
                sys.exit(1)

            _automation_print(f"SESSION_DIR: {Path(args.session_dir).resolve()}")

            # Create agents (same as normal single-question mode)
            orchestrator_cfg = config.get("orchestrator", {})
            agents = create_agents_from_config(
                config,
                orchestrator_cfg,
                memory_session_id=memory_session_id,
            )

            # Build orchestrator config (mirrors the normal path)
            orchestrator_config = AgentConfig()
            timeout_settings = config.get("timeout_settings", {})
            orchestrator_config.timeout_config = _parse_timeout_config(timeout_settings)
            _apply_orchestrator_runtime_params(orchestrator_config, orchestrator_cfg)
            if "coordination" in orchestrator_cfg:
                orchestrator_config.coordination_config = _parse_coordination_config(
                    orchestrator_cfg["coordination"],
                )

            snapshot_storage = _scope_snapshot_storage(orchestrator_cfg.get("snapshot_storage"))
            agent_temporary_workspace = _scope_agent_temporary_workspace(
                orchestrator_cfg.get("agent_temporary_workspace"),
            )

            # Create orchestrator with step mode
            orchestrator = Orchestrator(
                agents=agents,
                config=orchestrator_config,
                session_id=memory_session_id,
                snapshot_storage=snapshot_storage,
                agent_temporary_workspace=agent_temporary_workspace,
                step_mode=step_config,
                raw_config=kwargs.get("raw_config"),
            )

            # Build UI and run question
            ui = _build_coordination_ui(ui_config)
            orchestrator.coordination_ui = ui

            import time as _time

            _step_start = _time.monotonic()

            async for chunk in orchestrator.chat(
                [{"role": "user", "content": args.question}],
            ):
                pass  # Stream through silently in automation mode

            _step_duration = _time.monotonic() - _step_start

            # Save step output
            if orchestrator._step_action_data:
                action_data = orchestrator._step_action_data
                real_agent_id = list(agents.keys())[0]

                # Get seen_steps for votes
                seen_steps = None
                if action_data["action"] == "vote":
                    from ..step_mode import load_session_dir_inputs

                    inputs = load_session_dir_inputs(args.session_dir)
                    seen_steps = {}
                    for va_id, va_state in inputs.virtual_agents.items():
                        if va_state.latest_answer_step is not None:
                            seen_steps[va_id] = va_state.latest_answer_step

                save_step_mode_output(
                    session_dir=args.session_dir,
                    agent_id=real_agent_id,
                    action=action_data["action"],
                    answer_text=action_data.get("answer_text"),
                    vote_target=action_data.get("vote_target"),
                    vote_reason=action_data.get("vote_reason"),
                    seen_steps=seen_steps,
                    duration_seconds=_step_duration,
                    workspace_source=action_data.get("workspace_path"),
                    stale_workspace_paths=action_data.get("stale_workspace_paths"),
                )

                # Save post-coordination artifacts (final/, coordination_events.json, etc.)
                from massgen.logger_config import get_log_session_dir

                log_session_dir = get_log_session_dir()
                if log_session_dir:
                    orchestrator.finalize_step_mode(log_session_dir)

                _automation_print(f"ACTION: {action_data['action']}")
                _automation_print(f"STATUS: {Path(args.session_dir).resolve() / 'agents' / real_agent_id / 'last_action.json'}")
            else:
                print("❌ Step mode: agent did not produce an answer or vote", file=sys.stderr)
                sys.exit(2)

            sys.exit(0)

        # Handle plan-and-execute mode
        if getattr(args, "plan_and_execute", False):
            if not args.question:
                print("❌ --plan-and-execute requires a question/task to plan and execute")
                sys.exit(1)

            from rich.console import Console
            from rich.panel import Panel

            # Default broadcast to "false" for plan-and-execute (batch workflow)
            # "human" broadcast is not supported because planning runs as subprocess with piped I/O
            broadcast = getattr(args, "broadcast", None)
            if broadcast == "human":
                print("❌ --broadcast human is not currently supported with --plan-and-execute")
                print("   Planning runs as a subprocess and cannot receive human input.")
                print("")
                print("   For human interaction, run planning and execution separately:")
                print('     1. uv run massgen --plan --broadcast human "your task"')
                print("     2. uv run massgen --execute-plan latest")
                print("")
                print("   Or use --broadcast false (default) or --broadcast agents for autonomous mode.")
                sys.exit(1)
            if broadcast is None:
                broadcast = "false"

            final_answer, plan_session = await run_plan_and_execute(
                config=config,
                question=args.question,
                plan_depth=getattr(args, "plan_depth", "dynamic") or "dynamic",
                plan_thoroughness=getattr(args, "plan_thoroughness", "standard") or "standard",
                plan_target_steps=getattr(args, "plan_steps", None),
                plan_target_chunks=getattr(args, "plan_chunks", None),
                broadcast_mode=broadcast,
                automation=args.automation,
                debug=args.debug,
                config_path=str(resolved_path) if resolved_path else None,
            )

            # Print results
            if not args.automation:
                console = Console()
                console.print(Panel(final_answer, title="Final Answer", border_style="green"))

            # Write output file if specified
            if args.output_file:
                output_path = Path(args.output_file)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(final_answer)
                _automation_print(f"OUTPUT_FILE: {output_path.resolve()}")

            # Print plan location for automation mode
            if args.automation:
                _automation_print(f"PLAN_DIR: {plan_session.plan_dir}")
                _automation_print(f"PLAN_ID: {plan_session.plan_id}")

            sys.exit(0)

        # Handle --execute-plan mode (execute existing plan without planning phase)
        if getattr(args, "execute_plan", None):
            from rich.console import Console
            from rich.panel import Panel

            try:
                final_answer, plan_session = await run_execute_plan(
                    config=config,
                    plan_path=args.execute_plan,
                    question=args.question,  # Optional override
                    automation=args.automation,
                )

                # Print results
                if not args.automation:
                    console = Console()
                    console.print(Panel(final_answer, title="Final Answer", border_style="green"))

                # Write output file if specified
                if args.output_file:
                    output_path = Path(args.output_file)
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(final_answer)
                    _automation_print(f"OUTPUT_FILE: {output_path.resolve()}")

                # Print plan location for automation mode
                if args.automation:
                    _automation_print(f"PLAN_DIR: {plan_session.plan_dir}")
                    _automation_print(f"PLAN_ID: {plan_session.plan_id}")

                sys.exit(0)

            except FileNotFoundError as e:
                print(f"❌ {e}")
                sys.exit(1)

        # Handle --execute-spec mode (execute existing spec without spec creation phase)
        if getattr(args, "execute_spec", None):
            from rich.console import Console
            from rich.panel import Panel

            try:
                final_answer, plan_session = await run_execute_spec(
                    config=config,
                    spec_path=args.execute_spec,
                    question=args.question,  # Optional override
                    automation=args.automation,
                )

                # Print results
                if not args.automation:
                    console = Console()
                    console.print(Panel(final_answer, title="Final Answer", border_style="green"))

                # Write output file if specified
                if args.output_file:
                    output_path = Path(args.output_file)
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(final_answer)
                    _automation_print(f"OUTPUT_FILE: {output_path.resolve()}")

                # Print spec location for automation mode
                if args.automation:
                    _automation_print(f"SPEC_DIR: {plan_session.plan_dir}")
                    _automation_print(f"SPEC_ID: {plan_session.plan_id}")

                sys.exit(0)

            except FileNotFoundError as e:
                print(f"❌ {e}")
                sys.exit(1)

        # Run mode based on whether question was provided
        try:
            # Check if using textual display - textual always uses interactive mode
            # with question as initial_question (textual doesn't support single-question mode)
            is_textual_display = ui_config.get("display_type") == "textual_terminal"

            if args.question and not is_textual_display:
                await run_single_question(
                    args.question,
                    agents,
                    ui_config,
                    session_id=memory_session_id,
                    restore_session_if_exists=restore_existing_session,
                    **kwargs,
                )

                # Print FINAL_DIR for automation mode (allows plan-and-execute to capture workspace)
                if args.automation:
                    try:
                        from massgen.logger_config import get_log_session_dir

                        final_dir = get_log_session_dir() / "final"
                        if final_dir.exists():
                            _automation_print(f"FINAL_DIR: {final_dir}")
                    except Exception:
                        pass  # Log paths not available
            else:
                # Pass the config path and session_id to interactive mode
                config_file_path = str(resolved_path) if args.config and resolved_path else None
                # Check if we have an initial question from config builder or CLI arg (for textual mode)
                initial_q = getattr(args, "interactive_with_initial_question", None)
                # For textual display, use args.question as initial_question if provided
                if is_textual_display and args.question:
                    initial_q = args.question
                # Remove config_path and enable_rate_limit from kwargs to avoid duplicate argument
                interactive_kwargs = {k: v for k, v in kwargs.items() if k not in ("config_path", "enable_rate_limit")}
                await run_interactive_mode(
                    agents,
                    ui_config,
                    original_config=config,
                    orchestrator_cfg=orchestrator_cfg,
                    config_path=config_file_path,
                    memory_session_id=memory_session_id,
                    initial_question=initial_q,
                    restore_session_if_exists=restore_existing_session,
                    debug=args.debug,
                    raw_config_for_metadata=raw_config_for_metadata,
                    enable_rate_limit=enable_rate_limit,
                    session_storage_base=SESSION_STORAGE,
                    **interactive_kwargs,
                )
        finally:
            # Mark ALL sessions as completed
            if memory_session_id:
                from massgen.session import SessionRegistry

                registry = SessionRegistry()
                registry.complete_session(memory_session_id)
                if args.debug:
                    logger.debug(f"Marked session as completed: {memory_session_id}")

            # Cleanup all agents' filesystem managers (including Docker containers)
            # Note: agents may be None if deferred creation was used but no prompt was entered
            if agents:
                agents_with_docker = [
                    (agent_id, agent)
                    for agent_id, agent in agents.items()
                    if hasattr(agent, "backend")
                    and hasattr(agent.backend, "filesystem_manager")
                    and agent.backend.filesystem_manager
                    and hasattr(agent.backend.filesystem_manager, "docker_manager")
                    and agent.backend.filesystem_manager.docker_manager
                ]

                if agents_with_docker:
                    # Show spinner while cleaning up Docker containers in parallel
                    from concurrent.futures import ThreadPoolExecutor, as_completed

                    from rich.status import Status

                    def cleanup_agent(
                        agent_id: str,
                        agent,
                    ) -> tuple[str, Exception | None]:
                        """Cleanup a single agent's Docker container."""
                        try:
                            agent.backend.filesystem_manager.cleanup()
                            return (agent_id, None)
                        except Exception as e:
                            return (agent_id, e)

                    with Status(
                        f"[bold cyan]Cleaning up {len(agents_with_docker)} Docker container(s)...",
                        spinner="dots",
                    ):
                        with ThreadPoolExecutor(
                            max_workers=len(agents_with_docker),
                        ) as executor:
                            futures = {
                                executor.submit(
                                    cleanup_agent,
                                    agent_id,
                                    agent,
                                ): agent_id
                                for agent_id, agent in agents_with_docker
                            }
                            for future in as_completed(futures):
                                agent_id, error = future.result()
                                if error:
                                    logger.warning(
                                        f"[CLI] Cleanup failed for agent {agent_id}: {error}",
                                    )

                    print("✅ Docker cleanup complete", flush=True)

                # Cleanup non-Docker filesystem managers (quick, no spinner needed)
                for agent_id, agent in agents.items():
                    if (agent_id, agent) not in agents_with_docker:
                        if hasattr(agent, "backend") and hasattr(
                            agent.backend,
                            "filesystem_manager",
                        ):
                            if agent.backend.filesystem_manager:
                                try:
                                    agent.backend.filesystem_manager.cleanup()
                                except Exception as e:
                                    logger.warning(
                                        f"[CLI] Cleanup failed for agent {agent_id}: {e}",
                                    )

    except SystemExit as e:
        exit_code = getattr(e, "code", EXIT_EXECUTION_ERROR)
        if exit_code not in (None, 0):
            _save_prompt_metadata_failure_fallback(
                "system_exit",
                failure_error=SystemExit(exit_code),
            )
        raise
    except ConfigurationError as e:
        print(f"❌ Configuration error: {e}", file=sys.stderr, flush=True)
        _save_prompt_metadata_failure_fallback("configuration_error", failure_error=e)
        sys.exit(EXIT_CONFIG_ERROR)
    except KeyboardInterrupt:
        # Show spinner while cleaning up
        from rich.console import Console as RichConsole
        from rich.status import Status

        rich_console = RichConsole()
        rich_console.print("\n[yellow]Cancelling...[/yellow]")

        # Cleanup agents if they exist
        if "agents" in locals() and agents:
            agents_with_docker = [
                (agent_id, agent)
                for agent_id, agent in agents.items()
                if hasattr(agent, "backend")
                and hasattr(agent.backend, "filesystem_manager")
                and agent.backend.filesystem_manager
                and hasattr(agent.backend.filesystem_manager, "docker_manager")
                and agent.backend.filesystem_manager.docker_manager
            ]

            if agents_with_docker:
                from concurrent.futures import ThreadPoolExecutor, as_completed

                def cleanup_agent(
                    agent_id: str,
                    agent,
                ) -> tuple[str, Exception | None]:
                    try:
                        agent.backend.filesystem_manager.cleanup()
                        return (agent_id, None)
                    except Exception as e:
                        return (agent_id, e)

                with Status("[bold cyan]Cleaning up...[/bold cyan]", spinner="dots"):
                    with ThreadPoolExecutor(
                        max_workers=len(agents_with_docker),
                    ) as executor:
                        futures = {executor.submit(cleanup_agent, agent_id, agent): agent_id for agent_id, agent in agents_with_docker}
                        for future in as_completed(futures):
                            pass  # Just wait for completion

        # Cleanup MCP servers → terminates subagent processes
        if "agents" in locals() and agents:
            for agent_id, agent in agents.items():
                if hasattr(agent, "backend") and hasattr(agent.backend, "cleanup_mcp"):
                    try:
                        await agent.backend.cleanup_mcp()
                    except Exception:
                        pass

        rich_console.print("[green]👋 Goodbye![/green]")
        _save_prompt_metadata_failure_fallback("keyboard_interrupt")
        sys.exit(EXIT_INTERRUPTED)
    except TimeoutError as e:
        print(f"❌ Timeout error: {e}", flush=True)
        _save_prompt_metadata_failure_fallback("timeout_error", failure_error=e)
        sys.exit(EXIT_TIMEOUT)
    except Exception as e:
        print(f"❌ Error: {e}", flush=True)
        _save_prompt_metadata_failure_fallback("execution_error", failure_error=e)
        sys.exit(EXIT_EXECUTION_ERROR)


def cli_main():
    """Synchronous wrapper for CLI entry point."""
    # Handle 'viewer' subcommand — view a session in the TUI (read-only)
    if len(sys.argv) >= 2 and sys.argv[1] == "viewer":
        from ..viewer import build_viewer_parser, viewer_command

        viewer_parser = build_viewer_parser()
        viewer_args = viewer_parser.parse_args(sys.argv[2:])
        sys.exit(viewer_command(viewer_args))

    # Handle 'logs' subcommand specially before main argument parsing
    # This avoids conflict with the positional 'question' argument
    if len(sys.argv) >= 2 and sys.argv[1] == "logs":
        from ..logs_analyzer import logs_command

        # Create a separate parser just for logs subcommand
        logs_parser = argparse.ArgumentParser(
            prog="massgen logs",
            description="Analyze and display MassGen run logs",
        )
        logs_subparsers = logs_parser.add_subparsers(
            dest="logs_command",
            help="Log analysis commands",
        )

        # logs summary (default)
        summary_parser = logs_subparsers.add_parser(
            "summary",
            help="Display run summary (default)",
        )
        summary_parser.add_argument(
            "--log-dir",
            type=str,
            help="Path to specific log directory",
        )
        summary_parser.add_argument(
            "--json",
            action="store_true",
            help="Output as JSON",
        )

        # logs tools
        tools_parser = logs_subparsers.add_parser(
            "tools",
            help="Display tool breakdown",
        )
        tools_parser.add_argument(
            "--sort",
            choices=["time", "calls"],
            default="time",
            help="Sort by time or calls",
        )
        tools_parser.add_argument(
            "--log-dir",
            type=str,
            help="Path to specific log directory",
        )
        tools_parser.add_argument("--json", action="store_true", help="Output as JSON")

        # logs list
        list_parser = logs_subparsers.add_parser("list", help="List recent runs")
        list_parser.add_argument(
            "--limit",
            type=int,
            default=10,
            help="Number of runs to show",
        )
        list_parser.add_argument(
            "--analyzed",
            action="store_true",
            help="Show only logs with ANALYSIS_REPORT.md",
        )
        list_parser.add_argument(
            "--unanalyzed",
            action="store_true",
            help="Show only logs without ANALYSIS_REPORT.md",
        )
        list_parser.add_argument("--json", action="store_true", help="Output as JSON")

        # logs open
        open_parser = logs_subparsers.add_parser(
            "open",
            help="Open log directory in file manager",
        )
        open_parser.add_argument(
            "--log-dir",
            type=str,
            help="Path to specific log directory",
        )

        # logs analyze
        analyze_parser = logs_subparsers.add_parser(
            "analyze",
            help="Generate analysis prompt or run self-analysis",
        )
        analyze_parser.add_argument(
            "--log-dir",
            type=str,
            help="Path to specific log directory (default: latest)",
        )
        analyze_parser.add_argument(
            "--mode",
            choices=["prompt", "self"],
            default="prompt",
            help="Analysis mode: prompt (for Claude Code) or self (multi-agent)",
        )
        analyze_parser.add_argument(
            "--config",
            type=str,
            help="Custom config file for self-analysis mode",
        )
        analyze_parser.add_argument(
            "--ui",
            choices=["automation", "rich_terminal", "webui"],
            default="rich_terminal",
            help="UI mode for self-analysis: rich_terminal (default), automation (headless), or webui",
        )
        analyze_parser.add_argument(
            "--turn",
            "-t",
            type=int,
            help="Specific turn number to analyze (default: latest turn)",
        )
        analyze_parser.add_argument(
            "--force",
            "-f",
            action="store_true",
            help="Overwrite existing report without prompting",
        )

        # Parse logs arguments (skip 'massgen logs')
        logs_args = logs_parser.parse_args(sys.argv[2:])
        sys.exit(logs_command(logs_args))

    # Handle 'serve' subcommand (OpenAI-compatible HTTP server)
    if len(sys.argv) >= 2 and sys.argv[1] == "serve":
        import uvicorn

        from massgen.server.app import create_app
        from massgen.server.settings import ServerSettings

        serve_parser = argparse.ArgumentParser(
            prog="massgen serve",
            description="Run MassGen OpenAI-compatible server (FastAPI + Uvicorn)",
        )
        serve_parser.add_argument(
            "--host",
            type=str,
            default=None,
            help="Host to bind (default: 0.0.0.0)",
        )
        serve_parser.add_argument(
            "--port",
            type=int,
            default=None,
            help="Port to bind (default: 4000)",
        )
        serve_parser.add_argument(
            "--config",
            type=str,
            default=None,
            help="Default MassGen config file path",
        )
        serve_parser.add_argument(
            "--reload",
            action="store_true",
            help="Enable auto-reload (dev only)",
        )

        serve_args = serve_parser.parse_args(sys.argv[2:])

        # Reload env in case the user expects serve to pick up .env changes.
        load_env_file()

        # Resolve config path using same logic as main command
        # If --config provided, use it; otherwise auto-discover default config
        resolved_config = None
        try:
            if serve_args.config:
                resolved_config = resolve_config_path(serve_args.config)
            else:
                # Auto-discover: .massgen/config.yaml or ~/.config/massgen/config.yaml
                resolved_config = resolve_config_path(None)
                if resolved_config:
                    print(f"📁 Using default config: {resolved_config}")
        except ConfigurationError as e:
            print(f"❌ Configuration error: {e}", file=sys.stderr, flush=True)
            sys.exit(EXIT_CONFIG_ERROR)

        # Build settings from env, then apply CLI overrides using replace()
        # to preserve any future env-derived fields
        from dataclasses import replace

        settings = ServerSettings.from_env()
        overrides = {}
        if serve_args.host:
            overrides["host"] = serve_args.host
        if serve_args.port:
            overrides["port"] = serve_args.port
        if resolved_config:
            overrides["default_config"] = str(resolved_config)
        if overrides:
            settings = replace(settings, **overrides)

        app = create_app(settings=settings)
        uvicorn.run(
            app,
            host=settings.host,
            port=settings.port,
            reload=serve_args.reload,
        )
        return

    # Handle 'export' subcommand specially before main argument parsing
    if len(sys.argv) >= 2 and sys.argv[1] == "export":
        from ..session_exporter import export_command

        export_parser = argparse.ArgumentParser(
            prog="massgen export",
            description="Share MassGen session via GitHub Gist (requires gh CLI)",
        )
        export_parser.add_argument(
            "log_dir",
            nargs="?",
            help="Log directory to export (default: latest). Can be full path or log name.",
        )
        export_parser.add_argument(
            "--turns",
            "-t",
            default="all",
            help='Turn range to export: "all", "N" (turns 1-N), "N-M", or "latest" (default: all)',
        )
        export_parser.add_argument(
            "--no-workspace",
            action="store_true",
            help="Exclude workspace artifacts from export",
        )
        export_parser.add_argument(
            "--workspace-limit",
            default="500KB",
            help="Max workspace size per agent (e.g., 500KB, 1MB). Default: 500KB",
        )
        export_parser.add_argument(
            "--yes",
            "-y",
            action="store_true",
            help="Skip interactive prompts and use defaults",
        )
        export_parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be shared without creating gist",
        )
        export_parser.add_argument(
            "--verbose",
            "-v",
            action="store_true",
            help="Show detailed file listing",
        )
        export_parser.add_argument(
            "--json",
            action="store_true",
            help="Output result as JSON (useful for scripting)",
        )

        export_args = export_parser.parse_args(sys.argv[2:])
        sys.exit(export_command(export_args))

    # Handle 'shares' subcommand for managing shared sessions
    if len(sys.argv) >= 2 and sys.argv[1] == "shares":
        from rich.console import Console

        from ..share import delete_share, list_shares

        shares_parser = argparse.ArgumentParser(
            prog="massgen shares",
            description="Manage shared MassGen sessions",
        )
        shares_subparsers = shares_parser.add_subparsers(dest="shares_command")

        # massgen shares list
        shares_subparsers.add_parser("list", help="List your shared sessions")

        # massgen shares delete <gist_id>
        delete_parser = shares_subparsers.add_parser(
            "delete",
            help="Delete a shared session",
        )
        delete_parser.add_argument("gist_id", help="Gist ID to delete")

        shares_args = shares_parser.parse_args(sys.argv[2:])
        console = Console()

        if shares_args.shares_command == "list":
            sys.exit(list_shares(console))
        elif shares_args.shares_command == "delete":
            sys.exit(delete_share(shares_args.gist_id, console))
        else:
            shares_parser.print_help()
            sys.exit(1)

    parser = main_parser()
    args = parser.parse_args()

    if args.plan_steps is not None and args.plan_steps <= 0:
        print("❌ --plan-steps must be a positive integer")
        sys.exit(2)
    if args.plan_chunks is not None and args.plan_chunks <= 0:
        print("❌ --plan-chunks must be a positive integer")
        sys.exit(2)

    # Validate mode flag combinations
    mode_errors = validate_mode_flag_combinations(args)
    if mode_errors:
        for err in mode_errors:
            print(f"❌ {err}")
        sys.exit(2)

    # Continue with the rest of cli_main() logic
    _cli_main_continued(args)


def main_parser() -> argparse.ArgumentParser:
    """Build and return the main CLI argument parser.

    Extracted so tests can parse arguments without running cli_main().
    """
    from massgen.backend.capabilities import get_all_backend_types

    parser = argparse.ArgumentParser(
        description="MassGen - Multi-Agent Coordination CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use configuration file
  massgen --config config.yaml "What is machine learning?"

  # Quick single agent setup
  massgen --backend openai --model gpt-4o-mini "Explain quantum computing"
  massgen --backend claude --model claude-sonnet-4-20250514 "Analyze this data"

  # Use ChatCompletion backend with custom base URL
  massgen --backend chatcompletion --model gpt-oss-120b --base-url https://api.cerebras.ai/v1/chat/completions "What is 2+2?"

  # Interactive mode
  massgen --config config.yaml
  massgen  # Uses default config if available

  # Timeout control examples
  massgen --config config.yaml --orchestrator-timeout 600 "Complex task"

  # Enable rate limiting (uses limits from rate_limits.yaml)
  massgen --config config.yaml --rate-limit "Your question"

  # Configuration management
  massgen --init          # Create new configuration interactively
  massgen --select        # Choose from available configurations
  massgen --setup         # Set up API keys
  massgen --list-examples # View example configurations

Environment Variables:
    OPENAI_API_KEY      - Required for OpenAI backend
    XAI_API_KEY         - Required for Grok backend
    ANTHROPIC_API_KEY   - Required for Claude backend
    GOOGLE_API_KEY      - Required for Gemini backend (or GEMINI_API_KEY)
    ZAI_API_KEY         - Required for ZAI backend

    CEREBRAS_API_KEY    - For Cerebras AI (cerebras.ai)
    TOGETHER_API_KEY    - For Together AI (together.ai, together.xyz)
    FIREWORKS_API_KEY   - For Fireworks AI (fireworks.ai)
    GROQ_API_KEY        - For Groq (groq.com)
    NEBIUS_API_KEY      - For Nebius AI Studio (studio.nebius.ai)
    OPENROUTER_API_KEY  - For OpenRouter (openrouter.ai)
    POE_API_KEY         - For POE (poe.com)

  Note: The chatcompletion backend auto-detects the provider from the base_url
        and uses the appropriate environment variable for API key.
        """,
    )

    # Question (optional for interactive mode)
    parser.add_argument(
        "question",
        nargs="?",
        help="Question to ask (optional - if not provided, enters interactive mode)",
    )

    # Configuration options
    config_group = parser.add_mutually_exclusive_group()
    config_group.add_argument(
        "--config",
        type=str,
        help=(
            "Path to YAML/JSON configuration file or @examples/NAME. With "
            "interactive --quickstart, this is used as the output filename under "
            ".massgen/. With --quickstart --headless, this is used as the exact "
            "output config path."
        ),
    )
    config_group.add_argument(
        "--select",
        action="store_true",
        help="Interactively select from available configurations",
    )
    config_group.add_argument(
        "--backend",
        type=str,
        choices=sorted(get_all_backend_types()),
        help="Backend type for quick setup",
    )

    # Quick setup options
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model name for quick setup",
    )
    parser.add_argument(
        "--system-message",
        type=str,
        help="System message for quick setup",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        help="Base URL for API endpoint (e.g., https://api.cerebras.ai/v1/chat/completions)",
    )

    # UI options
    parser.add_argument(
        "--no-display",
        action="store_true",
        help="Disable visual coordination display",
    )
    parser.add_argument(
        "--display",
        type=str,
        choices=["rich", "textual"],
        default=None,
        help="Display type: textual (default, recommended TUI), rich (legacy)",
    )
    parser.add_argument(
        "--textual-serve",
        action="store_true",
        help="Serve Textual TUI in browser via textual-serve (http://localhost:8000)",
    )
    parser.add_argument(
        "--textual-serve-port",
        type=int,
        default=8000,
        help="Port for textual-serve (default: 8000)",
    )
    parser.add_argument("--no-logs", action="store_true", help="Disable logging")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode with verbose logging",
    )
    parser.add_argument(
        "--save-streaming-buffers",
        action="store_true",
        help="Save streaming buffers to files in streaming_buffers/ directory (works with all backends)",
    )
    parser.add_argument(
        "--logfire",
        action="store_true",
        help="Enable Logfire observability for structured tracing of LLM calls, tool executions, and orchestration",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Launch web UI server for real-time visualization",
    )
    parser.add_argument(
        "--web-quickstart",
        action="store_true",
        help="Launch a temporary browser-based setup + quickstart flow that exits automatically when complete",
    )
    parser.add_argument(
        "--web-port",
        type=int,
        default=8000,
        help="Port for web UI server (default: 8000)",
    )
    parser.add_argument(
        "--web-host",
        type=str,
        default="127.0.0.1",
        help="Host for web UI server (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't auto-open browser when using --web with a question",
    )
    parser.add_argument(
        "--web-review",
        action="store_true",
        default=False,
        help="Enable change review modal in WebUI for approving/rejecting git diffs (requires --web)",
    )
    parser.add_argument(
        "--automation",
        action="store_true",
        help="Enable automation mode: silent output (~10 lines), status.json tracking, meaningful exit codes. "
        "REQUIRED for LLM agents and background execution. Automatically isolates workspaces for parallel runs.",
    )
    parser.add_argument(
        "--step",
        action="store_true",
        default=False,
        help="Step mode: run one agent for one step (new_answer or vote), then exit. " "Config must define exactly one agent. Prior answers loaded from --session-dir.",
    )
    parser.add_argument(
        "--session-dir",
        type=str,
        default=None,
        help="Session directory for step mode. Contains agents/{id}/{step}/answer.json inputs " "and receives step outputs. Used with --step.",
    )
    parser.add_argument(
        "--stream-events",
        action="store_true",
        help="Stream events to stdout as JSON lines. Used by parent processes (e.g., TUI subagent modal) " "to receive real-time updates. Implies --automation.",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Task planning mode. Agents interactively create structured feature lists and planning documents. "
        "Use --cwd-context to include current directory context and enable user questions via ask_others.",
    )
    parser.add_argument(
        "--cwd-context",
        choices=["ro", "rw", "read", "write"],
        help="Add current working directory to context paths. " "Use ro/read for read-only or rw/write for write permission.",
    )
    parser.add_argument(
        "--plan-depth",
        choices=["dynamic", "shallow", "medium", "deep"],
        default="dynamic",
        help="Plan granularity for --plan mode: dynamic (scope-adaptive), shallow (5-10 tasks), " "medium (20-50 tasks), deep (100-200+ tasks). Default: dynamic.",
    )
    parser.add_argument(
        "--plan-thoroughness",
        choices=["standard", "thorough"],
        default="standard",
        help="Strategic reasoning depth for --plan mode: standard (reasonable justification), "
        "thorough (deep strategic reasoning, anti-patterns, risk analysis, design principles). "
        "Orthogonal to --plan-depth which controls task count. Default: standard.",
    )
    parser.add_argument(
        "--plan-steps",
        type=int,
        default=None,
        help="Optional explicit planning target for task count (for example 30). Omit for dynamic sizing.",
    )
    parser.add_argument(
        "--plan-chunks",
        type=int,
        default=None,
        help="Optional explicit planning target for chunk count (for example 5). Default in plan mode: 1 chunk.",
    )
    parser.add_argument(
        "--broadcast",
        choices=["human", "agents", "false"],
        default=None,
        help="Broadcast mode for --plan mode: 'human' (agents ask critical questions), 'agents' (agents debate), 'false' (fully autonomous). "
        "If not specified, uses config file value or defaults to 'false'.",
    )
    parser.add_argument(
        "--plan-and-execute",
        action="store_true",
        help="Run full plan-and-execute workflow: agents create plan (Phase 1), then automatically execute it (Phase 2). "
        "Combines --plan with automatic execution. Plan stored in .massgen/plans/ for validation and adherence tracking.",
    )
    parser.add_argument(
        "--execute-plan",
        type=str,
        metavar="PLAN_PATH",
        help="Execute an existing plan. Provide the plan directory path (e.g., .massgen/plans/plan_20260115_173113_836955) "
        "or plan ID (e.g., 20260115_173113_836955) or 'latest' for most recent plan. "
        "Skips planning phase and runs execution directly from the frozen plan.",
    )
    parser.add_argument(
        "--spec",
        action="store_true",
        help="Spec creation mode. Agents produce a requirements specification (EARS notation) instead of a task plan. "
        "Output is project_spec.json with requirements, verification criteria, and chunked execution phases.",
    )
    parser.add_argument(
        "--execute-spec",
        type=str,
        metavar="SPEC_PATH",
        help="Execute against an existing spec. Provide the spec directory path, spec ID, or 'latest' for most recent spec session. "
        "Skips spec creation phase and runs execution directly from the frozen spec.",
    )
    parser.add_argument(
        "--no-session-registry",
        action="store_true",
        help="Don't register this session in the global session registry. Used for internal subagent runs.",
    )
    parser.add_argument(
        "--no-parse-at-references",
        action="store_false",
        dest="parse_at_references",
        help="Treat @tokens in prompt text as plain text instead of extracting @path/@path:w context references.",
    )
    parser.add_argument(
        "--eval-criteria",
        type=str,
        metavar="FILE",
        help="Path to JSON file with evaluation criteria. "
        "Each entry: {text, category (primary/standard/stretch), anti_patterns?, verify_by?}. "
        "Also accepts 'description' or 'name' as aliases for 'text'. "
        "Injected as checklist_criteria_inline in coordination config.",
    )
    parser.add_argument(
        "--checklist-criteria-preset",
        type=str,
        metavar="PRESET",
        help="Use a built-in criteria preset (e.g., planning, evaluation, persona, " "decomposition, prompt, analysis, spec). Overrides YAML checklist_criteria_preset.",
    )
    parser.add_argument(
        "--output-file",
        type=str,
        metavar="PATH",
        help="Write final answer to specified file path. Works in any mode (automation, interactive, etc.)",
    )
    parser.add_argument(
        "--skip-agent-selector",
        action="store_true",
        help="Skip the Agent Selector interface at the end (useful for terminal recordings/automation). " "MassGen will exit immediately after showing the final answer.",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Launch interactive configuration builder to create config file",
    )
    parser.add_argument(
        "--quickstart",
        action="store_true",
        help="Quick setup: specify number of agents/models, get a full-featured config with code tools and Docker, and optionally install skill packages",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Non-interactive mode for --quickstart: auto-detect API keys, "
        "select best backend/model, generate config, pull Docker images, "
        "and install skills. Designed for programmatic use by AI agents.",
    )
    parser.add_argument(
        "--generate-config",
        type=str,
        metavar="PATH",
        help="Generate config file at specified path (non-interactive, requires --config-backend and --config-model)",
    )
    parser.add_argument(
        "--config-agents",
        type=int,
        default=None,
        help="Number of agents for --generate-config or --quickstart --headless (default: 1)",
    )
    parser.add_argument(
        "--config-backend",
        type=str,
        help="Backend provider for --generate-config (e.g., 'openai', 'anthropic', 'gemini')",
    )
    parser.add_argument(
        "--config-model",
        type=str,
        help="Model name for --generate-config (e.g., 'gpt-5', 'claude-sonnet-4', 'gemini-2.5-pro')",
    )
    parser.add_argument(
        "--config-agent-id",
        type=str,
        help="Explicit agent id for single-agent --generate-config or --quickstart --headless runs",
    )
    parser.add_argument(
        "--config-docker",
        action="store_true",
        help="Enable Docker execution mode in generated config",
    )
    parser.add_argument(
        "--config-context-path",
        type=str,
        help="Add context path to generated config",
    )
    parser.add_argument(
        "--quickstart-agent",
        action="append",
        dest="quickstart_agents",
        help="Explicit headless quickstart agent spec. Repeat for mixed providers, e.g. " "--quickstart-agent id=agent_a,backend=claude,model=claude-opus-4-6",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Launch interactive API key setup wizard to configure credentials",
    )
    parser.add_argument(
        "--setup-skills",
        action="store_true",
        help="Install skills (openskills CLI, Anthropic/OpenAI/Vercel collections, Agent Browser skill, Remotion, Crawl4AI)",
    )
    parser.add_argument(
        "--setup-docker",
        action="store_true",
        help="Interactively select and pull MassGen Docker executor images (sudo image recommended by default)",
    )
    parser.add_argument(
        "--list-backends",
        action="store_true",
        help="List all supported backends with models, capabilities, and auth requirements",
    )
    parser.add_argument(
        "--list-examples",
        action="store_true",
        help="List available example configurations from package",
    )
    parser.add_argument(
        "--example",
        type=str,
        help="Print example config to stdout (e.g., --example basic_multi)",
    )
    parser.add_argument(
        "--show-schema",
        action="store_true",
        help="Display configuration schema and available parameters",
    )
    parser.add_argument(
        "--schema-backend",
        type=str,
        help="Show schema for specific backend (use with --show-schema)",
    )
    parser.add_argument(
        "--with-examples",
        action="store_true",
        help="Include example configurations in schema display",
    )
    parser.add_argument(
        "--validate",
        type=str,
        metavar="CONFIG_FILE",
        help="Validate a configuration file without running it",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors during validation (use with --validate)",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Output validation results in JSON format (use with --validate)",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip automatic config validation when loading config files",
    )
    parser.add_argument(
        "--strict-validation",
        action="store_true",
        help="Treat config warnings as errors and abort execution",
    )

    # Session options
    session_group = parser.add_argument_group(
        "session management",
        "Load or list memory sessions",
    )
    session_group.add_argument(
        "--session-id",
        type=str,
        help="Load memory from a previous session by ID (e.g., chat_session_a1b2c3d4)",
    )
    session_group.add_argument(
        "--continue",
        action="store_true",
        dest="continue_session",
        help="Continue the most recent session (shortcut for loading last session)",
    )
    session_group.add_argument(
        "--list-sessions",
        action="store_true",
        help="List recent memory sessions (default: 10 most recent)",
    )
    session_group.add_argument(
        "--all",
        action="store_true",
        dest="list_all_sessions",
        help="Show all sessions (use with --list-sessions for detailed view)",
    )

    # Timeout options
    timeout_group = parser.add_argument_group(
        "timeout settings",
        "Override timeout settings from config",
    )
    timeout_group.add_argument(
        "--orchestrator-timeout",
        type=int,
        help="Maximum time for orchestrator coordination in seconds (default: 1800)",
    )

    # Rate limit options
    parser.add_argument(
        "--rate-limit",
        action="store_true",
        help="Enable rate limiting (uses limits from rate_limits.yaml config)",
    )

    # Mode settings (mirror TUI mode bar toggles)
    add_mode_flags_to_parser(parser)

    return parser


def _cli_main_continued(args):
    """Continuation of cli_main() after argument parsing.

    This is split out because main_parser() was extracted between the parser
    construction and the post-parse logic. This function is called from cli_main().
    """
    # Handle --continue flag BEFORE setup_logging so we can reuse log directory
    if args.continue_session:
        from massgen.session import SessionRegistry

        registry = SessionRegistry()
        # Use get_most_recent_continuable_session to skip empty sessions
        recent_session = registry.get_most_recent_continuable_session()
        if not recent_session:
            print("❌ No continuable sessions found (all sessions are empty)")
            print("Run 'massgen --list-sessions' to see available sessions")
            sys.exit(1)
        args.session_id = recent_session["session_id"]
        print(f"🔄 Continuing most recent session: {args.session_id}")

    # Restore log directory from session if loading existing session
    if args.session_id:
        from massgen.logger_config import set_log_base_session_dir
        from massgen.session import SessionRegistry

        registry = SessionRegistry()
        if not registry.session_exists(args.session_id):
            print(
                f"❌ Session error: Session '{args.session_id}' not found in registry",
            )
            print("Run 'massgen --list-sessions' to see available sessions")
            sys.exit(1)

        session_metadata = registry.get_session(args.session_id)
        log_directory = session_metadata.get("log_directory")
        if log_directory:
            # Reuse the original log directory for this session
            set_log_base_session_dir(log_directory)
            print(f"📚 Loading session: {args.session_id} (log: {log_directory})")

        # Restore config from session if not explicitly provided
        session_config_path = session_metadata.get("config_path")
        if args.config and session_config_path:
            # Resolve both paths to compare actual files (handles @examples aliases)
            current_resolved = resolve_config_path(args.config)
            session_resolved = Path(session_config_path).resolve() if session_config_path else None

            if current_resolved and session_resolved and current_resolved.resolve() != session_resolved:
                # User is overriding with a different config - warn them
                print("⚠️  Warning: Using different config than original session")
                print(f"   Original: {session_config_path}")
                print(f"   Current:  {args.config}")
        elif not args.config and session_config_path:
            # Automatically load config from session
            args.config = session_config_path
            print(f"📄 Using config from session: {session_config_path}")

    # Handle special commands first (before logging setup to avoid creating log dirs)
    # Note: 'logs' subcommand is handled at the very start of cli_main()

    if args.list_sessions:
        from massgen.session import SessionRegistry, format_session_list

        registry = SessionRegistry()
        # Show all sessions if --all flag is provided, otherwise show recent 10
        limit = None if args.list_all_sessions else 10
        sessions = registry.list_sessions(limit=limit)
        print(format_session_list(sessions, show_all=args.list_all_sessions))
        return

    if args.validate:
        from ..config_validator import ConfigValidator

        validator = ConfigValidator()
        result = validator.validate_config_file(args.validate)

        # Output results
        if args.json_output:
            # JSON output for machine parsing
            print(json.dumps(result.to_dict(), indent=2))
        else:
            # Human-readable output
            print(result.format_all())

        # Exit with appropriate code
        if not result.is_valid() or (args.strict and result.has_warnings()):
            sys.exit(1)
        sys.exit(0)

    if args.list_backends:
        _print_backends_table()
        return

    if args.list_examples:
        show_available_examples()
        return

    if args.example:
        print_example_config(args.example)
        return

    if args.show_schema:
        from ..schema_display import show_schema

        show_schema(backend=args.schema_backend, show_examples=args.with_examples)
        return

    # Setup logging for all other commands (actual execution, setup, init, etc.)
    setup_logging(debug=args.debug)

    # Configure Logfire observability if requested
    if args.logfire:
        _setup_logfire_observability()

    if args.debug:
        logger.info("Debug mode enabled")
        logger.debug(f"Command line arguments: {vars(args)}")

    quickstart_config_filename = _quickstart_filename_from_config_arg(args.config) if args.quickstart else None
    headless_quickstart_output_path = _headless_quickstart_output_path_from_config_arg(args.config) if args.quickstart else None

    def _run_quickstart_wizard_tui(config_filename: str | None = None):
        """Launch quickstart wizard TUI. Returns result dict or None."""
        try:
            from textual.app import App as _QApp

            from ..frontend.displays.textual_widgets import (
                QuickstartWizard,
                WizardCancelled,
                WizardCompleted,
            )

            class _QuickstartWizardApp(_QApp):
                CSS_PATH = Path(__file__).parent / "frontend" / "displays" / "textual_themes" / "dark.tcss"
                BINDINGS = [("ctrl+c", "quit", "Quit")]

                def __init__(self, quickstart_config_filename: str | None = None):
                    super().__init__(css_path=str(self.CSS_PATH))
                    self._wizard_result = None
                    self._quickstart_config_filename = quickstart_config_filename

                def on_mount(self):
                    self.push_screen(
                        QuickstartWizard(config_filename=self._quickstart_config_filename),
                    )

                def on_wizard_completed(self, message: WizardCompleted) -> None:
                    self._wizard_result = message.result
                    self.exit(message.result)

                def on_wizard_cancelled(self, message: WizardCancelled) -> None:
                    self.exit(None)

                def action_quit(self) -> None:
                    self.exit(None)

                def on_key(self, event) -> None:
                    if event.key == "escape" and len(self.screen_stack) <= 1:
                        self.exit(None)

            app = _QuickstartWizardApp(
                quickstart_config_filename=config_filename,
            )
            return app.run()
        except ImportError as e:
            logger.warning(f"TUI not available for quickstart wizard: {e}")
            return None

    def _handle_quickstart_result(result):
        """Handle quickstart wizard result - launch web/terminal or save only. Returns True if handled."""
        if not result:
            print(f"\n{BRIGHT_YELLOW}⚠️  Quickstart cancelled{RESET}")
            return True

        config_path = result.get("config_path")
        question = result.get("question", "")
        launch_option = result.get("launch_option", "save_only")
        install_skills_now = result.get("install_skills_now", True)

        if config_path:
            _ensure_quickstart_skills_ready(config_path, bool(install_skills_now))

        if config_path and launch_option == "web":
            try:
                from ..frontend.web import run_server

                prompt_question = question if question else None
                print(f"{BRIGHT_CYAN}🌐 Starting MassGen Web UI...{RESET}")
                print(f"{BRIGHT_GREEN}   Server: http://{args.web_host}:{args.web_port}{RESET}")
                print(f"{BRIGHT_GREEN}   Config: {config_path}{RESET}")

                auto_url = None
                if prompt_question:
                    import urllib.parse

                    prompt_encoded = urllib.parse.quote(prompt_question)
                    auto_url = f"http://{args.web_host}:{args.web_port}/?prompt={prompt_encoded}"
                    config_encoded = urllib.parse.quote(config_path)
                    auto_url += f"&config={config_encoded}"
                    print(f"{BRIGHT_GREEN}   Auto-launch URL: {auto_url}{RESET}")

                print(f"{BRIGHT_YELLOW}   Press Ctrl+C to stop{RESET}\n")

                browser_url = auto_url if auto_url else f"http://{args.web_host}:{args.web_port}/"

                def open_browser():
                    import time

                    time.sleep(0.5)
                    webbrowser.open(browser_url)

                threading.Thread(target=open_browser, daemon=True).start()
                run_server(
                    host=args.web_host,
                    port=args.web_port,
                    config_path=config_path,
                    automation_mode=False,
                )
            except ImportError as e:
                print(f"{BRIGHT_RED}❌ Web UI dependencies not installed.{RESET}")
                print(f"{BRIGHT_CYAN}   Run: pip install massgen{RESET}")
                logger.debug(f"Import error: {e}")
                sys.exit(1)
            return True
        elif config_path and launch_option == "terminal":
            args.config = config_path
            args.display = "textual"
            if question:
                args.interactive_with_initial_question = question
            args.question = None
            return False  # Continue with normal flow
        elif config_path:
            print(f"\n{BRIGHT_GREEN}✅ Configuration saved to: {config_path}{RESET}")
            print(f'{BRIGHT_CYAN}Run with: massgen --config {config_path} "Your question"{RESET}')
            return True
        else:
            return True

    # Launch interactive API key setup if requested
    # Skip terminal setup if --web is also provided (web UI will handle setup)
    if args.setup and not args.web:
        # Launch TUI Setup Wizard
        try:
            from textual.app import App

            from ..frontend.displays.textual_widgets import (
                SetupWizard,
                WizardCancelled,
                WizardCompleted,
            )

            class SetupWizardApp(App):
                """Standalone app for setup wizard."""

                CSS_PATH = Path(__file__).parent / "frontend" / "displays" / "textual_themes" / "dark.tcss"
                SCREENS = {"wizard": SetupWizard}
                BINDINGS = [("ctrl+c", "quit", "Quit")]

                def __init__(self):
                    super().__init__(css_path=str(self.CSS_PATH))
                    self._wizard_result = None

                def on_mount(self):
                    self.push_screen("wizard")

                def on_wizard_completed(self, message: WizardCompleted) -> None:
                    """Handle wizard completion."""
                    self._wizard_result = message.result
                    self.exit(message.result)

                def on_wizard_cancelled(self, message: WizardCancelled) -> None:
                    """Handle wizard cancellation - exit immediately."""
                    self.exit(None)

                def action_quit(self) -> None:
                    self.exit(None)

                def on_key(self, event) -> None:
                    if event.key == "escape" and len(self.screen_stack) <= 1:
                        self.exit(None)

            app = SetupWizardApp()
            result = app.run()

            if result and result.get("success"):
                print(f"\n{BRIGHT_GREEN}✅ API key setup complete!{RESET}")
                configured = result.get("configured_providers", [])
                if configured:
                    print(f"{BRIGHT_CYAN}💡 Configured providers: {', '.join(configured)}{RESET}")

                if result.get("launch_quickstart"):
                    qs_result = _run_quickstart_wizard_tui()
                    if not _handle_quickstart_result(qs_result):
                        pass  # Terminal launch - fall through to normal flow
                    else:
                        return
                else:
                    print(f"{BRIGHT_CYAN}💡 Run 'massgen --quickstart' to create a config and start.{RESET}\n")
            else:
                print(f"\n{BRIGHT_YELLOW}⚠️  Setup cancelled or no changes made{RESET}")
                print(f"{BRIGHT_CYAN}💡 You can run 'massgen --setup' anytime to configure API keys{RESET}\n")

        except ImportError as e:
            logger.warning(f"TUI not available, falling back to CLI setup: {e}")
            # Fallback to CLI-based setup
            builder = ConfigBuilder()
            api_keys = builder.interactive_api_key_setup()

            if any(api_keys.values()):
                print(f"\n{BRIGHT_GREEN}✅ API key setup complete!{RESET}")
                print(f"{BRIGHT_CYAN}💡 You can now use MassGen with these providers{RESET}\n")
            else:
                print(f"\n{BRIGHT_YELLOW}⚠️  No API keys configured{RESET}")
                print(f"{BRIGHT_CYAN}💡 You can run 'massgen --setup' anytime to set them up{RESET}\n")

        return

    # Install skills if requested
    if args.setup_skills:
        from ..utils.skills_installer import install_skills

        install_skills()
        return

    # Setup Docker images if requested
    if args.setup_docker:
        setup_docker()
        return

    # Launch textual-serve to serve TUI in browser
    if args.textual_serve:
        try:
            from textual_serve.server import Server
        except ImportError:
            print(f"{BRIGHT_RED}❌ textual-serve not installed.{RESET}")
            print(f"{BRIGHT_CYAN}   Run: uv pip install textual-serve{RESET}")
            sys.exit(1)

        # Build the massgen command to run inside textual-serve
        cmd_parts = ["massgen", "--display", "textual"]
        if hasattr(args, "config") and args.config:
            cmd_parts.extend(["--config", args.config])
        if hasattr(args, "interactive") and args.interactive:
            cmd_parts.append("--interactive")
        if hasattr(args, "question") and args.question:
            cmd_parts.append(f'"{args.question}"')

        cmd = " ".join(cmd_parts)
        port = args.textual_serve_port

        print(f"{BRIGHT_CYAN}🌐 Starting MassGen Textual TUI Server...{RESET}")
        print(f"{BRIGHT_GREEN}   URL: http://localhost:{port}{RESET}")
        print(f"{BRIGHT_GREEN}   Command: {cmd}{RESET}")
        print(f"{BRIGHT_YELLOW}   Press Ctrl+C to stop{RESET}\n")

        server = Server(cmd, port=port)
        server.serve()
        return

    if args.web_quickstart:
        try:
            from ..frontend.web.server import run_temporary_quickstart_server

            print(f"{BRIGHT_CYAN}🌐 Starting MassGen Web Quickstart...{RESET}")
            print(
                f"{BRIGHT_GREEN}   Server: http://{args.web_host}:{args.web_port}/?temporary=1&wizard=open{RESET}",
            )
            print(
                f"{BRIGHT_YELLOW}   This temporary setup session will close automatically when complete{RESET}\n",
            )

            session_result = run_temporary_quickstart_server(
                host=args.web_host,
                port=args.web_port,
                no_browser=getattr(args, "no_browser", False),
            )
            if session_result.get("status") == "completed":
                config_path = session_result.get("config_path")
                if config_path:
                    print(f"{BRIGHT_GREEN}✅ Configuration saved to: {config_path}{RESET}")
                    print(
                        f'{BRIGHT_CYAN}Run with: massgen --config {config_path} "Your question"{RESET}',
                    )
                return

            print(f"{BRIGHT_YELLOW}⚠️  Web quickstart cancelled{RESET}")
            sys.exit(1)
        except ImportError as e:
            print(f"{BRIGHT_RED}❌ Web UI dependencies not installed.{RESET}")
            print(f"{BRIGHT_CYAN}   Run: pip install massgen{RESET}")
            logger.debug(f"Import error: {e}")
            sys.exit(1)

    # Launch web UI server if requested
    if args.web:
        try:
            from ..frontend.web import run_server

            config_path = args.config if hasattr(args, "config") and args.config else None
            question = getattr(args, "question", None)
            automation_mode = getattr(args, "automation", False)

            # Auto-resolve default config (same as main() does)
            if not config_path and automation_mode and question:
                resolved_default = resolve_config_path(None)
                if resolved_default:
                    config_path = str(resolved_default)

            print(f"{BRIGHT_CYAN}🌐 Starting MassGen Web UI...{RESET}")
            print(
                f"{BRIGHT_GREEN}   Server: http://{args.web_host}:{args.web_port}{RESET}",
            )
            if config_path:
                print(f"{BRIGHT_GREEN}   Config: {config_path}{RESET}")
            else:
                print(
                    f"{BRIGHT_YELLOW}   No config specified - use --config or select in UI{RESET}",
                )

            # Build auto-launch URL. V2 is the default UI (no param needed).
            # The frontend auto-starts coordination when both prompt= and config=
            # are in the URL (see App.tsx useEffect at line ~226).
            import urllib.parse

            base_url = f"http://{args.web_host}:{args.web_port}/"
            url_params = []
            if question:
                url_params.append(f"prompt={urllib.parse.quote(question)}")
            if config_path:
                url_params.append(f"config={urllib.parse.quote(config_path)}")
            auto_url = f"{base_url}?{'&'.join(url_params)}" if url_params else base_url
            # Print a short URL for the terminal (no giant prompt)
            short_url_params = []
            if config_path:
                short_url_params.append(f"config={urllib.parse.quote(config_path)}")
            short_url = f"{base_url}?{'&'.join(short_url_params)}" if short_url_params else base_url
            print(f"{BRIGHT_GREEN}   UI: {short_url}{RESET}")

            if automation_mode:
                if question:
                    print(
                        f"{BRIGHT_YELLOW}   Run starting immediately — open browser anytime to monitor{RESET}",
                    )
                else:
                    print(
                        f"{BRIGHT_YELLOW}   No question provided — open the URL above to start a run{RESET}",
                    )

            print(f"{BRIGHT_YELLOW}   Press Ctrl+C to stop{RESET}\n")

            # Auto-open browser (unless --no-browser or automation mode)
            no_browser = getattr(args, "no_browser", False)
            if not no_browser and not automation_mode:
                browser_url = auto_url
                separator = "&" if "?" in browser_url else "?"
                if getattr(args, "setup", False):
                    browser_url += f"{separator}setup=open"
                elif getattr(args, "quickstart", False):
                    browser_url += f"{separator}wizard=open"

                def open_browser():
                    import time

                    time.sleep(0.5)  # Wait for server to start
                    webbrowser.open(browser_url)

                threading.Thread(target=open_browser, daemon=True).start()
            cli_overrides = _build_cli_overrides_dict(args)
            run_server(
                host=args.web_host,
                port=args.web_port,
                config_path=config_path,
                automation_mode=automation_mode,
                cli_overrides=cli_overrides or None,
                question=question if question else None,
            )
        except ImportError as e:
            print(f"{BRIGHT_RED}❌ Web UI dependencies not installed.{RESET}")
            print(f"{BRIGHT_CYAN}   Run: pip install massgen{RESET}")
            logger.debug(f"Import error: {e}")
            sys.exit(1)
        return

    # Launch interactive config selector if requested
    if args.select:
        selected_config = interactive_config_selector()
        if selected_config:
            # Update args to use the selected config
            args.config = selected_config
            # Continue to main() with the selected config
        else:
            # User cancelled selection
            return

    # Generate config programmatically if requested
    if args.generate_config:
        if not args.config_backend or not args.config_model:
            print(
                f"{BRIGHT_RED}❌ Error: --config-backend and --config-model are required with --generate-config{RESET}",
            )
            print(
                f"{BRIGHT_CYAN}Example: massgen --generate-config ./config.yaml --config-backend gemini --config-model gemini-2.5-pro{RESET}",
            )
            return

        try:
            builder = ConfigBuilder()
            success = builder.generate_config_programmatic(
                output_path=args.generate_config,
                num_agents=args.config_agents if args.config_agents is not None else 1,
                backend_type=args.config_backend,
                model=args.config_model,
                use_docker=args.config_docker,
                context_path=args.config_context_path,
                agent_id=args.config_agent_id,
            )
            if success:
                print(
                    f"{BRIGHT_GREEN}✅ Configuration saved to: {args.generate_config}{RESET}",
                )
                print(
                    f'{BRIGHT_CYAN}Run with: massgen --config {args.generate_config} "Your question"{RESET}',
                )
            return
        except ValueError as e:
            print(f"{BRIGHT_RED}❌ Error: {e}{RESET}")
            return
        except Exception as e:
            print(f"{BRIGHT_RED}❌ Unexpected error: {e}{RESET}")
            import traceback

            traceback.print_exc()
            return

    # Launch quickstart if requested
    # Skip terminal quickstart if --web is also provided (web UI will show wizard directly)
    if args.quickstart and not args.web:
        # Headless quickstart: auto-detect keys, generate config, no user interaction.
        # Also triggers when stdin is not a TTY (e.g., piped from an AI agent).
        if args.headless or not sys.stdin.isatty():
            builder = ConfigBuilder()
            quickstart_agent_specs = _parse_quickstart_agent_specs(
                getattr(args, "quickstart_agents", None),
            )
            headless_result = builder.run_quickstart_headless(
                output_dir=".massgen",
                output_path=headless_quickstart_output_path,
                num_agents=args.config_agents if args.config_agents is not None else 1,
                backend_override=args.config_backend,
                model_override=args.config_model,
                use_docker=args.config_docker if args.config_docker else None,
                context_path=args.config_context_path,
                agent_specs=quickstart_agent_specs or None,
                agent_id=args.config_agent_id,
            )

            # Docker pull if available and headless
            if headless_result.get("docker_available") and headless_result.get("success"):
                headless_result["docker_pulled"] = _pull_docker_image_headless()

            _print_headless_quickstart_summary(headless_result)

            # Install skills if config was generated
            if headless_result.get("config_path"):
                _ensure_quickstart_skills_ready(headless_result["config_path"], True)

            return

        # Launch TUI Quickstart Wizard
        try:
            result = _run_quickstart_wizard_tui(quickstart_config_filename)
            if _handle_quickstart_result(result):
                return
            # Terminal launch - fall through to normal flow

        except Exception as e:
            logger.warning(f"TUI not available, falling back to CLI quickstart: {e}")
            # Fallback to CLI-based quickstart
            builder = ConfigBuilder()
            result = builder.run_quickstart(
                quickstart_config_filename=quickstart_config_filename,
            )

            if result and len(result) >= 2:
                filepath = result[0]
                question = result[1]
                interface_choice = result[2] if len(result) >= 3 else "terminal"
                install_skills_now = result[3] if len(result) >= 4 else True

                if filepath:
                    _ensure_quickstart_skills_ready(filepath, bool(install_skills_now))

                if filepath and interface_choice == "web":
                    try:
                        from ..frontend.web import run_server

                        config_path = filepath
                        prompt_question = question if question else None

                        print(f"{BRIGHT_CYAN}🌐 Starting MassGen Web UI...{RESET}")
                        print(f"{BRIGHT_GREEN}   Server: http://{args.web_host}:{args.web_port}{RESET}")
                        print(f"{BRIGHT_GREEN}   Config: {config_path}{RESET}")

                        auto_url = None
                        if prompt_question:
                            import urllib.parse

                            prompt_encoded = urllib.parse.quote(prompt_question)
                            auto_url = f"http://{args.web_host}:{args.web_port}/?prompt={prompt_encoded}"
                            config_encoded = urllib.parse.quote(config_path)
                            auto_url += f"&config={config_encoded}"
                            print(f"{BRIGHT_GREEN}   Auto-launch URL: {auto_url}{RESET}")

                        print(f"{BRIGHT_YELLOW}   Press Ctrl+C to stop{RESET}\n")

                        browser_url = auto_url if auto_url else f"http://{args.web_host}:{args.web_port}/"

                        def open_browser():
                            import time

                            time.sleep(0.5)
                            webbrowser.open(browser_url)

                        threading.Thread(target=open_browser, daemon=True).start()
                        run_server(
                            host=args.web_host,
                            port=args.web_port,
                            config_path=config_path,
                            automation_mode=False,
                        )
                    except ImportError as e:
                        print(f"{BRIGHT_RED}❌ Web UI dependencies not installed.{RESET}")
                        print(f"{BRIGHT_CYAN}   Run: pip install massgen{RESET}")
                        logger.debug(f"Import error: {e}")
                        sys.exit(1)
                    return
                elif filepath and question:
                    args.config = filepath
                    args.question = question
                    args.interactive_with_initial_question = question
                    args.question = None
                elif filepath and question == "":
                    args.config = filepath
                    args.question = None
                elif filepath:
                    print(f"\n✅ Configuration saved to: {filepath}")
                    print(f'Run with: massgen --config {filepath} "Your question"')
                    return
                else:
                    return
            else:
                return

    # Launch interactive config builder if requested
    if args.init:
        builder = ConfigBuilder()
        result = builder.run()

        if result and len(result) == 2:
            filepath, question = result
            if filepath and question:
                # Update args to use the newly created config and launch interactive mode with initial question
                args.config = filepath
                args.question = question
                # Store initial question for interactive mode (don't run single-question mode)
                args.interactive_with_initial_question = question
                args.question = None  # Clear to trigger interactive mode instead of single-question
            elif filepath:
                # Config created but user chose not to run
                print(f"\n✅ Configuration saved to: {filepath}")
                print(f'Run with: massgen --config {filepath} "Your question"')
                return
            else:
                # User cancelled
                return
        else:
            # Builder returned None (cancelled or error)
            return

    # First-run detection: auto-trigger setup wizard → quickstart wizard via TUI
    # Note: If config has a 'prompt' key, it will be used (set above), so args.question will be set
    if not args.question and not args.config and not args.model and not args.backend:
        if should_run_builder():
            # Launch TUI Setup Wizard for first-run experience
            try:
                from textual.app import App as _FirstRunApp

                from ..frontend.displays.textual_widgets import (
                    SetupWizard,
                    WizardCancelled,
                    WizardCompleted,
                )

                class _FirstRunSetupApp(_FirstRunApp):
                    CSS_PATH = Path(__file__).parent / "frontend" / "displays" / "textual_themes" / "dark.tcss"
                    SCREENS = {"wizard": SetupWizard}
                    BINDINGS = [("ctrl+c", "quit", "Quit")]

                    def __init__(self):
                        super().__init__(css_path=str(self.CSS_PATH))
                        self._wizard_result = None

                    def on_mount(self):
                        self.push_screen("wizard")

                    def on_wizard_completed(self, message: WizardCompleted) -> None:
                        self._wizard_result = message.result
                        self.exit(message.result)

                    def on_wizard_cancelled(self, message: WizardCancelled) -> None:
                        self.exit(None)

                    def action_quit(self) -> None:
                        self.exit(None)

                    def on_key(self, event) -> None:
                        if event.key == "escape" and len(self.screen_stack) <= 1:
                            self.exit(None)

                setup_app = _FirstRunSetupApp()
                setup_result = setup_app.run()

                if setup_result and setup_result.get("success"):
                    print(f"\n{BRIGHT_GREEN}✅ API key setup complete!{RESET}")
                    configured = setup_result.get("configured_providers", [])
                    if configured:
                        print(f"{BRIGHT_CYAN}💡 Configured providers: {', '.join(configured)}{RESET}")

                    # Chain into quickstart wizard (auto-launch or if user clicked the button)
                    launch_qs = setup_result.get("launch_quickstart", False)
                    if launch_qs:
                        qs_result = _run_quickstart_wizard_tui()
                        if not _handle_quickstart_result(qs_result):
                            pass  # Terminal launch - fall through to normal flow
                        else:
                            return
                    else:
                        print(f"{BRIGHT_CYAN}💡 Run 'massgen --quickstart' to create a config and start.{RESET}\n")
                        return
                else:
                    print(f"\n{BRIGHT_YELLOW}⚠️  Setup cancelled{RESET}")
                    print(f"{BRIGHT_CYAN}💡 You can run 'massgen --setup' anytime to configure API keys{RESET}\n")
                    return

            except ImportError:
                # Fallback to CLI-based first-run flow
                builder = ConfigBuilder(default_mode=True)
                existing_api_keys = builder.detect_api_keys()
                cloud_providers = ["openai", "anthropic", "gemini", "grok", "azure_openai"]
                has_api_keys = any(existing_api_keys.get(provider, False) for provider in cloud_providers)

                print()
                print(f"{BRIGHT_CYAN}{'=' * 60}{RESET}")
                print(f"{BRIGHT_CYAN}  Welcome to MassGen!{RESET}")
                print(f"{BRIGHT_CYAN}{'=' * 60}{RESET}")
                print()

                if not has_api_keys:
                    print("  Let's first set up your API keys...")
                    print()
                    api_keys = builder.interactive_api_key_setup()
                    if any(api_keys.values()):
                        print(f"\n{BRIGHT_GREEN}✅ API key setup complete!{RESET}\n")
                    else:
                        print(f"\n{BRIGHT_YELLOW}⚠️  No API keys configured{RESET}\n")
                else:
                    print(f"{BRIGHT_GREEN}✅ API keys detected{RESET}\n")

                print()
                result = builder.run_quickstart(
                    quickstart_config_filename=quickstart_config_filename,
                )

                if result and len(result) >= 2:
                    filepath = result[0]
                    question = result[1]
                    interface_choice = result[2] if len(result) >= 3 else "terminal"
                    install_skills_now = result[3] if len(result) >= 4 else True

                    if filepath:
                        _ensure_quickstart_skills_ready(filepath, bool(install_skills_now))

                        # Set the config path
                        args.config = filepath

                        # Check if user chose web interface
                        if interface_choice == "web":
                            try:
                                from ..frontend.web import run_server

                                config_path = filepath
                                prompt_question = question if question else None

                                print(f"{BRIGHT_CYAN}🌐 Starting MassGen Web UI...{RESET}")
                                print(
                                    f"{BRIGHT_GREEN}   Server: http://{args.web_host}:{args.web_port}{RESET}",
                                )
                                print(f"{BRIGHT_GREEN}   Config: {config_path}{RESET}")

                                auto_url = None
                                if prompt_question:
                                    import urllib.parse

                                    prompt_encoded = urllib.parse.quote(prompt_question)
                                    auto_url = f"http://{args.web_host}:{args.web_port}/?prompt={prompt_encoded}"
                                    config_encoded = urllib.parse.quote(config_path)
                                    auto_url += f"&config={config_encoded}"
                                    print(
                                        f"{BRIGHT_GREEN}   Auto-launch URL: {auto_url}{RESET}",
                                    )

                                print(f"{BRIGHT_YELLOW}   Press Ctrl+C to stop{RESET}\n")

                                browser_url = auto_url if auto_url else f"http://{args.web_host}:{args.web_port}/"

                                def open_browser():
                                    import time

                                    time.sleep(0.5)
                                    webbrowser.open(browser_url)

                                threading.Thread(target=open_browser, daemon=True).start()
                                run_server(
                                    host=args.web_host,
                                    port=args.web_port,
                                    config_path=config_path,
                                    automation_mode=False,
                                )
                            except ImportError as e:
                                print(
                                    f"{BRIGHT_RED}❌ Web UI dependencies not installed.{RESET}",
                                )
                                print(f"{BRIGHT_CYAN}   Run: pip install massgen{RESET}")
                                logger.debug(f"Import error: {e}")
                                sys.exit(1)
                            return
                        elif question:
                            args.question = question
                        else:
                            print(
                                f"\n{BRIGHT_GREEN}🚀 Launching interactive mode...{RESET}\n",
                            )
                    else:
                        # No filepath - user cancelled
                        return
                else:
                    # Builder returned None - user cancelled
                    return

    # Now call the async main with the parsed arguments
    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        # User pressed Ctrl+C - exit gracefully without traceback
        _restore_terminal_for_input()
