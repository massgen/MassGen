"""
Web UI module for MassGen.

Provides an interactive web interface for multi-agent coordination.
"""

from .app import create_app
from .api import api_bp
from .websocket_handler import socketio

__all__ = ['create_app', 'api_bp', 'socketio']