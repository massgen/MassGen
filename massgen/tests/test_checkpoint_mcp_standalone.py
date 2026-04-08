"""Tests for the standalone checkpoint MCP server (objective mode).

TDD: these tests are written before the implementation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest


def _setup_session(mod: Any, tmp_path: Path, **overrides: Any) -> None:
    """Set up module session state for tests that bypass _init_impl."""
    mod._session.clear()
    session_dir = tmp_path / "session"
    session_dir.mkdir(exist_ok=True)
    mod._session_dir = session_dir
    mod._checkpoint_counter = 0

    trajectory = tmp_path / "trajectory.log"
    if not trajectory.exists():
        trajectory.write_text("data")

    defaults = {
        "workspace_dir": str(tmp_path),
        "trajectory_path": str(trajectory),
        "available_tools": [],
        "config_dict": {
            "agents": [
                {
                    "id": "p1",
                    "backend": {"type": "claude", "model": "claude-sonnet-4-20250514"},
                },
            ],
            "orchestrator": {"coordination": {"max_rounds": 1}},
        },
        "safety_policy": ["rule"],
    }
    defaults.update(overrides)
    mod._session.update(defaults)


# ---------------------------------------------------------------------------
# Test: merge_criteria
# ---------------------------------------------------------------------------


class TestMergeCriteria:
    """merge_criteria merges global policy with per-call eval_criteria."""

    def test_policy_only_when_no_eval_criteria(self):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            DEFAULT_SAFETY_POLICY,
            merge_criteria,
        )

        result = merge_criteria(DEFAULT_SAFETY_POLICY, None)
        assert result == DEFAULT_SAFETY_POLICY

    def test_eval_criteria_augments_policy(self):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            DEFAULT_SAFETY_POLICY,
            merge_criteria,
        )

        extra = ["Migration must be backward-compatible"]
        result = merge_criteria(DEFAULT_SAFETY_POLICY, extra)
        # All global policy entries present
        for entry in DEFAULT_SAFETY_POLICY:
            assert entry in result
        # Extra criteria present
        assert "Migration must be backward-compatible" in result

    def test_eval_criteria_never_removes_global(self):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            merge_criteria,
        )

        policy = ["Rule A", "Rule B"]
        result = merge_criteria(policy, ["Rule C"])
        assert "Rule A" in result
        assert "Rule B" in result
        assert "Rule C" in result

    def test_deduplicates(self):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            merge_criteria,
        )

        policy = ["Rule A", "Rule B"]
        result = merge_criteria(policy, ["Rule A", "Rule C"])
        assert result.count("Rule A") == 1

    def test_empty_eval_criteria_returns_policy(self):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            merge_criteria,
        )

        policy = ["Rule A"]
        result = merge_criteria(policy, [])
        assert result == ["Rule A"]


# ---------------------------------------------------------------------------
# Test: validate_plan_output
# ---------------------------------------------------------------------------


class TestOutputSchemaValidation:
    """validate_plan_output checks the plan structure."""

    def test_valid_minimal_plan(self):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            validate_plan_output,
        )

        raw = {
            "plan": [
                {"step": 1, "description": "Run tests"},
            ],
        }
        result = validate_plan_output(raw)
        assert len(result["plan"]) == 1

    def test_valid_plan_with_all_fields(self):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            validate_plan_output,
        )

        raw = {
            "plan": [
                {
                    "step": 1,
                    "description": "Take backup",
                    "constraints": ["Do not modify schema"],
                    "approved_action": {
                        "goal_id": "backup",
                        "tool": "Bash",
                        "args": {"command": "pg_dump db > backup.sql"},
                    },
                    "recovery": {
                        "if": "backup fails",
                        "then": "recheckpoint",
                        "else": "proceed",
                    },
                },
            ],
        }
        result = validate_plan_output(raw)
        assert result["plan"][0]["approved_action"]["tool"] == "Bash"

    def test_rejects_missing_plan(self):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            validate_plan_output,
        )

        with pytest.raises(ValueError, match="plan"):
            validate_plan_output({})

    def test_rejects_step_without_description(self):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            validate_plan_output,
        )

        raw = {"plan": [{"step": 1}]}
        with pytest.raises(ValueError, match="description"):
            validate_plan_output(raw)

    def test_rejects_invalid_recovery_terminal(self):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            validate_plan_output,
        )

        raw = {
            "plan": [
                {
                    "step": 1,
                    "description": "Do thing",
                    "recovery": {
                        "if": "fails",
                        "then": "retry",  # invalid terminal
                    },
                },
            ],
        }
        with pytest.raises(ValueError, match="terminal"):
            validate_plan_output(raw)

    def test_valid_nested_recovery(self):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            validate_plan_output,
        )

        raw = {
            "plan": [
                {
                    "step": 1,
                    "description": "Deploy",
                    "recovery": {
                        "if": "health check fails",
                        "then": {
                            "if": "rollback available",
                            "then": "proceed",
                            "else": "refuse",
                        },
                        "else": "proceed",
                    },
                },
            ],
        }
        result = validate_plan_output(raw)
        recovery = result["plan"][0]["recovery"]
        assert isinstance(recovery["then"], dict)
        assert recovery["then"]["then"] == "proceed"

    def test_rejects_plan_not_a_list(self):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            validate_plan_output,
        )

        with pytest.raises(ValueError, match="list"):
            validate_plan_output({"plan": "not a list"})

    def test_rejects_empty_plan(self):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            validate_plan_output,
        )

        with pytest.raises(ValueError, match="empty"):
            validate_plan_output({"plan": []})

    def test_rejects_old_block_terminal(self):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            validate_plan_output,
        )

        raw = {
            "plan": [
                {
                    "step": 1,
                    "description": "Deploy",
                    "recovery": {"if": "fails", "then": "block"},
                },
            ],
        }
        with pytest.raises(ValueError, match="terminal"):
            validate_plan_output(raw)

    def test_validate_plan_script_pass(self, tmp_path):
        import subprocess

        plan = {
            "plan": [
                {
                    "step": 1,
                    "description": "Test step",
                    "recovery": {
                        "if": "fails",
                        "then": "refuse",
                        "else": "proceed",
                    },
                },
            ],
        }
        plan_file = tmp_path / "checkpoint_result.json"
        plan_file.write_text(json.dumps(plan))

        script = Path(__file__).parent.parent / "mcp_tools" / "standalone" / "validate_plan.py"
        result = subprocess.run(
            [sys.executable, str(script), str(plan_file)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "PASS" in result.stdout

    def test_validate_plan_script_fail_annotated_terminal(self, tmp_path):
        import subprocess

        plan = {
            "plan": [
                {
                    "step": 1,
                    "description": "Deploy",
                    "recovery": {
                        "if": "fails",
                        "then": "refuse — do not send emails",
                    },
                },
            ],
        }
        plan_file = tmp_path / "checkpoint_result.json"
        plan_file.write_text(json.dumps(plan))

        script = Path(__file__).parent.parent / "mcp_tools" / "standalone" / "validate_plan.py"
        result = subprocess.run(
            [sys.executable, str(script), str(plan_file)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "terminal" in result.stderr.lower()


# ---------------------------------------------------------------------------
# Test: extract_json_from_response
# ---------------------------------------------------------------------------


class TestExtractJson:
    """extract_json_from_response handles various LLM output formats."""

    def test_bare_json(self):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            extract_json_from_response,
        )

        text = '{"plan": [{"step": 1, "description": "test"}]}'
        result = extract_json_from_response(text)
        assert result["plan"][0]["step"] == 1

    def test_json_in_markdown_fence(self):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            extract_json_from_response,
        )

        text = '```json\n{"plan": [{"step": 1, "description": "test"}]}\n```'
        result = extract_json_from_response(text)
        assert result["plan"][0]["step"] == 1

    def test_json_with_preamble(self):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            extract_json_from_response,
        )

        text = "Here is the safety plan:\n\n" '{"plan": [{"step": 1, "description": "test"}]}'
        result = extract_json_from_response(text)
        assert result["plan"][0]["step"] == 1

    def test_raises_on_no_json(self):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            extract_json_from_response,
        )

        with pytest.raises(ValueError, match="JSON"):
            extract_json_from_response("no json here")

    def test_json_with_trailing_text(self):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            extract_json_from_response,
        )

        text = '{"plan": [{"step": 1, "description": "test"}]}\n\n' "That concludes the plan."
        result = extract_json_from_response(text)
        assert result["plan"][0]["description"] == "test"


# ---------------------------------------------------------------------------
# Test: build_objective_prompt
# ---------------------------------------------------------------------------


class TestBuildObjectivePrompt:
    """build_objective_prompt assembles the system prompt for checkpoint agents."""

    def test_includes_objective(self):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            build_objective_prompt,
        )

        prompt = build_objective_prompt(
            objective="Deploy to production",
            available_tools=[{"name": "Bash", "description": "Run commands"}],
            criteria=["No downtime"],
            workspace_dir="/tmp/test-workspace",
        )
        assert "Deploy to production" in prompt

    def test_includes_available_tools(self):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            build_objective_prompt,
        )

        prompt = build_objective_prompt(
            objective="Deploy",
            available_tools=[
                {"name": "Bash", "description": "Run commands"},
                {"name": "Read", "description": "Read files"},
            ],
            criteria=["Be safe"],
            workspace_dir="/tmp/test-workspace",
        )
        assert "Bash" in prompt
        assert "Read" in prompt

    def test_includes_criteria(self):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            build_objective_prompt,
        )

        prompt = build_objective_prompt(
            objective="Deploy",
            available_tools=[],
            criteria=["No downtime", "Run tests first"],
            workspace_dir="/tmp/test-workspace",
        )
        assert "No downtime" in prompt
        assert "Run tests first" in prompt

    def test_references_trajectory_file(self):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            TRAJECTORY_FILENAME,
            build_objective_prompt,
        )

        prompt = build_objective_prompt(
            objective="Deploy",
            available_tools=[],
            criteria=["Be safe"],
            workspace_dir="/tmp/test-workspace",
        )
        assert TRAJECTORY_FILENAME in prompt

    def test_includes_action_goals_when_provided(self):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            build_objective_prompt,
        )

        prompt = build_objective_prompt(
            objective="Deploy",
            available_tools=[],
            criteria=["Be safe"],
            workspace_dir="/tmp/test-workspace",
            action_goals=[
                {"id": "deploy", "goal": "Deploy to Vercel production"},
            ],
        )
        assert "deploy" in prompt
        assert "Deploy to Vercel production" in prompt

    def test_omits_action_goals_when_none(self):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            build_objective_prompt,
        )

        prompt = build_objective_prompt(
            objective="Deploy",
            available_tools=[],
            criteria=["Be safe"],
            workspace_dir="/tmp/test-workspace",
            action_goals=None,
        )
        assert "action_goals" not in prompt.lower() or "Action Goals" not in prompt

    def test_references_result_filename(self):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            RESULT_FILENAME,
            build_objective_prompt,
        )

        prompt = build_objective_prompt(
            objective="Deploy",
            available_tools=[],
            criteria=["Be safe"],
            workspace_dir="/tmp/test-workspace",
        )
        assert RESULT_FILENAME in prompt


# ---------------------------------------------------------------------------
# Test: generate_objective_config
# ---------------------------------------------------------------------------


class TestGenerateObjectiveConfig:
    """generate_objective_config builds a subprocess config for objective mode."""

    def _base_config(self) -> dict[str, Any]:
        return {
            "agents": [
                {
                    "id": "planner_1",
                    "backend": {
                        "type": "claude",
                        "model": "claude-sonnet-4-20250514",
                        "mcp_servers": [
                            {"name": "checkpoint", "command": "x"},
                            {"name": "filesystem", "command": "y"},
                        ],
                    },
                },
            ],
            "orchestrator": {
                "coordination": {"max_rounds": 3},
            },
        }

    def test_returns_valid_dict(self, tmp_path: Path):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            generate_objective_config,
        )

        config = generate_objective_config(
            self._base_config(),
            tmp_path,
            "You are a planner.",
        )
        assert isinstance(config, dict)
        assert "agents" in config or "agent" in config

    def test_injects_workspace_paths(self, tmp_path: Path):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            generate_objective_config,
        )

        config = generate_objective_config(
            self._base_config(),
            tmp_path,
            "You are a planner.",
        )
        assert str(tmp_path) in config["orchestrator"]["snapshot_storage"]

    def test_injects_system_message(self, tmp_path: Path):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            generate_objective_config,
        )

        prompt = "You are a safety planner."
        config = generate_objective_config(
            self._base_config(),
            tmp_path,
            prompt,
        )
        agents = config.get("agents", [config.get("agent")])
        for agent in agents:
            assert agent["system_message"] == prompt

    def test_disables_checkpoint_recursion(self, tmp_path: Path):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            generate_objective_config,
        )

        config = generate_objective_config(
            self._base_config(),
            tmp_path,
            "prompt",
        )
        coord = config["orchestrator"]["coordination"]
        assert coord["checkpoint_enabled"] is False

    def test_removes_checkpoint_mcp_servers(self, tmp_path: Path):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            generate_objective_config,
        )

        config = generate_objective_config(
            self._base_config(),
            tmp_path,
            "prompt",
        )
        agents = config.get("agents", [config.get("agent")])
        for agent in agents:
            mcp_names = [s.get("name") for s in agent.get("backend", {}).get("mcp_servers", [])]
            assert "checkpoint" not in mcp_names
            assert "massgen_checkpoint" not in mcp_names
            # filesystem should still be there
            assert "filesystem" in mcp_names


# ---------------------------------------------------------------------------
# Test: Session state + init
# ---------------------------------------------------------------------------


class TestSessionState:
    """_init_impl stores session context for subsequent checkpoint calls."""

    @pytest.mark.asyncio
    async def test_init_stores_workspace_dir(self, tmp_path: Path):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            _init_impl,
            _session,
        )

        _session.clear()
        trajectory = tmp_path / "trajectory.log"
        trajectory.write_text("some trajectory")

        result_str = await _init_impl(
            workspace_dir=str(tmp_path),
            trajectory_path=str(trajectory),
            available_tools=[{"name": "Bash", "description": "Run commands"}],
        )
        result = json.loads(result_str)
        assert result["status"] == "ok"
        assert _session["workspace_dir"] == str(tmp_path)

    @pytest.mark.asyncio
    async def test_init_stores_trajectory_path(self, tmp_path: Path):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            _init_impl,
            _session,
        )

        _session.clear()
        trajectory = tmp_path / "trajectory.log"
        trajectory.write_text("data")

        await _init_impl(
            workspace_dir=str(tmp_path),
            trajectory_path=str(trajectory),
            available_tools=[],
        )
        assert _session["trajectory_path"] == str(trajectory)

    @pytest.mark.asyncio
    async def test_init_stores_available_tools(self, tmp_path: Path):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            _init_impl,
            _session,
        )

        _session.clear()
        trajectory = tmp_path / "trajectory.log"
        trajectory.write_text("data")

        tools = [{"name": "Bash", "description": "Run commands"}]
        await _init_impl(
            workspace_dir=str(tmp_path),
            trajectory_path=str(trajectory),
            available_tools=tools,
        )
        assert _session["available_tools"] == tools

    @pytest.mark.asyncio
    async def test_init_returns_ok(self, tmp_path: Path):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            _init_impl,
            _session,
        )

        _session.clear()
        trajectory = tmp_path / "trajectory.log"
        trajectory.write_text("data")

        result_str = await _init_impl(
            workspace_dir=str(tmp_path),
            trajectory_path=str(trajectory),
            available_tools=[],
        )
        result = json.loads(result_str)
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_init_custom_safety_policy_merges(self, tmp_path: Path):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            DEFAULT_SAFETY_POLICY,
            _init_impl,
            _session,
        )

        _session.clear()
        trajectory = tmp_path / "trajectory.log"
        trajectory.write_text("data")

        custom = ["Custom rule"]
        await _init_impl(
            workspace_dir=str(tmp_path),
            trajectory_path=str(trajectory),
            available_tools=[],
            safety_policy=custom,
        )
        # Should contain both default and custom
        for entry in DEFAULT_SAFETY_POLICY:
            assert entry in _session["safety_policy"]
        assert "Custom rule" in _session["safety_policy"]

    @pytest.mark.asyncio
    async def test_init_default_safety_policy(self, tmp_path: Path):
        from massgen.mcp_tools.standalone.checkpoint_mcp_server import (
            DEFAULT_SAFETY_POLICY,
            _init_impl,
            _session,
        )

        _session.clear()
        trajectory = tmp_path / "trajectory.log"
        trajectory.write_text("data")

        await _init_impl(
            workspace_dir=str(tmp_path),
            trajectory_path=str(trajectory),
            available_tools=[],
        )
        assert _session["safety_policy"] == DEFAULT_SAFETY_POLICY


# ---------------------------------------------------------------------------
# Test: checkpoint tool validation + mode dispatch
# ---------------------------------------------------------------------------


class TestCheckpointToolValidation:
    """Validate checkpoint tool parameter handling."""

    @pytest.mark.asyncio
    async def test_checkpoint_without_init_returns_error(self):
        import massgen.mcp_tools.standalone.checkpoint_mcp_server as mod

        mod._session.clear()
        mod._session_dir = None
        result_str = await mod._checkpoint_impl(objective="Deploy to prod")
        result = json.loads(result_str)
        assert result["status"] == "error"
        assert "init" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_requires_objective(self, tmp_path: Path):
        import massgen.mcp_tools.standalone.checkpoint_mcp_server as mod

        _setup_session(mod, tmp_path)
        mod._session.update(
            {
                "config_dict": {"agents": []},
            },
        )
        result_str = await mod._checkpoint_impl(objective="")
        result = json.loads(result_str)
        assert result["status"] == "error"
        assert "objective" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_accepts_minimal_params(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Minimal params (just objective) should not error on validation."""
        from massgen.mcp_tools.standalone import checkpoint_mcp_server as mod

        _setup_session(mod, tmp_path)

        # Mock subprocess to isolate validation testing
        async def mock_run_subrun(
            prompt,
            config_path,
            workspace,
            timeout,
            answer_file=None,
        ):
            final_ws = workspace / ".massgen" / "massgen_logs" / "log_test" / "turn_1" / "attempt_1" / "final" / "agent_a" / "workspace"
            final_ws.mkdir(parents=True, exist_ok=True)
            result_file = final_ws / mod.RESULT_FILENAME
            result_file.write_text(
                json.dumps({"plan": [{"step": 1, "description": "Do it"}]}),
            )
            return {"success": True, "output": "", "execution_time_seconds": 0.1}

        monkeypatch.setattr(
            "massgen.mcp_tools.standalone.checkpoint_mcp_server.run_massgen_subrun",
            mock_run_subrun,
        )

        result_str = await mod._checkpoint_impl(objective="Deploy to prod")
        result = json.loads(result_str)
        assert result["status"] == "ok"
        assert "plan" in result


# ---------------------------------------------------------------------------
# Test: End-to-end with mocked subprocess
# ---------------------------------------------------------------------------


class TestCheckpointEndToEnd:
    """End-to-end tests with mocked subprocess."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_checkpoint_returns_structured_plan(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        from massgen.mcp_tools.standalone import checkpoint_mcp_server as mod

        trajectory = tmp_path / "trajectory.log"
        trajectory.write_text("Agent called Bash to run tests. Tests passed.")
        _setup_session(
            mod,
            tmp_path,
            available_tools=[{"name": "Bash", "description": "Run commands"}],
            safety_policy=["Never deploy without tests"],
        )

        # Mock run_massgen_subrun to write checkpoint_result.json and return success
        plan_data = {
            "plan": [
                {
                    "step": 1,
                    "description": "Run test suite",
                    "constraints": ["Do not modify test files"],
                    "recovery": {
                        "if": "tests fail",
                        "then": "recheckpoint",
                        "else": "proceed",
                    },
                },
                {
                    "step": 2,
                    "description": "Deploy to production",
                    "approved_action": {
                        "goal_id": "deploy",
                        "tool": "Bash",
                        "args": {"command": "vercel --prod"},
                    },
                },
            ],
        }

        async def mock_run_subrun(
            prompt,
            config_path,
            workspace,
            timeout,
            answer_file=None,
        ):
            # Write the result file in the workspace
            final_ws = workspace / ".massgen" / "massgen_logs" / "log_test" / "turn_1" / "attempt_1" / "final" / "agent_a" / "workspace"
            final_ws.mkdir(parents=True, exist_ok=True)
            result_file = final_ws / mod.RESULT_FILENAME
            result_file.write_text(json.dumps(plan_data))
            return {"success": True, "output": "", "execution_time_seconds": 1.0}

        monkeypatch.setattr(
            "massgen.mcp_tools.standalone.checkpoint_mcp_server.run_massgen_subrun",
            mock_run_subrun,
        )

        result_str = await mod._checkpoint_impl(
            objective="Deploy dashboard to production",
            action_goals=[{"id": "deploy", "goal": "Deploy to Vercel"}],
            eval_criteria=["Zero downtime deployment"],
        )
        result = json.loads(result_str)
        assert result["status"] == "ok"
        assert len(result["plan"]) == 2
        assert result["plan"][0]["description"] == "Run test suite"
        assert result["plan"][1]["approved_action"]["tool"] == "Bash"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_checkpoint_subprocess_failure(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        from massgen.mcp_tools.standalone import checkpoint_mcp_server as mod

        _setup_session(mod, tmp_path)

        async def mock_run_subrun(
            prompt,
            config_path,
            workspace,
            timeout,
            answer_file=None,
        ):
            return {
                "success": False,
                "error": "Process crashed",
                "execution_time_seconds": 0.5,
            }

        monkeypatch.setattr(
            "massgen.mcp_tools.standalone.checkpoint_mcp_server.run_massgen_subrun",
            mock_run_subrun,
        )

        result_str = await mod._checkpoint_impl(objective="Deploy")
        result = json.loads(result_str)
        assert result["status"] == "error"
        assert "crashed" in result["error"].lower() or "failed" in result["error"].lower()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_checkpoint_invalid_output(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        from massgen.mcp_tools.standalone import checkpoint_mcp_server as mod

        _setup_session(mod, tmp_path)

        async def mock_run_subrun(
            prompt,
            config_path,
            workspace,
            timeout,
            answer_file=None,
        ):
            # Write invalid result (no plan field)
            final_ws = workspace / ".massgen" / "massgen_logs" / "log_test" / "turn_1" / "attempt_1" / "final" / "agent_a" / "workspace"
            final_ws.mkdir(parents=True, exist_ok=True)
            result_file = final_ws / mod.RESULT_FILENAME
            result_file.write_text(json.dumps({"bad": "data"}))
            return {"success": True, "output": "", "execution_time_seconds": 1.0}

        monkeypatch.setattr(
            "massgen.mcp_tools.standalone.checkpoint_mcp_server.run_massgen_subrun",
            mock_run_subrun,
        )

        result_str = await mod._checkpoint_impl(objective="Deploy")
        result = json.loads(result_str)
        assert result["status"] == "error"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_trajectory_copied_to_workspace(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Verify trajectory file is copied into subprocess workspace."""
        from massgen.mcp_tools.standalone import checkpoint_mcp_server as mod

        trajectory = tmp_path / "trajectory.log"
        trajectory.write_text("Agent did things")
        _setup_session(mod, tmp_path)

        captured_workspace = {}

        async def mock_run_subrun(
            prompt,
            config_path,
            workspace,
            timeout,
            answer_file=None,
        ):
            # Check that trajectory was copied
            traj_in_workspace = workspace / ".checkpoint" / "trajectory.log"
            captured_workspace["trajectory_exists"] = traj_in_workspace.exists()
            captured_workspace["trajectory_content"] = traj_in_workspace.read_text() if traj_in_workspace.exists() else ""
            # Write valid result
            final_ws = workspace / ".massgen" / "massgen_logs" / "log_test" / "turn_1" / "attempt_1" / "final" / "agent_a" / "workspace"
            final_ws.mkdir(parents=True, exist_ok=True)
            result_file = final_ws / mod.RESULT_FILENAME
            result_file.write_text(
                json.dumps({"plan": [{"step": 1, "description": "Do it"}]}),
            )
            return {"success": True, "output": "", "execution_time_seconds": 1.0}

        monkeypatch.setattr(
            "massgen.mcp_tools.standalone.checkpoint_mcp_server.run_massgen_subrun",
            mock_run_subrun,
        )

        await mod._checkpoint_impl(objective="Deploy")
        assert captured_workspace["trajectory_exists"] is True
        assert captured_workspace["trajectory_content"] == "Agent did things"
