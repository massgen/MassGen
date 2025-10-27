# -*- coding: utf-8 -*-
"""
Generate video from multiple input videos by understanding, synthesizing, and creating new video.
"""

import base64
import json
import os
import time
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
        agent_cwd: Agent\'s current working directory (automatically injected)

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


def _extract_key_frames(video_path: Path, num_frames: int = 8) -> List[str]:
    """
    Extract key frames from a video file.

    Args:
        video_path: Path to the video file
        num_frames: Number of key frames to extract

    Returns:
        List of base64-encoded frame images

    Raises:
        ImportError: If opencv-python is not installed
        Exception: If frame extraction fails
    """
    try:
        import cv2
    except ImportError:
        raise ImportError(
            "opencv-python is required for video frame extraction. "
            "Please install it with: pip install opencv-python"
        )

    # Open the video file
    video = cv2.VideoCapture(str(video_path))

    if not video.isOpened():
        raise Exception(f"Failed to open video file: {video_path}")

    try:
        # Get total number of frames
        total_frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))

        if total_frames == 0:
            raise Exception(f"Video file has no frames: {video_path}")

        # Calculate frame indices to extract (evenly spaced)
        frame_indices = []
        if num_frames >= total_frames:
            # If requesting more frames than available, use all frames
            frame_indices = list(range(total_frames))
        else:
            # Extract evenly spaced frames
            step = total_frames / num_frames
            frame_indices = [int(i * step) for i in range(num_frames)]

        # Extract frames
        frames_base64 = []
        for frame_idx in frame_indices:
            # Set video position to the frame
            video.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)

            # Read the frame
            ret, frame = video.read()

            if not ret:
                continue

            # Encode frame to JPEG
            ret, buffer = cv2.imencode(".jpg", frame)

            if not ret:
                continue

            # Convert to base64
            frame_base64 = base64.b64encode(buffer).decode("utf-8")
            frames_base64.append(frame_base64)

        if not frames_base64:
            raise Exception("Failed to extract any frames from video")

        return frames_base64

    finally:
        # Release the video capture object
        video.release()


async def video_to_video_generation(
    video_paths: List[str],
    synthesis_instruction: str = "Combine and synthesize the following video descriptions into a coherent narrative for a new video.",
    num_frames_per_video: int = 6,
    understanding_model: str = "gpt-4.1",
    synthesis_model: str = "gpt-4o",
    video_generation_model: str = "sora-2",
    video_seconds: int = 4,
    storage_path: Optional[str] = None,
    allowed_paths: Optional[List[str]] = None,
    agent_cwd: Optional[str] = None,
) -> ExecutionResult:
    """
    Generate video from multiple input videos through understanding, synthesis, and video generation.

    This tool performs a three-step process:
    1. Understands each input video by extracting key frames and analyzing them with gpt-4.1
    2. Synthesizes the video descriptions into a coherent text prompt using a language model
    3. Generates a new video from the synthesized prompt using OpenAI's Sora-2 API

    Args:
        video_paths: List of paths to input video files (MP4, AVI, MOV, etc.)
                    - Relative path: Resolved relative to agent's workspace
                    - Absolute path: Must be within allowed directories
        synthesis_instruction: Instructions for how to synthesize the video descriptions
                              (default: "Combine and synthesize the following video descriptions into a coherent narrative for a new video.")
        num_frames_per_video: Number of key frames to extract from each video (default: 6)
                             - Higher values provide more detail but increase API costs
                             - Recommended range: 4-12 frames
        understanding_model: Model for video understanding (default: "gpt-4.1")
        synthesis_model: Model for text synthesis (default: "gpt-4o")
                        Options: "gpt-4o", "gpt-4o-mini", "gpt-4-turbo"
        video_generation_model: Model for video generation (default: "sora-2")
        video_seconds: Duration of generated video in seconds (default: 4)
        storage_path: Directory path where to save the output video (optional)
                     - Relative path: Resolved relative to agent's workspace
                     - Absolute path: Must be within allowed directories
                     - None/empty: Saves to agent's workspace root
        allowed_paths: List of allowed base paths for validation (optional)
        agent_cwd: Agent\'s current working directory (automatically injected)

    Returns:
        ExecutionResult containing:
        - success: Whether operation succeeded
        - operation: "video_to_video_generation"
        - input_video_files: List of input video file paths
        - video_understandings: Descriptions/understandings of each video
        - synthesized_prompt: The final synthesized video prompt
        - output_video: Generated video file with path and metadata
        - models_used: Dictionary of models used for each step
        - generation_duration: Time taken for video generation

    Examples:
        video_to_video_generation(
            video_paths=["clip1.mp4", "clip2.mp4"],
            synthesis_instruction="Combine these video clips into a cohesive story"
        )
        → Analyzes both clips, combines them, and generates a new video

        video_to_video_generation(
            video_paths=["scene1.mp4", "scene2.mp4", "scene3.mp4"],
            synthesis_instruction="Create a dramatic montage from these scenes",
            video_seconds=8,
            num_frames_per_video=8
        )
        → Creates an 8-second dramatic montage video

        video_to_video_generation(
            video_paths=["demo1.mp4", "demo2.mp4"],
            synthesis_instruction="Create a product showcase video combining the best elements",
            storage_path="output/videos/"
        )
        → Creates a product showcase video from multiple demos

    Security:
        - Requires valid OpenAI API key with Sora-2 access
        - Requires opencv-python package for video processing
        - All input video files must exist and be readable
        - Supports common video formats (MP4, AVI, MOV, MKV, etc.)

    Note:
        This tool analyzes video content through visual frames only.
        Audio content from input videos is not included in the analysis or output.
    """
    try:
        # Convert allowed_paths from strings to Path objects
        allowed_paths_list = [Path(p) for p in allowed_paths] if allowed_paths else None

        # Use agent_cwd if available, otherwise fall back to base_dir
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
                "operation": "video_to_video_generation",
                "error": "OpenAI API key not found. Please set OPENAI_API_KEY in .env file or environment variable.",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        # Initialize OpenAI client
        client = OpenAI(api_key=openai_api_key)

        # Step 1: Validate and understand all input videos
        validated_video_paths = []
        video_understandings = []
        video_extensions = [".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".webm", ".m4v", ".mpg", ".mpeg"]

        for video_path_str in video_paths:
            # Resolve video path
            if Path(video_path_str).is_absolute():
                video_path = Path(video_path_str).resolve()
            else:
                video_path = (base_dir / video_path_str).resolve()

            # Validate video path
            _validate_path_access(video_path, allowed_paths_list)

            if not video_path.exists():
                result = {
                    "success": False,
                    "operation": "video_to_video_generation",
                    "error": f"Video file does not exist: {video_path}",
                }
                return ExecutionResult(
                    output_blocks=[TextContent(data=json.dumps(result, indent=2))],
                )

            # Check if file is a video file
            if video_path.suffix.lower() not in video_extensions:
                result = {
                    "success": False,
                    "operation": "video_to_video_generation",
                    "error": f"File does not appear to be a video file: {video_path}. Supported formats: {', '.join(video_extensions)}",
                }
                return ExecutionResult(
                    output_blocks=[TextContent(data=json.dumps(result, indent=2))],
                )

            validated_video_paths.append(video_path)

            # Extract key frames and understand video
            try:
                frames_base64 = _extract_key_frames(video_path, num_frames_per_video)
            except ImportError as import_error:
                result = {
                    "success": False,
                    "operation": "video_to_video_generation",
                    "error": str(import_error),
                }
                return ExecutionResult(
                    output_blocks=[TextContent(data=json.dumps(result, indent=2))],
                )
            except Exception as extract_error:
                result = {
                    "success": False,
                    "operation": "video_to_video_generation",
                    "step": "frame_extraction",
                    "error": f"Failed to extract frames from video {video_path}: {str(extract_error)}",
                }
                return ExecutionResult(
                    output_blocks=[TextContent(data=json.dumps(result, indent=2))],
                )

            # Build content array with frames
            content = [
                {
                    "type": "input_text",
                    "text": "Describe this video in detail. Include the key visual elements, actions, scenes, mood, and any important details that would be useful for recreating or understanding the video content.",
                }
            ]

            for frame_base64 in frames_base64:
                content.append(
                    {
                        "type": "input_image",
                        "image_url": f"data:image/jpeg;base64,{frame_base64}",
                    }
                )

            try:
                # Call OpenAI API for video understanding
                response = client.responses.create(
                    model=understanding_model,
                    input=[
                        {
                            "role": "user",
                            "content": content,
                        }
                    ],
                )

                # Extract response text
                understanding = response.output_text if hasattr(response, "output_text") else str(response.output)

                video_understandings.append(
                    {
                        "file": str(video_path),
                        "description": understanding,
                        "frames_analyzed": len(frames_base64),
                    }
                )

            except Exception as api_error:
                result = {
                    "success": False,
                    "operation": "video_to_video_generation",
                    "step": "video_understanding",
                    "error": f"Video understanding API error for file {video_path}: {str(api_error)}",
                }
                return ExecutionResult(
                    output_blocks=[TextContent(data=json.dumps(result, indent=2))],
                )

        # Step 2: Synthesize video descriptions into a single prompt
        try:
            # Prepare the video descriptions
            description_texts = "\n\n---\n\n".join(
                [f"Video {i+1} ({v['file']}):\n{v['description']}" for i, v in enumerate(video_understandings)]
            )

            # Use chat completion to synthesize
            response = client.chat.completions.create(
                model=synthesis_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that synthesizes multiple video descriptions into a single, coherent video generation prompt. The output should be a clear, concise prompt suitable for video generation AI.",
                    },
                    {
                        "role": "user",
                        "content": f"{synthesis_instruction}\n\nVideo Descriptions:\n{description_texts}",
                    },
                ],
                temperature=0.7,
            )

            synthesized_prompt = response.choices[0].message.content.strip()

        except Exception as api_error:
            result = {
                "success": False,
                "operation": "video_to_video_generation",
                "step": "synthesis",
                "error": f"Prompt synthesis API error: {str(api_error)}",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        # Step 3: Generate new video from synthesized prompt
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

            start_time = time.time()

            # Start video generation
            video = client.videos.create(
                model=video_generation_model,
                prompt=synthesized_prompt,
                seconds=str(video_seconds),
            )

            # Monitor progress
            while video.status in ("in_progress", "queued"):
                video = client.videos.retrieve(video.id)
                time.sleep(2)

            if video.status == "failed":
                message = getattr(
                    getattr(video, "error", None),
                    "message",
                    "Video generation failed",
                )
                result = {
                    "success": False,
                    "operation": "video_to_video_generation",
                    "step": "video_generation",
                    "error": message,
                }
                return ExecutionResult(
                    output_blocks=[TextContent(data=json.dumps(result, indent=2))],
                )

            # Download video content
            content = client.videos.download_content(video.id, variant="video")

            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            clean_prompt = "".join(c for c in synthesized_prompt[:30] if c.isalnum() or c in (" ", "-", "_")).strip()
            clean_prompt = clean_prompt.replace(" ", "_")
            filename = f"synthesized_video_{timestamp}_{clean_prompt}.mp4"

            # Full file path
            file_path = storage_dir / filename

            # Write video to file
            content.write_to_file(str(file_path))

            # Calculate duration
            generation_duration = time.time() - start_time

            # Get file size
            file_size = file_path.stat().st_size

            result = {
                "success": True,
                "operation": "video_to_video_generation",
                "input_video_files": [str(p) for p in validated_video_paths],
                "video_understandings": video_understandings,
                "synthesized_prompt": synthesized_prompt,
                "output_video": {
                    "file_path": str(file_path),
                    "filename": filename,
                    "size": file_size,
                    "duration_seconds": video_seconds,
                },
                "models_used": {
                    "understanding": understanding_model,
                    "synthesis": synthesis_model,
                    "video_generation": video_generation_model,
                },
                "generation_duration": generation_duration,
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        except Exception as api_error:
            result = {
                "success": False,
                "operation": "video_to_video_generation",
                "step": "video_generation",
                "error": f"Video generation API error: {str(api_error)}",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

    except Exception as e:
        result = {
            "success": False,
            "operation": "video_to_video_generation",
            "error": f"Failed to generate video: {str(e)}",
        }
        return ExecutionResult(
            output_blocks=[TextContent(data=json.dumps(result, indent=2))],
        )
