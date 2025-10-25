# Corrected Rate Limits for Gemini Models

## Issue Found

The actual Google AI Studio rate limits are **different per model**:

| Model | Actual Limit | What I Used Before | Corrected |
|-------|-------------|-------------------|-----------|
| **Gemini 2.5 Flash** | 10 RPM | 7 RPM ❌ | **9 RPM** ✅ (conservative) |
| **Gemini 2.5 Pro** | 2 RPM | 7 RPM ❌ | **2 RPM** ✅ |

## The Real Problem

Your config has **both Flash and Pro models**:
- **30 Flash agents** → Need 10 RPM limit
- **20 Pro agents** → Need 2 RPM limit (much slower!)

Before: All 50 agents shared a single 7 RPM limit
Now: Flash agents share 9 RPM, Pro agents share 2 RPM (separate limits)

## What Was Fixed

### 1. Backend Rate Limiting (`gemini.py`)
Now detects model and applies **per-model limits**:
```python
if 'gemini-2.5-flash' in model_name:
    max_requests=9  # Conservative (actual: 10)
elif 'gemini-2.5-pro' in model_name:
    max_requests=2  # Very limited!
```

### 2. Orchestrator Startup Limiting (`orchestrator.py`)
Now tracks **per-model startup times**:
```python
"gemini-2.5-flash": {"max_starts": 9, "time_window": 60},
"gemini-2.5-pro": {"max_starts": 2, "time_window": 60},
```

## Expected Performance with 50 Agents

### Flash Agents (30 agents)
- **Startup**: 30 agents ÷ 9 per minute ≈ 3.5 minutes
- **API calls**: 9 calls per minute total
- **Progress**: Relatively fast

### Pro Agents (20 agents)
- **Startup**: 20 agents ÷ 2 per minute = 10 minutes ⚠️
- **API calls**: 2 calls per minute total ⚠️
- **Progress**: **Very slow** due to 2 RPM limit

### Total Timeline
```
Time    Event
0:00    Flash agents start (first 9)
0:00    Pro agents start (first 2)
1:00    Next 9 Flash agents start
1:00    Next 2 Pro agents start
2:00    Next 9 Flash agents start
2:00    Next 2 Pro agents start
3:00    Last 3 Flash agents start (30 total)
3:00    2 more Pro agents start
...
10:00   Last 2 Pro agents start (20 total)
...
20-40m  All agents complete (Pro agents are bottleneck)
```

## The Pro Problem

**Gemini Pro is VERY rate limited** (2 RPM):
- 20 Pro agents will take **10 minutes** just to start
- Each Pro agent can only make ~2 API calls per minute
- **Pro agents are the bottleneck**

## Recommendations

### Option 1: Reduce Pro Agents (Fastest)
Use fewer Pro agents since they're so slow:
```yaml
# Reduce from 20 to 5 Pro agents
agents:
  # 30 Flash agents (keep these)
  - id: "flash_agent_1" ...
  # Only 5 Pro agents (reduce from 20)
  - id: "pro_agent_1" ...
  - id: "pro_agent_5" ...
```

**Result**: 
- 30 Flash + 5 Pro = 35 agents total
- Flash done in ~3 minutes
- Pro done in ~2.5 minutes
- **Total: ~5-10 minutes** ✅

### Option 2: Flash Only (Fastest)
Use only Flash models:
```yaml
# 50 Flash agents, no Pro
agents:
  - id: "agent_1"
    backend: {type: "gemini", model: "gemini-2.5-flash", ...}
  # ... 50 Flash agents
```

**Result**:
- Startup: 50 ÷ 9 ≈ 6 minutes
- **Total: ~10-15 minutes** ✅

### Option 3: Keep Current Config (Slowest)
Keep all 50 agents (30 Flash + 20 Pro):

**Result**:
- Startup: ~10 minutes (waiting for Pro)
- Execution: Very slow (Pro bottleneck)
- **Total: ~30-60 minutes** ⏱️

## Test Now

Try the corrected version:

```bash
# Test with your current config (will be slow due to Pro agents)
massgen --config massgen/configs/basic/multi/fifty_gemini_agents.yaml "What is 2+2?"

# Watch for corrected rate limit messages
grep "API rate limiter enabled" logs/session_*/agent_*.log
```

You should see:
```
[Gemini] API rate limiter enabled for Flash: 9 requests per minute
[Gemini] API rate limiter enabled for Pro: 2 requests per minute
```

## Summary

✅ **Rate limits now corrected for each model**
- Flash: 9 RPM
- Pro: 2 RPM (separate limit!)

⚠️ **Pro agents are very slow** (2 RPM limit)
- Consider reducing Pro agents
- Or use Flash-only for faster results

🚀 **Should work without 429 errors now**
- Each model respects its own limit
- No more rate limit exceeded

## Quick Fix for Speed

If you want faster results, edit your config to use fewer Pro agents:

```bash
# Create a fast version with only Flash
cp massgen/configs/basic/multi/fifty_gemini_agents.yaml fifty_flash_only.yaml

# Then edit fifty_flash_only.yaml:
# - Change all "gemini-2.5-pro" to "gemini-2.5-flash"
# Result: All 50 agents using Flash (9 RPM) = much faster!
```
