"""Characterization tests for the cli interactive run-loop entry points.

These lock in observable behavior of ``run_interactive_mode`` (the dispatcher)
so the large interactive loops can later be decomposed safely. They mock the
heavy collaborators (the Textual loop) and assert the dispatch contract only.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from massgen.cli import run as run_mod
from massgen.cli.run import (
    _agents_have_context_path,
    _build_agent_display_info,
    _merge_readonly_context_path,
)


class TestMergeReadonlyContextPath:
    """_merge_readonly_context_path adds a read-only context path idempotently."""

    def test_empty_path_is_noop(self):
        cfg: dict = {}
        assert _merge_readonly_context_path(cfg, "", "desc") is False
        assert cfg == {}

    def test_adds_new_path(self, tmp_path):
        cfg: dict = {}
        added = _merge_readonly_context_path(cfg, str(tmp_path), "my ctx")
        assert added is True
        entries = cfg["orchestrator"]["context_paths"]
        assert len(entries) == 1
        assert entries[0]["permission"] == "read"
        assert entries[0]["description"] == "my ctx"
        assert entries[0]["path"] == str(tmp_path.resolve())

    def test_existing_path_not_duplicated(self, tmp_path):
        cfg = {"orchestrator": {"context_paths": [{"path": str(tmp_path), "permission": "read"}]}}
        added = _merge_readonly_context_path(cfg, str(tmp_path), "desc")
        assert added is False
        assert len(cfg["orchestrator"]["context_paths"]) == 1

    def test_non_list_context_paths_coerced(self, tmp_path):
        cfg = {"orchestrator": {"context_paths": "bogus"}}
        added = _merge_readonly_context_path(cfg, str(tmp_path), "desc")
        assert added is True
        assert isinstance(cfg["orchestrator"]["context_paths"], list)


class TestAgentsHaveContextPath:
    """_agents_have_context_path returns True only if ALL agents already have it."""

    def _agent_with_paths(self, paths):
        from types import SimpleNamespace

        ppm = SimpleNamespace(get_context_paths=lambda: [{"path": p} for p in paths])
        fm = SimpleNamespace(path_permission_manager=ppm)
        return SimpleNamespace(backend=SimpleNamespace(filesystem_manager=fm))

    def test_no_agents_is_false(self):
        assert _agents_have_context_path(None, "/x") is False
        assert _agents_have_context_path({}, "/x") is False

    def test_all_agents_have_path(self, tmp_path):
        agents = {"a": self._agent_with_paths([str(tmp_path)]), "b": self._agent_with_paths([str(tmp_path)])}
        assert _agents_have_context_path(agents, str(tmp_path)) is True

    def test_one_agent_missing_path(self, tmp_path):
        agents = {"a": self._agent_with_paths([str(tmp_path)]), "b": self._agent_with_paths([])}
        assert _agents_have_context_path(agents, str(tmp_path)) is False

    def test_agent_without_permission_manager_is_false(self, tmp_path):
        from types import SimpleNamespace

        agent = SimpleNamespace(backend=SimpleNamespace(filesystem_manager=None))
        assert _agents_have_context_path({"a": agent}, str(tmp_path)) is False


class TestBuildAgentDisplayInfo:
    """_build_agent_display_info derives welcome-screen ids/models in both modes."""

    def test_created_agents_read_backend_model(self):
        from types import SimpleNamespace

        agents = {"a": SimpleNamespace(backend=SimpleNamespace(model="gpt-5.4"))}
        ids, models = _build_agent_display_info(agents, None)
        assert ids == ["a"]
        assert models == {"a": "gpt-5.4"}

    def test_created_agents_fallback_to_config_backend_params(self):
        from types import SimpleNamespace

        # No backend.model attribute -> fall back to config.backend_params.
        agent = SimpleNamespace(config=SimpleNamespace(backend_params={"model": "claude-opus-4-6"}))
        ids, models = _build_agent_display_info({"b": agent}, None)
        assert ids == ["b"]
        assert models == {"b": "claude-opus-4-6"}

    def test_deferred_creation_reads_from_config_agents_list(self):
        cfg = {"agents": [{"id": "x", "backend": {"model": "gpt-5.4"}}, {"id": "y", "model": "grok-4"}]}
        ids, models = _build_agent_display_info(None, cfg)
        assert ids == ["x", "y"]
        assert models == {"x": "gpt-5.4", "y": "grok-4"}

    def test_deferred_single_agent_form_and_generated_ids(self):
        cfg = {"agent": {"backend": {"model": "gpt-5.4"}}}
        ids, models = _build_agent_display_info(None, cfg)
        assert ids == ["agent_0"]
        assert models == {"agent_0": "gpt-5.4"}

    def test_deferred_no_config_is_empty(self):
        ids, models = _build_agent_display_info(None, None)
        assert ids == []
        assert models == {}


class TestOrchestrationThreadContextPropagation:
    """MAS-274: the orchestration thread must inherit the per-run LoggingSession.

    run_textual_interactive_mode runs the controller on a background thread via
    ``contextvars.copy_context().run(...)``. Threads do NOT inherit ContextVars,
    so without that the per-run session ContextVar is invisible in the thread and
    falls back to the process-global session — cross-contaminating concurrent
    in-process runs. This pins the mechanism the fix relies on.
    """

    def test_copy_context_run_propagates_session_but_raw_thread_does_not(self):
        import contextvars
        import threading

        from massgen.logger_config import (
            LoggingSession,
            _current_session,
            get_current_session,
            set_current_session,
        )

        session = LoggingSession.create()
        token = set_current_session(session)
        try:
            ctx = contextvars.copy_context()
            seen: dict = {}

            def with_ctx():
                seen["with"] = get_current_session()

            def without_ctx():
                # Raw ContextVar (no implicit-global fallback) shows non-inheritance.
                seen["without"] = _current_session.get()

            t1 = threading.Thread(target=lambda: ctx.run(with_ctx))
            t1.start()
            t1.join()
            t2 = threading.Thread(target=without_ctx)
            t2.start()
            t2.join()

            assert seen["with"] is session  # copied context carries the session
            assert seen["without"] is None  # a raw thread does NOT inherit it
        finally:
            _current_session.reset(token)


class TestRunTextualTurnContract:
    """_run_textual_turn is now an importable, dependency-injected function.

    These lock its dependency-injection interface and its top-level error
    contract so the (still large) turn body can be decomposed further without
    silently changing how the controller drives it.
    """

    def test_injected_dependency_signature(self):
        import inspect

        from massgen.cli.run import _run_textual_turn

        sig = inspect.signature(_run_textual_turn)
        params = sig.parameters
        # Positional turn inputs.
        for name in ("question", "agents", "ui_config", "conversation_history", "session_info"):
            assert name in params
        # Collaborators are injected as keyword-only (the former closure captures).
        for name in ("display", "adapter", "context", "agent_ids", "config_path", "original_config", "orchestrator_cfg", "debug", "parse_at_references", "outer_kwargs"):
            assert params[name].kind is inspect.Parameter.KEYWORD_ONLY, name
        assert inspect.iscoroutinefunction(_run_textual_turn)

    @pytest.mark.asyncio
    async def test_returns_turnresult_on_unexpected_error(self):
        # Drive an early failure (display blows up) and assert the function's
        # top-level handler returns a TurnResult rather than propagating.
        from massgen.cli.run import _run_textual_turn

        class _ExplodingDisplay:
            def get_mode_state(self):
                raise RuntimeError("boom")

        result = await _run_textual_turn(
            "q",
            {"a": object()},
            {},
            [],
            {"session_id": "s1", "current_turn": 3},
            display=_ExplodingDisplay(),
            adapter=object(),
            context=object(),
            agent_ids=["a"],
            config_path=None,
            original_config={},
            orchestrator_cfg={},
            debug=False,
            parse_at_references=False,
            outer_kwargs={},
        )

        assert result.was_cancelled is False
        assert isinstance(result.error, RuntimeError)
        assert result.updated_session_id == "s1"
        assert result.updated_turn == 3


@pytest.mark.asyncio
class TestRunInteractiveModeDispatch:
    """run_interactive_mode routes to the Textual loop for the default display."""

    async def test_textual_display_delegates_to_textual_loop(self, monkeypatch):
        sentinel = object()
        fake_textual = AsyncMock(return_value=sentinel)
        monkeypatch.setattr(run_mod, "run_textual_interactive_mode", fake_textual)

        agents = {"a": object()}
        ui_config = {"display_type": "textual_terminal"}
        result = await run_mod.run_interactive_mode(
            agents=agents,
            ui_config=ui_config,
            config_path="cfg.yaml",
            initial_question="hello",
            debug=True,
        )

        assert result is sentinel
        fake_textual.assert_awaited_once()
        # Key params are forwarded to the Textual loop.
        kwargs = fake_textual.await_args.kwargs
        assert kwargs["agents"] is agents
        assert kwargs["ui_config"] is ui_config
        assert kwargs["config_path"] == "cfg.yaml"
        assert kwargs["initial_question"] == "hello"
        assert kwargs["debug"] is True

    async def test_default_display_is_textual(self, monkeypatch):
        # Missing display_type must default to the Textual loop (not the Rich path).
        fake_textual = AsyncMock(return_value=None)
        monkeypatch.setattr(run_mod, "run_textual_interactive_mode", fake_textual)

        await run_mod.run_interactive_mode(agents={"a": object()}, ui_config={})

        fake_textual.assert_awaited_once()

    async def test_non_textual_display_does_not_delegate(self, monkeypatch):
        # A non-textual display must NOT take the Textual delegation path. We stop
        # execution right after the dispatch decision by making the Rich console
        # raise, so we only assert the branch taken (not the full Rich loop).
        fake_textual = AsyncMock(return_value=None)
        monkeypatch.setattr(run_mod, "run_textual_interactive_mode", fake_textual)

        class _Boom(Exception):
            pass

        def _explode(*_a, **_k):
            raise _Boom

        monkeypatch.setattr(run_mod, "Console", _explode)

        with pytest.raises(_Boom):
            await run_mod.run_interactive_mode(
                agents={"a": object()},
                ui_config={"display_type": "rich_terminal"},
            )

        fake_textual.assert_not_awaited()
