# Rate Limiting in MassGen

MassGen implements multi-dimensional rate limiting to respect AI provider rate limits and avoid hitting API quotas.

## Overview

The rate limiting system supports three types of limits:

- **RPM (Requests Per Minute)**: Maximum number of API requests allowed per minute
- **TPM (Tokens Per Minute)**: Maximum number of tokens (input + output) allowed per minute
- **RPD (Requests Per Day)**: Maximum number of API requests allowed per 24-hour period

All limits are enforced using **sliding windows** for accurate, real-time tracking.

## Configuration

Rate limits are defined in `massgen/configs/rate_limits/rate_limits.yaml`:

```yaml
gemini:
  gemini-2.5-flash:
    rpm: 9        # 9 requests per minute
    tpm: 240000   # 240K tokens per minute
    rpd: 245      # 245 requests per day

  gemini-2.5-pro:
    rpm: 2        # 2 requests per minute
    tpm: 120000   # 120K tokens per minute
    rpd: 48       # 48 requests per day

  default:
    rpm: 7
    tpm: 100000
    rpd: 100
```

### Adding New Providers

To add rate limits for a new provider (e.g., OpenAI):

```yaml
openai:
  gpt-4:
    rpm: 500
    tpm: 150000
    rpd: 10000

  gpt-3.5-turbo:
    rpm: 3000
    tpm: 250000
    rpd: 50000
```

## How It Works

### 1. Configuration Loading

Rate limits are loaded from the YAML file when the backend initializes:

```python
from massgen.configs.rate_limits import get_rate_limit_config

config = get_rate_limit_config()
limits = config.get_limits('gemini', 'gemini-2.5-flash')
# Returns: {'rpm': 9, 'tpm': 240000, 'rpd': 245}
```

### 2. Rate Limiter Creation

The backend creates a shared multi-dimensional rate limiter:

```python
from massgen.backend.rate_limiter import GlobalRateLimiter

limiter = GlobalRateLimiter.get_multi_limiter_sync(
    provider='gemini-2.5-flash',
    rpm=limits['rpm'],
    tpm=limits['tpm'],
    rpd=limits['rpd']
)
```

### 3. Request Enforcement

Before each API request, the rate limiter checks all limits:

```python
async with self.rate_limiter:
    # Rate limiter ensures all limits are respected
    response = await api_call()
```

If any limit is exceeded, the request automatically waits until it's safe to proceed.

### 4. Token Tracking

After receiving a response, token usage is recorded for TPM tracking:

```python
await self.rate_limiter.record_tokens(total_tokens)
```

## Rate Limiter Behavior

### Sliding Windows

All limits use sliding windows, not fixed time periods:

- **RPM**: Tracks requests in the last 60 seconds
- **TPM**: Tracks tokens used in the last 60 seconds
- **RPD**: Tracks requests in the last 86400 seconds (24 hours)

This provides accurate, real-time enforcement without "reset" windows.

### Waiting Logic

When a limit is hit, the rate limiter:

1. Calculates wait time until the oldest request/tokens expire from the window
2. Logs a message explaining which limit was hit
3. Automatically sleeps until the request can proceed
4. Retries the limit check and allows the request

### Example Log Output

```
[MultiRateLimiter] Rate limit reached: RPM limit (9/9). Waiting 12.5s...
[MultiRateLimiter] Rate limit reached: TPM limit (245000/240000 tokens). Waiting 8.2s...
```

## Global Rate Limiter

Rate limiters are **shared globally** across all instances of the same model:

```python
# Multiple agents using the same model share the same rate limiter
agent1 = GeminiBackend(model='gemini-2.5-flash')  # Uses shared limiter
agent2 = GeminiBackend(model='gemini-2.5-flash')  # Uses SAME limiter
agent3 = GeminiBackend(model='gemini-2.5-pro')    # Uses different limiter
```

This ensures that total usage across all agents respects the provider's limits.

## Advanced Usage

### Programmatic Configuration

You can also create rate limiters programmatically:

```python
from massgen.backend.rate_limiter import MultiRateLimiter

limiter = MultiRateLimiter(
    rpm=10,      # 10 requests per minute
    tpm=100000,  # 100K tokens per minute
    rpd=500      # 500 requests per day
)

async with limiter:
    response = await your_api_call()
    await limiter.record_tokens(response.total_tokens)
```

### Disabling Limits

Set a limit to `None` to disable it:

```yaml
gemini:
  gemini-2.5-flash:
    rpm: 9
    tpm: null     # No TPM limit
    rpd: null     # No RPD limit
```

### Conservative Limits

The default configuration uses **conservative limits** (slightly below the actual API limits) to provide a safety buffer and prevent hitting rate limits due to timing variations.

## Architecture

```
┌─────────────────────────────────────┐
│  rate_limits.yaml                   │
│  (Configuration file)               │
└──────────────┬──────────────────────┘
               │
               ↓
┌─────────────────────────────────────┐
│  RateLimitConfig                    │
│  (Loads and parses YAML)            │
└──────────────┬──────────────────────┘
               │
               ↓
┌─────────────────────────────────────┐
│  GlobalRateLimiter                  │
│  (Manages shared limiters)          │
└──────────────┬──────────────────────┘
               │
               ↓
┌─────────────────────────────────────┐
│  MultiRateLimiter                   │
│  (Enforces RPM, TPM, RPD)           │
│  - Sliding windows                  │
│  - Automatic waiting                │
│  - Token tracking                   │
└─────────────────────────────────────┘
```

## Testing

To test rate limiting behavior:

```python
import asyncio
from massgen.backend.gemini import GeminiBackend

async def test_rate_limiting():
    backend = GeminiBackend(model='gemini-2.5-flash')

    # Make multiple rapid requests
    for i in range(20):
        print(f"Request {i+1}...")
        async for chunk in backend.stream_with_tools(
            messages=[{"role": "user", "content": f"Hello {i}"}],
            tools=[]
        ):
            if chunk.type == "content":
                print(chunk.content, end='')
        print()

asyncio.run(test_rate_limiting())
```

You should see rate limiting messages when limits are exceeded.

## Benefits

1. **Prevents API errors**: Never hit rate limit errors from providers
2. **Automatic retry**: No need to handle rate limit errors manually
3. **Multi-agent safe**: Shared limiters work correctly with multiple agents
4. **Configurable**: Easy to update limits without code changes
5. **Accurate**: Sliding windows provide precise enforcement
6. **Transparent**: Clear logging shows when and why requests are delayed

## Future Enhancements

Potential improvements:

- [ ] Per-user rate limiting
- [ ] Dynamic limit adjustment based on API responses
- [ ] Rate limit metrics and dashboards
- [ ] Circuit breaker integration
- [ ] Cost tracking alongside rate limiting
