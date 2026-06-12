"""P2.1 — ApprovalLedger (append-only audit trail) + ApprovalBudget (runaway guard).

The ledger records every approval-flow decision as a JSONL line so a run's
permission decisions are auditable after the fact. The budget caps how many
consecutive auto-approvals one agent may accrue before its calls must be
re-surfaced (a runaway-loop circuit breaker).

All opt-in: a PermissionCoordinator with no ledger behaves exactly as before.
"""

from __future__ import annotations

import json

import pytest

from massgen.permissions.approval_provider import PolicyApprovalProvider
from massgen.permissions.coordinator import PermissionCoordinator
from massgen.permissions.ledger import ApprovalBudget, ApprovalLedger
from massgen.permissions.models import (
    ApprovalDecision,
    AuthorizationObject,
    AutomationDefault,
    GrantScope,
    RiskTier,
)


# --------------------------------------------------------------------------- #
# ApprovalLedger — append-only JSONL
# --------------------------------------------------------------------------- #
def _authz(**kw):
    base = dict(
        agent_id="agent-a",
        tool="bash",
        arguments={"command": "git status"},
        normalized_pattern="command:git status",
        risk=RiskTier.LOW,
        reason="status check",
        args_preview="$ git status",
    )
    base.update(kw)
    return AuthorizationObject(**base)


def test_record_appends_one_jsonl_line_per_call(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = ApprovalLedger(path, run_id="run-1")
    ledger.record(_authz(), allowed=True, operator="human", scope=GrantScope.ONCE, source="provider")
    ledger.record(
        _authz(tool="write_file"),
        allowed=False,
        operator="policy",
        scope=GrantScope.ONCE,
        source="provider",
        feedback="too risky",
    )
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["run_id"] == "run-1"
    assert first["agent_id"] == "agent-a"
    assert first["tool"] == "bash"
    assert first["normalized_pattern"] == "command:git status"
    assert first["decision"] == "allow"
    assert first["operator"] == "human"
    assert first["scope"] == "once"
    assert first["risk"] == "low"
    assert first["source"] == "provider"
    assert first["seq"] == 0
    assert "timestamp" in first
    second = json.loads(lines[1])
    assert second["decision"] == "deny"
    assert second["feedback"] == "too risky"
    assert second["seq"] == 1


def test_ledger_is_append_only_across_instances(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ApprovalLedger(path, run_id="r").record(_authz(), allowed=True, operator="human", scope=GrantScope.ONCE, source="provider")
    # A fresh instance pointed at the same file must append, not truncate.
    ApprovalLedger(path, run_id="r").record(_authz(), allowed=True, operator="cache", scope=GrantScope.SESSION, source="cache")
    assert len(path.read_text().strip().splitlines()) == 2


def test_entries_reads_back_in_order(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = ApprovalLedger(path, run_id="r")
    ledger.record(_authz(tool="a"), allowed=True, operator="human", scope=GrantScope.ONCE, source="provider")
    ledger.record(_authz(tool="b"), allowed=False, operator="policy", scope=GrantScope.ONCE, source="provider")
    tools = [e["tool"] for e in ledger.entries()]
    assert tools == ["a", "b"]


# --------------------------------------------------------------------------- #
# Coordinator integration — opt-in
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_coordinator_records_provider_decision(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = ApprovalLedger(path, run_id="run-x")
    coord = PermissionCoordinator(
        PolicyApprovalProvider(AutomationDefault.ALLOW_ALL),
        ledger=ledger,
    )
    allowed, _ = await coord.resolve_ask("agent-a", "bash", {"command": "echo hi"}, reason="r")
    assert allowed is True
    entries = ledger.entries()
    assert len(entries) == 1
    assert entries[0]["source"] == "provider"
    assert entries[0]["decision"] == "allow"
    assert entries[0]["operator"] == "policy"


@pytest.mark.asyncio
async def test_coordinator_records_cache_hit(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = ApprovalLedger(path, run_id="run-x")

    class _SessionGranter(PolicyApprovalProvider):
        async def request_approval(self, authz):
            return ApprovalDecision(allowed=True, scope=GrantScope.SESSION, operator="human")

    coord = PermissionCoordinator(_SessionGranter(), ledger=ledger)
    await coord.resolve_ask("agent-a", "bash", {"command": "ls"}, reason="r")  # provider → grants session
    await coord.resolve_ask("agent-a", "bash", {"command": "ls"}, reason="r")  # cache hit
    sources = [e["source"] for e in ledger.entries()]
    assert sources == ["provider", "cache"]
    assert ledger.entries()[1]["operator"] == "cache"


@pytest.mark.asyncio
async def test_coordinator_without_ledger_unchanged(tmp_path):
    # No ledger → no file, no error (default behavior preserved).
    coord = PermissionCoordinator(PolicyApprovalProvider(AutomationDefault.ALLOW_ALL))
    allowed, _ = await coord.resolve_ask("agent-a", "bash", {"command": "echo hi"})
    assert allowed is True
    assert not list(tmp_path.iterdir())


# --------------------------------------------------------------------------- #
# ApprovalBudget — runaway-loop circuit breaker
# --------------------------------------------------------------------------- #
def test_budget_allows_until_cap_then_trips():
    budget = ApprovalBudget(max_consecutive_auto=3)
    assert budget.check_auto("agent-a") is True  # 1
    assert budget.check_auto("agent-a") is True  # 2
    assert budget.check_auto("agent-a") is True  # 3
    assert budget.check_auto("agent-a") is False  # 4 → over cap


def test_budget_is_per_agent():
    budget = ApprovalBudget(max_consecutive_auto=1)
    assert budget.check_auto("agent-a") is True
    assert budget.check_auto("agent-b") is True  # separate counter
    assert budget.check_auto("agent-a") is False


def test_budget_resets_on_human_decision():
    budget = ApprovalBudget(max_consecutive_auto=2)
    assert budget.check_auto("agent-a") is True
    assert budget.check_auto("agent-a") is True
    budget.reset("agent-a")  # a human checkpoint clears the streak
    assert budget.check_auto("agent-a") is True
    assert budget.check_auto("agent-a") is True
