"""SessionApprovalCache — remember approval grants so we don't re-prompt.

Keyed by (agent_id, tool, normalized_pattern). `once` grants are consumed on first
check; `session` grants stay sticky for the run. `always` grants are persisted to
``.massgen/settings.local.json`` by the caller (trust-gated) — this cache only holds
the in-memory once/session grants.
"""

from __future__ import annotations

from .models import GrantScope


class SessionApprovalCache:
    def __init__(self) -> None:
        # key -> scope (only ONCE / SESSION live here; ALWAYS becomes a persisted rule)
        self._grants: dict[str, GrantScope] = {}

    @staticmethod
    def key_for(agent_id: str, tool: str, normalized_pattern: str) -> str:
        return f"{agent_id}\x1f{tool}\x1f{normalized_pattern}"

    def grant(self, key: str, scope: GrantScope) -> None:
        # ALWAYS is persisted as a rule by the caller; we still cache it for this run.
        self._grants[key] = scope

    def check(self, key: str) -> bool:
        """Return True if a grant covers this key. Consumes a ONCE grant."""
        scope = self._grants.get(key)
        if scope is None:
            return False
        if scope == GrantScope.ONCE:
            del self._grants[key]
        return True

    def clear(self) -> None:
        self._grants.clear()
