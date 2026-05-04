from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    bio TEXT DEFAULT '',
    location TEXT DEFAULT '',
    social_links_json TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    is_admin INTEGER DEFAULT 1,
    achievements_json TEXT DEFAULT '["Founder"]'
);

CREATE TABLE IF NOT EXISTS organizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    description TEXT DEFAULT '',
    owner_user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(owner_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS org_members (
    org_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    PRIMARY KEY (org_id, user_id),
    FOREIGN KEY(org_id) REFERENCES organizations(id) ON DELETE CASCADE,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    permission TEXT NOT NULL,
    FOREIGN KEY(org_id) REFERENCES organizations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS repositories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_slug TEXT NOT NULL,
    owner_type TEXT NOT NULL,
    owner_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    slug TEXT NOT NULL,
    description TEXT DEFAULT '',
    visibility TEXT NOT NULL,
    archived INTEGER DEFAULT 0,
    default_branch TEXT DEFAULT 'main',
    topics_json TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    stars_count INTEGER DEFAULT 0,
    watchers_count INTEGER DEFAULT 0,
    forks_count INTEGER DEFAULT 0,
    transfer_target_slug TEXT DEFAULT '',
    UNIQUE(owner_slug, slug)
);

CREATE TABLE IF NOT EXISTS repo_collaborators (
    repo_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    permission TEXT NOT NULL,
    PRIMARY KEY (repo_id, user_id),
    FOREIGN KEY(repo_id) REFERENCES repositories(id) ON DELETE CASCADE,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS branch_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL,
    branch_name TEXT NOT NULL,
    require_reviews INTEGER DEFAULT 0,
    codeowners_required INTEGER DEFAULT 0,
    required_status_checks INTEGER DEFAULT 0,
    FOREIGN KEY(repo_id) REFERENCES repositories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS releases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL,
    tag_name TEXT NOT NULL,
    title TEXT NOT NULL,
    notes TEXT DEFAULT '',
    prerelease INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(repo_id) REFERENCES repositories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL,
    number INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT DEFAULT '',
    state TEXT NOT NULL,
    locked INTEGER DEFAULT 0,
    author_id INTEGER NOT NULL,
    labels_json TEXT DEFAULT '[]',
    assignees_json TEXT DEFAULT '[]',
    milestone TEXT DEFAULT '',
    pinned INTEGER DEFAULT 0,
    linked_issue_number INTEGER,
    reactions_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(repo_id, number),
    FOREIGN KEY(repo_id) REFERENCES repositories(id) ON DELETE CASCADE,
    FOREIGN KEY(author_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS pull_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL,
    number INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT DEFAULT '',
    state TEXT NOT NULL,
    draft INTEGER DEFAULT 0,
    source_branch TEXT NOT NULL,
    target_branch TEXT NOT NULL,
    author_id INTEGER NOT NULL,
    review_state TEXT DEFAULT 'COMMENTED',
    reviewers_json TEXT DEFAULT '[]',
    linked_issue_number INTEGER,
    auto_merge INTEGER DEFAULT 0,
    merge_strategy TEXT DEFAULT '',
    merge_queue_position INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    merged_at TEXT DEFAULT '',
    UNIQUE(repo_id, number),
    FOREIGN KEY(repo_id) REFERENCES repositories(id) ON DELETE CASCADE,
    FOREIGN KEY(author_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_id INTEGER NOT NULL,
    author_id INTEGER NOT NULL,
    state TEXT NOT NULL,
    body TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(pr_id) REFERENCES pull_requests(id) ON DELETE CASCADE,
    FOREIGN KEY(author_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS review_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_id INTEGER NOT NULL,
    author_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    line_number INTEGER DEFAULT 1,
    body TEXT DEFAULT '',
    suggested_change TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(pr_id) REFERENCES pull_requests(id) ON DELETE CASCADE,
    FOREIGN KEY(author_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS discussions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL,
    number INTEGER NOT NULL,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT DEFAULT '',
    state TEXT DEFAULT 'open',
    author_id INTEGER NOT NULL,
    answer_comment_id INTEGER,
    pinned INTEGER DEFAULT 0,
    locked INTEGER DEFAULT 0,
    reactions_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE(repo_id, number),
    FOREIGN KEY(repo_id) REFERENCES repositories(id) ON DELETE CASCADE,
    FOREIGN KEY(author_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS discussion_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discussion_id INTEGER NOT NULL,
    author_id INTEGER NOT NULL,
    body TEXT NOT NULL,
    is_answer INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(discussion_id) REFERENCES discussions(id) ON DELETE CASCADE,
    FOREIGN KEY(author_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    view_type TEXT DEFAULT 'board',
    custom_fields_json TEXT DEFAULT '["Status","Owner","Due Date"]',
    created_at TEXT NOT NULL,
    FOREIGN KEY(repo_id) REFERENCES repositories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS project_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    item_type TEXT NOT NULL,
    item_id INTEGER NOT NULL,
    status TEXT DEFAULT 'Todo',
    field_values_json TEXT DEFAULT '{}',
    position INTEGER DEFAULT 0,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS wiki_pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL,
    slug TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT DEFAULT '',
    sidebar TEXT DEFAULT '',
    updated_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(repo_id, slug),
    FOREIGN KEY(repo_id) REFERENCES repositories(id) ON DELETE CASCADE,
    FOREIGN KEY(updated_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS wiki_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    updated_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(page_id) REFERENCES wiki_pages(id) ON DELETE CASCADE,
    FOREIGN KEY(updated_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS action_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL,
    workflow_name TEXT NOT NULL,
    event_name TEXT NOT NULL,
    status TEXT NOT NULL,
    logs TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(repo_id) REFERENCES repositories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS packages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL,
    ecosystem TEXT NOT NULL,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    visibility TEXT DEFAULT 'private',
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(repo_id) REFERENCES repositories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS stars (
    user_id INTEGER NOT NULL,
    repo_id INTEGER NOT NULL,
    PRIMARY KEY (user_id, repo_id),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(repo_id) REFERENCES repositories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS watches (
    user_id INTEGER NOT NULL,
    repo_id INTEGER NOT NULL,
    PRIMARY KEY (user_id, repo_id),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(repo_id) REFERENCES repositories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS followers (
    follower_id INTEGER NOT NULL,
    following_id INTEGER NOT NULL,
    PRIMARY KEY (follower_id, following_id),
    FOREIGN KEY(follower_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(following_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    message TEXT NOT NULL,
    url TEXT DEFAULT '',
    is_read INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_security (
    user_id INTEGER PRIMARY KEY,
    two_factor_enabled INTEGER DEFAULT 0,
    totp_secret TEXT DEFAULT '',
    required_2fa INTEGER DEFAULT 0,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    session_token TEXT UNIQUE NOT NULL,
    user_agent TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    revoked_at TEXT DEFAULT '',
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS api_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    token_prefix TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    scopes_json TEXT DEFAULT '[]',
    repo_scope TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    last_used_at TEXT DEFAULT '',
    revoked_at TEXT DEFAULT '',
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    key_type TEXT NOT NULL,
    title TEXT NOT NULL,
    public_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    revoked_at TEXT DEFAULT '',
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS repo_webhooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL,
    target_url TEXT NOT NULL,
    secret TEXT DEFAULT '',
    events_json TEXT DEFAULT '[]',
    active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    FOREIGN KEY(repo_id) REFERENCES repositories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    webhook_id INTEGER NOT NULL,
    event_name TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(webhook_id) REFERENCES repo_webhooks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sponsorship_tiers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_slug TEXT NOT NULL,
    name TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    perks TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sponsorships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sponsor_user_id INTEGER NOT NULL,
    tier_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(sponsor_user_id) REFERENCES users(id),
    FOREIGN KEY(tier_id) REFERENCES sponsorship_tiers(id)
);

CREATE TABLE IF NOT EXISTS marketplace_apps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    description TEXT NOT NULL,
    install_url TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS repo_traffic (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(repo_id) REFERENCES repositories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_user_id INTEGER,
    action TEXT NOT NULL,
    target TEXT NOT NULL,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(actor_user_id) REFERENCES users(id)
);
"""


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def decode_record(record: dict[str, Any] | None) -> dict[str, Any] | None:
    if record is None:
        return None
    for key, value in list(record.items()):
        if key.endswith("_json") and isinstance(value, str):
            record[key[:-5]] = json.loads(value or "null")
    return record


@dataclass
class Database:
    path: Path

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            existing = conn.execute("SELECT COUNT(*) FROM marketplace_apps").fetchone()[0]
            if existing == 0:
                conn.executemany(
                    "INSERT INTO marketplace_apps (name, kind, description, install_url) VALUES (?, ?, ?, ?)",
                    [
                        ("Super Linter", "Action", "Run lint checks on every push.", "#"),
                        ("DeployBot", "GitHub App", "Push deployments with environment approvals.", "#"),
                        ("Acme OAuth", "OAuth App", "Single sign-on for enterprise teams.", "#"),
                    ],
                )

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def fetchone(self, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self.connect() as conn:
            return decode_record(row_to_dict(conn.execute(query, params).fetchone()))

    def fetchall(self, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [decode_record(row_to_dict(row)) for row in conn.execute(query, params).fetchall()]

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> int:
        with self.connect() as conn:
            cur = conn.execute(query, params)
            conn.commit()
            return int(cur.lastrowid or 0)

    def log(self, actor_user_id: int | None, action: str, target: str, metadata: dict[str, Any] | None = None) -> None:
        self.execute(
            "INSERT INTO audit_logs (actor_user_id, action, target, metadata_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (actor_user_id, action, target, json.dumps(metadata or {}), utcnow()),
        )

    def create_user(self, email: str, username: str, password_hash: str) -> int:
        user_id = self.execute(
            "INSERT INTO users (email, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (email, username, password_hash, utcnow()),
        )
        self.log(user_id, "user.create", username)
        return user_id

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        return self.fetchone("SELECT * FROM users WHERE email = ?", (email,))

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        return self.fetchone("SELECT * FROM users WHERE username = ?", (username,))

    def get_user(self, user_id: int) -> dict[str, Any] | None:
        return self.fetchone("SELECT * FROM users WHERE id = ?", (user_id,))

    def list_users(self) -> list[dict[str, Any]]:
        return self.fetchall("SELECT * FROM users ORDER BY created_at DESC")

    def create_org(self, owner_user_id: int, name: str, slug: str, description: str) -> int:
        org_id = self.execute(
            "INSERT INTO organizations (name, slug, description, owner_user_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (name, slug, description, owner_user_id, utcnow()),
        )
        self.execute(
            "INSERT INTO org_members (org_id, user_id, role) VALUES (?, ?, ?)",
            (org_id, owner_user_id, "owner"),
        )
        self.execute(
            "INSERT INTO teams (org_id, name, permission) VALUES (?, ?, ?)",
            (org_id, "core", "admin"),
        )
        self.log(owner_user_id, "org.create", slug)
        return org_id

    def get_org(self, slug: str) -> dict[str, Any] | None:
        return self.fetchone("SELECT * FROM organizations WHERE slug = ?", (slug,))

    def list_orgs_for_user(self, user_id: int) -> list[dict[str, Any]]:
        return self.fetchall(
            "SELECT o.* FROM organizations o JOIN org_members m ON m.org_id = o.id WHERE m.user_id = ? ORDER BY o.created_at DESC",
            (user_id,),
        )

    def create_repo(
        self,
        owner_slug: str,
        owner_type: str,
        owner_id: int,
        name: str,
        description: str,
        visibility: str,
        topics: list[str],
    ) -> int:
        repo_id = self.execute(
            """
            INSERT INTO repositories (
                owner_slug, owner_type, owner_id, name, slug, description, visibility, topics_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (owner_slug, owner_type, owner_id, name, name, description, visibility, json.dumps(topics), utcnow(), utcnow()),
        )
        self.execute(
            "INSERT INTO branch_rules (repo_id, branch_name, require_reviews, codeowners_required, required_status_checks) VALUES (?, ?, ?, ?, ?)",
            (repo_id, "main", 0, 1, 0),
        )
        self.log(owner_id if owner_type == "user" else None, "repo.create", f"{owner_slug}/{name}")
        return repo_id

    def get_repo(self, owner_slug: str, slug: str) -> dict[str, Any] | None:
        return self.fetchone("SELECT * FROM repositories WHERE owner_slug = ? AND slug = ?", (owner_slug, slug))

    def get_repo_by_id(self, repo_id: int) -> dict[str, Any] | None:
        return self.fetchone("SELECT * FROM repositories WHERE id = ?", (repo_id,))

    def list_repos(self, visibility: str | None = None) -> list[dict[str, Any]]:
        if visibility:
            return self.fetchall("SELECT * FROM repositories WHERE visibility = ? ORDER BY updated_at DESC", (visibility,))
        return self.fetchall("SELECT * FROM repositories ORDER BY updated_at DESC")

    def list_owner_repos(self, owner_slug: str) -> list[dict[str, Any]]:
        return self.fetchall("SELECT * FROM repositories WHERE owner_slug = ? ORDER BY updated_at DESC", (owner_slug,))

    def update_repo_state(self, repo_id: int, *, archived: int | None = None, visibility: str | None = None) -> None:
        repo = self.get_repo_by_id(repo_id)
        archived_val = repo["archived"] if archived is None else archived
        visibility_val = repo["visibility"] if visibility is None else visibility
        self.execute(
            "UPDATE repositories SET archived = ?, visibility = ?, updated_at = ? WHERE id = ?",
            (archived_val, visibility_val, utcnow(), repo_id),
        )

    def delete_repo(self, repo_id: int) -> None:
        self.execute("DELETE FROM repositories WHERE id = ?", (repo_id,))

    def increment_counter(self, table: str, column: str, record_id: int, delta: int) -> None:
        self.execute(f"UPDATE {table} SET {column} = {column} + ?, updated_at = ? WHERE id = ?", (delta, utcnow(), record_id))

    def add_notification(self, user_id: int, kind: str, message: str, url: str = "") -> None:
        self.execute(
            "INSERT INTO notifications (user_id, kind, message, url, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, kind, message, url, utcnow()),
        )

    def list_notifications(self, user_id: int | None = None) -> list[dict[str, Any]]:
        if user_id is None:
            return self.fetchall("SELECT * FROM notifications ORDER BY created_at DESC")
        return self.fetchall("SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC", (user_id,))

    def get_user_security(self, user_id: int) -> dict[str, Any]:
        record = self.fetchone("SELECT * FROM user_security WHERE user_id = ?", (user_id,))
        if record:
            return record
        self.execute("INSERT INTO user_security (user_id) VALUES (?)", (user_id,))
        return self.fetchone("SELECT * FROM user_security WHERE user_id = ?", (user_id,))

    def enable_totp(self, user_id: int, secret: str) -> None:
        self.execute(
            "INSERT INTO user_security (user_id, two_factor_enabled, totp_secret, required_2fa) VALUES (?, 1, ?, 1) "
            "ON CONFLICT(user_id) DO UPDATE SET two_factor_enabled = 1, totp_secret = excluded.totp_secret, required_2fa = 1",
            (user_id, secret),
        )

    def create_user_session(self, user_id: int, session_token: str, user_agent: str = "") -> int:
        return self.execute(
            "INSERT INTO user_sessions (user_id, session_token, user_agent, created_at, last_seen_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, session_token, user_agent, utcnow(), utcnow()),
        )

    def get_user_session(self, session_token: str) -> dict[str, Any] | None:
        return self.fetchone("SELECT * FROM user_sessions WHERE session_token = ?", (session_token,))

    def list_user_sessions(self, user_id: int) -> list[dict[str, Any]]:
        return self.fetchall(
            "SELECT * FROM user_sessions WHERE user_id = ? AND revoked_at = '' ORDER BY last_seen_at DESC",
            (user_id,),
        )

    def touch_user_session(self, session_token: str) -> None:
        self.execute("UPDATE user_sessions SET last_seen_at = ? WHERE session_token = ?", (utcnow(), session_token))

    def revoke_user_session(self, session_token: str) -> None:
        self.execute("UPDATE user_sessions SET revoked_at = ? WHERE session_token = ?", (utcnow(), session_token))

    def create_api_token(
        self,
        user_id: int,
        name: str,
        token_prefix: str,
        token_hash: str,
        scopes: list[str],
        repo_scope: str = "",
    ) -> int:
        return self.execute(
            """
            INSERT INTO api_tokens (user_id, name, token_prefix, token_hash, scopes_json, repo_scope, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, name, token_prefix, token_hash, json.dumps(scopes), repo_scope, utcnow()),
        )

    def list_api_tokens(self, user_id: int) -> list[dict[str, Any]]:
        return self.fetchall(
            "SELECT * FROM api_tokens WHERE user_id = ? AND revoked_at = '' ORDER BY created_at DESC",
            (user_id,),
        )

    def get_api_token_by_hash(self, token_hash: str) -> dict[str, Any] | None:
        return self.fetchone(
            "SELECT * FROM api_tokens WHERE token_hash = ? AND revoked_at = ''",
            (token_hash,),
        )

    def touch_api_token(self, token_id: int) -> None:
        self.execute("UPDATE api_tokens SET last_used_at = ? WHERE id = ?", (utcnow(), token_id))

    def revoke_api_token(self, token_id: int) -> None:
        self.execute("UPDATE api_tokens SET revoked_at = ? WHERE id = ?", (utcnow(), token_id))

    def create_user_key(self, user_id: int, key_type: str, title: str, public_key: str) -> int:
        return self.execute(
            "INSERT INTO user_keys (user_id, key_type, title, public_key, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, key_type, title, public_key, utcnow()),
        )

    def list_user_keys(self, user_id: int, key_type: str | None = None) -> list[dict[str, Any]]:
        if key_type:
            return self.fetchall(
                "SELECT * FROM user_keys WHERE user_id = ? AND key_type = ? AND revoked_at = '' ORDER BY created_at DESC",
                (user_id, key_type),
            )
        return self.fetchall(
            "SELECT * FROM user_keys WHERE user_id = ? AND revoked_at = '' ORDER BY created_at DESC",
            (user_id,),
        )

    def create_repo_webhook(self, repo_id: int, target_url: str, secret: str, events: list[str]) -> int:
        return self.execute(
            "INSERT INTO repo_webhooks (repo_id, target_url, secret, events_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (repo_id, target_url, secret, json.dumps(events), utcnow()),
        )

    def list_repo_webhooks(self, repo_id: int) -> list[dict[str, Any]]:
        return self.fetchall(
            "SELECT * FROM repo_webhooks WHERE repo_id = ? AND active = 1 ORDER BY created_at DESC",
            (repo_id,),
        )

    def create_webhook_delivery(self, webhook_id: int, event_name: str, status: str, payload: dict[str, Any]) -> int:
        return self.execute(
            "INSERT INTO webhook_deliveries (webhook_id, event_name, status, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (webhook_id, event_name, status, json.dumps(payload), utcnow()),
        )

    def list_webhook_deliveries(self, repo_id: int) -> list[dict[str, Any]]:
        return self.fetchall(
            """
            SELECT d.*, h.target_url
            FROM webhook_deliveries d
            JOIN repo_webhooks h ON h.id = d.webhook_id
            WHERE h.repo_id = ?
            ORDER BY d.created_at DESC
            """,
            (repo_id,),
        )

    def create_issue(self, repo_id: int, author_id: int, title: str, body: str, labels: list[str]) -> int:
        number = (self.fetchone("SELECT COALESCE(MAX(number), 0) AS value FROM issues WHERE repo_id = ?", (repo_id,)) or {"value": 0})["value"] + 1
        issue_id = self.execute(
            """
            INSERT INTO issues (repo_id, number, title, body, state, author_id, labels_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?)
            """,
            (repo_id, number, title, body, author_id, json.dumps(labels), utcnow(), utcnow()),
        )
        return issue_id

    def get_issue(self, repo_id: int, number: int) -> dict[str, Any] | None:
        return self.fetchone("SELECT * FROM issues WHERE repo_id = ? AND number = ?", (repo_id, number))

    def list_issues(self, repo_id: int) -> list[dict[str, Any]]:
        return self.fetchall("SELECT * FROM issues WHERE repo_id = ? ORDER BY pinned DESC, number DESC", (repo_id,))

    def create_pull_request(
        self,
        repo_id: int,
        author_id: int,
        title: str,
        body: str,
        source_branch: str,
        target_branch: str,
        linked_issue_number: int | None,
        draft: bool,
    ) -> int:
        number = (self.fetchone("SELECT COALESCE(MAX(number), 0) AS value FROM pull_requests WHERE repo_id = ?", (repo_id,)) or {"value": 0})["value"] + 1
        pr_id = self.execute(
            """
            INSERT INTO pull_requests (
                repo_id, number, title, body, state, draft, source_branch, target_branch, author_id, linked_issue_number,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?)
            """,
            (repo_id, number, title, body, int(draft), source_branch, target_branch, author_id, linked_issue_number, utcnow(), utcnow()),
        )
        return pr_id

    def get_pr(self, repo_id: int, number: int) -> dict[str, Any] | None:
        return self.fetchone("SELECT * FROM pull_requests WHERE repo_id = ? AND number = ?", (repo_id, number))

    def list_prs(self, repo_id: int) -> list[dict[str, Any]]:
        return self.fetchall("SELECT * FROM pull_requests WHERE repo_id = ? ORDER BY number DESC", (repo_id,))

    def get_reviews(self, pr_id: int) -> list[dict[str, Any]]:
        return self.fetchall("SELECT * FROM reviews WHERE pr_id = ? ORDER BY created_at DESC", (pr_id,))

    def add_review(self, pr_id: int, author_id: int, state: str, body: str) -> int:
        review_id = self.execute(
            "INSERT INTO reviews (pr_id, author_id, state, body, created_at) VALUES (?, ?, ?, ?, ?)",
            (pr_id, author_id, state, body, utcnow()),
        )
        self.execute(
            "UPDATE pull_requests SET review_state = ?, updated_at = ? WHERE id = ?",
            (state, utcnow(), pr_id),
        )
        return review_id

    def set_pr_reviewers(self, pr_id: int, reviewers: list[str]) -> None:
        self.execute(
            "UPDATE pull_requests SET reviewers_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(sorted(set(reviewers))), utcnow(), pr_id),
        )

    def set_pr_auto_merge(self, pr_id: int, enabled: bool, strategy: str, queue_position: int = 0) -> None:
        self.execute(
            "UPDATE pull_requests SET auto_merge = ?, merge_strategy = ?, merge_queue_position = ?, updated_at = ? WHERE id = ?",
            (int(enabled), strategy, queue_position, utcnow(), pr_id),
        )

    def next_merge_queue_position(self, repo_id: int) -> int:
        row = self.fetchone(
            "SELECT COALESCE(MAX(merge_queue_position), 0) AS value FROM pull_requests WHERE repo_id = ?",
            (repo_id,),
        )
        return int((row or {"value": 0})["value"]) + 1

    def list_auto_merge_prs(self, repo_id: int) -> list[dict[str, Any]]:
        return self.fetchall(
            """
            SELECT * FROM pull_requests
            WHERE repo_id = ? AND state = 'open' AND auto_merge = 1
            ORDER BY merge_queue_position ASC, number ASC
            """,
            (repo_id,),
        )

    def add_review_comment(
        self,
        pr_id: int,
        author_id: int,
        file_path: str,
        line_number: int,
        body: str,
        suggested_change: str = "",
    ) -> int:
        return self.execute(
            """
            INSERT INTO review_comments (pr_id, author_id, file_path, line_number, body, suggested_change, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (pr_id, author_id, file_path, line_number, body, suggested_change, utcnow()),
        )

    def list_review_comments(self, pr_id: int) -> list[dict[str, Any]]:
        return self.fetchall(
            """
            SELECT c.*, u.username AS author_username
            FROM review_comments c
            JOIN users u ON u.id = c.author_id
            WHERE c.pr_id = ?
            ORDER BY c.created_at ASC
            """,
            (pr_id,),
        )

    def merge_pr(self, pr_id: int, strategy: str) -> None:
        self.execute(
            """
            UPDATE pull_requests
            SET state = 'merged', merge_strategy = ?, merged_at = ?, updated_at = ?, auto_merge = 0, merge_queue_position = 0
            WHERE id = ?
            """,
            (strategy, utcnow(), utcnow(), pr_id),
        )

    def list_branch_rules(self, repo_id: int) -> list[dict[str, Any]]:
        return self.fetchall("SELECT * FROM branch_rules WHERE repo_id = ? ORDER BY branch_name", (repo_id,))

    def get_branch_rule(self, repo_id: int, branch_name: str) -> dict[str, Any] | None:
        return self.fetchone("SELECT * FROM branch_rules WHERE repo_id = ? AND branch_name = ?", (repo_id, branch_name))

    def create_release(self, repo_id: int, tag_name: str, title: str, notes: str, prerelease: bool) -> int:
        return self.execute(
            "INSERT INTO releases (repo_id, tag_name, title, notes, prerelease, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (repo_id, tag_name, title, notes, int(prerelease), utcnow()),
        )

    def list_releases(self, repo_id: int) -> list[dict[str, Any]]:
        return self.fetchall("SELECT * FROM releases WHERE repo_id = ? ORDER BY created_at DESC", (repo_id,))

    def create_discussion(self, repo_id: int, author_id: int, category: str, title: str, body: str) -> int:
        number = (self.fetchone("SELECT COALESCE(MAX(number), 0) AS value FROM discussions WHERE repo_id = ?", (repo_id,)) or {"value": 0})["value"] + 1
        return self.execute(
            "INSERT INTO discussions (repo_id, number, category, title, body, author_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (repo_id, number, category, title, body, author_id, utcnow()),
        )

    def list_discussions(self, repo_id: int) -> list[dict[str, Any]]:
        return self.fetchall("SELECT * FROM discussions WHERE repo_id = ? ORDER BY pinned DESC, number DESC", (repo_id,))

    def create_project(self, repo_id: int, name: str, description: str, view_type: str) -> int:
        return self.execute(
            "INSERT INTO projects (repo_id, name, description, view_type, created_at) VALUES (?, ?, ?, ?, ?)",
            (repo_id, name, description, view_type, utcnow()),
        )

    def list_projects(self, repo_id: int) -> list[dict[str, Any]]:
        return self.fetchall("SELECT * FROM projects WHERE repo_id = ? ORDER BY created_at DESC", (repo_id,))

    def create_wiki_page(self, repo_id: int, title: str, content: str, sidebar: str, updated_by: int) -> int:
        slug = title.strip().lower().replace(" ", "-")
        page_id = self.execute(
            "INSERT INTO wiki_pages (repo_id, slug, title, content, sidebar, updated_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (repo_id, slug, title, content, sidebar, updated_by, utcnow(), utcnow()),
        )
        self.execute(
            "INSERT INTO wiki_revisions (page_id, content, updated_by, created_at) VALUES (?, ?, ?, ?)",
            (page_id, content, updated_by, utcnow()),
        )
        return page_id

    def list_wiki_pages(self, repo_id: int) -> list[dict[str, Any]]:
        return self.fetchall("SELECT * FROM wiki_pages WHERE repo_id = ? ORDER BY updated_at DESC", (repo_id,))

    def get_wiki_page(self, repo_id: int, slug: str) -> dict[str, Any] | None:
        return self.fetchone("SELECT * FROM wiki_pages WHERE repo_id = ? AND slug = ?", (repo_id, slug))

    def get_wiki_revisions(self, page_id: int) -> list[dict[str, Any]]:
        return self.fetchall("SELECT * FROM wiki_revisions WHERE page_id = ? ORDER BY created_at DESC", (page_id,))

    def create_action_run(self, repo_id: int, workflow_name: str, event_name: str, status: str, logs: str) -> int:
        return self.execute(
            "INSERT INTO action_runs (repo_id, workflow_name, event_name, status, logs, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (repo_id, workflow_name, event_name, status, logs, utcnow()),
        )

    def list_action_runs(self, repo_id: int) -> list[dict[str, Any]]:
        return self.fetchall("SELECT * FROM action_runs WHERE repo_id = ? ORDER BY created_at DESC", (repo_id,))

    def upsert_package(self, repo_id: int, ecosystem: str, name: str, version: str, visibility: str, metadata: dict[str, Any]) -> int:
        existing = self.fetchone(
            "SELECT * FROM packages WHERE repo_id = ? AND ecosystem = ? AND name = ? AND version = ?",
            (repo_id, ecosystem, name, version),
        )
        if existing:
            return existing["id"]
        return self.execute(
            "INSERT INTO packages (repo_id, ecosystem, name, version, visibility, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (repo_id, ecosystem, name, version, visibility, json.dumps(metadata), utcnow()),
        )

    def list_packages(self, repo_id: int) -> list[dict[str, Any]]:
        return self.fetchall("SELECT * FROM packages WHERE repo_id = ? ORDER BY created_at DESC", (repo_id,))

    def record_traffic(self, repo_id: int, event_type: str) -> None:
        self.execute("INSERT INTO repo_traffic (repo_id, event_type, created_at) VALUES (?, ?, ?)", (repo_id, event_type, utcnow()))

    def get_traffic(self, repo_id: int) -> list[dict[str, Any]]:
        return self.fetchall(
            "SELECT event_type, COUNT(*) AS count FROM repo_traffic WHERE repo_id = ? GROUP BY event_type ORDER BY count DESC",
            (repo_id,),
        )

    def search(self, query: str) -> dict[str, list[dict[str, Any]]]:
        like = f"%{query}%"
        return {
            "repositories": self.fetchall(
                "SELECT * FROM repositories WHERE name LIKE ? OR description LIKE ? ORDER BY updated_at DESC",
                (like, like),
            ),
            "issues": self.fetchall(
                "SELECT * FROM issues WHERE title LIKE ? OR body LIKE ? ORDER BY updated_at DESC",
                (like, like),
            ),
            "pull_requests": self.fetchall(
                "SELECT * FROM pull_requests WHERE title LIKE ? OR body LIKE ? ORDER BY updated_at DESC",
                (like, like),
            ),
            "discussions": self.fetchall(
                "SELECT * FROM discussions WHERE title LIKE ? OR body LIKE ? ORDER BY created_at DESC",
                (like, like),
            ),
            "wiki_pages": self.fetchall(
                "SELECT * FROM wiki_pages WHERE title LIKE ? OR content LIKE ? ORDER BY updated_at DESC",
                (like, like),
            ),
        }

    def stats(self) -> dict[str, int]:
        return {
            "users": self.fetchone("SELECT COUNT(*) AS count FROM users")["count"],
            "organizations": self.fetchone("SELECT COUNT(*) AS count FROM organizations")["count"],
            "repositories": self.fetchone("SELECT COUNT(*) AS count FROM repositories")["count"],
            "issues": self.fetchone("SELECT COUNT(*) AS count FROM issues")["count"],
            "pull_requests": self.fetchone("SELECT COUNT(*) AS count FROM pull_requests")["count"],
            "actions": self.fetchone("SELECT COUNT(*) AS count FROM action_runs")["count"],
            "tokens": self.fetchone("SELECT COUNT(*) AS count FROM api_tokens")["count"],
            "webhooks": self.fetchone("SELECT COUNT(*) AS count FROM repo_webhooks")["count"],
        }

    def list_marketplace_apps(self) -> list[dict[str, Any]]:
        return self.fetchall("SELECT * FROM marketplace_apps ORDER BY kind, name")

    def create_sponsorship_tier(self, owner_slug: str, name: str, amount_cents: int, perks: str) -> int:
        return self.execute(
            "INSERT INTO sponsorship_tiers (owner_slug, name, amount_cents, perks, created_at) VALUES (?, ?, ?, ?, ?)",
            (owner_slug, name, amount_cents, perks, utcnow()),
        )

    def list_sponsorship_tiers(self, owner_slug: str) -> list[dict[str, Any]]:
        return self.fetchall("SELECT * FROM sponsorship_tiers WHERE owner_slug = ? ORDER BY amount_cents", (owner_slug,))

    def list_audit_logs(self) -> list[dict[str, Any]]:
        return self.fetchall("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 50")
