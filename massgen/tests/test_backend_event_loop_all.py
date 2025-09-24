#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Event loop/resource cleanup tests for multiple backends without changing code.
These tests mock SDK async clients and assert aclose() is awaited by backends.

Backends covered:
- ResponseBackend (OpenAI Responses API)
- GrokBackend (xAI via OpenAI-compatible client)
- ClaudeBackend (Anthropic Messages API)

NOTE: Some tests may currently FAIL, revealing missing cleanup in backends.
"""

import asyncio
from types import SimpleNamespace
from typing import Any, List

import pytest

from massgen.backend import ClaudeBackend, GrokBackend, ResponseBackend


# ---- Common fakes ----
class _FakeStreamSingleStop:
    """Async stream that yields once, then stops. Shape varies per backend needs."""

    def __init__(self, item_factory):
        self._yielded = False
        self._item_factory = item_factory

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._yielded:
            raise StopAsyncIteration
        self._yielded = True
        await asyncio.sleep(0)
        return self._item_factory()


class _FakeAsyncClientBase:
    def __init__(self, *args: Any, **kwargs: Any):
        self.args = args
        self.kwargs = kwargs
        self._closed = False

    async def aclose(self) -> None:
        await asyncio.sleep(0)
        self._closed = True


# ---- ResponseBackend test ----
class _FakeResponses:
    async def create(self, **kwargs: Any):
        # Build a stream where each chunk has a 'type' attribute that ends the response quickly
        def _item():
            return SimpleNamespace(type="response.completed", response={"output": []})

        return _FakeStreamSingleStop(_item)


class _FakeOpenAIClient(_FakeAsyncClientBase):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.responses = _FakeResponses()


@pytest.mark.asyncio
async def test_response_backend_stream_closes_client(monkeypatch):
    import sys

    created: List[_FakeOpenAIClient] = []

    def _factory(*args: Any, **kwargs: Any) -> _FakeOpenAIClient:
        client = _FakeOpenAIClient(*args, **kwargs)
        created.append(client)
        return client

    # Inject fake openai module so in-function import resolves to our factory
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(AsyncOpenAI=_factory))

    backend = ResponseBackend()

    messages = [{"role": "user", "content": "hi"}]

    # Drain the stream
    async for _ in backend.stream_with_tools(messages, tools=[], model="gpt-4o-mini"):
        pass

    assert len(created) == 1
    # Expectation: backend should close client to avoid event-loop errors
    assert created[0]._closed is True


# ---- GrokBackend test ----
class _FakeChatCompletions:
    async def create(self, **kwargs: Any):
        # Yield a single finishing chunk similar to Chat Completions
        def _item():
            choice = SimpleNamespace(delta=None, finish_reason="stop")
            return SimpleNamespace(choices=[choice], usage=None)

        return _FakeStreamSingleStop(_item)


class _FakeOpenAIClientForGrok(_FakeAsyncClientBase):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.chat = SimpleNamespace(completions=_FakeChatCompletions())


@pytest.mark.asyncio
async def test_grok_backend_stream_closes_client(monkeypatch):
    import sys

    created: List[_FakeOpenAIClientForGrok] = []

    def _factory(*args: Any, **kwargs: Any) -> _FakeOpenAIClientForGrok:
        client = _FakeOpenAIClientForGrok(*args, **kwargs)
        created.append(client)
        return client

    # Inject fake openai module for dynamic import inside function
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(AsyncOpenAI=_factory))

    backend = GrokBackend()
    messages = [{"role": "user", "content": "hi"}]

    async for _ in backend.stream_with_tools(messages, tools=[], model="grok-2-mini"):
        pass

    assert len(created) == 1
    # Expectation: backend should close client to avoid event-loop errors
    assert created[0]._closed is True


# ---- ClaudeBackend test ----
class _FakeClaudeMessages:
    async def create(self, **kwargs: Any):
        # Stream that yields a single message_stop event
        def _item():
            return SimpleNamespace(type="message_stop")

        return _FakeStreamSingleStop(_item)


class _FakeAnthropicClient(_FakeAsyncClientBase):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        # Provide both .messages and .beta.messages to cover branches
        self.messages = _FakeClaudeMessages()
        self.beta = SimpleNamespace(messages=_FakeClaudeMessages())


@pytest.mark.asyncio
async def test_claude_backend_stream_closes_client(monkeypatch):
    import sys

    created: List[_FakeAnthropicClient] = []

    def _factory(*args: Any, **kwargs: Any) -> _FakeAnthropicClient:
        client = _FakeAnthropicClient(*args, **kwargs)
        created.append(client)
        return client

    # Inject fake anthropic module for dynamic import inside function
    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(AsyncAnthropic=_factory))

    backend = ClaudeBackend()
    messages = [{"role": "user", "content": "hi"}]

    async for _ in backend.stream_with_tools(messages, tools=[], model="claude-3.7-sonnet"):
        pass

    assert len(created) == 1
    # Expectation: backend should close client to avoid event-loop errors
    assert created[0]._closed is True
