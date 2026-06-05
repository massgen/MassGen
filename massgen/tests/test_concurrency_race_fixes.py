"""Concurrency race-fix regression tests (Tranche 1 of next_version_eng_health_plan.md).

Covers the two verified, lock-free races from the concurrency audit:

R1 — Lost peer-answer revision: the mid-stream injection path selected peer
     answer *content* before a yielding ``await`` (snapshot copy), then marked
     the peer as "seen" by re-reading the **live** revision count afterward. If
     the peer appended a new revision during the await, the agent was marked as
     having seen a revision it was never shown -> that revision is never injected.
     Fix: thread the revision counts captured *at selection time* through
     ``register_injected_answer_updates`` / ``mark_seen_answer_revisions`` via an
     optional ``seen_counts`` argument.

R2/R3 — Lost background-subagent result: the injection paths did
     read-snapshot -> ``await`` -> blind ``_pending_subagent_results.pop(agent_id)``.
     A background task appending a fresh result during the await had it silently
     discarded by the whole-key pop. Fix: ``consume_pending_subagent_results``
     removes only the consumed subagent ids, preserving concurrent appends.

These tests drive the REAL collaborator code (PeerAnswerVisibilityTracker,
SubagentLifecycleCoordinator) against a lightweight fake orchestrator -- no
external LLM calls, fully deterministic. The "simulation" tests reproduce the
exact interleaving by appending to shared state between the collect and the
consume/mark, the same window the real ``await`` opens.
"""

from __future__ import annotations

import asyncio
import types

import pytest

from massgen.orchestrator import AgentState
from massgen.orchestrator_collaborators.peer_answer_visibility_tracker import (
    PeerAnswerVisibilityTracker,
)
from massgen.orchestrator_collaborators.subagent_lifecycle_coordinator import (
    SubagentLifecycleCoordinator,
)


# --------------------------------------------------------------------------- #
# Test doubles
# --------------------------------------------------------------------------- #
class _Revision:
    """Minimal stand-in for a coordination answer revision."""

    def __init__(self, content: str, timestamp: float, label: str | None = None) -> None:
        self.content = content
        self.timestamp = timestamp
        self.label = label


class _FakeCoordTracker:
    def __init__(self) -> None:
        self.answers_by_agent: dict[str, list[_Revision]] = {}


def _make_peer_orch(agent_ids: list[str]) -> types.SimpleNamespace:
    """A fake orchestrator exposing just what PeerAnswerVisibilityTracker reads."""
    orch = types.SimpleNamespace()
    orch.coordination_tracker = _FakeCoordTracker()
    orch.agent_states = {aid: AgentState() for aid in agent_ids}
    orch.agents = {aid: types.SimpleNamespace(backend=None) for aid in agent_ids}
    orch.config = types.SimpleNamespace(max_midstream_injections_per_round=2)
    orch._step_mode = None
    orch._step_inputs = None
    orch._is_decomposition_mode = lambda: False
    orch._is_fairness_enabled = lambda: False
    return orch


def _make_sub_orch() -> types.SimpleNamespace:
    orch = types.SimpleNamespace()
    orch._pending_subagent_results = {}
    orch._injected_subagents = {}
    orch.agents = {"A": types.SimpleNamespace()}
    return orch


# --------------------------------------------------------------------------- #
# R1 — peer-answer visibility race
# --------------------------------------------------------------------------- #
def test_r1_mark_seen_uses_captured_counts_not_live() -> None:
    """The agent must be marked seen up to what it was SHOWN, not the live count.

    Reproduces the race window: capture counts at selection, a peer appends a
    new revision (the await window), then we register the injection.
    """
    orch = _make_peer_orch(["A", "B"])
    tracker = PeerAnswerVisibilityTracker(orch)

    # B has 2 revisions; A is shown content as of count==2.
    orch.coordination_tracker.answers_by_agent["B"] = [
        _Revision("v1", 1.0),
        _Revision("v2", 2.0),
    ]
    orch.agent_states["B"].answer = "v2"
    captured = {"B": tracker.get_agent_answer_revision_count("B")}
    assert captured["B"] == 2

    # --- the await window: B publishes revision 3 concurrently ---
    orch.coordination_tracker.answers_by_agent["B"].append(_Revision("v3", 3.0))
    orch.agent_states["B"].answer = "v3"

    # Register the injection using the counts captured at selection time.
    tracker.register_injected_answer_updates("A", ["B"], seen_counts=captured)

    # A was only shown rev2 -> must be marked seen==2, NOT the live 3.
    assert orch.agent_states["A"].seen_answer_counts["B"] == 2
    # rev3 remains unseen, so it can still be injected / trigger a restart.
    assert tracker.has_unseen_answer_updates("A") is True


def test_r1_without_captured_counts_falls_back_to_live() -> None:
    """Backward-compat: omitting seen_counts preserves the legacy live-read behavior.

    Existing callers/tests that call register/mark without seen_counts must keep
    working unchanged.
    """
    orch = _make_peer_orch(["A", "B"])
    tracker = PeerAnswerVisibilityTracker(orch)
    orch.coordination_tracker.answers_by_agent["B"] = [
        _Revision("v1", 1.0),
        _Revision("v2", 2.0),
        _Revision("v3", 3.0),
    ]
    orch.agent_states["B"].answer = "v3"

    tracker.register_injected_answer_updates("A", ["B"])  # no seen_counts

    assert orch.agent_states["A"].seen_answer_counts["B"] == 3
    assert tracker.has_unseen_answer_updates("A") is False


def test_r1_mark_seen_never_regresses_existing_count() -> None:
    """A captured count must never lower an already-higher seen count."""
    orch = _make_peer_orch(["A", "B"])
    tracker = PeerAnswerVisibilityTracker(orch)
    orch.coordination_tracker.answers_by_agent["B"] = [
        _Revision("v1", 1.0),
        _Revision("v2", 2.0),
        _Revision("v3", 3.0),
    ]
    orch.agent_states["A"].seen_answer_counts["B"] = 5  # already ahead

    tracker.mark_seen_answer_revisions("A", ["B"], seen_counts={"B": 2})

    assert orch.agent_states["A"].seen_answer_counts["B"] == 5


def test_r1_captured_count_clamped_to_current() -> None:
    """A captured count larger than the live list is clamped (defensive)."""
    orch = _make_peer_orch(["A", "B"])
    tracker = PeerAnswerVisibilityTracker(orch)
    orch.coordination_tracker.answers_by_agent["B"] = [_Revision("v1", 1.0)]

    tracker.mark_seen_answer_revisions("A", ["B"], seen_counts={"B": 99})

    assert orch.agent_states["A"].seen_answer_counts["B"] == 1


# --------------------------------------------------------------------------- #
# R2 / R3 — background-subagent result consume race
# --------------------------------------------------------------------------- #
def test_r2_consume_removes_only_consumed_ids() -> None:
    orch = _make_sub_orch()
    orch._pending_subagent_results["A"] = [("s1", "r1"), ("s2", "r2")]
    coord = SubagentLifecycleCoordinator(orch)

    coord.consume_pending_subagent_results("A", {"s1"})

    assert orch._pending_subagent_results["A"] == [("s2", "r2")]


def test_r2_consume_drops_key_when_fully_consumed() -> None:
    orch = _make_sub_orch()
    orch._pending_subagent_results["A"] = [("s1", "r1"), ("s2", "r2")]
    coord = SubagentLifecycleCoordinator(orch)

    coord.consume_pending_subagent_results("A", {"s1", "s2"})

    assert "A" not in orch._pending_subagent_results


def test_r2_consume_missing_key_is_noop() -> None:
    orch = _make_sub_orch()
    coord = SubagentLifecycleCoordinator(orch)
    coord.consume_pending_subagent_results("A", {"s1"})  # must not raise
    assert orch._pending_subagent_results == {}


def test_r2_consume_preserves_concurrent_append() -> None:
    """Simulation of the race window with a manual snapshot/consume."""
    orch = _make_sub_orch()
    orch._pending_subagent_results["A"] = [("s1", "r1")]
    coord = SubagentLifecycleCoordinator(orch)

    collected_ids = {sid for sid, _ in orch._pending_subagent_results["A"]}
    # --- await window: a background task appends a fresh result ---
    orch._pending_subagent_results["A"].append(("s2", "r2"))

    coord.consume_pending_subagent_results("A", collected_ids)

    assert orch._pending_subagent_results["A"] == [("s2", "r2")]


@pytest.mark.asyncio
async def test_r2_collect_then_consume_preserves_late_append(monkeypatch) -> None:
    """End-to-end simulation through the REAL collect + consume code path.

    Drives ``collect_pending_subagent_results_async`` (the real consumer read),
    appends a fresh result during the simulated await window, then consumes only
    the collected ids -- proving the late append survives.
    """
    orch = _make_sub_orch()
    orch._pending_subagent_results["A"] = [("s1", "r1")]
    coord = SubagentLifecycleCoordinator(orch)

    async def _no_mcp_poll(agent_id: str):
        return []

    monkeypatch.setattr(coord, "get_pending_subagent_results_async", _no_mcp_poll)

    collected = await coord.collect_pending_subagent_results_async("A")
    assert [sid for sid, _ in collected] == ["s1"]

    # --- await window: background trace-analyzer task appends a result ---
    orch._pending_subagent_results["A"].append(("s2", "r2"))

    coord.consume_pending_subagent_results("A", {sid for sid, _ in collected})

    assert [sid for sid, _ in orch._pending_subagent_results["A"]] == ["s2"]


# --------------------------------------------------------------------------- #
# R4 — detached trace-analyzer tasks must be cancelled by timeout cleanup
# --------------------------------------------------------------------------- #
def _make_cleanup_orch() -> types.SimpleNamespace:
    orch = types.SimpleNamespace()
    orch._subagent_launch_watcher = None
    orch._flush_pending_subagent_results = lambda: None
    orch._active_tasks = {}
    orch.agents = {}
    orch._active_streams = {}
    orch.is_orchestrator_timeout = True
    orch.coordination_tracker = types.SimpleNamespace(track_agent_action=lambda *a, **k: None)
    orch._background_trace_tasks = {}
    return orch


@pytest.mark.asyncio
async def test_r4_cleanup_cancels_background_trace_tasks() -> None:
    """Timeout cleanup must cancel detached trace tasks, not leak them past timeout."""
    from massgen.orchestrator_collaborators.active_coordination_cleanup import (
        ActiveCoordinationCleanup,
    )

    orch = _make_cleanup_orch()

    async def _never_finishes():
        await asyncio.sleep(60)

    task = asyncio.create_task(_never_finishes())
    await asyncio.sleep(0)  # let the task start
    orch._background_trace_tasks = {"A": task}

    await ActiveCoordinationCleanup(orch).cleanup()

    assert task.cancelled() or task.done()
    assert orch._background_trace_tasks == {}


@pytest.mark.asyncio
async def test_r4_cleanup_skips_already_done_trace_tasks() -> None:
    from massgen.orchestrator_collaborators.active_coordination_cleanup import (
        ActiveCoordinationCleanup,
    )

    orch = _make_cleanup_orch()

    async def _quick():
        return None

    task = asyncio.create_task(_quick())
    await task  # already done
    orch._background_trace_tasks = {"A": task}

    await ActiveCoordinationCleanup(orch).cleanup()  # must not raise

    assert orch._background_trace_tasks == {}


# --------------------------------------------------------------------------- #
# R5 — cancel_all_subagents must await cancellations before clearing the registry
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_r5_cancel_all_awaits_background_tasks_before_clear() -> None:
    """Cancelled background tasks run their CancelledError handler before return.

    Without awaiting, the method clears the registry and returns while the
    cancelled coroutine has not yet resumed -- its cleanup runs later against a
    cleared dict. The fix gathers the cancellations first.
    """
    from massgen.subagent.manager import SubagentManager

    mgr = SubagentManager.__new__(SubagentManager)
    mgr._active_processes = {}
    mgr._subagents = {}

    handler_ran = {"value": False}

    async def _bg():
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            handler_ran["value"] = True
            raise

    task = asyncio.create_task(_bg())
    await asyncio.sleep(0)  # let it start
    mgr._background_tasks = {"s1": task}

    count = await mgr.cancel_all_subagents()

    assert handler_ran["value"] is True, "cancellation was not awaited before return"
    assert task.done()
    assert mgr._background_tasks == {}
    assert count >= 1


# --------------------------------------------------------------------------- #
# D2 — per-round worktree isolation failure is recorded, not silently swallowed
# --------------------------------------------------------------------------- #
def test_d2_default_agent_state_not_degraded() -> None:
    state = AgentState()
    assert state.round_isolation_degraded is False
    assert state.round_isolation_error is None


def test_d2_records_round_isolation_degradation(mock_orchestrator) -> None:
    orch = mock_orchestrator(num_agents=2)

    orch._record_round_isolation_degraded("agent_a", RuntimeError("git worktree add failed"))

    degraded = orch.agent_states["agent_a"]
    assert degraded.round_isolation_degraded is True
    assert "RuntimeError" in degraded.round_isolation_error
    assert "git worktree add failed" in degraded.round_isolation_error
    # untouched agents stay clean
    assert orch.agent_states["agent_b"].round_isolation_degraded is False


def test_d2_record_is_safe_for_unknown_agent(mock_orchestrator) -> None:
    orch = mock_orchestrator(num_agents=1)
    # Must not raise even if the agent id is not in agent_states.
    orch._record_round_isolation_degraded("nonexistent", ValueError("boom"))


def test_d2_emits_status_with_valid_signature(mock_orchestrator, monkeypatch) -> None:
    """The degradation signal must reach the emitter via emit_status's real
    contract (message=..., agent_id=...). A previous bug passed status=..., which
    is not a parameter of EventEmitter.emit_status, so the call raised TypeError
    that was silently swallowed -- the visible signal never fired.
    """
    import massgen.orchestrator as orch_mod

    captured: dict[str, object] = {}

    class _Emitter:
        def emit_status(self, message, level="info", agent_id=None):
            captured["message"] = message
            captured["level"] = level
            captured["agent_id"] = agent_id

    orch = mock_orchestrator(num_agents=1)
    monkeypatch.setattr(orch_mod, "get_event_emitter", lambda: _Emitter())

    orch._record_round_isolation_degraded("agent_a", RuntimeError("git worktree add failed"))

    # The emitter must have been called with a real message + agent_id and no
    # bogus status kwarg (the _Emitter signature would TypeError on status=).
    assert captured.get("agent_id") == "agent_a"
    assert "round isolation degraded" in str(captured.get("message", ""))
    assert "git worktree add failed" in str(captured.get("message", ""))


# --------------------------------------------------------------------------- #
# D3 — post-record changedoc enrichment must not kill a valid-answer agent
# --------------------------------------------------------------------------- #
class _Answer:
    def __init__(self, label: str) -> None:
        self.label = label
        self.changedoc = None


def test_d3_changedoc_attached_happy_path(mock_orchestrator, monkeypatch) -> None:
    orch = mock_orchestrator(num_agents=1)
    agent = orch.agents["agent_a"]
    agent.backend.filesystem_manager = types.SimpleNamespace(cwd="/tmp/ws")
    monkeypatch.setattr(orch, "_is_changedoc_enabled", lambda: True)
    ans = _Answer("agent1.1")
    orch.coordination_tracker.answers_by_agent["agent_a"] = [ans]

    import massgen.changedoc as cd

    monkeypatch.setattr(cd, "read_changedoc_from_workspace", lambda p: "changes by [SELF]")

    orch._attach_changedoc_to_latest_answer("agent_a", agent)

    assert ans.changedoc == "changes by agent1.1"


def test_d3_changedoc_failure_does_not_raise_and_preserves_answer(mock_orchestrator, monkeypatch) -> None:
    orch = mock_orchestrator(num_agents=1)
    agent = orch.agents["agent_a"]
    agent.backend.filesystem_manager = types.SimpleNamespace(cwd="/tmp/ws")
    monkeypatch.setattr(orch, "_is_changedoc_enabled", lambda: True)
    ans = _Answer("agent1.1")
    orch.coordination_tracker.answers_by_agent["agent_a"] = [ans]

    import massgen.changedoc as cd

    def _boom(_path):
        raise OSError("disk gone")

    monkeypatch.setattr(cd, "read_changedoc_from_workspace", _boom)

    # Must not raise — the agent already submitted a valid answer.
    orch._attach_changedoc_to_latest_answer("agent_a", agent)

    assert ans.changedoc is None
    assert orch.agent_states["agent_a"].is_killed is False
