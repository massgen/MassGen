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

from massgen.logger_config import logger
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

        # Read image and check size and dimensions
        try:
            # OpenAI Vision API limits:
            # - Up to 20MB per image
            # - High-resolution: 768px (short side) x 2000px (long side)
            file_size = img_path.stat().st_size
            max_size = 18 * 1024 * 1024  # 18MB (conservative buffer under OpenAI's 20MB limit)
            max_short_side = 768  # Maximum pixels for short side
            max_long_side = 2000  # Maximum pixels for long side

            # Try to import PIL for dimension/size checking
            try:
                import io

                from PIL import Image
            except ImportError:
                # PIL not available - fall back to simple file reading
                # This will work for small images but may fail for large ones
                if file_size > max_size:
                    result = {
                        "success": False,
                        "operation": "understand_image",
                        "error": f"Image too large ({file_size/1024/1024:.1f}MB > {max_size/1024/1024:.0f}MB) and PIL not available for resizing. Install with: pip install pillow",
                    }
                    return ExecutionResult(
                        output_blocks=[TextContent(data=json.dumps(result, indent=2))],
                    )
                # Read without resizing
                with open(img_path, "rb") as image_file:
                    image_data = image_file.read()
                base64_image = base64.b64encode(image_data).decode("utf-8")
                mime_type = "image/jpeg" if img_path.suffix.lower() in [".jpg", ".jpeg"] else "image/png"
                logger.info(f"Read image without dimension check (PIL not available): {img_path.name} ({file_size/1024/1024:.1f}MB)")

            else:
                # PIL available - check both file size and dimensions
                img = Image.open(img_path)
                img.size
                original_width, original_height = img.size

                # Determine short and long sides
                short_side = min(original_width, original_height)
                long_side = max(original_width, original_height)

                # Check if we need to resize
                needs_resize = False
                resize_reason = []

                if file_size > max_size:
                    needs_resize = True
                    resize_reason.append(f"file size {file_size/1024/1024:.1f}MB > {max_size/1024/1024:.0f}MB")

                if short_side > max_short_side or long_side > max_long_side:
                    needs_resize = True
                    resize_reason.append(f"dimensions {original_width}x{original_height} exceed {max_short_side}x{max_long_side}")

                if needs_resize:
                    # Calculate scale factor based on both size and dimensions
                    scale_factors = []

                    # Scale for file size (if needed)
                    if file_size > max_size:
                        # Estimate: reduce dimensions by sqrt of size ratio
                        size_scale = (max_size / file_size) ** 0.5 * 0.8  # 0.8 for safety margin
                        scale_factors.append(size_scale)

                    # Scale for dimensions (if needed)
                    if short_side > max_short_side or long_side > max_long_side:
                        # Calculate scale needed to fit within dimension constraints
                        short_scale = max_short_side / short_side if short_side > max_short_side else 1.0
                        long_scale = max_long_side / long_side if long_side > max_long_side else 1.0
                        dimension_scale = min(short_scale, long_scale) * 0.95  # 0.95 for safety margin
                        scale_factors.append(dimension_scale)

                    # Use the most restrictive scale factor
                    scale_factor = min(scale_factors)
                    new_width = int(original_width * scale_factor)
                    new_height = int(original_height * scale_factor)

                    # Resize image
                    img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

                    # Convert to bytes
                    img_byte_arr = io.BytesIO()
                    # Save as JPEG for better compression
                    img_resized.convert("RGB").save(img_byte_arr, format="JPEG", quality=85, optimize=True)
                    image_data = img_byte_arr.getvalue()

                    base64_image = base64.b64encode(image_data).decode("utf-8")
                    mime_type = "image/jpeg"

                    logger.info(
                        f"Resized image ({', '.join(resize_reason)}): "
                        f"{original_width}x{original_height} ({file_size/1024/1024:.1f}MB) -> "
                        f"{new_width}x{new_height} ({len(image_data)/1024/1024:.1f}MB)",
                    )

                else:
                    # No resize needed - read normally
                    with open(img_path, "rb") as image_file:
                        image_data = image_file.read()
                    base64_image = base64.b64encode(image_data).decode("utf-8")
                    # Determine MIME type
                    mime_type = "image/jpeg" if img_path.suffix.lower() in [".jpg", ".jpeg"] else "image/png"
                    logger.info(f"Image within limits: {original_width}x{original_height} ({file_size/1024/1024:.1f}MB)")

        except Exception as read_error:
            result = {
                "success": False,
                "operation": "understand_image",
                "error": f"Failed to read image file: {str(read_error)}",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

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
                    },
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
