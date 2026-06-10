"""Adversarial audit of PathPermissionManager.pre_tool_use_hook — the app-layer
that gates every MCP file tool (and the *only* layer for non-srt-wrapped servers).

Each test below is an attempted SANDBOX ESCAPE via a file tool; the hook MUST deny
it. Vectors: out-of-workspace absolute paths, `..` traversal, symlink-through,
UNRECOGNIZED path-arg keys (fail-open), list-valued paths, and move/copy `source`
pointing outside (delete-external / exfiltrate-external).
"""

import os

import pytest

from massgen.filesystem_manager._base import Permission
from massgen.filesystem_manager._path_permission_manager import PathPermissionManager


@pytest.fixture
def pm(tmp_path):
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    secret = outside / "secret.txt"
    for d in (workspace, outside):
        d.mkdir(parents=True, exist_ok=True)
    secret.write_text("TOP SECRET")
    m = PathPermissionManager(context_write_access_enabled=True)
    m.add_path(workspace, Permission.WRITE, "workspace")
    return {"m": m, "workspace": workspace.resolve(), "outside": outside.resolve(), "secret": secret.resolve()}


async def _denied(m, tool, args):
    allowed, _reason = await m.pre_tool_use_hook(tool, args)
    return not allowed


# --------------------------------------------------------------------------- #
# Baselines that should already hold (resolve() handles these)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_absolute_outside_write_denied(pm):
    assert await _denied(pm["m"], "write_file", {"path": str(pm["outside"] / "evil.txt"), "content": "x"})


@pytest.mark.asyncio
async def test_dotdot_traversal_write_denied(pm):
    evil = str(pm["workspace"] / ".." / "outside" / "evil.txt")
    assert await _denied(pm["m"], "write_file", {"path": evil, "content": "x"})


@pytest.mark.asyncio
async def test_symlink_through_workspace_denied(pm):
    link = pm["workspace"] / "link"
    os.symlink(str(pm["outside"]), str(link))
    assert await _denied(pm["m"], "write_file", {"path": str(link / "evil.txt"), "content": "x"})


# --------------------------------------------------------------------------- #
# The real gaps (these are expected to FAIL pre-hardening = currently ALLOWED)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_unrecognized_path_key_write_denied(pm):
    # path under a key not in the known list → fail-open today.
    assert await _denied(pm["m"], "write_file", {"output_path": str(pm["outside"] / "evil.txt"), "content": "x"})


@pytest.mark.asyncio
async def test_arbitrary_key_absolute_path_write_denied(pm):
    assert await _denied(pm["m"], "store_blob", {"dst": str(pm["outside"] / "evil.txt"), "content": "x"})


@pytest.mark.asyncio
async def test_list_valued_path_write_denied(pm):
    assert await _denied(pm["m"], "write_files", {"paths": [str(pm["outside"] / "evil.txt")], "content": "x"})


@pytest.mark.asyncio
async def test_move_source_outside_denied(pm):
    # move deletes the source — a source outside the sandbox must be denied.
    assert await _denied(pm["m"], "move_file", {"source": str(pm["secret"]), "destination": str(pm["workspace"] / "x")})


@pytest.mark.asyncio
async def test_copy_source_outside_denied(pm):
    # copy reads the source into the workspace — reading an external file is exfiltration.
    assert await _denied(pm["m"], "copy_file", {"source_path": str(pm["secret"]), "destination_path": str(pm["workspace"] / "x")})


# --------------------------------------------------------------------------- #
# Must NOT over-block legitimate in-workspace use (guard against false positives)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_in_workspace_write_allowed(pm):
    allowed, _ = await pm["m"].pre_tool_use_hook("write_file", {"path": str(pm["workspace"] / "ok.txt"), "content": "hi"})
    assert allowed


@pytest.mark.asyncio
async def test_content_with_pathlike_text_not_blocked(pm):
    # 'content' holds text that merely looks like a path — must not be treated as a path.
    allowed, _ = await pm["m"].pre_tool_use_hook(
        "write_file",
        {"path": str(pm["workspace"] / "ok.txt"), "content": "see /etc/passwd for details"},
    )
    assert allowed


@pytest.mark.asyncio
async def test_content_equal_to_absolute_path_not_blocked(pm):
    # The whole content value being an absolute path is still CONTENT (written into a
    # workspace file), not a target — must not be denied.
    allowed, _ = await pm["m"].pre_tool_use_hook(
        "write_file",
        {"path": str(pm["workspace"] / "cfg"), "content": str(pm["secret"])},
    )
    assert allowed


# --------------------------------------------------------------------------- #
# Deeper vectors closed by the review-driven hardening
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_nested_dict_path_escape_denied(pm):
    assert await _denied(pm["m"], "write_file", {"opts": {"path": str(pm["outside"] / "evil.txt")}, "content": "x"})


@pytest.mark.asyncio
async def test_dict_in_list_path_escape_denied(pm):
    assert await _denied(pm["m"], "write_files", {"items": [{"target": str(pm["outside"] / "evil.txt")}]})


@pytest.mark.asyncio
async def test_value_key_escape_denied(pm):
    # 'value' is no longer treated as a content key → a path under it is validated.
    assert await _denied(pm["m"], "store", {"value": str(pm["outside"] / "evil.txt")})


@pytest.mark.asyncio
async def test_read_tool_unrecognized_key_exfil_denied(pm):
    # A read-capable tool with the path under an unrecognized key must not exfiltrate.
    assert await _denied(pm["m"], "fetch_resource", {"location": str(pm["secret"])})
