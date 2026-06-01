"""Unit tests for essential files manifest loading and context block formatting.

Tests cover:
- Manifest JSON loading from temp workspaces
- Invalid/missing manifest handling
- Context block formatting with pre-loaded and read-guidance files
- Large file eviction (preview + path pattern)
- Verification groups prompt language changes
"""

import json
from unittest.mock import MagicMock


class TestLoadEssentialFilesManifests:
    """Tests for _load_essential_files_manifests on the orchestrator."""

    def _make_orchestrator(self, snapshot_storage, agents, agent_mapping):
        """Create a minimal mock orchestrator with required attributes."""
        orch = MagicMock()
        orch._snapshot_storage = str(snapshot_storage)
        orch.agents = {aid: MagicMock() for aid in agents}
        orch.coordination_tracker = MagicMock()
        orch.coordination_tracker.get_reverse_agent_mapping.return_value = agent_mapping

        # Bind the real method
        from massgen.orchestrator import Orchestrator
        from massgen.orchestrator_collaborators import EssentialFilesHelper

        orch._essential_files_helper = EssentialFilesHelper(orch)
        orch._load_essential_files_manifests = Orchestrator._load_essential_files_manifests.__get__(orch)
        return orch

    def test_load_valid_manifest(self, tmp_path):
        """Valid manifest JSON should be loaded and returned."""
        snapshot_dir = tmp_path / "snapshots"
        agent_dir = snapshot_dir / "agent_a" / "memory" / "short_term"
        agent_dir.mkdir(parents=True)

        manifest = {
            "version": 1,
            "summary": "Test state",
            "files": [
                {"path": "index.html", "why": "Main file", "read_whole_file": True, "how_to_read": None},
            ],
        }
        (agent_dir / "essential_files_manifest.json").write_text(json.dumps(manifest))

        orch = self._make_orchestrator(
            snapshot_dir,
            agents=["agent_a"],
            agent_mapping={"agent_a": "agent1"},
        )

        result = orch._load_essential_files_manifests("agent_a")
        assert "agent1" in result
        assert result["agent1"]["summary"] == "Test state"
        assert len(result["agent1"]["files"]) == 1

    def test_load_missing_manifest(self, tmp_path):
        """Missing manifest file should return empty dict."""
        snapshot_dir = tmp_path / "snapshots"
        (snapshot_dir / "agent_a").mkdir(parents=True)

        orch = self._make_orchestrator(
            snapshot_dir,
            agents=["agent_a"],
            agent_mapping={"agent_a": "agent1"},
        )

        result = orch._load_essential_files_manifests("agent_a")
        assert result == {}

    def test_load_malformed_json(self, tmp_path):
        """Malformed JSON should be skipped with warning."""
        snapshot_dir = tmp_path / "snapshots"
        agent_dir = snapshot_dir / "agent_a" / "memory" / "short_term"
        agent_dir.mkdir(parents=True)
        (agent_dir / "essential_files_manifest.json").write_text("not valid json{{{")

        orch = self._make_orchestrator(
            snapshot_dir,
            agents=["agent_a"],
            agent_mapping={"agent_a": "agent1"},
        )

        result = orch._load_essential_files_manifests("agent_a")
        assert result == {}

    def test_load_wrong_version(self, tmp_path):
        """Manifest with wrong version should be skipped."""
        snapshot_dir = tmp_path / "snapshots"
        agent_dir = snapshot_dir / "agent_a" / "memory" / "short_term"
        agent_dir.mkdir(parents=True)

        manifest = {"version": 99, "files": []}
        (agent_dir / "essential_files_manifest.json").write_text(json.dumps(manifest))

        orch = self._make_orchestrator(
            snapshot_dir,
            agents=["agent_a"],
            agent_mapping={"agent_a": "agent1"},
        )

        result = orch._load_essential_files_manifests("agent_a")
        assert result == {}

    def test_no_snapshot_storage(self):
        """No snapshot storage should return empty dict."""
        orch = MagicMock()
        orch._snapshot_storage = None

        from massgen.orchestrator import Orchestrator
        from massgen.orchestrator_collaborators import EssentialFilesHelper

        orch._essential_files_helper = EssentialFilesHelper(orch)
        orch._load_essential_files_manifests = Orchestrator._load_essential_files_manifests.__get__(orch)

        result = orch._load_essential_files_manifests("agent_a")
        assert result == {}


class TestFormatEssentialFilesContextBlock:
    """Tests for _format_essential_files_context_block."""

    def _make_orchestrator(self, snapshot_storage, agent_mapping, answers_by_agent=None):
        """Create a minimal mock orchestrator for formatting tests."""
        orch = MagicMock()
        orch._snapshot_storage = str(snapshot_storage) if snapshot_storage else None
        orch.coordination_tracker = MagicMock()
        orch.coordination_tracker.get_reverse_agent_mapping.return_value = agent_mapping

        # Set up answers_by_agent for label lookup
        if answers_by_agent is None:
            answers_by_agent = {}
        orch.coordination_tracker.answers_by_agent = answers_by_agent

        from massgen.orchestrator import Orchestrator

        orch._format_essential_files_context_block = Orchestrator._format_essential_files_context_block.__get__(orch)
        return orch

    def test_empty_manifests_returns_none(self, tmp_path):
        orch = self._make_orchestrator(tmp_path, {"agent_a": "agent1"})
        result = orch._format_essential_files_context_block({}, "agent_a")
        assert result is None

    def test_preloaded_file_content(self, tmp_path):
        """Files with read_whole_file=true should have content pre-loaded."""
        snapshot_dir = tmp_path / "snapshots"
        agent_dir = snapshot_dir / "agent_a"
        agent_dir.mkdir(parents=True)
        (agent_dir / "index.html").write_text("<h1>Hello</h1>")

        orch = self._make_orchestrator(
            snapshot_dir,
            agent_mapping={"agent_a": "agent1"},
        )

        manifests = {
            "agent1": {
                "version": 1,
                "summary": "A web page",
                "files": [
                    {"path": "index.html", "why": "Main page", "read_whole_file": True, "how_to_read": None},
                ],
            },
        }

        result = orch._format_essential_files_context_block(manifests, "agent_a")
        assert result is not None
        assert "<essential_files>" in result
        assert "<h1>Hello</h1>" in result
        assert 'path="agent1/index.html"' in result
        assert "<instructions>" in result

    def test_read_guidance_files(self, tmp_path):
        """Files with read_whole_file=false should show read guidance."""
        snapshot_dir = tmp_path / "snapshots"
        (snapshot_dir / "agent_a").mkdir(parents=True)

        orch = self._make_orchestrator(
            snapshot_dir,
            agent_mapping={"agent_a": "agent1"},
        )

        manifests = {
            "agent1": {
                "version": 1,
                "summary": "Complex app",
                "files": [
                    {
                        "path": "src/engine.ts",
                        "why": "Core logic",
                        "read_whole_file": False,
                        "how_to_read": "rg for 'class Engine' and 'handleEvent'",
                    },
                ],
            },
        }

        result = orch._format_essential_files_context_block(manifests, "agent_a")
        assert result is not None
        assert "<read_these>" in result
        assert "rg for 'class Engine'" in result
        assert "Core logic" in result
        assert "agent1/src/engine.ts" in result

    def test_large_file_eviction(self, tmp_path):
        """Files exceeding token threshold should show preview only."""
        snapshot_dir = tmp_path / "snapshots"
        agent_dir = snapshot_dir / "agent_a"
        agent_dir.mkdir(parents=True)

        # Create a large file (>20K tokens ~ >80K chars)
        large_content = "x" * 100_000
        (agent_dir / "big.svg").write_text(large_content)

        orch = self._make_orchestrator(
            snapshot_dir,
            agent_mapping={"agent_a": "agent1"},
        )

        manifests = {
            "agent1": {
                "version": 1,
                "summary": "SVG art",
                "files": [
                    {"path": "big.svg", "why": "Main SVG", "read_whole_file": True, "how_to_read": None},
                ],
            },
        }

        result = orch._format_essential_files_context_block(manifests, "agent_a")
        assert result is not None
        assert 'preview="true"' in result
        assert "100000" in result  # total chars shown
        # Preview should be much shorter than original
        assert len(result) < 50_000

    def test_context_block_has_parallel_read_instructions(self, tmp_path):
        """The context block should instruct agents to read guidance files in parallel."""
        snapshot_dir = tmp_path / "snapshots"
        (snapshot_dir / "agent_a").mkdir(parents=True)

        orch = self._make_orchestrator(
            snapshot_dir,
            agent_mapping={"agent_a": "agent1"},
        )

        manifests = {
            "agent1": {
                "version": 1,
                "summary": "Test",
                "files": [
                    {"path": "a.ts", "why": "File A", "read_whole_file": False, "how_to_read": "rg for main"},
                ],
            },
        }

        result = orch._format_essential_files_context_block(manifests, "agent_a")
        assert "parallel" in result.lower()
        assert "DO NOT re-read" in result


class TestVerificationGroupsPromptLanguage:
    """Tests for verification groups language in system prompt sections."""

    def test_task_planning_section_uses_verification_groups(self):
        """TaskPlanningSection should use verification groups, not per-task verification."""
        from massgen.system_prompt_sections import TaskPlanningSection

        section = TaskPlanningSection(filesystem_mode=True)
        content = section.build_content()

        # Should contain verification groups language
        assert "Verification is separate from implementation" in content
        assert "verify in groups" in content

        # Should NOT contain per-task verification language
        assert "Verify it actually works, then call" not in content
        assert "verify each task" not in content

    def test_output_first_verification_uses_grouped_language(self):
        """OutputFirstVerificationSection should not say 'short loops'."""
        from massgen.system_prompt_sections import OutputFirstVerificationSection

        section = OutputFirstVerificationSection()
        content = section.build_content()

        # Should contain grouped verification language
        assert "logical group" in content

        # Should NOT contain micro-loop language
        assert "short loops: interact, improve, re-interact" not in content

    def test_flow_lines_use_verify_in_groups(self):
        """Flow lines should say 'verify in groups' not 'verify each task'."""
        from massgen.system_prompt_sections import TaskPlanningSection

        # Without subagents
        section = TaskPlanningSection(filesystem_mode=True)
        content = section.build_content()
        assert "verify in groups" in content
        assert "verify each task" not in content

    def test_summary_step_uses_grouped_language(self):
        """Summary step should mention grouped verification."""
        from massgen.system_prompt_sections import TaskPlanningSection

        section = TaskPlanningSection(filesystem_mode=True)
        content = section.build_content()

        assert "separate from task completion" in content


class TestPlanningInjectionManifest:
    """Tests that the planning injection task mentions the manifest."""

    def test_verification_memo_task_mentions_manifest(self):
        """The write_verification_memo task should mention essential_files_manifest.json."""
        from massgen.mcp_tools.planning._planning_mcp_server import (
            _append_terminal_verification_memory_task,
        )

        tasks = [
            {"id": "implement", "description": "Do work"},
        ]

        out = _append_terminal_verification_memory_task(tasks)
        memo_task = out[-1]
        assert "essential_files_manifest.json" in memo_task["description"]
        assert "verification_latest.md" in memo_task["description"]
        assert '"version": 1' in memo_task["description"]


class TestNamespaceVerificationMemoryFiles:
    """Tests that archival namespaces the manifest file."""

    def test_namespace_includes_manifest(self, tmp_path):
        """_namespace_verification_memory_files should namespace the manifest file too."""
        from massgen.orchestrator import Orchestrator

        archive_path = tmp_path / "archived"
        short_term = archive_path / "short_term"
        short_term.mkdir(parents=True)

        # Create both files
        (short_term / "verification_latest.md").write_text("verification content")
        (short_term / "essential_files_manifest.json").write_text('{"version": 1}')

        orch = MagicMock()
        from massgen.orchestrator_collaborators import WorkspaceLifecycleManager

        orch.coordination_tracker = MagicMock()
        orch.coordination_tracker.get_path_token.return_value = "abc123"
        # Method delegates to WorkspaceLifecycleManager — wire a real collaborator
        # so the namespacing logic actually runs (otherwise the auto-mocked
        # collaborator returns a MagicMock and nothing is renamed).
        orch._workspace_lifecycle_manager = WorkspaceLifecycleManager(orch)
        orch._namespace_verification_memory_files = Orchestrator._namespace_verification_memory_files.__get__(orch)

        orch._namespace_verification_memory_files(archive_path, "agent_a")

        # Original files should be gone
        assert not (short_term / "verification_latest.md").exists()
        assert not (short_term / "essential_files_manifest.json").exists()

        # Namespaced files should exist
        assert (short_term / "verification_latest__abc123.md").exists()
        assert (short_term / "essential_files_manifest__abc123.json").exists()
