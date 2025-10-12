# MassGen Documentation Includes

This directory contains reusable content snippets that are used across multiple documentation locations (README, Sphinx docs, etc.) to maintain a single source of truth.

## Available Includes

- **installation.md** - Installation instructions for core and optional components
- **api-configuration.md** - API key configuration guide

## Usage in README

To use these includes in the README, use the README auto-generation script:

```bash
python scripts/generate_readme.py
```

This will replace markers in `README.template.md` with the content from these files.

## Usage in Sphinx Docs

In Sphinx RST files, you can include markdown files using:

```rst
.. include:: ../_includes/installation.md
   :parser: myst_parser.sphinx_
```

Or use the `literalinclude` directive for code blocks.

## Maintaining Single Source of Truth

When you need to update installation instructions or API configuration:

1. Edit the file in `docs/_includes/`
2. Run `python scripts/generate_readme.py` to update README
3. Sphinx docs will automatically pick up changes on next build

## Guidelines

- Keep includes focused and modular
- Use clear, concise language
- Include code blocks with proper syntax highlighting
- Update includes when features change
- Test that includes render correctly in both README and Sphinx
