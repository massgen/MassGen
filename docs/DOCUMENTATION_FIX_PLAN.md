# MassGen Documentation Fix Plan

**Goal:** Replace fictional Python API documentation with accurate CLI+YAML documentation

**Timeline:** 1-2 weeks
**Effort:** ~11 hours total

---

## Phase 1: Immediate Triage (1 hour) - TODAY

### Add Deprecation Warnings

Add this warning to the top of each fictional file:

```rst
.. warning::

   ⚠️ **This documentation is outdated and being rewritten.**

   MassGen is a CLI tool with YAML configuration, not a Python library.
   The Python API examples shown below do not exist.

   **For accurate documentation, see:**

   - `README.md <https://github.com/Leezekun/MassGen/blob/main/README.md>`_ (Authoritative source)
   - :doc:`../quickstart/running-massgen` (CLI usage)
   - :doc:`../reference/yaml_schema` (Configuration)
```

**Files to update:**
- [ ] docs/source/quickstart/configuration.rst
- [ ] docs/source/user_guide/backends.rst
- [ ] docs/source/user_guide/tools.rst
- [ ] docs/source/user_guide/advanced_usage.rst
- [ ] docs/source/examples/basic_examples.rst
- [ ] docs/source/examples/advanced_patterns.rst
- [ ] docs/source/examples/case_studies.rst

### Update index.rst Navigation

Comment out broken links in index.rst toctree temporarily:

```rst
.. toctree::
   :maxdepth: 2
   :caption: User Guide

   user_guide/concepts
   user_guide/multi_turn_mode
   user_guide/mcp_integration
   user_guide/file_operations
   user_guide/project_integration
   user_guide/ag2_integration
   .. user_guide/backends (Under Revision)
   .. user_guide/tools (Under Revision)
   .. user_guide/advanced_usage (Under Revision)
```

---

## Phase 2: Rewrite Critical Path (4 hours) - THIS WEEK

### File 1: configuration.rst (1.5 hours)

**Delete:** All Python API examples
**Replace with:**

1. **Environment Variables**
   ```rst
   .. code-block:: bash

      # Copy from .env.example
      cp .env.example .env

      # Edit with your API keys
      OPENAI_API_KEY=sk-...
      ANTHROPIC_API_KEY=sk-ant-...
      GOOGLE_API_KEY=...
   ```

2. **YAML Configuration Structure**
   - Copy agent configuration from README.md
   - Show single agent vs multi-agent
   - Explain backend configuration
   - Show orchestrator configuration

3. **Real Examples**
   - Link to massgen/configs/basic/single/
   - Link to massgen/configs/basic/multi/
   - Show three_agents_default.yaml

4. **Configuration Parameters**
   - Link to reference/yaml_schema.rst
   - Table of top-level keys: agents, orchestrator, etc.

**Source:** README.md "Quick Start" → "Run MassGen" sections

### File 2: backends.rst → backend_configuration.rst (1.5 hours)

**Rename file:** backends.rst → backend_configuration.rst
**Delete:** All Python class examples
**Replace with:**

1. **Backend Overview**
   - Explain backend types (not classes)
   - Backends are configured in YAML
   - Each agent can have different backend

2. **Backend Types Table**
   - Copy table from README.md "Supported Models and Tools"
   - Add YAML type column

3. **Configuration Examples**
   - OpenAI backend YAML
   - Claude backend YAML
   - Gemini backend YAML
   - Grok backend YAML
   - Azure OpenAI YAML
   - AG2 backend YAML
   - LM Studio YAML

4. **Backend-Specific Features**
   - Link to README tools table
   - MCP support by backend
   - File operations by backend

5. **Advanced Backend Configuration**
   - Link to massgen/configs/BACKEND_CONFIGURATION.md
   - Temperature, max_tokens, etc.
   - API key configuration

**Sources:**
- README.md "Supported Models and Tools"
- massgen/configs/BACKEND_CONFIGURATION.md
- docs/releases/v0.0.28/release-notes.md (AG2)

### File 3: examples/basic_examples.rst (1 hour)

**Delete:** All fictional Python code
**Replace with:**

1. **Single Agent Examples**
   ```rst
   Quick Model Test
   ----------------

   .. code-block:: bash

      # Test any model without configuration
      uv run python -m massgen.cli --model claude-3-5-sonnet-latest "What is ML?"
      uv run python -m massgen.cli --model gemini-2.5-flash "Explain quantum computing"
   ```

2. **Multi-Agent Collaboration**
   ```rst
   Three Agents Working Together
   ------------------------------

   .. code-block:: bash

      massgen --config @examples/basic_multi_three_agents_default \
        "Analyze pros and cons of renewable energy"

   This uses:

   - Gemini 2.5 Flash - Fast research with web search
   - GPT-5 Nano - Advanced reasoning with code execution
   - Grok-3 Mini - Real-time information
   ```

3. **Configuration File Example**
   - Show three_agents_default.yaml
   - Explain each section
   - Link to yaml_schema.rst

4. **Interactive Mode**
   ```rst
   Multi-Turn Conversation
   -----------------------

   .. code-block:: bash

      # Start interactive mode (no question = chat mode)
      uv run python -m massgen.cli \
        --config massgen/configs/basic/multi/three_agents_default.yaml
   ```

**Source:** README.md "Quick Start" section

---

## Phase 3: Complete User Guide (3 hours) - WEEK 2

### File 4: tools.rst → tools_and_capabilities.rst (1 hour)

**Rename:** tools.rst → tools_and_capabilities.rst
**Delete:** All fictional tool classes
**Replace with:**

1. **Overview**
   - Tools are backend capabilities
   - Configured in YAML, not Python imports
   - Three categories: built-in, MCP, file operations

2. **Backend Built-in Tools**
   - Copy table from README.md
   - Show which backends support what
   - Link to supported_models.rst

3. **MCP Integration**
   - Brief overview
   - Link to user_guide/mcp_integration.rst
   - Show simple MCP example

4. **File Operations**
   - Brief overview
   - Link to user_guide/file_operations.rst
   - Show filesystem example

**Source:** README.md "Tools" table

### File 5: examples/mcp_examples.rst (NEW - 1 hour)

**Create new file**
**Content:**

1. **Basic MCP - Weather**
   - Copy from README.md
   - gpt5_nano_mcp_example.yaml
   - Explain YAML structure

2. **Multi-Server MCP**
   - multimcp_gemini.yaml example
   - Multiple tools in one agent
   - Tool filtering

3. **MCP Planning Mode (v0.0.29)**
   - five_agents_filesystem_mcp_planning_mode.yaml
   - Explain planning vs execution
   - Link to v0.0.29 release notes

4. **Available MCP Servers**
   - Link to MCP server documentation
   - Common servers (weather, search, filesystem)

**Sources:**
- README.md "Model Context Protocol" section
- docs/releases/v0.0.29/release-notes.md
- massgen/configs/tools/mcp/

### File 6: examples/ag2_examples.rst (NEW - 1 hour)

**Create new file**
**Content:**

1. **Single AG2 Agent**
   - ag2_single_agent.yaml
   - Explain AG2 configuration

2. **AG2 with Code Execution**
   - ag2_coder.yaml
   - Code execution configuration
   - LocalCommandLineCodeExecutor

3. **AG2 + MassGen Hybrid**
   - ag2_coder_case_study.yaml
   - Multi-framework collaboration
   - Use case examples

4. **AG2 Configuration Reference**
   - Link to v0.0.28 release notes
   - AG2 adapter documentation

**Sources:**
- docs/releases/v0.0.28/release-notes.md
- massgen/configs/ag2/
- README.md AG2 section

---

## Phase 4: Advanced & Navigation (2 hours) - WEEK 2

### File 7: advanced_usage.rst → advanced_features.rst (1 hour)

**Rename:** advanced_usage.rst → advanced_features.rst
**Delete:** All fictional features
**Replace with:**

1. **Multi-Turn Sessions**
   - Link to user_guide/multi_turn_mode.rst
   - Session persistence
   - .massgen/ directory structure

2. **MCP Planning Mode (v0.0.29)**
   - What is planning mode
   - When to use it
   - Configuration example
   - Link to v0.0.29 release notes

3. **Workspace Management**
   - Agent workspaces
   - Snapshots
   - Context sharing
   - Link to file_operations.rst

4. **Context Paths & Permissions**
   - Project integration
   - Read/write permissions
   - Link to project_integration.rst

5. **AG2 Framework Integration**
   - Multi-framework collaboration
   - Link to ag2_integration.rst

6. **Debug Mode**
   - --debug flag
   - Log location
   - Troubleshooting tips

**Sources:**
- docs/releases/v0.0.29/release-notes.md
- user_guide/multi_turn_mode.rst
- user_guide/file_operations.rst
- user_guide/project_integration.rst

### File 8: index.rst Navigation Cleanup (1 hour)

**Changes:**

1. **Uncomment revised files**
   - backend_configuration.rst
   - tools_and_capabilities.rst
   - advanced_features.rst

2. **Add new examples**
   - mcp_examples.rst
   - ag2_examples.rst

3. **Create Project Coordination section**
   ```rst
   .. toctree::
      :maxdepth: 1
      :hidden:
      :caption: Project Coordination (For Contributors)

      tracks/multimodal/index
      tracks/coding-agent/index
      tracks/memory/index
      decisions/index
      rfcs/index
   ```

4. **Update Documentation Sections grid**
   - Reflect new structure
   - Remove fictional files
   - Add new guides

---

## Phase 5: Verification & Polish (2 hours) - WEEK 2

### Verification Checklist

For each rewritten file:

- [ ] All CLI commands tested and work
- [ ] All YAML examples validated against real configs
- [ ] No Python import statements (except API reference)
- [ ] Links to README.md are accurate
- [ ] Cross-references work
- [ ] Matches README.md content
- [ ] Reflects v0.0.28 and v0.0.29 features
- [ ] No contradictions with other docs

### Build & Review

1. **Build Sphinx docs**
   ```bash
   cd docs
   make clean
   make html
   ```

2. **Review in browser**
   - Check all links
   - Verify navigation
   - Test search functionality

3. **Cross-reference with README**
   - Side-by-side comparison
   - Check for contradictions
   - Verify all features covered

### Polish

- [ ] Add "Source: README.md" comments
- [ ] Consistent formatting
- [ ] Clear section headings
- [ ] Helpful code-block captions
- [ ] Warning boxes where appropriate

---

## Success Metrics

Documentation is complete when:

1. ✅ User can install and run MassGen following docs alone
2. ✅ All examples copy-paste and work without modification
3. ✅ No fictional Python APIs remain
4. ✅ v0.0.29 features documented (planning mode, file safety)
5. ✅ v0.0.28 features documented (AG2 integration)
6. ✅ Navigation is clear and simple
7. ✅ README.md acknowledged as source of truth
8. ✅ Sphinx build has no warnings
9. ✅ All internal links work
10. ✅ Search finds relevant content

---

## File Checklist

### Phase 1: Triage ✅
- [ ] Add warnings to 7 files
- [ ] Update index.rst navigation

### Phase 2: Critical Path 🔴
- [ ] Rewrite: configuration.rst
- [ ] Rewrite: backends.rst → backend_configuration.rst
- [ ] Rewrite: basic_examples.rst

### Phase 3: User Guide 🟡
- [ ] Rewrite: tools.rst → tools_and_capabilities.rst
- [ ] Create: mcp_examples.rst
- [ ] Create: ag2_examples.rst

### Phase 4: Advanced 🟢
- [ ] Rewrite: advanced_usage.rst → advanced_features.rst
- [ ] Update: index.rst (final navigation)

### Phase 5: Verify ⚪
- [ ] Test all CLI commands
- [ ] Validate all YAML
- [ ] Build Sphinx docs
- [ ] Review in browser
- [ ] Final audit

---

## Resources Needed

### Reference Documents
- README.md (primary source)
- docs/releases/v0.0.28/release-notes.md
- docs/releases/v0.0.29/release-notes.md
- massgen/configs/BACKEND_CONFIGURATION.md

### Example Configurations
- massgen/configs/basic/single/
- massgen/configs/basic/multi/
- massgen/configs/tools/mcp/
- massgen/configs/tools/filesystem/
- massgen/configs/ag2/

### Existing Accurate Guides
- user_guide/multi_turn_mode.rst
- user_guide/file_operations.rst
- user_guide/project_integration.rst
- user_guide/ag2_integration.rst
- user_guide/mcp_integration.rst
- reference/yaml_schema.rst

---

## Notes

### Key Principles

1. **Show, Don't Tell**
   - Real CLI commands that work
   - Real YAML from massgen/configs/
   - Tested examples only

2. **README First**
   - Copy content from README.md
   - Add comments: "Source: README.md"
   - Link back to README sections

3. **Simplicity**
   - Start with simplest examples
   - Build complexity gradually
   - Link to detailed guides

4. **Accuracy**
   - Verify against codebase
   - Test every command
   - Validate every YAML

### Common Patterns

**CLI Example Format:**
```rst
.. code-block:: bash

   # Brief description
   uv run python -m massgen.cli \
     --config path/to/config.yaml \
     "Your question here"
```

**YAML Example Format:**
```rst
.. code-block:: yaml

   # Brief description
   agents:
     - id: "agent_name"
       backend:
         type: "backend_type"
         model: "model_name"
```

**Link Format:**
```rst
See :doc:`../user_guide/guide_name` for details.

For more information, see `README.md <https://github.com/Leezekun/MassGen/blob/main/README.md#section>`_
```

---

## Timeline Summary

- **Day 1 (Today):** Phase 1 - Add warnings
- **Days 2-3:** Phase 2 - Rewrite critical files
- **Days 4-5:** Phase 3 - Complete user guide
- **Days 6-7:** Phase 4 - Advanced features + navigation
- **Days 8-9:** Phase 5 - Verification + polish
- **Day 10:** Final review + publish

**Total:** ~10 days, 11 hours of focused work

---

**Created:** October 8, 2025
**Status:** Ready to execute
**Owner:** Documentation team
**Audit report:** `/Users/ncrispin/GitHubProjects/MassGen/docs/DOCUMENTATION_AUDIT_REPORT.md`
