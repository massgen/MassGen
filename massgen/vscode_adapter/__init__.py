"""
VSCode Adapter for MassGen

This module provides a JSON-RPC server that allows VSCode extension
to communicate with MassGen's multi-agent system.
"""

from .server import VSCodeServer

__all__ = ["VSCodeServer"]
