"""Pre-collab helper utilities, extracted from Orchestrator.

This collaborator owns a small set of helpers used by pre-collab subagent
spawning paths (and by sibling collaborators such as
EvaluationCriteriaGenerator, PersonaInjector, PromptImproverCollaborator,
CriteriaEvolutionRunner, RoundEvaluatorRunner, and BootstrapCriteriaEngine).

Notes:
- All five helpers remain reachable as thin delegators on Orchestrator so the
  existing call sites (and the monkeypatch in
  ``test_evolving_criteria.py:158`` of ``_notify_precollab_completed``)
  continue to work unchanged.
- ``get_log_session_dir`` / ``get_log_session_root`` are looked up lazily via
  the ``massgen.orchestrator`` module so test patches at the orchestrator
  namespace still take effect.
"""

from __future__ import annotations

import tempfile
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class PreCollabHelpers:
    """Helpers supporting pre-collab subagent spawning and notifications."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    def build_parent_agent_configs(self) -> list[dict[str, Any]]:
        """Build simplified agent configs for subagent inheritance."""
        configs: list[dict[str, Any]] = []
        for agent_id, agent in self._orchestrator.agents.items():
            agent_cfg: dict[str, Any] = {"id": agent_id}
            if hasattr(agent, "backend") and hasattr(agent.backend, "config"):
                backend_cfg = {k: v for k, v in agent.backend.config.items() if k not in ("mcp_servers", "_config_path")}
                agent_cfg["backend"] = backend_cfg
            configs.append(agent_cfg)
        return configs

    def get_parent_workspace(self, fallback_prefix: str = "massgen_precollab_") -> str:
        """Return the first agent's workspace path, or a temp dir."""
        for agent in self._orchestrator.agents.values():
            fm = getattr(getattr(agent, "backend", None), "filesystem_manager", None)
            if fm and fm.cwd:
                return str(fm.cwd)
        return tempfile.mkdtemp(prefix=fallback_prefix)

    @staticmethod
    def get_log_directory() -> str | None:
        """Return the current log session directory as a string, or None."""
        # Lazy lookup through the orchestrator module so test patches of
        # ``massgen.orchestrator.get_log_session_dir`` still apply.
        try:
            from massgen import orchestrator as _orch_mod

            log_dir = _orch_mod.get_log_session_dir()
            return str(log_dir) if log_dir else None
        except Exception:
            return None

    def make_precollab_started_callback(
        self,
        anchor_agent: str | None,
        call_id: str,
        display: Any,
    ):
        """Build a callback for pre-collab subagent start notifications."""

        def _on_started(
            subagent_id: str,
            subagent_task: str,
            timeout_seconds: int,
            status_callback: Any,
            log_path: str | None,
        ) -> None:
            from massgen import orchestrator as _orch_mod

            _emitter = _orch_mod.get_event_emitter()
            if _emitter:
                _emitter.emit_raw(
                    _orch_mod.StructuredEventType.PRE_COLLAB_STARTED,
                    agent_id=anchor_agent,
                    subagent_id=subagent_id,
                    task=subagent_task,
                    timeout_seconds=timeout_seconds,
                    call_id=call_id,
                    log_path=log_path,
                )
            if display and anchor_agent and hasattr(display, "notify_runtime_subagent_started"):
                try:
                    display.notify_runtime_subagent_started(
                        agent_id=anchor_agent,
                        subagent_id=subagent_id,
                        task=subagent_task,
                        timeout_seconds=timeout_seconds,
                        call_id=call_id,
                        status_callback=status_callback,
                        log_path=log_path,
                    )
                except Exception:
                    pass

        return _on_started

    def notify_precollab_completed(
        self,
        anchor_agent: str | None,
        subagent_id: str,
        call_id: str,
        display: Any,
        *,
        status: str = "completed",
        answer_preview: str = "",
        error: str | None = None,
    ) -> None:
        """Emit event + notify display for a pre-collab phase completion."""
        from massgen import orchestrator as _orch_mod

        _emitter = _orch_mod.get_event_emitter()
        kwargs: dict[str, Any] = {
            "agent_id": anchor_agent,
            "subagent_id": subagent_id,
            "call_id": call_id,
            "status": status,
        }
        if error:
            kwargs["error"] = error
        if answer_preview:
            kwargs["answer_preview"] = answer_preview
        if _emitter and anchor_agent:
            _emitter.emit_raw(_orch_mod.StructuredEventType.PRE_COLLAB_COMPLETED, **kwargs)

        if display and anchor_agent and hasattr(display, "notify_runtime_subagent_completed"):
            try:
                display.notify_runtime_subagent_completed(**kwargs)
            except Exception:
                pass
