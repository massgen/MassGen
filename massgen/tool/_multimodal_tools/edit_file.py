# -*- coding: utf-8 -*-
"""
Edit file content using OpenAI's Chat Completion API.
"""

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


async def edit_file(
    file_path: str,
    edit_instruction: str,
    model: str = "gpt-4o",
    output_path: Optional[str] = None,
    create_backup: bool = True,
    allowed_paths: Optional[List[str]] = None,
) -> ExecutionResult:
    """
    Edit file content using OpenAI's Chat Completion API.

    This tool reads a file, applies editing instructions using OpenAI's language models,
    and saves the edited content. It can edit code files, text files, configuration files,
    and other text-based content.

    Args:
        file_path: Path to the file to edit
                  - Relative path: Resolved relative to workspace
                  - Absolute path: Must be within allowed directories
        edit_instruction: Text description of what changes to make to the file
        model: OpenAI model to use (default: "gpt-4o")
               Options: "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"
        output_path: Path where to save the edited file (optional)
                    - If None: overwrites the original file (creates backup if create_backup=True)
                    - Relative path: Resolved relative to workspace
                    - Absolute path: Must be within allowed directories
        create_backup: Whether to create a backup of the original file (default: True)
                      Backup is saved as {filename}.backup.{timestamp}{ext}
        allowed_paths: List of allowed base paths for validation (optional)

    Returns:
        ExecutionResult containing:
        - success: Whether operation succeeded
        - operation: "edit_file"
        - original_file: Path to original file
        - edited_file: Path to edited file
        - backup_file: Path to backup file (if created)
        - edit_instruction: The instruction used
        - model: Model used for editing
        - changes_made: Whether any changes were detected

    Examples:
        edit_file(
            file_path="config.json",
            edit_instruction="Add a new field 'timeout' with value 30"
        )
        → Edits config.json in place with backup

        edit_file(
            file_path="script.py",
            edit_instruction="Add error handling to all functions",
            output_path="script_v2.py",
            create_backup=False
        )
        → Creates a new file with edits, no backup

        edit_file(
            file_path="README.md",
            edit_instruction="Fix all spelling mistakes and improve grammar",
            model="gpt-4o-mini"
        )
        → Edits README with a smaller model

        edit_file(
            file_path="app.py",
            edit_instruction="Refactor the authentication function to use async/await"
        )
        → Refactors code with AI assistance

    Security:
        - Requires valid OpenAI API key
        - File must exist and be readable
        - Supports text-based files only
        - Creates backups by default to prevent data loss
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
                "operation": "edit_file",
                "error": "OpenAI API key not found. Please set OPENAI_API_KEY in .env file or environment variable.",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        # Initialize OpenAI client
        client = OpenAI(api_key=openai_api_key)

        # Resolve file path
        if Path(file_path).is_absolute():
            source_path = Path(file_path).resolve()
        else:
            source_path = (Path.cwd() / file_path).resolve()

        # Validate source file path
        _validate_path_access(source_path, allowed_paths_list)

        if not source_path.exists():
            result = {
                "success": False,
                "operation": "edit_file",
                "error": f"File does not exist: {source_path}",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        if not source_path.is_file():
            result = {
                "success": False,
                "operation": "edit_file",
                "error": f"Path is not a file: {source_path}",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        # Read original file content
        try:
            with open(source_path, "r", encoding="utf-8") as f:
                original_content = f.read()
        except UnicodeDecodeError:
            result = {
                "success": False,
                "operation": "edit_file",
                "error": f"File is not a text file or uses unsupported encoding: {source_path}",
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        # Determine output path
        if output_path:
            if Path(output_path).is_absolute():
                target_path = Path(output_path).resolve()
            else:
                target_path = (Path.cwd() / output_path).resolve()
        else:
            target_path = source_path

        # Validate target path
        _validate_path_access(target_path, allowed_paths_list)

        # Create backup if needed
        backup_path = None
        if create_backup and target_path == source_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"{source_path.stem}.backup.{timestamp}{source_path.suffix}"
            backup_path = source_path.parent / backup_filename

            with open(backup_path, "w", encoding="utf-8") as f:
                f.write(original_content)

        try:
            # Call OpenAI API to edit the file
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a helpful assistant that edits file content according to user instructions. "
                            "Return ONLY the edited file content without any explanation, markdown code blocks, or additional text. "
                            "Preserve the file's original structure and format unless specifically instructed to change it."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Here is the file content:\n\n{original_content}\n\n"
                        f"Edit instruction: {edit_instruction}\n\n"
                        f"Return the complete edited file content:",
                    },
                ],
                temperature=0.3,
            )

            edited_content = response.choices[0].message.content.strip()

            # Remove markdown code blocks if present
            if edited_content.startswith("```") and edited_content.endswith("```"):
                lines = edited_content.split("\n")
                # Remove first line (```language) and last line (```)
                edited_content = "\n".join(lines[1:-1])

            # Check if content changed
            changes_made = original_content != edited_content

            # Write edited content to target file
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(edited_content)

            result = {
                "success": True,
                "operation": "edit_file",
                "original_file": str(source_path),
                "edited_file": str(target_path),
                "edit_instruction": edit_instruction,
                "model": model,
                "changes_made": changes_made,
                "original_size": len(original_content),
                "edited_size": len(edited_content),
            }

            if backup_path:
                result["backup_file"] = str(backup_path)

            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

        except Exception as api_error:
            result = {
                "success": False,
                "operation": "edit_file",
                "error": f"OpenAI API error: {str(api_error)}",
                "file_path": str(source_path),
            }
            return ExecutionResult(
                output_blocks=[TextContent(data=json.dumps(result, indent=2))],
            )

    except Exception as e:
        result = {
            "success": False,
            "operation": "edit_file",
            "error": f"Failed to edit file: {str(e)}",
        }
        return ExecutionResult(
            output_blocks=[TextContent(data=json.dumps(result, indent=2))],
        )
