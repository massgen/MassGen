"""Persona generation and injection, extracted from Orchestrator.

This collaborator owns the ``_generated_personas`` mapping and provides the
methods that generate, retrieve, and persist personas. The Orchestrator keeps
thin delegator methods so all existing call sites (including monkeypatches in
tests) continue to work unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from massgen.logger_config import logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class PersonaInjector:
    """Owns persona generation, lookup, and log persistence.

    Mutates ``self._orchestrator._generated_personas`` to preserve the single
    source of truth on the orchestrator. Cross-method calls route through the
    orchestrator so test monkeypatches (e.g. of ``_generate_and_inject_personas``
    or ``_save_personas_to_log``) remain effective.
    """

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    async def generate_and_inject_personas(self) -> None:
        """Generate diverse personas for all agents and inject into their system messages."""
        orch = self._orchestrator
        if not hasattr(orch.config, "coordination_config"):
            return
        if not hasattr(orch.config.coordination_config, "persona_generator"):
            return
        if not orch.config.coordination_config.persona_generator.enabled:
            logger.info("[Orchestrator] Persona generation disabled in config")
            return
        if orch._personas_generated:
            logger.info("[Orchestrator] Personas already generated, skipping")
            return

        logger.info(
            f"[Orchestrator] Generating personas for {len(orch.agents)} agents via subagent",
        )

        display = getattr(orch.coordination_ui, "display", None) if orch.coordination_ui else None
        anchor_agent = next(iter(orch.agents.keys()), None)
        call_id = "persona_generation_persona_generation"

        try:
            pg_config = orch.config.coordination_config.persona_generator
            # Lazy lookup via the orchestrator module so test patches of
            # ``massgen.orchestrator.PersonaGenerator`` continue to apply.
            from massgen import orchestrator as _orch_mod

            generator = _orch_mod.PersonaGenerator(
                guidelines=pg_config.persona_guidelines,
                diversity_mode=pg_config.diversity_mode,
            )

            existing_messages = {}
            for agent_id, agent in orch.agents.items():
                if hasattr(agent, "get_configurable_system_message"):
                    existing_messages[agent_id] = agent.get_configurable_system_message()
                else:
                    existing_messages[agent_id] = None

            personas = await generator.generate_personas_via_subagent(
                agent_ids=list(orch.agents.keys()),
                task=orch.current_task or "Complete the assigned task",
                existing_system_messages=existing_messages,
                parent_agent_configs=orch._build_parent_agent_configs(),
                parent_workspace=orch._get_parent_workspace("massgen_persona_"),
                orchestrator_id=orch.orchestrator_id,
                log_directory=orch._get_log_directory(),
                on_subagent_started=orch._make_precollab_started_callback(
                    anchor_agent,
                    call_id,
                    display,
                ),
                voting_sensitivity=getattr(orch.config, "voting_sensitivity", None),
                voting_threshold=orch._get_pre_collab_voting_threshold(),
                has_planning_spec_context=bool(orch._plan_session_id),
                fast_iteration_mode=orch._get_fast_iteration_mode(),
            )

            source = getattr(generator, "last_generation_source", "unknown")

            # Build preview from personas
            preview_entries: list[str] = []
            for aid, persona in personas.items():
                summary = persona.attributes.get(
                    "approach_summary",
                    persona.attributes.get("thinking_style", ""),
                )
                if summary:
                    preview_entries.append(f"{aid}: {summary}")
                if len(preview_entries) >= 2:
                    break
            preview = " | ".join(preview_entries)[:400]

            if source == "subagent":
                orch._notify_precollab_completed(
                    anchor_agent,
                    "persona_generation",
                    call_id,
                    display,
                    answer_preview=preview or "Personas generated successfully.",
                )
            else:
                orch._notify_precollab_completed(
                    anchor_agent,
                    "persona_generation",
                    call_id,
                    display,
                    status="failed",
                    error="Used fallback personas.",
                )

            orch._generated_personas = personas
            orch._original_system_messages = existing_messages
            orch._personas_generated = True

            for agent_id, persona in personas.items():
                approach = persona.attributes.get(
                    "approach_summary",
                    persona.attributes.get("thinking_style", "unknown"),
                )
                logger.info(
                    f"[Orchestrator] Generated persona for {agent_id}: {approach}",
                )

            # Route through orchestrator so monkeypatches of
            # ``_save_personas_to_log`` are honored.
            orch._save_personas_to_log(personas)
            logger.info(
                f"[Orchestrator] Successfully generated and injected {len(personas)} personas",
            )

        except Exception as e:
            logger.error(f"[Orchestrator] Failed to generate personas: {e}")
            logger.warning("[Orchestrator] Continuing without persona generation")
            orch._notify_precollab_completed(
                anchor_agent,
                "persona_generation",
                call_id,
                display,
                status="failed",
                error=str(e),
            )
            orch._personas_generated = True  # Don't retry on failure

    def get_persona_for_agent(
        self,
        agent_id: str,
        has_peer_answers: bool,
    ) -> str | None:
        """Get the appropriate persona text for an agent based on phase."""
        orch = self._orchestrator
        if not orch._generated_personas:
            return None

        persona = orch._generated_personas.get(agent_id)
        if not persona:
            return None

        if has_peer_answers:
            mode = orch.config.coordination_config.persona_generator.after_first_answer
            if mode == "drop":
                return None
            elif mode == "keep":
                return persona.persona_text
            else:  # "soften"
                return persona.get_softened_text()
        else:
            # Exploration phase - always use strong perspective
            return persona.persona_text

    def get_generated_personas(self) -> dict[str, Any]:
        """Get the generated personas for persistence across turns."""
        return self._orchestrator._generated_personas

    def save_personas_to_log(self, personas: dict[str, Any]) -> None:
        """Save generated personas to a YAML file in the log directory."""
        try:
            import yaml

            # Lazy lookup so test patches of
            # ``massgen.orchestrator.get_log_session_dir`` apply.
            from massgen import orchestrator as _orch_mod

            log_dir = _orch_mod.get_log_session_dir()
            personas_file = log_dir / "generated_personas.yaml"

            personas_data = {}
            for agent_id, persona in personas.items():
                personas_data[agent_id] = {
                    "persona_text": persona.persona_text,
                    "attributes": persona.attributes,
                }

            with open(personas_file, "w") as f:
                yaml.dump(personas_data, f, default_flow_style=False, sort_keys=False)

            logger.info(f"[Orchestrator] Saved personas to {personas_file}")

        except Exception as e:
            logger.warning(f"[Orchestrator] Failed to save personas to log: {e}")
