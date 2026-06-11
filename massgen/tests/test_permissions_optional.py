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
