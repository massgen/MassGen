# -*- coding: utf-8 -*-
"""
System Prompt Section Architecture

This module implements a class-based architecture for building structured,
prioritized system prompts. Each section encapsulates specific instructions
with explicit priority levels, enabling better attention management and
maintainability.

Design Document: docs/dev_notes/system_prompt_architecture_redesign.md
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional


class Priority(IntEnum):
    """
    Explicit priority levels for system prompt sections.

    Lower numbers = higher priority (appear earlier in final prompt).
    Based on research showing critical instructions should appear at top
    or bottom of prompts for maximum attention.

    References:
        - Lakera AI Prompt Engineering Guide 2025
        - Anthropic Claude 4 Best Practices
        - "Position is Power" research (arXiv:2505.21091v2)
    """

    CRITICAL = 1  # Agent identity, MassGen primitives (vote/new_answer), core behaviors
    HIGH = 5  # Skills, memory, filesystem workspace - essential context
    MEDIUM = 10  # Operational guidance, task planning
    LOW = 15  # Task-specific context
    AUXILIARY = 20  # Optional guidance, best practices


@dataclass
class SystemPromptSection(ABC):
    """
    Base class for all system prompt sections.

    Each section encapsulates a specific set of instructions with explicit
    priority, optional XML structure, and support for hierarchical subsections.

    Attributes:
        title: Human-readable section title (for debugging/logging)
        priority: Priority level determining render order
        xml_tag: Optional XML tag name for wrapping content
        enabled: Whether this section should be included
        subsections: Optional list of child sections for hierarchy

    Example:
        >>> class CustomSection(SystemPromptSection):
        ...     def build_content(self) -> str:
        ...         return "Custom instructions here"
        >>>
        >>> section = CustomSection(
        ...     title="Custom",
        ...     priority=Priority.MEDIUM,
        ...     xml_tag="custom"
        ... )
        >>> print(section.render())
        <custom priority="medium">
        Custom instructions here
        </custom>
    """

    title: str
    priority: Priority
    xml_tag: Optional[str] = None
    enabled: bool = True
    subsections: List["SystemPromptSection"] = field(default_factory=list)

    @abstractmethod
    def build_content(self) -> str:
        """
        Build the actual content for this section.

        Subclasses must implement this to provide their specific instructions.

        Returns:
            String content for this section (without XML wrapping)
        """

    def render(self) -> str:
        """
        Render the complete section with XML structure if specified.

        Automatically handles:
        - XML tag wrapping with priority attributes
        - Recursive rendering of subsections
        - Skipping if disabled

        Returns:
            Formatted section string ready for inclusion in system prompt
        """
        if not self.enabled:
            return ""

        # Build main content
        content = self.build_content()

        # Render and append subsections if present
        if self.subsections:
            enabled_subsections = [s for s in self.subsections if s.enabled]
            if enabled_subsections:
                sorted_subsections = sorted(
                    enabled_subsections,
                    key=lambda s: s.priority,
                )
                subsection_content = "\n\n".join(s.render() for s in sorted_subsections)
                content = f"{content}\n\n{subsection_content}"

        # Wrap in XML if tag specified
        if self.xml_tag:
            priority_name = self.priority.name.lower()
            return f'<{self.xml_tag} priority="{priority_name}">\n{content}\n</{self.xml_tag}>'

        return content


class AgentIdentitySection(SystemPromptSection):
    """
    Agent's core identity: role, expertise, personality.

    This section ALWAYS comes first (Priority.CRITICAL) to establish
    WHO the agent is before any operational instructions.

    Args:
        agent_message: The agent's custom system message from
                      agent.get_configurable_system_message()
    """

    def __init__(self, agent_message: str):
        super().__init__(
            title="Agent Identity",
            priority=Priority.CRITICAL,
            xml_tag="agent_identity",
        )
        self.agent_message = agent_message

    def build_content(self) -> str:
        return self.agent_message


class CoreBehaviorsSection(SystemPromptSection):
    """
    Core behavioral principles for Claude agents.

    Includes critical guidance on:
    - Default to action vs suggestion
    - Parallel tool calling
    - File cleanup

    Based on Anthropic Claude 4 best practices.
    """

    def __init__(self):
        super().__init__(
            title="Core Behaviors",
            priority=Priority.CRITICAL,
            xml_tag="core_behaviors",
        )

    def build_content(self) -> str:
        return """## Core Behavioral Principles

**Default to Action:**
By default, implement changes rather than only suggesting them. If the user's intent is unclear,
infer the most useful likely action and proceed, using tools to discover any missing details instead
of guessing. Try to infer the user's intent about whether a tool call (e.g., file edit or read) is
intended or not, and act accordingly.

**Parallel Tool Calling:**
If you intend to call multiple tools and there are no dependencies between the tool calls, make all
of the independent tool calls in parallel. Prioritize calling tools simultaneously whenever the
actions can be done in parallel rather than sequentially. For example, when reading 3 files, run 3
tool calls in parallel to read all 3 files into context at the same time. Maximize use of parallel
tool calls where possible to increase speed and efficiency. However, if some tool calls depend on
previous calls to inform dependent values like the parameters, do NOT call these tools in parallel
and instead call them sequentially. Never use placeholders or guess missing parameters in tool calls."""


class SkillsSection(SystemPromptSection):
    """
    Available skills that agents can invoke.

    HIGH priority ensures skills are visible early in the prompt.
    Includes prominent emphasis on reviewing skills before starting work.

    Args:
        skills: List of external skills with name, description, etc.
        built_in_skills: Optional list of built-in skills to document
    """

    def __init__(self, skills: List[Dict[str, Any]], built_in_skills: Optional[List[str]] = None):
        super().__init__(
            title="Available Skills",
            priority=Priority.HIGH,
            xml_tag="skills",
        )
        self.skills = skills
        self.built_in_skills = built_in_skills or []

    def build_content(self) -> str:
        """Build skills table and usage instructions."""
        content_parts = []

        # Prominent header emphasizing importance
        content_parts.append(
            "## IMPORTANT: Review Available Skills Before Starting Work\n\n"
            "You have access to specialized skills that can dramatically improve your "
            "performance on certain tasks. ALWAYS think about the relevant available "
            "skills below before starting work - they may save significant time and effort.",
        )

        # Built-in skills (if any)
        if self.built_in_skills:
            content_parts.append("\n### Built-in Skills\n")
            content_parts.append(
                "The following skills are automatically available and have been " "injected into your system prompt:\n",
            )
            for skill_name in self.built_in_skills:
                content_parts.append(f"- `{skill_name}`")

        # External skills table
        if self.skills:
            content_parts.append("\n### Available Skills\n")
            content_parts.append(
                "| Skill | Description | When to Use |\n" "|-------|-------------|-------------|",
            )

            for skill in self.skills:
                name = skill.get("name", "Unknown")
                description = skill.get("description", "No description")
                when_to_use = skill.get("when_to_use", "See description")

                # Truncate long descriptions for table readability
                if len(description) > 100:
                    description = description[:97] + "..."

                content_parts.append(
                    f"| {name} | {description} | {when_to_use} |",
                )

            # Usage instructions
            content_parts.append(
                "\n**How to use skills:**\n"
                "1. Review the table above and identify which skill(s) apply to your task\n"
                "2. Invoke the skill by name using the appropriate tool/command\n"
                "3. Skills may provide specialized tools, context, or capabilities\n"
                "4. Always check skill outputs before proceeding with your task",
            )

        return "\n".join(content_parts)


class MemorySection(SystemPromptSection):
    """
    Memory system instructions for context retention across conversations.

    HIGH priority ensures memory usage is prominent and agents use it
    proactively rather than only when explicitly prompted.

    Args:
        memory_config: Dictionary containing memory system configuration
                      including short-term and long-term memory content
    """

    def __init__(self, memory_config: Dict[str, Any]):
        super().__init__(
            title="Memory System",
            priority=Priority.HIGH,
            xml_tag="memory",
        )
        self.memory_config = memory_config

    def build_content(self) -> str:
        """Build memory system instructions."""
        content_parts = []

        # Header with emphasis on proactive usage
        content_parts.append(
            "## Memory System: Proactive Context Retention\n\n"
            "You have access to a tiered memory system for retaining important context "
            "across conversations. Use memory proactively to:\n"
            "- Save key decisions and rationale\n"
            "- Record important findings\n"
            "- Build up knowledge over time\n"
            "- Avoid re-discovering the same information",
        )

        # Short-term memory (full content if available)
        short_term = self.memory_config.get("short_term", {})
        if short_term:
            content_parts.append("\n### Short-Term Memory (Current Session)\n")

            short_term_content = short_term.get("content", "")
            if short_term_content:
                content_parts.append(short_term_content)
            else:
                content_parts.append("*No short-term memories yet*")

        # Long-term memory (table format)
        long_term = self.memory_config.get("long_term", [])
        if long_term:
            content_parts.append("\n### Long-Term Memory (Persistent)\n")
            content_parts.append(
                "| Memory ID | Summary | Created |\n" "|-----------|---------|---------|",
            )

            for memory in long_term:
                mem_id = memory.get("id", "N/A")
                summary = memory.get("summary", "No summary")
                created = memory.get("created_at", "Unknown")

                # Truncate long summaries
                if len(summary) > 80:
                    summary = summary[:77] + "..."

                content_parts.append(f"| {mem_id} | {summary} | {created} |")

        # Memory operations
        content_parts.append(
            "\n### Memory Operations\n\n"
            "**Available operations:**\n"
            "- `create_memory(content, tier='short')` - Save new memory\n"
            "- `load_memory(memory_id)` - Retrieve specific memory\n"
            "- `search_memory(query)` - Search across all memories\n"
            "- `update_memory(memory_id, content)` - Update existing memory\n\n"
            "**Best practices:**\n"
            "- Create memories for important decisions and findings\n"
            "- Use descriptive content so memories are searchable\n"
            "- Load relevant memories at the start of related tasks\n"
            "- Update memories as context evolves",
        )

        return "\n".join(content_parts)


class WorkspaceStructureSection(SystemPromptSection):
    """
    Critical workspace paths and structure information.

    This subsection of FilesystemSection contains the MUST-KNOW information
    about where files are located and how the workspace is organized.

    Args:
        workspace_path: Path to the agent's workspace directory
        context_paths: List of paths containing important context
    """

    def __init__(self, workspace_path: str, context_paths: List[str]):
        super().__init__(
            title="Workspace Structure",
            priority=Priority.HIGH,
            xml_tag="workspace_structure",
        )
        self.workspace_path = workspace_path
        self.context_paths = context_paths

    def build_content(self) -> str:
        """Build workspace structure documentation."""
        content_parts = []

        content_parts.append("## Workspace Paths\n")
        content_parts.append(f"**Workspace directory**: `{self.workspace_path}`")
        content_parts.append(
            "\nThis is your primary working directory where you should create " "and manage files for this task.\n",
        )

        if self.context_paths:
            content_parts.append("**Context paths**:")
            for path in self.context_paths:
                content_parts.append(f"- `{path}`")
            content_parts.append(
                "\nThese paths contain important context for your task. " "Review them before starting work.",
            )

        return "\n".join(content_parts)


class FilesystemOperationsSection(SystemPromptSection):
    """
    Filesystem tool usage instructions.

    Documents how to use filesystem tools for creating answers, managing
    files, and coordinating with other agents.
    """

    def __init__(self, operations_content: str):
        super().__init__(
            title="Filesystem Operations",
            priority=Priority.MEDIUM,
            xml_tag="filesystem_operations",
        )
        self.operations_content = operations_content

    def build_content(self) -> str:
        return self.operations_content


class FilesystemBestPracticesSection(SystemPromptSection):
    """
    Optional filesystem best practices and tips.

    Lower priority guidance about workspace cleanup, comparison tools, etc.
    """

    def __init__(self, best_practices_content: str):
        super().__init__(
            title="Filesystem Best Practices",
            priority=Priority.AUXILIARY,
            xml_tag="filesystem_best_practices",
        )
        self.best_practices_content = best_practices_content

    def build_content(self) -> str:
        return self.best_practices_content


class FilesystemSection(SystemPromptSection):
    """
    Parent section for all filesystem-related instructions.

    Breaks the monolithic filesystem instructions into three prioritized
    subsections:
    1. Workspace structure (HIGH) - Must-know paths
    2. Operations (MEDIUM) - Tool usage
    3. Best practices (AUXILIARY) - Optional guidance

    Args:
        workspace_path: Path to agent's workspace
        context_paths: List of context paths
        operations_content: Tool usage instructions
        best_practices_content: Optional guidance
    """

    def __init__(
        self,
        workspace_path: str,
        context_paths: List[str],
        operations_content: str,
        best_practices_content: str,
    ):
        super().__init__(
            title="Filesystem & Workspace",
            priority=Priority.HIGH,
            xml_tag="filesystem",
        )

        # Create subsections with appropriate priorities
        self.subsections = [
            WorkspaceStructureSection(workspace_path, context_paths),
            FilesystemOperationsSection(operations_content),
            FilesystemBestPracticesSection(best_practices_content),
        ]

    def build_content(self) -> str:
        """Brief intro - subsections contain the details."""
        return "# Filesystem Instructions\n\n" "You have access to a filesystem-based workspace for managing your work " "and coordinating with other agents."


class TaskPlanningSection(SystemPromptSection):
    """
    Task planning guidance for complex multi-step tasks.

    Args:
        planning_guidance: The planning guidance content from message_templates
    """

    def __init__(self, planning_guidance: str):
        super().__init__(
            title="Task Planning",
            priority=Priority.MEDIUM,
            xml_tag="task_planning",
        )
        self.planning_guidance = planning_guidance

    def build_content(self) -> str:
        return self.planning_guidance


class EvaluationSection(SystemPromptSection):
    """
    MassGen evaluation and coordination mechanics.

    CRITICAL priority because this defines the fundamental MassGen primitives
    that the agent needs to understand: vote tool, new_answer tool, and
    coordination mechanics. This is foundational knowledge, not task-specific.

    Args:
        evaluation_instructions: The evaluation system message content
    """

    def __init__(self, evaluation_instructions: str):
        super().__init__(
            title="MassGen Coordination",
            priority=Priority.CRITICAL,
            xml_tag="massgen_coordination",
        )
        self.evaluation_instructions = evaluation_instructions

    def build_content(self) -> str:
        return self.evaluation_instructions


class PlanningModeSection(SystemPromptSection):
    """
    Planning mode instructions (conditional).

    Only included when planning mode is enabled. Instructs agent to
    think through approach before executing.

    Args:
        planning_mode_instruction: The planning mode instruction text
    """

    def __init__(self, planning_mode_instruction: str):
        super().__init__(
            title="Planning Mode",
            priority=Priority.MEDIUM,
            xml_tag="planning_mode",
        )
        self.planning_mode_instruction = planning_mode_instruction

    def build_content(self) -> str:
        return self.planning_mode_instruction


class SystemPromptBuilder:
    """
    Builder for assembling system prompts from sections.

    Automatically handles:
    - Priority-based sorting
    - XML structure wrapping
    - Conditional section inclusion (via enabled flag)
    - Hierarchical subsection rendering

    Example:
        >>> builder = SystemPromptBuilder()
        >>> builder.add_section(AgentIdentitySection("You are..."))
        >>> builder.add_section(SkillsSection(skills=[...]))
        >>> system_prompt = builder.build()
    """

    def __init__(self):
        self.sections: List[SystemPromptSection] = []

    def add_section(self, section: SystemPromptSection) -> "SystemPromptBuilder":
        """
        Add a section to the builder.

        Args:
            section: SystemPromptSection instance to add

        Returns:
            Self for method chaining (builder pattern)
        """
        self.sections.append(section)
        return self

    def build(self) -> str:
        """
        Assemble the final system prompt.

        Process:
        1. Filter to enabled sections only
        2. Sort by priority (lower number = earlier in prompt)
        3. Render each section (with XML if specified)
        4. Join with blank lines
        5. Wrap in root <system_prompt> XML tag

        Returns:
            Complete system prompt string ready for use
        """
        # Filter to enabled sections only
        enabled_sections = [s for s in self.sections if s.enabled]

        # Sort by priority (CRITICAL=1 comes before LOW=15)
        sorted_sections = sorted(enabled_sections, key=lambda s: s.priority)

        # Render each section
        rendered_sections = [s.render() for s in sorted_sections]

        # Join with blank lines and wrap in root tag
        content = "\n\n".join(rendered_sections)

        return f"<system_prompt>\n\n{content}\n\n</system_prompt>"
