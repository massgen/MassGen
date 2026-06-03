#!/usr/bin/env python3
"""Discovery, selection, and display of bundled example configs.

Part of the massgen.cli package (extracted from the legacy monolithic cli.py).
"""

import sys
from pathlib import Path
from typing import (
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    pass

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..logger_config import logger

# --- cross-module references within the cli package ---
from ._constants import (
    BRIGHT_BLUE,
    BRIGHT_CYAN,
    BRIGHT_GREEN,
    BRIGHT_YELLOW,
    MASSGEN_QUESTIONARY_STYLE,
    RESET,
)
from .config_loading import ConfigurationError, resolve_config_path


def _print_backends_table() -> None:
    """Print a table of all supported backends with models, capabilities, and auth."""
    from massgen.backend.capabilities import BACKEND_CAPABILITIES

    # Column widths
    w_type = 16
    w_name = 22
    w_default = 26
    w_auth = 28
    w_caps = 40

    header = f"{'Backend Type':<{w_type}}" f"{'Provider':<{w_name}}" f"{'Default Model':<{w_default}}" f"{'Auth':<{w_auth}}" f"{'Key Capabilities'}"
    sep = "-" * (w_type + w_name + w_default + w_auth + w_caps)

    print(f"\n{sep}")
    print("MASSGEN SUPPORTED BACKENDS")
    print(f"{sep}\n")
    print(header)
    print(sep)

    for backend_type, caps in sorted(BACKEND_CAPABILITIES.items()):
        # Auth info
        if caps.env_var:
            auth = f"{caps.env_var}"
            # Agent-based backends also support login
            if backend_type in ("claude_code", "codex"):
                auth += " or login"
            elif backend_type == "copilot":
                auth = "GitHub Copilot subscription"
        else:
            auth = "none"

        # Key capabilities (abbreviated)
        cap_list = []
        if "web_search" in caps.supported_capabilities:
            cap_list.append("web")
        if "code_execution" in caps.supported_capabilities:
            cap_list.append("code")
        if caps.filesystem_support == "native":
            cap_list.append("fs-native")
        elif caps.filesystem_support == "mcp":
            cap_list.append("fs-mcp")
        if "mcp" in caps.supported_capabilities:
            cap_list.append("mcp")
        if "reasoning" in caps.supported_capabilities:
            cap_list.append("reasoning")
        if "image_generation" in caps.supported_capabilities:
            cap_list.append("img-gen")
        if "image_understanding" in caps.supported_capabilities:
            cap_list.append("vision")
        cap_str = ", ".join(cap_list) if cap_list else "basic"

        print(
            f"{backend_type:<{w_type}}" f"{caps.provider_name:<{w_name}}" f"{caps.default_model:<{w_default}}" f"{auth:<{w_auth}}" f"{cap_str}",
        )

    print(f"\n{sep}")
    print("MODELS PER BACKEND")
    print(f"{sep}\n")

    for backend_type, caps in sorted(BACKEND_CAPABILITIES.items()):
        models_str = ", ".join(caps.models[:8])
        if len(caps.models) > 8:
            models_str += f" (+{len(caps.models) - 8} more)"
        print(f"  {backend_type}: {models_str}")

    print(f"\n{sep}")
    print(
        "Use with: massgen --quickstart --headless" " --config-backend <type> --config-model <model>",
    )
    print(
        "Mixed providers: massgen --quickstart --headless"
        " --quickstart-agent backend=claude,model=claude-opus-4-6"
        " --quickstart-agent backend=openai,model=gpt-5.4"
        " --quickstart-agent backend=gemini,model=gemini-3-flash-preview",
    )
    print()


def show_available_examples():
    """Display available example configurations from package."""
    try:
        from importlib.resources import files

        configs_root = files("massgen") / "configs"

        print(f"\n{BRIGHT_CYAN}Available Example Configurations{RESET}")
        print("=" * 60)

        # Organize by category
        categories = {}
        for config_file in sorted(configs_root.rglob("*.yaml")):
            # Get relative path from configs root
            rel_path = str(config_file).replace(str(configs_root) + "/", "")
            # Extract category (first directory)
            parts = rel_path.split("/")
            category = parts[0] if len(parts) > 1 else "root"

            if category not in categories:
                categories[category] = []

            # Create a short name for @examples/
            # Use the path without .yaml extension
            short_name = rel_path.replace(".yaml", "").replace("/", "_")

            categories[category].append((short_name, rel_path))

        # Display categories
        for category, configs in sorted(categories.items()):
            print(f"\n{BRIGHT_YELLOW}{category.title()}:{RESET}")
            for short_name, rel_path in configs[:10]:  # Limit to avoid overwhelming
                print(f"  {BRIGHT_GREEN}@examples/{short_name:<40}{RESET} {rel_path}")

            if len(configs) > 10:
                print(f"  ... and {len(configs) - 10} more")

        print(f"\n{BRIGHT_BLUE}Usage:{RESET}")
        print('  massgen --config @examples/SHORTNAME "Your question"')
        print("  massgen --example SHORTNAME > my-config.yaml")
        print()

    except Exception as e:
        print(f"Error listing examples: {e}")
        print("Examples may not be available (development mode?)")


def print_example_config(name: str):
    """Print an example config to stdout.

    Args:
        name: Name of the example (can include or exclude @examples/ prefix)
    """
    try:
        # Remove @examples/ prefix if present
        if name.startswith("@examples/"):
            name = name[10:]

        # Try to resolve the config
        resolved = resolve_config_path(f"@examples/{name}")
        if resolved:
            with open(resolved) as f:
                print(f.read())
        else:
            print(f"Error: Could not find example '{name}'", file=sys.stderr)
            print("Use --list-examples to see available configs", file=sys.stderr)
            sys.exit(1)

    except ConfigurationError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error printing example config: {e}", file=sys.stderr)
        sys.exit(1)


def discover_available_configs() -> dict[str, list[tuple[str, Path]]]:
    """Discover all available configuration files.

    Returns:
        Dict with categories as keys and list of (display_name, path) tuples as values
    """
    configs = {
        "User Configs": [],
        "Project Configs": [],
        "Current Directory": [],
        "Package Examples": [],
    }

    # 1. User configs (~/.config/massgen/agents/)
    user_agents_dir = Path.home() / ".config/massgen/agents"
    if user_agents_dir.exists():
        for config_file in sorted(user_agents_dir.glob("*.yaml")):
            display_name = config_file.stem
            configs["User Configs"].append((display_name, config_file))

    # 2. Project configs (.massgen/)
    project_config_dir = Path.cwd() / ".massgen"
    if project_config_dir.exists():
        for config_file in sorted(project_config_dir.glob("*.yaml")):
            display_name = f".massgen/{config_file.name}"
            configs["Project Configs"].append((display_name, config_file))

    # 3. Current directory (*.yaml files, excluding .massgen/ and non-massgen configs)
    # Filter out common non-massgen YAML files
    exclude_patterns = {
        ".pre-commit-config.yaml",
        ".readthedocs.yaml",
        ".github",
        "docker-compose",
        "ansible",
        "kubernetes",
    }

    for config_file in sorted(Path.cwd().glob("*.yaml")):
        # Skip if inside .massgen/ (already covered)
        if ".massgen" in str(config_file):
            continue

        # Skip common non-massgen config files
        file_name = config_file.name.lower()
        if any(pattern in file_name for pattern in exclude_patterns):
            continue

        display_name = config_file.name
        configs["Current Directory"].append((display_name, config_file))

    # 4. Package examples (massgen/configs/)
    try:
        from importlib.resources import files

        configs_root = files("massgen") / "configs"

        # Organize by subdirectory
        for config_file in sorted(configs_root.rglob("*.yaml")):
            # Get relative path from configs root
            rel_path = str(config_file).replace(str(configs_root) + "/", "")
            # Skip README and docs
            if "README" in rel_path or "BACKEND_CONFIGURATION" in rel_path:
                continue
            # Use relative path as display name
            display_name = rel_path.replace(".yaml", "")
            configs["Package Examples"].append((display_name, Path(str(config_file))))

    except Exception as e:
        logger.warning(f"Could not load package examples: {e}")

    # Remove empty categories
    configs = {k: v for k, v in configs.items() if v}

    return configs


def interactive_config_selector() -> str | None:
    """Interactively select a configuration file.

    Shows user/project/current directory configs directly in a flat list.
    Package examples are shown hierarchically (category → config).

    Returns:
        Path to selected config file, or None if cancelled
    """
    # Create console instance for rich output
    selector_console = Console()

    # Discover all available configs
    configs = discover_available_configs()

    if not configs:
        selector_console.print(
            "\n[yellow]⚠️  No configurations found![/yellow]",
        )
        selector_console.print("[dim]Create one with: massgen --init[/dim]\n")
        return None

    # Create a summary table showing what's available
    summary_table = Table(
        show_header=True,
        header_style="bold bright_white",
        border_style="bright_black",
        box=None,
        padding=(0, 1),
        width=88,
    )
    summary_table.add_column("Category", style="bright_cyan", no_wrap=True, width=25)
    summary_table.add_column("Count", justify="center", style="bright_yellow", width=10)
    summary_table.add_column("Location", style="dim")

    # Build summary and choices
    choices = []

    # Build summary table (overview only - no duplication)
    # User configs
    if "User Configs" in configs and configs["User Configs"]:
        summary_table.add_row(
            "👤 Your Configs",
            str(len(configs["User Configs"])),
            "~/.config/massgen/agents/",
        )
        choices.append(questionary.Separator("\n─────────────────────────────────"))
        for display_name, path in configs["User Configs"]:
            choices.append(
                questionary.Choice(
                    title=f"  👤  {display_name}",
                    value=str(path),
                ),
            )

    # Project configs
    if "Project Configs" in configs and configs["Project Configs"]:
        summary_table.add_row(
            "📁 Project Configs",
            str(len(configs["Project Configs"])),
            ".massgen/",
        )
        if choices:
            choices.append(questionary.Separator("\n─────────────────────────────────"))
        else:
            choices.append(questionary.Separator("\n─────────────────────────────────"))
        for display_name, path in configs["Project Configs"]:
            choices.append(
                questionary.Choice(
                    title=f"  📁  {display_name}",
                    value=str(path),
                ),
            )

    # Current directory configs
    if "Current Directory" in configs and configs["Current Directory"]:
        summary_table.add_row(
            "📂 Current Directory",
            str(len(configs["Current Directory"])),
            f"*.yaml in {Path.cwd().name}/",
        )
        if choices:
            choices.append(questionary.Separator("\n─────────────────────────────────"))
        else:
            choices.append(questionary.Separator("\n─────────────────────────────────"))
        for display_name, path in configs["Current Directory"]:
            choices.append(
                questionary.Choice(
                    title=f"  📂  {display_name}",
                    value=str(path),
                ),
            )

    # Package examples
    if "Package Examples" in configs and configs["Package Examples"]:
        summary_table.add_row(
            "📦 Package Examples",
            str(len(configs["Package Examples"])),
            "Built-in examples (hierarchical browser)",
        )
        if choices:
            choices.append(questionary.Separator("\n─────────────────────────────────"))
        choices.append(
            questionary.Choice(
                title=f"  📦  Browse {len(configs['Package Examples'])} example configs  →",
                value="__browse_examples__",
            ),
        )

    # Display summary table in a panel
    selector_console.print()
    selector_console.print(
        Panel(
            summary_table,
            title="[bold bright_cyan]🚀 Select a Configuration[/bold bright_cyan]",
            border_style="bright_cyan",
            padding=(0, 1),
            width=90,
        ),
    )

    # Add cancel option
    choices.append(questionary.Separator("\n─────────────────────────────────"))
    choices.append(questionary.Choice(title="  ❌  Cancel", value="__cancel__"))

    # Show the selector
    selector_console.print()
    selected = questionary.select(
        "Select a configuration:",
        choices=choices,
        use_shortcuts=True,
        use_arrow_keys=True,
        style=MASSGEN_QUESTIONARY_STYLE,
        pointer="▸",
    ).ask()

    if selected is None or selected == "__cancel__":
        selector_console.print("\n[yellow]⚠️  Selection cancelled[/yellow]\n")
        return None

    # If user wants to browse package examples, show hierarchical navigation
    if selected == "__browse_examples__":
        return _select_package_example(configs["Package Examples"], selector_console)

    # Otherwise, return the selected config path
    selector_console.print(
        f"\n[bold green]✓ Selected:[/bold green] [cyan]{selected}[/cyan]\n",
    )
    return selected


def _select_package_example(
    examples: list[tuple[str, Path]],
    console: Console,
) -> str | None:
    """Show hierarchical navigation for package examples.

    Args:
        examples: List of (display_name, path) tuples
        console: Rich console for output

    Returns:
        Path to selected config, or None if cancelled/back
    """
    # Organize examples by category (first directory in path)
    categories = {}
    for display_name, path in examples:
        # Extract category from display name (e.g., "basic/multi/config" -> "basic")
        parts = display_name.split("/")
        category = parts[0] if len(parts) > 1 else "other"

        if category not in categories:
            categories[category] = []
        categories[category].append((display_name, path))

    # Emoji mapping for categories
    category_emojis = {
        "basic": "🎯",
        "tools": "🛠️",
        "providers": "🌐",
        "configs": "⚙️",
        "other": "📋",
    }

    # Create category summary table
    category_table = Table(
        show_header=True,
        header_style="bold bright_white",
        border_style="bright_black",
        box=None,
        padding=(0, 1),
        width=88,
    )
    category_table.add_column("Category", style="bright_cyan", no_wrap=True, width=20)
    category_table.add_column(
        "Count",
        justify="center",
        style="bright_yellow",
        width=10,
    )
    category_table.add_column("Description", style="dim")

    # Category descriptions
    category_descriptions = {
        "basic": "Simple configurations for getting started",
        "tools": "Configs demonstrating tool integrations",
        "providers": "Provider-specific example configs",
        "configs": "Advanced configuration examples",
        "other": "Miscellaneous configurations",
    }

    # Build category table and choices
    category_choices = []
    for category in sorted(categories.keys()):
        count = len(categories[category])
        emoji = category_emojis.get(category, "📁")
        description = category_descriptions.get(category, "Example configurations")

        category_table.add_row(
            f"{emoji} {category.title()}",
            str(count),
            description,
        )

        category_choices.append(
            questionary.Choice(
                title=f"  {emoji}  {category.title()}  ({count} config{'s' if count != 1 else ''})",
                value=category,
            ),
        )

    # Display category summary in a panel
    console.print()
    console.print(
        Panel(
            category_table,
            title="[bold bright_yellow]📦 Package Examples - Select Category[/bold bright_yellow]",
            border_style="bright_yellow",
            padding=(0, 1),
            width=90,
        ),
    )

    # Add back option
    category_choices.append(
        questionary.Separator("\n─────────────────────────────────"),
    )
    category_choices.append(
        questionary.Choice(title="  ← Back to main menu", value="__back__"),
    )

    # Step 1: Select category
    console.print()
    selected_category = questionary.select(
        "Select a category:",
        choices=category_choices,
        use_shortcuts=True,
        use_arrow_keys=True,
        style=MASSGEN_QUESTIONARY_STYLE,
        pointer="▸",
    ).ask()

    if selected_category is None or selected_category == "__cancel__":
        console.print("\n[yellow]⚠️  Selection cancelled[/yellow]\n")
        return None

    if selected_category == "__back__":
        # Go back to main selector
        return interactive_config_selector()

    # Create configs table
    emoji = category_emojis.get(selected_category, "📁")
    configs_table = Table(
        show_header=True,
        header_style="bold bright_white",
        border_style="bright_black",
        box=None,
        padding=(0, 1),
        width=88,
    )
    configs_table.add_column("#", style="dim", width=5, justify="right")
    configs_table.add_column("Configuration", style="bright_cyan")

    # Build config choices and table
    config_choices = []
    for idx, (display_name, path) in enumerate(
        sorted(categories[selected_category]),
        1,
    ):
        # Show relative path within category
        short_name = display_name.replace(f"{selected_category}/", "")
        configs_table.add_row(str(idx), short_name)
        config_choices.append(
            questionary.Choice(
                title=f"  {idx:2d}. {short_name}",
                value=str(path),
            ),
        )

    # Display configs in a panel
    console.print()
    console.print(
        Panel(
            configs_table,
            title=f"[bold bright_green]{emoji} {selected_category.title()} Configurations[/bold bright_green]",
            border_style="bright_green",
            padding=(0, 1),
            width=90,
        ),
    )

    # Add back option
    config_choices.append(questionary.Separator("\n─────────────────────────────────"))
    config_choices.append(
        questionary.Choice(title="  ← Back to categories", value="__back__"),
    )

    # Step 2: Select config
    # For large lists: disable shortcuts (max 36) and enable search filter for better UX
    # Note: When search filter is enabled, j/k keys must be disabled (they conflict with search)
    use_shortcuts = len(config_choices) <= 36
    use_search_filter = len(config_choices) > 36
    console.print()
    selected_config = questionary.select(
        "Select a configuration:",
        choices=config_choices,
        use_shortcuts=use_shortcuts,
        use_arrow_keys=True,
        use_search_filter=use_search_filter,
        use_jk_keys=not use_search_filter,
        style=MASSGEN_QUESTIONARY_STYLE,
        pointer="▸",
    ).ask()

    if selected_config is None or selected_config == "__cancel__":
        console.print("\n[yellow]⚠️  Selection cancelled[/yellow]\n")
        return None

    if selected_config == "__back__":
        # Recursively call to go back to category selection
        return _select_package_example(examples, console)

    # Return the selected config path
    console.print(
        f"\n[bold green]✓ Selected:[/bold green] [cyan]{selected_config}[/cyan]\n",
    )
    return selected_config


def show_example_prompts() -> str | None:
    """Show example prompts that work with default quickstart config.

    These prompts work out-of-the-box with code execution, multimodal tools,
    and web scraping capabilities.

    Returns:
        Selected prompt text, or None if user skips/cancels
    """
    import questionary
    from questionary import Style

    example_prompts = [
        "Create a vibrant, interactive website about famous AI researchers using HTML, CSS, and JavaScript",
        "Write a Python script to analyze data from a CSV file, create visualizations, and generate a summary report",
        "Research recent developments in AI multi-agent systems by searching the web and summarize key trends with citations",
        "Generate 3 different logo concepts for a tech startup, then help me choose the best one based on design principles",
        "Create a lesson plan for teaching Python programming to beginners, with structured activities and code examples",
        "Build a web scraper to collect pricing data from e-commerce sites and analyze market trends",
        "Generate a presentation-ready infographic about climate change using text-to-image generation",
        "Research, plan, and write a technical blog post about multi-agent systems",
    ]

    # Custom style with highlighted autocomplete
    custom_style = Style(
        [
            ("answer", "#4A90E2 bold"),
            (
                "completion-menu.completion",
                "bg:#808080 fg:#ffffff",
            ),  # Dimmed gray background
            (
                "completion-menu.completion.current",
                "bg:#4A90E2 fg:#ffffff",
            ),  # Highlight current selection
        ],
    )

    try:
        print()
        # Show dimmed examples below the prompt
        print(
            "\033[2m" + "Example prompts (start typing to see autocomplete):" + "\033[0m",
        )
        for prompt in example_prompts[:3]:  # Show first 3 as hints
            print(
                "\033[2m" + f"  • {prompt[:70]}{'...' if len(prompt) > 70 else ''}" + "\033[0m",
            )
        print()

        choice = questionary.autocomplete(
            "Enter your prompt:",
            choices=example_prompts,
            style=custom_style,
            match_middle=True,
        ).ask()

        return choice if choice else None
    except (KeyboardInterrupt, EOFError):
        return None
