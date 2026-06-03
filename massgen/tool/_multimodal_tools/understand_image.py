"""
Understand and analyze images using the agent's native backend.

Supports single image or multiple images in one API call for comparison/analysis.
Routes to the agent's own backend (Claude, Gemini, Grok, Claude Code, Codex, OpenAI)
when possible, falling back to OpenAI for backwards compatibility.
"""

import base64
import json
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from massgen.backend.capabilities import has_capability, normalize_backend_type
from massgen.logger_config import logger
from massgen.tool._multimodal_tools.image_backends import (
    call_claude,
    call_claude_code,
    call_codex,
    call_gemini,
    call_grok,
    call_openai,
)
from massgen.tool._result import ExecutionResult, TextContent


def _validate_path_access(path: Path, allowed_paths: list[Path] | None = None) -> None:
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


@dataclass
class LoadedImage:
    """Represents a loaded and processed image ready for API submission."""

    path: Path
    base64_data: str
    mime_type: str
    name: str | None = None  # Optional name for referencing in prompts


def _load_and_process_image(
    image_path: str,
    base_dir: Path,
    allowed_paths_list: list[Path] | None = None,
    name: str | None = None,
) -> LoadedImage:
    """
    Load and process a single image, resizing if necessary.

    Args:
        image_path: Path to the image file
        base_dir: Base directory for resolving relative paths
        allowed_paths_list: List of allowed base paths for validation
        name: Optional name for referencing in prompts

    Returns:
        LoadedImage with base64 data ready for API submission

    Raises:
        ValueError: If image path is invalid or file doesn't exist
        Exception: If image processing fails
    """
    # Resolve image path
    if Path(image_path).is_absolute():
        img_path = Path(image_path).resolve()
    else:
        img_path = (base_dir / image_path).resolve()

    # Validate image path
    _validate_path_access(img_path, allowed_paths_list)

    if not img_path.exists():
        raise ValueError(f"Image file does not exist: {img_path}")

    # Check file format
    if img_path.suffix.lower() not in [".png", ".jpg", ".jpeg", ".webp"]:
        raise ValueError(f"Image must be PNG, JPEG, JPG, or WebP format: {img_path}")

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
        if file_size > max_size:
            raise ValueError(
                f"Image too large ({file_size/1024/1024:.1f}MB > {max_size/1024/1024:.0f}MB) " "and PIL not available for resizing. Install with: pip install pillow",
            )
        # Read without resizing
        with open(img_path, "rb") as image_file:
            image_data = image_file.read()
        base64_image = base64.b64encode(image_data).decode("utf-8")

        # Map file extension to MIME type
        suffix = img_path.suffix.lower()
        if suffix in [".jpg", ".jpeg"]:
            mime_type = "image/jpeg"
        elif suffix == ".png":
            mime_type = "image/png"
        elif suffix == ".webp":
            mime_type = "image/webp"
        else:
            mime_type = "image/jpeg"  # Fallback

        logger.info(f"Read image without dimension check (PIL not available): {img_path.name}")
        return LoadedImage(path=img_path, base64_data=base64_image, mime_type=mime_type, name=name)

    # PIL available - check both file size and dimensions
    img = Image.open(img_path)
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
            size_scale = (max_size / file_size) ** 0.5 * 0.8  # 0.8 for safety margin
            scale_factors.append(size_scale)

        # Scale for dimensions (if needed)
        if short_side > max_short_side or long_side > max_long_side:
            short_scale = max_short_side / short_side if short_side > max_short_side else 1.0
            long_scale = max_long_side / long_side if long_side > max_long_side else 1.0
            dimension_scale = min(short_scale, long_scale) * 0.95
            scale_factors.append(dimension_scale)

        # Use the most restrictive scale factor
        scale_factor = min(scale_factors)
        new_width = int(original_width * scale_factor)
        new_height = int(original_height * scale_factor)

        # Resize image
        img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Convert to bytes
        img_byte_arr = io.BytesIO()
        img_resized.convert("RGB").save(img_byte_arr, format="JPEG", quality=85, optimize=True)
        image_data = img_byte_arr.getvalue()

        base64_image = base64.b64encode(image_data).decode("utf-8")
        mime_type = "image/jpeg"

        logger.info(
            f"Resized image ({', '.join(resize_reason)}): " f"{original_width}x{original_height} ({file_size/1024/1024:.1f}MB) -> " f"{new_width}x{new_height} ({len(image_data)/1024/1024:.1f}MB)",
        )
    else:
        # No resize needed - read normally
        with open(img_path, "rb") as image_file:
            image_data = image_file.read()
        base64_image = base64.b64encode(image_data).decode("utf-8")

        # Map file extension to MIME type
        suffix = img_path.suffix.lower()
        if suffix in [".jpg", ".jpeg"]:
            mime_type = "image/jpeg"
        elif suffix == ".png":
            mime_type = "image/png"
        elif suffix == ".webp":
            mime_type = "image/webp"
        else:
            mime_type = "image/jpeg"  # Fallback

        logger.info(f"Image within limits: {original_width}x{original_height} ({file_size/1024/1024:.1f}MB)")

    return LoadedImage(path=img_path, base64_data=base64_image, mime_type=mime_type, name=name)


async def understand_image(
    image_path: str | None = None,
    prompt: str = "What's in this image? Please describe it in detail.",
    model: str = "gpt-5.4",
    allowed_paths: list[str] | None = None,
    agent_cwd: str | None = None,
    task_context: str | None = None,
    images: dict[str, str] | None = None,
    backend_type: str | None = None,
    system_prompt: str | None = None,
    previous_response_id: str | None = None,
    conversation_messages: list[dict] | None = None,
    reasoning_effort: str | None = None,
) -> ExecutionResult:
    """
    Understand and analyze one or more images using OpenAI's gpt-5.4 API.

    This tool processes images through OpenAI's gpt-5.4 API to extract insights,
    descriptions, or answer questions about image content. Supports multiple images
    in a single call for comparison or joint analysis.

    Args:
        image_path: Path to a single image file (PNG/JPEG/JPG/WebP).
                   Use this for simple single-image analysis.
        prompt: Question or instruction about the image(s).
                When using `images` dict, reference images by their keys.
        model: Model to use (default: "gpt-5.4")
        allowed_paths: List of allowed base paths for validation (optional)
        agent_cwd: Agent's current working directory (automatically injected)
        task_context: Task context for prompt augmentation (automatically injected)
        images: Dict mapping names to image paths for multi-image analysis.
                Use instead of image_path when analyzing multiple images together.
                Reference images by their dict keys in your prompt.

    Returns:
        ExecutionResult containing:
        - success: Whether operation succeeded
        - operation: "understand_image"
        - image_path or images: Path(s) to the analyzed image(s)
        - prompt: The prompt used
        - model: Model used for analysis
        - response: The model's understanding/description

    Examples:
        # Single image analysis
        understand_image(image_path="photo.jpg")
        → Returns detailed description of the image

        # Multiple images for comparison (dict keys become reference names)
        understand_image(
            images={"before": "before.png", "after": "after.png"},
            prompt="Compare the before and after screenshots. What changed?"
        )
        → Returns comparison analysis referencing both images by name

    Security:
        - Requires valid OpenAI API key
        - Image files must exist and be readable
        - Supports PNG, JPEG, JPG, and WebP formats
    """

    def _error(msg: str) -> ExecutionResult:
        return ExecutionResult(
            output_blocks=[TextContent(data=json.dumps({"success": False, "operation": "understand_image", "error": msg}, indent=2))],
        )

    try:
        # Validate image inputs. Fresh calls need image_path or images.
        # Follow-ups may omit new images if conversation threading context exists.
        has_threading_context = bool(previous_response_id or conversation_messages)
        if image_path and images:
            return _error("Provide either 'image_path' or 'images', not both")
        if not image_path and not images and not has_threading_context:
            return _error("Must provide either 'image_path' or 'images'")

        # Convert allowed_paths from strings to Path objects
        allowed_paths_list = [Path(p) for p in allowed_paths] if allowed_paths else None

        # Load environment variables
        script_dir = Path(__file__).parent.parent.parent.parent
        env_path = script_dir / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        else:
            load_dotenv()

        # Use agent_cwd if available, otherwise fall back to Path.cwd()
        base_dir = Path(agent_cwd) if agent_cwd else Path.cwd()

        # Load images using the helper function
        loaded_images: list[LoadedImage] = []
        normalized_backend_type = normalize_backend_type(backend_type)

        if image_path:
            # Single image mode
            try:
                loaded = _load_and_process_image(image_path, base_dir, allowed_paths_list, name=None)
                loaded_images.append(loaded)
            except Exception as e:
                return _error(str(e))
        elif images:
            # Multi-image mode with names from dict keys
            for name, path in images.items():
                try:
                    loaded = _load_and_process_image(path, base_dir, allowed_paths_list, name=name)
                    loaded_images.append(loaded)
                except Exception as e:
                    return _error(f"Error loading '{name}': {str(e)}")
        else:
            # Follow-up mode: rely on conversation threading, no new image payload.
            logger.info("[understand_image] Follow-up without new image input")

        try:
            # Inject task context into prompt if available
            from massgen.context.task_context import format_prompt_with_context

            augmented_prompt = format_prompt_with_context(prompt, task_context)

            # Build prompt with image name references for multi-image mode
            if images and len(loaded_images) > 1:
                name_context = "Images provided:\n"
                for img in loaded_images:
                    name_context += f"- {img.name}: {img.path.name}\n"
                augmented_prompt = f"{name_context}\n{augmented_prompt}"

            # Route to the agent's native backend if it supports image understanding
            response_id: str | None = None
            if normalized_backend_type and has_capability(normalized_backend_type, "image_understanding"):
                try:
                    logger.info(f"[understand_image] Using native backend: {normalized_backend_type}")
                    if normalized_backend_type == "claude":
                        response_text, response_id = await call_claude(
                            loaded_images,
                            augmented_prompt,
                            model,
                            system_prompt=system_prompt,
                            conversation_messages=conversation_messages,
                        )
                    elif normalized_backend_type == "gemini":
                        response_text, response_id = await call_gemini(
                            loaded_images,
                            augmented_prompt,
                            model,
                            system_prompt=system_prompt,
                            conversation_messages=conversation_messages,
                        )
                    elif normalized_backend_type == "grok":
                        response_text, response_id = await call_grok(
                            loaded_images,
                            augmented_prompt,
                            model,
                            system_prompt=system_prompt,
                            conversation_messages=conversation_messages,
                        )
                    elif normalized_backend_type == "claude_code":
                        response_text, response_id = await call_claude_code(
                            loaded_images,
                            augmented_prompt,
                            model,
                            agent_cwd,
                            system_prompt=system_prompt,
                        )
                    elif normalized_backend_type == "codex":
                        response_text, response_id = await call_codex(
                            loaded_images,
                            augmented_prompt,
                            model=model,
                            agent_cwd=agent_cwd,
                            system_prompt=system_prompt,
                        )
                    else:
                        # openai, response, chatcompletion, azure_openai, openrouter, uitars
                        response_text, response_id = await call_openai(
                            loaded_images,
                            augmented_prompt,
                            model,
                            system_prompt=system_prompt,
                            previous_response_id=previous_response_id,
                            reasoning_effort=reasoning_effort,
                        )
                except Exception as native_err:
                    logger.warning(
                        f"[understand_image] Native backend {normalized_backend_type} failed: {native_err}. " "Falling back to OpenAI gpt-5.4",
                    )
                    response_text, response_id = await call_openai(
                        loaded_images,
                        augmented_prompt,
                        "gpt-5.4",
                        system_prompt=system_prompt,
                        previous_response_id=previous_response_id,
                        reasoning_effort=reasoning_effort,
                    )
            else:
                # Fallback: OpenAI default (backward compat)
                logger.info(
                    f"[understand_image] Fallback to OpenAI (backend_type={normalized_backend_type or backend_type})",
                )
                response_text, response_id = await call_openai(
                    loaded_images,
                    augmented_prompt,
                    "gpt-5.4",
                    system_prompt=system_prompt,
                    previous_response_id=previous_response_id,
                    reasoning_effort=reasoning_effort,
                )

            # Build result based on single vs multiple images
            if image_path:
                # Single image - backwards compatible format
                result = {
                    "success": True,
                    "operation": "understand_image",
                    "image_path": str(loaded_images[0].path),
                    "prompt": prompt,
                    "model": model,
                    "response": response_text,
                }
            else:
                # Multi-image - include the images dict with resolved paths
                result = {
                    "success": True,
                    "operation": "understand_image",
                    "images": {img.name: str(img.path) for img in loaded_images},
                    "prompt": prompt,
                    "model": model,
                    "response": response_text,
                }

            if response_id:
                result["response_id"] = response_id

            return ExecutionResult(output_blocks=[TextContent(data=json.dumps(result, indent=2))])

        except Exception as api_error:
            return _error(f"API error ({normalized_backend_type or backend_type or 'openai'}): {str(api_error)}")

    except Exception as e:
        return _error(f"Failed to understand image: {str(e)}")
