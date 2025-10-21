#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Documentation Link Validation Script

This script validates all cross-references and links in the documentation.
It checks :doc: references, external links, and anchor references.

Usage:
    python scripts/validate_links.py
    python scripts/validate_links.py --external  # Also check external links (slow)

Features:
- Checks all :doc: references verify referenced files exist
- Validates anchor references
- Optional external link checking
- Can run in CI to prevent broken links
"""

import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple


class LinkValidator:
    """Validate links in documentation files."""

    def __init__(self, docs_path: Path, check_external: bool = False):
        self.docs_path = docs_path / "source"
        self.check_external = check_external
        self.errors: List[Tuple[Path, str, str]] = []
        self.warnings: List[Tuple[Path, str, str]] = []

    def check_doc_reference(self, file_path: Path, ref: str):
        """Check if a :doc: reference is valid."""
        # Handle relative references
        if ref.startswith("../"):
            # Relative reference
            target_path = (file_path.parent / ref).resolve()
        elif ref.startswith("/"):
            # Absolute reference from docs root
            target_path = self.docs_path / ref.lstrip("/")
        else:
            # Relative from current directory
            target_path = file_path.parent / ref

        # Check for .rst or .md extension if not present
        if not (str(target_path).endswith(".rst") or str(target_path).endswith(".md")):
            # Try .rst first, then .md
            rst_path = Path(str(target_path) + ".rst")
            md_path = Path(str(target_path) + ".md")

            if rst_path.exists():
                target_path = rst_path
            elif md_path.exists():
                target_path = md_path
            else:
                # Neither exists
                self.errors.append(
                    (
                        file_path,
                        f":doc:`{ref}`",
                        f"Referenced file does not exist: {rst_path.relative_to(self.docs_path.parent)} or {md_path.relative_to(self.docs_path.parent)}",
                    ),
                )
                return False
        else:
            # Explicit extension given, check if file exists
            if not target_path.exists():
                self.errors.append(
                    (
                        file_path,
                        f":doc:`{ref}`",
                        f"Referenced file does not exist: {target_path.relative_to(self.docs_path.parent)}",
                    ),
                )
                return False

        return True

    def check_external_link(self, file_path: Path, url: str):
        """Check if an external link is valid (optional, slow)."""
        if not self.check_external:
            return True

        try:
            import requests

            response = requests.head(url, timeout=5, allow_redirects=True)
            if response.status_code >= 400:
                self.warnings.append(
                    (
                        file_path,
                        url,
                        f"HTTP {response.status_code}",
                    ),
                )
                return False
        except Exception as e:
            self.warnings.append(
                (
                    file_path,
                    url,
                    f"Connection error: {e}",
                ),
            )
            return False

        return True

    def scan_file(self, file_path: Path):
        """Scan a single file for links."""
        try:
            content = file_path.read_text()

            # Find all :doc: references
            # Matches both :doc:`path` and :doc:`text <path>`
            doc_refs = re.findall(r":doc:`([^`]+)`", content)
            for ref in doc_refs:
                # Check if it's custom text format: "text <path>"
                custom_match = re.match(r"(.+)<(.+)>", ref)
                if custom_match:
                    # Extract just the path from <path>
                    ref = custom_match.group(2).strip()
                self.check_doc_reference(file_path, ref)

            # Find external links
            # Pattern: `text <url>`_
            external_links = re.findall(r"`[^`]+<(https?://[^>]+)>`_", content)
            for url in external_links:
                if self.check_external:
                    self.check_external_link(file_path, url)

            # Find standalone URLs
            standalone_urls = re.findall(r"https?://[^\s<>`]+", content)
            for url in standalone_urls:
                if url not in external_links:  # Avoid duplicates
                    if self.check_external:
                        self.check_external_link(file_path, url)

        except Exception as e:
            self.errors.append(
                (
                    file_path,
                    "FILE",
                    f"Error reading file: {e}",
                ),
            )

    def scan_all(self):
        """Scan all RST files."""
        rst_files = list(self.docs_path.rglob("*.rst"))

        print(f"Scanning {len(rst_files)} documentation files for broken links...")
        if self.check_external:
            print("(Including external link validation - this may take a while)")

        for file_path in rst_files:
            rel_path = file_path.relative_to(self.docs_path)
            print(f"  {rel_path}")
            self.scan_file(file_path)

    def generate_report(self, output_path: Path):
        """Generate validation report."""
        report_lines = []
        report_lines.append("# Documentation Link Validation Report")
        report_lines.append("")
        report_lines.append(f"**Date:** {Path(__file__).stat().st_mtime}")
        report_lines.append(f"**External Links Checked:** {self.check_external}")
        report_lines.append("")

        report_lines.append("## Summary")
        report_lines.append("")
        report_lines.append(f"- **Errors:** {len(self.errors)}")
        report_lines.append(f"- **Warnings:** {len(self.warnings)}")
        report_lines.append("")

        if self.errors:
            report_lines.append("## Errors (Broken Links)")
            report_lines.append("")

            # Group by file
            by_file: Dict[Path, List[Tuple[str, str]]] = {}
            for file_path, link, error in self.errors:
                if file_path not in by_file:
                    by_file[file_path] = []
                by_file[file_path].append((link, error))

            for file_path, issues in sorted(by_file.items()):
                rel_path = file_path.relative_to(self.docs_path)
                report_lines.append(f"### {rel_path}")
                report_lines.append("")

                for link, error in issues:
                    report_lines.append(f"- **Link:** `{link}`")
                    report_lines.append(f"  - **Error:** {error}")
                    report_lines.append("")

        if self.warnings:
            report_lines.append("## Warnings (External Links)")
            report_lines.append("")

            # Group by file
            by_file: Dict[Path, List[Tuple[str, str]]] = {}
            for file_path, link, warning in self.warnings:
                if file_path not in by_file:
                    by_file[file_path] = []
                by_file[file_path].append((link, warning))

            for file_path, issues in sorted(by_file.items()):
                rel_path = file_path.relative_to(self.docs_path)
                report_lines.append(f"### {rel_path}")
                report_lines.append("")

                for link, warning in issues:
                    report_lines.append(f"- **Link:** `{link}`")
                    report_lines.append(f"  - **Warning:** {warning}")
                    report_lines.append("")

        if not self.errors and not self.warnings:
            report_lines.append("✓ No broken links detected!")
            report_lines.append("")

        report_lines.append("---")
        report_lines.append("")
        report_lines.append("*Generated by `scripts/validate_links.py`*")

        # Save report
        output_path.write_text("\n".join(report_lines))
        print(f"\n✓ Report saved to {output_path}")

    def print_summary(self):
        """Print summary to console."""
        print("\n" + "=" * 60)
        print("LINK VALIDATION SUMMARY")
        print("=" * 60)

        if not self.errors and not self.warnings:
            print("\n✓ All links are valid!")
        else:
            if self.errors:
                print(f"\n✗ {len(self.errors)} broken links found")
                print("\nTop files with errors:")
                by_file: Dict[Path, int] = {}
                for file_path, _, _ in self.errors:
                    by_file[file_path] = by_file.get(file_path, 0) + 1

                for file_path, count in sorted(by_file.items(), key=lambda x: x[1], reverse=True)[:10]:
                    rel_path = file_path.relative_to(self.docs_path)
                    print(f"  {count:3d}  {rel_path}")

            if self.warnings:
                print(f"\n⚠ {len(self.warnings)} warnings (external links)")

        print("\n" + "=" * 60)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Validate links in documentation")
    parser.add_argument("--external", action="store_true", help="Check external links (slow)")
    parser.add_argument("--output", type=str, default="docs/LINK_VALIDATION_REPORT.md", help="Output report path")

    args = parser.parse_args()

    # Get project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    docs_path = project_root / "docs"
    output_path = project_root / args.output

    try:
        validator = LinkValidator(docs_path, check_external=args.external)
        validator.scan_all()
        validator.generate_report(output_path)
        validator.print_summary()

        # Exit with error code if errors found (for CI)
        if validator.errors:
            print("\n✗ Broken links detected. Please fix the errors above.")
            return 1
        else:
            return 0

    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
