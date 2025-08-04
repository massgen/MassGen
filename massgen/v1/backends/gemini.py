import os
import threading
import time
import json

try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    # Create dummy classes to prevent import errors
    class genai:
        @staticmethod
        def configure(**kwargs):
            raise ImportError("Google genai package not installed. Install with: pip install google-genai")
    
    class types:
        pass
from dotenv import load_dotenv
import copy

load_dotenv()

# Import utility functions and tools
from massgen.v1.utils import function_to_json, execute_function_calls, generate_random_id
from massgen.v1.types import AgentResponse

def add_citations_to_response(response):
    text = response.text
    
    # Check if grounding_metadata exists
    if not hasattr(response, 'candidates') or not response.candidates:
        return text
    
    candidate = response.candidates[0]
    if not hasattr(candidate, 'grounding_metadata') or not candidate.grounding_metadata:
        return text
    
    grounding_metadata = candidate.grounding_metadata
    
    # Check if grounding_supports and grounding_chunks exist and are not None
    supports = getattr(grounding_metadata, 'grounding_supports', None)
    chunks = getattr(grounding_metadata, 'grounding_chunks', None)
    
    if not supports or not chunks:
        return text

    # Sort supports by end_index in descending order to avoid shifting issues when inserting.
    sorted_supports = sorted(supports, key=lambda s: s.segment.end_index, reverse=True)

    for support in sorted_supports:
        end_index = support.segment.end_index
        if support.grounding_chunk_indices:
            # Create citation string like [1](link1)[2](link2)
            citation_links = []
            for i in support.grounding_chunk_indices:
                if i < len(chunks):
                    uri = chunks[i].web.uri
                    citation_links.append(f"[{i + 1}]({uri})")

            citation_string = ", ".join(citation_links)
            text = text[:end_index] + citation_string + text[end_index:]

    return text

def parse_completion(completion, add_citations=True):
    """Parse the completion response from Gemini API using the official SDK."""
    text = ""
    code = []
    citations = []
    function_calls = []
    reasoning_items = []

    # Handle response from the official SDK
    # Always parse candidates.content.parts for complete information
    # even if completion.text is available, as it may be incomplete
    if hasattr(completion, 'candidates') and completion.candidates:
        candidate = completion.candidates[0]
        if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
            for part in candidate.content.parts:
                # Handle text parts
                if hasattr(part, 'text') and part.text:
                    text += part.text
                # Handle executable code parts
                elif hasattr(part, 'executable_code') and part.executable_code:
                    if hasattr(part.executable_code, 'code') and part.executable_code.code:
                        code.append(part.executable_code.code)
                    elif hasattr(part.executable_code, 'language') and hasattr(part.executable_code, 'code'):
                        # Alternative format for executable code
                        code.append(part.executable_code.code)
                # Handle code execution results
                elif hasattr(part, 'code_execution_result') and part.code_execution_result:
                    if hasattr(part.code_execution_result, 'output') and part.code_execution_result.output:
                        # Add execution result as text output
                        text += f"\n[Code Output]\n{part.code_execution_result.output}\n"
                # Handle function calls
                elif hasattr(part, 'function_call'):
                    if part.function_call:
                        # Extract function name and arguments
                        func_name = getattr(part.function_call, 'name', 'unknown')
                        func_args = {}
                        call_id = getattr(part.function_call, 'id', generate_random_id())
                        if hasattr(part.function_call, 'args') and part.function_call.args:
                            # Convert args to dict if it's a struct/object
                            if hasattr(part.function_call.args, '_pb'):
                                # It's a protobuf struct, need to convert to dict
                                import json
                                try:
                                    func_args = dict(part.function_call.args)
                                except:
                                    func_args = {}
                            else:
                                func_args = part.function_call.args

                        function_calls.append({
                            "type": "function_call",
                            "call_id": call_id,
                            "name": func_name,
                            "arguments": func_args
                        })
                # Handle function responses
                elif hasattr(part, 'function_response'):
                    # Function responses are typically handled in multi-turn scenarios
                    pass

    # Handle grounding metadata (citations from search)
    if hasattr(completion, 'candidates') and completion.candidates:
        candidate = completion.candidates[0]
        if hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata:
            grounding = candidate.grounding_metadata
            if hasattr(grounding, 'grounding_chunks') and grounding.grounding_chunks:
                for chunk in grounding.grounding_chunks:
                    if hasattr(chunk, 'web') and chunk.web:
                        web_chunk = chunk.web
                        citation = {
                            "url": getattr(web_chunk, 'uri', ''),
                            "title": getattr(web_chunk, 'title', ''),
                            "start_index": -1,  # Not available in grounding metadata
                            "end_index": -1,    # Not available in grounding metadata
                        }
                        citations.append(citation)

            # Handle search entry point (if available)
            if hasattr(grounding, 'search_entry_point') and grounding.search_entry_point:
                entry_point = grounding.search_entry_point
                if hasattr(entry_point, 'rendered_content') and entry_point.rendered_content:
                    # Add search summary to citations if available
                    pass

    # Add citations to text if available and requested
    if add_citations:
        try:
            text = add_citations_to_response(completion)
        except Exception as e:
            print(f"[GEMINI] Error adding citations to text: {e}")

    return AgentResponse(
        text=text,
        code=code,
        citations=citations,
        function_calls=function_calls
    )

def process_message(messages, 
                    model="gemini-2.5-flash", 
                    tools=None, 
                    max_retries=10, 
                    max_tokens=None, 
                    temperature=None, 
                    top_p=None, 
                    api_key=None, 
                    stream=False, 
                    stream_callback=None):
    """
    Generate content using Gemini API with the official google.genai SDK.

    Args:
        messages: List of messages in OpenAI format
        model: The Gemini model to use
        tools: List of tools to use
        max_retries: Maximum number of retry attempts
        max_tokens: Maximum number of tokens in response
        temperature: Temperature for generation
        top_p: Top-p value for generation
        api_key: Gemini API key (if None, will get from environment)
        stream: Whether to stream the response (default: False)
        stream_callback: Function to call with each chunk when streaming (default: None)

    Returns:
        dict: {"text": text, "code": code, "citations": citations, "function_calls": function_calls}
    """

    """Internal function that contains all the processing logic."""
    # Get the API key
    if api_key is None:
        api_key_val = os.getenv("GEMINI_API_KEY")
    else:
        api_key_val = api_key

    if not api_key_val:
        raise ValueError("GEMINI_API_KEY not found in environment variables")

    # Set the API key for the client
    client = genai.Client(api_key=api_key_val)

    # Convert messages from OpenAI format to Gemini format
    gemini_messages = []
    system_instruction = None
    function_calls = {}
    
    for message in messages:
        role = message.get("role", None)
        content = message.get("content", None)

        if role == "system":
            system_instruction = content
        elif role == "user":
            gemini_messages.append(types.Content(role="user", parts=[types.Part(text=content)]))
        elif role == "assistant":
            gemini_messages.append(types.Content(role="model", parts=[types.Part(text=content)]))
        elif message.get("type", None) == "function_call":
            function_calls[message["call_id"]] = message
        elif message.get("type", None) == "function_call_output":
            func_name = function_calls[message["call_id"]]["name"]
            func_resp = message["output"]
            function_response_part = types.Part.from_function_response(
                name=func_name,
                response={"result": func_resp}
            )
            # Append the function response
            gemini_messages.append(types.Content(role="user", parts=[function_response_part])) 
        
    # Set up generation config
    generation_config = {}
    if temperature is not None:
        generation_config["temperature"] = temperature
    if top_p is not None:
        generation_config["top_p"] = top_p
    if max_tokens is not None:
        generation_config["max_output_tokens"] = max_tokens

    # Set up tools - separate native tools from custom functions
    # due to Gemini API limitation: can't combine native tools with custom functions
    gemini_tools = []
    has_native_tools = False
    custom_functions = []
    
    if tools:
        for tool in tools:
            if "live_search" == tool:
                gemini_tools.append(types.Tool(google_search=types.GoogleSearch()))
                has_native_tools = True
            elif "code_execution" == tool:
                gemini_tools.append(types.Tool(code_execution=types.ToolCodeExecution()))
                has_native_tools = True
            else:
                # Collect custom function declarations
                # Old format: {"type": "function", "function": {...}}
                if hasattr(tool, 'function'): 
                    function_declaration = tool["function"]
                else: # New OpenAI format: {"type": "function", "name": ..., "description": ...}
                    function_declaration = copy.deepcopy(tool)
                    if "type" in function_declaration:
                        del function_declaration["type"]
                custom_functions.append(function_declaration)
    
    if custom_functions and has_native_tools:
        print(f"[WARNING] Gemini API doesn't support combining native tools with custom functions. Prioritizing built-in tools.")
    elif custom_functions and not has_native_tools:
        # add custom functions to the tools
        gemini_tools.append(types.Tool(function_declarations=custom_functions))
    
    # Set up safety settings
    safety_settings = [
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
            threshold=types.HarmBlockThreshold.BLOCK_NONE
        ),
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
            threshold=types.HarmBlockThreshold.BLOCK_NONE
        ),
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
            threshold=types.HarmBlockThreshold.BLOCK_NONE
        ),
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
            threshold=types.HarmBlockThreshold.BLOCK_NONE
        ),
    ]

    # Prepare the request parameters
    request_params = {
        "model": model,
        "contents": gemini_messages,
        "config": types.GenerateContentConfig(
            safety_settings=safety_settings,
            **generation_config
        )
    }
            
    if system_instruction:
        request_params["config"].system_instruction = types.Content(
            parts=[types.Part(text=system_instruction)]
        )

    if gemini_tools:
        request_params["config"].tools = gemini_tools
    
    # Make API request with retry logic
    completion = None
    retry = 0
    while retry < max_retries:
        try:
            if stream and stream_callback:
                # Handle streaming response
                text = ""
                code = []
                citations = []
                function_calls = []  # Initialize function_calls list
                
                # Code streaming tracking
                code_lines_shown = 0
                current_code_chunk = ""
                truncation_message_sent = False  # Track if truncation message was sent

                stream_response = client.models.generate_content_stream(**request_params)
                
                for chunk in stream_response:
                    # Handle text chunks - be very careful to avoid duplication
                    chunk_text_processed = False
                    
                    # First, try to get text from the most direct source
                    if hasattr(chunk, 'text') and chunk.text:
                        chunk_text = chunk.text
                        text += chunk_text
                        try:
                            stream_callback(chunk_text)
                            chunk_text_processed = True
                        except Exception as e:
                            print(f"Stream callback error: {e}")
                    
                    # Only process candidates if we haven't already processed text from chunk.text
                    elif hasattr(chunk, 'candidates') and chunk.candidates:
                        candidate = chunk.candidates[0]
                        if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                            for part in candidate.content.parts:
                                if hasattr(part, 'text') and part.text and not chunk_text_processed:
                                    chunk_text = part.text
                                    text += chunk_text
                                    try:
                                        stream_callback(chunk_text)
                                        chunk_text_processed = True  # Mark as processed to avoid further processing
                                    except Exception as e:
                                        print(f"Stream callback error: {e}")
                                elif hasattr(part, 'executable_code') and part.executable_code and hasattr(part.executable_code, 'code') and part.executable_code.code:
                                    # Handle code execution streaming
                                    code_text = part.executable_code.code
                                    code.append(code_text)
                                    
                                    # Apply similar code streaming logic as in oai.py
                                    code_lines = code_text.split('\n')
                                    
                                    if code_lines_shown == 0:
                                        try:
                                            stream_callback("\n💻 Starting code execution...\n")
                                        except Exception as e:
                                            print(f"Stream callback error: {e}")
                                    
                                    for line in code_lines:
                                        if code_lines_shown < 3:
                                            try:
                                                stream_callback(line + '\n')
                                                code_lines_shown += 1
                                            except Exception as e:
                                                print(f"Stream callback error: {e}")
                                        elif code_lines_shown == 3 and not truncation_message_sent:
                                            try:
                                                stream_callback('\n[CODE_DISPLAY_ONLY]\n💻 ... (full code in log file)\n')
                                                truncation_message_sent = True  # Ensure this message is only sent once
                                                code_lines_shown += 1
                                            except Exception as e:
                                                print(f"Stream callback error: {e}")
                                        else:
                                            try:
                                                stream_callback(f"[CODE_LOG_ONLY]{line}\n")
                                            except Exception as e:
                                                print(f"Stream callback error: {e}")
                                
                                elif hasattr(part, 'function_call') and part.function_call:
                                    # Handle function calls - extract the actual function call data
                                    func_name = getattr(part.function_call, 'name', 'unknown')
                                    func_args = {}
                                    if hasattr(part.function_call, 'args') and part.function_call.args:
                                        # Convert args to dict if it's a struct/object
                                        if hasattr(part.function_call.args, '_pb'):
                                            # It's a protobuf struct, need to convert to dict
                                            import json
                                            try:
                                                func_args = dict(part.function_call.args)
                                            except:
                                                func_args = {}
                                        else:
                                            func_args = part.function_call.args

                                    function_calls.append({
                                        "type": "function_call",
                                        "call_id": part.function_call.id,
                                        "name": func_name,
                                        "arguments": func_args
                                    })
                                    
                                    try:
                                        stream_callback(f"\n🔧 Calling {func_name}\n")
                                    except Exception as e:
                                        print(f"Stream callback error: {e}")
                                
                                elif hasattr(part, 'function_response'):
                                    try:
                                        stream_callback("\n🔧 Function response received\n")
                                    except Exception as e:
                                        print(f"Stream callback error: {e}")
                                
                                elif hasattr(part, 'code_execution_result') and part.code_execution_result:
                                    if hasattr(part.code_execution_result, 'output') and part.code_execution_result.output:
                                        # Add execution result as text output
                                        result_text = f"\n[Code Output]\n{part.code_execution_result.output}\n"
                                        text += result_text
                                        try:
                                            stream_callback(result_text)
                                        except Exception as e:
                                            print(f"Stream callback error: {e}")

                        # Handle grounding metadata (citations from search) at the candidate level
                        if hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata:
                            grounding = candidate.grounding_metadata
                            if hasattr(grounding, 'grounding_chunks') and grounding.grounding_chunks:
                                for chunk_item in grounding.grounding_chunks:
                                    if hasattr(chunk_item, 'web') and chunk_item.web:
                                        web_chunk = chunk_item.web
                                        citation = {
                                            "url": getattr(web_chunk, 'uri', ''),
                                            "title": getattr(web_chunk, 'title', ''),
                                            "start_index": -1,  # Not available in grounding metadata
                                            "end_index": -1,    # Not available in grounding metadata
                                        }
                                        # Avoid duplicate citations
                                        if citation not in citations:
                                            citations.append(citation)

                # Handle completion
                try:
                    stream_callback("\n✅ Generation finished\n")
                except Exception as e:
                    print(f"Stream callback error: {e}")

                return AgentResponse(
                    text=text,
                    code=code,
                    citations=citations,
                    function_calls=function_calls  # Return the captured function calls
                )
            else:
                # Handle non-streaming response
                completion = client.models.generate_content(**request_params)
            break
        except Exception as e:
            print(f"Error on attempt {retry + 1}: {e}")
            retry += 1
            time.sleep(1.5)

    if completion is None:
        # If we failed all retries, return empty response instead of raising exception
        print(f"Failed to get completion after {max_retries} retries, returning empty response")
        return AgentResponse(text="", code=[], citations=[], function_calls=[])

    # Parse the completion and return text, code, and citations
    result = parse_completion(completion, add_citations=True)
    return result

# Example usage (you can remove this if not needed)
if __name__ == "__main__":
    pass