# -*- coding: utf-8 -*-
"""
Multimodal stream chunk implementation.
Handles media content including images, audio, video, and documents.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from .base import BaseStreamChunk, ChunkType


class MediaType(Enum):
    """Supported media types for multimodal content."""

    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    FILE = "file"
    DOCUMENT = "document"


class MediaEncoding(Enum):
    """Media encoding types."""

    BASE64 = "base64"
    URL = "url"
    FILE_PATH = "file_path"
    FILE_ID = "file_id"
    BINARY = "binary"


@dataclass
class MediaMetadata:
    """
    Metadata for media content.

    Attributes:
        mime_type: MIME type of the media (e.g., "image/jpeg", "audio/mp3")
        size_bytes: Size of the media in bytes
        width: Width in pixels (for images/video)
        height: Height in pixels (for images/video)
        duration_seconds: Duration in seconds (for audio/video)
        filename: Original filename
        checksum: Checksum for integrity verification (e.g., SHA-256)
    """

    mime_type: str
    size_bytes: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration_seconds: Optional[float] = None
    filename: Optional[str] = None
    checksum: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class MultimodalStreamChunk(BaseStreamChunk):
    """
    Stream chunk for multimodal content.

    This class handles streaming of media content including:
    - Images (JPEG, PNG, GIF, WebP)
    - Audio files (MP3, WAV, etc.)
    - Video files (MP4, WebM, etc.)
    - Documents (PDF, etc.)
    - Generic files

    Supports both complete media and streaming/chunked media delivery.

    Attributes:
        type: ChunkType enum value (typically MEDIA or MEDIA_PROGRESS)
        text_content: Optional text caption or description
        media_type: Type of media (IMAGE, AUDIO, VIDEO, etc.)
        media_encoding: How the media is encoded (BASE64, URL, etc.)
        media_data: The actual media data (URL string, base64 string, bytes, or file_id)
        media_metadata: Metadata about the media
        attachments: List of multiple attachments (for batch processing)
        progress_percentage: Progress percentage for large media (0-100)
        bytes_transferred: Number of bytes transferred so far
        total_bytes: Total bytes to transfer
        is_partial: True if this is part of a larger media stream
        chunk_index: Index of this chunk in the stream
        total_chunks: Total number of expected chunks
        source: Source identifier
        timestamp: When the chunk was created
        sequence_number: Sequence number for ordering
    """

    # Text content (optional caption/description)
    text_content: Optional[str] = None

    # Media fields
    media_type: Optional[MediaType] = None
    media_encoding: Optional[MediaEncoding] = None
    media_data: Optional[Any] = None  # URL, base64 string, bytes, or file_id
    media_metadata: Optional[MediaMetadata] = None

    # Multiple attachments support
    attachments: Optional[List[Dict[str, Any]]] = None

    # Progress tracking for large media
    progress_percentage: Optional[float] = None
    bytes_transferred: Optional[int] = None
    total_bytes: Optional[int] = None

    # Streaming support
    is_partial: bool = False
    chunk_index: Optional[int] = None
    total_chunks: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary with proper serialization.

        Handles enum conversion and special types like bytes and MediaMetadata.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        result = {}
        for key, value in self.__dict__.items():
            if value is not None:
                if key == "type" and isinstance(value, ChunkType):
                    result[key] = value.value
                elif isinstance(value, (MediaType, MediaEncoding)):
                    result[key] = value.value
                elif isinstance(value, MediaMetadata):
                    result[key] = value.to_dict()
                elif isinstance(value, bytes):
                    # Convert bytes to base64 for JSON serialization
                    import base64

                    result[key] = base64.b64encode(value).decode("utf-8")
                else:
                    result[key] = value
        return result

    def validate(self) -> bool:
        """
        Validate multimodal chunk integrity.

        Checks that required fields are present based on chunk type.

        Returns:
            True if chunk is valid, False otherwise.
        """
        if self.type == ChunkType.MEDIA:
            # Media chunks must have media_type, encoding, and data
            return self.media_type is not None and self.media_encoding is not None and self.media_data is not None

        elif self.type == ChunkType.MEDIA_PROGRESS:
            # Progress chunks must have progress_percentage
            return self.progress_percentage is not None

        elif self.type == ChunkType.ATTACHMENT:
            # Attachment chunks should have media data or attachments list
            return self.media_data is not None or self.attachments is not None

        elif self.type == ChunkType.ATTACHMENT_COMPLETE:
            # Attachment complete chunks are always valid
            return True

        # Unknown chunk type or no specific validation
        return True

    def is_complete(self) -> bool:
        """
        Check if media streaming is complete.

        For non-partial chunks, always returns True.
        For partial chunks, checks if this is the last chunk.

        Returns:
            True if media is complete, False if more chunks expected.
        """
        if not self.is_partial:
            return True

        if self.chunk_index is not None and self.total_chunks is not None:
            return self.chunk_index >= self.total_chunks - 1

        return False

    def get_progress(self) -> Optional[float]:
        """
        Get progress percentage.

        Calculates progress from either:
        - Explicit progress_percentage field
        - bytes_transferred / total_bytes
        - chunk_index / total_chunks

        Returns:
            Progress percentage (0-100) or None if not available.
        """
        if self.progress_percentage is not None:
            return self.progress_percentage

        if self.bytes_transferred is not None and self.total_bytes is not None and self.total_bytes > 0:
            return (self.bytes_transferred / self.total_bytes) * 100

        if self.chunk_index is not None and self.total_chunks is not None and self.total_chunks > 0:
            return ((self.chunk_index + 1) / self.total_chunks) * 100

        return None

    def __repr__(self) -> str:
        """String representation for debugging."""
        parts = [f"MultimodalStreamChunk(type={self.type.value}"]

        if self.media_type:
            parts.append(f"media_type={self.media_type.value}")

        if self.media_encoding:
            parts.append(f"encoding={self.media_encoding.value}")

        if self.text_content:
            parts.append(f"text='{self.text_content[:30]}...'")

        if self.is_partial:
            parts.append(f"partial={self.chunk_index}/{self.total_chunks}")

        progress = self.get_progress()
        if progress is not None:
            parts.append(f"progress={progress:.1f}%")

        if self.source:
            parts.append(f"source='{self.source}'")

        return ", ".join(parts) + ")"
