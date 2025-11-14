# Rate Limit Configuration

This directory contains rate limit configurations for different AI provider models.

## Files

### `rate_limits.yaml`

Defines rate limits for different AI provider models (Gemini, OpenAI, Claude, etc.).

**Structure:**
```yaml
provider_name:
  model_name:
    rpm: <requests per minute>
    tpm: <tokens per minute>
    rpd: <requests per day>
```

**Example:**
```yaml
gemini:
  gemini-2.5-flash:
    rpm: 9        # 9 requests per minute
    tpm: 240000   # 240K tokens per minute
    rpd: 245      # 245 requests per day
```

### `rate_limit_config.py`

Python module that loads and parses `rate_limits.yaml`.

**Usage:**
```python
from massgen.configs.rate_limits import get_rate_limit_config

config = get_rate_limit_config()
limits = config.get_limits('gemini', 'gemini-2.5-flash')
# Returns: {'rpm': 9, 'tpm': 240000, 'rpd': 245}
```

## Supported Providers

Add rate limits for any provider:

- **Gemini** - Google Gemini models (gemini-2.5-flash, gemini-2.5-pro, etc.)
- **OpenAI** - GPT models (gpt-4, gpt-4-turbo, gpt-3.5-turbo, etc.)
- **Claude** - Anthropic Claude models (claude-3-5-sonnet, claude-3-5-haiku, etc.)
- **Azure OpenAI** - Azure-hosted OpenAI models
- **Others** - Any custom provider

## Rate Limit Types

### RPM (Requests Per Minute)
Maximum number of API requests allowed per minute (60-second sliding window).

### TPM (Tokens Per Minute)
Maximum number of tokens (input + output) allowed per minute (60-second sliding window).

### RPD (Requests Per Day)
Maximum number of API requests allowed per 24-hour period (86400-second sliding window).

## How It Works

1. **Automatic Loading**: Configuration is loaded when the backend initializes
2. **Multi-dimensional Enforcement**: All limits (RPM, TPM, RPD) are enforced simultaneously
3. **Sliding Windows**: Uses precise sliding windows, not fixed time periods
4. **Global Sharing**: Rate limiters are shared across all agents using the same model
5. **Automatic Waiting**: Requests automatically wait when limits are hit

## Adding New Providers

To add rate limits for a new provider, edit `rate_limits.yaml`:

```yaml
# Example: Add OpenAI limits
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

No code changes needed! The system automatically loads the configuration.

## Conservative Limits

The default configuration uses **conservative limits** (slightly below actual API limits) to provide a safety buffer and prevent hitting rate limits due to timing variations or concurrent requests.

## Documentation

See [Rate Limiting Documentation](../../../docs/rate_limiting.md) for comprehensive details on:
- Architecture and design
- Usage examples
- Testing approaches
- Advanced features

## Dependencies

- `pyyaml` - Required for YAML parsing
  ```bash
  pip install pyyaml
  ```
