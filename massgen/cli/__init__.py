"""massgen.cli — command-line interface package.

This package was extracted from the former monolithic ``cli.py``. The facade
below re-exports its surface so ``from massgen.cli import X`` and ``massgen.cli.X``
keep working.

The public API is declared in ``__all__`` (the names callers should rely on).
Underscore-prefixed names are internal helpers; they remain importable from the
package for backwards compatibility but are not part of the public API — prefer
importing those from their specific submodule (e.g.
``from massgen.cli.config_parsing import _parse_coordination_config``).
"""

import sys
from pathlib import Path

# Compatibility re-exports of names the legacy cli.py exposed at module top.
from ..config_builder import ConfigBuilder, normalize_quickstart_config_filename

# --- internal helpers re-exported for backwards compatibility (not public API) ---
# --- public API ---
from ._constants import _MASSGEN_WORKSPACES_PREFIX  # noqa: F401
from ._constants import (
    BOLD,
    BRIGHT_BLUE,
    BRIGHT_CYAN,
    BRIGHT_GREEN,
    BRIGHT_MAGENTA,
    BRIGHT_RED,
    BRIGHT_WHITE,
    BRIGHT_YELLOW,
    EXIT_CONFIG_ERROR,
    EXIT_EXECUTION_ERROR,
    EXIT_INTERRUPTED,
    EXIT_SUCCESS,
    EXIT_TIMEOUT,
    MASSGEN_QUESTIONARY_STYLE,
    RESET,
    SESSION_STORAGE,
)
from .backends import _api_key_error_message  # noqa: F401
from .backends import (
    create_agents_from_config,
    create_backend,
    create_dspy_paraphraser_from_config,
)
from .config_loading import (  # noqa: F401
    ConfigurationError,
    _expand_env_vars,
    _route_workspace_path,
    _scope_agent_temporary_workspace,
    _scope_snapshot_storage,
    _substitute_variables,
    apply_cli_cwd_context_path,
    create_simple_config,
    inject_prompt_context_paths,
    load_config_file,
    relocate_filesystem_paths,
    resolve_config_path,
    validate_context_paths,
)
from .config_parsing import (  # noqa: F401
    _apply_orchestrator_runtime_params,
    _parse_coordination_config,
    _parse_standalone_checkpoint,
    _parse_timeout_config,
)
from .docker_setup import (
    check_docker_available,
    get_docker_diagnostics,
    setup_computer_use_docker,
    setup_docker,
)
from .entrypoint import _cli_main_continued  # noqa: F401
from .entrypoint import cli_main, main, main_parser
from .env import (  # noqa: F401
    _automation_print,
    _setup_logfire_observability,
    load_env_file,
)
from .examples import (  # noqa: F401
    _print_backends_table,
    _select_package_example,
    discover_available_configs,
    interactive_config_selector,
    print_example_config,
    show_available_examples,
    show_example_prompts,
)
from .input import (  # noqa: F401
    _get_prompt_session,
    _restore_terminal_for_input,
    prompt_for_context_paths,
    read_multiline_input,
    read_multiline_input_async,
)
from .inspection import (  # noqa: F401
    _find_log_dir_for_session,
    _list_all_turns,
    _show_turn_inspection,
)
from .mode_flags import _build_cli_overrides_dict  # noqa: F401
from .mode_flags import (
    add_mode_flags_to_parser,
    apply_mode_flags_to_config,
    build_cli_mode_defaults,
    filter_agents_for_single_mode,
    validate_mode_flag_combinations,
)
from .plan_commands import _execute_plan_phase  # noqa: F401
from .plan_commands import (
    resolve_plan_path,
    run_execute_plan,
    run_execute_spec,
    run_plan_and_execute,
)
from .planning import (  # noqa: F401
    _disable_evaluation_criteria_generation_for_planning,
    _inject_checklist_criteria_preset_into_config,
    _inject_eval_criteria_into_config,
    _is_planning_turn,
    _load_eval_criteria,
    _set_planning_checklist_criteria_defaults,
)
from .prompts import (  # noqa: F401
    _format_chunk_target_line,
    _get_log_session_original_query,
    _load_skill_creator_reference,
    build_plan_review_refinement_appendix,
    get_log_analysis_prompt_prefix,
    get_skill_organization_prompt_prefix,
    get_spec_creation_prompt_prefix,
    get_task_planning_prompt_prefix,
    should_include_quick_edit_hint,
)
from .quickstart import (  # noqa: F401
    _ensure_quickstart_skills_ready,
    _headless_quickstart_output_path_from_config_arg,
    _parse_quickstart_agent_specs,
    _print_headless_quickstart_summary,
    _pull_docker_image_headless,
    _quickstart_config_uses_skills,
    _quickstart_filename_from_config_arg,
    should_run_builder,
)
from .run import (  # noqa: F401
    _has_evolving_skills_enabled,
    _should_use_conversation_history_for_turn,
    handle_session_persistence,
    print_help_messages,
    run_interactive_mode,
    run_question_with_history,
    run_single_question,
    run_textual_interactive_mode,
)
from .streaming import (  # noqa: F401
    _build_coordination_ui,
    _setup_event_streaming,
    _setup_timeline_event_recording,
)

# --- module-level side effects from the legacy cli.py (preserved on import) ---
# Add project root to path. __file__ is massgen/cli/__init__.py, one level deeper
# than the old massgen/cli.py, hence one extra ``.parent``.
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Load .env file at package import.
load_env_file()

__all__ = [
    "BOLD",
    "BRIGHT_BLUE",
    "BRIGHT_CYAN",
    "BRIGHT_GREEN",
    "BRIGHT_MAGENTA",
    "BRIGHT_RED",
    "BRIGHT_WHITE",
    "BRIGHT_YELLOW",
    "ConfigBuilder",
    "ConfigurationError",
    "EXIT_CONFIG_ERROR",
    "EXIT_EXECUTION_ERROR",
    "EXIT_INTERRUPTED",
    "EXIT_SUCCESS",
    "EXIT_TIMEOUT",
    "MASSGEN_QUESTIONARY_STYLE",
    "RESET",
    "SESSION_STORAGE",
    "add_mode_flags_to_parser",
    "apply_cli_cwd_context_path",
    "apply_mode_flags_to_config",
    "build_cli_mode_defaults",
    "build_plan_review_refinement_appendix",
    "check_docker_available",
    "cli_main",
    "create_agents_from_config",
    "create_backend",
    "create_dspy_paraphraser_from_config",
    "create_simple_config",
    "discover_available_configs",
    "filter_agents_for_single_mode",
    "get_docker_diagnostics",
    "get_log_analysis_prompt_prefix",
    "get_skill_organization_prompt_prefix",
    "get_spec_creation_prompt_prefix",
    "get_task_planning_prompt_prefix",
    "handle_session_persistence",
    "inject_prompt_context_paths",
    "interactive_config_selector",
    "load_config_file",
    "load_env_file",
    "main",
    "main_parser",
    "normalize_quickstart_config_filename",
    "print_example_config",
    "print_help_messages",
    "prompt_for_context_paths",
    "read_multiline_input",
    "read_multiline_input_async",
    "relocate_filesystem_paths",
    "resolve_config_path",
    "resolve_plan_path",
    "run_execute_plan",
    "run_execute_spec",
    "run_interactive_mode",
    "run_plan_and_execute",
    "run_question_with_history",
    "run_single_question",
    "run_textual_interactive_mode",
    "setup_computer_use_docker",
    "setup_docker",
    "should_include_quick_edit_hint",
    "should_run_builder",
    "show_available_examples",
    "show_example_prompts",
    "validate_context_paths",
    "validate_mode_flag_combinations",
]
