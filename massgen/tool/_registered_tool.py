# -*- coding: utf-8 -*-
"""Registered tool entry data model."""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional, Type

from pydantic import BaseModel

from ._result import ExecutionResult


@dataclass
class RegisteredToolEntry:
    """Container for registered tool metadata and configuration."""

    tool_name: str
    """Identifier for the tool function."""

    category: str | Literal["default"]
    """Category this tool belongs to."""

    origin: Literal["function", "mcp_server", "function_group"]
    """Source type of the tool."""

    base_function: Callable
    """The underlying callable function."""

    schema_def: dict
    """JSON schema definition for the tool."""

    preset_params: dict[str, Any] = field(default_factory=dict)
    """Pre-configured parameters hidden from schema."""

    extension_model: Optional[Type[BaseModel]] = None
    """Optional model for extending the base schema."""

    mcp_server_id: Optional[str] = None
    """MCP server identifier if applicable."""

    post_processor: Optional[Callable[[dict, ExecutionResult], Optional[ExecutionResult]]] = None
    """Optional post-processing function for results."""

    @property
    def get_extended_schema(self) -> dict:
        """Generate the complete schema including extensions.

        Returns:
            Merged JSON schema with extensions applied
        """
        if self.extension_model is None:
            return self.schema_def

        # Generate extension schema
        ext_schema = self.extension_model.model_json_schema()
        combined_schema = deepcopy(self.schema_def)

        # Clean up title fields
        self._clean_titles(ext_schema)

        # Merge extension properties
        for prop_key, prop_val in ext_schema.get("properties", {}).items():
            existing_props = combined_schema["function"]["parameters"]["properties"]
            if prop_key in existing_props:
                raise ValueError(
                    f"Property '{prop_key}' conflicts with existing schema for '{self.tool_name}'",
                )

            existing_props[prop_key] = prop_val

            # Add to required list if necessary
            if prop_key in ext_schema.get("required", []):
                if "required" not in combined_schema["function"]["parameters"]:
                    combined_schema["function"]["parameters"]["required"] = []
                combined_schema["function"]["parameters"]["required"].append(prop_key)

        return combined_schema

    @staticmethod
    def _clean_titles(schema_obj: Any) -> None:
        """Recursively remove title fields from schema."""
        if isinstance(schema_obj, dict):
            schema_obj.pop("title", None)
            for val in schema_obj.values():
                RegisteredToolEntry._clean_titles(val)
        elif isinstance(schema_obj, list):
            for element in schema_obj:
                RegisteredToolEntry._clean_titles(element)
