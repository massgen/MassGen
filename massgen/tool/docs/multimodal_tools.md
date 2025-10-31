# Multimodal Tools Guide

## Overview

MassGen provides a comprehensive suite of multimodal understanding tools that enable AI agents to analyze and understand various media types including videos, images, audio files, and documents. These tools leverage OpenAI's advanced multimodal APIs (gpt-4.1 and transcription services) to provide intelligent content analysis capabilities.

## Tool Categories

Multimodal tools are organized into four main categories:

- **Video Understanding**: Extract key frames and analyze video content
- **Audio Understanding**: Transcribe and analyze audio files
- **Image Understanding**: Analyze and describe image content
- **File Understanding**: Process and understand documents (PDF, DOCX, PPTX, XLSX)

## Video Understanding Tool

### understand_video

**What it does**: Extracts key frames from video files and uses OpenAI's gpt-4.1 API to analyze and understand video content. The tool samples frames evenly across the video timeline to provide comprehensive coverage of the video's content.

**Why use it**: Allows agents to understand video content without manually watching videos. Perfect for summarizing videos, extracting key information, analyzing tutorial steps, or answering specific questions about video content.

**Location**: `massgen.tool._multimodal_tools.understand_video`

#### Parameters

- `video_path` (required): Path to the video file
  - Relative path: Resolved relative to workspace
  - Absolute path: Must be within allowed directories
  - Supported formats: MP4, AVI, MOV, MKV, FLV, WMV, WEBM, M4V, MPG, MPEG
- `prompt` (optional): Question or instruction about the video (default: "What's happening in this video? Please describe the content, actions, and any important details you observe across these frames.")
- `num_frames` (optional): Number of key frames to extract (default: 8)
  - Higher values provide more detail but increase API costs
  - Recommended range: 4-16 frames
- `model` (optional): OpenAI model to use (default: "gpt-4.1")
- `allowed_paths` (optional): List of allowed base paths for validation

#### Returns

ExecutionResult containing:
- `success`: Whether operation succeeded
- `operation`: "understand_video"
- `video_path`: Path to the analyzed video
- `num_frames_extracted`: Number of frames extracted
- `prompt`: The prompt used
- `model`: Model used for analysis
- `response`: The model's understanding/description of the video

#### Security Features

- Path validation to ensure access only to allowed directories
- Requires valid OpenAI API key
- File existence and format validation
- Automatic cleanup of video capture resources

#### Dependencies

Requires `opencv-python` package:
```bash
pip install opencv-python>=4.12.0.88
```

#### Examples

**Basic Video Analysis**:

```python
from massgen.tool._multimodal_tools import understand_video

# Analyze a video with default prompt
result = await understand_video(video_path="demo.mp4")

# Output includes detailed description of the video
print(result.output_blocks[0].data)
# {
#   "success": true,
#   "operation": "understand_video",
#   "video_path": "/path/to/demo.mp4",
#   "num_frames_extracted": 8,
#   "response": "The video shows..."
# }
```

**Custom Prompt and Frame Count**:

```python
# Ask specific questions about the video
result = await understand_video(
    video_path="tutorial.mp4",
    prompt="What steps are shown in this tutorial? List them in order.",
    num_frames=12  # Extract more frames for detailed analysis
)
```

**Meeting Summary**:

```python
# Summarize a meeting recording
result = await understand_video(
    video_path="meeting_recording.mp4",
    prompt="Summarize the key points and decisions made in this meeting."
)
```

**Configuration Example**:

```yaml
# massgen/configs/tools/custom_tools/multimodal_tools/understand_video.yaml
agents:
  - id: "understand_video_tool"
    backend:
      type: "openai"
      model: "gpt-5-nano"
      cwd: "workspace1"
      custom_tools:
        - name: ["understand_video"]
          category: "multimodal"
          path: "massgen/tool/_multimodal_tools/understand_video.py"
          function: ["understand_video"]
```

**CLI Usage**:

```bash
massgen --config massgen/configs/tools/custom_tools/multimodal_tools/understand_video.yaml "What's happening in this video?"
```

#### Note

This tool extracts still frames from the video. Audio content is not analyzed. For audio analysis, use the `understand_audio` tool.

---

## Audio Understanding Tool

### understand_audio

**What it does**: Transcribes audio files to text using OpenAI's Transcription API. Supports multiple audio file formats and can process multiple files in a single call.

**Why use it**: Enables agents to understand spoken content in audio files without manual listening. Ideal for transcribing interviews, meetings, podcasts, or any audio content that needs to be converted to text.

**Location**: `massgen.tool._multimodal_tools.understand_audio`

#### Parameters

- `audio_paths` (required): List of paths to input audio files
  - Relative paths: Resolved relative to workspace
  - Absolute paths: Must be within allowed directories
  - Supported formats: WAV, MP3, M4A, MP4, OGG, FLAC, AAC, WMA, OPUS
- `model` (optional): Model to use (default: "gpt-4o-transcribe")
- `allowed_paths` (optional): List of allowed base paths for validation

#### Returns

ExecutionResult containing:
- `success`: Whether operation succeeded
- `operation`: "generate_text_with_input_audio"
- `transcriptions`: List of transcription results for each file
  - Each contains `file` path and `transcription` text
- `audio_files`: List of paths to the input audio files
- `model`: Model used

#### Security Features

- Path validation for all audio files
- File existence and format validation
- Requires valid OpenAI API key
- Separate error handling for each file

#### Examples

**Single Audio File Transcription**:

```python
from massgen.tool._multimodal_tools import understand_audio

# Transcribe a single audio file
result = await understand_audio(audio_paths=["recording.wav"])

# Output includes transcription
print(result.output_blocks[0].data)
# {
#   "success": true,
#   "operation": "generate_text_with_input_audio",
#   "transcriptions": [
#     {
#       "file": "/path/to/recording.wav",
#       "transcription": "Hello, this is a test recording..."
#     }
#   ],
#   "audio_files": ["/path/to/recording.wav"],
#   "model": "gpt-4o-transcribe"
# }
```

**Multiple Audio Files**:

```python
# Transcribe multiple audio files in one call
result = await understand_audio(
    audio_paths=["interview1.mp3", "interview2.mp3", "interview3.mp3"]
)

# Each file is transcribed separately
for transcription in result["transcriptions"]:
    print(f"File: {transcription['file']}")
    print(f"Text: {transcription['transcription']}")
```

**Configuration Example**:

```yaml
# massgen/configs/tools/custom_tools/multimodal_tools/understand_audio.yaml
agents:
  - id: "understand_audio_tool"
    backend:
      type: "openai"
      model: "gpt-5-nano"
      cwd: "workspace1"
      custom_tools:
        - name: ["understand_audio"]
          category: "multimodal"
          path: "massgen/tool/_multimodal_tools/understand_audio.py"
          function: ["understand_audio"]
```

**CLI Usage**:

```bash
massgen --config massgen/configs/tools/custom_tools/multimodal_tools/understand_audio.yaml "What is being said in this audio?"
```

---

## Image Understanding Tool

### understand_image

**What it does**: Analyzes images using OpenAI's gpt-4.1 API to provide descriptions, answer questions, or extract insights from image content.

**Why use it**: Allows agents to "see" and understand images. Perfect for analyzing charts, screenshots, photos, diagrams, or any visual content that needs interpretation.

**Location**: `massgen.tool._multimodal_tools.understand_image`

#### Parameters

- `image_path` (required): Path to the image file
  - Relative path: Resolved relative to workspace
  - Absolute path: Must be within allowed directories
  - Supported formats: PNG, JPEG, JPG
- `prompt` (optional): Question or instruction about the image (default: "What's in this image? Please describe it in detail.")
- `model` (optional): Model to use (default: "gpt-4.1")
- `allowed_paths` (optional): List of allowed base paths for validation

#### Returns

ExecutionResult containing:
- `success`: Whether operation succeeded
- `operation`: "understand_image"
- `image_path`: Path to the analyzed image
- `prompt`: The prompt used
- `model`: Model used for analysis
- `response`: The model's understanding/description of the image

#### Security Features

- Path validation to ensure access only to allowed directories
- Requires valid OpenAI API key
- File format validation (PNG, JPEG, JPG only)
- Secure base64 encoding for API transmission

#### Examples

**Basic Image Description**:

```python
from massgen.tool._multimodal_tools import understand_image

# Get a detailed description of an image
result = await understand_image(image_path="photo.jpg")

# Output includes image analysis
print(result.output_blocks[0].data)
# {
#   "success": true,
#   "operation": "understand_image",
#   "image_path": "/path/to/photo.jpg",
#   "response": "This image shows..."
# }
```

**Chart Analysis**:

```python
# Analyze a chart or graph
result = await understand_image(
    image_path="sales_chart.png",
    prompt="What data is shown in this chart? What are the key trends?"
)
```

**Screenshot Analysis**:

```python
# Analyze UI elements in a screenshot
result = await understand_image(
    image_path="app_screenshot.png",
    prompt="What UI elements are visible in this screenshot? Describe the layout and functionality."
)
```

**Diagram Understanding**:

```python
# Understand technical diagrams
result = await understand_image(
    image_path="architecture_diagram.png",
    prompt="Explain the system architecture shown in this diagram."
)
```

**Configuration Example**:

```yaml
# massgen/configs/tools/custom_tools/multimodal_tools/understand_image.yaml
agents:
  - id: "understand_image_tool"
    backend:
      type: "openai"
      model: "gpt-5-nano"
      cwd: "workspace1"
      custom_tools:
        - name: ["understand_image"]
          category: "multimodal"
          path: "massgen/tool/_multimodal_tools/understand_image.py"
          function: ["understand_image"]
```

**CLI Usage**:

```bash
massgen --config massgen/configs/tools/custom_tools/multimodal_tools/understand_image.yaml "Describe this image in detail"
```

---

## File Understanding Tool

### understand_file

**What it does**: Reads and analyzes various file types (text files, PDF, DOCX, XLSX, PPTX) using OpenAI's gpt-4.1 API. Automatically extracts content from different document formats and processes it for analysis.

**Why use it**: Enables agents to understand document content without manual reading. Perfect for summarizing documents, extracting key information, answering questions about files, or analyzing structured data.

**Location**: `massgen.tool._multimodal_tools.understand_file`

#### Parameters

- `file_path` (required): Path to the file to analyze
  - Relative path: Resolved relative to workspace
  - Absolute path: Must be within allowed directories
- `prompt` (optional): Question or instruction about the file (default: "Please analyze this file and provide a comprehensive understanding of its content, purpose, and structure.")
- `model` (optional): Model to use (default: "gpt-4.1")
- `max_chars` (optional): Maximum number of characters to read/extract (default: 50000)
  - Prevents processing extremely large files
  - Applies to both text files and extracted content
- `allowed_paths` (optional): List of allowed base paths for validation

#### Returns

ExecutionResult containing:
- `success`: Whether operation succeeded
- `operation`: "understand_file"
- `file_path`: Path to the analyzed file
- `file_name`: Name of the file
- `file_type`: Extraction method used ("text", "pdf", "docx", "excel", "pptx")
- `file_size`: Size of the file in bytes
- `chars_read`: Number of characters read/extracted
- `truncated`: Whether content was truncated
- `prompt`: The prompt used
- `model`: Model used for analysis
- `response`: The model's understanding/analysis of the file

#### Security Features

- Path validation to ensure access only to allowed directories
- File existence and type validation
- Content size limits to prevent memory issues
- Requires valid OpenAI API key
- Blocks unsupported binary formats

#### Supported File Types

**Text Files** (read directly):
- Code: `.py`, `.js`, `.java`, `.cpp`, `.c`, `.go`, `.rs`, `.ts`, `.tsx`, `.jsx`, etc.
- Config: `.md`, `.yaml`, `.yml`, `.json`, `.xml`, `.toml`, `.ini`, etc.
- Data: `.txt`, `.log`, `.csv`, `.tsv`, etc.

**Document Files** (require additional packages):
- PDF: `.pdf` (requires `PyPDF2`)
- Word: `.docx` (requires `python-docx`)
- Excel: `.xlsx` (requires `openpyxl`)
- PowerPoint: `.pptx` (requires `python-pptx`)

**Unsupported Formats**:
- Old Office formats (`.doc`, `.xls`, `.ppt`)
- Images (use `understand_image` instead)
- Videos (use `understand_video` instead)
- Audio (use `understand_audio` instead)
- Archives (`.zip`, `.tar`, `.gz`, etc.)
- Executables (`.exe`, `.dll`, `.so`, etc.)

#### Dependencies

For document processing:
```bash
pip install PyPDF2>=3.0.1           # For PDF files
pip install python-docx>=1.2.0      # For DOCX files
pip install openpyxl>=3.1.5         # For XLSX files
pip install python-pptx>=1.0.2      # For PPTX files
```

#### Examples

**Analyze Python Script**:

```python
from massgen.tool._multimodal_tools import understand_file

# Analyze a Python script
result = await understand_file(
    file_path="script.py",
    prompt="Explain what this script does and how it works."
)

print(result.output_blocks[0].data)
# {
#   "success": true,
#   "operation": "understand_file",
#   "file_type": "text",
#   "response": "This Python script..."
# }
```

**Summarize Documentation**:

```python
# Summarize a README file
result = await understand_file(
    file_path="README.md",
    prompt="Summarize the key points of this documentation in 3-5 bullet points."
)
```

**Analyze PDF Document**:

```python
# Analyze a research paper
result = await understand_file(
    file_path="research_paper.pdf",
    prompt="What are the main findings and conclusions of this research paper?"
)
```

**Process Word Document**:

```python
# Summarize a business proposal
result = await understand_file(
    file_path="proposal.docx",
    prompt="Provide a summary of this business proposal including objectives, timeline, and budget."
)
```

**Analyze Excel Spreadsheet**:

```python
# Analyze data in spreadsheet
result = await understand_file(
    file_path="sales_data.xlsx",
    prompt="What patterns and trends can you identify in this sales data?"
)
```

**Process PowerPoint Presentation**:

```python
# Summarize presentation
result = await understand_file(
    file_path="quarterly_review.pptx",
    prompt="Summarize the key points from each slide of this presentation."
)
```

**Handle Large Files**:

```python
# Process large file with custom character limit
result = await understand_file(
    file_path="large_document.pdf",
    prompt="Summarize the introduction and conclusion sections.",
    max_chars=100000  # Increase limit for larger files
)
```

**Configuration Example**:

```yaml
# massgen/configs/tools/custom_tools/multimodal_tools/understand_file.yaml
agents:
  - id: "understand_file_tool"
    backend:
      type: "openai"
      model: "gpt-5-nano"
      cwd: "workspace1"
      custom_tools:
        - name: ["understand_file"]
          category: "multimodal"
          path: "massgen/tool/_multimodal_tools/understand_file.py"
          function: ["understand_file"]
```

**CLI Usage**:

```bash
massgen --config massgen/configs/tools/custom_tools/multimodal_tools/understand_file.yaml "Summarize the content of this PDF"
```

---

## Setup and Configuration

### Environment Setup

All multimodal tools require an OpenAI API key. Set it in your environment or `.env` file:

```bash
# In your .env file or environment
OPENAI_API_KEY=your-api-key-here
```

### Installing Dependencies

Install all required dependencies:

```bash
# For video understanding
pip install opencv-python>=4.12.0.88

# For document processing
pip install PyPDF2>=3.0.1
pip install python-docx>=1.2.0
pip install openpyxl>=3.1.5
pip install python-pptx>=1.0.2

# Or install all at once via pyproject.toml
uv sync
```

### Path Security

All tools implement path validation to ensure files are accessed only from allowed directories:

```python
# Configure allowed paths in your agent configuration
allowed_paths = ["/path/to/workspace", "/path/to/data"]

# Tools will validate all file accesses
result = await understand_file(
    file_path="document.pdf",
    allowed_paths=allowed_paths
)
```

---

## Best Practices

### Video Analysis

1. **Frame Selection**:
   - Use 8 frames for general videos
   - Use 12-16 frames for detailed tutorials or complex content
   - Use 4-6 frames for short clips

2. **Prompting**:
   - Be specific about what you want to know
   - Ask for step-by-step descriptions for tutorials
   - Request timestamps or sequence information when relevant

### Audio Transcription

1. **File Quality**:
   - Use high-quality audio files for best transcription results
   - Ensure audio is clear and audible
   - Consider splitting very long audio files

2. **Batch Processing**:
   - Process multiple related audio files in a single call
   - Organize transcriptions by file for clarity

### Image Analysis

1. **Image Quality**:
   - Use high-resolution images when possible
   - Ensure images are clear and properly exposed
   - Avoid heavily compressed images

2. **Specific Prompts**:
   - Ask targeted questions for specific information
   - Request structured output (lists, tables) when appropriate
   - Specify areas of focus for complex images

### File Understanding

1. **Content Size**:
   - Adjust `max_chars` based on file size and needs
   - For large files, focus prompts on specific sections
   - Consider extracting specific pages or sections first

2. **Document Types**:
   - Use appropriate prompts for different document types
   - For spreadsheets, specify which sheets or columns to focus on
   - For presentations, ask for slide-by-slide summaries

---

## Error Handling

All tools return structured error messages in the ExecutionResult:

```python
result = await understand_video(video_path="missing.mp4")

# Check for errors
if not result["success"]:
    print(f"Error: {result['error']}")
    # Error: Video file does not exist: /path/to/missing.mp4
```

Common errors:
- Missing API key
- File not found
- Invalid file format
- Path access violation
- API errors
- Missing dependencies

---

## Performance Considerations

1. **API Costs**:
   - Video and image analysis incur higher API costs
   - Limit frame count for videos to control costs
   - Use appropriate `max_chars` limits for files

2. **Processing Time**:
   - Video processing time increases with frame count
   - Large documents take longer to process
   - Multiple audio files are processed sequentially

3. **Resource Usage**:
   - Video frame extraction requires memory
   - Large files are read into memory
   - Consider file size limits for production use

---

## Integration Examples

### Using in Agent Workflows

```python
# Example: Analyze a video and generate a report
async def analyze_video_content(video_path: str):
    # Step 1: Understand the video
    video_result = await understand_video(
        video_path=video_path,
        prompt="Describe the main content and key moments in this video."
    )

    # Step 2: Extract any text/captions from a screenshot
    screenshot_result = await understand_image(
        image_path="video_screenshot.png",
        prompt="Extract any text visible in this image."
    )

    # Step 3: Transcribe audio
    audio_result = await understand_audio(
        audio_paths=["video_audio.mp3"]
    )

    # Step 4: Generate comprehensive report
    report = {
        "visual_content": video_result["response"],
        "visible_text": screenshot_result["response"],
        "audio_transcription": audio_result["transcriptions"][0]["transcription"]
    }

    return report
```

### Multi-Modal Document Analysis

```python
# Example: Analyze a presentation with images
async def analyze_presentation(pptx_path: str, image_dir: str):
    # Analyze presentation structure
    pptx_result = await understand_file(
        file_path=pptx_path,
        prompt="List the main topic of each slide."
    )

    # Analyze individual slide images
    image_results = []
    for image_file in Path(image_dir).glob("*.png"):
        result = await understand_image(
            image_path=str(image_file),
            prompt="Describe the content and any charts/diagrams in this slide."
        )
        image_results.append(result)

    return {
        "structure": pptx_result["response"],
        "slide_visuals": [r["response"] for r in image_results]
    }
```

---

## Troubleshooting

### OpenAI API Key Issues

```
Error: OpenAI API key not found
```

**Solution**: Set `OPENAI_API_KEY` in your `.env` file or environment variables.

### Missing Dependencies

```
Error: opencv-python is required for video frame extraction
```

**Solution**: Install the required package:
```bash
pip install opencv-python>=4.12.0.88
```

### Path Access Errors

```
Error: Path not in allowed directories
```

**Solution**: Ensure the file path is within the allowed directories or adjust the `allowed_paths` parameter.

### File Format Errors

```
Error: File does not appear to be a video file
```

**Solution**: Check that the file has the correct extension and is a valid media file.

---

---

## Image Generation Tools

### text_to_image_generation

**What it does**: Generates images from text descriptions using OpenAI's GPT-4.1 API **WITHOUT ANY INPUT IMAGES**. Creates new images from scratch based solely on text prompts.

**Why use it**: Allows agents to create original visual content from descriptions. Perfect for generating illustrations, concept art, product visualizations, or any creative visual content.

**Location**: `massgen.tool._multimodal_tools.text_to_image_generation`

#### Parameters

- `prompt` (required): Text description of the image to generate
  - Be specific and detailed for better results
  - Include style, composition, lighting, and mood details
- `model` (optional): Model to use (default: "gpt-4.1")
  - Options: "gpt-4.1"
- `storage_path` (optional): Directory path where to save the image
  - **IMPORTANT**: Must be a DIRECTORY path only, NOT a file path
  - Example: "images/generated" NOT "images/cat.png"
  - Filename is automatically generated from prompt and timestamp
  - Relative path: Resolved relative to agent's workspace
  - Absolute path: Must be within allowed directories
  - None/empty: Saves to agent's workspace root
- `allowed_paths` (optional): List of allowed base paths for validation

#### Returns

ExecutionResult containing:
- `success`: Whether operation succeeded
- `operation`: "generate_and_store_image_no_input_images"
- `note`: Note about operation
- `images`: List of generated images with file paths and metadata
- `model`: Model used for generation
- `prompt`: The prompt used for generation
- `total_images`: Total number of images generated and saved

#### Security Features

- Requires valid OpenAI API key
- Files are saved to specified path within workspace
- Path must be within allowed directories
- Automatic timestamp-based filename generation

#### Examples

**Basic Image Generation**:

```python
from massgen.tool._multimodal_tools import text_to_image_generation

# Generate an image from a text description
result = await text_to_image_generation(prompt="a cat in space")

# Output includes file path and metadata
print(result.output_blocks[0].data)
# {
#   "success": true,
#   "operation": "generate_and_store_image_no_input_images",
#   "images": [{
#     "file_path": "/workspace/20240115_143022_a_cat_in_space.png",
#     "filename": "20240115_143022_a_cat_in_space.png",
#     "size": 125340
#   }],
#   "total_images": 1
# }
```

**Custom Storage Path**:

```python
# Generate with custom storage location
result = await text_to_image_generation(
    prompt="sunset over mountains",
    storage_path="art/landscapes"
)
```

**Configuration Example**:

```yaml
# massgen/configs/tools/custom_tools/multimodal_tools/text_to_image_generation_single.yaml
agents:
  - id: "image_generator"
    backend:
      type: "openai"
      model: "gpt-4o"
      cwd: "workspace1"
      enable_image_generation: true
      custom_tools:
        - name: ["text_to_image_generation"]
          category: "multimodal"
          path: "massgen/tool/_multimodal_tools/text_to_image_generation.py"
          function: ["text_to_image_generation"]
```

**CLI Usage**:

```bash
massgen --config massgen/configs/tools/custom_tools/multimodal_tools/text_to_image_generation_single.yaml "Generate an image of a futuristic city at night"
```

---

### image_to_image_generation

**What it does**: Creates variations based on multiple input images using OpenAI's GPT-4.1 API. Generates new images inspired by existing ones.

**Why use it**: Allows agents to create variations, mashups, or transformations of existing images. Perfect for style transfer, image editing, or creating variations of designs.

**Location**: `massgen.tool._multimodal_tools.image_to_image_generation`

#### Parameters

- `base_image_paths` (required): List of paths to base images
  - Supported formats: PNG, JPEG (less than 4MB each)
  - Relative paths: Resolved relative to workspace
  - Absolute paths: Must be within allowed directories
- `prompt` (optional): Text description for the variation (default: "Create a variation of the provided images")
- `model` (optional): Model to use (default: "gpt-4.1")
- `storage_path` (optional): Directory path where to save variations
  - **IMPORTANT**: Must be a DIRECTORY path only
  - Filename is automatically generated
- `allowed_paths` (optional): List of allowed base paths for validation

#### Returns

ExecutionResult containing:
- `success`: Whether operation succeeded
- `operation`: "generate_and_store_image_with_input_images"
- `note`: Note about usage
- `images`: List of generated images with file paths and metadata
- `model`: Model used for generation
- `prompt`: The prompt used
- `total_images`: Total number of images generated

#### Security Features

- Requires valid OpenAI API key
- Input images must be valid image files less than 4MB
- Files are saved to specified path within workspace
- Path validation for security

#### Examples

**Create Image Variation**:

```python
from massgen.tool._multimodal_tools import image_to_image_generation

# Generate variation from a single image
result = await image_to_image_generation(
    base_image_paths=["logo.png"],
    prompt="Create a modern variation of this logo"
)
```

**Combine Multiple Images**:

```python
# Generate variation combining multiple images
result = await image_to_image_generation(
    base_image_paths=["cat.png", "dog.png"],
    prompt="Combine these animals into a single creature"
)
```

---

## Video Generation Tools

### text_to_video_generation

**What it does**: Generates videos from text descriptions using OpenAI's Sora-2 API. Creates high-quality video content from detailed scene descriptions.

**Why use it**: Allows agents to create video content from descriptions. Perfect for marketing content, concept visualization, educational videos, or social media content.

**Location**: `massgen.tool._multimodal_tools.text_to_video_generation`

#### Parameters

- `prompt` (required): Text description for the video to generate
  - Include scene details, camera movements, lighting, atmosphere
  - Be specific about actions, objects, and environment
- `model` (optional): Model to use (default: "sora-2")
- `seconds` (optional): Video duration in seconds (default: 4)
  - Supported range: 4-20 seconds
- `storage_path` (optional): Directory path where to save the video
  - **IMPORTANT**: Must be a DIRECTORY path only
  - Filename is automatically generated from prompt and timestamp
  - Relative path: Resolved relative to workspace
  - Absolute path: Must be within allowed directories
- `allowed_paths` (optional): List of allowed base paths for validation

#### Returns

ExecutionResult containing:
- `success`: Whether operation succeeded
- `operation`: "generate_and_store_video_no_input_images"
- `video_path`: Path to the saved video file
- `filename`: Name of the generated file
- `size`: File size in bytes
- `model`: Model used for generation
- `prompt`: The prompt used
- `duration`: Time taken for generation in seconds

#### Security Features

- Requires valid OpenAI API key with Sora-2 access
- Files are saved to specified path within workspace
- Automatic video download and storage

#### Examples

**Basic Video Generation**:

```python
from massgen.tool._multimodal_tools import text_to_video_generation

# Generate a 4-second video
result = await text_to_video_generation(
    prompt="A cool cat on a motorcycle in the night"
)

# Output includes video path
print(result.output_blocks[0].data)
# {
#   "success": true,
#   "operation": "generate_and_store_video_no_input_images",
#   "video_path": "/workspace/20240115_143022_a_cool_cat_on_motorcycle.mp4",
#   "size": 5242880,
#   "duration": 45.2
# }
```

**Detailed Scene with Duration**:

```python
# Generate with detailed prompt and custom duration
result = await text_to_video_generation(
    prompt="Neon-lit alley at night, light rain, slow push-in, cinematic lighting",
    seconds=10,
    storage_path="videos/cinematic"
)
```

**Configuration Example**:

```yaml
# massgen/configs/tools/custom_tools/multimodal_tools/text_to_video_generation_single.yaml
agents:
  - id: "video_generator"
    backend:
      type: "openai"
      model: "gpt-4o"
      cwd: "workspace1"
      enable_video_generation: true
      custom_tools:
        - name: ["text_to_video_generation"]
          category: "multimodal"
          path: "massgen/tool/_multimodal_tools/text_to_video_generation.py"
          function: ["text_to_video_generation"]
```

**CLI Usage**:

```bash
massgen --config massgen/configs/tools/custom_tools/multimodal_tools/text_to_video_generation_single.yaml "Generate a 4 seconds video with neon-lit alley at night, light rain, slow push-in, cinematic."
```

---

## Audio/Speech Generation Tools

### text_to_speech_continue_generation

**What it does**: Generates expressive speech from text using OpenAI's GPT-4o Audio Preview model. Creates natural-sounding speech with emotional expression and context awareness.

**Why use it**: Allows agents to generate expressive speech with emotional tone. Perfect for creating voice-overs, narrations, audiobooks, or any content requiring natural, emotional speech.

**Location**: `massgen.tool._multimodal_tools.text_to_speech_continue_generation`

#### Parameters

- `prompt` (required): Text content to convert to audio speech
- `model` (optional): Model to use (default: "gpt-4o-audio-preview")
- `voice` (optional): Voice to use (default: "alloy")
  - Options: "alloy", "echo", "fable", "onyx", "nova", "shimmer"
- `audio_format` (optional): Audio format for output (default: "wav")
  - Options: "wav", "mp3", "opus", "aac", "flac"
- `storage_path` (optional): Directory path where to save the audio
  - **IMPORTANT**: Must be a DIRECTORY path only
  - Filename is automatically generated from prompt and timestamp
- `allowed_paths` (optional): List of allowed base paths for validation

#### Returns

ExecutionResult containing:
- `success`: Whether operation succeeded
- `operation`: "generate_and_store_audio_no_input_audios"
- `audio_file`: Generated audio file with path and metadata
- `model`: Model used for generation
- `prompt`: The prompt used for generation
- `voice`: Voice used for generation
- `format`: Audio format used

#### Examples

**Expressive Speech**:

```python
from massgen.tool._multimodal_tools import text_to_speech_continue_generation

# Generate expressive speech
result = await text_to_speech_continue_generation(
    prompt="I want you to tell me a very short introduction about Sherlock Holmes in one sentence, and I want you to use emotion voice to read it out loud."
)
```

**Custom Voice and Format**:

```python
# Generate with specific voice and format
result = await text_to_speech_continue_generation(
    prompt="Hello world",
    voice="nova",
    audio_format="mp3",
    storage_path="audio/generated"
)
```

---

### text_to_speech_transcription_generation

**What it does**: Converts text directly to speech using OpenAI's TTS API with streaming response. Provides fast, cost-effective text-to-speech conversion.

**Why use it**: Allows agents to quickly convert text to speech. Perfect for transcription conversion, simple voice-overs, or when expressive emotion is not required.

**Location**: `massgen.tool._multimodal_tools.text_to_speech_transcription_generation`

#### Parameters

- `input_text` (required): The text content to convert to speech
- `model` (optional): TTS model to use (default: "gpt-4o-mini-tts")
  - Options: "gpt-4o-mini-tts", "tts-1", "tts-1-hd"
- `voice` (optional): Voice to use (default: "alloy")
  - Options: "alloy", "echo", "fable", "onyx", "nova", "shimmer", "coral", "sage"
- `instructions` (optional): Optional speaking instructions for tone and style
  - Example: "Speak in a cheerful tone"
- `storage_path` (optional): Directory path where to save the audio file
  - **IMPORTANT**: Must be a DIRECTORY path only
- `audio_format` (optional): Output audio format (default: "mp3")
  - Options: "mp3", "opus", "aac", "flac", "wav", "pcm"
- `allowed_paths` (optional): List of allowed base paths for validation

#### Returns

ExecutionResult containing:
- `success`: Whether operation succeeded
- `operation`: "convert_text_to_speech"
- `audio_file`: Generated audio file with path and metadata
- `model`: TTS model used
- `voice`: Voice used
- `format`: Audio format used
- `text_length`: Length of input text
- `instructions`: Speaking instructions if provided

#### Examples

**Simple Text-to-Speech**:

```python
from massgen.tool._multimodal_tools import text_to_speech_transcription_generation

# Convert text to speech
result = await text_to_speech_transcription_generation(
    input_text="Hello world, this is a test."
)
```

**With Instructions**:

```python
# Convert with specific voice and instructions
result = await text_to_speech_transcription_generation(
    input_text="Today is a wonderful day to build something people love!",
    voice="coral",
    instructions="Speak in a cheerful and positive tone."
)
```

---

## File Generation Tools

### text_to_file_generation

**What it does**: Generates text content using OpenAI API and saves it as various file formats (TXT, MD, PDF, PPTX). Creates professional documents from text prompts.

**Why use it**: Allows agents to create formatted documents automatically. Perfect for generating reports, documentation, presentations, or any structured text content.

**Location**: `massgen.tool._multimodal_tools.text_to_file_generation`

#### Parameters

- `prompt` (required): Description of the content to generate
  - Be specific about structure, sections, and formatting
  - Example: "Write a technical report about AI"
- `file_format` (optional): Output file format (default: "txt")
  - Options: "txt", "md", "pdf", "pptx"
- `filename` (optional): Custom filename without extension
  - If not provided, generates from prompt and timestamp
- `model` (optional): OpenAI model to use (default: "gpt-4o")
  - Options: "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"
- `storage_path` (optional): Directory path where to save the file
  - **IMPORTANT**: Must be a DIRECTORY path only
  - Filename is automatically generated from prompt or custom filename
  - Relative path: Resolved relative to workspace
  - Absolute path: Must be within allowed directories
- `allowed_paths` (optional): List of allowed base paths for validation

#### Returns

ExecutionResult containing:
- `success`: Whether operation succeeded
- `operation`: "generate_and_store_file"
- `file_path`: Path to the generated file
- `filename`: Name of the generated file
- `file_format`: Format of the generated file
- `content_preview`: First 500 characters of generated content
- `file_size`: Size of the generated file in bytes
- `model`: Model used for generation
- `prompt`: The prompt used

#### Security Features

- Requires valid OpenAI API key
- Files are saved to specified path within workspace
- Path must be within allowed directories

#### Dependencies

- PDF generation requires either `reportlab` or `fpdf2` library
- PPTX generation requires `python-pptx` library

```bash
pip install reportlab  # For PDF
pip install python-pptx  # For PPTX
```

#### Examples

**Generate Markdown Document**:

```python
from massgen.tool._multimodal_tools import text_to_file_generation

# Generate a markdown file
result = await text_to_file_generation(
    prompt="Write a blog post about Python",
    file_format="md"
)
```

**Generate PDF Report**:

```python
# Generate a PDF with custom filename
result = await text_to_file_generation(
    prompt="Create a technical report on machine learning",
    file_format="pdf",
    filename="ml_report",
    storage_path="documents/reports"
)
```

**Generate PowerPoint Presentation**:

```python
# Generate PPTX - structure prompt with slide titles (# or ##) and bullet points (-)
result = await text_to_file_generation(
    prompt="""Create a presentation about AI trends:

    # Introduction
    - Overview of AI landscape
    - Key developments in 2024

    # Current Trends
    - Large Language Models
    - Multimodal AI
    - AI Safety

    # Future Outlook
    - Predictions for 2025
    - Emerging technologies
    """,
    file_format="pptx",
    filename="ai_trends_presentation"
)
```

**Configuration Example**:

```yaml
# massgen/configs/tools/custom_tools/multimodal_tools/text_to_file_generation_single.yaml
agents:
  - id: "document_generator"
    backend:
      type: "openai"
      model: "gpt-4o"
      cwd: "workspace1"
      enable_file_generation: true
      custom_tools:
        - name: ["text_to_file_generation"]
          category: "multimodal"
          path: "massgen/tool/_multimodal_tools/text_to_file_generation.py"
          function: ["text_to_file_generation"]
```

**CLI Usage**:

```bash
massgen --config massgen/configs/tools/custom_tools/multimodal_tools/text_to_file_generation_single.yaml "Generate a technical report about LLMs and save as PDF"
```

#### Note

- For PPTX format, structure your prompt to include slide titles (using # or ##) and bullet points (using -)
- The quality and format of generated content depends on the prompt
- Longer content may consume more tokens

---

## Best Practices for Generation Tools

### Image Generation

1. **Prompt Quality**:
   - Be specific about style, composition, lighting, and mood
   - Include details about colors, perspective, and atmosphere
   - Use artistic terminology for better results

2. **Cost Management**:
   - Image generation (GPT-4.1) is more expensive than standard API calls
   - Test prompts with understanding tools first
   - Use multi-agent workflows to refine prompts before generation

### Video Generation

1. **Prompt Structure**:
   - Include: setting, lighting, camera movements, atmosphere
   - Specify duration based on content complexity (4-20 seconds)
   - Use cinematic terminology (push-in, pull-out, pan, etc.)

2. **Quality Verification**:
   - Combine with `understand_video` tool for quality checks
   - Use multi-agent workflows for iterative refinement

### Audio/Speech Generation

1. **Voice Selection**:
   - Choose appropriate voice for content type
   - Use expressive model (gpt-4o-audio-preview) for emotional content
   - Use TTS model (gpt-4o-mini-tts) for simple conversions

2. **Format Selection**:
   - WAV for highest quality
   - MP3 for balanced quality/size
   - OPUS for web streaming

### Document Generation

1. **Format Selection**:
   - TXT for simple content
   - MD for formatted documentation
   - PDF for professional documents
   - PPTX for presentations

2. **Prompt Structure**:
   - Outline structure clearly
   - Specify sections and formatting
   - For PPTX, use markdown-style headers and bullets

---

## Additional Resources

- [OpenAI API Documentation](https://platform.openai.com/docs)
- [OpenCV Documentation](https://docs.opencv.org/)
- [PyPDF2 Documentation](https://pypdf2.readthedocs.io/)
- [python-docx Documentation](https://python-docx.readthedocs.io/)
- [openpyxl Documentation](https://openpyxl.readthedocs.io/)
- [python-pptx Documentation](https://python-pptx.readthedocs.io/)
- [reportlab Documentation](https://www.reportlab.com/documentation/)
