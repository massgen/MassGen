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

import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table
from rich.theme import Theme

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

    # Model provider configurations
    PROVIDERS = {
        "openai": {
            "name": "OpenAI (GPT-5, GPT-4, etc.)",
            "type": "openai",
            "env_var": "OPENAI_API_KEY",
            "models": ["gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-4o", "gpt-4o-mini"],
            "supports": ["web_search", "code_execution", "mcp", "multimodal"],
        },
        "claude": {
            "name": "Anthropic Claude",
            "type": "claude",
            "env_var": "ANTHROPIC_API_KEY",
            "models": ["claude-sonnet-4-20250514", "claude-opus-4", "claude-3-5-sonnet-latest"],
            "supports": ["web_search", "code_execution", "mcp"],
        },
        "claude_code": {
            "name": "Claude Code (Native SDK)",
            "type": "claude_code",
            "env_var": "ANTHROPIC_API_KEY",
            "models": ["claude-sonnet-4", "claude-opus-4"],
            "supports": ["filesystem", "mcp", "bash"],
        },
        "gemini": {
            "name": "Google Gemini",
            "type": "gemini",
            "env_var": "GEMINI_API_KEY",
            "models": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
            "supports": ["web_search", "code_execution", "mcp"],
        },
        "grok": {
            "name": "xAI Grok",
            "type": "grok",
            "env_var": "XAI_API_KEY",
            "models": ["grok-4", "grok-3", "grok-3-mini"],
            "supports": ["web_search", "mcp"],
        },
        "azure": {
            "name": "Azure OpenAI",
            "type": "azure_openai",
            "env_var": "AZURE_OPENAI_API_KEY",
            "models": ["gpt-4", "gpt-4o", "gpt-35-turbo"],
            "supports": ["web_search", "code_execution"],
        },
        "local": {
            "name": "Local Models (LM Studio)",
            "type": "lmstudio",
            "env_var": None,
            "models": ["lmstudio-community/Qwen2.5-7B-Instruct-GGUF", "custom"],
            "supports": [],
        },
    }

    # Use case templates - all use cases support all agent types
    USE_CASES = {
        "qa": {
            "name": "Simple Q&A",
            "description": "Basic question answering with single or multiple agents",
            "recommended_agents": 1,
            "recommended_tools": [],
            "agent_types": "all",  # Any agent type works
            "notes": "Start simple with 1 agent, add more for diverse perspectives",
        },
        "research": {
            "name": "Research & Analysis",
            "description": "Multi-agent research with web search and diverse perspectives",
            "recommended_agents": 3,
            "recommended_tools": ["web_search"],
            "agent_types": "all",
            "notes": "Works best with web search enabled for current information",
        },
        "coding": {
            "name": "Code Generation & Development",
            "description": "Generate code with file operations and code execution",
            "recommended_agents": 2,
            "recommended_tools": ["code_execution", "filesystem"],
            "agent_types": "all",
            "notes": "Claude Code recommended for best filesystem support",
        },
        "creative": {
            "name": "Creative Writing",
            "description": "Collaborative creative writing with multiple perspectives",
            "recommended_agents": 3,
            "recommended_tools": [],
            "agent_types": "all",
            "notes": "Multiple agents provide diverse creative perspectives",
        },
        "data_analysis": {
            "name": "Data Analysis",
            "description": "Analyze data with code execution and visualizations",
            "recommended_agents": 2,
            "recommended_tools": ["code_execution", "filesystem"],
            "agent_types": "all",
            "notes": "Code execution helps with data processing and visualization",
        },
        "web_automation": {
            "name": "Web Automation",
            "description": "Browser automation and web scraping",
            "recommended_agents": 2,
            "recommended_tools": ["mcp", "filesystem"],
            "agent_types": "all",
            "notes": "MCP servers provide browser automation capabilities",
        },
        "custom": {
            "name": "Custom Configuration",
            "description": "Build your own custom setup - full flexibility",
            "recommended_agents": 1,
            "recommended_tools": [],
            "agent_types": "all",
            "notes": "Choose any combination of agents and tools",
        },
    }

    # MCP server templates
    MCP_SERVERS = {
        "weather": {
            "name": "Weather Information",
            "command": "npx",
            "args": ["-y", "@fak111/weather-mcp"],
            "env_vars": [],
        },
        "brave_search": {
            "name": "Brave Web Search",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-brave-search"],
            "env_vars": ["BRAVE_API_KEY"],
        },
        "filesystem": {
            "name": "Filesystem Operations",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
            "env_vars": [],
        },
        "notion": {
            "name": "Notion Integration",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-notion"],
            "env_vars": ["NOTION_API_KEY"],
        },
    }

    def __init__(self) -> None:
        """Initialize the configuration builder with default config."""
        self.config = {
            "agents": [],
            "ui": {
                "display_type": "rich_terminal",
                "logging_enabled": True,
            },
        }
        self.orchestrator_config = {}

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
        """Display table of available providers with error handling."""
        try:
            table = Table(title="Available Model Providers", show_header=True)
            table.add_column("ID", style="cyan")
            table.add_column("Provider", style="green")
            table.add_column("API Key", style="yellow")
            table.add_column("Capabilities", style="blue")

            for provider_id, provider_info in self.PROVIDERS.items():
                try:
                    has_key = "✅ Found" if api_keys.get(provider_id, False) else "❌ Missing"
                    capabilities = ", ".join(provider_info.get("supports", []))
                    table.add_row(
                        provider_id,
                        provider_info.get("name", "Unknown"),
                        has_key,
                        capabilities or "Basic",
                    )
                except Exception as e:
                    console.print(f"[warning]⚠️  Could not display {provider_id}: {e}[/warning]")

            console.print(table)
            console.print()
        except Exception as e:
            console.print(f"[error]❌ Error displaying providers: {e}[/error]")
            console.print("[info]Continuing with setup...[/info]\n")

    def select_use_case(self) -> str:
        """Let user select a use case template with error handling."""
        try:
            console.print(Panel("📋 Step 1: Select Your Use Case", style="bold blue"))
            console.print("[italic]All agent types are supported for every use case[/italic]\n")

            for i, (use_case_id, use_case_info) in enumerate(self.USE_CASES.items(), 1):
                try:
                    console.print(f"{i}. [bold cyan]{use_case_info.get('name', 'Unknown')}[/bold cyan]")
                    console.print(f"   {use_case_info.get('description', '')}")
                    console.print(f"   Recommended: {use_case_info.get('recommended_agents', 1)} agents")

                    # Show recommended tools if any
                    if use_case_info.get("recommended_tools"):
                        tools_str = ", ".join(use_case_info["recommended_tools"])
                        console.print(f"   Suggested tools: {tools_str}")
                    console.print()
                except Exception as e:
                    console.print(f"[warning]⚠️  Could not display use case {i}: {e}[/warning]")

            choice = IntPrompt.ask(
                "[prompt]Select use case[/prompt]",
                choices=[str(i) for i in range(1, len(self.USE_CASES) + 1)],
                default="1",
            )

            use_case_id = list(self.USE_CASES.keys())[choice - 1]
            console.print(f"✅ Selected: [green]{self.USE_CASES[use_case_id].get('name', use_case_id)}[/green]\n")
            return use_case_id
        except (KeyboardInterrupt, EOFError):
            raise  # Re-raise to be handled by run()
        except Exception as e:
            console.print(f"[error]❌ Error selecting use case: {e}[/error]")
            console.print("[info]Defaulting to 'qa' use case[/info]\n")
            return "qa"  # Safe default

    def configure_agents(self, use_case: str, api_keys: Dict[str, bool]) -> List[Dict]:
        """Configure agents with comprehensive error handling."""
        try:
            console.print(Panel("🤖 Step 2: Configure Agents", style="bold blue"))
            console.print("[italic]Choose any provider(s) - all types work for your selected use case[/italic]\n")

            use_case_info = self.USE_CASES.get(use_case, {})
            recommended = use_case_info.get("recommended_agents", 1)

            num_agents = IntPrompt.ask(
                "[prompt]How many agents?[/prompt]",
                default=recommended,
                show_default=True,
            )

            if num_agents < 1:
                console.print("[warning]⚠️  Number of agents must be at least 1. Setting to 1.[/warning]")
                num_agents = 1

            agents = []
            available_providers = [p for p, has_key in api_keys.items() if has_key]

            if not available_providers:
                console.print("[error]❌ No providers with API keys found. Please set at least one API key.[/error]")
                raise ValueError("No providers available")

            for i in range(num_agents):
                try:
                    console.print(f"\n[bold cyan]Agent {i + 1} Configuration:[/bold cyan]")

                    # Show available providers
                    console.print("\nAvailable providers:")
                    for j, provider_id in enumerate(available_providers, 1):
                        provider_name = self.PROVIDERS.get(provider_id, {}).get("name", provider_id)
                        console.print(f"{j}. {provider_name}")

                    provider_choice = IntPrompt.ask(
                        "[prompt]Select provider[/prompt]",
                        choices=[str(j) for j in range(1, len(available_providers) + 1)],
                        default="1",
                    )

                    provider_id = available_providers[provider_choice - 1]
                    provider_info = self.PROVIDERS.get(provider_id, {})

                    if not provider_info:
                        console.print(f"[error]❌ Provider {provider_id} not found. Skipping agent {i + 1}.[/error]")
                        continue

                    # Select model
                    models = provider_info.get("models", [])
                    if not models:
                        console.print(f"[error]❌ No models available for {provider_id}. Skipping agent {i + 1}.[/error]")
                        continue

                    console.print(f"\nAvailable models for {provider_info.get('name', provider_id)}:")
                    for j, model in enumerate(models, 1):
                        console.print(f"{j}. {model}")

                    model_choice = IntPrompt.ask(
                        "[prompt]Select model[/prompt]",
                        choices=[str(j) for j in range(1, len(models) + 1)],
                        default="1",
                    )

                    model = models[model_choice - 1]

                    # Build agent config
                    agent = {
                        "id": f"{provider_id}_agent_{i + 1}",
                        "backend": {
                            "type": provider_info.get("type", provider_id),
                            "model": model,
                        },
                    }

                    # Add workspace for Claude Code
                    if provider_info.get("type") == "claude_code":
                        agent["backend"]["cwd"] = f"workspace_{i + 1}"

                    agents.append(agent)
                    console.print(f"✅ Agent {i + 1} configured: [green]{provider_info.get('name', provider_id)} - {model}[/green]")

                except (KeyboardInterrupt, EOFError):
                    raise
                except Exception as e:
                    console.print(f"[error]❌ Error configuring agent {i + 1}: {e}[/error]")
                    console.print("[info]Skipping this agent...[/info]")

            if not agents:
                console.print("[error]❌ No agents were successfully configured.[/error]")
                raise ValueError("Failed to configure any agents")

            return agents

        except (KeyboardInterrupt, EOFError):
            raise
        except Exception as e:
            console.print(f"[error]❌ Fatal error in agent configuration: {e}[/error]")
            raise

    def configure_tools(self, use_case: str, agents: List[Dict]) -> Tuple[List[Dict], Dict]:
        """Configure tools for agents with error handling."""
        try:
            console.print(Panel("🔧 Step 3: Configure Tools & Capabilities", style="bold blue"))
            console.print()

            use_case_info = self.USE_CASES.get(use_case, {})
            recommended_tools = use_case_info.get("recommended_tools", [])

            # Show use case specific notes
            if use_case_info.get("notes"):
                console.print(f"[italic cyan]💡 {use_case_info['notes']}[/italic cyan]\n")

            # Web Search - smart default based on recommendations
            web_search_default = "web_search" in recommended_tools
            web_search_prompt = "[prompt]Enable web search?[/prompt]"
            if web_search_default:
                web_search_prompt += " (recommended for this use case)"

            if Confirm.ask(web_search_prompt, default=web_search_default):
                enabled_count = 0
                for agent in agents:
                    backend_type = agent.get("backend", {}).get("type")
                    if backend_type and "web_search" in self.PROVIDERS.get(backend_type, {}).get("supports", []):
                        if backend_type in ["openai", "claude", "gemini", "grok"]:
                            agent["backend"]["enable_web_search"] = True
                            enabled_count += 1
                if enabled_count > 0:
                    console.print(f"✅ Web search enabled for {enabled_count} compatible agent(s)")
                else:
                    console.print("[yellow]⚠️  No agents support web search[/yellow]")

            # Code Execution - smart default based on recommendations
            code_exec_default = "code_execution" in recommended_tools
            code_exec_prompt = "[prompt]Enable code execution?[/prompt]"
            if code_exec_default:
                code_exec_prompt += " (recommended for this use case)"

            if Confirm.ask(code_exec_prompt, default=code_exec_default):
                enabled_count = 0
                for agent in agents:
                    backend_type = agent.get("backend", {}).get("type")
                    if backend_type and "code_execution" in self.PROVIDERS.get(backend_type, {}).get("supports", []):
                        if backend_type == "openai":
                            agent["backend"]["enable_code_interpreter"] = True
                            enabled_count += 1
                        elif backend_type in ["claude", "gemini"]:
                            agent["backend"]["enable_code_execution"] = True
                            enabled_count += 1
                if enabled_count > 0:
                    console.print(f"✅ Code execution enabled for {enabled_count} compatible agent(s)")
                else:
                    console.print("[yellow]⚠️  No agents support code execution[/yellow]")

            # Filesystem Operations - smart default based on recommendations
            orchestrator_config = {}
            filesystem_default = "filesystem" in recommended_tools
            filesystem_prompt = "[prompt]Enable filesystem operations?[/prompt]"
            if filesystem_default:
                filesystem_prompt += " (recommended for this use case)"

            if Confirm.ask(filesystem_prompt, default=filesystem_default):
                orchestrator_config["snapshot_storage"] = "snapshots"
                orchestrator_config["agent_temporary_workspace"] = "temp_workspaces"

                # Check if any Claude Code agents
                has_claude_code = any(a.get("backend", {}).get("type") == "claude_code" for a in agents)
                if not has_claude_code:
                    console.print("[yellow]Note: Filesystem works best with Claude Code agents[/yellow]")

                # Context paths
                if Confirm.ask("[prompt]Add context paths (access to your project files)?[/prompt]", default=False):
                    context_paths = []
                    while True:
                        path = Prompt.ask("[prompt]Enter directory path (or press Enter to finish)[/prompt]")
                        if not path:
                            break

                        permission = Prompt.ask(
                            "[prompt]Permission[/prompt]",
                            choices=["read", "write"],
                            default="read",
                        )

                        context_paths.append(
                            {
                                "path": path,
                                "permission": permission,
                            },
                        )
                        console.print(f"✅ Added: {path} ({permission})")

                    if context_paths:
                        orchestrator_config["context_paths"] = context_paths

                console.print("✅ Filesystem operations configured")

            # MCP Servers - smart default based on recommendations
            mcp_default = "mcp" in recommended_tools
            mcp_prompt = "[prompt]Add MCP servers?[/prompt]"
            if mcp_default:
                mcp_prompt += " (recommended for this use case)"

            if Confirm.ask(mcp_prompt, default=mcp_default):
                console.print("\nAvailable MCP servers:")
                for i, (server_id, server_info) in enumerate(self.MCP_SERVERS.items(), 1):
                    console.print(f"{i}. {server_info.get('name', server_id)}")
                    if server_info.get("env_vars"):
                        env_status = " & ".join([f"{var}: {'✅' if os.getenv(var) else '❌'}" for var in server_info["env_vars"]])
                        console.print(f"   Requires: {env_status}")

                mcp_choice = Prompt.ask(
                    "[prompt]Select MCP servers (comma-separated numbers, or Enter to skip)[/prompt]",
                    default="",
                )

                if mcp_choice:
                    try:
                        selected_servers = [int(x.strip()) - 1 for x in mcp_choice.split(",") if x.strip()]
                        server_ids = list(self.MCP_SERVERS.keys())

                        for agent in agents:
                            backend_type = agent.get("backend", {}).get("type")
                            if backend_type and "mcp" in self.PROVIDERS.get(backend_type, {}).get("supports", []):
                                mcp_servers = []
                                for idx in selected_servers:
                                    if 0 <= idx < len(server_ids):
                                        server_id = server_ids[idx]
                                        server_info = self.MCP_SERVERS[server_id]

                                        mcp_server = {
                                            "name": server_id,
                                            "type": "stdio",
                                            "command": server_info["command"],
                                            "args": server_info["args"],
                                        }

                                        if server_info.get("env_vars"):
                                            mcp_server["env"] = {var: f"${{{var}}}" for var in server_info["env_vars"]}

                                        mcp_servers.append(mcp_server)

                                if mcp_servers:
                                    agent["backend"]["mcp_servers"] = mcp_servers

                        console.print("✅ MCP servers configured")
                    except (ValueError, IndexError) as e:
                        console.print(f"[warning]⚠️  Invalid MCP server selection: {e}[/warning]")

            # Planning Mode
            if orchestrator_config and Confirm.ask("[prompt]Enable planning mode (safer for irreversible operations)?[/prompt]", default=False):
                orchestrator_config["coordination"] = {
                    "enable_planning_mode": True,
                }
                console.print("✅ Planning mode enabled")

            # Multi-turn sessions
            if Confirm.ask("[prompt]Enable multi-turn sessions (persistent conversations)?[/prompt]", default=False):
                orchestrator_config["session_storage"] = "sessions"
                console.print("✅ Multi-turn sessions enabled")

            return agents, orchestrator_config

        except (KeyboardInterrupt, EOFError):
            raise
        except Exception as e:
            console.print(f"[error]❌ Error configuring tools: {e}[/error]")
            console.print("[info]Returning agents with basic configuration...[/info]")
            return agents, {}

    def review_and_save(self, agents: List[Dict], orchestrator_config: Dict) -> Optional[str]:
        """Review configuration and save to file with error handling."""
        try:
            console.print(Panel("📝 Step 4: Review & Save Configuration", style="bold blue"))
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

            # File saving loop with rename option
            default_name = "my_massgen_config.yaml"
            filename = None

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
