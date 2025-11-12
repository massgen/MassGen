# -*- coding: utf-8 -*-
"""
Skills management for MassGen.

This module provides utilities for discovering and managing skills installed via openskills.
Skills extend agent capabilities with specialized knowledge, workflows, and tools.
"""

import re
from pathlib import Path
from typing import Dict, List

import yaml


def scan_skills(skills_dir: Path) -> List[Dict[str, str]]:
    """Scan both .agent/skills/ and massgen/skills/ for available skills.

    Discovers skills by scanning directories for SKILL.md files and parsing their
    YAML frontmatter metadata. Includes both external skills (from openskills) and
    built-in skills (shipped with MassGen).

    Args:
        skills_dir: Path to external skills directory (typically .agent/skills/).
                   This is where openskills installs skills.

    Returns:
        List of skill dictionaries with keys: name, description, location.
        Location is either "project" (from openskills) or "builtin" (from massgen/skills/).

    Example:
        >>> skills = scan_skills(Path(".agent/skills"))
        >>> print(skills[0])
        {'name': 'pdf', 'description': 'PDF manipulation toolkit...', 'location': 'project'}
    """
    skills = []

    # Scan external skills directory (.agent/skills/)
    if skills_dir.exists():
        skills.extend(_scan_directory(skills_dir, location="project"))

    # Scan built-in skills (massgen/skills/)
    builtin_dir = Path(__file__).parent / "skills"
    if builtin_dir.exists():
        skills.extend(_scan_directory(builtin_dir, location="builtin"))

    return skills


def _scan_directory(directory: Path, location: str) -> List[Dict[str, str]]:
    """Scan a directory for skills.

    Args:
        directory: Directory to scan for skills
        location: Location type ("project" or "builtin")

    Returns:
        List of skill dictionaries with metadata
    """
    skills = []

    if not directory.is_dir():
        return skills

    for skill_path in directory.iterdir():
        if not skill_path.is_dir():
            continue

        # Look for SKILL.md file
        skill_file = skill_path / "SKILL.md"
        if not skill_file.exists():
            continue

        try:
            # Parse YAML frontmatter
            content = skill_file.read_text(encoding="utf-8")
            metadata = parse_frontmatter(content)

            skills.append(
                {
                    "name": metadata.get("name", skill_path.name),
                    "description": metadata.get("description", ""),
                    "location": location,
                },
            )
        except Exception:
            # Skip skills that can't be parsed
            continue

    return skills


def parse_frontmatter(content: str) -> Dict[str, str]:
    """Extract YAML frontmatter from skill file.

    Parses YAML frontmatter delimited by --- markers at the start of a file.
    This is the standard format used by openskills for skill metadata.

    Args:
        content: File content to parse

    Returns:
        Dictionary of metadata from frontmatter

    Example:
        >>> content = '''---
        ... name: example
        ... description: Example skill
        ... ---
        ... # Content here'''
        >>> metadata = parse_frontmatter(content)
        >>> print(metadata['name'])
        'example'
    """
    # Match YAML frontmatter between --- markers
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}

    try:
        # Parse YAML content
        frontmatter = match.group(1)
        metadata = yaml.safe_load(frontmatter)

        # Ensure we return a dict
        if not isinstance(metadata, dict):
            return {}

        return metadata
    except yaml.YAMLError:
        # Fall back to simple key: value parsing if YAML parsing fails
        return _parse_simple_frontmatter(match.group(1))


def _parse_simple_frontmatter(frontmatter: str) -> Dict[str, str]:
    """Simple key: value parser for frontmatter as fallback.

    Args:
        frontmatter: Frontmatter text to parse

    Returns:
        Dictionary of parsed key-value pairs
    """
    metadata = {}
    for line in frontmatter.split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()

    return metadata
