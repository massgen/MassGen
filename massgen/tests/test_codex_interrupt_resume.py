"""Deterministic tests for Codex mid-round interrupt-and-resume steering.

The end-to-end behavior (kill mid-turn + `codex exec resume` delivers steering)
is covered by the live test; these pin the cheap, deterministic pieces.
"""

from __future__ import annotations

import asyncio
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
