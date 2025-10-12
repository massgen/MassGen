# -*- coding: utf-8 -*-
"""
Unit tests for code execution MCP server.
"""
import subprocess
import sys
from pathlib import Path

import pytest

# Test utilities
def run_command_directly(command: str, cwd: str = None, timeout: int = 10) -> tuple:
    """Helper to run commands directly for testing."""
    result = subprocess.run(
        command,
        shell=True,
        cwd=cwd,
        timeout=timeout,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


class TestCodeExecutionBasics:
    """Test basic command execution functionality."""

    def test_simple_python_command(self, tmp_path):
        """Test executing a simple Python command."""
        exit_code, stdout, stderr = run_command_directly(
            f'{sys.executable} -c "print(\\"Hello, World!\\")"',
            cwd=str(tmp_path),
        )
        assert exit_code == 0
        assert "Hello, World!" in stdout

    def test_python_script_execution(self, tmp_path):
        """Test executing a Python script."""
        # Create a test script
        script_path = tmp_path / "test_script.py"
        script_path.write_text("print('Script executed')\nprint('Success')")

        exit_code, stdout, stderr = run_command_directly(
            f"{sys.executable} test_script.py",
            cwd=str(tmp_path),
        )
        assert exit_code == 0
        assert "Script executed" in stdout
        assert "Success" in stdout

    def test_command_with_error(self, tmp_path):
        """Test that command errors are captured."""
        exit_code, stdout, stderr = run_command_directly(
            f'{sys.executable} -c "import sys; sys.exit(1)"',
            cwd=str(tmp_path),
        )
        assert exit_code == 1

    def test_command_timeout(self, tmp_path):
        """Test that commands can timeout."""
        with pytest.raises(subprocess.TimeoutExpired):
            run_command_directly(
                f'{sys.executable} -c "import time; time.sleep(10)"',
                cwd=str(tmp_path),
                timeout=1,
            )

    def test_working_directory(self, tmp_path):
        """Test that working directory is respected."""
        # Create a file in tmp_path
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        # List files using command
        exit_code, stdout, stderr = run_command_directly(
            f'{sys.executable} -c "import os; print(os.listdir())"',
            cwd=str(tmp_path),
        )
        assert exit_code == 0
        assert "test.txt" in stdout


class TestPathValidation:
    """Test path validation and security."""

    def test_path_exists_validation(self, tmp_path):
        """Test that non-existent paths are rejected."""
        non_existent = tmp_path / "does_not_exist"
        # subprocess.run should raise FileNotFoundError for non-existent cwd
        with pytest.raises(FileNotFoundError):
            run_command_directly(
                'echo "test"',
                cwd=str(non_existent),
            )

    def test_relative_path_resolution(self, tmp_path):
        """Test that relative paths are resolved correctly."""
        # Create subdirectory
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        # Create file in subdir
        test_file = subdir / "test.txt"
        test_file.write_text("content")

        # Try to read file from parent using relative path
        exit_code, stdout, stderr = run_command_directly(
            f'{sys.executable} -c "import os; print(os.path.exists(\'subdir/test.txt\'))"',
            cwd=str(tmp_path),
        )
        assert exit_code == 0
        assert "True" in stdout


class TestCommandSanitization:
    """Test command sanitization patterns."""

    def test_dangerous_command_patterns(self):
        """Test that dangerous patterns are identified."""
        from massgen.filesystem_manager._code_execution_server import _sanitize_command

        dangerous_commands = [
            "rm -rf /",
            "dd if=/dev/zero of=/dev/sda",
            ":(){ :|:& };:",  # Fork bomb
            "mv file /dev/null",
            "sudo apt install something",
            "su root",
            "chown root file.txt",
            "chmod 777 file.txt",
        ]

        for cmd in dangerous_commands:
            with pytest.raises(ValueError, match="dangerous|not allowed"):
                _sanitize_command(cmd)

    def test_safe_commands_pass(self):
        """Test that safe commands pass sanitization."""
        from massgen.filesystem_manager._code_execution_server import _sanitize_command

        safe_commands = [
            "python script.py",
            "pytest tests/",
            "npm run build",
            "ls -la",
            "rm file.txt",  # Specific file, not rm -rf /
            "git submodule update",  # Contains "su" but not "su " command
            "echo 'summary'",  # Contains "su" substring
            "python -m pip install --user requests",  # Contains "user" not "su"
        ]

        for cmd in safe_commands:
            # Should not raise
            _sanitize_command(cmd)


class TestOutputHandling:
    """Test output capture and size limits."""

    def test_stdout_capture(self, tmp_path):
        """Test that stdout is captured correctly."""
        exit_code, stdout, stderr = run_command_directly(
            f'{sys.executable} -c "print(\\"line1\\"); print(\\"line2\\")"',
            cwd=str(tmp_path),
        )
        assert exit_code == 0
        assert "line1" in stdout
        assert "line2" in stdout

    def test_stderr_capture(self, tmp_path):
        """Test that stderr is captured correctly."""
        exit_code, stdout, stderr = run_command_directly(
            f'{sys.executable} -c "import sys; sys.stderr.write(\\"error message\\\\n\\")"',
            cwd=str(tmp_path),
        )
        assert "error message" in stderr

    def test_large_output_handling(self, tmp_path):
        """Test handling of large output."""
        # Generate large output (1000 lines)
        exit_code, stdout, stderr = run_command_directly(
            f'{sys.executable} -c "for i in range(1000): print(i)"',
            cwd=str(tmp_path),
        )
        assert exit_code == 0
        assert len(stdout) > 0  # Output was captured


class TestCrossPlatform:
    """Test cross-platform compatibility."""

    def test_python_version_check(self, tmp_path):
        """Test that Python version can be checked."""
        exit_code, stdout, stderr = run_command_directly(
            f"{sys.executable} --version",
            cwd=str(tmp_path),
        )
        assert exit_code == 0
        assert "Python" in stdout or "Python" in stderr  # Version might be in stderr

    def test_pip_install(self, tmp_path):
        """Test that pip commands work."""
        # Just check pip version, don't actually install anything
        exit_code, stdout, stderr = run_command_directly(
            f"{sys.executable} -m pip --version",
            cwd=str(tmp_path),
        )
        assert exit_code == 0
        assert "pip" in stdout or "pip" in stderr


class TestAutoGeneratedFiles:
    """Test handling of auto-generated files."""

    def test_pycache_deletion_allowed(self, tmp_path):
        """Test that __pycache__ files can be deleted without reading."""
        from massgen.filesystem_manager._file_operation_tracker import FileOperationTracker

        tracker = FileOperationTracker(enforce_read_before_delete=True)

        # Create a fake __pycache__ file
        pycache_dir = tmp_path / "__pycache__"
        pycache_dir.mkdir()
        pyc_file = pycache_dir / "test.cpython-313.pyc"
        pyc_file.write_text("fake bytecode")

        # Should be deletable without reading
        can_delete, reason = tracker.can_delete(pyc_file)
        assert can_delete
        assert reason is None

    def test_pyc_file_deletion_allowed(self, tmp_path):
        """Test that .pyc files can be deleted without reading."""
        from massgen.filesystem_manager._file_operation_tracker import FileOperationTracker

        tracker = FileOperationTracker(enforce_read_before_delete=True)

        # Create a fake .pyc file
        pyc_file = tmp_path / "module.pyc"
        pyc_file.write_text("fake bytecode")

        # Should be deletable without reading
        can_delete, reason = tracker.can_delete(pyc_file)
        assert can_delete
        assert reason is None

    def test_pytest_cache_deletion_allowed(self, tmp_path):
        """Test that .pytest_cache can be deleted without reading."""
        from massgen.filesystem_manager._file_operation_tracker import FileOperationTracker

        tracker = FileOperationTracker(enforce_read_before_delete=True)

        # Create a fake .pytest_cache directory
        cache_dir = tmp_path / ".pytest_cache"
        cache_dir.mkdir()
        cache_file = cache_dir / "v" / "cache" / "nodeids"
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text("test data")

        # Should be deletable without reading
        can_delete, reason = tracker.can_delete(cache_file)
        assert can_delete
        assert reason is None

    def test_regular_file_requires_read(self, tmp_path):
        """Test that regular files still require reading before deletion."""
        from massgen.filesystem_manager._file_operation_tracker import FileOperationTracker

        tracker = FileOperationTracker(enforce_read_before_delete=True)

        # Create a regular Python file
        py_file = tmp_path / "module.py"
        py_file.write_text("print('hello')")

        # Should NOT be deletable without reading
        can_delete, reason = tracker.can_delete(py_file)
        assert not can_delete
        assert reason is not None
        assert "must be read before deletion" in reason

    def test_directory_with_pycache_allowed(self, tmp_path):
        """Test that directories containing only __pycache__ can be deleted."""
        from massgen.filesystem_manager._file_operation_tracker import FileOperationTracker

        tracker = FileOperationTracker(enforce_read_before_delete=True)

        # Create directory with __pycache__ only
        test_dir = tmp_path / "mymodule"
        test_dir.mkdir()
        pycache_dir = test_dir / "__pycache__"
        pycache_dir.mkdir()
        pyc_file = pycache_dir / "test.pyc"
        pyc_file.write_text("fake bytecode")

        # Should be deletable (only contains auto-generated files)
        can_delete, reason = tracker.can_delete_directory(test_dir)
        assert can_delete
        assert reason is None


class TestVirtualEnvironment:
    """Test virtual environment handling."""

    def test_auto_detect_venv(self, tmp_path):
        """Test auto-detection of .venv directory."""
        from massgen.filesystem_manager._code_execution_server import _prepare_environment

        # Create fake .venv structure
        venv_dir = tmp_path / ".venv"
        venv_bin = venv_dir / "bin"
        venv_bin.mkdir(parents=True, exist_ok=True)

        # Test auto-detection
        cmd_prefix, env = _prepare_environment(tmp_path, None, None)

        assert cmd_prefix is None  # No prefix, just PATH modification
        assert "PATH" in env
        assert str(venv_bin) in env["PATH"]
        assert "VIRTUAL_ENV" in env
        assert str(venv_dir) in env["VIRTUAL_ENV"]

    def test_command_prefix_priority(self, tmp_path):
        """Test that command_prefix takes priority over auto-detection."""
        from massgen.filesystem_manager._code_execution_server import _prepare_environment

        # Create fake .venv (should be ignored)
        venv_dir = tmp_path / ".venv"
        venv_bin = venv_dir / "bin"
        venv_bin.mkdir(parents=True, exist_ok=True)

        # Test command prefix priority
        cmd_prefix, env = _prepare_environment(tmp_path, "uv run", None)

        assert cmd_prefix == "uv run"  # Prefix returned
        # PATH should NOT be modified when using prefix
        assert str(venv_bin) not in env.get("PATH", "")

    def test_custom_venv_path(self, tmp_path):
        """Test custom venv path configuration."""
        from massgen.filesystem_manager._code_execution_server import _prepare_environment

        # Create custom venv in different location
        custom_venv = tmp_path / "custom" / ".venv"
        custom_bin = custom_venv / "bin"
        custom_bin.mkdir(parents=True, exist_ok=True)

        # Test custom venv path
        cmd_prefix, env = _prepare_environment(tmp_path, None, custom_venv)

        assert cmd_prefix is None
        assert str(custom_bin) in env["PATH"]
        assert str(custom_venv) in env["VIRTUAL_ENV"]

    def test_no_venv_fallback(self, tmp_path):
        """Test fallback to system environment when no venv."""
        from massgen.filesystem_manager._code_execution_server import _prepare_environment
        import os

        # No .venv directory
        cmd_prefix, env = _prepare_environment(tmp_path, None, None)

        assert cmd_prefix is None
        # Should just be copy of system environment
        assert env["PATH"] == os.environ["PATH"]


class TestDockerIntegration:
    """Test Docker isolation functionality."""

    @pytest.fixture
    def docker_available(self):
        """Check if Docker is available."""
        from massgen.filesystem_manager._docker_manager import DOCKER_AVAILABLE
        if not DOCKER_AVAILABLE:
            pytest.skip("Docker not available")
        return True

    @pytest.fixture
    def docker_manager(self, docker_available):
        """Create a DockerManager instance for testing."""
        from massgen.filesystem_manager._docker_manager import DockerManager

        manager = DockerManager(
            image="massgen/mcp-runtime:latest",
            network_mode="none",
            memory_limit=None,
            cpu_limit=None,
        )
        yield manager
        # Cleanup any containers created during tests
        manager.cleanup()

    def test_docker_manager_initialization(self, docker_available):
        """Test DockerManager can be initialized."""
        from massgen.filesystem_manager._docker_manager import DockerManager

        manager = DockerManager(
            image="massgen/mcp-runtime:latest",
            network_mode="none",
            memory_limit="512m",
            cpu_limit=1.0,
        )
        assert manager.image == "massgen/mcp-runtime:latest"
        assert manager.network_mode == "none"
        assert manager.memory_limit == "512m"
        assert manager.cpu_limit == 1.0

    def test_image_exists_check(self, docker_manager):
        """Test that image existence can be checked."""
        # This should not raise if image exists
        docker_manager.ensure_image_exists()

    def test_container_creation(self, docker_manager, tmp_path):
        """Test creating a Docker container with volume mounts."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        temp_workspace = tmp_path / "temp"
        temp_workspace.mkdir()

        # Create a test file
        test_file = workspace / "test.txt"
        test_file.write_text("test content")

        # Create container
        container_id = docker_manager.create_container(
            agent_id="test_agent",
            workspace_path=workspace,
            temp_workspace_path=temp_workspace,
            context_paths=[],
        )

        assert container_id is not None
        assert "test_agent" in docker_manager.containers

        # Cleanup
        docker_manager.cleanup("test_agent")

    def test_container_with_context_paths(self, docker_manager, tmp_path):
        """Test container creation with context paths."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        temp_workspace = tmp_path / "temp"
        temp_workspace.mkdir()

        context_dir = tmp_path / "context"
        context_dir.mkdir()

        context_paths = [
            {
                "path": context_dir,
                "mount_name": "shared",
                "permission": "read",
            }
        ]

        container_id = docker_manager.create_container(
            agent_id="test_context_agent",
            workspace_path=workspace,
            temp_workspace_path=temp_workspace,
            context_paths=context_paths,
        )

        assert container_id is not None

        # Cleanup
        docker_manager.cleanup("test_context_agent")

    def test_exec_command_in_container(self, docker_manager, tmp_path):
        """Test executing a command inside container."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        temp_workspace = tmp_path / "temp"
        temp_workspace.mkdir()

        # Create container
        container_id = docker_manager.create_container(
            agent_id="test_exec_agent",
            workspace_path=workspace,
            temp_workspace_path=temp_workspace,
            context_paths=[],
        )

        # Execute command
        result = docker_manager.exec_command(
            agent_id="test_exec_agent",
            command=["python3", "-c", "print('Hello from Docker')"],
            workdir="/workspace",
        )

        assert result["exit_code"] == 0
        assert "Hello from Docker" in result["output"]

        # Cleanup
        docker_manager.cleanup("test_exec_agent")

    def test_container_cleanup(self, docker_manager, tmp_path):
        """Test that containers are properly cleaned up."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        temp_workspace = tmp_path / "temp"
        temp_workspace.mkdir()

        # Create container
        container_id = docker_manager.create_container(
            agent_id="test_cleanup_agent",
            workspace_path=workspace,
            temp_workspace_path=temp_workspace,
            context_paths=[],
        )

        assert "test_cleanup_agent" in docker_manager.containers

        # Cleanup specific container
        docker_manager.cleanup("test_cleanup_agent")

        assert "test_cleanup_agent" not in docker_manager.containers

    def test_cleanup_all_containers(self, docker_manager, tmp_path):
        """Test cleanup of all containers."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        temp_workspace = tmp_path / "temp"
        temp_workspace.mkdir()

        # Create multiple containers
        for i in range(3):
            docker_manager.create_container(
                agent_id=f"test_multi_agent_{i}",
                workspace_path=workspace,
                temp_workspace_path=temp_workspace,
                context_paths=[],
            )

        assert len(docker_manager.containers) == 3

        # Cleanup all
        docker_manager.cleanup()

        assert len(docker_manager.containers) == 0

    def test_container_resource_limits(self, docker_available, tmp_path):
        """Test container creation with resource limits."""
        from massgen.filesystem_manager._docker_manager import DockerManager

        manager = DockerManager(
            image="massgen/mcp-runtime:latest",
            network_mode="bridge",
            memory_limit="512m",
            cpu_limit=1.5,
        )

        workspace = tmp_path / "workspace"
        workspace.mkdir()

        temp_workspace = tmp_path / "temp"
        temp_workspace.mkdir()

        container_id = manager.create_container(
            agent_id="test_limits_agent",
            workspace_path=workspace,
            temp_workspace_path=temp_workspace,
            context_paths=[],
        )

        assert container_id is not None

        # Cleanup
        manager.cleanup("test_limits_agent")

    def test_network_isolation_modes(self, docker_available, tmp_path):
        """Test different network isolation modes."""
        from massgen.filesystem_manager._docker_manager import DockerManager

        workspace = tmp_path / "workspace"
        workspace.mkdir()

        temp_workspace = tmp_path / "temp"
        temp_workspace.mkdir()

        # Test different network modes
        for mode in ["none", "bridge", "host"]:
            manager = DockerManager(
                image="massgen/mcp-runtime:latest",
                network_mode=mode,
                memory_limit=None,
                cpu_limit=None,
            )

            container_id = manager.create_container(
                agent_id=f"test_network_{mode}",
                workspace_path=workspace,
                temp_workspace_path=temp_workspace,
                context_paths=[],
            )

            assert container_id is not None

            # Cleanup
            manager.cleanup(f"test_network_{mode}")

    def test_container_name_conflict_handling(self, docker_available, tmp_path):
        """Test that existing containers with same name are handled gracefully."""
        from massgen.filesystem_manager._docker_manager import DockerManager

        workspace = tmp_path / "workspace"
        workspace.mkdir()

        temp_workspace = tmp_path / "temp"
        temp_workspace.mkdir()

        manager = DockerManager(
            image="massgen/mcp-runtime:latest",
            network_mode="none",
            memory_limit=None,
            cpu_limit=None,
        )

        # Create first container
        container_id1 = manager.create_container(
            agent_id="test_conflict",
            workspace_path=workspace,
            temp_workspace_path=temp_workspace,
            context_paths=[],
        )

        assert container_id1 is not None

        # Cleanup but leave container on disk (simulate unclean shutdown)
        manager.containers.clear()  # Clear internal tracking

        # Create second container with same agent_id - should succeed
        container_id2 = manager.create_container(
            agent_id="test_conflict",
            workspace_path=workspace,
            temp_workspace_path=temp_workspace,
            context_paths=[],
        )

        assert container_id2 is not None
        # Should be a new container
        assert container_id1 != container_id2

        # Cleanup
        manager.cleanup("test_conflict")

    def test_docker_run_mcp_inside_parameter(self, tmp_path):
        """Test that docker_run_mcp_inside parameter works correctly."""
        from massgen.filesystem_manager import FilesystemManager

        # Create necessary directories
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        temp_workspace = tmp_path / "temp"
        temp_workspace.mkdir()

        # Test with docker_run_mcp_inside=True (should wrap MCP configs with docker exec)
        fs_manager = FilesystemManager(
            cwd=str(workspace),
            agent_temporary_workspace_parent=str(temp_workspace),
            enable_docker_isolation=True,
            docker_run_mcp_inside=True,
            docker_image="massgen/mcp-runtime:latest",
        )

        # Check that parameter is set correctly
        assert fs_manager.docker_run_mcp_inside is True

        # Get MCP config and check it will be wrapped
        mcp_config = {}
        result_config = fs_manager.inject_filesystem_mcp(mcp_config)

        # Should have MCP servers
        assert "mcp_servers" in result_config
        servers = result_config["mcp_servers"]
        assert len(servers) >= 2  # At least filesystem and workspace_tools

        # Check that commands are wrapped with docker exec
        for server in servers:
            if server["name"] in ["filesystem", "workspace_tools"]:
                # These should be wrapped with docker exec
                assert server["command"] == "docker", f"Server {server['name']} should use docker exec"
                assert "exec" in server["args"], f"Server {server['name']} should have 'exec' in args"

        # Cleanup
        if fs_manager.docker_manager and fs_manager.docker_container_id:
            agent_id = fs_manager.docker_early_container_name.replace("massgen-", "") if fs_manager.docker_early_container_name else "test"
            fs_manager.docker_manager.cleanup(agent_id)

    def test_docker_run_mcp_inside_false(self, tmp_path):
        """Test that docker_run_mcp_inside=False keeps MCP on host."""
        from massgen.filesystem_manager import FilesystemManager

        # Create necessary directories
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        temp_workspace = tmp_path / "temp"
        temp_workspace.mkdir()

        # Test with docker_run_mcp_inside=False (MCP servers run on host)
        fs_manager = FilesystemManager(
            cwd=str(workspace),
            agent_temporary_workspace_parent=str(temp_workspace),
            enable_docker_isolation=True,
            docker_run_mcp_inside=False,  # Explicitly set to False
            docker_image="massgen/mcp-runtime:latest",
        )

        # Check that parameter is set correctly
        assert fs_manager.docker_run_mcp_inside is False

        # Get MCP config and check it's NOT wrapped
        mcp_config = {}
        result_config = fs_manager.inject_filesystem_mcp(mcp_config)

        # Should have MCP servers
        assert "mcp_servers" in result_config
        servers = result_config["mcp_servers"]
        assert len(servers) >= 2  # At least filesystem and workspace_tools

        # Check that commands are NOT wrapped with docker exec
        for server in servers:
            if server["name"] == "filesystem":
                # This should NOT be wrapped
                assert server["command"] == "npx", "Filesystem server should use npx on host"
            elif server["name"] == "workspace_tools":
                # This should NOT be wrapped
                assert server["command"] == "fastmcp", "Workspace tools should use fastmcp on host"

        # No container should be created early
        assert fs_manager.docker_container_id is None

    def test_docker_run_mcp_inside_defaults_to_false(self, tmp_path):
        """Test that docker_run_mcp_inside defaults to False when not specified."""
        from massgen.filesystem_manager import FilesystemManager

        # Create necessary directories
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        temp_workspace = tmp_path / "temp"
        temp_workspace.mkdir()

        # Test with docker_run_mcp_inside NOT specified (should default to False)
        fs_manager = FilesystemManager(
            cwd=str(workspace),
            agent_temporary_workspace_parent=str(temp_workspace),
            enable_docker_isolation=True,
            # docker_run_mcp_inside NOT specified - should default to False
            docker_image="massgen/mcp-runtime:latest",
        )

        # Check that parameter defaults to False
        assert fs_manager.docker_run_mcp_inside is False

        # Get MCP config and verify MCP servers run on host (not wrapped)
        mcp_config = {}
        result_config = fs_manager.inject_filesystem_mcp(mcp_config)

        # Should have MCP servers
        assert "mcp_servers" in result_config
        servers = result_config["mcp_servers"]
        assert len(servers) >= 2

        # Check that commands are NOT wrapped with docker exec (running on host)
        for server in servers:
            if server["name"] == "filesystem":
                assert server["command"] == "npx", "Filesystem server should use npx on host by default"
            elif server["name"] == "workspace_tools":
                assert server["command"] == "fastmcp", "Workspace tools should use fastmcp on host by default"

        # No early container should be created when MCP runs on host
        assert fs_manager.docker_container_id is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
