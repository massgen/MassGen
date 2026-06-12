"""Activation predicates for the permissions system — single source of truth.

Both the hook installer (which wires the engine) and the system-prompt builder
(which adds the guardrail policy section) must agree on "are permissions active
for this agent?". Keeping that decision here prevents the two call sites from
drifting (e.g. the prompt promising guardrails the installer didn't actually
register).
"""

from __future__ import annotations

from typing import Any


def is_permissions_enabled(perms: Any) -> bool:
    """Presence-based opt-in: a ``permissions`` block that exists and isn't
    explicitly disabled. ``None``/``False`` (or ``{enabled: False}``) → off."""
    if perms is None or perms is False:
        return False
    if isinstance(perms, dict) and perms.get("enabled", True) is False:
        return False
    return True


def guardrail_prompt_active(backend: Any) -> bool:
    """True iff the permission engine is genuinely active for this backend.

    Requires BOTH an enabled ``permissions`` block AND a backend that supports the
    approval chokepoint (``set_permission_coordinator``). Native backends
    (claude_code, codex) lack the chokepoint, so the engine is inactive there and
    the guardrail policy section must NOT appear (it would promise enforcement the
    backend can't deliver — see the installer's parity guard)."""
    cfg = getattr(backend, "config", None)
    perms = cfg.get("permissions") if isinstance(cfg, dict) else None
    return is_permissions_enabled(perms) and hasattr(backend, "set_permission_coordinator")
