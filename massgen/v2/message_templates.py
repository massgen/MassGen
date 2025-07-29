"""
Message Templates for MassGen v0.0.2 - Issue #22: Message Templates and Workflow Tools

Implements the proven binary decision framework that eliminates perfectionism loops,
based on the reference MASS implementation.
"""

from typing import Dict, Any, Optional, List


class MessageTemplates:
    """Message templates implementing the proven MASS binary decision approach."""
    
    def __init__(self, **template_overrides):
        """Initialize with optional template overrides."""
        self._template_overrides = template_overrides
    
    # =============================================================================
    # SYSTEM MESSAGE TEMPLATES
    # =============================================================================
    
    def evaluation_system_message(self, original_system_message: Optional[str] = None) -> str:
        """Standard evaluation system message for all cases.
        
        Args:
            original_system_message: The agent's original system message to preserve
        """
        if "evaluation_system_message" in self._template_overrides:
            return str(self._template_overrides["evaluation_system_message"])
        
        evaluation_instructions = """You are evaluating answers from multiple agents for final response to a message. Does the best CURRENT ANSWER address the ORIGINAL MESSAGE?

If YES, use the `vote` tool to record your vote and skip the `new_answer` tool.
Otherwise, do additional work first, then use the `new_answer` tool to record a better answer to the ORIGINAL MESSAGE. Make sure you actually call one of the two tools."""
        
        # Combine with original system message if provided
        if original_system_message:
            return f"""{original_system_message}

COORDINATION CONTEXT:
{evaluation_instructions}"""
        else:
            return evaluation_instructions
    
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
        """Get standard tools for MASS framework."""
        return [
            self.get_new_answer_tool(),
            self.get_vote_tool(valid_agent_ids)
        ]
    
    # =============================================================================
    # COMPLETE MESSAGE BUILDERS
    # =============================================================================
    
    def build_initial_conversation(self, task: str, agent_summaries: Optional[Dict[str, str]] = None, 
                                  valid_agent_ids: Optional[List[str]] = None,
                                  original_system_message: Optional[str] = None) -> Dict[str, str]:
        """Build complete conversation for agent coordination."""
        system_message = self.evaluation_system_message(original_system_message)
        
        if agent_summaries:
            # Case 2: Existing answers available
            user_message = self.build_case2_user_message(task, agent_summaries)
        else:
            # Case 1: No answers yet
            user_message = self.build_case1_user_message(task)
        
        return {
            "system_message": system_message,
            "user_message": user_message
        }
    
    def build_case1_user_message(self, task: str) -> str:
        """Build Case 1 user message (no summaries exist)."""
        return f"""{self.format_original_message(task)}

{self.format_current_answers_empty()}"""
    
    def build_case2_user_message(self, task: str, agent_summaries: Dict[str, str]) -> str:
        """Build Case 2 user message (summaries exist)."""
        return f"""{self.format_original_message(task)}

{self.format_current_answers_with_summaries(agent_summaries)}"""