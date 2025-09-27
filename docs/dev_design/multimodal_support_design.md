# MassGen Multimodal Support Design Document

## 1. Architecture Overview

### 1.1 StreamChunk Refactoring
Move StreamChunk from backend to a dedicated module for better separation of concerns.

**New Directory Structure:**
```
massgen/
├── stream_chunk/
│   ├── __init__.py
│   ├── base.py          # Base StreamChunk class
│   ├── text.py          # TextStreamChunk implementation
│   └── multimodal.py    # MultimodalStreamChunk implementation
```

## 2. StreamChunk Base Class Design

### 2.1 Base StreamChunk Class

```python
# massgen/stream_chunk/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

class ChunkType(Enum):
    """Enumeration of chunk types."""
    # Text-based chunks
    CONTENT = "content"
    TOOL_CALLS = "tool_calls"
    COMPLETE_MESSAGE = "complete_message"
    COMPLETE_RESPONSE = "complete_response"
    DONE = "done"
    ERROR = "error"
    AGENT_STATUS = "agent_status"
    REASONING = "reasoning"
    REASONING_DONE = "reasoning_done"

    # Multimodal chunks
    MEDIA = "media"
    MEDIA_PROGRESS = "media_progress"
    ATTACHMENT = "attachment"
    ATTACHMENT_COMPLETE = "attachment_complete"

@dataclass
class BaseStreamChunk(ABC):
    """Abstract base class for stream chunks."""

    type: ChunkType
    source: Optional[str] = None  # Source identifier
    timestamp: Optional[float] = None  # When the chunk was created
    sequence_number: Optional[int] = None  # For ordering chunks

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Convert chunk to dictionary representation."""
        pass

    @abstractmethod
    def validate(self) -> bool:
        """Validate chunk data integrity."""
        pass
```

### 2.2 TextStreamChunk Class

```python
# massgen/stream_chunk/text.py
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from .base import BaseStreamChunk, ChunkType

@dataclass
class TextStreamChunk(BaseStreamChunk):
    """Stream chunk for text-based content."""

    # Text content
    content: Optional[str] = None

    # Tool-related fields
    tool_calls: Optional[List[Dict[str, Any]]] = None
    complete_message: Optional[Dict[str, Any]] = None
    response: Optional[Dict[str, Any]] = None

    # Status fields
    error: Optional[str] = None
    status: Optional[str] = None

    # Reasoning fields
    reasoning_delta: Optional[str] = None
    reasoning_text: Optional[str] = None
    reasoning_summary_delta: Optional[str] = None
    reasoning_summary_text: Optional[str] = None
    item_id: Optional[str] = None
    content_index: Optional[int] = None
    summary_index: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        return {k: v for k, v in self.__dict__.items() if v is not None}

    def validate(self) -> bool:
        """Validate text chunk integrity."""
        if self.type == ChunkType.CONTENT:
            return self.content is not None
        elif self.type == ChunkType.TOOL_CALLS:
            return self.tool_calls is not None and len(self.tool_calls) > 0
        elif self.type == ChunkType.ERROR:
            return self.error is not None
        return True
```

### 2.3 MultimodalStreamChunk Class

```python
# massgen/stream_chunk/multimodal.py
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional
from .base import BaseStreamChunk, ChunkType

class MediaType(Enum):
    """Supported media types."""
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
    BINARY = "binary"

@dataclass
class MediaMetadata:
    """Metadata for media content."""
    mime_type: str
    size_bytes: Optional[int] = None
    width: Optional[int] = None  # For images/video
    height: Optional[int] = None  # For images/video
    duration_seconds: Optional[float] = None  # For audio/video
    filename: Optional[str] = None
    checksum: Optional[str] = None

@dataclass
class MultimodalStreamChunk(BaseStreamChunk):
    """Stream chunk for multimodal content."""

    # Text content (optional caption/description)
    text_content: Optional[str] = None

    # Media fields
    media_type: Optional[MediaType] = None
    media_encoding: Optional[MediaEncoding] = None
    media_data: Optional[Any] = None  # URL, base64 string, or bytes
    media_metadata: Optional[MediaMetadata] = None

    # Multiple attachments support
    attachments: Optional[List[Dict[str, Any]]] = None

    # Progress tracking for large media
    progress_percentage: Optional[float] = None
    bytes_transferred: Optional[int] = None
    total_bytes: Optional[int] = None

    # Streaming support
    is_partial: bool = False  # True if this is part of a larger media stream
    chunk_index: Optional[int] = None  # For ordered streaming
    total_chunks: Optional[int] = None  # Total expected chunks

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with proper serialization."""
        result = {}
        for k, v in self.__dict__.items():
            if v is not None:
                if isinstance(v, Enum):
                    result[k] = v.value
                elif isinstance(v, MediaMetadata):
                    result[k] = v.__dict__
                elif isinstance(v, bytes):
                    # Convert bytes to base64 for JSON serialization
                    import base64
                    result[k] = base64.b64encode(v).decode('utf-8')
                else:
                    result[k] = v
        return result

    def validate(self) -> bool:
        """Validate multimodal chunk integrity."""
        if self.type == ChunkType.MEDIA:
            return (self.media_type is not None and
                    self.media_encoding is not None and
                    self.media_data is not None)
        elif self.type == ChunkType.MEDIA_PROGRESS:
            return self.progress_percentage is not None
        return True

    def is_complete(self) -> bool:
        """Check if media streaming is complete."""
        if not self.is_partial:
            return True
        return (self.chunk_index is not None and
                self.total_chunks is not None and
                self.chunk_index >= self.total_chunks - 1)
```

## 3. Message Formatter Enhancement

### 3.1 Enhanced MessageFormatter

```python
# massgen/formatter/message_formatter.py
class MessageFormatter:
    """Enhanced message formatter with multimodal support."""

    @staticmethod
    def to_chat_completions_format(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert messages for Chat Completions API with multimodal support."""
        converted_messages = []

        for message in messages:
            converted_msg = dict(message)

            # Handle multimodal content
            if "content" in message:
                converted_msg["content"] = MessageFormatter._convert_content_to_openai(
                    message["content"]
                )

            # Existing tool_calls handling...
            converted_messages.append(converted_msg)

        return converted_messages

    @staticmethod
    def _convert_content_to_openai(content: Any) -> Any:
        """Convert content to OpenAI multimodal format."""
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            openai_content = []
            for item in content:
                if item.get("type") == "text":
                    openai_content.append({
                        "type": "text",
                        "text": item.get("text", "")
                    })
                elif item.get("type") == "image":
                    # Handle different image formats
                    if "url" in item:
                        openai_content.append({
                            "type": "image_url",
                            "image_url": {"url": item["url"]}
                        })
                    elif "base64" in item:
                        openai_content.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{item.get('mime_type', 'image/jpeg')};base64,{item['base64']}"
                            }
                        })
                elif item.get("type") == "audio":
                    # OpenAI audio support (future)
                    openai_content.append({
                        "type": "audio",
                        "audio": item.get("data", {})
                    })
            return openai_content

        return content

    @staticmethod
    def to_claude_format(messages: List[Dict[str, Any]]) -> tuple:
        """Convert messages to Claude format with multimodal support."""
        converted_messages = []
        system_message = ""

        for message in messages:
            if message.get("role") == "system":
                system_message = message.get("content", "")
            elif message.get("role") in ["user", "assistant"]:
                converted_msg = {"role": message["role"]}

                # Handle multimodal content for Claude
                if "content" in message:
                    converted_msg["content"] = MessageFormatter._convert_content_to_claude(
                        message["content"]
                    )

                converted_messages.append(converted_msg)

        return converted_messages, system_message

    @staticmethod
    def _convert_content_to_claude(content: Any) -> Any:
        """Convert content to Claude multimodal format."""
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            claude_content = []
            for item in content:
                if item.get("type") == "text":
                    claude_content.append({
                        "type": "text",
                        "text": item.get("text", "")
                    })
                elif item.get("type") == "image":
                    if "base64" in item:
                        claude_content.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": item.get("mime_type", "image/jpeg"),
                                "data": item["base64"]
                            }
                        })
                    elif "url" in item:
                        # Claude doesn't support direct URLs, need to fetch and convert
                        # This would be handled by a utility function
                        pass
            return claude_content

        return content

    @staticmethod
    def to_gemini_format(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert messages to Gemini format with multimodal support."""
        converted_messages = []

        for message in messages:
            role = message.get("role", "")
            if role == "assistant":
                role = "model"

            gemini_msg = {"role": role, "parts": []}

            # Convert content to Gemini parts format
            if "content" in message:
                gemini_msg["parts"] = MessageFormatter._convert_content_to_gemini(
                    message["content"]
                )

            converted_messages.append(gemini_msg)

        return converted_messages

    @staticmethod
    def _convert_content_to_gemini(content: Any) -> List[Dict[str, Any]]:
        """Convert content to Gemini parts format."""
        if isinstance(content, str):
            return [{"text": content}]

        if isinstance(content, list):
            gemini_parts = []
            for item in content:
                if item.get("type") == "text":
                    gemini_parts.append({"text": item.get("text", "")})
                elif item.get("type") == "image":
                    if "base64" in item:
                        gemini_parts.append({
                            "inline_data": {
                                "mime_type": item.get("mime_type", "image/jpeg"),
                                "data": item["base64"]
                            }
                        })
            return gemini_parts

        return [{"text": str(content)}]
```

## 4. Backend Support Implementation

### 4.1 Base Backend Enhancement

```python
# massgen/backend/base.py
from typing import List, Optional
from ..stream_chunk import BaseStreamChunk, TextStreamChunk, MultimodalStreamChunk

class LLMBackend(ABC):
    """Enhanced base backend with multimodal support."""

    def supports_multimodal_input(self) -> Dict[str, bool]:
        """Return supported input modalities."""
        return {
            "image": False,
            "audio": False,
            "video": False,
            "document": False
        }

    def supports_multimodal_output(self) -> Dict[str, bool]:
        """Return supported output modalities."""
        return {
            "image": False,
            "audio": False,
            "video": False,
            "document": False
        }

    def get_max_media_size(self, media_type: str) -> Optional[int]:
        """Get maximum size in bytes for a media type."""
        return None  # Override in subclasses

    def validate_media_input(self, media_type: str, media_data: Any) -> bool:
        """Validate media input before sending to API."""
        # Default implementation
        supported = self.supports_multimodal_input()
        if not supported.get(media_type, False):
            return False

        max_size = self.get_max_media_size(media_type)
        if max_size and hasattr(media_data, '__len__'):
            return len(media_data) <= max_size

        return True
```

### 4.2 OpenAI Backend Enhancement

```python
# massgen/backend/chat_completions.py
class ChatCompletionsBackend(MCPBackend):
    """OpenAI Chat Completions backend with multimodal support."""

    def supports_multimodal_input(self) -> Dict[str, bool]:
        """OpenAI supports image input."""
        return {
            "image": True,  # GPT-4V models
            "audio": False,  # Coming soon
            "video": False,
            "document": False
        }

    def get_max_media_size(self, media_type: str) -> Optional[int]:
        """OpenAI image size limits."""
        if media_type == "image":
            return 20 * 1024 * 1024  # 20MB
        return None

    def _process_stream_chunk(self, chunk, agent_id) -> BaseStreamChunk:
        """Process chunks with multimodal support."""
        # Check for image generation responses
        if hasattr(chunk, 'choices') and chunk.choices:
            choice = chunk.choices[0]
            if hasattr(choice, 'message') and hasattr(choice.message, 'content'):
                content = choice.message.content

                # Check if content contains image data
                if isinstance(content, list):
                    for item in content:
                        if item.get('type') == 'image_url':
                            return MultimodalStreamChunk(
                                type=ChunkType.MEDIA,
                                media_type=MediaType.IMAGE,
                                media_encoding=MediaEncoding.URL,
                                media_data=item['image_url']['url'],
                                text_content="Generated image"
                            )

        # Fallback to text processing
        return TextStreamChunk(
            type=ChunkType.CONTENT,
            content=self._extract_text_content(chunk)
        )
```

### 4.3 Claude Backend Enhancement

```python
# massgen/backend/claude.py
class ClaudeBackend(MCPBackend):
    """Claude backend with multimodal support."""

    def supports_multimodal_input(self) -> Dict[str, bool]:
        """Claude supports image input."""
        return {
            "image": True,  # Claude 3 models
            "audio": False,
            "video": False,
            "document": True  # PDF support
        }

    def get_max_media_size(self, media_type: str) -> Optional[int]:
        """Claude media size limits."""
        if media_type == "image":
            return 5 * 1024 * 1024  # 5MB per image
        elif media_type == "document":
            return 10 * 1024 * 1024  # 10MB for PDFs
        return None

    async def _handle_multimodal_response(self, response) -> AsyncGenerator[BaseStreamChunk, None]:
        """Handle multimodal responses from Claude."""
        async for event in response:
            if event.type == "content_block_start":
                if hasattr(event.content_block, 'type'):
                    if event.content_block.type == "image":
                        yield MultimodalStreamChunk(
                            type=ChunkType.MEDIA,
                            media_type=MediaType.IMAGE,
                            is_partial=True,
                            chunk_index=0
                        )
            elif event.type == "content_block_delta":
                # Handle streaming image data
                if hasattr(event.delta, 'type') and event.delta.type == "image_delta":
                    yield MultimodalStreamChunk(
                        type=ChunkType.MEDIA,
                        media_type=MediaType.IMAGE,
                        media_data=event.delta.data,
                        is_partial=True
                    )
```

### 4.4 Response API Backend Enhancement

```python
# massgen/backend/response.py
class ResponseBackend(MCPBackend):
    """Response API backend with multimodal support."""

    def _process_stream_chunk(self, chunk, agent_id) -> BaseStreamChunk:
        """Enhanced chunk processing for multimodal content."""

        if not hasattr(chunk, 'type'):
            return TextStreamChunk(type=ChunkType.CONTENT, content="")

        chunk_type = chunk.type

        # Handle multimodal chunks
        if chunk_type == "response.media.start":
            return MultimodalStreamChunk(
                type=ChunkType.MEDIA,
                media_type=MediaType[chunk.media_type.upper()],
                text_content=f"📎 Starting {chunk.media_type} processing..."
            )

        elif chunk_type == "response.media.delta":
            return MultimodalStreamChunk(
                type=ChunkType.MEDIA,
                media_type=MediaType[chunk.media_type.upper()],
                media_data=chunk.data,
                is_partial=True,
                chunk_index=chunk.index,
                total_chunks=chunk.total
            )

        elif chunk_type == "response.media.complete":
            metadata = MediaMetadata(
                mime_type=chunk.mime_type,
                size_bytes=chunk.size,
                filename=chunk.filename
            )
            if hasattr(chunk, 'width'):
                metadata.width = chunk.width
                metadata.height = chunk.height

            return MultimodalStreamChunk(
                type=ChunkType.MEDIA,
                media_type=MediaType[chunk.media_type.upper()],
                media_encoding=MediaEncoding.BASE64 if chunk.encoding == "base64" else MediaEncoding.URL,
                media_data=chunk.data,
                media_metadata=metadata,
                text_content=f"✅ {chunk.media_type.capitalize()} ready"
            )

        # Existing text chunk handling
        return super()._process_stream_chunk(chunk, agent_id)
```

### 4.5 Gemini Backend Enhancement

```python
# massgen/backend/gemini.py
class GeminiBackend(MCPBackend):
    """Gemini backend with multimodal support."""

    def supports_multimodal_input(self) -> Dict[str, bool]:
        """Gemini supports multiple input modalities."""
        return {
            "image": True,
            "audio": True,
            "video": True,
            "document": True
        }

    def get_max_media_size(self, media_type: str) -> Optional[int]:
        """Gemini media size limits."""
        limits = {
            "image": 20 * 1024 * 1024,  # 20MB
            "audio": 25 * 1024 * 1024,  # 25MB
            "video": 100 * 1024 * 1024,  # 100MB
            "document": 30 * 1024 * 1024  # 30MB
        }
        return limits.get(media_type)
```

### 4.6 Azure OpenAI Backend Enhancement

```python
# massgen/backend/azure_openai.py
class AzureOpenAIBackend(ChatCompletionsBackend):
    """Azure OpenAI backend inherits multimodal support from ChatCompletions."""

    def supports_multimodal_input(self) -> Dict[str, bool]:
        """Azure OpenAI supports image input for GPT-4V deployments."""
        # Check if deployment supports vision
        if "vision" in self.deployment_name.lower() or "gpt-4v" in self.deployment_name.lower():
            return {
                "image": True,
                "audio": False,
                "video": False,
                "document": False
            }
        return super().supports_multimodal_input()
```

### 4.7 Grok Backend Enhancement

```python
# massgen/backend/grok.py
class GrokBackend(ChatCompletionsBackend):
    """Grok backend with potential multimodal support."""

    def supports_multimodal_input(self) -> Dict[str, bool]:
        """Grok multimodal capabilities."""
        # Update based on Grok's actual capabilities
        return {
            "image": False,  # Update when available
            "audio": False,
            "video": False,
            "document": False
        }
```

### 4.8 CLI Base Backend Enhancement

```python
# massgen/backend/cli_base.py
class CLIBasedBackend(LLMBackend):
    """Base class for CLI-based backends."""

    def supports_multimodal_input(self) -> Dict[str, bool]:
        """CLI backends typically don't support multimodal directly."""
        return {
            "image": False,
            "audio": False,
            "video": False,
            "document": False
        }
```

### 4.9 Claude Code Backend Enhancement

```python
# massgen/backend/claude_code.py
class ClaudeCodeBackend(CLIBasedBackend):
    """Claude Code backend with file system support but no direct multimodal."""

    def supports_multimodal_input(self) -> Dict[str, bool]:
        """Claude Code can read images from filesystem."""
        return {
            "image": True,  # Can read image files
            "audio": False,
            "video": False,
            "document": True  # Can read documents
        }

    def get_max_media_size(self, media_type: str) -> Optional[int]:
        """File size limits for Claude Code."""
        if media_type in ["image", "document"]:
            return 50 * 1024 * 1024  # 50MB file limit
        return None
```

## 5. Implementation Phases

### Phase 1: Basic Image Support (Week 1-2)

**Objectives:**
- Implement StreamChunk refactoring
- Add image support to MessageFormatter
- Enable image input/output for Claude and OpenAI

**Tasks:**
1. Create `stream_chunk` module structure
2. Implement `BaseStreamChunk`, `TextStreamChunk`, `MultimodalStreamChunk`
3. Update MessageFormatter with image conversion methods
4. Modify Claude backend to handle image inputs
5. Modify OpenAI backend to handle image inputs
6. Add unit tests for image handling
7. Create example scripts for image input/output

### Phase 2: Full Multimodal Support (Week 3-4)

**Objectives:**
- Add audio/video/document support
- Implement media type detection and validation
- Enable streaming for large media files

**Tasks:**
1. Extend `MultimodalStreamChunk` for audio/video
2. Add media type detection utilities
3. Implement streaming protocol for large files
4. Add progress tracking for uploads/downloads
5. Implement media validation and size checks
6. Add support for document types (PDF, etc.)
7. Create comprehensive test suite

**Success Criteria:**
- Support for all major media types
- Efficient streaming for large files
- Robust validation and error handling

### Phase 3: Advanced Features (Week 5-6)

**Objectives:**
- Multimodal backend support (image generation, TTS, STT)
- Media transformation and processing
- Performance optimization

**Tasks:**
1. Implement image generation backend (DALL-E, Stable Diffusion)
2. Add audio generation/transcription tools
3. Implement media conversion utilities
4. Add caching layer for media content
5. Optimize streaming performance
6. Add media preview generation
7. Implement batch processing for multiple media items

**Success Criteria:**
- Seamless tool integration for media generation
- Efficient media processing pipeline
- Optimized performance for production use

## 6. Case Study YAML Files

### 6.1 Multi-Agent Image Generation

```yaml
# MassGen Configuration: Multimodal Image Generation Team
# Usage:
#   uv run python -m massgen.cli --config configs/multimodal/image_generation_team.yaml "create a futuristic cityscape"

agents:
  - id: "prompt_engineer"
    backend:
      type: "claude"
      model: "claude-3-5-sonnet"
      temperature: 0.7
      max_tokens: 2000
    system_message: |
      You are a prompt engineering specialist. Your job is to:
      1. Take user requirements and create detailed image generation prompts
      2. Optimize prompts for specific image generation models
      3. Suggest variations and improvements based on model capabilities

  - id: "dalle_artist"
    backend:
      type: "openai"
      model: "gpt-4o"
      tools:
        - name: "dalle_generate"
          type: "image_generation"
          config:
            model: "dall-e-3"
            size: "1024x1024"
            quality: "hd"
            style: "vivid"
    system_message: |
      You are an image generation specialist using DALL-E 3. Your job is to:
      1. Generate images based on prompts from the prompt engineer
      2. Create variations of successful images
      3. Provide feedback on generation quality and suggest improvements

  - id: "sd_artist"
    backend:
      type: "openai"
      model: "gpt-4"
      tools:
        - name: "stable_diffusion"
          type: "image_generation"
          config:
            model: "sdxl-turbo"
            steps: 25
            cfg_scale: 7.5
            sampler: "DPM++ 2M Karras"
    system_message: |
      You are an image generation specialist using Stable Diffusion. Your job is to:
      1. Generate images using Stable Diffusion XL
      2. Apply specific artistic styles and techniques
      3. Create photorealistic variations when needed

  - id: "art_director"
    backend:
      type: "claude"
      model: "claude-3-opus"
      multimodal_capabilities:
        input: ["image"]
        output: ["text"]
    system_message: |
      You are an art director with expertise in visual design. Your job is to:
      1. Review all generated images for quality and aesthetics
      2. Provide artistic feedback and direction
      3. Select the best outputs based on composition, color, and style
      4. Suggest refinements and combinations for improved results

ui:
  display_type: "rich_terminal"
  logging_enabled: true
  multimodal_display:
    images: "inline"  # Display images inline in terminal
    save_outputs: true  # Save generated images to disk
```

### 6.2 Multimodal Document Analysis

```yaml
# MassGen Configuration: Document Analysis with Vision
# Usage:
#   uv run python -m massgen.cli --config configs/multimodal/document_analysis.yaml "analyze the uploaded document"

agents:
  - id: "vision_analyst"
    backend:
      type: "gemini"
      model: "gemini-2.5-pro"
      multimodal_capabilities:
        input: ["image", "document", "text"]
        output: ["text"]
    system_message: |
      You are a document analysis specialist with vision capabilities. Your job is to:
      1. Extract text from images and scanned documents
      2. Analyze document layout and structure
      3. Identify tables, charts, and diagrams
      4. Provide detailed content summaries

  - id: "data_extractor"
    backend:
      type: "openai"
      model: "gpt-4o"
      tools:
        - name: "ocr_tool"
          type: "text_extraction"
          config:
            languages: ["en", "es", "fr", "de", "zh", "ja"]
            preserve_formatting: true
    system_message: |
      You are a data extraction specialist. Your job is to:
      1. Extract structured data from documents
      2. Convert tables to CSV or JSON format
      3. Parse forms and extract field values
      4. Maintain data accuracy and completeness

ui:
  display_type: "rich_terminal"
  logging_enabled: true
```

## 7. Testing Strategy

### 7.1 Unit Tests
```python
# tests/test_multimodal_chunks.py
import pytest
from massgen.stream_chunk import MultimodalStreamChunk, MediaType, MediaEncoding

def test_image_chunk_creation():
    """Test creating an image chunk."""
    chunk = MultimodalStreamChunk(
        type=ChunkType.MEDIA,
        media_type=MediaType.IMAGE,
        media_encoding=MediaEncoding.BASE64,
        media_data="base64_encoded_data_here"
    )
    assert chunk.validate()
    assert chunk.media_type == MediaType.IMAGE

def test_streaming_chunks():
    """Test streaming media chunks."""
    chunks = []
    for i in range(5):
        chunk = MultimodalStreamChunk(
            type=ChunkType.MEDIA,
            media_type=MediaType.VIDEO,
            is_partial=True,
            chunk_index=i,
            total_chunks=5
        )
        chunks.append(chunk)

    assert not chunks[0].is_complete()
    assert chunks[-1].is_complete()
```

### 7.2 Integration Tests
```python
# tests/test_multimodal_backends.py
import pytest
from massgen.backend import ChatCompletionsBackend, ClaudeBackend

@pytest.mark.asyncio
async def test_openai_image_input():
    """Test sending image to OpenAI."""
    backend = ChatCompletionsBackend(model="gpt-4-vision-preview")

    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": "What's in this image?"},
            {"type": "image", "url": "https://example.com/image.jpg"}
        ]
    }]

    response = await backend.stream_with_tools(messages, [])
    chunks = []
    async for chunk in response:
        chunks.append(chunk)

    assert len(chunks) > 0
    assert any(isinstance(c, TextStreamChunk) for c in chunks)

@pytest.mark.asyncio
async def test_claude_image_base64():
    """Test sending base64 image to Claude."""
    backend = ClaudeBackend(model="claude-3-opus")

    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": "Describe this image"},
            {
                "type": "image",
                "base64": "iVBORw0KGgoAAAANS...",
                "mime_type": "image/png"
            }
        ]
    }]

    response = await backend.stream_with_tools(messages, [])
    # Verify response handling
```

## 8. Migration Guide

### 8.1 For Existing Code
```python
# Before
from massgen.backend.base import StreamChunk

chunk = StreamChunk(type="content", content="Hello")

# After
from massgen.stream_chunk import TextStreamChunk, ChunkType

chunk = TextStreamChunk(type=ChunkType.CONTENT, content="Hello")
```

### 8.2 For Backend Implementations
```python
# Before
def _process_stream_chunk(self, chunk, agent_id) -> StreamChunk:
    return StreamChunk(type="content", content=chunk.text)

# After
def _process_stream_chunk(self, chunk, agent_id) -> BaseStreamChunk:
    if hasattr(chunk, 'image_url'):
        return MultimodalStreamChunk(
            type=ChunkType.MEDIA,
            media_type=MediaType.IMAGE,
            media_encoding=MediaEncoding.URL,
            media_data=chunk.image_url
        )
    return TextStreamChunk(type=ChunkType.CONTENT, content=chunk.text)
```

## 9. Performance Considerations

### 9.1 Memory Management
- Stream large media files instead of loading into memory
- Implement chunk-based processing for video/audio
- Use memory-mapped files for large documents

### 9.2 Caching Strategy
- Cache converted media formats
- Implement LRU cache for frequently accessed media
- Store thumbnails/previews separately

### 9.3 Network Optimization
- Compress media before transmission when possible
- Use CDN for media storage and delivery
- Implement retry logic with exponential backoff

This design document provides a comprehensive roadmap for implementing multimodal support in MassGen, with clear separation of concerns, extensibility for future media types, and backward compatibility with existing text-only workflows.