# -*- coding: utf-8 -*-
"""System message builder for MassGen orchestration.

This module provides the SystemMessageBuilder class which centralizes all system
message construction logic for different orchestration phases (coordination,
presentation, and post-evaluation).

This was extracted from orchestrator.py to improve separation of concerns and
reduce coupling between orchestration logic and prompt construction.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class SystemMessageBuilder:
    """Builds system messages for different orchestration phases.

    This class centralizes all system message construction logic and consolidates
    duplicated code across the three main phases:
    - Coordination: Complex multi-agent collaboration with skills, memory, evaluation
    - Presentation: Final answer presentation with media generation capabilities
    - Post-evaluation: Answer verification and quality checking

    Args:
        config: Orchestrator configuration
        message_templates: MessageTemplates instance for presentation logic
        agents: Dictionary of agent_id -> ChatAgent for memory scanning
    """

    def __init__(
        self,
        config,  # CoordinationConfig type
        message_templates,  # MessageTemplates type
        agents: Dict[str, Any],  # Dict[str, ChatAgent]
    ):
        """Initialize the system message builder.

        Args:
            config: Orchestrator coordination configuration
            message_templates: MessageTemplates instance
            agents: Dictionary of agents for memory scanning
        """
        self.config = config
        self.message_templates = message_templates
        self.agents = agents

    def build_coordination_message(
        self,
        agent,  # ChatAgent
        agent_id: str,
        answers: Optional[Dict[str, str]],
        planning_mode_enabled: bool,
        use_skills: bool,
        enable_memory: bool,
        enable_task_planning: bool,
        previous_turns: List[Dict[str, Any]],
    ) -> str:
        """Build system message for coordination phase.

        This method assembles the system prompt using priority-based sections with
        XML structure, ensuring critical instructions (skills, memory) appear early.

        Args:
            agent: The agent instance
            agent_id: Agent identifier
            answers: Dict of current answers from agents
            planning_mode_enabled: Whether planning mode is active
            use_skills: Whether to include skills section
            enable_memory: Whether to include memory section
            enable_task_planning: Whether to include task planning guidance
            previous_turns: List of previous turn data for filesystem context

        Returns:
            Complete system prompt string with XML structure
        """
        from massgen.system_prompt_sections import (
            AgentIdentitySection,
            CoreBehaviorsSection,
            EvaluationSection,
            MemorySection,
            PlanningModeSection,
            SkillsSection,
            SystemPromptBuilder,
            TaskPlanningSection,
            WorkspaceStructureSection,
        )

        builder = SystemPromptBuilder()

        # PRIORITY 1 (CRITICAL): Agent Identity - WHO they are
        agent_system_message = agent.get_configurable_system_message()
        # Use empty string if None to avoid showing "None" in prompt
        if agent_system_message is None:
            agent_system_message = ""
        builder.add_section(AgentIdentitySection(agent_system_message))

        # PRIORITY 1 (CRITICAL): Core Behaviors - HOW to act
        builder.add_section(CoreBehaviorsSection())

        # PRIORITY 1 (CRITICAL): MassGen Coordination - vote/new_answer primitives
        voting_sensitivity = self.message_templates._voting_sensitivity
        answer_novelty_requirement = self.message_templates._answer_novelty_requirement
        builder.add_section(
            EvaluationSection(
                voting_sensitivity=voting_sensitivity,
                answer_novelty_requirement=answer_novelty_requirement,
            ),
        )

        # PRIORITY 5 (HIGH): Skills - Must be visible early
        if use_skills:
            from massgen.filesystem_manager.skills_manager import scan_skills

            # Scan all available skills
            skills_dir = Path(self.config.coordination_config.skills_directory)
            all_skills = scan_skills(skills_dir)

            # Log what we found
            builtin_count = len([s for s in all_skills if s["location"] == "builtin"])
            project_count = len([s for s in all_skills if s["location"] == "project"])
            logger.info(f"[SystemMessageBuilder] Scanned skills: {builtin_count} builtin, {project_count} project")

            # Add skills section with all skills (both project and builtin)
            # Builtin skills are now treated the same as project skills - invoke with openskills read
            builder.add_section(SkillsSection(all_skills))

        # PRIORITY 5 (HIGH): Memory - Proactive usage
        if enable_memory:
            short_term_memories, long_term_memories = self._get_all_memories()
            # Always add memory section to show usage instructions, even if empty
            memory_config = {
                "short_term": {
                    "content": "\n".join([f"- {m}" for m in short_term_memories]) if short_term_memories else "",
                },
                "long_term": [{"id": f"mem_{i}", "summary": mem, "created_at": "N/A"} for i, mem in enumerate(long_term_memories)] if long_term_memories else [],
            }
            builder.add_section(MemorySection(memory_config))
            logger.info(f"[SystemMessageBuilder] Added memory section ({len(short_term_memories)} short-term, {len(long_term_memories)} long-term memories)")

        # PRIORITY 5 (HIGH): Filesystem - Essential context
        if agent.backend.filesystem_manager:
            main_workspace = str(agent.backend.filesystem_manager.get_current_workspace())
            context_paths = agent.backend.filesystem_manager.path_permission_manager.get_context_paths() if agent.backend.filesystem_manager.path_permission_manager else []

            # Add workspace structure section (critical paths)
            builder.add_section(WorkspaceStructureSection(main_workspace, [p.get("path", "") for p in context_paths]))

            # Check command execution settings
            enable_command_execution = False
            docker_mode = False
            enable_sudo = False
            if hasattr(agent, "config") and agent.config:
                enable_command_execution = agent.config.backend_params.get("enable_mcp_command_line", False)
                docker_mode = agent.config.backend_params.get("command_line_execution_mode", "local") == "docker"
                enable_sudo = agent.config.backend_params.get("command_line_docker_enable_sudo", False)
            elif hasattr(agent, "backend") and hasattr(agent.backend, "backend_params"):
                enable_command_execution = agent.backend.backend_params.get("enable_mcp_command_line", False)
                docker_mode = agent.backend.backend_params.get("command_line_execution_mode", "local") == "docker"
                enable_sudo = agent.backend.backend_params.get("command_line_docker_enable_sudo", False)

            # Build and add filesystem sections using consolidated helper
            fs_ops, fs_best, cmd_exec = self._build_filesystem_sections(
                agent=agent,
                all_answers=answers,
                previous_turns=previous_turns,
                enable_command_execution=enable_command_execution,
                docker_mode=docker_mode,
                enable_sudo=enable_sudo,
            )

            builder.add_section(fs_ops)
            builder.add_section(fs_best)
            if cmd_exec:
                builder.add_section(cmd_exec)

            # Add lightweight file search guidance if command execution is available
            # (rg and sg are pre-installed in Docker and commonly available in local mode)
            from massgen.system_prompt_sections import FileSearchSection

            builder.add_section(FileSearchSection())

        # PRIORITY 10 (MEDIUM): Task Planning
        if enable_task_planning:
            filesystem_mode = (
                hasattr(self.config.coordination_config, "task_planning_filesystem_mode")
                and self.config.coordination_config.task_planning_filesystem_mode
                and hasattr(agent, "backend")
                and hasattr(agent.backend, "filesystem_manager")
                and agent.backend.filesystem_manager
                and agent.backend.filesystem_manager.cwd
            )
            builder.add_section(TaskPlanningSection(filesystem_mode=filesystem_mode))

        # PRIORITY 10 (MEDIUM): Planning Mode (conditional)
        if planning_mode_enabled and self.config and hasattr(self.config, "coordination_config") and self.config.coordination_config and self.config.coordination_config.planning_mode_instruction:
            builder.add_section(PlanningModeSection(self.config.coordination_config.planning_mode_instruction))
            logger.info(f"[SystemMessageBuilder] Added planning mode instructions for {agent_id}")

        # Build and return the complete structured system prompt
        return builder.build()

    def build_presentation_message(
        self,
        agent,  # ChatAgent
        all_answers: Dict[str, str],
        previous_turns: List[Dict[str, Any]],
        enable_image_generation: bool = False,
        enable_audio_generation: bool = False,
        enable_file_generation: bool = False,
        enable_video_generation: bool = False,
        has_irreversible_actions: bool = False,
        enable_command_execution: bool = False,
        docker_mode: bool = False,
        enable_sudo: bool = False,
    ) -> str:
        """Build system message for final presentation phase.

        This combines the agent's identity, presentation instructions, and filesystem
        operations using the structured section approach.

        Args:
            agent: The presenting agent
            all_answers: All answers from coordination phase
            previous_turns: List of previous turn data for filesystem context
            enable_image_generation: Whether image generation is enabled
            enable_audio_generation: Whether audio generation is enabled
            enable_file_generation: Whether file generation is enabled
            enable_video_generation: Whether video generation is enabled
            has_irreversible_actions: Whether agent has write access
            enable_command_execution: Whether command execution is enabled
            docker_mode: Whether commands run in Docker
            enable_sudo: Whether sudo is available

        Returns:
            Complete system message string
        """
        # Get agent's configurable system message
        agent_system_message = agent.get_configurable_system_message()
        if agent_system_message is None:
            agent_system_message = ""

        # Get presentation instructions from message_templates
        # (This contains special logic for image/audio/file/video generation)
        presentation_instructions = self.message_templates.final_presentation_system_message(
            original_system_message=agent_system_message,
            enable_image_generation=enable_image_generation,
            enable_audio_generation=enable_audio_generation,
            enable_file_generation=enable_file_generation,
            enable_video_generation=enable_video_generation,
            has_irreversible_actions=has_irreversible_actions,
            enable_command_execution=enable_command_execution,
        )

        # If filesystem is available, prepend filesystem sections
        if agent.backend.filesystem_manager:
            # Build filesystem sections using consolidated helper
            fs_ops, fs_best, cmd_exec = self._build_filesystem_sections(
                agent=agent,
                all_answers=all_answers,
                previous_turns=previous_turns,
                enable_command_execution=enable_command_execution,
                docker_mode=docker_mode,
                enable_sudo=enable_sudo,
            )

            # Build sections list
            sections_content = [fs_ops.build_content(), fs_best.build_content()]
            if cmd_exec:
                sections_content.append(cmd_exec.build_content())

            # Combine: filesystem sections + presentation instructions
            filesystem_content = "\n\n".join(sections_content)
            return f"{filesystem_content}\n\n## Instructions\n{presentation_instructions}"
        else:
            # No filesystem - just return presentation instructions
            return presentation_instructions

    def build_post_evaluation_message(
        self,
        agent,  # ChatAgent
        all_answers: Dict[str, str],
        previous_turns: List[Dict[str, Any]],
    ) -> str:
        """Build system message for post-evaluation phase.

        This combines the agent's identity, post-evaluation instructions, and filesystem
        operations using the structured section approach.

        Args:
            agent: The evaluating agent
            all_answers: All answers from coordination phase
            previous_turns: List of previous turn data for filesystem context

        Returns:
            Complete system message string
        """
        from massgen.system_prompt_sections import PostEvaluationSection

        # Get agent's configurable system message
        agent_system_message = agent.get_configurable_system_message()
        if agent_system_message is None:
            agent_system_message = ""

        # Start with agent identity if provided
        parts = []
        if agent_system_message:
            parts.append(agent_system_message)

        # If filesystem is available, add filesystem sections
        if agent.backend.filesystem_manager:
            # Build filesystem sections using consolidated helper
            # (No command execution in post-evaluation)
            fs_ops, fs_best, _ = self._build_filesystem_sections(
                agent=agent,
                all_answers=all_answers,
                previous_turns=previous_turns,
                enable_command_execution=False,
                docker_mode=False,
                enable_sudo=False,
            )

            parts.append(fs_ops.build_content())
            parts.append(fs_best.build_content())

        # Add post-evaluation instructions
        post_eval = PostEvaluationSection()
        parts.append(post_eval.build_content())

        return "\n\n".join(parts)

    def _build_filesystem_sections(
        self,
        agent,  # ChatAgent
        all_answers: Dict[str, str],
        previous_turns: List[Dict[str, Any]],
        enable_command_execution: bool,
        docker_mode: bool = False,
        enable_sudo: bool = False,
    ) -> Tuple[Any, Any, Optional[Any]]:  # Tuple[FilesystemOperationsSection, FilesystemBestPracticesSection, Optional[CommandExecutionSection]]
        """Build filesystem-related sections.

        This consolidates the duplicated logic across all three builder methods
        for creating filesystem operations, best practices, and command execution sections.

        Args:
            agent: The agent instance
            all_answers: Dict of current answers from agents
            previous_turns: List of previous turn data for filesystem context
            enable_command_execution: Whether to include command execution section
            docker_mode: Whether commands run in Docker
            enable_sudo: Whether sudo is available

        Returns:
            Tuple of (FilesystemOperationsSection, FilesystemBestPracticesSection, Optional[CommandExecutionSection])
        """
        from massgen.system_prompt_sections import (
            CommandExecutionSection,
            FilesystemBestPracticesSection,
            FilesystemOperationsSection,
        )

        # Extract filesystem paths from agent
        main_workspace = str(agent.backend.filesystem_manager.get_current_workspace())
        temp_workspace = str(agent.backend.filesystem_manager.agent_temporary_workspace) if agent.backend.filesystem_manager.agent_temporary_workspace else None
        context_paths = agent.backend.filesystem_manager.path_permission_manager.get_context_paths() if agent.backend.filesystem_manager.path_permission_manager else []

        # Calculate previous turns context
        current_turn_num = len(previous_turns) + 1 if previous_turns else 1
        turns_to_show = [t for t in previous_turns if t["turn"] < current_turn_num - 1]
        workspace_prepopulated = len(previous_turns) > 0

        # Build filesystem operations section
        fs_ops = FilesystemOperationsSection(
            main_workspace=main_workspace,
            temp_workspace=temp_workspace,
            context_paths=context_paths,
            previous_turns=turns_to_show,
            workspace_prepopulated=workspace_prepopulated,
            agent_answers=all_answers,
            enable_command_execution=enable_command_execution,
        )

        # Build filesystem best practices section
        fs_best = FilesystemBestPracticesSection()

        # Build command execution section if enabled
        cmd_exec = None
        if enable_command_execution:
            cmd_exec = CommandExecutionSection(docker_mode=docker_mode, enable_sudo=enable_sudo)

        return fs_ops, fs_best, cmd_exec

    def _get_all_memories(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Read all memories from all agents' workspaces.

        Returns:
            Tuple of (short_term_memories, long_term_memories)
            Each is a list of memory dictionaries with keys:
            - name, description, content, tier, agent_id, created, updated
        """
        short_term_memories = []
        long_term_memories = []

        # Scan all agents' workspaces
        for agent_id, agent in self.agents.items():
            if not (hasattr(agent, "backend") and hasattr(agent.backend, "filesystem_manager") and agent.backend.filesystem_manager):
                continue

            workspace = agent.backend.filesystem_manager.cwd
            if not workspace:
                continue

            memory_dir = Path(workspace) / "memory"
            if not memory_dir.exists():
                continue

            # Read short-term memories
            short_term_dir = memory_dir / "short_term"
            if short_term_dir.exists():
                for mem_file in short_term_dir.glob("*.md"):
                    try:
                        memory_data = self._parse_memory_file(mem_file)
                        if memory_data:
                            short_term_memories.append(memory_data)
                    except Exception as e:
                        logger.warning(f"[SystemMessageBuilder] Failed to parse memory file {mem_file}: {e}")

            # Read long-term memories
            long_term_dir = memory_dir / "long_term"
            if long_term_dir.exists():
                for mem_file in long_term_dir.glob("*.md"):
                    try:
                        memory_data = self._parse_memory_file(mem_file)
                        if memory_data:
                            long_term_memories.append(memory_data)
                    except Exception as e:
                        logger.warning(f"[SystemMessageBuilder] Failed to parse memory file {mem_file}: {e}")

        return short_term_memories, long_term_memories

    @staticmethod
    def _parse_memory_file(file_path: Path) -> Optional[Dict[str, Any]]:
        """Parse a memory markdown file with YAML frontmatter.

        Args:
            file_path: Path to the memory file

        Returns:
            Dictionary with memory data or None if parsing fails
        """
        try:
            content = file_path.read_text()

            # Split frontmatter from content
            if not content.startswith("---"):
                return None

            parts = content.split("---", 2)
            if len(parts) < 3:
                return None

            frontmatter_text = parts[1].strip()
            memory_content = parts[2].strip()

            # Parse frontmatter (simple key: value parser)
            metadata = {}
            for line in frontmatter_text.split("\n"):
                line = line.strip()
                if ":" in line:
                    key, value = line.split(":", 1)
                    metadata[key.strip()] = value.strip()

            # Return combined memory data
            return {
                "name": metadata.get("name", ""),
                "description": metadata.get("description", ""),
                "content": memory_content,
                "tier": metadata.get("tier", ""),
                "agent_id": metadata.get("agent_id", ""),
                "created": metadata.get("created", ""),
                "updated": metadata.get("updated", ""),
            }
        except Exception:
            return None
