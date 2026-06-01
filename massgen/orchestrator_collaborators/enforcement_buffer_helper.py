"""Streaming-buffer helpers for the enforcement-retry path.

Two small helpers used by the orchestrator's streaming loop to capture and
truncate per-agent streaming buffer content before re-issuing an enforcement
retry. Kept on the orchestrator as thin delegators since the streaming loop
references them directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from massgen.chat_agent import ChatAgent
    from massgen.orchestrator import Orchestrator


class EnforcementBufferHelper:
    """Capture + truncate streaming buffer content for enforcement retries."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    @staticmethod
    def get_buffer_content(agent: ChatAgent) -> tuple[str | None, int]:
        """Get streaming buffer content from agent backend for enforcement tracking.

        Returns ``(buffer_preview, buffer_chars)`` — preview is the first 500
        chars (or ``None`` when the backend doesn't expose a buffer), and
        ``buffer_chars`` is the total length.
        """
        buffer_content: str | None = None
        buffer_chars = 0

        if hasattr(agent.backend, "_get_streaming_buffer"):
            buffer_content = agent.backend._get_streaming_buffer()
            if buffer_content:
                buffer_chars = len(buffer_content)
                buffer_content = buffer_content[:500] if len(buffer_content) > 500 else buffer_content

        return buffer_content, buffer_chars

    def truncate_enforcement_buffer_content(self, buffer_content: str | None) -> str | None:
        """Bound enforcement retry buffer size to avoid prompt blowups."""
        if not buffer_content:
            return None

        normalized = buffer_content.strip()
        if not normalized:
            return None

        max_chars = self._orchestrator._ENFORCEMENT_RETRY_BUFFER_MAX_CHARS
        if len(normalized) <= max_chars:
            return normalized

        kept = normalized[:max_chars]
        removed = len(normalized) - len(kept)
        return f"[... earlier retry context truncated ({removed} chars removed); " f"showing first {len(kept)} chars ...]\n" f"{kept}"
