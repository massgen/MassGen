"""
MassGen Frontend Package

Provides user interface components for MassGen coordination display, logging, and monitoring.

TODO - Missing Frontend Features from v0.0.1:
- Web-based interface for remote coordination monitoring
- Enhanced terminal displays with better formatting
- Real-time metrics and performance monitoring
- Export capabilities for coordination logs
- Interactive configuration UI
- Dashboard for multi-session management
- Advanced visualization of agent interactions
"""

from .coordination_ui import CoordinationUI
from .displays import TerminalDisplay, SimpleDisplay
from .logging import RealtimeLogger

__all__ = ["CoordinationUI", "TerminalDisplay", "SimpleDisplay", "RealtimeLogger"]
