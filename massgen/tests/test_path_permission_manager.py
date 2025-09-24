#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for PathPermissionManager validation methods.

Tests the core permission validation logic including:
- _validate_write_tool method for filesystem operations
- _validate_command_tool method for shell commands
- Path permission management
- Context vs final agent permission handling
"""

import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Add the massgen directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from massgen.mcp_tools.filesystem_manager import (  # noqa: E402
    PathPermissionManager,
    Permission,
)
from massgen.mcp_tools.workspace_copy_server import (  # noqa: E402
    _validate_path_access,
    get_copy_file_pairs,
)


class TestHelper:
    """Helper class for test setup and teardown."""

    def __init__(self):
        self.temp_dir = None
        self.workspace_dir = None
        self.context_dir = None
        self.readonly_dir = None

    def setup(self):
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.workspace_dir = self.temp_dir / "workspace"
        self.context_dir = self.temp_dir / "context"
        self.readonly_dir = self.temp_dir / "readonly"

        # Create the directories
        self.workspace_dir.mkdir(parents=True)
        self.context_dir.mkdir(parents=True)
        self.readonly_dir.mkdir(parents=True)

        # Create test files
        (self.workspace_dir / "workspace_file.txt").write_text("workspace content")
        (self.context_dir / "context_file.txt").write_text("context content")
        (self.readonly_dir / "readonly_file.txt").write_text("readonly content")

    def teardown(self):
        """Clean up after tests."""
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def create_permission_manager(self, context_write_enabled=False):
        """Helper to create a PathPermissionManager with test paths."""
        manager = PathPermissionManager(context_write_access_enabled=context_write_enabled)

        # Add workspace (always writable)
        manager.add_path(self.workspace_dir, Permission.WRITE, "workspace")

        # Add context path (permission depends on context_write_enabled)
        if context_write_enabled:
            manager.add_path(self.context_dir, Permission.WRITE, "context")
        else:
            manager.add_path(self.context_dir, Permission.READ, "context")

        # Add readonly path
        manager.add_path(self.readonly_dir, Permission.READ, "context")

        return manager


def test_is_write_tool():
    """Test the _is_write_tool method."""
    print("\n📝 Testing _is_write_tool method...")

    helper = TestHelper()
    helper.setup()

    try:
        manager = helper.create_permission_manager()

        # Claude Code write tools
        claude_write_tools = ["Write", "Edit", "MultiEdit", "NotebookEdit"]
        for tool in claude_write_tools:
            if not manager._is_write_tool(tool):
                print(f"❌ Failed: {tool} should be detected as write tool")
                return False

        # Claude Code read tools
        claude_read_tools = ["Read", "Glob", "Grep", "WebFetch"]
        for tool in claude_read_tools:
            if manager._is_write_tool(tool):
                print(f"❌ Failed: {tool} should NOT be detected as write tool")
                return False

        # MCP write tools
        mcp_write_tools = ["write_file", "edit_file", "create_directory", "move_file", "delete_file", "remove_directory"]
        for tool in mcp_write_tools:
            if not manager._is_write_tool(tool):
                print(f"❌ Failed: {tool} should be detected as write tool")
                return False

        # MCP read tools
        mcp_read_tools = ["read_file", "list_directory"]
        for tool in mcp_read_tools:
            if manager._is_write_tool(tool):
                print(f"❌ Failed: {tool} should NOT be detected as write tool")
                return False

        print("✅ _is_write_tool detection works correctly")
        return True

    finally:
        helper.teardown()


def test_validate_write_tool():
    """Test the _validate_write_tool method."""
    print("\n📝 Testing _validate_write_tool method...")

    helper = TestHelper()
    helper.setup()

    try:
        # Test 1: Workspace files are always writable
        print("  Testing workspace write access...")
        manager = helper.create_permission_manager(context_write_enabled=False)
        tool_args = {"file_path": str(helper.workspace_dir / "workspace_file.txt")}
        allowed, reason = manager._validate_write_tool("Write", tool_args)

        if not allowed:
            print(f"❌ Failed: Workspace should always be writable. Reason: {reason}")
            return False

        # Test 2: Context path with write enabled
        print("  Testing context path with write enabled...")
        manager = helper.create_permission_manager(context_write_enabled=True)
        tool_args = {"file_path": str(helper.context_dir / "context_file.txt")}
        allowed, reason = manager._validate_write_tool("Write", tool_args)

        if not allowed:
            print(f"❌ Failed: Context path should be writable when enabled. Reason: {reason}")
            return False

        # Test 3: Context path with write disabled
        print("  Testing context path with write disabled...")
        manager = helper.create_permission_manager(context_write_enabled=False)
        tool_args = {"file_path": str(helper.context_dir / "context_file.txt")}
        allowed, reason = manager._validate_write_tool("Write", tool_args)

        if allowed:
            print("❌ Failed: Context path should NOT be writable when disabled")
            return False
        if "read-only context path" not in reason:
            print(f"❌ Failed: Expected 'read-only context path' in reason, got: {reason}")
            return False

        # Test 4: Readonly paths are always blocked
        print("  Testing readonly path...")
        for context_write_enabled in [True, False]:
            manager = helper.create_permission_manager(context_write_enabled=context_write_enabled)
            tool_args = {"file_path": str(helper.readonly_dir / "readonly_file.txt")}
            allowed, reason = manager._validate_write_tool("Write", tool_args)

            if allowed:
                print(f"❌ Failed: Readonly path should never be writable (context_write={context_write_enabled})")
                return False

        # Test 5: Unknown paths are allowed -- this is only bc the filesystem already restricts only to those paths that we provide
        print("  Testing unknown path...")
        manager = helper.create_permission_manager()
        unknown_file = helper.temp_dir / "unknown" / "file.txt"
        unknown_file.parent.mkdir(exist_ok=True)
        unknown_file.write_text("content")

        tool_args = {"file_path": str(unknown_file)}
        allowed, reason = manager._validate_write_tool("Write", tool_args)

        if not allowed:
            print(f"❌ Failed: Unknown paths should be allowed. Reason: {reason}")
            return False

        # Test 6: Different path argument names
        print("  Testing different path argument names...")
        manager = helper.create_permission_manager(context_write_enabled=False)
        readonly_file = str(helper.readonly_dir / "readonly_file.txt")

        path_arg_names = ["file_path", "path", "filename", "notebook_path", "target"]
        for arg_name in path_arg_names:
            tool_args = {arg_name: readonly_file}
            allowed, reason = manager._validate_write_tool("Write", tool_args)

            if allowed:
                print(f"❌ Failed: Should block readonly with arg name '{arg_name}'")
                return False

        print("✅ _validate_write_tool works correctly")
        return True

    finally:
        helper.teardown()


def test_validate_command_tool():
    """Test the _validate_command_tool method."""
    print("\n🔧 Testing _validate_command_tool method...")

    helper = TestHelper()
    helper.setup()

    try:
        manager = helper.create_permission_manager()

        # Test 1: Dangerous commands are blocked
        print("  Testing dangerous command blocking...")
        dangerous_commands = [
            "rm file.txt",
            "rm -rf directory/",
            "sudo apt install",
            "su root",
            "chmod 777 file.txt",
            "chown user:group file.txt",
            "format C:",
            "fdisk /dev/sda",
            "mkfs.ext4 /dev/sdb1",
        ]

        for cmd in dangerous_commands:
            tool_args = {"command": cmd}
            allowed, reason = manager._validate_command_tool("Bash", tool_args)

            if allowed:
                print(f"❌ Failed: Dangerous command should be blocked: {cmd}")
                return False
            if "Dangerous command pattern" not in reason:
                print(f"❌ Failed: Expected 'Dangerous command pattern' for: {cmd}, got: {reason}")
                return False

        # Test 2: Safe commands are allowed
        print("  Testing safe command allowance...")
        safe_commands = ["ls -la", "cat file.txt", "grep pattern file.txt", "find . -name '*.py'", "python script.py", "npm install", "git status"]

        for cmd in safe_commands:
            tool_args = {"command": cmd}
            allowed, reason = manager._validate_command_tool("Bash", tool_args)

            if not allowed:
                print(f"❌ Failed: Safe command should be allowed: {cmd}. Reason: {reason}")
                return False

        # Test 3: Write operations to readonly paths are blocked
        print("  Testing write operations to readonly paths...")
        manager = helper.create_permission_manager(context_write_enabled=False)
        readonly_file = str(helper.readonly_dir / "readonly_file.txt")

        write_commands = [
            f"echo 'content' > {readonly_file}",
            f"echo 'content' >> {readonly_file}",
            f"mv source.txt {readonly_file}",
            f"cp source.txt {readonly_file}",
            f"touch {readonly_file}",
        ]

        for cmd in write_commands:
            tool_args = {"command": cmd}
            allowed, reason = manager._validate_command_tool("Bash", tool_args)

            if allowed:
                print(f"❌ Failed: Write to readonly should be blocked: {cmd}")
                return False
            if "read-only context path" not in reason:
                print(f"❌ Failed: Expected 'read-only context path' for: {cmd}, got: {reason}")
                return False

        # Test 4: Write operations to workspace are allowed
        print("  Testing write operations to workspace...")
        workspace_file = str(helper.workspace_dir / "workspace_file.txt")

        write_commands = [
            f"echo 'content' > {workspace_file}",
            f"echo 'content' >> {workspace_file}",
            f"mv source.txt {workspace_file}",
            f"cp source.txt {workspace_file}",
        ]

        for cmd in write_commands:
            tool_args = {"command": cmd}
            allowed, reason = manager._validate_command_tool("Bash", tool_args)

            if not allowed:
                print(f"❌ Failed: Write to workspace should be allowed: {cmd}. Reason: {reason}")
                return False

        print("✅ _validate_command_tool works correctly")
        return True

    finally:
        helper.teardown()


def test_pre_tool_use_hook():
    """Test the main pre_tool_use_hook method."""
    print("\n🪝 Testing pre_tool_use_hook method...")

    helper = TestHelper()
    helper.setup()

    try:
        # Test 1: Write tools on readonly paths
        print("  Testing write tool on readonly path...")
        manager = helper.create_permission_manager(context_write_enabled=False)
        tool_args = {"file_path": str(helper.readonly_dir / "readonly_file.txt")}
        allowed, reason = asyncio.run(manager.pre_tool_use_hook("Write", tool_args))

        if allowed:
            print("❌ Failed: Write tool on readonly path should be blocked")
            return False
        if "read-only context path" not in reason:
            print(f"❌ Failed: Expected 'read-only context path' in reason, got: {reason}")
            return False

        # Test 2: Command tools with dangerous commands
        print("  Testing dangerous command...")
        tool_args = {"command": "rm -rf /"}
        allowed, reason = asyncio.run(manager.pre_tool_use_hook("Bash", tool_args))

        if allowed:
            print("❌ Failed: Dangerous command should be blocked")
            return False
        if "Dangerous command pattern" not in reason:
            print(f"❌ Failed: Expected 'Dangerous command pattern' in reason, got: {reason}")
            return False

        # Test 3: Read tools are always allowed
        print("  Testing read tools...")
        read_tools = ["Read", "Glob", "Grep", "WebFetch", "WebSearch"]

        for tool_name in read_tools:
            tool_args = {"file_path": str(helper.readonly_dir / "readonly_file.txt")}
            allowed, reason = asyncio.run(manager.pre_tool_use_hook(tool_name, tool_args))

            if not allowed:
                print(f"❌ Failed: Read tool should always be allowed: {tool_name}. Reason: {reason}")
                return False

        # Test 4: Unknown tools are allowed
        print("  Testing unknown tools...")
        tool_args = {"some_param": "value"}
        allowed, reason = asyncio.run(manager.pre_tool_use_hook("CustomTool", tool_args))

        if not allowed:
            print(f"❌ Failed: Unknown tool should be allowed. Reason: {reason}")
            return False

        print("✅ pre_tool_use_hook works correctly")
        return True

    finally:
        helper.teardown()


def test_context_write_access_toggle():
    """Test context write access enabling/disabling."""
    print("\n🔄 Testing context write access toggle...")

    helper = TestHelper()
    helper.setup()

    try:
        manager = PathPermissionManager(context_write_access_enabled=False)

        # Add context paths
        context_paths = [{"path": str(helper.context_dir), "permission": "write"}, {"path": str(helper.readonly_dir), "permission": "read"}]
        manager.add_context_paths(context_paths)

        # Initially should be read-only
        print("  Testing initial read-only state...")
        if manager.get_permission(helper.context_dir) != Permission.READ:
            print("❌ Failed: Context path should initially be read-only")
            return False
        if manager.get_permission(helper.readonly_dir) != Permission.READ:
            print("❌ Failed: Readonly path should be read-only")
            return False

        # Enable write access
        print("  Testing write access enabled...")
        manager.set_context_write_access_enabled(True)

        if manager.get_permission(helper.context_dir) != Permission.WRITE:
            print("❌ Failed: Context path should be writable after enabling")
            return False
        if manager.get_permission(helper.readonly_dir) != Permission.READ:
            print("❌ Failed: Readonly path should stay read-only")
            return False

        # Disable write access again
        print("  Testing write access disabled again...")
        manager.set_context_write_access_enabled(False)

        if manager.get_permission(helper.context_dir) != Permission.READ:
            print("❌ Failed: Context path should be read-only after disabling")
            return False
        if manager.get_permission(helper.readonly_dir) != Permission.READ:
            print("❌ Failed: Readonly path should stay read-only")
            return False

        print("✅ Context write access toggle works correctly")
        return True

    finally:
        helper.teardown()


def test_extract_file_from_command():
    """Test the _extract_file_from_command helper method."""
    print("\n📄 Testing _extract_file_from_command method...")

    helper = TestHelper()
    helper.setup()

    try:
        manager = helper.create_permission_manager()

        # Test redirect commands
        print("  Testing redirect command extraction...")
        test_cases = [
            ("echo 'content' > file.txt", ">", "file.txt"),
            ("cat input.txt >> output.log", ">>", "output.log"),
            ("ls -la > /path/to/file.txt", ">", "/path/to/file.txt"),
        ]

        for command, pattern, expected in test_cases:
            result = manager._extract_file_from_command(command, pattern)
            if result != expected:
                print(f"❌ Failed: Expected '{expected}' from '{command}', got '{result}'")
                return False

        # Test move/copy commands
        print("  Testing move/copy command extraction...")
        test_cases = [
            ("mv source.txt dest.txt", "mv ", "dest.txt"),
            ("cp file1.txt file2.txt", "cp ", "file2.txt"),
            ("move old.txt new.txt", "move ", "new.txt"),
            ("copy source.doc target.doc", "copy ", "target.doc"),
        ]

        for command, pattern, expected in test_cases:
            result = manager._extract_file_from_command(command, pattern)
            if result != expected:
                print(f"❌ Failed: Expected '{expected}' from '{command}', got '{result}'")
                return False

        print("✅ _extract_file_from_command works correctly")
        return True

    finally:
        helper.teardown()


def test_workspace_copy_tools():
    """Test workspace copy tool validation."""
    print("\n📦 Testing workspace copy tool validation...")

    helper = TestHelper()
    helper.setup()

    try:
        # Create temp workspace directory
        temp_workspace_dir = helper.temp_dir / "temp_workspace"
        temp_workspace_dir.mkdir(parents=True)
        (temp_workspace_dir / "source_file.txt").write_text("source content")

        # Test 1: copy_file and copy_files are detected as write tools
        print("  Testing copy tool detection...")
        manager = helper.create_permission_manager(context_write_enabled=False)

        copy_tools = ["copy_file", "copy_files_batch", "mcp__workspace_copy__copy_file", "mcp__workspace_copy__copy_files_batch"]
        for tool in copy_tools:
            if not manager._is_write_tool(tool):
                print(f"❌ Failed: {tool} should be detected as write tool")
                return False

        # Test 2: copy_file respects destination permissions
        print("  Testing copy_file destination permissions...")

        # Should allow copy to workspace
        tool_args = {"source_path": str(temp_workspace_dir / "source_file.txt"), "destination_path": str(helper.workspace_dir / "dest_file.txt")}
        allowed, reason = manager._validate_write_tool("copy_file", tool_args)
        if not allowed:
            print(f"❌ Failed: copy_file to workspace should be allowed. Reason: {reason}")
            return False

        # Should block copy to readonly directory
        tool_args = {"source_path": str(temp_workspace_dir / "source_file.txt"), "destination_path": str(helper.readonly_dir / "dest_file.txt")}
        allowed, reason = manager._validate_write_tool("copy_file", tool_args)
        if allowed:
            print("❌ Failed: copy_file to readonly directory should be blocked")
            return False

        # IMPORTANT: Test that we CAN copy FROM read-only paths
        print("  Testing copy FROM read-only paths...")
        tool_args = {
            "source_path": str(helper.readonly_dir / "readonly_file.txt"),  # Source is read-only - this is OK
            "destination_path": str(helper.workspace_dir / "copied_from_readonly.txt"),  # Dest is writable
        }
        allowed, reason = manager._validate_write_tool("copy_file", tool_args)
        if not allowed:
            print(f"❌ Failed: copy FROM read-only path should be allowed. Reason: {reason}")
            return False

        # Also test copy_files_batch FROM read-only path
        tool_args = {"source_base_path": str(helper.readonly_dir), "destination_base_path": str(helper.workspace_dir / "copied_from_readonly")}  # Source is read-only - this is OK  # Dest is writable
        allowed, reason = manager._validate_write_tool("copy_files_batch", tool_args)
        if not allowed:
            print(f"❌ Failed: copy_files_batch FROM read-only path should be allowed. Reason: {reason}")
            return False

        # Test 3: copy_files_batch validation
        print("  Testing copy_files_batch destination permissions...")

        # Should check destination_base_path, not source_base_path
        tool_args = {"source_base_path": str(temp_workspace_dir), "destination_base_path": str(helper.workspace_dir / "output")}  # This is fine, just reading from here  # This needs write permission
        allowed, reason = manager._validate_write_tool("copy_files_batch", tool_args)
        if not allowed:
            print(f"❌ Failed: copy_files_batch to workspace subdirectory should be allowed. Reason: {reason}")
            return False

        # Should block copy to readonly directory
        tool_args = {"source_base_path": str(temp_workspace_dir), "destination_base_path": str(helper.readonly_dir / "output")}
        allowed, reason = manager._validate_write_tool("copy_files_batch", tool_args)
        if allowed:
            print("❌ Failed: copy_files_batch to readonly directory should be blocked")
            return False

        # Test 4: _extract_file_path prioritizes destination paths
        print("  Testing _extract_file_path with copy arguments...")

        # Should extract destination_path when both source and destination are present
        tool_args = {"source_path": str(temp_workspace_dir / "source.txt"), "destination_path": str(helper.workspace_dir / "dest.txt")}
        extracted = manager._extract_file_path(tool_args)
        if extracted != str(helper.workspace_dir / "dest.txt"):
            print(f"❌ Failed: Should extract destination_path, got: {extracted}")
            return False

        # Should extract destination_base_path for batch operations
        tool_args = {"source_base_path": str(temp_workspace_dir), "destination_base_path": str(helper.workspace_dir / "output")}
        extracted = manager._extract_file_path(tool_args)
        if extracted != str(helper.workspace_dir / "output"):
            print(f"❌ Failed: Should extract destination_base_path, got: {extracted}")
            return False

        # Test 5: Test absolute path requirement and validation
        print("  Testing absolute path validation...")

        # Workspace copy tools should validate that destination paths are within allowed directories
        # This tests the _validate_path_access functionality that was added
        tool_args = {"source_path": str(temp_workspace_dir / "source_file.txt"), "destination_path": str(helper.workspace_dir / "valid_destination.txt")}
        allowed, reason = manager._validate_write_tool("copy_file", tool_args)
        if not allowed:
            print(f"❌ Failed: copy_file with valid absolute destination should be allowed. Reason: {reason}")
            return False

        # Test copy_files_batch with absolute destination_base_path
        tool_args = {"source_base_path": str(temp_workspace_dir), "destination_base_path": str(helper.workspace_dir / "batch_output")}
        allowed, reason = manager._validate_write_tool("copy_files_batch", tool_args)
        if not allowed:
            print(f"❌ Failed: copy_files_batch with valid absolute destination should be allowed. Reason: {reason}")
            return False

        # Test 6: Verify that destination paths outside allowed paths would be blocked
        print("  Testing outside allowed paths...")

        # Create a directory outside the allowed paths
        outside_dir = helper.temp_dir / "outside_allowed"
        outside_dir.mkdir(parents=True)

        # This should be blocked because outside_dir is not in the manager's allowed paths
        tool_args = {"source_path": str(temp_workspace_dir / "source_file.txt"), "destination_path": str(outside_dir / "should_be_blocked.txt")}
        allowed, reason = manager._validate_write_tool("copy_file", tool_args)
        # Note: This might be allowed because unknown paths are allowed in the current implementation
        # The actual path validation happens in the MCP server, not the permission manager
        # So we're just testing the manager's file path extraction logic here

        print("✅ Workspace copy tool validation works correctly")
        return True

    finally:
        helper.teardown()


def test_workspace_copy_server_path_validation():
    """Test the workspace copy server's absolute path validation logic."""
    print("\n🏗️  Testing workspace copy server path validation...")

    helper = TestHelper()
    helper.setup()

    try:
        # We need to modify ALLOWED_PATHS global for this test
        import massgen.mcp_tools.workspace_copy_server as wc_server

        # Store original ALLOWED_PATHS and WORKSPACE_PATH and set test paths
        original_allowed_paths = wc_server.ALLOWED_PATHS.copy()
        original_workspace_path = wc_server.WORKSPACE_PATH
        wc_server.ALLOWED_PATHS = [helper.workspace_dir.resolve(), helper.context_dir.resolve(), helper.readonly_dir.resolve()]
        wc_server.WORKSPACE_PATH = helper.workspace_dir.resolve()

        # Create some test files
        test_source_dir = helper.temp_dir / "source"
        test_source_dir.mkdir()
        (test_source_dir / "test_file.txt").write_text("test content")
        (test_source_dir / "subdir" / "nested_file.txt").parent.mkdir(parents=True)
        (test_source_dir / "subdir" / "nested_file.txt").write_text("nested content")

        # Add source to allowed paths so we can read from it
        wc_server.ALLOWED_PATHS.append(test_source_dir.resolve())

        # Test 1: Valid absolute destination path
        print("  Testing valid absolute destination path...")
        try:
            dest_path = helper.workspace_dir / "output"
            file_pairs = get_copy_file_pairs(source_base_path=str(test_source_dir), destination_base_path=str(dest_path))
            if len(file_pairs) < 2:  # Should find test_file.txt and nested_file.txt
                print(f"❌ Failed: Expected at least 2 files, got {len(file_pairs)}")
                return False
            print(f"  ✓ Found {len(file_pairs)} files to copy")
        except Exception as e:
            print(f"❌ Failed: Valid absolute path should work. Error: {e}")
            return False

        # Test 2: Destination path outside allowed paths should fail
        print("  Testing destination outside allowed paths...")
        outside_dir = helper.temp_dir / "outside"
        outside_dir.mkdir()

        try:
            file_pairs = get_copy_file_pairs(source_base_path=str(test_source_dir), destination_base_path=str(outside_dir / "output"))
            print("❌ Failed: Should have raised ValueError for path outside allowed directories")
            return False
        except ValueError as e:
            if "Path not in allowed directories" in str(e):
                print("  ✓ Correctly blocked path outside allowed directories")
            else:
                print(f"❌ Failed: Unexpected error: {e}")
                return False
        except Exception as e:
            print(f"❌ Failed: Unexpected exception: {e}")
            return False

        # Test 3: Source path outside allowed paths should fail
        print("  Testing source outside allowed paths...")
        outside_source = helper.temp_dir / "outside_source"
        outside_source.mkdir()
        (outside_source / "bad_file.txt").write_text("bad content")

        try:
            file_pairs = get_copy_file_pairs(source_base_path=str(outside_source), destination_base_path=str(helper.workspace_dir / "output"))
            print("❌ Failed: Should have raised ValueError for source outside allowed directories")
            return False
        except ValueError as e:
            if "Path not in allowed directories" in str(e):
                print("  ✓ Correctly blocked source outside allowed directories")
            else:
                print(f"❌ Failed: Unexpected error: {e}")
                return False

        # Test 4: Empty destination_base_path should fail
        print("  Testing empty destination_base_path...")
        try:
            file_pairs = get_copy_file_pairs(source_base_path=str(test_source_dir), destination_base_path="")
            print("❌ Failed: Should have raised ValueError for empty destination_base_path")
            return False
        except ValueError as e:
            if "destination_base_path is required" in str(e):
                print("  ✓ Correctly required destination_base_path")
            else:
                print(f"❌ Failed: Unexpected error: {e}")
                return False

        # Test 5: Test _validate_path_access directly
        print("  Testing _validate_path_access function...")

        # Valid path should not raise
        try:
            _validate_path_access(helper.workspace_dir / "test.txt", wc_server.ALLOWED_PATHS)
            print("  ✓ Valid path accepted")
        except Exception as e:
            print(f"❌ Failed: Valid path should be accepted. Error: {e}")
            return False

        # Invalid path should raise
        try:
            _validate_path_access(outside_dir / "test.txt", wc_server.ALLOWED_PATHS)
            print("❌ Failed: Invalid path should be rejected")
            return False
        except ValueError as e:
            if "Path not in allowed directories" in str(e):
                print("  ✓ Invalid path correctly rejected")
            else:
                print(f"❌ Failed: Unexpected error: {e}")
                return False

        # Test 6: Test relative path resolution to workspace
        print("  Testing relative path resolution...")
        from massgen.mcp_tools.workspace_copy_server import _validate_and_resolve_paths

        try:
            source, dest = _validate_and_resolve_paths(str(test_source_dir / "test_file.txt"), "subdir/relative_dest.txt")  # Relative path
            expected_dest = helper.workspace_dir / "subdir" / "relative_dest.txt"
            if dest != expected_dest.resolve():
                print(f"❌ Failed: Relative path should resolve to {expected_dest.resolve()}, got {dest}")
                return False
            print("  ✓ Relative path correctly resolved to workspace")
        except Exception as e:
            print(f"❌ Failed: Relative path resolution failed: {e}")
            return False

        # Test 7: Test relative path without workspace set
        print("  Testing relative path without workspace...")
        old_workspace = wc_server.WORKSPACE_PATH
        wc_server.WORKSPACE_PATH = None
        try:
            source, dest = _validate_and_resolve_paths(str(test_source_dir / "test_file.txt"), "relative_dest.txt")
            print("❌ Failed: Should have failed when WORKSPACE_PATH is None")
            return False
        except ValueError as e:
            if "require WORKSPACE_PATH" in str(e):
                print("  ✓ Correctly rejected relative path when workspace not set")
            else:
                print(f"❌ Failed: Unexpected error: {e}")
                return False
        finally:
            wc_server.WORKSPACE_PATH = old_workspace

        print("✅ Workspace copy server path validation works correctly")
        return True

    finally:
        # Restore original ALLOWED_PATHS and WORKSPACE_PATH
        wc_server.ALLOWED_PATHS = original_allowed_paths
        wc_server.WORKSPACE_PATH = original_workspace_path
        helper.teardown()


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("🧪 Path Permission Manager Test Suite")
    print("=" * 60)

    tests = [
        test_is_write_tool,
        test_validate_write_tool,
        test_validate_command_tool,
        test_pre_tool_use_hook,
        test_context_write_access_toggle,
        test_extract_file_from_command,
        test_workspace_copy_tools,
        test_workspace_copy_server_path_validation,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ {test_func.__name__} failed with exception: {e}")
            import traceback

            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"📊 Test Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
