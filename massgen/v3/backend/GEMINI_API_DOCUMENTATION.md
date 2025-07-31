# Gemini API Documentation for Backend Integration

## Overview

The Gemini API provides access to Google's latest generative AI models with multimodal capabilities, streaming support, and function calling.

## Authentication

- Requires API key from Google AI Studio
- Set up authentication in Python client

## Models Available

1. **Gemini 2.5 Pro**: Most powerful thinking model with features for complex reasoning
2. **Gemini 2.5 Flash**: Newest multimodal model with next generation features  
3. **Gemini 2.5 Flash-Lite**: Lighter version

**Note**: Starting April 29, 2025, Gemini 1.5 Pro and Gemini 1.5 Flash models are not available in projects with no prior usage.

## Python SDK Installation & Basic Usage

```python
from google import genai

client = genai.Client()

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Explain how AI works in a few words",
)

print(response.text)
```

## Streaming Implementation

### Synchronous Streaming
```python
for chunk in client.models.generate_content_stream(
    model='gemini-2.0-flash', 
    contents='Tell me a story in 300 words.'
):
    print(chunk.text)
    print("_" * 80)
```

### Asynchronous Streaming
```python
async for chunk in await client.aio.models.generate_content_stream(
    model='gemini-2.0-flash', 
    contents="Write a cute story about cats."
):
    if chunk.text:
        print(chunk.text)
        print("_" * 80)
```

### Async Concurrent Execution
```python
async def get_response():
    async for chunk in await client.aio.models.generate_content_stream(
        model='gemini-2.0-flash',
        contents='Tell me a story in 500 words.'
    ):
        if chunk.text:
            print(chunk.text)
            print("_" * 80)

async def something_else():
    for i in range(5):
        print("==========not blocked!==========")
        await asyncio.sleep(1)

async def async_demo():
    task1 = asyncio.create_task(get_response())
    task2 = asyncio.create_task(something_else())
    await asyncio.gather(task1, task2)
```

## Function Calling

### Overview
- Allows models to interact with external tools and APIs
- Three primary use cases:
  1. Augment Knowledge
  2. Extend Capabilities  
  3. Take Actions

### Function Call Workflow
1. Define function declarations with:
   - Name
   - Description
   - Parameters (type, properties)

2. Call model with function declarations
3. Model decides whether to:
   - Generate text response
   - Call specified function(s)

### Function Call Modes
- **AUTO** (default): Flexible response
- **ANY**: Force function call
- **NONE**: Prohibit function calls

### Supported Capabilities
- Parallel function calling
- Compositional (sequential) function calling
- Automatic function calling (Python SDK)

### Best Practices
- Provide clear, specific function descriptions
- Use strong typing for parameters
- Limit total number of tools (10-20 recommended)
- Implement robust error handling
- Be mindful of security and token limits

### Supported Models for Function Calling
- Gemini 2.5 Pro
- Gemini 2.5 Flash
- Gemini 2.5 Flash-Lite

## Additional Capabilities

- **Multimodal input**: text, images, video
- **Long context support**: millions of tokens
- **Structured output generation**
- **Native image generation**
- **Embeddings** for RAG workflows
- **OpenAI-compatible interface**: Can use OpenAI Python library with `stream=True`

## Integration Notes for v3 Backend

### Key Implementation Points:
1. Use `generate_content_stream()` for synchronous streaming
2. Use `aio.models.generate_content_stream()` for asynchronous streaming  
3. Check for `chunk.text` to ensure non-empty chunks
4. Supports both immediate and background processing
5. Compatible with asyncio patterns needed for v3 architecture

### Authentication Setup:
- Get API key from Google AI Studio
- Initialize client with proper credentials
- Handle authentication errors appropriately

### Error Handling:
- Implement robust error handling for API failures
- Handle rate limits and quota exceeded scenarios
- Manage streaming connection failures gracefully

### Pricing and Rate Limits:
- Pricing details: https://ai.google.dev/pricing
- Rate limits: https://ai.google.dev/gemini-api/docs/rate-limits
- Monitor usage and implement cost controls

## Tool Usage Restrictions & Multi-Tool Support

### Regular Gemini API (Stable)
**✅ Supported Combinations:**
- `code_execution` + `grounding` (includes search) - **RECOMMENDED**
- `function_declarations` only (user-defined tools)

**❌ NOT Supported:**
- `code_execution` + `function_declarations` 
- `grounding` + `function_declarations`
- All three tool types together

### Live API (Preview/Experimental) 
**✅ Multi-Tool Support:**
- Can combine `google_search` + `code_execution` + `function_declarations`
- Full flexibility but comes with major limitations

**🚨 Live API Restrictions (NOT Recommended for MassGen v3):**
- **Status**: Preview/experimental - unstable for production
- **Session Limits**: 3 free, 50-1000 paid (too restrictive)
- **Real-time focus**: WebSocket-based, designed for audio/video
- **Cost**: 50% premium over regular API
- **Availability**: Not guaranteed, capacity varies
- **Complexity**: Requires WebSocket implementation

### Recommendation for MassGen v3 Backend
**✅ Use Regular API with `code_execution + grounding`:**
- Stable, production-ready
- Covers both code execution and web search needs
- Standard REST endpoints
- Predictable pricing and limits
- No session restrictions

**❌ Avoid Live API:**
- Session limits incompatible with multi-agent scaling
- Preview status unsuitable for production
- Unnecessary complexity for text-based coordination

## Implementation Status for MassGen v3

**TODO**: Implement GeminiBackend class with:
- [ ] Google Gemini API integration with proper authentication
- [ ] Tool message conversion for Gemini format (code_execution + grounding)
- [ ] Streaming functionality compatible with v3 StreamChunk architecture
- [ ] Cost calculation for Gemini models
- [ ] Error handling for Gemini-specific responses
- [ ] Support for builtin tools (code_execution + grounding) 
- [ ] Integration with SingleAgent and orchestrator patterns
- [ ] NO Live API support (use regular API only)

This backend was available in v0.0.1 but needs to be ported to v3 architecture.