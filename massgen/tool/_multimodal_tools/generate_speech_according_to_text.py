# -*- coding: utf-8 -*-
"""
Generate audio from text using OpenAI's gpt-4o-audio-preview model and store it in the workspace.
"""

import base64
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

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


async def generate_speech_according_to_text(
    prompt: str,
    model: str = "gpt-4o-audio-preview",
    voice: str = "alloy",
    audio_format: str = "wav",
    storage_path: Optional[str] = None,
    allowed_paths: Optional[List[str]] = None,
) -> ExecutionResult:
    """
    Generate audio from text using OpenAI's gpt-4o-audio-preview model and store it in the workspace.

    This tool generates audio speech from text prompts using OpenAI's audio generation API
    and saves the audio files to the workspace with automatic organization.

    Args:
        prompt: Text content to convert to audio speech
        model: Model to use for generation (default: "gpt-4o-audio-preview")
        voice: Voice to use for audio generation (default: "alloy")
               Options: "alloy", "echo", "fable", "onyx", "nova", "shimmer"
        audio_format: Audio format for output (default: "wav")
                     Options: "wav", "mp3", "opus", "aac", "flac"
        storage_path: Directory path where to save the audio (optional)
                     - Relative path: Resolved relative to workspace (e.g., "audio/generated")
                     - Absolute path: Must be within allowed directories
                     - None/empty: Saves to workspace root
        allowed_paths: List of allowed base paths for validation (optional)

    Returns:
        ExecutionResult containing:
        - success: Whether operation succeeded
        - operation: "generate_and_store_audio_no_input_audios"
        - audio_file: Generated audio file with path and metadata
        - model: Model used for generation
        - prompt: The prompt used for generation
        - voice: Voice used for generation
        - format: Audio format used

    Examples:
        generate_and_store_audio_no_input_audios("Is a golden retriever a good family dog?")
        → Generates and saves to: 20240115_143022_audio.wav

        generate_and_store_audio_no_input_audios("Hello world", voice="nova", audio_format="mp3")
        → Generates with nova voice and saves as: 20240115_143022_audio.mp3

    Security:
        - Requires valid OpenAI API key (automatically detected from .env or environment)
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
                "operation": "generate_and_store_audio_no_input_audios",
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

        try:
            # Generate audio using OpenAI API
            completion = client.chat.completions.create(
                model=model,
                modalities=["text", "audio"],
                audio={"voice": voice, "format": audio_format},
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
            )

            # Check if audio data is available
            if not completion.choices[0].message.audio or not completion.choices[0].message.audio.data:
                result = {
                    "success": False,
                    "operation": "generate_and_store_audio_no_input_audios",
                    "error": "No audio data received from API",
                }
                return ExecutionResult(
                    output_blocks=[TextContent(data=json.dumps(result, indent=2))],
                )

            # Decode audio data from base64
            audio_bytes = base64.b64decode(completion.choices[0].message.audio.data)

            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # Clean prompt for filename (first 30 chars)
            clean_prompt = "".join(c for c in prompt[:30] if c.isalnum() or c in (" ", "-", "_")).strip()
            clean_prompt = clean_prompt.replace(" ", "_")

            filename = f"{timestamp}_{clean_prompt}.{audio_format}"

            # Full file path
            file_path = storage_dir / filename

            # Write audio to file
            file_path.write_bytes(audio_bytes)
            file_size = len(audio_bytes)

            # Get text response if available
            text_response = completion.choices[0].message.content if completion.choices[0].message.content else None

            result = {
                "success": True,
                "operation": "generate_and_store_audio_no_input_audios",
                "audio_file": {
                    "file_path": str(file_path),
                    "filename": filename,
                    "size": file_size,
                    "format": audio_format,
                },
                "model": model,
                "prompt": prompt,
                "voice": voice,
                "format": audio_format,
                "text_response": text_response,
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        except Exception as api_error:
            result = {
                "success": False,
                "operation": "generate_and_store_audio_no_input_audios",
                "error": f"OpenAI API error: {str(api_error)}",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

    except Exception as e:
        result = {
            "success": False,
            "operation": "generate_and_store_audio_no_input_audios",
            "error": f"Failed to generate or save audio: {str(e)}",
        }
        return ExecutionResult(
            output_blocks=[TextContent(data=json.dumps(result, indent=2))],
        )
