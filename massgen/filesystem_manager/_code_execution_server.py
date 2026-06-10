#!/usr/bin/env python3
"""
Code Execution MCP Server for MassGen

This MCP server provides command line execution capabilities for agents, allowing
them to run tests, execute scripts, and perform other command-line operations.

Tools provided:
- execute_command: Execute any command line command with timeout and working directory control

Inspired by AG2's LocalCommandLineCodeExecutor sanitization patterns.
"""

import argparse
import concurrent.futures
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import fastmcp

# Logging
from massgen.logger_config import logger

# Platform detection
WIN32 = sys.platform == "win32"

# Docker integration (optional)
try:
    import docker
    from docker.errors import DockerException

    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    docker = None  # type: ignore
    DockerException = Exception  # type: ignore


def _validate_path_access(path: Path, allowed_paths: list[Path]) -> None:
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


def _sanitize_command(command: str, enable_sudo: bool = False) -> None:
    """
    Sanitize the command to prevent dangerous operations.

    Adapted from AG2's LocalCommandLineCodeExecutor.sanitize_command().
    This provides basic protection for users running commands outside Docker.

    Args:
        command: The command to sanitize
        enable_sudo: Whether sudo is enabled (in Docker mode with sudo variant)

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
    ]

    # Only check these patterns if sudo is NOT enabled
    # When sudo is enabled (Docker mode with sudo variant), these are safe
    if not enable_sudo:
        dangerous_patterns.extend(
            [
                (r"\bsudo\b", "Use of 'sudo' is not allowed"),
                (r"\bsu\b", "Use of 'su' is not allowed"),
                (r"\bchown\b", "Use of 'chown' is not allowed"),
                (r"\bchmod\b", "Use of 'chmod' is not allowed"),
            ],
        )

    for pattern, message in dangerous_patterns:
        if re.search(pattern, command):
            raise ValueError(f"Potentially dangerous command detected: {message}")


def _check_command_filters(command: str, allowed_patterns: list[str] | None, blocked_patterns: list[str] | None) -> None:
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
                f"Command not in allowed list. Allowed patterns: {', '.join(allowed_patterns)}",
            )

    # Check blacklist (command must NOT match any blocked pattern)
    if blocked_patterns:
        for pattern in blocked_patterns:
            if re.match(pattern, command):
                raise ValueError(
                    f"Command matches blocked pattern: '{pattern}'",
                )


def _prepare_environment(work_dir: Path, local_skills_directory: str | None = None) -> dict[str, str]:
    """
    Prepare environment by auto-detecting .venv in work_dir and setting up skills.

    This function checks for a .venv directory in the working directory and
    automatically modifies PATH to use it if found. Each workspace manages
    its own virtual environment independently.

    For local mode with skills enabled, this creates a .agent/skills symlink in the
    workspace directory pointing to the merged skills directory, allowing openskills
    to discover skills in the standard location.

    Args:
        work_dir: Working directory to check for .venv
        local_skills_directory: Path to merged skills directory (for local mode with skills)

    Returns:
        Environment variables dict with PATH modified as needed
    """

    env = os.environ.copy()

    # Auto-detect .venv in work_dir
    venv_dir = work_dir / ".venv"
    if venv_dir.exists():
        # Determine bin directory based on platform
        venv_bin = venv_dir / ("Scripts" if WIN32 else "bin")
        if venv_bin.exists():
            # Prepend venv bin to PATH
            env["PATH"] = f"{venv_bin}{os.pathsep}{env['PATH']}"
            # Set VIRTUAL_ENV for tools that check it
            env["VIRTUAL_ENV"] = str(venv_dir)

    # Setup skills directory for local mode
    # Create .agent/skills symlink (or copy on Windows) in workspace so openskills can find skills
    if local_skills_directory:
        import shutil

        logger.info(f"[CodeExecution] Setting up skills for local mode, skills_directory: {local_skills_directory}")
        skills_path = Path(local_skills_directory)
        if skills_path.exists():
            # Create .agent directory in workspace
            agent_dir = work_dir / ".agent"
            agent_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"[CodeExecution] Created .agent directory in workspace: {agent_dir}")

            # Create symlink to merged skills directory
            # openskills looks for .agent/skills/ relative to current directory first
            skills_link = agent_dir / "skills"

            # Remove existing symlink/directory if present
            if skills_link.exists() or skills_link.is_symlink():
                if skills_link.is_symlink():
                    skills_link.unlink()
                    logger.info(f"[CodeExecution] Removed existing skills symlink: {skills_link}")
                elif skills_link.is_dir():
                    # Remove directory (could be from previous copy fallback)
                    shutil.rmtree(skills_link)
                    logger.info(f"[CodeExecution] Removed existing skills directory: {skills_link}")

            # Create symlink to merged skills directory
            if not skills_link.exists():
                # Try symlink first (works on Unix/Mac, requires perms on Windows)
                try:
                    skills_link.symlink_to(skills_path, target_is_directory=True)
                    logger.info(f"[CodeExecution] Created skills symlink: {skills_link} -> {skills_path}")
                except (OSError, NotImplementedError) as e:
                    # Symlink failed (likely Windows without admin/dev mode)
                    # Fallback: copy directory instead
                    logger.warning(f"[CodeExecution] Symlink failed ({e}), falling back to copy")
                    try:
                        shutil.copytree(skills_path, skills_link, dirs_exist_ok=True)
                        logger.info(f"[CodeExecution] Copied skills directory: {skills_link}")
                    except Exception as copy_error:
                        logger.error(f"[CodeExecution] Failed to copy skills directory: {copy_error}")
        else:
            logger.warning(f"[CodeExecution] Skills directory does not exist: {skills_path}")

    return env


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
        "--execution-mode",
        type=str,
        default="local",
        choices=["local", "docker", "srt"],
        help="Execution mode: local (subprocess), docker (container isolation), or srt (OS-level sandbox-runtime)",
    )
    parser.add_argument(
        "--srt-settings",
        type=str,
        default=None,
        help="Path to the SRT settings JSON file (required for srt mode)",
    )
    parser.add_argument(
        "--agent-id",
        type=str,
        default=None,
        help="Agent ID (required for Docker mode to identify container)",
    )
    parser.add_argument(
        "--instance-id",
        type=str,
        default=None,
        help="Instance ID for parallel execution (appended to container name)",
    )
    parser.add_argument(
        "--enable-sudo",
        action="store_true",
        default=False,
        help="Enable sudo in Docker containers (disables sudo command sanitization checks)",
    )
    parser.add_argument(
        "--local-skills-directory",
        type=str,
        default=None,
        help="Path to merged skills directory for local mode (contains built-in and external skills)",
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
    mcp.execution_mode = args.execution_mode
    mcp.srt_settings_path = args.srt_settings
    mcp.agent_id = args.agent_id
    mcp.instance_id = args.instance_id
    mcp.enable_sudo = args.enable_sudo
    mcp.local_skills_directory = args.local_skills_directory

    # Initialize Docker client if Docker mode
    mcp.docker_client = None
    if args.execution_mode == "docker":
        if not DOCKER_AVAILABLE:
            # Use diagnostics for better error message
            try:
                from massgen.utils.docker_diagnostics import diagnose_docker

                diagnostics = diagnose_docker(check_images=False)
                error_msg = diagnostics.format_error(include_steps=True)
                if error_msg:
                    raise RuntimeError(error_msg)
            except ImportError:
                pass
            raise RuntimeError("Docker mode requested but docker library not available. Install with: pip install docker")
        # Note: agent_id validation is deferred to first command execution
        # This allows MCP server to start before agent_id is set by orchestrator

        try:
            mcp.docker_client = docker.from_env()
            mcp.docker_client.ping()  # Test connection
            print("[Docker] Connected to Docker daemon")
        except DockerException as e:
            # Use diagnostics for better error message
            try:
                from massgen.utils.docker_diagnostics import diagnose_docker

                diagnostics = diagnose_docker(check_images=False)
                error_msg = diagnostics.format_error(include_steps=True)
                if error_msg:
                    raise RuntimeError(error_msg)
            except ImportError:
                pass
            raise RuntimeError(f"Failed to connect to Docker: {e}")

    # Validate SRT mode at startup (parallel to Docker validation above).
    if args.execution_mode == "srt":
        import platform

        from massgen.filesystem_manager._srt_manager import srt_available

        if platform.system() == "Windows":
            raise RuntimeError(
                "SRT sandboxing (command_line_execution_mode: srt) is not supported on Windows. " "Use 'docker' mode or run under Linux/macOS.",
            )
        if not args.srt_settings:
            raise RuntimeError("SRT mode requires --srt-settings <path>. This should be configured by the orchestrator.")
        if not Path(args.srt_settings).exists():
            raise RuntimeError(f"SRT settings file not found: {args.srt_settings}")
        if not srt_available():
            raise RuntimeError(
                "SRT mode requested but the 'srt' CLI was not found on PATH. " "Install it with: npm install -g @anthropic-ai/sandbox-runtime",
            )
        print(f"[SRT] Sandbox-runtime enabled (settings: {args.srt_settings})")

    @mcp.tool()
    def execute_command(
        command: str,
        timeout: int | None = None,
        work_dir: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute a command line command.

        This tool blocks until the command completes or times out (default: 60s).
        For long-running work, use the framework-level background tool management
        helpers to schedule execute_command asynchronously.

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
                _sanitize_command(command, enable_sudo=mcp.enable_sudo)
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

            # Execute command based on execution mode
            if mcp.execution_mode == "docker":
                # Docker mode: execute in container via Docker client
                if not mcp.docker_client:
                    return {
                        "success": False,
                        "exit_code": -1,
                        "stdout": "",
                        "stderr": "Docker mode enabled but docker_client not initialized",
                        "execution_time": 0.0,
                        "command": command,
                        "work_dir": str(work_path),
                    }

                # Validate agent_id is set before executing
                if not mcp.agent_id:
                    return {
                        "success": False,
                        "exit_code": -1,
                        "stdout": "",
                        "stderr": "Docker mode requires agent_id to be set. This should be configured by the orchestrator.",
                        "execution_time": 0.0,
                        "command": command,
                        "work_dir": str(work_path),
                    }

                try:
                    # Get container by name (include instance_id if set for parallel execution)
                    if mcp.instance_id:
                        container_name = f"massgen-{mcp.agent_id}-{mcp.instance_id}"
                    else:
                        container_name = f"massgen-{mcp.agent_id}"
                    container = mcp.docker_client.containers.get(container_name)

                    # IMPORTANT: Use host paths directly in container
                    # Container mounts are configured to use the SAME paths as host
                    # This makes Docker completely transparent to the LLM

                    # Execute command via docker exec
                    exec_config = {
                        "cmd": ["/bin/sh", "-c", command],
                        "workdir": str(work_path),  # Use host path directly
                        "stdout": True,
                        "stderr": True,
                    }

                    start_time = time.time()

                    # Use ThreadPoolExecutor to implement timeout for Docker exec_run
                    # Docker SDK's exec_run doesn't have native timeout support
                    # IMPORTANT: Don't use context manager - its __exit__ calls shutdown(wait=True)
                    # which blocks until the thread completes, defeating the timeout
                    def run_docker_exec():
                        return container.exec_run(**exec_config)

                    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                    future = executor.submit(run_docker_exec)
                    try:
                        exit_code, output = future.result(timeout=timeout)
                    except concurrent.futures.TimeoutError:
                        # Timeout occurred - shutdown executor without waiting
                        executor.shutdown(wait=False, cancel_futures=True)
                        execution_time = time.time() - start_time
                        logger.warning(f"Docker command timed out after {timeout}s: {command[:100]}")
                        return {
                            "success": False,
                            "exit_code": -1,
                            "stdout": "",
                            "stderr": f"Command timed out after {timeout} seconds",
                            "execution_time": execution_time,
                            "command": command,
                            "work_dir": str(work_path),
                        }
                    finally:
                        # Clean up executor (wait=False to not block if thread is still running)
                        executor.shutdown(wait=False)

                    execution_time = time.time() - start_time

                    # Docker exec_run combines stdout and stderr
                    output_str = output.decode("utf-8") if isinstance(output, bytes) else output

                    # Truncate output if too large
                    if len(output_str) > mcp.max_output_size:
                        output_str = output_str[: mcp.max_output_size] + f"\n... (truncated, exceeded {mcp.max_output_size} bytes)"

                    return {
                        "success": exit_code == 0,
                        "exit_code": exit_code,
                        "stdout": output_str,
                        "stderr": "",  # Docker exec_run combines stdout/stderr
                        "execution_time": execution_time,
                        "command": command,
                        "work_dir": str(work_path),  # Return host path
                    }

                except DockerException as e:
                    return {
                        "success": False,
                        "exit_code": -1,
                        "stdout": "",
                        "stderr": f"Docker container error: {str(e)}",
                        "execution_time": 0.0,
                        "command": command,
                        "work_dir": str(work_path),
                    }
                except Exception as e:
                    return {
                        "success": False,
                        "exit_code": -1,
                        "stdout": "",
                        "stderr": f"Docker execution error: {str(e)}",
                        "execution_time": 0.0,
                        "command": command,
                        "work_dir": str(work_path),
                    }

            else:
                # Local or SRT mode: execute using subprocess (existing logic).
                # Prepare environment (auto-detects .venv in work_dir and sets up skills)
                env = _prepare_environment(work_path, mcp.local_skills_directory)

                # SRT mode wraps the command in an OS-level sandbox. The original
                # command is passed to `sh -c` INSIDE the sandbox so shell features
                # (pipes, redirection) and any spawned subprocesses are contained.
                effective_command = command
                if mcp.execution_mode == "srt":
                    from massgen.filesystem_manager._srt_manager import (
                        wrap_command_with_srt,
                    )

                    effective_command = wrap_command_with_srt(command, mcp.srt_settings_path)

                # Execute command
                start_time = time.time()

                try:
                    result = subprocess.run(
                        effective_command,
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
                        "command": command,
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

    print("Command Execution MCP Server started and ready")
    print(f"Execution mode: {mcp.execution_mode}")
    if mcp.execution_mode == "docker":
        print(f"Agent ID: {mcp.agent_id}")
        if mcp.instance_id:
            print(f"Instance ID: {mcp.instance_id}")
    print(f"Default timeout: {mcp.default_timeout}s")
    print(f"Max output size: {mcp.max_output_size} bytes")
    print(f"Allowed paths: {[str(p) for p in mcp.allowed_paths]}")

    return mcp
