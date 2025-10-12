#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto-generate case studies RST from markdown files in docs/case_studies/

This script scans the case studies directory, parses markdown files,
and generates a case_studies.rst file with proper formatting.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional


def parse_case_study(md_file: Path) -> Optional[Dict[str, str]]:
    """
    Parse a case study markdown file and extract metadata.

    Args:
        md_file: Path to markdown file

    Returns:
        Dict with title, task, config, highlights, or None if parsing fails
    """
    try:
        content = md_file.read_text()

        # Extract title (first # heading)
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        title = title_match.group(1) if title_match else md_file.stem.replace("-", " ").replace("_", " ").title()

        # Extract task/problem description
        task_match = re.search(r"##\s+(?:Problem|Task|Description)[:\s]+(.+?)(?=\n##|\Z)", content, re.DOTALL | re.IGNORECASE)
        task = task_match.group(1).strip() if task_match else ""

        # Extract configuration section
        config_match = re.search(r"##\s+Configuration.*?\n```(?:bash|yaml)?\n(.+?)\n```", content, re.DOTALL | re.IGNORECASE)
        config = config_match.group(1).strip() if config_match else ""

        # Extract highlights
        highlights_match = re.search(r"##\s+Highlights.*?\n((?:[-*]\s+.+?\n)+)", content, re.DOTALL | re.IGNORECASE)
        highlights = []
        if highlights_match:
            highlight_lines = highlights_match.group(1).strip().split("\n")
            highlights = [line.strip("- *").strip() for line in highlight_lines if line.strip()]

        # Extract key insights if available
        insights_match = re.search(r"##\s+(?:Insights|Key\s+Findings).*?\n((?:[-*]\s+.+?\n)+)", content, re.DOTALL | re.IGNORECASE)
        insights = []
        if insights_match:
            insight_lines = insights_match.group(1).strip().split("\n")
            insights = [line.strip("- *").strip() for line in insight_lines if line.strip()]

        return {
            "title": title,
            "task": task,
            "config": config,
            "highlights": highlights,
            "insights": insights,
            "filename": md_file.name,
        }
    except Exception as e:
        print(f"Warning: Failed to parse {md_file.name}: {e}")
        return None


def categorize_case_studies(case_studies: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Categorize case studies based on their content and filename.

    Args:
        case_studies: List of parsed case study dicts

    Returns:
        Dict mapping category names to lists of case studies
    """
    categories = {
        "Research and Analysis": [],
        "Travel and Recommendations": [],
        "Creative Writing": [],
        "Technical Analysis": [],
        "Advanced Features": [],
        "Problem Solving": [],
        "Other": [],
    }

    # Keywords for categorization
    keywords = {
        "Research and Analysis": ["conference", "news", "research", "analysis", "berkeley", "ai news", "diverse"],
        "Travel and Recommendations": ["travel", "stockholm", "guide", "recommendations"],
        "Creative Writing": ["creative", "writing", "story"],
        "Technical Analysis": ["algorithm", "fibonacci", "cost", "estimation", "grok", "hle"],
        "Advanced Features": ["workspace", "mcp", "notion", "filesystem", "multi-turn", "context", "integration"],
        "Problem Solving": ["imo", "superintelligence", "winner", "problem"],
    }

    for study in case_studies:
        categorized = False
        title_lower = study["title"].lower()
        filename_lower = study["filename"].lower()

        for category, kw_list in keywords.items():
            if any(kw in title_lower or kw in filename_lower for kw in kw_list):
                categories[category].append(study)
                categorized = True
                break

        if not categorized:
            categories["Other"].append(study)

    # Remove empty categories
    return {k: v for k, v in categories.items() if v}


def generate_rst_content(case_studies: List[Dict]) -> str:
    """
    Generate RST content from case studies.

    Args:
        case_studies: List of parsed case study dicts

    Returns:
        RST formatted string
    """
    rst_lines = [
        "Case Studies",
        "============",
        "",
        "Real-world MassGen case studies demonstrating multi-agent collaboration on complex tasks.",
        "",
        ".. note::",
        "",
        "   These case studies are based on actual MassGen sessions with real session logs and outcomes.",
        "   This page is auto-generated from the `docs/case_studies/ directory <https://github.com/Leezekun/MassGen/tree/main/docs/case_studies>`_.",
        "",
        "Overview",
        "--------",
        "",
        "Each case study includes:",
        "",
        "* **Problem description** - The task or question given to agents",
        "* **Configuration used** - YAML config and CLI command",
        "* **Agent collaboration** - How agents worked together",
        "* **Final outcome** - Results and quality assessment",
        "* **Session logs** - Actual coordination history and voting patterns",
        "",
        f"**Total Case Studies**: {len(case_studies)}",
        "",
    ]

    # Categorize and add case studies
    categorized = categorize_case_studies(case_studies)

    for category, studies in categorized.items():
        rst_lines.append(category)
        rst_lines.append("-" * len(category))
        rst_lines.append("")

        for study in studies:
            # Title
            title = study["title"].replace("Case Study:", "").strip()
            rst_lines.append(title)
            rst_lines.append("~" * len(title))
            rst_lines.append("")

            # Task
            if study["task"]:
                task_lines = study["task"].split("\n")
                rst_lines.append(f"**Task:** {task_lines[0]}")
                rst_lines.append("")

            # Configuration
            if study["config"]:
                rst_lines.append("**Configuration:**")
                rst_lines.append("")
                rst_lines.append(".. code-block:: bash")
                rst_lines.append("")
                for line in study["config"].split("\n"):
                    rst_lines.append(f"   {line}")
                rst_lines.append("")

            # Link to case study
            github_url = f"https://github.com/Leezekun/MassGen/blob/main/docs/case_studies/{study['filename']}"
            rst_lines.append(f"**Case Study:** `{study['filename']} <{github_url}>`_")
            rst_lines.append("")

            # Highlights
            if study["highlights"]:
                rst_lines.append("**Highlights:**")
                rst_lines.append("")
                for highlight in study["highlights"]:
                    rst_lines.append(f"* {highlight}")
                rst_lines.append("")

            # Insights (if available)
            if study["insights"]:
                rst_lines.append("**Key Insights:**")
                rst_lines.append("")
                for insight in study["insights"]:
                    rst_lines.append(f"* {insight}")
                rst_lines.append("")

        rst_lines.append("")

    # Add footer sections
    rst_lines.extend(
        [
            "Running Your Own Case Studies",
            "------------------------------",
            "",
            "To create your own case studies:",
            "",
            "1. Run MassGen with interesting tasks",
            "2. Save session logs and outputs",
            "3. Use the `case-study-template.md <https://github.com/Leezekun/MassGen/blob/main/docs/case_studies/case-study-template.md>`_",
            "4. Submit a pull request to ``docs/case_studies/``",
            "",
            "See :doc:`../user_guide/logging` for details on accessing session logs.",
            "",
            "Contributing",
            "------------",
            "",
            "We welcome new case studies! To contribute:",
            "",
            "* Follow the case study template",
            "* Include configuration and session logs",
            "* Provide clear highlights and insights",
            "* See `Contributing Guidelines <https://github.com/Leezekun/MassGen/blob/main/CONTRIBUTING.md>`_",
            "",
            "Next Steps",
            "----------",
            "",
            "* :doc:`basic_examples` - Start with simpler examples",
            "* :doc:`../user_guide/multi_turn_mode` - Interactive sessions",
            "* :doc:`../user_guide/logging` - Understanding session logs",
            "* :doc:`../user_guide/mcp_integration` - External tool integration",
            "* :doc:`../reference/yaml_schema` - Complete configuration reference",
            "",
        ],
    )

    return "\n".join(rst_lines)


def main():
    """Main function to generate case studies RST."""
    # Paths
    repo_root = Path(__file__).parent.parent.parent
    case_studies_dir = repo_root / "docs" / "case_studies"
    output_file = repo_root / "docs" / "source" / "examples" / "case_studies.rst"

    # Find all markdown case studies (exclude template and README)
    md_files = []
    for md_file in sorted(case_studies_dir.glob("*.md")):
        if md_file.name not in ["case-study-template.md", "README.md"]:
            md_files.append(md_file)

    print(f"Found {len(md_files)} case study files")

    # Parse case studies
    case_studies = []
    for md_file in md_files:
        study = parse_case_study(md_file)
        if study:
            case_studies.append(study)
            print(f"  ✓ Parsed: {study['title']}")

    print(f"\nSuccessfully parsed {len(case_studies)} case studies")

    # Generate RST content
    rst_content = generate_rst_content(case_studies)

    # Write output
    output_file.write_text(rst_content)
    print(f"\n✓ Generated: {output_file}")
    print(f"  Total case studies: {len(case_studies)}")

    # Show categories
    categorized = categorize_case_studies(case_studies)
    print("\nCategories:")
    for category, studies in categorized.items():
        print(f"  {category}: {len(studies)} studies")


if __name__ == "__main__":
    main()
