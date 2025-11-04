# -*- coding: utf-8 -*-
"""
MassGen Session Management

This module provides session management capabilities for MassGen, including:
- Session state tracking and restoration
- Session registry for listing and managing sessions
- Conversation history and workspace persistence

The session system is designed to be:
- Unified: Single abstraction for session loading across interactive and CLI modes
- Extensible: Easy to add session forking, export, and other features
- Testable: Clean separation of concerns for unit testing
"""

from ._registry import SessionRegistry, format_session_list
from ._state import SessionState, restore_session

__all__ = [
    "SessionState",
    "restore_session",
    "SessionRegistry",
    "format_session_list",
]
