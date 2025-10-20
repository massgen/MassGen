# ToolManager Documentation

## Overview

The `ToolManager` class is the central component of the MassGen Tool System. It handles all aspects of tool lifecycle management including registration, schema generation, category management, and execution orchestration.

## Class Overview

```python
from massgen.tool import ToolManager

class ToolManager:
    """Manager class for tool registration and execution.

    Provides methods for:
    - Tool registration: add_tool_function
    - Tool removal: delete_tool_function
    - Category management: setup_category, modify_categories, delete_categories
    - Schema retrieval: fetch_tool_schemas
    - Tool execution: execute_tool
    """
```

## Initialization

### \_\_init\_\_()

**What it does**: Creates a new ToolManager instance with empty tool and category registries.

**Why you need it**: The ToolManager is your entry point to the entire tool system. You need an instance to register tools, manage categories, and execute tools.

```python
from massgen.tool import ToolManager

# Create a new tool manager
manager = ToolManager()

# Ready to register tools and categories
manager.setup_category("utilities", "Utility tools", enabled=True)
```

**Internal State**:
- `registered_tools`: Dictionary mapping tool names to RegisteredToolEntry objects
- `tool_categories`: Dictionary mapping category names to ToolCategory objects

## Category Management

### setup_category()

**What it does**: Creates a new category for organizing related tools. Categories can be enabled or disabled as a group, making it easy to control which tools are available.

**Why you need it**: As you add more tools, organizing them into categories makes management easier. You can enable/disable entire groups of tools based on the task at hand.

**Parameters**:
- `category_name` (required): Unique identifier for the category
- `description` (required): Human-readable description of what tools in this category do
- `enabled` (optional): Whether tools in this category are initially active (default: False)
- `usage_hints` (optional): Guidelines for when to use these tools

**Returns**: None (raises ValueError if category already exists or name is "default")

```python
# Basic category creation
manager.setup_category(
    category_name="data_analysis",
    description="Tools for analyzing and processing data",
    enabled=True
)

# Category with usage hints
manager.setup_category(
    category_name="visualization",
    description="Chart and graph generation tools",
    enabled=False,  # Disabled by default
    usage_hints="""
    Use these tools when you need to:
    - Create charts from data
    - Generate visual reports
    - Export images for presentations
    """
)

# Error: Reserved name
try:
    manager.setup_category("default", "Default category", enabled=True)
except ValueError as e:
    print(f"Error: {e}")  # Cannot use reserved name 'default'

# Error: Duplicate category
manager.setup_category("math", "Math tools", enabled=True)
try:
    manager.setup_category("math", "Duplicate", enabled=True)
except ValueError as e:
    print(f"Error: {e}")  # Category 'math' already exists
```

### modify_categories()

**What it does**: Enable or disable entire categories of tools at once. This is useful for dynamically controlling which tools are available based on context or user permissions.

**Why you need it**: Different tasks require different tools. Instead of managing tools individually, you can enable/disable entire categories to match your current needs.

**Parameters**:
- `category_list` (required): List of category names to modify
- `enabled` (required): True to enable, False to disable

**Returns**: None

**Note**: The "default" category cannot be disabled and will be silently ignored.

```python
# Enable multiple categories
manager.modify_categories(
    category_list=["data_analysis", "visualization"],
    enabled=True
)

# Disable a category
manager.modify_categories(
    category_list=["admin_tools"],
    enabled=False
)

# Trying to disable default category (silently ignored)
manager.modify_categories(["default"], enabled=False)
# Default category remains active

# Enable non-existent category (silently ignored)
manager.modify_categories(["nonexistent"], enabled=True)
# No error, but nothing happens
```

### delete_categories()

**What it does**: Permanently removes categories and all tools registered in those categories. This is destructive and cannot be undone.

**Why you need it**: When you no longer need a set of tools, you can clean up by removing the entire category. This keeps your tool registry organized.

**Parameters**:
- `category_list` (required): List of category names to delete (or single string)

**Returns**: None (raises ValueError if trying to delete "default")

```python
# Delete single category
manager.delete_categories("temporary_tools")

# Delete multiple categories
manager.delete_categories(["experiment", "debug_utils"])

# Alternative: pass string instead of list
manager.delete_categories("old_category")

# Error: Cannot delete default category
try:
    manager.delete_categories("default")
except ValueError as e:
    print(f"Error: {e}")  # Cannot remove the default category

# Tools in deleted categories are also removed
manager.setup_category("temp", "Temporary", enabled=True)
manager.add_tool_function(func=my_tool, category="temp")
manager.delete_categories("temp")
# my_tool is now gone from registered_tools
```

### fetch_category_hints()

**What it does**: Collects usage hints from all enabled categories and formats them as a markdown string. This is useful for providing context-aware guidance to AI agents.

**Why you need it**: When tools are organized with usage hints, agents can make better decisions about which tools to use. This method aggregates all relevant hints.

**Returns**: String containing formatted hints from all enabled categories

```python
# Set up categories with hints
manager.setup_category(
    "file_ops",
    "File operations",
    enabled=True,
    usage_hints="Use for reading, writing, and managing files"
)

manager.setup_category(
    "network",
    "Network tools",
    enabled=True,
    usage_hints="Use for HTTP requests and API calls"
)

# Get combined hints
hints = manager.fetch_category_hints()
print(hints)
# Output:
# ## file_ops Tools
# Use for reading, writing, and managing files
#
# ## network Tools
# Use for HTTP requests and API calls

# Disabled categories are not included
manager.modify_categories(["network"], enabled=False)
hints = manager.fetch_category_hints()
# Only file_ops hints are included
```

## Tool Registration

### add_tool_function()

**What it does**: Registers a Python function as a tool that AI agents can use. This is the main method for adding capabilities to your system. It automatically generates JSON schemas from function signatures and docstrings.

**Why you need it**: This is how you add new capabilities to your agents. Any Python function can become a tool with automatic schema generation, type checking, and documentation.

**Parameters**:
- `path` (optional): Path to Python file or module name. If None, use `func` parameter
- `func` (required if path is None): Function to register (callable or function name string)
- `category` (optional): Category name (default: "default")
- `preset_args` (optional): Arguments to preset and hide from schema
- `description` (optional): Override description from docstring
- `tool_schema` (optional): Manually provide JSON schema instead of auto-generation
- `include_full_desc` (optional): Include long description from docstring (default: True)
- `allow_var_args` (optional): Include *args in schema (default: False)
- `allow_var_kwargs` (optional): Include **kwargs in schema (default: False)
- `post_processor` (optional): Function to transform results before returning

**Returns**: None (raises ValueError on errors)

**Important**: Custom tools (category != "builtin") are automatically prefixed with `custom_tool__`

```python
# Example 1: Register a simple function
async def greet(name: str, greeting: str = "Hello") -> ExecutionResult:
    """Greet someone by name.

    Args:
        name: Person's name
        greeting: Greeting phrase

    Returns:
        ExecutionResult with greeting message
    """
    return ExecutionResult(
        output_blocks=[TextContent(data=f"{greeting}, {name}!")]
    )

manager.add_tool_function(func=greet)
# Registered as "custom_tool__greet"

# Example 2: Load from file path
manager.add_tool_function(
    path="my_tools/analyzer.py",
    func="analyze_data",
    category="analysis"
)

# Example 3: Load from module
manager.add_tool_function(
    path="massgen.tool._code_executors",
    func="run_python_script",
    category="execution"
)

# Example 4: Load built-in by name
manager.add_tool_function(func="run_python_script")

# Example 5: With preset arguments
manager.add_tool_function(
    func=api_call,
    preset_args={
        "api_key": os.getenv("API_KEY"),  # Hidden from schema
        "timeout": 30,
        "base_url": "https://api.example.com"
    }
)

# Example 6: Custom schema
custom_schema = {
    "type": "function",
    "function": {
        "name": "my_tool",
        "description": "Custom tool",
        "parameters": {
            "type": "object",
            "properties": {
                "input": {"type": "string"}
            },
            "required": ["input"]
        }
    }
}

manager.add_tool_function(
    func=my_function,
    tool_schema=custom_schema
)

# Example 7: With post-processor
def redact_sensitive_data(request: dict, result: ExecutionResult) -> ExecutionResult:
    """Remove API keys and tokens from output."""
    for block in result.output_blocks:
        if isinstance(block, TextContent):
            block.data = re.sub(r'token=\w+', 'token=***', block.data)
    return result

manager.add_tool_function(
    func=fetch_data,
    post_processor=redact_sensitive_data
)

# Example 8: Override description
manager.add_tool_function(
    func=complex_function,
    description="Simplified description for agents"
)

# Example 9: Allow **kwargs
def flexible_function(**options):
    """Function with flexible options."""
    pass

manager.add_tool_function(
    func=flexible_function,
    allow_var_kwargs=True  # Include **options in schema
)

# Error handling
try:
    manager.add_tool_function(func=my_tool)  # Registers successfully
    manager.add_tool_function(func=my_tool)  # Error: already registered
except ValueError as e:
    print(f"Error: {e}")  # Tool 'custom_tool__my_tool' is already registered

try:
    manager.add_tool_function(func=some_function, category="nonexistent")
except ValueError as e:
    print(f"Error: {e}")  # Category 'nonexistent' not found
```

**Schema Generation Details**:

The tool automatically extracts:
- Function name → `tool_name`
- Docstring short description → `description`
- Docstring long description → extended `description` (if `include_full_desc=True`)
- Parameter type hints → parameter types in schema
- Parameter docstrings → parameter descriptions
- Default values → optional parameters in schema

Example:

```python
from typing import List, Optional

async def analyze_sentiment(
    text: str,
    language: str = "en",
    include_score: bool = True,
    keywords: Optional[List[str]] = None
) -> ExecutionResult:
    """Analyze text sentiment.

    Performs sentiment analysis on the provided text,
    returning positive/negative/neutral classification.

    Args:
        text: Text to analyze
        language: Language code (ISO 639-1)
        include_score: Whether to include confidence score
        keywords: Optional keywords to focus on

    Returns:
        ExecutionResult with sentiment classification
    """
    # Implementation
    ...

# Generated schema:
{
    "type": "function",
    "function": {
        "name": "custom_tool__analyze_sentiment",
        "description": "Analyze text sentiment.\n\nPerforms sentiment analysis...",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to analyze"
                },
                "language": {
                    "type": "string",
                    "description": "Language code (ISO 639-1)",
                    "default": "en"
                },
                "include_score": {
                    "type": "boolean",
                    "description": "Whether to include confidence score",
                    "default": true
                },
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional keywords to focus on"
                }
            },
            "required": ["text"]
        }
    }
}
```

### delete_tool_function()

**What it does**: Removes a registered tool from the system. The tool will no longer appear in schemas or be available for execution.

**Why you need it**: When tools become outdated or are no longer needed, you can remove them to keep the tool registry clean and prevent agents from using deprecated functionality.

**Parameters**:
- `tool_name` (required): Exact name of the tool to remove (including any prefixes)

**Returns**: None (silently succeeds even if tool doesn't exist)

```python
# Remove a custom tool
manager.add_tool_function(func=my_tool)
manager.delete_tool_function("custom_tool__my_tool")

# Remove a built-in tool
manager.add_tool_function(func="run_shell_script")
manager.delete_tool_function("run_shell_script")

# No error if tool doesn't exist
manager.delete_tool_function("nonexistent_tool")  # Silently succeeds

# Verify removal
schemas = manager.fetch_tool_schemas()
tool_names = [s['function']['name'] for s in schemas]
assert "custom_tool__my_tool" not in tool_names
```

## Schema Management

### fetch_tool_schemas()

**What it does**: Generates JSON schemas for all active tools. Returns only tools in enabled categories plus any tools in the "default" category.

**Why you need it**: AI agents need schemas to understand what tools are available and how to use them. This method provides the schemas in a format compatible with function calling APIs.

**Returns**: List of dictionaries, each containing a JSON schema for one tool

```python
# Get all active tool schemas
schemas = manager.fetch_tool_schemas()

# Print tool names
for schema in schemas:
    print(f"Tool: {schema['function']['name']}")
    print(f"Description: {schema['function'].get('description', 'N/A')}")

# Example output format
[
    {
        "type": "function",
        "function": {
            "name": "custom_tool__process_data",
            "description": "Process and transform data",
            "parameters": {
                "type": "object",
                "properties": {
                    "data": {"type": "array", "description": "Input data"},
                    "operation": {"type": "string", "description": "Operation to perform"}
                },
                "required": ["data", "operation"]
            }
        }
    },
    # ... more tool schemas
]

# Only enabled categories are included
manager.setup_category("tools", "My tools", enabled=False)
manager.add_tool_function(func=my_tool, category="tools")

schemas = manager.fetch_tool_schemas()
# my_tool is NOT in schemas (category disabled)

manager.modify_categories(["tools"], enabled=True)
schemas = manager.fetch_tool_schemas()
# my_tool IS in schemas (category enabled)

# Default category always included
manager.add_tool_function(func=essential_tool, category="default")
schemas = manager.fetch_tool_schemas()
# essential_tool is ALWAYS in schemas
```

### apply_extension_model()

**What it does**: Extends a tool's schema by merging in additional parameters from a Pydantic model. This allows you to dynamically add new parameters without modifying the original function.

**Why you need it**: Sometimes you need to add configuration options or advanced parameters to existing tools without changing their code. Extension models provide a clean way to augment tool schemas.

**Parameters**:
- `tool_name` (required): Name of the tool to extend
- `model_class` (required): Pydantic BaseModel class with additional parameters

**Returns**: None (raises ValueError if tool not found or model is invalid)

**Important**: Extension properties cannot conflict with existing tool parameters

```python
from pydantic import BaseModel, Field

# Define extension model
class AdvancedOptions(BaseModel):
    """Advanced configuration options."""

    verbose: bool = Field(
        default=False,
        description="Enable verbose logging"
    )
    max_retries: int = Field(
        default=3,
        description="Maximum number of retry attempts"
    )
    timeout: float = Field(
        default=30.0,
        description="Timeout in seconds"
    )

# Register base tool
async def fetch_data(url: str) -> ExecutionResult:
    """Fetch data from URL.

    Args:
        url: URL to fetch from
    """
    # Implementation
    ...

manager.add_tool_function(func=fetch_data)

# Extend with advanced options
manager.apply_extension_model(
    tool_name="custom_tool__fetch_data",
    model_class=AdvancedOptions
)

# Schema now includes verbose, max_retries, timeout
schemas = manager.fetch_tool_schemas()
# Parameters: url, verbose, max_retries, timeout

# Error: Property conflict
class ConflictingModel(BaseModel):
    url: str = Field(description="Conflicts with existing 'url' parameter")

try:
    manager.apply_extension_model("custom_tool__fetch_data", ConflictingModel)
except ValueError as e:
    print(f"Error: {e}")  # Property 'url' conflicts with existing schema

# Error: Tool not found
try:
    manager.apply_extension_model("nonexistent_tool", AdvancedOptions)
except ValueError as e:
    print(f"Error: {e}")  # Tool 'nonexistent_tool' not found

# Error: Not a BaseModel
try:
    manager.apply_extension_model("custom_tool__fetch_data", dict)
except TypeError as e:
    print(f"Error: {e}")  # Extension model must be a Pydantic BaseModel

# Remove extension
manager.apply_extension_model("custom_tool__fetch_data", None)
# Schema reverts to original (only url parameter)
```

**Extension Model Requirements**:
- Must inherit from `pydantic.BaseModel`
- Properties cannot duplicate existing tool parameters
- Field descriptions are merged into schema
- Default values are respected
- Type annotations are converted to JSON schema types

## Tool Execution

### execute_tool()

**What it does**: Executes a registered tool asynchronously and streams results. Handles different return types (ExecutionResult, generators, async generators) and applies post-processing if configured.

**Why you need it**: This is how you actually run tools. It provides a uniform interface regardless of tool implementation details, handles errors gracefully, and supports streaming results.

**Parameters**:
- `tool_request` (required): Dictionary with `name` (tool name) and `input` (arguments dict)

**Yields**: `ExecutionResult` objects (may yield multiple results for streaming tools)

**Error Handling**: Errors are returned as ExecutionResult, not raised as exceptions

```python
# Example 1: Simple tool execution
tool_request = {
    "name": "custom_tool__calculate_sum",
    "input": {"a": 5, "b": 3}
}

async for result in manager.execute_tool(tool_request):
    print(result.output_blocks[0].data)
    # Output: "Sum: 8"

# Example 2: Streaming tool
async for result in manager.execute_tool({
    "name": "custom_tool__process_batch",
    "input": {"items": [1, 2, 3, 4, 5]}
}):
    if not result.is_final:
        print(f"Progress: {result.output_blocks[0].data}")
    else:
        print(f"Complete: {result.output_blocks[0].data}")

# Example 3: Error handling (tool not found)
async for result in manager.execute_tool({
    "name": "nonexistent_tool",
    "input": {}
}):
    print(result.output_blocks[0].data)
    # Output: "ToolNotFound: No tool named 'nonexistent_tool' exists"

# Example 4: With preset arguments
manager.add_tool_function(
    func=api_call,
    preset_args={"api_key": "secret", "timeout": 30}
)

# Preset args are automatically merged
async for result in manager.execute_tool({
    "name": "custom_tool__api_call",
    "input": {"endpoint": "/users"}  # api_key and timeout added automatically
}):
    print(result.output_blocks[0].data)

# Example 5: Post-processing
def log_execution(request: dict, result: ExecutionResult) -> ExecutionResult:
    print(f"Tool {request['name']} executed")
    return result

manager.add_tool_function(func=my_tool, post_processor=log_execution)

async for result in manager.execute_tool({
    "name": "custom_tool__my_tool",
    "input": {}
}):
    # log_execution is called before result is yielded
    pass

# Example 6: Cancellation handling
import asyncio

async def execute_with_timeout():
    try:
        task = asyncio.create_task(
            manager.execute_tool({"name": "long_running_tool", "input": {}}).__anext__()
        )
        result = await asyncio.wait_for(task, timeout=5.0)
    except asyncio.TimeoutError:
        task.cancel()
        print("Tool execution cancelled")

# Example 7: Collect all results
results = []
async for result in manager.execute_tool(tool_request):
    results.append(result)

final_result = results[-1]  # Last result
all_outputs = [r.output_blocks for r in results]  # All outputs
```

**Execution Flow**:

1. **Tool Lookup**: Find tool in `registered_tools`
2. **Argument Merging**: Combine `preset_params` with `input`
3. **Function Execution**:
   - Async functions: `await function(**args)`
   - Sync functions: `function(**args)`
4. **Result Wrapping**:
   - `AsyncGenerator`: Stream results directly
   - `Generator`: Convert to async generator
   - `ExecutionResult`: Wrap in async generator
5. **Post-Processing**: Apply post_processor if configured
6. **Error Handling**: Catch exceptions and return as ExecutionResult

**Supported Return Types**:

```python
# Type 1: Direct ExecutionResult
async def tool1() -> ExecutionResult:
    return ExecutionResult(output_blocks=[...])

# Type 2: Sync Generator
def tool2() -> Generator[ExecutionResult, None, None]:
    yield ExecutionResult(...)
    yield ExecutionResult(...)

# Type 3: Async Generator (streaming)
async def tool3() -> AsyncGenerator[ExecutionResult, None]:
    yield ExecutionResult(...)
    await asyncio.sleep(1)
    yield ExecutionResult(...)

# Invalid: Other types raise TypeError
async def invalid_tool() -> str:
    return "not an ExecutionResult"  # TypeError!
```

## Utility Methods

### reset_state()

**What it does**: Clears all registered tools and categories, resetting the manager to its initial state.

**Why you need it**: Useful for testing, or when you need to completely reconfigure the tool system.

**Returns**: None

```python
# Set up tools and categories
manager.setup_category("tools", "My tools", enabled=True)
manager.add_tool_function(func=tool1)
manager.add_tool_function(func=tool2)

# Clear everything
manager.reset_state()

# Manager is now empty
assert len(manager.registered_tools) == 0
assert len(manager.tool_categories) == 0

# Need to re-register everything
manager.setup_category("tools", "My tools", enabled=True)
manager.add_tool_function(func=tool1)
```

## Internal Methods

These methods are used internally but can be useful for advanced use cases.

### \_load_builtin_function()

**What it does**: Searches for a function in the built-in tool modules (`_basic`, `_code_executors`, `_file_handlers`, `_multimedia_processors`, `workflow_toolkits`).

**Returns**: Function object if found, None otherwise

### \_load_function_from_path()

**What it does**: Loads a function from a file path or module name. Handles absolute paths, relative paths, and module imports.

**Returns**: Function object if found, None otherwise

### \_extract_tool_schema()

**What it does**: Generates JSON schema from a function's signature and docstring using introspection.

**Parameters**:
- `func`: Function to analyze
- `include_full`: Include long description from docstring
- `include_varargs`: Include *args in schema
- `include_varkwargs`: Include **kwargs in schema

**Returns**: Dictionary containing JSON schema

## Complete Example

```python
from massgen.tool import ToolManager, ExecutionResult, TextContent
from pydantic import BaseModel, Field
import asyncio

# Initialize manager
manager = ToolManager()

# Create categories
manager.setup_category(
    "data",
    "Data processing tools",
    enabled=True,
    usage_hints="Use for data transformation and analysis"
)

manager.setup_category(
    "export",
    "Export and formatting tools",
    enabled=False  # Disabled by default
)

# Define tools
async def clean_data(data: list, remove_nulls: bool = True) -> ExecutionResult:
    """Clean and prepare data for analysis.

    Args:
        data: Raw data list
        remove_nulls: Whether to remove null values

    Returns:
        ExecutionResult with cleaned data
    """
    cleaned = [x for x in data if x is not None] if remove_nulls else data
    return ExecutionResult(
        output_blocks=[TextContent(data=f"Cleaned {len(cleaned)} items")],
        meta_info={"original_count": len(data), "cleaned_count": len(cleaned)}
    )

# Register tools
manager.add_tool_function(func=clean_data, category="data")

# Extend with options
class CleaningOptions(BaseModel):
    deduplicate: bool = Field(False, description="Remove duplicate values")
    sort: bool = Field(False, description="Sort the data")

manager.apply_extension_model("custom_tool__clean_data", CleaningOptions)

# Get schemas
schemas = manager.fetch_tool_schemas()
for schema in schemas:
    print(f"\nTool: {schema['function']['name']}")
    print(f"Parameters: {list(schema['function']['parameters']['properties'].keys())}")

# Execute tool
async def main():
    result_iterator = manager.execute_tool({
        "name": "custom_tool__clean_data",
        "input": {
            "data": [1, None, 2, None, 3],
            "remove_nulls": True,
            "deduplicate": False,
            "sort": True
        }
    })

    async for result in result_iterator:
        print(result.output_blocks[0].data)
        print(f"Metadata: {result.meta_info}")

asyncio.run(main())
```

## Best Practices

### Tool Registration

1. **Use Categories**: Organize tools into logical categories
2. **Provide Descriptions**: Write clear docstrings for automatic schema generation
3. **Type Everything**: Use type hints for all parameters
4. **Preset Sensitive Data**: Use `preset_args` for API keys and credentials
5. **Enable Selectively**: Start with categories disabled, enable as needed

### Schema Management

1. **Validate Schemas**: Check generated schemas match expectations
2. **Extend Carefully**: Ensure extension models don't conflict
3. **Document Parameters**: Use detailed parameter descriptions in docstrings
4. **Version Tools**: Consider versioning when changing tool signatures

### Execution

1. **Handle Errors**: Check result content for error messages
2. **Stream Long Operations**: Use generators for long-running tasks
3. **Clean Up Resources**: Use try/finally for resource cleanup
4. **Timeout Operations**: Set reasonable timeouts for all tools
5. **Post-Process Carefully**: Ensure post-processors don't break results

### Performance

1. **Lazy Load**: Only load tools when needed
2. **Cache Schemas**: Fetch schemas once and reuse
3. **Async Everything**: Use async functions for I/O operations
4. **Batch Operations**: Group related tool calls when possible

---

For more information, see:
- [ExecutionResult Documentation](execution_results.md)
- [Built-in Tools Guide](builtin_tools.md)
- [Workflow Toolkits](workflow_toolkits.md)
- [Exception Handling](exceptions.md)
