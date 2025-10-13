#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Initialize a new MassGen release.

This script creates the release framework that can ship immediately:
- Release directory and notes
- Auto-detect new models and configurations
- Update README "Latest Features" section
- Create changelog entry
- Prepare documentation updates

The case study is SEPARATE and optional - use init_case_study.py to add it later.

Usage:
    python scripts/init_release.py --version v0.0.30
    python scripts/init_release.py -v v0.0.30 --dry-run
    python scripts/init_release.py -v v0.0.30 --prev-version v0.0.29

"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


def get_git_changes(prev_tag: str, current_tag: str = "HEAD") -> Dict[str, List[str]]:
    """
    Get files changed between two git tags/commits.

    Args:
        prev_tag: Previous version tag (e.g., "v0.0.29")
        current_tag: Current version tag or "HEAD"

    Returns:
        Dictionary with categories of changed files
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", prev_tag, current_tag],
            capture_output=True,
            text=True,
            check=True,
        )
        files = result.stdout.strip().split("\n")

        changes = {
            "models": [],
            "configs": [],
            "tools": [],
            "docs": [],
            "tests": [],
            "other": [],
        }

        for file in files:
            if not file:
                continue

            if "backends" in file or "models" in file:
                changes["models"].append(file)
            elif "configs" in file:
                changes["configs"].append(file)
            elif "tools" in file:
                changes["tools"].append(file)
            elif "docs" in file:
                changes["docs"].append(file)
            elif "tests" in file:
                changes["tests"].append(file)
            else:
                changes["other"].append(file)

        return changes
    except subprocess.CalledProcessError:
        print(f"Warning: Could not get git diff for {prev_tag}..{current_tag}", file=sys.stderr)
        return {"models": [], "configs": [], "tools": [], "docs": [], "tests": [], "other": []}


def detect_new_models(prev_tag: str) -> List[Dict[str, str]]:
    """
    Detect new models added since previous version.

    Args:
        prev_tag: Previous version tag

    Returns:
        List of dicts with backend, model_id, description
    """
    # This is a placeholder - actual implementation would parse backend files
    # and compare with previous version
    changes = get_git_changes(prev_tag)
    new_models = []

    for file in changes["models"]:
        if file.endswith(".py"):
            # Parse file for new model definitions
            # This is simplified - real implementation would parse the actual model IDs
            pass

    return new_models


def detect_new_configs(prev_tag: str) -> List[str]:
    """
    Detect new configuration files added since previous version.

    Args:
        prev_tag: Previous version tag

    Returns:
        List of new config file paths
    """
    changes = get_git_changes(prev_tag)
    new_configs = []

    for file in changes["configs"]:
        if file.endswith(".yaml") or file.endswith(".yml"):
            # Check if this is a new file (not just modified)
            try:
                result = subprocess.run(
                    ["git", "diff", prev_tag, "HEAD", "--", file],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                # If file is completely new, the diff will show all additions
                if "new file" in result.stdout or result.stdout.startswith("diff --git"):
                    new_configs.append(file)
            except subprocess.CalledProcessError:
                pass

    return new_configs


def create_release_framework(
    version: str,
    prev_version: Optional[str] = None,
    dry_run: bool = False,
) -> None:
    """
    Create the release framework that can ship immediately.

    Args:
        version: Release version (e.g., "v0.0.30")
        prev_version: Previous version for comparison (auto-detected if not provided)
        dry_run: If True, print actions without creating files
    """
    # Clean version string
    if not version.startswith("v"):
        version = f"v{version}"

    release_date = datetime.now().strftime("%Y-%m-%d")

    # Set up paths
    project_root = Path(__file__).parent.parent
    release_dir = project_root / "docs" / "releases" / version

    # Auto-detect previous version if not provided
    if prev_version is None:
        try:
            result = subprocess.run(
                ["git", "describe", "--tags", "--abbrev=0"],
                capture_output=True,
                text=True,
                check=True,
            )
            prev_version = result.stdout.strip()
        except subprocess.CalledProcessError:
            prev_version = None

    print(f"\n{'='*70}")
    print(f"Initializing Release Framework for MassGen {version}")
    print(f"Release Date: {release_date}")
    if prev_version:
        print(f"Previous Version: {prev_version}")
    print(f"{'='*70}\n")

    if dry_run:
        print("DRY RUN MODE - No files will be created\n")

    # Create release directory
    print("Creating release directory:")
    if dry_run:
        print(f"  Would create: docs/releases/{version}/")
    else:
        release_dir.mkdir(parents=True, exist_ok=True)
        print(f"  ✓ Created: docs/releases/{version}/")

    print()

    # Detect changes from previous version
    if prev_version:
        print(f"Analyzing changes since {prev_version}:")
        changes = get_git_changes(prev_version)

        print(f"  Models/Backends: {len(changes['models'])} files changed")
        print(f"  Configurations: {len(changes['configs'])} files changed")
        print(f"  Tools: {len(changes['tools'])} files changed")
        print(f"  Documentation: {len(changes['docs'])} files changed")
        print(f"  Tests: {len(changes['tests'])} files changed")
        print(f"  Other: {len(changes['other'])} files changed")
        print()

        # Detect new models
        new_models = detect_new_models(prev_version)
        if new_models:
            print("New models detected:")
            for model in new_models:
                print(f"  - {model['backend']}: {model['model_id']}")
            print()

        # Detect new configs
        new_configs = detect_new_configs(prev_version)
        if new_configs:
            print("New configuration files:")
            for config in new_configs:
                print(f"  - {config}")
            print()

    # Create minimal release notes template
    release_notes_content = f"""# Release {version}

**Release Date:** {release_date}

**Release Type:** Minor

---

## Summary

<!-- Brief 2-3 sentence overview of this release -->

This release includes [key features/improvements].

---

## New Features

### Feature Name

**Purpose:** Brief description of what this feature does

**Usage:**
```python
# Example usage
```

**Documentation:** See [Feature Guide](../../features/feature-name.md)

---

## Improvements

- Improvement 1
- Improvement 2
- Improvement 3

---

## Bug Fixes

- Fixed: Bug description (#issue-number)
- Fixed: Another bug description (#issue-number)

---

## Configuration Changes

### New Configuration Options

```yaml
# New configuration options
```

---

## Model Support

### New Models Added

| Backend | Model ID | Description |
|---------|----------|-------------|
| TBD | TBD | TBD |

---

## Breaking Changes

<!-- Remove this section if no breaking changes -->

None in this release.

---

## Dependencies

### Updated
- dependency: version

---

## Installation

```bash
pip install --upgrade massgen=={version}
```

Or with uv:
```bash
uv pip install --upgrade massgen=={version}
```

---

## Next Steps

**For Users:**
1. Upgrade to {version}
2. Review new features and configuration options
3. Check for any breaking changes that might affect your setup

**For Contributors:**
- Case study documentation (optional): Use `scripts/init_case_study.py -v {version}`
- See [CONTRIBUTING.md](../../../CONTRIBUTING.md) for guidelines

---

## Links

- **GitHub Release:** https://github.com/Leezekun/MassGen/releases/tag/{version}
- **Documentation:** https://massgen.readthedocs.io/
- **Changelog:** [CHANGELOG.md](../../../CHANGELOG.md)
"""

    # Write release notes
    release_notes_path = release_dir / "release-notes.md"
    if dry_run:
        print(f"Would create: docs/releases/{version}/release-notes.md")
    else:
        release_notes_path.write_text(release_notes_content)
        print(f"✓ Created: docs/releases/{version}/release-notes.md")

    print()

    # Create README for release directory
    readme_content = f"""# MassGen {version} Release

**Release Date:** {release_date}

## Contents

- `release-notes.md` - Complete release notes (features, fixes, changes)

## Optional: Add Case Study

To add a comprehensive case study with video demonstration:

```bash
python scripts/init_case_study.py --version {version} --feature "Feature Name"
```

This will create:
- `case-study.md` - In-depth feature walkthrough
- `RECORDING_GUIDE.md` - Video recording instructions
- `video-script.md` - Video narration and captions
- `improvements.md` - Bug/improvement tracking log
- `video/` - Video assets directory

## Status

- [x] Release notes created
- [ ] Release notes completed with actual content
- [ ] README "Latest Features" updated
- [ ] Changelog entry added
- [ ] Documentation updated
- [ ] GitHub release created
- [ ] Case study added (optional)
"""

    readme_path = release_dir / "README.md"
    if dry_run:
        print(f"Would create: docs/releases/{version}/README.md")
    else:
        readme_path.write_text(readme_content)
        print(f"✓ Created: docs/releases/{version}/README.md")

    print()

    # Print next steps
    print(f"{'='*70}")
    print("Next Steps - Release Framework:")
    print(f"{'='*70}\n")

    print(f"1. Complete release notes:")
    print(f"   docs/releases/{version}/release-notes.md")
    print(f"   - Document all new features")
    print(f"   - List bug fixes with issue numbers")
    print(f"   - Note any breaking changes")
    print(f"   - Update model support table\n")

    print(f"2. Update README 'Latest Features' section:")
    print(f"   python scripts/update_readme_features.py --version {version}\n")

    print(f"3. Add changelog entry:")
    print(f"   Edit CHANGELOG.md with summary from release notes\n")

    print(f"4. Update documentation:")
    print(f"   - API docs (if needed)")
    print(f"   - User guides (if new features)")
    print(f"   - Configuration docs (if new options)\n")

    print(f"5. Create GitHub release:")
    print(f'   gh release create {version} --title "{version}" --notes-file docs/releases/{version}/release-notes.md\n')

    print(f"6. (Optional) Add comprehensive case study later:")
    print(f'   python scripts/init_case_study.py --version {version} --feature "Feature Name"\n')

    if not dry_run:
        print(f"✓ Release framework initialized for {version}")
        print(f"  You can now complete the release notes and ship immediately.")
        print(f"  The case study can be added later without blocking the release.")
    else:
        print(f"  (Dry run complete - run without --dry-run to create files)")

    print(f"{'='*70}\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Initialize a new MassGen release framework (ships without case study)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Initialize release framework for v0.0.30
  python scripts/init_release.py --version v0.0.30

  # Initialize with explicit previous version for comparison
  python scripts/init_release.py -v v0.0.30 --prev-version v0.0.29

  # Dry run to see what would be created
  python scripts/init_release.py -v v0.0.30 --dry-run

Note: This creates the minimal release framework that can ship immediately.
      Use init_case_study.py separately to add optional case study later.
        """,
    )

    parser.add_argument(
        "-v",
        "--version",
        required=True,
        help="Release version (e.g., v0.0.30 or 0.0.30)",
    )

    parser.add_argument(
        "--prev-version",
        help="Previous version for comparison (auto-detected if not provided)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without actually creating files",
    )

    args = parser.parse_args()

    try:
        create_release_framework(
            version=args.version,
            prev_version=args.prev_version,
            dry_run=args.dry_run,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
