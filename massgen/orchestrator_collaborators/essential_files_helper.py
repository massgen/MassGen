"""Essential-files manifest loader, extracted from Orchestrator.

The orchestrator-managed checklist gate writes a per-agent
``memory/short_term/essential_files_manifest.json`` describing which workspace
files an agent considers essential at the end of its round. This collaborator
reads those manifests back so the next round can include them as context for
peer agents.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from massgen.logger_config import logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class EssentialFilesHelper:
    """Read per-agent essential_files_manifest.json from snapshot storage."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    def load_essential_files_manifests(self, agent_id: str) -> dict[str, Any]:
        """Load essential_files_manifest.json from all agents' snapshots.

        Returns a dict mapping anonymous agent ID to parsed manifest data.
        Skips agents without manifests or with invalid JSON.
        """
        orch = self._orchestrator
        manifests: dict[str, Any] = {}
        if not orch._snapshot_storage:
            return manifests

        agent_mapping = orch.coordination_tracker.get_reverse_agent_mapping()
        snapshot_base = Path(orch._snapshot_storage)

        for source_agent_id in orch.agents:
            anon_id = agent_mapping.get(source_agent_id, source_agent_id)
            manifest_path = snapshot_base / source_agent_id / "memory" / "short_term" / "essential_files_manifest.json"
            if not manifest_path.exists():
                continue
            try:
                manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
                if not isinstance(manifest_data, dict) or manifest_data.get("version") != 1:
                    logger.warning(
                        f"[EssentialFiles] Invalid manifest version for {source_agent_id}, skipping",
                    )
                    continue
                manifests[anon_id] = manifest_data
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(
                    f"[EssentialFiles] Failed to load manifest for {source_agent_id}: {e}",
                )
        return manifests
