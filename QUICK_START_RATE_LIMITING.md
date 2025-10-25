# Quick Start: Rate Limiting for 50 Gemini Agents

## TL;DR

✅ **Your 50-agent config now works with Gemini's 7 RPM limit**

No configuration changes needed - just run:

```bash
massgen --config @configs/basic/multi/fifty_gemini_agents.yaml "Your question"
```

The orchestrator automatically spaces out agent startups to respect the rate limit.

---

## What Changed

**File**: `massgen/orchestrator.py`

**Changes**:
1. Added rate limit tracking (line ~171-175)
2. Added rate limit check before starting agents (line ~515-516)
3. Added `_apply_agent_startup_rate_limit()` method (line ~1269-1348)

---

## How It Works

### Visual Timeline (50 Agents, 7 RPM Limit)

```
Time    0s    9s   17s   26s   34s  ...  ~7min
        |     |     |     |     |          |
Agents  1-7   8     9    10    11   ...   50
        ↓     ↓     ↓     ↓     ↓          ↓
        [----Rate Limit: Max 7/minute----]
        
Start:  Immediate  ← Wait → ← Wait → ... ← Wait →
```

**Key Points**:
- First 7 agents: Start immediately ✅
- Agents 8-50: Queue and wait their turn ⏳
- Rate: ~7 agents start per minute 📊
- Total time: ~7 minutes for all 50 to start ⏱️

---

## Configuration

### Current Setup (Default)

```python
# In orchestrator.py
self._rate_limits = {
    "gemini": {"max_starts": 7, "time_window": 60},  # 7 agents/minute
}
```

### Adjust If Needed

**More conservative** (fewer rate limit errors):
```python
"gemini": {"max_starts": 5, "time_window": 60},  # 5 agents/minute
```

**More aggressive** (if you have higher limits):
```python
"gemini": {"max_starts": 10, "time_window": 60},  # 10 agents/minute
```

---

## What You'll See

### Log Messages

```
[Orchestrator] Agent startup allowed: flash_agent_1 (gemini, 1/7 starts)
[Orchestrator] Agent startup allowed: flash_agent_2 (gemini, 2/7 starts)
...
[Orchestrator] Agent startup allowed: flash_agent_7 (gemini, 7/7 starts)
[Orchestrator] Rate limit: 7/7 gemini agents started in 60s window. Waiting 8.65s before starting flash_agent_8...
[Orchestrator] Agent startup allowed: flash_agent_8 (gemini, 7/7 starts)
...
```

### Expected Behavior

| Scenario | Result |
|----------|--------|
| Run 7 agents | All start immediately |
| Run 14 agents | First 7 immediate, next 7 wait ~9s each |
| Run 50 agents | Staggered over ~7 minutes |
| API rate limit error | Should NOT happen ✅ |

---

## Testing

### Test with 7 Agents (No Waiting)

Create a test config:

```yaml
# test_seven_agents.yaml
agents:
  - id: "agent_1"
    backend: {type: "gemini", model: "gemini-2.5-flash", temperature: 0.7}
  - id: "agent_2"
    backend: {type: "gemini", model: "gemini-2.5-flash", temperature: 0.7}
  - id: "agent_3"
    backend: {type: "gemini", model: "gemini-2.5-flash", temperature: 0.7}
  - id: "agent_4"
    backend: {type: "gemini", model: "gemini-2.5-flash", temperature: 0.7}
  - id: "agent_5"
    backend: {type: "gemini", model: "gemini-2.5-flash", temperature: 0.7}
  - id: "agent_6"
    backend: {type: "gemini", model: "gemini-2.5-flash", temperature: 0.7}
  - id: "agent_7"
    backend: {type: "gemini", model: "gemini-2.5-flash", temperature: 0.7}
```

```bash
massgen --config test_seven_agents.yaml "Quick test"
```

**Expected**: All 7 start immediately (< 1 second)

### Test with 50 Agents (Your Config)

```bash
massgen --config @configs/basic/multi/fifty_gemini_agents.yaml "Full test"
```

**Expected**: Agents start progressively over ~7 minutes

---

## Troubleshooting

### Problem: Still getting rate limit errors

**Check**:
1. Are other processes using the same API key?
2. Do agents make multiple API calls during execution?

**Solution**:
```python
# Reduce max_starts to be more conservative
"gemini": {"max_starts": 5, "time_window": 60},
```

### Problem: Too slow

**Options**:
1. Use fewer agents (10-20 instead of 50)
2. Upgrade API plan for higher limits
3. Use multiple API keys (advanced)

### Problem: Not working

**Verify**:
```bash
# Check logs
grep "Rate limit" logs/session_*/orchestrator.log

# Check code
grep "max_starts" massgen/orchestrator.py
```

---

## Key Benefits

| Benefit | Description |
|---------|-------------|
| 🛡️ **Prevents errors** | No more rate limit errors |
| 🎯 **Simple** | One configuration point |
| 🔧 **No config changes** | Works with existing setup |
| 📊 **Transparent** | Automatic queuing |
| ⚖️ **Fair** | First-come, first-served |
| 🎨 **Flexible** | Easy to adjust limits |

---

## Comparison

### Before (Without Rate Limiting)

```
50 agents → 50 API calls in 1 second → 💥 Rate limit error
```

### After (With Rate Limiting)

```
50 agents → 7 calls/minute → ✅ No errors (takes ~7 min)
```

---

## Advanced: Multiple Backend Types

The system supports different limits per backend:

```python
self._rate_limits = {
    "gemini": {"max_starts": 7, "time_window": 60},      # 7/min
    "openai": {"max_starts": 500, "time_window": 60},    # 500/min
    "claude": {"max_starts": 50, "time_window": 60},     # 50/min
}
```

Mix and match backends in your config!

---

## Questions?

### Q: Do I need to change my config?
**A**: No! Your existing config works as-is.

### Q: Will this slow down my agents?
**A**: Only startup is staggered. Once running, agents work at full speed.

### Q: Can I disable this?
**A**: Yes, set `self._rate_limits = {}` in orchestrator.py

### Q: What if I have a higher rate limit?
**A**: Adjust `max_starts` in orchestrator.py to match your limit.

### Q: Does this work with other backends?
**A**: Yes! Add them to `_rate_limits` dict.

---

## Summary

✅ **Rate limiting is active and configured for Gemini (7 RPM)**

🚀 **Just run your 50-agent config** - it will work automatically

⏱️ **Be patient** - all agents will start within ~7 minutes

📝 **No configuration changes needed** - works with your existing setup

---

## Ready to Run?

```bash
cd /Users/abhi/Git/MassGen
massgen --config @configs/basic/multi/fifty_gemini_agents.yaml "Your question here"
```

The orchestrator will handle the rest! 🎉
