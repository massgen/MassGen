# Claude API Research for MassGen Backend

## API Status & Availability (2025)

✅ **Production Ready**: Claude API is stable and production-ready  
✅ **Active Development**: Regular updates with new features in 2025  
✅ **Strong SDK Support**: Official Python SDK with async/sync support  

## Models Available (2025)

- **Claude 4 Opus**: Most capable, hybrid with extended thinking mode
- **Claude 4 Sonnet**: Balanced performance, also available to free users  
- **Claude 3.7 Sonnet**: Previous generation, still supported
- **Claude 3.5 Haiku**: Fastest, cost-effective option

## Tool Use Capabilities

### ✅ Excellent Multi-Tool Support
**Key Advantage**: Claude can combine ALL tool types in a single request:
- ✅ **Server-side tools** (web search, code execution) 
- ✅ **User-defined functions** (custom tools)
- ✅ **File processing** via Files API
- ✅ **No restrictions** on combining different tool types

### Tool Types Supported

#### 1. Server-Side Tools (Builtin)
**Web Search Tool:**
- Real-time web access with citations
- Progressive/chained searches supported
- Pricing: $10 per 1,000 searches
- Enable with tool definition in API request

**Code Execution Tool:**
- Python code execution in secure sandbox **server-side**
- 1 GiB RAM, 5 GiB storage, 1-hour sessions
- File upload support (CSV, Excel, JSON, images)
- Data analysis, visualization, calculations
- Pricing: $0.05 per session-hour (5 min minimum)
- **IMPORTANT**: Claude executes code server-side and streams results back
- **Execution results streamed** as additional content blocks
- **Tool type**: `code_execution_20250522` (requires beta headers)
- **Beta header required**: `"anthropic-beta": "code-execution-2025-05-22"`
- **Models supporting code execution**: Claude 3.5 Sonnet and above (NOT Haiku)

#### 2. Client-Side Tools (User-Defined)
- Custom function definitions with JSON schemas
- Parallel tool execution supported
- Chained/sequential tool calls
- No limitations on combining with server-side tools

## Streaming Support

### ✅ Advanced Streaming Capabilities
- **Basic streaming**: Real-time response generation
- **Tool use streaming**: Fine-grained streaming of tool parameters
- **Async support**: Full async/await patterns
- **SDK integration**: Built-in streaming helpers and accumulation

### Streaming with Tools
```python
# Fine-grained tool streaming (beta) - REQUIRES BETA CLIENT
stream = client.beta.messages.create(
    model="claude-3-5-sonnet-20241022",
    messages=[{"role": "user", "content": "Search and analyze..."}],
    tools=[
        {"type": "web_search_20250305"},
        {"type": "code_execution_20250522"}
    ],
    headers={"anthropic-beta": "code-execution-2025-05-22"},
    stream=True
)

for event in stream:
    if event.type == "content_block_delta":
        # Stream tool input parameters incrementally
        print(event.delta)
    elif event.delta.type == "input_json_delta":
        # Stream tool arguments as JSON fragments
        print(event.delta.partial_json)
```

## Authentication & Setup

```python
# Simple setup
import anthropic

client = anthropic.Anthropic(
    api_key="your-api-key"  # or use ANTHROPIC_API_KEY env var
)

# Async client
async_client = anthropic.AsyncAnthropic()

# IMPORTANT: For code execution, use the beta client
beta_client = anthropic.AsyncAnthropic()
response = await beta_client.beta.messages.create(
    model="claude-3-5-sonnet-20241022",
    tools=[{"type": "code_execution_20250522"}],
    headers={"anthropic-beta": "code-execution-2025-05-22"},
    messages=[...]
)
```

## Pricing Model

- **Token-based pricing**: Input/output tokens
- **Additional costs**:
  - Web search: $10 per 1,000 searches
  - Code execution: $0.05 per session-hour
- **No session limits**: Unlike Gemini Live API
- **Predictable scaling**: Standard REST API

## Advanced Features (2025)

### New Beta Features  
- **Code execution**: Python sandbox with server-side execution
  - Header: `"anthropic-beta": "code-execution-2025-05-22"`
  - Tool type: `code_execution_20250522`
- **Interleaved thinking**: Claude can think between tool calls
  - Header: `"anthropic-beta": "interleaved-thinking-2025-05-14"`
- **Fine-grained tool streaming**: Stream tool parameters without buffering
- **MCP Connector**: Connect to remote MCP servers from Messages API

### Extended Thinking Mode
- Available in Claude 4 models
- Can use tools during extended reasoning
- Alternates between thinking and tool use

## Architecture Compatibility with MassGen

### ✅ Perfect Fit for v3 Requirements

**Multi-Tool Support:**
- ✅ Can combine web search + code execution + user functions
- ✅ No API limitations like Gemini
- ✅ Parallel and sequential tool execution

**Streaming Architecture:**
- ✅ Compatible with StreamChunk pattern
- ✅ Real-time tool parameter streaming
- ✅ Async generator support

**Production Readiness:**
- ✅ Stable API with predictable pricing
- ✅ No session limits or experimental restrictions  
- ✅ Strong error handling and rate limits

## Implementation Recommendation

### ✅ HIGH PRIORITY: Implement Claude Backend

**Advantages for MassGen:**
1. **No tool restrictions** - can use all tool types together
2. **Production stable** - no experimental limitations
3. **Advanced streaming** - perfect for real-time coordination
4. **Strong Python SDK** - easy integration
5. **Competitive pricing** - especially for multi-agent use cases

**Implementation Priority:**
- **Higher than Gemini** - no API limitations
- **Complement to OpenAI/Grok** - provides third major backend option
- **Clean architecture** - no workarounds needed

### Suggested Implementation Order:
1. ✅ OpenAI Backend (completed)
2. ✅ Grok Backend (completed) 
3. 🎯 **Claude Backend** (recommended next)
4. ⏳ Gemini Backend (when API supports multi-tools)

## Sample Integration

```python
class ClaudeBackend(LLMBackend):
    def __init__(self, api_key: Optional[str] = None):
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
    
    async def stream_with_tools(self, messages, tools, **kwargs):
        # Can freely combine all tool types
        combined_tools = []
        
        # Add server-side tools  
        if kwargs.get("enable_web_search"):
            combined_tools.append({"type": "web_search_20250305"})
        
        if kwargs.get("enable_code_execution"):
            combined_tools.append({"type": "code_execution_20250522"})
        
        # Add user-defined tools
        if tools:
            combined_tools.extend(tools)
        
        # Single API call with all tools - USE BETA CLIENT FOR CODE EXECUTION
        headers = {}
        if kwargs.get("enable_code_execution"):
            headers["anthropic-beta"] = "code-execution-2025-05-22"
            
        stream = await self.client.beta.messages.create(
            model="claude-3-5-sonnet-20241022",
            messages=messages,
            tools=combined_tools,
            headers=headers,
            stream=True
        )
        
        async for event in stream:
            yield StreamChunk(...)
```

## Key Implementation Requirements

### ✅ CRITICAL: Code Execution Setup
- **Use beta client**: `client.beta.messages.create()` NOT `client.messages.create()`
- **Beta header required**: `"anthropic-beta": "code-execution-2025-05-22"`
- **Correct tool type**: `code_execution_20250522` NOT `bash_20250124`
- **Model requirement**: Claude 3.5 Sonnet or above (Haiku does NOT support code execution)

### ✅ Tool Execution Pattern
Claude's code execution is **server-side** - Claude executes the code and streams results back:
1. Send request with `code_execution_20250522` tool
2. Claude generates code and executes it server-side  
3. Claude streams back execution results automatically
4. No client-side tool execution needed for code execution tools

### ✅ Streaming Event Types to Handle
- `content_block_start`: Tool use begins
- `content_block_delta`: Tool input streaming  
- `input_json_delta`: Tool arguments as JSON fragments
- Tool execution results are streamed as additional content blocks

### ✅ VERIFIED: Code Execution Streaming Flow
Based on successful test with `claude-3-5-haiku-latest`:

**Event Sequence:**
1. `message_start` - Stream begins
2. `content_block_start` -> `text` - Initial explanation text
3. `content_block_delta` -> `text_delta` - Text streaming (multiple events)
4. `content_block_stop` - Text block ends
5. `content_block_start` -> `server_tool_use` - Code execution tool begins
6. `content_block_delta` -> `input_json_delta` - **Python code streams in JSON fragments**
7. `content_block_stop` - Tool input complete
8. `content_block_start` -> `code_execution_tool_result` - **Server-side execution results**
9. `content_block_stop` - Tool result complete
10. `content_block_start` -> `text` - Analysis text
11. `content_block_delta` -> `text_delta` - Final analysis streaming
12. `content_block_stop` - Analysis complete
13. `message_stop` - Stream ends

**Key Implementation Details:**
- **Model**: `claude-3-5-haiku-latest` supports code execution
- **Beta setup**: `betas=["code-execution-2025-05-22"]` (not `extra_headers`)
- **Tool type**: `code_execution_20250522` with `name: "code_execution"`
- **Real-time code**: Events 27-47 show code streaming as JSON fragments
- **Server execution**: Claude executes code and streams results automatically
- **No client execution needed**: Unlike bash tools, code execution is server-side

## Conclusion

**Claude API is the ideal candidate for MassGen's next backend implementation** due to its:
- Complete multi-tool support without restrictions
- Production-ready stability and pricing
- Advanced streaming capabilities with server-side code execution
- Perfect alignment with v3 architecture requirements

Unlike Gemini's API limitations, Claude provides the flexibility we need without compromising the architecture.