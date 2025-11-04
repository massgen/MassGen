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

**status.json structure:**
```json
{
  "meta": {
    "elapsed_seconds": 45.3,
    "question": "Create a simple HTML page about Bob Dylan"
  },
  "coordination": {
    "phase": "enforcement",
    "completion_percentage": 65,
    "active_agent": "agent_b"
  },
  "agents": {
    "agent_a": {
      "status": "voted",
      "answer_count": 1,
      "error": null
    },
    "agent_b": {
      "status": "streaming",
      "answer_count": 0,
      "error": null
    }
  },
  "results": {
    "votes": {"agent1.1": 1},
    "winner": null
  }
}
```

**Monitor by checking:**
- `completion_percentage` (0-100) to track progress
- `agents[].error` for any agent errors
- `results.winner` to know when complete (will be `null` until done)

**Agent status values:**
- `waiting` - Not started
- `streaming` - Actively working
- `answered` - Provided answer
- `voted` - Cast vote
- `error` - Failed
- `completed` - Done

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

### Issue: Process runs forever
- **Cause:** No timeout set
- **Fix:** Kill the background process after reasonable timeout (e.g., 5 minutes for simple tasks)

## Summary Checklist

Before running MassGen:
- [ ] Using `--automation` flag
- [ ] Running in background mode
- [ ] Parsing LOG_DIR from output
- [ ] Monitoring status.json file
- [ ] Checking exit code when complete
- [ ] Reading final answer from `final/{winner}/answer.txt`

**That's it!** With `--automation` mode, MassGen is fully automatable.

## Full Documentation

- **Complete guide**: `docs/source/user_guide/automation.rst`
- **Quick commands**: `AUTOMATION_COMMANDS.md`
- **README section**: Search "Automation & LLM Integration" in `README.md`
