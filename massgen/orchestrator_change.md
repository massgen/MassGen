# Orchestrator Timeout Agent Handling Changes

## Overview
Modified the orchestrator to handle timeout agents in a way that allows active agents to consider timeout agents' answers while preventing timeout agents from participating in any coordination activities. Additionally, implemented comprehensive timeout handling for three scenarios:
1. All agents timeout - orchestrator generates comprehensive answer
2. Some agents timeout - only active agents can be selected as final presenter
3. Final presenter considers all agents' answers (including timeout agents)

## Key Changes

### 1. Answer Collection Logic Modification
- **Active answers**: Contains only non-killed agents, used for voting validation and final selection
- **Timeout answers**: Contains killed agents' answers, used for context only
- **All answers for context**: Combines both sets, passed to active agents as decision reference

```python
# Collect answers from active agents (for voting targets and final selection)
active_answers = {
    aid: state.answer
    for aid, state in self.agent_states.items()
    if state.answer and not state.is_killed
}
# Collect answers from timeout agents (for context only)
timeout_answers = {
    aid: state.answer
    for aid, state in self.agent_states.items()
    if state.answer and state.is_killed
}
# Combine for agent context (active agents can see all answers for informed decisions)
all_answers_for_context = {**active_answers, **timeout_answers}
```

### 2. Voting Validation Logic Modification
- Active agents can only vote for other active agents (`answers_for_voting`)
- Timeout agents cannot be voted for, even if they have answers
- The vote tool's `valid_agent_ids` only includes active agents

### 3. Final Agent Selection Logic Modification
- `_determine_final_agent_from_votes` only receives active agents as candidates
- Even if a timeout agent receives votes, it cannot be selected as the final presenter
- Ensures only active agents can win the coordination

```python
# TIMEOUT AGENTS EXCLUSION: Only active agents can be selected as final presenter
# This ensures that timeout agents cannot win the coordination even if they received votes
active_answers_for_selection = {
    aid: state.answer
    for aid, state in self.agent_states.items()
    if state.answer and not state.is_killed
}
```

### 4. Agent Execution Flow Modification
- `_stream_agent_execution` method now accepts two parameters:
  - `answers_for_context`: Contains all answers (active + timeout) for building conversation
  - `answers_for_voting`: Contains only active answers for voting validation
- Active agents can see timeout agents' answers but cannot vote for them

```python
async def _stream_agent_execution(
    self,
    agent_id: str,
    task: str,
    answers_for_context: Dict[str, str],
    answers_for_voting: Dict[str, str],
    conversation_context: Optional[Dict[str, Any]] = None,
) -> AsyncGenerator[tuple, None]:
```

### 5. Timeout Agent State Preservation
- Timeout agents' states remain unchanged (`is_killed=True`)
- They cannot participate in any active coordination activities
- However, their answers still provide reference value for active agents

## Design Principles

### What Active Agents CAN Do:
- ✅ Consider timeout agents' answers as reference
- ✅ Make better decisions based on all available information
- ✅ Vote for other active agents
- ✅ Be selected as the final presenter

### What Timeout Agents CANNOT Do:
- ❌ Generate new answers
- ❌ Vote for any agent
- ❌ Be voted for by any agent
- ❌ Be selected as the final presenter
- ❌ Participate in any active coordination activities

## Benefits
1. **Information Preservation**: Timeout agents' partial work is not wasted
2. **Better Decision Making**: Active agents have more context for informed decisions
3. **System Integrity**: Only healthy agents can drive the coordination forward
4. **Clear Boundaries**: Timeout agents are completely excluded from active participation

## Implementation Notes
- The coordination loop only waits for active agents to vote
- Timeout agents are excluded from the voting cycle check
- The message templates system passes appropriate answer sets to agents
- All timeout handling preserves the original timeout reason and state

## Enhanced Timeout Handling Implementation

### 1. Enhanced `_handle_orchestrator_timeout` Method

The method now handles three distinct cases:

#### Case 1: All Agents Timeout (Orchestrator Generates Answer)
```python
if len(active_answers) == 0 and len(timeout_answers) > 0:
    yield StreamChunk(
        type="content",
        content="🤖 All agents timed out. Orchestrator generating comprehensive answer from partial results...\n",
        source=self.orchestrator_id,
    )
    # Orchestrator generates final presentation from all timeout answers
    async for chunk in self._orchestrator_generate_presentation(all_answers):
        yield chunk
```

#### Case 2: No Answers at All
```python
elif len(all_answers) == 0:
    yield StreamChunk(
        type="content",
        content="❌ No answers available from any agents.\n",
        source=self.orchestrator_id,
    )
    fallback_message = "I apologize, but no agents provided answers before timeout..."
    self.add_to_history("assistant", fallback_message)
    yield StreamChunk(type="content", content=fallback_message)
```

#### Case 3: Some Agents Active (Enhanced Normal Flow)
```python
# Only active agents can be selected
self._selected_agent = self._determine_final_agent_from_votes(current_votes, active_answers)

if self._selected_agent and active_answers.get(self._selected_agent):
    # Get vote results for presentation context
    vote_results = self._get_vote_results()
    
    # Let the selected agent generate final presentation considering ALL answers
    async for chunk in self.get_final_presentation(self._selected_agent, vote_results):
        yield chunk
```

### 2. New Orchestrator Presentation Method

```python
async def _orchestrator_generate_presentation(
    self, timeout_answers: Dict[str, str]
) -> AsyncGenerator[StreamChunk, None]:
    """Orchestrator generates final presentation from timeout agents' answers."""
    # Build a comprehensive summary from all timeout answers
    summary_parts = []
    summary_parts.append("Based on the partial results from all agents before timeout:\n")
    
    for agent_id, answer in timeout_answers.items():
        summary_parts.append(f"\n**{agent_id}**: {answer}\n")
    
    summary_parts.append("\n**Orchestrator Summary**:\n")
    
    # Simple aggregation - in production, this could use an LLM to synthesize
    if len(timeout_answers) == 1:
        # Single agent - use its answer
        single_answer = next(iter(timeout_answers.values()))
        summary_parts.append(single_answer)
    else:
        # Multiple agents - create a combined summary
        summary_parts.append("Multiple perspectives were provided by the agents before timeout. ")
        summary_parts.append("Here are the key insights from each agent's partial response:\n")
        
        for i, (agent_id, answer) in enumerate(timeout_answers.items(), 1):
            # Extract first 200 chars as summary
            summary = answer[:200] + "..." if len(answer) > 200 else answer
            summary_parts.append(f"\n{i}. {agent_id}: {summary}")
            
    final_summary = "".join(summary_parts)
    self.add_to_history("assistant", final_summary)
    
    yield StreamChunk(
        type="content",
        content=final_summary,
        source=self.orchestrator_id
    )
```

### 3. Final Presenter Considers All Answers

The existing `get_final_presentation` method already handles this correctly:

```python
# Get all answers for context
all_answers = {
    aid: s.answer for aid, s in self.agent_states.items() if s.answer
}

# This includes both active and timeout agents' answers
presentation_content = self.message_templates.build_final_presentation_message(
    original_task=self.current_task,
    vote_summary=voting_summary,
    all_answers=all_answers,  # Includes timeout agents
    selected_agent_id=selected_agent_id,
)
```

## Complete Timeout Handling Flow

1. **All Agents Timeout**:
   - Orchestrator collects all timeout answers
   - Generates comprehensive summary using `_orchestrator_generate_presentation`
   - Clearly indicates this is an orchestrator-generated fallback

2. **Some Agents Timeout**:
   - Only active agents participate in voting and selection
   - Selected active agent receives ALL answers (including timeout) for context
   - Final presentation incorporates insights from all agents

3. **No Answers Available**:
   - Generic fallback message
   - Suggests retry with simpler request or increased timeouts

## Status Messages

- `🤖 All agents timed out. Orchestrator generating comprehensive answer...`
- `🏆 Selected Agent: {agent_id} (from X votes)`
- `❌ No answers available from any agents`
- `⚠️ Generated from partial coordination due to timeout`
- `*Coordinated by X active agents and Y timeout agents via MassGen framework*`

## Orchestrator Timeout Trigger Mechanism

### When `_handle_orchestrator_timeout` is Triggered

The `_handle_orchestrator_timeout` method is triggered under specific conditions:

#### 1. Time-based Timeout
- When orchestrator coordination time exceeds `orchestrator_timeout_seconds` (default: 1800s = 30 minutes)
- Caught via `asyncio.timeout` and `TimeoutError` exception

#### 2. Token Limit Timeout
- When total tokens exceed `orchestrator_max_tokens` (default: 200,000 tokens)
- Checked during processing of each chunk

#### 3. Fallback Must Be Enabled
- `config.timeout_config.enable_timeout_fallback` must be `True` (default: True)
- If False, only returns error message without fallback generation

### Trigger Flow in `_coordinate_agents_with_timeout`

```python
async def _coordinate_agents_with_timeout(self, conversation_context):
    # 1. Initialize timeout tracking
    self.coordination_start_time = time.time()
    self.total_tokens = 0
    self.is_orchestrator_timeout = False
    self.timeout_reason = None
    
    timeout_seconds = self.config.timeout_config.orchestrator_timeout_seconds
    
    try:
        # 2. Set asyncio timeout (default 30 minutes)
        async with asyncio.timeout(timeout_seconds):
            async for chunk in coordination_task():
                # 3. Track tokens
                if hasattr(chunk, 'content') and chunk.content:
                    self.total_tokens += len(chunk.content.split())
                
                # 4. Check token limit (default 200k)
                if self.total_tokens > self.config.timeout_config.orchestrator_max_tokens:
                    self.is_orchestrator_timeout = True
                    self.timeout_reason = f"Token limit exceeded ({self.total_tokens}/{...})"
                    break
                
                yield chunk
                
    except asyncio.TimeoutError:
        # 5. Handle time-based timeout
        self.is_orchestrator_timeout = True 
        elapsed = time.time() - self.coordination_start_time
        self.timeout_reason = f"Time limit exceeded ({elapsed:.1f}s/{timeout_seconds}s)"
    
    # 6. Trigger timeout handler if conditions met
    if self.is_orchestrator_timeout and self.config.timeout_config.enable_timeout_fallback:
        async for chunk in self._handle_orchestrator_timeout():
            yield chunk
    elif self.is_orchestrator_timeout:
        # Fallback disabled - only show error
        yield StreamChunk(type="error", error=f"Orchestrator timeout: {self.timeout_reason}")
```

### Default Timeout Configuration

```python
@dataclass
class TimeoutConfig:
    orchestrator_timeout_seconds: int = 1800  # 30 minutes
    orchestrator_max_tokens: int = 200000     # 200k tokens
    agent_timeout_seconds: int = 300          # 5 minutes per agent
    agent_max_tokens: int = 50000             # 50k tokens per agent
    enable_timeout_fallback: bool = True      # Generate answer on timeout
```

### Trigger Scenarios

1. **Long Coordination**: Multiple agents discussing complex problems for over 30 minutes
2. **Excessive Output**: Total generated content exceeds 200k tokens
3. **Agent Blocking**: Some agents not responding, causing orchestrator to wait until timeout
4. **Resource Protection**: Prevents runaway processes from consuming unlimited resources

### Non-Trigger Scenarios

- If `enable_timeout_fallback = False`: Only outputs error, no fallback handling
- If all agents complete voting/coordination before timeout
- If individual agents timeout but orchestrator total time/tokens within limits

### Design Benefits

1. **Graceful Degradation**: Always provides some response even in timeout scenarios
2. **Resource Management**: Prevents infinite loops or excessive resource consumption  
3. **User Experience**: Clear feedback about timeout reasons and fallback status
4. **Flexibility**: Configurable timeouts for different use cases
5. **Robustness**: Handles both time and token-based limits

This dual-timeout mechanism (time + tokens) ensures the system remains responsive and resource-efficient while maximizing the chance of successful coordination.