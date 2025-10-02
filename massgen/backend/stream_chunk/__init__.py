# -*- coding: utf-8 -*-
"""
Stream Chunk Module

This module provides classes for handling streaming responses from LLM backends.
It supports both text-based content (regular text, tool calls, reasoning) and
multimodal content (images, audio, video, documents).

Classes:
    BaseStreamChunk: Abstract base class for all stream chunks
    TextStreamChunk: Stream chunk for text-based content

Enums:
    ChunkType: Types of stream chunks

Data Classes:
    MediaMetadata: Metadata for media content
"""

from .base import BaseStreamChunk, ChunkType
from .text import TextStreamChunk

__all__ = [
    # Base classes
    "BaseStreamChunk",
    "ChunkType",
    # Text chunks
    "TextStreamChunk",
]

__version__ = "1.0.0"
