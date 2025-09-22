## PR Title Format
Your PR title must follow the format: `<type>: <brief description>`

Valid types:
- `fix:` - Bug fixes
- `feat:` - New features
- `breaking:` - Breaking changes
- `docs:` - Documentation updates
- `refactor:` - Code refactoring
- `test:` - Test additions/modifications
- `chore:` - Maintenance tasks
- `perf:` - Performance improvements
- `style:` - Code style changes
- `ci:` - CI/CD configuration changes

Examples:
- `fix: resolve memory leak in data processing`
- `feat: add export to CSV functionality`
- `breaking: change API response format`
- `docs: update installation guide`

## Description
Brief description of the changes in this PR

## Type of change
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update

## Checklist
- [ ] I have run pre-commit on my changed files and all checks pass
- [ ] My code follows the style guidelines of this project
- [ ] I have performed a self-review of my own code
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] I have made corresponding changes to the documentation
- [ ] My changes generate no new warnings
- [ ] I have added tests that prove my fix is effective or that my feature works
- [ ] New and existing unit tests pass locally with my changes

## Pre-commit status
```
# Paste the output of running pre-commit on your changed files:
# git diff --name-only HEAD~1 | xargs pre-commit run --files
```

## Additional context
Add any other context about the PR here.