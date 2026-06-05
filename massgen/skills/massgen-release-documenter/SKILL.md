---
name: massgen-release-documenter
description: Guide for following MassGen's release documentation workflow. This skill should be used when preparing release documentation, updating changelogs, writing case studies, or maintaining project documentation across releases.
license: MIT
---

# Release Documenter

This skill provides guidance for documenting MassGen releases following the established workflow and conventions.

## Purpose

The release-documenter skill ensures consistent, complete release documentation by guiding you through the full release documentation workflow: CHANGELOG → Sphinx Documentation → README → Roadmap updates.

## When to Use This Skill

Use the release-documenter skill when you need to:

- Prepare documentation for a new release
- Update CHANGELOG.md with new features and fixes
- Write or update Sphinx documentation
- Create case studies for major features
- Update README.md and roadmap documents
- Follow the release checklist process

## Authoritative Documentation

**IMPORTANT:** The primary source of truth for release documentation is:

**📋 `docs/dev_notes/release_checklist.md`**

This file contains:
- Complete phase-by-phase release workflow
- Detailed documentation update requirements
- Validation checklists
- Commit and tag workflow
- Automation tool information
- All current conventions and rules

**Always consult this document** for the complete release process.

## Critical Documentation Order

**Always follow this order:**

0. **Fresh-branch bootstrap** (once, at branch creation) — version bump + rename `ROADMAP_v0.1.X.md` → `ROADMAP_v0.1.X+1.md` (see Phase 0)
1. **CHANGELOG.md** ⭐ START HERE
2. **Version bump** (`massgen/__init__.py` `__version__`)
3. **Sphinx Documentation** (docs/source/)
4. **Config Documentation** (massgen/configs/README.md)
5. **Case Studies** (docs/source/examples/case_studies/)
6. **README.md**
7. **README_PYPI.md** (auto-synced via pre-commit)
8. **Roadmap** (ROADMAP.md)
9. **Announcements** (docs/announcements/) — current-release.md, github-release-vX.md, archive

This order is critical - never skip ahead!

## Quick Reference Workflow

### Phase 0: Fresh Release Branch Bootstrap (do this when the branch is created)

**⚠️ Easy to miss — this happens once, at the *start* of a new `dev/v0.1.X` branch, not at doc-writing time.** When `dev/v0.1.X` is branched (right after the previous release merges in), a small bootstrap commit (`feat: v0.1.X`) sets the branch up:

1. **Bump the version**: `massgen/__init__.py` `__version__ = "0.1.X"` (`pyproject.toml` reads it dynamically).
2. **Roll the forward-looking roadmap file**: rename `ROADMAP_v0.1.X.md` → `ROADMAP_v0.1.X+1.md` and rewrite its content to plan the *next* release. This file always names the version *after* the one currently in development (the in-development version is tracked in the main `ROADMAP.md` sections). Update its title, "Overview", the deferred-feature "Deferred from …" range, and add the just-shipped version(s) to its "Related Tracks" list.

```bash
git mv ROADMAP_v0.1.X.md ROADMAP_v0.1.X+1.md
# then edit __version__ and the renamed roadmap file
```

> If you arrive mid-branch and find `ROADMAP_v0.1.X.md` (matching the in-dev version) still present, or `__version__` still on the previous release, the bootstrap was skipped — do it now before the release docs.

### Phase 1: CHANGELOG.md (Required First Step)

Document all changes under these categories:
- **Added** - New features
- **Changed** - Modified behavior
- **Fixed** - Bug fixes
- **Documentations, Configurations and Resources** - New docs/configs
- **Technical Details** - Contributors, focus areas

```bash
# Get changes since last release
git log v0.1.X-1..HEAD --oneline
gh pr list --base dev/v0.1.X --state merged
```

See `docs/dev_notes/release_checklist.md` sections 3.1 for detailed format.

### Phase 2: Sphinx Documentation

Update as needed:
- `docs/source/index.rst` - Recent Releases section (keep latest 3)
- `docs/source/user_guide/` - New feature guides
- `docs/source/reference/yaml_schema.rst` - New YAML parameters
- `docs/source/reference/supported_models.rst` - New models

**Build and verify:**
```bash
cd docs && make html
make linkcheck  # Verify no broken links
```

See `docs/dev_notes/release_checklist.md` section 3.2 for complete requirements.

### Phase 3: Config Documentation

- Update `massgen/configs/README.md`
- Create example configs in appropriate category
- Test all new configs

### Phase 4: Case Studies

```bash
# Use template
cp docs/source/examples/case_studies/case-study-template.md \
   docs/source/examples/case_studies/v0.1.X-feature-name.md

# Update index
vim docs/source/examples/case_studies.rst
```

See `docs/dev_notes/release_checklist.md` section 3.4.

### Phase 5: README.md

Update these sections:
1. **Recent Achievements** (move old to Previous Achievements)
2. **Case Studies** section
3. **Configuration Files** (if structure changed)

Copy format from CHANGELOG.md and expand.

### Phase 6: README_PYPI.md (Automated)

**✅ Auto-synced via pre-commit hook!**

When you commit README.md changes:
1. Pre-commit hook runs automatically
2. README_PYPI.md gets synced
3. If hook shows "Failed - files were modified", run `git commit` again

Manual sync if needed:
```bash
uv run python scripts/sync_readme_pypi.py
```

### Phase 7: Roadmap

- Mark completed features as ✅ in `ROADMAP.md`
- Update `ROADMAP_v0.1.X+1.md` for next release
- Do NOT edit `docs/source/development/roadmap.rst` (auto-generated)

### Phase 8: Announcements (`docs/announcements/`)

**⚠️ Easy to miss — not auto-generated.** Each release rotates three things in `docs/announcements/`:

1. **Archive the outgoing announcement**: copy the current `current-release.md` to `archive/v0.1.X-1.md` (the version it currently describes).
   ```bash
   cp docs/announcements/current-release.md docs/announcements/archive/v0.1.X-1.md
   ```
2. **Rewrite `current-release.md`** for the new version: update the title, Release Summary, Install version, release-notes link, "Suggested image" version, and the full LinkedIn announcement body (Key Improvements bullets). This is the long-form social/LinkedIn copy.
3. **Replace the GitHub-release highlights file**: delete `github-release-v0.1.X-1.md` and create `github-release-v0.1.X.md` (the short, emoji-sectioned GitHub Releases body dated `(YYYY-MM-DD)`).
   ```bash
   git rm docs/announcements/github-release-v0.1.X-1.md
   # then write docs/announcements/github-release-v0.1.X.md
   ```

`feature-highlights.md` and `README.md` in that directory are general (not per-version) — leave them unless the highlights changed.

Use the just-archived previous version's files as templates so the structure/sections stay consistent. Keep `[TO BE ADDED AFTER POSTING]` placeholders for the X/LinkedIn links.

> **Don't forget the version bump** (`massgen/__init__.py` `__version__ = "0.1.X"`) — `pyproject.toml` reads the version dynamically from there.

## Quick Validation Checklist

**Must Update (every release):**
0. ✅ Fresh-branch bootstrap done? (`__version__` bumped + `ROADMAP_v0.1.X.md` → `ROADMAP_v0.1.X+1.md` renamed — see Phase 0)
1. ✅ CHANGELOG.md
2. ✅ `massgen/__init__.py` (`__version__` bump)
3. ✅ docs/source/index.rst (Recent Releases)
4. ✅ README.md (Recent Achievements + Latest Features + TOC anchors)
5. ✅ ROADMAP.md (Current Version, completed section, table)
6. ✅ docs/announcements/ (archive old, rewrite current-release.md, swap github-release-vX.md)
7. ⚠️ docs/source/user_guide/ (if user-facing feature)
8. ⚠️ massgen/configs/ (example configs, if any)
9. ⚠️ Case study (skip for internal-quality/no-user-facing-feature releases)

**Should Update (if applicable):**
10. ⚠️ massgen/config_builder.py (if config params added)
11. ⚠️ massgen/backend/capabilities.py (if backend changes)
12. ✅ README_PYPI.md (auto-synced from README.md via pre-commit)

**Build & Verify:**
13. 🔨 `cd docs && make html && make linkcheck`
14. 🔨 Test new config files
15. 🔨 Verify all links work

See `docs/dev_notes/release_checklist.md` section "Quick Reference Checklist" for complete list.

## Backend Updates (When Needed)

### Config Builder

If new YAML parameters were added, update `massgen/config_builder.py`:
- Add parameters to interactive wizard
- Update validation
- Add help text
- Test with `massgen --config-builder`

### Backend Capabilities

If backend capabilities changed, update `massgen/backend/capabilities.py`:
- Document which backends support new features
- Update capability matrix
- Add new capability flags

See `docs/dev_notes/release_checklist.md` section 2.1-2.2.

## Commit and Release Workflow

### Commit Message Template

```bash
git commit -m "docs: Release v0.1.X documentation

- Updated CHANGELOG.md with full release notes
- Added case study: [Feature Name]
- Updated README.md Recent Achievements
- Enhanced Sphinx documentation
- Added example configurations

Major features:
- Feature 1: Description
- Feature 2: Description
"
```

### Create PR

```bash
git push origin dev/v0.1.X

gh pr create --base main --head dev/v0.1.X \
  --title "Release v0.1.X: [Feature Name]" \
  --body "See CHANGELOG.md for full release notes"
```

### Tag Release (After Merge)

```bash
git checkout main && git pull

git tag -a v0.1.X -m "Release v0.1.X: [Feature Name]

Major features:
- Feature 1
- Feature 2

See CHANGELOG.md for details."

git push origin v0.1.X
```

See `docs/dev_notes/release_checklist.md` section 7 for complete workflow.

## Reference Files

**Primary Documentation:**
- **Release checklist**: `docs/dev_notes/release_checklist.md` ⭐ START HERE
- **Writing configs**: `docs/source/development/writing_configs.rst`

**Scripts:**
- **README sync**: `scripts/sync_readme_pypi.py`
- **Config validation**: `scripts/precommit_validate_configs.py`
- **Backend tables**: `docs/scripts/generate_backend_tables.py`

**Templates:**
- **Case study template**: `docs/source/examples/case_studies/case-study-template.md`

## Tips for Agents

When preparing release documentation:

1. **Always read the release checklist first**: `docs/dev_notes/release_checklist.md`
2. **Follow the order strictly**: CHANGELOG → Sphinx → README → Roadmap
3. **Build docs after changes**: `cd docs && make html && make linkcheck`
4. **Test all new configs** before committing
5. **When in doubt**, consult `docs/dev_notes/release_checklist.md` for complete guidance

This skill is a quick reference guide. For comprehensive, step-by-step instructions, always refer to the official release checklist document.
