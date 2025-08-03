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

```bash
pip install -q -U google-genai
```

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

## Structured Output

### Overview
Structured output allows constraining model responses to specific JSON schemas or enums, ensuring predictable data formats.

### Implementation with Pydantic Models

```python
from google import genai
from pydantic import BaseModel, Field
import enum

class ActionType(enum.Enum):
    VOTE = "vote"
    NEW_ANSWER = "new_answer"

class VoteAction(BaseModel):
    action: ActionType = Field(default=ActionType.VOTE)
    agent_id: str = Field(description="Agent ID to vote for")
    reason: str = Field(description="Reason for voting")

class CoordinationResponse(BaseModel):
    action_type: ActionType
    vote_data: VoteAction | None = None

client = genai.Client()

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Choose the best agent and explain why.",
    config={
        "response_mime_type": "application/json",
        "response_schema": CoordinationResponse,
    }
)

# Response will be structured JSON matching the schema
```

### Enum-Only Responses

```python
class Instrument(enum.Enum):
    PERCUSSION = "Percussion"
    STRING = "String"
    WIND = "Wind"

response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents='What type of instrument is an oboe?',
    config={
        'response_mime_type': 'text/x.enum',
        'response_schema': Instrument,
    }
)
```

### Best Practices for Structured Output
- Keep schemas simple to avoid `InvalidArgument: 400` errors
- Use Pydantic models for complex JSON structures
- Add field descriptions for clarity
- Provide clear context in prompts
- Use `propertyOrdering` for consistent output order

## Builtin Tools

### Code Execution

**Overview:**
- Executes Python code within the model's runtime environment
- Maximum execution time: 30 seconds
- Can regenerate code up to 5 times if errors occur
- No additional charge beyond standard token pricing

**Supported Libraries:**
- numpy, pandas, matplotlib, scikit-learn
- Cannot install custom libraries
- Can generate Matplotlib graphs and handle file inputs (CSV, text)

**Configuration:**
```python
from google.genai import types

code_tool = types.Tool(code_execution=types.ToolCodeExecution())
config = types.GenerateContentConfig(tools=[code_tool])

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Calculate sum of first 50 prime numbers",
    config=config
)
```

**Response Format:**
- `text`: Model's explanatory text
- `executableCode`: Generated Python code  
- `codeExecutionResult`: Execution output
- Access via `response.candidates[0].content.parts`

**Limitations:**
- Python only
- Cannot return non-code artifacts
- Maximum file input ~2MB
- Some variation in performance

### Grounding (Web Search)

**Overview:**
- Provides real-time web information for factual accuracy
- Includes citations and source attribution
- Single billable use per request (even with multiple queries)

**Configuration:**
```python
from google.genai import types

grounding_tool = types.Tool(google_search=types.GoogleSearch())
config = types.GenerateContentConfig(tools=[grounding_tool])

response = client.models.generate_content(
    model="gemini-2.5-flash", 
    contents="Latest AI developments in 2025",
    config=config
)
```

**Response Metadata:**
Access via `response.candidates[0].grounding_metadata`:
- `webSearchQueries`: Search queries used
- `groundingChunks`: Web sources (URI and title)
- `groundingSupports`: Links text segments to sources

**Best Practices:**
- Process citations using `groundingSupports` and `groundingChunks`
- Use for current events and factual verification
- Review Search tool notebook for detailed examples

### URL Context (Experimental)

**Overview:**
- Process up to 20 URLs per request as additional context
- Extract and analyze content from web pages
- Currently free during experimental phase

**Capabilities:**
- Extract key data points from web pages
- Compare information across multiple URLs
- Synthesize data from multiple sources
- Answer questions based on webpage content

**Limitations:**
- Works best with standard web pages
- Not recommended for multimedia (YouTube videos)
- Daily quotas: 1500 queries per project, 100 per user
- Available on gemini-2.5-pro and gemini-2.5-flash

**Example Use Cases:**
```python
# Compare recipes from multiple URLs
"Compare recipes from URL1 and URL2"

# Extract schedule information
"Give me three day events schedule based on URL"
```

## Additional Capabilities

- **Multimodal input**: text, images, video
- **Long context support**: millions of tokens
- **Structured output generation** (see above)
- **Native image generation**
- **Embeddings** for RAG workflows
- **OpenAI-compatible interface**: Can use OpenAI Python library with `stream=True`

## Integration Notes for v3 Backend

### Key Implementation Points:
1. Use `google.generativeai` (imported as `genai`) for direct API access
2. Use `from google import genai` with `genai.Client()` for newer client patterns
3. Use `generate_content()` with `stream=True` for streaming
4. Check for `chunk.text` to ensure non-empty chunks
5. Configure structured output with `config={"response_mime_type": "application/json", "response_schema": Schema}`
6. Compatible with asyncio patterns needed for v3 architecture

### Correct Package Usage:
```python
# Correct import (google-genai package)
from google import genai

# Client-based approach (recommended)
client = genai.Client()
client.models.generate_content(...)

# Note: Old google-generativeai package is deprecated
# Use google-genai instead: pip install -q -U google-genai
```

### Authentication Setup:
- Get API key from Google AI Studio
- Set `GOOGLE_API_KEY` or `GEMINI_API_KEY` environment variable
- Use `genai.configure(api_key=api_key)` for direct API access
- Handle authentication errors appropriately

### Error Handling:
- Implement robust error handling for API failures
- Handle rate limits and quota exceeded scenarios
- Manage streaming connection failures gracefully
- Handle `InvalidArgument: 400` errors for complex schemas

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

**✅ COMPLETED**: GeminiBackend class implemented with:
- [x] Google Gemini API integration with proper authentication
- [x] Structured output for coordination (vote/new_answer) using JSON schemas
- [x] Streaming functionality compatible with v3 StreamChunk architecture
- [x] Cost calculation for Gemini 2.5 models (Flash, Flash-Lite, Pro)
- [x] Error handling for Gemini-specific responses and API limitations
- [x] Support for builtin tools (code_execution + grounding/web search)
- [x] Integration with SingleAgent and orchestrator patterns
- [x] Tool result detection and streaming for code execution and web search
- [x] CLI and configuration support with AgentConfig.create_gemini_config()
- [x] NO Live API support (uses regular API only)

**Key Features:**
- **Structured Output**: Uses `response_mime_type: "application/json"` with Pydantic schemas for coordination
- **Builtin Tools**: Supports code_execution and google_search_retrieval with proper result detection
- **Multi-mode Support**: Handles coordination-only, tools-only, and mixed scenarios
- **Cost Tracking**: Tracks token usage, search count, and code execution count
- **MassGen Compatible**: Full integration with v3 orchestrator and agent patterns

**Usage Examples:**
```python
# CLI usage
python -m massgen.v3.cli --backend gemini --model gemini-2.5-flash "Your question"

# Configuration
AgentConfig.create_gemini_config(
    model="gemini-2.5-flash",
    enable_web_search=True,
    enable_code_execution=True
)
```