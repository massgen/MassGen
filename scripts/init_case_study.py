#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Add a case study to an existing MassGen release.

This script adds comprehensive case study documentation to an EXISTING release:
- Case study markdown with self-evolution context
- Video recording guide and script templates
- Improvements tracking log
- Video asset directories

Prerequisites:
- Release must already exist (created by init_release.py)
- Release notes should be complete

Usage:
    python scripts/init_case_study.py --version v0.0.30 --feature "Multi-Agent Docs"
    python scripts/init_case_study.py -v v0.0.30 -f "Multi-Agent Docs" --dry-run

"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict


def load_template(template_path: Path, replacements: Dict[str, str]) -> str:
    """
    Load a template file and apply replacements.

    Args:
        template_path: Path to template file
        replacements: Dictionary of {PLACEHOLDER: value} replacements

    Returns:
        Template content with replacements applied
    """
    if not template_path.exists():
        print(f"Warning: Template not found: {template_path}", file=sys.stderr)
        return ""

    content = template_path.read_text()

    for placeholder, value in replacements.items():
        # Replace {PLACEHOLDER} format
        content = content.replace(f"{{{placeholder}}}", value)

    return content


def add_case_study_to_release(
    version: str,
    feature_name: str,
    dry_run: bool = False,
) -> None:
    """
    Add case study documentation to an existing release.

    Args:
        version: Release version (e.g., "v0.0.30")
        feature_name: Name of the primary feature for case study
        dry_run: If True, print actions without creating files
    """
    release_date = datetime.now().strftime("%Y-%m-%d")

    # Clean version string
    if not version.startswith("v"):
        version = f"v{version}"

    # Set up paths
    project_root = Path(__file__).parent.parent
    release_dir = project_root / "docs" / "releases" / version
    templates_dir = project_root / "docs" / "_templates"

    # Check if release exists
    if not release_dir.exists():
        print(f"\nError: Release {version} does not exist!", file=sys.stderr)
        print(f"Please create the release first with:", file=sys.stderr)
        print(f"  python scripts/init_release.py --version {version}\n", file=sys.stderr)
        sys.exit(1)

    # Check if release notes exist
    release_notes_path = release_dir / "release-notes.md"
    if not release_notes_path.exists():
        print(f"\nWarning: release-notes.md not found in {version}", file=sys.stderr)
        print(f"It's recommended to complete release notes before case study.\n", file=sys.stderr)

    # Feature slug for URLs
    feature_slug = feature_name.lower().replace(" ", "-").replace("_", "-")

    # Template replacements
    replacements = {
        "VERSION": version,
        "DATE": release_date,
        "FEATURE_NAME": feature_name,
        "FEATURE_SLUG": feature_slug,
        "TYPE": "Minor",  # Default to Minor, user can update
        "SUMMARY": f"This release introduces {feature_name}.",
        "FEATURE_PURPOSE": f"Enable {feature_name} capabilities in MassGen",
        "FEATURE_DETAILS": "Details to be added",
        "FEATURE_EXAMPLE": "# Example code to be added",
        "CASE_STUDY_FOCUS": feature_name,
        "START_DATE": release_date,
        "COMPLETION_DATE": "TBD",
        "TOTAL_IMPROVEMENTS": "0",
        "TOTAL_BUGS_FIXED": "0",
        "EXECUTIVE_SUMMARY": f"This case study demonstrates {feature_name} in MassGen {version}.",
        "FEATURE_RATIONALE": "Feature rationale to be added after market analysis.",
        "MARKET_GAP": "Market gap to be identified",
        "COMPETITIVE_ANALYSIS": "Competitive analysis to be conducted",
        "USER_FEEDBACK": "User feedback to be gathered",
        "IMPROVEMENT_GOAL_1": "Improve feature X",
        "IMPROVEMENT_GOAL_2": "Enhance capability Y",
        "IMPROVEMENT_GOAL_3": "Optimize performance Z",
        "PROBLEM_DESCRIPTION": "Problem description to be written",
        "LIMITATION_1": "Previous limitation 1",
        "LIMITATION_2": "Previous limitation 2",
        "LIMITATION_3": "Previous limitation 3",
        "IMPACT_DESCRIPTION": "Impact description to be added",
        "FEATURE_OVERVIEW": "Feature overview to be written",
        "TECHNICAL_DETAILS": "Technical implementation details to be added",
        "CAPABILITY_1": "Capability 1",
        "CAPABILITY_1_DETAIL": "Detail for capability 1",
        "CAPABILITY_2": "Capability 2",
        "CAPABILITY_2_DETAIL": "Detail for capability 2",
        "CAPABILITY_3": "Capability 3",
        "CAPABILITY_3_DETAIL": "Detail for capability 3",
        "EXAMPLE_NAME": "example scenario",
        "REASON_1": "Representative of common use case",
        "REASON_2": "Demonstrates key features",
        "REASON_3": "Easy to reproduce",
        "COMMAND_LINE": "massgen --config config.yaml",
        "CONFIG_FILE_CONTENT": "# Configuration to be added",
        "PYTHON_VERSION": "3.10+",
        "DEPENDENCIES": "See requirements.txt",
        "HARDWARE": "Standard laptop/workstation",
        "STEP_1_NAME": "Step 1",
        "STEP_1_DESCRIPTION": "Description of step 1",
        "STEP_1_COMMAND": "command-1",
        "STEP_1_RESULT": "Result of step 1",
        "STEP_2_NAME": "Step 2",
        "STEP_2_DESCRIPTION": "Description of step 2",
        "STEP_2_COMMAND": "command-2",
        "STEP_2_RESULT": "Result of step 2",
        "STEP_3_NAME": "Step 3",
        "STEP_3_DESCRIPTION": "Description of step 3",
        "STEP_3_COMMAND": "command-3",
        "STEP_3_RESULT": "Result of step 3",
        "METRIC_1": "Metric 1",
        "BEFORE_1": "N/A",
        "AFTER_1": "TBD",
        "IMPROVEMENT_1": "TBD",
        "METRIC_2": "Metric 2",
        "BEFORE_2": "N/A",
        "AFTER_2": "TBD",
        "IMPROVEMENT_2": "TBD",
        "METRIC_3": "Metric 3",
        "BEFORE_3": "N/A",
        "AFTER_3": "TBD",
        "IMPROVEMENT_3": "TBD",
        "BENCHMARK_DETAILS": "Benchmark details to be added after testing",
        "BUG_1": "Bug 1",
        "BUG_1_SYMPTOM": "Symptom description",
        "BUG_1_CAUSE": "Root cause",
        "BUG_1_FIX": "Fix description",
        "BUG_1_COMMIT": "commit-hash",
        "IMPROVEMENT_1_BEFORE": "Before state",
        "IMPROVEMENT_1_AFTER": "After state",
        "IMPROVEMENT_1_IMPACT": "Impact description",
        "LEARNING_1": "Learning 1",
        "LEARNING_1_DETAIL": "Details of learning 1",
        "LEARNING_2": "Learning 2",
        "LEARNING_2_DETAIL": "Details of learning 2",
        "LEARNING_3": "Learning 3",
        "LEARNING_3_DETAIL": "Details of learning 3",
        "FUTURE_1": "Future improvement 1",
        "PRIORITY_1": "P1",
        "IMPACT_1": "High",
        "COMPLEXITY_1": "Medium",
        "MARKET_POSITIONING_ANALYSIS": "Market positioning analysis to be conducted",
        "TAKEAWAY_1": "Key takeaway 1",
        "TAKEAWAY_2": "Key takeaway 2",
        "TAKEAWAY_3": "Key takeaway 3",
        "SUCCESS_METRIC_1": "Success metric 1 achieved",
        "SUCCESS_METRIC_2": "Success metric 2 achieved",
        "SUCCESS_METRIC_3": "Success metric 3 achieved",
        "NEXT_STEP_1": "Install MassGen " + version,
        "NEXT_STEP_2": "Review the configuration examples",
        "NEXT_STEP_3": "Try the feature with your own data",
        "API_DOCS_LINK": "https://massgen.readthedocs.io/",
        "COMPLETE_CONFIG": "# Complete configuration to be added",
        "RAW_LOGS": "Raw logs to be added after testing",
        "REPRODUCTION_COMMANDS": "# Reproduction commands to be added",
        "ESTIMATED_TIME": "5-7",
        "COLOR_SCHEME": "Dark background with light text (recommended)",
        "FONT_SIZE": "18",
        "WORKING_DIR": f"~/massgen-demo-{version}",
        "CONFIG_FILE": f"demo_config.yaml",
        "FILE_1": "input.txt",
        "FILE_2": "config.yaml",
        "FILE_3": "data.json",
        "FILE_CREATION_COMMANDS": "# File creation commands to be added",
        "EXAMPLE_SCENARIO": "example scenario",
        "KEY_CONFIG_LINE_1": "# Key config line 1",
        "KEY_CONFIG_LINE_2": "# Key config line 2",
        "KEY_CONFIG_LINE_3": "# Key config line 3",
        "CONFIG_EXPLANATION_1": "Configuration explanation 1",
        "CONFIG_EXPLANATION_2": "Configuration explanation 2",
        "MAIN_COMMAND": f"massgen --config config.yaml",
        "PROGRESS_NOTE_1": "Processing...",
        "PROGRESS_NOTE_2": "Generating output...",
        "RESULT_SUMMARY": "Results completed successfully",
        "KEY_OBSERVATION_1": "observation 1",
        "KEY_OBSERVATION_2": "observation 2",
        "RESULT_FILE_1": "output.txt",
        "METRICS_COMMAND": "cat metrics.json",
        "ADVANCED_CAPABILITY": "advanced capability",
        "ADVANCED_COMMAND": "massgen --advanced-flag",
        "OPTION_COMMAND_1": "massgen --option1",
        "OPTION_COMMAND_2": "massgen --option2",
        "ADVANCED_FEATURE_1": "Advanced feature 1",
        "ADVANCED_FEATURE_2": "Advanced feature 2",
        "OLD_COMMAND": "# Old command",
        "NEW_COMMAND": "# New command",
        "OLD_RESULT": "Old result",
        "NEW_RESULT": "New result",
        "IMPROVEMENT_PERCENTAGE": "50%",
        "RECOMMENDED_FONT_SIZE": "18-20",
        "TOTAL_DURATION": "6:30",
        "TARGET_AUDIENCE": "MassGen users and developers",
        "KEY_MESSAGE": f"{feature_name} makes MassGen more powerful and easier to use",
        "HOOK_STATEMENT": f"See how {feature_name} transforms your workflow",
        "FEATURE_BENEFIT": "improves productivity and capabilities",
        "FEATURE_TAGLINE": feature_name,
        "PROBLEM_TITLE": "Previous limitation",
        "PROBLEM_SYMPTOM": "Symptom of the problem",
        "PROBLEM_IMPACT": "Impact on users",
        "CONFIG_KEY_1": "config_key_1",
        "CONFIG_VALUE_1": "value1",
        "CONFIG_PURPOSE_1": "purpose of config 1",
        "CONFIG_KEY_2": "config_key_2",
        "CONFIG_VALUE_2": "value2",
        "CONFIG_PURPOSE_2": "purpose of config 2",
        "ADDITIONAL_CONFIG_EXPLANATION": "",
        "COMMAND_EXPLANATION": "This command runs MassGen with the new feature",
        "EXECUTION_OBSERVATION_1": "MassGen starts processing",
        "EXECUTION_OBSERVATION_2": "Feature activates successfully",
        "EXECUTION_OBSERVATION_3": "Results are generated",
        "RESULT_METRIC_1": "Metric 1",
        "RESULT_VALUE_1": "Value 1",
        "COMPARISON_1": "comparison 1",
        "RESULT_METRIC_2": "Metric 2",
        "RESULT_VALUE_2": "Value 2",
        "ADVANCED_OPTION_1": "option1",
        "ADVANCED_PURPOSE_1": "purpose 1",
        "ADVANCED_OPTION_2": "option2",
        "ADVANCED_PURPOSE_2": "purpose 2",
        "ADVANCED_BENEFIT": "provides flexibility and power",
        "PREVIOUS_VERSION": version.replace(version.split(".")[-1], str(int(version.split(".")[-1]) - 1)),
        "OLD_APPROACH_DESCRIPTION": "old approach",
        "OLD_TIME": "10 seconds",
        "NEW_APPROACH_DESCRIPTION": "new approach",
        "NEW_TIME": "5 seconds",
        "IMPROVEMENT_METRIC": "execution time",
        "ADDITIONAL_IMPROVEMENT": "Additional improvements noted",
        "MASSGEN_1": "✓",
        "COMP_A_1": "✗",
        "COMP_B_1": "✗",
        "ADVANTAGE_1": "Unique to MassGen",
        "MASSGEN_2": "✓",
        "COMP_A_2": "✓",
        "COMP_B_2": "✗",
        "ADVANTAGE_2": "Better implementation",
        "USE_CASE_1": "Use case 1",
        "USE_CASE_1_BENEFIT": "benefit 1",
        "USE_CASE_2": "Use case 2",
        "USE_CASE_2_BENEFIT": "benefit 2",
        "USE_CASE_3": "Use case 3",
        "USE_CASE_3_BENEFIT": "benefit 3",
        "TIMESTAMP_1_DESCRIPTION": "Introduction and setup",
        "TIMESTAMP_2_DESCRIPTION": "Feature demonstration",
        "TIMESTAMP_3_DESCRIPTION": "Results analysis",
        "TIMESTAMP_4_DESCRIPTION": "Conclusion and next steps",
        "DOCS_URL": "https://massgen.readthedocs.io/",
        "DISCORD_URL": "https://discord.gg/massgen",
        "NEXT_VERSION": f"v{int(version.split('v')[1].split('.')[0])}.{int(version.split('.')[1])}.{int(version.split('.')[2]) + 1}",
        "NEXT_RELEASE_DATE": "TBD",
        "CASE_STUDY_URL": f"https://github.com/Leezekun/MassGen/tree/main/docs/releases/{version}/case-study.md",
        "PR_NUMBER": "XXX",
        "NEXT_PRIORITY_1": "Priority 1 for next release",
        "NEXT_PRIORITY_2": "Priority 2 for next release",
        "NEXT_MEDIUM_1": "Medium priority 1",
        "NEXT_MEDIUM_2": "Medium priority 2",
        "NEXT_LOW_1": "Low priority 1",
        "NEXT_LOW_2": "Low priority 2",
    }

    # Directories to create (release_dir already exists)
    directories = [
        release_dir / "video",
        release_dir / "video" / "raw",
        release_dir / "video" / "editing",
    ]

    # Files to create from templates (skip release-notes.md - already exists)
    template_files = {
        "case-study.md": templates_dir / "case-study-template.md",
        "improvements.md": templates_dir / "improvements-log-template.md",
        "RECORDING_GUIDE.md": templates_dir / "recording-guide-template.md",
        "video-script.md": templates_dir / "video-script-template.md",
    }

    print(f"\n{'='*70}")
    print(f"Adding case study to MassGen {version}")
    print(f"Feature: {feature_name}")
    print(f"{'='*70}\n")

    if dry_run:
        print("DRY RUN MODE - No files will be created\n")

    # Create directories
    print("Creating directory structure:")
    for directory in directories:
        relative_path = directory.relative_to(project_root)
        if dry_run:
            print(f"  Would create: {relative_path}/")
        else:
            directory.mkdir(parents=True, exist_ok=True)
            print(f"  ✓ Created: {relative_path}/")

    print()

    # Create files from templates
    print("Creating files from templates:")
    for filename, template_path in template_files.items():
        output_path = release_dir / filename
        relative_path = output_path.relative_to(project_root)

        if dry_run:
            print(f"  Would create: {relative_path}")
        else:
            content = load_template(template_path, replacements)
            output_path.write_text(content)
            print(f"  ✓ Created: {relative_path}")

    print()

    # Create README for video directory
    video_readme = release_dir / "video" / "README.md"
    video_readme_content = f"""# Video Assets for {version}

This directory contains all video-related assets for the {feature_name} case study.

## Directory Structure

- `demo.mp4` - Final edited demonstration video
- `demo-hq.mp4` - High-quality version (optional)
- `captions.srt` - Subtitle/caption file
- `thumbnail.png` - Video thumbnail (1280x720)
- `raw/` - Raw footage archive
- `editing/` - Editing assets (title cards, overlays, etc.)

## Video Recording

Follow the instructions in `RECORDING_GUIDE.md` in the parent directory.

## Video Editing

See `video-script.md` for detailed editing instructions, timestamps, and captions.

## Status

- [ ] Raw footage recorded
- [ ] Video script created
- [ ] Captions generated
- [ ] Video edited with effects
- [ ] Final video exported
- [ ] Thumbnail created
- [ ] Quality review completed
"""

    if dry_run:
        print(f"  Would create: {(video_readme.relative_to(project_root))}")
    else:
        video_readme.write_text(video_readme_content)
        print(f"  ✓ Created: {video_readme.relative_to(project_root)}")

    print()

    # Update release README to indicate case study was added
    readme_path = release_dir / "README.md"
    if readme_path.exists() and not dry_run:
        readme_content = readme_path.read_text()
        if "- [ ] Case study added (optional)" in readme_content:
            readme_content = readme_content.replace(
                "- [ ] Case study added (optional)",
                "- [x] Case study added (optional)",
            )
            readme_path.write_text(readme_content)
            print(f"  ✓ Updated: {readme_path.relative_to(project_root)}")

    print()

    # Print next steps
    print(f"{'='*70}")
    print("Next Steps - Case Study Creation:")
    print(f"{'='*70}\n")

    print(f"1. Review and customize the case study template:")
    print(f"   docs/releases/{version}/case-study.md\n")

    print(f"2. Update case-study.md with:")
    print(f"   - Self-evolution context (why this feature?)")
    print(f"   - Market insights and competitive analysis")
    print(f"   - Self-improvement goals\n")

    print(f"3. Create configuration file for the demo:")
    print(f"   massgen/configs/tools/{{category}}/{feature_slug}.yaml\n")

    print(f"4. Follow the RECORDING_GUIDE.md to:")
    print(f"   - Set up demo environment")
    print(f"   - Record demonstration video")
    print(f"   - Capture outputs and logs\n")

    print(f"5. Update improvements.md throughout the process:")
    print(f"   - Document bugs discovered")
    print(f"   - Track feature improvements")
    print(f"   - Record insights gained\n")

    print(f"6. After recording, create video-script.md with:")
    print(f"   - Detailed timestamps")
    print(f"   - Narration text")
    print(f"   - Caption markers")
    print(f"   - Editing instructions\n")

    print(f"7. Complete the case study:")
    print(f"   - Write case-study.md with real results")
    print(f"   - Finalize release-notes.md")
    print(f"   - Link all documents together\n")

    print(f"8. Validate with:")
    print(f"   python scripts/validate_case_study.py --version {version}\n")

    if not dry_run:
        print(f"✓ Case study framework added to {version}")
        print(f"  The release can still ship independently.")
        print(f"  Complete the case study at your own pace.")
    else:
        print(f"  (Dry run complete - run without --dry-run to create files)")

    print(f"{'='*70}\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Add case study to an existing MassGen release (must run init_release.py first)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Add case study to existing v0.0.30 release
  python scripts/init_case_study.py --version v0.0.30 --feature "Multi-Agent Documentation"

  # Dry run to see what would be added
  python scripts/init_case_study.py -v v0.0.30 -f "MCP Integration" --dry-run

Prerequisites:
  1. Release must exist (created by init_release.py)
  2. Release notes should be complete

Note: Case study is OPTIONAL and can be added days/weeks after release ships.
        """,
    )

    parser.add_argument(
        "-v",
        "--version",
        required=True,
        help="Release version (e.g., v0.0.30 or 0.0.30)",
    )

    parser.add_argument(
        "-f",
        "--feature",
        required=True,
        help="Primary feature name for case study focus",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without actually creating files",
    )

    args = parser.parse_args()

    try:
        add_case_study_to_release(
            version=args.version,
            feature_name=args.feature,
            dry_run=args.dry_run,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
