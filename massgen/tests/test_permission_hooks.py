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
