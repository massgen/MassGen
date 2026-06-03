#!/usr/bin/env python3
"""CLI mode flags: parsing, validation, and application to config.

Part of the massgen.cli package (extracted from the legacy monolithic cli.py).
"""

import argparse
from typing import (
    TYPE_CHECKING,
    Any,
)

if TYPE_CHECKING:
    pass


def add_mode_flags_to_parser(parser: argparse.ArgumentParser) -> None:
    """Add mode bar toggle flags to an argparse parser.

    These flags mirror the TUI mode bar toggles, allowing CLI control
    of agent mode, coordination mode, refinement, and persona generation.
    """
    mode_group = parser.add_argument_group(
        "mode settings",
        "Override execution mode (mirrors TUI mode bar toggles)",
    )
    mode_group.add_argument(
        "--single-agent",
        nargs="?",
        const=True,
        default=None,
        metavar="AGENT_ID",
        help="Single-agent mode. Optionally specify agent ID (default: first agent). " "Overrides multi-agent config to use only one agent.",
    )
    mode_group.add_argument(
        "--coordination-mode",
        choices=["parallel", "decomposition"],
        default=None,
        help="Coordination mode: parallel (voting) or decomposition (subtask-based). " "Overrides coordination_mode from config file.",
    )
    mode_group.add_argument(
        "--quick",
        action="store_true",
        help="Quick mode: disable refinement. Agents produce one answer with no " "voting loop. Equivalent to TUI 'Refine OFF' toggle.",
    )
    mode_group.add_argument(
        "--personas",
        choices=["off", "perspective", "implementation", "methodology"],
        default=None,
        help="Enable parallel persona generation with specified diversity mode. " "'off' disables persona generation. Requires parallel coordination mode.",
    )
    mode_group.add_argument(
        "--fast",
        action="store_true",
        help="Fast mode: preset that tightens pre-round and post-candidate phases. "
        "Enables fast_iteration_mode, caps verifications to 1 and fix loops to 0 per round, "
        "skips redundant scaffolding on restart, and lowers image-understanding reasoning_effort "
        "to 'low' for latency-bounded read_media calls. YAML values always win over this preset.",
    )


def validate_mode_flag_combinations(args: argparse.Namespace) -> list[str]:
    """Validate that CLI mode flag combinations are compatible.

    Returns a list of error messages (empty if valid).
    """
    errors: list[str] = []

    if getattr(args, "single_agent", None) is not None and getattr(args, "coordination_mode", None) == "decomposition":
        errors.append(
            "--single-agent and --coordination-mode decomposition are incompatible. " "Decomposition requires multiple agents.",
        )

    personas = getattr(args, "personas", None)
    if personas is not None and personas != "off" and getattr(args, "coordination_mode", None) == "decomposition":
        errors.append(
            "--personas requires parallel coordination mode, not decomposition.",
        )

    if getattr(args, "web_quickstart", False) and getattr(args, "web", False):
        errors.append(
            "--web-quickstart already launches a dedicated browser setup flow; do not combine it with --web.",
        )

    quickstart_agents = getattr(args, "quickstart_agents", None)
    if quickstart_agents:
        if not getattr(args, "quickstart", False) or not getattr(args, "headless", False):
            errors.append(
                "--quickstart-agent requires --quickstart --headless.",
            )
        if getattr(args, "config_backend", None) or getattr(args, "config_model", None) or getattr(args, "config_agent_id", None) or getattr(args, "config_agents", None) is not None:
            errors.append(
                "--quickstart-agent cannot be combined with --config-backend, --config-model, --config-agent-id, or --config-agents.",
            )

    return errors


def apply_mode_flags_to_config(
    config: dict[str, Any],
    args: argparse.Namespace,
) -> None:
    """Apply CLI mode flags to the config dict.

    Mirrors the logic in TuiModeState.get_orchestrator_overrides() from
    tui_modes.py, but applies overrides to the raw config dict before
    the orchestrator is constructed.
    """
    coordination_mode = getattr(args, "coordination_mode", None)
    quick = getattr(args, "quick", False)
    personas = getattr(args, "personas", None)
    single_agent = getattr(args, "single_agent", None)
    fast = getattr(args, "fast", False)

    # Nothing to do if no mode flags set
    if coordination_mode is None and not quick and personas is None and not fast:
        return

    if "orchestrator" not in config:
        config["orchestrator"] = {}
    orch = config["orchestrator"]

    # Coordination mode
    if coordination_mode is not None:
        orch["coordination_mode"] = "decomposition" if coordination_mode == "decomposition" else "voting"

    # Quick mode (refinement OFF)
    if quick:
        orch["max_new_answers_per_agent"] = 1
        orch["skip_final_presentation"] = True

        if single_agent is not None:
            # Single agent + quick = skip voting too
            orch["skip_voting"] = True
        else:
            # Multi-agent + quick = independent work, deferred single vote
            orch["disable_injection"] = True
            orch["defer_voting_until_all_answered"] = True
            orch["final_answer_strategy"] = "synthesize"

    # Personas
    if personas is not None:
        if "coordination" not in orch:
            orch["coordination"] = {}
        if personas == "off":
            if "persona_generator" in orch["coordination"]:
                orch["coordination"]["persona_generator"]["enabled"] = False
        else:
            orch["coordination"]["persona_generator"] = {
                "enabled": True,
                "diversity_mode": personas,
            }

    # Fast mode: preset of orthogonal speed knobs. YAML values always win,
    # so only fill in keys that aren't already present.
    if fast:
        if "coordination" not in orch:
            orch["coordination"] = {}
        coord = orch["coordination"]
        fast_defaults = {
            "fast_iteration_mode": True,
            "max_verifications_per_round": 1,
            "max_internal_fix_loops": 0,
            "skip_redundant_scaffolding": True,
        }
        for key, default in fast_defaults.items():
            if key not in coord:
                coord[key] = default

        # Also lower image-understanding reasoning effort (read_media /
        # understand_image) so vision calls don't blow the latency budget.
        # Lives under orchestrator.multimodal_config, not coordination.
        mm_cfg = orch.setdefault("multimodal_config", {})
        image_cfg = mm_cfg.setdefault("image", {})
        image_cfg.setdefault("reasoning_effort", "low")


def filter_agents_for_single_mode(
    agents: dict[str, Any],
    single_agent_arg: Any,
) -> dict[str, Any]:
    """Filter agents dict for --single-agent mode.

    Args:
        agents: Dict mapping agent IDs to agent objects.
        single_agent_arg: The parsed --single-agent value.
            None = no filtering, True = pick first, str = pick by ID.

    Returns:
        Filtered agents dict (single entry or unchanged).

    Raises:
        ValueError: If specified agent ID not found.
    """
    if single_agent_arg is None:
        return agents

    if single_agent_arg is True:
        # Pick first agent
        first_id = next(iter(agents.keys()))
        return {first_id: agents[first_id]}

    # Pick by ID
    agent_id = str(single_agent_arg)
    if agent_id not in agents:
        available = ", ".join(agents.keys())
        raise ValueError(
            f"Agent '{agent_id}' not found in config. " f"Available agents: {available}",
        )
    return {agent_id: agents[agent_id]}


def build_cli_mode_defaults(args: argparse.Namespace) -> dict[str, Any]:
    """Build a dict of CLI mode defaults for passing to the TUI.

    Returns an empty dict if no mode flags were set.
    """
    defaults: dict[str, Any] = {}

    single_agent = getattr(args, "single_agent", None)
    if single_agent is not None:
        defaults["agent_mode"] = "single"
        if single_agent is not True:
            defaults["selected_agent"] = str(single_agent)

    coordination_mode = getattr(args, "coordination_mode", None)
    if coordination_mode is not None:
        defaults["coordination_mode"] = coordination_mode

    personas = getattr(args, "personas", None)
    if personas is not None:
        defaults["personas"] = personas

    if getattr(args, "quick", False):
        defaults["refinement_enabled"] = False

    if getattr(args, "plan", False):
        defaults["plan_mode"] = "plan"
    elif getattr(args, "spec", False):
        defaults["plan_mode"] = "spec"

    return defaults


def _build_cli_overrides_dict(args: argparse.Namespace) -> dict[str, Any]:
    """Build a dict of CLI overrides for forwarding to the WebUI server.

    Extracts config-affecting CLI flags that would otherwise be lost when
    ``--web`` bypasses ``main()``.  Returns an empty dict when no flags apply.
    """
    overrides: dict[str, Any] = {}
    if getattr(args, "eval_criteria", None):
        overrides["eval_criteria"] = args.eval_criteria
    if getattr(args, "checklist_criteria_preset", None):
        overrides["checklist_criteria_preset"] = args.checklist_criteria_preset
    if getattr(args, "orchestrator_timeout", None) is not None:
        overrides["orchestrator_timeout"] = args.orchestrator_timeout
    if getattr(args, "cwd_context", None):
        overrides["cwd_context"] = args.cwd_context
    if getattr(args, "web_review", False):
        overrides["web_review"] = True
    return overrides
