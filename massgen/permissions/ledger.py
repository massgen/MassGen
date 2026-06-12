"""P2.1 — ApprovalLedger (append-only audit trail) + ApprovalBudget.

The ledger writes one JSON line per permission decision at the approval
chokepoint, so a run's authorizations are reconstructable after the fact
(who/what/why/outcome). It is append-only and crash-safe (flush per line) and
deliberately thin — it records, it never decides.

The budget is a per-agent consecutive-auto-approval counter: a runaway agent
that keeps getting auto-allowed will trip the cap, signalling the caller to
re-surface a human checkpoint instead of rubber-stamping forever (mirrors the
RoundTimeout circuit-breaker pattern; inspired by Cline's Max Requests).

Both are opt-in. A PermissionCoordinator constructed without a ledger behaves
exactly as before — no file, no overhead.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ..logger_config import logger
from .models import AuthorizationObject, GrantScope


class ApprovalLedger:
    """Append-only JSONL record of permission decisions for one run."""

    def __init__(self, path: str | Path, *, run_id: str = "") -> None:
        self.path = Path(path)
        self.run_id = run_id
        self._seq = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Resume sequence numbering if the file already has entries (idempotent
        # across restarts — don't collide seqs on a resumed run).
        if self.path.exists():
            try:
                self._seq = sum(1 for _ in self.path.open("r", encoding="utf-8"))
            except OSError:
                self._seq = 0

    def record(
        self,
        authz: AuthorizationObject,
        *,
        allowed: bool,
        operator: str,
        scope: GrantScope = GrantScope.ONCE,
        source: str = "provider",
        feedback: str | None = None,
    ) -> dict[str, Any]:
        """Append one decision entry and return it."""
        entry: dict[str, Any] = {
            "seq": self._seq,
            "timestamp": time.time(),
            "run_id": self.run_id,
            "agent_id": authz.agent_id,
            "tool": authz.tool,
            "normalized_pattern": authz.normalized_pattern,
            "risk": authz.risk.value if hasattr(authz.risk, "value") else str(authz.risk),
            "reason": authz.reason,
            "args_preview": authz.args_preview,
            "decision": "allow" if allowed else "deny",
            "operator": operator,
            "scope": scope.value if hasattr(scope, "value") else str(scope),
            "source": source,
        }
        if feedback:
            entry["feedback"] = feedback
        self._seq += 1
        try:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, default=str) + "\n")
                fh.flush()
        except OSError as exc:  # auditing must never break the run
            logger.warning(f"[ApprovalLedger] failed to write entry: {exc}")
        return entry

    def entries(self) -> list[dict[str, Any]]:
        """Read all recorded entries back in order (skips any corrupt line)."""
        if not self.path.exists():
            return []
        out: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out


class ApprovalBudget:
    """Per-agent consecutive auto-approval counter (runaway-loop circuit breaker).

    ``check_auto(agent_id)`` is called for each *auto* (non-human) approval. It
    returns True while the agent is within budget and False once it exceeds the
    cap — the caller should then force a human checkpoint or halt. ``reset`` is
    called whenever a human actually weighs in, clearing that agent's streak.
    """

    def __init__(self, max_consecutive_auto: int = 25) -> None:
        self.max_consecutive_auto = max(1, max_consecutive_auto)
        self._counts: dict[str, int] = {}

    def check_auto(self, agent_id: str) -> bool:
        count = self._counts.get(agent_id, 0) + 1
        self._counts[agent_id] = count
        return count <= self.max_consecutive_auto

    def reset(self, agent_id: str) -> None:
        self._counts.pop(agent_id, None)
