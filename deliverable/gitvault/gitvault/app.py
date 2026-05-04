from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import os
import secrets
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from markdown import markdown
from starlette.middleware.sessions import SessionMiddleware

from gitvault.database import Database
from gitvault.gitops import GitService


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    salt, digest = stored.split("$", 1)
    candidate = hash_password(password, salt).split("$", 1)[1]
    return hmac.compare_digest(candidate, digest)


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(10)).decode().rstrip("=")


def totp_code(secret: str, counter: int | None = None) -> str:
    normalized = secret.upper()
    padding = "=" * ((8 - len(normalized) % 8) % 8)
    key = base64.b32decode(normalized + padding)
    counter = int(time.time()) // 30 if counter is None else counter
    digest = hmac.new(key, counter.to_bytes(8, "big"), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    chunk = digest[offset : offset + 4]
    code = (int.from_bytes(chunk, "big") & 0x7FFFFFFF) % 1_000_000
    return f"{code:06d}"


def verify_totp(secret: str, code: str) -> bool:
    counter = int(time.time()) // 30
    return any(hmac.compare_digest(totp_code(secret, counter + delta), code.strip()) for delta in (-1, 0, 1))


def hash_api_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def md(value: str) -> str:
    return markdown(value or "", extensions=["fenced_code", "tables"])


def nav_link(label: str, href: str) -> str:
    return f'<a href="{href}">{esc(label)}</a>'


def render_page(title: str, body: str, user: dict[str, Any] | None = None, flash: str = "") -> HTMLResponse:
    user_links = (
        f"<span class='user-pill'>@{esc(user['username'])}</span>"
        f"{nav_link('Notifications', '/notifications')}"
        f"{nav_link('Profile', f'/u/{user['username']}')}"
        f"{nav_link('Security', '/settings/security')}"
        f"{nav_link('New Repo', '/repos/new')}"
        f"{nav_link('New Org', '/orgs/new')}"
        f"{nav_link('Logout', '/logout')}"
        if user
        else f"{nav_link('Register', '/register')}{nav_link('Login', '/login')}"
    )
    flash_html = f"<div class='flash'>{esc(flash)}</div>" if flash else ""
    markup = f"""
    <!doctype html>
    <html lang='en'>
      <head>
        <meta charset='utf-8'>
        <meta name='viewport' content='width=device-width, initial-scale=1'>
        <title>{esc(title)} · GitVault</title>
        <link rel='stylesheet' href='/static/style.css'>
        <script defer src='/static/app.js'></script>
      </head>
      <body>
        <header class='topbar'>
          <div class='brand'><a href='/'>GitVault</a></div>
          <nav class='topnav'>
            {nav_link('Explore', '/explore')}
            {nav_link('Trending', '/trending')}
            {nav_link('Search', '/search')}
            {nav_link('Marketplace', '/marketplace')}
            {nav_link('Sponsors', '/sponsors')}
            {nav_link('Admin', '/admin')}
            {user_links}
          </nav>
        </header>
        <main class='container'>
          {flash_html}
          {body}
        </main>
      </body>
    </html>
    """
    return HTMLResponse(markup)


def create_app(data_dir: Path | None = None, testing: bool = False) -> FastAPI:
    data_root = Path(data_dir or Path.cwd() / ".gitvault_data")
    data_root.mkdir(parents=True, exist_ok=True)
    db = Database(data_root / "gitvault.db")
    git = GitService(data_root / "repos")
    archives = data_root / "archives"
    archives.mkdir(exist_ok=True)

    app = FastAPI(title="GitVault")
    app.add_middleware(SessionMiddleware, secret_key="gitvault-secret-key", same_site="lax")
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
    app.state.db = db
    app.state.git = git
    app.state.data_root = data_root
    app.state.testing = testing

    def current_user(request: Request) -> dict[str, Any] | None:
        user_id = request.session.get("user_id")
        session_token = request.session.get("session_token")
        if session_token:
            session = db.get_user_session(session_token)
            if not session or session.get("revoked_at"):
                request.session.clear()
                return None
            db.touch_user_session(session_token)
        return db.get_user(int(user_id)) if user_id else None

    def begin_session(request: Request, user: dict[str, Any]) -> None:
        session_token = secrets.token_urlsafe(24)
        request.session["user_id"] = user["id"]
        request.session["session_token"] = session_token
        request.session.pop("pending_2fa_user_id", None)
        db.create_user_session(user["id"], session_token, request.headers.get("user-agent", "browser"))

    def current_token_bundle(request: Request) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        authorization = request.headers.get("authorization", "")
        if not authorization.lower().startswith("bearer "):
            return None, None
        raw_token = authorization.split(" ", 1)[1].strip()
        token_record = db.get_api_token_by_hash(hash_api_token(raw_token))
        if not token_record:
            return None, None
        db.touch_api_token(token_record["id"])
        return db.get_user(token_record["user_id"]), token_record

    def token_allows_repo(token_record: dict[str, Any] | None, repo: dict[str, Any], required_scope: str = "repo:read") -> bool:
        if not token_record:
            return False
        scopes = token_record.get("scopes", [])
        if required_scope not in scopes and "repo" not in scopes and "*" not in scopes:
            return False
        repo_scope = (token_record.get("repo_scope") or "").strip()
        return not repo_scope or repo_scope == f"{repo['owner_slug']}/{repo['slug']}"

    def require_user(request: Request) -> dict[str, Any]:
        user = current_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Login required")
        return user

    def can_view_repo(user: dict[str, Any] | None, repo: dict[str, Any]) -> bool:
        if repo["visibility"] == "public":
            return True
        return bool(user and (user["username"] == repo["owner_slug"] or user["is_admin"]))

    def emit_webhook(repo: dict[str, Any], event_name: str, payload: dict[str, Any]) -> None:
        for webhook in db.list_repo_webhooks(repo["id"]):
            events = webhook.get("events", [])
            if "*" in events or event_name in events:
                db.create_webhook_delivery(webhook["id"], event_name, "recorded", payload)

    def repo_path(repo: dict[str, Any]) -> Path:
        return git.repo_path(repo["owner_slug"], repo["slug"])

    def repo_header(repo: dict[str, Any], current_tab: str = "code") -> str:
        base = f"/{repo['owner_slug']}/{repo['slug']}"
        tabs = [
            ("Code", base),
            ("Issues", f"{base}/issues"),
            ("Pull Requests", f"{base}/pulls"),
            ("Discussions", f"{base}/discussions"),
            ("Projects", f"{base}/projects"),
            ("Wiki", f"{base}/wiki"),
            ("Actions", f"{base}/actions"),
            ("Packages", f"{base}/packages"),
            ("Pages", f"{base}/pages"),
            ("Insights", f"{base}/insights"),
            ("Settings", f"{base}/settings"),
        ]
        actions = """
            <div class='subactions'>
              <form method='post' action='{base}/star'><button>★ Star</button></form>
              <form method='post' action='{base}/watch'><button>👁 Watch</button></form>
              <form method='post' action='{base}/fork'><button>⑂ Fork</button></form>
            </div>
        """.replace("{base}", base)
        return f"""
        <section class='hero'>
          <div>
            <h1>{esc(repo['owner_slug'])}/{esc(repo['slug'])}</h1>
            <p>{esc(repo['description'])}</p>
            <div class='meta-badges'>
              <span>{esc(repo['visibility'])}</span>
              <span>{'archived' if repo['archived'] else 'active'}</span>
              <span>{repo['stars_count']} stars</span>
              <span>{repo['watchers_count']} watchers</span>
              <span>{repo['forks_count']} forks</span>
            </div>
            <div class='topics'>{''.join(f"<span class='tag'>{esc(topic)}</span>" for topic in repo.get('topics', []))}</div>
          </div>
          {actions}
        </section>
        <nav class='repo-tabs'>
            {''.join(f"<a class={'active' if tab.lower().startswith(current_tab.lower()) else ''} href='{href}'>{tab}</a>" for tab, href in tabs)}
        </nav>
        """

    def list_to_cards(items: list[str]) -> str:
        if not items:
            return "<p class='muted'>None yet.</p>"
        return "<ul class='list'>" + "".join(f"<li>{item}</li>" for item in items) + "</ul>"

    def record_repo_notification(repo: dict[str, Any], kind: str, message: str, url: str) -> None:
        if repo["owner_type"] == "user":
            owner = db.get_user(repo["owner_id"])
            if owner:
                db.add_notification(owner["id"], kind, message, url)

    def trigger_actions(repo: dict[str, Any], event_name: str) -> None:
        workflows = git.parse_workflows(repo_path(repo))
        if not workflows:
            db.create_action_run(repo["id"], "GitVault Checks", event_name, "completed", f"Workflow: GitVault Checks\nEvent: {event_name}\nStep: baseline repository checks")
            return
        for workflow in workflows:
            logs = [f"Workflow: {workflow['name']}", f"Event: {event_name}"]
            for job in workflow["jobs"]:
                logs.append(f"Job: {job}")
            for step in workflow["steps"]:
                logs.append(f"Step: {step}")
            db.create_action_run(repo["id"], workflow["name"], event_name, "completed", "\n".join(logs))

    def pr_gate_state(repo: dict[str, Any], pr: dict[str, Any], reviews: list[dict[str, Any]] | None = None) -> tuple[list[str], set[str]]:
        reviews = reviews if reviews is not None else db.get_reviews(pr["id"])
        gate_message: list[str] = []
        rule = db.get_branch_rule(repo["id"], pr["target_branch"])
        if git.merge_conflicts(repo_path(repo), pr["source_branch"], pr["target_branch"]):
            gate_message.append("merge conflict detected")
        if rule and rule["require_reviews"] and not any(review["state"] == "APPROVED" for review in reviews):
            gate_message.append("required review missing")
        if rule and rule["required_status_checks"] and not db.list_action_runs(repo["id"]):
            gate_message.append("status checks missing")

        required_codeowners: set[str] = set()
        if rule and rule["codeowners_required"]:
            required_codeowners = {
                owner
                for owner in git.required_codeowners(
                    repo_path(repo),
                    pr["target_branch"],
                    pr["source_branch"],
                    pr["target_branch"],
                )
                if db.get_user_by_username(owner)
            }
            approved_usernames = {
                reviewer["username"]
                for review in reviews
                if review["state"] == "APPROVED"
                for reviewer in [db.get_user(review["author_id"])]
                if reviewer
            }
            if required_codeowners and not (approved_usernames & required_codeowners):
                gate_message.append("CODEOWNERS approval missing")
        return gate_message, required_codeowners

    def complete_merge(repo: dict[str, Any], pr: dict[str, Any], strategy: str) -> None:
        git.merge_pr(repo_path(repo), pr["source_branch"], pr["target_branch"], strategy)
        db.merge_pr(pr["id"], strategy)
        if pr["linked_issue_number"]:
            db.execute(
                "UPDATE issues SET state = 'closed', updated_at = ? WHERE repo_id = ? AND number = ?",
                (db.fetchone("SELECT CURRENT_TIMESTAMP as now")["now"], repo["id"], pr["linked_issue_number"]),
            )
        trigger_actions(repo, "merge_group")
        emit_webhook(
            repo,
            "pull_request",
            {"repository": f"{repo['owner_slug']}/{repo['slug']}", "action": "closed", "merged": True, "number": pr["number"], "strategy": strategy},
        )

    def process_auto_merge_queue(repo: dict[str, Any]) -> None:
        for queued_pr in db.list_auto_merge_prs(repo["id"]):
            gate_message, _ = pr_gate_state(repo, queued_pr)
            if gate_message:
                break
            strategy = queued_pr.get("merge_strategy") or "merge"
            complete_merge(repo, queued_pr, strategy)

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        user = current_user(request)
        repos = db.list_repos("public")[:8]
        cards = "".join(
            f"<article class='card'><h3><a href='/{r['owner_slug']}/{r['slug']}'>{esc(r['owner_slug'])}/{esc(r['slug'])}</a></h3><p>{esc(r['description'])}</p><small>{esc(r['visibility'])} · {r['stars_count']}★</small></article>"
            for r in repos
        ) or "<p>No repositories yet.</p>"
        body = f"""
        <section class='hero hero-home'>
          <div>
            <h1>GitVault</h1>
            <p>A GitHub-inspired code collaboration platform with real Git repositories, issues, pull requests, Actions, packages, pages, orgs, search, admin, and more.</p>
            <div class='cta-row'>
              <a class='button primary' href='/repos/new'>Create repository</a>
              <a class='button' href='/explore'>Explore projects</a>
            </div>
          </div>
          <div class='panel'>
            <h3>Platform coverage</h3>
            <ul>
              <li>Repositories, branches, tags, releases, file history, blame, compare, ZIP export</li>
              <li>Issues, pull requests, reviews, CODEOWNERS checks, protected branches</li>
              <li>Discussions, projects, wiki, notifications, marketplace, sponsors</li>
              <li>Actions workflow parsing, pages hosting preview, packages, search, admin</li>
            </ul>
          </div>
        </section>
        <section>
          <h2>Trending repositories</h2>
          <div class='grid'>{cards}</div>
        </section>
        """
        return render_page("Home", body, user)

    @app.get("/register", response_class=HTMLResponse)
    def register_form(request: Request) -> HTMLResponse:
        body = """
        <h1>Create account</h1>
        <form method='post' class='stack'>
          <label>Email<input type='email' name='email' required></label>
          <label>Username<input type='text' name='username' required></label>
          <label>Password<input type='password' name='password' required></label>
          <button class='button primary'>Register</button>
        </form>
        """
        return render_page("Register", body, current_user(request))

    @app.post("/register")
    def register(request: Request, email: str = Form(...), username: str = Form(...), password: str = Form(...)):
        if db.get_user_by_email(email) or db.get_user_by_username(username):
            return render_page("Register", "<p>Account already exists.</p>", None)
        db.create_user(email, username, hash_password(password))
        return RedirectResponse("/login", status_code=303)

    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request) -> HTMLResponse:
        body = """
        <h1>Sign in</h1>
        <form method='post' class='stack'>
          <label>Email<input type='email' name='email' required></label>
          <label>Password<input type='password' name='password' required></label>
          <button class='button primary'>Login</button>
        </form>
        """
        return render_page("Login", body, current_user(request))

    @app.post("/login")
    def login(request: Request, email: str = Form(...), password: str = Form(...)):
        user = db.get_user_by_email(email)
        if not user or not verify_password(password, user["password_hash"]):
            return render_page("Login", "<p>Invalid credentials.</p>", None)
        security = db.get_user_security(user["id"])
        if security.get("two_factor_enabled"):
            request.session.clear()
            request.session["pending_2fa_user_id"] = user["id"]
            return RedirectResponse("/login/2fa", status_code=303)
        begin_session(request, user)
        return RedirectResponse("/", status_code=303)

    @app.get("/login/2fa", response_class=HTMLResponse)
    def login_2fa_form(request: Request) -> HTMLResponse:
        pending_id = request.session.get("pending_2fa_user_id")
        if not pending_id:
            return RedirectResponse("/login", status_code=303)
        body = """
        <h1>Two-factor authentication</h1>
        <form method='post' class='stack'>
          <label>Authentication code<input name='code' inputmode='numeric' autocomplete='one-time-code' required></label>
          <button class='button primary'>Verify code</button>
        </form>
        """
        return render_page("Two-factor", body, None)

    @app.post("/login/2fa")
    def login_2fa_verify(request: Request, code: str = Form(...)):
        pending_id = request.session.get("pending_2fa_user_id")
        if not pending_id:
            raise HTTPException(status_code=400, detail="No pending two-factor login")
        user = db.get_user(int(pending_id))
        security = db.get_user_security(user["id"])
        if not security.get("totp_secret") or not verify_totp(security["totp_secret"], code):
            return render_page("Two-factor", "<p>Invalid authentication code.</p>", None)
        begin_session(request, user)
        return RedirectResponse("/", status_code=303)

    @app.get("/logout")
    def logout(request: Request):
        session_token = request.session.get("session_token")
        if session_token:
            db.revoke_user_session(session_token)
        request.session.clear()
        return RedirectResponse("/", status_code=303)

    def render_security_settings(user: dict[str, Any], request: Request, flash: str = "") -> HTMLResponse:
        security = db.get_user_security(user["id"])
        sessions = db.list_user_sessions(user["id"])
        tokens = db.list_api_tokens(user["id"])
        ssh_keys = db.list_user_keys(user["id"], "ssh")
        gpg_keys = db.list_user_keys(user["id"], "gpg")
        current_session = request.session.get("session_token", "")
        secret_block = (
            f"<p><strong>TOTP secret:</strong> <code>{esc(security['totp_secret'])}</code></p>"
            if security.get("totp_secret")
            else "<p class='muted'>Two-factor is not enabled yet.</p>"
        )
        body = f"""
        <h1>Security settings</h1>
        <section class='grid two-up'>
          <article class='card'>
            <h2>Two-factor authentication</h2>
            <p>Status: {'enabled' if security.get('two_factor_enabled') else 'disabled'}</p>
            {secret_block}
            <form method='post' action='/settings/security/totp/enable'>
              <button class='button primary'>Enable TOTP</button>
            </form>
          </article>
          <article class='card'>
            <h2>Personal access tokens</h2>
            <form method='post' action='/settings/tokens' class='stack'>
              <label>Name<input name='name' required></label>
              <label>Scopes<input name='scopes' value='repo:read' placeholder='repo:read,repo:write'></label>
              <label>Fine-grained repo scope<input name='repo_scope' placeholder='owner/repo'></label>
              <button class='button'>Create token</button>
            </form>
            {list_to_cards([f"{esc(token['name'])} · {esc(token['token_prefix'])} · scopes={', '.join(token.get('scopes', [])) or 'none'}" for token in tokens])}
          </article>
          <article class='card'>
            <h2>SSH keys</h2>
            <form method='post' action='/settings/keys' class='stack'>
              <input type='hidden' name='key_type' value='ssh'>
              <label>Title<input name='title' required></label>
              <label>Public key<textarea name='public_key' rows='4' required></textarea></label>
              <button class='button'>Add SSH key</button>
            </form>
            {list_to_cards([f"{esc(item['title'])} · <code>{esc(item['public_key'][:48])}...</code>" for item in ssh_keys])}
          </article>
          <article class='card'>
            <h2>GPG keys</h2>
            <form method='post' action='/settings/keys' class='stack'>
              <input type='hidden' name='key_type' value='gpg'>
              <label>Title<input name='title' required></label>
              <label>Public key<textarea name='public_key' rows='4' required></textarea></label>
              <button class='button'>Add GPG key</button>
            </form>
            {list_to_cards([f"{esc(item['title'])} · <code>{esc(item['public_key'][:48])}...</code>" for item in gpg_keys])}
          </article>
        </section>
        <section class='panel'>
          <h2>Active sessions</h2>
          {list_to_cards([f"{'current session' if session['session_token'] == current_session else 'browser session'} · {esc(session['created_at'])} · last seen {esc(session['last_seen_at'])}<form method='post' action='/settings/sessions/{quote(session['session_token'])}/revoke'><button class='button'>Revoke</button></form>" for session in sessions])}
        </section>
        """
        return render_page("Security", body, user, flash)

    @app.get("/settings/security", response_class=HTMLResponse)
    def security_settings_page(request: Request) -> HTMLResponse:
        user = require_user(request)
        return render_security_settings(user, request)

    @app.post("/settings/security/totp/enable")
    def enable_totp_route(request: Request):
        user = require_user(request)
        secret = generate_totp_secret()
        db.enable_totp(user["id"], secret)
        return render_security_settings(user, request, flash=f"TOTP enabled. Save this secret: {secret}")

    @app.post("/settings/tokens")
    def create_token_route(
        request: Request,
        name: str = Form(...),
        scopes: str = Form("repo:read"),
        repo_scope: str = Form(""),
    ) -> JSONResponse:
        user = require_user(request)
        raw_token = f"gv_{secrets.token_urlsafe(24)}"
        scope_list = [item.strip() for item in scopes.split(",") if item.strip()]
        db.create_api_token(user["id"], name, raw_token[:12], hash_api_token(raw_token), scope_list, repo_scope.strip())
        return JSONResponse({"token": raw_token, "name": name, "scopes": scope_list, "repo_scope": repo_scope.strip()})

    @app.post("/settings/keys")
    def create_key_route(request: Request, key_type: str = Form(...), title: str = Form(...), public_key: str = Form(...)):
        user = require_user(request)
        db.create_user_key(user["id"], key_type, title, public_key)
        return RedirectResponse("/settings/security", status_code=303)

    @app.post("/settings/sessions/{session_token}/revoke")
    def revoke_session_route(request: Request, session_token: str):
        user = require_user(request)
        session = db.get_user_session(session_token)
        if not session or session["user_id"] != user["id"]:
            raise HTTPException(status_code=404)
        db.revoke_user_session(session_token)
        if request.session.get("session_token") == session_token:
            request.session.clear()
            return RedirectResponse("/login", status_code=303)
        return RedirectResponse("/settings/security", status_code=303)

    @app.get("/repos/new", response_class=HTMLResponse)
    def new_repo_form(request: Request) -> HTMLResponse:
        user = require_user(request)
        orgs = db.list_orgs_for_user(user["id"])
        options = "".join(f"<option value='{esc(o['slug'])}'>{esc(o['slug'])} (org)</option>" for o in orgs)
        body = f"""
        <h1>Create repository</h1>
        <form method='post' class='stack'>
          <label>Name<input type='text' name='name' required></label>
          <label>Description<textarea name='description'></textarea></label>
          <label>Visibility<select name='visibility'><option value='public'>Public</option><option value='private'>Private</option></select></label>
          <label>Owner<select name='owner_slug'><option value='{esc(user['username'])}'>{esc(user['username'])} (you)</option>{options}</select></label>
          <label>README template<select name='readme_template'><option value='default'>Default</option><option value='python'>Python</option></select></label>
          <label>License<select name='license_template'><option value=''>None</option><option value='mit'>MIT</option><option value='apache-2.0'>Apache-2.0</option></select></label>
          <label>.gitignore<select name='gitignore_template'><option value='default'>Default</option><option value='python'>Python</option><option value='node'>Node</option></select></label>
          <label>Topics<input type='text' name='topics' placeholder='python, fastapi'></label>
          <button class='button primary'>Create repository</button>
        </form>
        """
        return render_page("New repo", body, user)

    @app.post("/repos/new")
    def create_repo(
        request: Request,
        name: str = Form(...),
        description: str = Form(""),
        visibility: str = Form("public"),
        owner_slug: str = Form(""),
        readme_template: str = Form("default"),
        license_template: str = Form(""),
        gitignore_template: str = Form("default"),
        topics: str = Form(""),
    ):
        user = require_user(request)
        owner_slug = owner_slug or user["username"]
        org = db.get_org(owner_slug)
        owner_type = "org" if org else "user"
        owner_id = org["id"] if org else user["id"]
        topics_list = [item.strip() for item in topics.split(",") if item.strip()]
        repo_id = db.create_repo(owner_slug, owner_type, owner_id, name, description, visibility, topics_list)
        git.init_repo(owner_slug, name, description, readme_template, license_template, gitignore_template)
        repo = db.get_repo_by_id(repo_id)
        db.record_traffic(repo_id, "repo_created")
        return RedirectResponse(f"/{repo['owner_slug']}/{repo['slug']}", status_code=303)

    @app.post("/{owner_slug}/{repo_slug}/star")
    def star_repo(request: Request, owner_slug: str, repo_slug: str):
        user = require_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        db.execute("INSERT OR IGNORE INTO stars (user_id, repo_id) VALUES (?, ?)", (user["id"], repo["id"]))
        db.execute("UPDATE repositories SET stars_count = (SELECT COUNT(*) FROM stars WHERE repo_id = ?) WHERE id = ?", (repo["id"], repo["id"]))
        return RedirectResponse(f"/{owner_slug}/{repo_slug}", status_code=303)

    @app.post("/{owner_slug}/{repo_slug}/watch")
    def watch_repo(request: Request, owner_slug: str, repo_slug: str):
        user = require_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        db.execute("INSERT OR IGNORE INTO watches (user_id, repo_id) VALUES (?, ?)", (user["id"], repo["id"]))
        db.execute("UPDATE repositories SET watchers_count = (SELECT COUNT(*) FROM watches WHERE repo_id = ?) WHERE id = ?", (repo["id"], repo["id"]))
        return RedirectResponse(f"/{owner_slug}/{repo_slug}", status_code=303)

    @app.post("/{owner_slug}/{repo_slug}/fork")
    def fork_repo(request: Request, owner_slug: str, repo_slug: str):
        user = require_user(request)
        source_repo = db.get_repo(owner_slug, repo_slug)
        fork_name = repo_slug if user["username"] != owner_slug else f"{repo_slug}-fork"
        fork_id = db.create_repo(user["username"], "user", user["id"], fork_name, f"Fork of {owner_slug}/{repo_slug}", source_repo["visibility"], source_repo.get("topics", []))
        git.fork_repo(repo_path(source_repo), git.repo_path(user["username"], fork_name))
        db.execute("UPDATE repositories SET forks_count = forks_count + 1 WHERE id = ?", (source_repo["id"],))
        return RedirectResponse(f"/{user['username']}/{fork_name}", status_code=303)

    @app.get("/explore", response_class=HTMLResponse)
    def explore(request: Request) -> HTMLResponse:
        user = current_user(request)
        repos = db.list_repos()
        cards = "".join(
            f"<article class='card'><h3><a href='/{r['owner_slug']}/{r['slug']}'>{esc(r['owner_slug'])}/{esc(r['slug'])}</a></h3><p>{esc(r['description'])}</p><small>{r['visibility']} · updated {esc(r['updated_at'])}</small></article>"
            for r in repos
        ) or "<p>No repositories found.</p>"
        return render_page("Explore", f"<h1>Explore repositories</h1><div class='grid'>{cards}</div>", user)

    @app.get("/trending", response_class=HTMLResponse)
    def trending(request: Request) -> HTMLResponse:
        user = current_user(request)
        repos = sorted(db.list_repos("public"), key=lambda item: (item["stars_count"], item["watchers_count"]), reverse=True)
        cards = "".join(
            f"<article class='card'><h3><a href='/{r['owner_slug']}/{r['slug']}'>{esc(r['owner_slug'])}/{esc(r['slug'])}</a></h3><p>{esc(r['description'])}</p><small>{r['stars_count']} stars · {r['watchers_count']} watchers</small></article>"
            for r in repos
        ) or "<p>No public repositories yet.</p>"
        return render_page("Trending", f"<h1>Trending</h1><div class='grid'>{cards}</div>", user)

    @app.get("/u/{username}", response_class=HTMLResponse)
    def profile(request: Request, username: str) -> HTMLResponse:
        user = current_user(request)
        profile_user = db.get_user_by_username(username)
        if not profile_user:
            raise HTTPException(404)
        repos = db.list_owner_repos(username)
        body = f"""
        <section class='hero'>
          <div>
            <h1>@{esc(username)}</h1>
            <p>{esc(profile_user['bio']) or 'Open source builder on GitVault.'}</p>
            <div class='meta-badges'>
              <span>{esc(profile_user['location']) or 'Unknown location'}</span>
              <span>{len(repos)} repos</span>
              <span>{', '.join(profile_user.get('achievements', []))}</span>
            </div>
          </div>
        </section>
        <section>
          <h2>Pinned repositories</h2>
          <div class='grid'>{''.join(f"<article class='card'><h3><a href='/{r['owner_slug']}/{r['slug']}'>{esc(r['slug'])}</a></h3><p>{esc(r['description'])}</p></article>" for r in repos[:6])}</div>
        </section>
        """
        return render_page(f"@{username}", body, user)

    @app.get("/orgs/new", response_class=HTMLResponse)
    def org_form(request: Request) -> HTMLResponse:
        user = require_user(request)
        body = """
        <h1>Create organization</h1>
        <form method='post' class='stack'>
          <label>Name<input name='name' required></label>
          <label>Slug<input name='slug' required></label>
          <label>Description<textarea name='description'></textarea></label>
          <button class='button primary'>Create organization</button>
        </form>
        """
        return render_page("New organization", body, user)

    @app.post("/orgs/new")
    def create_org(request: Request, name: str = Form(...), slug: str = Form(...), description: str = Form("")):
        user = require_user(request)
        db.create_org(user["id"], name, slug, description)
        return RedirectResponse(f"/orgs/{slug}", status_code=303)

    @app.get("/orgs/{slug}", response_class=HTMLResponse)
    def org_page(request: Request, slug: str) -> HTMLResponse:
        user = current_user(request)
        org = db.get_org(slug)
        if not org:
            raise HTTPException(404)
        repos = db.list_owner_repos(slug)
        teams = db.fetchall("SELECT * FROM teams WHERE org_id = ?", (org["id"],))
        body = f"""
        <section class='hero'>
          <div>
            <h1>{esc(org['name'])}</h1>
            <p>{esc(org['description'])}</p>
            <div class='meta-badges'><span>{len(repos)} repos</span><span>{len(teams)} teams</span><span>Billing: Team</span></div>
          </div>
        </section>
        <section class='split'>
          <div>
            <h2>Repositories</h2>
            <div class='grid'>{''.join(f"<article class='card'><a href='/{r['owner_slug']}/{r['slug']}'>{esc(r['slug'])}</a><p>{esc(r['description'])}</p></article>" for r in repos) or '<p>No repos yet.</p>'}</div>
          </div>
          <div>
            <h2>Teams</h2>
            {list_to_cards([f"{team['name']} · {team['permission']}" for team in teams])}
          </div>
        </section>
        """
        return render_page(org["name"], body, user)

    @app.get("/{owner_slug}/{repo_slug}", response_class=HTMLResponse)
    def repo_home(request: Request, owner_slug: str, repo_slug: str) -> HTMLResponse:
        user = current_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        if not repo or not can_view_repo(user, repo):
            raise HTTPException(404)
        db.record_traffic(repo["id"], "view")
        path = repo_path(repo)
        entries = git.get_tree(path, repo["default_branch"]) if path.exists() else []
        readme = ""
        try:
            readme = git.get_file(path, repo["default_branch"], "README.md")
        except Exception:
            readme = ""
        history = git.commit_history(path, limit=10)
        body = repo_header(repo, "code") + f"""
        <section class='toolbar'>
          <div class='breadcrumbs'>Default branch: <strong>{esc(repo['default_branch'])}</strong></div>
          <div class='toolbar-actions'>
            <a class='button' href='/{owner_slug}/{repo_slug}/branches'>Branches</a>
            <a class='button' href='/{owner_slug}/{repo_slug}/tags'>Tags</a>
            <a class='button' href='/{owner_slug}/{repo_slug}/download.zip'>Download ZIP</a>
            <a class='button' href='/{owner_slug}/{repo_slug}/compare?base=main&head=main'>Compare</a>
          </div>
        </section>
        <section class='split'>
          <div>
            <h2>Files</h2>
            <ul class='list'>
              {''.join(f"<li><span>{e['kind']}</span> <a href='/{owner_slug}/{repo_slug}/{'tree' if e['kind']=='tree' else 'blob'}/{repo['default_branch']}/{quote(e['name'])}'>{esc(e['name'])}</a></li>" for e in entries)}
            </ul>
          </div>
          <div>
            <h2>Recent commits</h2>
            <ul class='list'>
              {''.join(f"<li><strong>{esc(item['subject'])}</strong><br><small>{esc(item['author'])} · {esc(item['date'])}</small></li>" for item in history)}
            </ul>
          </div>
        </section>
        <section class='panel'>
          <h2>README</h2>
          <div class='markdown-body'>{md(readme)}</div>
        </section>
        """
        return render_page(f"{owner_slug}/{repo_slug}", body, user)

    @app.get("/{owner_slug}/{repo_slug}/tree/{ref}/{tree_path:path}", response_class=HTMLResponse)
    def tree_view(request: Request, owner_slug: str, repo_slug: str, ref: str, tree_path: str) -> HTMLResponse:
        user = current_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        if not repo or not can_view_repo(user, repo):
            raise HTTPException(404)
        entries = git.get_tree(repo_path(repo), ref, tree_path)
        body = repo_header(repo, "code") + f"<h2>Tree: {esc(tree_path)}</h2><ul class='list'>{''.join(f"<li>{e['kind']} <a href='/{owner_slug}/{repo_slug}/{'tree' if e['kind']=='tree' else 'blob'}/{ref}/{quote((Path(tree_path) / e['name']).as_posix())}'>{esc(e['name'])}</a></li>" for e in entries)}</ul>"
        return render_page(f"{repo_slug} tree", body, user)

    @app.get("/{owner_slug}/{repo_slug}/blob/{ref}/{file_path:path}", response_class=HTMLResponse)
    def blob_view(request: Request, owner_slug: str, repo_slug: str, ref: str, file_path: str) -> HTMLResponse:
        user = current_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        if not repo or not can_view_repo(user, repo):
            raise HTTPException(404)
        content = git.get_file(repo_path(repo), ref, file_path)
        is_markdown = file_path.endswith(".md")
        preview = md(content) if is_markdown else f"<pre>{esc(content)}</pre>"
        body = repo_header(repo, "code") + f"""
        <section class='toolbar'>
          <div class='breadcrumbs'>{esc(file_path)} @ {esc(ref)}</div>
          <div class='toolbar-actions'>
            <a class='button' href='/{owner_slug}/{repo_slug}/raw/{ref}/{quote(file_path)}'>Raw</a>
            <a class='button' href='/{owner_slug}/{repo_slug}/history/{ref}/{quote(file_path)}'>History</a>
            <a class='button' href='/{owner_slug}/{repo_slug}/blame/{ref}/{quote(file_path)}'>Blame</a>
            <a class='button' href='/{owner_slug}/{repo_slug}/edit/{ref}/{quote(file_path)}'>Edit</a>
          </div>
        </section>
        <div class='panel markdown-body'>{preview}</div>
        """
        return render_page(file_path, body, user)

    @app.get("/{owner_slug}/{repo_slug}/raw/{ref}/{file_path:path}")
    def raw_view(request: Request, owner_slug: str, repo_slug: str, ref: str, file_path: str):
        user = current_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        if not repo or not can_view_repo(user, repo):
            raise HTTPException(404)
        return PlainTextResponse(git.get_file(repo_path(repo), ref, file_path))

    @app.get("/{owner_slug}/{repo_slug}/history/{ref}/{file_path:path}", response_class=HTMLResponse)
    def file_history(request: Request, owner_slug: str, repo_slug: str, ref: str, file_path: str) -> HTMLResponse:
        user = current_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        history = git.history_for_path(repo_path(repo), ref, file_path)
        body = repo_header(repo, "code") + f"<h2>History for {esc(file_path)}</h2><ul class='list'>{''.join(f"<li><strong>{esc(item['subject'])}</strong><br><small>{esc(item['author'])} · {esc(item['date'])}</small></li>" for item in history)}</ul>"
        return render_page(f"History · {file_path}", body, user)

    @app.get("/{owner_slug}/{repo_slug}/blame/{ref}/{file_path:path}", response_class=HTMLResponse)
    def blame_view(request: Request, owner_slug: str, repo_slug: str, ref: str, file_path: str) -> HTMLResponse:
        user = current_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        blame_lines = git.blame(repo_path(repo), ref, file_path)
        body = repo_header(repo, "code") + f"<h2>Blame · {esc(file_path)}</h2><pre>{esc(chr(10).join(blame_lines))}</pre>"
        return render_page(f"Blame · {file_path}", body, user)

    @app.get("/{owner_slug}/{repo_slug}/edit/{ref}/{file_path:path}", response_class=HTMLResponse)
    def edit_form(request: Request, owner_slug: str, repo_slug: str, ref: str, file_path: str) -> HTMLResponse:
        user = require_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        try:
            content = git.get_file(repo_path(repo), ref, file_path)
        except Exception:
            content = ""
        body = repo_header(repo, "code") + f"""
        <h2>Edit {esc(file_path)} on {esc(ref)}</h2>
        <form method='post' class='stack'>
          <label>Content<textarea name='content' rows='20'>{esc(content)}</textarea></label>
          <label>Commit message<input name='message' value='Update {esc(file_path)}'></label>
          <button class='button primary'>Commit changes</button>
        </form>
        <div class='panel'><strong>Copilot equivalent:</strong> Inline AI suggestions endpoint available at <code>/api/ai/suggest</code>.</div>
        """
        return render_page(f"Edit {file_path}", body, user)

    @app.post("/{owner_slug}/{repo_slug}/edit/{ref}/{file_path:path}")
    def edit_file(
        request: Request,
        owner_slug: str,
        repo_slug: str,
        ref: str,
        file_path: str,
        content: str = Form(...),
        message: str = Form(...),
    ):
        user = require_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        git.commit_file(repo_path(repo), ref, file_path, content, message, user["username"], user["email"])
        db.record_traffic(repo["id"], "commit")
        trigger_actions(repo, "push")
        db.add_notification(user["id"], "commit", f"Committed to {owner_slug}/{repo_slug}: {message}", f"/{owner_slug}/{repo_slug}/blob/{ref}/{file_path}")
        emit_webhook(
            repo,
            "push",
            {"repository": f"{owner_slug}/{repo_slug}", "ref": ref, "file_path": file_path, "message": message},
        )
        return RedirectResponse(f"/{owner_slug}/{repo_slug}/blob/{ref}/{file_path}", status_code=303)

    @app.get("/{owner_slug}/{repo_slug}/download.zip")
    def download_zip(request: Request, owner_slug: str, repo_slug: str):
        user = current_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        if not repo or not can_view_repo(user, repo):
            raise HTTPException(404)
        archive = git.archive_zip(repo_path(repo), archives / f"{owner_slug}-{repo_slug}.zip")
        return FileResponse(archive, filename=f"{repo_slug}.zip")

    @app.get("/{owner_slug}/{repo_slug}/branches", response_class=HTMLResponse)
    def branches_page(request: Request, owner_slug: str, repo_slug: str) -> HTMLResponse:
        user = current_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        branches = git.list_branches(repo_path(repo))
        rules = db.list_branch_rules(repo["id"])
        body = repo_header(repo, "code") + f"""
        <section class='split'>
          <div>
            <h2>Branches</h2>
            {list_to_cards([f"{esc(branch)}" for branch in branches])}
          </div>
          <div>
            <h2>Create branch</h2>
            <form method='post' action='/{owner_slug}/{repo_slug}/branches/create' class='stack'>
              <label>Branch name<input name='branch_name' required></label>
              <label>From ref<input name='from_ref' value='main'></label>
              <button class='button primary'>Create branch</button>
            </form>
            <h3>Protection rules</h3>
            {list_to_cards([f"{rule['branch_name']} · reviews={rule['require_reviews']} · codeowners={rule['codeowners_required']} · checks={rule['required_status_checks']}" for rule in rules])}
          </div>
        </section>
        """
        return render_page("Branches", body, user)

    @app.post("/{owner_slug}/{repo_slug}/branches/create")
    def branch_create(request: Request, owner_slug: str, repo_slug: str, branch_name: str = Form(...), from_ref: str = Form("main")):
        require_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        git.create_branch(repo_path(repo), branch_name, from_ref)
        return RedirectResponse(f"/{owner_slug}/{repo_slug}/branches", status_code=303)

    @app.get("/{owner_slug}/{repo_slug}/tags", response_class=HTMLResponse)
    def tags_page(request: Request, owner_slug: str, repo_slug: str) -> HTMLResponse:
        user = current_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        tags = git.list_tags(repo_path(repo))
        releases = db.list_releases(repo["id"])
        body = repo_header(repo, "code") + f"""
        <section class='split'>
          <div>
            <h2>Tags</h2>
            {list_to_cards(tags)}
            <form method='post' action='/{owner_slug}/{repo_slug}/tags/create' class='stack'>
              <label>Tag name<input name='tag_name' required></label>
              <label>Message<input name='message' value='Release'></label>
              <button class='button primary'>Create tag</button>
            </form>
          </div>
          <div>
            <h2>Releases</h2>
            {list_to_cards([f"{rel['tag_name']} · {rel['title']}" for rel in releases])}
            <form method='post' action='/{owner_slug}/{repo_slug}/releases/new' class='stack'>
              <label>Tag<input name='tag_name' required></label>
              <label>Title<input name='title' required></label>
              <label>Notes<textarea name='notes'></textarea></label>
              <button class='button'>Publish release</button>
            </form>
          </div>
        </section>
        """
        return render_page("Tags & Releases", body, user)

    @app.post("/{owner_slug}/{repo_slug}/tags/create")
    def create_tag(request: Request, owner_slug: str, repo_slug: str, tag_name: str = Form(...), message: str = Form("Release")):
        require_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        git.create_tag(repo_path(repo), tag_name, message)
        return RedirectResponse(f"/{owner_slug}/{repo_slug}/tags", status_code=303)

    @app.post("/{owner_slug}/{repo_slug}/releases/new")
    def create_release(request: Request, owner_slug: str, repo_slug: str, tag_name: str = Form(...), title: str = Form(...), notes: str = Form("")):
        require_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        if tag_name not in git.list_tags(repo_path(repo)):
            git.create_tag(repo_path(repo), tag_name, title)
        db.create_release(repo["id"], tag_name, title, notes, False)
        emit_webhook(repo, "release", {"repository": f"{owner_slug}/{repo_slug}", "tag_name": tag_name, "title": title})
        return RedirectResponse(f"/{owner_slug}/{repo_slug}/tags", status_code=303)

    @app.get("/{owner_slug}/{repo_slug}/compare", response_class=HTMLResponse)
    def compare_page(request: Request, owner_slug: str, repo_slug: str, base: str = "main", head: str = "main") -> HTMLResponse:
        user = current_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        diff = git.compare(repo_path(repo), base, head) if base != head else "No diff yet."
        body = repo_header(repo, "code") + f"""
        <h2>Compare branches / tags / commits</h2>
        <form class='inline-form' method='get'>
          <input name='base' value='{esc(base)}'>
          <input name='head' value='{esc(head)}'>
          <button>Compare</button>
        </form>
        <pre>{esc(diff)}</pre>
        """
        return render_page("Compare", body, user)

    @app.get("/{owner_slug}/{repo_slug}/issues", response_class=HTMLResponse)
    def issues_page(request: Request, owner_slug: str, repo_slug: str) -> HTMLResponse:
        user = current_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        issues = db.list_issues(repo["id"])
        body = repo_header(repo, "issues") + f"""
        <section class='toolbar'><a class='button primary' href='/{owner_slug}/{repo_slug}/issues/new'>New issue</a></section>
        <ul class='list'>
          {''.join(f"<li><a href='/{owner_slug}/{repo_slug}/issues/{issue['number']}'>#{issue['number']} {esc(issue['title'])}</a><br><small>{esc(issue['state'])} · labels: {', '.join(issue.get('labels', []))}</small></li>" for issue in issues)}
        </ul>
        """
        return render_page("Issues", body, user)

    @app.get("/{owner_slug}/{repo_slug}/issues/new", response_class=HTMLResponse)
    def issue_form(request: Request, owner_slug: str, repo_slug: str) -> HTMLResponse:
        user = require_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        body = repo_header(repo, "issues") + """
        <h2>Open issue</h2>
        <form method='post' class='stack'>
          <label>Title<input name='title' required></label>
          <label>Body<textarea name='body'></textarea></label>
          <label>Labels<input name='labels' placeholder='bug,help wanted'></label>
          <button class='button primary'>Create issue</button>
        </form>
        """
        return render_page("New issue", body, user)

    @app.post("/{owner_slug}/{repo_slug}/issues/new")
    def issue_create(request: Request, owner_slug: str, repo_slug: str, title: str = Form(...), body: str = Form(""), labels: str = Form("")):
        user = require_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        issue_id = db.create_issue(repo["id"], user["id"], title, body, [item.strip() for item in labels.split(",") if item.strip()])
        issue = db.fetchone("SELECT * FROM issues WHERE id = ?", (issue_id,))
        record_repo_notification(repo, "issue", f"New issue in {owner_slug}/{repo_slug}: {title}", f"/{owner_slug}/{repo_slug}/issues/{issue['number']}")
        emit_webhook(
            repo,
            "issues",
            {"repository": f"{owner_slug}/{repo_slug}", "action": "opened", "number": issue["number"], "title": title},
        )
        return RedirectResponse(f"/{owner_slug}/{repo_slug}/issues/{issue['number']}", status_code=303)

    @app.get("/{owner_slug}/{repo_slug}/issues/{number}", response_class=HTMLResponse)
    def issue_detail(request: Request, owner_slug: str, repo_slug: str, number: int) -> HTMLResponse:
        user = current_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        issue = db.get_issue(repo["id"], number)
        body = repo_header(repo, "issues") + f"""
        <article class='panel'>
          <h2>#{issue['number']} {esc(issue['title'])}</h2>
          <p><strong>State:</strong> {esc(issue['state'])}</p>
          <div class='markdown-body'>{md(issue['body'])}</div>
          <p><strong>Labels:</strong> {', '.join(issue.get('labels', []))}</p>
        </article>
        """
        return render_page(issue["title"], body, user)

    @app.get("/{owner_slug}/{repo_slug}/pulls", response_class=HTMLResponse)
    def pulls_page(request: Request, owner_slug: str, repo_slug: str) -> HTMLResponse:
        user = current_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        prs = db.list_prs(repo["id"])
        body = repo_header(repo, "pull") + f"""
        <section class='toolbar'><a class='button primary' href='/{owner_slug}/{repo_slug}/pulls/new'>New pull request</a></section>
        <ul class='list'>
          {''.join(f"<li><a href='/{owner_slug}/{repo_slug}/pulls/{pr['number']}'>#{pr['number']} {esc(pr['title'])}</a><br><small>{esc(pr['state'])} · {esc(pr['source_branch'])} → {esc(pr['target_branch'])}</small></li>" for pr in prs)}
        </ul>
        """
        return render_page("Pull requests", body, user)

    @app.get("/{owner_slug}/{repo_slug}/pulls/new", response_class=HTMLResponse)
    def pr_form(request: Request, owner_slug: str, repo_slug: str) -> HTMLResponse:
        user = require_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        branches = git.list_branches(repo_path(repo))
        options = "".join(f"<option value='{esc(branch)}'>{esc(branch)}</option>" for branch in branches)
        body = repo_header(repo, "pull") + f"""
        <h2>Open pull request</h2>
        <form method='post' class='stack'>
          <label>Title<input name='title' required></label>
          <label>Body<textarea name='body'></textarea></label>
          <label>Source branch<select name='source_branch'>{options}</select></label>
          <label>Target branch<select name='target_branch'>{options}</select></label>
          <label>Linked issue #<input name='linked_issue_number' value=''></label>
          <label>Draft<select name='draft'><option value='false'>Ready for review</option><option value='true'>Draft</option></select></label>
          <button class='button primary'>Create PR</button>
        </form>
        """
        return render_page("New PR", body, user)

    @app.post("/{owner_slug}/{repo_slug}/pulls/new")
    def pr_create(
        request: Request,
        owner_slug: str,
        repo_slug: str,
        title: str = Form(...),
        body: str = Form(""),
        source_branch: str = Form(...),
        target_branch: str = Form(...),
        linked_issue_number: str = Form(""),
        draft: str = Form("false"),
    ):
        user = require_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        pr_id = db.create_pull_request(
            repo["id"],
            user["id"],
            title,
            body,
            source_branch,
            target_branch,
            int(linked_issue_number) if linked_issue_number.strip() else None,
            draft.lower() == "true",
        )
        pr = db.fetchone("SELECT * FROM pull_requests WHERE id = ?", (pr_id,))
        trigger_actions(repo, "pull_request")
        emit_webhook(
            repo,
            "pull_request",
            {"repository": f"{owner_slug}/{repo_slug}", "action": "opened", "number": pr["number"], "title": title},
        )
        return RedirectResponse(f"/{owner_slug}/{repo_slug}/pulls/{pr['number']}", status_code=303)

    @app.get("/{owner_slug}/{repo_slug}/pulls/{number}", response_class=HTMLResponse)
    def pr_detail(request: Request, owner_slug: str, repo_slug: str, number: int) -> HTMLResponse:
        user = current_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        pr = db.get_pr(repo["id"], number)
        diff = git.compare(repo_path(repo), pr["target_branch"], pr["source_branch"])
        reviews = db.get_reviews(pr["id"])
        review_comments = db.list_review_comments(pr["id"])
        gate_message, required_codeowners = pr_gate_state(repo, pr, reviews)
        requested_reviewers = pr.get("reviewers", [])
        queue_status = (
            f"Queued for auto-merge (position {pr['merge_queue_position']}, strategy {pr['merge_strategy'] or 'merge'})"
            if pr.get("auto_merge")
            else "Auto-merge disabled"
        )
        body = repo_header(repo, "pull") + f"""
        <article class='panel'>
          <h2>#{pr['number']} {esc(pr['title'])}</h2>
          <p><strong>Status:</strong> {esc(pr['state'])} · {'draft' if pr['draft'] else 'ready'} · {esc(pr['source_branch'])} → {esc(pr['target_branch'])}</p>
          <p><strong>Requested reviewers:</strong> {esc(', '.join(requested_reviewers) if requested_reviewers else 'none')}</p>
          <p><strong>Auto-merge:</strong> {esc(queue_status)}</p>
          <p><strong>Merge strategy:</strong> {esc(pr.get('merge_strategy') or 'merge')}</p>
          <div class='markdown-body'>{md(pr['body'])}</div>
          <p><strong>Linked issue:</strong> {esc(pr['linked_issue_number'])}</p>
          <p><strong>Merge gate:</strong> {esc(', '.join(gate_message) if gate_message else 'ready to merge')}</p>
          <p><strong>Required CODEOWNERS:</strong> {esc(', '.join(sorted(required_codeowners)) if required_codeowners else 'none')}</p>
        </article>
        <section class='split'>
          <div>
            <h3>Review diff</h3>
            <pre>{esc(diff or 'No diff')}</pre>
            <h3>Inline comments</h3>
            {list_to_cards([
                f"{esc(comment['author_username'])} · {esc(comment['file_path'])}:{comment['line_number']}<br>{esc(comment['body'])}"
                + (f"<pre>Suggested change\\n{esc(comment['suggested_change'])}</pre>" if comment.get('suggested_change') else "")
                for comment in review_comments
            ])}
            <form method='post' action='/{owner_slug}/{repo_slug}/pulls/{number}/comments' class='stack'>
              <label>File path<input name='file_path' value='README.md' required></label>
              <label>Line number<input name='line_number' value='1' required></label>
              <label>Comment<textarea name='body'></textarea></label>
              <label>Suggested change<textarea name='suggested_change' placeholder='Optional patch suggestion'></textarea></label>
              <button class='button'>Add inline comment</button>
            </form>
          </div>
          <div>
            <h3>Reviews</h3>
            {list_to_cards([f"{review['state']} · {esc(review['body'])}" for review in reviews])}
            <form method='post' action='/{owner_slug}/{repo_slug}/pulls/{number}/review-requests' class='stack'>
              <label>Reviewers<input name='reviewers' placeholder='bob,carol'></label>
              <button class='button'>Request reviews</button>
            </form>
            <form method='post' action='/{owner_slug}/{repo_slug}/pulls/{number}/reviews' class='stack'>
              <label>State<select name='state'><option value='APPROVED'>Approve</option><option value='CHANGES_REQUESTED'>Request changes</option><option value='COMMENTED'>Comment</option></select></label>
              <label>Body<textarea name='body'></textarea></label>
              <button class='button primary'>Submit review</button>
            </form>
            <form method='post' action='/{owner_slug}/{repo_slug}/pulls/{number}/merge' class='stack'>
              <label>Strategy<select name='strategy'><option value='merge'>Merge commit</option><option value='squash'>Squash merge</option><option value='rebase'>Rebase and merge</option></select></label>
              <button class='button'>Merge PR</button>
            </form>
            <form method='post' action='/{owner_slug}/{repo_slug}/pulls/{number}/auto-merge' class='stack'>
              <label>Auto-merge strategy<select name='strategy'><option value='merge'>Merge commit</option><option value='squash'>Squash merge</option><option value='rebase'>Rebase and merge</option></select></label>
              <button class='button'>Queue for auto-merge</button>
            </form>
          </div>
        </section>
        """
        return render_page(pr["title"], body, user)

    @app.post("/{owner_slug}/{repo_slug}/pulls/{number}/review-requests")
    def request_pr_reviewers(request: Request, owner_slug: str, repo_slug: str, number: int, reviewers: str = Form("")):
        user = require_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        pr = db.get_pr(repo["id"], number)
        requested = [item.strip().lstrip("@") for item in reviewers.split(",") if item.strip()]
        db.set_pr_reviewers(pr["id"], requested)
        for username in requested:
            reviewer = db.get_user_by_username(username)
            if reviewer:
                db.add_notification(
                    reviewer["id"],
                    "review_request",
                    f"Review request for {owner_slug}/{repo_slug} PR #{number} from @{user['username']}",
                    f"/{owner_slug}/{repo_slug}/pulls/{number}",
                )
        return RedirectResponse(f"/{owner_slug}/{repo_slug}/pulls/{number}", status_code=303)

    @app.post("/{owner_slug}/{repo_slug}/pulls/{number}/comments")
    def add_pr_comment(
        request: Request,
        owner_slug: str,
        repo_slug: str,
        number: int,
        file_path: str = Form(...),
        line_number: int = Form(1),
        body: str = Form(""),
        suggested_change: str = Form(""),
    ):
        user = require_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        pr = db.get_pr(repo["id"], number)
        db.add_review_comment(pr["id"], user["id"], file_path, int(line_number), body, suggested_change)
        return RedirectResponse(f"/{owner_slug}/{repo_slug}/pulls/{number}", status_code=303)

    @app.post("/{owner_slug}/{repo_slug}/pulls/{number}/reviews")
    def add_review(request: Request, owner_slug: str, repo_slug: str, number: int, state: str = Form(...), body: str = Form("")):
        user = require_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        pr = db.get_pr(repo["id"], number)
        db.add_review(pr["id"], user["id"], state, body)
        process_auto_merge_queue(repo)
        return RedirectResponse(f"/{owner_slug}/{repo_slug}/pulls/{number}", status_code=303)

    @app.post("/{owner_slug}/{repo_slug}/pulls/{number}/auto-merge")
    def enable_auto_merge(request: Request, owner_slug: str, repo_slug: str, number: int, strategy: str = Form("merge")):
        require_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        pr = db.get_pr(repo["id"], number)
        queue_position = pr["merge_queue_position"] or db.next_merge_queue_position(repo["id"])
        db.set_pr_auto_merge(pr["id"], True, strategy, queue_position)
        process_auto_merge_queue(repo)
        return RedirectResponse(f"/{owner_slug}/{repo_slug}/pulls/{number}", status_code=303)

    @app.post("/{owner_slug}/{repo_slug}/pulls/{number}/merge")
    def merge_pr(request: Request, owner_slug: str, repo_slug: str, number: int, strategy: str = Form("merge")):
        require_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        pr = db.get_pr(repo["id"], number)
        reviews = db.get_reviews(pr["id"])
        gate_message, _ = pr_gate_state(repo, pr, reviews)
        if gate_message:
            raise HTTPException(status_code=400, detail=", ".join(gate_message))
        complete_merge(repo, pr, strategy)
        return RedirectResponse(f"/{owner_slug}/{repo_slug}/pulls/{number}", status_code=303)

    @app.get("/{owner_slug}/{repo_slug}/discussions", response_class=HTMLResponse)
    def discussions_page(request: Request, owner_slug: str, repo_slug: str) -> HTMLResponse:
        user = current_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        discussions = db.list_discussions(repo["id"])
        body = repo_header(repo, "discussion") + f"""
        <section class='toolbar'><a class='button primary' href='/{owner_slug}/{repo_slug}/discussions/new'>New discussion</a></section>
        <ul class='list'>{''.join(f"<li>#{d['number']} <strong>{esc(d['title'])}</strong> · {esc(d['category'])}</li>" for d in discussions)}</ul>
        """
        return render_page("Discussions", body, user)

    @app.get("/{owner_slug}/{repo_slug}/discussions/new", response_class=HTMLResponse)
    def discussion_form(request: Request, owner_slug: str, repo_slug: str) -> HTMLResponse:
        user = require_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        body = repo_header(repo, "discussion") + """
        <h2>Start discussion</h2>
        <form method='post' class='stack'>
          <label>Category<select name='category'><option value='Announcements'>Announcements</option><option value='Q&A'>Q&A</option><option value='Ideas'>Ideas</option></select></label>
          <label>Title<input name='title' required></label>
          <label>Body<textarea name='body'></textarea></label>
          <button class='button primary'>Create discussion</button>
        </form>
        """
        return render_page("New discussion", body, user)

    @app.post("/{owner_slug}/{repo_slug}/discussions/new")
    def create_discussion(request: Request, owner_slug: str, repo_slug: str, category: str = Form(...), title: str = Form(...), body: str = Form("")):
        user = require_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        db.create_discussion(repo["id"], user["id"], category, title, body)
        emit_webhook(repo, "discussion", {"repository": f"{owner_slug}/{repo_slug}", "category": category, "title": title})
        return RedirectResponse(f"/{owner_slug}/{repo_slug}/discussions", status_code=303)

    @app.get("/{owner_slug}/{repo_slug}/projects", response_class=HTMLResponse)
    def projects_page(request: Request, owner_slug: str, repo_slug: str) -> HTMLResponse:
        user = current_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        projects = db.list_projects(repo["id"])
        body = repo_header(repo, "project") + f"""
        <section class='toolbar'><a class='button primary' href='/{owner_slug}/{repo_slug}/projects/new'>New project</a></section>
        <div class='grid'>{''.join(f"<article class='card'><h3>{esc(project['name'])}</h3><p>{esc(project['description'])}</p><small>{esc(project['view_type'])}</small></article>" for project in projects)}</div>
        """
        return render_page("Projects", body, user)

    @app.get("/{owner_slug}/{repo_slug}/projects/new", response_class=HTMLResponse)
    def project_form(request: Request, owner_slug: str, repo_slug: str) -> HTMLResponse:
        user = require_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        body = repo_header(repo, "project") + """
        <form method='post' class='stack'>
          <label>Name<input name='name' required></label>
          <label>Description<textarea name='description'></textarea></label>
          <label>View<select name='view_type'><option value='board'>Kanban board</option><option value='table'>Table</option><option value='roadmap'>Roadmap</option></select></label>
          <button class='button primary'>Create project</button>
        </form>
        """
        return render_page("New project", body, user)

    @app.post("/{owner_slug}/{repo_slug}/projects/new")
    def create_project(request: Request, owner_slug: str, repo_slug: str, name: str = Form(...), description: str = Form(""), view_type: str = Form("board")):
        require_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        db.create_project(repo["id"], name, description, view_type)
        return RedirectResponse(f"/{owner_slug}/{repo_slug}/projects", status_code=303)

    @app.get("/{owner_slug}/{repo_slug}/wiki", response_class=HTMLResponse)
    def wiki_page(request: Request, owner_slug: str, repo_slug: str) -> HTMLResponse:
        user = current_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        pages = db.list_wiki_pages(repo["id"])
        current = pages[0] if pages else None
        content = md(current["content"]) if current else "<p>No wiki pages yet.</p>"
        revisions = db.get_wiki_revisions(current["id"]) if current else []
        body = repo_header(repo, "wiki") + f"""
        <section class='toolbar'><a class='button primary' href='/{owner_slug}/{repo_slug}/wiki/new'>New page</a></section>
        <section class='split'>
          <div>
            <h2>Pages</h2>
            {list_to_cards([f"<a href='/{owner_slug}/{repo_slug}/wiki/{page['slug']}'>{esc(page['title'])}</a>" for page in pages])}
          </div>
          <div class='panel markdown-body'>
            {content}
            <hr>
            <h3>History</h3>
            {list_to_cards([esc(rev['created_at']) for rev in revisions])}
          </div>
        </section>
        """
        return render_page("Wiki", body, user)

    @app.get("/{owner_slug}/{repo_slug}/wiki/{slug}", response_class=HTMLResponse)
    def wiki_detail(request: Request, owner_slug: str, repo_slug: str, slug: str) -> HTMLResponse:
        user = current_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        page = db.get_wiki_page(repo["id"], slug)
        revisions = db.get_wiki_revisions(page["id"]) if page else []
        body = repo_header(repo, "wiki") + f"<article class='panel markdown-body'>{md(page['content'])}</article><h3>Sidebar</h3><pre>{esc(page['sidebar'])}</pre><h3>History</h3>{list_to_cards([esc(rev['created_at']) for rev in revisions])}"
        return render_page(page["title"], body, user)

    @app.get("/{owner_slug}/{repo_slug}/wiki/new", response_class=HTMLResponse)
    def wiki_form(request: Request, owner_slug: str, repo_slug: str) -> HTMLResponse:
        user = require_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        body = repo_header(repo, "wiki") + """
        <form method='post' class='stack'>
          <label>Title<input name='title' required></label>
          <label>Content<textarea name='content' rows='16'></textarea></label>
          <label>Sidebar<textarea name='sidebar'></textarea></label>
          <button class='button primary'>Publish page</button>
        </form>
        """
        return render_page("New wiki page", body, user)

    @app.post("/{owner_slug}/{repo_slug}/wiki/new")
    def create_wiki(request: Request, owner_slug: str, repo_slug: str, title: str = Form(...), content: str = Form(""), sidebar: str = Form("")):
        user = require_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        db.create_wiki_page(repo["id"], title, content, sidebar, user["id"])
        return RedirectResponse(f"/{owner_slug}/{repo_slug}/wiki", status_code=303)

    @app.get("/{owner_slug}/{repo_slug}/actions", response_class=HTMLResponse)
    def actions_page(request: Request, owner_slug: str, repo_slug: str) -> HTMLResponse:
        user = current_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        workflows = git.parse_workflows(repo_path(repo))
        runs = db.list_action_runs(repo["id"])
        body = repo_header(repo, "action") + f"""
        <section class='split'>
          <div>
            <h2>Workflows</h2>
            {list_to_cards([f"{workflow['name']} · triggers={workflow['on']} · jobs={', '.join(workflow['jobs'])}" for workflow in workflows])}
          </div>
          <div>
            <h2>Runs</h2>
            {list_to_cards([f"{run['workflow_name']} · {run['event_name']} · {run['status']}<pre>{esc(run['logs'])}</pre>" for run in runs])}
          </div>
        </section>
        <form method='post' action='/{owner_slug}/{repo_slug}/actions/dispatch'><button class='button'>Run workflow manually</button></form>
        """
        return render_page("Actions", body, user)

    @app.post("/{owner_slug}/{repo_slug}/actions/dispatch")
    def actions_dispatch(request: Request, owner_slug: str, repo_slug: str):
        require_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        trigger_actions(repo, "workflow_dispatch")
        process_auto_merge_queue(repo)
        return RedirectResponse(f"/{owner_slug}/{repo_slug}/actions", status_code=303)

    @app.get("/{owner_slug}/{repo_slug}/packages", response_class=HTMLResponse)
    def packages_page(request: Request, owner_slug: str, repo_slug: str) -> HTMLResponse:
        user = current_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        packages = db.list_packages(repo["id"])
        if not packages:
            db.upsert_package(repo["id"], "npm", repo_slug, "0.1.0", repo["visibility"], {"source": "seed"})
            packages = db.list_packages(repo["id"])
        body = repo_header(repo, "package") + f"<h2>Packages</h2>{list_to_cards([f"{p['ecosystem']} · {p['name']}@{p['version']} · {p['visibility']}" for p in packages])}"
        return render_page("Packages", body, user)

    @app.get("/{owner_slug}/{repo_slug}/pages", response_class=HTMLResponse)
    def pages_page(request: Request, owner_slug: str, repo_slug: str) -> HTMLResponse:
        user = current_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        content = git.pages_content(repo_path(repo))
        rendered = md(content) if content.endswith("\n") or content.startswith("#") else f"<pre>{esc(content)}</pre>"
        body = repo_header(repo, "page") + f"""
        <article class='panel'>
          <h2>Pages site preview</h2>
          <p>Source: branch <strong>{esc(repo['default_branch'])}</strong> or <code>/docs</code> folder · Custom domains and HTTPS can be configured via DNS in a production deployment.</p>
          <div class='markdown-body'>{rendered}</div>
        </article>
        """
        return render_page("Pages", body, user)

    @app.get("/{owner_slug}/{repo_slug}/insights", response_class=HTMLResponse)
    def insights_page(request: Request, owner_slug: str, repo_slug: str) -> HTMLResponse:
        user = current_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        insights = git.insights(repo_path(repo))
        traffic = db.get_traffic(repo["id"])
        body = repo_header(repo, "insight") + f"""
        <section class='grid two-up'>
          <article class='card'><h3>Language breakdown</h3>{list_to_cards([f"{lang}: {count} bytes" for lang, count in insights['languages'].items()])}</article>
          <article class='card'><h3>Dependency graph</h3>{list_to_cards(insights['dependencies'])}</article>
          <article class='card'><h3>Contributor graph</h3>{list_to_cards(insights['contributors'])}</article>
          <article class='card'><h3>Traffic analytics</h3>{list_to_cards([f"{row['event_type']}: {row['count']}" for row in traffic])}</article>
          <article class='card'><h3>Network graph</h3>{list_to_cards(git.list_branches(repo_path(repo)) + git.list_tags(repo_path(repo)))}</article>
          <article class='card'><h3>Compare refs</h3><a class='button' href='/{owner_slug}/{repo_slug}/compare?base=main&head=main'>Open compare</a></article>
        </section>
        """
        return render_page("Insights", body, user)

    @app.get("/{owner_slug}/{repo_slug}/settings", response_class=HTMLResponse)
    def repo_settings(request: Request, owner_slug: str, repo_slug: str) -> HTMLResponse:
        user = require_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        webhooks = db.list_repo_webhooks(repo["id"])
        body = repo_header(repo, "setting") + f"""
        <section class='split'>
          <div>
            <h2>Repository settings</h2>
            <form method='post' action='/{owner_slug}/{repo_slug}/settings/state' class='stack'>
              <label>Visibility<select name='visibility'><option value='public' {'selected' if repo['visibility']=='public' else ''}>Public</option><option value='private' {'selected' if repo['visibility']=='private' else ''}>Private</option></select></label>
              <label>Archived<select name='archived'><option value='0'>Active</option><option value='1' {'selected' if repo['archived'] else ''}>Archived</option></select></label>
              <button class='button primary'>Save settings</button>
            </form>
            <h3>Webhooks</h3>
            <form method='post' action='/{owner_slug}/{repo_slug}/settings/webhooks' class='stack'>
              <label>Target URL<input name='target_url' placeholder='https://example.test/webhook' required></label>
              <label>Events<input name='events' value='push,pull_request,issues' placeholder='push,issues'></label>
              <label>Secret<input name='secret' value=''></label>
              <button class='button'>Add webhook</button>
            </form>
            {list_to_cards([f"{esc(hook['target_url'])} · events={', '.join(hook.get('events', []))}" for hook in webhooks])}
          </div>
          <div>
            <h2>Danger zone</h2>
            <form method='post' action='/{owner_slug}/{repo_slug}/delete' class='stack'><button class='button danger'>Delete repository</button></form>
          </div>
        </section>
        """
        return render_page("Settings", body, user)

    @app.post("/{owner_slug}/{repo_slug}/settings/state")
    def repo_state_change(request: Request, owner_slug: str, repo_slug: str, visibility: str = Form(...), archived: int = Form(...)):
        require_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        db.update_repo_state(repo["id"], archived=int(archived), visibility=visibility)
        return RedirectResponse(f"/{owner_slug}/{repo_slug}/settings", status_code=303)

    @app.post("/{owner_slug}/{repo_slug}/settings/webhooks")
    def create_repo_webhook(
        request: Request,
        owner_slug: str,
        repo_slug: str,
        target_url: str = Form(...),
        events: str = Form("push"),
        secret: str = Form(""),
    ):
        require_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        event_list = [item.strip() for item in events.split(",") if item.strip()]
        db.create_repo_webhook(repo["id"], target_url, secret, event_list)
        return RedirectResponse(f"/{owner_slug}/{repo_slug}/settings", status_code=303)

    @app.post("/{owner_slug}/{repo_slug}/delete")
    def repo_delete(request: Request, owner_slug: str, repo_slug: str):
        require_user(request)
        repo = db.get_repo(owner_slug, repo_slug)
        git.delete_repo(repo_path(repo))
        db.delete_repo(repo["id"])
        return RedirectResponse("/explore", status_code=303)

    @app.get("/search", response_class=HTMLResponse)
    def search_page(request: Request, q: str = "") -> HTMLResponse:
        user = current_user(request)
        if not q:
            body = "<h1>Search</h1><form method='get' class='inline-form'><input name='q' placeholder='Search code, repos, issues, discussions'><button>Search</button></form>"
            return render_page("Search", body, user)
        results = db.search(q)
        code_hits = []
        for repo in db.list_repos():
            path = repo_path(repo)
            for file in path.rglob("*"):
                if file.is_file() and ".git" not in file.parts:
                    try:
                        if q.lower() in file.read_text(encoding="utf-8", errors="ignore").lower():
                            code_hits.append(f"{repo['owner_slug']}/{repo['slug']}: {file.relative_to(path)}")
                    except Exception:
                        continue
        body = f"""
        <h1>Search results for {esc(q)}</h1>
        <form method='get' class='inline-form'><input name='q' value='{esc(q)}'><button>Search</button></form>
        <section class='grid two-up'>
          <article class='card'><h2>Repositories</h2>{list_to_cards([f"<a href='/{r['owner_slug']}/{r['slug']}'>{esc(r['owner_slug'])}/{esc(r['slug'])}</a>" for r in results['repositories']])}</article>
          <article class='card'><h2>Issues</h2>{list_to_cards([f"{item['title']}" for item in results['issues']])}</article>
          <article class='card'><h2>Pull requests</h2>{list_to_cards([f"{item['title']}" for item in results['pull_requests']])}</article>
          <article class='card'><h2>Discussions</h2>{list_to_cards([f"{item['title']}" for item in results['discussions']])}</article>
          <article class='card'><h2>Wiki pages</h2>{list_to_cards([f"{item['title']}" for item in results['wiki_pages']])}</article>
          <article class='card'><h2>Code search</h2>{list_to_cards(code_hits[:25])}</article>
        </section>
        """
        return render_page("Search", body, user)

    @app.get("/notifications", response_class=HTMLResponse)
    def notifications_page(request: Request) -> HTMLResponse:
        user = current_user(request)
        items = db.list_notifications(user["id"] if user else None)
        body = f"<h1>Notifications</h1>{list_to_cards([f"{item['kind']} · <a href='{item['url'] or '#'}'>{esc(item['message'])}</a>" for item in items])}"
        return render_page("Notifications", body, user)

    @app.get("/marketplace", response_class=HTMLResponse)
    def marketplace_page(request: Request) -> HTMLResponse:
        user = current_user(request)
        apps = db.list_marketplace_apps()
        body = f"<h1>Marketplace</h1><div class='grid'>{''.join(f"<article class='card'><h3>{esc(app['name'])}</h3><p>{esc(app['description'])}</p><small>{esc(app['kind'])}</small><br><a class='button' href='{esc(app['install_url'])}'>Install</a></article>" for app in apps)}</div>"
        return render_page("Marketplace", body, user)

    @app.get("/sponsors", response_class=HTMLResponse)
    def sponsors_page(request: Request) -> HTMLResponse:
        user = current_user(request)
        tiers = db.list_sponsorship_tiers(user["username"] if user else "") if user else []
        if user and not tiers:
            db.create_sponsorship_tier(user["username"], "Supporter", 500, "Back the roadmap")
            tiers = db.list_sponsorship_tiers(user["username"])
        body = f"<h1>Sponsors</h1><p>User and organization sponsorship tiers with payment-ready records.</p>{list_to_cards([f"{tier['name']} · ${tier['amount_cents']/100:.2f} · {esc(tier['perks'])}" for tier in tiers])}"
        return render_page("Sponsors", body, user)

    @app.get("/admin", response_class=HTMLResponse)
    def admin_page(request: Request) -> HTMLResponse:
        user = current_user(request)
        stats = db.stats()
        audit = db.list_audit_logs()
        body = f"""
        <h1>Admin dashboard</h1>
        <section class='grid two-up'>
          <article class='card'><h3>System health</h3><ul><li>Database: healthy</li><li>Git storage: healthy</li><li>Runner pool: available</li><li>Rate limiting: enabled at app tier</li></ul></article>
          <article class='card'><h3>Counts</h3>{list_to_cards([f"{k}: {v}" for k, v in stats.items()])}</article>
          <article class='card'><h3>Users</h3>{list_to_cards([esc(user_item['username']) for user_item in db.list_users()])}</article>
          <article class='card'><h3>Audit logs</h3>{list_to_cards([f"{log['action']} → {esc(log['target'])}" for log in audit])}</article>
        </section>
        """
        return render_page("Admin", body, user)

    @app.get("/api/repos")
    def api_repos(request: Request) -> JSONResponse:
        session_user = current_user(request)
        token_user, token_record = current_token_bundle(request)
        viewer = session_user or token_user
        repos = []
        for repo in db.list_repos():
            if can_view_repo(viewer, repo) or token_allows_repo(token_record, repo):
                repos.append(repo)
        return JSONResponse(repos)

    @app.get("/api/repos/{owner_slug}/{repo_slug}")
    def api_repo(request: Request, owner_slug: str, repo_slug: str) -> JSONResponse:
        repo = db.get_repo(owner_slug, repo_slug)
        if not repo:
            raise HTTPException(404)
        session_user = current_user(request)
        token_user, token_record = current_token_bundle(request)
        if not can_view_repo(session_user or token_user, repo) and not token_allows_repo(token_record, repo):
            raise HTTPException(status_code=401, detail="Repository access denied")
        return JSONResponse(repo)

    @app.get("/api/repos/{owner_slug}/{repo_slug}/webhooks/deliveries")
    def api_repo_webhook_deliveries(request: Request, owner_slug: str, repo_slug: str) -> JSONResponse:
        repo = db.get_repo(owner_slug, repo_slug)
        if not repo:
            raise HTTPException(404)
        session_user = current_user(request)
        token_user, token_record = current_token_bundle(request)
        if not can_view_repo(session_user or token_user, repo) and not token_allows_repo(token_record, repo):
            raise HTTPException(status_code=401, detail="Repository access denied")
        return JSONResponse({"deliveries": db.list_webhook_deliveries(repo["id"])})

    @app.get("/api/graphql")
    def graphql_stub(owner: str = "", repo: str = "") -> JSONResponse:
        target = db.get_repo(owner, repo) if owner and repo else None
        return JSONResponse({"data": {"repository": target, "viewer": None}})

    @app.post("/api/ai/suggest")
    async def ai_suggest(request: Request) -> JSONResponse:
        payload = await request.json()
        code = payload.get("code", "")
        suggestion = "# Suggested improvement\n" + code + ("\n# TODO: add tests" if "TODO" not in code else "")
        return JSONResponse({"suggestion": suggestion, "provider": os.getenv("LLM_PROVIDER", "mock")})

    @app.get("/api/webhooks")
    def webhooks_info() -> JSONResponse:
        return JSONResponse({"supported_events": ["push", "pull_request", "issues", "release", "discussion"], "filtering": True})

    @app.get("/healthz")
    def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    return app


app = create_app()
