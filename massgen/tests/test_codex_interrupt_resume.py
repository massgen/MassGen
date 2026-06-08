"""Deterministic tests for Codex mid-round interrupt-and-resume steering.

The end-to-end behavior (kill mid-turn + `codex exec resume` delivers steering)
is covered by the live test; these pin the cheap, deterministic pieces.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from massgen.backend.codex import CodexBackend


def _make_backend(tmp_path: Path, **kw):
    with patch.object(CodexBackend, "_find_codex_cli", return_value="/usr/bin/codex"):
        return CodexBackend(api_key="test-key", cwd=str(tmp_path), **kw)


def test_supports_interrupt_resume_default_true(tmp_path):
    assert _make_backend(tmp_path).supports_interrupt_resume() is True


def test_supports_interrupt_resume_can_be_disabled(tmp_path):
    assert _make_backend(tmp_path, enable_interrupt_resume=False).supports_interrupt_resume() is False


def test_config_knobs(tmp_path):
    b = _make_backend(tmp_path, interrupt_poll_seconds=0.5, max_interrupts_per_turn=3)
    assert b._interrupt_poll_seconds == 0.5
    assert b._max_interrupts_per_turn == 3


@pytest.mark.asyncio
async def test_terminate_proc_kills_real_subprocess(tmp_path):
    proc = await asyncio.create_subprocess_exec("sleep", "30")
    assert proc.returncode is None
    await CodexBackend._terminate_proc(proc, grace=2.0)
    assert proc.returncode is not None


def test_resume_command_uses_session_id_and_prompt(tmp_path):
    """The resume path the watcher triggers builds `codex exec resume <id> <prompt>`."""
    b = _make_backend(tmp_path)
    b.session_id = "sess-123"
    cmd = b._build_exec_command("steer me", resume_session=True)
    assert "resume" in cmd
    assert "sess-123" in cmd
    assert "steer me" in cmd


def _write_hook(tmp_path: Path, payload: dict) -> Path:
    hook_dir = tmp_path / ".codex"
    hook_dir.mkdir(parents=True, exist_ok=True)
    hook_file = hook_dir / "hook_post_tool_use.json"
    hook_file.write_text(json.dumps(payload))
    return hook_file


def test_read_unconsumed_drops_expired_payload(tmp_path):
    # Parity with antigravity: a stale carryforward must not resurrect old steering.
    b = _make_backend(tmp_path)
    hook_file = _write_hook(tmp_path, {"inject": {"content": "stale"}, "expires_at": 1.0})
    assert b.read_unconsumed_hook_content() is None
    assert not hook_file.exists()


def test_read_unconsumed_returns_fresh_payload(tmp_path):
    b = _make_backend(tmp_path)
    _write_hook(tmp_path, {"inject": {"content": "fresh"}, "expires_at": time.time() + 3600})
    assert b.read_unconsumed_hook_content() == "fresh"


def test_read_unconsumed_tolerates_bad_expires_at(tmp_path):
    b = _make_backend(tmp_path)
    _write_hook(tmp_path, {"inject": {"content": "keep"}, "expires_at": "nan-ish"})
    assert b.read_unconsumed_hook_content() == "keep"
