"""Deterministic non-API integration tests for hooks, broadcast, and async subagents."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import massgen.orchestrator as orchestrator_module
from massgen.coordination_tracker import AgentAnswer
from massgen.mcp_tools.hooks import HookType
from massgen.subagent.models import SubagentResult


def _capture_general_hook_manager(agent):
    captured = {}

    def _set_manager(manager):
        captured["manager"] = manager

    agent.backend.set_general_hook_manager = _set_manager
    return captured


def test_setup_hook_manager_registers_media_call_ledger_hook(mock_orchestrator):
    """Standard hook-manager path should include the media call ledger post hook."""
    orchestrator = mock_orchestrator(num_agents=1)
    agent_id = "agent_a"
    agent = orchestrator.agents[agent_id]

    captured = _capture_general_hook_manager(agent)
    orchestrator._setup_hook_manager_for_agent(agent_id, agent, {})
    manager = captured["manager"]

    post_hooks = manager.get_hooks_for_agent(agent_id, HookType.POST_TOOL_USE)
    hook_names = {hook.name for hook in post_hooks}
    assert "media_call_ledger" in hook_names


@pytest.mark.asyncio
async def test_mid_stream_hook_clears_stale_restart_when_no_new_answers(mock_orchestrator):
    orchestrator = mock_orchestrator(num_agents=2)
    orchestrator.config.disable_injection = False
    agent_id = "agent_a"
    peer_id = "agent_b"

    state = orchestrator.agent_states[agent_id]
    state.restart_pending = True
    state.injection_count = 1
    state.answer = "Agent A's existing answer"  # Has produced an answer already
    orchestrator.agent_states[peer_id].answer = "Known peer answer"

    agent = orchestrator.agents[agent_id]
    captured = _capture_general_hook_manager(agent)
    known_answers = {peer_id: "Known peer answer"}
    orchestrator._setup_hook_manager_for_agent(agent_id, agent, known_answers)
    manager = captured["manager"]

    result = await manager.execute_hooks(
        HookType.POST_TOOL_USE,
        "read_file",
        "{}",
        {"agent_id": agent_id},
        tool_output="ok",
    )

    assert result.inject is None
    assert state.restart_pending is False


@pytest.mark.asyncio
async def test_mid_stream_hook_injects_new_answers_after_first_restart(mock_orchestrator, monkeypatch):
    orchestrator = mock_orchestrator(num_agents=2)
    orchestrator.config.disable_injection = False
    agent_id = "agent_a"
    peer_id = "agent_b"

    state = orchestrator.agent_states[agent_id]
    state.restart_pending = True
    state.injection_count = 1
    state.answer = "Agent A's existing answer"  # Has produced an answer already
    orchestrator.agent_states[peer_id].answer = "New answer from peer"

    # Register the answer revision in coordination_tracker so
    # _get_agent_answer_revision_count returns > 0 for the peer.
    peer_answer = AgentAnswer(agent_id=peer_id, content="New answer from peer", timestamp=time.time())
    peer_answer.label = "B1.1"
    orchestrator.coordination_tracker.answers_by_agent.setdefault(peer_id, []).append(peer_answer)

    monkeypatch.setattr(
        orchestrator,
        "_copy_all_snapshots_to_temp_workspace",
        AsyncMock(return_value="/tmp/mock-snapshots"),
    )

    agent = orchestrator.agents[agent_id]
    captured = _capture_general_hook_manager(agent)
    orchestrator._setup_hook_manager_for_agent(agent_id, agent, {})
    manager = captured["manager"]

    result = await manager.execute_hooks(
        HookType.POST_TOOL_USE,
        "read_file",
        "{}",
        {"agent_id": agent_id},
        tool_output="ok",
    )

    assert result.inject is not None
    assert "NEW ANSWER RECEIVED" in result.inject["content"]
    assert state.restart_pending is False
    assert state.injection_count == 2
    assert peer_id in state.known_answer_ids


@pytest.mark.asyncio
async def test_round_timeout_hooks_integration_soft_then_hard_timeout(mock_orchestrator):
    orchestrator = mock_orchestrator(num_agents=1)
    agent_id = "agent_a"
    agent = orchestrator.agents[agent_id]

    orchestrator.config.timeout_config.initial_round_timeout_seconds = 1
    orchestrator.config.timeout_config.subsequent_round_timeout_seconds = 1
    orchestrator.config.timeout_config.round_timeout_grace_seconds = 0
    orchestrator.config.coordination_config.use_two_tier_workspace = True
    orchestrator.config.coordination_config.write_mode = "legacy"
    orchestrator.agent_states[agent_id].round_start_time = time.time() - 5

    captured = _capture_general_hook_manager(agent)
    orchestrator._setup_hook_manager_for_agent(agent_id, agent, {})
    manager = captured["manager"]

    post_result = await manager.execute_hooks(
        HookType.POST_TOOL_USE,
        "read_file",
        "{}",
        {"agent_id": agent_id},
        tool_output="ok",
    )
    assert post_result.inject is not None
    assert "ROUND TIME LIMIT APPROACHING" in post_result.inject["content"]
    assert "deliverable/" in post_result.inject["content"]
    assert orchestrator.agent_states[agent_id].round_timeout_state is not None
    assert orchestrator.agent_states[agent_id].round_timeout_state.soft_timeout_fired_at is not None

    hard_block = await manager.execute_hooks(
        HookType.PRE_TOOL_USE,
        "read_file",
        "{}",
        {"agent_id": agent_id},
    )
    assert hard_block.decision == "deny"
    assert "HARD TIMEOUT" in (hard_block.reason or "")
    assert orchestrator.agent_states[agent_id].round_timeout_state.consecutive_hard_denials == 1

    allow_vote = await manager.execute_hooks(
        HookType.PRE_TOOL_USE,
        "vote",
        "{}",
        {"agent_id": agent_id},
    )
    assert allow_vote.allowed is True
    assert orchestrator.agent_states[agent_id].round_timeout_state.consecutive_hard_denials == 0


@pytest.mark.asyncio
async def test_subagent_post_hook_uses_async_pending_getter(mock_orchestrator, monkeypatch):
    orchestrator = mock_orchestrator(num_agents=1)
    agent_id = "agent_a"
    agent = orchestrator.agents[agent_id]
    orchestrator._background_subagents_enabled = True

    captured = _capture_general_hook_manager(agent)
    orchestrator._setup_hook_manager_for_agent(agent_id, agent, {})
    manager = captured["manager"]

    subagent_result = SubagentResult.create_success(
        subagent_id="sub-async",
        answer="done",
        workspace_path="/tmp/sub-async",
        execution_time_seconds=1.0,
    )

    async def fake_async_pending(aid: str):
        assert aid == agent_id
        return [("sub-async", subagent_result)]

    def fail_sync_pending(_aid: str):
        raise AssertionError("Sync pending getter should not be used from post-tool hook")

    monkeypatch.setattr(orchestrator._subagent_lifecycle_coordinator, "get_pending_subagent_results_async", fake_async_pending, raising=False)
    monkeypatch.setattr(orchestrator._subagent_lifecycle_coordinator, "get_pending_subagent_results", fail_sync_pending)

    result = await manager.execute_hooks(
        HookType.POST_TOOL_USE,
        "mcp__filesystem__write_file",
        "{}",
        {"agent_id": agent_id},
        tool_output="ok",
    )

    assert result.inject is not None
    assert "sub-async" in result.inject["content"]


def test_broadcast_tool_registration_adds_custom_tool_names(mock_orchestrator):
    orchestrator = mock_orchestrator(num_agents=2)
    orchestrator.config.coordination_config.broadcast = "agents"
    orchestrator.config.coordination_config.broadcast_sensitivity = "high"

    for agent in orchestrator.agents.values():
        agent.backend.custom_tool_manager = object()

    orchestrator._init_broadcast_tools()

    workflow_names = {(tool.get("function", {}) or {}).get("name") for tool in orchestrator.workflow_tools}
    assert "ask_others" in workflow_names

    for agent in orchestrator.agents.values():
        assert "ask_others" in agent.backend._custom_tool_names
        assert "respond_to_broadcast" in agent.backend._custom_tool_names


def test_on_subagent_complete_queues_pending_results(mock_orchestrator):
    orchestrator = mock_orchestrator(num_agents=1)
    agent_id = "agent_a"
    result = SubagentResult(
        subagent_id="sub-1",
        status="completed",
        success=True,
        answer="done",
        workspace_path="/tmp/sub-1",
        execution_time_seconds=1.2,
    )

    orchestrator._on_subagent_complete(agent_id, "sub-1", result)

    assert agent_id in orchestrator._pending_subagent_results
    assert orchestrator._pending_subagent_results[agent_id][0][0] == "sub-1"
    assert orchestrator._pending_subagent_results[agent_id][0][1] == result


def test_on_subagent_complete_schedules_background_wait_interrupt(mock_orchestrator):
    orchestrator = mock_orchestrator(num_agents=1)
    agent_id = "agent_a"
    result = SubagentResult(
        subagent_id="sub-1",
        status="completed",
        success=True,
        answer="done",
        workspace_path="/tmp/sub-1",
        execution_time_seconds=1.2,
    )
    scheduled: list[tuple[str, str]] = []

    # Method moved into SubagentLifecycleCoordinator; patch the collaborator
    # so its internal call site (on_subagent_complete) sees the fake.
    orchestrator._subagent_lifecycle_coordinator.schedule_background_wait_interrupt_for_agent = lambda aid, trigger="background_subagent_complete": scheduled.append((aid, trigger))

    orchestrator._on_subagent_complete(agent_id, "sub-1", result)

    assert scheduled == [(agent_id, "background_subagent_complete")]


def test_get_pending_subagent_results_polls_mcp_and_deduplicates(mock_orchestrator):
    orchestrator = mock_orchestrator(num_agents=1)
    agent_id = "agent_a"
    agent = orchestrator.agents[agent_id]

    class FakeMCPClient:
        def __init__(self):
            self.calls = []

        def call_tool(self, name, args):
            self.calls.append((name, args))
            expected_server = orchestrator._subagent_server_name(agent_id)
            if name == f"mcp__{expected_server}__list_subagents":
                return {
                    "success": True,
                    "subagents": [
                        {
                            "subagent_id": "sub-complete",
                            "status": "completed",
                            "result": {
                                "subagent_id": "sub-complete",
                                "success": True,
                                "status": "completed",
                                "answer": "Subagent finished",
                                "workspace_path": "/tmp/sub-complete",
                                "execution_time_seconds": 3.5,
                                "token_usage": {"input_tokens": 10, "output_tokens": 20},
                            },
                        },
                        {"subagent_id": "sub-running", "status": "running"},
                    ],
                }
            return {"success": False}

    agent.mcp_client = FakeMCPClient()

    first = orchestrator._get_pending_subagent_results(agent_id)
    second = orchestrator._get_pending_subagent_results(agent_id)

    assert len(first) == 1
    assert first[0][0] == "sub-complete"
    assert first[0][1].status == "completed"
    assert second == []
    expected_server = orchestrator._subagent_server_name(agent_id)
    assert all(name == f"mcp__{expected_server}__list_subagents" for name, _ in agent.mcp_client.calls)


def test_get_pending_subagent_results_uses_backend_mcp_executor(mock_orchestrator):
    orchestrator = mock_orchestrator(num_agents=1)
    agent_id = "agent_a"
    agent = orchestrator.agents[agent_id]
    backend = agent.backend
    captured_calls: list[tuple[str, dict]] = []

    async def _fake_execute(function_name, arguments_json, max_retries=3):  # noqa: ANN001
        del max_retries
        args = json.loads(arguments_json)
        captured_calls.append((function_name, args))
        return (
            '{"success": true}',
            {
                "success": True,
                "subagents": [
                    {
                        "subagent_id": "sub-complete",
                        "status": "completed",
                        "result": {
                            "subagent_id": "sub-complete",
                            "success": True,
                            "status": "completed",
                            "answer": "Subagent finished",
                            "workspace_path": "/tmp/sub-complete",
                            "execution_time_seconds": 3.5,
                            "token_usage": {"input_tokens": 10, "output_tokens": 20},
                        },
                    },
                ],
            },
        )

    backend._execute_mcp_function_with_retry = _fake_execute

    first = orchestrator._get_pending_subagent_results(agent_id)
    second = orchestrator._get_pending_subagent_results(agent_id)

    assert len(first) == 1
    assert first[0][0] == "sub-complete"
    assert first[0][1].status == "completed"
    assert second == []
    expected_server = orchestrator._subagent_server_name(agent_id)
    assert captured_calls == [
        (f"mcp__{expected_server}__list_subagents", {}),
        (f"mcp__{expected_server}__list_subagents", {}),
    ]


def test_send_runtime_message_to_subagent_uses_backend_mcp_executor(mock_orchestrator):
    orchestrator = mock_orchestrator(num_agents=1)
    agent_id = "agent_a"
    agent = orchestrator.agents[agent_id]
    backend = agent.backend
    captured_calls: list[tuple[str, dict]] = []

    async def _fake_execute(function_name, arguments_json, max_retries=3):  # noqa: ANN001
        del max_retries
        args = json.loads(arguments_json)
        captured_calls.append((function_name, args))
        return ('{"success": true}', {"success": True, "operation": "send_message"})

    backend._execute_mcp_function_with_retry = _fake_execute

    delivered = orchestrator.send_runtime_message_to_subagent(
        "sub-1",
        "focus on tests",
        target_agents=["agent_b"],
    )

    assert delivered is True
    expected_server = orchestrator._subagent_server_name(agent_id)
    assert captured_calls == [
        (
            f"mcp__{expected_server}__send_message_to_subagent",
            {
                "subagent_id": "sub-1",
                "message": "focus on tests",
                "target_agents": ["agent_b"],
            },
        ),
    ]


def test_continue_subagent_uses_backend_mcp_executor(mock_orchestrator):
    orchestrator = mock_orchestrator(num_agents=1)
    agent_id = "agent_a"
    agent = orchestrator.agents[agent_id]
    backend = agent.backend
    captured_calls: list[tuple[str, dict]] = []

    async def _fake_execute(function_name, arguments_json, max_retries=3):  # noqa: ANN001
        del max_retries
        args = json.loads(arguments_json)
        captured_calls.append((function_name, args))
        return ('{"success": true}', {"success": True, "operation": "continue_subagent"})

    backend._execute_mcp_function_with_retry = _fake_execute

    continued = orchestrator.continue_subagent_from_tui(
        "sub-1",
        "Continue and add citations.",
    )

    assert continued is True
    expected_server = orchestrator._subagent_server_name(agent_id)
    assert captured_calls == [
        (
            f"mcp__{expected_server}__continue_subagent",
            {
                "subagent_id": "sub-1",
                "message": "Continue and add citations.",
                "background": True,
            },
        ),
    ]


def test_continue_subagent_background_notifies_runtime_card(mock_orchestrator):
    orchestrator = mock_orchestrator(num_agents=1)
    agent_id = "agent_a"
    agent = orchestrator.agents[agent_id]
    backend = agent.backend

    async def _fake_execute(function_name, arguments_json, max_retries=3):  # noqa: ANN001
        del function_name, max_retries
        args = json.loads(arguments_json)
        assert args["background"] is True
        return (
            '{"success": true, "operation": "continue_subagent", "mode": "background", "subagents": [{"subagent_id": "sub-1", "status": "running", "workspace": "/tmp/sub-1"}]}',
            {
                "success": True,
                "operation": "continue_subagent",
                "mode": "background",
                "subagents": [{"subagent_id": "sub-1", "status": "running", "workspace": "/tmp/sub-1"}],
            },
        )

    backend._execute_mcp_function_with_retry = _fake_execute

    captured_notification: dict[str, object] = {}

    def _notify_runtime_subagent_started(**kwargs):  # noqa: ANN003
        captured_notification.update(kwargs)

    orchestrator.coordination_ui = SimpleNamespace(
        display=SimpleNamespace(
            notify_runtime_subagent_started=_notify_runtime_subagent_started,
        ),
    )

    continued = orchestrator.continue_subagent_from_tui(
        "sub-1",
        "Continue and add citations.",
    )

    assert continued is True
    assert captured_notification["agent_id"] == agent_id
    assert captured_notification["subagent_id"] == "sub-1"
    assert "Continue and add citations." in str(captured_notification["task"])
    assert callable(captured_notification["status_callback"])


def test_send_runtime_message_to_subagent_falls_back_to_direct_inbox_write(
    mock_orchestrator,
    tmp_path,
):
    orchestrator = mock_orchestrator(num_agents=1)
    agent_id = "agent_a"
    agent = orchestrator.agents[agent_id]
    backend = agent.backend

    workspace = tmp_path / "workspace"
    sub_workspace = workspace / "subagents" / "sub-1" / "workspace"
    sub_workspace.mkdir(parents=True, exist_ok=True)

    backend.filesystem_manager = SimpleNamespace(
        get_current_workspace=lambda: workspace,
    )

    async def _fake_execute(function_name, arguments_json, max_retries=3):  # noqa: ANN001
        del function_name, arguments_json, max_retries
        return ('{"success": false}', {"success": False, "error": "MCP server busy"})

    backend._execute_mcp_function_with_retry = _fake_execute

    delivered = orchestrator.send_runtime_message_to_subagent(
        "sub-1",
        "focus on Bob Dylan's early years",
        target_agents=["agent_b"],
    )

    assert delivered is True

    inbox_dir = sub_workspace / ".massgen" / "runtime_inbox"
    msg_files = sorted(inbox_dir.glob("msg_*.json"))
    assert len(msg_files) == 1

    payload = json.loads(msg_files[0].read_text())
    assert payload["content"] == "focus on Bob Dylan's early years"
    assert payload["target_agents"] == ["agent_b"]


def test_send_runtime_message_fallback_uses_temp_workspace_parent(
    mock_orchestrator,
    tmp_path,
):
    """Fallback delivery should resolve run workspace root from temp workspace metadata."""
    orchestrator = mock_orchestrator(num_agents=1)
    agent = orchestrator.agents["agent_a"]
    backend = agent.backend

    run_workspace = tmp_path / "run_workspace"
    active_workspace = run_workspace / "agent_1_abcd1234"
    active_workspace.mkdir(parents=True, exist_ok=True)

    sub_workspace = run_workspace / "subagents" / "sub-1" / "workspace"
    sub_workspace.mkdir(parents=True, exist_ok=True)

    orchestrator._agent_temporary_workspace = str(run_workspace / "temp")
    backend.filesystem_manager = SimpleNamespace(
        get_current_workspace=lambda: active_workspace,
    )

    async def _fake_execute(function_name, arguments_json, max_retries=3):  # noqa: ANN001
        del function_name, arguments_json, max_retries
        return ('{"success": false}', {"success": False, "error": "MCP server busy"})

    backend._execute_mcp_function_with_retry = _fake_execute

    delivered = orchestrator.send_runtime_message_to_subagent(
        "sub-1",
        "use workspace-root fallback",
    )

    assert delivered is True
    inbox_dir = sub_workspace / ".massgen" / "runtime_inbox"
    msg_files = sorted(inbox_dir.glob("msg_*.json"))
    assert len(msg_files) == 1


def test_runtime_inbox_poller_uses_temp_workspace_parent_for_subagent_runs(mock_orchestrator, tmp_path):
    orchestrator = mock_orchestrator(num_agents=1)
    agent = orchestrator.agents["agent_a"]

    run_workspace = tmp_path / "subagent_run_workspace"
    active_workspace = run_workspace / "agent_1_abcd1234"
    active_workspace.mkdir(parents=True, exist_ok=True)
    (run_workspace / ".massgen" / "runtime_inbox").mkdir(parents=True, exist_ok=True)

    # Subagent backend cwd can point at per-agent inner workspaces while runtime
    # inbox messages are written to the orchestrator workspace root.
    orchestrator._agent_temporary_workspace = str(run_workspace / "temp")
    orchestrator._runtime_inbox_poller = None
    agent.backend.filesystem_manager = SimpleNamespace(
        get_current_workspace=lambda: active_workspace,
    )

    orchestrator._ensure_runtime_inbox_poller_initialized()

    poller = orchestrator._runtime_inbox_poller
    assert poller is not None
    assert getattr(poller, "_inbox_dir", None) == run_workspace / ".massgen" / "runtime_inbox"


def test_runtime_inbox_poller_falls_back_to_backend_workspace_without_temp_workspace(
    mock_orchestrator,
    tmp_path,
):
    orchestrator = mock_orchestrator(num_agents=1)
    agent = orchestrator.agents["agent_a"]

    active_workspace = tmp_path / "active_workspace"
    active_workspace.mkdir(parents=True, exist_ok=True)

    orchestrator._agent_temporary_workspace = None
    orchestrator._runtime_inbox_poller = None
    agent.backend.filesystem_manager = SimpleNamespace(
        get_current_workspace=lambda: active_workspace,
    )

    orchestrator._ensure_runtime_inbox_poller_initialized()

    poller = orchestrator._runtime_inbox_poller
    assert poller is not None
    assert getattr(poller, "_inbox_dir", None) == active_workspace / ".massgen" / "runtime_inbox"


def test_runtime_inbox_poller_ignores_global_temp_workspace_root(mock_orchestrator, tmp_path, monkeypatch):
    orchestrator = mock_orchestrator(num_agents=1)
    agent = orchestrator.agents["agent_a"]

    active_workspace = tmp_path / "active_workspace"
    active_workspace.mkdir(parents=True, exist_ok=True)

    global_temp_root = tmp_path / ".massgen" / "temp_workspaces"
    global_temp_root.mkdir(parents=True, exist_ok=True)

    orchestrator._agent_temporary_workspace = str(global_temp_root)
    orchestrator._runtime_inbox_poller = None
    agent.backend.filesystem_manager = SimpleNamespace(
        get_current_workspace=lambda: active_workspace,
    )

    log_messages: list[str] = []

    def _capture_info(message, *args, **kwargs):
        if args:
            try:
                message = message % args
            except Exception:
                pass
        log_messages.append(str(message))

    monkeypatch.setattr(orchestrator_module.logger, "info", _capture_info)
    orchestrator._ensure_runtime_inbox_poller_initialized()

    poller = orchestrator._runtime_inbox_poller
    assert poller is not None
    assert getattr(poller, "_inbox_dir", None) == active_workspace / ".massgen" / "runtime_inbox"
    joined = "\n".join(log_messages)
    assert "Initialized runtime inbox poller" in joined
    assert str(active_workspace / ".massgen" / "runtime_inbox") in joined


def test_poll_runtime_inbox_reads_messages_from_temp_workspace_parent(mock_orchestrator, tmp_path):
    orchestrator = mock_orchestrator(num_agents=1)
    agent = orchestrator.agents["agent_a"]

    run_workspace = tmp_path / "subagent_run_workspace"
    agent_workspace = run_workspace / "agent_1_abcd1234"
    agent_workspace.mkdir(parents=True, exist_ok=True)

    inbox_dir = run_workspace / ".massgen" / "runtime_inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    msg_file = inbox_dir / "msg_1.json"
    msg_file.write_text(
        json.dumps(
            {
                "content": "include beatles comparison",
                "source": "parent",
                "timestamp": "2026-02-20T08:50:41.000000+00:00",
                "target_agents": None,
            },
        ),
    )

    orchestrator._agent_temporary_workspace = str(run_workspace / "temp")
    orchestrator._runtime_inbox_poller = None
    agent.backend.filesystem_manager = SimpleNamespace(
        get_current_workspace=lambda: agent_workspace,
    )

    orchestrator._ensure_runtime_inbox_poller_initialized()
    orchestrator._poll_runtime_inbox()

    assert orchestrator._human_input_hook is not None
    assert orchestrator._human_input_hook.has_pending_input()
    pending_messages = orchestrator._human_input_hook.get_pending_messages(agent_ids=["agent_a"])
    assert len(pending_messages) == 1
    assert pending_messages[0]["content"] == "include beatles comparison"
    assert pending_messages[0]["source"] == "parent"


def test_poll_runtime_inbox_emits_injection_received_event(mock_orchestrator, tmp_path, monkeypatch):
    orchestrator = mock_orchestrator(num_agents=1)
    agent = orchestrator.agents["agent_a"]

    run_workspace = tmp_path / "subagent_run_workspace"
    agent_workspace = run_workspace / "agent_1_abcd1234"
    agent_workspace.mkdir(parents=True, exist_ok=True)

    inbox_dir = run_workspace / ".massgen" / "runtime_inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    msg_file = inbox_dir / "msg_1.json"
    msg_file.write_text(
        json.dumps(
            {
                "content": "include beatles comparison",
                "source": "parent",
                "timestamp": "2026-02-20T08:50:41.000000+00:00",
                "target_agents": None,
            },
        ),
    )

    orchestrator._agent_temporary_workspace = str(run_workspace / "temp")
    orchestrator._runtime_inbox_poller = None
    agent.backend.filesystem_manager = SimpleNamespace(
        get_current_workspace=lambda: agent_workspace,
    )

    emitted_events: list[dict[str, object]] = []

    class _FakeEmitter:
        def emit_injection_received(self, agent_id, source_agents, injection_type):
            emitted_events.append(
                {
                    "agent_id": agent_id,
                    "source_agents": source_agents,
                    "injection_type": injection_type,
                },
            )

    monkeypatch.setattr(
        "massgen.orchestrator.get_event_emitter",
        lambda: _FakeEmitter(),
    )

    orchestrator._ensure_runtime_inbox_poller_initialized()
    orchestrator._poll_runtime_inbox()

    assert emitted_events == [
        {
            "agent_id": "agent_a",
            "source_agents": ["parent"],
            "injection_type": "runtime_inbox_input",
        },
    ]


@pytest.mark.asyncio
async def test_human_input_hook_execute_polls_runtime_inbox_and_logs_delivery(
    mock_orchestrator,
    tmp_path,
    monkeypatch,
):
    orchestrator = mock_orchestrator(num_agents=1)
    agent = orchestrator.agents["agent_a"]

    run_workspace = tmp_path / "subagent_run_workspace"
    agent_workspace = run_workspace / "agent_1_abcd1234"
    agent_workspace.mkdir(parents=True, exist_ok=True)

    inbox_dir = run_workspace / ".massgen" / "runtime_inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    msg_file = inbox_dir / "msg_1.json"
    msg_file.write_text(
        json.dumps(
            {
                "content": "please also research the beatles",
                "source": "parent",
                "timestamp": "2026-02-20T09:08:44.000000+00:00",
                "target_agents": ["agent_a"],
            },
        ),
    )

    orchestrator._agent_temporary_workspace = str(run_workspace / "temp")
    orchestrator._runtime_inbox_poller = None
    orchestrator._human_input_hook = None
    agent.backend.filesystem_manager = SimpleNamespace(
        get_current_workspace=lambda: agent_workspace,
    )

    log_messages: list[str] = []

    def _capture_info(message, *args, **kwargs):
        if args:
            try:
                message = message % args
            except Exception:
                pass
        log_messages.append(str(message))

    monkeypatch.setattr(orchestrator_module.logger, "info", _capture_info)
    orchestrator._ensure_runtime_human_input_hook_initialized()
    orchestrator._ensure_runtime_inbox_poller_initialized()

    human_hook = orchestrator._human_input_hook
    assert human_hook is not None
    result = await human_hook.execute(
        "mcp__filesystem__write_file",
        "{}",
        {"agent_id": "agent_a"},
    )

    assert result.inject is not None
    assert "please also research the beatles" in result.inject["content"]
    assert not msg_file.exists()
    joined = "\n".join(log_messages)
    assert "Injecting runtime inbox message" in joined
    assert "please also research the beatles" in joined
    assert "(target=['agent_a'], source=parent)" in joined
    assert "%s" not in joined


@pytest.mark.asyncio
async def test_setup_hook_manager_registers_subagent_injection_hook(mock_orchestrator, monkeypatch):
    orchestrator = mock_orchestrator(num_agents=1)
    orchestrator._background_subagents_enabled = True
    agent_id = "agent_a"
    agent = orchestrator.agents[agent_id]

    pending_result = SubagentResult(
        subagent_id="sub-done",
        status="completed",
        success=True,
        answer="Background subagent answer",
        workspace_path="/tmp/sub-done",
        execution_time_seconds=2.0,
    )

    async def _pending_results(_agent_id: str):
        return [("sub-done", pending_result)]

    monkeypatch.setattr(
        orchestrator,
        "_get_pending_subagent_results_async",
        _pending_results,
    )

    captured = _capture_general_hook_manager(agent)
    orchestrator._setup_hook_manager_for_agent(agent_id, agent, {})
    manager = captured["manager"]

    result = await manager.execute_hooks(
        HookType.POST_TOOL_USE,
        "read_file",
        "{}",
        {"agent_id": agent_id},
        tool_output="ok",
    )

    assert result.inject is not None
    assert "BACKGROUND SUBAGENT RESULTS" in result.inject["content"]
    assert "sub-done" in result.inject["content"]
    assert result.inject["strategy"] == orchestrator._background_subagent_injection_strategy
