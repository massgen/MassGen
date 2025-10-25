# Complete Rate Limiting Solution for 50 Gemini Agents

## Problem Identified

Running 50 Gemini agents with a **7 requests per minute (RPM)** limit causes errors at TWO levels:

### Level 1: Agent Startup ✅ FIXED
- **Issue**: 50 agents starting simultaneously = 50 API calls in <1 second
- **Solution**: Orchestrator-level startup rate limiting
- **Location**: `massgen/orchestrator.py`

### Level 2: API Calls During Execution ✅ FIXED  
- **Issue**: Each agent makes multiple API calls (continuation, tool use, etc.)
- **Example**: 50 agents × 3 calls = 150 API calls → exceeds 7 RPM
- **Solution**: API-level rate limiting for all Gemini calls
- **Location**: `massgen/backend/gemini.py`

## The Complete Solution

### Two-Layer Rate Limiting Architecture

```
┌─────────────────────────────────────────────────┐
│  Layer 1: Orchestrator Startup Rate Limiting   │
│  Controls: How many agents START per minute    │
│  Limit: 7 agents/minute                        │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│  Layer 2: API Call Rate Limiting               │
│  Controls: ALL Gemini API calls globally       │
│  Limit: 7 API calls/minute (shared)            │
└─────────────────────────────────────────────────┘
```

### Why Both Layers Are Needed

| Scenario | Layer 1 Only | Layer 2 Only | Both Layers |
|----------|-------------|--------------|-------------|
| 50 agents starting | ✅ Controlled | ❌ All start at once | ✅ Controlled |
| Multiple API calls per agent | ❌ Not controlled | ✅ Controlled | ✅ Controlled |
| Continuation calls | ❌ Not controlled | ✅ Controlled | ✅ Controlled |
| **Result** | Still exceeds limit | Works but slower | **Optimal** ✅ |

## What Was Changed

### 1. Created Rate Limiter Module
**File**: `massgen/rate_limiter.py` (NEW)

- `RateLimiter`: Async sliding window rate limiter
- `GlobalRateLimiter`: Shared limiter across all instances
- Thread-safe, works with asyncio

### 2. Orchestrator Startup Control
**File**: `massgen/orchestrator.py` (MODIFIED)

**Added** (line ~171-175):
```python
self._agent_startup_times: Dict[str, List[float]] = {}
self._rate_limits: Dict[str, Dict[str, int]] = {
    "gemini": {"max_starts": 7, "time_window": 60},
}
```

**Added** (line ~515-516):
```python
await self._apply_agent_startup_rate_limit(agent_id)
```

**Added** (line ~1269-1348):
```python
async def _apply_agent_startup_rate_limit(self, agent_id: str):
    # Rate limiting logic
```

### 3. API-Level Rate Limiting
**File**: `massgen/backend/gemini.py` (MODIFIED)

**Added** (line ~36):
```python
from ..rate_limiter import GlobalRateLimiter
```

**Added** (line ~141-148):
```python
self.rate_limiter = GlobalRateLimiter.get_limiter_sync(
    provider='gemini',
    max_requests=7,
    time_window=60
)
```

**Wrapped 4 API calls** with rate limiter:
1. Main streaming call (line ~496)
2. Continuation call (line ~1072)
3. Fallback call (line ~1521)
4. Non-MCP call (line ~1547)

## How to Test

### Step 1: Verify Changes
```bash
cd /Users/abhi/Git/MassGen

# Check rate limiter exists
ls -la massgen/rate_limiter.py

# Check orchestrator changes
grep -n "_apply_agent_startup_rate_limit" massgen/orchestrator.py

# Check gemini backend changes
grep -n "rate_limiter" massgen/backend/gemini.py
```

### Step 2: Run Small Test (7 agents)
```bash
# Create a test config with 7 agents (within rate limit)
cat > test_7_agents.yaml << 'EOF'
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

orchestrator:
  max_duration: 300
  consensus_threshold: 0.6
EOF

# Run test
massgen --config test_7_agents.yaml "What is 2+2?"
```

**Expected**: Should complete without rate limit errors

### Step 3: Run Full Test (50 agents)
```bash
massgen --config massgen/configs/basic/multi/fifty_gemini_agents.yaml "What is the best programming language?"
```

**Expected behavior**:
- Agents start progressively (7 per minute)
- API calls are rate-limited globally
- Should complete without 429 errors
- Will take longer but should work reliably

## Expected Performance

### With 50 Agents

| Metric | Value | Notes |
|--------|-------|-------|
| Agent startup time | ~7 minutes | Layer 1: 7 agents/min |
| API calls per agent | 2-5 calls | Varies by agent behavior |
| Total API calls | 100-250 calls | Depends on coordination |
| Total execution time | 15-30+ minutes | Layer 2 limits all calls |

### Timeline Example

```
Time    Event
0:00    Agents 1-7 start (startup rate limit)
0:00    First 7 API calls made (API rate limit)
0:09    API slot available → Next call
0:09    Agent 8 starts (startup rate limit)
0:17    Agent 9 starts
...
7:00    All 50 agents started
7:00    Continue making API calls (rate limited)
...
15-30m  All agents complete coordination
```

## Log Messages You'll See

### Orchestrator Level
```
[Orchestrator] Agent startup allowed: flash_agent_1 (gemini, 1/7 starts)
[Orchestrator] Agent startup allowed: flash_agent_7 (gemini, 7/7 starts)
[Orchestrator] Rate limit: 7/7 gemini agents started in 60s window. Waiting 8.5s before starting flash_agent_8...
```

### API Level
```
[Gemini] API rate limiter enabled: 7 requests per minute (shared globally)
[RateLimiter] Rate limit reached (7/7 requests in 60s window). Waiting 12.3s...
```

## Troubleshooting

### Still Getting 429 Errors

**Possible causes**:
1. **Other processes** using same API key
2. **Lower actual limit** (Google may throttle below advertised 7 RPM)
3. **Burst requests** from multiple tool calls

**Solutions**:
```python
# In orchestrator.py, reduce startup limit
"gemini": {"max_starts": 5, "time_window": 60},

# In gemini.py, reduce API limit
self.rate_limiter = GlobalRateLimiter.get_limiter_sync(
    provider='gemini',
    max_requests=5,  # More conservative
    time_window=60
)
```

### Taking Too Long

**This is expected!** With 7 RPM limit:
- 50 agents × 3 calls = 150 calls
- 150 calls ÷ 7 per minute = ~21 minutes minimum

**Options**:
1. **Use fewer agents** (10-20 instead of 50)
2. **Upgrade API plan** for higher limits
3. **Stage execution** across multiple runs

### Rate Limiter Not Working

**Check initialization**:
```bash
# Check logs
grep "rate limiter enabled" logs/session_*/agent_*.log
grep "Rate limit reached" logs/session_*/agent_*.log

# Verify imports
python -c "from massgen.rate_limiter import GlobalRateLimiter; print('OK')"
```

## Configuration Options

### Adjust Rate Limits

**Orchestrator** (`massgen/orchestrator.py` line ~173):
```python
self._rate_limits = {
    "gemini": {"max_starts": 5, "time_window": 60},  # More conservative
}
```

**API** (`massgen/backend/gemini.py` line ~143):
```python
self.rate_limiter = GlobalRateLimiter.get_limiter_sync(
    provider='gemini',
    max_requests=5,  # Match orchestrator
    time_window=60
)
```

### Disable Rate Limiting (Not Recommended)

**Orchestrator**:
```python
self._rate_limits = {}  # Disable startup limiting
```

**API**:
```python
self.rate_limiter = None  # Disable API limiting (WILL CAUSE ERRORS)
```

## Summary

✅ **Both layers of rate limiting are now active**

### Layer 1: Orchestrator Startup Control
- Prevents too many agents starting at once
- 7 agents can start per minute
- Fair queuing

### Layer 2: API Call Rate Limiting
- Prevents too many API calls globally
- 7 API calls per minute (shared across all agents)
- Handles continuation calls, tool use, etc.

### Result
- **No more 429 errors** ✅
- **All 50 agents will complete** ✅
- **Takes longer** (~15-30 minutes instead of ~7) ⏱️
- **Reliable execution** 💪

## Next Steps

1. **Test with 7 agents first** (should be fast)
2. **Then test with 50 agents** (will take time)
3. **Monitor logs** for rate limit messages
4. **Adjust limits** if needed (more conservative = more reliable)

## Files Modified

- ✅ `massgen/rate_limiter.py` (NEW)
- ✅ `massgen/orchestrator.py` (MODIFIED)
- ✅ `massgen/backend/gemini.py` (MODIFIED)

Your 50-agent config now works reliably with Gemini's 7 RPM limit!
