# -*- coding: utf-8 -*-
"""
NLIP State Manager.

Manages state for NLIP conversations and sessions, including context tokens,
session tracking, and state persistence.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from .schema import NLIPMessage


class NLIPStateManager:
    """
    Manages state for NLIP conversations and sessions.
    Handles context tokens, session tracking, and state persistence.
    """

    def __init__(self, cleanup_interval: int = 3600):
        """
        Initialize state manager.

        Args:
            cleanup_interval: Interval in seconds for cleaning up expired sessions
        """
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._context_tokens: Dict[str, Any] = {}
        self._cleanup_interval = cleanup_interval
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start background cleanup task."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self):
        """Stop background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def create_session(
        self,
        session_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Create new conversation session."""
        self._sessions[session_id] = {
            "created_at": datetime.utcnow(),
            "last_activity": datetime.utcnow(),
            "messages": [],
            "metadata": metadata or {},
            "state": {},
        }

    async def update_session(
        self,
        session_id: str,
        message: NLIPMessage,
    ) -> None:
        """Update session with new message."""
        if session_id not in self._sessions:
            await self.create_session(session_id)

        session = self._sessions[session_id]
        session["messages"].append(message)
        session["last_activity"] = datetime.utcnow()

    async def get_session_context(
        self,
        session_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Get context for a session."""
        return self._sessions.get(session_id)

    async def store_context_token(
        self,
        token: str,
        context: Dict[str, Any],
    ) -> None:
        """Store context associated with a token."""
        self._context_tokens[token] = {
            "context": context,
            "created_at": datetime.utcnow(),
        }

    async def retrieve_context_token(
        self,
        token: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve context for a token."""
        token_data = self._context_tokens.get(token)
        return token_data["context"] if token_data else None

    async def cleanup_expired_sessions(
        self,
        max_age_hours: int = 24,
    ) -> int:
        """Clean up sessions older than max_age_hours."""
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        expired = []

        for session_id, session_data in self._sessions.items():
            if session_data["last_activity"] < cutoff:
                expired.append(session_id)

        for session_id in expired:
            del self._sessions[session_id]

        return len(expired)

    async def _cleanup_loop(self):
        """Background task to cleanup expired sessions."""
        while True:
            await asyncio.sleep(self._cleanup_interval)
            await self.cleanup_expired_sessions()
