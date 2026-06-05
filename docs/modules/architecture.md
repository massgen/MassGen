# Architecture

## Core Flow

```text
cli.py -> orchestrator.py -> chat_agent.py -> backend/*.py
                |
        coordination_tracker.py (voting, consensus)
                |
        mcp_tools/ (tool execution)
```

## Key Components

**Orchestrator** (`orchestrator.py`): Central coordinator managing parallel agent execution, voting, and consensus detection. Handles coordination phases: initial_answer -> enforcement (voting) -> presentation. When an orchestrator timeout fires after agents have already produced answers, it salvages the best available existing answer directly instead of starting a new presenter pass.

**Backends** (`backend/`): Provider-specific implementations. All inherit from `base.py`. Add new backends by:
1. Create `backend/new_provider.py` inheriting from base
2. Register in `backend/__init__.py`
3. Add model mappings to `massgen/utils.py`
4. Add capabilities to `backend/capabilities.py`
5. Update `config_validator.py`

See also: [Backend Registration Checklist in CLAUDE.md Memory](../../CLAUDE.md)

**MCP Integration** (`mcp_tools/`): Model Context Protocol for external tools. `client.py` handles multi-server connections, `security.py` validates operations. Some tools have dual paths: SDK (in-process, for ClaudeCode) and stdio (config.toml-based, for Codex). For Codex, the model-facing MCP connections live inside the Codex CLI session, while orchestrator-managed operations (for example managed round-evaluator spawns) use a separate host-side MCP client built from the same stdio server configs. **Stdio MCP servers run inside Docker where `massgen` is NOT installed** — never import from `massgen` in stdio servers. Pre-compute any needed values in the orchestrator and pass via JSON specs files. Also note Codex sometimes sends tool args as JSON strings instead of dicts — always add a `json.loads()` fallback.

**Streaming Buffer** (`backend/_streaming_buffer_mixin.py`): Tracks partial responses during streaming for compression recovery.

## Backend Hierarchy

```text
base.py (abstract interface)
    +-- base_with_custom_tool_and_mcp.py (tool + MCP support)
    |       |-- response.py (OpenAI Response API)
    |       |-- chat_completions.py (generic OpenAI-compatible)
    |       |-- claude.py (Anthropic)
    |       |-- gemini.py (Google)
    |       +-- grok.py (xAI)
    +-- claude_code.py (Claude Code SDK; native tools + SDK MCP path)
    +-- codex.py (OpenAI Codex CLI; native tools + workspace .codex MCP path)
```

## Coordination as Evolutionary Search

MassGen's coordination loop maps to a genetic algorithm where the "population" is the set of agent answers and each round is a generation:

| GA Concept | MassGen Equivalent |
|---|---|
| **Population** | Current set of agent answers |
| **Selection** | Voting — agents evaluate and vote for the strongest answer |
| **Crossover** | Synthesis — agents combine strengths from multiple answers into a new one |
| **Mutation** | Variation — agents try different approaches for key parts of the solution |
| **Fitness** | Checklist evaluation (gap analysis, ideal version comparison) |
| **Speciation** | Persona generation — agents with different perspectives/methodologies explore different regions of the solution space |

### Diversity mechanisms

Without active diversity pressure, agents converge on the same approach and produce increasingly similar answers (the equivalent of a GA losing population diversity). MassGen maintains diversity through two layers:

1. **Persona generation** (explicit, configurable): When enabled, assigns agents different perspectives (`diversity_mode: perspective`), solution types (`implementation`), or working methodologies (`methodology`). This is the strongest diversity lever — it shapes how agents think from the start.

2. **Default prompt instructions** (always active): The evaluation prompts include a "Fresh Approach Consideration" that encourages agents to vary their approach for key parts rather than always refining the current best. The `new_answer` instruction explicitly presents "Vary" as a valid strategy alongside "Improve."

The balance between convergence (selection + synthesis) and diversity (variation + personas) is key. Too much convergence produces polished mediocrity. Too much diversity prevents answers from maturing. The checklist-gated voting controls when agents stop iterating, while personas and variation instructions control how different each iteration is.

## Agent Statelessness and Anonymity

Agents are STATELESS and ANONYMOUS across coordination rounds. Each round:
- Agent gets a fresh LLM invocation with no memory of previous rounds
- Agent does not know which agent it is (all identities are anonymous)
- Cross-agent information (answers, workspaces) is presented anonymously
- System prompts and branch names must NOT reveal agent identity or round history

## Logging Architecture: Session-Scoped Isolation

Each `massgen.run()` call (and each CLI process) gets an isolated `LoggingSession` object that owns all mutable logging state. This enables safe concurrent in-process execution via `asyncio.gather(run(), run())`.

### LoggingSession

`LoggingSession` (`massgen/logger_config.py`) is a dataclass holding per-run state:
- `log_base_session_dir` / `log_session_dir` — where this run's files go
- `current_turn` / `current_attempt` — for file sink path construction
- `main_log_handler_id` / `streaming_log_handler_id` — loguru handler IDs owned by this session
- `event_emitter` — the `EventEmitter` instance scoped to this run
- `debug_mode` — whether `--debug` was passed

The active session is stored in a `ContextVar[LoggingSession]` (`_current_session`). Each asyncio task inherits its parent's context, so concurrent tasks each see their own session without interfering.

### Session-Filtered Loguru Sinks

File sinks added during `setup_logging()` use a `_make_session_filter(session_id)` filter: only log records bound with `logger.bind(session_id=X)` reach session X's file. Use `session_logger()` (which returns `logger.bind(session_id=active_session.session_id)`) for all log calls that should be routed to the current session's file.

### Event Emitter Scoping

`get_event_emitter()` checks the active `LoggingSession.event_emitter` first, falling back to the global `_global_emitter`. All ~40 call sites get session scoping automatically via this single lookup point.

### Backward Compatibility

All existing public API functions (`get_log_session_dir`, `set_log_turn`, `set_log_attempt`, `reset_logging_session`, etc.) check the ContextVar first and fall back to legacy module globals. This Phase 1 migration keeps single-process CLI behavior unchanged.

### Multi-Process Isolation

Two simultaneous `uv run massgen` processes are isolated by:
1. **Session registry locking**: `~/.massgen/sessions.json` uses `fcntl.flock` (POSIX) for atomic read-modify-write under exclusive lock (`massgen/session/_registry.py`).
2. **Snapshot path scoping**: `snapshot_storage` from YAML is automatically scoped by the log session root name (microsecond timestamp) via `_scope_snapshot_storage()` in `cli.py`, producing paths like `.massgen/snapshots/log_20260301_XXX/agent_a/`.

**Immutable versioned snapshots.** Each agent's public snapshot path `<base>/<agent_id>` is a **symlink** to an immutable version directory under `<base>/.versions/<agent_id>/v<N>`. `save_snapshot` publishes a fresh `v<N>` and atomically repoints the symlink; it never rewrites a published version in place. The peer-context copy (`SnapshotManager.copy_all_snapshots_to_temp_workspace`) `acquire`s (refcounts) the current version before its offloaded `copytree`, so a concurrent `save_snapshot` republish on another agent cannot delete or mutate the source mid-copy. This is the fix for the B1 read-during-write race introduced when the copy was offloaded to `asyncio.to_thread`. Coordinated by `SnapshotVersionStore` (`massgen/filesystem_manager/_snapshot_version_store.py`); the symlink is transparent to all other readers, so the on-disk layout consumers see is unchanged. On platforms without symlink support the store falls back to a direct copy (no race protection). The interrupted-turn partial save also publishes through the store (it must not `rmtree` the symlink).

**Caveat — late writers.** `save_snapshot` and the interrupted-turn save are the only full publishers. A few *additive* writers still write **through** the symlink into the current version after it's published: execution-trace save (`execution_trace.md`) and changedoc applied-context sync. These run in low-concurrency post-publish / final-presentation phases, so they don't meaningfully race the offloaded peer copy, but they do mutate a "current" version in place — if either is ever moved into a hot, concurrent path it should publish a new version instead. The immutability guarantee that the race fix relies on is precise: *a version is never deleted or rebuilt while a reader holds it*; it does not currently forbid these additive in-place appends to the newest version.

### Public Accessors (replace private globals)

| Old | New |
|-----|-----|
| `_CURRENT_ATTEMPT` | `get_current_attempt()` |
| `_DEBUG_MODE` | `is_debug_mode()` |
| `_LOG_SESSION_DIR` | `get_log_session_dir()` |
| `_EVENT_EMITTER` | `get_event_emitter()` (via `events.py`) |

## TUI Design Principles

**Timeline Chronology Rule**: Tool batching MUST respect chronological order. Tools should ONLY be batched when they arrive consecutively with no intervening content (thinking, text, status). When non-tool content arrives, any pending batch must be finalized before the content is added, and the next tool starts a fresh batch.

This is enforced via `ToolBatchTracker.mark_content_arrived()` in `content_handlers.py`, which is called whenever non-tool content is added to the timeline.

### TUI Debug Logging

All TUI debug logging goes through `massgen/frontend/displays/shared/tui_debug.py`. This module is the **single source of truth** for TUI debug file output.

- **Enable**: set `MASSGEN_TUI_DEBUG=1` in your environment.
- **Log file**: `<tempdir>/tui_debug.log` (uses `tempfile.gettempdir()` for cross-platform support).
- **Usage**: call `tui_log(msg)` from anywhere in the TUI layer. Widget-specific wrappers (e.g. `_wizard_log`, `_tab_log`) add a prefix tag and delegate to `tui_log`.
- **Do NOT** create ad-hoc `logging.FileHandler` instances with hard-coded paths in widget files — always use `tui_log`.
