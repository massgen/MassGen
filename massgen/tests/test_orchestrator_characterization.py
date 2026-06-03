#!/usr/bin/env python3
"""Characterization safety net for ``massgen.orchestrator`` BEFORE the
collaborator-extraction refactor.

Purpose
-------
These tests PIN the current observable behavior of ``massgen.orchestrator`` so
the planned conversion of ``orchestrator.py`` into a package + collaborator
extraction can be proven to introduce no breaking changes. They are written
against the CURRENT, UNMODIFIED code and must pass green today.

Coverage (mapped to the refactor plan)
---------------------------------------
1. Public-contract import stability (refactor step 0 / hard constraint):
   ``Orchestrator``, ``AgentState``, ``WORKFLOW_TOOL_NAMES``,
   ``create_orchestrator``, ``MassOrchestrator`` -- importability + identity +
   signature pinning. NOTE: ``MassOrchestrator`` is intentionally documented as
   NOT YET exported from ``massgen.orchestrator`` (it lives in
   ``massgen.v1.orchestrator``); we pin that current reality so the step-0
   re-export shim has an explicit baseline to flip.
2. Construction / initialization with realistic configs.
3. The three lowest-risk extraction seams (refactor ordered_steps 1-3):
     - step 1: SkillsConfigValidator  -> ``_validate_skills_config``
     - step 2: NlipRoutingInitializer -> ``_init_nlip_routing``
     - step 3: RunModeStrategyResolver -> the 5 run-mode predicate methods
   We exercise each seam method and assert on its outputs/side effects so the
   delegators introduced during extraction can be checked for parity.

These are intentionally deterministic, no-network, no-live-API tests so they
serve as a fast regression net runnable on every extraction step.
"""

import inspect
from pathlib import Path

import pytest

# Import the entire module so we can assert on attribute presence/absence
# (e.g. MassOrchestrator currently absent) without an ImportError at collection.
import massgen.orchestrator as orchestrator_module
from massgen.agent_config import AgentConfig
from massgen.orchestrator import (
    WORKFLOW_TOOL_NAMES,
    AgentState,
    Orchestrator,
    create_orchestrator,
)


# ---------------------------------------------------------------------------
# Test doubles (mirroring the minimal-stub style used in test_vote_only_mode.py)
# ---------------------------------------------------------------------------
class _BackendNoCustomTools:
    """Backend stub WITHOUT a custom_tool_manager -> NLIP must skip it.

    ``filesystem_manager = None`` lets the constructor's per-agent setup
    early-return so this stub is safe to pass as a real agent during
    Orchestrator construction.
    """

    custom_tool_manager = None
    filesystem_manager = None

    def __init__(self):
        self.config = {}


class _BackendWithCustomTools:
    """Backend stub WITH a custom_tool_manager and set_nlip_router."""

    filesystem_manager = None

    def __init__(self):
        self.custom_tool_manager = object()
        self.config = {}
        self.set_nlip_router_calls = []

    def set_nlip_router(self, nlip_router=None, enabled=False):
        self.set_nlip_router_calls.append((nlip_router, enabled))


class _AgentConfigStub:
    """Per-agent config stub exposing the attributes _init_nlip_routing touches."""

    def __init__(self):
        self.enable_nlip = False
        self.nlip_config = None
        self.nlip_router = "fake-router"
        self.init_nlip_router_calls = []

    def init_nlip_router(self, tool_manager=None, mcp_executor=None):
        self.init_nlip_router_calls.append((tool_manager, mcp_executor))


class _AgentStub:
    """Minimal agent: has a backend and a config (NLIP-eligible by default)."""

    def __init__(self, backend, config):
        self.backend = backend
        self.config = config


def _make_orchestrator(config=None, **kwargs):
    """Construct an Orchestrator with no real agents (mirrors existing tests)."""
    return Orchestrator(agents={}, config=config or AgentConfig(), **kwargs)


def _construction_safe_agent():
    """An agent stub safe to pass during construction.

    The per-agent setup early-returns when ``backend.filesystem_manager`` is
    falsy, so this stub exercises only agent-count-dependent logic.
    """
    return _AgentStub(_BackendNoCustomTools(), _AgentConfigStub())


# ===========================================================================
# 1. PUBLIC CONTRACT: import stability + signature pinning (refactor step 0)
# ===========================================================================
class TestPublicContractImports:
    """The hard-constraint guard. Must stay green through every extraction step."""

    def test_orchestrator_importable_and_is_class(self):
        assert inspect.isclass(Orchestrator)
        assert Orchestrator.__name__ == "Orchestrator"

    def test_agent_state_importable_and_is_dataclass(self):
        assert inspect.isclass(AgentState)
        # AgentState is a dataclass today; pin that so the move preserves it.
        assert hasattr(AgentState, "__dataclass_fields__")

    def test_workflow_tool_names_value_and_identity(self):
        # Pin the exact membership/order observed today.
        assert WORKFLOW_TOOL_NAMES == [
            "new_answer",
            "vote",
            "stop",
            "submit",
            "restart_orchestration",
            "ask_others",
            "respond_to_broadcast",
            "check_broadcast_status",
            "get_broadcast_responses",
            "checkpoint",
        ]
        # It is re-exported (same object) from the toolkit base module today;
        # the package facade must preserve this re-import relationship.
        from massgen.tool.workflow_toolkits.base import (
            WORKFLOW_TOOL_NAMES as base_names,
        )

        assert WORKFLOW_TOOL_NAMES is base_names

    def test_create_orchestrator_signature_pinned(self):
        sig = inspect.signature(create_orchestrator)
        assert list(sig.parameters) == [
            "agents",
            "orchestrator_id",
            "session_id",
            "config",
            "snapshot_storage",
            "agent_temporary_workspace",
        ]
        # Defaults that external callers rely on.
        assert sig.parameters["orchestrator_id"].default == "orchestrator"
        assert sig.parameters["session_id"].default is None
        assert sig.parameters["config"].default is None
        assert sig.return_annotation is Orchestrator

    def test_orchestrator_init_signature_pinned(self):
        sig = inspect.signature(Orchestrator.__init__)
        params = list(sig.parameters)
        # Pin the full kwarg surface so the package conversion can't silently
        # drop/rename a constructor parameter relied on by callers.
        assert params == [
            "self",
            "agents",
            "orchestrator_id",
            "session_id",
            "config",
            "dspy_paraphraser",
            "snapshot_storage",
            "agent_temporary_workspace",
            "previous_turns",
            "winning_agents_history",
            "shared_conversation_memory",
            "shared_persistent_memory",
            "enable_nlip",
            "nlip_config",
            "enable_rate_limit",
            "trace_classification",
            "generated_personas",
            "generated_evaluation_criteria",
            "plan_session_id",
            "step_mode",
            "raw_config",
        ]

    def test_mass_orchestrator_not_exported(self):
        """The legacy ``MassOrchestrator`` name is not exported from massgen.orchestrator.

        (The old ``massgen.v1`` package that defined it has been removed; the
        current orchestrator is ``massgen.orchestrator.Orchestrator``.)
        """
        assert not hasattr(orchestrator_module, "MassOrchestrator")


# ===========================================================================
# 2. CONSTRUCTION / INITIALIZATION
# ===========================================================================
class TestConstruction:
    def test_default_construction_smoke(self):
        orch = _make_orchestrator()
        assert orch.orchestrator_id == "orchestrator"
        assert orch.agents == {}
        assert isinstance(orch.agent_states, dict)
        assert isinstance(orch.workflow_tools, list)
        # Coordination tracker is the central shared state for many seams.
        assert hasattr(orch, "coordination_tracker")
        assert orch.coordination_tracker is not None

    def test_create_orchestrator_factory_builds_orchestrator(self):
        orch = create_orchestrator(agents=[], config=AgentConfig())
        assert isinstance(orch, Orchestrator)
        assert orch.orchestrator_id == "orchestrator"

    def test_construction_with_nlip_kwargs_stores_config(self):
        nlip_cfg = {"routing": "demo"}
        orch = _make_orchestrator(enable_nlip=True, nlip_config=nlip_cfg)
        assert orch.nlip_config == nlip_cfg

    def test_construction_with_custom_id_and_session(self):
        orch = Orchestrator(
            agents={},
            orchestrator_id="orch-xyz",
            session_id="sess-123",
            config=AgentConfig(),
        )
        assert orch.orchestrator_id == "orch-xyz"


# ===========================================================================
# 3a. SEAM (refactor step 1): SkillsConfigValidator -> _validate_skills_config
# ===========================================================================
class TestSkillsConfigValidatorSeam:
    """Pin _validate_skills_config behavior: reads coordination_config.skills_directory.

    Built-in skills are bundled in massgen/skills, so validation succeeds even
    when the external skills dir is absent. We assert both the success path and
    the failure path (no external + no built-in) to avoid an always-pass test.
    """

    def test_validate_passes_with_builtin_skills(self):
        orch = _make_orchestrator()
        # Default skills_directory is '.agent/skills' (likely absent), but the
        # bundled built-in skills directory exists -> must NOT raise.
        builtin = Path(orchestrator_module.__file__).parent / "skills"
        assert builtin.exists(), "precondition: built-in skills dir should exist"
        orch._validate_skills_config()  # should not raise

    def test_validate_reads_skills_directory_from_coordination_config(self):
        orch = _make_orchestrator()
        # The seam's only EXPLICIT dependency (per refactor plan) is this value.
        assert hasattr(orch.config.coordination_config, "skills_directory")
        # Point at an existing dir with content -> external-skills branch True.
        orch.config.coordination_config.skills_directory = str(
            Path(orchestrator_module.__file__).parent / "skills",
        )
        orch._validate_skills_config()  # should not raise via external branch

    def test_validate_raises_when_no_skills_anywhere(self, tmp_path, monkeypatch):
        orch = _make_orchestrator()
        # Empty external dir.
        empty_external = tmp_path / "no_skills"
        empty_external.mkdir()
        orch.config.coordination_config.skills_directory = str(empty_external)

        # Force the built-in branch to also be empty by pointing __file__'s
        # parent/skills resolution at an empty dir. The method computes
        # ``Path(__file__).parent / "skills"``; we cannot move __file__, so
        # instead assert the failure path via a missing built-in by patching
        # Path.iterdir/exists is brittle -- instead emulate "no builtin" by
        # making the built-in dir lookup resolve empty through monkeypatching
        # the module file location.
        fake_module_dir = tmp_path / "fakepkg"
        (fake_module_dir).mkdir()
        # built-in skills dir intentionally NOT created under fake_module_dir
        monkeypatch.setattr(
            orchestrator_module,
            "__file__",
            str(fake_module_dir / "orchestrator.py"),
        )
        with pytest.raises(RuntimeError, match="No skills found"):
            orch._validate_skills_config()


# ===========================================================================
# 3b. SEAM (refactor step 2): NlipRoutingInitializer -> _init_nlip_routing
# ===========================================================================
class TestNlipRoutingInitializerSeam:
    """Pin _init_nlip_routing side effects: per-agent enablement when the
    backend exposes a custom_tool_manager, and skipping otherwise."""

    def test_init_nlip_no_agents_is_noop(self):
        orch = _make_orchestrator(enable_nlip=True, nlip_config={"k": "v"})
        # No agents -> must not raise.
        orch._init_nlip_routing()

    def test_init_nlip_skips_backend_without_custom_tool_manager(self):
        agent = _AgentStub(_BackendNoCustomTools(), _AgentConfigStub())
        orch = Orchestrator(
            agents={"a": agent},
            config=AgentConfig(),
            enable_nlip=True,
            nlip_config={"k": "v"},
        )
        orch.agents = {"a": agent}  # ensure our stub is the agent
        orch._init_nlip_routing()
        # Skipped: enable_nlip stays False, init_nlip_router never called.
        assert agent.config.enable_nlip is False
        assert agent.config.init_nlip_router_calls == []

    def test_init_nlip_enables_backend_with_custom_tool_manager(self):
        backend = _BackendWithCustomTools()
        cfg = _AgentConfigStub()
        agent = _AgentStub(backend, cfg)
        nlip_cfg = {"routing": "on"}
        orch = Orchestrator(
            agents={"a": agent},
            config=AgentConfig(),
            enable_nlip=True,
            nlip_config=nlip_cfg,
        )
        orch.agents = {"a": agent}
        # NOTE (characterization finding): construction with enable_nlip=True and
        # an NLIP-eligible agent ALREADY invokes _init_nlip_routing once. We reset
        # the recorded calls so this test isolates the explicit invocation below.
        cfg.init_nlip_router_calls.clear()
        backend.set_nlip_router_calls.clear()

        orch._init_nlip_routing()
        # Enabled side effects (the contract the collaborator must preserve):
        assert cfg.enable_nlip is True
        assert cfg.nlip_config == nlip_cfg
        assert len(cfg.init_nlip_router_calls) == 1
        # Router injected into backend with enabled=True.
        assert backend.set_nlip_router_calls == [("fake-router", True)]


# ===========================================================================
# 3c. SEAM (refactor step 3): RunModeStrategyResolver -> 5 run-mode predicates
# ===========================================================================
class TestRunModeStrategyResolverSeam:
    """Pin the 5 pure run-mode predicate methods across config variants.

    These read self.config / self.agents / _is_decomposition_mode (which stays
    on the facade). The collaborator extraction keeps thin delegators -- these
    tests give parity coverage for the delegated outputs.
    """

    # ---- _get_final_answer_strategy ----
    def test_strategy_default_is_winner_present(self):
        assert _make_orchestrator()._get_final_answer_strategy() == "winner_present"

    def test_strategy_winner_reuse_when_skip_final_presentation(self):
        cfg = AgentConfig()
        cfg.skip_final_presentation = True
        assert _make_orchestrator(cfg)._get_final_answer_strategy() == "winner_reuse"

    def test_strategy_honors_explicit_synthesize(self):
        cfg = AgentConfig()
        cfg.final_answer_strategy = "synthesize"
        assert _make_orchestrator(cfg)._get_final_answer_strategy() == "synthesize"

    def test_strategy_honors_explicit_winner_reuse(self):
        cfg = AgentConfig()
        cfg.final_answer_strategy = "winner_reuse"
        assert _make_orchestrator(cfg)._get_final_answer_strategy() == "winner_reuse"

    # ---- _expects_final_presentation_stage ----
    def test_expects_presentation_default_true(self):
        assert _make_orchestrator()._expects_final_presentation_stage() is True

    def test_expects_presentation_false_when_skip_and_skip_voting(self):
        cfg = AgentConfig()
        cfg.skip_final_presentation = True
        cfg.skip_voting = True
        assert _make_orchestrator(cfg)._expects_final_presentation_stage() is False

    def test_expects_presentation_true_for_synthesize_even_when_skip_final(self):
        cfg = AgentConfig()
        cfg.skip_final_presentation = True
        cfg.skip_voting = False
        cfg.final_answer_strategy = "synthesize"
        assert _make_orchestrator(cfg)._expects_final_presentation_stage() is True

    # ---- _is_round_learning_capture_enabled ----
    def test_round_learning_default_false(self):
        # Default coordination learning_capture_mode is
        # 'verification_and_final_only' -> learning capture disabled.
        assert _make_orchestrator()._is_round_learning_capture_enabled() is False

    def test_round_learning_true_for_round_mode(self):
        cfg = AgentConfig()
        cfg.coordination_config.learning_capture_mode = "round"
        assert _make_orchestrator(cfg)._is_round_learning_capture_enabled() is True

    def test_round_learning_final_only_falls_back_when_no_presenter(self):
        # final_only + no presenter stage -> fallback to round capture (True).
        cfg = AgentConfig()
        cfg.coordination_config.learning_capture_mode = "final_only"
        cfg.skip_final_presentation = True
        cfg.skip_voting = True  # makes _expects_final_presentation_stage() False
        assert _make_orchestrator(cfg)._is_round_learning_capture_enabled() is True

    def test_round_learning_final_only_no_fallback_when_disabled(self):
        cfg = AgentConfig()
        cfg.coordination_config.learning_capture_mode = "final_only"
        cfg.coordination_config.disable_final_only_round_capture_fallback = True
        cfg.skip_final_presentation = True
        cfg.skip_voting = True
        assert _make_orchestrator(cfg)._is_round_learning_capture_enabled() is False

    # ---- _is_round_verification_capture_enabled ----
    def test_round_verification_default_true(self):
        # Default mode is 'verification_and_final_only' -> verification enabled.
        assert _make_orchestrator()._is_round_verification_capture_enabled() is True

    def test_round_verification_true_when_learning_true(self):
        cfg = AgentConfig()
        cfg.coordination_config.learning_capture_mode = "round"
        assert _make_orchestrator(cfg)._is_round_verification_capture_enabled() is True

    def test_round_verification_false_for_final_only_no_fallback(self):
        cfg = AgentConfig()
        cfg.coordination_config.learning_capture_mode = "final_only"
        cfg.coordination_config.disable_final_only_round_capture_fallback = True
        cfg.skip_final_presentation = True
        cfg.skip_voting = True
        # learning False AND mode != verification_and_final_only -> False.
        assert _make_orchestrator(cfg)._is_round_verification_capture_enabled() is False

    # ---- _should_skip_vote_rounds_for_synthesize ----
    def test_skip_vote_rounds_false_single_agent(self):
        # <=1 agent -> always False regardless of strategy.
        cfg = AgentConfig()
        cfg.final_answer_strategy = "synthesize"
        cfg.max_new_answers_per_agent = 1
        assert _make_orchestrator(cfg)._should_skip_vote_rounds_for_synthesize() is False

    def test_skip_vote_rounds_true_multi_agent_synthesize_single_answer(self):
        cfg = AgentConfig()
        cfg.final_answer_strategy = "synthesize"
        cfg.max_new_answers_per_agent = 1
        cfg.defer_voting_until_all_answered = False
        orch = Orchestrator(
            agents={"a": _construction_safe_agent(), "b": _construction_safe_agent()},
            config=cfg,
        )
        assert orch._should_skip_vote_rounds_for_synthesize() is True

    def test_skip_vote_rounds_false_when_defer_voting(self):
        cfg = AgentConfig()
        cfg.final_answer_strategy = "synthesize"
        cfg.max_new_answers_per_agent = 1
        cfg.defer_voting_until_all_answered = True
        orch = Orchestrator(
            agents={"a": _construction_safe_agent(), "b": _construction_safe_agent()},
            config=cfg,
        )
        assert orch._should_skip_vote_rounds_for_synthesize() is False

    def test_skip_vote_rounds_false_when_not_synthesize(self):
        cfg = AgentConfig()
        cfg.final_answer_strategy = "winner_present"
        cfg.max_new_answers_per_agent = 1
        orch = Orchestrator(
            agents={"a": _construction_safe_agent(), "b": _construction_safe_agent()},
            config=cfg,
        )
        assert orch._should_skip_vote_rounds_for_synthesize() is False

    def test_skip_vote_rounds_false_when_multi_answer(self):
        cfg = AgentConfig()
        cfg.final_answer_strategy = "synthesize"
        cfg.max_new_answers_per_agent = 2
        orch = Orchestrator(
            agents={"a": _construction_safe_agent(), "b": _construction_safe_agent()},
            config=cfg,
        )
        assert orch._should_skip_vote_rounds_for_synthesize() is False


# ---------------------------------------------------------------------------
# Regression: collaborators must resolve under __new__-bypass construction.
#
# The collaborator extraction composes helper objects (SkillsConfigValidator,
# RoundEvaluatorGateConfig, etc.) that delegator methods reference via
# ``self._<collaborator>``. Several tracked tests build an Orchestrator with
# ``Orchestrator.__new__(Orchestrator)`` and set only a few attributes, never
# running ``__init__``. If collaborators were assigned in ``__init__`` they
# would be missing here, raising AttributeError. They are defined as lazy
# ``cached_property`` accessors specifically so this construction path works.
# This pins that contract so the regression cannot silently return.
# ---------------------------------------------------------------------------
class TestCollaboratorsResolveUnderNewBypass:
    def _bare_orchestrator(self):
        from types import SimpleNamespace

        orch = Orchestrator.__new__(Orchestrator)
        orch.agents = {}
        orch.config = SimpleNamespace(
            coordination_config=SimpleNamespace(
                round_evaluator_before_checklist=False,
                orchestrator_managed_round_evaluator=False,
                subagent_orchestrator=False,
            ),
            final_answer_strategy="winner_present",
            skip_final_presentation=False,
            skip_voting=False,
            coordination_mode="default",
            max_new_answers_per_agent=1,
            defer_voting_until_all_answered=False,
        )
        orch.orchestrator_id = "test-orch"
        return orch

    def test_lazy_collaborator_accessors_do_not_require_init(self):
        orch = self._bare_orchestrator()
        # Each accessor must construct lazily without AttributeError.
        for attr in (
            "_skills_validator",
            "_nlip_routing_initializer",
            "_run_mode_strategy_resolver",
            "_context_path_write_tracker",
            "_round_evaluator_gate_config",
            "_round_start_context_queue",
            "_dspy_paraphrase_coordinator",
            "_answer_text_normalizer",
            "_orchestrator_timeout_calculator",
        ):
            assert getattr(orch, attr) is not None, f"{attr} failed to resolve under __new__"
        # cached_property caches: second access returns the same instance.
        assert orch._skills_validator is orch._skills_validator

    def test_delegated_predicate_works_under_new_bypass(self):
        orch = self._bare_orchestrator()
        # A read-only delegated predicate must run without __init__.
        assert orch._is_round_evaluator_gate_enabled() is False
