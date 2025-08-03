"""
Agent configuration for MassGen framework following input_cases_reference.md
Simplified configuration focused on the proven binary decision approach.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .message_templates import MessageTemplates


@dataclass
class AgentConfig:
    """Configuration for MassGen agents using the proven binary decision framework.
    
    This configuration implements the simplified approach from input_cases_reference.md
    that eliminates perfectionism loops through clear binary decisions.
    
    Args:
        backend_params: Settings passed directly to LLM backend (includes tool enablement)
        message_templates: Custom message templates (None=default)
        agent_id: Optional agent identifier for this configuration
        custom_system_instruction: Additional system instruction prepended to evaluation message
    """
    
    # Core backend configuration (includes tool enablement)
    backend_params: Dict[str, Any] = field(default_factory=dict)
    
    # Framework configuration
    message_templates: Optional["MessageTemplates"] = None
    
    # Agent customization
    agent_id: Optional[str] = None
    custom_system_instruction: Optional[str] = None
    
    @classmethod
    def create_openai_config(cls, model: str = "gpt-4o-mini", 
                           enable_web_search: bool = False,
                           enable_code_interpreter: bool = False,
                           **kwargs) -> 'AgentConfig':
        """Create OpenAI configuration following proven patterns.
        
        Args:
            model: OpenAI model name
            enable_web_search: Enable web search via Responses API
            enable_code_interpreter: Enable code execution for computational tasks
            **kwargs: Additional backend parameters
        
        Examples:
            # Basic configuration
            config = AgentConfig.create_openai_config("gpt-4o-mini")
            
            # Research task with web search
            config = AgentConfig.create_openai_config("gpt-4o", enable_web_search=True)
            
            # Computational task with code execution
            config = AgentConfig.create_openai_config("gpt-4o", enable_code_interpreter=True)
        """
        backend_params = {"model": model, **kwargs}
        
        # Add tool enablement to backend_params
        if enable_web_search:
            backend_params["enable_web_search"] = True
        if enable_code_interpreter:
            backend_params["enable_code_interpreter"] = True
            
        return cls(backend_params=backend_params)
    
    @classmethod
    def create_claude_config(cls, model: str = "claude-3-sonnet-20240229",
                           enable_web_search: bool = False,
                           enable_code_execution: bool = False,
                           **kwargs) -> 'AgentConfig':
        """Create Anthropic Claude configuration.
        
        Args:
            model: Claude model name
            enable_web_search: Enable builtin web search tool
            enable_code_execution: Enable builtin code execution tool  
            **kwargs: Additional backend parameters
        """
        backend_params = {"model": model, **kwargs}
        
        if enable_web_search:
            backend_params["enable_web_search"] = True
            
        if enable_code_execution:
            backend_params["enable_code_execution"] = True
            
        return cls(backend_params=backend_params)
    
    @classmethod
    def create_grok_config(cls, model: str = "grok-2-1212", 
                         enable_web_search: bool = False,
                         **kwargs) -> 'AgentConfig':
        """Create xAI Grok configuration.
        
        Args:
            model: Grok model name
            enable_web_search: Enable Live Search feature
            **kwargs: Additional backend parameters
        """
        backend_params = {"model": model, **kwargs}
        
        # Add tool enablement to backend_params
        if enable_web_search:
            backend_params["enable_web_search"] = True
            
        return cls(backend_params=backend_params)
    
    @classmethod
    def create_gemini_config(cls, model: str = "gemini-2.5-flash", 
                           enable_web_search: bool = False,
                           enable_code_execution: bool = False,
                           **kwargs) -> 'AgentConfig':
        """Create Google Gemini configuration.
        
        Args:
            model: Gemini model name
            enable_web_search: Enable Google Search retrieval tool
            enable_code_execution: Enable code execution tool
            **kwargs: Additional backend parameters
        """
        backend_params = {"model": model, **kwargs}
        
        # Add tool enablement to backend_params
        if enable_web_search:
            backend_params["enable_web_search"] = True
        if enable_code_execution:
            backend_params["enable_code_execution"] = True
            
        return cls(backend_params=backend_params)
    
    # =============================================================================
    # AGENT CUSTOMIZATION
    # =============================================================================
    
    def with_custom_instruction(self, instruction: str) -> 'AgentConfig':
        """Create a copy with custom system instruction."""
        import copy
        new_config = copy.deepcopy(self)
        new_config.custom_system_instruction = instruction
        return new_config
    
    def with_agent_id(self, agent_id: str) -> 'AgentConfig':
        """Create a copy with specified agent ID."""
        import copy
        new_config = copy.deepcopy(self)
        new_config.agent_id = agent_id
        return new_config
    
    # =============================================================================
    # PROVEN PATTERN CONFIGURATIONS
    # =============================================================================
    
    @classmethod
    def for_research_task(cls, model: str = "gpt-4o", backend: str = "openai") -> 'AgentConfig':
        """Create configuration optimized for research tasks.
        
        Based on econometrics test success patterns:
        - Enables web search for literature review
        - Uses proven model defaults
        """
        if backend == "openai":
            return cls.create_openai_config(model, enable_web_search=True)
        elif backend == "grok":
            return cls.create_grok_config(model, enable_web_search=True)
        elif backend == "claude":
            return cls.create_claude_config(model, enable_web_search=True)
        elif backend == "gemini":
            return cls.create_gemini_config(model, enable_web_search=True)
        else:
            raise ValueError(f"Research configuration not available for backend: {backend}")
    
    @classmethod
    def for_computational_task(cls, model: str = "gpt-4o", backend: str = "openai") -> 'AgentConfig':
        """Create configuration optimized for computational tasks.
        
        Based on Tower of Hanoi test success patterns:
        - Enables code execution for calculations
        - Uses proven model defaults
        """
        if backend == "openai":
            return cls.create_openai_config(model, enable_code_interpreter=True)
        elif backend == "claude":
            return cls.create_claude_config(model, enable_code_execution=True)
        elif backend == "gemini":
            return cls.create_gemini_config(model, enable_code_execution=True)
        else:
            raise ValueError(f"Computational configuration not available for backend: {backend}")
    
    @classmethod
    def for_analytical_task(cls, model: str = "gpt-4o-mini", backend: str = "openai") -> 'AgentConfig':
        """Create configuration optimized for analytical tasks.
        
        Based on general reasoning test patterns:
        - No special tools needed
        - Uses efficient model defaults
        """
        if backend == "openai":
            return cls.create_openai_config(model)
        elif backend == "claude":
            return cls.create_claude_config(model)
        elif backend == "grok":
            return cls.create_grok_config(model)
        elif backend == "gemini":
            return cls.create_gemini_config(model)
        else:
            raise ValueError(f"Analytical configuration not available for backend: {backend}")
    
    @classmethod
    def for_expert_domain(cls, domain: str, expertise_level: str = "expert", 
                         model: str = "gpt-4o", backend: str = "openai") -> 'AgentConfig':
        """Create configuration for domain expertise.
        
        Args:
            domain: Domain of expertise (e.g., "econometrics", "computer science")
            expertise_level: Level of expertise ("expert", "specialist", "researcher")
            model: Model to use
            backend: Backend provider
        """
        instruction = f"You are a {expertise_level} in {domain}. Apply your deep domain knowledge and methodological expertise when evaluating answers and providing solutions."
        
        if backend == "openai":
            config = cls.create_openai_config(model, enable_web_search=True)
        elif backend == "grok":
            config = cls.create_grok_config(model, enable_web_search=True)
        elif backend == "gemini":
            config = cls.create_gemini_config(model, enable_web_search=True)
        else:
            raise ValueError(f"Domain expert configuration not available for backend: {backend}")
        
        config.custom_system_instruction = instruction
        return config
    
    # =============================================================================
    # CONVERSATION BUILDING
    # =============================================================================
    
    def build_conversation(self, task: str, agent_summaries: Optional[Dict[str, str]] = None, 
                         session_id: Optional[str] = None) -> Dict[str, Any]:
        """Build conversation using the proven MassGen approach.
        
        Returns complete conversation configuration ready for backend.
        Automatically determines Case 1 vs Case 2 based on agent_summaries.
        """
        from .message_templates import get_templates
        
        templates = self.message_templates or get_templates()
        
        # Derive valid agent IDs from agent summaries
        valid_agent_ids = list(agent_summaries.keys()) if agent_summaries else None
        
        # Build base conversation
        conversation = templates.build_initial_conversation(
            task=task,
            agent_summaries=agent_summaries,
            valid_agent_ids=valid_agent_ids
        )
        
        # Add custom system instruction if provided
        if self.custom_system_instruction:
            base_system = conversation["system_message"]
            conversation["system_message"] = f"{self.custom_system_instruction}\n\n{base_system}"
        
        # Add backend configuration
        conversation.update({
            "backend_params": self.get_backend_params(),
            "session_id": session_id,
            "agent_id": self.agent_id
        })
        
        return conversation
    
    def add_enforcement_message(self, conversation_messages: list) -> list:
        """Add enforcement message to conversation (Case 3 handling).
        
        Args:
            conversation_messages: Existing conversation messages
            
        Returns:
            Updated conversation messages with enforcement
        """
        from .message_templates import get_templates
        
        templates = self.message_templates or get_templates()
        return templates.add_enforcement_message(conversation_messages)
    
    def continue_conversation(self, existing_messages: list, 
                            additional_message: Any = None,
                            additional_message_role: str = "user",
                            enforce_tools: bool = False) -> Dict[str, Any]:
        """Continue an existing conversation (Cases 3 & 4).
        
        Args:
            existing_messages: Previous conversation messages
            additional_message: Additional message (str or dict for tool results)
            additional_message_role: Role for additional message ("user", "tool", "assistant")
            enforce_tools: Whether to add tool enforcement message
            
        Returns:
            Updated conversation configuration
        """
        messages = existing_messages.copy()
        
        # Add additional message if provided
        if additional_message is not None:
            if isinstance(additional_message, dict):
                # Full message object provided
                messages.append(additional_message)
            else:
                # String content provided
                messages.append({
                    "role": additional_message_role,
                    "content": str(additional_message)
                })
        
        # Add enforcement if requested (Case 3)
        if enforce_tools:
            messages = self.add_enforcement_message(messages)
        
        # Build conversation with continued messages
        from .message_templates import get_templates
        templates = self.message_templates or get_templates()
        
        return {
            "messages": messages,
            "tools": templates.get_standard_tools(),  # Same tools as initial
            "backend_params": self.get_backend_params(),
            "session_id": None,  # Maintain existing session
            "agent_id": self.agent_id
        }
    
    def handle_case3_enforcement(self, existing_messages: list) -> Dict[str, Any]:
        """Handle Case 3: Non-workflow response requiring enforcement.
        
        Args:
            existing_messages: Messages from agent that didn't use tools
            
        Returns:
            Conversation with enforcement message added
        """
        return self.continue_conversation(
            existing_messages=existing_messages,
            enforce_tools=True
        )
    
    def add_tool_result(self, existing_messages: list, 
                       tool_call_id: str, result: str) -> Dict[str, Any]:
        """Add tool result to conversation.
        
        Args:
            existing_messages: Previous conversation messages
            tool_call_id: ID of the tool call this responds to
            result: Tool execution result (success or error)
            
        Returns:
            Conversation with tool result added
        """
        tool_message = {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result
        }
        
        return self.continue_conversation(
            existing_messages=existing_messages,
            additional_message=tool_message
        )
    
    def handle_case4_error_recovery(self, existing_messages: list, 
                                  clarification: str = None) -> Dict[str, Any]:
        """Handle Case 4: Error recovery after tool failure.
        
        Args:
            existing_messages: Messages including tool error response
            clarification: Optional clarification message
            
        Returns:
            Conversation ready for retry
        """
        return self.continue_conversation(
            existing_messages=existing_messages,
            additional_message=clarification,
            additional_message_role="user",
            enforce_tools=False  # Agent should retry naturally
        )
    
    def get_backend_params(self) -> Dict[str, Any]:
        """Get backend parameters (already includes tool enablement)."""
        return self.backend_params.copy()
    
    # =============================================================================
    # SERIALIZATION
    # =============================================================================
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "backend_params": self.backend_params,
            "agent_id": self.agent_id,
            "custom_system_instruction": self.custom_system_instruction
        }
        
        # Handle message_templates serialization
        if self.message_templates is not None:
            try:
                if hasattr(self.message_templates, '_template_overrides'):
                    overrides = self.message_templates._template_overrides
                    if all(not callable(v) for v in overrides.values()):
                        result["message_templates"] = overrides
                    else:
                        result["message_templates"] = "<contains_callable_functions>"
                else:
                    result["message_templates"] = "<custom_message_templates>"
            except (AttributeError, TypeError):
                result["message_templates"] = "<non_serializable>"
        
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AgentConfig':
        """Create from dictionary (for deserialization)."""
        # Extract basic fields
        backend_params = data.get("backend_params", {})
        agent_id = data.get("agent_id")
        custom_system_instruction = data.get("custom_system_instruction")
        
        # Handle message_templates
        message_templates = None
        template_data = data.get("message_templates")
        if isinstance(template_data, dict):
            from .message_templates import MessageTemplates
            message_templates = MessageTemplates(**template_data)
        
        return cls(
            backend_params=backend_params,
            message_templates=message_templates,
            agent_id=agent_id,
            custom_system_instruction=custom_system_instruction
        )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def create_research_config(model: str = "gpt-4o", backend: str = "openai") -> AgentConfig:
    """Create configuration for research tasks (web search enabled)."""
    return AgentConfig.for_research_task(model, backend)


def create_computational_config(model: str = "gpt-4o", backend: str = "openai") -> AgentConfig:
    """Create configuration for computational tasks (code execution enabled)."""
    return AgentConfig.for_computational_task(model, backend)


def create_analytical_config(model: str = "gpt-4o-mini", backend: str = "openai") -> AgentConfig:
    """Create configuration for analytical tasks (no special tools)."""
    return AgentConfig.for_analytical_task(model, backend)