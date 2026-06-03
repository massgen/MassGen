#!/usr/bin/env python3
"""Planning-turn helpers and evaluation-criteria injection.

Part of the massgen.cli package (extracted from the legacy monolithic cli.py).
"""

import json
import sys
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
)

if TYPE_CHECKING:
    pass


# --- cross-module references within the cli package ---
from ._constants import BRIGHT_RED, EXIT_CONFIG_ERROR, RESET


def _is_planning_turn(
    mode_state: Any | None,
    cli_plan_enabled: bool = False,
) -> bool:
    """Return True when the current turn is a planning turn."""
    if mode_state and getattr(mode_state, "plan_mode", None) in {"plan", "plan_and_execute"}:
        return True
    return bool(cli_plan_enabled)


def _disable_evaluation_criteria_generation_for_planning(
    coordination_config: Any | None,
) -> bool:
    """Disable dynamic evaluation criteria generation for planning turns.

    Returns True when a config value was changed.
    """
    if coordination_config is None:
        return False

    # YAML/dict config path
    if isinstance(coordination_config, dict):
        ec_cfg = coordination_config.get("evaluation_criteria_generator")
        if not isinstance(ec_cfg, dict):
            return False
        if not ec_cfg.get("enabled", False):
            return False
        ec_cfg["enabled"] = False
        return True

    # Dataclass/object config path
    ec_cfg = getattr(coordination_config, "evaluation_criteria_generator", None)
    if ec_cfg is None:
        return False
    if not getattr(ec_cfg, "enabled", False):
        return False
    ec_cfg.enabled = False
    return True


def _set_planning_checklist_criteria_defaults(
    coordination_config: Any | None,
) -> bool:
    """Set planning-specific checklist preset when no explicit criteria source exists.

    Returns True when checklist_criteria_preset was set to "planning".
    """
    if coordination_config is None:
        return False

    # YAML/dict config path
    if isinstance(coordination_config, dict):
        inline = coordination_config.get("checklist_criteria_inline")
        preset = coordination_config.get("checklist_criteria_preset")
        if inline or preset:
            return False
        coordination_config["checklist_criteria_preset"] = "planning"
        return True

    # Dataclass/object config path
    inline = getattr(coordination_config, "checklist_criteria_inline", None)
    preset = getattr(coordination_config, "checklist_criteria_preset", None)
    if inline or preset:
        return False
    setattr(coordination_config, "checklist_criteria_preset", "planning")
    return True


def _load_eval_criteria(file_path: str) -> list[dict]:
    """Load and validate evaluation criteria from a JSON file.

    Returns a list of criteria dicts. Calls sys.exit on error.
    """
    path = Path(file_path)
    if not path.exists():
        print(f"{BRIGHT_RED}Error: --eval-criteria file not found: {file_path}{RESET}")
        sys.exit(EXIT_CONFIG_ERROR)
    try:
        criteria_data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        print(f"{BRIGHT_RED}Error: --eval-criteria file is not valid JSON: {e}{RESET}")
        sys.exit(EXIT_CONFIG_ERROR)
    # Accept both bare array [...] and wrapped {"criteria": [...]} format
    # (the latter is what MassGen's quality tools produce)
    if isinstance(criteria_data, dict) and "criteria" in criteria_data:
        criteria_data = criteria_data["criteria"]
    if not isinstance(criteria_data, list):
        print(f'{BRIGHT_RED}Error: --eval-criteria must be a JSON array or {{"criteria": [...]}}{RESET}')
        sys.exit(EXIT_CONFIG_ERROR)

    # Validate each criterion has a text field (or common alias)
    for i, item in enumerate(criteria_data):
        if not isinstance(item, dict):
            print(f"{BRIGHT_RED}Error: --eval-criteria item {i + 1} must be a JSON object, got {type(item).__name__}{RESET}")
            sys.exit(EXIT_CONFIG_ERROR)
        has_text = item.get("text") or item.get("description") or item.get("name")
        if not has_text:
            print(
                f"{BRIGHT_RED}Error: --eval-criteria item {i + 1} missing 'text' field.\n"
                f'  Expected: {{"text": "...", "category": "primary|standard|stretch"}}\n'
                f"  Got keys: {list(item.keys())}{RESET}",
            )
            sys.exit(EXIT_CONFIG_ERROR)

    return criteria_data


def _inject_eval_criteria_into_config(
    config: dict,
    criteria: list[dict],
) -> None:
    """Inject evaluation criteria into config as checklist_criteria_inline.

    Merges into config["orchestrator"]["coordination"]["checklist_criteria_inline"],
    creating intermediate dicts as needed. CLI criteria override any YAML inline criteria.
    """
    if "orchestrator" not in config:
        config["orchestrator"] = {}
    if "coordination" not in config["orchestrator"]:
        config["orchestrator"]["coordination"] = {}
    config["orchestrator"]["coordination"]["checklist_criteria_inline"] = criteria


def _inject_checklist_criteria_preset_into_config(
    config: dict,
    preset: str,
) -> None:
    """Inject checklist criteria preset into config from CLI flag.

    Sets config["orchestrator"]["coordination"]["checklist_criteria_preset"],
    creating intermediate dicts as needed. CLI flag overrides any YAML preset.
    """
    if "orchestrator" not in config:
        config["orchestrator"] = {}
    if "coordination" not in config["orchestrator"]:
        config["orchestrator"]["coordination"] = {}
    config["orchestrator"]["coordination"]["checklist_criteria_preset"] = preset
