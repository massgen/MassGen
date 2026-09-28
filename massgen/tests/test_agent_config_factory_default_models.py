"""Default model resolution for the Claude AgentConfig factories.

A backend config may omit ``model`` when the backend declares a
``default_model`` in the capability registry (see
``ConfigValidator._validate_backend``). The factory methods used by
``create_agents_from_config`` must then resolve to that same registry default,
because the model they put in ``backend_params`` is forwarded to
``stream_with_tools`` and overrides the backend's own config.
"""

import pytest

from massgen.agent_config import AgentConfig
from massgen.backend.capabilities import get_capabilities
from massgen.config_validator import ConfigValidator


@pytest.mark.parametrize(
    ("backend_type", "factory"),
    [
        ("claude", AgentConfig.create_claude_config),
        ("claude_code", AgentConfig.create_claude_code_config),
    ],
)
class TestClaudeFactoryDefaultModel:
    def test_default_model_matches_registry(self, backend_type, factory):
        caps = get_capabilities(backend_type)

        config = factory()

        assert config.backend_params["model"] == caps.default_model
        assert config.backend_params["model"] in caps.models

    def test_explicit_none_uses_registry_default(self, backend_type, factory):
        config = factory(model=None)

        assert config.backend_params["model"] == get_capabilities(backend_type).default_model

    def test_explicit_model_is_preserved(self, backend_type, factory):
        config = factory(model="claude-sonnet-4-5-20250929")

        assert config.backend_params["model"] == "claude-sonnet-4-5-20250929"


def test_claude_config_keeps_tool_flags_with_default_model():
    config = AgentConfig.create_claude_config(enable_web_search=True, enable_code_execution=True)

    assert config.backend_params == {
        "model": get_capabilities("claude").default_model,
        "enable_web_search": True,
        "enable_code_execution": True,
    }


def test_claude_code_config_keeps_options_with_default_model():
    config = AgentConfig.create_claude_code_config(cwd="workspace", reasoning={"effort": "low"})

    assert config.backend_params == {
        "model": get_capabilities("claude_code").default_model,
        "reasoning": {"effort": "low"},
        "cwd": "workspace",
    }


def test_model_less_claude_agent_sends_registry_default(monkeypatch):
    """A YAML agent without ``model`` must request the registry default model."""
    from massgen.cli.backends import create_agents_from_config

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    config = {"agents": [{"id": "agent_a", "backend": {"type": "claude"}}]}

    result = ConfigValidator().validate_config(config)
    assert not result.has_errors()

    agent = create_agents_from_config(config)["agent_a"]

    assert agent._get_backend_params()["model"] == get_capabilities("claude").default_model
