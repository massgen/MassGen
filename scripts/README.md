# MassGen Scripts

This directory contains automation scripts for MassGen development and documentation maintenance.

## Documentation Automation Scripts

### check_duplication.py

Detects duplicated content across documentation files to maintain single source of truth.

**Purpose:**
- Scans all .rst files for similar paragraphs
- Identifies content that appears in multiple files
- Prevents documentation duplication
- Can run in CI to block PRs with duplication

**Usage:**
```bash
# Basic scan with default settings (80% similarity, 50+ words)
python scripts/check_duplication.py

# Custom threshold
python scripts/check_duplication.py --threshold 0.85 --min-words 40

# Generate report
python scripts/check_duplication.py --output docs/DUPLICATION_REPORT.md
```

**Parameters:**
- `--threshold`: Similarity threshold (0.0-1.0, default: 0.8)
- `--min-words`: Minimum words for paragraph (default: 50)
- `--output`: Output report path (default: docs/DUPLICATION_REPORT.md)

**Exit Codes:**
- `0`: No duplication detected
- `1`: Duplication found (CI should fail)

---

### validate_links.py

Validates cross-references and links in documentation.

**Purpose:**
- Checks all `:doc:` references point to existing files
- Validates anchor references
- Optionally checks external HTTP links
- Can run in CI to prevent broken links

**Usage:**
```bash
# Check internal links only (fast)
python scripts/validate_links.py

# Also check external links (slow)
python scripts/validate_links.py --external

# Generate report
python scripts/validate_links.py --output docs/LINK_VALIDATION_REPORT.md
```

**Parameters:**
- `--external`: Also validate external HTTP links (slow)
- `--output`: Output report path (default: docs/LINK_VALIDATION_REPORT.md)

**Exit Codes:**
- `0`: All links valid
- `1`: Broken links found (CI should fail)

---

### generate_readme.py

Auto-generates README.md from documentation sources.

**Purpose:**
- Keeps README.md in sync with docs
- Extracts content from authoritative sources
- Prevents README drift

**Usage:**
```bash
# Generate README.md
python scripts/generate_readme.py
```

**Synced Content:**
- Backend capability table from `backends.rst`
- Quick start examples from `running-massgen.rst`
- Feature list from `index.rst`
- Installation steps from `installation.rst`

---

## Release Management Scripts

### init_release.py

Initializes a new release with version bumping and changelog generation.

**Usage:**
```bash
python scripts/init_release.py --version 0.0.30
```

---

### package_release.py

Packages a release for distribution.

**Usage:**
```bash
python scripts/package_release.py --version 0.0.30
```

---

### update_readme_release.py

Updates README with latest release information.

**Usage:**
```bash
python scripts/update_readme_release.py --version 0.0.30
```

---

### update_readme_features.py

Updates README with latest features from documentation.

**Usage:**
```bash
python scripts/update_readme_features.py
```

---

## Model Management Scripts

### detect_new_models.py

Detects new AI models from provider APIs.

**Usage:**
```bash
python scripts/detect_new_models.py
```

---

### extract_models.py

Extracts model information for documentation.

**Usage:**
```bash
python scripts/extract_models.py
```

---

## Case Study Management Scripts

### init_case_study.py

Initializes a new case study template.

**Usage:**
```bash
python scripts/init_case_study.py --name "my-case-study"
```

---

### validate_case_study.py

Validates case study format and content.

**Usage:**
```bash
python scripts/validate_case_study.py --path docs/case_studies/my-case-study
```

---

## GitHub Actions Integration

These scripts are designed to run in GitHub Actions CI/CD pipelines:

### Recommended Workflows

**`.github/workflows/docs-automation.yml`:**
```yaml
name: Documentation Automation

on:
  pull_request:
    paths:
      - 'docs/**'
  push:
    branches:
      - main

jobs:
  check-docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Check for duplication
        run: python scripts/check_duplication.py

      - name: Validate links
        run: python scripts/validate_links.py

      - name: Generate README
        run: python scripts/generate_readme.py

      - name: Check for changes
        run: git diff --exit-code README.md || echo "README needs updating"
```

---

## Best Practices

### When to Run Scripts

**During Development:**
- Run `validate_links.py` before committing doc changes
- Run `check_duplication.py` before adding new doc sections
- Run `generate_readme.py` after updating docs

**In CI/CD:**
- Always run validation scripts on doc PRs
- Block merges if validation fails
- Auto-generate README on main branch

**Before Releases:**
- Run all scripts to ensure consistency
- Validate external links with `--external` flag
- Generate fresh README

### Adding New Scripts

When adding new automation scripts:

1. Add shebang line: `#!/usr/bin/env python3`
2. Add docstring explaining purpose and usage
3. Include `--help` argument parsing
4. Use proper exit codes (0 = success, 1 = error)
5. Generate reports in `docs/` directory
6. Update this README with script documentation

---

## Dependencies

Most scripts use only Python standard library. External dependencies:

- `requests` (optional, for external link checking in `validate_links.py`)

Install dependencies:
```bash
pip install requests
```

---

## Troubleshooting

**Script fails with "File not found":**
- Ensure you're running from project root
- Check paths are correct relative to project root

**Link validation finds broken links:**
- Check if referenced file exists
- Verify :doc: syntax is correct
- Check for typos in file paths

**Duplication detected:**
- Review the duplication report
- Consolidate content to primary source
- Add seealso links to other files

**README generation fails:**
- Check that all source files exist
- Verify RST syntax in source files
- Check for encoding issues

---

## Contributing

When modifying scripts:

1. Test thoroughly before committing
2. Update this README with changes
3. Follow Python best practices
4. Add error handling for edge cases
5. Document new parameters in `--help`

---

*Last updated: 2025-10-08*
