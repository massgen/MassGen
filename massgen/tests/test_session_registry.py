# -*- coding: utf-8 -*-
"""Tests for session registry functionality."""

import json
import tempfile
from pathlib import Path

from massgen.session import SessionRegistry, format_session_list


class TestSessionRegistry:
    """Test SessionRegistry class."""

    def test_create_registry(self):
        """Test registry creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "sessions.json"
            SessionRegistry(str(registry_path))

            assert registry_path.exists()
            data = json.loads(registry_path.read_text())
            assert "sessions" in data
            assert data["sessions"] == []

    def test_register_session(self):
        """Test registering a new session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "sessions.json"
            registry = SessionRegistry(str(registry_path))

            session_id = "test_session_001"
            registry.register_session(
                session_id=session_id,
                config_path="/path/to/config.yaml",
                model="gpt-4o-mini",
                description="Test session",
            )

            # Verify session was registered
            session = registry.get_session(session_id)
            assert session is not None
            assert session["session_id"] == session_id
            assert session["config_path"] == "/path/to/config.yaml"
            assert session["model"] == "gpt-4o-mini"
            assert session["description"] == "Test session"
            assert session["status"] == "active"
            assert session["start_time"] is not None
            assert session["end_time"] is None

    def test_update_existing_session(self):
        """Test updating an existing session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "sessions.json"
            registry = SessionRegistry(str(registry_path))

            session_id = "test_session_002"

            # Register initial session
            registry.register_session(
                session_id=session_id,
                model="gpt-4o-mini",
            )

            # Update with new metadata
            registry.register_session(
                session_id=session_id,
                model="gpt-4o",
                description="Updated description",
            )

            # Verify update
            session = registry.get_session(session_id)
            assert session["model"] == "gpt-4o"
            assert session["description"] == "Updated description"

    def test_complete_session(self):
        """Test marking a session as completed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "sessions.json"
            registry = SessionRegistry(str(registry_path))

            session_id = "test_session_003"
            registry.register_session(session_id=session_id)

            # Complete the session
            registry.complete_session(session_id)

            # Verify completion
            session = registry.get_session(session_id)
            assert session["status"] == "completed"
            assert session["end_time"] is not None

    def test_list_sessions(self):
        """Test listing sessions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "sessions.json"
            registry = SessionRegistry(str(registry_path))

            # Register multiple sessions
            for i in range(5):
                registry.register_session(
                    session_id=f"session_{i:03d}",
                    model=f"model_{i}",
                )

            # List all sessions
            sessions = registry.list_sessions()
            assert len(sessions) == 5

            # List with limit
            sessions = registry.list_sessions(limit=3)
            assert len(sessions) == 3

    def test_list_sessions_by_status(self):
        """Test filtering sessions by status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "sessions.json"
            registry = SessionRegistry(str(registry_path))

            # Register and complete some sessions
            for i in range(3):
                session_id = f"session_{i:03d}"
                registry.register_session(session_id=session_id)
                if i < 2:
                    registry.complete_session(session_id)

            # List active sessions
            active = registry.list_sessions(status="active")
            assert len(active) == 1

            # List completed sessions
            completed = registry.list_sessions(status="completed")
            assert len(completed) == 2

    def test_session_exists(self):
        """Test checking if session exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "sessions.json"
            registry = SessionRegistry(str(registry_path))

            session_id = "test_session_004"
            assert not registry.session_exists(session_id)

            registry.register_session(session_id=session_id)
            assert registry.session_exists(session_id)

    def test_delete_session(self):
        """Test deleting a session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "sessions.json"
            registry = SessionRegistry(str(registry_path))

            session_id = "test_session_005"
            registry.register_session(session_id=session_id)

            assert registry.session_exists(session_id)

            # Delete session
            result = registry.delete_session(session_id)
            assert result is True
            assert not registry.session_exists(session_id)

            # Try deleting non-existent session
            result = registry.delete_session(session_id)
            assert result is False

    def test_format_session_list_empty(self):
        """Test formatting empty session list."""
        output = format_session_list([])
        assert "No sessions found" in output

    def test_format_session_list_with_sessions(self):
        """Test formatting session list with data."""
        sessions = [
            {
                "session_id": "session_001",
                "start_time": "2025-10-28T14:30:00",
                "status": "completed",
                "model": "gpt-4o-mini",
                "config_path": "/path/to/config.yaml",
                "description": "Test session",
            },
            {
                "session_id": "session_002",
                "start_time": "2025-10-28T15:00:00",
                "status": "active",
                "model": "gpt-4o",
                "config_path": "/path/to/other.yaml",
            },
        ]

        output = format_session_list(sessions)
        assert "Recent Memory Sessions" in output
        assert "session_001" in output
        assert "session_002" in output
        assert "completed" in output
        assert "active" in output
        assert "gpt-4o-mini" in output
        assert "gpt-4o" in output
        # Note: Description only shown with show_all=True
        assert "massgen --session-id" in output
