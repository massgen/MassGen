#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sync README.md to README_PYPI.md by replacing relative asset paths with full GitHub URLs.

This script:
1. Copies README.md content to README_PYPI.md
2. Replaces relative asset paths with full GitHub URLs for PyPI display

Usage:
    python scripts/sync_readme_pypi.py
    # Or with uv:
    uv run python scripts/sync_readme_pypi.py
"""

from pathlib import Path


def sync_readme_pypi(readme_path: Path, readme_pypi_path: Path, dry_run: bool = False):
    """
    Sync README.md to README_PYPI.md with asset path replacements.

    Args:
        readme_path: Path to README.md
        readme_pypi_path: Path to README_PYPI.md
        dry_run: If True, print changes without writing
    """
    # Read README.md
    readme_content = readme_path.read_text(encoding="utf-8")

    # Replace relative asset paths with full GitHub URLs
    replacements = [
        # Logo images (light and dark)
        (
            "assets/logo.png",
            "https://raw.githubusercontent.com/Leezekun/MassGen/main/assets/logo.png",
        ),
        (
            "assets/logo-dark.png",
            "https://raw.githubusercontent.com/Leezekun/MassGen/main/assets/logo-dark.png",
        ),
        # Demo GIF → Thumbnail for PyPI (replace GIF with static thumbnail from assets)
        (
            "assets/massgen-demo.gif",
            "https://raw.githubusercontent.com/Leezekun/MassGen/main/assets/thumbnail.png",
        ),
        (
            "docs/source/_static/images/readme.gif",
            "https://raw.githubusercontent.com/Leezekun/MassGen/main/docs/source/_static/images/thumbnail.png",
        ),
    ]

    # Apply replacements
    pypi_content = readme_content
    for old_path, new_path in replacements:
        pypi_content = pypi_content.replace(old_path, new_path)

    # Remove PyPI badge from the first row (redundant on PyPI)
    # Replace the entire first badge row to exclude PyPI badge
    old_badge_row = """<div align="center">

[![PyPI](https://img.shields.io/pypi/v/massgen?style=flat-square&logo=pypi&logoColor=white&label=PyPI&color=3775A9)](https://pypi.org/project/massgen/)
[![Docs](https://img.shields.io/badge/docs-massgen.ai-blue?style=flat-square&logo=readthedocs&logoColor=white)](https://docs.massgen.ai)
[![GitHub Stars](https://img.shields.io/github/stars/Leezekun/MassGen?style=flat-square&logo=github&color=181717&logoColor=white)](https://github.com/Leezekun/MassGen)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green?style=flat-square)](LICENSE)

</div>"""

    new_badge_row = """<div align="center">

[![Docs](https://img.shields.io/badge/docs-massgen.ai-blue?style=flat-square&logo=readthedocs&logoColor=white)](https://docs.massgen.ai)
[![GitHub Stars](https://img.shields.io/github/stars/Leezekun/MassGen?style=flat-square&logo=github&color=181717&logoColor=white)](https://github.com/Leezekun/MassGen)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green?style=flat-square)](LICENSE)

</div>"""

    pypi_content = pypi_content.replace(old_badge_row, new_badge_row)

    # Show diff summary
    print("=" * 80)
    print("README_PYPI.md Sync Summary")
    print("=" * 80)
    print(f"\n📄 Copying README.md ({len(readme_content.split(chr(10)))} lines)")
    print("\n🔄 Asset Path Replacements:")
    for old_path, new_path in replacements:
        count = readme_content.count(old_path)
        print(f"   • {old_path}")
        print(f"     → {new_path}")
        print(f"     ({count} occurrence{'s' if count != 1 else ''})")
    print("\n🏷️  Badge Transformations:")
    print("   • Removed PyPI badge (redundant on PyPI)")
    print("   • Kept: Docs | GitHub Stars | Python | License")

    if dry_run:
        print("\n🔍 DRY RUN - No files were modified")
        print("\nPreview of first 500 characters:")
        print("-" * 80)
        print(pypi_content[:500])
        print("...")
        print("-" * 80)
        print("\nRun without --dry-run to apply changes")
    else:
        # Write the new content
        readme_pypi_path.write_text(pypi_content, encoding="utf-8")
        print("\n✅ Successfully synced README_PYPI.md")
        print("✅ Asset paths updated for PyPI display")

    print("=" * 80)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Sync README.md to README_PYPI.md with asset path replacements",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without modifying files",
    )
    parser.add_argument(
        "--readme",
        type=Path,
        default=Path(__file__).parent.parent / "README.md",
        help="Path to README.md (default: repo root)",
    )
    parser.add_argument(
        "--readme-pypi",
        type=Path,
        default=Path(__file__).parent.parent / "README_PYPI.md",
        help="Path to README_PYPI.md (default: repo root)",
    )

    args = parser.parse_args()

    # Verify files exist
    if not args.readme.exists():
        print(f"❌ Error: README.md not found at {args.readme}")
        return 1

    # Sync files
    sync_readme_pypi(args.readme, args.readme_pypi, dry_run=args.dry_run)

    return 0


if __name__ == "__main__":
    exit(main())
