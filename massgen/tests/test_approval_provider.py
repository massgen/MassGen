"""Tests for ApprovalProvider implementations (the `ask` round-trip)."""

import pytest

from massgen.permissions import (
    ApprovalDecision,
    AuthorizationObject,
    AutomationDefault,
    RiskTier,
)
from massgen.permissions.approval_provider import (
    CallbackApprovalProvider,
    PolicyApprovalProvider,
)


def _authz(risk=RiskTier.MEDIUM, tool="execute_command", command="x"):
    return AuthorizationObject(agent_id="a1", tool=tool, arguments={"command": command}, risk=risk)


# --------------------------------------------------------------------------- #
# PolicyApprovalProvider — the automation/headless default
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_risk_based_denies_high_allows_low():
    p = PolicyApprovalProvider(AutomationDefault.RISK_BASED)
    assert (await p.request_approval(_authz(RiskTier.HIGH))).allowed is False
    assert (await p.request_approval(_authz(RiskTier.LOW))).allowed is True
    assert (await p.request_approval(_authz(RiskTier.MEDIUM))).allowed is True


@pytest.mark.asyncio
async def test_risk_based_deny_gives_feedback():
    p = PolicyApprovalProvider(AutomationDefault.RISK_BASED)
    d = await p.request_approval(_authz(RiskTier.HIGH, command="git push --force"))
    assert d.allowed is False
    assert d.feedback  # reason fed back to the agent
    assert d.operator == "policy"


@pytest.mark.asyncio
async def test_deny_all_and_allow_all():
    assert (await PolicyApprovalProvider(AutomationDefault.DENY_ALL).request_approval(_authz(RiskTier.LOW))).allowed is False
    assert (await PolicyApprovalProvider(AutomationDefault.ALLOW_ALL).request_approval(_authz(RiskTier.HIGH))).allowed is True


# --------------------------------------------------------------------------- #
# CallbackApprovalProvider — wraps an injected async decision fn (interactive TUI)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_callback_provider_delegates():
    async def cb(authz):
        return ApprovalDecision(allowed=True, operator="human")

    p = CallbackApprovalProvider(cb)
    d = await p.request_approval(_authz())
    assert d.allowed is True
    assert d.operator == "human"


@pytest.mark.asyncio
async def test_callback_provider_falls_back_on_error():
    async def cb(authz):
        raise RuntimeError("modal crashed")

    # On callback failure, fail closed (deny) — never silently allow.
    p = CallbackApprovalProvider(cb, fail_closed=True)
    d = await p.request_approval(_authz())
    assert d.allowed is False
