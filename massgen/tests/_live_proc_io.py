"""Non-blocking stdout reading for live subprocess tests.

The live steering/interrupt-resume tests poll a child process's stdout inside a
``while time.time() < deadline`` loop. A plain blocking ``proc.stdout.readline()``
defeats that guard: if the child buffers output or stops emitting newlines,
``readline()`` blocks indefinitely and the deadline is never re-checked, so the
test hangs instead of failing.

These helpers make the stream non-blocking and surface "no line available right
now" as an empty string (matching ``readline()``'s EOF return), so the caller's
existing ``if not line:`` branch handles both no-data-yet and EOF — and the loop
always loops back to re-check the deadline.
"""

from __future__ import annotations

import os
from typing import IO


def set_nonblocking(stream: IO[str] | None) -> None:
    """Put ``stream``'s underlying fd in non-blocking mode (best effort)."""
    if stream is None:
        return
    try:
        os.set_blocking(stream.fileno(), False)
    except (OSError, ValueError):
        # No fileno (e.g. a mock) or unsupported platform — leave as-is; the
        # caller's deadline still bounds the loop, just less tightly.
        pass


def read_line_nonblocking(stream: IO[str] | None) -> str:
    """Read one line without blocking.

    Returns the line (including its trailing newline) when one is available,
    or ``""`` when there is nothing to read *right now* OR at EOF. The caller
    disambiguates EOF from "not yet" via ``proc.poll()`` — same as it already
    did for blocking ``readline()``'s ``""`` return.
    """
    if stream is None:
        return ""
    try:
        line = stream.readline()
    except BlockingIOError:
        return ""
    # A non-blocking text stream with no complete line may yield None rather
    # than raising; normalize to "" so callers never see a non-str.
    return line if line is not None else ""
