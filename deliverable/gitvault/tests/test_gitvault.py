import base64
import hashlib
import hmac
import time
from pathlib import Path

from fastapi.testclient import TestClient

from gitvault.app import create_app


def make_client(tmp_path: Path):
    app = create_app(data_dir=tmp_path / "data", testing=True)
    return TestClient(app)


def register_and_login(client: TestClient, email="alice@example.com", username="alice", password="secret123"):
    response = client.post(
        "/register",
        data={"email": email, "username": username, "password": password},
        follow_redirects=False,
    )
    assert response.status_code == 303
    login = client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
    assert login.status_code == 303


def current_totp(secret: str) -> str:
    normalized = secret.upper()
    padding = "=" * ((8 - len(normalized) % 8) % 8)
    key = base64.b32decode(normalized + padding)
    counter = int(time.time()) // 30
    digest = hmac.new(key, counter.to_bytes(8, "big"), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    chunk = digest[offset : offset + 4]
    code = (int.from_bytes(chunk, "big") & 0x7FFFFFFF) % 1_000_000
    return f"{code:06d}"


def test_homepage_loads(tmp_path: Path):
    client = make_client(tmp_path)
    response = client.get("/")
    assert response.status_code == 200
    assert "GitVault" in response.text


def test_create_repository_and_browse_file(tmp_path: Path):
    client = make_client(tmp_path)
    register_and_login(client)

    response = client.post(
        "/repos/new",
        data={
            "name": "demo-repo",
            "description": "A demo repository",
            "visibility": "public",
            "readme_template": "python",
            "license_template": "mit",
            "gitignore_template": "python",
            "topics": "python,fastapi",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    repo_page = client.get("/alice/demo-repo")
    assert repo_page.status_code == 200
    assert "demo-repo" in repo_page.text
    assert "README.md" in repo_page.text

    raw = client.get("/alice/demo-repo/raw/main/README.md")
    assert raw.status_code == 200
    assert "demo-repo" in raw.text.lower()

    history = client.get("/alice/demo-repo/history/main/README.md")
    assert history.status_code == 200
    assert "Initial scaffold commit" in history.text


def test_issue_and_pr_flow(tmp_path: Path):
    client = make_client(tmp_path)
    register_and_login(client)
    client.post(
        "/repos/new",
        data={"name": "collab", "description": "repo", "visibility": "public"},
        follow_redirects=False,
    )
    branch = client.post(
        "/alice/collab/branches/create",
        data={"branch_name": "feature-login", "from_ref": "main"},
        follow_redirects=False,
    )
    assert branch.status_code == 303
    edit = client.post(
        "/alice/collab/edit/feature-login/docs/notes.md",
        data={"content": "hello world", "message": "Add notes"},
        follow_redirects=False,
    )
    assert edit.status_code == 303

    issue = client.post(
        "/alice/collab/issues/new",
        data={"title": "Bug report", "body": "something broke", "labels": "bug"},
        follow_redirects=False,
    )
    assert issue.status_code == 303

    pr = client.post(
        "/alice/collab/pulls/new",
        data={
            "title": "Add notes",
            "body": "Implements docs",
            "source_branch": "feature-login",
            "target_branch": "main",
            "linked_issue_number": "1",
            "draft": "false",
        },
        follow_redirects=False,
    )
    assert pr.status_code == 303

    review = client.post(
        "/alice/collab/pulls/1/reviews",
        data={"state": "APPROVED", "body": "Looks good"},
        follow_redirects=False,
    )
    assert review.status_code == 303

    merge = client.post(
        "/alice/collab/pulls/1/merge",
        data={"strategy": "merge"},
        follow_redirects=False,
    )
    assert merge.status_code == 303

    pulls = client.get("/alice/collab/pulls/1")
    assert "merged" in pulls.text.lower()


def test_search_notifications_and_actions(tmp_path: Path):
    client = make_client(tmp_path)
    register_and_login(client)
    client.post(
        "/repos/new",
        data={"name": "ops", "description": "automation repo", "visibility": "public"},
        follow_redirects=False,
    )
    client.post(
        "/alice/ops/edit/main/.github/workflows/ci.yml",
        data={
            "content": "name: CI\non:\n  push:\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hello\n",
            "message": "Add workflow",
        },
        follow_redirects=False,
    )

    actions = client.get("/alice/ops/actions")
    assert actions.status_code == 200
    assert "CI" in actions.text or "ci" in actions.text.lower()

    search = client.get("/search?q=automation")
    assert search.status_code == 200
    assert "ops" in search.text

    notifications = client.get("/notifications")
    assert notifications.status_code == 200


def test_org_wiki_project_discussion_and_admin(tmp_path: Path):
    client = make_client(tmp_path)
    register_and_login(client)
    org = client.post(
        "/orgs/new",
        data={"name": "Acme Inc", "slug": "acme", "description": "The org"},
        follow_redirects=False,
    )
    assert org.status_code == 303
    repo = client.post(
        "/repos/new",
        data={"name": "platform", "description": "repo", "visibility": "private", "owner_slug": "acme"},
        follow_redirects=False,
    )
    assert repo.status_code == 303

    wiki = client.post(
        "/acme/platform/wiki/new",
        data={"title": "Home", "content": "# Welcome", "sidebar": "* [Home](/)"},
        follow_redirects=False,
    )
    assert wiki.status_code == 303

    project = client.post(
        "/acme/platform/projects/new",
        data={"name": "Roadmap", "description": "Q3 work", "view_type": "roadmap"},
        follow_redirects=False,
    )
    assert project.status_code == 303

    discussion = client.post(
        "/acme/platform/discussions/new",
        data={"category": "Q&A", "title": "How do we deploy?", "body": "Question body"},
        follow_redirects=False,
    )
    assert discussion.status_code == 303

    admin = client.get("/admin")
    assert admin.status_code == 200
    assert "System health" in admin.text


def test_two_factor_sessions_and_personal_access_tokens(tmp_path: Path):
    client = make_client(tmp_path)
    register_and_login(client)
    client.post(
        "/repos/new",
        data={"name": "secure-repo", "description": "repo", "visibility": "private"},
        follow_redirects=False,
    )

    enable = client.post("/settings/security/totp/enable", follow_redirects=False)
    assert enable.status_code in {200, 303}

    user = client.app.state.db.get_user_by_email("alice@example.com")
    security = client.app.state.db.get_user_security(user["id"])
    assert security["two_factor_enabled"] == 1
    assert security["totp_secret"]

    client.get("/logout", follow_redirects=False)
    login = client.post(
        "/login",
        data={"email": "alice@example.com", "password": "secret123"},
        follow_redirects=False,
    )
    assert login.status_code == 303
    assert login.headers["location"].endswith("/login/2fa")

    verify = client.post("/login/2fa", data={"code": current_totp(security["totp_secret"])}, follow_redirects=False)
    assert verify.status_code == 303

    security_page = client.get("/settings/security")
    assert security_page.status_code == 200
    assert "Two-factor authentication" in security_page.text
    assert "Active sessions" in security_page.text

    token_create = client.post(
        "/settings/tokens",
        data={"name": "ci-bot", "scopes": "repo:read", "repo_scope": "alice/secure-repo"},
    )
    assert token_create.status_code == 200
    token = token_create.json()["token"]
    assert token.startswith("gv_")

    anonymous = make_client(tmp_path)
    anonymous_repo = anonymous.get("/api/repos/alice/secure-repo")
    assert anonymous_repo.status_code in {401, 403, 404}

    token_repo = anonymous.get(
        "/api/repos/alice/secure-repo",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert token_repo.status_code == 200
    assert token_repo.json()["slug"] == "secure-repo"


def test_filtered_webhook_deliveries_are_recorded(tmp_path: Path):
    client = make_client(tmp_path)
    register_and_login(client)
    client.post(
        "/repos/new",
        data={"name": "hooks", "description": "repo", "visibility": "public"},
        follow_redirects=False,
    )

    hook = client.post(
        "/alice/hooks/settings/webhooks",
        data={"target_url": "https://example.test/webhook", "events": "issues,push", "secret": "topsecret"},
        follow_redirects=False,
    )
    assert hook.status_code == 303

    issue = client.post(
        "/alice/hooks/issues/new",
        data={"title": "Webhook me", "body": "body", "labels": "bug"},
        follow_redirects=False,
    )
    assert issue.status_code == 303

    discussion = client.post(
        "/alice/hooks/discussions/new",
        data={"category": "Q&A", "title": "Ignored", "body": "no delivery wanted"},
        follow_redirects=False,
    )
    assert discussion.status_code == 303

    edit = client.post(
        "/alice/hooks/edit/main/README.md",
        data={"content": "# hooks\nupdated", "message": "Update README"},
        follow_redirects=False,
    )
    assert edit.status_code == 303

    deliveries = client.get("/api/repos/alice/hooks/webhooks/deliveries")
    assert deliveries.status_code == 200
    events = [delivery["event_name"] for delivery in deliveries.json()["deliveries"]]
    assert "issues" in events
    assert "push" in events
    assert "discussion" not in events


def test_pull_request_review_requests_inline_suggestions_and_auto_merge_queue(tmp_path: Path):
    alice = make_client(tmp_path)
    bob = make_client(tmp_path)

    register_and_login(alice)
    register_and_login(bob, email="bob@example.com", username="bob", password="secret456")

    repo = alice.post(
        "/repos/new",
        data={"name": "review-lab", "description": "repo", "visibility": "public"},
        follow_redirects=False,
    )
    assert repo.status_code == 303

    codeowners = alice.post(
        "/alice/review-lab/edit/main/CODEOWNERS",
        data={"content": "* @bob\n", "message": "Require bob approval"},
        follow_redirects=False,
    )
    assert codeowners.status_code == 303

    alice.app.state.db.execute(
        "UPDATE branch_rules SET require_reviews = 1, codeowners_required = 1, required_status_checks = 1 WHERE repo_id = ? AND branch_name = ?",
        (alice.app.state.db.get_repo("alice", "review-lab")["id"], "main"),
    )

    branch = alice.post(
        "/alice/review-lab/branches/create",
        data={"branch_name": "feature-ui", "from_ref": "main"},
        follow_redirects=False,
    )
    assert branch.status_code == 303

    edit = alice.post(
        "/alice/review-lab/edit/feature-ui/src/app.py",
        data={"content": "print('hello from feature')\n", "message": "Add app entrypoint"},
        follow_redirects=False,
    )
    assert edit.status_code == 303

    pr = alice.post(
        "/alice/review-lab/pulls/new",
        data={
            "title": "Feature UI",
            "body": "Implements the first version",
            "source_branch": "feature-ui",
            "target_branch": "main",
            "linked_issue_number": "",
            "draft": "false",
        },
        follow_redirects=False,
    )
    assert pr.status_code == 303

    request_review = alice.post(
        "/alice/review-lab/pulls/1/review-requests",
        data={"reviewers": "bob"},
        follow_redirects=False,
    )
    assert request_review.status_code == 303

    comment = bob.post(
        "/alice/review-lab/pulls/1/comments",
        data={
            "file_path": "src/app.py",
            "line_number": "1",
            "body": "Use a function so the entrypoint is reusable.",
            "suggested_change": "def main():\n    print('hello from feature')\n\n\nif __name__ == '__main__':\n    main()\n",
        },
        follow_redirects=False,
    )
    assert comment.status_code == 303

    auto_merge = alice.post(
        "/alice/review-lab/pulls/1/auto-merge",
        data={"strategy": "squash"},
        follow_redirects=False,
    )
    assert auto_merge.status_code == 303

    queued_detail = alice.get("/alice/review-lab/pulls/1")
    assert queued_detail.status_code == 200
    assert "Queued for auto-merge" in queued_detail.text
    assert "Requested reviewers" in queued_detail.text
    assert "Suggested change" in queued_detail.text

    approve = bob.post(
        "/alice/review-lab/pulls/1/reviews",
        data={"state": "APPROVED", "body": "Approved by code owner"},
        follow_redirects=False,
    )
    assert approve.status_code == 303

    final_detail = alice.get("/alice/review-lab/pulls/1")
    assert final_detail.status_code == 200
    assert "merged" in final_detail.text.lower()
    assert "squash" in final_detail.text.lower()

    notifications = bob.get("/notifications")
    assert notifications.status_code == 200
    assert "review request" in notifications.text.lower()
