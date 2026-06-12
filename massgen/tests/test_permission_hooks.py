"""Tests for the permission PreToolUse hooks (hardline + engine)."""

import json

import pytest

from massgen.permissions.hooks import (
    HardlineBlocklistHook,
    PermissionEngineHook,
    normalize_pattern,
)


def _args(**kw) -> str:
    return json.dumps(kw)


@pytest.mark.asyncio
async def test_hardline_blocks_catastrophic():
    h = HardlineBlocklistHook()
    assert (await h.execute("execute_command", _args(command="rm -rf /"))).decision == "deny"
    assert (await h.execute("execute_command", _args(command="ls -la"))).decision == "allow"


@pytest.mark.asyncio
async def test_engine_low_risk_allows():
    h = PermissionEngineHook()
    r = await h.execute("execute_command", _args(command="git status"))
    assert r.decision == "allow"


@pytest.mark.asyncio
async def test_engine_high_and_medium_ask():
    h = PermissionEngineHook()
    assert (await h.execute("execute_command", _args(command="git push --force"))).decision == "ask"
    assert (await h.execute("execute_command", _args(command="python build.py"))).decision == "ask"


@pytest.mark.asyncio
async def test_engine_read_tool_allows():
    h = PermissionEngineHook()
    assert (await h.execute("read_file", _args(path="a.txt"))).decision == "allow"


def test_normalize_pattern():
    assert normalize_pattern("execute_command", {"command": "git status"}) == "command:git status"
    assert normalize_pattern("write_file", {"path": "out.txt"}) == "write_file:out.txt"
    assert normalize_pattern("Foo", {}) == "Foo"


# --------------------------------------------------------------------------- #
# Engine + declarative rules (rules override risk; deny-wins)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_allow_rule_suppresses_risk_ask():
    from massgen.permissions.rules import PermissionRuleSet

    # git push --force is HIGH risk → would ask, but an explicit allow rule wins.
    rules = PermissionRuleSet(allow=["command(git push --force*)"])
    h = PermissionEngineHook(rules=rules)
    assert (await h.execute("execute_command", _args(command="git push --force origin main"))).decision == "allow"


@pytest.mark.asyncio
async def test_deny_rule_wins():
    from massgen.permissions.rules import PermissionRuleSet

    rules = PermissionRuleSet(deny=["command(rm *)"], allow=["command(*)"])
    h = PermissionEngineHook(rules=rules)
    assert (await h.execute("execute_command", _args(command="rm file.txt"))).decision == "deny"


@pytest.mark.asyncio
async def test_no_rule_falls_through_to_risk():
    from massgen.permissions.rules import PermissionRuleSet

    rules = PermissionRuleSet(allow=["command(git status)"])  # doesn't match curl
    h = PermissionEngineHook(rules=rules)
    # curl egress is HIGH risk and no rule matches → ask
    assert (await h.execute("execute_command", _args(command="curl https://x"))).decision == "ask"
