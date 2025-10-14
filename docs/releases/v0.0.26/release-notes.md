# MassGen v0.0.26 Release Notes

**Release Date:** October 2, 2025

---

## Overview

Version 0.0.26 introduces **File Deletion and Context File Management**, providing agents with safe file deletion capabilities and fine-grained access control. This release adds workspace cleanup tools, file-based context paths, and protected paths to prevent accidental modification of reference files.

Additionally, v0.0.26 includes major code refactoring that improves module structure and simplifies import paths across the codebase.

---

## What's New

### File Deletion and Workspace Management

The headline feature of v0.0.26 is **File Deletion** and enhanced workspace management through new MCP tools.

**New MCP Tools:**
- **delete_file:** Delete a single file from workspace
- **delete_files_batch:** Delete multiple files in a single operation
- **compare_directories:** Compare two directories and show differences
- **compare_files:** Compare two files and show differences

**Key Capabilities:**
- Safe file deletion with permission checks
- Batch operations for efficiency
- Directory and file comparison for verification
- Improved workspace cleanup for multi-turn sessions

**Implementation:**
- New consolidated `_workspace_tools_server.py` replacing previous `_workspace_copy_server.py`
- Integration with permission system for safe deletions
- Proper error handling and validation
- Test coverage for all workspace operations

**Try It Out:**
```bash
# Workspace cleanup example
massgen --config @examples/gemini_gemini_workspace_cleanup \
  "Clean up temporary files and organize the workspace"
```

**Use Cases:**
- Clean up temporary files after processing
- Remove outdated files during multi-turn sessions
- Organize workspace by deleting unnecessary files
- Batch cleanup operations

---

### File-Based Context Paths

New support for single file access without exposing entire directories.

**Key Features:**
- **Individual File Access:** Context paths can now be single files, not just directories
- **Fine-Grained Control:** Grant access to specific reference files only
- **Better Security:** Limit agent access to only necessary files
- **Enhanced Validation:** Path validation distinguishes between file and directory contexts

**Configuration Example:**
```yaml
orchestrator:
  context_paths:
    - path: "/path/to/specific/config.yaml"
      permission: READ
    - path: "/path/to/reference/data.json"
      permission: READ
```

**Try It Out:**
```bash
# File context path example
massgen --config @examples/gemini_gpt5nano_file_context_path \
  "Read the configuration and suggest improvements"
```

**Benefits:**
- More precise access control
- Reduced risk of unintended file access
- Better alignment with principle of least privilege
- Clearer agent permissions

---

### Protected Paths Feature

Prevent agents from modifying specific reference files.

**Key Capabilities:**
- **Protected Within Write-Permitted Paths:** Mark specific files as read-only within writable directories
- **Reference File Protection:** Prevent agents from modifying important reference files
- **Clear Error Messages:** Agents get clear feedback when trying to modify protected files

**How It Works:**
```yaml
orchestrator:
  context_paths:
    - path: "/workspace"
      permission: WRITE
      protected_paths:
        - "/workspace/reference/important_config.yaml"
        - "/workspace/templates/*.template"
```

**Try It Out:**
```bash
# Protected paths example
massgen --config @examples/gemini_gpt5nano_protected_paths \
  "Modify the project files but preserve the reference configuration"
```

**Use Cases:**
- Protect configuration templates while allowing workspace modifications
- Preserve reference documentation during code generation
- Safeguard important files in collaborative multi-agent scenarios
- Prevent accidental deletion of critical files

---

### Code Refactoring

Major restructuring of utility modules for better code organization.

**Module Relocation:**
Moved from `backend/utils/` to top-level `massgen/`:
- `api_params_handler` module
- `formatter` module
- `filesystem_manager` module

**Benefits:**
- Simplified import paths
- Better code discoverability
- Improved separation between backend-specific and shared utilities
- Cleaner module structure
- Easier maintenance

**Impact:**
- Internal refactoring with no breaking changes to user configurations
- Better foundation for future development
- More intuitive codebase organization

---

## What Changed

### Path Permission Manager Enhancements

Major improvements to the permission system.

**Changes:**
- Enhanced `will_be_writable` logic for better permission state tracking
- Improved path validation distinguishing between context paths and workspace paths
- Better handling of edge cases and nested path scenarios
- Comprehensive test coverage in `test_path_permission_manager.py`

**Benefits:**
- More reliable permission checks
- Better error messages for permission violations
- Improved handling of complex permission scenarios
- Stronger safety guarantees

---

## What Was Fixed

### Path Permission Edge Cases

Resolved various permission checking issues:
- Fixed file context path validation logic
- Corrected protected path matching behavior
- Improved handling of nested paths and symbolic links
- Better error handling for non-existent paths

**Impact:**
- More reliable permission system
- Fewer unexpected permission errors
- Better handling of edge cases
- Improved user experience

---

## New Configurations

### Configuration Examples (3 configs)

Located in `massgen/configs/`:

1. **gemini_gpt5nano_protected_paths.yaml**
   - Demonstrates protected paths feature
   - Use Case: Protecting reference files while allowing modifications
   - Example: "Update the code but preserve the configuration template"

2. **gemini_gpt5nano_file_context_path.yaml**
   - Shows file-based context path usage
   - Use Case: Granting access to specific files only
   - Example: "Read this config file and suggest optimizations"

3. **gemini_gemini_workspace_cleanup.yaml**
   - Demonstrates workspace cleanup capabilities
   - Use Case: Organizing and cleaning workspaces
   - Example: "Clean up temporary files and organize the workspace"

---

## Documentation Updates

### New Documentation

- **file_deletion_and_context_files.md:** Comprehensive design documentation for file deletion and context file features
- **Updated permissions_and_context_files.md:** Enhanced with v0.0.26 features
- **Release Workflow Documentation:** Added `docs/workflows/release_example_checklist.md` with step-by-step release preparation guide

### Example Resources

Added v0.0.26 example resources for testing:
- Bob Dylan themed website with multiple pages and styles
- HTML, CSS, and JavaScript examples
- Located in `massgen/configs/resources/v0.0.26-example/`

**Purpose:**
- Testing protected paths feature
- Demonstrating file context paths
- Workspace cleanup examples

---

## Technical Details

### Statistics

- **Commits:** 20+ commits
- **Files Modified:** 46 files
- **Insertions:** 4,343 lines
- **Deletions:** 836 lines
- **New Tools:** 4 MCP workspace tools

### Major Components Changed

1. **MCP Workspace Tools:** File deletion and comparison capabilities
2. **Permission System:** Protected paths and file context paths
3. **Code Structure:** Module reorganization and refactoring
4. **Path Validation:** Enhanced permission manager logic

### New MCP Tools

**delete_file:**
- Delete a single file with permission validation
- Returns confirmation or error message
- Integrated with permission system

**delete_files_batch:**
- Delete multiple files in one operation
- Batch validation before deletion
- Detailed results for each file

**compare_directories:**
- Show differences between two directories
- List files unique to each directory
- Identify common files with differences

**compare_files:**
- Compare two files line by line
- Show differences with context
- Useful for verification before deletion

---

## Use Cases

### Workspace Organization

**Cleanup After Processing:**
```bash
# Agents clean up temporary files
massgen --config @examples/gemini_gemini_workspace_cleanup \
  "Remove all .tmp files and organize remaining files into folders"
```

**Multi-Turn Session Cleanup:**
```bash
# Clean up between conversation turns
massgen --config @examples/gemini_gemini_workspace_cleanup \
  "Delete outdated files from previous iterations"
```

### Reference File Protection

**Template Preservation:**
```yaml
context_paths:
  - path: "/project/templates"
    permission: WRITE
    protected_paths:
      - "/project/templates/base.template"
```

**Configuration Safety:**
```yaml
context_paths:
  - path: "/app/config"
    permission: WRITE
    protected_paths:
      - "/app/config/default_config.yaml"
```

### File-Level Access Control

**Specific File Access:**
```yaml
context_paths:
  - path: "/data/config.json"  # Single file
    permission: READ
  - path: "/data/schema.yaml"  # Another single file
    permission: READ
```

---

## Migration Guide

### Upgrading from v0.0.25

**No Breaking Changes**

v0.0.26 is fully backward compatible with v0.0.25. All existing configurations will continue to work.

**Optional: Enable New Features**

**1. Use File Deletion Tools:**

File deletion tools are automatically available when using MCP workspace tools.

```bash
# Agents can now delete files
uv run python -m massgen.cli \
  --config your_config.yaml \
  "Clean up temporary files"
```

**2. Add Protected Paths:**

```yaml
orchestrator:
  context_paths:
    - path: "/your/workspace"
      permission: WRITE
      protected_paths:
        - "/your/workspace/important_file.txt"
```

**3. Use File Context Paths:**

```yaml
orchestrator:
  context_paths:
    - path: "/path/to/specific/file.txt"
      permission: READ
```

**Code Changes:**

If you have custom code importing from `backend/utils/`, update imports:

```python
# Old import
from massgen.backend.utils.filesystem_manager import FilesystemManager

# New import
from massgen.filesystem_manager import FilesystemManager
```

---

## Contributors

Special thanks to all contributors who made v0.0.26 possible:

- @praneeth999
- @ncrispino
- @qidanrui
- @sonichi
- @Henry-811
- And the entire MassGen team

---

## Resources

- **CHANGELOG:** [CHANGELOG.md](../../../CHANGELOG.md#0026---2025-10-01)
- **Design Doc:** [file_deletion_and_context_files.md](../../../backend/docs/file_deletion_and_context_files.md)
- **Permissions Doc:** [permissions_and_context_files.md](../../../backend/docs/permissions_and_context_files.md)
- **Next Release:** [v0.0.27 Release Notes](../v0.0.27/release-notes.md) - Multimodal Support
- **Previous Release:** [v0.0.25 Release Notes](../v0.0.25/release-notes.md) - Multi-Turn Filesystem
- **GitHub Release:** https://github.com/Leezekun/MassGen/releases/tag/v0.0.26

---

## What's Next

See the [v0.0.27 Release](../v0.0.27/release-notes.md) for what came after, including:
- **Multimodal Support** - Image processing and generation
- **File Upload and Search** - Document Q&A capabilities
- **Claude Sonnet 4.5** - Latest Claude model support

---

*Released with ❤️ by the MassGen team*
