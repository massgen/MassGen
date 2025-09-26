# OpenAI Responses API Tool Call Format Documentation

## Key Points for MassGen Framework

### Tool Call Format (Model Output)
```json
{
    "type": "function_call",
    "id": "fc_12345xyz",
    "call_id": "call_12345xyz",
    "name": "get_weather",
    "arguments": "{\"location\":\"Paris, France\"}"
}
```

### Tool Result Format (Input to Model)
```json
{
    "type": "function_call_output",
    "call_id": "call_12345xyz",
    "output": "Temperature is 15°C"
}
```

## Critical Flow for Multi-Turn Conversations

When handling tool calls across multiple turns:

1. **Model makes tool call** - Returns function_call object with call_id
2. **Execute function** - Run your code with the arguments
3. **Add BOTH messages to input array**:
   ```python
   input_messages.append(tool_call)  # append model's function call message
   input_messages.append({           # append result message
       "type": "function_call_output",
       "call_id": tool_call.call_id,
       "output": str(result)
   })
   ```
4. **Call model again** with complete conversation history

## Key Requirements

- **Tool result messages MUST reference the exact call_id from the original tool call**
- **Both the tool call AND tool result must be in the conversation history**
- **Tool results use "output" field, not "content"**
- **Arguments are JSON strings, not objects**

## Error Handling Pattern

For error messages to tools, follow the same pattern:
```python
# Agent made invalid tool call with call_id "call_123"
error_message = {
    "type": "function_call_output",
    "call_id": "call_123",
    "output": "Error: You can only vote once per response. Please vote for just ONE agent."
}

# Add both the original tool call AND error message to conversation
input_messages.append(original_tool_call)
input_messages.append(error_message)
```

This ensures the API can match the tool result to the original call.