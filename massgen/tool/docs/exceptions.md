# Exception Handling Documentation

## Overview

The MassGen Tool System provides a hierarchy of custom exceptions for handling errors in tool operations. These exceptions provide clear, specific error information to help with debugging and error recovery.

**What are Tool Exceptions?**
Exceptions are Python's way of signaling that something went wrong. The Tool System defines specific exception types for different error scenarios, making it easier to understand and handle problems.

**Why use custom exceptions?**
Instead of generic errors, custom exceptions provide:
- **Specific Error Types**: Know exactly what went wrong
- **Structured Information**: Access to error details programmatically
- **Better Error Messages**: Clear, actionable error descriptions
- **Easier Debugging**: Specific exceptions help identify issues quickly

## Exception Hierarchy

```
Exception
    └── ToolException (base)
        ├── InvalidToolArgumentsException
        ├── ToolNotFoundException
        ├── ToolExecutionException
        └── CategoryNotFoundException
```

All tool exceptions inherit from `ToolException`, which inherits from Python's built-in `Exception` class.

## Exception Classes

### ToolException

**What it is**: Base exception class for all tool-related errors.

**Why use it**: Catch all tool system errors with a single except clause.

**Location**: `massgen.tool._exceptions`

```python
from massgen.tool._exceptions import ToolException

class ToolException(Exception):
    """Base exception for tool-related errors."""
```

**Usage**:

```python
from massgen.tool._exceptions import ToolException

try:
    # Any tool operation
    manager.add_tool_function(func=my_tool)
    await manager.execute_tool(tool_request)
except ToolException as e:
    # Catches all tool-specific errors
    print(f"Tool system error: {e}")
except Exception as e:
    # Catches other errors
    print(f"General error: {e}")
```

**When to use**:
- When you want to catch any tool-related error
- When specific error type doesn't matter
- For logging all tool errors uniformly

---

### InvalidToolArgumentsException

**What it is**: Raised when a tool receives invalid or malformed arguments.

**Why it happens**:
- Arguments don't match tool's parameter schema
- Required parameters are missing
- Parameter types are incorrect
- Parameter values are invalid

**Location**: `massgen.tool._exceptions`

```python
class InvalidToolArgumentsException(ToolException):
    """Raised when tool receives invalid arguments."""

    def __init__(self, error_msg: str):
        self.error_msg = error_msg
        super().__init__(self.error_msg)
```

**Attributes**:
- `error_msg`: Detailed description of what's wrong with the arguments

**Examples**:

```python
from massgen.tool._exceptions import InvalidToolArgumentsException

# Missing required parameter
try:
    await my_tool()  # Missing required 'name' parameter
except InvalidToolArgumentsException as e:
    print(f"Invalid arguments: {e.error_msg}")
    # Output: "Missing required parameter: name"

# Wrong type
try:
    await my_tool(name=123)  # Expected string, got int
except InvalidToolArgumentsException as e:
    print(f"Type error: {e.error_msg}")
    # Output: "Parameter 'name' must be string, got int"

# Invalid value
try:
    await my_tool(age=-5)  # Age can't be negative
except InvalidToolArgumentsException as e:
    print(f"Value error: {e.error_msg}")
    # Output: "Parameter 'age' must be positive"
```

**How to handle**:

```python
async def safe_tool_call(tool_func, **kwargs):
    """Safely call a tool with argument validation."""
    try:
        result = await tool_func(**kwargs)
        return result
    except InvalidToolArgumentsException as e:
        print(f"❌ Argument validation failed: {e.error_msg}")
        print(f"💡 Check parameter names, types, and values")
        # Return error result instead of crashing
        return ExecutionResult(
            output_blocks=[TextContent(data=f"Error: {e.error_msg}")]
        )
```

---

### ToolNotFoundException

**What it is**: Raised when attempting to access a tool that doesn't exist in the registry.

**Why it happens**:
- Tool was never registered
- Tool name is misspelled
- Tool was deleted
- Wrong category (disabled or non-existent)

**Location**: `massgen.tool._exceptions`

```python
class ToolNotFoundException(ToolException):
    """Raised when requested tool is not found."""

    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        super().__init__(f"Tool '{tool_name}' not found in registry")
```

**Attributes**:
- `tool_name`: The name of the tool that wasn't found

**Examples**:

```python
from massgen.tool._exceptions import ToolNotFoundException

# Tool never registered
try:
    manager.delete_tool_function("nonexistent_tool")
    # Note: delete_tool_function doesn't raise this exception
    # It's raised by other operations
except ToolNotFoundException as e:
    print(f"Tool '{e.tool_name}' doesn't exist")

# Misspelled name
try:
    manager.apply_extension_model("custom_tool__my_too", MyModel)
    # Misspelled: "my_too" instead of "my_tool"
except ToolNotFoundException as e:
    print(f"Did you mean 'custom_tool__my_tool'?")

# Tool in disabled category
manager.setup_category("experimental", "Experimental tools", enabled=False)
manager.add_tool_function(func=experimental_tool, category="experimental")

# Tool exists but category is disabled
schemas = manager.fetch_tool_schemas()
# experimental_tool won't be in schemas
```

**How to handle**:

```python
def find_tool_or_suggest(manager: ToolManager, tool_name: str):
    """Find tool or suggest alternatives."""
    try:
        # Try to find tool
        if tool_name in manager.registered_tools:
            return manager.registered_tools[tool_name]
        else:
            raise ToolNotFoundException(tool_name)
    except ToolNotFoundException as e:
        # Suggest similar tools
        all_tools = list(manager.registered_tools.keys())
        similar = [t for t in all_tools if e.tool_name.lower() in t.lower()]

        if similar:
            print(f"❌ Tool '{e.tool_name}' not found")
            print(f"💡 Did you mean one of these?")
            for tool in similar:
                print(f"   - {tool}")
        else:
            print(f"❌ No tools matching '{e.tool_name}' found")
            print(f"📋 Available tools: {all_tools}")
```

---

### ToolExecutionException

**What it is**: Raised when a tool's execution fails due to runtime errors.

**Why it happens**:
- Tool code raises an exception
- External dependency fails
- Resource unavailable (file, network, etc.)
- Timeout or cancellation

**Location**: `massgen.tool._exceptions`

```python
class ToolExecutionException(ToolException):
    """Raised when tool execution fails."""

    def __init__(self, tool_name: str, error_details: str):
        self.tool_name = tool_name
        self.error_details = error_details
        super().__init__(f"Tool '{tool_name}' execution failed: {error_details}")
```

**Attributes**:
- `tool_name`: Name of the tool that failed
- `error_details`: Description of what went wrong

**Examples**:

```python
from massgen.tool._exceptions import ToolExecutionException

# File operation failure
try:
    result = await read_file_content("/nonexistent/file.txt")
except ToolExecutionException as e:
    print(f"Tool: {e.tool_name}")
    print(f"Error: {e.error_details}")
    # Output:
    # Tool: read_file_content
    # Error: File not found: /nonexistent/file.txt

# Network failure
try:
    result = await fetch_api_data(url="https://invalid-url-xyz.com")
except ToolExecutionException as e:
    print(f"API call failed: {e.error_details}")
    # Output: API call failed: Connection timeout

# Code execution failure
try:
    result = await run_python_script("import nonexistent_module")
except ToolExecutionException as e:
    print(f"Script failed: {e.error_details}")
    # Output: Script failed: ModuleNotFoundError: No module named 'nonexistent_module'
```

**How to handle**:

```python
async def execute_with_retry(manager, tool_request, max_retries=3):
    """Execute tool with automatic retry on failure."""
    for attempt in range(max_retries):
        try:
            result = await manager.execute_tool(tool_request)
            return result

        except ToolExecutionException as e:
            if attempt < max_retries - 1:
                print(f"⚠️ Attempt {attempt + 1} failed: {e.error_details}")
                print(f"🔄 Retrying...")
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
            else:
                print(f"❌ All {max_retries} attempts failed")
                print(f"Tool: {e.tool_name}")
                print(f"Error: {e.error_details}")
                raise  # Re-raise after final attempt
```

---

### CategoryNotFoundException

**What it is**: Raised when attempting to access a tool category that doesn't exist.

**Why it happens**:
- Category was never created
- Category name is misspelled
- Category was deleted
- Trying to use reserved name "default" incorrectly

**Location**: `massgen.tool._exceptions`

```python
class CategoryNotFoundException(ToolException):
    """Raised when tool category is not found."""

    def __init__(self, category_name: str):
        self.category_name = category_name
        super().__init__(f"Category '{category_name}' not found")
```

**Attributes**:
- `category_name`: Name of the category that wasn't found

**Examples**:

```python
from massgen.tool._exceptions import CategoryNotFoundException

# Add tool to non-existent category
try:
    manager.add_tool_function(func=my_tool, category="nonexistent")
except ValueError as e:  # Note: This actually raises ValueError, not CategoryNotFoundException
    print(f"Category error: {e}")
    # Output: Category 'nonexistent' not found

# Note: CategoryNotFoundException is defined but not currently used
# The actual implementation raises ValueError instead
# This may change in future versions

# Proper category usage
manager.setup_category("my_category", "Description", enabled=True)
manager.add_tool_function(func=my_tool, category="my_category")  # ✅ Works
```

**How to handle**:

```python
def ensure_category(manager: ToolManager, category_name: str):
    """Ensure category exists, create if not."""
    if category_name in manager.tool_categories:
        print(f"✅ Category '{category_name}' already exists")
    else:
        try:
            manager.setup_category(
                category_name=category_name,
                description=f"Auto-created category: {category_name}",
                enabled=True
            )
            print(f"✅ Created category '{category_name}'")
        except Exception as e:
            print(f"❌ Failed to create category: {e}")
```

## Error Handling Patterns

### Pattern 1: Specific Exception Handling

Handle each exception type differently:

```python
from massgen.tool._exceptions import (
    InvalidToolArgumentsException,
    ToolNotFoundException,
    ToolExecutionException,
    CategoryNotFoundException
)

try:
    manager.add_tool_function(func=my_tool, category="custom")
    result = await manager.execute_tool(tool_request)

except InvalidToolArgumentsException as e:
    # Fix arguments and retry
    print(f"Invalid arguments: {e.error_msg}")
    # Prompt user for correct arguments
    corrected_args = get_user_input()
    result = await manager.execute_tool({
        "name": tool_request["name"],
        "input": corrected_args
    })

except ToolNotFoundException as e:
    # Suggest alternatives
    print(f"Tool '{e.tool_name}' not found")
    similar_tools = find_similar_tools(e.tool_name)
    print(f"Similar tools: {similar_tools}")

except ToolExecutionException as e:
    # Log error and return safe result
    logger.error(f"Tool {e.tool_name} failed: {e.error_details}")
    result = ExecutionResult(
        output_blocks=[TextContent(data=f"Error: {e.error_details}")]
    )

except CategoryNotFoundException as e:
    # Create category and retry
    print(f"Category '{e.category_name}' not found, creating...")
    manager.setup_category(e.category_name, "Auto-created", enabled=True)
    manager.add_tool_function(func=my_tool, category=e.category_name)
```

### Pattern 2: Catch-All with Logging

Log all errors uniformly:

```python
import logging
from massgen.tool._exceptions import ToolException

logger = logging.getLogger(__name__)

try:
    result = await manager.execute_tool(tool_request)

except ToolException as e:
    # Log with full context
    logger.error(
        "Tool operation failed",
        exc_info=True,
        extra={
            "tool_request": tool_request,
            "exception_type": type(e).__name__,
            "exception_message": str(e)
        }
    )
    # Return error result
    result = ExecutionResult(
        output_blocks=[TextContent(data=f"Error: {str(e)}")]
    )
```

### Pattern 3: Retry with Backoff

Automatically retry failed operations:

```python
import asyncio
from massgen.tool._exceptions import ToolExecutionException

async def execute_with_backoff(manager, tool_request, max_retries=3):
    """Execute with exponential backoff on failure."""
    for attempt in range(max_retries):
        try:
            result = await manager.execute_tool(tool_request)
            return result

        except ToolExecutionException as e:
            wait_time = 2 ** attempt  # 1s, 2s, 4s...

            if attempt < max_retries - 1:
                logger.warning(
                    f"Tool execution failed (attempt {attempt + 1}/{max_retries}): {e.error_details}"
                )
                logger.info(f"Retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Tool execution failed after {max_retries} attempts")
                raise
```

### Pattern 4: Graceful Degradation

Provide fallback behavior:

```python
from massgen.tool._exceptions import ToolNotFoundException

async def execute_with_fallback(manager, primary_tool, fallback_tool, args):
    """Try primary tool, fall back to alternative if not found."""
    try:
        # Try primary tool
        result = await manager.execute_tool({
            "name": primary_tool,
            "input": args
        })
        return result

    except ToolNotFoundException:
        logger.warning(f"Primary tool '{primary_tool}' not found, using fallback")

        # Try fallback
        try:
            result = await manager.execute_tool({
                "name": fallback_tool,
                "input": args
            })
            return result

        except ToolNotFoundException:
            logger.error(f"Neither '{primary_tool}' nor '{fallback_tool}' available")
            # Return error result
            return ExecutionResult(
                output_blocks=[TextContent(data="No suitable tool available")]
            )
```

### Pattern 5: Validation Before Execution

Prevent errors proactively:

```python
from massgen.tool._exceptions import InvalidToolArgumentsException

def validate_tool_request(manager, tool_request):
    """Validate tool request before execution."""
    tool_name = tool_request.get("name")
    tool_input = tool_request.get("input", {})

    # Check tool exists
    if tool_name not in manager.registered_tools:
        raise ToolNotFoundException(tool_name)

    # Get tool schema
    tool_entry = manager.registered_tools[tool_name]
    schema = tool_entry.schema_def["function"]["parameters"]

    # Check required parameters
    required = schema.get("required", [])
    missing = [p for p in required if p not in tool_input]

    if missing:
        raise InvalidToolArgumentsException(
            f"Missing required parameters: {', '.join(missing)}"
        )

    # Check parameter types
    properties = schema.get("properties", {})
    for param_name, param_value in tool_input.items():
        if param_name in properties:
            expected_type = properties[param_name].get("type")
            actual_type = type(param_value).__name__

            # Simple type checking (can be more sophisticated)
            if expected_type == "string" and not isinstance(param_value, str):
                raise InvalidToolArgumentsException(
                    f"Parameter '{param_name}' must be string, got {actual_type}"
                )

    return True

# Usage
try:
    validate_tool_request(manager, tool_request)
    result = await manager.execute_tool(tool_request)
except ToolException as e:
    print(f"Validation or execution failed: {e}")
```

## Best Practices

### 1. Be Specific

Catch specific exceptions when you can handle them differently:

```python
# ❌ Too broad
try:
    result = await manager.execute_tool(tool_request)
except Exception as e:
    print("Something went wrong")

# ✅ Specific handling
try:
    result = await manager.execute_tool(tool_request)
except InvalidToolArgumentsException as e:
    fix_arguments(e.error_msg)
except ToolNotFoundException as e:
    suggest_alternatives(e.tool_name)
except ToolExecutionException as e:
    log_and_retry(e.tool_name, e.error_details)
```

### 2. Preserve Stack Traces

Use `exc_info=True` for debugging:

```python
import logging

try:
    result = await manager.execute_tool(tool_request)
except ToolException as e:
    # Logs full stack trace
    logger.error("Tool execution failed", exc_info=True)
```

### 3. Provide Context

Add context to error messages:

```python
try:
    result = await manager.execute_tool(tool_request)
except ToolExecutionException as e:
    # Add context
    enhanced_message = (
        f"Failed to execute tool for task '{task_id}'\n"
        f"Tool: {e.tool_name}\n"
        f"Error: {e.error_details}\n"
        f"Request: {tool_request}"
    )
    logger.error(enhanced_message)
```

### 4. Don't Swallow Exceptions

Always handle or re-raise:

```python
# ❌ Silently ignores errors
try:
    result = await manager.execute_tool(tool_request)
except ToolException:
    pass  # Bad! Error is lost

# ✅ Log and handle
try:
    result = await manager.execute_tool(tool_request)
except ToolException as e:
    logger.error(f"Tool failed: {e}")
    result = ExecutionResult(
        output_blocks=[TextContent(data=f"Error: {e}")]
    )
```

### 5. Use Finally for Cleanup

Ensure resources are cleaned up:

```python
resource = None
try:
    resource = acquire_resource()
    result = await manager.execute_tool(tool_request)
except ToolException as e:
    logger.error(f"Tool failed: {e}")
    raise
finally:
    if resource:
        resource.cleanup()
```

## Complete Example

```python
import logging
import asyncio
from typing import Optional
from massgen.tool import ToolManager, ExecutionResult, TextContent
from massgen.tool._exceptions import (
    ToolException,
    InvalidToolArgumentsException,
    ToolNotFoundException,
    ToolExecutionException,
    CategoryNotFoundException
)

logger = logging.getLogger(__name__)

class RobustToolExecutor:
    """Robust tool executor with comprehensive error handling."""

    def __init__(self, manager: ToolManager):
        self.manager = manager
        self.retry_count = 3
        self.retry_delay = 1.0

    async def execute(
        self,
        tool_request: dict,
        fallback_result: Optional[ExecutionResult] = None
    ) -> ExecutionResult:
        """Execute tool with robust error handling."""

        # Validate request
        if not self._validate_request(tool_request):
            return ExecutionResult(
                output_blocks=[TextContent(data="Invalid tool request format")]
            )

        # Try execution with retry
        for attempt in range(self.retry_count):
            try:
                result = await self._execute_with_timeout(tool_request)
                logger.info(f"Tool execution succeeded on attempt {attempt + 1}")
                return result

            except InvalidToolArgumentsException as e:
                logger.error(f"Invalid arguments: {e.error_msg}")
                return ExecutionResult(
                    output_blocks=[TextContent(data=f"Argument error: {e.error_msg}")]
                )

            except ToolNotFoundException as e:
                logger.error(f"Tool not found: {e.tool_name}")
                alternatives = self._find_similar_tools(e.tool_name)
                msg = f"Tool '{e.tool_name}' not found."
                if alternatives:
                    msg += f" Similar tools: {', '.join(alternatives)}"
                return ExecutionResult(
                    output_blocks=[TextContent(data=msg)]
                )

            except ToolExecutionException as e:
                if attempt < self.retry_count - 1:
                    logger.warning(
                        f"Execution failed (attempt {attempt + 1}): {e.error_details}"
                    )
                    await asyncio.sleep(self.retry_delay * (2 ** attempt))
                else:
                    logger.error(f"Execution failed after {self.retry_count} attempts")
                    if fallback_result:
                        logger.info("Using fallback result")
                        return fallback_result
                    return ExecutionResult(
                        output_blocks=[TextContent(data=f"Execution error: {e.error_details}")]
                    )

            except Exception as e:
                logger.exception("Unexpected error during tool execution")
                return ExecutionResult(
                    output_blocks=[TextContent(data=f"Unexpected error: {str(e)}")]
                )

    async def _execute_with_timeout(
        self,
        tool_request: dict,
        timeout: float = 30.0
    ) -> ExecutionResult:
        """Execute with timeout."""
        try:
            result = await asyncio.wait_for(
                self.manager.execute_tool(tool_request).__anext__(),
                timeout=timeout
            )
            return result
        except asyncio.TimeoutError:
            raise ToolExecutionException(
                tool_request["name"],
                f"Execution timed out after {timeout} seconds"
            )

    def _validate_request(self, tool_request: dict) -> bool:
        """Validate tool request structure."""
        return (
            isinstance(tool_request, dict) and
            "name" in tool_request and
            isinstance(tool_request.get("input", {}), dict)
        )

    def _find_similar_tools(self, tool_name: str) -> list:
        """Find similar tool names."""
        all_tools = list(self.manager.registered_tools.keys())
        similar = [
            t for t in all_tools
            if tool_name.lower() in t.lower() or t.lower() in tool_name.lower()
        ]
        return similar[:3]  # Return top 3

# Usage
async def main():
    manager = ToolManager()
    executor = RobustToolExecutor(manager)

    # Execute with full error handling
    result = await executor.execute({
        "name": "my_tool",
        "input": {"arg1": "value1"}
    })

    print(result.output_blocks[0].data)

if __name__ == "__main__":
    asyncio.run(main())
```

---

For more information, see:
- [ToolManager Documentation](manager.md)
- [ExecutionResult Documentation](execution_results.md)
- [Built-in Tools Guide](builtin_tools.md)
