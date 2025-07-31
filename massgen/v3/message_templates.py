"""
Message templates for MassGen framework following input_cases_reference.md
Implements proven binary decision framework that eliminates perfectionism loops.
"""

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
        
        return f"""You are evaluating answers from multiple agents for final response to a message. Does the best CURRENT ANSWER address the ORIGINAL MESSAGE?

If YES, use the `vote` tool to record your vote and skip the `new_answer` tool.
Otherwise, do additional work first, then use the `new_answer` tool to record a better answer to the ORIGINAL MESSAGE. Make sure you actually call one of the two tools.
"""
    
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
        return {
            "role": "tool",
            "content": error_msg
        }
    
    def enforcement_user_message(self) -> Dict[str, str]:
        """Create a user role message for enforcement."""
        return {
            "role": "user", 
            "content": self.enforcement_message()
        }
    
    # =============================================================================
    # TOOL DEFINITIONS
    # =============================================================================
    
    def get_new_answer_tool(self) -> Dict[str, Any]:
        """Get new_answer tool definition."""
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
                        "content": {"type": "string", "description": "Your improved answer."}
                    },
                    "required": ["content"]
                }
            }
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
                        "agent_id": {"type": "string", "description": "Anonymous agent ID to vote for (e.g., 'agent1', 'agent2')"},
                        "reason": {"type": "string", "description": "Brief reason why this agent has the best answer"}
                    },
                    "required": ["agent_id", "reason"]
                }
            }
        }
        
        # Create anonymous mapping for enum constraint
        if valid_agent_ids:
            anon_agent_ids = [f"agent{i}" for i in range(1, len(valid_agent_ids) + 1)]
            tool_def["function"]["parameters"]["properties"]["agent_id"]["enum"] = anon_agent_ids
        
        return tool_def
    
    def get_standard_tools(self, valid_agent_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Get standard tools for MassGen framework."""
        return [
            self.get_new_answer_tool(),
            self.get_vote_tool(valid_agent_ids)
        ]
    
    def final_presentation_system_message(self, original_system_message: Optional[str] = None) -> str:
        """System message for final answer presentation by winning agent.
        
        Args:
            original_system_message: The agent's original system message to preserve
        """
        if "final_presentation_system_message" in self._template_overrides:
            return str(self._template_overrides["final_presentation_system_message"])
        
        presentation_instructions = """You have been selected as the winning answer in a coordination process. Your task is to present a polished, comprehensive final answer that incorporates the best insights from all participants.

Consider:
1. Your original response and how it can be refined
2. Valuable insights from other agents' answers that should be incorporated  
3. Feedback received through the voting process
4. Ensuring clarity, completeness, and comprehensiveness for the final audience

Present your final coordinated answer in the most helpful and complete way possible."""
        
        # Combine with original system message if provided
        if original_system_message:
            return f"""{original_system_message}

COORDINATION CONTEXT:
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
    
    def build_case2_user_message(self, task: str, agent_summaries: Dict[str, str]) -> str:
        """Build Case 2 user message (summaries exist)."""
        return f"""{self.format_original_message(task)}

{self.format_current_answers_with_summaries(agent_summaries)}"""
    
    def build_evaluation_message(self, task: str, agent_answers: Optional[Dict[str, str]] = None) -> str:
        """Build evaluation user message for any case."""
        if agent_answers:
            return self.build_case2_user_message(task, agent_answers)
        else:
            return self.build_case1_user_message(task)
    
    def build_coordination_context(self, current_task: str, 
                                  conversation_history: Optional[List[Dict[str, str]]] = None,
                                  agent_answers: Optional[Dict[str, str]] = None) -> str:
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
            context_parts.append(self.format_current_answers_with_summaries(agent_answers))
        else:
            context_parts.append(self.format_current_answers_empty())
        
        return "\n".join(context_parts)
    
    # =============================================================================
    # CONVERSATION BUILDERS
    # =============================================================================
    
    def build_initial_conversation(self, task: str, agent_summaries: Optional[Dict[str, str]] = None, 
                                 valid_agent_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """Build complete initial conversation for MassGen evaluation."""
        return {
            "system_message": self.evaluation_system_message(),
            "user_message": self.build_evaluation_message(task, agent_summaries),
            "tools": self.get_standard_tools(valid_agent_ids)
        }
    
    def build_conversation_with_context(self, current_task: str,
                                       conversation_history: Optional[List[Dict[str, str]]] = None,
                                       agent_summaries: Optional[Dict[str, str]] = None,
                                       valid_agent_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """Build complete conversation with conversation history context for MassGen evaluation."""
        return {
            "system_message": self.system_message_with_context(conversation_history),
            "user_message": self.build_coordination_context(current_task, conversation_history, agent_summaries),
            "tools": self.get_standard_tools(valid_agent_ids)
        }
    
    def build_final_presentation_message(self, 
                                        original_task: str,
                                        vote_summary: str, 
                                        all_answers: Dict[str, str],
                                        selected_agent_id: str) -> str:
        """Build final presentation message for winning agent."""
        # Format all answers with clear marking
        answers_section = "All answers provided during coordination:\n"
        for agent_id, answer in all_answers.items():
            marker = " (YOUR ANSWER)" if agent_id == selected_agent_id else ""
            answers_section += f"\n{agent_id}{marker}: \"{answer}\"\n"
        
        return f"""{self.format_original_message(original_task)}

VOTING RESULTS:
{vote_summary}

{answers_section}

Based on the coordination process above, present your final answer:"""
    
    def add_enforcement_message(self, conversation_messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Add enforcement message to existing conversation (Case 3)."""
        messages = conversation_messages.copy()
        messages.append({
            "role": "user",
            "content": self.enforcement_message()
        })
        return messages


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


def build_case2_conversation(task: str, agent_summaries: Dict[str, str], 
                           valid_agent_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """Build Case 2 conversation (summaries exist)."""
    return get_templates().build_initial_conversation(task, agent_summaries, valid_agent_ids)


def get_standard_tools(valid_agent_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Get standard MassGen tools."""
    return get_templates().get_standard_tools(valid_agent_ids)


def get_enforcement_message() -> str:
    """Get enforcement message for Case 3."""
    return get_templates().enforcement_message()