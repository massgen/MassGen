#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Package a MassGen release for publication.

This script performs final checks and packaging:
- Validates case study (if present)
- Updates README with latest features
- Detects and updates model support table
- Creates changelog entry
- Generates GitHub release notes
- Creates release package summary

Tracks:
- Multimodal
- AgentAdapter backends
- Coding Agent
- Web UI
- Irreversible actions
- Memory

Usage:
    python scripts/package_release.py --version v0.0.30
    python scripts/package_release.py -v v0.0.30 --dry-run
    python scripts/package_release.py -v v0.0.30 --skip-validation

"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional


def run_command(cmd: list, description: str, dry_run: bool = False) -> bool:
    """
    Run a command and report results.

    Args:
        cmd: Command to run
        description: Human-readable description
        dry_run: If True, only print what would be done

    Returns:
        True if successful, False otherwise
    """
    print(f"  {description}...")

    if dry_run:
        print(f"    Would run: {' '.join(cmd)}")
        return True

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"    ✓ Success")
        return True
    except subprocess.CalledProcessError as e:
        print(f"    ❌ Failed: {e.stderr}")
        return False


def validate_case_study_if_present(version: str, dry_run: bool = False) -> bool:
    """Validate case study if it exists."""
    print("\n1. Validating case study (if present):")

    if dry_run:
        print("    Would run: python scripts/validate_case_study.py -v " + version)
        return True

    return run_command(
        ["python", "scripts/validate_case_study.py", "-v", version],
        "Running validation checks",
        dry_run,
    )


def update_readme(version: str, dry_run: bool = False) -> bool:
    """Update README with latest features."""
    print("\n2. Updating README 'Latest Features' section:")

    return run_command(
        ["python", "scripts/update_readme_features.py", "-v", version] + (["--dry-run"] if dry_run else []),
        "Extracting and updating features",
        False,  # Don't double-dry-run
    )


def detect_new_models(version: str, prev_version: Optional[str] = None) -> Dict[str, list]:
    """Detect newly added models."""
    print("\n3. Detecting new models:")

    if prev_version is None:
        # Auto-detect previous version
        try:
            result = subprocess.run(
                ["git", "describe", "--tags", "--abbrev=0"],
                capture_output=True,
                text=True,
                check=True,
            )
            prev_version = result.stdout.strip()
            print(f"    Auto-detected previous version: {prev_version}")
        except subprocess.CalledProcessError:
            print("    Warning: Could not auto-detect previous version")
            return {}

    try:
        result = subprocess.run(
            ["python", "scripts/detect_new_models.py", "--prev", prev_version, "--format", "json"],
            capture_output=True,
            text=True,
            check=True,
        )
        import json

        new_models = json.loads(result.stdout)

        if new_models:
            total = sum(len(models) for models in new_models.values())
            print(f"    ✓ Detected {total} new models across {len(new_models)} backends")
            for backend, models in new_models.items():
                print(f"      - {backend}: {', '.join(models)}")
        else:
            print("    No new models detected")

        return new_models
    except Exception as e:
        print(f"    Warning: Could not detect models: {e}")
        return {}


def create_changelog_entry(version: str, release_dir: Path, dry_run: bool = False) -> bool:
    """Create or update changelog entry."""
    print("\n4. Creating changelog entry:")

    changelog_path = Path("CHANGELOG.md")
    release_notes_path = release_dir / "release-notes.md"

    if not release_notes_path.exists():
        print("    ❌ release-notes.md not found")
        return False

    # Read release notes to extract summary
    release_notes = release_notes_path.read_text()

    # Extract summary section
    import re

    summary_match = re.search(r"## Summary\s*\n(.*?)\n##", release_notes, re.DOTALL)
    summary = summary_match.group(1).strip() if summary_match else ""
    summary = re.sub(r"<!--.*?-->", "", summary, flags=re.DOTALL).strip()

    # Extract features
    features_match = re.search(r"## New Features\s*\n(.*?)\n##", release_notes, re.DOTALL)
    features = []
    if features_match:
        feature_sections = re.findall(r"### (.*?)\n", features_match.group(1))
        features = [f.strip() for f in feature_sections if f.strip()]

    # Create changelog entry
    entry = f"""## [{version}] - {datetime.now().strftime("%Y-%m-%d")}

### Summary
{summary}

### New Features
"""
    for feature in features:
        entry += f"- {feature}\n"

    entry += f"""
### Documentation
- [Release Notes](docs/releases/{version}/release-notes.md)
"""

    # Check if case study exists
    if (release_dir / "case-study.md").exists():
        entry += f"- [Case Study](docs/releases/{version}/case-study.md)\n"

    entry += "\n"

    if dry_run:
        print(f"    Would add to {changelog_path}:")
        print("    " + entry.replace("\n", "\n    "))
        return True

    # Read existing changelog
    if changelog_path.exists():
        changelog_content = changelog_path.read_text()
    else:
        changelog_content = "# Changelog\n\nAll notable changes to MassGen will be documented in this file.\n\n"

    # Insert new entry at the top (after header)
    lines = changelog_content.split("\n")
    # Find first ## heading
    insert_idx = next((i for i, line in enumerate(lines) if line.startswith("## [")), len(lines))

    lines.insert(insert_idx, entry)
    changelog_content = "\n".join(lines)

    changelog_path.write_text(changelog_content)
    print(f"    ✓ Added entry to {changelog_path}")

    return True


def generate_release_summary(version: str, release_dir: Path, new_models: Dict, dry_run: bool = False) -> None:
    """Generate a release package summary."""
    print("\n5. Generating release package summary:")

    summary_path = release_dir / "RELEASE_SUMMARY.md"

    # Check what's included
    has_case_study = (release_dir / "case-study.md").exists()
    has_video = (release_dir / "video" / "demo.mp4").exists() or (release_dir / "video" / "demo.mov").exists()

    summary_content = f"""# MassGen {version} - Release Package Summary

**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## Package Contents

✓ Release notes: `release-notes.md`
{'✓' if has_case_study else '✗'} Case study: `case-study.md`
{'✓' if has_video else '✗'} Video demonstration: `video/demo.mp4`

## Release Checklist

- [{"x" if (release_dir / "release-notes.md").exists() else " "}] Release notes completed
- [{"x" if has_case_study else " "}] Case study completed (optional)
- [{"x" if has_video else " "}] Video demonstration (optional)
- [ ] README updated with latest features
- [ ] Changelog entry added
- [ ] GitHub release created
- [ ] PyPI package published

## New Models

"""

    if new_models:
        summary_content += "| Backend | Model ID |\n|---------|----------|\n"
        for backend, models in sorted(new_models.items()):
            for model in models:
                summary_content += f"| {backend} | `{model}` |\n"
    else:
        summary_content += "No new models in this release.\n"

    summary_content += f"""

## GitHub Release Command

```bash
gh release create {version} \\
  --title "MassGen {version}" \\
  --notes-file docs/releases/{version}/release-notes.md
```

## PyPI Publish Command

```bash
# Build package
python -m build

# Upload to PyPI
python -m twine upload dist/*
```

## Post-Release

1. Announce on social media / Discord
2. Update documentation website
3. Close related GitHub issues
4. Start planning next release

## Tracks

This release includes work from:
- Multimodal
- AgentAdapter backends
- Coding Agent
- Web UI
- Irreversible actions
- Memory

---

*Generated by `scripts/package_release.py`*
"""

    if dry_run:
        print(f"    Would create: {summary_path}")
        print("    Preview:")
        print("    " + summary_content[:500].replace("\n", "\n    ") + "...")
    else:
        summary_path.write_text(summary_content)
        print(f"    ✓ Created: {summary_path}")


def package_release(
    version: str,
    prev_version: Optional[str] = None,
    skip_validation: bool = False,
    dry_run: bool = False,
) -> bool:
    """
    Package a release for publication.

    Args:
        version: Release version
        prev_version: Previous version for comparison
        skip_validation: Skip validation step
        dry_run: Don't modify files

    Returns:
        True if successful
    """
    # Clean version
    if not version.startswith("v"):
        version = f"v{version}"

    # Set up paths
    project_root = Path(__file__).parent.parent
    release_dir = project_root / "docs" / "releases" / version

    if not release_dir.exists():
        print(f"Error: Release directory not found: {version}")
        return False

    print(f"\n{'='*70}")
    print(f"Packaging Release: {version}")
    print(f"{'='*70}")

    if dry_run:
        print("\nDRY RUN MODE - No files will be modified\n")

    success = True

    # Step 1: Validate (if case study exists and not skipped)
    if not skip_validation:
        success = validate_case_study_if_present(version, dry_run) and success

    # Step 2: Update README
    success = update_readme(version, dry_run) and success

    # Step 3: Detect new models
    new_models = detect_new_models(version, prev_version)

    # Step 4: Create changelog entry
    success = create_changelog_entry(version, release_dir, dry_run) and success

    # Step 5: Generate summary
    generate_release_summary(version, release_dir, new_models, dry_run)

    # Final summary
    print(f"\n{'='*70}")
    if success:
        print(f"✅ Release package ready for {version}")
        if not dry_run:
            print(f"\nNext steps:")
            print(f"1. Review changes: git diff")
            print(f"2. Commit changes: git add . && git commit -m 'Release {version}'")
            print(f"3. Create tag: git tag {version}")
            print(f"4. Push: git push origin main --tags")
            print(f"5. Create GitHub release:")
            print(f"   gh release create {version} --title '{version}' --notes-file docs/releases/{version}/release-notes.md")
            print(f"6. Publish to PyPI: python -m build && python -m twine upload dist/*")
        else:
            print("Run without --dry-run to package the release")
    else:
        print(f"❌ Some steps failed - review errors above")
    print(f"{'='*70}\n")

    return success


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Package a MassGen release for publication",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Package v0.0.30 for release
  python scripts/package_release.py --version v0.0.30

  # Preview what would be done
  python scripts/package_release.py -v v0.0.30 --dry-run

  # Skip validation (if case study incomplete)
  python scripts/package_release.py -v v0.0.30 --skip-validation

This script:
  1. Validates case study (if present)
  2. Updates README with latest features
  3. Detects new models
  4. Creates changelog entry
  5. Generates release summary

Tracks: Multimodal, AgentAdapter backends, Coding Agent, Web UI,
        Irreversible actions, Memory
        """,
    )

    parser.add_argument(
        "-v",
        "--version",
        required=True,
        help="Release version (e.g., v0.0.30)",
    )

    parser.add_argument(
        "--prev-version",
        help="Previous version for comparison (auto-detected if not provided)",
    )

    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip case study validation",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying files",
    )

    args = parser.parse_args()

    try:
        success = package_release(
            version=args.version,
            prev_version=args.prev_version,
            skip_validation=args.skip_validation,
            dry_run=args.dry_run,
        )
        return 0 if success else 1
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
