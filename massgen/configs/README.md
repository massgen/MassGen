# MassGen Configuration Guide

This guide explains the organization and usage of MassGen configuration files.

## Directory Structure

```
massgen/configs/
├── basic/                 # Simple configs to get started
│   ├── single/           # Single agent examples
│   └── multi/            # Multi-agent examples
├── tools/                 # Tool-enabled configurations
│   ├── mcp/              # MCP server integrations
│   ├── web-search/       # Web search enabled configs
│   ├── code-execution/   # Code interpreter/execution
│   └── filesystem/       # File operations & workspace
├── providers/             # Provider-specific examples
│   ├── openai/           # GPT-5 series configs
│   ├── claude/           # Claude API configs
│   ├── gemini/           # Gemini configs
│   ├── azure/            # Azure OpenAI
│   ├── local/            # LMStudio, local models
│   └── others/           # Cerebras, Grok, Qwen, ZAI
├── teams/                # Pre-configured specialized teams
│   ├── creative/         # Creative writing teams
│   ├── research/         # Research & analysis
│   └── development/      # Coding teams
└── docs/                 # Setup guides and documentation
```

## CLI Command Line Arguments

| Parameter          | Description |
|-------------------|-------------|
| `--config`         | Path to YAML configuration file with agent definitions, model parameters, backend parameters and UI settings |
| `--backend`        | Backend type for quick setup without a config file (`claude`, `claude_code`, `gemini`, `grok`, `openai`, `azure_openai`, `zai`). Optional for [models with default backends](../utils.py).|
| `--model`          | Model name for quick setup (e.g., `gemini-2.5-flash`, `gpt-5-nano`, ...). `--config` and `--model` are mutually exclusive - use one or the other. |
| `--system-message` | System prompt for the agent in quick setup mode. If `--config` is provided, `--system-message` is omitted. |
| `--no-display`     | Disable real-time streaming UI coordination display (fallback to simple text output).|
| `--no-logs`        | Disable real-time logging.|
| `--debug`          | Enable debug mode with verbose logging (NEW in v0.0.13). Shows detailed orchestrator activities, agent messages, backend operations, and tool calls. Debug logs are saved to `agent_outputs/log_{time}/massgen_debug.log`. |
| `"<your question>"`         | Optional single-question input; if omitted, MassGen enters interactive chat mode. |

## Quick Start Examples

### 🌟 Recommended Showcase Example

**Best starting point for multi-agent collaboration:**
```bash
# Three powerful agents (Gemini, GPT-5, Grok) with enhanced workspace tools
massgen --config @examples/basic/multi/three_agents_default "Your complex task"
```

This configuration combines:
- **Gemini 2.5 Flash** - Fast, versatile with web search
- **GPT-5 Nano** - Advanced reasoning with code interpreter
- **Grok-3 Mini** - Efficient with real-time web search

### Quick Setup Without Config Files

**Single agent with model name only:**
```bash
# Quick test with any supported model - no configuration needed
massgen --model claude-3-5-sonnet-latest "What is machine learning?"
massgen --model gemini-2.5-flash "Explain quantum computing"
massgen --model gpt-5-nano "Summarize the latest AI developments"
```

**Interactive Mode:**
```bash
# Start interactive chat (no initial question)
massgen --config @examples/basic/multi/three_agents_default

# Debug mode for troubleshooting
massgen --config @examples/basic/multi/three_agents_default --debug "Your question"
```

### Basic Usage

For simple single-agent setups:
```bash
massgen --config @examples/basic/single/single_agent "Your question"
```

### Tool-Enabled Configurations

#### MCP (Model Context Protocol) Servers
MCP enables agents to use external tools and services:
```bash
# Weather queries
massgen --config @examples/tools/mcp/gemini_mcp_example "What's the weather in Tokyo?"

# Discord integration
massgen --config @examples/tools/mcp/claude_code_discord_mcp_example "Extract latest messages"
```

#### Web Search
For agents with web search capabilities:
```bash
massgen --config @examples/tools/web-search/claude_streamable_http_test "Search for latest news"
```

#### Code Execution
For code interpretation and execution:
```bash
massgen --config @examples/tools/code-execution/multi_agent_playwright_automation \
  "Browse three issues in https://github.com/Leezekun/MassGen and suggest documentation improvements. Include screenshots and suggestions in a website."
```

#### Filesystem Operations
For file manipulation, workspace management, and copy tools:
```bash
# Single agent with enhanced file operations
massgen --config @examples/tools/filesystem/claude_code_single "Analyze this codebase"

# Multi-agent workspace collaboration with copy tools (NEW in v0.0.22)
massgen --config @examples/tools/filesystem/claude_code_context_sharing "Create shared workspace files"
```

### Provider-Specific Examples

Each provider has unique features and capabilities:

#### OpenAI (GPT-5 Series)
```bash
massgen --config @examples/providers/openai/gpt5 "Complex reasoning task"
```

#### Claude
```bash
massgen --config @examples/providers/claude/claude_mcp_example "Creative writing task"
```

#### Gemini
```bash
massgen --config @examples/providers/gemini/gemini_mcp_example "Research task"
```

#### Local Models
```bash
massgen --config @examples/providers/local/lmstudio "Run with local model"
```

### Pre-Configured Teams

Teams are specialized multi-agent setups for specific domains:

#### Creative Teams
```bash
massgen --config @examples/teams/creative/creative_team "Write a story"
```

#### Research Teams
```bash
massgen --config @examples/teams/research/research_team "Analyze market trends"
```

#### Development Teams
```bash
massgen --config @examples/teams/development/zai_coding_team "Build a web app"
```

## Configuration File Format

### Single Agent
```yaml
agent:
  id: "agent_name"
  backend:
    type: "provider_type"
    model: "model_name"
    # Additional backend settings
  system_message: "Agent instructions"

ui:
  display_type: "rich_terminal"
  logging_enabled: true
```

### Multi-Agent
```yaml
agents:
  - id: "agent1"
    backend:
      type: "provider1"
      model: "model1"
    system_message: "Agent 1 role"

  - id: "agent2"
    backend:
      type: "provider2"
      model: "model2"
    system_message: "Agent 2 role"

ui:
  display_type: "rich_terminal"
  logging_enabled: true
```

### MCP Server Configuration
```yaml
backend:
  type: "provider"
  model: "model_name"
  mcp_servers:
    server_name:
      type: "stdio"
      command: "command"
      args: ["arg1", "arg2"]
      env:
        KEY: "${ENV_VAR}"
```

## Finding the Right Configuration

1. **New Users**: Start with `basic/single/` or `basic/multi/`
2. **Need Tools**: Check `tools/` subdirectories for specific capabilities
3. **Specific Provider**: Look in `providers/` for your provider
4. **Complex Tasks**: Use pre-configured `teams/`

## Environment Variables

Most configurations use environment variables for API keys:so
- Set up your `.env` file based on `.env.example`
- Provider-specific keys: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.
- MCP server keys: `DISCORD_BOT_TOKEN`, `BRAVE_API_KEY`, etc.

## Release History & Examples

### v0.1.96 - Latest
**OS-Level Agent Sandboxing:** Real OS-level execution sandbox (Anthropic sandbox-runtime) + hardened permission hook, defense in depth

**Key Features:**
- **SRT sandbox mode** (`command_line_execution_mode: srt`): wraps agent command/code execution in `srt` (bubblewrap on Linux, Seatbelt on macOS); OS-enforced filesystem + network isolation derived from the same path policy as the app layer. One-knob opt-in, default-off
- **Configurable read confinement** (`command_line_srt_read_mode`, default `confined`): denies `$HOME` and re-allows only the workspace + context; `strict` / `open` modes available. Network is deny-all by default
- **Hardened permission hook**: key-agnostic scan walks the full tool-args tree and denies any value resolving outside managed areas, closing prior fail-open gaps without false positives
- **Parity & safety**: native-sandbox backends (Codex `--full-auto`, Claude Code) degrade `srt`→`local`; subagents inherit parent SRT settings

**Try It:**
```bash
pip install massgen==0.1.96

# Prerequisite (one-time): npm install -g @anthropic-ai/sandbox-runtime
uv run massgen --automation \
  --config massgen/configs/tools/filesystem/sandbox/srt_sandbox.yaml \
  "Create out.txt in the workspace, then try to read ~/.ssh/id_rsa"
# Expected: the workspace write succeeds; reading ~/.ssh and all network egress are denied.
```

### v0.1.95
**Steering Improvements:** Existing mid-stream steering extended to headless callers + upgraded to interrupt-and-resume

**Key Features:**
- **Programmatic steering inbox** (`--inbox-dir`): drop human guidance into a streaming `--automation` run via `send_steering_message()`; routed to the same chokepoint the TUI/WebUI use, with per-message targeting
- **Interrupt-and-resume (Codex & Antigravity)**: steering mid-turn now kills the in-flight turn and resumes (`codex exec resume` / `agy --continue`) instead of waiting for a round boundary
- **MCP-server-hook payload IPC**: Antigravity gains codex-parity mid-stream injection through the MCP middleware, with `expires_at`-guarded payloads
- **Antigravity `--model`**: the model label is now actually passed to `agy`

**Try It:**
```bash
pip install massgen==0.1.95

# Headless steering: start a run, then drop a message mid-stream
uv run massgen --automation --inbox-dir /tmp/inbox \
  --config massgen/configs/debug/codex_mcp_middleware_test.yaml "Write and refine a short essay."
# in another shell:
python -c "from massgen.steering import send_steering_message; send_steering_message('/tmp/inbox', 'prioritize concision')"
```

### v0.1.93
**Internal-Quality Release:** CLI Package Decomposition & Pydantic Config Migration

**Key Changes:**
- **CLI Package Decomposition**: The monolithic `cli.py` (12,206 lines) is split into a focused `massgen/cli/` package while preserving the public import surface
- **Pydantic Config Migration**: Config classes validate field types on construction, with `Literal`-typed modes as a single source of truth the validator derives from
- **Dead Code Removal & Tooling**: Removed ~8.7k lines of unreferenced legacy code, fixed the coverage gate, and re-enabled type checking via an incremental mypy ratchet

No new configuration files — this release preserves runtime behavior. All 282 bundled configs continue to validate.

**Install:**
```bash
pip install massgen==0.1.93
```

### v0.1.92
**New Features:** Orchestrator Collaborator Refactor & Parallel Search MCP

**Key Features:**
- **Orchestrator Collaborators**: `orchestrator.py` is split into 49 lazy collaborators with stable delegator call sites
- **Textual Display Cleanup**: Provider/model helpers, terminal capability probing, and widget-debug helpers moved into focused sibling modules
- **Parallel Web Search MCP**: New `parallel_search` registry entry and runnable example config for Parallel's hosted Search MCP server
- **Characterization Coverage**: New orchestrator and Textual display tests pin public contracts and extraction seams

**Try It:**
```bash
pip install massgen==0.1.92
uv run massgen --config massgen/configs/tools/web-search/parallel_search_example.yaml "Research the latest advances in multi-agent AI systems"
```

### v0.1.91
**New Features:** Config Reliability & Hook Safety

**Key Features:**
- **Centralized Config Wiring**: Coordination, timeout, and top-level orchestrator runtime settings parse through single source-of-truth helpers
- **Config Drift Detection**: Unknown release-critical YAML keys produce validation warnings, and strict validation treats them as release blockers
- **Checklist Runtime Controls**: `max_checklist_calls_per_round` and `checklist_first_answer` now flow through the centralized runtime helper
- **Native Hook Permission Safety**: Gemini CLI and Codex standalone hooks enforce nested protected/read-only paths before broader writable parents

**Try It:**
```bash
pip install massgen==0.1.91
uv run massgen --config massgen/configs/features/fast_iteration.yaml "Create an svg of an AI agent coding."
```

### v0.1.90
**New Features:** Discriminative Criteria Refinements & Checklist Calibration

**Key Features:**
- **Discriminative-Power Pruning**: Bootstrap criteria compute score spread across agents and demote non-discriminative criteria to `stretch`
- **Criterion Feedback Loop**: Checklist reasoning is carried into the next round as targeted criterion feedback
- **Position-Bias Calibration**: Candidate ordering rotates per scoring agent, and equal aggregate scores break deterministically
- **Unified Checklist Gate**: `ChecklistGate.from_budget(...)` keeps required-true count and confidence cutoff on one 0-10 scale
- **Fast-Iteration Config Updates**: `fast_iteration.yaml` now defaults to local command execution and current Gemini + Codex pairings

**Try It:**
```bash
pip install massgen==0.1.90
uv run massgen --config massgen/configs/features/fast_iteration.yaml "Create an svg of an AI agent coding."
```

### v0.1.89
**New Features:** Antigravity CLI Full Integration & Hardening

**Key Features:**
- **Workflow-Mode Parity**: Antigravity now mirrors Gemini CLI's `new_answer` / `vote` workflow handling, including `new_answer_only` rounds and post-evaluation guards
- **Auth and Binary Health Checks**: The backend verifies `agy --version` and fails fast when no API-key or cached Google OAuth credentials are available
- **Workspace Write Reliability**: MassGen passes `--add-dir <cwd>` and creates a workspace-root `.antigravitycli/` marker so agy writes files into the shared workspace
- **Native Hooks**: Antigravity hooks now use standalone `hooks.json` plus `enableJsonHooks`
- **Prompt Guardrails**: `TaskContextSection` hides `spawn_subagents` when subagents are disabled

**Try It:**
```bash
pip install massgen==0.1.89
curl -fsSL https://antigravity.google/cli/install.sh | bash
uv run massgen --config massgen/configs/features/fast_iteration_gemini_antigravity.yaml "Create an svg of an AI agent coding."
```

### v0.1.88
**New Features:** Antigravity CLI Backend

**Key Features:**
- **Antigravity CLI Backend**: New `antigravity_cli` backend wraps Google's `agy` binary as a MassGen agent backend
- **Workspace-Local Isolation**: Antigravity config and MCP settings are written under `.antigravity/` in the run workspace instead of the user's global `~/.gemini/` config
- **MCP Schema Translation**: MassGen MCP server entries are emitted using Antigravity's `mcp_config.json` schema, including `serverUrl` for HTTP servers
- **Native Hook Adapter**: Antigravity reuses Gemini CLI hook behavior via `AntigravityCLINativeHookAdapter`
- **Example Configs**: `massgen/configs/providers/antigravity/antigravity_cli_local.yaml` and `massgen/configs/features/fast_iteration_gemini_antigravity.yaml`

**Try It:**
```bash
pip install massgen==0.1.88
curl -fsSL https://antigravity.google/cli/install.sh | bash
uv run massgen --config massgen/configs/features/fast_iteration_gemini_antigravity.yaml "Create an svg of an AI agent coding."
```

### v0.1.87
**New Features:** Documentation: Framework Comparisons & `llms.txt`

**Key Features:**
- **Framework Comparison Pages**: Three new "MassGen vs ..." pages — CrewAI, LangGraph, AutoGen/AG2 — under `docs/source/reference/comparisons/`
- **`llms.txt` Index**: Curated [llmstxt.org](https://llmstxt.org)-spec index plus full-corpus `llms-full.txt` (~1 MB, 59 files) published at the docs site root
- **Landing Page Update**: "How Does MassGen Compare?" now lists all four comparisons; parent `comparisons.rst` drops "coming soon" and gains a toctree
- **`bootstrap_subagent` Single-Shot Fix**: `_run_bootstrap_discriminator_step` now passes `refine=False` to `spawn_subagent` — the canonical knob `SubagentManager` respects at the orchestrator level

**Try It:**
```bash
pip install massgen==0.1.87
# Browse the new comparisons:
# https://docs.massgen.ai/en/latest/reference/comparisons.html
```

### v0.1.86
**New Features:** `bootstrap_subagent` Discriminator + Codex MCP Approval Fix

**Key Features:**
- **`bootstrap_subagent` Variant**: Fully functional critic-driven path — the orchestrator runs a between-rounds LLM critic, merges `proposed_criteria` into the accumulator, and augments the next round's checklist automatically
- **Session-End Drain**: Late stdio criteria emissions are drained before final presentation
- **Codex MCP Approval Fix**: Non-interactive Codex workspaces write the approval bypasses needed for external MCP tools under `codex exec`
- **Example Configs**: `massgen/configs/coordination/bootstrap_subagent_criteria.yaml` and `bootstrap_inline_criteria.yaml`

### v0.1.85
**New Features:** Discriminative Criteria Emergence (`criteria_mode`)

**Key Features:**
- **`bootstrap_inline` Variant**: Fully functional on all backends with checklist tool support — agents emit `proposed_criteria` alongside `submit_checklist`, the accumulator dedupes/caps, and the next round's checklist is augmented automatically
- **`bootstrap_subagent` Variant**: Same accumulator pipeline, LLM discriminator pass queued for v0.1.86
- **Anti-Goodhart by Construction**: Criteria come from observed gaps, not priors — and no cold-start friction for new tasks
- **Cross-Backend Coverage**: SDK path (Claude Code) wires the field into the in-process tool schema; stdio backends emit through a JSONL channel drained by the orchestrator
- **Example Configs**: `massgen/configs/coordination/bootstrap_inline_criteria.yaml` and `bootstrap_subagent_criteria.yaml`

**Try It:**
```bash
pip install massgen==0.1.85
uv run massgen --config massgen/configs/coordination/bootstrap_inline_criteria.yaml "Create an SVG of an AI agent coding."
```

### v0.1.84
**New Features:** TUI Consensus Map

**Key Features:**
- **TUI Consensus Map**: Compact visual map below the agent status ribbon during multi-agent runs that summarizes coordination state without replacing the timeline. Shows one node per agent with latest answer labels, vote arrows, current vote leader, winner state, and waiting/working indicators
- **Visibility Logic**: Hidden on welcome screen and single-agent runs — only shown when more than one active agent is coordinating
- **Event-Driven State Updates**: Driven by existing coordination events without backend schema changes
- **Direct-Callback Fallback**: Map remains accurate when direct TUI callbacks update agent status or votes

### v0.1.83
**New Features:** In-Session Standalone Checkpoint MCP Integration

**Key Features:**
- **In-Session Standalone Checkpoint**: Standalone checkpoint MCP server can now run inside a normal MassGen single-agent session, exposing richer `init` + `checkpoint` tools backed by its own reviewer team
- **`coordination.standalone_checkpoint` Config Block**: New YAML block with `enabled`, `team_config`, `mode` (`generate` | `verify`), `single_checkpoint`, `include_workspace_context`; invalid `mode` falls back to `generate` with a warning
- **Single-Agent-Only Affordance Gating**: Multi-agent parents skip the standalone server with a warning
- **Enhanced Checkpoint Tool Card**: TUI tool card distinguishes primary checkpoint operations from system tasks
- **Example Configs**: `massgen/configs/checkpoint/standalone_mcp/fast_iteration.yaml` and `reviewers.yaml`

### v0.1.82
**New Features:** TUI Copy Mode & Checkpoint Quality Improvements

**Key Features:**
- **TUI Copy Mode**: New `Ctrl+Shift+S` toggle releases terminal mouse tracking so users can drag-select text natively and copy with the terminal's built-in shortcut
- **Checkpoint Workspace Context**: New `include_workspace_context` config option for the standalone checkpoint MCP server (default `false`)
- **Checkpoint Plan Quality Criteria**: Mode-aware quality criteria score selective branch depth and fallback handling in generated plans
- **Single-Checkpoint Agent Recovery**: Recovery workflow in `checkpoint_instructions.md` for when a plan branch resolves to `terminate`

### v0.1.81
**New Features:** Multi-Region Circuit Breaker Failover (Phase 6)

**Key Features:**
- **Multi-Region Failover**: LLM circuit breaker fails over to backup regions when the primary trips OPEN, with automatic recovery when the primary returns to healthy
- **Production-Grade Resilience**: Builds on Phase 4 (distributed store) and Phase 5 (adaptive thresholds)

### v0.1.80
**New Features:** Adaptive Circuit Breaker & Checkpoint Modes

**Key Features:**
- **Circuit Breaker Adaptive Thresholds (Phase 5)**: Self-tuning thresholds that respond to each backend's actual failure patterns
- **Single Checkpoint Mode**: New standalone checkpoint mode — no recheckpointing within a single operation
- **Draft Plan Verify Mode**: New standalone checkpoint mode — verify a draft plan before executing

### v0.1.79
**New Features:** Fast Mode Speed Control & Broader Checkpoint Framing

**Key Features:**
- **Better Fast Mode Options**: New options to control coordination speed — fine-grained speed vs. quality tradeoff
- **Broader Checkpoint Framing**: Checkpoint mode framing broadened from safety-only to high-stakes and coordinated phases

### v0.1.78
**New Features:** Circuit Breaker Distributed Store (Phase 4)

**Key Features:**
- **Pluggable Circuit Breaker State Store**: LLM circuit breaker state can now be shared across workers and processes via `CircuitBreakerStore` Protocol
- **In-Memory CB Store**: Thread-safe, zero-dependency implementation
- **Redis-Backed CB Store**: Distributes CB state across processes via Redis; install with `pip install massgen[redis-store]`

### v0.1.77
**New Features:** Answer Now Button

**Key Features:**
- **Answer Now Button**: Agents can submit answers more quickly, both within a round, and bypassing additional refinement rounds when quality is sufficient

### v0.1.76
**New Features:** Exa Search & Circuit Breaker Observability

**Key Features:**
- **Exa AI Search Tool**: New Exa AI-powered search tool for MCP with example config
- **Circuit Breaker Observability (Phase 3)**: Probe ownership, lock release, per-attempt latency tracking across all backends

### v0.1.75
**New Features:** Codex Hooks & Checkpoint WebUI

**Key Features:**
- **Codex Native Hooks**: Hybrid hook system for Codex backend combining native and MCP capabilities
- **Checkpoint WebUI Auto-Launch**: Checkpoint workflows auto-launch WebUI for visual monitoring

### v0.1.74
**New Features:** Checkpoint Improvements & Tool Call Fixes

**Key Features:**
- **Checkpoint MCP Improvements**: Major enhancements to the standalone checkpoint MCP server
- **Duplicate Tool Call Fix**: Resolved duplicate tool call issues in ChatCompletions and Response API backends

### v0.1.73
**New Features:** Eval Criteria Evolver & Checkpoint Objectives

**Key Features:**
- **Eval Criteria Evolver Subagent**: New subagent type that evolves evaluation criteria across rounds
- **Checkpoint Objective Mode (Initial Draft)**: Initial draft of checkpoint MCP with `objective` mode for safety planning of irreversible actions

### v0.1.72
**New Features:** Grok Backend Update & Circuit Breaker Phase 2

**Key Features:**
- **Grok Backend Update**: Updated Grok backend with latest improvements
- **Circuit Breaker Phase 2**: LLM API circuit breaker extended to ChatCompletions, Response API, and Gemini backends (was Claude-only)

### v0.1.71
**New Features:** Trace Memory & Evaluation Polish

**Key Features:**
- **Trace Analyzer Subagents**: Background trace analysis after each round — writes insights from execution traces into memory
- **Better Evaluation Criteria**: Improved criteria generation for higher-quality, more opinionated output

### v0.1.70
**New Features:** Evaluation Criteria Redesign

**Key Features:**
- **Evaluation Criteria Redesign**: Three-tier categorization (`primary`, `standard`, `stretch`) with anti-pattern definitions and aspiration statements
- **Improved Checklist-Gated Evaluation**: Tighter iterative submission cycles with improved scoring and improvement proposals
- **Fast Iteration Mode**: Streamlined multi-round submission phases via `fast_iteration.yaml`

### v0.1.69
**New Features:** WebUI Automation & Improved Skill

**Key Features:**
- **WebUI Automation Auto-Start**: Automation runs begin immediately — open the URL at any point to monitor progress mid-run
- **MassGen Skill Redesign**: Increased usability and integration with the WebUI; skill now launches the WebUI for live session tracking
- **Quickstart Wizard Rework**: New Welcome, Skills, API Key, Docker, and Setup Mode steps for smoother onboarding

### v0.1.68
**New Features:** Checkpoint Mode

**Key Features:**
- **Checkpoint Coordination Mode**: Delegator pattern — main agent plans solo then delegates to team via `checkpoint()` tool
- **WebUI Checkpoint Support**: Checkpoint mode display in the modernized WebUI
- **LiteLLM Supply Chain Fix**: Pinned litellm<=1.82.6 and committed uv.lock

**Try It:**
```bash
pip install massgen==0.1.68
# Try checkpoint mode -- click 'COORD' in the mode bar above the input then the checkpoint box
uv run massgen --web
```

### v0.1.67
**New Features:** Modernized WebUI

**Key Features:**
- **Modernized WebUI**: Complete UI redesign with inline final answers and keyboard shortcuts
- **RoundBudgetGuardHook**: Per-round cost enforcement with configurable warning thresholds
- **Unified Pre-Collab**: Personas, evaluation criteria, and prompt improvement run in parallel

### v0.1.66
**New Features:** Step Mode

**Key Features:**
- **Step Mode**: New `--step` CLI flag runs one agent for one iteration then exits
- **massgen-refinery Step Mode**: Claude Code plugin now supports step mode

### v0.1.65
**New Features:** MassGen Refinery Plugin

**Key Features:**
- **Quality Server**: Standalone `massgen_quality_tools` MCP server with session-based checklist evaluation
- **Workflow Server**: Multi-round answer submission with deliverable snapshots
- **Media Server**: Image/video/audio generation and media analysis

### v0.1.64
**New Features:** Gemini CLI Backend

**Key Features:**
- **Gemini CLI Backend**: New subprocess-based backend for Google's Gemini CLI with session persistence, MCP tools, and Docker support
- **WebSocket Mode**: Persistent WebSocket transport for OpenAI Response API with auto-reconnection
- **Execution Trace Analyzer**: New subagent type for mechanistic analysis of agent execution traces

### v0.1.63
**New Features:** Ensemble & Contracts

**Key Features:**
- **Ensemble Pattern Defaults**: `disable_injection` and `defer_voting_until_all_answered` now default to true for ensemble-style subagent orchestration
- **Transformation Pressure**: Round evaluator pushes agents toward meaningful structural changes
- **Success Contracts**: Explicit quality gates agents must satisfy before convergence

### v0.1.62
**New Features:** MassGen Skill & Viewer

**Key Features:**
- **MassGen Skill**: New general-purpose multi-agent skill with 4 modes (general, evaluate, plan, spec) for Claude Code and other AI agents
- **Session Viewer**: New `massgen viewer` command for real-time observation of automation sessions with interactive picker and web mode
- **Backend Improvements**: Claude Code background task execution, Codex native filesystem and MCP support, Copilot runtime model discovery
- **Quickstart Enhancements**: Headless quickstart for CI/CD, web quickstart for browser-based setup

### v0.1.61
**New Features:** Round Evaluator Paradigm

**Key Features:**
- **Round Evaluator Subagent Type**: New `round_evaluator` subagent type that delegates evaluation to specialized evaluator subagents for deeper quality assessment
- **Orchestrator Refactoring**: Major orchestrator refactoring (+1,189 lines) to support the round evaluation workflow
- **Evaluation Improvements**: Improved evaluation prompts with task plan injection for context-aware assessment
- **New Config**: `round_evaluator_example.yaml` for easy adoption

### v0.1.60
**New Features:** Multimodal Tools, Subagent Enhancements & GPT-5.4

**Key Features:**
- **Multimodal Tool Improvements**: Rewritten `read_media` with clearer schema; new `MediaCallLedgerHook` for media call tracking
- **Subagent Enhancements**: `inherit_spawning_agent_backend` for automatic backend inheritance, `final_answer_strategy` for child orchestrator policy, per-agent `subagent_agents` override
- **GPT-5.4 Support**: New default OpenAI flagship model
- **Decomp + Checklist Cooperation**: Decomposition mode works with checklist workflow for quality-gated subtask iteration

### v0.1.59
**New Features:** Quality Round Improvements — Planning, Evaluation, Subagents, Media Fixes

**Key Features:**
- **Planning Improvements**: Auto-add improvements to task plan, plan review enhancements
- **Checklist & Evaluation**: Better eval gen config, checklist fixes, Gemini tool name normalization for MCP
- **Subagent Improvements**: Adjusted subagent behavior, subagent manager enhancements, Docker skill write access fixes
- **Media Generation Fixes**: Video gen skill adjustments, video understanding criticality, impact metric restoration

### v0.1.58
**New Features:** Multimodal Revamp, Nvidia NIM Backend, Quality Rethinking Subagent, Checklist Improvements

**Key Features:**
- **Multimodal Revamp**: ElevenLabs TTS/STT, Nano Banana 2 image generation, Grok image/video generation, media generation skills, multi-turn image editing with continuation IDs
- **Nvidia NIM Backend**: First-class provider integration for NVIDIA Inference Microservices
- **Quality Rethinking Subagent**: New `quality_rethinking` subagent type for targeted per-element craft improvements
- **Checklist Improvements**: Explicit improve/preserve listings, better label refresh ordering, evaluation criteria defaults

**Try It:**
```bash
# Install or upgrade to v0.1.58
pip install --upgrade massgen

# Try checklist-driven refinement with quality rethinking
uv run massgen --config @examples/features/subagent_checklist.yaml \
  "Create a website for an AI company selling a creative sci-fi style product. Ensure polished visuals and cool interactive elements"
```

### v0.1.57
**New Features:** Subagent Delegation Protocol, Builder Subagent, Substantiveness Tracking, Claude Code Reasoning

**Key Features:**
- **Subagent Delegation Protocol**: Spawn subagents from within Docker containers via secure file-based delegation with atomic JSON exchange and workspace validation
- **Builder Subagent**: New subagent type for large-scale work (complex rewrites, big documents) with fresh context, auto-triggered when transformative changes are needed
- **Substantiveness Tracking**: Checklist classifies planned changes as transformative, structural, or incremental for smarter convergence decisions
- **Claude Code Reasoning**: Updated SDK with unified `reasoning` config supporting adaptive/enabled/disabled modes and effort levels

### v0.1.56
**New Features:** Spec Plan Mode, ask_others Targeting, Critic Subagent, Codex OAuth Login Fix

**Key Features:**
- **Spec Plan Mode**: `plan_mode="spec"` for formal requirements specification before execution with TUI spec mode support
- **ask_others Targeted Messaging**: `target_agents` parameter for focused agent-to-agent communication
- **Critic Subagent**: New subagent type for honest, unbiased quality assessment detecting genuine vs incremental improvement
- **read_media Conversation Continuity**: Follow-up conversations on supported media (image) via `continue_from` conversation_id
- **Codex OAuth Login Fix**: Codex backend always available in WebUI regardless of OPENAI_API_KEY

**Try It:**
```bash
# Install or upgrade to v0.1.56
pip install --upgrade massgen

# Launch MassGen, then press Shift+Tab twice to enter 'spec' mode
uv run massgen
```

### v0.1.55
**New Features:** Specialized Subagent Types, Dynamic Evaluation Criteria, Native Backend Image Routing, Configurable Video Frame Extraction

**Key Features:**
- **Specialized Subagent Types**: Discovery-based system for specialized subagent roles (evaluator, explorer, researcher, novelty) via `SUBAGENT.md` frontmatter with TUI visualization
- **Dynamic Evaluation Criteria**: GEPA-inspired task-specific evaluation criteria with domain presets and core/stretch categorization
- **Native Backend Image Routing**: `understand_image` routes to agent's own backend (Claude, Gemini, Grok, Claude Code, Codex) with OpenAI fallback
- **Configurable Video Frame Extraction**: Scene-based (PySceneDetect) or uniform extraction with `max_frames` cost guardrail

### v0.1.54
**New Features:** Copilot SDK Backend, Subagent Runtime Messaging, Gemini 3.1 Pro Support, Per-Agent Injection Targeting

**Key Features:**
- **Copilot SDK Backend**: New `copilot` backend using `github-copilot-sdk` with native MCP server integration
- **Subagent Runtime Messaging**: New `send_message_to_subagent` tool to steer running background subagents mid-execution
- **Gemini 3.1 Pro Support**: `gemini-3.1-pro-preview` model added to capabilities registry
- **Per-Agent Injection Targeting**: Injections can target specific agents or broadcast to all

### v0.1.53
**New Features:** Background Tool Execution, Planning Task Verification, TUI Background Job Indicators

**Key Features:**
- **Background Tool Execution**: Non-blocking lifecycle tools (`start_background_tool`, `get_background_tool_status`, `get_background_tool_result`, `wait_for_background_tool`, `cancel_background_tool`, `list_background_tools`)
- **Planning Task Verification**: Tasks require `verification` and `verification_method` by default; `--no-require-verification` to opt out
- **TUI Background Job Indicators**: Agent status ribbon and background tasks modal with lifecycle controls
- **Subagent Infrastructure**: Groundwork for Evaluator and Explorer subagent types via `SUBAGENT.md` frontmatter

### v0.1.52
**New Features:** Dedicated Final Answer Modal, Substantive Gate, Novelty Injection, Agent Identity & Versioning

**Key Features:**
- **Dedicated Final Answer Modal**: Tabbed modal with Answer tab (markdown, post-eval, file list) and Workspace/Review Changes tab (diff review)
- **Substantive Gate**: Quality gate preventing coordination from continuing with only incremental changes
- **Novelty Injection**: Creative pressure injection when agents converge — levels: `none`, `gentle`, `moderate`, `aggressive`
- **Agent Identity & Versioning**: Versioned answer labels (e.g., `agent1.2`) with `answer_label_mapping` for provenance tracking
- **First Answer Non-Restart**: First answers no longer trigger automatic restarts on quality check failure

### v0.1.51
**New Features:** Change Documents (Changedoc), Changedoc-Anchored Evaluation, Checklist Gap Report, Drift Conflict Policy

**Key Features:**
- **Change Documents**: Decision journals in `tasks/changedoc.md` capturing decision provenance, rationale, and code traceability
- **Changedoc-Anchored Evaluation**: 5 changedoc-specific checklist items with mandatory gap report
- **Drift Conflict Policy**: `drift_conflict_policy: skip|prefer_presenter|fail` for safer change application
- **Review Modal Improvements**: Multi-context, multi-file diff visualization with critique
- **`--cwd-context` CLI Flag**: Inject CWD as context path (`ro`/`rw`)

### v0.1.50
**New Features:** Chunked Plan Execution, Skill Lifecycle Management, Iterative Planning Review

**Key Features:**
- **Chunked Plan Execution**: Plans divided into chunks and executed one at a time with progress checkpoints
- **Iterative Planning Review**: New modal with Continue Planning / Quick Edit / Finalize Plan options
- **Skill Lifecycle Management**: New lifecycle modes, skill organizer, `SKILL_REGISTRY.md`, previous-session skills
- **Local Skills MCP**: New MCP tool for skill access in Docker/local execution
- **Worktree Improvements**: Branch accumulation, cross-agent diff visibility, orphan cleanup
- **Responsive TUI Mode Bar**: Adaptive layout with compact labels on narrow terminals

**Try It:**
```bash
# Launch with chunked plan execution and skill lifecycle
uv run massgen
```

> Press `Shift+Tab` then press the three dots above the input bar to see plan settings.

### v0.1.49
**New Features:** Log Analysis TUI Mode, Fairness Gate, Checklist Voting, Testing Infrastructure

**Key Features:**
- **Log Analysis in TUI**: New "Analyzing" mode in TUI mode bar for in-app run analysis with configurable profiles
- **Fairness Gate**: Prevents fast agents from dominating coordination with configurable lead caps
- **Checklist Voting**: Structured quality evaluation with binary pass/fail scoring via MCP server
- **Skills Modal**: TUI modal for discovering and toggling skills in interactive mode
- **Persona Easing in TUI**: Persona easing toggle now available in the TUI mode bar

**Try It:**
```bash
# Launch and cycle to Analysis mode via the TUI mode bar
uv run massgen
```

### v0.1.48
**New Features:** Decomposition Mode, Worktree Isolation, Quickstart Docker Setup

**Key Features:**
- **Decomposition Mode**: New coordination mode that decomposes tasks into subtasks assigned to individual agents
- **Worktree Isolation**: Git worktree-based isolation for agent file writes with review modal
- **Quickstart Docker Setup**: Docker setup step in quickstart wizard with animated pull progress
- **Stop Tool**: Agents can signal completion and exit workflows

**Try It:**
```bash
# Launch the quickstart wizard and select Decomposition mode
uv run massgen
```

### v0.1.47
**New Features:** Codex Backend, TUI Theme Refactoring, Per-agent Voting Sensitivity

**Key Features:**
- **Codex Backend**: Run OpenAI Codex CLI as a MassGen backend with local and Docker execution
- **TUI Theme System**: Palette-based theming with dark and light variants
- **Per-agent Voting Sensitivity**: Set different voting standards (strict/balanced/lenient) for each agent
- **Claude Code Refactored**: Shared NativeToolMixin for native tool handling across CLI-based backends

**Try It:**
```bash
# First install codex with `npm install -g @openai/codex`, then authenticate and run the below.
uv run massgen --config @examples/configs/providers/openai/codex/codex_local.yaml "Create a website about Bob Dylan"
uv run massgen --config @examples/configs/providers/openai/codex/codex_docker.yaml "Create a website about Bob Dylan"
```

### v0.1.46
**New Features:** Subagent TUI Streaming, Enhanced Final Presentation, TUI Architecture Refactor

**Key Features:**
- **Subagent TUI Streaming**: Interactive preview cards that expand to full timeline views with real-time event streaming
- **Enhanced Final Presentation**: Final answer display with workspace visualization and winning agent highlighting
- **TUI Architecture Refactor**: Unified event pipeline with single source of truth for display creation

**Try It:**
```bash
# Experience subagent TUI streaming with async execution
uv run massgen --config @examples/configs/features/test_subagent_orchestrator_code_mode.yaml "Use subagents to research bob dylan"
```

### v0.1.45
**New Features:** TUI as Default Display Mode, Config Migration, Enhanced Setup

**Key Features:**
- **TUI as Default**: Textual Terminal UI now launches by default for all users
- **Automatic Migration**: Existing configs with `rich_terminal` auto-migrate with deprecation warning
- **Enhanced Setup**: Setup wizard generates TUI configs by default
- **Legacy Access**: Use `--display rich` to explicitly request legacy Rich display

**Example Usage:**
```bash
# TUI launches by default (no --display flag needed)
uv run massgen --config @examples/basic/multi/three_agents_default \
  "Compare the benefits of solar, wind, and hydro energy"

# Setup wizard generates TUI configs automatically
uv run massgen --quickstart
```

### v0.1.44
**New Features:** Execute Mode for Independent Plan Selection, Case Studies UX Enhancements

**Key Features:**
- **Execute Mode Cycling**: Navigate through Normal → Planning → Execute modes via `Shift+Tab`
- **Plan Selector Popover**: Browse and select from up to 10 recent plans with timestamps
- **Context Path Preservation**: Context paths automatically preserved between planning and execution
- **Enhanced Case Studies**: Setup guides and quick start instructions on case studies page

**Try It:**
```bash
# Use the TUI with plan mode cycling
massgen --display textual --config @examples/providers/gemini/gemini_3_flash.yaml

# In the TUI:
# 1. Press Shift+Tab to enter Planning mode
# 2. Create a plan: "Create a Python web scraper for news articles"
# 3. Press Shift+Tab twice to enter Execute mode
# 4. Select your plan from the popover and press Enter to execute
```

### v0.1.43
**New Features:** Tool Call Batching, Interactive Case Studies, Plan Mode Enhancements, Quoted Path Support

**Key Features:**
- **Tool Call Batching**: Consecutive MCP tool calls grouped into collapsible tree views with timing info
- **Interactive Case Studies**: Side-by-side SVG comparisons between MassGen and single-agent outputs
- **Plan Mode Enhancements**: New `PlanOptionsPopover` for browsing plans, selecting depth, and toggling broadcast
- **Quoted Path Support**: `@"/path/with spaces/file.txt"` syntax for paths containing spaces
- **Final Presentation Fixes**: Reasoning text separated from actual answers in final display

**Try It:**
```bash
# Install or upgrade
pip install --upgrade massgen

# Experience tool call batching - multiple file operations batch into collapsible trees
uv run massgen --display textual --config @examples/providers/gemini/gemini_3_flash.yaml "Create a project structure with src/, tests/, and docs/ directories, then add README.md and requirements.txt"
```

### v0.1.42
**New Features:** TUI Visual Redesign, Human Input Queue, AG2 Single-Agent Fix

**Key Features:**
- **TUI Visual Redesign**: Modern "Conversational AI" aesthetic with rounded corners, redesigned agent tabs, polished modals
- **Human Input Queue**: Inject messages to agents mid-stream during execution with `HumanInputHook`
- **AG2 Single-Agent Fix**: Single-agent AG2 setups now vote and coordinate correctly

**Try It:**
```bash
# Experience the redesigned TUI with interactive mode
uv run massgen --display textual \
  --config massgen/configs/basic/multi/three_agents_default.yaml \
  "Compare the pros and cons of React vs Vue for building a dashboard"
```

### v0.1.41
**New Features:** Background Subagent Execution, Subagent Round Timeouts, Extended Subagent Configuration

**Key Features:**
- **Background Subagent Execution**: Spawn subagents with `background=True` for non-blocking parallel work while parent continues
- **Poll for Completion**: Check subagent status and retrieve results when ready
- **Subagent Round Timeouts**: Per-round timeout control with `subagent_round_timeouts` config section
- **Extended Subagent Config**: `subagent_default_timeout`, `subagent_min_timeout`, `subagent_max_timeout`, `subagent_max_concurrent`

**Try It:**
```bash
# Install or upgrade
pip install --upgrade massgen

# Background subagent execution - parent continues while subagent works in background
uv run massgen --display textual --config massgen/configs/features/background_subagent_example.yaml \
  "Use one subagent to research the band Geese in the background while you create a creative website about them, including similar bands."
```

### v0.1.40
**New Features:** Textual TUI Interactive Mode, Context Path @ Syntax, Performance & Stability Improvements

**Key Features:**
- **Textual TUI Interactive Mode**: Launch with `--display textual` for interactive terminal UI with real-time agent streaming and keyboard shortcuts
- **Context Path @ Syntax**: Include files/directories inline with `@path/to/file` syntax with autocomplete support in TUI
- **Interactive Modals**: Access costs (`c`), votes (`v`), workspace browser (`w`), answer comparisons (`b`), and keyboard shortcuts (`?` or `h`)

**Try It:**
```bash
# Install or upgrade
pip install --upgrade massgen

# Launch interactive TUI with three agents
massgen --display textual \
  --config massgen/configs/basic/multi/three_agents_default.yaml \
  "Explain the difference between async and parallel programming"

# Use context path injection to include files
massgen --display textual "Refactor this code @src/app.py"
```

### v0.1.39
**New Features:** Plan and Execute Workflow, Task Verification System, Plan Storage, Response API Fix

**Key Features:**
- **Plan and Execute Workflow**: `--plan-and-execute` creates a plan then immediately executes it, `--execute-plan` runs existing plans
- **Task Verification System**: New `verified` status with verification groups for batch validation at checkpoints
- **Plan Storage**: Persistent plans in `.massgen/plans/` with frozen snapshots and execution tracking
- **Response API Fix**: Function call message sanitization for OpenAI compatibility

**Try It:**
```bash
# Plan and execute in one command - creates a plan then runs it
massgen --plan-and-execute --plan-depth medium \
  "Build a REST API for a todo application"

# Execute an existing plan (prompt auto-fills from plan)
massgen --execute-plan latest
```

### v0.1.38
**New Features:** Task Planning Mode, Two-Tier Workspace, Project Instructions Auto-Discovery, Batch Image Analysis, Reliability Improvements

**Key Features:**
- **Task Planning Mode**: Create structured plans with `--plan` flag and `--plan-depth` (shallow/medium/deep) for future workflows (plan-only, no auto-execution)
- **Two-Tier Workspace**: Git-backed scratch/deliverable separation keeping exploratory work separate from final outputs
- **Project Instructions Auto-Discovery**: Automatic loading of `CLAUDE.md` and `AGENTS.md` for project context
- **Batch Image Analysis**: Process multiple images simultaneously with `read_media` tool for comparison and batch analysis
- **Reliability Fixes**: Circuit breaker prevents infinite loops, fixed soft-to-hard timeout race conditions, MCP tools properly restored after hard timeout restarts

**Try It:**
```bash
# Task planning mode - creates a plan (no auto-execution)
uv run massgen --plan --plan-depth medium \
  "Build a REST API for a todo application"

# Will read from CLAUDE.md/AGENTS.md in cwd, if it exists
uv run massgen --config massgen/configs/basic/multi/three_agents_default.yaml \
  "Explain the current functionality of this repo @./"
```

### v0.1.37
**New Features:** Execution Traces, Thinking Mode Improvements, Standardized Agent Labeling

**Key Features:**
- **Execution Traces**: Full execution history preserved as `execution_trace.md` for compression recovery and cross-agent coordination
- **Thinking Mode Improvements**: Claude Code and Gemini reasoning content streaming buffer integration
- **Standardized Agent Labeling**: Consistent agent identification across all backends

**Try It:**
```bash
# Will read from CLAUDE.md/AGENTS.md in cwd, if it exists
uv run massgen --config massgen/configs/basic/multi/three_agents_default.yaml \
  "Explain the current functionality of this repo @./"
```

### v0.1.36
**New Features:** @path Context Handling, Hook Framework, Claude Code Integration

**Key Features:**
- **@path Context Handling**: Reference files inline with `@path` syntax - type `@` to trigger autocomplete file picker (like Claude Code)
- **Hook Framework**: Extend agent behavior with PreToolUse/PostToolUse hooks for permission validation, content injection, and custom processing
- **Claude Code Integration**: Native Claude Code hooks compatibility and improved Docker resource management

**Try It:**
```bash
# Reference files with @path syntax - autocomplete file picker
uv run massgen
# Then type: Analyze @src/main.py and suggest improvements

# Test hook framework with built-in hooks
uv run massgen --config massgen/configs/debug/injection_delay_test.yaml \
  "Create a simple poem and write it into a file"
# View logs for MidStreamInjectionHook (cross-agent updates) and HighPriorityTaskReminderHook (system reminders)
```

### v0.1.35
**New Features:** Log Analysis CLI, Logfire Workflow Observability, Direct MCP Servers, Tool Handling Fixes

**Key Features:**
- **Log Analysis CLI**: New `massgen logs analyze` command with prompt mode and multi-agent self-analysis using MassGen
- **Logfire Workflow Attributes**: Round context, vote reasoning, and local file references for observability
- **Direct MCP Servers**: Keep specific MCPs as protocol tools when using code-based tools
- **Tool Handling Fixes**: Unknown tools handled gracefully, vote-only mode improvements

**Try It:**
```bash
# Install or upgrade
pip install --upgrade massgen

# List your runs and see which have been analyzed
uv run massgen logs list

# Generate an analysis prompt (defaults to most recent log)
uv run massgen logs analyze

# Run multi-agent self-analysis on your logs
uv run massgen logs analyze --mode self

# Use direct MCP servers with code-based tools for multi-agent log analysis
uv run massgen --config massgen/configs/analysis/log_analysis_cli.yaml \
  "Use the massgen-log-analyzer skill to analyze the log directory at .massgen/massgen_logs/log_20260107_123456. Read all relevant files and produce an ANALYSIS_REPORT.md"
```

### v0.1.34
**New Features:** OpenAI-Compatible Server, Dynamic Model Discovery, WebUI Improvements, Subagent Reliability

**Key Features:**
- **OpenAI-Compatible Server**: Run MassGen as a local HTTP server with `massgen serve` command
- **Dynamic Model Discovery**: Groq and Together backends fetch available models via authenticated API calls
- **WebUI File Diffs**: View workspace file changes with diff highlighting
- **Answer Refresh Polling**: Real-time answer display with polling-based updates
- **Subagent Status Tracking**: Improved status monitoring and error handling for subagent workflows
- **Cancellation Recovery**: Better handling of cancelled subagent operations

**Try It:**
```bash
# Install or upgrade
pip install --upgrade massgen

# Start OpenAI-compatible server with default config
massgen serve --host 0.0.0.0 --port 4000

# Or specify a custom config
massgen serve --config @examples/basic/multi/three_agents_default

# Use with any OpenAI SDK client
curl http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "massgen", "messages": [{"role": "user", "content": "Explain multi-agent systems in LLMs"}]}'
```

### v0.1.33
**New Features:** Reactive Context Compression, Streaming Buffer System, MCP Tool Protections

**Key Features:**
- **Reactive Context Compression**: Automatic conversation compression when context length errors occur
- **Streaming Buffer System**: Tracks partial agent responses for compression recovery
- **File Overwrite Protection**: `write_file` tool refuses to overwrite existing files
- **Task Plan Duplicate Prevention**: `create_task_plan` blocks duplicate plans after recovery
- **Grok MCP Tools**: Fixed MCP tool visibility by adjusting tool handling in chat completions
- **Gemini Vote-Only Mode**: Fixed `vote_only` parameter handling in Gemini backend streaming
- **GPT-5 Model Behavior**: System prompt adjustments and default reasoning set for newer models

**Try It:**
```bash
# Install or upgrade
pip install --upgrade massgen

# Test reactive context compression (automatically handles long conversations)
uv run massgen --debug --save-llm-calls \
  --config massgen/configs/tools/filesystem/test_reactive_compression.yaml \
  "Read all Python files in massgen/backend/ and summarize what each one does"

# Compression activates automatically when context limits are reached
# Agent progress is preserved through the streaming buffer system
# Debug logs saved to .massgen/massgen_logs/<session>/compression_debug/
```

### v0.1.32
**New Features:** Multi-Turn Session Export, Logfire Optional, Per-Attempt Logging

**Key Features:**
- **Multi-Turn Session Export**: Share sessions with turn range selection, workspace options, and export controls
- **Logfire Optional Dependency**: Moved to `[observability]` extra for smaller default installs
- **Per-Attempt Logging**: Each restart attempt gets separate log files for cleaner debugging
- **Office PDF Conversion**: Automatic DOCX/PPTX/XLSX to PDF when sharing sessions

**Try It:**
```bash
# Install or upgrade
pip install --upgrade massgen

# Share a multi-turn session with turn selection
massgen export --turns 1-3              # Export turns 1-3
massgen export --turns latest           # Export only the latest turn
massgen export --dry-run --verbose      # Preview what would be shared

# Install with observability support (optional)
pip install "massgen[observability]"
massgen --logfire --config massgen/configs/basic/multi/three_agents_default.yaml \
  "What are the benefits of multi-agent AI systems?"
```

### v0.1.31
**New Features:** Logfire Observability, Azure Tool Call Streaming

**Key Features:**
- **Logfire Observability Integration**: Comprehensive logging and tracing via [Logfire](https://logfire.pydantic.dev/) with automatic LLM instrumentation
- **Azure OpenAI Tool Call Streaming**: Tool calls now accumulated and yielded as structured chunks

**Try It:**
```bash
# Enable Logfire observability
massgen --logfire --config massgen/configs/basic/multi/three_agents_default.yaml \
  "What are the benefits of multi-agent AI systems?"
```

### v0.1.30
**New Features:** OpenRouter Web Search, Persona Diversity Modes, Azure Multi-Endpoint Support

**Key Features:**
- **OpenRouter Web Search Plugin**: Add real-time web search to OpenRouter models with `enable_web_search: true`
- **Persona Diversity Modes**: Agents get unique personalities - prioritize different values or create different solution styles, with automatic softening when evaluating others' work
- **Azure Multi-Endpoint**: Support both Azure-specific and OpenAI-compatible endpoints with auto-detection
- **Environment Variable Expansion**: Keep API keys in `.env` and reference them with `${VAR}` syntax - safer to share configs

**Try It:**
```bash
# Install or upgrade
pip install --upgrade massgen

# OpenRouter web search - search the web with any OpenRouter model
uv run massgen --config massgen/configs/basic/single/single_openrouter_web_search.yaml \
  "What are the latest developments in quantum computing?"

# Persona diversity - automatic diverse personas for multi-agent collaboration
uv run massgen --config massgen/configs/basic/multi/persona_diversity_example.yaml \
  "Create a website about Bob Dylan"
```

### v0.1.29
**New Features:** Subagent System, Tool Metrics Distribution, Per-Agent System Messages

**Key Features:**
- **Subagent System**: Spawn parallel child MassGen processes for independent tasks with isolated workspaces
- **Tool Metrics Distribution**: Enhanced metrics with per-call averages and min/max/median output distribution
- **Per-Agent System Messages**: Configure different system messages for each agent via `massgen --quickstart`

**Try It:**
```bash
# Subagent system - spawn parallel child processes for independent tasks
massgen --config massgen/configs/features/test_subagent_orchestrator.yaml \
  "Spawn a subagent to research Python async best practices"

# Subagent with code-based tools and Docker execution
massgen --config massgen/configs/features/test_subagent_orchestrator_code_mode.yaml \
  "Spawn a subagent to write a Python script that fetches the current weather"
```

### v0.1.28
**New Features:** Unified Multimodal Tools, Web UI Artifact Previewer

**Key Features:**
- **Unified Multimodal Tools**: Consolidated `read_media` for understanding and `generate_media` for generation (images, audio, video)
- **Web UI Artifact Previewer**: Preview PDFs, DOCX, PPTX, images, HTML, SVG, Markdown, and Mermaid diagrams
- **OpenRouter Model Filtering**: Automatic filtering to only show tool-capable models

**Try It:**
```bash
# Unified multimodal tools - generate and analyze images, audio, video
massgen --config @examples/tools/custom_tools/multimodal_tools/unified_multimodal \
  "Create an image of two AI chatting with a human and then describe it in detail"
```

### v0.1.27
**New Features:** Session Sharing, Log Analysis CLI, Per-LLM Call Timing, Gemini 3 Flash

**Key Features:**
- **Session Sharing via GitHub Gist**: Share sessions with `massgen export`, manage with `massgen shares list/delete`
- **Log Analysis CLI**: New `massgen logs` command for viewing, filtering, and exporting run logs
- **Per-LLM Call Timing**: Detailed timing metrics for individual LLM API calls across all backends
- **Gemini 3 Flash Model**: Google's Gemini 3 Flash model added to provider registry
- **CLI Config Builder**: Per-agent web search toggle, system messages, coordination settings
- **Web UI Context Paths Wizard**: New `ContextPathsStep` component for workspace configuration

**Try It:**
```bash
# Install or upgrade
pip install --upgrade massgen

# Share a session via GitHub Gist (requires gh CLI)
massgen export                            # Share most recent session
massgen export log_20251218_134125        # Share specific session
massgen shares list                       # List your shared sessions

# Analyze your run logs
massgen logs list                         # List all runs
massgen logs view <log_id>                # View detailed run info with LLM timing

# Try Gemini 3 Flash
massgen --config @examples/providers/gemini/gemini_3_flash \
  "Create a simple Python script that demonstrates async programming"
```

### v0.1.26
**New Features:** Docker Diagnostics Module, Web UI Setup System, Shadow Agent Response Depth

**Key Features:**
- **Docker Diagnostics Module**: Comprehensive error detection with platform-specific resolution steps for Docker issues
- **Web UI Setup System**: Guided first-run setup with API key management and environment checks
- **Shadow Agent Response Depth**: Test-time compute scaling via `response_depth` parameter (`low`/`medium`/`high`)
- **Model Registry Updates**: GPT-5.1-Codex family, Claude alias notation, updated defaults

**Try It:**
```bash
# Install or upgrade
pip install --upgrade massgen

# Use response depth for test-time compute scaling in agent broadcasts
massgen --config @examples/broadcast/test_broadcast_agents \
  "Create a website about Bob Dylan. Please ask_others for what framework to use first"

# Launch Web UI with setup wizard
massgen --web
```

### v0.1.25
**New Features:** UI-TARS Custom Tool, GPT-5.2 Support, Evolving Skills

**Key Features:**
- **UI-TARS Custom Tool**: ByteDance's UI-TARS-1.5-7B model for GUI automation with vision and reasoning
- **GPT-5.2 Model**: OpenAI's latest model added as new default
- **Evolving Skills**: Create reusable workflow plans that improve through iteration
- **Textual Terminal Enhancement**: Improved adaptive layouts and dark/light themes

**Try It:**
```bash
# Install or upgrade
pip install --upgrade massgen

# Try UI-TARS computer use (requires UI_TARS_API_KEY and UI_TARS_ENDPOINT)
massgen --config @examples/tools/custom_tools/ui_tars_browser_example \
  "Search for 'Python asyncio' on Google and summarize the first result"

# Use the new Textual terminal display
massgen --config @examples/basic/single_agent_textual \
  "What is the transformers in deep learning?"

# Create evolving skills with previous session discovery
massgen --config @examples/skills/skills_with_previous_sessions \
  "Create a web scraping workflow that extracts article titles from news sites"
```

### v0.1.24
**New Features:** Enhanced Cost Tracking Across Multiple Backends

**Key Features:**
- **Multi-Backend Cost Tracking**: Real-time token counting and cost calculation for OpenRouter, xAI/Grok, Gemini, and Claude Code
- **Cost Inspection Command**: `/inspect c` displays detailed per-agent cost breakdown (input, output, reasoning, cached tokens)
- **Session Cost Aggregation**: Aggregated cost totals and tool metrics across all agents in coordination status

**Try It:**
```bash
# Install or upgrade
pip install --upgrade massgen

# Run any multi-agent session to track costs
massgen --config @examples/basic/multi/three_agents_default "Compare AI approaches"

# View cost breakdown during or after coordination:
#   /inspect c  - Show detailed cost breakdown per agent
```

### v0.1.23
**New Features:** Turn History Inspection, Web UI Automation Mode, Docker Container Persistence, Async Execution Consistency

**Key Features:**
- **Turn History Inspection**: Review any turn's agent outputs and coordination data with `/inspect` commands
- **Web UI Automation Mode**: Streamlined interface with `AutomationView` component for programmatic monitoring workflows
- **Docker Container Persistence**: `SessionMountManager` pre-mounts session directories, eliminating container recreation between turns
- **Improved Cancellation Handling**: Flag-based cancellation with terminal state restoration
- **Async Safety Utilities**: `run_async_safely()` handles nested event loops with ThreadPoolExecutor pattern

**Try It:**
```bash
# Multi-turn session with turn inspection
massgen --config @examples/basic/multi/three_agents_default
# Use /inspect to review history:
#   /inspect all  - List all turns with summaries
#   /inspect 1    - View Turn 1 details

# Web UI automation mode
massgen --automation --web --config @examples/basic/multi/three_agents_default \
  "Analyze multi-agent AI coordination patterns"
```

### v0.1.22
**New Features:** Shadow Agent Architecture, Full Context Broadcast Responses

**Key Features:**
- **Shadow Agent Architecture**: Lightweight agent clones spawned in parallel to respond to broadcasts without interrupting parent agents
- **Full Context Inheritance**: Shadow agents copy parent's complete conversation history and current turn streaming content
- **Non-Blocking Responses**: Parent agents continue working uninterrupted while shadows handle broadcast responses
- **Automatic Response Collection**: Shadow agent responses collected via `asyncio.gather()` for maximum parallelism
- **Parent Agent Awareness**: Informational messages injected into parent agents after shadow responds

**Documentation:**
- `docs/source/user_guide/advanced/agent_communication.rst` - Shadow agent architecture documentation

**Try It:**
```bash
# Install or upgrade
pip install --upgrade massgen

# Run a multi-agent session with agent-to-agent communication enabled
# Enable with: orchestrator.coordination.broadcast: "agents"
massgen --config @examples/broadcast/test_broadcast_agents \
  "Design a collaborative architecture for a microservices system"
# Agents ask each other questions via ask_others() - shadow agents respond in parallel
```

### v0.1.21
**New Features:** Graceful Cancellation System, Session Restoration for Incomplete Turns

**Key Features:**
- **Graceful Cancellation**: Ctrl+C during coordination saves partial progress instead of losing work
- **Two-Stage Exit**: First Ctrl+C saves and exits gracefully; second forces immediate exit
- **Session Resumption**: Cancelled sessions can be resumed with `--continue`, preserving agent answers and workspaces
- **Multi-Turn Behavior**: In interactive mode, first Ctrl+C returns to prompt instead of exiting

**Documentation:**
- `docs/source/user_guide/sessions/graceful_cancellation.rst` - Graceful cancellation guide

**Try It:**
```bash
# Install or upgrade
pip install --upgrade massgen

# Run a multi-agent session and press Ctrl+C to test graceful cancellation
massgen --config @examples/basic/multi/three_agents_default \
  "Analyze the pros and cons of different programming paradigms"
# Press Ctrl+C during coordination - partial progress is saved

# Resume a cancelled session
massgen --continue
# Agents see previous partial answers and can continue from where they left off
```

### v0.1.20
**New Features:** Web UI System, Automatic Computer Use Docker Setup, Response API Improvements

**Key Features:**
- **Web UI System**: Browser-based real-time visualization with React frontend, WebSocket streaming, and interactive components (AgentCarousel, AnswerBrowser, Timeline, VoteVisualization)
- **Automatic Docker Setup**: Ubuntu 22.04 container creation for computer use agents with X11 virtual display, xdotool, Firefox, Chromium, and scrot
- **Response API Improvements**: Enhanced multi-turn context handling with function call preservation and stub output generation

**Try It:**
```bash
# Web UI - browser-based multi-agent visualization
massgen --web --config @examples/basic/multi/three_agents_default \
  "What are the advantages of multi-agent AI systems?"

# Computer Use with Auto Docker Setup
massgen --config @examples/tools/custom_tools/claude_computer_use_docker_example \
  "Open Firefox and search for Python documentation"
```

### v0.1.19
**New Features:** LiteLLM Integration & Programmatic API, Claude Strict Tool Use & Structured Outputs, Gemini Exponential Backoff

**Configuration Files:**
- `providers/claude/strict_tool_use_example.yaml` - Claude strict tool use with custom and MCP tools

**Key Features:**
- **LiteLLM Integration**: MassGen as a drop-in LiteLLM custom provider via `MassGenLLM` class with `register_with_litellm()` one-line setup
- **Programmatic API**: New `run()` and `build_config()` functions for direct Python execution, `NoneDisplay` for silent output
- **Claude Strict Tool Use**: `enable_strict_tool_use` config flag with recursive schema patching, `output_schema` for structured JSON outputs
- **Gemini Exponential Backoff**: Automatic retry for rate limit errors (429, 503) with `BackoffConfig` and `Retry-After` header support

**Try It:**
```bash
# Claude Strict Tool Use - schema validation with structured outputs
# Prerequisites: ANTHROPIC_API_KEY in .env
uv run massgen --config massgen/configs/providers/claude/strict_tool_use_example.yaml \
  "Add 42 and 58, then get weather for Tokyo"
```

### v0.1.18
**New Features:** Agent Communication System (Human Broadcast Q&A), Claude Programmatic Tool Calling, Claude Tool Search

**Configuration Files:**
- `providers/claude/programmatic_with_two_tools.yaml` - Claude programmatic tool calling with custom and MCP tools
- `providers/claude/tool_search_example.yaml` - Claude tool search with deferred loading
- `broadcast/test_broadcast_agents.yaml` - Agent-to-agent broadcast communication
- `broadcast/test_broadcast_human.yaml` - Human broadcast communication with Q&A prompts

**Key Features:**
- **Agent Communication System**: Agents broadcast questions to humans or other agents via `ask_others()` tool with three modes, blocking execution with inline response delivery, session-persistent Q&A history
- **Claude Programmatic Tool Calling**: Code execution invokes tools via `enable_programmatic_flow` flag (requires claude-opus-4-5 or claude-sonnet-4-5)
- **Claude Tool Search**: Server-side deferred tool discovery via `enable_tool_search` with regex or bm25 variants

**Try It:**
```bash
# Claude Programmatic Tool Calling - call tools from code execution
# Prerequisites: ANTHROPIC_API_KEY in .env
massgen --config massgen/configs/providers/claude/programmatic_with_two_tools.yaml \
  "Add 5 and 3, then get weather for Tokyo and New York"

# Claude Tool Search - deferred tool discovery (visible + deferred tools)
# Prerequisites: ANTHROPIC_API_KEY, BRAVE_API_KEY in .env
massgen --config massgen/configs/providers/claude/tool_search_example.yaml \
  "Check weather in tokyo, search for tourist attractions, and find me an Airbnb there for 3 nights in january 2026"
```

### v0.1.17
**New Features:** Textual Terminal Display System with Dark/Light Themes (Early Release)

**Configuration Files:**
- `basic/single_agent_textual.yaml` - Single agent with Textual terminal display

**Key Features:**
- **Textual Terminal Display**: Modern interactive terminal UI using the Textual library with multi-panel layout for agents and orchestrator
- **Dark & Light Themes**: VS Code-inspired TCSS stylesheets for customizable appearance
- **Enhanced Visualization**: Real-time streaming with syntax highlighting, emoji fallback, and content filtering for critical patterns

> **Note:** This is an early release of the Textual display. The default remains `rich_terminal` for stability, but we'll continue iterating on the Textual version.

**Try It:**
```bash
# Install or upgrade
pip install --upgrade massgen

# Textual Terminal Display - enhanced interactive UI with dark/light themes
# Prerequisites: OPENAI_API_KEY in .env
massgen --config massgen/configs/basic/single_agent_textual.yaml \
  "What is the transformers in deep learning?"
```

### v0.1.16
**New Features:** Terminal Evaluation System, LiteLLM Cost Tracking, Memory Archiving, Self-Evolution Skills

**Configuration Files:**
- `meta/massgen_evaluates_terminal.yaml` - MassGen evaluates its own terminal display with VHS recording
- `tools/custom_tools/terminal_evaluation.yaml` - Terminal evaluation tool demonstration
- `skills/test_memory.yaml` - Memory archiving with multi-turn session support

**Key Features:**
- **Terminal Evaluation System**: Record terminal sessions with VHS and analyze with multimodal AI for UI/UX evaluation
- **LiteLLM Cost Tracking**: Accurate pricing for 500+ models with automatic updates, reasoning token support
- **Memory Archiving**: Persistent memory across conversation turns for session continuity
- **Self-Evolution Skills**: Four new skills for MassGen self-development and maintenance

**Try It:**
```bash
# Terminal Evaluation - record and analyze MassGen's terminal display
# Prerequisites: VHS installed (brew install vhs), OPENAI_API_KEY or GEMINI_API_KEY in .env
uv run massgen --config massgen/configs/meta/massgen_evaluates_terminal.yaml \
  "Record running massgen on @examples/basic/multi/two_agents_gemini.yaml, answering 'What is 2+2?'. Then, evaluate the terminal display for clarity, status indicators, and coordination visualization, coming up with improvements."

# Memory Archiving - persistent memory across conversation turns
# Prerequisites: Docker running, API keys in .env
uv run massgen --config massgen/configs/skills/test_memory.yaml \
  "Create a website about Bob Dylan"
```

### v0.1.15
**New Features:** Persona Generation System, Docker Distribution & Custom Tools Enhancement

**Configuration Files:**
- `basic/multi/persona_diversity_example.yaml` - Persona generation with strategy and backend configuration
- `.github/workflows/docker-publish.yml` - Enhanced CI/CD pipeline for GitHub Container Registry

**Key Features:**
- **Persona Generation System**: Automatic generation of diverse system messages for multi-agent configurations with multiple strategies (complementary, diverse, specialized, adversarial)
- **Docker Distribution Enhancement**: GitHub Container Registry integration with ARM architecture support
- **Custom Tools in Docker**: Isolated Docker containers for security and portability (Issue #510)
- **MassGen Pre-installed**: Docker images include MassGen for immediate use with custom tools
- **Config Builder Enhancement**: Improved interactive configuration with better model selection and defaults

**Try It:**
```bash
# Persona Generation - automatic diverse system messages for agents
# Prerequisites: OPENAI_API_KEY in .env, Docker running for code execution
uv run massgen --config massgen/configs/basic/multi/persona_diversity_example.yaml \
  "Create a website about Bob Dylan"

# Enhanced Config Builder - improved model selection
uv run massgen --init  # Interactive wizard with better defaults
```

### v0.1.14
**New Features:** Parallel Tool Execution, Interactive Quickstart, Gemini 3 Pro Support & MCP Registry Client

**Configuration Files:**
- `tools/custom_tools/gpt5_nano_custom_tool_with_mcp_parallel.yaml` - Parallel tool execution example with configurable concurrency
- `providers/gemini/gemini_3_pro.yaml` - Configuration for Gemini 3 Pro model with function calling

**Key Features:**
- **Parallel Tool Execution System**: Configurable concurrent tool execution across all backends with asyncio-based scheduling
- **Gemini 3 Pro Support**: Full integration for Google's Gemini 3 Pro model with native function calling
- **Interactive Quickstart Workflow**: Streamlined onboarding experience with guided configuration creation
- **MCP Registry Client**: Enhanced server metadata fetching from official MCP registry

**Try It:**
```bash
# Interactive Quickstart - guided configuration creation
uv run massgen --quickstart

# Parallel Tool Execution - concurrent tool execution
uv run massgen --config massgen/configs/tools/custom_tools/gpt5_nano_custom_tool_with_mcp_parallel.yaml \
  "whats the sum of 123 and 456? and whats the weather of Tokyo and london?"

# Gemini 3 Pro - Google's latest model with function calling
uv run massgen --config massgen/configs/providers/gemini/gemini_3_pro.yaml \
  "Create a website about Bob Dylan"
```

### v0.1.13
**New Features:** Code-Based Tools, MCP Registry, Skills Installation & NLIP Integration

**Configuration Files:**
- `tools/filesystem/code_based/example_code_based_tools.yaml` - Code-based tools with auto-discovery and shared tools directory
- `tools/filesystem/exclude_mcps/test_minimal_mcps.yaml` - Minimal MCPs with command-line file operations
- `examples/nlip_basic.yaml` - Basic NLIP protocol support with router and translation settings
- `examples/nlip_openai_weather_test.yaml` - OpenAI with NLIP integration for custom tools and MCP servers
- `examples/nlip_orchestrator_test.yaml` - Orchestrator-level NLIP configuration for multi-agent coordination

**Key Features:**
- **Code-Based Tools (CodeAct Paradigm)**: Revolutionary tool integration via importable Python code, reducing token usage by 98%
- **MCP Server Registry**: Auto-discovery and intelligent tool routing with on-demand loading
- **Skills Installation System**: Cross-platform automated installer for openskills CLI, Anthropic/OpenAI/Vercel skills, Agent Browser skill, and Crawl4AI
- **NLIP Integration**: Advanced tool routing with Natural Language Interface Protocol across all backends
- **Shared Tools Directory**: Tools generated once and shared across all agents to avoid duplication
- **Auto-Discover Custom Tools**: Automatically discover and load all tools from `massgen/tool/` directory
- **Exclude File Operation MCPs**: Use command-line tools for file operations to reduce MCP overhead
- **TOOL.md Documentation Standard**: Standardized documentation format for all custom tools

**Try It:**
```bash
# Install or upgrade
pip install --upgrade massgen

# Automated Skills Installation - cross-platform setup
massgen --setup-skills  # Installs openskills CLI, Anthropic/OpenAI/Vercel skills, Agent Browser skill, and Crawl4AI

# Code-Based Tools with Auto-Discovery - demonstrates 98% context reduction
# Prerequisites: Docker running, .env file with API keys (OPENAI_API_KEY, GOOGLE_API_KEY, etc.)
uv run massgen --automation \
  --config massgen/configs/tools/filesystem/code_based/example_code_based_tools.yaml \
  "List all available tools by exploring the workspace filesystem. Show what MCP tools and custom tools are available."

# Or use with skills for advanced features (e.g., website creation):
uv run massgen --config massgen/configs/tools/filesystem/code_based/example_code_based_tools.yaml \
  "Create a website about Bob Dylan, ensuring that it is visually appealing and user friendly"

# Minimal MCPs - test memory and task planning with reduced tool overhead
# Prerequisites: Docker running
uv run massgen --config massgen/configs/tools/filesystem/exclude_mcps/test_minimal_mcps.yaml \
  "Create a website about Bob Dylan"

# NLIP Integration - natural language tool routing with OpenAI
# Prerequisites: OPENAI_API_KEY in .env, weather MCP (npx -y @fak111/weather-mcp)
massgen --config massgen/configs/examples/nlip_openai_weather_test.yaml \
  "What's the sum of 123 and 456? And what's the weather in Tokyo?"

# Orchestrator-level NLIP - multi-agent coordination with NLIP routing
# Prerequisites: OPENAI_API_KEY, CEREBRAS_API_KEY in .env
massgen --config massgen/configs/examples/nlip_orchestrator_test.yaml \
  "What's the sum of 123 and 456? And what's the weather in Tokyo?"
```

### v0.1.12
**New Features:** System Prompt Architecture Refactoring, Semantic Skills & Multi-Agent Computer Use

**Configuration Files:**
- `skills/skills_basic.yaml` - Enhanced skills system with semantic search and code understanding
- `tools/custom_tools/multi_agent_computer_use_example.yaml` - Multi-agent computer automation with Claude (Docker) and Gemini (Browser)
- `tools/custom_tools/gemini_computer_use_docker_example.yaml` - Gemini computer use with Docker integration
- `tools/custom_tools/claude_computer_use_docker_example.yaml` - Claude computer use with Docker integration

**Key Features:**
- **System Prompt Architecture**: Complete refactoring with hierarchical structure, XML-based formatting for Claude, improved LLM attention management
- **Semtools Skill**: Semantic search capabilities using embedding-based similarity for intelligent file and code discovery
- **Serena Skill**: Symbol-level code understanding via LSP integration for precise code navigation and analysis
- **Skills System Enhancements**: Local execution mode support enabling skills to run outside Docker environments
- **Enhanced Computer Use**: Docker integration for Linux desktop automation with VNC visualization and X11 display support
- **Multi-Agent Coordination**: Combined Claude (Docker/Linux) and Gemini (Browser) computer use for complex automation workflows
- **Browser Automation**: Screenshot file saving with automatic persistence to workspace directories

**Try It:**
```bash
# Install or upgrade
pip install --upgrade massgen

# Enhanced Skills System - semantic search and code understanding
# Prerequisites: Docker daemon running (or install openskills locally)
uv run massgen --config massgen/configs/skills/skills_basic.yaml \
  "Create cool algorithmic art we can use in GitHub repo"

# Multi-Agent Computer Use - Claude (Docker) + Gemini (Browser) coordination
# Prerequisites:
#   1. Set ANTHROPIC_API_KEY and GEMINI_API_KEY in .env
#   2. Docker installed and running
#   3. Run ./scripts/setup_docker_cua.sh for Claude Docker setup
#   4. Install Playwright: pip install playwright && playwright install chromium
uv run massgen --config massgen/configs/tools/custom_tools/multi_agent_computer_use_example.yaml \
  "Search for latest Python releases online and create a summary document"

# Gemini Computer Use with Docker - Linux desktop automation
# Prerequisites:
#   1. Set GEMINI_API_KEY in .env
#   2. Docker running, run ./scripts/setup_docker_cua.sh
#   3. pip install google-genai docker
massgen --config massgen/configs/tools/custom_tools/gemini_computer_use_docker_example.yaml \
  "Browse GitHub and find popular AI projects"
```

### v0.1.11
**New Features:** Skills System, Memory MCP & Rate Limiting

**Configuration Files:**
- `skills/skills_basic.yaml` - Basic skills system with file search capabilities
- `skills/skills_with_memory.yaml` - Skills with memory and task planning integration
- `skills/skills_existing_filesystem.yaml` - Skills integrated into existing project filesystem
- `rate_limits/rate_limits.yaml` - Rate limiting configuration for Gemini models

**Key Features:**
- **Skills System**: Modular prompting framework with automatic skill discovery from `massgen/skills/` directory, organized into `always/` (auto-included) and `optional/` categories
- **Memory MCP Tool & Filesystem Integration**: MCP server for memory management with persistent markdown storage, simultaneous memory and filesystem operations for advanced workflows
- **Rate Limiting System (Gemini)**: Multi-dimensional rate limiting (RPM, TPM, RPD) for Gemini models with graceful cooldown periods
- **Enhanced Windows Support**: Improved Claude Code backend handling of long system prompts on Windows

**Try It:**
```bash
# Install or upgrade
pip install --upgrade massgen

# Skills System - enable domain-specific capabilities
# Prerequisites: Docker daemon running (or install openskills locally)
uv run massgen --config massgen/configs/skills/skills_basic.yaml \
  "Create cool algorithmic art we can use in GitHub repo"

# Memory with Skills and Task Planning - combined filesystem coordination
# Prerequisites: Docker daemon running
uv run massgen --config massgen/configs/skills/skills_with_memory.yaml \
  "Research neural architectures and document findings"

# Skills with Existing Filesystem - self-extension case study
# Prerequisites: Docker daemon running
uv run massgen --config massgen/configs/skills/skills_existing_filesystem.yaml \
  "Analyze the MassGen codebase to identify common development workflows that could benefit from being codified as skills. Create 1-2 optional skills that would help future agents work more efficiently with the codebase."

# Rate Limiting - manage API costs for Gemini models
# Enable rate limiting for any configuration with --enable-rate-limiting flag
massgen --backend gemini --model gemini-2.5-flash --enable-rate-limiting \
  "Explain quantum computing"
```

### v0.1.10
**New Features:** Framework Interoperability Streaming & Docker Enhancements

**Configuration Files:**
- `docker_custom_image.yaml` - Custom Docker image with pre-installed packages
- `docker_github_readonly.yaml` - Docker with read-only GitHub access via gh CLI and git
- `docker_full_dev_setup.yaml` - Full development environment with authentication
- `langgraph_lesson_planner_example.yaml` - LangGraph workflow streaming
- `smolagent_lesson_planner_example.yaml` - SmoLAgent framework streaming
- `Dockerfile.custom-example` - Example Dockerfile for extending MassGen base image

**Key Features:**
- **Framework Interoperability Streaming**: Real-time intermediate step streaming for LangGraph and SmoLAgent with log/output distinction
- **Docker Authentication Restructuring**: Nested `command_line_docker_credentials` with separate `mount` array and `env_vars` array
- **Docker Custom Image Support**: Extend MassGen base image with your own packages via custom Dockerfiles
- **Docker Package Management**: Preinstall packages via `command_line_docker_packages` array before agent execution
- **Parallel Execution Safety**: Instance ID generation for safe parallel execution across all modes
- **MassGen Handbook**: Comprehensive contributor documentation at https://massgen.github.io/Handbook/

**Try It:**
```bash
# Install or upgrade
pip install --upgrade massgen

# LangGraph streaming - watch state graph workflow execution in real-time
# Prerequisites:
#   1. pip install langgraph langchain-openai langchain-core
#   2. OPENAI_API_KEY environment variable must be set
massgen --config @examples/tools/custom_tools/interop/langgraph_lesson_planner_example.yaml \
  "Create a lesson plan for photosynthesis"

# SmoLAgent streaming - see HuggingFace agent reasoning steps live
# Prerequisites:
#   1. pip install smolagents
#   2. OPENAI_API_KEY environment variable must be set
massgen --config @examples/tools/custom_tools/interop/smolagent_lesson_planner_example.yaml \
  "Create a lesson plan for photosynthesis"

# Docker custom image - use your own Docker image with preinstalled packages
# Prerequisites:
#   1. Docker daemon running
#   2. Build the example custom image:
#      docker build -t massgen-custom-test:v1 -f massgen/docker/Dockerfile.custom-example .
uv run massgen --config @examples/configs/tools/code-execution/docker_custom_image.yaml \
  "Verify custom packages: sklearn, matplotlib, seaborn, ipython, black, vim, htop, tree"

# Docker with GitHub authentication - read-only repository access
# Prerequisites:
#   1. Docker daemon running
#   2. Already logged in: gh auth login (or set GITHUB_TOKEN)
#   3. Build the Docker image: bash massgen/docker/build.sh
uv run massgen --config @examples/configs/tools/code-execution/docker_github_readonly.yaml \
  "Test to see the most recent issues in the massgen/MassGen repo with the github cli"
```

### v0.1.9
**New Features:** Session Management & Computer Use Tools

**Configuration Files:**
- `claude_computer_use_example.yaml` - Claude-specific computer use and browser automation
- `gemini_computer_use_example.yaml` - Gemini-specific computer use with screenshot analysis
- `computer_use_browser_example.yaml` - Lightweight browser automation focused on specific tasks
- `grok4_gpt5_gemini_mcp_filesystem_test_with_claude_code.yaml` - Multi-turn session with MCP filesystem

**Key Features:**
- **Session Management System**: Resume multi-turn conversations with complete state restoration across CLI invocations
- **Computer Use Tools**: Automate browsers and desktop using Claude and Gemini APIs with Playwright integration
- **Fuzzy Model Matching**: Type approximate model names to find exact matches (e.g., "sonnet" → "claude-sonnet-4-5-20250929")
- **Six New Backends**: Cerebras AI, Together AI, Fireworks AI, Groq, OpenRouter, Moonshot (Kimi)
- **Enhanced Memory**: Improved memory update logic focusing on actionable patterns and technical insights

**Try It:**
```bash
# Install or upgrade
pip install --upgrade massgen

# Browser automation with Claude
# Prerequisites:
#   1. Set ANTHROPIC_API_KEY environment variable
#   2. Playwright installed: pip install playwright && playwright install
#   3. Virtual display setup (Xvfb) for desktop control
massgen --config @examples/tools/custom_tools/claude_computer_use_example "Search for Python documentation on the web"

# Browser automation with Gemini
# Prerequisites:
#   1. Set GOOGLE_API_KEY in your .env file
#   2. Install Playwright: pip install playwright
#   3. Install browsers: playwright install
#   4. Install Google GenAI SDK: pip install google-genai
massgen --config @examples/tools/custom_tools/gemini_computer_use_example "Navigate to GitHub and search for MassGen repository"

# Interactive model selection with fuzzy matching
massgen  # Run the interactive config builder with smart model search
```

### v0.1.8
**New Features:** Automation Mode & DSPy Integration

**Configuration Files:**
- `three_agents_dspy_enabled.yaml` - Three-agent setup with DSPy paraphrasing
- `massgen_runs_massgen.yaml` - Meta-coordination configuration
- `massgen_suggests_to_improve_massgen.yaml` - Autonomous MassGen experiments

**Key Features:**
- **Automation Mode**: Clean structured output (~10 lines vs 250-3,000+) for LLM agents with `--automation` flag
- **DSPy Integration**: Question paraphrasing with three strategies (diverse/balanced/conservative) for multi-agent diversity
- **Meta-Coordination**: MassGen running MassGen for self-improvement workflows
- **Status Monitoring**: Real-time `status.json` updated every 2 seconds with phase tracking and voting results

**Try It:**
```bash
# DSPy question paraphrasing for multi-agent diversity
massgen --config @examples/basic/multi/three_agents_dspy_enabled "Explain the differences between transformer architecture and recurrent neural networks"

# Automation mode - clean output for LLM agents
massgen --automation --config @examples/tools/todo/example_task_todo "Create a simple HTML page about Bob Dylan"

# Meta-coordination - MassGen running MassGen
massgen --config @examples/meta/massgen_runs_massgen "Run a MassGen experiment to create a webpage about Bob Dylan"
```

### v0.1.7
**New Features:** Agent Task Planning & Background Execution

**Configuration Files:**
- `example_task_todo.yaml` - Task planning with dependency management
- `background_shell_demo.yaml` - Background command execution demo

**Key Features:**
- **Agent Task Planning**: MCP-based planning tools with task dependencies and status tracking
- **Background Shell Execution**: Persistent shell sessions for long-running commands
- **Preemption Coordination**: Interrupt coordination without full restart

**Try It:**
```bash
# Agent task planning for complex multi-step projects
massgen --config @examples/configs/tools/todo/example_task_todo.yaml "Create a website about Bob Dylan"

# Background shell execution for parallel long-running commands
uv run massgen --config massgen/configs/tools/code-execution/background_shell_demo.yaml "Run three experiments in parallel using background shell commands: test sorting algorithms (bubble, quick, merge) on arrays of size 10000. Compare their execution times."
```

### v0.1.6
**New Features:** Framework Interoperability & Backend Refactoring

**Configuration Files:**
- `ag2_lesson_planner_example.yaml` - AG2 nested chat as custom tool (supports streaming)
- `langgraph_lesson_planner_example.yaml` - LangGraph workflows integrated as tools
- `agentscope_lesson_planner_example.yaml` - AgentScope agent system integration
- `openai_assistant_lesson_planner_example.yaml` - OpenAI Assistants as tools
- `smolagent_lesson_planner_example.yaml` - HuggingFace SmoLAgent integration
- `ag2_and_langgraph_lesson_planner.yaml` - Multi-framework collaboration (AG2 + LangGraph)
- `ag2_and_openai_assistant_lesson_planner.yaml` - AG2 + OpenAI Assistants combination
- `two_models_with_tools_example.yaml` - Multiple models with custom tools

**Key Features:**
- **Framework Interoperability**: Use agents from external frameworks (AG2, LangGraph, AgentScope, OpenAI Assistants, SmoLAgent) as MassGen tools
- **Streaming Support**: AG2 supports streaming; other frameworks return complete results
- **Configuration Validator**: Pre-flight YAML validation with detailed error messages
- **Unified Tool Execution**: ToolExecutionConfig dataclass for consistent tool handling
- **Gemini Simplification**: Major backend cleanup reducing codebase by 1,598 lines

**Try It:**
```bash
# Use AG2 agents for lesson planning (supports streaming)
# Requirements: pip install pyAG2, OPENAI_API_KEY must be set
massgen --config massgen/configs/tools/custom_tools/ag2_lesson_planner_example.yaml "Create a lesson plan for photosynthesis"

# Use LangGraph workflows as tools
# Requirements: pip install langgraph langchain-openai langchain-core, OPENAI_API_KEY must be set
massgen --config massgen/configs/tools/custom_tools/langgraph_lesson_planner_example.yaml "Create a lesson plan for photosynthesis"

# Use AgentScope multi-agent framework as tools
# Requirements: pip install agentscope, OPENAI_API_KEY must be set
massgen --config massgen/configs/tools/custom_tools/agentscope_lesson_planner_example.yaml "Create a lesson plan for photosynthesis"

# Use OpenAI Assistants API as tools
# Requirements: pip install openai, OPENAI_API_KEY must be set
massgen --config massgen/configs/tools/custom_tools/openai_assistant_lesson_planner_example.yaml "Create a lesson plan for photosynthesis"

# Use SmolAgent (HuggingFace) as tools
# Requirements: pip install smolagents, OPENAI_API_KEY must be set
massgen --config massgen/configs/tools/custom_tools/smolagent_lesson_planner_example.yaml "Create a lesson plan for photosynthesis"

# Combine multiple frameworks
# Requirements: pip install pyAG2 langgraph langchain-openai langchain-core, OPENAI_API_KEY must be set
massgen --config massgen/configs/tools/custom_tools/ag2_and_langgraph_lesson_planner.yaml "Create a lesson plan for photosynthesis"
```

### v0.1.5
**New Features:** Memory System with Semantic Retrieval

**Configuration Files:**
- `gpt5mini_gemini_context_window_management.yaml` - Multi-agent with automatic context compression
- `gpt5mini_gemini_research_to_implementation.yaml` - Research-to-implementation workflow (featured in case study)
- `gpt5mini_high_reasoning_gemini.yaml` - High reasoning agents with memory integration
- `gpt5mini_gemini_baseline_research_to_implementation.yaml` - Baseline research workflow
- `single_agent_compression_test.yaml` - Testing context compression behavior

**Key Features:**
- **Long-Term Memory**: Semantic storage via mem0 with vector database integration
- **Context Compression**: Automatic compression when approaching token limits
- **Cross-Agent Sharing**: Agents learn from each other's experiences
- **Session Management**: Memory persistence across conversations

**Try it:**
```bash
# Install or upgrade
pip install --upgrade massgen

# Multi-agent collaboration with context compression
massgen --config @examples/memory/gpt5mini_gemini_context_window_management \
  "Analyze the MassGen codebase comprehensively. Create an architecture document that explains: (1) Core components and their responsibilities, (2) How different modules interact, (3) Key design patterns used, (4) Main entry points and request flows. Read > 30 files to build a complete understanding."

# Research-to-implementation workflow with memory persistence
# Prerequisites: Start Qdrant and crawl4ai Docker containers
docker run -d -p 6333:6333 -p 6334:6334 \
  -v $(pwd)/.massgen/qdrant_storage:/qdrant/storage:z qdrant/qdrant
docker run -d -p 11235:11235 --name crawl4ai --shm-size=1g unclecode/crawl4ai:latest

# Session 1 - Research phase:
massgen --config @examples/memory/gpt5mini_gemini_research_to_implementation \
  "Use crawl4ai to research the latest multi-agent AI papers and techniques from 2025. Focus on: coordination mechanisms, voting strategies, tool-use patterns, and architectural innovations."

# Session 2 - Implementation analysis (continue in same session):
# "Based on the multi-agent research from earlier, which techniques should we implement in MassGen to make it more state-of-the-art? Consider MassGen's current architecture and what would be most impactful."
```

→ See [Multi-Turn Persistent Memory Case Study](../../docs/source/examples/case_studies/multi-turn-persistent-memory.md) for detailed analysis

```bash
# Test automatic context compression
massgen --config @examples/memory/single_agent_compression_test \
  "Analyze the MassGen codebase comprehensively. Create an architecture document that explains: (1) Core components and their responsibilities, (2) How different modules interact, (3) Key design patterns used, (4) Main entry points and request flows. Read > 30 files to build a complete understanding."
```

### v0.1.4
**New Features:** Multimodal Generation Tools, Binary File Protection, Crawl4AI Integration

**Configuration Files:**
- `text_to_image_generation_single.yaml` / `text_to_image_generation_multi.yaml` - Image generation
- `text_to_video_generation_single.yaml` / `text_to_video_generation_multi.yaml` - Video generation
- `text_to_speech_generation_single.yaml` / `text_to_speech_generation_multi.yaml` - Audio generation
- `text_to_file_generation_single.yaml` / `text_to_file_generation_multi.yaml` - Document generation
- `crawl4ai_example.yaml` - Web scraping configuration

**Key Features:**
- **Generation Tools**: Create images, videos, audio, and documents using OpenAI APIs
- **Binary File Protection**: Automatic blocking prevents text tools from reading 40+ binary file types
- **Web Scraping**: Crawl4AI integration for intelligent content extraction
- **Enhanced Security**: Smart tool suggestions guide users to appropriate specialized tools

**Try it:**
```bash
# Generate an image from text
massgen --config @examples/tools/custom_tools/multimodal_tools/text_to_image_generation_single \
  "Please generate an image of a cat in space."

# Generate a video from text
massgen --config @examples/tools/custom_tools/multimodal_tools/text_to_video_generation_single \
  "Generate a 4 seconds video with neon-lit alley at night, light rain, slow push-in, cinematic."

# Generate documents (PDF, DOCX, etc.)
massgen --config @examples/tools/custom_tools/multimodal_tools/text_to_file_generation_single \
  "Please generate a comprehensive technical report about the latest developments in Large Language Models (LLMs)."
```

### v0.1.3
**New Features:** Post-Evaluation Workflow, Custom Multimodal Understanding Tools, Docker Sudo Mode

**Configuration Files:**
- `understand_image.yaml`, `understand_audio.yaml`, `understand_video.yaml`, `understand_file.yaml`

**Key Features:**
- **Post-Evaluation Tools**: Submit and restart capabilities for winning agents
- **Multimodal Understanding**: Analyze images, audio, video, and documents
- **Docker Sudo Mode**: Execute privileged commands in containers

**Try it:**
```bash
# Try multimodal image understanding
massgen --config @examples/tools/custom_tools/multimodal_tools/understand_image \
  "Please summarize the content in this image."
```

### v0.1.2
**New Features:** Intelligent Planning Mode, Claude 4.5 Haiku Support, Grok Web Search Improvements

**Configuration Files:**
- `configs/tools/planning/` - 5 planning mode configurations with selective blocking
- `configs/basic/multi/three_agents_default.yaml` - Updated with Grok-4-fast model

**Documentation:**
- `docs/dev_notes/intelligent_planning_mode.md` - Complete intelligent planning mode guide

**Key Features:**
- **Intelligent Planning Mode**: Automatic analysis of question irreversibility for dynamic MCP tool blocking
- **Selective Tool Blocking**: Granular control over which MCP tools are blocked during planning
- **Enhanced Safety**: Read-only operations allowed, write operations blocked during coordination
- **Latest Models**: Claude 4.5 Haiku support with updated model priorities

**Try it:**
```bash
# Try intelligent planning mode with MCP tools
# (Please read the YAML file for required API keys: DISCORD_TOKEN, OPENAI_API_KEY, etc.)
massgen --config @examples/tools/planning/five_agents_discord_mcp_planning_mode \
  "Check recent messages in our development channel, summarize the discussion, and post a helpful response about the current topic."

# Use latest Claude 4.5 Haiku model
# (Requires ANTHROPIC_API_KEY in .env)
massgen --model claude-haiku-4-5-20251001 \
  "Summarize the latest AI developments"
```

### v0.1.1
**New Features:** Custom Tools System, Voting Sensitivity Controls, Interactive Configuration Builder

**Key Features:**
- Custom tools registration using `ToolManager` class
- Three-tier voting system (lenient/balanced/strict)
- 40+ custom tool examples
- Backend capabilities registry

**Try it:**
```bash
# Try custom tools with agents
massgen --config @examples/tools/custom_tools/claude_custom_tool_example \
  "whats the sum of 123 and 456?"

# Test voting sensitivity controls
massgen --config @examples/voting/gemini_gpt_voting_sensitivity \
  "Your question here"
```

### v0.1.0
**New Features:** PyPI Package Release, Comprehensive Documentation, Interactive Setup Wizard, Enhanced CLI

**Key Features:**
- Official PyPI distribution: `pip install massgen` with global CLI command
- Interactive Setup Wizard with smart defaults for API keys and model selection
- Comprehensive documentation at [docs.massgen.ai](https://docs.massgen.ai/)
- Simplified command syntax: `massgen "question"` with `@examples/` prefix

**Try it:**
```bash
pip install massgen && massgen
massgen --config @examples/basic/multi/three_agents_default "What is 2+2?"
```

### v0.0.32
**New Features:** Docker Execution Mode, MCP Architecture Refactoring, Claude Code Docker Integration

**Configuration Files:**
- `massgen/configs/tools/code-execution/docker_simple.yaml` - Basic single-agent Docker execution
- `massgen/configs/tools/code-execution/docker_multi_agent.yaml` - Multi-agent Docker deployment with isolated containers
- `massgen/configs/tools/code-execution/docker_with_resource_limits.yaml` - Resource-constrained Docker setup with CPU/memory limits
- `massgen/configs/tools/code-execution/docker_claude_code.yaml` - Claude Code with Docker execution and automatic tool management
- `massgen/configs/debug/code_execution/docker_verification.yaml` - Docker setup verification configuration

**Key Features:**
- Docker-based command execution with container isolation preventing host filesystem access
- Persistent state across conversation turns (packages stay installed)
- Multi-agent support with dedicated containers per agent
- Resource limits (CPU, memory) and network isolation modes (none/bridge/host)
- Simplified MCP architecture with MCPClient (renamed from MultiMCPClient)
- Claude Code automatic Bash tool disablement in Docker mode

**Try it:**
```bash
# Docker isolated execution - secure command execution in containers
massgen --config @examples/tools/code-execution/docker_simple \
  "Write a factorial function and test it"

# Multi-agent Docker deployment - each agent in isolated container
massgen --config @examples/tools/code-execution/docker_multi_agent \
  "Build a Flask website about Bob Dylan"

# Claude Code with Docker - automatic tool management
massgen --config @examples/tools/code-execution/docker_claude_code \
  "Build a Flask website about Bob Dylan"

# Resource-limited Docker execution - production-ready setup
massgen --config @examples/tools/code-execution/docker_with_resource_limits \
  "Fetch data from an API and analyze it"
```

### v0.0.31
**New Features:** Universal Code Execution, AG2 Group Chat Integration, Audio & Video Generation Tools

**Configuration Files:**
- `massgen/configs/tools/code-execution/basic_command_execution.yaml` - Universal command execution across all backends
- `massgen/configs/debug/code_execution/command_filtering_whitelist.yaml` - Command execution with whitelist filtering
- `massgen/configs/debug/code_execution/command_filtering_blacklist.yaml` - Command execution with blacklist filtering
- `massgen/configs/tools/code-execution/code_execution_use_case_simple.yaml` - Multi-agent web automation with code execution
- `massgen/configs/ag2/ag2_groupchat.yaml` - Native AG2 group chat with multi-agent conversations
- `massgen/configs/ag2/ag2_groupchat_gpt.yaml` - Mixed MassGen and AG2 agents (GPT-5-nano + AG2 team)
- `massgen/configs/basic/single/single_gpt4o_audio_generation.yaml` - Single agent audio generation with GPT-4o
- `massgen/configs/basic/multi/gpt4o_audio_generation.yaml` - Multi-agent audio generation with GPT-4o
- `massgen/configs/basic/single/single_gpt4o_video_generation.yaml` - Video generation with OpenAI Sora-2

**Case Study:**
- [Universal Code Execution via MCP](../../docs/source/examples/case_studies/universal-code-execution-mcp.md)

**Key Features:**
- Universal `execute_command` tool works across Claude, Gemini, OpenAI (Response API), and Chat Completions providers (Grok, ZAI, etc.)
- Audio tools: text-to-speech, audio transcription, audio generation
- Video tools: text-to-video generation via Sora-2 API
- Code execution in planning mode for safer coordination
- Enhanced file operation tracking and path permission management

**Try it:**
```bash
# Universal code execution - works with any backend
massgen --config @examples/tools/code-execution/basic_command_execution \
  "Write a Python function to calculate factorial and test it"

# AG2 group chat - multi-agent conversations
massgen --config @examples/ag2/ag2_groupchat \
  "Write a Python function to calculate factorial."

# Mixed MassGen + AG2 agents - GPT-5-nano collaborating with AG2 team
massgen --config @examples/ag2/ag2_groupchat_gpt \
  "Write a Python function to calculate factorial."

# Audio generation
massgen --config @examples/basic/single/single_gpt4o_audio_generation \
  "I want to you tell me a very short introduction about Sherlock Homes in one sentence, and I want you to use emotion voice to read it out loud."

# Video generation with Sora-2
massgen --config @examples/basic/single/single_gpt4o_video_generation \
  "Generate a 4 seconds video with neon-lit alley at night, light rain, slow push-in, cinematic."
```

### v0.0.30
**New Features:** Multimodal Audio and Video Support, Claude Agent SDK Update, Qwen API Integration
- `massgen/configs/basic/single/single_openrouter_audio_understanding.yaml` - Audio understanding with OpenRouter
- `massgen/configs/basic/single/single_qwen_video_understanding.yaml` - Video understanding with Qwen API
- `massgen/configs/basic/single/single_gemini2.5pro.yaml` - Gemini 2.5 Pro single agent setup
- `massgen/configs/tools/filesystem/cc_gpt5_gemini_filesystem.yaml` - Claude Code, GPT-5, and Gemini filesystem collaboration
- `massgen/configs/ag2/ag2_case_study.yaml` - AG2 framework integration case study
- `massgen/configs/debug/test_sdk_migration.yaml` - Claude Code SDK migration testing
- Updated from `claude-code-sdk>=0.0.19` to `claude-agent-sdk>=0.0.22`
- Audio/video multimodal support for Chat Completions and Claude backends
- Qwen API provider integration with video understanding capabilities

**Try it:**
```bash
# Audio understanding with OpenRouter
massgen --config @examples/basic/single/single_openrouter_audio_understanding \
  "What is in this recording?"

# Video understanding with Qwen API
massgen --config @examples/basic/single/single_qwen_video_understanding \
  "Describe what happens in this video"

# Multi-agent filesystem collaboration
massgen --config @examples/tools/filesystem/cc_gpt5_gemini_filesystem \
  "Create a comprehensive project with documentation"
```

### v0.0.29
**New Features:** MCP Planning Mode, File Operation Safety, Enhanced MCP Tool Filtering
- `massgen/configs/tools/planning/five_agents_discord_mcp_planning_mode.yaml` - Five agents with Discord MCP in planning mode
- `massgen/configs/tools/planning/five_agents_filesystem_mcp_planning_mode.yaml` - Five agents with filesystem MCP in planning mode
- `massgen/configs/tools/planning/five_agents_notion_mcp_planning_mode.yaml` - Five agents with Notion MCP in planning mode
- `massgen/configs/tools/planning/five_agents_twitter_mcp_planning_mode.yaml` - Five agents with Twitter MCP in planning mode
- `massgen/configs/tools/planning/gpt5_mini_case_study_mcp_planning_mode.yaml` - Planning mode case study configuration
- `massgen/configs/tools/mcp/five_agents_travel_mcp_test.yaml` - Five agents testing travel-related MCP tools
- `massgen/configs/tools/mcp/five_agents_weather_mcp_test.yaml` - Five agents testing weather MCP tools
- `massgen/configs/debug/skip_coordination_test.yaml` - Debug configuration for testing coordination skipping
- New `CoordinationConfig` class with `enable_planning_mode` flag for safer MCP coordination
- New `FileOperationTracker` class for read-before-delete enforcement
- Enhanced PathPermissionManager with operation tracking methods

**Case Study:** [MCP Planning Mode](../../docs/source/examples/case_studies/mcp-planning-mode.md)

**Try it:**
```bash
# Planning mode with filesystem operations
massgen --config @examples/tools/planning/five_agents_filesystem_mcp_planning_mode \
  "Create a comprehensive project structure with documentation"

# Multi-agent weather MCP testing
massgen --config @examples/tools/mcp/five_agents_weather_mcp_test \
  "Compare weather forecasts for New York, London, and Tokyo"

# Planning mode with Twitter integration
massgen --config @examples/tools/planning/five_agents_twitter_mcp_planning_mode \
  "Draft and plan tweet series about AI advancements"
```

### v0.0.28
**New Features:** AG2 Framework Integration, External Agent Backend, Code Execution Support
- `massgen/configs/ag2/ag2_single_agent.yaml` - Basic single AG2 agent setup
- `massgen/configs/ag2/ag2_coder.yaml` - AG2 agent with code execution capabilities
- `massgen/configs/ag2/ag2_coder_case_study.yaml` - Multi-agent setup with AG2 and Gemini
- `massgen/configs/ag2/ag2_gemini.yaml` - AG2-Gemini hybrid configuration
- New `massgen/adapters/` module for external framework integration
- New `ExternalAgentBackend` class bridging MassGen with external frameworks
- Multiple code executor types: LocalCommandLineCodeExecutor, DockerCommandLineCodeExecutor, JupyterCodeExecutor, YepCodeCodeExecutor

**Case Study:** [AG2 Framework Integration](../../docs/source/examples/case_studies/ag2-framework-integration.md)

**Try it:**
```bash
# AG2 single agent with code execution
massgen --config @examples/ag2/ag2_coder \
  "Create a factorial function and calculate the factorial of 8. Show the result?"

# Mixed team: AG2 agent + Gemini agent
massgen --config @examples/ag2/ag2_gemini \
  "what is quantum computing?"

# AG2 case study: Compare AG2 and MassGen (requires external dependency)
uv pip install -e ".[external]"
massgen --config @examples/ag2/ag2_coder_case_study \
  "Output a summary comparing the differences between AG2 (https://github.com/ag2ai/ag2) and MassGen (https://github.com/Leezekun/MassGen) for LLM agents."
```

### v0.0.27
**New Features:** Multimodal Support (Image Processing), File Upload and File Search, Claude Sonnet 4.5
- `massgen/configs/basic/multi/gpt4o_image_generation.yaml` - Multi-agent image generation
- `massgen/configs/basic/multi/gpt5nano_image_understanding.yaml` - Multi-agent image understanding
- `massgen/configs/basic/single/single_gpt4o_image_generation.yaml` - Single agent image generation
- `massgen/configs/basic/single/single_gpt5nano_image_understanding.yaml` - Single agent image understanding
- `massgen/configs/basic/single/single_gpt5nano_file_search.yaml` - File search for document Q&A
- New `stream_chunk` module for multimodal content architecture
- Enhanced `read_multimodal_files` MCP tool for image processing

**Try it:**
```bash
# Image generation with single agent
massgen --config @examples/basic/single/single_gpt4o_image_generation \
  "Generate an image of gray tabby cat hugging an otter with an orange scarf. Limit image size within 5kb."

# Image understanding with multiple agents
massgen --config @examples/basic/multi/gpt5nano_image_understanding \
  "Please summarize the content in this image."

# File search for document Q&A
massgen --config @examples/basic/single/single_gpt5nano_file_search \
  "What is humanity's last exam score for OpenAI Deep Research? Also, provide details about the other models mentioned in the PDF?"
```

### v0.0.26
**New Features:** File Deletion, Protected Paths, File-Based Context Paths
- `massgen/configs/tools/filesystem/gemini_gpt5nano_protected_paths.yaml` - Protected paths configuration
- `massgen/configs/tools/filesystem/gemini_gpt5nano_file_context_path.yaml` - File-based context paths
- `massgen/configs/tools/filesystem/grok4_gpt5_gemini_filesystem.yaml` - Multi-agent filesystem collaboration
- New MCP tools: `delete_file`, `delete_files_batch`, `compare_directories`, `compare_files`

**Try it:**
```bash
# Protected paths - keep reference files safe
massgen --config @examples/tools/filesystem/gemini_gpt5nano_protected_paths \
  "Review the HTML and CSS files, then improve the styling"

# File-based context paths - grant access to specific files
massgen --config @examples/tools/filesystem/gemini_gpt5nano_file_context_path \
  "Analyze the CSS file and make modern improvements"
```

### v0.0.25
**New Features:** Multi-Turn Filesystem Support, SGLang Backend Integration
- `massgen/configs/tools/filesystem/multiturn/two_gemini_flash_filesystem_multiturn.yaml` - Multi-turn with Gemini agents
- `massgen/configs/tools/filesystem/multiturn/grok4_gpt5_claude_code_filesystem_multiturn.yaml` - Three-agent multi-turn
- `massgen/configs/basic/multi/two_qwen_vllm_sglang.yaml` - Mixed vLLM and SGLang deployment
- Automatic `.massgen` directory management for persistent conversation context
- Enhanced path permissions with `will_be_writable` flag and smart exclusion patterns

**Case Study:** [Multi-Turn Filesystem Support](../../docs/source/examples/case_studies/multi-turn-filesystem-support.md)
```bash
# Turn 1 - Initial creation
Turn 1: Make a website about Bob Dylan
# Creates workspace and saves state to .massgen/sessions/

# Turn 2 - Enhancement based on Turn 1
Turn 2: Can you (1) remove the image placeholder? we will not use image directly. (2) generally improve the appearance so it is more engaging, (3) make it longer and add an interactive element
# Note: Unlike pre-v0.0.25, Turn 2 automatically loads Turn 1's workspace state
# Agents can directly access and modify files from the previous turn
```

### v0.0.24
**New Features:** vLLM Backend Support, Backend Utility Modules
- `massgen/configs/basic/multi/three_agents_vllm.yaml` - vLLM with Cerebras and ZAI backends
- `massgen/configs/basic/multi/two_qwen_vllm.yaml` - Dual vLLM agents for testing
- POE provider support for accessing multiple AI models through single platform
- GPT-5-Codex model recognition for enhanced code generation capabilities

**Try it:**
```bash
# Try vLLM backend with local models (requires vLLM server running)
# First start vLLM server: python -m vllm.entrypoints.openai.api_server --model Qwen/Qwen3-0.6B --host 0.0.0.0 --port 8000
massgen --config @examples/basic/multi/two_qwen_vllm \
  "What is machine learning?"
```

### v0.0.23
**New Features:** Backend Architecture Refactoring, Formatter Module
- Major code consolidation with new `base_with_mcp.py` class reducing ~1,932 lines across backends
- Extracted message and tool formatting logic into dedicated `massgen/formatter/` module
- Streamlined chat_completions.py, claude.py, and response.py for better maintainability

### v0.0.22
**New Features:** Workspace Copy Tools via MCP, Configuration Organization
- All configs now organized by provider & use case (basic/, providers/, tools/, teams/)
- Use same configs as v0.0.21 for compatibility, but now with improved performance

**Case Study:** [Advanced Filesystem with User Context Path Support](../../docs/source/examples/case_studies/v0.0.21-v0.0.22-filesystem-permissions.md)
```bash
# Multi-agent collaboration with granular filesystem permissions
massgen --config @examples/tools/filesystem/gpt5mini_cc_fs_context_path "Enhance the website in massgen/configs/resources with: 1) A dark/light theme toggle with smooth transitions, 2) An interactive feature that helps users engage with the blog content (your choice - could be search, filtering by topic, reading time estimates, social sharing, reactions, etc.), and 3) Visual polish with CSS animations or transitions that make the site feel more modern and responsive. Use vanilla JavaScript and be creative with the implementation details."
```

### v0.0.21
**New Features:** Advanced Filesystem Permissions, Grok MCP Integration
- `massgen/configs/tools/mcp/grok3_mini_mcp_example.yaml` - Grok with MCP tools
- `massgen/configs/tools/filesystem/fs_permissions_test.yaml` - Permission-controlled file sharing
- `massgen/configs/tools/filesystem/claude_code_context_sharing.yaml` - Agent workspace sharing

**Try it:**
```bash
# Grok with MCP tools
massgen --config @examples/tools/mcp/grok3_mini_mcp_example \
  "What's the weather in Tokyo?"
```

### v0.0.20
**New Features:** Claude MCP Support with Recursive Execution
- `massgen/configs/tools/mcp/claude_mcp_example.yaml` - Claude with MCP tools
- `massgen/configs/tools/mcp/claude_mcp_test.yaml` - Testing Claude MCP capabilities

**Try it:**
```bash
# Claude with MCP tools
massgen --config @examples/tools/mcp/claude_mcp_example \
  "What's the current weather?"
```

### v0.0.17
**New Features:** OpenAI MCP Integration
- `massgen/configs/tools/mcp/gpt5_nano_mcp_example.yaml` - GPT-5 with MCP tools
- `massgen/configs/tools/mcp/gpt5mini_claude_code_discord_mcp_example.yaml` - Multi-agent MCP

**Try it:**
```bash
# Claude with MCP tools
massgen --config @examples/tools/mcp/gpt5_nano_mcp_example \
  "whats the weather of Tokyo?"
```


### v0.0.16
**New Features:** Unified Filesystem Support with MCP Integration
**Case Study:** [Cross-Backend Collaboration with Gemini MCP Filesystem](../../docs/source/examples/case_studies/unified-filesystem-mcp-integration.md)
```bash
# Gemini and Claude Code agents with unified filesystem via MCP
massgen --config @examples/tools/mcp/gemini_mcp_filesystem_test_with_claude_code "Create a presentation that teaches a reinforcement learning algorithm and output it in LaTeX Beamer format. No figures should be added."
```

### v0.0.15
**New Features:** Gemini MCP Integration
- `massgen/configs/tools/mcp/gemini_mcp_example.yaml` - Gemini with weather MCP
- `massgen/configs/tools/mcp/multimcp_gemini.yaml` - Multiple MCP servers

### v0.0.12 - v0.0.14
**New Features:** Enhanced Logging and Workspace Management
**Case Study:** [Claude Code Workspace Management with Comprehensive Logging](../../docs/source/examples/case_studies/claude-code-workspace-management.md)
```bash
# Multi-agent Claude Code collaboration with enhanced workspace isolation
massgen --config @examples/tools/filesystem/claude_code_context_sharing "Create a website about a diverse set of fun facts about LLMs, placing the output in one index.html file"
```

### v0.0.10
**New Features:** Azure OpenAI Support
- `massgen/configs/providers/azure/azure_openai_single.yaml` - Azure single agent
- `massgen/configs/providers/azure/azure_openai_multi.yaml` - Azure multi-agent

### v0.0.7
**New Features:** Local Model Support with LM Studio
- `massgen/configs/providers/local/lmstudio.yaml` - Local model inference

### v0.0.5
**New Features:** Claude Code Integration
- `massgen/configs/tools/filesystem/claude_code_single.yaml` - Claude Code with dev tools
- `massgen/configs/tools/filesystem/claude_code_flash2.5.yaml` - Multi-agent with Claude Code

## Naming Convention

To improve clarity and discoverability, we follow this naming pattern:

**Format: `{agents}_{features}_{description}.yaml`**

### 1. Agents (who's participating)
- `single-{provider}` - Single agent (e.g., `single-claude`, `single-gemini`)
- `{provider1}-{provider2}` - Two agents (e.g., `claude-gemini`, `gemini-gpt5`)
- `three-mixed` - Three agents from different providers
- `team-{type}` - Specialized teams (e.g., `team-creative`, `team-research`)

### 2. Features (what tools/capabilities)
- `basic` - No special tools, just conversation
- `mcp` - MCP server integration
- `mcp-{service}` - Specific MCP service (e.g., `mcp-discord`, `mcp-weather`)
- `mcp-multi` - Multiple MCP servers
- `websearch` - Web search enabled
- `codeexec` - Code execution/interpreter
- `filesystem` - File operations and workspace management

### 3. Description (purpose/context - optional)
- `showcase` - Demonstration/getting started example
- `test` - Testing configuration
- `research` - Research and analysis tasks
- `dev` - Development and coding tasks
- `collab` - Collaboration example

### Examples
```
# Current → Suggested
three_agents_default.yaml → three-mixed_basic_showcase.yaml
grok3_mini_mcp_example.yaml → single-grok_mcp-weather_test.yaml
claude_code_discord_mcp_example.yaml → single-claude_mcp-discord_demo.yaml
gpt5mini_claude_code_discord_mcp_example.yaml → claude-gpt5_mcp-discord_collab.yaml
```

**Note:** Existing configs maintain their current names for compatibility. New configs should follow this convention.

## Additional Documentation

For detailed setup guides:
- Discord MCP: `docs/DISCORD_MCP_SETUP.md`
- Twitter MCP: `docs/TWITTER_MCP_ENESCINAR_SETUP.md`
- Main README: See repository root for comprehensive documentation
