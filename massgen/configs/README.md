# MassGen Configuration Examples

This directory contains sample configuration files for MassGen CLI usage. Each configuration is optimized for specific use cases and demonstrates different agent collaboration patterns.

## 📁 Available Configurations

### 🤖 Single Agent Configurations

- **`single_agent.yaml`** - Basic single agent setup with Gemini
  - Uses Gemini 2.5 Flash model
  - Web search enabled for current information
  - Rich terminal display with token usage tracking

### 👥 Multi-Agent Configurations

#### General Purpose Teams

- **`three_agents_default.yaml`** - Default three-agent setup with frontier models
  - **Gemini 2.5 Flash**: Web search enabled
  - **GPT-4o-mini**: Web search and code interpreter enabled
  - **Grok-3-mini**: Web search with citations
  - Best for general questions requiring diverse perspectives

- **`gemini_4o_claude.yaml`** - Premium three-agent configuration
  - **Gemini 2.5 Flash**: Web search enabled
  - **GPT-4o**: Full GPT-4o with web search and code interpreter
  - **Claude 3.5 Haiku**: Web search with citations
  - Higher quality responses for complex tasks

- **`two_agents.yaml`** - Focused two-agent collaboration
  - **Primary Agent (GPT-4o)**: Comprehensive research and analysis
  - **Secondary Agent (GPT-4o-mini)**: Review and refinement
  - Efficient for tasks needing depth with validation

#### Specialized Teams

- **`research_team.yaml`** - Academic/technical research configuration
  - **Information Gatherer (Grok)**: Web search specialist
  - **Domain Expert (GPT-4o)**: Deep analysis with code interpreter
  - **Synthesizer (GPT-4o-mini)**: Integration and summarization
  - Low temperature (0.3) for accuracy

- **`creative_team.yaml`** - Creative writing and storytelling
  - **Storyteller (GPT-4o)**: Narrative creation
  - **Editor (GPT-4o-mini)**: Structure and flow refinement
  - **Critic (Grok-3-mini)**: Literary analysis
  - High temperature (0.8) for creativity

- **`news_analysis.yaml`** - Current events and news synthesis
  - **News Gatherer (GPT-4o)**: Finding current events
  - **Trend Analyst (Grok-3-mini)**: Pattern identification
  - **News Synthesizer (GPT-4o-mini)**: Balanced summaries
  - Medium temperature (0.4) for balanced analysis

- **`technical_analysis.yaml`** - Technical queries and cost estimation
  - **Technical Researcher (GPT-4o)**: Specifications and documentation
  - **Cost Analyst (Grok-3-mini)**: Pricing and cost calculations
  - **Technical Advisor (GPT-4o-mini)**: Practical recommendations
  - Low temperature (0.2) for precision

- **`travel_planning.yaml`** - Travel recommendations and planning
  - **Travel Researcher (GPT-4o)**: Destination information
  - **Local Expert (Grok-3-mini)**: Insider knowledge
  - **Travel Planner (GPT-4o-mini)**: Itinerary organization
  - Medium temperature (0.6) for balanced suggestions

## 🚀 Usage Examples

### Single Agent Mode
```bash
# Using configuration file
uv run python -m massgen.cli --config single_agent.yaml "What is machine learning?"

# Quick setup without config file
uv run python -m massgen.cli --model gemini-2.5-flash "Explain quantum computing"
```

### Multi-Agent Mode
```bash
# Default three agents for general questions
uv run python -m massgen.cli --config three_agents_default.yaml "Compare renewable energy technologies"

# Premium agents for complex analysis
uv run python -m massgen.cli --config gemini_4o_claude.yaml "Analyze the implications of quantum computing on cryptography"

# Specialized teams for specific tasks
uv run python -m massgen.cli --config research_team.yaml "Latest developments in CRISPR gene editing"
uv run python -m massgen.cli --config creative_team.yaml "Write a short story about AI consciousness"
uv run python -m massgen.cli --config news_analysis.yaml "What happened in tech news this week?"
uv run python -m massgen.cli --config technical_analysis.yaml "Cost analysis for running LLMs at scale"
uv run python -m massgen.cli --config travel_planning.yaml "Plan a 5-day trip to Tokyo in spring"
```

### Interactive Mode
```bash
# Start interactive session with any configuration
uv run python -m massgen.cli --config gemini_4o_claude.yaml

# Commands in interactive mode:
# /clear - Clear conversation history
# /quit, /exit, /q - Exit the session
```

## 📋 Configuration Structure

### Basic Structure
```yaml
# Single agent
agent:
  id: "agent_name"
  backend:
    type: "claude" | "openai" | "grok" | "gemini"
    model: "model_name"
    api_key: "optional_key"  # Uses env vars by default
  system_message: "Agent role and instructions"

# Multiple agents
agents:
  - id: "agent1"
    backend: {...}
    system_message: "..."
  - id: "agent2"
    backend: {...}
    system_message: "..."
```

### Backend Configuration
```yaml
backend:
  type: "openai"           # "openai", "claude", "gemini", "grok"
  model: "gpt-4o"          # Model name
  api_key: "optional_key"  # API key (uses env vars by default)
  temperature: 0.7         # Creativity vs consistency (0.0-1.0)
  max_tokens: 2500         # Maximum response length
  enable_web_search: true  # Web search capability (all backends)
  enable_code_interpreter: true  # OpenAI only
  enable_code_execution: true    # Gemini/Claude only
```

### UI Configuration
```yaml
ui:
  display_type: "rich_terminal" | "terminal" | "simple"
  logging_enabled: true | false
```

### Advanced Parameters
```yaml
# Orchestrator settings
orchestrator:
  voting_timeout: 30
  max_coordination_rounds: 3
  require_consensus: false

# Global backend parameters
backend_params:
  temperature: 0.7
  max_tokens: 2000

# Web search advanced parameters
web_search:
  return_citations: true         # Include search result citations (Grok/Claude)
  max_search_results: 10         # Maximum search results to use (Grok)
  search_mode: "auto"            # Search strategy: "auto", "fast", "thorough" (Grok)

# Code execution advanced parameters  
code_execution:
  container_type: "auto"         # Container type for OpenAI code interpreter
```

## 🔧 Environment Variables

Set these in your `.env` file:

```bash
# API Keys
ANTHROPIC_API_KEY="your-anthropic-key"
GEMINI_API_KEY="your-gemini-key"
OPENAI_API_KEY="your-openai-key"
XAI_API_KEY="your-xai-key"
```

## 💡 Backend Capabilities

| Backend | Live Search | Code Execution |
|---------|:-----------:|:--------------:|
| **Claude** | ✅ | ✅ |
| **OpenAI** | ✅ | ✅ |
| **Grok** | ✅ | ❌ |
| **Gemini** | ✅ | ✅ |

## 📚 Best Practices

1. **Choose the Right Configuration**
   - Use `three_agents_default.yaml` for general questions
   - Use specialized teams for domain-specific tasks
   - Use `single_agent.yaml` for quick, simple queries

2. **Temperature Settings**
   - Low (0.1-0.3): Technical analysis, factual information
   - Medium (0.4-0.6): Balanced tasks, general questions
   - High (0.7-0.9): Creative writing, brainstorming

3. **Cost Optimization**
   - Use mini models (gpt-4o-mini, grok-3-mini) for routine tasks
   - Reserve premium models (gpt-4o, claude-3-5-sonnet) for complex analysis
   - Single agent mode is most cost-effective for simple queries

4. **Tool Usage**
   - Enable web search for current events and real-time information
   - Use code interpreter for data analysis and calculations
   - Combine tools for comprehensive research tasks

## 🛠️ Creating Custom Configurations

1. Copy an existing configuration as a template
2. Modify agent roles and system messages for your use case
3. Adjust temperature and max_tokens based on task requirements
4. Enable/disable tools based on agent needs
5. Test with sample queries to refine the configuration

Example custom configuration for code review:
```yaml
agents:
  - id: "code_analyzer"
    backend:
      type: "openai"
      model: "gpt-4o"
      temperature: 0.2
      enable_code_interpreter: true
    system_message: "Analyze code for bugs, security issues, and best practices"
    
  - id: "refactoring_expert"
    backend:
      type: "claude"
      model: "claude-3-5-sonnet-20250514"
      temperature: 0.3
    system_message: "Suggest code improvements and refactoring opportunities"
```