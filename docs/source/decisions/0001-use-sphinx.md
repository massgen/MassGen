# ADR-0001: Use Sphinx for Project Documentation

**Status:** Accepted
**Date:** 2024-10-08 (decision made earlier, documented retroactively)
**Deciders:** @Leezekun, core team
**Technical Story:** Documentation infrastructure setup

## Context and Problem Statement

MassGen needs comprehensive documentation that serves both external users and internal developers. The documentation system must:

- Support both narrative documentation and API reference
- Be extensible with plugins for advanced features
- Support Python docstring auto-generation
- Integrate with GitHub Pages for hosting
- Be maintainable by technical contributors
- Support both Markdown and reStructuredText
- Enable versioned documentation

## Considered Options

1. **Sphinx** - Python documentation generator with extensive ecosystem
2. **MkDocs** - Simpler markdown-based static site generator
3. **Docusaurus** - React-based, modern but requires Node.js ecosystem
4. **GitBook** - Hosted solution with less control
5. **Read the Docs** - Hosting service (works with Sphinx/MkDocs)

## Decision

We chose **Sphinx with Read the Docs theme**.

### Rationale

- **Python ecosystem alignment**: Sphinx is the de facto standard for Python projects
- **API documentation**: Excellent autodoc support for Python docstrings
- **Extensibility**: Rich plugin ecosystem (autodoc, napoleon, myst-parser for Markdown)
- **RST + Markdown**: Supports both via MyST parser for flexibility
- **Mature and stable**: Battle-tested in major Python projects (Django, Flask, NumPy, etc.)
- **Read the Docs integration**: Native support for versioned documentation hosting
- **Cross-referencing**: Powerful intersphinx for linking to external docs

## Consequences

### Positive

- Standard Python documentation toolchain - familiar to contributors
- Excellent API documentation auto-generated from docstrings
- Rich theming options (currently using Read the Docs theme)
- Strong ecosystem with many plugins available
- Good search functionality out of the box
- Support for mathematical notation (important for ML project)
- Can write docs in Markdown (via MyST) or RST

### Negative

- Steeper learning curve than MkDocs (especially for RST)
- Configuration can be complex for advanced features
- Rebuilds can be slow for large documentation sets
- Some contributors may be unfamiliar with RST syntax

### Neutral

- Need to maintain `conf.py` configuration
- RST is more powerful but less intuitive than Markdown
- Build process requires Python environment

## Implementation Notes

- Sphinx setup completed in `/docs/`
- Using `sphinx-rtd-theme` for visual style
- MyST parser enabled for Markdown support
- API docs auto-generated from Python docstrings
- GitHub Actions workflow deploys to GitHub Pages
- Build command: `cd docs && make html`

## Validation

Success metrics:
- ✅ Documentation builds successfully
- ✅ API reference auto-generates from code
- ✅ Deploys automatically to GitHub Pages
- ✅ Contributors can write docs in Markdown or RST
- ✅ Search functionality works

## Related Decisions

- This decision enables case-driven development documentation (ADR-0004)
- Complements the documentation reorganization initiative
- May evolve with improved templates and automation

---

*This ADR documents a decision made during initial project setup. The documentation system continues to evolve with new features like ADRs, RFCs, and track coordination pages.*

*Last updated: 2024-10-08 by @ncrispin*
