#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate roadmap overview from individual track files.

This script parses all track index.md files and generates a status overview
that can be inserted into the main ROADMAP.md file.

Usage:
    python scripts/generate_roadmap_overview.py

Output: Prints markdown table to stdout
"""

import re
from pathlib import Path
from typing import Dict, List, Optional


def parse_track_metadata(track_file: Path) -> Optional[Dict[str, str]]:
    """
    Extract metadata from track index.md file.

    Args:
        track_file: Path to track's index.md file

    Returns:
        Dict with track metadata or None if parsing fails
    """
    try:
        content = track_file.read_text()

        # Extract track name from title
        title_match = re.search(r"^#\s+(.+?)\s+Track", content, re.MULTILINE)
        track_name = title_match.group(1) if title_match else track_file.parent.name

        # Extract lead from header line
        lead_match = re.search(r"\*\*Lead:\*\*\s+(@?\w+)", content)
        lead = lead_match.group(1) if lead_match else "TBD"

        # Extract status emoji from header line
        status_match = re.search(r"\*\*Status:\*\*\s+(🟢|🟡|🔴|⚪)", content)
        status = status_match.group(1) if status_match else "⚪"

        # Find first incomplete P0/P1 task as "Sprint Focus"
        sprint_section = re.search(
            r"## 🎯 Current Sprint.*?\n(.*?)(?=\n##)",
            content,
            re.DOTALL,
        )

        focus = "See track file"
        if sprint_section:
            # Look for first unchecked task in P0 or P1
            tasks_text = sprint_section.group(1)
            p0_p1_match = re.search(
                r"###\s+P[01].*?\n(.*?)(?=###|$)",
                tasks_text,
                re.DOTALL,
            )
            if p0_p1_match:
                first_task = re.search(r"- \[ \] (.+?)(?:\n|$)", p0_p1_match.group(1))
                if first_task:
                    focus = first_task.group(1)[:55]  # Truncate if too long
                    if len(first_task.group(1)) > 55:
                        focus += "..."

        # Count tasks: total unchecked vs total tasks in sprint section
        total_tasks = 0
        completed_tasks = 0

        if sprint_section:
            tasks_text = sprint_section.group(1)
            # Count all tasks (checked and unchecked)
            total_tasks = len(re.findall(r"- \[[ x]\]", tasks_text))
            # Count completed tasks
            completed_tasks = len(re.findall(r"- \[x\]", tasks_text))

        progress = f"{completed_tasks}/{total_tasks}"

        return {
            "name": track_name,
            "lead": lead,
            "status": status,
            "focus": focus,
            "progress": progress,
            "path": track_file.parent.name,
        }

    except Exception as e:
        print(f"Warning: Failed to parse {track_file.name}: {e}")
        return None


def generate_overview_table(tracks: List[Dict]) -> str:
    """
    Generate markdown table from track metadata.

    Args:
        tracks: List of track metadata dicts

    Returns:
        Markdown formatted table string
    """
    # Sort tracks alphabetically by name
    tracks = sorted(tracks, key=lambda t: t["name"].lower())

    lines = [
        "## 🎯 Track Status Overview",
        "",
        "| Track | Lead | Status | Sprint Focus | Progress |",
        "|-------|------|--------|--------------|----------|",
    ]

    for track in tracks:
        # Create link to track file
        track_link = f"[{track['name']}](docs/source/tracks/{track['path']}/index.md)"

        lines.append(
            f"| {track_link} | {track['lead']} | {track['status']} | " f"{track['focus']} | {track['progress']} |",
        )

    lines.extend(
        [
            "",
            "**Status Legend:** 🟢 Active | 🟡 Planning | 🔴 Blocked | ⚪ Paused",
            "",
            "*This table is auto-generated from track files. Run `python scripts/generate_roadmap_overview.py` to update.*",
            "",
        ],
    )

    return "\n".join(lines)


def main():
    """Main function to generate roadmap overview."""
    # Find all track index.md files
    repo_root = Path(__file__).parent.parent
    tracks_dir = repo_root / "docs" / "source" / "tracks"

    track_files = sorted(tracks_dir.glob("*/index.md"))

    print(f"Found {len(track_files)} track files", file=__import__("sys").stderr)

    # Parse all tracks
    tracks = []
    for track_file in track_files:
        metadata = parse_track_metadata(track_file)
        if metadata:
            tracks.append(metadata)
            print(f"  ✓ Parsed: {metadata['name']} Track", file=__import__("sys").stderr)

    print(f"\nSuccessfully parsed {len(tracks)} tracks\n", file=__import__("sys").stderr)

    # Generate and print table
    table = generate_overview_table(tracks)
    print(table)


if __name__ == "__main__":
    main()
