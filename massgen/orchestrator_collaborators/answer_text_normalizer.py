"""Answer text normalization and novelty checks, extracted from Orchestrator.

PRESERVE BEHAVIOR EXACTLY -- the jaccard/novelty heuristics are intentionally
left untouched during this extraction.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

from massgen.logger_config import logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class AnswerTextNormalizer:
    """Normalize answer payloads/workspace paths and run novelty checks.

    Reads ``agents``, ``coordination_tracker``, and ``config`` via the
    orchestrator back-reference. ``coerce_answer_content_to_text`` is a
    staticmethod so it can be called without an orchestrator instance (it is
    also exposed as ``Orchestrator._coerce_answer_content_to_text``).
    """

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    @staticmethod
    def coerce_answer_content_to_text(content: Any) -> str:
        """Normalize heterogeneous answer payloads into plain text."""
        if content is None:
            return ""

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts = [AnswerTextNormalizer.coerce_answer_content_to_text(item).strip() for item in content]
            return "\n".join(part for part in parts if part)

        if isinstance(content, dict):
            for key in (
                "content",
                "description",
                "text",
                "message",
                "answer",
                "final_answer",
                "summary",
                "output",
            ):
                if key not in content:
                    continue
                text = AnswerTextNormalizer.coerce_answer_content_to_text(content.get(key)).strip()
                if text:
                    return text

            title = AnswerTextNormalizer.coerce_answer_content_to_text(content.get("title")).strip()
            if title:
                return title

            try:
                return json.dumps(content, ensure_ascii=False, sort_keys=True)
            except TypeError:
                return str(content)

        return str(content)

    def normalize_workspace_paths_in_answers(
        self,
        answers: dict[str, Any],
        viewing_agent_id: str | None = None,
    ) -> dict[str, str]:
        """Normalize absolute workspace paths in agent answers to accessible temporary workspace paths."""
        orchestrator = self._orchestrator
        normalized_answers = {}

        # Get viewing agent's temporary workspace path for context sharing (full absolute path)
        temp_workspace_base = None
        if viewing_agent_id:
            viewing_agent = orchestrator.agents.get(viewing_agent_id)
            if viewing_agent and viewing_agent.backend.filesystem_manager:
                temp_workspace_base = str(
                    viewing_agent.backend.filesystem_manager.agent_temporary_workspace,
                )
        # Create anonymous agent mapping for consistent directory names
        agent_mapping = orchestrator.coordination_tracker.get_reverse_agent_mapping()

        for agent_id, answer in answers.items():
            normalized_answer = self.coerce_answer_content_to_text(answer)

            # Replace all workspace paths found in the answer with accessible paths
            for other_agent_id, other_agent in orchestrator.agents.items():
                if not other_agent.backend.filesystem_manager:
                    continue

                anon_agent_id = agent_mapping.get(
                    other_agent_id,
                    other_agent_id,
                )
                replace_path = os.path.join(temp_workspace_base, anon_agent_id) if temp_workspace_base else anon_agent_id
                other_workspace = str(
                    other_agent.backend.filesystem_manager.get_current_workspace(),
                )
                # C2: use loguru brace-style deferred formatting instead of eager
                # f-strings. These logs interpolate the full answer body on every
                # (answer x agent) pair; with f-strings Python builds the multi-KB
                # string even when no DEBUG sink is attached. With brace args, loguru
                # only formats when a handler actually accepts the record.
                logger.debug(
                    "[Orchestrator._normalize_workspace_paths_in_answers] Replacing {} in answer from {} with path {}. original answer: {}",
                    other_workspace,
                    agent_id,
                    replace_path,
                    normalized_answer,
                )
                normalized_answer = normalized_answer.replace(
                    other_workspace,
                    replace_path,
                )
                logger.debug(
                    "[Orchestrator._normalize_workspace_paths_in_answers] Intermediate normalized answer: {}",
                    normalized_answer,
                )

            normalized_answers[agent_id] = normalized_answer

        return normalized_answers

    def normalize_workspace_paths_for_comparison(
        self,
        content: Any,
        replacement_path: str = "/workspace",
    ) -> str:
        """Normalize all workspace paths in content to a canonical form for equality comparison."""
        normalized_content = self.coerce_answer_content_to_text(content)

        # Replace all agent workspace paths with canonical '/workspace/'
        for _, agent in self._orchestrator.agents.items():
            if not agent.backend.filesystem_manager:
                continue

            # Get this agent's workspace path
            workspace_path = str(
                agent.backend.filesystem_manager.get_current_workspace(),
            )
            normalized_content = normalized_content.replace(
                workspace_path,
                replacement_path,
            )

        return normalized_content

    def calculate_jaccard_similarity(self, text1: str, text2: str) -> float:
        """Calculate Jaccard similarity between two texts based on word tokens."""
        # Tokenize and normalize - simple word-based approach
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 and not words2:
            return 1.0  # Both empty, consider identical
        if not words1 or not words2:
            return 0.0  # One empty, one not

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    def check_answer_novelty(
        self,
        new_answer: Any,
        existing_answers: dict[str, Any],
    ) -> tuple[bool, str | None]:
        """Check if a new answer is sufficiently different from existing answers."""
        orchestrator = self._orchestrator
        # Lenient mode: no checks (current behavior)
        if orchestrator.config.answer_novelty_requirement == "lenient":
            return (True, None)

        # Determine threshold based on setting
        is_decomposition = getattr(orchestrator.config, "coordination_mode", "voting") == "decomposition"
        terminal_action = "call `stop`" if is_decomposition else "vote for an existing answer"
        if orchestrator.config.answer_novelty_requirement == "strict":
            threshold = 0.50  # Reject if >50% overlap (strict)
            error_msg = f"Your answer is too similar to existing answers (>50% overlap). Please use a fundamentally different approach, employ different tools/techniques, or {terminal_action}."
        else:  # balanced
            threshold = 0.70  # Reject if >70% overlap (balanced)
            error_msg = (
                f"Your answer is too similar to existing answers (>70% overlap). "
                f"Please provide a meaningfully different solution with new insights, "
                f"approaches, or tools, or {terminal_action}."
            )

        normalized_new_answer = self.coerce_answer_content_to_text(new_answer)

        # Check similarity against all existing answers
        for agent_id, existing_answer in existing_answers.items():
            similarity = self.calculate_jaccard_similarity(
                normalized_new_answer,
                self.coerce_answer_content_to_text(existing_answer),
            )
            if similarity > threshold:
                logger.info(
                    f"[Orchestrator] Answer rejected: {similarity:.2%} similar to {agent_id}'s answer (threshold: {threshold:.0%})",
                )
                return (False, error_msg)

        # Answer is sufficiently novel
        return (True, None)
