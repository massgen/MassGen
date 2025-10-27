# -*- coding: utf-8 -*-
"""
MassGen Memory System

This module provides memory capabilities for MassGen agents, supporting both
short-term conversation memory and long-term persistent memory storage.

The memory system is designed to be:
- Asynchronous: All operations are async for optimal performance
- Pluggable: Easy to swap different storage backends
- Serializable: Support for saving and loading agent memory state
"""

from ._base import MemoryBase, PersistentMemoryBase
from ._conversation import ConversationMemory
from ._persistent import PersistentMemory

__all__ = [
    "MemoryBase",
    "PersistentMemoryBase",
    "ConversationMemory",
    "PersistentMemory",
]
