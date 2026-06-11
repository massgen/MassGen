"""ApprovalProvider — how a tool call asks a human (or a policy) for approval.

Pluggable so the same chokepoint works in interactive TUI, headless/automation, and
(later) remote/Slack-style approval:
  - ``PolicyApprovalProvider``   — no human; applies a configurable default.
  - ``CallbackApprovalProvider`` — delegates to an injected async fn (the TUI modal,
    wired via the same Future pattern as ``show_change_review_modal``).
  - (P1.2) ``FileApprovalProvider`` — per-tool request/response JSON for headless/remote.
"""

from __future__ import annotations

import abc
from collections.abc import Awaitable, Callable

from ..logger_config import logger
from .models import (
    ApprovalDecision,
    AuthorizationObject,
    AutomationDefault,
    GrantScope,
    RiskTier,
)


class ApprovalProvider(abc.ABC):
    @abc.abstractmethod
    async def request_approval(self, authz: AuthorizationObject) -> ApprovalDecision:
        """Return the decision for this authorization request."""
        raise NotImplementedError


class PolicyApprovalProvider(ApprovalProvider):
    """Automation/headless: decide without a human via a configurable default."""

    def __init__(self, automation_default: AutomationDefault = AutomationDefault.RISK_BASED) -> None:
        self.automation_default = automation_default

    async def request_approval(self, authz: AuthorizationObject) -> ApprovalDecision:
        if self.automation_default == AutomationDefault.ALLOW_ALL:
            return ApprovalDecision(allowed=True, operator="policy")
        if self.automation_default == AutomationDefault.DENY_ALL:
            return ApprovalDecision(
                allowed=False,
                operator="policy",
                feedback=f"Denied by automation policy (deny-all): {authz.reason or authz.tool}",
            )
        # RISK_BASED (shipped default): high → deny (with reason), low/medium → allow.
        if authz.risk == RiskTier.HIGH:
            return ApprovalDecision(
                allowed=False,
                operator="policy",
                feedback=(
                    f"Denied by automation policy: '{authz.tool}' is high-risk " f"({authz.reason or 'no human available to approve'}). " "Choose a lower-risk action or run interactively to approve."
                ),
            )
        return ApprovalDecision(allowed=True, operator="policy")


class CallbackApprovalProvider(ApprovalProvider):
    """Interactive: delegate to an injected ``async (authz) -> ApprovalDecision``.

    The callback is wired to the TUI approval modal (mirroring the Future-based
    ``show_change_review_modal`` flow). On callback failure we fail closed by default
    so a crashed/closed modal never silently allows a tool call.
    """

    def __init__(
        self,
        callback: Callable[[AuthorizationObject], Awaitable[ApprovalDecision]],
        *,
        fail_closed: bool = True,
    ) -> None:
        self._callback = callback
        self._fail_closed = fail_closed

    async def request_approval(self, authz: AuthorizationObject) -> ApprovalDecision:
        try:
            return await self._callback(authz)
        except Exception as e:  # noqa: BLE001 - any modal/transport failure
            logger.warning(f"[ApprovalProvider] approval callback failed: {e}")
            if self._fail_closed:
                return ApprovalDecision(allowed=False, operator="policy", feedback=f"Approval unavailable ({e}); denied (fail-closed).")
            return ApprovalDecision(allowed=True, scope=GrantScope.ONCE, operator="policy")
