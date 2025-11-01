# -*- coding: utf-8 -*-
"""
Background shell execution manager for MassGen.

Provides infrastructure for running shell commands in the background with
process management, output capture, and control capabilities.

Example usage:
    >>> manager = BackgroundShellManager()
    >>> shell_id = manager.start_shell("python train.py --epochs 100")
    >>> # Later...
    >>> status = manager.get_status(shell_id)
    >>> output = manager.get_output(shell_id)
    >>> manager.kill_shell(shell_id)
"""

import atexit
import subprocess
import threading
import time
import uuid
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..logger_config import logger


class RingBuffer:
    """Thread-safe ring buffer for output capture with size limit."""

    def __init__(self, maxlen: int = 10000):
        """Initialize ring buffer.

        Args:
            maxlen: Maximum number of lines to store (default: 10,000)
        """
        self._buffer = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def append(self, line: str) -> None:
        """Append a line to the buffer (thread-safe).

        Args:
            line: Line to append
        """
        with self._lock:
            self._buffer.append(line)

    def get_all(self) -> List[str]:
        """Get all lines from the buffer (thread-safe).

        Returns:
            List of all lines in the buffer
        """
        with self._lock:
            return list(self._buffer)

    def clear(self) -> None:
        """Clear the buffer (thread-safe)."""
        with self._lock:
            self._buffer.clear()


class BackgroundShell:
    """Represents a single background shell process."""

    def __init__(
        self,
        shell_id: str,
        command: str,
        process: subprocess.Popen,
        cwd: Optional[str] = None,
        max_output_lines: int = 10000,
    ):
        """Initialize background shell.

        Args:
            shell_id: Unique identifier for this shell
            command: Command being executed
            process: subprocess.Popen instance
            cwd: Working directory for the command
            max_output_lines: Maximum lines to buffer (default: 10,000)
        """
        self.shell_id = shell_id
        self.command = command
        self.process = process
        self.cwd = cwd
        self.start_time = datetime.now()
        self.end_time: Optional[datetime] = None
        self.exit_code: Optional[int] = None

        # Output buffers
        self.stdout_buffer = RingBuffer(maxlen=max_output_lines)
        self.stderr_buffer = RingBuffer(maxlen=max_output_lines)

        # Start output capture threads
        self._stop_capture = threading.Event()
        self._stdout_thread = threading.Thread(target=self._capture_stdout, daemon=True)
        self._stderr_thread = threading.Thread(target=self._capture_stderr, daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()

    def _capture_stdout(self) -> None:
        """Capture stdout in background thread."""
        try:
            for line in iter(self.process.stdout.readline, ""):
                if self._stop_capture.is_set():
                    break
                if line:
                    self.stdout_buffer.append(line.rstrip("\n"))
        except Exception as e:
            logger.error(f"Error capturing stdout for shell {self.shell_id}: {e}")
        finally:
            if self.process.stdout:
                self.process.stdout.close()

    def _capture_stderr(self) -> None:
        """Capture stderr in background thread."""
        try:
            for line in iter(self.process.stderr.readline, ""):
                if self._stop_capture.is_set():
                    break
                if line:
                    self.stderr_buffer.append(line.rstrip("\n"))
        except Exception as e:
            logger.error(f"Error capturing stderr for shell {self.shell_id}: {e}")
        finally:
            if self.process.stderr:
                self.process.stderr.close()

    def get_status(self) -> str:
        """Get current status of the shell.

        Returns:
            Status string: 'running', 'stopped', 'failed', or 'killed'
        """
        if self.process.poll() is None:
            return "running"
        elif self.exit_code is not None and self.exit_code < 0:
            return "killed"
        elif self.exit_code is not None and self.exit_code > 0:
            return "failed"
        else:
            return "stopped"

    def update_exit_code(self) -> Optional[int]:
        """Update and return exit code if process has finished.

        Returns:
            Exit code if process finished, None if still running
        """
        if self.exit_code is None:
            self.exit_code = self.process.poll()
            if self.exit_code is not None and self.end_time is None:
                self.end_time = datetime.now()
        return self.exit_code

    def kill(self, signal: int = subprocess.signal.SIGTERM) -> None:
        """Kill the background process.

        Args:
            signal: Signal to send (default: SIGTERM)
        """
        if self.process.poll() is None:
            try:
                self.process.send_signal(signal)
                # Wait a bit for graceful shutdown
                time.sleep(0.5)
                if self.process.poll() is None:
                    # Force kill if still running
                    self.process.kill()
                self.update_exit_code()
            except Exception as e:
                logger.error(f"Error killing shell {self.shell_id}: {e}")

    def cleanup(self) -> None:
        """Clean up resources."""
        self._stop_capture.set()
        if self.process.poll() is None:
            self.kill()
        # Daemon threads will terminate automatically, no need to wait
        # (joining can cause hangs if threads are blocked on readline)


class BackgroundShellManager:
    """Manager for background shell processes."""

    _instance: Optional["BackgroundShellManager"] = None
    _lock = threading.RLock()

    def __new__(cls):
        """Singleton pattern to ensure single manager instance."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        """Initialize the background shell manager."""
        if self._initialized:
            return

        self._shells: Dict[str, BackgroundShell] = {}
        self._shells_lock = threading.RLock()
        self._max_concurrent = 10  # Default max concurrent shells
        self._max_output_lines = 10000  # Default max output lines per shell

        # Register cleanup on exit
        atexit.register(self.cleanup_all)

        self._initialized = True
        logger.info("BackgroundShellManager initialized")

    def start_shell(
        self,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> str:
        """Start a command in the background.

        Args:
            command: Command to execute
            cwd: Working directory (default: current directory)
            env: Environment variables (default: inherit from parent)

        Returns:
            shell_id: Unique identifier for this shell

        Raises:
            RuntimeError: If max concurrent shells limit is reached
        """
        with self._shells_lock:
            # Check concurrent limit
            active_shells = sum(1 for s in self._shells.values() if s.get_status() == "running")
            if active_shells >= self._max_concurrent:
                raise RuntimeError(f"Maximum concurrent shells ({self._max_concurrent}) reached")

            # Generate unique shell ID
            shell_id = f"shell_{uuid.uuid4().hex[:8]}"

            # Start process
            process = subprocess.Popen(
                command,
                shell=True,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
            )

            # Create background shell
            bg_shell = BackgroundShell(
                shell_id=shell_id,
                command=command,
                process=process,
                cwd=cwd,
                max_output_lines=self._max_output_lines,
            )

            self._shells[shell_id] = bg_shell

            logger.info(
                f"Started background shell {shell_id}: {command[:100]}{'...' if len(command) > 100 else ''}",
            )

            return shell_id

    def get_output(self, shell_id: str) -> Dict[str, Any]:
        """Get output from a background shell.

        Args:
            shell_id: Shell identifier

        Returns:
            Dictionary with stdout, stderr, and status

        Raises:
            KeyError: If shell_id not found
        """
        with self._shells_lock:
            if shell_id not in self._shells:
                raise KeyError(f"Shell {shell_id} not found")

            bg_shell = self._shells[shell_id]
            bg_shell.update_exit_code()

            return {
                "shell_id": shell_id,
                "stdout": "\n".join(bg_shell.stdout_buffer.get_all()),
                "stderr": "\n".join(bg_shell.stderr_buffer.get_all()),
                "status": bg_shell.get_status(),
                "exit_code": bg_shell.exit_code,
            }

    def get_status(self, shell_id: str) -> Dict[str, Any]:
        """Get status of a background shell.

        Args:
            shell_id: Shell identifier

        Returns:
            Dictionary with status information

        Raises:
            KeyError: If shell_id not found
        """
        with self._shells_lock:
            if shell_id not in self._shells:
                raise KeyError(f"Shell {shell_id} not found")

            bg_shell = self._shells[shell_id]
            bg_shell.update_exit_code()

            duration = None
            if bg_shell.end_time:
                duration = (bg_shell.end_time - bg_shell.start_time).total_seconds()
            else:
                duration = (datetime.now() - bg_shell.start_time).total_seconds()

            return {
                "shell_id": shell_id,
                "status": bg_shell.get_status(),
                "exit_code": bg_shell.exit_code,
                "pid": bg_shell.process.pid,
                "command": bg_shell.command,
                "cwd": bg_shell.cwd,
                "start_time": bg_shell.start_time.isoformat(),
                "duration_seconds": round(duration, 2),
            }

    def kill_shell(self, shell_id: str) -> Dict[str, Any]:
        """Kill a background shell.

        Args:
            shell_id: Shell identifier

        Returns:
            Dictionary with kill result

        Raises:
            KeyError: If shell_id not found
        """
        with self._shells_lock:
            if shell_id not in self._shells:
                raise KeyError(f"Shell {shell_id} not found")

            bg_shell = self._shells[shell_id]

            if bg_shell.get_status() == "running":
                bg_shell.kill()
                logger.info(f"Killed background shell {shell_id}")
                return {
                    "shell_id": shell_id,
                    "status": "killed",
                    "signal": "SIGTERM",
                }
            else:
                return {
                    "shell_id": shell_id,
                    "status": bg_shell.get_status(),
                    "signal": None,
                    "message": "Process already terminated",
                }

    def list_shells(self) -> List[Dict[str, Any]]:
        """List all background shells.

        Returns:
            List of shell status dictionaries
        """
        with self._shells_lock:
            return [self.get_status(shell_id) for shell_id in self._shells.keys()]

    def cleanup_all(self) -> None:
        """Clean up all background shells (called on exit)."""
        logger.info("Cleaning up all background shells...")
        with self._shells_lock:
            for shell_id in list(self._shells.keys()):
                try:
                    bg_shell = self._shells[shell_id]
                    bg_shell.cleanup()
                except Exception as e:
                    logger.error(f"Error cleaning up shell {shell_id}: {e}")
        logger.info("Background shell cleanup complete")

    @classmethod
    def reset_for_testing(cls) -> None:
        """Reset the singleton for testing purposes.

        WARNING: Only use in tests! This force-resets the singleton by
        cleaning up all shells and resetting the instance.
        """
        with cls._lock:
            if cls._instance is not None:
                try:
                    cls._instance.cleanup_all()
                    cls._instance._shells.clear()
                except Exception as e:
                    logger.error(f"Error during testing reset: {e}")
                # Don't reset _instance itself - just clean the state
                cls._instance._initialized = True


# Convenience functions for easy import
def start_shell(command: str, cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None) -> str:
    """Start a command in the background.

    Args:
        command: Command to execute
        cwd: Working directory (default: current directory)
        env: Environment variables (default: inherit from parent)

    Returns:
        shell_id: Unique identifier for this shell
    """
    manager = BackgroundShellManager()
    return manager.start_shell(command, cwd=cwd, env=env)


def get_shell_output(shell_id: str) -> Dict[str, Any]:
    """Get output from a background shell.

    Args:
        shell_id: Shell identifier

    Returns:
        Dictionary with stdout, stderr, and status
    """
    manager = BackgroundShellManager()
    return manager.get_output(shell_id)


def get_shell_status(shell_id: str) -> Dict[str, Any]:
    """Get status of a background shell.

    Args:
        shell_id: Shell identifier

    Returns:
        Dictionary with status information
    """
    manager = BackgroundShellManager()
    return manager.get_status(shell_id)


def kill_shell(shell_id: str) -> Dict[str, Any]:
    """Kill a background shell.

    Args:
        shell_id: Shell identifier

    Returns:
        Dictionary with kill result
    """
    manager = BackgroundShellManager()
    return manager.kill_shell(shell_id)


def list_shells() -> List[Dict[str, Any]]:
    """List all background shells.

    Returns:
        List of shell status dictionaries
    """
    manager = BackgroundShellManager()
    return manager.list_shells()
