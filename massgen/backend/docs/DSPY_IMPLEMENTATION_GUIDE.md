# DSPy Implementation Guide for MassGen

## Table of Contents
1. [Quick Start](#quick-start)
2. [What is DSPy in MassGen?](#what-is-dspy-in-massgen)
3. [How DSPy Works](#how-dspy-works)
4. [Configuration Reference](#configuration-reference)
5. [Configuration Example](#configuration-example)
6. [Troubleshooting](#troubleshooting)
7. [Summary](#summary)

---

## Quick Start

### 5-Minute Setup

**1. Ensure DSPy is installed:**
```bash
pip install 'dspy>=2.4.0'
```

**2. Set your API key:**
```bash
export GOOGLE_API_KEY="your-gemini-api-key"
# OR
export OPENAI_API_KEY="your-openai-api-key"
```

**3. Create a config file (e.g., `my_config.yaml`):**
```yaml
agents:
  - id: "agent1"
    backend:
      type: "gemini"
      model: "gemini-2.5-flash"

  - id: "agent2"
    backend:
      type: "openai"
      model: "gpt-4o-mini"

orchestrator:
  dspy:
    enabled: true
    backend:
      type: "gemini"
      model: "gemini-2.5-flash"
      temperature: 0.7
    num_variants: 2
    strategy: "balanced"
```

**4. Run MassGen:**
```bash
massgen --config my_config.yaml "Explain quantum computing"
```

**5. Observe the output:**
You'll see logs indicating DSPy paraphrasing is active:
```
✅ DSPy question paraphrasing enabled (strategy=balanced, variants=2)
 DSPy paraphrasing enabled: 2 variant(s) generated and assigned to 2 agent(s)
```

Each agent will receive a paraphrased version of your question!

---

## What is DSPy in MassGen?

DSPy is integrated into MassGen to provide **intelligent question paraphrasing** for multi-agent coordination. When enabled, DSPy generates semantically equivalent but differently worded versions of user questions, which are then distributed to different agents.

### Why Use DSPy?

- **Diverse Agent Perspectives**: Each agent receives a unique paraphrase, encouraging different interpretations
- **Semantic Equivalence**: All paraphrases maintain the exact meaning of the original question
- **Better Coverage**: Linguistic variations help agents explore the problem space more thoroughly
- **Automatic Validation**: Built-in semantic validation ensures paraphrases ask for the same information

---

## How DSPy Works

### Visual Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: User Provides Question                                  │
│ "Explain quantum computing"                                     │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: Configuration Loaded                                    │
│ - MassGen reads orchestrator.dspy section from YAML            │
│ - Creates DSPy Language Model (Gemini/OpenAI/Claude/etc)       │
│ - Initializes QuestionParaphraser with settings                │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: Generate Paraphrase Variants                            │
│ - QuestionParaphraser generates N variants using DSPy           │
│ - Each variant uses different temperature for diversity         │
│                                                                 │
│ Example outputs:                                                │
│   Variant 1: "Can you explain what quantum computing is?"      │
│   Variant 2: "What is quantum computing and how does it work?" │
│   Variant 3: "Please describe quantum computing principles"    │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 4: Validate Each Variant                                   │
│ - Semantic check: Does it ask for the same information?        │
│ - Quality check: Appropriate length, word variation, etc.      │
│ - If validation fails: Generate replacement or use fallback    │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 5: Assign Paraphrases to Agents                            │
│ - Round-robin assignment: Agent1→Variant1, Agent2→Variant2     │
│ - If more agents than variants: Paraphrases cycle              │
│ - Each agent gets: ORIGINAL + assigned PARAPHRASE              │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 6: Agents Process Questions                                │
│ - Each agent sees both original and paraphrased version        │
│ - Paraphrase influences interpretation and response            │
│ - Agents work in parallel                                       │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 7: Orchestrator Combines Results                           │
│ - All agent responses aggregated                               │
│ - User receives diverse perspectives from varied interpretations│
└─────────────────────────────────────────────────────────────────┘
```

### Key Components

**1. QuestionParaphraser** (`massgen/dspy_paraphraser.py`)
- Core class that handles paraphrasing using DSPy
- Generates variants, validates them, manages caching
- Uses DSPy signatures for paraphrase generation and validation

**2. CLI Integration** (`massgen/cli.py`)
- Loads DSPy configuration from YAML
- Creates DSPy Language Model from backend config
- Initializes QuestionParaphraser and passes to Orchestrator

**3. Orchestrator** (`massgen/orchestrator.py`)
- Calls QuestionParaphraser to generate variants
- Assigns paraphrases to agents in round-robin fashion
- Handles fallback if paraphrasing fails

**4. Message Templates** (`massgen/message_templates.py`)
- Formats messages to include both original and paraphrased question
- Agents receive: `<ORIGINAL MESSAGE>...<PARAPHRASED MESSAGE>...`

### What Happens Behind the Scenes

**Caching:**
- Paraphrases are cached based on question + configuration
- Repeated questions return instantly from cache
- Cache is in-memory (cleared when process ends)

**Validation:**
- Semantic validation uses DSPy to verify paraphrase asks same thing
- Quality checks: length ratio, word overlap, uniqueness
- Failed paraphrases are regenerated or replaced

**Fallback Mechanisms:**
- If DSPy fails to generate enough variants: template-based fallbacks
- If all generation fails: agents receive original question
- System never blocks due to paraphrasing issues

**Temperature Scheduling:**
- Different strategies use different temperature schedules
- Ensures diversity across variants (unless fixed temperature set)
- Example: "diverse" strategy uses [0.3, 0.6, 0.9] temperatures

---

## Configuration Reference

### Main DSPy Configuration Variables

All variables go under `orchestrator.dspy` in your config file:

| Variable | Type | Options/Values | Default | Required? | Description |
|----------|------|----------------|---------|-----------|-------------|
| `enabled` | boolean | `true`, `false` | `false` | ✅ **Yes** | Enable or disable DSPy paraphrasing |
| `backend` | object | Backend config object | - | ✅ **Yes** | Configuration for DSPy language model |
| `num_variants` | integer | `>= 1` (1-10 recommended) | `3` | No | Number of paraphrase variants to generate (no hard cap enforced) |
| `strategy` | string | `balanced`, `diverse`, `conservative`, `adaptive` | `balanced` | No | Paraphrasing strategy (see table below) |
| `cache_enabled` | boolean | `true`, `false` | `true` | No | Enable caching of paraphrases for repeated questions |
| `semantic_threshold` | float | `0.0` to `1.0` | `0.85` | No | Minimum semantic similarity score for validation |
| `use_chain_of_thought` | boolean | `true`, `false` | `false` | No | Use ChainOfThought module (higher quality, higher cost) |
| `validate_semantics` | boolean | `true`, `false` | `true` | No | Validate that paraphrases ask for same information |
| `temperature_range` | array | `[min, max]` floats `0.0-2.0` | `[0.3, 0.9]` | No | Temperature range for dynamic scheduling per strategy (ignored if backend.temperature is set). Strategies calculate specific temps from this range. |

### Backend Configuration Variables

Variables under `orchestrator.dspy.backend`:

| Variable | Type | Options/Values | Default | Required? | Description |
|----------|------|----------------|---------|-----------|-------------|
| `type` | string | See provider types below | - | ✅ **Yes** | LLM provider type |
| `model` | string | Any valid model name for provider | - | ✅ **Yes** | Model to use for paraphrasing |
| `api_key` | string | Your API key string | From env var | No | API key (falls back to environment variable) |
| `base_url` | string | Custom endpoint URL | Provider default | No | Custom API endpoint (for local servers) |
| `temperature` | float | `0.0` to `2.0` | From strategy | No | Fixed temperature for all variants (overrides temperature_range and disables dynamic temperature scheduling) |
| `max_tokens` | integer | `1` to `4096+` | Provider default | No | Maximum tokens for paraphrase generation |
| `top_p` | float | `0.0` to `1.0` | Provider default | No | Nucleus sampling parameter |

### Supported Provider Types

| Provider Type | Maps To | API Key Env Var | Notes |
|--------------|---------|-----------------|-------|
| `openai` | OpenAI API | `OPENAI_API_KEY` | Standard OpenAI models |
| `anthropic` | Anthropic API | `ANTHROPIC_API_KEY` | Claude models |
| `claude` | Anthropic API | `ANTHROPIC_API_KEY` | Alias for anthropic |
| `gemini` | Google Gemini | `GOOGLE_API_KEY` or `GEMINI_API_KEY` | Google's Gemini models |
| `chatcompletion` | OpenAI-compatible | `OPENAI_API_KEY` | Generic OpenAI-compatible endpoint |
| `lmstudio` | OpenAI-compatible | - | Local LMStudio server (default: `http://localhost:1234/v1`) |
| `vllm` | OpenAI-compatible | - | Local vLLM server (default: `http://localhost:8000/v1`) |
| `sglang` | OpenAI-compatible | - | Local SGLang server (default: `http://localhost:30000/v1`) |
| `cerebras` | OpenAI-compatible | `CEREBRAS_API_KEY` | Cerebras Cloud API |

### Paraphrasing Strategies

| Strategy | Best For | Temperature Behavior | Variation Level | Example Use Case |
|----------|----------|---------------------|-----------------|------------------|
| `balanced` | General use (default) | Medium temps `[0.5, 0.6, 0.7]` | Moderate | Standard multi-agent queries |
| `diverse` | Maximum variation | Low→High `[0.3, 0.6, 0.9]` | High | Exploring problem space thoroughly |
| `conservative` | Precision critical | Low temps `[0.3, 0.4, 0.5]` | Minimal | Technical/scientific questions |
| `adaptive` | Mixed question types | Wide range `[0.3, 0.5, 0.7, 0.9]` | High (static spread) | Production with varied inputs |

**Strategy Details:**

- **balanced**: Natural rephrasing with moderate variation. Good default choice.
- **diverse**: Generates significantly different phrasings. Use when you want maximum linguistic diversity.
- **conservative**: Minimal structural changes, stays close to original. Use for technical accuracy.
- **adaptive**: Uses a wider temperature spread and a generic prompt suited for varied inputs. Good when you want both low and high temperature paraphrases.

### Understanding Temperature Behavior

DSPy uses temperatures to control diversity across paraphrase variants. Here's how it works:

**Scenario 1: No temperature specified (Default)**
- Uses `temperature_range: [0.3, 0.9]` (default)
- Each strategy calculates temperatures from this range
- Example with balanced strategy:
  - min = 0.3, max = 0.9, mid = 0.6
  - Temps: [mid-0.1, mid, mid+0.1] = [0.5, 0.6, 0.7]

**Scenario 2: Custom temperature_range specified**
```yaml
temperature_range: [0.5, 1.0]  # Custom range
```
- Strategies adapt to YOUR range
- Example with diverse strategy:
  - min = 0.5, max = 1.0, mid = 0.75
  - Temps: [min, mid, max] = [0.5, 0.75, 1.0]

**Scenario 3: Fixed backend.temperature specified**
```yaml
backend:
  temperature: 0.7  # Fixed value
```
- **Overrides temperature_range completely**
- All variants use 0.7 (no diversity from temperature)
- Diversity comes only from DSPy's text generation randomness

**Temperature Calculation Formulas by Strategy:**

| Strategy | Formula | Example (range [0.3, 0.9]) | Example (range [0.5, 1.0]) |
|----------|---------|---------------------------|---------------------------|
| `balanced` | [mid-0.1, mid, mid+0.1] | [0.5, 0.6, 0.7] | [0.65, 0.75, 0.85] |
| `diverse` | [min, mid, max] | [0.3, 0.6, 0.9] | [0.5, 0.75, 1.0] |
| `conservative` | [min, min+0.1, min+0.2] | [0.3, 0.4, 0.5] | [0.5, 0.6, 0.7] |
| `adaptive` | [min, min+0.2, max-0.2, max] | [0.3, 0.5, 0.7, 0.9] | [0.5, 0.7, 0.8, 1.0] |

Where: `mid = (min + max) / 2`

> **Note:** The `balanced` strategy offsets the midpoint by ±0.1 regardless of the supplied range, so with very narrow ranges those values can extend slightly outside your exact `[min, max]`. If you need strict bounds, set a fixed `backend.temperature` instead.

**Recommendation:**
- For most cases: Use default temperature_range, let strategies control diversity
- For fine control: Set custom temperature_range
- For consistent temperature: Set backend.temperature (but reduces variant diversity)

### Environment Variables

DSPy will automatically look for API keys in these environment variables if not provided in config:

| Provider | Environment Variable(s) |
|----------|------------------------|
| OpenAI | `OPENAI_API_KEY` |
| Anthropic/Claude | `ANTHROPIC_API_KEY` |
| Google Gemini | `GOOGLE_API_KEY` or `GEMINI_API_KEY` |
| Cerebras | `CEREBRAS_API_KEY` |

**Set environment variables:**
```bash
# Linux/Mac
export OPENAI_API_KEY="sk-..."

# Windows (Command Prompt)
set OPENAI_API_KEY=sk-...

# Windows (PowerShell)
$env:OPENAI_API_KEY="sk-..."
```

---

## Configuration Example

### Comprehensive Annotated Example

```yaml
agents:
  - id: "agent1"
    backend:
      type: "gemini"
      model: "gemini-2.5-flash"

  - id: "agent2"
    backend:
      type: "openai"
      model: "gpt-4o-mini"

  - id: "agent3"
    backend:
      type: "claude"
      model: "claude-3-5-sonnet-20241022"

orchestrator:
  snapshot_storage: "snapshots"
  agent_temporary_workspace: "temp_workspaces"

  # ============================================================
  # DSPy Question Paraphrasing Configuration
  # ============================================================
  dspy:
    # -------------------- Required Settings --------------------
    enabled: true                         # Enable DSPy paraphrasing

    backend:                              # DSPy language model config
      type: "gemini"                      # Provider: openai|anthropic|gemini|lmstudio|vllm|sglang|cerebras|chatcompletion
      model: "gemini-2.5-flash"           # Model name (gemini-2.5-flash is fast & cheap)

      # Optional: Uncomment to override defaults
      # api_key: "your-api-key"           # Or use GOOGLE_API_KEY env var
      # base_url: "https://..."           # Custom endpoint (for local servers)
      # temperature: 0.7                  # Fixed temp (overrides temperature_range below)
      # max_tokens: 150                   # Limit paraphrase length
      # top_p: 0.9                        # Nucleus sampling

    # -------------------- Paraphrasing Settings --------------------
    num_variants: 3                       # Generate 3 paraphrases (any positive integer works; 1-10 recommended)
    strategy: "balanced"                  # balanced|diverse|conservative|adaptive

    # -------------------- Advanced Settings (Optional) --------------------
    cache_enabled: true                   # Cache paraphrases (faster repeated queries)
    semantic_threshold: 0.85              # Validation strictness (0.0-1.0, higher=stricter)
    use_chain_of_thought: false           # true = better quality but higher cost
    validate_semantics: true              # Verify paraphrases ask same thing
    temperature_range: [0.3, 0.9]         # Temperature range (ignored if temperature set)

ui:
  display_type: "rich_terminal"
  logging_enabled: true
```

### Example: Using Local LLM (LMStudio)

```yaml
orchestrator:
  dspy:
    enabled: true
    backend:
      type: "lmstudio"                    # Local LMStudio server
      model: "your-local-model"           # Model loaded in LMStudio
      base_url: "http://localhost:1234/v1"  # Default LMStudio endpoint
      temperature: 0.6
    num_variants: 3
    strategy: "balanced"
```

### Example: Cost-Optimized Configuration

```yaml
orchestrator:
  dspy:
    enabled: true
    backend:
      type: "openai"
      model: "gpt-4o-mini"                # Cheaper model
      temperature: 0.7
      max_tokens: 100                     # Limit response size
    num_variants: 2                       # Fewer variants = fewer API calls
    strategy: "conservative"              # Less variation = more reliable
    use_chain_of_thought: false           # Standard Predict (cheaper than ChainOfThought)
    cache_enabled: true                   # Cache aggressively
```

### Example: High-Quality Configuration

```yaml
orchestrator:
  dspy:
    enabled: true
    backend:
      type: "openai"
      model: "gpt-4o"                     # More powerful model
      temperature: 0.7
      max_tokens: 200
    num_variants: 4                       # More variants
    strategy: "diverse"                   # Maximum variation
    use_chain_of_thought: true            # Better reasoning
    semantic_threshold: 0.90              # Stricter validation
    validate_semantics: true
```

---

## Troubleshooting

### Installation Issues

**Error:** `DSPy is not installed`

**Solution:**
```bash
pip install 'dspy>=2.4.0'
```

Check that DSPy version is 2.4.0 or higher:
```bash
pip show dspy
```

---

### Backend Configuration Issues

**Error:** `Unsupported backend type 'xyz' for DSPy`

**Solution:** Use one of the supported backend types:
- `openai`, `anthropic`, `claude`, `gemini`
- `chatcompletion`, `lmstudio`, `vllm`, `sglang`, `cerebras`

**Error:** `Model name required for backend type`

**Solution:** Add `model` to your backend config:
```yaml
backend:
  type: "gemini"
  model: "gemini-2.5-flash"  # Required
```

---

### API Key Problems

**Error:** `Failed to create DSPy LM: API key required`

**Solution:** Either add API key to config or set environment variable:

**Option 1: Config file**
```yaml
backend:
  type: "openai"
  model: "gpt-4o-mini"
  api_key: "sk-..."
```

**Option 2: Environment variable**
```bash
# OpenAI
export OPENAI_API_KEY="sk-..."

# Anthropic
export ANTHROPIC_API_KEY="sk-ant-..."

# Gemini
export GOOGLE_API_KEY="..."
```

---

### Paraphrase Generation Failures

**Warning:** `Failed to generate DSPy paraphrases: <error>`

**What happens:** System falls back to using original question for all agents. Orchestration continues normally.

**Solutions:**
1. Check backend connectivity and model availability
2. Verify API key is valid and has credits
3. Try a different model or provider
4. Check logs for specific error details

---

### Low Quality Paraphrases

**Problem:** Paraphrases are too similar to original or don't make sense

**Solutions:**

1. **Use "diverse" strategy** for more variation:
```yaml
strategy: "diverse"
```

2. **Increase semantic threshold** for stricter validation:
```yaml
semantic_threshold: 0.90
```

3. **Enable ChainOfThought** for better reasoning (costs more):
```yaml
use_chain_of_thought: true
```

4. **Adjust temperature range** for more diversity:
```yaml
temperature_range: [0.5, 1.0]
```

---

### High API Costs

**Solutions to reduce costs:**

1. **Use cheaper model:**
```yaml
backend:
  type: "openai"
  model: "gpt-4o-mini"  # Instead of gpt-4
```

2. **Disable ChainOfThought:**
```yaml
use_chain_of_thought: false
```

3. **Enable caching:**
```yaml
cache_enabled: true
```

4. **Reduce variants:**
```yaml
num_variants: 2  # Instead of 3 or more
```

5. **Set max_tokens limit:**
```yaml
backend:
  max_tokens: 100
```

6. **Use local LLM:**
```yaml
backend:
  type: "lmstudio"
  model: "your-local-model"
  base_url: "http://localhost:1234/v1"
```

---

### Timeout Issues

**Error:** `Paraphrase generation error: timeout`

**What happens:** DSPy has 60-second timeout with 3 retries by default.

**Solutions:**
1. Check network connection
2. Try a faster model (e.g., `gemini-2.5-flash`, `gpt-4o-mini`)
3. Reduce `max_tokens` if set very high
4. Try a different provider

---

### Debug Logging

To see detailed DSPy activity:

```bash
# Set logging level
export MASSGEN_LOG_LEVEL=DEBUG

# Run with verbose logging
massgen --config your_config.yaml "your question"
```

Check logs for:
- `✅ DSPy question paraphrasing enabled` - Initialization successful
- ` DSPy paraphrasing enabled: N variant(s) generated` - Generation successful
- Warning/error messages with details

---

## Summary

DSPy is integrated into MassGen as an **intelligent question paraphrasing system** that enhances multi-agent coordination by providing diverse linguistic perspectives.

### What It Does

1. **Generates** semantically equivalent question variants using DSPy language models
2. **Validates** paraphrases for semantic equivalence and quality
3. **Assigns** paraphrases to agents to encourage diverse interpretations
4. **Caches** results for performance optimization
5. **Falls back** gracefully when generation fails

### How to Enable

Add to your config file:

```yaml
orchestrator:
  dspy:
    enabled: true
    backend:
      type: "gemini"
      model: "gemini-2.5-flash"
      temperature: 0.7
    num_variants: 3
    strategy: "balanced"
```

### Key Configuration Options

- **Backend providers:** OpenAI, Anthropic, Gemini, local LLMs (LMStudio/vLLM/SGLang)
- **Strategies:** balanced (default), diverse, conservative, adaptive
- **Quality controls:** semantic validation, temperature scheduling, quality checks
- **Performance:** caching, fallback mechanisms, configurable variants

### When to Use

- ✅ Multi-agent systems where diverse perspectives are valuable
- ✅ Complex queries that benefit from multiple interpretations
- ✅ Scenarios where linguistic variation might uncover different aspects
- ❌ Not needed for single-agent setups or simple factual queries

The implementation is production-ready with comprehensive error handling, quality validation, and performance optimizations. For issues or questions, check the Troubleshooting section or review the logs for detailed debugging information.
