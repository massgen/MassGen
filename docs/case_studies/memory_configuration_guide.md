# Memory Configuration Quick Reference

This guide provides quick examples for configuring persistent memory in MassGen agents.

## Basic Memory Configuration

```yaml
agents:
  - id: "my-agent"
    backend:
      type: "openai"
      model: "gpt-5-mini"
    
    persistent_memory:
      enabled: true
      agent_name: "my_agent_name"
      user_name: "user_identifier"  # optional
      session_name: "session_id"    # optional
      on_disk: true
      
      # LLM for memory operations (summarization, extraction)
      llm:
        backend_type: "openai"
        model: "gpt-5-mini"
      
      # Embeddings for semantic search
      embedding:
        backend_type: "openai"
        model: "text-embedding-3-small"
```

## Multi-Agent with Independent Memory

```yaml
agents:
  - id: "researcher"
    backend:
      type: "openai"
      model: "gpt-5-mini"
    persistent_memory:
      enabled: true
      agent_name: "research_specialist"
      llm:
        backend_type: "openai"
        model: "gpt-5-mini"
      embedding:
        backend_type: "openai"
        model: "text-embedding-3-small"

  - id: "analyst"
    backend:
      type: "gemini"
      model: "gemini-2.5-flash"
    persistent_memory:
      enabled: true
      agent_name: "data_analyst"
      llm:
        backend_type: "gemini"
        model: "gemini-2.5-flash"
      embedding:
        backend_type: "openai"
        model: "text-embedding-3-small"
```

## Memory with Session Isolation

```yaml
agents:
  - id: "assistant"
    backend:
      type: "claude"
      model: "claude-3-5-haiku"
    persistent_memory:
      enabled: true
      agent_name: "personal_assistant"
      user_name: "john_doe"
      session_name: "2025-01-15_morning"  # Separate memory per session
      on_disk: true
```

## Memory Configuration Options

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `enabled` | bool | Enable persistent memory | Yes |
| `agent_name` | str | Unique identifier for this agent's memory | Yes |
| `user_name` | str | Associate memory with specific user | No |
| `session_name` | str | Isolate memory by session | No |
| `on_disk` | bool | Persist memory to disk (survives restarts) | No (default: false) |
| `llm` | dict | LLM backend for memory operations | Yes |
| `embedding` | dict | Embedding backend for semantic search | Yes |

## LLM Backend Options

```yaml
# OpenAI
llm:
  backend_type: "openai"
  model: "gpt-5-mini"  # or "gpt-4", "gpt-5-nano", etc.

# Gemini
llm:
  backend_type: "gemini"
  model: "gemini-2.5-flash"  # or "gemini-2.5-pro"

# Claude
llm:
  backend_type: "claude"
  model: "claude-3-5-haiku"  # or "claude-3-5-sonnet"
```

## Embedding Backend Options

```yaml
# OpenAI Embeddings (Recommended)
embedding:
  backend_type: "openai"
  model: "text-embedding-3-small"  # Fast, good quality
  # or "text-embedding-3-large"     # Slower, best quality

# Gemini Embeddings
embedding:
  backend_type: "gemini"
  model: "text-embedding-004"

# Note: Embedding model must support text embeddings
```

## Use Cases

### Codebase Analysis
- **Memory**: Retain architectural insights across 30+ files
- **Config**: High-capacity LLM (gpt-4, gemini-2.5-pro), efficient embeddings

### Multi-Session Support
- **Memory**: Remember user preferences and conversation history
- **Config**: Set `user_name` and `session_name` for isolation

### Collaborative Research
- **Memory**: Each agent maintains independent knowledge base
- **Config**: Different `agent_name` per agent, shared `user_name`

### Long-Term Projects
- **Memory**: Persist insights across days/weeks
- **Config**: Set `on_disk: true` for durability

## Testing Memory Configuration

```bash
# Test basic memory
uv run python -m massgen.cli \
  --config your_memory_config.yaml \
  "Tell me your name and remember it"

# Verify memory in new session
uv run python -m massgen.cli \
  --config your_memory_config.yaml \
  "What name did I tell you before?"
```

## Troubleshooting

**Issue**: Memory not persisting between sessions
- **Solution**: Ensure `on_disk: true` is set
- **Check**: Verify write permissions in memory storage directory

**Issue**: Slow memory retrieval
- **Solution**: Use smaller embedding model (text-embedding-3-small)
- **Check**: Reduce search scope with more specific queries

**Issue**: High memory usage
- **Solution**: Implement periodic memory cleanup
- **Check**: Use session isolation to limit memory size

**Issue**: Memory not found
- **Solution**: Verify `agent_name`, `user_name`, `session_name` match exactly
- **Check**: Case-sensitive, ensure consistency across sessions

## Advanced: Custom Vector Store

```yaml
persistent_memory:
  enabled: true
  agent_name: "my_agent"
  on_disk: true
  
  # Custom vector store configuration
  vector_store:
    provider: "qdrant"  # or "chroma", "pinecone"
    config:
      path: "./custom_memory_path"
      collection_name: "my_memories"
      # Provider-specific options...
  
  llm:
    backend_type: "openai"
    model: "gpt-5-mini"
  
  embedding:
    backend_type: "openai"
    model: "text-embedding-3-small"
```

## Complete Example: FastAPI Analysis

See [`codebase_analysis_with_memory.yaml`](../../../massgen/configs/case_studies/codebase_analysis_with_memory.yaml) for a full working example with:
- ✅ Two agents with independent memory
- ✅ Filesystem and command-line tools
- ✅ On-disk persistence
- ✅ Semantic retrieval configuration

## Related Documentation

- [Memory System README](../../../massgen/memory/README.md) - Detailed memory API documentation
- [Memory Examples](../../../massgen/memory/examples.py) - Code examples for memory usage
- [Memory Case Study](./memory_enabled_codebase_analysis.md) - Complete use case demonstration
