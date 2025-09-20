"""
Gemini backend implementation - REFACTORED VERSION.
Uses internal helper classes and mixins to reduce from 2506 lines to ~1400 lines.
Maintains single file structure with better organization.
"""

from __future__ import annotations

import os
import json
import asyncio
from typing import Dict, List, Any, AsyncGenerator, Optional, Union
import google.generativeai as genai
from google.ai.generativelanguage_v1beta import Content, Part, FunctionCall, FunctionResponse

from .base import LLMBackend, StreamChunk, FilesystemSupport  
from .mcp_integration import MCPIntegrationMixin
from .tool_handlers import ToolHandlerMixin, ToolFormat
from .token_management import TokenCostCalculator
from .utils import StreamAccumulator, StreamProcessor
from .utils import MessageConverter, APIRequestBuilder, ResponseParser
from ..logger_config import log_backend_activity, logger


class GeminiBackend(LLMBackend, MCPIntegrationMixin, ToolHandlerMixin):
    """
    Gemini backend implementation - REFACTORED.
    Uses internal helper classes to organize complexity while maintaining single file.
    """
    
    # ============== INTERNAL HELPER CLASSES ==============
    
    class GeminiSessionManager:
        """Internal class to manage Gemini chat sessions."""
        
        def __init__(self, api_key: str):
            self.api_key = api_key
            self.sessions: Dict[str, Any] = {}
            self.models: Dict[str, Any] = {}
            genai.configure(api_key=api_key)
        
        async def get_or_create_session(
            self,
            model_name: str,
            generation_config: Optional[Dict] = None,
            safety_settings: Optional[List] = None,
            tools: Optional[List] = None
        ) -> Any:
            """Get existing or create new chat session."""
            session_key = f"{model_name}_{hash(str(tools))}"
            
            if session_key not in self.sessions:
                # Create model if not exists
                if model_name not in self.models:
                    self.models[model_name] = genai.GenerativeModel(
                        model_name=model_name,
                        generation_config=generation_config,
                        safety_settings=safety_settings,
                        tools=tools
                    )
                
                # Create chat session
                self.sessions[session_key] = self.models[model_name].start_chat()
            
            return self.sessions[session_key]
        
        def clear_session(self, model_name: str):
            """Clear a specific session."""
            session_keys = [k for k in self.sessions.keys() if k.startswith(model_name)]
            for key in session_keys:
                del self.sessions[key]
        
        def clear_all_sessions(self):
            """Clear all sessions."""
            self.sessions.clear()
            self.models.clear()
    
    class GeminiStreamHandler:
        """Internal class to handle Gemini-specific streaming."""
        
        def __init__(self, backend: 'GeminiBackend'):
            self.backend = backend
            self.accumulator = StreamAccumulator()
        
        async def handle_stream(
            self,
            response_stream: AsyncGenerator,
            execute_mcp_func: Optional[callable] = None
        ) -> AsyncGenerator[StreamChunk, None]:
            """
            Process Gemini streaming response.
            """
            try:
                async for chunk in response_stream:
                    # Process candidates
                    if hasattr(chunk, 'candidates') and chunk.candidates:
                        for candidate in chunk.candidates:
                            # Extract content
                            if hasattr(candidate, 'content') and candidate.content:
                                async for stream_chunk in self._process_content(
                                    candidate.content,
                                    execute_mcp_func
                                ):
                                    yield stream_chunk
                            
                            # Check finish reason
                            if hasattr(candidate, 'finish_reason'):
                                self.accumulator.set_finish_reason(
                                    str(candidate.finish_reason)
                                )
                    
                    # Extract usage metadata
                    if hasattr(chunk, 'usage_metadata'):
                        self.accumulator.set_usage({
                            "prompt_tokens": chunk.usage_metadata.prompt_token_count,
                            "completion_tokens": chunk.usage_metadata.candidates_token_count,
                            "total_tokens": chunk.usage_metadata.total_token_count
                        })
                
                yield StreamChunk(type="done")
                
            except Exception as e:
                logger.error(f"Gemini stream error: {e}")
                yield StreamChunk(type="error", error=str(e))
        
        async def _process_content(
            self,
            content: Content,
            execute_mcp_func: Optional[callable] = None
        ) -> AsyncGenerator[StreamChunk, None]:
            """Process Gemini content parts."""
            if not hasattr(content, 'parts'):
                return
            
            for part in content.parts:
                # Handle text
                if hasattr(part, 'text') and part.text:
                    self.accumulator.add_content(part.text)
                    yield StreamChunk(type="content", content=part.text)
                
                # Handle function calls
                elif hasattr(part, 'function_call'):
                    func_call = part.function_call
                    tool_call = {
                        "id": f"call_{hash(func_call.name)}",
                        "type": "function",
                        "function": {
                            "name": func_call.name,
                            "arguments": json.dumps(dict(func_call.args))
                        }
                    }
                    
                    self.accumulator.add_tool_call(0, tool_call)
                    yield StreamChunk(type="tool_calls", tool_calls=[tool_call])
                    
                    # Execute MCP tools if available
                    if execute_mcp_func:
                        results = await execute_mcp_func([tool_call])
                        for result in results:
                            yield StreamChunk(
                                type="tool_result",
                                content=result["content"]
                            )
    
    class GeminiMessageConverter:
        """Internal class for Gemini-specific message conversions."""
        
        def __init__(self, base_converter: MessageConverter):
            self.base_converter = base_converter
        
        def to_gemini_contents(self, messages: List[Dict[str, Any]]) -> List[Content]:
            """
            Convert messages to Gemini Content objects.
            """
            contents = []
            
            # First convert to Gemini dict format
            gemini_messages = self.base_converter.to_gemini_format(messages)
            
            for msg in gemini_messages:
                role = msg.get("role", "user")
                parts_data = msg.get("parts", [])
                
                # Create Part objects
                parts = []
                for part_data in parts_data:
                    if isinstance(part_data, dict):
                        if "text" in part_data:
                            parts.append(Part(text=part_data["text"]))
                        elif "functionCall" in part_data:
                            fc = part_data["functionCall"]
                            parts.append(Part(
                                function_call=FunctionCall(
                                    name=fc["name"],
                                    args=fc.get("args", {})
                                )
                            ))
                        elif "functionResponse" in part_data:
                            fr = part_data["functionResponse"]
                            parts.append(Part(
                                function_response=FunctionResponse(
                                    name=fr["name"],
                                    response=fr.get("response", {})
                                )
                            ))
                
                if parts:
                    contents.append(Content(role=role, parts=parts))
            
            return contents
        
        def merge_system_into_first_user(
            self,
            messages: List[Dict[str, Any]]
        ) -> List[Dict[str, Any]]:
            """
            Gemini doesn't support system role, merge into first user message.
            """
            system_prompt, other_messages = self.base_converter.merge_system_messages(messages)
            
            if system_prompt and other_messages:
                # Find first user message
                for i, msg in enumerate(other_messages):
                    if msg.get("role") == "user":
                        content = msg.get("content", "")
                        if isinstance(content, str):
                            other_messages[i]["content"] = f"{system_prompt}\n\n{content}"
                        elif isinstance(content, list):
                            # Add system as first text block
                            other_messages[i]["content"].insert(0, {
                                "type": "text",
                                "text": system_prompt
                            })
                        break
                else:
                    # No user message found, add one
                    other_messages.insert(0, {
                        "role": "user",
                        "content": system_prompt
                    })
            
            return other_messages
    
    class GeminiToolHandler:
        """Internal class for Gemini tool handling."""
        
        def __init__(self, backend: 'GeminiBackend'):
            self.backend = backend
        
        def convert_tools_to_gemini(self, tools: List[Dict[str, Any]]) -> List[Any]:
            """
            Convert tools to Gemini function declarations.
            """
            if not tools:
                return []
            
            # Use backend's tool handler mixin
            gemini_tools = self.backend.convert_tools_format(tools, ToolFormat.GEMINI)
            
            # Create Gemini function declaration objects
            function_declarations = []
            for tool in gemini_tools:
                if "functionDeclarations" in tool:
                    for func_decl in tool["functionDeclarations"]:
                        function_declarations.append(func_decl)
            
            return function_declarations
        
        async def prepare_all_tools(
            self,
            user_tools: List[Dict[str, Any]],
            kwargs: Dict[str, Any]
        ) -> List[Any]:
            """Prepare all tools including MCP."""
            all_tools = []
            
            # Convert user tools
            if user_tools:
                filtered_tools = self.backend.filter_tools(
                    user_tools,
                    allowed=self.backend.allowed_tools,
                    excluded=self.backend.exclude_tools
                )
                all_tools.extend(filtered_tools)
            
            # Add MCP tools if available
            if self.backend._mcp_initialized and self.backend.functions:
                mcp_tools = []
                for func_name, func in self.backend.functions.items():
                    mcp_tools.append({
                        "type": "function",
                        "name": func_name,
                        "description": func.description or "",
                        "parameters": func.input_schema or {}
                    })
                all_tools.extend(mcp_tools)
            
            # Convert all to Gemini format
            return self.convert_tools_to_gemini(all_tools)
    
    # ============== MAIN BACKEND CLASS ==============
    
    # Parameters to exclude from API calls
    EXCLUDED_API_PARAMS = LLMBackend.get_base_excluded_config_params().union({
        "api_key",
        "project_id",
        "location",
        "allowed_tools",
        "exclude_tools",
    })
    
    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(api_key, **kwargs)
        
        # API configuration
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("Google/Gemini API key required")
        
        # Initialize mixins
        self._init_mcp_integration(**kwargs)
        
        # Initialize utilities
        self.token_calculator = TokenCostCalculator()
        self.message_converter = MessageConverter()
        self.request_builder = APIRequestBuilder()
        
        # Initialize internal helpers
        self.session_manager = self.GeminiSessionManager(self.api_key)
        self.stream_handler = self.GeminiStreamHandler(self)
        self.gemini_converter = self.GeminiMessageConverter(self.message_converter)
        self.tool_handler = self.GeminiToolHandler(self)
        
        # Backend identification
        self.backend_name = self.get_provider_name()
        self.agent_id = kwargs.get('agent_id', None)
    
    def get_provider_name(self) -> str:
        """Get the name of this provider."""
        return "Gemini"
    
    def get_filesystem_support(self) -> FilesystemSupport:
        """Gemini supports filesystem through MCP servers."""
        return FilesystemSupport.MCP if self.mcp_servers else FilesystemSupport.NONE
    
    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Stream response with tool support - REFACTORED.
        Uses internal helpers to reduce complexity.
        """
        agent_id = kwargs.get('agent_id', self.agent_id)
        
        log_backend_activity(
            self.backend_name,
            "Starting stream_with_tools",
            {"num_messages": len(messages), "num_tools": len(tools) if tools else 0},
            agent_id=agent_id
        )
        
        try:
            # Initialize MCP if needed (mixin)
            if self.mcp_servers and not self._mcp_initialized:
                await self._initialize_mcp_client()
            
            # Prepare messages
            prepared_messages = self.gemini_converter.merge_system_into_first_user(messages)
            gemini_contents = self.gemini_converter.to_gemini_contents(prepared_messages)
            
            # Prepare tools
            gemini_tools = await self.tool_handler.prepare_all_tools(tools, kwargs)
            
            # Build generation config
            generation_config = self._build_generation_config(kwargs)
            safety_settings = self._build_safety_settings(kwargs)
            
            # Get or create session
            session = await self.session_manager.get_or_create_session(
                model_name=kwargs.get("model", "gemini-1.5-pro"),
                generation_config=generation_config,
                safety_settings=safety_settings,
                tools=gemini_tools
            )
            
            # Send message and stream response
            response = await session.send_message_async(
                gemini_contents[-1] if gemini_contents else "",
                stream=True
            )
            
            # Handle streaming with internal handler
            async for chunk in self.stream_handler.handle_stream(
                response,
                self._execute_mcp_tools if self._mcp_initialized else None
            ):
                yield chunk
            
            # Update token usage
            if self.stream_handler.accumulator.usage:
                usage = self.stream_handler.accumulator.usage
                self.token_usage.input_tokens += usage.get("prompt_tokens", 0)
                self.token_usage.output_tokens += usage.get("completion_tokens", 0)
                self.token_usage.estimated_cost += self.token_calculator.calculate_cost(
                    usage.get("prompt_tokens", 0),
                    usage.get("completion_tokens", 0),
                    "Google",
                    kwargs.get("model", "gemini-1.5-pro")
                )
            
        except Exception as e:
            logger.error(f"Gemini API error: {str(e)}")
            yield StreamChunk(type="error", error=str(e))
    
    def _build_generation_config(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Build Gemini generation configuration."""
        config = {}
        
        param_map = {
            "temperature": "temperature",
            "top_p": "top_p",
            "top_k": "top_k",
            "max_tokens": "max_output_tokens",
            "stop_sequences": "stop_sequences"
        }
        
        for key, gemini_key in param_map.items():
            if key in kwargs:
                config[gemini_key] = kwargs[key]
        
        return config or None
    
    def _build_safety_settings(self, kwargs: Dict[str, Any]) -> List[Dict[str, str]]:
        """Build Gemini safety settings."""
        # Use request builder helper
        params = self.request_builder.add_safety_settings({}, "gemini")
        return params.get("safety_settings", [])
    
    # Token and cost methods use mixins
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count using unified calculator."""
        return self.token_calculator.estimate_tokens(text)
    
    def calculate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str
    ) -> float:
        """Calculate cost using unified calculator."""
        return self.token_calculator.calculate_cost(
            input_tokens, output_tokens, "Google", model
        )
    
    def get_supported_builtin_tools(self) -> List[str]:
        """Gemini supports code execution natively."""
        return ["code_execution"]
    
    def clear_history(self) -> None:
        """Clear conversation history while maintaining session."""
        self.session_manager.clear_all_sessions()
    
    def reset_state(self) -> None:
        """Reset backend state."""
        self.clear_history()
        self.reset_token_usage()