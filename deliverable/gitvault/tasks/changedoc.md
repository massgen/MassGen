# Change Document

**Sources reviewed:** agent1.2, agent_a

## Summary
Final GitVault consolidates the verified FastAPI + SQLite + Git implementation into this workspace and keeps the strongest depth improvements in pull requests: review requests, inline review comments with suggested changes, CODEOWNERS-aware approval enforcement, queued auto-merge, and fallback status checks for protected branches. The delivered app remains a real, runnable web application with persistent state, on-disk repositories, browser UI, and JSON API surfaces rather than a mock prototype.

## Decisions

### DEC-001: Keep the real full-stack FastAPI + Git architecture
**Origin:** agent1.2 (kept)
**Choice:** Continue with a real server-rendered FastAPI application backed by SQLite and on-disk Git repositories.
**Why:** The request called for a GitHub-style platform, so the solution needed durable state, working authentication, real repository operations, and actual HTTP routes instead of static pages or placeholders.
**Synthesis Note:** This remained the right foundation for the final answer. The strongest path was to preserve the broad feature surface already present and deepen central collaboration flows.
**Alternatives considered:**
- Rebuild from scratch: rejected because the existing implementation already provided the strongest working platform base.
- Replace the app with a frontend-only demo: rejected because it would remove the persistence and Git behavior that make the result credible.
**Implementation:**
- `gitvault/app.py` → `create_app()` and the registered HTML/JSON routes
- `gitvault/database.py` → `Database` schema and persistence helpers
- `gitvault/gitops.py` → `GitService` repository lifecycle, history, compare, archive, and merge operations

### DEC-002: Deepen pull requests into a fuller review workflow
**Origin:** agent1.2 → agent_a (modified)
**Choice:** Extend pull requests with review requests, inline review comments, suggested changes, queue-backed auto-merge, and richer PR detail rendering.
**Why:** Pull requests are a flagship GitHub workflow. Without reviewer assignment, code-review comments, or queued auto-merge, the application would feel materially less like a collaboration platform.
**Synthesis Note:** The final answer keeps the baseline open/review/merge flow and turns it into a more complete end-to-end review loop.
**Alternatives considered:**
- Spend the same effort on another shallow top-level module: rejected because PR collaboration is more central to the requested platform.
- Limit reviews to summary approvals only: rejected because inline context and suggested edits are part of the expected GitHub experience.
**Implementation:**
- `gitvault/app.py` → `pr_detail()`, `request_pr_reviewers()`, `add_pr_comment()`, `enable_auto_merge()`
- `gitvault/database.py` → `review_comments` table plus reviewer and auto-merge persistence helpers in `Database`
- `tests/test_gitvault.py` → `test_pull_request_review_requests_inline_suggestions_and_auto_merge_queue`

### DEC-003: Make CODEOWNERS and branch protection rules affect mergeability
**Origin:** agent1.2 → agent_a (modified)
**Choice:** Add live PR gate evaluation for merge conflicts, required reviews, required status checks, and CODEOWNERS approvals based on changed files.
**Why:** Protected branches and CODEOWNERS only matter if they can block or permit merges. Wiring them into merge gates makes the platform's governance model meaningfully closer to GitHub.
**Synthesis Note:** The final implementation keeps the existing branch-rule concepts and connects them to real Git diff data and review state.
**Alternatives considered:**
- Keep CODEOWNERS informational only: rejected because it would not satisfy the intended repository-governance behavior.
- Hardcode placeholder approvers: rejected because it would make normal repository flows brittle and unrealistic.
**Implementation:**
- `gitvault/app.py` → `pr_gate_state()` and merge/queue enforcement paths
- `gitvault/gitops.py` → `changed_files()` and `required_codeowners()`
- `tests/test_gitvault.py` → advanced PR workflow coverage and merge-path regression coverage

### DEC-004: Provide baseline status checks when no YAML workflows exist
**Origin:** agent_a — NEW
**Choice:** Have the Actions layer create a default “GitVault Checks” run for push- and PR-style events when no explicit workflow files are present.
**Why:** Required status checks were otherwise impossible to satisfy on fresh repositories. A baseline check keeps protected-branch rules coherent even before a repository adds custom CI.
**Implementation:**
- `gitvault/app.py` → `trigger_actions()` fallback check-run creation
- `tests/test_gitvault.py` → advanced PR auto-merge coverage exercises the required-status-check path

## Deliberation Trail

### agent1.2
- Introduced the working FastAPI + SQLite + Git platform foundation with broad repository, collaboration, and admin surfaces.
- Established the initial pull-request, issues, wiki, projects, actions, and API shape that the final answer retains.

### agent_a
- Kept the existing architecture and focused improvement effort on one of the most central GitHub workflows: pull requests.
- Added reviewer requests, inline suggested-change comments, queued auto-merge, and more credible protected-branch enforcement.
- **NEW:** Added fallback Actions checks so required-status-check rules work on new repositories without custom workflow YAML.
