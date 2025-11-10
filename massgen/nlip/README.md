# NLIP Integration for MassGen

NLIP (Natural Language Interaction Protocol) is a universal application-level protocol for AI agent communication, being standardized by Ecma International TC56. This module provides NLIP support for MassGen, enabling standardized agent-to-agent communication.

## Overview

The NLIP integration provides:

- **Optional Middleware**: NLIP can be enabled/disabled via configuration
- **Unified Tool Router**: Single routing layer that translates between NLIP and existing tool protocols
- **Protocol Translation**: Bidirectional translation between NLIP and MCP/custom/built-in tools
- **Backward Compatibility**: Existing tools work without modification
- **Standardized Schema**: NLIP message schema with `format`, `control`, and `token` fields

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    MassGen Orchestrator                     │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
         ┌───────────────────────────────┐
         │   NLIP Middleware Layer       │
         │   (Optional - if enabled)     │
         └───────────────┬───────────────┘
                         │
                         ▼
         ┌───────────────────────────────┐
         │      NLIP Router              │
         │  (massgen/nlip/router.py)     │
         │                               │
         │  • Message Translation        │
         │  • Protocol Detection         │
         │  • State Management           │
         │  • Token Tracking             │
         └───────────────┬───────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
    ┌────────┐    ┌──────────┐    ┌──────────┐
    │  MCP   │    │  Custom  │    │ Built-in │
    │ Tools  │    │  Tools   │    │  Tools   │
    └────────┘    └──────────┘    └──────────┘
```

## Module Structure

```
massgen/nlip/
├── __init__.py                 # Module exports
├── router.py                   # Main NLIP message router
├── schema.py                   # NLIP message schema definitions
├── state_manager.py            # State and context tracking
├── token_tracker.py            # Token field management
└── translator/                 # Protocol translators
    ├── __init__.py
    ├── base.py                 # Base translator interface
    ├── mcp_translator.py       # MCP ↔ NLIP translation
    ├── custom_translator.py    # Custom tools ↔ NLIP
    └── builtin_translator.py   # Built-in tools ↔ NLIP
```

## Quick Start

### 1. Enable NLIP for a Single Agent

```python
from massgen.agent_config import AgentConfig

# Create agent config with NLIP enabled
config = AgentConfig(
    backend_params={
        "type": "openai",
        "model": "gpt-4o-mini"
    },
    agent_id="nlip_agent",
    enable_nlip=True,
    nlip_config={
        "router": {
            "enable_message_tracking": True,
            "session_timeout_hours": 24
        }
    }
)
```

### 2. Enable NLIP for Multi-Agent Orchestrator

```python
from massgen import Orchestrator
from massgen.agent_config import AgentConfig

# Create NLIP-enabled agents
agents = {}
for i in range(3):
    config = AgentConfig(
        backend_params={"type": "openai", "model": "gpt-4o-mini"},
        agent_id=f"agent_{i}",
        enable_nlip=True
    )
    # agents[config.agent_id] = create_agent_from_config(config)

# Create orchestrator with NLIP
orchestrator = Orchestrator(
    agents=agents,
    enable_nlip=True,
    nlip_config={
        "router": {
            "enable_message_tracking": True
        }
    }
)
```

### 3. Use NLIP Router Directly

```python
from massgen.nlip import (
    NLIPRouter, NLIPRequest, NLIPToolCall,
    NLIPControlField, NLIPTokenField, NLIPFormatField,
    NLIPMessageType
)
import uuid
from datetime import datetime

# Initialize router
router = NLIPRouter(
    tool_manager=tool_manager,
    enable_nlip=True
)

# Create NLIP request
request = NLIPRequest(
    format=NLIPFormatField(
        content_type="application/json",
        encoding="utf-8",
        schema_version="1.0"
    ),
    control=NLIPControlField(
        message_type=NLIPMessageType.REQUEST,
        message_id=str(uuid.uuid4()),
        timestamp=datetime.utcnow().isoformat() + "Z"
    ),
    token=NLIPTokenField(
        session_id="session_123",
        context_token="ctx_456",
        conversation_turn=1
    ),
    content={"query": "Search for information"},
    tool_calls=[
        NLIPToolCall(
            tool_id="call_1",
            tool_name="mcp__web_search",
            parameters={"query": "AI agent protocols"},
            require_confirmation=False
        )
    ]
)

# Route message
async for response in router.route_message(request):
    print(f"Response: {response.content}")
```

## NLIP Message Schema

NLIP messages follow a standardized structure with three main components:

### Format Field
Defines content structure and encoding:
- `content_type`: MIME type (default: "application/json")
- `encoding`: Character encoding (default: "utf-8")
- `schema_version`: NLIP schema version (default: "1.0")
- `compression`: Optional compression algorithm

### Control Field
Message routing and lifecycle metadata:
- `message_type`: REQUEST, RESPONSE, NOTIFICATION, or ERROR
- `message_id`: Unique message identifier
- `correlation_id`: Links request and response
- `timestamp`: ISO 8601 timestamp
- `priority`: Message priority (0-10)
- `timeout`: Optional timeout in seconds
- `retry_count`: Number of retries

### Token Field
State and session management:
- `session_id`: Session identifier for multi-turn conversations
- `context_token`: Opaque token for context maintenance
- `state_token`: Token for distributed state management
- `conversation_turn`: Turn number in conversation

## Protocol Translators

The NLIP router uses protocol translators to convert between NLIP messages and native tool formats:

### MCP Translator
Converts between NLIP and Model Context Protocol (MCP) format:
- Detects tools with `mcp__` prefix
- Translates to MCP's `tool_use` format
- Handles MCP-specific result structures

### Custom Tool Translator
Handles custom MassGen tools:
- Uses MassGen's native tool format
- Preserves parameter structures
- Maintains tool metadata

### Builtin Tool Translator
Translates built-in MassGen tools (vote, new_answer, etc.):
- Handles confirmation requirements
- Preserves tool-specific options
- Maintains tool categories

## Configuration Options

### Agent-Level Configuration

```python
config = AgentConfig(
    enable_nlip=True,
    nlip_config={
        "router": {
            "enable_message_tracking": True,
            "enable_state_management": True,
            "session_timeout_hours": 24,
            "default_timeout": 300
        },
        "translation": {
            "mcp_enabled": True,
            "custom_tools_enabled": True,
            "builtin_tools_enabled": True
        },
        "tokens": {
            "auto_generate_sessions": True,
            "track_conversation_turns": True,
            "persist_context_tokens": False
        }
    }
)
```

### Orchestrator-Level Configuration

```python
orchestrator = Orchestrator(
    agents=agents,
    enable_nlip=True,
    nlip_config={
        "router": {
            "enable_message_tracking": True,
            "coordinate_via_nlip": True
        }
    }
)
```

## YAML Configuration

See `massgen/configs/examples/nlip_basic.yaml` for a complete YAML configuration example.

## Examples

Complete working examples are available in:
- `massgen/configs/examples/nlip_usage_example.py` - Python usage examples
- `massgen/configs/examples/nlip_basic.yaml` - YAML configuration

Run the examples:
```bash
python -m massgen.configs.examples.nlip_usage_example
```

## Benefits

1. **Standardization**: Adopts Ecma TC56 NLIP standard for agent communication
2. **Interoperability**: Agents can communicate with other NLIP-compliant systems
3. **Unified Interface**: Single entry point for all tool routing
4. **Protocol Agnostic**: Tools don't need to know about NLIP
5. **Backward Compatible**: Zero impact when NLIP is disabled
6. **Extensible**: Easy to add new protocol translators

## API Reference

### NLIPRouter

Main router class for NLIP message routing:

```python
router = NLIPRouter(
    tool_manager: ToolManager,
    enable_nlip: bool = True,
    config: Optional[Dict[str, Any]] = None
)

# Route a message
async for response in router.route_message(message):
    # Process response
    pass

# Check if enabled
if router.is_enabled():
    # NLIP routing active
    pass
```

### NLIPStateManager

Manages session state and context:

```python
state_manager = NLIPStateManager()

# Create session
await state_manager.create_session("session_id", metadata={})

# Update session
await state_manager.update_session("session_id", message)

# Get session context
context = await state_manager.get_session_context("session_id")
```

### NLIPTokenTracker

Tracks tokens and conversation turns:

```python
tracker = NLIPTokenTracker()

# Create session token
token = tracker.create_session_token(agent_id="agent_1")

# Increment turn
new_token = tracker.increment_turn(token)

# Get session info
info = tracker.get_session_info(token.session_id)
```

## Design Documentation

For detailed design information, see:
- `docs/dev_notes/nlip_integration_design.md` - Complete design specification

## Testing

Run tests for NLIP integration:
```bash
pytest massgen/tests/nlip/
```

## Contributing

When adding new protocol translators:

1. Extend `ProtocolTranslator` base class
2. Implement `nlip_to_native_call()`, `native_to_nlip_result()`, and `nlip_to_native_params()`
3. Register translator in `NLIPRouter`
4. Add tests in `massgen/tests/nlip/`

## References

- **Ecma International TC56**: https://ecma-international.org/
- **NLIP Specification**: https://github.com/nlip-project/ecma_draft
- **MassGen Documentation**: See main MassGen README

## License

Part of MassGen framework - see main license file.
