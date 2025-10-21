# -*- coding: utf-8 -*-
"""
Edit and combine multiple images using OpenAI's gpt-image-1 API.
"""

import base64
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


async def edit_images(
    image_paths: List[str],
    prompt: str,
    model: str = "gpt-image-1",
    storage_path: Optional[str] = None,
    allowed_paths: Optional[List[str]] = None,
) -> ExecutionResult:
    """
    Edit and combine multiple images using OpenAI's gpt-image-1 API.

    This tool takes multiple input images and a text prompt to generate a new edited
    image based on the instructions. It can combine, modify, or recreate images
    according to the prompt.

    Args:
        image_paths: List of paths to input images (PNG/JPEG files)
                    - Relative path: Resolved relative to workspace
                    - Absolute path: Must be within allowed directories
        prompt: Text description of how to edit/combine the images
        model: Model to use (default: "gpt-image-1")
        storage_path: Directory path where to save the edited image (optional)
                     - Relative path: Resolved relative to workspace
                     - Absolute path: Must be within allowed directories
                     - None/empty: Saves to workspace root
        allowed_paths: List of allowed base paths for validation (optional)

    Returns:
        ExecutionResult containing:
        - success: Whether operation succeeded
        - operation: "edit_images"
        - input_images: List of input image paths
        - prompt: The prompt used
        - model: Model used for editing
        - output_image: Generated image file with path and metadata

    Examples:
        edit_images(
            ["body-lotion.png", "bath-bomb.png", "soap.png"],
            "Generate a photorealistic image of a gift basket on a white background with all items"
        )
        → Combines items into a gift basket image

        edit_images(
            ["logo.png", "background.png"],
            "Place the logo in the center of the background image",
            storage_path="output/"
        )
        → Composites logo onto background

        edit_images(
            ["photo1.jpg", "photo2.jpg"],
            "Merge these two photos side by side with a white border",
        )
        → Creates a merged image

    Security:
        - Requires valid OpenAI API key
        - All input images must exist and be readable
        - Only supports PNG and JPEG formats
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
                "operation": "edit_images",
                "error": "OpenAI API key not found. Please set OPENAI_API_KEY in .env file or environment variable.",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        # Initialize OpenAI client
        client = OpenAI(api_key=openai_api_key)

        # Validate and open all input images
        validated_paths = []
        image_files = []

        try:
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
                        "operation": "edit_images",
                        "error": f"Image file does not exist: {image_path}",
                    }
                    return ExecutionResult(
                        output_blocks=[TextContent(data=json.dumps(result, indent=2))],
                    )

                # Check file format
                if image_path.suffix.lower() not in [".png", ".jpg", ".jpeg"]:
                    result = {
                        "success": False,
                        "operation": "edit_images",
                        "error": f"Image must be PNG or JPEG format: {image_path}",
                    }
                    return ExecutionResult(
                        output_blocks=[TextContent(data=json.dumps(result, indent=2))],
                    )

                validated_paths.append(image_path)

                # Open image file in binary mode
                image_file = open(image_path, "rb")
                image_files.append(image_file)

            # Determine storage directory
            if storage_path:
                if Path(storage_path).is_absolute():
                    storage_dir = Path(storage_path).resolve()
                else:
                    storage_dir = (Path.cwd() / storage_path).resolve()
            else:
                storage_dir = Path.cwd()

            # Validate storage directory
            _validate_path_access(storage_dir, allowed_paths_list)
            storage_dir.mkdir(parents=True, exist_ok=True)

            try:
                # Call OpenAI image edit API
                response = client.images.edit(
                    model=model,
                    image=image_files,
                    prompt=prompt,
                )

                # Extract base64 image data from response
                if not response.data or len(response.data) == 0:
                    result = {
                        "success": False,
                        "operation": "edit_images",
                        "error": "No image data received from API",
                    }
                    return ExecutionResult(
                        output_blocks=[TextContent(data=json.dumps(result, indent=2))],
                    )

                image_base64 = response.data[0].b64_json
                image_bytes = base64.b64decode(image_base64)

                # Generate filename with timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                # Clean prompt for filename (first 30 chars)
                clean_prompt = "".join(c for c in prompt[:30] if c.isalnum() or c in (" ", "-", "_")).strip()
                clean_prompt = clean_prompt.replace(" ", "_")

                filename = f"edited_{timestamp}_{clean_prompt}.png"

                # Full file path
                file_path = storage_dir / filename

                # Write image to file
                with open(file_path, "wb") as f:
                    f.write(image_bytes)

                file_size = len(image_bytes)

                result = {
                    "success": True,
                    "operation": "edit_images",
                    "input_images": [str(p) for p in validated_paths],
                    "prompt": prompt,
                    "model": model,
                    "output_image": {
                        "file_path": str(file_path),
                        "filename": filename,
                        "size": file_size,
                    },
                }
                return ExecutionResult(
                    output_blocks=[TextContent(data=json.dumps(result, indent=2))],
                )

            except Exception as api_error:
                result = {
                    "success": False,
                    "operation": "edit_images",
                    "error": f"OpenAI API error: {str(api_error)}",
                }
                return ExecutionResult(
                    output_blocks=[TextContent(data=json.dumps(result, indent=2))],
                )

        finally:
            # Close all opened image files
            for img_file in image_files:
                try:
                    img_file.close()
                except Exception:
                    pass

    except Exception as e:
        result = {
            "success": False,
            "operation": "edit_images",
            "error": f"Failed to edit images: {str(e)}",
        }
        return ExecutionResult(
            output_blocks=[TextContent(data=json.dumps(result, indent=2))],
        )
