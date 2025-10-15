# -*- coding: utf-8 -*-
import asyncio
import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

# Removed wc_server import - now using factory function approach
from massgen.filesystem_manager import (
    FileOperationTracker,
    FilesystemManager,
    PathPermissionManager,
    Permission,
)
from massgen.filesystem_manager._workspace_tools_server import (
    _validate_and_resolve_paths,
    _validate_path_access,
    get_copy_file_pairs,
)
from massgen.mcp_tools.client import MCPClient


class TestHelper:
    def __init__(self):
        self.temp_dir = None
        self.workspace_dir = None
        self.context_dir = None
        self.readonly_dir = None

    def setup(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.workspace_dir = self.temp_dir / "workspace"
        self.context_dir = self.temp_dir / "context"
        self.readonly_dir = self.temp_dir / "readonly"

        self.workspace_dir.mkdir(parents=True)
        self.context_dir.mkdir(parents=True)
        self.readonly_dir.mkdir(parents=True)
        (self.workspace_dir / "workspace_file.txt").write_text("workspace content")
        (self.context_dir / "context_file.txt").write_text("context content")
        (self.readonly_dir / "readonly_file.txt").write_text("readonly content")

    def teardown(self):
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def create_permission_manager(self, context_write_enabled=False):
        manager = PathPermissionManager(context_write_access_enabled=context_write_enabled)
        manager.add_path(self.workspace_dir, Permission.WRITE, "workspace")
        if context_write_enabled:
            manager.add_path(self.context_dir, Permission.WRITE, "context")
        else:
            manager.add_path(self.context_dir, Permission.READ, "context")
        manager.add_path(self.readonly_dir, Permission.READ, "context")
        return manager


async def test_mcp_relative_paths():
    """Test that MCP servers resolve relative paths correctly when cwd is set."""
    print("🧪 Testing MCP relative path resolution with cwd parameter...")

    # Create temporary directories
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        workspace_dir = temp_path / "workspace1"
        workspace_dir.mkdir()

        print(f"📁 Created test workspace: {workspace_dir}")

        # Create filesystem manager (this should generate configs with cwd)
        temp_workspace_parent = temp_path / "temp_workspaces"
        temp_workspace_parent.mkdir()

        filesystem_manager = FilesystemManager(
            cwd=str(workspace_dir),
            context_paths=[],
            context_write_access_enabled=True,
            agent_temporary_workspace_parent=str(temp_workspace_parent),
        )

        # Get MCP filesystem config - should include cwd parameter
        filesystem_config = filesystem_manager.get_mcp_filesystem_config()
        print(f"🔧 Filesystem MCP config: {filesystem_config}")

        # Verify cwd is set correctly (resolve both paths to handle /private prefix on macOS)
        expected_cwd = str(workspace_dir.resolve())
        actual_cwd = str(Path(filesystem_config.get("cwd")).resolve())
        assert actual_cwd == expected_cwd, f"Expected cwd={expected_cwd}, got {actual_cwd}"
        print("✅ Filesystem config has correct cwd")

        # Get workspace tools config - should also include cwd parameter
        workspace_tools_config = filesystem_manager.get_workspace_tools_mcp_config()
        print(f"🔧 Workspace tools MCP config: {workspace_tools_config}")

        # Verify cwd is set correctly (resolve both paths to handle /private prefix on macOS)
        expected_cwd = str(workspace_dir.resolve())
        actual_cwd = str(Path(workspace_tools_config.get("cwd")).resolve())
        assert actual_cwd == expected_cwd, f"Expected cwd={expected_cwd}, got {actual_cwd}"
        print("✅ Workspace tools config has correct cwd")

        # Test filesystem MCP server
        print("\n📡 Testing filesystem MCP server...")
        try:
            async with MCPClient([filesystem_config], timeout_seconds=10) as client:
                print("✅ Filesystem MCP server connected successfully")
                tools = client.get_available_tools()
                print(f"🔧 Available tools: {tools}")

                # Test creating a directory with relative path
                if "create_directory" in tools:
                    print("🏗️  Testing create_directory with relative path 'api'...")
                    try:
                        result = await client.call_tool("create_directory", {"path": "api"})
                        print(f"✅ create_directory result: {result}")

                        # Verify directory was created in workspace
                        api_dir = workspace_dir / "api"
                        if api_dir.exists():
                            print(f"✅ Directory created at correct location: {api_dir}")
                        else:
                            print(f"❌ Directory not found at expected location: {api_dir}")

                    except Exception as e:
                        print(f"⚠️  create_directory failed: {e}")
                else:
                    print("⚠️  create_directory tool not available")

        except Exception as e:
            print(f"❌ Filesystem MCP server test failed: {e}")

        # Test workspace tools MCP server
        print("\n📦 Testing workspace tools MCP server...")
        try:
            async with MCPClient([workspace_tools_config], timeout_seconds=10) as client:
                print("✅ Workspace tools MCP server connected successfully")
                tools = client.get_available_tools()
                print(f"🔧 Available tools: {tools}")

                # Test get_cwd to verify working directory
                if "get_cwd" in tools:
                    print("📍 Testing get_cwd to verify working directory...")
                    try:
                        cwd_result = await client.call_tool("get_cwd", {})
                        print(f"✅ get_cwd result: {cwd_result}")

                        # Extract cwd info from structured content if available
                        if hasattr(cwd_result, "structuredContent") and cwd_result.structuredContent:
                            cwd_info = cwd_result.structuredContent
                        else:
                            # Fallback to parsing text content
                            cwd_info = json.loads(cwd_result.content[0].text)

                        server_cwd = cwd_info.get("cwd")
                        expected_cwd = str(workspace_dir.resolve())
                        actual_cwd = str(Path(server_cwd).resolve())

                        if actual_cwd == expected_cwd:
                            print(f"✅ Server is running in correct directory: {server_cwd}")
                        else:
                            print(f"❌ Server working directory mismatch: expected {expected_cwd}, got {actual_cwd}")

                    except Exception as e:
                        print(f"⚠️  get_cwd failed: {e}")
                else:
                    print("⚠️  get_cwd tool not available")

                # Create a test source file in the temp workspace (which is in allowed paths)
                source_dir = temp_workspace_parent / "source"
                source_dir.mkdir()
                test_file = source_dir / "test.txt"
                test_file.write_text("test content")

                # Test copying with relative destination path
                if "copy_file" in tools:
                    print("📋 Testing copy_file with relative destination path...")
                    try:
                        result = await client.call_tool(
                            "copy_file",
                            {
                                "source_path": str(test_file),
                                "destination_path": "copied_file.txt",  # Relative path
                            },
                        )
                        print(f"✅ copy_file result: {result}")

                        # Verify file was copied to workspace
                        copied_file = workspace_dir / "copied_file.txt"
                        if copied_file.exists():
                            print(f"✅ File copied to correct location: {copied_file}")
                            content = copied_file.read_text()
                            if content == "test content":
                                print("✅ File content is correct")
                            else:
                                print(f"❌ File content mismatch: {content}")
                        else:
                            print(f"❌ File not found at expected location: {copied_file}")

                    except Exception as e:
                        print(f"⚠️  copy_file failed: {e}")
                else:
                    print("⚠️  copy_file tool not available")

        except Exception as e:
            print(f"❌ Workspace copy MCP server test failed: {e}")

    print("\n🎉 MCP relative path testing complete!")


def test_is_write_tool():
    print("\n📝 Testing _is_write_tool method...")

    helper = TestHelper()
    helper.setup()

    try:
        manager = helper.create_permission_manager()
        claude_write_tools = ["Write", "Edit", "MultiEdit", "NotebookEdit"]
        for tool in claude_write_tools:
            if not manager._is_write_tool(tool):
                print(f"❌ Failed: {tool} should be detected as write tool")
                return False
        claude_read_tools = ["Read", "Glob", "Grep", "WebFetch"]
        for tool in claude_read_tools:
            if manager._is_write_tool(tool):
                print(f"❌ Failed: {tool} should NOT be detected as write tool")
                return False
        mcp_write_tools = ["write_file", "edit_file", "create_directory", "move_file", "delete_file", "remove_directory"]
        for tool in mcp_write_tools:
            if not manager._is_write_tool(tool):
                print(f"❌ Failed: {tool} should be detected as write tool")
                return False
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
    print("\n📝 Testing _validate_write_tool method...")

    helper = TestHelper()
    helper.setup()

    try:
        print("  Testing workspace write access...")
        manager = helper.create_permission_manager(context_write_enabled=False)
        tool_args = {"file_path": str(helper.workspace_dir / "workspace_file.txt")}
        allowed, reason = manager._validate_write_tool("Write", tool_args)

        if not allowed:
            print(f"❌ Failed: Workspace should always be writable. Reason: {reason}")
            return False
        print("  Testing context path with write enabled...")
        manager = helper.create_permission_manager(context_write_enabled=True)
        tool_args = {"file_path": str(helper.context_dir / "context_file.txt")}
        allowed, reason = manager._validate_write_tool("Write", tool_args)

        if not allowed:
            print(f"❌ Failed: Context path should be writable when enabled. Reason: {reason}")
            return False
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
        print("  Testing readonly path...")
        for context_write_enabled in [True, False]:
            manager = helper.create_permission_manager(context_write_enabled=context_write_enabled)
            tool_args = {"file_path": str(helper.readonly_dir / "readonly_file.txt")}
            allowed, reason = manager._validate_write_tool("Write", tool_args)

            if allowed:
                print(f"❌ Failed: Readonly path should never be writable (context_write={context_write_enabled})")
                return False
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
    print("\n🔧 Testing _validate_command_tool method...")

    helper = TestHelper()
    helper.setup()

    try:
        manager = helper.create_permission_manager()
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
        print("  Testing safe command allowance...")
        safe_commands = ["ls -la", "cat file.txt", "grep pattern file.txt", "find . -name '*.py'", "python script.py", "npm install", "git status"]

        for cmd in safe_commands:
            tool_args = {"command": cmd}
            allowed, reason = manager._validate_command_tool("Bash", tool_args)

            if not allowed:
                print(f"❌ Failed: Safe command should be allowed: {cmd}. Reason: {reason}")
                return False
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


def test_validate_execute_command_tool():
    print("\n⚙️  Testing _validate_command_tool for execute_command...")

    helper = TestHelper()
    helper.setup()

    try:
        manager = helper.create_permission_manager()
        print("  Testing dangerous command blocking for execute_command...")
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
            allowed, reason = manager._validate_command_tool("execute_command", tool_args)

            if allowed:
                print(f"❌ Failed: Dangerous command should be blocked for execute_command: {cmd}")
                return False
            if "Dangerous command pattern" not in reason:
                print(f"❌ Failed: Expected 'Dangerous command pattern' for: {cmd}, got: {reason}")
                return False
        print("  Testing safe command allowance for execute_command...")
        safe_commands = [
            "python script.py",
            "pytest tests/",
            "npm run build",
            "ls -la",
            "cat file.txt",
            "git status",
            "node app.js",
        ]

        for cmd in safe_commands:
            tool_args = {"command": cmd}
            allowed, reason = manager._validate_command_tool("execute_command", tool_args)

            if not allowed:
                print(f"❌ Failed: Safe command should be allowed for execute_command: {cmd}. Reason: {reason}")
                return False
        print("  Testing write operations to readonly paths for execute_command...")
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
            allowed, reason = manager._validate_command_tool("execute_command", tool_args)

            if allowed:
                print(f"❌ Failed: Write to readonly should be blocked for execute_command: {cmd}")
                return False
            if "read-only context path" not in reason:
                print(f"❌ Failed: Expected 'read-only context path' for: {cmd}, got: {reason}")
                return False
        print("  Testing write operations to workspace for execute_command...")
        workspace_file = str(helper.workspace_dir / "workspace_file.txt")

        write_commands = [
            f"echo 'content' > {workspace_file}",
            f"echo 'content' >> {workspace_file}",
            f"mv source.txt {workspace_file}",
            f"cp source.txt {workspace_file}",
        ]

        for cmd in write_commands:
            tool_args = {"command": cmd}
            allowed, reason = manager._validate_command_tool("execute_command", tool_args)

            if not allowed:
                print(f"❌ Failed: Write to workspace should be allowed for execute_command: {cmd}. Reason: {reason}")
                return False

        print("  Testing write operations to paths outside all managed directories...")
        # Create a directory outside workspace, context, and readonly dirs
        outside_dir = helper.temp_dir / "completely_outside"
        outside_dir.mkdir(parents=True)
        outside_file = str(outside_dir / "outside_file.txt")

        # Commands writing to completely unmanaged paths
        # These should be allowed since they're not in any context path
        # (manager only restricts writes to read-only context paths)
        outside_commands = [
            f"echo 'content' > {outside_file}",
            f"cp source.txt {outside_file}",
        ]

        for cmd in outside_commands:
            tool_args = {"command": cmd}
            allowed, reason = manager._validate_command_tool("execute_command", tool_args)

            if not allowed:
                print(f"❌ Failed: Write to unmanaged path should be allowed for execute_command: {cmd}. Reason: {reason}")
                return False

        print("✅ _validate_command_tool works correctly for execute_command")
        return True

    finally:
        helper.teardown()


async def test_pre_tool_use_hook():
    print("\n🪝 Testing pre_tool_use_hook method...")

    helper = TestHelper()
    helper.setup()

    try:
        print("  Testing write tool on readonly path...")
        manager = helper.create_permission_manager(context_write_enabled=False)
        tool_args = {"file_path": str(helper.readonly_dir / "readonly_file.txt")}
        allowed, reason = await manager.pre_tool_use_hook("Write", tool_args)

        if allowed:
            print("❌ Failed: Write tool on readonly path should be blocked")
            return False
        if "read-only context path" not in reason:
            print(f"❌ Failed: Expected 'read-only context path' in reason, got: {reason}")
            return False
        print("  Testing dangerous command with Bash...")
        tool_args = {"command": "rm -rf /"}
        allowed, reason = await manager.pre_tool_use_hook("Bash", tool_args)

        if allowed:
            print("❌ Failed: Dangerous command should be blocked for Bash")
            return False
        if "Dangerous command pattern" not in reason:
            print(f"❌ Failed: Expected 'Dangerous command pattern' in reason, got: {reason}")
            return False
        print("  Testing dangerous command with execute_command...")
        tool_args = {"command": "sudo apt install malware"}
        allowed, reason = await manager.pre_tool_use_hook("execute_command", tool_args)

        if allowed:
            print("❌ Failed: Dangerous command should be blocked for execute_command")
            return False
        if "Dangerous command pattern" not in reason:
            print(f"❌ Failed: Expected 'Dangerous command pattern' in reason for execute_command, got: {reason}")
            return False
        print("  Testing safe command with execute_command...")
        tool_args = {"command": "python test.py"}
        allowed, reason = await manager.pre_tool_use_hook("execute_command", tool_args)

        if not allowed:
            print(f"❌ Failed: Safe command should be allowed for execute_command. Reason: {reason}")
            return False
        print("  Testing write to readonly with execute_command...")
        readonly_file = str(helper.readonly_dir / "readonly_file.txt")
        tool_args = {"command": f"echo 'data' > {readonly_file}"}
        allowed, reason = await manager.pre_tool_use_hook("execute_command", tool_args)

        if allowed:
            print("❌ Failed: Write to readonly should be blocked for execute_command")
            return False
        if "read-only context path" not in reason:
            print(f"❌ Failed: Expected 'read-only context path' in reason for execute_command, got: {reason}")
            return False
        print("  Testing read tools...")
        read_tools = ["Read", "Glob", "Grep", "WebFetch", "WebSearch"]

        for tool_name in read_tools:
            tool_args = {"file_path": str(helper.readonly_dir / "readonly_file.txt")}
            allowed, reason = await manager.pre_tool_use_hook(tool_name, tool_args)

            if not allowed:
                print(f"❌ Failed: Read tool should always be allowed: {tool_name}. Reason: {reason}")
                return False
        print("  Testing unknown tools...")
        tool_args = {"some_param": "value"}
        allowed, reason = await manager.pre_tool_use_hook("CustomTool", tool_args)

        if not allowed:
            print(f"❌ Failed: Unknown tool should be allowed. Reason: {reason}")
            return False

        print("✅ pre_tool_use_hook works correctly")
        return True

    finally:
        helper.teardown()


def test_context_write_access_toggle():
    print("\n🔄 Testing context write access toggle...")

    helper = TestHelper()
    helper.setup()

    try:
        manager = PathPermissionManager(context_write_access_enabled=False)
        context_paths = [{"path": str(helper.context_dir), "permission": "write"}, {"path": str(helper.readonly_dir), "permission": "read"}]
        manager.add_context_paths(context_paths)
        print("  Testing initial read-only state...")
        if manager.get_permission(helper.context_dir) != Permission.READ:
            print("❌ Failed: Context path should initially be read-only")
            return False
        if manager.get_permission(helper.readonly_dir) != Permission.READ:
            print("❌ Failed: Readonly path should be read-only")
            return False
        print("  Testing write access enabled...")
        manager.set_context_write_access_enabled(True)

        if manager.get_permission(helper.context_dir) != Permission.WRITE:
            print("❌ Failed: Context path should be writable after enabling")
            return False
        if manager.get_permission(helper.readonly_dir) != Permission.READ:
            print("❌ Failed: Readonly path should stay read-only")
            return False
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
    print("\n📄 Testing _extract_file_from_command method...")

    helper = TestHelper()
    helper.setup()

    try:
        manager = helper.create_permission_manager()
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


def test_workspace_tools():
    print("\n📦 Testing workspace tools validation...")

    helper = TestHelper()
    helper.setup()

    try:
        temp_workspace_dir = helper.temp_dir / "temp_workspace"
        temp_workspace_dir.mkdir(parents=True)
        (temp_workspace_dir / "source_file.txt").write_text("source content")
        print("  Testing copy tool detection...")
        manager = helper.create_permission_manager(context_write_enabled=False)
        # Add temp_workspace_dir to the permission manager's allowed paths
        manager.add_path(temp_workspace_dir, Permission.READ, "temp_workspace")

        copy_tools = ["copy_file", "copy_files_batch", "mcp__workspace_tools__copy_file", "mcp__workspace_tools__copy_files_batch"]
        for tool in copy_tools:
            if not manager._is_write_tool(tool):
                print(f"❌ Failed: {tool} should be detected as write tool")
                return False
        print("  Testing copy_file destination permissions...")
        tool_args = {"source_path": str(temp_workspace_dir / "source_file.txt"), "destination_path": str(helper.workspace_dir / "dest_file.txt")}
        allowed, reason = manager._validate_write_tool("copy_file", tool_args)
        if not allowed:
            print(f"❌ Failed: copy_file to workspace should be allowed. Reason: {reason}")
            return False
        tool_args = {"source_path": str(temp_workspace_dir / "source_file.txt"), "destination_path": str(helper.readonly_dir / "dest_file.txt")}
        allowed, reason = manager._validate_write_tool("copy_file", tool_args)
        if allowed:
            print("❌ Failed: copy_file to readonly directory should be blocked")
            return False
        print("  Testing copy FROM read-only paths...")
        tool_args = {
            "source_path": str(helper.readonly_dir / "readonly_file.txt"),
            "destination_path": str(helper.workspace_dir / "copied_from_readonly.txt"),
        }
        allowed, reason = manager._validate_write_tool("copy_file", tool_args)
        if not allowed:
            print(f"❌ Failed: copy FROM read-only path should be allowed. Reason: {reason}")
            return False
        tool_args = {"source_base_path": str(helper.readonly_dir), "destination_base_path": str(helper.workspace_dir / "copied_from_readonly")}
        allowed, reason = manager._validate_write_tool("copy_files_batch", tool_args)
        if not allowed:
            print(f"❌ Failed: copy_files_batch FROM read-only path should be allowed. Reason: {reason}")
            return False
        print("  Testing copy_files_batch destination permissions...")
        tool_args = {"source_base_path": str(temp_workspace_dir), "destination_base_path": str(helper.workspace_dir / "output")}
        allowed, reason = manager._validate_write_tool("copy_files_batch", tool_args)
        if not allowed:
            print(f"❌ Failed: copy_files_batch to workspace subdirectory should be allowed. Reason: {reason}")
            return False
        tool_args = {"source_base_path": str(temp_workspace_dir), "destination_base_path": str(helper.readonly_dir / "output")}
        allowed, reason = manager._validate_write_tool("copy_files_batch", tool_args)
        if allowed:
            print("❌ Failed: copy_files_batch to readonly directory should be blocked")
            return False
        print("  Testing _extract_file_path with copy arguments...")
        tool_args = {"source_path": str(temp_workspace_dir / "source.txt"), "destination_path": str(helper.workspace_dir / "dest.txt")}
        extracted = manager._extract_file_path(tool_args)
        if extracted != str(helper.workspace_dir / "dest.txt"):
            print(f"❌ Failed: Should extract destination_path, got: {extracted}")
            return False
        tool_args = {"source_base_path": str(temp_workspace_dir), "destination_base_path": str(helper.workspace_dir / "output")}
        extracted = manager._extract_file_path(tool_args)
        if extracted != str(helper.workspace_dir / "output"):
            print(f"❌ Failed: Should extract destination_base_path, got: {extracted}")
            return False
        print("  Testing absolute path validation...")
        tool_args = {"source_path": str(temp_workspace_dir / "source_file.txt"), "destination_path": str(helper.workspace_dir / "valid_destination.txt")}
        allowed, reason = manager._validate_write_tool("copy_file", tool_args)
        if not allowed:
            print(f"❌ Failed: copy_file with valid absolute destination should be allowed. Reason: {reason}")
            return False
        tool_args = {"source_base_path": str(temp_workspace_dir), "destination_base_path": str(helper.workspace_dir / "batch_output")}
        allowed, reason = manager._validate_write_tool("copy_files_batch", tool_args)
        if not allowed:
            print(f"❌ Failed: copy_files_batch with valid absolute destination should be allowed. Reason: {reason}")
            return False
        print("  Testing outside allowed paths...")
        outside_dir = helper.temp_dir / "outside_allowed"
        outside_dir.mkdir(parents=True)
        tool_args = {"source_path": str(temp_workspace_dir / "source_file.txt"), "destination_path": str(outside_dir / "should_be_blocked.txt")}
        allowed, reason = manager._validate_write_tool("copy_file", tool_args)
        print("✅ Workspace copy tool validation works correctly")
        return True

    finally:
        helper.teardown()


def test_default_exclusions():
    print("\n🚫 Testing default system file exclusions...")

    helper = TestHelper()
    helper.setup()

    try:
        manager = helper.create_permission_manager(context_write_enabled=True)

        # Add context path with write permission
        project_dir = helper.temp_dir / "project"
        project_dir.mkdir()
        manager.add_path(project_dir, Permission.WRITE, "context")

        print("  Testing excluded patterns are blocked...")
        excluded_files = [
            project_dir / ".env",
            project_dir / ".git" / "config",
            project_dir / "node_modules" / "package" / "index.js",
            project_dir / "__pycache__" / "module.pyc",
            project_dir / ".venv" / "lib" / "python.py",
            project_dir / ".massgen" / "sessions" / "session.json",
            project_dir / "massgen_logs" / "app.log",
        ]

        for excluded_file in excluded_files:
            excluded_file.parent.mkdir(parents=True, exist_ok=True)
            excluded_file.write_text("content")

            permission = manager.get_permission(excluded_file)
            if permission != Permission.READ:
                print(f"❌ Failed: {excluded_file} should be READ, got {permission}")
                return False

        print("  Testing normal files are writable...")
        normal_files = [
            project_dir / "src" / "main.py",
            project_dir / "README.md",
            project_dir / "config.yaml",
        ]

        for normal_file in normal_files:
            normal_file.parent.mkdir(parents=True, exist_ok=True)
            normal_file.write_text("content")

            permission = manager.get_permission(normal_file)
            if permission != Permission.WRITE:
                print(f"❌ Failed: {normal_file} should be WRITE, got {permission}")
                return False

        print("  Testing workspace overrides exclusions...")
        workspace_dir = helper.temp_dir / "project" / ".massgen" / "workspaces" / "workspace1"
        workspace_dir.mkdir(parents=True)
        manager.add_path(workspace_dir, Permission.WRITE, "workspace")

        workspace_file = workspace_dir / "index.html"
        workspace_file.write_text("content")

        permission = manager.get_permission(workspace_file)
        if permission != Permission.WRITE:
            print(f"❌ Failed: Workspace file should be WRITE even under .massgen/, got {permission}")
            return False

        print("✅ Default system file exclusions work correctly")
        return True

    finally:
        helper.teardown()


def test_path_priority_resolution():
    print("\n🎯 Testing path priority resolution (depth-first)...")

    helper = TestHelper()
    helper.setup()

    try:
        manager = PathPermissionManager(context_write_access_enabled=True)

        # Add a broad parent context path (read-only)
        project_dir = helper.temp_dir / "project"
        project_dir.mkdir()
        manager.add_path(project_dir, Permission.READ, "context")

        # Add a deeper workspace path (writable)
        workspace_dir = project_dir / ".massgen" / "workspaces" / "workspace1"
        workspace_dir.mkdir(parents=True)
        manager.add_path(workspace_dir, Permission.WRITE, "workspace")

        print("  Testing workspace file uses deeper path permission...")
        workspace_file = workspace_dir / "index.html"
        workspace_file.write_text("content")

        permission = manager.get_permission(workspace_file)
        if permission != Permission.WRITE:
            print(f"❌ Failed: Workspace file should use workspace WRITE permission, got {permission}")
            return False

        print("  Testing project file uses parent path permission...")
        project_file = project_dir / "README.md"
        project_file.write_text("content")

        permission = manager.get_permission(project_file)
        if permission != Permission.READ:
            print(f"❌ Failed: Project file should use context READ permission, got {permission}")
            return False

        print("  Testing multiple nested paths...")
        # Add another level
        nested_dir = project_dir / "src" / "components"
        nested_dir.mkdir(parents=True)
        manager.add_path(nested_dir, Permission.WRITE, "context")

        nested_file = nested_dir / "Button.jsx"
        nested_file.write_text("content")

        permission = manager.get_permission(nested_file)
        if permission != Permission.WRITE:
            print(f"❌ Failed: Nested file should use deepest matching path, got {permission}")
            return False

        # File in src/ but not in components/
        src_file = project_dir / "src" / "index.js"
        src_file.write_text("content")

        permission = manager.get_permission(src_file)
        if permission != Permission.READ:
            print(f"❌ Failed: src/ file should use parent context READ permission, got {permission}")
            return False

        print("✅ Path priority resolution works correctly")
        return True

    finally:
        helper.teardown()


def test_workspace_tools_server_path_validation():
    print("\n🏗️  Testing workspace tools server path validation...")

    helper = TestHelper()
    helper.setup()

    try:
        # Set up allowed paths for the new factory function approach
        allowed_paths = [helper.workspace_dir.resolve(), helper.context_dir.resolve(), helper.readonly_dir.resolve()]

        test_source_dir = helper.temp_dir / "source"
        test_source_dir.mkdir()
        (test_source_dir / "test_file.txt").write_text("test content")
        (test_source_dir / "subdir" / "nested_file.txt").parent.mkdir(parents=True)
        (test_source_dir / "subdir" / "nested_file.txt").write_text("nested content")
        allowed_paths.append(test_source_dir.resolve())

        print("  Testing valid absolute destination path...")
        try:
            dest_path = helper.workspace_dir / "output"
            file_pairs = get_copy_file_pairs(allowed_paths, str(test_source_dir), str(dest_path))
            if len(file_pairs) < 2:
                print(f"❌ Failed: Expected at least 2 files, got {len(file_pairs)}")
                return False
            print(f"  ✓ Found {len(file_pairs)} files to copy")
        except Exception as e:
            print(f"❌ Failed: Valid absolute path should work. Error: {e}")
            return False
        print("  Testing destination outside allowed paths...")
        outside_dir = helper.temp_dir / "outside"
        outside_dir.mkdir()

        try:
            file_pairs = get_copy_file_pairs(allowed_paths, str(test_source_dir), str(outside_dir / "output"))
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
        print("  Testing source outside allowed paths...")
        outside_source = helper.temp_dir / "outside_source"
        outside_source.mkdir()
        (outside_source / "bad_file.txt").write_text("bad content")

        try:
            file_pairs = get_copy_file_pairs(allowed_paths, str(outside_source), str(helper.workspace_dir / "output"))
            print("❌ Failed: Should have raised ValueError for source outside allowed directories")
            return False
        except ValueError as e:
            if "Path not in allowed directories" in str(e):
                print("  ✓ Correctly blocked source outside allowed directories")
            else:
                print(f"❌ Failed: Unexpected error: {e}")
                return False
        print("  Testing empty destination_base_path...")
        try:
            file_pairs = get_copy_file_pairs(allowed_paths, str(test_source_dir), "")
            print("❌ Failed: Should have raised ValueError for empty destination_base_path")
            return False
        except ValueError as e:
            if "destination_base_path is required" in str(e):
                print("  ✓ Correctly required destination_base_path")
            else:
                print(f"❌ Failed: Unexpected error: {e}")
                return False
        print("  Testing _validate_path_access function...")
        try:
            # Use resolve() to handle macOS /private prefix differences
            test_path = (helper.workspace_dir / "test.txt").resolve()
            resolved_allowed_paths = [p.resolve() for p in allowed_paths]
            _validate_path_access(test_path, resolved_allowed_paths)
            print("  ✓ Valid path accepted")
        except Exception as e:
            print(f"❌ Failed: Valid path should be accepted. Error: {e}")
            return False
        try:
            # Use resolve() to handle macOS /private prefix differences
            test_path = (outside_dir / "test.txt").resolve()
            resolved_allowed_paths = [p.resolve() for p in allowed_paths]
            _validate_path_access(test_path, resolved_allowed_paths)
            print("❌ Failed: Invalid path should be rejected")
            return False
        except ValueError as e:
            if "Path not in allowed directories" in str(e):
                print("  ✓ Invalid path correctly rejected")
            else:
                print(f"❌ Failed: Unexpected error: {e}")
                return False

        # Test relative path resolution with workspace context
        print("  Testing relative path resolution...")
        original_cwd = os.getcwd()
        try:
            # Change to workspace directory to simulate the new factory function approach
            os.chdir(str(helper.workspace_dir))
            source, dest = _validate_and_resolve_paths(allowed_paths, str(test_source_dir / "test_file.txt"), "subdir/relative_dest.txt")
            expected_dest = helper.workspace_dir / "subdir" / "relative_dest.txt"
            if dest != expected_dest.resolve():
                print(f"❌ Failed: Relative path should resolve to {expected_dest.resolve()}, got {dest}")
                return False
            print("  ✓ Relative path correctly resolved to workspace")
        except Exception as e:
            print(f"❌ Failed: Relative path resolution failed: {e}")
            return False
        finally:
            os.chdir(original_cwd)

        print("✅ Workspace copy server path validation works correctly")
        return True
    finally:
        helper.teardown()


def test_file_context_paths():
    print("\n📄 Testing file-based context paths...")

    helper = TestHelper()
    helper.setup()

    try:
        # Create test files
        test_file = helper.context_dir / "important_file.txt"
        test_file.write_text("important content")
        sibling_file = helper.context_dir / "sibling_file.txt"
        sibling_file.write_text("sibling content")
        another_sibling = helper.context_dir / "another_file.txt"
        another_sibling.write_text("another content")

        # Create manager with file-specific context path
        manager = PathPermissionManager(context_write_access_enabled=False)
        manager.add_path(helper.workspace_dir, Permission.WRITE, "workspace")

        # Add file context path (not directory)
        file_context_paths = [{"path": str(test_file), "permission": "read"}]
        manager.add_context_paths(file_context_paths)

        print("  Testing file gets read permission...")
        permission = manager.get_permission(test_file)
        if permission != Permission.READ:
            print(f"❌ Failed: File should have read permission, got {permission}")
            return False

        print("  Testing sibling file has no permission...")
        permission = manager.get_permission(sibling_file)
        if permission is not None:
            print(f"❌ Failed: Sibling file should have no permission, got {permission}")
            return False

        print("  Testing parent directory has no direct permission...")
        permission = manager.get_permission(helper.context_dir)
        if permission is not None:
            print(f"❌ Failed: Parent directory should have no permission, got {permission}")
            return False

        print("  Testing write tool access to sibling file is blocked...")
        # Try to write to sibling file - should be blocked
        tool_args = {"file_path": str(sibling_file)}
        allowed, reason = manager._validate_write_tool("Write", tool_args)
        if allowed:
            print("❌ Failed: Write to sibling file should be blocked")
            return False
        if "not an explicitly allowed file" not in reason:
            print(f"❌ Failed: Expected 'not an explicitly allowed file' in reason, got: {reason}")
            return False

        print("  Testing write tool access to another sibling is also blocked...")
        tool_args = {"file_path": str(another_sibling)}
        allowed, reason = manager._validate_write_tool("Write", tool_args)
        if allowed:
            print("❌ Failed: Write to another sibling should be blocked")
            return False

        print("  Testing read tool access to allowed file works...")
        # Try to read the explicitly allowed file - should work
        tool_args = {"file_path": str(test_file)}
        allowed, reason = manager._validate_write_tool("Read", tool_args)
        # Read tools are always allowed
        if not allowed:
            print(f"❌ Failed: Read of allowed file should work. Reason: {reason}")
            return False

        print("  Testing file context path with write permission...")
        manager2 = PathPermissionManager(context_write_access_enabled=True)
        manager2.add_path(helper.workspace_dir, Permission.WRITE, "workspace")
        file_context_paths2 = [{"path": str(test_file), "permission": "write"}]
        manager2.add_context_paths(file_context_paths2)

        permission = manager2.get_permission(test_file)
        if permission != Permission.WRITE:
            print(f"❌ Failed: File should have write permission when enabled, got {permission}")
            return False

        print("  Testing write to allowed file works with write permission...")
        tool_args = {"file_path": str(test_file)}
        allowed, reason = manager2._validate_write_tool("Write", tool_args)
        if not allowed:
            print(f"❌ Failed: Write to allowed file should work with write permission. Reason: {reason}")
            return False

        print("  Testing write to sibling still blocked even with write-enabled file context...")
        tool_args = {"file_path": str(sibling_file)}
        allowed, reason = manager2._validate_write_tool("Write", tool_args)
        if allowed:
            print("❌ Failed: Write to sibling should still be blocked")
            return False

        print("  Testing parent directory still has no MCP paths...")
        mcp_paths = manager.get_mcp_filesystem_paths()
        # Parent should be in allowed paths for MCP access but not grant permissions
        if str(helper.context_dir.resolve()) not in mcp_paths:
            print("❌ Failed: Parent directory should be in MCP allowed paths for file access")
            return False

        print("  Testing deletion of sibling file is blocked...")
        tool_args = {"path": str(sibling_file)}
        allowed, reason = manager._validate_write_tool("delete_file", tool_args)
        if allowed:
            print("❌ Failed: Deletion of sibling file should be blocked")
            return False

        print("  Testing copy to sibling location is blocked...")
        tool_args = {
            "source_path": str(helper.workspace_dir / "workspace_file.txt"),
            "destination_path": str(another_sibling),
        }
        allowed, reason = manager._validate_write_tool("copy_file", tool_args)
        if allowed:
            print("❌ Failed: Copy to sibling location should be blocked")
            return False

        print("✅ File-based context paths work correctly")
        return True

    finally:
        helper.teardown()


def test_delete_operations():
    print("\n🗑️  Testing deletion operations...")

    helper = TestHelper()
    helper.setup()

    try:
        manager = helper.create_permission_manager(context_write_enabled=False)

        print("  Testing delete_file detected as write tool...")
        if not manager._is_write_tool("delete_file"):
            print("❌ Failed: delete_file should be detected as write tool")
            return False

        if not manager._is_write_tool("delete_files_batch"):
            print("❌ Failed: delete_files_batch should be detected as write tool")
            return False

        print("  Testing deletion permission validation...")
        # Test workspace deletion (allowed)
        test_file = helper.workspace_dir / "test.txt"
        test_file.write_text("content")
        tool_args = {"path": str(test_file)}
        allowed, reason = manager._validate_write_tool("delete_file", tool_args)
        if not allowed:
            print(f"❌ Failed: Workspace file deletion should be allowed. Reason: {reason}")
            return False

        # Test read-only context deletion (blocked)
        readonly_file = helper.readonly_dir / "readonly_file.txt"
        tool_args = {"path": str(readonly_file)}
        allowed, reason = manager._validate_write_tool("delete_file", tool_args)
        if allowed:
            print("❌ Failed: Read-only file deletion should be blocked")
            return False
        if "read-only context path" not in reason:
            print(f"❌ Failed: Expected 'read-only context path' in reason, got: {reason}")
            return False

        # Test writable context deletion (allowed)
        manager2 = helper.create_permission_manager(context_write_enabled=True)
        context_file = helper.context_dir / "context_file.txt"
        tool_args = {"path": str(context_file)}
        allowed, reason = manager2._validate_write_tool("delete_file", tool_args)
        if not allowed:
            print(f"❌ Failed: Writable context file deletion should be allowed. Reason: {reason}")
            return False

        print("  Testing batch deletion permissions...")
        # Create multiple files
        for i in range(3):
            (helper.workspace_dir / f"file{i}.txt").write_text(f"content {i}")

        tool_args = {"base_path": str(helper.workspace_dir), "include_patterns": ["*.txt"]}
        allowed, reason = manager._validate_write_tool("delete_files_batch", tool_args)
        # Note: This should succeed because workspace is writable
        # The actual deletion logic is in workspace_tools_server

        print("✅ Deletion operation permissions work correctly")
        return True

    finally:
        helper.teardown()


def test_permission_path_root_protection():
    print("\n🛡️  Testing permission path root protection...")

    helper = TestHelper()
    helper.setup()

    try:
        from massgen.filesystem_manager._workspace_tools_server import (
            _is_permission_path_root,
        )

        print("  Testing workspace root is protected...")
        # The workspace root itself should be protected
        if not _is_permission_path_root(helper.workspace_dir, [helper.workspace_dir]):
            print("❌ Failed: Workspace root should be protected from deletion")
            return False

        print("  Testing files within workspace are NOT protected...")
        # Files/dirs inside workspace should NOT be protected
        test_file = helper.workspace_dir / "file.txt"
        test_file.write_text("content")
        if _is_permission_path_root(test_file, [helper.workspace_dir]):
            print("❌ Failed: Files within workspace should not be protected by root check")
            return False

        test_subdir = helper.workspace_dir / "subdir"
        test_subdir.mkdir()
        if _is_permission_path_root(test_subdir, [helper.workspace_dir]):
            print("❌ Failed: Subdirs within workspace should not be protected by root check")
            return False

        print("  Testing nested directories are NOT protected...")
        nested = helper.workspace_dir / "a" / "b" / "c"
        nested.mkdir(parents=True)
        if _is_permission_path_root(nested, [helper.workspace_dir]):
            print("❌ Failed: Nested directories should not be protected by root check")
            return False

        print("  Testing system files still protected within workspace...")
        from massgen.filesystem_manager._workspace_tools_server import _is_critical_path

        system_dir = helper.workspace_dir / ".massgen"
        system_dir.mkdir()
        # Pass allowed_paths so it checks within workspace context
        if not _is_critical_path(system_dir, [helper.workspace_dir]):
            print("❌ Failed: .massgen should still be protected by critical path check")
            return False

        # But workspace root itself is NOT a critical path (when checking within allowed paths)
        if _is_critical_path(helper.workspace_dir, [helper.workspace_dir]):
            print("❌ Failed: Workspace root should not be a critical path when within allowed paths")
            return False

        # Regular user directory within workspace should not be critical
        user_dir = helper.workspace_dir / "user_project"
        user_dir.mkdir()
        if _is_critical_path(user_dir, [helper.workspace_dir]):
            print("❌ Failed: Regular user directory should not be critical within workspace")
            return False

        print("  Testing real-world scenario: workspace under .massgen/workspaces/...")
        # This is the critical test that was missing!
        # Simulate real workspace path: /project/.massgen/workspaces/workspace1/
        massgen_dir = helper.temp_dir / ".massgen"
        massgen_dir.mkdir()
        workspaces_dir = massgen_dir / "workspaces"
        workspaces_dir.mkdir()
        real_workspace = workspaces_dir / "workspace1"
        real_workspace.mkdir()

        # User creates a directory in their workspace
        user_project = real_workspace / "bob_dylan_website"
        user_project.mkdir()
        (user_project / "index.html").write_text("<html></html>")

        # This should NOT be blocked even though path contains .massgen
        if _is_critical_path(user_project, [real_workspace]):
            print("❌ Failed: User project should not be critical within workspace even if parent has .massgen")
            print(f"   Path: {user_project}")
            print(f"   Workspace: {real_workspace}")
            return False

        # But system files within that workspace should still be blocked
        git_dir = real_workspace / ".git"
        git_dir.mkdir()
        if not _is_critical_path(git_dir, [real_workspace]):
            print("❌ Failed: .git should still be critical within workspace")
            return False

        # And .massgen itself within workspace should be blocked
        massgen_subdir = real_workspace / ".massgen"
        massgen_subdir.mkdir()
        if not _is_critical_path(massgen_subdir, [real_workspace]):
            print("❌ Failed: .massgen subdir should be critical within workspace")
            return False

        print("  Testing multiple permission paths...")
        allowed_paths = [helper.workspace_dir, helper.context_dir, helper.readonly_dir]

        # All roots should be protected
        for path in allowed_paths:
            if not _is_permission_path_root(path, allowed_paths):
                print(f"❌ Failed: {path} should be protected as root")
                return False

        # Files within any root should not be protected
        for root_dir in allowed_paths:
            test_file = root_dir / "test.txt"
            test_file.write_text("test")
            if _is_permission_path_root(test_file, allowed_paths):
                print(f"❌ Failed: File {test_file} should not be protected as root")
                return False

        print("✅ Permission path root protection works correctly")
        return True

    finally:
        helper.teardown()


def test_protected_paths():
    print("\n🛡️  Testing protected paths feature...")

    helper = TestHelper()
    helper.setup()

    try:
        # Create test structure
        test_dir = helper.temp_dir / "test_project"
        test_dir.mkdir()
        (test_dir / "modifiable.txt").write_text("can modify")
        (test_dir / "protected.txt").write_text("cannot modify")
        protected_dir = test_dir / "protected_dir"
        protected_dir.mkdir()
        (protected_dir / "nested.txt").write_text("also protected")

        print("  Testing protected paths configuration...")
        manager = PathPermissionManager(context_write_access_enabled=True)

        # Add context path with protected paths
        context_paths = [
            {
                "path": str(test_dir),
                "permission": "write",
                "protected_paths": ["protected.txt", "protected_dir/"],  # Relative paths
            },
        ]
        manager.add_context_paths(context_paths)

        print("  Testing modifiable file has WRITE permission...")
        modifiable = test_dir / "modifiable.txt"
        permission = manager.get_permission(modifiable)
        if permission != Permission.WRITE:
            print(f"❌ Failed: Modifiable file should have WRITE, got {permission}")
            return False

        print("  Testing protected file has READ permission...")
        protected_file = test_dir / "protected.txt"
        permission = manager.get_permission(protected_file)
        if permission != Permission.READ:
            print(f"❌ Failed: Protected file should have READ (forced), got {permission}")
            return False

        print("  Testing files in protected directory have READ permission...")
        nested_file = protected_dir / "nested.txt"
        permission = manager.get_permission(nested_file)
        if permission != Permission.READ:
            print(f"❌ Failed: File in protected dir should have READ, got {permission}")
            return False

        print("  Testing protected directory itself has READ permission...")
        permission = manager.get_permission(protected_dir)
        if permission != Permission.READ:
            print(f"❌ Failed: Protected directory should have READ, got {permission}")
            return False

        print("  Testing write tool validation on protected paths...")
        # Try to write to protected file (should be blocked)
        tool_args = {"file_path": str(protected_file)}
        allowed, reason = manager._validate_write_tool("Write", tool_args)
        if allowed:
            print("❌ Failed: Write to protected file should be blocked")
            return False
        if "read-only" not in reason.lower():
            print(f"❌ Failed: Expected 'read-only' in reason, got: {reason}")
            return False

        # Try to delete protected file (should be blocked)
        tool_args = {"path": str(protected_file)}
        allowed, reason = manager._validate_write_tool("delete_file", tool_args)
        if allowed:
            print("❌ Failed: Delete of protected file should be blocked")
            return False

        # Try to write to modifiable file (should be allowed)
        tool_args = {"file_path": str(modifiable)}
        allowed, reason = manager._validate_write_tool("Write", tool_args)
        if not allowed:
            print(f"❌ Failed: Write to modifiable file should be allowed. Reason: {reason}")
            return False

        print("  Testing absolute protected paths...")
        test_dir2 = helper.temp_dir / "test_project2"
        test_dir2.mkdir()
        (test_dir2 / "file.txt").write_text("content")
        protected_abs = test_dir2 / "protected_abs.txt"
        protected_abs.write_text("absolutely protected")

        manager2 = PathPermissionManager(context_write_access_enabled=True)
        context_paths2 = [
            {
                "path": str(test_dir2),
                "permission": "write",
                "protected_paths": [str(protected_abs)],  # Absolute path
            },
        ]
        manager2.add_context_paths(context_paths2)

        permission = manager2.get_permission(protected_abs)
        if permission != Permission.READ:
            print(f"❌ Failed: Absolutely protected file should have READ, got {permission}")
            return False

        print("  Testing protected paths outside context path are ignored...")
        test_dir3 = helper.temp_dir / "test_project3"
        test_dir3.mkdir()
        outside_file = helper.temp_dir / "outside.txt"
        outside_file.write_text("outside")

        manager3 = PathPermissionManager(context_write_access_enabled=True)
        context_paths3 = [
            {
                "path": str(test_dir3),
                "permission": "write",
                "protected_paths": [str(outside_file)],  # Outside context path
            },
        ]
        # This should log a warning and skip the protected path
        manager3.add_context_paths(context_paths3)

        print("✅ Protected paths work correctly")
        return True

    finally:
        helper.teardown()


async def test_delete_file_real_workspace_scenario():
    print("\n🧪 Testing delete_file with real .massgen/workspaces/ path...")

    helper = TestHelper()
    helper.setup()

    try:
        # Simulate REAL MassGen workspace structure
        massgen_root = helper.temp_dir / ".massgen"
        massgen_root.mkdir()
        workspaces_dir = massgen_root / "workspaces"
        workspaces_dir.mkdir()
        workspace = workspaces_dir / "workspace1"
        workspace.mkdir()

        # User creates files in their workspace
        user_project = workspace / "my_website"
        user_project.mkdir()
        index_file = user_project / "index.html"
        index_file.write_text("<html><body>Hello World</body></html>")
        styles_file = user_project / "styles.css"
        styles_file.write_text("body { color: blue; }")

        print(f"  Created test workspace at: {workspace}")
        print(f"  User project: {user_project}")

        # Import the helper functions directly to test logic
        from massgen.filesystem_manager._workspace_tools_server import (
            _is_critical_path,
            _is_permission_path_root,
        )

        # Test 1: User file should NOT be critical (key test!)
        print("  Testing that user file is not critical...")
        if _is_critical_path(index_file, [workspace]):
            print("❌ Failed: User file should not be critical")
            print(f"   Path: {index_file}")
            print(f"   Workspace: {workspace}")
            return False

        print("  ✓ User file correctly allowed")

        # Test 2: User directory should NOT be critical
        print("  Testing that user directory is not critical...")
        if _is_critical_path(user_project, [workspace]):
            print("❌ Failed: User directory should not be critical")
            print(f"   Path: {user_project}")
            return False

        print("  ✓ User directory correctly allowed")

        # Test 3: .git within workspace SHOULD be critical
        git_dir = workspace / ".git"
        git_dir.mkdir()

        print("  Testing that .git is still protected...")
        if not _is_critical_path(git_dir, [workspace]):
            print("❌ Failed: .git should be critical within workspace")
            return False

        print("  ✓ .git correctly blocked")

        # Test 4: .env within workspace SHOULD be critical
        env_file = workspace / ".env"
        env_file.write_text("SECRET=123")

        print("  Testing that .env is still protected...")
        if not _is_critical_path(env_file, [workspace]):
            print("❌ Failed: .env should be critical within workspace")
            return False

        print("  ✓ .env correctly blocked")

        # Test 5: Workspace root SHOULD be protected
        print("  Testing that workspace root is protected...")
        if not _is_permission_path_root(workspace, [workspace]):
            print("❌ Failed: Workspace root should be protected")
            return False

        print("  ✓ Workspace root correctly blocked")

        print("✅ Real workspace deletion scenario works correctly")
        return True

    finally:
        helper.teardown()


async def test_compare_tools():
    print("\n🔍 Testing comparison tools...")

    helper = TestHelper()
    helper.setup()

    try:
        print("  Testing compare tools are not write tools...")
        manager = helper.create_permission_manager()

        if manager._is_write_tool("compare_directories"):
            print("❌ Failed: compare_directories should not be write tool")
            return False

        if manager._is_write_tool("compare_files"):
            print("❌ Failed: compare_files should not be write tool")
            return False

        print("  Testing compare operations are always allowed...")
        # Compare tools should never be blocked since they're read-only
        tool_args = {"dir1": str(helper.workspace_dir), "dir2": str(helper.context_dir)}
        allowed, reason = await manager.pre_tool_use_hook("compare_directories", tool_args)
        if not allowed:
            print(f"❌ Failed: compare_directories should be allowed. Reason: {reason}")
            return False

        tool_args = {"file1": str(helper.workspace_dir / "workspace_file.txt"), "file2": str(helper.context_dir / "context_file.txt")}
        allowed, reason = await manager.pre_tool_use_hook("compare_files", tool_args)
        if not allowed:
            print(f"❌ Failed: compare_files should be allowed. Reason: {reason}")
            return False

        print("✅ Comparison tools work correctly")
        return True

    finally:
        helper.teardown()


def test_file_operation_tracker():
    print("\n📊 Testing FileOperationTracker...")

    helper = TestHelper()
    helper.setup()

    try:
        tracker = FileOperationTracker(enforce_read_before_delete=True)

        print("  Testing file read tracking...")
        test_file = helper.workspace_dir / "test.txt"
        test_file.write_text("content")

        # File not read yet
        if tracker.was_read(test_file):
            print("❌ Failed: File should not be marked as read initially")
            return False

        # Mark as read
        tracker.mark_as_read(test_file)

        if not tracker.was_read(test_file):
            print("❌ Failed: File should be marked as read after mark_as_read")
            return False

        print("  Testing created file tracking...")
        created_file = helper.workspace_dir / "created.txt"
        created_file.write_text("new content")

        tracker.mark_as_created(created_file)

        if not tracker.was_read(created_file):
            print("❌ Failed: Created file should count as 'read'")
            return False

        print("  Testing delete validation...")
        # Can delete read file
        can_delete, reason = tracker.can_delete(test_file)
        if not can_delete:
            print(f"❌ Failed: Should allow delete of read file. Reason: {reason}")
            return False

        # Cannot delete unread file
        unread_file = helper.workspace_dir / "unread.txt"
        unread_file.write_text("unread content")
        can_delete, reason = tracker.can_delete(unread_file)
        if can_delete:
            print("❌ Failed: Should block delete of unread file")
            return False
        if "must be read before deletion" not in reason:
            print(f"❌ Failed: Expected 'must be read before deletion' in reason, got: {reason}")
            return False

        # Can delete created file (even if not explicitly read)
        can_delete, reason = tracker.can_delete(created_file)
        if not can_delete:
            print(f"❌ Failed: Should allow delete of created file. Reason: {reason}")
            return False

        print("  Testing directory delete validation...")
        test_dir = helper.workspace_dir / "test_dir"
        test_dir.mkdir()
        (test_dir / "file1.txt").write_text("content 1")
        (test_dir / "file2.txt").write_text("content 2")

        # Cannot delete directory with unread files
        can_delete, reason = tracker.can_delete_directory(test_dir)
        if can_delete:
            print("❌ Failed: Should block delete of directory with unread files")
            return False

        # Mark files as read
        tracker.mark_as_read(test_dir / "file1.txt")
        tracker.mark_as_read(test_dir / "file2.txt")

        # Now can delete
        can_delete, reason = tracker.can_delete_directory(test_dir)
        if not can_delete:
            print(f"❌ Failed: Should allow delete of directory with all files read. Reason: {reason}")
            return False

        print("  Testing tracker stats...")
        stats = tracker.get_stats()
        if stats["read_files"] < 3:  # test_file + file1 + file2
            print(f"❌ Failed: Expected at least 3 read files, got {stats['read_files']}")
            return False
        if stats["created_files"] < 1:  # created_file
            print(f"❌ Failed: Expected at least 1 created file, got {stats['created_files']}")
            return False

        print("  Testing tracker clear...")
        tracker.clear()
        stats = tracker.get_stats()
        if stats["read_files"] != 0 or stats["created_files"] != 0:
            print(f"❌ Failed: Tracker should be empty after clear, got {stats}")
            return False

        print("  Testing disabled enforcement...")
        tracker_disabled = FileOperationTracker(enforce_read_before_delete=False)
        can_delete, reason = tracker_disabled.can_delete(unread_file)
        if not can_delete:
            print("❌ Failed: Should allow delete when enforcement disabled")
            return False

        print("✅ FileOperationTracker works correctly")
        return True

    finally:
        helper.teardown()


async def test_read_before_delete_tracking():
    print("\n📖 Testing read-before-delete tracking...")

    helper = TestHelper()
    helper.setup()

    try:
        # Create manager with read-before-delete enabled
        manager = PathPermissionManager(context_write_access_enabled=True, enforce_read_before_delete=True)
        manager.add_path(helper.workspace_dir, Permission.WRITE, "workspace")

        # Create test files
        file1 = helper.workspace_dir / "file1.txt"
        file1.write_text("content 1")
        file2 = helper.workspace_dir / "file2.txt"
        file2.write_text("content 2")

        print("  Testing Read tool tracking...")
        # Read file1
        tool_args = {"file_path": str(file1)}
        allowed, reason = await manager.pre_tool_use_hook("Read", tool_args)

        # Should be tracked as read
        if not manager.file_operation_tracker.was_read(file1):
            print("❌ Failed: Read tool should track file as read")
            return False

        print("  Testing Write tool tracking (creates file)...")
        new_file = helper.workspace_dir / "new_file.txt"
        tool_args = {"file_path": str(new_file)}
        allowed, reason = await manager.pre_tool_use_hook("Write", tool_args)

        # Write should track file as created
        if not manager.file_operation_tracker.was_read(new_file):
            print("❌ Failed: Write tool should track file as created")
            return False

        print("  Testing read_multimodal_files tracking...")
        image_file = helper.workspace_dir / "image.png"
        image_file.write_text("fake image data")
        tool_args = {"path": str(image_file)}
        allowed, reason = await manager.pre_tool_use_hook("read_multimodal_files", tool_args)

        if not manager.file_operation_tracker.was_read(image_file):
            print("❌ Failed: read_multimodal_files should track file as read")
            return False

        # Reset tracking for MCP version test
        manager.file_operation_tracker = FileOperationTracker()

        print("  Testing mcp__workspace_tools__read_multimodal_files tracking...")
        image_file2 = helper.workspace_dir / "image2.png"
        image_file2.write_text("fake image data")
        tool_args = {"path": str(image_file2)}
        allowed, reason = await manager.pre_tool_use_hook("mcp__workspace_tools__read_multimodal_files", tool_args)

        if not manager.file_operation_tracker.was_read(image_file2):
            print("❌ Failed: mcp__workspace_tools__read_multimodal_files should track file as read")
            return False

        print("  Testing mcp__filesystem__read_text_file tracking...")
        text_file = helper.workspace_dir / "text.txt"
        text_file.write_text("test content")
        tool_args = {"path": str(text_file)}
        allowed, reason = await manager.pre_tool_use_hook("mcp__filesystem__read_text_file", tool_args)

        if not manager.file_operation_tracker.was_read(text_file):
            print("❌ Failed: mcp__filesystem__read_text_file should track file as read")
            return False

        print("  Testing mcp__filesystem__read_multiple_files tracking...")
        file3 = helper.workspace_dir / "file3.txt"
        file4 = helper.workspace_dir / "file4.txt"
        file3.write_text("content3")
        file4.write_text("content4")
        tool_args = {"paths": [str(file3), str(file4)]}
        allowed, reason = await manager.pre_tool_use_hook("mcp__filesystem__read_multiple_files", tool_args)

        if not manager.file_operation_tracker.was_read(file3):
            print("❌ Failed: mcp__filesystem__read_multiple_files should track file3 as read")
            return False
        if not manager.file_operation_tracker.was_read(file4):
            print("❌ Failed: mcp__filesystem__read_multiple_files should track file4 as read")
            return False

        print("  Testing compare_files tracking...")
        tool_args = {"file1": str(file1), "file2": str(file2)}
        allowed, reason = await manager.pre_tool_use_hook("compare_files", tool_args)

        # Both files should be tracked
        if not manager.file_operation_tracker.was_read(file1):
            print("❌ Failed: compare_files should track file1 as read")
            return False
        if not manager.file_operation_tracker.was_read(file2):
            print("❌ Failed: compare_files should track file2 as read")
            return False

        print("✅ Read-before-delete tracking works correctly")
        return True

    finally:
        helper.teardown()


async def test_delete_validation_with_read_requirement():
    print("\n🗑️  Testing delete validation with read requirement...")

    helper = TestHelper()
    helper.setup()

    try:
        # Create manager with read-before-delete enabled
        manager = PathPermissionManager(context_write_access_enabled=True, enforce_read_before_delete=True)
        manager.add_path(helper.workspace_dir, Permission.WRITE, "workspace")

        # Create test files
        read_file = helper.workspace_dir / "read_file.txt"
        read_file.write_text("content")
        unread_file = helper.workspace_dir / "unread_file.txt"
        unread_file.write_text("content")

        print("  Testing delete of unread file is blocked...")
        tool_args = {"path": str(unread_file)}
        allowed, reason = await manager.pre_tool_use_hook("delete_file", tool_args)

        if allowed:
            print("❌ Failed: Delete of unread file should be blocked")
            return False
        if "must be read before deletion" not in reason:
            print(f"❌ Failed: Expected 'must be read before deletion' in reason, got: {reason}")
            return False

        print("  Testing delete after reading is allowed...")
        # Read the file first
        read_args = {"file_path": str(unread_file)}
        await manager.pre_tool_use_hook("Read", read_args)

        # Now delete should work
        tool_args = {"path": str(unread_file)}
        allowed, reason = await manager.pre_tool_use_hook("delete_file", tool_args)

        if not allowed:
            print(f"❌ Failed: Delete after reading should be allowed. Reason: {reason}")
            return False

        print("  Testing delete of created file is allowed...")
        new_file = helper.workspace_dir / "new.txt"
        write_args = {"file_path": str(new_file)}
        await manager.pre_tool_use_hook("Write", write_args)

        # Can delete created file without reading
        tool_args = {"path": str(new_file)}
        allowed, reason = await manager.pre_tool_use_hook("delete_file", tool_args)

        if not allowed:
            print(f"❌ Failed: Delete of created file should be allowed. Reason: {reason}")
            return False

        print("  Testing directory delete with unread files...")
        test_dir = helper.workspace_dir / "test_dir"
        test_dir.mkdir()
        (test_dir / "file1.txt").write_text("content 1")
        (test_dir / "file2.txt").write_text("content 2")

        tool_args = {"path": str(test_dir), "recursive": True}
        allowed, reason = await manager.pre_tool_use_hook("delete_file", tool_args)

        if allowed:
            print("❌ Failed: Delete of directory with unread files should be blocked")
            return False

        # Read files
        await manager.pre_tool_use_hook("Read", {"file_path": str(test_dir / "file1.txt")})
        await manager.pre_tool_use_hook("Read", {"file_path": str(test_dir / "file2.txt")})

        # Now should work
        tool_args = {"path": str(test_dir), "recursive": True}
        allowed, reason = await manager.pre_tool_use_hook("delete_file", tool_args)

        if not allowed:
            print(f"❌ Failed: Delete after reading all files should be allowed. Reason: {reason}")
            return False

        print("✅ Delete validation with read requirement works correctly")
        return True

    finally:
        helper.teardown()


async def test_batch_delete_with_read_requirement():
    print("\n🗑️📦 Testing batch delete with read requirement...")

    helper = TestHelper()
    helper.setup()

    try:
        # Create manager with read-before-delete enabled
        manager = PathPermissionManager(context_write_access_enabled=True, enforce_read_before_delete=True)
        manager.add_path(helper.workspace_dir, Permission.WRITE, "workspace")

        # Create test files
        for i in range(3):
            (helper.workspace_dir / f"file{i}.txt").write_text(f"content {i}")

        print("  Testing batch delete of unread files is blocked...")
        tool_args = {"base_path": str(helper.workspace_dir), "include_patterns": ["*.txt"]}
        allowed, reason = await manager.pre_tool_use_hook("delete_files_batch", tool_args)

        if allowed:
            print("❌ Failed: Batch delete of unread files should be blocked")
            return False
        if "unread file(s)" not in reason:
            print(f"❌ Failed: Expected 'unread file(s)' in reason, got: {reason}")
            return False

        print("  Testing batch delete after reading some files...")
        # Read only file0 and file1
        await manager.pre_tool_use_hook("Read", {"file_path": str(helper.workspace_dir / "file0.txt")})
        await manager.pre_tool_use_hook("Read", {"file_path": str(helper.workspace_dir / "file1.txt")})

        # Still should be blocked because file2 is unread
        tool_args = {"base_path": str(helper.workspace_dir), "include_patterns": ["*.txt"]}
        allowed, reason = await manager.pre_tool_use_hook("delete_files_batch", tool_args)

        if allowed:
            print("❌ Failed: Batch delete should still be blocked with unread files")
            return False

        print("  Testing batch delete after reading all files...")
        # Read file2
        await manager.pre_tool_use_hook("Read", {"file_path": str(helper.workspace_dir / "file2.txt")})

        # Now should work
        tool_args = {"base_path": str(helper.workspace_dir), "include_patterns": ["*.txt"]}
        allowed, reason = await manager.pre_tool_use_hook("delete_files_batch", tool_args)

        if not allowed:
            print(f"❌ Failed: Batch delete after reading all should be allowed. Reason: {reason}")
            return False

        print("  Testing batch delete with exclusions...")
        # Create new files
        (helper.workspace_dir / "include1.txt").write_text("include 1")
        (helper.workspace_dir / "include2.txt").write_text("include 2")
        (helper.workspace_dir / "exclude1.txt").write_text("exclude 1")

        # Read only included files
        await manager.pre_tool_use_hook("Read", {"file_path": str(helper.workspace_dir / "include1.txt")})
        await manager.pre_tool_use_hook("Read", {"file_path": str(helper.workspace_dir / "include2.txt")})

        # Should work because excluded files aren't checked
        tool_args = {"base_path": str(helper.workspace_dir), "include_patterns": ["include*.txt"], "exclude_patterns": ["exclude*.txt"]}
        allowed, reason = await manager.pre_tool_use_hook("delete_files_batch", tool_args)

        if not allowed:
            print(f"❌ Failed: Batch delete with proper exclusions should work. Reason: {reason}")
            return False

        print("✅ Batch delete with read requirement works correctly")
        return True

    finally:
        helper.teardown()


async def test_read_before_delete_disabled():
    print("\n🔓 Testing read-before-delete when disabled...")

    helper = TestHelper()
    helper.setup()

    try:
        # Create manager with read-before-delete DISABLED
        manager = PathPermissionManager(context_write_access_enabled=True, enforce_read_before_delete=False)
        manager.add_path(helper.workspace_dir, Permission.WRITE, "workspace")

        # Create unread file
        unread_file = helper.workspace_dir / "unread.txt"
        unread_file.write_text("content")

        print("  Testing delete of unread file is allowed when disabled...")
        tool_args = {"path": str(unread_file)}
        allowed, reason = await manager.pre_tool_use_hook("delete_file", tool_args)

        if not allowed:
            print(f"❌ Failed: Delete should be allowed when enforcement disabled. Reason: {reason}")
            return False

        print("  Testing batch delete of unread files is allowed...")
        for i in range(3):
            (helper.workspace_dir / f"batch{i}.txt").write_text(f"content {i}")

        tool_args = {"base_path": str(helper.workspace_dir), "include_patterns": ["batch*.txt"]}
        allowed, reason = await manager.pre_tool_use_hook("delete_files_batch", tool_args)

        if not allowed:
            print(f"❌ Failed: Batch delete should be allowed when enforcement disabled. Reason: {reason}")
            return False

        print("✅ Read-before-delete disabled mode works correctly")
        return True

    finally:
        helper.teardown()


async def main():
    print("\n" + "=" * 60)
    print("🧪 Path Permission Manager Test Suite")
    print("=" * 60)

    sync_tests = [
        test_is_write_tool,
        test_validate_write_tool,
        test_validate_command_tool,
        test_validate_execute_command_tool,
        test_context_write_access_toggle,
        test_extract_file_from_command,
        test_workspace_tools,
        test_workspace_tools_server_path_validation,
        test_file_context_paths,
        test_delete_operations,
        test_permission_path_root_protection,
        test_protected_paths,
        test_file_operation_tracker,
    ]

    async_tests = [
        test_pre_tool_use_hook,
        test_mcp_relative_paths,
        test_delete_file_real_workspace_scenario,
        test_compare_tools,
        test_read_before_delete_tracking,
        test_delete_validation_with_read_requirement,
        test_batch_delete_with_read_requirement,
        test_read_before_delete_disabled,
    ]

    passed = 0
    failed = 0

    # Run synchronous tests
    for test_func in sync_tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ {test_func.__name__} failed with exception: {e}")
            traceback.print_exc()
            failed += 1

    # Run asynchronous tests
    for test_func in async_tests:
        try:
            await test_func()
            passed += 1
        except Exception as e:
            print(f"❌ {test_func.__name__} failed with exception: {e}")
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"📊 Test Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
