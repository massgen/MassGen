# Agent Startup Rate Limiting

## Overview

The orchestrator now includes **agent startup rate limiting** to prevent exceeding API rate limits when running many agents simultaneously.

## Problem

With 50 Gemini agents and a 7 requests per minute (RPM) API limit:
- All 50 agents would try to start simultaneously
- Each agent makes an API call on startup
- Result: 50 API calls in < 1 second → **rate limit exceeded** ❌

## Solution

**Orchestrator-level startup control**: The orchestrator now limits how many agents of the same backend type can start within a time window.

### Configuration

In `orchestrator.py` `__init__`:

```python
self._rate_limits: Dict[str, Dict[str, int]] = {
    "gemini": {"max_starts": 7, "time_window": 60},  # 7 agents per minute
}
```

### How It Works

1. **Before starting each agent**, check if rate limit is reached
2. **If limit reached**, wait until a slot becomes available
3. **Track startup times** per backend type (gemini, openai, etc.)
4. **Sliding window**: Only count startups in the last 60 seconds

## Usage with Your 50 Agent Config

Your configuration **works without changes**:

```yaml
# massgen/configs/basic/multi/fifty_gemini_agents.yaml
agents:
  - id: "flash_agent_1"
    backend: {type: "gemini", model: "gemini-2.5-flash", ...}
  - id: "flash_agent_2"
    backend: {type: "gemini", model: "gemini-2.5-flash", ...}
  # ... 50 agents total
```

### Expected Behavior

When you run this config:

```bash
massgen --config @configs/basic/multi/fifty_gemini_agents.yaml "Your question"
```

**Agent Startup Timeline:**

| Time | Action | Note |
|------|--------|------|
| 0:00 | Agents 1-7 start | Immediate (within rate limit) |
| 0:09 | Agent 8 starts | Waits ~9s for slot to free |
| 0:17 | Agent 9 starts | Waits ~17s total |
| 0:26 | Agent 10 starts | Waits ~26s total |
| ... | ... | ... |
| ~6:00 | Agent 43 starts | After ~6 minutes |
| ~7:00 | All 50 agents running | After ~7 minutes |

**Rate**: ~7 agents start per minute

## Log Messages

You'll see messages like:

```
[Orchestrator] Rate limit: 7/7 gemini agents started in 60s window. Waiting 8.43s before starting flash_agent_8...
[Orchestrator] Agent startup allowed: flash_agent_8 (gemini, 7/7 starts)
```

## Benefits of This Approach

### ✅ Advantages

1. **Simple & Clean**: Single point of control in orchestrator
2. **Backend-Agnostic**: Works for any backend (Gemini, OpenAI, etc.)
3. **No API Changes**: Doesn't modify backend code
4. **Fair Queuing**: First-come, first-served
5. **Transparent**: Agents don't need to know about rate limiting
6. **Configurable**: Easy to adjust limits per backend

### Comparison to API-Level Rate Limiting

| Feature | Orchestrator-Level | API-Level |
|---------|-------------------|-----------|
| Where applied | Agent startup | Every API call |
| Complexity | Low | High |
| Maintenance | Single location | Multiple call sites |
| Backend changes | None | Extensive |
| Configurability | Easy (one dict) | Requires backend mods |

## Customization

### Adjust Rate Limits

Edit `orchestrator.py` `__init__`:

```python
self._rate_limits: Dict[str, Dict[str, int]] = {
    "gemini": {"max_starts": 7, "time_window": 60},     # 7/minute for Gemini
    "openai": {"max_starts": 500, "time_window": 60},   # 500/minute for OpenAI (example)
}
```

### Add More Backends

```python
self._rate_limits = {
    "gemini": {"max_starts": 7, "time_window": 60},
    "claude": {"max_starts": 50, "time_window": 60},
    "grok": {"max_starts": 10, "time_window": 60},
}
```

### Disable Rate Limiting

Remove the backend from `_rate_limits`:

```python
self._rate_limits = {}  # No rate limiting
```

## Technical Details

### Algorithm

```python
1. Get agent's backend type (e.g., "gemini")
2. Check if backend has rate limit configured
3. Get startup times for this backend in last N seconds
4. If count >= max_starts:
   a. Calculate wait time until oldest startup expires
   b. Sleep for wait time
   c. Clean up old timestamps
5. Record new startup timestamp
6. Proceed with agent execution
```

### Code Location

**File**: `massgen/orchestrator.py`

**Key sections**:
- **Init** (line ~171-175): Rate limit configuration
- **Startup loop** (line ~515-516): Apply rate limit before starting agent
- **Rate limit method** (line ~1269-1348): `_apply_agent_startup_rate_limit()`

### Thread Safety

- Uses standard Python lists (modified in async context)
- Single orchestrator instance = no race conditions
- Agents started sequentially in for-loop = safe ordering

## Performance Implications

### Startup Time

With 50 agents and 7 RPM:
- **Math**: 50 agents ÷ 7 per minute ≈ 7.14 minutes
- **Reality**: ~7 minutes for all to start
- **First response**: Agent 1 can respond immediately
- **All responses**: Depends on coordination, not just startup

### Memory

- Tracks ~7 timestamps per backend type
- Negligible memory footprint (<1 KB)

### CPU

- Lightweight timestamp comparisons
- Async sleep (no CPU usage while waiting)

## Troubleshooting

### Still Getting Rate Limit Errors

**Possible causes:**
1. **Other processes** using the same API key
2. **Continuation calls**: Agents make multiple API calls during execution (not just startup)
3. **Actual limit lower**: Google may throttle to less than 7 RPM

**Solutions:**
1. Reduce `max_starts` to 5 or 6 for safety margin
2. Check if other processes are using API key
3. Verify your API key's actual rate limits

### Agents Not Starting

**Check logs:**
```bash
grep "Rate limit" logs/session_*/orchestrator.log
grep "Agent startup allowed" logs/session_*/orchestrator.log
```

**Verify configuration:**
```python
# In orchestrator.py __init__, check:
self._rate_limits  # Should contain "gemini"
```

### Long Wait Times

**This is expected!** With 50 agents and 7 RPM:
- Agent 50 waits ~7 minutes
- This prevents rate limit errors
- All agents will eventually start

**Alternatives:**
1. Use fewer agents (e.g., 10-20)
2. Stage execution across multiple runs
3. Upgrade API plan for higher limits

## Example Session

### Small Test (7 agents)

```bash
# Create test config with 7 agents
massgen --config @configs/basic/multi/seven_gemini_agents.yaml "Test"
```

**Expected**: All 7 start immediately (within rate limit)

### Medium Test (14 agents)

```bash
# 14 agents
massgen --config @configs/basic/multi/fourteen_gemini_agents.yaml "Test"
```

**Expected**:
- First 7: Start immediately
- Next 7: Wait ~8-9 seconds each

### Full Test (50 agents)

```bash
# Your current config
massgen --config @configs/basic/multi/fifty_gemini_agents.yaml "Test"
```

**Expected**:
- First 7: Immediate
- Remaining 43: Staggered over ~7 minutes
- Total startup time: ~7 minutes

## Future Enhancements

Possible improvements:
1. **YAML configuration**: Specify rate limits in config file
2. **Dynamic adjustment**: Adapt based on actual API errors
3. **Per-model limits**: Different limits for Flash vs Pro
4. **Priority queuing**: Start certain agents first
5. **Burst allowance**: Allow brief bursts above limit
6. **Status dashboard**: Show queue status in UI

## Related Code

- **Orchestrator**: `massgen/orchestrator.py`
  - `__init__()`: Rate limit configuration
  - `_apply_agent_startup_rate_limit()`: Rate limiting logic
  - `_stream_coordination_with_agents()`: Agent startup loop

- **Config**: `massgen/configs/basic/multi/fifty_gemini_agents.yaml`
  - Your 50-agent configuration

## Summary

✅ **Agent startup rate limiting is now active**

- Prevents exceeding API rate limits
- Works transparently with your 50-agent config
- No configuration changes needed
- Automatically queues agents when limit is reached
- Fair, first-come first-served startup order

Just run your config and the orchestrator will handle rate limiting automatically!
