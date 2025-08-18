# Azure OpenAI Setup Guide for MassGen

This guide explains how to set up and use Azure OpenAI with MassGen.

## Prerequisites

1. **Azure OpenAI Service**: You need an Azure OpenAI service deployed in your Azure subscription
2. **Deployment**: At least one model deployment (e.g., GPT-4, GPT-3.5-turbo)
3. **API Key**: Your Azure OpenAI API key
4. **Endpoint URL**: Your Azure OpenAI endpoint URL

## Environment Variables

Set the following environment variables in your `.env` file:

```bash
# Azure OpenAI Configuration
AZURE_OPENAI_API_KEY=your_azure_openai_api_key_here
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-02-15-preview
```

## Configuration

### Single Agent Configuration

```yaml
# azure_openai_single.yaml
agent:
  id: "azure_gpt4_agent"
  backend:
    type: "azure_openai"
    model: "gpt-4.1"  # Your Azure OpenAI deployment name
    enable_web_search: true
    enable_code_interpreter: true
  system_message: "You are a helpful AI assistant powered by Azure OpenAI."
```

### Multi-Agent Configuration

```yaml
# azure_openai_multi.yaml
agents:
  - id: "azure_gpt4"
    backend:
      type: "azure_openai"
      model: "gpt-4.1"  # Your deployment name
      enable_web_search: true
      enable_code_interpreter: true
    system_message: "You are an expert AI assistant powered by Azure OpenAI GPT-4.1."

  - id: "azure_gpt35_turbo"
    backend:
      type: "azure_openai"
      model: "gpt-35-turbo"  # Your deployment name
      enable_web_search: true
      enable_code_interpreter: true
    system_message: "You are a helpful AI assistant powered by Azure OpenAI GPT-3.5."
```

## Usage Examples

### Quick Setup with Azure OpenAI

```bash
# Single agent with Azure OpenAI
uv run python -m massgen.cli --backend azure_openai --model gpt-4.1 "Explain quantum computing"

# Using configuration file
uv run python -m massgen.cli --config azure_openai_single.yaml "What is machine learning?"

# Multi-agent setup
uv run python -m massgen.cli --config azure_openai_multi.yaml "Compare different approaches to renewable energy"
```

### Interactive Mode

```bash
# Start interactive mode with Azure OpenAI
uv run python -m massgen.cli --backend azure_openai --model gpt-4.1

# Interactive mode with configuration file
uv run python -m massgen.cli --config azure_openai_single.yaml
```

## Important Notes

1. **Deployment Names**: The `model` parameter should be your Azure OpenAI deployment name, not the model family name
2. **Endpoint Format**: The endpoint should be your Azure OpenAI resource URL (e.g., `https://your-resource.openai.azure.com/`)
3. **API Version**: The default API version is `2024-02-15-preview`, but you can override this in your configuration
4. **Tools Support**: Azure OpenAI supports web search and code interpreter when enabled in your deployment

## Troubleshooting

### Common Issues

1. **Authentication Error**: Ensure your `AZURE_OPENAI_API_KEY` is correct and has access to the deployment
2. **Endpoint Error**: Verify your `AZURE_OPENAI_ENDPOINT` is correct and the service is running
3. **Deployment Not Found**: Make sure the deployment name in your config matches exactly with your Azure OpenAI deployment
4. **API Version**: Some features may require specific API versions - check Azure OpenAI documentation for compatibility

### Getting Help

- Check Azure OpenAI service status in Azure portal
- Verify deployment configuration and model availability
- Review Azure OpenAI API documentation for endpoint and authentication details
