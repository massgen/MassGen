# Multi-Turn LLM Input Analysis - MassGen

## Overview

This document shows the exact input structure sent to LLMs during multi-turn conversations in MassGen, demonstrating how conversation context is built and passed to agents.

## Context Building Progression

### Turn 1: Initial Question (No History)

**Context Size:** 568 characters total
- System Message: 389 chars
- User Message: 179 chars  
- Tools: 2 (new_answer, vote)

**System Message:**
```
You are evaluating answers from multiple agents for final response to a message. Does the best CURRENT ANSWER address the ORIGINAL MESSAGE?

If YES, use the `vote` tool to record your vote and skip the `new_answer` tool.
Otherwise, do additional work first, then use the `new_answer` tool to record a better answer to the ORIGINAL MESSAGE. Make sure you actually call one of the two tools.
```

**User Message Structure:**
```
<ORIGINAL MESSAGE> What are the main benefits of renewable energy? <END OF ORIGINAL MESSAGE>

<CURRENT ANSWERS from the agents>
(no answers available yet)
<END OF CURRENT ANSWERS>
```

**Key Features:**
- ❌ No conversation history section
- ✅ Original message clearly marked
- ✅ Empty current answers section
- ❌ Standard system message (no context awareness)

---

### Turn 2: Follow-up with History

**Context Size:** 1,152 characters total (+103% from Turn 1)
- System Message: 574 chars (+47%)
- User Message: 578 chars (+223%)
- Tools: 2 (same)

**System Message (Enhanced):**
```
You are evaluating answers from multiple agents for final response to a message. Does the best CURRENT ANSWER address the ORIGINAL MESSAGE?

If YES, use the `vote` tool to record your vote and skip the `new_answer` tool.
Otherwise, do additional work first, then use the `new_answer` tool to record a better answer to the ORIGINAL MESSAGE. Make sure you actually call one of the two tools.
            
IMPORTANT: You are responding to the latest message in an ongoing conversation. Consider the full conversation context when evaluating answers and providing your response.
```

**User Message Structure:**
```
<CONVERSATION_HISTORY>
User: What are the main benefits of renewable energy?
Assistant: Renewable energy offers several key benefits including environmental sustainability, economic advantages, and energy security. It reduces greenhouse gas emissions, creates jobs, and decreases dependence on fossil fuel imports.
<END OF CONVERSATION_HISTORY>

<ORIGINAL MESSAGE> What about the challenges and limitations? <END OF ORIGINAL MESSAGE>

<CURRENT ANSWERS from the agents>
<agent1> Key benefits include environmental and economic advantages. <end of agent1>
<END OF CURRENT ANSWERS>
```

**Key Features:**
- ✅ **Conversation history section** with previous exchange
- ✅ Original message (current question)
- ✅ Agent answers from coordination
- ✅ **Context-aware system message**

---

### Turn 3: Extended Conversation

**Context Size:** 1,252 characters total (+120% from Turn 1)
- System Message: 574 chars (same as Turn 2)
- User Message: 678 chars (+279% from Turn 1)
- Tools: 2 (same)

**User Message Structure:**
```
<CONVERSATION_HISTORY>
User: What are the main benefits of renewable energy?
Assistant: Renewable energy offers environmental, economic, and energy security benefits.
User: What about the challenges and limitations?
Assistant: Main challenges include high upfront costs, intermittency issues, and infrastructure requirements.
<END OF CONVERSATION_HISTORY>

<ORIGINAL MESSAGE> How can governments support the transition? <END OF ORIGINAL MESSAGE>

<CURRENT ANSWERS from the agents>
<agent2> Benefits include environmental and economic advantages. <end of agent2>
<agent1> Challenges include costs, intermittency, and infrastructure needs. <end of agent1>
<END OF CURRENT ANSWERS>
```

**Key Features:**
- ✅ **Full conversation history** (2 previous exchanges)
- ✅ Original message (current question)
- ✅ **Multiple agent answers** from coordination
- ✅ Context-aware system message
- ✅ **Progressive context building**

## Context Growth Analysis

### Size Progression
```
Turn 1: 568 chars  (baseline)
Turn 2: 1,152 chars (+103% growth)
Turn 3: 1,252 chars (+120% growth)
```

### Context Elements by Turn
| Element | Turn 1 | Turn 2 | Turn 3 |
|---------|--------|--------|--------|
| CONVERSATION_HISTORY | ❌ | ✅ (1 exchange) | ✅ (2 exchanges) |
| ORIGINAL MESSAGE | ✅ | ✅ | ✅ |
| CURRENT ANSWERS | ✅ (empty) | ✅ (1 agent) | ✅ (2 agents) |
| Context-aware system | ❌ | ✅ | ✅ |

## Key Implementation Insights

### 1. **Dynamic Context Reconstruction**
- Each turn rebuilds the complete context from scratch (v0.0.1 approach)
- No persistent conversation state in agents
- Context includes conversation history + current coordination state

### 2. **Conversation History Format**
```
<CONVERSATION_HISTORY>
User: [previous question]
Assistant: [previous response]
User: [another question]
Assistant: [another response]
<END OF CONVERSATION_HISTORY>
```

### 3. **System Message Enhancement**
- Turn 1: Standard evaluation prompt
- Turn 2+: Enhanced with context awareness note:
  ```
  IMPORTANT: You are responding to the latest message in an ongoing conversation. 
  Consider the full conversation context when evaluating answers and providing your response.
  ```

### 4. **Multi-layered Context**
Each agent receives:
1. **Conversation History**: Previous user-assistant exchanges
2. **Original Message**: Current question being coordinated
3. **Current Answers**: Existing answers from other agents in this coordination round
4. **Tools**: Standard MassGen workflow tools (vote, new_answer)

## Benefits of This Approach

### ✅ **True Multi-Turn Support**
- Agents understand full conversation context, not just current message
- Natural conversation flow maintained across coordination rounds
- Context-aware responses that reference previous exchanges

### ✅ **Scalable Context Management**
- Context size grows linearly with conversation length
- Clean separation between conversation history and coordination state
- Memory-efficient (no persistent agent state)

### ✅ **Robust State Management**
- Each coordination round starts with fresh, complete context
- No issues with stale or inconsistent conversation state
- Easy to debug and understand exactly what agents receive

## Testing and Validation

The implementation includes comprehensive tests:

1. **`test_message_context_building.py`**: Shows exact message structure without API calls
2. **`test_multiturn_llm_input.py`**: Captures actual LLM calls during coordination with debug backend
3. **`test_multiturn_conversation.py`**: End-to-end multi-turn conversation testing

Run these tests to see the exact LLM inputs and validate the context building behavior.

---

*This analysis confirms that MassGen's multi-turn conversation support properly implements the proven v0.0.1 dynamic context reconstruction approach, adapted for the current async streaming architecture.*