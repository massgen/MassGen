# MassGen Configuration Examples

This directory contains sample configuration files for MassGen CLI usage.

## Configuration Files

### 🤖 Single Agent Configurations

- **`single_agent.yaml`** - Basic single agent setup with OpenAI
  - Simple assistant for general questions
  - Terminal display with logging
  - Uses `gpt-4o-mini` model

### 👥 Multi-Agent Configurations

- **`multi_agent.yaml`** - Three-agent coordination setup
  - **Researcher**: Information gathering and fact-checking (OpenAI)
  - **Analyst**: Critical analysis and pattern recognition (Grok)  
  - **Communicator**: Clear synthesis and presentation (OpenAI)
  - Multi-region terminal display with coordination

- **`research_team.yaml`** - Specialized research team configuration
  - **Information Gatherer**: Web search enabled (Grok)
  - **Domain Expert**: Code interpreter enabled (OpenAI GPT-4o)
  - **Synthesizer**: Integration and summarization (OpenAI)
  - Optimized for research tasks with longer timeouts

## Usage Examples

### Single Agent Mode
```bash
# Using configuration file
python -m massgen.cli --config massgen/configs/single_agent.yaml "What is machine learning?"

# Quick setup without config file
python -m massgen.cli --backend openai --model gpt-4o-mini "Explain quantum computing"
```

### Multi-Agent Mode
```bash
# Research team for complex questions
python -m massgen.cli --config massgen/configs/research_team.yaml "What are the latest developments in renewable energy technology?"

# General multi-agent coordination
python -m massgen.cli --config massgen/configs/multi_agent.yaml "Compare different programming languages for web development"
```

### Interactive Mode
```bash
# Start interactive session
python -m massgen.cli --config massgen/configs/multi_agent.yaml

# Quick interactive setup
python -m massgen.cli --backend openai --model gpt-4o-mini
```

## Configuration Structure

### Agent Configuration
```yaml
agent:  # Single agent
  id: "agent_name"
  backend:
    type: "openai" | "grok"
    model: "model_name"
    api_key: "optional_key"  # Uses env vars by default
  system_message: "Agent role and instructions"

agents:  # Multiple agents (alternative to 'agent')
  - id: "agent1"
    backend: {...}
    system_message: "..."
  - id: "agent2"
    backend: {...}
    system_message: "..."
```

### UI Configuration
```yaml
ui:
  display_type: "terminal" | "simple"
  logging_enabled: true | false
```

### Optional Parameters
```yaml
orchestrator:
  voting_timeout: 30
  max_coordination_rounds: 3
  require_consensus: false

backend_params:
  temperature: 0.7
  max_tokens: 2000
  enable_web_search: true  # Grok backend
  enable_code_interpreter: true  # OpenAI backend
```

## Environment Variables

Set these environment variables for API access:

```bash
export OPENAI_API_KEY="your-openai-api-key"
export XAI_API_KEY="your-grok-api-key"
```

## Backend Support

### OpenAI Backend
- **Models**: `gpt-4o`, `gpt-4o-mini`, `gpt-3.5-turbo`
- **Tools**: Web search, code interpreter, custom functions
- **Features**: Full tool combination support

### Grok Backend  
- **Models**: `grok-3-mini`, `grok-2-mini`
- **Tools**: Web search, custom functions
- **Features**: Real-time web access

## Tips

1. **Start Simple**: Use `single_agent.yaml` for basic testing
2. **Research Tasks**: Use `research_team.yaml` for complex analysis
3. **Interactive Mode**: Great for exploring and iterating on questions
4. **Tool Access**: Enable web search or code interpreter in backend config
5. **Cost Management**: Use `gpt-4o-mini` for cost-effective operations

## Creating Custom Configurations

Copy and modify any of these examples to create your own configurations. The system is flexible and supports various agent combinations and specializations.