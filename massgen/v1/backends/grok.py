# -*- coding: utf-8 -*-
import json
import os

from dotenv import load_dotenv
from xai_sdk import Client
from xai_sdk.chat import assistant, system
from xai_sdk.chat import tool as xai_tool_func
from xai_sdk.chat import tool_result, user
from xai_sdk.search import SearchParameters

# Import utility functions and tools
from massgen.v1.types import AgentResponse

load_dotenv()


def parse_completion(response, add_citations=True):
    """Parse the completion response from Grok API."""
    text = response.content
    code = []
    citations = []
    function_calls = []

    if hasattr(response, "citations") and response.citations:
        for citation in response.citations:
            citations.append({"url": citation, "title": "", "start_index": -1, "end_index": -1})

    if citations and add_citations:
        citation_content = []
        for idx, citation in enumerate(citations):
            citation_content.append(f"[{idx}]({citation['url']})")
        text = text + "\n\nReferences:\n" + "\n".join(citation_content)

    # Check if response has tool_calls directly (some SDK formats)
    if hasattr(response, "tool_calls") and response.tool_calls:
        for tool_call in response.tool_calls:
            if hasattr(tool_call, "function"):
                # OpenAI-style structure: tool_call.function.name, tool_call.function.arguments
                function_calls.append(
                    {
                        "type": "function_call",
                        "call_id": tool_call.id,
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                )
            elif hasattr(tool_call, "name") and hasattr(tool_call, "arguments"):
                # Direct structure: tool_call.name, tool_call.arguments
                function_calls.append(
                    {
                        "type": "function_call",
                        "call_id": tool_call.id,
                        "name": tool_call.name,
                        "arguments": tool_call.arguments,
                    },
                )

    return AgentResponse(text=text, code=code, citations=citations, function_calls=function_calls)


def process_message(
    messages,
    model="grok-3-mini",
    tools=None,
    max_retries=10,
    max_tokens=None,
    temperature=None,
    top_p=None,
    api_key=None,
    stream=False,
    stream_callback=None,
):
    """
    Generate content using Grok API with optional streaming support and custom tools.

    Args:
        messages: List of message dictionaries with 'role' and 'content' keys
        model: Model name to use (default: "grok-4")
        tools: List of tool definitions for function calling, each tool should be a dict with OpenAI-compatible format:
               [
                   {
                       "type": "function",
                       "function": {
                           "name": "function_name",
                           "description": "Function description",
                           "parameters": {
                               "type": "object",
                               "properties": {
                                   "param1": {"type": "string", "description": "Parameter description"},
                                   "param2": {"type": "number", "description": "Another parameter"}
                               },
                               "required": ["param1"]
                           }
                       }
                   }
               ]
        enable_search: Boolean to enable live search functionality (default: False)
        max_retries: Maximum number of retry attempts (default: 10)
        max_tokens: Maximum tokens in response (default: 32000)
        temperature: Sampling temperature (default: None)
        top_p: Top-p sampling parameter (default: None)
        api_key: XAI API key (default: None, uses environment variable)
        stream: Enable streaming response (default: False)
        stream_callback: Callback function for streaming (default: None)

    Returns:
        Dict with keys: 'text', 'code', 'citations', 'function_calls'

    Note:
        - For backward compatibility, tools=["live_search"] is still supported and will enable search
        - Function calls will be returned in the 'function_calls' key as a list of dicts with 'name' and 'arguments'
        - The 'arguments' field will contain the function arguments as returned by the model
    """

    """Internal function that contains all the processing logic."""
    if api_key is None:
        api_key_val = os.getenv("XAI_API_KEY")
    else:
        api_key_val = api_key

    if not api_key_val:
        raise ValueError("XAI_API_KEY not found in environment variables")

    client = Client(api_key=api_key_val)

    # Handle backward compatibility for old tools=["live_search"] format
    enable_search = False
    custom_tools = []

    if tools and isinstance(tools, list) and len(tools) > 0:
        for tool in tools:
            if tool == "live_search":
                enable_search = True
            elif isinstance(tool, str):
                # Skip unexpected strings to avoid API errors
                continue
            else:
                # This should be a proper tool object
                custom_tools.append(tool)

    # Handle search parameters
    search_parameters = None
    if enable_search:
        search_parameters = SearchParameters(
            mode="auto",
            return_citations=True,
        )

    # Prepare tools for the API call
    api_tools = None
    if custom_tools and isinstance(custom_tools, list) and len(custom_tools) > 0:
        # Convert OpenAI format tools to X.AI SDK format for the API call
        api_tools = []
        for custom_tool in custom_tools:
            if isinstance(custom_tool, dict) and custom_tool.get("type") == "function":
                # Check if it's the OpenAI nested format or the direct format from function_to_json
                if "function" in custom_tool:
                    # OpenAI format: {"type": "function", "function": {...}}
                    func_def = custom_tool["function"]
                else:
                    # Older format: {"type": "function", "name": ..., "description": ...}
                    func_def = custom_tool

                xai_tool = xai_tool_func(
                    name=func_def["name"],
                    description=func_def["description"],
                    parameters=func_def["parameters"],
                )
                api_tools.append(xai_tool)
            else:
                # If it's already in X.AI format, use as-is
                api_tools.append(custom_tool)

    def make_grok_request(stream=False):
        # Build chat creation parameters
        chat_params = {
            "model": model,
            "search_parameters": search_parameters,
        }

        # Add optional parameters only if they have values
        if temperature is not None:
            chat_params["temperature"] = temperature
        if top_p is not None:
            chat_params["top_p"] = top_p
        if max_tokens is not None:
            chat_params["max_tokens"] = max_tokens
        if api_tools is not None:
            chat_params["tools"] = api_tools

        chat = client.chat.create(**chat_params)

        for message in messages:
            role = message.get("role", None)
            content = message.get("content", None)

            if role == "system":
                chat.append(system(content))
            elif role == "user":
                chat.append(user(content))
            elif role == "assistant":
                chat.append(assistant(content))
            elif message.get("type", None) == "function_call":
                pass
            elif message.get("type", None) == "function_call_output":
                content = message.get("output", None)
                chat.append(tool_result(content))

        if stream:
            return chat.stream()
        else:
            return chat.sample()

    completion = None
    retry = 0
    while retry < max_retries:
        try:
            is_streaming = stream and stream_callback is not None
            completion = make_grok_request(stream=is_streaming)
            break
        except Exception as e:
            print(f"Error on attempt {retry + 1}: {e}")
            retry += 1
            import time  # Local import to ensure availability in threading context

            time.sleep(1.5)

    if completion is None:
        print(f"Failed to get completion after {max_retries} retries, returning empty response")
        return AgentResponse(text="", code=[], citations=[], function_calls=[])

    if stream and stream_callback is not None:
        text = ""
        code = []
        citations = []
        function_calls = []
        thinking_count = 0
        has_shown_search_indicator = False

        try:
            has_delta_content = False
            for response, chunk in completion:
                # Handle XAI SDK streaming format: (response, chunk)
                # The XAI SDK follows OpenAI-like streaming format
                delta_content = None

                # Extract delta content from chunk - XAI SDK specific format
                # Primary method: check for choices structure and extract content directly
                if hasattr(chunk, "choices") and chunk.choices and len(chunk.choices) > 0:
                    choice = chunk.choices[0]
                    # XAI SDK stores content directly in choice.content, not choice.delta.content
                    if hasattr(choice, "content") and choice.content:
                        delta_content = choice.content

                # Fallback method: direct content attribute on chunk
                elif hasattr(chunk, "content") and chunk.content:
                    delta_content = chunk.content

                # Additional fallback: text attribute
                elif hasattr(chunk, "text") and chunk.text:
                    delta_content = chunk.text

                if delta_content:
                    has_delta_content = True
                    # Check if this is a "Thinking..." chunk (indicates processing/search)
                    if delta_content.strip() == "Thinking...":
                        thinking_count += 1
                        # Show search indicator after first few thinking chunks
                        if thinking_count == 3 and not has_shown_search_indicator and search_parameters:
                            try:
                                stream_callback("\n🧠 Thinking...\n")
                            except Exception as e:
                                print(f"Stream callback error: {e}")
                            has_shown_search_indicator = True

                        # Stream the "Thinking..." to user but don't add to final text
                        try:
                            stream_callback(delta_content)
                        except Exception as e:
                            print(f"Stream callback error: {e}")
                    else:
                        # This is actual content - add to text and stream
                        text += delta_content
                        try:
                            stream_callback(delta_content)
                        except Exception as e:
                            print(f"Stream callback error: {e}")

                # Check for function calls in streaming response
                if hasattr(response, "tool_calls") and response.tool_calls:
                    for tool_call in response.tool_calls:
                        if hasattr(tool_call, "function"):
                            _func_call = {
                                "type": "function_call",
                                "call_id": tool_call.id,
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments,
                            }
                            if _func_call not in function_calls:
                                function_calls.append(_func_call)
                        elif hasattr(tool_call, "name") and hasattr(tool_call, "arguments"):
                            _func_call = {
                                "type": "function_call",
                                "call_id": tool_call.id,
                                "name": tool_call.name,
                                "arguments": tool_call.arguments,
                            }
                            if _func_call not in function_calls:
                                function_calls.append(_func_call)
                elif hasattr(response, "choices") and response.choices:
                    for choice in response.choices:
                        if hasattr(choice, "message") and hasattr(choice.message, "tool_calls") and choice.message.tool_calls:
                            for tool_call in choice.message.tool_calls:
                                if hasattr(tool_call, "function"):
                                    _func_call = {
                                        "type": "function_call",
                                        "call_id": tool_call.id,
                                        "name": tool_call.function.name,
                                        "arguments": tool_call.function.arguments,
                                    }
                                    if _func_call not in function_calls:
                                        function_calls.append(_func_call)
                                elif hasattr(tool_call, "name") and hasattr(tool_call, "arguments"):
                                    _func_call = {
                                        "type": "function_call",
                                        "call_id": tool_call.id,
                                        "name": tool_call.name,
                                        "arguments": tool_call.arguments,
                                    }
                                    if _func_call not in function_calls:
                                        function_calls.append(_func_call)

                # Check if this is the final chunk with citations
                if hasattr(response, "citations") and response.citations:
                    citations = []
                    for citation in response.citations:
                        citations.append(
                            {
                                "url": citation,
                                "title": "",
                                "start_index": -1,
                                "end_index": -1,
                            },
                        )

                    # Notify about found sources if we had search enabled
                    if citations and enable_search and stream_callback is not None:
                        try:
                            stream_callback(f"\n\n🔍 Found {len(citations)} web sources\n")
                        except Exception as e:
                            print(f"Stream callback error: {e}")

            # Streaming the complete text response at the end if the above streaming fails
            if not has_delta_content:
                if text:
                    stream_callback(text)
                if function_calls:
                    for function_call in function_calls:
                        stream_callback(f"🔧 Calling function: {function_call['name']}\n")
                        stream_callback(f"🔧 Arguments: {json.dumps(function_call['arguments'], indent=4)}\n\n")

        except Exception:
            # Fall back to non-streaming
            completion = make_grok_request(stream=False)
            result = parse_completion(completion, add_citations=True)
            return result

        result = AgentResponse(text=text, code=code, citations=citations, function_calls=function_calls)
    else:
        result = parse_completion(completion, add_citations=True)

    return result


if __name__ == "__main__":
    pass
