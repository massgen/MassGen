# -*- coding: utf-8 -*-
"""
External agent adapters for MassGen.

This package provides adapters for integrating various external agent
frameworks and systems into MassGen's orchestration system.
"""
from typing import Dict, Type

# Import framework-specific adapters
from .ag2_adapter import AG2Adapter
from .base import AgentAdapter

# Adapter registry maps framework names to adapter classes
adapter_registry: Dict[str, Type[AgentAdapter]] = {
    "ag2": AG2Adapter,
    "autogen": AG2Adapter,  # Alias for backward compatibility
}


__all__ = [
    "AgentAdapter",
    "adapter_registry",
]
