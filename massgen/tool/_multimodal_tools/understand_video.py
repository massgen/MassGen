# -*- coding: utf-8 -*-
"""
Understand and analyze videos by extracting key frames and using OpenAI's gpt-4.1 API.
"""

import base64
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
            "opencv-python is required for video frame extraction. " "Please install it with: pip install opencv-python",
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


async def understand_video(
    video_path: str,
    prompt: str = "What's happening in this video? Please describe the content, actions, and any important details you observe across these frames.",
    num_frames: int = 8,
    model: str = "gpt-4.1",
    allowed_paths: Optional[List[str]] = None,
    agent_cwd: Optional[str] = None,
) -> ExecutionResult:
    """
    Understand and analyze a video by extracting key frames and using OpenAI's gpt-4.1 API.

    This tool extracts key frames from a video file and processes them through OpenAI's
    gpt-4.1 API to provide insights, descriptions, or answer questions about the video content.

    Args:
        video_path: Path to the video file (MP4, AVI, MOV, etc.)
                   - Relative path: Resolved relative to workspace
                   - Absolute path: Must be within allowed directories
        prompt: Question or instruction about the video (default: asks for general description)
        num_frames: Number of key frames to extract from the video (default: 8)
                   - Higher values provide more detail but increase API costs
                   - Recommended range: 4-16 frames
        model: Model to use (default: "gpt-4.1")
        allowed_paths: List of allowed base paths for validation (optional)
        agent_cwd: Agent's current working directory (automatically injected, optional)

    Returns:
        ExecutionResult containing:
        - success: Whether operation succeeded
        - operation: "understand_video"
        - video_path: Path to the analyzed video
        - num_frames_extracted: Number of frames extracted
        - prompt: The prompt used
        - model: Model used for analysis
        - response: The model's understanding/description of the video

    Examples:
        understand_video("demo.mp4")
        → Returns detailed description of the video content

        understand_video("tutorial.mp4", "What steps are shown in this tutorial?")
        → Returns analysis of tutorial steps

        understand_video("meeting.mp4", "Summarize the key points discussed in this meeting", num_frames=12)
        → Returns meeting summary based on 12 key frames

        understand_video("sports.mp4", "What sport is being played and what are the key moments?")
        → Returns sports analysis

    Security:
        - Requires valid OpenAI API key
        - Requires opencv-python package for video processing
        - Video file must exist and be readable
        - Supports common video formats (MP4, AVI, MOV, MKV, etc.)

    Note:
        This tool extracts still frames from the video. Audio content is not analyzed.
        For audio analysis, use the generate_text_with_input_audio tool.
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
                "operation": "understand_video",
                "error": "OpenAI API key not found. Please set OPENAI_API_KEY in .env file or environment variable.",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        # Initialize OpenAI client
        client = OpenAI(api_key=openai_api_key)

        # Resolve video path
        # Use agent_cwd if available, otherwise fall back to Path.cwd()
        base_dir = Path(agent_cwd) if agent_cwd else Path.cwd()

        if Path(video_path).is_absolute():
            vid_path = Path(video_path).resolve()
        else:
            vid_path = (base_dir / video_path).resolve()

        # Validate video path
        _validate_path_access(vid_path, allowed_paths_list)

        if not vid_path.exists():
            result = {
                "success": False,
                "operation": "understand_video",
                "error": f"Video file does not exist: {vid_path}",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        # Check if file is likely a video (by extension)
        video_extensions = [".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".webm", ".m4v", ".mpg", ".mpeg"]
        if vid_path.suffix.lower() not in video_extensions:
            result = {
                "success": False,
                "operation": "understand_video",
                "error": f"File does not appear to be a video file: {vid_path}. Supported formats: {', '.join(video_extensions)}",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        # Extract key frames from video
        try:
            frames_base64 = _extract_key_frames(vid_path, num_frames)
        except ImportError as import_error:
            result = {
                "success": False,
                "operation": "understand_video",
                "error": str(import_error),
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )
        except Exception as extract_error:
            result = {
                "success": False,
                "operation": "understand_video",
                "error": f"Failed to extract frames from video: {str(extract_error)}",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        # Build content array with prompt and all frames
        content = [{"type": "input_text", "text": prompt}]

        for frame_base64 in frames_base64:
            content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:image/jpeg;base64,{frame_base64}",
                },
            )

        try:
            # Call OpenAI API for video understanding
            response = client.responses.create(
                model=model,
                input=[
                    {
                        "role": "user",
                        "content": content,
                    },
                ],
            )

            # Extract response text
            response_text = response.output_text if hasattr(response, "output_text") else str(response.output)

            result = {
                "success": True,
                "operation": "understand_video",
                "video_path": str(vid_path),
                "num_frames_extracted": len(frames_base64),
                "prompt": prompt,
                "model": model,
                "response": response_text,
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        except Exception as api_error:
            result = {
                "success": False,
                "operation": "understand_video",
                "error": f"OpenAI API error: {str(api_error)}",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

    except Exception as e:
        result = {
            "success": False,
            "operation": "understand_video",
            "error": f"Failed to understand video: {str(e)}",
        }
        return ExecutionResult(
            output_blocks=[TextContent(data=json.dumps(result, indent=2))],
        )
