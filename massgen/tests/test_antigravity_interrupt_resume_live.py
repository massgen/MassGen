"""Live end-to-end test: agy (Antigravity CLI) mid-round interrupt-and-resume steering.

Single agy agent on a slow task; drop a steering message with a verifiable
instruction (create a sentinel file) mid-run; assert (a) the backend interrupted
+ resumed the session (`agy --continue`), and (b) agy acted on the steering.

Marked live_api + expensive (real agy / Antigravity quota).

Run with:
    uv run pytest massgen/tests/test_antigravity_interrupt_resume_live.py \
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

from ._live_proc_io import read_line_nonblocking, set_nonblocking

_CONFIG = "massgen/configs/features/fast_iteration_gemini_antigravity.yaml"
_SENTINEL_FILE = "STEERED_AGY.txt"


def _massgen_bin() -> str:
    candidate = Path(sys.executable).parent / "massgen"
    return str(candidate) if candidate.exists() else (shutil.which("massgen") or "massgen")


def _skip_if_unavailable() -> None:
    if not (Path(sys.executable).parent / "massgen").exists() and not shutil.which("massgen"):
        pytest.skip("massgen console script not found")
    if not shutil.which("agy"):
        pytest.skip("agy CLI not installed")
    if not ((Path.home() / ".gemini" / "google_accounts.json").exists() or (Path.home() / ".gemini" / "oauth_creds.json").exists()):
        pytest.skip("agy not authenticated (~/.gemini/ login missing)")
    if not Path(_CONFIG).exists():
        pytest.skip(f"config not found: {_CONFIG}")


@pytest.mark.integration
@pytest.mark.live_api
@pytest.mark.expensive
def test_agy_interrupt_resume_delivers_steering(tmp_path):
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
            "Write a detailed five-paragraph essay about mountains to mountains.txt. Take your time.",
        ],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    set_nonblocking(proc.stdout)

    interrupted = False
    steered_file_created = False
    try:
        deadline = time.time() + 480
        log_root: Path | None = None
        captured = ""
        while time.time() < deadline and log_root is None:
            line = read_line_nonblocking(proc.stdout)
            if not line:
                if proc.poll() is not None:
                    break
                time.sleep(0.1)  # non-blocking read returned nothing yet
                continue
            captured += line
            m = re.search(r"LOG_DIR:\s*(\S+)", line)
            if m:
                log_root = Path(m.group(1))
        assert log_root is not None, f"never saw LOG_DIR:\n{captured[-1500:]}"
        massgen_log = log_root / "turn_1" / "attempt_1" / "massgen.log"

        # Wait until agy is streaming, then steer.
        while time.time() < deadline:
            if massgen_log.exists() and "Running Antigravity" in massgen_log.read_text(errors="ignore"):
                break
            if proc.poll() is not None:
                break
            time.sleep(2)

        send_steering_message(
            inbox,
            f"URGENT NEW INSTRUCTION: immediately create a file named {_SENTINEL_FILE} containing exactly the word YES, then continue.",
            target_agents=["agent_b"],
        )

        ws_dir = repo_root / ".massgen" / "workspaces"
        while time.time() < deadline:
            text = massgen_log.read_text(errors="ignore") if massgen_log.exists() else ""
            if "interrupt #" in text and "resuming session" in text:
                interrupted = True
            if any(p.name == _SENTINEL_FILE for p in ws_dir.rglob(_SENTINEL_FILE)):
                steered_file_created = True
            if interrupted and steered_file_created:
                break
            if proc.poll() is not None:
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

    assert interrupted, "backend did not interrupt + resume the agy session on steering"
    assert steered_file_created, f"agy did not act on the steering ({_SENTINEL_FILE} never created)"
