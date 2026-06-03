"""Closed value sets for MassGen config "mode" fields, as ``Literal`` types.

These were previously bare ``str`` fields whose valid values lived only in
comments and in a parallel ``VALID_*`` set inside ``config_validator.py``.
Expressing them as ``Literal`` makes the type the documentation, gives the type
checker and pydantic the allowed values directly, and provides a single source
of truth (``config_validator`` can derive its sets from ``get_args`` of these).

This module imports nothing beyond typing, so it stays a dependency leaf.
"""

from __future__ import annotations

from typing import Literal

CoordinationMode = Literal["voting", "decomposition"]
WriteMode = Literal["auto", "worktree", "isolated", "legacy"]
DriftConflictPolicy = Literal["skip", "prefer_presenter", "fail"]
NoveltyInjection = Literal["none", "gentle", "moderate", "aggressive"]
RoundEvaluatorTransformationPressure = Literal["gentle", "balanced", "aggressive"]
SubagentRuntimeMode = Literal["isolated", "inherited", "delegated"]
SubagentRuntimeFallbackMode = Literal["inherited"]
FinalAnswerStrategy = Literal["winner_reuse", "winner_present", "synthesize"]
LearningCaptureMode = Literal["round", "verification_and_final_only", "final_only"]
GapReportMode = Literal["changedoc", "separate", "none"]

__all__ = [
    "CoordinationMode",
    "WriteMode",
    "DriftConflictPolicy",
    "NoveltyInjection",
    "RoundEvaluatorTransformationPressure",
    "SubagentRuntimeMode",
    "SubagentRuntimeFallbackMode",
    "FinalAnswerStrategy",
    "LearningCaptureMode",
    "GapReportMode",
]
