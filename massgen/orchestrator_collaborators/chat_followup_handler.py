"""Chat follow-up + conversation-context helpers, extracted from Orchestrator.

Two small chat-flow helpers used by the public ``chat`` entry point:

- ``handle_followup``: respond to a follow-up message after the orchestrator
  has already produced a final answer; emits a context-aware acknowledgement.
- ``build_conversation_context``: convert a list of chat messages into a
  ``{current_message, conversation_history, full_messages}`` dict.

Both go through the orchestrator back-ref for any cross-method calls so test
monkeypatches on the orchestrator instance keep working.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator
    from massgen.stream_chunk import StreamChunk


class ChatFollowupHandler:
    """Follow-up message handling + conversation-context construction."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    async def handle_followup(
        self,
        user_message: str,
        conversation_context: dict[str, Any] | None = None,
    ) -> AsyncGenerator[StreamChunk]:
        """Handle follow-up questions after presenting final answer with conversation context."""
        # Lazy lookup so tests that patch massgen.orchestrator.log_* symbols still fire.
        from massgen import orchestrator as _orch_mod
        from massgen.stream_chunk import StreamChunk

        orch = self._orchestrator

        has_irreversible = await orch._analyze_question_irreversibility(
            user_message,
            conversation_context or {},
        )

        for agent_id, agent in orch.agents.items():
            if hasattr(agent.backend, "set_planning_mode"):
                agent.backend.set_planning_mode(has_irreversible)
                _orch_mod.log_orchestrator_activity(
                    orch.orchestrator_id,
                    f"Set planning mode for {agent_id} (follow-up)",
                    {
                        "planning_mode_enabled": has_irreversible,
                        "reason": "follow-up irreversibility analysis",
                    },
                )

        if conversation_context and len(conversation_context.get("conversation_history", [])) > 0:
            msg = (
                f"🤔 Thank you for your follow-up question in our ongoing conversation. "
                f"I understand you're asking: '{user_message}'. Currently, the coordination is "
                f"complete, but I can help clarify the answer or coordinate a new task that takes "
                f"our conversation history into account."
            )
        else:
            msg = f"🤔 Thank you for your follow-up: '{user_message}'. The coordination is complete, " f"but I can help clarify the answer or coordinate a new task if needed."

        _orch_mod.log_stream_chunk("orchestrator", "content", msg)
        yield StreamChunk(type="content", content=msg)

        _orch_mod.log_stream_chunk("orchestrator", "done", None)
        yield StreamChunk(type="done")

    @staticmethod
    def build_conversation_context(
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build conversation context from message list."""
        conversation_history = []
        current_message = None

        for message in messages:
            role = message.get("role")
            content = message.get("content", "")

            if role == "user":
                current_message = content
                if len(conversation_history) > 0 or len(messages) > 1:
                    conversation_history.append(message.copy())
            elif role == "assistant":
                conversation_history.append(message.copy())
            elif role == "tool":
                conversation_history.append(message.copy())
            elif role == "system":
                pass

        if conversation_history and conversation_history[-1].get("role") == "user":
            conversation_history.pop()

        return {
            "current_message": current_message,
            "conversation_history": conversation_history,
            "full_messages": messages,
        }
