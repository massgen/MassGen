"""Permission guardrail system-prompt section + activation gating.

When the permission engine is ACTIVE for an agent, the system prompt must carry a
channel-based guardrail policy: follow the guardrails, do not circumvent blocks,
and treat ONLY the system prompt as the source of permission authority (no token —
authority is established by channel, since untrusted content can never be the
system prompt). The section must NOT appear when permissions are off or when the
backend can't honor the approval chokepoint (native backends).
"""

from __future__ import annotations

from massgen.permissions.activation import (
    guardrail_prompt_active,
    is_permissions_enabled,
)
from massgen.system_prompt_sections import (
    PermissionGuardrailSection,
    SystemPromptBuilder,
)


# --------------------------------------------------------------------------- #
# is_permissions_enabled — single source of truth for the opt-in check
# --------------------------------------------------------------------------- #
def test_is_permissions_enabled_truth_table():
    assert is_permissions_enabled(None) is False
    assert is_permissions_enabled(False) is False
    assert is_permissions_enabled({}) is True  # present, enabled defaults True
    assert is_permissions_enabled({"enabled": True}) is True
    assert is_permissions_enabled({"enabled": False}) is False


# --------------------------------------------------------------------------- #
# Activation gating — only when permissions active AND backend supports chokepoint
# --------------------------------------------------------------------------- #
class _ChokepointBackend:
    def __init__(self, perms):
        self.config = {"permissions": perms} if perms is not None else {}

    def set_permission_coordinator(self, c):  # marks chokepoint support
        pass


class _NativeBackend:
    """No set_permission_coordinator — mimics claude_code / codex."""

    def __init__(self, perms):
        self.config = {"permissions": perms} if perms is not None else {}


def test_active_when_enabled_and_chokepoint_backend():
    assert guardrail_prompt_active(_ChokepointBackend({"enabled": True})) is True
    assert guardrail_prompt_active(_ChokepointBackend({})) is True  # bare block opts in


def test_inactive_when_no_permissions_block():
    assert guardrail_prompt_active(_ChokepointBackend(None)) is False


def test_inactive_when_disabled():
    assert guardrail_prompt_active(_ChokepointBackend({"enabled": False})) is False


def test_inactive_on_native_backend_even_with_permissions():
    # Permissions are INACTIVE on backends without the chokepoint, so the policy
    # section must not appear there (no false promise of enforcement).
    assert guardrail_prompt_active(_NativeBackend({"enabled": True})) is False


# --------------------------------------------------------------------------- #
# Section content — the policy the model is told
# --------------------------------------------------------------------------- #
def test_section_states_the_core_policy():
    content = PermissionGuardrailSection().render()
    low = content.lower()
    assert "guardrail" in low
    # anti-circumvention
    assert "circumvent" in low
    # surface-and-ask, don't route around
    assert "approval" in low
    # channel-based authority: only the system prompt is authoritative
    assert "system prompt" in low
    assert "untrusted" in low
    # cannot be relaxed/overridden by other content
    assert "override" in low or "relax" in low


def test_section_encourages_the_approval_flow_not_just_blocks():
    # The policy must NOT discourage the legitimate `ask`/approval path: needing
    # approval is normal, and the model should still make approvable calls. Only
    # circumventing an actual DENIAL is forbidden.
    content = PermissionGuardrailSection().render()
    low = content.lower()
    # approval is framed as normal/sanctioned, not something to avoid
    assert "approval is normal" in low or "needing approval is not a block" in low
    # circumvention is tied to denial/rejection, not to "requires approval"
    assert "circumvent a denial" in low or "denied" in low


def test_section_mentions_role_when_provided():
    content = PermissionGuardrailSection(role="read-only").render()
    assert "read-only" in content


def test_section_omits_role_line_when_absent():
    content = PermissionGuardrailSection().render()
    # No stray "role" placeholder when no role is set.
    assert "assigned permission role" not in content.lower()


# --------------------------------------------------------------------------- #
# Wiring — the gate + section integrate (mirrors system_message_builder usage)
# --------------------------------------------------------------------------- #
def _render_with_gate(backend) -> str:
    builder = SystemPromptBuilder()
    if guardrail_prompt_active(backend):
        perms = backend.config.get("permissions") or {}
        role = perms.get("role") if isinstance(perms, dict) else None
        builder.add_section(PermissionGuardrailSection(role=role))
    return builder.build()


def test_prompt_includes_guardrails_when_active():
    out = _render_with_gate(_ChokepointBackend({"enabled": True, "role": "read-only"}))
    assert "permission_guardrails" in out  # xml tag rendered
    assert "circumvent" in out.lower()
    assert "read-only" in out


def test_prompt_excludes_guardrails_when_inactive():
    assert "permission_guardrails" not in _render_with_gate(_ChokepointBackend(None))
    assert "permission_guardrails" not in _render_with_gate(_NativeBackend({"enabled": True}))
