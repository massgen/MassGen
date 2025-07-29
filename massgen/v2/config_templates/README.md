# Configuration Templates

This directory contains pre-built configuration templates for common organizational patterns and use cases.

## Available Templates

### Single Agent Templates

- **`simple_agent.json`** - Basic single agent configuration with standard settings

### Team Templates

- **`research_team.yaml`** - Research team with primary researcher, fact checker, analyst, and reporter
- **`development_team.yaml`** - Software development team with backend, frontend, DevOps, and QA engineers

### Organizational Templates

- **`hierarchical_organization.yaml`** - Complex multi-level organization with departments and teams

## Using Templates

### Loading a Template

```python
from massgen.v2.agent_config import ConfigManager
from massgen.v2.team_factories import create_custom_team

# Load team configuration
team_config = ConfigManager.load_from_file("config_templates/research_team.yaml")

# Create team from configuration
team = create_custom_team(team_config)
```

### Customizing Templates

Templates can be customized by:

1. **Direct modification** - Edit the template files
2. **Environment variables** - Use `${VAR_NAME}` syntax in templates
3. **Runtime configuration** - Override specific settings when loading

### Example: Environment Variable Usage

```yaml
# In template file
api_key: "${OPENAI_API_KEY}"
log_level: "${MASSGEN_LOG_LEVEL:-INFO}"  # Default to INFO if not set
```

```bash
# Set environment variables
export OPENAI_API_KEY="your-api-key"
export MASSGEN_LOG_LEVEL="DEBUG"
```

### Example: Runtime Customization

```python
# Load base template
config = ConfigManager.load_from_file("config_templates/research_team.yaml")

# Customize settings
config["orchestrator"]["max_duration"] = 1200  # 20 minutes instead of 15
config["agents"][0]["model"] = "gpt-4o-mini"   # Use smaller model

# Create team
team = create_custom_team(config)
```

## Template Structure

### Agent Configuration

```yaml
agents:
  - agent_id: "team.role"           # Hierarchical ID
    model: "gpt-4o"                 # LLM model
    provider: "openai"              # Provider (auto-detected if omitted)
    system_message: |               # Multi-line system prompt
      You are a specialist in...
    tags: ["tag1", "tag2"]          # Categorization tags
    max_retries: 3                  # Error handling
    timeout: 300                    # Request timeout
    temperature: 0.7                # Generation parameters (optional)
    max_tokens: 2000                # Token limit (optional)
```

### Orchestrator Configuration

```yaml
orchestrator:
  orchestrator_id: "team_name"
  max_duration: 600                 # Maximum coordination time
  max_rounds: 10                    # Maximum voting rounds
  
  voting_config:
    include_vote_counts: true       # Show vote tallies
    include_vote_reasons: true      # Include reasoning
    anonymous_voting: false         # Attribution setting
    voting_strategy: "simple_majority"
    tie_breaking: "registration_order"
  
  enable_streaming: true            # Real-time updates
  stream_coordination: true         # Stream coordination process
  graceful_restart: true           # Handle interruptions
```

### Hierarchical Organization

For complex organizations, use nested structures:

```yaml
departments:
  - department_id: "engineering"
    teams:
      - team_id: "engineering.backend"
        agents:
          - agent_id: "engineering.backend.senior_architect"
            # ... agent config
```

## Best Practices

1. **Naming Conventions**
   - Use descriptive, hierarchical agent IDs
   - Follow pattern: `organization.department.team.role`
   - Keep names under 50 characters per level

2. **System Messages**
   - Be specific about responsibilities and expertise
   - Include expected output formats
   - Mention collaboration expectations

3. **Voting Configuration**
   - Enable reasoning for complex decisions
   - Use anonymous voting for sensitive topics
   - Choose appropriate tie-breaking strategies

4. **Resource Management**
   - Set reasonable timeouts and retry limits
   - Consider token limits for cost control
   - Use appropriate models for each role

5. **Environment Variables**
   - Never commit API keys to version control
   - Use environment variables for sensitive data
   - Provide sensible defaults

## Creating Custom Templates

To create a new template:

1. Start with an existing template as a base
2. Modify agent roles and system messages
3. Adjust orchestrator settings for your use case
4. Test with validation functions
5. Document any special requirements

### Validation

```python
from massgen.v2.agent_config import validate_config_file

# Validate template
errors = validate_config_file("my_template.yaml")
if errors:
    print("Validation errors:", errors)
else:
    print("Template is valid!")
```