"""Antigravity CLI Backend - subprocess wrapper for Google's `agy` CLI.

The Antigravity CLI (a.k.a. `agy`, released at Google I/O 2026) is the
successor to Gemini CLI for consumer tiers as of 2026-06-18. It is a Go
binary installed by `https://antigravity.google/cli/install.sh` to
``~/.local/bin/agy`` and self-updates from there.

Compared to GeminiCLIBackend this wrapper is intentionally minimal:

- No ``--output-format stream-json``: agy emits plain text on stdout. We
  tail the per-session ``transcript.jsonl`` written by agy under
  ``<cwd>/.antigravity/antigravity-cli/brain/<uuid>/.system_generated/logs/``
  concurrently with the subprocess to get real-time thinking + tool events,
  and forward stdout lines as content chunks on process exit.
- ``--model``: agy 1.0.5+ exposes a real ``--model`` flag taking an exact
  label from ``agy models`` (e.g. ``"Gemini 3.5 Flash (High)"``). The
  configured ``model`` is resolved to such a label (exact or via alias) and
  passed through; unrecognizable ids fall back to agy's default rather than
  failing the call. See ``AGY_MODEL_LABELS`` / ``AGY_MODEL_ALIASES``.
- ``--conversation <id>`` replaces ``--resume <id>``.
- ``--dangerously-skip-permissions`` replaces ``--approval-mode yolo``.
- Per-project isolation via the hidden ``--gemini_dir <abs_path>`` flag (not
  shown in ``--help`` but exposed by the binary's flag table and verified
  live). Each session writes MCP config + settings to ``<cwd>/.antigravity/``
  and never mutates the user's ``~/.gemini/``.
- MCP server entries use ``serverUrl`` (not ``url``) for HTTP servers per
  agy's ``mcp_config.json`` schema.

Authentication: agy honors the existing Google OAuth login at
``~/.gemini/google_accounts.json``. ``GEMINI_API_KEY`` / ``GOOGLE_API_KEY``
are passed through to the subprocess env so future API-key auth (if added
by Google) works transparently.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from ..logger_config import logger
from ._streaming_buffer_mixin import StreamingBufferMixin
from .base import FilesystemSupport, LLMBackend, StreamChunk
from .native_tool_mixin import NativeToolBackendMixin

AGY_DEFAULT_MODEL_LABEL = "Gemini 3.5 Flash (High)"
AGY_AGENT_ID_LITERAL = "antigravity_cli"
AGY_MCP_CONFIG_PATH = Path.home() / ".gemini" / "config" / "mcp_config.json"

# Exact model labels accepted by `agy --model` (source of truth: `agy models`).
# agy 1.0.5+ exposes a real ``--model`` flag that takes one of these strings
# verbatim; anything else is rejected. Keep in sync with `agy models` output.
AGY_MODEL_LABELS: tuple[str, ...] = (
    "Gemini 3.5 Flash (Low)",
    "Gemini 3.5 Flash (Medium)",
    "Gemini 3.5 Flash (High)",
    "Gemini 3.1 Pro (Low)",
    "Gemini 3.1 Pro (High)",
    "Claude Sonnet 4.6 (Thinking)",
    "Claude Opus 4.6 (Thinking)",
    "GPT-OSS 120B (Medium)",
)

# Deterministic alias map: short config ids → canonical agy label. This is an
# explicit id-normalization table (registry-style), NOT heuristic similarity
# matching. A bare family id maps to the highest-effort variant by default.
AGY_MODEL_ALIASES: dict[str, str] = {
    "gemini-3.5-flash": "Gemini 3.5 Flash (High)",
    "gemini-3.5-flash-high": "Gemini 3.5 Flash (High)",
    "gemini-3.5-flash-medium": "Gemini 3.5 Flash (Medium)",
    "gemini-3.5-flash-low": "Gemini 3.5 Flash (Low)",
    "gemini-3.1-pro": "Gemini 3.1 Pro (High)",
    "gemini-3.1-pro-high": "Gemini 3.1 Pro (High)",
    "gemini-3.1-pro-low": "Gemini 3.1 Pro (Low)",
    "claude-sonnet-4.6": "Claude Sonnet 4.6 (Thinking)",
    "claude-opus-4.6": "Claude Opus 4.6 (Thinking)",
    "gpt-oss-120b": "GPT-OSS 120B (Medium)",
}

# Mirrors gemini_cli.py:48-52 so workflow-mode inference behaves identically
# across both Google-CLI backends. The orchestrator embeds prior-round
# candidate answers in a `<CURRENT ANSWERS from the agents>…<END OF CURRENT
# ANSWERS>` block in the user message; we use it to know whether `vote`
# would be a valid action this turn.
_RE_CURRENT_ANSWERS = re.compile(
    r"<CURRENT ANSWERS from the agents>(.*?)<END OF CURRENT ANSWERS>",
    re.IGNORECASE | re.DOTALL,
)
_RE_AGENT_TAG = re.compile(r"<agent[^>]*>", re.IGNORECASE)


class AntigravityCLIBackend(NativeToolBackendMixin, StreamingBufferMixin, LLMBackend):
    """Antigravity CLI backend wrapping the `agy` Go binary.

    Inherits ``NativeToolBackendMixin`` for native-hook adapter wiring and
    ``StreamingBufferMixin`` for context-compression recovery. Hooks use the
    ``AntigravityCLINativeHookAdapter`` (a thin subclass of the Gemini CLI
    adapter): the hook *payload* shape is identical to Gemini CLI's
    (``{"hooks": {"BeforeTool": [...], "AfterTool": [...]}}``, subprocess
    JSON-stdin/stdout IPC), but agy reads it from a **standalone
    ``hooks.json``** gated by ``enableJsonHooks: true`` in ``settings.json`` —
    NOT embedded under ``settings.json["hooks"]`` the way Gemini CLI does. See
    :meth:`_write_hooks_json` / :meth:`get_native_hook_adapter`.
    """

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(api_key, **kwargs)
        self.__init_native_tool_mixin__()
        self._init_native_hook_adapter(
            "massgen.mcp_tools.native_hook_adapters.antigravity_cli_adapter.AntigravityCLINativeHookAdapter",
        )

        configured_env = self._get_configured_credentials_env() if hasattr(self, "_get_configured_credentials_env") else {}
        self.api_key = (
            api_key
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
            or (configured_env.get("GEMINI_API_KEY") if configured_env else None)
            or (configured_env.get("GOOGLE_API_KEY") if configured_env else None)
        )

        # agy supports OAuth-only auth via ~/.gemini/google_accounts.json; an
        # API key is *also* honored (passed through) but not required.
        self.use_login = not bool(self.api_key)

        self.dangerously_skip_permissions: bool = kwargs.get(
            "dangerously_skip_permissions",
            kwargs.get("approval_mode", "yolo") == "yolo",
        )
        self.disable_auto_update: bool = kwargs.get("disable_auto_update", True)

        # agy 1.0.5+ has a real --model flag; the configured model is resolved
        # to an exact `agy models` label at command-build time. Warn early if
        # it won't resolve so the operator knows agy will use its default.
        self.model = kwargs.get("model", AGY_DEFAULT_MODEL_LABEL)
        if kwargs.get("model") and self._resolve_agy_model_label(self.model) is None:
            logger.warning(
                f"Antigravity CLI: configured model '{self.model}' does not map to a " "known `agy models` label; agy will use its default model. Valid " f"labels: {list(AGY_MODEL_LABELS)}",
            )

        self._config_cwd = kwargs.get("cwd")
        self.system_prompt = kwargs.get("system_prompt", "")
        self.agent_id = kwargs.get("agent_id")

        # Monotonic sequence for MCP-middleware hook payloads (parity with codex).
        self._hook_sequence = 0

        configured_mcp_servers = kwargs.get("mcp_servers", [])
        self.mcp_servers: list[dict[str, Any]] = list(configured_mcp_servers) if isinstance(configured_mcp_servers, list) else []

        # Workspace-local MCP config (managed via --gemini_dir).
        self._mcp_config_managed_names: set[str] = set()

        # Workflow-mode state — ported from gemini_cli.py:105-109. Tracks whether
        # `vote` is a valid action this turn (depends on whether prior rounds
        # produced candidate answers) and whether we've already accepted a
        # workflow tool call in the current stream (dedup against double-emits).
        self._workflow_call_mode: str = "any"
        self._workflow_call_emitted_this_turn: bool = False
        self._last_turn_missing_workflow_call: bool = False

        # Docker mode: agy's OAuth token state lives in HOME-scoped storage that
        # doesn't cross container boundaries. Require an API key instead.
        self._docker_execution = kwargs.get("command_line_execution_mode") == "docker"
        if self._docker_execution and not self.api_key:
            raise RuntimeError(
                "Antigravity CLI Docker mode requires GEMINI_API_KEY or "
                "GOOGLE_API_KEY in the environment (OAuth state doesn't cross "
                "container boundaries). Set the API key in your shell or your "
                "agent config, then re-run.",
            )

        self._agy_path = self._find_agy_cli()
        if not self._agy_path:
            raise RuntimeError(
                "Antigravity CLI ('agy') not found. Install with:\n"
                "  curl -fsSL https://antigravity.google/cli/install.sh | bash\n"
                "Default install path is ~/.local/bin/agy. "
                "Run `agy --version` to verify.",
            )

        # Synchronous binary health check: confirm `agy --version` runs cleanly.
        # Catches stale/corrupt installs (binary file exists but doesn't execute)
        # before the orchestrator throws this agent into coordination.
        # Cheap (~50ms, no API call) and the only way to fail fast on a broken
        # binary — full auth verification would require a real call.
        skip_health_check = kwargs.get("skip_health_check", False)
        if not skip_health_check:
            self._verify_agy_binary_runs()

    def _has_cached_credentials(self) -> bool:
        """True iff agy has a usable credential path available.

        Parity with gemini_cli.py:255. agy honors:
        - ``GEMINI_API_KEY`` / ``GOOGLE_API_KEY`` env (passed through subprocess)
        - ``~/.gemini/google_accounts.json`` (Google OAuth login)
        - ``~/.gemini/oauth_creds.json`` (alternate OAuth cache)
        Returning False means the next ``agy -p`` call will hit the silent
        UNAUTHENTICATED path our log scanner catches; we'd rather fail fast.
        """
        if self.api_key:
            return True
        gemini_home = Path.home() / ".gemini"
        return (gemini_home / "google_accounts.json").exists() or (gemini_home / "oauth_creds.json").exists()

    async def _ensure_authenticated(self) -> None:
        """Raise if no credential source is available before launching agy.

        Mirrors gemini_cli.py:262. Avoids burning a coordination round on an
        empty agy run when the user just hasn't logged in / set an API key.
        """
        if self._has_cached_credentials():
            return
        raise RuntimeError(
            "Antigravity CLI not authenticated. Run `agy` interactively to log in, " "or set GEMINI_API_KEY or GOOGLE_API_KEY in your environment.",
        )

    def _verify_agy_binary_runs(self) -> None:
        """Run ``agy --version`` and raise if the binary is unusable.

        Surfaces a clear error at construction time instead of letting the
        first orchestration call burn a round on a broken install.
        """
        import subprocess

        try:
            result = subprocess.run(
                [self._agy_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(
                f"Antigravity CLI ('agy' at {self._agy_path}) is installed but "
                f"won't run: {exc}. Try `{self._agy_path} --version` manually, "
                "or reinstall with `curl -fsSL https://antigravity.google/cli/install.sh | bash`.",
            ) from exc
        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(
                f"Antigravity CLI ('agy' at {self._agy_path}) exited with code "
                f"{result.returncode} on `--version`. Output: {stderr or '(empty)'}. "
                "Try reinstalling with `curl -fsSL https://antigravity.google/cli/install.sh | bash`.",
            )
        version = (result.stdout or "").strip()
        logger.info(f"Antigravity CLI: binary health check passed (agy version {version})")

    @property
    def cwd(self) -> str:
        if self.filesystem_manager:
            return str(Path(str(self.filesystem_manager.get_current_workspace())).resolve())
        return self._config_cwd or os.getcwd()

    # ── Binary discovery ──────────────────────────────────────────────────

    @staticmethod
    def _find_agy_cli() -> str | None:
        """Locate the agy binary. Returns absolute path or None."""
        on_path = shutil.which("agy")
        if on_path:
            return on_path
        candidates = [
            Path.home() / ".local" / "bin" / "agy",
            Path("/usr/local/bin/agy"),
            Path("/opt/homebrew/bin/agy"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return None

    @staticmethod
    def _resolve_agy_model_label(model: str | None) -> str | None:
        """Resolve a configured model id to an exact ``agy --model`` label.

        agy 1.0.5+ accepts ``--model`` but only with one of the exact strings
        from ``agy models`` (``AGY_MODEL_LABELS``). We accept either an exact
        label (case-insensitive) or a short alias (``AGY_MODEL_ALIASES``).
        Returns ``None`` for anything unresolvable so the caller omits
        ``--model`` and lets agy fall back to its default instead of failing
        the whole call on a rejected label.
        """
        if not model or not isinstance(model, str):
            return None
        raw = model.strip()
        if not raw:
            return None
        for label in AGY_MODEL_LABELS:
            if raw.lower() == label.lower():
                return label
        norm = re.sub(r"[\s_]+", "-", raw.lower())
        return AGY_MODEL_ALIASES.get(norm)

    # ── MCP config ────────────────────────────────────────────────────────

    def _build_mcp_config_dict(self) -> dict[str, Any]:
        """Translate MassGen MCP server entries to agy's mcp_config.json schema.

        agy uses ``serverUrl`` for HTTP servers (not ``url``) and
        ``command``/``args``/``env`` for stdio. SDK-only entries are excluded.
        """
        merged: dict[str, Any] = {}
        config_mcp = self.config.get("mcp_servers") if self.config else None

        servers: list[dict[str, Any]] = []
        if isinstance(config_mcp, dict):
            for name, srv in config_mcp.items():
                if isinstance(srv, dict) and srv.get("type") != "sdk":
                    srv = dict(srv)
                    srv["name"] = name
                    servers.append(srv)
        elif isinstance(config_mcp, list):
            servers.extend(s for s in config_mcp if isinstance(s, dict))

        existing_names = {s.get("name") for s in servers if s.get("name")}
        for s in self.mcp_servers:
            if isinstance(s, dict) and s.get("name") and s.get("name") not in existing_names:
                servers.append(s)
                existing_names.add(s.get("name"))

        for srv in servers:
            name = srv.get("name")
            if not name or srv.get("type") == "sdk":
                continue
            entry: dict[str, Any] = {}
            if srv.get("command"):
                entry["command"] = srv["command"]
            if srv.get("args"):
                entry["args"] = list(srv["args"])
            if srv.get("env"):
                entry["env"] = dict(srv["env"])
            # HTTP servers: agy expects `serverUrl`, not `url`. Accept either
            # in the source config and emit the canonical key.
            http_url = srv.get("serverUrl") or srv.get("url") or srv.get("httpUrl")
            if http_url:
                entry["serverUrl"] = http_url
                if srv.get("headers"):
                    entry["headers"] = dict(srv["headers"])
            if entry:
                merged[name] = entry

        return merged

    def _workspace_config_dir(self) -> Path:
        """Project-scoped agy data root, passed via ``--gemini_dir``."""
        return Path(self.cwd).resolve() / ".antigravity"

    def _workspace_project_marker_dir(self) -> Path:
        """Workspace-anchor for agy's project discovery walk.

        agy walks UP from cwd looking for ``.antigravitycli/`` to decide the
        project root. Without an anchor at the workspace level, agy adopts
        whichever ancestor directory happens to contain one — which can be
        a sibling MassGen agent's leftover or even the user's repo root if
        anyone has ever run ``agy`` interactively there. The wrong project
        root makes ``--add-dir`` ineffective: agy still routes
        ``write_to_file`` into its internal scratch directory, hidden from
        peers and snapshot promotion.

        Pre-creating an empty ``.antigravitycli/`` at the workspace stops
        the upward walk here (verified live).
        """
        return Path(self.cwd).resolve() / ".antigravitycli"

    def _ensure_workspace_project_marker(self) -> None:
        """Idempotently create the workspace project-discovery anchor."""
        marker = self._workspace_project_marker_dir()
        try:
            marker.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning(
                f"Antigravity CLI: could not create project marker {marker}: {exc} " "— agy may walk up to a parent's .antigravitycli and adopt the wrong project",
            )

    def _workspace_mcp_config_path(self) -> Path:
        """Where to drop our merged mcp_config.json so agy reads it."""
        return self._workspace_config_dir() / "config" / "mcp_config.json"

    def _write_mcp_config(self) -> None:
        """Write MassGen MCP servers into the workspace-local mcp_config.json.

        Because we pass ``--gemini_dir <workspace>`` to agy, this is the file
        agy reads — the user's global ``~/.gemini/config/mcp_config.json`` is
        never touched. Cleanup just removes the workspace file.
        """
        new_servers = self._build_mcp_config_dict()
        if not new_servers:
            return

        path = self._workspace_mcp_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"mcpServers": new_servers}, indent=2), encoding="utf-8")
        self._mcp_config_managed_names = set(new_servers.keys())
        logger.info(
            f"Antigravity CLI: wrote {len(new_servers)} MCP server(s) to {path} " f"(servers: {sorted(self._mcp_config_managed_names)})",
        )

    def _restore_mcp_config(self) -> None:
        """Remove the workspace-local mcp_config.json written by this backend."""
        path = self._workspace_mcp_config_path()
        if path.exists():
            try:
                path.unlink()
                logger.info(f"Antigravity CLI: removed workspace {path}")
            except OSError as exc:
                logger.warning(f"Antigravity CLI: failed to remove {path}: {exc}")
        self._mcp_config_managed_names = set()

    def _workspace_agents_md_path(self) -> Path:
        """Path to AGENTS.md in the agent workspace.

        agy loads ``AGENTS.md``/``GEMINI.md`` from the workspace root as
        persistent context. We use this as the system-prompt channel since
        ``agy -p`` has no separate system message input.
        """
        return Path(self.cwd).resolve() / "AGENTS.md"

    def _workspace_agents_md_backup_path(self) -> Path:
        return Path(self.cwd).resolve() / ".AGENTS.md.massgen_backup"

    def _write_system_prompt_md(self) -> None:
        """Write the MassGen system prompt to <cwd>/AGENTS.md atomically.

        agy treats AGENTS.md as persistent workspace context (not as the user
        request), so the model sees coordination/workflow instructions in the
        right channel instead of inside ``<USER_REQUEST>``. Backs up any
        pre-existing AGENTS.md so :meth:`_restore_system_prompt_md` can put
        the original back.

        Atomic-write semantics: writes to ``AGENTS.md.massgen_tmp`` first,
        then ``os.replace()`` onto the target. If we're killed between the
        backup-rename and the new-content write, the backup still exists and
        :meth:`_restore_system_prompt_md` recovers cleanly.
        """
        if not self.system_prompt:
            return
        path = self._workspace_agents_md_path()
        backup = self._workspace_agents_md_backup_path()
        tmp_path = path.with_suffix(path.suffix + ".massgen_tmp")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not backup.exists():
            try:
                path.replace(backup)
                logger.info(f"Antigravity CLI: backed up existing {path} -> {backup}")
            except OSError as exc:
                logger.warning(f"Antigravity CLI: could not back up {path}: {exc}")
        tmp_path.write_text(self.system_prompt, encoding="utf-8")
        os.replace(tmp_path, path)
        logger.info(
            f"Antigravity CLI: wrote system prompt ({len(self.system_prompt)} chars) to {path}",
        )

    def _restore_system_prompt_md(self) -> None:
        """Restore the user's original AGENTS.md, or remove ours if none existed.

        Best-effort: never raises. Cleans up our temp file if a previous call
        was killed mid-write (rare but possible if the orchestrator cancels
        the streaming generator).
        """
        path = self._workspace_agents_md_path()
        backup = self._workspace_agents_md_backup_path()
        tmp_path = path.with_suffix(path.suffix + ".massgen_tmp")
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError as exc:
            logger.warning(f"Antigravity CLI: failed to remove stale {tmp_path}: {exc}")
        try:
            if backup.exists():
                backup.replace(path)
                logger.info(f"Antigravity CLI: restored original AGENTS.md from {backup}")
            elif path.exists():
                path.unlink()
                logger.info(f"Antigravity CLI: removed managed {path}")
        except OSError as exc:
            logger.warning(f"Antigravity CLI: failed to clean up AGENTS.md: {exc}")

    def _workspace_hooks_json_path(self) -> Path:
        """Path to agy's standalone hooks.json file.

        Unlike Gemini CLI (which embeds hooks under ``"hooks"`` inside
        ``settings.json``), agy 1.0.x reads hooks from a separate file.
        Binary strings confirm: ``Loaded hooks.json from %s``,
        ``No hooks.json found at %s``, ``failed to parse hooks.json``.
        Subject to ``enableJsonHooks: true`` in settings.json (also
        confirmed by ``json-hooks-enabled`` / ``EnableJsonHooks`` literals).
        """
        return self._workspace_config_dir() / "hooks.json"

    def _write_workspace_settings_json(self, has_hooks: bool = False) -> None:
        """Write a minimal settings.json in the workspace config dir.

        In Docker mode (or any time we have an API key but no host OAuth
        login), this forces agy to use `selectedType: "gemini-api-key"` so it
        won't try to start the OAuth flow inside a headless container. The key
        itself is provided via the ``GEMINI_API_KEY`` env var, not in this file.

        When ``has_hooks=True``, also sets ``enableJsonHooks: true`` so agy
        will pick up our workspace ``hooks.json``. Without this gate agy's
        log shows ``skipping hooks.json at %s`` instead of ``Loaded hooks.json``.
        """
        config_dir = self._workspace_config_dir()
        config_dir.mkdir(parents=True, exist_ok=True)
        settings_path = config_dir / "settings.json"
        settings: dict[str, Any] = {}
        if settings_path.exists():
            try:
                raw = settings_path.read_text(encoding="utf-8").strip()
                if raw:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        settings = parsed
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(
                    f"Antigravity CLI: could not parse existing {settings_path} " f"({exc}); overwriting.",
                )
        if self._docker_execution or self.api_key:
            settings.setdefault("security", {}).setdefault("auth", {})["selectedType"] = "gemini-api-key"
        if has_hooks:
            settings["enableJsonHooks"] = True
        settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")

    def _write_hooks_json(self) -> bool:
        """Write a workspace-local hooks.json built from MassGen's hook adapter.

        Returns True iff a non-empty hooks payload was written (caller uses
        this to decide whether to set ``enableJsonHooks`` in settings.json).
        """
        adapter = self._native_hook_adapter if hasattr(self, "_native_hook_adapter") else None
        if not adapter:
            return False
        # Hook adapter needs to know where its IPC dir lives. Mirror the
        # gemini_cli pattern (gemini_cli.py:1163-1164) but use our
        # workspace config dir.
        if hasattr(adapter, "hook_dir"):
            adapter.hook_dir = self._workspace_config_dir()
        if not self._massgen_hooks_config or not hasattr(adapter, "build_native_hooks_config"):
            return False
        try:
            from ..mcp_tools.hooks import (  # noqa: F401 — type ref for clarity
                GeneralHookManager,
            )
        except ImportError:
            pass
        # The orchestrator already converted MassGen hooks to the native
        # config shape via `set_native_hooks_config`; reuse that here.
        hooks_payload = self._massgen_hooks_config
        if not hooks_payload or not hooks_payload.get("hooks"):
            return False
        hooks_path = self._workspace_hooks_json_path()
        hooks_path.parent.mkdir(parents=True, exist_ok=True)
        hooks_path.write_text(json.dumps(hooks_payload, indent=2), encoding="utf-8")
        logger.info(
            f"Antigravity CLI: wrote hooks.json to {hooks_path} " f"(events: {sorted(hooks_payload.get('hooks', {}).keys())})",
        )
        return True

    def _restore_hooks_json(self) -> None:
        """Remove the workspace-local hooks.json written by this backend."""
        hooks_path = self._workspace_hooks_json_path()
        if hooks_path.exists():
            try:
                hooks_path.unlink()
                logger.info(f"Antigravity CLI: removed workspace {hooks_path}")
            except OSError as exc:
                logger.warning(f"Antigravity CLI: failed to remove {hooks_path}: {exc}")

    def get_native_hook_adapter(self) -> Any | None:
        """Return the native hook adapter with ``hook_dir`` wired to the workspace.

        The orchestrator fetches the adapter via this accessor immediately
        before calling ``adapter.build_native_hooks_config(...)`` during per-round
        hook setup — which happens BEFORE our stream ever runs
        :meth:`_write_hooks_json` (the old, lazy place ``hook_dir`` got set). If
        ``hook_dir`` is still ``None`` at build time, ``build_native_hooks_config``
        returns ``{}`` and that round runs with **no** MassGen native hooks. On a
        fresh backend this bit the **initial-answer round** specifically: the
        ``[GeminiCLINativeHookAdapter] No hook_dir set`` warning fired once, no
        ``hooks.json`` was written, and only round 2+ recovered (because the
        adapter instance persisted the ``hook_dir`` set by round 1's stream).

        Setting it here closes that gap. By the time the orchestrator runs,
        ``filesystem_manager`` is attached so :meth:`cwd` is correct — unlike
        ``__init__`` (gemini_cli.py:92-95), where the workspace isn't known yet
        and a construction-time path would be baked into the hook command.
        """
        adapter = self._native_hook_adapter
        if adapter is not None and hasattr(adapter, "hook_dir"):
            adapter.hook_dir = self._workspace_config_dir()
        return adapter

    # ── MCP-server-hook (mid-stream injection) payload IPC ─────────────────
    #
    # Parity with codex.py: the orchestrator's per-chunk flush
    # (`_flush_codex_hook_payloads`, backend-agnostic — gated only on
    # `write_post_tool_use_hook` + `supports_mcp_server_hooks()`) writes pending
    # peer/steering content here, and the `MassGenHookMiddleware` attached to
    # agy's MassGen MCP servers appends it to the next MCP tool result. This is
    # the only mid-stream channel that doesn't depend on the CLI firing native
    # hooks (agy's native hooks are trust-gated and inert headlessly). NOTE: live
    # end-to-end delivery shares the unresolved Codex MCP-client gap — see
    # test_codex_middleware_firing_live.py; the middleware itself is verified
    # (test_mcp_hook_middleware).

    def supports_mcp_server_hooks(self) -> bool:
        """agy uses MCP server middleware for PostToolUse injection (parity with codex)."""
        return True

    def get_hook_dir(self) -> Path:
        """Directory for hook IPC files — the workspace agy config dir.

        Must match the ``--hook-dir`` the MassGen MCP servers attached to agy are
        launched with, so the middleware reads the same file this writes.
        """
        return self._workspace_config_dir()

    def write_post_tool_use_hook(
        self,
        content: str,
        tool_matcher: str = "*",
        ttl_seconds: float = 30.0,
    ) -> None:
        """Atomic write of hook_post_tool_use.json for the MCP middleware to consume."""
        self._hook_sequence += 1
        hook_dir = self.get_hook_dir()
        hook_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "inject": {"content": content, "strategy": "tool_result"},
            "tool_matcher": tool_matcher,
            "expires_at": time.time() + ttl_seconds,
            "sequence": self._hook_sequence,
        }
        hook_file = hook_dir / "hook_post_tool_use.json"
        tmp_file = hook_file.with_suffix(".tmp")
        tmp_file.write_text(json.dumps(payload), encoding="utf-8")
        tmp_file.replace(hook_file)
        logger.info(f"Antigravity CLI: wrote hook_post_tool_use.json (seq={self._hook_sequence}, {len(content)} chars)")

    def read_unconsumed_hook_content(self) -> str | None:
        """Read+remove an unconsumed hook payload (round-end carryforward)."""
        hook_file = self.get_hook_dir() / "hook_post_tool_use.json"
        try:
            data = json.loads(hook_file.read_text(encoding="utf-8"))
            hook_file.unlink(missing_ok=True)
            content = data.get("inject", {}).get("content")
            if content:
                logger.info(f"Antigravity CLI: read unconsumed hook content ({len(content)} chars) — carrying forward")
            return content
        except FileNotFoundError:
            return None
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"Antigravity CLI: failed reading unconsumed hook file: {exc}")
            hook_file.unlink(missing_ok=True)
            return None

    def clear_hook_files(self) -> None:
        """Remove stale hook IPC files at turn start."""
        hook_dir = self.get_hook_dir()
        for filename in ("hook_post_tool_use.json", "hook_post_tool_use.tmp"):
            (hook_dir / filename).unlink(missing_ok=True)

    # ── Command construction ──────────────────────────────────────────────

    def _agy_log_file_path(self) -> Path:
        """Per-call log file path agy writes via ``--log-file``.

        agy treats backend errors (quota 429, auth failures, etc.) as
        non-fatal — it exits with code 0 and an empty stdout. We capture the
        log so we can surface the real reason instead of an empty retry loop.
        """
        return self._workspace_config_dir() / "antigravity-cli" / "agy.log"

    def _build_exec_command(self, prompt: str) -> list[str]:
        """Build the agy subprocess command for non-interactive print mode.

        Always passes ``--gemini_dir <abs_path>`` so agy reads our workspace-local
        config (mcp_config.json, settings.json) instead of the user's global one.

        Always passes ``--add-dir <cwd>`` so agy registers our workspace as an
        "active workspace" for its built-in tools (``write_to_file``,
        ``view_file``, ``run_command``). Without this flag, agy's
        ``write_to_file`` defaults to its internal
        ``.antigravity/antigravity-cli/scratch/`` directory — files land
        outside the workspace where peer agents, snapshot promotion, and
        next-round verification can't find them. Verified live: with
        ``--add-dir`` agy writes to ``<cwd>/hello.txt``; without it agy
        writes to ``<cwd>/.antigravity/antigravity-cli/scratch/hello.txt``
        and the response explicitly asks the user to "set the scratch
        subdirectory as your active workspace."

        Each MassGen call is a single-shot ``-p`` invocation — the orchestrator
        already injects prior-response context into retry prompts, so agy's
        ``--continue``/``--conversation`` session resumption is unnecessary (and
        ``--conversation`` with a UUID we generated fails with
        "conversation X not found" since agy assigns its own IDs).
        """
        cmd: list[str] = [self._agy_path]
        cmd.extend(["--gemini_dir", str(self._workspace_config_dir())])
        cmd.extend(["--add-dir", str(Path(self.cwd).resolve())])
        log_path = self._agy_log_file_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        cmd.extend(["--log-file", str(log_path)])
        # agy 1.0.5+ exposes a real --model flag (exact label from `agy models`).
        # Emit it only when the configured model resolves to a known label;
        # otherwise fall back to agy's server-side default rather than passing a
        # bad value that would fail the call.
        model_label = self._resolve_agy_model_label(self.model)
        if model_label:
            cmd.extend(["--model", model_label])
        elif self.model:
            logger.info(
                f"Antigravity CLI: configured model '{self.model}' has no agy label " "mapping; using agy's default model.",
            )
        if self.dangerously_skip_permissions:
            cmd.append("--dangerously-skip-permissions")
        cmd.extend(["-p", prompt])
        return cmd

    def _scan_agy_log_for_errors(self) -> str | None:
        """Return a user-facing error string if agy's log shows a known failure.

        agy logs failures (quota 429, auth, etc.) at level ``E`` but still
        exits 0 with empty stdout, which leaves MassGen looping on empty
        retries. Surfacing the real message lets the orchestrator (and the
        user) see what actually happened.
        """
        log_path = self._agy_log_file_path()
        if not log_path.exists():
            return None
        try:
            text = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        if "RESOURCE_EXHAUSTED" in text or "code 429" in text:
            for line in text.splitlines():
                if "RESOURCE_EXHAUSTED" in line or "code 429" in line:
                    return f"Antigravity quota exhausted: {line.strip()}"
            return "Antigravity quota exhausted (HTTP 429)."
        if "PERMISSION_DENIED" in text or "UNAUTHENTICATED" in text:
            return "Antigravity authentication failed — run `agy` interactively to log in, or set GEMINI_API_KEY."
        return None

    def _build_subprocess_env(self) -> dict[str, str]:
        """Build the env passed to agy. Includes API-key passthrough and
        opt-in auto-update suppression (useful for deterministic tests).

        Live env vars take precedence so callers (and tests) can override
        the api_key captured at backend construction.
        """
        env = dict(os.environ)
        env["NO_COLOR"] = "1"
        if self.api_key:
            env.setdefault("GEMINI_API_KEY", self.api_key)
            env.setdefault("GOOGLE_API_KEY", self.api_key)
        if self.disable_auto_update:
            env["AGY_CLI_DISABLE_AUTO_UPDATE"] = "1"
        return env

    # ── Scratch deliverable promotion ─────────────────────────────────────

    def _scratch_dir(self) -> Path:
        """agy's internal scratch directory (under the workspace gemini_dir).

        agy may route ``write_to_file`` here instead of the workspace root —
        observed in the 2026-06-05 baseline run, where the SVG deliverable
        landed in ``.antigravity/antigravity-cli/scratch/`` and was invisible
        to snapshots (``.antigravity`` is in the filesystem manager's metadata
        exclusion set). 1.0.6 writes to the process cwd in the common case, but
        we keep this as a safety net so deliverables never get silently dropped.
        """
        return self._workspace_config_dir() / "antigravity-cli" / "scratch"

    @staticmethod
    def _snapshot_scratch_files(scratch_dir: Path) -> dict[Path, float]:
        """Record {path: mtime} of files currently in scratch (pre-run baseline).

        Used to detect which scratch files are NEW or MODIFIED by this run so
        :meth:`_promote_scratch_deliverables` only copies fresh deliverables.
        """
        out: dict[Path, float] = {}
        if not scratch_dir.exists():
            return out
        for p in scratch_dir.rglob("*"):
            if p.is_file():
                try:
                    out[p] = p.stat().st_mtime
                except OSError:
                    continue
        return out

    def _promote_scratch_deliverables(self, pre_existing: dict[Path, float]) -> list[str]:
        """Copy new/modified scratch files into the workspace root.

        Promotes any file under ``scratch/`` that wasn't present before the run
        (or was modified during it), preserving its relative path. Never
        clobbers a file the model already placed in the workspace — if the
        destination exists, the model's copy wins. Returns the list of promoted
        relative paths (for logging / "real output" detection).
        """
        scratch = self._scratch_dir()
        if not scratch.exists():
            return []
        workspace = Path(self.cwd).resolve()
        promoted: list[str] = []
        for src in scratch.rglob("*"):
            if not src.is_file():
                continue
            try:
                mtime = src.stat().st_mtime
            except OSError:
                continue
            prev = pre_existing.get(src)
            if prev is not None and mtime <= prev:
                continue  # unchanged pre-existing file
            rel = src.relative_to(scratch)
            dest = workspace / rel
            if dest.exists():
                continue  # model already placed it in the workspace; don't clobber
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
            except OSError as exc:
                logger.warning(f"Antigravity CLI: failed to promote scratch file {src}: {exc}")
                continue
            promoted.append(str(rel))
        if promoted:
            logger.info(
                f"Antigravity CLI: promoted {len(promoted)} scratch deliverable(s) to " f"workspace {workspace}: {promoted}",
            )
        return promoted

    # ── Transcript tailing ────────────────────────────────────────────────

    @staticmethod
    def _existing_transcripts(brain_dir: Path) -> set[Path]:
        if not brain_dir.exists():
            return set()
        return set(brain_dir.rglob("transcript.jsonl"))

    async def _find_and_tail_transcript(
        self,
        brain_dir: Path,
        pre_existing: set[Path],
        proc: asyncio.subprocess.Process,
    ) -> AsyncGenerator[StreamChunk]:
        """Locate the new transcript.jsonl agy creates and tail it in real-time."""
        logger.info(
            f"Antigravity CLI transcript tail starting — brain_dir={brain_dir} " f"exists={brain_dir.exists()} pre_existing_count={len(pre_existing)} agent_id={self.agent_id!r}",
        )
        transcript_path: Path | None = None
        for poll_iter in range(100):  # up to 10 s before giving up
            if brain_dir.exists():
                for p in brain_dir.rglob("transcript.jsonl"):
                    if p not in pre_existing:
                        transcript_path = p
                        break
            if transcript_path:
                break
            if proc.returncode is not None:
                break
            await asyncio.sleep(0.1)

        if not transcript_path:
            # Diagnose why we didn't find it: walk one level under brain_dir if
            # it exists at all, to surface what agy DID write. This is critical
            # for catching regressions where agy lands the brain dir elsewhere
            # (e.g., under the project root instead of appDataDir).
            if brain_dir.exists():
                children = list(brain_dir.iterdir())
                child_summary = [f"{c.name}/" if c.is_dir() else c.name for c in children[:10]]
            else:
                child_summary = "<brain_dir missing>"
            logger.warning(
                f"Antigravity CLI transcript tail: gave up after ~{poll_iter / 10:.1f}s "
                f"(brain_dir={brain_dir} exists={brain_dir.exists()} children={child_summary} "
                f"proc_returncode={proc.returncode}). No transcript events will reach TUI.",
            )
            return

        logger.info(f"Antigravity CLI transcript tail: streaming events from {transcript_path}")

        seen: set[int] = set()
        # FIFO queue of pending tool calls emitted from PLANNER_RESPONSE, matched
        # in order against subsequent RUN_COMMAND / CODE_ACTION result events.
        pending_tool_calls: list[dict[str, Any]] = []

        def process(event: dict[str, Any]) -> None:
            step = event.get("step_index", -1)
            if step in seen:
                return
            seen.add(step)
            try:
                self._process_transcript_event(event, pending_tool_calls)
            except Exception as exc:
                # Per-event isolation: a malformed transcript entry (e.g.,
                # missing ``created_at``, unexpected type) must not nuke the
                # whole tail. Log and move on so subsequent events still
                # reach the TUI.
                logger.warning(
                    f"Antigravity CLI: dropped malformed transcript event " f"step={step} type={event.get('type')}: {exc}",
                )

        with open(transcript_path) as fh:
            while True:
                line = fh.readline()
                if line:
                    line = line.strip()
                    if line:
                        try:
                            process(json.loads(line))
                        except json.JSONDecodeError:
                            pass
                else:
                    if proc.returncode is not None:
                        for line in fh:
                            line = line.strip()
                            if line:
                                try:
                                    process(json.loads(line))
                                except json.JSONDecodeError:
                                    pass
                        break
                    await asyncio.sleep(0.1)

        # Async generator must yield at least once — nothing to yield since all
        # output goes directly through the event emitter.
        return
        yield  # make this function an async generator

    def _process_transcript_event(
        self,
        event: dict[str, Any],
        pending_tool_calls: list[dict[str, Any]],
    ) -> None:
        """Emit structured TUI events for a single transcript entry.

        Uses the event emitter directly so the Textual TUI renders proper
        thinking bubbles and tool cards, not just mcp_status text blobs.
        """
        from massgen.logger_config import get_event_emitter

        source = event.get("source", "")
        event_type = event.get("type", "")
        status = event.get("status", "")
        _emitter = get_event_emitter()

        if source == "MODEL" and event_type == "PLANNER_RESPONSE":
            thinking = event.get("thinking", "")
            if thinking and _emitter:
                _emitter.emit_thinking(thinking, agent_id=self.agent_id)

            for tc in event.get("tool_calls", []):
                args = tc.get("args", {})
                action = args.get("toolAction") or args.get("toolSummary") or tc.get("name", "tool")
                if isinstance(action, str):
                    action = action.strip('"')
                tool_name = tc.get("name", "run_command")
                tool_id = f"agy_{event.get('step_index', 0)}_{len(pending_tool_calls)}"

                pending_tool_calls.append(
                    {
                        "tool_id": tool_id,
                        "tool_name": tool_name,
                        "action": action,
                        "created_at": event.get("created_at", ""),
                    },
                )

                if _emitter:
                    _emitter.emit_tool_start(
                        tool_id=tool_id,
                        tool_name=f"agy_{tool_name}",
                        args={"action": action},
                        server_name="agy",
                        agent_id=self.agent_id,
                    )

        elif source == "MODEL" and event_type in ("RUN_COMMAND", "CODE_ACTION"):
            pending = pending_tool_calls.pop(0) if pending_tool_calls else None
            if not pending or not _emitter:
                return

            is_error = status == "ERROR"
            content = event.get("content", "")
            if status == "DONE" and content:
                result = content.split("Output:\n", 1)[-1].strip() if "Output:\n" in content else ""
                if not result and "Created file" in content:
                    result = content.split("\n")[0].strip()
            elif is_error:
                result = content[:300]
            else:
                result = ""

            elapsed = 0.0
            try:
                from datetime import datetime, timezone

                fmt = "%Y-%m-%dT%H:%M:%SZ"
                t0 = datetime.strptime(pending["created_at"], fmt).replace(tzinfo=timezone.utc)
                t1 = datetime.strptime(event.get("created_at", pending["created_at"]), fmt).replace(tzinfo=timezone.utc)
                elapsed = (t1 - t0).total_seconds()
            except Exception:
                pass

            _emitter.emit_tool_complete(
                tool_id=pending["tool_id"],
                tool_name=f"agy_{pending['tool_name']}",
                result=result[:500] if result else "(no output)",
                elapsed_seconds=elapsed,
                status="error" if is_error else "success",
                is_error=is_error,
                agent_id=self.agent_id,
            )

    # ── Streaming ─────────────────────────────────────────────────────────

    @staticmethod
    async def _terminate_subprocess(
        proc: asyncio.subprocess.Process,
        grace_seconds: float = 2.0,
    ) -> None:
        """SIGTERM agy and wait up to ``grace_seconds`` before SIGKILL.

        Used on cancellation / unexpected error so we don't leak an orphan
        agy process when the orchestrator gives up on the agent (timeout,
        round restart, user abort, etc.).
        """
        if proc.returncode is not None:
            return
        try:
            proc.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(proc.wait(), timeout=grace_seconds)
        except TimeoutError:
            logger.warning(
                f"Antigravity CLI: agy didn't exit within {grace_seconds}s of SIGTERM — sending SIGKILL",
            )
            try:
                proc.kill()
            except ProcessLookupError:
                return
            try:
                await asyncio.wait_for(proc.wait(), timeout=grace_seconds)
            except TimeoutError:
                logger.error("Antigravity CLI: agy did not exit after SIGKILL — giving up")

    async def _stream_local(
        self,
        prompt: str,
    ) -> AsyncGenerator[StreamChunk]:
        """Run agy as a subprocess, tailing transcript.jsonl for real-time events."""
        cmd = self._build_exec_command(prompt)
        env = self._build_subprocess_env()
        logger.info("Running Antigravity CLI")

        brain_dir = self._workspace_config_dir() / "antigravity-cli" / "brain"
        pre_existing = self._existing_transcripts(brain_dir)
        # Baseline scratch contents so we can promote only files agy writes
        # during THIS run (safety net for the scratch-routing case).
        pre_existing_scratch = self._snapshot_scratch_files(self._scratch_dir())

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=self.cwd,
            env=env,
        )

        try:
            self.record_first_token()
        except (AttributeError, TypeError):
            pass
        yield StreamChunk(type="content", content="[Antigravity CLI] Running...\n")

        # Use a queue to merge stdout reader + transcript tailer.
        _DONE: object = object()
        queue: asyncio.Queue[StreamChunk | object] = asyncio.Queue()

        produced_real_output = {"value": False}

        async def _read_stdout() -> None:
            try:
                async for raw_line in proc.stdout:
                    text = raw_line.decode("utf-8", errors="replace")
                    if text:
                        produced_real_output["value"] = True
                        await queue.put(StreamChunk(type="content", content=text))
            finally:
                await proc.wait()
                await queue.put(_DONE)

        async def _tail() -> None:
            try:
                async for chunk in self._find_and_tail_transcript(brain_dir, pre_existing, proc):
                    produced_real_output["value"] = True
                    await queue.put(chunk)
            except Exception as exc:
                # Without this catch, exceptions inside _process_transcript_event
                # silently kill the tail task and the TUI gets zero thinking /
                # tool_start / tool_complete events for agent_b. Always log the
                # traceback so regressions are obvious in the orchestrator log.
                logger.exception(f"Antigravity CLI transcript tail crashed: {exc}")
            finally:
                await queue.put(_DONE)

        stdout_task = asyncio.create_task(_read_stdout())
        tail_task = asyncio.create_task(_tail())

        done_count = 0
        try:
            while done_count < 2:
                item = await queue.get()
                if item is _DONE:
                    done_count += 1
                else:
                    yield item  # type: ignore[misc]
        except (asyncio.CancelledError, GeneratorExit):
            # Orchestrator cancelled us (timeout, user abort, etc.). Cleanly
            # terminate agy so it doesn't outlive the agent task, then
            # propagate. Background reader tasks observe proc exit and finish
            # on their own.
            logger.info("Antigravity CLI: cancellation requested — terminating agy subprocess")
            await self._terminate_subprocess(proc)
            for task in (stdout_task, tail_task):
                task.cancel()
            raise
        except Exception as exc:
            logger.error(f"Antigravity CLI streaming error: {exc}")
            await self._terminate_subprocess(proc)
            yield StreamChunk(type="error", error=str(exc))
            return

        rc = proc.returncode
        if rc != 0:
            err_msg = f"agy exited with code {rc}"
            yield StreamChunk(type="error", error=err_msg)
            try:
                self.end_api_call_timing(success=False, error=err_msg)
            except (AttributeError, TypeError):
                pass
            return

        # Safety net: if agy routed write_to_file into its internal scratch dir
        # (excluded from snapshots), promote those deliverables into the
        # workspace root so peers + snapshot promotion can see them.
        try:
            promoted = self._promote_scratch_deliverables(pre_existing_scratch)
        except Exception as exc:
            logger.warning(f"Antigravity CLI: scratch promotion failed: {exc}")
            promoted = []
        if promoted:
            produced_real_output["value"] = True
            yield StreamChunk(
                type="content",
                content=f"\n[Antigravity CLI] Recovered {len(promoted)} deliverable(s) from scratch into the workspace: {', '.join(promoted)}\n",
            )

        # agy exits 0 with empty stdout on quota/auth failures — surface what
        # the log file actually says so the orchestrator doesn't retry-loop
        # against an empty response.
        if not produced_real_output["value"]:
            err_msg = self._scan_agy_log_for_errors() or ("agy returned no output (process exited cleanly with empty stdout " "and no transcript activity). Check agy's log file for details.")
            logger.error(f"Antigravity CLI: silent failure — {err_msg}")
            yield StreamChunk(type="content", content=f"\n[Antigravity CLI ERROR] {err_msg}\n")
            yield StreamChunk(type="error", error=err_msg)
            try:
                self.end_api_call_timing(success=False, error=err_msg)
            except (AttributeError, TypeError):
                pass
            return

        yield StreamChunk(type="done", usage={})
        try:
            self.end_api_call_timing(success=True)
        except (AttributeError, TypeError):
            pass

    async def stream_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        **kwargs,
    ) -> AsyncGenerator[StreamChunk]:
        """Stream a response from agy. Workflow tools (vote/new_answer) are
        injected as text instructions into the prompt and parsed from stdout,
        because agy 1.0.0's print-mode CLI does not load MCP tools mid-session.
        """
        from ..tool.workflow_toolkits.base import WORKFLOW_TOOL_NAMES
        from .base import build_workflow_instructions, parse_workflow_tool_calls

        # Pick up agent_id from kwargs so transcript-emitter events label the
        # right agent (siblings do the same). Falls back to construction-time id.
        self.agent_id = self.agent_id or kwargs.get("agent_id")

        try:
            await self._ensure_authenticated()
        except RuntimeError as exc:
            yield StreamChunk(type="error", error=str(exc))
            return

        prompt = self._build_prompt_from_messages(messages)
        if not prompt.strip():
            yield StreamChunk(type="error", error="No user message found in messages")
            return

        latest_system = self._extract_latest_system_message(messages)
        if latest_system:
            self.system_prompt = latest_system

        # Workflow-mode inference (parity with gemini_cli): when prior rounds
        # produced no candidate answers, `vote` is not a valid action this
        # turn — strip it from both the tool exposure to agy and from any
        # text-fallback calls we parse back.
        self._workflow_call_mode = self._infer_workflow_call_mode(messages, tools or [])
        mode_filtered_tools = self._filter_workflow_tools_for_mode(tools or [], self._workflow_call_mode)
        if self._workflow_call_mode == "new_answer_only" and len(mode_filtered_tools) != len(tools or []):
            logger.info("Antigravity CLI: new_answer_only mode active; omitting vote from workflow toolset")

        # Reset per-turn dedup flag now that we know we're entering a new stream.
        self._workflow_call_emitted_this_turn = False

        # Workflow tools via text fallback: detect them in the (mode-filtered)
        # tools arg, inject formatting guidance into the prompt, and parse
        # stdout for matching calls. agy 1.0.x does not expose MCP tools as
        # native tools in print mode (confirmed by binary-strings probe + live
        # test), so text fallback is the only path.
        workflow_tools_present = any((t.get("function", {}).get("name") or t.get("name")) in WORKFLOW_TOOL_NAMES for t in mode_filtered_tools)
        workflow_instructions = build_workflow_instructions(mode_filtered_tools) if workflow_tools_present else ""
        workflow_allowed_names = {(t.get("function", {}).get("name") or t.get("name")) for t in mode_filtered_tools if (t.get("function", {}).get("name") or t.get("name")) in WORKFLOW_TOOL_NAMES}

        # agy -p has no separate system channel — anything prepended to the
        # prompt ends up inside <USER_REQUEST>, which confused the model. The
        # MassGen system prompt is written to AGENTS.md instead (loaded by agy
        # as workspace context); the -p argument carries only workflow tool
        # guidance and the actual user message.
        prompt_parts: list[str] = []
        # Post-evaluation phase guard (parity with gemini_cli) — only fires when
        # `submit` AND `restart_orchestration` are both in the tools list.
        phase_prefix = self._build_phase_prompt_prefix(tools or [])
        if phase_prefix:
            prompt_parts.append(phase_prefix)
            logger.info("Antigravity CLI: applying post-evaluation prompt guard")
        if workflow_instructions:
            prompt_parts.append(workflow_instructions)
        prompt_parts.append(prompt)
        full_prompt = "\n\n".join(p for p in prompt_parts if p)

        # Anchor agy's project discovery at the workspace root. Without this,
        # agy walks up looking for a `.antigravitycli/` directory and adopts
        # whichever parent it finds first — breaking workspace isolation and
        # making --add-dir ineffective.
        self._ensure_workspace_project_marker()
        self._write_mcp_config()
        # Hooks are gated by `enableJsonHooks: true` in settings.json (per agy's
        # `json-hooks-enabled` feature flag). Write hooks.json first, then pass
        # has_hooks to the settings writer so the flag and the file are emitted
        # together — otherwise agy logs "skipping hooks.json" instead of
        # "Loaded hooks.json".
        hooks_written = self._write_hooks_json()
        self._write_workspace_settings_json(has_hooks=hooks_written)
        self._write_system_prompt_md()
        try:
            try:
                self.start_api_call_timing(self.model)
            except (AttributeError, TypeError):
                pass

            self._clear_streaming_buffer(**kwargs) if hasattr(self, "_clear_streaming_buffer") else None

            accumulated_content = ""
            done_chunk: StreamChunk | None = None
            async for chunk in self._stream_local(full_prompt):
                if chunk.type == "content" and chunk.content:
                    accumulated_content += chunk.content
                    if hasattr(self, "_append_to_streaming_buffer"):
                        self._append_to_streaming_buffer(chunk.content)
                # Hold the `done` chunk so workflow tool_calls can be yielded
                # before terminal events (mirrors gemini_cli.py:1529-1531 pattern).
                if chunk.type == "done" and workflow_tools_present:
                    done_chunk = chunk
                    continue
                yield chunk

            yielded_any_workflow_call = False
            if workflow_tools_present and accumulated_content:
                tool_calls = parse_workflow_tool_calls(
                    accumulated_content,
                    allowed_tool_names=workflow_allowed_names or None,
                )
                original_count = len(tool_calls)
                tool_calls = self._filter_workflow_tool_calls_for_mode(tool_calls, self._workflow_call_mode)
                if len(tool_calls) != original_count:
                    logger.info(
                        f"Antigravity CLI: dropped {original_count - len(tool_calls)} parsed " f"workflow tool call(s) invalid for mode={self._workflow_call_mode}",
                    )
                if tool_calls and self._workflow_call_emitted_this_turn:
                    # Already yielded one workflow call this stream; suppress
                    # duplicates so the orchestrator doesn't see multiple
                    # new_answer submissions in a single turn.
                    logger.info("Antigravity CLI: suppressing duplicate workflow tool call(s) (already emitted this turn)")
                    tool_calls = []
                if tool_calls:
                    logger.info(
                        f"Antigravity CLI: parsed {len(tool_calls)} workflow tool call(s) " f"from agy stdout (text fallback path)",
                    )
                    self._workflow_call_emitted_this_turn = True
                    yielded_any_workflow_call = True
                    yield StreamChunk(
                        type="tool_calls",
                        tool_calls=tool_calls,
                        source="antigravity_cli",
                    )

            # Track for next-turn diagnostics + retry-mode logic. Mirrors
            # gemini_cli.py:1553 — when set, callers (or future logic here)
            # can treat the prior turn as a no-decision turn.
            self._last_turn_missing_workflow_call = workflow_tools_present and not yielded_any_workflow_call

            if done_chunk is not None:
                yield done_chunk

            agent_id = self.agent_id or kwargs.get("agent_id")
            if hasattr(self, "_finalize_streaming_buffer"):
                self._finalize_streaming_buffer(agent_id=agent_id)
        finally:
            self._restore_mcp_config()
            self._restore_hooks_json()
            self._restore_system_prompt_md()

    # ── Message helpers ───────────────────────────────────────────────────

    @staticmethod
    def _message_content_to_text(content: Any) -> str:
        """Squash a message's content into plain text for the ``agy -p`` arg.

        Multimodal parts (images, audio, video, files) are inlined as
        human-readable references — agy has filesystem/shell tools and can
        ``read`` paths or fetch URLs itself when asked. We never silently
        drop a non-text part; the goal is that the model sees enough to act.
        """
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for c in content:
                if not isinstance(c, dict):
                    parts.append(str(c))
                    continue
                if isinstance(c.get("text"), str):
                    parts.append(c["text"])
                    continue
                ctype = c.get("type") or ""
                # Image / audio / video / file references — surface a path or
                # URL the agent can use via its native filesystem tools.
                for key in ("source_path", "image_path", "audio_path", "video_path", "file_path", "url", "image_url"):
                    val = c.get(key)
                    if isinstance(val, str) and val:
                        kind = ctype or key.split("_")[0]
                        parts.append(f"[{kind}: {val}]")
                        break
                else:
                    # base64-inlined content: too large for the prompt;
                    # surface a brief stub so the agent knows it exists.
                    if c.get("base64"):
                        mime = c.get("mime_type", "binary")
                        parts.append(f"[inline {ctype or mime} attachment ({len(c.get('base64', ''))} chars b64) — write to a local file if you need to inspect it]")
                    elif ctype:
                        parts.append(f"[{ctype} part]")
            return "".join(parts)
        return str(content)

    def _build_prompt_from_messages(self, messages: list[dict[str, Any]]) -> str:
        """Squash the user's latest message into a single prompt string."""
        for msg in reversed(messages or []):
            if msg.get("role") == "user":
                return self._message_content_to_text(msg.get("content", ""))
        return ""

    def _extract_latest_system_message(self, messages: list[dict[str, Any]]) -> str:
        latest = ""
        for msg in messages or []:
            if msg.get("role") == "system":
                latest = self._message_content_to_text(msg.get("content", ""))
        return latest

    # ── Workflow-mode inference (parity with gemini_cli.py) ───────────────

    @staticmethod
    def _extract_latest_current_answers_block(messages: list[dict[str, Any]]) -> str | None:
        """Extract the latest <CURRENT ANSWERS …> block from messages.

        Ported verbatim from gemini_cli.py:347. The orchestrator embeds prior-
        round candidate answers in this block; presence + emptiness drives
        whether ``vote`` is a valid action this turn.
        """
        for msg in reversed(messages or []):
            content = msg.get("content", "") if isinstance(msg, dict) else ""
            text = AntigravityCLIBackend._message_content_to_text(content)
            matches = list(_RE_CURRENT_ANSWERS.finditer(text))
            if matches:
                return matches[-1].group(1)
        return None

    @staticmethod
    def _current_answers_block_has_answers(block: str) -> bool:
        """True iff the block contains at least one ``<agent…>`` tag.

        Mirrors gemini_cli.py:358.
        """
        return bool(_RE_AGENT_TAG.search(block or ""))

    def _infer_workflow_call_mode(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> str:
        """Infer whether ``vote`` is valid this turn or only ``new_answer``.

        Returns ``"new_answer_only"`` when a CURRENT ANSWERS block exists but
        contains no candidate answers (so voting has no target). Returns
        ``"any"`` otherwise. Retry-sticky: once ``new_answer_only`` is set,
        sticks until a non-empty CURRENT ANSWERS block appears.

        Mirrors gemini_cli.py:448 exactly so cross-backend behavior stays
        consistent in multi-agent runs.
        """
        tool_names = {t.get("function", {}).get("name") for t in (tools or [])}
        if "vote" not in tool_names or "new_answer" not in tool_names:
            return "any"

        current_answers_block = self._extract_latest_current_answers_block(messages)
        if current_answers_block is not None:
            if self._current_answers_block_has_answers(current_answers_block):
                return "any"
            return "new_answer_only"

        # No block at all → preserve any prior new_answer_only sticky decision.
        if self._workflow_call_mode == "new_answer_only":
            return "new_answer_only"
        return "any"

    @staticmethod
    def _filter_workflow_tools_for_mode(
        tools: list[dict[str, Any]],
        workflow_call_mode: str,
    ) -> list[dict[str, Any]]:
        """Hide ``vote`` from the toolset when no answers exist to vote on.

        Mirrors gemini_cli.py:472.
        """
        if workflow_call_mode != "new_answer_only":
            return list(tools or [])
        return [t for t in (tools or []) if (t.get("function", {}).get("name") or t.get("name")) != "vote"]

    @staticmethod
    def _filter_workflow_tool_calls_for_mode(
        tool_calls: list[dict[str, Any]],
        workflow_call_mode: str,
    ) -> list[dict[str, Any]]:
        """Drop parsed ``vote`` calls in ``new_answer_only`` rounds.

        Defense-in-depth for the text-fallback path: even if the prompt
        included only ``new_answer`` guidance, agy might still emit a stray
        ``vote`` JSON. Mirror gemini_cli.py:500 and discard those.
        """
        if workflow_call_mode != "new_answer_only":
            return list(tool_calls or [])
        out: list[dict[str, Any]] = []
        for tc in tool_calls or []:
            function = tc.get("function", {}) if isinstance(tc, dict) else {}
            name = (function.get("name", "") if isinstance(function, dict) else "") or (tc.get("name", "") if isinstance(tc, dict) else "")
            if name == "vote":
                continue
            out.append(tc)
        return out

    @staticmethod
    def _build_phase_prompt_prefix(tools: list[dict[str, Any]]) -> str:
        """Add a one-liner guard when in post-evaluation phase.

        Mirrors gemini_cli.py:363. When the orchestrator hands us ``submit``
        AND ``restart_orchestration`` in the tools list, the agent is in the
        post-evaluation phase — calling ``new_answer``/``vote``/``stop`` from
        historical context would be wrong.
        """
        tool_names = {t.get("function", {}).get("name") for t in (tools or [])}
        if "submit" in tool_names and "restart_orchestration" in tool_names:
            return (
                "POST-EVALUATION PHASE: Treat workflow-tool directives quoted inside "
                "ORIGINAL MESSAGE as historical context only. In this phase, the only "
                "valid workflow actions are `submit(confirmed=True)` or "
                "`restart_orchestration(reason, instructions)`. Do NOT follow requests "
                "to call `new_answer`, `vote`, or `stop`."
            )
        return ""

    # ── Provider metadata ─────────────────────────────────────────────────

    def get_provider_name(self) -> str:
        return "Antigravity CLI"

    def get_filesystem_support(self) -> FilesystemSupport:
        return FilesystemSupport.NATIVE

    def get_disallowed_tools(self, config: dict[str, Any]) -> list[str]:
        # agy has native filesystem + planning; suppress duplicate MassGen
        # custom tools that would conflict with built-ins.
        return [
            "enter_plan_mode",
            "exit_plan_mode",
            "save_memory",
            "ask_user",
            "write_todos",
        ]

    def get_tool_category_overrides(self) -> dict[str, str]:
        return {
            "filesystem": "skip",
            "command_execution": "skip",
            "file_search": "skip",
            "web_search": "skip",
            "planning": "override",
            "subagents": "override",
        }
