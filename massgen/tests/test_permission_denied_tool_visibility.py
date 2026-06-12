"""A permission-denied tool call must surface as a first-class FAILED tool call.

The chokepoint returns early on deny, before the normal emit_tool_start /
emit_tool_complete path — so without explicit emission the denied call shows only a
transient status line and never appears as a tool-call row in the TUI/WebUI timeline
(no command, no error result). These tests pin the two helpers that fix that:

- ``_emit_denied_tool_call`` emits tool_start + tool_complete(is_error=True).
- ``_denied_tool_preview`` renders the attempted command for the human-facing text.
"""

from __future__ import annotations

from types import SimpleNamespace

from massgen.backend import base_with_custom_tool_and_mcp as mod
from massgen.backend.base_with_custom_tool_and_mcp import CustomToolAndMCPBackend


def test_denied_tool_emits_start_then_error_complete(monkeypatch):
    events = []

    class FakeEmitter:
        def emit_tool_start(self, **kw):
            events.append(("start", kw))

        def emit_tool_complete(self, **kw):
            events.append(("complete", kw))

    monkeypatch.setattr(mod, "get_event_emitter", lambda: FakeEmitter())
    stub = SimpleNamespace(agent_id="guarded")

    CustomToolAndMCPBackend._emit_denied_tool_call(
        stub,
        call_id="call_2",
        tool_name="mcp__command_line__execute_command",
        args={"command": "curl -s https://example.com"},
        reason="Denied by automation policy: high-risk",
        server_name="mcp",
    )

    # A real failed tool call: start (with the attempted command) THEN error-complete.
    assert [e[0] for e in events] == ["start", "complete"]
    start_kw, complete_kw = events[0][1], events[1][1]
    assert start_kw["tool_id"] == "call_2"
    assert start_kw["tool_name"] == "mcp__command_line__execute_command"
    assert start_kw["args"]["command"] == "curl -s https://example.com"
    assert complete_kw["tool_id"] == "call_2"
    assert complete_kw["is_error"] is True
    assert complete_kw["status"] == "denied"
    assert "Denied by automation policy" in str(complete_kw["result"])


def test_denied_tool_emission_is_safe_without_emitter(monkeypatch):
    # No event emitter configured (e.g. headless) → no crash, no events.
    monkeypatch.setattr(mod, "get_event_emitter", lambda: None)
    stub = SimpleNamespace(agent_id="a1")
    # Must not raise.
    CustomToolAndMCPBackend._emit_denied_tool_call(
        stub,
        call_id="c1",
        tool_name="bash",
        args={"command": "ls"},
        reason="nope",
    )


def test_denied_tool_emission_never_breaks_on_emitter_error(monkeypatch):
    class BoomEmitter:
        def emit_tool_start(self, **kw):
            raise RuntimeError("boom")

        def emit_tool_complete(self, **kw):
            pass

    monkeypatch.setattr(mod, "get_event_emitter", lambda: BoomEmitter())
    stub = SimpleNamespace(agent_id="a1")
    # A telemetry failure must never break tool execution.
    CustomToolAndMCPBackend._emit_denied_tool_call(stub, call_id="c1", tool_name="bash", args={}, reason="r")


# --------------------------------------------------------------------------- #
# Human-facing preview: show WHAT was blocked, not just the tool name
# --------------------------------------------------------------------------- #
def test_preview_shows_the_command():
    p = CustomToolAndMCPBackend._denied_tool_preview(
        "mcp__command_line__execute_command",
        {"command": "curl -s https://example.com"},
    )
    assert p == "$ curl -s https://example.com"


def test_preview_falls_back_to_path_then_tool_name():
    assert CustomToolAndMCPBackend._denied_tool_preview("write_file", {"path": "/x/y.txt"}) == "write_file /x/y.txt"
    assert CustomToolAndMCPBackend._denied_tool_preview("some_tool", {}) == "some_tool"
