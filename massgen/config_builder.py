#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MassGen Interactive Configuration Builder

A user-friendly CLI tool to create MassGen configuration files without
manually writing YAML. Guides users through agent selection, tool configuration,
and workspace setup.

Usage:
    python -m massgen.config_builder
    python -m massgen.cli --build-config
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import questionary
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.theme import Theme

from massgen.backend.capabilities import BACKEND_CAPABILITIES, get_capabilities

# Load environment variables
load_dotenv()

# Custom theme for the CLI
custom_theme = Theme(
    {
        "info": "cyan",
        "warning": "yellow",
        "error": "red bold",
        "success": "green bold",
        "prompt": "blue bold",
    },
)

console = Console(theme=custom_theme)


class ConfigBuilder:
    """Interactive configuration builder for MassGen."""

    @property
    def PROVIDERS(self) -> Dict[str, Dict]:
        """Generate provider configurations from the capabilities registry (single source of truth).

        This dynamically builds the PROVIDERS dict from massgen/backend/capabilities.py,
        ensuring consistency between config builder, documentation, and backend implementations.
        """
        providers = {}

        for backend_type, caps in BACKEND_CAPABILITIES.items():
            # Build supports list, handling filesystem specially
            supports = list(caps.supported_capabilities)

            # Add "filesystem" to supports for ANY backend that supports it (native or MCP)
            if caps.filesystem_support in ["native", "mcp"]:
                supports = [s if s != "filesystem_native" else "filesystem" for s in supports]
                if "filesystem" not in supports:
                    supports.append("filesystem")

            providers[backend_type] = {
                "name": caps.provider_name,
                "type": caps.backend_type,
                "env_var": caps.env_var,
                "models": caps.models,
                "supports": supports,
            }

        return providers

    # Use case templates - all use cases support all agent types
    USE_CASES = {
        "custom": {
            "name": "Custom Configuration",
            "description": "Full flexibility - choose any agents, tools, and settings",
            "recommended_agents": 1,
            "recommended_tools": [],
            "agent_types": "all",
            "notes": "Choose any combination of agents and tools",
            "info": "Manual setup: You'll configure each agent, model, and tool individually. Best for advanced users or specific requirements.",
        },
        "coding": {
            "name": "Filesystem + Code Execution",
            "description": "Generate, test, and modify code with file operations",
            "recommended_agents": 2,
            "recommended_tools": ["code_execution", "filesystem"],
            "agent_types": "all",
            "notes": "Claude Code recommended for best filesystem support",
            "info": "Automatically enables: File read/write operations, code execution in isolated workspace, and agent collaboration on code projects.",
        },
        "coding_docker": {
            "name": "Filesystem + Code Execution (Docker)",
            "description": "Secure isolated code execution in Docker containers (requires setup)",
            "recommended_agents": 2,
            "recommended_tools": ["code_execution", "filesystem"],
            "agent_types": "all",
            "notes": "⚠️ SETUP REQUIRED: Docker Engine 28+, Python docker library, and image build (see massgen/docker/README.md)",
            "info": "Automatically enables: File operations, code execution in Docker containers (fully isolated), persistent package installations, and network/resource controls.",
        },
        "qa": {
            "name": "Simple Q&A",
            "description": "Basic question answering",
            "recommended_agents": 1,
            "recommended_tools": [],
            "agent_types": "all",  # Any agent type works
            "notes": "Start simple with 1 agent, add more for diverse perspectives",
            "info": "Minimal setup: Just text-based conversations with AI agents. No special tools enabled by default.",
        },
        "research": {
            "name": "Research & Analysis",
            "description": "Multi-agent research with web search",
            "recommended_agents": 3,
            "recommended_tools": ["web_search"],
            "agent_types": "all",
            "notes": "Works best with web search enabled for current information",
            "info": "Automatically enables: Real-time web search for current information, multiple agents for diverse perspectives and fact-checking.",
        },
        "creative": {
            "name": "Creative Writing",
            "description": "Collaborative creative content generation",
            "recommended_agents": 3,
            "recommended_tools": [],
            "agent_types": "all",
            "notes": "Multiple agents provide diverse creative perspectives",
            "info": "Multiple agents collaborate to provide diverse creative ideas, styles, and perspectives. No special tools - pure creativity.",
        },
        "data_analysis": {
            "name": "Data Analysis",
            "description": "Analyze data with code execution and visualizations",
            "recommended_agents": 2,
            "recommended_tools": ["code_execution", "filesystem"],
            "agent_types": "all",
            "notes": "Code execution helps with data processing and visualization",
            "info": "Automatically enables: Code execution for data processing, file operations to read/write data files, and visualization generation.",
        },
        "web_automation": {
            "name": "Web Automation",
            "description": "Browser automation and web scraping with MCP",
            "recommended_agents": 2,
            "recommended_tools": ["mcp", "filesystem"],
            "agent_types": "all",
            "notes": "MCP servers provide browser automation capabilities",
            "info": "Requires manual MCP server setup. Enables: Browser automation via Playwright MCP, web scraping, screenshot capture, and file saving.",
        },
    }

    def __init__(self, default_mode: bool = False) -> None:
        """Initialize the configuration builder with default config.

        Args:
            default_mode: If True, save config to ~/.config/massgen/config.yaml by default
        """
        self.config = {
            "agents": [],
            "ui": {
                "display_type": "rich_terminal",
                "logging_enabled": True,
            },
        }
        self.orchestrator_config = {}
        self.default_mode = default_mode

    def show_banner(self) -> None:
        """Display welcome banner."""
        banner = """
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   🚀 MassGen Interactive Configuration Builder 🚀        ║
║                                                           ║
║   Create custom multi-agent configurations in minutes!   ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
        """
        console.print(banner, style="bold cyan")
        console.print()

    def detect_api_keys(self) -> Dict[str, bool]:
        """Detect available API keys from environment with error handling."""
        api_keys = {}
        try:
            for provider_id, provider_info in self.PROVIDERS.items():
                try:
                    env_var = provider_info.get("env_var")
                    if env_var:
                        api_keys[provider_id] = bool(os.getenv(env_var))
                    else:
                        api_keys[provider_id] = True  # Local models don't need keys
                except Exception as e:
                    console.print(f"[warning]⚠️  Could not check {provider_id}: {e}[/warning]")
                    api_keys[provider_id] = False
            return api_keys
        except Exception as e:
            console.print(f"[error]❌ Error detecting API keys: {e}[/error]")
            # Return empty dict to allow continue with manual input
            return {provider_id: False for provider_id in self.PROVIDERS.keys()}

    def show_available_providers(
        self,
        api_keys: Dict[str, bool],
    ) -> None:
        """Display providers in improved format with error handling."""
        try:
            # Use full terminal width
            width = console.width - 4  # Leave some margin

            console.print()
            console.print("╔" + "═" * width + "╗")
            console.print("║  " + "[bold cyan]Available Providers[/bold cyan]".ljust(width + 10) + "║")
            console.print("╠" + "═" * width + "╣")
            console.print("║" + " " * width + "║")

            for provider_id, provider_info in self.PROVIDERS.items():
                try:
                    has_key = api_keys.get(provider_id, False)
                    status = "✅" if has_key else "❌"
                    name = provider_info.get("name", "Unknown")

                    # Main line with status and name
                    console.print(f"║  {status} [bold]{name:<60}[/bold]  ║")

                    # Models line
                    models = provider_info.get("models", [])
                    models_display = ", ".join(models[:3])
                    if len(models) > 3:
                        models_display += f" (+{len(models)-3} more)"
                    # Trim models display if too long
                    max_model_width = width - 10
                    if len(models_display) > max_model_width:
                        models_display = models_display[: max_model_width - 3] + "..."
                    console.print(f"║     [dim]{models_display}[/dim]")

                    # Capabilities line
                    if provider_info.get("supports"):
                        caps = "Supports: " + ", ".join(provider_info["supports"])
                        # Trim caps if too long
                        max_caps_width = width - 10
                        if len(caps) > max_caps_width:
                            caps = caps[: max_caps_width - 3] + "..."
                        console.print(f"║     [dim cyan]{caps}[/dim cyan]")
                    elif has_key:
                        console.print("║     [dim]Basic text generation[/dim]")

                    # API key hint if missing
                    if not has_key and provider_info.get("env_var"):
                        console.print(f"║     [yellow]Need: {provider_info['env_var']}[/yellow]")

                    console.print("║" + " " * width + "║")

                except Exception as e:
                    console.print(f"║  [warning]⚠️  Could not display {provider_id}: {e}[/warning]")

            console.print("╚" + "═" * width + "╝")
            console.print()
            console.print("💡 [dim]Tip: Set API keys in ~/.config/massgen/.env[/dim]")
            console.print()
        except Exception as e:
            console.print(f"[error]❌ Error displaying providers: {e}[/error]")
            console.print("[info]Continuing with setup...[/info]\n")

    def select_use_case(self) -> str:
        """Let user select a use case template with error handling."""
        try:
            console.print()
            sep_width = console.width - 4
            console.print("━" * sep_width)
            console.print("[bold cyan]Step 1 of 4: Select Your Use Case[/bold cyan]")
            console.print("━" * sep_width)
            console.print()
            console.print("[italic dim]All agent types are supported for every use case[/italic dim]\n")

            # Build choices for questionary
            choices = []
            for use_case_id, use_case_info in self.USE_CASES.items():
                try:
                    name = use_case_info.get("name", "Unknown")
                    description = use_case_info.get("description", "")
                    use_case_info.get("recommended_agents", 1)

                    # Create display string with name and description (no truncation)
                    display = f"{name} - {description}"

                    choices.append(
                        questionary.Choice(
                            title=display,
                            value=use_case_id,
                        ),
                    )
                except Exception as e:
                    console.print(f"[warning]⚠️  Could not display use case: {e}[/warning]")

            use_case_id = questionary.select(
                "Select your use case:",
                choices=choices,
                style=questionary.Style(
                    [
                        ("selected", "fg:cyan bold"),
                        ("pointer", "fg:cyan bold"),
                        ("highlighted", "fg:cyan"),
                    ],
                ),
                use_arrow_keys=True,
            ).ask()

            if not use_case_id:
                return "qa"  # Default if cancelled

            console.print(f"\n✅ Selected: [green]{self.USE_CASES[use_case_id].get('name', use_case_id)}[/green]\n")

            # Show preset information
            use_case_details = self.USE_CASES[use_case_id]
            if use_case_details.get("info"):
                console.print(
                    Panel(
                        f"[cyan]ℹ️  What this preset does:[/cyan]\n\n{use_case_details['info']}",
                        border_style="cyan",
                        title="Preset Information",
                    ),
                )
                console.print()

            # Show Docker setup warning if Docker preset is selected
            if use_case_id == "coding_docker":
                console.print("[yellow]⚠️  Docker Setup Required:[/yellow]")
                console.print("   1. Docker Engine 28.0.0+ installed and running")
                console.print('   2. Python docker library: [cyan]uv pip install -e ".[docker]"[/cyan]')
                console.print("   3. Build Docker image: [cyan]bash massgen/docker/build.sh[/cyan]")
                console.print("   📚 Full guide: [cyan]massgen/docker/README.md[/cyan]\n")

            return use_case_id
        except (KeyboardInterrupt, EOFError):
            raise  # Re-raise to be handled by run()
        except Exception as e:
            console.print(f"[error]❌ Error selecting use case: {e}[/error]")
            console.print("[info]Defaulting to 'qa' use case[/info]\n")
            return "qa"  # Safe default

    def add_custom_mcp_server(self) -> Optional[Dict]:
        """Interactive flow to configure a custom MCP server.

        Returns:
            MCP server configuration dict, or None if cancelled
        """
        try:
            console.print("\n[bold cyan]Configure Custom MCP Server[/bold cyan]\n")

            # Name
            name = questionary.text(
                "Server name (identifier):",
                validate=lambda x: len(x) > 0,
            ).ask()

            if not name:
                return None

            # Type
            server_type = questionary.select(
                "Server type:",
                choices=[
                    questionary.Choice("stdio (standard input/output)", value="stdio"),
                    questionary.Choice("sse (server-sent events)", value="sse"),
                    questionary.Choice("Custom type", value="custom"),
                ],
                default="stdio",
                style=questionary.Style(
                    [
                        ("selected", "fg:cyan bold"),
                        ("pointer", "fg:cyan bold"),
                        ("highlighted", "fg:cyan"),
                    ],
                ),
                use_arrow_keys=True,
            ).ask()

            if server_type == "custom":
                server_type = questionary.text("Enter custom type:").ask()

            if not server_type:
                server_type = "stdio"

            # Command
            command = questionary.text(
                "Command:",
                default="npx",
            ).ask()

            if not command:
                command = "npx"

            # Args
            args_str = questionary.text(
                "Arguments (space-separated, or empty for none):",
                default="",
            ).ask()

            args = args_str.split() if args_str else []

            # Environment variables
            env_vars = {}
            if questionary.confirm("Add environment variables?", default=False).ask():
                console.print("\n[dim]Tip: Use ${VAR_NAME} to reference from .env file[/dim]\n")
                while True:
                    var_name = questionary.text(
                        "Environment variable name (or press Enter to finish):",
                    ).ask()

                    if not var_name:
                        break

                    var_value = questionary.text(
                        f"Value for {var_name}:",
                        default=f"${{{var_name}}}",
                    ).ask()

                    if var_value:
                        env_vars[var_name] = var_value

            # Build server config
            mcp_server = {
                "name": name,
                "type": server_type,
                "command": command,
                "args": args,
            }

            if env_vars:
                mcp_server["env"] = env_vars

            console.print(f"\n✅ Custom MCP server configured: {name}\n")
            return mcp_server

        except (KeyboardInterrupt, EOFError):
            console.print("\n[info]Cancelled custom MCP configuration[/info]")
            return None
        except Exception as e:
            console.print(f"[error]❌ Error configuring custom MCP: {e}[/error]")
            return None

    def batch_create_agents(self, count: int, provider_id: str) -> List[Dict]:
        """Create multiple agents with the same provider.

        Args:
            count: Number of agents to create
            provider_id: Provider ID (e.g., 'openai', 'claude')

        Returns:
            List of agent configurations with default models
        """
        agents = []
        provider_info = self.PROVIDERS.get(provider_id, {})

        # Generate agent IDs like agent_a, agent_b, agent_c...
        for i in range(count):
            # Convert index to letter (0->a, 1->b, 2->c, etc.)
            agent_letter = chr(ord("a") + i)

            agent = {
                "id": f"agent_{agent_letter}",
                "backend": {
                    "type": provider_info.get("type", provider_id),
                    "model": provider_info.get("models", ["default"])[0],  # Default to first model
                },
            }

            # Add workspace for Claude Code (use numbers, not letters)
            if provider_info.get("type") == "claude_code":
                agent["backend"]["cwd"] = f"workspace{i + 1}"

            agents.append(agent)

        return agents

    def apply_preset_to_agent(self, agent: Dict, use_case: str) -> Dict:
        """Auto-apply preset configuration to an agent.

        Args:
            agent: Agent configuration dict
            use_case: Use case ID for preset configuration

        Returns:
            Updated agent configuration with preset applied
        """
        if use_case == "custom":
            return agent

        use_case_info = self.USE_CASES.get(use_case, {})
        recommended_tools = use_case_info.get("recommended_tools", [])

        backend_type = agent.get("backend", {}).get("type")
        provider_info = None

        # Find provider info
        for pid, pinfo in self.PROVIDERS.items():
            if pinfo.get("type") == backend_type:
                provider_info = pinfo
                break

        if not provider_info:
            return agent

        # Auto-enable filesystem if recommended
        if "filesystem" in recommended_tools and "filesystem" in provider_info.get("supports", []):
            if not agent["backend"].get("cwd"):
                agent["backend"]["cwd"] = "workspace"

        # Auto-enable web search if recommended
        if "web_search" in recommended_tools:
            if backend_type in ["openai", "claude", "gemini", "grok"]:
                agent["backend"]["enable_web_search"] = True

        # Auto-enable code execution if recommended
        if "code_execution" in recommended_tools:
            if backend_type == "openai":
                agent["backend"]["enable_code_interpreter"] = True
            elif backend_type in ["claude", "gemini"]:
                agent["backend"]["enable_code_execution"] = True

        # Auto-enable Docker for Docker preset
        if use_case == "coding_docker" and agent["backend"].get("cwd"):
            agent["backend"]["enable_mcp_command_line"] = True
            agent["backend"]["command_line_execution_mode"] = "docker"

        return agent

    def customize_agent(self, agent: Dict, agent_num: int, total_agents: int, use_case: Optional[str] = None) -> Dict:
        """Customize a single agent with Panel UI.

        Args:
            agent: Agent configuration dict
            agent_num: Agent number (1-indexed)
            total_agents: Total number of agents
            use_case: Use case ID for preset recommendations

        Returns:
            Updated agent configuration
        """
        try:
            backend_type = agent.get("backend", {}).get("type")
            provider_info = None

            # Find provider info
            for pid, pinfo in self.PROVIDERS.items():
                if pinfo.get("type") == backend_type:
                    provider_info = pinfo
                    break

            if not provider_info:
                console.print(f"[warning]⚠️  Could not find provider for {backend_type}[/warning]")
                return agent

            # Create Panel for this agent
            panel_content = []
            panel_content.append(f"[bold]Agent {agent_num} of {total_agents}: {agent['id']}[/bold]\n")

            # Model selection
            models = provider_info.get("models", [])
            if models:
                current_model = agent["backend"].get("model")
                panel_content.append(f"[cyan]Current model:[/cyan] {current_model}")

                console.print(Panel("\n".join(panel_content), border_style="cyan"))
                console.print()

                model_choices = [
                    questionary.Choice(
                        f"{model}" + (" (current)" if model == current_model else ""),
                        value=model,
                    )
                    for model in models
                ]

                selected_model = questionary.select(
                    f"Select model for {agent['id']}:",
                    choices=model_choices,
                    default=current_model,
                    style=questionary.Style(
                        [
                            ("selected", "fg:cyan bold"),
                            ("pointer", "fg:cyan bold"),
                            ("highlighted", "fg:cyan"),
                        ],
                    ),
                    use_arrow_keys=True,
                ).ask()

                if selected_model:
                    agent["backend"]["model"] = selected_model
            else:
                console.print(Panel("\n".join(panel_content), border_style="cyan"))

            # Filesystem access (native or via MCP)
            if "filesystem" in provider_info.get("supports", []):
                console.print()

                # Get filesystem support type from capabilities
                caps = get_capabilities(backend_type)
                fs_type = caps.filesystem_support if caps else "mcp"

                # Check if filesystem is recommended in the preset
                filesystem_recommended = False
                if use_case and use_case != "custom":
                    use_case_info = self.USE_CASES.get(use_case, {})
                    filesystem_recommended = "filesystem" in use_case_info.get("recommended_tools", [])

                if fs_type == "native":
                    console.print("[dim]This backend has native filesystem support[/dim]")
                else:
                    console.print("[dim]This backend supports filesystem operations via MCP[/dim]")

                if filesystem_recommended:
                    console.print("[dim]💡 Filesystem access recommended for this preset[/dim]")

                # Auto-enable for Docker preset
                enable_filesystem = filesystem_recommended
                if not filesystem_recommended:
                    enable_filesystem = questionary.confirm("Enable filesystem access for this agent?", default=True).ask()

                if enable_filesystem:
                    if backend_type == "claude_code":
                        # cwd is already set during batch_create_agents
                        # Optionally allow user to customize it
                        current_cwd = agent["backend"].get("cwd", "workspace")
                        console.print(f"[dim]Current workspace: {current_cwd}[/dim]")

                        if questionary.confirm("Customize workspace directory?", default=False).ask():
                            custom_cwd = questionary.text(
                                "Enter workspace directory:",
                                default=current_cwd,
                            ).ask()
                            if custom_cwd:
                                agent["backend"]["cwd"] = custom_cwd

                        console.print(f"✅ Filesystem access enabled (native): {agent['backend']['cwd']}")
                    else:
                        # For MCP-based filesystem, set cwd parameter
                        # This will be used for MCP filesystem operations
                        if not agent["backend"].get("cwd"):
                            # Use agent index for workspace naming
                            agent["backend"]["cwd"] = f"workspace{agent_num}"

                        console.print(f"✅ Filesystem access enabled (via MCP): {agent['backend']['cwd']}")

            # Enable Docker execution mode for Docker preset
            if use_case == "coding_docker" and agent["backend"].get("cwd"):
                agent["backend"]["enable_mcp_command_line"] = True
                agent["backend"]["command_line_execution_mode"] = "docker"
                console.print("🐳 Docker execution mode enabled for isolated code execution")

            # Built-in tools (backend-specific capabilities)
            supports = provider_info.get("supports", [])
            builtin_tools = [s for s in supports if s in ["web_search", "code_execution", "multimodal", "bash"]]

            # Get recommended tools from use case
            recommended_tools = []
            if use_case:
                use_case_info = self.USE_CASES.get(use_case, {})
                recommended_tools = use_case_info.get("recommended_tools", [])

            if builtin_tools:
                console.print()

                # Show preset info if this is a preset use case
                if recommended_tools and use_case != "custom":
                    console.print(f"[dim]💡 Preset recommendation: {', '.join(recommended_tools)}[/dim]")

                tool_choices = []

                if "web_search" in builtin_tools:
                    tool_choices.append(questionary.Choice("Web Search", value="web_search", checked="web_search" in recommended_tools))
                if "code_execution" in builtin_tools:
                    tool_choices.append(questionary.Choice("Code Execution", value="code_execution", checked="code_execution" in recommended_tools))
                if "bash" in builtin_tools:
                    tool_choices.append(questionary.Choice("Bash/Shell", value="bash", checked="bash" in recommended_tools))
                if "multimodal" in builtin_tools:
                    tool_choices.append(questionary.Choice("Multimodal (vision)", value="multimodal", checked="multimodal" in recommended_tools))

                if tool_choices:
                    selected_tools = questionary.checkbox(
                        "Enable built-in tools for this agent (Space to select, Enter to confirm):",
                        choices=tool_choices,
                        style=questionary.Style(
                            [
                                ("selected", "fg:cyan"),
                                ("pointer", "fg:cyan bold"),
                                ("highlighted", "fg:cyan"),
                            ],
                        ),
                        use_arrow_keys=True,
                    ).ask()

                    if selected_tools:
                        # Apply backend-specific configuration
                        if "web_search" in selected_tools:
                            if backend_type in ["openai", "claude", "gemini", "grok"]:
                                agent["backend"]["enable_web_search"] = True

                        if "code_execution" in selected_tools:
                            if backend_type == "openai":
                                agent["backend"]["enable_code_interpreter"] = True
                            elif backend_type in ["claude", "gemini"]:
                                agent["backend"]["enable_code_execution"] = True

                        console.print(f"✅ Enabled {len(selected_tools)} built-in tool(s)")

            # MCP servers (custom only)
            # Note: Filesystem is handled internally above, NOT as external MCP
            if "mcp" in provider_info.get("supports", []):
                console.print()
                console.print("[dim]MCP servers are external integrations. Filesystem is handled internally (configured above).[/dim]")

                if questionary.confirm("Add custom MCP servers?", default=False).ask():
                    mcp_servers = []
                    while True:
                        custom_server = self.add_custom_mcp_server()
                        if custom_server:
                            mcp_servers.append(custom_server)

                            # Ask if they want to add another
                            if not questionary.confirm("Add another custom MCP server?", default=False).ask():
                                break
                        else:
                            break

                    # Add to agent config if any MCPs were configured
                    if mcp_servers:
                        agent["backend"]["mcp_servers"] = mcp_servers
                        console.print(f"\n✅ Total: {len(mcp_servers)} MCP server(s) configured for this agent\n")

            console.print(f"✅ [green]Agent {agent_num} configured[/green]\n")
            return agent

        except (KeyboardInterrupt, EOFError):
            raise
        except Exception as e:
            console.print(f"[error]❌ Error customizing agent: {e}[/error]")
            return agent

    def configure_agents(self, use_case: str, api_keys: Dict[str, bool]) -> List[Dict]:
        """Configure agents with batch creation and individual customization."""
        try:
            console.print()
            sep_width = console.width - 4
            console.print("━" * sep_width)
            console.print("[bold cyan]Step 2 of 4: Agent Setup[/bold cyan]")
            console.print("━" * sep_width)
            console.print()
            console.print("[italic dim]Choose any provider(s) - all types work for your selected use case[/italic dim]\n")

            use_case_info = self.USE_CASES.get(use_case, {})
            recommended = use_case_info.get("recommended_agents", 1)

            # Step 2a: How many agents?
            console.print(f"💡 [dim]Recommended for this use case: {recommended} agent(s)[/dim]\n")

            # Build choices with proper default handling
            num_choices = [
                questionary.Choice("1 agent", value=1),
                questionary.Choice("2 agents", value=2),
                questionary.Choice("3 agents (recommended for diverse perspectives)", value=3),
                questionary.Choice("4 agents", value=4),
                questionary.Choice("5 agents", value=5),
                questionary.Choice("Custom number", value="custom"),
            ]

            # Find the default choice by value
            default_choice = None
            for choice in num_choices:
                if choice.value == recommended:
                    default_choice = choice.value
                    break

            try:
                num_agents_choice = questionary.select(
                    "How many agents?",
                    choices=num_choices,
                    default=default_choice,
                    style=questionary.Style(
                        [
                            ("selected", "fg:cyan bold"),
                            ("pointer", "fg:cyan bold"),
                            ("highlighted", "fg:cyan"),
                        ],
                    ),
                    use_arrow_keys=True,
                ).ask()

                if num_agents_choice == "custom":
                    num_agents_text = questionary.text(
                        "Enter number of agents:",
                        validate=lambda x: x.isdigit() and int(x) > 0,
                    ).ask()
                    num_agents = int(num_agents_text) if num_agents_text else recommended
                else:
                    num_agents = num_agents_choice
            except Exception as e:
                console.print(f"[warning]⚠️  Error with selection: {e}[/warning]")
                console.print(f"[info]Using recommended: {recommended} agents[/info]")
                num_agents = recommended

            if num_agents < 1:
                console.print("[warning]⚠️  Number of agents must be at least 1. Setting to 1.[/warning]")
                num_agents = 1

            available_providers = [p for p, has_key in api_keys.items() if has_key]

            if not available_providers:
                console.print("[error]❌ No providers with API keys found. Please set at least one API key.[/error]")
                raise ValueError("No providers available")

            # Step 2b: Same provider or mix?
            agents = []
            if num_agents == 1:
                # Single agent - just pick provider directly
                console.print()

                provider_choices = [
                    questionary.Choice(
                        self.PROVIDERS.get(pid, {}).get("name", pid),
                        value=pid,
                    )
                    for pid in available_providers
                ]

                provider_id = questionary.select(
                    "Select provider:",
                    choices=provider_choices,
                    style=questionary.Style(
                        [
                            ("selected", "fg:cyan bold"),
                            ("pointer", "fg:cyan bold"),
                            ("highlighted", "fg:cyan"),
                        ],
                    ),
                    use_arrow_keys=True,
                ).ask()

                if not provider_id:
                    provider_id = available_providers[0]

                agents = self.batch_create_agents(1, provider_id)
                provider_name = self.PROVIDERS.get(provider_id, {}).get("name", provider_id)
                console.print(f"\n✅ Created 1 {provider_name} agent\n")

            else:
                # Multiple agents - ask if same or different providers
                console.print()

                setup_mode = questionary.select(
                    "Setup mode:",
                    choices=[
                        questionary.Choice("Same provider for all agents (quick setup)", value="same"),
                        questionary.Choice("Mix different providers (advanced)", value="mix"),
                    ],
                    style=questionary.Style(
                        [
                            ("selected", "fg:cyan bold"),
                            ("pointer", "fg:cyan bold"),
                            ("highlighted", "fg:cyan"),
                        ],
                    ),
                    use_arrow_keys=True,
                ).ask()

                if not setup_mode:
                    setup_mode = "same"

                if setup_mode == "same":
                    # Batch creation with same provider
                    console.print()

                    provider_choices = [
                        questionary.Choice(
                            self.PROVIDERS.get(pid, {}).get("name", pid),
                            value=pid,
                        )
                        for pid in available_providers
                    ]

                    provider_id = questionary.select(
                        "Select provider:",
                        choices=provider_choices,
                        style=questionary.Style(
                            [
                                ("selected", "fg:cyan bold"),
                                ("pointer", "fg:cyan bold"),
                                ("highlighted", "fg:cyan"),
                            ],
                        ),
                        use_arrow_keys=True,
                    ).ask()

                    if not provider_id:
                        provider_id = available_providers[0]

                    agents = self.batch_create_agents(num_agents, provider_id)
                    provider_name = self.PROVIDERS.get(provider_id, {}).get("name", provider_id)
                    console.print(f"\n✅ Created {num_agents} {provider_name} agents\n")

                else:
                    # Advanced: mix providers
                    console.print("\n[yellow]💡 Advanced mode: Configure each agent individually[/yellow]\n")
                    for i in range(num_agents):
                        try:
                            console.print(f"[bold cyan]Agent {i + 1} of {num_agents}:[/bold cyan]")

                            provider_choices = [
                                questionary.Choice(
                                    self.PROVIDERS.get(pid, {}).get("name", pid),
                                    value=pid,
                                )
                                for pid in available_providers
                            ]

                            provider_id = questionary.select(
                                f"Select provider for agent {i + 1}:",
                                choices=provider_choices,
                                style=questionary.Style(
                                    [
                                        ("selected", "fg:cyan bold"),
                                        ("pointer", "fg:cyan bold"),
                                        ("highlighted", "fg:cyan"),
                                    ],
                                ),
                                use_arrow_keys=True,
                            ).ask()

                            if not provider_id:
                                provider_id = available_providers[0]

                            agent_batch = self.batch_create_agents(1, provider_id)
                            agents.extend(agent_batch)

                            provider_name = self.PROVIDERS.get(provider_id, {}).get("name", provider_id)
                            console.print(f"✅ Agent {i + 1} created: {provider_name}\n")

                        except (KeyboardInterrupt, EOFError):
                            raise
                        except Exception as e:
                            console.print(f"[error]❌ Error configuring agent {i + 1}: {e}[/error]")
                            console.print("[info]Skipping this agent...[/info]")

            if not agents:
                console.print("[error]❌ No agents were successfully configured.[/error]")
                raise ValueError("Failed to configure any agents")

            # Step 2c: Model selection and preset application
            console.print()
            sep_width = console.width - 4
            console.print("━" * sep_width)
            console.print("[bold cyan]Step 3 of 4: Agent Configuration[/bold cyan]")
            console.print("━" * sep_width)
            console.print()

            # For non-custom presets, show info and configure models
            if use_case != "custom":
                use_case_info = self.USE_CASES.get(use_case, {})
                recommended_tools = use_case_info.get("recommended_tools", [])

                console.print(f"[bold green]✓ Preset Selected:[/bold green] {use_case_info.get('name', use_case)}")
                console.print(f"[dim]{use_case_info.get('description', '')}[/dim]\n")

                if recommended_tools:
                    console.print("[cyan]This preset will auto-configure:[/cyan]")
                    for tool in recommended_tools:
                        tool_display = {
                            "filesystem": "📁 Filesystem access",
                            "code_execution": "💻 Code execution",
                            "web_search": "🔍 Web search",
                            "mcp": "🔌 MCP servers",
                        }.get(tool, tool)
                        console.print(f"  • {tool_display}")

                    if use_case == "coding_docker":
                        console.print("  • 🐳 Docker isolated execution")

                    console.print()

                # Let users select models for each agent
                console.print("[cyan]Select models for your agents:[/cyan]\n")
                for i, agent in enumerate(agents, 1):
                    backend_type = agent.get("backend", {}).get("type")
                    provider_info = None

                    # Find provider info
                    for pid, pinfo in self.PROVIDERS.items():
                        if pinfo.get("type") == backend_type:
                            provider_info = pinfo
                            break

                    if provider_info:
                        models = provider_info.get("models", [])
                        if models and len(models) > 1:
                            current_model = agent["backend"].get("model")
                            console.print(f"[bold]Agent {i} ({agent['id']}) - {provider_info.get('name')}:[/bold]")

                            model_choices = [
                                questionary.Choice(
                                    f"{model}" + (" (default)" if model == current_model else ""),
                                    value=model,
                                )
                                for model in models
                            ]

                            selected_model = questionary.select(
                                "Select model:",
                                choices=model_choices,
                                default=current_model,
                                style=questionary.Style(
                                    [
                                        ("selected", "fg:cyan bold"),
                                        ("pointer", "fg:cyan bold"),
                                        ("highlighted", "fg:cyan"),
                                    ],
                                ),
                                use_arrow_keys=True,
                            ).ask()

                            if selected_model:
                                agent["backend"]["model"] = selected_model
                            console.print(f"  ✓ {selected_model}\n")

                # Auto-apply preset to all agents
                console.print("[cyan]Applying preset configuration to all agents...[/cyan]")
                for i, agent in enumerate(agents):
                    agents[i] = self.apply_preset_to_agent(agent, use_case)

                console.print(f"[green]✅ {len(agents)} agent(s) configured with preset[/green]\n")

                # Ask if user wants additional customization
                if Confirm.ask("[prompt]Further customize agent settings (advanced)?[/prompt]", default=False):
                    console.print("\n[cyan]Entering advanced customization...[/cyan]\n")
                    for i, agent in enumerate(agents, 1):
                        agent = self.customize_agent(agent, i, len(agents), use_case=use_case)
                        agents[i - 1] = agent
            else:
                # Custom configuration - always customize
                console.print("[cyan]Custom configuration - configuring each agent...[/cyan]\n")
                for i, agent in enumerate(agents, 1):
                    agent = self.customize_agent(agent, i, len(agents), use_case=use_case)
                    agents[i - 1] = agent

            return agents

        except (KeyboardInterrupt, EOFError):
            raise
        except Exception as e:
            console.print(f"[error]❌ Fatal error in agent configuration: {e}[/error]")
            raise

    def configure_tools(self, use_case: str, agents: List[Dict]) -> Tuple[List[Dict], Dict]:
        """Configure orchestrator-level settings (tools are configured per-agent)."""
        try:
            console.print()
            sep_width = console.width - 4
            console.print("━" * sep_width)
            console.print("[bold cyan]Step 4 of 4: Orchestrator Configuration[/bold cyan]")
            console.print("━" * sep_width)
            console.print()
            console.print("[dim]Note: Tools and capabilities were configured per-agent in the previous step.[/dim]\n")

            orchestrator_config = {}

            # Check if any agents have filesystem enabled (Claude Code with cwd)
            has_filesystem = any(a.get("backend", {}).get("cwd") or a.get("backend", {}).get("type") == "claude_code" for a in agents)

            if has_filesystem:
                console.print("[cyan]Filesystem-enabled agents detected[/cyan]\n")
                orchestrator_config["snapshot_storage"] = "snapshots"
                orchestrator_config["agent_temporary_workspace"] = "temp_workspaces"

                # Context paths
                console.print("[dim]Context paths give agents access to your project files.[/dim]")
                console.print("[dim]Paths can be absolute or relative (resolved against current directory).[/dim]")
                console.print("[dim]Note: During coordination, all context paths are read-only.[/dim]")
                console.print("[dim]      Write permission applies only to the final agent.[/dim]\n")

                if Confirm.ask("[prompt]Add context paths?[/prompt]", default=False):
                    context_paths = []
                    while True:
                        path = Prompt.ask("[prompt]Enter directory or file path (or press Enter to finish)[/prompt]")
                        if not path:
                            break

                        permission = Prompt.ask(
                            "[prompt]Permission (write means final agent can modify)[/prompt]",
                            choices=["read", "write"],
                            default="write",
                        )

                        context_path_entry = {
                            "path": path,
                            "permission": permission,
                        }

                        # If write permission, offer to add protected paths
                        if permission == "write":
                            console.print("[dim]Protected paths are files/directories immune from modification[/dim]")
                            if Confirm.ask("[prompt]Add protected paths (e.g., .env, config.json)?[/prompt]", default=False):
                                protected_paths = []
                                console.print("[dim]Enter paths relative to the context path (or press Enter to finish)[/dim]")
                                while True:
                                    protected_path = Prompt.ask("[prompt]Protected path[/prompt]")
                                    if not protected_path:
                                        break
                                    protected_paths.append(protected_path)
                                    console.print(f"🔒 Protected: {protected_path}")

                                if protected_paths:
                                    context_path_entry["protected_paths"] = protected_paths

                        context_paths.append(context_path_entry)
                        console.print(f"✅ Added: {path} ({permission})")

                    if context_paths:
                        orchestrator_config["context_paths"] = context_paths

            # Multi-turn sessions (always enabled)
            if not orchestrator_config:
                orchestrator_config = {}
            orchestrator_config["session_storage"] = "sessions"
            console.print("✅ Multi-turn sessions enabled (supports persistent conversations with memory)")

            # Planning Mode (for MCP irreversible actions)
            console.print("\n[dim]Planning Mode: Prevents MCP tool execution during coordination (for irreversible actions like Discord/Twitter posts)[/dim]")
            if Confirm.ask("[prompt]Enable planning mode for MCP tools?[/prompt]", default=False):
                orchestrator_config["coordination"] = {
                    "enable_planning_mode": True,
                }
                console.print("✅ Planning mode enabled - MCP tools will plan without executing during coordination")

            return agents, orchestrator_config

        except (KeyboardInterrupt, EOFError):
            raise
        except Exception as e:
            console.print(f"[error]❌ Error configuring orchestrator: {e}[/error]")
            console.print("[info]Returning agents with basic configuration...[/info]")
            return agents, {}

    def review_and_save(self, agents: List[Dict], orchestrator_config: Dict) -> Optional[str]:
        """Review configuration and save to file with error handling."""
        try:
            console.print()
            sep_width = console.width - 4
            console.print("━" * sep_width)
            console.print("[bold green]✅ Review & Save Configuration[/bold green]")
            console.print("━" * sep_width)
            console.print()

            # Build final config
            self.config["agents"] = agents
            if orchestrator_config:
                self.config["orchestrator"] = orchestrator_config

            # Display configuration
            try:
                console.print("[bold cyan]Generated Configuration:[/bold cyan]")
                console.print()
                yaml_content = yaml.dump(self.config, default_flow_style=False, sort_keys=False)
                console.print(Panel(yaml_content, title="Config Preview", border_style="green"))
            except Exception as e:
                console.print(f"[warning]⚠️  Could not preview YAML: {e}[/warning]")
                console.print("[info]Proceeding with save...[/info]")

            if not Confirm.ask("\n[prompt]Save this configuration?[/prompt]", default=True):
                console.print("[info]Configuration not saved.[/info]")
                return None

            # Determine save location
            if self.default_mode:
                # First-run mode: save to ~/.config/massgen/config.yaml
                config_dir = Path.home() / ".config/massgen"
                config_dir.mkdir(parents=True, exist_ok=True)
                filepath = config_dir / "config.yaml"

                # If file exists, ask to overwrite
                if filepath.exists():
                    if not Confirm.ask("\n[yellow]⚠️  Default config already exists. Overwrite?[/yellow]", default=True):
                        console.print("[info]Configuration not saved.[/info]")
                        return None

                # Save the file
                with open(filepath, "w") as f:
                    yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)

                console.print(f"\n✅ [success]Configuration saved to: {filepath}[/success]")
                return str(filepath)

            # File saving loop with rename option (standard mode)
            default_name = "my_massgen_config.yaml"
            filename = None

            # Ask where to save
            console.print("\nWhere would you like to save the config?")
            console.print("  [1] Current directory (default)")
            console.print("  [2] MassGen config directory (~/.config/massgen/agents/)")

            save_location = Prompt.ask(
                "[prompt]Choose location[/prompt]",
                choices=["1", "2"],
                default="1",
            )

            if save_location == "2":
                # Save to ~/.config/massgen/agents/
                agents_dir = Path.home() / ".config/massgen/agents"
                agents_dir.mkdir(parents=True, exist_ok=True)
                default_name = str(agents_dir / "my_massgen_config.yaml")

            while True:
                try:
                    # Get filename with validation
                    if filename is None:
                        filename = Prompt.ask(
                            "[prompt]Config filename[/prompt]",
                            default=default_name,
                        )

                    if not filename:
                        console.print("[warning]⚠️  Empty filename, using default.[/warning]")
                        filename = default_name

                    if not filename.endswith(".yaml"):
                        filename += ".yaml"

                    filepath = Path(filename)

                    # Check if file exists
                    if filepath.exists():
                        console.print(f"\n[yellow]⚠️  File '{filename}' already exists![/yellow]")
                        console.print("\nWhat would you like to do?")
                        console.print("  1. Rename (enter a new filename)")
                        console.print("  2. Overwrite (replace existing file)")
                        console.print("  3. Cancel (don't save)")

                        choice = Prompt.ask(
                            "\n[prompt]Choose an option[/prompt]",
                            choices=["1", "2", "3"],
                            default="1",
                        )

                        if choice == "1":
                            # Ask for new filename
                            filename = Prompt.ask(
                                "[prompt]Enter new filename[/prompt]",
                                default=f"config_{Path(filename).stem}.yaml",
                            )
                            continue  # Loop back to check new filename
                        elif choice == "2":
                            # User chose to overwrite
                            pass  # Continue to save
                        else:  # choice == "3"
                            console.print("[info]Save cancelled.[/info]")
                            return None

                    # Save the file
                    with open(filepath, "w") as f:
                        yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)

                    console.print(f"\n✅ [success]Configuration saved to: {filepath.absolute()}[/success]")
                    return str(filepath)

                except PermissionError:
                    console.print(f"[error]❌ Permission denied: Cannot write to {filename}[/error]")
                    console.print("[info]Would you like to try a different filename?[/info]")
                    if Confirm.ask("[prompt]Try again?[/prompt]", default=True):
                        filename = None  # Reset to ask again
                        continue
                    else:
                        return None
                except OSError as e:
                    console.print(f"[error]❌ OS error saving file: {e}[/error]")
                    console.print("[info]Would you like to try a different filename?[/info]")
                    if Confirm.ask("[prompt]Try again?[/prompt]", default=True):
                        filename = None  # Reset to ask again
                        continue
                    else:
                        return None
                except Exception as e:
                    console.print(f"[error]❌ Unexpected error saving file: {e}[/error]")
                    return None

        except (KeyboardInterrupt, EOFError):
            console.print("\n[info]Save cancelled by user.[/info]")
            return None
        except Exception as e:
            console.print(f"[error]❌ Error in review and save: {e}[/error]")
            return None

    def run(self) -> Optional[tuple]:
        """Run the interactive configuration builder with comprehensive error handling."""
        try:
            self.show_banner()

            # Detect API keys with error handling
            try:
                api_keys = self.detect_api_keys()
            except Exception as e:
                console.print(f"[error]❌ Failed to detect API keys: {e}[/error]")
                api_keys = {}

            # Show available providers
            self.show_available_providers(api_keys)

            # Check if any API keys are available
            if not any(api_keys.values()):
                console.print("[error]❌ No API keys found in environment![/error]")
                console.print("\n[yellow]Please set at least one API key in your .env file:[/yellow]")
                for provider_id, provider_info in self.PROVIDERS.items():
                    if provider_info.get("env_var"):
                        console.print(f"  - {provider_info['env_var']}")
                console.print("\n[info]Tip: Copy .env.example to .env and add your keys[/info]")
                return None

            try:
                # Step 1: Select use case
                use_case = self.select_use_case()
                if not use_case:
                    console.print("[warning]⚠️  No use case selected.[/warning]")
                    return None

                # Step 2: Configure agents
                agents = self.configure_agents(use_case, api_keys)
                if not agents:
                    console.print("[error]❌ No agents configured.[/error]")
                    return None

                # Step 3: Configure tools
                try:
                    agents, orchestrator_config = self.configure_tools(use_case, agents)
                except Exception as e:
                    console.print(f"[warning]⚠️  Error configuring tools: {e}[/warning]")
                    console.print("[info]Continuing with basic configuration...[/info]")
                    orchestrator_config = {}

                # Step 4: Review and save
                filepath = self.review_and_save(agents, orchestrator_config)

                if filepath:
                    # Ask if user wants to run now
                    try:
                        if Confirm.ask("\n[prompt]Run MassGen with this configuration now?[/prompt]", default=True):
                            question = Prompt.ask("\n[prompt]Enter your question[/prompt]")
                            if question:
                                console.print(f'\n[info]Running: massgen --config {filepath} "{question}"[/info]\n')
                                return (filepath, question)
                            else:
                                console.print("[warning]⚠️  No question provided.[/warning]")
                                return (filepath, None)
                    except (KeyboardInterrupt, EOFError):
                        console.print("\n[info]Skipping immediate run.[/info]")
                        return (filepath, None)

                return (filepath, None) if filepath else None

            except (KeyboardInterrupt, EOFError):
                console.print("\n\n[warning]⚠️  Configuration cancelled by user[/warning]")
                return None
            except ValueError as e:
                console.print(f"\n[error]❌ Configuration error: {str(e)}[/error]")
                console.print("[info]Please check your inputs and try again.[/info]")
                return None
            except Exception as e:
                console.print(f"\n[error]❌ Unexpected error during configuration: {str(e)}[/error]")
                console.print(f"[info]Error type: {type(e).__name__}[/info]")
                return None

        except KeyboardInterrupt:
            console.print("\n\n[warning]⚠️  Configuration cancelled by user (Ctrl+C)[/warning]")
            return None
        except EOFError:
            console.print("\n\n[warning]⚠️  Configuration cancelled (EOF)[/warning]")
            return None
        except Exception as e:
            console.print(f"\n[error]❌ Fatal error: {str(e)}[/error]")
            console.print("[info]Please report this issue if it persists.[/info]")
            return None


def main() -> None:
    """Main entry point for the config builder."""
    builder = ConfigBuilder()
    result = builder.run()

    if result and len(result) == 2:
        filepath, question = result
        if question:
            # Run MassGen with the created config
            console.print(
                "\n[bold green]✅ Configuration created successfully![/bold green]",
            )
            console.print("\n[bold cyan]Running MassGen...[/bold cyan]\n")

            import asyncio
            import sys

            # Simulate CLI call with the config
            original_argv = sys.argv.copy()
            sys.argv = ["massgen", "--config", filepath, question]

            try:
                from .cli import main as cli_main

                asyncio.run(cli_main())
            finally:
                sys.argv = original_argv
        else:
            console.print(
                "\n[bold green]✅ Configuration saved![/bold green]",
            )
            console.print("\n[bold cyan]To use it, run:[/bold cyan]")
            console.print(
                f"  [yellow]python -m massgen.cli --config {filepath} " '"Your question"[/yellow]\n',
            )
    else:
        console.print("[yellow]Configuration builder exited.[/yellow]")


if __name__ == "__main__":
    main()
