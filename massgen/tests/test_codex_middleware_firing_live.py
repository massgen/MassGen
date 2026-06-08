"""Targeted live test: force the Codex MCP-injection MIDDLEWARE to fire.

Earlier we proved (a) Codex native hooks don't fire in `codex exec`, and (b) the
in-process HumanInputHook path delivers steering for in-process backends. For
Codex specifically, mid-stream injection rides a different path: the orchestrator
flushes pending input to ``.codex/hook_post_tool_use.json`` and the FastMCP
``MassGenHookMiddleware`` (attached to Codex's MassGen MCP servers) appends it to
the next MCP tool result. A normal run rarely aligns the timing (30s TTL), so we
never observed it fire.

This test uses the programmatic steering lever to CONTROL the timing: run a
single Codex agent (which calls planning MCP tools throughout), then repeatedly
drop a steering message while it streams. The orchestrator polls the inbox inside
``_flush_codex_hook_payloads`` (orchestrator.py:3564), writes the hook file, and
Codex's next MCP tool call triggers the middleware.

Detection: the middleware logs ``Hook middleware injected N chars into '<tool>'``
from inside the MCP server subprocess, captured in ``mcp_*_stderr.log``.

Marked live_api + expensive (real Codex calls).

Run with:
    uv run pytest massgen/tests/test_codex_middleware_firing_live.py \
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


def _massgen_bin() -> str:
    """Resolve the REPO's massgen (venv), not a global ~/.local/bin install.

    Under `uv run pytest`, the console script sits next to sys.executable. Fall
    back to PATH only if that's missing.
    """
    candidate = Path(sys.executable).parent / "massgen"
    if candidate.exists():
        return str(candidate)
    return shutil.which("massgen") or "massgen"


# Config tuned so the middleware has a real MCP call to ride: code-based tools
# OFF (tools are MCP-protocol calls, not CodeAct scripts) + MCP-mode planning.
_CONFIG = "massgen/configs/debug/codex_mcp_middleware_test.yaml"
_SENTINEL = "MW-FIRE-SENTINEL-9Q"


def _skip_if_unavailable() -> None:
    if not shutil.which("massgen"):
        pytest.skip("massgen console script not on PATH")
    if not (shutil.which("codex") and (Path.home() / ".codex" / "auth.json").exists()):
        pytest.skip("codex not logged in (~/.codex/auth.json missing)")
    if not Path(_CONFIG).exists():
        pytest.skip(f"config not found: {_CONFIG}")


def _injection_reached_codex(massgen_log: Path, sentinel: str) -> bool:
    """Reliable detection: did the steered sentinel actually reach Codex?

    The middleware's own logger isn't reliably captured in the MCP subprocess
    stderr, so we check for the *effect* instead: if the middleware injected the
    payload into a tool result, the sentinel shows up in Codex's stream (a tool
    result / codex item), NOT only in the orchestrator's own bookkeeping
    (Injecting/QUEUED/Wrote hook).
    """
    if not massgen_log.exists():
        return False
    bookkeeping = ("Injecting runtime inbox", "QUEUED message", "Wrote hook_post_tool_use")
    for line in massgen_log.read_text(errors="ignore").splitlines():
        if sentinel in line and not any(b in line for b in bookkeeping):
            return True
    return False


@pytest.mark.integration
@pytest.mark.live_api
@pytest.mark.expensive
@pytest.mark.xfail(
    reason="The Codex MCP-injection middleware did not deliver in a live Codex run "
    "(verified 2026-06-07): Codex called a middleware-attached planning server 20x "
    "with valid fresh payloads in the correct hook_dir, yet the steered content "
    "never reached Codex. NOTE the middleware itself is proven to work both "
    "in-memory and via the real `fastmcp run <module>:create_server` STDIO "
    "deployment (see test_mcp_hook_middleware.TestRealFastMCPInvocation and "
    "TestStdioDeploymentInvocation, both passing). So the remaining gap is "
    "Codex-MCP-client / per-server-wiring specific, not the middleware or the "
    "transport. Codex mid-stream injection currently relies on round-end "
    "carryforward + round-start system-message injection. XPASS => the live gap is "
    "closed.",
    strict=False,
)
def test_codex_mcp_middleware_injects_steering(tmp_path):
    _skip_if_unavailable()

    inbox = tmp_path / "inbox"
    repo_root = Path(__file__).resolve().parents[2]
    massgen_bin = _massgen_bin()

    proc = subprocess.Popen(
        [
            massgen_bin,
            "--automation",
            "--inbox-dir",
            str(inbox),
            "--config",
            _CONFIG,
            "Make a task plan, then write a Python function add(a, b) to add.py, " "then update your plan status, then write a test in test_add.py.",
        ],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    set_nonblocking(proc.stdout)

    fired = False
    log_root: Path | None = None
    try:
        deadline = time.time() + 420
        captured = ""
        # Discover LOG_DIR.
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

        # Wait until Codex is streaming (so an inbox poll / flush can happen),
        # then start steering — early, so a payload is pending before/while Codex
        # makes its MCP planning calls.
        while time.time() < deadline:
            if massgen_log.exists() and re.search(r"Stream chunk|Running Codex|Calling ", massgen_log.read_text(errors="ignore")):
                break
            if proc.poll() is not None:
                break
            time.sleep(2)

        # Repeatedly drop the steering message while Codex streams, to align with
        # a middleware-equipped MCP tool call inside the 30s TTL. Stop as soon as
        # the middleware logs an injection.
        while time.time() < deadline:
            send_steering_message(inbox, f"{_SENTINEL}", target_agents=["agent_a"])
            for _ in range(2):
                if _injection_reached_codex(massgen_log, _SENTINEL):
                    fired = True
                    break
                if proc.poll() is not None:
                    break
                time.sleep(2)
            if fired or proc.poll() is not None:
                break
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    assert fired, (
        "Codex MCP middleware never logged an injection. Mid-stream injection via "
        "the middleware did not fire even with controlled steering timing — the "
        "middleware may not deliver in practice for Codex."
    )
