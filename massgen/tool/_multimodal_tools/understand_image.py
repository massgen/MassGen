# -*- coding: utf-8 -*-
"""
Understand and analyze images using OpenAI's gpt-4.1 API.
"""

import base64
import json
import os
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


async def understand_image(
    image_path: str,
    prompt: str = "What's in this image? Please describe it in detail.",
    model: str = "gpt-4.1",
    allowed_paths: Optional[List[str]] = None,
) -> ExecutionResult:
    """
    Understand and analyze an image using OpenAI's gpt-4.1 API.

    This tool processes an image through OpenAI's gpt-4.1 API to extract insights,
    descriptions, or answer questions about the image content.

    Args:
        image_path: Path to the image file (PNG/JPEG/JPG)
                   - Relative path: Resolved relative to workspace
                   - Absolute path: Must be within allowed directories
        prompt: Question or instruction about the image (default: "What's in this image? Please describe it in detail.")
        model: Model to use (default: "gpt-4.1")
        allowed_paths: List of allowed base paths for validation (optional)

    Returns:
        ExecutionResult containing:
        - success: Whether operation succeeded
        - operation: "understand_image"
        - image_path: Path to the analyzed image
        - prompt: The prompt used
        - model: Model used for analysis
        - response: The model's understanding/description of the image

    Examples:
        understand_image("photo.jpg")
        → Returns detailed description of the image

        understand_image("chart.png", "What data is shown in this chart?")
        → Returns analysis of the chart data

        understand_image("screenshot.png", "What UI elements are visible in this screenshot?")
        → Returns description of UI elements

    Security:
        - Requires valid OpenAI API key
        - Image file must exist and be readable
        - Only supports PNG, JPEG, and JPG formats
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
                "operation": "understand_image",
                "error": "OpenAI API key not found. Please set OPENAI_API_KEY in .env file or environment variable.",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        # Initialize OpenAI client
        client = OpenAI(api_key=openai_api_key)

        # Resolve image path
        if Path(image_path).is_absolute():
            img_path = Path(image_path).resolve()
        else:
            img_path = (Path.cwd() / image_path).resolve()

        # Validate image path
        _validate_path_access(img_path, allowed_paths_list)

        if not img_path.exists():
            result = {
                "success": False,
                "operation": "understand_image",
                "error": f"Image file does not exist: {img_path}",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        # Check file format
        if img_path.suffix.lower() not in [".png", ".jpg", ".jpeg"]:
            result = {
                "success": False,
                "operation": "understand_image",
                "error": f"Image must be PNG, JPEG, or JPG format: {img_path}",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        # Read and encode image to base64
        try:
            with open(img_path, "rb") as image_file:
                image_data = image_file.read()
            base64_image = base64.b64encode(image_data).decode("utf-8")
        except Exception as read_error:
            result = {
                "success": False,
                "operation": "understand_image",
                "error": f"Failed to read image file: {str(read_error)}",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        # Determine MIME type
        mime_type = "image/jpeg" if img_path.suffix.lower() in [".jpg", ".jpeg"] else "image/png"

        try:
            # Call OpenAI API for image understanding
            response = client.responses.create(
                model=model,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": prompt},
                            {
                                "type": "input_image",
                                "image_url": f"data:{mime_type};base64,{base64_image}",
                            },
                        ],
                    }
                ],
            )

            # Extract response text
            response_text = response.output_text if hasattr(response, "output_text") else str(response.output)

            result = {
                "success": True,
                "operation": "understand_image",
                "image_path": str(img_path),
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
                "operation": "understand_image",
                "error": f"OpenAI API error: {str(api_error)}",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

    except Exception as e:
        result = {
            "success": False,
            "operation": "understand_image",
            "error": f"Failed to understand image: {str(e)}",
        }
        return ExecutionResult(
            output_blocks=[TextContent(data=json.dumps(result, indent=2))],
        )
