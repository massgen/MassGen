# -*- coding: utf-8 -*-
"""
Generate a video from a text prompt with input images using OpenAI's Sora-2 API.
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


async def text_add_image_to_video_generation(
    prompt: str,
    image_paths: List[str],
    model: str = "sora-2",
    seconds: int = 4,
    storage_path: Optional[str] = None,
    allowed_paths: Optional[List[str]] = None,
) -> ExecutionResult:
    """
    Generate a video from a text prompt with input images using OpenAI's Sora-2 API.

    This tool generates a video based on a text prompt and input images using OpenAI's Sora-2 API
    and saves it to the workspace with automatic organization. The input images can be used as
    reference frames, starting frames, or visual context for the video generation.

    Args:
        prompt: Text description for the video to generate
        image_paths: List of paths to input images (PNG/JPEG/WebP files)
                    - Relative path: Resolved relative to workspace
                    - Absolute path: Must be within allowed directories
                    - Images will be used as reference/first frame for video generation
        model: Model to use (default: "sora-2", can use "sora-2-pro" for higher quality)
        seconds: Video duration in seconds (default: 4)
        storage_path: Directory path where to save the video (optional)
                     - Relative path: Resolved relative to workspace
                     - Absolute path: Must be within allowed directories
                     - None/empty: Saves to workspace root
        allowed_paths: List of allowed base paths for validation (optional)

    Returns:
        ExecutionResult containing:
        - success: Whether operation succeeded
        - operation: "generate_and_store_video_with_input_images"
        - video_path: Path to the saved video file
        - model: Model used for generation
        - prompt: The prompt used
        - source_images: List of source image paths used
        - duration: Time taken for generation in seconds

    Examples:
        generate_and_store_video_with_input_images(
            "Animate this scene with a cat walking",
            ["cat.png"]
        )
        → Generates a video starting from the cat image

        generate_and_store_video_with_input_images(
            "Create a smooth transition between these images",
            ["scene1.png", "scene2.png"],
            model="sora-2-pro",
            seconds=8
        )
        → Generates a higher quality 8-second video transitioning between images

    Security:
        - Requires valid OpenAI API key with Sora-2 access
        - Input images must be valid image files
        - Files are saved to specified path within workspace
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
                "operation": "generate_and_store_video_with_input_images",
                "error": "OpenAI API key not found. Please set OPENAI_API_KEY in .env file or environment variable.",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        # Initialize OpenAI client
        client = OpenAI(api_key=openai_api_key)

        # Validate that at least one image is provided
        if not image_paths:
            result = {
                "success": False,
                "operation": "generate_and_store_video_with_input_images",
                "error": "At least one input image is required. For text-only generation, use text_to_video_generation tool.",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        # Process and validate all input images
        validated_paths = []
        image_urls = []

        for image_path_str in image_paths:
            # Resolve image path
            if Path(image_path_str).is_absolute():
                image_path = Path(image_path_str).resolve()
            else:
                image_path = (Path.cwd() / image_path_str).resolve()

            # Validate image path
            _validate_path_access(image_path, allowed_paths_list)

            if not image_path.exists():
                result = {
                    "success": False,
                    "operation": "generate_and_store_video_with_input_images",
                    "error": f"Image file does not exist: {image_path}",
                }
                return ExecutionResult(
                    output_blocks=[TextContent(data=json.dumps(result, indent=2))],
                )

            # Allow PNG, JPEG, and WebP formats
            if image_path.suffix.lower() not in [".png", ".jpg", ".jpeg", ".webp"]:
                result = {
                    "success": False,
                    "operation": "generate_and_store_video_with_input_images",
                    "error": f"Image must be PNG, JPEG, or WebP format: {image_path}",
                }
                return ExecutionResult(
                    output_blocks=[TextContent(data=json.dumps(result, indent=2))],
                )

            validated_paths.append(image_path)

            # Read and encode image to base64 for data URL
            with open(image_path, "rb") as f:
                image_data = f.read()
            image_base64 = base64.b64encode(image_data).decode("utf-8")

            # Determine MIME type
            if image_path.suffix.lower() in [".jpg", ".jpeg"]:
                mime_type = "image/jpeg"
            elif image_path.suffix.lower() == ".webp":
                mime_type = "image/webp"
            else:
                mime_type = "image/png"

            # Create data URL for the image
            image_url = f"data:{mime_type};base64,{image_base64}"
            image_urls.append(image_url)

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
            start_time = time.time()

            # Start video generation with image inputs
            # According to OpenAI's Sora-2 API, image_urls parameter accepts a list of image URLs
            video = client.videos.create(
                model=model,
                prompt=prompt,
                seconds=str(seconds),
                image_urls=image_urls,
            )

            getattr(video, "progress", 0)

            # Monitor progress (silently, no stdout writes)
            while video.status in ("in_progress", "queued"):
                # Refresh status
                video = client.videos.retrieve(video.id)
                getattr(video, "progress", 0)
                time.sleep(2)

            if video.status == "failed":
                message = getattr(
                    getattr(video, "error", None),
                    "message",
                    "Video generation failed",
                )
                result = {
                    "success": False,
                    "operation": "generate_and_store_video_with_input_images",
                    "error": message,
                }
                return ExecutionResult(
                    output_blocks=[TextContent(data=json.dumps(result, indent=2))],
                )

            # Download video content
            content = client.videos.download_content(video.id, variant="video")

            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            clean_prompt = "".join(c for c in prompt[:30] if c.isalnum() or c in (" ", "-", "_")).strip()
            clean_prompt = clean_prompt.replace(" ", "_")
            filename = f"{timestamp}_{clean_prompt}_with_images.mp4"

            # Full file path
            file_path = storage_dir / filename

            # Write video to file
            content.write_to_file(str(file_path))

            # Calculate duration
            duration = time.time() - start_time

            # Get file size
            file_size = file_path.stat().st_size

            result = {
                "success": True,
                "operation": "generate_and_store_video_with_input_images",
                "note": "If no input images are needed, use text_to_video_generation tool instead.",
                "video_path": str(file_path),
                "filename": filename,
                "size": file_size,
                "model": model,
                "prompt": prompt,
                "source_images": [str(p) for p in validated_paths],
                "total_source_images": len(validated_paths),
                "duration": duration,
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        except Exception as api_error:
            result = {
                "success": False,
                "operation": "generate_and_store_video_with_input_images",
                "error": f"OpenAI API error: {str(api_error)}",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

    except Exception as e:
        result = {
            "success": False,
            "operation": "generate_and_store_video_with_input_images",
            "error": f"Failed to generate or save video: {str(e)}",
        }
        return ExecutionResult(
            output_blocks=[TextContent(data=json.dumps(result, indent=2))],
        )
