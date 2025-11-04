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
    # Check both primary and alternate locations for sessions
    # This handles cases where sessions may be split across directories due to path relocation
    primary_dir = Path(session_storage) / session_id
    alternate_path = None
    alternate_dir = None

    # Determine alternate path based on primary
    if session_storage.startswith(".massgen/"):
        alternate_path = session_storage.replace(".massgen/", "", 1)
        alternate_dir = Path(alternate_path) / session_id
    else:
        alternate_path = f".massgen/{session_storage}"
        alternate_dir = Path(alternate_path) / session_id

    # Find all turn directories across both locations
    def find_turns(base_dir: Path) -> set:
        """Return set of turn numbers that exist in this directory."""
        if not base_dir.exists():
            return set()
        turns = set()
        for item in base_dir.iterdir():
            if item.is_dir() and item.name.startswith("turn_"):
                try:
                    turn_num = int(item.name.split("_")[1])
                    turns.add(turn_num)
                except (ValueError, IndexError):
                    continue
        return turns

    primary_turn_nums = find_turns(primary_dir)
    alternate_turn_nums = find_turns(alternate_dir)
    all_turn_nums = primary_turn_nums | alternate_turn_nums

    if not all_turn_nums:
        logger.debug(f"Session directory not found or has no turns in {session_storage} or {alternate_path}")
        return None

    # ALWAYS use the location where turn_1 exists (original session location)
    # This keeps all turns in one place for easier log viewing
    if 1 in primary_turn_nums:
        actual_storage_path = session_storage
        logger.debug(f"Session originated in {session_storage}, will save all turns there")
    elif 1 in alternate_turn_nums:
        actual_storage_path = alternate_path
        logger.info(f"Session originated in {alternate_path}, will save all turns there")
    else:
        # Fallback: use location with most turns
        max_turn_primary = max(primary_turn_nums) if primary_turn_nums else 0
        max_turn_alternate = max(alternate_turn_nums) if alternate_turn_nums else 0
        if max_turn_alternate > max_turn_primary:
            actual_storage_path = alternate_path
        else:
            actual_storage_path = session_storage
        logger.warning(f"Turn 1 not found, using location with most turns: {actual_storage_path}")

    # We'll load turns from both locations below
    session_dirs_to_check = []
    if primary_dir.exists():
        session_dirs_to_check.append(primary_dir)
    if alternate_dir and alternate_dir.exists() and alternate_dir != primary_dir:
        session_dirs_to_check.append(alternate_dir)

    # Load previous turns metadata from all available turns (across both locations if split)
    previous_turns = []

    # Process turns in order
    for turn_num in sorted(all_turn_nums):
        # Check each location for this turn
        turn_dir = None
        for check_dir in session_dirs_to_check:
            candidate = check_dir / f"turn_{turn_num}"
            if candidate.exists():
                turn_dir = candidate
                break

        if not turn_dir:
            logger.warning(f"Turn {turn_num} not found in any location")
            continue

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

    # No turns found
    if not previous_turns:
        logger.debug(f"No turns found in session: {session_id}")
        return None

    # Build conversation history from turns
    conversation_history = []

    for turn_data in previous_turns:
        # Find answer file in either location
        answer_file = None
        for check_dir in session_dirs_to_check:
            candidate = check_dir / f"turn_{turn_data['turn']}" / "answer.txt"
            if candidate.exists():
                answer_file = candidate
                break

        # Add user message (task)
        if turn_data["task"]:
            conversation_history.append(
                {
                    "role": "user",
                    "content": turn_data["task"],
                },
            )

        # Add assistant message (answer)
        if answer_file and answer_file.exists():
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

    # Load winning agents history (check both locations, use first found)
    winning_agents_history = []
    for check_dir in session_dirs_to_check:
        winning_agents_file = check_dir / "winning_agents_history.json"
        if winning_agents_file.exists():
            try:
                winning_agents_history = json.loads(
                    winning_agents_file.read_text(encoding="utf-8"),
                )
                logger.debug(
                    f"Loaded {len(winning_agents_history)} winning agent(s) " f"from {winning_agents_file}: {winning_agents_history}",
                )
                break  # Use first found
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
