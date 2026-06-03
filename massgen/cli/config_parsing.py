#!/usr/bin/env python3
"""Parsing of orchestrator, coordination, and timeout config sections.

Part of the massgen.cli package (extracted from the legacy monolithic cli.py).
"""

from typing import (
    TYPE_CHECKING,
    Any,
)

if TYPE_CHECKING:
    from ..agent_config import CoordinationConfig

from ..agent_config import AgentConfig, TimeoutConfig


def _apply_orchestrator_runtime_params(
    orchestrator_config: AgentConfig,
    orchestrator_cfg: dict[str, Any] | None,
) -> None:
    """Apply orchestrator-level runtime params from config onto an AgentConfig."""
    orchestrator_config.apply_orchestrator_config(orchestrator_cfg)


def _parse_standalone_checkpoint(raw: dict[str, Any]) -> dict[str, Any]:
    """Parse the `coordination.standalone_checkpoint` block into kwargs.

    Returns kwargs suitable for passing to CoordinationConfig(...). Unknown
    `mode` values fall back to "generate" but log a warning — a silent
    coercion would let a typo (e.g. "verfy") run the wrong mode without any
    surfacing to the user. The fallback (rather than raising) keeps malformed
    configs forgiving at parse time.
    """
    from ..agent_config import CoordinationConfig

    return CoordinationConfig._parse_standalone_checkpoint(raw)


def _parse_coordination_config(coord_cfg: dict[str, Any]) -> "CoordinationConfig":
    """Parse a coordination config dict into a CoordinationConfig object.

    Centralizes the parsing logic used by run_question_with_history,
    run_single_question, and run_textual_interactive_mode.
    """
    from ..agent_config import CoordinationConfig

    return CoordinationConfig.from_dict(coord_cfg)


def _parse_timeout_config(timeout_settings: dict[str, Any] | None) -> TimeoutConfig:
    """Parse top-level timeout_settings into a TimeoutConfig object."""
    return TimeoutConfig.from_dict(timeout_settings)
