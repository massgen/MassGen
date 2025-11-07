#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pre-commit hook to validate MassGen configuration files.

This script is called by pre-commit for any changed YAML files in massgen/configs/.
It validates each file and exits with non-zero if any have errors.

Usage:
    python scripts/precommit_validate_configs.py file1.yaml file2.yaml ...
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from massgen.config_validator import ConfigValidator  # noqa: E402


def main():
    """Validate config files passed as arguments."""
    if len(sys.argv) < 2:
        print("Usage: precommit_validate_configs.py file1.yaml file2.yaml ...")
        return 0  # No files to validate

    validator = ConfigValidator()
    failed_files = []

    for config_file in sys.argv[1:]:
        # Only validate if file still exists (could be deleted)
        if not Path(config_file).exists():
            continue

        result = validator.validate_config_file(config_file)

        if result.has_errors():
            failed_files.append(config_file)
            print(f"\n❌ Validation failed: {config_file}")
            print(result.format_errors())

    if failed_files:
        print("\n" + "=" * 80)
        print(f"❌ {len(failed_files)} config file(s) failed validation")
        print("=" * 80)
        print("\nFix the errors above before committing.")
        print("Or run: massgen --validate <file> to validate manually")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
