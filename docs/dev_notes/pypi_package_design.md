# MassGen PyPI Package Design

**Status:** Draft
**Author:** Nick
**Date:** 2025-10-13
**Target Version:** v0.0.33 (PyPI Release)

---

## User Journey: From Install to Success

This design doc describes the PyPI release experience for MassGen users.

### The 5-Minute Journey

**Minute 1: Installation**
```bash
pip install massgen
```

**Minute 2: First Run (Interactive Setup)**
```bash
$ massgen "What is AI?"

╔═══════════════════════════════════════════════════════════════╗
║           Welcome to MassGen - Multi-Agent System             ║
╚═══════════════════════════════════════════════════════════════╝

First time setup! Let's configure MassGen.

✓ Found ANTHROPIC_API_KEY in environment
✗ OPENAI_API_KEY not found

What will you use MassGen for?
  [1] Research (web search, multi-agent collaboration)
  [2] Coding (file operations, development tools)
  [3] Single agent (fast, simple)
  [4] Skip (use temporary config)

Choice: 1

Creating research configuration...
  ✓ Saved to ~/.config/massgen/config.yaml

Running your query...
[Multi-agent coordination happens]

Answer: Artificial Intelligence is...
```

**Minute 3-5: Exploring**
```bash
# List examples
$ massgen --list-examples

Available Example Configurations
═════════════════════════════════

Single Agent:
  @examples/basic_single           Claude Sonnet 4 (fast)

Multi-Agent:
  @examples/basic_multi            Gemini + GPT + Grok (recommended)
  @examples/research_team          Research-optimized team

Tools:
  @examples/mcp_weather            Weather information
  @examples/file_operations        File system operations

# Try an example
$ massgen --config @examples/basic_multi "Compare renewable energy sources"

# Save and customize
$ massgen --example basic_multi > my-team.yaml
# Edit my-team.yaml...
$ massgen --config my-team "Your question"
```

**Done!** User is productive in 5 minutes.

---

## Python API Usage

For users who want programmatic access:

```python
import asyncio
import massgen

# Quick single agent
result = await massgen.run(
    query="What is machine learning?",
    model="gemini-2.5-flash"
)
print(result['final_answer'])

# Multi-agent with config
result = await massgen.run(
    query="Analyze climate change data",
    config="@examples/research_team"
)

# Or synchronously
result = asyncio.run(massgen.run("Question", model="claude-sonnet-4"))
```

**Note:** MassGen is async by nature, so the API is naturally async.

---

## Backwards Compatibility

**100% backwards compatible. All existing workflows continue to work.**

### For Git Clone Users

If you're currently using MassGen via git clone, **nothing changes**:

```bash
# Your existing commands work exactly as before
cd /path/to/MassGen
uv run python -m massgen.cli \
  --config massgen/configs/basic/multi/three_agents_default.yaml \
  "Question"
# ✓ Still works!

# Your custom configs work
uv run python -m massgen.cli \
  --config my-custom-config.yaml \
  "Question"
# ✓ Still works!

# All existing flags work
uv run python -m massgen.cli \
  --config config.yaml \
  --no-display \
  --debug \
  "Question"
# ✓ Still works!
```

### Python API for Git Clone Users

**Git clone users can also use the Python API!** Just install the local package in editable mode:

```bash
cd /path/to/MassGen
uv pip install -e .  # Editable install
```

Then use the Python API from anywhere:

```python
import massgen

# Works exactly like pip install users
result = await massgen.run("Question", model="gemini-2.5-flash")
print(result['final_answer'])

# Use with config files
result = await massgen.run("Question", config="@examples/basic_multi")

# Or use local config files
result = await massgen.run(
    "Question",
    config="massgen/configs/basic/multi/three_agents_default.yaml"
)
```

**All features work:**
- ✓ `massgen.run()` API
- ✓ Config resolution (`@examples/` syntax)
- ✓ Config builder (`massgen --init`)
- ✓ All CLI commands

**The only difference:** Git clone users can edit the source code directly and see changes immediately (since it's an editable install).

### Both Old and New Syntax Work

After implementing this design, **both** syntaxes work:

```bash
# Old style (works if file exists at this path)
massgen --config massgen/configs/basic/multi/three_agents_default.yaml "Q"

# New style (works from any directory after pip install)
massgen --config @examples/basic_multi "Q"
```

### Why Both Work

The `resolve_config_path()` function tries multiple strategies:

```python
def resolve_config_path(config_arg: Optional[str]) -> Optional[Path]:
    # 1. Try @examples/ prefix (new)
    if config_arg.startswith('@examples/'):
        # Look in package...

    # 2. Try as regular path (supports old style)
    path = Path(config_arg).expanduser()
    if path.exists():
        return path  # Old style works here!

    # 3. Try user config directory (new)
    # 4. Try other locations...
```

So if you provide `massgen/configs/...` and that file exists, it uses it. No breaking changes.

### Migration: Optional, Not Required

**Existing users:** Keep using your current workflow. No action needed.

**New users:** Use `@examples/` syntax for better portability.

**If you want to migrate:**
```bash
# Old
massgen --config massgen/configs/basic/multi/three_agents_default.yaml "Q"

# New (shorter, works from any directory)
massgen --config @examples/basic_multi "Q"
```

But migration is **optional**. Old style will be supported indefinitely.

### No Deprecation Warnings

We will **not** add deprecation warnings for old-style paths because:
1. Old style is valid for development workflow
2. No plan to remove support
3. Avoids annoying existing users

Both styles are first-class citizens.

---

## How It Works

### 1. Config Resolution

Users can reference configs in multiple ways:

```bash
# Package examples (works after pip install)
massgen --config @examples/basic_multi

# Named config in user directory
massgen --config my-team
# → Looks for ~/.config/massgen/agents/my-team.yaml

# Relative path
massgen --config ./agents/custom.yaml

# Absolute path
massgen --config /path/to/config.yaml

# No config (first-run triggers wizard)
massgen "Question"
```

**Implementation:**

```python
def resolve_config_path(config_arg: Optional[str]) -> Optional[Path]:
    """
    Resolve config file with flexible syntax.

    Priority:
    1. @examples/NAME → Package examples
    2. Absolute/relative paths
    3. Named configs in ~/.config/massgen/agents/
    4. None → trigger config builder
    """
    if not config_arg:
        return None  # Trigger builder

    if config_arg.startswith('@examples/'):
        # Find in package using importlib.resources
        name = config_arg[10:]
        from importlib.resources import files
        configs = files('massgen') / 'configs'
        # Search recursively for matching name
        for f in configs.rglob('*.yaml'):
            if name in str(f):
                return f

    # Regular path resolution
    path = Path(config_arg).expanduser()
    if path.exists():
        return path

    # Try user config dir
    user_path = Path.home() / '.config/massgen/agents' / f"{config_arg}.yaml"
    if user_path.exists():
        return user_path

    raise FileNotFoundError(f"Config not found: {config_arg}")
```

### 2. First-Run Experience (Config Builder)

#### When It Triggers

The config builder runs automatically when:
1. User runs `massgen "Question"` without specifying `--config` or `--model`
2. No config exists at `~/.config/massgen/config.yaml`

Or manually via: `massgen --init`

**Detection:**
```python
def should_run_builder() -> bool:
    """Check if config builder should run."""
    user_config = Path.home() / '.config/massgen/config.yaml'
    return not user_config.exists()
```

#### Config Persistence

**After completing the wizard on first run:**
- Config is saved to `~/.config/massgen/config.yaml`
- ✓ Automatically loaded on all future runs
- ✓ No wizard on subsequent runs
- User can override per-query with `--config` or `--model` flags

**If wizard is skipped (option [5]):**
- No config is saved (temporary)
- ✓ Wizard will run again on next invocation
- User can avoid wizard by using `--config` or `--model` flags

**Changing saved config:**

```bash
# Re-run wizard to replace config
massgen --init

# Or edit directly
vim ~/.config/massgen/config.yaml

# Or override per-query (doesn't change saved config)
massgen --config @examples/basic_single "Question"
massgen --model gemini-2.5-flash "Question"
```

**Example: First run (wizard completed)**

```bash
# First run
$ massgen "What is AI?"
# → Wizard runs
# → User selects [2] Research & Analysis
# → Config saved to ~/.config/massgen/config.yaml
# → Query runs with research team

# Second run
$ massgen "What is machine learning?"
# → NO wizard (config exists)
# → Loads ~/.config/massgen/config.yaml
# → Runs with research team from first run
```

**Example: First run (wizard skipped)**

```bash
# First run
$ massgen "What is AI?"
# → Wizard runs
# → User selects [5] Skip Setup
# → Config NOT saved
# → Query runs with default single agent

# Second run
$ massgen "What is machine learning?"
# → Wizard runs AGAIN (no saved config)
# → User must choose or skip again
```

#### Interactive Wizard Flow

**Step 1: Welcome & API Key Check**
```
╔═══════════════════════════════════════════════════════════════╗
║           Welcome to MassGen - Multi-Agent System             ║
╚═══════════════════════════════════════════════════════════════╝

First time setup! Let's configure MassGen.

Checking for API keys...
  ✓ ANTHROPIC_API_KEY found
  ✓ OPENAI_API_KEY found
  ✗ GOOGLE_API_KEY not found
  ✗ XAI_API_KEY not found

You have 2/4 provider keys configured.
(You can add more later in ~/.config/massgen/.env)
```

**Step 2: Use Case Selection**
```
What will you primarily use MassGen for?

  [1] Custom Configuration (Recommended)
      → Build your own multi-agent team from scratch
      → Choose number of agents, backends, models, and tools
      → Most flexible option

  [2] Research & Analysis (Pre-built Multi-Agent Team)
      → 3-agent team with web search
      → Gemini 2.5 Pro + GPT-5 Mini + Grok-4 Fast Reasoning
      → Best for: research, current events, fact-checking

  [3] Coding & Development (Pre-built Multi-Agent Team)
      → 2-agent team with file operations and code execution
      → Claude Code + GPT-5
      → Best for: software projects, code review

  [4] Single Agent (Fast & Simple)
      → One powerful agent (no coordination overhead)
      → Claude Sonnet 4
      → Best for: quick questions, simple tasks

  [5] Skip Setup
      → Use temporary config for this session only
      → Config won't be saved

Choice [1-5]: 1
```

**Step 3: Configuration Preview**
```
Creating Custom configuration...

How many agents would you like? [1-5]: 3

Select backend for Agent 1:
  [1] Anthropic Claude
  [2] OpenAI GPT
  [3] Google Gemini
  [4] xAI Grok
Choice: 3

Select model:
  [1] gemini-2.5-pro
  [2] gemini-2.5-flash
Choice: 1

Enable web search? [Y/n]: y

[... repeat for agents 2 and 3 ...]

Your Agent Team:
  • Gemini 2.5 Pro (Google)
    - Web search enabled
    - Advanced reasoning

  • GPT-5 Mini (OpenAI)
    - Web search enabled
    - Fast, cost-effective

  • Grok-4 Fast Reasoning (xAI)
    - Web search enabled
    - Real-time information

Coordination: Multi-agent voting and consensus
UI: Rich terminal display with live coordination

Looks good? [Y/n]: y
```

**Step 4: Save & Run**
```
✓ Configuration saved to ~/.config/massgen/config.yaml
✓ Created ~/.config/massgen/.env (add API keys here)
✓ Created ~/.config/massgen/agents/ (for your custom configs)

Setup complete!

Running your query with research team...
```

#### What Gets Created

```
~/.config/massgen/
├── config.yaml                    # Default config based on use case
├── .env                           # Template for API keys
└── agents/                        # Directory for user's custom configs
```

**Example `config.yaml` (Custom/Research preset):**
```yaml
agents:
  - id: "gemini_researcher"
    backend:
      type: "gemini"
      model: "gemini-2.5-pro"
      enable_web_search: true
    system_message: "You are a research specialist..."

  - id: "gpt_analyst"
    backend:
      type: "openai"
      model: "gpt-5-mini"
      enable_web_search: true
    system_message: "You are an analytical thinker..."

  - id: "grok_checker"
    backend:
      type: "grok"
      model: "grok-4-fast-reasoning"
      enable_web_search: true
    system_message: "You provide alternative perspectives..."

orchestrator:
  snapshot_storage: "~/.config/massgen/snapshots"
  session_storage: "~/.config/massgen/sessions"

ui:
  display_type: "rich_terminal"
  logging_enabled: true
```

#### Preset Templates

**1. Custom Configuration (Recommended, Default)**
- Interactive builder
- Choose number of agents
- Select backend and model for each agent
- Configure tools per agent (web search, file operations, etc.)
- Most flexible option - users build exactly what they need

**2. Research & Analysis (Pre-built Multi-Agent Team)**
- 3 agents: Gemini 2.5 Pro + GPT-5 Mini + Grok-4 Fast Reasoning
- All with web search enabled
- Optimized for: current events, fact-checking, comprehensive research

**3. Coding & Development (Pre-built Multi-Agent Team)**
- 2 agents: Claude Code + GPT-5
- File operations enabled
- Code execution enabled
- Optimized for: software development, code review

**4. Single Agent (Fast & Simple)**
- 1 agent: Claude Sonnet 4
- Fast, no coordination overhead
- Optimized for: quick questions, simple tasks

#### Integration with PR #309

The config builder from PR #309 provides the `ConfigBuilder` class:

```python
from massgen.config_builder import ConfigBuilder

def run_config_builder():
    """Run the interactive config builder."""
    builder = ConfigBuilder()

    # Run interactive wizard
    result = builder.run()

    if result.success:
        print(f"\n✓ Configuration saved to {result.config_path}")
        print(f"\nYou can:")
        print(f"  • Run queries: massgen 'Your question'")
        print(f"  • Edit config: {result.config_path}")
        print(f"  • Create more configs in: ~/.config/massgen/agents/")
        return result.config_path
    else:
        print("\n✗ Configuration setup cancelled")
        print("  Using temporary config for this session")
        return None
```

#### Reconfiguration

Users can re-run the wizard anytime:

```bash
# Re-run setup wizard
massgen --init

# Options:
#   [1] Replace current config
#   [2] Create new config (save to agents/)
#   [3] Edit current config
#   [4] Reset to defaults
#   [5] Exit
```

### 3. CLI Enhancements

**New flags:**

```python
@click.command()
@click.option('--config', help='Config file or @examples/NAME')
@click.option('--model', help='Quick single-agent mode')
@click.option('--init', is_flag=True, help='Run setup wizard')
@click.option('--example', help='Print example config to stdout')
@click.option('--list-examples', is_flag=True, help='List available examples')
@click.argument('query', required=False)
def main(config, model, init, example, list_examples, query, **kwargs):
    # Handle special commands
    if init:
        run_config_builder()
        return

    if list_examples:
        show_available_examples()
        return

    if example:
        print_example_config(example)
        return

    # First-run check
    if not query and should_run_builder():
        run_config_builder()
        return

    # Normal execution
    config_path = resolve_config_path(config)
    # ... existing logic
```

**Helper: List Examples**

```python
def show_available_examples():
    """Pretty-print available configs."""
    from importlib.resources import files

    configs = files('massgen') / 'configs'

    print("\nAvailable Example Configurations\n" + "="*50)

    categories = {
        'basic/single': 'Single Agent',
        'basic/multi': 'Multi-Agent',
        'tools/mcp': 'MCP Tools',
        'tools/filesystem': 'File Operations'
    }

    for path, title in categories.items():
        print(f"\n{title}:")
        for config in (configs / path).glob('*.yaml'):
            shortcut = str(config.stem)
            print(f"  @examples/{shortcut:<30} {config.stem}")

    print("\nUsage:")
    print("  massgen --config @examples/basic_multi 'Question'")
```

### 4. Simple Python API

**Expose existing async functionality:**

```python
# massgen/__init__.py

__version__ = "0.1.0"

async def run(query: str,
              config: Optional[str] = None,
              model: Optional[str] = None) -> dict:
    """
    Run MassGen query.

    Args:
        query: Question or task for agents
        config: Config file or @examples/NAME (optional)
        model: Quick single-agent mode (optional)

    Returns:
        Dict with 'final_answer' and metadata

    Examples:
        # Single agent
        result = await massgen.run("What is AI?", model="gemini-2.5-flash")

        # Multi-agent
        result = await massgen.run("Compare energy sources",
                                   config="@examples/basic_multi")
    """
    from massgen.cli import run_massgen_from_config, run_massgen_quick
    from massgen.cli import resolve_config_path

    if model:
        return await run_massgen_quick(query=query, model=model)
    else:
        config_path = resolve_config_path(config)
        return await run_massgen_from_config(query=query, config=config_path)

__all__ = ['run', '__version__']
```

**Note:** Just expose the existing logic. No new abstractions needed.

### 5. Package Data Inclusion

**In `pyproject.toml`:**

```toml
[tool.setuptools.packages.find]
include = ["massgen*"]

[tool.setuptools.package-data]
massgen = [
    "configs/**/*.yaml",
    "configs/**/*.yml"
]
```

That's it! `massgen/configs/` directory ships with the wheel.

---

## Multi-Turn Mode (Interactive Sessions)

MassGen supports interactive multi-turn conversations where context is preserved across turns. This works seamlessly with the PyPI setup.

### How to Start Multi-Turn Mode

**Option 1: Omit the query**
```bash
# With default config
massgen

# With specific config
massgen --config @examples/basic_multi

# With single agent
massgen --model gemini-2.5-flash
```

**Option 2: Python API**
```python
import massgen

# Start interactive session (future API)
session = await massgen.start_session(config="@examples/basic_multi")
result1 = await session.ask("What is quantum computing?")
result2 = await session.ask("Give me a practical example")  # Has context from turn 1
await session.close()
```

### What Happens in Multi-Turn Mode

**Turn 1:**
```bash
$ massgen

MassGen Interactive Mode
Type your question or /help for commands

You: What is machine learning?

[Agents coordinate]
Agent coordination complete. Winner: gpt_analyst

Answer: Machine learning is a subset of artificial intelligence...

Session saved to: ~/.config/massgen/sessions/session_2025-01-12_143022/
```

**Turn 2:**
```bash
You: Give me a practical example

[Agents coordinate with context from turn 1]
Agent coordination complete. Winner: gemini_researcher

Answer: Building on the definition I provided earlier, here's a practical
example of supervised machine learning...
```

**Turn 3:**
```bash
You: How can I implement this in Python?

[Agents coordinate with full conversation history]
Agent coordination complete. Winner: gpt_analyst

Answer: Based on the supervised learning example I mentioned, here's how to
implement it in Python using scikit-learn...
```

### Session Storage

Multi-turn sessions are automatically saved:

```
~/.config/massgen/sessions/
└── session_2025-01-12_143022/
    ├── turn_1/
    │   ├── coordination_log.json          # Coordination events
    │   ├── agent_responses.json           # All agent answers
    │   └── final_answer.txt               # Winner's answer
    ├── turn_2/
    │   ├── coordination_log.json
    │   ├── agent_responses.json
    │   └── final_answer.txt
    ├── turn_3/
    │   └── ...
    └── session_summary.json               # Full conversation history
```

### Context Preservation

Each turn includes:
1. **Full conversation history** - All previous queries and answers
2. **Agent memory** - Each agent sees its own previous responses
3. **Workspace state** (if using file operations) - Files persist across turns
4. **Tool results** - Previous tool calls and results available

**How context flows:**
```
Turn 1: "What is ML?"
  → Agents answer
  → Context: [Turn 1]

Turn 2: "Give example"
  → Agents see: [Turn 1, Turn 2 query]
  → Answer builds on Turn 1
  → Context: [Turn 1, Turn 2]

Turn 3: "How to implement?"
  → Agents see: [Turn 1, Turn 2, Turn 3 query]
  → Answer builds on Turn 1 & 2
  → Context: [Turn 1, Turn 2, Turn 3]
```

### Multi-Turn with File Operations

When using agents with file operations (Claude Code, MCP filesystem), workspaces persist across turns:

```bash
$ massgen --config @examples/file_operations

You: Create a Python web scraper

[Agents coordinate]
Winner creates files in workspace:
  ~/.config/massgen/workspaces/agent_coder/
    └── scraper.py

You: Add error handling to the scraper

[Agents see previous workspace]
Winner reads scraper.py, modifies it with error handling

You: Write unit tests for it

[Agents see updated workspace]
Winner creates tests/test_scraper.py
```

**Workspace structure:**
```
~/.config/massgen/
├── workspaces/                    # Persistent agent workspaces
│   ├── agent_coder/
│   │   ├── scraper.py
│   │   └── tests/
│   │       └── test_scraper.py
│   └── agent_reviewer/
│       └── review_notes.md
├── snapshots/                     # Snapshots during coordination
│   ├── agent_coder_turn1/
│   ├── agent_coder_turn2/
│   └── agent_coder_turn3/
└── sessions/                      # Session history
    └── session_2025-01-12_143022/
```

### Interactive Commands

During multi-turn mode, users can use special commands:

```bash
You: /help
Available commands:
  /clear      - Clear conversation history
  /quit       - Exit interactive mode (/q, /exit also work)
  /save NAME  - Save current session with custom name
  /show       - Show full conversation history
  /config     - Show current configuration
  Ctrl+C      - Exit interactive mode

You: /clear
Conversation history cleared. Starting fresh.

You: /quit
Session saved to ~/.config/massgen/sessions/session_2025-01-12_143022/
Goodbye!
```

### Multi-Turn Performance

**Context management:**
- Each turn adds to context window
- MassGen automatically manages token limits
- Older turns may be summarized if context gets too long
- Critical information preserved

**Coordination per turn:**
- Full coordination happens for each user query
- Agents vote and reach consensus on every turn
- Same quality as single-turn mode
- Takes 1-5 minutes per turn depending on complexity

### Python API for Multi-Turn (Future)

Proposed Python API for multi-turn sessions:

```python
import massgen

# Start session
session = await massgen.start_session(config="@examples/basic_multi")

# Turn 1
result = await session.ask("What is quantum computing?")
print(result['final_answer'])

# Turn 2 (with context)
result = await session.ask("Give me a practical example")
print(result['final_answer'])

# Turn 3 (with full history)
result = await session.ask("How can I implement this?")
print(result['final_answer'])

# Clear context if needed
session.clear_history()

# Close session
await session.close()

# Or use context manager
async with massgen.start_session(config="my-team") as session:
    result1 = await session.ask("Question 1")
    result2 = await session.ask("Question 2")
    # Auto-saved on exit
```

### Use Cases for Multi-Turn

**1. Iterative Development**
```
Turn 1: "Create a Flask API for user management"
Turn 2: "Add authentication with JWT"
Turn 3: "Add rate limiting"
Turn 4: "Write integration tests"
```

**2. Research Deep Dives**
```
Turn 1: "What is quantum entanglement?"
Turn 2: "Explain Bell's theorem"
Turn 3: "How is this used in quantum computing?"
Turn 4: "What are the practical applications?"
```

**3. Document Analysis**
```
Turn 1: "Read the contract in docs/contract.pdf and summarize key terms"
Turn 2: "What are the potential risks?"
Turn 3: "Draft amendments to address those risks"
Turn 4: "Format as a legal memo"
```

**4. Debugging**
```
Turn 1: "Review error in logs/error.log"
Turn 2: "Check the database connection code"
Turn 3: "Suggest a fix"
Turn 4: "Implement the fix and test it"
```

### Configuration for Multi-Turn

Multi-turn mode uses the same config as single-turn. To optimize for multi-turn:

```yaml
orchestrator:
  # Where to save sessions
  session_storage: "~/.config/massgen/sessions"

  # Workspace persistence for file operations
  snapshot_storage: "~/.config/massgen/snapshots"
  agent_temporary_workspace: "~/.config/massgen/workspaces"

  # Optional: context management
  max_conversation_turns: 20           # Limit conversation length
  context_summarization: true          # Summarize old turns
  preserve_critical_info: true         # Keep important context

agents:
  - id: "agent1"
    backend:
      type: "claude_code"
      model: "claude-sonnet-4"
      # Persistent workspace across turns
      cwd: "~/.config/massgen/workspaces/agent1"
```

---

## Directory Structure (Minimal Changes)

**Existing structure stays the same:**

```
massgen/
├── __init__.py                    # Add: async run() function
├── cli.py                         # Add: new flags + helpers
├── config_builder.py              # Integrate PR #309
├── configs/                       # Ship with package (unchanged)
│   ├── basic/
│   │   ├── single/
│   │   └── multi/
│   ├── tools/
│   │   ├── mcp/
│   │   └── filesystem/
│   └── providers/
├── backend/                       # Unchanged
├── orchestrator.py                # Unchanged
├── agent_config.py                # Unchanged
└── ...                            # Everything else unchanged
```

**User directory (created on first run):**

```
~/.config/massgen/
├── config.yaml                    # Default config from wizard
├── .env                           # API keys (optional)
└── agents/                        # User's custom configs
    ├── my-research-team.yaml
    └── my-coding-team.yaml
```

---

## Implementation Plan

### Phase 1: Config Resolution (1-2 days)

**Goal:** Make `@examples/` syntax work

**Tasks:**
1. Add `resolve_config_path()` function to `cli.py`
2. Update `pyproject.toml` to include `configs/**/*.yaml`
3. Test that configs ship with package
4. Test `@examples/basic_multi` resolution

**Test:**
```bash
pip install -e .
massgen --config @examples/basic_multi "Test"
```

### Phase 2: CLI Enhancements (2-3 days)

**Goal:** Add new flags and helpers

**Tasks:**
1. Add `--init`, `--example`, `--list-examples` flags
2. Implement `show_available_examples()`
3. Implement `print_example_config()`
4. Add first-run detection logic

**Test:**
```bash
massgen --list-examples
massgen --example basic_multi > test.yaml
massgen --init
```

### Phase 3: Config Builder (2-3 days)

**Goal:** First-run wizard experience

**Tasks:**
1. Integrate config builder from PR #309
2. Connect to first-run detection
3. Create `~/.config/massgen/` directory structure
4. Test full first-run flow

**Test:**
```bash
rm -rf ~/.config/massgen
massgen "Test"
# Should trigger wizard
```

### Phase 4: Python API (1 day)

**Goal:** Expose async run() function

**Tasks:**
1. Add `async def run()` to `__init__.py`
2. Import and wrap existing CLI functions
3. Write docstring with examples
4. Basic tests

**Test:**
```python
import massgen
result = await massgen.run("Hi", model="gemini-2.5-flash")
assert 'final_answer' in result
```

### Phase 5: Documentation (3-4 days)

**Goal:** Update all docs for pip install users

**Tasks:**
1. Rewrite installation page (pip install first)
2. Update Quick Start with first-run flow
3. Replace all `massgen/configs/...` with `@examples/...`
4. Add Python API documentation page
5. Update troubleshooting section

### Phase 6: Testing & Release (2-3 days)

**Tasks:**
1. Integration tests for config resolution
2. Test on clean system (VM or Docker)
3. Build wheel and test install
4. Publish to TestPyPI
5. Test from TestPyPI
6. Publish to PyPI

**Total:** ~2 weeks

---

## Files to Change

### 1. `massgen/__init__.py` (New Python API)

```python
"""MassGen - Multi-Agent System for GenAI"""

__version__ = "0.1.0"

async def run(query: str, config=None, model=None) -> dict:
    """Run MassGen query. [Full docstring]"""
    from massgen.cli import run_massgen_from_config, run_massgen_quick
    from massgen.cli import resolve_config_path

    if model:
        return await run_massgen_quick(query=query, model=model)
    else:
        config_path = resolve_config_path(config)
        return await run_massgen_from_config(query=query, config=config_path)

__all__ = ['run', '__version__']
```

### 2. `massgen/cli.py` (Enhanced CLI)

Add:
- `resolve_config_path()` function
- `show_available_examples()` function
- `print_example_config()` function
- `should_run_builder()` function
- `run_config_builder()` function
- New CLI flags: `--init`, `--example`, `--list-examples`

### 3. `pyproject.toml` (Package Data)

```toml
[tool.setuptools.package-data]
massgen = ["configs/**/*.yaml", "configs/**/*.yml"]
```

### 4. `massgen/config_builder.py` (Integration)

Use existing code from PR #309, no changes needed.

---

## Success Criteria

After implementation, these should all work:

### For New Users (pip install)

```bash
# Install
pip install massgen

# First run triggers wizard
massgen "What is AI?"
# ✓ Wizard runs, creates config, answers question

# Use examples
massgen --config @examples/basic_multi "Question"
# ✓ Works without error

# List examples
massgen --list-examples
# ✓ Shows all available configs

# Print example
massgen --example basic_multi > my-config.yaml
# ✓ Outputs config to file
```

### For Existing Users (git clone)

```bash
# Old style still works
uv run python -m massgen.cli \
  --config massgen/configs/basic/multi/three_agents_default.yaml \
  "Question"
# ✓ Works (backwards compatible)

# New style works too
uv run python -m massgen.cli \
  --config @examples/basic_multi \
  "Question"
# ✓ Works
```

### For Python Users

```python
import massgen

# Simple API works
result = await massgen.run("Question", model="gemini-2.5-flash")
# ✓ Returns dict with answer

# Config examples work
result = await massgen.run("Question", config="@examples/basic_multi")
# ✓ Returns dict with answer
```

---

## What We're NOT Changing

1. ❌ No directory restructuring
2. ❌ No refactoring of core logic
3. ❌ No changes to YAML schema
4. ❌ No changes to existing CLI behavior (only additions)
5. ❌ No changes to agent coordination logic
6. ❌ No changes to backend implementations

**Philosophy:** Add PyPI-friendly features without breaking existing functionality.

---

## Open Questions

### 1. Example Config Shortcuts

How should we map `@examples/NAME` to actual files?

**Current structure:**
```
massgen/configs/basic/multi/three_agents_default.yaml
```

**Option A: Fuzzy matching**
```bash
@examples/basic_multi
# Searches for files containing "basic_multi"
# Matches: basic/multi/*.yaml
```

**Option B: Explicit shortcuts**
```python
SHORTCUTS = {
    'basic_multi': 'basic/multi/three_agents_default.yaml',
    'basic_single': 'basic/single/single_gpt5nano.yaml'
}
```

**Recommendation:** A (fuzzy) - less maintenance, more flexible

### 2. Config Builder Presets

What preset options should the wizard offer?

**Proposed:**
1. **Research Team** - Gemini + GPT + Grok, web search enabled
2. **Coding Team** - Claude Code + GPT, file operations
3. **Single Agent** - Claude Sonnet 4, simple & fast
4. **Skip** - Use temporary config (no save)

### 3. Return Format for Python API

What should `massgen.run()` return?

**Option A: Rich dict**
```python
{
    'final_answer': "The answer...",
    'winner_agent_id': "agent_1",
    'coordination_rounds': 3,
    'agent_responses': {...},
    'duration_seconds': 45.2
}
```

**Option B: Simple string**
```python
"The answer..."
```

**Recommendation:** A (dict) - more useful, can add metadata later

---

## Next Steps

1. Review and approve this design
2. Start Phase 1 (config resolution)
3. Test incrementally after each phase
4. Get early feedback from users
5. Iterate and polish
6. Release v0.0.33 to PyPI

---

## Appendix: Motivation

### Why This Design?

**Problem:** After `pip install massgen`, docs examples fail because `massgen/configs/` doesn't exist.

**Current user confusion:**
```bash
# Docs say:
massgen --config massgen/configs/basic/multi/three_agents_default.yaml

# User types:
massgen --config massgen/configs/basic/multi/three_agents_default.yaml
# FileNotFoundError!

# User thinks: "Where are the configs? Do I need to git clone?"
```

**Solution:** Ship configs with package, add `@examples/` syntax

**After this design:**
```bash
pip install massgen
massgen --config @examples/basic_multi "Question"
# Works!
```

### Design Principles

1. **Minimal disruption** - No restructuring, just additions
2. **Backwards compatible** - Old workflows still work
3. **Progressive disclosure** - Simple API, advanced features optional
4. **Convention over configuration** - Smart defaults, override when needed
5. **Fail gracefully** - Clear error messages with solutions

---

**End of Design Document**
