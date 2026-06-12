"""Declarative permission rules — Antigravity-style ``action(target)`` algebra.

A small action vocabulary, each with a glob/regex target, grouped under
``allow`` / ``ask`` / ``deny``, with **deny-wins** precedence:

    permissions:
      rules:
        deny:  [ "command(git push --force*)", "write_file(/etc/**)" ]
        ask:   [ "read_url(*)", "command(npm publish*)" ]
        allow: [ "write_file(./**)", "command(git status)", "mcp(linear/*)" ]

Evaluation order: deny → allow → ask → (no match → fall to the risk classifier).
An explicit ``allow`` therefore suppresses the risk-ask — which is exactly why
rules + risk must live in ONE engine hook (see hooks.py).

Actions unify MassGen's tool surface:
  command, read_file, write_file, read_url, mcp, ``*`` (any).
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from typing import Any

from ..logger_config import logger

_RULE_RE = re.compile(r"^\s*([A-Za-z_*][\w*]*)\s*(?:\((.*)\)\s*)?$")

ACTIONS = ("command", "read_file", "write_file", "read_url", "mcp", "*")

# tool-name → action mapping hints.
_COMMAND_HINTS = ("execute_command", "bash", "shell", "exec", "run_command", "terminal")
_NETWORK_HINTS = ("fetch", "read_url", "websearch", "web_search", "browse")
_WRITE_HINTS = ("write", "edit", "create", "move", "copy", "apply_patch", "notebook", "delete", "remove")
_READ_HINTS = ("read", "grep", "glob", "list", "view", "search", "cat")
_PATH_KEYS = ("path", "file_path", "destination", "destination_path", "target", "notebook_path")
# MCP servers whose tools are FILE operations (so they map to read_file/write_file,
# not the generic mcp(...) action). Other MCP servers stay as mcp(server/tool).
_FILESYSTEM_SERVERS = ("filesystem", "workspace_tools", "workspace_copy")


def _fs_action(tool_name: str) -> str | None:
    tn = tool_name.lower()
    if any(h in tn for h in _WRITE_HINTS):
        return "write_file"
    if any(h in tn for h in _READ_HINTS):
        return "read_file"
    return None


def classify_action_target(tool: str, args: dict[str, Any]) -> tuple[str, str]:
    """Map a tool call to ``(action, target)`` for rule matching."""
    tl = (tool or "").lower()

    # Command/shell tools (incl. mcp__command_line__execute_command).
    if any(h in tl for h in _COMMAND_HINTS):
        return ("command", str(args.get("command") or args.get("cmd") or ""))

    # MCP tools: only the framework FILESYSTEM servers map to file actions; every
    # other server stays mcp(server/tool) (so e.g. linear/create_issue is NOT a write).
    if tool.startswith("mcp__"):
        parts = tool.split("__")
        server = parts[1] if len(parts) > 1 else ""
        tool_name = "__".join(parts[2:]) if len(parts) > 2 else server
        if server in _FILESYSTEM_SERVERS:
            action = _fs_action(tool_name)
            if action:
                return (action, _first_path(args))
        if any(h in tool_name.lower() for h in _NETWORK_HINTS):
            return ("read_url", str(args.get("url") or args.get("domain") or ""))
        return ("mcp", f"{server}/{tool_name}")

    # Non-MCP tools (Claude-Code-style Write/Edit/Read, WebFetch, …).
    if any(h in tl for h in _NETWORK_HINTS):
        return ("read_url", str(args.get("url") or args.get("domain") or ""))
    if any(h in tl for h in _WRITE_HINTS):
        return ("write_file", _first_path(args))
    if any(h in tl for h in _READ_HINTS):
        return ("read_file", _first_path(args))
    return ("mcp", tool)


def _first_path(args: dict[str, Any]) -> str:
    for k in _PATH_KEYS:
        v = args.get(k)
        if isinstance(v, str) and v:
            return v
    return ""


@dataclass
class PermissionRule:
    decision: str  # allow | ask | deny
    action: str  # one of ACTIONS
    pattern: str  # glob target ("*" = any)

    def matches(self, action: str, target: str) -> bool:
        if self.action != "*" and self.action != action:
            return False
        # Case-sensitive glob for deterministic, OS-independent matching.
        return fnmatch.fnmatchcase(target, self.pattern)


def _parse_rule(spec: str, decision: str) -> PermissionRule | None:
    m = _RULE_RE.match(spec.strip())
    if not m:
        logger.warning(f"[permissions] ignoring malformed rule: {spec!r}")
        return None
    action = m.group(1)
    pattern = m.group(2)
    if pattern is None:  # bare action, e.g. "read_url" → any target
        pattern = "*"
    if action != "*" and action not in ACTIONS:
        logger.warning(f"[permissions] unknown action '{action}' in rule {spec!r} (allowed: {ACTIONS})")
    return PermissionRule(decision=decision, action=action, pattern=pattern)


@dataclass
class PermissionRuleSet:
    allow_rules: list[PermissionRule] = field(default_factory=list)
    ask_rules: list[PermissionRule] = field(default_factory=list)
    deny_rules: list[PermissionRule] = field(default_factory=list)

    def __init__(
        self,
        allow: list[str] | None = None,
        ask: list[str] | None = None,
        deny: list[str] | None = None,
    ) -> None:
        self.allow_rules = [r for s in (allow or []) if (r := _parse_rule(s, "allow"))]
        self.ask_rules = [r for s in (ask or []) if (r := _parse_rule(s, "ask"))]
        self.deny_rules = [r for s in (deny or []) if (r := _parse_rule(s, "deny"))]

    @property
    def is_empty(self) -> bool:
        return not (self.allow_rules or self.ask_rules or self.deny_rules)

    def evaluate(self, tool: str, args: dict[str, Any]) -> str | None:
        """Return 'deny'|'allow'|'ask', or None if no rule matches (→ risk classifier)."""
        action, target = classify_action_target(tool, args)
        if any(r.matches(action, target) for r in self.deny_rules):
            return "deny"
        if any(r.matches(action, target) for r in self.allow_rules):
            return "allow"
        if any(r.matches(action, target) for r in self.ask_rules):
            return "ask"
        return None

    @classmethod
    def from_config(cls, cfg: dict[str, Any] | None) -> PermissionRuleSet:
        cfg = cfg or {}
        return cls(allow=cfg.get("allow"), ask=cfg.get("ask"), deny=cfg.get("deny"))

    @classmethod
    def merge(cls, rule_sets: list[PermissionRuleSet]) -> PermissionRuleSet:
        """Merge scopes by decision bucket so deny-wins holds ACROSS scopes
        (all denies are checked before any allow, before any ask)."""
        merged = cls()
        for rs in rule_sets:
            merged.deny_rules.extend(rs.deny_rules)
            merged.allow_rules.extend(rs.allow_rules)
            merged.ask_rules.extend(rs.ask_rules)
        return merged


# Per-agent ROLE presets — a one-liner for the common multi-agent shapes. Role rules
# are a higher-precedence scope (merged with deny-wins), so a `read-only` agent's
# write-deny cannot be loosened by a per-agent allow rule.
_ROLE_SPECS: dict[str, dict[str, list[str]]] = {
    # Reads files, may ask before network; NO writes, NO shell. (alias: researcher)
    "read-only": {
        "deny": ["write_file(*)", "command(*)"],
        "ask": ["read_url(*)"],
        "allow": ["read_file(*)"],
    },
    "researcher": {
        "deny": ["write_file(*)", "command(*)"],
        "ask": ["read_url(*)"],
        "allow": ["read_file(*)"],
    },
    # Full workspace access — no preset rules (falls to user rules + risk).
    "read-write": {},
    "implementer": {},
}


def role_rule_set(role: str | None) -> PermissionRuleSet | None:
    """Return the rule set for a named role, or None if the role is unknown/empty."""
    if not role:
        return None
    spec = _ROLE_SPECS.get(role.strip().lower())
    if spec is None:
        logger.warning(f"[permissions] unknown role '{role}' (known: {sorted(_ROLE_SPECS)})")
        return None
    return PermissionRuleSet(allow=spec.get("allow"), ask=spec.get("ask"), deny=spec.get("deny"))
