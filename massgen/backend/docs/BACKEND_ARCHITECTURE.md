# Backend Architecture: Stateful vs Stateless

## Overview

The MassGen backend system supports two distinct architectural patterns for AI model backends: stateless and stateful. Understanding these patterns is crucial for proper agent implementation and state management.

## Backend Types

### Stateless Backends

**Examples:** `ChatCompletionBackend`, OpenAI GPT models, Gemini

**Characteristics:**
- No conversation state maintained between requests
- Each request is independent and self-contained
- Complete context must be provided with every request
- No memory of previous interactions
- Simpler to scale horizontally

**Implementation Pattern:**
```python
# Each request includes full conversation history
# NOTE: Documentation uses .generate() for clarity, actual code uses .stream_with_tools()
response = backend.generate(
    messages=[
        {"role": "user", "content": "Previous context..."},
        {"role": "assistant", "content": "Previous response..."},
        {"role": "user", "content": "Current request..."}
    ]
)
```

### Stateful Backends

**Examples:** `Claude Code CLI`, Interactive CLI sessions

**Characteristics:**
- Maintains conversation context across interactions
- State persists between requests
- Can reference previous interactions without resending context
- Requires explicit state management (reset, clear, etc.)
- More complex but efficient for long conversations

**Implementation Pattern:**
```python
# Only current request needed, context maintained internally
# NOTE: Documentation uses .generate() for clarity, actual code uses .stream_with_tools()
response = backend.generate(message="Current request...")
```

## Current Agent Implementation Issue

The current agent implementation assumes all backends are **stateless**, which creates inefficiencies and potential issues:

### Problems with Current Approach:
1. **Redundant Context**: Sends complete conversation history to stateful backends
2. **Inefficient Resource Usage**: Wastes bandwidth and processing power
3. **State Confusion**: May conflict with backend's internal state management
4. **Reset Handling**: Doesn't properly clear stateful backend state on reset

## Recommended Solution

### 1. Backend Detection
Add capability detection to identify backend type:

```python
class Backend:
    @property
    def is_stateful(self) -> bool:
        """Returns True if backend maintains conversation state"""
        return False  # Default to stateless
```

### 2. Conditional Context Management
Adjust message sending based on backend type:

```python
def send_message(self, message: str):
    if self.backend.is_stateful:
        # Send only current message
        # NOTE: Documentation uses .generate() for clarity, actual code uses .stream_with_tools()
        response = self.backend.generate(message)
    else:
        # Send full conversation history
        # NOTE: Documentation uses .generate() for clarity, actual code uses .stream_with_tools()
        response = self.backend.generate(self.get_full_context())
```

### 3. Reset Handling
Handle resets differently for each backend type:

```python
# NOTE: Methods shown are conceptual examples, not current implementation
def reset_conversation(self):
    if self.backend.is_stateful:
        # Clear backend's internal state
        self.backend.reset()
    else:
        # Clear local conversation history
        self.conversation_history.clear()
```

## Implementation Files

- `base.py` - Base backend interface with `LLMBackend` abstract class
- `chat_completions.py` - Stateless ChatCompletion backends (OpenAI-compatible)
- `claude_code.py` - **Stateful** Claude Code backend with streaming support
- `cli_base.py` - Base CLI backend functionality

## Benefits of Proper Implementation

1. **Performance**: Reduced context transmission for stateful backends
2. **Reliability**: Proper state management prevents confusion
3. **Scalability**: Optimized resource usage
4. **Consistency**: Uniform behavior across backend types
5. **Maintainability**: Clear separation of concerns

## Next Steps

1. Add `is_stateful` property to backend interface
2. Update agent logic to detect and handle backend types
3. Implement proper reset mechanisms for both types
4. Add tests for both stateful and stateless scenarios
5. Update documentation for backend developers

TODO: Clean up the design - StreamChunk has grown complex with many optional fields for different reasoning types and provider-specific features