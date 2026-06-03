"""Locks the pydantic config migration: config models now validate on construction.

Before the migration these were plain dataclasses that silently accepted any
type and let ``from_dict`` override non-None defaults with None. These tests pin
the new behavior so a regression (e.g. reverting to a plain dataclass) is caught.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from massgen.agent_config import (
    AgentConfig,
    CoordinationConfig,
    PromptImproverConfig,
    StepModeConfig,
    TimeoutConfig,
)
from massgen.evaluation_criteria_generator import EvaluationCriteriaGeneratorConfig
from massgen.persona_generator import PersonaGeneratorConfig
from massgen.task_decomposer import TaskDecomposerConfig

ALL_CONFIG_CLASSES = [
    StepModeConfig,
    TimeoutConfig,
    PromptImproverConfig,
    CoordinationConfig,
    AgentConfig,
    PersonaGeneratorConfig,
    EvaluationCriteriaGeneratorConfig,
    TaskDecomposerConfig,
]


class TestConfigsAreValidated:
    def test_all_config_classes_are_pydantic_validated(self):
        # pydantic.dataclasses attach a __pydantic_validator__; plain dataclasses don't.
        for cls in ALL_CONFIG_CLASSES:
            assert hasattr(cls, "__pydantic_validator__"), f"{cls.__name__} is not pydantic-validated"

    def test_all_config_classes_still_construct_with_defaults(self):
        for cls in ALL_CONFIG_CLASSES:
            cls()  # must not raise


class TestValidationCatchesBadTypes:
    def test_timeout_rejects_non_int(self):
        with pytest.raises(ValidationError):
            TimeoutConfig(orchestrator_timeout_seconds="not-an-int")

    def test_timeout_coerces_numeric_string(self):
        # Lax coercion (preserves permissive YAML behavior for well-formed values).
        assert TimeoutConfig(orchestrator_timeout_seconds="600").orchestrator_timeout_seconds == 600

    def test_eval_criteria_rejects_non_int_bounds(self):
        with pytest.raises(ValidationError):
            EvaluationCriteriaGeneratorConfig(min_criteria="lots")


class TestFromDictDefaultFix:
    def test_from_dict_empty_uses_field_default_not_none(self):
        # Regression: from_dict({}) previously produced write_mode=None (overriding
        # the "auto" default). It must now respect the default.
        assert CoordinationConfig.from_dict({}).write_mode == "auto"

    def test_from_dict_explicit_value_wins(self):
        assert CoordinationConfig.from_dict({"write_mode": "worktree"}).write_mode == "worktree"

    def test_from_dict_preserves_other_defaults(self):
        cc = CoordinationConfig.from_dict({})
        assert cc.broadcast is False
        assert cc.learning_capture_mode == "round"


class TestModeLiterals:
    def test_invalid_write_mode_rejected(self):
        with pytest.raises(ValidationError):
            CoordinationConfig(write_mode="bogus")

    def test_invalid_coordination_mode_rejected(self):
        with pytest.raises(ValidationError):
            AgentConfig(coordination_mode="nonsense")

    def test_valid_modes_accepted(self):
        assert CoordinationConfig(write_mode="worktree").write_mode == "worktree"
        assert AgentConfig(coordination_mode="decomposition").coordination_mode == "decomposition"


class TestUnknownKeyDetection:
    def test_unknown_coordination_key_warns(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="massgen.agent_config"):
            CoordinationConfig.from_dict({"coordnation_mode": "voting"})  # typo
        assert any("Unknown orchestrator.coordination key" in r.message for r in caplog.records)

    def test_known_keys_do_not_warn(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="massgen.agent_config"):
            CoordinationConfig.from_dict({"write_mode": "auto", "broadcast": False, "use_skills": True})
        assert not any("Unknown orchestrator.coordination key" in r.message for r in caplog.records)

    def test_unknown_timeout_key_warns(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="massgen.agent_config"):
            TimeoutConfig.from_dict({"orchestrator_timeout_secondz": 60})  # typo
        assert any("Unknown timeout_settings key" in r.message for r in caplog.records)

    def test_known_timeout_keys_do_not_warn(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="massgen.agent_config"):
            TimeoutConfig.from_dict({"orchestrator_timeout_seconds": 60})
        assert not any("Unknown timeout_settings key" in r.message for r in caplog.records)


class TestNestedValidation:
    def test_nested_config_objects_are_typed_instances(self):
        a = AgentConfig()
        assert isinstance(a.coordination_config, CoordinationConfig)
        assert isinstance(a.timeout_config, TimeoutConfig)
        assert isinstance(a.coordination_config.persona_generator, PersonaGeneratorConfig)


class TestForwardRefConfigsNowTyped:
    """The two formerly Any-typed forward-ref configs are now validated."""

    def test_subagent_orchestrator_is_typed_and_validated(self):
        from massgen.subagent.models import SubagentOrchestratorConfig

        cc = CoordinationConfig.from_dict({"subagent_orchestrator": {"enabled": True, "max_new_answers": 5}})
        assert isinstance(cc.subagent_orchestrator, SubagentOrchestratorConfig)
        assert cc.subagent_orchestrator.max_new_answers == 5
        with pytest.raises(ValidationError):
            SubagentOrchestratorConfig(max_new_answers="not-an-int")

    def test_message_templates_field_rejects_wrong_type(self):
        from massgen.message_templates import MessageTemplates

        assert AgentConfig(message_templates=MessageTemplates()).message_templates is not None
        with pytest.raises(ValidationError):
            AgentConfig(message_templates="not-a-template")
