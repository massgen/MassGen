#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate README.md from docs sources and code introspection.

This script maintains a single source of truth by extracting content from:
- docs/_includes/ - Reusable content snippets
- Codebase analysis - Supported models, CLI parameters
- docs/source/changelog.rst - Latest release notes

Usage:
    python scripts/generate_readme.py
    python scripts/generate_readme.py --dry-run  # Preview changes without writing
"""

import argparse
import sys
from pathlib import Path


def load_include(filename: str) -> str:
    """Load content from an include file."""
    include_path = Path("docs/_includes") / filename
    if not include_path.exists():
        print(f"Warning: Include file not found: {include_path}", file=sys.stderr)
        return f"[Include file not found: {filename}]"
    return include_path.read_text()


def extract_supported_models() -> str:
    """Extract supported models from backend implementations."""
    # This is a placeholder - implement based on your actual model registration
    # You may want to scan massgen/backends/ or look for a central registry
    models_info = []

    # Example: scan for backend files
    backends_dir = Path("massgen/backends")
    if backends_dir.exists():
        backend_files = list(backends_dir.glob("*.py"))
        models_info.append(f"Found {len(backend_files)} backend implementations")

    return "\n".join(
        [
            "The system currently supports multiple model providers with advanced capabilities:",
            "",
            "**API-based Models:**",
            "- **Azure OpenAI**: GPT-4, GPT-4o, GPT-3.5-turbo, GPT-4.1, GPT-5-chat",
            "- **Cerebras AI**: GPT-OSS models",
            "- **Claude**: Claude Haiku 3.5, Claude Sonnet 4, Claude Opus 4",
            "- **Gemini**: Gemini 2.5 Flash, Gemini 2.5 Pro",
            "- **Grok**: Grok-4, Grok-3, Grok-3-mini",
            "- **OpenAI**: GPT-5 series (GPT-5, GPT-5-mini, GPT-5-nano), GPT-4o series",
            "",
            "See [Backend Configuration](docs/source/user_guide/configuration.rst) for complete list.",
        ],
    )


def extract_latest_changelog(num_versions: int = 1) -> str:
    """Extract latest changelog entries."""
    changelog_path = Path("docs/source/changelog.rst")
    if not changelog_path.exists():
        return "[Changelog not found]"

    content = changelog_path.read_text()

    # Extract version sections (adjust regex based on your changelog format)
    # This is a simple implementation - enhance as needed
    lines = content.split("\n")
    changelog_lines = []
    in_latest = False
    version_count = 0

    for line in lines:
        if line.startswith("v") or line.startswith("Version"):
            if version_count >= num_versions:
                break
            version_count += 1
            in_latest = True

        if in_latest:
            changelog_lines.append(line)

    return "\n".join(changelog_lines[:50])  # Limit to first 50 lines


def generate_readme(dry_run: bool = False) -> bool:
    """
    Generate README from current README and docs sources.

    Returns:
        True if changes were made, False otherwise
    """
    readme_path = Path("README.md")

    if not readme_path.exists():
        print(f"Error: README.md not found at {readme_path}", file=sys.stderr)
        return False

    # Read current README
    current_readme = readme_path.read_text()

    # For now, we'll add markers that can be replaced
    # In the future, you may want to use a template system

    # Define replacements
    replacements = {
        "{{INSTALLATION}}": load_include("installation.md"),
        "{{API_CONFIGURATION}}": load_include("api-configuration.md"),
        "{{SUPPORTED_MODELS}}": extract_supported_models(),
        "{{LATEST_CHANGELOG}}": extract_latest_changelog(1),
    }

    # Check if markers exist in README
    has_markers = any(marker in current_readme for marker in replacements.keys())

    if not has_markers:
        print("No markers found in README.md")
        print("To use auto-generation, add markers like {{INSTALLATION}} where you want content inserted")
        return False

    # Perform replacements
    new_readme = current_readme
    changes_made = False

    for marker, content in replacements.items():
        if marker in new_readme:
            new_readme = new_readme.replace(marker, content)
            changes_made = True
            print(f"✅ Replaced {marker}")

    # Write result
    if changes_made:
        if dry_run:
            print("\n=== DRY RUN: Would update README.md with: ===\n")
            # Show diff-like output
            for marker in replacements.keys():
                if marker in current_readme:
                    print(f"Would replace {marker}")
            print("\n=== End of dry run ===")
        else:
            readme_path.write_text(new_readme)
            print(f"\n✅ Successfully updated {readme_path}")
    else:
        print("No changes needed")

    return changes_made


def main():
    parser = argparse.ArgumentParser(
        description="Generate README.md from documentation sources",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing files",
    )

    args = parser.parse_args()

    # Ensure we're in the project root
    if not Path("massgen").exists():
        print("Error: Must run from project root directory", file=sys.stderr)
        sys.exit(1)

    # Generate README
    success = generate_readme(dry_run=args.dry_run)

    if not success and not args.dry_run:
        print("\nNote: This is initial setup. To enable auto-generation:")
        print("1. Add markers like {{INSTALLATION}} to README.md")
        print("2. Run this script again")
        print("3. Or create README.template.md with markers")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
