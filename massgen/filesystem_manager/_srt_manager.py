"""SRT (Anthropic sandbox-runtime) manager for MassGen.

OS-level command/code execution sandboxing using Anthropic's
`@anthropic-ai/sandbox-runtime` (CLI `srt`): bubblewrap on Linux, Seatbelt
(`sandbox-exec`) on macOS. SRT has no Python API, so integration is by
**command wrapping**: ``srt --settings <cfg.json> <command>``.

Design notes (see plan + memory):
  - **Defense in depth, not either/or.** SRT settings are *derived from the same*
    `PathPermissionManager` policy as the application-level permission layer, so
    the two layers can't drift. The OS layer backstops the app layer (shell
    escapes, MCP-server bugs, prompt-injected file ops).
  - **Sandbox the executor, not the orchestrator.** We only ever wrap MassGen's
    own execution surface — the command-execution MCP and the fs-tools MCP server
    — never MassGen itself. Backends with their OWN execution sandbox (codex's
    `--full-auto` Landlock/Seatbelt, claude_code) use that instead of SRT.
  - **Network deny-all by default.** An allowlisted domain is a capability grant
    (allowlist-only egress can leak via embedded API keys), so the allowlist is
    strictly opt-in.

This module is import-safe without `srt` installed; the binary is only required
at actual execution time (`verify_available()` / runtime).
"""

from __future__ import annotations

import json
import platform
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..logger_config import logger
from ._base import Permission

if TYPE_CHECKING:
    from ._path_permission_manager import PathPermissionManager

# Default binary name (overridable for tests / custom installs).
DEFAULT_SRT_BINARY = "srt"

# Credential/secret locations denied for READS by default. SRT reads are otherwise
# allow-all (empty denyRead = full read access), so without this a sandboxed command
# could `cat ~/.ssh/id_rsa` and exfiltrate secrets — the sandbox would only constrain
# writes/network. We deny the well-known secret stores (NOT all of $HOME, so commands
# can still read ~/.cache, ~/.local, system libs, etc. and keep working). Users extend
# via command_line_srt_deny_read.
_DEFAULT_DENY_READ_HOME_RELATIVE = (
    ".ssh",
    ".aws",
    ".gnupg",
    ".netrc",
    ".npmrc",
    ".pypirc",
    ".docker/config.json",
    ".git-credentials",
    ".kube",
    ".azure",
    ".config/gcloud",
    ".config/gh",
)
_DEFAULT_DENY_READ_ABSOLUTE = ("/etc/shadow",)

# Read-confinement modes (SRT reads are allow-all by default; deny-then-allow, where
# allowRead WINS over denyRead).
#   "confined" (default): deny all of $HOME, re-allow the agent's managed paths
#       (workspace + context + temp). Denies personal data/secrets/other projects;
#       system paths (/usr, /opt, …) outside $HOME stay readable so commands run.
#   "strict":   deny "/", re-allow managed paths + a system runtime baseline + extras.
#       Tightest; may break commands that read an unlisted path.
#   "open":     allow-all reads except the built-in secret denylist + extras.
READ_MODE_CONFINED = "confined"
READ_MODE_STRICT = "strict"
READ_MODE_OPEN = "open"
READ_MODES = (READ_MODE_CONFINED, READ_MODE_STRICT, READ_MODE_OPEN)

# System roots a sandboxed command needs to READ to run, used by "strict" mode.
_STRICT_SYSTEM_READ_BASELINE = (
    "/usr",
    "/bin",
    "/sbin",
    "/etc",
    "/opt",
    "/dev",
    "/tmp",
    "/var",
    "/private",  # macOS: /private/var, /private/tmp
    "/System",  # macOS
    "/Library",  # macOS
    "/lib",  # linux
    "/lib64",
    "/proc",
    "/sys",
    "/run",
)

# Profiles -------------------------------------------------------------------
# "execution": tight — reflects exactly what the AGENT may write.
# "fs_tools":  widened — the fs-tools MCP server also writes temp + snapshot
#              storage on the framework's behalf (e.g. snapshots), which the
#              agent itself sees as read-only.
EXECUTION_PROFILE = "execution"
FS_TOOLS_PROFILE = "fs_tools"


# --------------------------------------------------------------------------- #
# Pure wrapping helpers — SINGLE SOURCE OF TRUTH.
# Imported by the code-execution MCP server subprocess too, so the wrapping is
# identical everywhere.
# --------------------------------------------------------------------------- #
def wrap_command_with_srt(command: str, settings_path: str | Path, srt_path: str = DEFAULT_SRT_BINARY) -> str:
    """Wrap a shell command string so it runs under SRT.

    Returns a string suitable for ``subprocess.run(..., shell=True)``. The
    original command is passed as a single quoted argument to ``sh -c`` so that
    shell features (pipes, redirection) execute *inside* the sandbox rather than
    in the outer, unsandboxed shell.
    """
    import shlex

    return f"{srt_path} --settings {shlex.quote(str(settings_path))} sh -c {shlex.quote(command)}"


def wrap_argv_with_srt(argv: list[str], settings_path: str | Path, srt_path: str = DEFAULT_SRT_BINARY) -> list[str]:
    """Wrap an argv list (e.g. ``["codex", "exec", ...]``) so it runs under SRT."""
    return [srt_path, "--settings", str(settings_path), *argv]


def srt_available(srt_path: str = DEFAULT_SRT_BINARY) -> bool:
    """True if the `srt` binary is discoverable on PATH."""
    return shutil.which(srt_path) is not None


def _framework_read_roots() -> list[str]:
    """Read roots the framework's OWN MCP servers need to start under SRT.

    When SRT wraps a framework server (``fastmcp run <massgen script> …``), the
    sandbox must be able to READ the server's code, the Python interpreter, the
    installed dependencies (fastmcp, mcp, GitPython, …), and the runtime config those
    dependencies require at startup. In a typical dev/editable install all of these
    live under ``$HOME`` — exactly the region ``confined``/``strict`` deny — so without
    re-allowing them ``srt`` denies the read and the server never starts (first the
    server's own script, then GitPython's ``git version`` reading ``~/.gitconfig``).

    Returns, all framework code/runtime (NOT user data — these don't widen access to
    secrets or other projects):
      - ``sys.prefix`` / ``sys.base_prefix`` — interpreter + site-packages (deps)
      - the ``massgen`` package directory — the server scripts
      - git's user config (``~/.gitconfig``, ``~/.config/git``) — git is core to the
        workspace model (snapshots/commits via GitPython); git reads its global config
        on essentially every invocation.
    """
    import sys

    roots = {sys.prefix, sys.base_prefix}
    try:
        import massgen

        roots.add(str(Path(massgen.__file__).resolve().parent))
    except Exception:  # pragma: no cover - massgen is always importable in practice
        pass
    home = Path.home()
    roots.add(str(home / ".gitconfig"))
    roots.add(str(home / ".config" / "git"))
    return sorted(roots)


class SrtManager:
    """Builds per-agent SRT settings and wraps commands.

    Mirrors the lightweight, contract-style shape of ``DockerManager`` (no shared
    base class today). Holds a reference to the agent's ``PathPermissionManager``
    and reads ``managed_paths`` *lazily* at settings-build time, because paths are
    added progressively during ``FilesystemManager`` setup.
    """

    def __init__(
        self,
        path_permission_manager: PathPermissionManager,
        *,
        network_allowed_domains: list[str] | None = None,
        extra_deny_read: list[str] | None = None,
        allow_unix_sockets: list[str] | None = None,
        read_mode: str = READ_MODE_CONFINED,
        allow_read: list[str] | None = None,
        fs_tools_extra_writable: list[str | Path] | None = None,
        settings_dir: str | Path | None = None,
        srt_path: str = DEFAULT_SRT_BINARY,
    ) -> None:
        self.path_permission_manager = path_permission_manager
        self.network_allowed_domains = list(network_allowed_domains or [])
        self.extra_deny_read = list(extra_deny_read or [])
        self.allow_unix_sockets = list(allow_unix_sockets or [])
        self.read_mode = read_mode if read_mode in READ_MODES else READ_MODE_CONFINED
        self.allow_read = list(allow_read or [])
        self.fs_tools_extra_writable = [Path(p).resolve() for p in (fs_tools_extra_writable or [])]
        self.settings_dir = Path(settings_dir) if settings_dir else None
        self.srt_path = srt_path

    # ------------------------------------------------------------------ #
    # Settings derivation
    # ------------------------------------------------------------------ #
    def build_settings(self, profile: str = EXECUTION_PROFILE) -> dict[str, Any]:
        """Derive an SRT settings dict from the agent's path permissions.

        Reads are default-allowed by SRT; we only add protected paths to
        ``denyRead``. Writes are default-denied; ``allowWrite`` is allow-only.
        """
        managed = list(self.path_permission_manager.managed_paths)

        # Determine the set of writable paths for this profile.
        writable: list[Path] = [mp.path for mp in managed if mp.permission == Permission.WRITE]
        if profile == FS_TOOLS_PROFILE:
            # The fs-tools server also writes temp workspaces (read-only to the
            # agent) and the framework's snapshot storage.
            writable += [mp.path for mp in managed if mp.path_type == "temp_workspace"]
            writable += self.fs_tools_extra_writable

        writable_set = {str(p) for p in writable}

        # Per-context protected paths are immune from modification AND reading, even
        # when they live inside a writable context dir.
        protected_paths = [str(p) for mp in managed for p in (mp.protected_paths or [])]

        # Explicitly deny-write the read-only paths (belt-and-suspenders on top of
        # SRT's allow-only write model), excluding anything we just made writable,
        # plus the protected paths (immune even within a writable context).
        deny_write = [str(mp.path) for mp in managed if mp.permission == Permission.READ and str(mp.path) not in writable_set]
        deny_write += protected_paths

        # Reads: SRT defaults to allow-all (deny-then-allow; allowRead WINS over
        # denyRead). The managed paths the agent may read (re-allowed within any
        # denied region) plus user-configured extras:
        home = str(Path.home())
        managed_readable = [str(mp.path) for mp in managed]
        allow_read = managed_readable + [str(p) for p in self.fs_tools_extra_writable] + list(self.allow_read)

        # The fs-tools profile wraps a FRAMEWORK MCP server (fastmcp run <massgen
        # script>). Under confined/strict the server's own code + interpreter + deps
        # live in a denied region ($HOME), so re-allow the framework runtime roots or
        # the wrapped server can't read its own script and fails to start. This is
        # framework code, not user data; the agent's own command sandbox (execution
        # profile) stays tight and is unaffected. ("open" re-allows nothing because
        # it is allow-all-minus-denylist; the framework roots are readable anyway.)
        if profile == FS_TOOLS_PROFILE:
            allow_read = allow_read + _framework_read_roots()

        if self.read_mode == READ_MODE_OPEN:
            # Allow-all minus the secret denylist + protected + extras. (No allowRead:
            # protected/secret denies stay effective because nothing re-allows them.)
            deny_read = [str(Path(home) / rel) for rel in _DEFAULT_DENY_READ_HOME_RELATIVE]
            deny_read += list(_DEFAULT_DENY_READ_ABSOLUTE)
            deny_read += protected_paths
            deny_read += list(self.extra_deny_read)
            allow_read = []
        elif self.read_mode == READ_MODE_STRICT:
            # Deny everything; re-allow only managed paths + a system runtime baseline
            # (so the interpreter/libs are readable) + user extras.
            deny_read = ["/"] + list(self.extra_deny_read)
            allow_read = sorted(set(allow_read) | set(_STRICT_SYSTEM_READ_BASELINE))
        else:  # READ_MODE_CONFINED (default)
            # Deny all of $HOME (personal data/secrets/other projects), re-allow the
            # agent's managed paths within it; system paths outside $HOME stay
            # readable so commands run. NOTE: a protected sub-path inside an
            # allow-read context can't be read-denied here (allowRead wins); its
            # write-immunity (denyWrite) still holds.
            deny_read = [home, *_DEFAULT_DENY_READ_ABSOLUTE]
            deny_read += list(self.extra_deny_read)

        return {
            "filesystem": {
                "allowWrite": sorted(writable_set),
                "denyWrite": sorted(set(deny_write)),
                "denyRead": sorted(set(deny_read)),
                "allowRead": sorted(set(allow_read)),
            },
            "network": {
                "allowedDomains": list(self.network_allowed_domains),
                "deniedDomains": [],
                "allowUnixSockets": list(self.allow_unix_sockets),
            },
        }

    def write_settings_file(self, profile: str = EXECUTION_PROFILE, agent_id: str | None = None) -> Path:
        """Write the settings for ``profile`` to a JSON file and return its path."""
        target_dir = self.settings_dir or Path.cwd()
        target_dir.mkdir(parents=True, exist_ok=True)
        suffix = f"{agent_id}-" if agent_id else ""
        path = target_dir / f"srt-settings-{suffix}{profile}.json"
        path.write_text(json.dumps(self.build_settings(profile=profile), indent=2))
        logger.info(f"[SrtManager] Wrote {profile} settings to {path}")
        return path

    # ------------------------------------------------------------------ #
    # Wrapping (instance convenience; delegate to the pure helpers)
    # ------------------------------------------------------------------ #
    def wrap_command(self, command: str, settings_path: str | Path) -> str:
        return wrap_command_with_srt(command, settings_path, srt_path=self.srt_path)

    def wrap_argv(self, argv: list[str], settings_path: str | Path) -> list[str]:
        return wrap_argv_with_srt(argv, settings_path, srt_path=self.srt_path)

    # ------------------------------------------------------------------ #
    # Availability / platform guards
    # ------------------------------------------------------------------ #
    def verify_available(self) -> None:
        """Raise an actionable error if SRT can't run here."""
        system = platform.system()
        if system == "Windows":
            raise RuntimeError(
                "SRT sandboxing (command_line_execution_mode: srt) is not supported on Windows. " "Use 'docker' mode or run under Linux/macOS.",
            )
        if shutil.which(self.srt_path) is None:
            raise RuntimeError(
                "SRT sandboxing requires the 'srt' CLI (Anthropic sandbox-runtime), which was not found on PATH. " "Install it with: npm install -g @anthropic-ai/sandbox-runtime",
            )
