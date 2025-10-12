# Release README Update Workflow

This document describes the automated workflow for updating README.md with new release information.

## Overview

When releasing a new version:
1. **features-overview.md** (short, ~100-150 lines) → Embedded in README.md
2. **release-notes.md** (long, 400+ lines) → Complete technical documentation
3. Previous release is automatically archived to "Previous Releases" section

## Files Structure

```
docs/releases/v0.0.X/
├── features-overview.md        # SHORT - copy-pasteable into README
├── release-notes.md            # LONG - complete technical docs
└── case-study.md              # Optional - detailed example

README.md
├── What's New in v0.0.X       # ← Auto-updated from features-overview.md
└── Previous Releases          # ← Auto-archived from previous "What's New"
```

## Release Process

### Step 1: Create Release Documentation

Create three files in `docs/releases/v0.0.X/`:

**1. features-overview.md** (~100-150 lines)
```markdown
# v0.0.X Features Overview

**Release Date:** Date | [Full Release Notes](release-notes.md) | [Video Demo](url)

---

## What's New

### Feature Name
**One-line description**

**Key Benefits:**
- ✅ Benefit 1
- ✅ Benefit 2
- ✅ Benefit 3

---

### Feature Name 2
...

## New Configurations (N)
...

## Quick Start Commands
```bash
uv run python -m massgen.cli --config ... "task"
```

## When to Use X
...

## Migration from v0.0.Y
...
```

**2. release-notes.md** (400+ lines)
- Complete technical documentation
- Implementation details
- Full code examples
- Migration guides
- Contributors
- All bug fixes

**3. case-study.md** (optional)
- Detailed walkthrough
- Real-world example
- Session logs

### Step 2: Run Update Script

```bash
# From repo root
uv run python scripts/update_readme_release.py v0.0.29

# Or without 'v' prefix
uv run python scripts/update_readme_release.py 0.0.29
```

**What the script does:**
1. ✅ Extracts "What's New" content from `features-overview.md`
2. ✅ Updates README.md's "What's New in v0.0.X" section
3. ✅ Moves previous release to "Previous Releases" section
4. ✅ Adds proper links to detailed docs

### Step 3: Review and Commit

```bash
# Review changes
git diff README.md

# Verify the update looks correct
# - New "What's New in v0.0.X" section at top
# - Previous version moved to "Previous Releases"
# - Links to features-overview.md and release-notes.md

# Commit
git add README.md docs/releases/v0.0.X/
git commit -m "docs: update README for v0.0.X release"
```

## Script Details

### Location
```
scripts/update_readme_release.py
```

### Usage
```bash
python scripts/update_readme_release.py <version>

# Examples:
python scripts/update_readme_release.py v0.0.29
python scripts/update_readme_release.py 0.0.29  # 'v' prefix optional
```

### Requirements
- Python 3.7+
- No external dependencies (uses stdlib only)

### What It Does

1. **Extracts Content**
   - Reads `docs/releases/vX.X.X/features-overview.md`
   - Extracts "What's New" section (main content)
   - Removes metadata, resources, contributor sections

2. **Updates README.md**
   - Finds existing "What's New in vX.X.X" section
   - Replaces with new version content
   - Adds links to full documentation

3. **Archives Previous Release**
   - Extracts current "What's New" from README
   - Creates summary (first paragraph/bullets)
   - Adds to "Previous Releases" section
   - Links to full release notes

### Output Example

**README.md after update:**
```markdown
## What's New in v0.0.29 🎉

## What's New

### MCP Planning Mode
**Agents plan without executing during coordination**

**Key Benefits:**
- ✅ No duplicate Discord posts during coordination
- ✅ 80% reduction in unnecessary API calls
...

📖 [Features Overview](docs/releases/v0.0.29/features-overview.md) | 📝 [Full Release Notes](docs/releases/v0.0.29/release-notes.md) | 🎥 [Video Demo](https://youtu.be/...)

---

## Previous Releases

**v0.0.28**
**AG2 Framework Integration** - External agent framework support
- Complete adapter system for external frameworks
- Code execution with multiple executor types
...

[See full notes →](docs/releases/v0.0.28/release-notes.md)

---
```

## Best Practices

### features-overview.md Guidelines

**Keep it short:**
- ✅ 100-150 lines max
- ✅ High-level benefits, not implementation
- ✅ Quick start commands
- ✅ "When to use" guidance
- ❌ No detailed code examples
- ❌ No implementation details
- ❌ No bug fix lists

**Structure:**
1. Header with links
2. What's New (3-5 features max)
3. New Configurations (count + list)
4. Quick Start Commands
5. When to Use / Migration
6. Links to full docs

**Writing Style:**
- One-line descriptions with bullets
- Action-oriented ("Prevents duplicate...", "Enables agents to...")
- Quantify impact ("80% reduction", "100% enforcement")
- Use checkmarks (✅) for benefits

### release-notes.md Guidelines

**Be comprehensive:**
- ✅ Full technical details
- ✅ Implementation specifics
- ✅ Code examples
- ✅ Architecture changes
- ✅ Migration guides
- ✅ All bug fixes
- ✅ Contributors

### Automation Integration

**Pre-commit hook** (optional):
```bash
# .git/hooks/pre-commit
#!/bin/bash
# Verify release docs exist before allowing commit of version tag

if git describe --exact-match --tags HEAD 2>/dev/null | grep -q "^v[0-9]"; then
    VERSION=$(git describe --exact-match --tags HEAD)
    if [ ! -f "docs/releases/$VERSION/features-overview.md" ]; then
        echo "❌ Error: docs/releases/$VERSION/features-overview.md not found"
        exit 1
    fi
    if [ ! -f "docs/releases/$VERSION/release-notes.md" ]; then
        echo "❌ Error: docs/releases/$VERSION/release-notes.md not found"
        exit 1
    fi
fi
```

**GitHub Actions** (future):
```yaml
# .github/workflows/release.yml
name: Release Documentation
on:
  push:
    tags:
      - 'v*'
jobs:
  update-readme:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Update README
        run: |
          python scripts/update_readme_release.py ${{ github.ref_name }}
          git config user.name "github-actions"
          git config user.email "github-actions@github.com"
          git add README.md
          git commit -m "docs: update README for ${{ github.ref_name }}"
          git push
```

## Troubleshooting

### Script fails: "features-overview-short.md not found"
**Solution:** Create `docs/releases/vX.X.X/features-overview.md` first

### README.md not updated correctly
**Solution:** Manually verify structure. Script looks for `## What's New in v` pattern

### Previous release not archived
**Solution:** Verify old "What's New" section exists with correct format

### Links broken after update
**Solution:** Verify file paths in features-overview.md are correct

## Examples

See existing releases:
- `docs/releases/v0.0.29/` - Complete example with all three files
- `docs/releases/v0.0.28/` - AG2 integration release

## Checklist

- [ ] Created `features-overview.md` (~100-150 lines)
- [ ] Created `release-notes.md` (400+ lines)
- [ ] Created `case-study.md` (optional)
- [ ] Ran `python scripts/update_readme_release.py vX.X.X`
- [ ] Reviewed `git diff README.md`
- [ ] Verified links work
- [ ] Committed changes
- [ ] Tagged release: `git tag vX.X.X && git push origin vX.X.X`

---

**Questions?** Open an issue or check the [release workflow checklist](release_example_checklist.md)
