"""
FastAPI Web Server for MassGen Web UI

Provides WebSocket endpoints for real-time coordination updates
and serves the React frontend.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import logging.handlers
import os
import uuid
from pathlib import Path
from typing import Any

try:
    from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

from massgen.filesystem_manager._constants import (
    SKIP_DIRS_FOR_LOGGING,
    get_language_for_extension,
)
from massgen.frontend.displays.web_display import WebDisplay

# Set up logging for workspace browser debugging
workspace_logger = logging.getLogger("massgen.workspace")
workspace_logger.setLevel(logging.DEBUG)

# Create log directory and file handler for persistent debugging
_webui_log_dir = Path.home() / ".massgen" / "webui_logs"
_webui_log_dir.mkdir(parents=True, exist_ok=True)
_webui_log_file = _webui_log_dir / "workspace_browser.log"

# Create handlers if not already present
if not workspace_logger.handlers:
    # Console handler (for CLI output)
    _ws_console_handler = logging.StreamHandler()
    _ws_console_handler.setLevel(logging.INFO)  # Less verbose in console
    _ws_console_formatter = logging.Formatter(
        "[%(asctime)s] [WORKSPACE] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    _ws_console_handler.setFormatter(_ws_console_formatter)
    workspace_logger.addHandler(_ws_console_handler)

    # File handler (for detailed debugging)
    _ws_file_handler = logging.handlers.RotatingFileHandler(
        _webui_log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB max per file
        backupCount=5,  # Keep 5 backup files
        encoding="utf-8",
    )
    _ws_file_handler.setLevel(logging.DEBUG)  # Full debug in file
    _ws_file_formatter = logging.Formatter(
        "[%(asctime)s] [%(name)s] %(levelname)s: %(message)s\n" "    Location: %(pathname)s:%(lineno)d",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _ws_file_handler.setFormatter(_ws_file_formatter)
    workspace_logger.addHandler(_ws_file_handler)

    workspace_logger.info(f"WebUI logs writing to: {_webui_log_file}")

# Note: Watchdog/live file monitoring was removed for simplicity.
# File lists are now pre-fetched on connect and refreshed on-demand.
# See: specs/001-fix-workspace-browser/data-model.md

# Cache for PDF conversions (Office files converted via Docker)
# Key: (workspace_path, file_path, mtime) -> base64 PDF content
# This avoids re-converting the same file repeatedly (expensive Docker operation)
_pdf_conversion_cache: dict[tuple, str] = {}
_PDF_CACHE_MAX_SIZE = 50  # Max number of cached conversions


def _get_pdf_cache_key(workspace: str, file_path: str, mtime: float) -> tuple:
    """Generate cache key for PDF conversion."""
    return (workspace, file_path, mtime)


def _get_cached_pdf(workspace: str, file_path: str, mtime: float) -> str | None:
    """Get cached PDF conversion if available and still valid."""
    key = _get_pdf_cache_key(workspace, file_path, mtime)
    return _pdf_conversion_cache.get(key)


def _cache_pdf(workspace: str, file_path: str, mtime: float, pdf_content: str) -> None:
    """Cache a PDF conversion result."""
    # Evict oldest entries if cache is full
    if len(_pdf_conversion_cache) >= _PDF_CACHE_MAX_SIZE:
        # Remove first (oldest) entry
        oldest_key = next(iter(_pdf_conversion_cache))
        del _pdf_conversion_cache[oldest_key]

    key = _get_pdf_cache_key(workspace, file_path, mtime)
    _pdf_conversion_cache[key] = pdf_content


def _normalize_workspace_path(path: str) -> str:
    """Normalize a workspace path for consistent storage and lookup.

    Ensures paths are in a consistent format across HTTP API and WebSocket responses.
    This fixes path mismatch issues where paths may differ in:
    - Trailing slashes: "/path/to/workspace/" vs "/path/to/workspace"
    - Multiple slashes: "/path//to///workspace" vs "/path/to/workspace"

    Args:
        path: The workspace path to normalize

    Returns:
        Normalized path string without trailing slashes
    """
    import re

    if not path:
        return ""
    # Remove trailing slashes
    normalized = path.rstrip("/")
    # Collapse multiple consecutive slashes into single slash
    normalized = re.sub(r"/+", "/", normalized)
    return normalized


def _should_skip_workspace_path(file_path: Path) -> bool:
    """Check if a file path should be skipped based on excluded directory patterns.

    Uses SKIP_DIRS_FOR_LOGGING from _constants.py which includes node_modules,
    .venv, __pycache__, and other large/irrelevant directories.
    """
    import fnmatch

    for part in file_path.parts:
        if part in SKIP_DIRS_FOR_LOGGING:
            return True
        # Also check glob patterns like *.egg-info
        for pattern in SKIP_DIRS_FOR_LOGGING:
            if "*" in pattern and fnmatch.fnmatch(part, pattern):
                return True
    return False


def _should_skip_dir(dir_name: str) -> bool:
    """Check if a directory should be skipped entirely during workspace scanning.

    This is used with os.walk to skip directories BEFORE entering them,
    which is much faster than rglob + filter for large directories like node_modules.
    """
    import fnmatch

    if dir_name.startswith("."):
        return True
    if dir_name in SKIP_DIRS_FOR_LOGGING:
        return True
    # Check glob patterns like *.egg-info
    for pattern in SKIP_DIRS_FOR_LOGGING:
        if "*" in pattern and fnmatch.fnmatch(dir_name, pattern):
            return True
    return False


def _scan_workspace_files(workspace_path: Path) -> list[dict]:
    """Scan workspace for files, skipping large directories entirely.

    Uses os.walk with in-place directory filtering to avoid entering
    node_modules, .venv, and other large directories at all.
    This is much faster than rglob("*") + filter for workspaces with packages.
    """
    files = []

    for root, dirs, filenames in os.walk(workspace_path):
        # Modify dirs in-place to skip excluded directories BEFORE entering them
        dirs[:] = [d for d in dirs if not _should_skip_dir(d)]

        for filename in filenames:
            # Skip hidden files
            if filename.startswith("."):
                continue
            file_path = Path(root) / filename
            try:
                rel_path = file_path.relative_to(workspace_path)
                stat = file_path.stat()
                files.append(
                    {
                        "path": str(rel_path),
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                    },
                )
            except (OSError, ValueError):
                continue

    return files


class WorkspaceConnectionManager:
    """Manages WebSocket connections for workspace file listing.

    Note: Live file monitoring via watchdog was removed for simplicity.
    File lists are pre-fetched on connect and refreshed on-demand via
    explicit refresh requests from the frontend.
    """

    def __init__(self):
        # session_id -> set of WebSocket connections for workspace updates
        self.workspace_connections: dict[str, set[WebSocket]] = {}
        # Connection counter for logging
        self._connection_count = 0
        workspace_logger.info("WorkspaceConnectionManager initialized")

    async def connect(self, websocket: WebSocket, session_id: str, workspace_paths: list[str]) -> None:
        """Accept and register a WebSocket connection for workspace file listing.

        Scans workspace directories and sends initial file list on connect.
        No live file watching - frontend can request refresh when needed.
        """
        self._connection_count += 1
        conn_id = self._connection_count

        workspace_logger.info(
            f"[Conn #{conn_id}] WebSocket CONNECT request: session={session_id}, " f"paths={workspace_paths}",
        )

        await websocket.accept()
        workspace_logger.debug(f"[Conn #{conn_id}] WebSocket accepted")

        if session_id not in self.workspace_connections:
            self.workspace_connections[session_id] = set()
        self.workspace_connections[session_id].add(websocket)

        # Collect initial file lists from workspace paths
        watched = []
        initial_files: dict[str, list[dict]] = {}
        for path in workspace_paths:
            # Normalize path for consistent key format across HTTP and WebSocket
            normalized_path = _normalize_workspace_path(path)
            workspace_path = Path(path)
            if workspace_path.exists():
                watched.append(normalized_path)
                workspace_logger.debug(f"[Conn #{conn_id}] Path exists: {normalized_path}")

                # Collect initial file list for this workspace (non-blocking)
                try:
                    files = _scan_workspace_files(workspace_path)
                    initial_files[normalized_path] = files
                    workspace_logger.debug(
                        f"[Conn #{conn_id}] Initial files for {workspace_path.name}: {len(files)} files",
                    )
                except Exception as e:
                    workspace_logger.warning(f"[Conn #{conn_id}] Failed to scan {normalized_path}: {e}")
                    initial_files[normalized_path] = []
            else:
                workspace_logger.warning(f"[Conn #{conn_id}] Path does not exist, skipping: {path}")

        # Send connected confirmation with initial file lists
        await websocket.send_json(
            {
                "type": "workspace_connected",
                "session_id": session_id,
                "timestamp": asyncio.get_event_loop().time(),
                "watched_paths": watched,
                "initial_files": initial_files,
            },
        )

        workspace_logger.info(
            f"[Conn #{conn_id}] WebSocket CONNECTED: session={session_id}, "
            f"watching {len(watched)}/{len(workspace_paths)} paths, "
            f"total_connections={sum(len(conns) for conns in self.workspace_connections.values())}",
        )

    def disconnect(self, websocket: WebSocket, session_id: str) -> None:
        """Remove a WebSocket connection."""
        workspace_logger.info(f"WebSocket DISCONNECT: session={session_id}")

        if session_id in self.workspace_connections:
            self.workspace_connections[session_id].discard(websocket)

            # Clean up empty session entries
            if not self.workspace_connections[session_id]:
                del self.workspace_connections[session_id]
                workspace_logger.info(f"No more connections for session={session_id}")
        else:
            workspace_logger.warning(f"Disconnect called but session not found: {session_id}")

        workspace_logger.debug(
            f"After disconnect: total_connections=" f"{sum(len(conns) for conns in self.workspace_connections.values())}",
        )


# Global workspace connection manager
workspace_manager = WorkspaceConnectionManager()


class ConnectionManager:
    """Manages WebSocket connections per session."""

    def __init__(self):
        # session_id -> set of WebSocket connections
        self.active_connections: dict[str, set[WebSocket]] = {}
        # session_id -> WebDisplay instance
        self.displays: dict[str, WebDisplay] = {}
        # session_id -> orchestration task
        self.tasks: dict[str, asyncio.Task] = {}
        # session_id -> log session directory (for multi-turn continuation)
        self.session_log_dirs: dict[str, Path] = {}
        # session_id -> current turn number
        self.session_turns: dict[str, int] = {}
        # session_id -> config path used
        self.session_configs: dict[str, str] = {}
        # Completed sessions: session_id -> metadata (persists after disconnect)
        self.completed_sessions: dict[str, dict[str, Any]] = {}
        # session_id -> orchestrator instance (for cancellation)
        self.orchestrators: dict[str, Any] = {}

    def mark_session_completed(
        self,
        session_id: str,
        question: str = None,
        config: str = None,
    ) -> None:
        """Mark a session as completed so it persists in the session list."""
        import time

        self.completed_sessions[session_id] = {
            "question": question,
            "config": config,
            "completed_at": time.time(),
        }

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        """Accept and register a WebSocket connection."""
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = set()
        self.active_connections[session_id].add(websocket)

    def disconnect(self, websocket: WebSocket, session_id: str) -> None:
        """Remove a WebSocket connection."""
        if session_id in self.active_connections:
            self.active_connections[session_id].discard(websocket)
            # Clean up empty sessions
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]

    async def broadcast(self, session_id: str, message: dict[str, Any]) -> None:
        """Broadcast message to all clients in a session."""
        if session_id not in self.active_connections:
            return

        disconnected = set()
        # Take a snapshot to avoid "Set changed size during iteration" error
        # This can happen if disconnect() is called while we're broadcasting
        connections_snapshot = list(self.active_connections.get(session_id, set()))
        for websocket in connections_snapshot:
            try:
                await websocket.send_json(message)
            except Exception:
                disconnected.add(websocket)

        # Clean up disconnected clients
        if disconnected and session_id in self.active_connections:
            self.active_connections[session_id] -= disconnected

    def get_display(self, session_id: str) -> WebDisplay | None:
        """Get the WebDisplay for a session."""
        return self.displays.get(session_id)

    def create_display(
        self,
        session_id: str,
        agent_ids: list,
        agent_models: dict[str, str] | None = None,
    ) -> WebDisplay:
        """Create a new WebDisplay for a session."""

        async def broadcast_fn(message: dict[str, Any]) -> None:
            await self.broadcast(session_id, message)

        display = WebDisplay(
            agent_ids=agent_ids,
            broadcast=broadcast_fn,
            session_id=session_id,
            agent_models=agent_models,
        )
        self.displays[session_id] = display
        return display


# Global connection manager
manager = ConnectionManager()

# Default config path (set from CLI)
_default_config_path: str | None = None


def set_default_config(config_path: str | None) -> None:
    """Set the default config path for new sessions."""
    global _default_config_path
    _default_config_path = config_path


def get_default_config() -> str | None:
    """Get the default config path."""
    return _default_config_path


def create_app(
    config_path: str | None = None,
    automation_mode: bool = False,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        config_path: Default config path for coordination sessions
        automation_mode: If True, UI shows automation-friendly timeline view
    """
    if not FASTAPI_AVAILABLE:
        raise ImportError(
            "FastAPI is not installed. Install with: pip install massgen",
        )

    # Store default config
    if config_path:
        set_default_config(config_path)

    app = FastAPI(
        title="MassGen Web UI",
        description="Real-time multi-agent coordination visualization",
        version="0.1.0",
    )

    # Store automation_mode in app state for WebSocket access
    app.state.automation_mode = automation_mode

    # CORS for development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # In production, restrict this
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # =========================================================================
    # API Routes
    # =========================================================================

    @app.get("/api/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "ok", "service": "massgen-web"}

    @app.get("/api/config")
    async def get_config():
        """Get current default config path."""
        return {"config_path": get_default_config()}

    @app.get("/api/config/content")
    async def get_config_content(path: str):
        """Get the content of a config file."""
        try:
            config_path = Path(path)
            if not config_path.exists():
                return JSONResponse(
                    status_code=404,
                    content={"error": "Config file not found"},
                )
            if not config_path.is_file():
                return JSONResponse(
                    status_code=400,
                    content={"error": "Path is not a file"},
                )
            # Security: ensure path is within allowed locations
            config_path = config_path.resolve()
            allowed_paths = [
                Path.home() / ".config" / "massgen",
                Path.cwd() / ".massgen",
            ]
            try:
                import massgen

                package_dir = Path(massgen.__file__).parent
                allowed_paths.append(package_dir / "configs")
            except Exception:
                pass

            is_allowed = any(str(config_path).startswith(str(allowed.resolve())) for allowed in allowed_paths)
            if not is_allowed:
                return JSONResponse(
                    status_code=403,
                    content={"error": "Access denied"},
                )

            content = config_path.read_text(encoding="utf-8")
            return {"content": content, "path": str(config_path)}
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"error": str(e)},
            )

    @app.get("/api/configs")
    async def list_configs():
        """List all available config files."""
        configs = []
        quickstart_config = None

        # Check for project-local config at ./.massgen/ (prioritized)
        project_config_dir = Path.cwd() / ".massgen"
        if project_config_dir.exists():
            for yaml_file in sorted(project_config_dir.glob("*.yaml")) + sorted(project_config_dir.glob("*.yml")):
                entry = {
                    "name": f"{yaml_file.stem} (project)",
                    "path": str(yaml_file),
                    "category": "project",
                    "relative": yaml_file.name,
                }
                configs.append(entry)
                if quickstart_config is None:
                    quickstart_config = entry

        # Check for user's global config at ~/.config/massgen/
        user_config_dir = Path.home() / ".config" / "massgen"
        if user_config_dir.exists():
            user_yamls = sorted(user_config_dir.glob("*.yaml")) + sorted(user_config_dir.glob("*.yml"))
            for yaml_file in user_yamls:
                entry = {
                    "name": yaml_file.stem if len(user_yamls) > 1 else "Default Config",
                    "path": str(yaml_file),
                    "category": "user",
                    "relative": yaml_file.name,
                }
                configs.append(entry)
                if quickstart_config is None:
                    quickstart_config = entry

        # Get configs from massgen package
        try:
            import massgen

            package_dir = Path(massgen.__file__).parent
            configs_dir = package_dir / "configs"

            if configs_dir.exists():
                for yaml_file in configs_dir.rglob("*.yaml"):
                    # Get relative path from configs dir
                    rel_path = yaml_file.relative_to(configs_dir)
                    configs.append(
                        {
                            "name": yaml_file.stem,
                            "path": str(yaml_file),
                            "category": str(rel_path.parent) if rel_path.parent != Path(".") else "root",
                            "relative": str(rel_path),
                        },
                    )
        except Exception:
            pass

        # Sort: project first, then user, then package configs
        category_order = {"project": 0, "user": 1}

        def sort_key(x):
            return (category_order.get(x["category"], 2), x["name"])

        configs.sort(key=sort_key)

        # Default: project config > user config > CLI default
        default = quickstart_config["path"] if quickstart_config else get_default_config()

        return {
            "configs": configs,
            "default": default,
            "quickstart_config": quickstart_config["path"] if quickstart_config else None,
        }

    # =========================================================================
    # Quickstart Wizard API Routes
    # =========================================================================

    @app.get("/api/setup/status")
    async def get_setup_status():
        """Check if setup is needed (no config exists) and Docker availability."""
        from pathlib import Path

        from massgen.utils.docker_diagnostics import diagnose_docker

        # Check if default config exists
        config_path = Path.home() / ".config" / "massgen" / "config.yaml"
        has_config = config_path.exists()

        # Check Docker using diagnostics
        diagnostics = diagnose_docker()

        return {
            "needs_setup": not has_config,
            "has_config": has_config,
            "config_path": str(config_path),
            "docker_available": diagnostics.is_available,
            "docker_status": diagnostics.status.value,
            "docker_error": diagnostics.error_message if not diagnostics.is_available else None,
            "docker_resolution": diagnostics.resolution_steps if not diagnostics.is_available else None,
        }

    @app.get("/api/docker/diagnostics")
    async def get_docker_diagnostics():
        """Get comprehensive Docker diagnostics.

        Returns detailed information about Docker installation status,
        daemon availability, permissions, and installed images.
        """
        from massgen.utils.docker_diagnostics import diagnose_docker

        diagnostics = diagnose_docker()
        return diagnostics.to_dict()

    @app.get("/api/setup/env-status")
    async def get_env_status():
        """Check which .env files exist and their locations."""
        from pathlib import Path

        home_env = Path.home() / ".massgen" / ".env"
        local_env = Path.cwd() / ".env"

        return {
            "global_env": {
                "path": str(home_env),
                "exists": home_env.exists(),
            },
            "local_env": {
                "path": str(local_env),
                "exists": local_env.exists(),
            },
            "recommended": "global",
        }

    @app.post("/api/setup/api-keys")
    async def save_api_keys(request_data: dict):
        """Save API keys to .env file.

        Request body:
        {
            "keys": {
                "OPENAI_API_KEY": "sk-...",
                "ANTHROPIC_API_KEY": "sk-ant-..."
            },
            "save_location": "global" | "local"
        }

        Returns:
            {"success": true, "saved_to": "...", "saved_keys": ["OPENAI_API_KEY", ...]}
        """
        import os
        from pathlib import Path

        keys = request_data.get("keys", {})
        save_location = request_data.get("save_location", "global")

        if not keys:
            return JSONResponse(
                {"error": "No API keys provided"},
                status_code=400,
            )

        # Validate keys format (basic sanity checks)
        for key_name, key_value in keys.items():
            if not key_name or not isinstance(key_name, str):
                return JSONResponse(
                    {"error": f"Invalid key name: {key_name}"},
                    status_code=400,
                )
            if not key_value or not isinstance(key_value, str):
                return JSONResponse(
                    {"error": f"Invalid value for {key_name}"},
                    status_code=400,
                )

        # Determine save path
        if save_location == "global":
            env_dir = Path.home() / ".massgen"
            env_path = env_dir / ".env"
        else:
            env_dir = Path.cwd()
            env_path = env_dir / ".env"

        try:
            # Create directory if needed
            env_dir.mkdir(parents=True, exist_ok=True)

            # Load existing env vars if file exists
            existing_vars = {}
            if env_path.exists():
                with open(env_path) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            name, _, value = line.partition("=")
                            existing_vars[name.strip()] = value.strip().strip('"').strip("'")

            # Merge new keys (overwrite existing)
            existing_vars.update(keys)

            # Write back
            with open(env_path, "w") as f:
                f.write("# MassGen API Keys\n")
                f.write("# Generated by MassGen WebUI Setup\n\n")
                for name, value in sorted(existing_vars.items()):
                    f.write(f'{name}="{value}"\n')

            # Set file permissions (600 - owner read/write only)
            os.chmod(env_path, 0o600)

            # Reload into current environment
            for name, value in keys.items():
                os.environ[name] = value

            return {
                "success": True,
                "saved_to": str(env_path),
                "saved_keys": list(keys.keys()),
                "message": f"Saved {len(keys)} API key(s) to {env_path}",
            }

        except Exception as e:
            return JSONResponse(
                {"error": f"Failed to save API keys: {str(e)}"},
                status_code=500,
            )

    @app.post("/api/docker/pull")
    async def start_docker_pull(request_data: dict):
        """Start pulling Docker images.

        Request body:
        {
            "images": ["ghcr.io/massgen/mcp-runtime-sudo:latest"]
        }

        Returns:
            {"job_id": "uuid", "status": "started"}
        """
        images = request_data.get("images", [])

        if not images:
            return JSONResponse(
                {"error": "No images specified"},
                status_code=400,
            )

        job_id = str(uuid.uuid4())

        # Store job info for tracking
        if not hasattr(app, "_docker_pull_jobs"):
            app._docker_pull_jobs = {}

        app._docker_pull_jobs[job_id] = {
            "images": images,
            "status": "started",
            "progress": {},
            "completed": False,
            "error": None,
        }

        return {
            "job_id": job_id,
            "status": "started",
            "images": images,
        }

    @app.get("/api/docker/pull/{job_id}/stream")
    async def stream_docker_pull(job_id: str):
        """Stream Docker pull progress via Server-Sent Events.

        Returns SSE stream with progress updates.
        """
        from starlette.responses import StreamingResponse

        if not hasattr(app, "_docker_pull_jobs"):
            app._docker_pull_jobs = {}

        job = app._docker_pull_jobs.get(job_id)
        if not job:
            return JSONResponse(
                {"error": "Job not found"},
                status_code=404,
            )

        async def generate():
            import json

            try:
                import docker

                client = docker.from_env()
            except Exception as e:
                yield f"data: {json.dumps({'event': 'error', 'error': str(e)})}\n\n"
                return

            images = job["images"]

            for image in images:
                yield f"data: {json.dumps({'event': 'start', 'image': image})}\n\n"

                try:
                    # Pull with streaming progress
                    for line in client.api.pull(image, stream=True, decode=True):
                        status = line.get("status", "")
                        progress = line.get("progress", "")
                        layer_id = line.get("id", "")

                        yield f"data: {json.dumps({'event': 'progress', 'image': image, 'status': status, 'progress': progress, 'layer_id': layer_id})}\n\n"

                    yield f"data: {json.dumps({'event': 'complete', 'image': image, 'success': True})}\n\n"

                except Exception as e:
                    yield f"data: {json.dumps({'event': 'error', 'image': image, 'error': str(e)})}\n\n"

            yield f"data: {json.dumps({'event': 'done', 'all_complete': True})}\n\n"

            # Clean up job
            if job_id in app._docker_pull_jobs:
                del app._docker_pull_jobs[job_id]

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/skills")
    async def list_skills():
        """List all available skills (built-in, user-installed, and project).

        Returns skills from:
        - Built-in: massgen/skills/
        - User: ~/.agent/skills/ (home directory - where openskills installs)
        - Project: .agent/skills/ (current working directory)
        """
        from pathlib import Path

        import massgen

        skills = []
        seen_names = set()  # Track seen skill names to avoid duplicates

        def add_skills_from_dir(skills_dir: Path, location: str) -> None:
            """Helper to add skills from a directory."""
            if not skills_dir.exists():
                return

            for skill_dir in skills_dir.iterdir():
                if skill_dir.is_dir() and skill_dir.name not in seen_names:
                    skill_md = skill_dir / "SKILL.md"
                    if skill_md.exists():
                        description = ""
                        try:
                            content = skill_md.read_text()
                            lines = content.strip().split("\n")
                            for line in lines:
                                if line.strip() and not line.startswith("#") and not line.startswith("---"):
                                    description = line.strip()[:200]
                                    break
                        except Exception:
                            pass

                        skills.append(
                            {
                                "name": skill_dir.name,
                                "description": description,
                                "location": location,
                                "path": str(skill_dir),
                                "installed": True,
                            },
                        )
                        seen_names.add(skill_dir.name)

        # Find built-in skills
        massgen_path = Path(massgen.__file__).parent
        add_skills_from_dir(massgen_path / "skills", "builtin")

        # Find user-installed skills (~/.agent/skills/ - where openskills/crawl4ai install)
        add_skills_from_dir(Path.home() / ".agent" / "skills", "user")

        # Find project skills (.agent/skills/ in current directory)
        add_skills_from_dir(Path.cwd() / ".agent" / "skills", "project")

        from massgen.utils.skills_installer import check_skill_packages_installed

        return {
            "skills": skills,
            "builtin_count": len([s for s in skills if s["location"] == "builtin"]),
            "user_count": len([s for s in skills if s["location"] == "user"]),
            "project_count": len([s for s in skills if s["location"] == "project"]),
            "packages": check_skill_packages_installed(),
        }

    @app.get("/api/skills/{skill_name}")
    async def get_skill_detail(skill_name: str):
        """Get detailed information about a skill including SKILL.md content."""
        from pathlib import Path

        import massgen

        # Search in built-in skills first
        massgen_path = Path(massgen.__file__).parent
        builtin_skill = massgen_path / "skills" / skill_name

        if builtin_skill.exists():
            skill_md = builtin_skill / "SKILL.md"
            content = skill_md.read_text() if skill_md.exists() else ""
            return {
                "name": skill_name,
                "location": "builtin",
                "path": str(builtin_skill),
                "content": content,
            }

        # Search in project skills
        project_skill = Path.cwd() / ".agent" / "skills" / skill_name
        if project_skill.exists():
            skill_md = project_skill / "SKILL.md"
            content = skill_md.read_text() if skill_md.exists() else ""
            return {
                "name": skill_name,
                "location": "project",
                "path": str(project_skill),
                "content": content,
            }

        return JSONResponse(
            {"error": f"Skill '{skill_name}' not found"},
            status_code=404,
        )

    @app.post("/api/skills/install")
    async def install_skill_package(request_data: dict):
        """Install a skill package.

        Request body:
        {
            "package": "anthropic" | "openai" | "vercel" | "agent_browser" | "remotion" | "crawl4ai"
        }

        Returns:
            {"success": true, "message": "..."} or {"error": "..."}
        """
        from massgen.utils.skills_installer import (
            install_agent_browser_skill,
            install_anthropic_skills,
            install_crawl4ai_skill,
            install_openai_skills,
            install_openskills_cli,
            install_remotion_skill,
            install_vercel_skills,
        )

        package_id = request_data.get("package")

        openskills_installers = {
            "anthropic": (install_anthropic_skills, "Anthropic skills"),
            "openai": (install_openai_skills, "OpenAI skills"),
            "vercel": (install_vercel_skills, "Vercel agent skills"),
            "agent_browser": (install_agent_browser_skill, "Vercel Agent Browser skill"),
            "remotion": (install_remotion_skill, "Remotion skill"),
        }

        if package_id in openskills_installers:
            if not install_openskills_cli():
                return JSONResponse(
                    {"error": "Failed to install openskills CLI. Ensure npm/Node.js is installed."},
                    status_code=500,
                )

            installer, label = openskills_installers[package_id]
            if installer():
                return {"success": True, "message": f"{label} installed successfully"}
            return JSONResponse(
                {"error": f"Failed to install {label}"},
                status_code=500,
            )

        if package_id == "crawl4ai":
            if install_crawl4ai_skill():
                return {
                    "success": True,
                    "message": "Crawl4AI skill installed successfully",
                }
            return JSONResponse(
                {"error": "Failed to install Crawl4AI skill"},
                status_code=500,
            )

        return JSONResponse(
            {"error": f"Unknown package: {package_id}"},
            status_code=400,
        )

    @app.get("/api/providers")
    async def get_providers():
        """Get available providers with their models and API key status."""
        import os

        from massgen.backend.capabilities import BACKEND_CAPABILITIES

        providers = []
        for backend_type, caps in BACKEND_CAPABILITIES.items():
            # Skip generic/advanced backends for quickstart
            # Also skip ag2 as it's not a realistic standalone backend
            if backend_type in [
                "chatcompletion",
                "inference",
                "lmstudio",
                "vllm",
                "sglang",
                "ag2",
            ]:
                continue

            # Check if API key is available (and not a placeholder)
            has_api_key = False
            if backend_type == "claude_code":
                # Claude Code always shows - works with CLI login, CLAUDE_CODE_API_KEY, or ANTHROPIC_API_KEY
                # Mark as available but the notes will explain auth requirements
                has_api_key = True
            elif backend_type == "copilot":
                # Copilot always shows - works with gh CLI login, no API key needed
                has_api_key = True
            elif backend_type == "codex":
                # Codex always shows - works with OAuth (codex login) or OPENAI_API_KEY
                has_api_key = True
            elif caps.env_var:
                api_key = os.getenv(caps.env_var, "")
                # Check it's not empty and not a placeholder from .env.example
                # All placeholders follow pattern: your-*-key-here
                is_placeholder = api_key.lower().startswith(
                    "your-",
                ) and api_key.lower().endswith("-key-here")
                has_api_key = bool(api_key) and not is_placeholder
            else:
                # Local backends don't need keys
                has_api_key = True

            providers.append(
                {
                    "id": backend_type,
                    "name": caps.provider_name,
                    "models": caps.models,
                    "default_model": caps.default_model,
                    "env_var": caps.env_var,
                    "has_api_key": has_api_key,
                    "capabilities": list(caps.supported_capabilities),
                    "notes": caps.notes,
                },
            )

        # Sort by has_api_key (available first), then by name
        providers.sort(key=lambda p: (not p["has_api_key"], p["name"]))

        return {"providers": providers}

    @app.get("/api/providers/{provider_id}/models")
    async def get_provider_models(provider_id: str):
        """Get dynamic model list for a provider.

        For providers like OpenRouter that have many models, this fetches
        the full list from their API with caching.
        """
        from massgen.backend.capabilities import BACKEND_CAPABILITIES
        from massgen.utils.model_catalog import get_models_for_provider

        # Get static models from capabilities
        caps = BACKEND_CAPABILITIES.get(provider_id)
        static_models = caps.models if caps else []

        # For providers with dynamic model lists, fetch from API
        dynamic_providers = [
            "openrouter",
            "groq",
            "together",
            "fireworks",
            "cerebras",
            "nebius",
            "moonshot",
            "qwen",
            "poe",
            "openai",
        ]

        if provider_id in dynamic_providers:
            try:
                dynamic_models = await get_models_for_provider(
                    provider_id,
                    use_cache=True,
                )
                if dynamic_models:
                    return {
                        "provider_id": provider_id,
                        "models": dynamic_models,
                        "source": "dynamic",
                    }
            except Exception:
                pass  # Fall back to static models

        return {
            "provider_id": provider_id,
            "models": static_models,
            "source": "static",
        }

    @app.get("/api/providers/{provider_id}/capabilities")
    async def get_provider_capabilities(provider_id: str):
        """Get capabilities for a specific provider.

        Returns information about what features the provider supports,
        such as web search, code execution, etc.
        """
        from massgen.backend.capabilities import BACKEND_CAPABILITIES

        caps = BACKEND_CAPABILITIES.get(provider_id)
        if not caps:
            return JSONResponse(
                {"error": f"Unknown provider: {provider_id}"},
                status_code=404,
            )

        return {
            "provider_id": provider_id,
            "supports_web_search": "web_search" in caps.supported_capabilities,
            "supports_code_execution": "code_execution" in caps.supported_capabilities,
            "supports_mcp": "mcp" in caps.supported_capabilities,
            "builtin_tools": caps.builtin_tools,
            "filesystem_support": caps.filesystem_support,
            "all_capabilities": list(caps.supported_capabilities),
        }

    @app.post("/api/config/generate")
    async def generate_config(request_data: dict):
        """Generate a config YAML from wizard selections.

        Request body:
        {
            "agents": [
                {"id": "agent_a", "provider": "openai", "model": "gpt-4o", "enable_web_search": true},
                {"id": "agent_b", "provider": "claude", "model": "claude-sonnet-4-5-20250929", "enable_web_search": false}
            ],
            "use_docker": true,
            "context_path": "/path/to/project",  // optional
            "coordination": {  // optional
                "voting_sensitivity": "balanced",  // lenient, balanced, strict
                "answer_novelty_requirement": "lenient",  // lenient, balanced, strict
                "max_new_answers_per_agent": 5,  // optional, limit answers per agent
                "persona_generator": {  // optional, auto-generate diverse personas
                    "enabled": true
                }
            }
        }

        Returns:
            {"config": {...}, "yaml": "..."}
        """
        import yaml

        from massgen.config_builder import ConfigBuilder

        agents_config = request_data.get("agents", [])
        use_docker = request_data.get("use_docker", True)
        context_path = request_data.get("context_path")
        context_paths_raw = request_data.get("context_paths", [])
        coordination = request_data.get("coordination", {})

        # Transform frontend context_paths format to backend format
        # Frontend: {path, type: 'read'|'write'}
        # Backend: {path, permission: 'read'|'write'}
        context_paths = [{"path": cp.get("path", ""), "permission": cp.get("type", "read")} for cp in context_paths_raw if cp.get("path")] if context_paths_raw else None

        if not agents_config:
            return JSONResponse(
                {"error": "At least one agent is required"},
                status_code=400,
            )

        # Convert to format expected by _generate_quickstart_config
        formatted_agents = []
        agent_tools = {}  # Per-agent tool settings
        agent_system_messages = {}  # Per-agent system messages
        for agent in agents_config:
            agent_id = agent.get("id", f"agent_{chr(ord('a') + len(formatted_agents))}")
            formatted_agents.append(
                {
                    "id": agent_id,
                    "type": agent.get("provider", "openai"),
                    "model": agent.get("model", "gpt-4o"),
                },
            )
            # Collect per-agent tool settings
            tool_settings = {}
            if agent.get("enable_web_search") is not None:
                tool_settings["enable_web_search"] = agent.get("enable_web_search")
            if agent.get("enable_code_execution") is not None:
                tool_settings["enable_code_execution"] = agent.get(
                    "enable_code_execution",
                )
            if tool_settings:
                agent_tools[agent_id] = tool_settings
            # Collect per-agent system messages
            if agent.get("system_message"):
                agent_system_messages[agent_id] = agent.get("system_message")

        # Use ConfigBuilder to generate config
        builder = ConfigBuilder()
        config = builder._generate_quickstart_config(
            formatted_agents,
            context_path=context_path,
            context_paths=context_paths,
            use_docker=use_docker,
            agent_tools=agent_tools,
            agent_system_messages=agent_system_messages,
            coordination_settings=coordination,
        )

        # Convert to YAML string for preview
        yaml_str = yaml.dump(
            config,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )

        return {"config": config, "yaml": yaml_str}

    @app.post("/api/config/save")
    async def save_config(request_data: dict):
        """Save the generated config to a file.

        Request body:
        {
            "config": {...},  // The config object from generate_config (optional if yaml_content provided)
            "yaml_content": "...",  // Raw YAML string (optional, takes priority if provided)
            "filename": "my_config.yaml"  // Optional custom filename (defaults to config.yaml)
        }

        Returns:
            {"success": true, "path": "..."}
        """
        import re
        from pathlib import Path

        import yaml

        config = request_data.get("config")
        yaml_content = request_data.get("yaml_content")

        if not config and not yaml_content:
            return JSONResponse(
                {"error": "No config or yaml_content provided"},
                status_code=400,
            )

        # Get custom filename or use default
        filename = request_data.get("filename", "config.yaml")
        # Sanitize filename - only allow alphanumeric, underscore, dash, and .yaml extension
        if not re.match(r"^[\w\-]+\.ya?ml$", filename):
            # If invalid, sanitize it
            base_name = re.sub(
                r"[^\w\-]",
                "_",
                filename.replace(".yaml", "").replace(".yml", ""),
            )
            filename = f"{base_name}.yaml"

        # Save to user config location
        config_dir = Path.home() / ".config" / "massgen"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / filename

        try:
            with open(config_path, "w", encoding="utf-8") as f:
                if yaml_content:
                    # Write raw YAML content (user edited)
                    f.write(yaml_content)
                else:
                    # Serialize config object to YAML
                    yaml.dump(
                        config,
                        f,
                        default_flow_style=False,
                        sort_keys=False,
                        allow_unicode=True,
                    )

            return {
                "success": True,
                "path": str(config_path),
                "filename": filename,
                "message": f"Config saved to {config_path}",
            }
        except Exception as e:
            return JSONResponse(
                {"error": f"Failed to save config: {str(e)}"},
                status_code=500,
            )

    @app.get("/api/config/user-configs")
    async def list_user_configs():
        """List all user config files from ~/.config/massgen/ and ./.massgen/.

        Returns:
            {"configs": [{"name": "config.yaml", "path": "...", "modified": timestamp, "source": "global"|"project"}, ...],
             "config_dir": "...", "project_config_dir": "..."|null}
        """
        from pathlib import Path

        global_config_dir = Path.home() / ".config" / "massgen"
        project_config_dir = Path.cwd() / ".massgen"
        configs = []
        seen_paths = set()

        for config_dir, source in [(global_config_dir, "global"), (project_config_dir, "project")]:
            if not config_dir.exists():
                continue
            for pattern in ("*.yaml", "*.yml"):
                for yaml_file in config_dir.glob(pattern):
                    resolved = str(yaml_file.resolve())
                    if resolved in seen_paths:
                        continue
                    seen_paths.add(resolved)
                    stat = yaml_file.stat()
                    configs.append(
                        {
                            "name": yaml_file.name,
                            "path": str(yaml_file),
                            "modified": stat.st_mtime,
                            "size": stat.st_size,
                            "source": source,
                        },
                    )

        # Sort: project configs first, then by modification time (newest first)
        configs.sort(key=lambda x: (x["source"] != "project", -x["modified"]))

        return {
            "configs": configs,
            "config_dir": str(global_config_dir),
            "project_config_dir": str(project_config_dir) if project_config_dir.exists() else None,
        }

    @app.put("/api/config/update")
    async def update_config(request_data: dict):
        """Update an existing config file with new content.

        Request body:
        {
            "path": "/path/to/config.yaml",  // Full path to the config file
            "content": "yaml content string"  // New YAML content
        }

        Returns:
            {"success": true, "path": "..."}
        """
        from pathlib import Path

        import yaml

        config_path = request_data.get("path")
        content = request_data.get("content")

        if not config_path:
            return JSONResponse(
                {"error": "No path provided"},
                status_code=400,
            )

        if content is None:
            return JSONResponse(
                {"error": "No content provided"},
                status_code=400,
            )

        config_path = Path(config_path).resolve()

        # Security: ensure path is within allowed locations
        allowed_paths = [
            Path.home() / ".config" / "massgen",
        ]
        is_allowed = any(str(config_path).startswith(str(allowed.resolve())) for allowed in allowed_paths)
        if not is_allowed:
            return JSONResponse(
                {"error": "Access denied: can only edit configs in ~/.config/massgen/"},
                status_code=403,
            )

        # Validate YAML syntax before saving
        try:
            yaml.safe_load(content)
        except yaml.YAMLError as e:
            return JSONResponse(
                {"error": f"Invalid YAML syntax: {str(e)}"},
                status_code=400,
            )

        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(content)

            return {
                "success": True,
                "path": str(config_path),
                "message": f"Config updated: {config_path}",
            }
        except Exception as e:
            return JSONResponse(
                {"error": f"Failed to save config: {str(e)}"},
                status_code=500,
            )

    @app.post("/api/config/rename")
    async def rename_config(request_data: dict):
        """Rename a config file.

        Request body:
        {
            "path": "/path/to/old_config.yaml",
            "new_name": "new_config.yaml"
        }

        Returns:
            {"success": true, "old_path": "...", "new_path": "..."}
        """
        import re
        from pathlib import Path

        old_path = request_data.get("path")
        new_name = request_data.get("new_name")

        if not old_path:
            return JSONResponse(
                {"error": "No path provided"},
                status_code=400,
            )

        if not new_name:
            return JSONResponse(
                {"error": "No new name provided"},
                status_code=400,
            )

        old_path = Path(old_path).resolve()

        # Security: ensure path is within allowed locations
        allowed_paths = [
            Path.home() / ".config" / "massgen",
        ]
        is_allowed = any(str(old_path).startswith(str(allowed.resolve())) for allowed in allowed_paths)
        if not is_allowed:
            return JSONResponse(
                {
                    "error": "Access denied: can only rename configs in ~/.config/massgen/",
                },
                status_code=403,
            )

        if not old_path.exists():
            return JSONResponse(
                {"error": "Config file not found"},
                status_code=404,
            )

        # Sanitize new filename
        if not re.match(r"^[\w\-]+\.ya?ml$", new_name):
            base_name = re.sub(
                r"[^\w\-]",
                "_",
                new_name.replace(".yaml", "").replace(".yml", ""),
            )
            new_name = f"{base_name}.yaml"

        new_path = old_path.parent / new_name

        if new_path.exists():
            return JSONResponse(
                {"error": f"A config with name '{new_name}' already exists"},
                status_code=409,
            )

        try:
            old_path.rename(new_path)
            return {
                "success": True,
                "old_path": str(old_path),
                "new_path": str(new_path),
                "new_name": new_name,
                "message": f"Config renamed to {new_name}",
            }
        except Exception as e:
            return JSONResponse(
                {"error": f"Failed to rename config: {str(e)}"},
                status_code=500,
            )

    @app.delete("/api/config/delete")
    async def delete_config(path: str):
        """Delete a config file.

        Query params:
            path: Full path to the config file to delete

        Returns:
            {"success": true, "path": "..."}
        """
        from pathlib import Path

        if not path:
            return JSONResponse(
                {"error": "No path provided"},
                status_code=400,
            )

        config_path = Path(path).resolve()

        # Security: ensure path is within allowed locations
        allowed_paths = [
            Path.home() / ".config" / "massgen",
            Path.cwd() / ".massgen",
        ]
        is_allowed = any(str(config_path).startswith(str(allowed.resolve())) for allowed in allowed_paths)
        if not is_allowed:
            return JSONResponse(
                {
                    "error": "Access denied: can only delete configs in ~/.config/massgen/ or ./.massgen/",
                },
                status_code=403,
            )

        if not config_path.exists():
            return JSONResponse(
                {"error": "Config file not found"},
                status_code=404,
            )

        # Don't allow deleting the last config (count across both dirs)
        total_configs = 0
        for d in allowed_paths:
            if d.exists():
                total_configs += len(list(d.glob("*.yaml"))) + len(list(d.glob("*.yml")))
        if total_configs <= 1:
            return JSONResponse(
                {"error": "Cannot delete the last config file"},
                status_code=400,
            )

        try:
            config_path.unlink()
            return {
                "success": True,
                "path": str(config_path),
                "message": f"Config deleted: {config_path.name}",
            }
        except Exception as e:
            return JSONResponse(
                {"error": f"Failed to delete config: {str(e)}"},
                status_code=500,
            )

    @app.get("/api/sessions")
    async def list_sessions():
        """List all active and completed sessions."""
        sessions = []
        # Active sessions (with WebSocket connections)
        for session_id in manager.active_connections.keys():
            display = manager.get_display(session_id)
            task = manager.tasks.get(session_id)

            sessions.append(
                {
                    "session_id": session_id,
                    "connections": len(
                        manager.active_connections.get(session_id, set()),
                    ),
                    "has_display": display is not None,
                    "is_running": task is not None and not task.done() if task else False,
                    "question": display.question if display and hasattr(display, "question") else None,
                    "status": "active",
                },
            )

        # Completed sessions (no longer connected but preserved)
        for session_id, metadata in manager.completed_sessions.items():
            # Skip if already in active list
            if session_id in manager.active_connections:
                continue
            sessions.append(
                {
                    "session_id": session_id,
                    "connections": 0,
                    "has_display": False,
                    "is_running": False,
                    "question": metadata.get("question"),
                    "status": "completed",
                    "completed_at": metadata.get("completed_at"),
                },
            )

        return {"sessions": sessions}

    @app.post("/api/sessions")
    async def create_session():
        """Create a new coordination session."""
        session_id = str(uuid.uuid4())
        return JSONResponse({"session_id": session_id})

    @app.get("/api/workspace/{session_id}/{agent_id}")
    async def get_workspace_files(session_id: str, agent_id: str):
        """Get workspace files for an agent.

        Returns files from the agent's current workspace directory.
        """
        display = manager.get_display(session_id)
        if display is None:
            return JSONResponse(
                {"error": "Session not found", "files": []},
                status_code=404,
            )

        # Try to get workspace path from status.json first (more reliable during active coordination)
        agent_workspace = None
        if display.log_session_dir:
            try:
                import json

                from massgen.logger_config import get_log_session_dir

                log_dir = get_log_session_dir()
                if log_dir:
                    status_file = log_dir / "status.json"
                    if status_file.exists():
                        with open(status_file) as f:
                            status_data = json.load(f)

                        # Get workspace path from status.json
                        agents_data = status_data.get("agents", {})
                        agent_data = agents_data.get(agent_id, {})
                        workspace_paths = agent_data.get("workspace_paths", {})
                        workspace_str = workspace_paths.get("workspace")

                        if workspace_str:
                            agent_workspace = Path(workspace_str)
            except Exception as e:
                print(f"[WebUI] Warning: Could not read workspace path from status.json: {e}")

        # Fall back to display workspace path or default pattern
        if not agent_workspace:
            workspace_path = getattr(display, "_workspace_path", None)
            if workspace_path:
                agent_workspace = Path(workspace_path) / agent_id
            else:
                # Fall back to default workspace pattern
                agent_workspace = Path.cwd() / f"workspace_{agent_id}"

        files = []
        if agent_workspace and agent_workspace.exists():
            try:
                # Use iterdir with limit instead of rglob to avoid scanning huge trees
                # Limit to first 1000 files to prevent timeout
                file_count = 0
                max_files = 1000

                def scan_directory(directory: Path, max_depth: int = 10, current_depth: int = 0):
                    """Recursively scan directory with depth limit and file count limit."""
                    nonlocal file_count

                    if current_depth > max_depth or file_count >= max_files:
                        return

                    try:
                        for item in directory.iterdir():
                            if file_count >= max_files:
                                break

                            if item.is_file():
                                rel_path = item.relative_to(agent_workspace)
                                stat = item.stat()
                                files.append(
                                    {
                                        "path": str(rel_path),
                                        "size": stat.st_size,
                                        "modified": stat.st_mtime,
                                        "operation": "create",
                                    },
                                )
                                file_count += 1
                            elif item.is_dir():
                                # Skip hidden directories and common ignore patterns
                                if not item.name.startswith(".") and item.name not in ["__pycache__", "node_modules", ".git"]:
                                    scan_directory(item, max_depth, current_depth + 1)
                    except PermissionError:
                        pass  # Skip directories we can't read

                scan_directory(agent_workspace)

                if file_count >= max_files:
                    print(f"[WebUI] Warning: File limit reached for {agent_id} workspace. Showing first {max_files} files.")

            except Exception as e:
                return JSONResponse(
                    {"error": str(e), "files": []},
                    status_code=500,
                )

        return {"files": files, "workspace_path": str(agent_workspace) if agent_workspace else None}

    @app.get("/api/workspaces")
    async def list_workspaces(session_id: str = None):
        """List all available workspaces for the current session.

        IMPORTANT: This endpoint ONLY reads from status.json per FR-011.
        No filesystem scanning fallback is performed.

        Args:
            session_id: Session ID for reading workspace paths from status.json.
                       If not provided or status.json unavailable, returns an error.

        Returns:
        - current: Workspaces for the current session (from status.json)
        - historical: Empty (historical workspaces require explicit log_dir via /api/sessions/{id}/answer-workspaces)

        Raises:
        - 400 if session_id not provided
        - 503 if status.json unavailable
        """
        if not session_id:
            return JSONResponse(
                {"error": "session_id is required", "current": [], "historical": []},
                status_code=400,
            )

        workspaces = {
            "current": [],
            "historical": [],
        }

        # Read workspace paths from status.json ONLY (per FR-011)
        try:
            # Try to get log_session_dir from the display (most reliable during active session)
            display = manager.get_display(session_id)
            log_session_dir = getattr(display, "log_session_dir", None) if display else None

            # Fallback to global logger (works when called from same process)
            if not log_session_dir:
                from massgen.logger_config import get_log_session_dir

                log_session_dir = get_log_session_dir()

            if not log_session_dir:
                return JSONResponse(
                    {
                        "error": "Session log directory not found. status.json unavailable.",
                        "current": [],
                        "historical": [],
                    },
                    status_code=503,
                )

            status_file = Path(log_session_dir) / "status.json"
            if not status_file.exists():
                return JSONResponse(
                    {
                        "error": "status.json not found. Session may not have started yet.",
                        "current": [],
                        "historical": [],
                    },
                    status_code=503,
                )

            with open(status_file) as f:
                status_data = json.load(f)

            agents_data = status_data.get("agents", {})
            for agent_id, agent_info in agents_data.items():
                workspace_paths = agent_info.get("workspace_paths", {})
                workspace_path = workspace_paths.get("workspace")
                if workspace_path and Path(workspace_path).exists():
                    # Normalize path for consistent format across HTTP and WebSocket
                    normalized_path = _normalize_workspace_path(workspace_path)
                    workspaces["current"].append(
                        {
                            "name": Path(workspace_path).name,
                            "path": normalized_path,
                            "type": "current",
                            "agentId": agent_id,
                        },
                    )

            return workspaces

        except json.JSONDecodeError as e:
            return JSONResponse(
                {
                    "error": f"status.json is corrupted: {e}",
                    "current": [],
                    "historical": [],
                },
                status_code=503,
            )
        except Exception as e:
            return JSONResponse(
                {
                    "error": f"Failed to read workspaces from status.json: {e}",
                    "current": [],
                    "historical": [],
                },
                status_code=503,
            )

    @app.get("/api/workspace/browse")
    async def browse_workspace(path: str):
        """Browse files in a specific workspace path.

        Args:
            path: Absolute path to workspace directory
        """
        import time as time_module

        request_start = time_module.time()
        workspace_path = Path(path)

        workspace_logger.info(f"BROWSE request: path={path}")

        if not workspace_path.exists():
            workspace_logger.warning(f"BROWSE 404: workspace not found: {path}")
            return JSONResponse(
                {"error": "Workspace not found", "files": []},
                status_code=404,
            )

        if not workspace_path.is_dir():
            workspace_logger.warning(f"BROWSE 400: path is not a directory: {path}")
            return JSONResponse(
                {"error": "Path is not a directory", "files": []},
                status_code=400,
            )

        workspace_mtime = workspace_path.stat().st_mtime
        try:
            files = _scan_workspace_files(workspace_path)
            # Add operation field for browse endpoint
            for f in files:
                f["operation"] = "create"
        except Exception as e:
            workspace_logger.error(f"BROWSE 500: error scanning {path}: {e}")
            return JSONResponse(
                {"error": str(e), "files": []},
                status_code=500,
            )

        duration_ms = (time_module.time() - request_start) * 1000
        workspace_logger.info(
            f"BROWSE complete: path={workspace_path.name}, " f"files={len(files)}, duration={duration_ms:.1f}ms",
        )

        return {
            "files": files,
            # Normalize path for consistent format across HTTP and WebSocket
            "workspace_path": _normalize_workspace_path(str(workspace_path)),
            "workspace_mtime": workspace_mtime,
        }

    @app.get("/api/sessions/{session_id}/status")
    async def get_session_status(session_id: str, log_dir: str = None):
        """Get session status.json with workspace paths and agent information."""
        import json

        from massgen.logger_config import get_log_session_dir

        display = manager.get_display(session_id)

        # Determine log session dir
        if log_dir:
            log_session_dir = Path(log_dir).resolve()
        elif display and getattr(display, "log_session_dir", None):
            log_session_dir = Path(display.log_session_dir).resolve()
        else:
            log_session_dir = get_log_session_dir()

        # Look for status.json in various locations
        status_paths = []
        if log_session_dir and log_session_dir.exists():
            # Direct status.json
            direct_status = log_session_dir / "status.json"
            if direct_status.exists():
                status_paths.append(direct_status)

            # Look in turn_X/attempt_Y subdirectories
            for turn_dir in log_session_dir.glob("turn_*"):
                if turn_dir.is_dir():
                    turn_status = turn_dir / "status.json"
                    if turn_status.exists():
                        status_paths.append(turn_status)

                    for attempt_dir in turn_dir.glob("attempt_*"):
                        if attempt_dir.is_dir():
                            attempt_status = attempt_dir / "status.json"
                            if attempt_status.exists():
                                status_paths.append(attempt_status)

        # Return the most recent status.json (based on path depth and modification time)
        if status_paths:
            # Sort by modification time, most recent first
            status_paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            status_file = status_paths[0]

            try:
                with open(status_file) as f:
                    status_data = json.load(f)

                return {
                    "status": status_data,
                    "status_file": str(status_file),
                    "log_dir_used": str(log_session_dir) if log_session_dir else "",
                }
            except Exception as e:
                return JSONResponse(
                    {"error": f"Failed to read status.json: {e}", "status": None},
                    status_code=500,
                )

        return {
            "status": None,
            "status_file": None,
            "log_dir_used": str(log_session_dir) if log_session_dir else "",
            "error": "No status.json found",
        }

    @app.get("/api/sessions/{session_id}/answer-workspaces")
    async def get_answer_workspaces(session_id: str, log_dir: str = None):
        """Get workspaces linked to specific answer versions.

        Uses status.json as the single source of truth:
        - agents.{id}.workspace_paths.workspace for current workspaces
        - historical_workspaces for historical answer snapshots

        Falls back to directory scanning only if status.json is unavailable.
        """
        from massgen.logger_config import get_log_session_dir

        display = manager.get_display(session_id)
        agent_ids = display.agent_ids if display else []

        workspaces = []
        cwd = Path.cwd()
        sources = []

        # Determine log session dir
        log_session_dir = None
        if log_dir:
            log_session_dir = Path(log_dir).resolve()
        elif display and getattr(display, "log_session_dir", None):
            log_session_dir = Path(display.log_session_dir).resolve()
        else:
            log_session_dir = get_log_session_dir()

        # PRIMARY SOURCE: Read from status.json
        status_data = None
        try:
            status_response = await get_session_status(session_id, log_dir)
            status_data = status_response.get("status")
        except Exception as e:
            print(f"[WARNING] Failed to get status.json: {e}")

        if status_data:
            # Extract historical workspaces (answer snapshots)
            if "historical_workspaces" in status_data:
                for ws_data in status_data["historical_workspaces"]:
                    workspace_path = ws_data.get("workspacePath")
                    if workspace_path and Path(workspace_path).exists():
                        workspaces.append(
                            {
                                "answerId": ws_data.get("answerId"),
                                "agentId": ws_data.get("agentId"),
                                "answerNumber": ws_data.get("answerNumber", 1),
                                "answerLabel": ws_data.get("answerLabel"),
                                "timestamp": ws_data.get("timestamp", ""),
                                "workspacePath": workspace_path,
                            },
                        )
                if workspaces:
                    sources.append("status_json")

        # FALLBACK: Directory scanning if no status.json data
        if not workspaces and log_session_dir and log_session_dir.exists():
            # Helper to scan a directory for agent workspaces
            # Only includes directories that have answer.txt (not update_message.txt or vote.json)
            def scan_for_workspaces(base_dir: Path):
                found = []
                agent_dirs = [p for p in base_dir.iterdir() if p.is_dir() and p.name.startswith("agent_")]
                for agent_dir in agent_dirs:
                    agent_id = agent_dir.name
                    agent_index = (agent_ids.index(agent_id) + 1) if agent_id in agent_ids else 0
                    answer_count = 0
                    for ts_dir in sorted(agent_dir.iterdir(), key=lambda x: x.name):
                        ws_path = ts_dir / "workspace"
                        answer_file = ts_dir / "answer.txt"
                        # Only include if both workspace dir AND answer.txt exist
                        if ts_dir.is_dir() and ws_path.exists() and answer_file.exists():
                            answer_count += 1
                            found.append(
                                {
                                    "answerId": f"{agent_id}-{ts_dir.name}",
                                    "agentId": agent_id,
                                    "answerNumber": answer_count,
                                    "answerLabel": f"agent{agent_index}.{answer_count}",
                                    "timestamp": ts_dir.name,
                                    "workspacePath": str(ws_path),
                                },
                            )
                return found

            # Try direct agent_* directories first
            workspaces = scan_for_workspaces(log_session_dir)

            # If not found, try turn_*/attempt_* subdirectories
            if not workspaces:
                for turn_dir in sorted(log_session_dir.glob("turn_*")):
                    for attempt_dir in sorted(turn_dir.glob("attempt_*")):
                        workspaces = scan_for_workspaces(attempt_dir)
                        if workspaces:
                            break
                    if workspaces:
                        break

            if workspaces:
                sources.append("log_dir_scan")

            # Also scan for final/ directories (winner's workspace after consensus)
            def scan_for_final_workspaces(base_dir: Path):
                found = []
                final_dir = base_dir / "final"
                if final_dir.exists() and final_dir.is_dir():
                    for agent_dir in final_dir.iterdir():
                        if agent_dir.is_dir() and agent_dir.name.startswith("agent_"):
                            agent_id = agent_dir.name
                            ws_path = agent_dir / "workspace"
                            if ws_path.exists():
                                found.append(
                                    {
                                        "answerId": f"{agent_id}-final",
                                        "agentId": agent_id,
                                        "answerNumber": 0,  # 0 indicates final
                                        "answerLabel": "Final",
                                        "timestamp": "final",
                                        "workspacePath": str(ws_path),
                                    },
                                )
                return found

            # Try to find final workspaces in log_session_dir
            final_workspaces = scan_for_final_workspaces(log_session_dir)

            # If not found, try turn_*/attempt_* subdirectories
            if not final_workspaces:
                for turn_dir in sorted(log_session_dir.glob("turn_*")):
                    for attempt_dir in sorted(turn_dir.glob("attempt_*")):
                        final_workspaces = scan_for_final_workspaces(attempt_dir)
                        if final_workspaces:
                            break
                    if final_workspaces:
                        break

            if final_workspaces:
                workspaces.extend(final_workspaces)
                sources.append("final_scan")

        # Include current workspaces from cwd
        current = []
        for path in cwd.iterdir():
            if path.is_dir() and path.name.startswith("workspace"):
                current.append(
                    {
                        "name": path.name,
                        "path": str(path),
                        "type": "current",
                    },
                )
        if current:
            sources.append("cwd_current")

        return {
            "workspaces": workspaces,
            "current": current,
            "sources": sources,
            "log_dir_used": str(log_session_dir) if log_session_dir else "",
        }

    @app.get("/api/workspace/file")
    async def get_file_content(path: str, workspace: str):
        """Get the content of a specific file from a workspace.

        Args:
            path: Relative path to file within workspace
            workspace: Absolute path to workspace directory

        Returns:
            {
                "content": str,           # File content (text files)
                "binary": bool,           # True if binary file
                "size": int,              # File size in bytes
                "mimeType": str,          # Detected MIME type
                "language": str,          # Programming language for syntax highlighting
            }
        """
        import mimetypes
        import re
        import time as time_module
        from urllib.parse import unquote

        request_start = time_module.time()

        # Normalize paths to fix 404 issues from path format inconsistencies
        # Handle URL encoding, trailing slashes, and multiple slashes
        workspace = unquote(workspace).rstrip("/")
        workspace = re.sub(r"/+", "/", workspace)
        path = unquote(path).lstrip("/")
        path = re.sub(r"/+", "/", path)

        workspace_logger.info(f"FILE request: path={path}, workspace={workspace}")

        # Handle both absolute and relative workspace paths
        workspace_path = Path(workspace)
        if not workspace_path.is_absolute():
            # Relative paths are relative to the MassGen project root
            massgen_root = Path(__file__).parent.parent.parent.parent
            workspace_path = massgen_root / workspace
        workspace_path = workspace_path.resolve()

        workspace_logger.debug(f"FILE resolved workspace: {workspace_path}")
        file_path = (workspace_path / path).resolve()

        # Security: Ensure file is within workspace (prevent directory traversal)
        try:
            file_path.relative_to(workspace_path)
        except ValueError:
            workspace_logger.warning(f"FILE 403: path traversal attempt: {path}")
            return JSONResponse(
                {"error": "Access denied: path outside workspace"},
                status_code=403,
            )

        if not file_path.exists():
            workspace_logger.warning(f"FILE 404: file not found: {path} in {workspace}")
            return JSONResponse(
                {"error": "File not found"},
                status_code=404,
            )

        if not file_path.is_file():
            workspace_logger.warning(f"FILE 400: not a file: {path}")
            return JSONResponse(
                {"error": "Path is not a file"},
                status_code=400,
            )

        # Get file stats
        stat = file_path.stat()
        size = stat.st_size

        # Get file extension for MIME type and language detection
        suffix = file_path.suffix.lower()

        # Detect MIME type with fallbacks for common types that mimetypes may not know
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if mime_type is None:
            # Fallback mappings for types that Python's mimetypes may not recognize
            mime_fallbacks = {
                ".md": "text/markdown",
                ".markdown": "text/markdown",
                ".mmd": "text/plain",  # Mermaid diagrams
                ".mermaid": "text/plain",
                ".yaml": "text/yaml",
                ".yml": "text/yaml",
                ".toml": "text/plain",
                ".env": "text/plain",
                ".tsx": "text/typescript",
                ".jsx": "text/javascript",
            }
            mime_type = mime_fallbacks.get(suffix, "application/octet-stream")

        # Get language from shared constants (EXTENSION_TO_LANGUAGE)
        language = get_language_for_extension(suffix)

        # Special case for Dockerfile without extension
        if file_path.name.lower() == "dockerfile":
            language = "dockerfile"

        # Check if binary by mime type first, then by content
        # Known binary mime type prefixes
        binary_mime_prefixes = (
            "image/",
            "audio/",
            "video/",
            "application/pdf",
            "application/zip",
            "application/x-tar",
            "application/gzip",
            "application/octet-stream",
            "application/vnd.",  # Office documents, etc.
        )

        try:
            with open(file_path, "rb") as f:
                chunk = f.read(8192)

            # Check for null bytes OR known binary mime types
            # PNG files don't have null bytes in header, so we need mime check
            is_binary = b"\x00" in chunk or any(mime_type.startswith(prefix) for prefix in binary_mime_prefixes)

            if is_binary:
                # For binary files, read and base64 encode the content
                # Limit binary files to 50MB (increased from 10MB for large presentations/PDFs)
                max_binary_size = 50 * 1024 * 1024
                if size > max_binary_size:
                    return {
                        "content": "",
                        "binary": True,
                        "size": size,
                        "mimeType": mime_type,
                        "language": language,
                        "error": f"File too large for preview ({size} bytes, max {max_binary_size})",
                    }

                with open(file_path, "rb") as f:
                    binary_content = f.read()

                duration_ms = (time_module.time() - request_start) * 1000
                workspace_logger.info(
                    f"FILE complete: {path}, size={size}, binary=True, duration={duration_ms:.1f}ms",
                )
                return {
                    "content": base64.b64encode(binary_content).decode("utf-8"),
                    "binary": True,
                    "size": size,
                    "mimeType": mime_type,
                    "language": language,
                }

            # Read full content for text files (limit to 1MB)
            max_size = 1024 * 1024  # 1MB
            if size > max_size:
                with open(file_path, encoding="utf-8", errors="replace") as f:
                    content = f.read(max_size)
                content += f"\n\n... (truncated, file is {size} bytes)"
            else:
                with open(file_path, encoding="utf-8", errors="replace") as f:
                    content = f.read()

            duration_ms = (time_module.time() - request_start) * 1000
            workspace_logger.info(
                f"FILE complete: {path}, size={size}, binary=False, duration={duration_ms:.1f}ms",
            )
            return {
                "content": content,
                "binary": False,
                "size": size,
                "mimeType": mime_type,
                "language": language,
            }

        except Exception as e:
            workspace_logger.error(f"FILE 500: failed to read {path}: {e}")
            return JSONResponse(
                {"error": f"Failed to read file: {str(e)}"},
                status_code=500,
            )

    @app.get("/workspace-preview/{session_id}/{agent_id}/{file_path:path}")
    async def serve_workspace_preview(
        session_id: str,
        agent_id: str,
        file_path: str,
        workspace: str = None,  # Optional: direct workspace path for historical workspaces
    ):
        """Serve workspace files directly for HTML preview with working relative links.

        This endpoint serves files from an agent's workspace at a stable URL path,
        allowing relative links in HTML files to work correctly.

        Security:
        - Validates session_id exists
        - Gets workspace path from status.json (trusted source) or query param
        - Prevents directory traversal attacks
        - Only serves files within the workspace

        Args:
            session_id: Active session ID
            agent_id: Agent ID (e.g., "agent_a")
            file_path: Relative path within workspace (e.g., "index.html" or "about/index.html")
            workspace: Optional direct workspace path (for historical workspaces)

        Returns:
            FileResponse with appropriate content type
        """
        import mimetypes

        from starlette.responses import FileResponse

        # Default to index.html if no file specified or path ends with /
        if not file_path or file_path.endswith("/"):
            file_path = file_path.rstrip("/") + "/index.html" if file_path else "index.html"

        # Get workspace path - prefer query param for historical workspaces
        workspace_path = None

        # First, try the explicit workspace parameter (for historical workspaces)
        if workspace:
            explicit_path = Path(workspace)
            if explicit_path.exists() and explicit_path.is_dir():
                workspace_path = explicit_path

        # If not provided or invalid, try status.json
        if not workspace_path:
            try:
                # Try to get workspace from display's status.json
                display = manager.get_display(session_id)
                log_session_dir = getattr(display, "log_session_dir", None) if display else None

                # Fallback to global logger
                if not log_session_dir:
                    from massgen.logger_config import get_log_session_dir

                    log_session_dir = get_log_session_dir()

                if log_session_dir:
                    status_file = log_session_dir / "status.json"
                    if status_file.exists():
                        with open(status_file) as f:
                            status_data = json.load(f)

                        agents_data = status_data.get("agents", {})
                        agent_data = agents_data.get(agent_id, {})
                        workspace_paths = agent_data.get("workspace_paths", {})
                        workspace_str = workspace_paths.get("workspace")
                        if workspace_str:
                            workspace_path = Path(workspace_str)
            except Exception as e:
                print(f"[WebUI] Warning: Could not get workspace path from status.json: {e}")

        # Fallback: Try common workspace patterns
        if not workspace_path or not workspace_path.exists():
            cwd = Path.cwd()
            # Try workspace{N} pattern based on agent index
            agent_match = agent_id.replace("agent_", "")
            agent_index = ord(agent_match[0]) - ord("a") + 1 if agent_match and agent_match[0].isalpha() else 1
            fallback_path = cwd / f"workspace{agent_index}"
            if fallback_path.exists():
                workspace_path = fallback_path

        if not workspace_path or not workspace_path.exists():
            return JSONResponse(
                {"error": f"Workspace not found for agent {agent_id}"},
                status_code=404,
            )

        # Resolve the full file path
        workspace_path = workspace_path.resolve()
        full_file_path = (workspace_path / file_path).resolve()

        # Security: Ensure file is within workspace (prevent directory traversal)
        try:
            full_file_path.relative_to(workspace_path)
        except ValueError:
            return JSONResponse(
                {"error": "Access denied: path outside workspace"},
                status_code=403,
            )

        # If path is a directory, try index.html
        if full_file_path.is_dir():
            full_file_path = full_file_path / "index.html"

        if not full_file_path.exists():
            return JSONResponse(
                {"error": f"File not found: {file_path}"},
                status_code=404,
            )

        if not full_file_path.is_file():
            return JSONResponse(
                {"error": "Path is not a file"},
                status_code=400,
            )

        # Determine content type
        mime_type, _ = mimetypes.guess_type(str(full_file_path))
        mime_type = mime_type or "application/octet-stream"

        # For HTML files, inject a <base> tag and rewrite root-relative links
        # so navigation works within the workspace preview
        if mime_type == "text/html":
            import re

            from starlette.responses import HTMLResponse

            try:
                html_content = full_file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                html_content = full_file_path.read_text(encoding="latin-1")

            # Build the base URL for this workspace
            base_url = f"/workspace-preview/{session_id}/{agent_id}/"

            # Rewrite root-relative links (href="/about") to workspace-relative
            # This handles links like <a href="/about"> -> <a href="/workspace-preview/.../about">
            def rewrite_root_relative(match):
                attr = match.group(1)  # href or src
                path = match.group(2)  # the path starting with /
                # Don't rewrite if it's already our workspace-preview path
                if path.startswith("/workspace-preview/"):
                    return match.group(0)
                # Rewrite to workspace-relative path
                return f'{attr}="{base_url}{path.lstrip("/")}"'

            # Match href="/..." or src="/..." (root-relative paths)
            html_content = re.sub(
                r'(href|src)="(/[^"]*)"',
                rewrite_root_relative,
                html_content,
                flags=re.IGNORECASE,
            )
            # Also handle single quotes
            html_content = re.sub(
                r"(href|src)='(/[^']*)'",
                lambda m: f"{m.group(1)}='{base_url}{m.group(2).lstrip('/')}'",
                html_content,
                flags=re.IGNORECASE,
            )

            # Inject <base> tag for truly relative links (./about, about, etc.)
            # This goes right after <head> to ensure it applies to all resources
            if "<head>" in html_content.lower():
                # Find <head> case-insensitively and inject base tag after it
                head_match = re.search(r"<head[^>]*>", html_content, re.IGNORECASE)
                if head_match:
                    insert_pos = head_match.end()
                    base_tag = f'\n<base href="{base_url}">\n'
                    html_content = html_content[:insert_pos] + base_tag + html_content[insert_pos:]
            elif "<html" in html_content.lower():
                # No <head>, inject after <html>
                html_match = re.search(r"<html[^>]*>", html_content, re.IGNORECASE)
                if html_match:
                    insert_pos = html_match.end()
                    base_tag = f'\n<head><base href="{base_url}"></head>\n'
                    html_content = html_content[:insert_pos] + base_tag + html_content[insert_pos:]
            else:
                # No HTML structure, prepend base tag
                html_content = f'<base href="{base_url}">\n' + html_content

            return HTMLResponse(content=html_content, media_type="text/html")

        return FileResponse(
            path=full_file_path,
            media_type=mime_type,
            filename=full_file_path.name,
        )

    @app.post("/api/convert/document")
    async def convert_document_to_pdf(request: Request):
        """Convert DOCX/PPTX/XLSX to PDF using the MassGen Docker container.

        This endpoint uses LibreOffice inside the MassGen container to convert
        Office documents to PDF format for preview in the webui.

        Request body:
            {
                "path": str,        # Relative path to file within workspace
                "workspace": str,   # Absolute path to workspace directory
            }

        Returns:
            {
                "content": str,     # Base64-encoded PDF content
                "success": bool,    # Whether conversion succeeded
                "error": str,       # Error message if failed
            }
        """
        import base64
        import tempfile

        try:
            data = await request.json()
            file_path_str = data.get("path")
            workspace = data.get("workspace")

            if not file_path_str or not workspace:
                return JSONResponse(
                    {
                        "success": False,
                        "error": "Both 'path' and 'workspace' are required",
                    },
                    status_code=400,
                )

            workspace_path = Path(workspace).resolve()
            file_path = (workspace_path / file_path_str).resolve()

            # Security: Ensure file is within workspace
            try:
                file_path.relative_to(workspace_path)
            except ValueError:
                return JSONResponse(
                    {
                        "success": False,
                        "error": "Access denied: path outside workspace",
                    },
                    status_code=403,
                )

            if not file_path.exists():
                return JSONResponse(
                    {"success": False, "error": "File not found"},
                    status_code=404,
                )

            # Get file mtime for cache validation
            file_mtime = file_path.stat().st_mtime

            # Check cache first - avoid expensive Docker conversion if already done
            cached_pdf = _get_cached_pdf(workspace, file_path_str, file_mtime)
            if cached_pdf:
                workspace_logger.info(f"PDF cache hit for {file_path_str}")
                return {
                    "success": True,
                    "content": cached_pdf,
                    "mimeType": "application/pdf",
                    "cached": True,
                }

            # Check file extension
            suffix = file_path.suffix.lower()
            if suffix not in [
                ".docx",
                ".pptx",
                ".xlsx",
                ".doc",
                ".ppt",
                ".xls",
                ".odt",
                ".odp",
                ".ods",
            ]:
                return JSONResponse(
                    {"success": False, "error": f"Unsupported file type: {suffix}"},
                    status_code=400,
                )

            # Check if Docker is available
            try:
                import docker

                client = docker.from_env()
                client.ping()
            except Exception:
                return JSONResponse(
                    {
                        "success": False,
                        "error": "Docker is not available. Install Docker and pull the MassGen container to enable document preview.",
                        "docker_required": True,
                    },
                    status_code=503,
                )

            # Check if MassGen image exists
            massgen_image = "ghcr.io/massgen/mcp-runtime:latest"
            try:
                client.images.get(massgen_image)
            except docker.errors.ImageNotFound:
                return JSONResponse(
                    {
                        "success": False,
                        "error": f"MassGen Docker image not found. Run: docker pull {massgen_image}",
                        "docker_required": True,
                    },
                    status_code=503,
                )

            # Create temp directory for output
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_dir_path = Path(temp_dir)

                # Run LibreOffice conversion in container
                # Mount the file's parent directory and temp output directory
                input_dir = file_path.parent
                input_filename = file_path.name
                output_filename = file_path.stem + ".pdf"

                try:
                    # Run soffice in container
                    result = client.containers.run(
                        massgen_image,
                        command=[
                            "/bin/sh",
                            "-c",
                            f"soffice --headless --convert-to pdf --outdir /output '/input/{input_filename}'",
                        ],
                        volumes={
                            str(input_dir): {"bind": "/input", "mode": "ro"},
                            str(temp_dir_path): {"bind": "/output", "mode": "rw"},
                        },
                        remove=True,
                        user="root",  # LibreOffice needs write access to home dir
                        stderr=True,
                        stdout=True,
                    )

                    # Check if PDF was created
                    output_pdf = temp_dir_path / output_filename
                    if not output_pdf.exists():
                        # Try alternate output name (sometimes LibreOffice changes case)
                        for f in temp_dir_path.iterdir():
                            if f.suffix.lower() == ".pdf":
                                output_pdf = f
                                break

                    if not output_pdf.exists():
                        return JSONResponse(
                            {
                                "success": False,
                                "error": "Conversion failed: PDF not generated",
                                "details": result.decode("utf-8") if isinstance(result, bytes) else str(result),
                            },
                            status_code=500,
                        )

                    # Read and encode the PDF
                    with open(output_pdf, "rb") as f:
                        pdf_content = base64.b64encode(f.read()).decode("utf-8")

                    # Cache the conversion result for future requests
                    _cache_pdf(workspace, file_path_str, file_mtime, pdf_content)
                    workspace_logger.info(f"PDF conversion cached for {file_path_str}")

                    return {
                        "success": True,
                        "content": pdf_content,
                        "mimeType": "application/pdf",
                    }

                except docker.errors.ContainerError as e:
                    return JSONResponse(
                        {
                            "success": False,
                            "error": f"Container error: {e.stderr.decode() if e.stderr else str(e)}",
                        },
                        status_code=500,
                    )

        except Exception as e:
            return JSONResponse(
                {"success": False, "error": f"Conversion failed: {str(e)}"},
                status_code=500,
            )

    @app.post("/api/tester/upload")
    async def upload_test_file(request: Request):
        """Upload a file temporarily for testing artifact preview with Docker conversion.

        This endpoint saves a base64-encoded file to a temp directory so the
        artifact tester can test Docker-based document conversion.

        Request body:
            {
                "fileName": str,    # Original file name
                "content": str,     # Base64-encoded file content
            }

        Returns:
            {
                "success": bool,
                "workspacePath": str,   # Temp directory path
                "filePath": str,        # Relative file path within workspace
            }
        """
        import base64
        import tempfile

        try:
            data = await request.json()
            file_name = data.get("fileName")
            content_b64 = data.get("content")

            if not file_name or not content_b64:
                return JSONResponse(
                    {
                        "success": False,
                        "error": "Both 'fileName' and 'content' are required",
                    },
                    status_code=400,
                )

            # Create a persistent temp directory (won't be auto-deleted)
            # We use a fixed location so files persist across requests
            temp_base = Path(tempfile.gettempdir()) / "massgen_artifact_tester"
            temp_base.mkdir(exist_ok=True)

            # Create a unique subdirectory for this upload
            import uuid

            upload_id = str(uuid.uuid4())[:8]
            workspace_path = temp_base / upload_id
            workspace_path.mkdir(exist_ok=True)

            # Decode and save the file
            try:
                file_bytes = base64.b64decode(content_b64)
            except Exception as e:
                return JSONResponse(
                    {"success": False, "error": f"Invalid base64 content: {str(e)}"},
                    status_code=400,
                )

            file_path = workspace_path / file_name
            with open(file_path, "wb") as f:
                f.write(file_bytes)

            return {
                "success": True,
                "workspacePath": str(workspace_path),
                "filePath": file_name,
            }

        except Exception as e:
            return JSONResponse(
                {"success": False, "error": f"Upload failed: {str(e)}"},
                status_code=500,
            )

    @app.post("/api/workspace/open")
    async def open_workspace_in_finder(request: Request):
        """Open a workspace folder in the native file browser.

        Args:
            request body: { "path": str }  # Absolute path to workspace directory

        Returns:
            { "success": bool, "message": str }
        """
        import platform
        import subprocess

        try:
            data = await request.json()
            workspace_path = data.get("path")

            if not workspace_path:
                return JSONResponse(
                    {"error": "Path is required"},
                    status_code=400,
                )

            path = Path(workspace_path).resolve()

            if not path.exists():
                return JSONResponse(
                    {"error": f"Path does not exist: {workspace_path}"},
                    status_code=404,
                )

            if not path.is_dir():
                return JSONResponse(
                    {"error": "Path is not a directory"},
                    status_code=400,
                )

            # Open in native file browser based on platform
            system = platform.system()

            if system == "Darwin":  # macOS
                subprocess.Popen(["open", str(path)])
            elif system == "Windows":
                subprocess.Popen(["explorer", str(path)])
            elif system == "Linux":
                # Try common Linux file managers
                for cmd in ["xdg-open", "nautilus", "dolphin", "thunar", "pcmanfm"]:
                    try:
                        subprocess.Popen([cmd, str(path)])
                        break
                    except FileNotFoundError:
                        continue
                else:
                    return JSONResponse(
                        {"error": "No supported file browser found on Linux"},
                        status_code=500,
                    )
            else:
                return JSONResponse(
                    {"error": f"Unsupported platform: {system}"},
                    status_code=500,
                )

            return {"success": True, "message": f"Opened {path}"}

        except Exception as e:
            return JSONResponse(
                {"error": f"Failed to open workspace: {str(e)}"},
                status_code=500,
            )

    # Frontend debug logging endpoint - writes to webui_debug.log
    # When session_id is provided and active, writes to the session's log_dir
    # Otherwise falls back to the MassGen root directory
    _fallback_log_file = Path(__file__).parent.parent.parent.parent / "webui_debug.log"

    @app.post("/api/debug/log")
    async def frontend_debug_log(request: Request):
        """Log frontend debug messages to file for easier debugging.

        Request body:
        {
            "level": "debug" | "info" | "warn" | "error",
            "message": str,
            "data": dict (optional),
            "sessionId": str (optional - routes logs to session log_dir)
        }
        """
        import datetime

        try:
            body = await request.json()
            level = body.get("level", "info").upper()
            message = body.get("message", "")
            data = body.get("data")
            session_id = body.get("sessionId")

            # Determine log file location
            log_file = _fallback_log_file
            if session_id and session_id in manager.session_log_dirs:
                session_dir = manager.session_log_dirs[session_id]
                log_file = session_dir / "webui_debug.log"

            timestamp = datetime.datetime.now().isoformat()
            log_line = f"[{timestamp}] [{level}] {message}"
            if data:
                log_line += f" | {json.dumps(data)}"
            log_line += "\n"

            with open(log_file, "a") as f:
                f.write(log_line)

            return {"success": True}
        except Exception as e:
            return JSONResponse(
                {"error": str(e)},
                status_code=500,
            )

    @app.post("/api/browse/files")
    async def browse_files(request: Request):
        """Open a native file picker dialog and return selected paths.

        Request body:
        {
            "mode": "files" | "directory",  # What to select
            "multiple": bool,  # Allow multiple selection (files only)
            "title": str  # Optional dialog title
        }

        Returns:
            { "paths": [str, ...] }  # List of selected absolute paths
        """
        import platform
        import subprocess

        try:
            data = await request.json()
            mode = data.get("mode", "files")
            multiple = data.get("multiple", True)
            title = data.get(
                "title",
                "Select Files" if mode == "files" else "Select Directory",
            )

            system = platform.system()
            paths = []

            if system == "Darwin":
                # macOS - use AppleScript
                if mode == "directory":
                    script = f"""
                    tell application "System Events"
                        activate
                    end tell
                    set chosenFolder to choose folder with prompt "{title}"
                    return POSIX path of chosenFolder
                    """
                else:
                    if multiple:
                        script = f"""
                        tell application "System Events"
                            activate
                        end tell
                        set chosenFiles to choose file with prompt "{title}" with multiple selections allowed
                        set posixPaths to {{}}
                        repeat with aFile in chosenFiles
                            set end of posixPaths to POSIX path of aFile
                        end repeat
                        set AppleScript's text item delimiters to linefeed
                        return posixPaths as text
                        """
                    else:
                        script = f"""
                        tell application "System Events"
                            activate
                        end tell
                        set chosenFile to choose file with prompt "{title}"
                        return POSIX path of chosenFile
                        """

                result = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )

                if result.returncode == 0 and result.stdout.strip():
                    # Parse the output - may be multiple paths separated by newlines
                    paths = [p.strip() for p in result.stdout.strip().split("\n") if p.strip()]

            elif system == "Linux":
                # Linux - try zenity first, then kdialog
                try:
                    if mode == "directory":
                        result = subprocess.run(
                            [
                                "zenity",
                                "--file-selection",
                                "--directory",
                                "--title",
                                title,
                            ],
                            capture_output=True,
                            text=True,
                            timeout=300,
                        )
                    else:
                        cmd = ["zenity", "--file-selection", "--title", title]
                        if multiple:
                            cmd.append("--multiple")
                            cmd.extend(["--separator", "\n"])
                        result = subprocess.run(
                            cmd,
                            capture_output=True,
                            text=True,
                            timeout=300,
                        )

                    if result.returncode == 0 and result.stdout.strip():
                        paths = [p.strip() for p in result.stdout.strip().split("\n") if p.strip()]
                except FileNotFoundError:
                    # Try kdialog as fallback
                    try:
                        if mode == "directory":
                            result = subprocess.run(
                                [
                                    "kdialog",
                                    "--getexistingdirectory",
                                    ".",
                                    "--title",
                                    title,
                                ],
                                capture_output=True,
                                text=True,
                                timeout=300,
                            )
                        else:
                            cmd = [
                                "kdialog",
                                "--getopenfilename",
                                ".",
                                "--title",
                                title,
                            ]
                            if multiple:
                                cmd = [
                                    "kdialog",
                                    "--getopenfilename",
                                    ".",
                                    "--multiple",
                                    "--title",
                                    title,
                                ]
                            result = subprocess.run(
                                cmd,
                                capture_output=True,
                                text=True,
                                timeout=300,
                            )

                        if result.returncode == 0 and result.stdout.strip():
                            paths = [p.strip() for p in result.stdout.strip().split("\n") if p.strip()]
                    except FileNotFoundError:
                        return JSONResponse(
                            {
                                "error": "No file dialog available. Please install zenity or kdialog.",
                            },
                            status_code=500,
                        )

            elif system == "Windows":
                # Windows - use PowerShell
                if mode == "directory":
                    ps_script = """
                    Add-Type -AssemblyName System.Windows.Forms
                    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
                    $dialog.Description = "{}"
                    if ($dialog.ShowDialog() -eq 'OK') {{ $dialog.SelectedPath }}
                    """.format(
                        title,
                    )
                else:
                    ps_script = """
                    Add-Type -AssemblyName System.Windows.Forms
                    $dialog = New-Object System.Windows.Forms.OpenFileDialog
                    $dialog.Title = "{}"
                    $dialog.Multiselect = ${}
                    if ($dialog.ShowDialog() -eq 'OK') {{ $dialog.FileNames -join "`n" }}
                    """.format(
                        title,
                        "true" if multiple else "false",
                    )

                result = subprocess.run(
                    ["powershell", "-Command", ps_script],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )

                if result.returncode == 0 and result.stdout.strip():
                    paths = [p.strip() for p in result.stdout.strip().split("\n") if p.strip()]

            else:
                return JSONResponse(
                    {"error": f"Unsupported platform: {system}"},
                    status_code=500,
                )

            return {"paths": paths}

        except subprocess.TimeoutExpired:
            return JSONResponse(
                {"error": "Dialog timed out"},
                status_code=408,
            )
        except Exception as e:
            return JSONResponse(
                {"error": f"Failed to open file dialog: {str(e)}"},
                status_code=500,
            )

    @app.get("/api/path/autocomplete")
    async def path_autocomplete(
        prefix: str = "",
        base_path: str | None = None,
    ):
        """Get path suggestions for autocomplete.

        Used by the Web UI to provide inline file path completion
        when users type @path syntax.

        Args:
            prefix: The partial path to complete (e.g., "~/Doc" or "./src")
            base_path: Optional base directory to resolve relative paths from.
                       If not provided, uses user's home directory.

        Returns:
            {
                "suggestions": [
                    {"path": "/full/path", "name": "filename", "is_dir": bool},
                    ...
                ]
            }
        """
        import os
        from pathlib import Path

        MAX_SUGGESTIONS = 50

        try:
            # Expand ~ to home directory
            if prefix.startswith("~"):
                prefix = os.path.expanduser(prefix)
            elif prefix.startswith("./") or prefix.startswith("../"):
                # Resolve relative paths
                if base_path:
                    base = Path(base_path).expanduser().resolve()
                else:
                    base = Path.home()
                prefix = str(base / prefix)
            elif not prefix.startswith("/"):
                # If no prefix or just a filename, use base_path or home
                if base_path:
                    base = Path(base_path).expanduser().resolve()
                else:
                    base = Path.home()
                prefix = str(base / prefix) if prefix else str(base) + "/"

            prefix_path = Path(prefix)

            # Determine parent directory and partial name to match
            if prefix.endswith("/") or prefix_path.is_dir():
                # User is browsing a directory
                parent_dir = prefix_path if prefix_path.is_dir() else prefix_path.parent
                partial_name = ""
            else:
                # User is typing a partial name
                parent_dir = prefix_path.parent
                partial_name = prefix_path.name.lower()

            # Security: Resolve to absolute path and verify it exists
            parent_dir = parent_dir.resolve()

            if not parent_dir.exists() or not parent_dir.is_dir():
                return {"suggestions": []}

            # List directory contents
            suggestions = []
            try:
                for entry in parent_dir.iterdir():
                    # Skip hidden files unless explicitly requested
                    if entry.name.startswith(".") and not partial_name.startswith("."):
                        continue

                    # Match partial name (case-insensitive)
                    if partial_name and not entry.name.lower().startswith(partial_name):
                        continue

                    is_dir = entry.is_dir()
                    suggestions.append(
                        {
                            "path": str(entry),
                            "name": entry.name + ("/" if is_dir else ""),
                            "is_dir": is_dir,
                        },
                    )

                    if len(suggestions) >= MAX_SUGGESTIONS:
                        break

            except PermissionError:
                return {"suggestions": []}

            # Sort: directories first, then alphabetically
            suggestions.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))

            return {"suggestions": suggestions}

        except Exception as e:
            return JSONResponse(
                {"error": f"Failed to get path suggestions: {str(e)}"},
                status_code=500,
            )

    @app.get("/api/sessions/{session_id}/timeline")
    async def get_session_timeline(session_id: str):
        """Get coordination timeline data for visualization.

        Returns timeline nodes representing answers, votes, and final answer
        with their context sources (which answers they saw).
        """
        display = manager.get_display(session_id)
        if display is None:
            return JSONResponse(
                {"error": "Session not found"},
                status_code=404,
            )

        # Get agents from display
        agent_ids = display.agent_ids if display else []

        # Build timeline from display's tracked events
        nodes = []

        # Get timeline data from display if available
        timeline_events = getattr(display, "_timeline_events", [])

        for event in timeline_events:
            node = {
                "id": event.get("id", ""),
                "type": event.get("type", "answer"),
                "agentId": event.get("agent_id", ""),
                "label": event.get("label", ""),
                "timestamp": event.get("timestamp", 0),
                "round": event.get("round", 1),
                "contextSources": event.get("context_sources", []),
                "votedFor": event.get("voted_for"),
            }
            nodes.append(node)

        # Timeline nodes are only populated from explicitly recorded events
        # (record_answer_with_context, record_vote_with_context, record_final_with_context)
        # No fallback reconstruction - prevents phantom nodes from appearing before
        # agents have actually submitted answers

        # Sort by timestamp
        nodes.sort(key=lambda x: x.get("timestamp", 0))

        # Calculate start/end times
        timestamps = [n.get("timestamp", 0) for n in nodes if n.get("timestamp")]
        start_time = min(timestamps) if timestamps else 0
        end_time = max(timestamps) if timestamps else None

        # Calculate current voting round (max round from vote nodes)
        # This lets the frontend determine which votes are superseded
        vote_rounds = [n.get("round", 1) for n in nodes if n.get("type") == "vote"]
        current_voting_round = max(vote_rounds) if vote_rounds else 1

        # Debug: log vote rounds
        vote_info = [(n.get("label"), n.get("round")) for n in nodes if n.get("type") == "vote"]
        print(f"[DEBUG] Timeline API: vote_info={vote_info}, currentVotingRound={current_voting_round}")

        return {
            "nodes": nodes,
            "agents": agent_ids,
            "startTime": start_time,
            "endTime": end_time,
            "currentVotingRound": current_voting_round,
        }

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str):
        """Get current state of a session."""
        display = manager.get_display(session_id)
        if display is None:
            return JSONResponse(
                {"error": "Session not found"},
                status_code=404,
            )
        return JSONResponse(display.get_state_snapshot())

    @app.get("/api/sessions/{session_id}/final-answer")
    async def get_final_answer(session_id: str):
        """Get the clean final answer from the saved log file.

        The final answer is saved to:
        .massgen/massgen_logs/log_<timestamp>/turn_<N>/final/<agent_id>/answer.txt

        This returns the clean answer without any tool call noise.
        """
        # Get the log session dir from the display (stored after coordination completes)
        display = manager.get_display(session_id)
        log_session_dir = getattr(display, "log_session_dir", None) if display else None

        print(f"[DEBUG] get_final_answer: session_id={session_id}")
        print(f"[DEBUG] get_final_answer: display={display}")
        print(
            f"[DEBUG] get_final_answer: log_session_dir from display={log_session_dir}",
        )

        # Fallback to global log session dir if display doesn't have it
        if not log_session_dir:
            from massgen.logger_config import get_log_session_dir

            log_session_dir = get_log_session_dir()
            print(
                f"[DEBUG] get_final_answer: log_session_dir from global={log_session_dir}",
            )

        if not log_session_dir or not log_session_dir.exists():
            print(
                "[DEBUG] get_final_answer: log_session_dir not found or doesn't exist",
            )
            return JSONResponse(
                {"error": "Log directory not found", "answer": None},
                status_code=404,
            )

        # log_session_dir could be:
        # - .massgen/massgen_logs/log_xxx/turn_1 (old structure)
        # - .massgen/massgen_logs/log_xxx/turn_1/attempt_N (new structure with attempts)
        # We need to search for final/<agent>/answer.txt in multiple possible locations

        # Helper to find answer in a final directory
        def find_answer_in_final_dir(final_dir):
            if not final_dir.exists():
                return None
            for agent_dir in final_dir.iterdir():
                if not agent_dir.is_dir():
                    continue
                answer_file = agent_dir / "answer.txt"
                print(f"[DEBUG] get_final_answer: Checking answer_file={answer_file}")
                if answer_file.exists():
                    try:
                        answer_content = answer_file.read_text(encoding="utf-8")
                        print(
                            f"[DEBUG] get_final_answer: Found answer! Length={len(answer_content)}",
                        )
                        return {
                            "answer": answer_content,
                            "agent_id": agent_dir.name,
                            "path": str(answer_file),
                        }
                    except Exception as e:
                        return {"error": f"Failed to read answer: {str(e)}"}
            return None

        # Try 1: Direct final/ directory (log_session_dir/final)
        final_dir = log_session_dir / "final"
        print(f"[DEBUG] get_final_answer: Looking for final_dir={final_dir}")
        result = find_answer_in_final_dir(final_dir)
        if result:
            if "error" in result:
                return JSONResponse(
                    {"error": result["error"], "answer": None},
                    status_code=500,
                )
            return result

        # Try 2: Check for attempt_N subdirectories (log_session_dir/attempt_N/final)
        print("[DEBUG] get_final_answer: Checking attempt subdirectories")
        for attempt_dir in sorted(log_session_dir.iterdir(), reverse=True):
            if not attempt_dir.is_dir() or not attempt_dir.name.startswith("attempt_"):
                continue
            print(f"[DEBUG] get_final_answer: Checking attempt dir: {attempt_dir}")
            final_dir = attempt_dir / "final"
            result = find_answer_in_final_dir(final_dir)
            if result:
                if "error" in result:
                    return JSONResponse(
                        {"error": result["error"], "answer": None},
                        status_code=500,
                    )
                return result

        # Fallback: search in turn subdirectories (for older log structure or if log_session_dir is base)
        print("[DEBUG] get_final_answer: No final dir, searching turn subdirs")
        for turn_dir in sorted(log_session_dir.iterdir(), reverse=True):
            if not turn_dir.is_dir() or not turn_dir.name.startswith("turn_"):
                continue

            # Check direct final/ in turn dir
            result = find_answer_in_final_dir(turn_dir / "final")
            if result:
                if "error" in result:
                    return JSONResponse(
                        {"error": result["error"], "answer": None},
                        status_code=500,
                    )
                return result

            # Check attempt_N subdirectories within turn dir
            for attempt_dir in sorted(turn_dir.iterdir(), reverse=True):
                if not attempt_dir.is_dir() or not attempt_dir.name.startswith(
                    "attempt_",
                ):
                    continue
                result = find_answer_in_final_dir(attempt_dir / "final")
                if result:
                    if "error" in result:
                        return JSONResponse(
                            {"error": result["error"], "answer": None},
                            status_code=500,
                        )
                    return result

        return JSONResponse(
            {"error": "Final answer not found", "answer": None},
            status_code=404,
        )

    @app.post("/api/sessions/{session_id}/share")
    async def share_session_gist(session_id: str):
        """Upload session to GitHub Gist and return viewer URL.

        Requires GitHub CLI (gh) to be installed and authenticated.
        Returns the viewer URL for the shared session.
        """
        from massgen.share import ShareError, share_session

        # Get the log session dir from the display
        display = manager.get_display(session_id)
        log_session_dir = getattr(display, "log_session_dir", None) if display else None

        # Fallback to global log session dir
        if not log_session_dir:
            from massgen.logger_config import get_log_session_dir

            log_session_dir = get_log_session_dir()

        if not log_session_dir or not log_session_dir.exists():
            return JSONResponse(
                {"error": "Log directory not found. Session may not have started yet."},
                status_code=404,
            )

        try:
            # Share the session (creates gist and returns viewer URL)
            viewer_url = share_session(log_session_dir, console=None)

            return JSONResponse(
                {
                    "success": True,
                    "viewer_url": viewer_url,
                    "message": "Session shared successfully!",
                },
            )

        except ShareError as e:
            return JSONResponse(
                {"error": str(e)},
                status_code=400,
            )
        except Exception as e:
            import traceback

            traceback.print_exc()
            return JSONResponse(
                {"error": f"Failed to share session: {str(e)}"},
                status_code=500,
            )

    @app.post("/api/sessions/{session_id}/start")
    async def start_coordination(session_id: str, request: dict):
        """Start coordination for a session."""
        question = request.get("question", "")
        # Use provided config or fall back to default
        cfg_path = request.get("config") or get_default_config()

        if not question:
            return JSONResponse(
                {"error": "Question is required"},
                status_code=400,
            )

        if not cfg_path:
            return JSONResponse(
                {
                    "error": "No config specified. Use --config flag or provide in request.",
                },
                status_code=400,
            )

        # Start orchestration in background
        task = asyncio.create_task(
            run_coordination(session_id, question, cfg_path),
        )
        manager.tasks[session_id] = task

        return JSONResponse(
            {
                "status": "started",
                "session_id": session_id,
                "config": cfg_path,
            },
        )

    @app.post("/api/sessions/{session_id}/cancel")
    async def cancel_coordination(session_id: str):
        """Cancel an active coordination session."""
        task = manager.tasks.get(session_id)

        if not task:
            return JSONResponse(
                {"error": "No active session found", "session_id": session_id},
                status_code=404,
            )

        if task.done():
            return JSONResponse(
                {
                    "status": "already_completed",
                    "session_id": session_id,
                    "message": "Coordination has already completed",
                },
            )

        # Set cancellation flag on orchestrator first (for graceful stop)
        orchestrator = manager.orchestrators.get(session_id)
        if orchestrator:
            if hasattr(orchestrator, "cancellation_manager") and orchestrator.cancellation_manager:
                orchestrator.cancellation_manager._cancelled = True
                print(f"[WebUI] Set cancellation flag for session {session_id}")
            # Also cancel the background status update task if it exists
            if hasattr(orchestrator, "_status_update_task") and orchestrator._status_update_task:
                orchestrator._status_update_task.cancel()

        # Also cancel the asyncio task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Update status.json to show cancelled state
        try:
            from massgen.logger_config import get_log_session_dir

            log_dir = get_log_session_dir()
            if log_dir:
                status_file = log_dir / "status.json"
                if status_file.exists():
                    import json
                    import time

                    with open(status_file) as f:
                        status_data = json.load(f)
                    status_data["coordination"] = status_data.get("coordination", {})
                    status_data["coordination"]["phase"] = "cancelled"
                    status_data["coordination"]["cancelled"] = True
                    status_data["coordination"]["cancelled_at"] = time.time()
                    with open(status_file, "w") as f:
                        json.dump(status_data, f, indent=2)
        except Exception as status_err:
            print(f"[WebUI] Warning: Could not update status.json: {status_err}")

        # Cleanup orchestrator reference
        if session_id in manager.orchestrators:
            del manager.orchestrators[session_id]

        # Notify connected clients
        await manager.broadcast(
            session_id,
            {
                "type": "coordination_cancelled",
                "session_id": session_id,
                "message": "Coordination cancelled by user",
            },
        )

        return JSONResponse(
            {
                "status": "cancelled",
                "session_id": session_id,
                "message": "Coordination cancelled successfully",
            },
        )

    # =========================================================================
    # WebSocket Endpoint
    # =========================================================================

    @app.websocket("/ws/{session_id}")
    async def websocket_endpoint(websocket: WebSocket, session_id: str):
        """WebSocket endpoint for real-time coordination updates."""
        await manager.connect(websocket, session_id)

        try:
            # Send current state if session exists
            display = manager.get_display(session_id)
            if display:
                await websocket.send_json(
                    {
                        "type": "state_snapshot",
                        "automation_mode": app.state.automation_mode,
                        **display.get_state_snapshot(),
                    },
                )
            else:
                # Send init message with automation_mode even without display
                await websocket.send_json(
                    {
                        "type": "init",
                        "automation_mode": app.state.automation_mode,
                        "session_id": session_id,
                    },
                )

            # Handle incoming messages
            while True:
                data = await websocket.receive_json()
                action = data.get("action")

                if action == "start":
                    # Start new coordination
                    question = data.get("question", "")
                    # Use provided config or fall back to default
                    cfg_path = data.get("config") or get_default_config()

                    if not cfg_path:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": "No config specified. Start server with --config flag.",
                            },
                        )
                        continue

                    if question:
                        # Parse @path references from question
                        context_paths = []
                        try:
                            from massgen.path_handling import (
                                PromptParserError,
                                parse_prompt_for_context,
                            )

                            parsed = parse_prompt_for_context(question)
                            if parsed.context_paths:
                                context_paths = parsed.context_paths
                                question = parsed.cleaned_prompt
                                # Notify client about extracted paths
                                await websocket.send_json(
                                    {
                                        "type": "context_paths_extracted",
                                        "paths": context_paths,
                                        "session_id": session_id,
                                    },
                                )
                        except PromptParserError as e:
                            await websocket.send_json(
                                {
                                    "type": "error",
                                    "message": f"Path error: {e}",
                                },
                            )
                            continue
                        except ImportError as e:
                            # Log warning - path_handling module not available
                            workspace_logger.warning(
                                f"Path handling module not available: {e}. " "@path syntax will not be processed.",
                            )

                        # Send immediate acknowledgment that we received the prompt
                        await websocket.send_json(
                            {
                                "type": "preparation_status",
                                "status": "Received prompt...",
                                "detail": "Preparing to start coordination",
                                "session_id": session_id,
                            },
                        )

                        task = asyncio.create_task(
                            run_coordination(session_id, question, cfg_path, context_paths),
                        )
                        manager.tasks[session_id] = task
                        await websocket.send_json(
                            {
                                "type": "coordination_started",
                                "session_id": session_id,
                                "config": cfg_path,
                            },
                        )

                elif action == "get_state":
                    # Request current state
                    display = manager.get_display(session_id)
                    if display:
                        await websocket.send_json(
                            {
                                "type": "state_snapshot",
                                **display.get_state_snapshot(),
                            },
                        )

                elif action == "broadcast_response":
                    # Human response to a broadcast question
                    # TODO: Integrate with BroadcastChannel
                    pass

                elif action == "continue":
                    # Continue conversation with follow-up question
                    followup_question = data.get("question", "")
                    if not followup_question:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": "Question is required for continuation",
                            },
                        )
                        continue

                    # Parse @path references from follow-up question
                    context_paths = []
                    try:
                        from massgen.path_handling import (
                            PromptParserError,
                            parse_prompt_for_context,
                        )

                        parsed = parse_prompt_for_context(followup_question)
                        if parsed.context_paths:
                            context_paths = parsed.context_paths
                            followup_question = parsed.cleaned_prompt
                            # Notify client about extracted paths
                            await websocket.send_json(
                                {
                                    "type": "context_paths_extracted",
                                    "paths": context_paths,
                                    "session_id": session_id,
                                },
                            )
                    except PromptParserError as e:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": f"Path error: {e}",
                            },
                        )
                        continue
                    except ImportError as e:
                        # Log warning - path_handling module not available
                        workspace_logger.warning(
                            f"Path handling module not available: {e}. " "@path syntax will not be processed.",
                        )

                    # Get session info from previous turn
                    session_log_dir = manager.session_log_dirs.get(session_id)
                    current_turn = manager.session_turns.get(session_id, 0)
                    cfg_path = manager.session_configs.get(session_id) or get_default_config()

                    if not session_log_dir:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": "No active session to continue. Start a new coordination first.",
                            },
                        )
                        continue

                    if not cfg_path:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": "No config available for continuation.",
                            },
                        )
                        continue

                    # Start continuation coordination
                    next_turn = current_turn + 1
                    task = asyncio.create_task(
                        run_coordination_with_history(
                            session_id=session_id,
                            question=followup_question,
                            config_path=cfg_path,
                            session_log_dir=session_log_dir,
                            turn_number=next_turn,
                            context_paths=context_paths,
                        ),
                    )
                    manager.tasks[session_id] = task
                    await websocket.send_json(
                        {
                            "type": "coordination_started",
                            "session_id": session_id,
                            "config": cfg_path,
                            "turn": next_turn,
                            "is_continuation": True,
                        },
                    )

                elif action == "cancel":
                    # Cancel the running coordination task
                    task = manager.tasks.get(session_id)
                    if task and not task.done():
                        # Set cancellation flag on orchestrator first (for graceful stop)
                        orchestrator = manager.orchestrators.get(session_id)
                        if orchestrator:
                            if hasattr(orchestrator, "cancellation_manager") and orchestrator.cancellation_manager:
                                orchestrator.cancellation_manager._cancelled = True
                                print(f"[WebUI] Set cancellation flag for session {session_id}")
                            # Also cancel the background status update task if it exists
                            if hasattr(orchestrator, "_status_update_task") and orchestrator._status_update_task:
                                orchestrator._status_update_task.cancel()

                        # Also cancel the asyncio task
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass

                        # Cleanup orchestrator reference
                        if session_id in manager.orchestrators:
                            del manager.orchestrators[session_id]

                        await websocket.send_json(
                            {
                                "type": "coordination_cancelled",
                                "session_id": session_id,
                                "message": "Coordination cancelled by user",
                            },
                        )
                    else:
                        await websocket.send_json(
                            {
                                "type": "info",
                                "message": "No active coordination to cancel",
                            },
                        )

        except WebSocketDisconnect:
            manager.disconnect(websocket, session_id)
        except Exception as e:
            # Send error and disconnect
            try:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": str(e),
                    },
                )
            except Exception:
                pass
            manager.disconnect(websocket, session_id)

    # =========================================================================
    # Workspace WebSocket Endpoint (for real-time file change notifications)
    # =========================================================================

    @app.websocket("/ws/workspace/{session_id}")
    async def workspace_websocket_endpoint(websocket: WebSocket, session_id: str):
        """WebSocket endpoint for real-time workspace file change notifications.

        Clients connect to receive push notifications when files are created,
        modified, or deleted in watched workspace directories.

        Protocol:
        - On connect: Client sends { "action": "watch", "paths": ["/path/to/workspace1", ...] }
        - Server sends: { "type": "workspace_connected", "watched_paths": [...] }
        - On file change: Server pushes { "type": "workspace_file_change", "file_path": ..., "operation": ... }
        - Client can request refresh: { "action": "refresh", "path": "/path/to/workspace" }
        """
        workspace_logger.info(f"WS endpoint: new connection for session={session_id}")

        # Get workspace paths from query params or wait for watch action
        initial_paths = []

        # Try to get workspace paths from status.json if session exists
        try:
            display = manager.get_display(session_id)
            log_session_dir = getattr(display, "log_session_dir", None) if display else None
            workspace_logger.debug(f"WS endpoint: display={display is not None}, log_dir={log_session_dir}")

            if not log_session_dir:
                from massgen.logger_config import get_log_session_dir

                log_session_dir = get_log_session_dir()
                workspace_logger.debug(f"WS endpoint: using fallback log_dir={log_session_dir}")

            if log_session_dir:
                status_file = Path(log_session_dir) / "status.json"
                if status_file.exists():
                    workspace_logger.debug(f"WS endpoint: reading status.json from {status_file}")
                    with open(status_file) as f:
                        status_data = json.load(f)

                    agents_data = status_data.get("agents", {})
                    for agent_id_key, agent_info in agents_data.items():
                        workspace_paths = agent_info.get("workspace_paths", {})
                        workspace_path = workspace_paths.get("workspace")
                        if workspace_path and Path(workspace_path).exists():
                            initial_paths.append(workspace_path)
                            workspace_logger.debug(f"WS endpoint: found workspace for {agent_id_key}: {workspace_path}")
                else:
                    workspace_logger.debug(f"WS endpoint: status.json not found at {status_file}")
        except Exception as e:
            workspace_logger.warning(f"WS endpoint: could not get workspace paths from status.json: {e}")

        workspace_logger.info(f"WS endpoint: connecting with {len(initial_paths)} initial paths")

        # Connect with initial paths (may be empty)
        await workspace_manager.connect(websocket, session_id, initial_paths)

        try:
            # Handle incoming messages
            while True:
                data = await websocket.receive_json()
                action = data.get("action")
                workspace_logger.debug(f"WS message received: action={action}, session={session_id}")

                if action == "watch_session":
                    # Watch all workspaces for this session (reads from status.json)
                    # Frontend uses this on initial connect to get all workspace files
                    workspace_logger.info(f"WS watch_session request for session={session_id}")

                    # Re-read status.json to get current workspace paths
                    session_paths: list[str] = []
                    try:
                        if log_session_dir:
                            status_file = Path(log_session_dir) / "status.json"
                            if status_file.exists():
                                with open(status_file) as f:
                                    status_data = json.load(f)
                                agents_data = status_data.get("agents", {})
                                for agent_id_key, agent_info in agents_data.items():
                                    workspace_paths = agent_info.get("workspace_paths", {})
                                    workspace_path = workspace_paths.get("workspace")
                                    if workspace_path and Path(workspace_path).exists():
                                        session_paths.append(workspace_path)
                    except Exception as e:
                        workspace_logger.warning(f"WS watch_session: failed to read status.json: {e}")

                    # Collect initial files for each workspace
                    initial_files: dict[str, list[dict]] = {}
                    for path in session_paths:
                        workspace_path = Path(path)
                        if workspace_path.exists() and workspace_path.is_dir():
                            try:
                                files = _scan_workspace_files(workspace_path)
                                # Normalize path for consistent key format
                                normalized_path = _normalize_workspace_path(path)
                                initial_files[normalized_path] = files
                                workspace_logger.debug(
                                    f"WS watch_session: scanned {len(files)} files for {workspace_path.name}",
                                )
                            except Exception as e:
                                workspace_logger.warning(f"WS watch_session: failed to scan {path}: {e}")
                                # Use normalized path for error case too
                                normalized_path = _normalize_workspace_path(path)
                                initial_files[normalized_path] = []

                    # Normalize watched_paths for consistency
                    normalized_watched_paths = [_normalize_workspace_path(p) for p in session_paths]
                    await websocket.send_json(
                        {
                            "type": "workspace_connected",
                            "session_id": session_id,
                            "timestamp": asyncio.get_event_loop().time(),
                            "watched_paths": normalized_watched_paths,
                            "initial_files": initial_files,
                        },
                    )
                    workspace_logger.info(f"WS watch_session: sent {len(session_paths)} workspaces with files")

                elif action == "watch":
                    # Start watching additional paths
                    # Support both "paths" and "workspace_paths" keys for compatibility
                    paths = data.get("paths", []) or data.get("workspace_paths", [])
                    workspace_logger.info(f"WS watch request: {len(paths)} paths for session={session_id}")

                    # Collect initial files for each watched path
                    initial_files: dict[str, list[dict]] = {}
                    for path in paths:
                        workspace_path = Path(path)
                        if workspace_path.exists() and workspace_path.is_dir():
                            try:
                                files = _scan_workspace_files(workspace_path)
                                # FIX: Normalize path for consistency with broadcasts
                                normalized_path = _normalize_workspace_path(path)
                                initial_files[normalized_path] = files
                                workspace_logger.debug(
                                    f"WS watch: scanned {len(files)} files for {workspace_path.name}",
                                )
                            except Exception as e:
                                workspace_logger.warning(f"WS watch: failed to scan {path}: {e}")
                                normalized_path = _normalize_workspace_path(path)
                                initial_files[normalized_path] = []

                    await websocket.send_json(
                        {
                            "type": "workspace_connected",
                            "session_id": session_id,
                            "timestamp": asyncio.get_event_loop().time(),
                            "watched_paths": paths,
                            "initial_files": initial_files,
                        },
                    )

                elif action == "refresh":
                    # Request a full file list for a workspace path
                    path = data.get("path")
                    # FIX: Normalize path for consistency with broadcasts and initial_files
                    normalized_path = _normalize_workspace_path(path) if path else None
                    workspace_logger.info(f"WS refresh request: path={path}, normalized={normalized_path}, session={session_id}")
                    if normalized_path and Path(normalized_path).exists():
                        workspace_path = Path(normalized_path)
                        try:
                            files = _scan_workspace_files(workspace_path)
                        except Exception as e:
                            await websocket.send_json(
                                {
                                    "type": "workspace_error",
                                    "session_id": session_id,
                                    "timestamp": asyncio.get_event_loop().time(),
                                    "error": str(e),
                                    "workspace_path": normalized_path,
                                },
                            )
                            continue

                        await websocket.send_json(
                            {
                                "type": "workspace_refresh",
                                "session_id": session_id,
                                "timestamp": asyncio.get_event_loop().time(),
                                "workspace_path": normalized_path,
                                "files": files,
                            },
                        )
                    else:
                        await websocket.send_json(
                            {
                                "type": "workspace_error",
                                "session_id": session_id,
                                "timestamp": asyncio.get_event_loop().time(),
                                "error": "Workspace path not found",
                                "workspace_path": normalized_path or path,
                            },
                        )

        except WebSocketDisconnect:
            workspace_logger.info(f"WS endpoint: client disconnected, session={session_id}")
            workspace_manager.disconnect(websocket, session_id)
        except Exception as e:
            workspace_logger.error(f"WS endpoint: error in message loop for session={session_id}: {e}")
            try:
                await websocket.send_json(
                    {
                        "type": "workspace_error",
                        "session_id": session_id,
                        "timestamp": asyncio.get_event_loop().time(),
                        "error": str(e),
                    },
                )
            except Exception:
                pass
            workspace_manager.disconnect(websocket, session_id)

    # =========================================================================
    # Static File Serving (React build)
    # =========================================================================

    # Path to React build directory (packaged with massgen)
    static_dir = Path(__file__).parent / "static"

    if static_dir.exists():
        # Serve static files from React build
        app.mount(
            "/assets",
            StaticFiles(directory=static_dir / "assets"),
            name="assets",
        )

        @app.get("/")
        async def serve_index():
            """Serve React app index.html."""
            return FileResponse(static_dir / "index.html")

        @app.get("/{path:path}")
        async def serve_spa(path: str):
            """Serve React SPA - route all paths to index.html.

            Note: API routes (/api/*) are handled by the routes defined above.
            This catch-all only handles frontend routes.
            """
            # Don't serve SPA for API routes - they should 404 if not found
            if path.startswith("api/"):
                return JSONResponse(
                    {"error": "API endpoint not found", "path": path},
                    status_code=404,
                )

            file_path = static_dir / path
            if file_path.exists() and file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(static_dir / "index.html")

    return app


async def _save_session_metadata(
    session_id: str,
    question: str,
    orchestrator: Any,
    config_path: str,
    log_session_dir: Path | None,
    turn_number: int = 1,
) -> None:
    """Save CLI-compatible metadata for multi-turn session continuation.

    This creates the same metadata structure as the CLI's save_final_state(),
    enabling sessions started in WebUI to be continued with `--continue`.

    Args:
        session_id: WebSocket session identifier
        question: The question/task that was asked
        orchestrator: The orchestrator instance (to get winning agent info)
        config_path: Path to the config file used
        log_session_dir: The log session directory (may include attempt subdirectory)
        turn_number: Current turn number (default 1 for first turn)
    """
    import json
    from datetime import datetime

    from massgen.logger_config import get_log_session_dir_base, get_log_session_root

    if not log_session_dir or not log_session_dir.exists():
        print("[WebUI] Warning: log_session_dir not available, skipping metadata save")
        return

    try:
        # Get orchestrator status for winning agent info
        status = orchestrator.get_status()
        winning_agent = status.get("selected_agent", "unknown")

        # Get the final answer
        final_answer = ""
        if hasattr(orchestrator, "_final_presentation_content") and orchestrator._final_presentation_content:
            final_answer = orchestrator._final_presentation_content.strip()
        elif winning_agent and hasattr(orchestrator, "agent_states") and winning_agent in orchestrator.agent_states:
            stored_answer = orchestrator.agent_states[winning_agent].answer
            if stored_answer:
                final_answer = stored_answer.strip()

        # Get the turn directory (without attempt subdirectory)
        # log_session_dir may be log_xxx/turn_Y/attempt_1/ but we need log_xxx/turn_Y/
        turn_dir = get_log_session_dir_base()
        session_dir = get_log_session_root()

        print(
            f"[WebUI] Saving metadata: turn_dir={turn_dir}, session_dir={session_dir}",
        )

        # Save metadata.json at turn level (CLI-compatible format)
        metadata = {
            "turn": turn_number,
            "timestamp": datetime.now().isoformat(),
            "winning_agent": winning_agent,
            "task": question,
            "session_id": session_dir.name,  # Use log dir name as session ID (e.g., log_xxx)
        }
        metadata_file = turn_dir / "metadata.json"
        metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        # Save answer.txt at turn level (CLI-compatible format)
        # Note: final/{agent}/answer.txt already exists, but CLI expects answer.txt at turn level too
        answer_file = turn_dir / "answer.txt"
        answer_file.write_text(final_answer, encoding="utf-8")

        # Save winning_agents_history.json at session level (for multi-turn memory sharing)
        winning_agents_history = []

        # Load existing history if present
        history_file = session_dir / "winning_agents_history.json"
        if history_file.exists():
            try:
                winning_agents_history = json.loads(
                    history_file.read_text(encoding="utf-8"),
                )
            except (json.JSONDecodeError, OSError):
                pass

        # Add current turn's winner
        winning_agents_history.append(
            {
                "agent_id": winning_agent,
                "turn": turn_number,
                "timestamp": datetime.now().isoformat(),
            },
        )
        history_file.write_text(
            json.dumps(winning_agents_history, indent=2),
            encoding="utf-8",
        )

        # Register session with SessionRegistry for `massgen --list-sessions` compatibility
        try:
            from massgen.session import SessionRegistry

            registry = SessionRegistry()
            # Use the log directory name as session_id (e.g., "log_20251130_211636_581944")
            massgen_session_id = session_dir.name
            registry.register_session(
                session_id=massgen_session_id,
                log_directory=str(session_dir),
                config_path=config_path,
            )
            print(f"[WebUI] Registered session: {massgen_session_id}")
        except Exception as e:
            print(f"[WebUI] Warning: Could not register session: {e}")

        # Store session info in ConnectionManager for continuation
        manager.session_log_dirs[session_id] = session_dir
        manager.session_turns[session_id] = turn_number
        manager.session_configs[session_id] = config_path

        print(
            f"[WebUI] Saved session metadata: turn={turn_number}, winner={winning_agent}",
        )

    except Exception as e:
        print(f"[WebUI] Error saving session metadata: {e}")
        import traceback

        traceback.print_exc()


async def run_coordination_with_history(
    session_id: str,
    question: str,
    config_path: str,
    session_log_dir: Path,
    turn_number: int,
    context_paths: list | None = None,
) -> None:
    """Run coordination with conversation history from previous turns.

    This is similar to `run_coordination()` but:
    1. Restores previous turn data using `restore_session()`
    2. Passes `previous_turns` and `winning_agents_history` to Orchestrator
    3. Sets the correct turn number in logger

    Args:
        session_id: WebSocket session identifier
        question: The follow-up question
        config_path: Path to the config file
        context_paths: Optional list of context paths from @path syntax
        session_log_dir: Path to the session log directory (e.g., .massgen/massgen_logs/log_xxx)
        turn_number: The turn number for this coordination (2, 3, etc.)
    """
    import traceback

    try:
        # Import here to avoid circular imports
        from massgen.agent_config import AgentConfig, CoordinationConfig
        from massgen.cli import (
            create_agents_from_config,
            load_config_file,
            resolve_config_path,
        )
        from massgen.frontend.coordination_ui import CoordinationUI
        from massgen.logger_config import (
            get_log_session_dir,
            save_execution_metadata,
            set_log_base_session_dir,
            set_log_turn,
        )
        from massgen.orchestrator import Orchestrator

        # IMPORTANT: Set the base session dir to reuse the existing session log directory
        # This must happen before set_log_turn() or get_log_session_dir() is called
        set_log_base_session_dir(
            session_log_dir.name,
        )  # e.g., "log_20251202_235530_074788"

        # Restore session state from previous turns
        previous_turns = []
        winning_agents_history = []
        conversation_history = []  # For multi-turn context passing to agents

        try:
            from massgen.session import restore_session

            # The session_log_dir is the base log dir (e.g., .massgen/massgen_logs/log_xxx)
            # We need to tell restore_session to look in the massgen_logs directory
            print(
                f"[WebUI] Attempting to restore session: session_log_dir={session_log_dir}",
            )
            print(
                f"[WebUI] session_log_dir.name={session_log_dir.name}, parent={session_log_dir.parent}",
            )
            session_state = restore_session(
                session_log_dir.name,  # e.g., "log_20251130_211636_581944"
                session_storage=str(
                    session_log_dir.parent,
                ),  # e.g., ".massgen/massgen_logs"
            )
            if session_state:
                previous_turns = session_state.previous_turns
                winning_agents_history = session_state.winning_agents_history
                conversation_history = session_state.conversation_history or []
                print(
                    f"[WebUI] Restored {len(previous_turns)} previous turns, {len(winning_agents_history)} winners, {len(conversation_history)} history messages",
                )
                if conversation_history:
                    print(
                        f"[WebUI] Conversation history preview: {conversation_history[0] if conversation_history else 'empty'}",
                    )
            else:
                print(
                    f"[WebUI] restore_session returned None for {session_log_dir.name}",
                )
        except Exception as e:
            print(f"[WebUI] ERROR restoring session state: {e}")
            traceback.print_exc()
            # Continue anyway - first follow-up might work without full history

        # Set the turn number for logging
        set_log_turn(turn_number)

        # Resolve config path
        resolved_path = resolve_config_path(config_path)
        if resolved_path is None:
            raise ValueError(f"Could not resolve config path: {config_path}")

        config, raw_config_for_metadata = load_config_file(str(resolved_path))

        # Inject context paths from @path syntax if provided
        if context_paths:
            if "orchestrator" not in config:
                config["orchestrator"] = {}
            if "context_paths" not in config["orchestrator"]:
                config["orchestrator"]["context_paths"] = []
            # Add the new paths (accumulate with existing)
            for ctx in context_paths:
                config["orchestrator"]["context_paths"].append(ctx)

        # Extract orchestrator config dict from YAML
        orchestrator_cfg = config.get("orchestrator", {})

        # Create agents from config with progress updates
        # Note: Multi-turn reuses existing session, so progress is less critical but nice to have
        num_agents = len(config.get("agents", []))

        # Create progress callback that sends WebSocket updates
        loop = asyncio.get_running_loop()

        async def emit_preparation_status(status: str, detail: str = "") -> None:
            """Emit preparation status update to web clients."""
            await manager.broadcast(
                session_id,
                {
                    "type": "preparation_status",
                    "status": status,
                    "detail": detail,
                    "session_id": session_id,
                },
            )

        await emit_preparation_status(
            "Initializing agents...",
            f"{num_agents} agent{'s' if num_agents != 1 else ''}",
        )

        def progress_callback(status: str, detail: str) -> None:
            """Thread-safe callback to queue progress updates."""
            asyncio.run_coroutine_threadsafe(
                emit_preparation_status(status, detail),
                loop,
            )

        # Run agent creation in thread pool so progress updates can be sent
        agents = await loop.run_in_executor(
            None,
            lambda: create_agents_from_config(
                config,
                orchestrator_config=orchestrator_cfg,
                config_path=str(resolved_path),
                memory_session_id=session_id,
                progress_callback=progress_callback,
                filesystem_session_id=session_id,
                session_storage_base=".massgen/sessions",
            ),
        )

        # Get agent IDs and model names
        # Sort for consistent anonymous mapping with coordination_tracker
        agent_ids = sorted(agents.keys())
        agent_models = {}
        for agent_id, agent in agents.items():
            # Try to get model name from agent - check multiple sources
            model_name = getattr(agent, "model", None)
            # For ConfigurableAgent, model is in config.backend_params["model"]
            if not model_name and hasattr(agent, "config") and agent.config:
                backend_params = getattr(agent.config, "backend_params", None)
                if backend_params:
                    model_name = backend_params.get("model")
            if model_name:
                agent_models[agent_id] = model_name

        # Create web display with agent_models
        display = manager.create_display(session_id, agent_ids, agent_models)

        # Build AgentConfig object for orchestrator
        orchestrator_config = AgentConfig()

        # Apply voting sensitivity if specified
        if "voting_sensitivity" in orchestrator_cfg:
            orchestrator_config.voting_sensitivity = orchestrator_cfg["voting_sensitivity"]

        # Apply answer count limit if specified
        if "max_new_answers_per_agent" in orchestrator_cfg:
            orchestrator_config.max_new_answers_per_agent = orchestrator_cfg["max_new_answers_per_agent"]

        # Apply answer novelty requirement if specified
        if "answer_novelty_requirement" in orchestrator_cfg:
            orchestrator_config.answer_novelty_requirement = orchestrator_cfg["answer_novelty_requirement"]

        # Apply coordination config from YAML (includes enable_agent_task_planning, etc.)
        coord_cfg = orchestrator_cfg.get("coordination", {})
        if coord_cfg:
            # Parse persona_generator config if present
            from massgen.persona_generator import PersonaGeneratorConfig

            persona_generator_config = PersonaGeneratorConfig()
            if "persona_generator" in coord_cfg:
                pg_cfg = coord_cfg["persona_generator"]
                persona_generator_config = PersonaGeneratorConfig(
                    enabled=pg_cfg.get("enabled", False),
                    diversity_mode=pg_cfg.get("diversity_mode", "perspective"),
                    persona_guidelines=pg_cfg.get("persona_guidelines"),
                    persist_across_turns=pg_cfg.get("persist_across_turns", False),
                )

            orchestrator_config.coordination_config = CoordinationConfig(
                enable_planning_mode=coord_cfg.get("enable_planning_mode", False),
                planning_mode_instruction=coord_cfg.get(
                    "planning_mode_instruction",
                    "During coordination, describe what you would do without actually executing actions.",
                ),
                max_orchestration_restarts=coord_cfg.get(
                    "max_orchestration_restarts",
                    0,
                ),
                enable_agent_task_planning=coord_cfg.get(
                    "enable_agent_task_planning",
                    False,
                ),
                max_tasks_per_plan=coord_cfg.get("max_tasks_per_plan", 10),
                broadcast=coord_cfg.get("broadcast", False),
                broadcast_sensitivity=coord_cfg.get("broadcast_sensitivity", "medium"),
                response_depth=coord_cfg.get("response_depth", "medium"),
                broadcast_timeout=coord_cfg.get("broadcast_timeout", 300),
                broadcast_wait_by_default=coord_cfg.get(
                    "broadcast_wait_by_default",
                    True,
                ),
                max_broadcasts_per_agent=coord_cfg.get("max_broadcasts_per_agent", 10),
                task_planning_filesystem_mode=coord_cfg.get(
                    "task_planning_filesystem_mode",
                    False,
                ),
                enable_memory_filesystem_mode=coord_cfg.get(
                    "enable_memory_filesystem_mode",
                    False,
                ),
                use_skills=coord_cfg.get("use_skills", False),
                massgen_skills=coord_cfg.get("massgen_skills", []),
                skills_directory=coord_cfg.get("skills_directory", ".agent/skills"),
                load_previous_session_skills=coord_cfg.get(
                    "load_previous_session_skills",
                    False,
                ),
                persona_generator=persona_generator_config,
                drift_conflict_policy=coord_cfg.get("drift_conflict_policy", "skip"),
            )

        # Get context sharing parameters
        snapshot_storage = orchestrator_cfg.get("snapshot_storage")
        agent_temporary_workspace = orchestrator_cfg.get("agent_temporary_workspace")

        # Create orchestrator with history from previous turns
        orchestrator = Orchestrator(
            agents=agents,
            config=orchestrator_config,
            session_id=session_id,
            snapshot_storage=snapshot_storage,
            agent_temporary_workspace=agent_temporary_workspace,
            previous_turns=previous_turns,
            winning_agents_history=winning_agents_history,
        )

        # Set up cancellation manager for WebUI cancellation support
        from massgen.cancellation import CancellationManager

        cancellation_mgr = CancellationManager()
        # Don't register signal handlers (WebUI uses API-based cancellation)
        # Just set the basic attributes so the orchestrator can check is_cancelled
        cancellation_mgr._orchestrator = orchestrator
        cancellation_mgr._cancelled = False
        orchestrator.cancellation_manager = cancellation_mgr

        # Store orchestrator reference for cancellation support
        manager.orchestrators[session_id] = orchestrator

        # Store the log session directory in the display
        display.log_session_dir = get_log_session_dir()
        print(
            f"[WebUI] run_coordination_with_history: turn={turn_number}, log_dir={display.log_session_dir}",
        )

        # Save execution metadata for session export/sharing (same as CLI)
        # Use raw_config_for_metadata to avoid logging expanded secrets
        if display.log_session_dir:
            save_execution_metadata(
                query=question,
                config_path=str(resolved_path),
                config_content=raw_config_for_metadata,
            )

            # IMPORTANT: Save initial status.json with workspace paths immediately
            # This allows the WebUI to display workspace files right away without waiting
            # for coordination to start
            # Run in executor to avoid blocking event loop
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    None,
                    orchestrator.coordination_tracker.save_status_file,
                    display.log_session_dir,
                    orchestrator,
                )
                print("[WebUI] Saved initial status.json with workspace paths")
            except Exception as e:
                print(f"[WebUI] Warning: Could not save initial status.json: {e}")

        # Create coordination UI with web display
        ui = CoordinationUI(
            display=display,
            display_type="web",
        )

        # Run coordination with conversation history (like CLI does)
        # Build messages list: previous Q&A pairs + current question
        messages = conversation_history.copy() if conversation_history else []
        messages.append({"role": "user", "content": question})

        if len(messages) > 1:
            # Multi-turn: use coordinate_with_context so agents see previous conversation
            print(
                f"[WebUI] Running coordination with {len(conversation_history)} history messages",
            )
            await ui.coordinate_with_context(orchestrator, question, messages)
        else:
            # First turn: standard coordination
            await ui.coordinate(orchestrator, question)

        # Save CLI-compatible metadata for this turn
        await _save_session_metadata(
            session_id=session_id,
            question=question,
            orchestrator=orchestrator,
            config_path=str(resolved_path),
            log_session_dir=display.log_session_dir,
            turn_number=turn_number,
        )

        # Broadcast completion
        await manager.broadcast(
            session_id,
            {
                "type": "coordination_complete",
                "session_id": session_id,
                "turn": turn_number,
            },
        )

        # Mark session as completed so it persists in session list
        manager.mark_session_completed(
            session_id,
            question=question,
            config=str(resolved_path) if resolved_path else None,
        )

        # Cleanup orchestrator reference on completion
        if session_id in manager.orchestrators:
            del manager.orchestrators[session_id]

    except asyncio.CancelledError:
        # Task was cancelled by user - don't broadcast completion or error
        print(f"[WebUI] Coordination cancelled for session {session_id} (turn {turn_number})")

        # Update status.json to show cancelled state
        try:
            from massgen.logger_config import get_log_session_dir

            log_dir = get_log_session_dir()
            if log_dir:
                status_file = log_dir / "status.json"
                if status_file.exists():
                    import json

                    with open(status_file) as f:
                        status_data = json.load(f)
                    status_data["coordination"] = status_data.get("coordination", {})
                    status_data["coordination"]["phase"] = "cancelled"
                    status_data["coordination"]["cancelled"] = True
                    status_data["coordination"]["cancelled_at"] = __import__("time").time()
                    with open(status_file, "w") as f:
                        json.dump(status_data, f, indent=2)
        except Exception as status_err:
            print(f"[WebUI] Warning: Could not update status.json: {status_err}")

        # Cleanup orchestrator reference
        if session_id in manager.orchestrators:
            del manager.orchestrators[session_id]

        # Broadcast cancellation
        await manager.broadcast(
            session_id,
            {
                "type": "coordination_cancelled",
                "session_id": session_id,
                "turn": turn_number,
                "message": "Coordination cancelled by user",
            },
        )
        # Re-raise to properly terminate the task
        raise

    except Exception as e:
        # Log the full traceback for debugging
        error_msg = f"{type(e).__name__}: {str(e)}"
        print(f"[WebUI Error] {error_msg}")
        traceback.print_exc()

        # Cleanup orchestrator reference on error
        if session_id in manager.orchestrators:
            del manager.orchestrators[session_id]

        # Broadcast error
        await manager.broadcast(
            session_id,
            {
                "type": "error",
                "message": error_msg,
                "session_id": session_id,
            },
        )


async def run_coordination(
    session_id: str,
    question: str,
    config_path: str | None = None,
    context_paths: list | None = None,
) -> None:
    """Run coordination with web display.

    Args:
        session_id: Session identifier
        question: Question for coordination
        config_path: Optional path to config YAML
        context_paths: Optional list of context paths from @path syntax
    """
    import traceback

    async def send_init_status(message: str, step: str, progress: int = 0) -> None:
        """Send initialization status to WebSocket clients."""
        await manager.broadcast(
            session_id,
            {
                "type": "init_status",
                "message": message,
                "step": step,
                "progress": progress,
                "session_id": session_id,
            },
        )

    async def emit_preparation_status(status: str, detail: str = "") -> None:
        """Emit preparation status update to web clients."""
        await manager.broadcast(
            session_id,
            {
                "type": "preparation_status",
                "status": status,
                "detail": detail,
                "session_id": session_id,
            },
        )

    try:
        # Emit initial preparation status
        await emit_preparation_status("Loading configuration...", config_path or "")

        # Import here to avoid circular imports
        from massgen.agent_config import AgentConfig, CoordinationConfig
        from massgen.cli import (
            create_agents_from_config,
            load_config_file,
            resolve_config_path,
        )
        from massgen.frontend.coordination_ui import CoordinationUI
        from massgen.orchestrator import Orchestrator

        # Send initial status
        await send_init_status("Loading configuration...", "config", 10)

        # Load config from YAML file
        if not config_path:
            raise ValueError("Config path is required")

        # Resolve config path (handles @examples/, paths, etc.)
        resolved_path = resolve_config_path(config_path)
        if resolved_path is None:
            raise ValueError(f"Could not resolve config path: {config_path}")

        config, raw_config_for_metadata = load_config_file(str(resolved_path))

        # Inject context paths from @path syntax if provided
        if context_paths:
            if "orchestrator" not in config:
                config["orchestrator"] = {}
            if "context_paths" not in config["orchestrator"]:
                config["orchestrator"]["context_paths"] = []
            # Add the new paths (accumulate with existing)
            for ctx in context_paths:
                config["orchestrator"]["context_paths"].append(ctx)

        # Extract orchestrator config dict from YAML
        orchestrator_cfg = config.get("orchestrator", {})

        # Send agent setup status (this is the slow part - Docker containers, etc.)
        agent_configs = config.get("agents", [])
        num_agents = len(agent_configs)
        await send_init_status(f"Setting up {num_agents} agents...", "agents", 30)

        # Check if Docker is being used
        uses_docker = config.get("execution", {}).get("use_docker", False)
        if uses_docker:
            await emit_preparation_status(
                "Preparing Docker environment...",
                "Setting up isolated containers",
            )

        # Create agents from config with progress updates
        await emit_preparation_status(
            "Initializing agents...",
            f"{num_agents} agent{'s' if num_agents != 1 else ''}",
        )

        # Create progress callback that sends WebSocket updates
        # We run agent creation in a thread so progress updates can be sent in real-time
        loop = asyncio.get_running_loop()

        def progress_callback(status: str, detail: str) -> None:
            """Thread-safe callback to queue progress updates."""
            # Schedule the async emit on the main event loop
            asyncio.run_coroutine_threadsafe(
                emit_preparation_status(status, detail),
                loop,
            )

        # Run agent creation in thread pool so progress updates can be sent
        agents = await loop.run_in_executor(
            None,
            lambda: create_agents_from_config(
                config,
                orchestrator_config=orchestrator_cfg,
                config_path=str(resolved_path),
                memory_session_id=session_id,
                progress_callback=progress_callback,
                filesystem_session_id=session_id,
                session_storage_base=".massgen/sessions",
            ),
        )

        # Get agent IDs and model names
        # Sort for consistent anonymous mapping with coordination_tracker
        agent_ids = sorted(agents.keys())
        agent_models = {}
        for agent_id, agent in agents.items():
            # Try to get model name from agent - check multiple sources
            model_name = getattr(agent, "model", None)
            # For ConfigurableAgent, model is in config.backend_params["model"]
            if not model_name and hasattr(agent, "config") and agent.config:
                backend_params = getattr(agent.config, "backend_params", None)
                if backend_params:
                    model_name = backend_params.get("model")
            if model_name:
                agent_models[agent_id] = model_name

        await send_init_status(
            f"Agents ready: {', '.join(agent_ids)}",
            "agents_ready",
            60,
        )

        # Emit status about loaded agents
        await emit_preparation_status(
            "Configuring orchestrator...",
            ", ".join(agent_ids),
        )

        # Create web display with agent_models
        display = manager.create_display(session_id, agent_ids, agent_models)

        await send_init_status("Initializing orchestrator...", "orchestrator", 80)

        # Build AgentConfig object for orchestrator (required by Orchestrator)
        orchestrator_config = AgentConfig()

        # Apply voting sensitivity if specified
        if "voting_sensitivity" in orchestrator_cfg:
            orchestrator_config.voting_sensitivity = orchestrator_cfg["voting_sensitivity"]

        # Apply answer count limit if specified
        if "max_new_answers_per_agent" in orchestrator_cfg:
            orchestrator_config.max_new_answers_per_agent = orchestrator_cfg["max_new_answers_per_agent"]

        # Apply answer novelty requirement if specified
        if "answer_novelty_requirement" in orchestrator_cfg:
            orchestrator_config.answer_novelty_requirement = orchestrator_cfg["answer_novelty_requirement"]

        # Apply coordination config from YAML (includes enable_agent_task_planning, etc.)
        coord_cfg = orchestrator_cfg.get("coordination", {})
        if coord_cfg:
            # Parse persona_generator config if present
            from massgen.persona_generator import PersonaGeneratorConfig

            persona_generator_config = PersonaGeneratorConfig()
            if "persona_generator" in coord_cfg:
                pg_cfg = coord_cfg["persona_generator"]
                persona_generator_config = PersonaGeneratorConfig(
                    enabled=pg_cfg.get("enabled", False),
                    diversity_mode=pg_cfg.get("diversity_mode", "perspective"),
                    persona_guidelines=pg_cfg.get("persona_guidelines"),
                    persist_across_turns=pg_cfg.get("persist_across_turns", False),
                )

            orchestrator_config.coordination_config = CoordinationConfig(
                enable_planning_mode=coord_cfg.get("enable_planning_mode", False),
                planning_mode_instruction=coord_cfg.get(
                    "planning_mode_instruction",
                    "During coordination, describe what you would do without actually executing actions.",
                ),
                max_orchestration_restarts=coord_cfg.get(
                    "max_orchestration_restarts",
                    0,
                ),
                enable_agent_task_planning=coord_cfg.get(
                    "enable_agent_task_planning",
                    False,
                ),
                max_tasks_per_plan=coord_cfg.get("max_tasks_per_plan", 10),
                broadcast=coord_cfg.get("broadcast", False),
                broadcast_sensitivity=coord_cfg.get("broadcast_sensitivity", "medium"),
                response_depth=coord_cfg.get("response_depth", "medium"),
                broadcast_timeout=coord_cfg.get("broadcast_timeout", 300),
                broadcast_wait_by_default=coord_cfg.get(
                    "broadcast_wait_by_default",
                    True,
                ),
                max_broadcasts_per_agent=coord_cfg.get("max_broadcasts_per_agent", 10),
                task_planning_filesystem_mode=coord_cfg.get(
                    "task_planning_filesystem_mode",
                    False,
                ),
                enable_memory_filesystem_mode=coord_cfg.get(
                    "enable_memory_filesystem_mode",
                    False,
                ),
                use_skills=coord_cfg.get("use_skills", False),
                massgen_skills=coord_cfg.get("massgen_skills", []),
                skills_directory=coord_cfg.get("skills_directory", ".agent/skills"),
                load_previous_session_skills=coord_cfg.get(
                    "load_previous_session_skills",
                    False,
                ),
                persona_generator=persona_generator_config,
                drift_conflict_policy=coord_cfg.get("drift_conflict_policy", "skip"),
            )

        # Get context sharing parameters
        snapshot_storage = orchestrator_cfg.get("snapshot_storage")
        agent_temporary_workspace = orchestrator_cfg.get("agent_temporary_workspace")

        # Create orchestrator with AgentConfig object
        orchestrator = Orchestrator(
            agents=agents,
            config=orchestrator_config,
            session_id=session_id,
            snapshot_storage=snapshot_storage,
            agent_temporary_workspace=agent_temporary_workspace,
        )

        # Set up cancellation manager for WebUI cancellation support
        from massgen.cancellation import CancellationManager

        cancellation_mgr = CancellationManager()
        # Don't register signal handlers (WebUI uses API-based cancellation)
        # Just set the basic attributes so the orchestrator can check is_cancelled
        cancellation_mgr._orchestrator = orchestrator
        cancellation_mgr._cancelled = False
        orchestrator.cancellation_manager = cancellation_mgr

        # Store orchestrator reference for cancellation support
        manager.orchestrators[session_id] = orchestrator

        # Store the log session directory in the display BEFORE coordination
        # This ensures the API can find it when coordination_complete is sent
        from massgen.logger_config import get_log_session_dir, save_execution_metadata

        display.log_session_dir = get_log_session_dir()
        print(
            f"[DEBUG] run_coordination: Set display.log_session_dir = {display.log_session_dir}",
        )

        # Print status.json location for automation mode monitoring
        if display.log_session_dir:
            print(f"LOG_DIR: {display.log_session_dir}")
            print(f"STATUS: {display.log_session_dir / 'status.json'}")

            # Save execution metadata for session export/sharing (same as CLI)
            # Use raw_config_for_metadata to avoid logging expanded secrets
            save_execution_metadata(
                query=question,
                config_path=str(resolved_path),
                config_content=raw_config_for_metadata,
            )

            # IMPORTANT: Save initial status.json with workspace paths immediately
            # This allows the WebUI to display workspace files right away without waiting
            # for coordination to start
            # Run in executor to avoid blocking event loop
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    None,
                    orchestrator.coordination_tracker.save_status_file,
                    display.log_session_dir,
                    orchestrator,
                )
                print("[WebUI] Saved initial status.json with workspace paths")
            except Exception as e:
                print(f"[WebUI] Warning: Could not save initial status.json: {e}")

        # Create coordination UI with web display
        ui = CoordinationUI(
            display=display,
            display_type="web",
        )

        await send_init_status("Starting coordination...", "starting", 100)

        # Final preparation status before starting
        await emit_preparation_status(
            "Launching agents...",
            "Agents will appear momentarily",
        )

        # Run coordination
        await ui.coordinate(orchestrator, question)

        # Save CLI-compatible metadata for multi-turn continuation
        await _save_session_metadata(
            session_id=session_id,
            question=question,
            orchestrator=orchestrator,
            config_path=str(resolved_path),
            log_session_dir=display.log_session_dir,
        )

        # Broadcast completion
        await manager.broadcast(
            session_id,
            {
                "type": "coordination_complete",
                "session_id": session_id,
            },
        )

        # Mark session as completed so it persists in session list
        manager.mark_session_completed(
            session_id,
            question=question,
            config=str(resolved_path) if resolved_path else None,
        )

        # Cleanup orchestrator reference on completion
        if session_id in manager.orchestrators:
            del manager.orchestrators[session_id]

    except asyncio.CancelledError:
        # Task was cancelled by user - don't broadcast completion or error
        print(f"[WebUI] Coordination cancelled for session {session_id}")

        # Update status.json to show cancelled state
        try:
            from massgen.logger_config import get_log_session_dir

            log_dir = get_log_session_dir()
            if log_dir:
                status_file = log_dir / "status.json"
                if status_file.exists():
                    import json

                    with open(status_file) as f:
                        status_data = json.load(f)
                    status_data["coordination"] = status_data.get("coordination", {})
                    status_data["coordination"]["phase"] = "cancelled"
                    status_data["coordination"]["cancelled"] = True
                    status_data["coordination"]["cancelled_at"] = __import__("time").time()
                    with open(status_file, "w") as f:
                        json.dump(status_data, f, indent=2)
        except Exception as status_err:
            print(f"[WebUI] Warning: Could not update status.json: {status_err}")

        # Cleanup orchestrator reference
        if session_id in manager.orchestrators:
            del manager.orchestrators[session_id]

        # Broadcast cancellation (already done by cancel endpoint, but ensure it's sent)
        await manager.broadcast(
            session_id,
            {
                "type": "coordination_cancelled",
                "session_id": session_id,
                "message": "Coordination cancelled by user",
            },
        )
        # Re-raise to properly terminate the task
        raise

    except Exception as e:
        # Log the full traceback for debugging
        error_msg = f"{type(e).__name__}: {str(e)}"
        print(f"[WebUI Error] {error_msg}")
        traceback.print_exc()

        # Cleanup orchestrator reference on error
        if session_id in manager.orchestrators:
            del manager.orchestrators[session_id]

        # Broadcast error
        await manager.broadcast(
            session_id,
            {
                "type": "error",
                "message": error_msg,
                "session_id": session_id,
            },
        )


def run_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
    config_path: str | None = None,
    automation_mode: bool = False,
) -> None:
    """Run the web server.

    Args:
        host: Host to bind to
        port: Port to listen on
        reload: Enable auto-reload for development
        config_path: Default config path for coordination sessions
        automation_mode: If True, UI shows automation-friendly timeline view
    """
    try:
        import uvicorn
    except ImportError:
        raise ImportError(
            "uvicorn is not installed. Install with: pip install massgen",
        )

    # Set default config before starting server
    if config_path:
        set_default_config(config_path)

    # Create app directly with automation_mode (can't pass args via factory string)
    app = create_app(config_path=config_path, automation_mode=automation_mode)

    # In automation mode, suppress verbose logging to keep stdout clean
    if automation_mode:
        import logging
        import warnings

        # Suppress uvicorn access logs and info messages
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

        # Suppress websockets deprecation warnings
        warnings.filterwarnings(
            "ignore",
            category=DeprecationWarning,
            module="websockets",
        )
        warnings.filterwarnings(
            "ignore",
            category=DeprecationWarning,
            module="uvicorn.protocols.websockets",
        )

        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="warning",
        )
    else:
        uvicorn.run(
            app,
            host=host,
            port=port,
        )


# For running directly: python -m massgen.frontend.web.server
if __name__ == "__main__":
    run_server()
