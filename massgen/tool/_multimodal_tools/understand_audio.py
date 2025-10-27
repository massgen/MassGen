# -*- coding: utf-8 -*-
"""
Transcribe audio file(s) to text using OpenAI's Transcription API.
"""

import json
import os
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from openai import OpenAI

from massgen.tool._result import ExecutionResult, TextContent


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


async def understand_audio(
    audio_paths: List[str],
    model: str = "gpt-4o-transcribe",
    allowed_paths: Optional[List[str]] = None,
    agent_cwd: Optional[str] = None,
) -> ExecutionResult:
    """
    Transcribe audio file(s) to text using OpenAI's Transcription API.

    This tool processes one or more audio files through OpenAI's Transcription API
    to extract the text content from the audio. Each file is processed separately.

    Args:
        audio_paths: List of paths to input audio files (WAV, MP3, M4A, etc.)
                    - Relative path: Resolved relative to workspace
                    - Absolute path: Must be within allowed directories
        model: Model to use (default: "gpt-4o-transcribe")
        allowed_paths: List of allowed base paths for validation (optional)
        agent_cwd: Current working directory of the agent (optional)

    Returns:
        ExecutionResult containing:
        - success: Whether operation succeeded
        - operation: "generate_text_with_input_audio"
        - transcriptions: List of transcription results for each file
        - audio_files: List of paths to the input audio files
        - model: Model used

    Examples:
        generate_text_with_input_audio(["recording.wav"])
        → Returns transcription for recording.wav

        generate_text_with_input_audio(["interview1.mp3", "interview2.mp3"])
        → Returns separate transcriptions for each file

    Security:
        - Requires valid OpenAI API key
        - All input audio files must exist and be readable
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
                "operation": "generate_text_with_input_audio",
                "error": "OpenAI API key not found. Please set OPENAI_API_KEY in .env file or environment variable.",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        # Initialize OpenAI client
        client = OpenAI(api_key=openai_api_key)

        # Validate and process input audio files
        validated_audio_paths = []
        audio_extensions = [".wav", ".mp3", ".m4a", ".mp4", ".ogg", ".flac", ".aac", ".wma", ".opus"]

        for audio_path_str in audio_paths:
            # Resolve audio path
            # Use agent_cwd if available, otherwise fall back to Path.cwd()
            base_dir = Path(agent_cwd) if agent_cwd else Path.cwd()

            if Path(audio_path_str).is_absolute():
                audio_path = Path(audio_path_str).resolve()
            else:
                audio_path = (base_dir / audio_path_str).resolve()

            # Validate audio path
            _validate_path_access(audio_path, allowed_paths_list)

            if not audio_path.exists():
                result = {
                    "success": False,
                    "operation": "generate_text_with_input_audio",
                    "error": f"Audio file does not exist: {audio_path}",
                }
                return ExecutionResult(
                    output_blocks=[TextContent(data=json.dumps(result, indent=2))],
                )

            # Check if file is an audio file
            if audio_path.suffix.lower() not in audio_extensions:
                result = {
                    "success": False,
                    "operation": "generate_text_with_input_audio",
                    "error": f"File does not appear to be an audio file: {audio_path}",
                }
                return ExecutionResult(
                    output_blocks=[TextContent(data=json.dumps(result, indent=2))],
                )

            validated_audio_paths.append(audio_path)

        # Process each audio file separately using OpenAI Transcription API
        transcriptions = []

        for audio_path in validated_audio_paths:
            try:
                # Open audio file
                with open(audio_path, "rb") as audio_file:
                    # Basic transcription without prompt
                    transcription = client.audio.transcriptions.create(
                        model=model,
                        file=audio_file,
                        response_format="text",
                    )

                # Add transcription to list
                transcriptions.append(
                    {
                        "file": str(audio_path),
                        "transcription": transcription,
                    },
                )

            except Exception as api_error:
                result = {
                    "success": False,
                    "operation": "generate_text_with_input_audio",
                    "error": f"Transcription API error for file {audio_path}: {str(api_error)}",
                }
                return ExecutionResult(
                    output_blocks=[TextContent(data=json.dumps(result, indent=2))],
                )

        result = {
            "success": True,
            "operation": "generate_text_with_input_audio",
            "transcriptions": transcriptions,
            "audio_files": [str(p) for p in validated_audio_paths],
            "model": model,
        }
        return ExecutionResult(
            output_blocks=[TextContent(data=json.dumps(result, indent=2))],
        )

    except Exception as e:
        result = {
            "success": False,
            "operation": "generate_text_with_input_audio",
            "error": f"Failed to transcribe audio: {str(e)}",
        }
        return ExecutionResult(
            output_blocks=[TextContent(data=json.dumps(result, indent=2))],
        )
