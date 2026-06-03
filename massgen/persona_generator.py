"""Automatic persona generation for MassGen agents.

This module provides functionality to automatically generate diverse system
messages (personas) for MassGen agents using an LLM, increasing response
diversity without requiring users to manually craft different system messages.
"""

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic.dataclasses import dataclass as pydantic_dataclass

from massgen.structured_logging import log_persona_generation, trace_persona_generation

# Template for easing persona strength after agents see peer solutions
SOFTENED_PERSPECTIVE_TEMPLATE = """Your initial perspective was:
{persona_text}

Now that you've seen peer solutions, treat your perspective as a preference, not a position
to defend. Keep full end-to-end coverage of the task, evaluate ALL approaches objectively,
and synthesize the strongest ideas into the best overall answer."""


@dataclass
class GeneratedPersona:
    """A persona generated for an agent.

    Attributes:
        agent_id: The ID of the agent this persona is for
        persona_text: The full persona instruction text (strong, for initial exploration)
        attributes: Additional attributes describing the persona style
    """

    agent_id: str
    persona_text: str
    attributes: dict[str, str]

    def get_softened_text(self) -> str:
        """Get the eased persona text after peer answers are visible."""
        return SOFTENED_PERSPECTIVE_TEMPLATE.format(persona_text=self.persona_text)


class DiversityMode:
    """Diversity modes for persona generation."""

    PERSPECTIVE = "perspective"  # Different values/priorities, same problem
    IMPLEMENTATION = "implementation"  # Different solution types/interpretations
    METHODOLOGY = "methodology"  # Different working approaches, same problem


@pydantic_dataclass
class PersonaGeneratorConfig:
    """Configuration for automatic persona generation.

    Attributes:
        enabled: Whether persona generation is enabled
        diversity_mode: Type of diversity to generate:
            - "perspective": Different values/priorities (what to optimize for)
            - "implementation": Different solution types/interpretations (what kind of solution)
            - "methodology": Different working approaches (how to tackle the work)
        persona_guidelines: Optional custom guidelines for persona generation
        persist_across_turns: If True, reuse personas across turns in multi-turn sessions.
            If False (default), generate fresh personas each turn.
        after_first_answer: What happens to the persona after the agent submits its first answer:
            - "drop": Persona is completely removed (default). Agents synthesize freely.
            - "soften": Persona is softened to a preference, not a position to defend.
            - "keep": Persona stays at full strength for all answers.
    """

    enabled: bool = False
    diversity_mode: str = "perspective"  # "perspective" or "implementation"
    persona_guidelines: str | None = None
    persist_across_turns: bool = False  # Default: generate new personas each turn
    after_first_answer: str = "drop"  # "drop" | "soften" | "keep"

    def __post_init__(self):
        # Validate diversity_mode
        valid_modes = (DiversityMode.PERSPECTIVE, DiversityMode.IMPLEMENTATION, DiversityMode.METHODOLOGY)
        if self.diversity_mode not in valid_modes:
            self.diversity_mode = DiversityMode.PERSPECTIVE
        # Validate after_first_answer
        valid_lifecycle = ("drop", "soften", "keep")
        if self.after_first_answer not in valid_lifecycle:
            self.after_first_answer = "drop"


class PersonaGenerator:
    """Generates diverse personas for MassGen agents using an LLM.

    The generator creates complementary personas that encourage diverse
    perspectives when multiple agents tackle the same problem.

    Example:
        >>> from massgen.persona_generator import PersonaGenerator, PersonaGeneratorConfig
        >>> from massgen.cli import create_backend
        >>>
        >>> config = PersonaGeneratorConfig(
        ...     enabled=True,
        ...     backend={"type": "openai", "model": "gpt-4o-mini"},
        ...     strategy="complementary"
        ... )
        >>> backend = create_backend(**config.backend)
        >>> generator = PersonaGenerator(
        ...     backend=backend,
        ...     strategy=config.strategy,
        ...     guidelines=config.persona_guidelines
        ... )
        >>> personas = await generator.generate_personas(
        ...     agent_ids=["agent_a", "agent_b", "agent_c"],
        ...     task="Analyze this code for bugs",
        ...     existing_system_messages={}
        ... )
    """

    def __init__(
        self,
        guidelines: str | None = None,
        diversity_mode: str = "perspective",
    ):
        """Initialize the persona generator.

        Args:
            guidelines: Optional custom guidelines for persona generation
            diversity_mode: Type of diversity - "perspective" or "implementation"
        """
        self.guidelines = guidelines
        self.diversity_mode = diversity_mode
        self.last_generation_source = "unknown"

    async def generate_personas(
        self,
        agent_ids: list[str],
        task: str,
        existing_system_messages: dict[str, str | None],
    ) -> dict[str, GeneratedPersona]:
        """Generate diverse personas for all agents.

        Args:
            agent_ids: List of agent IDs to generate personas for
            task: The task/query agents will work on
            existing_system_messages: Existing system messages (to enhance, not replace)

        Returns:
            Dictionary mapping agent_id to GeneratedPersona
        """
        if not agent_ids:
            logger.warning("No agent IDs provided for persona generation")
            return {}

        prompt = self._build_generation_prompt(agent_ids, task, existing_system_messages)

        logger.info(f"Generating personas for {len(agent_ids)} agents using strategy: {self.strategy}")

        start_time = time.perf_counter()

        with trace_persona_generation(
            num_agents=len(agent_ids),
            strategy=self.strategy,
            diversity_mode=self.diversity_mode,
        ) as span:
            try:
                # Use stream_with_tools with empty tools to generate text
                response_content = await self._generate_response(prompt)
                personas = self._parse_response(response_content, agent_ids)

                # Log summary
                for agent_id, persona in personas.items():
                    style = persona.attributes.get("thinking_style", "unknown")
                    logger.debug(f"Generated persona for {agent_id}: {style}")

                generation_time_ms = (time.perf_counter() - start_time) * 1000
                span.set_attribute("persona.success", True)
                span.set_attribute("persona.generation_time_ms", generation_time_ms)

                # Log structured event
                log_persona_generation(
                    agent_ids=agent_ids,
                    strategy=self.strategy,
                    success=True,
                    generation_time_ms=generation_time_ms,
                    used_fallback=False,
                    diversity_mode=self.diversity_mode,
                )

                return personas

            except Exception as e:
                logger.error(f"Failed to generate personas: {e}")
                logger.info("Using fallback personas")

                generation_time_ms = (time.perf_counter() - start_time) * 1000
                span.set_attribute("persona.success", False)
                span.set_attribute("persona.used_fallback", True)
                span.set_attribute("persona.error", str(e))

                # Log structured event for fallback case
                log_persona_generation(
                    agent_ids=agent_ids,
                    strategy=self.strategy,
                    success=False,
                    generation_time_ms=generation_time_ms,
                    used_fallback=True,
                    diversity_mode=self.diversity_mode,
                    error_message=str(e),
                )

                return self._generate_fallback_personas(agent_ids)

    async def _generate_response(self, prompt: str) -> str:
        """Generate a response from the LLM backend.

        Args:
            prompt: The prompt to send to the LLM

        Returns:
            The generated response text
        """
        messages = [{"role": "user", "content": prompt}]

        # Collect streaming response
        response_parts = []

        # Get model from backend config, with fallback
        model = self.backend.config.get("model", "gpt-4o-mini")

        async for chunk in self.backend.stream_with_tools(messages=messages, tools=[], model=model):
            if chunk.content:
                response_parts.append(chunk.content)

        return "".join(response_parts)

    def _build_generation_prompt(
        self,
        agent_ids: list[str],
        task: str,
        existing_system_messages: dict[str, str | None],
    ) -> str:
        """Build the prompt for persona generation.

        Args:
            agent_ids: List of agent IDs
            task: The task description
            existing_system_messages: Existing system messages per agent

        Returns:
            The formatted prompt string
        """
        strategy_instructions = self._get_strategy_instructions()

        # Build agent context
        agents_context = []
        for agent_id in agent_ids:
            existing = existing_system_messages.get(agent_id)
            if existing:
                agents_context.append(f"- {agent_id}: Has existing instruction:\n{existing}")
            else:
                agents_context.append(f"- {agent_id}: No existing instruction")

        agents_list = "\n".join(agents_context)
        agent_ids_json = json.dumps(agent_ids)

        prompt = f"""Generate diverse personas for {len(agent_ids)} AI agents working collaboratively on a task.

## Task
{task}

## Agents
{agents_list}

## Strategy: {self.strategy}
{strategy_instructions}

## Guidelines
{self.guidelines or "Generate personas that encourage diverse, high-quality responses."}

## Requirements
1. Each persona should be detailed, as it will be used for a system prompt for an agent.
2. Personas should be complementary - cover different aspects/approaches
3. Include specific thinking styles, focuses, and communication patterns
4. If an agent has an existing instruction, enhance it rather than replace it
5. Make personas specific enough to influence behavior but general enough to apply to any subtask
6. **CRITICAL**: All agents must solve the ENTIRE task completely. Do NOT create
   specialized roles or divide the task into subtasks. Each agent should produce a
   complete solution to the task with their unique perspective/approach. Personas add
   diversity in HOW to solve the task, NOT which part to solve.

## Output Format
Return a JSON object with this structure:
{{
    "personas": {{
        "<agent_id>": {{
            "persona_text": "The full persona instruction text...",
            "attributes": {{
                "thinking_style": "analytical|creative|systematic|intuitive",
                "focus_area": "details|big-picture|risks|opportunities",
                "communication": "concise|thorough|example-driven|principle-based"
            }}
        }}
    }}
}}

Important: The agent_ids you must generate personas for are: {agent_ids_json}

Generate personas now:"""

        return prompt

    def _get_strategy_instructions(self) -> str:
        """Get instructions based on generation strategy.

        Returns:
            Strategy-specific instructions string
        """
        strategies = {
            "complementary": """Create personas that complement each other:
- Cover different aspects of the problem
- Use different analytical approaches
- Balance risk-awareness with innovation
- Ensure all major perspectives are represented""",
            "diverse": """Maximize diversity across personas:
- Each should have a distinctly different viewpoint
- Vary thinking styles significantly
- Include contrarian perspectives
- Embrace unconventional approaches""",
            "specialized": """Create specialized expert personas:
- Each should have deep expertise in a specific area
- Focus on different technical/domain aspects
- Provide domain-specific insights
- Reference relevant best practices and patterns""",
            "adversarial": """Create constructively adversarial personas:
- Include devil's advocate perspectives
- Challenge assumptions and proposals
- Probe for weaknesses and edge cases
- Balance criticism with constructive alternatives""",
        }
        return strategies.get(self.strategy, strategies["complementary"])

    def _parse_response(self, response: str, agent_ids: list[str]) -> dict[str, GeneratedPersona]:
        """Parse LLM response into GeneratedPersona objects.

        Tries multiple strategies to extract JSON from potentially messy output:
        1. Direct JSON parse
        2. Extract from markdown code blocks
        3. Find JSON object by locating { and } braces

        Args:
            response: The raw LLM response
            agent_ids: Expected agent IDs

        Returns:
            Dictionary mapping agent_id to GeneratedPersona
        """
        json_str = response.strip()

        # Strategy 1: Try direct parse first
        data = self._try_parse_json(json_str)

        # Strategy 2: Extract from markdown code blocks
        if data is None and "```" in json_str:
            if "```json" in json_str:
                start = json_str.find("```json") + 7
                end = json_str.find("```", start)
                if end > start:
                    data = self._try_parse_json(json_str[start:end].strip())
            if data is None:
                # Try generic code block
                start = json_str.find("```") + 3
                end = json_str.find("```", start)
                if end > start:
                    data = self._try_parse_json(json_str[start:end].strip())

        # Strategy 3: Find JSON by braces - look for {"personas":
        if data is None:
            # Find the start of the personas object
            personas_start = json_str.find('{"personas"')
            if personas_start == -1:
                personas_start = json_str.find("{'personas'")
            if personas_start >= 0:
                # Find matching closing brace
                brace_count = 0
                json_end = -1
                for i, char in enumerate(json_str[personas_start:]):
                    if char == "{":
                        brace_count += 1
                    elif char == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            json_end = personas_start + i + 1
                            break
                if json_end > personas_start:
                    data = self._try_parse_json(json_str[personas_start:json_end])

        # If we got valid data, extract personas
        if data and "personas" in data:
            try:
                personas = {}
                for agent_id in agent_ids:
                    if agent_id in data["personas"]:
                        persona_data = data["personas"][agent_id]
                        personas[agent_id] = GeneratedPersona(
                            agent_id=agent_id,
                            persona_text=persona_data.get("persona_text", "Approach this task thoughtfully."),
                            attributes=persona_data.get("attributes", {}),
                        )
                    else:
                        logger.warning(f"No persona generated for agent {agent_id}, using default")
                        personas[agent_id] = GeneratedPersona(
                            agent_id=agent_id,
                            persona_text="Approach this task thoughtfully and thoroughly.",
                            attributes={},
                        )
                return personas
            except (KeyError, TypeError) as e:
                logger.error(f"Failed to extract personas from parsed data: {e}")

        logger.error("Failed to parse persona response after all strategies")
        logger.debug(f"Response was: {response[:500]}...")
        return self._generate_fallback_personas(agent_ids)

    def _try_parse_json(self, text: str) -> dict[str, Any] | None:
        """Attempt to parse JSON, returning None on failure.

        Args:
            text: String to parse as JSON

        Returns:
            Parsed dict or None if parsing fails
        """
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def _find_personas_json(
        self,
        log_directory: str,
        agent_ids: list[str],
    ) -> dict[str, GeneratedPersona] | None:
        """Search for personas.json in the subagent logs.

        Delegates file discovery to :func:`massgen.precollab_utils.find_precollab_artifact`,
        then parses the JSON and validates that all expected agent IDs are present.

        Args:
            log_directory: Path to the main run's log directory
            agent_ids: Expected agent IDs

        Returns:
            Dictionary mapping agent_id to GeneratedPersona, or None if not found/invalid
        """
        from massgen.precollab_utils import find_precollab_artifact

        personas_file = find_precollab_artifact(
            log_directory,
            "persona_generation",
            "personas.json",
        )
        if personas_file is None:
            return None

        try:
            data = json.loads(personas_file.read_text())

            if "personas" not in data:
                logger.debug("personas.json missing 'personas' key")
                return None

            personas = {}
            for agent_id in agent_ids:
                if agent_id in data["personas"]:
                    persona_data = data["personas"][agent_id]
                    personas[agent_id] = GeneratedPersona(
                        agent_id=agent_id,
                        persona_text=persona_data.get(
                            "persona_text",
                            "Approach this task thoughtfully.",
                        ),
                        attributes=persona_data.get("attributes", {}),
                    )

            if len(personas) == len(agent_ids):
                logger.debug(f"Found complete personas at: {personas_file}")
                return personas
            else:
                logger.debug(
                    f"Incomplete personas at {personas_file}: " f"found {len(personas)}/{len(agent_ids)} agents",
                )

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.debug(f"Failed to parse {personas_file}: {e}")

        return None

    def _generate_fallback_personas(self, agent_ids: list[str]) -> dict[str, GeneratedPersona]:
        """Generate simple fallback personas if LLM generation fails.

        Args:
            agent_ids: List of agent IDs

        Returns:
            Dictionary mapping agent_id to GeneratedPersona with default personas
        """
        if self.diversity_mode == DiversityMode.METHODOLOGY:
            return self._generate_methodology_fallback_personas(agent_ids)

        fallback_templates = [
            (
                "analytical",
                "You approach problems analytically, breaking them down into components and examining each carefully. Focus on logical reasoning and evidence-based conclusions.",
            ),
            (
                "creative",
                "You think creatively, looking for innovative solutions and unconventional approaches. Don't be afraid to suggest novel ideas that others might overlook.",
            ),
            (
                "systematic",
                "You work systematically, ensuring thorough coverage and consistent methodology. Pay attention to process and make sure no important details are missed.",
            ),
            (
                "critical",
                "You take a critical perspective, questioning assumptions and identifying potential issues. Your role is to probe for weaknesses and ensure robustness.",
            ),
            (
                "practical",
                "You focus on practical implementation, considering real-world constraints and feasibility. Prioritize actionable solutions over theoretical ideals.",
            ),
        ]

        personas = {}
        for i, agent_id in enumerate(agent_ids):
            style, text = fallback_templates[i % len(fallback_templates)]
            personas[agent_id] = GeneratedPersona(
                agent_id=agent_id,
                persona_text=text,
                attributes={
                    "thinking_style": style,
                    "focus_area": "general",
                    "communication": "balanced",
                },
            )
            logger.debug(f"Using fallback persona for {agent_id}: {style}")

        return personas

    def _generate_methodology_fallback_personas(self, agent_ids: list[str]) -> dict[str, GeneratedPersona]:
        """Generate fallback personas for methodology mode (different working approaches)."""
        fallback_templates = [
            (
                "top-down",
                "Start by sketching the full structure and architecture before writing any details. Work from the big picture down to"
                " specifics, ensuring everything fits together before diving deep into any one part.",
            ),
            (
                "risk-first",
                "Identify the hardest, riskiest, or most uncertain part of the task and tackle it first. Get that working before"
                " building anything else — if the hard part doesn't work, everything else is wasted effort.",
            ),
            (
                "iterative",
                "Begin with the simplest complete version that could possibly work, then improve it in passes. Each iteration should"
                " produce something functional — layer on sophistication gradually rather than trying to get everything right the"
                " first time.",
            ),
            (
                "example-driven",
                "Start from concrete examples of what the desired output should look like. Work backwards from those examples to"
                " figure out what's needed, letting the concrete cases drive the design rather than abstract planning.",
            ),
            (
                "foundation-first",
                "Build the solid foundational infrastructure first using proven patterns and reliable approaches. Only innovate or"
                " experiment once the base is rock-solid — creativity on a strong foundation beats ambitious ideas on a shaky one.",
            ),
        ]

        personas = {}
        for i, agent_id in enumerate(agent_ids):
            style, text = fallback_templates[i % len(fallback_templates)]
            personas[agent_id] = GeneratedPersona(
                agent_id=agent_id,
                persona_text=text,
                attributes={
                    "thinking_style": style,
                    "focus_area": "general",
                    "communication": "balanced",
                },
            )
            logger.debug(f"Using fallback methodology persona for {agent_id}: {style}")

        return personas

    # =========================================================================
    # Subagent-based persona generation (uses MassGen coordination)
    # =========================================================================

    async def generate_personas_via_subagent(
        self,
        agent_ids: list[str],
        task: str,
        existing_system_messages: dict[str, str | None],
        parent_agent_configs: list[dict[str, Any]],
        parent_workspace: str,
        orchestrator_id: str,
        log_directory: str | None = None,
        on_subagent_started: Callable[[str, str, int, Callable[[str], Any | None], str | None], None] | None = None,
        voting_sensitivity: str | None = None,
        voting_threshold: int | None = None,
        has_planning_spec_context: bool = False,
        fast_iteration_mode: bool = False,
    ) -> dict[str, GeneratedPersona]:
        """Generate all personas via a single subagent call.

        This method uses MassGen's subagent infrastructure to generate personas.
        The subagent inherits the same models as the parent but with stripped-down
        config (no filesystem, no command line tools - just pure LLM reasoning).

        If the parent has multiple agents, the subagent will also use multiple
        agents to collaboratively generate the personas.

        Args:
            agent_ids: List of agent IDs to generate personas for
            task: The task/query agents will work on
            existing_system_messages: Existing system messages (to enhance, not replace)
            parent_agent_configs: List of parent agent configurations to inherit models from
            parent_workspace: Path to parent workspace for subagent workspace creation
            orchestrator_id: ID of the parent orchestrator
            log_directory: Optional path to log directory for subagent logs
            voting_sensitivity: Optional voting sensitivity to pass through to
                the pre-collaboration subagent coordination config.
            voting_threshold: Optional voting threshold to pass through to
                the pre-collaboration subagent coordination config.
            has_planning_spec_context: Whether planning/spec context is mounted
                and should be explicitly referenced by prompt guidance.
            fast_iteration_mode: Whether to enable fast iteration mode for
                the pre-collaboration subagent coordination.

        Returns:
            Dictionary mapping agent_id to GeneratedPersona
        """
        if not agent_ids:
            logger.warning("No agent IDs provided for persona generation")
            return {}

        logger.info(f"Generating personas via subagent for {len(agent_ids)} agents")

        # Build a dedicated workspace with CONTEXT.md (required by SubagentManager).
        base_workspace = parent_workspace or os.getcwd()
        persona_workspace = os.path.join(base_workspace, ".persona_generation")
        try:
            os.makedirs(persona_workspace, exist_ok=True)
            context_md = os.path.join(persona_workspace, "CONTEXT.md")
            with open(context_md, "w", encoding="utf-8") as f:
                f.write(
                    "# Persona Generation Context\n\n" f"Task:\n{task}\n\n" f"Agents:\n{', '.join(agent_ids)}\n\n" "Goal: generate diverse, high-quality personas for each agent in personas.json.\n",
                )
        except Exception as e:
            logger.warning(f"[PersonaGenerator] Failed to prepare dedicated persona workspace: {e}")
            persona_workspace = base_workspace

        try:
            from massgen.subagent.manager import SubagentManager
            from massgen.subagent.models import SubagentOrchestratorConfig

            # Create simplified agent configs (same models, no tools)
            simplified_configs = self._create_simplified_agent_configs(parent_agent_configs)

            # Configure subagent orchestrator with simplified agents.
            coordination = {
                "enable_subagents": False,  # No nested subagents
                "broadcast": False,  # Keep it simple
                "checklist_criteria_preset": "persona",
            }
            if voting_sensitivity:
                coordination["voting_sensitivity"] = voting_sensitivity
            if voting_threshold is not None:
                coordination["voting_threshold"] = voting_threshold
            if fast_iteration_mode:
                coordination["fast_iteration_mode"] = True

            subagent_orch_config = SubagentOrchestratorConfig(
                enabled=True,
                agents=simplified_configs,
                coordination=coordination,
            )
            from massgen.precollab_utils import build_subagent_parent_context_paths

            parent_context_paths = build_subagent_parent_context_paths(
                parent_workspace=base_workspace,
                agent_configs=parent_agent_configs,
            )

            manager = SubagentManager(
                parent_workspace=persona_workspace,
                parent_agent_id="persona_generator",
                orchestrator_id=orchestrator_id,
                parent_agent_configs=simplified_configs,
                max_concurrent=1,
                default_timeout=300,  # 5 min for all personas
                subagent_orchestrator_config=subagent_orch_config,
                log_directory=log_directory,
                parent_context_paths=parent_context_paths,
            )

            def _status_callback(subagent_id: str) -> Any | None:
                try:
                    return manager.get_subagent_display_data(subagent_id)
                except Exception:
                    return None

            # Build the prompt asking for ALL personas at once
            prompt = self._build_subagent_personas_prompt(
                agent_ids,
                task,
                existing_system_messages,
                has_planning_spec_context=has_planning_spec_context,
            )

            if on_subagent_started:
                try:
                    subagent_log_path = None
                    if log_directory:
                        subagent_log_path = str(Path(log_directory) / "subagents" / "persona_generation")
                    on_subagent_started(
                        "persona_generation",
                        prompt,
                        300,
                        _status_callback,
                        subagent_log_path,
                    )
                except Exception:
                    pass

            # Execute single subagent
            result = await manager.spawn_subagent(
                task=prompt,
                subagent_id="persona_generation",
                timeout_seconds=300,
            )

            # Check for output files regardless of success status
            # (subagent may have produced valid output before timeout/cancellation)
            if log_directory:
                personas = self._find_personas_json(log_directory, agent_ids)
                if personas:
                    self.last_generation_source = "subagent"
                    if result.success:
                        logger.info(f"Successfully loaded {len(personas)} personas from personas.json")
                    else:
                        logger.info(
                            f"Recovered {len(personas)} personas from partial output " f"(subagent status: {result.error})",
                        )
                    return personas

            # Try parsing answer if available
            if result.answer:
                personas = self._parse_response(result.answer, agent_ids)
                if personas:
                    self.last_generation_source = "subagent"
                    logger.info(f"Successfully parsed {len(personas)} personas from answer")
                    return personas

            if not result.success:
                logger.warning(f"Persona subagent failed: {result.error}, using fallback")
            else:
                logger.warning("No valid persona output found, using fallback")
            self.last_generation_source = "fallback"
            return self._generate_fallback_personas(agent_ids)

        except Exception as e:
            logger.error(f"Failed to generate personas via subagent: {e}")
            logger.info("Using fallback personas")
            self.last_generation_source = "fallback"
            return self._generate_fallback_personas(agent_ids)

    def _create_simplified_agent_configs(
        self,
        parent_configs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Create simplified agent configs - same models, no tools.

        Args:
            parent_configs: List of parent agent configurations

        Returns:
            List of simplified agent configurations with tools disabled
        """
        simplified = []
        for i, config in enumerate(parent_configs):
            backend = config.get("backend", {})
            simplified.append(
                {
                    "id": config.get("id", f"persona_agent_{i}"),
                    "backend": {
                        "type": backend.get("type", "openai"),
                        "model": backend.get("model"),
                        "base_url": backend.get("base_url"),
                        # Explicitly disable tools for pure LLM reasoning
                        "enable_mcp_command_line": False,
                        "enable_code_based_tools": False,
                        "exclude_file_operation_mcps": True,
                    },
                },
            )
        return simplified

    def _build_subagent_personas_prompt(
        self,
        agent_ids: list[str],
        task: str,
        existing_system_messages: dict[str, str | None],
        has_planning_spec_context: bool = False,
    ) -> str:
        """Build prompt to generate ALL personas with task-appropriate diversity.

        This prompt guides the LLM to dynamically determine what kinds of diversity
        make sense for the specific task, rather than using hardcoded approaches.

        Args:
            agent_ids: List of agent IDs to generate personas for
            task: The task description
            existing_system_messages: Existing system messages per agent

        Returns:
            The formatted prompt string
        """
        agents_context = []
        for agent_id in agent_ids:
            existing = existing_system_messages.get(agent_id)
            if existing:
                agents_context.append(f"- {agent_id}: Has existing instruction: {existing}")
            else:
                agents_context.append(f"- {agent_id}: No existing instruction")

        agents_list = "\n".join(agents_context)
        agent_ids_json = json.dumps(agent_ids)

        # Include custom guidelines if provided
        guidelines_section = ""
        if self.guidelines:
            guidelines_section = f"""
## Additional Guidelines
{self.guidelines}
"""

        # Build mode-specific content
        if self.diversity_mode == DiversityMode.IMPLEMENTATION:
            prompt = self._build_implementation_diversity_prompt(
                agent_ids,
                task,
                agents_list,
                agent_ids_json,
                guidelines_section,
            )
        elif self.diversity_mode == DiversityMode.METHODOLOGY:
            prompt = self._build_methodology_diversity_prompt(
                agent_ids,
                task,
                agents_list,
                agent_ids_json,
                guidelines_section,
            )
        else:
            prompt = self._build_perspective_diversity_prompt(
                agent_ids,
                task,
                agents_list,
                agent_ids_json,
                guidelines_section,
            )

        if has_planning_spec_context:
            context_alignment_section = """

## Planning/Spec Context Alignment
Read the mounted planning/spec context before writing personas and align with \
it so goals, personas, and evaluation criteria stay coherent. Treat planning/spec \
files as read-only references — do not modify them.
"""
            prompt += context_alignment_section

        return prompt

    def _build_perspective_diversity_prompt(
        self,
        agent_ids: list[str],
        task: str,
        agents_list: str,
        agent_ids_json: str,
        guidelines_section: str,
    ) -> str:
        """Build prompt for perspective-based diversity (different values/priorities)."""
        return f"""You are assigning different PERSPECTIVES to {len(agent_ids)} AI agents who will work on a task in parallel.

## Task
{task}

## Agents
{agents_list}
{guidelines_section}
## Your Goal
Give each agent a different PERSPECTIVE or LENS through which to view the problem.
The value of multiple agents is that they see the problem differently and therefore
arrive at different solutions - NOT that they use different implementation techniques.

## What Makes a Good Perspective

A perspective is about WHAT matters and WHY, not HOW to implement:
- What does this agent value most? (simplicity? robustness? user delight? correctness?)
- What tradeoffs would they make differently?
- What would they refuse to compromise on?
- What would they consider "good enough" vs "not acceptable"?

Examples of perspectives (do NOT use these literally - create ones appropriate for the task):
- "Optimize for the end user who will interact with this daily"
- "Prioritize long-term maintainability over short-term convenience"
- "Assume constraints are tighter than stated and build defensively"
- "Focus on the 80% case and make that exceptional"

## Requirements
1. Keep personas concise (3-5 sentences)
2. Focus on VALUES and PRIORITIES, not implementation steps
3. Do NOT prescribe file structures, specific technologies, or methodologies
4. Do NOT tell them HOW to work - just WHAT to optimize for
5. Each agent must solve the ENTIRE task - perspectives differ, scope does not
6. If agent has existing instructions, add perspective without changing their workflow
7. Each persona must explicitly reinforce complete end-to-end delivery quality
8. Never assign a narrow role (e.g., "only testing" or "only frontend")

## Output Format
IMPORTANT: Write the JSON to a file called `personas.json` in your workspace.

The JSON must have this structure:
{{
    "personas": {{
        "<agent_id>": {{
            "persona_text": "Short perspective statement...",
            "attributes": {{
                "approach_summary": "2-3 word summary"
            }}
        }}
    }}
}}

Agent IDs: {agent_ids_json}

Write personas.json now."""

    def _build_implementation_diversity_prompt(
        self,
        agent_ids: list[str],
        task: str,
        agents_list: str,
        agent_ids_json: str,
        guidelines_section: str,
    ) -> str:
        """Build prompt for implementation-based diversity (different solution types)."""
        return f"""You are assigning different SOLUTION APPROACHES to {len(agent_ids)} AI agents who will work on a task in parallel.

## Task
{task}

## Agents
{agents_list}
{guidelines_section}
## Your Goal
Give each agent a different INTERPRETATION of what kind of solution to build.
The value of multiple agents is that they explore fundamentally different solution types -
not just different ways to build the same thing.

## What Makes Good Implementation Diversity

Think about the CATEGORY or TYPE of solution, not implementation details:
- What different forms could the solution take?
- What different user experiences could be created?
- What different scopes or ambitions are valid interpretations?
- What different mental models could inform the solution?

Examples for a "create a website" task (do NOT use these literally):
- "Build a single-page immersive storytelling experience"
- "Create a multi-page informational resource with deep navigation"
- "Design an interactive timeline-based exploration"
- "Make a minimalist gallery-focused presentation"

## Requirements
1. Keep personas concise (3-5 sentences)
2. Focus on WHAT KIND of solution, not HOW to build it
3. Do NOT prescribe specific technologies, file structures, or code patterns
4. Do NOT tell them implementation steps - just the vision/direction
5. Each agent must solve the ENTIRE task - interpretations differ, completeness does not
6. If agent has existing instructions, add direction without changing their workflow
7. Each persona must explicitly reinforce complete end-to-end delivery quality
8. Never assign a narrow role (e.g., "only testing" or "only frontend")

## Output Format
IMPORTANT: Write the JSON to a file called `personas.json` in your workspace.

The JSON must have this structure:
{{
    "personas": {{
        "<agent_id>": {{
            "persona_text": "Solution direction statement...",
            "attributes": {{
                "approach_summary": "2-3 word summary"
            }}
        }}
    }}
}}

Agent IDs: {agent_ids_json}

Write personas.json now."""

    def _build_methodology_diversity_prompt(
        self,
        agent_ids: list[str],
        task: str,
        agents_list: str,
        agent_ids_json: str,
        guidelines_section: str,
    ) -> str:
        """Build prompt for methodology-based diversity (different working approaches)."""
        return f"""You are assigning different WORKING APPROACHES to {len(agent_ids)} AI agents who will work on a task in parallel.

## Task
{task}

## Agents
{agents_list}
{guidelines_section}
## Your Goal
Give each agent a genuinely different METHODOLOGY for how they tackle the work.
The value of multiple agents is that they approach the same problem in fundamentally different
ways — different processes, different starting points, different ways of structuring their work.
This naturally produces different solutions even when agents have the same goal.

## What Makes Good Methodology Diversity

Think about HOW each agent works, not WHAT they optimize for or WHAT they build:
- Where do they start? (big picture first? hardest problem first? simplest prototype first?)
- How do they structure their process? (top-down? bottom-up? inside-out?)
- What do they do when stuck? (experiment? analyze? simplify? reframe?)
- What's their relationship to risk? (bold experiments? proven patterns? defensive builds?)

Examples (do NOT use these literally - create approaches appropriate for the task):
- "Start with the hardest, riskiest piece first. Get that working, then build everything else around it."
- "Begin with a complete but minimal version, then iteratively layer on sophistication."
- "Work top-down: sketch the full architecture first, then fill in each component."
- "Start from concrete examples of the desired output, then reverse-engineer the solution."
- "Build the foundational infrastructure with proven patterns first, then innovate on top."

The approaches should be different enough that agents will naturally produce different solutions
even if given the same task and the same goals.

## Requirements
1. Keep personas concise (3-5 sentences)
2. Focus on HOW to approach the work, not WHAT to optimize for or WHAT kind of solution
3. Do NOT prescribe specific technologies, file structures, or code patterns
4. Do NOT tell them what to value - tell them how to work
5. Each agent must solve the ENTIRE task - approaches differ, scope does not
6. If agent has existing instructions, add working approach without changing their workflow
7. Each persona must explicitly reinforce complete end-to-end delivery quality
8. Never assign a narrow role (e.g., "only testing" or "only frontend")

## Output Format
IMPORTANT: Write the JSON to a file called `personas.json` in your workspace.

The JSON must have this structure:
{{
    "personas": {{
        "<agent_id>": {{
            "persona_text": "Working approach statement...",
            "attributes": {{
                "approach_summary": "2-3 word summary"
            }}
        }}
    }}
}}

Agent IDs: {agent_ids_json}

Write personas.json now."""
