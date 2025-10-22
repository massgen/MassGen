# -*- coding: utf-8 -*-
"""
Remix videos using OpenAI's Sora video remix API.
"""

import json
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

from .._result import ExecutionResult, TextContent


async def edit_video(
    video_id: str,
    prompt: str,
    model: str = "sora-2",
) -> ExecutionResult:
    """
    Create a video remix using OpenAI's Sora video API.

    This tool takes an existing video ID and a text prompt to generate a new remixed
    video based on the instructions. The remix can extend, modify, or alter the
    original video according to the prompt.

    Args:
        video_id: The identifier of the completed video to remix (e.g., "video_123")
        prompt: Text description of how to remix the video
        model: Model to use (default: "sora-2")

    Returns:
        ExecutionResult containing:
        - success: Whether operation succeeded
        - operation: "edit_video"
        - video_id: The new remixed video ID
        - status: Current status of the remix job (e.g., "queued", "processing", "completed")
        - progress: Progress percentage (0-100)
        - model: Model used for remixing
        - size: Video dimensions (e.g., "720x1280")
        - seconds: Video duration in seconds
        - remixed_from_video_id: Original video ID that was remixed
        - created_at: Unix timestamp of creation

    Examples:
        edit_video(
            video_id="video_123",
            prompt="Extend the scene with the cat taking a bow to the cheering audience"
        )
        → Creates a remix extending the original video

        edit_video(
            video_id="video_456",
            prompt="Add dramatic lighting and slow motion effect to the action sequence"
        )
        → Creates a remix with visual effects

        edit_video(
            video_id="video_789",
            prompt="Change the setting from day to night while keeping the same action"
        )
        → Creates a remix with modified environment

    Security:
        - Requires valid OpenAI API key
        - Video ID must refer to a completed video
        - Only Sora models support video remix
    """
    try:
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
                "operation": "edit_video",
                "error": "OpenAI API key not found. Please set OPENAI_API_KEY in .env file or environment variable.",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        # Initialize OpenAI client
        client = OpenAI(api_key=openai_api_key)

        try:
            # Call OpenAI video remix API
            video = client.videos.remix(
                video_id=video_id,
                prompt=prompt,
            )

            # Build result with video information
            result = {
                "success": True,
                "operation": "edit_video",
                "video_id": video.id,
                "status": video.status,
                "progress": video.progress,
                "model": video.model,
                "prompt": prompt,
                "created_at": video.created_at,
            }

            # Add optional fields if available
            if hasattr(video, "size") and video.size:
                result["size"] = video.size
            if hasattr(video, "seconds") and video.seconds:
                result["seconds"] = video.seconds
            if hasattr(video, "remixed_from_video_id") and video.remixed_from_video_id:
                result["remixed_from_video_id"] = video.remixed_from_video_id

            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        except Exception as api_error:
            result = {
                "success": False,
                "operation": "edit_video",
                "error": f"OpenAI API error: {str(api_error)}",
                "video_id": video_id,
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

    except Exception as e:
        result = {
            "success": False,
            "operation": "edit_video",
            "error": f"Failed to remix video: {str(e)}",
        }
        return ExecutionResult(
            output_blocks=[TextContent(data=json.dumps(result, indent=2))],
        )
