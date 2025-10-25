# MassGen Release Checklist

**Version:** `v0.1.X`
**Release Date:** `YYYY-MM-DD`
**Branch:** `dev/v0.1.X`

---

## Pre-Release: Branch Setup

- [ ] Create new release branch: `dev/v0.1.X`
- [ ] Ensure all feature PRs are merged into `dev/v0.1.X`
- [ ] All tests passing on `dev/v0.1.X`
- [ ] Version number updated in `pyproject.toml`
- [ ] Ensure issues for next release are already created and marked with a milestone (for roadmap)

---

## Phase 1: Review & Audit Changes 🔍

### 1.1 Read All Changes
- [ ] Review all PRs merged into `dev/v0.1.X`
- [ ] List new features, bug fixes, and breaking changes
- [ ] Identify configuration changes
- [ ] Identify backend capability changes

**Command to get PR list:**
```bash
# Get all commits since last release
git log v0.1.X-1..HEAD --oneline

# Or if using GitHub PR numbers
gh pr list --base dev/v0.1.X --state merged
```

### 1.2 Verify PR Documentation
- [ ] Each PR has associated documentation (user guides, API docs, or design docs)
- [ ] No undocumented features
- [ ] Breaking changes are documented with migration guides

**Missing docs?** → Create them now before proceeding.

---

## Phase 2: Code & Configuration Updates 🔧

### 2.1 Config Builder Updates
**If new YAML parameters were added:**

- [ ] Update `massgen/config_builder.py`
  - Add new parameters to interactive wizard
  - Update parameter validation
  - Add help text for new options
  - Test: `massgen --config-builder`

**Files to check:**
- `massgen/config_builder.py` - Main builder logic
- `massgen/configs/` - Example YAML files

### 2.2 Backend Capabilities Registry
**If backend capabilities changed (new features, MCP support, multimodal, etc.):**

- [ ] Update `massgen/backend/capabilities.py`
  - Document which backends support new features
  - Update capability matrix
  - Add any new capability flags

**Example:**
```python
# If you added a new feature "X"
BACKEND_CAPABILITIES = {
    "claude": {"feature_x": True, ...},
    "gemini": {"feature_x": True, ...},
    "openai": {"feature_x": False, ...},  # Not supported
}
```

### 2.3 Example Configurations
- [ ] Create example YAML files for new features in `massgen/configs/`
- [ ] Organize by category (basic, tools, teams, providers)
- [ ] Test each new config file

---

## Phase 3: Primary Documentation Updates 📝

**Order: CHANGELOG → Sphinx Docs → Config Docs → README**

### 3.1 CHANGELOG.md ⭐ **START HERE**
- [ ] Add new `## [0.1.X] - YYYY-MM-DD` section
- [ ] Document under proper categories:
  - `### Added` - New features
  - `### Changed` - Modified behavior
  - `### Fixed` - Bug fixes
  - `### Documentations, Configurations and Resources` - New docs/configs
  - `### Technical Details` - Contributors, focus areas

**Template:**
```markdown
## [0.1.X] - 2025-XX-XX

### Added
- **Feature Name**: Description
  - Implementation detail with file path
  - Key capability

### Changed
- **Modified Feature**: What changed and why

### Fixed
- **Issue #123**: What was fixed

### Documentations, Configurations and Resources
- **Documentation**: `docs/source/user_guide/feature.rst` - Description
- **Configuration Examples**: `configs/category/example.yaml` - Description
- **Case Studies**: `docs/source/examples/case_studies/feature.md` - Description

### Technical Details
- **Major Focus**: Summary of release theme
- **Contributors**: @username1 @username2
```

- [ ] Include file paths for all changes
- [ ] Reference issue/PR numbers
- [ ] Follow [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format

### 3.2 Sphinx Documentation (User-Facing)
**Location:** `docs/source/`

- [ ] **User Guides** (`docs/source/user_guide/`)
  - [ ] Add/update guides for new features
  - [ ] Include code examples
  - [ ] Show expected output

- [ ] **Configuration Reference** (`docs/source/reference/yaml_schema.rst`)
  - [ ] Document new YAML parameters
  - [ ] Update schema examples

- [ ] **Supported Models** (`docs/source/reference/supported_models.rst`)
  - [ ] Add new models if applicable
  - [ ] Update capability matrix

- [ ] **API Documentation**
  - [ ] Verify docstrings are updated (auto-generates)
  - [ ] Check `docs/source/api/` renders correctly

**Verify:**
```bash
cd docs && make html
# Check for warnings and broken links
make linkcheck
```

### 3.3 Configuration Documentation
- [ ] **Update** `massgen/configs/README.md`
  - [ ] Add new configuration examples
  - [ ] Update version history sections (Recent Achievements)
  - [ ] Link to case studies for new features
  - [ ] Ensure logical organization

- [ ] **Verify** new configs make sense
  - [ ] Test each new YAML file
  - [ ] Ensure consistent naming
  - [ ] Check all paths are correct

### 3.4 Case Study
**Location:** `docs/source/examples/case_studies/`

- [ ] Plan case study demonstrating new feature(s)
- [ ] Create `docs/source/examples/case_studies/feature-name.md`
  - Follow `case-study-template.md`
  - Include real usage examples
  - Show configuration used
  - Document outcomes

- [ ] Update `docs/source/examples/case_studies.rst`
  - Add new case study to toctree
  - Update index/listing

**Template reference:**
```bash
# Use existing template
cp docs/source/examples/case_studies/case-study-template.md \
   docs/source/examples/case_studies/v0.1.X-feature-name.md
```

---

## Phase 4: Top-Level Documentation 📋

### 4.1 README.md
**Update these sections in order:**

- [ ] **Recent Achievements** (Roadmap section)
  - [ ] Move current "Recent Achievements (v0.1.X-1)" → "Previous Achievements"
  - [ ] Add new "Recent Achievements (v0.1.X)" section
  - [ ] Include detailed bullet points with:
    - Feature descriptions
    - Implementation details
    - File paths
    - Configuration examples
  - [ ] Link to case studies

- [ ] **Case Studies** section
  - [ ] Add links to new case studies
  - [ ] Update case study descriptions

- [ ] **Configuration Files** section (if needed)
  - [ ] Update quick navigation if structure changed

**Tip:** Copy format from CHANGELOG.md → expand for README.md

### 4.2 README_PYPI.md
**Goal:** Auto-sync with README.md (only logo/thumbnail paths differ for PyPI display)

**✅ Automated via Pre-Commit Hook (Default):**

README_PYPI.md now syncs **automatically** when you commit README.md changes!

- [ ] Edit and commit README.md normally
- [ ] Pre-commit hook auto-syncs README_PYPI.md
- [ ] If hook shows "Failed - files were modified", just run `git commit` again
- [ ] Both files will be committed together

**How it works:**
1. When you `git commit` with README.md changes
2. Pre-commit hook runs `scripts/sync_readme_pypi.py`
3. Automatically stages README_PYPI.md
4. You commit again to include both files

**Manual Sync (if needed):**
```bash
# Run the sync script manually
uv run python scripts/sync_readme_pypi.py

# Or dry-run to preview changes
uv run python scripts/sync_readme_pypi.py --dry-run

# Then stage and commit
git add README_PYPI.md
```

**What the automation does:**
1. Copies README.md content to README_PYPI.md
2. Replaces `assets/logo.png` → `https://raw.githubusercontent.com/Leezekun/MassGen/main/assets/logo.png`
3. Replaces `assets/massgen-demo.gif` → `https://raw.githubusercontent.com/Leezekun/MassGen/main/assets/thumbnail.png`

### 4.3 Roadmap Updates
- [ ] **Update** `ROADMAP.md`
  - [ ] Mark completed features as ✅
  - [ ] Move completed items to "Recent Achievements"
  - [ ] Add new planned features from GitHub issues

- [ ] **Update** `ROADMAP_v0.1.4.md` (next version)
  - [ ] Plan features for next release
  - [ ] Pull from GitHub issues/milestones

**Future automation idea:**
```bash
# Script to pull GitHub issues labeled "v0.1.4"
# and auto-generate roadmap sections
# TODO: Create scripts/generate_roadmap_from_issues.py
```

**Note:**
- ❌ DO NOT update `docs/source/development/roadmap.rst` (auto-pulls from ROADMAP.md)

### 4.4 Contributing Guide
- [ ] **Update** `CONTRIBUTING.md` if:
  - Development process changed
  - New documentation requirements
  - New PR templates needed

**Note:**
- ❌ DO NOT update `docs/source/development/contributing.rst` (auto-pulls from CONTRIBUTING.md)

---

## Phase 5: Build & Verify 🔨

### 5.1 Build Documentation
```bash
cd docs
make clean
make html
```

**Check for:**
- [ ] ❌ No build errors
- [ ] ❌ No broken links (`make linkcheck`)
- [ ] ❌ Minimal warnings (document any unavoidable ones)
- [ ] ✅ New pages render correctly
- [ ] ✅ Case studies appear in navigation
- [ ] ✅ API docs generated properly

**Live preview for testing:**
```bash
cd docs && make livehtml
# Opens at http://localhost:8000
```

### 5.2 Verify Configuration Examples
```bash
# Test each new config file
massgen --config @examples/path/to/new_config "test query"

# Or use config builder
massgen --init
```

- [ ] All new configs load without errors
- [ ] Config builder shows new options
- [ ] Example queries work as expected

### 5.3 Cross-Reference Check
- [ ] All CHANGELOG.md file paths are correct
- [ ] All README.md links work
- [ ] Case study references are accurate
- [ ] Config documentation matches actual files

---

## Phase 6: Final Review 👀

### 6.1 Consistency Check
- [ ] Version numbers consistent across:
  - `pyproject.toml`
  - `CHANGELOG.md`
  - `README.md`
  - `README_PYPI.md`
  - Branch name `dev/v0.1.X`

### 6.2 Documentation Quality
- [ ] All code examples are runnable
- [ ] All commands are tested
- [ ] All file paths are absolute (from repo root)
- [ ] Formatting is consistent (follow existing style)

### 6.3 Completeness Check
- [ ] Every feature has user-facing documentation
- [ ] Every config change has examples
- [ ] Every breaking change has migration guide
- [ ] Case study demonstrates key features

---

## Phase 7: Commit & Release 🚀

### 7.1 Stage Changes
```bash
# Stage modified tracked files
git add -u .

# Add new files explicitly
git add docs/source/examples/case_studies/v0.1.X-feature.md
git add docs/source/user_guide/new-feature.rst
git add massgen/configs/category/new-config.yaml

# Verify staging
git status
```

### 7.2 Commit
```bash
git commit -m "docs: Release v0.1.X documentation

- Updated CHANGELOG.md with full release notes
- Added case study: [Feature Name]
- Updated README.md Recent Achievements
- Enhanced Sphinx documentation (user_guide/feature.rst)
- Added example configurations
- Updated roadmap and contributing guides

Major features:
- Feature 1: Description
- Feature 2: Description
- Bug fixes: #123, #456
"
```

### 7.3 Push & Create PR
```bash
# Push release branch
git push origin dev/v0.1.X

# Create PR: dev/v0.1.X → main
gh pr create --base main --head dev/v0.1.X \
  --title "Release v0.1.X: [Feature Name]" \
  --body "See CHANGELOG.md for full release notes"
```

### 7.4 Tag Release (After PR Merge)
```bash
# After merging to main
git checkout main
git pull

# Create annotated tag
git tag -a v0.1.X -m "Release v0.1.X: [Feature Name]

Major features:
- Feature 1
- Feature 2

See CHANGELOG.md for details.
"

# Push tag
git push origin v0.1.X
```

### 7.5 Publish to PyPI (if applicable)
```bash
# Build package
uv build

# Publish to PyPI
uv publish

# Verify on PyPI
# https://pypi.org/project/massgen/
```

### 7.6 GitHub Release
- [ ] Create GitHub release from tag `v0.1.X`
- [ ] Copy CHANGELOG.md section to release notes
- [ ] Attach any release assets (if applicable)
- [ ] Publish release

---

## Post-Release 📢

### 8.1 Verify Deployment
- [ ] PyPI package updated: https://pypi.org/project/massgen/
- [ ] ReadTheDocs built: https://docs.massgen.ai/
- [ ] GitHub release published
- [ ] Tag visible in repository

### 8.2 Announcement (if applicable)
- [ ] Update project README on GitHub
- [ ] Post to community channels
- [ ] Update any external documentation

### 8.3 Prepare Next Release
- [ ] Create `dev/v0.1.X+1` branch for next cycle
- [ ] Update `ROADMAP_v0.1.X+1.md`
- [ ] Close milestone `v0.1.X`
- [ ] Create milestone `v0.1.X+1`

---

## Quick Reference Checklist ✅

**Must Update:**
1. ✅ `CHANGELOG.md`
2. ✅ `docs/source/user_guide/` (if user-facing feature)
3. ✅ `README.md` (Recent Achievements)
4. ✅ `massgen/configs/` (example configs)
5. ✅ `massgen/configs/README.md`
6. ✅ Case study in `docs/source/examples/case_studies/`

**Should Update (if applicable):**
7. ⚠️ `massgen/config_builder.py` (if config params added)
8. ⚠️ `massgen/backend/capabilities.py` (if backend changes)
9. ✅ `README_PYPI.md` (auto-synced via pre-commit hook when README.md changes)
10. ⚠️ `ROADMAP.md` (mark completed items)
11. ⚠️ `ROADMAP_v0.1.X+1.md` (plan next release)
12. ⚠️ `CONTRIBUTING.md` (if process changed)

**Auto-Updated (DO NOT EDIT):**
- ❌ `docs/source/development/roadmap.rst` (pulls from `ROADMAP.md`)
- ❌ `docs/source/development/contributing.rst` (pulls from `CONTRIBUTING.md`)

**Build & Verify:**
13. 🔨 `cd docs && make html && make linkcheck`
14. 🔨 Test new config files
15. 🔨 Verify all links work

---

## Automation Tools 🤖

### ✅ Implemented

1. **README_PYPI.md Auto-Sync** - Pre-commit hook + `scripts/sync_readme_pypi.py`
   - **Automatic**: Runs via pre-commit hook when README.md is committed
   - **Manual**: `uv run python scripts/sync_readme_pypi.py`
   - Replaces relative asset paths with full GitHub URLs for PyPI display
   - Configured in `.pre-commit-config.yaml` (local hook)

### 🔮 Future Enhancements

2. **Roadmap Generator from GitHub Issues**
   ```bash
   # scripts/generate_roadmap_from_issues.py
   # Pull issues with milestone v0.1.X → ROADMAP_v0.1.X.md
   ```

3. **CHANGELOG Helper**
   ```bash
   # scripts/generate_changelog_draft.py
   # Extract PR titles/descriptions from dev/v0.1.X
   # Generate CHANGELOG draft
   ```

4. **Documentation Link Validator**
   ```bash
   # scripts/validate_docs_references.py
   # Verify all file paths in CHANGELOG/README exist
   # Check all internal links resolve
   ```

5. **Release Checklist Validator**
   ```bash
   # scripts/validate_release.py
   # Check version consistency across files
   # Verify all required docs exist
   # Ensure case study is present
   ```

---

## Notes

- This checklist should be copied for each release
- Track progress by checking boxes as you go
- Add release-specific notes below

---

## Release-Specific Notes

*Add any special considerations for this release here:*

-
-
-

