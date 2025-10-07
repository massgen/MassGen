#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Workspace Tools MCP Server for MassGen

This MCP server provides workspace management tools for agents including file operations,
deletion, and comparison capabilities. It implements copy-on-write behavior for multi-agent
collaboration and provides safe file manipulation within allowed paths.

Tools provided:
- copy_file: Copy a single file or directory from any accessible path to workspace
- copy_files_batch: Copy multiple files with pattern matching and exclusions
- delete_file: Delete a single file or directory from workspace
- delete_files_batch: Delete multiple files with pattern matching
- compare_directories: Compare two directories and show differences
- compare_files: Compare two text files and show unified diff
- generate_and_store_image_with_input_images: Create variations of existing images using GPT-4o
- generate_and_store_image_no_input_images: Generate new images from text prompts using GPT-4o
- generate_and_store_video_no_input_images: Generate videos from text prompts using Sora-2
"""

import argparse
import base64
import difflib
import filecmp
import fnmatch
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import fastmcp
from dotenv import load_dotenv
from openai import OpenAI


def get_copy_file_pairs(
    allowed_paths: List[Path],
    source_base_path: str,
    destination_base_path: str = "",
    include_patterns: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None,
) -> List[Tuple[Path, Path]]:
    """
    Get all source->destination file pairs that would be copied by copy_files_batch.

    This function can be imported by the filesystem manager for permission validation.

    Args:
        allowed_paths: List of allowed base paths for validation
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

    # Validate source base path
    source_base = Path(source_base_path).resolve()
    if not source_base.exists():
        raise ValueError(f"Source base path does not exist: {source_base}")

    _validate_path_access(source_base, allowed_paths)

    # Handle destination base path - resolve relative paths relative to workspace
    if destination_base_path:
        if Path(destination_base_path).is_absolute():
            dest_base = Path(destination_base_path).resolve()
        else:
            # Relative path should be resolved relative to workspace (current working directory)
            dest_base = (Path.cwd() / destination_base_path).resolve()
    else:
        # No destination specified - this shouldn't happen for batch operations
        raise ValueError("destination_base_path is required for copy_files_batch")

    _validate_path_access(dest_base, allowed_paths)

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
        _validate_path_access(dest_file, allowed_paths)

        file_pairs.append((item, dest_file))

    return file_pairs


def _validate_path_access(path: Path, allowed_paths: List[Path]) -> None:
    """
    Validate that a path is within allowed directories.

    Args:
        path: Path to validate
        allowed_paths: List of allowed base paths

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


def _is_critical_path(path: Path, allowed_paths: List[Path] = None) -> bool:
    """
    Check if a path is a critical system file that should not be deleted.

    Critical paths include:
    - .git directories (version control)
    - .env files (environment variables)
    - .massgen directories (MassGen metadata) - UNLESS within an allowed workspace
    - node_modules (package dependencies)
    - venv/.venv (Python virtual environments)
    - __pycache__ (Python cache)
    - massgen_logs (logging)

    Args:
        path: Path to check
        allowed_paths: List of allowed base paths (workspaces). If provided and path
                      is within an allowed path, only check for critical patterns
                      within that workspace (not in parent paths).

    Returns:
        True if path is critical and should not be deleted

    Examples:
        # Outside workspace - blocks any .massgen in path
        _is_critical_path(Path("/home/.massgen/config"))  → True (blocked)

        # Inside workspace - allows user files even if parent has .massgen
        workspace = Path("/home/.massgen/workspaces/workspace1")
        _is_critical_path(Path("/home/.massgen/workspaces/workspace1/user_dir"), [workspace])  → False (allowed)
        _is_critical_path(Path("/home/.massgen/workspaces/workspace1/.git"), [workspace])  → True (blocked)
    """
    CRITICAL_PATTERNS = [
        ".git",
        ".env",
        ".massgen",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "massgen_logs",
    ]

    resolved_path = path.resolve()

    # If path is within an allowed workspace, only check for critical patterns
    # within the workspace itself (not in parent directories)
    if allowed_paths:
        for allowed_path in allowed_paths:
            try:
                # Get the relative path from workspace
                rel_path = resolved_path.relative_to(allowed_path.resolve())
                # Only check parts within the workspace
                for part in rel_path.parts:
                    if part in CRITICAL_PATTERNS:
                        return True
                # Check if the file name itself is critical
                if resolved_path.name in CRITICAL_PATTERNS:
                    return True
                # Path is within workspace and not critical
                return False
            except ValueError:
                # Not within this allowed path, continue checking
                continue

    # Path is not within any allowed workspace, check entire path
    parts = resolved_path.parts
    for part in parts:
        if part in CRITICAL_PATTERNS:
            return True

    # Check if the file name itself is critical
    if resolved_path.name in CRITICAL_PATTERNS:
        return True

    return False


def _is_text_file(path: Path) -> bool:
    """
    Check if a file is likely a text file (not binary).

    Uses simple heuristic: try to read as text and check for null bytes.

    TODO: Handle multi-modal files once implemented.

    Args:
        path: Path to check

    Returns:
        True if file appears to be text
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            # Read first 8KB to check
            chunk = f.read(8192)
            # If it contains null bytes, it's probably binary
            if "\0" in chunk:
                return False
        return True
    except (UnicodeDecodeError, OSError):
        return False


def _is_permission_path_root(path: Path, allowed_paths: List[Path]) -> bool:
    """
    Check if a path is exactly one of the permission path roots.

    This prevents deletion of workspace directories, context path roots, etc.,
    while still allowing deletion of files and subdirectories within them.

    Args:
        path: Path to check
        allowed_paths: List of allowed base paths (permission path roots)

    Returns:
        True if path is exactly a permission path root

    Examples (Unix/macOS):
        allowed_paths = [Path("/workspace1"), Path("/context")]
        _is_permission_path_root(Path("/workspace1"))              → True  (blocked)
        _is_permission_path_root(Path("/workspace1/file.txt"))    → False (allowed)
        _is_permission_path_root(Path("/workspace1/subdir"))      → False (allowed)
        _is_permission_path_root(Path("/context"))                → True  (blocked)
        _is_permission_path_root(Path("/context/config.yaml"))    → False (allowed)

    Examples (Windows):
        allowed_paths = [Path("C:\\workspace1"), Path("D:\\context")]
        _is_permission_path_root(Path("C:\\workspace1"))           → True  (blocked)
        _is_permission_path_root(Path("C:\\workspace1\\file.txt")) → False (allowed)
        _is_permission_path_root(Path("D:\\context"))             → True  (blocked)
        _is_permission_path_root(Path("D:\\context\\data.json"))  → False (allowed)
    """
    resolved_path = path.resolve()
    for allowed_path in allowed_paths:
        if resolved_path == allowed_path.resolve():
            return True
    return False


def _validate_and_resolve_paths(allowed_paths: List[Path], source_path: str, destination_path: str) -> tuple[Path, Path]:
    """
    Validate source and destination paths for copy operations.

    Args:
        allowed_paths: List of allowed base paths for validation
        source_path: Source file/directory path
        destination_path: Destination path in workspace

    Returns:
        Tuple of (resolved_source, resolved_destination)

    Raises:
        ValueError: If paths are invalid
    """
    try:
        # Validate and resolve source
        source = Path(source_path).resolve()
        if not source.exists():
            raise ValueError(f"Source path does not exist: {source}")

        _validate_path_access(source, allowed_paths)

        # Handle destination path - resolve relative paths relative to workspace
        if Path(destination_path).is_absolute():
            destination = Path(destination_path).resolve()
        else:
            # Relative path should be resolved relative to workspace (current working directory)
            destination = (Path.cwd() / destination_path).resolve()

        _validate_path_access(destination, allowed_paths)

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
            return {"type": "file", "source": str(source), "destination": str(destination), "size": destination.stat().st_size}
        elif source.is_dir():
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(source, destination)

            file_count = len([f for f in destination.rglob("*") if f.is_file()])
            return {"type": "directory", "source": str(source), "destination": str(destination), "file_count": file_count}
        else:
            raise ValueError(f"Source is neither file nor directory: {source}")

    except Exception as e:
        raise ValueError(f"Copy operation failed: {e}")


async def create_server() -> fastmcp.FastMCP:
    """Factory function to create and configure the workspace copy server."""

    parser = argparse.ArgumentParser(description="Workspace Copy MCP Server")
    parser.add_argument(
        "--allowed-paths",
        type=str,
        nargs="*",
        default=[],
        help="List of allowed base paths for file operations (default: no restrictions)",
    )
    args = parser.parse_args()

    # Create the FastMCP server
    mcp = fastmcp.FastMCP("Workspace Copy")

    # Add allowed paths from arguments
    mcp.allowed_paths = [Path(p).resolve() for p in args.allowed_paths]

    # Below is for debugging - can be uncommented if needed
    # @mcp.tool()
    # def get_cwd() -> Dict[str, Any]:
    #     """
    #     Get the current working directory of the workspace copy server.

    #     Useful for testing and verifying that relative paths resolve correctly.

    #     Returns:
    #         Dictionary with current working directory information
    #     """
    #     cwd = Path.cwd()
    #     return {
    #         "success": True,
    #         "operation": "get_cwd",
    #         "cwd": str(cwd),
    #         "absolute_path": str(cwd.resolve()),
    #         "allowed_paths": [str(p) for p in mcp.allowed_paths],
    #         "allowed_paths_count": len(mcp.allowed_paths),
    #     }

    @mcp.tool()
    def copy_file(source_path: str, destination_path: str, overwrite: bool = False) -> Dict[str, Any]:
        """
        Copy a file or directory from any accessible path to the agent's workspace.

        This is the primary tool for copying files from temp workspaces, context paths,
        or any other accessible location to the current agent's workspace.

        Args:
            source_path: Path to source file/directory (must be absolute path)
            destination_path: Destination path - can be:
                - Relative path: Resolved relative to your workspace (e.g., "output/file.txt")
                - Absolute path: Must be within allowed directories for security
            overwrite: Whether to overwrite existing files/directories (default: False)

        Returns:
            Dictionary with copy operation results
        """
        source, destination = _validate_and_resolve_paths(mcp.allowed_paths, source_path, destination_path)
        result = _perform_copy(source, destination, overwrite)

        return {"success": True, "operation": "copy_file", "details": result}

    @mcp.tool()
    def copy_files_batch(
        source_base_path: str,
        destination_base_path: str = "",
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        """
        Copy multiple files with pattern matching and exclusions.

        This advanced tool allows copying multiple files at once with glob-style patterns
        for inclusion and exclusion, useful for copying entire directory structures
        while filtering out unwanted files.

        Args:
            source_base_path: Base path to copy from (must be absolute path)
            destination_base_path: Base destination path - can be:
                - Relative path: Resolved relative to your workspace (e.g., "project/output")
                - Absolute path: Must be within allowed directories for security
                - Empty string: Copy to workspace root
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
            copied_files = []
            skipped_files = []
            errors = []

            # Get all file pairs to copy
            file_pairs = get_copy_file_pairs(mcp.allowed_paths, source_base_path, destination_base_path, include_patterns, exclude_patterns)

            # Process each file pair
            for source_file, dest_file in file_pairs:
                rel_path_str = str(source_file.relative_to(Path(source_base_path).resolve()))

                try:
                    # Check if destination exists
                    if dest_file.exists() and not overwrite:
                        skipped_files.append({"path": rel_path_str, "reason": "destination exists (overwrite=false)"})
                        continue

                    # Create parent directories
                    dest_file.parent.mkdir(parents=True, exist_ok=True)

                    # Copy file
                    shutil.copy2(source_file, dest_file)

                    copied_files.append({"source": str(source_file), "destination": str(dest_file), "relative_path": rel_path_str, "size": dest_file.stat().st_size})

                except Exception as e:
                    errors.append({"path": rel_path_str, "error": str(e)})

            return {
                "success": True,
                "operation": "copy_files_batch",
                "summary": {"copied": len(copied_files), "skipped": len(skipped_files), "errors": len(errors)},
                "details": {"copied_files": copied_files, "skipped_files": skipped_files, "errors": errors},
            }

        except Exception as e:
            return {"success": False, "operation": "copy_files_batch", "error": str(e)}

    @mcp.tool()
    def delete_file(path: str, recursive: bool = False) -> Dict[str, Any]:
        """
        Delete a file or directory from the workspace.

        This tool allows agents to clean up outdated files or directories, helping maintain
        a clean workspace without cluttering it with old versions.

        Args:
            path: Path to file/directory to delete - can be:
                - Relative path: Resolved relative to your workspace (e.g., "old_file.txt")
                - Absolute path: Must be within allowed directories for security
            recursive: Whether to delete directories and their contents (default: False)
                      Required for non-empty directories

        Returns:
            Dictionary with deletion operation results

        Security:
            - Requires WRITE permission on path (validated by PathPermissionManager hook)
            - Must be within allowed directories
            - System files (.git, .env, etc.) cannot be deleted
            - Permission path roots themselves cannot be deleted
            - Protected paths specified in config are immune from deletion
        """
        try:
            # Resolve path
            if Path(path).is_absolute():
                target_path = Path(path).resolve()
            else:
                # Relative path - resolve relative to workspace
                target_path = (Path.cwd() / path).resolve()

            # Validate path access
            _validate_path_access(target_path, mcp.allowed_paths)

            # Check if path exists
            if not target_path.exists():
                return {"success": False, "operation": "delete_file", "error": f"Path does not exist: {target_path}"}

            # Prevent deletion of critical system paths
            if _is_critical_path(target_path, mcp.allowed_paths):
                return {"success": False, "operation": "delete_file", "error": f"Cannot delete critical system path: {target_path}"}

            # Prevent deletion of permission path roots themselves
            if _is_permission_path_root(target_path, mcp.allowed_paths):
                return {
                    "success": False,
                    "operation": "delete_file",
                    "error": f"Cannot delete permission path root: {target_path}. You can delete files/directories within it, but not the root itself.",
                }

            # Handle file deletion
            if target_path.is_file():
                size = target_path.stat().st_size
                target_path.unlink()
                return {"success": True, "operation": "delete_file", "details": {"type": "file", "path": str(target_path), "size": size}}

            # Handle directory deletion
            elif target_path.is_dir():
                if not recursive:
                    # Check if directory is empty
                    if any(target_path.iterdir()):
                        return {"success": False, "operation": "delete_file", "error": f"Directory not empty (use recursive=true): {target_path}"}
                    target_path.rmdir()
                else:
                    # Count files before deletion
                    file_count = len([f for f in target_path.rglob("*") if f.is_file()])
                    shutil.rmtree(target_path)
                    return {"success": True, "operation": "delete_file", "details": {"type": "directory", "path": str(target_path), "file_count": file_count}}

                return {"success": True, "operation": "delete_file", "details": {"type": "directory", "path": str(target_path)}}

            else:
                return {"success": False, "operation": "delete_file", "error": f"Path is neither file nor directory: {target_path}"}

        except Exception as e:
            return {"success": False, "operation": "delete_file", "error": str(e)}

    @mcp.tool()
    def delete_files_batch(
        base_path: str,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Delete multiple files matching patterns.

        This advanced tool allows deleting multiple files at once with glob-style patterns
        for inclusion and exclusion, useful for cleaning up entire directory structures
        while preserving specific files.

        Args:
            base_path: Base directory to search in - can be:
                - Relative path: Resolved relative to your workspace (e.g., "build")
                - Absolute path: Must be within allowed directories for security
            include_patterns: List of glob patterns for files to include (default: ["*"])
            exclude_patterns: List of glob patterns for files to exclude (default: [])

        Returns:
            Dictionary with batch deletion results including:
            - deleted: List of deleted files
            - skipped: List of skipped files (read-only or system files)
            - errors: List of errors encountered

        Security:
            - Requires WRITE permission on each file
            - Must be within allowed directories
            - System files (.git, .env, etc.) cannot be deleted
        """
        if include_patterns is None:
            include_patterns = ["*"]
        if exclude_patterns is None:
            exclude_patterns = []

        try:
            deleted_files = []
            skipped_files = []
            errors = []

            # Resolve base path
            if Path(base_path).is_absolute():
                base = Path(base_path).resolve()
            else:
                base = (Path.cwd() / base_path).resolve()

            # Validate base path
            if not base.exists():
                return {"success": False, "operation": "delete_files_batch", "error": f"Base path does not exist: {base}"}

            _validate_path_access(base, mcp.allowed_paths)

            # Collect files to delete
            for item in base.rglob("*"):
                if not item.is_file():
                    continue

                # Get relative path from base
                rel_path = item.relative_to(base)
                rel_path_str = str(rel_path)

                # Check include patterns
                included = any(fnmatch.fnmatch(rel_path_str, pattern) for pattern in include_patterns)
                if not included:
                    continue

                # Check exclude patterns
                excluded = any(fnmatch.fnmatch(rel_path_str, pattern) for pattern in exclude_patterns)
                if excluded:
                    continue

                try:
                    # Check if this is a critical system file
                    if _is_critical_path(item, mcp.allowed_paths):
                        skipped_files.append({"path": rel_path_str, "reason": "system file (protected)"})
                        continue

                    # Check if this is a permission path root
                    if _is_permission_path_root(item, mcp.allowed_paths):
                        skipped_files.append({"path": rel_path_str, "reason": "permission path root (protected)"})
                        continue

                    # Validate path access
                    _validate_path_access(item, mcp.allowed_paths)

                    # Delete file
                    size = item.stat().st_size
                    item.unlink()

                    deleted_files.append({"path": str(item), "relative_path": rel_path_str, "size": size})

                except Exception as e:
                    errors.append({"path": rel_path_str, "error": str(e)})

            return {
                "success": True,
                "operation": "delete_files_batch",
                "summary": {"deleted": len(deleted_files), "skipped": len(skipped_files), "errors": len(errors)},
                "details": {"deleted_files": deleted_files, "skipped_files": skipped_files, "errors": errors},
            }

        except Exception as e:
            return {"success": False, "operation": "delete_files_batch", "error": str(e)}

    @mcp.tool()
    def compare_directories(dir1: str, dir2: str, show_content_diff: bool = False) -> Dict[str, Any]:
        """
        Compare two directories and show differences.

        This tool helps understand what changed between two workspaces or directory states,
        making it easier to review changes before deployment or understand agent modifications.

        Args:
            dir1: First directory path (absolute or relative to workspace)
            dir2: Second directory path (absolute or relative to workspace)
            show_content_diff: Whether to include unified diffs of different files (default: False)

        Returns:
            Dictionary with comparison results:
            - only_in_dir1: Files only in first directory
            - only_in_dir2: Files only in second directory
            - different: Files that exist in both but have different content
            - identical: Files that are identical
            - content_diffs: Optional unified diffs (if show_content_diff=True)

        Security:
            - Read-only operation, never modifies files
            - Both paths must be within allowed directories
        """
        try:
            # Resolve paths
            path1 = Path(dir1).resolve() if Path(dir1).is_absolute() else (Path.cwd() / dir1).resolve()
            path2 = Path(dir2).resolve() if Path(dir2).is_absolute() else (Path.cwd() / dir2).resolve()

            # Validate paths
            _validate_path_access(path1, mcp.allowed_paths)
            _validate_path_access(path2, mcp.allowed_paths)

            if not path1.exists() or not path1.is_dir():
                return {"success": False, "operation": "compare_directories", "error": f"First path is not a directory: {path1}"}

            if not path2.exists() or not path2.is_dir():
                return {"success": False, "operation": "compare_directories", "error": f"Second path is not a directory: {path2}"}

            # Use filecmp for comparison
            dcmp = filecmp.dircmp(str(path1), str(path2))

            result = {
                "success": True,
                "operation": "compare_directories",
                "details": {
                    "only_in_dir1": list(dcmp.left_only),
                    "only_in_dir2": list(dcmp.right_only),
                    "different": list(dcmp.diff_files),
                    "identical": list(dcmp.same_files),
                },
            }

            # Add content diffs if requested
            if show_content_diff and dcmp.diff_files:
                content_diffs = {}
                for filename in dcmp.diff_files:
                    file1 = path1 / filename
                    file2 = path2 / filename
                    try:
                        # Only diff text files
                        if _is_text_file(file1) and _is_text_file(file2):
                            with open(file1) as f1, open(file2) as f2:
                                lines1 = f1.readlines()
                                lines2 = f2.readlines()
                            diff = list(difflib.unified_diff(lines1, lines2, fromfile=f"dir1/{filename}", tofile=f"dir2/{filename}", lineterm=""))
                            content_diffs[filename] = "\n".join(diff[:100])  # Limit to 100 lines
                    except Exception as e:
                        content_diffs[filename] = f"Error generating diff: {e}"

                result["details"]["content_diffs"] = content_diffs

            return result

        except Exception as e:
            return {"success": False, "operation": "compare_directories", "error": str(e)}

    @mcp.tool()
    def compare_files(file1: str, file2: str, context_lines: int = 3) -> Dict[str, Any]:
        """
        Compare two text files and show unified diff.

        This tool provides detailed line-by-line comparison of two files,
        making it easy to see exactly what changed between versions.

        Args:
            file1: First file path (absolute or relative to workspace)
            file2: Second file path (absolute or relative to workspace)
            context_lines: Number of context lines around changes (default: 3)

        Returns:
            Dictionary with comparison results:
            - identical: Boolean indicating if files are identical
            - diff: Unified diff output
            - stats: Statistics (lines added/removed/changed)

        Security:
            - Read-only operation, never modifies files
            - Both paths must be within allowed directories
            - Works best with text files
        """
        try:
            # Resolve paths
            path1 = Path(file1).resolve() if Path(file1).is_absolute() else (Path.cwd() / file1).resolve()
            path2 = Path(file2).resolve() if Path(file2).is_absolute() else (Path.cwd() / file2).resolve()

            # Validate paths
            _validate_path_access(path1, mcp.allowed_paths)
            _validate_path_access(path2, mcp.allowed_paths)

            if not path1.exists() or not path1.is_file():
                return {"success": False, "operation": "compare_files", "error": f"First path is not a file: {path1}"}

            if not path2.exists() or not path2.is_file():
                return {"success": False, "operation": "compare_files", "error": f"Second path is not a file: {path2}"}

            # Read files
            try:
                with open(path1) as f1:
                    lines1 = f1.readlines()
                with open(path2) as f2:
                    lines2 = f2.readlines()
            except UnicodeDecodeError:
                return {"success": False, "operation": "compare_files", "error": "Files appear to be binary, not text"}

            # Generate diff
            diff = list(difflib.unified_diff(lines1, lines2, fromfile=str(path1), tofile=str(path2), lineterm="", n=context_lines))

            # Calculate stats
            added = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
            removed = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))

            return {
                "success": True,
                "operation": "compare_files",
                "details": {"identical": len(diff) == 0, "diff": "\n".join(diff[:500]), "stats": {"added": added, "removed": removed, "changed": min(added, removed)}},
            }

        except Exception as e:
            return {"success": False, "operation": "compare_files", "error": str(e)}

    @mcp.tool()
    def generate_and_store_image_with_input_images(
        base_image_paths: List[str],
        prompt: str = "Create a variation of the provided images",
        model: str = "gpt-4o",
        n: int = 1,
        storage_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create variations based on multiple input images using OpenAI's gpt-4o API.

        This tool generates image variations based on multiple base images using OpenAI's gpt-4o API
        and saves them to the workspace with automatic organization.

        Args:
            base_image_paths: List of paths to base images (PNG/JPEG files, less than 4MB)
                        - Relative path: Resolved relative to workspace
                        - Absolute path: Must be within allowed directories
            prompt: Text description for the variation (default: "Create a variation of the provided images")
            model: Model to use (default: "gpt-4o")
            n: Number of variations to generate (default: 1)
            storage_path: Directory path where to save variations (optional)
                         - Relative path: Resolved relative to workspace
                         - Absolute path: Must be within allowed directories
                         - None/empty: Saves to workspace root

        Returns:
            Dictionary containing:
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
        from datetime import datetime

        try:
            # Load environment variables
            script_dir = Path(__file__).parent.parent.parent
            env_path = script_dir / ".env"
            if env_path.exists():
                load_dotenv(env_path)
            else:
                load_dotenv()

            openai_api_key = os.getenv("OPENAI_API_KEY")

            if not openai_api_key:
                return {
                    "success": False,
                    "operation": "generate_and_store_image_with_input_images",
                    "error": "OpenAI API key not found. Please set OPENAI_API_KEY in .env file or environment variable.",
                }

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
                _validate_path_access(image_path, mcp.allowed_paths)

                if not image_path.exists():
                    return {
                        "success": False,
                        "operation": "generate_and_store_image_with_input_images",
                        "error": f"Image file does not exist: {image_path}",
                    }

                # Allow both PNG and JPEG formats
                if image_path.suffix.lower() not in [".png", ".jpg", ".jpeg"]:
                    return {
                        "success": False,
                        "operation": "generate_and_store_image_with_input_images",
                        "error": f"Image must be PNG or JPEG format: {image_path}",
                    }

                # Check file size (must be less than 4MB)
                file_size = image_path.stat().st_size
                if file_size > 4 * 1024 * 1024:
                    return {
                        "success": False,
                        "operation": "generate_and_store_image_with_input_images",
                        "error": f"Image file too large (must be < 4MB): {image_path} is {file_size / (1024*1024):.2f}MB",
                    }

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
            _validate_path_access(storage_dir, mcp.allowed_paths)
            storage_dir.mkdir(parents=True, exist_ok=True)

            try:
                # print("Content for OpenAI API:", str(content))
                # Generate variations using gpt-4o API with all images at once
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
                        return {
                            "success": False,
                            "operation": "generate_and_store_image_with_input_images",
                            "error": f"No images generated. Response: {' '.join(text_outputs)}",
                        }

            except Exception as api_error:
                return {
                    "success": False,
                    "operation": "generate_and_store_image_with_input_images",
                    "error": f"OpenAI API error: {str(api_error)}",
                }

            return {
                "success": True,
                "operation": "generate_and_store_image_with_input_images",
                "note": "If no input images were provided, you must use generate_and_store_image_no_input_images tool.",
                "images": all_variations,
                "model": model,
                "prompt": prompt,
                "total_images": len(all_variations),
            }

        except Exception as e:
            return {
                "success": False,
                "operation": "generate_and_store_image_with_input_images",
                "error": f"Failed to generate variations: {str(e)}",
            }

    @mcp.tool()
    def generate_and_store_image_no_input_images(
        prompt: str,
        model: str = "gpt-4o",
        storage_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate image using OpenAI's response with gpt-4o **WITHOUT ANY INPUT IMAGES** and store it in the workspace.

        This tool Generate image using OpenAI's response with gpt-4o **WITHOUT ANY INPUT IMAGES** and store it in the workspace.

        Args:
            prompt: Text description of the image to generate
            model: Model to use for generation (default: "gpt-4o")
                   Options: "gpt-4o"
            n: Number of images to generate (default: 1)
               - gpt-4o: only 1
            storage_path: Directory path where to save the image (optional)
                         - Relative path: Resolved relative to workspace (e.g., "images/generated")
                         - Absolute path: Must be within allowed directories
                         - None/empty: Saves to workspace root

        Returns:
            Dictionary containing:
            - success: Whether operation succeeded
            - operation: "generate_and_store_image_no_input_images"
            - note: Note about operation
            - images: List of generated images with file paths and metadata
            - model: Model used for generation
            - prompt: The prompt used for generation
            - total_images: Total number of images generated and saved
            - images: List of generated images with file paths and metadata

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
        from datetime import datetime

        try:
            # Try to find and load .env file from multiple locations
            # 1. Try loading from script directory
            script_dir = Path(__file__).parent.parent.parent  # Go up to project root
            env_path = script_dir / ".env"
            if env_path.exists():
                load_dotenv(env_path)
            else:
                # 2. Try loading from current directory and parent directories
                load_dotenv()

            # Get API key from environment (load_dotenv will have loaded .env file)
            openai_api_key = os.getenv("OPENAI_API_KEY")

            if not openai_api_key:
                return {
                    "success": False,
                    "operation": "generate_and_store_image",
                    "error": "OpenAI API key not found. Please set OPENAI_API_KEY in .env file or environment variable.",
                }

            # Initialize OpenAI client
            client = OpenAI(api_key=openai_api_key)

            # Determine storage directory
            if storage_path:
                if Path(storage_path).is_absolute():
                    storage_dir = Path(storage_path).resolve()
                else:
                    storage_dir = (Path.cwd() / storage_path).resolve()
            else:
                storage_dir = Path.cwd()

            # Validate storage directory is within allowed paths
            _validate_path_access(storage_dir, mcp.allowed_paths)

            # Create directory if it doesn't exist
            storage_dir.mkdir(parents=True, exist_ok=True)

            try:
                # Generate image using OpenAI API with gpt-4o non-streaming format
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

                return result

            except Exception as api_error:
                print(f"OpenAI API error: {str(api_error)}")
                return {
                    "success": False,
                    "operation": "generate_and_store_image_no_input_images",
                    "error": f"OpenAI API error: {str(api_error)}",
                }

        except Exception as e:
            return {
                "success": False,
                "operation": "generate_and_store_image_no_input_images",
                "error": f"Failed to generate or save image: {str(e)}",
            }

    @mcp.tool()
    def generate_and_store_video_no_input_images(
        prompt: str,
        model: str = "sora-2",
        seconds: int = 4,
        storage_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a video from a text prompt using OpenAI's Sora-2 API.

        This tool generates a video based on a text prompt using OpenAI's Sora-2 API
        and saves it to the workspace with automatic organization.

        Args:
            prompt: Text description for the video to generate
            model: Model to use (default: "sora-2")
            storage_path: Directory path where to save the video (optional)
                         - Relative path: Resolved relative to workspace
                         - Absolute path: Must be within allowed directories
                         - None/empty: Saves to workspace root

        Returns:
            Dictionary containing:
            - success: Whether operation succeeded
            - operation: "generate_and_store_video_no_input_images"
            - video_path: Path to the saved video file
            - model: Model used for generation
            - prompt: The prompt used
            - duration: Time taken for generation in seconds

        Examples:
            generate_and_store_video_no_input_images("A cool cat on a motorcycle in the night")
            → Generates a video and saves to workspace root

            generate_and_store_video_no_input_images("Dancing robot", storage_path="videos/")
            → Generates a video and saves to videos/ directory

        Security:
            - Requires valid OpenAI API key with Sora-2 access
            - Files are saved to specified path within workspace
        """
        import time
        from datetime import datetime

        try:
            # Load environment variables
            script_dir = Path(__file__).parent.parent.parent
            env_path = script_dir / ".env"
            if env_path.exists():
                load_dotenv(env_path)
            else:
                load_dotenv()

            openai_api_key = os.getenv("OPENAI_API_KEY")

            if not openai_api_key:
                return {
                    "success": False,
                    "operation": "generate_and_store_video_no_input_images",
                    "error": "OpenAI API key not found. Please set OPENAI_API_KEY in .env file or environment variable.",
                }

            # Initialize OpenAI client
            client = OpenAI(api_key=openai_api_key)

            # Determine storage directory
            if storage_path:
                if Path(storage_path).is_absolute():
                    storage_dir = Path(storage_path).resolve()
                else:
                    storage_dir = (Path.cwd() / storage_path).resolve()
            else:
                storage_dir = Path.cwd()

            # Validate storage directory is within allowed paths
            _validate_path_access(storage_dir, mcp.allowed_paths)

            # Create directory if it doesn't exist
            storage_dir.mkdir(parents=True, exist_ok=True)

            try:
                start_time = time.time()

                # Start video generation (no print statements to avoid MCP JSON parsing issues)
                video = client.videos.create(
                    model=model,
                    prompt=prompt,
                    seconds=str(seconds),
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
                    return {
                        "success": False,
                        "operation": "generate_and_store_video_no_input_images",
                        "error": message,
                    }

                # Download video content
                content = client.videos.download_content(video.id, variant="video")

                # Generate filename with timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                clean_prompt = "".join(c for c in prompt[:30] if c.isalnum() or c in (" ", "-", "_")).strip()
                clean_prompt = clean_prompt.replace(" ", "_")
                filename = f"{timestamp}_{clean_prompt}.mp4"

                # Full file path
                file_path = storage_dir / filename

                # Write video to file
                content.write_to_file(str(file_path))

                # Calculate duration
                duration = time.time() - start_time

                # Get file size
                file_size = file_path.stat().st_size

                return {
                    "success": True,
                    "operation": "generate_and_store_video_no_input_images",
                    "video_path": str(file_path),
                    "filename": filename,
                    "size": file_size,
                    "model": model,
                    "prompt": prompt,
                    "duration": duration,
                }

            except Exception as api_error:
                return {
                    "success": False,
                    "operation": "generate_and_store_video_no_input_images",
                    "error": f"OpenAI API error: {str(api_error)}",
                }

        except Exception as e:
            return {
                "success": False,
                "operation": "generate_and_store_video_no_input_images",
                "error": f"Failed to generate or save video: {str(e)}",
            }

    return mcp
