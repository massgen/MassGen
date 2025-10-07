# -*- coding: utf-8 -*-
"""
File Operation Tracker for MassGen

This module provides tracking of file operations to enforce read-before-delete policies.
It ensures agents can only delete files they have read or understood first.
"""

from pathlib import Path
from typing import Set

from ..logger_config import logger


class FileOperationTracker:
    """
    Track file operations to enforce read-before-delete policy.

    This tracker maintains a set of files that have been read by the agent,
    allowing the system to prevent deletion of files that haven't been
    comprehended yet.
    """

    def __init__(self, enforce_read_before_delete: bool = True):
        """
        Initialize the file operation tracker.

        Args:
            enforce_read_before_delete: Whether to enforce read-before-delete policy
        """
        self._read_files: Set[Path] = set()
        self._created_files: Set[Path] = set()  # Files created by agent (exempt from read requirement)
        self.enforce_read_before_delete = enforce_read_before_delete

        logger.info(f"[FileOperationTracker] Initialized with enforce_read_before_delete={enforce_read_before_delete}")

    def mark_as_read(self, file_path: Path) -> None:
        """
        Mark a file as read/understood by the agent.

        This is called when the agent uses Read, read_multimodal_files,
        compare_files, or other tools that read file contents.

        Args:
            file_path: Path to the file that was read
        """
        resolved_path = file_path.resolve()
        self._read_files.add(resolved_path)
        logger.debug(f"[FileOperationTracker] Marked as read: {resolved_path}")

    def mark_as_created(self, file_path: Path) -> None:
        """
        Mark a file as created by the agent during this turn.

        Files created by the agent are exempt from read-before-delete requirements
        since the agent knows what it created.

        Args:
            file_path: Path to the file that was created
        """
        resolved_path = file_path.resolve()
        self._created_files.add(resolved_path)
        logger.debug(f"[FileOperationTracker] Marked as created: {resolved_path}")

    def was_read(self, file_path: Path) -> bool:
        """
        Check if a file was read by the agent.

        Args:
            file_path: Path to check

        Returns:
            True if the file was read or created by the agent
        """
        resolved_path = file_path.resolve()
        was_read = resolved_path in self._read_files
        was_created = resolved_path in self._created_files

        logger.debug(f"[FileOperationTracker] Checking read status for {resolved_path}: read={was_read}, created={was_created}")

        return was_read or was_created

    def can_delete(self, file_path: Path) -> tuple[bool, str | None]:
        """
        Check if a file can be deleted based on read-before-delete policy.

        Args:
            file_path: Path to the file to check

        Returns:
            Tuple of (can_delete: bool, reason: Optional[str])
            - can_delete: Whether deletion is allowed
            - reason: Explanation if deletion is blocked (None if allowed)
        """
        if not self.enforce_read_before_delete:
            return (True, None)

        resolved_path = file_path.resolve()

        # If file doesn't exist, allow deletion (nothing to delete)
        if not resolved_path.exists():
            return (True, None)

        # Check if file was read or created
        if self.was_read(resolved_path):
            return (True, None)

        # File hasn't been read - block deletion
        reason = f"Cannot delete '{resolved_path}': File must be read before deletion. " f"Use Read or read_multimodal_files tool to view the file first."
        logger.info(f"[FileOperationTracker] Blocking deletion: {reason}")
        return (False, reason)

    def can_delete_directory(self, dir_path: Path) -> tuple[bool, str | None]:
        """
        Check if a directory can be deleted based on read-before-delete policy.

        For directories, we check if all files within have been read.

        Args:
            dir_path: Path to the directory to check

        Returns:
            Tuple of (can_delete: bool, reason: Optional[str])
            - can_delete: Whether deletion is allowed
            - reason: Explanation if deletion is blocked (None if allowed)
        """
        if not self.enforce_read_before_delete:
            return (True, None)

        resolved_dir = dir_path.resolve()

        if not resolved_dir.exists() or not resolved_dir.is_dir():
            # Not a directory or doesn't exist
            return (True, None)

        # Check all files in directory
        unread_files = []
        for file_path in resolved_dir.rglob("*"):
            if file_path.is_file() and not self.was_read(file_path):
                unread_files.append(str(file_path.relative_to(resolved_dir)))

        if unread_files:
            # Limit to first 3 unread files for readable error message
            example_files = unread_files[:3]
            suffix = f" (and {len(unread_files) - 3} more)" if len(unread_files) > 3 else ""
            reason = f"Cannot delete directory '{resolved_dir}': Contains {len(unread_files)} unread file(s). " f"Examples: {', '.join(example_files)}{suffix}. " f"Please read files before deletion."
            logger.info(f"[FileOperationTracker] Blocking directory deletion: {reason}")
            return (False, reason)

        return (True, None)

    def clear(self) -> None:
        """
        Clear all tracked operations.

        This should be called at the start of each agent's turn to reset
        the tracker state.
        """
        read_count = len(self._read_files)
        created_count = len(self._created_files)

        self._read_files.clear()
        self._created_files.clear()

        logger.info(f"[FileOperationTracker] Cleared tracker (had {read_count} read files, {created_count} created files)")

    def get_stats(self) -> dict[str, int]:
        """
        Get statistics about tracked operations.

        Returns:
            Dictionary with tracking statistics
        """
        return {
            "read_files": len(self._read_files),
            "created_files": len(self._created_files),
            "total_tracked": len(self._read_files) + len(self._created_files),
        }
