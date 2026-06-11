"""RiskClassifier — tier a tool call by BLAST RADIUS, not by tool name.

The single biggest anti-fatigue lever from the research: auto-allow reads/edits
inside the workspace; require approval only for the dangerous tail (force-push,
mass delete, network egress, publish/spend, privilege escalation). The path
*boundary* (out-of-workspace) is enforced separately by PathPermissionManager;
this classifier tiers calls that already pass the boundary.

This is the DETERMINISTIC floor (security pattern lists, like the existing
``_sanitize_command`` danger patterns — a denylist, not content categorization).
An optional LLM-judge can compose on top by max-severity (see plan P0.2).
"""

from __future__ import annotations

import re
from typing import Any

from .models import RiskTier

_COMMAND_TOOL_HINTS = ("bash", "shell", "exec", "execute_command", "run_command", "terminal")
_NETWORK_TOOL_HINTS = ("fetch", "read_url", "websearch", "web_search", "browse", "http", "curl_")
_READ_TOOL_HINTS = ("read", "grep", "glob", "list", "cat_", "view", "search")
_WRITE_TOOL_HINTS = ("write", "edit", "create", "move", "copy", "apply_patch", "notebook")

# Commands that are clearly dangerous / irreversible / privileged → HIGH.
_HIGH_COMMAND = (
    re.compile(r"\bsudo\b|\bsu\b"),
    re.compile(r"\bgit\s+push\b.*--force|\bgit\s+push\s+-f\b|--force-with-lease"),
    re.compile(r"\bgit\s+(reset\s+--hard|clean\s+-[a-z]*f)"),
    re.compile(r"\bnpm\s+publish\b|\byarn\s+publish\b|\bpip\s+.*\bupload\b|\btwine\s+upload\b|\bgh\s+release\s+create\b|\bdocker\s+push\b"),
    re.compile(r"\bchmod\b|\bchown\b"),
    re.compile(r"\bdd\b|\bmkfs|\bfdisk\b"),
    re.compile(r"\brm\s+-[a-zA-Z]*r"),  # any recursive rm is notable-high
    re.compile(r"\bkill(all)?\b|\bshutdown\b|\breboot\b"),
    re.compile(r"\bcrontab\b|\bsystemctl\b|\blaunchctl\b"),
)
# Network egress from a shell command → HIGH (exfiltration channel).
_EGRESS_COMMAND = re.compile(r"\b(curl|wget|nc|netcat|ssh|scp|sftp|rsync|telnet)\b")
# Clearly safe, read-only-ish shell commands → LOW.
_LOW_COMMAND = re.compile(
    r"^\s*(git\s+(status|diff|log|show|branch|remote|config\s+--get)|ls|ll|cat|head|tail|pwd|echo|which|whoami|date|env|wc|grep|find|tree|stat|file)\b",
)

_COMMAND_KEYS = ("command", "cmd", "script", "code")


class RiskClassifier:
    def _command_text(self, arguments: dict[str, Any]) -> str:
        for key in _COMMAND_KEYS:
            v = arguments.get(key)
            if isinstance(v, str) and v:
                return v
        return ""

    def classify(self, tool: str, arguments: dict[str, Any]) -> RiskTier:
        tool_l = (tool or "").lower()

        # 1) Command / shell tools — tier by the command itself.
        if any(h in tool_l for h in _COMMAND_TOOL_HINTS):
            cmd = self._command_text(arguments)
            if not cmd:
                return RiskTier.MEDIUM
            if any(p.search(cmd) for p in _HIGH_COMMAND) or _EGRESS_COMMAND.search(cmd):
                return RiskTier.HIGH
            if _LOW_COMMAND.search(cmd):
                return RiskTier.LOW
            return RiskTier.MEDIUM

        # 2) Network-capable tools → HIGH (egress / SSRF surface).
        if any(h in tool_l for h in _NETWORK_TOOL_HINTS):
            return RiskTier.HIGH

        # 3) Deletes are notable (recoverable but worth tiering up from writes).
        if "delete" in tool_l or "remove" in tool_l or "rm_" in tool_l:
            return RiskTier.MEDIUM

        # 4) Read-only tools → LOW.
        if any(h in tool_l for h in _READ_TOOL_HINTS):
            return RiskTier.LOW

        # 5) In-workspace write/edit (boundary already enforced) → LOW.
        if any(h in tool_l for h in _WRITE_TOOL_HINTS):
            return RiskTier.LOW

        # 6) Unknown → MEDIUM (ask in interactive; allow under risk-based automation).
        return RiskTier.MEDIUM
