"""A1 regression: the two near-identical mid-stream injection closures
(GeneralHookManager path + native path) are unified into a single
``MidStreamInjectionHookInstaller.build_midstream_injection(..., native=)``.

This closes the backend-parity hazard where a fix to one closure silently
skipped the other. These tests drive the REAL unified collaborator method
against a recording fake orchestrator (no LLM calls) and assert:

  - the load-bearing invariant: ``update_agent_context_with_new_answers`` runs
    BEFORE ``refresh_checklist_state_for_agent`` (so available_agent_labels
    reflect newly-injected labels) -- for BOTH native and non-native paths;
  - the captured revision counts (R1) are threaded into register;
  - state mutation (injection_count, midstream_injections_this_round,
    known_answer_ids, answers dict) is identical across paths;
  - the early-exit guards (disable_injection, vote-only, cap-reached) behave.
"""

from __future__ import annotations

import types

import pytest

from massgen.orchestrator import AgentState
from massgen.orchestrator_collaborators.midstream_injection_hook_installer import (
    MidStreamInjectionHookInstaller,
)


class _RecordingOrch:
    """Fake orchestrator capturing the order + arguments of injection side effects."""

    def __init__(self, *, selected=None, has_unseen_after=False, vote_only=False, disable=False, cap_reached=False):
        self.calls: list[tuple] = []
        self._selected = {} if selected is None else dict(selected)
        self._had_unseen = bool(selected) or cap_reached
        self._cap_reached = cap_reached
        self._has_unseen_after = has_unseen_after
        self._vote_only = vote_only

        self.config = types.SimpleNamespace(disable_injection=disable, max_midstream_injections_per_round=2)
        self.agent_states = {"A": AgentState(restart_pending=True)}
        self.agents = {"A": types.SimpleNamespace(backend=types.SimpleNamespace(filesystem_manager=None))}
        self.coordination_tracker = types.SimpleNamespace(
            get_reverse_agent_mapping=lambda: {},
            update_agent_context_with_new_answers=lambda aid, srcs: self.calls.append(("update_context", aid, tuple(srcs))),
            track_agent_action=lambda aid, action, msg: self.calls.append(("track", aid, msg)),
        )

    # --- guard predicates ---
    def _check_restart_pending(self, agent_id):
        return self.agent_states[agent_id].restart_pending

    def _should_defer_restart_for_first_answer(self, agent_id):
        return False

    def _is_vote_only_mode(self, agent_id):
        return self._vote_only

    def _should_defer_peer_updates_until_restart(self, agent_id):
        return False

    def _has_unseen_answer_updates(self, agent_id):
        return self._has_unseen_after

    def _should_skip_injection_due_to_timeout(self, agent_id):
        return False

    # --- selection ---
    def _get_current_answers_snapshot(self):
        return dict(self._selected) if self._selected else {}

    def _select_midstream_answer_updates(self, agent_id, current_answers):
        if self._cap_reached:
            return ({}, True)
        return (dict(self._selected), bool(self._selected))

    def _capture_answer_revision_counts(self, source_ids):
        return {sid: 7 for sid in source_ids}

    async def _copy_all_snapshots_to_temp_workspace(self, agent_id):
        self.calls.append(("copy_snapshots", agent_id))

    def _build_tool_result_injection(self, agent_id, selected, existing_answers=None):
        self.calls.append(("build_injection", agent_id, tuple(selected)))
        return "INJECTION_PAYLOAD"

    # --- post-record side effects ---
    def _register_injected_answer_updates(self, agent_id, source_ids, seen_counts=None):
        self.calls.append(("register", agent_id, tuple(source_ids), tuple(sorted((seen_counts or {}).items()))))

    def _mark_pending_checklist_recheck_labels(self, agent_id, source_ids):
        self.calls.append(("mark_pending", agent_id, tuple(source_ids)))

    def _refresh_checklist_state_for_agent(self, agent_id):
        self.calls.append(("refresh_checklist", agent_id))

    def _order(self) -> list[str]:
        return [c[0] for c in self.calls]


@pytest.mark.asyncio
@pytest.mark.parametrize("native", [False, True])
async def test_a1_unified_injection_happy_path(native) -> None:
    orch = _RecordingOrch(selected={"B": "peer answer"})
    installer = MidStreamInjectionHookInstaller(orch)
    answers: dict[str, str] = {}

    result = await installer.build_midstream_injection("A", answers, native=native)

    assert result == "INJECTION_PAYLOAD"
    # answers dict mutated so the same content isn't re-injected
    assert answers == {"B": "peer answer"}
    state = orch.agent_states["A"]
    assert state.injection_count == 1
    assert state.midstream_injections_this_round == 1
    assert "B" in state.known_answer_ids

    order = orch._order()
    # Load-bearing invariant (both paths): context update BEFORE checklist refresh.
    assert order.index("update_context") < order.index("refresh_checklist")
    # R1: captured counts threaded into register.
    register_call = next(c for c in orch.calls if c[0] == "register")
    assert register_call[3] == (("B", 7),)
    # snapshot copy happens before building the injection
    assert order.index("copy_snapshots") < order.index("build_injection")


@pytest.mark.asyncio
async def test_a1_native_and_general_have_same_effect_order() -> None:
    """The unified method yields the identical side-effect sequence regardless of path."""
    orch_general = _RecordingOrch(selected={"B": "x"})
    orch_native = _RecordingOrch(selected={"B": "x"})
    await MidStreamInjectionHookInstaller(orch_general).build_midstream_injection("A", {}, native=False)
    await MidStreamInjectionHookInstaller(orch_native).build_midstream_injection("A", {}, native=True)

    assert orch_general._order() == orch_native._order()


@pytest.mark.asyncio
@pytest.mark.parametrize("native", [False, True])
async def test_a1_disable_injection_short_circuits(native) -> None:
    orch = _RecordingOrch(selected={"B": "x"}, disable=True)
    result = await MidStreamInjectionHookInstaller(orch).build_midstream_injection("A", {}, native=native)
    assert result is None
    assert orch.calls == []  # nothing happened


@pytest.mark.asyncio
@pytest.mark.parametrize("native", [False, True])
async def test_a1_vote_only_mode_skips_injection(native) -> None:
    orch = _RecordingOrch(selected={"B": "x"}, vote_only=True)
    result = await MidStreamInjectionHookInstaller(orch).build_midstream_injection("A", {}, native=native)
    assert result is None
    assert "build_injection" not in orch._order()


@pytest.mark.asyncio
@pytest.mark.parametrize("native", [False, True])
async def test_a1_cap_reached_keeps_restart_pending(native) -> None:
    orch = _RecordingOrch(cap_reached=True)
    result = await MidStreamInjectionHookInstaller(orch).build_midstream_injection("A", {}, native=native)
    assert result is None
    assert orch.agent_states["A"].restart_pending is True
    assert "build_injection" not in orch._order()
