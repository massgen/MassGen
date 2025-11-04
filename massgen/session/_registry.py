# -*- coding: utf-8 -*-
"""Session registry for tracking and managing memory sessions.

This module provides functionality to:
- Log session IDs when sessions start/end
- Store session metadata (timestamp, config, model info)
- List available sessions
- Retrieve session details
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SessionRegistry:
    """Registry for tracking memory sessions across MassGen runs.

    Sessions are stored in ~/.massgen/sessions.json with metadata including:
    - session_id: Unique identifier for the session
    - start_time: ISO timestamp when session started
    - end_time: ISO timestamp when session ended (if completed)
    - config_path: Path to YAML config used
    - model: Primary model used (if available)
    - status: "active" or "completed"
    - description: Optional user-provided description
    """

    def __init__(self, registry_path: Optional[str] = None):
        """Initialize session registry.

        Args:
            registry_path: Path to registry file. Defaults to ~/.massgen/sessions.json
        """
        if registry_path:
            self.registry_path = Path(registry_path)
        else:
            massgen_dir = Path.home() / ".massgen"
            massgen_dir.mkdir(exist_ok=True)
            self.registry_path = massgen_dir / "sessions.json"

        self._ensure_registry_exists()

    def _ensure_registry_exists(self) -> None:
        """Create registry file if it doesn't exist."""
        if not self.registry_path.exists():
            self.registry_path.write_text(json.dumps({"sessions": []}, indent=2))
            logger.debug(f"Created session registry at {self.registry_path}")

    def _load_registry(self) -> Dict[str, List[Dict[str, Any]]]:
        """Load registry from disk."""
        try:
            with open(self.registry_path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load session registry: {e}. Creating new registry.")
            return {"sessions": []}

    def _save_registry(self, data: Dict[str, List[Dict[str, Any]]]) -> None:
        """Save registry to disk."""
        try:
            with open(self.registry_path, "w") as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            logger.error(f"Failed to save session registry: {e}")

    def register_session(
        self,
        session_id: str,
        config_path: Optional[str] = None,
        model: Optional[str] = None,
        description: Optional[str] = None,
        **metadata: Any,
    ) -> None:
        """Register a new session or update existing session.

        Args:
            session_id: Unique session identifier
            config_path: Path to configuration file used
            model: Model name/ID used for the session
            description: Optional description of the session
            **metadata: Additional metadata to store
        """
        registry = self._load_registry()

        # Check if session already exists
        existing_session = None
        for session in registry["sessions"]:
            if session["session_id"] == session_id:
                existing_session = session
                break

        if existing_session:
            # Update existing session
            existing_session.update(
                {
                    "config_path": config_path,
                    "model": model,
                    "description": description,
                    **metadata,
                },
            )
            logger.debug(f"Updated existing session: {session_id}")
        else:
            # Create new session
            new_session = {
                "session_id": session_id,
                "start_time": datetime.now().isoformat(),
                "end_time": None,
                "status": "active",
                "config_path": config_path,
                "model": model,
                "description": description,
                **metadata,
            }
            registry["sessions"].append(new_session)
            logger.info(f"Registered new session: {session_id}")

        self._save_registry(registry)

    def complete_session(self, session_id: str) -> None:
        """Mark a session as completed.

        Args:
            session_id: Session to mark as completed
        """
        registry = self._load_registry()

        for session in registry["sessions"]:
            if session["session_id"] == session_id:
                session["end_time"] = datetime.now().isoformat()
                session["status"] = "completed"
                logger.info(f"Marked session as completed: {session_id}")
                break

        self._save_registry(registry)

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a specific session.

        Args:
            session_id: Session to retrieve

        Returns:
            Session metadata dict or None if not found
        """
        registry = self._load_registry()

        for session in registry["sessions"]:
            if session["session_id"] == session_id:
                return session

        return None

    def list_sessions(
        self,
        limit: Optional[int] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List all registered sessions.

        Args:
            limit: Maximum number of sessions to return (most recent first)
            status: Filter by status ("active" or "completed")

        Returns:
            List of session metadata dicts
        """
        registry = self._load_registry()
        sessions = registry["sessions"]

        # Filter by status if specified
        if status:
            sessions = [s for s in sessions if s.get("status") == status]

        # Sort by start_time (most recent first)
        sessions.sort(key=lambda s: s.get("start_time", ""), reverse=True)

        # Apply limit if specified
        if limit:
            sessions = sessions[:limit]

        return sessions

    def get_most_recent_session(self) -> Optional[Dict[str, Any]]:
        """Get the most recently started session.

        Returns:
            Session metadata dict for most recent session, or None if no sessions
        """
        sessions = self.list_sessions(limit=1)
        return sessions[0] if sessions else None

    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists in the registry.

        Args:
            session_id: Session ID to check

        Returns:
            True if session exists, False otherwise
        """
        return self.get_session(session_id) is not None

    def delete_session(self, session_id: str) -> bool:
        """Delete a session from the registry.

        Note: This only removes the session from the registry, not from
        the vector database. Memory data remains in Qdrant.

        Args:
            session_id: Session to delete

        Returns:
            True if session was deleted, False if not found
        """
        registry = self._load_registry()

        initial_count = len(registry["sessions"])
        registry["sessions"] = [s for s in registry["sessions"] if s["session_id"] != session_id]

        if len(registry["sessions"]) < initial_count:
            self._save_registry(registry)
            logger.info(f"Deleted session from registry: {session_id}")
            return True

        return False


def format_session_list(sessions: List[Dict[str, Any]]) -> str:
    """Format session list for display in CLI.

    Args:
        sessions: List of session metadata dicts

    Returns:
        Formatted string for display
    """
    if not sessions:
        return "No sessions found."

    output = []
    output.append("\nAvailable Memory Sessions:")
    output.append("=" * 80)

    for session in sessions:
        session_id = session.get("session_id", "unknown")
        start_time = session.get("start_time", "unknown")
        status = session.get("status", "unknown")
        model = session.get("model", "N/A")
        config = session.get("config_path", "N/A")
        description = session.get("description", "")

        # Parse and format start time
        try:
            dt = datetime.fromisoformat(start_time)
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            time_str = start_time

        output.append(f"\nSession ID: {session_id}")
        output.append(f"  Status:  {status}")
        output.append(f"  Started: {time_str}")
        output.append(f"  Model:   {model}")
        if description:
            output.append(f"  Description: {description}")
        if config != "N/A":
            # Show just filename for brevity
            config_name = Path(config).name if config else "N/A"
            output.append(f"  Config:  {config_name}")

    output.append("\n" + "=" * 80)
    output.append('\nTo load a session, use: massgen --session-id <SESSION_ID> "Your question"')

    return "\n".join(output)
