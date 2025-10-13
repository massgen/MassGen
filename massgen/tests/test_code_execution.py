# -*- coding: utf-8 -*-
"""
Unit tests for code execution MCP server.
"""
import subprocess
import sys

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
            f"{sys.executable} -c \"import os; print(os.path.exists('subdir/test.txt'))\"",
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
        from massgen.filesystem_manager._file_operation_tracker import (
            FileOperationTracker,
        )

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
        from massgen.filesystem_manager._file_operation_tracker import (
            FileOperationTracker,
        )

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
        from massgen.filesystem_manager._file_operation_tracker import (
            FileOperationTracker,
        )

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
        from massgen.filesystem_manager._file_operation_tracker import (
            FileOperationTracker,
        )

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
        from massgen.filesystem_manager._file_operation_tracker import (
            FileOperationTracker,
        )

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
        from massgen.filesystem_manager._code_execution_server import (
            _prepare_environment,
        )

        # Create fake .venv structure
        venv_dir = tmp_path / ".venv"
        venv_bin = venv_dir / "bin"
        venv_bin.mkdir(parents=True, exist_ok=True)

        # Test auto-detection
        env = _prepare_environment(tmp_path)

        assert "PATH" in env
        assert str(venv_bin) in env["PATH"]
        assert "VIRTUAL_ENV" in env
        assert str(venv_dir) in env["VIRTUAL_ENV"]

    def test_no_venv_fallback(self, tmp_path):
        """Test fallback to system environment when no venv."""
        import os

        from massgen.filesystem_manager._code_execution_server import (
            _prepare_environment,
        )

        # No .venv directory
        env = _prepare_environment(tmp_path)

        # Should just be copy of system environment
        assert env["PATH"] == os.environ["PATH"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
