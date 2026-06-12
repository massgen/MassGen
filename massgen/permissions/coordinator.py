"""PermissionCoordinator — resolves a per-tool-call ``ask`` into allow/deny.

Owned by the backend; the chokepoint calls ``resolve_ask`` when a PreToolUse hook
returns ``decision == "ask"``. Flow: normalize a stable cache key → if a prior
grant covers it, allow without re-prompting → else build an AuthorizationObject
(with a classified risk tier) and ask the ApprovalProvider → cache session/always
grants (and persist 'always' as a rule via an injected callback).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from .approval_provider import ApprovalProvider
from .hooks import normalize_pattern
from .ledger import ApprovalLedger
from .models import AuthorizationObject, GrantScope
from .risk_classifier import RiskClassifier
from .session_cache import SessionApprovalCache


class PermissionCoordinator:
    def __init__(
        self,
        provider: ApprovalProvider,
        *,
        cache: SessionApprovalCache | None = None,
        risk_classifier: RiskClassifier | None = None,
        persist_always: Callable[[AuthorizationObject, Any], None] | None = None,
        ledger: ApprovalLedger | None = None,
    ) -> None:
        self.provider = provider
        self.cache = cache or SessionApprovalCache()
        self.risk_classifier = risk_classifier or RiskClassifier()
        self._persist_always = persist_always
        self.ledger = ledger

    async def resolve_ask(
        self,
        agent_id: str | None,
        tool: str,
        arguments: dict[str, Any],
        reason: str = "",
    ) -> tuple[bool, str | None]:
        """Return (allowed, feedback). Honors cached grants; otherwise asks the provider."""
        normalized = normalize_pattern(tool, arguments)
        key = self.cache.key_for(agent_id or "", tool, normalized)
        risk = self.risk_classifier.classify(tool, arguments)
        authz = AuthorizationObject(
            agent_id=agent_id or "",
            tool=tool,
            arguments=arguments,
            normalized_pattern=normalized,
            risk=risk,
            reason=reason,
            args_preview=self._preview(tool, arguments),
        )
        if self.cache.check(key):
            self._audit(authz, allowed=True, operator="cache", scope=GrantScope.SESSION, source="cache")
            return (True, None)

        decision = await self.provider.request_approval(authz)
        if decision.allowed and decision.scope in (GrantScope.SESSION, GrantScope.ALWAYS):
            self.cache.grant(key, decision.scope)
            if decision.scope == GrantScope.ALWAYS and self._persist_always:
                self._persist_always(authz, decision)
        self._audit(
            authz,
            allowed=decision.allowed,
            operator=decision.operator,
            scope=decision.scope,
            source="provider",
            feedback=decision.feedback,
        )
        return (decision.allowed, decision.feedback)

    def _audit(
        self,
        authz: AuthorizationObject,
        *,
        allowed: bool,
        operator: str,
        scope: GrantScope,
        source: str,
        feedback: str | None = None,
    ) -> None:
        if self.ledger is None:
            return
        self.ledger.record(
            authz,
            allowed=allowed,
            operator=operator,
            scope=scope,
            source=source,
            feedback=feedback,
        )

    @staticmethod
    def _preview(tool: str, arguments: dict[str, Any]) -> str:
        cmd = arguments.get("command") or arguments.get("cmd")
        if isinstance(cmd, str) and cmd:
            return f"$ {cmd}"
        try:
            return f"{tool} {json.dumps(arguments)[:200]}"
        except (TypeError, ValueError):
            return tool
