#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Documentation Duplication Detection Script

This script scans all .rst files in the documentation and detects duplicated content.
It identifies paragraphs that appear in multiple files to help maintain single source of truth.

Usage:
    python scripts/check_duplication.py
    python scripts/check_duplication.py --threshold 0.8  # Custom similarity threshold
    python scripts/check_duplication.py --output docs/DUPLICATION_REPORT.md

Features:
- Detects duplicated paragraphs (>50 words, >80% similarity by default)
- Generates detailed duplication report
- Can run in CI to prevent new duplication
- Ignores code blocks and tables
"""

import re
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Tuple


class DuplicationDetector:
    """Detect duplicated content in documentation files."""

    def __init__(self, docs_path: Path, threshold: float = 0.8, min_words: int = 50):
        self.docs_path = docs_path / "source"
        self.threshold = threshold
        self.min_words = min_words
        self.paragraphs: Dict[Path, List[str]] = {}
        self.duplications: List[Tuple[Path, Path, str, float]] = []

    def extract_paragraphs(self, content: str) -> List[str]:
        """Extract paragraphs from RST content, excluding code blocks and tables."""
        # Remove code blocks
        content = re.sub(r".. code-block::.*?\n\n(?:   .*\n)*", "", content, flags=re.DOTALL)

        # Remove list-tables
        content = re.sub(r".. list-table::.*?\n\n(?:   .*\n)*", "", content, flags=re.DOTALL)

        # Remove other directives
        content = re.sub(r".. \w+::.*?\n", "", content)

        # Split into paragraphs
        paragraphs = re.split(r"\n\n+", content)

        # Filter paragraphs
        valid_paragraphs = []
        for para in paragraphs:
            # Clean up
            para = para.strip()

            # Skip section headers (lines of ===, ---, ~~~)
            if re.match(r"^[=\-~]+$", para):
                continue

            # Skip empty or too short
            if not para or len(para.split()) < self.min_words:
                continue

            # Skip if mostly punctuation or symbols
            if sum(c in "=~-*#" for c in para) / len(para) > 0.5:
                continue

            valid_paragraphs.append(para)

        return valid_paragraphs

    def similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two text strings."""
        return SequenceMatcher(None, text1, text2).ratio()

    def scan_files(self):
        """Scan all RST files and extract paragraphs."""
        rst_files = list(self.docs_path.rglob("*.rst"))

        print(f"Scanning {len(rst_files)} documentation files...")

        for file_path in rst_files:
            try:
                content = file_path.read_text()
                paragraphs = self.extract_paragraphs(content)
                self.paragraphs[file_path] = paragraphs
                print(f"  {file_path.relative_to(self.docs_path)}: {len(paragraphs)} paragraphs")
            except Exception as e:
                print(f"  Error reading {file_path}: {e}")

    def find_duplications(self):
        """Find duplicated paragraphs across files."""
        print(f"\nFinding duplications (threshold: {self.threshold}, min words: {self.min_words})...")

        files = list(self.paragraphs.keys())

        for i, file1 in enumerate(files):
            for file2 in files[i + 1 :]:
                # Compare all paragraphs between file1 and file2
                for para1 in self.paragraphs[file1]:
                    for para2 in self.paragraphs[file2]:
                        sim = self.similarity(para1, para2)

                        if sim >= self.threshold:
                            self.duplications.append((file1, file2, para1, sim))

        print(f"Found {len(self.duplications)} potential duplications")

    def generate_report(self, output_path: Path):
        """Generate duplication report."""
        # Group duplications by file pairs
        file_pairs: Dict[Tuple[Path, Path], List[Tuple[str, float]]] = defaultdict(list)

        for file1, file2, para, sim in self.duplications:
            pair = tuple(sorted([file1, file2]))
            file_pairs[pair].append((para, sim))

        # Generate report
        report_lines = []
        report_lines.append("# Documentation Duplication Report")
        report_lines.append("")
        report_lines.append(f"**Date:** {Path(__file__).stat().st_mtime}")
        report_lines.append(f"**Threshold:** {self.threshold * 100}% similarity")
        report_lines.append(f"**Minimum Words:** {self.min_words}")
        report_lines.append("")

        report_lines.append("## Summary")
        report_lines.append("")
        report_lines.append(f"- **Files Scanned:** {len(self.paragraphs)}")
        report_lines.append(f"- **Total Paragraphs:** {sum(len(p) for p in self.paragraphs.values())}")
        report_lines.append(f"- **Duplications Found:** {len(self.duplications)}")
        report_lines.append(f"- **File Pairs with Duplication:** {len(file_pairs)}")
        report_lines.append("")

        if not file_pairs:
            report_lines.append("✓ No significant duplication detected!")
            report_lines.append("")
        else:
            report_lines.append("## Duplication Details")
            report_lines.append("")

            for (file1, file2), duplications in sorted(file_pairs.items(), key=lambda x: len(x[1]), reverse=True):
                rel1 = file1.relative_to(self.docs_path)
                rel2 = file2.relative_to(self.docs_path)

                report_lines.append(f"### {rel1} ↔ {rel2}")
                report_lines.append("")
                report_lines.append(f"**Duplications:** {len(duplications)}")
                report_lines.append("")

                for i, (para, sim) in enumerate(duplications[:3], 1):  # Show first 3
                    report_lines.append(f"#### Duplication {i} ({sim*100:.1f}% similar)")
                    report_lines.append("")
                    preview = para[:200] + "..." if len(para) > 200 else para
                    report_lines.append(f"> {preview}")
                    report_lines.append("")

                if len(duplications) > 3:
                    report_lines.append(f"*...and {len(duplications) - 3} more duplications*")
                    report_lines.append("")

        report_lines.append("---")
        report_lines.append("")
        report_lines.append("*Generated by `scripts/check_duplication.py`*")

        # Save report
        output_path.write_text("\n".join(report_lines))
        print(f"\n✓ Report saved to {output_path}")

    def print_summary(self):
        """Print summary to console."""
        print("\n" + "=" * 60)
        print("DUPLICATION SUMMARY")
        print("=" * 60)

        if not self.duplications:
            print("\n✓ No significant duplication detected!")
            print("  Your documentation follows single source of truth principles.")
        else:
            # Count by file
            file_counts: Dict[Path, int] = defaultdict(int)
            for file1, file2, para, sim in self.duplications:
                file_counts[file1] += 1
                file_counts[file2] += 1

            print(f"\n⚠ Found {len(self.duplications)} duplications")
            print("\nTop files with duplication:")
            for file_path, count in sorted(file_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
                rel_path = file_path.relative_to(self.docs_path)
                print(f"  {count:3d}  {rel_path}")

        print("\n" + "=" * 60)


def main():
    """Main entry point."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Detect duplicated content in documentation")
    parser.add_argument("--threshold", type=float, default=0.8, help="Similarity threshold (0.0-1.0)")
    parser.add_argument("--min-words", type=int, default=50, help="Minimum words for paragraph")
    parser.add_argument("--output", type=str, default="docs/DUPLICATION_REPORT.md", help="Output report path")

    args = parser.parse_args()

    # Get project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    docs_path = project_root / "docs"
    output_path = project_root / args.output

    try:
        detector = DuplicationDetector(docs_path, threshold=args.threshold, min_words=args.min_words)
        detector.scan_files()
        detector.find_duplications()
        detector.generate_report(output_path)
        detector.print_summary()

        # Exit with error code if duplications found (for CI)
        if detector.duplications:
            print("\n⚠ Duplications detected. Review the report and consolidate duplicate content.")
            return 1
        else:
            return 0

    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
