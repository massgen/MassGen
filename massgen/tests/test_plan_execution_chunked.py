"""Unit tests for chunked plan execution helpers."""

import json
from pathlib import Path

import pytest

from massgen.plan_execution import (
    PlanValidationError,
    initialize_chunk_execution_state,
    setup_agent_workspaces_for_execution,
    validate_chunked_plan,
)
from massgen.plan_storage import PlanStorage


class _DummyFilesystemManager:
    def __init__(self, cwd: Path) -> None:
        self.cwd = str(cwd)
        self.path_permission_manager = None
        self.agent_temporary_workspace = None
        self.enable_code_based_tools = False

    def get_current_workspace(self) -> str:
        return self.cwd

    def setup_orchestration_paths(self, **kwargs) -> None:
        return None

    def setup_massgen_skill_directories(self, **kwargs) -> None:
        return None

    def setup_memory_directories(self) -> None:
        return None

    def update_backend_mcp_config(self, _backend_config) -> None:
        return None


class _DummyBackend:
    def __init__(self, cwd: Path) -> None:
        self.filesystem_manager = _DummyFilesystemManager(cwd)
        self.config = {}


class _DummyAgent:
    def __init__(self, cwd: Path) -> None:
        self.agent_id = "agent_a"
        self.backend = _DummyBackend(cwd)


@pytest.fixture
def temp_plans_dir(monkeypatch, tmp_path):
    temp_path = tmp_path / ".massgen" / "plans"
    temp_path.mkdir(parents=True)
    monkeypatch.setattr("massgen.plan_storage.PLANS_DIR", temp_path)
    yield temp_path


def _write_frozen_plan(session, plan_data):
    session.frozen_dir.mkdir(parents=True, exist_ok=True)
    (session.frozen_dir / "plan.json").write_text(json.dumps(plan_data, indent=2))


def test_validate_chunked_plan_requires_chunk_labels():
    plan_data = {
        "tasks": [
            {"id": "T001", "description": "Task with chunk", "chunk": "C01_setup"},
            {"id": "T002", "description": "Task missing chunk"},
        ],
    }

    with pytest.raises(PlanValidationError, match="missing non-empty 'chunk'"):
        validate_chunked_plan(plan_data)


def test_validate_chunked_plan_rejects_future_chunk_dependencies():
    plan_data = {
        "tasks": [
            {"id": "T001", "description": "API", "chunk": "C02_api", "depends_on": ["T002"]},
            {"id": "T002", "description": "Foundation", "chunk": "C01_foundation"},
        ],
    }

    with pytest.raises(PlanValidationError, match="depends on future chunk"):
        validate_chunked_plan(plan_data)


def test_initialize_chunk_execution_state_sets_current_chunk(temp_plans_dir):
    storage = PlanStorage()
    session = storage.create_plan("planning_session", "/tmp/logs")
    _write_frozen_plan(
        session,
        {
            "tasks": [
                {"id": "T001", "description": "Foundation", "chunk": "C01_foundation"},
                {"id": "T002", "description": "Backend", "chunk": "C02_backend", "depends_on": ["T001"]},
            ],
        },
    )

    metadata = initialize_chunk_execution_state(session)
    assert metadata.chunk_order == ["C01_foundation", "C02_backend"]
    assert metadata.current_chunk == "C01_foundation"
    assert metadata.execution_mode == "chunked_by_planner_v1"


def test_initialize_chunk_execution_state_advances_past_completed_chunk(temp_plans_dir):
    storage = PlanStorage()
    session = storage.create_plan("planning_session", "/tmp/logs")
    _write_frozen_plan(
        session,
        {
            "tasks": [
                {"id": "T001", "description": "Foundation", "chunk": "C01_foundation"},
                {"id": "T002", "description": "Backend", "chunk": "C02_backend", "depends_on": ["T001"]},
            ],
        },
    )

    metadata = session.load_metadata()
    metadata.completed_chunks = ["C01_foundation"]
    metadata.current_chunk = "C01_foundation"
    session.save_metadata(metadata)

    updated = initialize_chunk_execution_state(session)
    assert updated.current_chunk == "C02_backend"


def test_setup_agent_workspaces_writes_chunk_only_operational_plan(
    temp_plans_dir,
    tmp_path,
):
    storage = PlanStorage()
    session = storage.create_plan("planning_session", "/tmp/logs")
    _write_frozen_plan(
        session,
        {
            "tasks": [
                {"id": "T001", "description": "Foundation", "chunk": "C01_foundation"},
                {"id": "T002", "description": "API", "chunk": "C02_api", "depends_on": ["T001"]},
                {"id": "T003", "description": "UI", "chunk": "C03_ui", "depends_on": ["T002"]},
            ],
        },
    )

    # Also include a planning document to verify doc copy.
    (session.frozen_dir / "design.md").write_text("# design")

    agent_workspace = tmp_path / "agent_workspace"
    agent_workspace.mkdir(parents=True)
    agents = {"agent_a": _DummyAgent(agent_workspace)}

    copied_count = setup_agent_workspaces_for_execution(
        agents,
        session,
        active_chunk="C02_api",
    )
    assert copied_count == 1

    operational_plan = json.loads((agent_workspace / "tasks" / "plan.json").read_text())
    assert operational_plan["execution_scope"]["active_chunk"] == "C02_api"
    assert [task["id"] for task in operational_plan["tasks"]] == ["T002"]

    full_plan_reference = agent_workspace / "planning_docs" / "full_plan.json"
    assert full_plan_reference.exists()
    full_plan = json.loads(full_plan_reference.read_text())
    assert len(full_plan["tasks"]) == 3


def test_orchestrator_clear_workspace_reseeds_plan_execution_artifacts(
    temp_plans_dir,
    tmp_path,
):
    from massgen.agent_config import AgentConfig
    from massgen.orchestrator import Orchestrator

    storage = PlanStorage()
    session = storage.create_plan("planning_session", "/tmp/logs")
    _write_frozen_plan(
        session,
        {
            "tasks": [
                {"id": "T001", "description": "Setup", "chunk": "C01_setup"},
                {"id": "T002", "description": "Build", "chunk": "C02_build", "depends_on": ["T001"]},
            ],
        },
    )

    (session.frozen_dir / "requirements.md").write_text("# requirements")

    agent_workspace = tmp_path / "agent_workspace"
    agent_workspace.mkdir(parents=True)
    (agent_workspace / "stale.txt").write_text("old")

    agents = {"agent_a": _DummyAgent(agent_workspace)}
    orchestrator = Orchestrator(
        agents=agents,
        config=AgentConfig(),
        plan_session_id=session.plan_id,
    )

    orchestrator._clear_agent_workspaces()

    assert not (agent_workspace / "stale.txt").exists()

    operational_plan_path = agent_workspace / "tasks" / "plan.json"
    assert operational_plan_path.exists()
    operational_plan = json.loads(operational_plan_path.read_text())
    assert operational_plan["execution_scope"]["active_chunk"] == "C01_setup"
    assert [task["id"] for task in operational_plan["tasks"]] == ["T001"]

    assert (agent_workspace / "planning_docs" / "requirements.md").exists()
    assert (agent_workspace / "planning_docs" / "full_plan.json").exists()


def test_orchestrator_init_seeds_plan_execution_artifacts(
    temp_plans_dir,
    tmp_path,
):
    from massgen.agent_config import AgentConfig
    from massgen.orchestrator import Orchestrator

    storage = PlanStorage()
    session = storage.create_plan("planning_session", "/tmp/logs")
    _write_frozen_plan(
        session,
        {
            "tasks": [
                {"id": "T001", "description": "Setup", "chunk": "C01_setup"},
                {"id": "T002", "description": "Build", "chunk": "C02_build", "depends_on": ["T001"]},
            ],
        },
    )

    (session.frozen_dir / "requirements.md").write_text("# requirements")

    agent_workspace = tmp_path / "agent_workspace"
    agent_workspace.mkdir(parents=True)

    agents = {"agent_a": _DummyAgent(agent_workspace)}
    Orchestrator(
        agents=agents,
        config=AgentConfig(),
        plan_session_id=session.plan_id,
    )

    operational_plan_path = agent_workspace / "tasks" / "plan.json"
    assert operational_plan_path.exists()
    operational_plan = json.loads(operational_plan_path.read_text())
    assert operational_plan["execution_scope"]["active_chunk"] == "C01_setup"
    assert [task["id"] for task in operational_plan["tasks"]] == ["T001"]

    assert (agent_workspace / "planning_docs" / "requirements.md").exists()
    assert (agent_workspace / "planning_docs" / "full_plan.json").exists()


def test_orchestrator_execute_mode_restores_previous_workspace_and_archives_prior_chunk_plan(
    temp_plans_dir,
    tmp_path,
):
    from massgen.agent_config import AgentConfig
    from massgen.orchestrator import Orchestrator

    storage = PlanStorage()
    session = storage.create_plan("planning_session", "/tmp/logs")
    _write_frozen_plan(
        session,
        {
            "tasks": [
                {"id": "T001", "description": "Setup", "chunk": "C01_setup"},
                {"id": "T002", "description": "Build", "chunk": "C02_build", "depends_on": ["T001"]},
            ],
        },
    )

    metadata = session.load_metadata()
    metadata.execution_mode = "chunked_by_planner_v1"
    metadata.chunk_order = ["C01_setup", "C02_build"]
    metadata.completed_chunks = ["C01_setup"]
    metadata.current_chunk = "C02_build"
    session.save_metadata(metadata)

    previous_workspace = tmp_path / "previous_turn_workspace"
    previous_workspace.mkdir(parents=True)
    (previous_workspace / "site").mkdir(parents=True)
    (previous_workspace / "site" / "index.html").write_text("<h1>from previous chunk</h1>")
    (previous_workspace / "tasks").mkdir(parents=True)
    (previous_workspace / "tasks" / "plan.json").write_text(
        json.dumps(
            {
                "tasks": [{"id": "T001", "chunk": "C01_setup", "status": "verified"}],
                "execution_scope": {"active_chunk": "C01_setup"},
            },
            indent=2,
        ),
    )

    agent_workspace = tmp_path / "agent_workspace"
    agent_workspace.mkdir(parents=True)
    (agent_workspace / "stale.txt").write_text("old")

    agents = {"agent_a": _DummyAgent(agent_workspace)}
    orchestrator = Orchestrator(
        agents=agents,
        config=AgentConfig(),
        previous_turns=[{"path": str(previous_workspace)}],
        plan_session_id=session.plan_id,
    )

    orchestrator._clear_agent_workspaces()

    assert not (agent_workspace / "stale.txt").exists()
    assert (agent_workspace / "site" / "index.html").read_text() == "<h1>from previous chunk</h1>"

    archived_plan = agent_workspace / "tasks" / "tasks_c01.json"
    assert archived_plan.exists()
    archived_payload = json.loads(archived_plan.read_text())
    assert archived_payload.get("execution_scope", {}).get("active_chunk") == "C01_setup"

    active_plan = json.loads((agent_workspace / "tasks" / "plan.json").read_text())
    assert active_plan.get("execution_scope", {}).get("active_chunk") == "C02_build"
    assert [task["id"] for task in active_plan.get("tasks", [])] == ["T002"]


@pytest.mark.asyncio
async def test_execute_plan_phase_timeout_skips_chunk_and_advances_to_next_chunk(
    temp_plans_dir,
    tmp_path,
    monkeypatch,
):
    """Chunk timeout should be recorded then execution should continue to next chunk.

    Regression guard:
    A timed-out chunk must not abort the whole execution run when later chunks
    can still be attempted.
    """
    import massgen.cli as cli_module

    storage = PlanStorage()
    session = storage.create_plan("planning_session", "/tmp/logs")
    _write_frozen_plan(
        session,
        {
            "tasks": [
                {"id": "T001", "description": "Core playable", "chunk": "C01_build"},
                {
                    "id": "T002",
                    "description": "UI polish",
                    "chunk": "C02_polish",
                    "depends_on": ["T001"],
                },
            ],
        },
    )

    agent_workspace = tmp_path / "agent_workspace"
    agent_workspace.mkdir(parents=True)
    agents = {"agent_a": _DummyAgent(agent_workspace)}

    monkeypatch.setattr(
        cli_module.plan_commands,
        "create_agents_from_config",
        lambda *args, **kwargs: agents,
    )

    attempts = {"count": 0}

    async def _fake_run_single_question(*args, **kwargs):
        attempts["count"] += 1
        tasks_dir = agent_workspace / "tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)
        current_plan = json.loads((tasks_dir / "plan.json").read_text())
        active_chunk = current_plan.get("execution_scope", {}).get("active_chunk")
        if active_chunk == "C01_build":
            (tasks_dir / "plan.json").write_text(
                json.dumps(
                    {
                        "tasks": [
                            {
                                "id": "T001",
                                "chunk": "C01_build",
                                "status": "in_progress",
                            },
                        ],
                        "execution_scope": {"active_chunk": "C01_build"},
                    },
                    indent=2,
                ),
            )
            return {
                "answer": "partial",
                "coordination_result": {
                    "selected_agent": "agent_a",
                    "is_orchestrator_timeout": True,
                    "timeout_reason": "Time limit exceeded",
                },
            }

        if active_chunk == "C02_polish":
            (tasks_dir / "plan.json").write_text(
                json.dumps(
                    {
                        "tasks": [
                            {
                                "id": "T002",
                                "chunk": "C02_polish",
                                "status": "completed",
                            },
                        ],
                        "execution_scope": {"active_chunk": "C02_polish"},
                    },
                    indent=2,
                ),
            )
            return {
                "answer": "done",
                "coordination_result": {
                    "selected_agent": "agent_a",
                    "is_orchestrator_timeout": False,
                    "timeout_reason": None,
                },
            }

        raise AssertionError(f"unexpected active chunk in test: {active_chunk}")

    monkeypatch.setattr(cli_module.plan_commands, "run_single_question", _fake_run_single_question)

    config = {
        "agents": [{"type": "mock", "model": "mock-model"}],
        "orchestrator": {"coordination": {"max_orchestration_restarts": 0}},
        "timeout": {"orchestrator_timeout_seconds": 30},
    }

    final_answer, _ = await cli_module._execute_plan_phase(
        config=config,
        plan_session=session,
        question="Build chunks",
        automation=True,
    )

    assert final_answer == "done"
    assert attempts["count"] == 2

    metadata = session.load_metadata()
    assert metadata.status == "completed"
    assert metadata.current_chunk is None

    history = metadata.chunk_history or []
    assert len(history) == 2
    assert history[0].get("chunk") == "C01_build"
    assert history[0].get("status") == "timed_out"
    assert history[1].get("chunk") == "C02_polish"
    assert history[1].get("status") == "completed"


@pytest.mark.asyncio
async def test_execute_plan_phase_uses_textual_display_when_configured(
    temp_plans_dir,
    tmp_path,
    monkeypatch,
):
    """Execution phase should honor textual display type from config."""
    import massgen.cli as cli_module

    storage = PlanStorage()
    session = storage.create_plan("planning_session", str(tmp_path / "logs"))
    _write_frozen_plan(
        session,
        {
            "tasks": [
                {"id": "T001", "description": "Foundation", "chunk": "C01_build"},
            ],
        },
    )

    agent_workspace = tmp_path / "agent_workspace"
    agent_workspace.mkdir(parents=True)
    agents = {"agent_a": _DummyAgent(agent_workspace)}

    monkeypatch.setattr(
        cli_module.plan_commands,
        "create_agents_from_config",
        lambda *args, **kwargs: agents,
    )

    captured_display_types: list[str] = []

    async def _fake_run_single_question(*args, **kwargs):
        ui_config = args[2]
        captured_display_types.append(ui_config.get("display_type"))

        tasks_dir = agent_workspace / "tasks"
        current_plan = json.loads((tasks_dir / "plan.json").read_text())
        active_chunk = current_plan.get("execution_scope", {}).get("active_chunk", "C01_build")
        (tasks_dir / "plan.json").write_text(
            json.dumps(
                {
                    "tasks": [
                        {
                            "id": "T001",
                            "chunk": active_chunk,
                            "status": "completed",
                        },
                    ],
                    "execution_scope": {"active_chunk": active_chunk},
                },
                indent=2,
            ),
        )
        return {
            "answer": "done",
            "coordination_result": {
                "selected_agent": "agent_a",
                "is_orchestrator_timeout": False,
                "timeout_reason": None,
            },
        }

    monkeypatch.setattr(cli_module.plan_commands, "run_single_question", _fake_run_single_question)

    config = {
        "agents": [{"type": "mock", "model": "mock-model"}],
        "orchestrator": {"coordination": {"max_orchestration_restarts": 0}},
        "timeout": {"orchestrator_timeout_seconds": 30},
        "ui": {"display_type": "textual_terminal"},
    }

    final_answer, _ = await cli_module._execute_plan_phase(
        config=config,
        plan_session=session,
        question="Build chunk",
        automation=False,
    )

    assert final_answer == "done"
    assert captured_display_types == ["textual_terminal"]
