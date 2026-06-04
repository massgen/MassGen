#!/usr/bin/env python3
"""Tests for the Grok backend.

E2 fix: this file previously held three async functions that ``print()``-ed and
returned ``True/False`` with no assertions. Under ``asyncio_mode=auto`` they were
collected and passed silently (the return value was consumed by pytest-asyncio),
giving keyless duplicate coverage with no regression-detection value.

Now:
  - the metadata/token/cost surface is a real **offline** unit test (no key, no
    network, no cost), so it runs in the default suite;
  - the streaming and agent paths are proper ``live_api`` tests that skip without
    ``XAI_API_KEY`` and assert on real responses (they do NOT run by default, so
    no external cost is incurred unless explicitly enabled).
"""

from __future__ import annotations

import os

import pytest

from massgen.backend.grok import GrokBackend
from massgen.chat_agent import SingleAgent


def test_grok_backend_metadata_offline() -> None:
    """Provider name, builtin tools, token estimation, and cost calc (no network)."""
    backend = GrokBackend(api_key="dummy-key-offline")

    assert backend.get_provider_name() == "Grok"

    tools = backend.get_supported_builtin_tools()
    assert isinstance(tools, list) and tools, "expected at least one builtin tool"

    tokens = backend.estimate_tokens("Hello world, this is a test message")
    assert isinstance(tokens, int) and tokens > 0

    cost = backend.calculate_cost(100, 50, "grok-3-mini")
    assert isinstance(cost, float) and cost > 0.0


@pytest.mark.live_api
@pytest.mark.asyncio
async def test_grok_streaming_live() -> None:
    """Streaming returns non-empty content with no error chunk (requires XAI_API_KEY)."""
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        pytest.skip("XAI_API_KEY not set")

    backend = GrokBackend(api_key=api_key)
    messages = [{"role": "user", "content": "Say hello in one short sentence."}]

    response_content = ""
    async for chunk in backend.stream_with_tools(messages, tools=[], model="grok-3-mini"):
        if chunk.type == "content" and chunk.content:
            response_content += chunk.content
        elif chunk.type == "error":
            pytest.fail(f"Grok streaming returned an error chunk: {chunk.error}")

    assert response_content.strip()


@pytest.mark.live_api
@pytest.mark.asyncio
async def test_grok_with_agent_live() -> None:
    """SingleAgent over Grok returns content with no error chunk (requires XAI_API_KEY)."""
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        pytest.skip("XAI_API_KEY not set")

    backend = GrokBackend(api_key=api_key)
    agent = SingleAgent(
        backend=backend,
        system_message="You are a helpful AI assistant.",
        agent_id="test_grok_agent",
    )

    response_content = ""
    async for chunk in agent.chat([{"role": "user", "content": "What is 2+2? Answer briefly."}]):
        if chunk.type == "content" and chunk.content:
            response_content += chunk.content
        elif chunk.type == "error":
            pytest.fail(f"Grok agent returned an error chunk: {chunk.error}")

    assert response_content.strip()
