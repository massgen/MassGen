"""Regression coverage for ChatCompletionsBackend provider wiring."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from massgen.backend import ChatCompletionsBackend
from massgen.backend.base_with_custom_tool_and_mcp import (
    BACKGROUND_TOOL_CANCEL_NAME,
    BACKGROUND_TOOL_LIST_NAME,
    BACKGROUND_TOOL_RESULT_NAME,
    BACKGROUND_TOOL_START_NAME,
    BACKGROUND_TOOL_STATUS_NAME,
    BACKGROUND_TOOL_WAIT_NAME,
)


def test_openai_backend_defaults():
    """Default backend should use generic provider settings."""
    backend = ChatCompletionsBackend()
    assert backend.get_provider_name() == "ChatCompletion"
    assert "base_url" not in backend.config
    assert backend.estimate_tokens("Hello world, how are you doing today?") > 0
    assert backend.calculate_cost(1000, 500, "gpt-4o-mini") >= 0


def test_together_ai_backend():
    """Provider should be inferred from Together base URL."""
    backend = ChatCompletionsBackend(
        base_url="https://api.together.xyz/v1",
        api_key="test-key",
    )
    assert backend.get_provider_name() == "Together AI"
    assert backend.config["base_url"] == "https://api.together.xyz/v1"
    assert backend.calculate_cost(1000, 500, "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo") >= 0


def test_cerebras_backend():
    """Provider should be inferred from Cerebras base URL."""
    backend = ChatCompletionsBackend(
        base_url="https://api.cerebras.ai/v1",
        api_key="test-key",
    )
    assert backend.get_provider_name() == "Cerebras AI"
    assert backend.config["base_url"] == "https://api.cerebras.ai/v1"


@pytest.mark.asyncio
async def test_tool_conversion_via_api_params_handler():
    """Response-style function tools are converted via ChatCompletionsAPIParamsHandler."""
    backend = ChatCompletionsBackend(api_key="test-key")
    tools = [
        {
            "type": "function",
            "name": "calculate_area",
            "description": "Calculate area of rectangle",
            "parameters": {
                "type": "object",
                "properties": {
                    "width": {"type": "number"},
                    "height": {"type": "number"},
                },
                "required": ["width", "height"],
            },
        },
    ]

    api_params = await backend.api_params_handler.build_api_params(
        messages=[{"role": "user", "content": "Calculate area for width 5 and height 3"}],
        tools=tools,
        all_params={"model": "gpt-4o-mini"},
    )

    assert "tools" in api_params
    tool_names = {tool["function"]["name"] for tool in api_params["tools"] if tool.get("type") == "function" and "function" in tool}
    assert "calculate_area" in tool_names
    assert BACKGROUND_TOOL_START_NAME in tool_names
    assert BACKGROUND_TOOL_STATUS_NAME in tool_names
    assert BACKGROUND_TOOL_RESULT_NAME in tool_names
    assert BACKGROUND_TOOL_CANCEL_NAME in tool_names
    assert BACKGROUND_TOOL_LIST_NAME in tool_names
    assert BACKGROUND_TOOL_WAIT_NAME in tool_names


def _make_chat_completion_chunk(
    *,
    delta: SimpleNamespace | None = None,
    finish_reason: str | None = None,
    usage: SimpleNamespace | None = None,
) -> SimpleNamespace:
    choice = None
    if delta is not None or finish_reason is not None:
        choice = SimpleNamespace(delta=delta, finish_reason=finish_reason)
    return SimpleNamespace(
        choices=[choice] if choice is not None else [],
        usage=usage,
    )


async def _yield_chunks(chunks):
    for chunk in chunks:
        yield chunk


@pytest.mark.asyncio
async def test_stream_with_custom_tools_deduplicates_duplicate_tool_call_ids(monkeypatch: pytest.MonkeyPatch):
    """Duplicate streamed call IDs should execute once and recurse with one tool result."""
    backend = ChatCompletionsBackend(
        api_key="test-key",
        base_url="https://openrouter.ai/api/v1",
        model="minimax/minimax-m2.7",
    )
    backend._mcp_functions = {"mcp__filesystem__write_file": object()}
    backend._custom_tool_names = set()

    recorded_message_batches: list[list[dict]] = []

    async def fake_build_api_params(messages, tools, all_params):  # noqa: ARG001
        recorded_message_batches.append(deepcopy(messages))
        return {
            "model": "minimax/minimax-m2.7",
            "stream": True,
        }

    monkeypatch.setattr(
        backend.api_params_handler,
        "build_api_params",
        fake_build_api_params,
    )
    monkeypatch.setattr(
        backend,
        "_check_circuit_breaker_before_execution",
        AsyncMock(return_value=True),
    )

    executed_calls: list[tuple[str, str]] = []

    async def fake_execute_mcp(name: str, arguments: str):
        executed_calls.append((name, arguments))
        return "Successfully wrote file", None

    monkeypatch.setattr(backend, "_execute_mcp_function_with_retry", fake_execute_mcp)

    tool_name = "mcp__filesystem__write_file"
    tool_args = '{"path":"dsa_interview.py","content":"hello"}'
    tool_function = SimpleNamespace(name=tool_name, arguments=tool_args)
    first_stream = [
        _make_chat_completion_chunk(
            delta=SimpleNamespace(
                content=None,
                tool_calls=[
                    SimpleNamespace(index=0, id="call_duplicate", function=tool_function),
                    SimpleNamespace(index=1, id="call_duplicate", function=tool_function),
                ],
            ),
        ),
        _make_chat_completion_chunk(finish_reason="tool_calls"),
        _make_chat_completion_chunk(
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        ),
    ]
    second_stream = [
        _make_chat_completion_chunk(delta=SimpleNamespace(content="done", tool_calls=None)),
        _make_chat_completion_chunk(finish_reason="stop"),
        _make_chat_completion_chunk(
            usage=SimpleNamespace(prompt_tokens=3, completion_tokens=1, total_tokens=4),
        ),
    ]

    backend.circuit_breaker.call_with_retry = AsyncMock(
        side_effect=[
            _yield_chunks(first_stream),
            _yield_chunks(second_stream),
        ],
    )

    chunks = [
        chunk
        async for chunk in backend._stream_with_custom_and_mcp_tools(
            current_messages=[{"role": "user", "content": "Create the file"}],
            tools=[],
            client=MagicMock(),
            agent_id="agent_a",
            concurrent_tool_execution=True,
        )
    ]

    tool_calls_chunk = next(chunk for chunk in chunks if chunk.type == "tool_calls")
    assert len(tool_calls_chunk.tool_calls) == 1
    assert tool_calls_chunk.tool_calls[0]["id"] == "call_duplicate"

    assert executed_calls == [(tool_name, tool_args)]

    assert len(recorded_message_batches) == 2
    recursive_messages = recorded_message_batches[1]

    assistant_tool_message = next(message for message in recursive_messages if message.get("role") == "assistant" and message.get("tool_calls"))
    assert len(assistant_tool_message["tool_calls"]) == 1
    assert assistant_tool_message["tool_calls"][0]["id"] == "call_duplicate"

    tool_results = [message for message in recursive_messages if message.get("role") == "tool"]
    assert len(tool_results) == 1
    assert tool_results[0]["tool_call_id"] == "call_duplicate"
