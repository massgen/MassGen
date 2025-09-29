# File Deletion and Context Files Design Document

## Overview
This document describes the implementation of file/directory deletion capabilities, file-based context paths, protected paths feature, and optional diff tools for MassGen's filesystem management system, addressing [Issue #254](https://github.com/Leezekun/MassGen/issues/254).

### Additional Improvements
During implementation, we also addressed:
1. **CLI Enhancement**: Added interactive prompt for protected paths when users add custom context paths in multiturn dialogue mode
2. **Critical Bug Fix**: Fixed async generator cleanup in orchestrator that caused "async generator ignored GeneratorExit" errors when users quit inspection interface

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
Users can only provide directories as context paths. To share a single file like `image.png`, users must:
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

#### New Tools in `_workspace_copy_server.py`

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
  - path: "/path/to/directory"      # Still works
    permission: "read"
  - path: "/path/to/file.png"       # NEW: Single file support
    permission: "read"
  - path: "/path/to/testing"        # NEW: Protected paths support
    permission: "write"
    protected_paths:                 # These paths are ALWAYS read-only
      - "do-not-touch/"              # Relative to context path
      - "config.yaml"                # Single file protection
      - "golden_tests/"              # Entire directory protection
```

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

**Example Behavior**:
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

### 3. Diff Tools

#### New Tools in `_workspace_copy_server.py`

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
   - User provides single image.png as context
   - Agent reads image.png (allowed)
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

### Bug Fix: Async Generator Cleanup

**Problem**: When users quit the inspection interface during multi-agent coordination, async generators were not properly closed, causing:
```
Task exception was never retrieved
future: <Task-1555 finished name='Task-1555' exception=RuntimeError('async generator ignored GeneratorExit')>
RuntimeError: async generator ignored GeneratorExit
```

**Root Cause**: Two issues were causing this error:

1. The `chat_stream` async generator in `_stream_agent_execution()` was not handling `GeneratorExit` exceptions when the generator is closed before completion (e.g., user quits inspection).

2. The `_get_next_chunk()` method was not handling `GeneratorExit` exceptions. When a task calls `stream.__anext__()` and the generator is closed, it raises `GeneratorExit` (a `BaseException`, not `Exception`), which was not being caught by the `except Exception` clause.

**Solution 1** (`massgen/orchestrator.py` lines 1287-1402) - Handle GeneratorExit in `_stream_agent_execution()`:

```python
try:
    async for chunk in chat_stream:
        # Process chunks...
        if chunk.type == "content":
            yield ("content", chunk.content)
        elif chunk.type == "tool_calls":
            # Handle tool calls...
except GeneratorExit:
    # Handle case when generator is closed (e.g., user quits inspection)
    logger.info(f"[Orchestrator] Agent {agent_id} stream closed by GeneratorExit")
    # Properly close the chat_stream async generator
    if hasattr(chat_stream, 'aclose'):
        try:
            await chat_stream.aclose()
        except Exception as e:
            logger.warning(f"[Orchestrator] Error closing chat_stream for {agent_id}: {e}")
    raise  # Re-raise to propagate the GeneratorExit
finally:
    # Ensure chat_stream is closed even on normal completion
    if hasattr(chat_stream, 'aclose'):
        try:
            await chat_stream.aclose()
        except Exception as e:
            logger.debug(f"[Orchestrator] Error in finally block closing chat_stream for {agent_id}: {e}")
```

**Solution 2** (`massgen/orchestrator.py` lines 1626-1641) - Handle GeneratorExit in `_get_next_chunk()`:

```python
async def _get_next_chunk(self, stream: AsyncGenerator[tuple, None]) -> tuple:
    """Get the next chunk from an agent stream."""
    try:
        return await stream.__anext__()
    except StopAsyncIteration:
        return ("done", None)
    except GeneratorExit:
        # Handle generator being closed (e.g., user quits inspection)
        # Close the stream properly to prevent "async generator ignored GeneratorExit"
        try:
            await stream.aclose()
        except Exception:
            pass  # Ignore cleanup errors
        return ("done", None)
    except Exception as e:
        return ("error", str(e))
```

**Why This Works**:
- `GeneratorExit` inherits from `BaseException`, not `Exception`, so it bypasses `except Exception` clauses
- When a task is waiting on `stream.__anext__()` and the generator is closed externally, `GeneratorExit` is raised
- By explicitly catching `GeneratorExit`, we can properly close the stream with `aclose()` before returning
- This prevents the "async generator ignored GeneratorExit" error from being logged as an unhandled exception

**Impact**:
- ✅ Eliminates "Task exception was never retrieved" warnings
- ✅ Properly cleans up resources when inspection is quit
- ✅ Prevents resource leaks in long-running sessions
- ✅ Maintains stability during multi-turn conversations
- ✅ Handles generator closure at all levels of the async generator chain

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
- [x] Add `delete_file` tool to `_workspace_copy_server.py`
- [x] Add `delete_files_batch` tool to `_workspace_copy_server.py`
- [x] Add `_is_critical_path()` helper to protect system files
- [x] Add `_is_permission_path_root()` to prevent deleting workspace roots
- [x] Add `compare_directories` tool to `_workspace_copy_server.py`
- [x] Add `compare_files` tool to `_workspace_copy_server.py`
- [x] Add `_is_text_file()` helper for diff operations

### Permission System
- [x] Update `add_context_paths()` to handle files in `_path_permission_manager.py`
- [x] Add file context path tracking in `PathPermissionManager`
- [x] Update MCP filesystem config generation for file context paths
- [x] Add `protected_paths` feature to context paths
- [x] Update `ManagedPath` dataclass with `is_file` and `protected_paths` fields
- [x] Add `is_protected()` method to `ManagedPath`
- [x] Update `get_permission()` to check protected paths first
- [x] Add deletion validation to `_validate_write_tool()`

### User Experience
- [x] Update system prompt with workspace cleanup guidance in `message_templates.py`
- [x] Add protected paths prompt to interactive mode in `cli.py`
- [x] Users can specify protected paths when adding custom context paths interactively

### Testing
- [x] Write unit tests for deletion operations (`test_delete_operations`)
- [x] Write unit tests for file context paths (`test_file_context_paths`)
- [x] Write unit tests for protected paths (`test_protected_paths`)
- [x] Write unit tests for diff tools (`test_compare_tools`)
- [x] Write unit tests for permission path root protection (`test_permission_path_root_protection`)
- [x] All 14 tests passing

### Bug Fixes
- [x] Fix async generator cleanup in `orchestrator.py` (_stream_agent_execution)
- [x] Add proper `try/except/finally` block for `chat_stream` async generator
- [x] Handle `GeneratorExit` exception when user quits inspection
- [x] Properly close async generators with `aclose()` to prevent "Task exception was never retrieved" errors

### Documentation
- [x] Write comprehensive design document (`file_deletion_and_context_files.md`)
- [x] Document protected paths feature with examples
- [x] Document permission resolution priority
- [x] Update implementation checklist
- [x] Add usage examples and migration path

## Future Enhancements

1. **Dry-Run Mode**: Preview deletions before executing
2. **Undo Capability**: Store deleted files temporarily for recovery
3. **Smart Diffs**: Use better diff algorithms (Myers, Patience)
4. **Directory Merge**: Tool to merge changes from multiple workspaces
5. **File Metadata**: Compare timestamps, permissions, sizes
6. **Diff Visualization**: Generate HTML/rich output for diffs

## References

### Issue
- [Issue #254](https://github.com/Leezekun/MassGen/issues/254) - File Deletion, Context Path Files, and Protected Paths

### Modified Files
- `massgen/backend/utils/filesystem_manager/_workspace_copy_server.py` - Deletion & diff tools
- `massgen/backend/utils/filesystem_manager/_path_permission_manager.py` - Protected paths & file context paths
- `massgen/message_templates.py` - Workspace cleanup guidance
- `massgen/tests/test_path_permission_manager.py` - Test coverage (14 tests)
- `massgen/cli.py` - Interactive protected paths prompt
- `massgen/orchestrator.py` - Async generator cleanup bug fix

### Related Documentation
- `docs/case_studies/user-context-path-support-with-copy-mcp.md`
- Python `pathlib`, `shutil`, `filecmp`, `difflib` documentation

### Test Coverage
- 14 tests total, all passing
- `test_delete_operations()` - Deletion permission validation
- `test_permission_path_root_protection()` - Workspace root protection
- `test_protected_paths()` - Protected paths enforcement
- `test_file_context_paths()` - File-based context paths
- `test_compare_tools()` - Diff tools validation