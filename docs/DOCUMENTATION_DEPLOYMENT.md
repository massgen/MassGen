# Documentation Deployment & Testing Guide

**Status:** ✅ Active
**Last Updated:** October 2025

## Overview

MassGen documentation is automatically deployed to multiple platforms with built-in validation and quality checks.

## Quick Commands

```bash
# Run all validation checks
make docs-check

# Build and serve docs locally
make docs-serve

# Just validate links
make docs-validate

# Just check duplication
make docs-duplication

# Build HTML documentation
make docs-build

# Clean all build artifacts
make docs-clean
```

---

## Deployment Platforms

### 1. ReadTheDocs (Primary)

**URL:** `https://massgen.readthedocs.io`
**Configuration:** `docs/.readthedocs.yaml`

#### How It Works

- Automatically builds on every push to `main`
- Generates HTML, PDF, and ePub formats
- Uses `uv` for dependency management
- Versioned documentation support

#### Setup (One-time)

1. Go to [readthedocs.org](https://readthedocs.org)
2. Sign in with GitHub
3. Click "Import a Project"
4. Select `MassGen` repository
5. ReadTheDocs auto-detects `.readthedocs.yaml`
6. Click "Build Version"

**Done!** All future builds happen automatically on push.

#### Triggering a Build

```bash
# Automatic: Just push to main
git push origin main

# Manual: Use ReadTheDocs dashboard
# → Go to project → Versions → Build
```

### 2. GitHub Pages (Secondary)

**URL:** `https://<username>.github.io/MassGen`
**Workflow:** `.github/workflows/docs.yml`

#### How It Works

- Builds on push to `main` or `doc_web` branches
- Deploys to GitHub Pages automatically
- Triggered by changes to `docs/**` or `massgen/**/*.py`

#### Setup (One-time)

1. Go to repository **Settings** → **Pages**
2. **Source:** Deploy from a branch
3. **Branch:** `gh-pages` (created automatically by workflow)
4. **Folder:** `/ (root)`
5. Click **Save**

**Done!** Deployments happen automatically via GitHub Actions.

#### Triggering a Deployment

```bash
# Automatic: Push to main or doc_web
git push origin doc_web

# Manual: Via GitHub Actions UI
gh workflow run docs.yml
```

### 3. Local Development

Build and serve documentation on your machine.

#### Setup

```bash
# Install documentation dependencies
make install-docs

# Or manually with uv
uv pip install -r docs/requirements-docs.txt
```

#### Serve Locally

```bash
# Build and serve at http://localhost:8000
make docs-serve

# Build only (output in docs/_build/html/)
make docs-build

# Open in browser
open docs/_build/html/index.html  # macOS
xdg-open docs/_build/html/index.html  # Linux
```

---

## Testing GitHub Actions

### Testing Documentation Automation

The `docs-automation.yml` workflow runs on PRs and provides automated validation.

#### Test Locally (Recommended)

Before pushing, run the same checks locally:

```bash
# Run all checks (same as CI)
make docs-check

# This runs:
# 1. Link validation
# 2. Duplication detection
# 3. Generates reports
```

**Output:**
```
🔍 Validating documentation links...
✓ Link validation complete. See docs/LINK_VALIDATION_REPORT.md

🔍 Checking for duplicated content...
✓ Duplication check complete. See docs/DUPLICATION_REPORT.md

✅ All documentation checks passed!
```

#### Test on a Feature Branch

```bash
# 1. Create test branch
git checkout -b test-docs-automation

# 2. Make a documentation change
echo "Test content" >> docs/source/index.rst

# 3. Commit and push
git add docs/source/index.rst
git commit -m "test: trigger docs automation"
git push origin test-docs-automation

# 4. Create a PR
gh pr create --title "Test: Documentation Automation" \
             --body "Testing the docs-automation workflow"

# 5. Watch the workflow run
# → Go to Actions tab in GitHub
# → See "Documentation Quality Checks" workflow
# → View logs and results

# 6. Check PR comment
# → Workflow posts validation results as a comment
```

**Expected Workflow Steps:**

1. ✅ **Checkout code**
2. ✅ **Set up Python 3.10**
3. ✅ **Install uv**
4. ✅ **Install dependencies**
5. ✅ **Check documentation duplication**
6. ✅ **Validate documentation links**
7. ✅ **Post summary comment on PR**

#### Test Manual Workflow Trigger

```bash
# Trigger workflow manually via GitHub CLI
gh workflow run docs-automation.yml

# Or via GitHub web UI:
# 1. Go to Actions tab
# 2. Click "Documentation Quality Checks"
# 3. Click "Run workflow"
# 4. Select branch
# 5. Click "Run workflow"
```

### Testing Documentation Build

The `docs.yml` workflow builds and deploys documentation.

#### Test Locally

```bash
# Test the exact build process used by CI
cd docs
sphinx-build -b html source _build/html

# Check for warnings
sphinx-build -b html -W source _build/html  # Fail on warnings

# Verify output
ls -la _build/html/
open _build/html/index.html
```

#### Test on a Feature Branch

```bash
# 1. Create test branch
git checkout -b test-docs-build

# 2. Make documentation changes
vim docs/source/user_guide/tools.rst

# 3. Commit and push
git add docs/source/user_guide/tools.rst
git commit -m "docs: update tools documentation"
git push origin test-docs-build

# 4. Create PR targeting main
gh pr create --base main \
             --title "docs: update tools documentation" \
             --body "Testing documentation build"

# 5. Watch the workflow
# → Actions tab → "Build and Deploy Documentation"
# → Verify build succeeds
# → Check artifact upload

# 6. Test deployment (if merged to main)
# → Merge PR or push to main
# → Workflow deploys to GitHub Pages
# → Visit https://<username>.github.io/MassGen
```

**Expected Workflow Steps:**

1. ✅ **Checkout**
2. ✅ **Set up Python**
3. ✅ **Cache dependencies**
4. ✅ **Install dependencies**
5. ✅ **Build documentation**
6. ✅ **Upload artifact**
7. ✅ **Deploy to GitHub Pages** (main branch only)
8. ✅ **Trigger ReadTheDocs build** (main branch only)

### Testing Release Automation

See [github_actions_release_automation.md](workflows/github_actions_release_automation.md) for detailed instructions.

Quick test:

```bash
# 1. Create test release docs
mkdir -p docs/releases/v0.0.99-test
echo "# Test Release" > docs/releases/v0.0.99-test/features-overview.md
echo "# Test Notes" > docs/releases/v0.0.99-test/release-notes.md

# 2. Commit and push
git add docs/releases/v0.0.99-test/
git commit -m "test: add test release docs"
git push origin main

# 3. Create and push test tag
git tag v0.0.99-test
git push origin v0.0.99-test

# 4. Watch workflow
# → Actions tab → "Release Documentation Automation"
# → Verify it creates PR or commits

# 5. Clean up
git push --delete origin v0.0.99-test
git tag -d v0.0.99-test
```

---

## Validation Scripts

### Link Validation

**Script:** `scripts/validate_links.py`
**Command:** `make docs-validate` or `uv run python scripts/validate_links.py`

#### What It Checks

- ✅ `:doc:` cross-references (both `:doc:\`path\`` and `:doc:\`text <path>\``)
- ✅ File existence
- ✅ Path resolution
- ❌ External URLs (disabled by default)

#### Output

```
Scanning 40 documentation files for broken links...
✓ All links are valid!
```

**Report:** `docs/LINK_VALIDATION_REPORT.md`

#### Example Issues Caught

```
❌ ERROR in index.rst: Broken :doc: reference to 'quickstart/missing_file'
   → File not found: docs/source/quickstart/missing_file.rst
```

### Duplication Detection

**Script:** `scripts/check_duplication.py`
**Command:** `make docs-duplication` or `uv run python scripts/check_duplication.py`

#### What It Checks

- 🔍 Scans all `.rst` files
- 🔍 Compares text blocks (>50 words)
- 🔍 Detects >80% similarity
- ✅ Excludes code blocks, tables, and titles

#### Output

```
Scanning 40 documentation files...
Found 0 potential duplications
✓ No significant duplication detected!
```

**Report:** `docs/DUPLICATION_REPORT.md`

#### Example Issues Caught

```
⚠️  DUPLICATION DETECTED

File 1: user_guide/tools.rst (lines 45-120)
File 2: user_guide/backends.rst (lines 200-275)
Similarity: 92%
Content: Backend Tool Capabilities table (150 words)

→ Recommendation: Move to single source in backends.rst, add link from tools.rst
```

---

## CI/CD Integration

### Pull Request Checks

When you create a PR touching `docs/**`:

1. **Documentation Quality Checks** (`docs-automation.yml`)
   - ✅ Validates all links
   - ✅ Checks for duplication
   - ✅ Posts results as PR comment

2. **Build Verification** (`docs.yml`)
   - ✅ Builds documentation
   - ✅ Uploads artifact
   - ❌ Does NOT deploy (only on main)

### Main Branch Deployment

When you push/merge to `main`:

1. **Documentation Quality Checks** (runs first)
   - ✅ Validates quality

2. **Build and Deploy** (if checks pass)
   - ✅ Builds documentation
   - ✅ Deploys to GitHub Pages
   - ✅ Triggers ReadTheDocs build

### Branch Protection

Configure in **Settings → Branches → main**:

```yaml
Required Status Checks:
  ✅ Documentation Quality Checks
  ✅ Build and Deploy Documentation
```

This prevents merging PRs with broken links or duplication.

---

## Common Workflows

### Adding New Documentation

```bash
# 1. Run checks before starting
make docs-check

# 2. Create new file
vim docs/source/user_guide/new_feature.rst

# 3. Add to toctree
vim docs/source/user_guide/index.rst  # Add new_feature

# 4. Build locally and verify
make docs-serve
# → Visit http://localhost:8000

# 5. Run checks again
make docs-check

# 6. Commit and push
git add docs/source/user_guide/
git commit -m "docs: add new feature documentation"
git push origin doc_web

# 7. Create PR - CI runs automatically
gh pr create --title "docs: add new feature documentation"
```

### Fixing Broken Links

```bash
# 1. Run link validator
make docs-validate

# 2. Check report
cat docs/LINK_VALIDATION_REPORT.md

# 3. Fix broken links
vim docs/source/index.rst  # Fix :doc: references

# 4. Verify fix
make docs-validate

# 5. Commit
git add docs/source/index.rst
git commit -m "docs: fix broken cross-references"
```

### Reducing Duplication

```bash
# 1. Run duplication checker
make docs-duplication

# 2. Check report
cat docs/DUPLICATION_REPORT.md

# 3. Consolidate duplicated content
# → Move to single source
# → Add :seealso: links

# 4. Verify fix
make docs-duplication

# 5. Commit
git add docs/source/
git commit -m "docs: consolidate duplicated content"
```

---

## Troubleshooting

### "sphinx-build: command not found"

```bash
# Install documentation dependencies
make install-docs

# Or manually
uv pip install -r docs/requirements-docs.txt
```

### Workflow Doesn't Trigger

**Check:**
1. Workflow file exists and is enabled (not `.disabled`)
2. File changes match `paths:` filter in workflow
3. Branch matches `branches:` filter
4. GitHub Actions enabled in repository settings

**Debug:**
```bash
# View workflow configuration
cat .github/workflows/docs-automation.yml

# List recent workflow runs
gh run list --workflow=docs-automation.yml

# View specific run logs
gh run view <run-id> --log
```

### Build Fails in CI but Works Locally

**Common Causes:**
- Different Python version (CI uses 3.10)
- Different Sphinx version
- Missing dependencies in `requirements-docs.txt`

**Solution:**
```bash
# Test with same Python version as CI
pyenv install 3.10
pyenv local 3.10
make docs-build
```

### Duplication False Positives

If the checker reports false positives:

```python
# Edit scripts/check_duplication.py
SIMILARITY_THRESHOLD = 0.8  # Increase to 0.9 for stricter matching
MIN_WORDS = 50  # Increase to 100 to ignore shorter duplications
```

### Link Checker Misses Custom Text Links

The validator now supports `:doc:\`text <path>\`` syntax. If it still fails:

```bash
# Check validator version
grep -A5 "custom_match" scripts/validate_links.py

# Should show:
# custom_match = re.match(r'(.+)<(.+)>', ref)
# if custom_match:
#     ref = custom_match.group(2).strip()
```

---

## Monitoring

### View Recent Deployments

```bash
# GitHub Pages deployments
gh api repos/:owner/:repo/pages/builds

# ReadTheDocs builds
# → Visit https://readthedocs.org/projects/massgen/builds/
```

### Check Documentation Health

```bash
# Run full validation
make docs-check

# Check build warnings
cd docs
sphinx-build -b html -W source _build/html  # Fail on warnings
```

### Monitor Workflow Status

```bash
# List recent workflow runs
gh run list

# Watch a specific run
gh run watch

# View run logs
gh run view --log
```

---

## Best Practices

### Before Committing

1. ✅ Run `make docs-check` locally
2. ✅ Build and review `make docs-serve`
3. ✅ Check reports in `docs/*.md`
4. ✅ Fix all errors and warnings

### During PR Review

1. ✅ Check CI passes all checks
2. ✅ Review validation reports in PR comments
3. ✅ Preview documentation in artifact
4. ✅ Ensure no duplication introduced

### After Merging

1. ✅ Verify GitHub Pages deployment
2. ✅ Check ReadTheDocs build status
3. ✅ Test links on live site
4. ✅ Confirm all pages render correctly

---

## Related Documentation

- **[Deployment README](README.md)** - General documentation guide
- **[Release Automation](workflows/github_actions_release_automation.md)** - Testing release workflows
- **[Scripts README](../scripts/README.md)** - Automation scripts documentation
- **[Makefile](../Makefile)** - All available commands

---

**Maintained By:** MassGen Team
**Workflow Files:**
- `.github/workflows/docs-automation.yml` - Quality checks
- `.github/workflows/docs.yml` - Build and deploy
- `docs/.readthedocs.yaml` - ReadTheDocs configuration
- `Makefile` - Convenience commands
