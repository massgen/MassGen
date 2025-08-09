# Reasoning Streaming Implementation Notes

## Overview
Based on analysis of the MassGen codebase, here are key insights about how reasoning streaming works, particularly for OpenAI GPT-5 series and O-series models.

## Key Implementation Details

### OpenAI Backend Configuration
- **Reasoning Parameter**: `reasoning.effort` can be set to "low", "medium", or "high" 
- **Orthogonality**: Reasoning, web search, and code execution are orthogonal capabilities and can be adjusted independently
- **Model Support**: GPT-5 series (gpt-5, gpt-5-mini, gpt-5-nano) and GPT O-series models
- **Response Format**: When reasoning is enabled, the model provides structured reasoning traces
- **Summary Control**: `reasoning.summary` can be set to "auto", "concise", or "detailed" for reasoning summaries (if omitted, no reasoning summaries are provided)

### Configuration Examples
```yaml
backend:
  type: "openai"
  model: "gpt-5-nano"
  reasoning:
    effort: "medium"  # Options: low, medium, high
    summary: "auto"   # Options: auto, concise, detailed (omit for no summaries)
  enable_web_search: true    # Can be enabled with reasoning
  enable_code_execution: true # Can be enabled with reasoning
```

### Multi-Agent Reasoning Scenarios
In the case studies examined:
- **Agent 1**: `reasoning.effort: "minimal"` - Basic safety-focused approaches
- **Agent 2**: `reasoning.effort: "medium"` - Structured comprehensive frameworks  
- **Agent 3**: `reasoning.effort: "high"` - Advanced systematic analysis

### Reasoning Quality Progression
Higher reasoning effort levels consistently produce:
- More sophisticated analysis and synthesis
- Better integration of multiple dimensions (technical, philosophical, societal)
- Enhanced strategic thinking and implementation frameworks
- Superior consensus-building through cross-agent evaluation

### Stream Processing
The MassGen implementation handles reasoning traces through:
- **Event Types**: `response.reasoning_text.delta`, `response.reasoning_text.done`, `response.reasoning_summary_text.delta`, `response.reasoning_summary_text.done`
- **StreamChunk Integration**: Reasoning content is converted to standardized StreamChunk format
- **Progressive Display**: Real-time streaming of reasoning deltas with consistent formatting prefixes
- **Frontend Support**: Both coordination UI and final presentation display reasoning with consistent formatting

### Implementation Architecture
- **Backend (response.py)**: Handles OpenAI reasoning stream events and converts to StreamChunk format
- **Orchestrator**: Passes through reasoning chunks with source attribution
- **Frontend**: Displays reasoning content with `📋 [Reasoning Summary]` prefixes
- **Shared Logic**: BaseDisplay.process_reasoning_content() provides consistent formatting prefixes

## Implementation Status
✅ **Complete**: Full end-to-end reasoning streaming support
- OpenAI GPT-5 reasoning events properly handled
- Reasoning summary prefixes display correctly in both coordination and final presentation
- No artificial constraints between reasoning, web search, and code execution
- Clean, shared codebase without duplication

## Future Enhancements
- Support for other providers' reasoning capabilities (Claude's thinking, Gemini's reasoning)
- Configurable reasoning display modes (full traces vs. summaries)
- Reasoning quality metrics and evaluation frameworks