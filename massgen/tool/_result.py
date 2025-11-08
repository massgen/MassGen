# -*- coding: utf-8 -*-
"""Execution result class for tool outputs."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Union


def _generate_id() -> str:
    """Generate a unique identifier with timestamp."""
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


@dataclass
class ContentBlock:
    """Base class for content blocks."""

    block_type: str
    data: str


@dataclass
class TextContent(ContentBlock):
    """Text content block."""

    def __init__(self, data: str):
        super().__init__(block_type="text", data=data)


@dataclass
class ImageContent(ContentBlock):
    """Image content block."""

    def __init__(self, data: str):
        super().__init__(block_type="image", data=data)


@dataclass
class AudioContent(ContentBlock):
    """Audio content block."""

    def __init__(self, data: str):
        super().__init__(block_type="audio", data=data)


@dataclass
class ExecutionResult:
    """Result container for tool execution outputs."""

    output_blocks: List[Union[TextContent, ImageContent, AudioContent]]
    """The execution output blocks from the tool."""

    meta_info: Optional[dict] = None
    """Additional metadata accessible within the system."""

    is_streaming: bool = False
    """Indicates if the output is being streamed."""

    is_final: bool = True
    """Indicates if this is the final result in a stream."""

    is_log: bool = False
    """Indicates if this result is for logging purposes only."""

    was_interrupted: bool = False
    """Indicates if the execution was interrupted."""

    result_id: str = field(default_factory=_generate_id)
    """Unique identifier for this result."""
