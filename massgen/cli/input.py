#!/usr/bin/env python3
"""Terminal input helpers: prompt sessions, multiline input, and context-path prompts.

Part of the massgen.cli package (extracted from the legacy monolithic cli.py).
"""

import asyncio
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
)

if TYPE_CHECKING:
    pass

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.patch_stdout import patch_stdout

from ..logger_config import is_debug_mode as _is_debug_mode
from ..logger_config import logger
from ..path_handling import AtPathCompleter

# --- cross-module references within the cli package ---
from ._constants import BRIGHT_CYAN, BRIGHT_GREEN, BRIGHT_RED, BRIGHT_YELLOW, RESET

# Cached prompt_toolkit session (lazily created by _get_prompt_session).
_prompt_session: PromptSession | None = None


def _restore_terminal_for_input() -> None:
    """Restore terminal settings to a known good state for input().

    This is needed after Rich display cancellation, which can leave
    the terminal in a non-canonical mode.
    """
    try:
        import sys

        if sys.stdin.isatty():
            try:
                import termios

                # Get current settings
                current = termios.tcgetattr(sys.stdin.fileno())
                # Enable echo and canonical mode (required for input())
                current[3] = current[3] | termios.ECHO | termios.ICANON
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, current)
                # Flush any pending input
                termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
            except ImportError:
                pass  # termios not available (Windows)
    except Exception:
        pass  # Best effort


def _get_prompt_session() -> PromptSession:
    """Get or create the PromptSession instance with AtPathCompleter."""
    global _prompt_session
    if _prompt_session is None:
        _prompt_session = PromptSession(
            completer=AtPathCompleter(),
            complete_while_typing=True,
        )
    return _prompt_session


async def read_multiline_input_async(
    prompt: str,
    enable_path_completion: bool = True,
    use_ansi_prompt: bool = False,
) -> str:
    """Async version of read_multiline_input for use in async contexts.

    Uses prompt_toolkit's async prompt_async() method which works correctly
    inside an already-running event loop.

    Args:
        prompt: The prompt string (can contain ANSI codes if use_ansi_prompt=True)
        enable_path_completion: Whether to enable @path autocomplete
        use_ansi_prompt: If True, interpret prompt as ANSI-formatted text
    """
    try:
        session = _get_prompt_session()
        # Wrap prompt in ANSI() if it contains escape codes
        formatted_prompt = ANSI(prompt) if use_ansi_prompt else prompt
        with patch_stdout():
            if not enable_path_completion:
                first_line = (await session.prompt_async(formatted_prompt, completer=None)).strip()
            else:
                first_line = (await session.prompt_async(formatted_prompt)).strip()
    except (EOFError, KeyboardInterrupt):
        raise
    except Exception as e:
        if _is_debug_mode():
            logger.debug(f"prompt_toolkit async failed; falling back to input(): {e}")
        # Fallback to basic input - run in executor to not block
        loop = asyncio.get_running_loop()
        # Strip ANSI codes for fallback
        plain_prompt = prompt if not use_ansi_prompt else "User: "
        first_line = await loop.run_in_executor(
            None,
            lambda: input(plain_prompt).strip(),
        )

    # Check for multi-line delimiters
    if first_line.startswith('"""'):
        delimiter = '"""'
        content = first_line[3:]
    elif first_line.startswith("'''"):
        delimiter = "'''"
        content = first_line[3:]
    else:
        return first_line

    # Check if closing delimiter is on the same line
    if delimiter in content:
        return content[: content.index(delimiter)]

    # Collect multi-line input
    lines = [content] if content else []
    loop = asyncio.get_running_loop()
    while True:
        try:
            line = await loop.run_in_executor(None, input)
        except (EOFError, KeyboardInterrupt):
            raise
        if delimiter in line:
            final_part = line[: line.index(delimiter)]
            if final_part:
                lines.append(final_part)
            break
        lines.append(line)

    return "\n".join(lines)


def read_multiline_input(prompt: str, enable_path_completion: bool = True) -> str:
    """Read user input with support for multi-line input and @path completion.

    Uses prompt_toolkit PromptSession to provide inline file completion when user types @.
    If input starts with ''' or \""", continues reading until closing quotes.
    Otherwise returns single line input.

    Note: This synchronous version will fallback to basic input() if called from
    within an async context. Use read_multiline_input_async() instead in async code.

    Args:
        prompt: The prompt to display to the user
        enable_path_completion: If True, enable @path autocomplete (default True)

    Returns:
        The complete user input (single or multi-line)
    """
    # Check if we're in an async context
    try:
        import asyncio

        asyncio.get_running_loop()
        # We're in an async context - can't use sync prompt
        # Fallback to basic input
        first_line = input(prompt).strip()
    except RuntimeError:
        # No running loop - safe to use sync prompt
        try:
            session = _get_prompt_session()
            if not enable_path_completion:
                first_line = session.prompt(prompt, completer=None).strip()
            else:
                first_line = session.prompt(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            raise
        except Exception as e:
            import sys

            print(f"\n[DEBUG] prompt_toolkit failed: {e}", file=sys.stderr)
            first_line = input(prompt).strip()

    # Check for multi-line delimiters
    if first_line.startswith('"""'):
        delimiter = '"""'
        content = first_line[3:]  # Remove opening delimiter
    elif first_line.startswith("'''"):
        delimiter = "'''"
        content = first_line[3:]  # Remove opening delimiter
    else:
        # Single line input
        return first_line

    # Check if closing delimiter is on the same line
    if delimiter in content:
        return content[: content.index(delimiter)]

    # Multi-line mode: read until closing delimiter
    lines = [content] if content else []
    print(
        f"   {BRIGHT_CYAN}(Multi-line mode: enter {delimiter} on a new line to finish){RESET}",
        flush=True,
    )

    while True:
        try:
            line = input("   ")
            if delimiter in line:
                # Found closing delimiter
                before_delimiter = line[: line.index(delimiter)]
                if before_delimiter:
                    lines.append(before_delimiter)
                break
            lines.append(line)
        except EOFError:
            # Handle Ctrl+D
            break

    return "\n".join(lines)


def prompt_for_context_paths(
    original_config: dict[str, Any],
    orchestrator_cfg: dict[str, Any],
) -> bool:
    """Prompt user to add context paths in interactive mode.

    Returns True if config was modified, False otherwise.
    """
    # Check if filesystem is enabled (at least one agent has cwd)
    agent_entries = [original_config["agent"]] if "agent" in original_config else original_config.get("agents", [])
    has_filesystem = any("cwd" in agent.get("backend", {}) for agent in agent_entries)

    if not has_filesystem:
        return False

    # Skip prompting if context_paths was explicitly configured (even if empty)
    # This means user already made a decision during config creation (e.g., quickstart)
    if "context_paths" in orchestrator_cfg:
        return False

    # Show current context paths
    existing_paths = orchestrator_cfg.get("context_paths", [])
    cwd = Path.cwd()

    # Use Rich for better display
    from rich.console import Console as RichConsole
    from rich.panel import Panel as RichPanel

    rich_console = RichConsole()

    # Build context paths display
    context_content = []
    if existing_paths:
        for path_config in existing_paths:
            path = path_config.get("path") if isinstance(path_config, dict) else path_config
            permission = path_config.get("permission", "read") if isinstance(path_config, dict) else "read"
            context_content.append(
                f"  [green]✓[/green] {path} [dim]({permission})[/dim]",
            )
    else:
        context_content.append("  [yellow]No context paths configured[/yellow]")

    context_panel = RichPanel(
        "\n".join(context_content),
        title="[bold bright_cyan]📂 Context Paths[/bold bright_cyan]",
        border_style="cyan",
        padding=(0, 2),
        width=80,
    )
    rich_console.print(context_panel)
    print()

    # Check if CWD is already in context paths
    cwd_str = str(cwd)
    cwd_already_added = any((path_config.get("path") if isinstance(path_config, dict) else path_config) == cwd_str for path_config in existing_paths)

    if not cwd_already_added:
        # Create prompt panel
        prompt_content = [
            "[bold cyan]Add current directory as context path?[/bold cyan]",
            f"  [yellow]{cwd}[/yellow]",
            "",
            "  [dim]Context paths give agents access to your project files.[/dim]",
            "  [dim]• Read-only during coordination (prevents conflicts)[/dim]",
            "  [dim]• Write permission for final agent to save results[/dim]",
            "",
            "  [dim]Options:[/dim]",
            "  [green]Y[/green] → Add with write permission (default)",
            "  [cyan]P[/cyan] → Add with protected paths (e.g., .env, secrets)",
            "  [yellow]N[/yellow] → Skip",
            "  [blue]C[/blue] → Add custom path",
        ]
        prompt_panel = RichPanel(
            "\n".join(prompt_content),
            border_style="cyan",
            padding=(1, 2),
            width=80,
        )
        rich_console.print(prompt_panel)
        print()
        try:
            response = input(f"   {BRIGHT_CYAN}Your choice [Y/P/N/C]:{RESET} ").strip().lower()

            if response in ["y", "yes", ""]:
                # Add CWD with write permission
                if "context_paths" not in orchestrator_cfg:
                    orchestrator_cfg["context_paths"] = []
                orchestrator_cfg["context_paths"].append(
                    {"path": cwd_str, "permission": "write"},
                )
                print(f"   {BRIGHT_GREEN}✅ Added: {cwd} (write){RESET}", flush=True)
                return True
            elif response in ["p", "protected"]:
                # Add CWD with write permission and protected paths
                protected_paths = []
                print(
                    f"\n   {BRIGHT_CYAN}Enter protected paths (one per line, empty to finish):{RESET}",
                    flush=True,
                )
                print(
                    f"   {BRIGHT_YELLOW}Tip: Protected paths are relative to {cwd}{RESET}",
                    flush=True,
                )
                while True:
                    protected_input = input(f"   {BRIGHT_CYAN}→{RESET} ").strip()
                    if not protected_input:
                        break
                    protected_paths.append(protected_input)
                    print(
                        f"     {BRIGHT_GREEN}✓ Added: {protected_input}{RESET}",
                        flush=True,
                    )

                if "context_paths" not in orchestrator_cfg:
                    orchestrator_cfg["context_paths"] = []

                context_config = {"path": cwd_str, "permission": "write"}
                if protected_paths:
                    context_config["protected_paths"] = protected_paths

                orchestrator_cfg["context_paths"].append(context_config)
                print(
                    f"\n   {BRIGHT_GREEN}✅ Added: {cwd} (write) with {len(protected_paths)} protected path(s){RESET}",
                    flush=True,
                )
                return True
            elif response in ["n", "no"]:
                # User explicitly declined
                return False
            elif response in ["c", "custom"]:
                # Loop until valid path or user cancels
                print()
                while True:
                    custom_path = input(
                        f"   {BRIGHT_CYAN}Enter path (absolute or relative):{RESET} ",
                    ).strip()
                    if not custom_path:
                        print(f"   {BRIGHT_YELLOW}⚠️  Cancelled{RESET}", flush=True)
                        return False

                    # Resolve to absolute path
                    abs_path = str(Path(custom_path).resolve())

                    # Check if path exists
                    if not Path(abs_path).exists():
                        print(
                            f"   {BRIGHT_RED}✗ Path does not exist: {abs_path}{RESET}",
                            flush=True,
                        )
                        retry = input(f"   {BRIGHT_CYAN}Try again? [Y/n]:{RESET} ").strip().lower()
                        if retry in ["n", "no"]:
                            return False
                        continue

                    # Valid path (file or directory), ask for permission
                    permission = (
                        input(
                            f"   {BRIGHT_CYAN}Permission [read/write] (default: write):{RESET} ",
                        )
                        .strip()
                        .lower()
                        or "write"
                    )
                    if permission not in ["read", "write"]:
                        permission = "write"

                    # Ask about protected paths if write permission
                    protected_paths = []
                    if permission == "write":
                        add_protected = (
                            input(
                                f"   {BRIGHT_CYAN}Add protected paths? [y/N]:{RESET} ",
                            )
                            .strip()
                            .lower()
                        )
                        if add_protected in ["y", "yes"]:
                            print(
                                f"   {BRIGHT_CYAN}Enter protected paths (one per line, empty to finish):{RESET}",
                                flush=True,
                            )
                            while True:
                                protected_input = input(
                                    f"   {BRIGHT_CYAN}→{RESET} ",
                                ).strip()
                                if not protected_input:
                                    break
                                protected_paths.append(protected_input)
                                print(
                                    f"     {BRIGHT_GREEN}✓ Added: {protected_input}{RESET}",
                                    flush=True,
                                )

                    if "context_paths" not in orchestrator_cfg:
                        orchestrator_cfg["context_paths"] = []

                    context_config = {"path": abs_path, "permission": permission}
                    if protected_paths:
                        context_config["protected_paths"] = protected_paths

                    orchestrator_cfg["context_paths"].append(context_config)
                    if protected_paths:
                        print(
                            f"   {BRIGHT_GREEN}✅ Added: {abs_path} ({permission}) with {len(protected_paths)} protected path(s){RESET}",
                            flush=True,
                        )
                    else:
                        print(
                            f"   {BRIGHT_GREEN}✅ Added: {abs_path} ({permission}){RESET}",
                            flush=True,
                        )
                    return True
            else:
                # Invalid response - clarify options
                print(
                    f"\n   {BRIGHT_RED}✗ Invalid option: '{response}'{RESET}",
                    flush=True,
                )
                print(
                    f"   {BRIGHT_YELLOW}Please choose: Y (yes), P (protected), N (no), or C (custom){RESET}",
                    flush=True,
                )
                return False
        except (KeyboardInterrupt, EOFError):
            print()  # New line after Ctrl+C
            return False

    return False
