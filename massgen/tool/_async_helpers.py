# -*- coding: utf-8 -*-
"""Async utility functions for wrapping different return types."""

import asyncio
from typing import AsyncGenerator, Callable, Generator, Optional

from ._result import ExecutionResult, TextContent


async def _apply_post_processing(
    result: ExecutionResult,
    processor: Optional[Callable[[ExecutionResult], Optional[ExecutionResult]]],
) -> ExecutionResult:
    """Apply post-processing to an execution result."""
    if processor:
        processed = processor(result)
        if processed:
            return processed
    return result


async def wrap_object_async(
    obj: ExecutionResult,
    processor: Optional[Callable[[ExecutionResult], Optional[ExecutionResult]]],
) -> AsyncGenerator[ExecutionResult, None]:
    """Convert a single ExecutionResult to async generator."""
    yield await _apply_post_processing(obj, processor)


async def wrap_sync_gen_async(
    sync_gen: Generator[ExecutionResult, None, None],
    processor: Optional[Callable[[ExecutionResult], Optional[ExecutionResult]]],
) -> AsyncGenerator[ExecutionResult, None]:
    """Convert sync generator to async generator."""
    for chunk in sync_gen:
        yield await _apply_post_processing(chunk, processor)


async def wrap_as_async_generator(
    async_gen: AsyncGenerator[ExecutionResult, None],
    processor: Optional[Callable[[ExecutionResult], Optional[ExecutionResult]]],
) -> AsyncGenerator[ExecutionResult, None]:
    """Wrap async generator with interruption handling."""

    previous_chunk = None
    try:
        async for chunk in async_gen:
            processed = await _apply_post_processing(chunk, processor)
            yield processed
            previous_chunk = processed

    except asyncio.CancelledError:
        interrupt_msg = TextContent(
            data="<system>Execution interrupted by user request</system>",
        )

        if previous_chunk:
            previous_chunk.output_blocks.append(interrupt_msg)
            previous_chunk.was_interrupted = True
            previous_chunk.is_final = True
            yield await _apply_post_processing(previous_chunk, processor)
        else:
            yield await _apply_post_processing(
                ExecutionResult(
                    output_blocks=[interrupt_msg],
                    was_interrupted=True,
                    is_final=True,
                ),
                processor,
            )
