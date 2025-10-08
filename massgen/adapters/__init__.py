# -*- coding: utf-8 -*-
"""
External agent adapters for MassGen.

This package provides adapters for integrating various external agent
frameworks and systems into MassGen's orchestration system.
"""
from typing import Dict, Type

from .base import AgentAdapter

# Adapter registry maps framework names to adapter classes
adapter_registry: Dict[str, Type[AgentAdapter]] = {}

# Try to import AG2 adapter (optional dependency)
try:
    from .ag2_adapter import AG2Adapter

    adapter_registry["ag2"] = AG2Adapter
    adapter_registry["autogen"] = AG2Adapter  # Alias for backward compatibility
except ImportError:
    # AG2 not installed, skip registration
    pass


__all__ = [
    "AgentAdapter",
    "adapter_registry",
]
