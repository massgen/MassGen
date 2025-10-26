# -*- coding: utf-8 -*-
"""
Create variations based on multiple input images using OpenAI's gpt-4.1 API.
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


async def image_to_image_generation(
    base_image_paths: List[str],
    prompt: str = "Create a variation of the provided images",
    model: str = "gpt-4.1",
    storage_path: Optional[str] = None,
    allowed_paths: Optional[List[str]] = None,
) -> ExecutionResult:
    """
    Create variations based on multiple input images using OpenAI's gpt-4.1 API.

    This tool generates image variations based on multiple base images using OpenAI's gpt-4.1 API
    and saves them to the workspace with automatic organization.

    Args:
        base_image_paths: List of paths to base images (PNG/JPEG files, less than 4MB)
                    - Relative path: Resolved relative to workspace
                    - Absolute path: Must be within allowed directories
        prompt: Text description for the variation (default: "Create a variation of the provided images")
        model: Model to use (default: "gpt-4.1")
        storage_path: Directory path where to save variations (optional)
                     - Relative path: Resolved relative to workspace
                     - Absolute path: Must be within allowed directories
                     - None/empty: Saves to workspace root
        allowed_paths: List of allowed base paths for validation (optional)

    Returns:
        ExecutionResult containing:
        - success: Whether operation succeeded
        - operation: "generate_and_store_image_with_input_images"
        - note: Note about usage
        - images: List of generated images with file paths and metadata
        - model: Model used for generation
        - prompt: The prompt used
        - total_images: Total number of images generated

    Examples:
        generate_and_store_image_with_input_images(["cat.png", "dog.png"], "Combine these animals")
        → Generates a variation combining both images

        generate_and_store_image_with_input_images(["art/logo.png", "art/icon.png"], "Create a unified design")
        → Generates variations based on both images

    Security:
        - Requires valid OpenAI API key
        - Input images must be valid image files less than 4MB
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
                "operation": "generate_and_store_image_with_input_images",
                "error": "OpenAI API key not found. Please set OPENAI_API_KEY in .env file or environment variable.",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        # Initialize OpenAI client
        client = OpenAI(api_key=openai_api_key)

        # Prepare content list with prompt and images
        content = [{"type": "input_text", "text": prompt}]

        # Process and validate all input images
        validated_paths = []
        for image_path_str in base_image_paths:
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
                    "operation": "generate_and_store_image_with_input_images",
                    "error": f"Image file does not exist: {image_path}",
                }
                return ExecutionResult(
                    output_blocks=[TextContent(data=json.dumps(result, indent=2))],
                )

            # Allow both PNG and JPEG formats
            if image_path.suffix.lower() not in [".png", ".jpg", ".jpeg"]:
                result = {
                    "success": False,
                    "operation": "generate_and_store_image_with_input_images",
                    "error": f"Image must be PNG or JPEG format: {image_path}",
                }
                return ExecutionResult(
                    output_blocks=[TextContent(data=json.dumps(result, indent=2))],
                )

            # Check file size (must be less than 4MB)
            file_size = image_path.stat().st_size
            if file_size > 4 * 1024 * 1024:
                result = {
                    "success": False,
                    "operation": "generate_and_store_image_with_input_images",
                    "error": f"Image file too large (must be < 4MB): {image_path} is {file_size / (1024*1024):.2f}MB",
                }
                return ExecutionResult(
                    output_blocks=[TextContent(data=json.dumps(result, indent=2))],
                )

            validated_paths.append(image_path)

            # Read and encode image to base64
            with open(image_path, "rb") as f:
                image_data = f.read()
            image_base64 = base64.b64encode(image_data).decode("utf-8")

            # Determine MIME type
            mime_type = "image/jpeg" if image_path.suffix.lower() in [".jpg", ".jpeg"] else "image/png"

            # Add image to content
            content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:{mime_type};base64,{image_base64}",
                },
            )

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
            # Generate variations using gpt-4.1 API with all images at once
            response = client.responses.create(
                model=model,
                input=[
                    {
                        "role": "user",
                        "content": content,
                    },
                ],
                tools=[{"type": "image_generation"}],
            )

            # Extract image generation calls from response
            image_generation_calls = [output for output in response.output if output.type == "image_generation_call"]

            all_variations = []
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # Process generated images
            for idx, output in enumerate(image_generation_calls):
                if hasattr(output, "result"):
                    image_base64 = output.result
                    image_bytes = base64.b64decode(image_base64)

                    # Generate filename
                    if len(image_generation_calls) > 1:
                        filename = f"variation_{idx+1}_{timestamp}.png"
                    else:
                        filename = f"variation_{timestamp}.png"

                    # Full file path
                    file_path = storage_dir / filename

                    # Save image
                    file_path.write_bytes(image_bytes)

                    all_variations.append(
                        {
                            "source_images": [str(p) for p in validated_paths],
                            "file_path": str(file_path),
                            "filename": filename,
                            "size": len(image_bytes),
                            "index": idx,
                        },
                    )

            # If no images were generated, check for text response
            if not all_variations:
                text_outputs = [output.content for output in response.output if hasattr(output, "content")]
                if text_outputs:
                    result = {
                        "success": False,
                        "operation": "generate_and_store_image_with_input_images",
                        "error": f"No images generated. Response: {' '.join(text_outputs)}",
                    }
                    return ExecutionResult(
                        output_blocks=[TextContent(data=json.dumps(result, indent=2))],
                    )

        except Exception as api_error:
            result = {
                "success": False,
                "operation": "generate_and_store_image_with_input_images",
                "error": f"OpenAI API error: {str(api_error)}",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        result = {
            "success": True,
            "operation": "generate_and_store_image_with_input_images",
            "note": "If no input images were provided, you must use generate_and_store_image_no_input_images tool.",
            "images": all_variations,
            "model": model,
            "prompt": prompt,
            "total_images": len(all_variations),
        }
        return ExecutionResult(
            output_blocks=[TextContent(data=json.dumps(result, indent=2))],
        )

    except Exception as e:
        result = {
            "success": False,
            "operation": "generate_and_store_image_with_input_images",
            "error": f"Failed to generate variations: {str(e)}",
        }
        return ExecutionResult(
            output_blocks=[TextContent(data=json.dumps(result, indent=2))],
        )
