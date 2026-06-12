"""Hardline command blocklist — catastrophic patterns denied unconditionally.

This is the safety FLOOR: it must hold even under an `allow(*)` rule, automation
`allow-all`, or any bypass mode. Kept as an immutable module constant so config can
never loosen it (inspired by Hermes' non-overridable blocklist and Claude Code's
`rm -rf /` circuit breaker). Distinct from the *risk classifier* (which tiers
normal-but-notable actions) — this only fires on truly destructive operations.
"""

from __future__ import annotations

import re
from typing import Any

# Catastrophic patterns. Intentionally narrow: a normal `rm file.txt` is NOT here
# (that's the risk/rules layer's job) — only operations that can destroy the host
# or the disk.
_HARDLINE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\brm\s+(-[a-zA-Z]*\s+)*-?[a-zA-Z]*[rf]+[a-zA-Z]*\s+/(?:\s|$|\*)"), "Recursive delete of '/' is never allowed"),
    (re.compile(r"\brm\s+-rf\s+/"), "Recursive force-delete of '/' is never allowed"),
    (re.compile(r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:?\s*&\s*\}\s*;\s*:"), "Fork bombs are never allowed"),
    (re.compile(r"\bdd\b.*\bof=/dev/(?:sd|nvme|disk|hd)"), "Writing raw disk devices with dd is never allowed"),
    (re.compile(r"\bmkfs(\.\w+)?\b"), "Formatting a filesystem is never allowed"),
    (re.compile(r">\s*/dev/(?:sd|nvme|disk|hd)[a-z]?[0-9]*"), "Overwriting raw disk blocks is never allowed"),
    (re.compile(r"\bmv\b.+\s+/dev/null\b"), "Moving files into /dev/null is never allowed"),
)

# Args that may carry a shell command, by common tool-arg key.
_COMMAND_KEYS = ("command", "cmd", "script", "code")


def _command_text(arguments: dict[str, Any]) -> str:
    for key in _COMMAND_KEYS:
        v = arguments.get(key)
        if isinstance(v, str) and v:
            return v
    return ""


def is_hardline_blocked(tool: str, arguments: dict[str, Any]) -> tuple[bool, str | None]:
    """Return (blocked, reason). Blocks only catastrophic command patterns."""
    command = _command_text(arguments)
    if not command:
        return (False, None)
    for pattern, reason in _HARDLINE_PATTERNS:
        if pattern.search(command):
            return (True, f"Hardline block: {reason}")
    return (False, None)
