# MassGen RL Integration

This module provides reinforcement learning capabilities for MassGen agents, enabling automatic learning and optimization of agent behavior.

## Overview

The RL integration follows the design from `docs/dev_notes/massgen_rl_integration_design.md` and provides:

- **Minimally Invasive**: Existing functionality preserved, RL is optional
- **Decoupled Architecture**: Training and execution are separated
- **Progressive Implementation**: Start simple, expand to complex scenarios
- **Backward Compatible**: No breaking changes to existing code

## Architecture

```
┌─────────────────────────────────────┐
│     MassGen Agent (with Mixin)      │
│  - Runs normally                    │
│  - Collects traces via mixin        │
└────────────┬────────────────────────┘
             │ Traces (spans, rewards)
             ↓
┌─────────────────────────────────────┐
│      Lightning Store (Local)        │
│  - Stores traces as JSON            │
│  - Organizes by date/agent          │
└────────────┬────────────────────────┘
             │ Read traces
             ↓
┌─────────────────────────────────────┐
│      Training (Future Phase)        │
│  - LightningRL algorithm            │
│  - APO prompt optimization          │
└─────────────────────────────────────┘
```

## Quick Start

### 1. Enable RL for Single Agent

```python
from massgen import AgentConfig
from massgen.chat_agent import SingleAgent
from massgen.rl import RLAgentMixin, RLConfig, StoreConfig

# Create RL-enabled agent class
class RLSingleAgent(RLAgentMixin, SingleAgent):
    pass

# Configure RL
rl_config = RLConfig(
    enable_rl=True,
    store_config=StoreConfig(
        type="local",
        path="./rl_data"
    ),
    enable_tool_rewards=True,
    enable_answer_quality_rewards=True,
    collect_only=True
)

# Create agent
config = AgentConfig.create_openai_config(model="gpt-4o")
agent = RLSingleAgent(
    backend=config.create_backend(),
    agent_id="my_agent",
    enable_rl=True,
    rl_config=rl_config
)

# Use normally - traces collected automatically
async for chunk in agent.chat([{"role": "user", "content": "Hello"}]):
    print(chunk.content)
```

### 2. Enable RL for Orchestrator

```python
from massgen import Orchestrator
from massgen.rl import RLOrchestratorMixin, RLConfig

# Create RL-enabled orchestrator
class RLOrchestrator(RLOrchestratorMixin, Orchestrator):
    pass

# Configure and use
rl_config = RLConfig(
    enable_rl=True,
    enable_coordination_rewards=True
)

orchestrator = RLOrchestrator(
    agents=agents,
    enable_rl=True,
    rl_config=rl_config
)
```

### 3. Run Data Collection Script

```bash
# Collect sample RL data
python scripts/collect_rl_data.py

# Check collected traces
ls -R ./rl_data/traces/
```

## Components

### Core Classes

- **`RLConfig`**: Configuration for RL features
  - `enable_rl`: Enable/disable RL collection
  - `enable_tool_rewards`: Compute rewards for tool calls
  - `enable_answer_quality_rewards`: Compute rewards for answer quality
  - `enable_coordination_rewards`: Compute rewards for coordination
  - `collect_only`: Only collect data, don't train (default for now)

- **`TraceCollector`**: Collects execution traces
  - Starts/ends traces
  - Emits different types of spans
  - Saves to LightningStore

- **`RewardComputer`**: Computes reward signals
  - Tool execution rewards
  - Answer quality rewards
  - Coordination efficiency rewards
  - Voting accuracy rewards

- **`LightningStore`**: Local storage for traces
  - Saves traces as JSON files
  - Organizes by date and agent
  - Provides query interface

### Mixins

- **`RLAgentMixin`**: Adds RL to individual agents
  - Wraps `chat()` method
  - Collects tool calls, content, reasoning
  - Computes immediate rewards

- **`RLOrchestratorMixin`**: Adds RL to orchestrator
  - Collects coordination events
  - Tracks voting, answers, restarts
  - Computes coordination rewards

### Data Structures

- **`Trace`**: Complete execution trajectory
  - Contains sequence of spans
  - Tracks total reward
  - Has metadata (agent_id, task, etc.)

- **Span Types**:
  - `PromptSpan`: LLM call (input, output, model)
  - `ToolSpan`: Tool execution (name, args, result)
  - `RewardSpan`: Reward signal (value, type, reason)
  - `CoordinationSpan`: Coordination event (vote, answer, restart)
  - `ContentSpan`: Content generation
  - `ReasoningSpan`: Reasoning process

## Configuration Options

```python
from massgen.rl import RLConfig, StoreConfig, AlgorithmConfig

rl_config = RLConfig(
    # Basic settings
    enable_rl=True,
    collect_only=True,  # Only collect, don't train

    # Storage
    store_config=StoreConfig(
        type="local",  # or "remote" (future)
        path="./rl_data"
    ),

    # Reward signals
    enable_tool_rewards=True,
    enable_answer_quality_rewards=True,
    enable_coordination_rewards=True,
    enable_human_feedback=False,  # RLHF (future)

    # Training (future phases)
    algorithm_config=AlgorithmConfig(
        algorithm="lightningrl",
        learning_rate=1e-5,
        batch_size=32,
        num_epochs=10
    ),

    # Paths
    checkpoint_dir="./rl_checkpoints",
    log_dir="./rl_logs"
)
```

## Reward System

### Tool Execution Rewards

- **Success**: `+1.0` for successful execution
- **Failure**: `-1.0` for exceptions/errors
- **Quality**: Adjusted based on result usefulness

Example:
```python
# Web search with good results: +1.0
# Code execution error: -1.0
# Empty result: -0.5
```

### Answer Quality Rewards

Based on:
- **Structure**: Headings, paragraphs, lists (+0.0 to +0.3)
- **Depth**: Examples, reasoning, specificity (+0.0 to +0.4)
- **Similarity**: Match to reference if available (+0.0 to +0.3)

Example:
```python
# Well-structured answer with examples: +0.8
# Short, unstructured answer: +0.2
# Empty answer: 0.0
```

### Coordination Rewards

Based on:
- **Efficiency**: Fewer rounds is better
- **Quality**: Final answer quality (×2.0 weight)
- **Consensus**: Achieved vs failed (+1.0 vs -0.5)
- **Tokens**: Penalty for excessive usage

Example:
```python
# 2 rounds, high quality, consensus: +2.5
# 5 rounds, low quality, no consensus: -1.0
```

## Data Storage Format

Traces are stored as JSON files:

```
rl_data/
├── traces/
│   ├── 20250109/          # Date
│   │   ├── agent_1/
│   │   │   ├── trace_abc123.json
│   │   │   └── trace_def456.json
│   │   └── agent_2/
│   │       └── trace_ghi789.json
│   └── 20250110/
│       └── ...
└── metadata/
    └── trace_index.json   # Fast lookup
```

Each trace file contains:
```json
{
  "trace_id": "trace_abc123",
  "agent_id": "agent_1",
  "task": "Analyze quantum computing",
  "spans": [
    {
      "span_type": "prompt",
      "input": "...",
      "output": "...",
      "model": "gpt-4o"
    },
    {
      "span_type": "tool",
      "tool_name": "web_search",
      "arguments": {...},
      "result": {...}
    },
    {
      "span_type": "reward",
      "reward": 1.0,
      "reward_type": "tool"
    }
  ],
  "total_reward": 2.5,
  "status": "completed"
}
```

## Testing

Run the test suite:

```bash
# Run all RL tests
pytest massgen/tests/test_rl_integration.py -v

# Run specific test
pytest massgen/tests/test_rl_integration.py::TestTraceCollector -v
```

## Implementation Status

✅ **Phase 1: Infrastructure (Completed)**
- [x] Module structure
- [x] Configuration system
- [x] Span data structures
- [x] Trace data structure
- [x] Local LightningStore
- [x] TraceCollector

✅ **Phase 2: Agent Integration (Completed)**
- [x] RLAgentMixin
- [x] RLOrchestratorMixin
- [x] RewardComputer
- [x] Tool reward computation
- [x] Answer quality rewards
- [x] Coordination rewards

🔄 **Phase 3: Training Loop (Future)**
- [ ] Agent Lightning SDK integration
- [ ] LightningRL algorithm
- [ ] Training scripts
- [ ] Checkpoint management

🔄 **Phase 4-7: Advanced Features (Future)**
- [ ] Prompt optimization (APO)
- [ ] Hierarchical RL
- [ ] Human feedback (RLHF)
- [ ] Remote store
- [ ] Distributed training

## Future Enhancements

1. **Training Pipeline**
   - Integrate Agent Lightning SDK
   - Implement LightningRL algorithm
   - Add training/deployment scripts

2. **Advanced Rewards**
   - Human feedback integration
   - External evaluation metrics
   - Multi-objective optimization

3. **Scalability**
   - Remote Lightning Store
   - Distributed data collection
   - Parallel training

4. **Visualization**
   - Training dashboard
   - Reward distributions
   - Trace inspection tools

## References

- Design Document: `docs/dev_notes/massgen_rl_integration_design.md`
- Example Script: `scripts/collect_rl_data.py`
- Tests: `massgen/tests/test_rl_integration.py`

## Support

For questions or issues with RL integration:
1. Check the design document for detailed explanations
2. Review example script for usage patterns
3. Run tests to verify installation
4. File issues on GitHub with `rl-integration` label
