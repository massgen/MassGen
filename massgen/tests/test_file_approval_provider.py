"""Tests for FileApprovalProvider — headless/remote approval via request/response JSON."""

import json

import pytest

from massgen.permissions import AuthorizationObject, GrantScope, RiskTier
from massgen.permissions.approval_provider import FileApprovalProvider


def _authz(**kw):
    base = dict(agent_id="a1", tool="execute_command", arguments={"command": "x"}, normalized_pattern="command:x")
    base.update(kw)
    return AuthorizationObject(**base)


@pytest.mark.asyncio
async def test_writes_request_file_and_times_out_fail_closed(tmp_path):
    p = FileApprovalProvider(tmp_path, poll_interval=0.02, timeout=0.15)
    d = await p.request_approval(_authz(reason="why", risk=RiskTier.HIGH))
    assert d.allowed is False  # no response → timeout → deny (fail-closed)
    reqs = list(tmp_path.glob("req_*.json"))
    assert reqs, "a request file must be written for an external approver"
    data = json.loads(reqs[0].read_text())
    assert data["tool"] == "execute_command"
    assert data["risk"] == "high"
    assert data["reason"] == "why"


@pytest.mark.asyncio
async def test_reads_an_existing_approve_response(tmp_path):
    p = FileApprovalProvider(tmp_path, poll_interval=0.02, timeout=2.0)
    authz = _authz()
    rid = p.request_id(authz)
    (tmp_path / f"resp_{rid}.json").write_text(json.dumps({"approved": True, "scope": "session"}))
    d = await p.request_approval(authz)
    assert d.allowed is True
    assert d.scope == GrantScope.SESSION
    assert d.operator == "human"


@pytest.mark.asyncio
async def test_reads_a_deny_response_with_feedback(tmp_path):
    p = FileApprovalProvider(tmp_path, poll_interval=0.02, timeout=2.0)
    authz = _authz()
    rid = p.request_id(authz)
    (tmp_path / f"resp_{rid}.json").write_text(json.dumps({"approved": False, "feedback": "nope"}))
    d = await p.request_approval(authz)
    assert d.allowed is False
    assert d.feedback == "nope"


@pytest.mark.asyncio
async def test_response_is_consumed(tmp_path):
    p = FileApprovalProvider(tmp_path, poll_interval=0.02, timeout=0.15)
    authz = _authz()
    rid = p.request_id(authz)
    (tmp_path / f"resp_{rid}.json").write_text(json.dumps({"approved": True}))
    assert (await p.request_approval(authz)).allowed is True
    # response file consumed → a second ask re-prompts (and here times out → deny)
    assert (await p.request_approval(authz)).allowed is False


@pytest.mark.asyncio
async def test_request_id_is_stable_per_logical_request(tmp_path):
    p = FileApprovalProvider(tmp_path)
    assert p.request_id(_authz()) == p.request_id(_authz())
    assert p.request_id(_authz()) != p.request_id(_authz(normalized_pattern="command:rm"))
