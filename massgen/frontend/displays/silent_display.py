# -*- coding: utf-8 -*-
"""
Silent Display for MassGen Coordination

Minimal output display designed for automation, background execution, and LLM-managed workflows.
Provides only essential information while detailed progress is available via status.json file.
"""

import time
from pathlib import Path
from typing import Optional

from .base_display import BaseDisplay


class SilentDisplay(BaseDisplay):
    """Silent display for automation contexts.

    Designed for LLM agents and automation tools that need:
    - Minimal stdout output (< 15 lines)
    - No emojis or ANSI codes
    - Clear file paths for monitoring
    - Real-time progress via status.json

    Prints only:
    - Log directory path
    - Status file path
    - Question being answered
    - Final result summary
    """

    def __init__(self, agent_ids, **kwargs):
        """Initialize silent display.

        Args:
            agent_ids: List of agent IDs participating
            **kwargs: Additional configuration options
        """
        super().__init__(agent_ids, **kwargs)
        self.log_dir = None
        self.start_time = None

    def initialize(self, question: str, log_filename: Optional[str] = None):
        """Initialize the display with essential information only.

        Prints:
        - LOG_DIR: Full path to log directory
        - STATUS: Path to status.json file for real-time monitoring
        - QUESTION: The question being answered

        Args:
            question: The user's question
            log_filename: Path to the main log file (used to determine log directory)
        """
        self.start_time = time.time()

        if log_filename:
            self.log_dir = Path(log_filename).parent
            print(f"LOG_DIR: {self.log_dir}")
            print(f"STATUS: {self.log_dir / 'status.json'}")

        print(f"QUESTION: {question}")
        print("[Coordination in progress - monitor status.json for real-time updates]")

    def update_agent_content(self, agent_id: str, content: str, content_type: str = "thinking"):
        """Update content for a specific agent (silent - no output).

        Content is still stored internally but not printed to stdout.
        Monitor status.json for real-time agent activity.

        Args:
            agent_id: The agent whose content to update
            content: The content to store
            content_type: Type of content (ignored in silent mode)
        """
        if agent_id not in self.agent_ids:
            return

        # Store content internally for potential later use
        self.agent_outputs[agent_id].append(content)
        # But don't print anything to stdout

    def update_agent_status(self, agent_id: str, status: str):
        """Update status for a specific agent (silent - no output).

        Status changes are tracked in status.json instead of stdout.

        Args:
            agent_id: The agent whose status to update
            status: New status string
        """
        if agent_id not in self.agent_ids:
            return

        self.agent_status[agent_id] = status
        # Silent - no output to stdout

    def add_orchestrator_event(self, event: str):
        """Add an orchestrator coordination event (silent - no output).

        Events are tracked in coordination_events.json instead of stdout.

        Args:
            event: The coordination event message
        """
        self.orchestrator_events.append(event)
        # Silent - no output to stdout

    def show_final_answer(self, answer: str, vote_results=None, selected_agent=None):
        """Display the final coordinated answer with essential information.

        Prints:
        - WINNER: The winning agent ID
        - ANSWER_FILE: Path to final answer file
        - DURATION: Total coordination time
        - ANSWER_PREVIEW: First 200 characters of answer

        Args:
            answer: The final coordinated answer
            vote_results: Dictionary of vote results
            selected_agent: The winning agent ID
        """
        print()  # Blank line for readability

        if selected_agent:
            print(f"WINNER: {selected_agent}")

        if self.log_dir and selected_agent:
            answer_file = self.log_dir / f"final/{selected_agent}/answer.txt"
            print(f"ANSWER_FILE: {answer_file}")

        if self.start_time:
            duration = time.time() - self.start_time
            print(f"DURATION: {duration:.1f}s")

        # Show preview of answer (first 200 chars)
        if answer:
            preview_length = 200
            preview = answer[:preview_length]
            if len(answer) > preview_length:
                preview += "..."
            print(f"ANSWER_PREVIEW: {preview}")

    def show_post_evaluation_content(self, content: str, agent_id: str):
        """Display post-evaluation streaming content (silent - no output).

        Post-evaluation content is logged to files instead of stdout.

        Args:
            content: Post-evaluation content from the agent
            agent_id: The agent performing the evaluation
        """
        # Silent - no output to stdout

    def show_restart_banner(self, reason: str, instructions: str, attempt: int, max_attempts: int):
        """Display restart decision banner (minimal output).

        Prints minimal restart notification for awareness.

        Args:
            reason: Why the restart was triggered
            instructions: Instructions for the next attempt
            attempt: Next attempt number
            max_attempts: Maximum attempts allowed
        """
        print(f"RESTART: Attempt {attempt}/{max_attempts}")

    def show_restart_context_panel(self, reason: str, instructions: str):
        """Display restart context panel (silent - no output).

        Restart context is available in coordination logs.

        Args:
            reason: Why the previous attempt restarted
            instructions: Instructions for this attempt
        """
        # Silent - no output to stdout

    def cleanup(self):
        """Clean up resources and print final summary.

        Prints:
        - COMPLETED: Confirmation message
        - AGENTS: Number of agents that participated
        """
        if self.start_time:
            duration = time.time() - self.start_time
            print(f"\nCOMPLETED: {len(self.agent_ids)} agents, {duration:.1f}s total")
        else:
            print(f"\nCOMPLETED: {len(self.agent_ids)} agents")
