# -*- coding: utf-8 -*-
"""
Message templates for MassGen framework following input_cases_reference.md
Implements proven binary decision framework that eliminates perfectionism loops.
"""

from typing import Any, Dict, List, Optional


class MessageTemplates:
    """Message templates implementing the proven MassGen approach."""

    def __init__(self, voting_sensitivity: str = "lenient", answer_novelty_requirement: str = "lenient", **template_overrides):
        """Initialize with optional template overrides.

        Args:
            voting_sensitivity: Controls how critical agents are when voting.
                - "lenient": Agents vote YES more easily, fewer new answers (default)
                - "balanced": Agents apply detailed criteria (comprehensive, accurate, complete?)
                - "strict": Agents apply high standards of excellence (all aspects, edge cases, reference-quality)
            answer_novelty_requirement: Controls how different new answers must be.
                - "lenient": No additional checks (default)
                - "balanced": Require meaningful differences
                - "strict": Require substantially different solutions
            **template_overrides: Custom template strings to override defaults
        """
        self._voting_sensitivity = voting_sensitivity
        self._answer_novelty_requirement = answer_novelty_requirement
        self._template_overrides = template_overrides

    # =============================================================================
    # SYSTEM MESSAGE TEMPLATES
    # =============================================================================

    # =============================================================================
    # USER MESSAGE TEMPLATES
    # =============================================================================

    def format_original_message(self, task: str, paraphrase: Optional[str] = None) -> str:
        """Format the original message section."""
        if "format_original_message" in self._template_overrides:
            override = self._template_overrides["format_original_message"]
            if callable(override):
                try:
                    return override(task, paraphrase=paraphrase)
                except TypeError:
                    return override(task)
            return str(override).format(task=task, paraphrase=paraphrase)

        original_block = f"<ORIGINAL MESSAGE> {task} <END OF ORIGINAL MESSAGE>"
        if paraphrase:
            paraphrase_block = f"<PARAPHRASED MESSAGE> {paraphrase} <END OF PARAPHRASED MESSAGE>"
            return f"{original_block}\n{paraphrase_block}"
        return original_block

    def format_conversation_history(self, conversation_history: List[Dict[str, str]]) -> str:
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

    def system_message_with_context(self, conversation_history: Optional[List[Dict[str, str]]] = None) -> str:
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

    def format_current_answers_with_summaries(self, agent_summaries: Dict[str, str]) -> str:
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
                        },
                    },
                    "required": ["content"],
                },
            },
        }

    def get_vote_tool(self, valid_agent_ids: Optional[List[str]] = None) -> Dict[str, Any]:
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
            tool_def["function"]["parameters"]["properties"]["agent_id"]["enum"] = anon_agent_ids

        return tool_def

    def get_standard_tools(self, valid_agent_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Get standard tools for MassGen framework."""
        return [self.get_new_answer_tool(), self.get_vote_tool(valid_agent_ids)]

    def final_presentation_system_message(
        self,
        original_system_message: Optional[str] = None,
        enable_image_generation: bool = False,
        enable_audio_generation: bool = False,
        enable_file_generation: bool = False,
        enable_video_generation: bool = False,
        has_irreversible_actions: bool = False,
        enable_command_execution: bool = False,
    ) -> str:
        """System message for final answer presentation by winning agent.

        Args:
            original_system_message: The agent's original system message to preserve
            enable_image_generation: Whether image generation is enabled
            enable_audio_generation: Whether audio generation is enabled
            enable_file_generation: Whether file generation is enabled
            enable_video_generation: Whether video generation is enabled
            has_irreversible_actions: Whether agent has write access to context paths (requires actual file delivery)
            enable_command_execution: Whether command execution is enabled for this agent
        """
        if "final_presentation_system_message" in self._template_overrides:
            return str(self._template_overrides["final_presentation_system_message"])

        # BACKUP - Original final presentation message (pre-explicit-synthesis update):
        # presentation_instructions = """You have been selected as the winning presenter in a coordination process.
        # Your task is to present a polished, comprehensive final answer that incorporates the best insights from all participants.
        #
        # Consider:
        # 1. Your original response and how it can be refined
        # 2. Valuable insights from other agents' answers that should be incorporated
        # 3. Feedback received through the voting process
        # 4. Ensuring clarity, completeness, and comprehensiveness for the final audience
        #
        # Present your final coordinated answer in the most helpful and complete way possible."""

        presentation_instructions = """You have been selected as the winning presenter in a coordination process.
Present the best possible coordinated answer by combining the strengths from all participants.\n\n"""

        # Add image generation instructions only if enabled
        if enable_image_generation:
            presentation_instructions += """For image generation tasks:

  **MANDATORY WORKFLOW - You MUST follow these steps in order:**

  Step 1: **Check for existing images (REQUIRED)**
  - First, list all files in the Shared Reference directory (temp_workspaces) to find ALL images from EVERY agent
  - Look for image files (.png, .jpg, .jpeg, .gif, .webp, etc.) in each agent's workspace subdirectory

  Step 2: **Understand ALL existing images (REQUIRED if images exist)**
  - For EACH image file you found, you MUST call the **understand_image** tool to extract its key visual elements, composition, style, and quality
  - Do this for images from yourself AND from other agents - analyze ALL images found
  - DO NOT skip this step even if you think you know the content

  Step 3: **Synthesize and generate final image (REQUIRED)**
  - If existing images were found and analyzed:
    * Synthesize ALL image analyses into a single, detailed, combined prompt
    * The combined prompt should capture the best visual elements, composition, style, and quality from all analyzed images
    * Call **image_to_image_generation** with this synthesized prompt and ALL images to create the final unified image
  - If NO existing images were found:
    * Generate a new image based directly on the original task requirements
    * Call **text_to_image_generation** with a prompt derived from the original task

  Step 4: **Save and report (REQUIRED)**
  - Save the final generated image in your workspace
  - Report the saved path in your final answer

  **CRITICAL**: You MUST complete Steps 1-4 in order. Do not skip checking for existing images. Do not skip calling
  understand_image on found images. This is a mandatory synthesis workflow.
  """
        #             presentation_instructions += """For image generation tasks:
        # - Extract image paths from the existing answer and resolve them in the shared reference.
        # - Gather all agent-produced images (ignore non-existent files).
        # - IMPORTANT: If you find ANY existing images (from yourself or other agents), you MUST call the understand_image tool
        #   to analyze EACH image and extract their key visual elements, composition, style, and quality.
        # - IMPORTANT: Synthesize insights from all analyzed images into a detailed, combined prompt that captures the best elements.
        # - IMPORTANT: Call text_to_image_generation with this synthesized prompt to generate the final image.
        # - IMPORTANT: Save the final output in your workspace and output the saved path.
        # - If no existing images are found, generate based on the original task requirements.
        # """
        # Add audio generation instructions only if enabled
        if enable_audio_generation:
            presentation_instructions += """For audio generation tasks:

  **MANDATORY WORKFLOW - You MUST follow these steps in order:**

  Step 1: **Check for existing audios (REQUIRED)**
  - First, list all files in the Shared Reference directory (temp_workspaces) to find ALL audio files from EVERY agent
  - Look for audio files (.mp3, .wav, .flac, etc.) in each agent's workspace subdirectory

  Step 2: **Understand ALL existing audios (REQUIRED if audios exist)**
  - For EACH audio file you found, you MUST call the **understand_audio** tool to extract its transcription
  - Do this for audios from yourself AND from other agents - analyze ALL audios found
  - DO NOT skip this step even if you think you know the content

  Step 3: **Synthesize and generate final audio (REQUIRED)**
  - If existing audios were found and analyzed:
    * Synthesize ALL audio transcriptions into a single, detailed, combined transcription
    * The combined transcription should capture the best content from all analyzed audios
    * Call **text_to_speech_transcription_generation** with this synthesized transcription to create the final unified audio
  - If NO existing audios were found:
    * Generate a new audio based directly on the original task requirements
    * Call **text_to_speech_transcription_generation** with a transcription derived from the original task

  Step 4: **Save and report (REQUIRED)**
  - Save the final generated audio in your workspace
  - Report the saved path in your final answer

  **CRITICAL**: You MUST complete Steps 1-4 in order. Do not skip checking for existing audios. Do not skip calling
  understand_audio on found audios. This is a mandatory synthesis workflow.
  """
        #                         presentation_instructions += """For audio generation tasks:
        # - Extract audio paths from the existing answer and resolve them in the shared reference.
        # - Gather ALL audio files produced by EVERY agent (ignore non-existent files).
        # - IMPORTANT: If you find ANY existing audios (from yourself or other agents), you MUST call the **understand_audio** tool to extract each audio's transcription.
        # - IMPORTANT: Synthesize transcriptions from all audios into a detailed, combined transcription.
        # - IMPORTANT: You MUST call the **text_to_speech_transcription_generation** tool with this synthesized transcription to generate the final audio.
        # - IMPORTANT: Save the final output in your workspace and output the saved path.
        # - If no existing audios are found, generate based on the original task requirements.
        # """
        # Add file generation instructions only if enabled
        if enable_file_generation:
            presentation_instructions += """For file generation tasks:

  **MANDATORY WORKFLOW - You MUST follow these steps in order:**

  Step 1: **Check for existing files (REQUIRED)**
  - First, list all files in the Shared Reference directory (temp_workspaces) to find ALL files from EVERY agent
  - Look for files of the requested type in each agent's workspace subdirectory

  Step 2: **Understand ALL existing files (REQUIRED if files exist)**
  - For EACH file you found, you MUST call the **understand_file** tool to extract its content, structure, and key elements
  - Do this for files from yourself AND from other agents - analyze ALL files found
  - DO NOT skip this step even if you think you know the content

  Step 3: **Synthesize and generate final file (REQUIRED)**
  - If existing files were found and analyzed:
    * Synthesize ALL file contents into a single, detailed, combined content
    * The combined content should capture the best elements, structure, and information from all analyzed files
    * Call **text_to_file_generation** with this synthesized content to generate the final unified file
  - If NO existing files were found:
    * Generate a new file based directly on the original task requirements
    * Call **text_to_file_generation** with content derived from the original task

  Step 4: **Save and report (REQUIRED)**
  - Save the final generated file in your workspace
  - Report the saved path in your final answer

  **CRITICAL**: You MUST complete Steps 1-4 in order. Do not skip checking for existing files. Do not skip calling
  understand_file on found files. This is a mandatory synthesis workflow.
  """
        #             presentation_instructions += """For file generation tasks:
        # - Extract file paths from the existing answer and resolve them in the shared reference.
        # - Gather ALL files produced by EVERY agent (ignore non-existent files).
        # - IMPORTANT: If you find ANY existing files (from yourself or other agents), you MUST call the **understand_file** tool to extract each file's content.
        # - IMPORTANT: Synthesize contents from all files into a detailed, combined content.
        # - IMPORTANT: You MUST call the **text_to_file_generation** tool with this synthesized content to generate the final file.
        # - IMPORTANT: Save the final output in your workspace and output the saved path.
        # - If no existing files are found, generate based on the original task requirements.
        # """
        # Add video generation instructions only if enabled
        if enable_video_generation:
            presentation_instructions += """For video generation tasks:

  **MANDATORY WORKFLOW - You MUST follow these steps in order:**

  Step 1: **Check for existing videos (REQUIRED)**
  - First, list all files in the Shared Reference directory (temp_workspaces) to find ALL videos from EVERY agent
  - Look for video files (.mp4, .avi, .mov, etc.) in each agent's workspace subdirectory

  Step 2: **Understand ALL existing videos (REQUIRED if videos exist)**
  - For EACH video file you found, you MUST call the **understand_video** tool to extract its description, visual features, and
  key elements
  - Do this for videos from yourself AND from other agents - analyze ALL videos found
  - DO NOT skip this step even if you think you know the content

  Step 3: **Synthesize and generate final video (REQUIRED)**
  - If existing videos were found and analyzed:
    * Synthesize ALL video descriptions into a single, detailed, combined prompt
    * The combined prompt should capture the best visual elements, composition, motion, and style from all analyzed videos
    * Call **text_to_video_generation** with this synthesized prompt to create the final unified video
  - If NO existing videos were found:
    * Generate a new video based directly on the original task requirements
    * Call **text_to_video_generation** with a prompt derived from the original task

  Step 4: **Save and report (REQUIRED)**
  - Save the final generated video in your workspace
  - Report the saved path in your final answer

  **CRITICAL**: You MUST complete Steps 1-4 in order. Do not skip checking for existing videos. Do not skip calling
  understand_video on found videos. This is a mandatory synthesis workflow.
  """
        #             presentation_instructions += """For video generation tasks:
        # - Extract video paths from the existing answer and resolve them in the shared reference.
        # - Gather ALL videos produced by EVERY agent (ignore non-existent files).
        # - IMPORTANT: If you find ANY existing videos (from yourself or other agents), you MUST call the **understand_video** tool to extract each video's description and key features.
        # - IMPORTANT: Synthesize descriptions from all videos into a detailed, combined prompt capturing the best elements.
        # - IMPORTANT: You MUST call the **text_to_video_generation** tool with this synthesized prompt to generate the final video.
        # - IMPORTANT: Save the final output in your workspace and output the saved path.
        # - If no existing videos are found, generate based on the original task requirements.
        # """

        # Add irreversible actions reminder if needed
        # TODO: Integrate more general irreversible actions handling in future (i.e., not just for context file delivery)
        if has_irreversible_actions:
            presentation_instructions += (
                "### Write Access to Target Path:\n\n"
                "Reminder: File Delivery Required. You should first place your final answer in your workspace. "
                "However, note your workspace is NOT the final destination. You MUST copy/write files to the Target Path using FULL ABSOLUTE PATHS. "
                "Then, clean up this Target Path by deleting any outdated or unused files. "
                "Then, you must ALWAYS verify that the Target Path contains the correct final files, as no other agents were allowed to write to this path.\n"
            )

        # Add requirements.txt guidance if command execution is enabled
        if enable_command_execution:
            presentation_instructions += (
                "### Package Dependencies:\n\n"
                "Create a `requirements.txt` file listing all Python packages needed to run your code. "
                "This helps users reproduce your work later. Include only the packages you actually used in your solution.\n"
            )

        # Combine with original system message if provided
        if original_system_message:
            return f"""{original_system_message}

{presentation_instructions}"""
        else:
            return presentation_instructions

    def format_restart_context(self, reason: str, instructions: str, previous_answer: Optional[str] = None) -> str:
        """Format restart context for subsequent orchestration attempts.

        This context is added to agent messages (like multi-turn context) on restart attempts.

        Args:
            reason: Why the previous attempt was insufficient
            instructions: Detailed guidance for improvement
            previous_answer: The winning answer from the previous attempt (optional)
        """
        if "format_restart_context" in self._template_overrides:
            override = self._template_overrides["format_restart_context"]
            if callable(override):
                return override(reason, instructions, previous_answer)
            return str(override).format(reason=reason, instructions=instructions, previous_answer=previous_answer or "")

        base_context = f"""<PREVIOUS ATTEMPT FEEDBACK>
The previous orchestration attempt was restarted because:
{reason}

**Instructions for this attempt:**
{instructions}"""

        # Include previous answer if available
        if previous_answer:
            base_context += f"""

**Previous attempt's winning answer (for reference):**
{previous_answer}"""

        base_context += """

Please address these specific issues in your coordination and final answer.
<END OF PREVIOUS ATTEMPT FEEDBACK>"""

        return base_context

    # =============================================================================
    # COMPLETE MESSAGE BUILDERS
    # =============================================================================

    def build_case1_user_message(self, task: str, paraphrase: Optional[str] = None) -> str:
        """Build Case 1 user message (no summaries exist)."""
        return f"""{self.format_original_message(task, paraphrase)}

{self.format_current_answers_empty()}"""

    def build_case2_user_message(self, task: str, agent_summaries: Dict[str, str], paraphrase: Optional[str] = None) -> str:
        """Build Case 2 user message (summaries exist)."""
        return f"""{self.format_original_message(task, paraphrase)}

{self.format_current_answers_with_summaries(agent_summaries)}"""

    def build_evaluation_message(self, task: str, agent_answers: Optional[Dict[str, str]] = None, paraphrase: Optional[str] = None) -> str:
        """Build evaluation user message for any case."""
        if agent_answers:
            return self.build_case2_user_message(task, agent_answers, paraphrase)
        else:
            return self.build_case1_user_message(task, paraphrase)

    def build_coordination_context(
        self,
        current_task: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        agent_answers: Optional[Dict[str, str]] = None,
        paraphrase: Optional[str] = None,
    ) -> str:
        """Build coordination context including conversation history and current state."""
        if "build_coordination_context" in self._template_overrides:
            override = self._template_overrides["build_coordination_context"]
            if callable(override):
                try:
                    return override(current_task, conversation_history, agent_answers, paraphrase)
                except TypeError:
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
        context_parts.append(self.format_original_message(current_task, paraphrase))
        context_parts.append("")  # Empty line for spacing

        # Add agent answers
        if agent_answers:
            context_parts.append(self.format_current_answers_with_summaries(agent_answers))
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
        paraphrase: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build complete initial conversation for MassGen evaluation."""
        # Use agent's custom system message if provided, otherwise use default evaluation message
        if base_system_message:
            # Check if this is a structured system prompt (contains <system_prompt> tag)
            # Structured prompts already include evaluation message, so don't prepend it
            if "<system_prompt>" in base_system_message:
                system_message = base_system_message
            else:
                # Old-style: prepend evaluation message for backward compatibility
                system_message = f"{self.evaluation_system_message()}\n\n#Special Requirement\n{base_system_message}"
        else:
            system_message = self.evaluation_system_message()

        return {
            "system_message": system_message,
            "user_message": self.build_evaluation_message(task, agent_summaries, paraphrase),
            "tools": self.get_standard_tools(valid_agent_ids),
        }

    def build_conversation_with_context(
        self,
        current_task: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        agent_summaries: Optional[Dict[str, str]] = None,
        valid_agent_ids: Optional[List[str]] = None,
        base_system_message: Optional[str] = None,
        paraphrase: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build complete conversation with conversation history context for MassGen evaluation."""
        # Use agent's custom system message if provided, otherwise use default context-aware message
        if base_system_message:
            # Check if this is a structured system prompt (contains <system_prompt> tag)
            # Structured prompts already include evaluation message, so don't append it
            if "<system_prompt>" in base_system_message:
                system_message = base_system_message
            else:
                # Old-style: append evaluation message for backward compatibility
                system_message = f"{base_system_message}\n\n{self.system_message_with_context(conversation_history)}"
        else:
            system_message = self.system_message_with_context(conversation_history)

        return {
            "system_message": system_message,
            "user_message": self.build_coordination_context(current_task, conversation_history, agent_summaries, paraphrase),
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

    def add_enforcement_message(self, conversation_messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Add enforcement message to existing conversation (Case 3)."""
        messages = conversation_messages.copy()
        messages.append({"role": "user", "content": self.enforcement_message()})
        return messages


# ### IMPORTANT Evaluation Note:
# When evaluating other agents' work, focus on the CONTENT and FUNCTIONALITY of their files.
# Each agent works in their own isolated workspace - this is correct behavior.
# The paths shown in their answers are normalized so you can access and verify their work.
# Judge based on code quality, correctness, and completeness, not on which workspace directory was used.


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
    return get_templates().build_initial_conversation(task, agent_summaries, valid_agent_ids)


def get_standard_tools(
    valid_agent_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Get standard MassGen tools."""
    return get_templates().get_standard_tools(valid_agent_ids)


def get_enforcement_message() -> str:
    """Get enforcement message for Case 3."""
    return get_templates().enforcement_message()
