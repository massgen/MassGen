# Inference Backend Implementation Guide

## Overview

The inference backend (`massgen/backend/inference.py`) provides unified OpenAI-compatible integration with both vLLM and SGLang servers for high-performance local model deployment within the MassGen framework.

## vLLM Implementation

### Overview

The vLLM backend option shares the same inference backend class, but is configured to connect to vLLM servers that provide OpenAI-compatible APIs.

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

If you need specific parameters that aren't automatically handled, you can wrap them in an `extra_body` configuration in your YAML file:

---

## Backend Architecture

The vLLM backend extends `ChatCompletionsBackend` and implements:

* Custom provider naming (returns `"vLLM"`).
* vLLM-specific API key handling (defaults to `"EMPTY"`).
* Specialized parameter processing in `_build_vllm_extra_body()`.
* Management of extra body parameters for vLLM-specific features.

---

For more details, refer to the [vLLM Official Documentation](https://docs.vllm.ai/en/stable/).

---

## SGLang Implementation

### Overview

The SGLang backend option shares the same inference backend class, but is configured to connect to SGLang servers that provide OpenAI-compatible APIs.

### Key Features

* **OpenAI-Compatible**: Uses SGLang's OpenAI-compatible endpoint at `/v1`.
* **Tool Call Parser**: Supports Qwen-family tool call parsing (e.g. `--tool-call-parser qwen25`).
* **Thinking Mode**: Forward compatible with `chat_template_kwargs.enable_thinking` and `separate_reasoning` in `extra_body`.

---

## Configuration

### Example Configuration (`two_qwen_vllm_sglang.yaml`)

```yaml
agents:
  - id: "qwen1"
    backend:
      type: "vllm"
      model: "Qwen/Qwen3-4B"
      base_url: "http://localhost:8000/v1"
      chat_template_kwargs:
        enable_thinking: True
      top_k: 50
  - id: "qwen2"
    backend:
      type: "sglang"
      model: "Qwen/Qwen3-4B"
      base_url: "http://localhost:30000/v1"
      extra_body:
        chat_template_kwargs:
          enable_thinking: True
```

---

### Example Backend Configuration with SGLang Parameters

```yaml
backend:
  type: "sglang"
  model: "Qwen/Qwen3-4B"
  base_url: "http://localhost:30000/v1"
  extra_body:
    chat_template_kwargs:
      enable_thinking: true
```

---

## Base URL Configuration

The `base_url` should be specified in your config YAML file under the backend configuration. Here are example configurations:

```yaml
backend:
  type: "sglang"
  model: "Qwen/Qwen3-4B"
  base_url: "http://localhost:30000/v1"  # Local server (default)
  # OR for remote/tunneled servers:
  # base_url: "http://your-remote-server:30000/v1" # replace with the server url
```

---

## Environment Variables

```bash
# SGLang API key (default "EMPTY" for local servers)
export SGLANG_API_KEY="EMPTY"
```

---

## SGLang Server Startup

```bash
# SGLang server
python -m sglang.launch_server \
  --model-path Qwen/Qwen3-4B \
  --tool-call-parser qwen25 \
  --tensor-parallel-size 1 \
  --log-level debug \
  --log-requests \
  --log-requests-level 1 \
  --show-time-cost \
  --port 30000
```

## Usage

```bash
# Run with your SGLang configuration
uv run python -m massgen.cli --config massgen/configs/basic/multi/two_qwen_vllm_sglang.yaml "your prompt"
```

## Parameter Handling

### How to Add SGLang Parameters

Simply include SGLang-specific parameters in your backend configuration YAML—they will be automatically processed and passed to the SGLang server.

If you need specific parameters that aren't automatically handled, you can wrap them in an `extra_body` configuration in your YAML file:

---

## Backend Architecture

The SGLang backend extends the unified `InferenceBackend` and implements:

* Custom provider naming (returns `"SGLang"`).
* SGLang-specific API key handling (defaults to `"EMPTY"`).
* Specialized parameter processing in `_build_extra_body()` for SGLang-specific features like `chat_template_kwargs` and `separate_reasoning`.

---

For more details, refer to the [SGLang Official Documentation](https://docs.sglang.ai/).