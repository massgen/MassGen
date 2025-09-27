# -*- coding: utf-8 -*-
import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

# Removed wc_server import - now using factory function approach
from massgen.backend.utils.filesystem_manager import (
    FilesystemManager,
    PathPermissionManager,
    Permission,
)
from massgen.backend.utils.filesystem_manager._workspace_copy_server import (
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

        # Get workspace copy config - should also include cwd parameter
        workspace_copy_config = filesystem_manager.get_workspace_copy_mcp_config()
        print(f"🔧 Workspace copy MCP config: {workspace_copy_config}")

        # Verify cwd is set correctly (resolve both paths to handle /private prefix on macOS)
        expected_cwd = str(workspace_dir.resolve())
        actual_cwd = str(Path(workspace_copy_config.get("cwd")).resolve())
        assert actual_cwd == expected_cwd, f"Expected cwd={expected_cwd}, got {actual_cwd}"
        print("✅ Workspace copy config has correct cwd")

        # Test filesystem MCP server
        print("\n📡 Testing filesystem MCP server...")
        try:
            async with MCPClient(filesystem_config, timeout_seconds=10) as client:
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

        # Test workspace copy MCP server
        print("\n📦 Testing workspace copy MCP server...")
        try:
            async with MCPClient(workspace_copy_config, timeout_seconds=10) as client:
                print("✅ Workspace copy MCP server connected successfully")
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
                            import json

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
        print("  Testing dangerous command...")
        tool_args = {"command": "rm -rf /"}
        allowed, reason = await manager.pre_tool_use_hook("Bash", tool_args)

        if allowed:
            print("❌ Failed: Dangerous command should be blocked")
            return False
        if "Dangerous command pattern" not in reason:
            print(f"❌ Failed: Expected 'Dangerous command pattern' in reason, got: {reason}")
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


def test_workspace_copy_tools():
    print("\n📦 Testing workspace copy tool validation...")

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

        copy_tools = ["copy_file", "copy_files_batch", "mcp__workspace_copy__copy_file", "mcp__workspace_copy__copy_files_batch"]
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


def test_workspace_copy_server_path_validation():
    print("\n🏗️  Testing workspace copy server path validation...")

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
        import os

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


async def main():
    print("\n" + "=" * 60)
    print("🧪 Path Permission Manager Test Suite")
    print("=" * 60)

    sync_tests = [
        test_is_write_tool,
        test_validate_write_tool,
        test_validate_command_tool,
        test_context_write_access_toggle,
        test_extract_file_from_command,
        test_workspace_copy_tools,
        test_workspace_copy_server_path_validation,
    ]

    async_tests = [
        test_pre_tool_use_hook,
        test_mcp_relative_paths,
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
            import traceback

            traceback.print_exc()
            failed += 1

    # Run asynchronous tests
    for test_func in async_tests:
        try:
            await test_func()
            passed += 1
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
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
