"""Proves the permissions system is fully OPT-IN: with no `permissions:` block,
no permission hooks are registered and no coordinator is installed — i.e. default
behavior is unchanged.
"""

from massgen.orchestrator_collaborators.midstream_injection_hook_installer import (
    MidStreamInjectionHookInstaller,
)


class _Manager:
    def __init__(self):
        self.hooks = []

    def register_global_hook(self, hook_type, hook):
        self.hooks.append(hook)


class _Backend:
    def __init__(self, config):
        self.config = config
        self.coordinator = None

    def set_permission_coordinator(self, c):
        self.coordinator = c


class _Agent:
    def __init__(self, config):
        self.backend = _Backend(config)


def _install(config):
    inst = MidStreamInjectionHookInstaller.__new__(MidStreamInjectionHookInstaller)
    agent = _Agent(config)
    mgr = _Manager()
    inst._install_permission_hooks(agent, "a1", mgr)
    return agent, mgr


def test_no_permissions_block_is_a_total_noop():
    agent, mgr = _install({"type": "openai", "cwd": "x"})  # no `permissions`
    assert mgr.hooks == []  # no hardline / engine hooks registered
    assert agent.backend.coordinator is None  # no approval coordinator


def test_permissions_enabled_false_is_a_noop():
    agent, mgr = _install({"permissions": {"enabled": False}})
    assert mgr.hooks == []
    assert agent.backend.coordinator is None


def test_permissions_block_opts_in():
    agent, mgr = _install({"permissions": {"enabled": True}})
    # registers exactly the hardline blocklist + the permission engine, and a coordinator
    names = sorted(getattr(h, "name", "") for h in mgr.hooks)
    assert names == ["hardline_blocklist", "permission_engine"]
    assert agent.backend.coordinator is not None


def test_bare_permissions_block_defaults_enabled():
    # `permissions: {}` (present, no `enabled`) opts in (enabled defaults True).
    agent, mgr = _install({"permissions": {}})
    assert len(mgr.hooks) == 2
    assert agent.backend.coordinator is not None


# --------------------------------------------------------------------------- #
# Per-agent scoping: each agent's permission engine is built from ITS OWN config
# --------------------------------------------------------------------------- #
def _engine(mgr):
    return next(h for h in mgr.hooks if getattr(h, "name", "") == "permission_engine")


def test_read_only_role_agent_denies_writes():
    agent, mgr = _install({"permissions": {"enabled": True, "role": "read-only"}})
    engine = _engine(mgr)
    assert engine.rules is not None
    assert engine.rules.evaluate("write_file", {"path": "x"}) == "deny"
    assert engine.rules.evaluate("read_file", {"path": "x"}) == "allow"


def test_read_write_agent_has_no_rules_falls_to_risk():
    agent, mgr = _install({"permissions": {"enabled": True}})  # no role/rules
    assert _engine(mgr).rules is None  # → falls through to the risk classifier


def test_approval_mode_default_is_policy():
    from massgen.permissions.approval_provider import PolicyApprovalProvider

    agent, _ = _install({"permissions": {"enabled": True}})
    assert isinstance(agent.backend.coordinator.provider, PolicyApprovalProvider)


def test_approval_mode_file_uses_file_provider(tmp_path):
    from massgen.permissions.approval_provider import FileApprovalProvider

    agent, _ = _install({"permissions": {"enabled": True, "approval_mode": "file", "approval_dir": str(tmp_path)}})
    assert isinstance(agent.backend.coordinator.provider, FileApprovalProvider)


def test_two_agents_get_independent_engines():
    # A "researcher" (read-only) and an "implementer" (read-write) built side by side
    # have distinct rule sets — the multi-agent differentiator.
    _, mgr_researcher = _install({"permissions": {"enabled": True, "role": "read-only"}})
    _, mgr_implementer = _install({"permissions": {"enabled": True, "role": "read-write", "rules": {"deny": ["command(git push --force*)"]}}})
    assert _engine(mgr_researcher).rules.evaluate("write_file", {"path": "x"}) == "deny"
    # implementer can write, but the force-push deny applies
    assert _engine(mgr_implementer).rules.evaluate("write_file", {"path": "x"}) is None
    assert _engine(mgr_implementer).rules.evaluate("execute_command", {"command": "git push --force"}) == "deny"
