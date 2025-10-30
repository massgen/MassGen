# -*- coding: utf-8 -*-
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
from typing import Any, Dict, List, Optional

import yaml

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
    suggestion: Optional[str] = None
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

    errors: List[ValidationIssue] = field(default_factory=list)
    warnings: List[ValidationIssue] = field(default_factory=list)

    def add_error(self, message: str, location: str, suggestion: Optional[str] = None) -> None:
        """Add a validation error."""
        self.errors.append(ValidationIssue(message, location, suggestion, "error"))

    def add_warning(self, message: str, location: str, suggestion: Optional[str] = None) -> None:
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

    def to_dict(self) -> Dict[str, Any]:
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
    VALID_DISPLAY_TYPES = {"rich_terminal", "simple"}

    # Valid voting sensitivity levels
    VALID_VOTING_SENSITIVITY = {"lenient", "balanced", "strict"}

    # Valid answer novelty requirements
    VALID_ANSWER_NOVELTY = {"lenient", "balanced", "strict"}

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
            with open(path, "r") as f:
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

    def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
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
            self._validate_orchestrator(config["orchestrator"], result)

        # Validate UI (if present)
        if "ui" in config:
            self._validate_ui(config["ui"], result)

        # Validate memory (if present)
        if "memory" in config:
            self._validate_memory(config["memory"], result)

        # Check for warnings (best practices, deprecations, etc.)
        self._check_warnings(config, result)

        return result

    def _check_v1_keywords(self, config: Dict[str, Any], result: ValidationResult) -> None:
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

    def _validate_top_level(self, config: Dict[str, Any], result: ValidationResult) -> None:
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

    def _validate_agents(self, config: Dict[str, Any], result: ValidationResult) -> None:
        """Validate agent configurations (Level 2)."""
        # Get agents list (normalize single agent to list)
        if "agents" in config:
            agents = config["agents"]
            if not isinstance(agents, list):
                return  # Already reported error in _validate_top_level
        else:
            agents = [config["agent"]]

        # Track agent IDs for duplicate detection
        agent_ids: List[str] = []

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

    def _validate_backend(self, backend_config: Dict[str, Any], location: str, result: ValidationResult) -> None:
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
            "enable_code_execution",
            "enable_code_interpreter",
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

    def _validate_tool_filtering(
        self,
        backend_config: Dict[str, Any],
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

    def _validate_orchestrator(self, orchestrator_config: Dict[str, Any], result: ValidationResult) -> None:
        """Validate orchestrator configuration (Level 5)."""
        location = "orchestrator"

        if not isinstance(orchestrator_config, dict):
            result.add_error(
                f"Orchestrator must be a dictionary, got {type(orchestrator_config).__name__}",
                location,
                "Use orchestrator fields like snapshot_storage, context_paths, etc.",
            )
            return

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
                # Validate boolean fields
                boolean_fields = ["enable_planning_mode"]
                for field_name in boolean_fields:
                    if field_name in coordination:
                        value = coordination[field_name]
                        if not isinstance(value, bool):
                            result.add_error(
                                f"'{field_name}' must be a boolean, got {type(value).__name__}",
                                f"{location}.coordination.{field_name}",
                                "Use 'true' or 'false'",
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

    def _validate_ui(self, ui_config: Dict[str, Any], result: ValidationResult) -> None:
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

    def _validate_memory(self, memory_config: Dict[str, Any], result: ValidationResult) -> None:
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

    def _check_warnings(self, config: Dict[str, Any], result: ValidationResult) -> None:
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
