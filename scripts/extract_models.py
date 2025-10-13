#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extract supported models from MassGen codebase.

This script analyzes the backends directory to generate a list of supported models.

Usage:
    python scripts/extract_models.py                    # Print to stdout
    python scripts/extract_models.py --output models.md # Write to file
    python scripts/extract_models.py --format json      # Output as JSON
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List


def scan_backends_directory() -> Dict[str, List[str]]:
    """
    Scan massgen/backends/ to find backend implementations and their models.

    Returns:
        Dictionary mapping backend provider to list of models
    """
    backends_dir = Path("massgen/backends")
    if not backends_dir.exists():
        print(f"Error: Backends directory not found at {backends_dir}", file=sys.stderr)
        return {}

    backends = {}
    backend_files = list(backends_dir.glob("*.py"))

    # Filter out common non-backend files
    exclude_files = {"__init__.py", "base.py", "base_with_mcp.py", "utils.py"}

    for backend_file in backend_files:
        if backend_file.name in exclude_files:
            continue

        backend_name = backend_file.stem.replace("_", " ").title()
        content = backend_file.read_text()

        # Extract model identifiers (this is a heuristic - adjust as needed)
        # Look for common patterns like model names in strings
        models = set()

        # Common model name patterns
        patterns = [
            r'"([a-z0-9-]+(?:gpt|claude|gemini|grok|llama|mistral|qwen)[a-z0-9-]*)"',
            r"'([a-z0-9-]+(?:gpt|claude|gemini|grok|llama|mistral|qwen)[a-z0-9-]*)'",
        ]

        import re

        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            models.update(matches)

        if models:
            backends[backend_name] = sorted(list(models))

    return backends


def format_as_markdown(backends: Dict[str, List[str]]) -> str:
    """Format backends as Markdown."""
    lines = ["# Supported Models", "", ""]

    for backend, models in sorted(backends.items()):
        lines.append(f"## {backend}")
        lines.append("")
        for model in models:
            lines.append(f"- `{model}`")
        lines.append("")

    return "\n".join(lines)


def format_as_json(backends: Dict[str, List[str]]) -> str:
    """Format backends as JSON."""
    return json.dumps(backends, indent=2)


def format_as_list(backends: Dict[str, List[str]]) -> str:
    """Format backends as simple list."""
    lines = []
    for backend, models in sorted(backends.items()):
        lines.append(f"{backend}:")
        for model in models:
            lines.append(f"  - {model}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Extract supported models from MassGen codebase",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="Output file path (default: print to stdout)",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["markdown", "json", "list"],
        default="markdown",
        help="Output format (default: markdown)",
    )

    args = parser.parse_args()

    # Ensure we're in project root
    if not Path("massgen").exists():
        print("Error: Must run from project root directory", file=sys.stderr)
        sys.exit(1)

    # Extract backends and models
    backends = scan_backends_directory()

    if not backends:
        print("Warning: No backends found", file=sys.stderr)
        sys.exit(1)

    # Format output
    if args.format == "markdown":
        output = format_as_markdown(backends)
    elif args.format == "json":
        output = format_as_json(backends)
    else:  # list
        output = format_as_list(backends)

    # Write output
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(output)
        print(f"✅ Wrote model list to {output_path}", file=sys.stderr)
    else:
        print(output)

    # Print summary to stderr
    print(f"\n✅ Found {len(backends)} backend providers", file=sys.stderr)
    total_models = sum(len(models) for models in backends.values())
    print(f"✅ Found {total_models} model identifiers", file=sys.stderr)


if __name__ == "__main__":
    main()
