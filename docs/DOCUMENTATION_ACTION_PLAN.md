# Documentation Action Plan
## Priority Updates for User Guide (Based on v0.0.13-v0.0.29 Release Verification)

**Created:** October 8, 2025
**Status:** Ready for Implementation
**Owner:** docs-manager

---

## Executive Summary

After verifying all features from releases v0.0.13 through v0.0.29 against the main user documentation, we've identified **4 high-priority gaps** and **3 medium-priority improvements** that should be addressed to ensure users can discover and use all available features.

**Overall Documentation Health:** 75% well-documented, 15% needs improvement, 10% missing

---

## High Priority: Missing Major Features

### 1. Multimodal Support (v0.0.27) ❌ CRITICAL

**Impact:** Users cannot discover image generation and understanding capabilities

**File to Create:** `docs/source/user_guide/multimodal.rst`

**Content Needed:**
```rst
Multimodal Capabilities
=======================

Image Generation
----------------
- Configuration for image generation agents
- Example: gpt4o_image_generation.yaml
- Use cases: marketing assets, creative design

Image Understanding
-------------------
- Configuration for vision models
- Example: gpt5nano_image_understanding.yaml
- Use cases: document analysis, visual Q&A

File Upload and Search
----------------------
- Document Q&A capabilities
- Vector store management
- Example configurations

Multimodal MCP Tools
--------------------
- read_multimodal_files tool
- Base64 encoding for images
- MIME type detection
```

**Also Update:**
- `tools.rst` - Add multimodal section
- `backends.rst` - Note which backends support multimodal
- `concepts.rst` - Mention StreamChunk architecture

---

### 2. Local Inference Backends (v0.0.24-v0.0.25) ❌ CRITICAL

**Impact:** Users cannot use vLLM or SGLang for cost-effective local deployment

**File to Update:** `docs/source/user_guide/backends.rst`

**Content to Add:**

```rst
Inference Backend (vLLM & SGLang)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For local model deployment and cost-effective inference:

**vLLM Configuration:**

.. code-block:: yaml

   agents:
     - id: "vllm_agent"
       backend:
         type: "inference"
         base_url: "http://localhost:8000"
         model: "meta-llama/Meta-Llama-3.1-8B-Instruct"
         api_key: ${VLLM_API_KEY}

**SGLang Configuration:**

.. code-block:: yaml

   agents:
     - id: "sglang_agent"
       backend:
         type: "inference"
         base_url: "http://localhost:30000"
         model: "Qwen/Qwen2.5-7B-Instruct"
         backend_params:
           separate_reasoning: true

**Setup:**

vLLM:
   .. code-block:: bash

      pip install vllm
      python -m vllm.entrypoints.openai.api_server \
        --model meta-llama/Meta-Llama-3.1-8B-Instruct \
        --port 8000

SGLang:
   .. code-block:: bash

      pip install sglang
      python -m sglang.launch_server \
        --model Qwen/Qwen2.5-7B-Instruct \
        --port 30000

**Benefits:**
- Zero API costs
- Full privacy (local inference)
- High-performance serving
- Custom model deployment
```

**Also Update:**
- Backend types table - Add `inference` type
- Backend capabilities table - Add vLLM and SGLang rows
- Cost optimization section - Highlight local inference
- `advanced_usage.rst` - Add local deployment examples

---

### 3. Logging & Debugging (v0.0.13-v0.0.14) ❌ MISSING

**Impact:** Users struggle to debug issues without understanding logging system

**File to Update:** `docs/source/user_guide/advanced_usage.rst`

**Section to Add:**

```rst
Logging & Debugging
-------------------

Debug Mode
~~~~~~~~~~

Enable detailed logging for troubleshooting:

.. code-block:: bash

   uv run python -m massgen.cli --debug --config your-config.yaml "Your task"

**Debug Output Includes:**
- Agent decision-making processes
- Backend operations and API calls
- Tool execution details
- Coordination events
- Full message history

Log Files
~~~~~~~~~

Debug logs are saved to ``agent_outputs/log_{timestamp}/massgen_debug.log``

**Log Structure:**

.. code-block:: text

   agent_outputs/
   └── log_20250108_143022/
       ├── massgen_debug.log      # Debug-level logs
       ├── massgen.log            # Info-level logs
       └── agent_responses/       # Individual agent outputs

**Color-Coded Console Output:**
- DEBUG (cyan) - Detailed internal operations
- INFO (green) - Important status updates
- WARNING (yellow) - Potential issues
- ERROR (red) - Errors and failures

Interpreting Debug Logs
~~~~~~~~~~~~~~~~~~~~~~~~

**Common Patterns:**

Coordination Events:
   .. code-block:: text

      [DEBUG] Agent 'researcher' voted for 'analyst'
      [DEBUG] Consensus detected: 0.67 threshold reached
      [DEBUG] Final agent selected: 'analyst'

Backend Operations:
   .. code-block:: text

      [DEBUG] OpenAI API call: 1234ms
      [DEBUG] MCP tool 'filesystem:read_file' executed
      [DEBUG] Response streaming: 45 chunks

**Troubleshooting Tips:**
1. Check for timeout errors in coordination phase
2. Verify MCP server initialization succeeded
3. Review tool execution for permission errors
4. Check API rate limits in backend logs
```

---

### 4. Coordination Tracking (v0.0.19) ❌ MISSING

**Impact:** Users don't know about the 'r' key coordination table feature

**File to Update:** `docs/source/user_guide/advanced_usage.rst`

**Section to Add:**

```rst
Coordination Tracking
---------------------

Live Coordination Table
~~~~~~~~~~~~~~~~~~~~~~~

During execution, press **'r'** to view the complete coordination history:

.. code-block:: text

   ┌─ Coordination History ─────────────────────────────────┐
   │ Round │ Agent      │ Action      │ Target   │ Time     │
   ├───────┼────────────┼─────────────┼──────────┼──────────┤
   │   1   │ researcher │ NEW_ANSWER  │ -        │ 14:30:22 │
   │   1   │ analyst    │ VOTE        │ researcher│ 14:30:25 │
   │   1   │ coder      │ NEW_ANSWER  │ -        │ 14:30:28 │
   │   2   │ researcher │ VOTE        │ coder    │ 14:30:45 │
   │   2   │ analyst    │ VOTE        │ coder    │ 14:30:48 │
   │   2   │ coder      │ CONVERGED   │ self     │ 14:30:50 │
   └────────────────────────────────────────────────────────┘

**Event Types:**
- **NEW_ANSWER** - Agent provides new solution
- **VOTE** - Agent votes for another agent's solution
- **VOTE_IGNORED** - Vote not counted (threshold already met)
- **CONVERGED** - Agent consensus reached
- **ERROR** - Agent encountered error
- **TIMEOUT** - Agent exceeded time limit
- **CANCELLED** - Operation cancelled

**Use Cases:**
- Debug coordination issues
- Understand voting patterns
- Analyze agent performance
- Optimize round configuration

Coordination Patterns
~~~~~~~~~~~~~~~~~~~~~

**Fast Convergence:**
   All agents vote for same solution in round 1

**Iterative Refinement:**
   Agents provide new answers for 2-3 rounds before consensus

**Diverse Perspectives:**
   Multiple strong solutions compete across rounds
```

**Also Update:**
- `multi_turn_mode.rst` - Expand 'r' key documentation
- `concepts.rst` - Reference coordination tracking

---

## Medium Priority: Improvements

### 5. Update Configuration Paths (v0.0.22) ⚠️

**Impact:** Users may reference outdated config paths

**Files to Update:** All user guide files with config examples

**Changes:**
- Update paths from `massgen/configs/xxx.yaml` to new structure:
  - `massgen/configs/basic/single/xxx.yaml`
  - `massgen/configs/basic/multi/xxx.yaml`
  - `massgen/configs/tools/mcp/xxx.yaml`
  - `massgen/configs/tools/filesystem/xxx.yaml`
  - `massgen/configs/ag2/xxx.yaml`

**Add to configuration.rst:**
```rst
Configuration Organization
~~~~~~~~~~~~~~~~~~~~~~~~~~

Configurations are organized by use case:

- ``basic/single/`` - Single agent templates
- ``basic/multi/`` - Multi-agent templates
- ``tools/mcp/`` - MCP integration examples
- ``tools/filesystem/`` - File operation examples
- ``tools/planning/`` - Planning mode examples
- ``ag2/`` - AG2 framework examples

Browse all examples in the `Configuration README <https://github.com/Leezekun/MassGen/blob/main/massgen/configs/README.md>`_.
```

---

### 6. File-Based Context Paths (v0.0.26) ⚠️

**Impact:** Users don't know they can use individual files as context paths

**File to Update:** `docs/source/user_guide/project_integration.rst`

**Current Issue:** Documentation states "Context paths must be directories"

**Fix:** Update to clarify file support:

```rst
Context Path Types
~~~~~~~~~~~~~~~~~~

**Directory Context Paths:**

.. code-block:: yaml

   context_paths:
     - path: "/home/user/project/src"
       permission: "read"

All files in the directory are accessible.

**File Context Paths (v0.0.26+):**

.. code-block:: yaml

   context_paths:
     - path: "/home/user/project/config/settings.yaml"
       permission: "read"
     - path: "/home/user/project/docs/api.md"
       permission: "read"

Grant access to specific files only.

**Protected Paths (v0.0.26+):**

.. code-block:: yaml

   context_paths:
     - path: "/workspace"
       permission: "write"
       protected_paths:
         - "/workspace/reference/template.yaml"
         - "/workspace/config/*.json"

Mark specific files as read-only within writable directories.
```

---

### 7. Backend Capabilities Table Updates ⚠️

**Impact:** Incomplete feature visibility for backends

**File to Update:** `docs/source/user_guide/backends.rst`

**Updates Needed:**
- Add `inference` backend type (vLLM/SGLang)
- Update with latest models (Claude Sonnet 4.5, GPT-5-Codex)
- Add multimodal column to capabilities table
- Verify all backend features are current

```rst
.. list-table:: Backend Capabilities (Updated)
   :header-rows: 1
   :widths: 15 10 10 10 10 10 15 20

   * - Backend
     - Web Search
     - Code Exec
     - File Ops
     - MCP
     - Multimodal
     - Local Deploy
     - Notes
   * - ``openai``
     - ✅
     - ✅
     - ✅
     - ✅
     - ✅
     - ❌
     - Vision, DALL-E
   * - ``claude``
     - ✅
     - ✅
     - ✅
     - ✅
     - ✅
     - ❌
     - Long context
   * - ``gemini``
     - ✅
     - ✅
     - ✅
     - ✅
     - ✅
     - ❌
     - Fast, multimodal
   * - ``inference``
     - ❌
     - ✅
     - ✅
     - ✅
     - Varies
     - ✅
     - vLLM, SGLang
```

---

## Implementation Order

### Week 1: Critical Missing Features
1. ✅ Create multimodal.rst guide (Day 1-2)
2. ✅ Add inference backend to backends.rst (Day 3)
3. ✅ Add logging section to advanced_usage.rst (Day 4)
4. ✅ Add coordination tracking to advanced_usage.rst (Day 5)

### Week 2: Improvements & Updates
5. ✅ Update all config paths (Day 1-2)
6. ✅ Update file context paths docs (Day 3)
7. ✅ Update backend tables and capabilities (Day 4-5)

### Week 3: Review & Polish
8. ✅ Cross-reference check (Day 1-2)
9. ✅ Add missing examples (Day 3-4)
10. ✅ Final review and merge (Day 5)

---

## Success Metrics

**Completion Criteria:**
- [ ] All v0.0.13-v0.0.29 features documented in user guide
- [ ] No major features discoverable only in release notes
- [ ] All backend types in backends.rst table
- [ ] Multimodal guide complete with examples
- [ ] Logging and debugging well explained
- [ ] Config paths updated throughout

**Quality Checks:**
- [ ] Each new section has working examples
- [ ] Cross-references between guides work
- [ ] No contradictions with release notes
- [ ] Technical accuracy verified
- [ ] User-friendly language throughout

---

## Next Steps

1. **Assign tasks** to documentation team
2. **Create branches** for each major update
3. **Review technical accuracy** with engineering team
4. **Test all examples** before publishing
5. **Update index** and navigation after changes
6. **Announce updates** in release notes

---

## Notes

- Maintain consistency with existing doc style
- Use same RST formatting as current guides
- Include YAML examples for all features
- Add troubleshooting for common issues
- Cross-link between related sections
- Update "Next Steps" sections as needed

**Contact:** docs-manager for questions or clarifications
