#!/usr/bin/env python3
"""Quickstart setup helpers (skills, docker image pull, headless summaries).

Part of the massgen.cli package (extracted from the legacy monolithic cli.py).
"""

from pathlib import Path
from typing import (
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    pass

import yaml

from ..config_builder import normalize_quickstart_config_filename
from ..logger_config import logger


def _quickstart_config_uses_skills(config_path: str | None) -> bool:
    """Return True when a config enables coordination skills."""
    if not config_path:
        return False

    try:
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except Exception as e:
        logger.debug(f"[Quickstart] Failed to read config for skill check ({config_path}): {e}")
        return False

    if not isinstance(config, dict):
        return False

    orchestrator = config.get("orchestrator", {})
    if not isinstance(orchestrator, dict):
        return False

    coordination = orchestrator.get("coordination", {})
    if not isinstance(coordination, dict):
        return False

    return bool(coordination.get("use_skills", False))


def _ensure_quickstart_skills_ready(
    config_path: str | None,
    install_requested: bool = True,
) -> bool:
    """Install quickstart skill packages when generated config enables skills."""
    if not install_requested:
        logger.info("[Quickstart] Skipping skill package installation by user choice")
        return True

    if not _quickstart_config_uses_skills(config_path):
        return True

    try:
        from ..utils.skills_installer import install_quickstart_skills

        return install_quickstart_skills()
    except Exception as e:
        logger.warning(f"[Quickstart] Skill setup failed: {e}")
        return False


def _pull_docker_image_headless() -> bool:
    """Pull default Docker image without interactive prompts.

    Returns:
        True if image was pulled successfully, False otherwise.
    """
    import subprocess

    image = "ghcr.io/massgen/mcp-runtime-sudo:latest"
    try:
        subprocess.run(
            ["docker", "pull", image],
            capture_output=True,
            timeout=300,
        )
        return True
    except Exception:
        return False


def _print_headless_quickstart_summary(result: dict) -> None:
    """Print structured, machine-parseable summary of headless quickstart."""
    print(f"\n{'=' * 50}")
    print("MASSGEN HEADLESS QUICKSTART")
    print(f"{'=' * 50}")

    # API Keys
    print("\nAPI Keys:")
    for key_name, available in result.get("api_keys_summary", {}).items():
        status = "available" if available else "not set"
        print(f"  {key_name}: {status}")

    # Selection
    if result.get("backends") and result.get("models"):
        # Multi-backend mode
        pairs = list(zip(result["backends"], result["models"]))
        print(f"\nSelected ({len(pairs)} backends):")
        for b, m in pairs:
            print(f"  {b} / {m}")
    elif result.get("backend") and result.get("model"):
        print(f"\nSelected: {result['backend']} / {result['model']}")
    else:
        print("\nSelected: none (no API keys found)")

    # Config
    if result.get("config_path"):
        print(f"Config: {result['config_path']}")
    elif result.get("env_template_path"):
        print(f"Env template: {result['env_template_path']}")

    # Docker
    docker_status = "available" if result.get("docker_available") else "not available"
    if result.get("docker_pulled"):
        docker_status += ", image pulled"
    print(f"Docker: {docker_status}")

    # Skills
    skills_status = "installed" if result.get("skills_installed") else "not installed"
    print(f"Skills: {skills_status}")

    # Status
    if result["success"]:
        print("\nSTATUS: SUCCESS")
        print("\nRun with:")
        config = result["config_path"]
        print(
            f"  massgen --automation --config {config}" ' "Your question"',
        )
    else:
        print("\nSTATUS: NEEDS_CONFIG")
        for step in result.get("manual_steps", []):
            print(f"  -> {step}")

    print()


def _quickstart_filename_from_config_arg(config_path_arg: str | None) -> str | None:
    """Extract quickstart filename override from --config when --quickstart is used."""
    if not config_path_arg:
        return None

    value = config_path_arg.strip()
    if not value:
        return None

    return normalize_quickstart_config_filename(value)


def _headless_quickstart_output_path_from_config_arg(config_path_arg: str | None) -> str | None:
    """Extract an exact output path for headless quickstart from --config."""
    if not config_path_arg:
        return None

    value = config_path_arg.strip()
    if not value:
        return None

    return str(Path(value).expanduser())


def _parse_quickstart_agent_specs(values: list[str] | None) -> list[dict[str, str | None]]:
    """Parse repeated --quickstart-agent values into explicit agent specs."""
    specs: list[dict[str, str | None]] = []
    if not values:
        return specs

    allowed_keys = {"id", "backend", "type", "model", "reasoning_effort"}
    for raw_value in values:
        spec: dict[str, str | None] = {}
        for item in raw_value.split(","):
            key, sep, value = item.partition("=")
            key = key.strip()
            value = value.strip()
            if not sep or not key or not value:
                raise ValueError(
                    "Each --quickstart-agent value must use key=value pairs, " "for example backend=claude,model=claude-opus-4-6",
                )
            if key not in allowed_keys:
                allowed = ", ".join(sorted(allowed_keys))
                raise ValueError(
                    f"Unsupported --quickstart-agent field '{key}'. " f"Allowed fields: {allowed}",
                )
            spec[key] = value

        if not (spec.get("backend") or spec.get("type")):
            raise ValueError(
                "Each --quickstart-agent requires backend=<type>.",
            )
        specs.append(spec)

    return specs


def should_run_builder() -> bool:
    """Check if config builder should run automatically.

    Returns True if:
    - No default config exists at ~/.config/massgen/config.yaml
    """
    default_config = Path.home() / ".config/massgen/config.yaml"
    return not default_config.exists()
