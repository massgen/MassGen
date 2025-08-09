# Multi-Turn Conversation Design for MassGen Orchestrator

## Overview

This document outlines the design approach for implementing multi-turn conversations in the MassGen orchestrator, based on the proven approach used in MassGen v0.0.1.

## V0.0.1 Approach Analysis

### Key Innovation: Dynamic Context Reconstruction

V0.0.1 implements multi-turn conversations through **dynamic message reconstruction** rather than persistent conversation state:

```python
def work_on_task(self, task: TaskInput) -> List[Dict[str, str]]:
    # Initialize working messages
    working_status, working_messages, all_tools = self._get_curr_messages_and_tools(task)
    
    while curr_round < self.max_rounds and self.state.status == "working":
        # Process messages...
        
        # When agents need to restart due to updates:
        if renew_conversation:
            # Rebuild conversation with latest context
            working_status, working_messages, all_tools = self._get_curr_messages_and_tools(task)
```

### Core Principles

1. **Dynamic Context Generation**: Agents don't maintain persistent conversations - they regenerate context each time they restart
2. **Fresh State on Updates**: When other agents provide new answers, the conversation context is rebuilt with latest information
3. **Multi-layered Context**: Conversations include:
   - System instructions
   - Original task/question  
   - Current answers from all agents
   - Voting information (when applicable)

### Context Reconstruction Method

```python
def _get_curr_messages_and_tools(self, task: TaskInput):
    """Get the current messages and tools for the agent."""
    working_status, user_input = self._get_task_input(task)  # Includes latest agent answers
    working_messages = self._get_task_input_messages(user_input)  # System + user messages
    all_tools = self._get_available_tools()  # Current tool set
    return working_status, working_messages, all_tools
```

## Proposed Implementation

### 1. Orchestrator-Level Conversation Management

```python
class Orchestrator:
    def __init__(self, ...):
        self.conversation_history: List[Dict[str, Any]] = []  # User conversation
        self.current_coordination_context: Optional[str] = None
    
    async def chat(self, messages: List[Dict[str, Any]], ...):
        # Extract full conversation context
        conversation_context = self._build_conversation_context(messages)
        
        # Start coordination with full context
        async for chunk in self._coordinate_agents(conversation_context):
            yield chunk
```

### 2. Context-Aware Agent Coordination

```python
async def _coordinate_agents(self, conversation_context: Dict[str, Any]):
    """Coordinate agents with full conversation context."""
    
    # Build enriched task context including:
    # - Original conversation history  
    # - Current user message
    # - Existing agent answers (if any)
    
    for agent_id in self.agents:
        # Each agent gets full context when starting/restarting
        agent_context = self._build_agent_context(
            conversation_history=conversation_context['history'],
            current_task=conversation_context['current_message'], 
            agent_answers=self._get_current_answers(),
            voting_state=self._get_voting_state()
        )
        
        # Agent processes with full context
        await self._stream_agent_execution(agent_id, agent_context)
```

### 3. Dynamic Context Rebuilding

```python
def _build_agent_context(self, conversation_history, current_task, agent_answers, voting_state):
    """Build agent context dynamically based on current state."""
    
    # Format conversation history for agent context
    history_context = self._format_conversation_history(conversation_history)
    
    # Format current coordination state
    coordination_context = self.message_templates.build_coordination_context(
        current_task=current_task,
        conversation_history=history_context,
        agent_answers=agent_answers,
        voting_state=voting_state
    )
    
    return {
        "system_message": self.message_templates.system_message_with_context(history_context),
        "user_message": coordination_context,
        "tools": self.workflow_tools
    }
```

### 4. Message Template Updates

```python
class MessageTemplates:
    def build_coordination_context(self, current_task, conversation_history, agent_answers, voting_state):
        """Build coordination context including conversation history."""
        
        context_parts = []
        
        # Add conversation history if present
        if conversation_history:
            context_parts.append(f"""
<CONVERSATION_HISTORY>
{self._format_conversation_for_agent(conversation_history)}
</CONVERSATION_HISTORY>
""")
        
        # Add current task
        context_parts.append(f"""
<CURRENT_MESSAGE>
{current_task}
</CURRENT_MESSAGE>
""")
        
        # Add agent answers if any exist
        if agent_answers:
            context_parts.append(f"""
<CURRENT_ANSWERS>
{self._format_agent_answers(agent_answers)}
</CURRENT_ANSWERS>
""")
        
        return "\n".join(context_parts)
```

## Implementation Benefits

### 1. **True Multi-Turn Support**
- Agents understand full conversation context, not just current message
- Natural conversation flow maintained across coordination rounds
- Context-aware responses that reference previous exchanges

### 2. **Dynamic State Management**
- Agents always work with latest information from all sources
- No stale conversation state issues
- Clean restart mechanism when coordination state changes

### 3. **Scalable Architecture**
- Conversation history managed centrally at orchestrator level
- Agents remain stateless - context provided on-demand
- Easy to extend for different conversation patterns

### 4. **Backward Compatibility**
- Existing single-turn usage patterns continue to work
- Gradual migration path for CLI and frontend improvements

## Implementation Priority

This approach addresses multiple TODO items:

- **HIGH PRIORITY**: Support chat with an orchestrator (core multi-agent functionality)
- **MEDIUM PRIORITY**: Fix CLI multi-turn conversation display in multi-agent mode
- **MEDIUM PRIORITY**: Port missing features from v0.0.1

## Next Steps

1. **Phase 1**: Update message templates to support conversation context
2. **Phase 2**: Modify orchestrator coordination to pass full context to agents  
3. **Phase 3**: Update CLI to properly display coordination with conversation history
4. **Phase 4**: Add conversation management utilities and testing

## Technical Notes

### Context Size Management
- Monitor conversation history length to prevent token limit issues
- Implement conversation truncation strategies for very long histories
- Consider conversation summarization for extended sessions

### Performance Considerations
- Context rebuilding is lightweight (no persistent state management)
- Memory usage scales with conversation length, not coordination complexity
- Caching opportunities for repeated context elements

### Testing Strategy
- Unit tests for context building methods
- Integration tests for multi-turn coordination scenarios
- CLI testing with conversation history of various lengths
- Edge case testing (empty history, very long conversations, etc.)

---

*This design document is based on analysis of MassGen v0.0.1's proven multi-turn approach and adapted for the current async streaming architecture.*