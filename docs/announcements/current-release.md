# MassGen v0.1.93 Release Announcement

<!--
This is the current release announcement. Copy this + feature-highlights.md to LinkedIn/X.
After posting, update the social links below.
-->

## Release Summary

MassGen v0.1.93 — CLI Package Decomposition & Pydantic Config Migration — is an internal-quality release with no intended runtime behavior changes. It breaks the 12k-line CLI module into a focused `massgen/cli/` package, adds construction-time validation to core config dataclasses, consolidates duplicated provider-exclusion lists, removes dead legacy code from the wheel, and tightens CI/type-checking so future changes fail earlier and with clearer signals.

## Install

```bash
pip install massgen==0.1.93
```

## Links

- **Release notes:** https://github.com/massgen/MassGen/releases/tag/v0.1.93
- **X post:** [TO BE ADDED AFTER POSTING]
- **LinkedIn post:** [TO BE ADDED AFTER POSTING]

## Posting Notes

- **Suggested image:** Use a screenshot of the v0.1.93 release notes.

---

## Full Announcement (for LinkedIn)

Copy everything below this line, then append content from `feature-highlights.md`:

---

MassGen v0.1.93 — CLI Package Decomposition & Pydantic Config Migration — is an internal-quality release with no intended runtime behavior changes. It breaks the 12k-line CLI module into a focused `massgen/cli/` package, adds construction-time validation to core config dataclasses, consolidates duplicated provider-exclusion lists, removes dead legacy code from the wheel, and tightens CI/type-checking so future changes fail earlier and with clearer signals.

**Key Improvements:**

🧩 **CLI Package Decomposition**:
- `massgen/cli.py` was split into an 18-module `massgen/cli/` package
- The facade keeps `from massgen.cli import ...` and `massgen.cli...` imports working
- The Textual per-turn handler was extracted into a dependency-injected function

🛡️ **Pydantic Config Validation**:
- Core config classes now validate field types on construction
- Mode fields use `Literal` types in `massgen/config_modes.py`
- `config_validator` derives valid mode sets from those typed definitions instead of maintaining drift-prone duplicates

🔧 **Correctness Fixes**:
- Concurrent in-process Textual runs keep their own logging/snapshot session
- `CoordinationConfig.from_dict()` now drops absent `None` values so field defaults apply
- Response backend tool-argument parsing now logs malformed payloads instead of silently converting them to `{}`

🧪 **Test Signal & Typing**:
- Coverage config now points at the real package
- No-assert pytest returns are treated as errors
- CI enforces `uv.lock` with `uv sync --frozen`
- An incremental mypy island runs as a blocking pre-commit/CI gate

🧹 **Dead Code Removal**:
- Removed unreferenced legacy `massgen/v1` and `massgen/prototype` code from the shipped wheel

**Install:**

```bash
pip install massgen==0.1.93
```

Release notes: https://github.com/massgen/MassGen/releases/tag/v0.1.93

Feature highlights:

<!-- Paste feature-highlights.md content here -->
