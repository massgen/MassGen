"""DSPy paraphrase coordination, extracted from Orchestrator."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from massgen.logger_config import log_coordination_step, logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class DspyParaphraseCoordinator:
    """Generate and assign DSPy paraphrases for the current question.

    All shared dicts (``_agent_paraphrases``, ``_evolved_prompts``,
    ``_paraphrase_generation_errors``, and ``agent_states``) are mutated via the
    orchestrator back-reference, never local copies. ``_evolved_prompts`` is
    shared with prompt-evolution code and is only reset here.
    """

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    async def prepare_paraphrases_for_agents(self, question: str) -> None:
        """Generate and assign DSPy paraphrases for the current question."""
        orchestrator = self._orchestrator

        # Reset paraphrases and evolved prompts before regenerating
        orchestrator._agent_paraphrases = {}
        orchestrator._evolved_prompts = {}
        for state in orchestrator.agent_states.values():
            state.paraphrase = None

        if not orchestrator.dspy_paraphraser:
            return

        if not question:
            return

        try:
            variants = await asyncio.to_thread(
                orchestrator.dspy_paraphraser.generate_variants,
                question,
            )
        except Exception as exc:
            orchestrator._paraphrase_generation_errors += 1
            logger.warning(f"Failed to generate DSPy paraphrases: {exc}")
            return

        if not variants:
            logger.warning(
                "DSPy paraphraser returned no variants; proceeding with original question for all agents.",
            )
            return

        agent_ids = list(orchestrator.agents.keys())
        if not agent_ids:
            return

        for idx, agent_id in enumerate(agent_ids):
            paraphrase = variants[idx % len(variants)]
            orchestrator._agent_paraphrases[agent_id] = paraphrase
            orchestrator.agent_states[agent_id].paraphrase = paraphrase

        # Log at INFO level so users know paraphrasing is active
        logger.info(
            f"DSPy paraphrasing enabled: {len(variants)} variant(s) generated and assigned to {len(agent_ids)} agent(s)",
        )
        for agent_id, paraphrase in orchestrator._agent_paraphrases.items():
            logger.info(f"  {agent_id}: {paraphrase}")

        log_coordination_step(
            "DSPy paraphrases prepared",
            {
                "variants": len(variants),
                "assigned_agents": orchestrator._agent_paraphrases,
            },
        )

    def get_paraphrase_status(self) -> dict[str, Any]:
        """Return current DSPy paraphrase assignments and metrics for observability."""
        orchestrator = self._orchestrator

        status = {
            "paraphrases": orchestrator._agent_paraphrases.copy(),
            "generation_errors": orchestrator._paraphrase_generation_errors,
            "metrics": None,
        }

        if orchestrator.dspy_paraphraser:
            try:
                status["metrics"] = orchestrator.dspy_paraphraser.get_metrics()
            except Exception as exc:  # pragma: no cover - defensive guard
                logger.debug(f"Unable to fetch DSPy paraphraser metrics: {exc}")

        return status
