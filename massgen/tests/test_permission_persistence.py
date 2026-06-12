"""P2.2 — persistence of `always` grants + read-back as merged rules.

The modal's "Always" button yields a ``GrantScope.ALWAYS`` decision. For that to
mean *always* (and not silently behave as session-only), the coordinator must
persist it and a later run must load it back. These tests pin both halves of the
loop: write an allow rule to ``settings.local.json``, then evaluate a fresh
rule set loaded from that file.
"""

from __future__ import annotations

import json

from massgen.permissions.models import ApprovalDecision, AuthorizationObject, GrantScope
from massgen.permissions.persistence import load_persisted_rules, make_persist_callback


def _authz(tool="bash", arguments=None, normalized_pattern="command:make build"):
    return AuthorizationObject(
        agent_id="a1",
        tool=tool,
        arguments=arguments if arguments is not None else {"command": "make build"},
        normalized_pattern=normalized_pattern,
    )


def test_persist_then_load_roundtrip_command(tmp_path):
    path = tmp_path / "settings.local.json"
    persist = make_persist_callback(path)
    persist(_authz(), ApprovalDecision(allowed=True, scope=GrantScope.ALWAYS, operator="human"))

    rs = load_persisted_rules(path)
    assert rs is not None
    # The exact command the human approved is now allowed without prompting.
    assert rs.evaluate("bash", {"command": "make build"}) == "allow"
    # A different command is NOT covered.
    assert rs.evaluate("bash", {"command": "rm -rf build"}) is None


def test_persist_then_load_roundtrip_write_path(tmp_path):
    path = tmp_path / "settings.local.json"
    persist = make_persist_callback(path)
    persist(
        _authz(tool="write_file", arguments={"file_path": "/proj/out.txt"}, normalized_pattern="write_file:/proj/out.txt"),
        ApprovalDecision(allowed=True, scope=GrantScope.ALWAYS, operator="human"),
    )
    rs = load_persisted_rules(path)
    assert rs is not None
    assert rs.evaluate("write_file", {"file_path": "/proj/out.txt"}) == "allow"


def test_persist_is_append_only_and_deduped(tmp_path):
    path = tmp_path / "settings.local.json"
    persist = make_persist_callback(path)
    dec = ApprovalDecision(allowed=True, scope=GrantScope.ALWAYS, operator="human")
    persist(_authz(), dec)
    persist(_authz(tool="bash", arguments={"command": "git status"}, normalized_pattern="command:git status"), dec)
    persist(_authz(), dec)  # duplicate of the first — must not double-write

    data = json.loads(path.read_text())
    allow_rules = data["permissions"]["rules"]["allow"]
    assert allow_rules.count("command(make build)") == 1
    assert "command(git status)" in allow_rules


def test_persist_preserves_existing_settings(tmp_path):
    path = tmp_path / "settings.local.json"
    path.write_text(json.dumps({"unrelated": {"keep": True}, "permissions": {"role": "implementer"}}))
    persist = make_persist_callback(path)
    persist(_authz(), ApprovalDecision(allowed=True, scope=GrantScope.ALWAYS, operator="human"))

    data = json.loads(path.read_text())
    assert data["unrelated"] == {"keep": True}  # untouched
    assert data["permissions"]["role"] == "implementer"  # preserved
    assert "command(make build)" in data["permissions"]["rules"]["allow"]


def test_persist_skips_when_no_stable_target(tmp_path):
    # A write/read call with no path resolves to an EMPTY target — persisting it
    # would mean `write_file()` (no concrete pattern), so skip instead.
    path = tmp_path / "settings.local.json"
    persist = make_persist_callback(path)
    persist(
        _authz(tool="write_file", arguments={}, normalized_pattern="write_file"),
        ApprovalDecision(allowed=True, scope=GrantScope.ALWAYS, operator="human"),
    )
    # Nothing meaningful to persist → no file, or no allow rules.
    rs = load_persisted_rules(path)
    assert rs is None or rs.is_empty


def test_load_missing_file_returns_none(tmp_path):
    assert load_persisted_rules(tmp_path / "nope.json") is None


def test_load_corrupt_file_returns_none(tmp_path):
    path = tmp_path / "settings.local.json"
    path.write_text("{ not valid json")
    assert load_persisted_rules(path) is None
