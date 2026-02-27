## 📝 PR Description

### What
Brief description of changes

### Why
Motivation and context

### How
Technical approach taken

### Testing
How you tested the changes

### Screenshots
If UI changes (if applicable)

---

## ✅ Checklist (Before Submitting)

- [ ] Code passes all pre-commit hooks
- [ ] Tests pass locally
- [ ] Documentation is updated if needed
- [ ] Commit messages follow convention
- [ ] PR targets `dev/v0.1.57` branch (or `main` if dev branch doesn't exist yet)

---

## 🔄 Addressing Original Issue
*🔗 Issue Addressed: Closes #[issue-number]*

Explain how the changes made address the issues and requirements outlined in the original issue.

---

## 📋 Additional Notes
*Add any additional context, caveats, or follow-up items here*

---

## 💻 CODE CHANGES

## Summary
Brief description of what was implemented.

## Key Changes
Describe the key changes made to the codebase, including new features, modifications, bug fixes, refactoring, or any other relevant updates.

---

## 🧪 Testing
*Describe how you tested your changes. Include test commands if applicable.*

Example:
```bash
# Run tests
uv run pytest massgen/tests/ -v

# Run specific test file
uv run pytest massgen/tests/test_config_validator.py -v

# Run linting/formatting
uv run pre-commit run --all-files
```

---

## 📚 Documentation
*Is documentation updated?*

- [ ] Yes - documentation added/updated in `docs/`
- [ ] No documentation changes needed

---

## 🔍 Review Process

1. Automated checks will run on your PR
2. **CodeRabbit** will provide AI-powered code review comments
3. Maintainers will review your code
4. Address any feedback or requested changes
5. Once approved, PR will be merged

**Useful CodeRabbit commands** (in PR comments):
- `@coderabbitai review` - Trigger incremental review
- `@coderabbitai resolve` - Mark all comments as resolved
- `@coderabbitai summary` - Regenerate PR summary
