# ExecutionResult Documentation

## Overview

`ExecutionResult` is the standardized container for all tool execution outputs in the MassGen Tool System. It provides a structured way to return results from tools, supporting text, images, audio, streaming outputs, and metadata.

## Core Concepts

**What is ExecutionResult?**
Think of ExecutionResult as a package that tools send back to agents. Like a delivery package, it contains:
- The main content (text, images, audio)
- Metadata (extra information about the result)
- Status flags (is it streaming? is it final? was it interrupted?)
- A unique ID for tracking

**Why use ExecutionResult?**
Instead of returning raw strings or objects, ExecutionResult provides:
- **Type Safety**: Structured format prevents errors
- **Multimodal Support**: Can include text, images, and audio together
- **Streaming**: Support for progressive results
- **Metadata**: Extra information without cluttering main content
- **Tracking**: Unique IDs for debugging and logging

## Class Definition

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Union

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

    was_interrupted: bool = False
    """Indicates if the execution was interrupted."""

    result_id: str = field(default_factory=_generate_id)
    """Unique identifier for this result."""
```

## Content Block Types

### TextContent

**What it does**: Wraps text output from tools. This is the most common content type for returning strings, error messages, or formatted text.

**When to use it**: For any text-based output - results, logs, error messages, JSON strings, etc.

```python
from massgen.tool import TextContent

# Simple text
text = TextContent(data="Hello, World!")

# Formatted output
text = TextContent(data="""
Results:
- Item 1: Success
- Item 2: Failed
- Item 3: Pending
""")

# JSON output
import json
data_dict = {"status": "ok", "count": 42}
text = TextContent(data=json.dumps(data_dict, indent=2))

# Error message
text = TextContent(data="Error: File not found at /path/to/file")

# Large text
with open("report.txt") as f:
    text = TextContent(data=f.read())
```

### ImageContent

**What it does**: Wraps image data (typically base64-encoded) from tools that generate or process images.

**When to use it**: For image generation, image processing results, charts, visualizations, or any visual output.

```python
from massgen.tool import ImageContent
import base64

# From file
with open("chart.png", "rb") as f:
    image_data = base64.b64encode(f.read()).decode()
    image = ImageContent(data=image_data)

# From generation API
# Assume dalle.generate() returns base64 image
image_data = await dalle.generate("A sunset over mountains")
image = ImageContent(data=image_data)

# Multiple images
images = [
    ImageContent(data=encode_image("image1.png")),
    ImageContent(data=encode_image("image2.png")),
    ImageContent(data=encode_image("image3.png"))
]
```

### AudioContent

**What it does**: Wraps audio data (typically base64-encoded) from tools that generate or process audio.

**When to use it**: For text-to-speech, audio generation, audio processing, or any audio output.

```python
from massgen.tool import AudioContent
import base64

# From file
with open("speech.mp3", "rb") as f:
    audio_data = base64.b64encode(f.read()).decode()
    audio = AudioContent(data=audio_data)

# From TTS API
audio_data = await tts.synthesize("Hello, World!")
audio = AudioContent(data=audio_data)

# Podcast episode
with open("episode_1.mp3", "rb") as f:
    audio = AudioContent(data=base64.b64encode(f.read()).decode())
```

## Creating ExecutionResults

### Simple Text Result

```python
from massgen.tool import ExecutionResult, TextContent

# Basic success result
result = ExecutionResult(
    output_blocks=[TextContent(data="Operation completed successfully")]
)

# With metadata
result = ExecutionResult(
    output_blocks=[TextContent(data="Processed 100 items")],
    meta_info={"processed_count": 100, "duration_ms": 1250}
)
```

### Multimodal Result

```python
from massgen.tool import ExecutionResult, TextContent, ImageContent

# Text + Image
result = ExecutionResult(
    output_blocks=[
        TextContent(data="Generated chart for dataset:"),
        ImageContent(data=chart_image_base64),
        TextContent(data="Analysis complete. See chart above.")
    ],
    meta_info={"chart_type": "bar", "data_points": 20}
)

# Multiple images with descriptions
result = ExecutionResult(
    output_blocks=[
        TextContent(data="Comparison results:"),
        TextContent(data="Original image:"),
        ImageContent(data=original_image),
        TextContent(data="Processed image:"),
        ImageContent(data=processed_image),
        TextContent(data="Difference highlighted in red")
    ]
)
```

### Error Result

```python
# Simple error
error_result = ExecutionResult(
    output_blocks=[TextContent(data="Error: File not found")]
)

# Detailed error with metadata
error_result = ExecutionResult(
    output_blocks=[
        TextContent(data="Error: Connection timeout"),
        TextContent(data="Failed to connect to server after 3 attempts")
    ],
    meta_info={
        "error_type": "ConnectionTimeout",
        "attempts": 3,
        "timeout_seconds": 30
    }
)

# Exception formatting
try:
    risky_operation()
except Exception as e:
    error_result = ExecutionResult(
        output_blocks=[
            TextContent(data=f"Error: {type(e).__name__}"),
            TextContent(data=f"Details: {str(e)}")
        ],
        meta_info={"traceback": traceback.format_exc()}
    )
```

## Streaming Results

### Basic Streaming

**What it does**: Allows tools to send results progressively rather than all at once. Useful for long-running operations where you want to show progress.

**Why use it**: Users see progress immediately instead of waiting for completion. Better user experience for slow operations.

```python
from typing import AsyncGenerator
from massgen.tool import ExecutionResult, TextContent
import asyncio

async def streaming_tool() -> AsyncGenerator[ExecutionResult, None]:
    """Tool that streams progress updates."""

    # Start
    yield ExecutionResult(
        output_blocks=[TextContent(data="Starting process...")],
        is_streaming=True,
        is_final=False
    )

    # Progress updates
    for i in range(1, 6):
        await asyncio.sleep(1)  # Simulate work
        yield ExecutionResult(
            output_blocks=[TextContent(data=f"Processing step {i}/5...")],
            is_streaming=True,
            is_final=False
        )

    # Final result
    yield ExecutionResult(
        output_blocks=[TextContent(data="Process complete!")],
        is_streaming=True,
        is_final=True  # Mark as final
    )

# Usage
async for result in streaming_tool():
    print(result.output_blocks[0].data)
    if result.is_final:
        print("Done!")
```

### Streaming with Accumulation

```python
async def accumulating_stream() -> AsyncGenerator[ExecutionResult, None]:
    """Stream results that build on each other."""

    accumulated = []

    for i in range(5):
        await asyncio.sleep(0.5)
        accumulated.append(f"Item {i+1}")

        # Send accumulated results each time
        yield ExecutionResult(
            output_blocks=[
                TextContent(data=f"Found {len(accumulated)} items so far:"),
                TextContent(data="\n".join(accumulated))
            ],
            is_streaming=True,
            is_final=(i == 4),
            meta_info={"total_items": len(accumulated)}
        )
```

### Streaming with Status

```python
async def status_streaming() -> AsyncGenerator[ExecutionResult, None]:
    """Stream with different status updates."""

    phases = [
        ("Initializing", 2),
        ("Processing", 3),
        ("Validating", 2),
        ("Finalizing", 1)
    ]

    for phase_name, duration in phases:
        yield ExecutionResult(
            output_blocks=[TextContent(data=f"Phase: {phase_name}")],
            is_streaming=True,
            is_final=False,
            meta_info={"current_phase": phase_name}
        )

        await asyncio.sleep(duration)

    # Final
    yield ExecutionResult(
        output_blocks=[TextContent(data="All phases complete")],
        is_streaming=True,
        is_final=True,
        meta_info={"total_phases": len(phases)}
    )
```

## Handling Interruption

**What it does**: The `was_interrupted` flag indicates that execution was cancelled or stopped early.

**Why use it**: Allows tools to signal that they didn't complete normally, helping agents understand partial results.

```python
async def interruptible_tool() -> AsyncGenerator[ExecutionResult, None]:
    """Tool that can be cancelled."""

    try:
        for i in range(100):
            await asyncio.sleep(0.1)

            yield ExecutionResult(
                output_blocks=[TextContent(data=f"Progress: {i}%")],
                is_streaming=True,
                is_final=False
            )

    except asyncio.CancelledError:
        # Handle cancellation gracefully
        yield ExecutionResult(
            output_blocks=[
                TextContent(data="<system>Operation was cancelled</system>")
            ],
            is_streaming=True,
            is_final=True,
            was_interrupted=True  # Mark as interrupted
        )
        raise  # Re-raise to propagate cancellation

# Usage
import asyncio

async def run_with_timeout():
    gen = interruptible_tool()
    try:
        async for result in gen:
            print(result.output_blocks[0].data)
            # Simulate timeout after 3 results
            if "Progress: 2%" in result.output_blocks[0].data:
                raise asyncio.TimeoutError()
    except asyncio.TimeoutError:
        # Generator will send interrupted result
        pass
```

## Metadata Usage

**What it does**: `meta_info` stores additional data that shouldn't be shown directly to users but is useful for logging, debugging, or system processing.

**Why use it**: Separate user-facing content from system-level information. Keep output clean while preserving detailed data.

### Common Metadata Patterns

```python
# Execution metrics
result = ExecutionResult(
    output_blocks=[TextContent(data="Analysis complete")],
    meta_info={
        "execution_time_ms": 1234,
        "memory_used_mb": 45,
        "api_calls": 3
    }
)

# Data provenance
result = ExecutionResult(
    output_blocks=[TextContent(data="Data retrieved")],
    meta_info={
        "source": "database",
        "query": "SELECT * FROM users",
        "row_count": 100,
        "timestamp": datetime.now().isoformat()
    }
)

# Model information
result = ExecutionResult(
    output_blocks=[ImageContent(data=image_data)],
    meta_info={
        "model": "dall-e-3",
        "prompt": "a sunset",
        "size": "1024x1024",
        "revised_prompt": "a beautiful sunset over mountains"
    }
)

# Error details
result = ExecutionResult(
    output_blocks=[TextContent(data="Error: Request failed")],
    meta_info={
        "error_code": "TIMEOUT",
        "retry_count": 3,
        "last_error": "Connection timeout after 30s",
        "failed_at": datetime.now().isoformat()
    }
)

# Processing statistics
result = ExecutionResult(
    output_blocks=[TextContent(data="Processed dataset")],
    meta_info={
        "input_rows": 1000,
        "output_rows": 950,
        "filtered_rows": 50,
        "null_values_removed": 25,
        "duplicates_removed": 25,
        "processing_stages": ["clean", "filter", "deduplicate"]
    }
)
```

## Result ID Tracking

**What it does**: Each ExecutionResult gets a unique ID automatically generated from timestamp and random components.

**Why use it**: Track results through the system, correlate logs, debug issues, and identify specific execution instances.

```python
# Automatic ID generation
result1 = ExecutionResult(output_blocks=[TextContent(data="Result 1")])
result2 = ExecutionResult(output_blocks=[TextContent(data="Result 2")])

print(f"Result 1 ID: {result1.result_id}")
print(f"Result 2 ID: {result2.result_id}")
# Output:
# Result 1 ID: 20240315_143022_123456
# Result 2 ID: 20240315_143022_123457

# Use for logging
import logging

logger = logging.getLogger(__name__)

async def logged_tool() -> ExecutionResult:
    result = ExecutionResult(
        output_blocks=[TextContent(data="Operation complete")]
    )

    logger.info(f"Tool execution complete - ID: {result.result_id}")
    logger.debug(f"Result details: {result.output_blocks[0].data}")

    return result

# Use for tracking
execution_history = {}

async def tracked_tool() -> ExecutionResult:
    result = ExecutionResult(
        output_blocks=[TextContent(data="Processed")],
        meta_info={"processed_items": 100}
    )

    # Store in history
    execution_history[result.result_id] = {
        "timestamp": datetime.now(),
        "output": result.output_blocks[0].data,
        "metadata": result.meta_info
    }

    return result
```

## Complete Examples

### Example 1: Data Processing Tool

```python
from massgen.tool import ExecutionResult, TextContent
import json

async def analyze_csv(file_path: str, column: str) -> ExecutionResult:
    """Analyze a CSV file column.

    Args:
        file_path: Path to CSV file
        column: Column to analyze

    Returns:
        ExecutionResult with statistics
    """
    # Load data (simplified)
    import pandas as pd
    df = pd.read_csv(file_path)

    # Calculate statistics
    stats = {
        "mean": df[column].mean(),
        "median": df[column].median(),
        "std": df[column].std(),
        "min": df[column].min(),
        "max": df[column].max()
    }

    # Format output
    output = f"Statistics for column '{column}':\n"
    output += json.dumps(stats, indent=2)

    return ExecutionResult(
        output_blocks=[TextContent(data=output)],
        meta_info={
            "file": file_path,
            "column": column,
            "row_count": len(df),
            "null_count": df[column].isnull().sum()
        }
    )
```

### Example 2: Image Generation Tool

```python
from massgen.tool import ExecutionResult, TextContent, ImageContent
import base64

async def generate_chart(
    data: list,
    chart_type: str = "bar"
) -> ExecutionResult:
    """Generate a chart from data.

    Args:
        data: Data points for chart
        chart_type: Type of chart (bar, line, pie)

    Returns:
        ExecutionResult with chart image
    """
    # Generate chart (simplified)
    import matplotlib.pyplot as plt
    import io

    fig, ax = plt.subplots()

    if chart_type == "bar":
        ax.bar(range(len(data)), data)
    elif chart_type == "line":
        ax.plot(range(len(data)), data)

    # Save to bytes
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    image_data = base64.b64encode(buf.read()).decode()

    plt.close()

    return ExecutionResult(
        output_blocks=[
            TextContent(data=f"Generated {chart_type} chart with {len(data)} points"),
            ImageContent(data=image_data)
        ],
        meta_info={
            "chart_type": chart_type,
            "data_points": len(data),
            "min_value": min(data),
            "max_value": max(data)
        }
    )
```

### Example 3: Streaming File Processor

```python
from typing import AsyncGenerator
from massgen.tool import ExecutionResult, TextContent
import asyncio

async def process_large_file(
    file_path: str,
    operation: str
) -> AsyncGenerator[ExecutionResult, None]:
    """Process a large file with progress updates.

    Args:
        file_path: Path to file
        operation: Operation to perform (count, validate, transform)

    Yields:
        ExecutionResult objects with progress
    """
    # Open file
    with open(file_path, 'r') as f:
        lines = f.readlines()
        total = len(lines)

    # Initial status
    yield ExecutionResult(
        output_blocks=[TextContent(data=f"Processing {total} lines...")],
        is_streaming=True,
        is_final=False
    )

    # Process in batches
    batch_size = 1000
    processed = 0

    for i in range(0, total, batch_size):
        batch = lines[i:i+batch_size]

        # Simulate processing
        await asyncio.sleep(0.1)
        processed += len(batch)

        # Progress update
        progress = int((processed / total) * 100)
        yield ExecutionResult(
            output_blocks=[
                TextContent(data=f"Progress: {processed}/{total} lines ({progress}%)")
            ],
            is_streaming=True,
            is_final=False,
            meta_info={"processed_lines": processed, "total_lines": total}
        )

    # Final result
    yield ExecutionResult(
        output_blocks=[
            TextContent(data=f"Processing complete! Processed {total} lines")
        ],
        is_streaming=True,
        is_final=True,
        meta_info={
            "operation": operation,
            "total_lines": total,
            "file_path": file_path
        }
    )
```

## Best Practices

### Content Organization

1. **Use Multiple Blocks**: Separate different types of content
2. **Clear Descriptions**: Precede images/audio with descriptive text
3. **Structured Output**: Use formatting for readability
4. **Error Context**: Include context with error messages

### Metadata Guidelines

1. **Don't Duplicate**: Don't repeat output_blocks content in meta_info
2. **Use for System Data**: Metrics, timestamps, internal IDs
3. **Keep JSON-Serializable**: Only basic types (str, int, float, bool, list, dict)
4. **Meaningful Keys**: Use clear, descriptive key names

### Streaming Best Practices

1. **Regular Updates**: Send updates frequently enough to show progress
2. **Mark Final**: Always set `is_final=True` on last result
3. **Handle Cancellation**: Use try/except for asyncio.CancelledError
4. **Meaningful Progress**: Show actual progress, not just "working..."

### Error Handling

1. **Structured Errors**: Use consistent error message format
2. **Include Details**: Provide context for debugging
3. **Use Metadata**: Store stack traces and error codes in meta_info
4. **User-Friendly**: Main message should be clear to non-technical users

---

For more information, see:
- [ToolManager Documentation](manager.md)
- [Built-in Tools Guide](builtin_tools.md)
- [Workflow Toolkits](workflow_toolkits.md)
