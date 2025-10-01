# Release Example Configuration Checklist

This checklist guides the creation of example configurations for each MassGen release to showcase new features.

## Pre-Implementation Questions for User

Before creating examples, gather the following information:

### 1. Feature Information
- [ ] **What new features are being released?** (e.g., file deletion, protected paths, reasoning modes, new tools)
- [ ] **What is the design document location?** (e.g., `docs/dev_notes/feature_name.md`)
- [ ] **What is the GitHub issue number?** (e.g., #254)
- [ ] **What version is this for?** (e.g., v0.0.26)

### 2. Example Resource Paths (if applicable)
- [ ] **Does this feature need resource files to demonstrate?** (e.g., HTML files for filesystem features)
- [ ] **If yes, should we create a new resource directory?** (e.g., `massgen/configs/resources/v0.0.26-example`)
- [ ] **What should it contain?** (files to demonstrate the feature)
- [ ] **If no, can we use existing resources or is this feature standalone?** (e.g., reasoning features don't need files)
- [ ] **Does the source directory exist, or should we copy from elsewhere?** (e.g., copy from `../testing_new_copy`)

### 3. Agent Configuration
- [ ] **Which agent models should be used?**
  - Check existing configs in `massgen/configs/basic/multi/` for current model naming
  - Common combinations: `gemini-2.5-flash` + `gpt-5-nano`, two `gemini-2.5-flash`, etc.
- [ ] **Is the new feature model-specific?** (e.g., reasoning only for certain models)
- [ ] **Should agents have reasoning/thinking enabled?** (for models like `gpt-5-nano`)
- [ ] **How many agents?** (typically 2 for examples)
- [ ] **What should agent IDs be?** (use `agent_a`, `agent_b` convention)
- [ ] **Should each agent have separate workspaces?** (typically yes: `workspace1`, `workspace2`)

### 4. Example Scenarios
- [ ] **How many examples should we create?** (aim for 2-3 per major feature)
- [ ] **What use case does each example demonstrate?** (be specific)
- [ ] **What should the example prompts be?** (should clearly trigger the new feature)
- [ ] **Are there any specific constraints or edge cases to highlight?** (e.g., permission boundaries)
- [ ] **What category does this belong to?** (filesystem, web-search, code-execution, mcp, etc.)

## Implementation Checklist

### Phase 1: Resource Preparation (if needed)

- [ ] **Create/identify resource directory** (skip if feature doesn't need files)
  ```bash
  # Example: Copy from external directory
  cp -r ../testing_new_copy massgen/configs/resources/v0.0.26-example

  # Example: Verify contents
  ls -la massgen/configs/resources/v0.0.26-example/
  ```

- [ ] **Document what's in the resource directory** (for example descriptions)
  - List all files/directories
  - Note what makes it especially important for the example

### Phase 2: Config File Creation

For each example configuration:

- [ ] **Follow naming convention**: `{agent1}_{agent2}_{feature}.yaml`
  - Examples: `gemini_gpt5nano_protected_paths.yaml`, `gemini_gemini_workspace_cleanup.yaml`
  - Place in appropriate subdirectory: `massgen/configs/tools/{category}/`
  - Categories: `filesystem/`, `web-search/`, `code-execution/`, `mcp/`, etc.

- [ ] **Header comment structure**:
  ```yaml
  # Example Configuration: {Feature Name}
  #
  # Use Case: {One sentence description}
  #
  # {2-3 sentences explaining what this demonstrates}
  #
  # Run with:
  #   uv run python -m massgen.cli --config {full/path/to/config.yaml} "{example prompt}"
  ```

- [ ] **Agent configuration**:
  ```yaml
  agents:
    - id: "agent_a"
      backend:
        type: "gemini"  # or "openai", "claude"
        model: "gemini-2.5-flash"  # Use current model names
      filesystem:
        cwd: "workspace1"  # Include if feature uses filesystem

    - id: "agent_b"
      backend:
        type: "openai"
        model: "gpt-5-nano"
        text:
          verbosity: "medium"  # Include for reasoning models
        reasoning:
          effort: "medium"     # Feature-specific configuration
          summary: "auto"
      filesystem:
        cwd: "workspace2"
  ```

- [ ] **Feature-specific configuration** (adapt to your feature):
  ```yaml
  # Example 1: Filesystem features
  filesystem:
    context_paths:
      - path: "massgen/configs/resources/v0.0.26-example"
        permission: "write"
        protected_paths:     # if applicable
          - "file.txt"

  # Example 2: Web search features (no extra config needed usually)

  # Example 3: Code execution features
  # (may need sandbox settings, etc.)
  ```

- [ ] **UI configuration**:
  ```yaml
  ui:
    display_type: "rich_terminal"
    logging_enabled: true
  ```

- [ ] **Footer comments** (adapt based on what's relevant for the feature):
  ```yaml
  # What happens:
  # 1. {Step 1}
  # 2. {Step 2}
  # 3. {Step 3}
  #
  # Available tools (if introducing new tools):
  # - {tool_name}({args}) - {description}
  #
  # Feature behavior (if complex edge cases):
  # - ✅ {what's enabled/allowed}
  # - ❌ {what's disabled/blocked}
  ```

### Phase 3: Design Document Updates

- [ ] **Add "Quick Start Examples" section at the top** (after Overview, before Motivation)

For each example:

- [ ] **Follow this template** (adapt sections based on feature):
  ```markdown
  ### Example {N}: {Feature Name}
  **Use Case**: {One sentence description}

  **Config**: [`{relative/path/to/config.yaml}`](../../{path/to/config.yaml})

  **Command**:
  ```bash
  uv run python -m massgen.cli --config {path} "{prompt}"
  ```

  **What happens**: (use this OR "Result" section below, depending on feature)
  1. {Step 1 - what the agents do}
  2. {Step 2}
  3. {Step 3}

  **Result**: (use for features with specific permission/access patterns)
  - ✅ `{path/behavior}` → {what's allowed/enabled}
  - ❌ `{path/behavior}` → {what's blocked/disabled}

  **Available Tools**: (if introducing new tools)
  - `{tool_name}({args})` - {description}

  ---
  ```

- [ ] **Choose appropriate sections for your feature**:
  - Use **"What happens"** for workflow-based features (e.g., multi-agent coordination, reasoning)
  - Use **"Result"** for permission/constraint-based features (e.g., filesystem access, protected paths)
  - Use **"Available Tools"** when introducing new MCP tools or capabilities
  - Omit sections that don't apply to your feature

- [ ] **Verify all paths are correct** (both in markdown links and commands)
- [ ] **Ensure prompts match between config file and design doc**

### Phase 4: Verification

- [ ] **Check config file naming follows convention**
  - Pattern: `{agent1}_{agent2}_{feature}.yaml`
  - Located in: `massgen/configs/tools/{category}/`

- [ ] **Verify all paths exist** (if using resource files):
  ```bash
  # Check resource directories
  ls massgen/configs/resources/v0.0.26-example/

  # Check config files
  ls massgen/configs/tools/{category}/{new_config}.yaml
  ```

- [ ] **Test-run the config** (optional but recommended):
  ```bash
  uv run python -m massgen.cli --config {path} "{prompt}"
  ```

- [ ] **Verify design doc links work** (relative paths from `docs/dev_notes/`)

- [ ] **Check for consistency**:
  - Prompts match in config comments and design doc
  - Agent models are current (not deprecated)
  - All file paths use forward slashes or are OS-agnostic
  - Windows examples included where relevant (for filesystem features)

### Phase 5: Final Polish

- [ ] **Ensure examples are ordered logically** (simple → complex, or by feature aspect)

- [ ] **Add cross-platform examples** (Unix/macOS and Windows paths where relevant for filesystem)

- [ ] **Verify all TODOs/placeholders are filled**

- [ ] **Check markdown formatting** (proper code blocks, bullet points)

- [ ] **Review for clarity** (can someone unfamiliar with the feature understand it?)

- [ ] **Remove sections that don't apply** (e.g., "Result" section if feature isn't about permissions)

## Example Structure Summary

```
massgen/
├── configs/
│   ├── resources/
│   │   └── v0.0.26-example/        # Resource files (if needed)
│   │       ├── file1.html
│   │       └── file2.css
│   └── tools/
│       ├── filesystem/              # Category-specific configs
│       │   ├── gemini_gpt5nano_feature1.yaml
│       │   └── gemini_gemini_feature2.yaml
│       ├── web-search/
│       │   └── gemini_gpt5_web_search_example.yaml
│       └── code-execution/
│           └── claude_gpt5_code_exec_example.yaml
└── docs/
    └── dev_notes/
        └── feature_design.md        # Design doc with Quick Start Examples at top
```

## Common Pitfalls to Avoid

- ❌ **Don't** use `massgen/configs/examples/` (use category-specific dirs like `tools/filesystem/`)
- ❌ **Don't** use generic names like `example1.yaml` (use descriptive names with agent info)
- ❌ **Don't** forget to update both config file AND design doc
- ❌ **Don't** use outdated model names (check existing configs first)
- ❌ **Don't** forget `filesystem.cwd` for each agent (if feature uses filesystem, else do not include)
- ❌ **Don't** use absolute paths in configs (use relative to repo root)
- ❌ **Don't** forget to include reasoning config for models like `gpt-5-nano`
- ❌ **Don't** create resource directories outside the repo (use `massgen/configs/resources/`)
- ❌ **Don't** include irrelevant sections (e.g., "Result" section for non-permission features)

## Questions to Ask If Unclear

1. **Agent Selection**: "Which models should I use? Should I check `massgen/configs/basic/multi/` for current conventions?"

2. **Resource Location**: "Does this feature need resource files to demonstrate? If yes, should I create a new resource directory for v{X.Y.Z}, or reuse an existing one?"

3. **Feature Scope**: "This feature has multiple aspects. Should I create one example that shows everything, or separate examples for each aspect?"

4. **Prompt Complexity**: "Should the example prompt be simple and direct, or showcase a complex multi-step workflow?"

5. **Edge Cases**: "Are there any specific edge cases or limitations I should highlight in the example?"

6. **Platform Support**: "Should I include Windows-specific examples, or is Unix/macOS sufficient?" (mainly for filesystem features)

7. **Category Placement**: "Which tools category does this feature belong to? (filesystem, web-search, code-execution, mcp, etc.)"

8. **Example Sections**: "What sections should I include in the design doc example? (What happens, Result, Available Tools, or something else?)"

9. **Backward Compatibility**: "Does this example work with previous versions, or is it version-specific?"

## Template Files

### Minimal Config Template
```yaml
# Example Configuration: {Feature Name}
#
# Use Case: {Description}
#
# Run with:
#   uv run python -m massgen.cli --config {path} "{prompt}"

agents:
  - id: "agent_a"
    backend:
      type: "gemini"
      model: "gemini-2.5-flash"
    filesystem:  # Include if feature uses filesystem
      cwd: "workspace1"

  - id: "agent_b"
    backend:
      type: "openai"
      model: "gpt-5-nano"
      text:
        verbosity: "medium"
      reasoning:
        effort: "medium"
        summary: "auto"
    filesystem:  # Include if feature uses filesystem
      cwd: "workspace2"

# Feature-specific configuration (adapt as needed)
filesystem:
  context_paths:
    - path: "massgen/configs/resources/v0.0.X-example"
      permission: "write"

ui:
  display_type: "rich_terminal"
  logging_enabled: true

# What happens:
# 1. {Step 1}
# 2. {Step 2}
```

### Design Doc Example Section Template (Flexible)
```markdown
### Example {N}: {Feature Name}
**Use Case**: {One sentence}

**Config**: [`path/to/config.yaml`](../../path/to/config.yaml)

**Command**:
```bash
uv run python -m massgen.cli --config path/to/config.yaml "prompt"
```

<!-- Choose ONE of the following based on your feature -->

<!-- Option A: For workflow features -->
**What happens**:
1. Step 1
2. Step 2
3. Step 3

<!-- Option B: For permission/constraint features -->
**Result**:
- ✅ What's allowed
- ❌ What's blocked

<!-- Option C: For tool introduction -->
**Available Tools**:
- `tool_name(args)` - description

---
```

## Version History Reference

**Note**: This section shows an example of how to document what was created for a release. Use this as a reference when creating examples for new releases.

### Example Entry (v0.0.26)
- **v0.0.26** (Issue #254): File deletion, protected paths, file context paths
  - Created configs: `gemini_gpt5nano_protected_paths.yaml`, `gemini_gpt5nano_file_context_path.yaml`, `gemini_gemini_workspace_cleanup.yaml`
  - Category: `tools/filesystem/`
  - Resource dir: `v0.0.26-example` (copied from `../testing_new_copy`)
  - Design doc: `docs/dev_notes/file_deletion_and_context_files.md`
  - Example sections used: "What happens", "Result", "Available Tools"

**When creating examples for a new release**, add a similar entry documenting what you created.
