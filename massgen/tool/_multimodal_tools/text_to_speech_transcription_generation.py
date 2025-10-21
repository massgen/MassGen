# -*- coding: utf-8 -*-
"""
Convert text (transcription) directly to speech using OpenAI's TTS API with streaming response.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from openai import OpenAI

from .._result import ExecutionResult, TextContent


def _validate_path_access(path: Path, allowed_paths: Optional[List[Path]] = None) -> None:
    """
    Validate that a path is within allowed directories.

    Args:
        path: Path to validate
        allowed_paths: List of allowed base paths (optional)

    Raises:
        ValueError: If path is not within allowed directories
    """
    if not allowed_paths:
        return  # No restrictions

    for allowed_path in allowed_paths:
        try:
            path.relative_to(allowed_path)
            return  # Path is within this allowed directory
        except ValueError:
            continue

    raise ValueError(f"Path not in allowed directories: {path}")


async def text_to_speech_transcription_generation(
    input_text: str,
    model: str = "gpt-4o-mini-tts",
    voice: str = "alloy",
    instructions: Optional[str] = None,
    storage_path: Optional[str] = None,
    audio_format: str = "mp3",
    allowed_paths: Optional[List[str]] = None,
) -> ExecutionResult:
    """
    Convert text (transcription) directly to speech using OpenAI's TTS API with streaming response.

    This tool converts text directly to speech audio using OpenAI's Text-to-Speech API,
    designed specifically for converting transcriptions or any text content to spoken audio.
    Uses streaming response for efficient file handling.

    Args:
        input_text: The text content to convert to speech (e.g., transcription text)
        model: TTS model to use (default: "gpt-4o-mini-tts")
               Options: "gpt-4o-mini-tts", "tts-1", "tts-1-hd"
        voice: Voice to use for speech synthesis (default: "alloy")
               Options: "alloy", "echo", "fable", "onyx", "nova", "shimmer", "coral", "sage"
        instructions: Optional speaking instructions for tone and style (e.g., "Speak in a cheerful tone")
        storage_path: Directory path where to save the audio file (optional)
                     - Relative path: Resolved relative to workspace
                     - Absolute path: Must be within allowed directories
                     - None/empty: Saves to workspace root
        audio_format: Output audio format (default: "mp3")
                     Options: "mp3", "opus", "aac", "flac", "wav", "pcm"
        allowed_paths: List of allowed base paths for validation (optional)

    Returns:
        ExecutionResult containing:
        - success: Whether operation succeeded
        - operation: "convert_text_to_speech"
        - audio_file: Generated audio file with path and metadata
        - model: TTS model used
        - voice: Voice used
        - format: Audio format used
        - text_length: Length of input text
        - instructions: Speaking instructions if provided

    Examples:
        convert_text_to_speech("Hello world, this is a test.")
        → Converts text to speech and saves as MP3

        convert_text_to_speech(
            "Today is a wonderful day to build something people love!",
            voice="coral",
            instructions="Speak in a cheerful and positive tone."
        )
        → Converts with specific voice and speaking instructions

    Security:
        - Requires valid OpenAI API key
        - Files are saved to specified path within workspace
        - Path must be within allowed directories
    """
    try:
        # Convert allowed_paths from strings to Path objects
        allowed_paths_list = [Path(p) for p in allowed_paths] if allowed_paths else None

        # Load environment variables
        script_dir = Path(__file__).parent.parent.parent.parent
        env_path = script_dir / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        else:
            load_dotenv()

        openai_api_key = os.getenv("OPENAI_API_KEY")

        if not openai_api_key:
            result = {
                "success": False,
                "operation": "convert_text_to_speech",
                "error": "OpenAI API key not found. Please set OPENAI_API_KEY in .env file or environment variable.",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        # Initialize OpenAI client
        client = OpenAI(api_key=openai_api_key)

        # Determine storage directory
        if storage_path:
            if Path(storage_path).is_absolute():
                storage_dir = Path(storage_path).resolve()
            else:
                storage_dir = (Path.cwd() / storage_path).resolve()
        else:
            storage_dir = Path.cwd()

        # Validate storage directory is within allowed paths
        _validate_path_access(storage_dir, allowed_paths_list)

        # Create directory if it doesn't exist
        storage_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Clean text for filename (first 30 chars)
        clean_text = "".join(c for c in input_text[:30] if c.isalnum() or c in (" ", "-", "_")).strip()
        clean_text = clean_text.replace(" ", "_")

        filename = f"speech_{timestamp}_{clean_text}.{audio_format}"
        file_path = storage_dir / filename

        try:
            # Prepare request parameters
            request_params = {
                "model": model,
                "voice": voice,
                "input": input_text,
            }

            # Add instructions if provided (only for models that support it)
            if instructions and model in ["gpt-4o-mini-tts"]:
                request_params["instructions"] = instructions

            # Use streaming response for efficient file handling
            with client.audio.speech.with_streaming_response.create(**request_params) as response:
                # Stream directly to file
                response.stream_to_file(file_path)

            # Get file size
            file_size = file_path.stat().st_size

            result = {
                "success": True,
                "operation": "convert_text_to_speech",
                "audio_file": {
                    "file_path": str(file_path),
                    "filename": filename,
                    "size": file_size,
                    "format": audio_format,
                },
                "model": model,
                "voice": voice,
                "format": audio_format,
                "text_length": len(input_text),
                "instructions": instructions if instructions else None,
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        except Exception as api_error:
            result = {
                "success": False,
                "operation": "convert_text_to_speech",
                "error": f"OpenAI TTS API error: {str(api_error)}",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

    except Exception as e:
        result = {
            "success": False,
            "operation": "convert_text_to_speech",
            "error": f"Failed to convert text to speech: {str(e)}",
        }
        return ExecutionResult(
            output_blocks=[TextContent(data=json.dumps(result, indent=2))],
        )
