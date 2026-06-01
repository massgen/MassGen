"""Per-agent round-start context block queue, extracted from Orchestrator."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class RoundStartContextQueue:
    """Trivial per-agent string queue over the orchestrator's
    ``_round_start_context_blocks`` dict.

    Mutates the orchestrator's attribute via the back-reference (the dict is
    owned exclusively by this queue).
    """

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    def queue(self, agent_id: str, block: str) -> None:
        """Queue a context block for the next parent round."""
        normalized = str(block or "").strip()
        if not normalized:
            return
        self._orchestrator._round_start_context_blocks.setdefault(agent_id, []).append(normalized)

    def consume(self, agent_id: str) -> str | None:
        """Pop and combine queued round-start context blocks for an agent."""
        blocks = self._orchestrator._round_start_context_blocks.pop(agent_id, [])
        normalized = [str(block or "").strip() for block in blocks if str(block or "").strip()]
        if not normalized:
            return None
        return "\n\n".join(normalized)
