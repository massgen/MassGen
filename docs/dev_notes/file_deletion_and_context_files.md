# File Deletion and Context Files Design Document

## Overview
This document describes the implementation of file/directory deletion capabilities, file-based context paths, protected paths feature, and optional diff tools for MassGen's filesystem management system, addressing [Issue #254](https://github.com/Leezekun/MassGen/issues/254).

## Quick Start Examples

### Example 1: Protected Paths
**Use Case**: Allow agents to modify files but prevent changes to specific reference files.

**Config**: [`massgen/configs/tools/filesystem/gemini_gpt5nano_protected_paths.yaml`](../../massgen/configs/tools/filesystem/gemini_gpt5nano_protected_paths.yaml)

**Command**:
```bash
massgen --config @examples/tools/filesystem/gemini_gpt5nano_protected_paths "Review the HTML and CSS files, then improve the styling"
```

**Result**:
- ✅ `massgen/configs/resources/v0.0.21-example/styles.css` → Can modify/delete
- ❌ `massgen/configs/resources/v0.0.21-example/index.html` → Read-only (protected)

---

### Example 2: File Context Path (Single File Access)
**Use Case**: Give agents access to a specific file without exposing the entire directory.

**Config**: [`massgen/configs/tools/filesystem/gemini_gpt5nano_file_context_path.yaml`](../../massgen/configs/tools/filesystem/gemini_gpt5nano_file_context_path.yaml)

**Command**:
```bash
massgen --config @examples/tools/filesystem/gemini_gpt5nano_file_context_path "Analyze the CSS file and make modern improvements"
```

**Result**:
- ✅ `massgen/configs/resources/v0.0.21-example/styles.css` → Can read/write
- ❌ `massgen/configs/resources/v0.0.21-example/index.html` → NOT accessible (sibling file blocked)

---

### Example 3: Workspace Cleanup with Deletion Tools
**Use Case**: Agents can delete outdated files during iteration to keep workspace clean.

**Config**: [`massgen/configs/tools/filesystem/gemini_gemini_workspace_cleanup.yaml`](../../massgen/configs/tools/filesystem/gemini_gemini_workspace_cleanup.yaml)

**Command**:
```bash
massgen --config @examples/tools/filesystem/gemini_gemini_workspace_cleanup "Please improve the website to reference Jimi Hendrix then remove the other files and directories that aren't being used"
```

**What happens**:
1. Agents analyze the messy directory (`v0.0.26-example`) with multiple HTML files (beatles.html, dylan.html, index.html, bob_dylan_website/)
2. Agents combine the best elements from existing websites to create improved Jimi Hendrix website
3. Agents use `delete_file` tool to remove old/redundant files
4. Final workspace contains only one clean website

**Available Deletion Tools**:
- `delete_file(path, recursive=False)` - Delete single file/directory
- `delete_files_batch(base_path, include_patterns, exclude_patterns)` - Delete multiple files matching patterns

---

### Additional Improvements
During implementation, we also addressed:
1. **CLI Enhancement**: Added interactive prompt for protected paths when users add custom context paths in multiturn dialogue mode
2. **MCP Server Compatibility Fix**: Fixed MCP filesystem server crash when file paths were passed as arguments (only directories are supported)
3. **Sibling File Isolation**: Implemented comprehensive access control to prevent agents from accessing sibling files when a specific file is added as a context path

## Motivation

### Problem 1: Workspace Cleanup
Currently, agents can only add or edit files in their workspace. Over multiple iterations, workspaces become cluttered with outdated files:
```
index.html (old version)
new_website/
    index.html (new version)
```
Agents cannot clean up old files, leading to confusion about which files are current.

### Problem 2: Context Paths as Files
Users can only provide directories as context paths. To share a single file like `config.yaml`, users must:
1. Provide the parent directory as context path
2. Give access to all files in that directory (security/privacy concern)
3. Risk agents accessing unintended files

### Problem 3: Workspace Comparison
With copy-heavy workflows, users need to:
- Compare different workspace states
- See what changed between agent iterations
- Understand differences before deploying to production

## Design Goals

1. **Safe Deletion**: Allow agents to delete files/directories with proper permission checks
2. **File Context Paths**: Support single files as context paths, not just directories
3. **Protected Paths**: Allow users to specify files/directories immune from modification/deletion
4. **Diff Tools**: Provide utilities to compare workspaces and directories
5. **Backward Compatibility**: Existing configs continue to work unchanged
6. **Security**: All operations respect existing permission boundaries

## Implementation

### 1. File Deletion Tools

#### New Tools in `_workspace_tools_server.py`

**Tool: `delete_file`**
```python
@mcp.tool()
def delete_file(path: str, recursive: bool = False) -> Dict[str, Any]:
    """
    Delete a file or directory from the workspace.

    Args:
        path: Path to file/directory to delete (absolute or relative to workspace)
        recursive: Whether to delete directories recursively (default: False)

    Returns:
        Dictionary with deletion results

    Security:
        - Requires WRITE permission on path
        - Must be within allowed paths
        - Workspace files always deletable
        - Context paths require write permission
    """
```

**Tool: `delete_files_batch`**
```python
@mcp.tool()
def delete_files_batch(
    base_path: str,
    include_patterns: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Delete multiple files matching patterns.

    Args:
        base_path: Base directory to search in
        include_patterns: Glob patterns for files to include (default: ["*"])
        exclude_patterns: Glob patterns for files to exclude

    Returns:
        Dictionary with batch deletion results including:
        - deleted: List of deleted files
        - skipped: List of skipped files (permission denied)
        - errors: List of errors encountered
    """
```

#### Implementation Details

1. **Path Validation**:
   - Resolve relative paths against workspace (via `cwd`)
   - Validate path is within allowed directories
   - Check permissions via PathPermissionManager

2. **Safety Checks**:
   - Never delete system files (.git, .env, node_modules, etc.)
   - Require `recursive=True` for directory deletion
   - Prevent deletion of workspace root
   - Atomic operations where possible

3. **Error Handling**:
   - Clear error messages for permission failures
   - Report which files failed and why
   - Graceful handling of non-existent paths

### 2. File-Based Context Paths with Protected Paths

#### Changes to `PathPermissionManager`

**Current Behavior**:
```yaml
context_paths:
  - path: "/path/to/directory"
    permission: "read"
```

**New Behavior** (backward compatible):
```yaml
context_paths:
  - path: "/path/to/directory"      # Still works (Unix/macOS)
    permission: "read"
  - path: "C:\\Users\\Project\\data"  # Windows paths also supported
    permission: "read"
  - path: "/path/to/config.yaml"    # NEW: Single file support
    permission: "read"
  - path: "/path/to/testing"        # NEW: Protected paths support
    permission: "write"
    protected_paths:                 # These paths are ALWAYS read-only
      - "do-not-touch/"              # Relative to context path
      - "config.yaml"                # Single file protection
      - "golden_tests/"              # Entire directory protection
```

**Note**: All paths are handled using Python's `pathlib.Path`, which automatically normalizes paths for the current operating system. Both forward slashes (`/`) and backslashes (`\`) work on all platforms.

#### Implementation in `_path_permission_manager.py`

```python
def add_context_paths(self, context_paths: List[Dict[str, Any]]) -> None:
    """
    Add context paths from configuration.
    Now supports both files and directories.
    """
    for config in context_paths:
        path = Path(config.get("path", ""))
        if not path.exists():
            logger.warning(f"Context path does not exist: {path}")
            continue

        if path.is_file():
            # NEW: Handle file context paths
            # Add parent directory to allowed paths for access
            parent = path.parent
            self._add_file_context_path(path, parent, config)
        else:
            # Existing: Handle directory context paths
            self._add_directory_context_path(path, config)
```

#### File Context Path Behavior

1. **MCP Filesystem Config**:
   - Add parent directory to allowed paths
   - Track specific file in managed paths
   - Permissions apply only to that file

2. **Permission Checks**:
   - File gets specified permission
   - Siblings in same directory not accessible
   - Parent directory not directly accessible (unless separately added)

3. **Security**:
   - Prevents directory traversal attacks
   - Isolates file access from directory access
   - Maintains principle of least privilege

#### Protected Paths Feature

**Purpose**: Give users fine-grained control over which files/directories within context paths should NEVER be modified or deleted, even when the parent context has write permission.

**Use Cases**:
- Golden test data that should never change
- Configuration files that define expected behavior
- Reference implementations for comparison
- Sensitive data that agents can read but must not modify

**Implementation**:

```python
@dataclass
class ManagedPath:
    protected_paths: List[Path] = None  # Paths immune from modification/deletion

    def is_protected(self, check_path: Path) -> bool:
        """Check if path is in protected paths list."""
        # Exact match or check if path is within protected directory
        for protected in self.protected_paths:
            if check_path == protected or check_path is within protected:
                return True
        return False
```

**Permission Resolution Priority**:
1. System files (.massgen, .git) → Always READ
2. Protected paths → Always READ (overrides context write permission)
3. File-specific context paths → Specified permission (READ or WRITE)
4. Directory context paths → Specified permission (READ or WRITE)

**Example Behavior (Unix/macOS)**:
```yaml
context_paths:
  - path: "/project/testing"
    permission: "write"
    protected_paths:
      - "golden_tests/"
      - "expected_output.txt"
```

- `/project/testing/new_test.py` → WRITE (can create/modify/delete)
- `/project/testing/golden_tests/test1.json` → READ (protected, cannot modify)
- `/project/testing/expected_output.txt` → READ (protected, cannot modify)
- `/project/testing/golden_tests/subdir/file.txt` → READ (within protected dir)

**Example Behavior (Windows)**:
```yaml
context_paths:
  - path: "C:\\Projects\\testing"
    permission: "write"
    protected_paths:
      - "golden_tests\\"
      - "expected_output.txt"
```

- `C:\Projects\testing\new_test.py` → WRITE (can create/modify/delete)
- `C:\Projects\testing\golden_tests\test1.json` → READ (protected, cannot modify)
- `C:\Projects\testing\expected_output.txt` → READ (protected, cannot modify)
- `C:\Projects\testing\golden_tests\subdir\file.txt` → READ (within protected dir)

### 3. Diff Tools

#### New Tools in `_workspace_tools_server.py`

**Tool: `compare_directories`**
```python
@mcp.tool()
def compare_directories(
    dir1: str,
    dir2: str,
    show_content_diff: bool = False
) -> Dict[str, Any]:
    """
    Compare two directories and show differences.

    Returns:
        - only_in_dir1: Files only in first directory
        - only_in_dir2: Files only in second directory
        - different: Files that exist in both but differ
        - identical: Files that are identical
        - content_diff: Optional unified diffs (if show_content_diff=True)
    """
```

**Tool: `compare_files`**
```python
@mcp.tool()
def compare_files(
    file1: str,
    file2: str,
    context_lines: int = 3
) -> Dict[str, Any]:
    """
    Compare two text files and show unified diff.

    Returns:
        - identical: Boolean
        - diff: Unified diff output
        - stats: Lines added/removed/changed
    """
```

#### Implementation Using Python Standard Library

```python
import difflib
import filecmp

def compare_directories(dir1: str, dir2: str, show_content_diff: bool = False):
    """Use filecmp.dircmp for directory comparison."""
    dcmp = filecmp.dircmp(dir1, dir2)

    result = {
        "only_in_dir1": list(dcmp.left_only),
        "only_in_dir2": list(dcmp.right_only),
        "different": list(dcmp.diff_files),
        "identical": list(dcmp.same_files),
    }

    if show_content_diff:
        # Generate unified diffs for differing files
        result["content_diff"] = _generate_content_diffs(dcmp)

    return result

def compare_files(file1: str, file2: str, context_lines: int = 3):
    """Use difflib for file comparison."""
    with open(file1) as f1, open(file2) as f2:
        lines1 = f1.readlines()
        lines2 = f2.readlines()

    diff = list(difflib.unified_diff(
        lines1, lines2,
        fromfile=file1, tofile=file2,
        lineterm='', n=context_lines
    ))

    return {
        "identical": len(diff) == 0,
        "diff": '\n'.join(diff),
        "stats": _calculate_diff_stats(diff)
    }
```

### 4. Permission Manager Updates

#### Deletion Validation

The existing `_is_write_tool()` method already detects delete operations (lines 332-333):
```python
r".*[Dd]elete.*",  # delete operations
r".*[Rr]emove.*",  # remove operations
```

Updates needed in `_validate_write_tool()`:
1. Extract path from delete tool arguments
2. Check WRITE permission on path
3. Block deletions in read-only context paths
4. Allow deletions in workspace and writable context paths

#### System File Protection

Enhance `_is_excluded_path()` to prevent deletion of critical files:
```python
UNDELETABLE_PATTERNS = [
    ".git",
    ".env",
    "node_modules",
    "__pycache__",
    ".massgen",
    "massgen_logs",
]
```

Deletion attempts on these patterns should fail even with WRITE permission.

## Security Considerations

### Deletion Operations
1. **Permission Enforcement**: All deletions require WRITE permission
2. **Path Restrictions**: Must be within allowed paths
3. **System Protection**: Critical system files cannot be deleted
4. **Audit Trail**: All deletions logged with full path and outcome

### File Context Paths
1. **Isolation**: File access doesn't grant directory access
2. **Sibling Protection**: Can't access other files in same directory
3. **Path Traversal**: Prevented by existing validation
4. **Permission Inheritance**: File permissions independent of directory

### Diff Operations
1. **Read-Only**: Diff tools never modify files
2. **Path Validation**: Both paths must be in allowed directories
3. **Large Files**: Optional limits on file size for diffs
4. **Binary Files**: Skip binary files in content diffs

## Testing Strategy

### Unit Tests (`test_path_permission_manager.py`)

```python
def test_delete_file_permissions():
    """Test that delete operations respect permissions."""
    # Test workspace deletion (allowed)
    # Test read-only context deletion (blocked)
    # Test writable context deletion (allowed)
    # Test system file deletion (blocked)

def test_delete_files_batch():
    """Test batch deletion with patterns."""
    # Test pattern matching
    # Test permission checks on each file
    # Test exclusion patterns

def test_file_context_paths():
    """Test single file context paths."""
    # Test file vs directory detection
    # Test file permission isolation
    # Test parent directory not accessible

def test_compare_directories():
    """Test directory comparison tool."""
    # Test detecting added/removed files
    # Test detecting modified files
    # Test content diff generation

def test_compare_files():
    """Test file comparison tool."""
    # Test identical files
    # Test different files
    # Test diff statistics
```

### Integration Tests

1. **Workspace Cleanup Scenario**:
   - Agent creates old_index.html
   - Agent creates new_website/index.html
   - Agent uses `delete_file` to remove old_index.html
   - Verify workspace clean

2. **File Context Path Scenario**:
   - User provides single config.yaml as context
   - Agent reads config.yaml (allowed)
   - Agent tries to read sibling.txt (blocked)
   - Agent tries to list parent directory (blocked)

3. **Diff Workflow Scenario**:
   - Compare workspace before/after changes
   - Identify modified files
   - Generate content diffs
   - Verify no side effects

## Additional Improvements

### CLI Enhancement: Interactive Protected Paths Prompt

**File**: `massgen/cli.py` - `prompt_for_context_paths()` function

When users add custom context paths in interactive mode, they are now prompted to specify protected paths:

```
Enter path: /project/testing
Permission [read/write] (default: write): write
Add protected paths (files/dirs immune from modification)? [y/N]: y
Enter protected paths (relative to context path), one per line. Empty line to finish:
  → golden_tests/
  → expected_output.txt
  →
✓ Will protect 2 path(s)
✓ Added /project/testing (write)
```

**Implementation**:
```python
if permission == "write":
    add_protected = input("   Add protected paths (files/dirs immune from modification)? [y/N]: ").strip().lower()
    if add_protected in ["y", "yes"]:
        print("   Enter protected paths (relative to context path), one per line. Empty line to finish:")
        while True:
            protected_input = input("     → ").strip()
            if not protected_input:
                break
            protected_paths.append(protected_input)
```

This provides a user-friendly way to specify protected paths without manually editing YAML configuration files.

### Bug Fix: MCP Filesystem Server Crash with File Paths

**Problem**: When file context paths were added (e.g., `/project/index.html`), the MCP filesystem server would crash with:
```
MCP manager error for filesystem: unhandled errors in a TaskGroup (1 sub-exception)
Failed to connect to MCP server filesystem: unknown error
```

**Root Cause**: The MCP filesystem server (`@modelcontextprotocol/server-filesystem`) only accepts **directory paths** as arguments. When file context paths were added:
1. The file path itself was added to `managed_paths` with `is_file=True`
2. The parent directory was added with `path_type="file_context_parent"`
3. `get_mcp_filesystem_paths()` returned **both** the file and its parent directory
4. The MCP server received file paths as arguments and crashed

**Solution** (`massgen/filesystem_manager/_path_permission_manager.py` lines 693-709):

```python
def get_mcp_filesystem_paths(self) -> List[str]:
    """
    Get all managed paths for MCP filesystem server configuration. Workspace path will be first.

    Only returns directories, as MCP filesystem server cannot accept file paths as arguments.
    For file context paths, the parent directory is already added with path_type="file_context_parent".

    Returns:
        List of directory path strings to include in MCP filesystem server args
    """
    # Only include directories - exclude file-type managed paths (is_file=True)
    # The parent directory for file contexts is already added separately
    workspace_paths = [str(mp.path) for mp in self.managed_paths if mp.path_type == "workspace"]
    other_paths = [str(mp.path) for mp in self.managed_paths
                  if mp.path_type != "workspace" and not mp.is_file]
    out = workspace_paths + other_paths
    return out
```

**Key Changes**:
- Added filter `and not mp.is_file` to exclude file-type managed paths
- MCP server now only receives directory paths
- Parent directories for file contexts are already included via `file_context_parent` entries
- Files remain in `managed_paths` for permission tracking but aren't passed to MCP

**Impact**:
- ✅ MCP filesystem server connects successfully with file context paths
- ✅ File context paths work as intended (only specific file accessible)
- ✅ No more "unhandled errors in a TaskGroup" crashes
- ✅ Maintains full permission tracking for file-level access control

### Enhancement 4: Sibling File Access Prevention

**Problem**: When a specific file was added as a context path (e.g., `/project/config.yaml`), the MCP filesystem server was given access to the parent directory (`/project/`), which would allow agents to access **all** files in that directory, including siblings like `/project/secrets.yaml`.

**Solution**: Implemented comprehensive permission hooks to intercept **all** tool calls and validate file access (`massgen/filesystem_manager/_path_permission_manager.py` lines 440-504):

**1. New Validation Method** (`_validate_file_context_access`):
```python
def _validate_file_context_access(self, tool_name: str, tool_args: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validate access for file context paths (prevents sibling file access).

    When a specific file is added as a context path, only that file should be accessible,
    not other files in the same directory. This method checks all tool calls to enforce this.
    """
    # Extract file path from arguments
    file_path = self._extract_file_path(tool_args)
    if not file_path:
        # Can't determine path - allow it (tool may not access files)
        return (True, None)

    # Resolve relative paths against workspace
    file_path = self._resolve_path_against_workspace(file_path)
    path = Path(file_path).resolve()
    permission = self.get_permission(path)

    # If permission is None, check if in file_context_parent directory
    if permission is None:
        parent_paths = [mp for mp in self.managed_paths if mp.path_type == "file_context_parent"]
        for parent_mp in parent_paths:
            if parent_mp.contains(path):
                # Path is in a file context parent dir, but not the specific file
                return (False, f"Access denied: '{path}' is not an explicitly allowed file in this directory")
        # Not in any managed paths - allow (likely workspace or other valid path)
        return (True, None)

    # Has explicit permission - allow
    return (True, None)
```

**2. Updated Hook Flow** (`pre_tool_use_hook`):
```python
async def pre_tool_use_hook(self, tool_name: str, tool_args: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    # Check if this is a write operation using pattern matching
    if self._is_write_tool(tool_name):
        return self._validate_write_tool(tool_name, tool_args)

    # Tools that can potentially modify through commands
    command_tools = {"Bash", "bash", "shell", "exec"}

    # Check command tools for dangerous operations
    if tool_name in command_tools:
        return self._validate_command_tool(tool_name, tool_args)

    # For all other tools (including Read, Grep, Glob, list_directory, etc.),
    # validate access to file context paths to prevent sibling file access
    return self._validate_file_context_access(tool_name, tool_args)
```

**How It Works**:

When `/project/index.html` is added as a context path:

1. **Setup Phase**:
   - `ManagedPath(path="/project/", path_type="file_context_parent")` - for MCP
   - `ManagedPath(path="/project/index.html", is_file=True)` - for permissions

2. **MCP Configuration**:
   - Only `/project/` is passed to MCP server (files filtered out)
   - MCP allows access to entire directory

3. **Access Control (Agent tries to access files)**:

   **Case A: Accessing `/project/index.html`** ✅
   - `get_permission()` finds exact match with `is_file=True`
   - Returns `Permission.READ` or `Permission.WRITE`
   - Access granted

   **Case B: Accessing `/project/sibling.txt`** ❌
   - `get_permission()` checks file-specific paths: No match
   - `get_permission()` checks directory paths: Excludes `file_context_parent`
   - Returns `None`
   - `_validate_file_context_access()` detects path is in `file_context_parent`
   - **Access denied** with message: "Access denied: '/project/sibling.txt' is not an explicitly allowed file in this directory"

**Tools Protected**:
- ✅ Write tools (Write, Edit, Delete, Copy, Move)
- ✅ Read tools (Read, Grep, Glob, read_file)
- ✅ Directory tools (list_directory, search_files)
- ✅ All file-accessing tools

**Impact**:
- ✅ File-level security for context paths
- ✅ Prevents accidental exposure of sensitive sibling files
- ✅ Granular access control without exposing entire directories
- ✅ Works seamlessly with MCP filesystem servers
- ✅ Clear error messages when access is denied

## Migration Path

### Backward Compatibility
- All existing configs work unchanged
- Directory context paths work as before
- New features are opt-in

### Incremental Adoption

**Phase 1: Directory Context (Current)**
```yaml
context_paths:
  - path: "/project/src"
    permission: "read"
```

**Phase 2: File Context (New)**
```yaml
context_paths:
  - path: "/project/src"           # Directory access
    permission: "read"
  - path: "/project/assets/logo.png"  # Single file
    permission: "read"
```

**Phase 3: Cleanup Workflows (New)**
```python
# Agent workflow
1. Create files in workspace
2. Test and iterate
3. Use delete_file to clean up old versions
4. Use copy_file to deploy final version
```

**Phase 4: Diff-Driven Development (New)**
```python
# Agent workflow
1. Use compare_directories to see workspace vs production
2. Make targeted changes
3. Use compare_files to verify specific changes
4. Deploy with confidence
```

## Implementation Checklist

### Core Features
- [x] Add `delete_file` tool to `_workspace_tools_server.py`
- [x] Add `delete_files_batch` tool to `_workspace_tools_server.py`
- [x] Add `_is_critical_path()` helper to protect system files
- [x] Add `_is_permission_path_root()` to prevent deleting workspace roots
- [x] Add `compare_directories` tool to `_workspace_tools_server.py`
- [x] Add `compare_files` tool to `_workspace_tools_server.py`
- [x] Add `_is_text_file()` helper for diff operations

### Permission System
- [x] Update `add_context_paths()` to handle files in `_path_permission_manager.py`
- [x] Add file context path tracking in `PathPermissionManager`
- [x] Update MCP filesystem config generation for file context paths
- [x] **Fix `get_mcp_filesystem_paths()` to filter out file paths** (MCP server only accepts directories)
- [x] Add `protected_paths` feature to context paths
- [x] Update `ManagedPath` dataclass with `is_file` and `protected_paths` fields
- [x] Add `is_protected()` method to `ManagedPath`
- [x] Update `get_permission()` to check protected paths first
- [x] Add deletion validation to `_validate_write_tool()`
- [x] **Add `_validate_file_context_access()` method to prevent sibling file access**
- [x] **Update `pre_tool_use_hook()` to validate all tools for file context paths**
- [x] **Add sibling file blocking in write tool validation**

### User Experience
- [x] Update system prompt with workspace cleanup guidance in `message_templates.py`
- [x] Clarify deletion permissions in system prompt (cannot delete read-only files)
- [x] Add comparison tools guidance to system prompt (compare_directories, compare_files)
- [x] Add protected paths prompt to interactive mode in `cli.py`
- [x] Users can specify protected paths when adding custom context paths interactively
- [x] **Update CLI to support both files and directories** (removed directory-only restriction)
- [x] **Add clear prompts for file/directory input** ("absolute or relative, file or directory")
- [x] **Add retry loop for invalid paths with user-friendly error messages**
- [x] **Add explicit "No" option handling in context path prompt**

### Testing
- [x] Write unit tests for deletion operations (`test_delete_operations`)
- [x] Write unit tests for file context paths (`test_file_context_paths`)
- [x] Write unit tests for protected paths (`test_protected_paths`)
- [x] Write unit tests for diff tools (`test_compare_tools`)
- [x] Write unit tests for permission path root protection (`test_permission_path_root_protection`)
- [x] All 14 tests passing

### Bug Fixes
- [x] **Fix MCP filesystem server crash** when file paths passed as arguments
- [x] **Filter file paths from `get_mcp_filesystem_paths()`** to only return directories

### Documentation
- [x] Write comprehensive design document (`file_deletion_and_context_files.md`)
- [x] Document protected paths feature with examples
- [x] Document permission resolution priority
- [x] Update implementation checklist
- [x] Add usage examples and migration path
- [x] **Document MCP filesystem server fix and sibling file isolation**
- [x] **Update `permissions_and_context_files.md` with file context path examples**
- [x] **Add file context path use cases and interactive examples**
- [x] **Document sibling file access blocking behavior**

## Future Enhancements

1. **Dry-Run Mode**: Preview deletions before executing
2. **Undo Capability**: Store deleted files temporarily for recovery
3. **Smart Diffs**: Use better diff algorithms (Myers, Patience)
4. **Directory Merge**: Tool to merge changes from multiple workspaces
5. **File Metadata**: Compare timestamps, permissions, sizes
6. **Diff Visualization**: Generate HTML/rich output for diffs
7. **TODO: Improved Tool Name Matching for File Path Extraction**: Current implementation uses `_extract_file_path()` which looks for common parameter names like `path`, `file_path`, `dir`, etc. However, some backends like Claude Code may have tools with non-standard parameter names that aren't matched by our current patterns. This could lead to sibling file access not being properly validated.
   - **Problem**: If a tool uses a parameter name not in our current list (e.g., `location`, `target`, `source`), `_extract_file_path()` returns `None` and validation is skipped
   - **Current workaround**: Falls back to "allow if can't determine path" (line 485 in `_validate_file_context_access`)
   - **Proposed solutions**:
     - Add logging to track when path extraction fails for file-accessing tools
     - Expand parameter name patterns in `_extract_file_path()` to cover more variations
     - Consider introspecting tool schemas to automatically detect path parameters
     - Add backend-specific tool name mappings for known edge cases
     - Potentially deny access by default if tool name suggests file access but path can't be extracted
   - **Example edge case**: A hypothetical Claude Code tool `inspect_resource(location="...")` might bypass sibling file validation
   - **Priority**: Medium - Current implementation is secure by default (MCP server + existing patterns), but could miss edge cases with non-standard tool names

## References

### Issue
- [Issue #254](https://github.com/Leezekun/MassGen/issues/254) - File Deletion, Context Path Files, and Protected Paths

### Modified Files
- `massgen/backend/utils/filesystem_manager/_workspace_tools_server.py` - Deletion & diff tools
- `massgen/backend/utils/filesystem_manager/_path_permission_manager.py` - Protected paths, file context paths, sibling file isolation, MCP server fix
- `massgen/message_templates.py` - Workspace cleanup guidance
- `massgen/tests/test_path_permission_manager.py` - Test coverage (17 tests, enhanced file context path tests)
- `massgen/cli.py` - Interactive protected paths prompt, file/directory support, improved error handling
- `massgen/backend/docs/permissions_and_context_files.md` - Updated with file context path documentation
- `docs/dev_notes/file_deletion_and_context_files.md` - Added MCP fix and sibling isolation sections

### Related Documentation
- `docs/case_studies/user-context-path-support-with-copy-mcp.md`
- Python `pathlib`, `shutil`, `filecmp`, `difflib` documentation

### Test Coverage
- 17 tests total, all passing
- `test_delete_operations()` - Deletion permission validation
- `test_permission_path_root_protection()` - Workspace root protection
- `test_protected_paths()` - Protected paths enforcement
- `test_file_context_paths()` - File-based context paths with comprehensive sibling file isolation tests
- `test_compare_tools()` - Diff tools validation