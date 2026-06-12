"""Tests for the interactive tool-approval modal mapping + its TUI wiring."""

from massgen.frontend.displays.textual.widgets.modals.tool_approval_modal import (
    decision_for_action,
)
from massgen.permissions.approval_provider import (
    CallbackApprovalProvider,
    PolicyApprovalProvider,
)
from massgen.permissions.coordinator import PermissionCoordinator
from massgen.permissions.models import GrantScope


# --------------------------------------------------------------------------- #
# Pure button → ApprovalDecision mapping (no TUI needed)
# --------------------------------------------------------------------------- #
def test_decision_for_action_allow_scopes():
    assert decision_for_action("allow_once").scope == GrantScope.ONCE
    assert decision_for_action("allow_session").scope == GrantScope.SESSION
    assert decision_for_action("allow_always").scope == GrantScope.ALWAYS
    for a in ("allow_once", "allow_session", "allow_always"):
        d = decision_for_action(a)
        assert d.allowed is True
        assert d.operator == "human"


def test_decision_for_action_reject_and_unknown_deny():
    assert decision_for_action("reject").allowed is False
    assert decision_for_action("reject").feedback
    # Unknown / closed-without-choice → fail safe (deny).
    assert decision_for_action("???").allowed is False


# --------------------------------------------------------------------------- #
# Wiring: CoordinationUI swaps in a modal-backed provider for guarded agents
# --------------------------------------------------------------------------- #
class _Disp:
    async def show_tool_approval_modal(self, authz):  # pragma: no cover - not invoked here
        from massgen.permissions.models import ApprovalDecision

        return ApprovalDecision(allowed=True, operator="human")


class _Backend:
    def __init__(self, with_coordinator=True):
        self._permission_coordinator = PermissionCoordinator(provider=PolicyApprovalProvider()) if with_coordinator else None

    def set_approval_provider(self, p):
        if self._permission_coordinator is not None:
            self._permission_coordinator.provider = p


class _Agent:
    def __init__(self, **kw):
        self.backend = _Backend(**kw)


class _Orch:
    def __init__(self, agents):
        self.agents = agents


def _ui(display, config):
    from massgen.frontend.coordination_ui import CoordinationUI

    ui = CoordinationUI.__new__(CoordinationUI)
    ui.display = display
    ui.config = config
    return ui


def test_interactive_provider_installed_for_guarded_agent():
    agent = _Agent()
    ui = _ui(_Disp(), {})
    ui._install_interactive_approval_provider(_Orch({"a1": agent}))
    assert isinstance(agent.backend._permission_coordinator.provider, CallbackApprovalProvider)


def test_noop_in_automation_mode():
    agent = _Agent()
    ui = _ui(_Disp(), {"automation_mode": True})
    ui._install_interactive_approval_provider(_Orch({"a1": agent}))
    # provider unchanged (still the automation policy)
    assert isinstance(agent.backend._permission_coordinator.provider, PolicyApprovalProvider)


def test_noop_for_agent_without_coordinator():
    agent = _Agent(with_coordinator=False)
    ui = _ui(_Disp(), {})
    # should not raise, and nothing to swap
    ui._install_interactive_approval_provider(_Orch({"a1": agent}))
    assert agent.backend._permission_coordinator is None


def test_noop_when_display_lacks_modal_method():
    agent = _Agent()
    ui = _ui(object(), {})  # display without show_tool_approval_modal
    ui._install_interactive_approval_provider(_Orch({"a1": agent}))
    assert isinstance(agent.backend._permission_coordinator.provider, PolicyApprovalProvider)


def test_interactive_swap_does_not_override_file_provider(tmp_path):
    from massgen.permissions.approval_provider import FileApprovalProvider

    agent = _Agent()
    agent.backend._permission_coordinator.provider = FileApprovalProvider(tmp_path)
    ui = _ui(_Disp(), {})
    ui._install_interactive_approval_provider(_Orch({"a1": agent}))
    # a file/remote provider stays in place even under a TUI
    assert isinstance(agent.backend._permission_coordinator.provider, FileApprovalProvider)
