# GitHub Actions Release Automation

**Status:** ✅ Configured
**Created:** October 2025

## Overview

MassGen includes GitHub Actions workflows to automatically update README.md when you tag a new release. Two approaches are available:

1. **PR Workflow** (Recommended) - Creates a pull request for review
2. **Auto-merge Workflow** - Directly commits to main branch

## Approach 1: PR Workflow (Recommended)

**File:** `.github/workflows/release-docs-automation.yml`

### What It Does

When you push a tag like `v0.0.29`:

1. ✅ **Verifies** release documentation exists
   - Checks for `docs/releases/v0.0.29/features-overview.md`
   - Checks for `docs/releases/v0.0.29/release-notes.md`
   - **Fails the workflow if missing**

2. ✅ **Runs** the update script
   - Executes `scripts/update_readme_release.py v0.0.29`
   - Updates README.md with new release info
   - Archives previous release

3. ✅ **Creates** a pull request
   - Branch: `docs/readme-update-v0.0.29`
   - Title: "📝 Update README for v0.0.29 release"
   - Labels: `documentation`, `automated`
   - **Waits for your review and merge**

### Workflow Diagram

```
git tag v0.0.29
git push --tags
        ↓
GitHub Actions Triggered
        ↓
┌─────────────────────────────────┐
│ 1. Verify Docs Exist            │
│    - features-overview.md ✅    │
│    - release-notes.md ✅        │
└─────────────────────────────────┘
        ↓
┌─────────────────────────────────┐
│ 2. Run Update Script            │
│    - Extract content            │
│    - Update README.md           │
│    - Archive previous release   │
└─────────────────────────────────┘
        ↓
┌─────────────────────────────────┐
│ 3. Create Pull Request          │
│    - Branch: docs/readme-update │
│    - Labels: documentation      │
│    - Status: Waiting for review │
└─────────────────────────────────┘
        ↓
   You review & merge
        ↓
   README.md updated!
```

### Benefits

✅ **Human review** before README changes
✅ **Safe** - no direct commits to main
✅ **Transparent** - see exact changes in PR
✅ **Rollback-friendly** - just close PR
✅ **CI/CD integration** - PR checks can run

### Usage

```bash
# 1. Create release docs
# docs/releases/v0.0.29/features-overview.md
# docs/releases/v0.0.29/release-notes.md

# 2. Commit and push docs
git add docs/releases/v0.0.29/
git commit -m "docs: add v0.0.29 release documentation"
git push origin main

# 3. Tag the release
git tag v0.0.29
git push origin v0.0.29

# 4. GitHub Actions will:
#    - Verify docs exist ✅
#    - Update README.md
#    - Create PR for you to review

# 5. Review and merge the PR
#    - Check README.md changes look correct
#    - Merge PR to update README on main
```

## Approach 2: Auto-merge Workflow

**File:** `.github/workflows/release-docs-automation-automerge.yml.disabled`

### What It Does

When you push a tag like `v0.0.29`:

1. ✅ Verifies release documentation exists
2. ✅ Runs the update script
3. ✅ **Auto-commits directly to main** (no PR)

### Workflow Diagram

```
git tag v0.0.29
git push --tags
        ↓
GitHub Actions Triggered
        ↓
┌─────────────────────────────────┐
│ 1. Verify Docs Exist            │
└─────────────────────────────────┘
        ↓
┌─────────────────────────────────┐
│ 2. Run Update Script            │
└─────────────────────────────────┘
        ↓
┌─────────────────────────────────┐
│ 3. Auto-commit to main          │
│    (No PR, immediate update)    │
└─────────────────────────────────┘
        ↓
   README.md updated immediately!
```

### Benefits

✅ **Fully automated** - zero manual steps
✅ **Fast** - immediate README update
✅ **Simple** - no PR to review

### Tradeoffs

⚠️ **No review** - changes go directly to main
⚠️ **Branch protection** - requires special setup
⚠️ **Less safe** - harder to rollback

### Activation

To use auto-merge instead of PR workflow:

1. **Rename the file:**
   ```bash
   mv .github/workflows/release-docs-automation-automerge.yml.disabled \
      .github/workflows/release-docs-automation-automerge.yml
   ```

2. **Disable PR workflow:**
   ```bash
   mv .github/workflows/release-docs-automation.yml \
      .github/workflows/release-docs-automation.yml.disabled
   ```

3. **Configure branch protection** (see below)

4. **Commit and push:**
   ```bash
   git add .github/workflows/
   git commit -m "ci: enable auto-merge release automation"
   git push origin main
   ```

## Branch Protection Configuration

### For PR Workflow (Recommended)

**Settings → Branches → main → Branch protection rules:**

```
✅ Require a pull request before merging
✅ Require approvals: 1
✅ Require status checks to pass
□ Allow force pushes (not needed)
```

**Permissions:**
- ✅ GitHub Actions can create PRs (default)
- No special configuration needed

### For Auto-merge Workflow

**Settings → Branches → main → Branch protection rules:**

```
□ Require a pull request before merging (DISABLED)
  OR
✅ Allow specific actors to bypass (add: github-actions[bot])

✅ Require status checks to pass (optional)
```

**Actions Permissions:**
Settings → Actions → General → Workflow permissions:
```
✅ Read and write permissions
✅ Allow GitHub Actions to create and approve pull requests
```

## Workflow Features

### Documentation Verification

Both workflows verify documentation exists before proceeding:

```yaml
- name: Verify release documentation exists
  run: |
    if [ ! -f "docs/releases/v0.0.29/features-overview.md" ]; then
      echo "❌ Missing: features-overview.md"
      exit 1
    fi
    if [ ! -f "docs/releases/v0.0.29/release-notes.md" ]; then
      echo "❌ Missing: release-notes.md"
      exit 1
    fi
```

**Result:** Workflow fails if docs missing - prevents incomplete releases

### Smart Change Detection

Only creates PR/commits if README.md actually changed:

```yaml
- name: Check for changes
  run: |
    if git diff --quiet README.md; then
      echo "No changes needed, skipping"
      exit 0
    fi
```

**Result:** No unnecessary PRs/commits if README already updated

### Detailed Summary

Each workflow run shows a summary:

```markdown
## 📋 Release Documentation Automation Summary

**Release:** v0.0.29

✅ Documentation verification: PASSED
  - features-overview.md found
  - release-notes.md found

✅ README update: COMPLETED
  - Pull request created for review
```

## Trigger Conditions

### What Triggers the Workflow

```yaml
on:
  push:
    tags:
      - 'v*.*.*'  # Any tag matching v0.0.29, v1.2.3, etc.
```

**Triggers on:**
- ✅ `git push origin v0.0.29`
- ✅ `git push origin v1.0.0`
- ✅ `git push --tags` (if includes v*.*.*)

**Does NOT trigger on:**
- ❌ Regular commits to main
- ❌ Branch pushes
- ❌ Non-version tags (like `beta`, `alpha`)
- ❌ Tags without 'v' prefix (like `0.0.29`)

### Manual Trigger

You can also manually run the workflow:

1. Go to Actions → Release Documentation Automation
2. Click "Run workflow"
3. Select tag version
4. Click "Run workflow"

## Testing the Workflow

### Test on a Feature Branch

```bash
# 1. Create test branch
git checkout -b test-release-automation

# 2. Create test release docs
mkdir -p docs/releases/v0.0.99-test
cat > docs/releases/v0.0.99-test/features-overview.md << 'EOF'
# v0.0.99-test Features Overview
Test release for automation
EOF

cat > docs/releases/v0.0.99-test/release-notes.md << 'EOF'
# Test Release Notes
Testing the automation workflow
EOF

# 3. Commit
git add docs/releases/v0.0.99-test/
git commit -m "test: add test release docs"
git push origin test-release-automation

# 4. Create test tag
git tag v0.0.99-test
git push origin v0.0.99-test

# 5. Watch GitHub Actions
# - Go to Actions tab
# - See workflow run
# - Verify it creates PR or commits

# 6. Clean up
git push --delete origin v0.0.99-test
git tag -d v0.0.99-test
```

## Troubleshooting

### Workflow doesn't trigger

**Check:**
1. Tag format: Must be `v*.*.*` (e.g., `v0.0.29`)
2. Tag pushed to GitHub: `git push origin v0.0.29`
3. Workflow file exists and is enabled (not `.disabled`)
4. GitHub Actions enabled in repository settings

### Documentation verification fails

**Error:**
```
❌ Missing: docs/releases/v0.0.29/features-overview.md
```

**Solution:**
1. Create the required documentation files
2. Commit and push to main BEFORE tagging
3. Tag and push again

### PR creation fails

**Error:**
```
failed to create pull request
```

**Solution:**
1. Verify GitHub token has required permissions
2. Check if branch `docs/readme-update-v0.0.29` already exists
3. Check branch protection rules aren't blocking Actions

### Auto-merge commits fail

**Error:**
```
failed to push to main: protected branch
```

**Solution:**
1. Configure branch protection to allow GitHub Actions
2. Add `github-actions[bot]` to bypass list
3. Or switch to PR workflow (recommended)

### Script execution fails

**Error:**
```
python: command not found
```

**Solution:**
- Workflow includes Python setup, this shouldn't happen
- If it does, check Python version in workflow matches script requirements

## Comparison Table

| Feature | PR Workflow | Auto-merge Workflow |
|---------|------------|---------------------|
| **Human Review** | ✅ Required | ❌ None |
| **Safety** | ✅✅ Very safe | ⚠️ Less safe |
| **Speed** | 🐢 Manual merge needed | ⚡ Immediate |
| **Branch Protection** | ✅ Compatible | ⚠️ Requires bypass |
| **Rollback** | ✅ Easy (close PR) | ⚠️ Need to revert |
| **Transparency** | ✅✅ Full visibility | ✅ Commit visible |
| **Setup Complexity** | ✅ Simple | ⚠️ Requires config |
| **Recommended For** | Production | Personal projects |

## Recommendations

### Use PR Workflow When:

✅ Multiple team members
✅ Public repository
✅ Want review process
✅ Branch protection enabled
✅ **Production releases**

### Use Auto-merge When:

✅ Solo developer
✅ Private repository
✅ Trust automation fully
✅ Speed is critical
✅ **Internal/test releases**

## Security Considerations

### Token Permissions

Both workflows use `GITHUB_TOKEN` with limited permissions:

```yaml
permissions:
  contents: write        # Update README.md
  pull-requests: write   # Create PRs (PR workflow only)
```

**Security:**
- ✅ Token scoped to repository only
- ✅ Token expires after workflow
- ✅ No access to secrets or other repos

### Protected Branches

**PR Workflow:** Works with standard branch protection
**Auto-merge Workflow:** Requires bypass configuration

### Code Review

**PR Workflow:** Changes reviewed before merge
**Auto-merge Workflow:** No review (trust automation)

## Monitoring

### View Workflow Runs

1. Go to **Actions** tab in GitHub
2. Click **Release Documentation Automation**
3. See all runs with status

### Notifications

Configure notifications for workflow failures:

**Settings → Notifications → Actions:**
```
✅ Email me when workflow fails
✅ Email me when workflow succeeds (optional)
```

### Logs

Each workflow run has detailed logs:
1. Click on workflow run
2. Click on job "verify-and-update"
3. Expand each step to see output

## Future Enhancements

**Potential additions:**
- Slack/Discord notifications on release
- Automatic changelog update
- Release notes posting to GitHub Releases
- Social media announcements
- Documentation deployment trigger

## Example Workflow Runs

### Successful PR Workflow

```
✅ Verify release documentation exists
   ✅ Found: features-overview.md
   ✅ Found: release-notes.md

✅ Run README update script
   📝 Extracted content from features-overview.md
   ✅ Updated README.md

✅ Create pull request
   🌿 Created branch: docs/readme-update-v0.0.29
   🔄 Created PR #123
   ✅ Pull request ready for review
```

### Successful Auto-merge Workflow

```
✅ Verify release documentation exists
   ✅ Documentation verified

✅ Run README update script
   ✅ README.md updated

✅ Commit and push changes
   ⬆️  Pushed to main
   ✅ README.md updated on main!
```

### Failed Verification

```
❌ Verify release documentation exists
   ❌ Missing: docs/releases/v0.0.29/features-overview.md
   ❌ Missing: docs/releases/v0.0.29/release-notes.md

   Please create the required documentation before tagging

Workflow failed ❌
```

## Related Documentation

- [Release Documentation System](RELEASE_DOCUMENTATION_SYSTEM.md) - System overview
- [Release README Update Workflow](release_readme_update.md) - Manual workflow
- [GitHub Actions Documentation](https://docs.github.com/en/actions) - Official docs

---

**Created:** October 2025
**Maintained By:** MassGen Team
**Workflow Files:**
- `.github/workflows/release-docs-automation.yml` (Active)
- `.github/workflows/release-docs-automation-automerge.yml.disabled` (Optional)
