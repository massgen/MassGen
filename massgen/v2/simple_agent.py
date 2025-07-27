"""
SimpleAgent Implementation - Issue #19: Create SimpleAgent Implementation

This module creates SimpleAgent class that implements the ChatAgent interface 
with full LLM backend integration and workflow support.
"""

from typing import Dict, List, Optional, Any, AsyncGenerator
import time
import json
from .chat_agent import ChatAgent, StreamChunk
from .agent_backend import AgentBackend, create_backend, get_provider_from_model


class SimpleAgent(ChatAgent):
    """Individual LLM-powered agent with unified interface."""
    
    def __init__(self, 
                 agent_id: str, 
                 backend: AgentBackend, 
                 system_message: Optional[str] = None, 
                 session_id: Optional[str] = None,
                 max_retries: int = 3):
        """
        Initialize SimpleAgent.
        
        Args:
            agent_id: Semantic string identifier for this agent
            backend: AgentBackend instance for LLM communication
            system_message: Optional system message for the agent
            session_id: Optional session ID for conversation tracking
            max_retries: Maximum number of retries for failed requests
        """
        super().__init__(session_id)
        self.agent_id = agent_id
        self.backend = backend
        self.system_message = system_message or f"You are {agent_id}, a helpful AI assistant."
        self.tools: List[Dict[str, Any]] = []
        self.max_retries = max_retries
        self.created_at = time.time()
        
        # Agent state
        self.status = "ready"  # ready, working, error, completed
        self.current_task = None
        self.error_message = None
    
    async def chat(self, 
                   messages: List[Dict[str, Any]], 
                   tools: Optional[List[Dict[str, Any]]] = None, 
                   reset_chat: bool = False, 
                   clear_history: bool = False) -> AsyncGenerator[StreamChunk, None]:
        """
        Chat using LLM backend with streaming.
        
        Args:
            messages: List of conversation messages
            tools: Optional list of tools available to the agent
            reset_chat: If True, replace conversation history with provided messages
            clear_history: If True, clear conversation history before processing
            
        Yields:
            StreamChunk: Streaming response chunks with agent source attribution
        """
        self.status = "working"
        self.error_message = None
        
        try:
            # Handle conversation state management
            if clear_history:
                self.conversation_history = []
            
            if reset_chat:
                self.conversation_history = messages.copy()
            elif not clear_history:
                # Add new messages to history
                self.conversation_history.extend(messages)
            
            # Prepare messages with system message
            full_messages = self._prepare_messages(messages)
            
            # Use provided tools or default agent tools
            active_tools = tools if tools is not None else self.tools
            
            # Stream through LLM backend with retry logic
            retry_count = 0
            last_error = None
            
            while retry_count <= self.max_retries:
                try:
                    # Process stream using the same approach as the reference implementation
                    async for chunk in self._process_stream(
                        self.backend.stream_with_tools(full_messages, active_tools),
                        active_tools
                    ):
                        # Add agent source attribution
                        chunk.source = self.agent_id
                        yield chunk
                        
                        if chunk.type == "done":
                            self.status = "completed"
                            break
                        elif chunk.type == "error":
                            raise Exception(f"Backend error: {chunk.error}")
                    
                    # If we get here without errors, break the retry loop
                    break
                    
                except Exception as e:
                    last_error = e
                    retry_count += 1
                    
                    if retry_count <= self.max_retries:
                        # Yield retry notification
                        yield StreamChunk(
                            type="agent_status",
                            status=f"retrying",
                            content=f"Retry {retry_count}/{self.max_retries} after error: {str(e)}",
                            source=self.agent_id
                        )
                        
                        # Wait before retry
                        import asyncio
                        await asyncio.sleep(1.0 * retry_count)  # Progressive backoff
                    else:
                        # Max retries exceeded
                        self.status = "error"
                        self.error_message = str(last_error)
                        
                        yield StreamChunk(
                            type="error",
                            error=f"Max retries ({self.max_retries}) exceeded. Last error: {str(last_error)}",
                            source=self.agent_id
                        )
                        return
        
        except Exception as e:
            self.status = "error"
            self.error_message = str(e)
            
            yield StreamChunk(
                type="error",
                error=str(e),
                source=self.agent_id
            )
    
    async def _process_stream(self, backend_stream, tools: List[Dict[str, Any]] = None) -> AsyncGenerator[StreamChunk, None]:
        """Common streaming logic for processing backend responses, based on ../mass reference."""
        assistant_response = ""
        tool_calls = []
        complete_message = None
        
        try:
            async for chunk in backend_stream:
                if chunk.type == "content":
                    assistant_response += chunk.content
                    yield chunk
                elif chunk.type == "tool_calls":
                    # Reference implementation always uses chunk.content for tool calls
                    tool_calls.extend(chunk.content)
                    yield chunk
                elif chunk.type == "complete_message":
                    # Backend provided the complete message structure
                    complete_message = chunk.complete_message
                    # Don't yield this - it's for internal use
                elif chunk.type == "complete_response":
                    # Backend provided the raw Responses API response
                    if hasattr(chunk, 'complete_message') and chunk.complete_message:
                        complete_message = chunk.complete_message
                        
                        # Extract and yield tool calls for orchestrator processing
                        if isinstance(chunk.complete_message, dict) and 'output' in chunk.complete_message:
                            response_tool_calls = []
                            for output_item in chunk.complete_message['output']:
                                if output_item.get('type') == 'function_call':
                                    response_tool_calls.append(output_item)
                                    tool_calls.append(output_item)  # Also store for fallback
                            
                            # Yield tool calls so orchestrator can process them
                            if response_tool_calls:
                                yield StreamChunk(type="tool_calls", content=response_tool_calls)
                    elif hasattr(chunk, 'response') and chunk.response:
                        # Alternative attribute name from reference implementation
                        complete_message = chunk.response
                        
                        # Extract and yield tool calls for orchestrator processing
                        if isinstance(chunk.response, dict) and 'output' in chunk.response:
                            response_tool_calls = []
                            for output_item in chunk.response['output']:
                                if output_item.get('type') == 'function_call':
                                    response_tool_calls.append(output_item)
                                    tool_calls.append(output_item)  # Also store for fallback
                            
                            # Yield tool calls so orchestrator can process them
                            if response_tool_calls:
                                yield StreamChunk(type="tool_calls", content=response_tool_calls)
                    # Complete response is for internal use - don't yield it
                elif chunk.type == "done":
                    # Add complete response to history
                    if complete_message:
                        # For Responses API: complete_message is the response object with 'output' array
                        if isinstance(complete_message, dict) and 'output' in complete_message:
                            self.conversation_history.extend(complete_message['output'])
                        else:
                            # Fallback if it's already in message format
                            self.conversation_history.append(complete_message)
                    elif assistant_response.strip() or tool_calls:
                        # Fallback for legacy backends
                        message_data = {"role": "assistant", "content": assistant_response.strip()}
                        if tool_calls:
                            message_data["tool_calls"] = tool_calls
                        self.conversation_history.append(message_data)
                    yield chunk
                else:
                    yield chunk
                    
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            self.add_to_history("assistant", error_msg)
            yield StreamChunk(type="content", content=error_msg)
            yield StreamChunk(type="error", error=str(e))
    
    def _prepare_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Prepare messages with system message.
        
        Args:
            messages: Input messages
            
        Returns:
            List of prepared messages with system message
        """
        prepared_messages = []
        
        # Add system message if not already present
        has_system = any(msg.get("role") == "system" for msg in messages)
        if not has_system and self.system_message:
            prepared_messages.append({
                "role": "system",
                "content": self.system_message
            })
        
        # Add the input messages
        prepared_messages.extend(messages)
        
        return prepared_messages
    
    def _update_conversation_history(self, messages: List[Dict[str, Any]]) -> None:
        """
        Update conversation history with new messages.
        
        Args:
            messages: Messages to add to history
        """
        # Simply append messages - caller is responsible for avoiding duplicates
        # This prevents false duplicate detection based on content matching
        self.conversation_history.extend(messages)
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current agent status and state.
        
        Returns:
            Dict containing comprehensive agent status
        """
        token_usage = self.backend.get_token_usage()
        return {
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "status": self.status,
            "backend": self.backend.get_provider_name(),
            "conversation_length": len(self.conversation_history),
            "token_usage": token_usage.__dict__,
            "total_tokens": token_usage.get_total_tokens(),
            "current_task": self.current_task,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "tools_count": len(self.tools)
        }
    
    def reset(self) -> None:
        """Reset agent state for new conversation."""
        self.conversation_history = []
        self.status = "ready"
        self.current_task = None
        self.error_message = None
        self.backend.reset_token_usage()
    
    def add_tool(self, tool: Dict[str, Any]) -> None:
        """
        Add a tool to the agent's toolkit.
        
        Args:
            tool: Tool definition in OpenAI function format
        """
        if tool not in self.tools:
            self.tools.append(tool)
    
    def remove_tool(self, tool_name: str) -> bool:
        """
        Remove a tool from the agent's toolkit.
        
        Args:
            tool_name: Name of the tool to remove
            
        Returns:
            bool: True if tool was removed, False if not found
        """
        for i, tool in enumerate(self.tools):
            if tool.get("name") == tool_name or tool.get("function", {}).get("name") == tool_name:
                self.tools.pop(i)
                return True
        return False
    
    def set_system_message(self, system_message: str) -> None:
        """
        Update the agent's system message.
        
        Args:
            system_message: New system message
        """
        self.system_message = system_message
    
    def get_tools(self) -> List[Dict[str, Any]]:
        """
        Get current list of tools.
        
        Returns:
            List of tool definitions
        """
        return self.tools.copy()


# Factory function for creating SimpleAgent instances
def create_simple_agent(agent_id: str, 
                       model: str, 
                       api_key: Optional[str] = None,
                       system_message: Optional[str] = None,
                       session_id: Optional[str] = None,
                       **kwargs) -> SimpleAgent:
    """
    Create a SimpleAgent with automatic backend selection.
    
    Args:
        agent_id: Semantic string identifier for the agent
        model: Model name (e.g., "gpt-4o", "claude-3-sonnet")
        api_key: Optional API key for the provider
        system_message: Optional system message
        session_id: Optional session ID
        **kwargs: Additional configuration for the backend
        
    Returns:
        SimpleAgent: Configured SimpleAgent instance
    """
    # Detect provider from model name
    provider = get_provider_from_model(model)
    
    # Create backend
    backend = create_backend(provider, model, api_key=api_key, **kwargs)
    
    # Create and return SimpleAgent
    return SimpleAgent(
        agent_id=agent_id,
        backend=backend,
        system_message=system_message,
        session_id=session_id
    )


# Utility function to create multiple agents
def create_agent_team(agent_configs: List[Dict[str, Any]], 
                     session_id: Optional[str] = None) -> Dict[str, SimpleAgent]:
    """
    Create a team of SimpleAgent instances.
    
    Args:
        agent_configs: List of agent configuration dictionaries
        session_id: Optional shared session ID
        
    Returns:
        Dict mapping agent_id to SimpleAgent instance
    """
    agents = {}
    
    for config in agent_configs:
        agent_id = config["agent_id"]
        model = config["model"]
        
        # Extract optional parameters
        api_key = config.get("api_key")
        system_message = config.get("system_message")
        
        # Create agent
        agent = create_simple_agent(
            agent_id=agent_id,
            model=model,
            api_key=api_key,
            system_message=system_message,
            session_id=session_id,
            **{k: v for k, v in config.items() if k not in ["agent_id", "model", "api_key", "system_message"]}
        )
        
        # Add any tools
        if "tools" in config:
            for tool in config["tools"]:
                agent.add_tool(tool)
        
        agents[agent_id] = agent
    
    return agents