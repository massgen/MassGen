"""Core data types for the MassGen permissions system.

Three-layer separation (see docs/dev_notes/permission_systems_research.md):
authorization (deterministic floor) → approval (human checkpoint) → guardrails
(risk triage). These models carry an *authorization object* through the chokepoint
and back as an *approval decision*.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RiskTier(str, Enum):
    """Blast-radius tier of a tool call (low → allow, high → interrupt/deny)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class GrantScope(str, Enum):
    """How long an approval grant lasts."""

    ONCE = "once"  # single execution, consumed immediately
    SESSION = "session"  # sticky for this run (in-memory cache)
    ALWAYS = "always"  # persisted as a rule (gated on project trust)


class AutomationDefault(str, Enum):
    """What a per-tool ``ask`` resolves to when no human is present (--automation)."""

    DENY_ALL = "deny-all"
    ALLOW_ALL = "allow-all"
    RISK_BASED = "risk-based"  # high → deny, low/medium → allow (shipped default)


@dataclass
class AuthorizationObject:
    """The unit handed to an ApprovalProvider: what's being requested and why."""

    agent_id: str
    tool: str
    arguments: dict[str, Any]
    normalized_pattern: str = ""  # stable key for caching (e.g. "command:git status")
    risk: RiskTier = RiskTier.MEDIUM
    reason: str = ""
    args_preview: str = ""  # human-readable preview/diff for the approval card
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ApprovalDecision:
    """The operator's (or policy's) answer to an AuthorizationObject."""

    allowed: bool
    scope: GrantScope = GrantScope.ONCE
    feedback: str | None = None  # reject reason fed back to the agent
    operator: str = "policy"  # "human" | "policy" | "cache" | "hardline"
