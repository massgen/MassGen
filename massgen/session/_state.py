# -*- coding: utf-8 -*-
"""Session state management for MassGen.

This module provides functionality to save and restore session state,
including conversation history, workspace snapshots, and turn metadata.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SessionState:
    """Complete state of a MassGen session.

    Attributes:
        session_id: Unique session identifier
        conversation_history: Full conversation history as messages
        current_turn: Number of completed turns
        last_workspace_path: Path to most recent workspace snapshot
        winning_agents_history: History of winning agents per turn
        previous_turns: Turn metadata for orchestrator
        session_storage_path: Actual directory where session was found (for consistency)
        log_directory: Log directory name to reuse (e.g., "log_20251101_151837")
    """

    session_id: str
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    current_turn: int = 0
    last_workspace_path: Optional[Path] = None
    winning_agents_history: List[Dict[str, Any]] = field(default_factory=list)
    previous_turns: List[Dict[str, Any]] = field(default_factory=list)
    session_storage_path: str = "sessions"  # Where the session was actually found
    log_directory: Optional[str] = None  # Log directory to reuse for all turns


def restore_session(
    session_id: str,
    session_storage: str = "sessions",
    registry: Optional[Any] = None,
) -> Optional[SessionState]:
    """Restore complete session state from disk.

    Loads all turn data from session storage directory, reconstructing:
    - Conversation history from task + answer pairs
    - Turn metadata for orchestrator
    - Winning agents history for memory sharing
    - Most recent workspace path
    - Log directory to reuse

    Args:
        session_id: Session to restore
        session_storage: Base directory for session storage (default: "sessions")
        registry: Optional SessionRegistry instance to load metadata from

    Returns:
        SessionState object if session exists and has turns, None otherwise

    Raises:
        ValueError: If session exists but has no conversation messages (empty session)

    Example:
        >>> state = restore_session("session_20251029_120000")
        >>> if state:
        ...     print(f"Restored {state.current_turn} turns")
        ...     print(f"History: {len(state.conversation_history)} messages")
    """
    # Load log directory from registry if available
    log_directory = None
    if registry:
        session_metadata = registry.get_session(session_id)
        if session_metadata:
            log_directory = session_metadata.get("log_directory")
    # Session storage location (primary: sessions/, legacy: .massgen/memory_test_sessions/)
    session_dir = Path(session_storage) / session_id

    # Check primary location first, then ONE legacy location for backward compatibility
    if not session_dir.exists():
        legacy_dir = Path(".massgen/memory_test_sessions") / session_id
        if legacy_dir.exists():
            session_dir = legacy_dir
            logger.info(f"Using legacy session location: {legacy_dir}")

    # Check if session directory exists
    if not session_dir.exists():
        raise ValueError(
            f"Session '{session_id}' not found in {session_storage} or legacy locations. " f"Cannot continue a non-existent session.",
        )

    # Helper to find turn directories
    def find_turns(base_dir: Path) -> set:
        """Return set of turn numbers that exist in this directory."""
        turns = set()
        for item in base_dir.iterdir():
            if item.is_dir() and item.name.startswith("turn_"):
                try:
                    turn_num = int(item.name.split("_")[1])
                    turns.add(turn_num)
                except (ValueError, IndexError):
                    continue
        return turns

    # Find all turn numbers
    all_turn_nums = find_turns(session_dir)

    if not all_turn_nums:
        raise ValueError(
            f"Session '{session_id}' exists at {session_dir} but has no saved turns. " f"Cannot continue an empty session.",
        )

    # Use the session directory we found
    actual_storage_path = str(session_dir.parent)
    logger.debug(f"Restoring session from: {actual_storage_path}")

    # Load previous turns metadata
    previous_turns = []

    # Process turns in order
    for turn_num in sorted(all_turn_nums):
        turn_dir = session_dir / f"turn_{turn_num}"

        metadata_file = turn_dir / "metadata.json"
        if metadata_file.exists():
            try:
                metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
                workspace_path = (turn_dir / "workspace").resolve()

                previous_turns.append(
                    {
                        "turn": turn_num,
                        "path": str(workspace_path),
                        "task": metadata.get("task", ""),
                        "winning_agent": metadata.get("winning_agent", ""),
                    },
                )
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load metadata for turn {turn_num}: {e}")

    # Build conversation history from turns
    conversation_history = []

    for turn_data in previous_turns:
        turn_dir = session_dir / f"turn_{turn_data['turn']}"
        answer_file = turn_dir / "answer.txt"

        # Add user message (task)
        if turn_data["task"]:
            conversation_history.append(
                {
                    "role": "user",
                    "content": turn_data["task"],
                },
            )

        # Add assistant message (answer)
        if answer_file.exists():
            try:
                answer_text = answer_file.read_text(encoding="utf-8")
                conversation_history.append(
                    {
                        "role": "assistant",
                        "content": answer_text,
                    },
                )
            except IOError as e:
                logger.warning(f"Failed to load answer for turn {turn_data['turn']}: {e}")

    # Validate that we have actual conversation content
    if not conversation_history:
        raise ValueError(
            f"Session '{session_id}' exists but has no conversation messages. "
            f"Found {len(previous_turns)} turn(s) but all tasks/answers were empty or missing. "
            f"Cannot continue an empty session.",
        )

    # Load winning agents history
    winning_agents_history = []
    winning_agents_file = session_dir / "winning_agents_history.json"
    if winning_agents_file.exists():
        try:
            winning_agents_history = json.loads(
                winning_agents_file.read_text(encoding="utf-8"),
            )
            logger.debug(
                f"Loaded {len(winning_agents_history)} winning agent(s) " f"from {winning_agents_file}: {winning_agents_history}",
            )
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load winning agents history from {winning_agents_file}: {e}")

    # Find most recent workspace
    last_workspace_path = None
    if previous_turns:
        last_turn = previous_turns[-1]
        workspace_path = Path(last_turn["path"])
        if workspace_path.exists():
            last_workspace_path = workspace_path

    # Create and return session state
    state = SessionState(
        session_id=session_id,
        conversation_history=conversation_history,
        current_turn=len(previous_turns),
        last_workspace_path=last_workspace_path,
        winning_agents_history=winning_agents_history,
        previous_turns=previous_turns,
        session_storage_path=actual_storage_path,  # Use actual path where session was found
        log_directory=log_directory,  # Reuse log directory from session metadata
    )

    logger.info(
        f"📚 Restored session {session_id} from {actual_storage_path}: " f"{state.current_turn} turns, " f"{len(state.conversation_history)} messages",
    )

    return state
