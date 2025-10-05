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
- read_multimodal_files: Read image files and return as base64 data with MIME type
"""

import argparse
import base64
import difflib
import filecmp
import fnmatch
import mimetypes
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import fastmcp


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
    def extract_multimodal_files(path: str, max_size_mb: float = 0.25, compress_quality: int = 65, understanding_mode: bool = True) -> Dict[str, Any]:
        """
        Read multimodal files (images, etc.) and return as base64 data with MIME type.

        This tool is specifically designed for reading image files and other multimodal content,
        converting them to base64 format suitable for AI model processing. Large images are
        automatically compressed to avoid exceeding model context limits.

        Args:
            path: Path to the multimodal file (absolute or relative to workspace)
                  Supports common image formats: png, jpg, jpeg, gif, bmp, webp, svg
            max_size_mb: Maximum file size in MB after compression (default: 0.25)
                        Reduced default to prevent context window overflow
            compress_quality: JPEG compression quality 1-100 (default: 65)
                            Lower default for better context efficiency
            understanding_mode: If True, uses more aggressive compression for AI understanding tasks
                              (max 0.15MB, quality 50)

        Returns:
            Dictionary containing:
            - success: Whether operation succeeded
            - operation: "read_multimodal_files"
            - data: Base64 encoded file content with data URI scheme
            - mime_type: MIME type of the file
            - size: File size in bytes (after compression if applied)
            - original_size: Original file size in bytes
            - compressed: Whether compression was applied
            - path: Resolved file path

        Examples:
            read_multimodal_files("image.png")
            → {"data": "data:image/png;base64,iVBORw0...", "mime_type": "image/png"}

        Security:
            - Read-only operation
            - Path must be within allowed directories
            - Large files are automatically compressed to fit within limits
        """
        try:
            import io

            from PIL import Image

            # Apply understanding mode if enabled
            if understanding_mode:
                max_size_mb = min(max_size_mb, 0.15)  # Max 150KB for understanding mode
                compress_quality = min(compress_quality, 50)  # Lower quality for understanding

            # Resolve path
            if Path(path).is_absolute():
                file_path = Path(path).resolve()
            else:
                # Relative path - resolve relative to workspace
                file_path = (Path.cwd() / path).resolve()

            # Validate path access
            _validate_path_access(file_path, mcp.allowed_paths)

            # Check if file exists
            if not file_path.exists():
                return {
                    "success": False,
                    "operation": "read_multimodal_files",
                    "error": f"File does not exist: {file_path}",
                }

            if not file_path.is_file():
                return {
                    "success": False,
                    "operation": "read_multimodal_files",
                    "error": f"Path is not a file: {file_path}",
                }

            # Get MIME type
            mime_type, _ = mimetypes.guess_type(str(file_path))
            if mime_type is None:
                # Default MIME type for unknown files
                mime_type = "application/octet-stream"

            # Read file
            try:
                with open(file_path, "rb") as f:
                    file_content = f.read()

                original_size = len(file_content)
                max_size_bytes = max_size_mb * 1024 * 1024
                compressed = False

                # Check if it's an image that needs compression
                if mime_type and mime_type.startswith("image/") and mime_type != "image/svg+xml":
                    if original_size > max_size_bytes:
                        try:
                            # Open image with PIL
                            img = Image.open(io.BytesIO(file_content))

                            # Convert RGBA to RGB if needed for JPEG
                            if img.mode in ("RGBA", "LA", "P"):
                                background = Image.new("RGB", img.size, (255, 255, 255))
                                if img.mode == "P":
                                    img = img.convert("RGBA")
                                background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
                                img = background

                            # Start with original dimensions
                            current_img = img.copy()

                            # Try different compression levels and sizes
                            for scale in [1.0, 0.8, 0.6, 0.4, 0.2]:
                                if scale < 1.0:
                                    new_size = (int(img.width * scale), int(img.height * scale))
                                    current_img = img.resize(new_size, Image.Resampling.LANCZOS)

                                # Save to bytes with compression
                                output = io.BytesIO()
                                # Use actual compress_quality value (may be reduced by understanding_mode)
                                current_img.save(output, format="JPEG", quality=compress_quality, optimize=True)
                                compressed_content = output.getvalue()

                                if len(compressed_content) <= max_size_bytes:
                                    file_content = compressed_content
                                    mime_type = "image/jpeg"
                                    compressed = True
                                    break
                            else:
                                # If still too large after maximum compression, use lowest quality
                                output = io.BytesIO()
                                # For understanding mode, go even lower; otherwise use 30
                                final_quality = 20 if understanding_mode else 30
                                current_img.save(output, format="JPEG", quality=final_quality, optimize=True)
                                file_content = output.getvalue()
                                mime_type = "image/jpeg"
                                compressed = True

                        except Exception as e:
                            # If compression fails, continue with original
                            print(f"Warning: Failed to compress image: {e}")

                # Get final file size
                file_size = len(file_content)

                # Final check - if still too large, return error
                if file_size > 5 * 1024 * 1024:  # 5MB absolute limit
                    return {
                        "success": False,
                        "operation": "read_multimodal_files",
                        "error": f"File too large even after compression: {file_size / (1024*1024):.2f}MB. Maximum allowed: 5MB",
                    }

                # Encode to base64
                base64_content = base64.b64encode(file_content).decode("utf-8")

                # Create data URI
                data_uri = f"data:{mime_type};base64,{base64_content}"

                return {
                    "success": True,
                    "operation": "read_multimodal_files",
                    "data": data_uri,
                    "mime_type": mime_type,
                    "size": file_size,
                    "original_size": original_size,
                    "compressed": compressed,
                    "path": str(file_path),
                }

            except Exception as e:
                return {
                    "success": False,
                    "operation": "read_multimodal_files",
                    "error": f"Failed to read file: {e}",
                }

        except ImportError:
            return {
                "success": False,
                "operation": "read_multimodal_files",
                "error": "PIL (Pillow) is required for image compression. Install with: pip install Pillow",
            }
        except Exception as e:
            return {
                "success": False,
                "operation": "read_multimodal_files",
                "error": str(e),
            }

    print("🚀 Workspace Copy MCP Server started and ready")
    print(f"Allowed paths: {[str(p) for p in mcp.allowed_paths]}")

    return mcp
