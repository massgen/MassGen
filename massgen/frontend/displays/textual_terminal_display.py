# -*- coding: utf-8 -*-
"""
Textual Terminal Display for MassGen Coordination

A modern terminal UI using Textual with feature parity to RichTerminalDisplay.
"""

import asyncio
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base_display import BaseDisplay

try:
    from textual.app import App, ComposeResult
    from textual.containers import Container, ScrollableContainer, Vertical
    from textual.screen import ModalScreen
    from textual.widgets import Footer, Label, RichLog, Static, TextArea

    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False


# Emoji fallback mapping for terminals without Unicode support
EMOJI_FALLBACKS = {
    "🚀": ">>",  # Launch
    "💡": "(!)",  # Question
    "🤖": "[A]",  # Agent
    "✅": "[✓]",  # Success
    "❌": "[X]",  # Error
    "🔄": "[↻]",  # Processing
    "📊": "[=]",  # Stats
    "🎯": "[>]",  # Target
    "⚡": "[!]",  # Fast
    "🎤": "[M]",  # Presentation
    "🔍": "[?]",  # Search/Evaluation
    "⚠️": "[!]",  # Warning
    "📋": "[□]",  # Summary
    "🧠": "[B]",  # Brain/Reasoning
}


class TextualTerminalDisplay(BaseDisplay):
    """Textual-based terminal display with feature parity to Rich."""

    def __init__(self, agent_ids: List[str], **kwargs: Any):
        super().__init__(agent_ids, **kwargs)

        # Configuration (same pattern as RichTerminalDisplay)
        self.theme = kwargs.get("theme", "dark")
        self.refresh_rate = kwargs.get("refresh_rate", 10)
        self.enable_syntax_highlighting = kwargs.get("enable_syntax_highlighting", True)
        self.show_timestamps = kwargs.get("show_timestamps", True)
        self.enable_flush_output = kwargs.get("enable_flush_output", True)
        self.flush_char_delay = kwargs.get("flush_char_delay", 0.03)
        self.flush_word_delay = kwargs.get("flush_word_delay", 0.08)

        # Buffering
        self.buffer_flush_interval = kwargs.get("buffer_flush_interval", 0.1)
        self._buffers = {agent_id: [] for agent_id in agent_ids}
        self._buffer_lock = threading.Lock()

        # File output
        self.output_dir = None
        self.agent_files = {}
        self.system_status_file = None
        self.final_presentation_file = None

        # Textual app
        self._app = None
        self._ready_event = threading.Event()

        # Display state
        self.question = ""
        self.log_filename = None
        self.restart_reason = None
        self.restart_instructions = None

        # Emoji support detection
        self.emoji_support = self._detect_emoji_support()

        # Terminal type detection
        self.terminal_type = self._detect_terminal_type()
        if "refresh_rate" not in kwargs:
            self.refresh_rate = self._get_adaptive_refresh_rate(self.terminal_type)

    def _detect_emoji_support(self) -> bool:
        """Detect if terminal supports emoji."""
        import locale

        term_program = os.environ.get("TERM_PROGRAM", "")
        if term_program in ["vscode", "iTerm.app", "Apple_Terminal"]:
            return True

        if os.environ.get("WT_SESSION"):
            return True

        try:
            encoding = locale.getpreferredencoding()
            if encoding.lower() in ["utf-8", "utf8"]:
                return True
        except Exception:
            pass

        lang = os.environ.get("LANG", "")
        if "UTF-8" in lang or "utf8" in lang:
            return True

        return False

    def _get_icon(self, emoji: str) -> str:
        """Get emoji or fallback based on terminal support."""
        if self.emoji_support:
            return emoji
        return EMOJI_FALLBACKS.get(emoji, emoji)

    def _detect_terminal_type(self) -> str:
        """Detect terminal type and capabilities."""
        if os.environ.get("TERM_PROGRAM") == "vscode":
            return "vscode"

        if os.environ.get("TERM_PROGRAM") == "iTerm.app":
            return "iterm"

        if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_CLIENT"):
            return "ssh"

        if os.environ.get("WT_SESSION"):
            return "windows_terminal"

        return "unknown"

    def _get_adaptive_refresh_rate(self, terminal_type: str) -> int:
        """Get optimal refresh rate based on terminal."""
        rates = {
            "ssh": 4,
            "vscode": 15,
            "iterm": 20,
            "windows_terminal": 15,
            "unknown": 10,
        }
        return rates.get(terminal_type, 10)

    def _write_to_agent_file(self, agent_id: str, content: str):
        """Write content to agent's output file."""
        if agent_id not in self.agent_files:
            return

        try:
            file_path = self.agent_files[agent_id]
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(content)
                f.flush()
        except Exception:
            pass

    def _write_to_system_file(self, content: str):
        """Write content to system status file."""
        if not self.system_status_file:
            return

        try:
            with open(self.system_status_file, "a", encoding="utf-8") as f:
                if self.show_timestamps:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    f.write(f"[{timestamp}] {content}\n")
                else:
                    f.write(f"{content}\n")
                f.flush()
        except Exception:
            pass

    def _open_in_editor(self, agent_id: str, editor_type: str = "default"):
        """Open agent/system files in an external editor."""
        file_path = self.agent_files.get(agent_id)

        if not file_path:
            if agent_id == "system_status":
                file_path = self.system_status_file
            elif agent_id == "final_presentation":
                file_path = self.final_presentation_file

        if not file_path or not Path(file_path).exists():
            return

        try:
            if editor_type == "vscode":
                subprocess.run(["code", str(file_path)], check=False)
            elif sys.platform == "win32":
                os.startfile(file_path)
            elif sys.platform == "darwin":
                subprocess.run(["open", str(file_path)], check=False)
            else:
                subprocess.run(["xdg-open", str(file_path)], check=False)
        except Exception:
            pass

    def initialize(self, question: str, log_filename: Optional[str] = None):
        """Initialize display with file output."""
        self.question = question
        self.log_filename = log_filename

        # Create output directory
        if log_filename:
            self.output_dir = Path(log_filename).parent
        else:
            self.output_dir = Path("output") / datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Create agent output files
        for agent_id in self.agent_ids:
            file_path = self.output_dir / f"{agent_id}.txt"
            self.agent_files[agent_id] = file_path
            # Initialize file with header
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"=== {agent_id.upper()} OUTPUT LOG ===\n\n")

        # Create system status file
        self.system_status_file = self.output_dir / "system_status.txt"
        with open(self.system_status_file, "w", encoding="utf-8") as f:
            f.write("=== SYSTEM STATUS LOG ===\n")
            f.write(f"Question: {question}\n\n")

        # Create final presentation file
        self.final_presentation_file = self.output_dir / "final_presentation.txt"

        # Create Textual app
        if TEXTUAL_AVAILABLE:
            self._app = TextualApp(
                self,
                question,
                refresh_rate=self.refresh_rate,
                buffers=self._buffers,
                buffer_lock=self._buffer_lock,
                buffer_flush_interval=self.buffer_flush_interval,
            )
            self._ready_event.set()

    def update_agent_content(self, agent_id: str, content: str, content_type: str = "thinking"):
        """Update agent content with appropriate formatting.

        Args:
            agent_id: Agent identifier
            content: Content to display
            content_type: Type of content - "thinking", "tool", "status", "presentation"
        """
        # Store in memory for retrieval
        self.agent_outputs[agent_id].append(content)

        # Write to file immediately
        self._write_to_agent_file(agent_id, content)

        with self._buffer_lock:
            self._buffers[agent_id].append(
                {
                    "content": content,
                    "type": content_type,
                    "timestamp": datetime.now(),
                },
            )

    def update_agent_status(self, agent_id: str, status: str):
        """Update status for a specific agent."""
        self.agent_status[agent_id] = status

        # Update status in app if running
        if self._app:
            self._app.call_from_thread(self._app.update_agent_status, agent_id, status)

        # Write to agent file
        status_msg = f"\n[Status Changed: {status.upper()}]\n"
        self._write_to_agent_file(agent_id, status_msg)

    def add_orchestrator_event(self, event: str):
        """Add an orchestrator coordination event."""
        self.orchestrator_events.append(event)

        # Write to system file
        self._write_to_system_file(event)

        # Update app if running
        if self._app:
            self._app.call_from_thread(self._app.add_orchestrator_event, event)

    def show_final_answer(self, answer: str, vote_results=None, selected_agent=None):
        """Show final answer with flush effect."""
        # Write to final presentation file
        with open(self.final_presentation_file, "w", encoding="utf-8") as f:
            f.write("=== FINAL PRESENTATION ===\n")
            if selected_agent:
                f.write(f"Selected Agent: {selected_agent}\n")
            if vote_results:
                f.write(f"Vote Results: {vote_results}\n")
            f.write(f"\n{answer}\n")

        # Trigger modal
        if self._app:
            self._app.call_from_thread(
                self._app.show_final_presentation,
                answer,
                vote_results,
                selected_agent,
            )

    def show_post_evaluation_content(self, content: str, agent_id: str):
        """Display post-evaluation streaming content."""
        # Write to agent file
        eval_msg = f"\n[POST-EVALUATION]\n{content}"
        self._write_to_agent_file(agent_id, eval_msg)

        # Update app if running
        if self._app:
            self._app.call_from_thread(
                self._app.show_post_evaluation,
                content,
                agent_id,
            )

    def show_restart_banner(self, reason: str, instructions: str, attempt: int, max_attempts: int):
        """Display restart decision banner."""
        banner_msg = f"\n{'=' * 60}\n" f"RESTART TRIGGERED (Attempt {attempt}/{max_attempts})\n" f"Reason: {reason}\n" f"Instructions: {instructions}\n" f"{'=' * 60}\n"

        # Write to system file
        self._write_to_system_file(banner_msg)

        # Update app if running
        if self._app:
            self._app.call_from_thread(
                self._app.show_restart_banner,
                reason,
                instructions,
                attempt,
                max_attempts,
            )

    def show_restart_context_panel(self, reason: str, instructions: str):
        """Display restart context panel at top of UI (for attempt 2+)."""
        self.restart_reason = reason
        self.restart_instructions = instructions

        # Update app if running
        if self._app:
            self._app.call_from_thread(
                self._app.show_restart_context,
                reason,
                instructions,
            )

    def cleanup(self):
        """Cleanup and exit Textual app."""
        if self._app:
            self._app.exit()
            self._app = None
        self._ready_event.clear()

    def run(self):
        """Run Textual app in main thread."""
        if self._app and TEXTUAL_AVAILABLE:
            self._app.run()

    async def run_async(self):
        """Run Textual app within an existing asyncio event loop."""
        if self._app and TEXTUAL_AVAILABLE:
            await self._app.run_async()

    # Rich parity methods (not in BaseDisplay, but needed for feature parity)
    def display_vote_results(self, vote_results: Dict[str, Any]):
        """Display vote results in formatted table."""
        if self._app:
            self._app.call_from_thread(self._app.display_vote_results, vote_results)

        # Write to system file
        self._write_to_system_file(f"Vote Results: {vote_results}")

    def display_coordination_table(self):
        """Display coordination table using existing builder."""
        if self._app:
            self._app.call_from_thread(self._app.display_coordination_table)

    def show_agent_selector(self):
        """Show interactive agent selector modal."""
        if self._app:
            self._app.call_from_thread(self._app.show_agent_selector)


# Textual App Implementation
if TEXTUAL_AVAILABLE:
    from textual.binding import Binding
    from textual.css.query import NoMatches
    from textual.widgets import Button, ListItem, ListView

    class TextualApp(App):
        """Main Textual application for MassGen coordination."""

        THEMES_DIR = Path(__file__).parent / "textual_themes"
        CSS_PATH = str(THEMES_DIR / "dark.tcss")

        BINDINGS = [
            Binding("tab", "next_agent", "Next Agent"),
            Binding("shift+tab", "prev_agent", "Prev Agent"),
            Binding("page_up", "scroll_up_fast", "Page Up"),
            Binding("page_down", "scroll_down_fast", "Page Down"),
            Binding("e", "open_editor", "Open in Editor"),
            Binding("v", "open_vscode", "Open in VSCode"),
            Binding("i", "agent_selector", "Agent Selector"),
            Binding("c", "coordination_table", "Coordination Table"),
            Binding("q", "quit", "Quit"),
        ]

        def __init__(
            self,
            display: TextualTerminalDisplay,
            question: str,
            refresh_rate: int,
            buffers: Dict[str, List],
            buffer_lock: threading.Lock,
            buffer_flush_interval: float,
        ):
            super().__init__()
            self.coordination_display = display
            self.question = question
            self.refresh_rate = refresh_rate
            self._buffers = buffers
            self._buffer_lock = buffer_lock
            self.buffer_flush_interval = buffer_flush_interval

            # Widget references
            self.agent_widgets = {}
            self.orchestrator_panel = None
            self.header_widget = None
            self.footer_widget = None

            # State
            self.current_agent_index = 0
            self._final_presentation_active = False
            self._post_evaluation_active = False

            # Set theme CSS path
            if display.theme == "light":
                self.CSS_PATH = str(self.THEMES_DIR / "light.tcss")

        def compose(self) -> ComposeResult:
            """Compose the UI layout."""
            # Header
            self.header_widget = HeaderWidget(self.question)
            yield self.header_widget

            # Main container with agent columns and orchestrator panel
            with Container(id="main_container"):
                # Agent columns
                with Container(id="agents_container"):
                    for agent_id in self.coordination_display.agent_ids:
                        agent_widget = AgentPanel(agent_id)
                        self.agent_widgets[agent_id] = agent_widget
                        yield agent_widget

                # Orchestrator panel (side-by-side layout)
                self.orchestrator_panel = OrchestratorPanel()
                yield self.orchestrator_panel

            # Footer
            self.footer_widget = Footer()
            yield self.footer_widget

        async def on_mount(self):
            """Set up periodic buffer flushing when app starts."""
            # Set up periodic buffer flushing
            self.set_interval(self.buffer_flush_interval, self._flush_buffers)

        async def _flush_buffers(self):
            """Flush buffered content to widgets (runs in asyncio event loop)."""
            for agent_id in self.coordination_display.agent_ids:
                with self._buffer_lock:
                    if not self._buffers[agent_id]:
                        continue
                    buffer_copy = self._buffers[agent_id].copy()
                    self._buffers[agent_id].clear()

                # Update widget
                if buffer_copy and agent_id in self.agent_widgets:
                    for item in buffer_copy:
                        await self.update_agent_widget(
                            agent_id,
                            item["content"],
                            item.get("type", "thinking"),
                        )

        async def update_agent_widget(self, agent_id: str, content: str, content_type: str):
            """Update agent widget with content."""
            if agent_id in self.agent_widgets:
                self.agent_widgets[agent_id].add_content(content, content_type)

        def update_agent_status(self, agent_id: str, status: str):
            """Update agent status."""
            if agent_id in self.agent_widgets:
                self.agent_widgets[agent_id].update_status(status)

        def add_orchestrator_event(self, event: str):
            """Add orchestrator event."""
            if self.orchestrator_panel:
                self.orchestrator_panel.add_event(event)

        def show_final_presentation(
            self,
            answer: str,
            vote_results=None,
            selected_agent=None,
        ):
            """Display final answer modal with flush effect."""

            async def _show_modal():
                modal = FinalPresentationModal(
                    answer=answer,
                    flush_char_delay=self.coordination_display.flush_char_delay,
                    flush_word_delay=self.coordination_display.flush_word_delay,
                    vote_results=vote_results,
                    selected_agent=selected_agent,
                )
                await self.push_screen(modal)

            self.call_later(_show_modal)

        def show_post_evaluation(self, content: str, agent_id: str):
            """Show post-evaluation content."""
            # Add to orchestrator panel with special formatting
            if self.orchestrator_panel:
                self.orchestrator_panel.add_event(
                    f"[POST-EVALUATION by {agent_id}]\n{content}",
                )

        def show_restart_banner(
            self,
            reason: str,
            instructions: str,
            attempt: int,
            max_attempts: int,
        ):
            """Show restart banner."""
            if self.header_widget:
                self.header_widget.show_restart_banner(
                    reason,
                    instructions,
                    attempt,
                    max_attempts,
                )

        def show_restart_context(self, reason: str, instructions: str):
            """Show restart context."""
            if self.header_widget:
                self.header_widget.show_restart_context(reason, instructions)

        def display_vote_results(self, vote_results: Dict[str, Any]):
            """Display vote results."""
            # Format vote results for display
            formatted = f"Vote Results: {vote_results}"
            if self.orchestrator_panel:
                self.orchestrator_panel.add_event(formatted)

        def display_coordination_table(self):
            """Display coordination table."""
            try:
                from massgen.frontend.displays.create_coordination_table import (
                    CoordinationTableBuilder,
                )

                tracker = getattr(
                    self.coordination_display.orchestrator,
                    "coordination_tracker",
                    None,
                )

                if not tracker:
                    modal = CoordinationTableModal(
                        "Coordination data is not available yet.",
                    )
                    self.push_screen(modal)
                    return

                events_data = [event.to_dict() for event in getattr(tracker, "events", [])]
                session_data = {
                    "session_metadata": {
                        "user_prompt": getattr(tracker, "user_prompt", ""),
                        "agent_ids": getattr(tracker, "agent_ids", []),
                        "start_time": getattr(tracker, "start_time", None),
                        "end_time": getattr(tracker, "end_time", None),
                        "final_winner": getattr(tracker, "final_winner", None),
                    },
                    "events": events_data,
                }

                builder = CoordinationTableBuilder(session_data)
                table = builder.generate_event_table()
                if not table:
                    table = "No coordination events have been recorded yet."

                modal = CoordinationTableModal(table)
                self.push_screen(modal)
            except Exception as exc:
                modal = CoordinationTableModal(
                    f"Unable to build coordination table: {exc}",
                )
                self.push_screen(modal)

        def show_agent_selector(self):
            """Show agent selector modal."""
            modal = AgentSelectorModal(
                self.coordination_display.agent_ids,
                self.coordination_display,
            )
            self.push_screen(modal)

        def action_next_agent(self):
            """Move focus to next agent."""
            self.current_agent_index = (self.current_agent_index + 1) % len(self.coordination_display.agent_ids)
            agent_id = self.coordination_display.agent_ids[self.current_agent_index]
            if agent_id in self.agent_widgets:
                self.agent_widgets[agent_id].focus()

        def action_prev_agent(self):
            """Move focus to previous agent."""
            self.current_agent_index = (self.current_agent_index - 1) % len(self.coordination_display.agent_ids)
            agent_id = self.coordination_display.agent_ids[self.current_agent_index]
            if agent_id in self.agent_widgets:
                self.agent_widgets[agent_id].focus()

        def action_scroll_up_fast(self):
            """Fast scroll up."""
            agent_id = self.coordination_display.agent_ids[self.current_agent_index]
            if agent_id in self.agent_widgets:
                self.agent_widgets[agent_id].scroll_up(10)

        def action_scroll_down_fast(self):
            """Fast scroll down."""
            agent_id = self.coordination_display.agent_ids[self.current_agent_index]
            if agent_id in self.agent_widgets:
                self.agent_widgets[agent_id].scroll_down(10)

        def action_open_editor(self):
            """Open current agent file in default editor."""
            agent_id = self.coordination_display.agent_ids[self.current_agent_index]
            self.coordination_display._open_in_editor(agent_id, "default")

        def action_open_vscode(self):
            """Open current agent file in VSCode."""
            agent_id = self.coordination_display.agent_ids[self.current_agent_index]
            self.coordination_display._open_in_editor(agent_id, "vscode")

        def action_agent_selector(self):
            """Show agent selector."""
            self.show_agent_selector()

        def action_coordination_table(self):
            """Show coordination table."""
            self.display_coordination_table()

        def action_quit(self):
            """Quit the application."""
            self.exit()

    # Widget implementations
    class HeaderWidget(Static):
        """Header widget showing question and restart context."""

        def __init__(self, question: str):
            super().__init__()
            self.question = question
            self.restart_banner = None

        def compose(self) -> ComposeResult:
            yield Label(f"💡 Question: {self.question}", id="question_label")

        def show_restart_banner(
            self,
            reason: str,
            instructions: str,
            attempt: int,
            max_attempts: int,
        ):
            """Show restart banner."""
            banner_text = f"⚠️ RESTART (Attempt {attempt}/{max_attempts}): {reason}"
            try:
                banner_label = self.query_one("#restart_banner")
                banner_label.update(banner_text)
            except NoMatches:
                # Create banner if it doesn't exist
                banner = Label(banner_text, id="restart_banner")
                self.mount(banner, before=0)

        def show_restart_context(self, reason: str, instructions: str):
            """Show restart context."""
            context_text = f"📋 Previous attempt: {reason}"
            try:
                context_label = self.query_one("#restart_context")
                context_label.update(context_text)
            except NoMatches:
                # Create context if it doesn't exist
                context = Label(context_text, id="restart_context")
                self.mount(context)

    class AgentPanel(ScrollableContainer):
        """Panel for individual agent output."""

        def __init__(self, agent_id: str):
            super().__init__(id=f"agent_{agent_id}")
            self.agent_id = agent_id
            self.status = "waiting"
            self.content_log = RichLog(
                id=f"log_{agent_id}",
                highlight=True,
                markup=True,
                wrap=True,
            )

        def compose(self) -> ComposeResult:
            with Vertical():
                # Agent header with status
                yield Label(
                    f"🤖 {self.agent_id} [{self.status}]",
                    id=f"header_{self.agent_id}",
                )
                # Content area
                yield self.content_log

        def add_content(self, content: str, content_type: str):
            """Add content to agent panel."""
            # Apply formatting based on content type
            if content_type == "tool":
                self.content_log.write(f"[cyan]🔧 {content}[/cyan]")
            elif content_type == "status":
                self.content_log.write(f"[yellow]📊 {content}[/yellow]")
            else:
                self.content_log.write(content)

        def update_status(self, status: str):
            """Update agent status."""
            self.status = status
            header = self.query_one(f"#header_{self.agent_id}")
            status_emoji = {
                "waiting": "⏳",
                "working": "🔄",
                "streaming": "📝",
                "completed": "✅",
                "error": "❌",
            }.get(status, "🤖")
            header.update(f"{status_emoji} {self.agent_id} [{status}]")

        def scroll_up(self, lines: int):
            """Scroll content up."""
            for _ in range(lines):
                self.content_log.scroll_up()

        def scroll_down(self, lines: int):
            """Scroll content down."""
            for _ in range(lines):
                self.content_log.scroll_down()

    class OrchestratorPanel(ScrollableContainer):
        """Panel for orchestrator events."""

        def __init__(self):
            super().__init__(id="orchestrator_panel")
            self.events_log = RichLog(
                id="orchestrator_log",
                highlight=True,
                markup=True,
                wrap=True,
            )

        def compose(self) -> ComposeResult:
            with Vertical():
                yield Label("📊 Orchestrator Events", id="orchestrator_header")
                yield self.events_log

        def add_event(self, event: str):
            """Add orchestrator event."""
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.events_log.write(f"[dim]{timestamp}[/dim] {event}")

    class FinalPresentationModal(ModalScreen):
        """Full-screen modal for final answer with flush effect."""

        def __init__(
            self,
            answer: str,
            flush_char_delay: float,
            flush_word_delay: float,
            vote_results=None,
            selected_agent=None,
        ):
            super().__init__()
            self.answer = answer
            self.flush_char_delay = flush_char_delay
            self.flush_word_delay = flush_word_delay
            self.vote_results = vote_results
            self.selected_agent = selected_agent
            self.content_area = None

        def compose(self) -> ComposeResult:
            with Container(id="presentation_container"):
                yield Label("🎤 Final Presentation", id="presentation_header")

                if self.selected_agent:
                    yield Label(f"Selected Agent: {self.selected_agent}")

                if self.vote_results:
                    yield Label(f"Vote Results: {self.vote_results}")

                self.content_area = TextArea(
                    id="answer_content",
                    read_only=True,
                )
                yield self.content_area
                yield Button("Dismiss (ESC)", id="dismiss_button")

        async def on_mount(self):
            """Render answer character-by-character when modal opens."""
            if self.content_area:
                # Character-by-character flush effect
                displayed_text = ""
                for char in self.answer:
                    displayed_text += char
                    self.content_area.text = displayed_text
                    await asyncio.sleep(self.flush_char_delay)

                    # Extra delay after punctuation
                    if char in ".!?":
                        await asyncio.sleep(self.flush_word_delay)

        def on_button_pressed(self, event: Button.Pressed):
            """Handle button press."""
            if event.button.id == "dismiss_button":
                self.dismiss()

    class AgentSelectorModal(ModalScreen):
        """Interactive agent selection menu."""

        def __init__(self, agent_ids: List[str], display: TextualTerminalDisplay):
            super().__init__()
            self.agent_ids = agent_ids
            self.coordination_display = display

        def compose(self) -> ComposeResult:
            with Container(id="selector_container"):
                yield Label("Select an agent to view:", id="selector_header")

                items = [ListItem(Label(f"📄 View {agent_id}")) for agent_id in self.agent_ids]
                items.append(ListItem(Label("📊 View System Status")))
                items.append(ListItem(Label("📋 View Coordination Table")))

                yield ListView(*items, id="agent_list")
                yield Button("Cancel (ESC)", id="cancel_button")

        def on_list_view_selected(self, event):
            """Handle selection from list."""
            index = event.list_view.index
            if index < len(self.agent_ids):
                # View agent file
                agent_id = self.agent_ids[index]
                self.coordination_display._open_in_editor(agent_id)
            elif index == len(self.agent_ids):
                # View system status
                self.coordination_display._open_in_editor("system_status")
            elif index == len(self.agent_ids) + 1:
                # View coordination table
                self.app.display_coordination_table()

            self.dismiss()

        def on_button_pressed(self, event: Button.Pressed):
            """Handle button press."""
            if event.button.id == "cancel_button":
                self.dismiss()

    class CoordinationTableModal(ModalScreen):
        """Modal to display coordination table."""

        def __init__(self, table_content: str):
            super().__init__()
            self.table_content = table_content

        def compose(self) -> ComposeResult:
            with Container(id="table_container"):
                yield Label("📋 Coordination Table", id="table_header")
                yield TextArea(
                    self.table_content,
                    id="table_content",
                    read_only=True,
                )
                yield Button("Close (ESC)", id="close_button")

        def on_button_pressed(self, event: Button.Pressed):
            """Handle button press."""
            if event.button.id == "close_button":
                self.dismiss()


def is_textual_available() -> bool:
    """Check if Textual is available."""
    return TEXTUAL_AVAILABLE


def create_textual_display(agent_ids: List[str], **kwargs) -> Optional[TextualTerminalDisplay]:
    """Factory function to create Textual display if available."""
    if not TEXTUAL_AVAILABLE:
        return None
    return TextualTerminalDisplay(agent_ids, **kwargs)
