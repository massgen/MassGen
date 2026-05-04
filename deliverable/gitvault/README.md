# GitVault

GitVault is a GitHub-inspired platform built as a single deployable FastAPI application with SQLite-backed collaboration features and real Git repository operations.

## Run locally

```bash
uv sync
uv run uvicorn gitvault.app:app --reload
```

Then open `http://127.0.0.1:8000`.

## Core capabilities in this build

- User registration, persistent session tracking, TOTP-based 2FA, personal access tokens, SSH/GPG key management
- Repository creation, visibility, archive/delete, forking
- File browser, README rendering, raw view, blame, file history, compare view, ZIP download
- Branches, tags, commit history, simple web editor/commit flow, releases
- Issues, pull requests, review requests, inline suggested-change comments, merge strategies, protected branches, CODEOWNERS-aware review checks, and queued auto-merge
- Discussions, projects, wiki, notifications, profiles, orgs, admin dashboard
- Workflow YAML parsing and simulated Actions runs/logs
- Search, trending, explore, stars, watches, contributors, language and dependency insights
- Pages preview, package registry records, marketplace directory, sponsorship tiers, REST/GraphQL-style JSON endpoints
- Repository webhooks with event filtering plus recorded deliveries for push/issues/pull_request/release/discussion events
