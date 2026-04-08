#!/usr/bin/env python3
"""Standalone validator for checkpoint plan JSON files.

Self-contained — no massgen imports. Designed to run inside Docker
containers where agents validate their checkpoint_result.json before
submitting.

Usage:
    python validate_plan.py <path_to_json_file>

Exit codes:
    0 = PASS
    1 = FAIL (with error details on stderr)
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

VALID_TERMINALS: set[str] = {"proceed", "recheckpoint", "refuse"}


def validate_recovery_node(node: Any, path: str = "recovery") -> list[str]:
    """Validate a recovery node recursively. Returns list of errors."""
    errors: list[str] = []

    if isinstance(node, str):
        if node not in VALID_TERMINALS:
            errors.append(
                f"{path}: invalid terminal value '{node}', " f"must be one of {sorted(VALID_TERMINALS)}",
            )
        return errors

    if not isinstance(node, dict):
        errors.append(f"{path}: must be a string terminal or dict node")
        return errors

    if "if" not in node:
        errors.append(f"{path}: missing 'if' field")
    if "then" not in node:
        errors.append(f"{path}: missing 'then' field")
    else:
        errors.extend(validate_recovery_node(node["then"], f"{path}.then"))

    if "else" in node:
        errors.extend(validate_recovery_node(node["else"], f"{path}.else"))

    return errors


def validate_plan(raw: dict[str, Any]) -> list[str]:
    """Validate a checkpoint plan dict. Returns list of errors."""
    errors: list[str] = []

    if "plan" not in raw:
        errors.append("Output missing required 'plan' field")
        return errors

    plan = raw["plan"]
    if not isinstance(plan, list):
        errors.append("'plan' must be a list of steps")
        return errors
    if len(plan) == 0:
        errors.append("'plan' must not be empty")
        return errors

    for i, step in enumerate(plan):
        prefix = f"plan[{i}]"
        if not isinstance(step, dict):
            errors.append(f"{prefix}: must be a dict")
            continue
        if "description" not in step:
            errors.append(f"{prefix}: missing required 'description' field")

        aa = step.get("approved_action")
        if aa is not None:
            if not isinstance(aa, dict):
                errors.append(f"{prefix}.approved_action: must be a dict")
            else:
                for field in ("goal_id", "tool", "args"):
                    if field not in aa:
                        errors.append(
                            f"{prefix}.approved_action: missing '{field}'",
                        )

        recovery = step.get("recovery")
        if recovery is not None:
            errors.extend(
                validate_recovery_node(recovery, f"{prefix}.recovery"),
            )

    return errors


def extract_json(text: str) -> dict[str, Any]:
    """Extract JSON dict from text, handling fenced code blocks."""
    # Try bare JSON first
    text = text.strip()
    if text.startswith("{"):
        return json.loads(text)

    # Try ```json fenced block
    match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1).strip())

    # Try finding first { to last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])

    raise ValueError("No valid JSON object found in input")


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <path_to_json_file>", file=sys.stderr)
        return 1

    filepath = sys.argv[1]
    try:
        with open(filepath) as f:
            content = f.read()
    except FileNotFoundError:
        print(f"FAIL: file not found: {filepath}", file=sys.stderr)
        return 1

    try:
        data = extract_json(content)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"FAIL: could not parse JSON: {e}", file=sys.stderr)
        return 1

    errors = validate_plan(data)
    if errors:
        print("FAIL: validation errors:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
