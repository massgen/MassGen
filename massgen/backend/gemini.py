"""
Gemini backend implementation using structured output for voting and answer submission.

APPROACH: Uses structured output instead of function declarations to handle the limitation
where Gemini API cannot combine builtin tools with user-defined function declarations.

KEY FEATURES:
- ✅ Structured output for vote and new_answer mechanisms 
- ✅ Builtin tools support (code_execution + grounding)
- ✅ Streaming with proper token usage tracking
- ✅ Error handling and response parsing
- ✅ Compatible with MassGen v3 StreamChunk architecture

TECHNICAL SOLUTION:
- Uses Pydantic models to define structured output schemas
- Prompts model to use specific JSON format for voting/answering
- Converts structured responses to standard tool call format
- Maintains compatibility with existing MassGen workflow
"""

import os
import json
import enum
from typing import Dict, List, Any, AsyncGenerator, Optional
from .base import LLMBackend, StreamChunk

try:
    from pydantic import BaseModel, Field
except ImportError:
    BaseModel = None
    Field = None


class VoteOption(enum.Enum):
    """Vote options for agent selection."""
    AGENT1 = "agent1"
    AGENT2 = "agent2" 
    AGENT3 = "agent3"
    AGENT4 = "agent4"
    AGENT5 = "agent5"


class ActionType(enum.Enum):
    """Action types for structured output."""
    VOTE = "vote"
    NEW_ANSWER = "new_answer"


class VoteAction(BaseModel):
    """Structured output for voting action."""
    action: ActionType = Field(default=ActionType.VOTE, description="Action type")
    agent_id: str = Field(description="Anonymous agent ID to vote for (e.g., 'agent1', 'agent2')")
    reason: str = Field(description="Brief reason why this agent has the best answer")


class NewAnswerAction(BaseModel):
    """Structured output for new answer action."""
    action: ActionType = Field(default=ActionType.NEW_ANSWER, description="Action type")
    content: str = Field(description="Your improved answer. If any builtin tools like search or code execution were used, include how they are used here.")


class CoordinationResponse(BaseModel):
    """Structured response for coordination actions."""
    action_type: ActionType = Field(description="Type of action to take")
    vote_data: Optional[VoteAction] = Field(default=None, description="Vote data if action is vote")
    answer_data: Optional[NewAnswerAction] = Field(default=None, description="Answer data if action is new_answer")


class GeminiBackend(LLMBackend):
    """Google Gemini backend using structured output for coordination."""
    
    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(api_key, **kwargs)
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        self.search_count = 0
        self.code_execution_count = 0
        
        if BaseModel is None:
            raise ImportError("pydantic is required for Gemini backend. Install with: pip install pydantic")
    
    def detect_coordination_tools(self, tools: List[Dict[str, Any]]) -> bool:
        """Detect if tools contain vote/new_answer coordination tools."""
        if not tools:
            return False
        
        tool_names = set()
        for tool in tools:
            if tool.get("type") == "function":
                if "function" in tool:
                    tool_names.add(tool["function"].get("name", ""))
                elif "name" in tool:
                    tool_names.add(tool.get("name", ""))
        
        return "vote" in tool_names and "new_answer" in tool_names
    
    def build_structured_output_prompt(self, base_content: str, valid_agent_ids: Optional[List[str]] = None) -> str:
        """Build prompt that encourages structured output for coordination."""
        agent_list = ""
        if valid_agent_ids:
            agent_list = f"Valid agents: {', '.join(valid_agent_ids)}"
        
        return f"""{base_content}

IMPORTANT: You must respond with a structured JSON decision at the end of your response.

If you want to VOTE for an existing agent's answer:
{{
  "action_type": "vote",
  "vote_data": {{
    "action": "vote",
    "agent_id": "agent1",  // Choose from: {agent_list or 'agent1, agent2, agent3, etc.'}
    "reason": "Brief reason for your vote"
  }}
}}

If you want to provide a NEW ANSWER:
{{
  "action_type": "new_answer", 
  "answer_data": {{
    "action": "new_answer",
    "content": "Your complete improved answer here"
  }}
}}

Make your decision and include the JSON at the very end of your response."""
    
    def extract_structured_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Extract structured JSON response from model output."""
        try:
            import re
            
            # Strategy 0: Look for JSON inside markdown code blocks first
            markdown_json_pattern = r'```json\s*(\{.*?\})\s*```'
            markdown_matches = re.findall(markdown_json_pattern, response_text, re.DOTALL)
            
            for match in reversed(markdown_matches):
                try:
                    parsed = json.loads(match.strip())
                    if isinstance(parsed, dict) and "action_type" in parsed:
                        return parsed
                except json.JSONDecodeError:
                    continue
            
            # Strategy 1: Look for complete JSON blocks with proper braces
            json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
            json_matches = re.findall(json_pattern, response_text, re.DOTALL)
            
            # Try parsing each match (in reverse order - last one first)
            for match in reversed(json_matches):
                try:
                    cleaned_match = match.strip()
                    parsed = json.loads(cleaned_match)
                    if isinstance(parsed, dict) and "action_type" in parsed:
                        return parsed
                except json.JSONDecodeError:
                    continue
            
            # Strategy 2: Look for JSON blocks with nested braces (more complex)
            brace_count = 0
            json_start = -1
            
            for i, char in enumerate(response_text):
                if char == '{':
                    if brace_count == 0:
                        json_start = i
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0 and json_start >= 0:
                        # Found a complete JSON block
                        json_block = response_text[json_start:i+1]
                        try:
                            parsed = json.loads(json_block)
                            if isinstance(parsed, dict) and "action_type" in parsed:
                                return parsed
                        except json.JSONDecodeError:
                            pass
                        json_start = -1
            
            # Strategy 3: Line-by-line approach (fallback)
            lines = response_text.strip().split('\n')
            json_candidates = []
            
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith('{') and stripped.endswith('}'):
                    json_candidates.append(stripped)
                elif stripped.startswith('{'):
                    # Multi-line JSON - collect until closing brace
                    json_text = stripped
                    for j in range(i + 1, len(lines)):
                        json_text += '\n' + lines[j].strip()
                        if lines[j].strip().endswith('}'):
                            json_candidates.append(json_text)
                            break
            
            # Try to parse each candidate
            for candidate in reversed(json_candidates):
                try:
                    parsed = json.loads(candidate)
                    if isinstance(parsed, dict) and "action_type" in parsed:
                        return parsed
                except json.JSONDecodeError:
                    continue
            
            return None
            
        except Exception:
            return None
    
    def convert_structured_to_tool_calls(self, structured_response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert structured response to tool call format."""
        action_type = structured_response.get("action_type")
        
        if action_type == "vote":
            vote_data = structured_response.get("vote_data", {})
            return [{
                "id": f"vote_{hash(str(vote_data)) % 10000}",
                "type": "function",
                "function": {
                    "name": "vote",
                    "arguments": {
                        "agent_id": vote_data.get("agent_id", ""),
                        "reason": vote_data.get("reason", "")
                    }
                }
            }]
        
        elif action_type == "new_answer":
            answer_data = structured_response.get("answer_data", {})
            return [{
                "id": f"new_answer_{hash(str(answer_data)) % 10000}",
                "type": "function", 
                "function": {
                    "name": "new_answer",
                    "arguments": {
                        "content": answer_data.get("content", "")
                    }
                }
            }]
        
        return []
    
    async def stream_with_tools(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], 
                              **kwargs) -> AsyncGenerator[StreamChunk, None]:
        """Stream response using Gemini API with structured output for coordination."""
        try:
            from google import genai
            
            # Extract parameters
            model_name = kwargs.get("model", "gemini-2.5-flash")
            temperature = kwargs.get("temperature", 0.1)
            enable_web_search = kwargs.get("enable_web_search", False)
            enable_code_execution = kwargs.get("enable_code_execution", False)
            
            # Check if this is a coordination request
            is_coordination = self.detect_coordination_tools(tools)
            valid_agent_ids = None
            
            if is_coordination:
                # Extract valid agent IDs from vote tool enum if available
                for tool in tools:
                    if tool.get("type") == "function":
                        func_def = tool.get("function", {})
                        if func_def.get("name") == "vote":
                            agent_id_param = func_def.get("parameters", {}).get("properties", {}).get("agent_id", {})
                            if "enum" in agent_id_param:
                                valid_agent_ids = agent_id_param["enum"]
                            break
            
            # Build content string from messages
            conversation_content = ""
            system_message = ""
            
            for msg in messages:
                if msg.get("role") == "system":
                    system_message = msg.get("content", "")
                elif msg.get("role") == "user":
                    conversation_content += f"User: {msg.get('content', '')}\n"
                elif msg.get("role") == "assistant":
                    conversation_content += f"Assistant: {msg.get('content', '')}\n"
            
            # For coordination requests, modify the prompt to use structured output
            if is_coordination:
                conversation_content = self.build_structured_output_prompt(conversation_content, valid_agent_ids)
            
            # Combine system message and conversation
            full_content = ""
            if system_message:
                full_content += f"{system_message}\n\n"
            full_content += conversation_content
            
            # Use google-genai package
            client = genai.Client(api_key=self.api_key)
            
            # Setup builtin tools
            builtin_tools = []
            if enable_web_search:
                try:
                    from google.genai import types
                    grounding_tool = types.Tool(google_search=types.GoogleSearch())
                    builtin_tools.append(grounding_tool)
                except ImportError:
                    yield StreamChunk(type="content", content="\n⚠️  Web search requires google.genai.types\n")
            
            if enable_code_execution:
                try:
                    from google.genai import types
                    code_tool = types.Tool(code_execution=types.ToolCodeExecution())
                    builtin_tools.append(code_tool)
                except ImportError:
                    yield StreamChunk(type="content", content="\n⚠️  Code execution requires google.genai.types\n")
            
            config = {
                "temperature": temperature,
                "max_output_tokens": kwargs.get("max_tokens", 8192),
            }
            
            # Add builtin tools to config
            if builtin_tools:
                config["tools"] = builtin_tools
            
            # For coordination requests, use JSON response format (may conflict with builtin tools)
            if is_coordination and not builtin_tools:
                config["response_mime_type"] = "application/json"
                config["response_schema"] = CoordinationResponse.model_json_schema()
            elif is_coordination and builtin_tools:
                # Cannot use structured output with builtin tools - fallback to text parsing
                pass
            
            # Use streaming for real-time response
            full_content_text = ""
            final_response = None
            
            for chunk in client.models.generate_content_stream(
                model=model_name,
                contents=full_content,
                config=config
            ):
                if hasattr(chunk, 'text') and chunk.text:
                    chunk_text = chunk.text
                    full_content_text += chunk_text
                    yield StreamChunk(type="content", content=chunk_text)
                
                # Keep track of the final response for tool processing
                if hasattr(chunk, 'candidates'):
                    final_response = chunk
                    
                # Check for tools used in each chunk for real-time detection
                if builtin_tools and hasattr(chunk, 'candidates') and chunk.candidates:
                    candidate = chunk.candidates[0]
                    
                    # Check for code execution in this chunk
                    if enable_code_execution and hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                        for part in candidate.content.parts:
                            if hasattr(part, 'executable_code') and part.executable_code:
                                code_content = getattr(part.executable_code, 'code', str(part.executable_code))
                                yield StreamChunk(type="content", content=f"\n💻 [Code Executed]\n```python\n{code_content}\n```\n")
                            elif hasattr(part, 'code_execution_result') and part.code_execution_result:
                                result_content = getattr(part.code_execution_result, 'output', str(part.code_execution_result))
                                yield StreamChunk(type="content", content=f"📊 [Result] {result_content}\n")
            
            content = full_content_text
            
            # Process coordination FIRST (before adding tool indicators that might confuse parsing)
            tool_calls_detected = []
            if is_coordination and content.strip():
                # For structured output mode, the entire content is JSON
                structured_response = None
                # Try multiple parsing strategies
                try:
                    # Strategy 1: Parse entire content as JSON (works for both modes)
                    structured_response = json.loads(content.strip())
                except json.JSONDecodeError:
                    # Strategy 2: Extract JSON from mixed text content (handles markdown-wrapped JSON)
                    structured_response = self.extract_structured_response(content)
                
                if structured_response and isinstance(structured_response, dict) and "action_type" in structured_response:
                    # Convert to tool calls
                    tool_calls = self.convert_structured_to_tool_calls(structured_response)
                    if tool_calls:
                        tool_calls_detected = tool_calls
            
            # Process builtin tool results if any tools were used
            builtin_tool_results = []
            if builtin_tools and final_response and hasattr(final_response, 'candidates') and final_response.candidates:
                # Check for grounding or code execution results
                candidate = final_response.candidates[0]
                
                # Check for web search results - only show if actually used
                if hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata:
                    # Check if web search was actually used by looking for queries or chunks
                    search_actually_used = False
                    search_queries = []
                    
                    # Look for web search queries
                    if hasattr(candidate.grounding_metadata, 'web_search_queries') and candidate.grounding_metadata.web_search_queries:
                        try:
                            for query in candidate.grounding_metadata.web_search_queries:
                                if query and query.strip():
                                    search_queries.append(query.strip())
                                    search_actually_used = True
                        except (TypeError, AttributeError):
                            pass
                    
                    # Look for grounding chunks (indicates actual search results)
                    if hasattr(candidate.grounding_metadata, 'grounding_chunks') and candidate.grounding_metadata.grounding_chunks:
                        try:
                            if len(candidate.grounding_metadata.grounding_chunks) > 0:
                                search_actually_used = True
                        except (TypeError, AttributeError):
                            pass
                    
                    # Only show indicators if search was actually used
                    if search_actually_used:
                        yield StreamChunk(type="content", content="🔍 [Builtin Tool: Web Search] Results integrated\n")
                        
                        # Show search queries
                        for query in search_queries:
                            yield StreamChunk(type="content", content=f"🔍 [Search Query] '{query}'\n")
                        
                        builtin_result = {
                            "id": f"web_search_{hash(str(candidate.grounding_metadata)) % 10000}",
                            "tool_type": "google_search_retrieval",
                            "status": "completed",
                            "metadata": str(candidate.grounding_metadata)
                        }
                        builtin_tool_results.append(builtin_result)
                        self.search_count += 1
                
                # Check for code execution in the response parts
                if enable_code_execution and hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                    # Look for executable_code and code_execution_result parts
                    code_parts = []
                    for part in candidate.content.parts:
                        if hasattr(part, 'executable_code') and part.executable_code:
                            code_content = getattr(part.executable_code, 'code', str(part.executable_code))
                            code_parts.append(f"Code: {code_content}")
                        elif hasattr(part, 'code_execution_result') and part.code_execution_result:
                            result_content = getattr(part.code_execution_result, 'output', str(part.code_execution_result))
                            code_parts.append(f"Result: {result_content}")
                    
                    if code_parts:
                        # Code execution was actually used
                        yield StreamChunk(type="content", content="💻 [Builtin Tool: Code Execution] Code executed\n")
                        # Also show the actual code and result
                        for part in code_parts:
                            if part.startswith("Code: "):
                                code_content = part[6:]  # Remove "Code: " prefix
                                yield StreamChunk(type="content", content=f"💻 [Code Executed]\n```python\n{code_content}\n```\n")
                            elif part.startswith("Result: "):
                                result_content = part[8:]  # Remove "Result: " prefix
                                yield StreamChunk(type="content", content=f"📊 [Result] {result_content}\n")
                        
                        builtin_result = {
                            "id": f"code_execution_{hash(str(code_parts)) % 10000}",
                            "tool_type": "code_execution", 
                            "status": "completed",
                            "code_parts": code_parts,
                            "output": "; ".join(code_parts)
                        }
                        builtin_tool_results.append(builtin_result)
                        self.code_execution_count += 1
            
            # Yield builtin tool results
            if builtin_tool_results:
                yield StreamChunk(type="builtin_tool_results", builtin_tool_results=builtin_tool_results)
            
            # Yield coordination tool calls if detected
            if tool_calls_detected:
                yield StreamChunk(type="tool_calls", tool_calls=tool_calls_detected)
            
            # Build complete message
            complete_message = {
                "role": "assistant",
                "content": content.strip()
            }
            if tool_calls_detected:
                complete_message["tool_calls"] = tool_calls_detected
            
            yield StreamChunk(type="complete_message", complete_message=complete_message)
            yield StreamChunk(type="done")
            
        except Exception as e:
            yield StreamChunk(type="error", error=f"Gemini API error: {e}")
    
    def get_provider_name(self) -> str:
        """Get the provider name."""
        return "Gemini"
    
    def get_supported_builtin_tools(self) -> List[str]:
        """Get list of builtin tools supported by Gemini."""
        return ["google_search_retrieval", "code_execution"]
    
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text (Gemini uses ~4 chars per token)."""
        return len(text) // 4
    
    def calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """Calculate cost for Gemini token usage (2025 pricing)."""
        model_lower = model.lower()
        
        if "gemini-2.5-pro" in model_lower:
            # Gemini 2.5 Pro pricing
            input_cost = (input_tokens / 1_000_000) * 1.25
            output_cost = (output_tokens / 1_000_000) * 5.0
        elif "gemini-2.5-flash" in model_lower:
            if "lite" in model_lower:
                # Gemini 2.5 Flash-Lite pricing
                input_cost = (input_tokens / 1_000_000) * 0.075
                output_cost = (output_tokens / 1_000_000) * 0.30
            else:
                # Gemini 2.5 Flash pricing
                input_cost = (input_tokens / 1_000_000) * 0.15
                output_cost = (output_tokens / 1_000_000) * 0.60
        else:
            # Default fallback (assume Flash pricing)
            input_cost = (input_tokens / 1_000_000) * 0.15
            output_cost = (output_tokens / 1_000_000) * 0.60
        
        # Add tool usage costs (estimates)
        tool_costs = 0.0
        if self.search_count > 0:
            tool_costs += self.search_count * 0.01  # Estimated search cost
        
        if self.code_execution_count > 0:
            tool_costs += self.code_execution_count * 0.005  # Estimated execution cost
        
        return input_cost + output_cost + tool_costs
    
    def reset_tool_usage(self):
        """Reset tool usage tracking."""
        self.search_count = 0
        self.code_execution_count = 0
        super().reset_token_usage()