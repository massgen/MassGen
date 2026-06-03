"""Unit tests for pure helper functions extracted into the massgen.cli package.

These functions had no direct coverage before the cli.py -> massgen/cli/ package
decomposition. They are pure (no I/O, deterministic) and now live in focused
submodules, which makes them cheap to test directly. Each test imports through
the public facade (``massgen.cli``) to also assert the facade re-exports them.
"""

from __future__ import annotations

import pytest

from massgen.cli import (
    _expand_env_vars,
    _format_chunk_target_line,
    _headless_quickstart_output_path_from_config_arg,
    _parse_quickstart_agent_specs,
    _parse_standalone_checkpoint,
    _substitute_variables,
    relocate_filesystem_paths,
)


class TestSubstituteVariables:
    """${var} substitution from an explicit variables mapping."""

    def test_substitutes_in_nested_structures(self):
        obj = {"a": "${name}", "b": ["${name}", 1, {"c": "x-${name}-y"}]}
        result = _substitute_variables(obj, {"name": "VAL"})
        assert result == {"a": "VAL", "b": ["VAL", 1, {"c": "x-VAL-y"}]}

    def test_leaves_unknown_placeholders_untouched(self):
        assert _substitute_variables("${missing}", {"name": "VAL"}) == "${missing}"

    def test_non_string_scalars_passthrough(self):
        assert _substitute_variables(42, {"x": "y"}) == 42
        assert _substitute_variables(None, {"x": "y"}) is None

    def test_does_not_mutate_input(self):
        obj = {"a": "${name}"}
        _substitute_variables(obj, {"name": "VAL"})
        assert obj == {"a": "${name}"}


class TestExpandEnvVars:
    """${VAR} expansion from the process environment."""

    def test_expands_set_variable(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("MG_TEST_TOKEN", "secret")
        assert _expand_env_vars("Bearer ${MG_TEST_TOKEN}") == "Bearer secret"

    def test_unset_variable_left_as_is(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("MG_TEST_MISSING", raising=False)
        assert _expand_env_vars("${MG_TEST_MISSING}") == "${MG_TEST_MISSING}"

    def test_recurses_into_dicts_and_lists(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("MG_TEST_K", "v")
        cfg = {"a": ["${MG_TEST_K}", 1], "b": {"c": "${MG_TEST_K}"}}
        assert _expand_env_vars(cfg) == {"a": ["v", 1], "b": {"c": "v"}}


class TestRelocateFilesystemPaths:
    """Relative state paths get relocated under .massgen/; absolute/.massgen kept."""

    def test_relocates_relative_orchestrator_paths(self):
        cfg = {"orchestrator": {"snapshot_storage": "snaps", "agent_temporary_workspace": "tmp"}}
        relocate_filesystem_paths(cfg)
        assert cfg["orchestrator"]["snapshot_storage"] == ".massgen/snaps"
        assert cfg["orchestrator"]["agent_temporary_workspace"] == ".massgen/tmp"

    def test_keeps_already_scoped_and_absolute_paths(self):
        cfg = {"orchestrator": {"snapshot_storage": ".massgen/snaps", "agent_temporary_workspace": "/abs/tmp"}}
        relocate_filesystem_paths(cfg)
        assert cfg["orchestrator"]["snapshot_storage"] == ".massgen/snaps"
        assert cfg["orchestrator"]["agent_temporary_workspace"] == "/abs/tmp"

    def test_relocates_agent_cwd_under_workspaces(self):
        cfg = {"agents": [{"backend": {"cwd": "ws1"}}, {"backend": {"cwd": "/abs/ws"}}]}
        relocate_filesystem_paths(cfg)
        assert cfg["agents"][0]["backend"]["cwd"] == ".massgen/workspaces/ws1"
        assert cfg["agents"][1]["backend"]["cwd"] == "/abs/ws"

    def test_single_agent_form(self):
        cfg = {"agent": {"backend": {"cwd": "ws"}}}
        relocate_filesystem_paths(cfg)
        assert cfg["agent"]["backend"]["cwd"] == ".massgen/workspaces/ws"


class TestFormatChunkTargetLine:
    def test_none_and_one_are_exactly_one(self):
        assert _format_chunk_target_line(None) == "- Target chunks: exactly 1"
        assert _format_chunk_target_line(1) == "- Target chunks: exactly 1"

    def test_multiple_is_approximate(self):
        assert _format_chunk_target_line(4) == "- Target chunks: around 4"

    def test_zero_or_negative_falls_back_to_one(self):
        assert _format_chunk_target_line(0) == "- Target chunks: exactly 1"
        assert _format_chunk_target_line(-3) == "- Target chunks: exactly 1"


class TestParseQuickstartAgentSpecs:
    def test_none_and_empty_return_empty(self):
        assert _parse_quickstart_agent_specs(None) == []
        assert _parse_quickstart_agent_specs([]) == []

    def test_parses_key_value_pairs(self):
        specs = _parse_quickstart_agent_specs(["backend=claude,model=claude-opus-4-6"])
        assert specs == [{"backend": "claude", "model": "claude-opus-4-6"}]

    def test_type_alias_satisfies_backend_requirement(self):
        specs = _parse_quickstart_agent_specs(["type=openai,model=gpt-5.4"])
        assert specs == [{"type": "openai", "model": "gpt-5.4"}]

    def test_rejects_malformed_pair(self):
        with pytest.raises(ValueError, match="key=value"):
            _parse_quickstart_agent_specs(["backendclaude"])

    def test_rejects_unknown_field(self):
        with pytest.raises(ValueError, match="Unsupported"):
            _parse_quickstart_agent_specs(["backend=claude,temperature=0.5"])

    def test_requires_backend_or_type(self):
        with pytest.raises(ValueError, match="requires backend"):
            _parse_quickstart_agent_specs(["model=gpt-5.4"])


class TestHeadlessQuickstartOutputPath:
    def test_none_and_blank_return_none(self):
        assert _headless_quickstart_output_path_from_config_arg(None) is None
        assert _headless_quickstart_output_path_from_config_arg("   ") is None

    def test_expands_user_home(self):
        result = _headless_quickstart_output_path_from_config_arg("~/cfg.yaml")
        assert result is not None
        assert not result.startswith("~")
        assert result.endswith("cfg.yaml")


class TestExtractModelsForSession:
    """run._extract_models_for_session collects per-agent models for metadata."""

    def _agent(self, model):
        from types import SimpleNamespace

        return SimpleNamespace(config=SimpleNamespace(backend_params={"model": model} if model else {}))

    def test_collects_unique_models_in_order(self):
        from massgen.cli.run import _extract_models_for_session

        agents = {"a": self._agent("gpt-5.4"), "b": self._agent("claude-opus-4-6"), "c": self._agent("gpt-5.4")}
        models_dict, registry = _extract_models_for_session(agents)
        assert models_dict == {"a": "gpt-5.4", "b": "claude-opus-4-6", "c": "gpt-5.4"}
        assert registry == "gpt-5.4, claude-opus-4-6"

    def test_no_models_returns_none_registry(self):
        from massgen.cli.run import _extract_models_for_session

        models_dict, registry = _extract_models_for_session({"a": self._agent(None)})
        assert models_dict == {}
        assert registry is None

    def test_agent_without_config_skipped(self):
        from massgen.cli.run import _extract_models_for_session

        models_dict, registry = _extract_models_for_session({"a": object()})
        assert models_dict == {}
        assert registry is None


class TestPersistGeneratedPersonasAndCriteria:
    """run._persist_generated_personas_and_criteria stores into session_info."""

    def _orch(self, personas, criteria):
        from types import SimpleNamespace

        return SimpleNamespace(
            get_generated_personas=lambda: personas,
            get_generated_evaluation_criteria=lambda: criteria,
        )

    def test_stores_personas_and_criteria(self):
        from types import SimpleNamespace

        from massgen.cli.run import _persist_generated_personas_and_criteria

        crit = SimpleNamespace(id="c1", text="be correct", category="quality")
        session_info: dict = {}
        _persist_generated_personas_and_criteria(self._orch(["p1"], [crit]), session_info)
        assert session_info["generated_personas"] == ["p1"]
        assert session_info["generated_evaluation_criteria"] == [{"id": "c1", "text": "be correct", "category": "quality"}]

    def test_absent_when_nothing_generated(self):
        from massgen.cli.run import _persist_generated_personas_and_criteria

        session_info: dict = {}
        _persist_generated_personas_and_criteria(self._orch([], []), session_info)
        assert session_info == {}


class TestLoadPersistedPersonasAndCriteria:
    """run._load_persisted_personas_and_criteria gated by persist_across_turns."""

    def _cfg(self, persona_persist, criteria_persist):
        from types import SimpleNamespace

        cc = SimpleNamespace(
            persona_generator=SimpleNamespace(persist_across_turns=persona_persist),
            evaluation_criteria_generator=SimpleNamespace(persist_across_turns=criteria_persist),
        )
        return SimpleNamespace(coordination_config=cc)

    def test_returns_none_when_persist_disabled(self):
        from massgen.cli.run import _load_persisted_personas_and_criteria

        session = {"generated_personas": ["p"], "generated_evaluation_criteria": [{"text": "x"}]}
        personas, criteria = _load_persisted_personas_and_criteria(self._cfg(False, False), session)
        assert personas is None
        assert criteria is None

    def test_loads_personas_when_enabled(self):
        from massgen.cli.run import _load_persisted_personas_and_criteria

        personas, _ = _load_persisted_personas_and_criteria(self._cfg(True, False), {"generated_personas": ["p1"]})
        assert personas == ["p1"]

    def test_rebuilds_criteria_objects_when_enabled(self):
        from massgen.cli.run import _load_persisted_personas_and_criteria

        session = {"generated_evaluation_criteria": [{"id": "c1", "text": "be correct", "category": "quality"}, {"name": "no-text-key"}]}
        _, criteria = _load_persisted_personas_and_criteria(self._cfg(False, True), session)
        assert [c.id for c in criteria] == ["c1", "E2"]
        assert criteria[0].text == "be correct"
        assert criteria[1].text == "no-text-key"

    def test_no_coordination_config_is_safe(self):
        from types import SimpleNamespace

        from massgen.cli.run import _load_persisted_personas_and_criteria

        personas, criteria = _load_persisted_personas_and_criteria(SimpleNamespace(coordination_config=None), {})
        assert personas is None and criteria is None

    def test_roundtrip_with_persist_helper(self):
        # _persist_* writes into session_info; _load_* reads it back when enabled.
        from types import SimpleNamespace

        from massgen.cli.run import (
            _load_persisted_personas_and_criteria,
            _persist_generated_personas_and_criteria,
        )

        crit = SimpleNamespace(id="c1", text="t", category="quality")
        orch = SimpleNamespace(get_generated_personas=lambda: ["p1"], get_generated_evaluation_criteria=lambda: [crit])
        session: dict = {}
        _persist_generated_personas_and_criteria(orch, session)
        personas, criteria = _load_persisted_personas_and_criteria(self._cfg(True, True), session)
        assert personas == ["p1"]
        assert criteria[0].id == "c1" and criteria[0].text == "t"


class TestReloadTurnHistory:
    """run._reload_turn_history prefers session_info, else restores from storage."""

    def test_prefers_values_in_session_info(self):
        from massgen.cli.run import _reload_turn_history

        session = {"previous_turns": [{"t": 1}], "winning_agents_history": ["a"]}
        prev, winners = _reload_turn_history(session, "sid")
        assert prev == [{"t": 1}]
        assert winners == ["a"]

    def test_no_session_id_returns_empty(self):
        from massgen.cli.run import _reload_turn_history

        prev, winners = _reload_turn_history({}, None)
        assert prev == []
        assert winners == []

    def test_restores_from_storage_when_empty(self, monkeypatch):
        # The helper does a call-time ``from massgen.session import restore_session``,
        # so patch the attribute on massgen.session.
        import types

        import massgen.session as session_mod
        from massgen.cli.run import _reload_turn_history

        state = types.SimpleNamespace(previous_turns=[{"t": 9}], winning_agents_history=["w"])
        monkeypatch.setattr(session_mod, "restore_session", lambda *a, **k: state)
        prev, winners = _reload_turn_history({}, "sid")
        assert prev == [{"t": 9}]
        assert winners == ["w"]

    def test_restore_failure_is_swallowed(self, monkeypatch):
        import massgen.session as session_mod
        from massgen.cli.run import _reload_turn_history

        def _boom(*a, **k):
            raise ValueError("no session")

        monkeypatch.setattr(session_mod, "restore_session", _boom)
        prev, winners = _reload_turn_history({}, "sid")
        assert prev == []
        assert winners == []


class TestParseStandaloneCheckpoint:
    def test_defaults_for_empty_block(self):
        kwargs = _parse_standalone_checkpoint({})
        assert kwargs["standalone_checkpoint_enabled"] is False
        assert kwargs["standalone_checkpoint_mode"] == "generate"

    def test_known_mode_preserved(self):
        kwargs = _parse_standalone_checkpoint({"enabled": True, "mode": "verify"})
        assert kwargs["standalone_checkpoint_enabled"] is True
        assert kwargs["standalone_checkpoint_mode"] == "verify"

    def test_unknown_mode_falls_back_to_generate(self):
        # Forgiving parse: a typo must not silently run a different mode.
        kwargs = _parse_standalone_checkpoint({"mode": "verfy"})
        assert kwargs["standalone_checkpoint_mode"] == "generate"
