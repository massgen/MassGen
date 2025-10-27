# -*- coding: utf-8 -*-
"""
Generate image using OpenAI's response with gpt-4.1 WITHOUT ANY INPUT IMAGES and store it in the workspace.
"""

import base64
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


async def text_to_image_generation(
    prompt: str,
    model: str = "gpt-4.1",
    storage_path: Optional[str] = None,
    allowed_paths: Optional[List[str]] = None,
    agent_cwd: Optional[str] = None,
) -> ExecutionResult:
    """
    Generate image using OpenAI's response with gpt-4.1 **WITHOUT ANY INPUT IMAGES** and store it in the workspace.

    This tool Generate image using OpenAI's response with gpt-4.1 **WITHOUT ANY INPUT IMAGES** and store it in the workspace.

    Args:
        prompt: Text description of the image to generate
        model: Model to use for generation (default: "gpt-4.1")
               Options: "gpt-4.1"
        storage_path: Directory path where to save the image (optional)
                     - Relative path: Resolved relative to agent's workspace (e.g., "images/generated")
                     - Absolute path: Must be within allowed directories
                     - None/empty: Saves to agent's workspace root
        allowed_paths: List of allowed base paths for validation (optional)
        agent_cwd: Agent's current working directory (automatically injected)

    Returns:
        ExecutionResult containing:
        - success: Whether operation succeeded
        - operation: "generate_and_store_image_no_input_images"
        - note: Note about operation
        - images: List of generated images with file paths and metadata
        - model: Model used for generation
        - prompt: The prompt used for generation
        - total_images: Total number of images generated and saved

    Examples:
        generate_and_store_image_no_input_images("a cat in space")
        → Generates and saves to: 20240115_143022_a_cat_in_space.png

        generate_and_store_image_no_input_images("sunset over mountains", storage_path="art/landscapes")
        → Generates and saves to: art/landscapes/20240115_143022_sunset_over_mountains.png

    Security:
        - Requires valid OpenAI API key (automatically detected from .env or environment)
        - Files are saved to specified path within workspace
        - Path must be within allowed directories

    Note:
        API key is automatically detected in this order:
        1. First checks .env file in current directory or parent directories
        2. Then checks environment variables
    """
    try:
        # Convert allowed_paths from strings to Path objects
        allowed_paths_list = [Path(p) for p in allowed_paths] if allowed_paths else None

        # Try to find and load .env file from multiple locations
        # 1. Try loading from script directory
        script_dir = Path(__file__).parent.parent.parent.parent  # Go up to project root
        env_path = script_dir / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        else:
            # 2. Try loading from current directory and parent directories
            load_dotenv()

        # Get API key from environment (load_dotenv will have loaded .env file)
        openai_api_key = os.getenv("OPENAI_API_KEY")

        if not openai_api_key:
            result = {
                "success": False,
                "operation": "generate_and_store_image",
                "error": "OpenAI API key not found. Please set OPENAI_API_KEY in .env file or environment variable.",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        # Initialize OpenAI client
        client = OpenAI(api_key=openai_api_key)

        # Determine storage directory
        # Use agent_cwd if available, otherwise fall back to Path.cwd()
        base_dir = Path(agent_cwd) if agent_cwd else Path.cwd()

        if storage_path:
            if Path(storage_path).is_absolute():
                storage_dir = Path(storage_path).resolve()
            else:
                storage_dir = (base_dir / storage_path).resolve()
        else:
            storage_dir = base_dir

        # Validate storage directory is within allowed paths
        _validate_path_access(storage_dir, allowed_paths_list)

        # Create directory if it doesn't exist
        storage_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Generate image using OpenAI API with gpt-4.1 non-streaming format
            response = client.responses.create(
                model=model,
                input=prompt,
                tools=[{"type": "image_generation"}],
            )

            # Extract image data from response
            image_data = [output.result for output in response.output if output.type == "image_generation_call"]

            saved_images = []

            if image_data:
                # Generate filename with timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                # Clean prompt for filename
                clean_prompt = "".join(c for c in prompt[:30] if c.isalnum() or c in (" ", "-", "_")).strip()
                clean_prompt = clean_prompt.replace(" ", "_")

                for idx, image_base64 in enumerate(image_data):
                    # Decode base64 image data
                    image_bytes = base64.b64decode(image_base64)

                    # Add index if generating multiple images
                    if len(image_data) > 1:
                        filename = f"{timestamp}_{clean_prompt}_{idx+1}.png"
                    else:
                        filename = f"{timestamp}_{clean_prompt}.png"

                    # Full file path
                    file_path = storage_dir / filename

                    # Write image to file
                    file_path.write_bytes(image_bytes)
                    file_size = len(image_bytes)

                    saved_images.append(
                        {
                            "file_path": str(file_path),
                            "filename": filename,
                            "size": file_size,
                            "index": idx,
                        },
                    )

            result = {
                "success": True,
                "operation": "generate_and_store_image_no_input_images",
                "note": "New images are generated and saved to the specified path.",
                "images": saved_images,
                "model": model,
                "prompt": prompt,
                "total_images": len(saved_images),
            }

            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        except Exception as api_error:
            result = {
                "success": False,
                "operation": "generate_and_store_image_no_input_images",
                "error": f"OpenAI API error: {str(api_error)}",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

    except Exception as e:
        result = {
            "success": False,
            "operation": "generate_and_store_image_no_input_images",
            "error": f"Failed to generate or save image: {str(e)}",
        }
        return ExecutionResult(
            output_blocks=[TextContent(data=json.dumps(result, indent=2))],
        )
