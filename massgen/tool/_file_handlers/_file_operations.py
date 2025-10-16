# -*- coding: utf-8 -*-
"""File operation tools for reading and writing."""

import os
from typing import List, Optional

from .._result import ExecutionResult, TextContent


async def read_file_content(
    target_path: str,
    line_range: Optional[List[int]] = None,
) -> ExecutionResult:
    """Read file contents with optional line range specification.

    Args:
        target_path: Path to the file to read
        line_range: Optional [start, end] line numbers (1-based, inclusive).
                   Use negative numbers for lines from end (e.g., [-100, -1])

    Returns:
        ExecutionResult with file content or error message
    """
    if not os.path.exists(target_path):
        return ExecutionResult(
            output_blocks=[
                TextContent(
                    data=f"Error: File '{target_path}' does not exist.",
                ),
            ],
        )

    if not os.path.isfile(target_path):
        return ExecutionResult(
            output_blocks=[
                TextContent(
                    data=f"Error: Path '{target_path}' is not a file.",
                ),
            ],
        )

    try:
        with open(target_path, "r", encoding="utf-8") as file:
            all_lines = file.readlines()

        if line_range:
            start_line, end_line = line_range

            # Handle negative indices
            if start_line < 0:
                start_line = len(all_lines) + start_line + 1
            if end_line < 0:
                end_line = len(all_lines) + end_line + 1

            # Validate range
            if start_line < 1 or end_line > len(all_lines) or start_line > end_line:
                return ExecutionResult(
                    output_blocks=[
                        TextContent(
                            data=f"Error: Invalid line range {line_range} for file with {len(all_lines)} lines.",
                        ),
                    ],
                )

            # Extract lines (convert to 0-based indexing)
            selected_lines = all_lines[start_line - 1 : end_line]
            content_with_numbers = "".join(f"{i + start_line:4d}│ {line}" for i, line in enumerate(selected_lines))

            return ExecutionResult(
                output_blocks=[
                    TextContent(
                        data=f"Content of {target_path} (lines {start_line}-{end_line}):\n```\n{content_with_numbers}```",
                    ),
                ],
            )
        else:
            full_content = "".join(all_lines)
            return ExecutionResult(
                output_blocks=[
                    TextContent(
                        data=f"Content of {target_path}:\n```\n{full_content}```",
                    ),
                ],
            )

    except Exception as error:
        return ExecutionResult(
            output_blocks=[
                TextContent(
                    data=f"Error reading file: {error}",
                ),
            ],
        )


async def save_file_content(
    target_path: str,
    file_content: str,
    create_dirs: bool = True,
) -> ExecutionResult:
    """Write content to a file, creating directories if needed.

    Args:
        target_path: Path where file will be saved
        file_content: Content to write to the file
        create_dirs: Whether to create parent directories if they don't exist

    Returns:
        ExecutionResult indicating success or failure
    """
    try:
        # Create parent directories if requested
        if create_dirs:
            parent_dir = os.path.dirname(target_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)

        with open(target_path, "w", encoding="utf-8") as file:
            file.write(file_content)

        return ExecutionResult(
            output_blocks=[
                TextContent(
                    data=f"Successfully wrote {len(file_content)} characters to {target_path}",
                ),
            ],
        )

    except Exception as error:
        return ExecutionResult(
            output_blocks=[
                TextContent(
                    data=f"Error writing file: {error}",
                ),
            ],
        )


async def append_file_content(
    target_path: str,
    additional_content: str,
    line_position: Optional[int] = None,
) -> ExecutionResult:
    """Append content to a file or insert at specific line.

    Args:
        target_path: Path to the file
        additional_content: Content to append or insert
        line_position: Optional line number to insert at (1-based).
                      If None, appends to end of file.

    Returns:
        ExecutionResult indicating success or failure
    """
    if not os.path.exists(target_path):
        return ExecutionResult(
            output_blocks=[
                TextContent(
                    data=f"Error: File '{target_path}' does not exist.",
                ),
            ],
        )

    try:
        with open(target_path, "r", encoding="utf-8") as file:
            current_lines = file.readlines()

        if line_position is None:
            # Append to end
            with open(target_path, "a", encoding="utf-8") as file:
                file.write(additional_content)

            return ExecutionResult(
                output_blocks=[
                    TextContent(
                        data=f"Successfully appended {len(additional_content)} characters to {target_path}",
                    ),
                ],
            )
        else:
            # Insert at specific line
            if line_position < 1 or line_position > len(current_lines) + 1:
                return ExecutionResult(
                    output_blocks=[
                        TextContent(
                            data=f"Error: Invalid line position {line_position} for file with {len(current_lines)} lines.",
                        ),
                    ],
                )

            # Insert content (convert to 0-based index)
            insert_idx = line_position - 1

            # Ensure content ends with newline for proper insertion
            if not additional_content.endswith("\n"):
                additional_content += "\n"

            current_lines.insert(insert_idx, additional_content)

            with open(target_path, "w", encoding="utf-8") as file:
                file.writelines(current_lines)

            return ExecutionResult(
                output_blocks=[
                    TextContent(
                        data=f"Successfully inserted content at line {line_position} in {target_path}",
                    ),
                ],
            )

    except Exception as error:
        return ExecutionResult(
            output_blocks=[
                TextContent(
                    data=f"Error modifying file: {error}",
                ),
            ],
        )
