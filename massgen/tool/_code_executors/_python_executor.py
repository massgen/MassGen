# -*- coding: utf-8 -*-
"""Python code execution tool implementation."""

import asyncio
import os
import sys
import tempfile
import uuid
from typing import Any

from .._result import ExecutionResult, TextContent


async def run_python_script(
    source_code: str,
    max_duration: float = 300,
    **extra_kwargs: Any,
) -> ExecutionResult:
    """Execute Python code in an isolated temporary environment.

    The code runs in a temporary file that is cleaned up after execution.
    Results must be printed to be captured in the output.

    Args:
        source_code: Python code to execute
        max_duration: Maximum execution time in seconds (default: 300)

    Returns:
        ExecutionResult containing execution status and output
    """

    with tempfile.TemporaryDirectory() as temp_workspace:
        script_file = os.path.join(temp_workspace, f"script_{uuid.uuid4().hex}.py")
        with open(script_file, "w", encoding="utf-8") as file:
            file.write(source_code)

        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-u",
            script_file,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            await asyncio.wait_for(process.wait(), timeout=max_duration)
            stdout_data, stderr_data = await process.communicate()
            stdout_text = stdout_data.decode("utf-8")
            stderr_text = stderr_data.decode("utf-8")
            exit_code = process.returncode

        except asyncio.TimeoutError:
            timeout_msg = f"TimeoutError: Execution exceeded {max_duration} seconds limit"
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
