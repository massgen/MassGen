# -*- coding: utf-8 -*-
"""
NLIP Token Tracker.

Tracks and manages NLIP token fields for state management, including
session IDs, context tokens, and conversation turns.
"""

import uuid
from typing import Any, Dict, Optional

from .schema import NLIPTokenField


class NLIPTokenTracker:
    """
    Tracks and manages NLIP token fields for state management.
    Handles session IDs, context tokens, and conversation turns.
    """

    def __init__(self):
        self._session_tokens: Dict[str, Dict[str, Any]] = {}
        self._context_tokens: Dict[str, str] = {}

    def create_session_token(
        self,
        agent_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> NLIPTokenField:
        """
        Create new session token for conversation.

        Args:
            agent_id: Optional agent identifier
            metadata: Optional session metadata

        Returns:
            New NLIP token field
        """
        session_id = self._generate_session_id(agent_id)
        context_token = str(uuid.uuid4())

        token = NLIPTokenField(
            session_id=session_id,
            context_token=context_token,
            state_token=None,
            conversation_turn=0,
        )

        # Store session info
        self._session_tokens[session_id] = {
            "context_token": context_token,
            "agent_id": agent_id,
            "metadata": metadata or {},
            "turn_count": 0,
        }

        # Map context token to session
        self._context_tokens[context_token] = session_id

        return token

    def increment_turn(self, token: NLIPTokenField) -> NLIPTokenField:
        """Increment conversation turn counter."""
        new_token = token.model_copy()
        new_token.conversation_turn += 1

        if token.session_id:
            session = self._session_tokens.get(token.session_id)
            if session:
                session["turn_count"] += 1

        return new_token

    def get_session_info(
        self,
        session_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Get session information."""
        return self._session_tokens.get(session_id)

    def get_session_from_context_token(
        self,
        context_token: str,
    ) -> Optional[str]:
        """Get session ID from context token."""
        return self._context_tokens.get(context_token)

    def _generate_session_id(self, agent_id: Optional[str] = None) -> str:
        """Generate unique session ID."""
        prefix = f"{agent_id}_" if agent_id else "nlip_"
        return f"{prefix}{uuid.uuid4()}"
