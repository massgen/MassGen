"""
Configuration validation for MassGen YAML/JSON configs.

This module provides comprehensive validation for MassGen configuration files,
checking schema structure, required fields, valid values, and best practices.

Usage:
    from massgen.config_validator import ConfigValidator

    # Validate a config file
    validator = ConfigValidator()
    result = validator.validate_config_file("config.yaml")

    if result.has_errors():
        print(result.format_errors())
        sys.exit(1)

    if result.has_warnings():
        print(result.format_warnings())

    # Validate a config dict
    result = validator.validate_config(config_dict)
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, get_args

import yaml

from . import config_modes
from .backend.capabilities import (
    BACKEND_CAPABILITIES,
    get_capabilities,
    validate_backend_config,
)
from .mcp_tools.config_validator import MCPConfigValidator


@dataclass
class ValidationIssue:
    """Represents a validation error or warning."""

    message: str
    location: str
    suggestion: str | None = None
    severity: str = "error"  # "error" or "warning"

    def __str__(self) -> str:
        """Format issue for display."""
        severity_symbol = "❌" if self.severity == "error" else "⚠️"
        parts = [f"{severity_symbol} [{self.location}] {self.message}"]
        if self.suggestion:
            parts.append(f"   💡 Suggestion: {self.suggestion}")
        return "\n".join(parts)


@dataclass
class ValidationResult:
    """Aggregates all validation errors and warnings."""

    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    def add_error(self, message: str, location: str, suggestion: str | None = None) -> None:
        """Add a validation error."""
        self.errors.append(ValidationIssue(message, location, suggestion, "error"))

    def add_warning(self, message: str, location: str, suggestion: str | None = None) -> None:
        """Add a validation warning."""
        self.warnings.append(ValidationIssue(message, location, suggestion, "warning"))

    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return len(self.errors) > 0

    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return len(self.warnings) > 0

    def is_valid(self) -> bool:
        """Check if config is valid (no errors)."""
        return not self.has_errors()

    def format_errors(self) -> str:
        """Format all errors for display."""
        if not self.errors:
            return ""
        lines = ["\n🔴 Configuration Errors Found:\n"]
        lines.extend(str(error) for error in self.errors)
        return "\n".join(lines)

    def format_warnings(self) -> str:
        """Format all warnings for display."""
        if not self.warnings:
            return ""
        lines = ["\n🟡 Configuration Warnings:\n"]
        lines.extend(str(warning) for warning in self.warnings)
        return "\n".join(lines)

    def format_all(self) -> str:
        """Format all issues for display."""
        parts = []
        if self.has_errors():
            parts.append(self.format_errors())
        if self.has_warnings():
            parts.append(self.format_warnings())
        return "\n".join(parts) if parts else "✅ Configuration is valid!"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON output."""
        return {
            "valid": self.is_valid(),
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": [{"message": e.message, "location": e.location, "suggestion": e.suggestion} for e in self.errors],
            "warnings": [{"message": w.message, "location": w.location, "suggestion": w.suggestion} for w in self.warnings],
        }


class ConfigValidator:
    """Validates MassGen configuration files."""

    # V1 config keywords that are no longer supported
    V1_KEYWORDS = {
        "models",
        "model_configs",
        "num_agents",
        "max_rounds",
        "consensus_threshold",
        "voting_enabled",
        "enable_voting",
    }

    # Valid permission modes for backends that support them
    VALID_PERMISSION_MODES = {"default", "acceptEdits", "bypassPermissions", "plan"}

    # Valid display types for UI
    VALID_DISPLAY_TYPES = {"rich_terminal", "simple", "textual_terminal"}

    # Valid voting sensitivity levels
    VALID_VOTING_SENSITIVITY = {
        "lenient",
        "balanced",
        "strict",
        "roi",
        "roi_conservative",
        "roi_balanced",
        "roi_aggressive",
        "sequential",
        "adversarial",
        "consistency",
        "diversity",
        "reflective",
        "checklist",
        "checklist_scored",
        "checklist_gated",
    }

    # Valid answer novelty requirements
    VALID_ANSWER_NOVELTY = {"lenient", "balanced", "strict"}

    # These mode value-sets derive from the Literal types in config_modes (the
    # single source of truth) so the validator can't drift from the config models
    # again (it previously omitted the "delegated" subagent runtime mode).
    VALID_WRITE_MODES = set(get_args(config_modes.WriteMode))
    VALID_DRIFT_CONFLICT_POLICIES = set(get_args(config_modes.DriftConflictPolicy))
    VALID_NOVELTY_INJECTION = set(get_args(config_modes.NoveltyInjection))
    VALID_ROUND_EVALUATOR_TRANSFORMATION_PRESSURE = set(get_args(config_modes.RoundEvaluatorTransformationPressure))
    VALID_SUBAGENT_RUNTIME_MODES = set(get_args(config_modes.SubagentRuntimeMode))
    VALID_SUBAGENT_RUNTIME_FALLBACK_MODES = set(get_args(config_modes.SubagentRuntimeFallbackMode))
    VALID_FINAL_ANSWER_STRATEGIES = set(get_args(config_modes.FinalAnswerStrategy))
    VALID_LEARNING_CAPTURE_MODES = set(get_args(config_modes.LearningCaptureMode))
    VALID_GAP_REPORT_MODES = set(get_args(config_modes.GapReportMode))

    def __init__(self):
        """Initialize the validator."""

    def validate_config_file(self, config_path: str) -> ValidationResult:
        """
        Validate a configuration file.

        Args:
            config_path: Path to YAML or JSON config file

        Returns:
            ValidationResult with any errors or warnings found
        """
        result = ValidationResult()

        # Check file exists
        path = Path(config_path)
        if not path.exists():
            result.add_error(f"Config file not found: {config_path}", "file", "Check the file path")
            return result

        # Load config file
        try:
            with open(path) as f:
                if path.suffix in [".yaml", ".yml"]:
                    config = yaml.safe_load(f)
                elif path.suffix == ".json":
                    import json

                    config = json.load(f)
                else:
                    result.add_error(
                        f"Unsupported file format: {path.suffix}",
                        "file",
                        "Use .yaml, .yml, or .json extension",
                    )
                    return result
        except Exception as e:
            result.add_error(f"Failed to parse config file: {e}", "file", "Check file syntax")
            return result

        # Validate the loaded config
        return self.validate_config(config)

    def validate_config(self, config: dict[str, Any]) -> ValidationResult:
        """
        Validate a configuration dictionary.

        Args:
            config: Configuration dictionary

        Returns:
            ValidationResult with any errors or warnings found
        """
        result = ValidationResult()

        if not isinstance(config, dict):
            result.add_error("Config must be a dictionary/object", "root", "Check YAML/JSON syntax")
            return result

        # Check for V1 config keywords (instant fail)
        self._check_v1_keywords(config, result)
        if result.has_errors():
            return result  # Stop validation if V1 detected

        # Validate top-level structure
        self._validate_top_level(config, result)

        # Validate agents (if present)
        if "agents" in config or "agent" in config:
            self._validate_agents(config, result)

        # Validate orchestrator (if present)
        if "orchestrator" in config:
            self._validate_orchestrator(config["orchestrator"], result, config=config)

        # Validate UI (if present)
        if "ui" in config:
            self._validate_ui(config["ui"], result)

        # Validate memory (if present)
        if "memory" in config:
            self._validate_memory(config["memory"], result)

        # Check for warnings (best practices, deprecations, etc.)
        self._check_warnings(config, result)

        return result

    def _check_v1_keywords(self, config: dict[str, Any], result: ValidationResult) -> None:
        """Check for V1 config keywords and reject them."""
        found_v1_keywords = []
        for keyword in self.V1_KEYWORDS:
            if keyword in config:
                found_v1_keywords.append(keyword)

        if found_v1_keywords:
            result.add_error(
                f"V1 config format detected (found: {', '.join(found_v1_keywords)}). " "V1 configs are no longer supported.",
                "root",
                "Migrate to V2 config format. See docs/source/reference/yaml_schema.rst for the current schema.",
            )

    def _validate_top_level(self, config: dict[str, Any], result: ValidationResult) -> None:
        """Validate top-level config structure (Level 1)."""
        # Require either 'agents' (list) or 'agent' (single)
        has_agents = "agents" in config
        has_agent = "agent" in config

        if not has_agents and not has_agent:
            result.add_error(
                "Config must have either 'agents' (list) or 'agent' (single agent)",
                "root",
                "Add 'agents: [...]' for multiple agents or 'agent: {...}' for a single agent",
            )
            return

        if has_agents and has_agent:
            result.add_error(
                "Config cannot have both 'agents' and 'agent' fields",
                "root",
                "Use either 'agents' for multiple agents or 'agent' for a single agent",
            )
            return

        # Validate agents is a list (if present)
        if has_agents and not isinstance(config["agents"], list):
            result.add_error(
                f"'agents' must be a list, got {type(config['agents']).__name__}",
                "root.agents",
                "Use 'agents: [...]' for multiple agents",
            )

        # Validate agent is a dict (if present)
        if has_agent and not isinstance(config["agent"], dict):
            result.add_error(
                f"'agent' must be a dictionary, got {type(config['agent']).__name__}",
                "root.agent",
                "Use 'agent: {...}' for a single agent",
            )

        # Validate global hooks if present
        if "hooks" in config:
            self._validate_hooks(config["hooks"], "hooks", result)

        if "timeout_settings" in config:
            self._validate_timeout_settings(config["timeout_settings"], result)

    def _validate_timeout_settings(self, timeout_settings: Any, result: ValidationResult) -> None:
        """Validate top-level timeout_settings config."""
        location = "timeout_settings"
        if not isinstance(timeout_settings, dict):
            result.add_error(
                f"'timeout_settings' must be a dictionary, got {type(timeout_settings).__name__}",
                location,
                "Use timeout fields like orchestrator_timeout_seconds",
            )
            return

        from .agent_config import TimeoutConfig

        known_timeout_keys = TimeoutConfig.yaml_timeout_keys()
        for field_name in sorted(set(timeout_settings) - known_timeout_keys):
            result.add_warning(
                f"Unknown timeout_settings key: '{field_name}'",
                f"{location}.{field_name}",
                "Check the spelling or update TimeoutConfig parser metadata if this is a new supported field.",
            )

        positive_number_fields = (
            "orchestrator_timeout_seconds",
            "initial_round_timeout_seconds",
            "subsequent_round_timeout_seconds",
        )
        for field_name in positive_number_fields:
            if field_name not in timeout_settings or timeout_settings[field_name] is None:
                continue
            value = timeout_settings[field_name]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                result.add_error(
                    f"'{field_name}' must be a positive number or null, got {value!r}",
                    f"{location}.{field_name}",
                    "Use a positive number of seconds, or null for round soft timeouts.",
                )

        if "round_timeout_grace_seconds" in timeout_settings:
            value = timeout_settings["round_timeout_grace_seconds"]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                result.add_error(
                    f"'round_timeout_grace_seconds' must be a non-negative number, got {value!r}",
                    f"{location}.round_timeout_grace_seconds",
                    "Use a non-negative number of seconds.",
                )

    def _validate_agents(self, config: dict[str, Any], result: ValidationResult) -> None:
        """Validate agent configurations (Level 2)."""
        # Get agents list (normalize single agent to list)
        if "agents" in config:
            agents = config["agents"]
            if not isinstance(agents, list):
                return  # Already reported error in _validate_top_level
        else:
            agents = [config["agent"]]

        # Track agent IDs for duplicate detection
        agent_ids: list[str] = []

        for i, agent_config in enumerate(agents):
            agent_location = f"agents[{i}]" if "agents" in config else "agent"

            # Validate agent is a dict
            if not isinstance(agent_config, dict):
                result.add_error(
                    f"Agent must be a dictionary, got {type(agent_config).__name__}",
                    agent_location,
                    "Use 'id', 'backend', and optional 'system_message' fields",
                )
                continue

            # Validate required field: id
            if "id" not in agent_config:
                result.add_error("Agent missing required field 'id'", agent_location, "Add 'id: \"agent-name\"'")
            else:
                agent_id = agent_config["id"]
                if not isinstance(agent_id, str):
                    result.add_error(
                        f"Agent 'id' must be a string, got {type(agent_id).__name__}",
                        f"{agent_location}.id",
                        "Use a string identifier like 'id: \"researcher\"'",
                    )
                elif agent_id in agent_ids:
                    result.add_error(
                        f"Duplicate agent ID: '{agent_id}'",
                        f"{agent_location}.id",
                        "Each agent must have a unique ID",
                    )
                else:
                    agent_ids.append(agent_id)

            # Validate required field: backend
            if "backend" not in agent_config:
                result.add_error(
                    "Agent missing required field 'backend'",
                    agent_location,
                    "Add 'backend: {type: ..., model: ...}'",
                )
            else:
                self._validate_backend(agent_config["backend"], f"{agent_location}.backend", result)

            # Validate optional field: system_message
            if "system_message" in agent_config:
                system_message = agent_config["system_message"]
                if not isinstance(system_message, str):
                    result.add_error(
                        f"Agent 'system_message' must be a string, got {type(system_message).__name__}",
                        f"{agent_location}.system_message",
                        "Use a string for the system message",
                    )

            # Validate optional field: voting_sensitivity (per-agent override)
            if "voting_sensitivity" in agent_config:
                voting_sensitivity = agent_config["voting_sensitivity"]
                if voting_sensitivity not in self.VALID_VOTING_SENSITIVITY:
                    valid_values = ", ".join(sorted(self.VALID_VOTING_SENSITIVITY))
                    result.add_error(
                        f"Invalid voting_sensitivity: '{voting_sensitivity}'",
                        f"{agent_location}.voting_sensitivity",
                        f"Use one of: {valid_values}",
                    )

            # Validate optional field: subtask (decomposition mode)
            if "subtask" in agent_config:
                subtask = agent_config["subtask"]
                if not isinstance(subtask, str):
                    result.add_error(
                        f"Agent 'subtask' must be a string, got {type(subtask).__name__}",
                        f"{agent_location}.subtask",
                        "Use a string describing the agent's subtask",
                    )

            if "subagent_agents" in agent_config:
                subagent_agents = agent_config["subagent_agents"]
                if not isinstance(subagent_agents, list):
                    result.add_error(
                        "'subagent_agents' must be a list",
                        f"{agent_location}.subagent_agents",
                        "Use a list of agent-like entries with 'backend' and optional 'id'",
                    )
                else:
                    subagent_ids: list[str] = []
                    for j, subagent_cfg in enumerate(subagent_agents):
                        subagent_location = f"{agent_location}.subagent_agents[{j}]"
                        if not isinstance(subagent_cfg, dict):
                            result.add_error(
                                f"Subagent agent must be a dictionary, got {type(subagent_cfg).__name__}",
                                subagent_location,
                                "Use 'id' and 'backend' fields",
                            )
                            continue

                        if "id" in subagent_cfg:
                            subagent_id = subagent_cfg["id"]
                            if not isinstance(subagent_id, str):
                                result.add_error(
                                    f"Subagent agent 'id' must be a string, got {type(subagent_id).__name__}",
                                    f"{subagent_location}.id",
                                    "Use a string identifier like 'id: \"local_eval\"'",
                                )
                            elif subagent_id in subagent_ids:
                                result.add_error(
                                    f"Duplicate subagent agent ID: '{subagent_id}'",
                                    f"{subagent_location}.id",
                                    "Each subagent agent ID must be unique within the list",
                                )
                            else:
                                subagent_ids.append(subagent_id)

                        if "backend" not in subagent_cfg:
                            result.add_error(
                                "Subagent agent missing required field 'backend'",
                                subagent_location,
                                "Add 'backend: {type: ..., model: ...}'",
                            )
                        else:
                            self._validate_backend(
                                subagent_cfg["backend"],
                                f"{subagent_location}.backend",
                                result,
                            )

        # Validate main_agent: at most one agent can have main_agent: true
        main_agent_count = sum(1 for a in agents if isinstance(a, dict) and a.get("main_agent") is True)
        if main_agent_count > 1:
            result.add_error(
                f"Only one agent can have main_agent: true, found {main_agent_count}",
                "agents",
                "Set main_agent: true on exactly one agent for checkpoint coordination",
            )

        # Validate checkpoint config (if present at top level)
        if "checkpoint" in config:
            self._validate_checkpoint_config(config["checkpoint"], result)

    def _validate_checkpoint_config(
        self,
        checkpoint_config: dict[str, Any],
        result: ValidationResult,
    ) -> None:
        """Validate checkpoint configuration section."""
        if not isinstance(checkpoint_config, dict):
            result.add_error(
                "checkpoint must be a dictionary",
                "checkpoint",
                "Use checkpoint: {enabled: true, mode: conversation}",
            )
            return

        # Validate mode
        valid_modes = {"conversation", "task"}
        mode = checkpoint_config.get("mode", "conversation")
        if mode not in valid_modes:
            result.add_error(
                f"Invalid checkpoint mode: '{mode}'",
                "checkpoint.mode",
                f"Use one of: {', '.join(sorted(valid_modes))}",
            )

        # Validate gated_patterns
        gated_patterns = checkpoint_config.get("gated_patterns")
        if gated_patterns is not None:
            if not isinstance(gated_patterns, list):
                result.add_error(
                    "checkpoint.gated_patterns must be a list of strings",
                    "checkpoint.gated_patterns",
                )
            elif not all(isinstance(p, str) for p in gated_patterns):
                result.add_error(
                    "All entries in checkpoint.gated_patterns must be strings",
                    "checkpoint.gated_patterns",
                )

    def _validate_backend(self, backend_config: dict[str, Any], location: str, result: ValidationResult) -> None:
        """Validate backend configuration (Level 3)."""
        if not isinstance(backend_config, dict):
            result.add_error(
                f"Backend must be a dictionary, got {type(backend_config).__name__}",
                location,
                "Use 'type', 'model', and other backend-specific fields",
            )
            return

        # Validate required field: type
        if "type" not in backend_config:
            result.add_error("Backend missing required field 'type'", location, "Add 'type: \"openai\"' or similar")
            return

        backend_type = backend_config["type"]
        if not isinstance(backend_type, str):
            result.add_error(
                f"Backend 'type' must be a string, got {type(backend_type).__name__}",
                f"{location}.type",
                "Use a string like 'openai', 'claude', 'gemini', etc.",
            )
            return

        # Validate backend type is supported
        if backend_type not in BACKEND_CAPABILITIES:
            valid_types = ", ".join(sorted(BACKEND_CAPABILITIES.keys()))
            result.add_error(
                f"Unknown backend type: '{backend_type}'",
                f"{location}.type",
                f"Use one of: {valid_types}",
            )
            return

        # Validate model field
        # Model is optional for:
        # - ag2 (uses agent_config.llm_config instead)
        # - claude_code (has default model)
        # - backends with default models in BACKEND_CAPABILITIES
        caps = get_capabilities(backend_type)
        has_default_model = caps and caps.default_model != "custom"

        if backend_type != "ag2" and not has_default_model:
            if "model" not in backend_config:
                result.add_error("Backend missing required field 'model'", location, "Add 'model: \"model-name\"'")
            else:
                model = backend_config["model"]
                if not isinstance(model, str):
                    result.add_error(
                        f"Backend 'model' must be a string, got {type(model).__name__}",
                        f"{location}.model",
                        "Use a string model identifier",
                    )
        elif "model" in backend_config:
            # Validate type if model is provided (even if optional)
            model = backend_config["model"]
            if not isinstance(model, str):
                result.add_error(
                    f"Backend 'model' must be a string, got {type(model).__name__}",
                    f"{location}.model",
                    "Use a string model identifier",
                )

        # Require cwd for backends that create workspace config directories.
        # Without cwd, codex writes .codex/ and claude_code writes .claude/
        # into the project root, polluting the repo.
        if backend_type in ("codex", "claude_code") and "cwd" not in backend_config:
            result.add_error(
                f"Backend type '{backend_type}' requires 'cwd' to avoid writing config into the project root",
                f"{location}.cwd",
                "Add 'cwd: workspace' (resolved to .massgen/workspaces/workspace_<hash>)",
            )

        # Validate backend-specific capabilities using existing validator
        capability_errors = validate_backend_config(backend_type, backend_config)
        for error_msg in capability_errors:
            result.add_error(error_msg, location, "Check backend capabilities in documentation")

        # Validate permission_mode if present
        if "permission_mode" in backend_config:
            permission_mode = backend_config["permission_mode"]
            if permission_mode not in self.VALID_PERMISSION_MODES:
                valid_modes = ", ".join(sorted(self.VALID_PERMISSION_MODES))
                result.add_error(
                    f"Invalid permission_mode: '{permission_mode}'",
                    f"{location}.permission_mode",
                    f"Use one of: {valid_modes}",
                )

        # Validate tool filtering (allowed_tools, exclude_tools, disallowed_tools)
        self._validate_tool_filtering(backend_config, location, result)

        # Validate MCP servers if present
        if "mcp_servers" in backend_config:
            try:
                MCPConfigValidator.validate_backend_mcp_config(backend_config)
            except Exception as e:
                result.add_error(
                    f"MCP configuration error: {str(e)}",
                    f"{location}.mcp_servers",
                    "Check MCP server configuration syntax",
                )

        # Validate boolean fields
        boolean_fields = [
            "enable_web_search",
            "enable_x_search",
            "enable_code_execution",
            "enable_code_interpreter",
            "enable_programmatic_flow",
            "enable_tool_search",
            "enable_strict_tool_use",
            "websocket_mode",
        ]
        for field_name in boolean_fields:
            if field_name in backend_config:
                value = backend_config[field_name]
                if not isinstance(value, bool):
                    result.add_error(
                        f"Backend '{field_name}' must be a boolean, got {type(value).__name__}",
                        f"{location}.{field_name}",
                        "Use 'true' or 'false'",
                    )

        # Validate output_schema if present (structured outputs)
        if "output_schema" in backend_config:
            output_schema = backend_config["output_schema"]
            if not isinstance(output_schema, dict):
                result.add_error(
                    f"'output_schema' must be a dictionary, got {type(output_schema).__name__}",
                    f"{location}.output_schema",
                    "Use a JSON schema object like: {type: object, properties: {...}}",
                )
            elif not output_schema:
                result.add_warning(
                    "'output_schema' is an empty dictionary",
                    f"{location}.output_schema",
                    "Provide a valid JSON schema",
                )
            elif "type" not in output_schema:
                result.add_warning(
                    "'output_schema' should have a 'type' field",
                    f"{location}.output_schema",
                    "Add 'type: object' or similar",
                )

        # Check for incompatible feature combinations
        if backend_config.get("enable_programmatic_flow") and backend_config.get("enable_strict_tool_use"):
            result.add_warning(
                "Strict tool use is not compatible with programmatic tool calling",
                location,
                "Strict tool use will be automatically disabled at runtime. ",
            )

        # Validate hooks if present
        if "hooks" in backend_config:
            self._validate_hooks(backend_config["hooks"], f"{location}.hooks", result)

        # Validate Codex Docker mode requirements
        if backend_type == "codex":
            execution_mode = backend_config.get("command_line_execution_mode")
            if execution_mode == "docker":
                # command_line_docker_network_mode is required for Codex in Docker mode
                if "command_line_docker_network_mode" not in backend_config:
                    result.add_error(
                        "Codex backend in Docker mode requires 'command_line_docker_network_mode'",
                        f"{location}.command_line_docker_network_mode",
                        "Add 'command_line_docker_network_mode: bridge' (required for Codex Docker execution)",
                    )

        # Validate Copilot Docker mode requirements
        if backend_type == "copilot":
            execution_mode = backend_config.get("command_line_execution_mode")
            if execution_mode == "docker":
                if "command_line_docker_network_mode" not in backend_config:
                    result.add_error(
                        "Copilot backend in Docker mode requires 'command_line_docker_network_mode'",
                        f"{location}.command_line_docker_network_mode",
                        "Add 'command_line_docker_network_mode: bridge' (required for Copilot Docker execution)",
                    )

        # Validate Gemini CLI Docker mode requirements
        if backend_type == "gemini_cli":
            execution_mode = backend_config.get("command_line_execution_mode")
            if execution_mode == "docker":
                if "command_line_docker_network_mode" not in backend_config:
                    result.add_error(
                        "Gemini CLI backend in Docker mode requires 'command_line_docker_network_mode'",
                        f"{location}.command_line_docker_network_mode",
                        "Add 'command_line_docker_network_mode: bridge' (required for Gemini CLI Docker execution)",
                    )

    def _validate_tool_filtering(
        self,
        backend_config: dict[str, Any],
        location: str,
        result: ValidationResult,
    ) -> None:
        """Validate tool filtering parameters."""
        # Check allowed_tools
        if "allowed_tools" in backend_config:
            allowed_tools = backend_config["allowed_tools"]
            if not isinstance(allowed_tools, list):
                result.add_error(
                    f"'allowed_tools' must be a list, got {type(allowed_tools).__name__}",
                    f"{location}.allowed_tools",
                    "Use a list of tool names",
                )
            else:
                for i, tool in enumerate(allowed_tools):
                    if not isinstance(tool, str):
                        result.add_error(
                            f"'allowed_tools[{i}]' must be a string, got {type(tool).__name__}",
                            f"{location}.allowed_tools[{i}]",
                            "Use string tool names",
                        )

        # Check exclude_tools
        if "exclude_tools" in backend_config:
            exclude_tools = backend_config["exclude_tools"]
            if not isinstance(exclude_tools, list):
                result.add_error(
                    f"'exclude_tools' must be a list, got {type(exclude_tools).__name__}",
                    f"{location}.exclude_tools",
                    "Use a list of tool names",
                )
            else:
                for i, tool in enumerate(exclude_tools):
                    if not isinstance(tool, str):
                        result.add_error(
                            f"'exclude_tools[{i}]' must be a string, got {type(tool).__name__}",
                            f"{location}.exclude_tools[{i}]",
                            "Use string tool names",
                        )

        # Check disallowed_tools (claude_code specific)
        if "disallowed_tools" in backend_config:
            disallowed_tools = backend_config["disallowed_tools"]
            if not isinstance(disallowed_tools, list):
                result.add_error(
                    f"'disallowed_tools' must be a list, got {type(disallowed_tools).__name__}",
                    f"{location}.disallowed_tools",
                    "Use a list of tool patterns",
                )
            else:
                for i, tool in enumerate(disallowed_tools):
                    if not isinstance(tool, str):
                        result.add_error(
                            f"'disallowed_tools[{i}]' must be a string, got {type(tool).__name__}",
                            f"{location}.disallowed_tools[{i}]",
                            "Use string tool patterns",
                        )

    def _validate_hooks(
        self,
        hooks_config: dict[str, Any],
        location: str,
        result: ValidationResult,
    ) -> None:
        """Validate hooks configuration.

        Hooks can be defined at two levels:
        - Global (top-level `hooks:`) - applies to all agents
        - Per-agent (in `backend.hooks:`) - can extend or override global hooks
        """
        if not isinstance(hooks_config, dict):
            result.add_error(
                f"'hooks' must be a dictionary, got {type(hooks_config).__name__}",
                location,
                "Use hook types like 'PreToolUse' and 'PostToolUse'",
            )
            return

        valid_hook_types = {"PreToolUse", "PostToolUse"}

        for hook_type, hook_list in hooks_config.items():
            if hook_type == "override":
                # Skip override flag
                continue

            if hook_type not in valid_hook_types:
                result.add_warning(
                    f"Unknown hook type: '{hook_type}'",
                    f"{location}.{hook_type}",
                    f"Use one of: {', '.join(sorted(valid_hook_types))}",
                )
                continue

            # Handle both list format and dict format (with override)
            hooks_to_validate = hook_list
            if isinstance(hook_list, dict):
                hooks_to_validate = hook_list.get("hooks", [])
                if "override" in hook_list and not isinstance(hook_list["override"], bool):
                    result.add_error(
                        "'override' must be a boolean",
                        f"{location}.{hook_type}.override",
                        "Use 'true' or 'false'",
                    )

            if not isinstance(hooks_to_validate, list):
                result.add_error(
                    f"'{hook_type}' must be a list of hooks",
                    f"{location}.{hook_type}",
                    "Use a list of hook configurations",
                )
                continue

            # Validate each hook in the list
            for i, hook_config in enumerate(hooks_to_validate):
                self._validate_single_hook(
                    hook_config,
                    f"{location}.{hook_type}[{i}]",
                    result,
                )

    def _validate_single_hook(
        self,
        hook_config: dict[str, Any],
        location: str,
        result: ValidationResult,
    ) -> None:
        """Validate a single hook configuration."""
        if not isinstance(hook_config, dict):
            result.add_error(
                f"Hook must be a dictionary, got {type(hook_config).__name__}",
                location,
                "Use 'handler', 'matcher', 'type', and 'timeout' fields",
            )
            return

        # Validate required field: handler
        if "handler" not in hook_config:
            result.add_error(
                "Hook missing required field 'handler'",
                location,
                "Add 'handler: \"module.function\"' or 'handler: \"path/to/script.py\"'",
            )
        else:
            handler = hook_config["handler"]
            if not isinstance(handler, str):
                result.add_error(
                    f"'handler' must be a string, got {type(handler).__name__}",
                    f"{location}.handler",
                    "Use a module path or file path",
                )

        # Validate optional field: type
        if "type" in hook_config:
            hook_type = hook_config["type"]
            valid_types = {"python"}
            if hook_type not in valid_types:
                result.add_error(
                    f"Invalid hook type: '{hook_type}'",
                    f"{location}.type",
                    f"Use one of: {', '.join(sorted(valid_types))}",
                )

        # Validate optional field: matcher
        if "matcher" in hook_config:
            matcher = hook_config["matcher"]
            if not isinstance(matcher, str):
                result.add_error(
                    f"'matcher' must be a string, got {type(matcher).__name__}",
                    f"{location}.matcher",
                    "Use a glob pattern like '*' or 'Write|Edit'",
                )

        # Validate optional field: timeout
        if "timeout" in hook_config:
            timeout = hook_config["timeout"]
            if not isinstance(timeout, (int, float)):
                result.add_error(
                    f"'timeout' must be a number, got {type(timeout).__name__}",
                    f"{location}.timeout",
                    "Use a number of seconds like 30 or 60",
                )
            elif timeout <= 0:
                result.add_error(
                    f"'timeout' must be positive, got {timeout}",
                    f"{location}.timeout",
                    "Use a positive number of seconds",
                )

        # Validate optional field: fail_closed
        if "fail_closed" in hook_config:
            fail_closed = hook_config["fail_closed"]
            if not isinstance(fail_closed, bool):
                result.add_error(
                    f"'fail_closed' must be a boolean, got {type(fail_closed).__name__}",
                    f"{location}.fail_closed",
                    "Use true or false",
                )

    def _validate_orchestrator(self, orchestrator_config: dict[str, Any], result: ValidationResult, config: dict[str, Any] | None = None) -> None:
        """Validate orchestrator configuration (Level 5)."""
        location = "orchestrator"

        if not isinstance(orchestrator_config, dict):
            result.add_error(
                f"Orchestrator must be a dictionary, got {type(orchestrator_config).__name__}",
                location,
                "Use orchestrator fields like snapshot_storage, context_paths, etc.",
            )
            return

        from .agent_config import AgentConfig

        known_orchestrator_keys = AgentConfig.valid_orchestrator_keys()
        for field_name in sorted(set(orchestrator_config) - known_orchestrator_keys):
            result.add_warning(
                f"Unknown orchestrator config key: '{field_name}'",
                f"{location}.{field_name}",
                "Check the spelling or update AgentConfig orchestrator key metadata if this is a new supported field.",
            )

        # Validate coordination_mode if present
        if "coordination_mode" in orchestrator_config:
            coordination_mode = orchestrator_config["coordination_mode"]
            valid_modes = ["voting", "decomposition"]
            if coordination_mode not in valid_modes:
                result.add_error(
                    f"Invalid coordination_mode: '{coordination_mode}'",
                    f"{location}.coordination_mode",
                    f"Use one of: {', '.join(valid_modes)}",
                )

        # Validate presenter_agent if present
        if "presenter_agent" in orchestrator_config:
            presenter = orchestrator_config["presenter_agent"]
            if not isinstance(presenter, str):
                result.add_error(
                    f"'presenter_agent' must be a string, got {type(presenter).__name__}",
                    f"{location}.presenter_agent",
                    "Use an agent ID string like 'integrator'",
                )

        # Validate final_answer_strategy if present
        if "final_answer_strategy" in orchestrator_config:
            strategy = orchestrator_config["final_answer_strategy"]
            valid_strategies = sorted(self.VALID_FINAL_ANSWER_STRATEGIES)
            if strategy is not None and strategy not in self.VALID_FINAL_ANSWER_STRATEGIES:
                result.add_error(
                    f"Invalid final_answer_strategy: '{strategy}'",
                    f"{location}.final_answer_strategy",
                    f"Use one of: {', '.join(valid_strategies)}",
                )

        # Validate context_paths if present
        if "context_paths" in orchestrator_config:
            context_paths = orchestrator_config["context_paths"]
            if not isinstance(context_paths, list):
                result.add_error(
                    f"'context_paths' must be a list, got {type(context_paths).__name__}",
                    f"{location}.context_paths",
                    "Use a list of path configurations",
                )
            else:
                for i, path_config in enumerate(context_paths):
                    if not isinstance(path_config, dict):
                        result.add_error(
                            f"'context_paths[{i}]' must be a dictionary",
                            f"{location}.context_paths[{i}]",
                            "Use 'path' and 'permission' fields",
                        )
                        continue

                    # Check required field: path
                    if "path" not in path_config:
                        result.add_error(
                            "context_paths entry missing 'path' field",
                            f"{location}.context_paths[{i}]",
                            "Add 'path: \"/path/to/dir\"'",
                        )

                    # Check permission field
                    if "permission" in path_config:
                        permission = path_config["permission"]
                        if permission not in ["read", "write"]:
                            result.add_error(
                                f"Invalid permission: '{permission}'",
                                f"{location}.context_paths[{i}].permission",
                                "Use 'read' or 'write'",
                            )

        # Validate coordination if present
        if "coordination" in orchestrator_config:
            coordination = orchestrator_config["coordination"]
            if not isinstance(coordination, dict):
                result.add_error(
                    f"'coordination' must be a dictionary, got {type(coordination).__name__}",
                    f"{location}.coordination",
                    "Use coordination fields like enable_planning_mode, max_orchestration_restarts, etc.",
                )
            else:
                from .agent_config import CoordinationConfig

                known_removed_keys = {"async_subagents"}
                known_coordination_keys = CoordinationConfig.valid_coordination_keys() | known_removed_keys
                for field_name in sorted(set(coordination) - known_coordination_keys):
                    result.add_warning(
                        f"Unknown coordination config key: '{field_name}'",
                        f"{location}.coordination.{field_name}",
                        "Check the spelling or update CoordinationConfig parser metadata if this is a new supported field.",
                    )

                # Validate boolean fields
                boolean_fields = [
                    "enable_planning_mode",
                    "use_two_tier_workspace",
                    "enable_changedoc",
                    "round_evaluator_before_checklist",
                    "orchestrator_managed_round_evaluator",
                    "round_evaluator_refine",
                    "round_evaluator_skip_synthesis",
                    "fast_iteration_mode",
                    "skip_redundant_scaffolding",
                ]
                for field_name in boolean_fields:
                    if field_name in coordination:
                        value = coordination[field_name]
                        if not isinstance(value, bool):
                            result.add_error(
                                f"'{field_name}' must be a boolean, got {type(value).__name__}",
                                f"{location}.coordination.{field_name}",
                                "Use 'true' or 'false'",
                            )

                # Validate non-negative int fields (None is allowed and means "unlimited")
                nonneg_int_fields = [
                    "max_verifications_per_round",
                    "max_internal_fix_loops",
                ]
                for field_name in nonneg_int_fields:
                    if field_name in coordination and coordination[field_name] is not None:
                        value = coordination[field_name]
                        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                            result.add_error(
                                f"'{field_name}' must be a non-negative integer or null, got {value!r}",
                                f"{location}.coordination.{field_name}",
                                "Use a non-negative integer (e.g., 0, 1, 2) or omit the field for unlimited.",
                            )

                positive_timeout_fields = [
                    "subagent_default_timeout",
                    "subagent_min_timeout",
                    "subagent_max_timeout",
                ]
                for field_name in positive_timeout_fields:
                    if field_name in coordination:
                        value = coordination[field_name]
                        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                            result.add_error(
                                f"'{field_name}' must be a positive integer, got {value!r}",
                                f"{location}.coordination.{field_name}",
                                "Use a positive integer number of seconds.",
                            )

                min_timeout = coordination.get("subagent_min_timeout")
                max_timeout = coordination.get("subagent_max_timeout")
                min_timeout_is_int = isinstance(min_timeout, int) and not isinstance(min_timeout, bool)
                max_timeout_is_int = isinstance(max_timeout, int) and not isinstance(max_timeout, bool)
                if min_timeout_is_int and max_timeout_is_int and min_timeout > max_timeout:
                    result.add_error(
                        "subagent_min_timeout must be less than or equal to subagent_max_timeout",
                        f"{location}.coordination.subagent_min_timeout",
                        "Set subagent_min_timeout <= subagent_max_timeout.",
                    )

                # Deprecation warning for use_two_tier_workspace
                if coordination.get("use_two_tier_workspace"):
                    write_mode = coordination.get("write_mode")
                    if write_mode:
                        result.add_warning(
                            "'use_two_tier_workspace' is deprecated and ignored when 'write_mode' is set. " "Remove 'use_two_tier_workspace' from your config.",
                            f"{location}.coordination.use_two_tier_workspace",
                        )
                    else:
                        result.add_warning(
                            "'use_two_tier_workspace' is deprecated. " "Migrate to 'write_mode: auto' for the same functionality with git worktree isolation.",
                            f"{location}.coordination.use_two_tier_workspace",
                        )

                # Validate integer fields
                if "max_orchestration_restarts" in coordination:
                    value = coordination["max_orchestration_restarts"]
                    if not isinstance(value, int) or value < 0:
                        result.add_error(
                            "'max_orchestration_restarts' must be a non-negative integer",
                            f"{location}.coordination.max_orchestration_restarts",
                            "Use a value like 0, 1, 2, etc.",
                        )

                # Hard-break rename: async_subagents -> background_subagents
                if "async_subagents" in coordination:
                    result.add_error(
                        "'async_subagents' has been removed. Use 'background_subagents' instead.",
                        f"{location}.coordination.async_subagents",
                        "Replace with background_subagents: {enabled: true, injection_strategy: 'tool_result'}",
                    )

                # Validate background_subagents if present
                if "background_subagents" in coordination:
                    background_config = coordination["background_subagents"]
                    if not isinstance(background_config, dict):
                        result.add_error(
                            f"'background_subagents' must be a dictionary, got {type(background_config).__name__}",
                            f"{location}.coordination.background_subagents",
                            "Use background_subagents: {enabled: true, injection_strategy: 'tool_result'}",
                        )
                    else:
                        # Validate enabled field
                        if "enabled" in background_config:
                            enabled = background_config["enabled"]
                            if not isinstance(enabled, bool):
                                result.add_error(
                                    f"'background_subagents.enabled' must be a boolean, got {type(enabled).__name__}",
                                    f"{location}.coordination.background_subagents.enabled",
                                    "Use 'true' or 'false'",
                                )

                        # Validate injection_strategy field
                        if "injection_strategy" in background_config:
                            strategy = background_config["injection_strategy"]
                            valid_strategies = ["tool_result", "user_message"]
                            if strategy not in valid_strategies:
                                result.add_error(
                                    f"Invalid background_subagents.injection_strategy: '{strategy}'",
                                    f"{location}.coordination.background_subagents.injection_strategy",
                                    f"Use one of: {', '.join(valid_strategies)}",
                                )
                # Validate plan_depth if present
                if "plan_depth" in coordination:
                    value = coordination["plan_depth"]
                    valid_depths = ["dynamic", "shallow", "medium", "deep"]
                    if value not in valid_depths:
                        result.add_error(
                            f"'plan_depth' must be one of {valid_depths}, got '{value}'",
                            f"{location}.coordination.plan_depth",
                            "Use 'dynamic', 'shallow' (5-10 tasks), 'medium' (20-50 tasks), or 'deep' (100-200+ tasks)",
                        )

                # Validate optional explicit planning targets
                if "plan_target_steps" in coordination:
                    value = coordination["plan_target_steps"]
                    if value is not None and (not isinstance(value, int) or value <= 0):
                        result.add_error(
                            "'plan_target_steps' must be a positive integer or null",
                            f"{location}.coordination.plan_target_steps",
                            "Use values like 20, 40, 80, or omit/null for dynamic sizing.",
                        )

                if "plan_target_chunks" in coordination:
                    value = coordination["plan_target_chunks"]
                    if value is not None and (not isinstance(value, int) or value <= 0):
                        result.add_error(
                            "'plan_target_chunks' must be a positive integer or null",
                            f"{location}.coordination.plan_target_chunks",
                            "Use values like 3, 5, 8, or omit/null for dynamic sizing.",
                        )

                if "pre_collab_voting_threshold" in coordination:
                    value = coordination["pre_collab_voting_threshold"]
                    if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value <= 0):
                        result.add_error(
                            "'pre_collab_voting_threshold' must be a positive integer or null",
                            f"{location}.coordination.pre_collab_voting_threshold",
                            "Use a positive integer like 5, 10, 15, or omit/null to inherit orchestrator.voting_threshold",
                        )

                # Validate subagent_round_timeouts if present
                if "subagent_round_timeouts" in coordination:
                    round_timeouts = coordination["subagent_round_timeouts"]
                    if not isinstance(round_timeouts, dict):
                        result.add_error(
                            f"'subagent_round_timeouts' must be a dictionary, got {type(round_timeouts).__name__}",
                            f"{location}.coordination.subagent_round_timeouts",
                            "Use keys like initial_round_timeout_seconds, subsequent_round_timeout_seconds, round_timeout_grace_seconds",
                        )
                    else:
                        timeout_fields = [
                            "initial_round_timeout_seconds",
                            "subsequent_round_timeout_seconds",
                            "round_timeout_grace_seconds",
                        ]
                        for field_name in timeout_fields:
                            if field_name in round_timeouts:
                                value = round_timeouts[field_name]
                                if field_name == "round_timeout_grace_seconds":
                                    if not isinstance(value, (int, float)) or value < 0:
                                        result.add_error(
                                            f"'{field_name}' must be a non-negative number",
                                            f"{location}.coordination.subagent_round_timeouts.{field_name}",
                                            "Use a value like 120 (seconds)",
                                        )
                                else:
                                    if not isinstance(value, (int, float)) or value <= 0:
                                        result.add_error(
                                            f"'{field_name}' must be a positive number",
                                            f"{location}.coordination.subagent_round_timeouts.{field_name}",
                                            "Use a value like 300 (seconds)",
                                        )

                # Validate subagent runtime isolation settings
                runtime_mode = coordination.get("subagent_runtime_mode", "isolated")
                if "subagent_runtime_mode" in coordination and runtime_mode not in self.VALID_SUBAGENT_RUNTIME_MODES:
                    valid_values = ", ".join(sorted(self.VALID_SUBAGENT_RUNTIME_MODES))
                    result.add_error(
                        f"Invalid subagent_runtime_mode: '{runtime_mode}'",
                        f"{location}.coordination.subagent_runtime_mode",
                        f"Use one of: {valid_values}",
                    )

                if "subagent_runtime_fallback_mode" in coordination:
                    fallback_mode = coordination["subagent_runtime_fallback_mode"]
                    if fallback_mode is not None and fallback_mode not in self.VALID_SUBAGENT_RUNTIME_FALLBACK_MODES:
                        valid_values = ", ".join(sorted(self.VALID_SUBAGENT_RUNTIME_FALLBACK_MODES))
                        result.add_error(
                            f"Invalid subagent_runtime_fallback_mode: '{fallback_mode}'",
                            f"{location}.coordination.subagent_runtime_fallback_mode",
                            f"Use one of: null, {valid_values}",
                        )
                    elif fallback_mode is not None and runtime_mode != "isolated":
                        result.add_error(
                            "subagent_runtime_fallback_mode can only be set when subagent_runtime_mode is 'isolated'",
                            f"{location}.coordination.subagent_runtime_fallback_mode",
                            "Set subagent_runtime_mode: isolated or remove subagent_runtime_fallback_mode",
                        )

                if "subagent_host_launch_prefix" in coordination:
                    host_launch_prefix = coordination["subagent_host_launch_prefix"]
                    if host_launch_prefix is not None:
                        if not isinstance(host_launch_prefix, list):
                            result.add_error(
                                f"'subagent_host_launch_prefix' must be a list or null, got {type(host_launch_prefix).__name__}",
                                f"{location}.coordination.subagent_host_launch_prefix",
                                "Use a list of command tokens, for example ['host-launch', '--exec']",
                            )
                        else:
                            for i, token in enumerate(host_launch_prefix):
                                if not isinstance(token, str) or not token.strip():
                                    result.add_error(
                                        "'subagent_host_launch_prefix' entries must be non-empty strings",
                                        f"{location}.coordination.subagent_host_launch_prefix[{i}]",
                                        "Use command token strings only",
                                    )

                # Validate write_mode if present
                if "write_mode" in coordination:
                    write_mode = coordination["write_mode"]
                    if write_mode not in self.VALID_WRITE_MODES:
                        valid_values = ", ".join(sorted(self.VALID_WRITE_MODES))
                        result.add_error(
                            f"Invalid write_mode: '{write_mode}'",
                            f"{location}.coordination.write_mode",
                            f"Use one of: {valid_values}",
                        )
                if "drift_conflict_policy" in coordination:
                    policy = coordination["drift_conflict_policy"]
                    if policy not in self.VALID_DRIFT_CONFLICT_POLICIES:
                        valid_values = ", ".join(sorted(self.VALID_DRIFT_CONFLICT_POLICIES))
                        result.add_error(
                            f"Invalid drift_conflict_policy: '{policy}'",
                            f"{location}.coordination.drift_conflict_policy",
                            f"Use one of: {valid_values}",
                        )
                if "novelty_injection" in coordination:
                    novelty = coordination["novelty_injection"]
                    if novelty not in self.VALID_NOVELTY_INJECTION:
                        valid_values = ", ".join(sorted(self.VALID_NOVELTY_INJECTION))
                        result.add_error(
                            f"Invalid novelty_injection: '{novelty}'",
                            f"{location}.coordination.novelty_injection",
                            f"Use one of: {valid_values}",
                        )
                if "round_evaluator_transformation_pressure" in coordination:
                    pressure = coordination["round_evaluator_transformation_pressure"]
                    if pressure not in self.VALID_ROUND_EVALUATOR_TRANSFORMATION_PRESSURE:
                        valid_values = ", ".join(sorted(self.VALID_ROUND_EVALUATOR_TRANSFORMATION_PRESSURE))
                        result.add_error(
                            f"Invalid round_evaluator_transformation_pressure: '{pressure}'. Supported values: {valid_values}",
                            f"{location}.coordination.round_evaluator_transformation_pressure",
                            f"Use one of: {valid_values}",
                        )
                if "enable_novelty_on_iteration" in coordination and not isinstance(
                    coordination["enable_novelty_on_iteration"],
                    bool,
                ):
                    result.add_error(
                        "'enable_novelty_on_iteration' must be a boolean",
                        f"{location}.coordination.enable_novelty_on_iteration",
                        "Use true or false",
                    )
                if "enable_quality_rethink_on_iteration" in coordination and not isinstance(
                    coordination["enable_quality_rethink_on_iteration"],
                    bool,
                ):
                    result.add_error(
                        "'enable_quality_rethink_on_iteration' must be a boolean",
                        f"{location}.coordination.enable_quality_rethink_on_iteration",
                        "Use true or false",
                    )
                if "enable_execution_trace_analyzer" in coordination:
                    eta_val = coordination["enable_execution_trace_analyzer"]
                    if not isinstance(eta_val, bool):
                        result.add_error(
                            "'enable_execution_trace_analyzer' must be a boolean",
                            f"{location}.coordination.enable_execution_trace_analyzer",
                            "Use true or false",
                        )
                    elif eta_val and not coordination.get("orchestrator_managed_round_evaluator", False):
                        result.add_error(
                            "enable_execution_trace_analyzer requires orchestrator_managed_round_evaluator: true",
                            f"{location}.coordination.enable_execution_trace_analyzer",
                            "Enable orchestrator_managed_round_evaluator or remove enable_execution_trace_analyzer",
                        )
                if "improvements" in coordination:
                    improvements = coordination["improvements"]
                    improvements_location = f"{location}.coordination.improvements"
                    if not isinstance(improvements, dict):
                        result.add_error(
                            "'improvements' must be a dictionary",
                            improvements_location,
                            "Use keys like min_transformative, min_structural, min_non_incremental",
                        )
                    else:
                        for key in ("min_transformative", "min_structural", "min_non_incremental"):
                            if key not in improvements:
                                continue
                            value = improvements[key]
                            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                                result.add_error(
                                    f"'{key}' must be a non-negative integer",
                                    f"{improvements_location}.{key}",
                                    "Use values like 0, 1, 2",
                                )
                if "learning_capture_mode" in coordination:
                    learning_capture_mode = coordination["learning_capture_mode"]
                    if learning_capture_mode not in self.VALID_LEARNING_CAPTURE_MODES:
                        valid_values = ", ".join(
                            sorted(self.VALID_LEARNING_CAPTURE_MODES),
                        )
                        result.add_error(
                            f"Invalid learning_capture_mode: '{learning_capture_mode}'",
                            f"{location}.coordination.learning_capture_mode",
                            f"Use one of: {valid_values}",
                        )
                if "disable_final_only_round_capture_fallback" in coordination and not isinstance(
                    coordination["disable_final_only_round_capture_fallback"],
                    bool,
                ):
                    result.add_error(
                        "'disable_final_only_round_capture_fallback' must be a boolean",
                        f"{location}.coordination.disable_final_only_round_capture_fallback",
                        "Use true or false",
                    )

                if "subagent_orchestrator" in coordination:
                    subagent_orchestrator = coordination["subagent_orchestrator"]
                    if subagent_orchestrator is not None:
                        if not isinstance(subagent_orchestrator, dict):
                            result.add_error(
                                f"'subagent_orchestrator' must be a dictionary or null, got {type(subagent_orchestrator).__name__}",
                                f"{location}.coordination.subagent_orchestrator",
                                "Use a dict like {enabled: true, agents: [...]}",
                            )
                        else:
                            inherit_spawning_backend = subagent_orchestrator.get("inherit_spawning_agent_backend")
                            if inherit_spawning_backend is not None and not isinstance(inherit_spawning_backend, bool):
                                result.add_error(
                                    "'inherit_spawning_agent_backend' must be a boolean",
                                    f"{location}.coordination.subagent_orchestrator.inherit_spawning_agent_backend",
                                    "Use true or false",
                                )
                            shared_child_team_types = subagent_orchestrator.get("shared_child_team_types")
                            if shared_child_team_types is not None:
                                if not isinstance(shared_child_team_types, list):
                                    result.add_error(
                                        "'shared_child_team_types' must be a list of non-empty strings",
                                        f"{location}.coordination.subagent_orchestrator.shared_child_team_types",
                                        "Use a list like: [round_evaluator, builder]",
                                    )
                                else:
                                    for i, child_type in enumerate(shared_child_team_types):
                                        if not isinstance(child_type, str) or not child_type.strip():
                                            result.add_error(
                                                "'shared_child_team_types' entries must be non-empty strings",
                                                f"{location}.coordination.subagent_orchestrator.shared_child_team_types[{i}]",
                                                "Use a list like: [round_evaluator, builder]",
                                            )
                            child_final_answer_strategy = subagent_orchestrator.get("final_answer_strategy")
                            if child_final_answer_strategy is not None and child_final_answer_strategy not in self.VALID_FINAL_ANSWER_STRATEGIES:
                                valid_values = ", ".join(sorted(self.VALID_FINAL_ANSWER_STRATEGIES))
                                result.add_error(
                                    f"Invalid final_answer_strategy: '{child_final_answer_strategy}'",
                                    f"{location}.coordination.subagent_orchestrator.final_answer_strategy",
                                    f"Use one of: {valid_values}",
                                )

                if "subagent_types" in coordination:
                    st = coordination["subagent_types"]
                    if st is not None:
                        if not isinstance(st, list):
                            result.add_error(
                                f"'subagent_types' must be a list of strings or null, got {type(st).__name__}",
                                f"{location}.coordination.subagent_types",
                                "Use a list like: [evaluator, explorer, novelty]",
                            )
                        else:
                            for i, t in enumerate(st):
                                if not isinstance(t, str) or not t.strip():
                                    result.add_error(
                                        "'subagent_types' entries must be non-empty strings",
                                        f"{location}.coordination.subagent_types[{i}]",
                                        "Use type name strings like 'evaluator', 'explorer', 'novelty'",
                                    )

                if "checklist_criteria_preset" in coordination:
                    preset = coordination["checklist_criteria_preset"]
                    if preset is not None:
                        from .evaluation_criteria_generator import (
                            VALID_CRITERIA_PRESETS,
                        )

                        if preset not in VALID_CRITERIA_PRESETS:
                            valid_values = ", ".join(sorted(VALID_CRITERIA_PRESETS))
                            result.add_error(
                                f"Invalid checklist_criteria_preset: '{preset}'",
                                f"{location}.coordination.checklist_criteria_preset",
                                f"Use one of: {valid_values}",
                            )

                if "checklist_criteria_inline" in coordination:
                    inline = coordination["checklist_criteria_inline"]
                    if inline is not None:
                        valid_categories = {"primary", "standard", "stretch", "must", "should", "could"}
                        if not isinstance(inline, list):
                            result.add_error(
                                "checklist_criteria_inline must be a list",
                                f"{location}.coordination.checklist_criteria_inline",
                                "Provide a list of {{text, category}} dicts",
                            )
                        else:
                            for i, item in enumerate(inline):
                                if not isinstance(item, dict):
                                    result.add_error(
                                        f"checklist_criteria_inline[{i}] must be a dict",
                                        f"{location}.coordination.checklist_criteria_inline[{i}]",
                                        "Each item needs 'text' and 'category' keys",
                                    )
                                    continue
                                if "text" not in item or not item.get("text"):
                                    result.add_error(
                                        f"checklist_criteria_inline[{i}] missing 'text'",
                                        f"{location}.coordination.checklist_criteria_inline[{i}]",
                                        "Each criterion needs a 'text' field",
                                    )
                                if "category" not in item:
                                    result.add_error(
                                        f"checklist_criteria_inline[{i}] missing 'category'",
                                        f"{location}.coordination.checklist_criteria_inline[{i}]",
                                        "Each criterion needs a 'category' (primary/standard/stretch)",
                                    )
                                elif item["category"] not in valid_categories:
                                    result.add_error(
                                        f"checklist_criteria_inline[{i}] invalid category: '{item['category']}'",
                                        f"{location}.coordination.checklist_criteria_inline[{i}]",
                                        f"Use one of: {', '.join(sorted(valid_categories))}",
                                    )

                        # Warn if both inline and eval generator are enabled
                        eval_gen = coordination.get("evaluation_criteria_generator", {})
                        if inline and eval_gen.get("enabled", False):
                            result.add_warning(
                                "checklist_criteria_inline is set alongside evaluation_criteria_generator.enabled; " "inline criteria will take priority and generated criteria will be ignored",
                                f"{location}.coordination.checklist_criteria_inline",
                            )

                if "resume_from_log" in coordination:
                    resume = coordination["resume_from_log"]
                    if resume is not None:
                        if not isinstance(resume, dict):
                            result.add_error(
                                "resume_from_log must be a dict with 'log_path' and 'round'",
                                f"{location}.coordination.resume_from_log",
                                "Example: {{log_path: '.massgen/massgen_logs/...', round: 1}}",
                            )
                        else:
                            log_path = resume.get("log_path")
                            resume_round = resume.get("round")

                            if not log_path:
                                result.add_error(
                                    "resume_from_log missing 'log_path'",
                                    f"{location}.coordination.resume_from_log",
                                    "Provide the path to a previous log's turn/attempt directory",
                                )
                            elif not Path(log_path).is_dir():
                                result.add_error(
                                    f"resume_from_log log_path does not exist: {log_path}",
                                    f"{location}.coordination.resume_from_log",
                                    "Provide a valid path to a previous log directory",
                                )
                            else:
                                # Validate agent IDs match
                                metadata_path = Path(log_path) / "execution_metadata.yaml"
                                if metadata_path.exists():
                                    try:
                                        import yaml

                                        metadata = yaml.safe_load(metadata_path.read_text())
                                        nested_resume = metadata.get("config", {}).get("orchestrator", {}).get("coordination", {}).get("resume_from_log")
                                        if nested_resume is not None:
                                            result.add_error(
                                                "resume_from_log cannot target a log that itself used resume_from_log",
                                                f"{location}.coordination.resume_from_log",
                                                "Resume from the original non-resumed run instead",
                                            )
                                        log_agent_ids = sorted(a["id"] for a in metadata.get("config", {}).get("agents", []))
                                        config_agent_ids = sorted(a.get("id", "") for a in (config or {}).get("agents", []))
                                        if log_agent_ids != config_agent_ids:
                                            result.add_error(
                                                f"resume_from_log agent IDs don't match: " f"log has {log_agent_ids}, config has {config_agent_ids}",
                                                f"{location}.coordination.resume_from_log",
                                                "Resume requires the same agent IDs as the original run",
                                            )
                                    except Exception:
                                        pass  # Non-fatal: skip agent ID check if metadata unreadable

                            if resume_round is None:
                                result.add_error(
                                    "resume_from_log missing 'round'",
                                    f"{location}.coordination.resume_from_log",
                                    "Specify which round to resume after (e.g., round: 1)",
                                )
                            elif not isinstance(resume_round, int) or resume_round < 0:
                                result.add_error(
                                    f"resume_from_log 'round' must be a non-negative integer, got: {resume_round}",
                                    f"{location}.coordination.resume_from_log",
                                    "Specify the round number to resume after (0-based)",
                                )

        # Validate voting_sensitivity if present
        if "voting_sensitivity" in orchestrator_config:
            voting_sensitivity = orchestrator_config["voting_sensitivity"]
            if voting_sensitivity not in self.VALID_VOTING_SENSITIVITY:
                valid_values = ", ".join(sorted(self.VALID_VOTING_SENSITIVITY))
                result.add_error(
                    f"Invalid voting_sensitivity: '{voting_sensitivity}'",
                    f"{location}.voting_sensitivity",
                    f"Use one of: {valid_values}",
                )

        # Validate answer_novelty_requirement if present
        if "answer_novelty_requirement" in orchestrator_config:
            answer_novelty = orchestrator_config["answer_novelty_requirement"]
            if answer_novelty not in self.VALID_ANSWER_NOVELTY:
                valid_values = ", ".join(sorted(self.VALID_ANSWER_NOVELTY))
                result.add_error(
                    f"Invalid answer_novelty_requirement: '{answer_novelty}'",
                    f"{location}.answer_novelty_requirement",
                    f"Use one of: {valid_values}",
                )

        # Validate answer cap fields if present (null means unlimited)
        for field_name in ("max_new_answers_per_agent", "max_new_answers_global"):
            if field_name not in orchestrator_config:
                continue
            value = orchestrator_config[field_name]
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                result.add_error(
                    f"'{field_name}' must be a positive integer or null, got {type(value).__name__}",
                    f"{location}.{field_name}",
                    "Use null (unlimited) or a positive integer like 1, 2, or 3",
                )

        if "checklist_require_gap_report" in orchestrator_config:
            checklist_report_gate = orchestrator_config["checklist_require_gap_report"]
            if not isinstance(checklist_report_gate, bool):
                result.add_error(
                    f"'checklist_require_gap_report' must be a boolean, got {type(checklist_report_gate).__name__}",
                    f"{location}.checklist_require_gap_report",
                    "Use true or false",
                )

        if "gap_report_mode" in orchestrator_config:
            gap_mode = orchestrator_config["gap_report_mode"]
            if gap_mode not in self.VALID_GAP_REPORT_MODES:
                valid_values = ", ".join(sorted(self.VALID_GAP_REPORT_MODES))
                result.add_error(
                    f"Invalid gap_report_mode: '{gap_mode}'",
                    f"{location}.gap_report_mode",
                    f"Use one of: {valid_values}",
                )

        # Validate fairness controls if present
        if "fairness_enabled" in orchestrator_config:
            fairness_enabled = orchestrator_config["fairness_enabled"]
            if not isinstance(fairness_enabled, bool):
                result.add_error(
                    f"'fairness_enabled' must be a boolean, got {type(fairness_enabled).__name__}",
                    f"{location}.fairness_enabled",
                    "Use true or false",
                )

        if "fairness_lead_cap_answers" in orchestrator_config:
            lead_cap = orchestrator_config["fairness_lead_cap_answers"]
            if isinstance(lead_cap, bool) or not isinstance(lead_cap, int) or lead_cap < 0:
                result.add_error(
                    f"'fairness_lead_cap_answers' must be a non-negative integer, got {type(lead_cap).__name__}",
                    f"{location}.fairness_lead_cap_answers",
                    "Use 0 (strict lockstep) or a positive integer like 1 or 2",
                )

        if "max_midstream_injections_per_round" in orchestrator_config:
            injection_cap = orchestrator_config["max_midstream_injections_per_round"]
            if isinstance(injection_cap, bool) or not isinstance(injection_cap, int) or injection_cap <= 0:
                result.add_error(
                    f"'max_midstream_injections_per_round' must be a positive integer, got {type(injection_cap).__name__}",
                    f"{location}.max_midstream_injections_per_round",
                    "Use a positive integer like 1 or 2",
                )

        if "defer_peer_updates_until_restart" in orchestrator_config:
            defer_peer_updates = orchestrator_config["defer_peer_updates_until_restart"]
            if not isinstance(defer_peer_updates, bool):
                result.add_error(
                    f"'defer_peer_updates_until_restart' must be a boolean, got {type(defer_peer_updates).__name__}",
                    f"{location}.defer_peer_updates_until_restart",
                    "Use true or false",
                )

        if "allow_midstream_peer_updates_before_checklist_submit" in orchestrator_config:
            allow_midstream = orchestrator_config["allow_midstream_peer_updates_before_checklist_submit"]
            if allow_midstream is not None and not isinstance(allow_midstream, bool):
                result.add_error(
                    ("'allow_midstream_peer_updates_before_checklist_submit' must be " f"a boolean or null, got {type(allow_midstream).__name__}"),
                    f"{location}.allow_midstream_peer_updates_before_checklist_submit",
                    "Use true, false, or null",
                )

        if "max_checklist_calls_per_round" in orchestrator_config:
            checklist_cap = orchestrator_config["max_checklist_calls_per_round"]
            if isinstance(checklist_cap, bool) or not isinstance(checklist_cap, int) or checklist_cap < 1:
                result.add_error(
                    f"'max_checklist_calls_per_round' must be a positive integer >= 1, got {type(checklist_cap).__name__}",
                    f"{location}.max_checklist_calls_per_round",
                    "Use a positive integer like 1 or 2 (default: 1)",
                )

        if "checklist_first_answer" in orchestrator_config:
            cfa = orchestrator_config["checklist_first_answer"]
            if not isinstance(cfa, bool):
                result.add_error(
                    f"'checklist_first_answer' must be a boolean, got {type(cfa).__name__}",
                    f"{location}.checklist_first_answer",
                    "Use true or false (default: false)",
                )

        # Validate timeout if present
        if "timeout" in orchestrator_config:
            timeout = orchestrator_config["timeout"]
            if not isinstance(timeout, dict):
                result.add_error(
                    f"'timeout' must be a dictionary, got {type(timeout).__name__}",
                    f"{location}.timeout",
                    "Use 'orchestrator_timeout_seconds: <number>'",
                )
            elif "orchestrator_timeout_seconds" in timeout:
                value = timeout["orchestrator_timeout_seconds"]
                if not isinstance(value, (int, float)) or value <= 0:
                    result.add_error(
                        "'orchestrator_timeout_seconds' must be a positive number",
                        f"{location}.timeout.orchestrator_timeout_seconds",
                        "Use a value like 1800 (30 minutes)",
                    )

        # Validate boolean fields
        boolean_fields = ["skip_coordination_rounds", "debug_final_answer"]
        for field_name in boolean_fields:
            if field_name in orchestrator_config:
                value = orchestrator_config[field_name]
                # debug_final_answer can be a string or boolean
                if field_name == "debug_final_answer":
                    if not isinstance(value, (bool, str)):
                        result.add_error(
                            f"'{field_name}' must be a boolean or string, got {type(value).__name__}",
                            f"{location}.{field_name}",
                            "Use 'true', 'false', or a string value",
                        )
                else:
                    if not isinstance(value, bool):
                        result.add_error(
                            f"'{field_name}' must be a boolean, got {type(value).__name__}",
                            f"{location}.{field_name}",
                            "Use 'true' or 'false'",
                        )

    def _validate_ui(self, ui_config: dict[str, Any], result: ValidationResult) -> None:
        """Validate UI configuration (Level 6)."""
        location = "ui"

        if not isinstance(ui_config, dict):
            result.add_error(
                f"UI must be a dictionary, got {type(ui_config).__name__}",
                location,
                "Use UI fields like display_type and logging_enabled",
            )
            return

        # Validate display_type if present
        if "display_type" in ui_config:
            display_type = ui_config["display_type"]
            if display_type not in self.VALID_DISPLAY_TYPES:
                valid_types = ", ".join(sorted(self.VALID_DISPLAY_TYPES))
                result.add_error(
                    f"Invalid display_type: '{display_type}'",
                    f"{location}.display_type",
                    f"Use one of: {valid_types}",
                )

        # Validate logging_enabled if present
        if "logging_enabled" in ui_config:
            logging_enabled = ui_config["logging_enabled"]
            if not isinstance(logging_enabled, bool):
                result.add_error(
                    f"'logging_enabled' must be a boolean, got {type(logging_enabled).__name__}",
                    f"{location}.logging_enabled",
                    "Use 'true' or 'false'",
                )

    def _validate_memory(self, memory_config: dict[str, Any], result: ValidationResult) -> None:
        """Validate memory configuration."""
        location = "memory"

        if not isinstance(memory_config, dict):
            result.add_error(
                f"Memory must be a dictionary, got {type(memory_config).__name__}",
                location,
                "Use memory fields like enabled, conversation_memory, persistent_memory, etc.",
            )
            return

        # Validate enabled if present
        if "enabled" in memory_config:
            enabled = memory_config["enabled"]
            if not isinstance(enabled, bool):
                result.add_error(
                    f"'enabled' must be a boolean, got {type(enabled).__name__}",
                    f"{location}.enabled",
                    "Use 'true' or 'false'",
                )

        # Validate conversation_memory if present
        if "conversation_memory" in memory_config:
            conv_memory = memory_config["conversation_memory"]
            if not isinstance(conv_memory, dict):
                result.add_error(
                    f"'conversation_memory' must be a dictionary, got {type(conv_memory).__name__}",
                    f"{location}.conversation_memory",
                    "Use 'enabled: true/false'",
                )
            elif "enabled" in conv_memory:
                enabled = conv_memory["enabled"]
                if not isinstance(enabled, bool):
                    result.add_error(
                        f"'enabled' must be a boolean, got {type(enabled).__name__}",
                        f"{location}.conversation_memory.enabled",
                        "Use 'true' or 'false'",
                    )

        # Validate persistent_memory if present
        if "persistent_memory" in memory_config:
            persist_memory = memory_config["persistent_memory"]
            if not isinstance(persist_memory, dict):
                result.add_error(
                    f"'persistent_memory' must be a dictionary, got {type(persist_memory).__name__}",
                    f"{location}.persistent_memory",
                    "Use fields like enabled, on_disk, vector_store, etc.",
                )
            else:
                # Validate boolean fields
                boolean_fields = ["enabled", "on_disk"]
                for field_name in boolean_fields:
                    if field_name in persist_memory:
                        value = persist_memory[field_name]
                        if not isinstance(value, bool):
                            result.add_error(
                                f"'{field_name}' must be a boolean, got {type(value).__name__}",
                                f"{location}.persistent_memory.{field_name}",
                                "Use 'true' or 'false'",
                            )

                # Validate vector_store if present
                if "vector_store" in persist_memory:
                    vector_store = persist_memory["vector_store"]
                    if not isinstance(vector_store, str):
                        result.add_error(
                            f"'vector_store' must be a string, got {type(vector_store).__name__}",
                            f"{location}.persistent_memory.vector_store",
                            "Use 'qdrant' or other vector store name",
                        )

                # Validate llm config if present
                if "llm" in persist_memory:
                    llm_config = persist_memory["llm"]
                    if not isinstance(llm_config, dict):
                        result.add_error(
                            f"'llm' must be a dictionary, got {type(llm_config).__name__}",
                            f"{location}.persistent_memory.llm",
                            "Use 'provider' and 'model' fields",
                        )
                    else:
                        # Check provider and model are strings
                        for field_name in ["provider", "model"]:
                            if field_name in llm_config:
                                value = llm_config[field_name]
                                if not isinstance(value, str):
                                    result.add_error(
                                        f"'{field_name}' must be a string, got {type(value).__name__}",
                                        f"{location}.persistent_memory.llm.{field_name}",
                                        "Use a string value",
                                    )

                # Validate embedding config if present
                if "embedding" in persist_memory:
                    embedding_config = persist_memory["embedding"]
                    if not isinstance(embedding_config, dict):
                        result.add_error(
                            f"'embedding' must be a dictionary, got {type(embedding_config).__name__}",
                            f"{location}.persistent_memory.embedding",
                            "Use 'provider' and 'model' fields",
                        )
                    else:
                        # Check provider and model are strings
                        for field_name in ["provider", "model"]:
                            if field_name in embedding_config:
                                value = embedding_config[field_name]
                                if not isinstance(value, str):
                                    result.add_error(
                                        f"'{field_name}' must be a string, got {type(value).__name__}",
                                        f"{location}.persistent_memory.embedding.{field_name}",
                                        "Use a string value",
                                    )

                # Validate qdrant config if present
                if "qdrant" in persist_memory:
                    qdrant_config = persist_memory["qdrant"]
                    if not isinstance(qdrant_config, dict):
                        result.add_error(
                            f"'qdrant' must be a dictionary, got {type(qdrant_config).__name__}",
                            f"{location}.persistent_memory.qdrant",
                            "Use 'mode', 'host', 'port' or 'path' fields",
                        )
                    else:
                        # Validate mode if present
                        if "mode" in qdrant_config:
                            mode = qdrant_config["mode"]
                            if mode not in ["server", "local"]:
                                result.add_error(
                                    f"Invalid qdrant mode: '{mode}'",
                                    f"{location}.persistent_memory.qdrant.mode",
                                    "Use 'server' or 'local'",
                                )

                        # Validate port if present (for server mode)
                        if "port" in qdrant_config:
                            port = qdrant_config["port"]
                            if not isinstance(port, int) or port <= 0 or port > 65535:
                                result.add_error(
                                    "'port' must be a valid port number (1-65535)",
                                    f"{location}.persistent_memory.qdrant.port",
                                    "Use a port number like 6333",
                                )

        # Validate compression if present
        if "compression" in memory_config:
            compression = memory_config["compression"]
            if not isinstance(compression, dict):
                result.add_error(
                    f"'compression' must be a dictionary, got {type(compression).__name__}",
                    f"{location}.compression",
                    "Use 'trigger_threshold' and 'target_ratio' fields",
                )
            else:
                # Validate threshold values (should be between 0 and 1)
                for field_name in ["trigger_threshold", "target_ratio"]:
                    if field_name in compression:
                        value = compression[field_name]
                        if not isinstance(value, (int, float)):
                            result.add_error(
                                f"'{field_name}' must be a number, got {type(value).__name__}",
                                f"{location}.compression.{field_name}",
                                "Use a decimal value between 0 and 1",
                            )
                        elif not 0 <= value <= 1:
                            result.add_error(
                                f"'{field_name}' must be between 0 and 1, got {value}",
                                f"{location}.compression.{field_name}",
                                "Use a decimal value between 0 and 1 (e.g., 0.75 for 75%)",
                            )

        # Validate retrieval if present
        if "retrieval" in memory_config:
            retrieval = memory_config["retrieval"]
            if not isinstance(retrieval, dict):
                result.add_error(
                    f"'retrieval' must be a dictionary, got {type(retrieval).__name__}",
                    f"{location}.retrieval",
                    "Use 'limit' and 'exclude_recent' fields",
                )
            else:
                # Validate limit if present
                if "limit" in retrieval:
                    limit = retrieval["limit"]
                    if not isinstance(limit, int) or limit <= 0:
                        result.add_error(
                            "'limit' must be a positive integer",
                            f"{location}.retrieval.limit",
                            "Use a value like 5 or 10",
                        )

                # Validate exclude_recent if present
                if "exclude_recent" in retrieval:
                    exclude_recent = retrieval["exclude_recent"]
                    if not isinstance(exclude_recent, bool):
                        result.add_error(
                            f"'exclude_recent' must be a boolean, got {type(exclude_recent).__name__}",
                            f"{location}.retrieval.exclude_recent",
                            "Use 'true' or 'false'",
                        )

    def _check_warnings(self, config: dict[str, Any], result: ValidationResult) -> None:
        """Check for warnings (best practices, deprecations, etc.)."""
        # Get agents list (normalize single agent to list)
        if "agents" in config:
            agents = config["agents"]
            if not isinstance(agents, list):
                return
        elif "agent" in config:
            agents = [config["agent"]]
        else:
            return

        # Check each agent's backend for warnings
        for i, agent_config in enumerate(agents):
            if not isinstance(agent_config, dict) or "backend" not in agent_config:
                continue

            agent_location = f"agents[{i}]" if "agents" in config else "agent"
            backend_config = agent_config["backend"]

            if not isinstance(backend_config, dict):
                continue

            # Warning: Using both allowed_tools and exclude_tools
            if "allowed_tools" in backend_config and "exclude_tools" in backend_config:
                result.add_warning(
                    "Using both 'allowed_tools' and 'exclude_tools' can be confusing",
                    f"{agent_location}.backend",
                    "Prefer using only 'allowed_tools' (explicit allowlist) or 'exclude_tools' (denylist)",
                )

            # Warning: Check for deprecated fields (add as needed)
            # This is a placeholder for future deprecations

        # Cross-validation: checklist_gated + changedoc
        orchestrator_cfg = config.get("orchestrator", {})
        if isinstance(orchestrator_cfg, dict):
            voting_sens = orchestrator_cfg.get("voting_sensitivity", "")
            coordination = orchestrator_cfg.get("coordination", {})
            if isinstance(coordination, dict):
                changedoc_enabled = coordination.get("enable_changedoc", True)
                if voting_sens == "checklist_gated" and changedoc_enabled is False:
                    result.add_warning(
                        "checklist_gated voting works best with changedoc enabled for integrated quality assessment",
                        "orchestrator.voting_sensitivity",
                        "Set coordination.enable_changedoc: true or use gap_report_mode: 'separate'",
                    )
                round_eval_before_checklist = coordination.get("round_evaluator_before_checklist", False)
                orchestrator_managed_round_evaluator = coordination.get("orchestrator_managed_round_evaluator", False)
                if orchestrator_managed_round_evaluator and not round_eval_before_checklist:
                    result.add_error(
                        "orchestrator_managed_round_evaluator requires round_evaluator_before_checklist: true",
                        "orchestrator.coordination.orchestrator_managed_round_evaluator",
                        "Enable round_evaluator_before_checklist or remove orchestrator_managed_round_evaluator",
                    )
                if round_eval_before_checklist and not orchestrator_managed_round_evaluator:
                    result.add_error(
                        "round_evaluator_before_checklist requires orchestrator_managed_round_evaluator: true",
                        "orchestrator.coordination.round_evaluator_before_checklist",
                        "Enable orchestrator_managed_round_evaluator so the evaluator stage is orchestrator-managed",
                    )
                round_evaluator_refine = coordination.get("round_evaluator_refine", False)
                if round_evaluator_refine and not orchestrator_managed_round_evaluator:
                    result.add_error(
                        "round_evaluator_refine requires orchestrator_managed_round_evaluator: true",
                        "orchestrator.coordination.round_evaluator_refine",
                        "Enable orchestrator_managed_round_evaluator or remove round_evaluator_refine",
                    )
                if round_eval_before_checklist:
                    if len(agents) != 1:
                        result.add_error(
                            "round_evaluator_before_checklist currently supports single-parent runs only",
                            "orchestrator.coordination.round_evaluator_before_checklist",
                            "Use exactly one top-level agent when enabling the round evaluator stage",
                        )
                    if voting_sens != "checklist_gated":
                        result.add_error(
                            "round_evaluator_before_checklist requires orchestrator.voting_sensitivity: checklist_gated",
                            "orchestrator.coordination.round_evaluator_before_checklist",
                            "Set orchestrator.voting_sensitivity: checklist_gated",
                        )
                    if coordination.get("enable_subagents") is not True:
                        result.add_error(
                            "round_evaluator_before_checklist requires enable_subagents: true",
                            "orchestrator.coordination.enable_subagents",
                            "Enable subagents so the parent can spawn the round_evaluator child run",
                        )
                    subagent_orchestrator = coordination.get("subagent_orchestrator")
                    if not isinstance(subagent_orchestrator, dict) or subagent_orchestrator.get("enabled") is not True:
                        result.add_error(
                            "round_evaluator_before_checklist requires subagent_orchestrator.enabled: true",
                            "orchestrator.coordination.subagent_orchestrator",
                            "Provide an enabled child subagent orchestrator for the evaluator team",
                        )
                    subagent_types = coordination.get("subagent_types")
                    if not isinstance(subagent_types, list) or "round_evaluator" not in subagent_types:
                        result.add_error(
                            "round_evaluator_before_checklist requires subagent_types to include 'round_evaluator'",
                            "orchestrator.coordination.subagent_types",
                            "Set coordination.subagent_types to a list containing 'round_evaluator'",
                        )
                    if coordination.get("round_evaluator_skip_synthesis") is True:
                        result.add_error(
                            "round_evaluator_skip_synthesis is incompatible with the managed round evaluator stage",
                            "orchestrator.coordination.round_evaluator_skip_synthesis",
                            "Remove round_evaluator_skip_synthesis so the parent receives one synthesized evaluator packet",
                        )

        # Cross-validation: decomposition mode
        if isinstance(orchestrator_cfg, dict):
            coordination_mode = orchestrator_cfg.get("coordination_mode")
            if coordination_mode == "decomposition":
                # Collect agent IDs
                agent_ids = []
                for agent_config in agents:
                    if isinstance(agent_config, dict) and "id" in agent_config:
                        agent_ids.append(agent_config["id"])

                # Validate presenter_agent references a valid agent
                presenter = orchestrator_cfg.get("presenter_agent")
                if presenter and presenter not in agent_ids:
                    result.add_error(
                        f"presenter_agent '{presenter}' does not match any agent ID",
                        "orchestrator.presenter_agent",
                        f"Use one of: {', '.join(agent_ids)}",
                    )

                # Warn if no subtasks defined (runtime decomposition subagent will be used)
                has_subtasks = any(isinstance(a, dict) and "subtask" in a for a in agents)
                if not has_subtasks:
                    result.add_warning(
                        "No explicit 'subtask' fields defined on agents in decomposition mode",
                        "orchestrator.coordination_mode",
                        "MassGen will spawn a decomposition subagent at runtime to assign subtasks. Add 'subtask' per agent for deterministic assignments.",
                    )
