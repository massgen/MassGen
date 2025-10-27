# -*- coding: utf-8 -*-
"""
Generate audio from multiple input audio files by transcribing, synthesizing, and converting to speech.
"""

import json
import os
from datetime import datetime
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


async def audio_to_audio_generation(
    audio_paths: List[str],
    synthesis_instruction: str = "Combine and synthesize the following transcriptions into a coherent narrative.",
    transcription_model: str = "gpt-4o-transcribe",
    synthesis_model: str = "gpt-4o",
    tts_model: str = "gpt-4o-mini-tts",
    voice: str = "alloy",
    speech_instructions: Optional[str] = None,
    storage_path: Optional[str] = None,
    audio_format: str = "mp3",
    allowed_paths: Optional[List[str]] = None,
    agent_cwd: Optional[str] = None,
) -> ExecutionResult:
    """
    Generate audio from multiple input audio files through transcription, synthesis, and TTS.

    This tool performs a three-step process:
    1. Transcribes all input audio files to text using OpenAI's Whisper API
    2. Synthesizes the transcriptions into a coherent text using a language model
    3. Converts the synthesized text back to audio using OpenAI's TTS API

    Args:
        audio_paths: List of paths to input audio files (WAV, MP3, M4A, etc.)
                    - Relative path: Resolved relative to workspace
                    - Absolute path: Must be within allowed directories
        synthesis_instruction: Instructions for how to synthesize the transcriptions
                              (default: "Combine and synthesize the following transcriptions into a coherent narrative.")
        transcription_model: Model for audio transcription (default: "gpt-4o-transcribe")
        synthesis_model: Model for text synthesis (default: "gpt-4o")
                        Options: "gpt-4o", "gpt-4o-mini", "gpt-4-turbo"
        tts_model: Text-to-speech model (default: "gpt-4o-mini-tts")
                  Options: "gpt-4o-mini-tts", "tts-1", "tts-1-hd"
        voice: Voice for speech synthesis (default: "alloy")
              Options: "alloy", "echo", "fable", "onyx", "nova", "shimmer", "coral", "sage"
        speech_instructions: Optional speaking instructions for tone and style
        storage_path: Directory path where to save the output audio (optional)
                     - Relative path: Resolved relative to agent's workspace
                     - Absolute path: Must be within allowed directories
                     - None/empty: Saves to agent's workspace root
        audio_format: Output audio format (default: "mp3")
                     Options: "mp3", "opus", "aac", "flac", "wav", "pcm"
        allowed_paths: List of allowed base paths for validation (optional)
        agent_cwd: Agent's current working directory (automatically injected)

    Returns:
        ExecutionResult containing:
        - success: Whether operation succeeded
        - operation: "audio_to_audio_generation"
        - input_audio_files: List of input audio file paths
        - transcriptions: Individual transcriptions from each audio file
        - synthesized_text: The final synthesized text
        - output_audio: Generated audio file with path and metadata
        - models_used: Dictionary of models used for each step

    Examples:
        audio_to_audio_generation(
            audio_paths=["interview1.mp3", "interview2.mp3"],
            synthesis_instruction="Combine these interviews into a single summary"
        )
        → Transcribes both interviews, combines them, and generates a summary audio

        audio_to_audio_generation(
            audio_paths=["chapter1.wav", "chapter2.wav", "chapter3.wav"],
            synthesis_instruction="Create a smooth transition between these chapters",
            voice="nova",
            speech_instructions="Speak in a storytelling tone"
        )
        → Creates an audiobook with smooth chapter transitions

        audio_to_audio_generation(
            audio_paths=["lecture_part1.mp3", "lecture_part2.mp3"],
            synthesis_instruction="Summarize the key points from these lecture recordings",
            storage_path="output/summaries/"
        )
        → Creates a summarized audio from lecture recordings

    Security:
        - Requires valid OpenAI API key
        - All input audio files must exist and be readable
        - Supports common audio formats (WAV, MP3, M4A, etc.)
    """
    try:
        # Convert allowed_paths from strings to Path objects
        allowed_paths_list = [Path(p) for p in allowed_paths] if allowed_paths else None

        # Use agent_cwd if available, otherwise fall back to Path.cwd()
        base_dir = Path(agent_cwd) if agent_cwd else Path.cwd()

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
                "operation": "audio_to_audio_generation",
                "error": "OpenAI API key not found. Please set OPENAI_API_KEY in .env file or environment variable.",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        # Initialize OpenAI client
        client = OpenAI(api_key=openai_api_key)

        # Step 1: Validate and transcribe all input audio files
        validated_audio_paths = []
        transcriptions = []
        audio_extensions = [".wav", ".mp3", ".m4a", ".mp4", ".ogg", ".flac", ".aac", ".wma", ".opus"]

        for audio_path_str in audio_paths:
            # Resolve audio path
            if Path(audio_path_str).is_absolute():
                audio_path = Path(audio_path_str).resolve()
            else:
                audio_path = (base_dir / audio_path_str).resolve()

            # Validate audio path
            _validate_path_access(audio_path, allowed_paths_list)

            if not audio_path.exists():
                result = {
                    "success": False,
                    "operation": "audio_to_audio_generation",
                    "error": f"Audio file does not exist: {audio_path}",
                }
                return ExecutionResult(
                    output_blocks=[TextContent(data=json.dumps(result, indent=2))],
                )

            # Check if file is an audio file
            if audio_path.suffix.lower() not in audio_extensions:
                result = {
                    "success": False,
                    "operation": "audio_to_audio_generation",
                    "error": f"File does not appear to be an audio file: {audio_path}",
                }
                return ExecutionResult(
                    output_blocks=[TextContent(data=json.dumps(result, indent=2))],
                )

            validated_audio_paths.append(audio_path)

            # Transcribe audio file
            try:
                with open(audio_path, "rb") as audio_file:
                    transcription = client.audio.transcriptions.create(
                        model=transcription_model,
                        file=audio_file,
                        response_format="text",
                    )

                transcriptions.append(
                    {
                        "file": str(audio_path),
                        "text": transcription,
                    },
                )

            except Exception as api_error:
                result = {
                    "success": False,
                    "operation": "audio_to_audio_generation",
                    "step": "transcription",
                    "error": f"Transcription API error for file {audio_path}: {str(api_error)}",
                }
                return ExecutionResult(
                    output_blocks=[TextContent(data=json.dumps(result, indent=2))],
                )

        # Step 2: Synthesize transcriptions into a single text
        try:
            # Prepare the transcription texts
            transcription_texts = "\n\n---\n\n".join(
                [f"Audio {i+1} ({t['file']}):\n{t['text']}" for i, t in enumerate(transcriptions)]
            )

            # Use chat completion to synthesize
            response = client.chat.completions.create(
                model=synthesis_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that synthesizes multiple audio transcriptions into coherent text.",
                    },
                    {
                        "role": "user",
                        "content": f"{synthesis_instruction}\n\nTranscriptions:\n{transcription_texts}",
                    },
                ],
                temperature=0.7,
            )

            synthesized_text = response.choices[0].message.content.strip()

        except Exception as api_error:
            result = {
                "success": False,
                "operation": "audio_to_audio_generation",
                "step": "synthesis",
                "error": f"Text synthesis API error: {str(api_error)}",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        # Step 3: Convert synthesized text to audio
        try:
            # Determine storage directory
            if storage_path:
                if Path(storage_path).is_absolute():
                    storage_dir = Path(storage_path).resolve()
                else:
                    storage_dir = (base_dir / storage_path).resolve()
            else:
                storage_dir = base_dir

            # Validate storage directory
            _validate_path_access(storage_dir, allowed_paths_list)
            storage_dir.mkdir(parents=True, exist_ok=True)

            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # Clean text for filename (first 30 chars)
            clean_text = "".join(c for c in synthesized_text[:30] if c.isalnum() or c in (" ", "-", "_")).strip()
            clean_text = clean_text.replace(" ", "_")

            filename = f"synthesized_audio_{timestamp}_{clean_text}.{audio_format}"
            file_path = storage_dir / filename

            # Prepare TTS request parameters
            request_params = {
                "model": tts_model,
                "voice": voice,
                "input": synthesized_text,
            }

            # Add speech instructions if provided (only for models that support it)
            if speech_instructions and tts_model in ["gpt-4o-mini-tts"]:
                request_params["instructions"] = speech_instructions

            # Generate audio using streaming response
            with client.audio.speech.with_streaming_response.create(**request_params) as response:
                response.stream_to_file(file_path)

            # Get file size
            file_size = file_path.stat().st_size

            result = {
                "success": True,
                "operation": "audio_to_audio_generation",
                "input_audio_files": [str(p) for p in validated_audio_paths],
                "transcriptions": transcriptions,
                "synthesized_text": synthesized_text,
                "output_audio": {
                    "file_path": str(file_path),
                    "filename": filename,
                    "size": file_size,
                    "format": audio_format,
                    "voice": voice,
                },
                "models_used": {
                    "transcription": transcription_model,
                    "synthesis": synthesis_model,
                    "tts": tts_model,
                },
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        except Exception as api_error:
            result = {
                "success": False,
                "operation": "audio_to_audio_generation",
                "step": "text_to_speech",
                "error": f"TTS API error: {str(api_error)}",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

    except Exception as e:
        result = {
            "success": False,
            "operation": "audio_to_audio_generation",
            "error": f"Failed to generate audio: {str(e)}",
        }
        return ExecutionResult(
            output_blocks=[TextContent(data=json.dumps(result, indent=2))],
        )
