---
name: memory
description: This skill should be used when agents need to store long-term context, decisions, or findings that should persist across conversation turns or be shared with other agents.
license: MIT
---

# Memory Skill

Store and retrieve memories using the filesystem to maintain context across conversation turns.

## Purpose

The memory skill provides a filesystem-based approach to storing and retrieving context that needs to persist across conversation turns. Use standard file operations to save important information, decisions, and findings in the `memory/` directory. Other agents can read (but not modify) these memories from the shared reference path (see system prompt), enabling coordination without explicit communication.

## Directory Structure

```
your_workspace/
  ├── memory/              # Your memory directory
  │   ├── context.txt      # General context/background
  │   ├── decisions.json   # Important decisions made
  │   └── notes.md         # Working notes
  └── workspace/           # Your main working directory

<shared_reference>/      # Read-only access to other agents
  ├── agent1/             # (path varies by config, often temp_workspaces/)
  │   └── memory/          # Agent 1's memories (read-only)
  └── agent2/
      └── memory/          # Agent 2's memories (read-only)
```

**Note**: The shared reference path is shown in your system prompt under "Shared Reference". The default is typically `temp_workspaces/` but can be configured differently.

## When to Use This Skill

Use the memory skill when:

- Important information should persist across conversation turns
- Decisions or context need to be shared with other agents
- User preferences or constraints should be remembered
- Analysis findings should be available for future reference

Do not use for:

- Current task tracking (use `tasks/` skill instead)
- Information that is not necessary to be shared

## How to Use

### Saving Memories

To save a memory, create or update a file in the `memory/` directory:

```bash
# Save a text memory
echo "User prefers JSON format for output" > memory/user_preferences.txt

# Save structured data
cat > memory/context.json << 'EOF'
{
  "project": "web-app",
  "framework": "React",
  "last_task": "Added authentication"
}
EOF
```

### Loading Memories

To load memories from your previous work or other agents:

```bash
# Read your own memories
cat memory/context.txt

# Read another agent's memories (check system prompt for shared reference path)
# Example if shared reference is temp_workspaces/:
cat temp_workspaces/agent1/memory/decisions.json
```

### Organizing Memories

Organize memories by topic or purpose:

```
memory/
  ├── project_context.md   # Project background and goals
  ├── user_preferences.txt # User's stated preferences
  ├── decisions/           # Subdirectory for decisions
  │   ├── architecture.md
  │   └── tech_stack.json
  └── notes/               # Temporary working notes
      └── todo.txt
```

## Best Practices

1. **Be Selective**: Only save information that will be useful in future turns
2. **Use Clear Names**: Use descriptive filenames (e.g., `user_email_preferences.txt` not `prefs.txt`)
3. **Structured Data**: Use JSON for structured data, Markdown for documentation, plain text for simple notes
4. **Read Before Writing**: Check existing memories before creating new ones to avoid duplicates
5. **Respect Read-Only**: You can read other agents' memories but cannot modify them

## Common Patterns

### Save Decision Context
```bash
cat > memory/decision_context.md << 'EOF'
# Architecture Decision: Use PostgreSQL

**Date**: 2025-11-11
**Reason**: User requires ACID compliance for financial transactions
**Alternatives Considered**: MongoDB, MySQL
**Next Steps**: Setup database schema
EOF
```

### Load and Build Upon Previous Work
```bash
# Check if we have context from previous turn
if [ -f memory/project_context.json ]; then
    echo "Loading previous context..."
    cat memory/project_context.json
else
    echo "No previous context found, starting fresh"
fi
```

### Share Findings with Future Agents
```bash
# Save your analysis for future reference
cat > memory/code_analysis.md << 'EOF'
# Code Analysis Results

- Bug found in auth.py line 42
- Security issue: passwords not hashed
- Recommendation: Use bcrypt library
EOF
```

## Integration with MassGen

When `organize_workspace: true` is set in your configuration, your workspace will have the `memory/` directory automatically created alongside `tasks/` and `workspace/`. This provides a clean separation of concerns:

- `memory/` - Long-term context and decisions
- `tasks/` - Current task plans and status
- `workspace/` - Active working files and outputs

## Tips

- **Multi-turn conversations**: Memory persists across turns in the shared reference path
- **Collaboration**: Review other agents' memories to avoid duplicating work
- **Incremental updates**: Update existing memory files rather than creating many small files
- **Cleanup**: Remove outdated memories that are no longer relevant

## See Also

- `tasks` skill - For managing task plans and progress
- `file_search` skill - For searching through code and memory files
