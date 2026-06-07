"""Deterministic tests for programmatic steering via the runtime inbox.

These verify the wiring that lets `--automation` (and any UI-less caller) inject
mid-stream human input without a TUI/WebUI:

  send_steering_message() -> msg_*.json in inbox dir
      -> RuntimeInboxPoller.poll()
          -> RuntimeInputDelivery.poll_runtime_inbox()
              -> HumanInputHook.set_pending_input(content, target_agents, source)

The chokepoint (`set_pending_input`) is the SAME one the TUI (`_queue_human_input`)
and WebUI (`broadcast_response`) call, so this covers all backends. Targeting
(one / subset / all) is exercised explicitly.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from massgen.mcp_tools.hooks import HumanInputHook, RuntimeInboxPoller
from massgen.orchestrator_collaborators.runtime_input_delivery import (
    RuntimeInputDelivery,
)
from massgen.steering import send_steering_message


class TestSendSteeringMessage:
    """The writer produces a msg the poller can read, with correct targeting."""

    def test_writes_pollable_message_broadcast(self, tmp_path):
        send_steering_message(tmp_path, "focus on errors")
        files = list(tmp_path.glob("msg_*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text())
        assert data["content"] == "focus on errors"
        # No target_agents key => broadcast to all (poller returns None)
        assert "target_agents" not in data

    def test_writes_targeted_message(self, tmp_path):
        send_steering_message(tmp_path, "add tests", target_agents=["agent_b"])
        data = json.loads(next(tmp_path.glob("msg_*.json")).read_text())
        assert data["target_agents"] == ["agent_b"]

    def test_rejects_empty_content(self, tmp_path):
        with pytest.raises(ValueError):
            send_steering_message(tmp_path, "   ")

    def test_unique_filenames_for_rapid_sends(self, tmp_path):
        for i in range(5):
            send_steering_message(tmp_path, f"msg {i}")
        assert len(list(tmp_path.glob("msg_*.json"))) == 5

    def test_poller_reads_what_writer_wrote(self, tmp_path):
        send_steering_message(tmp_path, "hello", target_agents=["a1"], source="programmatic")
        poller = RuntimeInboxPoller(inbox_dir=tmp_path, min_poll_interval=0.0)
        msgs = poller.poll()
        assert len(msgs) == 1
        assert msgs[0]["content"] == "hello"
        assert msgs[0]["target_agents"] == ["a1"]
        assert msgs[0]["source"] == "programmatic"


def _delivery_with_stub(tmp_path, agent_ids=("agent_a", "agent_b")):
    """Build a RuntimeInputDelivery over a minimal stub orchestrator."""
    hook = HumanInputHook()
    orch = SimpleNamespace(
        _runtime_inbox_poller=None,
        _human_input_hook=hook,
        _agent_temporary_workspace=None,
        agents={aid: SimpleNamespace(backend=None) for aid in agent_ids},
        # Attributes touched by the hook-callback wiring (no-ops in this sync test)
        _poll_runtime_inbox=lambda: None,
        _maybe_interrupt_background_wait_for_agent=lambda *a, **k: None,
        _human_input_display=None,
    )
    delivery = RuntimeInputDelivery(orch)
    return delivery, orch, hook


class TestEnvOverrideResolution:
    """MASSGEN_RUNTIME_INBOX_DIR forces a deterministic inbox dir."""

    def test_env_override_initializes_poller_at_dir(self, tmp_path, monkeypatch):
        inbox = tmp_path / "my_inbox"
        monkeypatch.setenv("MASSGEN_RUNTIME_INBOX_DIR", str(inbox))
        delivery, orch, _ = _delivery_with_stub(tmp_path)

        delivery.ensure_runtime_inbox_poller_initialized()

        assert orch._runtime_inbox_poller is not None
        assert orch._runtime_inbox_poller._inbox_dir == inbox
        assert inbox.exists()  # created even though it didn't exist

    def test_no_override_no_workspace_yields_no_poller(self, tmp_path, monkeypatch):
        # Without the override AND without any backend workspace, the legacy
        # heuristic resolves to None and no poller is created (unchanged behavior).
        monkeypatch.delenv("MASSGEN_RUNTIME_INBOX_DIR", raising=False)
        delivery, orch, _ = _delivery_with_stub(tmp_path)
        delivery.ensure_runtime_inbox_poller_initialized()
        assert orch._runtime_inbox_poller is None


class TestPollRoutesToChokepoint:
    """A dropped steering message reaches set_pending_input with right targeting."""

    def _drain(self, delivery, orch, monkeypatch):
        # poll_runtime_inbox imports get_event_emitter from massgen.orchestrator;
        # stub it so the emitter branch is a no-op.
        monkeypatch.setattr("massgen.orchestrator.get_event_emitter", lambda: None, raising=False)
        delivery.poll_runtime_inbox()

    def test_broadcast_message_queued_for_all(self, tmp_path, monkeypatch):
        inbox = tmp_path / "inbox"
        monkeypatch.setenv("MASSGEN_RUNTIME_INBOX_DIR", str(inbox))
        delivery, orch, hook = _delivery_with_stub(tmp_path)
        delivery.ensure_runtime_inbox_poller_initialized()

        send_steering_message(inbox, "steer all")
        orch._runtime_inbox_poller._min_poll_interval = 0.0  # defeat throttle
        self._drain(delivery, orch, monkeypatch)

        pending = hook._pending_messages
        assert len(pending) == 1
        assert pending[0]["content"] == "steer all"
        assert pending[0]["target_agents"] is None  # None => all agents

    def test_targeted_subset(self, tmp_path, monkeypatch):
        inbox = tmp_path / "inbox"
        monkeypatch.setenv("MASSGEN_RUNTIME_INBOX_DIR", str(inbox))
        delivery, orch, hook = _delivery_with_stub(tmp_path, agent_ids=("a", "b", "c"))
        delivery.ensure_runtime_inbox_poller_initialized()

        send_steering_message(inbox, "only b and c", target_agents=["b", "c"])
        orch._runtime_inbox_poller._min_poll_interval = 0.0
        self._drain(delivery, orch, monkeypatch)

        assert hook._pending_messages[0]["target_agents"] == {"b", "c"}

    def test_single_target(self, tmp_path, monkeypatch):
        inbox = tmp_path / "inbox"
        monkeypatch.setenv("MASSGEN_RUNTIME_INBOX_DIR", str(inbox))
        delivery, orch, hook = _delivery_with_stub(tmp_path)
        delivery.ensure_runtime_inbox_poller_initialized()

        send_steering_message(inbox, "only agent_b", target_agents=["agent_b"])
        orch._runtime_inbox_poller._min_poll_interval = 0.0
        self._drain(delivery, orch, monkeypatch)

        assert hook._pending_messages[0]["target_agents"] == {"agent_b"}
