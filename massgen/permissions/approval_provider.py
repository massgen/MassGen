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
from pathlib import Path

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


class FileApprovalProvider(ApprovalProvider):
    """Headless/remote approval via a request/response JSON handshake.

    Writes ``<dir>/req_<id>.json`` describing the call, then polls for
    ``<dir>/resp_<id>.json`` (written by an external approver — a TUI watcher, a
    Slack bot, ``/approve <id>``, …). The id is stable per logical request, so a
    response that already exists on resume is honored (idempotent). The response is
    consumed (deleted) on read so a later identical call re-prompts. On timeout we
    fail closed (deny) — a tool never proceeds without an explicit approval.

    Response JSON: ``{"approved": bool, "scope": "once|session|always", "feedback": str}``.
    """

    def __init__(
        self,
        requests_dir: str | Path,
        *,
        poll_interval: float = 0.4,
        timeout: float = 300.0,
        fail_closed: bool = True,
    ) -> None:
        self.dir = Path(requests_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.poll_interval = max(0.01, poll_interval)
        self.timeout = max(0.0, timeout)
        self.fail_closed = fail_closed

    def request_id(self, authz: AuthorizationObject) -> str:
        import hashlib

        raw = f"{authz.agent_id}\x1f{authz.tool}\x1f{authz.normalized_pattern}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    async def request_approval(self, authz: AuthorizationObject) -> ApprovalDecision:
        import asyncio
        import json

        rid = self.request_id(authz)
        req_path = self.dir / f"req_{rid}.json"
        resp_path = self.dir / f"resp_{rid}.json"
        try:
            req_path.write_text(
                json.dumps(
                    {
                        "id": rid,
                        "agent_id": authz.agent_id,
                        "tool": authz.tool,
                        "pattern": authz.normalized_pattern,
                        "risk": authz.risk.value,
                        "reason": authz.reason,
                        "preview": authz.args_preview,
                        "status": "pending",
                    },
                    indent=2,
                ),
            )
        except OSError as e:
            logger.warning(f"[FileApprovalProvider] could not write request: {e}")

        waited = 0.0
        while waited < self.timeout:
            if resp_path.exists():
                try:
                    data = json.loads(resp_path.read_text())
                except (OSError, ValueError):
                    data = {}
                try:
                    resp_path.unlink()
                except OSError:
                    pass
                allowed = bool(data.get("approved", data.get("allowed", False)))
                scope = GrantScope.ONCE
                raw_scope = str(data.get("scope", "once"))
                try:
                    scope = GrantScope(raw_scope)
                except ValueError:
                    pass
                return ApprovalDecision(allowed=allowed, scope=scope, feedback=data.get("feedback"), operator="human")
            await asyncio.sleep(self.poll_interval)
            waited += self.poll_interval

        if self.fail_closed:
            return ApprovalDecision(allowed=False, feedback="Approval request timed out (no response); denied (fail-closed).", operator="policy")
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
