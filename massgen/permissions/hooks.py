"""PreToolUse hooks for the permissions system.

- ``HardlineBlocklistHook`` — separate, registered FIRST, denies catastrophic
  commands unconditionally (the safety floor).
- ``PermissionEngineHook`` — the COMPOSITE: declarative rules (P1.1) → risk
  classification → emits a single allow/ask decision. It must be one hook (not
  separate rule + risk hooks) because ``execute_hooks`` makes ``ask`` always win
  over ``allow`` — so a separate risk hook's ``ask`` could not be suppressed by an
  explicit allow rule.

The chokepoint (``base_with_custom_tool_and_mcp._execute_tool_with_logging``) owns
the SessionApprovalCache + ApprovalProvider and handles the ``ask`` → approval
round-trip; these hooks only emit the decision.
"""

from __future__ import annotations

import json
from typing import Any

from ..mcp_tools.hooks import HookResult, PatternHook
from .hardline import is_hardline_blocked
from .models import RiskTier
from .risk_classifier import RiskClassifier

_PATH_KEYS = ("path", "file_path", "destination", "destination_path", "url", "target", "notebook_path")


def normalize_pattern(tool: str, arguments: dict[str, Any]) -> str:
    """Stable key for caching grants: the command, or the tool+path/url."""
    cmd = arguments.get("command") or arguments.get("cmd")
    if isinstance(cmd, str) and cmd.strip():
        return f"command:{cmd.strip()[:200]}"
    for k in _PATH_KEYS:
        v = arguments.get(k)
        if isinstance(v, str) and v:
            return f"{tool}:{v}"
    return tool


def _parse_args(arguments: str) -> dict[str, Any]:
    try:
        return json.loads(arguments) if arguments else {}
    except (json.JSONDecodeError, TypeError):
        return {}


class HardlineBlocklistHook(PatternHook):
    """Deny catastrophic commands regardless of any rule / mode / approval."""

    def __init__(self) -> None:
        super().__init__(name="hardline_blocklist", matcher="*")

    async def execute(self, function_name: str, arguments: str, context: dict[str, Any] | None = None, **kwargs) -> HookResult:
        blocked, reason = is_hardline_blocked(function_name, _parse_args(arguments))
        if blocked:
            return HookResult.deny(reason=reason)
        return HookResult.allow()


class PermissionEngineHook(PatternHook):
    """Composite permission decision: (rules → P1.1) → risk → allow/ask."""

    def __init__(self, *, risk_classifier: RiskClassifier | None = None, rules: Any = None) -> None:
        super().__init__(name="permission_engine", matcher="*")
        self.risk_classifier = risk_classifier or RiskClassifier()
        self.rules = rules  # P1.1: declarative allow/ask/deny rule set

    async def execute(self, function_name: str, arguments: str, context: dict[str, Any] | None = None, **kwargs) -> HookResult:
        args = _parse_args(arguments)

        # 1) Declarative rules (deny > allow > ask). An explicit allow/deny is
        #    authoritative and SUPPRESSES the risk classifier — which is why rules
        #    and risk live in this one hook (ask always wins over allow in the
        #    manager's aggregation, so they can't be separate hooks).
        if self.rules is not None and not self.rules.is_empty:
            decision = self.rules.evaluate(function_name, args)
            if decision == "deny":
                return HookResult.deny(reason=f"Denied by permission rule: {function_name}")
            if decision == "allow":
                return HookResult.allow()
            if decision == "ask":
                return HookResult.ask(reason=f"Permission rule requires approval: {function_name}")

        # 2) No rule matched → tier by risk. Low → allow; medium/high → ask.
        risk = self.risk_classifier.classify(function_name, args)
        if risk == RiskTier.LOW:
            return HookResult.allow()
        return HookResult.ask(reason=f"{risk.value}-risk operation: {function_name}")
