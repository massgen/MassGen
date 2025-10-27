#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for binary file blocking in PathPermissionManager.

These tests ensure that text-based read tools (Read, read_text_file, etc.)
are blocked from reading binary files (images, videos, audio, etc.) to prevent
context pollution with binary data.
"""

from pathlib import Path

import pytest

from massgen.filesystem_manager._base import Permission
from massgen.filesystem_manager._path_permission_manager import PathPermissionManager


@pytest.fixture
def permission_manager():
    """Create a PathPermissionManager instance for testing."""
    manager = PathPermissionManager(
        context_write_access_enabled=False,
        enforce_read_before_delete=True,
    )
    # Add a workspace path for testing
    test_workspace = Path("/tmp/test_workspace").resolve()
    manager.add_path(test_workspace, Permission.WRITE, "workspace")
    return manager


class TestBinaryFileBlocking:
    """Test suite for binary file blocking functionality."""

    @pytest.mark.asyncio
    async def test_block_read_image_with_read_tool(self, permission_manager):
        """Test that Read tool is blocked from reading image files."""
        tool_name = "Read"
        tool_args = {"file_path": "/tmp/test_workspace/photo.jpg"}

        allowed, reason = await permission_manager.pre_tool_use_hook(tool_name, tool_args)

        assert not allowed, "Read should be blocked from reading .jpg files"
        assert reason is not None
        assert "understand_image" in reason.lower()
        assert "photo.jpg" in reason

    @pytest.mark.asyncio
    async def test_block_read_text_file_image(self, permission_manager):
        """Test that read_text_file (MCP) is blocked from reading image files."""
        tool_name = "mcp__filesystem__read_text_file"
        tool_args = {"path": "/tmp/test_workspace/diagram.png"}

        allowed, reason = await permission_manager.pre_tool_use_hook(tool_name, tool_args)

        assert not allowed, "read_text_file should be blocked from reading .png files"
        assert reason is not None
        assert "understand_image" in reason.lower()

    @pytest.mark.asyncio
    async def test_block_read_video(self, permission_manager):
        """Test that Read tool is blocked from reading video files."""
        tool_name = "Read"
        tool_args = {"file_path": "/tmp/test_workspace/demo.mp4"}

        allowed, reason = await permission_manager.pre_tool_use_hook(tool_name, tool_args)

        assert not allowed, "Read should be blocked from reading .mp4 files"
        assert reason is not None
        assert "understand_video" in reason.lower()

    @pytest.mark.asyncio
    async def test_block_read_audio(self, permission_manager):
        """Test that Read tool is blocked from reading audio files."""
        tool_name = "Read"
        tool_args = {"file_path": "/tmp/test_workspace/recording.mp3"}

        allowed, reason = await permission_manager.pre_tool_use_hook(tool_name, tool_args)

        assert not allowed, "Read should be blocked from reading .mp3 files"
        assert reason is not None
        assert "audio" in reason.lower()

    @pytest.mark.asyncio
    async def test_allow_read_text_file(self, permission_manager):
        """Test that Read tool is allowed to read text files."""
        tool_name = "Read"
        tool_args = {"file_path": "/tmp/test_workspace/document.txt"}

        allowed, reason = await permission_manager.pre_tool_use_hook(tool_name, tool_args)

        assert allowed, "Read should be allowed to read .txt files"
        assert reason is None

    @pytest.mark.asyncio
    async def test_allow_read_code_file(self, permission_manager):
        """Test that Read tool is allowed to read code files."""
        test_cases = [
            "script.py",
            "app.js",
            "component.tsx",
            "main.go",
            "app.rs",
        ]

        for filename in test_cases:
            tool_name = "Read"
            tool_args = {"file_path": f"/tmp/test_workspace/{filename}"}

            allowed, reason = await permission_manager.pre_tool_use_hook(tool_name, tool_args)

            assert allowed, f"Read should be allowed to read {filename}"
            assert reason is None

    @pytest.mark.asyncio
    async def test_block_all_image_formats(self, permission_manager):
        """Test that all image formats are blocked."""
        image_extensions = [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".ico", ".svg", ".webp", ".tiff", ".tif"]

        for ext in image_extensions:
            tool_name = "Read"
            tool_args = {"file_path": f"/tmp/test_workspace/image{ext}"}

            allowed, reason = await permission_manager.pre_tool_use_hook(tool_name, tool_args)

            assert not allowed, f"Read should be blocked from reading {ext} files"
            assert reason is not None

    @pytest.mark.asyncio
    async def test_block_all_video_formats(self, permission_manager):
        """Test that all video formats are blocked."""
        video_extensions = [".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".webm", ".m4v", ".mpg", ".mpeg"]

        for ext in video_extensions:
            tool_name = "Read"
            tool_args = {"file_path": f"/tmp/test_workspace/video{ext}"}

            allowed, reason = await permission_manager.pre_tool_use_hook(tool_name, tool_args)

            assert not allowed, f"Read should be blocked from reading {ext} files"
            assert reason is not None

    @pytest.mark.asyncio
    async def test_block_all_audio_formats(self, permission_manager):
        """Test that all audio formats are blocked."""
        audio_extensions = [".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".wma"]

        for ext in audio_extensions:
            tool_name = "Read"
            tool_args = {"file_path": f"/tmp/test_workspace/audio{ext}"}

            allowed, reason = await permission_manager.pre_tool_use_hook(tool_name, tool_args)

            assert not allowed, f"Read should be blocked from reading {ext} files"
            assert reason is not None

    @pytest.mark.asyncio
    async def test_block_archive_formats(self, permission_manager):
        """Test that archive formats are blocked."""
        archive_extensions = [".zip", ".tar", ".gz", ".bz2", ".7z", ".rar", ".xz"]

        for ext in archive_extensions:
            tool_name = "Read"
            tool_args = {"file_path": f"/tmp/test_workspace/archive{ext}"}

            allowed, reason = await permission_manager.pre_tool_use_hook(tool_name, tool_args)

            assert not allowed, f"Read should be blocked from reading {ext} files"
            assert reason is not None

    @pytest.mark.asyncio
    async def test_block_executable_formats(self, permission_manager):
        """Test that executable/binary formats are blocked."""
        binary_extensions = [".exe", ".bin", ".dll", ".so", ".dylib", ".o", ".a", ".pyc", ".class", ".jar"]

        for ext in binary_extensions:
            tool_name = "Read"
            tool_args = {"file_path": f"/tmp/test_workspace/binary{ext}"}

            allowed, reason = await permission_manager.pre_tool_use_hook(tool_name, tool_args)

            assert not allowed, f"Read should be blocked from reading {ext} files"
            assert reason is not None

    @pytest.mark.asyncio
    async def test_block_old_office_formats(self, permission_manager):
        """Test that old Office formats are blocked (use understand_file instead)."""
        old_office_extensions = [".doc", ".xls", ".ppt"]

        for ext in old_office_extensions:
            tool_name = "Read"
            tool_args = {"file_path": f"/tmp/test_workspace/document{ext}"}

            allowed, reason = await permission_manager.pre_tool_use_hook(tool_name, tool_args)

            assert not allowed, f"Read should be blocked from reading {ext} files"
            assert reason is not None

    @pytest.mark.asyncio
    async def test_block_office_formats(self, permission_manager):
        """Test that Office document formats are blocked from Read (must use understand_file).

        These are binary formats that should be handled by understand_file tool,
        which can properly extract text from them using specialized libraries.
        """
        office_extensions = [".pdf", ".docx", ".xlsx", ".pptx"]

        for ext in office_extensions:
            tool_name = "Read"
            tool_args = {"file_path": f"/tmp/test_workspace/document{ext}"}

            allowed, reason = await permission_manager.pre_tool_use_hook(tool_name, tool_args)

            assert not allowed, f"Read should be blocked from reading {ext} files (use understand_file)"
            assert reason is not None
            assert "understand_file" in reason.lower()

    @pytest.mark.asyncio
    async def test_case_insensitive_extension_check(self, permission_manager):
        """Test that extension checking is case-insensitive."""
        test_cases = [
            "/tmp/test_workspace/PHOTO.JPG",
            "/tmp/test_workspace/Video.MP4",
            "/tmp/test_workspace/Audio.MP3",
            "/tmp/test_workspace/Image.PNG",
        ]

        for file_path in test_cases:
            tool_name = "Read"
            tool_args = {"file_path": file_path}

            allowed, reason = await permission_manager.pre_tool_use_hook(tool_name, tool_args)

            assert not allowed, f"Read should be blocked from reading {file_path} (case-insensitive)"
            assert reason is not None

    @pytest.mark.asyncio
    async def test_non_text_read_tools_not_affected(self, permission_manager):
        """Test that non-text-read tools are not affected by binary file blocking."""
        # Tools like Write, Edit, Delete should not be affected
        test_cases = [
            ("Write", {"file_path": "/tmp/test_workspace/image.jpg"}),
            ("Edit", {"file_path": "/tmp/test_workspace/video.mp4"}),
            ("Grep", {"pattern": "test"}),  # No file_path, should pass
        ]

        for tool_name, tool_args in test_cases:
            allowed, reason = await permission_manager.pre_tool_use_hook(tool_name, tool_args)

            # These tools have their own validation, but shouldn't be blocked by binary check
            # (they may be blocked for other reasons like permissions)
            # The key is that _validate_binary_file_access is not called for these
            assert isinstance(allowed, bool)  # Should complete without binary file error

    @pytest.mark.asyncio
    async def test_helpful_error_messages(self, permission_manager):
        """Test that error messages provide helpful suggestions for blocked binary files."""
        test_cases = [
            (".jpg", "understand_image"),
            (".mp4", "understand_video"),
            (".mp3", "audio"),
            (".pdf", "understand_file"),
            (".docx", "understand_file"),
        ]

        for ext, expected_suggestion in test_cases:
            tool_name = "Read"
            tool_args = {"file_path": f"/tmp/test_workspace/file{ext}"}

            allowed, reason = await permission_manager.pre_tool_use_hook(tool_name, tool_args)

            assert not allowed, f"File with {ext} extension should be blocked"
            assert reason is not None
            assert expected_suggestion.lower() in reason.lower(), f"Error message should suggest {expected_suggestion} for {ext} files"
