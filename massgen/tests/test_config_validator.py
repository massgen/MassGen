# -*- coding: utf-8 -*-
"""
Tests for configuration validator.

Tests cover:
- Valid configs (should pass)
- Missing required fields
- Invalid types and values
- Backend-specific validation
- V1 config rejection
- Warning generation
- Error reporting format
"""

import json
import tempfile
from pathlib import Path

import yaml

from massgen.config_validator import ConfigValidator, ValidationResult


class TestConfigValidator:
    """Test suite for ConfigValidator."""

    def test_valid_single_agent_config(self):
        """Test validation of a valid single agent config."""
        config = {
            "agent": {
                "id": "test-agent",
                "backend": {"type": "openai", "model": "gpt-4o"},
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert result.is_valid()
        assert not result.has_errors()

    def test_valid_multi_agent_config(self):
        """Test validation of a valid multi-agent config."""
        config = {
            "agents": [
                {
                    "id": "agent-1",
                    "backend": {"type": "openai", "model": "gpt-4o"},
                },
                {
                    "id": "agent-2",
                    "backend": {"type": "claude", "model": "claude-sonnet-4-5-20250929"},
                },
            ],
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert result.is_valid()
        assert not result.has_errors()

    def test_valid_config_with_orchestrator(self):
        """Test validation of config with orchestrator settings."""
        config = {
            "agents": [
                {
                    "id": "agent-1",
                    "backend": {"type": "openai", "model": "gpt-4o"},
                },
            ],
            "orchestrator": {
                "voting_sensitivity": "balanced",
                "answer_novelty_requirement": "strict",
                "coordination": {
                    "enable_planning_mode": True,
                    "max_orchestration_restarts": 2,
                },
                "timeout": {
                    "orchestrator_timeout_seconds": 1800,
                },
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert result.is_valid()
        assert not result.has_errors()

    def test_valid_config_with_ui(self):
        """Test validation of config with UI settings."""
        config = {
            "agent": {
                "id": "test-agent",
                "backend": {"type": "openai", "model": "gpt-4o"},
            },
            "ui": {
                "display_type": "rich_terminal",
                "logging_enabled": True,
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert result.is_valid()
        assert not result.has_errors()

    def test_v1_config_rejected(self):
        """Test that V1 configs are rejected with helpful error."""
        config = {
            "models": ["gpt-4o", "claude-3-opus"],
            "num_agents": 2,
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert result.has_errors()
        assert any("V1 config format detected" in error.message for error in result.errors)
        assert any("migrate" in error.suggestion.lower() for error in result.errors if error.suggestion)

    def test_missing_agents_field(self):
        """Test error when neither 'agents' nor 'agent' is present."""
        config = {
            "orchestrator": {},
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("must have either 'agents'" in error.message for error in result.errors)

    def test_both_agents_and_agent(self):
        """Test error when both 'agents' and 'agent' are present."""
        config = {
            "agents": [{"id": "a1", "backend": {"type": "openai", "model": "gpt-4o"}}],
            "agent": {"id": "a2", "backend": {"type": "openai", "model": "gpt-4o"}},
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("cannot have both 'agents' and 'agent'" in error.message for error in result.errors)

    def test_missing_agent_id(self):
        """Test error when agent is missing required 'id' field."""
        config = {
            "agent": {
                "backend": {"type": "openai", "model": "gpt-4o"},
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("missing required field 'id'" in error.message for error in result.errors)

    def test_missing_backend(self):
        """Test error when agent is missing required 'backend' field."""
        config = {
            "agent": {
                "id": "test-agent",
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("missing required field 'backend'" in error.message for error in result.errors)

    def test_duplicate_agent_ids(self):
        """Test error when multiple agents have the same ID."""
        config = {
            "agents": [
                {"id": "agent-1", "backend": {"type": "openai", "model": "gpt-4o"}},
                {"id": "agent-1", "backend": {"type": "claude", "model": "claude-sonnet-4-5-20250929"}},
            ],
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("Duplicate agent ID" in error.message for error in result.errors)

    def test_missing_backend_type(self):
        """Test error when backend is missing required 'type' field."""
        config = {
            "agent": {
                "id": "test-agent",
                "backend": {"model": "gpt-4o"},
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("missing required field 'type'" in error.message for error in result.errors)

    def test_missing_backend_model(self):
        """Test error when backend is missing required 'model' field."""
        config = {
            "agent": {
                "id": "test-agent",
                "backend": {"type": "chatcompletion"},  # Uses default_model="custom", requires explicit model
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("missing required field 'model'" in error.message for error in result.errors)

    def test_unknown_backend_type(self):
        """Test error when backend type is not recognized."""
        config = {
            "agent": {
                "id": "test-agent",
                "backend": {"type": "unknown_backend", "model": "some-model"},
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("Unknown backend type" in error.message for error in result.errors)

    def test_invalid_permission_mode(self):
        """Test error when permission_mode has invalid value."""
        config = {
            "agent": {
                "id": "test-agent",
                "backend": {
                    "type": "claude_code",
                    "model": "claude-sonnet-4-5-20250929",
                    "permission_mode": "invalid_mode",
                },
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("Invalid permission_mode" in error.message for error in result.errors)

    def test_backend_capability_validation(self):
        """Test that backend capabilities are validated."""
        config = {
            "agent": {
                "id": "test-agent",
                "backend": {
                    "type": "lmstudio",  # lmstudio doesn't support web_search
                    "model": "custom",
                    "enable_web_search": True,
                },
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("does not support" in error.message for error in result.errors)

    def test_invalid_display_type(self):
        """Test error when UI display_type is invalid."""
        config = {
            "agent": {
                "id": "test-agent",
                "backend": {"type": "openai", "model": "gpt-4o"},
            },
            "ui": {
                "display_type": "invalid_type",
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("Invalid display_type" in error.message for error in result.errors)

    def test_invalid_voting_sensitivity(self):
        """Test error when voting_sensitivity is invalid."""
        config = {
            "agents": [
                {"id": "agent-1", "backend": {"type": "openai", "model": "gpt-4o"}},
            ],
            "orchestrator": {
                "voting_sensitivity": "invalid_value",
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("Invalid voting_sensitivity" in error.message for error in result.errors)

    def test_invalid_context_path_permission(self):
        """Test error when context_paths permission is invalid."""
        config = {
            "agents": [
                {"id": "agent-1", "backend": {"type": "openai", "model": "gpt-4o"}},
            ],
            "orchestrator": {
                "context_paths": [
                    {"path": "/some/path", "permission": "invalid_permission"},
                ],
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("Invalid permission" in error.message for error in result.errors)

    def test_warning_both_allowed_and_exclude_tools(self):
        """Test warning when both allowed_tools and exclude_tools are used."""
        config = {
            "agent": {
                "id": "test-agent",
                "backend": {
                    "type": "claude_code",
                    "model": "claude-sonnet-4-5-20250929",
                    "allowed_tools": ["Read", "Write"],
                    "exclude_tools": ["Bash"],
                },
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert result.is_valid()  # No errors
        assert result.has_warnings()
        assert any("both 'allowed_tools' and 'exclude_tools'" in warning.message for warning in result.warnings)

    def test_no_warning_missing_system_message(self):
        """Test that missing system_message doesn't generate a warning."""
        config = {
            "agent": {
                "id": "test-agent",
                "backend": {"type": "openai", "model": "gpt-4o"},
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert result.is_valid()
        # Should not have warnings about missing system_message
        assert not any("system_message" in warning.message.lower() for warning in result.warnings)

    def test_no_warning_multi_agent_no_orchestrator(self):
        """Test that multi-agent setup without orchestrator doesn't generate a warning."""
        config = {
            "agents": [
                {"id": "agent-1", "backend": {"type": "openai", "model": "gpt-4o"}},
                {"id": "agent-2", "backend": {"type": "claude", "model": "claude-sonnet-4-5-20250929"}},
            ],
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert result.is_valid()
        # Should not have warnings about missing orchestrator
        assert not any("orchestrator" in warning.message.lower() for warning in result.warnings)

    def test_invalid_type_field_types(self):
        """Test errors for wrong field types."""
        config = {
            "agent": {
                "id": 123,  # Should be string
                "backend": {
                    "type": "openai",
                    "model": "gpt-4o",
                    "enable_web_search": "yes",  # Should be boolean
                },
                "system_message": ["not", "a", "string"],  # Should be string
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert len(result.errors) >= 2  # Multiple type errors

    def test_validate_file_not_found(self):
        """Test validation of non-existent file."""
        validator = ConfigValidator()
        result = validator.validate_config_file("/nonexistent/config.yaml")

        assert not result.is_valid()
        assert any("Config file not found" in error.message for error in result.errors)

    def test_validate_yaml_file(self):
        """Test validation of a YAML file."""
        config = {
            "agent": {
                "id": "test-agent",
                "backend": {"type": "openai", "model": "gpt-4o"},
            },
        }

        # Create temporary YAML file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            temp_path = f.name

        try:
            validator = ConfigValidator()
            result = validator.validate_config_file(temp_path)

            assert result.is_valid()
            assert not result.has_errors()
        finally:
            Path(temp_path).unlink()

    def test_validate_json_file(self):
        """Test validation of a JSON file."""
        config = {
            "agent": {
                "id": "test-agent",
                "backend": {"type": "openai", "model": "gpt-4o"},
            },
        }

        # Create temporary JSON file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config, f)
            temp_path = f.name

        try:
            validator = ConfigValidator()
            result = validator.validate_config_file(temp_path)

            assert result.is_valid()
            assert not result.has_errors()
        finally:
            Path(temp_path).unlink()

    def test_validation_result_to_dict(self):
        """Test conversion of ValidationResult to dict."""
        result = ValidationResult()
        result.add_error("Test error", "test.location", "Test suggestion")
        result.add_warning("Test warning", "test.location", "Test suggestion")

        result_dict = result.to_dict()

        assert result_dict["valid"] is False
        assert result_dict["error_count"] == 1
        assert result_dict["warning_count"] == 1
        assert len(result_dict["errors"]) == 1
        assert len(result_dict["warnings"]) == 1
        assert result_dict["errors"][0]["message"] == "Test error"
        assert result_dict["warnings"][0]["message"] == "Test warning"

    def test_validation_result_format_errors(self):
        """Test error formatting."""
        result = ValidationResult()
        result.add_error("Test error message", "config.agent.backend", "Use correct type")

        formatted = result.format_errors()

        assert "Configuration Errors Found" in formatted
        assert "Test error message" in formatted
        assert "config.agent.backend" in formatted
        assert "Use correct type" in formatted

    def test_validation_result_format_warnings(self):
        """Test warning formatting."""
        result = ValidationResult()
        result.add_warning("Test warning message", "config.agent", "Add system_message")

        formatted = result.format_warnings()

        assert "Configuration Warnings" in formatted
        assert "Test warning message" in formatted
        assert "config.agent" in formatted
        assert "Add system_message" in formatted

    def test_tool_filtering_validation(self):
        """Test validation of tool filtering lists."""
        config = {
            "agent": {
                "id": "test-agent",
                "backend": {
                    "type": "claude_code",
                    "model": "claude-sonnet-4-5-20250929",
                    "allowed_tools": "not-a-list",  # Should be list
                },
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("'allowed_tools' must be a list" in error.message for error in result.errors)

    def test_mcp_servers_validation(self):
        """Test that MCP server configs are validated."""
        config = {
            "agent": {
                "id": "test-agent",
                "backend": {
                    "type": "claude",
                    "model": "claude-sonnet-4-5-20250929",
                    "mcp_servers": "invalid-format",  # Should trigger MCP validator
                },
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        # Should have error from MCP validation
        assert not result.is_valid()

    def test_complex_valid_config(self):
        """Test a complex but valid configuration."""
        config = {
            "agents": [
                {
                    "id": "researcher",
                    "backend": {
                        "type": "openai",
                        "model": "gpt-4o",
                        "enable_web_search": True,
                    },
                    "system_message": "You are a research assistant.",
                },
                {
                    "id": "analyst",
                    "backend": {
                        "type": "claude",
                        "model": "claude-sonnet-4-5-20250929",
                        "enable_code_execution": True,
                    },
                    "system_message": "You are a data analyst.",
                },
            ],
            "orchestrator": {
                "voting_sensitivity": "balanced",
                "answer_novelty_requirement": "lenient",
                "coordination": {
                    "enable_planning_mode": False,
                    "max_orchestration_restarts": 1,
                },
                "context_paths": [
                    {"path": "/data", "permission": "read"},
                    {"path": "/output", "permission": "write"},
                ],
                "timeout": {
                    "orchestrator_timeout_seconds": 3600,
                },
            },
            "ui": {
                "display_type": "rich_terminal",
                "logging_enabled": True,
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert result.is_valid()
        # May have warnings but should have no errors
        assert not result.has_errors()


class TestCommonBadConfigs:
    """Test suite for common configuration mistakes users might make."""

    def test_v1_config_with_models_list(self):
        """Test V1 config with models list is rejected."""
        config = {
            "models": ["gpt-4o", "claude-3-opus"],
            "num_agents": 2,
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("V1 config format detected" in error.message for error in result.errors)
        assert any("migrate" in error.suggestion.lower() for error in result.errors if error.suggestion)

    def test_v1_config_with_model_configs(self):
        """Test V1 config with model_configs is rejected."""
        config = {
            "model_configs": {
                "gpt-4o": {"temperature": 0.7},
                "claude-3-opus": {"temperature": 0.5},
            },
            "agents": [{"id": "test"}],  # Even with agents present
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("V1 config" in error.message for error in result.errors)

    def test_missing_both_agents_and_agent(self):
        """Test config without agents or agent field."""
        config = {
            "orchestrator": {},
            "ui": {"display_type": "simple"},
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("must have either 'agents'" in error.message for error in result.errors)

    def test_typo_in_backend_type(self):
        """Test common typo in backend type."""
        config = {
            "agent": {
                "id": "test-agent",
                "backend": {
                    "type": "openi",  # Common typo
                    "model": "gpt-4o",
                },
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("Unknown backend type: 'openi'" in error.message for error in result.errors)
        assert any("openai" in error.suggestion for error in result.errors if error.suggestion)

    def test_wrong_case_backend_type(self):
        """Test wrong case in backend type."""
        config = {
            "agent": {
                "id": "test-agent",
                "backend": {
                    "type": "OpenAI",  # Should be lowercase
                    "model": "gpt-4o",
                },
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("Unknown backend type" in error.message for error in result.errors)

    def test_unsupported_feature_for_backend(self):
        """Test requesting unsupported feature from backend."""
        config = {
            "agent": {
                "id": "test-agent",
                "backend": {
                    "type": "lmstudio",
                    "model": "custom",
                    "enable_web_search": True,  # lmstudio doesn't support this
                },
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("does not support web_search" in error.message for error in result.errors)

    def test_boolean_as_string(self):
        """Test using string instead of boolean."""
        config = {
            "agent": {
                "id": "test-agent",
                "backend": {
                    "type": "openai",
                    "model": "gpt-4o",
                    "enable_web_search": "true",  # Should be boolean true
                },
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("must be a boolean" in error.message for error in result.errors)

    def test_number_as_string(self):
        """Test using string for numeric field."""
        config = {
            "agents": [
                {"id": "test", "backend": {"type": "openai", "model": "gpt-4o"}},
            ],
            "orchestrator": {
                "timeout": {
                    "orchestrator_timeout_seconds": "1800",  # Should be number
                },
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("must be a positive number" in error.message for error in result.errors)

    def test_invalid_display_type_typo(self):
        """Test typo in display_type."""
        config = {
            "agent": {
                "id": "test-agent",
                "backend": {"type": "openai", "model": "gpt-4o"},
            },
            "ui": {
                "display_type": "detailed",  # Not a valid type
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("Invalid display_type" in error.message for error in result.errors)
        assert any("rich_terminal" in error.suggestion for error in result.errors if error.suggestion)

    def test_invalid_permission_mode(self):
        """Test invalid permission_mode value."""
        config = {
            "agent": {
                "id": "test-agent",
                "backend": {
                    "type": "claude_code",
                    "model": "claude-sonnet-4-5-20250929",
                    "permission_mode": "auto",  # Not valid
                },
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("Invalid permission_mode" in error.message for error in result.errors)

    def test_context_path_wrong_permission(self):
        """Test wrong permission value in context_paths."""
        config = {
            "agents": [
                {"id": "test", "backend": {"type": "openai", "model": "gpt-4o"}},
            ],
            "orchestrator": {
                "context_paths": [
                    {"path": "/data", "permission": "readonly"},  # Should be "read"
                ],
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("Invalid permission" in error.message for error in result.errors)
        assert any("'read' or 'write'" in error.suggestion for error in result.errors if error.suggestion)

    def test_negative_timeout(self):
        """Test negative timeout value."""
        config = {
            "agents": [
                {"id": "test", "backend": {"type": "openai", "model": "gpt-4o"}},
            ],
            "orchestrator": {
                "timeout": {
                    "orchestrator_timeout_seconds": -100,  # Negative
                },
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("must be a positive number" in error.message for error in result.errors)

    def test_negative_max_restarts(self):
        """Test negative max_orchestration_restarts."""
        config = {
            "agents": [
                {"id": "test", "backend": {"type": "openai", "model": "gpt-4o"}},
            ],
            "orchestrator": {
                "coordination": {
                    "max_orchestration_restarts": -1,  # Negative
                },
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("must be a non-negative integer" in error.message for error in result.errors)

    def test_agent_without_id(self):
        """Test agent missing id field (common mistake)."""
        config = {
            "agents": [
                {
                    # Missing id
                    "backend": {"type": "openai", "model": "gpt-4o"},
                },
            ],
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("missing required field 'id'" in error.message for error in result.errors)

    def test_agent_without_backend(self):
        """Test agent missing backend field (common mistake)."""
        config = {
            "agents": [
                {
                    "id": "test-agent",
                    # Missing backend
                },
            ],
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("missing required field 'backend'" in error.message for error in result.errors)

    def test_tools_list_with_non_strings(self):
        """Test tool filtering with non-string values."""
        config = {
            "agent": {
                "id": "test-agent",
                "backend": {
                    "type": "claude_code",
                    "model": "claude-sonnet-4-5-20250929",
                    "allowed_tools": ["Read", 123, "Write"],  # 123 is not a string
                },
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("must be a string" in error.message for error in result.errors)

    def test_mcp_servers_wrong_type(self):
        """Test mcp_servers as wrong type."""
        config = {
            "agent": {
                "id": "test-agent",
                "backend": {
                    "type": "claude",
                    "model": "claude-sonnet-4-5-20250929",
                    "mcp_servers": "filesystem",  # Should be list or dict
                },
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("MCP configuration error" in error.message for error in result.errors)

    def test_invalid_voting_sensitivity(self):
        """Test invalid voting_sensitivity value."""
        config = {
            "agents": [
                {"id": "test", "backend": {"type": "openai", "model": "gpt-4o"}},
            ],
            "orchestrator": {
                "voting_sensitivity": "medium",  # Should be lenient/balanced/strict
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("Invalid voting_sensitivity" in error.message for error in result.errors)

    def test_invalid_answer_novelty(self):
        """Test invalid answer_novelty_requirement value."""
        config = {
            "agents": [
                {"id": "test", "backend": {"type": "openai", "model": "gpt-4o"}},
            ],
            "orchestrator": {
                "answer_novelty_requirement": "high",  # Should be lenient/balanced/strict
            },
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("Invalid answer_novelty_requirement" in error.message for error in result.errors)

    def test_v1_max_rounds(self):
        """Test V1 max_rounds parameter is rejected."""
        config = {
            "agents": [
                {"id": "test", "backend": {"type": "openai", "model": "gpt-4o"}},
            ],
            "max_rounds": 5,  # V1 parameter
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("V1 config format detected" in error.message for error in result.errors)
        assert any("max_rounds" in error.message for error in result.errors)

    def test_v1_consensus_threshold(self):
        """Test V1 consensus_threshold parameter is rejected."""
        config = {
            "agents": [
                {"id": "test", "backend": {"type": "openai", "model": "gpt-4o"}},
            ],
            "consensus_threshold": 0.6,  # V1 parameter
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("V1 config format detected" in error.message for error in result.errors)
        assert any("consensus_threshold" in error.message for error in result.errors)

    def test_v1_voting_enabled(self):
        """Test V1 voting_enabled parameter is rejected."""
        config = {
            "agents": [
                {"id": "test", "backend": {"type": "openai", "model": "gpt-4o"}},
            ],
            "voting_enabled": True,  # V1 parameter
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("V1 config format detected" in error.message for error in result.errors)
        assert any("voting_enabled" in error.message for error in result.errors)

    def test_v1_multiple_keywords(self):
        """Test config with multiple V1 keywords."""
        config = {
            "agents": [
                {"id": "test", "backend": {"type": "openai", "model": "gpt-4o"}},
            ],
            "max_rounds": 5,
            "voting_enabled": True,
            "consensus_threshold": 0.6,
        }

        validator = ConfigValidator()
        result = validator.validate_config(config)

        assert not result.is_valid()
        assert any("V1 config format detected" in error.message for error in result.errors)
        # Should mention all found V1 keywords
        error_messages = " ".join([e.message for e in result.errors])
        assert "max_rounds" in error_messages
        assert "voting_enabled" in error_messages
        assert "consensus_threshold" in error_messages
