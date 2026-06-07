"""Live end-to-end test: Codex mid-round interrupt-and-resume steering.

Proves steering reaches a running Codex agent at ANY point in a long round (not
just when an MCP tool happens to be called): we run a single Codex agent on a
slow task, drop a steering message with a *verifiable* instruction (create a
sentinel file), and assert (a) the backend interrupted + resumed the session,
and (b) Codex actually acted on the steering (the file appears).

This is the reliable mid-round delivery path for CLI backends — `codex exec
resume <session_id>` preserves full context across the kill. Marked
live_api + expensive (real Codex calls).

Run with:
    uv run pytest massgen/tests/test_codex_interrupt_resume_live.py \
        --run-integration --run-live-api --run-expensive -v
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from massgen.steering import send_steering_message

_CONFIG = "massgen/configs/debug/codex_mcp_middleware_test.yaml"
_SENTINEL_FILE = "STEERED_OK.txt"


def _massgen_bin() -> str:
    candidate = Path(sys.executable).parent / "massgen"
    return str(candidate) if candidate.exists() else (shutil.which("massgen") or "massgen")


def _skip_if_unavailable() -> None:
    if not (Path(sys.executable).parent / "massgen").exists() and not shutil.which("massgen"):
        pytest.skip("massgen console script not found")
    if not (shutil.which("codex") and (Path.home() / ".codex" / "auth.json").exists()):
        pytest.skip("codex not logged in")
    if not Path(_CONFIG).exists():
        pytest.skip(f"config not found: {_CONFIG}")


@pytest.mark.integration
@pytest.mark.live_api
@pytest.mark.expensive
def test_codex_interrupt_resume_delivers_steering(tmp_path):
    _skip_if_unavailable()

    inbox = tmp_path / "inbox"
    repo_root = Path(__file__).resolve().parents[2]

    proc = subprocess.Popen(
        [
            _massgen_bin(),
            "--automation",
            "--inbox-dir",
            str(inbox),
            "--config",
            _CONFIG,
            "Write a detailed five-paragraph essay about the ocean to ocean.txt. Take your time.",
        ],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    interrupted = False
    steered_file_created = False
    try:
        deadline = time.time() + 420
        log_root: Path | None = None
        captured = ""
        while time.time() < deadline and log_root is None:
            line = proc.stdout.readline() if proc.stdout else ""
            if not line:
                if proc.poll() is not None:
                    break
                continue
            captured += line
            m = re.search(r"LOG_DIR:\s*(\S+)", line)
            if m:
                log_root = Path(m.group(1))
        assert log_root is not None, f"never saw LOG_DIR:\n{captured[-1500:]}"
        massgen_log = log_root / "turn_1" / "attempt_1" / "massgen.log"

        # Wait until Codex has a session id (so resume is possible), then steer.
        while time.time() < deadline:
            if massgen_log.exists() and "Codex session started" in massgen_log.read_text(errors="ignore"):
                break
            if proc.poll() is not None:
                break
            time.sleep(2)

        send_steering_message(
            inbox,
            f"URGENT NEW INSTRUCTION: immediately create a file named {_SENTINEL_FILE} containing exactly the word YES, then continue.",
            target_agents=["agent_a"],
        )

        # Confirm (a) the backend interrupted+resumed and (b) Codex acted on it.
        while time.time() < deadline:
            text = massgen_log.read_text(errors="ignore") if massgen_log.exists() else ""
            if "interrupt #" in text and "resuming session" in text:
                interrupted = True
            if any(p.name == _SENTINEL_FILE for p in (repo_root / ".massgen" / "workspaces").rglob(_SENTINEL_FILE)):
                steered_file_created = True
            if interrupted and steered_file_created:
                break
            if proc.poll() is not None:
                # final sweep
                if "interrupt #" in text:
                    interrupted = True
                break
            time.sleep(3)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    assert interrupted, "backend did not interrupt + resume the Codex session on steering"
    assert steered_file_created, f"Codex did not act on the steering ({_SENTINEL_FILE} never created)"
