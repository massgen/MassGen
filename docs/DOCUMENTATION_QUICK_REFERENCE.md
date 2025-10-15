# MassGen Documentation Quick Reference

**For:** Documentation writers and maintainers
**Last Updated:** October 8, 2025

---

## The Core Truth

**MassGen is a CLI tool with YAML configuration.**

It is **NOT** a Python library. There are no importable `Agent`, `Orchestrator`, or backend classes.

---

## Quick Audit Results

### ✅ Accurate Files (KEEP)
- index.rst
- quickstart/installation.rst
- quickstart/running-massgen.rst
- user_guide/concepts.rst
- user_guide/multi_turn_mode.rst
- user_guide/mcp_integration.rst
- user_guide/file_operations.rst
- user_guide/project_integration.rst
- user_guide/ag2_integration.rst
- reference/cli.rst
- reference/yaml_schema.rst
- reference/supported_models.rst

### ❌ Fictional Files (REWRITE)
- quickstart/configuration.rst
- user_guide/backends.rst
- user_guide/tools.rst
- user_guide/advanced_usage.rst
- examples/basic_examples.rst
- examples/advanced_patterns.rst
- examples/case_studies.rst

---

## How MassGen Actually Works

### Correct Usage Pattern

```bash
# Single agent - quick test
uv run python -m massgen.cli --model gemini-2.5-flash "Your question"

# Multi-agent with config file
massgen --config @examples/basic/multi/three_agents_default \
  "Your question"

# Interactive mode
uv run python -m massgen.cli \
  --config massgen/configs/basic/multi/three_agents_default.yaml
```

### Correct YAML Configuration

```yaml
agents:
  - id: "gemini_agent"
    backend:
      type: "gemini"
      model: "gemini-2.5-flash"
    system_message: "You are a helpful assistant."

  - id: "gpt_agent"
    backend:
      type: "openai"
      model: "gpt-5-nano"

orchestrator:
  max_rounds: 5
  voting_config:
    threshold: 0.6
```

### Incorrect (Fictional) Pattern

```python
# THIS DOES NOT EXIST - Do not document this!
from massgen import Agent, Orchestrator
from massgen.backends import OpenAIBackend

agent = Agent(name="MyAgent", backend=OpenAIBackend())
```

---

## Documentation Sources of Truth

### 1. README.md (PRIMARY)
- **Location:** `/Users/ncrispin/GitHubProjects/MassGen/README.md`
- **Status:** Authoritative, comprehensive, accurate
- **Use for:** All feature documentation, examples, configuration

### 2. Release Notes
- **v0.0.28:** `/Users/ncrispin/GitHubProjects/MassGen/docs/releases/v0.0.28/release-notes.md`
  - AG2 Integration
  - External agent framework support
- **v0.0.29:** `/Users/ncrispin/GitHubProjects/MassGen/docs/releases/v0.0.29/release-notes.md`
  - MCP Planning Mode
  - File operation safety
  - Enhanced MCP tool filtering

### 3. Configuration Examples
- **Location:** `/Users/ncrispin/GitHubProjects/MassGen/massgen/configs/`
- **Use for:** Real, tested YAML examples
- **Structure:**
  - `basic/single/` - Single agent configs
  - `basic/multi/` - Multi-agent configs
  - `tools/mcp/` - MCP integration
  - `tools/filesystem/` - File operations
  - `ag2/` - AG2 integration

### 4. Backend Configuration Guide
- **Location:** `/Users/ncrispin/GitHubProjects/MassGen/massgen/configs/BACKEND_CONFIGURATION.md`
- **Use for:** Detailed backend configuration parameters

---

## Key Features by Version

### v0.0.29 (Current - Oct 8, 2025)
- ✅ MCP Planning Mode
- ✅ File operation safety (read-before-delete)
- ✅ Enhanced MCP tool filtering
- ✅ Gemini planning mode support

### v0.0.28 (Oct 6, 2025)
- ✅ AG2 Framework Integration
- ✅ External agent adapter system
- ✅ Code execution via AG2

### v0.0.27 and Earlier
- ✅ Multimodal support (images)
- ✅ File operations
- ✅ MCP integration
- ✅ Multi-turn mode
- ✅ Context paths
- ✅ Multiple backends (OpenAI, Claude, Gemini, Grok, etc.)

---

## Backend Support Matrix

Copy from README.md Table:

| Backend | Type in YAML | Live Search | Code Execution | File Operations | MCP Support |
|---------|-------------|-------------|----------------|-----------------|-------------|
| Azure OpenAI | `azure_openai` | ❌ | ❌ | ❌ | ❌ |
| Claude API | `claude` | ✅ | ✅ | ✅ | ✅ |
| Claude Code | `claude_code` | ✅ | ✅ | ✅ | ✅ |
| Gemini API | `gemini` | ✅ | ✅ | ✅ | ✅ |
| Grok API | `grok` | ✅ | ❌ | ✅ | ✅ |
| OpenAI API | `openai` | ✅ | ✅ | ✅ | ✅ |
| ZAI API | `zai` | ❌ | ❌ | ✅ | ✅ |
| AG2 | `ag2` | Varies | ✅ | Varies | Varies |
| LM Studio | `lmstudio` | ❌ | ❌ | ❌ | ❌ |

---

## Common Documentation Patterns

### Pattern 1: CLI Example
```rst
.. code-block:: bash

   # Brief description of what this does
   massgen --config @examples/path_to_config \
     "Your question or task"
```

### Pattern 2: YAML Configuration
```rst
.. code-block:: yaml

   # Brief description
   agents:
     - id: "agent_name"
       backend:
         type: "backend_type"  # claude, gemini, openai, etc.
         model: "model_name"
       system_message: "Agent role and instructions"
```

### Pattern 3: Link to README
```rst
For more information, see `README.md <https://github.com/Leezekun/MassGen/blob/main/README.md#section-anchor>`_

.. note::

   This section is derived from README.md. If README changes, update this documentation.
```

### Pattern 4: Link to Guide
```rst
For detailed information, see :doc:`../user_guide/guide_name`.
```

### Pattern 5: Version-Specific Feature
```rst
.. versionadded:: 0.0.29

   MCP Planning Mode allows agents to plan tool usage without execution during coordination.

See `v0.0.29 Release Notes <../../releases/v0.0.29/release-notes.md>`_ for details.
```

---

## What NOT to Document

### ❌ DO NOT Document These (They Don't Exist)

```python
# Fictional - DO NOT USE
from massgen import Agent, Orchestrator, load_config
from massgen.backends import OpenAIBackend, ClaudeBackend
from massgen.tools import WebSearch, Calculator

# None of these exist
agent = Agent(name="...", backend=...)
orchestrator = Orchestrator(agents=[...])
tool = WebSearch(api_key="...")
```

### ❌ DO NOT Show These Patterns

- Python class instantiation for agents
- Python class instantiation for backends
- Python class instantiation for tools
- Python imports from `massgen` module (except for API reference)
- Orchestration strategies as parameters (they're configured differently)
- Tool registration via Python (it's YAML or MCP)

---

## Rewrite Priority Guide

When rewriting documentation:

### Priority 1: Show Working Examples
- Real CLI commands
- Real YAML from massgen/configs/
- Test before documenting

### Priority 2: Link to Sources
- README.md (primary)
- Release notes (features)
- Real config files (examples)

### Priority 3: Keep It Simple
- Start with simplest case
- Build complexity gradually
- Link to advanced guides

### Priority 4: Verify Accuracy
- Cross-check with README
- Test all commands
- Validate all YAML
- Check against releases

---

## File Naming Conventions

When creating new docs:

### Good Names (Descriptive)
- `backend_configuration.rst` (not backends.rst)
- `tools_and_capabilities.rst` (not tools.rst)
- `advanced_features.rst` (not advanced_usage.rst)
- `mcp_examples.rst` (specific)
- `ag2_examples.rst` (specific)

### Section Organization
```
quickstart/     - Getting started guides
user_guide/     - How-to guides for users
reference/      - Reference documentation
examples/       - Working examples
api/            - Auto-generated API docs
development/    - For contributors
```

---

## Quick Commands Reference

### Build Documentation
```bash
cd /Users/ncrispin/GitHubProjects/MassGen/docs
make clean
make html
open build/html/index.html
```

### Test MassGen Commands
```bash
cd /Users/ncrispin/GitHubProjects/MassGen

# Test single agent
uv run python -m massgen.cli --model gemini-2.5-flash "Test question"

# Test multi-agent
massgen --config @examples/basic/multi/three_agents_default \
  "Test question"

# Validate YAML
python -c "import yaml; yaml.safe_load(open('massgen/configs/path/to/config.yaml'))"
```

### Find Real Examples
```bash
# List all config files
find massgen/configs -name "*.yaml" -type f

# Search for specific feature
grep -r "mcp_servers" massgen/configs/
grep -r "planning_mode" massgen/configs/
```

---

## Common Questions

### Q: Can users import MassGen as a Python library?
**A:** No. MassGen is a CLI tool. Users run it via `uv run python -m massgen.cli`.

### Q: Where should I look for examples?
**A:**
1. README.md (primary source)
2. massgen/configs/ (real YAML files)
3. Release notes (new features)

### Q: What if README.md and docs contradict?
**A:** README.md is always correct. Update docs to match README.

### Q: How do I document a new backend?
**A:**
1. Check README.md backend table
2. Find example in massgen/configs/
3. Document YAML configuration (not Python class)
4. Link to BACKEND_CONFIGURATION.md

### Q: How do I document a new tool/feature?
**A:**
1. Check which release introduced it
2. Read release notes for that version
3. Find examples in massgen/configs/
4. Document CLI usage and YAML config
5. Link back to README.md and release notes

---

## Documentation Workflow

### Before Writing
1. Read relevant README.md section
2. Read release notes if version-specific
3. Find real config files in massgen/configs/
4. Test commands yourself

### While Writing
1. Use real CLI commands
2. Use real YAML from configs
3. Link to sources (README, guides)
4. Add version tags if needed

### After Writing
1. Test all commands
2. Validate all YAML
3. Check links
4. Build and review in browser
5. Cross-check with README

---

## Emergency Contact

**If you find contradictions:**
1. README.md is the source of truth
2. Update docs to match README
3. Document what you changed
4. Note the contradiction for review

**If you find missing features:**
1. Check README.md
2. Check latest release notes
3. Search massgen/configs/
4. Ask team if it's intentional

**If examples don't work:**
1. That's a critical bug
2. Fix the example
3. Test before publishing
4. Never publish untested examples

---

## Resources

### Essential Reading
- `/Users/ncrispin/GitHubProjects/MassGen/README.md`
- `/Users/ncrispin/GitHubProjects/MassGen/docs/releases/v0.0.29/release-notes.md`
- `/Users/ncrispin/GitHubProjects/MassGen/docs/releases/v0.0.28/release-notes.md`

### Essential Directories
- `/Users/ncrispin/GitHubProjects/MassGen/massgen/configs/` - Real examples
- `/Users/ncrispin/GitHubProjects/MassGen/docs/source/` - Documentation source

### Audit Documents
- `/Users/ncrispin/GitHubProjects/MassGen/docs/DOCUMENTATION_AUDIT_REPORT.md` - Full audit
- `/Users/ncrispin/GitHubProjects/MassGen/docs/DOCUMENTATION_AUDIT_SUMMARY.md` - Summary
- `/Users/ncrispin/GitHubProjects/MassGen/docs/DOCUMENTATION_FIX_PLAN.md` - Action plan

---

**Remember:** When in doubt, check README.md. If it's in README, it's real. If it's not, verify before documenting.

---

**Created:** October 8, 2025
**For:** Documentation team
**Status:** Living document - update as needed
