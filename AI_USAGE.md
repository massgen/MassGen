# MassGen for LLM Agents - Essential Guide

**If you are an LLM agent:** This is your complete guide to running MassGen via command line.

## 🚨 ALWAYS Use Automation Mode

**Required command format:**

```bash
uv run massgen --automation --config [config_file] "[question]"
```

**Why `--automation` is required:**
- ✅ Clean output (~10 lines vs 250-3,000+ unparseable ANSI codes)
- ✅ Real-time `status.json` monitoring (updated every 2s)
- ✅ Meaningful exit codes (0=success, 1-4=different errors)
- ✅ Automatic workspace isolation for parallel execution

## Complete Workflow

### Step 1: Start MassGen in Background

Use your `execute_command` tool with `run_in_background: true`:

```bash
uv run massgen --automation --config massgen/configs/tools/todo/example_task_todo.yaml "Create a simple HTML page about Bob Dylan"
```

**Expected output** (parseable, ~10 lines):
```
LOG_DIR: .massgen/massgen_logs/log_20251103_143022_123456
STATUS: .massgen/massgen_logs/log_20251103_143022_123456/status.json
QUESTION: Create a simple HTML page about Bob Dylan
[Coordination in progress - monitor status.json for real-time updates]
```

**Parse the LOG_DIR from the first line** - you'll need this path!

### Step 2: Monitor Progress

**Read the status.json file** (updated every 2 seconds):

```bash
cat .massgen/massgen_logs/log_20251103_143022_123456/status.json
```

**📚 Complete status.json documentation:** `docs/source/reference/status_file.rst`

**status.json structure:**
```json
{
  "meta": {
    "elapsed_seconds": 45.3,
    "question": "Create a simple HTML page about Bob Dylan",
    "log_dir": ".massgen/massgen_logs/log_20251103_143022_123456"
  },
  "coordination": {
    "phase": "enforcement",
    "completion_percentage": 65,
    "active_agent": "agent_b",
    "is_final_presentation": false
  },
  "agents": {
    "agent_a": {
      "status": "voted",
      "answer_count": 1,
      "latest_answer_label": "agent1.1",
      "vote_cast": {
        "voted_for_agent": "agent_b",
        "voted_for_label": "agent2.1",
        "reason_preview": "Better solution..."
      },
      "times_restarted": 1,
      "last_activity": 1730678850.123,
      "error": null
    },
    "agent_b": {
      "status": "streaming",
      "answer_count": 1,
      "latest_answer_label": "agent2.1",
      "vote_cast": null,
      "times_restarted": 0,
      "last_activity": 1730678900.456,
      "error": null
    }
  },
  "results": {
    "votes": {"agent1.1": 0, "agent2.1": 1},
    "winner": null,
    "final_answer_preview": null
  }
}
```

**Monitor by checking:**
- `completion_percentage` (0-100) to track progress
- `results.winner` to know when complete (`null` = still running)
- `agents[].error` for any agent errors
- `coordination.phase` to see current phase

**Coordination Phases:**
- `initial_answer` - Agents providing their answers
- `enforcement` - Agents voting on best answer
- `presentation` - Winner presenting final coordinated answer

**Agent Status Values:**
- `waiting` - Not started yet
- `streaming` - Actively working (thinking, reasoning, using tools)
- `answered` - Provided answer, waiting to vote
- `voted` - Cast vote
- `restarting` - Restarting to review new answers from others
- `error` - Encountered an error
- `timeout` - Exceeded timeout limit
- `completed` - Finished all work

**Key Field Explanations:**
- `times_restarted` - How many times agent restarted to incorporate others' work (MassGen's adaptive coordination)
- `latest_answer_label` - Format: `agent1.1`, `agent2.1` (used in voting to identify which answer was chosen)
- `is_final_presentation` - `true` when winner is presenting final answer

**📚 For complete field-by-field documentation:** See `docs/source/reference/status_file.rst`

### Step 3: Check Exit Code

**Once the background command completes**, check the exit code:

| Exit Code | Meaning | What to Do |
|-----------|---------|------------|
| `0` | Success | Read results from log directory |
| `1` | Config error | Check config file exists and is valid |
| `2` | Execution error | Read stderr for details |
| `3` | Timeout | Task took too long, consider simpler query |
| `4` | Interrupted | Process was killed |

### Step 4: Read Final Results

**After exit code 0**, read the final answer:

```bash
# 1. Read status.json to find winner
cat .massgen/massgen_logs/log_20251103_143022_123456/status.json

# Parse the "results.winner" field (e.g., "agent_a")

# 2. Read final answer file
cat .massgen/massgen_logs/log_20251103_143022_123456/final/agent_a/answer.txt
```

**This file contains the coordinated final answer!**

## Parallel Execution (Fully Automatic)

**You can run the SAME config multiple times in parallel** - no configuration needed!

```bash
# Safe - each automatically gets unique workspace
uv run massgen --automation --config config.yaml "Task 1" &
uv run massgen --automation --config config.yaml "Task 2" &
uv run massgen --automation --config config.yaml "Task 3" &
```

**How it works:**
- Automation mode automatically appends unique suffix to workspace paths
- Example: `workspace1` → `workspace1_a1b2c3d4`, `workspace1_e5f6a7b8`
- Each instance is completely isolated

## Example Workflow Pattern

```bash
# 1. Start MassGen in background
uv run massgen --automation --config massgen/configs/tools/todo/example_task_todo.yaml "Your question here"

# 2. Parse log directory from first line of output
# Output will be: LOG_DIR: .massgen/massgen_logs/log_YYYYMMDD_HHMMSS_ffffff
# Extract the path after "LOG_DIR: "

# 3. Monitor progress by reading status.json every 2-5 seconds
cat [log_dir]/status.json

# Check: completion_percentage (0-100)
# Check: results.winner (null = still running, "agent_a" = done)
# Check: agents[].error (null = ok, object = error occurred)

# 4. When background command completes, check exit code
# If 0: Success
# If 1-4: Error (see table above)

# 5. If exit code 0, read final answer
cat [log_dir]/final/[winner]/answer.txt
```

## Example Configs

### Standard Multi-Agent Config

```bash
massgen/configs/tools/todo/example_task_todo.yaml
```

**Features**: 2 agents (Gemini 2.5 Pro + GPT-5 Mini), task planning, file operations

### Meta-Config: MassGen Running MassGen

```bash
massgen/configs/meta/massgen_runs_massgen.yaml
```

**Run it:**
```bash
uv run massgen --config massgen/configs/meta/massgen_runs_massgen.yaml \
    "Run a MassGen experiment to create a webpage about Bob Dylan"
```

**What it does**: Single agent autonomously runs MassGen experiments, monitors status.json, and reports results.

**Use for**: Self-improvement, hyperparameter tuning, bug fixing, automated testing.

**Timing**: Running MassGen may take some time to run (typically 10-30 minutes). Monitor `status.json` - if `completion_percentage` increases, it's working, not hanging.

**Limitation**: Local execution only. Docker requires:
- API credential passing to nested instances
- Automatic dependency installation (e.g., reinstalling MassGen)
- See Issue #436

## Files You'll Read

After completion, these files are available:

| File | Purpose |
|------|---------|
| `status.json` | Real-time status (updated every 2s during run) |
| `final/{winner}/answer.txt` | **The final coordinated answer** |
| `execution_metadata.yaml` | Config and execution details |
| `coordination_events.json` | Complete event log |
| `coordination_table.txt` | Human-readable coordination summary |

## Quick Troubleshooting

### Issue: Can't find log directory
- **Check:** Did you use `--automation` flag?
- **Check:** Parse the first line that starts with `LOG_DIR:`

### Issue: status.json doesn't exist
- **Wait:** File is created after coordination starts (~2-5 seconds)
- **Check:** Logging is enabled (automation mode enables it automatically)

### Issue: Exit code is 1
- **Cause:** Config file error
- **Fix:** Verify config file path exists and is valid YAML

### Issue: Process seems to hang
- **Important:** MassGen coordination takes time - this is normal!
- **Typical:** 2-10 minutes, **Meta-coordination:** 10-30 minutes
- **How to check if stuck:** Read `status.json` - if `completion_percentage` increases, it's working
- **Only stuck if:** NO progress for >5 minutes
- **Recommendations for future configs:**
  - Set `orchestrator_timeout_seconds: 1800` (30 min max)
  - Set `max_new_answers_per_agent: 2` (helps track progress accurately)

## Summary Checklist

Before running MassGen:
- [ ] Using `--automation` flag
- [ ] Running in background mode
- [ ] Parsing LOG_DIR from output
- [ ] Monitoring status.json file
- [ ] Checking exit code when complete
- [ ] Reading final answer from `final/{winner}/answer.txt`

**That's it!** With `--automation` mode, MassGen is fully automatable.

## Limitations

### 1. Local Code Execution Only (Meta-Coordination)

For MassGen-running-MassGen scenarios, currently only local execution is supported:

```yaml
# ✅ Works
agents:
  - backend:
      enable_mcp_command_line: true
      command_line_execution_mode: "local"

# ❌ Not yet supported for nested MassGen
agents:
  - backend:
      command_line_execution_mode: "docker"
```

**Why:** Docker execution requires:
- API credentials to be passed to nested instances
- Automatic dependency installation (e.g., reinstalling MassGen in container)
- Planned for future PR (Issue #436)

### 2. Cost Control ⚠️

**CRITICAL**: Automation mode runs without human oversight. Agents can make many API calls, potentially incurring significant costs.

**Mitigation Strategies:**

1. **Set strict timeouts**:
   ```yaml
   timeout_settings:
     orchestrator_timeout_seconds: 300
     agent_timeout_seconds: 180
   ```

2. **Use economical models**:
   ```yaml
   agents:
     - backend:
         model: "gpt-4o-mini"  # or gpt-5-mini
   ```

3. **Monitor costs**: Check API provider dashboards regularly
4. **Set provider rate limits**: Configure spending limits at API provider level
5. **Start small**: Test with single experiments before scaling

**Future**: Built-in cost tracking and spending limits (planned).

## Full Documentation

- **Complete guide**: `docs/source/user_guide/automation.rst`
- **README section**: Search "Automation & LLM Integration" in `README.md`
