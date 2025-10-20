# -*- coding: utf-8 -*-
"""
Attempt Storage Module for MassGen

Handles unified storage for both:
1. Multi-turn conversations (between user messages) - turn_N/
2. Orchestration restart attempts (within a single user message) - turn_N/attempt_M/

This module provides a standardized way to save and load orchestration states,
supporting both the multi-turn feature and the new orchestration restart feature.

Structure:
sessions/{session_id}/
├── turn_1/
│   ├── attempt_1/
│   │   ├── metadata.json
│   │   ├── workspace/
│   │   └── answer.txt
│   ├── attempt_2/  (if restart occurred)
│   │   ├── metadata.json
│   │   ├── workspace/
│   │   └── answer.txt
│   └── successful_attempt.json  (points to which attempt succeeded)
├── turn_2/
│   └── attempt_1/
│       ├── metadata.json
│       ├── workspace/
│       └── answer.txt
└── SESSION_SUMMARY.txt
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class AttemptStorage:
    """
    Manages storage and retrieval of orchestration attempts.

    Supports both multi-turn conversations and within-turn orchestration restarts.
    """

    def __init__(self, session_storage: str):
        """
        Initialize AttemptStorage.

        Args:
            session_storage: Base directory for session storage
        """
        self.session_storage = Path(session_storage)
        self.session_storage.mkdir(parents=True, exist_ok=True)

    def save_attempt(
        self,
        session_id: str,
        turn_number: int,
        attempt_number: int,
        task: str,
        final_answer: str,
        winning_agent_id: str,
        workspace_path: Optional[str] = None,
        restart_reason: Optional[str] = None,
        restart_instructions: Optional[str] = None,
        additional_metadata: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """
        Save an orchestration attempt.

        Args:
            session_id: Unique session identifier
            turn_number: Turn number (user message index)
            attempt_number: Attempt number within the turn
            task: The task/question being addressed
            final_answer: The final answer from this attempt
            winning_agent_id: ID of the winning agent
            workspace_path: Path to workspace to copy (if any)
            restart_reason: Reason for restart if this attempt led to restart
            restart_instructions: Instructions provided for next attempt
            additional_metadata: Any additional metadata to store

        Returns:
            Path to the saved attempt directory
        """
        # Create attempt directory
        attempt_dir = self.session_storage / session_id / f"turn_{turn_number}" / f"attempt_{attempt_number}"
        attempt_dir.mkdir(parents=True, exist_ok=True)

        # Save metadata
        metadata = {
            "session_id": session_id,
            "turn": turn_number,
            "attempt": attempt_number,
            "timestamp": datetime.now().isoformat(),
            "task": task,
            "winning_agent": winning_agent_id,
            "restart_reason": restart_reason,
            "restart_instructions": restart_instructions,
        }

        if additional_metadata:
            metadata.update(additional_metadata)

        metadata_file = attempt_dir / "metadata.json"
        metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        # Save answer
        answer_file = attempt_dir / "answer.txt"
        answer_file.write_text(final_answer, encoding="utf-8")

        # Copy workspace if provided
        if workspace_path:
            workspace_path = Path(workspace_path)
            if workspace_path.exists():
                dest_workspace = attempt_dir / "workspace"
                if dest_workspace.exists():
                    shutil.rmtree(dest_workspace)
                shutil.copytree(workspace_path, dest_workspace)

        return attempt_dir

    def mark_successful_attempt(
        self,
        session_id: str,
        turn_number: int,
        attempt_number: int,
    ) -> None:
        """
        Mark which attempt was successful for a given turn.

        Args:
            session_id: Unique session identifier
            turn_number: Turn number
            attempt_number: Successful attempt number
        """
        turn_dir = self.session_storage / session_id / f"turn_{turn_number}"
        turn_dir.mkdir(parents=True, exist_ok=True)

        success_marker = turn_dir / "successful_attempt.json"
        success_marker.write_text(
            json.dumps({"attempt": attempt_number, "timestamp": datetime.now().isoformat()}, indent=2),
            encoding="utf-8",
        )

    def load_attempts(
        self,
        session_id: str,
        turn_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Load attempts for a session or specific turn.

        Args:
            session_id: Unique session identifier
            turn_number: Optional turn number to filter by

        Returns:
            List of attempt metadata dictionaries
        """
        session_dir = self.session_storage / session_id
        if not session_dir.exists():
            return []

        attempts = []

        # If turn_number specified, only load that turn
        if turn_number is not None:
            turn_dirs = [session_dir / f"turn_{turn_number}"]
        else:
            # Load all turns
            turn_dirs = sorted([d for d in session_dir.iterdir() if d.is_dir() and d.name.startswith("turn_")])

        for turn_dir in turn_dirs:
            if not turn_dir.exists():
                continue

            # Find all attempts in this turn
            attempt_dirs = sorted([d for d in turn_dir.iterdir() if d.is_dir() and d.name.startswith("attempt_")])

            for attempt_dir in attempt_dirs:
                metadata_file = attempt_dir / "metadata.json"
                if metadata_file.exists():
                    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))

                    # Add workspace path if it exists
                    workspace_path = attempt_dir / "workspace"
                    if workspace_path.exists():
                        metadata["workspace_path"] = str(workspace_path.resolve())

                    # Add answer path
                    answer_path = attempt_dir / "answer.txt"
                    if answer_path.exists():
                        metadata["answer_path"] = str(answer_path.resolve())
                        metadata["answer"] = answer_path.read_text(encoding="utf-8")

                    attempts.append(metadata)

        return attempts

    def get_attempt_context(
        self,
        session_id: str,
        turn_number: int,
        current_attempt: int,
    ) -> Dict[str, Any]:
        """
        Get context about previous attempts for the current turn.

        This is used to provide agents with information about what was tried before
        when an orchestration restart occurs.

        Args:
            session_id: Unique session identifier
            turn_number: Current turn number
            current_attempt: Current attempt number

        Returns:
            Dictionary with previous attempts context
        """
        previous_attempts = []

        for attempt_num in range(1, current_attempt):
            attempts = self.load_attempts(session_id, turn_number)
            attempt_data = [a for a in attempts if a.get("attempt") == attempt_num]

            if attempt_data:
                previous_attempts.append(attempt_data[0])

        return {
            "turn": turn_number,
            "current_attempt": current_attempt,
            "previous_attempts": previous_attempts,
            "has_previous_attempts": len(previous_attempts) > 0,
        }

    def load_previous_turns_for_multi_turn(
        self,
        session_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Load previous turns for multi-turn conversation.

        For each turn, returns the successful attempt (or latest attempt if none marked).
        This maintains compatibility with the existing multi-turn system.

        Args:
            session_id: Unique session identifier

        Returns:
            List of previous turn information
        """
        session_dir = self.session_storage / session_id
        if not session_dir.exists():
            return []

        previous_turns = []
        turn_num = 1

        while True:
            turn_dir = session_dir / f"turn_{turn_num}"
            if not turn_dir.exists():
                break

            # Check for successful attempt marker
            success_marker = turn_dir / "successful_attempt.json"
            if success_marker.exists():
                success_data = json.loads(success_marker.read_text(encoding="utf-8"))
                attempt_num = success_data["attempt"]
            else:
                # No marker, use latest attempt
                attempt_dirs = sorted([d for d in turn_dir.iterdir() if d.is_dir() and d.name.startswith("attempt_")])
                if not attempt_dirs:
                    turn_num += 1
                    continue
                attempt_num = int(attempt_dirs[-1].name.split("_")[1])

            # Load the successful/latest attempt
            metadata_file = turn_dir / f"attempt_{attempt_num}" / "metadata.json"
            if metadata_file.exists():
                metadata = json.loads(metadata_file.read_text(encoding="utf-8"))

                # Add workspace path (absolute)
                workspace_path = (turn_dir / f"attempt_{attempt_num}" / "workspace").resolve()

                previous_turns.append(
                    {
                        "turn": turn_num,
                        "path": str(workspace_path),
                        "task": metadata.get("task", ""),
                        "winning_agent": metadata.get("winning_agent", ""),
                    },
                )

            turn_num += 1

        return previous_turns

    def update_session_summary(
        self,
        session_id: str,
        turn_number: int,
        attempt_number: int,
        task: str,
        is_successful: bool = True,
    ) -> None:
        """
        Update the session summary file.

        Args:
            session_id: Unique session identifier
            turn_number: Turn number
            attempt_number: Attempt number
            task: The task being addressed
            is_successful: Whether this attempt was successful
        """
        session_dir = self.session_storage / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        summary_file = session_dir / "SESSION_SUMMARY.txt"

        # Read existing summary or create header
        if summary_file.exists():
            summary_lines = summary_file.read_text(encoding="utf-8").splitlines()
        else:
            summary_lines = [
                "=" * 80,
                f"Multi-Turn Session: {session_id}",
                "=" * 80,
                "",
            ]

        # Add attempt information
        summary_lines.append("")
        summary_lines.append("=" * 80)
        summary_lines.append(f"TURN {turn_number} - ATTEMPT {attempt_number}")
        summary_lines.append("=" * 80)
        summary_lines.append(f"Timestamp: {datetime.now().isoformat()}")
        summary_lines.append(f"Task: {task}")
        summary_lines.append(f"Status: {'✓ Successful' if is_successful else '↻ Restarted'}")

        attempt_dir = session_dir / f"turn_{turn_number}" / f"attempt_{attempt_number}"
        summary_lines.append(f"Workspace: {(attempt_dir / 'workspace').resolve()}")
        summary_lines.append(f"Answer: See {(attempt_dir / 'answer.txt').resolve()}")
        summary_lines.append("")

        summary_file.write_text("\n".join(summary_lines), encoding="utf-8")
