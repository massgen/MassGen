# Release Documentation System

**Status:** ✅ Implemented
**Date:** October 2025

## Overview

MassGen uses a **2-tier release documentation system** with automated README updates.

## The System

```
┌─────────────────────────────────────────┐
│  features-overview.md                   │
│  SHORT (~100-150 lines)                 │
│  Copy-pasteable, high-level             │
│  Automatically embedded in README.md    │
└─────────────────────────────────────────┘
              ↓ Links to
┌─────────────────────────────────────────┐
│  release-notes.md                       │
│  LONG (400+ lines)                      │
│  Complete technical documentation       │
│  Reference for developers               │
└─────────────────────────────────────────┘
```

## Documentation Files

### features-overview.md (~100-150 lines)

**Purpose:** Short announcement for README

**Structure:**
```markdown
# vX.X.X Features Overview

## What's New

### Feature Name
**One-line description**

**Key Benefits:**
- ✅ Benefit 1
- ✅ Benefit 2

### Feature Name 2
...

## New Configurations (N)
...

## Quick Start Commands
```bash
uv run python -m massgen.cli --config ... "task"
```

## When to Use / Migration
...
```

**Guidelines:**
- ✅ 100-150 lines max
- ✅ High-level benefits only
- ✅ Action-oriented language
- ✅ Quantify impact ("80% reduction")
- ✅ Quick start commands
- ❌ No implementation details
- ❌ No detailed code examples

### release-notes.md (400+ lines)

**Purpose:** Complete technical documentation

**Structure:**
```markdown
# MassGen vX.X.X Release Notes

## Overview
High-level summary

## 🚀 What's New

### Feature Name
Full implementation details with:
- Technical capabilities
- Architecture changes
- Code examples
- Configuration examples

## 🔧 What Changed
...

## 🐛 What Was Fixed
...

## 📦 New Configurations
Detailed list with use cases

## 📚 Documentation Updates
...

## 🚀 Migration Guide
...

## 🤝 Contributors
...
```

**Guidelines:**
- ✅ Complete technical depth
- ✅ Full code examples
- ✅ Migration guides
- ✅ All bug fixes
- ✅ Architecture details

### case-study.md (optional)

**Purpose:** Real-world walkthrough

**Content:**
- Problem statement
- Solution approach
- Step-by-step execution
- Performance metrics
- Lessons learned

## Automation Script

### Location
```
scripts/update_readme_release.py
```

### Usage
```bash
# From repo root
uv run python scripts/update_readme_release.py v0.0.29

# Or without 'v' prefix
python scripts/update_readme_release.py 0.0.29
```

### What It Does

1. **Extracts Content**
   - Reads `docs/releases/vX.X.X/features-overview.md`
   - Extracts "What's New" section (removes metadata)

2. **Updates README.md**
   - Replaces "What's New in vX.X.X" section
   - Adds links to full documentation

3. **Archives Previous Release**
   - Extracts current "What's New" from README
   - Creates summary (first paragraph/bullets)
   - Adds to "Previous Releases" section

### README.md Result

After running the script, README.md looks like:

```markdown
## What's New in v0.0.29 🎉

## What's New

### MCP Planning Mode
**Agents plan without executing during coordination**

**Key Benefits:**
- ✅ No duplicate Discord posts
- ✅ 80% reduction in API calls
...

📖 [Features Overview](docs/releases/v0.0.29/features-overview.md) |
📝 [Full Release Notes](docs/releases/v0.0.29/release-notes.md) |
🎥 [Video Demo](https://youtu.be/...)

---

## Previous Releases

**v0.0.28**
**AG2 Framework Integration** - External agent framework support
...

[See full notes →](docs/releases/v0.0.28/release-notes.md)
```

## Release Process

### Step 1: Create Documentation

In `docs/releases/vX.X.X/`:

1. **features-overview.md** (100-150 lines)
   - Short, high-level announcement
   - Copy-pasteable format

2. **release-notes.md** (400+ lines)
   - Complete technical documentation
   - Full details

3. **case-study.md** (optional)
   - Real-world example
   - Walkthrough

### Step 2: Run Automation

```bash
# From repo root
uv run python scripts/update_readme_release.py v0.0.29
```

### Step 3: Review & Commit

```bash
# Review changes
git diff README.md

# Verify:
# - New "What's New in vX.X.X" section
# - Previous release moved to "Previous Releases"
# - Links are correct

# Commit
git add README.md docs/releases/vX.X.X/
git commit -m "docs: update README for vX.X.X release"

# Tag
git tag vX.X.X
git push origin main --tags
```

## File Locations

```
MassGen/
├── README.md                          # Main README with "What's New"
├── scripts/
│   └── update_readme_release.py       # Automation script
├── docs/
│   ├── workflows/
│   │   ├── release_readme_update.md   # Detailed workflow guide
│   │   └── RELEASE_DOCUMENTATION_SYSTEM.md  # This file
│   └── releases/
│       ├── README.md                  # Release index
│       └── vX.X.X/
│           ├── features-overview.md   # SHORT - for README
│           ├── release-notes.md       # LONG - complete docs
│           └── case-study.md         # OPTIONAL - example
```

## Benefits

### For Users
- ✅ Concise updates in main README
- ✅ Quick understanding of new features
- ✅ Clear "when to use" guidance
- ✅ Easy access to full details

### For Developers
- ✅ Complete technical documentation
- ✅ Implementation details preserved
- ✅ Migration guides available
- ✅ Consistent structure

### For Maintainers
- ✅ Automated README updates
- ✅ Previous releases archived automatically
- ✅ Consistent documentation format
- ✅ Less manual work

## Examples

### Completed Releases

**v0.0.29** - MCP Planning Mode
- ✅ features-overview.md (140 lines)
- ✅ release-notes.md (390 lines)
- ✅ case-study.md (detailed example)
- ✅ Automation tested

**v0.0.28** - AG2 Framework Integration
- ✅ features-overview.md (needs trimming to ~150 lines)
- ✅ release-notes.md (450 lines)
- ✅ case-study.md (framework comparison)

## Checklist Template

For each new release:

```markdown
## vX.X.X Release Checklist

Documentation:
- [ ] Create docs/releases/vX.X.X/features-overview.md (~100-150 lines)
- [ ] Create docs/releases/vX.X.X/release-notes.md (400+ lines)
- [ ] Create docs/releases/vX.X.X/case-study.md (optional)

Automation:
- [ ] Run: python scripts/update_readme_release.py vX.X.X
- [ ] Review: git diff README.md
- [ ] Verify links work
- [ ] Check "Previous Releases" section

Git:
- [ ] git add README.md docs/releases/vX.X.X/
- [ ] git commit -m "docs: update README for vX.X.X release"
- [ ] git tag vX.X.X
- [ ] git push origin main --tags
```

## Troubleshooting

### Script fails: "features-overview.md not found"
**Solution:** Create the file first

### README not updated
**Solution:** Check for correct `## What's New in v` pattern

### Previous release not archived
**Solution:** Verify old section has correct format

### Links broken
**Solution:** Verify relative paths in features-overview.md

## GitHub Actions Automation

### ✅ Fully Implemented

MassGen includes GitHub Actions workflows for automated README updates:

**Workflow:** `.github/workflows/release-docs-automation.yml`

**What it does:**
1. ✅ Triggers on version tags (e.g., `v0.0.29`)
2. ✅ Verifies release docs exist (fails if missing)
3. ✅ Runs update script automatically
4. ✅ Creates PR for review (recommended approach)

**Alternative:** Auto-merge workflow available (`.yml.disabled`)

**Documentation:** [GitHub Actions Release Automation](github_actions_release_automation.md)

### Usage with GitHub Actions

```bash
# 1. Create release docs
# docs/releases/v0.0.29/features-overview.md
# docs/releases/v0.0.29/release-notes.md

# 2. Commit and push
git add docs/releases/v0.0.29/
git commit -m "docs: add v0.0.29 release documentation"
git push origin main

# 3. Tag release
git tag v0.0.29
git push origin v0.0.29

# 4. GitHub Actions automatically:
#    - Verifies docs exist ✅
#    - Updates README.md
#    - Creates PR for you to review and merge

# 5. Review and merge PR
#    - Check changes look correct
#    - Merge to complete release
```

### Benefits

✅ **Automated** - No manual script running
✅ **Verified** - Blocks release if docs missing
✅ **Safe** - PR review before README changes
✅ **Transparent** - See exact changes in PR

## References

- [Release README Update Workflow](release_readme_update.md) - Detailed guide
- [docs/releases/README.md](../releases/README.md) - Release index
- [scripts/update_readme_release.py](../../scripts/update_readme_release.py) - Source code

---

**Created:** October 2025
**Last Updated:** October 2025
**Status:** ✅ Active and working
