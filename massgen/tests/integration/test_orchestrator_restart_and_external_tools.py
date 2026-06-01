"""Deterministic non-API integration tests for restart and external tool passthrough."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest


def _configure_agent_script(agent, scripted_tool_calls, responses=None):
    """Attach deterministic per-call tool scripts to a mock-backed agent."""
    agent.backend.tool_call_responses = scripted_tool_calls
    agent.backend.responses = responses or ["ok"] * len(scripted_tool_calls)


async def _collect_stream(stream):
    emitted = []
    async for item in stream:
        emitted.append(item)
    return emitted


@pytest.mark.asyncio
async def test_stream_agent_execution_vote_only_restart_short_circuits(mock_orchestrator, monkeypatch):
    orchestrator = mock_orchestrator(num_agents=1)
    orchestrator.current_task = "Vote-only restart path"
    agent_id = "agent_a"

    state = orchestrator.agent_states[agent_id]
    state.restart_pending = True
    state.injection_count = 2
    state.answer = "existing answer"  # Must have answer for restart to proceed

    monkeypatch.setattr(orchestrator, "_is_vote_only_mode", lambda _aid: True)

    emitted = await _collect_stream(
        orchestrator._stream_agent_execution(agent_id, orchestrator.current_task, {}),
    )

    assert emitted == [("done", None)]
    assert state.restart_pending is False
    assert orchestrator.agents[agent_id].backend._call_count == 0


@pytest.mark.asyncio
async def test_stream_agent_execution_first_restart_increments_injection_count(mock_orchestrator, monkeypatch):
    orchestrator = mock_orchestrator(num_agents=1)
    orchestrator.current_task = "First restart path"
    agent_id = "agent_a"

    state = orchestrator.agent_states[agent_id]
    state.restart_pending = True
    state.injection_count = 0
    state.answer = "existing answer"  # Must have answer for restart to proceed

    monkeypatch.setattr(orchestrator, "_is_vote_only_mode", lambda _aid: False)

    emitted = await _collect_stream(
        orchestrator._stream_agent_execution(agent_id, orchestrator.current_task, {}),
    )

    assert emitted == [("done", None)]
    assert state.restart_pending is False
    assert state.injection_count == 1
    assert orchestrator.agents[agent_id].backend._call_count == 0


# --- First-answer protection tests ---


def test_should_defer_restart_true_when_no_answer(mock_orchestrator):
    """Agent with no answer should defer restart to protect first-answer production."""
    orchestrator = mock_orchestrator(num_agents=1)
    assert orchestrator._should_defer_restart_for_first_answer("agent_a") is True


def test_should_defer_restart_false_when_has_answer(mock_orchestrator):
    """Agent with an existing answer should not defer restart."""
    orchestrator = mock_orchestrator(num_agents=1)
    orchestrator.agent_states["agent_a"].answer = "some answer"
    assert orchestrator._should_defer_restart_for_first_answer("agent_a") is False


def test_should_defer_restart_false_for_unknown_agent(mock_orchestrator):
    """Unknown agent_id should not defer (no state to protect)."""
    orchestrator = mock_orchestrator(num_agents=1)
    assert orchestrator._should_defer_restart_for_first_answer("nonexistent") is False


@pytest.mark.asyncio
async def test_first_answer_protection_skips_restart(mock_orchestrator, monkeypatch):
    """Agent with restart_pending but no answer yet should NOT restart - it should
    clear the flag and proceed with normal execution instead."""
    orchestrator = mock_orchestrator(num_agents=1)
    orchestrator.current_task = "First answer protection test"
    agent_id = "agent_a"

    state = orchestrator.agent_states[agent_id]
    state.restart_pending = True
    state.injection_count = 0
    state.answer = None  # No answer yet - first answer protection applies

    monkeypatch.setattr(orchestrator, "_is_vote_only_mode", lambda _aid: False)

    emitted = await _collect_stream(
        orchestrator._stream_agent_execution(agent_id, orchestrator.current_task, {}),
    )

    # Agent should NOT have immediately restarted - it should have run normally
    assert emitted != [("done", None)]
    # restart_pending should be cleared
    assert state.restart_pending is False


@pytest.mark.asyncio
async def test_first_answer_protection_allows_restart_when_has_answer(mock_orchestrator, monkeypatch):
    """Agent WITH an existing answer should restart normally when restart_pending."""
    orchestrator = mock_orchestrator(num_agents=1)
    orchestrator.current_task = "Restart proceeds with answer"
    agent_id = "agent_a"

    state = orchestrator.agent_states[agent_id]
    state.restart_pending = True
    state.injection_count = 0
    state.answer = "existing answer"  # HAS an answer

    monkeypatch.setattr(orchestrator, "_is_vote_only_mode", lambda _aid: False)

    emitted = await _collect_stream(
        orchestrator._stream_agent_execution(agent_id, orchestrator.current_task, {}),
    )

    # Should restart normally (existing behavior)
    assert emitted == [("done", None)]


@pytest.mark.asyncio
async def test_no_hook_midstream_deferred_for_first_answer(mock_orchestrator):
    """_prepare_no_hook_midstream_enforcement should return None when agent has no answer."""
    orchestrator = mock_orchestrator(num_agents=2)
    agent_id = "agent_a"

    state = orchestrator.agent_states[agent_id]
    state.restart_pending = True
    state.answer = None  # No answer yet

    # Give the other agent an answer so there's something to inject
    orchestrator.agent_states["agent_b"].answer = "agent b answer"

    result = await orchestrator._prepare_no_hook_midstream_enforcement(agent_id, {})

    assert result is None
    assert state.restart_pending is False


@pytest.mark.asyncio
async def test_no_hook_midstream_enforcement_includes_queued_human_input(mock_orchestrator, monkeypatch):
    """Hookless fallback should still deliver queued runtime human input at checkpoints."""
    from massgen.mcp_tools.hooks import HumanInputHook

    orchestrator = mock_orchestrator(num_agents=1)
    agent_id = "agent_a"
    state = orchestrator.agent_states[agent_id]
    state.restart_pending = True
    state.answer = "existing answer"

    # No peer-answer updates in this scenario.
    monkeypatch.setattr(
        orchestrator,
        "_select_midstream_answer_updates",
        lambda _agent_id, _answers: ({}, False),
    )

    orchestrator._human_input_hook = HumanInputHook()
    orchestrator._human_input_hook.set_pending_input("Please include concrete citations.")

    result = await orchestrator._prepare_no_hook_midstream_enforcement(agent_id, {})

    assert result is not None
    assert "[Human Input]:" in result
    assert "Please include concrete citations." in result
    assert state.restart_pending is False


@pytest.mark.asyncio
async def test_no_hook_midstream_enforcement_allows_runtime_input_before_first_answer(mock_orchestrator, monkeypatch):
    """Runtime control messages should still deliver during first-answer protection."""
    from massgen.mcp_tools.hooks import HumanInputHook

    orchestrator = mock_orchestrator(num_agents=1)
    agent_id = "agent_a"
    state = orchestrator.agent_states[agent_id]
    state.restart_pending = True
    state.answer = None

    monkeypatch.setattr(
        orchestrator,
        "_select_midstream_answer_updates",
        lambda _agent_id, _answers: ({}, False),
    )

    orchestrator._human_input_hook = HumanInputHook()
    orchestrator._human_input_hook.set_pending_input("Focus on edge cases first.")

    result = await orchestrator._prepare_no_hook_midstream_enforcement(agent_id, {})

    assert result is not None
    assert "[Human Input]:" in result
    assert "Focus on edge cases first." in result


@pytest.mark.asyncio
async def test_no_hook_midstream_enforcement_includes_background_tool_updates(mock_orchestrator, monkeypatch):
    """Hookless fallback should inject completed background tool results."""
    orchestrator = mock_orchestrator(num_agents=1)
    agent_id = "agent_a"
    state = orchestrator.agent_states[agent_id]
    state.restart_pending = True
    state.answer = "existing answer"

    # No peer-answer updates in this scenario.
    monkeypatch.setattr(
        orchestrator,
        "_select_midstream_answer_updates",
        lambda _agent_id, _answers: ({}, False),
    )

    backend = orchestrator.agents[agent_id].backend
    setattr(
        backend,
        "get_pending_background_tool_results",
        lambda: [
            {
                "job_id": "bgtool_1",
                "tool_name": "custom_tool__generate_media",
                "status": "completed",
                "result": "Generated image at /tmp/image.png",
            },
        ],
    )

    result = await orchestrator._prepare_no_hook_midstream_enforcement(agent_id, {})

    assert result is not None
    assert "BACKGROUND TOOL RESULTS" in result
    assert "bgtool_1" in result
    assert "custom_tool__generate_media" in result


@pytest.mark.asyncio
async def test_no_hook_midstream_enforcement_includes_subagent_completions(mock_orchestrator, monkeypatch):
    """Hookless fallback should inject completed background subagent results."""
    from massgen.subagent.models import SubagentResult

    orchestrator = mock_orchestrator(num_agents=1)
    agent_id = "agent_a"
    state = orchestrator.agent_states[agent_id]
    state.restart_pending = True
    state.answer = "existing answer"

    # No peer-answer updates in this scenario.
    monkeypatch.setattr(
        orchestrator,
        "_select_midstream_answer_updates",
        lambda _agent_id, _answers: ({}, False),
    )

    async def _fake_get_pending_subagent_results(_aid):
        return [
            (
                "subagent_1",
                SubagentResult.create_success(
                    subagent_id="subagent_1",
                    answer="Subagent synthesis complete.",
                    workspace_path="/workspace/subagent_1",
                    execution_time_seconds=12.0,
                ),
            ),
        ]

    # Method moved into SubagentLifecycleCoordinator; patch the collaborator so
    # in-collaborator call sites see the fake (the orchestrator delegator routes
    # through self._subagent_lifecycle_coordinator).
    monkeypatch.setattr(
        orchestrator._subagent_lifecycle_coordinator,
        "get_pending_subagent_results_async",
        _fake_get_pending_subagent_results,
    )

    result = await orchestrator._prepare_no_hook_midstream_enforcement(agent_id, {})

    assert result is not None
    assert "subagent_1" in result
    assert "Subagent synthesis complete." in result


@pytest.mark.asyncio
async def test_runtime_queue_wait_interrupt_for_active_external_wait(mock_orchestrator, monkeypatch):
    """Queued runtime input should trigger wait interruption for external wait handlers."""
    orchestrator = mock_orchestrator(num_agents=1)
    agent_id = "agent_a"
    backend = orchestrator.agents[agent_id].backend

    setattr(backend, "is_background_wait_active", lambda: True)
    captured_payload: dict = {}
    setattr(
        backend,
        "notify_background_wait_interrupt",
        lambda payload: captured_payload.update(payload) or True,
    )

    async def _fake_runtime_sections(_agent_id: str):
        return ["[Human Input]: Prioritize edge-case tests."]

    monkeypatch.setattr(
        orchestrator,
        "_collect_no_hook_runtime_fallback_sections",
        _fake_runtime_sections,
    )

    interrupted = await orchestrator._maybe_interrupt_background_wait_for_agent(
        agent_id,
        trigger="queued_human_input",
    )

    assert interrupted is True
    assert captured_payload.get("interrupt_reason") == "runtime_injection_available"
    assert "edge-case tests" in str(captured_payload.get("injected_content", ""))


@pytest.mark.asyncio
async def test_runtime_queue_wait_interrupt_skips_when_agent_not_waiting(mock_orchestrator, monkeypatch):
    """No signal should be emitted when the backend is not actively waiting."""
    orchestrator = mock_orchestrator(num_agents=1)
    agent_id = "agent_a"
    backend = orchestrator.agents[agent_id].backend

    setattr(backend, "is_background_wait_active", lambda: False)
    called = {"collect": 0}

    async def _fake_runtime_sections(_agent_id: str):
        called["collect"] += 1
        return ["[Human Input]: should not be collected"]

    monkeypatch.setattr(
        orchestrator,
        "_collect_no_hook_runtime_fallback_sections",
        _fake_runtime_sections,
    )

    interrupted = await orchestrator._maybe_interrupt_background_wait_for_agent(
        agent_id,
        trigger="queued_human_input",
    )

    assert interrupted is False
    assert called["collect"] == 0


@pytest.mark.asyncio
async def test_stream_agent_execution_inserts_runtime_user_instructions_after_original_message(
    mock_orchestrator,
):
    """Delivered runtime input should be persisted into subsequent execution context."""
    orchestrator = mock_orchestrator(num_agents=1)
    orchestrator.current_task = "Create an image about a goat."
    agent_id = "agent_a"

    # Hookless backends should still initialize the runtime-injection hook.
    orchestrator._setup_hook_manager_for_agent(agent_id, orchestrator.agents[agent_id], {})
    assert orchestrator._human_input_hook is not None
    orchestrator._human_input_hook.set_pending_input(
        "include bob dylan",
        target_agents=[agent_id],
    )

    runtime_sections = await orchestrator._collect_no_hook_runtime_fallback_sections(agent_id)
    assert runtime_sections
    assert "include bob dylan" in "\n".join(runtime_sections)

    _configure_agent_script(
        orchestrator.agents[agent_id],
        scripted_tool_calls=[
            [{"name": "new_answer", "arguments": {"content": "Generated image prompt"}}],
        ],
    )

    captured_messages = []
    original_stream = orchestrator.agents[agent_id].backend.stream_with_tools

    async def _capture_stream(messages, tools=None, **kwargs):
        captured_messages.append(messages)
        async for chunk in original_stream(messages, tools=tools, **kwargs):
            yield chunk

    orchestrator.agents[agent_id].backend.stream_with_tools = _capture_stream

    emitted = await _collect_stream(
        orchestrator._stream_agent_execution(agent_id, orchestrator.current_task, {}),
    )

    assert ("result", ("answer", "Generated image prompt")) in emitted
    assert captured_messages
    first_user_message = next(
        (msg.get("content", "") for msg in captured_messages[0] if msg.get("role") == "user"),
        "",
    )
    assert "<RUNTIME USER INSTRUCTIONS>" in first_user_message
    assert "include bob dylan" in first_user_message
    assert "<END OF ORIGINAL MESSAGE>" in first_user_message
    assert "<CURRENT ANSWERS from the agents>" in first_user_message
    assert first_user_message.index("<END OF ORIGINAL MESSAGE>") < first_user_message.index(
        "<RUNTIME USER INSTRUCTIONS>",
    )
    assert first_user_message.index("<RUNTIME USER INSTRUCTIONS>") < first_user_message.index(
        "<CURRENT ANSWERS from the agents>",
    )


@pytest.mark.asyncio
async def test_stream_agent_execution_inserts_round_evaluator_context_before_current_answers(
    mock_orchestrator,
    tmp_path: Path,
):
    """Orchestrator-provided round-evaluator artifacts should be surfaced in the next round's user message."""
    from massgen.subagent.models import RoundEvaluatorResult, SubagentResult

    orchestrator = mock_orchestrator(num_agents=1)
    orchestrator.current_task = "Revise the draft using evaluator critique."
    agent_id = "agent_a"

    orchestrator.agent_states[agent_id].answer = "answer v1"
    evaluator_workspace = tmp_path / "round_evaluator"
    evaluator_workspace.mkdir()
    critique_path = evaluator_workspace / "critique_packet.md"
    critique_path.write_text(
        "Detailed critique packet\n\nTop weakness: tighten the evidence trail.",
        encoding="utf-8",
    )
    (evaluator_workspace / "verdict.json").write_text(
        json.dumps(
            {
                "schema_version": "1",
                "verdict": "converged",
                "scores": {"E1": 9},
            },
        ),
        encoding="utf-8",
    )
    evaluator_result = RoundEvaluatorResult.from_subagent_result(
        SubagentResult.create_success(
            subagent_id="round_eval",
            answer="Short evaluator summary",
            workspace_path=str(evaluator_workspace),
            execution_time_seconds=1.0,
        ),
    )
    orchestrator._queue_round_start_context_block(
        agent_id,
        orchestrator._format_round_evaluator_result_block(
            "round_eval",
            evaluator_result,
        ),
    )

    _configure_agent_script(
        orchestrator.agents[agent_id],
        scripted_tool_calls=[
            [{"name": "vote", "arguments": {"agent_id": agent_id, "reason": "ready"}}],
        ],
    )

    captured_messages = []
    original_stream = orchestrator.agents[agent_id].backend.stream_with_tools

    async def _capture_stream(messages, tools=None, **kwargs):
        captured_messages.append(messages)
        async for chunk in original_stream(messages, tools=tools, **kwargs):
            yield chunk

    orchestrator.agents[agent_id].backend.stream_with_tools = _capture_stream

    emitted = await _collect_stream(
        orchestrator._stream_agent_execution(
            agent_id,
            orchestrator.current_task,
            {agent_id: "answer v1"},
        ),
    )

    assert ("result", ("vote", {"agent_id": agent_id, "reason": "ready"})) in emitted
    assert captured_messages
    first_user_message = next(
        (msg.get("content", "") for msg in captured_messages[0] if msg.get("role") == "user"),
        "",
    )
    assert "ROUND EVALUATOR RESULT" in first_user_message
    assert '<evaluator_packet subagent_id="round_eval" status="success">' in first_user_message
    assert str(critique_path) in first_user_message
    assert "Detailed critique packet" in first_user_message
    assert "<CURRENT ANSWERS from the agents>" in first_user_message
    assert first_user_message.index("ROUND EVALUATOR RESULT") < first_user_message.index(
        "<CURRENT ANSWERS from the agents>",
    )


@pytest.mark.asyncio
async def test_stream_agent_execution_surfaces_external_tool_calls(mock_orchestrator):
    orchestrator = mock_orchestrator(num_agents=1)
    orchestrator.current_task = "External passthrough"
    orchestrator._external_tools = [
        {
            "type": "function",
            "function": {
                "name": "external_lookup",
                "description": "Caller-executed external tool",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]

    agent_id = "agent_a"
    _configure_agent_script(
        orchestrator.agents[agent_id],
        scripted_tool_calls=[
            [{"id": "ext-1", "name": "external_lookup", "arguments": {"query": "latest"}}],
        ],
    )

    emitted = await _collect_stream(
        orchestrator._stream_agent_execution(agent_id, orchestrator.current_task, {}),
    )

    external_items = [item for item in emitted if item[0] == "external_tool_calls"]
    assert len(external_items) == 1
    assert external_items[0][1][0]["name"] == "external_lookup"
    assert emitted[-1] == ("done", None)
    assert not any(item[0] == "result" for item in emitted)


@pytest.mark.asyncio
async def test_stream_coordination_surfaces_external_tool_calls_and_stops(mock_orchestrator):
    orchestrator = mock_orchestrator(num_agents=1)
    orchestrator.current_task = "Coordination external passthrough"
    orchestrator._external_tools = [
        {
            "type": "function",
            "function": {
                "name": "external_lookup",
                "description": "Caller-executed external tool",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]

    _configure_agent_script(
        orchestrator.agents["agent_a"],
        scripted_tool_calls=[
            [{"id": "ext-2", "name": "external_lookup", "arguments": {"query": "deploy status"}}],
        ],
    )

    votes = {}
    chunks = []
    async for chunk in orchestrator._stream_coordination_with_agents(votes, {}):
        chunks.append(chunk)

    tool_chunks = [chunk for chunk in chunks if getattr(chunk, "type", None) == "tool_calls"]
    assert len(tool_chunks) == 1
    assert tool_chunks[0].source == "agent_a"
    assert tool_chunks[0].tool_calls[0]["name"] == "external_lookup"
    assert chunks[-1].type == "done"
    assert votes == {}


# =============================================================================
# Hookless delivery silent-drop prevention (MAS-308)
# =============================================================================


@pytest.mark.asyncio
async def test_hookless_bg_tool_delivery_failure_does_not_silently_drop(mock_orchestrator, monkeypatch):
    """If background tool formatting fails inside the hook, items must not be permanently lost."""
    from massgen.mcp_tools.hooks import BackgroundToolCompleteHook

    orchestrator = mock_orchestrator(num_agents=1)
    agent_id = "agent_a"

    jobs = [
        {"job_id": "bg1", "tool_name": "my_tool", "status": "completed", "result": "ok"},
    ]
    orchestrator._no_hook_pending_background_tool_results[agent_id] = list(jobs)

    # Make formatting raise so the hook returns allow() with no inject
    BackgroundToolCompleteHook._format_completed_jobs
    monkeypatch.setattr(
        BackgroundToolCompleteHook,
        "_format_completed_jobs",
        staticmethod(lambda _jobs: (_ for _ in ()).throw(RuntimeError("format exploded"))),
    )

    sections = await orchestrator._collect_no_hook_runtime_fallback_sections(agent_id)

    # No content was delivered (formatting failed)
    assert not sections or not any("bg1" in s for s in sections)

    # But the items must still be available for retry
    remaining = orchestrator._no_hook_pending_background_tool_results.get(agent_id, [])
    assert len(remaining) >= 1, "Items must not be permanently dropped on delivery failure"


@pytest.mark.asyncio
async def test_hookless_subagent_delivery_failure_does_not_silently_drop(mock_orchestrator, monkeypatch):
    """If subagent result formatting fails, items must be preserved for retry."""
    from massgen.subagent.models import SubagentResult

    orchestrator = mock_orchestrator(num_agents=1)
    agent_id = "agent_a"

    result = SubagentResult(
        subagent_id="sub_1",
        status="completed",
        success=True,
        answer="Found it",
    )
    orchestrator._pending_subagent_results[agent_id] = [("sub_1", result)]
    # Suppress MCP polling
    monkeypatch.setattr(orchestrator, "_get_pending_subagent_results", lambda _aid: [])

    # Make formatting raise inside the hook's execute path
    monkeypatch.setattr(
        "massgen.subagent.result_formatter.format_batch_results",
        lambda _results: (_ for _ in ()).throw(RuntimeError("format exploded")),
    )

    sections = await orchestrator._collect_no_hook_runtime_fallback_sections(agent_id)

    assert not sections or not any("sub_1" in s for s in sections)

    remaining = orchestrator._pending_subagent_results.get(agent_id, [])
    assert len(remaining) >= 1, "Subagent results must not be permanently dropped on delivery failure"


@pytest.mark.asyncio
async def test_codex_hook_flush_includes_local_subagent_queue(mock_orchestrator, monkeypatch):
    """Codex hook delivery should flush orchestrator-owned queued subagent results."""
    from massgen.subagent.models import SubagentResult

    orchestrator = mock_orchestrator(num_agents=1)
    agent_id = "agent_a"
    agent = orchestrator.agents[agent_id]

    result = SubagentResult(
        subagent_id="trace_analyzer_agent_a_r2",
        status="completed",
        success=True,
        answer="Trace analysis completed.\n### DO\n- Run tests now.",
    )
    orchestrator._pending_subagent_results[agent_id] = [(result.subagent_id, result)]

    written_payloads: list[str] = []
    setattr(
        agent.backend,
        "write_post_tool_use_hook",
        lambda content, tool_matcher="*", ttl_seconds=30.0: written_payloads.append(content),
    )

    async def _fake_get_pending_subagent_results(_aid):
        return []

    monkeypatch.setattr(
        orchestrator,
        "_get_pending_subagent_results_async",
        _fake_get_pending_subagent_results,
    )
    monkeypatch.setattr(
        "massgen.subagent.result_formatter.format_batch_results",
        lambda results: ("BACKGROUND SUBAGENT RESULTS\n" f"{results[0][0]} -> {results[0][1].answer}"),
    )

    await orchestrator._flush_codex_hook_payloads(agent_id, agent, {})

    assert len(written_payloads) == 1
    assert "BACKGROUND SUBAGENT RESULTS" in written_payloads[0]
    assert "trace_analyzer_agent_a_r2" in written_payloads[0]
    assert "Run tests now" in written_payloads[0]
    assert orchestrator._pending_subagent_results.get(agent_id) in (None, [])


def test_setup_hook_manager_for_codex_hybrid_sets_native_and_mcp(mock_orchestrator, tmp_path: Path):
    """Codex hybrid setup should configure native Bash hooks without losing MCP delivery."""
    from massgen.mcp_tools.native_hook_adapters.codex_adapter import (
        CodexNativeHookAdapter,
    )

    orchestrator = mock_orchestrator(num_agents=1)
    agent_id = "agent_a"
    agent = orchestrator.agents[agent_id]

    captured: dict[str, object] = {}
    adapter = CodexNativeHookAdapter(hook_dir=tmp_path / ".codex")

    agent.backend._provider_name = "codex"
    agent.backend.supports_native_hooks = lambda: True
    agent.backend.supports_mcp_server_hooks = lambda: True
    agent.backend.get_native_hook_adapter = lambda: adapter
    agent.backend.set_native_hooks_config = lambda config: captured.setdefault("native_config", config)
    agent.backend.set_background_wait_interrupt_provider = lambda provider: captured.setdefault(
        "wait_provider",
        provider,
    )

    orchestrator._setup_hook_manager_for_agent(agent_id, agent, {})

    native_config = captured.get("native_config")
    assert isinstance(native_config, dict)
    assert "hooks" in native_config
    assert "PreToolUse" not in native_config["hooks"]
    assert "PostToolUse" in native_config["hooks"]
    assert native_config["hooks"]["PostToolUse"][0]["matcher"] == "Bash"
    assert agent_id in orchestrator._codex_mcp_hook_agents
    assert callable(captured.get("wait_provider"))


def test_setup_hook_manager_for_codex_hybrid_registers_round_timeout_hooks(
    mock_orchestrator,
    tmp_path: Path,
):
    """Codex hybrid setup should still initialize round-timeout state for runtime controls."""
    from massgen.mcp_tools.native_hook_adapters.codex_adapter import (
        CodexNativeHookAdapter,
    )

    orchestrator = mock_orchestrator(num_agents=1)
    agent_id = "agent_a"
    agent = orchestrator.agents[agent_id]
    orchestrator.config.timeout_config.initial_round_timeout_seconds = 1200
    orchestrator.config.timeout_config.subsequent_round_timeout_seconds = 900
    orchestrator.config.timeout_config.round_timeout_grace_seconds = 300

    adapter = CodexNativeHookAdapter(hook_dir=tmp_path / ".codex")

    agent.backend._provider_name = "codex"
    agent.backend.supports_native_hooks = lambda: True
    agent.backend.supports_mcp_server_hooks = lambda: True
    agent.backend.get_native_hook_adapter = lambda: adapter
    agent.backend.set_native_hooks_config = lambda _config: None
    agent.backend.set_background_wait_interrupt_provider = lambda _provider: None

    orchestrator._setup_hook_manager_for_agent(agent_id, agent, {})

    assert orchestrator.agent_states[agent_id].round_timeout_hooks is not None
    assert orchestrator.agent_states[agent_id].round_timeout_state is not None


@pytest.mark.asyncio
async def test_codex_answer_now_flushes_manual_wrap_up_payload(
    mock_orchestrator,
    tmp_path: Path,
):
    """Codex hybrid path should prime manual wrap-up payloads as soon as Answer Now is clicked."""
    from massgen.mcp_tools.native_hook_adapters.codex_adapter import (
        CodexNativeHookAdapter,
    )

    orchestrator = mock_orchestrator(num_agents=1)
    agent_id = "agent_a"
    agent = orchestrator.agents[agent_id]
    orchestrator.config.timeout_config.initial_round_timeout_seconds = 1200
    orchestrator.config.timeout_config.subsequent_round_timeout_seconds = 900
    orchestrator.config.timeout_config.round_timeout_grace_seconds = 300

    adapter = CodexNativeHookAdapter(hook_dir=tmp_path / ".codex")

    agent.backend._provider_name = "codex"
    agent.backend.supports_native_hooks = lambda: True
    agent.backend.supports_mcp_server_hooks = lambda: True
    agent.backend.get_native_hook_adapter = lambda: adapter
    agent.backend.set_native_hooks_config = lambda _config: None
    agent.backend.set_background_wait_interrupt_provider = lambda _provider: None

    written_payloads: list[str] = []
    setattr(
        agent.backend,
        "write_post_tool_use_hook",
        lambda content, tool_matcher="*", ttl_seconds=30.0: written_payloads.append(content),
    )

    orchestrator._setup_hook_manager_for_agent(agent_id, agent, {})
    orchestrator._active_streams = {}
    orchestrator._active_tasks = {}
    orchestrator.agent_states[agent_id].round_start_time = time.time() - 5

    result = orchestrator.request_answer_now()
    assert result["requested_agents"] == ["agent_a"]

    assert len(written_payloads) == 1
    assert "ANSWER NOW REQUESTED" in written_payloads[0]


# =============================================================================
# Hookless delivery event emissions (MAS-308)
# =============================================================================


@pytest.mark.asyncio
async def test_hookless_human_input_delivery_emits_event(mock_orchestrator, monkeypatch):
    """Delivering human input via hookless path should emit an injection_received event."""
    from massgen.mcp_tools.hooks import HumanInputHook

    orchestrator = mock_orchestrator(num_agents=1)
    agent_id = "agent_a"

    orchestrator._human_input_hook = HumanInputHook()
    orchestrator._human_input_hook.set_pending_input("Prioritize accuracy.")

    emitted_events = []

    # Patch the event emitter at module level
    class _FakeEmitter:
        def emit_injection_received(self, agent_id, source_agents, injection_type):
            emitted_events.append({"agent_id": agent_id, "injection_type": injection_type})

    monkeypatch.setattr(
        "massgen.orchestrator.get_event_emitter",
        lambda: _FakeEmitter(),
    )

    sections = await orchestrator._collect_no_hook_runtime_fallback_sections(agent_id)

    assert sections, "Human input should have been delivered"
    assert any(e["injection_type"] == "hookless_human_input" for e in emitted_events), f"Expected hookless_human_input emission, got {emitted_events}"


@pytest.mark.asyncio
async def test_hookless_bg_tool_delivery_emits_event(mock_orchestrator, monkeypatch):
    """Delivering background tool results via hookless path should emit an event."""
    orchestrator = mock_orchestrator(num_agents=1)
    agent_id = "agent_a"

    orchestrator._no_hook_pending_background_tool_results[agent_id] = [
        {"job_id": "bg1", "tool_name": "my_tool", "status": "completed", "result": "ok"},
    ]

    emitted_events = []

    class _FakeEmitter:
        def emit_injection_received(self, agent_id, source_agents, injection_type):
            emitted_events.append({"agent_id": agent_id, "injection_type": injection_type})

    monkeypatch.setattr(
        "massgen.orchestrator.get_event_emitter",
        lambda: _FakeEmitter(),
    )

    sections = await orchestrator._collect_no_hook_runtime_fallback_sections(agent_id)

    assert sections, "Background tool results should have been delivered"
    assert any(e["injection_type"] == "hookless_bg_tool" for e in emitted_events), f"Expected hookless_bg_tool emission, got {emitted_events}"


# =============================================================================
# Backend capability contract tests (MAS-308)
# =============================================================================


def test_mock_llm_backend_classified_as_hookless(mock_orchestrator):
    """MockLLMBackend must classify as hookless so tests exercise the fallback path."""
    orchestrator = mock_orchestrator(num_agents=1)
    agent = orchestrator.agents["agent_a"]
    assert orchestrator._backend_supports_midstream_hook_injection(agent) is False


def test_backend_with_set_general_hook_manager_is_hook_capable(mock_orchestrator):
    """Any backend implementing set_general_hook_manager() is hook-capable."""
    orchestrator = mock_orchestrator(num_agents=1)

    class _GHMBackend:
        def set_general_hook_manager(self, m):
            pass

    class _Agent:
        backend = _GHMBackend()

    assert orchestrator._backend_supports_midstream_hook_injection(_Agent()) is True


# =============================================================================
# Full-round hookless integration test (MAS-308)
# =============================================================================


@pytest.mark.asyncio
async def test_hookless_runtime_input_delivered_at_next_safe_checkpoint(mock_orchestrator, monkeypatch):
    """Full round-trip: queue human input -> hookless enforcement -> delivered in enforcement msg."""
    from massgen.mcp_tools.hooks import HumanInputHook

    orchestrator = mock_orchestrator(num_agents=1)
    agent_id = "agent_a"
    state = orchestrator.agent_states[agent_id]
    state.restart_pending = True
    state.answer = "existing answer"

    # Ensure MockLLMBackend is hookless
    assert not orchestrator._backend_supports_midstream_hook_injection(
        orchestrator.agents[agent_id],
    )

    # Queue human input
    orchestrator._human_input_hook = HumanInputHook()
    orchestrator._human_input_hook.set_pending_input(
        "Add a section on limitations.",
        target_agents=[agent_id],
    )

    # No peer-answer updates
    monkeypatch.setattr(
        orchestrator,
        "_select_midstream_answer_updates",
        lambda _agent_id, _answers: ({}, False),
    )

    result = await orchestrator._prepare_no_hook_midstream_enforcement(agent_id, {})

    assert result is not None
    assert "limitations" in result, "Queued human input must appear in enforcement message"


# =============================================================================
# Runtime inbox polling integration tests (MAS-310)
# =============================================================================


@pytest.mark.asyncio
async def test_inbox_messages_fed_into_human_input_hook(mock_orchestrator, tmp_path, monkeypatch):
    """Create orchestrator with inbox poller, write message file, verify it surfaces
    in _collect_no_hook_runtime_fallback_sections()."""
    import json

    from massgen.mcp_tools.hooks import HumanInputHook, RuntimeInboxPoller

    orchestrator = mock_orchestrator(num_agents=1)
    agent_id = "agent_a"

    # Set up inbox poller on the orchestrator
    inbox_dir = tmp_path / ".massgen" / "runtime_inbox"
    inbox_dir.mkdir(parents=True)
    orchestrator._runtime_inbox_poller = RuntimeInboxPoller(
        inbox_dir=inbox_dir,
        min_poll_interval=0.0,
    )

    # Set up human input hook
    orchestrator._human_input_hook = HumanInputHook()

    # Write a message file to the inbox
    msg = {"content": "focus on edge cases", "source": "parent", "timestamp": "2025-01-01T00:00:00Z"}
    (inbox_dir / "msg_1740000000_1.json").write_text(json.dumps(msg))

    # Poll inbox and inject into human input hook (this is what the orchestrator does)
    messages = orchestrator._runtime_inbox_poller.poll()
    for m in messages:
        orchestrator._human_input_hook.set_pending_input(
            m["content"],
            target_agents=m.get("target_agents"),
        )

    # Stub event emitter
    monkeypatch.setattr(
        "massgen.orchestrator.get_event_emitter",
        lambda: None,
    )

    # Collect sections
    sections = await orchestrator._collect_no_hook_runtime_fallback_sections(agent_id)

    assert sections, "Inbox messages should produce runtime sections"
    combined = "\n".join(sections)
    assert "focus on edge cases" in combined, "Inbox message content must appear in sections"


@pytest.mark.asyncio
async def test_inbox_polling_in_codex_path(mock_orchestrator, tmp_path, monkeypatch):
    """Verify inbox messages appear in Codex hook file write path."""
    import json

    from massgen.mcp_tools.hooks import HumanInputHook, RuntimeInboxPoller

    orchestrator = mock_orchestrator(num_agents=1)
    agent_id = "agent_a"

    # Set up inbox poller
    inbox_dir = tmp_path / ".massgen" / "runtime_inbox"
    inbox_dir.mkdir(parents=True)
    orchestrator._runtime_inbox_poller = RuntimeInboxPoller(
        inbox_dir=inbox_dir,
        min_poll_interval=0.0,
    )

    # Set up human input hook
    orchestrator._human_input_hook = HumanInputHook()

    # Write inbox message
    msg = {"content": "skip CSS audit", "source": "parent", "timestamp": "2025-01-01T00:00:00Z"}
    (inbox_dir / "msg_1740000000_1.json").write_text(json.dumps(msg))

    # Simulate what _poll_runtime_inbox does
    messages = orchestrator._runtime_inbox_poller.poll()
    for m in messages:
        orchestrator._human_input_hook.set_pending_input(
            m["content"],
            target_agents=m.get("target_agents"),
        )

    # Verify it's now pending
    assert orchestrator._human_input_hook.has_pending_input()
    assert orchestrator._human_input_hook.has_pending_input_for_agent(agent_id)
