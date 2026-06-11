"""MassGen permissions system.

A layered permission model built on the existing hook chokepoint
(``GeneralHookManager``), path validator (``PathPermissionManager``), and OS
sandbox (``SRT``). See docs/dev_notes/permission_systems_research.md and the plan.
"""

from .hardline import is_hardline_blocked
from .models import (
    ApprovalDecision,
    AuthorizationObject,
    AutomationDefault,
    GrantScope,
    RiskTier,
)
from .risk_classifier import RiskClassifier
from .session_cache import SessionApprovalCache

__all__ = [
    "ApprovalDecision",
    "AuthorizationObject",
    "AutomationDefault",
    "GrantScope",
    "RiskClassifier",
    "RiskTier",
    "SessionApprovalCache",
    "is_hardline_blocked",
]
