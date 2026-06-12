"""Interactive "approve this tool call?" modal.

Mirrors the change-review modal flow: a ModalScreen parameterized by the result
type (``ApprovalDecision``), dismissed with the operator's choice. Shown via
``TextualTerminalDisplay.show_tool_approval_modal`` (the Future/call_from_thread
bridge), which the permission system reaches through a ``CallbackApprovalProvider``.
"""

from __future__ import annotations

from massgen.permissions.models import ApprovalDecision, AuthorizationObject, GrantScope

# Map a button/action id → the resulting ApprovalDecision. Pure + testable without a
# running TUI.
_ACTION_TO_DECISION = {
    "allow_once": (True, GrantScope.ONCE),
    "allow_session": (True, GrantScope.SESSION),
    "allow_always": (True, GrantScope.ALWAYS),
    "reject": (False, GrantScope.ONCE),
}


def decision_for_action(action: str) -> ApprovalDecision:
    """Translate a modal action id into an ApprovalDecision (operator='human')."""
    allowed, scope = _ACTION_TO_DECISION.get(action, (False, GrantScope.ONCE))
    return ApprovalDecision(
        allowed=allowed,
        scope=scope,
        feedback=None if allowed else "Rejected by user.",
        operator="human",
    )


try:
    from textual.app import ComposeResult
    from textual.containers import Container, Horizontal
    from textual.screen import ModalScreen
    from textual.widgets import Button, Static

    TEXTUAL_AVAILABLE = True
except ImportError:  # pragma: no cover - textual always present in TUI runs
    TEXTUAL_AVAILABLE = False
    ModalScreen = object  # type: ignore
    ComposeResult = None  # type: ignore


if TEXTUAL_AVAILABLE:

    class ToolApprovalModal(ModalScreen):  # ModalScreen[ApprovalDecision]
        """Ask the operator to approve/deny a single tool call."""

        BINDINGS = [
            ("escape", "reject", "Reject"),
            ("1", "allow_once", "Allow once"),
            ("2", "allow_session", "Allow session"),
            ("a", "allow_always", "Always allow"),
        ]

        def __init__(self, authz: AuthorizationObject, **kwargs) -> None:
            super().__init__(**kwargs)
            self._authz = authz

        def compose(self) -> ComposeResult:  # type: ignore[override]
            a = self._authz
            risk = a.risk.value.upper()
            with Container(classes="modal-container", id="tool_approval_container"):
                yield Static(f"⚠️  Approval required — {risk} risk", classes="modal-title")
                yield Static(f"Agent: {a.agent_id or '?'}    Tool: {a.tool}", classes="modal-subtitle")
                yield Static(a.args_preview or a.reason or "(no preview)", classes="modal-body")
                if a.reason:
                    yield Static(a.reason, classes="modal-reason")
                with Horizontal(classes="modal-buttons"):
                    yield Button("Allow once (1)", variant="success", id="allow_once")
                    yield Button("Allow session (2)", variant="success", id="allow_session")
                    yield Button("Always (a)", variant="primary", id="allow_always")
                    yield Button("Reject (Esc)", variant="error", id="reject")

        def on_button_pressed(self, event: Button.Pressed) -> None:  # type: ignore[name-defined]
            self.dismiss(decision_for_action(event.button.id or "reject"))

        def action_reject(self) -> None:
            self.dismiss(decision_for_action("reject"))

        def action_allow_once(self) -> None:
            self.dismiss(decision_for_action("allow_once"))

        def action_allow_session(self) -> None:
            self.dismiss(decision_for_action("allow_session"))

        def action_allow_always(self) -> None:
            self.dismiss(decision_for_action("allow_always"))
