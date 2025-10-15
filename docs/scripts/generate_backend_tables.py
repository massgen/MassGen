#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto-generate backend capability tables for documentation.

This script reads from massgen/backend/capabilities.py (single source of truth)
and generates markdown tables for inclusion in documentation.

Usage:
    python docs/scripts/generate_backend_tables.py

This will generate:
    - docs/generated/backend_feature_table.md (feature comparison)
    - docs/generated/backend_details_table.md (detailed specs)
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from massgen.backend.capabilities import BACKEND_CAPABILITIES


def generate_feature_comparison_table() -> str:
    """Generate a markdown table comparing features across backends."""

    # Define features to display
    features = [
        ("Web Search", "web_search"),
        ("Code Execution", "code_execution"),
        ("Bash/Shell", "bash"),
        ("Image", "image"),  # Combined understanding + generation
        ("Audio", "audio"),  # Combined understanding + generation
        ("Video", "video"),  # Combined understanding + generation
        ("MCP Support", "mcp"),
        ("Filesystem", "filesystem_support"),
    ]

    # Header row with backend names
    backends = list(BACKEND_CAPABILITIES.keys())
    header = "| Feature | " + " | ".join([BACKEND_CAPABILITIES[b].provider_name for b in backends]) + " |"
    separator = "|" + "|".join(["---"] * (len(backends) + 1)) + "|"

    rows = [header, separator]

    # Feature rows
    for feature_name, feature_key in features:
        row = f"| **{feature_name}** |"

        for backend_type in backends:
            caps = BACKEND_CAPABILITIES[backend_type]

            if feature_key == "filesystem_support":
                # Special handling for filesystem
                if caps.filesystem_support == "native":
                    row += " ✅ Native |"
                elif caps.filesystem_support == "mcp":
                    row += " ✅ Via MCP |"
                else:
                    row += " ❌ |"
            elif feature_key == "image":
                # Check for image understanding or generation
                has_understanding = "image_understanding" in caps.supported_capabilities
                has_generation = "image_generation" in caps.supported_capabilities
                if has_understanding and has_generation:
                    row += " ✅ Both |"
                elif has_understanding:
                    row += " ✅ Understanding |"
                elif has_generation:
                    row += " ✅ Generation |"
                else:
                    row += " ❌ |"
            elif feature_key == "audio":
                # Check for audio understanding or generation
                has_understanding = "audio_understanding" in caps.supported_capabilities
                has_generation = "audio_generation" in caps.supported_capabilities
                if has_understanding and has_generation:
                    row += " ✅ Both |"
                elif has_understanding:
                    row += " ✅ Understanding |"
                elif has_generation:
                    row += " ✅ Generation |"
                else:
                    row += " ❌ |"
            elif feature_key == "video":
                # Check for video understanding or generation
                has_understanding = "video_understanding" in caps.supported_capabilities
                has_generation = "video_generation" in caps.supported_capabilities
                if has_understanding and has_generation:
                    row += " ✅ Both |"
                elif has_understanding:
                    row += " ✅ Understanding |"
                elif has_generation:
                    row += " ✅ Generation |"
                else:
                    row += " ❌ |"
            else:
                # Check if feature is in supported capabilities
                if feature_key in caps.supported_capabilities:
                    row += " ✅ |"
                else:
                    row += " ❌ |"

        rows.append(row)

    return "\n".join(rows)


def generate_backend_details_table() -> str:
    """Generate a detailed markdown table with backend specifications."""

    header = "| Backend | Provider | Models | Built-in Tools | Filesystem | API Key Required |"
    separator = "|---|---|---|---|---|---|"

    rows = [header, separator]

    for backend_type, caps in BACKEND_CAPABILITIES.items():
        # Format models list
        if len(caps.models) > 3:
            models_display = ", ".join(caps.models[:3]) + f" (+{len(caps.models) - 3} more)"
        else:
            models_display = ", ".join(caps.models)

        # Format built-in tools
        if len(caps.builtin_tools) > 3:
            tools_display = ", ".join(caps.builtin_tools[:3]) + "..."
        elif caps.builtin_tools:
            tools_display = ", ".join(caps.builtin_tools)
        else:
            tools_display = "None"

        # Filesystem support
        fs_display = {
            "native": "✅ Native",
            "mcp": "Via MCP",
            "none": "❌",
        }.get(caps.filesystem_support, "❌")

        # API key
        api_key_display = caps.env_var if caps.env_var else "Not required"

        row = f"| `{backend_type}` | {caps.provider_name} | {models_display} | {tools_display} | {fs_display} | {api_key_display} |"
        rows.append(row)

    return "\n".join(rows)


def generate_capabilities_list() -> str:
    """Generate a detailed list of capabilities per backend."""

    output = []

    for backend_type, caps in BACKEND_CAPABILITIES.items():
        output.append(f"### {caps.provider_name} (`{backend_type}`)\n")

        # Models
        output.append("**Models:**")
        for model in caps.models:
            default_marker = " (default)" if model == caps.default_model else ""
            output.append(f"- `{model}`{default_marker}")
        output.append("")

        # Capabilities
        output.append("**Capabilities:**")
        for cap in sorted(caps.supported_capabilities):
            output.append(f"- {cap}")
        output.append("")

        # Built-in tools
        if caps.builtin_tools:
            output.append("**Built-in Tools:**")
            for tool in caps.builtin_tools:
                output.append(f"- `{tool}`")
            output.append("")

        # Filesystem
        output.append(f"**Filesystem Support:** {caps.filesystem_support}")
        output.append("")

        # API key
        if caps.env_var:
            output.append(f"**Required Environment Variable:** `{caps.env_var}`")
        else:
            output.append("**Required Environment Variable:** None")
        output.append("")

        # Notes
        if caps.notes:
            output.append(f"**Notes:** {caps.notes}")
            output.append("")

        output.append("---\n")

    return "\n".join(output)


def main():
    """Generate all backend documentation tables."""

    print("Generating backend capability documentation...")
    print(f"Reading from: {project_root}/massgen/backend/capabilities.py")

    # Create output directory
    output_dir = project_root / "docs" / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate feature comparison table
    feature_table = generate_feature_comparison_table()
    feature_table_path = output_dir / "backend_feature_table.md"
    with open(feature_table_path, "w") as f:
        f.write("<!-- AUTO-GENERATED - DO NOT EDIT MANUALLY -->\n")
        f.write("<!-- Generated from massgen/backend/capabilities.py -->\n")
        f.write("<!-- Run: python docs/scripts/generate_backend_tables.py -->\n\n")
        f.write("# Backend Feature Comparison\n\n")
        f.write(feature_table)
        f.write("\n\n")
        f.write("**Legend:**\n")
        f.write("- ✅ = Supported\n")
        f.write("- ❌ = Not supported\n")
        f.write("\n**Notes:**\n")
        f.write('- "Via MCP" means the feature is available through Model Context Protocol integration\n')
        f.write('- "Native" means the feature is built directly into the backend\n')
    print(f"✅ Generated: {feature_table_path}")

    # Generate details table
    details_table = generate_backend_details_table()
    details_table_path = output_dir / "backend_details_table.md"
    with open(details_table_path, "w") as f:
        f.write("<!-- AUTO-GENERATED - DO NOT EDIT MANUALLY -->\n")
        f.write("<!-- Generated from massgen/backend/capabilities.py -->\n")
        f.write("<!-- Run: python docs/scripts/generate_backend_tables.py -->\n\n")
        f.write("# Backend Details\n\n")
        f.write(details_table)
    print(f"✅ Generated: {details_table_path}")

    # Generate capabilities list
    capabilities_list = generate_capabilities_list()
    capabilities_list_path = output_dir / "backend_capabilities_list.md"
    with open(capabilities_list_path, "w") as f:
        f.write("<!-- AUTO-GENERATED - DO NOT EDIT MANUALLY -->\n")
        f.write("<!-- Generated from massgen/backend/capabilities.py -->\n")
        f.write("<!-- Run: python docs/scripts/generate_backend_tables.py -->\n\n")
        f.write("# Backend Capabilities Reference\n\n")
        f.write(capabilities_list)
    print(f"✅ Generated: {capabilities_list_path}")

    print("\n✅ All backend documentation tables generated successfully!")
    print("\nGenerated files:")
    print(f"  - {feature_table_path}")
    print(f"  - {details_table_path}")
    print(f"  - {capabilities_list_path}")
    print("\nYou can now include these in your documentation with:")
    print("  ```markdown")
    print("  [!INCLUDE](../generated/backend_feature_table.md)")
    print("  ```")


if __name__ == "__main__":
    main()
