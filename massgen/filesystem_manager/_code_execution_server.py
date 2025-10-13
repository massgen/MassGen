#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Code Execution MCP Server for MassGen

This MCP server provides command line execution capabilities for agents, allowing
them to run tests, execute scripts, and perform other command-line operations.

Tools provided:
- execute_command: Execute any command line command with timeout and working directory control

Inspired by AG2's LocalCommandLineCodeExecutor sanitization patterns.
"""

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import fastmcp

# Platform detection
WIN32 = sys.platform == "win32"


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


def _sanitize_command(command: str) -> None:
    """
    Sanitize the command to prevent dangerous operations.

    Adapted from AG2's LocalCommandLineCodeExecutor.sanitize_command().
    This provides basic protection for users running commands outside Docker.

    Args:
        command: The command to sanitize

    Raises:
        ValueError: If dangerous command is detected
    """
    dangerous_patterns = [
        # AG2 original patterns
        (r"\brm\s+-rf\s+/", "Use of 'rm -rf /' is not allowed"),
        (r"\bmv\b.*?\s+/dev/null", "Moving files to /dev/null is not allowed"),
        (r"\bdd\b", "Use of 'dd' command is not allowed"),
        (r">\s*/dev/sd[a-z][1-9]?", "Overwriting disk blocks directly is not allowed"),
        (r":\(\)\{\s*:\|\:&\s*\};:", "Fork bombs are not allowed"),
        # Additional safety patterns
        (r"\bsudo\b", "Use of 'sudo' is not allowed"),
        (r"\bsu\b", "Use of 'su' is not allowed"),
        (r"\bchown\b", "Use of 'chown' is not allowed"),
        (r"\bchmod\b", "Use of 'chmod' is not allowed"),
    ]

    for pattern, message in dangerous_patterns:
        if re.search(pattern, command):
            raise ValueError(f"Potentially dangerous command detected: {message}")


def _check_command_filters(command: str, allowed_patterns: Optional[List[str]], blocked_patterns: Optional[List[str]]) -> None:
    """
    Check command against whitelist/blacklist filters.

    Args:
        command: The command to check
        allowed_patterns: Whitelist regex patterns (if provided, command MUST match one)
        blocked_patterns: Blacklist regex patterns (command must NOT match any)

    Raises:
        ValueError: If command doesn't match whitelist or matches blacklist
    """
    # Check whitelist (if provided, command MUST match at least one pattern)
    if allowed_patterns:
        if not any(re.match(pattern, command) for pattern in allowed_patterns):
            raise ValueError(
                f"Command not in allowed list. Allowed patterns: {', '.join(allowed_patterns)}"
            )

    # Check blacklist (command must NOT match any blocked pattern)
    if blocked_patterns:
        for pattern in blocked_patterns:
            if re.match(pattern, command):
                raise ValueError(
                    f"Command matches blocked pattern: '{pattern}'"
                )


def _prepare_environment(work_dir: Path, command_prefix: Optional[str], venv_path: Optional[Path]) -> tuple[str, Dict[str, str]]:
    """
    Prepare command and environment based on virtual environment settings.

    Priority:
    1. If command_prefix is set, return it (for wrapping commands)
    2. If venv_path is set, modify PATH to use that venv
    3. Auto-detect .venv in work_dir and modify PATH
    4. Use system environment

    Args:
        work_dir: Working directory to check for .venv
        command_prefix: Optional command prefix (e.g., "uv run", "conda run -n myenv")
        venv_path: Optional custom venv path

    Returns:
        Tuple of (command_prefix, env_dict)
        - command_prefix: String to prepend to commands (or None)
        - env_dict: Environment variables dict
    """
    env = os.environ.copy()

    # Priority 1: Use explicit command prefix if provided
    if command_prefix:
        return command_prefix, env

    # Priority 2 & 3: Modify PATH for venv (custom or auto-detected)
    venv_to_use = venv_path if venv_path else (work_dir / ".venv" if (work_dir / ".venv").exists() else None)

    if venv_to_use and venv_to_use.exists():
        # Determine bin directory based on platform
        venv_bin = venv_to_use / ("Scripts" if WIN32 else "bin")
        if venv_bin.exists():
            # Prepend venv bin to PATH
            env["PATH"] = f"{venv_bin}{os.pathsep}{env['PATH']}"
            # Set VIRTUAL_ENV for tools that check it
            env["VIRTUAL_ENV"] = str(venv_to_use)

    return None, env


async def create_server() -> fastmcp.FastMCP:
    """Factory function to create and configure the code execution server."""

    parser = argparse.ArgumentParser(description="Code Execution MCP Server")
    parser.add_argument(
        "--allowed-paths",
        type=str,
        nargs="*",
        default=[],
        help="List of allowed base paths for execution (default: no restrictions)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Default timeout in seconds (default: 60)",
    )
    parser.add_argument(
        "--max-output-size",
        type=int,
        default=1024 * 1024,  # 1MB
        help="Maximum output size in bytes (default: 1MB)",
    )
    parser.add_argument(
        "--allowed-commands",
        type=str,
        nargs="*",
        default=None,
        help="Whitelist: Only allow commands matching these regex patterns (e.g., 'python .*', 'pytest .*')",
    )
    parser.add_argument(
        "--blocked-commands",
        type=str,
        nargs="*",
        default=None,
        help="Blacklist: Block commands matching these regex patterns (e.g., 'rm .*', 'sudo .*')",
    )
    parser.add_argument(
        "--command-prefix",
        type=str,
        default=None,
        help="Command prefix to prepend (e.g., 'uv run', 'conda run -n myenv', 'poetry run')",
    )
    parser.add_argument(
        "--venv-path",
        type=str,
        default=None,
        help="Path to virtual environment (will modify PATH to use this venv)",
    )
    args = parser.parse_args()

    # Create the FastMCP server
    mcp = fastmcp.FastMCP("Command Execution")

    # Store configuration
    mcp.allowed_paths = [Path(p).resolve() for p in args.allowed_paths]
    mcp.default_timeout = args.timeout
    mcp.max_output_size = args.max_output_size
    mcp.allowed_commands = args.allowed_commands  # Whitelist patterns
    mcp.blocked_commands = args.blocked_commands  # Blacklist patterns
    mcp.command_prefix = args.command_prefix  # Command prefix (e.g., "uv run")
    mcp.venv_path = Path(args.venv_path).resolve() if args.venv_path else None  # Custom venv path

    @mcp.tool()
    def execute_command(
        command: str,
        timeout: Optional[int] = None,
        work_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute a command line command.

        This tool allows executing any command line program including:
        - Python: execute_command("python script.py")
        - Node.js: execute_command("node app.js")
        - Tests: execute_command("pytest tests/")
        - Build tools: execute_command("npm run build")
        - Shell commands: execute_command("ls -la")

        The command is executed in a shell environment, so you can use shell features
        like pipes, redirection, and environment variables. On Windows, this uses
        cmd.exe; on Unix/Mac, this uses the default shell (typically bash).

        Args:
            command: The command to execute (required)
            timeout: Maximum execution time in seconds (default: 60)
                    Set to None for no timeout (use with caution)
            work_dir: Working directory for execution (relative to workspace)
                     If not specified, uses the current workspace directory

        Returns:
            Dictionary containing:
            - success: bool - True if exit code was 0
            - exit_code: int - Process exit code
            - stdout: str - Standard output from the command
            - stderr: str - Standard error from the command
            - execution_time: float - Time taken to execute in seconds
            - command: str - The command that was executed
            - work_dir: str - The working directory used

        Security:
            - Execution is confined to allowed paths
            - Timeout enforced to prevent infinite loops
            - Output size limited to prevent memory exhaustion
            - Basic sanitization against dangerous commands

        Examples:
            # Run Python script
            execute_command("python test.py")

            # Run tests with pytest
            execute_command("pytest tests/ -v")

            # Install package and run script
            execute_command("pip install requests && python scraper.py")

            # Check Python version
            execute_command("python --version")

            # List files
            execute_command("ls -la")  # Unix/Mac
            execute_command("dir")      # Windows
        """
        try:
            # Basic command sanitization (dangerous patterns)
            try:
                _sanitize_command(command)
            except ValueError as e:
                return {
                    "success": False,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": str(e),
                    "execution_time": 0.0,
                    "command": command,
                    "work_dir": work_dir or str(Path.cwd()),
                }

            # Check whitelist/blacklist filters
            try:
                _check_command_filters(command, mcp.allowed_commands, mcp.blocked_commands)
            except ValueError as e:
                return {
                    "success": False,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": str(e),
                    "execution_time": 0.0,
                    "command": command,
                    "work_dir": work_dir or str(Path.cwd()),
                }

            # Use default timeout if not specified
            if timeout is None:
                timeout = mcp.default_timeout

            # Resolve working directory
            if work_dir:
                if Path(work_dir).is_absolute():
                    work_path = Path(work_dir).resolve()
                else:
                    # Relative path - resolve relative to current working directory
                    work_path = (Path.cwd() / work_dir).resolve()
            else:
                work_path = Path.cwd()

            # Validate working directory is within allowed paths
            _validate_path_access(work_path, mcp.allowed_paths)

            # Verify working directory exists
            if not work_path.exists():
                return {
                    "success": False,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": f"Working directory does not exist: {work_path}",
                    "execution_time": 0.0,
                    "command": command,
                    "work_dir": str(work_path),
                }

            if not work_path.is_dir():
                return {
                    "success": False,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": f"Working directory is not a directory: {work_path}",
                    "execution_time": 0.0,
                    "command": command,
                    "work_dir": str(work_path),
                }

            # Prepare environment and command prefix
            cmd_prefix, env = _prepare_environment(work_path, mcp.command_prefix, mcp.venv_path)

            # Apply command prefix if specified (e.g., "uv run", "conda run -n myenv")
            final_command = f"{cmd_prefix} {command}" if cmd_prefix else command

            # Execute command
            start_time = time.time()

            try:
                result = subprocess.run(
                    final_command,
                    shell=True,
                    cwd=str(work_path),
                    timeout=timeout,
                    capture_output=True,
                    text=True,
                    env=env,
                )

                execution_time = time.time() - start_time

                # Truncate output if too large
                stdout = result.stdout
                stderr = result.stderr

                if len(stdout) > mcp.max_output_size:
                    stdout = stdout[: mcp.max_output_size] + f"\n... (truncated, exceeded {mcp.max_output_size} bytes)"

                if len(stderr) > mcp.max_output_size:
                    stderr = stderr[: mcp.max_output_size] + f"\n... (truncated, exceeded {mcp.max_output_size} bytes)"

                return {
                    "success": result.returncode == 0,
                    "exit_code": result.returncode,
                    "stdout": stdout,
                    "stderr": stderr,
                    "execution_time": execution_time,
                    "command": final_command,
                    "work_dir": str(work_path),
                }

            except subprocess.TimeoutExpired:
                execution_time = time.time() - start_time
                return {
                    "success": False,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": f"Command timed out after {timeout} seconds",
                    "execution_time": execution_time,
                    "command": command,
                    "work_dir": str(work_path),
                }

            except Exception as e:
                execution_time = time.time() - start_time
                return {
                    "success": False,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": f"Execution error: {str(e)}",
                    "execution_time": execution_time,
                    "command": command,
                    "work_dir": str(work_path),
                }

        except ValueError as e:
            # Path validation error
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Path validation error: {str(e)}",
                "execution_time": 0.0,
                "command": command,
                "work_dir": work_dir or str(Path.cwd()),
            }

        except Exception as e:
            # Unexpected error
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Unexpected error: {str(e)}",
                "execution_time": 0.0,
                "command": command,
                "work_dir": work_dir or str(Path.cwd()),
            }

    print("🚀 Command Execution MCP Server started and ready")
    print(f"Default timeout: {mcp.default_timeout}s")
    print(f"Max output size: {mcp.max_output_size} bytes")
    print(f"Allowed paths: {[str(p) for p in mcp.allowed_paths]}")

    return mcp
