# 🚀 Release Highlights — v0.1.93 (2026-06-03)

v0.1.93 is an internal-quality release: no intended runtime behavior changes, but a smaller CLI surface, typed config validation, cleaner package contents, and stronger test/type-checking gates.

### 🧩 CLI Package Decomposition
- `massgen/cli.py` was split into an 18-module `massgen/cli/` package
- The public import surface is preserved through the package facade
- The Textual per-turn handler was extracted into a dependency-injected function
- CLI helper and run-loop characterization tests cover the new seams

### 🛡️ Pydantic Config Migration
- `AgentConfig`, `CoordinationConfig`, `TimeoutConfig`, `StepModeConfig`, and related nested config classes now validate field types on construction
- Mode fields use `Literal` definitions in `massgen/config_modes.py`
- `config_validator` derives valid mode sets from the typed definitions, reducing validator drift
- `pydantic>=2.0` is now a declared dependency

### 🔧 Correctness Fixes
- Textual concurrent-run logging now preserves per-run session context
- `CoordinationConfig.from_dict()` no longer lets absent YAML keys override defaults with `None`
- Response backend tool-argument parsing now logs malformed payloads instead of silently dropping them
- Backend/API parameter exclusion lists now derive from a single source

### 🧪 Test Signal & Typing
- Coverage configuration now points at the real package
- `pytest.PytestReturnNotNoneWarning` is treated as an error
- CI enforces `uv.lock` via `uv sync --frozen`
- `scripts/mypy_island.sh` adds a blocking incremental mypy gate
- All bundled configs were validated after the migration

### 🧹 Dead Code Removal
- Removed unreferenced legacy `massgen/v1` and `massgen/prototype` code from the wheel

---

### 📖 Install
```bash
pip install massgen==0.1.93
```
