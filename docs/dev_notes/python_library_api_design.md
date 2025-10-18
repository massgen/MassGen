# Python Library API Design Discussion

**Status**: Draft / Under Consideration
**Date**: 2025-01-12
**Context**: MassGen is currently CLI-only. We want to add a Python library API but need to think through the design carefully.

## The Question

**When do we create an API vs. not?**

Currently, MassGen is entirely CLI-driven with YAML configuration. Users mentioned we'll "make a library soon", but we need to think through:

1. What functionality should be exposed as a Python API?
2. What should remain CLI-only?
3. Specifically: Do we need an API for filesystem operations?
4. What's the right abstraction level?

## How MassGen Coordination Actually Works

**Important Context for API Design:**

MassGen's coordination is **asynchronous** and **anonymous**:

1. **Asynchronous evaluation** - No "rounds", agents evaluate independently
2. **Anonymized answers** - Agents see answers without knowing which agent provided them
3. **Restart on new_answer** - When any agent provides `new_answer`, ALL agents restart evaluation
4. **Actual prompt** - Agents evaluate: "Does the best CURRENT ANSWER address the ORIGINAL MESSAGE well?"
   - If YES → `vote` tool
   - If NO → Digest, combine strengths, address weaknesses → `new_answer` tool

This means the API should:
- Not expose "which agent is in which round" (no rounds exist)
- Not break anonymization by revealing answer attribution during coordination
- Allow inspection after coordination completes (when anonymization is less critical)

## Current State

### What We Have (CLI-based)
```bash
# CLI command
uv run python -m massgen.cli --config config.yaml "Your question"
```

### What We Don't Have (Python API)
```python
# This doesn't exist yet
from massgen import MassGen

# What should this look like?
result = massgen.run(agents=[...], query="Your question")
```

## Design Options

### Option 1: Mirror CLI Functionality (Simple)

**Pros:**
- Easy to implement - thin wrapper around existing CLI
- Consistent with CLI behavior
- Low maintenance burden

**Cons:**
- Doesn't leverage Python's strengths
- Limited programmatic control
- Still feels like "running a CLI from Python"

```python
from massgen import run_from_config

result = run_from_config(
    config_path="config.yaml",
    query="Your question"
)
```

### Option 2: Full Programmatic API (Rich)

**Pros:**
- Idiomatic Python
- Fine-grained control
- Composable and testable
- Can integrate into Python applications

**Cons:**
- Large API surface to maintain
- Two ways to do everything (YAML vs code)
- More complex implementation

```python
from massgen import Orchestrator, Agent
from massgen.backends import GeminiBackend, ClaudeCodeBackend

# Define agents programmatically
agents = [
    Agent(
        id="researcher",
        backend=GeminiBackend(model="gemini-2.5-flash"),
        system_message="You are a researcher"
    ),
    Agent(
        id="coder",
        backend=ClaudeCodeBackend(
            model="claude-sonnet-4",
            workspace="./workspace"
        )
    )
]

# Run coordination
orchestrator = Orchestrator(agents=agents)
result = orchestrator.coordinate(query="Your question")

# Access results
print(result.final_answer)
print(result.winner.id)
for vote in result.votes:
    print(f"{vote.agent} voted for {vote.target}")
```

### Option 3: Hybrid Approach (Pragmatic)

**Pros:**
- YAML for configuration (declarative, shareable)
- Python API for control flow and integration
- Best of both worlds

**Cons:**
- Need to decide what goes where
- Potential confusion about which approach to use

```python
from massgen import MassGen

# Load from YAML but control programmatically
massgen = MassGen.from_config("config.yaml")

# Programmatic control
result = massgen.run("Your question")

# Access internals
for agent in massgen.agents:
    print(f"Agent {agent.id} workspace: {agent.workspace.path}")

# Iterate over turns in interactive mode
massgen = MassGen.from_config("config.yaml")
for turn in massgen.interactive():
    query = input("Your question: ")
    result = turn.run(query)
    print(result.final_answer)
```

## Filesystem Operations: API or Not?

### The Specific Question

Do we expose filesystem operations through a Python API?

**Current state:** Filesystem operations happen through:
1. Claude Code's native tools (Read, Write, Edit, Bash)
2. MCP filesystem servers
3. Context paths (read/write permissions)

**Should we add:**
```python
# Option A: Expose workspace operations
workspace = agent.workspace
workspace.write_file("test.txt", "content")
workspace.read_file("test.txt")

# Option B: Context path operations
orchestrator.context_paths[0].list_files()
orchestrator.context_paths[0].read_file("src/main.py")

# Option C: None - keep it agent-driven only
```

### Considerations

**Against exposing filesystem API:**
- Agents should control file operations, not external code
- Breaks the abstraction of "agents working autonomously"
- Context paths are meant for agent access, not library user access
- Adds surface area for permission/safety bugs

**For exposing filesystem API:**
- Useful for setup/teardown in programmatic usage
- Inspecting results after coordination
- Setting up test fixtures
- Reading final outputs

**Middle ground:**
- Read-only access to workspaces after coordination completes
- Setup/teardown helpers but no mid-coordination access
- Query methods (list files, check existence) but not modify

```python
# Read-only post-coordination access
result = orchestrator.coordinate("Build a website")
winner_workspace = result.winner.workspace

# Read final outputs
files = winner_workspace.list_files()
content = winner_workspace.read_file("index.html")

# But can't modify - that's the agent's job
# winner_workspace.write_file(...) # ❌ Not allowed
```

## Recommendations

### Phase 1: Start Simple (Hybrid Approach)
1. **Keep YAML as primary configuration method**
2. **Add thin Python API for control flow:**
   ```python
   from massgen import MassGen

   massgen = MassGen.from_config("config.yaml")
   result = massgen.run("Your question")
   ```

3. **Expose read-only inspection of results:**
   ```python
   print(result.final_answer)
   print(result.winner.id)
   files = result.winner.workspace.list_files()
   ```

4. **No write access to filesystem through API** - agents control that

### Phase 2: Expand Based on Usage
- Monitor how people use the API
- Add programmatic agent construction if there's demand
- Consider context path setup helpers if needed
- Let real-world usage guide the design

## Open Questions

1. **Should we allow programmatic agent construction?** Or always require YAML config?
2. **Interactive mode API** - how should multi-turn work in code?
3. **Async support** - should the API be async/await?
4. **Streaming** - how to handle streaming responses in Python API?
5. **Error handling** - what exceptions should we raise?
6. **Testing** - mock agents? test utilities?

## Next Steps

1. **Create RFC** for initial Python API design
2. **Prototype** Option 3 (Hybrid) with Phase 1 scope
3. **Gather feedback** from early users
4. **Iterate** based on real usage patterns
5. **Document** clear guidance on "CLI vs API" decision making

## Related

- `docs/source/user_guide/concepts.rst` - Current CLI-based mental model
- `docs/source/quickstart/configuration.rst` - YAML-first approach
- Future: `docs/source/user_guide/python_api.rst` - Python API guide (TBD)
