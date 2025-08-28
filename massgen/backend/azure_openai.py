from __future__ import annotations

"""
Azure OpenAI backend implementation.
Uses the official Azure OpenAI client for proper Azure integration.
"""

import os
from typing import Dict, List, Any, AsyncGenerator, Optional
from .base import LLMBackend, StreamChunk
from ..logger_config import log_backend_activity, log_backend_agent_message, log_stream_chunk


class AzureOpenAIBackend(LLMBackend):
    """Azure OpenAI backend using the official Azure OpenAI client.

    Supports Azure OpenAI deployments with proper Azure authentication and configuration.

    Environment Variables:
        AZURE_OPENAI_API_KEY: Azure OpenAI API key
        AZURE_OPENAI_ENDPOINT: Azure OpenAI endpoint URL
        AZURE_OPENAI_API_VERSION: Azure OpenAI API version (optional, defaults to 2024-12-01-preview)
    """

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(api_key, **kwargs)

        # Get Azure configuration from parameters or environment variables
        self.api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY")

        if not self.api_key:
            raise ValueError(
                "Azure OpenAI API key is required. Set AZURE_OPENAI_API_KEY environment variable or pass api_key parameter."
            )

    def get_provider_name(self) -> str:
        """Get the name of this provider."""
        return "Azure OpenAI"

    async def stream_with_tools(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Stream a response with tool calling support using Azure OpenAI.

        Args:
            messages: Conversation messages
            tools: Available tools schema
            **kwargs: Additional parameters including model (deployment name)
        """
        # Extract agent_id for logging
        agent_id = kwargs.get('agent_id', None)
        
        log_backend_activity(
            self.get_provider_name(),
            "Starting stream_with_tools",
            {"num_messages": len(messages), "num_tools": len(tools) if tools else 0},
            agent_id=agent_id
        )
        
        try:
            # Merge constructor config with stream kwargs (stream kwargs take priority)
            all_params = {**self.config, **kwargs}

            # Import Azure OpenAI client
            from openai import AsyncAzureOpenAI

            azure_endpoint = (
                all_params.get("azure_endpoint")
                or all_params.get("base_url")
                or os.getenv("AZURE_OPENAI_ENDPOINT")
            )
            api_version = all_params.get("api_version") or os.getenv(
                "AZURE_OPENAI_API_VERSION", "2024-12-01-preview"
            )

            # Validate required configuration
            if not azure_endpoint:
                raise ValueError(
                    "Azure OpenAI endpoint URL is required. Set AZURE_OPENAI_ENDPOINT environment variable or pass azure_endpoint/base_url parameter."
                )

            if not api_version:
                raise ValueError(
                    "Azure OpenAI API version is required. Set AZURE_OPENAI_API_VERSION environment variable or pass api_version parameter."
                )

            # Clean up endpoint URL
            if azure_endpoint.endswith("/"):
                azure_endpoint = azure_endpoint[:-1]

            # Initialize Azure OpenAI client
            self.client = AsyncAzureOpenAI(
                api_version=api_version,
                azure_endpoint=azure_endpoint,
                api_key=self.api_key,
            )

            # Get deployment name from model parameter
            deployment_name = all_params.get("model")
            if not deployment_name:
                raise ValueError(
                    "Azure OpenAI requires a deployment name. Pass it as the 'model' parameter."
                )

            # Check if workflow tools are present
            workflow_tools = (
                [
                    t
                    for t in tools
                    if t.get("function", {}).get("name") in ["new_answer", "vote"]
                ]
                if tools
                else []
            )
            has_workflow_tools = len(workflow_tools) > 0

            # Modify messages to include workflow tool instructions if needed
            modified_messages = (
                self._prepare_messages_with_workflow_tools(messages, workflow_tools)
                if has_workflow_tools
                else messages
            )
            
            # Log messages being sent
            log_backend_agent_message(
                agent_id or "default",
                "SEND",
                {"messages": modified_messages, "tools": len(tools) if tools else 0},
                backend_name=self.get_provider_name()
            )

            # Prepare API parameters
            api_params = {
                "messages": modified_messages,
                "model": deployment_name,  # Use deployment name directly
                "stream": True,
            }

            # Only add tools if explicitly provided and not empty
            if tools and len(tools) > 0:
                # Convert tools to Azure OpenAI format if needed
                converted_tools = self._convert_tools_format(tools)
                api_params["tools"] = converted_tools
            else:
                # Disable tool calling for simple queries
                api_params["tool_choice"] = "none"

            # Add other parameters (excluding model since we already set it)
            # Filter out unsupported Azure OpenAI parameters
            excluded_params = {
                "model",
                "messages",
                "stream",
                "tools",
                "agent_id",
                "session_id",
                "type"
            }
            for key, value in kwargs.items():
                if key not in excluded_params and value is not None:
                    api_params[key] = value

            # Create streaming response (now properly async)
            stream = await self.client.chat.completions.create(**api_params)

            # Process streaming response with content accumulation
            accumulated_content = ""
            complete_response = ""  # Keep track of the complete response
            last_yield_type = None

            async for chunk in stream:
                converted = self._convert_chunk_to_stream_chunk(chunk)

                # Accumulate content chunks
                if converted.type == "content" and converted.content:
                    accumulated_content += converted.content
                    complete_response += converted.content  # Add to complete response
                    # Only yield content when we have meaningful chunks (words, not single characters)
                    if len(accumulated_content) >= 10 or " " in accumulated_content:
                        log_backend_agent_message(
                            agent_id or "default",
                            "RECV",
                            {"content": accumulated_content},
                            backend_name=self.get_provider_name()
                        )
                        log_stream_chunk("backend.azure_openai", "content", accumulated_content, agent_id)
                        yield StreamChunk(type="content", content=accumulated_content)
                        accumulated_content = ""
                elif converted.type != "content":
                    # Log non-content chunks
                    if converted.type == "error":
                        log_stream_chunk("backend.azure_openai", "error", converted.error, agent_id)
                    elif converted.type == "done":
                        log_stream_chunk("backend.azure_openai", "done", None, agent_id)
                    # Yield non-content chunks immediately
                    yield converted
                    last_yield_type = converted.type

            # Yield any remaining accumulated content
            if accumulated_content:
                log_backend_agent_message(
                    agent_id or "default",
                    "RECV",
                    {"content": accumulated_content},
                    backend_name=self.get_provider_name()
                )
                log_stream_chunk("backend.azure_openai", "content", accumulated_content, agent_id)
                yield StreamChunk(type="content", content=accumulated_content)

            # After streaming is complete, check if we have workflow tool calls
            if has_workflow_tools:
                workflow_tool_calls = self._extract_workflow_tool_calls(
                    complete_response
                )
                if workflow_tool_calls:
                    log_stream_chunk("backend.azure_openai", "tool_calls", workflow_tool_calls, agent_id)
                    yield StreamChunk(type="tool_calls", tool_calls=workflow_tool_calls)
                    last_yield_type = "tool_calls"

            # Ensure stream termination is signaled
            if last_yield_type != "done":
                log_stream_chunk("backend.azure_openai", "done", None, agent_id)
                yield StreamChunk(type="done")

        except Exception as e:
            error_msg = f"Azure OpenAI API error: {str(e)}"
            log_stream_chunk("backend.azure_openai", "error", error_msg, agent_id)
            yield StreamChunk(type="error", error=error_msg)

    def _prepare_messages_with_workflow_tools(
        self, messages: List[Dict[str, Any]], workflow_tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Prepare messages with workflow tool instructions."""
        if not workflow_tools:
            return messages

        # Find the system message
        system_message = None
        for msg in messages:
            if msg.get("role") == "system":
                system_message = msg
                break

        # Create enhanced system message with workflow tool instructions
        enhanced_system = self._build_workflow_tools_system_prompt(
            system_message.get("content", "") if system_message else "", workflow_tools
        )

        # Create new messages list with enhanced system message
        new_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                new_messages.append({"role": "system", "content": enhanced_system})
            else:
                new_messages.append(msg)

        return new_messages

    def _build_workflow_tools_system_prompt(
        self, base_system: str, workflow_tools: List[Dict[str, Any]]
    ) -> str:
        """Build system prompt with workflow tool instructions."""
        system_parts = []

        if base_system:
            system_parts.append(base_system)

        # Add workflow tools information
        if workflow_tools:
            system_parts.append("\n--- Available Tools ---")
            for tool in workflow_tools:
                name = tool.get("function", {}).get("name", "unknown")
                description = tool.get("function", {}).get(
                    "description", "No description"
                )
                system_parts.append(f"- {name}: {description}")

                # Add usage examples for workflow tools
                if name == "new_answer":
                    system_parts.append(
                        '    Usage: {"tool_name": "new_answer", '
                        '"arguments": {"content": "your answer"}}'
                    )
                elif name == "vote":
                    # Extract valid agent IDs from enum if available
                    agent_id_enum = None
                    for t in workflow_tools:
                        if t.get("function", {}).get("name") == "vote":
                            agent_id_param = (
                                t.get("function", {})
                                .get("parameters", {})
                                .get("properties", {})
                                .get("agent_id", {})
                            )
                            if "enum" in agent_id_param:
                                agent_id_enum = agent_id_param["enum"]
                            break

                    if agent_id_enum:
                        agent_list = ", ".join(agent_id_enum)
                        system_parts.append(
                            f'    Usage: {{"tool_name": "vote", '
                            f'"arguments": {{"agent_id": "agent1", '
                            f'"reason": "explanation"}}}} // Choose agent_id from: {agent_list}'
                        )
                    else:
                        system_parts.append(
                            '    Usage: {"tool_name": "vote", '
                            '"arguments": {"agent_id": "agent1", '
                            '"reason": "explanation"}}'
                        )

            system_parts.append("\n--- MassGen Workflow Instructions ---")
            system_parts.append(
                "IMPORTANT: You must respond with a structured JSON decision at the end of your response."
            )
            system_parts.append(
                "You must use the coordination tools (new_answer, vote) "
                "to participate in multi-agent workflows."
            )
            system_parts.append(
                "The JSON MUST be formatted as a strict JSON code block:"
            )
            system_parts.append("1. Start with ```json on one line")
            system_parts.append("2. Include your JSON content (properly formatted)")
            system_parts.append("3. End with ``` on one line")
            system_parts.append(
                'Example format:\n```json\n{"tool_name": "vote", "arguments": {"agent_id": "agent1", "reason": "explanation"}}\n```'
            )
            system_parts.append(
                "The JSON block should be placed at the very end of your response, after your analysis."
            )

        return "\n".join(system_parts)

    def _extract_workflow_tool_calls(self, content: str) -> List[Dict[str, Any]]:
        """Extract workflow tool calls from content."""
        try:
            import re
            import json

            # Look for JSON inside markdown code blocks first
            markdown_json_pattern = r"```json\s*(\{.*?\})\s*```"
            markdown_matches = re.findall(markdown_json_pattern, content, re.DOTALL)

            for match in reversed(markdown_matches):
                try:
                    parsed = json.loads(match.strip())
                    if isinstance(parsed, dict) and "tool_name" in parsed:
                        # Convert to MassGen tool call format
                        tool_call = {
                            "id": f"call_{hash(match) % 10000}",  # Generate a unique ID
                            "type": "function",
                            "function": {
                                "name": parsed["tool_name"],
                                "arguments": json.dumps(parsed["arguments"]),
                            },
                        }
                        return [tool_call]
                except json.JSONDecodeError:
                    continue

            # Also look for JSON without markdown blocks
            json_pattern = r'\{[^{}]*"tool_name"[^{}]*\}'
            json_matches = re.findall(json_pattern, content, re.DOTALL)

            for match in json_matches:
                try:
                    parsed = json.loads(match.strip())
                    if isinstance(parsed, dict) and "tool_name" in parsed:
                        # Convert to MassGen tool call format
                        tool_call = {
                            "id": f"call_{hash(match) % 10000}",  # Generate a unique ID
                            "type": "function",
                            "function": {
                                "name": parsed["tool_name"],
                                "arguments": json.dumps(parsed["arguments"]),
                            },
                        }
                        return [tool_call]
                except json.JSONDecodeError:
                    continue

            return []

        except Exception as e:
            return []

    def _convert_tools_format(
        self, tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Convert tools to Azure OpenAI format if needed."""
        # Azure OpenAI uses the same tool format as OpenAI
        return tools

    def _convert_chunk_to_stream_chunk(self, chunk) -> StreamChunk:
        """Convert Azure OpenAI chunk to MassGen StreamChunk format."""
        try:
            if hasattr(chunk, "choices") and chunk.choices:
                choice = chunk.choices[0]

                if hasattr(choice, "delta") and choice.delta:
                    delta = choice.delta

                    # Handle content - this should be the main response
                    if hasattr(delta, "content") and delta.content:
                        return StreamChunk(type="content", content=delta.content)

                    # Handle tool calls - but only if we actually want them
                    if hasattr(delta, "tool_calls") and delta.tool_calls:
                        # For now, let's ignore tool calls and treat them as content
                        # This prevents the empty response issue
                        tool_call_text = ""
                        for tool_call in delta.tool_calls:
                            if hasattr(tool_call, "function") and tool_call.function:
                                if (
                                    hasattr(tool_call.function, "arguments")
                                    and tool_call.function.arguments
                                ):
                                    tool_call_text += tool_call.function.arguments

                        if tool_call_text:
                            return StreamChunk(type="content", content=tool_call_text)

                    # Handle finish reason
                    if hasattr(choice, "finish_reason") and choice.finish_reason:
                        if choice.finish_reason == "stop":
                            return StreamChunk(type="done")
                        elif choice.finish_reason == "tool_calls":
                            return StreamChunk(type="done")  # Treat as done

            # Default chunk - this should not happen for valid responses
            return StreamChunk(type="content", content="")

        except Exception as e:
            return StreamChunk(type="error", error=f"Error processing chunk: {str(e)}")

    # --- Tool call helpers (Chat Completions compatible) ---
    def extract_tool_name(self, tool_call: Dict[str, Any]) -> str:
        """Extract tool name from Chat Completions-style tool call."""
        return tool_call.get("function", {}).get("name", "unknown")

    def extract_tool_arguments(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """Extract tool arguments and parse JSON string if necessary."""
        arguments = tool_call.get("function", {}).get("arguments", {})
        if isinstance(arguments, str):
            try:
                import json

                return json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError:
                return {}
        return arguments

    def extract_tool_call_id(self, tool_call: Dict[str, Any]) -> str:
        """Extract tool call id from Chat Completions-style tool call."""
        return tool_call.get("id", "")

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text using Azure OpenAI tokenizer."""
        # Azure OpenAI uses the same tokenization as OpenAI
        # This is a rough estimation - for precise counting, use tiktoken
        return len(text.split()) * 1.3

    def calculate_cost(
        self, input_tokens: int, output_tokens: int, model: str
    ) -> float:
        """Calculate cost for token usage on Azure OpenAI.

        Note: Azure OpenAI pricing varies by region and deployment.
        This provides estimates based on Azure OpenAI pricing.
        """
        # Cost estimates based on Azure OpenAI pricing (as of 2024)
        model_lower = model.lower()

        if "gpt-4.1" in model_lower:
            # GPT-4.1 pricing from working implementation
            input_cost_per_1k = 0.02
            output_cost_per_1k = 0.005
        elif "gpt-4o" in model_lower:
            # GPT-4o pricing from working implementation
            input_cost_per_1k = 0.025
            output_cost_per_1k = 0.0125
        elif "gpt-4" in model_lower:
            # Standard GPT-4 pricing
            input_cost_per_1k = 0.03
            output_cost_per_1k = 0.06
        elif "gpt-3.5" in model_lower:
            # GPT-3.5 pricing
            input_cost_per_1k = 0.0015
            output_cost_per_1k = 0.002
        else:
            # Default to GPT-4 pricing for unknown models
            input_cost_per_1k = 0.03
            output_cost_per_1k = 0.06

        input_cost = (input_tokens / 1000) * input_cost_per_1k
        output_cost = (output_tokens / 1000) * output_cost_per_1k

        return input_cost + output_cost
