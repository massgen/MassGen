#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validate that a case study is complete and ready for publication.

This script checks:
- All required files exist
- Case study has real content (not placeholders)
- Video assets are present
- Links between documents are valid
- Improvements log has entries
- Configuration files referenced exist

Tracks:
- Multimodal
- AgentAdapter backends
- Coding Agent
- Web UI
- Irreversible actions
- Memory

Usage:
    python scripts/validate_case_study.py --version v0.0.30
    python scripts/validate_case_study.py -v v0.0.30 --strict

"""

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple


class ValidationError:
    """Represents a validation error or warning."""

    def __init__(self, severity: str, category: str, message: str):
        self.severity = severity  # "error" or "warning"
        self.category = category
        self.message = message

    def __str__(self):
        symbol = "❌" if self.severity == "error" else "⚠️ "
        return f"{symbol} [{self.category}] {self.message}"


def check_file_exists(path: Path, required: bool = True) -> List[ValidationError]:
    """Check if a file exists."""
    errors = []
    if not path.exists():
        severity = "error" if required else "warning"
        errors.append(
            ValidationError(
                severity,
                "Files",
                f"Missing {'required' if required else 'optional'} file: {path.name}",
            ),
        )
    return errors


def check_file_not_placeholder(path: Path, placeholder_patterns: List[str]) -> List[ValidationError]:
    """Check if file content has been filled in (not still placeholder text)."""
    errors = []
    if not path.exists():
        return errors

    content = path.read_text()

    for pattern in placeholder_patterns:
        if pattern in content:
            errors.append(
                ValidationError(
                    "warning",
                    "Content",
                    f"{path.name}: Contains placeholder '{pattern}'",
                ),
            )

    return errors


def check_video_assets(video_dir: Path) -> List[ValidationError]:
    """Check video assets are present."""
    errors = []

    if not video_dir.exists():
        errors.append(
            ValidationError(
                "warning",
                "Video",
                "Video directory missing (case study may not be complete)",
            ),
        )
        return errors

    # Check for demo video
    demo_files = list(video_dir.glob("demo.*"))
    if not demo_files:
        errors.append(
            ValidationError(
                "warning",
                "Video",
                "No demo video file found (demo.mp4, demo.mov, etc.)",
            ),
        )

    # Check for captions
    caption_files = list(video_dir.glob("*.srt"))
    if not caption_files:
        errors.append(
            ValidationError(
                "warning",
                "Video",
                "No caption file found (captions.srt)",
            ),
        )

    # Check for thumbnail
    thumbnail_files = list(video_dir.glob("thumbnail.*"))
    if not thumbnail_files:
        errors.append(
            ValidationError(
                "warning",
                "Video",
                "No thumbnail image found",
            ),
        )

    return errors


def check_improvements_log(improvements_path: Path) -> List[ValidationError]:
    """Check improvements log has real entries."""
    errors = []

    if not improvements_path.exists():
        errors.append(
            ValidationError(
                "error",
                "Content",
                "improvements.md missing",
            ),
        )
        return errors

    content = improvements_path.read_text()

    # Check for actual bug/improvement entries
    bug_sections = re.findall(r"### (Critical|Major|Minor) Bugs", content)
    improvement_sections = re.findall(r"### (Implemented|Deferred)", content)

    if not bug_sections and not improvement_sections:
        errors.append(
            ValidationError(
                "warning",
                "Content",
                "improvements.md: No bugs or improvements logged (expected during case study creation)",
            ),
        )

    # Check for placeholder counts
    if "TOTAL_IMPROVEMENTS: 0" in content or "TOTAL_BUGS_FIXED: 0" in content:
        errors.append(
            ValidationError(
                "warning",
                "Content",
                "improvements.md: Totals not updated (still 0)",
            ),
        )

    return errors


def check_case_study_content(case_study_path: Path, project_root: Path) -> List[ValidationError]:
    """Check case study has real content and valid links."""
    errors = []

    if not case_study_path.exists():
        errors.append(
            ValidationError(
                "error",
                "Content",
                "case-study.md missing",
            ),
        )
        return errors

    content = case_study_path.read_text()

    # Check for common placeholders
    placeholders = [
        "{FEATURE_DESCRIPTION}",
        "{PROBLEM_DESCRIPTION}",
        "TBD",
        "TODO",
        "to be added",
        "Details to be",
    ]
    for placeholder in placeholders:
        if placeholder in content:
            errors.append(
                ValidationError(
                    "warning",
                    "Content",
                    f"case-study.md: Contains placeholder '{placeholder}'",
                ),
            )

    # Check for video timestamps
    if "video/" not in content.lower() and ".mp4" not in content.lower():
        errors.append(
            ValidationError(
                "warning",
                "Content",
                "case-study.md: No video references found (expected for complete case study)",
            ),
        )

    # Check for self-evolution context
    if "self-evolution" not in content.lower():
        errors.append(
            ValidationError(
                "warning",
                "Content",
                "case-study.md: Missing self-evolution context",
            ),
        )

    # Check internal links
    links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", content)
    for link_text, link_url in links:
        # Skip external links
        if link_url.startswith("http"):
            continue

        # Resolve relative links
        link_path = case_study_path.parent / link_url
        if not link_path.exists():
            errors.append(
                ValidationError(
                    "error",
                    "Links",
                    f"case-study.md: Broken link to '{link_url}'",
                ),
            )

    return errors


def check_release_notes(release_notes_path: Path) -> List[ValidationError]:
    """Check release notes are complete."""
    errors = []

    if not release_notes_path.exists():
        errors.append(
            ValidationError(
                "error",
                "Content",
                "release-notes.md missing",
            ),
        )
        return errors

    content = release_notes_path.read_text()

    # Check for incomplete sections
    if "## New Features" in content:
        features_section = re.search(r"## New Features(.*?)##", content, re.DOTALL)
        if features_section and "TBD" in features_section.group(1):
            errors.append(
                ValidationError(
                    "warning",
                    "Content",
                    "release-notes.md: Features section has TBD placeholders",
                ),
            )

    # Check for case study link if case study exists
    case_study_path = release_notes_path.parent / "case-study.md"
    if case_study_path.exists():
        if "case-study.md" not in content.lower():
            errors.append(
                ValidationError(
                    "warning",
                    "Links",
                    "release-notes.md: Missing link to case study",
                ),
            )

    return errors


def validate_case_study(version: str, strict: bool = False) -> Tuple[List[ValidationError], List[ValidationError]]:
    """
    Validate a case study release.

    Args:
        version: Release version (e.g., "v0.0.30")
        strict: If True, treat warnings as errors

    Returns:
        Tuple of (errors, warnings)
    """
    # Clean version
    if not version.startswith("v"):
        version = f"v{version}"

    # Set up paths
    project_root = Path(__file__).parent.parent
    release_dir = project_root / "docs" / "releases" / version

    if not release_dir.exists():
        return ([ValidationError("error", "Setup", f"Release directory not found: {version}")], [])

    # Required files
    required_files = [
        release_dir / "release-notes.md",
    ]

    # Optional files (for complete case study)
    optional_files = [
        release_dir / "case-study.md",
        release_dir / "improvements.md",
        release_dir / "RECORDING_GUIDE.md",
        release_dir / "video-script.md",
    ]

    errors = []
    warnings = []

    # Check required files
    for path in required_files:
        errors.extend(check_file_exists(path, required=True))

    # Check optional files (warnings only)
    for path in optional_files:
        warnings.extend(check_file_exists(path, required=False))

    # Check release notes
    errors.extend(check_release_notes(release_dir / "release-notes.md"))

    # If case study exists, validate it thoroughly
    case_study_path = release_dir / "case-study.md"
    if case_study_path.exists():
        errors.extend(check_case_study_content(case_study_path, project_root))
        errors.extend(check_improvements_log(release_dir / "improvements.md"))
        warnings.extend(check_video_assets(release_dir / "video"))

    # Separate errors and warnings
    actual_errors = [e for e in errors if e.severity == "error"]
    actual_warnings = [e for e in errors if e.severity == "warning"] + warnings

    return (actual_errors, actual_warnings)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate MassGen case study completeness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate v0.0.30 case study
  python scripts/validate_case_study.py --version v0.0.30

  # Strict mode: treat warnings as errors
  python scripts/validate_case_study.py -v v0.0.30 --strict

Checks:
  - All required files exist
  - Content has been filled in (not placeholders)
  - Video assets are present
  - Internal links are valid
  - Improvements log has entries
  - Self-evolution context included

Exit codes:
  0 - All checks passed
  1 - Errors found
  2 - Warnings found (strict mode only)

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
        "--strict",
        action="store_true",
        help="Treat warnings as errors",
    )

    args = parser.parse_args()

    print(f"\n{'='*70}")
    print(f"Validating Case Study: {args.version}")
    print(f"{'='*70}\n")

    errors, warnings = validate_case_study(args.version, args.strict)

    # Print results
    if errors:
        print("Errors found:")
        for error in errors:
            print(f"  {error}")
        print()

    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"  {warning}")
        print()

    # Summary
    print(f"{'='*70}")
    if not errors and not warnings:
        print("✅ All checks passed!")
        print(f"   Case study for {args.version} is ready for publication.")
    elif not errors:
        print(f"✅ No errors found ({len(warnings)} warnings)")
        if args.strict:
            print("   ⚠️  Strict mode: Warnings treated as errors")
        else:
            print("   Case study can be published (consider addressing warnings)")
    else:
        print(f"❌ {len(errors)} error(s) found")
        if warnings:
            print(f"⚠️  {len(warnings)} warning(s)")
        print("   Case study needs fixes before publication")
    print(f"{'='*70}\n")

    # Exit code
    if errors:
        return 1
    elif warnings and args.strict:
        return 2
    else:
        return 0


if __name__ == "__main__":
    sys.exit(main())
