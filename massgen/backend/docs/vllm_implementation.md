# vLLM Backend Implementation Guide

## Overview

The vLLM backend (`massgen/backend/vllm.py`) provides OpenAI-compatible integration with vLLM servers for high-performance local model deployment within the MassGen framework.

### Key Features

* **OpenAI-Compatible**: Full compatibility with OpenAI Chat Completions API.
* **Local Deployment**: Run models locally with full control.
* **vLLM-Specific Features**: Supports `top_k`, `repetition_penalty`, `enable_thinking`

---

## Configuration

### Example Configuration (`three_agents_vllm.yaml`)

```yaml
agents:
  - id: "gpt-oss"
    backend:
      type: "chatcompletion"
      model: "gpt-oss-120b"
      base_url: "https://api.cerebras.ai/v1"
  - id: "qwen"
    backend:
      type: "vllm"
      model: "Qwen/Qwen3-4B"
      base_url: "http://localhost:8000/v1"  # Change this to your vLLM server
  - id: "glm"
    backend:
      type: "chatcompletion"
      model: "glm-4.5"
      base_url: "https://api.z.ai/api/paas/v4"
ui:
  display_type: "rich_terminal"
  logging_enabled: true
```

---

### Example Backend Configuration with vLLM Parameters

```yaml
backend:
  type: "vllm"
  model: "Qwen/Qwen3-4B"
  base_url: "http://localhost:8000/v1"
  top_k: 50
  repetition_penalty: 1.2
  enable_thinking: true
```

---

## Base URL Configuration

The `base_url` should be specified in your config YAML file under the backend configuration. Here are example configurations:

```yaml
backend:
  type: "vllm"
  model: "Qwen/Qwen3-4B"
  base_url: "http://localhost:8000/v1"  # Local server (default)
  # OR for remote/tunneled servers:
  # base_url: "http://your-remote-server:8000/v1" # replace with the server url
```

---

## Environment Variables

```bash
# vLLM API key (default "EMPTY" for local servers)
export VLLM_API_KEY="EMPTY"
```
---

## vLLM Server Startup

```bash
# Basic vLLM server
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen3-4B \
  --host 0.0.0.0 \
  --port 8000

# Advanced vLLM server with Additional Parameters
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen3-4B \
  --host 0.0.0.0 \
  --port 8000 \
  --tensor-parallel-size 1 \
  --gpu-memory-utilization 0.9 \

```

## Usage

```bash
# Run with your vLLM configuration
uv run python -m massgen.cli --config massgen/configs/basic/multi/three_agents_vllm.yaml "your prompt"
```

## Parameter Handling

### How to Add vLLM Parameters

Simply include vLLM-specific parameters in your backend configuration YAML—they will be automatically processed and passed to the vLLM server.

---

## Backend Architecture

The vLLM backend extends `ChatCompletionsBackend` and implements:

* Custom provider naming (returns `"vLLM"`).
* vLLM-specific API key handling (defaults to `"EMPTY"`).
* Specialized parameter processing in `_build_vllm_extra_body()`.
* Management of extra body parameters for vLLM-specific features.

---

For more details, refer to the [vLLM Official Documentation](https://docs.vllm.ai/en/stable/).