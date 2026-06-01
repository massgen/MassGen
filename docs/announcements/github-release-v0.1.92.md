# 🚀 Release Highlights — v0.1.92 (2026-06-01)

v0.1.92 is a maintainability release for MassGen's orchestration core, with a new Parallel Web Search MCP example included for research-heavy workflows. The main result: the largest orchestrator surfaces are smaller, more modular, and guarded by characterization tests before deeper behavior changes continue.

### 🧩 Orchestrator Collaborator Extraction
- `orchestrator.py` drops from 21,599 to 8,574 lines
- 49 collaborator classes are extracted into `massgen/orchestrator_collaborators/`
- Existing public methods remain available through thin delegators
- Shared mutable state still lives on the orchestrator, preserving current ownership semantics

### 🖥️ TUI Display Module Cleanup
- Provider/model display logic moved to `_textual_provider_model.py`
- Terminal capability probing moved to `_textual_terminal_capabilities.py`
- Widget debug helpers moved to `_textual_widget_debug.py`
- Public imports from `textual_terminal_display.py` stay stable

### 🔎 Parallel Web Search MCP
- New `parallel_search` MCP registry entry
- New example config: `massgen/configs/tools/web-search/parallel_search_example.yaml`
- Supports Parallel's hosted Search MCP server for LLM-optimized web search and URL extraction
- Optional `PARALLEL_API_KEY` enables higher rate limits

### 🧪 Characterization Coverage
- `massgen/tests/test_orchestrator_characterization.py`
- `massgen/tests/frontend/test_textual_terminal_display_characterization.py`
- Existing integration/unit tests updated for the new collaborator seams
- Refactor roadmap and remaining high-risk follow-up steps documented in `docs/dev_notes/orchestrator_refactor_roadmap.md`

---

### 📖 Getting Started
- [**Quick Start Guide**](https://github.com/massgen/MassGen?tab=readme-ov-file#1--installation)
- **Install**:
  ```bash
  pip install massgen==0.1.92
  ```
- **Try Parallel Search**:
  ```bash
  uv run massgen --config massgen/configs/tools/web-search/parallel_search_example.yaml "Research the latest advances in multi-agent AI systems"
  ```
