"""Tests for CLI --spec and --execute-spec flags."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSpecFlagIntegration:
    """Tests for --spec CLI flag behavior in argument processing."""

    def test_spec_flag_prepends_spec_prefix_not_plan(self):
        """When --spec is active, spec prefix should be prepended (not plan prefix)."""
        from massgen.cli import (
            get_spec_creation_prompt_prefix,
            get_task_planning_prompt_prefix,
        )

        spec_prefix = get_spec_creation_prompt_prefix()
        plan_prefix = get_task_planning_prompt_prefix("dynamic")

        # Spec prefix references project_spec.json
        assert "project_spec.json" in spec_prefix
        # Plan prefix references project_plan.json
        assert "project_plan.json" in plan_prefix
        # They are different
        assert spec_prefix != plan_prefix

    def test_spec_prefix_includes_ears_notation(self):
        """Spec prefix should include EARS notation guidance."""
        from massgen.cli import get_spec_creation_prompt_prefix

        prefix = get_spec_creation_prompt_prefix()
        assert "EARS" in prefix
        assert "SHALL" in prefix

    def test_spec_prefix_includes_chunking_rules(self):
        """Spec prefix should include chunking rules for large specs."""
        from massgen.cli import get_spec_creation_prompt_prefix

        prefix = get_spec_creation_prompt_prefix()
        assert "chunk" in prefix.lower()

    def test_spec_question_prepending_logic(self):
        """Simulate the spec question prepending that happens in CLI main."""
        from massgen.cli import get_spec_creation_prompt_prefix

        question = "Build a REST API for user management"
        spec_prefix = get_spec_creation_prompt_prefix()
        result = spec_prefix + question
        assert result.startswith(spec_prefix)
        assert result.endswith(question)
        assert "project_spec.json" in result


class TestRunExecuteSpec:
    """Tests for run_execute_spec function."""

    @pytest.mark.asyncio
    async def test_run_execute_spec_loads_spec_session(self, tmp_path):
        """run_execute_spec should load a spec session and execute."""
        from massgen.cli import run_execute_spec

        # Create mock plan session with spec artifact
        plan_dir = tmp_path / ".massgen" / "plans" / "plan_20260115_173113_836955"
        frozen_dir = plan_dir / "frozen"
        frozen_dir.mkdir(parents=True)

        # Write spec.json
        spec_data = {
            "feature": "Test Feature",
            "overview": "A test spec",
            "requirements": [
                {
                    "id": "REQ-001",
                    "chunk": "C01_core",
                    "title": "Core requirement",
                    "priority": "P0",
                    "type": "functional",
                    "ears": "WHEN user submits THE SYSTEM SHALL save data",
                    "rationale": "Data persistence",
                    "verification": "Check database",
                    "depends_on": [],
                },
            ],
        }
        (frozen_dir / "spec.json").write_text(json.dumps(spec_data))

        config = {"agents": [{"agent_id": "agent1", "backend": "openai"}], "orchestrator": {}}

        with (
            patch("massgen.cli.plan_commands.resolve_plan_path") as mock_resolve,
            patch("massgen.cli.plan_commands._execute_plan_phase", new_callable=AsyncMock) as mock_execute,
        ):
            mock_session = MagicMock()
            mock_session.plan_dir = plan_dir
            mock_session.plan_id = "20260115_173113_836955"
            mock_session.frozen_dir = frozen_dir
            mock_resolve.return_value = mock_session

            mock_metadata = MagicMock()
            mock_metadata.created_at = "2026-01-15T17:31:13"
            mock_metadata.status = "finalized"
            mock_metadata.artifact_type = "spec"
            mock_session.load_metadata.return_value = mock_metadata

            mock_execute.return_value = ("Final answer", None)

            final_answer, session = await run_execute_spec(
                config=config,
                spec_path="latest",
            )

            assert final_answer == "Final answer"
            mock_resolve.assert_called_once_with("latest")
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_execute_spec_fails_without_spec_json(self, tmp_path):
        """run_execute_spec should fail if spec.json is missing."""
        from massgen.cli import run_execute_spec

        plan_dir = tmp_path / ".massgen" / "plans" / "plan_test"
        frozen_dir = plan_dir / "frozen"
        frozen_dir.mkdir(parents=True)

        # NO spec.json — should fail

        config = {"agents": [{"agent_id": "agent1", "backend": "openai"}], "orchestrator": {}}

        with patch("massgen.cli.plan_commands.resolve_plan_path") as mock_resolve:
            mock_session = MagicMock()
            mock_session.plan_dir = plan_dir
            mock_session.plan_id = "test"
            mock_session.frozen_dir = frozen_dir
            mock_resolve.return_value = mock_session

            mock_metadata = MagicMock()
            mock_metadata.created_at = "2026-01-15T17:31:13"
            mock_metadata.status = "finalized"
            mock_metadata.artifact_type = "spec"
            mock_session.load_metadata.return_value = mock_metadata

            with pytest.raises(SystemExit):
                await run_execute_spec(config=config, spec_path="latest")

    @pytest.mark.asyncio
    async def test_run_execute_spec_default_question_references_spec(self, tmp_path):
        """run_execute_spec default question should reference spec, not plan."""
        from massgen.cli import run_execute_spec

        plan_dir = tmp_path / ".massgen" / "plans" / "plan_test"
        frozen_dir = plan_dir / "frozen"
        frozen_dir.mkdir(parents=True)

        spec_data = {
            "feature": "Test",
            "overview": "Test",
            "requirements": [{"id": "REQ-001", "chunk": "C01_core", "title": "Test", "ears": "WHEN x SHALL y"}],
        }
        (frozen_dir / "spec.json").write_text(json.dumps(spec_data))

        config = {"agents": [{"agent_id": "agent1"}], "orchestrator": {}}

        with (
            patch("massgen.cli.plan_commands.resolve_plan_path") as mock_resolve,
            patch("massgen.cli.plan_commands._execute_plan_phase", new_callable=AsyncMock) as mock_execute,
        ):
            mock_session = MagicMock()
            mock_session.plan_dir = plan_dir
            mock_session.plan_id = "test"
            mock_session.frozen_dir = frozen_dir
            mock_resolve.return_value = mock_session

            mock_metadata = MagicMock()
            mock_metadata.artifact_type = "spec"
            mock_metadata.created_at = "2026-01-15T17:31:13"
            mock_metadata.status = "finalized"
            mock_session.load_metadata.return_value = mock_metadata

            mock_execute.return_value = ("Answer", None)

            await run_execute_spec(config=config, spec_path="latest")

            # Check the question passed to _execute_plan_phase
            call_kwargs = mock_execute.call_args
            # question is a keyword arg
            question = call_kwargs.kwargs.get("question")
            assert question is not None
            assert "spec" in question.lower()

    @pytest.mark.asyncio
    async def test_run_execute_spec_custom_question_override(self, tmp_path):
        """run_execute_spec should use custom question when provided."""
        from massgen.cli import run_execute_spec

        plan_dir = tmp_path / ".massgen" / "plans" / "plan_test"
        frozen_dir = plan_dir / "frozen"
        frozen_dir.mkdir(parents=True)

        spec_data = {
            "feature": "Test",
            "overview": "Test",
            "requirements": [{"id": "REQ-001", "chunk": "C01_core", "title": "Test", "ears": "WHEN x SHALL y"}],
        }
        (frozen_dir / "spec.json").write_text(json.dumps(spec_data))

        config = {"agents": [{"agent_id": "agent1"}], "orchestrator": {}}

        with (
            patch("massgen.cli.plan_commands.resolve_plan_path") as mock_resolve,
            patch("massgen.cli.plan_commands._execute_plan_phase", new_callable=AsyncMock) as mock_execute,
        ):
            mock_session = MagicMock()
            mock_session.plan_dir = plan_dir
            mock_session.plan_id = "test"
            mock_session.frozen_dir = frozen_dir
            mock_resolve.return_value = mock_session

            mock_metadata = MagicMock()
            mock_metadata.artifact_type = "spec"
            mock_metadata.created_at = "2026-01-15T17:31:13"
            mock_metadata.status = "finalized"
            mock_session.load_metadata.return_value = mock_metadata

            mock_execute.return_value = ("Answer", None)

            await run_execute_spec(
                config=config,
                spec_path="latest",
                question="Custom execution instruction",
            )

            call_kwargs = mock_execute.call_args
            question = call_kwargs.kwargs.get("question")
            assert question == "Custom execution instruction"

    @pytest.mark.asyncio
    async def test_run_execute_spec_prints_requirement_count(self, tmp_path):
        """run_execute_spec should print requirement count from spec."""
        from massgen.cli import run_execute_spec

        plan_dir = tmp_path / ".massgen" / "plans" / "plan_test"
        frozen_dir = plan_dir / "frozen"
        frozen_dir.mkdir(parents=True)

        spec_data = {
            "feature": "Test",
            "overview": "Test",
            "requirements": [
                {"id": "REQ-001", "chunk": "C01_core", "title": "Req 1", "ears": "WHEN x SHALL y"},
                {"id": "REQ-002", "chunk": "C01_core", "title": "Req 2", "ears": "WHEN a SHALL b"},
                {"id": "REQ-003", "chunk": "C02_api", "title": "Req 3", "ears": "WHEN c SHALL d"},
            ],
        }
        (frozen_dir / "spec.json").write_text(json.dumps(spec_data))

        config = {"agents": [{"agent_id": "agent1"}], "orchestrator": {}}

        with (
            patch("massgen.cli.plan_commands.resolve_plan_path") as mock_resolve,
            patch("massgen.cli.plan_commands._execute_plan_phase", new_callable=AsyncMock) as mock_execute,
        ):
            mock_session = MagicMock()
            mock_session.plan_dir = plan_dir
            mock_session.plan_id = "test"
            mock_session.frozen_dir = frozen_dir
            mock_resolve.return_value = mock_session

            mock_metadata = MagicMock()
            mock_metadata.artifact_type = "spec"
            mock_metadata.created_at = "2026-01-15T17:31:13"
            mock_metadata.status = "finalized"
            mock_session.load_metadata.return_value = mock_metadata

            mock_execute.return_value = ("Answer", None)

            # Should not raise — just verify it runs successfully
            final_answer, _ = await run_execute_spec(config=config, spec_path="latest")
            assert final_answer == "Answer"
