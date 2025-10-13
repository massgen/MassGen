#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Update README.md with new release information.

This script:
1. Extracts content from docs/releases/vX.X.X/features-overview-short.md
2. Updates README.md's "What's New" section
3. Archives previous release info to "Previous Releases" section

Usage:
    python scripts/update_readme_release.py v0.0.29
"""

import re
import sys
from pathlib import Path


def extract_whats_new_content(features_overview_path: Path) -> str:
    """Extract the main content from features-overview-short.md."""
    content = features_overview_path.read_text()

    # Remove the title line and first separator
    lines = content.split("\n")

    # Skip title and metadata line, start from "What's New"
    start_idx = 0
    for i, line in enumerate(lines):
        if line.startswith("## What's New"):
            start_idx = i
            break

    # Extract until "Resources" or "Contributors" section
    end_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        if lines[i].startswith("## Resources") or lines[i].startswith("## Contributors"):
            end_idx = i
            break

    extracted = "\n".join(lines[start_idx:end_idx]).strip()
    return extracted


def extract_previous_release_summary(readme_content: str) -> tuple[str, str]:
    """Extract current 'What's New' to become 'Previous Release'."""
    # Find the current What's New section
    pattern = r"## What\'s New in v(\d+\.\d+\.\d+).*?\n(.*?)(?=\n## |$)"
    match = re.search(pattern, readme_content, re.DOTALL)

    if not match:
        return None, None

    version = match.group(1)
    content = match.group(2).strip()

    # Extract just the first paragraph/bullet list (short summary)
    lines = content.split("\n")
    summary_lines = []

    for line in lines:
        # Stop at Resources or detailed sections
        if "Resources:" in line or "[Full Release Notes]" in line:
            break
        if line.startswith("**") or line.startswith("-") or line.startswith("###"):
            summary_lines.append(line)
        elif summary_lines and line.strip():  # Continue until blank line after content started
            summary_lines.append(line)
        elif summary_lines and not line.strip():  # Blank line after content
            break

    summary = "\n".join(summary_lines).strip()
    return version, summary


def update_readme(
    readme_path: Path,
    new_version: str,
    new_content: str,
    prev_version: str = None,
    prev_summary: str = None,
) -> None:
    """Update README.md with new release information."""

    readme_content = readme_path.read_text()

    # Create new What's New section
    new_whats_new = f"""## What's New in v{new_version} 🎉

{new_content}

📖 [Features Overview](docs/releases/v{new_version}/features-overview-short.md) | 📝 [Full Release Notes](docs/releases/v{new_version}/release-notes.md) | 🎥 [Video Demo](https://youtu.be/jLrMMEIr118)

---
"""

    # Find existing What's New section
    whats_new_pattern = r"## What\'s New in v\d+\.\d+\.\d+.*?\n---\n"

    if re.search(whats_new_pattern, readme_content, re.DOTALL):
        # Replace existing What's New
        readme_content = re.sub(
            whats_new_pattern,
            new_whats_new,
            readme_content,
            count=1,
            flags=re.DOTALL,
        )
    else:
        # Insert after main header/description
        # Find a good insertion point (after ## Features or ## Quick Start)
        insertion_point = readme_content.find("## Features")
        if insertion_point == -1:
            insertion_point = readme_content.find("## Quick Start")
        if insertion_point == -1:
            insertion_point = readme_content.find("## Installation")

        if insertion_point != -1:
            readme_content = readme_content[:insertion_point] + new_whats_new + "\n" + readme_content[insertion_point:]

    # Update or create Previous Releases section
    if prev_version and prev_summary:
        prev_releases_marker = "## Previous Releases"

        if prev_releases_marker in readme_content:
            # Add to existing Previous Releases
            marker_pos = readme_content.find(prev_releases_marker)
            # Find the next section after Previous Releases
            next_section_match = re.search(r"\n## ", readme_content[marker_pos + len(prev_releases_marker) :])

            if next_section_match:
                insert_pos = marker_pos + len(prev_releases_marker) + next_section_match.start()
                new_prev_entry = f"\n\n**v{prev_version}**\n{prev_summary}\n\n[See full notes →](docs/releases/v{prev_version}/release-notes.md)\n"
                readme_content = readme_content[:insert_pos] + new_prev_entry + readme_content[insert_pos:]
        else:
            # Create Previous Releases section after What's New
            whats_new_end = readme_content.find("---\n", readme_content.find("## What's New"))
            if whats_new_end != -1:
                whats_new_end += 4  # Skip the ---\n
                prev_releases_section = f"""\n## Previous Releases

**v{prev_version}**
{prev_summary}

[See full notes →](docs/releases/v{prev_version}/release-notes.md)

---

"""
                readme_content = readme_content[:whats_new_end] + prev_releases_section + readme_content[whats_new_end:]

    # Write updated README
    readme_path.write_text(readme_content)
    print(f"✅ Updated README.md with v{new_version} release information")
    if prev_version:
        print(f"✅ Archived v{prev_version} to Previous Releases section")


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/update_readme_release.py v0.0.29")
        sys.exit(1)

    version = sys.argv[1]
    if not version.startswith("v"):
        version = f"v{version}"

    # Paths
    repo_root = Path(__file__).parent.parent
    features_overview = repo_root / "docs" / "releases" / version / "features-overview-short.md"
    readme_path = repo_root / "README.md"

    # Validate files exist
    if not features_overview.exists():
        print(f"❌ Error: {features_overview} not found")
        print(f"   Create features-overview-short.md for {version} first")
        sys.exit(1)

    if not readme_path.exists():
        print(f"❌ Error: {readme_path} not found")
        sys.exit(1)

    # Extract new content
    print(f"📄 Extracting content from {features_overview.name}...")
    new_content = extract_whats_new_content(features_overview)

    # Extract previous release info
    print("📋 Extracting previous release info from README...")
    readme_content = readme_path.read_text()
    prev_version, prev_summary = extract_previous_release_summary(readme_content)

    # Update README
    print(f"✏️  Updating README.md...")
    update_readme(
        readme_path,
        version.lstrip("v"),
        new_content,
        prev_version,
        prev_summary,
    )

    print(f"\n✨ Done! README.md updated with {version} release information")
    print(f"\nNext steps:")
    print(f"  1. Review the changes: git diff README.md")
    print(f"  2. Commit: git add README.md && git commit -m 'docs: update README for {version}'")


if __name__ == "__main__":
    main()
