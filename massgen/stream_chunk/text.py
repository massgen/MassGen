# -*- coding: utf-8 -*-
"""
Text stream chunk implementation.
Handles text-based content including regular text, tool calls, and reasoning.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .base import BaseStreamChunk, ChunkType


@dataclass
class TextStreamChunk(BaseStreamChunk):
    """
    Stream chunk for text-based content.

    This class handles all text-based streaming content including:
    - Regular text content
    - Tool calls and function execution
    - Reasoning text and summaries
    - Status messages and errors
    - Complete messages and responses

    Attributes:
        type: ChunkType enum value
        content: Text content (for CONTENT, ERROR, STATUS chunks)
        tool_calls: List of tool call dictionaries (for TOOL_CALLS chunks)
        complete_message: Complete assistant message (for COMPLETE_MESSAGE chunks)
        response: Raw API response (for COMPLETE_RESPONSE chunks)
        error: Error message (for ERROR chunks)
        status: Status message (for STATUS chunks)
        reasoning_delta: Incremental reasoning text (for REASONING chunks)
        reasoning_text: Complete reasoning text (for REASONING_DONE chunks)
        reasoning_summary_delta: Incremental reasoning summary (for REASONING_SUMMARY chunks)
        reasoning_summary_text: Complete reasoning summary (for REASONING_SUMMARY_DONE chunks)
        item_id: Reasoning item identifier
        content_index: Reasoning content index
        summary_index: Reasoning summary index
        source: Source identifier (e.g., agent_id, backend name)
        timestamp: When the chunk was created
        sequence_number: Sequence number for ordering
    """

    # Text content
    content: Optional[str] = None

    # Tool-related fields
    tool_calls: Optional[List[Dict[str, Any]]] = None
    complete_message: Optional[Dict[str, Any]] = None
    response: Optional[Dict[str, Any]] = None

    # Status fields
    error: Optional[str] = None
    status: Optional[str] = None

    # Reasoning fields (OpenAI Response API)
    reasoning_delta: Optional[str] = None
    reasoning_text: Optional[str] = None
    reasoning_summary_delta: Optional[str] = None
    reasoning_summary_text: Optional[str] = None
    item_id: Optional[str] = None
    content_index: Optional[int] = None
    summary_index: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary, excluding None values.

        Returns:
            Dictionary with all non-None fields, with ChunkType converted to string.
        """
        result = {}
        for key, value in self.__dict__.items():
            if value is not None:
                if key == "type" and isinstance(value, ChunkType):
                    result[key] = value.value
                else:
                    result[key] = value
        return result

    def validate(self) -> bool:
        """
        Validate text chunk integrity.

        Checks that required fields are present based on chunk type.

        Returns:
            True if chunk is valid, False otherwise.
        """
        if self.type == ChunkType.CONTENT:
            # Content chunks should have content (can be empty string)
            return self.content is not None

        elif self.type == ChunkType.TOOL_CALLS:
            # Tool call chunks must have non-empty tool_calls list
            return self.tool_calls is not None and len(self.tool_calls) > 0

        elif self.type == ChunkType.COMPLETE_MESSAGE:
            # Complete message chunks must have complete_message dict
            return self.complete_message is not None

        elif self.type == ChunkType.COMPLETE_RESPONSE:
            # Complete response chunks must have response dict
            return self.response is not None

        elif self.type == ChunkType.ERROR:
            # Error chunks must have error message
            return self.error is not None or self.content is not None

        elif self.type == ChunkType.REASONING:
            # Reasoning chunks should have reasoning_delta
            return self.reasoning_delta is not None

        elif self.type == ChunkType.REASONING_DONE:
            # Reasoning done chunks should have reasoning_text
            return self.reasoning_text is not None

        elif self.type == ChunkType.REASONING_SUMMARY:
            # Reasoning summary chunks should have reasoning_summary_delta
            return self.reasoning_summary_delta is not None

        elif self.type == ChunkType.REASONING_SUMMARY_DONE:
            # Reasoning summary done chunks should have reasoning_summary_text
            return self.reasoning_summary_text is not None

        elif self.type in [ChunkType.AGENT_STATUS, ChunkType.BACKEND_STATUS, ChunkType.MCP_STATUS]:
            # Status chunks should have status or content
            return self.status is not None or self.content is not None

        elif self.type == ChunkType.DONE:
            # Done chunks are always valid
            return True

        # Unknown chunk type or no specific validation
        return True

    def __repr__(self) -> str:
        """String representation for debugging."""
        parts = [f"TextStreamChunk(type={self.type.value}"]

        if self.content:
            content_preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
            parts.append(f"content='{content_preview}'")

        if self.tool_calls:
            parts.append(f"tool_calls={len(self.tool_calls)} calls")

        if self.error:
            parts.append(f"error='{self.error}'")

        if self.status:
            parts.append(f"status='{self.status}'")

        if self.reasoning_delta:
            parts.append(f"reasoning_delta='{self.reasoning_delta[:30]}...'")

        if self.source:
            parts.append(f"source='{self.source}'")

        return ", ".join(parts) + ")"
