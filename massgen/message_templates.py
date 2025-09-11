"""
Message templates for MassGen framework following input_cases_reference.md
Implements proven binary decision framework that eliminates perfectionism loops.
"""

import re
from typing import Dict, Any, Optional, List


class MessageTemplates:
    """Message templates implementing the proven MassGen approach."""

    def __init__(self, **template_overrides):
        """Initialize with optional template overrides."""
        self._template_overrides = template_overrides

    # =============================================================================
    # SYSTEM MESSAGE TEMPLATES
    # =============================================================================

    def evaluation_system_message(self) -> str:
        """Standard evaluation system message for all cases."""
        if "evaluation_system_message" in self._template_overrides:
            return str(self._template_overrides["evaluation_system_message"])

        import time

        #         return f"""You are evaluating answers from multiple agents for final response to a message.

        # For every aspect, claim, and reasoning step in the CURRENT ANSWERS, verify correctness, factual accuracy, and completeness using your expertise, reasoning, and **available tools**.

        # **You must use at least one tool in every evaluation round**—this is mandatory.

        # - If the CURRENT ANSWERS fully address the ORIGINAL MESSAGE, use the `vote` tool to record your vote and skip the `new_answer` tool.
        # - If the CURRENT ANSWERS are incomplete, incorrect, or do not fully address the ORIGINAL MESSAGE, conduct any necessary reasoning or research using tools (such as `search`), and then use the `new_answer` tool to submit a new response.

        # Your new answer must be self-contained, process-complete, well-sourced, and compelling—ready to serve as the final reply.

        # **Important**:
        # - You must actually call at least one tool per round.
        # - If no other tools are relevant or available, you must use either `new_answer` or `vote` to fulfill the tool-use requirement.

        # *Note*: The CURRENT TIME is **{time.strftime("%Y-%m-%d %H:%M:%S")}**.
        # For any time-sensitive requests, use the `search` tool (if available) rather than relying on prior knowledge.
        # """

        # return f"""You are evaluating answers from multiple agents for final response to a message.

        # For every aspect, claim, reasoning steps in the CURRENT ANSWERS, verify correctness, factual accuracy, and completeness using your expertise, reasoning, and available tools.

        # If the CURRENT ANSWERS fully address the ORIGINAL MESSAGE, use the `vote` tool to record your vote and skip the `new_answer` tool.

        # If the CURRENT ANSWERS are incomplete, incorrect, or not fully address the ORIGINAL MESSAGE, conduct any necessary reasoning or research. Then, use the `new_answer` tool to submit a new response.

        # Your new answer must be self-contained, process-complete, well-sourced, and compelling—ready to serve as the final reply.

        # **Important**: Be sure to actually call the `new_answer` tool to submit your new answer (use native tool call format).

        # *Note*: The CURRENT TIME is **{time.strftime("%Y-%m-%d %H:%M:%S")}**.
        # For any time-sensitive requests, use the search tool (if available) rather than relying on prior knowledge."""

        # BACKUP - Original evaluation message (pre-synthesis-encouragement update):
        # return f"""You are evaluating answers from multiple agents for final response to a message. Does the best CURRENT ANSWER address the ORIGINAL MESSAGE?
        #
        # If YES, use the `vote` tool to record your vote and skip the `new_answer` tool.
        # Otherwise, digest existing answers, combine their strengths, and do additional work to address their weaknesses, then use the `new_answer` tool to record a better answer to the ORIGINAL MESSAGE. Make sure you actually call `vote` or `new_answer` (in tool call format).
        #
        # *Note*: The CURRENT TIME is **{time.strftime("%Y-%m-%d %H:%M:%S")}**."""

        return f"""You are evaluating answers from multiple agents for final response to a message. Different agents may have different builtin tools and capabilities. Does the best CURRENT ANSWER address the ORIGINAL MESSAGE well?

If YES, use the `vote` tool to record your vote and skip the `new_answer` tool.
Otherwise, digest existing answers, combine their strengths, and do additional work to address their weaknesses, then use the `new_answer` tool to record a better answer to the ORIGINAL MESSAGE. Make sure you actually call `vote` or `new_answer` (in tool call format).

*Note*: The CURRENT TIME is **{time.strftime("%Y-%m-%d %H:%M:%S")}**."""

    # =============================================================================
    # USER MESSAGE TEMPLATES
    # =============================================================================

    def format_original_message(self, task: str) -> str:
        """Format the original message section."""
        if "format_original_message" in self._template_overrides:
            override = self._template_overrides["format_original_message"]
            if callable(override):
                return override(task)
            return str(override).format(task=task)

        return f"<ORIGINAL MESSAGE> {task} <END OF ORIGINAL MESSAGE>"

    def format_conversation_history(
        self, conversation_history: List[Dict[str, str]]
    ) -> str:
        """Format conversation history for agent context."""
        if "format_conversation_history" in self._template_overrides:
            override = self._template_overrides["format_conversation_history"]
            if callable(override):
                return override(conversation_history)
            return str(override)

        if not conversation_history:
            return ""

        lines = ["<CONVERSATION_HISTORY>"]
        for message in conversation_history:
            role = message.get("role", "unknown")
            content = message.get("content", "")
            if role == "user":
                lines.append(f"User: {content}")
            elif role == "assistant":
                lines.append(f"Assistant: {content}")
            elif role == "system":
                # Skip system messages in history display
                continue
        lines.append("<END OF CONVERSATION_HISTORY>")
        return "\n".join(lines)

    def system_message_with_context(
        self, conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """Evaluation system message with conversation context awareness."""
        if "system_message_with_context" in self._template_overrides:
            override = self._template_overrides["system_message_with_context"]
            if callable(override):
                return override(conversation_history)
            return str(override)

        base_message = self.evaluation_system_message()

        if conversation_history and len(conversation_history) > 0:
            context_note = """
            
IMPORTANT: You are responding to the latest message in an ongoing conversation. Consider the full conversation context when evaluating answers and providing your response."""
            return base_message + context_note

        return base_message

    def format_current_answers_empty(self) -> str:
        """Format current answers section when no answers exist (Case 1)."""
        if "format_current_answers_empty" in self._template_overrides:
            return str(self._template_overrides["format_current_answers_empty"])

        return """<CURRENT ANSWERS from the agents>
(no answers available yet)
<END OF CURRENT ANSWERS>"""

    def format_current_answers_with_summaries(
        self, agent_summaries: Dict[str, str]
    ) -> str:
        """Format current answers section with agent summaries (Case 2) using anonymous agent IDs."""
        if "format_current_answers_with_summaries" in self._template_overrides:
            override = self._template_overrides["format_current_answers_with_summaries"]
            if callable(override):
                return override(agent_summaries)

        lines = ["<CURRENT ANSWERS from the agents>"]

        # Create anonymous mapping: agent1, agent2, etc.
        agent_mapping = {}
        for i, agent_id in enumerate(sorted(agent_summaries.keys()), 1):
            agent_mapping[agent_id] = f"agent{i}"

        for agent_id, summary in agent_summaries.items():
            anon_id = agent_mapping[agent_id]
            lines.append(f"<{anon_id}> {summary} <end of {anon_id}>")

        lines.append("<END OF CURRENT ANSWERS>")
        return "\n".join(lines)

    def enforcement_message(self) -> str:
        """Enforcement message for Case 3 (non-workflow responses)."""
        if "enforcement_message" in self._template_overrides:
            return str(self._template_overrides["enforcement_message"])

        return "Finish your work above by making a tool call of `vote` or `new_answer`. Make sure you actually call the tool."

    def tool_error_message(self, error_msg: str) -> Dict[str, str]:
        """Create a tool role message for tool usage errors."""
        return {"role": "tool", "content": error_msg}

    def enforcement_user_message(self) -> Dict[str, str]:
        """Create a user role message for enforcement."""
        return {"role": "user", "content": self.enforcement_message()}

    # =============================================================================
    # TOOL DEFINITIONS
    # =============================================================================

    def get_new_answer_tool(self) -> Dict[str, Any]:
        """Get new_answer tool definition.

        TODO: Consider extending with optional context parameters for stateful backends:
        - cwd: Working directory for Claude Code sessions
        - session_id: Backend session identifier for continuity
        - model: Model used to generate the answer
        - tools_used: List of tools actually utilized
        This would enable better context preservation in multi-iteration workflows.
        """
        if "new_answer_tool" in self._template_overrides:
            return self._template_overrides["new_answer_tool"]

        return {
            "type": "function",
            "function": {
                "name": "new_answer",
                "description": "Provide an improved answer to the ORIGINAL MESSAGE",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "Your improved answer. If any builtin tools like search or code execution were used, mention how they are used here.",
                        }
                    },
                    "required": ["content"],
                },
            },
        }

    def get_vote_tool(
        self, valid_agent_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Get vote tool definition with anonymous agent IDs."""
        if "vote_tool" in self._template_overrides:
            override = self._template_overrides["vote_tool"]
            if callable(override):
                return override(valid_agent_ids)
            return override

        tool_def = {
            "type": "function",
            "function": {
                "name": "vote",
                "description": "Vote for the best agent to present final answer",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "Anonymous agent ID to vote for (e.g., 'agent1', 'agent2')",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Brief reason why this agent has the best answer",
                        },
                    },
                    "required": ["agent_id", "reason"],
                },
            },
        }

        # Create anonymous mapping for enum constraint
        if valid_agent_ids:
            anon_agent_ids = [f"agent{i}" for i in range(1, len(valid_agent_ids) + 1)]
            tool_def["function"]["parameters"]["properties"]["agent_id"][
                "enum"
            ] = anon_agent_ids

        return tool_def

    def get_standard_tools(
        self, valid_agent_ids: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Get standard tools for MassGen framework."""
        return [self.get_new_answer_tool(), self.get_vote_tool(valid_agent_ids)]

    def final_presentation_system_message(
        self, original_system_message: Optional[str] = None
    ) -> str:
        """System message for final answer presentation by winning agent.

        Args:
            original_system_message: The agent's original system message to preserve
        """
        if "final_presentation_system_message" in self._template_overrides:
            return str(self._template_overrides["final_presentation_system_message"])

        # BACKUP - Original final presentation message (pre-explicit-synthesis update):
        # presentation_instructions = """You have been selected as the winning presenter in a coordination process. Your task is to present a polished, comprehensive final answer that incorporates the best insights from all participants.
        #
        # Consider:
        # 1. Your original response and how it can be refined
        # 2. Valuable insights from other agents' answers that should be incorporated
        # 3. Feedback received through the voting process
        # 4. Ensuring clarity, completeness, and comprehensiveness for the final audience
        #
        # Present your final coordinated answer in the most helpful and complete way possible."""

        presentation_instructions = """You have been selected as the winning presenter in a coordination process.
Present the best possible coordinated answer by combining the strengths from all participants."""

        # Combine with original system message if provided
        if original_system_message:
            return f"""{original_system_message}

{presentation_instructions}"""
        else:
            return presentation_instructions

    # =============================================================================
    # COMPLETE MESSAGE BUILDERS
    # =============================================================================

    def build_case1_user_message(self, task: str) -> str:
        """Build Case 1 user message (no summaries exist)."""
        return f"""{self.format_original_message(task)}

{self.format_current_answers_empty()}"""

    def build_case2_user_message(
        self, task: str, agent_summaries: Dict[str, str]
    ) -> str:
        """Build Case 2 user message (summaries exist)."""
        return f"""{self.format_original_message(task)}

{self.format_current_answers_with_summaries(agent_summaries)}"""

    def build_evaluation_message(
        self, task: str, agent_answers: Optional[Dict[str, str]] = None
    ) -> str:
        """Build evaluation user message for any case."""
        if agent_answers:
            return self.build_case2_user_message(task, agent_answers)
        else:
            return self.build_case1_user_message(task)

    def build_coordination_context(
        self,
        current_task: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        agent_answers: Optional[Dict[str, str]] = None,
    ) -> str:
        """Build coordination context including conversation history and current state."""
        if "build_coordination_context" in self._template_overrides:
            override = self._template_overrides["build_coordination_context"]
            if callable(override):
                return override(current_task, conversation_history, agent_answers)
            return str(override)

        context_parts = []

        # Add conversation history if present
        if conversation_history and len(conversation_history) > 0:
            history_formatted = self.format_conversation_history(conversation_history)
            if history_formatted:
                context_parts.append(history_formatted)
                context_parts.append("")  # Empty line for spacing

        # Add current task
        context_parts.append(self.format_original_message(current_task))
        context_parts.append("")  # Empty line for spacing

        # Add agent answers
        if agent_answers:
            context_parts.append(
                self.format_current_answers_with_summaries(agent_answers)
            )
        else:
            context_parts.append(self.format_current_answers_empty())

        return "\n".join(context_parts)

    # =============================================================================
    # CONVERSATION BUILDERS
    # =============================================================================

    def build_initial_conversation(
        self,
        task: str,
        agent_summaries: Optional[Dict[str, str]] = None,
        valid_agent_ids: Optional[List[str]] = None,
        base_system_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build complete initial conversation for MassGen evaluation."""
        # Use agent's custom system message if provided, otherwise use default evaluation message
        if base_system_message:
            system_message = (
                f"{base_system_message}\n\n{self.evaluation_system_message()}"
            )
        else:
            system_message = self.evaluation_system_message()

        return {
            "system_message": system_message,
            "user_message": self.build_evaluation_message(task, agent_summaries),
            "tools": self.get_standard_tools(valid_agent_ids),
        }

    def build_conversation_with_context(
        self,
        current_task: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        agent_summaries: Optional[Dict[str, str]] = None,
        valid_agent_ids: Optional[List[str]] = None,
        base_system_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build complete conversation with conversation history context for MassGen evaluation."""
        # Use agent's custom system message if provided, otherwise use default context-aware message
        if base_system_message:
            system_message = f"{base_system_message}\n\n{self.system_message_with_context(conversation_history)}"
        else:
            system_message = self.system_message_with_context(conversation_history)

        return {
            "system_message": system_message,
            "user_message": self.build_coordination_context(
                current_task, conversation_history, agent_summaries
            ),
            "tools": self.get_standard_tools(valid_agent_ids),
        }

    def build_final_presentation_message(
        self,
        original_task: str,
        vote_summary: str,
        all_answers: Dict[str, str],
        selected_agent_id: str,
    ) -> str:
        """Build final presentation message for winning agent."""
        # Format all answers with clear marking
        answers_section = "All answers provided during coordination:\n"
        for agent_id, answer in all_answers.items():
            marker = " (YOUR ANSWER)" if agent_id == selected_agent_id else ""
            answers_section += f'\n{agent_id}{marker}: "{answer}"\n'

        return f"""{self.format_original_message(original_task)}

VOTING RESULTS:
{vote_summary}

{answers_section}

Based on the coordination process above, present your final answer:"""

    def add_enforcement_message(
        self, conversation_messages: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        """Add enforcement message to existing conversation (Case 3)."""
        messages = conversation_messages.copy()
        messages.append({"role": "user", "content": self.enforcement_message()})
        return messages

    def filesystem_system_message(
        self, main_workspace: Optional[str] = None, temp_workspace: Optional[str] = None
    ) -> str:
        """Generate filesystem access instructions for agents with filesystem support.

        Args:
            main_workspace: Path to agent's main workspace
            temp_workspace: Path to temporary workspace for context sharing
        """
        if "filesystem_system_message" in self._template_overrides:
            return str(self._template_overrides["filesystem_system_message"])

        # Build workspace information
        workspace_info = []
        if main_workspace:
            workspace_info.append(f"1. **Your Main Workspace**: `{main_workspace}`")
            workspace_info.append(
                " - IMPORTANT: ALL your own work (like writing files and creating outputs) MUST be done in your working directory."
            )
            workspace_info.append(
                " - DO NOT look in your working directory for agent information - it's exclusively for creating YOUR OWN new work."
            )
            workspace_info.append(
                " - Use this for creating your own files and outputs if providing a new answer"
            )
            workspace_info.append(
                " - When providing a new answer, ensure you save any relevant files or outputs in your main workspace. Then, give a summary of your work in the answer content. Do NOT repeat the full file contents in your answer."
            )
            workspace_info.append(
                f" - Do NOT copy any files from the temporary workspace to your main workspace to use them. The only thing that should go in your main workspace is YOUR OWN work for your new answer."
            )

        if temp_workspace:
            workspace_info.append(f"2. **Context Workspace**: `{temp_workspace}`")
            workspace_info.append(
                f" - Context: You have access to a reference temporary workspace that contains work from yourself and other agents for REFERENCE ONLY."
            )
            workspace_info.append(
                " - CRITICAL: To understand your own or other agents' information, context, and work, ONLY check the temporary workspace."
            )
            workspace_info.append(
                " - You may READ documents or EXECUTE code from the temporary workspace to understand other agents' work."
            )
            workspace_info.append(
                " - When you READ or EXECUTE content from the temporary workspace, save any resulting outputs (analysis results, execution outputs, etc.) to the temporary workspace as well."
            )
            workspace_info.append(
                " - You do NOT need to copy any files from the temporary workspace to your main workspace to use them. You can read and execute them directly from the temporary workspace."
            )
            workspace_info.append(
                " - For voting, you can review all agents' work here and use this context to make an informed voting decision."
            )
            workspace_info.append(
                " - Files organized by anonymous agent IDs (agent1/, agent2/, etc.)"
            )
            workspace_info.append(
                " - IMPORTANT: Each agent works in their own separate workspace"
            )
            workspace_info.append(
                " - File paths in answers have been normalized to show where you can access their work"
            )
            workspace_info.append(
                " - All agents' work is equally valid regardless of which workspace directory they used"
            )
            workspace_info.append(
                " - Focus on evaluating the content and quality of their work, not the specific paths"
            )

        workspace_section = (
            "\n".join(workspace_info)
            if workspace_info
            else "- Check your available directories using filesystem tools"
        )

        return f"""## Filesystem Access

You have access to filesystem operations through MCP tools allowing you to read and write files.

### Your Accessible Directories:

{workspace_section}

### Best Practices:

- Always save your own work in your main workspace
- Use absolute paths when possible for clarity
- When referencing others' work, read from context directories first
- Create meaningful file names and directory structure
"""


# ### IMPORTANT Evaluation Note:
# When evaluating other agents' work, focus on the CONTENT and FUNCTIONALITY of their files. Each agent works in their own isolated workspace - this is correct behavior. The paths shown in their answers are normalized so you can access and verify their work. Judge based on code quality, correctness, and completeness, not on which workspace directory was used.


# Global template instance
_templates = MessageTemplates()


def get_templates() -> MessageTemplates:
    """Get global message templates instance."""
    return _templates


def set_templates(templates: MessageTemplates) -> None:
    """Set global message templates instance."""
    global _templates
    _templates = templates


# Convenience functions for common operations
def build_case1_conversation(task: str) -> Dict[str, Any]:
    """Build Case 1 conversation (no summaries exist)."""
    return get_templates().build_initial_conversation(task)


def build_case2_conversation(
    task: str,
    agent_summaries: Dict[str, str],
    valid_agent_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build Case 2 conversation (summaries exist)."""
    return get_templates().build_initial_conversation(
        task, agent_summaries, valid_agent_ids
    )


def get_standard_tools(
    valid_agent_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Get standard MassGen tools."""
    return get_templates().get_standard_tools(valid_agent_ids)


def get_enforcement_message() -> str:
    """Get enforcement message for Case 3."""
    return get_templates().enforcement_message()
