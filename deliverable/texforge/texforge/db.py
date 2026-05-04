from __future__ import annotations

import json
import hashlib
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.artifact_root = self.path.parent / "artifacts"
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.setup()
        self.seed()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def setup(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS templates (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    slug TEXT NOT NULL UNIQUE,
                    category TEXT NOT NULL,
                    description TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    main_tex TEXT NOT NULL,
                    refs_bib TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS organizations (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    template TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    description TEXT NOT NULL,
                    visibility TEXT NOT NULL,
                    org_id TEXT,
                    archived INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS files (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(project_id, path)
                );

                CREATE TABLE IF NOT EXISTS comments (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    file_id TEXT NOT NULL,
                    parent_id TEXT,
                    author TEXT NOT NULL,
                    body TEXT NOT NULL,
                    line_from INTEGER NOT NULL,
                    line_to INTEGER NOT NULL,
                    resolved INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS snapshots (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    file_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS compile_jobs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    engine TEXT NOT NULL,
                    entrypoint TEXT NOT NULL,
                    trigger TEXT NOT NULL,
                    status TEXT NOT NULL,
                    log TEXT NOT NULL,
                    pdf_path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT,
                    actor TEXT NOT NULL,
                    verb TEXT NOT NULL,
                    target TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS notifications (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    level TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS share_links (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    url TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS project_memberships (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(project_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS suggestions (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    file_id TEXT NOT NULL,
                    author TEXT NOT NULL,
                    body TEXT NOT NULL,
                    original_text TEXT NOT NULL,
                    suggested_text TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS references_library (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    identifier TEXT NOT NULL,
                    citation_key TEXT NOT NULL,
                    title TEXT NOT NULL,
                    authors TEXT NOT NULL,
                    year TEXT NOT NULL,
                    raw_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(project_id, source, identifier)
                );

                CREATE TABLE IF NOT EXISTS branches (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    snapshot_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def seed(self) -> None:
        with self._connect() as conn:
            template_count = conn.execute("SELECT COUNT(*) FROM templates").fetchone()[0]
            if template_count == 0:
                templates = [
                    {
                        "id": self._id("tpl"),
                        "name": "IEEE Conference",
                        "slug": "ieee",
                        "category": "Journal",
                        "description": "Two-column conference paper with bibliography and figure scaffold.",
                        "tags": json.dumps(["ieee", "conference", "paper"]),
                        "main_tex": "\\documentclass{article}\n\\begin{document}\n\\title{IEEE Paper}\n\\maketitle\n\\section{Introduction}\nWrite here.\\cite{smith2024}\n\\end{document}\n",
                        "refs_bib": "@article{smith2024,\n  title={Sample Reference},\n  author={Smith, Ada},\n  journal={Journal of Examples},\n  year={2024}\n}\n",
                    },
                    {
                        "id": self._id("tpl"),
                        "name": "ACM Article",
                        "slug": "acm",
                        "category": "Journal",
                        "description": "ACM submission starter with abstract and CCS concepts.",
                        "tags": json.dumps(["acm", "article"]),
                        "main_tex": "\\documentclass{article}\n\\begin{document}\n\\title{ACM Draft}\n\\maketitle\n\\begin{abstract}\nAbstract here.\n\\end{abstract}\n\\section{Method}\n\\end{document}\n",
                        "refs_bib": "@inproceedings{lee2025,\n  title={Collaborative Editing at Scale},\n  author={Lee, Robin},\n  booktitle={ACM Example},\n  year={2025}\n}\n",
                    },
                    {
                        "id": self._id("tpl"),
                        "name": "Research Thesis",
                        "slug": "thesis",
                        "category": "Thesis",
                        "description": "Multi-file thesis layout with chapters and front matter.",
                        "tags": json.dumps(["thesis", "phd"]),
                        "main_tex": "\\documentclass{report}\n\\begin{document}\n\\title{Thesis}\n\\maketitle\n\\chapter{Overview}\n\\input{chapters/ch1.tex}\n\\end{document}\n",
                        "refs_bib": "@book{doe2023,\n  title={Example Thesis Book},\n  author={Doe, Jane},\n  year={2023}\n}\n",
                    },
                    {
                        "id": self._id("tpl"),
                        "name": "Academic Resume",
                        "slug": "resume",
                        "category": "CV",
                        "description": "One-page resume with publications and teaching sections.",
                        "tags": json.dumps(["resume", "cv"]),
                        "main_tex": "\\documentclass{article}\n\\begin{document}\n\\section*{Experience}\n\\section*{Publications}\n\\end{document}\n",
                        "refs_bib": "",
                    },
                ]
                conn.executemany(
                    "INSERT INTO templates (id, name, slug, category, description, tags, main_tex, refs_bib) VALUES (:id, :name, :slug, :category, :description, :tags, :main_tex, :refs_bib)",
                    templates,
                )

            if conn.execute("SELECT COUNT(*) FROM organizations").fetchone()[0] == 0:
                conn.execute(
                    "INSERT INTO organizations (id, name, description, created_at) VALUES (?, ?, ?, ?)",
                    (self._id("org"), "TexForge Research Lab", "Shared workspace for papers, reviews, and journal submissions.", self.now()),
                )

            if conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == 0:
                notifications = [
                    (self._id("note"), "Compile queue healthy", "All worker lanes are available for fast feedback.", "success", self.now()),
                    (self._id("note"), "Review mention", "@alice requested changes on Quantum Notes.", "info", self.now()),
                ]
                conn.executemany(
                    "INSERT INTO notifications (id, title, body, level, created_at) VALUES (?, ?, ?, ?, ?)",
                    notifications,
                )
            conn.commit()

        with self._connect() as conn:
            if conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0:
                org_id = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()["id"]
            else:
                org_id = None
        if org_id:
            project = self.create_project(
                name="Quantum Notes",
                template="ieee",
                owner="alice@example.com",
                description="Shared manuscript for a collaborative quantum systems paper.",
                visibility="private",
                org_id=org_id,
            )
            files = self.list_project_files(project["id"])
            main_tex = next(f for f in files if f["path"] == "main.tex")
            self.create_comment(
                project["id"],
                main_tex["id"],
                "prof@example.com",
                "Live collaboration note: tighten the motivation paragraph.",
                1,
                2,
            )
            self.create_snapshot(project["id"], main_tex["id"], "Initial draft")
            self.record_activity(project["id"], "alice@example.com", "seeded", "Quantum Notes demo project")

    @staticmethod
    def now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _id(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:10]}"

    def list_templates(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM templates ORDER BY name").fetchall()
        return [self._row_to_template(r) for r in rows]

    def search_templates(self, query: str = "") -> list[dict[str, Any]]:
        if not query.strip():
            return self.list_templates()
        like = f"%{query.lower()}%"
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM templates
                WHERE lower(name) LIKE ? OR lower(description) LIKE ? OR lower(tags) LIKE ?
                ORDER BY name""",
                (like, like, like),
            ).fetchall()
        return [self._row_to_template(r) for r in rows]

    def get_template(self, slug: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM templates WHERE slug = ?", (slug,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown template: {slug}")
        return self._row_to_template(row)

    def list_organizations(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM organizations ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    def list_notifications(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM notifications ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def create_user(self, email: str, password: str, name: str, role: str = "user") -> dict[str, Any]:
        user = {
            "id": self._id("usr"),
            "email": email.lower(),
            "name": name,
            "password_hash": self._hash_password(password),
            "role": role,
            "created_at": self.now(),
        }
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO users (id, email, name, password_hash, role, created_at) VALUES (:id, :email, :name, :password_hash, :role, :created_at)",
                user,
            )
        safe_user = self.get_user_by_email(email)
        self.record_activity(None, email.lower(), "registered", "user account")
        return safe_user

    def get_user_by_email(self, email: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT id, email, name, role, created_at FROM users WHERE email = ?", (email.lower(),)).fetchone()
        if row is None:
            raise KeyError(email)
        return dict(row)

    def authenticate_user(self, email: str, password: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
        if row is None or row["password_hash"] != self._hash_password(password):
            return None
        return {
            "id": row["id"],
            "email": row["email"],
            "name": row["name"],
            "role": row["role"],
            "created_at": row["created_at"],
        }

    def create_session(self, user_id: str) -> str:
        session_id = self._id("sess")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (id, user_id, created_at) VALUES (?, ?, ?)",
                (session_id, user_id, self.now()),
            )
        return session_id

    def delete_session(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    def get_user_by_session(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT users.id, users.email, users.name, users.role, users.created_at
                FROM sessions JOIN users ON users.id = sessions.user_id
                WHERE sessions.id = ?""",
                (session_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_projects(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
        return [self._row_to_project(r) for r in rows]

    def get_project(self, project_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise KeyError(project_id)
        return self._row_to_project(row)

    def create_project(
        self,
        name: str,
        template: str,
        owner: str,
        description: str = "",
        visibility: str = "private",
        org_id: str | None = None,
    ) -> dict[str, Any]:
        template_row = self.get_template(template)
        project_id = self._id("prj")
        now = self.now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO projects (id, name, template, owner, description, visibility, org_id, archived, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
                (project_id, name, template, owner, description or template_row["description"], visibility, org_id, now, now),
            )
        self.create_or_update_file(project_id, "main.tex", template_row["main_tex"])
        self.create_or_update_file(project_id, "refs.bib", template_row["refs_bib"])
        if template == "thesis":
            self.create_or_update_file(project_id, "chapters/ch1.tex", "\\chapter{Introduction}\nThesis chapter placeholder.\n")
        self.create_share_link(project_id, "editor")
        try:
            owner_user = self.get_user_by_email(owner)
        except KeyError:
            owner_user = None
        if owner_user:
            self.add_project_member(project_id, owner_user["id"], "owner")
        self.record_activity(project_id, owner, "created", name)
        return self.get_project(project_id)

    def create_share_link(self, project_id: str, role: str, expires_in_days: int = 14) -> dict[str, Any]:
        share_id = self._id("share")
        expires = (datetime.now(UTC) + timedelta(days=expires_in_days)).isoformat()
        url = f"/share/{share_id}"
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO share_links (id, project_id, role, expires_at, url) VALUES (?, ?, ?, ?, ?)",
                (share_id, project_id, role, expires, url),
            )
        return {"id": share_id, "project_id": project_id, "role": role, "expires_at": expires, "url": url}

    def get_share_link(self, share_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM share_links WHERE id = ?", (share_id,)).fetchone()
        if row is None:
            raise KeyError(share_id)
        return dict(row)

    def accept_share_link(self, share_id: str, user_id: str) -> dict[str, Any]:
        share = self.get_share_link(share_id)
        self.add_project_member(share["project_id"], user_id, share["role"])
        user = self.get_user_by_id(user_id)
        self.record_activity(share["project_id"], user["email"], "joined", share["role"])
        return {"project_id": share["project_id"], "user_id": user_id, "role": share["role"], "share_id": share_id}

    def list_share_links(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM share_links WHERE project_id = ? ORDER BY expires_at DESC", (project_id,)).fetchall()
        return [dict(r) for r in rows]

    def add_project_member(self, project_id: str, user_id: str, role: str) -> dict[str, Any]:
        membership = {
            "id": self._id("mbr"),
            "project_id": project_id,
            "user_id": user_id,
            "role": role,
            "created_at": self.now(),
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO project_memberships (id, project_id, user_id, role, created_at)
                VALUES (:id, :project_id, :user_id, :role, :created_at)
                ON CONFLICT(project_id, user_id) DO UPDATE SET role = excluded.role""",
                membership,
            )
        return self.get_project_member(project_id, user_id)

    def get_user_by_id(self, user_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT id, email, name, role, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise KeyError(user_id)
        return dict(row)

    def get_project_member(self, project_id: str, user_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT project_memberships.*, users.email, users.name
                FROM project_memberships JOIN users ON users.id = project_memberships.user_id
                WHERE project_memberships.project_id = ? AND project_memberships.user_id = ?""",
                (project_id, user_id),
            ).fetchone()
        return dict(row) if row else None

    def list_project_members(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT project_memberships.*, users.email, users.name
                FROM project_memberships JOIN users ON users.id = project_memberships.user_id
                WHERE project_memberships.project_id = ?
                ORDER BY CASE project_memberships.role WHEN 'owner' THEN 0 WHEN 'editor' THEN 1 ELSE 2 END, users.email""",
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_or_update_file(self, project_id: str, path: str, content: str) -> dict[str, Any]:
        with self._connect() as conn:
            existing = conn.execute("SELECT id FROM files WHERE project_id = ? AND path = ?", (project_id, path)).fetchone()
            now = self.now()
            if existing:
                conn.execute("UPDATE files SET content = ?, updated_at = ? WHERE id = ?", (content, now, existing["id"]))
                file_id = existing["id"]
            else:
                file_id = self._id("file")
                conn.execute(
                    "INSERT INTO files (id, project_id, path, content, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (file_id, project_id, path, content, now, now),
                )
            conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))
        return self.get_file(file_id)

    def create_file(self, project_id: str, path: str, content: str) -> dict[str, Any]:
        file_record = self.create_or_update_file(project_id, path, content)
        self.record_activity(project_id, "system", "file_added", path)
        return file_record

    def move_file(self, file_id: str, new_path: str) -> dict[str, Any]:
        now = self.now()
        with self._connect() as conn:
            row = conn.execute("SELECT project_id, path FROM files WHERE id = ?", (file_id,)).fetchone()
            if row is None:
                raise KeyError(file_id)
            conn.execute("UPDATE files SET path = ?, updated_at = ? WHERE id = ?", (new_path, now, file_id))
            conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, row["project_id"]))
        self.record_activity(row["project_id"], "system", "file_moved", f"{row['path']} -> {new_path}")
        return self.get_file(file_id)

    def delete_file(self, file_id: str) -> dict[str, Any]:
        file_record = self.get_file(file_id)
        with self._connect() as conn:
            conn.execute("DELETE FROM comments WHERE file_id = ?", (file_id,))
            conn.execute("DELETE FROM snapshots WHERE file_id = ?", (file_id,))
            conn.execute("DELETE FROM suggestions WHERE file_id = ?", (file_id,))
            conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
            conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (self.now(), file_record["project_id"]))
        self.record_activity(file_record["project_id"], "system", "file_deleted", file_record["path"])
        return {"deleted": True, "file_id": file_id, "path": file_record["path"]}

    def list_project_files(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM files WHERE project_id = ? ORDER BY path", (project_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_file(self, file_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        if row is None:
            raise KeyError(file_id)
        return dict(row)

    def update_file(self, file_id: str, content: str) -> dict[str, Any]:
        now = self.now()
        with self._connect() as conn:
            row = conn.execute("SELECT project_id, path FROM files WHERE id = ?", (file_id,)).fetchone()
            if row is None:
                raise KeyError(file_id)
            conn.execute("UPDATE files SET content = ?, updated_at = ? WHERE id = ?", (content, now, file_id))
            conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, row["project_id"]))
        self.record_activity(row["project_id"], "system", "file_updated", row["path"])
        return self.get_file(file_id)

    def clone_project(self, project_id: str) -> dict[str, Any]:
        project = self.get_project(project_id)
        clone = self.create_project(
            name=f"{project['name']} (Clone {datetime.now(UTC).strftime('%H:%M')})",
            template=project["template"],
            owner=project["owner"],
            description=project["description"],
            visibility=project["visibility"],
            org_id=project.get("org_id"),
        )
        for file in self.list_project_files(project_id):
            self.create_or_update_file(clone["id"], file["path"], file["content"])
        self.record_activity(clone["id"], project["owner"], "cloned_from", project["name"])
        return clone

    def archive_project(self, project_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            conn.execute("UPDATE projects SET archived = 1, updated_at = ? WHERE id = ?", (self.now(), project_id))
        self.record_activity(project_id, "system", "archived", project_id)
        return self.get_project(project_id)

    def delete_project(self, project_id: str) -> dict[str, Any]:
        project = self.get_project(project_id)
        with self._connect() as conn:
            conn.execute("DELETE FROM branches WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM compile_jobs WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM comments WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM snapshots WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM share_links WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM project_memberships WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM suggestions WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM references_library WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM activity WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM files WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        artifact_dir = self.artifact_root / project_id
        if artifact_dir.exists():
            for child in artifact_dir.iterdir():
                child.unlink()
            artifact_dir.rmdir()
        return {"deleted": True, "project_id": project_id, "name": project["name"]}

    def create_comment(
        self,
        project_id: str,
        file_id: str,
        author: str,
        body: str,
        line_from: int,
        line_to: int,
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        comment = {
            "id": self._id("cmt"),
            "project_id": project_id,
            "file_id": file_id,
            "parent_id": parent_id,
            "author": author,
            "body": body,
            "line_from": line_from,
            "line_to": line_to,
            "resolved": 0,
            "created_at": self.now(),
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO comments (id, project_id, file_id, parent_id, author, body, line_from, line_to, resolved, created_at)
                VALUES (:id, :project_id, :file_id, :parent_id, :author, :body, :line_from, :line_to, :resolved, :created_at)""",
                comment,
            )
        self.record_activity(project_id, author, "commented", body[:60])
        return comment

    def list_comments(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM comments WHERE project_id = ? ORDER BY created_at DESC", (project_id,)).fetchall()
        return [dict(r) for r in rows]

    def list_comment_threads(self, project_id: str) -> list[dict[str, Any]]:
        comments = self.list_comments(project_id)
        by_parent: dict[str, list[dict[str, Any]]] = {}
        roots: list[dict[str, Any]] = []
        for comment in comments:
            comment["resolved"] = bool(comment["resolved"])
            comment["replies"] = []
            comment["reply_count"] = 0
            parent_id = comment.get("parent_id")
            if parent_id:
                by_parent.setdefault(parent_id, []).append(comment)
            else:
                roots.append(comment)
        for root in roots:
            replies = list(reversed(by_parent.get(root["id"], [])))
            root["replies"] = replies
            root["reply_count"] = len(replies)
        return roots

    def get_comment(self, comment_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM comments WHERE id = ?", (comment_id,)).fetchone()
        if row is None:
            raise KeyError(comment_id)
        comment = dict(row)
        comment["resolved"] = bool(comment["resolved"])
        return comment

    def set_comment_resolved(self, comment_id: str, resolved: bool) -> dict[str, Any]:
        comment = self.get_comment(comment_id)
        with self._connect() as conn:
            conn.execute("UPDATE comments SET resolved = ? WHERE id = ?", (1 if resolved else 0, comment_id))
        verb = "resolved_comment" if resolved else "reopened_comment"
        self.record_activity(comment["project_id"], comment["author"], verb, comment["body"][:60])
        return self.get_comment(comment_id)

    def create_snapshot(self, project_id: str, file_id: str, name: str) -> dict[str, Any]:
        file_record = self.get_file(file_id)
        snapshot = {
            "id": self._id("snap"),
            "project_id": project_id,
            "file_id": file_id,
            "name": name,
            "content": file_record["content"],
            "created_at": self.now(),
        }
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO snapshots (id, project_id, file_id, name, content, created_at) VALUES (:id, :project_id, :file_id, :name, :content, :created_at)",
                snapshot,
            )
        self.record_activity(project_id, "system", "snapshot", name)
        return snapshot

    def restore_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        snapshot = self.get_snapshot(snapshot_id)
        restored = self.update_file(snapshot["file_id"], snapshot["content"])
        self.record_activity(snapshot["project_id"], "system", "restored_snapshot", snapshot["name"])
        return restored

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM snapshots WHERE id = ?", (snapshot_id,)).fetchone()
        if row is None:
            raise KeyError(snapshot_id)
        return dict(row)

    def list_snapshots(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM snapshots WHERE project_id = ? ORDER BY created_at DESC", (project_id,)).fetchall()
        return [dict(r) for r in rows]

    def create_branch(self, project_id: str, snapshot_id: str, name: str) -> dict[str, Any]:
        self.get_project(project_id)
        snapshot = self.get_snapshot(snapshot_id)
        branch = {
            "id": self._id("br"),
            "project_id": project_id,
            "snapshot_id": snapshot["id"],
            "name": name,
            "created_at": self.now(),
        }
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO branches (id, project_id, snapshot_id, name, created_at) VALUES (:id, :project_id, :snapshot_id, :name, :created_at)",
                branch,
            )
        self.record_activity(project_id, "system", "branch_created", name)
        return branch

    def list_branches(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM branches WHERE project_id = ? ORDER BY created_at DESC", (project_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_branch(self, branch_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM branches WHERE id = ?", (branch_id,)).fetchone()
        if row is None:
            raise KeyError(branch_id)
        return dict(row)

    def restore_branch(self, branch_id: str) -> dict[str, Any]:
        branch = self.get_branch(branch_id)
        restored = self.restore_snapshot(branch["snapshot_id"])
        self.record_activity(branch["project_id"], "system", "restored_branch", branch["name"])
        return restored

    def create_compile_job(self, project_id: str, engine: str, entrypoint: str, trigger: str, log: str, pdf_path: str) -> dict[str, Any]:
        job = {
            "id": self._id("job"),
            "project_id": project_id,
            "engine": engine,
            "entrypoint": entrypoint,
            "trigger": trigger,
            "status": "completed",
            "log": log,
            "pdf_path": pdf_path,
            "created_at": self.now(),
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO compile_jobs (id, project_id, engine, entrypoint, trigger, status, log, pdf_path, created_at)
                VALUES (:id, :project_id, :engine, :entrypoint, :trigger, :status, :log, :pdf_path, :created_at)""",
                job,
            )
        self.record_activity(project_id, "worker", "compiled", f"{engine}:{entrypoint}")
        return self.get_compile_job(project_id, job["id"])

    def get_compile_job(self, project_id: str, job_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM compile_jobs WHERE project_id = ? AND id = ?", (project_id, job_id)).fetchone()
        if row is None:
            raise KeyError(job_id)
        job = dict(row)
        job["pdf_url"] = f"/artifacts/{project_id}/{Path(job['pdf_path']).name}"
        return job

    def list_activity(self, project_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if project_id:
                rows = conn.execute("SELECT * FROM activity WHERE project_id = ? ORDER BY created_at DESC LIMIT 20", (project_id,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM activity ORDER BY created_at DESC LIMIT 20").fetchall()
        return [dict(r) for r in rows]

    def record_activity(self, project_id: str | None, actor: str, verb: str, target: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO activity (project_id, actor, verb, target, created_at) VALUES (?, ?, ?, ?, ?)",
                (project_id, actor, verb, target, self.now()),
            )

    def create_suggestion(self, project_id: str, file_id: str, author: str, body: str, original_text: str, suggested_text: str) -> dict[str, Any]:
        suggestion = {
            "id": self._id("sgt"),
            "project_id": project_id,
            "file_id": file_id,
            "author": author,
            "body": body,
            "original_text": original_text,
            "suggested_text": suggested_text,
            "status": "open",
            "created_at": self.now(),
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO suggestions (id, project_id, file_id, author, body, original_text, suggested_text, status, created_at)
                VALUES (:id, :project_id, :file_id, :author, :body, :original_text, :suggested_text, :status, :created_at)""",
                suggestion,
            )
        self.record_activity(project_id, author, "suggested", body[:60])
        return suggestion

    def get_suggestion(self, suggestion_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM suggestions WHERE id = ?", (suggestion_id,)).fetchone()
        if row is None:
            raise KeyError(suggestion_id)
        return dict(row)

    def accept_suggestion(self, suggestion_id: str) -> dict[str, Any]:
        suggestion = self.get_suggestion(suggestion_id)
        file_record = self.get_file(suggestion["file_id"])
        if suggestion["original_text"] and suggestion["original_text"] in file_record["content"]:
            updated_content = file_record["content"].replace(suggestion["original_text"], suggestion["suggested_text"], 1)
        else:
            updated_content = file_record["content"] + "\n" + suggestion["suggested_text"]
        updated_file = self.update_file(file_record["id"], updated_content)
        with self._connect() as conn:
            conn.execute("UPDATE suggestions SET status = 'accepted' WHERE id = ?", (suggestion_id,))
        self.record_activity(suggestion["project_id"], suggestion["author"], "accepted_suggestion", suggestion["body"][:60])
        return {"suggestion": self.get_suggestion(suggestion_id), "file": updated_file}

    def import_reference(self, project_id: str, source: str, identifier: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM references_library WHERE project_id = ? AND source = ? AND identifier = ?",
                (project_id, source, identifier),
            ).fetchone()
        if row:
            result = dict(row)
            result["duplicate"] = True
            return result

        slug = "".join(ch for ch in identifier.lower() if ch.isalnum())[-10:] or "ref"
        title = f"Imported {source.upper()} reference for {identifier}"
        citation_key = f"texforge{slug}"
        ref = {
            "id": self._id("ref"),
            "project_id": project_id,
            "source": source,
            "identifier": identifier,
            "citation_key": citation_key,
            "title": title,
            "authors": "TexForge Research Team",
            "year": str(datetime.now(UTC).year),
            "raw_json": json.dumps({"source": source, "identifier": identifier, "title": title}),
            "created_at": self.now(),
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO references_library
                (id, project_id, source, identifier, citation_key, title, authors, year, raw_json, created_at)
                VALUES (:id, :project_id, :source, :identifier, :citation_key, :title, :authors, :year, :raw_json, :created_at)""",
                ref,
            )
        bibtex_entry = (
            f"@article{{{citation_key},\n"
            f"  title={{{title}}},\n"
            f"  author={{{ref['authors']}}},\n"
            f"  year={{{ref['year']}}},\n"
            f"  note={{{identifier}}}\n"
            f"}}\n"
        )
        refs_file = next((file for file in self.list_project_files(project_id) if file["path"] == "refs.bib"), None)
        if refs_file and citation_key not in refs_file["content"]:
            updated_bib = refs_file["content"].rstrip() + ("\n\n" if refs_file["content"].strip() else "") + bibtex_entry
            self.update_file(refs_file["id"], updated_bib)
        self.record_activity(project_id, "system", "imported_reference", identifier)
        ref["duplicate"] = False
        return ref

    def search_references(self, project_id: str, query: str) -> list[dict[str, Any]]:
        like = f"%{query.lower()}%"
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM references_library
                WHERE project_id = ? AND (
                    lower(citation_key) LIKE ? OR lower(title) LIKE ? OR lower(authors) LIKE ? OR lower(identifier) LIKE ?
                )
                ORDER BY created_at DESC""",
                (project_id, like, like, like, like),
            ).fetchall()
        return [dict(row) for row in rows]

    def admin_metrics(self) -> dict[str, int]:
        with self._connect() as conn:
            users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            projects = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
            memberships = conn.execute("SELECT COUNT(*) FROM project_memberships").fetchone()[0]
            compile_jobs = conn.execute("SELECT COUNT(*) FROM compile_jobs").fetchone()[0]
            references = conn.execute("SELECT COUNT(*) FROM references_library").fetchone()[0]
        return {
            "users": users,
            "projects": projects,
            "memberships": memberships,
            "compile_jobs": compile_jobs,
            "references": references,
        }

    def search(self, query: str) -> list[dict[str, Any]]:
        like = f"%{query.lower()}%"
        results: list[dict[str, Any]] = []
        with self._connect() as conn:
            for row in conn.execute("SELECT id, name, description FROM projects WHERE lower(name) LIKE ? OR lower(description) LIKE ?", (like, like)).fetchall():
                results.append({"kind": "project", "id": row["id"], "label": row["name"], "snippet": row["description"]})
            for row in conn.execute("SELECT id, path, content FROM files WHERE lower(path) LIKE ? OR lower(content) LIKE ?", (like, like)).fetchall():
                results.append({"kind": "file", "id": row["id"], "label": row["path"], "snippet": row["content"][:120]})
            for row in conn.execute("SELECT id, body, author FROM comments WHERE lower(body) LIKE ?", (like,)).fetchall():
                results.append({"kind": "comment", "id": row["id"], "label": row["author"], "snippet": row["body"]})
            for row in conn.execute("SELECT id, name, description FROM templates WHERE lower(name) LIKE ? OR lower(description) LIKE ?", (like, like)).fetchall():
                results.append({"kind": "template", "id": row["id"], "label": row["name"], "snippet": row["description"]})
            for row in conn.execute(
                "SELECT id, citation_key, title FROM references_library WHERE lower(citation_key) LIKE ? OR lower(title) LIKE ? OR lower(identifier) LIKE ?",
                (like, like, like),
            ).fetchall():
                results.append({"kind": "reference", "id": row["id"], "label": row["citation_key"], "snippet": row["title"]})
        return results

    def _row_to_project(self, row: sqlite3.Row) -> dict[str, Any]:
        project = dict(row)
        project["archived"] = bool(project["archived"])
        project["files"] = self.list_project_files(project["id"])
        project["comments"] = self.list_comments(project["id"])
        project["snapshots"] = self.list_snapshots(project["id"])
        project["branches"] = self.list_branches(project["id"])
        project["shares"] = self.list_share_links(project["id"])
        project["members"] = self.list_project_members(project["id"])
        project["references"] = self.search_references(project["id"], "")
        return project

    @staticmethod
    def _row_to_template(row: sqlite3.Row) -> dict[str, Any]:
        template = dict(row)
        template["tags"] = json.loads(template["tags"])
        return template

    @staticmethod
    def _hash_password(password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()
