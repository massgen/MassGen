# -*- coding: utf-8 -*-
"""Shell command execution tool implementation."""

import asyncio
from typing import Any

from .._result import ExecutionResult, TextContent


async def run_shell_script(
    shell_command: str,
    max_duration: int = 300,
    **extra_kwargs: Any,
) -> ExecutionResult:
    """Execute shell commands and capture output.

    Args:
        shell_command: Shell command to execute
        max_duration: Maximum execution time in seconds (default: 300)

    Returns:
        ExecutionResult with exit code, stdout, and stderr
    """

    process = await asyncio.create_subprocess_shell(
        shell_command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        bufsize=0,
    )

    try:
        await asyncio.wait_for(process.wait(), timeout=max_duration)
        stdout_data, stderr_data = await process.communicate()
        stdout_text = stdout_data.decode("utf-8")
        stderr_text = stderr_data.decode("utf-8")
        exit_code = process.returncode

    except asyncio.TimeoutError:
        timeout_msg = f"TimeoutError: Command execution exceeded {max_duration} seconds limit"
        exit_code = -1
        try:
            process.terminate()
            stdout_data, stderr_data = await process.communicate()
            stdout_text = stdout_data.decode("utf-8")
            stderr_text = stderr_data.decode("utf-8")
            if stderr_text:
                stderr_text += f"\n{timeout_msg}"
            else:
                stderr_text = timeout_msg
        except ProcessLookupError:
            stdout_text = ""
            stderr_text = timeout_msg

    return ExecutionResult(
        output_blocks=[
            TextContent(
                data=(f"<exit_code>{exit_code}</exit_code>" f"<stdout>{stdout_text}</stdout>" f"<stderr>{stderr_text}</stderr>"),
            ),
        ],
    )
