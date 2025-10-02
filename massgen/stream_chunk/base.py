# -*- coding: utf-8 -*-
"""
Base classes for stream chunks.
Provides abstract base class and enums for streaming responses.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class ChunkType(Enum):
    """Enumeration of chunk types for streaming responses."""

    # Text-based chunks
    CONTENT = "content"
    TOOL_CALLS = "tool_calls"
    COMPLETE_MESSAGE = "complete_message"
    COMPLETE_RESPONSE = "complete_response"
    DONE = "done"
    ERROR = "error"
    AGENT_STATUS = "agent_status"
    BACKEND_STATUS = "backend_status"

    # Reasoning chunks (OpenAI Response API)
    REASONING = "reasoning"
    REASONING_DONE = "reasoning_done"
    REASONING_SUMMARY = "reasoning_summary"
    REASONING_SUMMARY_DONE = "reasoning_summary_done"

    # MCP-related chunks
    MCP_STATUS = "mcp_status"

    # Multimodal chunks
    MEDIA = "media"
    MEDIA_PROGRESS = "media_progress"
    ATTACHMENT = "attachment"
    ATTACHMENT_COMPLETE = "attachment_complete"


@dataclass
class BaseStreamChunk(ABC):
    """
    Abstract base class for stream chunks.

    All stream chunks must inherit from this class and implement
    the required abstract methods for validation and serialization.

    Attributes:
        type: ChunkType enum value indicating the chunk type
        source: Optional source identifier (e.g., agent_id, backend name)
        timestamp: Optional timestamp when the chunk was created
        sequence_number: Optional sequence number for ordering chunks
    """

    type: ChunkType
    source: Optional[str] = None
    timestamp: Optional[float] = None
    sequence_number: Optional[int] = None

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert chunk to dictionary representation.

        Returns:
            Dictionary representation of the chunk, suitable for JSON serialization.
        """

    @abstractmethod
    def validate(self) -> bool:
        """
        Validate chunk data integrity.

        Returns:
            True if the chunk data is valid, False otherwise.
        """

    def __post_init__(self):
        """Post-initialization validation."""
        # Ensure type is a ChunkType enum
        if not isinstance(self.type, ChunkType):
            # Try to convert string to ChunkType
            if isinstance(self.type, str):
                try:
                    self.type = ChunkType(self.type)
                except ValueError:
                    raise ValueError(f"Invalid chunk type: {self.type}")
            else:
                raise TypeError(f"Chunk type must be ChunkType enum or string, got {type(self.type)}")
