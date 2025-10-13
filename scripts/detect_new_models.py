#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Detect new models added between releases.

This script compares backend files between git tags to identify newly added models.
It can output in markdown table format for easy inclusion in release notes.

Tracks:
- Multimodal
- AgentAdapter backends
- Coding Agent
- Web UI
- Irreversible actions
- Memory

Usage:
    python scripts/detect_new_models.py --prev v0.0.29
    python scripts/detect_new_models.py --prev v0.0.29 --current HEAD
    python scripts/detect_new_models.py --prev v0.0.29 --format markdown

"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set


def get_file_at_ref(file_path: str, git_ref: str) -> Optional[str]:
    """
    Get file content at a specific git ref.

    Args:
        file_path: Path to file relative to repo root
        git_ref: Git ref (tag, commit, branch)

    Returns:
        File content or None if file doesn't exist at that ref
    """
    try:
        result = subprocess.run(
            ["git", "show", f"{git_ref}:{file_path}"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError:
        return None


def extract_models_from_backend(content: str, backend_name: str) -> Set[str]:
    """
    Extract model IDs from backend file content.

    This looks for common patterns like:
    - model_id = "gpt-4"
    - "model": "claude-3"
    - MODEL_NAME = "gemini-pro"
    - List of model strings

    Args:
        content: File content
        backend_name: Name of backend (for context)

    Returns:
        Set of model ID strings
    """
    models = set()

    # Pattern 1: model_id = "..." or model = "..."
    pattern1 = r'(?:model|model_id|MODEL)\s*[=:]\s*["\']([a-zA-Z0-9_\-./]+)["\']'
    models.update(re.findall(pattern1, content))

    # Pattern 2: List of model strings
    # e.g., ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"]
    pattern2 = r'["\']([a-zA-Z0-9_\-./]+(?:gpt|claude|gemini|llama|mistral|palm|command)[a-zA-Z0-9_\-./]*)["\']'
    models.update(re.findall(pattern2, content, re.IGNORECASE))

    # Pattern 3: Dictionary keys that look like model names
    pattern3 = r'["\']([a-z0-9_\-]+(?:-\d+)?(?:-[a-z]+)?)["\']:\s*(?:True|{)'
    potential_models = re.findall(pattern3, content)
    for model in potential_models:
        # Filter to likely model names (contain numbers or known prefixes)
        if any(x in model for x in ["gpt", "claude", "gemini", "llama", "mistral", "3", "4", "5"]):
            models.add(model)

    # Filter out common non-model strings
    exclude = {"model", "model_id", "MODEL", "api_key", "base_url", "version", "type", "config"}
    models = {m for m in models if m not in exclude and len(m) > 2}

    return models


def get_models_in_backends(git_ref: str, backends_dir: str = "massgen/backends") -> Dict[str, Set[str]]:
    """
    Get all models for each backend at a specific git ref.

    Args:
        git_ref: Git reference (tag, commit, branch)
        backends_dir: Path to backends directory

    Returns:
        Dictionary mapping backend name to set of model IDs
    """
    # Get list of Python files in backends directory at this ref
    try:
        result = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", git_ref, backends_dir],
            capture_output=True,
            text=True,
            check=True,
        )
        files = [f for f in result.stdout.strip().split("\n") if f.endswith(".py")]
    except subprocess.CalledProcessError:
        print(f"Warning: Could not list backends at {git_ref}", file=sys.stderr)
        return {}

    backends = {}

    for file_path in files:
        # Skip __init__.py and common utility files
        if "__init__" in file_path or "base" in file_path.lower() or "utils" in file_path:
            continue

        # Get backend name from filename
        backend_name = Path(file_path).stem

        # Get file content at this ref
        content = get_file_at_ref(file_path, git_ref)
        if content is None:
            continue

        # Extract models
        models = extract_models_from_backend(content, backend_name)
        if models:
            backends[backend_name] = models

    return backends


def compare_models(
    prev_models: Dict[str, Set[str]],
    current_models: Dict[str, Set[str]],
) -> Dict[str, List[str]]:
    """
    Compare models between two versions.

    Args:
        prev_models: Models in previous version
        current_models: Models in current version

    Returns:
        Dictionary mapping backend name to list of newly added models
    """
    new_models = {}

    # Check all current backends
    for backend, models in current_models.items():
        if backend not in prev_models:
            # Entire backend is new
            new_models[backend] = sorted(models)
        else:
            # Find models not in previous version
            added = models - prev_models[backend]
            if added:
                new_models[backend] = sorted(added)

    return new_models


def format_output(new_models: Dict[str, List[str]], format_type: str = "markdown") -> str:
    """
    Format the output in requested format.

    Args:
        new_models: Dictionary of backend -> new models
        format_type: Output format (markdown, json, text)

    Returns:
        Formatted string
    """
    if not new_models:
        return "No new models detected."

    if format_type == "json":
        return json.dumps(new_models, indent=2)

    elif format_type == "markdown":
        lines = ["| Backend | Model ID | Notes |", "|---------|----------|-------|"]
        for backend, models in sorted(new_models.items()):
            for model in models:
                # Add a note if this is a new backend entirely
                note = "New backend" if len(models) == len(new_models.get(backend, [])) else ""
                lines.append(f"| {backend} | `{model}` | {note} |")
        return "\n".join(lines)

    else:  # text format
        lines = []
        for backend, models in sorted(new_models.items()):
            lines.append(f"{backend}:")
            for model in models:
                lines.append(f"  - {model}")
        return "\n".join(lines)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Detect new models added between MassGen releases",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Detect new models since v0.0.29
  python scripts/detect_new_models.py --prev v0.0.29

  # Compare two specific versions
  python scripts/detect_new_models.py --prev v0.0.29 --current v0.0.30

  # Output in JSON format
  python scripts/detect_new_models.py --prev v0.0.29 --format json

  # Output markdown table for release notes
  python scripts/detect_new_models.py --prev v0.0.29 --format markdown

Tracks: Multimodal, AgentAdapter backends, Coding Agent, Web UI,
        Irreversible actions, Memory
        """,
    )

    parser.add_argument(
        "--prev",
        required=True,
        help="Previous version tag (e.g., v0.0.29)",
    )

    parser.add_argument(
        "--current",
        default="HEAD",
        help="Current version tag or ref (default: HEAD)",
    )

    parser.add_argument(
        "--format",
        choices=["markdown", "json", "text"],
        default="markdown",
        help="Output format (default: markdown)",
    )

    parser.add_argument(
        "--backends-dir",
        default="massgen/backends",
        help="Path to backends directory (default: massgen/backends)",
    )

    args = parser.parse_args()

    print(f"Analyzing models between {args.prev} and {args.current}...", file=sys.stderr)
    print(file=sys.stderr)

    try:
        # Get models in previous version
        print(f"Scanning {args.prev}...", file=sys.stderr)
        prev_models = get_models_in_backends(args.prev, args.backends_dir)
        print(f"  Found {len(prev_models)} backends with {sum(len(m) for m in prev_models.values())} models", file=sys.stderr)

        # Get models in current version
        print(f"Scanning {args.current}...", file=sys.stderr)
        current_models = get_models_in_backends(args.current, args.backends_dir)
        print(f"  Found {len(current_models)} backends with {sum(len(m) for m in current_models.values())} models", file=sys.stderr)

        # Compare
        print(f"Comparing...", file=sys.stderr)
        new_models = compare_models(prev_models, current_models)
        print(file=sys.stderr)

        # Output results
        if new_models:
            total_new = sum(len(models) for models in new_models.values())
            print(f"✓ Detected {total_new} new models across {len(new_models)} backends", file=sys.stderr)
            print(file=sys.stderr)
            print("=" * 70, file=sys.stderr)
            print(file=sys.stderr)

        output = format_output(new_models, args.format)
        print(output)  # Print to stdout for piping

        return 0

    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
