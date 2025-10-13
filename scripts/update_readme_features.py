#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Update README.md with latest features from a release.

This script:
1. Reads release notes from docs/releases/v{VERSION}/release-notes.md
2. Extracts key features and summary
3. Updates README.md "Latest Features" section
4. Archives previous "Latest Features" to massgen/configs/README.md

Tracks:
- Multimodal
- AgentAdapter backends
- Coding Agent
- Web UI
- Irreversible actions
- Memory

Usage:
    python scripts/update_readme_features.py --version v0.0.30
    python scripts/update_readme_features.py -v v0.0.30 --dry-run

"""

import argparse
import re
import sys
from pathlib import Path
from typing import Dict


def extract_features_from_release_notes(release_notes_path: Path) -> Dict[str, any]:
    """
    Extract key information from release notes.

    Args:
        release_notes_path: Path to release-notes.md

    Returns:
        Dictionary with version, summary, features, improvements
    """
    if not release_notes_path.exists():
        raise FileNotFoundError(f"Release notes not found: {release_notes_path}")

    content = release_notes_path.read_text()

    # Extract version
    version_match = re.search(r"# Release (v[\d.]+)", content)
    version = version_match.group(1) if version_match else "unknown"

    # Extract summary (text between ## Summary and next ##)
    summary_match = re.search(r"## Summary\s*\n(.*?)\n##", content, re.DOTALL)
    summary = summary_match.group(1).strip() if summary_match else ""
    # Remove HTML comments
    summary = re.sub(r"<!--.*?-->", "", summary, flags=re.DOTALL).strip()

    # Extract features (text between ## New Features and next ##)
    features_match = re.search(r"## New Features\s*\n(.*?)\n##", content, re.DOTALL)
    features_text = features_match.group(1).strip() if features_match else ""

    # Parse individual features (### Feature Name)
    features = []
    feature_sections = re.findall(r"### (.*?)\n(.*?)(?=###|\Z)", features_text, re.DOTALL)
    for feature_name, feature_content in feature_sections:
        # Extract purpose
        purpose_match = re.search(r"\*\*Purpose:\*\* (.*?)(?:\n|$)", feature_content)
        purpose = purpose_match.group(1).strip() if purpose_match else ""

        features.append(
            {
                "name": feature_name.strip(),
                "purpose": purpose,
            },
        )

    # Extract improvements (bullet points under ## Improvements)
    improvements_match = re.search(r"## Improvements\s*\n(.*?)\n##", content, re.DOTALL)
    improvements = []
    if improvements_match:
        improvements_text = improvements_match.group(1).strip()
        improvements = re.findall(r"^- (.+)$", improvements_text, re.MULTILINE)

    return {
        "version": version,
        "summary": summary,
        "features": features,
        "improvements": improvements,
    }


def format_features_section(release_info: Dict) -> str:
    """
    Format the "Latest Features" section for README.

    Args:
        release_info: Dictionary from extract_features_from_release_notes

    Returns:
        Formatted markdown text
    """
    lines = [
        f"## 🆕 Latest Features ({release_info['version']})",
        "",
    ]

    # Add summary if present
    if release_info["summary"]:
        lines.append(release_info["summary"])
        lines.append("")

    # Add features
    if release_info["features"]:
        for feature in release_info["features"]:
            lines.append(f"### {feature['name']}")
            if feature["purpose"]:
                lines.append(f"{feature['purpose']}")
            lines.append("")

    # Add improvements if any
    if release_info["improvements"]:
        lines.append("**Other Improvements:**")
        for improvement in release_info["improvements"][:3]:  # Limit to top 3
            lines.append(f"- {improvement}")
        if len(release_info["improvements"]) > 3:
            lines.append(f"- *...and {len(release_info['improvements']) - 3} more*")
        lines.append("")

    # Add link to full release notes
    lines.append(f"[📋 Full Release Notes](docs/releases/{release_info['version']}/release-notes.md)")
    lines.append("")

    return "\n".join(lines)


def archive_previous_features(readme_path: Path, archive_path: Path, dry_run: bool = False) -> None:
    """
    Archive the previous "Latest Features" section to configs README.

    Args:
        readme_path: Path to main README.md
        archive_path: Path to massgen/configs/README.md
        dry_run: If True, don't write files
    """
    if not readme_path.exists():
        print(f"Warning: README not found: {readme_path}", file=sys.stderr)
        return

    readme_content = readme_path.read_text()

    # Extract current "Latest Features" section
    latest_match = re.search(
        r"## 🆕 Latest Features.*?\n(.*?)(?=\n## [^L]|\Z)",
        readme_content,
        re.DOTALL,
    )

    if not latest_match:
        print("No 'Latest Features' section found to archive.")
        return

    latest_features = latest_match.group(0)

    # Check if archive file exists
    if not archive_path.exists():
        archive_content = """# MassGen Configuration Archive

This file archives previous "Latest Features" from the main README.

---

"""
    else:
        archive_content = archive_path.read_text()

    # Append to archive (at the end)
    archive_content += "\n" + latest_features + "\n\n---\n"

    if dry_run:
        print(f"Would archive previous features to: {archive_path}")
        print("Preview:")
        print(latest_features[:200] + "...")
    else:
        archive_path.write_text(archive_content)
        print(f"✓ Archived previous features to: {archive_path}")


def update_readme_latest_features(
    readme_path: Path,
    new_features_section: str,
    dry_run: bool = False,
) -> None:
    """
    Update README.md with new "Latest Features" section.

    Args:
        readme_path: Path to README.md
        new_features_section: New features section text
        dry_run: If True, don't write file
    """
    if not readme_path.exists():
        raise FileNotFoundError(f"README not found: {readme_path}")

    readme_content = readme_path.read_text()

    # Find and replace "Latest Features" section
    # Match from ## 🆕 Latest Features to the next ## heading
    pattern = r"## 🆕 Latest Features.*?\n(.*?)(?=\n## [^L]|\Z)"

    if re.search(pattern, readme_content, re.DOTALL):
        # Replace existing section
        updated_content = re.sub(
            pattern,
            new_features_section.rstrip() + "\n\n",
            readme_content,
            flags=re.DOTALL,
        )
    else:
        # Insert after main header/badges if no "Latest Features" exists
        # Find a good insertion point (after badges, before first ## heading)
        insertion_match = re.search(r"(.*?)(## )", readme_content, re.DOTALL)
        if insertion_match:
            updated_content = insertion_match.group(1) + new_features_section + "\n\n" + insertion_match.group(2) + readme_content[insertion_match.end() :]
        else:
            # Fallback: append at end
            updated_content = readme_content + "\n\n" + new_features_section

    if dry_run:
        print("Would update README.md with:")
        print(new_features_section)
    else:
        readme_path.write_text(updated_content)
        print(f"✓ Updated: {readme_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Update README with latest features from a release",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Update README with v0.0.30 features
  python scripts/update_readme_features.py --version v0.0.30

  # Preview changes without writing
  python scripts/update_readme_features.py -v v0.0.30 --dry-run

Workflow:
  1. Archives current "Latest Features" to massgen/configs/README.md
  2. Extracts features from docs/releases/v{VERSION}/release-notes.md
  3. Updates README.md "Latest Features" section

Tracks referenced: Multimodal, AgentAdapter backends, Coding Agent, Web UI,
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
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying files",
    )

    args = parser.parse_args()

    # Clean version
    version = args.version if args.version.startswith("v") else f"v{args.version}"

    # Set up paths
    project_root = Path(__file__).parent.parent
    release_notes_path = project_root / "docs" / "releases" / version / "release-notes.md"
    readme_path = project_root / "README.md"
    archive_path = project_root / "massgen" / "configs" / "README.md"

    print(f"\n{'='*70}")
    print(f"Updating README with features from {version}")
    print(f"{'='*70}\n")

    if args.dry_run:
        print("DRY RUN MODE - No files will be modified\n")

    try:
        # Extract features from release notes
        print(f"Reading release notes: {release_notes_path.relative_to(project_root)}")
        release_info = extract_features_from_release_notes(release_notes_path)
        print(f"✓ Extracted {len(release_info['features'])} features\n")

        # Archive previous features
        print("Archiving previous 'Latest Features' section:")
        archive_previous_features(readme_path, archive_path, args.dry_run)
        print()

        # Format new features section
        new_features_section = format_features_section(release_info)

        # Update README
        print("Updating README.md:")
        update_readme_latest_features(readme_path, new_features_section, args.dry_run)
        print()

        print(f"{'='*70}")
        if not args.dry_run:
            print(f"✓ README updated with {version} features")
            print(f"  - README.md: Latest Features section updated")
            print(f"  - massgen/configs/README.md: Previous features archived")
        else:
            print("Dry run complete - run without --dry-run to apply changes")
        print(f"{'='*70}\n")

    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
