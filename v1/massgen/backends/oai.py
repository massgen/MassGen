import os
import threading
import time
import json
import copy

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI

# Import utility functions
from massgen.utils import function_to_json, execute_function_calls
from massgen.types import AgentResponse

            
def parse_completion(response, add_citations=True):
    """Parse the completion response from OpenAI API.

    Mainly three types of output in the response:
    - reasoning (no summary provided): ResponseReasoningItem(id='rs_6876b0d566d08198ab9f992e1911bd0a02ec808107751c1f', summary=[], type='reasoning', status=None)
    - web_search_call (actions: search, open_page, find_in_page): ResponseFunctionWebSearch(id='ws_6876b0e3b83081988d6cddd9770357c402ec808107751c1f', status='completed', type='web_search_call', action={'type': 'search', 'query': 'Economy of China Wikipedia GDP table'})
    - message: response output (including text and citations, optional)
    - code_interpreter_call (code provided): code output
    - function_call: function call, arguments, and name provided
    """
    text = ""
    code = []
    citations = []
    function_calls = []
    reasoning_items = []

    # Process the response output
    for r in response.output:
        if r.type == "message":  # Final response, including text and citations (optional)
            for c in r.content:
                text += c.text
                if add_citations and hasattr(c, "annotations") and c.annotations:
                    for annotation in c.annotations:
                        citations.append(
                            {
                                "url": annotation.url,
                                "title": annotation.title,
                                "start_index": annotation.start_index,
                                "end_index": annotation.end_index,
                            }
                        )
        elif r.type == "code_interpreter_call":
            code.append(r.code)
        elif r.type == "web_search_call":
            # detailed web search actions: search, open_page, find_in_page, etc
            pass
        elif r.type == "reasoning":
            reasoning_items.append({"type": "reasoning", "id": r.id, "summary": r.summary})
        elif r.type == "function_call":
            # tool output - include call_id for Responses API
            function_calls.append({
                "type": "function_call",
                "name": r.name, 
                "arguments": r.arguments,
                "call_id": getattr(r, "call_id", None),
                "id": getattr(r, "id", None)
            })

    # Add citations to text if available
    if add_citations and citations:
        try:
            new_text = text
            # Sort citations by end_index in descending order to avoid shifting issues when inserting
            sorted_citations = sorted(citations, key=lambda c: c["end_index"], reverse=True)

            for idx, citation in enumerate(sorted_citations):
                end_index = citation["end_index"]
                citation_link = f"[{len(citations) - idx}]({citation['url']})"
                new_text = new_text[:end_index] + citation_link + new_text[end_index:]
            text = new_text
        except Exception as e:
            print(f"[OAI] Error adding citations to text: {e}")
                    
    return AgentResponse(
        text=text,
        code=code,
        citations=citations,
        function_calls=function_calls
    )

def process_message(messages, 
                    model="gpt-4.1-mini", 
                    tools=None, 
                    max_retries=10, 
                    max_tokens=None, 
                    temperature=None, 
                    top_p=None, 
                    api_key=None, 
                    stream=False, stream_callback=None):
    """
    Generate content using OpenAI API with optional streaming support.

    Args:
        messages: List of messages in OpenAI format
        model: The OpenAI model to use
        tools: List of tools to use
        max_retries: Maximum number of retry attempts
        max_tokens: Maximum number of tokens in response
        temperature: Temperature for generation
        top_p: Top-p value for generation
        api_key: OpenAI API key (if None, will get from environment)
        stream: Whether to stream the response (default: False)
        stream_callback: Optional callback function for streaming chunks

    Returns:
        dict: {"text": text, "code": code, "citations": citations, "function_calls": function_calls}
    """

    """Internal function that contains all the processing logic."""
    # Get the API key
    if api_key is None:
        api_key_val = os.getenv("OPENAI_API_KEY")
    else:
        api_key_val = api_key

    if not api_key_val:
        raise ValueError("OPENAI_API_KEY not found in environment variables")

    # Create OpenAI client without individual timeouts
    client = OpenAI(api_key=api_key_val)

    # All models can use the same Responses API - no need to distinguish

    # Prepare tools (Responses API format - same for all models)
    formatted_tools = []

    # Add other custom tools
    if tools:
        for tool in tools:
            if isinstance(tool, dict):
                formatted_tools.append(tool)
            elif callable(tool):
                formatted_tools.append(function_to_json(tool))
            elif tool == "live_search":  # built-in tools
                formatted_tools.append({"type": "web_search_preview"})
            elif tool == "code_execution":  # built-in tools
                formatted_tools.append({"type": "code_interpreter", "container": {"type": "auto"}})
            else:
                raise ValueError(f"Invalid tool type: {type(tool)}")
                
    # Convert messages to the format expected by OpenAI responses API
    # For now, we'll use the last user message as input
    input_text = []
    instructions = ""
    for message in messages:
        if message.get("role", "") == "system":
            instructions = message["content"]
        else:
            # Clean the function calls' id to avoid the requirements of related reasoning items
            if message.get("type", "") == "function_call" and message.get("id", None) is not None:
                del message["id"]
            input_text.append(message)
            
    # Make API request with retry logic (use Responses API for all models)
    completion = None
    retry = 0
    while retry < max_retries:
        try:
            # Create a local copy of model to avoid scoping issues
            model_name = model
            
            # Use responses API for all models (supports streaming)
            # Note: Response models doesn't support temperature parameter
            params = {
                "model": model_name,
                "tools": formatted_tools if formatted_tools else None,
                "instructions": instructions if instructions else None,
                "input": input_text,
                "max_output_tokens": max_tokens if max_tokens else None,
                "stream": True if stream and stream_callback else False,
            }
            
            # CRITICAL: Include code interpreter outputs for streaming
            # Without this, code execution results (stdout/stderr) won't be available
            if formatted_tools and any(tool.get("type") == "code_interpreter" for tool in formatted_tools):
                params["include"] = ["code_interpreter_call.outputs"]

            # Only add temperature and top_p for models that support them
            # All o-series models (o1, o3, o4, etc.) don't support temperature/top_p
            if temperature is not None and not model_name.startswith("o"):
                params["temperature"] = temperature
            if top_p is not None and not model_name.startswith("o"):
                params["top_p"] = top_p
            if model_name.startswith("o"):
                if model_name.endswith("-low"):
                    params["reasoning"] = {"effort": "low"}
                    model_name = model_name.replace("-low", "")
                elif model_name.endswith("-medium"):
                    params["reasoning"] = {"effort": "medium"}
                    model_name = model_name.replace("-medium", "")
                elif model_name.endswith("-high"):
                    params["reasoning"] = {"effort": "high"}
                    model_name = model_name.replace("-high", "")
                else:
                    params["reasoning"] = {"effort": "low"}
            params["model"] = model_name
            
            # Inference        
            response = client.responses.create(**params)
            completion = response
            break
        except Exception as e:
            print(f"Error on attempt {retry + 1}: {e}")
            retry += 1
            import time  # Local import to ensure availability in threading context
            time.sleep(1.5)

    if completion is None:
        # If we failed all retries, return empty response instead of raising exception
        print(f"Failed to get completion after {max_retries} retries, returning empty response")
        return AgentResponse(text="", code=[], citations=[], function_calls=[])

    # Handle Responses API response (same for all models)
    if stream and stream_callback:
        # Handle streaming response
        text = ""
        code = []
        citations = []
        function_calls = []
        
        # Code streaming tracking
        code_lines_shown = 0
        current_code_chunk = ""
        truncation_message_sent = False
        
        # Function call arguments streaming tracking
        current_function_call = None
        current_function_arguments = ""

        for chunk in completion:
            # Handle different event types from responses API streaming
            if hasattr(chunk, "type"):                       
                if chunk.type == "response.output_text.delta":
                    # This is a text delta event
                    if hasattr(chunk, "delta") and chunk.delta:
                        chunk_text = chunk.delta
                        text += chunk_text
                        try:
                            stream_callback(chunk_text)
                        except Exception as e:
                            print(f"Stream callback error: {e}")
                elif chunk.type == "response.function_call_output.delta":
                    # Function call streaming
                    try:
                        stream_callback(f"\n🔧 {chunk.delta if hasattr(chunk, 'delta') else 'Function call'}\n")
                    except Exception as e:
                        print(f"Stream callback error: {e}")
                elif chunk.type == "response.function_call_output.done":
                    # Function call completed
                    try:
                        stream_callback("\n🔧 Function call completed\n")
                    except Exception as e:
                        print(f"Stream callback error: {e}")
                elif chunk.type == "response.code_interpreter_call.in_progress":
                    # Code interpreter call started
                    # Reset code streaming tracking for new code block
                    code_lines_shown = 0
                    current_code_chunk = ""
                    truncation_message_sent = False
                    try:
                        stream_callback("\n💻 Starting code execution...\n")
                    except Exception as e:
                        print(f"Stream callback error: {e}")
                elif chunk.type == "response.code_interpreter_call_code.delta":
                    # Code being written/streamed
                    if hasattr(chunk, 'delta') and chunk.delta:
                        try:
                            # Add to current code chunk for tracking
                            current_code_chunk += chunk.delta
                            
                            # Count lines in this delta
                            new_lines = chunk.delta.count('\n')
                            
                            if code_lines_shown < 3:
                                # Still within first 3 lines - send normally for display & logging
                                stream_callback(chunk.delta)
                                code_lines_shown += new_lines
                                
                                # Check if we just exceeded 3 lines with this chunk
                                if code_lines_shown >= 3 and not truncation_message_sent:
                                    # Send truncation message for display only (not logging)
                                    stream_callback('\n[CODE_DISPLAY_ONLY]\n💻 ... (full code in log file)\n')
                                    truncation_message_sent = True
                            else:
                                # Beyond 3 lines - send with special prefix for logging only
                                # The workflow can detect this prefix and log but not display
                                stream_callback(f"[CODE_LOG_ONLY]{chunk.delta}")
                                        
                        except Exception as e:
                            print(f"Stream callback error: {e}")
                elif chunk.type == "response.code_interpreter_call_code.done":
                    # Code writing completed - capture the code
                    if current_code_chunk:
                        code.append(current_code_chunk)
                    try:
                        stream_callback("\n💻 Code writing completed\n")
                    except Exception as e:
                        print(f"Stream callback error: {e}")
                elif chunk.type == "response.code_interpreter_call_execution.in_progress":
                    # Code execution started
                    try:
                        stream_callback("\n💻 Executing code...\n")
                    except Exception as e:
                        print(f"Stream callback error: {e}")
                elif chunk.type == "response.code_interpreter_call_execution.done":
                    # Code execution completed
                    try:
                        stream_callback("\n💻 Code execution completed\n")
                    except Exception as e:
                        print(f"Stream callback error: {e}")
                elif chunk.type == "response.output_item.added":
                    # New output item added
                    if hasattr(chunk, "item") and chunk.item:
                        if hasattr(chunk.item, "type") and chunk.item.type == "web_search_call":
                            try:
                                stream_callback("\n🔍 Starting web search...\n")
                            except Exception as e:
                                print(f"Stream callback error: {e}")
                        elif hasattr(chunk.item, "type") and chunk.item.type == "reasoning":
                            try:
                                stream_callback("\n🧠 Reasoning in progress...\n")
                            except Exception as e:
                                print(f"Stream callback error: {e}")
                        elif hasattr(chunk.item, "type") and chunk.item.type == "code_interpreter_call":
                            try:
                                stream_callback("\n💻 Code interpreter starting...\n")
                            except Exception as e:
                                print(f"Stream callback error: {e}")
                        elif hasattr(chunk.item, "type") and chunk.item.type == "function_call":
                            # Function call started - create initial function call object
                            function_call_data = {
                                "type": "function_call",
                                "name": getattr(chunk.item, "name", None),
                                "arguments": getattr(chunk.item, "arguments", None),
                                "call_id": getattr(chunk.item, "call_id", None),
                                "id": getattr(chunk.item, "id", None)
                            }
                            function_calls.append(function_call_data)
                            current_function_call = function_call_data
                            current_function_arguments = ""
                            
                            # Notify function call started
                            function_name = function_call_data.get("name", "unknown")
                            try:
                                stream_callback(f"\n🔧 Calling function '{function_name}'...\n")
                            except Exception as e:
                                print(f"Stream callback error: {e}")
                elif chunk.type == "response.output_item.done":
                    # Check if this is a completed web search with query or reasoning completion
                    if hasattr(chunk, "item") and chunk.item:
                        if hasattr(chunk.item, "type") and chunk.item.type == "web_search_call":
                            if hasattr(chunk.item, "action") and hasattr(chunk.item.action, "query"):
                                search_query = chunk.item.action.query
                                if search_query:
                                    try:
                                        stream_callback(f"\n🔍 Completed search for: {search_query}\n")
                                    except Exception as e:
                                        print(f"Stream callback error: {e}")
                        elif hasattr(chunk.item, "type") and chunk.item.type == "reasoning":
                            try:
                                stream_callback("\n🧠 Reasoning completed\n")
                            except Exception as e:
                                print(f"Stream callback error: {e}")
                        elif hasattr(chunk.item, "type") and chunk.item.type == "code_interpreter_call":
                            # CRITICAL: Capture code execution outputs (stdout/stderr)
                            # This is the actual result of running the code
                            if hasattr(chunk.item, "outputs") and chunk.item.outputs:
                                for output in chunk.item.outputs:
                                    # Check if it's a dict-like object with a 'type' key (most common)
                                    if hasattr(output, 'get') and output.get("type") == "logs":
                                        logs_content = output.get("logs")
                                        if logs_content:
                                            # Add execution result to text output
                                            execution_result = f"\n[Code Execution Output]\n{logs_content}\n"
                                            text += execution_result
                                            try:
                                                stream_callback(execution_result)
                                            except Exception as e:
                                                print(f"Stream callback error: {e}")
                                    # Also check for attribute-based access (fallback)
                                    elif hasattr(output, "type") and output.type == "logs":
                                        if hasattr(output, "logs") and output.logs:
                                            # Add execution result to text output
                                            execution_result = f"\n[Code Execution Output]\n{output.logs}\n"
                                            text += execution_result
                                            try:
                                                stream_callback(execution_result)
                                            except Exception as e:
                                                print(f"Stream callback error: {e}")
                            try:
                                stream_callback("\n💻 Code interpreter completed\n")
                            except Exception as e:
                                print(f"Stream callback error: {e}")
                        elif hasattr(chunk.item, "type") and chunk.item.type == "function_call":
                            # Function call completed - update the function call data if needed
                            if hasattr(chunk.item, "arguments"):
                                # Find and update the corresponding function call
                                for fc in function_calls:
                                    if fc.get("id") == getattr(chunk.item, "id", None):
                                        fc["arguments"] = chunk.item.arguments
                                        break
                            
                            # Also update with accumulated arguments if available
                            if current_function_call and current_function_arguments:
                                current_function_call["arguments"] = current_function_arguments
                            
                            # Reset tracking
                            current_function_call = None
                            current_function_arguments = ""
                            
                            # Notify function call completed
                            function_name = getattr(chunk.item, "name", "unknown")
                            try:
                                stream_callback(f"\n🔧 Function '{function_name}' completed\n")
                            except Exception as e:
                                print(f"Stream callback error: {e}")
                elif chunk.type == "response.web_search_call.in_progress":
                    try:
                        stream_callback("\n🔍 Search in progress...\n")
                    except Exception as e:
                        print(f"Stream callback error: {e}")
                elif chunk.type == "response.web_search_call.searching":
                    try:
                        stream_callback("\n🔍 Searching...\n")
                    except Exception as e:
                        print(f"Stream callback error: {e}")
                elif chunk.type == "response.web_search_call.completed":
                    try:
                        stream_callback("\n🔍 Search completed\n")
                    except Exception as e:
                        print(f"Stream callback error: {e}")
                elif chunk.type == "response.output_text.annotation.added":
                    # Citation added - capture citation information
                    if hasattr(chunk, "annotation"):
                        citation_data = {
                            "url": getattr(chunk.annotation, "url", None),
                            "title": getattr(chunk.annotation, "title", None),
                            "start_index": getattr(chunk.annotation, "start_index", None),
                            "end_index": getattr(chunk.annotation, "end_index", None),
                        }
                        citations.append(citation_data)
                    try:
                        stream_callback("\n📚 Citation added\n")
                    except Exception as e:
                        print(f"Stream callback error: {e}")
                elif chunk.type == "response.function_call_arguments.delta":
                    # Handle function call arguments streaming
                    if hasattr(chunk, "delta") and chunk.delta:
                        current_function_arguments += chunk.delta
                        try:
                            # Stream the function arguments as they're generated
                            stream_callback(chunk.delta)
                        except Exception as e:
                            print(f"Stream callback error: {e}")
                elif chunk.type == "response.function_call_arguments.done":
                    # Function arguments completed - update the function call
                    if hasattr(chunk, "arguments") and hasattr(chunk, "item_id"):
                        # Find and update the corresponding function call
                        for fc in function_calls:
                            if fc.get("id") == chunk.item_id:
                                fc["arguments"] = chunk.arguments
                                break
                    
                    # Also update with accumulated arguments if available
                    if current_function_call and current_function_arguments:
                        current_function_call["arguments"] = current_function_arguments
                    
                    # Reset tracking
                    current_function_call = None
                    current_function_arguments = ""
                    
                    try:
                        stream_callback("\n🔧 Function arguments complete\n")
                    except Exception as e:
                        print(f"Stream callback error: {e}")
                elif chunk.type == "response.completed":
                    try:
                        stream_callback("\n✅ Response complete\n")
                    except Exception as e:
                        print(f"Stream callback error: {e}")
                   
        result = AgentResponse(
            text=text,
            code=code,
            citations=citations,
            function_calls=function_calls
        )
    else:
        # Parse non-streaming response using existing parse_completion function
        result = parse_completion(completion, add_citations=True)
        
    return result

# Example usage (you can remove this if not needed)
if __name__ == "__main__":
    pass