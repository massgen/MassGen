"""Tests for quickstart skill setup helpers."""

import json

import yaml

import massgen.cli as cli
import massgen.utils.skills_installer as skills_installer


def _package_status(
    *,
    anthropic_installed: bool,
    openai_installed: bool,
    vercel_installed: bool,
    agent_browser_installed: bool,
    remotion_installed: bool,
    crawl4ai_installed: bool,
) -> dict:
    """Build package status payload matching check_skill_packages_installed()."""
    return {
        "anthropic": {
            "name": "Anthropic Skills Collection",
            "description": "Anthropic skills",
            "installed": anthropic_installed,
            "skill_count": 1 if anthropic_installed else 0,
        },
        "openai": {
            "name": "OpenAI Skills Collection",
            "description": "OpenAI skills",
            "installed": openai_installed,
        },
        "vercel": {
            "name": "Vercel Agent Skills",
            "description": "Vercel skills",
            "installed": vercel_installed,
        },
        "agent_browser": {
            "name": "Vercel Agent Browser Skill",
            "description": "Agent browser skill",
            "installed": agent_browser_installed,
        },
        "remotion": {
            "name": "Remotion Skill",
            "description": "Video generation and editing skill powered by Remotion",
            "installed": remotion_installed,
        },
        "crawl4ai": {
            "name": "Crawl4AI",
            "description": "Crawl4AI skill",
            "installed": crawl4ai_installed,
        },
    }


def test_install_quickstart_skills_skips_when_packages_already_installed(monkeypatch):
    """Quickstart installer should no-op when required packages are already present."""
    calls = []

    monkeypatch.setattr(
        skills_installer,
        "check_skill_packages_installed",
        lambda: _package_status(
            anthropic_installed=True,
            openai_installed=True,
            vercel_installed=True,
            agent_browser_installed=True,
            remotion_installed=True,
            crawl4ai_installed=True,
        ),
    )
    monkeypatch.setattr(
        skills_installer,
        "_check_command_exists",
        lambda _: True,
    )
    monkeypatch.setattr(
        skills_installer,
        "install_openskills_cli",
        lambda: calls.append("openskills") or True,
    )
    monkeypatch.setattr(
        skills_installer,
        "install_anthropic_skills",
        lambda: calls.append("anthropic") or True,
    )
    monkeypatch.setattr(
        skills_installer,
        "install_openai_skills",
        lambda: calls.append("openai") or True,
    )
    monkeypatch.setattr(
        skills_installer,
        "install_vercel_skills",
        lambda: calls.append("vercel") or True,
    )
    monkeypatch.setattr(
        skills_installer,
        "install_agent_browser_skill",
        lambda: calls.append("agent_browser") or True,
    )
    monkeypatch.setattr(
        skills_installer,
        "install_remotion_skill",
        lambda: calls.append("remotion") or True,
    )
    monkeypatch.setattr(
        skills_installer,
        "install_crawl4ai_skill",
        lambda: calls.append("crawl4ai") or True,
    )

    assert skills_installer.install_quickstart_skills() is True
    assert calls == []


def test_install_quickstart_skills_installs_only_missing_packages(monkeypatch):
    """Quickstart installer should install all missing quickstart skill packages."""
    calls = []

    monkeypatch.setattr(
        skills_installer,
        "check_skill_packages_installed",
        lambda: _package_status(
            anthropic_installed=False,
            openai_installed=False,
            vercel_installed=False,
            agent_browser_installed=False,
            remotion_installed=False,
            crawl4ai_installed=False,
        ),
    )
    monkeypatch.setattr(
        skills_installer,
        "_check_command_exists",
        lambda _: False,
    )
    monkeypatch.setattr(
        skills_installer,
        "install_openskills_cli",
        lambda: calls.append("openskills") or True,
    )
    monkeypatch.setattr(
        skills_installer,
        "install_anthropic_skills",
        lambda: calls.append("anthropic") or True,
    )
    monkeypatch.setattr(
        skills_installer,
        "install_openai_skills",
        lambda: calls.append("openai") or True,
    )
    monkeypatch.setattr(
        skills_installer,
        "install_vercel_skills",
        lambda: calls.append("vercel") or True,
    )
    monkeypatch.setattr(
        skills_installer,
        "install_agent_browser_skill",
        lambda: calls.append("agent_browser") or True,
    )
    monkeypatch.setattr(
        skills_installer,
        "install_remotion_skill",
        lambda: calls.append("remotion") or True,
    )
    monkeypatch.setattr(
        skills_installer,
        "install_crawl4ai_skill",
        lambda: calls.append("crawl4ai") or True,
    )

    assert skills_installer.install_quickstart_skills() is True
    assert calls == ["openskills", "anthropic", "openai", "vercel", "agent_browser", "remotion", "crawl4ai"]


def test_install_quickstart_skills_handles_partial_failures(monkeypatch):
    """Quickstart installer should continue and report failure when some installs fail."""
    calls = []

    monkeypatch.setattr(
        skills_installer,
        "check_skill_packages_installed",
        lambda: _package_status(
            anthropic_installed=False,
            openai_installed=False,
            vercel_installed=False,
            agent_browser_installed=False,
            remotion_installed=False,
            crawl4ai_installed=False,
        ),
    )
    monkeypatch.setattr(
        skills_installer,
        "_check_command_exists",
        lambda _: False,
    )
    monkeypatch.setattr(
        skills_installer,
        "install_openskills_cli",
        lambda: calls.append("openskills") or False,
    )
    monkeypatch.setattr(
        skills_installer,
        "install_anthropic_skills",
        lambda: calls.append("anthropic") or True,
    )
    monkeypatch.setattr(
        skills_installer,
        "install_openai_skills",
        lambda: calls.append("openai") or True,
    )
    monkeypatch.setattr(
        skills_installer,
        "install_vercel_skills",
        lambda: calls.append("vercel") or True,
    )
    monkeypatch.setattr(
        skills_installer,
        "install_agent_browser_skill",
        lambda: calls.append("agent_browser") or True,
    )
    monkeypatch.setattr(
        skills_installer,
        "install_remotion_skill",
        lambda: calls.append("remotion") or True,
    )
    monkeypatch.setattr(
        skills_installer,
        "install_crawl4ai_skill",
        lambda: calls.append("crawl4ai") or True,
    )

    assert skills_installer.install_quickstart_skills() is False
    assert calls == ["openskills", "crawl4ai"]


def test_install_quickstart_skills_installs_openskills_when_missing(monkeypatch):
    """Quickstart installer should install openskills even if skill folders already exist."""
    calls = []

    monkeypatch.setattr(
        skills_installer,
        "check_skill_packages_installed",
        lambda: _package_status(
            anthropic_installed=True,
            openai_installed=True,
            vercel_installed=True,
            agent_browser_installed=True,
            remotion_installed=True,
            crawl4ai_installed=True,
        ),
    )
    monkeypatch.setattr(
        skills_installer,
        "_check_command_exists",
        lambda _: False,
    )
    monkeypatch.setattr(
        skills_installer,
        "install_openskills_cli",
        lambda: calls.append("openskills") or True,
    )
    monkeypatch.setattr(
        skills_installer,
        "install_anthropic_skills",
        lambda: calls.append("anthropic") or True,
    )
    monkeypatch.setattr(
        skills_installer,
        "install_openai_skills",
        lambda: calls.append("openai") or True,
    )
    monkeypatch.setattr(
        skills_installer,
        "install_vercel_skills",
        lambda: calls.append("vercel") or True,
    )
    monkeypatch.setattr(
        skills_installer,
        "install_agent_browser_skill",
        lambda: calls.append("agent_browser") or True,
    )
    monkeypatch.setattr(
        skills_installer,
        "install_remotion_skill",
        lambda: calls.append("remotion") or True,
    )
    monkeypatch.setattr(
        skills_installer,
        "install_crawl4ai_skill",
        lambda: calls.append("crawl4ai") or True,
    )

    assert skills_installer.install_quickstart_skills() is True
    assert calls == ["openskills"]


def test_quickstart_config_uses_skills_detects_enabled_flag(tmp_path):
    """CLI helper should detect use_skills=true in generated config."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump({"orchestrator": {"coordination": {"use_skills": True}}}),
        encoding="utf-8",
    )

    assert cli._quickstart_config_uses_skills(str(config_path)) is True


def test_quickstart_config_uses_skills_returns_false_when_disabled(tmp_path):
    """CLI helper should return False when skills are disabled."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump({"orchestrator": {"coordination": {"use_skills": False}}}),
        encoding="utf-8",
    )

    assert cli._quickstart_config_uses_skills(str(config_path)) is False


def test_quickstart_filename_from_config_arg_uses_filename_only():
    """Quickstart filename helper should normalize to a safe basename."""
    assert cli._quickstart_filename_from_config_arg(".massgen/custom/team-config") == "team-config.yaml"


def test_quickstart_filename_from_config_arg_returns_none_for_blank():
    """Quickstart filename helper should ignore empty values."""
    assert cli._quickstart_filename_from_config_arg("   ") is None


def test_ensure_quickstart_skills_ready_runs_installer_when_needed(monkeypatch):
    """CLI should run quickstart installer when config enables skills."""
    calls = []

    monkeypatch.setattr(cli.quickstart, "_quickstart_config_uses_skills", lambda _: True)
    monkeypatch.setattr(
        skills_installer,
        "install_quickstart_skills",
        lambda: calls.append("install") or True,
    )

    assert cli._ensure_quickstart_skills_ready("config.yaml") is True
    assert calls == ["install"]


def test_ensure_quickstart_skills_ready_skips_installer_when_not_needed(monkeypatch):
    """CLI should skip quickstart installer when config does not enable skills."""
    calls = []

    monkeypatch.setattr(cli.quickstart, "_quickstart_config_uses_skills", lambda _: False)
    monkeypatch.setattr(
        skills_installer,
        "install_quickstart_skills",
        lambda: calls.append("install") or True,
    )

    assert cli._ensure_quickstart_skills_ready("config.yaml") is True
    assert calls == []


def test_ensure_quickstart_skills_ready_skips_when_user_declines(monkeypatch):
    """CLI should skip quickstart installer when user opts out in wizard."""
    calls = []

    monkeypatch.setattr(cli.quickstart, "_quickstart_config_uses_skills", lambda _: True)
    monkeypatch.setattr(
        skills_installer,
        "install_quickstart_skills",
        lambda: calls.append("install") or True,
    )

    assert cli._ensure_quickstart_skills_ready("config.yaml", install_requested=False) is True
    assert calls == []


# ---------------------------------------------------------------------------
# check_skill_packages_installed: filesystem-based detection
# ---------------------------------------------------------------------------


def _fake_available_skills(user_skills=None, project_skills=None):
    """Build a mock return value for list_available_skills."""
    user_skills = user_skills or []
    project_skills = project_skills or []
    return {
        "builtin": [],
        "user": [{"name": s, "location": "user", "description": ""} for s in user_skills],
        "project": [{"name": s, "location": "project", "description": ""} for s in project_skills],
    }


def test_stale_manifest_does_not_report_packages_as_installed(monkeypatch, tmp_path):
    """Packages recorded in the manifest but absent from disk should NOT be reported installed."""
    # Manifest says vercel and agent_browser were installed, but no skills exist on disk.
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "vercel": {"source": "vercel-labs/agent-skills", "installed_at": "2026-01-01T00:00:00+00:00"},
                "agent_browser": {"source": "vercel-labs/agent-browser", "installed_at": "2026-01-01T00:00:00+00:00"},
            },
        ),
    )
    monkeypatch.setattr(skills_installer, "_get_package_manifest_path", lambda: manifest_path)

    # No skills on disk at all.
    monkeypatch.setattr(skills_installer, "list_available_skills", lambda: _fake_available_skills())

    result = skills_installer.check_skill_packages_installed()

    assert result["vercel"]["installed"] is False
    assert result["agent_browser"]["installed"] is False


def test_agent_browser_detected_from_skill_directory(monkeypatch, tmp_path):
    """Agent browser should be detected when the skill directory exists, not from the manifest."""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({}))
    monkeypatch.setattr(skills_installer, "_get_package_manifest_path", lambda: manifest_path)

    # agent-browser skill exists in user skills dir.
    monkeypatch.setattr(
        skills_installer,
        "list_available_skills",
        lambda: _fake_available_skills(user_skills=["agent-browser"]),
    )

    result = skills_installer.check_skill_packages_installed()

    assert result["agent_browser"]["installed"] is True


def test_vercel_detected_from_marker_skills(monkeypatch, tmp_path):
    """Vercel should be detected when marker skills exist on disk."""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({}))
    monkeypatch.setattr(skills_installer, "_get_package_manifest_path", lambda: manifest_path)

    # Vercel marker skill exists in project skills dir.
    monkeypatch.setattr(
        skills_installer,
        "list_available_skills",
        lambda: _fake_available_skills(project_skills=["react-best-practices", "web-design-guidelines"]),
    )

    result = skills_installer.check_skill_packages_installed()

    assert result["vercel"]["installed"] is True


def test_openai_detected_from_marker_skills(monkeypatch, tmp_path):
    """OpenAI should be detected when marker skills exist on disk."""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({}))
    monkeypatch.setattr(skills_installer, "_get_package_manifest_path", lambda: manifest_path)

    monkeypatch.setattr(
        skills_installer,
        "list_available_skills",
        lambda: _fake_available_skills(user_skills=["openai-docs", "gh-fix-ci"]),
    )

    result = skills_installer.check_skill_packages_installed()

    assert result["openai"]["installed"] is True


def test_remotion_detected_from_marker_skills(monkeypatch, tmp_path):
    """Remotion should be detected when marker skills exist on disk."""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({}))
    monkeypatch.setattr(skills_installer, "_get_package_manifest_path", lambda: manifest_path)

    monkeypatch.setattr(
        skills_installer,
        "list_available_skills",
        lambda: _fake_available_skills(project_skills=["remotion"]),
    )

    result = skills_installer.check_skill_packages_installed()

    assert result["remotion"]["installed"] is True


def test_anthropic_detected_from_marker_skills_not_manifest(monkeypatch, tmp_path):
    """Anthropic detection should rely on marker skills, not the manifest."""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "anthropic": {"source": "anthropics/skills", "installed_at": "2026-01-01T00:00:00+00:00"},
            },
        ),
    )
    monkeypatch.setattr(skills_installer, "_get_package_manifest_path", lambda: manifest_path)

    # Manifest says installed, but no anthropic marker skills on disk.
    monkeypatch.setattr(skills_installer, "list_available_skills", lambda: _fake_available_skills())

    result = skills_installer.check_skill_packages_installed()

    assert result["anthropic"]["installed"] is False


# ---------------------------------------------------------------------------
# Remotion install/setup section injection
# ---------------------------------------------------------------------------


def test_apply_remotion_install_setup_section_inserts_after_frontmatter():
    """Remotion setup section should be inserted after SKILL.md frontmatter."""
    original = """---
name: remotion-best-practices
description: Best practices for Remotion - Video creation in React
metadata:
  tags: remotion, video, react, animation, composition
---

## When to use

Use this skills whenever you are dealing with Remotion code to obtain the domain-specific knowledge.
"""

    updated = skills_installer._apply_remotion_install_setup_section(original)

    assert "## Install and Setup" in updated
    assert "bun create video" in updated
    assert "npx create-video@latest" in updated
    assert updated.index("## Install and Setup") < updated.index("## When to use")


def test_apply_remotion_install_setup_section_is_idempotent():
    """Remotion setup section injection should be a no-op when already present."""
    original = """---
name: remotion-best-practices
description: Best practices for Remotion - Video creation in React
metadata:
  tags: remotion, video, react, animation, composition
---

## Install and Setup

If no existing Remotion project is found in the current workspace, initialize one first.

## When to use

Use this skills whenever you are dealing with Remotion code to obtain the domain-specific knowledge.
"""

    updated = skills_installer._apply_remotion_install_setup_section(original)

    assert updated == original


def test_install_remotion_skill_runs_post_install_setup_patch(monkeypatch):
    """Successful remotion install should patch SKILL.md with setup guidance."""
    calls = []

    monkeypatch.setattr(
        skills_installer,
        "_install_openskills_skill_package",
        lambda package_id: calls.append(("install", package_id)) or True,
    )
    monkeypatch.setattr(
        skills_installer,
        "_ensure_remotion_install_setup_section",
        lambda: calls.append(("patch", None)) or True,
    )

    assert skills_installer.install_remotion_skill() is True
    assert calls == [("install", "remotion"), ("patch", None)]


def test_install_remotion_skill_skips_patch_when_install_fails(monkeypatch):
    """Failed remotion install should not attempt SKILL.md patching."""
    calls = []

    monkeypatch.setattr(
        skills_installer,
        "_install_openskills_skill_package",
        lambda package_id: calls.append(("install", package_id)) or False,
    )
    monkeypatch.setattr(
        skills_installer,
        "_ensure_remotion_install_setup_section",
        lambda: calls.append(("patch", None)) or True,
    )

    assert skills_installer.install_remotion_skill() is False
    assert calls == [("install", "remotion")]
