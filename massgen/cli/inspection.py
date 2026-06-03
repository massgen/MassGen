#!/usr/bin/env python3
"""Session and turn log inspection helpers.

Part of the massgen.cli package (extracted from the legacy monolithic cli.py).
"""

import json
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
)

if TYPE_CHECKING:
    pass

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# --- cross-module references within the cli package ---
from ._constants import BRIGHT_YELLOW, RESET, SESSION_STORAGE


def _list_all_turns(
    session_id: str | None,
    current_turn: int,
    console: Console,
) -> None:
    """List all turns in the current session."""
    if not session_id:
        console.print("[yellow]No active session. Complete a turn first.[/yellow]")
        return

    session_dir = Path(SESSION_STORAGE) / session_id

    if not session_dir.exists():
        console.print("[yellow]No session data available.[/yellow]")
        return

    if current_turn == 0:
        console.print("[yellow]No turns completed yet.[/yellow]")
        return

    table = Table(title=f"Session: {session_id}")
    table.add_column("Turn", style="cyan", width=6)
    table.add_column("Task", style="white")
    table.add_column("Winner", style="green", width=15)

    for turn_num in range(1, current_turn + 1):
        turn_dir = session_dir / f"turn_{turn_num}"
        metadata_file = turn_dir / "metadata.json"

        if metadata_file.exists():
            metadata = json.loads(metadata_file.read_text())
            task = metadata.get("task", "Unknown")
            # Truncate long tasks
            if len(task) > 60:
                task = task[:57] + "..."
            winner = metadata.get("winning_agent", "Unknown")
            table.add_row(str(turn_num), task, winner)

    console.print(table)
    console.print("\n[dim]Use /inspect <turn_number> to view details[/dim]")


def _find_log_dir_for_session(session_id: str, turn_number: int) -> Path | None:
    """Find the log directory for a given session and turn.

    Searches through log directories to find one that matches the session_id
    by checking execution_metadata.yaml files. Returns the attempt directory
    which contains the actual log data (agent_outputs, coordination_table, etc.).
    """
    logs_base = Path(".massgen/massgen_logs")
    if not logs_base.exists():
        return None

    # Search through log directories for matching session_id
    for log_dir in sorted(logs_base.iterdir(), reverse=True):  # Most recent first
        if not log_dir.is_dir() or not log_dir.name.startswith("log_"):
            continue

        turn_dir = log_dir / f"turn_{turn_number}"
        if not turn_dir.exists():
            continue

        # Look for attempt directories (e.g., attempt_1, attempt_2)
        # The actual log data is stored inside attempt directories
        for attempt_dir in sorted(turn_dir.iterdir(), reverse=True):
            if not attempt_dir.is_dir() or not attempt_dir.name.startswith("attempt_"):
                continue

            metadata_file = attempt_dir / "execution_metadata.yaml"
            if metadata_file.exists():
                try:
                    metadata = yaml.safe_load(metadata_file.read_text())
                    cli_args = metadata.get("cli_args", {})
                    if cli_args.get("session_id") == session_id:
                        return attempt_dir
                except Exception:
                    continue

    return None


def _show_turn_inspection(
    session_id: str,
    turn_number: int,
    agents: dict[str, Any],
) -> None:
    """Show inspection menu for a specific turn's outputs.

    Uses data from both session storage and log directories to provide
    full inspection capabilities including agent outputs, system status,
    and coordination events.
    """
    console = Console()
    session_dir = Path(SESSION_STORAGE) / session_id
    turn_dir = session_dir / f"turn_{turn_number}"

    if not turn_dir.exists():
        print(f"{BRIGHT_YELLOW}No data for turn {turn_number}.{RESET}", flush=True)
        return

    # Find the corresponding log directory for richer data
    log_turn_dir = _find_log_dir_for_session(session_id, turn_number)

    # Load metadata from session
    metadata_file = turn_dir / "metadata.json"
    metadata = {}
    if metadata_file.exists():
        metadata = json.loads(metadata_file.read_text())

    # Load answer from session
    answer_file = turn_dir / "answer.txt"
    answer_content = ""
    if answer_file.exists():
        answer_content = answer_file.read_text()

    # Check workspace from session
    workspace_dir = turn_dir / "workspace"
    workspace_files = []
    if workspace_dir.exists():
        workspace_files = list(workspace_dir.rglob("*"))
        workspace_files = [f for f in workspace_files if f.is_file()]

    # Check for log data
    agent_outputs_dir = log_turn_dir / "agent_outputs" if log_turn_dir else None
    system_status_file = agent_outputs_dir / "system_status.txt" if agent_outputs_dir else None
    log_turn_dir / "coordination_events.json" if log_turn_dir else None
    coordination_table_file = log_turn_dir / "coordination_table.txt" if log_turn_dir else None
    status_json_file = log_turn_dir / "status.json" if log_turn_dir else None

    # Get available agent output files
    agent_files = {}
    if agent_outputs_dir and agent_outputs_dir.exists():
        for f in agent_outputs_dir.glob("*.txt"):
            if f.name.startswith("agent_") and not f.name.startswith(
                "final_presentation",
            ):
                agent_id = f.stem.replace("agent_", "")
                agent_files[agent_id] = f

    # Get winning agent for display
    winning_agent = metadata.get("winning_agent", "winner")

    # Interactive menu - matches style of RichTerminalDisplay.show_agent_selector()
    while True:
        # Build menu content inside a panel like the original agent selector
        menu_lines = []

        # Intro description (matches original agent selector style)
        menu_lines.append(
            "This is a system inspection interface for diving into the multi-agent collaboration "
            "behind the scenes in MassGen. It lets you examine each agent's original output and "
            "compare it to the final MassGen answer in terms of quality. You can explore the "
            "detailed communication, collaboration, voting, and decision-making process.",
        )
        menu_lines.append("")

        # Turn metadata inline
        task_preview = metadata.get("task", "N/A")
        if len(task_preview) > 60:
            task_preview = task_preview[:57] + "..."
        menu_lines.append(
            f"[dim]Turn {turn_number} | Task: {task_preview} | Winner: {winning_agent}[/dim]",
        )
        menu_lines.append("")

        menu_lines.append("[bold green]🎮 Select an option to inspect:[/bold green]")

        # Agent outputs (from logs) - numbered options first
        if agent_files:
            for i, agent_id in enumerate(sorted(agent_files.keys()), 1):
                menu_lines.append(
                    f"  [yellow]{i}:[/yellow] Inspect the original answer and working log of agent {agent_id}",
                )

        # System status (s) - orchestrator log
        if system_status_file and system_status_file.exists():
            menu_lines.append(
                "  [yellow]s:[/yellow] Inspect the orchestrator working log including the voting process",
            )

        # Coordination table (r)
        if coordination_table_file and coordination_table_file.exists():
            menu_lines.append(
                "  [yellow]r:[/yellow] Display coordination table to see the full history of agent interactions and decisions",
            )

        # Cost breakdown (c)
        if status_json_file and status_json_file.exists():
            menu_lines.append(
                "  [yellow]c:[/yellow] Show cost breakdown and token usage",
            )

        # Final answer (f) - with winning agent info if available
        menu_lines.append(
            f"  [yellow]f:[/yellow] Show final presentation from Selected Agent ({winning_agent})",
        )

        # Workspace files (w/o)
        if workspace_files:
            menu_lines.append(
                f"  [yellow]w:[/yellow] List workspace files ({len(workspace_files)} files)",
            )
            menu_lines.append("  [yellow]o:[/yellow] Open workspace in file browser")

        # Quit (q)
        menu_lines.append("  [yellow]q:[/yellow] Quit Inspection")
        menu_lines.append("")

        # Display in a panel matching the original agent selector style
        console.print(
            Panel(
                "\n".join(menu_lines),
                title="[bold]Agent Selector[/bold]",
                border_style="cyan",
            ),
        )

        try:
            choice = input("Enter your choice: ").strip().lower()

            # Check for agent number selection
            if choice.isdigit():
                idx = int(choice)
                agent_ids = sorted(agent_files.keys())
                if 1 <= idx <= len(agent_ids):
                    agent_id = agent_ids[idx - 1]
                    agent_file = agent_files[agent_id]
                    content = agent_file.read_text()
                    # Escape Rich markup in content
                    if "[" in content:
                        content = content.replace("[", r"\[")
                    console.print("\n" + "=" * 80)
                    console.print(
                        Panel(
                            content,
                            title=f"[bold]{agent_id} Output[/bold]",
                            border_style="cyan",
                        ),
                    )
                    input("\nPress Enter to continue...")
                    console.print("=" * 80 + "\n")
                else:
                    console.print("[red]Invalid agent number.[/red]")
                continue

            if choice == "f":
                if answer_content:
                    console.print("\n" + "=" * 80)
                    # Escape Rich markup
                    display_content = answer_content
                    if "[" in display_content:
                        display_content = display_content.replace("[", r"\[")
                    console.print(
                        Panel(
                            display_content,
                            title=f"[bold]Final Answer (Turn {turn_number})[/bold]",
                            border_style="green",
                        ),
                    )
                    input("\nPress Enter to continue...")
                    console.print("=" * 80 + "\n")
                else:
                    console.print("[yellow]No answer content available.[/yellow]")

            elif choice == "s" and system_status_file and system_status_file.exists():
                content = system_status_file.read_text()
                if "[" in content:
                    content = content.replace("[", r"\[")
                console.print("\n" + "=" * 80)
                console.print(
                    Panel(
                        content,
                        title="[bold]System Status Log[/bold]",
                        border_style="magenta",
                    ),
                )
                input("\nPress Enter to continue...")
                console.print("=" * 80 + "\n")

            elif choice == "r" and coordination_table_file and coordination_table_file.exists():
                content = coordination_table_file.read_text()
                if "[" in content:
                    content = content.replace("[", r"\[")
                console.print("\n" + "=" * 80)
                console.print(
                    Panel(
                        content,
                        title="[bold]Coordination Table[/bold]",
                        border_style="yellow",
                    ),
                )
                input("\nPress Enter to continue...")
                console.print("=" * 80 + "\n")

            elif choice == "c" and status_json_file and status_json_file.exists():
                from rich.table import Table

                status_data = json.loads(status_json_file.read_text())
                console.print("\n" + "=" * 80)

                # Create cost table
                table = Table(
                    title="💰 Cost Breakdown & Token Usage",
                    show_header=True,
                    header_style="bold cyan",
                    border_style="cyan",
                )
                table.add_column("Agent", style="cyan", no_wrap=True)
                table.add_column("Input", justify="right", style="green")
                table.add_column("Output", justify="right", style="blue")
                table.add_column("Reasoning", justify="right", style="magenta")
                table.add_column("Cached", justify="right", style="yellow")
                table.add_column("Est. Cost", justify="right", style="bold green")

                # Get per-agent data
                agents_data = status_data.get("agents", {})
                for agent_id in sorted(agents_data.keys()):
                    agent_info = agents_data[agent_id]
                    tu = agent_info.get("token_usage", {})
                    if tu:
                        cost = tu.get("estimated_cost", 0)
                        if cost < 0.01:
                            cost_str = f"${cost:.4f}"
                        elif cost < 1.0:
                            cost_str = f"${cost:.3f}"
                        else:
                            cost_str = f"${cost:.2f}"
                        table.add_row(
                            agent_id,
                            f"{tu.get('input_tokens', 0):,}",
                            f"{tu.get('output_tokens', 0):,}",
                            (f"{tu.get('reasoning_tokens', 0):,}" if tu.get("reasoning_tokens", 0) > 0 else "-"),
                            (f"{tu.get('cached_input_tokens', 0):,}" if tu.get("cached_input_tokens", 0) > 0 else "-"),
                            cost_str,
                        )

                # Add totals row
                costs_data = status_data.get("costs", {})
                if costs_data and len(agents_data) > 1:
                    total_cost = costs_data.get("total_estimated_cost", 0)
                    if total_cost < 0.01:
                        total_cost_str = f"${total_cost:.4f}"
                    elif total_cost < 1.0:
                        total_cost_str = f"${total_cost:.3f}"
                    else:
                        total_cost_str = f"${total_cost:.2f}"
                    table.add_row(
                        "TOTAL",
                        f"{costs_data.get('total_input_tokens', 0):,}",
                        f"{costs_data.get('total_output_tokens', 0):,}",
                        "-",
                        "-",
                        total_cost_str,
                        style="bold",
                    )

                console.print(table)
                input("\nPress Enter to continue...")
                console.print("=" * 80 + "\n")

            elif choice == "w" and workspace_files:
                console.print("\n[bold]Workspace Files:[/bold]")
                for f in workspace_files[:20]:  # Limit to 20 files
                    rel_path = f.relative_to(workspace_dir)
                    console.print(f"  {rel_path}")
                if len(workspace_files) > 20:
                    console.print(f"  ... and {len(workspace_files) - 20} more files")
                console.print(f"\n[dim]Workspace path: {workspace_dir}[/dim]")
                input("\nPress Enter to continue...")

            elif choice == "o" and workspace_files:
                import platform
                import subprocess

                try:
                    system = platform.system()
                    if system == "Darwin":  # macOS
                        subprocess.run(["open", str(workspace_dir)])
                    elif system == "Windows":
                        subprocess.run(["explorer", str(workspace_dir)])
                    else:  # Linux
                        subprocess.run(["xdg-open", str(workspace_dir)])
                    console.print(f"[green]Opened workspace: {workspace_dir}[/green]")
                except Exception as e:
                    console.print(f"[red]Error opening workspace: {e}[/red]")

            elif choice == "q":
                break

            else:
                console.print("[red]Invalid choice. Please try again.[/red]")

        except KeyboardInterrupt:
            break

    console.print()
