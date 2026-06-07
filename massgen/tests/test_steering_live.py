"""Live end-to-end test: programmatic steering reaches a running agent.

Proves the full path in a REAL `--automation` run (no UI):

    massgen --automation --inbox-dir <dir>   (prints RUNTIME_INBOX: <dir>)
      -> send_steering_message(dir, "<sentinel>")
        -> RuntimeInboxPoller picks it up on the next tool use
          -> HumanInputHook injects "[Human Input]: <sentinel>" into the agent's
             next tool result (a `hook_execution` stream chunk in the log)

This is the regression guard for the steering feature. It uses a multi-agent
config that reliably makes tool calls (so the PostToolUse injection boundary is
hit). Marked live_api + expensive: it makes real model calls.

Run with:
    uv run pytest massgen/tests/test_steering_live.py \
        --run-integration --run-live-api --run-expensive -v
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from massgen.steering import send_steering_message

# Multi-agent config that exercises tool calls (gemini + codex). Override via env
# if you want a cheaper/other config; it must produce mid-run tool calls.
_CONFIG = os.environ.get(
    "MASSGEN_STEERING_TEST_CONFIG",
    "massgen/configs/features/fast_iteration.yaml",
)
_SENTINEL = "STEER-LIVE-SENTINEL-7C3"


def _skip_if_unavailable() -> None:
    if not shutil.which("massgen"):
        pytest.skip("massgen console script not on PATH")
    if not Path(_CONFIG).exists():
        pytest.skip(f"config not found: {_CONFIG}")
    if not (shutil.which("codex") and (Path.home() / ".codex" / "auth.json").exists()):
        # fast_iteration needs codex; skip if it isn't logged in.
        if "fast_iteration" in _CONFIG:
            pytest.skip("codex not available for fast_iteration config")


@pytest.mark.integration
@pytest.mark.live_api
@pytest.mark.expensive
def test_programmatic_steering_delivered_in_automation(tmp_path):
    _skip_if_unavailable()

    inbox = tmp_path / "inbox"
    repo_root = Path(__file__).resolve().parents[2]

    massgen_bin = shutil.which("massgen") or "massgen"
    proc = subprocess.Popen(
        [
            massgen_bin,
            "--automation",
            "--inbox-dir",
            str(inbox),
            "--config",
            _CONFIG,
            "Write a short poem about the ocean, then refine it.",
        ],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    delivered = False
    dropped = False
    log_path: Path | None = None
    try:
        deadline = time.time() + 420  # generous: model startup + a round
        captured = ""
        # 1) Read startup output to discover LOG_DIR / confirm RUNTIME_INBOX.
        while time.time() < deadline and log_path is None:
            line = proc.stdout.readline() if proc.stdout else ""
            if not line:
                if proc.poll() is not None:
                    break
                continue
            captured += line
            m = re.search(r"LOG_DIR:\s*(\S+)", line)
            if m:
                log_path = Path(m.group(1)) / "turn_1" / "attempt_1" / "massgen.log"
            assert "RUNTIME_INBOX:" not in line or str(inbox) in line

        assert log_path is not None, f"never saw LOG_DIR in output:\n{captured[-1500:]}"

        # 2) Wait until an agent is actively streaming (tool activity), then drop
        #    the steering message so it lands mid-stream.
        while time.time() < deadline:
            if log_path.exists() and re.search(r"Stream chunk|mcp_status|Calling ", log_path.read_text(errors="ignore")):
                break
            if proc.poll() is not None:
                break
            time.sleep(2)

        send_steering_message(inbox, f"{_SENTINEL}: prioritize a haiku.")
        dropped = True

        # 3) Wait for the injection to show up in the agent's stream.
        while time.time() < deadline:
            if log_path.exists():
                text = log_path.read_text(errors="ignore")
                if _SENTINEL in text and "human_input_hook" in text:
                    delivered = True
                    break
            if proc.poll() is not None:
                # process ended; do a final check
                if log_path.exists() and _SENTINEL in log_path.read_text(errors="ignore"):
                    delivered = True
                break
            time.sleep(3)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    assert dropped, "test never reached the message-drop step (run didn't start streaming)"
    assert delivered, f"steering sentinel '{_SENTINEL}' was not injected into the run's stream. " "Programmatic steering did not deliver end-to-end."
