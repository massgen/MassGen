from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx
from fastapi.testclient import TestClient
import websockets

from texforge.app import create_app
from texforge.db import Database


def make_client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "texforge.db"
    database = Database(db_path)
    app = create_app(database=database)
    return TestClient(app)


def register_and_login(client: TestClient, email: str, password: str = "secret123", name: str = "User") -> dict:
    register = client.post(
        "/auth/register",
        json={"email": email, "password": password, "name": name},
    )
    assert register.status_code == 200
    login = client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    return login.json()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_server(base_url: str) -> None:
    for _ in range(50):
        try:
            response = httpx.get(f"{base_url}/health", timeout=1.0)
            if response.status_code == 200:
                return
        except Exception:
            time.sleep(0.1)
    raise RuntimeError("server did not start in time")


def test_dashboard_renders_seeded_content(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/")

    assert response.status_code == 200
    body = response.text
    assert "TexForge" in body
    assert "IEEE Conference" in body
    assert "Quantum Notes" in body
    assert "Live collaboration" in body


def test_project_lifecycle_compile_and_export(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    create_response = client.post(
        "/api/projects",
        json={
            "name": "My Paper",
            "template": "acm",
            "owner": "alice@example.com",
        },
    )
    assert create_response.status_code == 200
    project = create_response.json()
    project_id = project["id"]

    file_response = client.post(
        f"/api/projects/{project_id}/files",
        json={
            "path": "sections/intro.tex",
            "content": "\\section{Intro} Collaborative writing.",
        },
    )
    assert file_response.status_code == 200
    assert file_response.json()["path"] == "sections/intro.tex"

    clone_response = client.post(f"/api/projects/{project_id}/clone")
    assert clone_response.status_code == 200
    assert clone_response.json()["name"].startswith("My Paper (Clone")

    compile_response = client.post(
        f"/api/projects/{project_id}/compile",
        json={"engine": "xelatex", "entrypoint": "main.tex", "trigger": "manual"},
    )
    assert compile_response.status_code == 200
    job = compile_response.json()
    assert job["status"] == "completed"
    assert "xelatex" in job["log"]
    assert job["pdf_url"].endswith(".pdf")

    job_response = client.get(f"/api/projects/{project_id}/jobs/{job['id']}")
    assert job_response.status_code == 200
    assert job_response.json()["status"] == "completed"

    export_response = client.get(f"/api/projects/{project_id}/export.zip")
    assert export_response.status_code == 200
    assert export_response.headers["content-type"] == "application/zip"

    archive_response = client.post(f"/api/projects/{project_id}/archive")
    assert archive_response.status_code == 200
    assert archive_response.json()["archived"] is True


def test_comments_snapshots_diff_search_and_ai(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    project = client.post(
        "/api/projects",
        json={"name": "Review Draft", "template": "ieee", "owner": "reviewer@example.com"},
    ).json()
    project_id = project["id"]

    main_file = client.post(
        f"/api/projects/{project_id}/files",
        json={"path": "main.tex", "content": "\\section{Results} First draft."},
    ).json()
    file_id = main_file["id"]

    snapshot_a = client.post(
        f"/api/projects/{project_id}/snapshots",
        json={"name": "Draft A", "file_id": file_id},
    )
    assert snapshot_a.status_code == 200

    update = client.put(
        f"/api/files/{file_id}",
        json={"content": "\\section{Results} Revised draft with citation \\cite{smith2024}."},
    )
    assert update.status_code == 200

    snapshot_b = client.post(
        f"/api/projects/{project_id}/snapshots",
        json={"name": "Draft B", "file_id": file_id},
    )
    assert snapshot_b.status_code == 200

    diff_response = client.get(
        f"/api/projects/{project_id}/diff",
        params={"from_snapshot": snapshot_a.json()["id"], "to_snapshot": snapshot_b.json()["id"]},
    )
    assert diff_response.status_code == 200
    assert "Revised draft" in diff_response.json()["diff"]

    comment_response = client.post(
        f"/api/projects/{project_id}/comments",
        json={
            "file_id": file_id,
            "author": "prof@example.com",
            "body": "Please strengthen the literature review.",
            "line_from": 1,
            "line_to": 1,
        },
    )
    assert comment_response.status_code == 200

    search_response = client.get("/api/search", params={"q": "literature review"})
    assert search_response.status_code == 200
    assert any(item["kind"] == "comment" for item in search_response.json()["results"])

    ai_response = client.post(
        f"/api/projects/{project_id}/ai/assist",
        json={
            "prompt": "Write a LaTeX table for experiment results with accuracy and F1 columns.",
            "mode": "generate",
        },
    )
    assert ai_response.status_code == 200
    assert "tabular" in ai_response.json()["suggestion"]


def test_auth_permissions_sharing_and_admin_metrics(tmp_path: Path) -> None:
    owner_client = make_client(tmp_path)
    bob_client = make_client(tmp_path)

    owner = register_and_login(owner_client, "alice@example.com", name="Alice")
    register_and_login(bob_client, "bob@example.com", name="Bob")

    project = owner_client.post(
        "/api/projects",
        json={"name": "Secured Draft", "template": "ieee", "owner": owner["email"]},
    ).json()
    project_id = project["id"]

    denied = bob_client.get(f"/api/projects/{project_id}/files")
    assert denied.status_code == 403

    share = owner_client.post(
        f"/api/projects/{project_id}/share-links",
        json={"role": "editor", "expires_in_days": 7},
    )
    assert share.status_code == 200
    share_id = share.json()["id"]

    accept = bob_client.post(f"/api/share/{share_id}/accept")
    assert accept.status_code == 200
    assert accept.json()["role"] == "editor"

    file_response = bob_client.post(
        f"/api/projects/{project_id}/files",
        json={"path": "sections/method.tex", "content": "\\section{Method} Shared edits."},
    )
    assert file_response.status_code == 200

    admin = owner_client.get("/api/admin/metrics")
    assert admin.status_code == 200
    metrics = admin.json()
    assert metrics["users"] >= 2
    assert metrics["projects"] >= 1
    assert metrics["memberships"] >= 2


def test_suggestions_references_and_snapshot_restore(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    owner = register_and_login(client, "writer@example.com", name="Writer")

    project = client.post(
        "/api/projects",
        json={"name": "Reference Draft", "template": "ieee", "owner": owner["email"]},
    ).json()
    project_id = project["id"]
    main_file = next(item for item in client.get(f"/api/projects/{project_id}/files").json() if item["path"] == "main.tex")

    suggestion = client.post(
        f"/api/projects/{project_id}/suggestions",
        json={
            "file_id": main_file["id"],
            "author": "reviewer@example.com",
            "body": "Use a stronger introduction sentence.",
            "original_text": "Write here.",
            "suggested_text": "Write here with stronger framing and a clearer motivation.",
        },
    )
    assert suggestion.status_code == 200

    accepted = client.post(f"/api/projects/{project_id}/suggestions/{suggestion.json()['id']}/accept")
    assert accepted.status_code == 200
    assert "stronger framing" in accepted.json()["file"]["content"]

    imported = client.post(
        f"/api/projects/{project_id}/references/import",
        json={"source": "doi", "identifier": "10.5555/texforge-demo"},
    )
    assert imported.status_code == 200
    citation_key = imported.json()["citation_key"]
    assert citation_key

    duplicate = client.post(
        f"/api/projects/{project_id}/references/import",
        json={"source": "doi", "identifier": "10.5555/texforge-demo"},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True

    autocomplete = client.get(f"/api/projects/{project_id}/citations", params={"q": "texforge"})
    assert autocomplete.status_code == 200
    assert any(item["citation_key"] == citation_key for item in autocomplete.json()["results"])

    snapshot = client.post(
        f"/api/projects/{project_id}/snapshots",
        json={"name": "Accepted suggestion", "file_id": main_file["id"]},
    ).json()

    client.put(
        f"/api/files/{main_file['id']}",
        json={"content": "\\section{Introduction} Diverged draft."},
    )
    restored = client.post(f"/api/projects/{project_id}/snapshots/{snapshot['id']}/restore")
    assert restored.status_code == 200
    assert "stronger framing" in restored.json()["content"]


def test_websocket_collaboration_broadcasts_presence_and_edits(tmp_path: Path) -> None:
    db_path = tmp_path / "live_ws.db"
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "PYTHONPATH": ".",
        "TEXFORGE_DB_PATH": str(db_path),
    }
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "run:app", "--port", str(port)],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        wait_for_server(base_url)
        project = httpx.post(
            f"{base_url}/api/projects",
            json={"name": "Realtime", "template": "thesis", "owner": "alice@example.com"},
            timeout=5.0,
        ).json()
        project_id = project["id"]

        async def exercise() -> None:
            alice = await websockets.connect(f"ws://127.0.0.1:{port}/ws/projects/{project_id}?user=alice")
            alice_join = json.loads(await alice.recv())
            assert alice_join["type"] == "sync"

            bob = await websockets.connect(f"ws://127.0.0.1:{port}/ws/projects/{project_id}?user=bob")
            bob_initial = json.loads(await bob.recv())
            assert bob_initial["type"] == "sync"

            alice_presence = json.loads(await alice.recv())
            assert alice_presence["type"] == "presence"
            assert alice_presence["user"] == "bob"

            await bob.send(json.dumps({"type": "edit", "path": "main.tex", "content": "\\section{Realtime} Hello from Bob."}))
            alice_edit = json.loads(await alice.recv())
            assert alice_edit["type"] == "edit"
            assert alice_edit["content"].endswith("Hello from Bob.")

            await alice.send(json.dumps({"type": "cursor", "path": "main.tex", "line": 3, "column": 7}))
            bob_cursor = json.loads(await bob.recv())
            assert bob_cursor["type"] == "cursor"
            assert bob_cursor["line"] == 3
            await bob.close()
            await alice.close()

        asyncio.run(exercise())
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


def test_template_marketplace_preview_search_and_instantiation(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    listing = client.get('/api/templates', params={'q': 'resume'})
    assert listing.status_code == 200
    templates = listing.json()['results']
    assert len(templates) == 1
    assert templates[0]['slug'] == 'resume'

    preview = client.get('/api/templates/ieee')
    assert preview.status_code == 200
    assert 'main_tex' in preview.json()
    assert 'Sample Reference' in preview.json()['refs_bib']

    created = client.post(
        '/api/projects/from-template',
        json={'name': 'Instantiated from gallery', 'template': 'resume', 'owner': 'gallery@example.com'},
    )
    assert created.status_code == 200
    project = created.json()
    assert project['template'] == 'resume'
    assert any(file['path'] == 'main.tex' for file in project['files'])



def test_file_move_delete_and_project_delete(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    project = client.post(
        '/api/projects',
        json={'name': 'Lifecycle', 'template': 'acm', 'owner': 'alice@example.com'},
    ).json()
    project_id = project['id']

    created = client.post(
        f'/api/projects/{project_id}/files',
        json={'path': 'sections/intro.tex', 'content': '\\section{Intro} draft'},
    )
    assert created.status_code == 200
    file_id = created.json()['id']

    moved = client.patch(f'/api/files/{file_id}/move', json={'path': 'sections/background.tex'})
    assert moved.status_code == 200
    assert moved.json()['path'] == 'sections/background.tex'

    files_after_move = client.get(f'/api/projects/{project_id}/files')
    assert files_after_move.status_code == 200
    paths = [item['path'] for item in files_after_move.json()]
    assert 'sections/background.tex' in paths
    assert 'sections/intro.tex' not in paths

    deleted_file = client.delete(f'/api/files/{file_id}')
    assert deleted_file.status_code == 200
    assert deleted_file.json()['deleted'] is True

    deleted_project = client.delete(f'/api/projects/{project_id}')
    assert deleted_project.status_code == 200
    assert deleted_project.json()['deleted'] is True

    missing = client.get(f'/api/projects/{project_id}/files')
    assert missing.status_code == 404



def test_threaded_comments_resolution_and_branches(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    project = client.post(
        '/api/projects',
        json={'name': 'Branching Draft', 'template': 'ieee', 'owner': 'alice@example.com'},
    ).json()
    project_id = project['id']
    main_file = next(item for item in client.get(f'/api/projects/{project_id}/files').json() if item['path'] == 'main.tex')

    parent = client.post(
        f'/api/projects/{project_id}/comments',
        json={
            'file_id': main_file['id'],
            'author': 'reviewer@example.com',
            'body': 'Please revise the introduction.',
            'line_from': 1,
            'line_to': 1,
        },
    )
    assert parent.status_code == 200

    reply = client.post(
        f'/api/projects/{project_id}/comments',
        json={
            'file_id': main_file['id'],
            'author': 'author@example.com',
            'body': 'Will do.',
            'line_from': 1,
            'line_to': 1,
            'parent_id': parent.json()['id'],
        },
    )
    assert reply.status_code == 200

    thread = client.get(f'/api/projects/{project_id}/comments')
    assert thread.status_code == 200
    thread_data = thread.json()['results']
    root = next(item for item in thread_data if item['id'] == parent.json()['id'])
    assert root['reply_count'] == 1
    assert root['replies'][0]['id'] == reply.json()['id']

    resolved = client.post(f"/api/projects/{project_id}/comments/{parent.json()['id']}/resolve")
    assert resolved.status_code == 200
    assert resolved.json()['resolved'] is True

    unresolved = client.post(f"/api/projects/{project_id}/comments/{parent.json()['id']}/unresolve")
    assert unresolved.status_code == 200
    assert unresolved.json()['resolved'] is False

    snapshot = client.post(
        f'/api/projects/{project_id}/snapshots',
        json={'name': 'Base draft', 'file_id': main_file['id']},
    ).json()
    branch = client.post(
        f'/api/projects/{project_id}/branches',
        json={'name': 'journal-revision', 'snapshot_id': snapshot['id']},
    )
    assert branch.status_code == 200
    assert branch.json()['name'] == 'journal-revision'

    listed = client.get(f'/api/projects/{project_id}/branches')
    assert listed.status_code == 200
    assert any(item['id'] == branch.json()['id'] for item in listed.json()['results'])

    client.put(
        f"/api/files/{main_file['id']}",
        json={'content': '\\section{Introduction} Diverged text.'},
    )
    restored = client.post(f"/api/projects/{project_id}/branches/{branch.json()['id']}/restore")
    assert restored.status_code == 200
    assert 'Write here.' in restored.json()['content']
