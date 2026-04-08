"""Tests for the shared pre-collab artifact discovery utility."""

from __future__ import annotations

import time
from pathlib import Path

from massgen.precollab_utils import (
    build_subagent_parent_context_paths,
    find_precollab_artifact,
)


def _make_subagent_dir(tmp_path: Path, subagent_id: str) -> Path:
    """Create the standard subagent directory structure."""
    d = tmp_path / "subagents" / subagent_id
    d.mkdir(parents=True)
    return d


# --- Pattern 1: full_logs/final/agent_*/workspace/ ---


def test_find_precollab_artifact_in_final_workspace(tmp_path: Path):
    base = _make_subagent_dir(tmp_path, "persona_generation")
    target = base / "full_logs" / "final" / "agent_a" / "workspace"
    target.mkdir(parents=True)
    (target / "personas.json").write_text('{"personas": {}}')

    result = find_precollab_artifact(str(tmp_path), "persona_generation", "personas.json")

    assert result is not None
    assert result.name == "personas.json"
    assert "full_logs/final/agent_a/workspace" in str(result)


# --- Pattern 4: workspace/agent_*/ ---


def test_find_precollab_artifact_in_direct_workspace(tmp_path: Path):
    base = _make_subagent_dir(tmp_path, "criteria_generation")
    target = base / "workspace" / "agent_b"
    target.mkdir(parents=True)
    (target / "criteria.json").write_text('{"criteria": []}')

    result = find_precollab_artifact(str(tmp_path), "criteria_generation", "criteria.json")

    assert result is not None
    assert result.name == "criteria.json"


# --- No match ---


def test_find_precollab_artifact_returns_none_when_missing(tmp_path: Path):
    _make_subagent_dir(tmp_path, "prompt_improvement")

    result = find_precollab_artifact(str(tmp_path), "prompt_improvement", "improved_prompt.json")

    assert result is None


# --- Multiple matches: most recent wins ---


def test_find_precollab_artifact_prefers_most_recent(tmp_path: Path):
    base = _make_subagent_dir(tmp_path, "persona_generation")

    # Older file in direct workspace
    older = base / "workspace" / "agent_a"
    older.mkdir(parents=True)
    older_file = older / "personas.json"
    older_file.write_text('{"personas": {"agent_a": {}}}')

    # Ensure mtime difference
    time.sleep(0.05)

    # Newer file in final workspace
    newer = base / "full_logs" / "final" / "agent_b" / "workspace"
    newer.mkdir(parents=True)
    newer_file = newer / "personas.json"
    newer_file.write_text('{"personas": {"agent_b": {}}}')

    result = find_precollab_artifact(str(tmp_path), "persona_generation", "personas.json")

    assert result is not None
    assert result == newer_file


# --- Pattern 2: full_logs/agent_*/<ts>/<ts2>/ ---


def test_find_precollab_artifact_in_timestamped_logs(tmp_path: Path):
    base = _make_subagent_dir(tmp_path, "prompt_improvement")
    target = base / "full_logs" / "agent_x" / "20260321" / "run1"
    target.mkdir(parents=True)
    (target / "improved_prompt.json").write_text('{"prompt": "better"}')

    result = find_precollab_artifact(str(tmp_path), "prompt_improvement", "improved_prompt.json")

    assert result is not None
    assert result.name == "improved_prompt.json"


# --- Pattern 3: workspace/snapshots/agent_*/ ---


def test_find_precollab_artifact_in_snapshots(tmp_path: Path):
    base = _make_subagent_dir(tmp_path, "criteria_generation")
    target = base / "workspace" / "snapshots" / "agent_c"
    target.mkdir(parents=True)
    (target / "criteria.json").write_text('{"criteria": []}')

    result = find_precollab_artifact(str(tmp_path), "criteria_generation", "criteria.json")

    assert result is not None
    assert "snapshots" in str(result)


# --- Pattern 5: workspace/temp/agent_*/agent*/ ---


def test_find_precollab_artifact_in_temp_nested(tmp_path: Path):
    base = _make_subagent_dir(tmp_path, "persona_generation")
    target = base / "workspace" / "temp" / "agent_d" / "agent_inner"
    target.mkdir(parents=True)
    (target / "personas.json").write_text('{"personas": {}}')

    result = find_precollab_artifact(str(tmp_path), "persona_generation", "personas.json")

    assert result is not None
    assert "temp" in str(result)


# --- Nonexistent subagent dir ---


def test_find_precollab_artifact_nonexistent_subagent_dir(tmp_path: Path):
    """Returns None when the subagent directory doesn't exist at all."""
    result = find_precollab_artifact(str(tmp_path), "nonexistent", "file.json")

    assert result is None


# --- Scoping: files outside the subagent dir are NOT found ---


def test_find_precollab_artifact_ignores_files_outside_subagent_dir(tmp_path: Path):
    """Files in the log_directory root should NOT be found (unlike rglob)."""
    _make_subagent_dir(tmp_path, "prompt_improvement")
    # Place file at log root — should NOT be discovered
    (tmp_path / "improved_prompt.json").write_text('{"prompt": "stray"}')

    result = find_precollab_artifact(str(tmp_path), "prompt_improvement", "improved_prompt.json")

    assert result is None


# --- build_subagent_parent_context_paths ---


def test_build_subagent_parent_context_paths_resolves_relative_against_cwd_not_workspace(
    tmp_path: Path,
    monkeypatch,
):
    """Regression: relative context_paths inherited from parent backend configs must
    resolve against the MassGen process cwd, not the parent agent's workspace dir.

    Reproduces the criteria_generation failure where a parent config with
    ``orchestrator.context_paths: [{path: massgen/evals/circle_packing}]`` caused the
    precollab subagent to receive ``<parent_workspace>/massgen/evals/circle_packing``,
    which does not exist, and to die at subprocess startup with
    ``Context paths not found``. The parent orchestrator itself resolves these
    relative paths against ``Path.cwd()`` via ``FilesystemManager.add_context_paths``,
    so the helper must match that anchor.
    """
    monkeypatch.chdir(tmp_path)

    # Relative target that exists under the process cwd, not under the parent workspace.
    target = tmp_path / "data_dir"
    target.mkdir()

    # Parent agent workspace is a nested dir (mirrors .massgen/workspaces/ws_xyz).
    parent_ws = tmp_path / ".massgen" / "workspaces" / "ws_xyz"
    parent_ws.mkdir(parents=True)

    agent_configs = [
        {
            "id": "agent_a",
            "backend": {
                "type": "openai",
                "model": "gpt-4o-mini",
                "context_paths": [{"path": "data_dir", "permission": "read"}],
            },
        },
    ]

    result = build_subagent_parent_context_paths(
        parent_workspace=str(parent_ws),
        agent_configs=agent_configs,
    )

    result_paths = {entry["path"] for entry in result}
    expected_cwd_path = str(target.resolve())
    bogus_workspace_path = str((parent_ws / "data_dir").resolve())

    assert expected_cwd_path in result_paths, f"Expected relative context_path to resolve against process cwd " f"({expected_cwd_path}); got {result_paths}"
    assert bogus_workspace_path not in result_paths, f"Relative context_path was wrongly resolved against parent workspace " f"({bogus_workspace_path}); this is the regression."
    # Every emitted entry must be read-only.
    assert all(entry["permission"] == "read" for entry in result)


def test_build_subagent_parent_context_paths_absolute_paths_preserved(tmp_path: Path):
    """Absolute inherited paths pass through unchanged — the cwd anchor only
    applies to relative entries.
    """
    abs_target = tmp_path / "external" / "spec_frozen"
    abs_target.mkdir(parents=True)

    parent_ws = tmp_path / ".massgen" / "workspaces" / "ws_abc"
    parent_ws.mkdir(parents=True)

    agent_configs = [
        {
            "backend": {
                "context_paths": [{"path": str(abs_target), "permission": "write"}],
            },
        },
    ]

    result = build_subagent_parent_context_paths(
        parent_workspace=str(parent_ws),
        agent_configs=agent_configs,
    )

    result_paths = {entry["path"] for entry in result}
    assert str(abs_target.resolve()) in result_paths
    # Absolute paths should be demoted to read-only.
    abs_entry = next(e for e in result if e["path"] == str(abs_target.resolve()))
    assert abs_entry["permission"] == "read"


def test_build_subagent_parent_context_paths_includes_parent_workspace(tmp_path: Path):
    """The parent agent's workspace is always emitted as a read-only context path."""
    parent_ws = tmp_path / ".massgen" / "workspaces" / "ws_only"
    parent_ws.mkdir(parents=True)

    result = build_subagent_parent_context_paths(
        parent_workspace=str(parent_ws),
        agent_configs=[],
    )

    assert len(result) >= 1
    assert result[0]["path"] == str(parent_ws.resolve())
    assert result[0]["permission"] == "read"


def test_build_subagent_parent_context_paths_accepts_string_entries(
    tmp_path: Path,
    monkeypatch,
):
    """Backend ``context_paths`` entries may be plain strings (not dicts) —
    exercise both branches.
    """
    monkeypatch.chdir(tmp_path)

    target_rel = tmp_path / "rel_data"
    target_rel.mkdir()
    target_abs = tmp_path / "abs_data"
    target_abs.mkdir()

    parent_ws = tmp_path / ".massgen" / "workspaces" / "ws_strings"
    parent_ws.mkdir(parents=True)

    agent_configs = [
        {
            "backend": {
                "context_paths": [
                    "rel_data",  # relative string
                    str(target_abs),  # absolute string
                ],
            },
        },
    ]

    result = build_subagent_parent_context_paths(
        parent_workspace=str(parent_ws),
        agent_configs=agent_configs,
    )

    result_paths = {entry["path"] for entry in result}
    assert str(target_rel.resolve()) in result_paths
    assert str(target_abs.resolve()) in result_paths


def test_build_subagent_parent_context_paths_deduplicates_across_agents(
    tmp_path: Path,
    monkeypatch,
):
    """Two agents inheriting the same relative path produce a single entry."""
    monkeypatch.chdir(tmp_path)

    target = tmp_path / "shared_data"
    target.mkdir()

    parent_ws = tmp_path / ".massgen" / "workspaces" / "ws_dedupe"
    parent_ws.mkdir(parents=True)

    agent_configs = [
        {
            "backend": {
                "context_paths": [{"path": "shared_data", "permission": "read"}],
            },
        },
        {
            "backend": {
                "context_paths": [{"path": "shared_data", "permission": "read"}],
            },
        },
    ]

    result = build_subagent_parent_context_paths(
        parent_workspace=str(parent_ws),
        agent_configs=agent_configs,
    )

    shared_resolved = str(target.resolve())
    matching = [entry for entry in result if entry["path"] == shared_resolved]
    assert len(matching) == 1, f"Expected 1 entry for {shared_resolved}, got {len(matching)}"
