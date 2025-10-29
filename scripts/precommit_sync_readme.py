#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pre-commit hook wrapper for syncing README_PYPI.md when README.md changes.

This script stages README_PYPI.md after syncing so it's included in the commit.

Usage:
    python scripts/precommit_sync_readme.py
"""

import subprocess
import sys
from pathlib import Path

from sync_readme_pypi import sync_readme_pypi


def main():
    """Sync README and stage the result."""
    repo_root = Path(__file__).parent.parent
    readme_path = repo_root / "README.md"
    readme_pypi_path = repo_root / "README_PYPI.md"

    # Verify README.md exists
    if not readme_path.exists():
        print(f"❌ Error: README.md not found at {readme_path}")
        return 1

    # Sync the files
    print("🔄 Syncing README_PYPI.md from README.md...")
    try:
        sync_readme_pypi(readme_path, readme_pypi_path, dry_run=False)
    except Exception as e:
        print(f"❌ Error syncing README: {e}")
        return 1

    # Stage the updated README_PYPI.md
    try:
        subprocess.run(
            ["git", "add", str(readme_pypi_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        print(f"✅ Staged {readme_pypi_path.name}")
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Warning: Could not stage {readme_pypi_path.name}: {e}")
        # Don't fail the commit if staging fails
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
