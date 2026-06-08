"""Live-fire test: does the Codex CLI actually FIRE native hooks in `codex exec`?

Background
----------
MassGen's Codex backend delivers mid-stream injection (peer answers, etc.) via
an in-process FastMCP middleware (``MassGenHookMiddleware``) plus a round-end
carryforward — NOT via Codex's native ``hooks.json``. Codex 0.124+ gained a full
Claude-Code-style hook system (PreToolUse/PostToolUse/SessionStart/...), which
raised the question: are native hooks now enough to replace the middleware?

This test answers it empirically. It runs the real ``codex`` binary in
non-interactive ``codex exec`` mode (exactly how MassGen invokes Codex) with a
sentinel hook that writes a file when executed, and checks whether Codex actually
runs the hook during a tool call.

Finding (codex-cli 0.134, 2026-06-07)
-------------------------------------
Codex *parses* the hooks (the ``--dangerously-bypass-hook-trust`` warning fires
and config validates), but NEITHER ``SessionStart`` NOR ``PostToolUse`` hooks are
dispatched in ``codex exec``. The hook engine appears wired into the interactive
TUI / app-server path (``codex-rs/tui/src/hooks_rpc.rs``), not the headless exec
path. Hooks are auto-discovered from ``$CODEX_HOME/hooks.json`` /
``<repo>/.codex/hooks.json`` and enabled by default, so this is a dispatch-mode
limitation, not a config problem.

Consequence: the MCP-server middleware is **not** redundant — it is the only
injection channel that works headlessly. This test asserts the *desired*
behavior (the hook fires) and is ``xfail``-marked with that limitation, so it
flips to XPASS and alerts us if a future Codex dispatches hooks in exec mode — at
which point native hooks could replace the middleware.

Run with:
    uv run pytest massgen/tests/test_codex_hook_firing_live.py \
        --run-integration --run-live-api -v
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def _skip_if_no_codex() -> None:
    if not shutil.which("codex"):
        pytest.skip("codex binary not found on PATH")
    if not (Path.home() / ".codex" / "auth.json").exists():
        pytest.skip("~/.codex/auth.json not found (codex not logged in)")


_SENTINEL_HOOK = """\
#!/usr/bin/env python3
import sys, json, time, pathlib
raw = sys.stdin.read()
try:
    data = json.loads(raw) if raw.strip() else {}
except Exception:
    data = {}
event = sys.argv[sys.argv.index("--event") + 1] if "--event" in sys.argv else "?"
tool = data.get("tool_name") or data.get("toolName") or "?"
sentinel = pathlib.Path(sys.argv[sys.argv.index("--sentinel") + 1])
with sentinel.open("a") as f:
    f.write(f"FIRED event={event} tool={tool} ts={time.time():.0f}\\n")
sys.stdout.write("{}")
sys.stdout.flush()
"""


def _run_codex_hook_probe(tmp_path: Path) -> dict:
    """Run `codex exec` with a sentinel hook; report what (if anything) fired.

    Returns a dict: {"fired": set[str], "saw_hooks": bool, "ran_tool": bool,
    "output": str}.
    """
    codex_home = tmp_path / ".codex"
    codex_home.mkdir(parents=True, exist_ok=True)
    # Copy real auth so the exec call can authenticate.
    shutil.copy2(Path.home() / ".codex" / "auth.json", codex_home / "auth.json")

    sentinel = tmp_path / "sentinel.log"
    hook_script = codex_home / "sentinel_hook.py"
    hook_script.write_text(_SENTINEL_HOOK, encoding="utf-8")

    py = sys.executable or "python3"

    def cmd_for(event: str) -> str:
        # shlex-safe enough: no spaces in our paths inside tmp_path on CI/macOS.
        return f"{py} {hook_script} --event {event} --sentinel {sentinel}"

    # Inline [hooks] TOML (the documented format). SessionStart needs no matcher;
    # PostToolUse matches every tool. If EITHER fires, the engine ran in exec.
    config = f"""\
approval_policy = "never"

[[hooks.SessionStart]]
[[hooks.SessionStart.hooks]]
type = "command"
command = "{cmd_for('SessionStart')}"
timeout = 15

[[hooks.PreToolUse]]
matcher = ".*"
[[hooks.PreToolUse.hooks]]
type = "command"
command = "{cmd_for('PreToolUse')}"
timeout = 15

[[hooks.PostToolUse]]
matcher = ".*"
[[hooks.PostToolUse.hooks]]
type = "command"
command = "{cmd_for('PostToolUse')}"
timeout = 15
"""
    (codex_home / "config.toml").write_text(config, encoding="utf-8")

    env = dict(os.environ)
    env["CODEX_HOME"] = str(codex_home)
    env["NO_COLOR"] = "1"

    proc = subprocess.run(
        [
            "codex",
            "exec",
            "--sandbox",
            "danger-full-access",
            "--skip-git-repo-check",
            "--dangerously-bypass-hook-trust",
            "-C",
            str(tmp_path),
            "Run the shell command: echo hello-from-codex and show me the output.",
        ],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    output = (proc.stdout or "") + (proc.stderr or "")

    fired: set[str] = set()
    if sentinel.exists():
        for line in sentinel.read_text(encoding="utf-8").splitlines():
            if line.startswith("FIRED event="):
                fired.add(line.split("event=", 1)[1].split()[0])

    return {
        "fired": fired,
        # Codex emits this warning only when it has parsed enabled hooks — proves
        # the harness config is valid and the probe is meaningful.
        "saw_hooks": "bypass-hook-trust" in output.lower() or "hook" in output.lower(),
        "ran_tool": "hello-from-codex" in output,
        "output": output,
    }


@pytest.mark.integration
@pytest.mark.live_api
@pytest.mark.expensive
def test_codex_parses_and_runs_tool_with_hooks_configured(tmp_path):
    """Sanity: with hooks configured, codex still runs the tool and sees the hooks.

    This guards the probe itself — if codex stopped accepting our hook config or
    the tool stopped running, the xfail test below would be meaningless.
    """
    _skip_if_no_codex()
    result = _run_codex_hook_probe(tmp_path)
    assert result["ran_tool"], f"codex did not run the shell tool; output:\n{result['output'][-2000:]}"
    assert result["saw_hooks"], "codex gave no sign it parsed the configured hooks (probe may be invalid)"


@pytest.mark.integration
@pytest.mark.live_api
@pytest.mark.expensive
@pytest.mark.xfail(
    reason="codex-cli 0.134 does not dispatch hooks in non-interactive `codex exec` "
    "mode (verified 2026-06-07). Hooks parse but neither SessionStart nor "
    "PostToolUse fire. If this XPASSes, codex now fires hooks headlessly and the "
    "Codex MCP-injection middleware could be replaced by native hooks.json.",
    strict=False,
)
def test_codex_native_hooks_fire_in_exec_mode(tmp_path):
    """DESIRED behavior: a native Codex hook executes during a real tool call.

    Currently xfails because `codex exec` doesn't dispatch hooks. The day it
    does, this XPASSes — our signal that native hooks are viable and the
    in-process MCP middleware (``MassGenHookMiddleware``) is no longer required.
    """
    _skip_if_no_codex()
    result = _run_codex_hook_probe(tmp_path)
    assert result["fired"], (
        "No native Codex hook fired during `codex exec` " f"(saw_hooks={result['saw_hooks']}, ran_tool={result['ran_tool']}). " "Native hooks remain unusable headlessly; keep the MCP middleware."
    )
