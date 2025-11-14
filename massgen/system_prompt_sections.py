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
            # Handle both Priority enum and raw integers
            if isinstance(self.priority, Priority):
                priority_name = self.priority.name.lower()
            else:
                # Map integer priorities to names
                priority_map = {1: "critical", 2: "critical", 3: "critical", 4: "critical", 5: "high", 10: "medium", 15: "low", 20: "auxiliary"}
                priority_name = priority_map.get(self.priority, "medium")
            return f'<{self.xml_tag} priority="{priority_name}">\n{content}\n</{self.xml_tag}>'

        return content


class AgentIdentitySection(SystemPromptSection):
    """
    Agent's core identity: role, expertise, personality.

    This section ALWAYS comes first (Priority 1) to establish
    WHO the agent is before any operational instructions.
    Skips rendering if empty.

    Args:
        agent_message: The agent's custom system message from
                      agent.get_configurable_system_message()
    """

    def __init__(self, agent_message: str):
        super().__init__(
            title="Agent Identity",
            priority=1,  # First, before massgen_coordination(2) and core_behaviors(3)
            xml_tag="agent_identity",
        )
        self.agent_message = agent_message

    def build_content(self) -> str:
        return self.agent_message

    def render(self) -> str:
        """Skip rendering if agent message is empty."""
        if not self.agent_message or not self.agent_message.strip():
            return ""
        return super().render()


class CoreBehaviorsSection(SystemPromptSection):
    """
    Core behavioral principles for Claude agents.

    Includes critical guidance on:
    - Default to action vs suggestion
    - Parallel tool calling
    - File cleanup

    Based on Anthropic Claude 4 best practices.
    Priority 4 puts this after agent_identity(1), massgen_coordination(2), and skills(3).
    """

    def __init__(self):
        super().__init__(
            title="Core Behaviors",
            priority=4,  # After agent_identity(1), massgen_coordination(2), skills(3)
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

    CRITICAL priority (3) ensures skills appear before general behaviors.
    Skills define fundamental capabilities that must be known before task execution.

    Args:
        skills: List of all skills (both builtin and project) with name, description, location
    """

    def __init__(self, skills: List[Dict[str, Any]]):
        super().__init__(
            title="Available Skills",
            priority=3,  # After agent_identity(1) and massgen_coordination(2), before core_behaviors(4)
            xml_tag="skills",
        )
        self.skills = skills

    def build_content(self) -> str:
        """Build skills in XML format with full descriptions."""
        content_parts = []

        # Header
        content_parts.append("## Available Skills")
        content_parts.append("")
        content_parts.append("<!-- SKILLS_TABLE_START -->")

        # Usage instructions
        content_parts.append("<usage>")
        content_parts.append("When users ask you to perform tasks, check if any of the available skills below can help complete the task more effectively.")
        content_parts.append("")
        content_parts.append("How to use skills:")
        content_parts.append('- Invoke: execute_command("openskills read <skill-name>")')
        content_parts.append("- The skill content will load with detailed instructions")
        content_parts.append("- Base directory provided in output for resolving bundled resources")
        content_parts.append("")
        content_parts.append("Usage notes:")
        content_parts.append("- Only use skills listed in <available_skills> below")
        content_parts.append("- Do not invoke a skill that is already loaded in your context")
        content_parts.append("</usage>")
        content_parts.append("")

        # Skills list (project skills only - builtin skills are auto-loaded elsewhere)
        content_parts.append("<available_skills>")

        # Add project skills only
        for skill in self.skills:
            name = skill.get("name", "Unknown")
            description = skill.get("description", "No description")
            location = skill.get("location", "project")

            content_parts.append("")
            content_parts.append("<skill>")
            content_parts.append(f"<name>{name}</name>")
            content_parts.append(f"<description>{description}</description>")
            content_parts.append(f"<location>{location}</location>")
            content_parts.append("</skill>")

        content_parts.append("")
        content_parts.append("</available_skills>")
        content_parts.append("<!-- SKILLS_TABLE_END -->")

        return "\n".join(content_parts)


class FileSearchSection(SystemPromptSection):
    """
    Lightweight file search guidance for ripgrep and ast-grep.

    This provides essential usage patterns for the pre-installed search tools.
    For comprehensive guidance, agents can invoke: execute_command("openskills read file-search")

    MEDIUM priority - useful but not critical for all tasks.
    """

    def __init__(self):
        super().__init__(
            title="File Search Tools",
            priority=Priority.MEDIUM,
            xml_tag="file_search_tools",
        )

    def build_content(self) -> str:
        """Build concise file search guidance."""
        return """## File Search Tools

You have access to fast search tools for code exploration:

**ripgrep (rg)** - Fast text/regex search:
```bash
# Search with file type filtering
rg "pattern" --type py --type js

# Common flags: -i (case-insensitive), -w (whole words), -l (files only), -C N (context lines)
rg "function.*login" --type js src/
```

**ast-grep (sg)** - Structural code search:
```bash
# Find code patterns by syntax
sg --pattern 'function $NAME($$$) { $$$ }' --lang js

# Metavariables: $VAR (single node), $$$ (zero or more nodes)
sg --pattern 'class $NAME { $$$ }' --lang python
```

**Key principles:**
- Start narrow: Specify file types (--type py) and directories (src/)
- Count first: Use `rg "pattern" --count` to check result volume before full search
- Limit output: Pipe to `head -N` if results are large
- Use rg for text, sg for code structure

For detailed guidance including targeting strategies and examples, invoke: `execute_command("openskills read file-search")`"""


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


class CommandExecutionSection(SystemPromptSection):
    """
    Command execution environment and instructions.

    Documents the execution environment (Docker vs native), available packages,
    and any restrictions.

    NOTE: Package list is manually maintained and should match massgen/docker/Dockerfile.
    TODO: Consider auto-generating this from the Dockerfile for accuracy.

    Args:
        docker_mode: Whether commands execute in Docker containers
        enable_sudo: Whether sudo is available in Docker containers
    """

    def __init__(self, docker_mode: bool = False, enable_sudo: bool = False):
        super().__init__(
            title="Command Execution",
            priority=Priority.MEDIUM,
            xml_tag="command_execution",
        )
        self.docker_mode = docker_mode
        self.enable_sudo = enable_sudo

    def build_content(self) -> str:
        parts = ["## Command Execution"]
        parts.append("You can run command line commands using the `execute_command` tool.\n")

        if self.docker_mode:
            parts.append("**IMPORTANT: Docker Execution Environment**")
            parts.append("- You are running in a Linux Docker container (Debian-based)")
            parts.append("- Base image: Python 3.11-slim with Node.js 20.x LTS")
            parts.append(
                "- Pre-installed packages:\n"
                "  - System: git, curl, build-essential, ripgrep, gh (GitHub CLI)\n"
                "  - Python: pytest, requests, numpy, pandas, ast-grep-cli\n"
                "  - Node: npm, openskills (global)",
            )
            parts.append("- Use `apt-get` for system packages (NOT brew, dnf, yum, etc.)")

            if self.enable_sudo:
                parts.append(
                    "- **Sudo is available**: You can install packages with " "`sudo apt-get install <package>`",
                )
                parts.append("- Example: `sudo apt-get update && sudo apt-get install -y ffmpeg`")
            else:
                parts.append("- Sudo is NOT available - use pip/npm for user-level packages only")
                parts.append(
                    "- For system packages, ask the user to rebuild the Docker image with " "needed packages",
                )

            parts.append("")

        return "\n".join(parts)


class FilesystemOperationsSection(SystemPromptSection):
    """
    Filesystem tool usage instructions.

    Documents how to use filesystem tools for creating answers, managing
    files, and coordinating with other agents.

    Args:
        main_workspace: Path to agent's main workspace
        temp_workspace: Path to shared reference workspace
        context_paths: List of context paths with permissions
        previous_turns: List of previous turn metadata
        workspace_prepopulated: Whether workspace is pre-populated
        agent_answers: Dict of agent answers to show workspace structure
        enable_command_execution: Whether command line execution is enabled
    """

    def __init__(
        self,
        main_workspace: Optional[str] = None,
        temp_workspace: Optional[str] = None,
        context_paths: Optional[List[Dict[str, str]]] = None,
        previous_turns: Optional[List[Dict[str, Any]]] = None,
        workspace_prepopulated: bool = False,
        agent_answers: Optional[Dict[str, str]] = None,
        enable_command_execution: bool = False,
    ):
        super().__init__(
            title="Filesystem Operations",
            priority=Priority.MEDIUM,
            xml_tag="filesystem_operations",
        )
        self.main_workspace = main_workspace
        self.temp_workspace = temp_workspace
        self.context_paths = context_paths or []
        self.previous_turns = previous_turns or []
        self.workspace_prepopulated = workspace_prepopulated
        self.agent_answers = agent_answers
        self.enable_command_execution = enable_command_execution

    def build_content(self) -> str:
        parts = ["## Filesystem Access"]

        # Explain workspace behavior
        parts.append(
            "Your working directory is set to your workspace, so all relative paths in your file "
            "operations will be resolved from there. This ensures each agent works in isolation "
            "while having access to shared references. Only include in your workspace files that "
            "should be used in your answer.\n",
        )

        if self.main_workspace:
            workspace_note = f"**Your Workspace**: `{self.main_workspace}` - Write actual files here using " "file tools. All your file operations will be relative to this directory."
            if self.workspace_prepopulated:
                workspace_note += (
                    " **Note**: Your workspace already contains a writable copy of the previous "
                    "turn's results - you can modify or build upon these files. The original "
                    "unmodified version is also available as a read-only context path if you need "
                    "to reference what was originally there."
                )
            parts.append(workspace_note)

        if self.temp_workspace:
            # Build workspace tree structure
            workspace_tree = f"**Shared Reference**: `{self.temp_workspace}` - Contains previous answers from " "all agents (read/execute-only)\n"

            # Add agent subdirectories in tree format
            if self.agent_answers:
                agent_mapping = {}
                for i, agent_id in enumerate(sorted(self.agent_answers.keys()), 1):
                    agent_mapping[agent_id] = f"agent{i}"

                workspace_tree += "   Available agent workspaces:\n"
                agent_items = list(agent_mapping.items())
                for idx, (agent_id, anon_id) in enumerate(agent_items):
                    is_last = idx == len(agent_items) - 1
                    prefix = "   └── " if is_last else "   ├── "
                    workspace_tree += f"{prefix}{self.temp_workspace}/{anon_id}/\n"

            workspace_tree += (
                "   **Building on Others' Work:**\n"
                "   - **Inspect First**: Use `read_file`, `read_multiple_files`, or other command "
                "line tools to examine files before copying. Understand what you're working with.\n"
                "   - **Selective Copying**: Only copy specific files you'll actually modify or "
                "use. Use `copy_file` for individual files, not `copy_directory` for wholesale "
                "copying.\n"
                "   - **Merging Approaches**: If combining work from multiple agents, consider "
                "merging complementary parts (e.g., agent1's data model + agent2's API layer) "
                "rather than picking one entire solution.\n"
                "   - **Attribution**: Be explicit in your answer about what you built on (e.g., "
                "'Extended agent1's parser.py to handle edge cases').\n"
                "   - **Verify Files**: Not all workspaces may have matching answers in CURRENT "
                "ANSWERS section (restart scenarios). Check actual files in Shared Reference.\n"
            )
            parts.append(workspace_tree)

        if self.context_paths:
            has_target = any(p.get("will_be_writable", False) for p in self.context_paths)
            has_readonly_context = any(not p.get("will_be_writable", False) and p.get("permission") == "read" for p in self.context_paths)

            if has_target:
                parts.append(
                    "\n**Important Context**: If the user asks about improving, fixing, debugging, "
                    "or understanding an existing code/project (e.g., 'Why is this code not "
                    "working?', 'Fix this bug', 'Add feature X'), they are referring to the Target "
                    "Path below. First READ the existing files from that path to understand what's "
                    "there, then make your changes based on that codebase. Final deliverables must "
                    "end up there.\n",
                )
            elif has_readonly_context:
                parts.append(
                    "\n**Important Context**: If the user asks about debugging or understanding an "
                    "existing code/project (e.g., 'Why is this code not working?', 'Explain this "
                    "bug'), they are referring to (one of) the Context Path(s) below. Read then "
                    "provide analysis/explanation based on that codebase - you cannot modify it "
                    "directly.\n",
                )

            for path_config in self.context_paths:
                path = path_config.get("path", "")
                permission = path_config.get("permission", "read")
                will_be_writable = path_config.get("will_be_writable", False)
                if path:
                    if permission == "read" and will_be_writable:
                        parts.append(
                            f"**Target Path**: `{path}` (read-only now, write access later) - This "
                            "is where your changes will be delivered. Work in your workspace first, "
                            f"then the final presenter will place or update files DIRECTLY into "
                            f"`{path}` using the FULL ABSOLUTE PATH.",
                        )
                    elif permission == "write":
                        parts.append(
                            f"**Target Path**: `{path}` (write access) - This is where your changes "
                            "must be delivered. First, ensure you place your answer in your "
                            f"workspace, then copy/write files DIRECTLY into `{path}` using FULL "
                            f"ABSOLUTE PATH (not relative paths). Files must go directly into the "
                            f"target path itself (e.g., `{path}/file.txt`), NOT into a `.massgen/` "
                            "subdirectory within it.",
                        )
                    else:
                        parts.append(
                            f"**Context Path**: `{path}` (read-only) - Use FULL ABSOLUTE PATH when " "reading.",
                        )

        # Add note about multi-turn conversations
        if self.previous_turns:
            parts.append(
                "\n**Note**: This is a multi-turn conversation. Each User/Assistant exchange in "
                "the conversation history represents one turn. The workspace from each turn is "
                "available as a read-only context path listed above (e.g., turn 1's workspace is "
                "at the path ending in `/turn_1/workspace`).",
            )

        # Add task handling priority
        parts.append(
            "\n**Task Handling Priority**: When responding to user requests, follow this priority "
            "order:\n"
            "1. **Use MCP Tools First**: If you have specialized MCP tools available, call them "
            "DIRECTLY to complete the task\n"
            "   - Save any outputs/artifacts from MCP tools to your workspace\n"
            "2. **Write Code If Needed**: If MCP tools cannot complete the task, write and execute "
            "code\n"
            "3. **Create Other Files**: Create configs, documents, or other deliverables as "
            "needed\n"
            "4. **Text Response Otherwise**: If no tools or files are needed, provide a direct "
            "text answer\n\n"
            "**Important**: Do NOT ask the user for clarification or additional input. Make "
            "reasonable assumptions and proceed with sensible defaults. You will not receive user "
            "feedback, so complete the task autonomously based on the original request.\n",
        )

        # Add new answer guidance
        new_answer_guidance = "\n**New Answer**: When calling `new_answer`:\n"
        if self.enable_command_execution:
            new_answer_guidance += "- If you executed commands (e.g., running tests), explain the results in your " "answer (what passed, what failed, what the output shows)\n"
        new_answer_guidance += "- If you created files, list your cwd and file paths (but do NOT paste full file " "contents)\n"
        new_answer_guidance += "- If providing a text response, include your analysis/explanation in the `content` " "field\n"
        parts.append(new_answer_guidance)

        return "\n".join(parts)


class FilesystemBestPracticesSection(SystemPromptSection):
    """
    Optional filesystem best practices and tips.

    Lower priority guidance about workspace cleanup, comparison tools, and evaluation.
    """

    def __init__(self):
        super().__init__(
            title="Filesystem Best Practices",
            priority=Priority.AUXILIARY,
            xml_tag="filesystem_best_practices",
        )

    def build_content(self) -> str:
        parts = []

        # Workspace management guidance
        parts.append(
            "**Workspace Management**: \n"
            "- **Selective Copying**: When building on other agents' work, only copy the specific "
            "files you need to modify or use. Do not copy entire workspaces wholesale. Be explicit "
            "about what you're building on (e.g., 'Using agent1's parser.py with "
            "modifications').\n"
            "- **Cleanup**: Remove any temporary files, intermediate artifacts, test scripts, or "
            "unused files copied from another agent before submitting `new_answer`. Your workspace "
            "should contain only the files that are part of your final deliverable. For example, "
            "if you created `test_output.txt` for debugging or `old_version.py` before "
            "refactoring, delete them.\n"
            "- **Organization**: Keep files logically organized. If you're combining work from "
            "multiple agents, structure the result clearly.\n",
        )

        # Comparison tools
        parts.append(
            "**Comparison Tools**: Use `compare_directories` to see differences between two "
            "directories (e.g., comparing your workspace to another agent's workspace or a previous "
            "version), or `compare_files` to see line-by-line diffs between two files. These "
            "read-only tools help you understand what changed, build upon existing work "
            "effectively, or verify solutions before voting.\n",
        )

        # Evaluation guidance
        parts.append(
            "**Evaluation**: When evaluating agents' answers, do NOT base your decision solely on "
            "the answer text. Instead, read and verify the actual files in their workspaces (via "
            "Shared Reference) to ensure the work matches their claims.\n",
        )

        return "\n".join(parts)


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
        main_workspace: Path to agent's main workspace
        temp_workspace: Path to shared reference workspace
        previous_turns: List of previous turn metadata
        workspace_prepopulated: Whether workspace is pre-populated
        agent_answers: Dict of agent answers to show workspace structure
        enable_command_execution: Whether command line execution is enabled
        docker_mode: Whether commands execute in Docker containers
        enable_sudo: Whether sudo is available in Docker containers
    """

    def __init__(
        self,
        workspace_path: str,
        context_paths: List[str],
        main_workspace: Optional[str] = None,
        temp_workspace: Optional[str] = None,
        context_paths_detailed: Optional[List[Dict[str, str]]] = None,
        previous_turns: Optional[List[Dict[str, Any]]] = None,
        workspace_prepopulated: bool = False,
        agent_answers: Optional[Dict[str, str]] = None,
        enable_command_execution: bool = False,
        docker_mode: bool = False,
        enable_sudo: bool = False,
    ):
        super().__init__(
            title="Filesystem & Workspace",
            priority=Priority.HIGH,
            xml_tag="filesystem",
        )

        # Create subsections with appropriate priorities
        self.subsections = [
            WorkspaceStructureSection(workspace_path, context_paths),
            FilesystemOperationsSection(
                main_workspace=main_workspace,
                temp_workspace=temp_workspace,
                context_paths=context_paths_detailed,
                previous_turns=previous_turns,
                workspace_prepopulated=workspace_prepopulated,
                agent_answers=agent_answers,
                enable_command_execution=enable_command_execution,
            ),
            FilesystemBestPracticesSection(),
        ]

        # Add command execution section if enabled
        if enable_command_execution:
            self.subsections.append(
                CommandExecutionSection(docker_mode=docker_mode, enable_sudo=enable_sudo),
            )

    def build_content(self) -> str:
        """Brief intro - subsections contain the details."""
        return "# Filesystem Instructions\n\n" "You have access to a filesystem-based workspace for managing your work " "and coordinating with other agents."


class TaskPlanningSection(SystemPromptSection):
    """
    Task planning guidance for complex multi-step tasks.

    Provides comprehensive instructions on when and how to use task planning
    tools for organizing multi-step work.

    Args:
        filesystem_mode: If True, includes guidance about filesystem-based task storage
    """

    def __init__(self, filesystem_mode: bool = False):
        super().__init__(
            title="Task Planning",
            priority=Priority.MEDIUM,
            xml_tag="task_planning",
        )
        self.filesystem_mode = filesystem_mode

    def build_content(self) -> str:
        base_guidance = """
# Task Planning and Management

You have access to task planning tools to organize complex work.

**IMPORTANT WORKFLOW - Plan Before Executing:**

When working on multi-step tasks:
1. **Think first** - Understand the requirements (some initial research/analysis is fine)
2. **Create your task plan EARLY** - Use `create_task_plan()` BEFORE executing file operations or major
   actions
3. **Execute tasks** - Work through your plan systematically
4. **Update as you go** - Use `add_task()` to capture new requirements you discover

**DO NOT:**
- ❌ Jump straight into creating files without planning first
- ❌ Start executing complex work without a clear task breakdown
- ❌ Ignore the planning tools for multi-step work

**DO:**
- ✅ Create a task plan early, even if it's just 3-4 high-level tasks
- ✅ Refine your plan as you learn more (tasks can be added/edited/deleted)
- ✅ Brief initial analysis is OK before planning (e.g., reading docs, checking existing code)

**When to create a task plan:**
- Multi-step tasks with dependencies (most common)
- Multiple files or components to create
- Complex features requiring coordination
- Work that needs to be tracked or broken down
- Any task where you'd benefit from a checklist

**Skip task planning ONLY for:**
- Trivial single-step tasks
- Simple questions/analysis with no execution
- Quick one-off operations

**Tools available:**
- `create_task_plan(tasks)` - Create a plan with tasks and dependencies
- `get_ready_tasks()` - Get tasks ready to start (dependencies satisfied)
- `get_blocked_tasks()` - See what's waiting on dependencies
- `update_task_status(task_id, status)` - Mark progress (pending/in_progress/completed)
- `add_task(description, depends_on)` - Add new tasks as you discover them
- `get_task_plan()` - View your complete task plan
- `edit_task(task_id, description)` - Update task descriptions
- `delete_task(task_id)` - Remove tasks no longer needed

**Recommended workflow:**
```python
# 1. Create plan FIRST (before major execution)
plan = create_task_plan([
    {"id": "research", "description": "Research OAuth providers"},
    {"id": "design", "description": "Design auth flow", "depends_on": ["research"]},
    {"id": "implement", "description": "Implement endpoints", "depends_on": ["design"]}
])

# 2. Work through tasks systematically
update_task_status("research", "in_progress")
# ... do research work ...
update_task_status("research", "completed")

# 3. Add tasks as you discover new requirements
add_task("Write integration tests", depends_on=["implement"])

# 4. Continue working
ready = get_ready_tasks()  # ["design"]
update_task_status("design", "in_progress")
```

**Dependency formats:**
```python
# By index (0-based)
create_task_plan([
    "Task 1",
    {"description": "Task 2", "depends_on": [0]}  # Depends on Task 1
])

# By ID (recommended for clarity)
create_task_plan([
    {"id": "auth", "description": "Setup auth"},
    {"id": "api", "description": "Build API", "depends_on": ["auth"]}
])
```

**IMPORTANT - Including Task Plan in Your Answer:**
If you created a task plan, include a summary at the end of your `new_answer` showing:
1. Each task name
2. Completion status (✓ or ✗)
3. Brief description of what you did

Example format:
```
[Your main answer content here]

---
**Task Execution Summary:**
✓ Research OAuth providers - Analyzed OAuth 2.0 spec and compared providers
✓ Design auth flow - Created flow diagram with PKCE and token refresh
✓ Implement endpoints - Built /auth/login, /auth/callback, /auth/refresh
✓ Write tests - Added integration tests for auth flow

Status: 4/4 tasks completed
```

This helps other agents understand your approach and makes voting more specific."""

        if self.filesystem_mode:
            filesystem_guidance = """

**Filesystem Mode Enabled:**
Your task plans are automatically saved to `tasks/plan.json` in your workspace. You can write notes
or comments in `tasks/notes.md` or other files in the `tasks/` directory.

*NOTE*: You will also have access to other agents' task plans in the shared reference."""
            return base_guidance + filesystem_guidance

        return base_guidance


class EvaluationSection(SystemPromptSection):
    """
    MassGen evaluation and coordination mechanics.

    Priority 2 places this after agent_identity(1) but before core_behaviors(3).
    This defines the fundamental MassGen primitives that the agent needs to understand:
    vote tool, new_answer tool, and coordination mechanics.

    Args:
        voting_sensitivity: Controls evaluation strictness ('lenient', 'balanced', 'strict')
        answer_novelty_requirement: Controls novelty requirements ('lenient', 'balanced', 'strict')
    """

    def __init__(
        self,
        voting_sensitivity: str = "lenient",
        answer_novelty_requirement: str = "lenient",
    ):
        super().__init__(
            title="MassGen Coordination",
            priority=2,  # After agent_identity(1), before core_behaviors(3)
            xml_tag="massgen_coordination",
        )
        self.voting_sensitivity = voting_sensitivity
        self.answer_novelty_requirement = answer_novelty_requirement

    def build_content(self) -> str:
        import time

        # Determine evaluation criteria based on voting sensitivity
        if self.voting_sensitivity == "strict":
            evaluation_section = """Does the best CURRENT ANSWER address the ORIGINAL MESSAGE exceptionally well? Consider:
- Is it comprehensive, addressing ALL aspects and edge cases?
- Is it technically accurate and well-reasoned?
- Does it provide clear explanations and proper justification?
- Is it complete with no significant gaps or weaknesses?
- Could it serve as a reference-quality solution?

Only use the `vote` tool if the best answer meets high standards of excellence."""
        elif self.voting_sensitivity == "balanced":
            evaluation_section = """Does the best CURRENT ANSWER address the ORIGINAL MESSAGE well? Consider:
- Is it comprehensive, accurate, and complete?
- Could it be meaningfully improved, refined, or expanded?
- Are there weaknesses, gaps, or better approaches?

Only use the `vote` tool if the best answer is strong and complete."""
        else:
            # Default to lenient (including explicit "lenient" or any other value)
            evaluation_section = """Does the best CURRENT ANSWER address the ORIGINAL MESSAGE well?

If YES, use the `vote` tool to record your vote and skip the `new_answer` tool."""

        # Add novelty requirement instructions if not lenient
        novelty_section = ""
        if self.answer_novelty_requirement == "balanced":
            novelty_section = """
IMPORTANT: If you provide a new answer, it must be meaningfully different from existing answers.
- Don't just rephrase or reword existing solutions
- Introduce new insights, approaches, or tools
- Make substantive improvements, not cosmetic changes"""
        elif self.answer_novelty_requirement == "strict":
            novelty_section = """
CRITICAL: New answers must be SUBSTANTIALLY different from existing answers.
- Use a fundamentally different approach or methodology
- Employ different tools or techniques
- Provide significantly more depth or novel perspectives
- If you cannot provide a truly novel solution, vote instead"""

        return f"""You are evaluating answers from multiple agents for final response to a message.
Different agents may have different builtin tools and capabilities.
{evaluation_section}
Otherwise, digest existing answers, combine their strengths, and do additional work to address their weaknesses,
then use the `new_answer` tool to record a better answer to the ORIGINAL MESSAGE.{novelty_section}
Make sure you actually call `vote` or `new_answer` (in tool call format).

*Note*: The CURRENT TIME is **{time.strftime("%Y-%m-%d %H:%M:%S")}**."""


class PostEvaluationSection(SystemPromptSection):
    """
    Post-evaluation phase instructions.

    After final presentation, the winning agent evaluates its own answer
    and decides whether to submit or restart with improvements.

    MEDIUM priority as this is phase-specific operational guidance.
    """

    def __init__(self):
        super().__init__(
            title="Post-Presentation Evaluation",
            priority=Priority.MEDIUM,
            xml_tag="post_evaluation",
        )

    def build_content(self) -> str:
        return """## Post-Presentation Evaluation

You have just presented a final answer to the user. Now you must evaluate whether your answer fully addresses the original task.

**Your Task:**
Review the final answer that was presented and determine if it completely and accurately addresses the original task requirements.

**Available Tools:**
You have access to the same filesystem and MCP tools that were available during presentation. Use these tools to:
- Verify that claimed files actually exist in the workspace
- Check file contents to confirm they match what was described
- Validate any technical claims or implementations

**Decision:**
You must call ONE of these tools:

1. **submit(confirmed=True)** - Use this when:
   - The answer fully addresses ALL parts of the original task
   - All claims in the answer are accurate and verified
   - The work is complete and ready for the user

2. **restart_orchestration(reason, instructions)** - Use this when:
   - The answer is incomplete (missing required elements)
   - The answer contains errors or inaccuracies
   - Important aspects of the task were not addressed

   Provide:
   - **reason**: Clear explanation of what's wrong (e.g., "The task required descriptions of two Beatles, but only John Lennon was described")
   - **instructions**: Detailed, actionable guidance for the next attempt (e.g.,
     "Provide two descriptions (John Lennon AND Paul McCartney). Each should include:
     birth year, role in band, notable songs, impact on music. Use 4-6 sentences per person.")

**Important Notes:**
- Be honest and thorough in your evaluation
- You are evaluating your own work with a fresh perspective
- If you find problems, restarting with clear instructions will lead to a better result
- The restart process gives you another opportunity to get it right
"""


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
