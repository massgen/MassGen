"""P2.2 — persisting `always` grants and loading them back as rules.

The modal's "Always" button yields a ``GrantScope.ALWAYS`` decision. To make that
mean *always* (not session-only), the coordinator persists it as a declarative
``allow(...)`` rule in ``settings.local.json`` (``make_persist_callback``), and the
hook installer loads those rules back into the engine on the next run
(``load_persisted_rules``). Persistence is human-gated: a rule only lands here
after an operator explicitly clicks "Always".

File shape mirrors the config block so persisted and configured rules are the
same algebra::

    {"permissions": {"rules": {"allow": ["command(make build)", ...]}}}
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..logger_config import logger
from .models import ApprovalDecision, AuthorizationObject
from .rules import PermissionRuleSet, classify_action_target


def _rule_for(authz: AuthorizationObject) -> str | None:
    """Build a stable ``action(target)`` rule from an approved call, or None if the
    call has no concrete target (an empty target would persist an over-broad grant)."""
    action, target = classify_action_target(authz.tool, authz.arguments)
    if not target:
        return None
    return f"{action}({target})"


def _read_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError) as exc:
        logger.warning(f"[permissions] could not read settings {path}: {exc}")
        return {}


def make_persist_callback(path: str | Path) -> Callable[[AuthorizationObject, ApprovalDecision], None]:
    """Return a ``persist_always(authz, decision)`` that appends a deduped allow rule
    to ``path``'s ``permissions.rules.allow`` list, preserving all other settings."""
    target_path = Path(path)

    def _persist(authz: AuthorizationObject, _decision: ApprovalDecision) -> None:
        rule = _rule_for(authz)
        if rule is None:
            logger.info(f"[permissions] not persisting 'always' for {authz.tool}: no stable target")
            return
        try:
            data = _read_settings(target_path)
            perms = data.setdefault("permissions", {})
            if not isinstance(perms, dict):
                perms = data["permissions"] = {}
            rules = perms.setdefault("rules", {})
            if not isinstance(rules, dict):
                rules = perms["rules"] = {}
            allow = rules.setdefault("allow", [])
            if not isinstance(allow, list):
                allow = rules["allow"] = []
            if rule not in allow:  # append-only, deduped
                allow.append(rule)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            logger.info(f"[permissions] persisted 'always' grant: {rule} -> {target_path}")
        except OSError as exc:  # persistence must never break the run
            logger.warning(f"[permissions] failed to persist 'always' grant: {exc}")

    return _persist


def load_persisted_rules(path: str | Path) -> PermissionRuleSet | None:
    """Load previously-persisted allow/ask/deny rules from ``path`` as a rule set,
    or None if the file is absent/unreadable/has no permission rules."""
    target_path = Path(path)
    if not target_path.exists():
        return None
    data = _read_settings(target_path)
    perms = data.get("permissions")
    rules_cfg = perms.get("rules") if isinstance(perms, dict) else None
    if not isinstance(rules_cfg, dict):
        return None
    rs = PermissionRuleSet.from_config(rules_cfg)
    return rs if not rs.is_empty else None
