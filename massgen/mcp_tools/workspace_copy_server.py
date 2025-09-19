#!/usr/bin/env python3
"""
Workspace Copy MCP Server for MassGen - Phase 1 Implementation

This MCP server provides tools for copying files from temporary workspaces and context paths
to the agent's own workspace. It implements copy-on-write behavior for multi-agent collaboration.

Tools provided:
- copy_file: Copy a single file or directory from any accessible path to workspace
- copy_files_batch: Copy multiple files with pattern matching and exclusions
"""

import os
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import fnmatch
import fastmcp


app = fastmcp.FastMCP("Workspace Copy")


def get_copy_file_pairs(
    source_base_path: str,
    destination_base_path: str = "",
    include_patterns: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None
) -> List[Tuple[Path, Path]]:
    """
    Get all source->destination file pairs that would be copied by copy_files_batch.

    This function can be imported by the filesystem manager for permission validation.

    Args:
        source_base_path: Base path to copy from
        destination_base_path: Base path in workspace to copy to
        include_patterns: List of glob patterns for files to include
        exclude_patterns: List of glob patterns for files to exclude

    Returns:
        List of (source_path, destination_path) tuples

    Raises:
        ValueError: If paths are invalid
    """
    if include_patterns is None:
        include_patterns = ["*"]
    if exclude_patterns is None:
        exclude_patterns = []

    # Get allowed paths for validation
    allowed_sources, allowed_destinations = _get_allowed_paths()

    # Validate source base path
    source_base = Path(source_base_path).resolve()
    if not source_base.exists():
        raise ValueError(f"Source base path does not exist: {source_base}")

    _validate_path_access(source_base, allowed_sources, "source")

    # Validate destination base path
    current_workspace = os.getenv("CURRENT_WORKSPACE")
    if not current_workspace:
        raise ValueError("CURRENT_WORKSPACE environment variable not set")

    workspace = Path(current_workspace).resolve()

    if destination_base_path:
        dest_base = (workspace / destination_base_path).resolve()
    else:
        dest_base = workspace

    _validate_path_access(dest_base, allowed_destinations, "destination")

    # Collect all file pairs
    file_pairs = []

    for item in source_base.rglob("*"):
        if not item.is_file():
            continue

        # Get relative path from source base
        rel_path = item.relative_to(source_base)
        rel_path_str = str(rel_path)

        # Check include patterns
        included = any(fnmatch.fnmatch(rel_path_str, pattern) for pattern in include_patterns)
        if not included:
            continue

        # Check exclude patterns
        excluded = any(fnmatch.fnmatch(rel_path_str, pattern) for pattern in exclude_patterns)
        if excluded:
            continue

        # Calculate destination
        dest_file = (dest_base / rel_path).resolve()

        # Validate destination is within allowed paths
        _validate_path_access(dest_file, allowed_destinations, "destination")

        file_pairs.append((item, dest_file))

    return file_pairs


def _get_allowed_paths() -> tuple[List[Path], List[Path]]:
    """
    Get allowed source and destination paths from environment.

    Returns:
        Tuple of (allowed_source_paths, allowed_destination_paths)
    """
    # Get paths from environment (set by filesystem manager)
    temp_workspace_base = os.getenv("TEMP_WORKSPACE_BASE", "")
    context_paths_str = os.getenv("CONTEXT_PATHS", "")
    current_workspace = os.getenv("CURRENT_WORKSPACE", "")

    allowed_sources = []
    allowed_destinations = []

    # Add temp workspace base for sources
    if temp_workspace_base:
        try:
            allowed_sources.append(Path(temp_workspace_base).resolve())
        except Exception:
            pass

    # Add context paths for sources
    if context_paths_str:
        for path_str in context_paths_str.split(","):
            if path_str.strip():
                try:
                    allowed_sources.append(Path(path_str.strip()).resolve())
                except Exception:
                    pass

    # Add current workspace for destinations
    if current_workspace:
        try:
            allowed_destinations.append(Path(current_workspace).resolve())
        except Exception:
            pass

    return allowed_sources, allowed_destinations


def _validate_path_access(path: Path, allowed_paths: List[Path], path_type: str) -> None:
    """
    Validate that a path is within allowed directories.

    Args:
        path: Path to validate
        allowed_paths: List of allowed base paths
        path_type: Type for error messages ("source" or "destination")

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

    raise ValueError(f"{path_type.capitalize()} path not in allowed directories: {path}")


def _validate_and_resolve_paths(source_path: str, destination_path: str) -> tuple[Path, Path]:
    """
    Validate source and destination paths for copy operations.

    Args:
        source_path: Source file/directory path
        destination_path: Destination path in workspace

    Returns:
        Tuple of (resolved_source, resolved_destination)

    Raises:
        ValueError: If paths are invalid
    """
    try:
        # Get allowed paths
        allowed_sources, allowed_destinations = _get_allowed_paths()

        # Validate and resolve source
        source = Path(source_path).resolve()
        if not source.exists():
            raise ValueError(f"Source path does not exist: {source}")

        _validate_path_access(source, allowed_sources, "source")

        # Validate and resolve destination
        current_workspace = os.getenv("CURRENT_WORKSPACE")
        if not current_workspace:
            raise ValueError("CURRENT_WORKSPACE environment variable not set")

        workspace = Path(current_workspace).resolve()

        if Path(destination_path).is_absolute():
            destination = Path(destination_path).resolve()
        else:
            destination = (workspace / destination_path).resolve()

        _validate_path_access(destination, allowed_destinations, "destination")

        return source, destination

    except Exception as e:
        raise ValueError(f"Path validation failed: {e}")


def _perform_copy(source: Path, destination: Path, overwrite: bool = False) -> Dict[str, Any]:
    """
    Perform the actual copy operation.

    Args:
        source: Source path
        destination: Destination path
        overwrite: Whether to overwrite existing files

    Returns:
        Dict with operation results
    """
    try:
        # Check if destination exists
        if destination.exists() and not overwrite:
            raise ValueError(f"Destination already exists (use overwrite=true): {destination}")

        # Create parent directories
        destination.parent.mkdir(parents=True, exist_ok=True)

        if source.is_file():
            shutil.copy2(source, destination)
            return {
                "type": "file",
                "source": str(source),
                "destination": str(destination),
                "size": destination.stat().st_size
            }
        elif source.is_dir():
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(source, destination)

            file_count = len([f for f in destination.rglob("*") if f.is_file()])
            return {
                "type": "directory",
                "source": str(source),
                "destination": str(destination),
                "file_count": file_count
            }
        else:
            raise ValueError(f"Source is neither file nor directory: {source}")

    except Exception as e:
        raise ValueError(f"Copy operation failed: {e}")


@app.tool()
def copy_file(
    source_path: str,
    destination_path: str,
    overwrite: bool = False
) -> Dict[str, Any]:
    """
    Copy a file or directory from any accessible path to the agent's workspace.

    This is the primary tool for copying files from temp workspaces, context paths,
    or any other accessible location to the current agent's workspace.

    Args:
        source_path: Path to source file/directory (absolute or relative to accessible paths)
        destination_path: Destination path in workspace (relative to workspace root)
        overwrite: Whether to overwrite existing files/directories (default: False)

    Returns:
        Dictionary with copy operation results
    """
    source, destination = _validate_and_resolve_paths(source_path, destination_path)
    result = _perform_copy(source, destination, overwrite)

    return {
        "success": True,
        "operation": "copy_file",
        "details": result
    }


@app.tool()
def copy_files_batch(
    source_base_path: str,
    destination_base_path: str = "",
    include_patterns: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None,
    overwrite: bool = False
) -> Dict[str, Any]:
    """
    Copy multiple files with pattern matching and exclusions.

    This advanced tool allows copying multiple files at once with glob-style patterns
    for inclusion and exclusion, useful for copying entire directory structures
    while filtering out unwanted files.

    Args:
        source_base_path: Base path to copy from
        destination_base_path: Base path in workspace to copy to (default: workspace root)
        include_patterns: List of glob patterns for files to include (default: ["*"])
        exclude_patterns: List of glob patterns for files to exclude (default: [])
        overwrite: Whether to overwrite existing files (default: False)

    Returns:
        Dictionary with batch copy operation results
    """
    if include_patterns is None:
        include_patterns = ["*"]
    if exclude_patterns is None:
        exclude_patterns = []

    try:
        # Get allowed paths
        allowed_sources, allowed_destinations = _get_allowed_paths()

        # Validate source base path
        source_base = Path(source_base_path).resolve()
        if not source_base.exists():
            raise ValueError(f"Source base path does not exist: {source_base}")

        _validate_path_access(source_base, allowed_sources, "source")

        # Validate destination base path
        current_workspace = os.getenv("CURRENT_WORKSPACE")
        if not current_workspace:
            raise ValueError("CURRENT_WORKSPACE environment variable not set")

        workspace = Path(current_workspace).resolve()

        if destination_base_path:
            dest_base = (workspace / destination_base_path).resolve()
        else:
            dest_base = workspace

        _validate_path_access(dest_base, allowed_destinations, "destination")

        copied_files = []
        skipped_files = []
        errors = []

        # Get all file pairs to copy
        file_pairs = get_copy_file_pairs(
            source_base_path, destination_base_path, include_patterns, exclude_patterns
        )

        # Process each file pair
        for source_file, dest_file in file_pairs:
            rel_path_str = str(source_file.relative_to(Path(source_base_path).resolve()))

            try:
                # Check if destination exists
                if dest_file.exists() and not overwrite:
                    skipped_files.append({
                        "path": rel_path_str,
                        "reason": "destination exists (overwrite=false)"
                    })
                    continue

                # Create parent directories
                dest_file.parent.mkdir(parents=True, exist_ok=True)

                # Copy file
                shutil.copy2(source_file, dest_file)

                copied_files.append({
                    "source": str(source_file),
                    "destination": str(dest_file),
                    "relative_path": rel_path_str,
                    "size": dest_file.stat().st_size
                })

            except Exception as e:
                errors.append({
                    "path": rel_path_str,
                    "error": str(e)
                })

        return {
            "success": True,
            "operation": "copy_files_batch",
            "summary": {
                "copied": len(copied_files),
                "skipped": len(skipped_files),
                "errors": len(errors)
            },
            "details": {
                "copied_files": copied_files,
                "skipped_files": skipped_files,
                "errors": errors
            }
        }

    except Exception as e:
        return {
            "success": False,
            "operation": "copy_files_batch",
            "error": str(e)
        }


def main():
    """Main entry point for the workspace copy MCP server."""
    app.run()


if __name__ == "__main__":
    main()