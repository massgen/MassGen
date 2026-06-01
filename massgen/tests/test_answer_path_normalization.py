"""Tests for workspace path normalization in final answer.txt files.

When MassGen saves the winning agent's answer to the log directory's
final/agent_id/answer.txt, temporary workspace paths (e.g., /tmp/workspace_abc123)
should be replaced with the path to the adjacent workspace/ directory in the log
structure. This lets consumers read the answer and navigate directly to the
workspace without resolving stale temporary paths.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_agent(workspace_path: str) -> MagicMock:
    """Create a mock agent with a filesystem_manager that has a cwd."""
    fm = MagicMock()
    fm.cwd = workspace_path
    fm.get_current_workspace.return_value = workspace_path
    fm.snapshot_storage = None
    fm.save_snapshot = AsyncMock()
    fm.is_shared_workspace = False

    agent = MagicMock()
    agent.backend.filesystem_manager = fm
    return agent


def _make_mock_agent_state() -> MagicMock:
    """Create a mock agent state with answer tracking."""
    state = MagicMock()
    state.answer_count = 0
    state.checklist_calls_this_round = 0
    state.pending_checklist_recheck_labels = set()
    state.is_killed = False
    return state


def _make_mock_orchestrator(agents: dict, log_dir: Path) -> MagicMock:
    """Create a minimal mock orchestrator for snapshot testing."""
    from massgen.coordination_tracker import CoordinationTracker
    from massgen.orchestrator_collaborators import SnapshotManager

    orch = MagicMock()
    orch.agents = agents
    orch.agent_states = {}
    orch.coordination_tracker = CoordinationTracker()
    orch.coordination_tracker._end_session = MagicMock()
    orch.coordination_tracker.save_coordination_logs = MagicMock()
    orch.coordination_tracker.save_status_file = MagicMock()
    orch.save_metrics = MagicMock()
    # _save_agent_snapshot now delegates to SnapshotManager. Wire a real
    # collaborator (with back-ref to the mock) so the test exercises the real
    # path-normalization logic instead of an auto-mocked async coroutine.
    orch._snapshot_manager = SnapshotManager(orch)
    return orch


# ---------------------------------------------------------------------------
# Tests: _save_agent_snapshot path normalization
# ---------------------------------------------------------------------------


class TestAnswerPathNormalization:
    """Verify workspace paths in answer.txt are normalized to log dir paths."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path):
        self.tmp_path = tmp_path
        self.workspace = tmp_path / "workspace_abc123"
        self.workspace.mkdir()
        self.log_dir = tmp_path / "log_session" / "turn_1" / "attempt_1"
        self.log_dir.mkdir(parents=True)

    @pytest.mark.asyncio
    async def test_final_answer_normalizes_workspace_path(self):
        """Final answer.txt should replace temp workspace path with log workspace."""
        agent = _make_mock_agent(str(self.workspace))
        answer_text = f"I created the file at {self.workspace}/output.txt"

        from massgen.orchestrator import Orchestrator

        # Call the actual _save_agent_snapshot method
        with patch(
            "massgen.orchestrator_collaborators.snapshot_manager.get_log_session_dir",
            return_value=self.log_dir,
        ):
            orch = MagicMock(spec=Orchestrator)
            orch.agents = {"agent_a": agent}
            orch.agent_states = {"agent_a": _make_mock_agent_state()}
            orch._is_changedoc_enabled = MagicMock(return_value=False)
            # _save_agent_snapshot delegates to SnapshotManager; wire a real
            # collaborator so the spec-mocked orch routes to real logic.
            from massgen.orchestrator_collaborators import SnapshotManager

            orch._snapshot_manager = SnapshotManager(orch)

            # Call the real method with our mock self
            await Orchestrator._save_agent_snapshot(
                orch,
                agent_id="agent_a",
                answer_content=answer_text,
                is_final=True,
            )

        # Check the written answer.txt
        answer_file = self.log_dir / "final" / "agent_a" / "answer.txt"
        assert answer_file.exists()
        content = answer_file.read_text()

        expected_workspace = str(self.log_dir / "final" / "agent_a" / "workspace")
        assert expected_workspace in content
        assert str(self.workspace) not in content

    @pytest.mark.asyncio
    async def test_non_final_answer_not_normalized(self):
        """Regular (non-final) snapshots should NOT normalize paths."""
        agent = _make_mock_agent(str(self.workspace))
        answer_text = f"I created the file at {self.workspace}/output.txt"

        from massgen.orchestrator import Orchestrator

        with patch(
            "massgen.orchestrator_collaborators.snapshot_manager.get_log_session_dir",
            return_value=self.log_dir,
        ):
            orch = MagicMock(spec=Orchestrator)
            orch.agents = {"agent_a": agent}
            orch.agent_states = {"agent_a": _make_mock_agent_state()}
            orch._is_changedoc_enabled = MagicMock(return_value=False)
            # _save_agent_snapshot delegates to SnapshotManager; wire a real
            # collaborator so the spec-mocked orch routes to real logic.
            from massgen.orchestrator_collaborators import SnapshotManager

            orch._snapshot_manager = SnapshotManager(orch)

            await Orchestrator._save_agent_snapshot(
                orch,
                agent_id="agent_a",
                answer_content=answer_text,
                is_final=False,
            )

        # Non-final answers go to timestamped dirs, paths should be unchanged
        # Find the answer file (it's in a timestamped subdir)
        agent_dir = self.log_dir / "agent_a"
        answer_files = list(agent_dir.rglob("answer.txt"))
        assert len(answer_files) == 1
        content = answer_files[0].read_text()
        assert str(self.workspace) in content

    @pytest.mark.asyncio
    async def test_answer_without_workspace_path_unchanged(self):
        """Answer that doesn't contain workspace path should be written as-is."""
        agent = _make_mock_agent(str(self.workspace))
        answer_text = "The answer is 42. No workspace references here."

        from massgen.orchestrator import Orchestrator

        with patch(
            "massgen.orchestrator_collaborators.snapshot_manager.get_log_session_dir",
            return_value=self.log_dir,
        ):
            orch = MagicMock(spec=Orchestrator)
            orch.agents = {"agent_a": agent}
            orch.agent_states = {"agent_a": _make_mock_agent_state()}
            orch._is_changedoc_enabled = MagicMock(return_value=False)
            # _save_agent_snapshot delegates to SnapshotManager; wire a real
            # collaborator so the spec-mocked orch routes to real logic.
            from massgen.orchestrator_collaborators import SnapshotManager

            orch._snapshot_manager = SnapshotManager(orch)

            await Orchestrator._save_agent_snapshot(
                orch,
                agent_id="agent_a",
                answer_content=answer_text,
                is_final=True,
            )

        answer_file = self.log_dir / "final" / "agent_a" / "answer.txt"
        assert answer_file.exists()
        assert answer_file.read_text() == answer_text

    @pytest.mark.asyncio
    async def test_resolved_path_also_replaced(self):
        """If resolved path differs from cwd string, both should be replaced."""
        # Use a symlink so resolved path differs
        real_workspace = self.tmp_path / "real_workspace"
        real_workspace.mkdir()
        symlink_workspace = self.tmp_path / "symlink_workspace"
        symlink_workspace.symlink_to(real_workspace)

        agent = _make_mock_agent(str(symlink_workspace))
        resolved = str(symlink_workspace.resolve())
        answer_text = f"Files at {symlink_workspace}/a.txt and also {resolved}/b.txt"

        from massgen.orchestrator import Orchestrator

        with patch(
            "massgen.orchestrator_collaborators.snapshot_manager.get_log_session_dir",
            return_value=self.log_dir,
        ):
            orch = MagicMock(spec=Orchestrator)
            orch.agents = {"agent_a": agent}
            orch.agent_states = {"agent_a": _make_mock_agent_state()}
            orch._is_changedoc_enabled = MagicMock(return_value=False)
            # _save_agent_snapshot delegates to SnapshotManager; wire a real
            # collaborator so the spec-mocked orch routes to real logic.
            from massgen.orchestrator_collaborators import SnapshotManager

            orch._snapshot_manager = SnapshotManager(orch)

            await Orchestrator._save_agent_snapshot(
                orch,
                agent_id="agent_a",
                answer_content=answer_text,
                is_final=True,
            )

        answer_file = self.log_dir / "final" / "agent_a" / "answer.txt"
        content = answer_file.read_text()
        expected_workspace = str(self.log_dir / "final" / "agent_a" / "workspace")

        assert str(symlink_workspace) not in content
        assert resolved not in content
        assert content.count(expected_workspace) == 2


# ---------------------------------------------------------------------------
# Tests: finalize_step_mode path normalization
# ---------------------------------------------------------------------------


class TestStepModeFinalAnswerNormalization:
    """Verify workspace paths in step mode final answer.txt are normalized."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path):
        self.tmp_path = tmp_path
        self.workspace = tmp_path / "workspace_step123"
        self.workspace.mkdir()
        self.log_dir = tmp_path / "log_session" / "turn_1" / "attempt_1"
        self.log_dir.mkdir(parents=True)

    def test_step_mode_normalizes_workspace_in_answer(self):
        """finalize_step_mode should normalize workspace paths in answer.txt."""
        import shutil

        from massgen.orchestrator import Orchestrator

        orch = MagicMock(spec=Orchestrator)
        orch._step_action_data = {
            "agent_id": "agent_a",
            "action": "new_answer",
            "answer_text": f"Result at {self.workspace}/result.md",
            "workspace_path": str(self.workspace),
        }
        orch.coordination_tracker = MagicMock()
        orch.save_metrics = MagicMock()

        with patch("massgen.orchestrator.shutil", shutil):
            Orchestrator.finalize_step_mode(orch, self.log_dir)

        answer_file = self.log_dir / "final" / "agent_a" / "answer.txt"
        assert answer_file.exists()
        content = answer_file.read_text()
        expected = str(self.log_dir / "final" / "agent_a" / "workspace")
        assert expected in content
        assert str(self.workspace) not in content
