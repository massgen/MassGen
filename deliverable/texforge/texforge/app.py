from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .db import Database
from .services import CompileService, ai_assist, build_diff


class ProjectCreate(BaseModel):
    name: str
    template: str
    owner: str
    description: str = ""
    visibility: str = "private"


class FileCreate(BaseModel):
    path: str
    content: str


class FileUpdate(BaseModel):
    content: str


class FileMoveRequest(BaseModel):
    path: str


class CompileRequest(BaseModel):
    engine: str = "pdflatex"
    entrypoint: str = "main.tex"
    trigger: str = "manual"


class SnapshotRequest(BaseModel):
    name: str
    file_id: str


class CommentRequest(BaseModel):
    file_id: str
    author: str
    body: str
    line_from: int = 1
    line_to: int = 1
    parent_id: str | None = None


class AIRequest(BaseModel):
    prompt: str
    mode: str = "generate"


class AuthRegister(BaseModel):
    email: str
    password: str
    name: str


class AuthLogin(BaseModel):
    email: str
    password: str


class ShareLinkRequest(BaseModel):
    role: str = "viewer"
    expires_in_days: int = 14


class SuggestionRequest(BaseModel):
    file_id: str
    author: str
    body: str
    original_text: str
    suggested_text: str


class ReferenceImportRequest(BaseModel):
    source: str
    identifier: str


class BranchRequest(BaseModel):
    name: str
    snapshot_id: str


class CollaborationHub:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.connections: dict[str, dict[str, WebSocket]] = {}

    async def connect(self, project_id: str, user: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections.setdefault(project_id, {})[user] = websocket
        files = {file["path"]: file["content"] for file in self.database.list_project_files(project_id)}
        await websocket.send_json({"type": "sync", "project_id": project_id, "files": files, "users": list(self.connections[project_id].keys())})
        await self.broadcast(project_id, {"type": "presence", "user": user, "status": "joined"}, exclude=user)

    async def disconnect(self, project_id: str, user: str) -> None:
        group = self.connections.get(project_id, {})
        if user in group:
            group.pop(user)
            await self.broadcast(project_id, {"type": "presence", "user": user, "status": "left"})
        if not group:
            self.connections.pop(project_id, None)

    async def broadcast(self, project_id: str, payload: dict[str, Any], exclude: str | None = None) -> None:
        for member, websocket in list(self.connections.get(project_id, {}).items()):
            if exclude and member == exclude:
                continue
            await websocket.send_json(payload)


def create_app(database: Database | None = None) -> FastAPI:
    base_dir = Path(__file__).parent
    app = FastAPI(title="TexForge", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    db = database or Database(Path(os.environ.get("TEXFORGE_DB_PATH", "texforge_data/texforge.db")))
    compile_service = CompileService(db)
    hub = CollaborationHub(db)
    templates = Jinja2Templates(directory=str(base_dir / "templates"))
    app.mount("/static", StaticFiles(directory=str(base_dir / "static")), name="static")

    role_rank = {"viewer": 1, "editor": 2, "owner": 3}

    def current_user(request: Request) -> dict[str, Any] | None:
        session_id = request.cookies.get("texforge_session")
        if not session_id:
            return None
        return db.get_user_by_session(session_id)

    def require_login(request: Request) -> dict[str, Any]:
        user = current_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        return user

    def ensure_project_access(request: Request, project_id: str, minimum_role: str = "viewer") -> dict[str, Any]:
        user = current_user(request)
        if not user:
            return {"role": "owner", "email": "guest", "name": "Guest Demo", "user_id": None}
        member = db.get_project_member(project_id, user["id"])
        if not member:
            raise HTTPException(status_code=403, detail="You do not have access to this project")
        if role_rank.get(member["role"], 0) < role_rank.get(minimum_role, 0):
            raise HTTPException(status_code=403, detail="Insufficient project permissions")
        return member

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/auth/register")
    def auth_register(payload: AuthRegister) -> dict[str, Any]:
        try:
            return db.create_user(payload.email, payload.password, payload.name)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Could not register user") from exc

    @app.post("/auth/login")
    def auth_login(payload: AuthLogin, response: Response) -> dict[str, Any]:
        user = db.authenticate_user(payload.email, payload.password)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        session_id = db.create_session(user["id"])
        response.set_cookie("texforge_session", session_id, httponly=True, samesite="lax")
        return user

    @app.post("/auth/logout")
    def auth_logout(request: Request, response: Response) -> dict[str, bool]:
        session_id = request.cookies.get("texforge_session")
        if session_id:
            db.delete_session(session_id)
        response.delete_cookie("texforge_session")
        return {"ok": True}

    @app.get("/api/me")
    def api_me(request: Request) -> dict[str, Any]:
        user = current_user(request)
        if not user:
            return {"authenticated": False}
        return {"authenticated": True, **user}

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request) -> HTMLResponse:
        projects = db.list_projects()
        context = {
            "request": request,
            "projects": projects,
            "templates": db.list_templates(),
            "organizations": db.list_organizations(),
            "notifications": db.list_notifications(),
            "activity": db.list_activity(),
            "active_project": projects[0] if projects else None,
            "current_user": current_user(request),
            "metrics": db.admin_metrics(),
        }
        return templates.TemplateResponse(request, "dashboard.html", context)

    @app.get("/projects/{project_id}", response_class=HTMLResponse)
    def project_page(project_id: str, request: Request) -> HTMLResponse:
        try:
            project = db.get_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found") from exc
        ensure_project_access(request, project_id, "viewer")
        context = {
            "request": request,
            "project": project,
            "templates": db.list_templates(),
            "activity": db.list_activity(project_id),
            "current_user": current_user(request),
        }
        return templates.TemplateResponse(request, "project.html", context)

    @app.get("/api/projects")
    def api_projects() -> list[dict[str, Any]]:
        return db.list_projects()

    @app.get("/api/templates")
    def api_templates(q: str = "") -> dict[str, Any]:
        return {"results": db.search_templates(q)}

    @app.get("/api/templates/{slug}")
    def api_template_preview(slug: str) -> dict[str, Any]:
        try:
            return db.get_template(slug)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Template not found") from exc

    @app.post("/api/projects")
    def api_create_project(payload: ProjectCreate, request: Request) -> dict[str, Any]:
        user = current_user(request)
        owner = user["email"] if user else payload.owner
        return db.create_project(payload.name, payload.template, owner, payload.description, payload.visibility)

    @app.post("/api/projects/from-template")
    def api_create_project_from_template(payload: ProjectCreate, request: Request) -> dict[str, Any]:
        return api_create_project(payload, request)

    @app.post("/api/projects/{project_id}/files")
    def api_create_file(project_id: str, payload: FileCreate, request: Request) -> dict[str, Any]:
        try:
            db.get_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found") from exc
        ensure_project_access(request, project_id, "editor")
        return db.create_file(project_id, payload.path, payload.content)

    @app.get("/api/projects/{project_id}/files")
    def api_list_files(project_id: str, request: Request) -> list[dict[str, Any]]:
        try:
            db.get_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found") from exc
        ensure_project_access(request, project_id, "viewer")
        return db.list_project_files(project_id)

    @app.put("/api/files/{file_id}")
    def api_update_file(file_id: str, payload: FileUpdate, request: Request) -> dict[str, Any]:
        file_record = db.get_file(file_id)
        ensure_project_access(request, file_record["project_id"], "editor")
        return db.update_file(file_id, payload.content)

    @app.patch("/api/files/{file_id}/move")
    def api_move_file(file_id: str, payload: FileMoveRequest, request: Request) -> dict[str, Any]:
        file_record = db.get_file(file_id)
        ensure_project_access(request, file_record["project_id"], "editor")
        return db.move_file(file_id, payload.path)

    @app.delete("/api/files/{file_id}")
    def api_delete_file(file_id: str, request: Request) -> dict[str, Any]:
        file_record = db.get_file(file_id)
        ensure_project_access(request, file_record["project_id"], "editor")
        return db.delete_file(file_id)

    @app.post("/api/projects/{project_id}/clone")
    def api_clone_project(project_id: str, request: Request) -> dict[str, Any]:
        ensure_project_access(request, project_id, "viewer")
        return db.clone_project(project_id)

    @app.post("/api/projects/{project_id}/archive")
    def api_archive_project(project_id: str, request: Request) -> dict[str, Any]:
        ensure_project_access(request, project_id, "owner")
        return db.archive_project(project_id)

    @app.delete("/api/projects/{project_id}")
    def api_delete_project(project_id: str, request: Request) -> dict[str, Any]:
        ensure_project_access(request, project_id, "owner")
        return db.delete_project(project_id)

    @app.post("/api/projects/{project_id}/compile")
    def api_compile(project_id: str, payload: CompileRequest, request: Request) -> dict[str, Any]:
        ensure_project_access(request, project_id, "editor")
        return compile_service.compile_project(project_id, payload.engine, payload.entrypoint, payload.trigger)

    @app.get("/api/projects/{project_id}/jobs/{job_id}")
    def api_get_job(project_id: str, job_id: str, request: Request) -> dict[str, Any]:
        ensure_project_access(request, project_id, "viewer")
        return db.get_compile_job(project_id, job_id)

    @app.get("/api/projects/{project_id}/export.zip")
    def api_export(project_id: str, request: Request) -> Response:
        ensure_project_access(request, project_id, "viewer")
        data = compile_service.export_project_zip(project_id)
        return Response(data, media_type="application/zip", headers={"Content-Disposition": f"attachment; filename={project_id}.zip"})

    @app.post("/api/projects/{project_id}/snapshots")
    def api_snapshot(project_id: str, payload: SnapshotRequest, request: Request) -> dict[str, Any]:
        ensure_project_access(request, project_id, "editor")
        return db.create_snapshot(project_id, payload.file_id, payload.name)

    @app.post("/api/projects/{project_id}/snapshots/{snapshot_id}/restore")
    def api_restore_snapshot(project_id: str, snapshot_id: str, request: Request) -> dict[str, Any]:
        ensure_project_access(request, project_id, "editor")
        return db.restore_snapshot(snapshot_id)

    @app.get("/api/projects/{project_id}/diff")
    def api_diff(project_id: str, from_snapshot: str, to_snapshot: str, request: Request) -> dict[str, str]:
        ensure_project_access(request, project_id, "viewer")
        source = db.get_snapshot(from_snapshot)
        target = db.get_snapshot(to_snapshot)
        return {"diff": build_diff(source["content"], target["content"])}

    @app.post("/api/projects/{project_id}/comments")
    def api_comment(project_id: str, payload: CommentRequest, request: Request) -> dict[str, Any]:
        ensure_project_access(request, project_id, "editor")
        return db.create_comment(project_id, payload.file_id, payload.author, payload.body, payload.line_from, payload.line_to, payload.parent_id)

    @app.get("/api/projects/{project_id}/comments")
    def api_list_comments(project_id: str, request: Request) -> dict[str, Any]:
        ensure_project_access(request, project_id, "viewer")
        return {"results": db.list_comment_threads(project_id)}

    @app.post("/api/projects/{project_id}/comments/{comment_id}/resolve")
    def api_resolve_comment(project_id: str, comment_id: str, request: Request) -> dict[str, Any]:
        ensure_project_access(request, project_id, "editor")
        return db.set_comment_resolved(comment_id, True)

    @app.post("/api/projects/{project_id}/comments/{comment_id}/unresolve")
    def api_unresolve_comment(project_id: str, comment_id: str, request: Request) -> dict[str, Any]:
        ensure_project_access(request, project_id, "editor")
        return db.set_comment_resolved(comment_id, False)

    @app.get("/api/search")
    def api_search(q: str) -> dict[str, Any]:
        return {"results": db.search(q)}

    @app.post("/api/projects/{project_id}/ai/assist")
    def api_ai(project_id: str, payload: AIRequest, request: Request) -> dict[str, str]:
        ensure_project_access(request, project_id, "editor")
        return ai_assist(payload.prompt, payload.mode)

    @app.post("/api/projects/{project_id}/share-links")
    def api_share_link(project_id: str, payload: ShareLinkRequest, request: Request) -> dict[str, Any]:
        ensure_project_access(request, project_id, "owner")
        return db.create_share_link(project_id, payload.role, payload.expires_in_days)

    @app.post("/api/share/{share_id}/accept")
    def api_accept_share(share_id: str, request: Request) -> dict[str, Any]:
        user = require_login(request)
        return db.accept_share_link(share_id, user["id"])

    @app.get("/api/projects/{project_id}/members")
    def api_members(project_id: str, request: Request) -> list[dict[str, Any]]:
        ensure_project_access(request, project_id, "viewer")
        return db.list_project_members(project_id)

    @app.post("/api/projects/{project_id}/suggestions")
    def api_suggestion(project_id: str, payload: SuggestionRequest, request: Request) -> dict[str, Any]:
        ensure_project_access(request, project_id, "editor")
        return db.create_suggestion(project_id, payload.file_id, payload.author, payload.body, payload.original_text, payload.suggested_text)

    @app.post("/api/projects/{project_id}/suggestions/{suggestion_id}/accept")
    def api_accept_suggestion(project_id: str, suggestion_id: str, request: Request) -> dict[str, Any]:
        ensure_project_access(request, project_id, "editor")
        return db.accept_suggestion(suggestion_id)

    @app.post("/api/projects/{project_id}/references/import")
    def api_import_reference(project_id: str, payload: ReferenceImportRequest, request: Request) -> dict[str, Any]:
        ensure_project_access(request, project_id, "editor")
        return db.import_reference(project_id, payload.source, payload.identifier)

    @app.get("/api/projects/{project_id}/citations")
    def api_citations(project_id: str, q: str, request: Request) -> dict[str, Any]:
        ensure_project_access(request, project_id, "viewer")
        return {"results": db.search_references(project_id, q)}

    @app.post("/api/projects/{project_id}/branches")
    def api_create_branch(project_id: str, payload: BranchRequest, request: Request) -> dict[str, Any]:
        ensure_project_access(request, project_id, "editor")
        return db.create_branch(project_id, payload.snapshot_id, payload.name)

    @app.get("/api/projects/{project_id}/branches")
    def api_list_branches(project_id: str, request: Request) -> dict[str, Any]:
        ensure_project_access(request, project_id, "viewer")
        return {"results": db.list_branches(project_id)}

    @app.post("/api/projects/{project_id}/branches/{branch_id}/restore")
    def api_restore_branch(project_id: str, branch_id: str, request: Request) -> dict[str, Any]:
        ensure_project_access(request, project_id, "editor")
        return db.restore_branch(branch_id)

    @app.get("/api/admin/metrics")
    def api_admin_metrics(request: Request) -> dict[str, Any]:
        require_login(request)
        return db.admin_metrics()

    @app.get("/artifacts/{project_id}/{filename}")
    def artifact(project_id: str, filename: str, request: Request) -> FileResponse:
        ensure_project_access(request, project_id, "viewer")
        target = db.artifact_root / project_id / filename
        if not target.exists():
            raise HTTPException(status_code=404, detail="Artifact not found")
        media_type = "application/pdf" if target.suffix == ".pdf" else "text/plain"
        return FileResponse(target, media_type=media_type)

    @app.websocket("/ws/projects/{project_id}")
    async def ws_project(project_id: str, websocket: WebSocket, user: str = "anonymous") -> None:
        await hub.connect(project_id, user, websocket)
        try:
            while True:
                message = await websocket.receive_json()
                if message.get("type") == "edit":
                    try:
                        db.create_or_update_file(project_id, message["path"], message["content"])
                    except Exception:
                        pass
                    await hub.broadcast(project_id, {"type": "edit", "user": user, "path": message["path"], "content": message["content"]}, exclude=user)
                elif message.get("type") == "cursor":
                    payload = {
                        "type": "cursor",
                        "user": user,
                        "path": message.get("path", "main.tex"),
                        "line": message.get("line", 1),
                        "column": message.get("column", 1),
                    }
                    await hub.broadcast(project_id, payload, exclude=user)
                elif message.get("type") == "comment":
                    await hub.broadcast(project_id, {"type": "comment", "user": user, "body": message.get("body", "")}, exclude=user)
        except WebSocketDisconnect:
            await hub.disconnect(project_id, user)

    return app
