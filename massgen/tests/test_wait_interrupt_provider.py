"""Tests for the deduplicated background-wait interrupt provider.

The three hook-setup paths (GeneralHookManager, Codex MCP, native) used to each
inline an identical ``_wait_interrupt_provider`` closure. They now share
``MidStreamInjectionHookInstaller._install_wait_interrupt_provider``. These tests
pin the consolidated contract so the single implementation can't silently drift:

  * it registers a provider on backends that support it (and no-ops otherwise),
  * cancelled turn  -> ``turn_cancelled`` with no content,
  * runtime sections present -> ``runtime_injection_available`` with joined content,
  * no sections -> ``None``.
"""

from __future__ import annotations

import types
from unittest.mock import AsyncMock

import pytest

from massgen.orchestrator_collaborators.midstream_injection_hook_installer import (
    MidStreamInjectionHookInstaller,
)


def _installer(orch) -> MidStreamInjectionHookInstaller:
    inst = MidStreamInjectionHookInstaller.__new__(MidStreamInjectionHookInstaller)
    inst._orchestrator = orch
    return inst


def _agent_with_capture():
    captured: dict = {}

    def _set(provider):
        captured["provider"] = provider

    backend = types.SimpleNamespace(set_background_wait_interrupt_provider=_set)
    return types.SimpleNamespace(backend=backend), captured


def test_provider_registered_when_backend_supports_it():
    orch = types.SimpleNamespace()
    agent, captured = _agent_with_capture()
    _installer(orch)._install_wait_interrupt_provider(agent, "agentA")
    assert callable(captured.get("provider"))


def test_no_op_when_backend_unsupported():
    orch = types.SimpleNamespace()
    # backend without set_background_wait_interrupt_provider must not raise.
    agent = types.SimpleNamespace(backend=types.SimpleNamespace())
    _installer(orch)._install_wait_interrupt_provider(agent, "agentA")  # no exception


@pytest.mark.asyncio
async def test_provider_returns_turn_cancelled_when_cancelled():
    orch = types.SimpleNamespace(
        cancellation_manager=types.SimpleNamespace(is_cancelled=True),
        _collect_no_hook_runtime_fallback_sections=AsyncMock(return_value=["unused"]),
    )
    agent, captured = _agent_with_capture()
    _installer(orch)._install_wait_interrupt_provider(agent, "agentA")
    result = await captured["provider"]("agentA")
    assert result == {"interrupt_reason": "turn_cancelled", "injected_content": None}


@pytest.mark.asyncio
async def test_provider_returns_runtime_injection_when_sections_present():
    orch = types.SimpleNamespace(
        cancellation_manager=types.SimpleNamespace(is_cancelled=False),
        _collect_no_hook_runtime_fallback_sections=AsyncMock(return_value=["sec1", "sec2"]),
    )
    agent, captured = _agent_with_capture()
    _installer(orch)._install_wait_interrupt_provider(agent, "agentA")
    result = await captured["provider"]("agentA")
    assert result["interrupt_reason"] == "runtime_injection_available"
    assert result["injected_content"] == "sec1\nsec2"


@pytest.mark.asyncio
async def test_provider_returns_none_when_no_sections():
    orch = types.SimpleNamespace(
        cancellation_manager=types.SimpleNamespace(is_cancelled=False),
        _collect_no_hook_runtime_fallback_sections=AsyncMock(return_value=[]),
    )
    agent, captured = _agent_with_capture()
    _installer(orch)._install_wait_interrupt_provider(agent, "agentA")
    assert await captured["provider"]("agentA") is None


@pytest.mark.asyncio
async def test_provider_falls_back_to_installed_agent_id():
    """When the runtime asks with an empty requested id, the install-time id is used."""
    collect = AsyncMock(return_value=[])
    orch = types.SimpleNamespace(
        cancellation_manager=types.SimpleNamespace(is_cancelled=False),
        _collect_no_hook_runtime_fallback_sections=collect,
    )
    agent, captured = _agent_with_capture()
    _installer(orch)._install_wait_interrupt_provider(agent, "agentA")
    await captured["provider"]("")  # empty requested id
    collect.assert_awaited_once_with("agentA")
