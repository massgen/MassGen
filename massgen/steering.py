"""Programmatic steering for MassGen runs.

"Steering" is mid-stream human input to a running agent — the same thing a user
does by typing into the TUI or WebUI. Under the hood every steering path funnels
into ``HumanInputHook.set_pending_input`` and is delivered on the agent's next
tool result. A running orchestrator also polls a **file inbox**
(``RuntimeInboxPoller``) that feeds the exact same chokepoint, so steering can be
driven without any UI: drop a ``msg_*.json`` into the inbox dir.

This module is the small, documented writer for that inbox — so scripts and
tests don't hand-roll the JSON + atomic-write dance.

Targeting mirrors the UI: ``target_agents=None`` broadcasts to all agents; a list
targets one agent or a subset.

Discovering the inbox dir:
- Run MassGen with ``--inbox-dir <path>`` (or set ``MASSGEN_RUNTIME_INBOX_DIR``).
  In ``--automation`` mode the path is echoed as ``RUNTIME_INBOX: <path>``.
- Then call :func:`send_steering_message` with that path while the run is live.

Example::

    from massgen.steering import send_steering_message
    send_steering_message("/tmp/run/inbox", "Focus on the error-handling path.")
    send_steering_message(inbox, "agent_b: add tests", target_agents=["agent_b"])
"""

from __future__ import annotations

import itertools
import json
import os
import time
from pathlib import Path

# Process-local monotonic counter so many messages in the same second still get
# unique filenames (mirrors SubagentManager.send_message_to_subagent).
_seq = itertools.count()

# Env var honored by the orchestrator's inbox-poller resolver
# (runtime_input_delivery.ensure_runtime_inbox_poller_initialized) and set by the
# ``--inbox-dir`` CLI flag.
INBOX_DIR_ENV = "MASSGEN_RUNTIME_INBOX_DIR"


def send_steering_message(
    inbox_dir: str | os.PathLike[str],
    content: str,
    target_agents: list[str] | None = None,
    source: str = "programmatic",
) -> Path:
    """Drop a steering message into a run's runtime inbox.

    The orchestrator's ``RuntimeInboxPoller`` picks it up on the next tool use
    and routes it through ``set_pending_input`` for mid-stream injection into the
    targeted agent(s).

    Args:
        inbox_dir: The run's runtime-inbox directory (from ``RUNTIME_INBOX:`` /
            ``--inbox-dir`` / ``MASSGEN_RUNTIME_INBOX_DIR``).
        content: The steering text to inject.
        target_agents: ``None`` broadcasts to all agents; a list targets one
            agent or a subset (by agent id).
        source: Label shown in injection context (e.g. ``programmatic``).

    Returns:
        The path of the written message file.
    """
    if not content or not content.strip():
        raise ValueError("steering content must be a non-empty string")

    inbox = Path(inbox_dir).expanduser()
    inbox.mkdir(parents=True, exist_ok=True)

    payload: dict[str, object] = {"content": content, "source": source}
    if target_agents is not None:
        payload["target_agents"] = list(target_agents)

    # Unique, sortable filename. Poller globs ``msg_*.json`` in sorted order.
    name = f"msg_{int(time.time() * 1000):013d}_{os.getpid()}_{next(_seq):04d}.json"
    dest = inbox / name
    tmp = dest.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, dest)  # atomic: poller never sees a half-written file
    return dest
