# Built-in Tools Guide

## Overview

MassGen provides a comprehensive set of built-in tools that give AI agents capabilities for code execution, file operations, and multimedia processing. These tools are production-ready, well-tested, and designed to integrate seamlessly with the Tool System.

## Tool Categories

Built-in tools are organized into several categories:

- **Code Executors**: Run Python and shell scripts safely
- **File Handlers**: Read, write, and modify files
- **Workflow Toolkits**: Specialized tools for agent coordination

## Code Execution Tools

### run_python_script

**What it does**: Executes Python code in an isolated subprocess environment. The code runs in a temporary file that's automatically cleaned up after execution.

**Why use it**: Allows agents to run Python code for calculations, data processing, or any task that requires Python. Isolation prevents interference with the main process.

**Location**: `massgen.tool._code_executors._python_executor`

#### Parameters

- `source_code` (required): Python code to execute as a string
- `max_duration` (optional): Maximum execution time in seconds (default: 300)
- `**extra_kwargs`: Additional keyword arguments (currently unused, reserved for future use)

#### Returns

ExecutionResult containing:
- `<exit_code>`: Process exit code (0 for success)
- `<stdout>`: Standard output from the script
- `<stderr>`: Standard error output

#### Security Features

- Runs in isolated subprocess
- Timeout protection (default 300 seconds)
- Temporary file cleanup
- No access to parent process environment

#### Examples

**Basic Calculation**:

```python
from massgen.tool import run_python_script

# Simple calculation
code = """
result = 2 + 2
print(f"Result: {result}")
"""

result = await run_python_script(source_code=code)
print(result.output_blocks[0].data)
# Output:
# <exit_code>0</exit_code>
# <stdout>Result: 4
# </stdout>
# <stderr></stderr>
```

**Data Processing**:

```python
# Process a list
code = """
data = [1, 2, 3, 4, 5]
squared = [x**2 for x in data]
print(f"Squared: {squared}")
print(f"Sum: {sum(squared)}")
"""

result = await run_python_script(source_code=code)
# Output includes squared values and sum
```

**With External Libraries**:

```python
# Use installed packages
code = """
import json
import math

data = {"values": [1, 4, 9, 16, 25]}
sqrt_values = [math.sqrt(x) for x in data["values"]]

output = {"original": data["values"], "sqrt": sqrt_values}
print(json.dumps(output, indent=2))
"""

result = await run_python_script(source_code=code)
```

**File Operations in Script**:

```python
# Create and read a file
code = """
# Write to file
with open('/tmp/test.txt', 'w') as f:
    f.write('Hello from Python!')

# Read back
with open('/tmp/test.txt', 'r') as f:
    content = f.read()
    print(f"File content: {content}")
"""

result = await run_python_script(source_code=code)
```

**Error Handling**:

```python
# Code with error
code = """
def divide(a, b):
    return a / b

result = divide(10, 0)  # Division by zero
print(f"Result: {result}")
"""

result = await run_python_script(source_code=code)
print(result.output_blocks[0].data)
# Output includes:
# <exit_code>1</exit_code>
# <stderr>ZeroDivisionError: division by zero</stderr>
```

**Timeout Example**:

```python
# Long-running script with timeout
code = """
import time
for i in range(100):
    time.sleep(1)
    print(f"Second {i+1}")
"""

result = await run_python_script(
    source_code=code,
    max_duration=5.0  # Stop after 5 seconds
)
# Will show timeout error in stderr
```

#### Best Practices

1. **Always Set Timeout**: Prevent runaway scripts
2. **Print Results**: Use `print()` to capture output
3. **Handle Errors**: Check exit_code and stderr
4. **Clean Code**: Test code before running in production
5. **Limit External Dependencies**: Not all packages may be available

#### Common Issues

**Import Errors**:
```python
# Problem: Missing package
code = "import nonexistent_package"
# Solution: Check package is installed in environment
```

**No Output**:
```python
# Problem: Forgot to print
code = "result = 2 + 2"  # No print statement
# Solution: Add print()
code = "result = 2 + 2; print(result)"
```

**Timeout Too Short**:
```python
# Problem: Complex operation needs more time
result = await run_python_script(code, max_duration=1.0)  # Too short
# Solution: Increase timeout
result = await run_python_script(code, max_duration=60.0)  # Better
```

---

### run_shell_script

**What it does**: Executes shell commands in a subprocess. Similar to run_python_script but for shell commands.

**Why use it**: Allows agents to run system commands, scripts, or CLI tools.

**Location**: `massgen.tool._code_executors._shell_executor`

**Note**: Implementation details similar to run_python_script. Use with caution due to security implications of shell access.

## File Operation Tools

### read_file_content

**What it does**: Reads the contents of a file with optional line range specification. Can read entire files or specific line ranges, including negative indices for reading from the end.

**Why use it**: Essential for agents that need to examine files, load data, or read configuration. Supports partial reads for large files.

**Location**: `massgen.tool._file_handlers._file_operations`

#### Parameters

- `target_path` (required): Absolute or relative path to the file
- `line_range` (optional): `[start, end]` line numbers (1-based, inclusive)
  - Positive numbers: Count from beginning (1 is first line)
  - Negative numbers: Count from end (-1 is last line)

#### Returns

ExecutionResult containing:
- File content (with line numbers if range specified)
- Error message if file doesn't exist or isn't readable

#### Examples

**Read Entire File**:

```python
from massgen.tool import read_file_content

# Read complete file
result = await read_file_content(target_path="config.json")
print(result.output_blocks[0].data)
# Output: Content of config.json:
# ```
# {
#   "setting1": "value1",
#   "setting2": "value2"
# }
# ```
```

**Read Specific Lines**:

```python
# Read lines 10-20
result = await read_file_content(
    target_path="large_file.txt",
    line_range=[10, 20]
)
# Output shows lines 10-20 with line numbers
# Content of large_file.txt (lines 10-20):
# ```
#   10│ Line 10 content
#   11│ Line 11 content
#   ...
#   20│ Line 20 content
# ```
```

**Read Last N Lines**:

```python
# Read last 100 lines
result = await read_file_content(
    target_path="app.log",
    line_range=[-100, -1]
)
# Shows last 100 lines of the log file
```

**Read First N Lines**:

```python
# Read first 50 lines
result = await read_file_content(
    target_path="data.csv",
    line_range=[1, 50]
)
```

**Error Handling**:

```python
# File doesn't exist
result = await read_file_content(target_path="nonexistent.txt")
print(result.output_blocks[0].data)
# Output: Error: File 'nonexistent.txt' does not exist.

# Not a file (is a directory)
result = await read_file_content(target_path="/etc")
# Output: Error: Path '/etc' is not a file.

# Invalid line range
result = await read_file_content(
    target_path="small_file.txt",
    line_range=[100, 200]  # File only has 50 lines
)
# Output: Error: Invalid line range [100, 200] for file with 50 lines.
```

#### Best Practices

1. **Check File Exists**: Handle error results gracefully
2. **Use Line Ranges**: For large files, avoid reading entire content
3. **Absolute Paths**: Use absolute paths when possible
4. **UTF-8 Encoding**: Assumes UTF-8 encoding (most common)

---

### save_file_content

**What it does**: Writes content to a file, optionally creating parent directories. Overwrites existing files.

**Why use it**: Allows agents to create files, save results, write reports, or persist data.

**Location**: `massgen.tool._file_handlers._file_operations`

#### Parameters

- `target_path` (required): Path where file will be saved
- `file_content` (required): Content to write (string)
- `create_dirs` (optional): Create parent directories if they don't exist (default: True)

#### Returns

ExecutionResult containing:
- Success message with character count
- Error message if write fails

#### Examples

**Simple Write**:

```python
from massgen.tool import save_file_content

# Write a text file
result = await save_file_content(
    target_path="output.txt",
    file_content="Hello, World!"
)
print(result.output_blocks[0].data)
# Output: Successfully wrote 13 characters to output.txt
```

**Write JSON**:

```python
import json

data = {"name": "Alice", "age": 30, "city": "NYC"}
content = json.dumps(data, indent=2)

result = await save_file_content(
    target_path="data.json",
    file_content=content
)
```

**Write with Directory Creation**:

```python
# Create nested directories automatically
result = await save_file_content(
    target_path="reports/2024/march/summary.txt",
    file_content="Monthly summary...",
    create_dirs=True  # Creates reports/2024/march/ if needed
)
```

**Overwrite Existing File**:

```python
# Overwrites without warning
result = await save_file_content(
    target_path="existing.txt",
    file_content="New content"  # Old content is lost
)
```

**Error Handling**:

```python
# Permission denied
result = await save_file_content(
    target_path="/root/protected.txt",
    file_content="content"
)
# Output: Error writing file: Permission denied

# Cannot create directory
result = await save_file_content(
    target_path="/readonly/file.txt",
    file_content="content",
    create_dirs=True
)
# Output: Error writing file: Cannot create directory
```

#### Best Practices

1. **Check Results**: Verify success message
2. **Use create_dirs**: Usually want to create parent directories
3. **Backup Important Files**: No confirmation before overwrite
4. **Validate Content**: Ensure content is correct before writing
5. **UTF-8 Safe**: Ensure content is UTF-8 compatible

#### Common Use Cases

**Save Analysis Results**:

```python
results = analyze_data(dataset)
report = format_report(results)

await save_file_content(
    target_path=f"reports/analysis_{datetime.now().date()}.txt",
    file_content=report
)
```

**Configuration Files**:

```python
config = {
    "api_key": "secret",
    "endpoint": "https://api.example.com",
    "timeout": 30
}

await save_file_content(
    target_path="config.json",
    file_content=json.dumps(config, indent=2)
)
```

**Log Files**:

```python
log_entry = f"[{datetime.now()}] Operation completed\n"

# Use append_file_content instead for logs
await append_file_content(
    target_path="app.log",
    additional_content=log_entry
)
```

---

### append_file_content

**What it does**: Appends content to the end of a file, or inserts content at a specific line position. Does not overwrite existing content.

**Why use it**: Perfect for log files, incremental data collection, or adding to existing documents without losing original content.

**Location**: `massgen.tool._file_handlers._file_operations`

#### Parameters

- `target_path` (required): Path to the file
- `additional_content` (required): Content to append or insert
- `line_position` (optional): Line number to insert at (1-based). If None, appends to end

#### Returns

ExecutionResult containing:
- Success message with character count and operation type
- Error message if operation fails

#### Examples

**Append to End**:

```python
from massgen.tool import append_file_content

# Append to log file
result = await append_file_content(
    target_path="app.log",
    additional_content="[2024-03-15] New log entry\n"
)
# Output: Successfully appended 30 characters to app.log
```

**Insert at Specific Line**:

```python
# Insert at line 5
result = await append_file_content(
    target_path="document.txt",
    additional_content="New paragraph here\n",
    line_position=5
)
# Output: Successfully inserted content at line 5 in document.txt
```

**Continuous Logging**:

```python
# Log multiple entries
log_messages = [
    "[INFO] Application started",
    "[DEBUG] Loading configuration",
    "[INFO] Server listening on port 8000"
]

for msg in log_messages:
    await append_file_content(
        target_path="server.log",
        additional_content=f"{msg}\n"
    )
```

**Insert Header**:

```python
# Insert at beginning of file
header = "# Report Generated on 2024-03-15\n\n"

await append_file_content(
    target_path="report.md",
    additional_content=header,
    line_position=1  # Insert at first line
)
```

**Error Handling**:

```python
# File doesn't exist
result = await append_file_content(
    target_path="nonexistent.txt",
    additional_content="content"
)
# Output: Error: File 'nonexistent.txt' does not exist.

# Invalid line position
result = await append_file_content(
    target_path="small_file.txt",  # 10 lines
    additional_content="content",
    line_position=100  # Too large
)
# Output: Error: Invalid line position 100 for file with 10 lines.
```

#### Best Practices

1. **Include Newlines**: Add `\n` to keep formatting correct
2. **Timestamp Logs**: Include timestamps in log entries
3. **Atomic Operations**: Each append is a separate file operation
4. **Line Position Validation**: Check file length before inserting
5. **Use for Logs**: Perfect for append-only log files

#### Common Use Cases

**Activity Logging**:

```python
async def log_activity(activity: str):
    timestamp = datetime.now().isoformat()
    entry = f"[{timestamp}] {activity}\n"

    await append_file_content(
        target_path="activity.log",
        additional_content=entry
    )

# Usage
await log_activity("User logged in")
await log_activity("File uploaded")
await log_activity("Report generated")
```

**Data Collection**:

```python
# Collect measurements over time
async def record_measurement(value: float):
    entry = f"{datetime.now()},{value}\n"

    await append_file_content(
        target_path="measurements.csv",
        additional_content=entry
    )
```

**Document Building**:

```python
# Build report incrementally
await save_file_content("report.md", "# Monthly Report\n\n")

await append_file_content("report.md", "## Sales Summary\n")
await append_file_content("report.md", sales_summary + "\n\n")

await append_file_content("report.md", "## User Statistics\n")
await append_file_content("report.md", user_stats + "\n\n")
```

## Integration with ToolManager

All built-in tools can be registered with ToolManager:

```python
from massgen.tool import ToolManager

manager = ToolManager()

# Register by name (auto-discovery)
manager.add_tool_function(func="run_python_script")
manager.add_tool_function(func="read_file_content")
manager.add_tool_function(func="save_file_content")
manager.add_tool_function(func="append_file_content")

# Register with custom configuration
manager.add_tool_function(
    func="run_python_script",
    preset_args={"max_duration": 60.0},  # Custom timeout
    description="Execute Python code with 60-second timeout"
)
```

## Security Considerations

### Code Execution

1. **Untrusted Code**: Never execute untrusted user code without review
2. **Timeouts**: Always set reasonable timeouts
3. **Resource Limits**: Consider memory and CPU limits
4. **Sandboxing**: Code runs in subprocess but shares system access

### File Operations

1. **Path Validation**: Validate file paths before operations
2. **Permission Checks**: Ensure agent has necessary permissions
3. **Path Traversal**: Be careful with user-provided paths (../)
4. **Overwrite Protection**: save_file_content overwrites without confirmation
5. **Sensitive Data**: Don't write secrets or credentials to files

### Best Practices

```python
# Validate paths
import os

def is_safe_path(base_path: str, user_path: str) -> bool:
    """Check if user_path is within base_path."""
    abs_base = os.path.abspath(base_path)
    abs_user = os.path.abspath(os.path.join(base_path, user_path))
    return abs_user.startswith(abs_base)

# Use with file operations
if is_safe_path("/safe/directory", user_provided_path):
    result = await read_file_content(user_provided_path)
else:
    print("Error: Path outside allowed directory")
```

## Performance Tips

### File Operations

1. **Batch Writes**: Combine multiple writes into one
2. **Line Ranges**: Use line_range for large files
3. **Stream Large Files**: Process in chunks if possible
4. **Cache Reads**: Cache frequently read files

### Code Execution

1. **Minimize Execution**: Cache results when possible
2. **Optimize Code**: Profile and optimize Python scripts
3. **Parallel Execution**: Use async for multiple operations
4. **Resource Monitoring**: Monitor memory and CPU usage

---

For more information, see:
- [ToolManager Documentation](manager.md)
- [ExecutionResult Documentation](execution_results.md)
- [Workflow Toolkits](workflow_toolkits.md)
