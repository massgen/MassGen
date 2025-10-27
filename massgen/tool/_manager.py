# -*- coding: utf-8 -*-
"""Tool management system for MassGen."""

import asyncio
import importlib
import importlib.util
import inspect
import sys
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, Dict, Generator, List, Optional, Type

from docstring_parser import parse
from pydantic import BaseModel, ConfigDict, Field, create_model

from ._async_helpers import (
    wrap_as_async_generator,
    wrap_object_async,
    wrap_sync_gen_async,
)
from ._registered_tool import RegisteredToolEntry
from ._result import ExecutionResult, TextContent


@dataclass
class ToolCategory:
    """Tool category configuration."""

    category_name: str
    """Category identifier for grouping tools."""

    is_enabled: bool
    """Whether tools in this category are active."""

    category_desc: str
    """Description of the tool category."""

    usage_hints: Optional[str] = None
    """Usage guidelines for tools in this category."""


class ToolManager:
    """Manager class for tool registration and execution.

    Provides methods for:
    - Tool registration: `add_tool_function`
    - Tool removal: `delete_tool_function`
    - Category management: `setup_category`, `modify_categories`, `delete_categories`
    - Schema retrieval: `fetch_tool_schemas`
    - Tool execution: `execute_tool`
    """

    def __init__(self) -> None:
        """Initialize the tool manager."""
        self.registered_tools: Dict[str, RegisteredToolEntry] = {}
        self.tool_categories: Dict[str, ToolCategory] = {}

    def setup_category(
        self,
        category_name: str,
        description: str,
        enabled: bool = False,
        usage_hints: Optional[str] = None,
    ) -> None:
        """Create a new tool category.

        Args:
            category_name: Name of the category
            description: Category description
            enabled: Whether category is initially active
            usage_hints: Optional usage guidelines
        """
        if category_name in self.tool_categories or category_name == "default":
            raise ValueError(
                f"Category '{category_name}' already exists or is reserved.",
            )

        self.tool_categories[category_name] = ToolCategory(
            category_name=category_name,
            category_desc=description,
            usage_hints=usage_hints,
            is_enabled=enabled,
        )

    def modify_categories(self, category_list: List[str], enabled: bool) -> None:
        """Update the activation status of categories.

        Args:
            category_list: List of category names
            enabled: New activation status
        """
        for cat_name in category_list:
            if cat_name == "default":
                continue  # Default category is always active

            if cat_name in self.tool_categories:
                self.tool_categories[cat_name].is_enabled = enabled

    def delete_categories(self, category_list: List[str]) -> None:
        """Remove categories and their associated tools.

        Args:
            category_list: Categories to remove
        """
        if isinstance(category_list, str):
            category_list = [category_list]

        if "default" in category_list:
            raise ValueError("Cannot remove the default category.")

        for cat_name in category_list:
            self.tool_categories.pop(cat_name, None)

        # Remove tools in deleted categories
        tool_list = list(self.registered_tools.keys())
        for tool_name in tool_list:
            if self.registered_tools[tool_name].category in category_list:
                self.registered_tools.pop(tool_name)

    def add_tool_function(
        self,
        path: Optional[str] = None,
        func: Optional[Callable] = None,
        category: str = "default",
        preset_args: Optional[Dict[str, Any]] = None,
        description: Optional[str] = None,
        tool_schema: Optional[dict] = None,
        include_full_desc: bool = True,
        allow_var_args: bool = False,
        allow_var_kwargs: bool = False,
        post_processor: Optional[Callable] = None,
    ) -> None:
        """Register a tool function.

        Args:
            path: Optional path to Python file or module. If None, use func parameter
            func: The tool function to register (required if path is None)
            category: Category for the tool
            preset_args: Arguments to preset (hidden from schema)
            description: Optional function description
            tool_schema: Optional manual JSON schema
            include_full_desc: Include long description from docstring
            allow_var_args: Include *args in schema
            allow_var_kwargs: Include **kwargs in schema
            post_processor: Optional post-processing function
        """
        if category not in self.tool_categories and category != "default":
            raise ValueError(f"Category '{category}' not found.")

        # Handle function loading
        if isinstance(func, str):
            # func is a string - treat it as function name to load
            func_name = func
            if path is not None:
                # Load from specified path
                func = self._load_function_from_path(path, func_name)
                if func is None:
                    raise ValueError(f"Could not load function '{func_name}' from path: {path}")
            else:
                # No path specified - try to find in tool folder
                func = self._load_builtin_function(func_name)
                if func is None:
                    raise ValueError(f"Could not find built-in function: {func_name}")
        elif func is None:
            # No func provided at all
            if path is not None:
                # Try to load from path (will auto-detect function)
                func = self._load_function_from_path(path, None)
                if func is None:
                    raise ValueError(f"Could not load function from path: {path}")
            else:
                raise ValueError("Either 'path' or 'func' must be provided")
        elif not callable(func):
            raise ValueError("'func' must be a callable or a string (function name)")

        # Validate schema if provided
        if tool_schema:
            assert isinstance(tool_schema, dict) and "type" in tool_schema and tool_schema["type"] == "function", "Invalid tool schema format."

        # Handle partial functions
        if isinstance(func, partial):
            func_kwargs = func.keywords.copy()
            if func.args:
                param_list = list(inspect.signature(func.func).parameters.keys())
                for idx, arg_val in enumerate(func.args):
                    if idx < len(param_list):
                        func_kwargs[param_list[idx]] = arg_val

            preset_args = {**func_kwargs, **(preset_args or {})}
            tool_name = func.func.__name__
            base_func = func.func
            tool_schema = tool_schema or self._extract_tool_schema(
                func.func,
                include_full_desc,
                allow_var_args,
                allow_var_kwargs,
            )
        else:
            tool_name = func.__name__
            base_func = func
            tool_schema = tool_schema or self._extract_tool_schema(
                func,
                include_full_desc,
                allow_var_args,
                allow_var_kwargs,
            )

        # Add prefix for custom tools (not built-in ones)
        if category != "builtin" and not tool_name.startswith("custom_tool__"):
            tool_name = f"custom_tool__{tool_name}"
            # Update the schema to reflect the new name
            tool_schema["function"]["name"] = tool_name

        # Check for duplicate names
        if tool_name in self.registered_tools:
            raise ValueError(f"Tool '{tool_name}' is already registered.")

        # Override description if provided
        if description:
            tool_schema["function"]["description"] = description

        # Remove preset args from schema
        for arg in preset_args or {}:
            if arg in tool_schema["function"]["parameters"]["properties"]:
                tool_schema["function"]["parameters"]["properties"].pop(arg)

            if "required" in tool_schema["function"]["parameters"]:
                if arg in tool_schema["function"]["parameters"]["required"]:
                    tool_schema["function"]["parameters"]["required"].remove(arg)

                if not tool_schema["function"]["parameters"]["required"]:
                    tool_schema["function"]["parameters"].pop("required", None)

        tool_entry = RegisteredToolEntry(
            tool_name=tool_name,
            category=category,
            origin="function",
            base_function=base_func,
            schema_def=tool_schema,
            preset_params=preset_args or {},
            extension_model=None,
            post_processor=post_processor,
        )

        self.registered_tools[tool_name] = tool_entry

    def delete_tool_function(self, tool_name: str) -> None:
        """Remove a tool function by name.

        Args:
            tool_name: Name of tool to remove
        """
        self.registered_tools.pop(tool_name, None)

    def fetch_tool_schemas(self) -> List[dict]:
        """Get JSON schemas for all active tools.

        Returns:
            List of tool JSON schemas
        """
        schemas = []
        for tool in self.registered_tools.values():
            if tool.category == "default":
                schemas.append(tool.get_extended_schema)
            elif tool.category in self.tool_categories:
                if self.tool_categories[tool.category].is_enabled:
                    schemas.append(tool.get_extended_schema)
        return schemas

    def apply_extension_model(
        self,
        tool_name: str,
        model_class: Optional[Type[BaseModel]],
    ) -> None:
        """Apply an extension model to a tool's schema.

        Args:
            tool_name: Name of the tool
            model_class: Pydantic model to extend schema with
        """
        if model_class and not issubclass(model_class, BaseModel):
            raise TypeError("Extension model must be a Pydantic BaseModel.")

        if tool_name in self.registered_tools:
            self.registered_tools[tool_name].extension_model = model_class
        else:
            raise ValueError(f"Tool '{tool_name}' not found.")

    async def execute_tool(
        self,
        tool_request: dict,
    ) -> AsyncGenerator[ExecutionResult, None]:
        """Execute a tool and return results as async generator.

        Args:
            tool_request: Tool execution request with name and input

        Yields:
            ExecutionResult objects (accumulated)
        """
        tool_name = tool_request.get("name")

        if tool_name not in self.registered_tools:
            yield ExecutionResult(
                output_blocks=[
                    TextContent(
                        data=f"ToolNotFound: No tool named '{tool_name}' exists",
                    ),
                ],
            )
            return

        tool_entry = self.registered_tools[tool_name]

        # Merge parameters: model input first, then preset params override
        # This ensures preset_params (like agent_cwd) always take precedence
        # and won't be overridden by null values from model
        model_input = tool_request.get("input", {}) or {}
        exec_kwargs = {
            **model_input,
            **tool_entry.preset_params,  # preset_params override model input
        }

        # Prepare post-processor if exists
        if tool_entry.post_processor:
            post_proc_partial = partial(
                tool_entry.post_processor,
                tool_request,
            )
        else:
            post_proc_partial = None

        try:
            # Execute based on function type
            if inspect.iscoroutinefunction(tool_entry.base_function):
                try:
                    result = await tool_entry.base_function(**exec_kwargs)
                except asyncio.CancelledError:
                    result = ExecutionResult(
                        output_blocks=[
                            TextContent(
                                data="<system>Tool execution was interrupted</system>",
                            ),
                        ],
                        is_streaming=True,
                        is_final=True,
                        was_interrupted=True,
                    )
            else:
                result = tool_entry.base_function(**exec_kwargs)

        except Exception as err:
            result = ExecutionResult(
                output_blocks=[
                    TextContent(data=f"Error: {err}"),
                ],
            )

        # Handle different return types
        if isinstance(result, AsyncGenerator):
            async for item in wrap_as_async_generator(result, post_proc_partial):
                yield item
        elif isinstance(result, Generator):
            async for item in wrap_sync_gen_async(result, post_proc_partial):
                yield item
        elif isinstance(result, ExecutionResult):
            async for item in wrap_object_async(result, post_proc_partial):
                yield item
        else:
            raise TypeError(
                f"Tool must return ExecutionResult or Generator, got {type(result)}",
            )

    def fetch_category_hints(self) -> str:
        """Get usage hints from active categories.

        Returns:
            Combined usage hints string
        """
        hints_list = []
        for cat_name, category in self.tool_categories.items():
            if category.is_enabled and category.usage_hints:
                hints_list.append(
                    f"## {cat_name} Tools\n{category.usage_hints}",
                )
        return "\n".join(hints_list)

    def reset_state(self) -> None:
        """Clear all registered tools and categories."""
        self.registered_tools.clear()
        self.tool_categories.clear()

    def _load_builtin_function(self, func_name: str) -> Optional[Callable]:
        """Load a built-in function from the tool folder.

        Args:
            func_name: Name of the function to load

        Returns:
            The loaded function or None if not found
        """
        # Try to import from tool module submodules
        tool_modules = [
            "_basic",
            "_code_executors",
            "_file_handlers",
            "_multimedia_processors",
            "workflow_toolkits",
        ]

        for module_name in tool_modules:
            try:
                full_module_name = f"massgen.tool.{module_name}"
                module = importlib.import_module(full_module_name)
                if hasattr(module, func_name):
                    return getattr(module, func_name)
            except ImportError:
                continue

        # Try to find in __init__.py exports
        try:
            tool_module = importlib.import_module("massgen.tool")
            if hasattr(tool_module, func_name):
                return getattr(tool_module, func_name)
        except ImportError:
            pass

        # Search in all Python files in tool folder
        tool_folder = Path(__file__).parent
        for py_file in tool_folder.glob("*.py"):
            if py_file.stem == "__init__" or py_file.stem == "_manager":
                continue

            try:
                spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    if hasattr(module, func_name):
                        return getattr(module, func_name)
            except Exception:
                continue

        return None

    def _load_function_from_path(
        self,
        path: str,
        func_name: Optional[str] = None,
    ) -> Optional[Callable]:
        """Load a function from a given path.

        Args:
            path: Path to Python file or module name
            func_name: Optional specific function name to load

        Returns:
            The loaded function or None if not found
        """
        # If path doesn't contain file extension, try to find it in tool folder
        if not path.endswith(".py"):
            # Try to import from tool module
            try:
                # First try as a submodule of tool
                module_name = f"massgen.tool.{path}"
                module = importlib.import_module(module_name)
            except ImportError:
                # Try to find in tool folder's Python files
                tool_folder = Path(__file__).parent
                possible_files = [
                    tool_folder / f"{path}.py",
                    tool_folder / f"_{path}.py",
                ]

                for file_path in possible_files:
                    if file_path.exists():
                        path = str(file_path)
                        break
                else:
                    # If still not found, try as a direct module import
                    try:
                        module = importlib.import_module(path)
                    except ImportError:
                        return None

        # If path is a file path, load it dynamically
        if path.endswith(".py"):
            path_obj = Path(path)

            # If path is not absolute, try multiple resolution strategies
            if not path_obj.is_absolute():
                # First try as relative to current working directory
                cwd_path = Path.cwd() / path
                if cwd_path.exists():
                    path_obj = cwd_path
                else:
                    # Then try relative to tool folder
                    tool_folder = Path(__file__).parent
                    tool_path = tool_folder / path
                    if tool_path.exists():
                        path_obj = tool_path
                    else:
                        # Finally try resolving from tool folder's parent (massgen/)
                        # in case path starts with "massgen/"
                        if path.startswith("massgen/"):
                            # Get the massgen package root
                            massgen_root = tool_folder.parent.parent
                            full_path = massgen_root / path
                            if full_path.exists():
                                path_obj = full_path

            if not path_obj.exists():
                return None

            # Load module from file
            module_name = path_obj.stem
            spec = importlib.util.spec_from_file_location(module_name, path_obj)
            if spec is None or spec.loader is None:
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

        # Extract function from module
        if func_name:
            # If specific function name provided
            if hasattr(module, func_name):
                return getattr(module, func_name)
        else:
            # Try to find a main function or the first callable
            # Priority order: main -> first public function -> first function
            if hasattr(module, "main"):
                return getattr(module, "main")

            # Find all callables in the module
            callables = []
            for name in dir(module):
                attr = getattr(module, name)
                if callable(attr) and not name.startswith("_"):
                    # Skip imported functions
                    if hasattr(attr, "__module__") and attr.__module__ != module.__name__:
                        continue
                    callables.append((name, attr))

            # Return the first public function found
            if callables:
                return callables[0][1]

        return None

    @staticmethod
    def _extract_tool_schema(
        func: Callable,
        include_full: bool,
        include_varargs: bool,
        include_varkwargs: bool,
    ) -> dict:
        """Extract JSON schema from function signature and docstring."""
        doc_parsed = parse(func.__doc__)
        param_docs = {p.arg_name: p.description for p in doc_parsed.params}

        # Build description
        desc_parts = []
        if doc_parsed.short_description:
            desc_parts.append(doc_parsed.short_description)
        if include_full and doc_parsed.long_description:
            desc_parts.append(doc_parsed.long_description)

        func_desc = "\n\n".join(desc_parts)

        # Build parameter fields
        param_fields = {}
        for param_name, param_info in inspect.signature(func).parameters.items():
            if param_name in ["self", "cls"]:
                continue

            if param_info.kind == inspect.Parameter.VAR_KEYWORD:
                if not include_varkwargs:
                    continue
                param_fields[param_name] = (
                    Dict[str, Any] if param_info.annotation == inspect.Parameter.empty else Dict[str, param_info.annotation],
                    Field(
                        description=param_docs.get(param_name),
                        default={} if param_info.default is param_info.empty else param_info.default,
                    ),
                )
            elif param_info.kind == inspect.Parameter.VAR_POSITIONAL:
                if not include_varargs:
                    continue
                param_fields[param_name] = (
                    list[Any] if param_info.annotation == inspect.Parameter.empty else list[param_info.annotation],
                    Field(
                        description=param_docs.get(param_name),
                        default=[] if param_info.default is param_info.empty else param_info.default,
                    ),
                )
            else:
                param_fields[param_name] = (
                    Any if param_info.annotation == inspect.Parameter.empty else param_info.annotation,
                    Field(
                        description=param_docs.get(param_name),
                        default=... if param_info.default is param_info.empty else param_info.default,
                    ),
                )

        dynamic_model = create_model(
            "_DynamicToolModel",
            __config__=ConfigDict(arbitrary_types_allowed=True),
            **param_fields,
        )

        params_schema = dynamic_model.model_json_schema()

        # Remove title fields
        def remove_titles(obj):
            if isinstance(obj, dict):
                obj.pop("title", None)
                for v in obj.values():
                    remove_titles(v)
            elif isinstance(obj, list):
                for item in obj:
                    remove_titles(item)

        remove_titles(params_schema)

        schema = {
            "type": "function",
            "function": {
                "name": func.__name__,
                "parameters": params_schema,
            },
        }

        if func_desc:
            schema["function"]["description"] = func_desc

        return schema
