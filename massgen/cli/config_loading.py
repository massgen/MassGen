#!/usr/bin/env python3
"""Config file resolution, loading, env/variable expansion, and context-path wiring.

Part of the massgen.cli package (extracted from the legacy monolithic cli.py).
"""

import copy
import json
import os
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
)

if TYPE_CHECKING:
    pass

import yaml

from ..logger_config import logger

# --- cross-module references within the cli package ---
from ._constants import _MASSGEN_WORKSPACES_PREFIX, BRIGHT_CYAN, BRIGHT_YELLOW, RESET


class ConfigurationError(Exception):
    """Configuration error for CLI."""


def _substitute_variables(obj: Any, variables: dict[str, str]) -> Any:
    """Recursively substitute ${var} references in config with actual values.

    Args:
        obj: Config object (dict, list, str, or other)
        variables: Dict of variable names to values

    Returns:
        Config object with variables substituted
    """
    if isinstance(obj, dict):
        return {k: _substitute_variables(v, variables) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_substitute_variables(item, variables) for item in obj]
    elif isinstance(obj, str):
        # Replace ${var} with value
        result = obj
        for var_name, var_value in variables.items():
            result = result.replace(f"${{{var_name}}}", var_value)
        return result
    else:
        return obj


def _route_workspace_path(cwd: str) -> str:
    """Route relative workspace paths under .massgen/workspaces/.

    Absolute paths are returned unchanged. Paths already under
    .massgen/workspaces/ are not double-prefixed.
    """
    from pathlib import PurePath

    p = PurePath(cwd)
    if p.is_absolute():
        return cwd
    # Don't double-prefix
    normalized = str(p).replace("\\", "/")
    if normalized.startswith(_MASSGEN_WORKSPACES_PREFIX) or normalized.startswith(".massgen/workspaces"):
        return cwd
    return f"{_MASSGEN_WORKSPACES_PREFIX}{cwd}"


def resolve_config_path(config_arg: str | None) -> Path | None:
    """Resolve config file with flexible syntax.

    Priority order:

    **If --config flag provided (highest priority):**
    1. @examples/NAME → Package examples (search configs directory)
    2. Absolute/relative paths (exact path as specified)
    3. Named configs in ~/.config/massgen/agents/

    **If NO --config flag (auto-discovery):**
    1. .massgen/config.yaml (project-level config in current directory)
    2. ~/.config/massgen/config.yaml (global default config)
    3. None → trigger config builder

    Args:
        config_arg: Config argument from --config flag (can be @examples/NAME, path, or None)

    Returns:
        Path to config file, or None if config builder should run

    Raises:
        ConfigurationError: If config file not found
    """
    # Check for default configs if no config_arg provided
    if not config_arg:
        # Priority 1: Project-level config (.massgen/config.yaml in current directory)
        project_config = Path.cwd() / ".massgen" / "config.yaml"
        if project_config.exists():
            return project_config

        # Priority 2: Global default config
        global_config = Path.home() / ".config/massgen/config.yaml"
        if global_config.exists():
            return global_config

        return None  # Trigger builder

    # Handle @examples/ prefix - search in package configs
    if config_arg.startswith("@examples/"):
        name = config_arg[10:]  # Remove '@examples/' prefix
        try:
            from importlib.resources import files

            configs_root = files("massgen") / "configs"

            # Search recursively for matching name
            # Try to find by filename stem match
            for config_file in configs_root.rglob("*.yaml"):
                # Check if name matches the file stem or is contained in the path
                if name in config_file.name or name in str(config_file):
                    return Path(str(config_file))

            raise ConfigurationError(
                f"Config '{config_arg}' not found in package.\n" f"Use --list-examples to see available configs.",
            )
        except Exception as e:
            if isinstance(e, ConfigurationError):
                raise
            raise ConfigurationError(f"Error loading package config: {e}")

    # Try as regular path (absolute or relative)
    path = Path(config_arg).expanduser()
    if path.exists():
        return path

    # Try in user config directory (~/.config/massgen/agents/)
    user_agents_dir = Path.home() / ".config/massgen/agents"
    # Try with config_arg as-is first
    user_config = user_agents_dir / config_arg
    if user_config.exists():
        return user_config

    # Also try with .yaml extension if not provided
    if not config_arg.endswith((".yaml", ".yml")):
        user_config_with_ext = user_agents_dir / f"{config_arg}.yaml"
        if user_config_with_ext.exists():
            return user_config_with_ext
        # For error message, show the path with .yaml extension
        user_config = user_config_with_ext

    # Config not found anywhere
    raise ConfigurationError(
        f"Configuration file not found: {config_arg}\n"
        f"Searched in:\n"
        f"  - Current directory: {Path.cwd() / config_arg}\n"
        f"  - User configs: {user_config}\n"
        f"Use --list-examples to see available package configs.",
    )


def load_config_file(config_path: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load configuration from YAML or JSON file.

    Search order:
    1. Exact path as provided (absolute or relative to CWD)
    2. If just a filename, search in package's configs/ directory
    3. If a relative path, also try within package's configs/ directory

    Supports variable substitution: ${VAR_NAME} in any string will be replaced
    with the value of the VAR_NAME environment variable.

    Returns:
        Tuple of (expanded_config, raw_config) where:
        - expanded_config: Config with ${VAR} replaced by actual env values
        - raw_config: Original config preserving ${VAR} syntax (safe for logging)
    """
    path = Path(config_path)

    # Try the path as-is first (handles absolute paths and relative to CWD)
    if path.exists():
        pass  # Use this path
    elif path.is_absolute():
        # Absolute path that doesn't exist
        raise ConfigurationError(f"Configuration file not found: {config_path}")
    else:
        # Relative path or just filename - search in package configs
        package_configs_dir = Path(__file__).parent / "configs"

        # Try 1: Just the filename in package configs root
        candidate1 = package_configs_dir / path.name
        # Try 2: The full relative path within package configs
        candidate2 = package_configs_dir / path

        if candidate1.exists():
            path = candidate1
        elif candidate2.exists():
            path = candidate2
        else:
            raise ConfigurationError(
                f"Configuration file not found: {config_path}\n" f"Searched in:\n" f"  - {Path.cwd() / config_path}\n" f"  - {candidate1}\n" f"  - {candidate2}",
            )

    try:
        with open(path, encoding="utf-8") as f:
            if path.suffix.lower() in [".yaml", ".yml"]:
                raw_config = yaml.safe_load(f)
            elif path.suffix.lower() == ".json":
                raw_config = json.load(f)
            else:
                raise ConfigurationError(
                    f"Unsupported config file format: {path.suffix}",
                )

            # Return both expanded (for runtime) and raw (for logging)
            expanded_config = _expand_env_vars(copy.deepcopy(raw_config))
            return expanded_config, raw_config
    except Exception as e:
        raise ConfigurationError(f"Error reading config file: {e}")


def _expand_env_vars(config: Any) -> Any:
    """Recursively expand environment variables in config.

    Replaces ${VAR_NAME} with the value of the VAR_NAME environment variable.
    If the variable is not set, leaves the ${VAR_NAME} string as-is.
    """
    import re

    if isinstance(config, dict):
        return {k: _expand_env_vars(v) for k, v in config.items()}
    elif isinstance(config, list):
        return [_expand_env_vars(item) for item in config]
    elif isinstance(config, str):
        # Replace ${VAR} with environment variable value
        pattern = r"\$\{([^}]+)\}"

        def replacer(match):
            var_name = match.group(1)
            return os.getenv(var_name, match.group(0))

        return re.sub(pattern, replacer, config)
    return config


def _scope_snapshot_storage(base: str | None) -> str | None:
    """Scope ``snapshot_storage`` by the current log session root name.

    Two concurrent CLI processes using the same config would otherwise write
    to the same ``.massgen/snapshots/agent_a/`` directory.  Appending the
    microsecond-timestamped session root name keeps them isolated.

    Args:
        base: Raw ``snapshot_storage`` value from YAML config, or None.

    Returns:
        Scoped path string (e.g., ``.massgen/snapshots/log_20260301_XXX``),
        or None if *base* is None.
    """
    if base is None:
        return None
    from pathlib import Path as _Path

    from ..logger_config import get_log_session_root as _get_root

    try:
        session_root_name = _get_root().name
        return str(_Path(base) / session_root_name)
    except Exception:
        return base  # Fallback: return unchanged if session root unavailable


def _scope_agent_temporary_workspace(base: str | None) -> str | None:
    """Scope ``agent_temporary_workspace`` by the current log session root name.

    Two concurrent CLI processes using the same config would otherwise share
    the same temp workspace parent.  Appending the microsecond-timestamped
    session root name keeps them isolated -- process B's
    ``clear_temp_workspace()`` only removes its own scoped subdirectory.

    Args:
        base: Raw ``agent_temporary_workspace`` value from YAML config,
            or None.

    Returns:
        Scoped path string, or None if *base* is None.
    """
    if base is None:
        return None
    from pathlib import Path as _Path

    from ..logger_config import get_log_session_root as _get_root

    try:
        session_root_name = _get_root().name
        return str(_Path(base) / session_root_name)
    except Exception:
        return base  # Fallback: return unchanged if session root unavailable


def create_simple_config(
    backend_type: str,
    model: str,
    system_message: str | None = None,
    base_url: str | None = None,
    ui_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a simple single-agent configuration."""
    backend_config = {"type": backend_type, "model": model}
    if base_url:
        backend_config["base_url"] = base_url

    # Add required workspace configuration for Claude Code backend
    if backend_type == "claude_code":
        backend_config["cwd"] = "workspace"

    # Use provided UI config or default to rich_terminal for CLI usage
    if ui_config is None:
        ui_config = {"display_type": "rich_terminal", "logging_enabled": True}

    config = {
        "agent": {
            "id": "agent1",
            "backend": backend_config,
            "system_message": system_message or "You are a helpful AI assistant.",
        },
        "ui": ui_config,
    }

    # Add orchestrator config with .massgen/ structure for Claude Code
    if backend_type == "claude_code":
        config["orchestrator"] = {
            "snapshot_storage": ".massgen/snapshots",
            "agent_temporary_workspace": ".massgen/temp_workspaces",
            # Note: session_storage is hardcoded to .massgen/sessions (not configurable)
        }

    return config


def apply_cli_cwd_context_path(
    config: dict[str, Any],
    cwd_context_mode: str | None,
) -> None:
    """Apply --cwd-context flag by injecting CWD into orchestrator context paths.

    Args:
        config: MassGen configuration dict (modified in-place).
        cwd_context_mode: CLI mode ("ro"/"read" or "rw"/"write"), or None.
    """
    if not cwd_context_mode:
        return

    mode = cwd_context_mode.lower()
    permission = "write" if mode in ("rw", "write") else "read"
    cwd_path = str(Path.cwd().resolve())

    orchestrator_cfg = config.setdefault("orchestrator", {})
    context_paths = orchestrator_cfg.get("context_paths")
    if not isinstance(context_paths, list):
        context_paths = []
        orchestrator_cfg["context_paths"] = context_paths

    existing_index = None
    for idx, entry in enumerate(context_paths):
        entry_path = entry.get("path") if isinstance(entry, dict) else entry
        if not entry_path:
            continue
        try:
            normalized_entry_path = str(Path(entry_path).resolve())
        except Exception:
            normalized_entry_path = str(entry_path)

        if normalized_entry_path == cwd_path:
            existing_index = idx
            break

    if existing_index is None:
        context_paths.append(
            {
                "path": cwd_path,
                "permission": permission,
            },
        )
        logger.info(
            f"[CLI] Added CWD to context_paths via --cwd-context: {cwd_path} ({permission})",
        )
        return

    existing = context_paths[existing_index]
    if isinstance(existing, dict):
        existing["path"] = cwd_path
        existing["permission"] = permission
    else:
        context_paths[existing_index] = {
            "path": cwd_path,
            "permission": permission,
        }
    logger.info(
        f"[CLI] Updated CWD context path via --cwd-context: {cwd_path} ({permission})",
    )


def validate_context_paths(config: dict[str, Any]) -> None:
    """Validate that all context paths in the config exist.

    Context paths can be either files or directories.
    File-level context paths allow access to specific files without exposing sibling files.
    Raises ConfigurationError with clear message if any paths don't exist.
    """
    orchestrator_cfg = config.get("orchestrator", {})
    context_paths = orchestrator_cfg.get("context_paths", [])

    missing_paths = []

    for context_path_config in context_paths:
        if isinstance(context_path_config, dict):
            path = context_path_config.get("path")
        else:
            # Handle string format for backwards compatibility
            path = context_path_config

        if path:
            path_obj = Path(path)
            if not path_obj.exists():
                missing_paths.append(path)

    if missing_paths:
        errors = ["Context paths not found:"]
        for path in missing_paths:
            errors.append(f"  - {path}")
        errors.append("\nPlease update your configuration with valid paths.")
        raise ConfigurationError("\n".join(errors))


def inject_prompt_context_paths(
    prompt: str,
    config: dict[str, Any],
    parse_at_references: bool = True,
) -> tuple[str, dict[str, Any]]:
    """Parse @references from prompt and inject into config.

    Extracts @path and @path:w references from the prompt, validates that
    the paths exist, and injects them into config["orchestrator"]["context_paths"].

    This displays extracted paths to the user for transparency when parsing is enabled.

    Args:
        prompt: User's raw prompt potentially containing @references.
        config: MassGen configuration dict (modified in-place).
        parse_at_references: Whether to parse @path references from prompt text.

    Returns:
        Tuple of (cleaned_prompt, modified_config).

    Raises:
        ConfigurationError: If any referenced paths don't exist.
    """
    if not parse_at_references:
        return prompt, config

    from ..path_handling import PromptParserError, parse_prompt_for_context

    try:
        parsed = parse_prompt_for_context(prompt)
    except PromptParserError as e:
        raise ConfigurationError(str(e)) from e

    if not parsed.context_paths:
        return prompt, config

    # Display extracted paths to user (always, for transparency)
    print(f"\n{BRIGHT_CYAN}📂 Context paths from prompt:{RESET}")
    for ctx in parsed.context_paths:
        perm_icon = "📝" if ctx["permission"] == "write" else "📖"
        print(f"   {perm_icon} {ctx['path']} ({ctx['permission']})")

    # Show consolidation suggestions
    for suggestion in parsed.suggestions:
        print(f"   {BRIGHT_YELLOW}💡 {suggestion}{RESET}")

    print()

    # Inject into config
    if "orchestrator" not in config:
        config["orchestrator"] = {}
    if "context_paths" not in config["orchestrator"]:
        config["orchestrator"]["context_paths"] = []

    # Add extracted paths (avoiding duplicates)
    existing_paths = {p.get("path") for p in config["orchestrator"]["context_paths"]}
    for ctx in parsed.context_paths:
        if ctx["path"] not in existing_paths:
            config["orchestrator"]["context_paths"].append(ctx)
            existing_paths.add(ctx["path"])
        else:
            # If path exists but with different permission, upgrade to write if needed
            for existing in config["orchestrator"]["context_paths"]:
                if existing.get("path") == ctx["path"] and ctx["permission"] == "write":
                    existing["permission"] = "write"
                    break

    return parsed.cleaned_prompt, config


def relocate_filesystem_paths(config: dict[str, Any]) -> None:
    """Relocate filesystem paths (orchestrator paths and agent workspaces) to be under .massgen/ directory.

    Modifies the config in-place to ensure all MassGen state is organized
    under .massgen/ for clean project structure.
    """
    massgen_dir = Path(".massgen")

    # Relocate orchestrator paths
    orchestrator_cfg = config.get("orchestrator", {})
    if orchestrator_cfg:
        path_fields = [
            "snapshot_storage",
            "agent_temporary_workspace",
            # Note: session_storage is not in this list - it's hardcoded to .massgen/sessions
            # Old configs with session_storage are backwards compatible (value is ignored)
        ]

        for field in path_fields:
            if field in orchestrator_cfg:
                user_path = orchestrator_cfg[field]
                # If user provided an absolute path or already starts with .massgen/, keep as-is
                if Path(user_path).is_absolute() or user_path.startswith(".massgen/"):
                    continue
                # Otherwise, relocate under .massgen/
                orchestrator_cfg[field] = str(massgen_dir / user_path)

    # Relocate agent workspaces (cwd fields)
    agent_entries = [config["agent"]] if "agent" in config else config.get("agents", [])
    for agent_data in agent_entries:
        backend_config = agent_data.get("backend", {})
        if "cwd" in backend_config:
            user_cwd = backend_config["cwd"]
            # If user provided an absolute path or already starts with .massgen/, keep as-is
            if Path(user_cwd).is_absolute() or user_cwd.startswith(".massgen/"):
                continue
            # Otherwise, relocate under .massgen/workspaces/
            backend_config["cwd"] = str(massgen_dir / "workspaces" / user_cwd)
