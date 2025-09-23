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
- [ ] Bug fix (`fix:`) - Non-breaking change which fixes an issue
- [ ] New feature (`feat:`) - Non-breaking change which adds functionality
- [ ] Breaking change (`breaking:`) - Fix or feature that would cause existing functionality to not work as expected
- [ ] Documentation (`docs:`) - Documentation updates
- [ ] Code refactoring (`refactor:`) - Code changes that neither fix a bug nor add a feature
- [ ] Tests (`test:`) - Adding missing tests or correcting existing tests
- [ ] Chore (`chore:`) - Maintenance tasks, dependency updates, etc.
- [ ] Performance improvement (`perf:`) - Code changes that improve performance
- [ ] Code style (`style:`) - Changes that do not affect the meaning of the code (formatting, missing semi-colons, etc.)
- [ ] CI/CD (`ci:`) - Changes to CI/CD configuration files and scripts

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
# uv run pre-commit install
# git diff --name-only HEAD~1 | xargs uv run pre-commit run --files
# git add --all # if any fixes were applied
# git commit -m "chore: apply pre-commit fixes"
# git push origin <branch-name>
```

## Additional context
Add any other context about the PR here.