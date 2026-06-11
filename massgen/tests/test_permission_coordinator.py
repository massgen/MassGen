"""Tests for PermissionCoordinator — the ask→approval resolution brain."""

import pytest

from massgen.permissions import (
    ApprovalDecision,
    AutomationDefault,
    GrantScope,
    RiskTier,
)
from massgen.permissions.approval_provider import PolicyApprovalProvider
from massgen.permissions.coordinator import PermissionCoordinator


class _RecordingProvider:
    def __init__(self, decision):
        self.decision = decision
        self.calls = 0

    async def request_approval(self, authz):
        self.calls += 1
        self.last_authz = authz
        return self.decision


@pytest.mark.asyncio
async def test_resolve_ask_allow_proceeds():
    prov = _RecordingProvider(ApprovalDecision(allowed=True, scope=GrantScope.ONCE))
    c = PermissionCoordinator(provider=prov)
    allowed, feedback = await c.resolve_ask("a1", "execute_command", {"command": "python x.py"})
    assert allowed is True
    assert prov.calls == 1


@pytest.mark.asyncio
async def test_resolve_ask_deny_returns_feedback():
    prov = _RecordingProvider(ApprovalDecision(allowed=False, feedback="nope"))
    c = PermissionCoordinator(provider=prov)
    allowed, feedback = await c.resolve_ask("a1", "execute_command", {"command": "git push --force"})
    assert allowed is False
    assert feedback == "nope"


@pytest.mark.asyncio
async def test_session_grant_suppresses_second_ask():
    prov = _RecordingProvider(ApprovalDecision(allowed=True, scope=GrantScope.SESSION))
    c = PermissionCoordinator(provider=prov)
    await c.resolve_ask("a1", "execute_command", {"command": "make build"})
    await c.resolve_ask("a1", "execute_command", {"command": "make build"})  # identical
    assert prov.calls == 1  # 2nd resolved from cache, provider not called again


@pytest.mark.asyncio
async def test_once_grant_does_not_persist():
    prov = _RecordingProvider(ApprovalDecision(allowed=True, scope=GrantScope.ONCE))
    c = PermissionCoordinator(provider=prov)
    await c.resolve_ask("a1", "t", {"command": "x"})
    await c.resolve_ask("a1", "t", {"command": "x"})
    assert prov.calls == 2  # once-grant not cached for the next call


@pytest.mark.asyncio
async def test_authz_carries_classified_risk():
    prov = _RecordingProvider(ApprovalDecision(allowed=True))
    c = PermissionCoordinator(provider=prov)
    await c.resolve_ask("a1", "execute_command", {"command": "git push --force"})
    assert prov.last_authz.risk == RiskTier.HIGH


@pytest.mark.asyncio
async def test_always_grant_persists_via_callback():
    persisted = []
    prov = _RecordingProvider(ApprovalDecision(allowed=True, scope=GrantScope.ALWAYS))
    c = PermissionCoordinator(provider=prov, persist_always=lambda authz, dec: persisted.append(authz))
    await c.resolve_ask("a1", "execute_command", {"command": "make build"})
    assert len(persisted) == 1


@pytest.mark.asyncio
async def test_end_to_end_with_policy_provider():
    # risk-based automation: high denied, medium allowed.
    c = PermissionCoordinator(provider=PolicyApprovalProvider(AutomationDefault.RISK_BASED))
    assert (await c.resolve_ask("a1", "execute_command", {"command": "git push --force"}))[0] is False
    assert (await c.resolve_ask("a1", "execute_command", {"command": "python x.py"}))[0] is True
