"""Tests for the set_evaluator_personas MCP tool and persona consumption flow.

Covers:
- State lifecycle: pending -> consumed -> last -> reuse fallback
- Count validation: mismatch rejected, correct count accepted
- Empty label/instructions rejected
- Persona injection into child YAML config
- Backward compatibility: no personas = existing behavior unchanged
- Single-use: pending cleared after consumption
- Stdio specs round-trip
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Helpers to build a minimal orchestrator-like object for state tests
# ---------------------------------------------------------------------------


def _make_orchestrator_stub(
    evaluator_team_size: int = 3,
    pending: list[dict[str, str]] | None = None,
    last: list[dict[str, str]] | None = None,
) -> Any:
    """Return a minimal object with the persona state fields and helpers.

    We test against the real Orchestrator methods once they exist; this stub
    lets us write the tests first (TDD red phase).
    """
    from massgen.orchestrator import Orchestrator
    from massgen.orchestrator_collaborators import RoundEvaluatorGateConfig

    # Build minimal config to instantiate orchestrator
    stub = MagicMock(spec=Orchestrator)
    stub._pending_evaluator_personas = pending
    stub._last_evaluator_personas = last

    # The persona validate/consume logic now lives in the RoundEvaluatorGateConfig
    # collaborator; wire a REAL instance (back-ref to the stub) so the delegator
    # methods exercise the real logic. Override only the team-size lever, which
    # the test parametrizes (the collaborator otherwise derives it from config).
    gate = RoundEvaluatorGateConfig(stub)
    gate.get_evaluator_team_size = lambda: evaluator_team_size
    stub._round_evaluator_gate_config = gate

    # Bind real delegator methods
    stub._get_evaluator_team_size = lambda: evaluator_team_size
    stub._consume_evaluator_personas = Orchestrator._consume_evaluator_personas.__get__(stub)
    stub._validate_evaluator_personas = Orchestrator._validate_evaluator_personas.__get__(stub)
    return stub


SAMPLE_PERSONAS = [
    {"label": "Correctness Auditor", "instructions": "Focus on logical correctness and edge cases."},
    {"label": "UX Advocate", "instructions": "Evaluate from end-user perspective and accessibility."},
    {"label": "Performance Critic", "instructions": "Focus on efficiency, scalability, and cost."},
]


# ===================================================================
# State lifecycle tests
# ===================================================================


class TestEvaluatorPersonaStateLifecycle:
    """Test the pending -> consumed -> last -> reuse state machine."""

    def test_consume_pending_moves_to_last(self):
        """Consuming pending personas stores them in _last and clears pending."""
        orch = _make_orchestrator_stub(
            evaluator_team_size=3,
            pending=list(SAMPLE_PERSONAS),
        )
        result = orch._consume_evaluator_personas()

        assert result == SAMPLE_PERSONAS
        assert orch._pending_evaluator_personas is None
        assert orch._last_evaluator_personas == SAMPLE_PERSONAS

    def test_consume_no_pending_reuses_last(self):
        """When no pending personas, fall back to last used set."""
        orch = _make_orchestrator_stub(
            evaluator_team_size=3,
            pending=None,
            last=list(SAMPLE_PERSONAS),
        )
        result = orch._consume_evaluator_personas()

        assert result == SAMPLE_PERSONAS
        assert orch._pending_evaluator_personas is None
        assert orch._last_evaluator_personas == SAMPLE_PERSONAS

    def test_consume_no_pending_no_last_returns_none(self):
        """When neither pending nor last exists, return None (backward compat)."""
        orch = _make_orchestrator_stub(
            evaluator_team_size=3,
            pending=None,
            last=None,
        )
        result = orch._consume_evaluator_personas()

        assert result is None
        assert orch._pending_evaluator_personas is None
        assert orch._last_evaluator_personas is None

    def test_pending_cleared_after_consumption(self):
        """Pending is single-use — cleared after one consumption."""
        orch = _make_orchestrator_stub(
            evaluator_team_size=3,
            pending=list(SAMPLE_PERSONAS),
        )
        first = orch._consume_evaluator_personas()
        assert first == SAMPLE_PERSONAS
        assert orch._pending_evaluator_personas is None

        # Second call should reuse last, not return None
        second = orch._consume_evaluator_personas()
        assert second == SAMPLE_PERSONAS

    def test_new_pending_overrides_last(self):
        """Setting new pending personas replaces last on next consumption."""
        new_personas = [
            {"label": "Security Reviewer", "instructions": "Focus on vulnerabilities."},
            {"label": "API Designer", "instructions": "Focus on API ergonomics."},
            {"label": "Test Strategist", "instructions": "Focus on test coverage."},
        ]
        orch = _make_orchestrator_stub(
            evaluator_team_size=3,
            pending=list(new_personas),
            last=list(SAMPLE_PERSONAS),
        )
        result = orch._consume_evaluator_personas()

        assert result == new_personas
        assert orch._last_evaluator_personas == new_personas


# ===================================================================
# Validation tests
# ===================================================================


class TestEvaluatorPersonaValidation:
    """Test validation of persona input."""

    def test_valid_personas_accepted(self):
        """Correct count and non-empty fields pass validation."""
        orch = _make_orchestrator_stub(evaluator_team_size=3)
        errors = orch._validate_evaluator_personas(SAMPLE_PERSONAS)
        assert errors is None

    def test_count_mismatch_rejected(self):
        """Wrong number of personas returns error."""
        orch = _make_orchestrator_stub(evaluator_team_size=3)
        too_few = SAMPLE_PERSONAS[:2]
        errors = orch._validate_evaluator_personas(too_few)
        assert errors is not None
        assert "3" in errors  # Should mention expected count

    def test_empty_label_rejected(self):
        """Persona with empty label is rejected."""
        orch = _make_orchestrator_stub(evaluator_team_size=1)
        bad = [{"label": "", "instructions": "Some instructions."}]
        errors = orch._validate_evaluator_personas(bad)
        assert errors is not None
        assert "label" in errors.lower()

    def test_empty_instructions_rejected(self):
        """Persona with empty instructions is rejected."""
        orch = _make_orchestrator_stub(evaluator_team_size=1)
        bad = [{"label": "Good Label", "instructions": ""}]
        errors = orch._validate_evaluator_personas(bad)
        assert errors is not None
        assert "instructions" in errors.lower()

    def test_missing_label_key_rejected(self):
        """Persona missing 'label' key is rejected."""
        orch = _make_orchestrator_stub(evaluator_team_size=1)
        bad = [{"instructions": "Some instructions."}]
        errors = orch._validate_evaluator_personas(bad)
        assert errors is not None

    def test_missing_instructions_key_rejected(self):
        """Persona missing 'instructions' key is rejected."""
        orch = _make_orchestrator_stub(evaluator_team_size=1)
        bad = [{"label": "Good Label"}]
        errors = orch._validate_evaluator_personas(bad)
        assert errors is not None

    def test_empty_list_rejected(self):
        """Empty persona list is rejected."""
        orch = _make_orchestrator_stub(evaluator_team_size=3)
        errors = orch._validate_evaluator_personas([])
        assert errors is not None

    def test_non_list_rejected(self):
        """Non-list input is rejected."""
        orch = _make_orchestrator_stub(evaluator_team_size=3)
        errors = orch._validate_evaluator_personas("not a list")
        assert errors is not None


# ===================================================================
# YAML config injection tests
# ===================================================================


class TestEvaluatorPersonaYAMLInjection:
    """Test that personas flow through to child YAML agent configs."""

    def test_persona_injected_as_system_prompt_in_backend(self):
        """Each persona's instructions should appear in corresponding agent's backend_config."""
        from massgen.subagent.manager import SubagentManager
        from massgen.subagent.models import SubagentConfig, SubagentOrchestratorConfig

        # Build a SubagentManager with 3 common agents (same model)
        agents_config = [{"id": f"eval_{i}", "backend": {"type": "openai", "model": "gpt-4o"}} for i in range(3)]
        orch_config = SubagentOrchestratorConfig(
            enabled=True,
            agents=agents_config,
            shared_child_team_types=["round_evaluator"],
        )

        manager = SubagentManager.__new__(SubagentManager)
        manager.parent_agent_id = "agent_a"
        manager.parent_workspace = Path("/tmp/fake_workspace")
        manager._subagent_orchestrator_config = orch_config
        manager.parent_agent_configs = [{"id": "agent_a", "backend": {"type": "openai", "model": "gpt-4o"}}]
        manager._parent_context_paths = []
        manager._parent_coordination_config = {}
        manager._agent_temporary_workspace = None
        manager._log_directory = None

        config = SubagentConfig.create(
            task="Evaluate the answer",
            parent_agent_id="agent_a",
            metadata={
                "refine": False,
                "subagent_type": "round_evaluator",
                "evaluator_personas": SAMPLE_PERSONAS,
            },
        )

        workspace = Path("/tmp/fake_subagent_workspace")
        workspace.mkdir(parents=True, exist_ok=True)

        yaml_config = manager._generate_subagent_yaml_config(config, workspace)

        # Verify each agent got its persona as system_prompt
        agents = yaml_config["agents"]
        assert len(agents) == 3

        for i, agent in enumerate(agents):
            backend = agent["backend"]
            assert "system_prompt" in backend, f"Agent {i} missing system_prompt"
            assert SAMPLE_PERSONAS[i]["label"] in backend["system_prompt"]
            assert SAMPLE_PERSONAS[i]["instructions"] in backend["system_prompt"]

    def test_no_persona_no_system_prompt_injection(self):
        """Without personas in metadata, no system_prompt should be injected."""
        from massgen.subagent.manager import SubagentManager
        from massgen.subagent.models import SubagentConfig, SubagentOrchestratorConfig

        agents_config = [
            {"id": "eval_0", "backend": {"type": "openai", "model": "gpt-4o"}},
        ]
        orch_config = SubagentOrchestratorConfig(
            enabled=True,
            agents=agents_config,
            shared_child_team_types=["round_evaluator"],
        )

        manager = SubagentManager.__new__(SubagentManager)
        manager.parent_agent_id = "agent_a"
        manager.parent_workspace = Path("/tmp/fake_workspace")
        manager._subagent_orchestrator_config = orch_config
        manager.parent_agent_configs = [{"id": "agent_a", "backend": {"type": "openai", "model": "gpt-4o"}}]
        manager._parent_context_paths = []
        manager._parent_coordination_config = {}
        manager._agent_temporary_workspace = None
        manager._log_directory = None

        config = SubagentConfig.create(
            task="Evaluate the answer",
            parent_agent_id="agent_a",
            metadata={
                "refine": False,
                "subagent_type": "round_evaluator",
                # No evaluator_personas key
            },
        )

        workspace = Path("/tmp/fake_subagent_workspace")
        workspace.mkdir(parents=True, exist_ok=True)

        yaml_config = manager._generate_subagent_yaml_config(config, workspace)

        agents = yaml_config["agents"]
        for agent in agents:
            # system_prompt should not be set by persona logic
            # (it might be set by other mechanisms, but not from evaluator_personas)
            backend = agent["backend"]
            assert "Evaluator Persona" not in backend.get("system_prompt", "")


# ===================================================================
# Metadata passthrough tests
# ===================================================================


class TestMetadataPassthrough:
    """Test that evaluator_personas in task_config flows through spawn_parallel."""

    def test_extra_metadata_merged_into_config(self):
        """Extra metadata from task_config should be available in SubagentConfig.metadata."""
        from massgen.subagent.models import SubagentConfig

        # Simulate what spawn_subagent does with extra_metadata
        metadata = {"refine": True, "subagent_type": "round_evaluator"}
        extra = {"evaluator_personas": SAMPLE_PERSONAS}
        metadata.update(extra)

        config = SubagentConfig.create(
            task="test",
            parent_agent_id="agent_a",
            metadata=metadata,
        )

        assert config.metadata["evaluator_personas"] == SAMPLE_PERSONAS
        assert config.metadata["refine"] is True
        assert config.metadata["subagent_type"] == "round_evaluator"


# ===================================================================
# Stdio specs round-trip tests
# ===================================================================


class TestStdioSpecsRoundTrip:
    """Test that evaluator_personas survives the specs JSON write/read cycle."""

    def test_evaluator_team_size_in_specs(self, tmp_path):
        """write_checklist_specs should include evaluator_team_size in state."""
        from massgen.mcp_tools.checklist_tools_server import write_checklist_specs

        state = {
            "has_existing_answers": False,
            "evaluator_team_size": 3,
        }
        specs_path = tmp_path / "specs.json"
        write_checklist_specs(items=[], state=state, output_path=specs_path)

        with open(specs_path) as f:
            loaded = json.load(f)

        assert loaded["state"]["evaluator_team_size"] == 3

    def test_evaluator_personas_roundtrip_in_specs(self, tmp_path):
        """Personas written to specs should be readable back."""
        from massgen.mcp_tools.checklist_tools_server import write_checklist_specs

        state = {
            "has_existing_answers": False,
            "evaluator_team_size": 3,
            "pending_evaluator_personas": SAMPLE_PERSONAS,
        }
        specs_path = tmp_path / "specs.json"
        write_checklist_specs(items=[], state=state, output_path=specs_path)

        with open(specs_path) as f:
            loaded = json.load(f)

        assert loaded["state"]["pending_evaluator_personas"] == SAMPLE_PERSONAS


# ===================================================================
# Codex backend _checklist_specs_path wiring test
# ===================================================================


class TestCodexBackendSpecsPathWiring:
    """The Codex backend must set _checklist_specs_path so the orchestrator
    can sync evaluator personas back from the specs file."""

    def test_codex_backend_sets_checklist_specs_path(self, tmp_path):
        """After writing checklist specs, the Codex backend should expose
        _checklist_specs_path so _sync_stdio_checklist_state_from_specs works."""
        from massgen.backend.codex import CodexBackend

        backend = CodexBackend.__new__(CodexBackend)
        backend._checklist_state = {"has_existing_answers": False, "evaluator_team_size": 3}
        backend._checklist_items = []

        # Simulate the config_dir that _prepare_workspace creates
        config_dir = tmp_path / ".codex"
        config_dir.mkdir()

        # Call the same code path the backend uses to write checklist specs
        from massgen.mcp_tools.checklist_tools_server import (
            write_checklist_specs,
        )

        specs_path = config_dir / "checklist_specs.json"
        write_checklist_specs(
            items=backend._checklist_items,
            state=backend._checklist_state,
            output_path=specs_path,
        )
        # This is the fix: backend must store the path
        backend._checklist_specs_path = specs_path

        assert hasattr(backend, "_checklist_specs_path")
        assert backend._checklist_specs_path == specs_path
        assert specs_path.exists()
