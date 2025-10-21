# -*- coding: utf-8 -*-
"""
Comprehensive tests for config_builder.py - Agent cloning and preset application.

These tests ensure:
1. Cross-provider cloning preserves correct settings
2. Incompatible settings are skipped with warnings
3. Workspace uniqueness across agents
4. Tool compatibility matrix is enforced

Run with: uv run pytest massgen/tests/test_config_builder.py -v
"""

import pytest

from massgen.config_builder import ConfigBuilder


class TestCloneAgent:
    """Test agent cloning across providers with compatibility checks."""

    @pytest.fixture
    def builder(self):
        """Create a ConfigBuilder instance for testing."""
        return ConfigBuilder()

    def test_clone_openai_to_gemini_preserves_provider(self, builder):
        """Test cloning OpenAI to Gemini preserves Gemini provider."""
        source = {
            "id": "agent_a",
            "backend": {
                "type": "openai",
                "model": "gpt-5",
                "enable_web_search": True,
                "cwd": "workspace1",
            },
        }

        cloned = builder.clone_agent(source, "agent_b", target_backend_type="gemini")

        assert cloned["id"] == "agent_b"
        assert cloned["backend"]["type"] == "gemini"
        assert cloned["backend"]["model"] == "gemini-2.5-flash"  # Default Gemini model
        assert cloned["backend"]["enable_web_search"] is True  # Compatible, should copy
        assert cloned["backend"]["cwd"] == "workspace2"  # Filesystem copied and updated to agent_b's number

    def test_clone_copies_filesystem_cwd(self, builder):
        """Test that cwd (filesystem) is copied and updated for target agent."""
        source = {
            "id": "agent_a",
            "backend": {"type": "openai", "model": "gpt-5", "cwd": "workspace1"},
        }

        cloned = builder.clone_agent(source, "agent_b", target_backend_type="claude")

        # cwd should exist (copied from source) and updated to agent_b's workspace number
        assert "cwd" in cloned["backend"]
        assert cloned["backend"]["cwd"] == "workspace2"  # agent_b -> workspace2

    def test_clone_updates_workspace_number(self, builder):
        """Test that workspace number updates for target agent ID."""
        source = {
            "id": "agent_a",
            "backend": {"type": "openai", "model": "gpt-5", "cwd": "workspace1"},
        }

        cloned = builder.clone_agent(source, "agent_c", target_backend_type="openai")

        assert cloned["backend"]["cwd"] == "workspace3"  # agent_c -> workspace3

    def test_clone_copies_compatible_tools(self, builder):
        """Test that compatible tools are copied across providers."""
        source = {
            "id": "agent_a",
            "backend": {
                "type": "openai",
                "model": "gpt-5",
                "enable_web_search": True,
                "enable_mcp_command_line": True,
                "command_line_execution_mode": "docker",
            },
        }

        cloned = builder.clone_agent(source, "agent_b", target_backend_type="gemini")

        # Universal tools should be copied
        assert cloned["backend"]["enable_mcp_command_line"] is True
        assert cloned["backend"]["command_line_execution_mode"] == "docker"
        # Web search compatible with both OpenAI and Gemini
        assert cloned["backend"]["enable_web_search"] is True

    def test_clone_skips_incompatible_tools(self, builder):
        """Test that incompatible tools are skipped with warnings."""
        source = {
            "id": "agent_a",
            "backend": {
                "type": "openai",
                "model": "gpt-5",
                "enable_code_interpreter": True,  # OpenAI-specific
            },
        }

        cloned = builder.clone_agent(source, "agent_b", target_backend_type="gemini")

        # Incompatible setting should be skipped
        assert "enable_code_interpreter" not in cloned["backend"]
        # Should generate skipped settings list
        assert "_skipped_settings" in cloned
        assert any("enable_code_interpreter" in s for s in cloned["_skipped_settings"])

    def test_clone_skips_openai_reasoning_to_gemini(self, builder):
        """Test that OpenAI reasoning/text settings are skipped for other providers."""
        source = {
            "id": "agent_a",
            "backend": {
                "type": "openai",
                "model": "gpt-5",
                "text": {"verbosity": "medium"},
                "reasoning": {"effort": "high", "summary": "auto"},
            },
        }

        cloned = builder.clone_agent(source, "agent_b", target_backend_type="gemini")

        # OpenAI-specific settings should be skipped
        assert "text" not in cloned["backend"]
        assert "reasoning" not in cloned["backend"]
        # Should be in skipped list
        assert any("text" in s for s in cloned["_skipped_settings"])
        assert any("reasoning" in s for s in cloned["_skipped_settings"])

    def test_clone_preserves_openai_reasoning_to_openai(self, builder):
        """Test that OpenAI reasoning settings are preserved when cloning to OpenAI."""
        source = {
            "id": "agent_a",
            "backend": {
                "type": "openai",
                "model": "gpt-5",
                "text": {"verbosity": "medium"},
                "reasoning": {"effort": "high", "summary": "auto"},
            },
        }

        cloned = builder.clone_agent(source, "agent_b", target_backend_type="openai")

        # OpenAI-specific settings should be preserved
        assert cloned["backend"]["text"]["verbosity"] == "medium"
        assert cloned["backend"]["reasoning"]["effort"] == "high"

    def test_clone_skips_code_interpreter_openai_to_gemini(self, builder):
        """Test code_interpreter is skipped when cloning OpenAI to Gemini."""
        source = {
            "id": "agent_a",
            "backend": {
                "type": "openai",
                "model": "gpt-5",
                "enable_code_interpreter": True,
            },
        }

        cloned = builder.clone_agent(source, "agent_b", target_backend_type="gemini")

        assert "enable_code_interpreter" not in cloned["backend"]
        assert any("enable_code_interpreter" in s for s in cloned["_skipped_settings"])

    def test_clone_skips_code_execution_gemini_to_openai(self, builder):
        """Test code_execution is skipped when cloning Gemini to OpenAI."""
        source = {
            "id": "agent_a",
            "backend": {"type": "gemini", "model": "gemini-2.5-pro", "enable_code_execution": True},
        }

        cloned = builder.clone_agent(source, "agent_b", target_backend_type="openai")

        assert "enable_code_execution" not in cloned["backend"]
        assert any("enable_code_execution" in s for s in cloned["_skipped_settings"])

    def test_clone_copies_mcp_servers_when_supported(self, builder):
        """Test MCP servers are copied when target supports MCP."""
        source = {
            "id": "agent_a",
            "backend": {
                "type": "openai",
                "model": "gpt-5",
                "mcp_servers": [
                    {"name": "weather", "command": "npx", "args": ["-y", "@fak111/weather-mcp"]},
                ],
            },
        }

        cloned = builder.clone_agent(source, "agent_b", target_backend_type="gemini")

        # Gemini supports MCP, should copy
        assert "mcp_servers" in cloned["backend"]
        assert cloned["backend"]["mcp_servers"][0]["name"] == "weather"

    def test_clone_same_provider_copies_everything(self, builder):
        """Test cloning within same provider copies all settings."""
        source = {
            "id": "agent_a",
            "backend": {
                "type": "openai",
                "model": "gpt-5",
                "enable_web_search": True,
                "enable_code_interpreter": True,
                "text": {"verbosity": "high"},
                "reasoning": {"effort": "medium", "summary": "auto"},
                "cwd": "workspace1",
            },
        }

        cloned = builder.clone_agent(source, "agent_b", target_backend_type="openai")

        # Everything should be copied for same provider
        assert cloned["backend"]["enable_web_search"] is True
        assert cloned["backend"]["enable_code_interpreter"] is True
        assert cloned["backend"]["text"]["verbosity"] == "high"
        assert cloned["backend"]["reasoning"]["effort"] == "medium"

    def test_clone_generates_skipped_settings_list(self, builder):
        """Test that _skipped_settings list is generated for incompatible settings."""
        source = {
            "id": "agent_a",
            "backend": {
                "type": "openai",
                "model": "gpt-5",
                "enable_code_interpreter": True,
                "text": {"verbosity": "high"},
                "reasoning": {"effort": "medium", "summary": "auto"},
            },
        }

        cloned = builder.clone_agent(source, "agent_b", target_backend_type="claude")

        # Should have skipped settings
        assert "_skipped_settings" in cloned
        skipped = cloned["_skipped_settings"]
        assert len(skipped) > 0
        # All three should be skipped
        assert any("enable_code_interpreter" in s for s in skipped)
        assert any("text" in s for s in skipped)
        assert any("reasoning" in s for s in skipped)


class TestApplyPresetToAgent:
    """Test preset application generates unique workspaces."""

    @pytest.fixture
    def builder(self):
        """Create a ConfigBuilder instance for testing."""
        return ConfigBuilder()

    def test_apply_preset_generates_unique_workspace(self, builder):
        """Test that preset application generates workspace based on agent index."""
        agent = {"id": "agent_a", "backend": {"type": "openai", "model": "gpt-5"}}

        updated = builder.apply_preset_to_agent(agent, "coding", agent_index=1)

        assert updated["backend"]["cwd"] == "workspace1"

    def test_apply_preset_multiple_agents_unique_workspaces(self, builder):
        """Test that multiple agents get unique workspace numbers."""
        agents = [
            {"id": "agent_a", "backend": {"type": "openai", "model": "gpt-5"}},
            {"id": "agent_b", "backend": {"type": "gemini", "model": "gemini-2.5-pro"}},
            {"id": "agent_c", "backend": {"type": "claude", "model": "claude-3-5-sonnet-20241022"}},
        ]

        for i, agent in enumerate(agents):
            updated = builder.apply_preset_to_agent(agent, "coding", agent_index=i + 1)
            agents[i] = updated

        # Check all have unique workspaces
        assert agents[0]["backend"]["cwd"] == "workspace1"
        assert agents[1]["backend"]["cwd"] == "workspace2"
        assert agents[2]["backend"]["cwd"] == "workspace3"

    def test_apply_preset_filesystem_enabled_for_preset(self, builder):
        """Test that filesystem is enabled for presets that require it."""
        agent = {"id": "agent_a", "backend": {"type": "openai", "model": "gpt-5"}}

        updated = builder.apply_preset_to_agent(agent, "coding", agent_index=1)

        # Coding preset requires filesystem
        assert "cwd" in updated["backend"]

    def test_apply_preset_respects_agent_index(self, builder):
        """Test that agent_index correctly determines workspace number."""
        agent = {"id": "agent_c", "backend": {"type": "openai", "model": "gpt-5"}}

        updated = builder.apply_preset_to_agent(agent, "coding", agent_index=3)

        assert updated["backend"]["cwd"] == "workspace3"


class TestCrossProviderCompatibility:
    """Test tool compatibility matrix across providers."""

    @pytest.fixture
    def builder(self):
        """Create a ConfigBuilder instance for testing."""
        return ConfigBuilder()

    def test_web_search_compatible_providers(self, builder):
        """Test web_search is compatible with OpenAI, Gemini, Claude, Grok."""
        source = {
            "id": "agent_a",
            "backend": {"type": "openai", "model": "gpt-5", "enable_web_search": True},
        }

        for target_type in ["gemini", "claude", "grok"]:
            cloned = builder.clone_agent(source, "agent_b", target_backend_type=target_type)
            assert cloned["backend"]["enable_web_search"] is True, f"web_search should work on {target_type}"

    def test_code_interpreter_only_openai_azure(self, builder):
        """Test code_interpreter only works on OpenAI and Azure OpenAI."""
        source = {
            "id": "agent_a",
            "backend": {"type": "openai", "model": "gpt-5", "enable_code_interpreter": True},
        }

        # Should be skipped for non-OpenAI providers
        for target_type in ["gemini", "claude", "grok"]:
            cloned = builder.clone_agent(source, "agent_b", target_backend_type=target_type)
            assert "enable_code_interpreter" not in cloned["backend"], f"code_interpreter shouldn't work on {target_type}"
            assert any("enable_code_interpreter" in s for s in cloned["_skipped_settings"])

    def test_code_execution_only_claude_gemini(self, builder):
        """Test code_execution only works on Claude and Gemini."""
        source = {
            "id": "agent_a",
            "backend": {"type": "gemini", "model": "gemini-2.5-pro", "enable_code_execution": True},
        }

        # Should work on Claude
        cloned_claude = builder.clone_agent(source, "agent_b", target_backend_type="claude")
        assert cloned_claude["backend"]["enable_code_execution"] is True

        # Should be skipped for OpenAI
        cloned_openai = builder.clone_agent(source, "agent_c", target_backend_type="openai")
        assert "enable_code_execution" not in cloned_openai["backend"]
        assert any("enable_code_execution" in s for s in cloned_openai["_skipped_settings"])

    def test_filesystem_copied_across_all_providers(self, builder):
        """Test filesystem (cwd) is copied across all providers and updated to target agent number."""
        source = {"id": "agent_a", "backend": {"type": "openai", "model": "gpt-5", "cwd": "workspace1"}}

        for target_type in ["gemini", "claude", "grok", "claude_code", "lmstudio"]:
            cloned = builder.clone_agent(source, "agent_b", target_backend_type=target_type)
            # cwd should exist and be updated to workspace2 for agent_b
            assert "cwd" in cloned["backend"], f"cwd should be copied to {target_type}"
            assert cloned["backend"]["cwd"] == "workspace2", f"cwd should be workspace2 for {target_type}"

    def test_command_line_execution_mode_universal(self, builder):
        """Test command_line_execution_mode is universal across providers."""
        source = {
            "id": "agent_a",
            "backend": {
                "type": "openai",
                "model": "gpt-5",
                "enable_mcp_command_line": True,
                "command_line_execution_mode": "docker",
            },
        }

        for target_type in ["gemini", "claude", "grok"]:
            cloned = builder.clone_agent(source, "agent_b", target_backend_type=target_type)
            assert cloned["backend"]["enable_mcp_command_line"] is True
            assert cloned["backend"]["command_line_execution_mode"] == "docker"


class TestWorkspaceUniqueness:
    """Test workspace uniqueness across different scenarios."""

    @pytest.fixture
    def builder(self):
        """Create a ConfigBuilder instance for testing."""
        return ConfigBuilder()

    def test_three_agents_get_workspace1_2_3(self, builder):
        """Test that three agents get workspace1, workspace2, workspace3."""
        agents = [
            {"id": "agent_a", "backend": {"type": "openai", "model": "gpt-5"}},
            {"id": "agent_b", "backend": {"type": "gemini", "model": "gemini-2.5-pro"}},
            {"id": "agent_c", "backend": {"type": "claude", "model": "claude-3-5-sonnet-20241022"}},
        ]

        for i, agent in enumerate(agents):
            agents[i] = builder.apply_preset_to_agent(agent, "coding", agent_index=i + 1)

        assert agents[0]["backend"]["cwd"] == "workspace1"
        assert agents[1]["backend"]["cwd"] == "workspace2"
        assert agents[2]["backend"]["cwd"] == "workspace3"

    def test_clone_updates_workspace_for_target_agent(self, builder):
        """Test that cloning updates workspace to match target agent ID."""
        source = {"id": "agent_a", "backend": {"type": "openai", "model": "gpt-5", "cwd": "workspace1"}}

        # Clone to agent_d should get workspace4
        cloned = builder.clone_agent(source, "agent_d", target_backend_type="openai")

        assert cloned["backend"]["cwd"] == "workspace4"

    def test_mixed_providers_all_unique_workspaces(self, builder):
        """Test mixed preset + clone scenario maintains unique workspaces."""
        # Agent A from preset
        agent_a = {"id": "agent_a", "backend": {"type": "openai", "model": "gpt-5"}}
        agent_a = builder.apply_preset_to_agent(agent_a, "coding", agent_index=1)

        # Agent B cloned from A
        agent_b = builder.clone_agent(agent_a, "agent_b", target_backend_type="gemini")

        # Agent C from preset
        agent_c = {"id": "agent_c", "backend": {"type": "claude", "model": "claude-3-5-sonnet-20241022"}}
        agent_c = builder.apply_preset_to_agent(agent_c, "coding", agent_index=3)

        assert agent_a["backend"]["cwd"] == "workspace1"
        assert agent_b["backend"]["cwd"] == "workspace2"  # Updated from agent_b ID
        assert agent_c["backend"]["cwd"] == "workspace3"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
